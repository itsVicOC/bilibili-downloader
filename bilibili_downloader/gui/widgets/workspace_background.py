"""A viewport-fixed backdrop shared by all persistent workspaces."""

from PySide6.QtCore import QObject, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR, BackgroundVisibility
from bilibili_downloader.gui.resources.styles import (
    background_overlay_alpha,
    theme_palette,
)
from bilibili_downloader.gui.widgets.background_readability import BackgroundReadability
from bilibili_downloader.gui.widgets.glass_surface import GlassBackdrop


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


class WindowBackdrop(QObject):
    """Use one crop and one glass cache in the host's coordinate space."""

    def __init__(self, host):
        super().__init__(host)
        self.image = QPixmap()
        self._background_key = None
        self._builtin = False
        self._pixel_art = False
        self.visibility = BackgroundVisibility()
        self.glass = GlassBackdrop()
        self.blur = DEFAULT_GLASS_BLUR
        self._viewport_key = None
        self._viewport = QPixmap()
        host.setProperty("customBackground", False)
        host.setProperty("mascotBackground", False)
        self._readability = BackgroundReadability(host)

    @property
    def host(self):
        return self.parent()

    def inherit(self, source):
        """Take a snapshot so an open dialog keeps its opening wallpaper."""
        if source is None:
            self.set_background(None)
            self.set_visibility(BackgroundVisibility())
            self.set_glass_blur(DEFAULT_GLASS_BLUR)
            return
        self.image = QPixmap(source.image)
        self._background_key = source._background_key
        self.set_visibility(source.visibility)
        self.set_glass_blur(source.blur)
        self._apply_source(source._builtin, source._pixel_art)

    def set_background(self, path, *, builtin=False, pixel_art=False):
        try:
            stat = path.stat() if path is not None else None
            key = (str(path), stat.st_mtime_ns, stat.st_size, builtin, pixel_art) if stat else None
            if key == self._background_key:
                return
            self.image = background_pixmap(path)
            self._background_key = key
        except OSError:
            self.image = QPixmap()
            self._background_key = None
        self._apply_source(builtin, pixel_art)

    def _apply_source(self, builtin, pixel_art):
        host = self.host
        active = not self.image.isNull()
        self._builtin = builtin and active
        self._pixel_art = pixel_art and active
        if host.property("customBackground") != active or host.property("mascotBackground") != self._builtin:
            host.setProperty("customBackground", active)
            host.setProperty("mascotBackground", self._builtin)
            for widget in [host, *host.findChildren(QWidget)]:
                if widget.window() != host.window():
                    continue
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        host.update()

    def set_visibility(self, visibility):
        if self.visibility != visibility:
            self.visibility = visibility.model_copy(deep=True)
            self.host.update()

    def _scene(self):
        app = QApplication.instance()
        dark = bool(app.property("darkTheme"))
        theme_id = app.property("colorTheme")
        visible = self.visibility.dark if dark else self.visibility.light
        host = self.host
        dpr = host.devicePixelRatioF()
        key = (self.image.cacheKey(), theme_id, dark, visible, self._builtin, self._pixel_art, dpr)
        viewport_key = (key, host.size())
        colors = theme_palette(dark, theme_id)
        if viewport_key != self._viewport_key:
            self._viewport = QPixmap()
            if not self.image.isNull() and not host.size().isEmpty():
                self._viewport = QPixmap(QSize(round(host.width() * dpr), round(host.height() * dpr)))
                self._viewport.setDevicePixelRatio(dpr)
                painter = QPainter(self._viewport)
                paint_workspace_background(
                    painter, QRectF(host.rect()), self.image, dark, theme_id, visible,
                    builtin=self._builtin, pixel_art=self._pixel_art,
                )
                painter.end()
            self._viewport_key = viewport_key
        return key, dark, colors

    def _paint_viewport(self, painter, rect, color):
        if self._viewport.isNull():
            painter.fillRect(rect, color)
        else:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, not self._pixel_art)
            painter.drawPixmap(QRectF(rect), self._viewport, QRectF(self._viewport.rect()))

    def paint_glass(self, painter, widget, radius=18, *, reading=False, clear=False, clear_below=None):
        key, dark, colors = self._scene()
        host = self.host
        self.glass.prepare(
            key, host.size(),
            lambda p, rect: self._paint_viewport(p, rect, QColor(colors.background)),
            dark, colors, self.blur, flat=self.image.isNull(),
        )
        offset = QPoint() if widget is host else widget.mapTo(host, QPoint())
        source = QRectF(offset, widget.size())
        if reading:
            self.glass.paint_reading(painter, widget.rect(), source, clear_below=clear_below)
        else:
            self.glass.paint(painter, widget.rect(), source, radius=radius, clear=clear)

    def set_glass_blur(self, value):
        if self.blur != value:
            self.blur = value
            self.host.update()

    def paint(self, painter):
        _, _, colors = self._scene()
        self._paint_viewport(painter, self.host.rect(), QColor(colors.background))


class WorkspaceStack(QStackedWidget):
    def __init__(self, parent=None, *, backdrop=None):
        super().__init__(parent)
        self.backdrop = backdrop if backdrop is not None else WindowBackdrop(self)

    def set_background(self, path, *, builtin=False, pixel_art=False):
        self.backdrop.set_background(path, builtin=builtin, pixel_art=pixel_art)

    def set_visibility(self, visibility):
        self.backdrop.set_visibility(visibility)

    def set_glass_blur(self, blur):
        self.backdrop.set_glass_blur(blur)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.backdrop.host is self:
            painter = QPainter(self)
            self.backdrop.paint(painter)
            painter.end()
