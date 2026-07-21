"""Settings dialog for application configuration."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)

from bilibili_downloader.core.models import AppSettings, VideoQuality


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings.model_copy(deep=True)
        self.setWindowTitle("下载设置")
        self.setMinimumWidth(620)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        title = QLabel("下载偏好")
        title.setObjectName("DialogTitle")
        caption = QLabel("统一管理保存位置、默认规格和并行任务数")
        caption.setObjectName("DialogCaption")
        layout.addWidget(title)
        layout.addWidget(caption)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        # Output directory
        dir_layout = QHBoxLayout()
        self._output_dir = QLineEdit(self._settings.output_dir)
        self._output_dir.setReadOnly(True)
        self._output_dir.setToolTip(self._settings.output_dir)
        dir_layout.addWidget(self._output_dir, 1)
        browse_btn = QPushButton("浏览...")
        browse_btn.setObjectName("SubtleButton")
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

        self._codec_combo = QComboBox()
        self._codec_combo.addItem("H.265 / HEVC", 12)
        self._codec_combo.addItem("H.264 / AVC", 7)
        self._codec_combo.addItem("AV1", 13)
        codec_index = self._codec_combo.findData(self._settings.default_video_codec)
        self._codec_combo.setCurrentIndex(codec_index if codec_index >= 0 else 0)
        form.addRow("默认编码：", self._codec_combo)

        # Max concurrent downloads
        self._max_concurrent = QSpinBox()
        self._max_concurrent.setRange(1, 8)
        self._max_concurrent.setValue(self._settings.max_concurrent_downloads)
        self._max_concurrent.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._max_concurrent.setAlignment(Qt.AlignCenter)
        self._max_concurrent.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        concurrency_layout = QHBoxLayout()
        concurrency_layout.setSpacing(8)
        self._concurrency_down = self._create_stepper_button(
            "-", "减少并发数", self._max_concurrent.stepDown
        )
        self._concurrency_up = self._create_stepper_button(
            "+", "增加并发数", self._max_concurrent.stepUp
        )
        concurrency_layout.addWidget(self._concurrency_down)
        concurrency_layout.addWidget(self._max_concurrent, 1)
        concurrency_layout.addWidget(self._concurrency_up)
        self._max_concurrent.valueChanged.connect(self._sync_stepper_buttons)
        self._sync_stepper_buttons(self._max_concurrent.value())
        form.addRow("最大并发：", concurrency_layout)

        # FFmpeg path
        ffmpeg_layout = QHBoxLayout()
        self._ffmpeg_path = QLineEdit(self._settings.ffmpeg_path)
        self._ffmpeg_path.setPlaceholderText("留空自动检测")
        ffmpeg_layout.addWidget(self._ffmpeg_path)
        ffmpeg_browse = QPushButton("浏览...")
        ffmpeg_browse.setObjectName("SubtleButton")
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

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_stepper_button(self, text: str, tooltip: str, callback):
        button = QPushButton(text)
        button.setObjectName("StepperButton")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRepeat(True)
        button.clicked.connect(callback)
        return button

    def _sync_stepper_buttons(self, value: int):
        self._concurrency_down.setEnabled(value > self._max_concurrent.minimum())
        self._concurrency_up.setEnabled(value < self._max_concurrent.maximum())

    def _browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if path:
            self._output_dir.setText(path)
            self._output_dir.setToolTip(path)

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 FFmpeg", "", "可执行文件 (ffmpeg*;ffmpeg.exe)"
        )
        if path:
            self._ffmpeg_path.setText(path)

    def _accept_if_valid(self):
        output_dir = self._output_dir.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "下载设置", "请选择有效的保存目录")
            return
        ffmpeg_path = self._ffmpeg_path.text().strip()
        if ffmpeg_path and not Path(ffmpeg_path).is_file():
            QMessageBox.warning(self, "下载设置", "FFmpeg 路径不是有效文件")
            return
        self.accept()

    def get_settings(self) -> AppSettings:
        """Return updated settings from dialog."""
        self._settings.output_dir = self._output_dir.text()
        self._settings.default_quality = self._quality_combo.currentData()
        self._settings.default_video_codec = self._codec_combo.currentData()
        self._settings.max_concurrent_downloads = self._max_concurrent.value()
        self._settings.ffmpeg_path = self._ffmpeg_path.text()
        self._settings.download_danmaku = self._danmaku_check.isChecked()
        self._settings.download_subtitle = self._subtitle_check.isChecked()
        return self._settings
