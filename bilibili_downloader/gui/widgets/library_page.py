"""Local downloads with explicit selection, concise feedback and recoverable actions."""

import sqlite3
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.library import FILE_STATES
from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    VIDEO_CODEC_MAP,
    OutputMode,
    VideoQuality,
)
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
    palette,
)
from bilibili_downloader.gui.widgets.file_table import FileTable
from bilibili_downloader.gui.widgets.row_hover import row_option
from bilibili_downloader.gui.widgets.selection import SelectionBar, TableSelection


class _FileLabelDelegate(QStyledItemDelegate):
    """Keep the filename and secondary context readable within a compact row."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator
        lines, opt.text = opt.text.splitlines()[:2], ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(
            QStyle.CE_ItemViewItem, row_option(opt, index), painter, opt.widget
        )
        painter.save()
        painter.setClipRect(opt.rect)
        painter.setFont(opt.font)
        metrics = painter.fontMetrics()
        height = metrics.height()
        top = opt.rect.center().y() - height * len(lines) // 2
        colors = palette()
        for number, line in enumerate(lines):
            painter.setPen(QColor(colors.text if number == 0 else colors.muted))
            painter.drawText(
                opt.rect.left() + 10,
                top + metrics.ascent() + number * height,
                metrics.elidedText(line, Qt.ElideRight, max(1, opt.rect.width() - 20)),
            )
        painter.restore()


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


def _size(value):
    if value is None:
        return "未知"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _media_state(media, outcome):
    state = media["state"] if media else "unchecked"
    if state not in {"missing", "inaccessible", "recycled"} and outcome.media_verification.get("valid") is False:
        return "媒体异常"
    return FILE_STATES.get(state, "待检查")


class LibraryPage(QWidget):
    download_requested = Signal()
    reuse_requested = Signal(object)

    def __init__(self, parent=None, *, pool=None):
        super().__init__(parent)
        self.repository = None
        self.record_provider = lambda: []
        self._pool = pool or QThreadPool.globalInstance()
        self._jobs = set()
        self._read_jobs = set()
        self._read_generation = 0
        self._cancel = threading.Event()
        self._assets = []
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
        self.search.setPlaceholderText("搜索文件、作品或作者")
        self.search.setToolTip("支持分 P、作者、合集及完整路径")
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
        self.details_action = menu.addAction("查看上次处理详情", self.show_details)
        more.setMenu(menu)
        self.tools.actions.addWidget(more)
        layout.addWidget(self.tools)
        self.selection_bar = SelectionBar()
        layout.addWidget(self.selection_bar)
        summary = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("MetaLabel")
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MetaLabel")
        self.count_label.hide()
        summary.addStretch()
        summary.addWidget(self.progress_label)
        layout.addLayout(summary)
        self.table = FileTable()
        self.table.setHorizontalHeaderLabels(
            [
                "文件 / 作品",
                "作者 / 合集",
                "类型 / 规格",
                "大小",
                "文件状态",
                "所在目录",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 120), (2, 132), (3, 80), (4, 100), (5, 190)):
            self.table.setColumnWidth(column, width)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        for column in (0, 1, 2):
            self.table.setItemDelegateForColumn(column, _FileLabelDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.selection = TableSelection(self.table, _FileLabelDelegate(self.table), paint_only=True)
        self.selection.changed.connect(self._checked_changed)
        self.selection.focus_changed.connect(self._selection)
        self.selection_bar.select_visible.connect(self.select_visible)
        self.selection_bar.clear_requested.connect(self._clear_selection)
        self.selection_bar.review_requested.connect(self._toggle_selection_review)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_file(False))
        self.table.select_all_requested.connect(self.select_visible)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.stack = QStackedWidget()
        # Empty-state hints must not prevent the file table from shrinking when
        # the attachment panel is expanded in a compact window.
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.stack.setMinimumHeight(60)
        self.stack.addWidget(self.table)
        self.stack.addWidget(
            EmptyState(
                "暂无文件记录",
                "下载完成后，文件会显示在这里。",
                "去下载",
                self.download_requested.emit,
            )
        )
        self.stack.addWidget(
            EmptyState(
                "没有匹配的文件",
                "试试其他关键词或筛选条件。",
                "清除筛选",
                self.clear_filters,
            )
        )
        self.stack.addWidget(EmptyState("正在加载文件记录", "请稍候。"))
        self.stack.addWidget(
            EmptyState(
                "文件列表暂不可用", "本地文件仍保留，请重试加载。", "重试", self.replay
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
            "处理详情", "完整路径和逐项原因如下。", self._details, self
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
        scroll = (
            self.table.verticalScrollBar().value(),
            self.table.horizontalScrollBar().value(),
        )
        attachment = self.files.currentItem()
        attachment_id = attachment.data(0, Qt.UserRole)["id"] if attachment else None
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
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        rows = []
        titles, search_text, media_index = [], {}, {}
        quality_names = {q.value: q.label for q in VideoQuality}
        for row, asset in enumerate(assets):
            item, outcome = asset["item"], asset["outcome"]
            media = self._media(asset)
            media_index[asset["id"]] = media or {}
            quality = quality_names.get(outcome.actual_quality, "规格未知")
            spec = (
                f"仅音频\n{AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '规格未知')}"
                if item.output_mode == OutputMode.AUDIO
                else f"视频 · {quality}\n{VIDEO_CODEC_MAP.get(outcome.actual_video_codec, '编码未知')}"
            )
            path = Path(media["path"] if media else asset["path"])
            filename = path.name
            values = [
                f"{filename}\n{item.video_info.title}",
                "\n".join(
                    v
                    for v in (
                        item.video_info.author or item.video_info.owner_name,
                        item.video_info.collection_title
                        or item.video_info.series_title
                        or item.video_info.season_title,
                    )
                    if v
                ),
                spec,
                _size(media["size"] if media else None),
                _media_state(media, outcome),
                str(path.parent),
            ]
            rows.append(values)
            title = item.display_title
            titles.append(title)
            info = item.video_info
            search_text[asset["id"]] = " ".join((title, info.author, info.owner_name, info.collection_title, info.series_title, *(f["path"] for f in asset["files"]))).casefold()
        self._search_text, self._media_index = search_text, media_index
        self.table.replace_rows(rows, [a["id"] for a in assets], titles)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.selection.reset([a["id"] for a in assets])
        focused = self.selection.state.focused
        if focused is not None:
            self.table.blockSignals(True)
            self.table.setCurrentCell(self.selection.state.order.index(focused), 0)
            self.table.blockSignals(False)
        self._filter()
        self._selection(attachment_id=attachment_id)
        self.table.verticalScrollBar().setValue(scroll[0])
        self.table.horizontalScrollBar().setValue(scroll[1])
        self._resize_columns()
        self._last_refresh_ms = (time.perf_counter() - refresh_started) * 1000

    def _apply_file_updates(self, updates):
        """A check only changes file facts; avoid decoding/rebuilding the library."""
        started = time.perf_counter()
        self._read_generation += 1
        entries = {entry["id"]: (row, entry) for row, asset in enumerate(self._assets) for entry in asset["files"]}
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        changed_rows = []
        try:
            for update in updates:
                current = entries.get(update["id"])
                if current is None or current[1]["path"] != update["path"]:
                    continue
                row, entry = current
                entry.update(update)
                if entry["kind"] != "media":
                    continue
                outcome = self._assets[row]["outcome"]
                state = _media_state(entry, outcome)
                for column, value in ((3, _size(entry["size"])), (4, state)):
                    if self.table.model().rows[row][column] != value:
                        self.table.model().rows[row][column] = value
                        changed_rows.append(row)
            if changed_rows:
                model = self.table.model()
                model.dataChanged.emit(model.index(min(changed_rows), 3), model.index(max(changed_rows), 4), [Qt.DisplayRole, Qt.ToolTipRole])
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        if self.state_filter.currentData() != "all":
            self._filter()
        else:
            self._selection()
        self._last_refresh_ms = (time.perf_counter() - started) * 1000

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
            self._selection()

    def _filter(self, *_):
        query = self.search.text().strip().casefold()
        mode, state = self.type_filter.currentData(), self.state_filter.currentData()
        reviewing = self.selection.state.reviewing
        for control in (self.search, self.type_filter, self.state_filter):
            control.setEnabled(not reviewing)
        visible_ids = []
        self.table.blockSignals(True)
        for row, asset in enumerate(self._assets):
            media = self._media_index[asset["id"]]
            visible = (
                (mode == "all" or asset["item"].output_mode.value == mode)
                and (state == "all" or media.get("state", "unchecked") == state)
                and query in self._search_text[asset["id"]]
            )
            if reviewing:
                visible = asset["id"] in self.selection.state.selected
            self.table.setRowHidden(row, not visible)
            if visible:
                visible_ids.append(asset["id"])
        self.table.blockSignals(False)
        if not self._load_error and self.repository is not None:
            self.stack.setCurrentIndex(
                1 if not self._assets else 0 if visible_ids else 2
            )
        self.selection.set_visible(visible_ids)
        self.selection_bar.update_state(self.selection.state)
        self._selection()

    def _selection(self, *_args, attachment_id=None):
        ids = self._focused_ids()
        self.files.blockSignals(True)
        self.files.clear()
        if len(ids) == 1 and not self._load_error:
            asset = next(a for a in self._assets if a["id"] == ids[0])
            if self._detail_asset != ids[0]:
                self.attachments_toggle.setChecked(False)
            self._detail_asset = ids[0]
            media = self._media(asset)
            self.detail_title.set_full_text(asset["item"].display_title)
            self.detail_path.set_full_text(media["path"] if media else asset["path"])
            hint = {
                "missing": "文件未找到，可重新选择文件更新位置。",
                "inaccessible": "无法访问，请检查目录或磁盘连接后重试。",
                "recycled": "文件已回收，可从系统回收站恢复后检查。",
            }.get(media["state"] if media else "unchecked", "")
            if asset["outcome"].warnings:
                self.detail_title.setToolTip(
                    asset["item"].display_title
                    + "\n"
                    + "\n".join(asset["outcome"].warnings)
                )
            outcome = self._presented_outcome(asset)
            self.detail.set_result(asset["item"], outcome, media_state=_media_state(media, outcome))
            if not hint and outcome.media_verification.get("valid") is False:
                hint = outcome.media_verification.get("message", "")
            self.detail_hint.set_full_text(hint)
            self.detail_hint.setVisible(bool(hint))
            missing = media and media["state"] in {"missing", "inaccessible"}
            primary = ("重新选择位置…", self.relocate) if missing else ("打开文件", lambda: self.open_file(False))
            secondary = ("补全附件…", self.request_supplement) if outcome.missing_artifacts and not missing else ("打开文件夹", lambda: self.open_file(True))
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
        selected_set = set(ids)
        candidates = [
            f
            for a in self._assets
            if a["id"] in selected_set
            for f in a["files"]
            if f["state"] != "recycled"
        ]
        self.recycle_action.setEnabled(ready and bool(candidates) and not self._jobs)
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
        return self._media(next(a for a in self._assets if a["id"] == ids[0]))

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
        asset = next(a for a in self._assets if a["id"] == ids[0])
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

    def _context_menu(self, point):
        index = self.table.indexAt(point)
        if not index.isValid():
            return
        self.table.setCurrentCell(index.row(), 0)
        focused_id = self.table.item(index.row(), 0).data(Qt.UserRole)
        selected_count = len(self.selected_ids())
        menu = PopupMenu(self.table)
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
        menu.exec(self.table.viewport().mapToGlobal(point))

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

    def _resize_columns(self, width=None):
        if hasattr(self, "table"):
            width = self.width() if width is None else width
            self.table.setColumnHidden(5, width < 1000)
            self.table.setColumnHidden(1, width < 700)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_columns(event.size().width())

    def cancel_work(self):
        self._cancel.set()
        self._read_generation += 1
        self._refresh_timer.stop()
