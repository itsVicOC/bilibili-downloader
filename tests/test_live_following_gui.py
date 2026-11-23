"""Live card pagination, actions, and shared anonymous thumbnails."""

import io
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from bilibili_downloader.api.live import FollowedLiveRoom
from bilibili_downloader.gui.widgets import discovery_cards, live_following
from tests.test_workspaces import room
from tests.test_workspaces import workspace as workspace


def test_followed_live_cards_load_in_workspace_and_dispatch_by_state(workspace, qtbot, monkeypatch):
    requests = []
    offline = FollowedLiveRoom(1, "作者一", "下次见", 0, "", "")
    live = FollowedLiveRoom(2, "作者二", "当前场次", 1, "", "")
    carousel = FollowedLiveRoom(3, "作者三", "直播预告", 2, "", "")
    next_live = FollowedLiveRoom(4, "作者四", "另一场直播", 1, "", "")

    def load(cookies, page):
        requests.append((cookies["SESSDATA"], page))
        return live_following.FollowedRoomsPage(
            (offline, live, carousel) if page == 1 else (next_live,), page == 1,
        )

    monkeypatch.setattr(live_following, "load_followed_rooms", load)
    page = workspace._live_page
    follow = page.following
    follow.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}))
    workspace.show()
    assert requests == []
    workspace._show_workspace(1)
    qtbot.waitUntil(lambda: len(follow.grid._cards) == 3)
    assert requests == [("fixture", 1)]
    assert [(card.key, card.action) for card in follow.grid._cards] == [
        ("2", "立即录制"), ("1", "添加监控"), ("3", "添加监控"),
    ]
    assert follow.grid._cards[2].badge == "轮播"
    assert [card.badge_tone for card in follow.grid._cards] == ["active", "muted", "warning"]
    assert follow.grid.more.isVisible()
    follow.grid.more.setFocus(Qt.TabFocusReason)
    qtbot.keyClick(follow.grid.more, Qt.Key_Space)
    qtbot.waitUntil(lambda: len(follow.grid._cards) == 4)
    assert [card.key for card in follow.grid._cards] == ["2", "4", "1", "3"]

    def card_for(key):
        return next(widget for widget in follow.grid._widgets if widget.card.key == key)

    page._confirm_copyright = lambda: True
    for target in (card_for("2").cover, card_for("2").title, card_for("1").cover, card_for("1").title):
        qtbot.mouseClick(target, Qt.LeftButton)
    assert not page.service.commands
    assert card_for("2").video_button is None
    page._confirm_copyright = lambda: False
    card_for("2").action_button.click()
    assert not page.service.commands
    page._confirm_copyright = lambda: True
    card_for("2").action_button.click()
    assert card_for("2").action_button.text() == "处理中…"
    assert not card_for("2").action_button.isEnabled()
    card_for("2").action_button.click()
    monitor = card_for("1").action_button
    monitor.setFocus(Qt.TabFocusReason)
    qtbot.keyClick(monitor, Qt.Key_Return)
    assert [(args["room_id"], args["intent"]) for action, args in page.service.commands if action == "shortcut"] == [
        (2, "record"), (1, "monitor"),
    ]
    for action, args in page.service.commands:
        if action == "shortcut":
            args["completion"].set_result((True, "已提交"))
    page.service.rows = [room(room_id=1), {**room(room_id=2, state="recording"), "state_label": "录制中"}]
    page.refresh()
    assert card_for("1").card.badge == "未开播 · 已监控"
    assert card_for("1").card.badge_tone == "success"
    assert card_for("2").card.badge == "录制中"
    assert card_for("2").action_button.text() == "查看房间"
    card_for("2").action_button.click()
    assert page._room_id() == 2
    follow.set_account(None)
    assert not follow.grid._cards and follow.login.isVisible()


def test_followed_live_scroll_renders_current_page_before_fetching_another(workspace, qtbot, qapp, monkeypatch):
    requests = []
    covers = set()

    def load(_cookies, page):
        requests.append(page)
        return live_following.FollowedRoomsPage(tuple(
            FollowedLiveRoom(i, f"作者 {i}", f"直播间 {i}", 0, f"cover-{i}", "")
            for i in (range(1, 9) if page == 1 else [9])
        ), has_more=page == 1)

    monkeypatch.setattr(live_following, "load_followed_rooms", load)
    monkeypatch.setattr(workspace._thumbnails, "resolve", lambda urls: covers.add(urls[0]))
    page = workspace._live_page
    follow = page.following
    follow.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "fixture"}))
    workspace.resize(900, 640)
    workspace.show()
    workspace._show_workspace(1)
    qtbot.waitUntil(lambda: len(follow.grid._cards) == 8)
    grid = follow.grid
    qtbot.waitUntil(lambda: len(grid._widgets) == grid._columns())
    first_row = grid._widgets.copy()
    qtbot.waitUntil(lambda: len(covers) == len(first_row))
    bar = page._scroll.verticalScrollBar()
    previous_maximum = bar.maximum()
    if previous_maximum:
        bar.setValue(previous_maximum)
    else:
        viewport = page._scroll.viewport()
        point = viewport.rect().center()
        event = QWheelEvent(
            QPointF(point), QPointF(viewport.mapToGlobal(point)), QPoint(), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )
        qapp.sendEvent(viewport, event)
    qtbot.waitUntil(lambda: len(grid._widgets) > len(first_row) and bar.maximum() > previous_maximum)
    assert requests == [1]
    assert grid._widgets[:len(first_row)] == first_row
    assert bar.value() == previous_maximum

    while len(grid._widgets) < 8:
        previous_count = len(grid._widgets)
        previous_maximum = bar.maximum()
        bar.setValue(previous_maximum)
        qtbot.waitUntil(lambda: len(grid._widgets) > previous_count and bar.maximum() > previous_maximum)
        assert requests == [1]

    bar.setValue(bar.maximum())
    qtbot.waitUntil(lambda: len(grid._widgets) == 9)
    assert requests == [1, 2]
    assert grid._widgets[:len(first_row)] == first_row
    assert not grid.more.isVisible()


def test_followed_live_discards_response_after_account_change(workspace, qtbot, monkeypatch):
    class Pool:
        def __init__(self):
            self.jobs = []

        def start(self, job):
            self.jobs.append(job)

    monkeypatch.setattr(live_following, "load_followed_rooms", lambda cookies, page:
                        live_following.FollowedRoomsPage(
                            (FollowedLiveRoom(2, cookies["SESSDATA"], "", 0, "", ""),)
                        ))
    follow = workspace._live_page.following
    pool = follow._pool = Pool()
    workspace.show()
    workspace._show_workspace(1)
    follow.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "old-fixture"}))
    pool.jobs[0].run()
    follow.set_account(SimpleNamespace(auth_cookies={"SESSDATA": "new-fixture"}))
    pool.jobs[1].run()
    qtbot.waitUntil(lambda: [card.author for card in follow.grid._cards] == ["new-fixture"])
    assert pool.jobs[0].request.is_set()


def test_anonymous_thumbnail_falls_back_to_avatar(qtbot, monkeypatch):
    calls = []
    binary = io.BytesIO()
    Image.new("RGB", (32, 32), "#243051").save(binary, "PNG")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def raise_for_status(self):
            pass

        def iter_bytes(self):
            yield binary.getvalue()

    def stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    monkeypatch.setattr(discovery_cards.httpx, "stream", stream)
    loader = discovery_cards.ThumbnailLoader()
    grid = discovery_cards.DiscoveryGrid(loader)
    qtbot.addWidget(grid)
    grid.set_cards([discovery_cards.DiscoveryCard(
        "1", "标题", "作者", ("https://example.com/untrusted.jpg", "//i0.hdslb.com/avatar.png"),
    )])
    grid.resize(720, 240)
    grid.show()
    widget = grid._widgets[0]
    qtbot.waitUntil(lambda: widget.cover.image is not None)
    assert calls == [("GET", "https://i0.hdslb.com/avatar.png", {"timeout": 5.0, "follow_redirects": False})]
    assert widget.cover.image.width() == 480
    assert widget.cover.heightForWidth(240) == 135
