"""Documented Win32 frame behaviour for a QWidget-painted Windows caption."""

import ctypes
import logging
from ctypes import wintypes

from bilibili_downloader.gui.widgets.caption_controls import caption_rects

logger = logging.getLogger(__name__)


def frame_hit_test(x, y, width, height, scale, border):
    """Physical client coordinates, independent of monitor origin or Qt fonts."""
    if not 0 <= x < width or not 0 <= y < height:
        return None
    left, right = x < border, x >= width - border
    top, bottom = y < border, y >= height - border
    if top:
        return 13 if left else 14 if right else 12
    if bottom:
        return 16 if left else 17 if right else 15
    if left or right:
        return 10 if left else 11
    for name, rect in caption_rects(width, scale).items():
        if rect.contains(x, y):
            return {"minimize": 8, "maximize": 9, "close": 20}[name]
    return None


class WindowsFrame:
    def __init__(self, chrome):
        self.chrome, self.window = chrome, chrome.window
        self.hwnd, self._dark, self.pressed = None, None, None
        self._configured_hwnd = None
        self.user32 = ctypes.windll.user32
        signatures = {
            "GetWindowLongPtrW": ([wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t),
            "SetWindowLongPtrW": ([wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
            "SetWindowPos": ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            "GetClientRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            "ScreenToClient": ([wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            "ClientToScreen": ([wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            "GetDpiForWindow": ([wintypes.HWND], wintypes.UINT),
            "GetSystemMetricsForDpi": ([ctypes.c_int, wintypes.UINT], ctypes.c_int),
            "SetCapture": ([wintypes.HWND], wintypes.HWND),
            "ReleaseCapture": ([], wintypes.BOOL),
            "TrackMouseEvent": ([ctypes.c_void_p], wintypes.BOOL),
            "MonitorFromWindow": ([wintypes.HWND, wintypes.DWORD], wintypes.HMONITOR),
            "GetMonitorInfoW": ([wintypes.HMONITOR, ctypes.c_void_p], wintypes.BOOL),
            "GetSystemMenu": ([wintypes.HWND, wintypes.BOOL], wintypes.HMENU),
            "TrackPopupMenu": ([wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p], wintypes.UINT),
            "PostMessageW": ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.user32, name)
            function.argtypes, function.restype = arguments, result

    def configure(self):
        hwnd, api = int(self.window.winId()), self.user32
        # Qt remains frameless. Windows retains native resize, taskbar,
        # system-menu and Snap styles without painting a second titlebar.
        style = api.GetWindowLongPtrW(hwnd, -16)
        required = 0x00C00000 | 0x00080000 | 0x00040000 | 0x00020000 | 0x00010000
        changed = self._configured_hwnd != hwnd or style & required != required
        self.hwnd = hwnd
        if changed:
            self._configured_hwnd = hwnd
            api.SetWindowLongPtrW(hwnd, -16, style | required)
            api.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
            try:
                margins = (ctypes.c_int * 4)(1, 1, 1, 1)
                ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(margins))
                corner = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(corner), ctypes.sizeof(corner))
            except (OSError, AttributeError):
                logger.debug("DWM frame decoration unavailable", exc_info=True)
        from PySide6.QtWidgets import QApplication

        dark = bool(QApplication.instance().property("darkTheme"))
        if changed or self._dark != dark:
            self._dark = dark
            try:
                value = wintypes.BOOL(dark)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(value), ctypes.sizeof(value))
            except (OSError, AttributeError):
                logger.debug("DWM dark frame unavailable", exc_info=True)

    def geometry(self, lparam, *, client=False):
        point = wintypes.POINT(ctypes.c_short(lparam & 0xFFFF).value,
                               ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        rect = wintypes.RECT()
        if not self.user32.GetClientRect(self.hwnd, ctypes.byref(rect)):
            return None
        if not client and not self.user32.ScreenToClient(self.hwnd, ctypes.byref(point)):
            return None
        scale = self.window.devicePixelRatioF()
        dpi = self.user32.GetDpiForWindow(self.hwnd) or 96
        border = 0 if self.window.isMaximized() or self.window.isFullScreen() else (
            self.user32.GetSystemMetricsForDpi(32, dpi) + self.user32.GetSystemMetricsForDpi(92, dpi)
        )
        return point.x, point.y, rect.right, rect.bottom, scale, border

    def action_at(self, geometry):
        if geometry is None:
            return None
        return {8: "minimize", 9: "maximize", 20: "close"}.get(frame_hit_test(*geometry))

    def _draggable(self, x, y, scale):
        from PySide6.QtWidgets import QAbstractButton, QLineEdit

        from bilibili_downloader.gui.widgets.components import WindowDragSurface

        child = self.window.childAt(round(x / scale), round(y / scale))
        while child is not None and child is not self.window:
            if isinstance(child, (QAbstractButton, QLineEdit)):
                return False
            if isinstance(child, WindowDragSurface):
                return True
            child = child.parentWidget()
        return False

    def cancel_press(self):
        self.pressed = None
        self.chrome.controls.reset()

    def _track_leave(self):
        class TrackMouse(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("hwnd", wintypes.HWND), ("hover", wintypes.DWORD)]

        tracking = TrackMouse(ctypes.sizeof(TrackMouse), 0x12, self.hwnd, 0)
        self.user32.TrackMouseEvent(ctypes.byref(tracking))

    def _max_bounds(self, lparam):
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

        class MinMax(ctypes.Structure):
            _fields_ = [(name, wintypes.POINT) for name in
                        ("reserved", "maximum", "position", "minimum_track", "maximum_track")]

        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = self.user32.MonitorFromWindow(self.hwnd, 2)
        if not monitor or not self.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        bounds = MinMax.from_address(lparam)
        bounds.position.x = info.work.left - info.monitor.left
        bounds.position.y = info.work.top - info.monitor.top
        bounds.maximum.x = info.work.right - info.work.left
        bounds.maximum.y = info.work.bottom - info.work.top
        dpr = self.window.devicePixelRatioF()
        bounds.minimum_track.x = round(self.window.minimumWidth() * dpr)
        bounds.minimum_track.y = round(self.window.minimumHeight() * dpr)
        return 0

    def system_menu(self, x, y):
        menu = self.user32.GetSystemMenu(self.hwnd, False)
        if menu:
            command = self.user32.TrackPopupMenu(menu, 0x0102, x, y, 0, self.hwnd, None)
            if command:
                self.user32.PostMessageW(self.hwnd, 0x0112, command, 0)

    def event(self, msg):
        message = msg.message
        if message == 0x0083:  # WM_NCCALCSIZE: full client frame in both forms.
            return 0
        if message in (0x0085, 0x0086):  # WM_NCPAINT / WM_NCACTIVATE
            return 1
        if message == 0x0024:
            return self._max_bounds(msg.lParam)
        if message == 0x02E0:  # Qt handles the suggested DPI geometry first.
            self.chrome.schedule_sync()
            return None
        if message in (0x001F, 0x0215):  # WM_CANCELMODE / WM_CAPTURECHANGED
            self.cancel_press()
            return None
        if message in (0x02A2, 0x02A3):
            self.chrome.controls.hover(None)
            return None
        if self.window.isFullScreen():
            return None
        if message == 0x0084:
            geometry = self.geometry(msg.lParam)
            if geometry is not None:
                hit = frame_hit_test(*geometry)
                if hit is not None:
                    return hit
                if self._draggable(geometry[0], geometry[1], geometry[4]):
                    return 2  # HTCAPTION: native move, double-click and context menu.
            return None
        if message == 0x00A0 or message == 0x0200 and self.pressed:
            action = self.action_at(self.geometry(msg.lParam, client=message == 0x0200))
            self.chrome.controls.hover(action)
            if self.pressed:
                self.chrome.controls.buttons[self.pressed].setDown(action == self.pressed)
            if message == 0x00A0:
                self._track_leave()
            # The default procedure must receive NC hover for the Snap flyout.
            return None
        if message == 0x00A1:
            action = self.action_at(self.geometry(msg.lParam))
            if action and self.window.isEnabled():
                self.pressed = action
                self.chrome.controls.hover(action)
                self.chrome.controls.buttons[action].setDown(True)
                self.user32.SetCapture(self.hwnd)
                return 0
        if message in (0x00A2, 0x0202) and self.pressed:
            action = self.action_at(self.geometry(msg.lParam, client=message == 0x0202))
            pressed = self.pressed
            self.cancel_press()
            self.user32.ReleaseCapture()
            if action == pressed:
                self.chrome.controls.buttons[pressed].click()
            return 0
        if message == 0x00A4:
            self.system_menu(ctypes.c_short(msg.lParam & 0xFFFF).value,
                             ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value)
            return 0
        if message == 0x0104 and msg.wParam == 0x20:  # Alt+Space
            point = wintypes.POINT(0, round(32 * self.window.devicePixelRatioF()))
            self.user32.ClientToScreen(self.hwnd, ctypes.byref(point))
            self.system_menu(point.x, point.y)
            return 0
        return None
