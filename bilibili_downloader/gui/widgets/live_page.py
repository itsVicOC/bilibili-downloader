"""Live room workspace backed by the shared live UI controller."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.live_models import LiveState
from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.core.recorder import find_recorder
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    EmptyState,
    FieldRow,
    Notice,
    PageHeader,
    PopupMenu,
    SectionCard,
    StatusBadge,
    repolish,
    scroll_area,
    stepper,
)
from bilibili_downloader.gui.widgets.download_list import (
    STATUS_TONE_ROLE,
    _StatusDelegate,
)
from bilibili_downloader.gui.widgets.hero_panel import HeroPanel


def _size(value):
    return (
        f"{value / 1024**2:.1f} MB" if value < 1024**3 else f"{value / 1024**3:.2f} GB"
    )


def _duration(value):
    seconds = max(0, int(value))
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def live_tone(state):
    if state == LiveState.ERROR.value:
        return "danger"
    if state == LiveState.RECONNECTING.value:
        return "warning"
    if state in {
        LiveState.RECORDING.value,
        LiveState.PREPARING.value,
        LiveState.FINALIZING.value,
    }:
        return "active"
    return "muted"


class LiveSettingsDialog(SettingsDialog):
    """Compatibility dialog using the same settings content as the page."""

    def __init__(self, settings, parent=None):
        super().__init__(AppSettings(live=settings), parent)
        self.tabs.setCurrentIndex(1)

    def settings(self):
        return self.get_settings().live


class LivePage(QWidget):
    settings_changed = Signal(object)
    settings_requested = Signal(int)
    history_requested = Signal()

    def __init__(self, config, confirm_copyright, parent=None, controller=None):
        super().__init__(parent)
        self._config = config
        self._confirm_copyright = confirm_copyright
        self._own_controller = controller is None
        self.controller = controller or LiveUiController(config, self)
        self._selected_id = None
        self._rows = []
        self._quality_fingerprint = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)
        header = PageHeader("直播录制", "守候开播，记录每一场喜欢的直播")
        history = QPushButton("录制历史")
        history.setObjectName("TextButton")
        history.clicked.connect(self.history_requested.emit)
        header.actions.addWidget(history)
        settings = QPushButton("录制设置")
        settings.clicked.connect(self._settings)
        header.actions.addWidget(settings)
        root.addWidget(header)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(20)
        hero = HeroPanel()
        hero.set_compact(True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(10)
        hint = QLabel("添加直播间 · 应用运行期间开播自动录制")
        hint.setObjectName("HeroTitle")
        hero_layout.addWidget(hint)
        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        self.source = ChineseLineEdit()
        self.source.setPlaceholderText("直播间链接、房间号或 b23.tv 短链")
        self.source.returnPressed.connect(self._add)
        self.source.textChanged.connect(
            lambda text: self.add_button.setEnabled(
                bool(text.strip())
                and self.service is not None
                and not self.controller.adding
            )
        )
        input_row.addWidget(self.source, 1)
        self.add_button = QPushButton("添加并监控")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.clicked.connect(self._add)
        input_row.addWidget(self.add_button)
        hero_layout.addLayout(input_row)
        column.addWidget(hero)
        self.engine_notice = Notice()
        column.addWidget(self.engine_notice)
        self._content = QWidget()
        self._content_layout = QBoxLayout(QBoxLayout.LeftToRight, self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(20)
        self._rooms_card = SectionCard("监控列表")
        self._count = StatusBadge("0 个直播间")
        self._rooms_card.header.addWidget(self._count)
        self.rooms = QTableWidget(0, 4)
        self.rooms.setHorizontalHeaderLabels(
            ["直播间", "状态 / 监控", "已录时长", "大小 / 速度"]
        )
        self.rooms.setSelectionBehavior(QTableWidget.SelectRows)
        self.rooms.setSelectionMode(QTableWidget.SingleSelection)
        self.rooms.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rooms.setShowGrid(False)
        self.rooms.verticalHeader().hide()
        self.rooms.verticalHeader().setDefaultSectionSize(UI_METRICS.row_height)
        table_header = self.rooms.horizontalHeader()
        table_header.setMinimumSectionSize(40)
        table_header.setSectionResizeMode(0, QHeaderView.Stretch)
        for index, width in ((1, 142), (2, 110), (3, 120)):
            table_header.setSectionResizeMode(index, QHeaderView.Fixed)
            table_header.resizeSection(index, width)
        self.rooms.setItemDelegateForColumn(1, _StatusDelegate(self.rooms))
        self.rooms.itemSelectionChanged.connect(self._selection_changed)
        self._room_stack = QStackedWidget()
        self._room_stack.addWidget(self.rooms)
        self._room_stack.addWidget(
            EmptyState("等待下一场星光", "在上方添加直播间，开播后可自动录制。")
        )
        self._room_stack.setMinimumHeight(240)
        self._rooms_card.body.addWidget(self._room_stack, 1)
        self._content_layout.addWidget(self._rooms_card, 1)
        self._detail_card = SectionCard("房间详情")
        self._detail_card.setMinimumWidth(300)
        self._detail_badge = StatusBadge("未选择房间")
        self._detail_card.header.addWidget(self._detail_badge)
        self._detail_empty = QLabel("选择一个直播间，查看状态与录制设置")
        self._detail_empty.setObjectName("MetaLabel")
        self._detail_empty.setWordWrap(True)
        self._detail_card.body.addWidget(self._detail_empty)
        self._detail_controls = QWidget()
        details = QVBoxLayout(self._detail_controls)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(12)
        self._room_name = QLabel()
        self._room_name.setObjectName("SectionTitle")
        self._room_name.setWordWrap(True)
        self._room_name.setTextFormat(Qt.PlainText)
        details.addWidget(self._room_name)
        self._room_id_label = QLabel()
        self._room_id_label.setObjectName("MetaLabel")
        details.addWidget(self._room_id_label)
        self._detail = QLabel()
        self._detail.setTextFormat(Qt.PlainText)
        self._detail.setWordWrap(True)
        details.addWidget(self._detail)
        self.quality = ComboBox()
        self.quality.activated.connect(self._set_quality)
        details.addWidget(FieldRow("下次拉流画质", self.quality))
        self._directory = QLineEdit()
        self._directory.setReadOnly(True)
        details.addWidget(FieldRow("保存目录", self._directory))
        self._segment = QLabel()
        self._segment.setObjectName("MetaLabel")
        details.addWidget(self._segment)
        self.monitor = QCheckBox("自动监控并录制")
        self.monitor.setToolTip("关闭监控会停止本场录制；开启后等待下一场开播")
        self.monitor.toggled.connect(self._toggle_monitor)
        self._monitor_hint = QLabel(
            "停止本场会保留下次自动录制；关闭监控会同时停止本场。"
        )
        self._monitor_hint.setObjectName("MetaLabel")
        self._monitor_hint.setWordWrap(True)
        details.addWidget(self._monitor_hint)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.start_stop = QPushButton("立即开始")
        self.start_stop.setObjectName("PrimaryButton")
        self.start_stop.clicked.connect(self._start_stop)
        buttons.addWidget(self.start_stop)
        self.room_settings = QPushButton("房间设置")
        self.room_settings.clicked.connect(self._room_settings)
        buttons.addWidget(self.room_settings)
        more = QPushButton("更多")
        more.setObjectName("TextButton")
        more.setProperty("menuButton", True)
        menu = PopupMenu(more)
        self.remove_action = menu.addAction("移除直播间")
        self.remove_action.triggered.connect(lambda: self._command("remove"))
        more.setMenu(menu)
        buttons.addWidget(more)
        self._detail_card.body.addWidget(self._detail_controls)
        self._detail_card.body.addStretch()
        self._content_layout.addWidget(self._detail_card)
        column.addWidget(self._content, 1)
        self._scroll = scroll_area(body)
        root.addWidget(self._scroll, 1)
        self._action_bar = QWidget()
        action_bar = QHBoxLayout(self._action_bar)
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(12)
        action_bar.addWidget(self.monitor)
        action_bar.addStretch()
        action_bar.addLayout(buttons)
        root.addWidget(self._action_bar)
        self._notice = Notice()
        self.message = self._notice.label
        root.addWidget(self._notice)
        self.controller.snapshot_changed.connect(self._update_rows)
        self.controller.message_changed.connect(self._notice.set_message)
        self.controller.addition_changed.connect(self._addition_changed)
        self._notice.set_message(self.controller.message, self.controller.message_tone)
        self.add_button.setEnabled(False)
        self._update_rows(self.controller.rows)
        self.check_engine()

    @property
    def service(self):
        return self.controller.service

    @property
    def repository(self):
        return self.controller.repository

    @property
    def _lock_file(self):
        return self.controller.lock

    def check_engine(self):
        try:
            find_recorder(self._config.load().live.recorder_path)
            self.engine_notice.set_message("")
        except (OSError, ValueError) as exc:
            self.engine_notice.set_message(str(exc), "warning")

    def resizeEvent(self, event):
        narrow = event.size().width() < 1000 or event.size().height() < 700
        self._stacked_details = narrow
        self._content_layout.setDirection(
            QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        )
        self._detail_card.setMaximumWidth(16777215 if narrow else 380)
        self._room_stack.setMinimumHeight(180 if narrow else 280)
        self._update_table_height()
        super().resizeEvent(event)

    def _update_table_height(self):
        stacked = getattr(self, "_stacked_details", True)
        self.rooms.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if stacked else Qt.ScrollBarAsNeeded
        )
        height = (
            max(40, self.rooms.horizontalHeader().height())
            + sum(self.rooms.rowHeight(i) for i in range(self.rooms.rowCount()))
            + self.rooms.frameWidth() * 2
        )
        # Stacked content scrolls as one page; never nest the room table's scroll.
        self.rooms.setMinimumHeight(max(140, height) if stacked else 140)

    def _room_id(self):
        item = self.rooms.item(self.rooms.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def _selected_row(self):
        return next(
            (row for row in self._rows if row["room_id"] == self._room_id()), None
        )

    def _add(self):
        if (
            self.service
            and not self.controller.adding
            and self.source.text().strip()
            and self._confirm_copyright()
        ):
            self.controller.add(self.source.text().strip())

    def _addition_changed(self, adding):
        self.add_button.setEnabled(
            not adding and self.service is not None and bool(self.source.text().strip())
        )
        self.add_button.setText("查询中…" if adding else "添加并监控")

    def _command(self, action):
        room_id = self._room_id()
        if room_id is None or not self.service:
            return
        if action in {"start", "enable"} and not self._confirm_copyright():
            self._selection_changed()
            return
        self.controller.command(action, room_id=room_id)
        self.start_stop.setEnabled(False)

    def _start_stop(self):
        row = self._selected_row()
        if row:
            self._command(
                "stop"
                if row["active"]
                or row["state"] in {"preparing", "queued", "reconnecting", "recording"}
                else "start"
            )

    def _toggle_monitor(self, enabled):
        self._command("enable" if enabled else "disable")

    def _selection_changed(self):
        row = self._selected_row()
        self._selected_id = row["room_id"] if row else None
        self._detail_controls.setVisible(row is not None)
        self._action_bar.setVisible(row is not None)
        self._detail_empty.setVisible(row is None)
        if not row:
            self._detail_badge.setText("未选择房间")
            self._detail_badge.set_tone("muted")
            self._quality_fingerprint = None
            return
        self._room_name.setText(row["author"] or "未命名直播间")
        self._room_id_label.setText(f"房间 {row['room_id']} · {row['title']}")
        self._room_id_label.setWordWrap(True)
        self._room_id_label.setTextFormat(Qt.PlainText)
        self._detail_badge.setText(row["state_label"])
        self._detail_badge.set_tone(live_tone(row["state"]))
        self._detail.setText(row["detail"] or "等待直播状态更新")
        self._directory.setText(row["output_dir"])
        self._directory.setToolTip(row["output_dir"])
        self._directory.setCursorPosition(0)
        self._segment.setText(
            f"分段时长 {row['segment_seconds'] // 60} 分钟 · 画质修改在下次拉流生效"
        )
        self._segment.setWordWrap(True)
        fingerprint = (row["room_id"], row["quality"], row["qualities"])
        if fingerprint != self._quality_fingerprint:
            self._quality_fingerprint = fingerprint
            self.quality.clear()
            self.quality.addItem("当前可用最高画质", 0)
            for quality in row["qualities"]:
                self.quality.addItem(quality["label"], quality["qn"])
            self.quality.setCurrentIndex(max(0, self.quality.findData(row["quality"])))
        self.monitor.blockSignals(True)
        self.monitor.setChecked(row["enabled"])
        self.monitor.blockSignals(False)
        active = row["active"] or row["state"] in {
            "recording",
            "preparing",
            "queued",
            "reconnecting",
        }
        finalizing = row["state"] == "finalizing"
        self.start_stop.setText(
            "正在收尾…" if finalizing else "停止本场" if active else "立即开始"
        )
        role = "SubtleButton" if active else "PrimaryButton"
        if self.start_stop.objectName() != role:
            self.start_stop.setObjectName(role)
            repolish(self.start_stop)
        self.start_stop.setEnabled(not finalizing)
        self.monitor.setEnabled(not finalizing)
        locked = row["active"] or row["state"] in {
            "recording",
            "reconnecting",
            "finalizing",
        }
        self.room_settings.setEnabled(not locked)
        self.remove_action.setEnabled(not locked)

    def _set_quality(self):
        if self._room_id():
            self.controller.command(
                "quality", room_id=self._room_id(), quality=self.quality.currentData()
            )

    def _settings(self):
        if not self._own_controller:
            self.settings_requested.emit(1)
            return
        dialog = LiveSettingsDialog(self._config.load().live, self)
        if dialog.exec():
            settings = self._config.load().model_copy(deep=True)
            settings.live = dialog.settings()
            try:
                self._config.save(settings)
            except OSError as exc:
                self.controller.notify(str(exc), "danger")
                return
            self.settings_changed.emit(settings)
            self.controller.command("settings", settings=settings.live)
            self.check_engine()

    def _room_settings(self):
        row = self._selected_row()
        if not row or not self.room_settings.isEnabled():
            return
        dialog = self._build_room_settings_dialog(row)
        if dialog.exec():
            self.controller.command(
                "room_settings",
                room_id=row["room_id"],
                output_dir=dialog.directory.text().strip(),
                segment_seconds=(
                    row["segment_seconds"]
                    if dialog.segment.value() == row["segment_seconds"] // 60
                    else dialog.segment.value() * 60
                ),
            )

    def _build_room_settings_dialog(self, row):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"直播间 {row['room_id']} 设置")
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        card = SectionCard("房间录制设置")
        directory = QLineEdit(row["output_dir"])
        directory.setToolTip(row["output_dir"])
        directory.setCursorPosition(0)
        dialog.directory = directory
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(directory, 1)
        browse = QPushButton("选择…")

        def select_directory():
            value = QFileDialog.getExistingDirectory(
                dialog, "选择录制目录", directory.text()
            )
            if value:
                directory.setText(value)

        browse.clicked.connect(select_directory)
        path_layout.addWidget(browse)
        directory_field = FieldRow("保存目录", path_row)
        card.body.addWidget(directory_field)
        segment = QSpinBox()
        dialog.segment = segment
        segment.setRange(1, 1440)
        segment.setValue(row["segment_seconds"] // 60)
        segment.setSuffix(" 分钟")
        segment_row, _, _ = stepper(segment)
        card.body.addWidget(FieldRow("分段时长", segment_row))
        card.body.addWidget(Notice("修改仅影响这个直播间；录制或收尾期间无法保存。"))
        layout.addWidget(card)
        notice = Notice()
        layout.addWidget(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Save).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")

        def save():
            current = next(
                (r for r in self.controller.rows if r["room_id"] == row["room_id"]),
                None,
            )
            if (
                not current
                or current["active"]
                or current["state"] in {"recording", "reconnecting", "finalizing"}
            ):
                notice.set_message("请先停止本场并等待收尾完成。", "warning")
                return
            if not directory.text().strip():
                notice.set_message("请选择有效的录制保存目录。", "danger")
                directory_field.set_error("请选择有效的录制保存目录。")
                directory.setFocus()
                return
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog

    def _update_rows(self, rows):
        selected = self._room_id()
        scroll = self.rooms.verticalScrollBar().value()
        self._rows = rows
        self.rooms.blockSignals(True)
        self.rooms.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [
                f"{row['author']} · {row['room_id']}\\n{row['title']}",
                row["state_label"]
                + ("\\n自动监控" if row["enabled"] else "\\n手动录制"),
                _duration(row["duration"]),
                f"{_size(row['size'])}\\n{_size(row['speed'])}/s",
            ]
            for column, value in enumerate(values):
                item = self.rooms.item(index, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.rooms.setItem(index, column, item)
                item.setText(value.replace("\\n", "\n"))
                item.setToolTip(
                    value.replace("\\n", "\n")
                    + ("\n" + row["detail"] if column == 1 else "")
                )
                if column == 0:
                    item.setData(Qt.UserRole, row["room_id"])
                elif column == 1:
                    item.setData(STATUS_TONE_ROLE, live_tone(row["state"]))
            self.rooms.setRowHeight(
                index,
                max(UI_METRICS.row_height, self.rooms.fontMetrics().height() * 2 + 20),
            )
            if row["room_id"] == selected:
                self.rooms.selectRow(index)
        if selected is not None and not any(row["room_id"] == selected for row in rows):
            self.rooms.clearSelection()
            self.rooms.setCurrentCell(-1, -1)
        self.rooms.blockSignals(False)
        self._update_table_height()
        self.rooms.verticalScrollBar().setValue(scroll)
        self._room_stack.setCurrentIndex(0 if rows else 1)
        self._count.setText(f"{len(rows)} 个直播间")
        self._selection_changed()

    def select_room(self, room_id):
        for index, row in enumerate(self._rows):
            if row["room_id"] == room_id:
                self.rooms.selectRow(index)
                self.rooms.scrollToItem(self.rooms.item(index, 0))
                if getattr(self, "_stacked_details", False):
                    self._scroll.ensureWidgetVisible(self._detail_card)
                break

    def refresh(self):
        self.controller.refresh()

    def shutdown(self):
        self.controller.shutdown()
