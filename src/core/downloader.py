"""DASH stream downloader with FFmpeg merge support."""

import logging
import ssl
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from src.api.client import BilibiliAPIError, BilibiliAPIClient
from src.api.endpoints import USER_AGENT
from src.core.ffmpeg import FFmpegManager
from src.core.models import DownloadItem, StreamInfo, VideoQuality

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
                video_stream.base_url,
                video_path,
                lambda p: progress_callback(p * 0.6, "正在下载视频流..."),
            )

            if self._cancelled:
                raise RuntimeError("Download cancelled by user")

            # Download audio stream
            progress_callback(0.6, "正在下载音频流...")
            self._download_stream(
                audio_stream.base_url,
                audio_path,
                lambda p: progress_callback(0.6 + p * 0.2, "正在下载音频流..."),
            )

            if self._cancelled:
                raise RuntimeError("Download cancelled by user")

            # Merge with FFmpeg
            progress_callback(0.85, "正在合并视频...")
            success, msg = FFmpegManager.merge_streams(
                video_path, audio_path, output_path, custom_path=self._ffmpeg_path,
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
        url: str,
        dest: Path,
        progress_callback: Callable[[float], None],
    ) -> None:
        """Download a single .m4s stream with progress tracking and retry."""
        last_error = None
        last_reported = -1.0  # Throttle progress reports

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

                try:
                    with client.stream(
                        "GET",
                        url,
                        headers=STREAM_HEADERS,
                        timeout=120.0,
                        follow_redirects=True,
                    ) as response:
                        response.raise_for_status()
                        total = int(response.headers.get("content-length", 0))
                        downloaded = 0

                        with open(dest, "wb") as f:
                            for chunk in response.iter_bytes(chunk_size=65536):
                                if self._cancelled:
                                    raise RuntimeError("Download cancelled")
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    pct = downloaded / total
                                    if pct - last_reported >= 0.05 or pct >= 1.0:
                                        progress_callback(pct)
                                        last_reported = pct

                        progress_callback(1.0)
                        return  # Success

                except (httpx.HTTPError, ConnectionError, OSError) as e:
                    last_error = e
                    error_msg = str(e)
                    logger.debug("Download attempt %d failed: %s", attempt + 1, error_msg)
                    if "SSL" in error_msg or "UNEXPECTED_EOF" in error_msg:
                        if attempt < self._max_retries - 1:
                            time.sleep(3 * (attempt + 1))
                            continue
                    elif attempt < self._max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue

        raise RuntimeError(
            f"下载失败：{last_error}"
        )
