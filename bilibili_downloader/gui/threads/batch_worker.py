"""Batch download worker for resolving multiple URLs in background."""

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.batch import BatchResolver
from bilibili_downloader.core.models import DownloadItem, VideoQuality

logger = logging.getLogger(__name__)


class BatchWorker(QObject):
    """Signals for batch download resolution.

    Signals:
        item_ready: (DownloadItem) — a single video resolved and ready to download
        error: (str) — error message for a single failed URL
        finished: () — all URLs processed
    """

    item_ready = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class BatchRunner(QRunnable):
    """Resolves multiple inputs into DownloadItems in a background thread."""

    def __init__(
        self,
        worker: BatchWorker,
        api_client: BilibiliAPIClient,
        urls: list[str],
        quality,
        codec: int,
        download_danmaku: bool,
        download_subtitle: bool,
    ):
        super().__init__()
        self._worker = worker
        self._api_client = api_client
        self._urls = urls
        self._quality = quality or VideoQuality.Q1080P
        self._codec = codec or 12
        self._download_danmaku = download_danmaku
        self._download_subtitle = download_subtitle
        self.setAutoDelete(True)

    def run(self):
        resolver = BatchResolver(self._api_client)
        try:
            for url in self._urls:
                if self._worker.cancelled:
                    break
                try:
                    info = resolver.resolve_one(url)
                    page_infos = (
                        [info.for_page(page) for page in info.pages]
                        if info.is_multi_part else [info]
                    )
                    for page_info in page_infos:
                        item = DownloadItem(
                            video_info=page_info,
                            selected_quality=self._quality,
                            selected_video_codec=self._codec,
                            download_danmaku=self._download_danmaku,
                            download_subtitle=self._download_subtitle,
                        )
                        self._worker.item_ready.emit(item)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Batch resolve failed for %s: %s", url, e)
                    self._worker.error.emit(f"无法加入队列 {url}: {e}")
        finally:
            self._worker.finished.emit()
