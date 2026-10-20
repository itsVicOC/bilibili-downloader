"""Task center: durable downloads, current recordings and finalized segments."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
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
    ActionBar,
    ElidedLabel,
    EmptyState,
    MessageBox,
    Notice,
    PageHeader,
    PopupMenu,
    SectionCard,
    StatusBadge,
    repolish,
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
    undo_remove_requested = Signal()

    def __init__(self, downloads, controller, parent=None):
        super().__init__(parent)
        self.downloads = downloads
        self.controller = controller
        self._live_rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        self.header = PageHeader("任务中心", "下载进度、正在录制与本地历史，一处查看")
        layout.addWidget(self.header)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._download_tab()
        self._current_tab()
        self._history_tab()
        self.undo_notice = Notice(action="撤销", callback=self.undo_remove_requested.emit)
        layout.addWidget(self.undo_notice)
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
        self._download_tools = QFrame()
        self._download_tools.setObjectName("ToolSurface")
        self._download_tools.setAttribute(Qt.WA_StyledBackground, True)
        toolbar = QHBoxLayout(self._download_tools)
        toolbar.setContentsMargins(10, 8, 10, 8)
        toolbar.setSpacing(8)
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
        self.scope = ComboBox()
        self.scope.addItem("当前筛选", "visible")
        self.scope.addItem("所有任务", "all")
        self.scope.setFixedWidth(112)
        self.scope.setAccessibleName("批量操作范围")
        self.scope.setToolTip("批量操作仅作用于所选范围；当前筛选不会修改隐藏任务")
        self.scope.currentIndexChanged.connect(self.refresh_downloads)
        toolbar.addWidget(self.scope)
        self._download_count = QLabel("0 项")
        self._download_count.setObjectName("MetaLabel")
        toolbar.addWidget(self._download_count)
        toolbar.addStretch()
        self._bulk_buttons = []
        for text, signal in (
            ("暂停", self.pause_all_requested),
            ("继续", self.resume_all_requested),
            ("移除完成", self.clear_completed_requested),
        ):
            button = QPushButton(text)
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(signal.emit)
            self._bulk_buttons.append(button)
            toolbar.addWidget(button)
        more = QPushButton("更多")
        more.setObjectName("TableSubtleButton")
        more.setProperty("menuButton", True)
        menu = PopupMenu(more)
        menu.addAction("清理下载缓存", self.clear_cache_requested.emit)
        more.setMenu(menu)
        toolbar.addWidget(more)
        layout.addWidget(self._download_tools)
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
        for button, action, title in zip(self._bulk_buttons, ("pause", "resume", "clear"), ("暂停", "继续", "移除完成")):
            count_action = len(self.bulk_ids(action))
            button.setEnabled(count_action > 0)
            button.setText(f"{title} {count_action}")
            button.setToolTip(f"{title}{self.scope.currentText()}中的 {count_action} 项任务" + ("，保留媒体文件" if action == "clear" else ""))
        self._download_count.setText(f"{count} / {total} 项")
        self._download_stack.setCurrentIndex(1 if not total else 0 if count else 2)
        self._download_selection()

    def bulk_ids(self, action):
        states = {
            "pause": {TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.MERGING},
            "resume": {TaskStatus.PAUSED, TaskStatus.FAILED, TaskStatus.CANCELLED},
            "clear": {TaskStatus.COMPLETED},
        }[action]
        return [task_id for task_id, state in self.downloads._states.items()
                if state in states and (self.scope.currentData() == "all" or
                not self.downloads.isRowHidden(self.downloads._row_for(task_id)))]

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
        specification = self.downloads.item(row, 1)
        text = [item.text(), specification.toolTip() if specification else "", status.text() if status else ""]
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
                if controls is not None:
                    # Qt deletes replaced cell widgets on a later event-loop
                    # turn; hide immediately to avoid stale controls flashing.
                    controls.hide()
                controls = QWidget()
                controls.setProperty("roomId", row["room_id"])
                actions = QHBoxLayout(controls)
                actions.setContentsMargins(8, 0, 8, 0)
                actions.setSpacing(8)
                actions.setAlignment(Qt.AlignCenter)
                stop = QPushButton("停止本场")
                stop.setObjectName("TableDangerButton")
                stop.clicked.connect(
                    lambda _checked=False, rid=row["room_id"], button=stop: (
                        self._recording_action(rid, button)
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
            stop, view = controls.findChildren(QPushButton)
            retry = row["state"] == "error"
            stop.setText("重试录制" if retry else "停止本场")
            button_style = "TablePrimaryButton" if retry else "TableDangerButton"
            if stop.objectName() != button_style:
                stop.setObjectName(button_style)
                repolish(stop)
            stop.setProperty("liveAction", "start" if retry else "stop")
            stop.setToolTip(
                "重新获取直播地址并尝试录制" if retry
                else "停止当前场次，保留监控，下次开播自动录制"
            )
            view.setToolTip("在直播录制页面查看房间与完整状态")
            stop.setEnabled(
                row["state"] != "finalizing"
                and (
                    retry
                    or row["active"]
                    or row["state"]
                    in {"preparing", "queued", "reconnecting", "recording"}
                )
            )
            for button in (stop, view):
                button.ensurePolished()
                button.setFixedHeight(UI_METRICS.compact_button_height)
                button.setMinimumWidth(button.sizeHint().width())
                button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.current.horizontalHeader().resizeSection(
                4, max(180, controls.layout().minimumSize().width())
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

    def _recording_action(self, room_id, button):
        button.setEnabled(False)
        self.controller.command(button.property("liveAction"), room_id=room_id)

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
        self._history_stack.setMinimumHeight(120)
        self.history.setMinimumHeight(120)
        self._history_stack.addWidget(self.history)
        self._history_stack.addWidget(
            EmptyState("留住每一场相遇", "录制场次及已封口片段会保存在这里。")
        )
        layout.addWidget(self._history_stack, 1)
        self._history_sessions = {}
        self.history_summary = SectionCard("")
        self.history_summary.body.setContentsMargins(16, 16, 16, 16)
        self.history_summary.body.setSpacing(8)
        self.history_summary.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        # The summary heading carries selected-session context, rather than a
        # fixed card title that repeats the tab name.
        self.history_summary.hide()
        summary_heading = QHBoxLayout()
        self.history_title = ElidedLabel()
        self.history_title.setObjectName("SectionTitle")
        summary_heading.addWidget(self.history_title, 1)
        self.history_diagnostics = QPushButton("详细提示")
        self.history_diagnostics.setObjectName("TextButton")
        self.history_diagnostics.clicked.connect(lambda: MessageBox(
            "录制提示", self.history_detail.toPlainText(), self, tone="warning"
        ).exec())
        summary_heading.addWidget(self.history_diagnostics)
        self.history_status = StatusBadge("未导出")
        summary_heading.addWidget(self.history_status)
        self.history_summary.body.addLayout(summary_heading)
        self.history_specs = ElidedLabel()
        self.history_specs.setObjectName("MetaLabel")
        self.history_summary.body.addWidget(self.history_specs)
        self.history_path = ElidedLabel()
        self.history_path.setObjectName("MetaLabel")
        self.history_summary.body.addWidget(self.history_path)
        self.history_stage = ElidedLabel()
        self.history_stage.setObjectName("MetaLabel")
        self.history_stage.hide()
        self.history_summary.body.addWidget(self.history_stage)
        self.history_progress = QProgressBar()
        self.history_progress.setRange(0, 0)
        self.history_progress.setTextVisible(False)
        self.history_progress.setObjectName("ImportProgress")
        self.history_progress.hide()
        self.history_summary.body.addWidget(self.history_progress)
        self.history_notice = Notice()
        self.history_summary.body.addWidget(self.history_notice)
        layout.addWidget(self.history_summary)
        self.history_detail = QPlainTextEdit()
        self.history_detail.setReadOnly(True)
        self.history_detail.setMaximumHeight(112)
        self.history_detail.hide()
        # Keep the complete recording diagnostics available without making every
        # selection consume a second details panel.
        self.history_detail.setParent(self.history_summary)
        self.history_summary.setToolTip("")
        self.history_actions = ActionBar()
        footer = self.history_actions.row
        self.open_button = QPushButton("打开目录")
        self.open_button.clicked.connect(self._open)
        footer.addWidget(self.open_button)
        self.copy_path_button = QPushButton("复制路径")
        self.copy_path_button.clicked.connect(lambda: QApplication.clipboard().setText(str(self._selected_path() or "")))
        footer.addWidget(self.copy_path_button)
        footer.addStretch()
        self.export_button = QPushButton("合并导出 MP4")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self._export_mp4)
        self.export_play = QPushButton("打开 MP4")
        self.export_play.clicked.connect(self._play_export)
        self.export_play.hide()
        footer.addWidget(self.export_play)
        self.export_location = QPushButton("所在目录")
        self.export_location.setObjectName("TextButton")
        self.export_location.clicked.connect(self._open_export)
        self.export_location.hide()
        footer.addWidget(self.export_location)
        footer.addWidget(self.export_button)
        layout.addWidget(self.history_actions)
        self.tabs.addTab(tab, "录制历史")

    def update_history(self, sessions):
        self._history_sessions = {s.id: s for s in sessions}
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
            if session.mp4_export:
                status += "\nMP4 · " + {"queued": "等待导出", "running": "导出中", "completed": "已导出", "failed": "失败"}[session.mp4_export.status]
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
            parent.setData(0, Qt.UserRole + 3, session.id)
            parent.setToolTip(0, "\n".join(details))
            parent.setSizeHint(
                0,
                QSize(
                    0,
                    max(
                        UI_METRICS.row_height,
                        self.history.fontMetrics().height() * (status.count("\n") + 1) + 20,
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
        session = self._selected_session()
        export = session.mp4_export if session else None
        busy = bool(export and export.status in {"queued", "running"})
        eligible = bool(session and session.status != "recording" and session.segments)
        self.export_button.setText("导出片段 MP4" if segment else "重试合并 MP4" if export and export.status == "failed" else "合并导出 MP4")
        self.export_button.setEnabled(
            bool(path and path.is_file() and not self.controller.exporting) if segment
            else eligible and not busy
        )
        self.copy_path_button.setEnabled(path is not None)
        self.history_summary.setVisible(item is not None)
        self.history_detail.hide()
        if item:
            self.history_detail.setPlainText(item.data(0, Qt.UserRole + 2) or str(path))
        if session:
            self.history_diagnostics.setVisible(bool(session.gaps or session.warnings or (export and export.error)))
            self.history_summary.setToolTip(self.history_detail.toPlainText())
            self.history_title.set_full_text(f"{session.room.author or '未命名直播间'} · {_local_time(session.started_at)}")
            integrity = f"{len(session.gaps)} 处缺口 / {len(session.warnings)} 条提示" if session.gaps or session.warnings else "未记录缺口"
            self.history_specs.set_full_text(f"{len(session.segments)} 个片段 · {_duration(sum(s.duration for s in session.segments))} · {_size(session.total_size)} · {integrity}")
            self.history_path.set_full_text(f"{'片段' if segment else '录制目录'}：{path}")
            text, tone = ("未导出", "muted")
            if export:
                text, tone = {"queued": ("等待导出", "warning"), "running": ("导出中", "active"), "completed": ("已导出 MP4", "success"), "failed": ("导出失败", "danger")}[export.status]
            self.history_status.setText(text)
            self.history_status.set_tone(tone)
            self.history_progress.setVisible(bool(export and export.status == "running"))
            message = "收尾后可合并导出，原始分段会保留。" if session.status == "recording" else ""
            if export:
                message = export.error if export.status == "failed" else export.progress
                if export.error:
                    self.history_detail.appendPlainText(f"\n合并导出：{export.error}")
                if export.status == "completed":
                    self.history_path.set_full_text(f"MP4：{export.path}")
            if not message and (session.gaps or session.warnings):
                message = "录制存在缺口或提示，合并仅衔接已保存的内容。详情见场次提示。"
            failed = bool(export and export.status == "failed")
            self.history_stage.set_full_text(message if not failed else "")
            self.history_stage.setVisible(bool(message) and not failed)
            self.history_notice.set_message(message[:180] if failed else "", "danger")
            self.history_notice.setToolTip(message)
            notice_width = max(280, self.history_summary.width() - 40)
            notice_height = self.history_notice.layout().totalHeightForWidth(notice_width)
            self.history_notice.setMinimumHeight(max(44, notice_height))
            self.history_summary.setMinimumHeight(self.history_summary.body.sizeHint().height())
            self.history_summary.updateGeometry()
        exported = self._selected_export_path()
        self.export_play.setVisible(bool(exported and exported.is_file()))
        self.export_location.setVisible(bool(exported and exported.is_file()))

    def _selected_session(self):
        item = self.history.currentItem()
        if item and item.parent():
            item = item.parent()
        return self._history_sessions.get(item.data(0, Qt.UserRole + 3)) if item else None

    def _selected_export_path(self):
        session = self._selected_session()
        item = self.history.currentItem()
        if (item and item.parent() and self.controller.export_path and self.controller.export_source
                and self._selected_path().resolve() == Path(self.controller.export_source)):
            return Path(self.controller.export_path)
        if session and session.mp4_export and session.mp4_export.status == "completed":
            return Path(session.mp4_export.path)
        if (session and self.controller.export_path and self.controller.export_source
                and any(Path(s.path).resolve() == Path(self.controller.export_source)
                        for s in session.segments)):
            return Path(self.controller.export_path)
        return None

    def _open(self):
        path = self._selected_path()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.notice.set_message("文件已移动或删除，请检查保存位置。", "warning")

    def _export_mp4(self):
        path = self._selected_path()
        if not self.export_button.isEnabled() or not path:
            return
        session = self._selected_session()
        segment = self.history.currentItem().parent() is not None
        proposed = path.with_suffix(".mp4") if segment else Path(session.directory) / "整场直播.mp4"
        output, _ = QFileDialog.getSaveFileName(
            self, self.export_button.text(), str(proposed), "MP4 (*.mp4)"
        )
        if output:
            if segment:
                self.controller.export(path, output)
            else:
                self.controller.export_session(session.id, output)

    def _export_changed(self, busy, path):
        self._history_selection()

    def _open_export(self):
        exported = self._selected_export_path()
        if exported:
            path = exported.parent
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _play_export(self):
        path = self._selected_export_path()
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
