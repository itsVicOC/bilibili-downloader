"""Plain, readable source input card used by the download workspace."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QSizePolicy

from bilibili_downloader.gui.widgets.glass_surface import GlassWidget


class HeroPanel(GlassWidget):
    """Keep the source controls on a readable surface."""

    def __init__(self, parent=None):
        super().__init__(parent, reading=True)
        self.setProperty("readingOutline", False)
        self.setObjectName("HeroPanel")
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
