"""Platform window identity with a shared, client-painted Windows caption."""

import ctypes
import logging
import sys

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.caption_controls import CaptionControls

logger = logging.getLogger(__name__)


class WindowChrome(QObject):
    def __init__(self, window, platform):
        super().__init__(window)
        self.window, self.platform = window, platform
        self.controls, self._native = None, None
        self._sync_pending = False
        self.expanded = platform == "win32" or (
            platform == "darwin" and hasattr(Qt, "ExpandedClientAreaHint")
        )
        if platform == "win32":
            flags = int(window.windowFlags()) | int(
                Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
                | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
            )
            # QWidget normalizes CustomizeWindowHint + caption-button hints by
            # removing FramelessWindowHint. Native styles are managed below.
            flags &= ~int(Qt.CustomizeWindowHint)
            for name in ("ExpandedClientAreaHint", "NoTitleBarBackgroundHint"):
                flags &= ~int(getattr(Qt, name, 0))
            window.setWindowFlags(Qt.WindowType(flags))
            self.controls = CaptionControls(window)
        elif self.expanded:
            window.setWindowFlags(window.windowFlags() | Qt.ExpandedClientAreaHint | Qt.NoTitleBarBackgroundHint)
        if self.expanded and hasattr(Qt, "WA_ContentsMarginsRespectsSafeArea"):
            window.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
        window.installEventFilter(self)

    @property
    def header_margins(self):
        if not self.expanded:
            return (24, 12, 24, 12)
        if self.platform == "darwin":
            return (88, 12, 24, 12)
        return (24, 12, 24 + 3 * UI_METRICS.caption_width, 12)

    def schedule_sync(self):
        if not self._sync_pending:
            self._sync_pending = True
            QTimer.singleShot(0, self, self._sync_native)

    def eventFilter(self, target, event):
        kind = event.type()
        if self.controls and kind in (QEvent.WindowDeactivate, QEvent.Hide):
            self.controls.reset()
            if self._native:
                self._native.cancel_press()
        if self.expanded and kind in (
            QEvent.Show, QEvent.WinIdChange, QEvent.WindowStateChange, QEvent.Resize,
            QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange,
            QEvent.ActivationChange, QEvent.DevicePixelRatioChange,
        ):
            if self.controls:
                self.controls.sync()
            if kind == QEvent.Show:
                self._sync_native()
            self.schedule_sync()
        return False

    def _sync_native(self):
        self._sync_pending = False
        if not isValid(self.window):
            return
        if self.controls:
            self.controls.sync()
            if sys.platform == "win32" and QApplication.platformName() == "windows":
                from bilibili_downloader.gui.windows_frame import WindowsFrame

                if self._native is None:
                    self._native = WindowsFrame(self)
                self._native.configure()
            return
        if not self.expanded or sys.platform != "darwin" or self.platform != "darwin" or QApplication.platformName() != "cocoa":
            return
        try:
            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
            get_window = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
            native = get_window(int(self.window.winId()), objc.sel_registerName(b"window"))
            if native:
                set_visibility = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(address)
                set_visibility(native, objc.sel_registerName(b"setTitleVisibility:"), 1)
        except (OSError, AttributeError):
            logger.debug("Native caption visibility unavailable", exc_info=True)

    def native_event(self, message):
        if self.platform != "win32" or sys.platform != "win32" or QApplication.platformName() != "windows":
            return None
        from ctypes import wintypes

        msg = wintypes.MSG.from_address(int(message))
        if self._native is None:
            from bilibili_downloader.gui.windows_frame import WindowsFrame

            self._native = WindowsFrame(self)
        self._native.hwnd = msg.hWnd
        return self._native.event(msg)

    def show_native(self, command):
        if self.platform != "win32" or sys.platform != "win32" or QApplication.platformName() != "windows" or self.window.isFullScreen():
            return False
        # QWidget still owns visibility, lifecycle and focus. Only the native
        # state transition bypasses Qt's frameless MoveWindow emulation.
        self.window.show()
        self._sync_native()
        self._native.show_window(command)
        return True

    def placement_state(self):
        return self._native.placement_state() if self._native and self._native.hwnd else None
