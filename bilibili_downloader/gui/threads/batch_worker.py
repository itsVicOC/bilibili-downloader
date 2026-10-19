"""Batch download worker for resolving multiple URLs in background."""

import logging
from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.batch import ContentSourceResolver
from bilibili_downloader.core.errors import redact_sensitive_text, user_error_message
from bilibili_downloader.core.resolve_control import ResolveCancelled, ResolveControl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportIssue:
    source: str
    message: str
    url: str = ""
    title: str = ""
    kind: str = "source"


@dataclass
class ImportReport:
    items: list = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    duplicates: int = 0
    cancelled: bool = False
    completed_sources: list[str] = field(default_factory=list)


class SourceResolveWorker(QObject):
    """Signal owner for resolving heterogeneous import sources."""

    finished = Signal(list, list)
    completed = Signal(object)
    progress = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cancel = Event()


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
        report = ImportReport()
        errors = []
        seen = set()
        streamed_failures = set()
        streamed = set()
        source, source_index = "", 0

        def emit(signal, *args):
            try:
                signal.emit(*args)
            except RuntimeError:
                self._worker.cancel.set()

        def progress(stage, completed, total):
            emit(
                self._worker.progress,
                {
                    "source": redact_sensitive_text(source),
                    "source_index": source_index,
                    "sources": len(self._sources),
                    "stage": stage,
                    "completed": completed,
                    "total": total,
                    "items": len(report.items),
                },
            )

        def add_item(info):
            identity = info.content_identity.lower()
            if identity not in seen:
                seen.add(identity)
                report.items.append(info)

        def stream_item(info):
            streamed.add(id(info))
            if info.content_identity.lower() in seen:
                report.duplicates += 1
            add_item(info)

        def add_failure(failure):
            # Distinct deleted entries can have identical titles and links.
            # Deduplicate only the callback/final-report copies of one object.
            if id(failure) not in streamed_failures:
                streamed_failures.add(id(failure))
                report.issues.append(
                    ImportIssue(
                        source,
                        failure.error,
                        failure.url or source,
                        failure.title,
                        "item",
                    )
                )

        control = ResolveControl(
            self._worker.cancel, progress, stream_item, add_failure
        )
        client = None
        try:
            client = BilibiliAPIClient(
                auth_cookies=self._api_client.auth_cookies,
                resolve_control=control,
                request_timeout=10.0,
            )
            resolver = ContentSourceResolver(client)
            for source_index, source in enumerate(self._sources, 1):
                streamed.clear()
                streamed_failures.clear()
                control.checkpoint()
                try:
                    collection = resolver.resolve(source)
                    if collection.errors:
                        errors.append(
                            f"{redact_sensitive_text(source)}："
                            f"{len(collection.errors)} 个作品解析失败，已跳过。\n"
                            + "\n".join(collection.errors)
                        )
                    if collection.failures:
                        for failure in collection.failures:
                            add_failure(failure)
                    elif collection.errors:
                        for error in collection.errors:
                            report.issues.append(
                                ImportIssue(source, error, source, kind="item")
                            )
                    for info in collection.items:
                        identity = info.content_identity.lower()
                        # Streaming collection callbacks may already have added it.
                        if identity in seen and id(info) not in streamed:
                            report.duplicates += 1
                        add_item(info)
                    report.completed_sources.append(source)
                except ResolveCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Content source resolve failed for %s: %s",
                        redact_sensitive_text(source),
                        redact_sensitive_text(exc),
                    )
                    errors.append(
                        f"{redact_sensitive_text(source)}：{user_error_message(exc)}"
                    )
                    report.issues.append(
                        ImportIssue(source, user_error_message(exc), source)
                    )
                    report.completed_sources.append(source)
                control.checkpoint("来源读取完成", source_index, len(self._sources))
        except ResolveCancelled:
            report.cancelled = True
        except Exception as exc:  # noqa: BLE001
            message = user_error_message(exc)
            errors.append(message)
            report.issues.append(ImportIssue(source, message, source))
        finally:
            if client:
                client.close()
        emit(self._worker.completed, report)
        emit(self._worker.finished, report.items, errors)
