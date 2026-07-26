"""Batch download worker for resolving multiple URLs in background."""

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.batch import ContentSourceResolver
from bilibili_downloader.core.errors import redact_sensitive_text, user_error_message

logger = logging.getLogger(__name__)


class SourceResolveWorker(QObject):
    """Signal owner for resolving heterogeneous import sources."""

    finished = Signal(list, list)


class SourceResolveRunner(QRunnable):
    """Resolve video, collection and favorite inputs for import preview."""

    def __init__(
        self,
        worker: SourceResolveWorker,
        api_client: BilibiliAPIClient,
        sources: list[str],
    ):
        super().__init__()
        self._worker = worker
        self._api_client = api_client
        self._sources = sources
        self.setAutoDelete(True)

    def run(self):
        client = BilibiliAPIClient(sessdata=self._api_client.sessdata)
        resolver = ContentSourceResolver(client)
        items = []
        errors = []
        seen = set()
        try:
            for source in self._sources:
                try:
                    collection = resolver.resolve(source)
                    for info in collection.items:
                        identity = info.bvid.lower()
                        if identity not in seen:
                            seen.add(identity)
                            items.append(info)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Content source resolve failed for %s: %s",
                        redact_sensitive_text(source),
                        redact_sensitive_text(exc),
                    )
                    errors.append(
                        f"{redact_sensitive_text(source)}：{user_error_message(exc)}"
                    )
        finally:
            client.close()
        self._worker.finished.emit(items, errors)
