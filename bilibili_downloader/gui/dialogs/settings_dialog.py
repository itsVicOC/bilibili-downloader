"""Settings dialog for application configuration."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.models import AppSettings, VideoQuality


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Output directory
        dir_layout = QHBoxLayout()
        self._output_dir = QLineEdit(self._settings.output_dir)
        self._output_dir.setReadOnly(True)
        dir_layout.addWidget(self._output_dir)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_layout.addWidget(browse_btn)
        form.addRow("保存目录：", dir_layout)

        # Default quality
        self._quality_combo = QComboBox()
        for q in VideoQuality:
            self._quality_combo.addItem(q.label, q)
        self._quality_combo.setCurrentIndex(
            self._quality_combo.findData(self._settings.default_quality)
        )
        form.addRow("默认画质：", self._quality_combo)

        # Max concurrent downloads
        self._max_concurrent = QSpinBox()
        self._max_concurrent.setRange(1, 8)
        self._max_concurrent.setValue(self._settings.max_concurrent_downloads)
        form.addRow("最大并发：", self._max_concurrent)

        # FFmpeg path
        ffmpeg_layout = QHBoxLayout()
        self._ffmpeg_path = QLineEdit(self._settings.ffmpeg_path)
        self._ffmpeg_path.setPlaceholderText("留空自动检测")
        ffmpeg_layout.addWidget(self._ffmpeg_path)
        ffmpeg_browse = QPushButton("浏览...")
        ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ffmpeg_layout.addWidget(ffmpeg_browse)
        form.addRow("FFmpeg 路径：", ffmpeg_layout)

        layout.addLayout(form)

        # Option checkboxes
        options_layout = QHBoxLayout()
        self._danmaku_check = QCheckBox("默认下载弹幕")
        self._danmaku_check.setChecked(self._settings.download_danmaku)
        self._subtitle_check = QCheckBox("默认下载字幕")
        self._subtitle_check.setChecked(self._settings.download_subtitle)
        options_layout.addWidget(self._danmaku_check)
        options_layout.addWidget(self._subtitle_check)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #00A1D6; color: white; "
            "padding: 6px 16px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #23a2d9; }"
        )
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if path:
            self._output_dir.setText(path)

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 FFmpeg", "", "可执行文件 (ffmpeg*;ffmpeg.exe)"
        )
        if path:
            self._ffmpeg_path.setText(path)

    def get_settings(self) -> AppSettings:
        """Return updated settings from dialog."""
        self._settings.output_dir = self._output_dir.text()
        self._settings.default_quality = self._quality_combo.currentData()
        self._settings.max_concurrent_downloads = self._max_concurrent.value()
        self._settings.ffmpeg_path = self._ffmpeg_path.text()
        self._settings.download_danmaku = self._danmaku_check.isChecked()
        self._settings.download_subtitle = self._subtitle_check.isChecked()
        return self._settings
