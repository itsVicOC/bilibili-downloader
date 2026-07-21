"""Download list table widget with cancel and retry support."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from bilibili_downloader.gui.resources.paths import asset_path

# Shared button size (width, height)
BTN_W = 68
BTN_H = 28


def _create_action_btn(text: str, object_name: str, download_id: int, handler):
    btn = QPushButton(text)
    btn.setObjectName(object_name)
    btn.setFixedSize(BTN_W, BTN_H)
    btn.clicked.connect(lambda checked, d=download_id: handler(d))
    return btn


def _create_cancel_btn(download_id: int, handler):
    return _create_action_btn("取消", "SubtleButton", download_id, handler)


def _create_delete_btn(download_id: int, handler):
    return _create_action_btn("删除", "DangerButton", download_id, handler)


def _create_retry_btn(download_id: int, handler):
    return _create_action_btn("重试", "PrimaryButton", download_id, handler)


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
    """Table showing download queue with progress bars and cancel buttons.

    Uses stable download IDs internally so row deletions do not corrupt
    the worker/item mappings.
    """

    # Signal emitted when user clicks retry (download_id)
    retry_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self._next_id = 0
        self._workers = {}       # download_id -> worker reference
        self._items = {}         # download_id -> DownloadItem snapshot
        self._id_to_row = {}     # download_id -> current row index
        self._placeholder_active = False
        self._setup_ui()

    def _setup_ui(self):
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["作品", "规格", "传输进度", "任务状态", "操作"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.horizontalHeader().resizeSection(2, 220)
        # Button column: fixed width based on BTN_W + padding buffer
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.horizontalHeader().resizeSection(4, BTN_W * 2 + 28)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(46)
        self.verticalHeader().setMinimumSectionSize(42)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setIconSize(QSize(20, 20))
        self._show_placeholder()

    def add_item(self, item) -> int:
        """Add a download item to the table. Returns a stable download ID."""
        self._clear_placeholder()
        download_id = self._next_id
        self._next_id += 1
        row = self.rowCount()
        self.insertRow(row)

        self._items[download_id] = item
        self._id_to_row[download_id] = row

        title_item = QTableWidgetItem(item.video_info.title[:50])
        title_item.setToolTip(item.video_info.title)
        title_item.setData(Qt.UserRole, download_id)
        self.setItem(row, 0, title_item)

        quality_item = QTableWidgetItem(item.selected_quality.label)
        quality_item.setData(Qt.UserRole, download_id)
        self.setItem(row, 1, quality_item)

        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(100)
        progress_bar.setValue(0)
        self.setCellWidget(row, 2, progress_bar)

        status_item = QTableWidgetItem("等待中")
        status_item.setData(Qt.UserRole, download_id)
        self.setItem(row, 3, status_item)

        self.setCellWidget(
            row, 4,
            _wrap_btn(_create_cancel_btn(download_id, self._on_cancel_clicked)),
        )
        return download_id

    def _row_for(self, download_id: int) -> int | None:
        """Return the current row index for a download ID."""
        return self._id_to_row.get(download_id)

    def _rebuild_row_mapping(self):
        """Rebuild id->row mapping after row insertion/deletion."""
        self._id_to_row = {}
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None:
                download_id = item.data(Qt.UserRole)
                if download_id is not None:
                    self._id_to_row[download_id] = row

    def _on_cancel_clicked(self, download_id: int):
        """Handle cancel button click."""
        worker = self._workers.get(download_id)
        if worker:
            worker.cancel()
            row = self._row_for(download_id)
            if row is not None:
                status_item = self.item(row, 3)
                if status_item:
                    status_item.setText("取消中...")
                    status_item.setForeground(Qt.yellow)

    def register_worker(self, download_id: int, worker):
        """Register a worker for a download ID (enables cancel)."""
        self._workers[download_id] = worker

    def get_item(self, download_id: int):
        """Get the DownloadItem for a download ID."""
        return self._items.get(download_id)

    def unregister_worker(self, download_id: int):
        """Unregister a worker after download completes."""
        self._workers.pop(download_id, None)

    def update_progress(self, download_id: int, progress: float, status_text: str):
        """Update progress bar and status for a download ID."""
        row = self._row_for(download_id)
        if row is None:
            return
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            progress_bar.setValue(int(progress * 100))

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText(status_text)

    def mark_done(self, download_id: int):
        """Mark a download as complete."""
        self.unregister_worker(download_id)
        row = self._row_for(download_id)
        if row is None:
            return
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            _set_progress_state(progress_bar, "")
            progress_bar.setValue(100)

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText("完成")
            status_item.setForeground(Qt.green)

        self.setCellWidget(
            row, 4,
            _wrap_btn(_create_delete_btn(download_id, self._on_delete_clicked)),
        )

    def mark_failed(self, download_id: int, error: str):
        """Mark a download as failed."""
        self.unregister_worker(download_id)
        row = self._row_for(download_id)
        if row is None:
            return
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            _set_progress_state(progress_bar, "ErrorProgress")

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText(f"失败：{error[:30]}")
            status_item.setForeground(Qt.red)
            status_item.setToolTip(error)

        self.setCellWidget(
            row, 4,
            _wrap_btns(
                _create_retry_btn(download_id, self.retry_requested.emit),
                _create_delete_btn(download_id, self._on_delete_clicked),
            ),
        )

    def mark_cancelled(self, download_id: int):
        """Mark a user-cancelled task without presenting it as a failure."""
        self.unregister_worker(download_id)
        row = self._row_for(download_id)
        if row is None:
            return
        status_item = self.item(row, 3)
        if status_item:
            status_item.setText("已取消")
            status_item.setForeground(Qt.gray)
        self.setCellWidget(
            row, 4,
            _wrap_btn(_create_delete_btn(download_id, self._on_delete_clicked)),
        )

    def mark_failed_retry_reset(self, download_id: int):
        """Reset a failed download for retry (clear error state)."""
        row = self._row_for(download_id)
        if row is None:
            return
        progress_bar = self.cellWidget(row, 2)
        if progress_bar:
            progress_bar.setValue(0)
            _set_progress_state(progress_bar, "")

        status_item = self.item(row, 3)
        if status_item:
            status_item.setText("重试中...")
            status_item.setForeground(Qt.yellow)

        self.setCellWidget(
            row, 4,
            _wrap_btn(_create_cancel_btn(download_id, self._on_cancel_clicked)),
        )

    def cancel_all_workers(self):
        """Cancel all active download workers."""
        for worker in self._workers.values():
            if worker is not None:
                worker.cancel()

    @property
    def running_workers(self):
        """Yield running worker references."""
        for worker in self._workers.values():
            if worker is not None and worker.is_running:
                yield worker

    def _on_delete_clicked(self, download_id: int):
        """Remove a download from the table."""
        row = self._row_for(download_id)
        self._items.pop(download_id, None)
        self._workers.pop(download_id, None)
        if row is not None:
            self.removeRow(row)
            self._rebuild_row_mapping()
            if not self._items:
                self._show_placeholder()

    def _show_placeholder(self):
        """Show a quiet empty-state row when the queue is empty."""
        if self._placeholder_active or self.rowCount() > 0:
            return
        self._placeholder_active = True
        self.insertRow(0)
        placeholder = QTableWidgetItem("  暂无任务 · 在上方解析作品后加入下载队列")
        placeholder.setIcon(QIcon(asset_path("sparkle.png")))
        placeholder.setSizeHint(QSize(0, 54))
        placeholder.setTextAlignment(Qt.AlignCenter)
        placeholder.setForeground(Qt.gray)
        self.setItem(0, 0, placeholder)
        self.setSpan(0, 0, 1, self.columnCount())
        for col in range(1, self.columnCount()):
            item = QTableWidgetItem("")
            item.setFlags(Qt.NoItemFlags)
            self.setItem(0, col, item)

    def _clear_placeholder(self):
        """Remove the empty-state row before adding real items."""
        if self._placeholder_active:
            self.setSpan(0, 0, 1, 1)
            self.removeRow(0)
            self._placeholder_active = False


def _set_progress_state(progress_bar: QProgressBar, object_name: str):
    """Refresh QSS when switching progress bar visual state."""
    progress_bar.setObjectName(object_name)
    progress_bar.style().unpolish(progress_bar)
    progress_bar.style().polish(progress_bar)
