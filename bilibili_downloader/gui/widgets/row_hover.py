"""View-owned row feedback, including index widgets, without model mutations."""

import weakref

from PySide6.QtCore import QEvent, QObject, QPersistentModelIndex, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTreeWidget,
    QWidget,
)
from shiboken6 import isValid

from bilibili_downloader.gui.widgets.components import palette


def row_option(option, index):
    opt = QStyleOptionViewItem(option)
    view = opt.widget
    feedback = getattr(view, "_row_hover", None)
    if feedback is not None:
        opt.state &= ~QStyle.State_MouseOver
        if feedback.matches(index) and index.flags() & Qt.ItemIsEnabled:
            opt.state |= QStyle.State_MouseOver
    return opt


class RowDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        super().paint(painter, row_option(opt, index), index)


class RowHover(QObject):
    def __init__(self, view):
        super().__init__(view)
        self._view = weakref.ref(view)
        self.index = QPersistentModelIndex()
        self._pinned = QPersistentModelIndex()
        self._menu = None
        self._queued = False
        self._suspended = False
        view.setProperty("wholeRowHover", True)
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        self._window = None
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        model = view.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset,
                       model.layoutChanged, model.dataChanged):
            signal.connect(self.schedule)
        for bar in (view.verticalScrollBar(), view.horizontalScrollBar()):
            bar.valueChanged.connect(self.schedule)
        if isinstance(view, QTreeWidget):
            view.expanded.connect(self.schedule)
            view.collapsed.connect(self.schedule)

    @property
    def view(self):
        return self._view()

    def matches(self, index):
        return (self.index.isValid() and index.isValid()
                and index.row() == self.index.row() and index.parent() == self.index.parent())

    def _rect(self, index):
        if not index.isValid():
            return QRect()
        rect = self.view.visualRect(index)
        return QRect(0, rect.top(), self.view.viewport().width(), rect.height())

    def set_index(self, index):
        candidate = QPersistentModelIndex(index.siblingAtColumn(0)) if index.isValid() else QPersistentModelIndex()
        if candidate == self.index:
            return
        old = self._rect(self.index)
        self.index = candidate
        self.view.viewport().update(old.united(self._rect(self.index)))

    def schedule(self, *_args):
        if not self._queued:
            self._queued = True
            QTimer.singleShot(0, self, self.sync)

    def sync(self):
        self._queued = False
        if self.view is None or not isValid(self.view):
            return
        if not self.view.isVisible() or self._suspended:
            self.set_index(QPersistentModelIndex())
            return
        if self._pinned.isValid():
            self.set_index(self._pinned)
            return
        point = self.view.viewport().mapFromGlobal(QCursor.pos())
        index = self.view.indexAt(point) if self.view.viewport().rect().contains(point) else QPersistentModelIndex()
        if index.isValid() and not index.flags() & Qt.ItemIsEnabled:
            index = QPersistentModelIndex()
        if getattr(self.view, "_placeholder_active", False):
            index = QPersistentModelIndex()
        self.set_index(index)

    def register(self, widget):
        # Index widgets must reveal the same item background as the other cells.
        widget.setAutoFillBackground(False)
        widget.setAttribute(Qt.WA_StyledBackground, False)
        for child in [widget, *widget.findChildren(QWidget)]:
            child.setMouseTracking(True)
            child.installEventFilter(self)
            if isinstance(child, QPushButton) and child.menu() is not None:
                menu = child.menu()
                menu.aboutToShow.connect(lambda m=menu, owner=child: self.pin(m, self.view.indexAt(owner.mapTo(self.view.viewport(), owner.rect().center()))))

    def pin(self, menu, index):
        menu.installEventFilter(self)
        self._menu = menu
        self._pinned = QPersistentModelIndex(index.siblingAtColumn(0))
        self.set_index(self._pinned)

    def eventFilter(self, watched, event):
        if self.view is None or not isValid(self.view):
            return False
        kind = event.type()
        view = self.view
        window = self._window() if self._window else None
        if watched is self._menu and kind in (QEvent.Hide, QEvent.Close):
            self._menu = None
            self._pinned = QPersistentModelIndex()
            self._suspended = False
            self.schedule()
        elif watched is window and kind in (QEvent.WindowDeactivate, QEvent.Hide):
            if self._menu is None:
                self._suspended = True
                self.set_index(QPersistentModelIndex())
        elif watched is window and kind == QEvent.WindowActivate:
            self._suspended = False
            self.schedule()
        elif watched is view and kind in (QEvent.Hide, QEvent.Show, QEvent.Resize):
            if kind == QEvent.Hide:
                self.set_index(QPersistentModelIndex())
            else:
                owner = view.window()
                if owner is not window:
                    if window is not None and isValid(window):
                        window.removeEventFilter(self)
                    self._window = weakref.ref(owner)
                    owner.installEventFilter(self)
                self._suspended = False
                self.schedule()
        elif kind in (QEvent.MouseMove, QEvent.Enter, QEvent.Leave, QEvent.MouseButtonPress):
            self.schedule()
        return False


class RowHoverTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._row_hover = RowHover(self)
        self.setItemDelegate(RowDelegate(self))
        self.verticalHeader().geometriesChanged.connect(self._row_hover.schedule)
        self.horizontalHeader().geometriesChanged.connect(self._row_hover.schedule)

    def setCellWidget(self, row, column, widget):
        super().setCellWidget(row, column, widget)
        self._row_hover.register(widget)

    def setRowHidden(self, row, hide):
        super().setRowHidden(row, hide)
        self._row_hover.schedule()


class RowHoverTree(QTreeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._row_hover = RowHover(self)
        self.setItemDelegate(RowDelegate(self))

    def drawRow(self, painter, option, index):
        super().drawRow(painter, row_option(option, index), index)

    def drawBranches(self, painter, rect, index):
        if self.selectionModel().isSelected(index) or self._row_hover.matches(index):
            p = palette()
            color = p.selection if self.selectionModel().isSelected(index) else p.row_hover
            painter.fillRect(rect, QColor(color))
        super().drawBranches(painter, rect, index)
