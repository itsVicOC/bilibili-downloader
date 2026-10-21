"""Local text protection without adding widgets or changing page geometry."""

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOptionButton,
)

from bilibili_downloader.gui.resources.styles import (
    background_reading_alpha,
    theme_palette,
)


def wallpaper_active(widget):
    window = widget.window()
    current = widget
    while current is not None and current.window() == window:
        if current.property("customBackground"):
            return True
        current = current.parentWidget()
    return False


def paint_reading_surface(painter, rect, surface, *foregrounds):
    color = QColor(surface)
    color.setAlpha(background_reading_alpha(surface, *foregrounds))
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(rect), 5, 5)
    painter.restore()


class BackgroundReadability(QObject):
    """Paint underneath native text, clipped by each widget and its viewport.

    An application paint filter covers dynamically created labels too. It only
    handles descendants of this workspace in the same window, so dialogs,
    menus and ordinary theme surfaces retain their native appearance.
    """

    def __init__(self, stack):
        super().__init__(stack)
        self.stack = stack
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, widget, event):
        if event.type() != QEvent.Paint or not self.stack.property("customBackground"):
            return False
        if not isinstance(widget, (QLabel, QCheckBox, QPushButton)):
            return False
        if widget.objectName() == "DownloadOptionCard":
            return False
        if widget.window() != self.stack.window() or not self.stack.isAncestorOf(widget):
            return False
        text = widget.text()
        if not text or (isinstance(widget, QLabel) and not widget.pixmap().isNull()):
            return False
        current = widget
        while current != self.stack:
            if current.objectName() in {
                "ActionBar", "OutputActionBar", "ToolSurface", "Notice", "StatusBadge",
                "StatusPill", "EmptyCover", "LoginInstructions", "WarningBanner",
                "Panel", "SectionCard", "ControlPanel", "SettingsSection", "HeroPanel",
            }:
                return False
            current = current.parentWidget()
        if isinstance(widget, QPushButton) and widget.objectName() not in {
            "GhostButton", "TextButton", "TableRemoveButton", "ActivityButton",
        }:
            return False
        rect = widget.contentsRect()
        alignment = Qt.AlignLeft | Qt.AlignVCenter
        if isinstance(widget, QLabel):
            alignment = widget.alignment()
            if widget.wordWrap():
                alignment |= Qt.TextWordWrap
        elif isinstance(widget, QCheckBox):
            option = QStyleOptionButton()
            widget.initStyleOption(option)
            rect = widget.style().subElementRect(QStyle.SE_CheckBoxContents, option, widget)
        else:
            alignment = Qt.AlignCenter
        bounds = widget.fontMetrics().boundingRect(rect, int(alignment), text)
        bounds = bounds.adjusted(-5, -3, 5, 3).intersected(widget.rect())
        if bounds.isEmpty():
            return False
        app = QApplication.instance()
        colors = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        role = QPalette.ButtonText if isinstance(widget, QPushButton) else QPalette.WindowText
        foreground = widget.palette().color(role).name()
        painter = QPainter(widget)
        paint_reading_surface(painter, bounds, colors.surface, foreground)
        painter.end()
        return False
