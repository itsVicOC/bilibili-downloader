"""Local downloads with explicit selection, concise feedback and recoverable actions."""

import sqlite3
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence
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
    QTableWidgetItem,
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
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    CommandBar,
    ElidedLabel,
    EmptyState,
    Notice,
    PopupMenu,
    ReadOnlyPath,
    palette,
)
from bilibili_downloader.gui.widgets.row_hover import RowHoverTable, row_option


class _FileLabelDelegate(QStyledItemDelegate):
    """Keep the filename and secondary context readable within a compact row."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
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


class OperationDialog(QDialog):
    """Keep the consequence visible even when the file list is very long."""

    def __init__(self, title, summary, details, parent=None, *, confirm=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        layout.addWidget(heading)
        self.summary = QLabel(summary)
        self.summary.setTextFormat(Qt.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.reader = QPlainTextEdit(details)
        self.reader.setReadOnly(True)
        self.reader.setMinimumHeight(180)
        self.reader.setAccessibleName("文件清单及处理详情")
        if confirm:
            toggle = QPushButton("查看文件清单")
            toggle.setObjectName("TextButton")
            toggle.setCheckable(True)
            self.reader.hide()

            def expand(checked):
                self.reader.setVisible(checked)
                toggle.setText("收起文件清单" if checked else "查看文件清单")
                self.adjustSize()

            toggle.toggled.connect(expand)
            layout.addWidget(toggle, alignment=Qt.AlignLeft)
        layout.addWidget(self.reader)
        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("取消" if confirm else "关闭")
        close.clicked.connect(self.reject if confirm else self.accept)
        close.setDefault(True)
        footer.addWidget(close)
        if confirm:
            accept = QPushButton(confirm)
            accept.setObjectName("DangerButton")
            accept.setAutoDefault(False)
            accept.clicked.connect(self.accept)
            footer.addWidget(accept)
        layout.addLayout(footer)
        self.resize(600, 220 if confirm else 360)


class _JobSignals(QObject):
    finished = Signal(object)
    progress = Signal(int, int)


class _LibraryJob(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.signals = _JobSignals()
        self.action = action

    def run(self):
        try:
            result = self.action(self.signals.progress.emit)
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


class _FileTable(RowHoverTable):
    select_all_requested = Signal()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.SelectAll):
            self.select_all_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class LibraryPage(QWidget):
    download_requested = Signal()

    def __init__(self, parent=None, *, pool=None):
        super().__init__(parent)
        self.repository = None
        self.record_provider = lambda: []
        self._pool = pool or QThreadPool.globalInstance()
        self._jobs = set()
        self._cancel = threading.Event()
        self._assets = []
        self._removed_ids = []
        self._load_error = False
        self._details = ""
        self._notice_callback = None
        self._detail_asset = None
        self._job_kind = ""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
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
        self.open_action = QPushButton("打开文件")
        self.folder_action = QPushButton("打开文件夹")
        self.check_button = QPushButton("检查文件")
        for button, callback in (
            (self.open_action, lambda: self.open_file(False)),
            (self.folder_action, lambda: self.open_file(True)),
            (self.check_button, self.check),
        ):
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(callback)
            self.tools.actions.addWidget(button)
        self.cancel_button = QPushButton("取消检查")
        self.cancel_button.clicked.connect(self._cancel.set)
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
        summary = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("MetaLabel")
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MetaLabel")
        summary.addWidget(self.count_label)
        summary.addStretch()
        summary.addWidget(self.progress_label)
        layout.addLayout(summary)
        self.table = _FileTable()
        self.table.setColumnCount(6)
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
        self.detail = QWidget()
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)
        self.detail_title = ElidedLabel()
        detail_layout.addWidget(self.detail_title)
        path_row = QHBoxLayout()
        self.detail_path = ReadOnlyPath()
        path_row.addWidget(self.detail_path, 1)
        copy = QPushButton("复制路径")
        copy.setObjectName("TextButton")
        copy.clicked.connect(self.copy_path)
        path_row.addWidget(copy)
        self.detail_relocate = QPushButton("重新选择文件…")
        self.detail_relocate.setObjectName("TextButton")
        self.detail_relocate.clicked.connect(self.relocate)
        path_row.addWidget(self.detail_relocate)
        detail_layout.addLayout(path_row)
        self.detail_hint = QLabel()
        self.detail_hint.setObjectName("MetaLabel")
        self.detail_hint.setWordWrap(True)
        detail_layout.addWidget(self.detail_hint)
        self.attachments_toggle = QPushButton()
        self.attachments_toggle.setObjectName("TextButton")
        self.attachments_toggle.setCheckable(True)
        self.attachments_toggle.toggled.connect(
            lambda expanded: self.files.setVisible(
                expanded and self.files.topLevelItemCount() > 0
            )
        )
        detail_layout.addWidget(self.attachments_toggle, alignment=Qt.AlignLeft)
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["附件", "状态", "大小"])
        self.files.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.setMaximumHeight(180)
        self.files.setRootIsDecorated(False)
        self.files.setUniformRowHeights(True)
        self.files.itemDoubleClicked.connect(
            lambda item, _: self.open_file(False, entry=item.data(0, Qt.UserRole))
        )
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._attachment_menu)
        self.files.hide()
        detail_layout.addWidget(self.files)
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
        self.refresh()

    def schedule_refresh(self):
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(120)

    def refresh(self):
        if self.repository is None:
            self.stack.setCurrentIndex(3)
            self._actions()
            return
        selected = set(self.selected_ids())
        scroll = (
            self.table.verticalScrollBar().value(),
            self.table.horizontalScrollBar().value(),
        )
        attachment = self.files.currentItem()
        attachment_id = attachment.data(0, Qt.UserRole)["id"] if attachment else None
        try:
            assets = self.repository.list_assets()
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
        self.table.setRowCount(len(assets))
        for row, asset in enumerate(assets):
            item, outcome = asset["item"], asset["outcome"]
            media = self._media(asset)
            quality = next(
                (q.label for q in VideoQuality if q.value == outcome.actual_quality),
                "规格未知",
            )
            spec = (
                f"仅音频\n{AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '规格未知')}"
                if item.output_mode == OutputMode.AUDIO
                else f"视频 · {quality}\n{VIDEO_CODEC_MAP.get(outcome.actual_video_codec, '编码未知')}"
            )
            filename = Path(media["path"]).name if media else Path(asset["path"]).name
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
                FILE_STATES.get(media["state"], "待检查") if media else "待检查",
                str(Path(media["path"] if media else asset["path"]).parent),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value + ("\n" + item.display_title if col == 0 else ""))
                if col == 0:
                    cell.setData(Qt.UserRole, asset["id"])
                self.table.setItem(row, col, cell)
            if asset["id"] in selected:
                for col in range(6):
                    self.table.item(row, col).setSelected(True)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._filter()
        self._selection(attachment_id=attachment_id)
        self.table.verticalScrollBar().setValue(scroll[0])
        self.table.horizontalScrollBar().setValue(scroll[1])
        self._resize_columns()

    @staticmethod
    def _media(asset):
        return next((f for f in asset["files"] if f["kind"] == "media"), None)

    def selected_ids(self):
        # Responsive column visibility must not turn a selected row into a
        # partial selection that QItemSelectionModel.selectedRows() omits.
        return [
            self.table.item(index.row(), 0).data(Qt.UserRole)
            for index in self.table.selectionModel().selectedIndexes()
            if index.column() == 0 and not self.table.isRowHidden(index.row())
        ]

    def visible_ids(self):
        return [
            asset["id"]
            for row, asset in enumerate(self._assets)
            if not self.table.isRowHidden(row)
        ]

    def select_visible(self):
        self.table.blockSignals(True)
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                for col in range(6):
                    self.table.item(row, col).setSelected(True)
        self.table.blockSignals(False)
        self._selection()

    def _clear_selection(self):
        self.table.clearSelection()

    def clear_filters(self):
        self.search.clear()
        self.type_filter.setCurrentIndex(0)
        self.state_filter.setCurrentIndex(0)

    def _filter(self, *_):
        query = self.search.text().strip().casefold()
        mode, state = self.type_filter.currentData(), self.state_filter.currentData()
        self.table.blockSignals(True)
        for row, asset in enumerate(self._assets):
            media = self._media(asset) or {}
            info = asset["item"].video_info
            searchable = " ".join(
                [
                    asset["item"].display_title,
                    info.author,
                    info.owner_name,
                    info.collection_title,
                    info.series_title,
                    *(f["path"] for f in asset["files"]),
                ]
            )
            visible = (
                (mode == "all" or asset["item"].output_mode.value == mode)
                and (state == "all" or media.get("state", "unchecked") == state)
                and query in searchable.casefold()
            )
            self.table.setRowHidden(row, not visible)
            if not visible:
                for col in range(6):
                    self.table.item(row, col).setSelected(False)
        self.table.blockSignals(False)
        if not self._load_error and self.repository is not None:
            self.stack.setCurrentIndex(
                1 if not self._assets else 0 if self.visible_ids() else 2
            )
        self._selection()

    def _selection(self, *_args, attachment_id=None):
        ids = self.selected_ids()
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
                hint += (
                    " " if hint else ""
                ) + f"有 {len(asset['outcome'].warnings)} 条下载提示，悬停作品可查看。"
                self.detail_title.setToolTip(
                    asset["item"].display_title
                    + "\n"
                    + "\n".join(asset["outcome"].warnings)
                )
            self.detail_hint.setText(hint)
            self.detail_hint.setVisible(bool(hint))
            self.detail_relocate.setVisible(
                bool(media and media["state"] in {"missing", "inaccessible"})
            )
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
            self.attachments_toggle.setText(f"附件（{count}）")
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
            button.setEnabled(ready and len(ids) == 1)
            button.setToolTip("请选择一个文件" if len(ids) != 1 else button.text())
        self.copy_action.setEnabled(ready and bool(ids))
        self.locate_action.setEnabled(ready and len(ids) == 1 and not self._jobs)
        self.detail_relocate.setEnabled(not self._jobs)
        self.hide_action.setEnabled(ready and bool(ids) and not self._jobs)
        candidates = [
            f
            for a in self._assets
            if a["id"] in ids
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
        ids = self.selected_ids()
        if len(ids) != 1:
            return None
        return self._media(next(a for a in self._assets if a["id"] == ids[0]))

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
        if self.table.item(index.row(), 0).data(Qt.UserRole) not in self.selected_ids():
            self.table.clearSelection()
            self.table.selectRow(index.row())
        menu = PopupMenu(self.table)
        for title, callback, enabled in (
            ("打开文件", lambda: self.open_file(False), self.open_action.isEnabled()),
            (
                "打开文件夹",
                lambda: self.open_file(True),
                self.folder_action.isEnabled(),
            ),
            ("复制路径", self.copy_path, self.copy_action.isEnabled()),
            ("重新选择文件…", self.relocate, self.locate_action.isEnabled()),
            ("移除记录", self.hide_selected, self.hide_action.isEnabled()),
            ("移入回收站…", self.recycle_selected, self.recycle_action.isEnabled()),
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
        job = _LibraryJob(action)
        self._jobs.add(job)
        self._job_kind = kind
        self.progress_label.setText(
            {
                "check": "正在检查…",
                "recycle": "正在移入回收站…",
                "recover": "正在恢复记录…",
            }[kind]
        )
        self.cancel_button.setVisible(kind == "check")
        self._actions()
        job.signals.progress.connect(self._progress)

        def finished(result):
            self._jobs.discard(job)
            self.cancel_button.hide()
            self.progress_label.clear()
            self.refresh()
            if isinstance(result, Exception):
                self._feedback("操作未完成，请重试。", "danger", details=str(result))
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
                self._feedback(
                    text + "。",
                    "warning" if result["issues"] else "info",
                    details="\n".join(f"{p}\n{e}" for p, e in result["issues"]),
                )

        job.signals.finished.connect(finished)
        self._pool.start(job)

    def _progress(self, done, total):
        title = "检查文件" if self._job_kind == "check" else "移入回收站"
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
