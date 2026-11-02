"""Searchable part selection; filtering never discards the user's choices."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
)

from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.components import CollapsibleSection, EmptyState
from bilibili_downloader.gui.widgets.selection import SelectionBar, TableSelection


def parse_page_range(text, maximum):
    result = set()
    normalized = re.sub(r"\s*([-–—])\s*", r"\1", text.strip())
    for token in re.split(r"[,，\s]+", normalized):
        if not token:
            continue
        bounds = re.fullmatch(r"(\d+)(?:[-–—](\d+))?", token)
        if not bounds:
            raise ValueError("请输入分 P 序号，例如 1–5,8")
        start, end = int(bounds[1]), int(bounds[2] or bounds[1])
        if not 1 <= start <= end <= maximum:
            raise ValueError(f"分 P 范围应为 1–{maximum}")
        result.update(range(start, end + 1))
    return result


class PageSelectionDialog(WorkflowDialog):
    def __init__(self, pages, selected, parent=None, *, title=""):
        super().__init__("选择分 P", title or "搜索和切换视图会保留勾选；确认后应用到本次下载。", parent, confirm="确认选择")
        self.pages = pages
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索分 P 标题或序号")
        self.search.setClearButtonEnabled(True)
        self.body.addWidget(self.search)
        self.selection_bar = SelectionBar()
        self.body.addWidget(self.selection_bar)
        self.list = QTableWidget(len(pages), 2)
        self.list.setHorizontalHeaderLabels(["分 P", "时长"])
        self.list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.list.setColumnWidth(1, 80)
        self.list.verticalHeader().hide()
        self.list.verticalHeader().setDefaultSectionSize(44)
        self.list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setMinimumHeight(140)
        self.list.setShowGrid(False)
        for index, page in enumerate(pages):
            item = QTableWidgetItem(f"{index + 1:03d} · {page.part or '未命名'}")
            item.setData(Qt.UserRole, page.cid)
            item.setToolTip(item.text())
            self.list.setItem(index, 0, item)
            self.list.setItem(index, 1, QTableWidgetItem(f"{page.duration // 60:02d}:{page.duration % 60:02d}" if page.duration else "—"))
        self.selection = TableSelection(self.list)
        self.selection.state.selected = set(selected)
        self.selection.reset()
        self.results = QStackedWidget()
        self.results.addWidget(self.list)
        self.results.addWidget(EmptyState("没有匹配的分 P", "已勾选的分 P 仍会保留，可清除搜索或查看已选。", "清除搜索", self.search.clear))
        self.body.addWidget(self.results, 1)
        ranges = CollapsibleSection("按序号添加")
        row = QHBoxLayout()
        self.range = QLineEdit()
        self.range.setPlaceholderText("例如 1–5,8")
        row.addWidget(self.range, 1)
        apply = QPushButton("添加到已选")
        apply.clicked.connect(self.apply_range)
        row.addWidget(apply)
        ranges.body.addLayout(row)
        self.body.addWidget(ranges)
        self.notice_label = self.notice
        self.search.textChanged.connect(self.filter)
        self.selection.changed.connect(self.filter)
        self.selection_bar.select_visible.connect(self.selection.select_visible)
        self.selection_bar.clear_requested.connect(self.selection.clear)
        self.selection_bar.review_requested.connect(self.selection.toggle_review)
        self.filter()
        self.search.setFocus()
        self.resize(660, 560)

    def filter(self, *_):
        state = self.selection.state
        query = self.search.text().strip().casefold()
        visible = []
        for index, page in enumerate(self.pages):
            show = page.cid in state.selected if state.reviewing else query in self.list.item(index, 0).text().casefold()
            self.list.setRowHidden(index, not show)
            if show:
                visible.append(page.cid)
        self.selection.set_visible(visible)
        self.results.setCurrentIndex(0 if visible else 1)
        self.search.setEnabled(not state.reviewing)
        self.selection_bar.update_state(state)
        self.confirm_button.setEnabled(bool(state.selected))
        self.confirm_button.setText(f"确认选择（{len(state.selected)} P）")
        self.footer_hint.setText("勾选仅在确认后生效")

    def apply_range(self):
        try:
            numbers = parse_page_range(self.range.text(), len(self.pages))
            if not numbers:
                raise ValueError("请输入要添加的分 P 序号")
        except ValueError as exc:
            self.notice.set_message(str(exc), "warning")
            self.range.setFocus()
            return
        self.selection.state.selected.update(self.pages[n - 1].cid for n in numbers)
        self.selection._paint_checks()
        self.filter()
        self.notice.set_message(f"已添加范围，合计选中 {len(self.selection.state.selected)} P。", "success")

    def selected_pages(self):
        return [page for page in self.pages if page.cid in self.selection.state.selected]

    def accept(self):
        if self.selected_pages():
            super().accept()
