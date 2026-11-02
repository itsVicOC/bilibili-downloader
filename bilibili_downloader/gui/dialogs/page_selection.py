"""Searchable multi-part selection with explicit numbered ranges."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


def parse_page_range(text, maximum):
    result = set()
    for token in re.split(r"[,，\s]+", text.strip()):
        if not token:
            continue
        bounds = re.fullmatch(r"(\d+)(?:\s*[-–—]\s*(\d+))?", token)
        if not bounds:
            raise ValueError("请输入分 P 序号，例如 1-5,8")
        start, end = int(bounds[1]), int(bounds[2] or bounds[1])
        if not 1 <= start <= end <= maximum:
            raise ValueError(f"分 P 范围应为 1–{maximum}")
        result.update(range(start, end + 1))
    return result


class PageSelectionDialog(QDialog):
    def __init__(self, pages, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择分 P")
        self.resize(540, 440)
        self.pages = pages
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索分 P 标题")
        layout.addWidget(self.search)
        row = QHBoxLayout()
        self.range = QLineEdit()
        self.range.setPlaceholderText("序号范围，例如 1-5,8")
        row.addWidget(self.range)
        apply = QPushButton("应用范围")
        apply.clicked.connect(self.apply_range)
        row.addWidget(apply)
        layout.addLayout(row)
        self.notice = QLabel()
        layout.addWidget(self.notice)
        self.list = QListWidget()
        for index, page in enumerate(pages, 1):
            item = QListWidgetItem(f"{index:03d} · {page.part or '未命名'}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if page.cid in selected else Qt.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        self.search.textChanged.connect(self.filter)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def filter(self, text):
        for index in range(self.list.count()):
            item = self.list.item(index)
            hidden = text.casefold() not in item.text().casefold()
            item.setHidden(hidden)
            if hidden:
                item.setCheckState(Qt.Unchecked)

    def apply_range(self):
        try:
            numbers = parse_page_range(self.range.text(), len(self.pages))
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self.search.clear()
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(Qt.Checked if index + 1 in numbers else Qt.Unchecked)
        self.notice.clear()

    def selected_pages(self):
        return [page for i, page in enumerate(self.pages)
                if not self.list.item(i).isHidden() and self.list.item(i).checkState() == Qt.Checked]

    def accept(self):
        if not self.selected_pages():
            self.notice.setText("请选择至少一个分 P")
            return
        super().accept()
