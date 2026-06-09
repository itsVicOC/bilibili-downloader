"""DASH stream downloader with FFmpeg merge support."""

import logging
import ssl
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from bilibili_downloader.api.client import BilibiliAPIError, BilibiliAPIClient
from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import DownloadItem, StreamInfo, VideoQuality

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
        self._max_retries = max_retries
        self._ffmpeg_path = ffmpeg_path
        self._cancelled = False

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
        )

        # Select video stream
        video_stream = self._select_video_stream(
            playurl_data["video_streams"],
            item.selected_quality,
            item.selected_video_codec,
        )
        if not video_stream:
            raise RuntimeError("No matching video stream found")

        # Select audio stream
        audio_stream = self._select_audio_stream(
            playurl_data["audio_streams"],
            item.selected_audio_quality,
        )
        if not audio_stream:
            raise RuntimeError("No matching audio stream found")

        # Create temp directory for streams
        with tempfile.TemporaryDirectory(dir=self._output_dir) as tmpdir:
            tmp = Path(tmpdir)
            video_path = tmp / "video.m4s"
            audio_path = tmp / "audio.m4s"
            output_path = (self._output_dir / item.filename).resolve()

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
            progress_callback(0.85, "正在合并视频...")
            success, msg = FFmpegManager.merge_streams(
                video_path,
                audio_path,
                output_path,
                custom_path=self._ffmpeg_path,
                cancel_checker=lambda: self._cancelled,
            )
            if not success:
                raise RuntimeError(f"FFmpeg merge failed: {msg}")

            progress_callback(1.0, "下载完成！")
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
                        return
                    except (httpx.HTTPError, ConnectionError, OSError) as e:
                        last_error = e
                        logger.debug(
                            "Download attempt %d failed for %s: %s",
                            attempt + 1, url, e,
                        )

                if attempt < self._max_retries - 1:
                    delay = _retry_delay(attempt, last_error)
                    time.sleep(delay)

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

        last_reported = -1.0
        with client.stream(
            "GET",
            url,
            headers=headers,
            timeout=120.0,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()

            append = resume_from > 0 and response.status_code == 206
            downloaded = resume_from if append else 0
            total = _response_total_size(response, downloaded)
            mode = "ab" if append else "wb"

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

    content_length = int(response.headers.get("content-length", 0))
    if response.status_code == 206:
        return downloaded + content_length
    return content_length


def _retry_delay(attempt: int, error: Optional[BaseException]) -> float:
    error_msg = str(error or "")
    if "SSL" in error_msg or "UNEXPECTED_EOF" in error_msg:
        return 3 * (attempt + 1)
    return 2 ** attempt
