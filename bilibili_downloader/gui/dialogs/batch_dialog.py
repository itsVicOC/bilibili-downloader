"""Batch download dialog for multiple URLs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from bilibili_downloader.core.batch import classify_batch_inputs


class BatchDialog(QDialog):
    """Dialog for pasting multiple URLs for batch download."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._urls = []

        self.setWindowTitle("批量任务舱")
        self.setMinimumSize(580, 460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("批量导入作品")
        title.setObjectName("DialogTitle")
        caption = QLabel("每行一个 B 站链接、BV / AV 号或 b23.tv 短链")
        caption.setObjectName("DialogCaption")
        layout.addWidget(title)
        layout.addWidget(caption)

        editor_panel = QFrame()
        editor_panel.setObjectName("DialogPanel")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(14, 14, 14, 14)
        editor_layout.setSpacing(10)
        self._url_text = QPlainTextEdit()
        self._url_text.setPlaceholderText(
            "https://www.bilibili.com/video/BV1xxx\n"
            "BV1yyy\n"
            "https://www.bilibili.com/video/BV1zzz"
        )
        self._url_text.textChanged.connect(self._refresh_preview)
        editor_layout.addWidget(self._url_text)

        self._count_label = QLabel("0 个视频")
        self._count_label.setObjectName("StatusPill")
        editor_layout.addWidget(self._count_label, alignment=Qt.AlignLeft)
        layout.addWidget(editor_panel)

        # Buttons
        btn_layout = QHBoxLayout()

        parse_btn = QPushButton("识别链接")
        parse_btn.setObjectName("SecondaryButton")
        parse_btn.clicked.connect(self._on_parse)
        btn_layout.addWidget(parse_btn)

        btn_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("加入队列")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)

        layout.addLayout(btn_layout)

    def _on_parse(self):
        """Validate the pasted inputs and update the preview."""
        raw = self._url_text.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "提示", "请先粘贴视频链接")
            return
        self._refresh_preview()

    def _refresh_preview(self):
        valid, invalid = classify_batch_inputs(self._url_text.toPlainText())
        self._urls = valid
        if invalid:
            self._count_label.setText(
                f"可加入 {len(valid)} 个 · 将忽略 {len(invalid)} 行无效输入"
            )
        else:
            self._count_label.setText(f"可加入 {len(valid)} 个视频")

    def accept(self):
        """Always parse current editor contents before submitting."""
        self._refresh_preview()
        if not self._urls:
            QMessageBox.warning(self, "提示", "没有可加入队列的有效视频链接")
            return
        super().accept()

    def get_urls(self) -> list[str]:
        """Return the list of URLs."""
        return self._urls
