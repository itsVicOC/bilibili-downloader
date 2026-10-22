"""Version choice dialog with bounded, selectable release notes."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from bilibili_downloader import __version__


class UpdateDialog(QDialog):
    UPDATE = 1
    LATER = 2
    SKIP = 3

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.setWindowTitle("发现新版本")
        self.setMinimumSize(460, 340)
        self.resize(560, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        heading = QLabel(f"BiliFlow v{release.version} 已发布")
        heading.setObjectName("DialogTitle")
        heading.setTextFormat(Qt.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        version = QLabel(
            f"当前版本 v{__version__}  →  新版本 v{release.version}\n发布日期：{release.published_at[:10] or '未提供'}"
        )
        version.setObjectName("DialogCaption")
        version.setTextFormat(Qt.PlainText)
        version.setWordWrap(True)
        layout.addWidget(version)
        self.notes = QPlainTextEdit(release.notes or "此版本未提供更新说明。")
        self.notes.setReadOnly(True)
        layout.addWidget(self.notes, 1)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        for text, result in (
            ("跳过此版本", self.SKIP),
            ("稍后提醒", self.LATER),
            ("立即更新", self.UPDATE),
        ):
            button = QPushButton(text)
            button.setObjectName(
                "PrimaryButton" if result == self.UPDATE else "TextButton" if result == self.SKIP else "SubtleButton"
            )
            button.clicked.connect(
                lambda _checked=False, value=result: self.done(value)
            )
            footer.addWidget(button)
            if result == self.SKIP:
                footer.addStretch()
        layout.addLayout(footer)
