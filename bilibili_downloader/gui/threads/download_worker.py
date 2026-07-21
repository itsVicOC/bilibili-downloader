"""Download worker for thread-pooled background downloading."""

import logging
import os
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.models import DownloadItem

logger = logging.getLogger(__name__)


class DownloadWorker(QObject):
    """Holds download parameters and signals. Used with DownloadRunner(QRunnable).

    Signals:
        progress: (download_id, progress_float, status_text)
        finished: (download_id, output_path)
        error: (download_id, error_message)
    """

    progress = Signal(int, float, str)
    finished = Signal(int, object)
    error = Signal(int, str)
    cancelled = Signal(int)

    def __init__(
        self,
        api_client: BilibiliAPIClient,
        item: DownloadItem,
        output_dir: str,
        download_id: int = 0,
        ffmpeg_path: Optional[str] = None,
    ):
        super().__init__()
        self._api_client = api_client
        self._item = item
        self._output_dir = output_dir
        self._download_id = download_id
        self._ffmpeg_path = ffmpeg_path
        self._cancelled = False
        self._service: Optional[DownloadService] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self):
        """Execute the download. Called by DownloadRunner.run()."""
        self._running = True
        try:
            os.makedirs(self._output_dir, exist_ok=True)

            self._service = DownloadService(
                self._api_client, self._output_dir, ffmpeg_path=self._ffmpeg_path,
            )

            def progress_cb(pct: float, text: str):
                if self._cancelled:
                    self._service.cancel()
                    raise RuntimeError("Cancelled")
                self.progress.emit(self._download_id, pct, text)

            outcome = self._service.download(self._item, progress_cb)

            if self._cancelled:
                raise RuntimeError("Cancelled")
            self.finished.emit(self._download_id, outcome)

        except Exception as e:
            if self._cancelled or "cancel" in str(e).lower():
                logger.info("Download cancelled for %s", self._item.video_info.title)
                self.cancelled.emit(self._download_id)
            else:
                logger.error("Download error for %s: %s", self._item.video_info.title, e)
                self.error.emit(self._download_id, str(e))
        finally:
            self._running = False

    def cancel(self):
        """Cancel the download."""
        self._cancelled = True
        if self._service:
            self._service.cancel()


class DownloadRunner(QRunnable):
    """Runs DownloadWorker in a thread pool."""

    def __init__(self, worker: DownloadWorker):
        super().__init__()
        self._worker = worker
        self.setAutoDelete(True)

    def run(self):
        self._worker.run()
