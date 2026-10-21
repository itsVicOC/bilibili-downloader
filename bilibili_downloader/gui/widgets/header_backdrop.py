"""Quiet, continuous chrome shared by the workspace and its preview."""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from bilibili_downloader.gui.resources.styles import theme_palette

HEADER_HEIGHT = 56


def paint_header_backdrop(painter, rect, is_dark, theme_id):
    """Draw only the workspace toolbar; the sidebar owns its full-height surface."""
    p = theme_palette(is_dark, theme_id)
    rect = QRectF(rect)
    if rect.isEmpty():
        return
    painter.save()
    painter.setClipRect(rect)
    painter.translate(rect.topLeft())
    painter.fillRect(QRectF(0, 0, rect.width(), rect.height()), QColor(p.background))
    painter.fillRect(QRectF(0, rect.height() - 1, rect.width(), 1), QColor(p.divider))
    painter.restore()
