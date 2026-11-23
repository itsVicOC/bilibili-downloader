"""Account-scoped discovery for followed Bilibili live rooms."""

import sys
from dataclasses import dataclass
from threading import Event

import httpx
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from bilibili_downloader.api.client import BilibiliAPIError
from bilibili_downloader.api.live import BilibiliLiveClient, FollowedLiveRoom
from bilibili_downloader.gui.widgets.discovery_cards import (
    DiscoveryCard,
    DiscoveryGrid,
    DiscoveryJob,
)

# Open to packaged builds after verifying both live and offline pages with an account.
PACKAGED_LIVE_FOLLOWING = False
ACTIVE_STATES = {
    "preparing": "active", "queued": "warning", "recording": "active",
    "reconnecting": "warning", "finalizing": "active",
}
ROOM_STATUS = {-1: "状态未知", 0: "未开播", 1: "直播中", 2: "轮播"}
ROOM_TONES = {-1: "warning", 0: "muted", 1: "active", 2: "warning"}


def live_following_enabled():
    return PACKAGED_LIVE_FOLLOWING or not getattr(sys, "frozen", False)


@dataclass(frozen=True)
class FollowedRoomsPage:
    rooms: tuple[FollowedLiveRoom, ...] = ()
    has_more: bool = False
    error: str = ""
    login_required: bool = False


def load_followed_rooms(cookies, page):
    client = BilibiliLiveClient(auth_cookies=cookies, timeout=6)
    try:
        rooms, has_more = client.get_followed_rooms(page)
        return FollowedRoomsPage(rooms, has_more)
    except (BilibiliAPIError, httpx.HTTPError, ValueError, AttributeError) as exc:
        code = exc.code if isinstance(exc, BilibiliAPIError) else (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        )
        if code in (-101, 401):
            return FollowedRoomsPage(error="请登录 B 站后查看关注的 UP 主。", login_required=True)
        if code in (-352, -412, -509, 412, 429):
            return FollowedRoomsPage(error="B 站暂时限制了关注列表请求，请稍后重试。")
        return FollowedRoomsPage(error="无法读取关注列表，请重试。")
    finally:
        client.close()


class LiveFollowingWidget(QWidget):
    login_requested = Signal()
    view_room = Signal(object)
    shortcut_requested = Signal(object, str)
    rooms_changed = Signal()

    def __init__(self, controller, pool, thumbnails, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._pool = pool
        self._account = None
        self._request = None
        self._loading_enabled = False
        self._page = 0
        self._rooms = {}
        self._has_more = False
        self._error = ""
        self._login_required = False
        self._one_row_hidden = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel("关注的 UP 主")
        title.setObjectName("SectionTitle")
        header.addWidget(title, 1)
        self.refresh = QPushButton("刷新")
        self.expand = QPushButton("展开列表")
        self.expand.setCheckable(True)
        self.login = QPushButton("登录 B 站")
        for button in (self.refresh, self.expand):
            button.setObjectName("DiscoveryHeaderAction")
            header.addWidget(button)
        layout.addLayout(header)
        self.notice_bar = QWidget()
        notice_layout = QHBoxLayout(self.notice_bar)
        notice_layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel()
        self.status.setObjectName("MetaLabel")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        notice_layout.addWidget(self.status, 1)
        self.login.setObjectName("SubtleButton")
        notice_layout.addWidget(self.login)
        layout.addWidget(self.notice_bar)
        self.grid = DiscoveryGrid(thumbnails)
        layout.addWidget(self.grid)
        self.more = QPushButton("加载更多")
        self.more.setObjectName("SubtleButton")
        layout.addWidget(self.more, alignment=Qt.AlignCenter)
        self.grid.can_expand.connect(self._overflow_changed)
        self.grid.action_requested.connect(self._activate)
        self.login.clicked.connect(self.login_requested.emit)
        self.refresh.clicked.connect(lambda: self._fetch(1))
        self.expand.toggled.connect(self._toggle_expanded)
        self.more.clicked.connect(lambda: self._fetch(self._page + 1))
        controller.snapshot_changed.connect(self._present)
        controller.shortcuts_changed.connect(self._present)
        self._present()

    def set_loading_enabled(self, enabled):
        self._loading_enabled = enabled
        if enabled:
            self._maybe_load()
        elif self._request:
            self._request.set()
            self._request = None
            self._present()

    def set_account(self, account):
        if self._account is account:
            return
        if self._request:
            self._request.set()
            self._request = None
        self._account = account
        self._page = 0
        had_rooms = bool(self._rooms)
        self._rooms.clear()
        self._has_more = False
        self._error = ""
        self._login_required = False
        self.expand.setChecked(False)
        self._present()
        if had_rooms:
            self.rooms_changed.emit()
        self._maybe_load()

    @property
    def has_rooms(self):
        return bool(self._rooms)

    def showEvent(self, event):
        super().showEvent(event)
        self._maybe_load()

    def _maybe_load(self):
        if not self._page and self.isVisible():
            self._fetch(1)

    def _fetch(self, page):
        if not self._loading_enabled or not self._account or self._login_required or self._request:
            return
        cookies = self._account.auth_cookies
        request = self._request = Event()
        job = DiscoveryJob(str(page), request, lambda: load_followed_rooms(cookies, page))
        job.signals.finished.connect(self._finished, Qt.QueuedConnection)
        self._present()
        self._pool.start(job)

    @Slot(str, object, object)
    def _finished(self, page, request, result):
        if request is not self._request:
            return
        had_rooms = bool(self._rooms)
        self._request = None
        self._error = result.error
        self._login_required = result.login_required
        if self._login_required:
            self._rooms.clear()
            self._page = 0
            self._has_more = False
        elif not self._error:
            self._page = int(page)
            if self._page == 1:
                self._rooms.clear()
            for room in result.rooms:
                self._rooms[room.room_id] = room
            self._has_more = result.has_more
        self._present()
        if had_rooms != self.has_rooms:
            self.rooms_changed.emit()

    def _toggle_expanded(self, expanded):
        self.grid.set_expanded(expanded)
        self.expand.setText("收起列表" if expanded else "展开列表")
        self._update_actions()

    def _overflow_changed(self, overflow):
        self._one_row_hidden = overflow
        self._update_actions()

    def _update_actions(self):
        self.expand.setVisible(self._one_row_hidden or self._has_more)
        self.more.setVisible(self.expand.isChecked() and self._has_more)
        self.more.setEnabled(self._request is None)

    def _action_for(self, room, row):
        if self._controller.shortcut_pending(room.room_id):
            return "处理中…", False
        if row and (row["enabled"] or row["active"] or row["state"] in ACTIVE_STATES):
            return "查看房间", True
        if room.status == -1:
            return "刷新后查看", False
        return ("立即录制" if room.status == 1 else "添加监控"), self._controller.service is not None

    def _present(self, *_):
        login = self._account is None or self._login_required
        self.login.setVisible(login)
        self.refresh.setVisible(not login)
        self.refresh.setText("重试" if self._error and not self._login_required else "刷新")
        self.refresh.setEnabled(self._request is None)
        message = self._error
        if self._request is not None:
            message = "正在读取关注的直播间…"
        elif login:
            message = "登录 B 站后查看关注的直播间。"
        elif self._page and not self._rooms and not message:
            message = "当前关注列表中没有直播间。"
        self.status.setText(message)
        self.notice_bar.setVisible(bool(message))
        rows = {row["room_id"]: row for row in self._controller.rows}
        cards = []
        for room in sorted(self._rooms.values(), key=lambda room: room.status != 1):
            row = rows.get(room.room_id)
            action, enabled = self._action_for(room, row)
            if row and (row["active"] or row["state"] in ACTIVE_STATES or row["state"] == "error"):
                state = row["state_label"]
                tone = ACTIVE_STATES.get(row["state"], "danger" if row["state"] == "error" else "active")
            else:
                state = ROOM_STATUS[room.status]
                tone = ROOM_TONES[room.status]
                if row and row["enabled"]:
                    state += " · 已监控"
                    if room.status == 0:
                        tone = "success"
            cards.append(DiscoveryCard(
                str(room.room_id), room.title or f"{room.author}的直播间",
                room.author or f"房间 {room.room_id}",
                (room.cover, room.avatar), state, action=action, enabled=enabled, badge_tone=tone,
            ))
        self.grid.set_cards(cards)
        self._update_actions()

    def _activate(self, key):
        room = self._rooms.get(int(key))
        if room is None:
            return
        row = next((row for row in self._controller.rows if row["room_id"] == room.room_id), None)
        action, enabled = self._action_for(room, row)
        if enabled:
            if action == "查看房间":
                self.view_room.emit(room.room_id)
            else:
                self.shortcut_requested.emit(room.room_id, "record" if room.status == 1 else "monitor")
