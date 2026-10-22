"""Expanded native window chrome, keeping platform window controls intact."""

import ctypes
import logging
import sys

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

logger = logging.getLogger(__name__)


class WindowChrome(QObject):
    def __init__(self, window, platform):
        super().__init__(window)
        self.window = window
        self.platform = platform
        self._caption_clip = None
        self._snap_hover = False
        self.expanded = platform in ("darwin", "win32") and hasattr(
            Qt, "ExpandedClientAreaHint"
        )
        if self.expanded:
            flags = (
                window.windowFlags()
                | Qt.ExpandedClientAreaHint
                | Qt.NoTitleBarBackgroundHint
            )
            if platform == "win32":
                flags |= (
                    Qt.CustomizeWindowHint
                    | Qt.WindowSystemMenuHint
                    | Qt.WindowMinimizeButtonHint
                    | Qt.WindowMaximizeButtonHint
                    | Qt.WindowCloseButtonHint
                )
            window.setWindowFlags(flags)
            window.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
        window.installEventFilter(self)

    @property
    def header_margins(self):
        if not self.expanded:
            return (24, 12, 24, 12)
        if self.platform == "darwin":
            return (88, 12, 24, 12)
        return (24, 12, 164, 12)

    def eventFilter(self, target, event):
        sync_events = (
            QEvent.Show,
            QEvent.WinIdChange,
            QEvent.WindowStateChange,
        )
        if self.platform == "win32":
            sync_events += (QEvent.Resize, QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange)
        if self.expanded and event.type() in sync_events:
            # Clear the Windows caption before the first exposed frame.
            if self.platform == "win32" and event.type() == QEvent.Show:
                self._sync_native()
            QTimer.singleShot(0, self, self._sync_native)
        return False

    def _sync_native(self):
        if not isValid(self.window):
            return
        if self.expanded and self.platform == "win32":
            self._sync_windows_caption()
            return
        if (
            sys.platform != "darwin"
            or self.platform != "darwin"
            or QApplication.platformName() != "cocoa"
        ):
            return
        try:
            # QWidget.winId() is an NSView on Cocoa. Keep the real window title
            # for accessibility/Dock while hiding its duplicate visual caption.
            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
            get_window = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(address)
            native = get_window(
                int(self.window.winId()), objc.sel_registerName(b"window")
            )
            if native:
                set_visibility = ctypes.CFUNCTYPE(
                    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long
                )(address)
                set_visibility(native, objc.sel_registerName(b"setTitleVisibility:"), 1)
        except (OSError, AttributeError):
            logger.debug("Native caption visibility unavailable", exc_info=True)

    def _sync_windows_caption(self):
        handle = self.window.windowHandle()
        if handle is not None:
            # QWidget.adjustFlags() adds WindowTitleHint back whenever caption
            # buttons are requested. Set the QWindow flag instead: Qt's Windows
            # expanded-titlebar renderer then omits BOTH the icon and caption,
            # while keeping the real title, icon, system menu and buttons.
            # Use integer masking: Python's enum inversion can omit high flags
            # such as CustomizeWindowHint/WindowCloseButtonHint on Windows.
            flags = Qt.WindowType((int(handle.flags()) | int(
                Qt.CustomizeWindowHint | Qt.WindowSystemMenuHint
                | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                | Qt.WindowCloseButtonHint
            )) & ~int(Qt.WindowTitleHint))
            if self._clip_windows_caption(handle):
                # Qt 6.11 hands a straight-alpha hover image to the layered
                # window compositor. White hover pixels saturate on Windows
                # in dark mode. An opaque caption base avoids that conversion;
                # the native region limits it to the existing three buttons.
                flags = Qt.WindowType(int(flags) & ~int(Qt.NoTitleBarBackgroundHint))
            else:
                flags |= Qt.NoTitleBarBackgroundHint
            if handle.flags() != flags:
                handle.setFlags(flags)
            if sys.platform == "win32" and QApplication.platformName() == "windows" and self.window.isVisible():
                # Qt 6.11's separate expanded-titlebar layer repaints on native
                # WM_PAINT/hit testing, but a widget palette change only updates
                # the backing store. Invalidate the native window so the caption
                # glyphs immediately follow light/dark mode too.
                self._invalidate_windows_caption()

    def _invalidate_windows_caption(self):
        if sys.platform != "win32" or QApplication.platformName() != "windows":
            return
        from ctypes import wintypes

        invalidate = ctypes.windll.user32.InvalidateRect
        invalidate.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.BOOL]
        invalidate.restype = wintypes.BOOL
        invalidate(wintypes.HWND(int(self.window.winId())), None, False)

    def _set_snap_hover(self, hovered):
        if self._snap_hover != hovered:
            self._snap_hover = hovered
            # Our HTMAXBUTTON result skips Qt's normal hit-test repaint. One
            # invalidation per enter/leave keeps its layered glyph/material in
            # sync, without repainting continuously while the pointer rests.
            self._invalidate_windows_caption()

    def _clip_windows_caption(self, handle):
        """Keep Qt's opaque caption material inside its native button bounds.

        This is a Qt Windows backend workaround, not a replacement caption:
        Qt/Windows still own glyphs, input, the system menu and Snap handling.
        If the backend changes, retain the transparent expanded titlebar.
        """
        if sys.platform != "win32" or QApplication.platformName() != "windows":
            return False
        from ctypes import wintypes

        try:
            user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
            user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowExW.restype = wintypes.HWND
            user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetClientRect.restype = wintypes.BOOL
            user32.GetDpiForWindow.argtypes = [wintypes.HWND]
            user32.GetDpiForWindow.restype = wintypes.UINT
            user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
            user32.GetSystemMetricsForDpi.restype = ctypes.c_int
            user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
            user32.SetWindowRgn.restype = ctypes.c_int
            gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
            gdi32.CreateRectRgn.restype = wintypes.HRGN
            gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            gdi32.DeleteObject.restype = wintypes.BOOL
            hwnd = wintypes.HWND(int(handle.winId()))
            caption = user32.FindWindowExW(hwnd, None, "_q_titlebar", None)
            rect = wintypes.RECT()
            if not caption or not user32.GetClientRect(caption, ctypes.byref(rect)):
                return False
            dpi = user32.GetDpiForWindow(hwnd) or 96
            height = sum(user32.GetSystemMetricsForDpi(metric, dpi) for metric in (32, 92, 4))
            width = rect.right - rect.left
            button_width = int(height * 1.5)
            if width <= 0 or height <= 0:
                return False
            bounds = (caption, width, height, button_width)
            if self._caption_clip == bounds:
                return True
            region = gdi32.CreateRectRgn(max(0, width - 3 * button_width), 0, width, height)
            if not region:
                return False
            if not user32.SetWindowRgn(caption, region, True):
                # Windows owns the region only after SetWindowRgn succeeds.
                gdi32.DeleteObject(region)
                return False
            self._caption_clip = bounds
            return True
        except (OSError, AttributeError):
            logger.debug("Native caption clipping unavailable", exc_info=True)
            return False

    def native_event(self, message):
        """Keep legacy caption painting out of the expanded client area."""
        if not self.expanded or sys.platform != "win32" or self.platform != "win32":
            return None
        from ctypes import wintypes

        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0086:  # WM_NCACTIVATE
            # Qt 6.11 suppresses this default caption paint for frameless
            # windows, but not expanded windows without WindowTitleHint.
            # Let WM_ACTIVATE continue to manage focus; only suppress the
            # legacy non-client paint over Qt's separate titlebar layer.
            return 1
        if msg.message == 0x02A2:  # WM_NCMOUSELEAVE
            self._set_snap_hover(False)
            return None
        if msg.message != 0x0084 or self.window.isFullScreen():  # WM_NCHITTEST
            return None
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        if any(user32.GetAsyncKeyState(button) & 0x8000 for button in (0x01, 0x02)):
            # Qt's expanded-titlebar hit test performs maximize/restore on
            # press. Returning HTMAXBUTTON here bypasses that action. Only
            # supply the idle hover target needed by Windows 11 Snap.
            self._set_snap_hover(False)
            return None
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
        user32.GetSystemMetricsForDpi.restype = ctypes.c_int
        rect = wintypes.RECT()
        origin = wintypes.POINT()
        hwnd = wintypes.HWND(int(self.window.winId()))
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return None
        dpi = user32.GetDpiForWindow(hwnd) or 96
        # Match Qt's expanded-titlebar metrics in physical client pixels,
        # including the per-monitor frame and padded border at this DPI.
        height = sum(user32.GetSystemMetricsForDpi(metric, dpi) for metric in (32, 92, 4))
        width = int(height * 1.5)
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        hovered = (
            origin.x + rect.right - 2 * width <= x < origin.x + rect.right - width
            and origin.y <= y < origin.y + height
        )
        self._set_snap_hover(hovered)
        if hovered:
            return 9  # HTMAXBUTTON; hover only, for the Windows Snap flyout.
        return None
