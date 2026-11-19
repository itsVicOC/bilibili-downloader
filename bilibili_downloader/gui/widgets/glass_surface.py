"""Cached wallpaper glass; native Qt text is painted separately and stays sharp."""

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
    UI_METRICS,
    theme_palette,
    wallpaper_tones,
)


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
        self.outline = QColor()

    def clear(self):
        self.key = None
        self.image = QPixmap()
        self.clear_image = QPixmap()
        self.reading = QPixmap()
        self.original = QPixmap()

    def prepare(self, key, size, render, dark, colors, blur=DEFAULT_GLASS_BLUR, *, flat=False):
        key = (key, size.width(), size.height(), dark, colors, blur, flat)
        if key == self.key:
            return
        if size.isEmpty():
            self.clear()
            return
        # Only wallpaper is downsampled. Controls never enter this cache.
        sample = size.scaled(QSize(32, 32) if flat else QSize(1200, 900), Qt.KeepAspectRatio)
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
        self.original = QPixmap.fromImage(base)
        picture = Image.frombytes("RGBA", (base.width(), base.height()), base.bits().tobytes()).convert("RGB")
        if flat:
            self.image = _pixmap(Image.new("RGB", picture.size, colors.surface_raised))
            self.reading = self.image
            self.clear_image = self.image
        else:
            strength = blur * self.scale[0]
            softened = ImageEnhance.Color(picture).enhance(.95)
            self.image = _material(softened, strength * .70, dark)
            self.reading = _material(softened, strength * .35, dark) if strength else self.image
            self.clear_image = _material(picture, strength * .30, dark, clear=True)
        self.key, self.dark = key, dark
        self.outline = QColor(colors.card_border)

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
        if clear_below is not None and self.clear_image.cacheKey() != self.reading.cacheKey() and clear_below < rect.bottom():
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

    def paint(self, painter, rect, source_rect, radius=18, *, clear=False):
        material = self.clear_image if clear else self.image
        if material.isNull():
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
        painter.setPen(QPen(QColor(0, 0, 0, 44 if self.dark else 26), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.translated(0, 1), radius, radius)
        painter.setClipPath(path, Qt.IntersectClip)
        painter.drawPixmap(rect, material, source)
        # The lens displaces the underlying image most at the outer edge.
        # Keep both bands outside the surface's reading area.
        if min(rect.width(), rect.height()) > 12:
            outer = path
            for inset, displacement, opacity in ((2, 3.0, .34), (4, 1.5, .16)):
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
        rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        rim.setColorAt(0, QColor(255, 255, 255, 84 if self.dark else 190))
        rim.setColorAt(.45, QColor(255, 255, 255, 26 if self.dark else 48))
        rim.setColorAt(1, QColor(0, 0, 0, 65 if self.dark else 38))
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
                clear=bool(widget.property("clearGlass")), clear_below=clear_below,
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


class ItemViewSurface(ScrollAreaSurface):
    """Draw rounded header tints and reveal more wallpaper below the rows."""

    def __init__(self, view):
        super().__init__(view)
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
        tint.setAlpha(112)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(tint)
        for header in self._headers:
            if header.isVisible():
                radius = UI_METRICS.radius
                painter.drawRoundedRect(QRectF(header.geometry()), radius, radius)
        painter.end()
