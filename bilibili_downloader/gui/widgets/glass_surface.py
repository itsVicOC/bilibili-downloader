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
        self.reading = QPixmap()
        self.original = QPixmap()
        self.scale = (1.0, 1.0)
        self.dark = False
        self.outline = QColor()

    def clear(self):
        self.key = None
        self.image = QPixmap()
        self.reading = QPixmap()
        self.original = QPixmap()

    def prepare(self, key, size, render, dark, colors, blur=DEFAULT_GLASS_BLUR, *, flat=False):
        key = (key, size.width(), size.height(), dark, colors, blur)
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
        else:
            picture = ImageEnhance.Color(picture).enhance(.95)
            low, high = wallpaper_tones(dark)
            # Preserve contours instead of clipping distinct source tones into
            # the same shade. The reading surface takes a lighter blur pass.
            gamma = .8 if dark else 1
            lut = [round(low + (high - low) * (value / 255) ** gamma) for value in range(256)] * 3
            strength = blur * self.scale[0]
            self.image = _pixmap(picture.filter(ImageFilter.GaussianBlur(strength)).point(lut))
            self.reading = _pixmap(picture.filter(ImageFilter.GaussianBlur(strength * .45)).point(lut)) if strength else self.image
        self.key, self.dark = key, dark
        self.outline = QColor(colors.card_border)

    def _sampling_rect(self, source):
        sx, sy = self.scale
        return QRectF(source.x() * sx, source.y() * sy, source.width() * sx, source.height() * sy)

    def paint_reading(self, painter, rect, source_rect):
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
        painter.drawPixmap(rect, self.reading, self._sampling_rect(QRectF(source_rect).adjusted(.5, .5, -.5, -.5)))
        painter.restore()
        painter.setPen(self.outline)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def paint(self, painter, rect, source_rect, radius=18):
        if self.image.isNull():
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
        painter.drawPixmap(rect, self.image, source)
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
        shine = QLinearGradient(rect.topLeft(), rect.bottomRight())
        shine.setColorAt(0, QColor(255, 255, 255, 8 if self.dark else 24))
        shine.setColorAt(.24, QColor(255, 255, 255, 3 if self.dark else 11))
        shine.setColorAt(.70, QColor(255, 255, 255, 0))
        shine.setColorAt(1, QColor(255, 255, 255, 8 if self.dark else 12))
        painter.fillPath(path, shine)
        rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        rim.setColorAt(0, QColor(255, 255, 255, 84 if self.dark else 190))
        rim.setColorAt(.45, QColor(255, 255, 255, 26 if self.dark else 48))
        rim.setColorAt(1, QColor(0, 0, 0, 65 if self.dark else 38))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rim, 1))
        painter.drawPath(path)
        painter.restore()


def _pixmap(source):
    rgba = source.convert("RGBA")
    image = QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(image.copy())


def paint_widget_glass(widget):
    glass = widget.property("glassSurface")
    reading = widget.property("readingSurface")
    if not (glass or reading) or widget.property("sectionStyle") == "plain":
        return False
    current = widget.parentWidget()
    while current is not None and current.window() == widget.window():
        backdrop = getattr(current, "backdrop", None)
        if backdrop is not None:
            painter = QPainter(widget)
            backdrop.paint_glass(painter, widget, reading=reading and not glass)
            painter.end()
            return True
        current = current.parentWidget()
    return False


class GlassFrame(QFrame):
    def __init__(self, parent=None, *, glass=False, reading=False):
        super().__init__(parent)
        self.setProperty("glassSurface", glass)
        self.setProperty("readingSurface", reading)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_widget_glass(self)


class GlassWidget(QWidget):
    def __init__(self, parent=None, *, glass=False, reading=False):
        super().__init__(parent)
        self.setProperty("glassSurface", glass)
        self.setProperty("readingSurface", reading)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_widget_glass(self)


class ItemViewSurface(GlassWidget):
    """Paint below an item view's viewport, headers and scroll bars."""

    def __init__(self, view):
        super().__init__(view, reading=True)
        self._headers = ((view.horizontalHeader(), view.verticalHeader()) if isinstance(view, QTableView)
                         else (view.header(),))
        for header in self._headers:
            header.geometriesChanged.connect(self.update)
        view.setProperty("readingView", True)
        view.viewport().setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(view.rect())
        self.lower()
        self.show()
        view.installEventFilter(self)

    def eventFilter(self, view, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(view.rect())
        return False

    def paintEvent(self, event):
        has_backdrop = paint_widget_glass(self)
        app = QApplication.instance()
        colors = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if not has_backdrop:
            painter.setBrush(QColor(colors.surface_raised))
            painter.drawRoundedRect(QRectF(self.rect()), UI_METRICS.card_radius, UI_METRICS.card_radius)
        tint = QColor(colors.surface_raised)
        tint.setAlpha(112)
        painter.setBrush(tint)
        for header in self._headers:
            if header.isVisible():
                radius = UI_METRICS.radius
                painter.drawRoundedRect(QRectF(header.geometry()), radius, radius)
        painter.end()
