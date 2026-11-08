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
from bilibili_downloader.gui.resources.styles import (
    UI_METRICS,
    contrast_ratio,
    glass_text_color,
)


class GlassBackdrop:
    """One blurred image per workspace, shared by cards even while scrolling."""

    def __init__(self):
        self.key = None
        self.image = QPixmap()
        self.original = QPixmap()
        self.scale = 1.0
        self.dark = False

    def clear(self):
        self.key = None
        self.image = QPixmap()
        self.original = QPixmap()

    def prepare(self, key, size, render, dark, colors, blur=DEFAULT_GLASS_BLUR):
        key = (key, size.width(), size.height(), dark, colors, blur)
        if key == self.key:
            return
        if size.isEmpty():
            self.clear()
            return
        # Only wallpaper is downsampled. Controls never enter this cache.
        sample = size.scaled(QSize(1200, 900), Qt.KeepAspectRatio)
        if sample.width() > size.width():
            sample = size
        self.scale = sample.width() / size.width()
        base = QImage(sample, QImage.Format_RGBA8888)
        base.fill(Qt.transparent)
        painter = QPainter(base)
        painter.scale(sample.width() / size.width(), sample.height() / size.height())
        render(painter, QRectF(QPoint(), size))
        painter.end()
        self.original = QPixmap.fromImage(base)
        picture = Image.frombytes("RGBA", (base.width(), base.height()), base.bits().tobytes()).convert("RGB")
        picture = ImageEnhance.Color(picture).enhance(.82)
        picture = picture.filter(ImageFilter.GaussianBlur(blur * self.scale))
        foregrounds = (colors.text, glass_text_color(colors))
        # Bound every channel, so even black/white art keeps text readable.
        candidates = range(255, -1, -1) if dark else range(256)
        bound = next(value for value in candidates if all(
            contrast_ratio(fg, f"#{value:02x}{value:02x}{value:02x}") >= (5.5 if dark else 5.0)
            for fg in foregrounds
        ))
        surface = QColor(colors.surface)
        channels = []
        for channel, tint in zip(picture.split(), (surface.red(), surface.green(), surface.blue())):
            lut = [round(value * .68 + tint * .32) for value in range(256)]
            lut = [min(bound, value) if dark else max(bound, value) for value in lut]
            channels.append(channel.point(lut))
        picture = Image.merge("RGB", channels).convert("RGBA")
        data = picture.tobytes()
        self.image = QPixmap.fromImage(QImage(data, picture.width, picture.height, picture.width * 4, QImage.Format_RGBA8888).copy())
        self.key, self.dark = key, dark

    def paint(self, painter, rect, source_rect, radius=UI_METRICS.card_radius):
        if self.image.isNull():
            return
        rect = QRectF(rect).adjusted(.75, .75, -.75, -1.5)
        source = QRectF(source_rect)
        source = QRectF(source.x() * self.scale, source.y() * self.scale, source.width() * self.scale, source.height() * self.scale)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setPen(QPen(QColor(0, 0, 0, 38 if self.dark else 24), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.translated(0, 1), radius, radius)
        painter.setClipPath(path, Qt.IntersectClip)
        painter.drawPixmap(rect, self.image, source)
        # A refracted rim adds depth without distorting the text region.
        inner = QPainterPath()
        inner.addRoundedRect(rect.adjusted(3, 3, -3, -3), max(1, radius - 3), max(1, radius - 3))
        painter.save()
        painter.setClipPath(path.subtracted(inner), Qt.IntersectClip)
        painter.setOpacity(.07)
        painter.drawPixmap(rect, self.original, source.adjusted(2, 2, -2, -2))
        painter.restore()
        shine = QLinearGradient(rect.topLeft(), rect.bottomRight())
        shine.setColorAt(0, QColor(255, 255, 255, 10 if self.dark else 24))
        shine.setColorAt(.24, QColor(255, 255, 255, 6))
        shine.setColorAt(.70, QColor(255, 255, 255, 0))
        shine.setColorAt(1, QColor(255, 255, 255, 8 if self.dark else 12))
        painter.fillPath(path, shine)
        rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        rim.setColorAt(0, QColor(255, 255, 255, 42 if self.dark else 100))
        rim.setColorAt(.45, QColor(255, 255, 255, 16 if self.dark else 36))
        rim.setColorAt(1, QColor(0, 0, 0, 32 if self.dark else 18))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rim, 1))
        painter.drawPath(path)
        painter.restore()


def paint_widget_glass(widget):
    current = widget.parentWidget()
    while current is not None and current.window() == widget.window():
        if hasattr(current, "paint_glass"):
            if not current.property("customBackground"):
                return False
            painter = QPainter(widget)
            current.paint_glass(painter, widget)
            painter.end()
            return True
        current = current.parentWidget()
    return False


class GlassFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("glassSurface", True)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_widget_glass(self)


class GlassWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("glassSurface", True)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_widget_glass(self)
