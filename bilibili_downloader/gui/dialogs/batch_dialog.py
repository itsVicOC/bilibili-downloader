"""Preview-first dialog for importing videos, collections and favorites."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.batch import classify_batch_inputs
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.threads.batch_worker import (
    SourceResolveRunner,
    SourceResolveWorker,
)
from bilibili_downloader.gui.widgets.components import MessageBox, Notice, SectionCard


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
        self._resolved_source = None
        self._request_source = None
        self._errors = []
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
        layout.setSpacing(20)
        self._input_card = SectionCard("1. 输入来源")
        self._count_label = QLabel("0 个来源")
        self._count_label.setObjectName("StatusBadge")
        self._input_card.header.addWidget(self._count_label)
        self._collapse_btn = QPushButton("收起输入")
        self._collapse_btn.setObjectName("TableSubtleButton")
        self._collapse_btn.setCheckable(True)
        self._collapse_btn.toggled.connect(self._toggle_input)
        self._collapse_btn.hide()
        self._input_card.header.addWidget(self._collapse_btn)
        self._url_text = QPlainTextEdit()
        self._url_text.setFixedHeight(112)
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
        self._resolve_btn.clicked.connect(self._start_resolve)
        input_row.addWidget(self._resolve_btn)
        self._input_card.body.addLayout(input_row)
        layout.addWidget(self._input_card)
        self._preview_card = SectionCard("2. 选择作品")
        for text, checked in (("全选", True), ("取消全选", False)):
            button = QPushButton(text)
            button.setObjectName("TableSubtleButton")
            button.clicked.connect(
                lambda _checked=False, value=checked: self._set_all_checked(value)
            )
            self._preview_card.header.addWidget(button)
        self._preview = QTableWidget(0, 4)
        self._preview.setHorizontalHeaderLabels(["选择", "作品", "UP 主", "来源"])
        header = self._preview.horizontalHeader()
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 56)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        self._preview.verticalHeader().hide()
        self._preview.verticalHeader().setDefaultSectionSize(UI_METRICS.row_height)
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._preview.setShowGrid(False)
        self._preview.setMinimumHeight(100)
        self._preview_card.body.addWidget(self._preview, 1)
        self._result_label = QLabel("解析后可在此筛选要加入的作品")
        self._result_label.setObjectName("MetaLabel")
        self._result_label.setTextFormat(Qt.PlainText)
        self._result_label.setWordWrap(True)
        self._preview_card.body.addWidget(self._result_label)
        layout.addWidget(self._preview_card, 1)
        self._preview_card.hide()
        self._notice = Notice(action="查看详情", callback=self._show_errors)
        self._notice.action.hide()
        layout.addWidget(self._notice)
        footer = QHBoxLayout()
        self._selected_label = QLabel("已选 0 项")
        self._selected_label.setObjectName("MetaLabel")
        footer.addWidget(self._selected_label)
        footer.addStretch()
        self._add_btn = QPushButton("加入下载队列")
        self._add_btn.setObjectName("PrimaryButton")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self.accept)
        footer.addWidget(self._add_btn)
        if not self._embedded:
            cancel = QPushButton("取消")
            cancel.clicked.connect(self.reject)
            footer.addWidget(cancel)
        layout.addLayout(footer)

    def _toggle_input(self, collapsed):
        self._url_text.setVisible(not collapsed)
        self._input_hint.setVisible(not collapsed)
        self._resolve_btn.setVisible(not collapsed)
        self._collapse_btn.setText("展开输入" if collapsed else "收起输入")
        if self._resolved_items:
            self._preview_card.setVisible(collapsed or self.height() >= 540)

    def resizeEvent(self, event):
        if self._resolved_items and event.size().height() < 540:
            self._collapse_btn.setChecked(True)
        elif self._resolved_items:
            self._preview_card.show()
        super().resizeEvent(event)

    def _selection_updated(self):
        count = len(self.get_video_infos())
        valid = self._resolved_source == self._url_text.toPlainText()
        self._selected_label.setText(f"已选 {count} 项")
        self._add_btn.setEnabled(count > 0 and valid and self._resolve_btn.isEnabled())

    def _refresh_input_count(self):
        if self._resolved_source is not None:
            stale = self._resolved_source != self._url_text.toPlainText()
            self._notice.set_message(
                "来源已修改，请重新解析后加入任务。"
                if stale
                else f"{len(self._errors)} 个来源解析失败，已解析作品仍可加入。"
                if self._errors
                else "",
                "warning",
            )
            self._notice.action.setVisible(bool(self._errors))
            self._result_label.setVisible(not stale and not self._errors)
            self._selection_updated()
        valid, invalid = classify_batch_inputs(self._url_text.toPlainText())
        self._inputs = valid
        if invalid:
            self._count_label.setText(
                f"{len(valid)} 个来源 · {len(invalid)} 行无法识别"
            )
        else:
            self._count_label.setText(f"{len(valid)} 个来源")

    def _start_resolve(self):
        self._refresh_input_count()
        if not self._inputs:
            self._notice.set_message("没有可解析的 B 站来源", "warning")
            return
        if self._api_client is None:
            self._notice.set_message("当前没有可用的 API 客户端", "danger")
            return
        self._request_source = self._url_text.toPlainText()
        self._notice.set_message("")
        self._add_btn.setEnabled(False)
        self._resolve_btn.setEnabled(False)
        self._resolve_btn.setText("解析中...")
        self._result_label.setText("正在读取来源内容和分页，请稍候...")
        self._resolved_items = []
        self._selectors = []
        self._preview.setRowCount(0)
        self._resolve_worker = SourceResolveWorker()
        self._resolve_worker.finished.connect(self._on_resolved)
        self._resolve_runner = SourceResolveRunner(
            self._resolve_worker, self._api_client, self._inputs
        )
        QThreadPool.globalInstance().start(self._resolve_runner)

    def _on_resolved(self, items: list, errors: list):
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("重新解析")
        self._resolved_source = (
            self._request_source
            if self._request_source is not None
            else self._url_text.toPlainText()
        )
        self._errors = errors
        self._resolved_items = items
        self._preview.setRowCount(len(items))
        self._selectors = []
        duplicate_count = 0
        for row, info in enumerate(items):
            selector = QCheckBox()
            duplicate = (
                info.content_identity.lower() in self._existing_content_identities
            )
            selector.setChecked(info.is_main_section)
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

        details = [f"解析到 {len(items)} 个作品"]
        if duplicate_count:
            details.append(f"{duplicate_count} 个已有同源任务，将按规格去重")
        if errors:
            details.append(f"{len(errors)} 个来源失败")
        self._result_label.setText(" · ".join(details))
        self._result_label.setToolTip("\n".join(errors))
        self._result_label.setVisible(
            not errors and self._resolved_source == self._url_text.toPlainText()
        )
        self._preview_card.show()
        self._collapse_btn.setVisible(bool(items))
        if items and self.height() < 540:
            self._collapse_btn.setChecked(True)
        self._selection_updated()
        if self._resolved_source != self._url_text.toPlainText():
            self._notice.set_message("解析期间来源已修改，请重新解析。", "warning")
        elif errors:
            self._notice.set_message(
                f"{len(errors)} 个来源解析失败，已解析作品仍可加入。", "warning"
            )
            self._notice.action.show()
        else:
            self._notice.set_message("")
            self._notice.action.hide()

    def _show_errors(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("来源解析详情")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText("\n\n".join(self._errors))
        layout.addWidget(detail)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.reject)
        layout.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()

    def _set_all_checked(self, checked: bool):
        for selector in self._selectors:
            if selector.isEnabled():
                selector.setChecked(checked)

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
