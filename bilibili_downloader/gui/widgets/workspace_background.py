"""A viewport-fixed backdrop shared by all persistent workspaces."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStackedWidget

from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.resources.styles import (
    background_overlay_alpha,
    theme_palette,
)


def background_pixmap(path, size=None):
    if path is None or path.stat().st_size > 64 * 1024 * 1024:
        return QPixmap()
    reader = QImageReader(str(path))
    dimensions = reader.size()
    if not dimensions.isValid() or max(dimensions.width(), dimensions.height()) > 3840:
        return QPixmap()
    if size is not None:
        dimensions.scale(size, Qt.KeepAspectRatio)
        reader.setScaledSize(dimensions)
    return QPixmap.fromImage(reader.read())


def paint_workspace_background(painter, rect, pixmap, is_dark, theme_id, visibility=None):
    """Use the same crop and readability mask in workspaces and draft previews."""
    colors = theme_palette(is_dark, theme_id)
    painter.fillRect(rect, QColor(colors.background))
    if pixmap.isNull() or rect.isEmpty():
        return
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    source = QRectF(pixmap.rect())
    ratio = max(rect.width() / source.width(), rect.height() / source.height())
    crop = QRectF(0, 0, rect.width() / ratio, rect.height() / ratio)
    crop.moveCenter(source.center())
    painter.drawPixmap(QRectF(rect), pixmap, crop)
    overlay = QColor(colors.background)
    overlay.setAlpha(background_overlay_alpha(is_dark, theme_id, visibility))
    painter.fillRect(rect, overlay)


class WorkspaceStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._background = QPixmap()
        self._background_key = None
        self._visibility = BackgroundVisibility()
        self.setProperty("customBackground", False)

    def set_background(self, path):
        try:
            stat = path.stat() if path is not None else None
            key = (str(path), stat.st_mtime_ns, stat.st_size) if stat else None
            if key == self._background_key:
                return
            self._background = background_pixmap(path)
            self._background_key = key
        except OSError:
            self._background = QPixmap()
            self._background_key = None
        self.setProperty("customBackground", not self._background.isNull())
        self.update()
        for child in self.findChildren(QStackedWidget):
            child.update()

    def set_visibility(self, visibility):
        self._visibility = visibility.model_copy(deep=True)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        app = QApplication.instance()
        is_dark = bool(app.property("darkTheme"))
        paint_workspace_background(
            painter, self.rect(), self._background, is_dark,
            app.property("colorTheme"),
            self._visibility.dark if is_dark else self._visibility.light,
        )
        painter.end()
