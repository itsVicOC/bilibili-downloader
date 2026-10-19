"""Preview-first dialog for importing videos, collections and favorites."""

from collections import Counter

from PySide6.QtCore import QSignalBlocker, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.batch import classify_batch_inputs
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.threads.batch_worker import (
    ImportIssue,
    ImportReport,
    SourceResolveRunner,
    SourceResolveWorker,
)
from bilibili_downloader.gui.widgets.components import (
    ElidedLabel,
    MessageBox,
    Notice,
    OutputActionBar,
    SectionCard,
)


class BatchDialog(QDialog):
    """Reusable import content, also available in a standalone dialog."""

    enqueue_requested = Signal(list)

    def __init__(
        self,
        api_client=None,
        existing_bvids: set[str] | None = None,
        existing_content_identities: set[str] | None = None,
        parent=None,
        embedded=False,
    ):
        super().__init__(parent)
        self._embedded = embedded
        self.setProperty("embedded", embedded)
        self._resolved_source = None
        self._request_source = None
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

        self.setWindowTitle("批量导入")
        if not embedded:
            self.setMinimumSize(700, 520)
            self.resize(820, 640)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            0, 0, 0, 0
        ) if self._embedded else layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        self.setObjectName("BatchImport")
        self._input_card = SectionCard("导入来源")
        self._input_card.body.setContentsMargins(16, 12, 16, 12)
        self._input_card.body.setSpacing(10)
        self._input_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._count_label = QLabel("0 个来源")
        self._count_label.setObjectName("StatusBadge")
        self._count_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._input_card.header.addWidget(self._count_label)
        self._compact_resolve = QPushButton("重新解析")
        self._compact_resolve.setObjectName("TableSubtleButton")
        self._compact_resolve.clicked.connect(self._start_resolve)
        self._compact_resolve.hide()
        self._input_card.header.addWidget(self._compact_resolve)
        self._collapse_btn = QPushButton("收起编辑")
        self._collapse_btn.setObjectName("TableSubtleButton")
        self._collapse_btn.setCheckable(True)
        self._collapse_btn.toggled.connect(self._toggle_input)
        self._collapse_btn.hide()
        self._input_card.header.addWidget(self._collapse_btn)
        self._source_summary = ElidedLabel()
        self._source_summary.setObjectName("MetaLabel")
        self._source_summary.hide()
        self._input_card.header.insertWidget(1, self._source_summary, 1)
        self._input_card.header.setStretch(2, 0)
        self._url_text = QPlainTextEdit()
        self._url_text.setFixedHeight(96)
        self._url_text.setPlaceholderText(
            "每行一个视频、番剧 ep/ss/md、合集、收藏夹或 b23.tv 短链"
        )
        self._url_text.textChanged.connect(self._refresh_input_count)
        self._input_card.body.addWidget(self._url_text)
        input_row = QHBoxLayout()
        hint = QLabel("支持多个来源，解析后可逐项选择作品")
        self._input_hint = hint
        hint.setObjectName("MetaLabel")
        input_row.addWidget(hint, 1)
        self._resolve_btn = QPushButton("解析并预览")
        self._resolve_btn.setObjectName("PrimaryButton")
        self._resolve_btn.setProperty("batchAction", True)
        self._resolve_btn.clicked.connect(self._start_resolve)
        input_row.addWidget(self._resolve_btn)
        self._input_card.body.addLayout(input_row)
        layout.addWidget(self._input_card)
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
        layout.addWidget(self._progress_area)
        self._preview_card = SectionCard("作品清单")
        self._preview_card.body.setContentsMargins(16, 14, 16, 10)
        self._preview_card.body.setSpacing(8)
        self._available_label = QLabel()
        self._available_label.setObjectName("MetaLabel")
        self._preview_card.header.insertWidget(1, self._available_label)
        for text, checked in (("全选", True), ("清空选择", False)):
            button = QPushButton(text)
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(
                lambda _checked=False, value=checked: self._set_all_checked(value)
            )
            self._preview_card.header.addWidget(button)
        self._preview = QTableWidget(0, 4)
        self._preview.setObjectName("BatchPreview")
        self._preview.setHorizontalHeaderLabels(["", "作品", "UP 主", "来源"])
        header = self._preview.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 44)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for column, width in ((2, 120), (3, 180)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            header.resizeSection(column, width)
        self._preview.verticalHeader().hide()
        self._preview.verticalHeader().setDefaultSectionSize(UI_METRICS.compact_row_height)
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._preview.setShowGrid(False)
        self._preview.setMinimumHeight(100)
        self._preview_card.body.addWidget(self._preview, 1)
        self._result_label = QLabel("解析后可在此筛选要加入的作品")
        self._result_label.setObjectName("MetaLabel")
        self._result_label.setTextFormat(Qt.PlainText)
        self._result_label.setWordWrap(True)
        results = QHBoxLayout()
        results.addWidget(self._result_label, 1)
        self._issue_btn = QPushButton("查看未解析项")
        self._issue_btn.setObjectName("TableSubtleButton")
        self._issue_btn.setProperty("warningAction", True)
        self._issue_btn.clicked.connect(self._show_errors)
        self._issue_btn.hide()
        results.addWidget(self._issue_btn)
        self._preview_card.body.addLayout(results)
        layout.addWidget(self._preview_card, 1)
        self._preview_card.hide()
        self._empty_space = QWidget()
        self._empty_space.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._empty_space, 1)
        self._notice = Notice(action="查看详情", callback=self._show_errors)
        self._notice.action.hide()
        layout.addWidget(self._notice)
        self._action_bar = OutputActionBar("已选 0 项")
        self._selected_label = self._action_bar.status
        self._output_specs = self._action_bar.specs
        self._output_directory = self._action_bar.directory
        self._footer_actions = self._action_bar.actions
        self._add_btn = self._action_bar.primary_button
        self._action_bar.submit_requested.connect(self.accept)
        self._action_bar.edit_button.setVisible(self._embedded)
        if not self._embedded:
            cancel = QPushButton("取消")
            cancel.clicked.connect(self.reject)
            self._footer_actions.insertWidget(0, cancel)
        layout.addWidget(self._action_bar)

    def set_output_summary(self, specs, directory):
        self._output_specs.set_full_text(specs)
        self._output_directory.set_full_text(directory)

    def _toggle_input(self, collapsed):
        self._url_text.setVisible(not collapsed)
        self._input_hint.setVisible(not collapsed)
        self._resolve_btn.setVisible(not collapsed)
        self._source_summary.setVisible(collapsed)
        self._count_label.setVisible(not collapsed)
        self._compact_resolve.setVisible(collapsed)
        self._collapse_btn.setText("编辑来源" if collapsed else "收起编辑")
        if self._resolved_items:
            visible = collapsed or self.height() >= 540
            self._preview_card.setVisible(visible)
            self._empty_space.setVisible(not visible)

    def resizeEvent(self, event):
        if self._resolved_items and event.size().height() < 540:
            self._collapse_btn.setChecked(True)
        elif self._resolved_items:
            self._preview_card.show()
            self._empty_space.hide()
        header = self._preview.horizontalHeader()
        header.resizeSection(2, 112 if self.width() < 900 else 152)
        header.resizeSection(3, 148 if self.width() < 900 else 180)
        super().resizeEvent(event)

    def _selection_updated(self):
        count = len(self.get_video_infos())
        valid = self._resolved_source == self._url_text.toPlainText()
        self._selected_label.setText(f"已选 {count} 项")
        self._add_btn.setEnabled(count > 0 and valid and not self._busy)

    def _refresh_input_count(self):
        if self._resolved_source is not None:
            stale = self._resolved_source != self._url_text.toPlainText()
            self._sync_result_feedback()
            self._result_label.setVisible(not stale)
            self._selection_updated()
        self._refresh_source_summary()
        valid, invalid = classify_batch_inputs(self._url_text.toPlainText())
        self._inputs = valid
        if invalid:
            self._count_label.setText(
                f"{len(valid)} 个来源 · {len(invalid)} 行无法识别"
            )
        else:
            self._count_label.setText(f"{len(valid)} 个来源")

    def _refresh_source_summary(self):
        raw = self._url_text.toPlainText()
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        source = lines[0] if lines else "尚未添加来源"
        if len(lines) > 1:
            source += f" 等 {len(lines)} 个来源"
        names = {
            info.collection_title or info.season_title or info.series_title
            for info in self._resolved_items
        }
        if self._resolved_source == raw and len(names) == 1 and next(iter(names)):
            source = next(iter(names))
            if lines:
                source += f" · {len(lines)} 个来源"
        self._source_summary.set_full_text(source)
        self._source_summary.setToolTip(raw)

    def _start_resolve(self):
        if self._busy:
            return
        self._refresh_input_count()
        if not self._inputs:
            self._notice.set_message("没有可解析的 B 站来源", "warning")
            return
        if self._api_client is None:
            self._notice.set_message("当前没有可用的 API 客户端", "danger")
            return
        self._begin_resolve(self._inputs)

    def _begin_resolve(self, sources, *, retry=False):
        self._busy = True
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
        self._request_source = self._url_text.toPlainText()
        self._notice.set_message("")
        self._notice.action.hide()
        self._issue_btn.hide()
        self._add_btn.setEnabled(False)
        self._resolve_btn.setEnabled(False)
        self._compact_resolve.setEnabled(False)
        self._resolve_btn.setText("解析中...")
        self._result_label.setText("正在读取来源内容和分页，请稍候...")
        self._progress_area.show()
        self._progress_bar.setRange(0, 0)
        self._progress_label.setText("正在准备解析…")
        self._cancel_btn.setText("取消解析")
        self._cancel_btn.setEnabled(True)
        if not retry:
            self._resolved_items = []
            self._selectors = []
            self._preview.setRowCount(0)
            self._preview_card.hide()
            self._empty_space.show()
            self._collapse_btn.setChecked(False)
            self._collapse_btn.hide()
            self._selection_updated()
        self._resolve_worker = SourceResolveWorker()
        self._resolve_worker.completed.connect(self._on_report)
        self._resolve_worker.progress.connect(self._on_progress)
        self._resolve_runner = SourceResolveRunner(
            self._resolve_worker, self._api_client, sources
        )
        QThreadPool.globalInstance().start(self._resolve_runner)

    def _on_progress(self, progress):
        if not self._busy:
            return
        completed, total = progress["completed"], progress["total"]
        self._progress_bar.setRange(0, total)
        if total:
            self._progress_bar.setValue(completed)
        number = f" · {completed}/{total}" if total else ""
        self._progress_label.setText(
            f"来源 {progress['source_index']}/{progress['sources']} · {progress['stage']}{number} · 已解析 {progress['items']} 项"
        )
        self._progress_label.setToolTip(progress["source"])

    def cancel_resolution(self):
        if self._busy and self._resolve_worker:
            self._resolve_worker.cancel.set()
            self._cancel_btn.setEnabled(False)
            self._progress_label.setText("正在结束当前请求，已解析作品会保留…")

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

    def _on_report(self, report):
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
        self._report = report
        self._busy = False
        self._progress_area.hide()
        self._resolve_btn.setEnabled(True)
        self._compact_resolve.setEnabled(True)
        self._resolve_btn.setText("重新解析")
        self._resolved_source = (
            self._request_source
            if self._request_source is not None
            else self._url_text.toPlainText()
        )
        self._errors = [
            f"{issue.title or issue.source}：{issue.message}" for issue in report.issues
        ]
        items = report.items
        self._resolved_items = items
        self._preview.setRowCount(len(items))
        self._selectors = []
        duplicate_count = 0
        for row, info in enumerate(items):
            selector = QCheckBox()
            duplicate = (
                info.content_identity.lower() in self._existing_content_identities
            )
            selector.setChecked(
                self._checked_before_retry.get(
                    info.content_identity, info.is_main_section
                )
            )
            if duplicate:
                duplicate_count += 1
                selector.setToolTip("任务中心已有同源作品，将按当前规格进一步去重")
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addWidget(selector, alignment=Qt.AlignCenter)
            self._preview.setCellWidget(row, 0, wrapper)
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
            self._selectors.append(selector)
            selector.toggled.connect(self._selection_updated)

        self._existing_duplicates = duplicate_count
        self._available_label.setText(f"{len(items)} 项")
        sources = {self._preview.item(row, 3).text() for row in range(len(items))}
        self._preview.setColumnHidden(3, len(sources) == 1)
        self._result_label.setText(self._report_summary())
        self._result_label.setToolTip("\n".join(self._errors))
        self._result_label.setVisible(
            self._resolved_source == self._url_text.toPlainText()
        )
        self._preview_card.setVisible(bool(items))
        self._empty_space.setVisible(not bool(items))
        self._collapse_btn.setVisible(bool(items))
        self._collapse_btn.setChecked(
            bool(items) and self._resolved_source == self._url_text.toPlainText()
        )
        self._selection_updated()
        self._refresh_source_summary()
        self._sync_result_feedback()

    def _sync_result_feedback(self):
        items = self._resolved_items
        self._issue_btn.setVisible(bool(items and self._errors))
        self._issue_btn.setAccessibleName(f"查看 {len(self._errors)} 项未解析内容及重试入口")
        self._issue_btn.setToolTip(self._report_summary())
        if self._resolved_source != self._url_text.toPlainText():
            self._issue_btn.hide()
            self._notice.set_message("来源已修改，请重新解析后加入任务。", "warning")
            self._notice.action.setVisible(bool(self._errors))
        elif self._errors and not items:
            self._notice.set_message(self._report_summary(), "warning")
            self._notice.action.show()
        else:
            self._notice.set_message(
                "解析已取消。" if self._report.cancelled and not items else ""
            )
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

    def _retry_failed(self):
        if (
            self._busy
            or self._api_client is None
            or self._resolved_source != self._url_text.toPlainText()
        ):
            return
        sources, _ = classify_batch_inputs("\n".join(self._failed_urls()))
        if sources:
            self._begin_resolve(sources, retry=True)

    def _show_errors(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("来源解析详情")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        detail = QTableWidget(len(self._report.issues), 3)
        detail.setHorizontalHeaderLabels(["内容", "原因", "重试链接"])
        detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        detail.setSelectionBehavior(QAbstractItemView.SelectRows)
        detail.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        detail.verticalHeader().hide()
        for row, issue in enumerate(self._report.issues):
            for column, value in enumerate(
                (
                    issue.title or issue.source or "来源",
                    issue.message,
                    issue.url or issue.source,
                )
            ):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                detail.setItem(row, column, item)
        layout.addWidget(detail)
        actions = QHBoxLayout()
        copy = QPushButton("复制失败链接")
        copy.setEnabled(bool(self._failed_urls()))
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText("\n".join(self._failed_urls()))
        )
        actions.addWidget(copy)
        retry = QPushButton("重试失败项")
        retry.setObjectName("PrimaryButton")
        retry.setEnabled(
            bool(self._failed_urls())
            and self._api_client is not None
            and not self._busy
            and self._resolved_source == self._url_text.toPlainText()
        )

        def retry_failed():
            dialog.accept()
            self._retry_failed()

        retry.clicked.connect(retry_failed)
        actions.addWidget(retry)
        actions.addStretch()
        close = QPushButton("关闭")
        close.clicked.connect(dialog.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        dialog.exec()

    def _set_all_checked(self, checked: bool):
        for selector in self._selectors:
            if selector.isEnabled():
                with QSignalBlocker(selector):
                    selector.setChecked(checked)
        self._selection_updated()

    def accept(self):
        if self._resolved_source != self._url_text.toPlainText():
            self._notice.set_message("请先重新解析已修改的来源", "warning")
            return
        if not self._resolved_items:
            MessageBox(
                "批量导入", "请先解析来源并预览内容", self, tone="warning"
            ).exec()
            return
        if not self.get_video_infos():
            MessageBox("批量导入", "请至少选择一个作品", self, tone="warning").exec()
            return
        if self._embedded:
            self.enqueue_requested.emit(self.get_video_infos())
        else:
            super().accept()

    def get_video_infos(self) -> list:
        return [
            info
            for info, selector in zip(self._resolved_items, self._selectors)
            if selector.isChecked()
        ]

    def get_urls(self) -> list[str]:
        """Compatibility accessor for callers that only need validated inputs."""
        return list(self._inputs)
