"""Batch import source cards through the workspace's existing queue flow."""

import io
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QDialog, QPushButton

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.batch_discovery import (
    BatchCover,
    BatchSource,
    BatchSourcePage,
)
from bilibili_downloader.core.models import ContentCollection, OutputMode, VideoInfo
from bilibili_downloader.gui.threads.batch_worker import ImportIssue, ImportReport
from bilibili_downloader.gui.widgets import batch_sources, discovery_cards
from bilibili_downloader.gui.widgets.discovery_cards import ThumbnailLoader
from tests.test_workspaces import contained
from tests.test_workspaces import workspace as workspace


class QueuedPool:
    def __init__(self):
        self.jobs = []

    def start(self, job):
        self.jobs.append(job)


def test_favorite_cards_append_draft_and_use_batch_preview_and_queue(workspace, qtbot, monkeypatch):
    panel = workspace._batch_page
    sources = workspace._batch_sources
    first = BatchSource("https://space.bilibili.com/42/favlist?fid=10042", "默认收藏夹", count=1)
    second = BatchSource("https://space.bilibili.com/42/favlist?fid=20042", "私密收藏夹", count=1)
    requests = []

    def load(cookies, mid, kind, offset, _cancelled):
        requests.append((cookies, mid, kind, offset))
        return BatchSourcePage((first, second))

    def favorite(client, media_id, source_url):
        assert client.auth_cookies == {"SESSDATA": "fixture"}
        info = VideoInfo(bvid=f"BV1GJ4{media_id}", cid=media_id, title=f"作品 {media_id}")
        return ContentCollection(source_url=source_url, items=[info])

    monkeypatch.setattr(batch_sources, "load_batch_sources", load)
    monkeypatch.setattr(BilibiliAPIClient, "get_favorite_collection", favorite)
    monkeypatch.setattr(workspace, "_confirm_copyright_acknowledgement", lambda: True)
    monkeypatch.setattr(workspace, "_start_download", lambda *_args: None)
    workspace.resize(900, 640)
    workspace.show()
    assert not requests
    workspace._download_tabs.setCurrentIndex(1)
    assert sources.tabs.tabText(0) == "粘贴链接" and panel._url_text.isVisible()
    assert not sources.login.isVisible()
    sources.tabs.setCurrentIndex(1)
    assert sources.login.isVisible()
    assert sources.tabs.tabText(1) == "我的收藏夹"
    assert sources.tabs.count() == 3
    workspace._api_client.auth_cookies = {"SESSDATA": "fixture"}
    workspace._on_login_status_result(workspace._login_status_request_id, {"isLogin": True, "mid": 42})
    qtbot.waitUntil(lambda: len(sources.grid._widgets) == 2)
    assert requests == [({"SESSDATA": "fixture"}, 42, "favorites", "")]

    panel._url_text.setPlainText("稍后补的链接\n")
    button = sources.grid._widgets[0].action_button
    button.setFocus(Qt.TabFocusReason)
    qtbot.keyClick(button, Qt.Key_Return)
    assert button.text() == "已加入"
    button.click()
    sources.grid._widgets[1].action_button.click()
    assert panel._url_text.toPlainText().splitlines() == ["稍后补的链接", first.url, second.url]
    assert panel._preview.rowCount() == 0
    assert contained(panel._action_bar, workspace)
    assert panel._add_btn.text() == "预览 2 个来源"

    panel._add_btn.click()
    qtbot.waitUntil(lambda: panel._preview.rowCount() == 2)
    assert panel._collapse_btn.isChecked() and not sources.isVisible()
    panel._selectors[1].setChecked(False)
    panel._add_btn.click()
    assert len(workspace._task_repository.list_tasks()) == 1
    panel._collapse_btn.click()
    assert sources.isVisible()
    assert panel._url_text.toPlainText().splitlines()[-2:] == [first.url, second.url]


def test_following_tab_retries_same_page_and_deduplicates_newest_collection(workspace, qtbot, monkeypatch):
    requests = []
    url = "https://space.bilibili.com/42/lists/7?type=season"
    latest = BatchSource(url, "合集", "作者", updated_at=10)
    earlier = BatchSource(url, "同一合集", "作者", updated_at=8)
    other = BatchSource("https://space.bilibili.com/42/lists/9?type=season", "另一合集", "作者", updated_at=6)

    def load(_cookies, _mid, kind, offset, _cancelled):
        requests.append((kind, offset))
        if kind == "favorites":
            return BatchSourcePage()
        if not offset:
            return BatchSourcePage((latest,), next_offset="more")
        if requests.count((kind, offset)) == 1:
            return BatchSourcePage(error="暂时无法读取来源，请重试。")
        return BatchSourcePage((earlier, other), next_offset="more")

    monkeypatch.setattr(batch_sources, "load_batch_sources", load)
    panel = workspace._batch_sources
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    workspace.show()
    workspace._download_tabs.setCurrentIndex(1)
    panel.tabs.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel.status.text() == "暂无收藏夹。")
    assert panel.tabs.tabText(2) == "找合集"
    panel.tabs.setCurrentIndex(2)
    assert panel.collection_tabs.tabText(0) == "最近动态"
    qtbot.waitUntil(lambda: len(panel.grid._widgets) == 1 and panel.grid.more.isVisible())
    panel.grid.more.click()
    qtbot.waitUntil(lambda: panel.refresh.text() == "重试")
    assert [card.title for card in panel.grid._cards] == ["合集"]
    panel.refresh.click()
    qtbot.waitUntil(lambda: len(panel.grid._cards) == 2)
    assert [card.title for card in panel.grid._cards] == ["合集", "另一合集"]
    assert "动态分页已中断" in panel.status.text()
    assert not panel.grid.more.isVisible()
    assert requests == [("favorites", ""), ("collections", ""), ("collections", "more"), ("collections", "more")]
    panel.grid._widgets[0].action_button.click()
    assert workspace._batch_page._url_text.toPlainText() == url


def test_account_change_discards_a_result_already_queued_to_gui(qtbot, monkeypatch):
    def load(cookies, mid, _kind, _offset, _cancelled):
        favorite = BatchSource(f"https://space.bilibili.com/{mid}/favlist?fid=42", cookies["SESSDATA"])
        return BatchSourcePage((favorite,))

    monkeypatch.setattr(batch_sources, "load_batch_sources", load)
    pool = QueuedPool()
    panel = batch_sources.BatchSourcesWidget(pool, ThumbnailLoader())
    qtbot.addWidget(panel)
    panel.set_loading_enabled(True)
    panel.tabs.setCurrentIndex(1)
    panel.show()
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "旧私密夹"}), mid=42)
    pool.jobs[0].run()
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "新私密夹"}), mid=43)
    assert pool.jobs[0].request.is_set()
    pool.jobs[1].run()
    qtbot.waitUntil(lambda: bool(panel.grid._cards))
    assert [card.title for card in panel.grid._cards] == ["新私密夹"]
    panel.set_account(None)
    assert not panel.grid._cards and panel.login.isVisible()


def test_following_only_loads_selected_creator_and_back_restores_position(workspace, qtbot, monkeypatch):
    authors = tuple(BatchSource(f"https://space.bilibili.com/{owner}", f"作者 {owner}", owner_mid=owner)
                    for owner in range(100, 124))
    season = BatchSource("https://space.bilibili.com/101/lists/7?type=season", "合集名", "作者 101")
    requests = []

    def load(_cookies, _mid, kind, offset, _cancelled, *, creator=None):
        requests.append((kind, offset, creator.owner_mid if creator else None))
        if kind == "following":
            return BatchSourcePage(authors)
        if kind != "space" or creator.owner_mid == 100:
            return BatchSourcePage()
        return BatchSourcePage((season,), next_offset="2" if not offset else "3", page_key=(season.url,))

    monkeypatch.setattr(batch_sources, "load_batch_sources", load)
    panel = workspace._batch_sources
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    workspace.resize(900, 640)
    workspace.show()
    panel.tabs.setCurrentIndex(2)
    panel.collection_tabs.setCurrentIndex(1)
    workspace._download_tabs.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel.grid.materialized_count > 0)
    assert requests == [("following", "", None)]
    assert panel.grid.materialized_count < len(authors)
    panel.grid.more.click()
    panel.grid.more.click()
    scroll_bar = panel._scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: scroll_bar.maximum() >= 140)
    scroll_bar.setValue(min(140, scroll_bar.maximum()))
    scrolled, rendered = scroll_bar.value(), panel.grid.materialized_count
    assert scrolled > 0

    panel.grid._widgets[0].action_button.click()
    qtbot.waitUntil(lambda: panel.status.text() == "该 UP 主暂无可查看的合集。")
    assert requests[-1] == ("space", "", 100)
    assert workspace._batch_page._url_text.toPlainText() == ""
    panel.back.click()
    qtbot.waitUntil(lambda: scroll_bar.value() == scrolled)
    assert panel.grid.materialized_count == rendered

    panel.grid._widgets[1].action_button.click()
    qtbot.waitUntil(lambda: panel.grid.materialized_count == 1 and panel.grid.more.isVisible())
    assert requests[-1] == ("space", "", 101)
    panel.grid.more.click()
    qtbot.waitUntil(lambda: "列表分页已中断" in panel.status.text())
    assert requests[-1] == ("space", "2", 101)
    assert not panel.grid.more.isVisible()
    panel.grid._widgets[0].action_button.click()
    assert workspace._batch_page._url_text.toPlainText() == season.url


def test_author_and_collection_search_visit_unread_pages_and_preserve_partial_results(qtbot, monkeypatch):
    early = BatchSource("https://space.bilibili.com/100", "首屏作者", owner_mid=100)
    target = BatchSource("https://space.bilibili.com/2897", "目标作者", owner_mid=2897)
    season = BatchSource("https://space.bilibili.com/2897/lists/7?type=season", "后页合集", "目标作者")
    requests = []

    def load(_cookies, _mid, kind, offset, _cancelled, *, creator=None):
        requests.append((kind, offset))
        if kind == "space":
            assert creator == target
            return BatchSourcePage((season,)) if offset else BatchSourcePage(next_offset="2", page_key=("other",))
        if not offset:
            return BatchSourcePage((early,), next_offset="2", page_key=(early.url,))
        if requests.count(("following", "2")) == 1:
            return BatchSourcePage(error="暂时无法读取来源，请重试。")
        return BatchSourcePage((target,), next_offset="3", page_key=(target.url,))

    monkeypatch.setattr(batch_sources, "load_batch_sources", load)
    pool = QueuedPool()
    panel = batch_sources.BatchSourcesWidget(pool, ThumbnailLoader())
    qtbot.addWidget(panel)
    panel.tabs.setCurrentIndex(2)
    panel.collection_tabs.setCurrentIndex(1)
    panel.set_loading_enabled(True)
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    panel.resize(650, 400)
    panel.show()
    pool.jobs[0].run()
    qtbot.waitUntil(lambda: len(panel.grid._widgets) == 1)
    panel.search.setText("2897")
    assert len(pool.jobs) == 1 and not panel.grid._cards
    qtbot.keyClick(panel.search, Qt.Key_Return)
    pool.jobs[1].run()
    qtbot.waitUntil(lambda: "搜索未完成" in panel.status.text())
    panel.search_action.click()
    pool.jobs[2].run()
    qtbot.waitUntil(lambda: len(pool.jobs) == 4)
    assert [card.title for card in panel.grid._cards] == [target.title]
    panel.search_action.click()
    assert pool.jobs[3].request.is_set() and "已停止" in panel.status.text()
    pool.jobs[3].run()
    assert ("following", "3") not in requests
    panel.search_action.click()
    pool.jobs[4].run()
    qtbot.waitUntil(lambda: "列表分页已中断" in panel.status.text())
    assert "1 个匹配" in panel.status.text()

    panel.grid._widgets[0].action_button.click()
    qtbot.waitUntil(lambda: len(pool.jobs) == 6)
    pool.jobs[5].run()
    qtbot.waitUntil(lambda: panel._current().pages == 1)
    assert panel.search.text() == ""
    panel.search.setText("后页")
    panel.search_action.click()
    pool.jobs[6].run()
    qtbot.waitUntil(lambda: [card.title for card in panel.grid._cards] == [season.title])
    panel.back.click()
    assert panel.search.text() == "2897" and [card.title for card in panel.grid._cards] == [target.title]
    panel.set_account(None)
    assert panel.search.text() == "" and not panel.grid._cards


def test_quick_preview_keeps_batch_draft_and_both_selections(workspace, qtbot, monkeypatch):
    first = BatchSource("https://space.bilibili.com/42/lists/7?type=season", "批量合集一", "作者")
    second = BatchSource("https://space.bilibili.com/42/lists/9?type=season", "批量合集二", "作者")
    quick = BatchSource("https://space.bilibili.com/42/lists/11?type=season", "单独预览合集", "作者")
    legacy = "https://space.bilibili.com/42/channel/collectiondetail?sid=7&spm_id_from=333"
    calls = []

    def resolve(_client, _mid, season_id, source_url):
        calls.append(season_id)
        return ContentCollection(source_url=source_url, items=[
            VideoInfo(bvid=f"BV1TEST{season_id:03d}{index:02d}", cid=season_id + index, title=f"作品 {season_id}-{index}")
            for index in (1, 2)
        ])

    monkeypatch.setattr(batch_sources, "load_batch_sources", lambda *_: BatchSourcePage((first, second, quick)))
    monkeypatch.setattr(BilibiliAPIClient, "get_season_collection", resolve)
    sources, batch = workspace._batch_sources, workspace._batch_page
    sources.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    workspace.resize(900, 640)
    workspace.show()
    sources.tabs.setCurrentIndex(2)
    workspace._download_tabs.setCurrentIndex(1)
    qtbot.waitUntil(lambda: len(sources.grid._widgets) == 3)
    batch._url_text.setPlainText(legacy)
    assert sources.grid._widgets[0].action_button.text() == "已加入"
    sources.grid._widgets[1].action_button.click()
    assert batch._add_btn.text() == "预览 2 个来源" and contained(batch._add_btn, workspace)
    batch._add_btn.click()
    qtbot.waitUntil(lambda: batch.preview_ready and batch._preview.rowCount() == 4)
    batch._selectors[0].setChecked(False)
    checked = set(batch.selection.state.selected)
    batch._collapse_btn.click()
    qtbot.waitUntil(lambda: sources.isVisible() and len(sources.grid._widgets) == 3)
    sources.search.setText("单独预览")
    qtbot.waitUntil(lambda: len(sources.grid._widgets) == 1)
    sources.grid._widgets[0].secondary_button.click()
    qtbot.waitUntil(lambda: batch.preview_ready and batch._preview.rowCount() == 2)
    assert batch._source_summary._full_text == f"单个来源 · {quick.title}"
    assert batch._url_text.toPlainText().splitlines() == [legacy, second.url]
    batch._selectors[1].setChecked(False)
    quick_checked = set(batch.selection.state.selected)
    batch._collapse_btn.click()
    assert sources.search.text() == "单独预览" and batch._add_btn.text() == "查看上次预览"
    batch._url_text.setPlainText(f"  {first.url}  \n保留的无效行\n{second.url}")
    assert batch._add_btn.text() == "查看上次预览"
    batch._url_text.setPlainText(f"{legacy}\n{second.url}")
    batch._add_btn.click()
    assert batch.preview_ready and batch.selection.state.selected == checked
    batch._collapse_btn.click()
    sources.grid._widgets[0].secondary_button.click()
    assert batch.preview_ready and batch.selection.state.selected == quick_checked
    assert calls == [7, 9, 11]
    batch._collapse_btn.click()

    batch._draft_button.click()
    popup = batch.findChild(QDialog, "BatchDraftPopup")
    buttons = [button for button in popup.findChildren(QPushButton) if button.text() == "移除"]
    assert [button.accessibleName() for button in buttons] == [f"移除 · {first.title}", f"移除 · {second.title}"]
    assert popup.frameGeometry().bottom() < batch._draft_button.mapToGlobal(batch._draft_button.rect().topLeft()).y()
    buttons[1].click()
    assert batch._url_text.toPlainText().strip() == legacy
    assert batch._add_btn.text() == "预览 1 个来源"
    qtbot.keyClick(popup, Qt.Key_Escape)
    assert not popup.isVisible()


def test_batch_settings_edit_shared_values_and_reveal_invalid_field(workspace, qtbot, monkeypatch):
    window = workspace
    batch = window._batch_page
    window.resize(900, 640)
    window.show()
    window._download_tabs.setCurrentIndex(1)
    batch._url_text.setPlainText("BV1GJ411x7h7")
    batch._on_report(ImportReport([VideoInfo(bvid="BV1GJ411x7h7", title="示例作品")]))
    configuration = window._configuration
    assert not configuration.isVisible() and batch._action_bar.edit_button.isVisible()
    expected = []

    def configure():
        dialog = window._batch_settings_dialog
        expected.append(dialog.isAncestorOf(configuration) and configuration.content.isVisible())
        window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.AUDIO))
        dialog.accept()

    QTimer.singleShot(50, window, configure)
    batch._action_bar.edit_button.click()
    assert expected == [True]
    assert not configuration.isVisible() and configuration.parentWidget() is window._output_sections
    assert window._output_mode_combo.currentData() == OutputMode.AUDIO
    assert "仅音频" in batch._output_specs.toolTip()

    window._match_policy.setCurrentIndex(-1)
    monkeypatch.setattr(window, "_confirm_copyright_acknowledgement", lambda: True)
    observed = []

    def check_error():
        observed.append((configuration._error_field, configuration._error_control))
        window._batch_settings_dialog.reject()

    QTimer.singleShot(50, window, check_error)
    batch._add_btn.click()
    assert observed == [(window._match_policy_row, window._match_policy)]
    assert not window._task_repository.list_tasks() and batch.preview_ready


def test_account_change_discards_old_preview_and_keeps_pasted_draft(workspace, qtbot, monkeypatch):
    pool = QueuedPool()
    monkeypatch.setattr(QThreadPool, "globalInstance", lambda: pool)
    window = workspace
    window.show()
    window._download_tabs.setCurrentIndex(1)
    batch = window._batch_page
    sources = window._batch_sources
    sources.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "old"}), mid=42)
    source = "BV1GJ411x7h7"
    batch._url_text.setPlainText(source)
    batch._url_text.setFocus()
    qtbot.keyClick(batch._url_text, Qt.Key_Return, Qt.ControlModifier)
    assert batch._busy
    old = batch._resolve_worker
    sources.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "new"}), mid=43)
    assert old.cancel.is_set() and batch._url_text.toPlainText() == source
    assert batch._add_btn.text() == "预览 1 个来源" and not batch._busy
    batch._add_btn.click()
    old.completed.emit(ImportReport([VideoInfo(bvid=source, title="旧账号结果")]))
    assert batch._busy and batch._preview.rowCount() == 0
    batch._resolve_worker.completed.emit(ImportReport([VideoInfo(bvid=source, title="新账号结果")]))
    assert batch.preview_ready and batch.get_video_infos()[0].title == "新账号结果"


def test_quick_preview_reports_empty_and_keeps_cancelled_partial_selection(workspace, qtbot, monkeypatch):
    season = BatchSource("https://space.bilibili.com/42/lists/7?type=season", "命名合集", "作者")
    pool = QueuedPool()
    monkeypatch.setattr(QThreadPool, "globalInstance", lambda: pool)
    monkeypatch.setattr(batch_sources, "load_batch_sources", lambda *_: BatchSourcePage((season,)))
    sources, batch = workspace._batch_sources, workspace._batch_page
    sources.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    workspace.show()
    workspace._download_tabs.setCurrentIndex(1)
    sources.tabs.setCurrentIndex(2)
    qtbot.waitUntil(lambda: len(sources.grid._widgets) == 1)
    sources.grid._widgets[0].secondary_button.click()
    batch._on_report(ImportReport())
    assert batch._empty_result.text() == "所选来源没有可解析的作品。"
    assert batch._add_btn.text() == "重新预览"
    batch._add_btn.click()
    batch._on_progress({"source": season.url, "source_index": 1, "sources": 1,
                        "stage": "读取合集", "completed": 1, "total": 3, "items": 1})
    assert season.title in batch._progress_label.text() and "已解析 1 个作品" in batch._progress_label.text()
    assert batch._add_btn.text() == "取消解析"
    batch._add_btn.click()
    assert batch._resolve_worker.cancel.is_set()
    assert batch._add_btn.text() == "正在停止…" and not batch._add_btn.isEnabled()
    first = VideoInfo(bvid="BV1GJ411x7h7", title="已读取作品")
    second = VideoInfo(bvid="BV1Q541167Qg", title="重试成功作品")
    issue = ImportIssue(season.url, "暂时不可读", second.bvid, kind="item")
    batch._on_report(ImportReport([first], [issue], cancelled=True))
    assert batch.preview_ready and "保留 1 个作品" in batch.selection_bar.summary.text()
    batch._selectors[0].setChecked(False)
    batch._retry_btn.click()
    assert batch._run_sources == [second.bvid]
    assert batch._preview.rowCount() == 1 and batch._preview.isVisible()
    batch._on_report(ImportReport([second]))
    assert batch.get_video_infos() == [second] and not batch._errors


def test_offscreen_directory_and_cover_jobs_wait_for_scroll(qtbot, monkeypatch):
    favorites = tuple(BatchSource(f"https://space.bilibili.com/42/favlist?fid={index}", f"收藏夹 {index}",
                                  count=1, owner_mid=42, resource_id=index)
                      for index in range(1, 31))
    monkeypatch.setattr(batch_sources, "load_batch_sources", lambda *_: BatchSourcePage(favorites))
    looked_up = []

    def cover(_cookies, source, *, favorite):
        assert favorite
        looked_up.append(source.url)
        return BatchCover()

    monkeypatch.setattr(batch_sources, "load_batch_cover", cover)
    pool, images = QueuedPool(), ThumbnailLoader()
    panel = batch_sources.BatchSourcesWidget(pool, images)
    panel.set_loading_enabled(True)
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    qtbot.addWidget(panel)
    panel.resize(755, 410)
    panel.show()
    assert not pool.jobs

    panel.tabs.setCurrentIndex(1)
    qtbot.waitUntil(lambda: len(pool.jobs) == 1)
    pool.jobs[0].run()
    qtbot.waitUntil(lambda: panel.grid.materialized_count > 0)
    initial = panel.grid.materialized_count
    assert initial < len(favorites)
    qtbot.waitUntil(lambda: len(pool.jobs) == 3)
    assert len(panel._cover_requests) == 2
    queued_keys = [job.kind for job in pool.jobs[1:]]
    assert all(key in {card.url for card in favorites[:initial]} for key in queued_keys)
    for job in pool.jobs[1:]:
        job.run()
    qtbot.waitUntil(lambda: set(queued_keys) <= panel._cover_cache.keys())
    assert looked_up == queued_keys


def test_collection_cdn_can_load_anonymously(monkeypatch):
    payload = io.BytesIO()
    Image.new("RGB", (32, 18)).save(payload, "PNG")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def raise_for_status(self):
            pass

        def iter_bytes(self):
            yield payload.getvalue()

    def stream(method, url, **kwargs):
        assert method == "GET" and url == "https://archive.biliimg.com/cover.png"
        assert kwargs == {"timeout": 5.0, "follow_redirects": False}
        return Response()

    monkeypatch.setattr(discovery_cards.httpx, "stream", stream)
    assert discovery_cards._thumbnail("//archive.biliimg.com/cover.png").startswith(b"\xff\xd8")


def test_rendered_cover_uses_first_video_after_original_image_fails(qtbot, monkeypatch):
    cover = "https://i0.hdslb.com/folder-cover.png"
    broken = "https://i0.hdslb.com/broken-cover.png"
    fallback = "https://i0.hdslb.com/first-video.png"
    favorites = (
        BatchSource("first", "有封面", cover=cover, owner_mid=42, resource_id=1),
        BatchSource("second", "封面不可用", cover=broken, owner_mid=42, resource_id=2),
    )
    payload = io.BytesIO()
    Image.new("RGB", (32, 18)).save(payload, "PNG")
    thumbnail_requests, fallback_requests = [], []

    def download(url):
        thumbnail_requests.append(url)
        return b"" if url == broken else payload.getvalue()

    def lookup_cover(_cookies, source, *, favorite):
        assert favorite
        fallback_requests.append(source.url)
        return BatchCover((fallback,))

    monkeypatch.setattr(discovery_cards, "_thumbnail", download)
    monkeypatch.setattr(batch_sources, "load_batch_sources", lambda *_: BatchSourcePage(favorites))
    monkeypatch.setattr(batch_sources, "load_batch_cover", lookup_cover)
    pool, images = QueuedPool(), ThumbnailLoader()
    panel = batch_sources.BatchSourcesWidget(pool, images)
    qtbot.addWidget(panel)
    panel.resize(800, 300)
    panel.set_loading_enabled(True)
    panel.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}), mid=42)
    panel.tabs.setCurrentIndex(1)
    panel.show()
    pool.jobs[0].run()
    qtbot.waitUntil(lambda: len(pool.jobs) == 2)
    pool.jobs[1].run()
    qtbot.waitUntil(lambda: len(panel.grid._widgets) == 2 and all(widget.cover.image for widget in panel.grid._widgets))
    assert fallback_requests == ["second"]
    assert thumbnail_requests.index(broken) < thumbnail_requests.index(fallback)
    assert panel._cover_cache == {"second": (fallback,)}
    images.pool.waitForDone(1000)
