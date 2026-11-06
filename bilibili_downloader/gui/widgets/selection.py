"""Session selection shared by import, part, task and file views."""

from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QWidget,
)

from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.responsive_actions import (
    ActionButton,
    ResponsiveActions,
)
from bilibili_downloader.gui.widgets.row_hover import row_option


@dataclass
class SelectionState:
    order: list = field(default_factory=list)
    selected: set = field(default_factory=set)
    visible: set = field(default_factory=set)
    focused: object = None
    reviewing: bool = False

    def reset(self, keys, *, preserve=True):
        self.order = list(dict.fromkeys(keys))
        self.selected = self.selected.intersection(self.order) if preserve else set()
        self.visible.intersection_update(self.order)
        if self.focused not in self.order:
            self.focused = None

    def ids(self):
        return [key for key in self.order if key in self.selected]

    @property
    def outside(self):
        return len(self.selected - self.visible)


class SelectionBar(QWidget):
    select_visible = Signal()
    clear_requested = Signal()
    review_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QBoxLayout
        row = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.row = row
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.summary = QLabel()
        self.summary.setObjectName("MetaLabel")
        self.summary.setWordWrap(True)
        row.addWidget(self.summary, 1)
        self.action_strip = ResponsiveActions(more_text="选择操作")
        self.all_button = ActionButton("全选当前结果")
        self.all_button.setProperty("actionPriority", 50)
        self.review_button = ActionButton("查看已选")
        self.review_button.setProperty("actionPriority", 30)
        self.clear_button = ActionButton("清空全部选择")
        for button, signal in ((self.all_button, self.select_visible), (self.review_button, self.review_requested), (self.clear_button, self.clear_requested)):
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(signal.emit)
            self.action_strip.row.addWidget(button)
        row.addWidget(self.action_strip)

    def update_state(self, state):
        suffix = f"，筛选外 {state.outside} 项" if state.outside else ""
        self.summary.setText(f"显示 {len(state.visible)} / {len(state.order)} 项 · 已选 {len(state.selected)} 项{suffix}")
        self.review_button.setText("返回筛选" if state.reviewing else "查看已选")
        self.review_button.setEnabled(bool(state.selected) or state.reviewing)
        self.clear_button.setEnabled(bool(state.selected))
        self.all_button.setEnabled(bool(state.visible))

    def resizeEvent(self, event):
        from PySide6.QtWidgets import QBoxLayout
        self.row.setDirection(QBoxLayout.TopToBottom if event.size().width() < 480 else QBoxLayout.LeftToRight)
        self.action_strip.schedule()
        super().resizeEvent(event)


class SelectionItem(QTableWidgetItem):
    """Expose session check state to Qt without rewriting every task cell."""

    def __init__(self, text, binding, key):
        super().__init__(text)
        self._binding, self._key = binding, key

    def data(self, role):
        if role == Qt.CheckStateRole and hasattr(self, "_binding"):
            return Qt.Checked.value if self._key in self._binding.state.selected else Qt.Unchecked.value
        return super().data(role)

    def setData(self, role, value):
        if role == Qt.CheckStateRole and hasattr(self, "_binding"):
            checked = value in (Qt.Checked, Qt.Checked.value)
            if checked != (self._key in self._binding.state.selected):
                self._binding.toggle(self._key)
        else:
            super().setData(role, value)


class CheckableRowDelegate(QStyledItemDelegate):
    """Paint a themed checkbox without allocating a widget for each record."""

    def __init__(self, parent, content=None, binding=None):
        super().__init__(parent)
        self.content = content
        self.binding = binding

    def paint(self, painter, option, index):
        state_only = self.binding is not None and self.binding.paint_only and index.data(Qt.UserRole) in self.binding._keys
        if not state_only and index.data(Qt.CheckStateRole) is None:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            return option.widget.style().drawControl(QStyle.CE_ItemViewItem, row_option(opt, index), painter, option.widget)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator
        opt = row_option(opt, index)
        background = QStyleOptionViewItem(opt)
        background.text = ""
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, background, painter, option.widget)
        opt.rect = option.rect.adjusted(30, 0, 0, 0)
        if self.content:
            self.content.paint(painter, opt, index)
        else:
            option.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, option.widget)
        p = palette()
        checked = index.data(Qt.UserRole) in self.binding.state.selected if state_only else index.data(Qt.CheckStateRole) == Qt.Checked.value
        rect = QRect(option.rect.left() + 9, option.rect.center().y() - 8, 16, 16)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(p.accent if checked else p.border_hover), 1.5))
        painter.setBrush(QColor(p.accent if checked else p.surface))
        painter.drawRoundedRect(rect, 4, 4)
        if checked:
            painter.setPen(QPen(QColor(p.accent_text), 1.8))
            painter.drawLine(rect.left() + 4, rect.top() + 8, rect.left() + 7, rect.top() + 11)
            painter.drawLine(rect.left() + 7, rect.top() + 11, rect.left() + 12, rect.top() + 5)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if self.binding is not None and self.binding.paint_only and index.data(Qt.UserRole) in self.binding._keys:
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and event.position().x() <= option.rect.left() + 30:
                self.binding.toggle(index.data(Qt.UserRole))
                return True
            return False
        if index.data(Qt.CheckStateRole) is None:
            return False
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and event.position().x() <= option.rect.left() + 30:
            checked = index.data(Qt.CheckStateRole) == Qt.Checked.value
            return model.setData(index, Qt.Unchecked if checked else Qt.Checked, Qt.CheckStateRole)
        return False


class TableSelection(QObject):
    changed = Signal()
    focus_changed = Signal()

    def __init__(self, table, content_delegate=None, *, paint_only=False):
        super().__init__(table)
        self.table = table
        self.state = SelectionState()
        self.paint_only = paint_only
        self._keys = set()
        self._syncing = False
        table._selection_binding = self
        table.installEventFilter(self)
        table.setItemDelegateForColumn(0, CheckableRowDelegate(table, content_delegate, self))
        table.itemChanged.connect(self._item_changed)
        table.currentItemChanged.connect(self._focus)

    def eventFilter(self, target, event):
        if target is self.table and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.SelectAll):
                self.select_visible()
                return True
            if event.key() == Qt.Key_Space and self.table.currentRow() >= 0:
                item = self.table.item(self.table.currentRow(), 0)
                if item is not None and item.data(Qt.UserRole) in self.state.order:
                    if self.paint_only:
                        self.toggle(item.data(Qt.UserRole))
                        return True
                    item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
                    return True
        return super().eventFilter(target, event)

    def reset(self, keys=None, *, preserve=True):
        if keys is None:
            keys = getattr(self.table.model(), "ids", None)
            if keys is None:
                keys = [self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount()) if self.table.item(row, 0) is not None]
        self.state.reset(keys, preserve=preserve)
        self._keys = set(self.state.order)
        self._paint_checks()

    def _paint_checks(self):
        if self.paint_only:
            blocked = self.table.blockSignals(True)
            self._notify_checks()
            self.table.blockSignals(blocked)
            self.table.viewport().update()
            return
        self._syncing = True
        blocked = self.table.blockSignals(True)
        model = self.table.model()
        model_blocked = model.blockSignals(True)
        known = set(self.state.order)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) in known:
                if not item.flags() & Qt.ItemIsUserCheckable:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                value = Qt.Checked if item.data(Qt.UserRole) in self.state.selected else Qt.Unchecked
                if item.data(Qt.CheckStateRole) is None or item.checkState() != value:
                    item.setCheckState(value)
        model.blockSignals(model_blocked)
        if not model_blocked:
            self._notify_checks()
        self.table.blockSignals(blocked)
        self._syncing = False

    def _notify_checks(self):
        # Offscreen rows read their current state when scrolled into view.
        # Limit view notifications so task index widgets are not all relaid out.
        model = self.table.model()
        if self.table.isVisible() and model.rowCount():
            first = self.table.rowAt(0)
            last = self.table.rowAt(self.table.viewport().height() - 1)
            if first >= 0:
                model.dataChanged.emit(model.index(first, 0), model.index(last if last >= 0 else model.rowCount() - 1, 0), [Qt.CheckStateRole])

    def toggle(self, key):
        if key in self.state.selected:
            self.state.selected.remove(key)
        else:
            self.state.selected.add(key)
        self._paint_checks()
        self.changed.emit()

    def _item_changed(self, item):
        if self._syncing or item.column() != 0:
            return
        key = item.data(Qt.UserRole)
        if key not in self.state.order:
            return
        checked = item.checkState() == Qt.Checked
        if checked != (key in self.state.selected):
            if checked:
                self.state.selected.add(key)
            else:
                self.state.selected.discard(key)
            self.changed.emit()

    def _focus(self, current, _previous):
        item = self.table.item(current.row(), 0) if current else None
        self.state.focused = item.data(Qt.UserRole) if item else None
        self.focus_changed.emit()

    def set_visible(self, keys):
        self.state.visible = set(keys)

    def select_visible(self):
        self.state.selected.update(self.state.visible)
        self._paint_checks()
        self.changed.emit()

    def clear(self):
        self.state.selected.clear()
        self._paint_checks()
        self.changed.emit()

    def select_only_row(self, row):
        item = self.table.item(row, 0)
        if item and item.data(Qt.UserRole) in self.state.order:
            self.state.selected = {item.data(Qt.UserRole)}
            self._paint_checks()
            self.changed.emit()

    def toggle_review(self):
        self.state.reviewing = not self.state.reviewing
        self.changed.emit()
