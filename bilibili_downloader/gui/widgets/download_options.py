"""Keyboard-accessible download cards with native checkbox semantics."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import UI_METRICS, blend_color
from bilibili_downloader.gui.widgets.check_box import draw_check_indicator
from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.motion import StateTransition


class DownloadOptionCard(QCheckBox):
    def __init__(self, text, description, icon, parent=None):
        super().__init__(text, parent)
        self.description = description
        self.icon_name = icon
        self.setObjectName("DownloadOptionCard")
        self.setAccessibleDescription(description)
        self.setToolTip(f"{text} · {description}")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.setAttribute(Qt.WA_Hover)
        self.setFixedHeight(UI_METRICS.option_card_height)
        self._selection = StateTransition(self)
        self._hover = StateTransition(self)
        self.toggled.connect(lambda checked: self._selection.to(float(checked)))

    def sizeHint(self):
        title_font = self.font()
        title_font.setWeight(title_font.Weight.Medium)
        detail_font = self.font()
        if detail_font.pointSizeF() > 0:
            detail_font.setPointSizeF(detail_font.pointSizeF() * .82)
        else:
            detail_font.setPixelSize(max(1, round(detail_font.pixelSize() * .82)))
        width = (40 + QFontMetrics(title_font).horizontalAdvance(self.text()) + 8
                 + QFontMetrics(detail_font).horizontalAdvance(getattr(self, "description", "")) + 28)
        return QSize(max(240, width), UI_METRICS.option_card_height)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def event(self, event):
        if hasattr(self, "_hover"):
            if event.type() == QEvent.HoverEnter:
                self._hover.to(1)
            elif event.type() == QEvent.HoverLeave:
                self._hover.to(0)
        if event.type() in (
            QEvent.HoverEnter,
            QEvent.HoverLeave,
            QEvent.FocusIn,
            QEvent.FocusOut,
        ):
            self.update()
        if event.type() in (QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "_selection"):
            self.setFixedHeight(max(UI_METRICS.option_card_height, self.fontMetrics().height() + 12))
        return super().event(event)

    def paintEvent(self, event):
        colors = palette()
        enabled = self.isEnabled()
        checked = self.isChecked()
        foreground = colors.text if enabled else colors.disabled
        fill = blend_color(colors.control_fill, colors.control_hover, self._hover.value)
        if enabled:
            fill = blend_color(fill, colors.subtle_selection, self._selection.value)
        else:
            fill = colors.control_fill
        border = colors.border_hover if self.underMouse() and enabled else colors.popup_border
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(border), UI_METRICS.border_width))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), UI_METRICS.radius, UI_METRICS.radius)
        size = UI_METRICS.indicator_size
        indicator = QRect(12, (self.height() - size) // 2, size, size)
        draw_check_indicator(painter, indicator, checked=checked, enabled=enabled,
                             hovered=self.underMouse(), pressed=self.isDown())
        painter.setPen(QColor(foreground))
        font = self.font()
        font.setWeight(font.Weight.Medium)
        painter.setFont(font)
        title_font = painter.font()
        font.setWeight(font.Weight.Normal)
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 0.82)
        else:
            font.setPixelSize(max(1, round(font.pixelSize() * .82)))
        painter.setFont(font)
        tag_width = painter.fontMetrics().horizontalAdvance(self.description) + 16
        detail = QRect(self.width() - 12 - tag_width, (self.height() - 24) // 2, tag_width, 24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors.control_fill))
        painter.drawRoundedRect(detail, 4, 4)
        painter.setPen(QColor(colors.muted if enabled else colors.disabled))
        painter.drawText(detail, Qt.AlignCenter, self.description)
        painter.setFont(title_font)
        painter.setPen(QColor(foreground))
        text_rect = QRect(40, 0, max(0, detail.left() - 48), self.height())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(self.text(), Qt.ElideRight, text_rect.width()))


class DownloadOptions(QWidget):
    """One responsive grid, with the dependent language option below subtitles."""

    def __init__(self, danmaku, subtitle, all_subtitles, cover, metadata, parent=None, *, max_columns=1):
        super().__init__(parent)
        self._cards = (danmaku, subtitle, cover, metadata)
        self._max_columns = max_columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        self._grid.setSizeConstraint(QLayout.SetMinimumSize)
        self._subtitle = QWidget()
        row = QVBoxLayout(self._subtitle)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(subtitle)
        all_subtitles.setMinimumHeight(24)
        dependency = QWidget()
        indent = QVBoxLayout(dependency)
        indent.setContentsMargins(40, 0, 0, 0)
        indent.addWidget(all_subtitles)
        row.addWidget(dependency)
        self._columns = 0
        self._reflow(1)

    def _reflow(self, columns):
        if self._columns == columns:
            return
        self._columns = columns
        widgets = (self._cards[0], self._subtitle, *self._cards[2:])
        for widget in widgets:
            self._grid.removeWidget(widget)
        for index, widget in enumerate(widgets):
            self._grid.addWidget(widget, index // columns, index % columns, Qt.AlignTop)
        for column in range(2):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event):
        self._reflow(2 if self._max_columns == 2 and event.size().width() >= 600 else 1)
        super().resizeEvent(event)
