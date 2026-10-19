"""Plain, readable source input card used by the download workspace."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from bilibili_downloader.gui.widgets.components import palette


class HeroPanel(QWidget):
    """Keep the source form on the same solid surface as the content cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeroPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(190)

    def set_compact(self, compact: bool) -> None:
        height = 120 if compact else 190
        self.setMinimumHeight(height)
        self.setMaximumHeight(height if compact else 16777215)
        self.setProperty("compact", compact)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        colors = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(colors.surface))
        painter.setPen(QPen(QColor(colors.divider), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.end()
