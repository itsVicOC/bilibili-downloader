"""Plain, readable source input card used by the download workspace."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from bilibili_downloader.gui.resources.styles import background_surface_alpha
from bilibili_downloader.gui.widgets.background_readability import wallpaper_active
from bilibili_downloader.gui.widgets.components import palette


class HeroPanel(QWidget):
    """Use the shared card surface, with local protection when a picture is set."""

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
        surface = QColor(colors.surface)
        if wallpaper_active(self):
            surface.setAlpha(background_surface_alpha(bool(QApplication.instance().property("darkTheme"))))
        painter.setBrush(surface)
        painter.setPen(QPen(QColor(colors.divider), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.end()
