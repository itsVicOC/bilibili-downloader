"""Preview-first dialog for importing videos, collections and favorites."""

from collections import Counter
from dataclasses import dataclass

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QSignalBlocker,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.batch import batch_source_key, classify_batch_inputs
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.threads.batch_worker import (
    ImportIssue,
    ImportReport,
    SourceResolveRunner,
    SourceResolveWorker,
)
from bilibili_downloader.gui.widgets.components import (
    ActionButton,
    ElidedLabel,
    EmptyState,
    MessageBox,
    Notice,
    OutputActionBar,
    SectionCard,
    palette,
    scroll_area,
)
from bilibili_downloader.gui.widgets.dialog_shell import AppDialog
from bilibili_downloader.gui.widgets.responsive_actions import ResponsiveActions
from bilibili_downloader.gui.widgets.row_hover import (
    RowDelegate,
    RowHoverTable,
    row_option,
)
from bilibili_downloader.gui.widgets.selection import SelectionBar, TableSelection


@dataclass
class _BatchPreview:
    report: ImportReport
    source_text: str | None
    choices: dict[str, bool]
    filter_text: str
    reviewing: bool
    focused: str | None
    scroll: int
    focus_search: bool


class _PreviewTitleDelegate(RowDelegate):
    @staticmethod
    def subtitle_font(font):
        result = QFont(font)
        if font.pointSizeF() > 0:
            result.setPointSizeF(font.pointSizeF() * 0.82)
        else:
            result.setPixelSize(max(1, round(font.pixelSize() * 0.82)))
        return result

    def paint(self, painter, option, index):
        if not index.siblingAtColumn(2).isValid() or not self.parent().isColumnHidden(2):
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt = row_option(opt, index)
        title, opt.text = opt.text, ""
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        subtitle = " · ".join(dict.fromkeys(value for value in (
            index.siblingAtColumn(2).data(), index.siblingAtColumn(3).data(),
        ) if value and value not in (title, "单个视频")))
        rect = opt.rect.adjusted(8, 0, -8, 0)
        painter.save()
        painter.setFont(opt.font)
        painter.setPen(QColor(palette(opt.widget).text))
        metrics = painter.fontMetrics()
        if not subtitle:
            painter.drawText(rect, Qt.AlignVCenter, metrics.elidedText(title, Qt.ElideRight, rect.width()))
        else:
            subtitle_font = self.subtitle_font(opt.font)
            subtitle_metrics = QFontMetrics(subtitle_font)
            rect.setTop(rect.top() + max(0, (rect.height() - metrics.height() - subtitle_metrics.height()) // 2))
            rect.setHeight(metrics.height())
            painter.drawText(rect, Qt.AlignVCenter, metrics.elidedText(title, Qt.ElideRight, rect.width()))
            rect.translate(0, metrics.height())
            rect.setHeight(subtitle_metrics.height())
            painter.setFont(subtitle_font)
            painter.setPen(QColor(palette(opt.widget).muted))
            painter.drawText(rect, Qt.AlignVCenter, subtitle_metrics.elidedText(subtitle, Qt.ElideRight, rect.width()))
        painter.restore()


class _ItemSelector(QObject):
    """Compatibility facade; checkbox state lives in the table model."""
    toggled = Signal(bool)

    def __init__(self, item):
        super().__init__()
        self.item = item

    def isChecked(self):
        return self.item.checkState() == Qt.Checked

    def setChecked(self, checked):
        self.item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def isEnabled(self):
        return bool(self.item.flags() & Qt.ItemIsEnabled)

    def setToolTip(self, text):
        self.item.setToolTip(text)


class BatchDialog(AppDialog):
    """Reusable import content, also available in a standalone dialog."""

    enqueue_requested = Signal(list)
    presentation_changed = Signal()

    def __init__(
        self,
        api_client=None,
        existing_bvids: set[str] | None = None,
        existing_content_identities: set[str] | None = None,
        parent=None,
        embedded=False,
        *,
        source_discovery=None,
    ):
        super().__init__(parent)
        self._embedded = embedded
        self._source_discovery = source_discovery
        self._source_names = {}
        self._quick_source = None
        self._saved_batch_preview = None
        self._last_quick_preview = None
        self._batch_return_position = None
        self._result_focus_search = False
        self._run_sources = []
        self.setProperty("embedded", embedded)
        self._resolved_source = None
        self._request_source = None
        self._resolved_keys = ()
        self._input_keys = ()
        self._errors = []
        self._report = ImportReport()
        self._busy = False
        self._retry_base = None
        self._retry_urls = []
        self._checked_before_retry = {}
        if embedded:
            self.setWindowFlags(Qt.Widget)
        self._api_client = api_client
        existing = existing_content_identities
        if existing is None:
            existing = existing_bvids or set()
        self._existing_content_identities = {value.lower() for value in existing}
        self._inputs = []
        self._resolved_items = []
        self._selectors = []
        self._resolve_worker = None
        self._resolve_runner = None
        self.library_repository = None
        self._inventory_job = None
        self._inventory_results = []
        self._inventory_timer = QTimer(self)
        self._inventory_timer.setSingleShot(True)
        self._inventory_timer.timeout.connect(self._refresh_inventory)

        self.setWindowTitle("批量导入")
        if not embedded:
            self.setMinimumSize(700, 520)
            self.resize(820, 640)
        self._setup_ui()
        if not embedded:
            from PySide6.QtCore import QSize

            from bilibili_downloader.gui.window_bounds import ScreenBounds
            self._screen_bounds = ScreenBounds(self, QSize(700, 0))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            0, 0, 0, 0
        ) if self._embedded else layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        self.setObjectName("BatchImport")
        self._input_card = SectionCard()
        self._count_label = QLabel("0 个来源")
        self._count_label.setObjectName("StatusBadge")
        self._count_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._compact_resolve = ActionButton("重新解析")
        self._compact_resolve.setObjectName("TableSubtleButton")
        self._compact_resolve.clicked.connect(self._start_resolve)
        self._compact_resolve.hide()
        self._collapse_btn = QPushButton("收起编辑")
        self._collapse_btn.setObjectName("TableSubtleButton")
        self._collapse_btn.setCheckable(True)
        self._collapse_btn.toggled.connect(self._toggle_input)
        self._collapse_btn.hide()
        self._source_summary = ElidedLabel()
        self._source_summary.setObjectName("MetaLabel")
        self._source_summary.hide()
        self._url_text = QPlainTextEdit()
        self._url_text.setAccessibleName("批量导入链接")
        self._url_text.setFixedHeight(96)
        self._url_text.setPlaceholderText(
            "每行一个视频、番剧 ep/ss/md、合集、收藏夹或 b23.tv 短链"
        )
        self._url_text.textChanged.connect(self._refresh_input_count)
        self._resolve_btn = QPushButton("解析预览")
        self._resolve_btn.setObjectName("PrimaryButton")
        self._resolve_btn.setToolTip("解析输入的来源并预览可导入的作品")
        self._resolve_btn.clicked.connect(self._start_resolve)
        if self._source_discovery is not None:
            self._source_discovery.source_requested.connect(self._append_discovered_source)
            self._source_discovery.preview_requested.connect(self._preview_discovered_source)
            self._source_discovery.account_changed.connect(self._invalidate_account_previews)
        self._progress_area = QWidget()
        self._progress_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        progress_layout = QHBoxLayout(self._progress_area)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_copy = QVBoxLayout()
        self._progress_label = QLabel()
        self._progress_label.setObjectName("MetaLabel")
        self._progress_label.setWordWrap(True)
        progress_copy.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("ImportProgress")
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        progress_copy.addWidget(self._progress_bar)
        progress_layout.addLayout(progress_copy, 1)
        self._cancel_btn = QPushButton("取消解析")
        self._cancel_btn.clicked.connect(self.cancel_resolution)
        progress_layout.addWidget(self._cancel_btn)
        self._progress_area.hide()
        self._preview_card = SectionCard("" if self._source_discovery is not None else "作品清单")
        self._preview_card.body.setContentsMargins(16, 12, 16, 8)
        self._preview_card.body.setSpacing(6)
        self._available_label = QLabel()
        self._available_label.setObjectName("MetaLabel")
        self._available_label.hide()
        if self._source_discovery is None:
            self._preview_card.header.insertWidget(1, self._available_label)
        self._preview = RowHoverTable(0, 5)
        self._preview.setAccessibleName("批量导入作品列表")
        self._preview.setObjectName("BatchPreview")
        self._preview.setHorizontalHeaderLabels(["", "作品", "UP 主", "来源", "保存情况"])
        header = self._preview.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 44)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for column, width in ((2, 120), (3, 180)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 150)
        self._preview.verticalHeader().hide()
        self._preview.verticalHeader().setDefaultSectionSize(UI_METRICS.compact_row_height)
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._preview.setMinimumHeight(100)
        self._preview_stack = QStackedWidget()
        self._preview_stack.addWidget(self._preview)
        self._preview_card.body.addWidget(self._preview_stack, 1)
        self.selection = TableSelection(self._preview)
        self.selection.changed.connect(self._filter_results)
        self.selection_bar = SelectionBar()
        self.selection_bar.select_visible.connect(self.selection.select_visible)
        self.selection_bar.clear_requested.connect(self.selection.clear)
        self.selection_bar.review_requested.connect(self.selection.toggle_review)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索作品、作者或来源")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_results)
        self.select_unsaved = ActionButton("勾选当前未保存项")
        self.select_unsaved.clicked.connect(self._select_unsaved)
        self._preview_stack.addWidget(
            EmptyState("没有匹配的作品", action="清除搜索", callback=self.search.clear, scene="batch_filtered")
        )
        self._path_preview = ElidedLabel(elide_mode=Qt.ElideMiddle)
        self._path_preview.setObjectName("MetaLabel")
        self._preview_card.body.addWidget(self._path_preview)
        self._path_preview.hide()
        self._result_label = QLabel(self._preview_card)
        self._result_label.setObjectName("MetaLabel")
        self._result_label.setTextFormat(Qt.PlainText)
        self._result_label.setWordWrap(True)
        self._issue_btn = ActionButton("查看未解析项")
        self._issue_btn.setObjectName("TableSubtleButton")
        self._issue_btn.setProperty("warningAction", True)
        self._issue_btn.clicked.connect(self._show_errors)
        self._issue_btn.hide()
        self._preview_card.hide()
        self._notice = Notice(action="查看详情", callback=self._show_errors)
        self._notice.action.hide()
        self._action_bar = OutputActionBar("0 个任务")
        self._selected_label = self._action_bar.status
        self._output_specs = self._action_bar.specs
        self._output_directory = self._action_bar.directory
        self._footer_actions = self._action_bar.actions
        self._add_btn = self._action_bar.primary_button
        self._action_bar.submit_requested.connect(self._submit_footer)
        self._action_bar.edit_button.setVisible(self._embedded)
        if self._source_discovery is not None:
            self._setup_workspace(layout)
        else:
            self._setup_standalone_layout(layout)
        if not self._embedded:
            cancel = ActionButton("取消")
            cancel.setProperty("alwaysVisible", True)
            cancel.clicked.connect(self.reject)
            self._footer_actions.insertWidget(0, cancel)
        layout.addWidget(self._action_bar)
        self._sync_source_discovery()
        self._refresh_input_count()

    def _setup_standalone_layout(self, layout):
        self._input_card.body.setContentsMargins(16, 12, 16, 12)
        self._input_card.body.setSpacing(10)
        self._input_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header = self._input_card.header
        header.addWidget(self._count_label)
        header.insertWidget(1, self._source_summary, 1)
        header.addWidget(self._compact_resolve)
        header.addWidget(self._collapse_btn)
        self._input_card.body.addLayout(header)
        self._input_card.body.addWidget(self._url_text)
        input_row = QHBoxLayout()
        input_row.addStretch()
        input_row.addWidget(self._resolve_btn)
        self._input_card.body.addLayout(input_row)
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.select_unsaved)
        self._preview_card.body.insertWidget(1, self.selection_bar)
        self._preview_card.body.insertLayout(1, filters)
        results = QHBoxLayout()
        results.addWidget(self._result_label, 1)
        results.addWidget(self._issue_btn)
        self._preview_card.body.addLayout(results)
        layout.addWidget(self._input_card)
        layout.addWidget(self._progress_area)
        layout.addWidget(self._preview_card, 1)
        layout.addWidget(self._notice)
        self._empty_space = QWidget()
        self._empty_space.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._empty_space, 1)

    def _setup_workspace(self, layout):
        layout.setSpacing(0)
        self._stages = QStackedWidget()
        self._stages.addWidget(self._source_discovery)
        self._stages.addWidget(self._preview_card)
        layout.addWidget(self._stages, 1)
        self._resolve_btn.setParent(self._input_card)
        self._resolve_btn.hide()
        self._input_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._input_card.body.setContentsMargins(0, 4, 0, 0)
        self._input_card.body.setSpacing(6)
        self._count_label.setObjectName("MetaLabel")
        self._input_card.body.addWidget(self._url_text)
        self._input_card.body.addWidget(self._count_label)
        self._input_card.body.addStretch(1)
        self._source_discovery.set_link_editor(self._input_card)
        self._url_text.installEventFilter(self)
        self._url_text.setMinimumHeight(104)
        self._url_text.setMaximumHeight(240)

        self._collapse_btn.setText("返回来源")
        self._collapse_btn.setAutoDefault(False)
        self._source_summary.setObjectName("SectionTitle")
        self._preview_card.header.insertWidget(0, self._collapse_btn)
        self._preview_card.header.insertWidget(1, self._source_summary, 1)
        self._preview_card.header.setSpacing(8)
        self._preview_card.body.insertLayout(0, self._preview_card.header)
        self._preview_card.body.setContentsMargins(16, 2, 16, 0)
        self._preview_card.body.setSpacing(4)
        actions = ResponsiveActions()
        self._retry_btn = ActionButton("重试失败项")
        self._retry_btn.clicked.connect(self._retry_failed)
        self._retry_btn.hide()
        for button in (self._issue_btn, self._retry_btn, self._compact_resolve):
            button.setObjectName("TableSubtleButton")
            button.setAutoDefault(False)
            actions.row.addWidget(button)
        self._issue_btn.setProperty("actionPriority", 80)
        self._retry_btn.setProperty("actionPriority", 70)
        self._preview_card.header.addWidget(actions)

        self._preview_toolbar = QWidget()
        toolbar = QHBoxLayout(self._preview_toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        toolbar.addWidget(self.search, 1)
        self.selection_bar.summary.setWordWrap(False)
        self.selection_bar.summary.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.select_unsaved.setObjectName("TableSubtleButton")
        self.select_unsaved.setText("勾选未保存")
        self.selection_bar.action_strip.row.addWidget(self.select_unsaved)
        toolbar.addWidget(self.selection_bar, 2)
        self._preview_card.body.insertWidget(1, self._preview_toolbar)
        self._preview_card.body.insertWidget(2, self._progress_area)
        self._cancel_btn.hide()
        self._empty_result = QLabel()
        self._empty_result.setObjectName("MetaLabel")
        self._empty_result.setAlignment(Qt.AlignCenter)
        self._empty_result.setWordWrap(True)
        self._preview_stack.addWidget(self._empty_result)
        self._preview_card.body.insertWidget(3, self._notice)
        self._result_label.hide()
        self._preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._preview.setItemDelegateForColumn(1, _PreviewTitleDelegate(self._preview))
        self._preview.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.search.installEventFilter(self)
        self._preview.installEventFilter(self)

        self._draft_button = ActionButton("待解析 0")
        self._draft_button.setObjectName("OutputSecondaryButton")
        self._draft_button.clicked.connect(self._show_draft)
        self._action_bar.row.insertWidget(0, self._draft_button)
        self._action_bar.edit_button.setText("下载设置")
        self._action_bar.edit_button.setProperty("alwaysVisible", True)

    @property
    def preview_ready(self):
        visible = self._source_discovery is None or self._collapse_btn.isChecked()
        return bool(visible and not self._busy and self._resolved_items and self._source_matches())

    def set_output_summary(self, specs, directory):
        self._output_specs.set_full_text(specs)
        self._output_directory.set_full_text(directory, copy_value=directory.removeprefix("保存至 "))
        self._path_cache_rows = None
        self.update_path_previews()
        self.schedule_inventory()

    def update_path_previews(self):
        factory = getattr(self, "output_item_factory", None)
        if factory is None:
            return
        from pathlib import Path
        if (getattr(self, "_path_cache_rows", None) is None
                or self._path_cache_infos is not self._resolved_items
                or self._path_cache_factory != factory):
            self._path_cache_rows = []
            self._path_cache_infos, self._path_cache_factory = self._resolved_items, factory
            for row, info in enumerate(self._resolved_items):
                pages = [info.for_page(p) for p in info.pages] if info.is_multi_part else [info]
                items = [factory(page) for page in pages]
                relative = [item.relative_output_path for item in items]
                paths = [str(Path(item.output_dir) / path) for item, path in zip(items, relative)]
                self._path_cache_rows.append((info.content_identity, len(items), relative[0].as_posix(), paths[0]))
                cell = self._preview.item(row, 1)
                if cell is not None:
                    cell.setToolTip(info.title + f"\n展开为 {len(items)} 个任务\n" + "\n".join(paths[:5]) + ("\n…" if len(paths) > 5 else ""))
        count, first, full = 0, "", ""
        selected = self.selection.state.selected
        for identity, task_count, relative, absolute in self._path_cache_rows:
            if identity in selected:
                count += task_count
                first, full = first or relative, full or absolute
        self._path_preview.set_full_text(f"路径示例：{first}" if count else "选择作品后预览保存路径")
        self._path_preview.setToolTip(full)

    def _toggle_input(self, collapsed):
        if self._source_discovery is not None:
            if not collapsed and not self._busy:
                if self._quick_source is not None:
                    self._restore_batch_preview()
                else:
                    self._batch_return_position = self._snapshot_preview()
            self._sync_source_discovery()
            self._update_footer()
            if not collapsed and not self._busy:
                self._sync_result_feedback()
                self._source_discovery.restore_position()
            self.presentation_changed.emit()
            return
        self._url_text.setVisible(not collapsed)
        self._resolve_btn.setVisible(not collapsed)
        self._source_summary.setVisible(collapsed)
        self._count_label.setVisible(not collapsed)
        self._compact_resolve.setVisible(collapsed)
        self._collapse_btn.setText("编辑来源" if collapsed else "收起编辑")
        self._sync_source_discovery()
        if self._resolved_items:
            visible = collapsed or self.height() >= 540
            self._preview_card.setVisible(visible)
            self._empty_space.setVisible(not visible)

    def _sync_source_discovery(self):
        if self._source_discovery is None:
            return
        previewing = self._collapse_btn.isChecked()
        self._stages.setCurrentWidget(self._preview_card if previewing or self._busy else self._source_discovery)
        self._collapse_btn.setVisible(previewing and not self._busy)
        self._source_summary.show()
        self._compact_resolve.setVisible(previewing and not self._busy and self._source_matches() and not self._report.issues)
        self._preview_toolbar.setVisible(bool(self._resolved_items) and (self._busy or self._source_matches()))
        self._action_bar.set_batch_output_visible(self.preview_ready)

    def show_link_editor(self):
        if self._busy:
            return False
        self._collapse_btn.setChecked(False)
        if self._source_discovery is not None:
            self._source_discovery.show_link_editor()
        self._url_text.setFocus()
        return True

    def _active_source_text(self):
        return self._quick_source.url if self._quick_source is not None else self._url_text.toPlainText()

    def _source_matches(self):
        if self._source_discovery is None:
            return self._resolved_source == self._active_source_text()
        keys = (batch_source_key(self._quick_source.url),) if self._quick_source is not None else self._input_keys
        return self._resolved_source is not None and self._resolved_keys == keys

    def _invalidate_account_previews(self):
        popup = self.findChild(QDialog, "BatchDraftPopup")
        if popup is not None and popup.isVisible():
            popup.reject()
        self._source_names.clear()
        self._last_quick_preview = self._saved_batch_preview = self._batch_return_position = None
        if not self._busy and self._resolved_source is None:
            return
        self.cancel_resolution()
        self._resolve_worker = None
        self._request_source = self._quick_source = self._retry_base = None
        self._checked_before_retry = {}
        with QSignalBlocker(self.search):
            self.search.clear()
        self.selection.state.reviewing = False
        self._render_report(ImportReport(), None, {}, reveal=False)

    def _append_discovered_source(self, source):
        if self._busy or self._collapse_btn.isChecked():
            return
        url, key = source.url, batch_source_key(source.url)
        self._source_names[key] = source.title
        self.add_source_link(url)

    def add_source_link(self, url):
        draft = self._url_text.toPlainText()
        key = batch_source_key(url)
        if url in draft.splitlines() or (key is not None and any(batch_source_key(line) == key for line in self._inputs)):
            return
        cursor = self._url_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(("\n" if draft and not draft.endswith("\n") else "") + url)

    def _preview_discovered_source(self, source):
        if self._busy or self._api_client is None or self._collapse_btn.isChecked():
            return
        self._saved_batch_preview = self._snapshot_preview()
        self._quick_source = source
        self._resolved_source = None
        last = self._last_quick_preview
        if last is not None and last.source_text and batch_source_key(last.source_text) == batch_source_key(source.url):
            self._source_discovery.remember_position()
            self._restore_preview(last, reveal=True)
            return
        with QSignalBlocker(self.search):
            self.search.clear()
        self._begin_resolve([source.url])

    def _selection_choices(self):
        return {info.content_identity: selector.isChecked() for info, selector in zip(self._resolved_items, self._selectors)}

    def _snapshot_preview(self):
        return _BatchPreview(
            self._report, self._resolved_source, self._selection_choices(),
            self.search.text(), self.selection.state.reviewing,
            self.selection.state.focused, self._preview.verticalScrollBar().value(),
            self._result_focus_search,
        )

    def _restore_batch_preview(self):
        if self._quick_source is None:
            return
        self._last_quick_preview = self._snapshot_preview()
        saved, self._saved_batch_preview = self._saved_batch_preview, None
        self._quick_source = None
        self._request_source = None
        self._restore_preview(saved, reveal=False)

    def _restore_preview(self, saved, *, reveal):
        with QSignalBlocker(self.search):
            self.search.setText(saved.filter_text)
        self.selection.state.reviewing = saved.reviewing
        self._render_report(saved.report, saved.source_text, saved.choices, reveal=reveal)
        self._restore_result_position(saved, focus=reveal)

    def _restore_result_position(self, saved, *, focus):
        items = self._resolved_items

        def restore():
            if self._resolved_items is not items or self._busy:
                return
            if saved.focused is not None:
                row = next((row for row, info in enumerate(items) if info.content_identity == saved.focused), None)
                if row is not None and not self._preview.isRowHidden(row):
                    self._preview.setCurrentCell(row, 1)
            self._preview.verticalScrollBar().setValue(saved.scroll)
            if focus and (saved.focus_search or saved.focused is not None):
                (self.search if saved.focus_search else self._preview).setFocus()

        QTimer.singleShot(0, self, restore)

    def _source_title(self, url):
        if self._quick_source is not None and self._quick_source.url == url:
            return self._quick_source.title
        return self._source_names.get(batch_source_key(url), url)

    def _draft_title(self, url):
        name = self._source_title(url)
        if name != url:
            return name
        key = batch_source_key(url)
        if not key:
            return url
        kind, identifier, *_ = key
        label = {"season": "合集", "series": "系列", "favorite": "收藏夹",
                 "ep": "番剧单集", "ss": "番剧季度", "md": "番剧媒体"}.get(kind)
        return f"{label} {identifier}" if label else url

    def _show_draft(self):
        self._source_names.update(self._source_discovery.known_source_titles(self._inputs))
        popup = QDialog(self, Qt.Popup)
        popup.setObjectName("BatchDraftPopup")
        popup.setAccessibleName("待解析清单")
        popup.setAttribute(Qt.WA_DeleteOnClose)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        heading = QLabel("待解析清单")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        sources = QWidget()
        rows = QVBoxLayout(sources)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)
        scroll = scroll_area(sources)
        layout.addWidget(scroll)

        def refresh(focus=0):
            while rows.count():
                entry = rows.takeAt(0)
                if entry.widget() is not None:
                    entry.widget().hide()
                    entry.widget().deleteLater()
            buttons = []
            for index, url in enumerate(self._inputs):
                title = self._draft_title(url)
                item = QWidget()
                row = QHBoxLayout(item)
                row.setContentsMargins(0, 0, 0, 0)
                name = ElidedLabel(title)
                name.setToolTip(url)
                row.addWidget(name, 1)
                remove = ActionButton("移除")
                remove.setAutoDefault(False)
                remove.setObjectName("TableSubtleButton")
                remove.setAccessibleName(f"移除 · {title}")
                remove.clicked.connect(lambda _checked=False, value=url, pos=index: remove_source(value, pos))
                row.addWidget(remove)
                buttons.append(remove)
                rows.addWidget(item)
                item.show()
            if not buttons:
                empty = QLabel("尚未添加来源")
                rows.addWidget(empty)
                empty.show()
            rows.addStretch()
            anchor = self._draft_button.mapToGlobal(QPoint(0, -6))
            bounds = self.window().frameGeometry()
            margins = layout.contentsMargins()
            row_height = max(36, popup.fontMetrics().height() + 12)
            content_height = row_height + (row_height + rows.spacing()) * max(0, len(buttons) - 1)
            requested = (margins.top() + margins.bottom() + heading.sizeHint().height()
                         + layout.spacing() + max(content_height, rows.sizeHint().height()) + 8)
            height = max(60, min(324, requested, anchor.y() - bounds.top() - 8))
            popup.setFixedSize(min(420, bounds.width() - 32), height)
            popup.move(anchor.x(), anchor.y() - height)
            if buttons:
                target = buttons[min(focus, len(buttons) - 1)]
                target.setFocus()
                scroll.ensureWidgetVisible(target)

        def remove_source(url, index):
            key = batch_source_key(url)
            remaining = "".join(line for line in self._url_text.toPlainText().splitlines(keepends=True)
                                if batch_source_key(line) != key)
            cursor = self._url_text.textCursor()
            cursor.select(QTextCursor.Document)
            cursor.insertText(remaining)
            refresh(index)

        popup.finished.connect(lambda _: self._draft_button.setFocus())
        popup.show()
        refresh()

    def resizeEvent(self, event):
        if self._resolved_items and self._source_discovery is None:
            self._toggle_input(self._collapse_btn.isChecked())
        self._size_preview_columns()
        super().resizeEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "_preview"):
            self._size_preview_columns()

    def eventFilter(self, watched, event):
        if (watched is self._url_text and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and event.modifiers() & Qt.ControlModifier):
            if not event.isAutoRepeat():
                self._add_btn.click()
            return True
        if watched in (self.search, self._preview) and event.type() == QEvent.FocusIn:
            self._result_focus_search = watched is self.search
        return super().eventFilter(watched, event)

    def _size_preview_columns(self):
        header = self._preview.horizontalHeader()
        if self._source_discovery is None:
            header.resizeSection(2, 112 if self.width() < 900 else 152)
            header.resizeSection(3, 148 if self.width() < 900 else 180)
            return
        metrics = self._preview.fontMetrics()
        narrow = self.width() < max(900, metrics.horizontalAdvance("保存情况") * 17)
        self._preview.setColumnHidden(2, narrow)
        self._preview.setColumnHidden(3, narrow or not getattr(self, "_multiple_sources", False))
        subtitle_height = QFontMetrics(_PreviewTitleDelegate.subtitle_font(self._preview.font())).height() if narrow else 0
        self._preview.verticalHeader().setDefaultSectionSize(max(37, metrics.height() + subtitle_height + 1))
        header.resizeSection(4, max(96, metrics.horizontalAdvance("部分已保存") + 24))

    def _selection_updated(self):
        self._update_footer()
        self.update_path_previews()
        if self._inventory_results:
            from bilibili_downloader.gui.threads.inventory_worker import (
                inventory_summary,
            )
            groups = [group for group, selector in zip(self._inventory_results, self._selectors) if selector.isChecked()]
            self._result_label.setText(inventory_summary(groups) if groups else "")
        else:
            self._result_label.setText("")
        if self._source_discovery is None:
            self._result_label.setVisible(bool(self._result_label.text()))

    def _update_footer(self):
        selected = self.get_video_infos()
        task_count = sum(len(info.pages) if info.is_multi_part else 1 for info in selected)
        if self._source_discovery is None:
            status = f"{task_count} 个任务"
            action = f"加入队列（{task_count} 项）" if task_count else "加入队列"
            enabled = bool(selected) and self.preview_ready
        else:
            count = len(self._inputs)
            self._draft_button.setVisible(not self._busy and not self._collapse_btn.isChecked())
            self._draft_button.setText(f"待解析 {count}")
            self._draft_button.setAccessibleName(f"待解析 {count} 个来源，打开清单")
            if self._busy:
                stopping = self._resolve_worker is not None and self._resolve_worker.cancel.is_set()
                status, action, enabled = "正在解析来源", "正在停止…" if stopping else "取消解析", not stopping
            elif self.preview_ready:
                status = f"已选 {len(selected)} 个作品 · {task_count} 个任务"
                action = f"加入队列（{task_count} 项）" if task_count else "加入队列"
                enabled = bool(selected)
            elif self._collapse_btn.isChecked() and self._source_matches():
                status = "暂无可预览作品"
                retry = self._can_retry()
                action = "重试失败项" if retry else "重新预览"
                enabled = self._api_client is not None and (self._quick_source is not None or bool(count))
            else:
                status = ""
                action = "查看上次预览" if count and self._source_matches() else f"预览 {count} 个来源" if count else "预览来源"
                enabled = bool(count) and self._api_client is not None
        self._selected_label.setText(status)
        self._selected_label.setVisible(bool(status))
        self._add_btn.setText(action)
        self._add_btn.setEnabled(enabled)

    def _submit_footer(self):
        if self._source_discovery is None or self.preview_ready:
            self.accept()
        elif self._busy:
            self.cancel_resolution()
        elif not self._collapse_btn.isChecked() and self._source_matches():
            self._source_discovery.remember_position()
            self._collapse_btn.setChecked(True)
            self._sync_result_feedback()
            if self._batch_return_position is not None:
                self._restore_result_position(self._batch_return_position, focus=True)
        elif self._collapse_btn.isChecked() and self._can_retry():
            self._retry_failed()
        else:
            self._start_resolve()

    def _refresh_input_count(self):
        valid, invalid = classify_batch_inputs(self._url_text.toPlainText())
        self._inputs = valid
        self._input_keys = tuple(map(batch_source_key, valid))
        if self._source_discovery is not None:
            self._source_discovery.set_selected_sources(valid)
        if self._resolved_source is not None:
            stale = not self._source_matches()
            if stale:
                self._inventory_timer.stop()
                if self._inventory_job is not None:
                    self._inventory_job.cancel()
                if self._source_discovery is not None and not self._busy:
                    self._collapse_btn.setChecked(False)
            self._sync_result_feedback()
            if self._source_discovery is None:
                self._result_label.setVisible(not stale)
            self._selection_updated()
        else:
            self._update_footer()
        self._refresh_source_summary()
        if self._source_discovery is not None:
            self._count_label.setText(f"{len(invalid)} 行无法识别，已保留供修改。" if invalid else "")
            self._count_label.setVisible(bool(invalid))
        elif invalid:
            self._count_label.setText(
                f"{len(valid)} 个来源 · {len(invalid)} 行无法识别"
            )
        else:
            self._count_label.setText(f"{len(valid)} 个来源")
        if self._source_discovery is not None and self._collapse_btn.isChecked():
            self.presentation_changed.emit()

    def _refresh_source_summary(self):
        raw = self._active_source_text()
        if self._source_discovery is None:
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
        else:
            lines = [self._quick_source.url] if self._quick_source is not None else self._inputs
        title = self._source_title if self._source_discovery is None else self._draft_title
        source = title(lines[0]) if lines else "尚未添加来源"
        if len(lines) > 1:
            source += f" 等 {len(lines)} 个来源"
        names = {
            info.collection_title or info.season_title or info.series_title
            for info in self._resolved_items
        }
        if self._quick_source is not None:
            source = f"单个来源 · {self._quick_source.title}"
        elif self._source_discovery is not None and len(lines) > 1:
            source = f"批量预览 · {len(lines)} 个来源"
        elif self._source_matches() and len(names) == 1 and next(iter(names)):
            source = next(iter(names))
            if lines and self._source_discovery is None:
                source += f" · {len(lines)} 个来源"
        elif self._source_discovery is not None and self._source_matches() and len(self._resolved_items) == 1:
            source = self._resolved_items[0].title
        self._source_summary.set_full_text(source)
        self._source_summary.setToolTip(raw)

    def _start_resolve(self):
        if self._busy:
            return
        self._refresh_input_count()
        sources = [self._quick_source.url] if self._quick_source is not None else self._inputs
        if not sources:
            self._notice.set_message("没有可解析的 B 站来源", "warning")
            return
        if self._api_client is None:
            self._notice.set_message("当前没有可用的 API 客户端", "danger")
            return
        self._begin_resolve(sources)

    def _begin_resolve(self, sources, *, retry=False):
        if self._source_discovery is not None:
            self._source_names.update(self._source_discovery.known_source_titles(sources))
            if not self._collapse_btn.isChecked():
                self._source_discovery.remember_position()
        self._busy = True
        self._run_sources = list(sources)
        self._retry_position = self._snapshot_preview() if retry and self._source_discovery is not None else None
        self._retry_base = self._report if retry else None
        self._retry_urls = sources if retry else []
        self._checked_before_retry = (
            {
                info.content_identity: selector.isChecked()
                for info, selector in zip(self._resolved_items, self._selectors)
            }
            if retry
            else {}
        )
        self._request_source = self._active_source_text()
        self._refresh_source_summary()
        self._notice.set_message("")
        self._notice.action.hide()
        self._issue_btn.hide()
        if self._source_discovery is not None:
            self._retry_btn.hide()
        self._add_btn.setEnabled(False)
        self._resolve_btn.setEnabled(False)
        self._compact_resolve.setEnabled(False)
        self._resolve_btn.setText("解析中…")
        self._result_label.setText("正在读取来源内容与分页…")
        self._progress_area.show()
        self._progress_bar.setRange(0, 0)
        self._progress_label.setText("正在准备解析…")
        self._cancel_btn.setText("取消解析")
        self._cancel_btn.setEnabled(True)
        if not retry:
            if not self._source_matches():
                with QSignalBlocker(self.search):
                    self.search.clear()
            self._resolved_items = []
            self._selectors = []
            self._preview.setRowCount(0)
            self.selection.state.reviewing = False
            self.selection.reset([], preserve=False)
            self.selection.set_visible([])
            self.selection_bar.update_state(self.selection.state)
            if self._source_discovery is None:
                self._preview_card.hide()
                self._empty_space.show()
            self._collapse_btn.setChecked(False)
            self._collapse_btn.hide()
            self._filter_results()
        self._resolve_worker = SourceResolveWorker()
        self._resolve_worker.completed.connect(self._on_worker_report)
        self._resolve_worker.progress.connect(self._on_progress)
        self._resolve_runner = SourceResolveRunner(
            self._resolve_worker, self._api_client, sources
        )
        self._sync_source_discovery()
        self._update_footer()
        if self._source_discovery is not None:
            self._sync_result_feedback()
        QThreadPool.globalInstance().start(self._resolve_runner)
        self.presentation_changed.emit()

    def _on_progress(self, progress):
        if (not self._busy or self._resolve_worker is None or self._resolve_worker.cancel.is_set()
                or (self.sender() is not None and self.sender() is not self._resolve_worker)):
            return
        completed, total = progress["completed"], progress["total"]
        self._progress_bar.setRange(0, total)
        if total:
            self._progress_bar.setValue(completed)
        number = f" · {completed}/{total}" if total else ""
        index = progress["source_index"]
        source = self._run_sources[index - 1] if 0 < index <= len(self._run_sources) else ""
        name = self._source_title(source)
        self._progress_label.setText(
            f"来源 {index}/{progress['sources']} · {name if name != source else progress['source']}\n"
            f"{progress['stage']}{number} · 已解析 {progress['items']} 个作品"
        )
        self._progress_label.setToolTip(progress["source"])

    def cancel_resolution(self):
        if self._busy and self._resolve_worker:
            self._resolve_worker.cancel.set()
            self._cancel_btn.setEnabled(False)
            self._progress_label.setText("正在结束请求，保留已解析作品…")
            if self._source_discovery is not None:
                self._update_footer()

    def reject(self):
        self.cancel_resolution()
        super().reject()

    def closeEvent(self, event):
        self.cancel_resolution()
        super().closeEvent(event)

    def _on_resolved(self, items: list, errors: list):
        """Compatibility entry point for older callers and offline previews."""
        self._on_report(
            ImportReport(
                items=items, issues=[ImportIssue("", error) for error in errors]
            )
        )

    @Slot(object)
    def _on_worker_report(self, report):
        if self.sender() is self._resolve_worker:
            self._on_report(report)

    def _on_report(self, report):
        self._resolve_worker = None
        source_text = self._request_source if self._request_source is not None else self._active_source_text()
        previous_choices = self._selection_choices() if self._source_matches() else {}
        retry_position = getattr(self, "_retry_position", None)
        self._retry_position = None
        if self._retry_base is not None:
            base = self._retry_base
            original_issues = {
                issue.url or issue.source: issue for issue in base.issues
            }
            report.issues = [
                ImportIssue(
                    issue.source,
                    issue.message,
                    issue.url,
                    original_issues[issue.url or issue.source].title,
                    "item",
                )
                if (issue.url or issue.source) in original_issues
                and original_issues[issue.url or issue.source].kind == "item"
                else issue
                for issue in report.issues
            ]
            items = {item.content_identity: item for item in base.items}
            for item in report.items:
                items.setdefault(item.content_identity, item)
            # Cancelled retries retain prior failures until they are resolved.
            completed = set(report.completed_sources)
            if not report.cancelled:
                completed.update(self._retry_urls)
            succeeded = set()
            succeeded.update(
                f"https://www.bilibili.com/video/{item.bvid}"
                for item in report.items
                if item.bvid
            )
            succeeded.update(item.bvid for item in report.items if item.bvid)
            succeeded.update(
                f"ep{item.episode_id}" for item in report.items if item.episode_id
            )
            issues = [
                issue
                for issue in base.issues
                if (issue.url or issue.source) not in completed | succeeded
            ]

            def issue_key(issue):
                return (issue.url or issue.source, issue.title, issue.kind)

            retained = Counter(issue_key(issue) for issue in issues)
            incoming = Counter()
            for issue in report.issues:
                key = issue_key(issue)
                incoming[key] += 1
                if incoming[key] > retained[key]:
                    issues.append(issue)
            report = ImportReport(
                list(items.values()),
                issues,
                base.duplicates + report.duplicates,
                report.cancelled,
                report.completed_sources,
            )
        self._retry_base = None
        choices = {**self._checked_before_retry, **previous_choices}
        self._checked_before_retry = {}
        self._request_source = None
        self._render_report(report, source_text, choices)
        if retry_position is not None:
            self._restore_result_position(retry_position, focus=False)

    def _render_report(self, report, source_text, choices, *, reveal=True):
        self._report = report
        self._busy = False
        self._progress_area.hide()
        self._resolve_btn.setEnabled(True)
        self._compact_resolve.setEnabled(True)
        self._compact_resolve.setText("重新预览" if self._source_discovery is not None else "重新解析")
        self._resolve_btn.setText("重新解析")
        self._resolved_source = source_text
        self._resolved_keys = tuple(map(batch_source_key, classify_batch_inputs(source_text or "")[0]))
        self._errors = [
            f"{issue.title or issue.source}：{issue.message}" for issue in report.issues
        ]
        items = report.items
        self._preview.blockSignals(True)
        self._resolved_items = items
        self._preview.setRowCount(len(items))
        self._selectors = []
        duplicate_count = 0
        for row, info in enumerate(items):
            check_item = QTableWidgetItem("")
            check_item.setData(Qt.UserRole, info.content_identity)
            check_item.setFlags(check_item.flags() | Qt.ItemIsUserCheckable)
            self._preview.setItem(row, 0, check_item)
            selector = _ItemSelector(check_item)
            duplicate = (
                info.content_identity.lower() in self._existing_content_identities
            )
            selector.setChecked(choices.get(info.content_identity, info.is_main_section))
            if duplicate:
                duplicate_count += 1
                selector.setToolTip("任务中心已有同源作品，将按当前规格进一步去重")
            title_item = QTableWidgetItem(info.title)
            title_item.setToolTip(info.title)
            self._preview.setItem(row, 1, title_item)
            author_item = QTableWidgetItem(info.author)
            author_item.setToolTip(info.author)
            self._preview.setItem(row, 2, author_item)
            if info.episode_id:
                source = " · ".join(
                    value
                    for value in (
                        info.series_title,
                        info.season_title,
                        info.section_title or "正片",
                    )
                    if value
                )
            else:
                source = info.collection_title or "单个视频"
            if duplicate:
                source = f"{source} · 已有同源任务"
            source_item = QTableWidgetItem(source)
            source_item.setToolTip(source)
            self._preview.setItem(row, 3, source_item)
            title_item.setData(Qt.AccessibleDescriptionRole, " · ".join(filter(None, (info.author, source))))
            self._preview.setItem(row, 4, QTableWidgetItem("待核对"))
            self._selectors.append(selector)

        self._preview.blockSignals(False)
        self.selection.state.selected = {info.content_identity for info, selector in zip(items, self._selectors) if selector.isChecked()}
        self.selection.reset([info.content_identity for info in items])
        self._existing_duplicates = duplicate_count
        self._available_label.setText(f"{len(items)} 项")
        sources = {self._preview.item(row, 3).text() for row in range(len(items))}
        self._multiple_sources = len(sources) > 1
        if self._source_discovery is None:
            self._preview.setColumnHidden(3, len(sources) == 1)
        else:
            self._size_preview_columns()
        self._result_label.setText(self._report_summary())
        self._result_label.setToolTip("\n".join(self._errors))
        if self._source_discovery is None:
            self._result_label.setVisible(self._source_matches())
            self._preview_card.setVisible(bool(items))
            self._empty_space.setVisible(not bool(items))
            self._collapse_btn.setVisible(bool(items))
        self._collapse_btn.setChecked(
            reveal and (bool(items) or self._source_discovery is not None)
            and self._source_matches()
        )
        self._sync_source_discovery()
        self._selection_updated()
        self._refresh_source_summary()
        self._sync_result_feedback()
        self._filter_results()
        self.schedule_inventory()
        self.presentation_changed.emit()

    def _filter_results(self, *_):
        query = self.search.text().strip().casefold()
        state = self.selection.state
        visible_ids = []
        for row, info in enumerate(self._resolved_items):
            text = " ".join(self._preview.item(row, col).text() for col in (1, 2, 3))
            visible = info.content_identity in state.selected if state.reviewing else query in text.casefold()
            self._preview.setRowHidden(row, not visible)
            if visible:
                visible_ids.append(info.content_identity)
        self.selection.set_visible(visible_ids)
        empty_result = self._source_discovery is not None and not self._resolved_items
        self._preview_stack.setCurrentIndex(2 if empty_result else 0 if visible_ids else 1)
        self.search.setEnabled(not state.reviewing)
        self.selection_bar.update_state(state)
        if self._source_discovery is not None:
            summary = f"共 {len(state.order)} 个作品"
            if len(state.visible) != len(state.order):
                summary = f"显示 {len(state.visible)} / {len(state.order)} 个作品"
            if self._report.cancelled and not self._busy and state.order:
                if len(state.visible) == len(state.order):
                    summary = f"保留 {len(state.order)} 个作品"
                summary = f"已取消 · {summary}"
            if state.outside and not state.reviewing:
                summary += f" · 筛选外已选 {state.outside} 个"
            self.selection_bar.summary.setText(summary)
            self.selection_bar.summary.setToolTip(summary)
        self._available_label.setText(f"共 {len(self._resolved_items)} 个作品")
        self._selection_updated()

    def schedule_inventory(self):
        self._inventory_results = []
        if self._inventory_job is not None:
            self._inventory_job.cancel()
        pending = bool(self._resolved_items and self.library_repository is not None
                       and getattr(self, "output_item_factory", None))
        self._result_label.setText("正在核对已有文件…" if pending else "")
        if self._source_discovery is None:
            self._result_label.setVisible(pending)
        self._inventory_timer.start(150)

    def _refresh_inventory(self):
        from bilibili_downloader.gui.threads.inventory_worker import (
            InventoryMatchRunner,
        )
        factory = getattr(self, "output_item_factory", None)
        if factory is None or self.library_repository is None or not self._resolved_items or not self._source_matches():
            return
        if self._inventory_job is not None:
            self._inventory_timer.start(150)
            return
        snapshot = self._resolved_items
        groups = [[factory(info.for_page(page)) for page in info.pages] or [factory(info)] for info in snapshot]
        fingerprints = [[item.fingerprint for item in group] for group in groups]
        job = InventoryMatchRunner(self.library_repository, groups)
        self._inventory_job = job
        self.select_unsaved.setEnabled(False)
        for row in range(self._preview.rowCount()):
            self._preview.item(row, 4).setText("正在核对…")

        def finished(result):
            self._inventory_job = None
            from shiboken6 import isValid
            if not isValid(self):
                return
            self.select_unsaved.setEnabled(True)
            if snapshot is not self._resolved_items or not self._source_matches():
                return
            current = [[factory(info.for_page(page)) for page in info.pages] or [factory(info)] for info in snapshot]
            if fingerprints != [[item.fingerprint for item in group] for group in current]:
                self.schedule_inventory()
                return
            if isinstance(result, Exception):
                self._notice.set_message("已有文件待核对，可继续加入任务；下载时将再次确认。", "warning")
                self._result_label.clear()
                self._result_label.hide()
                for row in range(self._preview.rowCount()):
                    self._preview.item(row, 4).setText("待确认")
                return
            self._inventory_results = result
            for row, group in enumerate(result):
                self._preview.item(row, 4).setText(group.label)
                self._preview.item(row, 4).setToolTip(group.label)
            self._selection_updated()
            self._sync_result_feedback()

        job.signals.finished.connect(finished)
        QThreadPool.globalInstance().start(job)

    def _select_unsaved(self):
        if not self._inventory_results:
            self._notice.set_message("正在核对已有文件…")
            self.schedule_inventory()
            return
        for row, (info, group) in enumerate(zip(self._resolved_items, self._inventory_results)):
            if not self._preview.isRowHidden(row) and not group.saved:
                self.selection.state.selected.add(info.content_identity)
        self.selection._paint_checks()
        self._filter_results()
        self._sync_result_feedback()

    def _sync_result_feedback(self):
        items = self._resolved_items
        if self._source_discovery is not None:
            active = not self._busy and self._collapse_btn.isChecked() and self._source_matches()
            self._issue_btn.setVisible(active and bool(self._errors))
            self._issue_btn.setText(f"问题详情（{len(self._errors)}）")
            self._issue_btn.setToolTip(self._report_summary())
            self._retry_btn.setVisible(active and bool(items) and self._can_retry())
            if self._busy:
                self._empty_result.setText("正在读取作品…")
            elif self._report.cancelled:
                self._empty_result.setText("解析已取消，暂无已解析的作品。")
            elif self._errors:
                reason = self._report.issues[0].message.partition("\n")[0]
                self._empty_result.setText(f"未能解析出作品。\n{reason}")
            else:
                self._empty_result.setText("所选来源没有可解析的作品。")
            self._notice.set_message("")
            self._notice.action.hide()
            return
        self._issue_btn.setVisible(bool(items and self._errors))
        self._issue_btn.setText(f"未解析（{len(self._errors)}）")
        self._issue_btn.setAccessibleName(f"查看 {len(self._errors)} 项未解析内容及重试入口")
        self._issue_btn.setToolTip(self._report_summary())
        if self._resolved_source is not None and self._resolved_source != self._active_source_text():
            self._issue_btn.hide()
            self._notice.set_message("来源已改，请重新解析后加入任务。", "warning")
            self._notice.action.setVisible(bool(self._errors))
        elif self._source_discovery is not None and not self._collapse_btn.isChecked():
            self._notice.set_message("")
        elif self._errors and not items:
            self._notice.set_message(self._report_summary(), "warning")
            self._notice.action.show()
        else:
            message = ""
            if self._report.cancelled:
                message = f"解析已取消，保留 {len(items)} 个作品。" if items else "解析已取消。"
            elif not items and self._resolved_source is not None:
                message = "所选来源没有可解析的作品。"
            self._notice.set_message(message)
            self._notice.action.hide()

    def _report_summary(self):
        items = sum(issue.kind == "item" for issue in self._report.issues)
        sources = sum(issue.kind == "source" for issue in self._report.issues)
        parts = (["已取消"] if self._report.cancelled else []) + [
            f"成功 {len(self._report.items)} 项"
        ]
        if items:
            parts.append(f"跳过 {items} 项")
        if sources:
            parts.append(f"来源失败 {sources} 个")
        if self._report.duplicates:
            parts.append(f"合并重复 {self._report.duplicates} 项")
        if getattr(self, "_existing_duplicates", 0):
            parts.append(f"已有同源 {self._existing_duplicates} 项（加入时按规格去重）")
        return " · ".join(parts)

    def _failed_urls(self):
        return list(
            dict.fromkeys(
                issue.url or issue.source
                for issue in self._report.issues
                if issue.url or issue.source
            )
        )

    def _can_retry(self):
        return bool(self._api_client is not None and classify_batch_inputs("\n".join(self._failed_urls()))[0])

    def _retry_failed(self):
        if (
            self._busy
            or self._api_client is None
            or not self._source_matches()
        ):
            return
        sources, _ = classify_batch_inputs("\n".join(self._failed_urls()))
        if sources:
            self._begin_resolve(sources, retry=True)

    def _show_errors(self):
        from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
        dialog = WorkflowDialog("来源解析详情", "查看失败原因，复制链接或重试失败项。", self,
                                confirm="重试失败项", width=760)
        dialog.resize(760, 440)
        dialog.cancel_button.setText("关闭")
        detail = RowHoverTable(len(self._report.issues), 3)
        detail.setHorizontalHeaderLabels(["内容", "原因", "链接"])
        detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        detail.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = detail.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 180)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 104)
        detail.setWordWrap(True)
        detail.setTextElideMode(Qt.ElideNone)
        detail.verticalHeader().hide()
        for row, issue in enumerate(self._report.issues):
            for column, value in enumerate(
                (
                    issue.title or issue.source or "来源",
                    issue.message,
                )
            ):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                detail.setItem(row, column, item)
            url = issue.url or issue.source
            copy_link = QPushButton("复制链接")
            copy_link.setObjectName("TableSubtleButton")
            copy_link.setToolTip(url)
            copy_link.setEnabled(bool(url))
            copy_link.clicked.connect(lambda _checked=False, value=url: QApplication.clipboard().setText(value))
            detail.setCellWidget(row, 2, copy_link)
        detail.horizontalHeader().sectionResized.connect(lambda *_args: detail.resizeRowsToContents())
        detail.resizeRowsToContents()
        if self._report.issues:
            detail.selectRow(0)
        detail.setMinimumHeight(140)
        dialog.body.addWidget(detail, 1)
        actions = dialog.footer_actions.row
        full_reason = ActionButton("所选项完整原因")
        full_reason.setObjectName("TextButton")
        full_reason.setEnabled(bool(self._report.issues))
        def show_reason():
            if detail.currentRow() < 0:
                return
            issue = self._report.issues[detail.currentRow()]
            MessageBox("来源解析详情", f"{issue.title or issue.source}\n{issue.message}\n{issue.url or issue.source}", dialog).exec()
        full_reason.clicked.connect(show_reason)
        actions.insertWidget(0, full_reason)
        copy = ActionButton("复制失败链接")
        copy.setEnabled(bool(self._failed_urls()))
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText("\n".join(self._failed_urls()))
        )
        actions.insertWidget(1, copy)
        retry = dialog.confirm_button
        retry.clicked.disconnect()
        retry.setEnabled(
            bool(self._failed_urls())
            and self._api_client is not None
            and not self._busy
            and self._source_matches()
        )

        def retry_failed():
            dialog.accept()
            self._retry_failed()

        retry.clicked.connect(retry_failed)
        dialog.exec()

    def _set_all_checked(self, checked: bool):
        if checked:
            self.selection.select_visible()
        else:
            self.selection.clear()

    def accept(self):
        if self._busy:
            return
        if not self._source_matches():
            self._notice.set_message("来源已改，请先重新解析", "warning")
            return
        if self._source_discovery is not None and not self._collapse_btn.isChecked():
            return
        if not self._resolved_items:
            MessageBox(
                "批量导入", "请先解析并预览来源", self, tone="warning"
            ).exec()
            return
        if not self.get_video_infos():
            MessageBox("批量导入", "请至少选一个作品", self, tone="warning").exec()
            return
        if self._embedded:
            self.enqueue_requested.emit(self.get_video_infos())
        else:
            super().accept()

    def get_video_infos(self) -> list:
        return [
            info
            for info in self._resolved_items
            if info.content_identity in self.selection.state.selected
        ]

    def get_urls(self) -> list[str]:
        """Compatibility accessor for callers that only need validated inputs."""
        return list(self._inputs)
