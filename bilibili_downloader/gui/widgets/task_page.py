"""Task center: durable downloads, current recordings and finalized segments."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.models import TaskStatus
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    EmptyState,
    Notice,
    PageHeader,
    PopupMenu,
)
from bilibili_downloader.gui.widgets.download_list import (
    STATUS_TONE_ROLE,
    _StatusDelegate,
)
from bilibili_downloader.gui.widgets.live_page import _duration, _size, live_tone

CURRENT_STATES = {
    "preparing",
    "queued",
    "recording",
    "reconnecting",
    "finalizing",
    "error",
}


def _local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value


class TaskPage(QWidget):
    room_requested = Signal(int)
    download_requested = Signal()
    pause_all_requested = Signal()
    resume_all_requested = Signal()
    clear_completed_requested = Signal()
    clear_cache_requested = Signal()

    def __init__(self, downloads, controller, parent=None):
        super().__init__(parent)
        self.downloads = downloads
        self.controller = controller
        self._live_rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(
            PageHeader("任务中心", "下载进度、正在录制与本地历史，一处查看")
        )
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._download_tab()
        self._current_tab()
        self._history_tab()
        self.notice = Notice()
        layout.addWidget(self.notice)
        downloads.content_state_changed.connect(self.refresh_downloads)
        downloads.itemChanged.connect(self.refresh_downloads)
        downloads.itemSelectionChanged.connect(self._download_selection)
        controller.snapshot_changed.connect(self.update_recordings)
        controller.history_changed.connect(self.update_history)
        controller.message_changed.connect(self.notice.set_message)
        controller.export_changed.connect(self._export_changed)
        self.refresh_downloads()
        self.update_recordings(controller.rows)
        self.update_history(controller.sessions)
        self.notice.set_message(controller.message, controller.message_tone)

    def _download_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        self.filter = ComboBox()
        for text, key in (
            ("全部任务", "all"),
            ("进行中", "active"),
            ("已暂停", "paused"),
            ("已完成", "completed"),
            ("需要处理", "attention"),
        ):
            self.filter.addItem(text, key)
        self.filter.setFixedWidth(132)
        self.filter.currentIndexChanged.connect(self.refresh_downloads)
        toolbar.addWidget(self.filter)
        self._download_count = QLabel("0 项")
        self._download_count.setObjectName("MetaLabel")
        toolbar.addWidget(self._download_count)
        toolbar.addStretch()
        for text, signal in (
            ("全部暂停", self.pause_all_requested),
            ("全部继续", self.resume_all_requested),
            ("清除完成", self.clear_completed_requested),
        ):
            button = QPushButton(text)
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(signal.emit)
            toolbar.addWidget(button)
        more = QPushButton("更多")
        more.setObjectName("TableSubtleButton")
        more.setProperty("menuButton", True)
        menu = PopupMenu(more)
        menu.addAction("清理下载缓存", self.clear_cache_requested.emit)
        more.setMenu(menu)
        toolbar.addWidget(more)
        layout.addLayout(toolbar)
        self._download_stack = QStackedWidget()
        self._download_stack.addWidget(self.downloads)
        self._download_stack.addWidget(
            EmptyState(
                "收藏，从这里开始",
                "解析喜欢的作品，将它加入下载队列。",
                "去解析作品",
                self.download_requested.emit,
            )
        )
        self._download_stack.addWidget(
            EmptyState("没有匹配的任务", "切换筛选条件，查看其他任务。")
        )
        layout.addWidget(self._download_stack, 1)
        self.download_detail = QPlainTextEdit()
        self.download_detail.setReadOnly(True)
        self.download_detail.setMaximumHeight(112)
        self.download_detail.setPlaceholderText("选择任务查看完整状态与警告")
        self.download_detail.hide()
        layout.addWidget(self.download_detail)
        self.tabs.addTab(tab, "下载队列")

    def refresh_downloads(self, *_args):
        key = self.filter.currentData()
        count = 0
        for task_id, state in self.downloads._states.items():
            row = self.downloads._row_for(task_id)
            if row is None:
                continue
            status_item = self.downloads.item(row, 3)
            warning = status_item and status_item.data(STATUS_TONE_ROLE) == "warning"
            visible = (
                key == "all"
                or (
                    key == "active"
                    and state
                    in {TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.MERGING}
                )
                or (key == "paused" and state == TaskStatus.PAUSED)
                or (key == "completed" and state == TaskStatus.COMPLETED)
                or (key == "attention" and (state == TaskStatus.FAILED or warning))
            )
            self.downloads.setRowHidden(row, not visible)
            count += bool(visible)
        total = len(self.downloads._states)
        self._download_count.setText(f"{count} / {total} 项")
        self._download_stack.setCurrentIndex(1 if not total else 0 if count else 2)
        self._download_selection()

    def _download_selection(self):
        row = self.downloads.currentRow()
        item = self.downloads.item(row, 0)
        if (
            item is None
            or item.data(Qt.UserRole) is None
            or self.downloads.isRowHidden(row)
        ):
            self.download_detail.hide()
            return
        task_id = item.data(Qt.UserRole)
        status = self.downloads.item(row, 3)
        text = [item.text(), status.text() if status else ""]
        if status and status.toolTip() and status.toolTip() != status.text():
            text.append(status.toolTip())
        if self.downloads._output_paths.get(task_id):
            text.append(f"保存位置：{self.downloads._output_paths[task_id]}")
        self.download_detail.setPlainText("\n".join(text))
        self.download_detail.show()

    def _current_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.current = QTableWidget(0, 5)
        self.current.setHorizontalHeaderLabels(
            ["直播间", "状态", "时长", "大小 / 速度", "操作"]
        )
        self.current.verticalHeader().hide()
        self.current.verticalHeader().setDefaultSectionSize(UI_METRICS.row_height)
        self.current.setEditTriggers(QTableWidget.NoEditTriggers)
        self.current.setSelectionBehavior(QTableWidget.SelectRows)
        self.current.setSelectionMode(QTableWidget.SingleSelection)
        self.current.setShowGrid(False)
        header = self.current.horizontalHeader()
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 128), (2, 100), (3, 120), (4, 180)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            header.resizeSection(column, width)
        self.current.setItemDelegateForColumn(1, _StatusDelegate(self.current))
        self.current.itemSelectionChanged.connect(self._recording_selection)
        self._current_stack = QStackedWidget()
        self._current_stack.addWidget(self.current)
        self._current_stack.addWidget(
            EmptyState("星轨正在待命", "开播录制、重连和收尾状态会在这里同步显示。")
        )
        layout.addWidget(self._current_stack, 1)
        self.current_detail = QPlainTextEdit()
        self.current_detail.setReadOnly(True)
        self.current_detail.setMaximumHeight(96)
        self.current_detail.hide()
        layout.addWidget(self.current_detail)
        self.tabs.addTab(tab, "当前录制")

    def update_recordings(self, rows):
        selected = self.current.item(self.current.currentRow(), 0)
        selected_id = selected.data(Qt.UserRole) if selected else None
        scroll = self.current.verticalScrollBar().value()
        self._live_rows = [
            row for row in rows if row["active"] or row["state"] in CURRENT_STATES
        ]
        self.current.blockSignals(True)
        self.current.setRowCount(len(self._live_rows))
        for index, row in enumerate(self._live_rows):
            values = [
                f"{row['author']} · {row['room_id']}",
                row["state_label"],
                _duration(row["duration"]),
                f"{_size(row['size'])}\n{_size(row['speed'])}/s",
            ]
            for column, value in enumerate(values):
                item = self.current.item(index, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.current.setItem(index, column, item)
                item.setText(value)
                item.setToolTip(row["detail"] if column == 1 else value)
                if column == 0:
                    item.setData(Qt.UserRole, row["room_id"])
                if column == 1:
                    item.setData(STATUS_TONE_ROLE, live_tone(row["state"]))
            controls = self.current.cellWidget(index, 4)
            if controls is None or controls.property("roomId") != row["room_id"]:
                controls = QWidget()
                controls.setProperty("roomId", row["room_id"])
                actions = QHBoxLayout(controls)
                actions.setContentsMargins(8, 0, 8, 0)
                actions.setSpacing(6)
                stop = QPushButton("停止本场")
                stop.setObjectName("TableSubtleButton")
                stop.clicked.connect(
                    lambda _checked=False, rid=row["room_id"], button=stop: (
                        self._stop_recording(rid, button)
                    )
                )
                view = QPushButton("查看房间")
                view.setObjectName("TableSubtleButton")
                view.clicked.connect(
                    lambda _checked=False, rid=row["room_id"]: self.room_requested.emit(
                        rid
                    )
                )
                actions.addWidget(stop)
                actions.addWidget(view)
                self.current.setCellWidget(index, 4, controls)
            controls.findChildren(QPushButton)[0].setEnabled(
                row["state"] != "finalizing"
                and (
                    row["active"]
                    or row["state"]
                    in {"preparing", "queued", "reconnecting", "recording"}
                )
            )
            self.current.setRowHeight(
                index,
                max(
                    UI_METRICS.row_height, self.current.fontMetrics().height() * 2 + 20
                ),
            )
            if row["room_id"] == selected_id:
                self.current.selectRow(index)
        if not any(row["room_id"] == selected_id for row in self._live_rows):
            self.current.clearSelection()
            self.current.setCurrentCell(-1, -1)
        self.current.blockSignals(False)
        self.current.verticalScrollBar().setValue(scroll)
        self._current_stack.setCurrentIndex(0 if self._live_rows else 1)
        self._recording_selection()

    def _stop_recording(self, room_id, button):
        button.setEnabled(False)
        self.controller.command("stop", room_id=room_id)

    def _recording_selection(self):
        item = self.current.item(self.current.currentRow(), 0)
        row = next(
            (
                r
                for r in self._live_rows
                if item and r["room_id"] == item.data(Qt.UserRole)
            ),
            None,
        )
        self.current_detail.setVisible(row is not None)
        if row:
            self.current_detail.setPlainText(
                f"{row['author']} · 房间 {row['room_id']}\n{row['state_label']} · {row['detail']}\n保存位置：{row['output_dir']}"
            )

    def _history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.history = QTreeWidget()
        self.history.setHeaderLabels(["场次 / 文件", "状态 / 时长", "大小"])
        self.history.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.history.header().resizeSection(1, 150)
        self.history.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.history.header().resizeSection(2, 108)
        self.history.setSelectionMode(QTreeWidget.SingleSelection)
        self.history.itemSelectionChanged.connect(self._history_selection)
        self._history_stack = QStackedWidget()
        self._history_stack.addWidget(self.history)
        self._history_stack.addWidget(
            EmptyState("留住每一场相遇", "录制场次及已封口片段会保存在这里。")
        )
        layout.addWidget(self._history_stack, 1)
        self.history_detail = QPlainTextEdit()
        self.history_detail.setReadOnly(True)
        self.history_detail.setMaximumHeight(112)
        self.history_detail.hide()
        layout.addWidget(self.history_detail)
        footer = QHBoxLayout()
        self.open_button = QPushButton("打开目录")
        self.open_button.clicked.connect(self._open)
        footer.addWidget(self.open_button)
        self.export_button = QPushButton("导出 MP4")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self._export_mp4)
        footer.addWidget(self.export_button)
        self.export_location = QPushButton("打开导出位置")
        self.export_location.setObjectName("TextButton")
        self.export_location.clicked.connect(self._open_export)
        self.export_location.hide()
        footer.addWidget(self.export_location)
        footer.addStretch()
        layout.addLayout(footer)
        self.tabs.addTab(tab, "录制历史")

    def update_history(self, sessions):
        selected = self.history.currentItem()
        key = selected.data(0, Qt.UserRole + 1) if selected else None
        expanded = {
            self.history.topLevelItem(i).data(0, Qt.UserRole + 1)
            for i in range(self.history.topLevelItemCount())
            if self.history.topLevelItem(i).isExpanded()
        }
        scroll = self.history.verticalScrollBar().value()
        self.history.blockSignals(True)
        self.history.clear()
        labels = {
            "recording": "录制中",
            "completed": "已结束",
            "stopped": "已停止",
            "failed": "失败",
            "interrupted": "中断",
        }
        for session in sessions:
            status = labels.get(session.status, session.status)
            if session.gaps or session.warnings:
                status += (
                    f"\n{len(session.gaps)} 处缺口 / {len(session.warnings)} 条提示"
                )
            details = [
                f"{session.room.author} · {_local_time(session.started_at)}",
                f"保存目录：{session.directory}",
            ] + session.warnings
            details.extend(f"录制缺口：{gap}" for gap in session.gaps)
            parent = QTreeWidgetItem(
                [
                    f"{session.room.author} · {_local_time(session.started_at)}",
                    status,
                    _size(session.total_size),
                ]
            )
            parent.setData(0, Qt.UserRole, session.directory)
            parent.setData(0, Qt.UserRole + 1, f"session:{session.id}")
            parent.setData(0, Qt.UserRole + 2, "\n".join(details))
            parent.setToolTip(0, "\n".join(details))
            parent.setSizeHint(
                0,
                QSize(
                    0,
                    max(
                        UI_METRICS.row_height,
                        self.history.fontMetrics().height() * 2 + 20,
                    ),
                ),
            )
            self.history.addTopLevelItem(parent)
            parent.setExpanded(parent.data(0, Qt.UserRole + 1) in expanded)
            if parent.data(0, Qt.UserRole + 1) == key:
                self.history.setCurrentItem(parent)
            for segment in session.segments:
                try:
                    name = str(Path(segment.path).relative_to(session.directory))
                except ValueError:
                    name = Path(segment.path).name
                child = QTreeWidgetItem(
                    [name, _duration(segment.duration), _size(segment.size)]
                )
                child.setData(0, Qt.UserRole, segment.path)
                child.setData(
                    0, Qt.UserRole + 1, f"segment:{session.id}:{segment.path}"
                )
                child.setData(
                    0, Qt.UserRole + 2, "\n".join(details + [f"片段：{segment.path}"])
                )
                child.setToolTip(0, segment.path)
                child.setSizeHint(0, QSize(0, UI_METRICS.row_height))
                parent.addChild(child)
                if child.data(0, Qt.UserRole + 1) == key:
                    self.history.setCurrentItem(child)
        self.history.blockSignals(False)
        self.history.verticalScrollBar().setValue(scroll)
        self._history_stack.setCurrentIndex(0 if sessions else 1)
        self._history_selection()

    def _selected_path(self):
        item = self.history.currentItem()
        return Path(item.data(0, Qt.UserRole)) if item else None

    def _history_selection(self):
        item = self.history.currentItem()
        path = self._selected_path()
        segment = item is not None and item.parent() is not None
        self.open_button.setText("打开文件" if segment else "打开目录")
        self.open_button.setEnabled(path is not None and path.exists())
        self.export_button.setEnabled(
            segment and path.is_file() and not self.controller.exporting
            if path
            else False
        )
        self.history_detail.setVisible(item is not None)
        if item:
            self.history_detail.setPlainText(item.data(0, Qt.UserRole + 2) or str(path))

    def _open(self):
        path = self._selected_path()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.notice.set_message("文件已移动或删除，请检查保存位置。", "warning")

    def _export_mp4(self):
        path = self._selected_path()
        if not self.export_button.isEnabled() or not path or not path.is_file():
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "导出 MP4", str(path.with_suffix(".mp4")), "MP4 (*.mp4)"
        )
        if output:
            self.controller.export(path, output)

    def _export_changed(self, busy, path):
        self.export_button.setText("导出中…" if busy else "导出 MP4")
        self.export_location.setVisible(bool(path))
        self._history_selection()

    def _open_export(self):
        if self.controller.export_path:
            path = Path(self.controller.export_path).parent
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
