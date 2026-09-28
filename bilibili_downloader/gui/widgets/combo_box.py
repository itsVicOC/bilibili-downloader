"""Theme-aware selectors with anchored popups and Qt's input handling."""

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
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


def popup_geometry(anchor: QRect, preferred: QSize, available: QRect) -> QRect:
    """Align with the field and choose the side with enough screen space.

    All coordinates are logical pixels, including on Retina and mixed-DPI screens.
    """
    gap = 4
    width = min(anchor.width(), available.width())
    x = max(available.left(), min(anchor.left(), available.right() + 1 - width))
    below_y = anchor.bottom() + 1 + gap
    below = max(0, available.bottom() + 1 - below_y)
    above_bottom = anchor.top() - gap
    above = max(0, above_bottom - available.top())
    height = preferred.height()
    opens_below = height <= below or (height > above and below >= above)
    height = max(1, min(height, below if opens_below else above))
    y = below_y if opens_below else above_bottom - height
    y = max(available.top(), min(y, available.bottom() + 1 - height))
    return QRect(x, y, width, height)


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
        self._position_popup()
        self._sync_popup_state()

    def _position_popup(self):
        """Replace native list-box offsets while retaining Qt's input handling."""
        view = self.view()
        popup = view.window()
        anchor = QRect(self.mapToGlobal(QPoint()), self.size())
        screen = QGuiApplication.screenAt(anchor.center()) or self.screen()
        if not screen or not popup.isVisible():
            return
        rows = min(self.count(), self.maxVisibleItems())
        height = sum(max(1, view.sizeHintForRow(row)) for row in range(rows))
        for margins in (view.contentsMargins(), popup.contentsMargins()):
            height += margins.top() + margins.bottom()
        if popup.layout():
            margins = popup.layout().contentsMargins()
            height += margins.top() + margins.bottom()
        popup.setGeometry(
            popup_geometry(anchor, QSize(self.width(), height), screen.availableGeometry())
        )
        view.doItemsLayout()
        view.scrollTo(view.currentIndex(), QAbstractItemView.EnsureVisible)

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
