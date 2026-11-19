"""Cached wallpaper glass; native Qt text is painted separately and stays sharp."""

from PIL import Image, ImageEnhance, ImageFilter
from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QFrame, QWidget

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR
from bilibili_downloader.gui.resources.styles import contrast_ratio, glass_text_color


class GlassBackdrop:
    """Cached wallpaper and contrast-adjusted glass for one rendering surface."""

    def __init__(self):
        self.key = None
        self.image = QPixmap()
        self.original = QPixmap()
        self.scale = (1.0, 1.0)
        self.dark = False

    def clear(self):
        self.key = None
        self.image = QPixmap()
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
        picture = ImageEnhance.Color(picture).enhance(.90)
        picture = picture.filter(ImageFilter.GaussianBlur(blur * self.scale[0]))
        foregrounds = (colors.text, colors.muted, glass_text_color(colors))
        # Bound every channel, so even black/white art keeps text readable.
        candidates = range(255, -1, -1) if dark else range(256)
        bound = next(value for value in candidates if all(
            contrast_ratio(fg, f"#{value:02x}{value:02x}{value:02x}") >= (5.5 if dark else 5.0)
            for fg in foregrounds
        ))
        surface = QColor(colors.surface)
        channels = []
        for channel, tint in zip(picture.split(), (surface.red(), surface.green(), surface.blue())):
            # Compress the tonal range; clipping bright channels flattens the
            # colors into a grey block over most of an illustrated wallpaper.
            low = min(bound, round(tint * .55)) if dark else bound
            high = bound if dark else max(bound, round(tint * .25 + 255 * .75))
            lut = [round(low + (high - low) * value / 255) for value in range(256)]
            channels.append(channel.point(lut))
        picture = Image.merge("RGB", channels).convert("RGBA")
        data = picture.tobytes()
        self.image = QPixmap.fromImage(QImage(data, picture.width, picture.height, picture.width * 4, QImage.Format_RGBA8888).copy())
        self.key, self.dark = key, dark

    def paint(self, painter, rect, source_rect, radius=18):
        if self.image.isNull():
            return
        rect = QRectF(rect).adjusted(2, 2, -2, -3)
        if rect.isEmpty():
            return
        source = QRectF(source_rect)
        sx, sy = self.scale
        source = QRectF(source.x() * sx, source.y() * sy, source.width() * sx, source.height() * sy)
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


def paint_widget_glass(widget):
    if not widget.property("glassSurface") or widget.property("sectionStyle") == "plain":
        return False
    current = widget.parentWidget()
    while current is not None and current.window() == widget.window():
        backdrop = getattr(current, "backdrop", None)
        if backdrop is not None:
            painter = QPainter(widget)
            backdrop.paint_glass(painter, widget)
            painter.end()
            return True
        current = current.parentWidget()
    return False


class GlassFrame(QFrame):
    def __init__(self, parent=None, *, glass=False):
        super().__init__(parent)
        self.setProperty("glassSurface", glass)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_widget_glass(self)


class GlassWidget(QWidget):
    def __init__(self, parent=None, *, glass=False):
        super().__init__(parent)
        self.setProperty("glassSurface", glass)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_widget_glass(self)
