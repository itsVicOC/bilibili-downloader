"""Download worker for thread-pooled background downloading."""

import logging
import os
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.errors import redact_sensitive_text, user_error_message
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
    paused = Signal(int)
    metrics = Signal(int, float, object)

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
        self._pause_requested = False
        self._service: Optional[DownloadService] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self):
        """Execute the download. Called by DownloadRunner.run()."""
        self._running = True
        try:
            if self._pause_requested:
                self.paused.emit(self._download_id)
                return
            os.makedirs(self._output_dir, exist_ok=True)

            self._service = DownloadService(
                self._api_client, self._output_dir, ffmpeg_path=self._ffmpeg_path,
            )

            def progress_cb(pct: float, text: str):
                if self._cancelled:
                    self._service.cancel()
                    raise RuntimeError("Cancelled")
                metrics = self._service.transfer_metrics
                if metrics.speed_bytes_per_second > 0 and "下载" in text:
                    text = _progress_text(
                        text,
                        metrics.speed_bytes_per_second,
                        metrics.eta_seconds,
                    )
                self.progress.emit(self._download_id, pct, text)
                self.metrics.emit(
                    self._download_id,
                    metrics.speed_bytes_per_second,
                    metrics.eta_seconds,
                )

            outcome = self._service.download(self._item, progress_cb)

            if self._cancelled:
                raise RuntimeError("Cancelled")
            self.finished.emit(self._download_id, outcome)

        except Exception as e:
            if self._pause_requested:
                logger.info("Download paused for %s", self._item.video_info.title)
                self.paused.emit(self._download_id)
            elif self._cancelled or "cancel" in str(e).lower():
                logger.info("Download cancelled for %s", self._item.video_info.title)
                self.cancelled.emit(self._download_id)
            else:
                logger.error(
                    "Download error for %s: %s",
                    self._item.video_info.title,
                    redact_sensitive_text(e),
                )
                self.error.emit(self._download_id, user_error_message(e))
        finally:
            self._running = False

    def cancel(self):
        """Cancel the download."""
        self._cancelled = True
        if self._service:
            self._service.cancel()

    def pause(self):
        """Pause by cancelling the current transfer while retaining resume parts."""
        self._pause_requested = True
        self.cancel()


class DownloadRunner(QRunnable):
    """Runs DownloadWorker in a thread pool."""

    def __init__(self, worker: DownloadWorker):
        super().__init__()
        self._worker = worker
        self.setAutoDelete(True)

    def run(self):
        self._worker.run()


def _progress_text(text: str, speed: float, eta: int | None) -> str:
    if speed >= 1024 * 1024:
        speed_text = f"{speed / 1024 / 1024:.1f} MB/s"
    else:
        speed_text = f"{speed / 1024:.0f} KB/s"
    if eta is None:
        return f"{text.rstrip('.')} · {speed_text}"
    minutes, seconds = divmod(max(0, eta), 60)
    eta_text = f"{minutes:d}:{seconds:02d}"
    return f"{text.rstrip('.')} · {speed_text} · 剩余 {eta_text}"
