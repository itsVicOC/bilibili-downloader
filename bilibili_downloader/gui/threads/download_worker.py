"""Download worker for thread-pooled background downloading."""

import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.danmaku import DanmakuDownloader
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.models import DownloadItem
from bilibili_downloader.core.subtitle import SubtitleDownloader

logger = logging.getLogger(__name__)


class DownloadWorker(QObject):
    """Holds download parameters and signals. Used with DownloadRunner(QRunnable).

    Signals:
        progress: (download_id, progress_float, status_text)
        finished: (download_id, output_path)
        error: (download_id, error_message)
    """

    progress = Signal(int, float, str)
    finished = Signal(int, str)
    error = Signal(int, str)

    def __init__(
        self,
        api_client: BilibiliAPIClient,
        item: DownloadItem,
        output_dir: str,
        download_danmaku: bool = False,
        download_subtitle: bool = False,
        download_id: int = 0,
        ffmpeg_path: Optional[str] = None,
    ):
        super().__init__()
        self._api_client = api_client
        self._item = item
        self._output_dir = output_dir
        self._download_danmaku = download_danmaku
        self._download_subtitle = download_subtitle
        self._download_id = download_id
        self._ffmpeg_path = ffmpeg_path
        self._cancelled = False
        self._downloader: Optional[StreamDownloader] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self):
        """Execute the download. Called by DownloadRunner.run()."""
        self._running = True
        try:
            os.makedirs(self._output_dir, exist_ok=True)

            self._downloader = StreamDownloader(
                self._api_client, self._output_dir, ffmpeg_path=self._ffmpeg_path,
            )

            def progress_cb(pct: float, text: str):
                if self._cancelled:
                    self._downloader.cancel()
                    raise RuntimeError("Cancelled")
                self.progress.emit(self._download_id, pct, text)

            output_path = self._downloader.download(self._item, progress_cb)

            if self._download_danmaku:
                try:
                    self.progress.emit(self._download_id, 0.9, "正在下载弹幕...")
                    danmaku_path = Path(output_path).with_suffix(".ass")
                    DanmakuDownloader.download_and_convert(
                        self._item.video_info.cid, danmaku_path,
                    )
                except Exception as e:
                    logger.warning(
                        "Danmaku download failed for %s: %s",
                        self._item.video_info.title, e,
                    )

            if self._download_subtitle and self._item.video_info.subtitle_list:
                try:
                    self.progress.emit(self._download_id, 0.95, "正在下载字幕...")
                    subtitle_info = self._item.video_info.subtitle_list[0]
                    subtitle_path = Path(output_path).with_suffix(".srt")
                    SubtitleDownloader.download_and_convert(
                        subtitle_info.url, subtitle_path,
                    )
                except Exception as e:
                    logger.warning(
                        "Subtitle download failed for %s: %s",
                        self._item.video_info.title, e,
                    )

            self.finished.emit(self._download_id, output_path)

        except Exception as e:
            logger.error("Download error for %s: %s", self._item.video_info.title, e)
            self.error.emit(self._download_id, str(e))
        finally:
            self._running = False

    def cancel(self):
        """Cancel the download."""
        self._cancelled = True
        if self._downloader:
            self._downloader.cancel()


class DownloadRunner(QRunnable):
    """Runs DownloadWorker in a thread pool."""

    def __init__(self, worker: DownloadWorker):
        super().__init__()
        self._worker = worker
        self.setAutoDelete(True)

    def run(self):
        self._worker.run()
