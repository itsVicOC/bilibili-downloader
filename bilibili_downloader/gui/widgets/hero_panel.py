"""Decorative hero panel used by the main window."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from bilibili_downloader.gui.resources.paths import asset_path


class HeroPanel(QWidget):
    """A readable image-backed surface with a strong anime-inspired treatment."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeroPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(190)
        self._background = QPixmap(asset_path("nebula.jpg"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        clip = QPainterPath()
        clip.addRoundedRect(self.rect(), 8, 8)
        painter.setClipPath(clip)

        if not self._background.isNull():
            scaled = self._background.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            source_x = max(0, (scaled.width() - self.width()) // 2)
            source_y = max(0, (scaled.height() - self.height()) // 2)
            painter.drawPixmap(
                self.rect(), scaled, QRect(source_x, source_y, self.width(), self.height())
            )

        app = QApplication.instance()
        is_dark = True if app is None else bool(app.property("darkTheme"))
        overlay = QLinearGradient(0, 0, self.width(), 0)
        if is_dark:
            overlay.setColorAt(0.0, QColor(12, 10, 30, 244))
            overlay.setColorAt(0.62, QColor(32, 17, 66, 218))
            overlay.setColorAt(1.0, QColor(9, 11, 28, 165))
        else:
            overlay.setColorAt(0.0, QColor(250, 248, 252, 244))
            overlay.setColorAt(0.62, QColor(247, 239, 249, 224))
            overlay.setColorAt(1.0, QColor(235, 244, 249, 194))
        painter.fillRect(self.rect(), overlay)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 95, 162, 42 if is_dark else 34))
        painter.drawEllipse(self.width() - 170, -62, 230, 230)
        painter.setBrush(QColor(98, 213, 255, 34 if is_dark else 42))
        painter.drawEllipse(self.width() - 300, 92, 190, 190)

        painter.setPen(
            QColor(255, 255, 255, 34)
            if is_dark else QColor(75, 60, 85, 28)
        )
        for offset in range(-160, self.width(), 56):
            painter.drawLine(offset, self.height(), offset + 160, 0)

        painter.end()
        super().paintEvent(event)
