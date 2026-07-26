"""Preview-first dialog for importing videos, collections and favorites."""

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.batch import classify_batch_inputs
from bilibili_downloader.gui.threads.batch_worker import (
    SourceResolveRunner,
    SourceResolveWorker,
)


class BatchDialog(QDialog):
    """Resolve sources in the background and let users select import items."""

    def __init__(
        self,
        api_client=None,
        existing_bvids: set[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._api_client = api_client
        self._existing_bvids = {value.lower() for value in (existing_bvids or set())}
        self._inputs = []
        self._resolved_items = []
        self._selectors = []
        self._resolve_worker = None
        self._resolve_runner = None

        self.setWindowTitle("批量导入")
        self.setMinimumSize(780, 620)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("导入作品与合集")
        title.setObjectName("DialogTitle")
        caption = QLabel("支持视频、合集、系列、收藏夹和 b23.tv 短链，每行一个来源")
        caption.setObjectName("DialogCaption")
        layout.addWidget(title)
        layout.addWidget(caption)

        self._url_text = QPlainTextEdit()
        self._url_text.setMaximumHeight(130)
        self._url_text.setPlaceholderText(
            "https://www.bilibili.com/video/BV1xxx\n"
            "https://space.bilibili.com/123/lists/456?type=season\n"
            "https://space.bilibili.com/123/favlist?fid=456"
        )
        self._url_text.textChanged.connect(self._refresh_input_count)
        layout.addWidget(self._url_text)

        input_row = QHBoxLayout()
        self._count_label = QLabel("0 个来源")
        self._count_label.setObjectName("StatusPill")
        input_row.addWidget(self._count_label)
        input_row.addStretch()
        self._resolve_btn = QPushButton("解析并预览")
        self._resolve_btn.setObjectName("PrimaryButton")
        self._resolve_btn.clicked.connect(self._start_resolve)
        input_row.addWidget(self._resolve_btn)
        layout.addLayout(input_row)

        self._preview = QTableWidget()
        self._preview.setColumnCount(4)
        self._preview.setHorizontalHeaderLabels(["选择", "作品", "UP 主", "来源"])
        self._preview.horizontalHeader().setStretchLastSection(True)
        self._preview.setColumnWidth(0, 64)
        self._preview.setColumnWidth(1, 330)
        self._preview.setColumnWidth(2, 140)
        self._preview.verticalHeader().setVisible(False)
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        layout.addWidget(self._preview, 1)

        self._result_label = QLabel("解析后可在此筛选要加入的作品")
        self._result_label.setObjectName("DialogCaption")
        self._result_label.setWordWrap(True)
        layout.addWidget(self._result_label)

        buttons_row = QHBoxLayout()
        select_all = QPushButton("全选")
        select_all.setObjectName("SubtleButton")
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        buttons_row.addWidget(select_all)
        select_none = QPushButton("取消全选")
        select_none.setObjectName("SubtleButton")
        select_none.clicked.connect(lambda: self._set_all_checked(False))
        buttons_row.addWidget(select_none)
        buttons_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("加入任务中心")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons_row.addWidget(buttons)
        layout.addLayout(buttons_row)

    def _refresh_input_count(self):
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
            QMessageBox.warning(self, "批量导入", "没有可解析的 B 站来源")
            return
        if self._api_client is None:
            QMessageBox.warning(self, "批量导入", "当前没有可用的 API 客户端")
            return
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
        self._resolved_items = items
        self._preview.setRowCount(len(items))
        self._selectors = []
        duplicate_count = 0
        for row, info in enumerate(items):
            selector = QCheckBox()
            duplicate = info.bvid.lower() in self._existing_bvids
            selector.setChecked(True)
            if duplicate:
                duplicate_count += 1
                selector.setToolTip("任务中心已有同源作品，将按当前规格进一步去重")
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addWidget(selector, alignment=Qt.AlignCenter)
            self._preview.setCellWidget(row, 0, wrapper)
            self._preview.setItem(row, 1, QTableWidgetItem(info.title))
            self._preview.setItem(row, 2, QTableWidgetItem(info.author))
            source = info.collection_title or "单个视频"
            if duplicate:
                source = f"{source} · 已有同源任务"
            self._preview.setItem(row, 3, QTableWidgetItem(source))
            self._selectors.append(selector)

        details = [f"解析到 {len(items)} 个作品"]
        if duplicate_count:
            details.append(f"{duplicate_count} 个已有同源任务，将按规格去重")
        if errors:
            details.append(f"{len(errors)} 个来源失败：{errors[0]}")
        self._result_label.setText(" · ".join(details))

    def _set_all_checked(self, checked: bool):
        for selector in self._selectors:
            if selector.isEnabled():
                selector.setChecked(checked)

    def accept(self):
        if not self._resolved_items:
            QMessageBox.warning(self, "批量导入", "请先解析来源并预览内容")
            return
        if not self.get_video_infos():
            QMessageBox.warning(self, "批量导入", "请至少选择一个作品")
            return
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
