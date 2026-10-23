"""Native desktop compositor and real Windows input regressions."""

import ctypes
import sys

import pytest
from PySide6.QtCore import Qt

from tests.test_workspaces import workspace as workspace


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows")
@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
def test_native_blank_click_activation_and_caption_maximize(qtbot, qapp, workspace, mode, theme_id):
    """Exercise real Win32 input; QTest.mouseClick bypasses WM_NCHITTEST."""
    import json
    import os
    from ctypes import wintypes
    from pathlib import Path
    from threading import Thread
    from time import sleep
    from types import SimpleNamespace

    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QFont, QPalette

    from bilibili_downloader.gui.resources.styles import contrast_ratio, theme_palette
    from bilibili_downloader.gui.resources.theme import ThemeManager
    from bilibili_downloader.gui.widgets.caption_controls import caption_rects

    if qapp.platformName() != "windows":
        pytest.skip("Requires the Windows Qt backend")
    window = workspace
    previous = (QFont(qapp.font()), QPalette(qapp.palette()), qapp.styleSheet())
    properties = {key: qapp.property(key) for key in ("appearanceMode", "darkTheme", "colorTheme")}
    theme = ThemeManager(qapp, theme_id)
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
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    def ensure_foreground():
        # A new Python process can bring the hosted runner's terminal above
        # Qt's window. isActiveWindow() alone can briefly retain stale state;
        # verify Win32 foreground ownership before real input/compositor grabs.
        window.raise_()
        window.activateWindow()
        if user32.GetForegroundWindow() != hwnd.value:
            # A second GUI process (the 150% run) can inherit the console's
            # foreground lock. Real Alt input releases it, as documented by
            # LockSetForegroundWindow; keep this inside the input test harness.
            keys = (Input * 2)(
                Input(type=1, data=InputData(ki=KeyboardInput(wVk=0x12))),
                Input(type=1, data=InputData(ki=KeyboardInput(wVk=0x12, dwFlags=0x0002))),
            )
            assert user32.SendInput(2, keys, ctypes.sizeof(Input)) == 2
            qtbot.wait(30)

        def acquired():
            user32.SetForegroundWindow(hwnd)
            return user32.GetForegroundWindow() == hwnd.value

        qtbot.waitUntil(acquired)

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class KeyboardInput(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class InputData(ctypes.Union):
        _fields_ = [("mi", MouseInput), ("ki", KeyboardInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("data", InputData)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

    def click(x, y):
        ensure_foreground()
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

    def caption_bounds():
        origin, rect = wintypes.POINT(), wintypes.RECT()
        assert user32.ClientToScreen(hwnd, ctypes.byref(origin))
        assert user32.GetClientRect(hwnd, ctypes.byref(rect))
        height = round(32 * window.devicePixelRatioF())
        width = round(46 * window.devicePixelRatioF())
        return origin.x, origin.y, rect.right, height, width

    def maximize_point():
        x, y, right, height, width = caption_bounds()
        return x + right - width * 3 // 2, y + height // 2

    def drag_right_edge():
        ensure_foreground()
        origin, rect = wintypes.POINT(), wintypes.RECT()
        assert user32.ClientToScreen(hwnd, ctypes.byref(origin))
        assert user32.GetClientRect(hwnd, ctypes.byref(rect))
        x, y = origin.x + rect.right - 2, origin.y + rect.bottom // 2
        assert user32.SetCursorPos(x, y)
        completed = []
        def finish():
            sleep(.12)
            user32.SetCursorPos(x + 40, y)
            sleep(.12)
            up = Input(type=0, data=InputData(mi=MouseInput(dwFlags=0x0004)))
            completed.append(user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(Input)))
        worker = Thread(target=finish, daemon=True)
        worker.start()
        before = window.width()
        down = Input(type=0, data=InputData(mi=MouseInput(dwFlags=0x0002)))
        assert user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(Input)) == 1
        qtbot.wait(350)
        worker.join(timeout=2)
        assert not worker.is_alive() and completed == [1]
        qtbot.waitUntil(lambda: window.width() > before)
        window.resize(900, 640)

    evidence = Path("build/ui-parity/chrome-regression") / f"scale-{os.environ.get('QT_SCALE_FACTOR', '1')}"
    evidence.mkdir(parents=True, exist_ok=True)
    checks = []

    def assert_clear(stage):
        ensure_foreground()
        qtbot.wait(150)
        frame = window.frameGeometry()
        pixmap = window.screen().grabWindow(0, *frame.getRect())
        assert not pixmap.isNull()
        pixmap.save(str(evidence / f"{theme_id}-{mode}-{stage}.png"))
        checks.append({"stage": stage, "frame": frame.getRect(),
                       "client": window.geometry().getRect(),
                       "qt_maximized": window.isMaximized(),
                       "native_maximized": bool(user32.IsZoomed(hwnd)),
                       "qwindow_flags": int(window.windowHandle().flags())})
        (evidence / f"{theme_id}-{mode}.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        origin = window.mapToGlobal(QPoint(12, 6)) - frame.topLeft()
        image, dpr = pixmap.toImage(), pixmap.devicePixelRatio()
        expected = QColor(theme_palette(mode == "dark", theme_id).sidebar)
        colors = [image.pixelColor(round((origin.x() + x) * dpr), round((origin.y() + y) * dpr))
                  for x in range(48) for y in range(12)]
        matching = sum(max(abs(c.red() - expected.red()), abs(c.green() - expected.green()),
                           abs(c.blue() - expected.blue())) <= 3 for c in colors)
        assert matching / len(colors) >= 0.98, f"Legacy caption repainted after {stage}"
        for index in range(3):
            sample = window.mapToGlobal(QPoint(window.width() - 138 + index * 46 + 3, 12)) - frame.topLeft()
            actual = image.pixelColor(round(sample.x() * dpr), round(sample.y() * dpr))
            expected = QColor(theme_palette(mode == "dark", theme_id).background)
            assert max(abs(a - b) for a, b in zip(actual.getRgb()[:3], expected.getRgb()[:3])) <= 2
        assert window.windowHandle().flags() & Qt.FramelessWindowHint

    def assert_hover(stage):
        # Capture the desktop compositor: QWidget.grab() misses Qt's separate
        # layered titlebar HWND, which is where this regression occurs.
        assert not window.windowHandle().flags() & Qt.ExpandedClientAreaHint
        ensure_foreground()
        x, y, right, height, width = caption_bounds()
        for button, rect in caption_rects(right, window.devicePixelRatioF()).items():
            left, width, height = x + rect.left(), rect.width(), rect.height()
            assert user32.SetCursorPos(left + width // 2, y + height // 2)
            qtbot.wait(100)
            screen = window.screen()
            pixmap = screen.grabWindow(0)
            dpr = pixmap.devicePixelRatio()
            # Win32 coordinates are physical; QScreen's origin is logical.
            origin = screen.geometry().topLeft()
            image = pixmap.toImage().copy(QRect(
                left - round(origin.x() * dpr), y - round(origin.y() * dpr), width, height,
            ))
            assert image.save(str(evidence / f"{theme_id}-{mode}-{stage}-{button}-hover.png"))
            # The button interior must be a neutral material plus a contrasting
            # glyph. Straight-alpha white hover pixels used to saturate this
            # entire area, leaving the white glyph invisible.
            colors = [image.pixelColor(px, py)
                      for px in range(4, width - 4) for py in range(4, height - 4)]
            background = sorted(colors, key=lambda c: c.lightness())[len(colors) // 2]
            palette = theme_palette(mode == "dark", theme_id)
            expected = palette.caption_close_hover if button == "close" else palette.caption_hover
            assert max(abs(a - b) for a, b in zip(background.getRgb()[:3], QColor(expected).getRgb()[:3])) <= 2
            foreground = [c for c in colors if contrast_ratio(c.name(), background.name()) >= 3.0]
            assert len(foreground) >= 8, (stage, button, len(foreground))
            assert contrast_ratio(foreground[0].name(), background.name()) >= 3.0
        assert user32.SetCursorPos(x + 300, y + 200)

    try:
        window.resize(900, 640)
        # Keep the entire 900x640 client on the CI desktop at 150% Qt scale.
        window.move(window.screen().availableGeometry().topLeft() + QPoint(24, 8))
        window.show()
        window.raise_()
        window.activateWindow()
        qtbot.waitUntil(window.isActiveWindow)
        hwnd = wintypes.HWND(int(window.winId()))
        qtbot.waitUntil(lambda: bool(window.windowHandle().flags() & Qt.FramelessWindowHint))
        style = user32.GetWindowLongPtrW(hwnd, -16)
        assert all(style & flag for flag in (0x00040000, 0x00080000, 0x00020000, 0x00010000))
        assert user32.GetSystemMenu(hwnd, False)
        # The reported trigger: click empty download workspace, not the header.
        origin = wintypes.POINT()
        assert user32.ClientToScreen(hwnd, ctypes.byref(origin))
        click(origin.x + 850, origin.y + 350)
        assert_clear("blank-click")
        user32.SendMessageW(hwnd, 0x0086, 0, 0)
        user32.SendMessageW(hwnd, 0x0086, 1, 0)
        assert_clear("activation")
        assert_hover("windowed")
        normal = window.geometry()
        click(*maximize_point())
        assert_clear("maximize-click")
        qtbot.waitUntil(lambda: window.isMaximized() and bool(user32.IsZoomed(hwnd)))
        assert_clear("maximized")
        assert_hover("maximized")
        click(*maximize_point())
        assert_clear("restore-click")
        qtbot.waitUntil(lambda: not window.isMaximized() and not user32.IsZoomed(hwnd))
        assert_clear("restored")
        assert_hover("restored")
        assert window.geometry() == normal
        drag_right_edge()
        assert_clear("edge-resize")
        x, y, right, height, width = caption_bounds()
        click(x + right - width * 5 // 2, y + height // 2)
        qtbot.waitUntil(window.isMinimized)
        window.showNormal()
        ensure_foreground()
        assert_clear("minimize-restored")
        window.hide()
        window.show()
        window.activateWindow()
        qtbot.waitUntil(window.isActiveWindow)
        assert_clear("reshown")
        closed = []
        previous_lifecycle = window._lifecycle
        def close_to_tray():
            closed.append(True)
            window.hide()
        window._lifecycle = SimpleNamespace(platform="win32", close_window=close_to_tray)
        try:
            x, y, right, height, width = caption_bounds()
            click(x + right - width // 2, y + height // 2)
            qtbot.waitUntil(window.isHidden)
            assert closed == [True] and not window._quit_requested
        finally:
            window._lifecycle = previous_lifecycle
    finally:
        if hasattr(qapp.styleHints(), "unsetColorScheme"):
            qapp.styleHints().unsetColorScheme()
        qapp.setFont(previous[0])
        qapp.setPalette(previous[1])
        qapp.setStyleSheet(previous[2])
        for key, value in properties.items():
            qapp.setProperty(key, value)
