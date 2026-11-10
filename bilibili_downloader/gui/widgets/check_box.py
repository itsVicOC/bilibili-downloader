"""Native checkbox semantics with one indicator shared by cards and tables."""

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QCheckBox, QStyle, QStyleOptionButton

from bilibili_downloader.gui.resources.styles import UI_METRICS, theme_palette


def draw_check_indicator(painter, rect, *, checked=False, partial=False, enabled=True, hovered=False, pressed=False):
    app = QApplication.instance()
    p = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
    selected = checked or partial
    fill = (p.primary_pressed if pressed else p.primary_hover if hovered else p.primary) if selected else p.control_pressed if pressed else p.control_hover if hovered else p.surface
    border = fill if selected else p.border_hover if hovered else p.control_border
    if not enabled:
        fill = p.border if selected else p.surface_raised
        border = p.border if selected else p.divider
    rect = QRectF(rect).adjusted(.5, .5, -.5, -.5)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(border), UI_METRICS.border_width))
    painter.setBrush(QColor(fill))
    painter.drawRoundedRect(rect, UI_METRICS.small_radius, UI_METRICS.small_radius)
    if selected:
        mark = QPainterPath()
        if partial:
            mark.moveTo(rect.left() + 4, rect.center().y())
            mark.lineTo(rect.right() - 4, rect.center().y())
        else:
            mark.moveTo(rect.left() + 3.5, rect.top() + 8.5)
            mark.lineTo(rect.left() + 7, rect.top() + 12)
            mark.lineTo(rect.left() + 13.5, rect.top() + 5)
        painter.setPen(QPen(QColor(p.primary_text if enabled else p.surface), UI_METRICS.icon_stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(mark)
    painter.restore()


class CheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.setMinimumHeight(UI_METRICS.compact_button_height)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self.setMinimumHeight(max(UI_METRICS.compact_button_height, self.fontMetrics().height() + 8))

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QPainter(self)
        label = QStyleOptionButton(option)
        label.rect = self.style().subElementRect(QStyle.SE_CheckBoxContents, option, self)
        self.style().drawControl(QStyle.CE_CheckBoxLabel, label, painter, self)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        draw_check_indicator(painter, rect, checked=self.isChecked(), partial=self.checkState() == Qt.PartiallyChecked,
                             enabled=self.isEnabled(), hovered=self.underMouse(), pressed=self.isDown())
