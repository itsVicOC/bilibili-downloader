"""Width-aware action presentation; business callbacks stay on their buttons."""

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
    QWidgetItem,
)


class ActionButton(QPushButton):
    """Keep a button and its overflow entry on one action and one callback path."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._overflowed = False
        self._tooltip = ""
        self._requested_enabled = True
        self.action = QAction(text, self)
        self.addAction(self.action)
        self.action.triggered.connect(self.click)
        self.action.changed.connect(self._sync_action)

    def _sync_action(self):
        QPushButton.setText(self, self.action.text())
        if self.action.isVisible():
            self._requested_enabled = self.action.isEnabled()
        QPushButton.setEnabled(self, self._requested_enabled)
        QPushButton.setToolTip(self, self._tooltip)
        if self.parentWidget() is not None or not self.action.isVisible():
            QPushButton.setVisible(self, self.action.isVisible() and not self._overflowed)

    def setText(self, text):
        if hasattr(self, "action"):
            self.action.setText(text)
        else:
            super().setText(text)

    def setEnabled(self, enabled):
        if hasattr(self, "action"):
            self._requested_enabled = enabled
            self.action.setEnabled(enabled)
            self._sync_action()
        else:
            super().setEnabled(enabled)

    def setToolTip(self, text):
        if hasattr(self, "action"):
            self._tooltip = text
            self.action.setToolTip(text)
            self._sync_action()
        else:
            super().setToolTip(text)

    def setVisible(self, visible):
        if hasattr(self, "action"):
            self.action.setVisible(visible)
            self._sync_action()
        else:
            super().setVisible(visible)

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def setHidden(self, hidden):
        self.setVisible(not hidden)

    def setDisabled(self, disabled):
        self.setEnabled(not disabled)

    def set_overflowed(self, overflowed):
        if self._overflowed != overflowed:
            self._overflowed = overflowed
            self._sync_action()


class _ActionLayout(QBoxLayout):
    def __init__(self, owner):
        super().__init__(QBoxLayout.LeftToRight, owner)
        self.owner = owner
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)
        self.setSizeConstraint(QLayout.SetNoConstraint)

    def addWidget(self, widget, stretch=0, alignment=Qt.Alignment()):
        self.owner.register(widget)
        anchor = self.owner.more
        position = self.indexOf(anchor)
        QBoxLayout.insertWidget(self, position if position >= 0 and widget is not anchor else self.count(), widget, stretch, alignment)

    def insertWidget(self, index, widget, stretch=0, alignment=Qt.Alignment()):
        self.owner.register(widget)
        super().insertWidget(index, widget, stretch, alignment)


class ResponsiveActions(QWidget):
    """Collapse lower-priority actions before wrapping indispensable controls."""

    def __init__(self, parent=None, *, more_text="更多"):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._buttons = []
        self._queued = False
        self._overflow = ()
        self._forced = set()
        self._own_more = QPushButton(more_text, self)
        self._own_more.setObjectName("TableSubtleButton")
        self._own_more.setProperty("menuButton", True)
        self._own_more.setAccessibleName(more_text)
        menu = QMenu(self._own_more)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        self._own_more.setMenu(menu)
        menu.aboutToShow.connect(self.reflow)
        self.more = self._own_more
        self._extra_entries = []
        self.row = _ActionLayout(self)
        QBoxLayout.addWidget(self.row, self.more)
        self.more.hide()

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def sizeHint(self):
        buttons = [b for b in self._buttons if b.action.isVisible() and b not in self._forced]
        widths = [max(b.minimumWidth(), b.sizeHint().width()) for b in buttons]
        if self._forced or self.more is not self._own_more:
            widths.append(self.more.sizeHint().width())
        return QSize(sum(widths) + 8 * max(0, len(widths) - 1), self.row.sizeHint().height())

    def register(self, button):
        if button is self.more or button is self._own_more or button in self._buttons:
            return
        if isinstance(button, QPushButton) and button.menu() is not None:
            self.row.removeWidget(self.more)
            self.more.hide()
            self.more = button
            self.more.setProperty("alwaysVisible", True)
            button.menu().aboutToShow.connect(self.reflow)
        elif isinstance(button, ActionButton):
            self._buttons.append(button)
            button.action.changed.connect(self.schedule)
        self.schedule()

    def force_overflow(self, button, forced):
        before = set(self._forced)
        self._forced.add(button) if forced else self._forced.discard(button)
        if before != self._forced:
            self.schedule()

    def schedule(self, *_args):
        if not self._queued:
            self._queued = True
            QTimer.singleShot(0, self, self.reflow)

    def reflow(self):
        self._queued = False
        buttons = [b for b in self._buttons if b.action.isVisible()]
        visible = [b for b in buttons if b not in self._forced]
        hidden = [b for b in buttons if b in self._forced]
        spacing = self.row.spacing()
        external = self.more is not self._own_more
        def required():
            widths = [max(b.minimumWidth(), b.sizeHint().width()) for b in visible]
            if hidden or external:
                widths.append(self.more.sizeHint().width())
            return sum(widths) + spacing * max(0, len(widths) - 1)
        candidates = sorted((b for b in visible if not b.property("alwaysVisible")),
                            key=lambda b: (b.property("actionPriority") or 0, self._buttons.index(b)))
        while candidates and required() > self.width():
            button = candidates.pop(0)
            visible.remove(button)
            hidden.append(button)
        hidden = tuple(b for b in buttons if b in hidden)
        focus = QApplication.focusWidget()
        if hidden != self._overflow:
            menu = self.more.menu()
            if menu.isVisible():
                menu.hide()
                self.more.setFocus(Qt.OtherFocusReason)
            for action in self._extra_entries:
                menu.removeAction(action)
                if action.isSeparator():
                    action.deleteLater()
            self._extra_entries = []
            if hidden and external:
                self._extra_entries.append(menu.addSeparator())
            for button in hidden:
                menu.addAction(button.action)
                self._extra_entries.append(button.action)
            self._overflow = hidden
        self.more.setVisible(bool(hidden) or external)
        for button in self._buttons:
            if button in hidden and focus is button:
                self.more.setFocus(Qt.OtherFocusReason)
            button.set_overflowed(button in hidden)
        direction = QBoxLayout.TopToBottom if required() > self.width() else QBoxLayout.LeftToRight
        if self.row.direction() != direction:
            self.row.setDirection(direction)
        self.updateGeometry()

    def event(self, event):
        if event.type() in (QEvent.LayoutRequest, QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "row"):
            self.schedule()
        return super().event(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule()


class FlowLayout(QLayout):
    """Wrap compact result badges without allocating per-record widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)

    def addItem(self, item):
        self._items.append(item)

    def insertWidget(self, index, widget):
        self.addChildWidget(widget)
        self._items.insert(index, QWidgetItem(widget))
        self.invalidate()

    def addStretch(self, *_args):
        pass

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(width)

    def minimumSize(self):
        return QSize(max((i.minimumSize().width() for i in self._items if not i.isEmpty()), default=0), 0)

    def sizeHint(self):
        items = [i for i in self._items if not i.isEmpty()]
        return QSize(sum(i.sizeHint().width() for i in items) + self.spacing() * max(0, len(items) - 1),
                     max((i.sizeHint().height() for i in items), default=0))

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect.width(), rect)

    def _arrange(self, width, rect=None):
        lines, line, used = [], [], 0
        for item in self._items:
            if item.isEmpty():
                continue
            needed = min(width, item.sizeHint().width())
            if line and used + self.spacing() + needed > width:
                lines.append(line)
                line, used = [], 0
            used += (self.spacing() if line else 0) + needed
            line.append(item)
        if line:
            lines.append(line)
        y = 0
        for line in lines:
            sizes = [item.sizeHint() for item in line]
            height = max(size.height() for size in sizes)
            occupied = sum(min(width, size.width()) for size in sizes) + self.spacing() * (len(line) - 1)
            expanders = sum(bool(item.expandingDirections() & Qt.Horizontal) for item in line)
            extra = max(0, width - occupied) // max(1, expanders)
            x = 0
            for item, size in zip(line, sizes):
                item_width = min(width, size.width()) + (extra if item.expandingDirections() & Qt.Horizontal else 0)
                if rect is not None:
                    from PySide6.QtCore import QRect
                    item.setGeometry(QRect(rect.x() + x, rect.y() + y, item_width, height))
                x += item_width + self.spacing()
            y += height + self.spacing()
        return max(0, y - self.spacing())
