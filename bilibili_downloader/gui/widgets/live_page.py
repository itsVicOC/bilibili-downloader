"""Live subscriptions and recordings, driven by a non-Qt background service."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import QLockFile, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.live_models import LiveSettings
from bilibili_downloader.core.live_repository import LiveRepository
from bilibili_downloader.core.live_service import LiveService


def _size(value):
    return (
        f"{value / 1024**2:.1f} MB" if value < 1024**3 else f"{value / 1024**3:.2f} GB"
    )


def _duration(value):
    seconds = max(0, int(value))
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class LiveSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("直播录制设置")
        self.setMinimumWidth(560)
        layout = QFormLayout(self)
        self.directory = QLineEdit(settings.output_dir)
        self.recorder = QLineEdit(settings.recorder_path)
        self.recorder.setPlaceholderText("full 包自动检测；lite 包请选择配套引擎")
        for label, entry, folder in (
            ("保存目录", self.directory, True),
            ("录制引擎", self.recorder, False),
        ):
            row = QHBoxLayout()
            row.addWidget(entry)
            button = QPushButton("选择…")
            button.clicked.connect(
                lambda checked=False, field=entry, is_folder=folder: self._browse(
                    field, is_folder
                )
            )
            row.addWidget(button)
            layout.addRow(label, row)
        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 4)
        self.concurrent.setValue(settings.max_concurrent)
        layout.addRow("同时录制", self.concurrent)
        self.segment = QSpinBox()
        self.segment.setRange(1, 1440)
        self.segment.setValue(settings.segment_seconds // 60)
        self.segment.setSuffix(" 分钟")
        layout.addRow("分段时长", self.segment)
        self.free_space = QSpinBox()
        self.free_space.setRange(1, 1024)
        self.free_space.setValue(settings.minimum_free_bytes // 1024**3)
        self.free_space.setSuffix(" GiB")
        layout.addRow("保留可用空间", self.free_space)
        note = QLabel(
            "目录与分段时长用于新添加的直播间。应用退出或电脑睡眠时无法录制。"
        )
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse(self, entry, folder):
        value = (
            QFileDialog.getExistingDirectory(self, "选择录制目录", entry.text())
            if folder
            else QFileDialog.getOpenFileName(
                self, "选择 biliflow-recorder", entry.text()
            )[0]
        )
        if value:
            entry.setText(value)

    def _accept(self):
        if not self.directory.text().strip():
            QMessageBox.warning(self, "保存目录", "请选择录制保存目录")
            return
        self.accept()

    def settings(self):
        return LiveSettings(
            recorder_path=self.recorder.text().strip(),
            output_dir=str(Path(self.directory.text().strip()).expanduser().resolve()),
            max_concurrent=self.concurrent.value(),
            segment_seconds=self.segment.value() * 60,
            minimum_free_bytes=self.free_space.value() * 1024**3,
        )


class LivePage(QWidget):
    settings_changed = Signal(object)

    def __init__(self, config, confirm_copyright, parent=None):
        super().__init__(parent)
        self._config = config
        self._confirm_copyright = confirm_copyright
        self.service = None
        self._exports = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="live-export"
        )
        self._export = None
        self._export_cancel = Event()
        self._history_fingerprint = None
        self._history_revision = -1
        self._quality_fingerprint = None
        self._lock_file = QLockFile(str(config.data_dir / "live.lock"))
        config.data_dir.mkdir(parents=True, exist_ok=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 16)
        title = QLabel("直播录制")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        caption = QLabel(
            "应用运行期间开播自动录制 · AVC/AAC · 断线后重新拉流，缺失内容无法补录"
        )
        caption.setWordWrap(True)
        caption.setObjectName("Caption")
        layout.addWidget(caption)
        row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setPlaceholderText("粘贴直播间链接、房间号或 b23 短链")
        self.source.returnPressed.connect(self._add)
        row.addWidget(self.source, 1)
        add = QPushButton("添加并监控")
        add.setObjectName("PrimaryButton")
        add.clicked.connect(self._add)
        row.addWidget(add)
        settings = QPushButton("录制设置")
        settings.clicked.connect(self._settings)
        row.addWidget(settings)
        layout.addLayout(row)
        self.rooms = QTableWidget(0, 5)
        self.rooms.setHorizontalHeaderLabels(
            ["直播间", "状态", "已录时长", "大小 / 速度", "详情"]
        )
        self.rooms.setSelectionBehavior(QTableWidget.SelectRows)
        self.rooms.setSelectionMode(QTableWidget.SingleSelection)
        self.rooms.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rooms.verticalHeader().hide()
        self.rooms.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.rooms.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.rooms.setColumnWidth(0, 220)
        self.rooms.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.rooms.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.rooms, 2)
        actions = QHBoxLayout()
        for text, action in (
            ("立即开始", "start"),
            ("停止本场", "stop"),
            ("开启监控", "enable"),
            ("关闭监控", "disable"),
            ("移除", "remove"),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, op=action: self._command(op))
            actions.addWidget(button)
        layout.addLayout(actions)
        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("下次录制画质"))
        self.quality = QComboBox()
        self.quality.addItem("当前可用最高画质", 0)
        self.quality.activated.connect(self._set_quality)
        quality_row.addWidget(self.quality)
        room_settings = QPushButton("房间设置…")
        room_settings.clicked.connect(self._room_settings)
        quality_row.addWidget(room_settings)
        quality_row.addStretch()
        layout.addLayout(quality_row)
        layout.addWidget(QLabel("录制历史 · 选择已完成片段可打开或导出 MP4"))
        self.history = QTreeWidget()
        self.history.setHeaderLabels(["场次 / 文件", "状态 / 时长", "大小"])
        self.history.setColumnWidth(0, 330)
        layout.addWidget(self.history, 2)
        history_actions = QHBoxLayout()
        for text, handler in (
            ("打开文件 / 目录", self._open),
            ("导出 MP4", self._export_mp4),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            history_actions.addWidget(button)
        history_actions.addStretch()
        layout.addLayout(history_actions)
        self.message = QLabel("")
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        try:
            if not self._lock_file.tryLock(0):
                raise RuntimeError(
                    "另一个 BiliFlow 实例正在管理直播录制，请在该实例中操作"
                )
            self.repository = LiveRepository(config.data_dir / "live.sqlite3")
            self.service = LiveService(
                self.repository, config.load().live, config.auth_cookies
            )
            self.service.start()
            self.destroyed.connect(self.service.request_shutdown)
            if self.repository.recovered_database_path:
                self.message.setText("损坏的直播数据库已隔离备份，请重新添加直播间")
            elif self.repository.invalid_records:
                self.message.setText("部分直播记录无法读取，原始记录已保留在数据库中")
        except Exception as exc:
            self.message.setText(redact_sensitive_text(str(exc)))
            add.setEnabled(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def _room_id(self):
        row = self.rooms.currentRow()
        item = self.rooms.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _add(self):
        if self.service and self.source.text().strip() and self._confirm_copyright():
            self.service.command("add", source=self.source.text().strip())
            self.source.clear()
            self.message.setText("正在查询直播间…")

    def _command(self, action):
        room_id = self._room_id()
        if self.service and room_id:
            if action in {"start", "enable"} and not self._confirm_copyright():
                return
            self.service.command(action, room_id=room_id)

    def _selection_changed(self):
        room_id = self._room_id()
        row = (
            next((r for r in self.service.snapshot() if r["room_id"] == room_id), None)
            if self.service
            else None
        )
        self._quality_fingerprint = (
            (room_id, row["quality"], row["qualities"]) if row else None
        )
        self.quality.clear()
        self.quality.addItem("当前可用最高画质", 0)
        if row:
            for quality in row["qualities"]:
                self.quality.addItem(quality["label"], quality["qn"])
            index = self.quality.findData(row["quality"])
            self.quality.setCurrentIndex(max(index, 0))

    def _set_quality(self):
        if self.service and self._room_id():
            self.service.command(
                "quality", room_id=self._room_id(), quality=self.quality.currentData()
            )

    def _settings(self):
        dialog = LiveSettingsDialog(self._config.load().live, self)
        if dialog.exec():
            settings = self._config.load().model_copy(deep=True)
            settings.live = dialog.settings()
            try:
                self._config.save(settings)
            except OSError as exc:
                self.message.setText(str(exc))
                return
            self.settings_changed.emit(settings)
            if self.service:
                self.service.command("settings", settings=settings.live)

    def _room_settings(self):
        room_id = self._room_id()
        row = (
            next((r for r in self.service.snapshot() if r["room_id"] == room_id), None)
            if self.service
            else None
        )
        if not row:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"直播间 {room_id} 设置")
        form = QFormLayout(dialog)
        directory = QLineEdit(row["output_dir"])
        segment = QSpinBox()
        segment.setRange(1, 1440)
        segment.setValue(row["segment_seconds"] // 60)
        segment.setSuffix(" 分钟")
        form.addRow("保存目录", directory)
        form.addRow("分段时长", segment)
        form.addRow(QLabel("请先停止本场并等待收尾，再修改这些设置。"))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() and directory.text().strip():
            self.service.command(
                "room_settings",
                room_id=room_id,
                output_dir=directory.text().strip(),
                segment_seconds=segment.value() * 60,
            )

    def refresh(self):
        if not self.service:
            return
        selected = self._room_id()
        rows = self.service.snapshot()
        self.rooms.blockSignals(True)
        self.rooms.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [
                f"{row['author']} · {row['room_id']}\n{row['title']}",
                row["state_label"] + (" · 自动" if row["enabled"] else ""),
                _duration(row["duration"]),
                f"{_size(row['size'])}\n{_size(row['speed'])}/s",
                row["detail"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.UserRole, row["room_id"])
                self.rooms.setItem(index, column, item)
            if row["room_id"] == selected:
                self.rooms.selectRow(index)
        self.rooms.resizeRowsToContents()
        self.rooms.blockSignals(False)
        selected_row = next((r for r in rows if r["room_id"] == selected), None)
        if selected_row and self._quality_fingerprint != (
            selected,
            selected_row["quality"],
            selected_row["qualities"],
        ):
            self._selection_changed()
        for message in self.service.messages():
            self.message.setText(message)
        try:
            revision = self.repository.history_revision
            sessions = (
                self.repository.sessions()
                if revision != self._history_revision
                else None
            )
            self._history_revision = revision
            if sessions is None:
                sessions = []
                fingerprint = self._history_fingerprint
            else:
                fingerprint = [
                    (s.id, s.status, len(s.segments), len(s.gaps), len(s.warnings))
                    for s in sessions
                ]
            if fingerprint != self._history_fingerprint:
                self._history_fingerprint = fingerprint
                self.history.clear()
                labels = {
                    "recording": "录制中",
                    "completed": "已结束",
                    "stopped": "已停止",
                    "failed": "失败",
                    "interrupted": "中断",
                }
                for session in sessions:
                    summary = labels.get(session.status, session.status)
                    if session.gaps or session.warnings:
                        summary += f" · {len(session.gaps)} 处缺口 / {len(session.warnings)} 条提示"
                    parent = QTreeWidgetItem(
                        [
                            f"{session.room.author} · {session.started_at}",
                            summary,
                            _size(session.total_size),
                        ]
                    )
                    parent.setData(0, Qt.UserRole, session.directory)
                    parent.setToolTip(
                        0, "\n".join(session.warnings + [str(g) for g in session.gaps])
                    )
                    self.history.addTopLevelItem(parent)
                    for segment in session.segments:
                        item = QTreeWidgetItem(
                            [
                                str(Path(segment.path).relative_to(session.directory)),
                                _duration(segment.duration),
                                _size(segment.size),
                            ]
                        )
                        item.setData(0, Qt.UserRole, segment.path)
                        parent.addChild(item)
        except (OSError, ValueError) as exc:
            self.message.setText(redact_sensitive_text(str(exc)))
        if self._export and self._export.done():
            try:
                ok, result = self._export.result()
                self.message.setText(
                    "MP4 导出完成" if ok else redact_sensitive_text(result)
                )
            except Exception as exc:
                self.message.setText(redact_sensitive_text(str(exc)))
            self._export = None

    def _selected_path(self):
        item = self.history.currentItem()
        return Path(item.data(0, Qt.UserRole)) if item else None

    def _open(self):
        path = self._selected_path()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _export_mp4(self):
        path = self._selected_path()
        if not path or not path.is_file() or self._export:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "导出 MP4", str(path.with_suffix(".mp4")), "MP4 (*.mp4)"
        )
        if output and Path(output).resolve() != path.resolve():
            self._export_cancel.clear()
            self._export = self._exports.submit(
                FFmpegManager.remux_live,
                path,
                Path(output),
                self._config.load().ffmpeg_path or None,
                self._export_cancel.is_set,
            )
            self.message.setText("正在无损转封装，源文件会保留…")

    def shutdown(self):
        self.timer.stop()
        self._export_cancel.set()
        if self.service:
            self.service.request_shutdown()
            if self.service.stopped:
                self._lock_file.unlock()
        self._exports.shutdown(wait=False, cancel_futures=True)
