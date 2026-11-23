"""On-demand video discovery for the download workspace."""

import sys
from datetime import timedelta
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.api.endpoints import FOLLOWING_FEED_PAGE, VIDEO_RANKING_PAGE
from bilibili_downloader.core.daily_rankings import (
    RankingResult,
    beijing_now,
    load_following_ranking,
    load_public_ranking,
)
from bilibili_downloader.gui.widgets.components import WorkspaceTabBar
from bilibili_downloader.gui.widgets.discovery_cards import (
    DiscoveryCard,
    DiscoveryGrid,
    DiscoveryJob,
)

# Add a source to packaged builds after it passes live desktop verification.
PACKAGED_RANKING_TABS = ("public",)
TAB_TITLES = {"public": "全站榜", "following": "关注榜"}


def enabled_ranking_tabs():
    return PACKAGED_RANKING_TABS if getattr(sys, "frozen", False) else tuple(TAB_TITLES)


class _RankingPane(QWidget):
    def __init__(self, kind, thumbnails):
        super().__init__()
        self.kind = kind
        self.videos = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toolbar = QWidget()
        actions = QHBoxLayout(self.toolbar)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.refresh = QPushButton("刷新" if kind == "following" else "重试")
        self.login = QPushButton("登录 B 站")
        self.expand = QPushButton("查看全部")
        self.expand.setCheckable(True)
        for button in (self.refresh, self.expand):
            button.setObjectName("DiscoveryHeaderAction")
            actions.addWidget(button)
        self.notice_bar = QWidget()
        notice_layout = QHBoxLayout(self.notice_bar)
        notice_layout.setContentsMargins(0, 0, 0, 0)
        self.notice = QLabel()
        self.notice.setObjectName("MetaLabel")
        self.notice.setTextFormat(Qt.PlainText)
        self.notice.setWordWrap(True)
        notice_layout.addWidget(self.notice, 1)
        self.login.setObjectName("SubtleButton")
        notice_layout.addWidget(self.login)
        label, page = (
            ("打开 B 站关注动态", FOLLOWING_FEED_PAGE) if kind == "following"
            else ("打开 B 站排行榜", VIDEO_RANKING_PAGE)
        )
        self.source = QPushButton(label)
        self.source.setObjectName("TextButton")
        self.source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(page)))
        notice_layout.addWidget(self.source)
        layout.addWidget(self.notice_bar)
        self.grid = DiscoveryGrid(thumbnails)
        self.grid.can_expand.connect(self.expand.setVisible)
        self.expand.hide()
        self.expand.toggled.connect(self.grid.set_expanded)
        self.expand.toggled.connect(lambda expanded: self.expand.setText("收起" if expanded else "查看全部"))
        layout.addWidget(self.grid)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)

    def set_videos(self, videos):
        self.videos = videos
        self.grid.set_cards(
            DiscoveryCard(
                video.url, video.title, video.author or "UP 主未知", (video.cover_url,),
                f"#{rank}", f"{video.play_text} 播放" if video.play_text else "",
                video.duration_text, action="解析下载", opens_video=True,
            )
            for rank, video in enumerate(videos, 1)
        )


class DailyRankingsWidget(QWidget):
    login_requested = Signal()
    parse_requested = Signal(str)
    open_video_requested = Signal(str)
    cards_changed = Signal()

    def __init__(self, tabs, pool, cache_path: Path, thumbnails, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        self._enabled = False
        self._pool = pool
        self._cache_path = cache_path
        self._client = None
        self._pending = {}
        self._results = {}
        self._day = beijing_now().date()
        self._midnight = QTimer(self)
        self._midnight.setSingleShot(True)
        self._midnight.timeout.connect(self._on_midnight)
        self._panes = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QWidget()
        header.setObjectName("DailyRankingHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        heading = QLabel("每日 Top 10")
        heading.setObjectName("SectionTitle")
        header_layout.addWidget(heading)
        self._tabs = WorkspaceTabBar()
        self._tabs.setAccessibleName("切换视频排行榜")
        header_layout.addWidget(self._tabs)
        header_layout.addStretch()
        layout.addWidget(header)
        for kind in tabs:
            pane = _RankingPane(kind, thumbnails)
            pane.refresh.clicked.connect(lambda _checked=False, tab=kind: self._request(tab, refresh=True))
            pane.login.clicked.connect(self.login_requested.emit)
            pane.grid.action_requested.connect(self.parse_requested.emit)
            pane.grid.video_requested.connect(self.open_video_requested.emit)
            self._panes[kind] = pane
            header_layout.addWidget(pane.toolbar)
            layout.addWidget(pane)
            index = self._tabs.addTab(TAB_TITLES[kind])
            self._tabs.setTabData(index, kind)
            self._present(kind)
        self._tabs.currentChanged.connect(self._show_current_tab)
        self._show_current_tab()

    def set_scroll_area(self, scroll):
        for pane in self._panes.values():
            pane.grid.set_scroll_area(scroll)

    def set_loading_enabled(self, enabled):
        self._enabled = enabled
        if enabled:
            self._show_current_tab()
        else:
            self.cancel_requests()

    def _on_midnight(self):
        self._check_day()
        self._show_current_tab()

    def showEvent(self, event):
        super().showEvent(event)
        self._show_current_tab()

    def set_account(self, client):
        if client is self._client:
            return
        self._client = client
        self._clear_following()
        if self.isVisible() and self._current_pane() is self._panes.get("following"):
            self._request("following")

    def cancel_requests(self):
        for kind, request in list(self._pending.items()):
            request.set()
            self._pending.pop(kind)
            self._present(kind)

    def _clear_following(self):
        request = self._pending.pop("following", None)
        if request is not None:
            request.set()
        self._results.pop("following", None)
        if "following" in self._panes:
            self._present("following")

    def _check_day(self):
        now = beijing_now()
        if now.date() != self._day:
            self._day = now.date()
            self._clear_following()
            if "public" in self._panes:
                self._present("public")
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        self._midnight.start(int((tomorrow - now).total_seconds() * 1000) + 10)

    def _current_pane(self):
        return self._panes[self._tabs.tabData(self._tabs.currentIndex())]

    def _show_current_tab(self):
        current = self._current_pane()
        for pane in self._panes.values():
            pane.setVisible(pane is current)
            pane.toolbar.setVisible(pane is current)
        self.cards_changed.emit()
        if self._enabled and self.isVisible():
            self._request(current.kind)

    @property
    def has_cards(self):
        return bool(self._current_pane().videos)

    def _request(self, kind, *, refresh=False):
        if not self._enabled:
            return
        self._check_day()
        if kind in self._pending:
            return
        result = self._results.get(kind, RankingResult())
        if kind == "following" and (self._client is None or result.login_required):
            return
        if result.snapshot and result.snapshot.day == self._day and not (refresh and kind == "following"):
            return

        request = Event()
        self._pending[kind] = request
        if kind == "public":
            job = DiscoveryJob(kind, request, lambda: load_public_ranking(self._cache_path))
        else:
            client = self._client
            job = DiscoveryJob(kind, request, lambda: load_following_ranking(client, request))
        job.signals.finished.connect(self._finished, Qt.QueuedConnection)
        self._present(kind)
        self._pool.start(job)

    @Slot(str, object, object)
    def _finished(self, kind, request, result):
        self._check_day()
        if request is not self._pending.get(kind):
            return
        self._pending.pop(kind)
        previous = self._results.get(kind, RankingResult()).snapshot
        if not result.snapshot and not result.login_required and previous:
            result = RankingResult(previous, result.message)
        self._results[kind] = result
        self._present(kind)

    def _present(self, kind):
        pane = self._panes[kind]
        result = self._results.get(kind, RankingResult())
        pending = kind in self._pending
        following = kind == "following"
        login_required = following and (self._client is None or result.login_required)
        snapshot = result.snapshot
        stale = snapshot is not None and snapshot.day != self._day
        messages = []
        if stale:
            messages.append("显示上次榜单。")
        if following and snapshot and not snapshot.videos and not result.message:
            messages.append("今天的关注动态还没有视频投稿。")
        if result.message and not pending:
            messages.append(result.message)
        if pending:
            messages.append("正在加载榜单…")
        elif login_required and not result.message:
            messages.append("请登录 B 站后查看关注榜。")
        pane.notice.setText("".join(messages))
        pane.notice_bar.setVisible(bool(messages))
        had_cards = bool(pane.videos)
        pane.set_videos(snapshot.videos if snapshot else ())
        if had_cards != bool(pane.videos) and pane is self._current_pane():
            self.cards_changed.emit()
        pane.login.setVisible(login_required)
        pane.refresh.setText("重试" if result.message or not following else "刷新")
        pane.refresh.setVisible(not login_required and (following or not snapshot or stale))
        pane.refresh.setEnabled(not pending)
        pane.source.setVisible(bool(result.message and not pending) or login_required)
