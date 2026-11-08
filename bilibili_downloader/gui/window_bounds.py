"""Keep transient windows inside the available desktop, in logical pixels."""

from PySide6.QtCore import QEvent, QObject, QRect, QSize, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog
from shiboken6 import isValid

from bilibili_downloader.gui.window_state import fit_rect


class ScreenBounds(QObject):
    def __init__(self, window, minimum=QSize(), *, available_geometry=None):
        super().__init__(window)
        self.window, self.minimum = window, minimum
        self.available_geometry = available_geometry
        self._queued = False
        self._screen = None
        self._handle = None
        window.installEventFilter(self)

    def schedule(self, *_args):
        if not self._queued:
            self._queued = True
            QTimer.singleShot(0, self, self.fit)

    def fit(self):
        self._queued = False
        window = self.window
        if not window.isVisible():
            return
        # Headless renderers expose an artificial 800px desktop. Their caller
        # owns the canvas; an explicit provider exercises bounds in tests.
        if self.available_geometry is None and QGuiApplication.platformName() in {"offscreen", "minimal"}:
            return
        handle = window.windowHandle()
        if handle is not None and self._handle is not handle:
            self._handle = handle
            handle.screenChanged.connect(self.schedule)
        screen = window.screen()
        if screen is None:
            return
        if screen is not self._screen:
            if self._screen is not None and isValid(self._screen):
                self._screen.availableGeometryChanged.disconnect(self.schedule)
            self._screen = screen
            screen.availableGeometryChanged.connect(self.schedule)
        available = self.available_geometry() if self.available_geometry else screen.availableGeometry()
        frame = window.frameGeometry()
        extra = frame.size() - window.size()
        limit = QSize(max(1, available.width() - max(0, extra.width())),
                      max(1, available.height() - max(0, extra.height())))
        minimum = self.minimum.boundedTo(limit)
        if window.minimumSize() != minimum:
            window.setMinimumSize(minimum)
        if isinstance(window, QDialog) and window.maximumSize() != limit:
            window.setMaximumSize(limit)
        # Cocoa reports a dialog at its maximumSize as maximized, even when
        # merely constrained to a smaller desktop. It still needs positioning.
        if (window.isMaximized() and not isinstance(window, QDialog)) or window.isFullScreen() or window.isMinimized():
            return
        target = fit_rect(QRect(frame.topLeft(), window.size()), available, extra)
        if window.size() != target.size():
            window.resize(target.size())
        if window.frameGeometry().topLeft() != target.topLeft():
            window.move(target.topLeft())

    def eventFilter(self, target, event):
        if event.type() in (QEvent.Show, QEvent.Move, QEvent.Resize, QEvent.ScreenChangeInternal,
                            QEvent.LayoutRequest, QEvent.WindowStateChange):
            self.schedule()
        return False
