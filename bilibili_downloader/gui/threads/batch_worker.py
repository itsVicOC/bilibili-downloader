"""Batch download worker for resolving multiple URLs in background."""

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient, BilibiliAPIError
from bilibili_downloader.core.models import DownloadItem
from bilibili_downloader.utils.validators import extract_bvid

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
    """Resolves multiple BV URLs into DownloadItems in a background thread."""

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
        for url in self._urls:
            bvid = extract_bvid(url)
            if not bvid:
                continue

            try:
                info = self._api_client.get_video_info(bvid)
                item = DownloadItem(
                    video_info=info,
                    selected_quality=self._quality,
                    selected_video_codec=self._codec,
                    download_danmaku=self._download_danmaku,
                    download_subtitle=self._download_subtitle,
                )
                self._worker.item_ready.emit(item)
            except (BilibiliAPIError, RuntimeError) as e:
                logger.warning("Batch resolve failed for %s: %s", bvid, e)
                self._worker.error.emit(f"无法加入队列 {bvid}: {e}")

        self._worker.finished.emit()
