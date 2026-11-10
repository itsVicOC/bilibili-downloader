"""One transparent, keyboard-visible menu for application-owned actions."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu

from bilibili_downloader.gui.resources.styles import UI_METRICS, theme_palette


class PopupMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setProperty("keyboardFocus", False)
        self._pointer_pos = QCursor.pos()

    def showEvent(self, event):
        self._pointer_pos = QCursor.pos()
        self.setProperty("keyboardFocus", bool(self.parentWidget() and self.parentWidget().property("keyboardFocus")))
        super().showEvent(event)

    def keyPressEvent(self, event):
        self.setProperty("keyboardFocus", True)
        self._pointer_pos = QCursor.pos()
        super().keyPressEvent(event)
        self.update()

    def mouseMoveEvent(self, event):
        if QCursor.pos() != self._pointer_pos:
            self.setProperty("keyboardFocus", False)
            self._pointer_pos = QCursor.pos()
        super().mouseMoveEvent(event)

    def event(self, event):
        if event.type() == QEvent.MouseButtonPress:
            self.setProperty("keyboardFocus", False)
        return super().event(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        action = self.activeAction()
        if not self.property("keyboardFocus") or action is None or not action.isEnabled() or action.isSeparator():
            return
        app = QApplication.instance()
        p = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(p.focus), UI_METRICS.focus_width))
        painter.drawRoundedRect(self.actionGeometry(action).adjusted(2, 2, -2, -2), UI_METRICS.small_radius, UI_METRICS.small_radius)
