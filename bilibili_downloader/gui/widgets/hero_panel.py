"""Plain, readable source input card used by the download workspace."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.glass_surface import paint_widget_glass


class HeroPanel(QWidget):
    """Use the shared card surface, with local protection when a picture is set."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeroPanel")
        self.setProperty("glassSurface", True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._compact = False
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setProperty("compact", compact)
        self.updateGeometry()
        self.update()

    def heightForWidth(self, width):
        layout = self.layout()
        content = layout.totalHeightForWidth(width) if layout and layout.hasHeightForWidth() else layout.sizeHint().height() if layout else 0
        return max(120 if self._compact else 190, content)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(0, hint.width()), self.heightForWidth(self.width()))

    def minimumSizeHint(self):
        layout = self.layout()
        return QSize(0, max(120 if self._compact else 190, layout.minimumSize().height() if layout else 0))

    def paintEvent(self, event):
        super().paintEvent(event)
        if paint_widget_glass(self):
            return
        colors = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        surface = QColor(colors.surface)
        painter.setBrush(surface)
        painter.setPen(QPen(QColor(colors.divider), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.end()
