"""A file view backed by row data, with cells materialized only for callers."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QTableView

from bilibili_downloader.gui.widgets.row_hover import RowDelegate, RowHover


class _FileModel(QAbstractTableModel):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.rows, self.ids, self.titles, self.headers = [], [], [], [""] * 6

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row, col = index.row(), index.column()
        if role == Qt.DisplayRole:
            return self.rows[row][col]
        if role == Qt.ToolTipRole:
            return self.rows[row][col] + ("\n" + self.titles[row] if col == 0 else "")
        if col == 0:
            if role == Qt.UserRole:
                return self.ids[row]
            if role == Qt.CheckStateRole and hasattr(self.view, "_selection_binding"):
                return Qt.Checked if self.ids[row] in self.view._selection_binding.state.selected else Qt.Unchecked
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags | Qt.ItemIsUserCheckable if index.column() == 0 else flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        row, col = index.row(), index.column()
        if role == Qt.CheckStateRole and col == 0:
            binding = self.view._selection_binding
            checked = value in (Qt.Checked, Qt.Checked.value)
            if checked != (self.ids[row] in binding.state.selected):
                binding.toggle(self.ids[row])
            return True
        if role in (Qt.EditRole, Qt.DisplayRole):
            self.rows[row][col] = value
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.ToolTipRole])
            return True
        return False


class _Cell:
    """Small compatibility handle; the model remains authoritative."""
    def __init__(self, view, row, column):
        self.view, self._row, self._column = view, row, column

    def row(self):
        return self._row

    def column(self):
        return self._column

    def data(self, role):
        return self.view.model().data(self.view.model().index(self._row, self._column), role)

    def text(self):
        return self.view.model().rows[self._row][self._column]

    def setText(self, value):
        model = self.view.model()
        model.setData(model.index(self._row, self._column), value)

    def toolTip(self):
        return self.data(Qt.ToolTipRole)

    def checkState(self):
        return self.data(Qt.CheckStateRole)

    def setCheckState(self, value):
        model = self.view.model()
        model.setData(model.index(self._row, self._column), value, Qt.CheckStateRole)


class FileTable(QTableView):
    currentItemChanged = Signal(object, object)
    itemSelectionChanged = Signal()
    itemChanged = Signal(object)
    itemDoubleClicked = Signal(object)
    select_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells = {}
        self.setModel(_FileModel(self))
        self._row_hover = RowHover(self)
        self.setItemDelegate(RowDelegate(self))
        self.verticalHeader().geometriesChanged.connect(self._row_hover.schedule)
        self.horizontalHeader().geometriesChanged.connect(self._row_hover.schedule)
        self.doubleClicked.connect(lambda index: self.itemDoubleClicked.emit(self.item(index.row(), index.column())))

    def replace_rows(self, rows, ids, titles):
        model = self.model()
        if ids == model.ids:
            model.rows, model.titles = rows, titles
            if rows:
                model.dataChanged.emit(model.index(0, 0), model.index(len(rows) - 1, 5), [])
        else:
            model.beginResetModel()
            self._cells.clear()
            model.rows, model.ids, model.titles = rows, ids, titles
            model.endResetModel()

    def setHorizontalHeaderLabels(self, labels):
        self.model().headers = labels
        self.model().headerDataChanged.emit(Qt.Horizontal, 0, len(labels) - 1)

    def rowCount(self):
        return self.model().rowCount()

    def currentRow(self):
        return self.currentIndex().row()

    def item(self, row, column):
        if not 0 <= row < self.rowCount() or not 0 <= column < self.model().columnCount():
            return None
        key = row, column
        if key not in self._cells:
            self._cells[key] = _Cell(self, row, column)
        return self._cells[key]

    def setCurrentCell(self, row, column):
        self.setCurrentIndex(self.model().index(row, column))

    def visualItemRect(self, item):
        return self.visualRect(self.model().index(item.row(), item.column()))

    def currentChanged(self, current, previous):
        super().currentChanged(current, previous)
        if hasattr(self, "_cells"):
            self.currentItemChanged.emit(self.item(current.row(), current.column()), self.item(previous.row(), previous.column()))

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        self.itemSelectionChanged.emit()

    def selectRow(self, row):
        super().selectRow(row)
        if hasattr(self, "_selection_binding"):
            self._selection_binding.select_only_row(row)

    def setRowHidden(self, row, hidden):
        super().setRowHidden(row, hidden)
        self._row_hover.schedule()

    def paintEvent(self, event):
        super().paintEvent(event)
        self._row_hover.paint_focus()
