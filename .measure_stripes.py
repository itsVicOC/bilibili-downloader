"""Measure the screenshot response to identical 24-logical-pixel wallpaper stripes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, qVersion
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR
from bilibili_downloader.gui.resources.styles import theme_palette
from bilibili_downloader.gui.widgets.glass_surface import GlassBackdrop

app = QApplication([])
size = QSize(480, 94)
rect = QRectF(QPoint(), size)
swatch = QImage(size, QImage.Format_RGB32)
stripes = QPainter(swatch)
for col in range(0, size.width(), 24):
    stripes.fillRect(col, 0, 24, size.height(), Qt.black if col // 24 % 2 == 0 else Qt.white)
stripes.end()

measurements = []
for theme in ("star_trail", "bilibili_blue"):
    for dark in (False, True):
        colors = theme_palette(dark, theme)
        glass = GlassBackdrop()
        glass.prepare(theme, size, lambda painter, target: painter.drawImage(target, swatch),
                      dark, colors, DEFAULT_GLASS_BLUR)
        sample = QImage(size, QImage.Format_RGB32)
        sample.fill(QColor(colors.background))
        paint = QPainter(sample)
        if hasattr(glass, "clear_image"):
            glass.paint(paint, rect, rect, clear=True)
        else:
            glass.paint(paint, rect, rect)
        paint.end()
        centers = [sample.pixelColor(x, size.height() // 2).lightness()
                   for x in range(108, size.width() - 96, 24)]
        delta = sum(abs(a - b) for a, b in zip(centers, centers[1:])) / (len(centers) - 1)
        measurements.append({"theme": theme, "mode": "dark" if dark else "light", "delta": delta, "sample": centers})
print(json.dumps({"backend": app.platformName(), "qt": qVersion(), "stripe_width": 24,
                  "blur": DEFAULT_GLASS_BLUR, "measurements": measurements}, indent=2))
