"""Cached window materials; Qt draws text and controls over the sampled surfaces."""

from PIL import Image, ImageEnhance, ImageFilter
from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QFrame, QTableView, QWidget

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR
from bilibili_downloader.gui.resources.styles import (
    TABLE_HEADER_OPACITY,
    UI_METRICS,
    blend_color,
    theme_palette,
    wallpaper_tones,
)

HEADER_BLEND_HEIGHT = 16


class GlassBackdrop:
    """Cached wallpaper and contrast-adjusted glass for one rendering surface."""

    def __init__(self):
        self.key = None
        self.image = QPixmap()
        self.clear_image = QPixmap()
        self.reading = QPixmap()
        self.original = QPixmap()
        self.scale = (1.0, 1.0)
        self.dark = False
        self.ambient = False
        self.outline = QColor()
        self._handoff_key = None
        self._handoff = QImage()

    def clear(self):
        self.key = None
        self.image = QPixmap()
        self.clear_image = QPixmap()
        self.reading = QPixmap()
        self.original = QPixmap()
        self._handoff_key = None
        self._handoff = QImage()

    def prepare(self, key, size, render, dark, colors, blur=DEFAULT_GLASS_BLUR, *, ambient=False):
        key = (key, size.width(), size.height(), dark, colors, ambient, None if ambient else blur)
        if key == self.key:
            return
        if size.isEmpty():
            self.clear()
            return
        # Controls never enter the backdrop, and a smooth color field can use a smaller cache.
        sample = size.scaled(QSize(240, 180) if ambient else QSize(1200, 900), Qt.KeepAspectRatio)
        if sample.width() > size.width():
            sample = size
        sample = sample.expandedTo(QSize(1, 1))
        self.scale = (sample.width() / size.width(), sample.height() / size.height())
        base = QImage(sample, QImage.Format_RGBA8888)
        base.fill(Qt.transparent)
        painter = QPainter(base)
        painter.scale(*self.scale)
        render(painter, QRectF(QPoint(), size))
        painter.end()
        picture = Image.frombytes("RGBA", (base.width(), base.height()), base.bits().tobytes()).convert("RGB")
        if ambient:
            raised = Image.new("RGB", picture.size, colors.surface_raised)
            paper = blend_color(colors.surface_raised, colors.text, .035) if dark else colors.surface
            reading = Image.new("RGB", picture.size, paper)
            self.image = _pixmap(Image.blend(picture, raised, .65 if dark else .57))
            self.reading = _pixmap(Image.blend(picture, reading, .64 if dark else .78))
            self.clear_image = self.image
            self.original = QPixmap()
        else:
            self.original = QPixmap.fromImage(base)
            strength = blur * self.scale[0]
            softened = ImageEnhance.Color(picture).enhance(.95)
            self.image = _material(softened, strength * .60, dark)
            self.reading = _material(softened, strength * .43, dark) if strength else self.image
            self.clear_image = _material(picture, strength * .24, dark, clear=True)
        self.key, self.dark, self.ambient = key, dark, ambient
        self.outline = QColor(colors.text if ambient else colors.card_border)
        self.outline.setAlpha(24 if ambient else 168)
        self._handoff_key = None

    def _sampling_rect(self, source):
        sx, sy = self.scale
        return QRectF(source.x() * sx, source.y() * sy, source.width() * sx, source.height() * sy)

    def paint_reading(self, painter, rect, source_rect, *, clear_below=None):
        rect = QRectF(rect).adjusted(.5, .5, -.5, -.5)
        if self.reading.isNull() or rect.isEmpty():
            return
        path = QPainterPath()
        radius = UI_METRICS.card_radius
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.save()
        painter.setClipPath(path, Qt.IntersectClip)
        source_rect = QRectF(source_rect).adjusted(.5, .5, -.5, -.5)
        painter.drawPixmap(rect, self.reading, self._sampling_rect(source_rect))
        if not self.ambient and clear_below is not None and clear_below < rect.bottom():
            self._paint_blank(painter, rect, source_rect, clear_below)
        painter.restore()
        painter.setPen(self.outline)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def _paint_blank(self, painter, rect, source_rect, top):
        # Fade only the narrow transition band, then draw the remaining
        # wallpaper directly from its cache. Both samples use window coordinates.
        top = max(rect.top(), top)
        fade_height = min(16, rect.bottom() - top)
        if fade_height <= 0:
            return
        fade = QRectF(rect.left(), top, rect.width(), fade_height)
        dpr = painter.device().devicePixelRatioF()
        size = QSize(round(fade.width() * dpr), round(fade.height() * dpr)).expandedTo(QSize(1, 1))
        band = QImage(size, QImage.Format_ARGB32_Premultiplied)
        band.setDevicePixelRatio(dpr)
        band.fill(Qt.transparent)
        mask = QPainter(band)
        local = QRectF(QPoint(), band.deviceIndependentSize())
        mask.setRenderHint(QPainter.SmoothPixmapTransform)
        mask.drawPixmap(local, self.clear_image, self._sampling_rect(fade.translated(source_rect.topLeft() - rect.topLeft())))
        alpha = QLinearGradient(local.topLeft(), local.bottomLeft())
        alpha.setColorAt(0, Qt.transparent)
        alpha.setColorAt(1, Qt.black)
        mask.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        mask.fillRect(local, alpha)
        mask.end()
        painter.drawImage(fade, band, QRectF(band.rect()))
        blank = QRectF(rect.left(), fade.bottom(), rect.width(), rect.bottom() - fade.bottom())
        if not blank.isEmpty():
            painter.drawPixmap(blank, self.clear_image, self._sampling_rect(blank.translated(source_rect.topLeft() - rect.topLeft())))

    def _paint_attached(self, painter, rect, source_rect, edge, material):
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(rect, material, self._sampling_rect(source_rect))
        if edge == Qt.RightEdge:
            depth = min(10, rect.width())
            band = QRectF(rect.right() - depth, rect.top(), depth, rect.height())
            start, end = band.topLeft(), band.topRight()
        else:
            depth = min(10, rect.height())
            top = rect.top() if edge == Qt.TopEdge else rect.bottom() - depth
            band = QRectF(rect.left(), top, rect.width(), depth)
            start, end = band.topLeft(), band.bottomLeft()
            if edge == Qt.TopEdge:
                start, end = end, start
        shadow = QLinearGradient(start, end)
        shadow.setColorAt(0, QColor(0, 0, 0, 0))
        shadow.setColorAt(1, QColor(0, 0, 0, 32 if self.dark else 21))
        painter.fillRect(band, shadow)
        painter.fillRect(QRectF(rect.x(), rect.y(), rect.width(), 1), QColor(255, 255, 255, 30 if self.dark else 95))
        painter.restore()

    def paint_header_handoff(self, painter, rect, source_rect):
        """Fade the cached title material into the same wallpaper below it."""
        if self.image.isNull() or rect.isEmpty():
            return
        dpr = painter.device().devicePixelRatioF()
        key = (*source_rect.getRect(), dpr)
        if key != self._handoff_key:
            surface = QImage(QSize(round(rect.width() * dpr), round(rect.height() * dpr)).expandedTo(QSize(1, 1)),
                             QImage.Format_ARGB32_Premultiplied)
            surface.setDevicePixelRatio(dpr)
            surface.fill(Qt.transparent)
            gradient_painter = QPainter(surface)
            local = QRectF(QPoint(), surface.deviceIndependentSize())
            gradient_painter.setRenderHint(QPainter.SmoothPixmapTransform)
            gradient_painter.drawPixmap(local, self.image, self._sampling_rect(source_rect))
            fade = QLinearGradient(local.topLeft(), local.bottomLeft())
            fade.setColorAt(0, QColor(0, 0, 0, 245))
            fade.setColorAt(.55, QColor(0, 0, 0, 120))
            fade.setColorAt(1, Qt.transparent)
            gradient_painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            gradient_painter.fillRect(local, fade)
            gradient_painter.end()
            self._handoff_key, self._handoff = key, surface
        painter.drawImage(rect, self._handoff, QRectF(self._handoff.rect()))

    def paint(self, painter, rect, source_rect, radius=18, *, clear=False, edge=None):
        material = self.clear_image if clear else self.image
        if material.isNull() or rect.isEmpty():
            return
        if edge is not None:
            self._paint_attached(painter, QRectF(rect), QRectF(source_rect), edge, material)
            return
        rect = QRectF(rect).adjusted(2, 2, -2, -3)
        if rect.isEmpty():
            return
        source = self._sampling_rect(QRectF(source_rect).adjusted(2, 2, -2, -3))
        sx, sy = self.scale
        radius = min(radius, rect.width() / 2, rect.height() / 2)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setPen(QPen(QColor(0, 0, 0, 26 if self.dark else 17), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.translated(0, 1), radius, radius)
        painter.setClipPath(path, Qt.IntersectClip)
        painter.drawPixmap(rect, material, source)
        # The lens displaces the underlying image most at the outer edge.
        # Keep both bands outside the surface's reading area.
        if not self.original.isNull() and min(rect.width(), rect.height()) > 12:
            outer = path
            for inset, displacement, opacity in ((2, 2.5, .23), (4, 1.25, .10)):
                inner = QPainterPath()
                inner.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset),
                                     max(0, radius - inset), max(0, radius - inset))
                painter.save()
                painter.setClipPath(outer.subtracted(inner), Qt.IntersectClip)
                painter.setOpacity(opacity)
                dx, dy = displacement * sx, displacement * sy
                painter.drawPixmap(rect, self.original, source.adjusted(dx, dy, -dx, -dy))
                painter.restore()
                outer = inner
        # One directional highlight and a smaller reflection across the opposite rim.
        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        highlight = (98 if self.dark else 212) if self.ambient else (78 if self.dark else 152)
        rim.setColorAt(0, QColor(255, 255, 255, highlight))
        rim.setColorAt(.34, QColor(255, 255, 255, round(highlight * .36)))
        rim.setColorAt(.66, QColor(0, 0, 0, 38 if self.dark else 26))
        rim.setColorAt(1, QColor(255, 255, 255, round(highlight * .52)))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rim, 1))
        painter.drawPath(path)
        painter.restore()


def _material(source, strength, dark, *, clear=False):
    low, high = wallpaper_tones(dark, clear=clear)
    gamma = .8 if dark else 1
    lut = [round(low + (high - low) * (value / 255) ** gamma) for value in range(256)] * 3
    return _pixmap(source.filter(ImageFilter.GaussianBlur(strength)).point(lut))


def _pixmap(source):
    rgba = source.convert("RGBA")
    image = QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(image.copy())


def paint_widget_glass(widget, *, clear_below=None):
    glass = widget.property("glassSurface")
    reading = widget.property("readingSurface")
    if not (glass or reading) or widget.property("sectionStyle") == "plain":
        return False
    current = widget.parentWidget()
    while current is not None and current.window() == widget.window():
        backdrop = getattr(current, "backdrop", None)
        if backdrop is not None:
            painter = QPainter(widget)
            backdrop.paint_glass(
                painter, widget, reading=reading and not glass,
                clear=bool(widget.property("clearGlass")), edge=widget.property("glassEdge"), clear_below=clear_below,
            )
            painter.end()
            return True
        current = current.parentWidget()
    return False


def _paint_reading_fallback(widget):
    app = QApplication.instance()
    colors = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(colors.card_border))
    painter.setBrush(QColor(colors.surface_raised))
    rect = QRectF(widget.rect()).adjusted(.5, .5, -.5, -.5)
    painter.drawRoundedRect(rect, UI_METRICS.card_radius, UI_METRICS.card_radius)
    painter.end()


class GlassFrame(QFrame):
    def __init__(self, parent=None, *, glass=False, reading=False):
        super().__init__(parent)
        self.setProperty("glassSurface", glass)
        self.setProperty("readingSurface", reading)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not paint_widget_glass(self) and self.property("readingSurface"):
            _paint_reading_fallback(self)


class GlassWidget(QWidget):
    def __init__(self, parent=None, *, glass=False, reading=False):
        super().__init__(parent)
        self.setProperty("glassSurface", glass)
        self.setProperty("readingSurface", reading)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not paint_widget_glass(self) and self.property("readingSurface"):
            _paint_reading_fallback(self)


class ScrollAreaSurface(GlassWidget):
    """Keep the rounded surface fixed while the viewport moves its content."""

    def __init__(self, area):
        super().__init__(area, reading=True)
        area.setProperty("readingSurface", True)
        area.viewport().setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(area.rect())
        self.lower()
        self.show()
        area.installEventFilter(self)

    def eventFilter(self, view, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(view.rect())
        return False


class ScrollEdge(QWidget):
    """Let clipped content recede underneath a fixed workspace or table header."""

    def __init__(self, area, height=18):
        self._viewport = area.viewport()
        super().__init__(self._viewport)
        self._height = height
        self._scrollbar = area.verticalScrollBar()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self._viewport.installEventFilter(self)
        self._scrollbar.valueChanged.connect(self._sync)
        self._sync()

    def _sync(self, *_args):
        self.setGeometry(0, 0, self._viewport.width(), self._height)
        active = self._scrollbar.value() > self._scrollbar.minimum()
        self.setVisible(active)
        if active:
            self.raise_()
            self.update()

    def eventFilter(self, widget, event):
        if event.type() == QEvent.Resize:
            self._sync()
        return False

    def paintEvent(self, event):
        app = QApplication.instance()
        colors = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        tint = QColor(colors.background)
        tint.setAlpha(min(200, 80 + 8 * (self._scrollbar.value() - self._scrollbar.minimum())))
        fade = QLinearGradient(0, 0, 0, self.height())
        fade.setColorAt(0, tint)
        tint.setAlpha(0)
        fade.setColorAt(1, tint)
        painter = QPainter(self)
        painter.fillRect(self.rect(), fade)
        painter.end()


class ItemViewSurface(ScrollAreaSurface):
    """Draw rounded header tints and reveal more wallpaper below the rows."""

    def __init__(self, view):
        super().__init__(view)
        self._scroll_edge = ScrollEdge(view, 9)
        self._headers = ((view.horizontalHeader(), view.verticalHeader()) if isinstance(view, QTableView)
                         else (view.header(),))
        for header in self._headers:
            header.geometriesChanged.connect(self.update)
            header.sectionResized.connect(self._rows_changed)
        model = view.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.layoutChanged, model.modelReset,
                       view.verticalScrollBar().valueChanged):
            signal.connect(self._rows_changed)
        if not isinstance(view, QTableView):
            view.expanded.connect(self._rows_changed)
            view.collapsed.connect(self._rows_changed)
        view.setProperty("readingView", True)

    def _rows_changed(self, *_):
        self.update()

    def _blank_top(self):
        view = self.parentWidget()
        viewport = view.viewport()
        if not viewport.isVisible() or viewport.height() < 1:
            return None
        if view.model().rowCount(view.rootIndex()) == 0:
            return viewport.y()

        def occupied(y):
            if isinstance(view, QTableView):
                return view.rowAt(y) >= 0
            return view.indexAt(QPoint(0, y)).isValid()

        low, high = 0, viewport.height() - 1
        if occupied(high) or not occupied(low):
            return None
        # Visible rows occupy a contiguous run from the top of the viewport.
        while high - low > 1:
            mid = (low + high) // 2
            if occupied(mid):
                low = mid
            else:
                high = mid
        return viewport.y() + high

    def paintEvent(self, event):
        if not paint_widget_glass(self, clear_below=self._blank_top()):
            _paint_reading_fallback(self)
        app = QApplication.instance()
        colors = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        tint = QColor(colors.surface_raised)
        tint.setAlpha(TABLE_HEADER_OPACITY)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(tint)
        for header in self._headers:
            if header.isVisible():
                radius = UI_METRICS.card_radius - UI_METRICS.surface_inset
                painter.drawRoundedRect(QRectF(header.geometry()), radius, radius)
        painter.end()
