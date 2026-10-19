"""Collection failures must reach the import preview without losing valid items."""

from types import SimpleNamespace

import pytest

from bilibili_downloader.core.models import ContentCollection, VideoInfo
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.threads.batch_worker import (
    ImportIssue,
    ImportReport,
    SourceResolveRunner,
    SourceResolveWorker,
)


@pytest.mark.parametrize("has_valid_video", [True, False])
def test_preview_keeps_collection_errors_and_valid_items(
    qtbot, monkeypatch, has_valid_video
):
    source = "https://space.bilibili.com/123/favlist?fid=456"
    valid = VideoInfo(bvid="BV1GJ411x7h7", title="Available")
    collection = ContentCollection(
        items=[valid] if has_valid_video else [],
        errors=["BV1xx411x7h8：视频不存在、已失效或暂时不可用。"],
    )
    closed = []
    client = SimpleNamespace(auth_cookies={}, close=lambda: closed.append(True))
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.BilibiliAPIClient",
        lambda **kwargs: client,
    )
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.ContentSourceResolver.resolve",
        lambda self, source: collection,
    )
    panel = BatchDialog(embedded=True)
    qtbot.addWidget(panel)
    panel._url_text.setPlainText(source)
    worker = SourceResolveWorker()
    worker.finished.connect(panel._on_resolved)

    SourceResolveRunner(worker, client, [source]).run()

    assert closed == [True]
    assert panel.get_video_infos() == collection.items
    assert panel._add_btn.isEnabled() == has_valid_video
    assert len(panel._errors) == 1
    assert "1 个作品解析失败，已跳过" in panel._errors[0]
    assert collection.errors[0] in panel._errors[0]
    detail_action = panel._issue_btn if has_valid_video else panel._notice.action
    assert not detail_action.isHidden()


def test_worker_continues_with_later_sources_after_partial_collection(
    monkeypatch, qapp
):
    source = "https://space.bilibili.com/123/favlist?fid=456"
    first = VideoInfo(bvid="BV1GJ411x7h7")
    last = VideoInfo(bvid="BV1Q541167Qg")
    collections = {
        source: ContentCollection(items=[first], errors=["Unavailable"]),
        last.bvid: ContentCollection(items=[first, last]),
    }
    client = SimpleNamespace(auth_cookies={}, close=lambda: None)
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.BilibiliAPIClient",
        lambda **kwargs: client,
    )
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.ContentSourceResolver.resolve",
        lambda self, source: collections[source],
    )
    worker = SourceResolveWorker()
    results = []
    worker.finished.connect(lambda items, errors: results.append((items, errors)))

    SourceResolveRunner(worker, client, [source, last.bvid]).run()

    items, errors = results[0]
    assert items == [first, last]
    assert len(errors) == 1
    assert "Unavailable" in errors[0]


def test_cancel_keeps_streamed_items_and_structured_failures(qapp, monkeypatch):
    from bilibili_downloader.api.client import BilibiliAPIClient as RealClient
    from bilibili_downloader.core.models import ContentFailure
    from bilibili_downloader.core.resolve_control import ResolveCancelled

    worker = SourceResolveWorker()
    client = SimpleNamespace(auth_cookies={})
    actual = RealClient.__new__(RealClient)
    closed = []
    actual.close = lambda: closed.append(True)

    def factory(**kwargs):
        actual._resolve_control = kwargs["resolve_control"]
        return actual

    def resolve(self, source):
        control = self._client._resolve_control
        control.checkpoint("读取收藏夹第 1 页", 20, 40)
        control.item_ready(
            VideoInfo(bvid="BV1GJ411x7h7", collection_title="演示收藏夹")
        )
        control.failure_ready(
            ContentFailure(
                url="https://www.bilibili.com/video/BV1xx411x7h8", error="失效"
            )
        )
        worker.cancel.set()
        control.checkpoint("解析作品", 1, 20)
        raise AssertionError("cancel must stop the next request")

    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.BilibiliAPIClient", factory
    )
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.ContentSourceResolver.resolve",
        resolve,
    )
    reports, progress = [], []
    worker.completed.connect(reports.append)
    worker.progress.connect(progress.append)
    SourceResolveRunner(
        worker, client, ["https://space.bilibili.com/123/favlist?fid=456"]
    ).run()
    assert reports[0].cancelled
    assert len(reports[0].items) == 1
    assert reports[0].items[0].collection_title == "演示收藏夹"
    assert reports[0].issues[0].kind == "item"
    assert progress[-1]["stage"] == "读取收藏夹第 1 页"
    assert closed == [True]
    assert issubclass(ResolveCancelled, Exception)


def test_report_distinguishes_partial_collection_from_failed_source(qapp, monkeypatch):
    from bilibili_downloader.core.models import ContentFailure

    failed_url = "https://www.bilibili.com/video/BV1xx411x7h8"
    failure = ContentFailure(url=failed_url, title="失效视频", error="内容不存在")
    client = SimpleNamespace(auth_cookies={}, close=lambda: None)
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.BilibiliAPIClient",
        lambda **kwargs: client,
    )

    def resolve(self, source):
        if source == "av42":
            raise OSError("offline")
        return ContentCollection(
            items=[VideoInfo(bvid="BV1GJ411x7h7")],
            failures=[failure],
            errors=[failure.error],
        )

    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.ContentSourceResolver.resolve",
        resolve,
    )
    worker = SourceResolveWorker()
    reports = []
    worker.completed.connect(reports.append)
    SourceResolveRunner(worker, client, ["favorites", "av42"]).run()
    report = reports[0]
    assert len(report.items) == 1
    assert [issue.kind for issue in report.issues] == ["item", "source"]
    assert report.issues[0].url == failed_url


def test_retry_merges_results_preserves_unchecked_items_and_stale_guard(
    qtbot, monkeypatch
):
    from PySide6.QtCore import QThreadPool

    monkeypatch.setattr(
        QThreadPool, "globalInstance", lambda: SimpleNamespace(start=lambda _: None)
    )
    panel = BatchDialog(api_client=SimpleNamespace(auth_cookies={}), embedded=True)
    qtbot.addWidget(panel)
    source = "https://space.bilibili.com/123/favlist?fid=456"
    retry = "https://www.bilibili.com/video/BV1xx411x7h8"
    panel._url_text.setPlainText(source)
    first = VideoInfo(bvid="BV1GJ411x7h7")
    panel._on_report(
        ImportReport([first], [ImportIssue(source, "offline", retry, "失败项", "item")])
    )
    panel._selectors[0].setChecked(False)
    assert "跳过 1 项" in panel._report_summary()
    panel._retry_failed()
    assert panel._busy
    panel._on_report(ImportReport([VideoInfo(bvid="BV1xx411x7h8", source_url=retry)]))
    assert [info.bvid for info in panel.get_video_infos()] == ["BV1xx411x7h8"]
    assert len(panel._resolved_items) == 2 and not panel._report.issues
    panel._url_text.setPlainText("av42")
    panel._retry_failed()
    assert not panel._busy
    assert not panel._add_btn.isEnabled()


def test_cancelled_retry_keeps_unresolved_failures(qtbot, monkeypatch):
    from PySide6.QtCore import QThreadPool

    monkeypatch.setattr(
        QThreadPool, "globalInstance", lambda: SimpleNamespace(start=lambda _: None)
    )
    panel = BatchDialog(api_client=SimpleNamespace(auth_cookies={}), embedded=True)
    qtbot.addWidget(panel)
    url = "BV1xx411x7h8"
    panel._url_text.setPlainText(url)
    panel._on_report(ImportReport([], [ImportIssue(url, "offline", url, kind="item")]))
    panel._retry_failed()
    panel.cancel_resolution()
    assert panel._resolve_worker.cancel.is_set()
    panel._on_report(ImportReport(cancelled=True))
    assert len(panel._report.issues) == 1
    assert panel._report.cancelled


def test_failure_details_copy_links_and_retry_only_failures(qtbot, monkeypatch, qapp):
    from PySide6.QtWidgets import QDialog, QPushButton

    panel = BatchDialog(api_client=SimpleNamespace(), embedded=True)
    qtbot.addWidget(panel)
    source = "BV1GJ411x7h7"
    panel._url_text.setPlainText(source)
    panel._on_report(ImportReport([], [ImportIssue(source, "offline", source)]))
    retried = []
    monkeypatch.setattr(panel, "_retry_failed", lambda: retried.append(True))

    def inspect(dialog):
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        buttons["复制失败链接"].click()
        assert qapp.clipboard().text() == source
        assert buttons["重试失败项"].isEnabled()
        buttons["重试失败项"].click()
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", inspect)
    panel._show_errors()
    assert retried == [True]


def test_identical_deleted_entries_are_counted_individually(qapp, monkeypatch):
    from bilibili_downloader.api.client import BilibiliAPIClient as RealClient

    actual = RealClient.__new__(RealClient)
    actual.close = lambda: None

    def factory(**kwargs):
        actual._resolve_control = kwargs["resolve_control"]
        return actual

    def resolve(self, source):
        return self._client._collection_from_entries(
            "Favorites", "favorite", source, [{"title": "已失效"}, {"title": "已失效"}]
        )

    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.BilibiliAPIClient", factory
    )
    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.batch_worker.ContentSourceResolver.resolve",
        resolve,
    )
    worker, reports = SourceResolveWorker(), []
    worker.completed.connect(reports.append)
    SourceResolveRunner(worker, SimpleNamespace(auth_cookies={}), ["favorites"]).run()
    assert len(reports[0].issues) == 2
    assert all(issue.kind == "item" for issue in reports[0].issues)


def test_cancelled_parent_retry_does_not_clear_unresolved_failures(qtbot, monkeypatch):
    from PySide6.QtCore import QThreadPool

    monkeypatch.setattr(
        QThreadPool, "globalInstance", lambda: SimpleNamespace(start=lambda _: None)
    )
    panel = BatchDialog(api_client=SimpleNamespace(auth_cookies={}), embedded=True)
    qtbot.addWidget(panel)
    parent = "https://space.bilibili.com/123/favlist?fid=456"
    issue = ImportIssue(parent, "missing id", parent, "失效条目", "item")
    panel._url_text.setPlainText(parent)
    panel._on_report(ImportReport([], [issue, issue]))
    panel._retry_failed()
    panel._on_report(
        ImportReport(
            [VideoInfo(bvid="BV1GJ411x7h7", source_url=parent)], [issue], cancelled=True
        )
    )
    assert len(panel._report.items) == 1
    assert len(panel._report.issues) == 2


def test_retry_keeps_metadata_of_previously_resolved_collection_item(
    qtbot, monkeypatch
):
    from PySide6.QtCore import QThreadPool

    monkeypatch.setattr(
        QThreadPool, "globalInstance", lambda: SimpleNamespace(start=lambda _: None)
    )
    panel = BatchDialog(api_client=SimpleNamespace(auth_cookies={}), embedded=True)
    qtbot.addWidget(panel)
    bvid = "BV1GJ411x7h7"
    panel._url_text.setPlainText(bvid)
    original = VideoInfo(bvid=bvid, collection_title="保留原合集路径")
    panel._on_report(
        ImportReport([original], [ImportIssue(bvid, "另一来源失败", bvid, kind="item")])
    )
    panel._retry_failed()
    panel._on_report(ImportReport([VideoInfo(bvid=bvid)]))
    assert panel._resolved_items[0].collection_title == "保留原合集路径"
