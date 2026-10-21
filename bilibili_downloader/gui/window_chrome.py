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
        if self.expanded and event.type() in (
            QEvent.Show,
            QEvent.WinIdChange,
            QEvent.WindowStateChange,
        ):
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
            geometry = handle.geometry()
            changed = handle.flags() != flags
            if changed:
                handle.setFlags(flags)
            # The Qt flag controls its caption painter. Keep the Win32 frame
            # style so native resize margins, restore geometry and Snap retain
            # their original metrics (Qt caches these for expanded windows).
            frame_changed = self._keep_windows_frame(handle)
            if (changed or frame_changed) and not self.window.isMaximized() and not self.window.isFullScreen():
                handle.setGeometry(geometry)

    def _keep_windows_frame(self, handle):
        if sys.platform != "win32" or QApplication.platformName() != "windows" or self.window.isFullScreen():
            return False
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = wintypes.LONG
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        user32.SetWindowLongW.restype = wintypes.LONG
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        hwnd = wintypes.HWND(int(handle.winId()))
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        if style & 0x00C00000 == 0x00C00000:  # WS_CAPTION
            return False
        user32.SetWindowLongW(hwnd, -16, style | 0x00C00000)
        # SWP_NOSIZE | NOMOVE | NOZORDER | NOACTIVATE | FRAMECHANGED.
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
        return True

    def native_event(self, message):
        """Expose the native maximize hit target on hover for Windows Snap."""
        if not self.expanded or sys.platform != "win32" or self.platform != "win32":
            return None
        from ctypes import wintypes

        msg = wintypes.MSG.from_address(int(message))
        if msg.message != 0x0084 or self.window.isFullScreen():  # WM_NCHITTEST
            return None
        user32 = ctypes.windll.user32
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        rect = wintypes.RECT()
        hwnd = wintypes.HWND(int(self.window.winId()))
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        dpi = user32.GetDpiForWindow(hwnd) or 96
        height = round(32 * dpi / 96)
        width = round(height * 1.5)
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        if (
            rect.right - 2 * width <= x < rect.right - width
            and rect.top <= y < rect.top + height
        ):
            return 9  # HTMAXBUTTON; Windows owns the Snap flyout and resize action.
        return None
