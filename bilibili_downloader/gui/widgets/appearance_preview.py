"""Theme selection cards and faithful, isolated wallpaper effect previews."""

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QSizePolicy, QWidget

from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.resources.styles import theme_palette
from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.header_backdrop import paint_header_backdrop
from bilibili_downloader.gui.widgets.workspace_background import (
    paint_workspace_background,
)


class ThemePreviewButton(QAbstractButton):
    def __init__(self, name, description, theme_id, parent=None):
        super().__init__(parent)
        self.theme_id = theme_id
        self.name, self.description = name, description
        self.setCheckable(True)
        self.setAccessibleName(f"{name}主题，{description}")
        self.setToolTip(f"{name} · {description}；保存后应用")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(140)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.toggled.connect(self._describe_selection)
        self._describe_selection(False)

    def _describe_selection(self, selected):
        self.setAccessibleDescription(
            "已选中，保存设置后应用" if selected else "按空格选择此主题，保存设置后应用"
        )

    def sizeHint(self):
        return QSize(260, 140)

    def event(self, event):
        if event.type() == QEvent.StyleChange:
            self.update()
        return super().event(event)

    def paintEvent(self, event):
        dark = bool(QApplication.instance().property("darkTheme"))
        p = theme_palette(dark, self.theme_id)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        selected = self.isChecked()
        painter.setPen(QPen(QColor(palette().focus if selected else palette().divider), 2 if selected else 1))
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(5, 5, -5, -5), 10, 10)
        if self.hasFocus() and self.property("keyboardFocus"):
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(palette().focus), 1.5, Qt.DashLine))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)
        canvas = QRectF(12, 12, self.width() - 24, 74)
        painter.fillRect(canvas, QColor(p.background))
        painter.fillRect(QRectF(12, 12, 28, 74), QColor(p.sidebar))
        painter.fillRect(QRectF(18, 32, 16, 5), QColor(p.accent))
        sky = QLinearGradient(50, 18, self.width() - 14, 60)
        sky.setColorAt(0, QColor(p.hero_start or p.surface))
        sky.setColorAt(1, QColor(p.hero_end or p.selection))
        painter.fillRect(QRectF(48, 18, self.width() - 62, 26), sky)
        painter.fillRect(QRectF(48, 51, self.width() - 130, 26), QColor(p.surface))
        painter.fillRect(
            QRectF(self.width() - 73, 51, 58, 26), QColor(p.primary or p.accent)
        )
        painter.setPen(QColor(p.text))
        painter.drawText(14, 107, self.name)
        painter.setPen(QColor(p.muted))
        painter.drawText(14, 128, self.description)
        if self.isChecked():
            painter.setPen(QColor(palette().active_text))
            painter.drawText(
                QRectF(self.width() - 90, 90, 72, 26),
                Qt.AlignRight | Qt.AlignVCenter,
                "✓ 已选",
            )
        painter.end()


class BackgroundThumbnail(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setText("默认背景")
        self.setFixedSize(160, 90)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    def clear(self):
        self._pixmap = QPixmap()
        self.update()

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def pixmap(self):
        return self._pixmap

    def paintEvent(self, event):
        p = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(p.surface_raised))
        painter.setPen(QPen(QColor(p.focus if self.hasFocus() else p.divider), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        if self._pixmap.isNull():
            painter.setPen(QColor(p.muted))
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        else:
            scaled = self._pixmap.scaled(
                156, 86, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            painter.setClipRect(self.rect().adjusted(2, 2, -2, -2))
            painter.drawPixmap(
                (self.width() - scaled.width()) // 2,
                (self.height() - scaled.height()) // 2,
                scaled,
            )
        painter.end()


class WorkspacePreview(QWidget):
    def __init__(self, title, pixmap, theme_id, parent=None, visibility=None):
        super().__init__(parent)
        self.title, self.pixmap, self.theme_id = title, pixmap, theme_id
        self.visibility = (visibility or BackgroundVisibility()).model_copy(deep=True)
        self.is_dark = bool(QApplication.instance().property("darkTheme"))
        self.setMinimumSize(480, 300)

    def paintEvent(self, event):
        p = theme_palette(self.is_dark, self.theme_id)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        content = self.rect().adjusted(64, 44, 0, 0)
        paint_workspace_background(
            painter, content, self.pixmap, self.is_dark, self.theme_id,
            self.visibility.dark if self.is_dark else self.visibility.light,
        )
        paint_header_backdrop(
            painter, QRectF(0, 0, self.width(), 44), self.is_dark, self.theme_id
        )
        painter.fillRect(0, 44, 64, self.height() - 44, QColor(p.sidebar))
        painter.setPen(QColor(p.text))
        painter.drawText(20, 28, f"{self.title} · 背景效果预览")
        painter.setBrush(QColor(p.accent))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(20, 76, 24, 24, 6, 6)
        painter.setBrush(QColor(p.surface))
        painter.setPen(QPen(QColor(p.divider), 1))
        painter.drawRoundedRect(
            content.adjusted(24, 28, -24, -self.height() // 2), 12, 12
        )
        painter.drawRoundedRect(
            content.adjusted(24, self.height() // 2 - 26, -120, -32), 12, 12
        )
        painter.setPen(QColor(p.text))
        painter.drawText(
            content.left() + 44, content.top() + 62, "卡片和表格保留清晰底色"
        )
        painter.setPen(QColor(p.muted))
        painter.drawText(
            content.left() + 44, content.top() + 88, "背景居中裁切，自动叠加深浅色遮罩"
        )
        painter.end()
