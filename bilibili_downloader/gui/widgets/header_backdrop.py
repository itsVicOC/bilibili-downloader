"""Theme decoration concentrated in the shared workspace header."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QRadialGradient

from bilibili_downloader.gui.resources.styles import theme_palette


def paint_header_backdrop(painter, rect, is_dark, theme_id):
    """Leave title space quiet and place the brand motif toward the right edge."""
    p = theme_palette(is_dark, theme_id)
    rect = QRectF(rect)
    if rect.isEmpty():
        return
    painter.save()
    painter.setClipRect(rect)
    painter.translate(rect.topLeft())
    width, height = rect.width(), rect.height()
    bounds = QRectF(0, 0, width, height)
    blue = theme_id == "bilibili_blue"
    sky = QLinearGradient(0, 0, width, 0)
    sky.setColorAt(0, QColor(p.surface))
    sky.setColorAt(0.35, QColor(p.surface))
    sky.setColorAt(0.7, QColor(p.hero_start or p.surface_raised))
    sky.setColorAt(1, QColor(p.hero_end or p.selection))
    painter.fillRect(bounds, sky)

    glow = QRadialGradient(width * 0.84, -height * 0.3, max(height * 2, width * 0.3))
    tint = QColor(p.hero_secondary or p.selection)
    tint.setAlpha(52 if is_dark else 64)
    glow.setColorAt(0, tint)
    tint.setAlpha(0)
    glow.setColorAt(1, tint)
    painter.fillRect(bounds, glow)

    wave = QPainterPath()
    wave.moveTo(width * 0.47, height)
    wave.cubicTo(
        width * 0.68, height * 0.08,
        width * 0.83, height * 1.2,
        width, height * 0.28,
    )
    wave.lineTo(width, height)
    wave.closeSubpath()
    tint = QColor(p.accent if blue or is_dark else p.selection)
    tint.setAlpha(20 if is_dark else 16 if blue else 80)
    painter.fillPath(wave, tint)

    if not blue:
        orbit = QPainterPath()
        orbit.moveTo(width * 0.57, height * 1.12)
        orbit.cubicTo(
            width * 0.68, -height * 0.38,
            width * 0.89, -height * 0.05,
            width * 1.03, height * 0.58,
        )
        tint = QColor(p.accent)
        tint.setAlpha(14 if is_dark else 8)
        painter.setPen(QPen(tint, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(orbit)
        tint.setAlpha(28 if is_dark else 12)
        painter.setPen(QPen(tint, 1.2))
        for x, y, size in ((0.72, 0.28, 3), (0.86, 0.58, 2), (0.95, 0.22, 3)):
            cx, cy = width * x, height * y
            painter.drawLine(QPointF(cx - size, cy), QPointF(cx + size, cy))
            painter.drawLine(QPointF(cx, cy - size), QPointF(cx, cy + size))
    painter.restore()
