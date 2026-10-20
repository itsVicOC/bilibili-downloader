"""A viewport-fixed backdrop shared by all persistent workspaces."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget

from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.resources.styles import (
    background_overlay_alpha,
    theme_palette,
)
from bilibili_downloader.gui.widgets.background_readability import BackgroundReadability


def background_pixmap(path, size=None, *, pixel_art=False):
    if path is None or path.stat().st_size > 64 * 1024 * 1024:
        return QPixmap()
    reader = QImageReader(str(path))
    dimensions = reader.size()
    if not dimensions.isValid() or max(dimensions.width(), dimensions.height()) > 3840:
        return QPixmap()
    if size is not None and not pixel_art:
        dimensions.scale(size, Qt.KeepAspectRatio)
        reader.setScaledSize(dimensions)
    return QPixmap.fromImage(reader.read())


def paint_workspace_background(painter, rect, pixmap, is_dark, theme_id, visibility=None, *, builtin=False, pixel_art=False):
    """Use the same crop and readability mask in workspaces and draft previews."""
    colors = theme_palette(is_dark, theme_id)
    painter.fillRect(rect, QColor(colors.background))
    if pixmap.isNull() or rect.isEmpty():
        return
    painter.setRenderHint(QPainter.SmoothPixmapTransform, not pixel_art)
    source = QRectF(pixmap.rect())
    ratio = max(rect.width() / source.width(), rect.height() / source.height())
    crop = QRectF(0, 0, rect.width() / ratio, rect.height() / ratio)
    crop.moveCenter(source.center())
    painter.drawPixmap(QRectF(rect), pixmap, crop)
    overlay = QColor(colors.background)
    overlay.setAlpha(background_overlay_alpha(is_dark, theme_id, visibility, builtin=builtin))
    painter.fillRect(rect, overlay)


class WorkspaceStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._background = QPixmap()
        self._background_key = None
        self._builtin = False
        self._pixel_art = False
        self._visibility = BackgroundVisibility()
        self.setProperty("customBackground", False)
        self.setProperty("mascotBackground", False)
        self._readability = BackgroundReadability(self)

    def set_background(self, path, *, builtin=False, pixel_art=False):
        try:
            stat = path.stat() if path is not None else None
            key = (str(path), stat.st_mtime_ns, stat.st_size, builtin, pixel_art) if stat else None
            if key == self._background_key:
                return
            self._background = background_pixmap(path)
            self._background_key = key
        except OSError:
            self._background = QPixmap()
            self._background_key = None
        previous = self.property("customBackground")
        self.setProperty("customBackground", not self._background.isNull())
        self._builtin = builtin and not self._background.isNull()
        self._pixel_art = pixel_art and not self._background.isNull()
        if previous != self.property("customBackground") or self.property("mascotBackground") != self._builtin:
            self.setProperty("mascotBackground", self._builtin)
            for widget in [self, *self.findChildren(QWidget)]:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
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
            builtin=self._builtin, pixel_art=self._pixel_art,
        )
        painter.end()
