"""Batch download worker for resolving multiple URLs in background."""

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient, BilibiliAPIError
from bilibili_downloader.core.batch import BatchResolver, BatchResolveError
from bilibili_downloader.core.models import DownloadItem

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
        self._quality = quality
        self._codec = codec
        self._download_danmaku = download_danmaku
        self._download_subtitle = download_subtitle
        self.setAutoDelete(True)

    def run(self):
        resolver = BatchResolver(self._api_client)
        for url in self._urls:
            try:
                info = resolver.resolve_one(url)
                item = DownloadItem(
                    video_info=info,
                    selected_quality=self._quality,
                    selected_video_codec=self._codec,
                    download_danmaku=self._download_danmaku,
                    download_subtitle=self._download_subtitle,
                )
                self._worker.item_ready.emit(item)
            except (BatchResolveError, BilibiliAPIError, RuntimeError) as e:
                logger.warning("Batch resolve failed for %s: %s", url, e)
                self._worker.error.emit(f"无法加入队列 {url}: {e}")

        self._worker.finished.emit()
