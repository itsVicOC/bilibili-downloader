"""Download list table widget with cancel and retry support."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

# Shared button size (width, height)
BTN_W = 72
BTN_H = 30


def _create_cancel_btn(row: int, handler):
    btn = QPushButton("取消")
    btn.setFixedSize(BTN_W, BTN_H)
    btn.setStyleSheet(
        "QPushButton { background-color: #555; color: white; "
        "border: 1px solid #666; border-radius: 4px; font-size: 12px; "
        "padding: 0px 4px; }"
        "QPushButton:hover { background-color: #666; }"
    )
    btn.clicked.connect(lambda checked, r=row: handler(r))
    return btn


def _create_delete_btn(row: int, handler):
    btn = QPushButton("删除")
    btn.setFixedSize(BTN_W, BTN_H)
    btn.setStyleSheet(
        "QPushButton { background-color: #d32f2f; color: white; "
        "border: 1px solid #d32f2f; border-radius: 4px; font-size: 12px; "
        "padding: 0px 4px; }"
        "QPushButton:hover { background-color: #e03e3e; }"
    )
    btn.clicked.connect(lambda checked, r=row: handler(r))
    return btn


def _create_retry_btn(row: int, handler):
    btn = QPushButton("重试")
    btn.setFixedSize(BTN_W, BTN_H)
    btn.setStyleSheet(
        "QPushButton { background-color: #00A1D6; color: white; "
        "border: 1px solid #00A1D6; border-radius: 4px; font-size: 12px; "
        "padding: 0px 4px; }"
        "QPushButton:hover { background-color: #23a2d9; }"
    )
    btn.clicked.connect(lambda checked, r=row: handler())
    return btn


def _wrap_btn(widget):
    """Wrap a button widget in a centered container."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.addWidget(widget, alignment=Qt.AlignCenter)
    layout.setContentsMargins(0, 0, 0, 0)
    return container


def _wrap_btns(*widgets):
    """Wrap multiple buttons in a centered container."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setSpacing(4)
    for w in widgets:
        layout.addWidget(w)
    layout.setContentsMargins(0, 0, 0, 0)
    return container


class DownloadListWidget(QTableWidget):
    """Table showing download queue with progress bars and cancel buttons."""

    # Signal emitted when user clicks retry (row_index)
    retry_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self._workers = {}  # row_index -> worker reference
        self._items = {}    # row_index -> DownloadItem snapshot
        self._setup_ui()

    def _setup_ui(self):
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["标题", "画质", "进度", "状态", ""])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        # Button column: fixed width based on BTN_W + padding buffer
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.horizontalHeader().resizeSection(4, BTN_W + 16)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setMinimumSectionSize(BTN_H + 12)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)

    def add_item(self, item):
        """Add a download item to the table."""
        row = self.rowCount()
        self.insertRow(row)

        self._items[row] = item

        title_item = QTableWidgetItem(item.video_info.title[:50])
        title_item.setToolTip(item.video_info.title)
        self.setItem(row, 0, title_item)

        quality_item = QTableWidgetItem(item.selected_quality.label)
        self.setItem(row, 1, quality_item)

        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(100)
        progress_bar.setValue(0)
        self.setCellWidget(row, 2, progress_bar)

        status_item = QTableWidgetItem("等待中")
        self.setItem(row, 3, status_item)

        self.setCellWidget(row, 4, _wrap_btn(_create_cancel_btn(row, self._on_cancel_clicked)))

    def _on_cancel_clicked(self, row: int):
        """Handle cancel button click."""
        worker = self._workers.get(row)
        if worker:
            worker.cancel()
            status_item = self.item(row, 3)
            if status_item:
                status_item.setText("取消中...")
                status_item.setForeground(Qt.yellow)

    def register_worker(self, row: int, worker):
        """Register a worker for a row (enables cancel)."""
        self._workers[row] = worker

    def get_item(self, row: int):
        """Get the DownloadItem for a row."""
        return self._items.get(row)

    def unregister_worker(self, row: int):
        """Unregister a worker after download completes."""
        self._workers.pop(row, None)

    def update_progress(self, row: int, progress: float, status_text: str):
        """Update progress bar and status for a row."""
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            progress_bar.setValue(int(progress * 100))

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText(status_text)

    def mark_done(self, row: int):
        """Mark a download as complete."""
        self.unregister_worker(row)
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            progress_bar.setValue(100)

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText("完成")
            status_item.setForeground(Qt.green)

        self.setCellWidget(row, 4, _wrap_btn(_create_delete_btn(row, self._on_delete_clicked)))

    def mark_failed(self, row: int, error: str):
        """Mark a download as failed."""
        self.unregister_worker(row)
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            progress_bar.setStyleSheet("QProgressBar::chunk { background: #d32f2f; }")

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText(f"失败：{error[:30]}")
            status_item.setForeground(Qt.red)
            status_item.setToolTip(error)

        self.setCellWidget(row, 4, _wrap_btns(
            _create_retry_btn(row, lambda r=row: self.retry_requested.emit(r)),
            _create_delete_btn(row, self._on_delete_clicked),
        ))

    def mark_failed_retry_reset(self, row: int):
        """Reset a failed row for retry (clear error state)."""
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            progress_bar.setValue(0)
            progress_bar.setStyleSheet("")

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText("重试中...")
            status_item.setForeground(Qt.yellow)

        self.setCellWidget(row, 4, _wrap_btn(_create_cancel_btn(row, self._on_cancel_clicked)))

    def _on_delete_clicked(self, row: int):
        """Remove a row from the table."""
        self._items.pop(row, None)
        self._workers.pop(row, None)
        self.removeRow(row)
