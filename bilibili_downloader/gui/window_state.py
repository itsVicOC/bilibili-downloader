"""Private desktop placement, independent of business settings and drafts."""

import base64
import json
import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from shiboken6 import isValid

from bilibili_downloader.core.update_protocol import atomic_json

logger = logging.getLogger(__name__)


def fit_rect(rect, available, frame=QSize()):
    """Fit client geometry, including native frame space, in logical pixels."""
    width = min(max(1, rect.width()), max(1, available.width() - max(0, frame.width())))
    height = min(max(1, rect.height()), max(1, available.height() - max(0, frame.height())))
    return QRect(
        max(available.left(), min(rect.x(), available.right() - width + 1 - max(0, frame.width()))),
        max(available.top(), min(rect.y(), available.bottom() - height + 1 - max(0, frame.height()))),
        width, height,
    )


def choose_screen(screens, name, rect):
    matching = [screen for screen in screens if screen.name() == name]
    candidates = matching or screens
    if not candidates:
        return None
    def overlap(screen):
        intersection = screen.availableGeometry().intersected(rect)
        return intersection.width() * intersection.height() if not intersection.isEmpty() else 0
    best = max(candidates, key=overlap)
    return best if matching or overlap(best) else QGuiApplication.primaryScreen() or best


class WindowStateStore(QObject):
    """Capture settled normal geometry; replay maximization via native chrome."""

    def __init__(self, window, path):
        super().__init__(window)
        self.window = window
        self.path = Path(path)
        self._ready = False
        self._restoring = False
        self._normal = None
        self._geometry = ""
        self._maximized = False
        self._screen_name = ""
        self._available = QRect()
        self._last_saved = None
        self._warned = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.flush)
        window.installEventFilter(self)
        app = QGuiApplication.instance()
        app.screenRemoved.connect(self._screens_changed)
        app.screenAdded.connect(self._connect_screen)
        app.aboutToQuit.connect(self.flush)
        for screen in app.screens():
            self._connect_screen(screen)

    def _connect_screen(self, screen):
        screen.availableGeometryChanged.connect(self._screens_changed)

    def _read(self):
        try:
            if self.path.stat().st_size > 65536:
                return None
            value = json.loads(self.path.read_text("utf-8"))
            rect = value["normal_rect"]
            if (value["version"] != 1 or type(value["maximized"]) is not bool
                    or not isinstance(rect, list) or len(rect) != 4
                    or any(type(number) is not int or abs(number) > 1000000 for number in rect)
                    or rect[2] <= 0 or rect[3] <= 0):
                return None
            base64.b64decode(value["geometry"], validate=True)
            if not isinstance(value["screen"], str):
                return None
            return value
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def show_initial(self):
        self._restoring = True
        value = self._read()
        screens = QGuiApplication.screens()
        rect = QRect(*value["normal_rect"]) if value else QRect(0, 0, 1320, 860)
        screen = choose_screen(screens, value["screen"] if value else "", rect)
        if screen:
            self._set_minimum(screen)
            self._available = screen.availableGeometry()
        if value:
            self.window.restoreGeometry(QByteArray(base64.b64decode(value["geometry"])))
            # The blob is captured only in normal state. Keep explicit state
            # authoritative even if a future/foreign blob includes flags.
            self.window.setWindowState(Qt.WindowNoState)
        if screen:
            rect = fit_rect(rect, screen.availableGeometry())
            if not value:
                rect.moveCenter(screen.availableGeometry().center())
        self.window.setGeometry(rect)
        self._normal = QRect(rect)
        if value:
            self._geometry = value["geometry"]
            self._screen_name = value["screen"]
        self._maximized = bool(value and value["maximized"])
        if self._maximized:
            self.window.showMaximized()
        else:
            self.window.show()
        QTimer.singleShot(0, self._finish_restore)

    def _set_minimum(self, screen):
        available = screen.availableGeometry()
        frame = self.window.frameGeometry().size() - self.window.size()
        self.window.setMinimumSize(min(900, max(1, available.width() - max(0, frame.width()))),
                                   min(640, max(1, available.height() - max(0, frame.height()))))

    def _finish_restore(self):
        if not isValid(self.window):
            return
        self._restoring = False
        self._ready = True
        self._ensure_visible()
        # Some native backends finalize frame offsets after the first move.
        # One bounded post-show correction handles that without polling.
        QTimer.singleShot(0, self._ensure_visible)
        self._capture()
        self._timer.start()

    def _screens_changed(self, *_args):
        if self._ready:
            QTimer.singleShot(0, self._ensure_visible)

    def _ensure_visible(self):
        if not isValid(self.window) or not self._normal:
            return
        screen = choose_screen(QGuiApplication.screens(), self._screen_name, self._normal)
        if not screen:
            return
        if (self.window.isMaximized() or self.window.isFullScreen() or self.window.isMinimized()
                or self._native_state() in ("maximized", "minimized")):
            return
        self._set_minimum(screen)
        frame = self.window.frameGeometry()
        available = screen.availableGeometry()
        if not available.contains(frame):
            # QWidget position includes the frame origin; geometry's top-left
            # is the client origin. Resize then move the native frame itself.
            rect = fit_rect(QRect(frame.topLeft(), self.window.size()), available,
                            frame.size() - self.window.size())
            self.window.resize(rect.size())
            self.window.move(rect.topLeft())

    def _capture(self):
        window = self.window
        if not self._ready or self._restoring:
            return
        native_state = self._native_state()
        if window.isVisible() and not window.isMinimized() and not window.isFullScreen() and native_state != "minimized":
            # ShowWindow resizes the Win32 client before Qt updates its flags.
            # Either backend reporting maximization protects the normal rect.
            self._maximized = window.isMaximized() or native_state == "maximized"
            if not self._maximized:
                self._normal = QRect(window.geometry())
                self._geometry = bytes(window.saveGeometry().toBase64()).decode("ascii")
                screen = window.screen()
                if screen:
                    self._screen_name = screen.name()
                    self._available = screen.availableGeometry()

    def _native_state(self):
        chrome = getattr(self.window, "_chrome", None)
        return chrome.placement_state() if chrome else None

    def eventFilter(self, target, event):
        if target is self.window and self._ready and not self._restoring:
            if event.type() in (QEvent.Move, QEvent.Resize, QEvent.WindowStateChange):
                self._capture()
                self._timer.start()
                if event.type() == QEvent.WindowStateChange:
                    QTimer.singleShot(0, self._ensure_visible)
            elif event.type() in (QEvent.Hide, QEvent.Close):
                self.flush()
        return False

    def flush(self):
        if not isValid(self.window):
            return
        self._timer.stop()
        self._capture()
        if not self._ready or self._normal is None:
            return
        value = dict(version=1, geometry=self._geometry,
                     normal_rect=list(self._normal.getRect()), screen=self._screen_name,
                     available_rect=list(self._available.getRect()), maximized=self._maximized)
        if value == self._last_saved:
            return
        try:
            atomic_json(self.path, value)
            self._last_saved = value
        except OSError:
            logger.warning("Unable to save window placement", exc_info=True)
            if not self._warned:
                self._warned = True
                bar = getattr(self.window, "_status_bar", None)
                if bar:
                    bar.showMessage("暂时无法记住窗口位置，本次使用不受影响。", 8000)
