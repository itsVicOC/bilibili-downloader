"""Keyboard-accessible download cards with native checkbox semantics."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.components import line_icon, palette


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
        self.setMinimumWidth(124)
        self.setFixedHeight(UI_METRICS.option_card_height)

    def sizeHint(self):
        return QSize(148, UI_METRICS.option_card_height)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def event(self, event):
        if event.type() in (
            QEvent.HoverEnter,
            QEvent.HoverLeave,
            QEvent.FocusIn,
            QEvent.FocusOut,
        ):
            self.update()
        return super().event(event)

    def paintEvent(self, event):
        colors = palette()
        enabled = self.isEnabled()
        checked = self.isChecked()
        foreground = colors.text if enabled else colors.disabled
        accent = colors.active_text if enabled else colors.disabled
        fill = colors.selection if checked and enabled else colors.surface_raised
        border = (
            colors.focus
            if self.hasFocus() and self.property("keyboardFocus") is not False
            else (
                colors.accent
                if checked and enabled
                else colors.border_hover
                if self.underMouse() and enabled
                else colors.divider
            )
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(border), 1.5))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        line_icon(self.icon_name, accent if checked else foreground).paint(
            painter, QRect(12, 12, 18, 18)
        )
        indicator = QRect(self.width() - 28, 13, 14, 14)
        painter.setPen(QPen(QColor(accent if checked else colors.border), 1.4))
        painter.setBrush(
            QColor(colors.accent if checked and enabled else colors.surface)
        )
        painter.drawRoundedRect(indicator, 4, 4)
        if checked:
            painter.setPen(
                QPen(
                    QColor(colors.accent_text if enabled else colors.disabled),
                    1.8,
                    Qt.SolidLine,
                    Qt.RoundCap,
                    Qt.RoundJoin,
                )
            )
            x, y = indicator.x(), indicator.y()
            painter.drawLine(x + 3, y + 7, x + 6, y + 10)
            painter.drawLine(x + 6, y + 10, x + 11, y + 4)
        painter.setPen(QColor(foreground))
        font = self.font()
        font.setWeight(font.Weight.Medium)
        painter.setFont(font)
        text_rect = QRect(12, 36, self.width() - 24, max(20, self.fontMetrics().height() + 4))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        # A short format label sits alongside the icon, leaving the title intact.
        font.setWeight(font.Weight.Normal)
        font.setPointSizeF(font.pointSizeF() * 0.82)
        painter.setFont(font)
        painter.setPen(QColor(colors.muted if enabled else colors.disabled))
        detail = QRect(36, 10, max(0, self.width() - 70), 22)
        painter.drawText(
            detail,
            Qt.AlignVCenter,
            painter.fontMetrics().elidedText(
                self.description, Qt.ElideRight, detail.width()
            ),
        )


class DownloadOptions(QWidget):
    """One responsive grid, with the dependent language option below subtitles."""

    def __init__(self, danmaku, subtitle, all_subtitles, cover, metadata, parent=None):
        super().__init__(parent)
        self._cards = (danmaku, subtitle, cover, metadata)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        self._grid.setSizeConstraint(QLayout.SetMinimumSize)
        self._subtitle = QWidget()
        row = QVBoxLayout(self._subtitle)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(subtitle)
        row.addWidget(all_subtitles)
        self._columns = 0
        self._reflow(2)

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
        self._reflow(2 if event.size().width() >= 272 else 1)
        super().resizeEvent(event)
