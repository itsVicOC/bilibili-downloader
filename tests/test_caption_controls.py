"""Caption material, shared geometry and one-shot native/client interactions."""

import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QDialog, QMainWindow

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.styles import contrast_ratio, theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.caption_controls import caption_rects
from bilibili_downloader.gui.window_chrome import WindowChrome
from bilibili_downloader.gui.windows_frame import WindowsFrame, frame_hit_test
from tests.test_ui_refresh import restore_theme as restore_theme


class ChromeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.chrome = WindowChrome(self, "win32")

    def nativeEvent(self, event_type, message):
        if hasattr(self, "chrome"):
            result = self.chrome.native_event(message)
            if result is not None:
                return True, result
        return super().nativeEvent(event_type, message)


def test_caption_identity_geometry_and_dialogs(qtbot):
    window = ChromeWindow()
    qtbot.addWidget(window)
    window.setWindowTitle("BiliFlow · 星轨收藏站")
    window.setWindowIcon(QIcon(asset_path("app_icon.png")))
    window.resize(900, 640)
    window.show()
    for transition in (window.showMaximized, window.showNormal, window.hide, window.show):
        transition()
        window.chrome._sync_native()
        assert window.windowFlags() & Qt.FramelessWindowHint
        assert not window.windowFlags() & Qt.ExpandedClientAreaHint
        assert window.windowTitle() == "BiliFlow · 星轨收藏站"
        assert not window.windowIcon().isNull()
        controls = window.chrome.controls
        assert controls.geometry().right() == window.width() - 1
        assert controls.width() == 138 and controls.height() == 32
        assert controls.buttons["maximize"].restore == window.isMaximized()
    dialog = QDialog(window)
    qtbot.addWidget(dialog)
    assert not dialog.windowFlags() & Qt.FramelessWindowHint


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_shared_edges_and_hit_regions_at_every_scale(scale):
    width, height = round(901 * scale), round(640 * scale)
    rectangles = caption_rects(width, scale)
    ordered = list(rectangles.values())
    assert ordered[-1].right() == width - 1
    assert max(r.width() for r in ordered) - min(r.width() for r in ordered) <= 1
    for left, right in zip(ordered, ordered[1:]):
        assert left.right() + 1 == right.left()
    for name, hit in (("minimize", 8), ("maximize", 9), ("close", 20)):
        point = rectangles[name].center()
        assert frame_hit_test(point.x(), point.y(), width, height, scale, round(8 * scale)) == hit
    for x, y, hit in ((0, 0, 13), (width - 1, 0, 14), (0, height - 1, 16),
                      (width - 1, height - 1, 17), (width // 2, 0, 12),
                      (0, height // 2, 10), (width - 1, height // 2, 11),
                      (width // 2, height - 1, 15)):
        assert frame_hit_test(x, y, width, height, scale, round(8 * scale)) == hit
    assert frame_hit_test(width // 2, height // 2, width, height, scale, 8) is None


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_caption_base_hover_glyphs_and_animation_settle(qapp, qtbot, theme_id, dark):
    manager = ThemeManager(qapp, theme_id, "dark" if dark else "light")
    window = ChromeWindow()
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    controls = window.chrome.controls
    p = theme_palette(dark, theme_id)
    for name, button in controls.buttons.items():
        button.reset()
        image = button.grab().toImage()
        assert image.pixelColor(3, 12).name() == p.background
        button.set_hovered(True)
        qtbot.waitUntil(lambda: button._hover.animation.state() == QAbstractAnimation.Stopped)
        image = button.grab().toImage()
        color = p.caption_close_hover if name == "close" else p.caption_hover
        assert image.pixelColor(3, 12).name() == color
        foreground = "#ffffff" if name == "close" else p.text
        assert contrast_ratio(foreground, color) >= 3
        background = QColor(color)
        pixels = [(x, y) for x in range(8, image.width() - 8) for y in range(6, image.height() - 6)
                  if image.pixelColor(x, y) != background]
        assert len(pixels) >= 8
        assert abs((min(x for x, _ in pixels) + max(x for x, _ in pixels)) / 2 - (image.width() - 1) / 2) <= 1
        assert abs((min(y for _, y in pixels) + max(y for _, y in pixels)) / 2 - (image.height() - 1) / 2) <= 1
        button.reset()
        assert button._hover.value == 0
    manager.deleteLater()


def fake_frame(window):
    frame = WindowsFrame.__new__(WindowsFrame)
    frame.chrome, frame.window, frame.hwnd = window.chrome, window, 1
    frame.pressed = None
    frame.user32 = SimpleNamespace(SetCapture=lambda _: None, ReleaseCapture=lambda: None)
    # NC and client paths intentionally share exactly the same geometry.
    frame.geometry = lambda value, **_: (value, 16, 900, 640, 1, 8)
    frame._track_leave = lambda: None
    return frame


def test_native_message_uses_the_windows_handle_field(qtbot, monkeypatch):
    """Decode a real ctypes MSG even when the desktop backend is offscreen."""
    import bilibili_downloader.gui.window_chrome as module

    window = ChromeWindow()
    qtbot.addWidget(window)
    seen = []
    adapter = SimpleNamespace(hwnd=None, event=lambda msg: seen.append(msg.message) or 12)
    window.chrome._native = adapter
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(module.QApplication, "platformName", lambda: "windows")
    msg = wintypes.MSG(hWnd=1234, message=0x0084)
    assert window.chrome.native_event(ctypes.addressof(msg)) == 12
    assert adapter.hwnd == 1234 and seen == [0x0084]
    # Restore before QObject teardown can send native/visibility events.
    window.chrome._native = None


@pytest.mark.parametrize("action,x", [("minimize", 785), ("maximize", 831), ("close", 877)])
def test_native_release_fires_once_and_drag_out_cancels(qtbot, monkeypatch, action, x):
    window = ChromeWindow()
    qtbot.addWidget(window)
    frame = fake_frame(window)
    actions = []
    monkeypatch.setattr(window.chrome.controls, "invoke", actions.append)
    assert frame.event(SimpleNamespace(message=0x00A1, lParam=x)) == 0
    assert frame.pressed == action
    assert frame.event(SimpleNamespace(message=0x0202, lParam=x)) == 0
    frame.event(SimpleNamespace(message=0x00A2, lParam=x))
    assert actions == [action]
    frame.event(SimpleNamespace(message=0x00A1, lParam=x))
    frame.event(SimpleNamespace(message=0x0200, lParam=500))
    assert not window.chrome.controls.buttons[action].isDown()
    frame.event(SimpleNamespace(message=0x0202, lParam=500))
    assert actions == [action]
    frame.event(SimpleNamespace(message=0x00A1, lParam=x))
    frame.event(SimpleNamespace(message=0x0215))
    assert frame.pressed is None


def test_caption_keyboard_actions_and_deactivation(qtbot, monkeypatch):
    window = ChromeWindow()
    qtbot.addWidget(window)
    window.resize(900, 640)
    window.show()
    maximum = window.chrome.controls.buttons["maximize"]
    maximum.setFocus(Qt.TabFocusReason)
    qtbot.keyClick(maximum, Qt.Key_Space)
    assert window.isMaximized()
    qtbot.keyClick(maximum, Qt.Key_Space)
    assert not window.isMaximized()
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    qtbot.mouseClick(window.chrome.controls.buttons["close"], Qt.LeftButton)
    assert closed == [True]
    maximum.set_hovered(True)
    window.chrome.eventFilter(window, QEvent(QEvent.WindowDeactivate))
    assert maximum._hover.value == 0 and not maximum.isDown()


def test_native_hover_is_not_cleared_by_qt_nonclient_leave(qapp, qtbot):
    window = ChromeWindow()
    qtbot.addWidget(window)
    window.show()
    controls = window.chrome.controls
    maximum = controls.buttons["maximize"]
    controls.hover("maximize", native=True)
    qapp.sendEvent(maximum, QEvent(QEvent.Leave))
    assert maximum.hovered and maximum._hover.target == 1
    controls.leave_native()
    assert not maximum.hovered and maximum._hover.target == 0


def test_native_leave_checks_pointer_before_clearing_hover(qtbot):
    window = ChromeWindow()
    qtbot.addWidget(window)
    frame = fake_frame(window)
    frame.cursor_geometry = lambda: (831, 16, 900, 640, 1, 8)
    frame.event(SimpleNamespace(message=0x02A2))
    assert window.chrome.controls.buttons["maximize"].hovered
    frame.cursor_geometry = lambda: (500, 200, 900, 640, 1, 8)
    frame.event(SimpleNamespace(message=0x02A2))
    assert not window.chrome.controls.buttons["maximize"].hovered


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_native_coordinates_on_negative_monitor(qtbot, scale):
    window = ChromeWindow()
    qtbot.addWidget(window)
    frame = WindowsFrame.__new__(WindowsFrame)
    frame.window, frame.hwnd = window, 1
    width = round(900 * scale)
    def rect(_hwnd, pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        value.right, value.bottom = width, round(640 * scale)
        return True
    def convert(_hwnd, pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(wintypes.POINT)).contents
        value.x += 1920
        value.y -= 120
        return True
    frame.user32 = SimpleNamespace(GetClientRect=rect, ScreenToClient=convert,
                                  GetDpiForWindow=lambda _: round(96 * scale),
                                  GetSystemMetricsForDpi=lambda *_: round(4 * scale))
    window.devicePixelRatioF = lambda: scale
    point = caption_rects(width, scale)["maximize"].center()
    x, y = point.x() - 1920, point.y() + 120
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    assert frame.action_at(frame.geometry(lparam)) == "maximize"
