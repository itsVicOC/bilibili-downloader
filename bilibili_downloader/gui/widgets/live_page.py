"""Live room workspace backed by the shared live UI controller."""

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.live_models import LiveState
from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.core.recorder import find_recorder
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.check_box import CheckBox
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    ActionButton,
    CollapsibleSection,
    EmptyState,
    FieldRow,
    Notice,
    PageHeader,
    PopupMenu,
    ReadOnlyPath,
    ResponsiveActions,
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
from bilibili_downloader.gui.widgets.glass_surface import ItemViewSurface
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


class _RoomDelegate(QStyledItemDelegate):
    """Use stable insets for the inline details widget within a spanned row."""

    horizontal_inset = 8
    vertical_inset = 4

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(
            self.horizontal_inset, self.vertical_inset, -self.horizontal_inset, -self.vertical_inset,
        ))


class LiveSettingsDialog(SettingsDialog):
    """Compatibility dialog using the same settings content as the page."""

    def __init__(self, settings, parent=None):
        super().__init__(AppSettings(live=settings), parent)
        # This compatibility editor returns only LiveSettings to its caller.
        self.tabs.setTabVisible(4, False)
        self.tabs.setCurrentIndex(1)

    def settings(self):
        return self.get_settings().live


class LivePage(QWidget):
    settings_changed = Signal(object)
    settings_requested = Signal(str)
    history_requested = Signal()

    def __init__(self, config, confirm_copyright, parent=None, controller=None, *, discovery_pool=None, thumbnails=None):
        super().__init__(parent)
        self._config = config
        self._confirm_copyright = confirm_copyright
        self._own_controller = controller is None
        self._has_following = discovery_pool is not None
        self.following = None
        self.controller = controller or LiveUiController(config, self)
        self._selected_id = None
        self._rows = []
        self._quality_fingerprint = None
        self._inline_row = None
        self._pending_inline_reveal = False
        self._inline_reveal_timer = QTimer(self)
        self._inline_reveal_timer.setSingleShot(True)
        self._inline_reveal_timer.setInterval(16)
        self._inline_reveal_timer.timeout.connect(self._reveal_inline_actions)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        header = PageHeader("直播录制", "记录喜欢的直播")
        self.header = header
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
        column.setContentsMargins(0, 0, 4, 12)
        column.setSpacing(16)
        hero = HeroPanel()
        hero.set_compact(True, minimum_height=UI_METRICS.source_resolved_height)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(10)
        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        self.source = ChineseLineEdit()
        self.source.setAccessibleName("直播间来源")
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
        self.add_button.setToolTip("BiliFlow 运行时，监控的房间开播即自动录制")
        self.add_button.setAccessibleDescription(self.add_button.toolTip())
        self.add_button.clicked.connect(self._add)
        input_row.addWidget(self.add_button)
        hero_layout.addLayout(input_row)
        column.addWidget(hero)
        self.engine_notice = Notice()
        column.addWidget(self.engine_notice)
        self._content = QWidget()
        self._content_layout = QBoxLayout(QBoxLayout.LeftToRight, self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
        self._rooms_card = SectionCard()
        self._rooms_card.set_plain()
        self._count = StatusBadge("0 个直播间")
        self._rooms_card.body.addWidget(self._count, alignment=Qt.AlignRight)
        self.rooms = QTableWidget(0, 4)
        self._rooms_surface = ItemViewSurface(self.rooms)
        self.rooms.setAccessibleName("直播监控列表")
        self.rooms.setHorizontalHeaderLabels(
            ["直播间", "状态 / 监控", "已录时长", "大小 / 速度"]
        )
        self.rooms.setColumnHidden(3, True)
        self.rooms.setSelectionBehavior(QTableWidget.SelectRows)
        self.rooms.setSelectionMode(QTableWidget.SingleSelection)
        self.rooms.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rooms.verticalHeader().hide()
        self.rooms.verticalHeader().setDefaultSectionSize(UI_METRICS.row_height)
        table_header = self.rooms.horizontalHeader()
        table_header.setMinimumSectionSize(40)
        table_header.setSectionResizeMode(0, QHeaderView.Stretch)
        for index, width in ((1, 142), (2, 110), (3, 120)):
            table_header.setSectionResizeMode(index, QHeaderView.Fixed)
            table_header.resizeSection(index, width)
        self.rooms.setItemDelegateForColumn(0, _RoomDelegate(self.rooms))
        self.rooms.setItemDelegateForColumn(1, _StatusDelegate(self.rooms))
        self.rooms.itemSelectionChanged.connect(self._selection_changed)
        self.rooms.itemClicked.connect(self._expand_selected_room)
        self._room_stack = QStackedWidget()
        self._room_stack.addWidget(self.rooms)
        self._room_stack.addWidget(
            EmptyState("暂无直播间", action="添加房间", callback=self.source.setFocus, workspace="live")
        )
        if self._has_following:
            empty = QLabel("暂无监控的直播间")
            empty.setObjectName("MetaLabel")
            self._room_stack.addWidget(empty)
        self._room_stack.setMinimumHeight(240)
        self._rooms_card.body.addWidget(self._room_stack, 1)
        self._content_layout.addWidget(self._rooms_card, 1)
        self._detail_card = SectionCard("房间详情")
        self._detail_card.setProperty("readingOutline", False)
        self._detail_card.installEventFilter(self)
        self._detail_card.setMinimumWidth(300)
        self._detail_badge = StatusBadge("未选择房间")
        self._detail_card.header.addWidget(self._detail_badge)
        self._detail_toggle = QPushButton("展开")
        self._detail_toggle.setObjectName("TextButton")
        self._detail_toggle.setCheckable(True)
        self._detail_toggle.setAccessibleName("展开或收起房间详情")
        self._detail_toggle.toggled.connect(self._sync_detail_visibility)
        self._detail_card.header.addWidget(self._detail_toggle)
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
        self._recording_metrics = QLabel()
        self._recording_metrics.setObjectName("RecordingSummary")
        self._recording_metrics.setTextFormat(Qt.PlainText)
        details.addWidget(self._recording_metrics)
        self._detail = QLabel()
        self._detail.setTextFormat(Qt.PlainText)
        self._detail.setWordWrap(True)
        details.addWidget(self._detail)
        self._room_configuration = CollapsibleSection("录制偏好")
        self._room_configuration.set_plain()
        self._room_configuration.body.setContentsMargins(0, 8, 0, 8)
        options = self._room_configuration.body
        self.quality = ComboBox()
        self.quality.activated.connect(self._set_quality)
        options.addWidget(FieldRow("下次拉流画质", self.quality))
        self._directory = ReadOnlyPath(show_end=True)
        self._directory.setAccessibleName("当前房间保存目录")
        self._directory.setSizePolicy(self.source.sizePolicy())
        directory_row = QWidget()
        directory_layout = QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.addWidget(self._directory, 1)
        self._open_directory = QPushButton("打开")
        self._open_directory.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(Path(self._directory.text()).expanduser()))
        ) if Path(self._directory.text()).expanduser().is_dir() else self.controller.notify("保存目录未创建或不可用。", "warning"))
        directory_layout.addWidget(self._open_directory)
        details.addWidget(FieldRow("保存目录", directory_row))
        details.addWidget(self._room_configuration)
        self._directory_hint = QLabel()
        self._directory_hint.setObjectName("MetaLabel")
        self._directory_hint.setWordWrap(True)
        self._directory_hint.setTextFormat(Qt.PlainText)
        options.addWidget(self._directory_hint)
        self._segment = QLabel()
        self._segment.setObjectName("MetaLabel")
        options.addWidget(self._segment)
        self.monitor = CheckBox("自动监控并录制")
        self.monitor.setToolTip("关闭监控将停止本场；开启后等待下次开播")
        self.monitor.setAccessibleDescription(self.monitor.toolTip())
        self.monitor.toggled.connect(self._toggle_monitor)
        self._monitor_hint = QLabel("关闭监控会停止本场录制。")
        self._monitor_hint.setObjectName("MetaLabel")
        self._monitor_hint.setWordWrap(True)
        options.addWidget(self._monitor_hint)
        buttons = ResponsiveActions()
        self.start_stop = ActionButton("立即开始")
        self.start_stop.setProperty("alwaysVisible", True)
        self.start_stop.setObjectName("PrimaryButton")
        self.start_stop.clicked.connect(self._start_stop)
        self.room_settings = ActionButton("房间设置")
        self.room_settings.setObjectName("OutputSecondaryButton")
        self.room_settings.clicked.connect(self._room_settings)
        buttons.row.addWidget(self.room_settings)
        more = QPushButton("更多")
        more.setObjectName("OutputSecondaryButton")
        more.setProperty("menuButton", True)
        menu = PopupMenu(more)
        self.remove_action = menu.addAction("移除直播间")
        self.remove_action.triggered.connect(lambda: self._command("remove"))
        more.setMenu(menu)
        buttons.row.addWidget(more)
        self.start_stop.setMinimumWidth(108)
        buttons.row.addWidget(self.start_stop)
        self._action_bar = QWidget()
        self._action_bar.installEventFilter(self)
        self._action_bar.setAccessibleName("直播间录制操作")
        action_bar = QVBoxLayout(self._action_bar)
        action_bar.setContentsMargins(0, 4, 0, 0)
        action_bar.setSpacing(8)
        action_bar.addWidget(self.monitor)
        action_bar.addWidget(buttons, alignment=Qt.AlignRight)
        details.addWidget(self._action_bar)
        self._detail_card.body.addWidget(self._detail_controls)
        self._detail_card.body.addStretch()
        self._content_layout.addWidget(self._detail_card)
        if self._has_following:
            from bilibili_downloader.gui.widgets.live_following import (
                LiveFollowingWidget,
            )

            self.following = LiveFollowingWidget(self.controller, discovery_pool, thumbnails)
            self.following.view_room.connect(self._view_followed_room)
            self.following.shortcut_requested.connect(self._followed_room_shortcut)
            self.following.rooms_changed.connect(self._sync_room_stack)
        column.addWidget(self._content, 0 if self.following else 1)
        if self.following:
            column.addWidget(self.following)
            column.addStretch()
        self._scroll = scroll_area(body, scroll_edge=True)
        if self.following:
            self.following.grid.set_scroll_area(self._scroll)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._schedule_inline_reveal)
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll, 1)
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
        # Both panes include their own padding; the 900px shell stays stacked.
        narrow = event.size().width() < 880
        self._stacked_details = narrow
        self._content_layout.setDirection(
            QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        )
        self._detail_card.setMaximumWidth(16777215 if narrow else 320)
        self._detail_toggle.setVisible(narrow)
        self._room_stack.setMinimumHeight(160 if narrow else 200)
        duration_width = max(80, self.rooms.fontMetrics().horizontalAdvance("000:00:00") + 24)
        for index, width in ((1, 108), (2, duration_width), (3, 92)):
            self.rooms.horizontalHeader().resizeSection(index, width)
        self._sync_detail_visibility()
        self._update_table_height()
        super().resizeEvent(event)

    def _sync_detail_visibility(self, *_args):
        stacked = getattr(self, "_stacked_details", True)
        expanded = not stacked or self._detail_toggle.isChecked()
        selected = self._selected_row() is not None
        index = self.rooms.currentRow()
        if self._inline_row is not None and index > self._inline_row:
            index -= 1
        inline = stacked and expanded and selected
        moved = self._inline_row != (index + 1 if inline else None)
        self._place_inline_detail(index + 1 if inline else None)
        self._detail_badge.setVisible(not inline)
        self._room_name.setVisible(not inline)
        self._room_id_label.setVisible(not inline)
        self._detail_card.setVisible(selected)
        self._detail_controls.setVisible(expanded and selected)
        self._detail_toggle.setText("收起" if expanded else "展开")
        if moved:
            self._pending_inline_reveal = inline
        self._update_table_height()
        self._schedule_inline_reveal()

    def _schedule_inline_reveal(self, *_args):
        if self._pending_inline_reveal:
            self._inline_reveal_timer.start()

    def _reveal_inline_actions(self):
        if self._pending_inline_reveal and self._inline_row is not None:
            viewport = self._scroll.viewport()
            scroll = self._scroll.verticalScrollBar()
            top = self._action_bar.mapTo(viewport, QPoint()).y()
            bottom = top + self._action_bar.height()
            previous = scroll.value()
            # Scroll the whole action bar into view; Qt may reveal only its focus target.
            if bottom + 8 > viewport.height():
                scroll.setValue(previous + bottom + 8 - viewport.height())
            elif top < 8:
                scroll.setValue(previous + top - 8)
            if scroll.value() != previous:
                # Scrolling can trigger another geometry pass for the spanned table row.
                self._schedule_inline_reveal()
            else:
                visible = self._action_bar.visibleRegion().boundingRect()
                self._pending_inline_reveal = not visible.contains(self._action_bar.rect())

    def _place_inline_detail(self, index):
        if index == self._inline_row:
            return
        blocked = self.rooms.blockSignals(True)
        if self._inline_row is not None:
            self._detail_card.setParent(self._content)
            self.rooms.removeRow(self._inline_row)
        self._inline_row = index
        if index is None:
            self._content_layout.addWidget(self._detail_card)
        else:
            self.rooms.insertRow(index)
            for column in range(self.rooms.columnCount()):
                item = QTableWidgetItem()
                item.setFlags(Qt.NoItemFlags)
                self.rooms.setItem(index, column, item)
            self.rooms.setSpan(index, 0, 1, self.rooms.columnCount())
            host = QWidget()
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._detail_card)
            self.rooms.setCellWidget(index, 0, host)
        self.rooms.blockSignals(blocked)

    def _expand_selected_room(self, _item):
        self._detail_toggle.setChecked(True)

    def eventFilter(self, watched, event):
        if self._inline_row is not None:
            kind = event.type()
            if watched is self._detail_card and kind == QEvent.LayoutRequest:
                self._update_table_height()
                self._schedule_inline_reveal()
            elif watched is self._action_bar and kind in (QEvent.Move, QEvent.Resize):
                self._schedule_inline_reveal()
            elif watched is self._scroll.viewport() and kind == QEvent.Resize:
                self._schedule_inline_reveal()
        return super().eventFilter(watched, event)

    def _update_table_height(self):
        if self._inline_row is not None:
            card = self._detail_card
            padding = card.frameWidth() * 2
            width = max(1, self.rooms.viewport().width() - _RoomDelegate.horizontal_inset * 2 - padding)
            hint = max(card.sizeHint().height(), card.body.totalHeightForWidth(width) + padding)
            self.rooms.setRowHeight(self._inline_row, hint + _RoomDelegate.vertical_inset * 2)
        stacked = getattr(self, "_stacked_details", True)
        self.rooms.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if stacked else Qt.ScrollBarAsNeeded
        )
        chrome = max(40, self.rooms.horizontalHeader().height()) + self.rooms.frameWidth() * 2
        if self.rooms.isVisible() and self.rooms.viewport().height() > 0:
            chrome = max(chrome, self.rooms.height() - self.rooms.viewport().height())
        height = chrome + sum(self.rooms.rowHeight(i) for i in range(self.rooms.rowCount()))
        # Stacked content scrolls as one page; never nest the room table's scroll.
        self.rooms.setMinimumHeight(max(140, height) if stacked else 140)
        compact_empty = self._compact_empty_room_list()
        self._room_stack.setMaximumHeight(40 if compact_empty else 16777215)
        self._room_stack.setMinimumHeight(
            32 if compact_empty else max(160, height) if stacked and self.rooms.rowCount() else 200
        )
        if stacked:
            self.rooms.verticalScrollBar().setValue(0)

    def _compact_empty_room_list(self):
        return not self._rows and self.following is not None and self.following.has_rooms

    def _sync_room_stack(self):
        compact_empty = self._compact_empty_room_list()
        self._room_stack.setCurrentIndex(0 if self._rows else 2 if compact_empty else 1)
        self._count.setVisible(not compact_empty)
        self._update_table_height()

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

    def _view_followed_room(self, room_id):
        self.select_room(room_id)
        if not getattr(self, "_stacked_details", False):
            self._scroll.ensureWidgetVisible(self.rooms, 0, 12)

    def _followed_room_shortcut(self, room_id, intent):
        if self.service and not self.controller.shortcut_pending(room_id) and self._confirm_copyright():
            self.controller.quick_room(room_id, intent)

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
        self._sync_detail_visibility()
        if not row:
            self._detail_badge.setText("未选择房间")
            self._detail_badge.set_tone("muted")
            self._quality_fingerprint = None
            return
        self._room_name.setText(row["author"] or "未命名直播间")
        self._action_bar.setAccessibleName(f"{row['author'] or row['room_id']}的录制操作")
        self._room_id_label.setText(f"房间 {row['room_id']} · {row['title']}")
        self._room_id_label.setWordWrap(True)
        self._room_id_label.setTextFormat(Qt.PlainText)
        self._detail_badge.setText(row["state_label"])
        self._detail_badge.set_tone(live_tone(row["state"]))
        self._detail.setText(row["detail"] or "等待直播状态更新")
        self._detail.setVisible(bool(row["detail"] and row["detail"] != row["state_label"]))
        self._recording_metrics.setText(f"{_size(row['size'])} · {_size(row['speed'])}/s")
        self._recording_metrics.setVisible(bool(row['size'] or row['speed']))
        actual = row.get("active_output_dir") or row["output_dir"]
        self._directory.set_full_text(actual)
        mode = {"default": "跟随全局", "custom": "独立目录", None: "旧目录待核对"}.get(row.get("output_dir_mode"), "独立目录")
        self._directory_hint.setText(
            f"{mode} · 下一场将使用新目录" if row.get("active_output_dir")
            else f"{mode} · 按主播和场次建立子目录"
        )
        self._directory_hint.setToolTip(f"下一场保存位置：{row['output_dir']}")
        self._segment.setText(
            f"分段时长 {row['segment_seconds'] // 60} 分钟 · 画质修改在下次拉流生效"
        )
        self._segment.setWordWrap(True)
        fingerprint = (row["room_id"], row["quality"], row["qualities"])
        if fingerprint != self._quality_fingerprint:
            self._quality_fingerprint = fingerprint
            self.quality.clear()
            self.quality.addItem("当前最高可用画质", 0)
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
        self._monitor_hint.setVisible(active and row["enabled"] and not finalizing)
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
        for button in (self.start_stop, self.room_settings, self.monitor):
            button.setAccessibleName(f"{button.text()} · {row['author']} · 房间 {row['room_id']}")

    def _set_quality(self):
        if self._room_id():
            self.controller.command(
                "quality", room_id=self._room_id(), quality=self.quality.currentData()
            )

    def _settings(self):
        if not self._own_controller:
            self.settings_requested.emit("live")
            return
        dialog = LiveSettingsDialog(self._config.load().live, self)
        dialog.set_live_rooms(self.controller.rows)
        if dialog.exec():
            settings = self._config.load().model_copy(deep=True)
            settings.live = dialog.settings()
            try:
                self._config.save(settings)
            except OSError as exc:
                self.controller.notify(str(exc), "danger")
                return
            self.settings_changed.emit(settings)
            self.controller.apply_live_settings(settings.live, dialog.directory_modes())
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
                output_dir_mode=dialog.directory_mode.currentData(),
                segment_seconds=(
                    row["segment_seconds"]
                    if dialog.segment.value() == row["segment_seconds"] // 60
                    else dialog.segment.value() * 60
                ),
            )

    def _build_room_settings_dialog(self, row):
        dialog = WorkflowDialog(f"直播间 {row['room_id']} 设置", "目录与分段设置仅用于此房间。", self, confirm="保存", width=640)
        dialog.resize(640, 500)
        card = SectionCard("录制偏好")
        mode = ComboBox()
        mode.addItem("跟随全局保存目录", "default")
        mode.addItem("独立保存目录", "custom")
        mode.setCurrentIndex(0 if row.get("output_dir_mode") == "default" else 1)
        dialog.directory_mode = mode
        card.body.addWidget(FieldRow("目录规则", mode))
        directory = QLineEdit(row["output_dir"])
        draft_directory = {"custom": row["output_dir"]}
        directory.textEdited.connect(lambda value: draft_directory.update(custom=value))
        directory.setToolTip(row["output_dir"])
        directory.setCursorPosition(0)
        dialog.directory = directory
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(directory, 1)
        browse = QPushButton("选择…")

        def select_directory():
            from bilibili_downloader.gui.dialogs.file_picker import file_picker

            def selected(value):
                directory.setText(value)
                directory.setToolTip(value)
                draft_directory["custom"] = value
            file_picker(dialog).directory("选择录制目录", directory.text(), selected)

        browse.clicked.connect(select_directory)
        path_layout.addWidget(browse)
        def sync_directory():
            follows = mode.currentData() == "default"
            directory.setEnabled(not follows)
            browse.setEnabled(not follows)
            directory.setText(self._config.load().live.output_dir if follows else draft_directory["custom"])
            directory.setToolTip(directory.text())
        mode.currentIndexChanged.connect(sync_directory)
        sync_directory()
        directory_field = FieldRow("保存目录", path_row)
        card.body.addWidget(directory_field)
        segment = QSpinBox()
        dialog.segment = segment
        segment.setRange(1, 1440)
        segment.setValue(row["segment_seconds"] // 60)
        segment.setSuffix(" 分钟")
        segment_row, _, _ = stepper(segment)
        card.body.addWidget(FieldRow("分段时长", segment_row))
        card.body.addWidget(Notice("跟随全局时下次录制用全局目录；独立目录仅用于此房间。录制或收尾时无法保存。"))
        dialog.body.addWidget(card)
        dialog.body.addStretch()
        notice = dialog.notice

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
                notice.set_message("请先停止本场，等待收尾完成。", "warning")
                return
            if not directory.text().strip() or Path(directory.text().strip()).expanduser().is_file():
                notice.set_message("请选择有效的录制目录。", "danger")
                directory_field.set_error("请选择有效的录制目录。")
                directory.setFocus()
                return
            dialog.accept()

        dialog.confirm_button.clicked.disconnect()
        dialog.confirm_button.clicked.connect(save)
        return dialog

    def _update_rows(self, rows):
        selected = self._room_id()
        scroll = self.rooms.verticalScrollBar().value()
        self._rows = rows
        self.rooms.blockSignals(True)
        if self._inline_row is not None and (
            self._inline_row > len(rows) or rows[self._inline_row - 1]["room_id"] != selected
        ):
            self._place_inline_detail(None)
        self.rooms.setRowCount(len(rows) + int(self._inline_row is not None))
        for position, row in enumerate(rows):
            index = position + int(self._inline_row is not None and position >= self._inline_row)
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
                if column == 2:
                    item.setTextAlignment(Qt.AlignCenter)
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
        if not getattr(self, "_stacked_details", True):
            self.rooms.verticalScrollBar().setValue(scroll)
        self._sync_room_stack()
        self._count.setText(f"{len(rows)} 个直播间")
        self._selection_changed()

    def select_room(self, room_id):
        for index in range(self.rooms.rowCount()):
            item = self.rooms.item(index, 0)
            if item is not None and item.data(Qt.UserRole) == room_id:
                self.rooms.selectRow(index)
                self.rooms.scrollToItem(item)
                self._detail_toggle.setChecked(True)
                if getattr(self, "_stacked_details", False):
                    self._pending_inline_reveal = True
                    self._schedule_inline_reveal()
                break

    def refresh(self):
        self.controller.refresh()

    def shutdown(self):
        self.controller.shutdown()
