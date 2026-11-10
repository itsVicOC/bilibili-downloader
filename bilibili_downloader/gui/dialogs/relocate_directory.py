"""Review and apply directory mappings in one dialog, without moving files."""

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from bilibili_downloader.gui.dialogs.file_picker import file_picker
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.components import FieldRow, help_text


class RelocateDirectoryDialog(WorkflowDialog):
    completed = Signal(int)

    def __init__(self, repository, old="", parent=None, *, pool=None):
        super().__init__("重新定位整个目录", "填写原位置与新位置，预览映射后更新记录，不移动文件。", parent, confirm="更新位置", width=760)
        self.repository = repository
        self.pool = pool or QThreadPool.globalInstance()
        self._job = None
        self._applying = False
        self._snapshot = None
        self._changes = []
        self.old = QLineEdit(old)
        self.new = QLineEdit()
        self.old.setPlaceholderText("原目录可已移动，支持粘贴路径")
        self.new.setPlaceholderText("选择保留相对结构的新根目录")
        self.body.addWidget(FieldRow("原根目录", self.old, stacked=True))
        row = QHBoxLayout()
        row.addWidget(self.new, 1)
        browse = QPushButton("选择目录…")
        browse.clicked.connect(lambda: file_picker(self).directory("选择新的根目录", self.new.text() or old, self.new.setText))
        row.addWidget(browse)
        self.body.addWidget(help_text("新根目录"))
        self.body.addLayout(row)
        controls = QHBoxLayout()
        self.preview_button = QPushButton("预览受影响文件")
        self.preview_button.clicked.connect(self.preview)
        controls.addWidget(self.preview_button)
        copy = QPushButton("复制完整映射")
        copy.setObjectName("TextButton")
        copy.clicked.connect(lambda: QApplication.clipboard().setText("\n".join(f"{c['old']} → {c['new']}" for c in self._changes)))
        controls.addWidget(copy)
        controls.addStretch()
        self.body.addLayout(controls)
        self.table = QTableWidget(0, 3)
        self.table.setAccessibleName("目录映射预览")
        self.table.setHorizontalHeaderLabels(["原文件", "新位置", "状态"])
        for col in (0, 1):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 100)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(180)
        self.body.addWidget(self.table, 1)
        self.old.textChanged.connect(self._invalidate)
        self.new.textChanged.connect(self._invalidate)
        self._invalidate()
        self.resize(760, 600)

    def _invalidate(self, *_):
        self.confirm_button.setEnabled(False)
        self._changes = []
        self.table.setRowCount(0)
        self.notice.set_message("")
        self.footer_hint.setText("预览后确认更新")

    def preview(self):
        if self._job is not None:
            return
        old, new = self.old.text().strip(), self.new.text().strip()
        if not old or not new:
            self.notice.set_message("请填写原根目录和新根目录。", "warning")
            return
        self._snapshot = (old, new)
        self._start(False)

    def _start(self, apply):
        from bilibili_downloader.gui.widgets.library_page import _LibraryJob
        old, new = self._snapshot
        self._applying = apply
        self.preview_button.setEnabled(False)
        self.confirm_button.setEnabled(False)
        self.cancel_button.setEnabled(not apply)
        self.footer_hint.setText("正在更新文件记录…" if apply else "正在检查目录映射…")
        self._job = _LibraryJob(lambda _: self.repository.relocate_directory(old, new, apply=apply))
        self._job.signals.finished.connect(self._finished)
        self.pool.start(self._job)

    def _finished(self, result):
        self._job = None
        self.preview_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        applying, self._applying = self._applying, False
        if isinstance(result, Exception):
            self._invalidate()
            self.notice.set_message(f"未更新位置：{result}", "warning")
            return
        if applying:
            self.completed.emit(len(result))
            super().accept()
            return
        if self._snapshot != (self.old.text().strip(), self.new.text().strip()):
            self.notice.set_message("目录已改变，请重新预览。", "warning")
            return
        self._changes = result
        self.table.setRowCount(min(200, len(result)))
        for row, change in enumerate(result[:200]):
            for col, text in enumerate((change["old"], change["new"], "可读取" if change["available"] else "不可读取")):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, col, item)
        unavailable = sum(not c["available"] for c in result)
        self.notice.set_message(f"涉及 {len(result)} 个文件，{unavailable} 个目标不可读取。" + ("显示前 200 项，可复制完整映射。" if len(result) > 200 else ""), "warning" if unavailable or not result else "info")
        self.confirm_button.setEnabled(bool(result) and not unavailable)
        self.confirm_button.setText(f"更新位置（{len(result)} 个文件）")
        self.footer_hint.setText("更新记录，保留文件")

    def accept(self):
        if self._job is None and self._changes and self._snapshot == (self.old.text().strip(), self.new.text().strip()):
            self._start(True)

    def reject(self):
        if not self._applying:
            super().reject()

    def closeEvent(self, event):
        if self._applying:
            event.ignore()
        else:
            super().closeEvent(event)
