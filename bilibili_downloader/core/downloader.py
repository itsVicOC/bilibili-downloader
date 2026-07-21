"""DASH stream downloader with FFmpeg merge support."""

import hashlib
import logging
import shutil
import ssl
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import DownloadItem, StreamInfo, VideoQuality
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

logger = logging.getLogger(__name__)

# Standard headers for stream download
STREAM_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.bilibili.com/",
}

CHUNK_SIZE = 8192
MAX_RETRIES = 5

# Create an SSL context that works around CDN issues
SSL_CONTEXT = ssl.create_default_context()
_OUTPUT_PATH_LOCK = threading.Lock()
_RESERVED_OUTPUT_PATHS: set[Path] = set()
_CACHE_PATH_LOCK = threading.Lock()
_RESERVED_CACHE_PATHS: set[Path] = set()


class StreamDownloader:
    """Downloads DASH video/audio streams and merges with FFmpeg."""

    def __init__(
        self,
        api_client: BilibiliAPIClient,
        output_dir: str,
        max_retries: int = MAX_RETRIES,
        ffmpeg_path: Optional[str] = None,
    ):
        self._api_client = api_client
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._max_retries = max(1, max_retries)
        self._ffmpeg_path = ffmpeg_path
        self._cancelled = False
        self.last_video_stream: Optional[StreamInfo] = None
        self.last_audio_stream: Optional[StreamInfo] = None

    def cancel(self):
        """Signal the downloader to cancel current operation."""
        self._cancelled = True

    def download(
        self,
        item: DownloadItem,
        progress_callback: Callable[[float, str], None],
    ) -> str:
        """Download a video to disk.

        Flow:
            1. Fetch playurl for fresh stream URLs
            2. Download video .m4s
            3. Download audio .m4s
            4. Merge with FFmpeg
            5. Clean up temp files

        Args:
            item: DownloadItem with video info and quality selection.
            progress_callback: Called with (progress 0-1, status_text).

        Returns:
            Path to the merged output file.
        """
        self._cancelled = False
        info = item.video_info

        progress_callback(0.0, "正在获取流地址...")

        # Determine fnval flags
        need_hdr = item.selected_quality in (VideoQuality.QHDR,)
        need_dolby = item.selected_quality in (VideoQuality.Q_DOLBY,)

        playurl_data = self._api_client.get_play_url(
            bvid=info.bvid,
            cid=info.cid,
            quality=item.selected_quality,
            need_hdr=need_hdr,
            need_dolby=need_dolby,
            preferred_codec=item.selected_video_codec,
        )

        # Select video stream
        video_stream = self._select_video_stream(
            playurl_data["video_streams"],
            item.selected_quality,
            item.selected_video_codec,
        )
        if not video_stream:
            raise RuntimeError("No matching video stream found")
        self.last_video_stream = video_stream

        # Select audio stream
        audio_stream = self._select_audio_stream(
            playurl_data["audio_streams"],
            item.selected_audio_quality,
        )
        if not audio_stream:
            raise RuntimeError("No matching audio stream found")
        self.last_audio_stream = audio_stream

        with _reserved_download_cache(self._output_dir, item) as tmp, _reserved_output_path(
            self._output_dir / item.filename
        ) as output_path:
            video_path = tmp / "video.m4s"
            audio_path = tmp / "audio.m4s"

            # Download video stream
            progress_callback(0.0, "正在下载视频流...")
            self._download_stream(
                video_stream,
                video_path,
                lambda p: progress_callback(p * 0.6, "正在下载视频流..."),
            )

            if self._cancelled:
                raise RuntimeError("Download cancelled by user")

            # Download audio stream
            progress_callback(0.6, "正在下载音频流...")
            self._download_stream(
                audio_stream,
                audio_path,
                lambda p: progress_callback(0.6 + p * 0.2, "正在下载音频流..."),
            )

            if self._cancelled:
                raise RuntimeError("Download cancelled by user")

            # Merge with FFmpeg
            progress_callback(0.82, "正在合并视频...")
            merged_path = tmp / "merged.mp4"
            success, msg = FFmpegManager.merge_streams(
                video_path,
                audio_path,
                merged_path,
                custom_path=self._ffmpeg_path,
                cancel_checker=lambda: self._cancelled,
            )
            if not success:
                raise RuntimeError(f"FFmpeg merge failed: {msg}")

            merged_path.replace(output_path)
            shutil.rmtree(tmp, ignore_errors=True)
            _remove_empty_cache_root(tmp.parent)

            progress_callback(1.0, "视频下载完成")
            return str(output_path)

    def _select_video_stream(
        self,
        streams: list[StreamInfo],
        quality: VideoQuality,
        preferred_codec: int = 12,  # HEVC
    ) -> Optional[StreamInfo]:
        """Find best matching video stream.

        Falls back to best available quality if requested quality not available.
        """
        # Try exact quality match first
        candidates = [s for s in streams if s.id == quality.value]
        if not candidates:
            # Fallback: group by quality, prefer requested codec within each group
            if not streams:
                return None
            # Find the closest available quality (prefer higher)
            available_ids = sorted({s.id for s in streams}, reverse=True)
            closest = None
            for qid in available_ids:
                if qid <= quality.value:
                    closest = qid
                    break
            if closest is None:
                closest = available_ids[-1]  # Fallback to lowest available
            candidates = [s for s in streams if s.id == closest]

        # Prefer requested codec
        for s in candidates:
            if s.codecid == preferred_codec:
                return s

        # Return highest bandwidth
        return max(candidates, key=lambda s: s.bandwidth)

    def _select_audio_stream(
        self,
        streams: list[StreamInfo],
        preferred_id: int = 30280,
    ) -> Optional[StreamInfo]:
        """Find best matching audio stream."""
        for s in streams:
            if s.id == preferred_id:
                return s
        # Fallback to highest quality audio
        if streams:
            return max(streams, key=lambda s: s.bandwidth)
        return None

    def _download_stream(
        self,
        stream: StreamInfo,
        dest: Path,
        progress_callback: Callable[[float], None],
    ) -> None:
        """Download a single .m4s stream with progress tracking and retry."""
        last_error = None
        complete_marker = dest.with_suffix(f"{dest.suffix}.complete")
        if _has_valid_completion_marker(dest, complete_marker):
            progress_callback(1.0)
            return
        urls = _stream_urls(stream)
        if not urls:
            raise RuntimeError("下载失败：流地址为空")

        # Reuse a single httpx.Client across all retries for connection pooling
        transport = httpx.HTTPTransport(
            http2=False,
            retries=1,
            verify=SSL_CONTEXT,
        )
        with httpx.Client(transport=transport) as client:
            for attempt in range(self._max_retries):
                if self._cancelled:
                    raise RuntimeError("Download cancelled")

                for url in urls:
                    try:
                        self._download_url(client, url, dest, progress_callback)
                        try:
                            complete_marker.write_text(
                                str(dest.stat().st_size), encoding="ascii"
                            )
                        except OSError:
                            # The media is complete even if the optional resume marker
                            # cannot be persisted (for example on a read-only mount).
                            logger.debug(
                                "Unable to write completion marker %s",
                                complete_marker,
                                exc_info=True,
                            )
                        return
                    except (httpx.HTTPError, ConnectionError, OSError) as e:
                        last_error = e
                        logger.debug(
                            "Download attempt %d failed for %s: %s",
                            attempt + 1, url, e,
                        )

                if attempt < self._max_retries - 1:
                    delay = _retry_delay(attempt, last_error)
                    self._wait_for_retry(delay)

        raise RuntimeError(
            f"下载失败：{last_error}"
        )

    def _download_url(
        self,
        client: httpx.Client,
        url: str,
        dest: Path,
        progress_callback: Callable[[float], None],
    ) -> None:
        """Download one URL, resuming from an existing partial file when possible."""
        resume_from = dest.stat().st_size if dest.exists() else 0
        headers = dict(STREAM_HEADERS)
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"

        current_url = trusted_https_url(url, BILIBILI_RESOURCE_HOSTS)
        for _ in range(8):
            with client.stream(
                "GET",
                current_url,
                headers=headers,
                timeout=120.0,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    current_url = trusted_https_url(
                        urljoin(current_url, location),
                        BILIBILI_RESOURCE_HOSTS,
                    )
                    continue
                self._write_response(response, dest, resume_from, progress_callback)
                return
        raise RuntimeError("下载失败：媒体地址重定向次数过多")

    def _write_response(
        self,
        response: httpx.Response,
        dest: Path,
        resume_from: int,
        progress_callback: Callable[[float], None],
    ) -> None:
        """Validate and persist a terminal media response."""
        if response.status_code == 416 and _range_already_complete(response, dest):
            progress_callback(1.0)
            return
        response.raise_for_status()

        append = resume_from > 0 and response.status_code == 206
        if response.status_code == 206:
            range_start = _content_range_start(response)
            if range_start != resume_from:
                raise httpx.ProtocolError(
                    "服务器返回的续传起点与本地文件大小不一致",
                    request=response.request,
                )
        downloaded = resume_from if append else 0
        total = _response_total_size(response, downloaded)
        mode = "ab" if append else "wb"

        last_reported = -1.0
        with open(dest, mode) as f:
            for chunk in response.iter_bytes(chunk_size=65536):
                if self._cancelled:
                    raise RuntimeError("Download cancelled")
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = min(downloaded / total, 1.0)
                    if pct - last_reported >= 0.05 or pct >= 1.0:
                        progress_callback(pct)
                        last_reported = pct

        progress_callback(1.0)

    def _wait_for_retry(self, delay: float) -> None:
        """Wait between retries while remaining responsive to cancellation."""
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if self._cancelled:
                raise RuntimeError("Download cancelled")
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))


def _stream_urls(stream: StreamInfo) -> list[str]:
    """Return base and backup URLs without duplicates."""
    urls = []
    for url in [stream.base_url, *stream.backup_url]:
        if url and url not in urls:
            urls.append(url)
    return urls


def _response_total_size(response: httpx.Response, downloaded: int) -> int:
    content_range = response.headers.get("content-range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)

    try:
        content_length = int(response.headers.get("content-length", 0))
    except (TypeError, ValueError):
        content_length = 0
    if response.status_code == 206:
        return downloaded + content_length
    return content_length


def _content_range_start(response: httpx.Response) -> Optional[int]:
    """Parse the first byte offset from a 206 Content-Range header."""
    value = response.headers.get("content-range", "")
    unit, separator, byte_range = value.partition(" ")
    start, dash, _remainder = byte_range.partition("-")
    if unit.lower() != "bytes" or not separator or not dash or not start.isdigit():
        return None
    return int(start)


def _retry_delay(attempt: int, error: Optional[BaseException]) -> float:
    error_msg = str(error or "")
    if "SSL" in error_msg or "UNEXPECTED_EOF" in error_msg:
        return 3 * (attempt + 1)
    return 2 ** attempt


def _range_already_complete(response: httpx.Response, dest: Path) -> bool:
    """Treat a 416 response as success when the partial file is already complete."""
    content_range = response.headers.get("content-range", "")
    if "/" not in content_range or not dest.is_file():
        return False
    total = content_range.rsplit("/", 1)[-1]
    return total.isdigit() and dest.stat().st_size == int(total)


def _has_valid_completion_marker(dest: Path, marker: Path) -> bool:
    if not dest.is_file() or not marker.is_file():
        return False
    try:
        expected_size = int(marker.read_text(encoding="ascii").strip())
        return expected_size > 0 and dest.stat().st_size == expected_size
    except (OSError, ValueError):
        return False


@contextmanager
def _reserved_output_path(requested: Path):
    """Reserve a non-existing output path across concurrent downloads."""
    requested = requested.resolve()
    with _OUTPUT_PATH_LOCK:
        candidate = requested
        counter = 2
        while candidate.exists() or candidate in _RESERVED_OUTPUT_PATHS:
            candidate = requested.with_name(
                f"{requested.stem} ({counter}){requested.suffix}"
            )
            counter += 1
        _RESERVED_OUTPUT_PATHS.add(candidate)
    try:
        yield candidate
    finally:
        with _OUTPUT_PATH_LOCK:
            _RESERVED_OUTPUT_PATHS.discard(candidate)


@contextmanager
def _reserved_download_cache(output_dir: Path, item: DownloadItem):
    """Reserve a stable cache directory so failed downloads can resume later."""
    identity = (
        f"{item.video_info.bvid}:{item.video_info.cid}:"
        f"{item.selected_quality.value}:{item.selected_video_codec}:"
        f"{item.selected_audio_quality}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    root = (output_dir / ".biliflow-parts").resolve()
    requested = root / digest
    with _CACHE_PATH_LOCK:
        candidate = requested
        counter = 2
        while candidate in _RESERVED_CACHE_PATHS:
            candidate = root / f"{digest}-{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=True)
        _RESERVED_CACHE_PATHS.add(candidate)
    try:
        yield candidate
    finally:
        with _CACHE_PATH_LOCK:
            _RESERVED_CACHE_PATHS.discard(candidate)


def _remove_empty_cache_root(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
