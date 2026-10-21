"""Caption visibility without losing desktop window identity or controls."""

import ctypes
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.window_chrome import WindowChrome
from tests.test_workspaces import workspace as workspace


def test_expanded_windows_caption_preserves_identity_and_controls(qtbot):
    window = QMainWindow()
    qtbot.addWidget(window)
    window.setWindowTitle("BiliFlow · 星轨收藏站")
    window.setWindowIcon(QIcon(asset_path("app_icon.png")))
    chrome = WindowChrome(window, "win32")
    assert window.windowFlags() & Qt.CustomizeWindowHint
    assert window.windowFlags() & Qt.WindowCloseButtonHint
    window.resize(900, 640)
    window.show()
    qtbot.waitUntil(lambda: not window.windowHandle().flags() & Qt.WindowTitleHint)
    handle = window.windowHandle()
    for transition in (window.showMaximized, window.showNormal, window.hide, window.show):
        transition()
        QApplication.processEvents()
        chrome._sync_native()
        assert not handle.flags() & Qt.WindowTitleHint
        assert not handle.flags() & Qt.FramelessWindowHint
        for flag in (
            Qt.ExpandedClientAreaHint, Qt.CustomizeWindowHint, Qt.WindowSystemMenuHint,
            Qt.WindowMinimizeButtonHint, Qt.WindowMaximizeButtonHint, Qt.WindowCloseButtonHint,
        ):
            assert handle.flags() & flag
        assert handle.title() == window.windowTitle() == "BiliFlow · 星轨收藏站"
        assert not handle.icon().isNull() and not window.windowIcon().isNull()

    # QWidget can reapply its normalized flags when recreating/configuring the
    # window. The next show must clear the duplicate caption again.
    window.hide()
    handle.setFlags(Qt.WindowType(
        (int(handle.flags()) | int(Qt.WindowTitleHint))
        & ~int(Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
    ))
    window.show()
    qtbot.waitUntil(lambda: not handle.flags() & Qt.WindowTitleHint)
    dialog = QDialog(window)
    qtbot.addWidget(dialog)
    dialog.setWindowTitle("选择背景")
    dialog.show()
    assert dialog.windowHandle().flags() & Qt.WindowTitleHint
    assert not dialog.windowHandle().flags() & Qt.ExpandedClientAreaHint


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows")
def test_windows_native_caption_keeps_taskbar_icon_resize_and_system_menu(qtbot, qapp):
    if qapp.platformName() != "windows":
        pytest.skip("Requires the Windows Qt backend")
    from ctypes import wintypes

    window = QMainWindow()
    qtbot.addWidget(window)
    window.setWindowTitle("BiliFlow · 星轨收藏站")
    window.setWindowIcon(QIcon(asset_path("app_icon.png")))
    chrome = WindowChrome(window, "win32")
    window.show()
    qtbot.waitUntil(lambda: not window.windowHandle().flags() & Qt.WindowTitleHint)
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.GetSystemMenu.restype = wintypes.HMENU
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    hwnd = wintypes.HWND(int(window.winId()))
    for transition in (window.showMaximized, window.showNormal):
        transition()
        QApplication.processEvents()
        chrome._sync_native()
        style = user32.GetWindowLongW(hwnd, -16)
        # WS_THICKFRAME, WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX.
        assert style & 0x00040000 and style & 0x00080000
        assert style & 0x00020000 and style & 0x00010000
        assert not user32.GetWindowLongW(hwnd, -20) & 0x00000080  # WS_EX_TOOLWINDOW
        assert user32.GetSystemMenu(hwnd, False)
        assert user32.SendMessageW(hwnd, 0x007F, 1, 0)  # WM_GETICON / ICON_BIG
        assert not window.windowHandle().flags() & Qt.WindowTitleHint


@pytest.mark.parametrize("active", [False, True])
def test_expanded_caption_suppresses_legacy_activation_paint(qtbot, monkeypatch, active):
    from ctypes import wintypes
    from types import SimpleNamespace

    import bilibili_downloader.gui.window_chrome as module

    window = QMainWindow()
    qtbot.addWidget(window)
    chrome = WindowChrome(window, "win32")
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    message = wintypes.MSG(message=0x0086, wParam=int(active))  # WM_NCACTIVATE
    assert chrome.native_event(ctypes.addressof(message)) == 1

    # Other platforms must keep their normal activation handling.
    chrome.platform = "darwin"
    assert chrome.native_event(ctypes.addressof(message)) is None


@pytest.mark.parametrize("button", [0x01, 0x02])
def test_pressed_caption_buttons_are_left_to_qt(qtbot, monkeypatch, button):
    from ctypes import wintypes
    from types import SimpleNamespace

    import bilibili_downloader.gui.window_chrome as module

    class NativeFunction:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def get_rect(_hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 100, 0, 1000, 640
        return True

    user32 = SimpleNamespace(
        GetAsyncKeyState=NativeFunction(lambda key: 0x8000 if key == button else 0),
        GetDpiForWindow=NativeFunction(lambda _hwnd: 96),
        GetWindowRect=NativeFunction(get_rect),
    )
    window = QMainWindow()
    qtbot.addWidget(window)
    chrome = WindowChrome(window, "win32")
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    message = wintypes.MSG(message=0x0084, lParam=(16 << 16) | 920)  # WM_NCHITTEST
    assert chrome.native_event(ctypes.addressof(message)) is None


@pytest.mark.parametrize("dpi", [96, 144])
@pytest.mark.parametrize("on_button", [False, True])
def test_snap_hover_uses_client_origin_and_current_dpi(qtbot, monkeypatch, dpi, on_button):
    from ctypes import wintypes
    from types import SimpleNamespace

    import bilibili_downloader.gui.window_chrome as module

    class NativeFunction:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def get_rect(_hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 1200, 800
        return True

    def to_screen(_hwnd, pointer):
        point = ctypes.cast(pointer, ctypes.POINTER(wintypes.POINT)).contents
        point.x, point.y = -1280, 100
        return True

    metrics = {96: {32: 4, 92: 4, 4: 23}, 144: {32: 6, 92: 6, 4: 35}}
    user32 = SimpleNamespace(
        GetAsyncKeyState=NativeFunction(lambda _key: 0),
        GetDpiForWindow=NativeFunction(lambda _hwnd: dpi),
        GetClientRect=NativeFunction(get_rect),
        ClientToScreen=NativeFunction(to_screen),
        GetSystemMetricsForDpi=NativeFunction(lambda metric, actual_dpi: metrics[actual_dpi][metric]),
    )
    window = QMainWindow()
    qtbot.addWidget(window)
    chrome = WindowChrome(window, "win32")
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    # These points are in the maximize/close buttons on a negative-X monitor.
    x = (-150 if dpi == 96 else -185) if on_button else -90
    message = wintypes.MSG(message=0x0084, lParam=(110 << 16) | (x & 0xFFFF))
    assert chrome.native_event(ctypes.addressof(message)) == (9 if on_button else None)


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows")
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_native_blank_click_activation_and_caption_maximize(qtbot, qapp, workspace, mode):
    """Exercise real Win32 input; QTest.mouseClick bypasses WM_NCHITTEST."""
    import json
    from ctypes import wintypes
    from pathlib import Path
    from threading import Thread
    from time import sleep

    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor, QFont, QPalette

    from bilibili_downloader.gui.resources.styles import theme_palette
    from bilibili_downloader.gui.resources.theme import ThemeManager

    if qapp.platformName() != "windows":
        pytest.skip("Requires the Windows Qt backend")
    window = workspace
    previous = (QFont(qapp.font()), QPalette(qapp.palette()), qapp.styleSheet())
    properties = {key: qapp.property(key) for key in ("appearanceMode", "darkTheme", "colorTheme")}
    theme = ThemeManager(qapp, "star_trail")
    theme.setParent(window)
    theme.set_mode(mode)
    user32 = ctypes.windll.user32
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    user32.GetSystemMetricsForDpi.restype = ctypes.c_int
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class InputData(ctypes.Union):
        _fields_ = [("mi", MouseInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("data", InputData)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

    def click(x, y):
        assert user32.SetCursorPos(x, y)
        qtbot.wait(60)
        released = []

        def release_button():
            # DefWindowProc can run a modal caption-button tracking loop.
            # Release from outside the GUI thread so that loop can finish.
            sleep(0.12)
            up = Input(type=0, data=InputData(mi=MouseInput(dwFlags=0x0004)))
            released.append(user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(Input)))

        worker = Thread(target=release_button, daemon=True)
        worker.start()
        try:
            down = Input(type=0, data=InputData(mi=MouseInput(dwFlags=0x0002)))
            assert user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(Input)) == 1
            qtbot.wait(250)
        finally:
            worker.join(timeout=2)
        assert not worker.is_alive() and released == [1]

    def maximize_point():
        origin, rect = wintypes.POINT(), wintypes.RECT()
        assert user32.ClientToScreen(hwnd, ctypes.byref(origin))
        assert user32.GetClientRect(hwnd, ctypes.byref(rect))
        dpi = user32.GetDpiForWindow(hwnd)
        height = sum(user32.GetSystemMetricsForDpi(metric, dpi) for metric in (32, 92, 4))
        width = int(height * 1.5)
        return origin.x + rect.right - width * 3 // 2, origin.y + height // 2

    evidence = Path("build/ui-parity/chrome-regression")
    evidence.mkdir(parents=True, exist_ok=True)
    checks = []

    def assert_clear(stage):
        qtbot.wait(150)
        frame = window.frameGeometry()
        pixmap = window.screen().grabWindow(0, *frame.getRect())
        assert not pixmap.isNull()
        pixmap.save(str(evidence / f"{mode}-{stage}.png"))
        checks.append({"stage": stage, "frame": frame.getRect(),
                       "client": window.geometry().getRect(),
                       "qt_maximized": window.isMaximized(),
                       "native_maximized": bool(user32.IsZoomed(hwnd)),
                       "qwindow_flags": int(window.windowHandle().flags())})
        (evidence / f"{mode}.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        origin = window.mapToGlobal(QPoint(12, 6)) - frame.topLeft()
        image, dpr = pixmap.toImage(), pixmap.devicePixelRatio()
        expected = QColor(theme_palette(mode == "dark", "star_trail").sidebar)
        colors = [image.pixelColor(round((origin.x() + x) * dpr), round((origin.y() + y) * dpr))
                  for x in range(48) for y in range(12)]
        matching = sum(max(abs(c.red() - expected.red()), abs(c.green() - expected.green()),
                           abs(c.blue() - expected.blue())) <= 3 for c in colors)
        assert matching / len(colors) >= 0.98, f"Legacy caption repainted after {stage}"
        assert not window.windowHandle().flags() & Qt.WindowTitleHint

    try:
        window.resize(900, 640)
        window.move(window.screen().availableGeometry().topLeft() + QPoint(32, 40))
        window.show()
        window.raise_()
        window.activateWindow()
        qtbot.waitUntil(window.isActiveWindow)
        hwnd = wintypes.HWND(int(window.winId()))
        qtbot.waitUntil(lambda: not window.windowHandle().flags() & Qt.WindowTitleHint)
        # The reported trigger: click empty download workspace, not the header.
        origin = wintypes.POINT()
        assert user32.ClientToScreen(hwnd, ctypes.byref(origin))
        click(origin.x + 850, origin.y + 350)
        assert_clear("blank-click")
        user32.SendMessageW(hwnd, 0x0086, 0, 0)
        user32.SendMessageW(hwnd, 0x0086, 1, 0)
        assert_clear("activation")
        normal = window.geometry()
        click(*maximize_point())
        assert_clear("maximize-click")
        qtbot.waitUntil(lambda: window.isMaximized() and bool(user32.IsZoomed(hwnd)))
        assert_clear("maximized")
        click(*maximize_point())
        assert_clear("restore-click")
        qtbot.waitUntil(lambda: not window.isMaximized() and not user32.IsZoomed(hwnd))
        assert_clear("restored")
        assert window.geometry() == normal
        window.hide()
        window.show()
        window.activateWindow()
        qtbot.waitUntil(window.isActiveWindow)
        assert_clear("reshown")
    finally:
        if hasattr(qapp.styleHints(), "unsetColorScheme"):
            qapp.styleHints().unsetColorScheme()
        qapp.setFont(previous[0])
        qapp.setPalette(previous[1])
        qapp.setStyleSheet(previous[2])
        for key, value in properties.items():
            qapp.setProperty(key, value)
