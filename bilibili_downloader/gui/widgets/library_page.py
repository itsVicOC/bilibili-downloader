"""Local downloads with explicit selection, concise feedback and recoverable actions."""

import sqlite3
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QRunnable,
    QSignalBlocker,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.library import FILE_STATES
from bilibili_downloader.gui.dialogs.file_picker import file_picker
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    ActionButton,
    CommandBar,
    EmptyState,
    Notice,
    PopupMenu,
    TaskDetailPanel,
)
from bilibili_downloader.gui.widgets.file_table import (
    DIRECTORY_COLUMN,
    SIZE_COLUMN,
    STATE_COLUMN,
    FileTable,
)
from bilibili_downloader.gui.widgets.glass_surface import ItemViewSurface
from bilibili_downloader.gui.widgets.library_records import LibraryRecord, normalize
from bilibili_downloader.gui.widgets.library_records import file_size as _size
from bilibili_downloader.gui.widgets.library_records import media_state as _media_state
from bilibili_downloader.gui.widgets.library_thumbnails import (
    LibraryThumbnails,
    ThumbnailFile,
    ThumbnailSource,
)
from bilibili_downloader.gui.widgets.library_views import (
    FileLabelDelegate,
    LibraryGrid,
    handle_browse_key,
)
from bilibili_downloader.gui.widgets.selection import SelectionBar, TableSelection


class OperationDialog(WorkflowDialog):
    """Summaries and optional detailed lists use the same workflow surface."""

    def __init__(self, title, summary, details, parent=None, *, confirm=""):
        super().__init__(title, parent=parent, confirm=confirm or "关闭")
        self.summary = QLabel(summary)
        self.summary.setTextFormat(Qt.PlainText)
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)
        self.reader = QPlainTextEdit(details)
        self.reader.setReadOnly(True)
        self.reader.setAccessibleName("文件清单及处理详情")
        self.reader.setMinimumHeight(180)
        if confirm:
            toggle = QPushButton("查看文件清单")
            toggle.setObjectName("TextButton")
            toggle.setCheckable(True)
            self.reader.hide()
            toggle.toggled.connect(self.reader.setVisible)
            self.body.addWidget(toggle, alignment=Qt.AlignLeft)
            self.cancel_button.setDefault(True)
            if "回收" in confirm:
                self.confirm_button.setObjectName("DangerButton")
        else:
            self.cancel_button.hide()
        self.body.addWidget(self.reader)
        self.resize(640, 360 if confirm else 480)


class _JobSignals(QObject):
    finished = Signal(object)
    progress = Signal(int, int)


class _LibraryJob(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.signals = _JobSignals()
        self.action = action

    def run(self):
        last_progress = 0.0
        def progress(done, total):
            nonlocal last_progress
            now = time.monotonic()
            if done == total or now - last_progress >= 0.05:
                self.signals.progress.emit(done, total)
                last_progress = now
        try:
            result = self.action(progress)
        except Exception as exc:  # noqa: BLE001
            result = exc
        self.signals.finished.emit(result)


class LibraryPage(QWidget):
    download_requested = Signal()
    reuse_requested = Signal(object)
    preferences_changed = Signal(str, str)

    def __init__(self, parent=None, *, pool=None, view_mode="grid", sort_mode="recent"):
        super().__init__(parent)
        self.repository = None
        self.record_provider = lambda: []
        self._pool = pool or QThreadPool.globalInstance()
        self._jobs = set()
        self._read_jobs = set()
        self._read_generation = 0
        self._cancel = threading.Event()
        self._assets = []
        self._records = {}
        self._ordered = []
        self._table_rows = {}
        self._table_visible = set()
        self._table_needs_refresh = True
        self._updating_view = False
        self._positions = {}
        self.view_mode, self.sort_mode = view_mode, sort_mode
        self._removed_ids = []
        self._load_error = False
        self._details = ""
        self._notice_callback = None
        self._detail_asset = None
        self._job_kind = ""
        self.ffmpeg_path = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_async)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tools = CommandBar()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文件、作品、作者或编号")
        self.search.setToolTip("支持分 P、合集、番剧、BV/AV/EP 号和完整路径，可用空格分隔关键词")
        self.search.setAccessibleName("搜索下载文件")
        self.search.setMinimumWidth(160)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.tools.filters.addWidget(self.search)
        self.type_filter = ComboBox()
        for label, key in (("全部类型", "all"), ("视频", "video"), ("仅音频", "audio")):
            self.type_filter.addItem(label, key)
        self.type_filter.setFixedWidth(112)
        self.type_filter.currentIndexChanged.connect(self._filter)
        self.tools.filters.addWidget(self.type_filter)
        self.state_filter = ComboBox()
        self.state_filter.addItem("全部状态", "all")
        for key, label in FILE_STATES.items():
            self.state_filter.addItem(label, key)
        self.state_filter.setFixedWidth(112)
        self.state_filter.currentIndexChanged.connect(self._filter)
        self.tools.filters.addWidget(self.state_filter)
        self.sort = ComboBox()
        self.sort.setAccessibleName("下载文件排序")
        for key, label in (("recent", "最近下载"), ("title", "标题"), ("size", "文件大小")):
            self.sort.addItem(label, key)
        self.sort.setCurrentIndex(self.sort.findData(self.sort_mode))
        self.sort.setMinimumWidth(112)
        self.tools.filters.addWidget(self.sort)
        view_switcher = QWidget()
        view_layout = QHBoxLayout(view_switcher)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(2)
        view_group = QButtonGroup(view_switcher)
        self.view_buttons = {}
        for mode, label in (("grid", "网格"), ("list", "列表")):
            button = QPushButton(label)
            button.setObjectName("SegmentButton")
            button.setAccessibleName(f"下载文件 · {label}")
            button.setCheckable(True)
            button.setChecked(mode == self.view_mode)
            button.clicked.connect(lambda checked, mode=mode: self.set_view_mode(mode) if checked else None)
            view_group.addButton(button)
            view_layout.addWidget(button)
            self.view_buttons[mode] = button
        self.tools.filters.addWidget(view_switcher)
        self.open_action = ActionButton("打开文件")
        self.folder_action = ActionButton("打开文件夹")
        self.check_button = ActionButton("检查文件")
        self.check_button.setProperty("alwaysVisible", True)
        for button, callback in (
            (self.open_action, lambda: self.open_file(False)),
            (self.folder_action, lambda: self.open_file(True)),
            (self.check_button, self.check),
        ):
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(callback)
            self.tools.actions.addWidget(button)
        self.open_action.hide()
        self.folder_action.hide()
        self.cancel_button = ActionButton("取消检查")
        self.cancel_button.setProperty("alwaysVisible", True)
        self.cancel_button.clicked.connect(self._request_cancel)
        self.cancel_button.hide()
        self.tools.actions.addWidget(self.cancel_button)
        more = QPushButton("更多")
        more.setObjectName("TableSubtleButton")
        menu = PopupMenu(more)
        self.select_action = menu.addAction("全选当前列表", self.select_visible)
        self.deselect_action = menu.addAction("取消选择", self._clear_selection)
        menu.addSeparator()
        self.copy_action = menu.addAction("复制路径", self.copy_path)
        self.locate_action = menu.addAction("重新选择文件…", self.relocate)
        self.relocate_directory_action = menu.addAction("重新定位整个目录…", self.relocate_directory)
        self.verify_action = menu.addAction("核验媒体轨道与时长", self.verify)
        self.supplement_action = menu.addAction("补全附件…", self.request_supplement)
        self.copy_media_action = menu.addAction("另存一份媒体", lambda: self.request_supplement(force_new=True))
        menu.addSeparator()
        self.hide_action = menu.addAction("移除记录", self.hide_selected)
        self.hide_action.setToolTip("保留本地文件，可撤销")
        self.undo_action = menu.addAction("撤销移除记录", self.undo_hide)
        self.recycle_action = menu.addAction("移入回收站…", self.recycle_selected)
        menu.addSeparator()
        self.recover_action = menu.addAction("恢复文件记录", self.replay)
        self.details_action = menu.addAction("上次处理详情", self.show_details)
        more.setMenu(menu)
        self.tools.actions.addWidget(more)
        layout.addWidget(self.tools)
        toolbar_status = QWidget()
        status_layout = QVBoxLayout(toolbar_status)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.selection_bar = SelectionBar(contextual=True)
        status_layout.addWidget(self.selection_bar)
        self.count_label = QLabel()
        self.count_label.setObjectName("MetaLabel")
        status_layout.addWidget(self.count_label)
        self.tools.set_status(toolbar_status)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MetaLabel")
        self.progress_label.setWordWrap(True)
        self.count_label.hide()
        self.progress_label.hide()
        layout.addWidget(self.progress_label, alignment=Qt.AlignRight)
        self._thumbnails = LibraryThumbnails(self)
        self._thumbnails.changed.connect(self._thumbnail_changed)
        self._painted_records = set()
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setSingleShot(True)
        self._thumbnail_timer.timeout.connect(self._load_visible_thumbnails)
        self.table = FileTable()
        self.table.setAccessibleName("下载文件列表")
        self.table.setHorizontalHeaderLabels(["作品", "规格", "大小", "状态", "所在目录"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 128), (STATE_COLUMN, 100), (DIRECTORY_COLUMN, 190)):
            self.table.setColumnWidth(column, width)
        self.table.verticalHeader().hide()
        self._resize_columns()
        for column in (1, STATE_COLUMN, DIRECTORY_COLUMN):
            self.table.setItemDelegateForColumn(column, FileLabelDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.selection = TableSelection(
            self.table, FileLabelDelegate(self.table, self._thumbnail_for), paint_only=True, distinguish_focus=True,
        )
        self.selection.changed.connect(self._checked_changed)
        self.selection.focus_changed.connect(self._table_focus_changed)
        self.selection_bar.select_visible.connect(self.select_visible)
        self.selection_bar.clear_requested.connect(self._clear_selection)
        self.selection_bar.review_requested.connect(self._toggle_selection_review)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_file(False))
        self.table.select_all_requested.connect(self.select_visible)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.grid = LibraryGrid(self.selection, self._thumbnail_for)
        self._views = {"grid": self.grid, "list": self.table}
        self.browser = QStackedWidget()
        for view in self._views.values():
            view.installEventFilter(self)
            view.viewport().installEventFilter(self)
            view.verticalScrollBar().valueChanged.connect(self._load_visible_thumbnails)
            self.browser.addWidget(view)
        self.grid.selectionModel().currentChanged.connect(self._browse_focus_changed)
        self.grid.doubleClicked.connect(self._browse_open)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(lambda point: self._context_menu(point, self.grid))
        self.browser.setCurrentWidget(self._views[self.view_mode])
        self.stack = QStackedWidget()
        # Empty-state hints must not prevent the file table from shrinking when
        # the attachment panel is expanded in a compact window.
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.stack.setMinimumHeight(60)
        self.stack.addWidget(self.browser)
        self.stack.addWidget(
            EmptyState(
                "暂无文件记录", action="去下载", callback=self.download_requested.emit, scene="files_empty",
            )
        )
        self.stack.addWidget(
            EmptyState(
                "没有匹配的文件", action="清除筛选", callback=self.clear_filters, scene="files_filtered",
            )
        )
        self.stack.addWidget(EmptyState("正在加载文件记录", scene="files_loading"))
        self.stack.addWidget(
            EmptyState(
                "文件列表暂不可用", "本地文件仍保留，请重试加载。", "重试", self.replay, scene="files_error",
            )
        )
        self.stack.setCurrentIndex(3)
        layout.addWidget(self.stack, 1)
        self.detail = TaskDetailPanel()
        self.detail_title = self.detail.title
        self.detail_path = self.detail.path
        self.detail_hint = self.detail.diagnostics
        self.detail_relocate = self.detail.primary_action
        self.attachments_toggle = QPushButton()
        self.attachments_toggle.setObjectName("TextButton")
        self.attachments_toggle.setCheckable(True)
        self.attachments_toggle.toggled.connect(lambda expanded: self.files.setVisible(expanded and self.files.topLevelItemCount() > 0))
        self.detail.result_row.layout().insertWidget(3, self.attachments_toggle)
        self.files = QTreeWidget()
        self._files_surface = ItemViewSurface(self.files)
        self.files.setAccessibleName("附加文件列表")
        self.files.setHeaderLabels(["附件", "状态", "大小"])
        self.files.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.setMaximumHeight(120)
        self.files.setRootIsDecorated(False)
        self.files.setUniformRowHeights(True)
        self.files.itemDoubleClicked.connect(lambda item, _: self.open_file(False, entry=item.data(0, Qt.UserRole)))
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._attachment_menu)
        self.files.hide()
        self.detail.body.addWidget(self.files)
        self.detail.hide()
        layout.addWidget(self.detail)
        self.notice = Notice(callback=self._activate_notice)
        layout.addWidget(self.notice)
        self.sort.currentIndexChanged.connect(self._sort_changed)
        self._actions()

    def _feedback(self, text, tone="info", *, action="", callback=None, details=""):
        self._details = details
        if details:
            if not callback:
                action, callback = "查看详情", self.show_details
        self._notice_callback = callback
        self.notice.action.setText(action)
        self.notice.action.setVisible(bool(action and callback))
        self.notice.set_message(text, tone)
        self.details_action.setVisible(bool(self._details))
        self.details_action.setEnabled(bool(self._details))

    def _activate_notice(self):
        if self._notice_callback:
            self._notice_callback()

    def show_details(self):
        OperationDialog(
            "处理详情", "查看完整路径与逐项原因。", self._details, self
        ).exec()

    def set_repository(self, repository):
        self.repository = repository
        self._read_generation += 1
        if repository is None:
            self.stack.setCurrentIndex(3)
            self.detail.hide()
            self._actions()
        else:
            self.refresh_async()

    def schedule_refresh(self):
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(120)

    def refresh_async(self):
        if self.repository is None:
            return
        self._read_generation += 1
        generation, repository = self._read_generation, self.repository
        job = _LibraryJob(lambda _: repository.list_assets())
        self._read_jobs.add(job)
        def finished(result):
            self._read_jobs.discard(job)
            from shiboken6 import isValid
            if not isValid(self) or not isValid(self.table):
                return
            if generation != self._read_generation or self.repository is not repository:
                return
            if isinstance(result, Exception):
                self._load_error = True
                self.stack.setCurrentIndex(4)
                self._feedback("文件列表暂不可用，请重试。", "danger", details=str(result))
                self._actions()
            else:
                self.refresh(assets=result)
        job.signals.finished.connect(finished)
        self._pool.start(job)

    def refresh(self, *, assets=None):
        refresh_started = time.perf_counter()
        self._read_generation += 1
        if self.repository is None:
            self.stack.setCurrentIndex(3)
            self._actions()
            return
        position = self._view_position()
        try:
            assets = self.repository.list_assets() if assets is None else assets
        except (OSError, ValueError, sqlite3.Error) as exc:
            self._load_error = True
            self.stack.setCurrentIndex(4)
            self.detail.hide()
            self._feedback("文件列表暂不可用，请重试。", "danger", details=str(exc))
            self._actions()
            return
        self._load_error = False
        self._assets = assets
        self._records = {asset["id"]: LibraryRecord(asset) for asset in assets}
        self._sort_records()
        self._filter(position=position)
        self._resize_columns()
        self._last_refresh_ms = (time.perf_counter() - refresh_started) * 1000

    def _apply_file_updates(self, updates):
        """Update file facts while retaining the loaded records and session selection."""
        started = time.perf_counter()
        self._read_generation += 1
        entries = {entry["id"]: (asset["id"], entry) for asset in self._assets for entry in asset["files"]}
        model = self.table.model()
        changed_rows = []
        size_changed = False
        for update in updates:
            current = entries.get(update["id"])
            if current is None or current[1]["path"] != update["path"]:
                continue
            asset_id, entry = current
            size_changed |= entry["kind"] == "media" and entry["size"] != update["size"]
            entry.update(update)
            if entry["kind"] != "media" or self._table_needs_refresh:
                continue
            record = self._records[asset_id]
            row = self._table_rows[asset_id]
            for column, value in ((SIZE_COLUMN, _size(record.size)), (STATE_COLUMN, record.state)):
                if model.rows[row][column] != value:
                    model.rows[row][column] = value
                    changed_rows.append(row)
        if changed_rows:
            model.dataChanged.emit(model.index(min(changed_rows), SIZE_COLUMN), model.index(max(changed_rows), STATE_COLUMN),
                                   [Qt.DisplayRole, Qt.ToolTipRole])
        resort = size_changed and self.sort_mode == "size"
        if resort:
            self._sort_records()
        if resort or self.view_mode != "list" or self.state_filter.currentData() != "all":
            self._filter(position=self._view_position())
        else:
            self._reset_thumbnails()
            self.table.viewport().update()
            self._selection()
        self._last_refresh_ms = (time.perf_counter() - started) * 1000

    def _sort_records(self):
        self._ordered = sorted(self._records.values(), key=lambda record: record.order_key(self.sort_mode))
        self.selection.reset([record.id for record in self._ordered])
        self._table_needs_refresh = True

    def _sort_changed(self):
        self.sort_mode = self.sort.currentData()
        self._sort_records()
        self._filter(reveal=True)
        self.preferences_changed.emit(self.view_mode, self.sort_mode)

    def _view_position(self):
        view = self._views[self.view_mode]
        return (view.verticalScrollBar().value(), view.horizontalScrollBar().value(),
                self.selection.state.focused)

    def _projection_key(self):
        return (self.search.text(), self.type_filter.currentData(), self.state_filter.currentData(),
                self.sort_mode, self.selection.state.reviewing)

    def set_view_mode(self, mode):
        if mode == self.view_mode:
            return
        projection = self._projection_key()
        self._positions[self.view_mode] = (projection, self._view_position())
        self.view_mode = mode
        self.view_buttons[mode].setChecked(True)
        saved_projection, position = self._positions.get(mode, (None, None))
        if saved_projection != projection:
            position = None
        self._filter(position=position, reveal=position is None or position[2] != self.selection.state.focused)
        self.preferences_changed.emit(mode, self.sort_mode)

    def _update_list(self, visible):
        if self._table_needs_refresh:
            records = self._ordered
            ids = [record.id for record in records]
            self.table.replace_rows([record.table_row() for record in records], ids,
                                    [record.table_tooltip() for record in records])
            self._table_rows = {asset_id: row for row, asset_id in enumerate(ids)}
            for asset_id, row in self._table_rows.items():
                self.table.setRowHidden(row, asset_id not in visible)
            self._table_needs_refresh = False
        else:
            for asset_id in self._table_visible ^ visible:
                self.table.setRowHidden(self._table_rows[asset_id], asset_id not in visible)
        self._table_visible = visible

    def _present_results(self, matched, position, reveal):
        state = self.selection.state
        view = self._views[self.view_mode]
        had_focus = self.browser.currentWidget().hasFocus()
        self._updating_view = True
        self.table.blockSignals(True)
        self._reset_thumbnails()
        try:
            self.browser.setCurrentWidget(view)
            if view is self.table:
                self._update_list(state.visible)
                index = self.table.model().index(self._table_rows.get(state.focused, -1), 0)
            else:
                view.model().replace(matched)
                index = view.model().index_for(state.focused)
            if state.focused not in state.visible:
                index = QModelIndex()
            if index.isValid() and view.currentIndex() != index:
                view.setCurrentIndex(index)
            elif not index.isValid() and view.currentIndex().isValid():
                view.setCurrentIndex(QModelIndex())
            if reveal and index.isValid():
                view.scrollTo(index)
            elif position is not None:
                view.verticalScrollBar().setValue(position[0])
                view.horizontalScrollBar().setValue(position[1])
            if had_focus and view.isVisible():
                view.setFocus()
        finally:
            self.table.blockSignals(False)
            self._updating_view = False
        view.viewport().update()

    @staticmethod
    def _media(asset):
        return next((f for f in asset["files"] if f["kind"] == "media"), None)

    def selected_ids(self):
        return self.selection.state.ids()

    def visible_ids(self):
        return [key for key in self.selection.state.order if key in self.selection.state.visible]

    def select_visible(self):
        self.selection.select_visible()

    def _clear_selection(self):
        self.selection.clear()
        self.table.clearSelection()

    def _focused_ids(self):
        focused = self.selection.state.focused
        if focused in self.selection.state.visible:
            return [focused]
        selected = self.selected_ids()
        return selected if len(selected) == 1 and selected[0] in self.selection.state.visible else []

    def clear_filters(self):
        self.selection.state.reviewing = False
        with QSignalBlocker(self.search), QSignalBlocker(self.type_filter), QSignalBlocker(self.state_filter):
            self.search.clear()
            self.type_filter.setCurrentIndex(0)
            self.state_filter.setCurrentIndex(0)
        self._filter()

    def _toggle_selection_review(self):
        self.selection.state.reviewing = not self.selection.state.reviewing
        self._filter()

    def _checked_changed(self):
        if self.selection.state.reviewing:
            self._filter()
        else:
            self.selection_bar.update_state(self.selection.state)
            self.browser.currentWidget().viewport().update()
            self._selection()

    def _filter(self, *_, position=None, reveal=False):
        terms = normalize(self.search.text()).split()
        mode, state = self.type_filter.currentData(), self.state_filter.currentData()
        reviewing = self.selection.state.reviewing
        for control in (self.search, self.type_filter, self.state_filter):
            control.setEnabled(not reviewing)
        if reviewing:
            matched = [record for record in self._ordered if record.id in self.selection.state.selected]
        else:
            matched = [
                record for record in self._ordered
                if (mode == "all" or record.asset["item"].output_mode.value == mode)
                and (state == "all" or record.media.get("state", "unchecked") == state)
                and all(term in record.search_text for term in terms)
            ]
        self.selection.set_visible(record.id for record in matched)
        if not self._load_error and self.repository is not None:
            self.stack.setCurrentIndex(1 if not self._assets else 0 if matched else 2)
        self._present_results(matched, position, reveal)
        self.selection_bar.update_state(self.selection.state)
        self._selection()

    def _table_focus_changed(self):
        if not self._updating_view and self.view_mode == "list":
            self._selection()

    def _browse_focus_changed(self, index, _previous):
        if not self._updating_view and self.view_mode != "list":
            self.selection.state.focused = index.data(Qt.UserRole)
            self.browser.currentWidget().viewport().update()
            self._selection()

    def _browse_open(self, index):
        if index.data(Qt.UserRole) is not None:
            self.open_file(False)

    def _reset_thumbnails(self):
        self._thumbnail_timer.stop()
        self._painted_records.clear()
        self._thumbnails.reset()

    def _thumbnail_source(self, record):
        return ThumbnailSource(
            ThumbnailFile.from_entry(record.cover),
            None if record.audio else ThumbnailFile.from_entry(record.media),
            record.duration, self.ffmpeg_path,
        )

    def _thumbnail_for(self, asset_id):
        record = self._records.get(asset_id)
        if record is None:
            return False, QImage()
        self._painted_records.add(asset_id)
        return record.audio, self._thumbnails.image(self._thumbnail_source(record))

    def _load_visible_thumbnails(self, *_):
        view = self._views[self.view_mode]
        if self._updating_view or not view.isVisible():
            return
        model = view.model()
        rows = self._table_rows if view is self.table else model.rows_by_id
        viewport = view.viewport().rect()
        visible = {}
        painted = set()
        for asset_id in sorted(self._painted_records.intersection(rows), key=rows.__getitem__):
            index = model.index(rows[asset_id], 0)
            if viewport.intersects(view.visualRect(index)):
                painted.add(asset_id)
                source = self._thumbnail_source(self._records[asset_id])
                visible.setdefault(source, []).append(asset_id)
        self._painted_records = painted
        self._thumbnails.show(visible)

    def _thumbnail_changed(self, _ids):
        self._views[self.view_mode].viewport().update()

    def eventFilter(self, target, event):
        kind = event.type()
        if kind in (QEvent.Resize, QEvent.Paint, QEvent.Hide, QEvent.KeyPress) and hasattr(self, "_views"):
            active = self._views[self.view_mode]
            if target is self.table.viewport() and kind == QEvent.Resize:
                self._resize_columns()
            if target is active.viewport() and kind == QEvent.Paint:
                self._thumbnail_timer.start(0)
            if target is active:
                if kind == QEvent.Hide:
                    self._reset_thumbnails()
                elif kind == QEvent.KeyPress and handle_browse_key(
                    active, event, self.select_visible, lambda: self.open_file(False),
                ):
                    return True
        return super().eventFilter(target, event)

    def _selection(self, *_args, attachment_id=None):
        ids = self._focused_ids()
        if ids and ids[0] == self._detail_asset and (attachment := self.files.currentItem()):
            attachment_id = attachment.data(0, Qt.UserRole)["id"]
        self.files.blockSignals(True)
        self.files.clear()
        if len(ids) == 1 and not self._load_error:
            asset = self._records[ids[0]].asset
            if self._detail_asset != ids[0]:
                self.attachments_toggle.setChecked(False)
            self._detail_asset = ids[0]
            media = self._media(asset)
            self.detail_title.set_full_text(asset["item"].display_title)
            self.detail_path.set_full_text(media["path"] if media else asset["path"])
            hint = {
                "missing": "未找到文件，请重新选择以更新位置。",
                "inaccessible": "无法访问，请检查目录或磁盘连接后重试。",
                "recycled": "文件已回收，请从系统回收站恢复后检查。",
            }.get(media["state"] if media else "unchecked", "")
            if asset["outcome"].warnings:
                self.detail_title.setToolTip(
                    asset["item"].display_title
                    + "\n"
                    + "\n".join(asset["outcome"].warnings)
                )
            outcome = self._presented_outcome(asset)
            missing = media and media["state"] in {"missing", "inaccessible"}
            repair = self.request_supplement if outcome.missing_artifacts and not missing else None
            self.detail.set_result(asset["item"], outcome, media_state=_media_state(media, outcome), supplement=repair)
            if not hint and outcome.media_verification.get("valid") is False:
                hint = outcome.media_verification.get("message", "")
            self.detail_hint.set_full_text(hint)
            self.detail_hint.setVisible(bool(hint))
            primary = ("重新选择位置…", self.relocate) if missing else ("打开文件", lambda: self.open_file(False))
            secondary = ("补全附件…", repair) if repair else ("打开文件夹", lambda: self.open_file(True))
            self.detail.set_actions(primary, secondary)
            labels = {
                "subtitle": "字幕",
                "danmaku": "弹幕",
                "cover": "封面",
                "metadata": "元数据",
            }
            for entry in asset["files"]:
                if entry["kind"] == "media":
                    continue
                row = QTreeWidgetItem(
                    [
                        f"{labels.get(entry['kind'], '附件')} · {Path(entry['path']).name}",
                        FILE_STATES[entry["state"]],
                        _size(entry["size"]),
                    ]
                )
                row.setData(0, Qt.UserRole, entry)
                row.setToolTip(0, entry["path"])
                self.files.addTopLevelItem(row)
                if entry["id"] == attachment_id:
                    self.files.setCurrentItem(row)
            count = self.files.topLevelItemCount()
            self.attachments_toggle.setText(f"附件文件（{count}）")
            self.attachments_toggle.setVisible(count > 0)
            self.files.setVisible(count > 0 and self.attachments_toggle.isChecked())
            header_height = max(
                self.files.header().height(), self.files.header().sizeHint().height()
            )
            row_height = max(
                self.files.sizeHintForRow(0), self.files.fontMetrics().height() + 12
            )
            self.files.setFixedHeight(
                min(
                    180,
                    header_height
                    + row_height * count
                    + 2 * self.files.frameWidth()
                    + 4,
                )
            )
        self.files.blockSignals(False)
        self.detail.setVisible(len(ids) == 1 and not self._load_error)
        self._actions()

    def _actions(self):
        ids, ready = (
            self.selected_ids(),
            self.repository is not None and not self._load_error,
        )
        visible = self.visible_ids()
        self.count_label.setText(
            f"显示 {len(visible)} / {len(self._assets)} 项"
            + (f" · 已选 {len(ids)} 项" if ids else "")
        )
        self.count_label.setVisible(ready and bool(self._assets) and not ids and not self.selection.state.reviewing)
        for button in (self.open_action, self.folder_action):
            button.setEnabled(ready and bool(self._focused_ids()))
            button.setToolTip("请选择一个文件" if len(ids) != 1 else button.text())
        self.copy_action.setEnabled(ready and bool(ids))
        self.locate_action.setEnabled(ready and bool(self._focused_ids()) and not self._jobs)
        self.relocate_directory_action.setEnabled(ready and not self._jobs)
        self.verify_action.setEnabled(ready and bool(ids or visible) and not self._jobs)
        for action in (self.supplement_action, self.copy_media_action):
            action.setEnabled(ready and bool(self._focused_ids()) and not self._jobs)
        self.detail_relocate.setEnabled(not self._jobs)
        self.hide_action.setEnabled(ready and bool(ids) and not self._jobs)
        self.recycle_action.setEnabled(ready and not self._jobs and any(
            entry["state"] != "recycled" for asset_id in ids
            for entry in self._records[asset_id].asset["files"]
        ))
        self.undo_action.setEnabled(
            bool(self._removed_ids) and not self._jobs and ready
        )
        self.select_action.setEnabled(ready and bool(visible))
        self.deselect_action.setEnabled(bool(ids))
        self.check_button.setEnabled(ready and bool(ids or visible) and not self._jobs)
        self.check_button.setText(f"检查所选（{len(ids)}）" if ids else "检查文件")
        self.check_button.setToolTip(
            "检查所选文件及附件"
            if ids
            else f"检查当前列表的 {len(visible)} 项下载及附件"
        )
        pending = (
            len(list(self.repository.pending_dir.glob("*.json")))
            if self.repository
            else 0
        )
        self.recover_action.setVisible(pending > 0 or self._load_error)
        self.recover_action.setText(
            f"恢复文件记录（{pending}）" if pending else "恢复文件记录"
        )
        self.recover_action.setEnabled(self.repository is not None and not self._jobs)
        self.details_action.setVisible(bool(self._details))
        self.details_action.setEnabled(bool(self._details))

    def _file(self):
        ids = self._focused_ids()
        if len(ids) != 1:
            return None
        return self._records[ids[0]].media or None

    @staticmethod
    def _presented_outcome(asset):
        outcome = asset["outcome"].model_copy(deep=True)
        missing = set(outcome.missing_artifacts)
        missing.update(entry["kind"] for entry in asset["files"] if entry["kind"] != "media" and entry["state"] in {"missing", "inaccessible", "recycled"})
        outcome.missing_artifacts = sorted(missing)
        return outcome

    def request_supplement(self, *, force_new=False):
        from bilibili_downloader.core.models import TaskStatus
        from bilibili_downloader.gui.dialogs.attachments import choose_attachments
        ids = self._focused_ids()
        if len(ids) != 1:
            return
        asset = self._records[ids[0]].asset
        media = self._media(asset)
        item = asset["item"]
        if not force_new:
            item = choose_attachments(item, self, outcome=self._presented_outcome(asset))
        if item is not None and force_new:
            from bilibili_downloader.gui.dialogs.attachments import confirm_media_copy
            if not confirm_media_copy(item, self):
                return
        if item is not None and media:
            self.reuse_requested.emit(item.model_copy(update={
                "force_new": force_new, "reuse_media_path": None if force_new else media["path"],
                "strict_match": False if not force_new else item.strict_match,
                "retry_count": 0, "retry_at": None, "status": TaskStatus.QUEUED,
            }, deep=True))

    def verify(self):
        ids = self.selected_ids() or self.visible_ids()
        if ids and self.repository:
            self._run(lambda progress: self.repository.verify_media(ids, self.ffmpeg_path, self._cancel, progress), kind="verify")

    def relocate_directory(self):
        if self.repository is None or self._jobs:
            return
        from bilibili_downloader.gui.dialogs.relocate_directory import (
            RelocateDirectoryDialog,
        )
        media = self._file()
        dialog = RelocateDirectoryDialog(self.repository, str(Path(media["path"]).parent) if media else "", self, pool=self._pool)
        def completed(count):
            self.refresh()
            self._feedback(f"已更新 {count} 个文件的位置。")
        dialog.completed.connect(completed)
        dialog.exec()

    def open_file(self, directory, *, entry=None):
        entry = entry or self._file()
        if not entry:
            return
        path = Path(entry["path"])
        target = path.parent if directory else path
        if not target.exists():
            if entry["state"] == "recycled":
                self._feedback("文件已回收，请从系统回收站恢复后检查。", "warning")
            elif not path.parent.is_dir():
                self._feedback("无法访问，请检查目录或磁盘连接后重试。", "warning")
            else:
                self._feedback(
                    "文件未找到，可重新选择文件。",
                    "warning",
                    action="重新选择",
                    callback=lambda: self.relocate(entry=entry),
                )
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            self._feedback("无法打开，请检查默认打开方式后重试。", "warning")

    def copy_path(self, *, entry=None):
        if entry:
            paths = [entry["path"]]
        else:
            ids = set(self.selected_ids())
            paths = [
                media["path"]
                for a in self._assets
                if a["id"] in ids and (media := self._media(a))
            ]
        if paths:
            QApplication.clipboard().setText("\n".join(paths))
            self._feedback(f"已复制 {len(paths)} 个文件路径。")

    def relocate(self, *, entry=None):
        entry = entry or self._file()
        if not entry or self._jobs:
            return

        def selected(path):
            try:
                self.repository.relocate(entry["id"], path)
                self.refresh()
                self._feedback("文件位置已更新。")
            except (OSError, ValueError, sqlite3.Error) as exc:
                self._feedback("无法更新位置，请重试。", "danger", details=str(exc))

        file_picker(self).open_file(
            "重新选择文件（仅更新记录，不移动文件）",
            entry["path"],
            "所有文件 (*)",
            selected,
        )

    def _context_menu(self, point, view=None):
        view = self.table if view is None else view
        index = view.indexAt(point).siblingAtColumn(0)
        focused_id = index.data(Qt.UserRole)
        if focused_id is None:
            return
        view.setCurrentIndex(index)
        selected_count = len(self.selected_ids())
        menu = PopupMenu(view)
        for title, callback, enabled in (
            ("打开文件", lambda: self.open_file(False), self.open_action.isEnabled()),
            (
                "打开文件夹",
                lambda: self.open_file(True),
                self.folder_action.isEnabled(),
            ),
            ("复制该文件路径", lambda: self.copy_path(entry=self._file()), self.open_action.isEnabled()),
            ("补全附件…", self.request_supplement, self.supplement_action.isEnabled()),
            ("检查此文件", lambda: self._run(lambda progress: self.repository.check_files([focused_id], self._cancel, progress)), self.check_button.isEnabled()),
            ("重新选择文件…", self.relocate, self.locate_action.isEnabled()),
            (f"移除所选 {selected_count} 项记录", self.hide_selected, self.hide_action.isEnabled()),
            (f"将所选 {selected_count} 项移入回收站…", self.recycle_selected, self.recycle_action.isEnabled()),
        ):
            menu.addAction(title, callback).setEnabled(enabled)
        menu.exec(view.viewport().mapToGlobal(point))

    def _attachment_menu(self, point):
        item = self.files.itemAt(point)
        if item is None:
            return
        self.files.setCurrentItem(item)
        entry = item.data(0, Qt.UserRole)
        menu = PopupMenu(self.files)
        menu.addAction("打开附件", lambda: self.open_file(False, entry=entry))
        menu.addAction("打开文件夹", lambda: self.open_file(True, entry=entry))
        menu.addAction("复制附件路径", lambda: self.copy_path(entry=entry))
        menu.addAction("重新选择附件…", lambda: self.relocate(entry=entry)).setEnabled(
            not self._jobs
        )
        menu.exec(self.files.viewport().mapToGlobal(point))

    def hide_selected(self):
        if self._jobs or not self.selected_ids():
            return
        try:
            removed = self.repository.hide(self.selected_ids())
        except (OSError, sqlite3.Error) as exc:
            self._feedback("记录未移除，请重试。", "danger", details=str(exc))
            return
        self._removed_ids = removed
        self.refresh()
        self._feedback(
            f"已移除 {len(removed)} 项记录，文件保留。",
            action="撤销",
            callback=self.undo_hide,
        )

    def undo_hide(self):
        try:
            restored = self.repository.restore_hidden(self._removed_ids)
        except (OSError, sqlite3.Error) as exc:
            self._feedback("恢复记录失败，请重试。", "danger", details=str(exc))
            return
        self._removed_ids = []
        self.refresh()
        self._feedback(f"已恢复 {len(restored)} 项记录。")

    def _run(self, action, *, kind="check"):
        if self._jobs:
            return
        self._cancel.clear()
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("取消检查")
        def perform(progress):
            result = action(progress)
            return result, None if kind == "check" and "file_updates" in result else self.repository.list_assets()
        job = _LibraryJob(perform)
        self._jobs.add(job)
        self._job_kind = kind
        self.progress_label.setText(
            {
                "check": "正在检查…",
                "recycle": "正在移入回收站…",
                "recover": "正在恢复记录…",
                "verify": "正在核验媒体…",
                "relocate_preview": "正在检查目录映射…",
                "relocate": "正在更新文件位置…",
            }[kind]
        )
        self.progress_label.show()
        self.cancel_button.setVisible(kind in {"check", "verify"})
        self._actions()
        job.signals.progress.connect(self._progress)

        def finished(result):
            self._jobs.discard(job)
            from shiboken6 import isValid
            if not isValid(self) or not isValid(self.table):
                return
            self.cancel_button.hide()
            self.progress_label.clear()
            self.progress_label.hide()
            if not isinstance(result, Exception):
                result, assets = result
                self._last_operation_report = result
                if assets is None:
                    self._apply_file_updates(result["file_updates"])
                else:
                    self.refresh(assets=assets)
            if isinstance(result, Exception):
                self._feedback("操作未完成，请重试。", "danger", details=str(result))
            elif kind == "relocate_preview":
                changes = result["changes"]
                unavailable = sum(not c["available"] for c in changes)
                if not changes or unavailable:
                    self._feedback(f"未修改位置：{len(changes)} 个文件中 {unavailable} 个目标不可读取。", "warning")
                    return
                box = OperationDialog("重新定位整个目录", f"更新 {len(changes)} 个文件记录的位置，不移动文件。",
                                      "\n".join(f"{c['old']} → {c['new']}" for c in changes), self, confirm="更新位置")
                if box.exec():
                    self._run(lambda _progress: self.repository.relocate_directory(result["old"], result["new"], apply=True), kind="relocate")
            elif kind == "relocate":
                self._feedback(f"已更新 {len(result)} 个文件的位置。")
            elif kind == "recycle":
                errors = [(p, e) for p, e in result if e]
                self._feedback(
                    f"已回收 {len(result) - len(errors)} 个文件"
                    + (f"，{len(errors)} 个未处理。" if errors else "。"),
                    "warning" if errors else "info",
                    details="\n".join(f"{p}\n{e}" for p, e in errors),
                )
            elif kind == "recover":
                text = (
                    f"已恢复 {result['restored']} 项文件记录。"
                    if result["restored"]
                    else ""
                )
                text += f"{result['failed']} 项仍待恢复。" if result["failed"] else ""
                self._feedback(
                    text or "文件记录已刷新。",
                    "warning" if result["failed"] else "info",
                )
            else:
                text = f"已检查 {result['checked']} 个文件"
                if result["cancelled"]:
                    text = f"检查已取消，保留 {result['checked']} 个文件的结果"
                if result["missing"]:
                    text += f"，{result['missing']} 个未找到"
                if result["inaccessible"]:
                    text += f"，{result['inaccessible']} 个无法访问"
                if result.get("skipped_changed"):
                    text += f"，{result['skipped_changed']} 个记录已变化，保留新记录"
                if result.get("invalid"):
                    text += f"，{result['invalid']} 个媒体异常"
                if kind == "verify":
                    text += "（轨道与时长检查，不代表逐帧完整性校验）"
                self._feedback(
                    text + "。",
                    "warning" if result["issues"] else "info",
                    details="\n".join(f"{p}\n{e}" for p, e in result["issues"]),
                )

        job.signals.finished.connect(finished)
        self._pool.start(job)

    def _request_cancel(self):
        self._cancel.set()
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("正在取消…")
        self.progress_label.setText("正在结束当前文件检查，已完成结果会保留…")

    def _progress(self, done, total):
        if self._cancel.is_set():
            return
        title = {"check": "快速检查", "verify": "核验轨道与时长", "recycle": "移入回收站"}.get(self._job_kind, "处理中")
        self.progress_label.setText(f"{title}（{done}/{total}）")

    def check(self):
        ids = self.selected_ids() or self.visible_ids()
        if ids and self.repository:
            self._run(
                lambda progress: self.repository.check_files(
                    ids, self._cancel, progress
                ),
                kind="check",
            )

    def replay(self):
        if self.repository is None:
            return
        self.stack.setCurrentIndex(3) if self._load_error else None

        def replay(_progress):
            before = len(list(self.repository.pending_dir.glob("*.json")))
            self.repository.initialize()
            failures = self.repository.replay_pending()
            self.repository.import_tasks(self.record_provider())
            return {"restored": before - len(failures), "failed": len(failures)}

        self._run(replay, kind="recover")

    def recycle_selected(self):
        if self._jobs:
            return
        try:
            entries = [
                e
                for e in self.repository.files_for(self.selected_ids())
                if e["state"] != "recycled"
            ]
        except (OSError, sqlite3.Error) as exc:
            self._feedback("无法读取文件清单，请重试。", "danger", details=str(exc))
            return
        if not entries:
            return
        attachments = sum(e["kind"] != "media" for e in entries)
        box = OperationDialog(
            "移入回收站？",
            f"共 {len(entries)} 个文件，包含 {attachments} 个附件。\n可从系统回收站恢复。",
            "\n".join(e["path"] for e in entries),
            self,
            confirm="移入回收站",
        )
        if box.exec() == QDialog.Accepted:
            self._run(
                lambda progress: self.repository.recycle(entries, progress=progress),
                kind="recycle",
            )

    def _resize_columns(self):
        hidden = self.table.viewport().width() < 1000
        if self.table.isColumnHidden(DIRECTORY_COLUMN) != hidden:
            self.table.setColumnHidden(DIRECTORY_COLUMN, hidden)

    def cancel_work(self):
        self._cancel.set()
        self._read_generation += 1
        self._refresh_timer.stop()
        self._reset_thumbnails()
