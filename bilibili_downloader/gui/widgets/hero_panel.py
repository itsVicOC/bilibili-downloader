"""Plain, readable source input card used by the download workspace."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from bilibili_downloader.gui.resources.styles import UI_METRICS
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
        self._minimum_height = 190
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_compact(self, compact: bool, *, minimum_height=None) -> None:
        self._compact = compact
        self._minimum_height = minimum_height if minimum_height is not None else 120 if compact else 190
        self.setProperty("compact", compact)
        self.updateGeometry()
        self.update()

    def heightForWidth(self, width):
        layout = self.layout()
        content = layout.totalHeightForWidth(width) if layout and layout.hasHeightForWidth() else layout.sizeHint().height() if layout else 0
        return max(self._minimum_height, content)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(0, hint.width()), self.heightForWidth(self.width()))

    def minimumSizeHint(self):
        layout = self.layout()
        return QSize(0, max(self._minimum_height, layout.minimumSize().height() if layout else 0))

    def paintEvent(self, event):
        super().paintEvent(event)
        if paint_widget_glass(self):
            return
        colors = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        surface = QColor(colors.surface)
        painter.setBrush(surface)
        painter.setPen(QPen(QColor(colors.card_border), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), UI_METRICS.card_radius, UI_METRICS.card_radius)
        painter.end()
