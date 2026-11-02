"""Search Chinese field names and examples before inserting template syntax."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
)

from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.components import EmptyState


class NamingFieldDialog(WorkflowDialog):
    def __init__(self, fields, parent=None, *, read_only=False):
        super().__init__("命名字段", "按中文名称查找字段，查看用途和示例。占位符会在下载时替换为实际内容。", parent, confirm="关闭" if read_only else "插入此字段", width=740)
        self.fields = fields
        self.variable = None
        self.read_only = read_only
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索中文名称、用途或占位符")
        self.search.setClearButtonEnabled(True)
        self.body.addWidget(self.search)
        self.table = QTableWidget(len(fields), 2)
        self.table.setHorizontalHeaderLabels(["字段与示例", "占位符"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 155)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(76)
        self.table.setWordWrap(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        for row, (key, (name, description)) in enumerate(fields.items()):
            item = QTableWidgetItem(f"{name}\n{description}")
            item.setData(Qt.UserRole, key)
            item.setToolTip(description)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem("{" + key + "}"))
        self.results = QStackedWidget()
        self.results.addWidget(self.table)
        self.results.addWidget(EmptyState("没有匹配的字段", "试试作品名称、作者、分 P 等中文关键词。", "清除搜索", self.search.clear))
        self.body.addWidget(self.results, 1)
        self.search.textChanged.connect(self.filter)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.itemDoubleClicked.connect(lambda *_: self.accept() if not read_only else None)
        self.cancel_button.setVisible(not read_only)
        self.confirm_button.setEnabled(read_only)
        self.resize(740, 560)
        self.search.setFocus()

    def filter(self, text):
        query = text.strip().casefold()
        for row in range(self.table.rowCount()):
            label = " ".join(self.table.item(row, col).text() for col in (0, 1))
            self.table.setRowHidden(row, query not in label.casefold())
        self.results.setCurrentIndex(0 if any(not self.table.isRowHidden(row) for row in range(self.table.rowCount())) else 1)
        self._selection()

    def _selection(self):
        row = self.table.currentRow()
        self.variable = self.table.item(row, 0).data(Qt.UserRole) if row >= 0 and not self.table.isRowHidden(row) else None
        self.confirm_button.setEnabled(self.read_only or self.variable is not None)
        self.footer_hint.setText(self.fields[self.variable][0] if self.variable else "请选择一个字段")

    def accept(self):
        if self.read_only or self.variable:
            super().accept()


def insert_naming_field(entry, fields, parent=None):
    start, length, cursor = entry.selectionStart(), entry.selectionLength(), entry.cursorPosition()
    dialog = NamingFieldDialog(fields, parent)
    if dialog.exec() and dialog.variable:
        if start >= 0:
            entry.setSelection(start, length)
        else:
            entry.setCursorPosition(cursor)
        entry.insert("{" + dialog.variable + "}")
        entry.setFocus(Qt.OtherFocusReason)
