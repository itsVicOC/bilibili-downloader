"""Theme-aware selectors using Qt's popup placement and keyboard handling."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QToolTip,
)

from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.components import palette, repolish


class _OptionDelegate(QStyledItemDelegate):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # Do not widen the popup for long titles; the complete label is a tooltip.
        return QSize(0, max(UI_METRICS.control_height, opt.fontMetrics.height() + 16))

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        p = palette()
        enabled = bool(opt.state & QStyle.State_Enabled)
        current = index.row() == self.combo.currentIndex()
        highlighted = bool(opt.state & (QStyle.State_Selected | QStyle.State_MouseOver))
        rect = opt.rect.adjusted(0, 2, 0, -2)
        painter.save()
        painter.setClipRect(opt.rect)
        painter.setRenderHint(QPainter.Antialiasing)
        if current or (highlighted and enabled):
            painter.setPen(
                QPen(QColor(p.focus), 1) if highlighted and not current else Qt.NoPen
            )
            painter.setBrush(QColor(p.selection if current else p.surface_raised))
            painter.drawRoundedRect(rect, 6, 6)
        color = p.disabled if not enabled else p.active_text if current else p.text
        painter.setPen(QColor(color))
        painter.setFont(opt.font)
        text_rect = rect.adjusted(12, 0, -36, 0)
        if not opt.icon.isNull():
            icon_rect = QRect(text_rect.left(), rect.center().y() - 8, 16, 16)
            opt.icon.paint(painter, QStyle.visualRect(opt.direction, rect, icon_rect))
            text_rect.adjust(24, 0, 0, 0)
        text_rect = QStyle.visualRect(opt.direction, rect, text_rect)
        alignment = Qt.AlignRight if opt.direction == Qt.RightToLeft else Qt.AlignLeft
        painter.drawText(
            text_rect,
            alignment | Qt.AlignVCenter,
            opt.fontMetrics.elidedText(opt.text, Qt.ElideRight, text_rect.width()),
        )
        if current:
            check_rect = QStyle.visualRect(
                opt.direction,
                rect,
                QRect(rect.right() - 26, rect.center().y() - 7, 14, 14),
            )
            mark = QPainterPath()
            mark.moveTo(check_rect.left() + 2, check_rect.top() + 7)
            mark.lineTo(check_rect.left() + 6, check_rect.top() + 11)
            mark.lineTo(check_rect.left() + 12, check_rect.top() + 3)
            painter.setPen(
                QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            )
            painter.drawPath(mark)
        painter.restore()

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip and index.isValid():
            text = index.data(Qt.ToolTipRole) or index.data(Qt.DisplayRole)
            if text:
                QToolTip.showText(event.globalPos(), str(text), view)
                return True
        return super().helpEvent(event, view, option, index)


class ComboBox(QComboBox):
    """Shared rounded popup, readable options and a persistent current-item mark."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("popupOpen", False)
        self.setMaxVisibleItems(8)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
        view = QListView(self)
        view.setObjectName("ComboPopupList")
        view.setFrameShape(QFrame.NoFrame)
        view.setMouseTracking(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setTextElideMode(Qt.ElideRight)
        self.setView(view)
        self.setItemDelegate(_OptionDelegate(self))
        popup = view.window()
        popup.setObjectName("ComboPopup")
        popup.setAttribute(Qt.WA_TranslucentBackground, True)
        popup.installEventFilter(self)
        self.currentTextChanged.connect(self.setToolTip)

    def eventFilter(self, watched, event):
        # Escape and outside clicks can hide Qt's popup without calling hidePopup.
        if event.type() == QEvent.Hide and watched.objectName() == "ComboPopup":
            if self.property("popupOpen"):
                self.setProperty("popupOpen", False)
                repolish(self)
        return super().eventFilter(watched, event)

    def _sync_popup_state(self):
        visible = self.view().isVisible()
        if visible != self.property("popupOpen"):
            self.setProperty("popupOpen", visible)
            repolish(self)

    def showPopup(self):
        if not self.isEnabled() or not self.count():
            return
        super().showPopup()
        self._sync_popup_state()

    def hidePopup(self):
        super().hidePopup()
        self._sync_popup_state()

    def paintEvent(self, event):
        super().paintEvent(event)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        arrow = (
            self.style()
            .subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self)
            .center()
        )
        p = palette()
        opened = self.property("popupOpen")
        color = (
            p.disabled
            if not self.isEnabled()
            else p.focus
            if opened or self.hasFocus()
            else p.muted
        )
        path = QPainterPath()
        direction = -1 if opened else 1
        path.moveTo(arrow.x() - 5, arrow.y() - 2 * direction)
        path.lineTo(arrow.x(), arrow.y() + 3 * direction)
        path.lineTo(arrow.x() + 5, arrow.y() - 2 * direction)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(
            QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        )
        painter.drawPath(path)
        painter.end()
