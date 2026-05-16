"""Batch download dialog for multiple URLs."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.batch import BatchResolver
from src.utils.validators import extract_bvid, is_short_link, resolve_short_link


class BatchDialog(QDialog):
    """Dialog for pasting multiple URLs for batch download."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self._api_client = api_client
        self._resolver = BatchResolver(api_client)
        self._urls = []
        self._resolved_items = []  # List of (bvid, VideoInfo)

        self.setWindowTitle("批量下载")
        self.setMinimumSize(500, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "每行粘贴一个B站链接或BV号："
        ))

        self._url_text = QPlainTextEdit()
        self._url_text.setPlaceholderText(
            "https://www.bilibili.com/video/BV1xxx\n"
            "BV1yyy\n"
            "https://www.bilibili.com/video/BV1zzz"
        )
        layout.addWidget(self._url_text)

        # Count label
        self._count_label = QLabel("0 个视频")
        layout.addWidget(self._count_label)

        # Buttons
        btn_layout = QHBoxLayout()

        parse_btn = QPushButton("解析链接")
        parse_btn.clicked.connect(self._on_parse)
        btn_layout.addWidget(parse_btn)

        btn_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)

        layout.addLayout(btn_layout)

    def _on_parse(self):
        """Parse the pasted URLs and resolve to video info."""
        raw = self._url_text.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "提示", "请先粘贴视频链接")
            return

        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        self._urls = lines
        self._resolved_items = []

        valid_count = 0
        short_link_count = 0

        for line in lines:
            if is_short_link(line):
                short_link_count += 1
                continue

            bvid = extract_bvid(line)
            if bvid:
                valid_count += 1

        # Try to resolve short links
        if short_link_count > 0:
            self._count_label.setText(
                f"共 {len(lines)} 行，其中 {short_link_count} 个短链（需展开），{valid_count} 个直链"
            )
        else:
            self._count_label.setText(f"共识别 {valid_count} 个视频")

    def get_urls(self) -> list[str]:
        """Return the list of URLs."""
        return self._urls
