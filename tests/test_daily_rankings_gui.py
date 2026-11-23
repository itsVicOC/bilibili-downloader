"""Website navigation, discovery, and personalized view state."""

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QDesktopServices, QWheelEvent
from PySide6.QtWidgets import QLabel

from bilibili_downloader.core.daily_rankings import (
    RankedVideo,
    RankingResult,
    RankingSnapshot,
)
from bilibili_downloader.core.models import VideoInfo, VideoPage
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets import daily_rankings
from bilibili_downloader.gui.widgets.discovery_cards import ThumbnailLoader
from bilibili_downloader.utils.config import ConfigManager
from tests.test_daily_rankings import TODAY, bvid
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_sidebar_website_and_help_share_default_browser_action(platform, tmp_path, qtbot, monkeypatch):
    window = MainWindow(ConfigManager(tmp_path / "config.json"), desktop_platform=platform, startup_paused=True)
    qtbot.addWidget(window)
    window._set_shell_enabled(True)
    window.resize(900, 640)
    window.show()
    button = window._website_button
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    assert button.isVisible() and button.text() == ""
    assert button.objectName() == window._settings_nav.objectName() == "NavButton"
    assert button.toolTip() == button.accessibleName() == "BiliFlow 官网"
    assert button.y() > window._settings_nav.y()
    assert button.geometry().bottom() < window._mode_button.y()
    assert not button.icon().isNull()
    button.setFocus()
    qtbot.keyClick(button, Qt.Key_Space)
    window._actions["website"].trigger()
    assert opened == ["https://1008.si/", "https://1008.si/"]
    window.resize(1320, 800)
    assert button.text() == "BiliFlow 官网"


def test_packaged_build_exposes_both_following_views(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(Path(__file__).resolve().parents[1]), raising=False)
    window = MainWindow(ConfigManager(tmp_path / "config.json"), startup_paused=True)
    qtbot.addWidget(window)
    assert tuple(window._ranking_panel._panes) == ("public", "following")
    assert window._live_page.following is not None
    window._api_client.sessdata = "test-expired"
    window._on_login_status_result(window._login_status_request_id, {"isLogin": False})
    assert "已失效" in window._ranking_panel._panes["following"].notice.text()
    assert "已失效" in window._live_page.following.status.text()
    window._set_discovery_account(None)
    assert "已失效" not in window._ranking_panel._panes["following"].notice.text()
    assert "已失效" not in window._live_page.following.status.text()


@pytest.mark.parametrize("dark", [False, True])
def test_video_workspace_loads_on_first_show_with_independent_actions(workspace, qtbot, qapp, monkeypatch, dark):
    videos = tuple(RankedVideo(bvid(n), "超长标题用于验证自动换行与省略" * 6, "作者", "123") for n in range(1, 11))
    fetches, parsed, opened = [], [], []

    def load(path):
        fetches.append(path.name)
        return RankingResult(RankingSnapshot(TODAY, videos))

    monkeypatch.setattr(daily_rankings, "beijing_now", lambda: TODAY)
    monkeypatch.setattr(daily_rankings, "load_public_ranking", load)
    def resolve():
        parsed.append(workspace._url_input.text())
        workspace._resolving_video = True
        workspace._sync_download_presentation()

    monkeypatch.setattr(workspace, "_on_resolve_clicked", resolve)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    assert fetches == []
    theme = ThemeManager(qapp)
    theme.setParent(workspace)
    theme.apply_theme(dark)
    # Linux keeps the menu bar inside the window. Exercise the same height
    # constraint on both native and offscreen test hosts.
    workspace.menuBar().setNativeMenuBar(False)
    workspace.menuBar().show()
    workspace.resize(900, 640)
    workspace._download_tabs.setCurrentIndex(1)
    workspace.show()
    assert fetches == []
    workspace._download_tabs.setCurrentIndex(0)
    panel = workspace._ranking_panel
    pane = panel._panes["public"]
    qtbot.waitUntil(lambda: len(pane.grid._widgets) == 3)
    qapp.processEvents()
    assert pane.videos == videos
    assert not pane.notice_bar.isVisible()
    assert fetches == ["video-ranking.json"]
    viewport = workspace._workspace_scroll.viewport()
    row = pane.grid._widgets[0]
    qtbot.waitUntil(lambda: row.video_button.height() > row.cover.height())
    assert viewport.rect().contains(row.mapTo(viewport, row.rect().bottomRight()))
    assert row.video_button.rect().contains(row.cover.mapTo(row.video_button, row.cover.rect().bottomRight()))
    assert viewport.rect().contains(workspace._resolve_btn.mapTo(viewport, workspace._resolve_btn.rect().topLeft()))
    panel._tabs.setCurrentIndex(1)
    assert panel._panes["following"].login.isVisible() and not pane.isVisible()
    panel._tabs.setCurrentIndex(0)
    draft = bvid(99)
    workspace._url_input.setText(draft)
    first = pane.grid._widgets[0]
    pane.grid.more.click()
    qtbot.waitUntil(lambda: len(pane.grid._widgets) > 3)
    assert first is pane.grid._widgets[0]
    last = pane.grid._widgets[3]
    def reveal_card():
        if not last.isVisible() or last.video_button.height() <= last.cover.height():
            return False
        workspace._workspace_scroll.ensureWidgetVisible(last, 0, 4)
        return viewport.rect().contains(QRect(last.mapTo(viewport, QPoint()), last.size()))

    qtbot.waitUntil(reveal_card)
    scroll = workspace._workspace_scroll.verticalScrollBar()
    position = scroll.value()
    for child in (last.cover, last.title):
        point = child.mapToGlobal(child.rect().center())
        target = workspace.childAt(workspace.mapFromGlobal(point))
        assert target is last.video_button
        qtbot.mouseClick(target, Qt.LeftButton, pos=target.mapFromGlobal(point))
    assert opened == [videos[3].url] * 2
    assert parsed == [] and workspace._url_input.text() == draft
    assert scroll.value() == position
    scroll.setValue(0)
    qapp.processEvents()
    row = pane.grid._widgets[0]
    qapp.setActiveWindow(workspace)
    row.video_button.setFocus(Qt.TabFocusReason)
    qtbot.waitUntil(row.video_button.hasFocus)
    qtbot.keyClick(row.video_button, Qt.Key_Space if dark else Qt.Key_Return)
    assert opened[-1] == videos[0].url
    assert parsed == []
    hints = qapp.styleHints()
    original_tab_behavior = hints.tabFocusBehavior()
    try:
        if dark:
            hints.setTabFocusBehavior(Qt.TabFocusTextControls)
        qtbot.keyClick(row.video_button, Qt.Key_Tab)
        assert row.action_button.hasFocus()
    finally:
        hints.setTabFocusBehavior(original_tab_behavior)
    assert row.action_button.text() == "解析下载"
    qtbot.keyClick(row.action_button, Qt.Key_Return if dark else Qt.Key_Space)
    assert parsed == [videos[0].url]
    assert workspace._download_tabs.currentIndex() == 0
    assert not panel.isVisible()
    assert workspace._task_repository.list_tasks() == []
    workspace._on_resolve_error("离线演示")
    assert panel.isVisible()
    assert "离线演示" in workspace._resolve_notice.label.text()
    qtbot.mouseClick(pane.grid._widgets[0].action_button, Qt.LeftButton)
    assert parsed == [videos[0].url] * 2 and not panel.isVisible()
    workspace._on_resolve_error("离线演示")
    workspace._configuration.open()
    assert not panel.isVisible()
    workspace._configuration.done.click()
    assert panel.isVisible()
    workspace._resolve_request_url = workspace._url_input.text()
    workspace._on_resolve_success(
        VideoInfo(bvid=videos[0].bvid, title=videos[0].title, pages=[VideoPage(cid=1, page=1)]),
        [], [], False,
    )
    assert workspace._return_to_rankings.isVisible() and not panel.isVisible()
    assert workspace._download_btn.isEnabled()
    workspace._cover_check.setChecked(True)
    workspace._return_to_rankings.click()
    assert workspace._url_input.text() == ""
    assert panel.isVisible() and not workspace._download_btn.isEnabled() and workspace._cover_check.isChecked()
    assert fetches == ["video-ranking.json"]


def test_top_100_only_creates_the_first_screen_and_appends_on_scroll(workspace, qtbot, qapp, monkeypatch):
    videos = tuple(
        RankedVideo(bvid(n), f"作品 {n}", "作者", str(n), cover_url=f"https://i0.hdslb.com/{n}.jpg")
        for n in range(1, 101)
    )
    fetches, requested_covers = [], set()

    def load(path):
        fetches.append(path)
        return RankingResult(RankingSnapshot(TODAY, videos))

    monkeypatch.setattr(daily_rankings, "beijing_now", lambda: TODAY)
    monkeypatch.setattr(daily_rankings, "load_public_ranking", load)
    monkeypatch.setattr(workspace._thumbnails, "resolve", lambda urls: requested_covers.update(urls))
    workspace.menuBar().setNativeMenuBar(False)
    workspace.menuBar().show()
    workspace.resize(900, 640)
    workspace.show()
    grid = workspace._ranking_panel._panes["public"].grid
    viewport = workspace._workspace_scroll.viewport()
    scroll = workspace._workspace_scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: len(grid._widgets) == 3 and len(requested_covers) == 3)
    qapp.processEvents()
    assert [widget.card.badge for widget in grid._widgets] == ["#1", "#2", "#3"]
    assert requested_covers == {video.cover_url for video in videos[:3]}
    initial = tuple(grid._widgets)
    # The first screen can fill the viewport without creating a scrollbar.
    end_of_first_screen = scroll.maximum()
    if end_of_first_screen:
        scroll.setValue(end_of_first_screen)
    else:
        point = viewport.rect().center()
        event = QWheelEvent(
            QPointF(point), QPointF(viewport.mapToGlobal(point)), QPoint(), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )
        qapp.sendEvent(viewport, event)
    qtbot.waitUntil(lambda: len(grid._widgets) > 3)
    assert tuple(grid._widgets[:3]) == initial
    assert scroll.value() == end_of_first_screen
    assert len(grid._widgets) < 100
    before = len(grid._widgets)
    qtbot.waitUntil(lambda: scroll.maximum() > end_of_first_screen)
    scroll.setValue(scroll.maximum())
    qtbot.waitUntil(lambda: len(grid._widgets) > before)
    qapp.setActiveWindow(workspace)
    grid.more.setFocus(Qt.TabFocusReason)
    qtbot.waitUntil(grid.more.hasFocus)
    before = len(grid._widgets)
    qtbot.keyClick(grid.more, Qt.Key_Return)
    assert len(grid._widgets) > before
    while grid.more.isVisible():
        grid.more.click()
    assert [widget.card.key for widget in grid._widgets] == [video.url for video in videos]
    assert grid._widgets[-1].card.badge == "#100"
    assert len(fetches) == 1


def test_stale_ranking_offers_retry_without_displaying_a_timestamp(qtbot, tmp_path, monkeypatch):
    video = RankedVideo(bvid(1), "上次的作品", "作者", "123")
    prior = RankingSnapshot(TODAY, (video,))
    updated = RankingSnapshot(TODAY, (video,))
    loads = iter((RankingResult(prior, "暂时无法读取榜单。", stale=True), RankingResult(updated)))
    monkeypatch.setattr(daily_rankings, "beijing_now", lambda: TODAY)
    monkeypatch.setattr(daily_rankings, "load_public_ranking", lambda path: next(loads))
    thumbnails = ThumbnailLoader()
    pool = thumbnails.pool
    panel = daily_rankings.DailyRankingsWidget(("public",), pool, tmp_path / "ranking.json", thumbnails)
    qtbot.addWidget(panel)
    panel.set_loading_enabled(True)
    panel.show()
    pane = panel._panes["public"]
    qtbot.waitUntil(lambda: "显示上次榜单" in pane.notice.text())
    assert pane.refresh.isEnabled() and pane.refresh.text() == "重试"
    assert pane.videos == (video,)
    assert not any(
        token in label.text()
        for label in panel.findChildren(QLabel)
        for token in ("北京时间", "获取于", prior.fetched_at.date().isoformat())
    )
    pane.refresh.click()
    qtbot.waitUntil(lambda: not pane.notice_bar.isVisible())
    assert not pane.refresh.isVisible()


def test_ranked_card_actions_fit_enlarged_type(workspace, qtbot, qapp, monkeypatch):
    video = RankedVideo(bvid(1), "带有很长标题的榜单测试作品" * 3, "名字很长的 UP 主" * 3, "3.5 万")
    monkeypatch.setattr(daily_rankings, "beijing_now", lambda: TODAY)
    monkeypatch.setattr(daily_rankings, "load_public_ranking", lambda path:
                        RankingResult(RankingSnapshot(TODAY, (video,))))
    theme = ThemeManager(qapp)
    theme.setParent(workspace)
    qapp.setStyleSheet(load_stylesheet(False, theme._font_scale * 1.5, theme._font_family))
    workspace.resize(900, 640)
    workspace.show()
    scroll = workspace._workspace_scroll
    viewport = scroll.viewport()
    grid = workspace._ranking_panel._panes["public"].grid

    def reveal_action():
        if not grid._widgets:
            return False
        card = grid._widgets[0]
        button = card.action_button
        bounds = QRect(button.mapTo(card, button.rect().topLeft()), button.size())
        if not button.isVisible() or not card.rect().contains(bounds):
            return False
        scroll.ensureWidgetVisible(button, 0, 4)
        return viewport.rect().contains(QRect(
            button.mapTo(viewport, button.rect().topLeft()), button.size(),
        ))

    qtbot.waitUntil(reveal_action)
    button = grid._widgets[0].action_button
    assert button.width() > button.fontMetrics().horizontalAdvance(button.text())
    assert button.height() > button.fontMetrics().height()
    assert scroll.horizontalScrollBar().maximum() == 0


def test_following_sort_switch_reuses_fetched_video_list(qtbot, tmp_path, monkeypatch):
    oldest = RankedVideo(bvid(1), "更早的视频", "作者", "2万", int((TODAY - timedelta(days=3)).timestamp()))
    latest = RankedVideo(bvid(2), "最新的视频", "作者", "500", int(TODAY.timestamp()))
    requests = []

    def load(client, cancelled):
        requests.append(client)
        return RankingResult(RankingSnapshot(TODAY, (oldest, latest)))

    monkeypatch.setattr(daily_rankings, "beijing_now", lambda: TODAY)
    monkeypatch.setattr(daily_rankings, "load_following_ranking", load)
    thumbnails = ThumbnailLoader()
    panel = daily_rankings.DailyRankingsWidget(
        ("following",), thumbnails.pool, tmp_path / "ranking.json", thumbnails,
    )
    qtbot.addWidget(panel)
    account = object()
    panel.set_account(account)
    panel.set_loading_enabled(True)
    panel.show()
    pane = panel._panes["following"]
    qtbot.waitUntil(lambda: pane.sort.isVisible())
    assert pane.videos == (latest, oldest)
    pane.sort.setCurrentIndex(1)
    assert pane.videos == (oldest, latest)
    pane.sort.setCurrentIndex(0)
    assert pane.videos == (latest, oldest)
    assert requests == [account]


def test_following_ignores_in_flight_results_from_previous_account_and_day(qtbot, tmp_path, monkeypatch):
    now = TODAY
    monkeypatch.setattr(daily_rankings, "beijing_now", lambda: now)
    video = RankedVideo(bvid(1), "旧账号结果", "作者", "1")
    old_client, new_client = object(), object()

    def load(client, _cancelled):
        videos = (video,) if client is old_client else ()
        return RankingResult(RankingSnapshot(now, videos))

    class Pool:
        def __init__(self):
            self.jobs = []

        def start(self, job):
            self.jobs.append(job)

    monkeypatch.setattr(daily_rankings, "load_following_ranking", load)
    pool = Pool()
    panel = daily_rankings.DailyRankingsWidget(("following",), pool, tmp_path / "ranking.json", ThumbnailLoader())
    qtbot.addWidget(panel)
    panel.set_loading_enabled(True)
    panel.show()
    pane = panel._panes["following"]
    assert pane.login.isVisible() and not pool.jobs

    panel.set_account(old_client)
    pool.jobs[0].run()
    panel.set_account(new_client)
    assert pool.jobs[0].request.is_set()
    pool.jobs[1].run()
    qtbot.waitUntil(lambda: "没有可上榜的视频投稿" in pane.notice.text())
    assert pane.notice.text() == "已读取的关注动态中没有可上榜的视频投稿。"
    assert pane.source is None and pane.refresh.text() == "刷新"
    assert not pane.videos

    pane.refresh.click()
    pool.jobs[2].run()
    now += timedelta(days=1)
    panel._check_day()
    assert pool.jobs[2].request.is_set()
    assert not pane.videos
    panel.set_account(None)
    assert pane.login.isVisible()
    assert not (tmp_path / "ranking.json").exists()
