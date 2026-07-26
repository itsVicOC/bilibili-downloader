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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)

from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    AppSettings,
    OutputMode,
    VideoQuality,
)
from bilibili_downloader.utils.validators import render_path_template


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

        self._path_template = QLineEdit(self._settings.path_template)
        self._path_template.setPlaceholderText("{author}/{title}{part_suffix}")
        self._path_template.setToolTip(
            "可用字段：title、author、bvid、page、part、part_suffix、"
            "collection、quality、codec"
        )
        form.addRow("目录模板：", self._path_template)

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

        self._audio_combo = QComboBox()
        for audio_id in (30251, 30250, 30285, 30280, 30216, 0):
            self._audio_combo.addItem(
                AUDIO_CODEC_MAP.get(audio_id, f"音频 {audio_id}"), audio_id
            )
        audio_index = self._audio_combo.findData(
            self._settings.default_audio_quality
        )
        self._audio_combo.setCurrentIndex(audio_index if audio_index >= 0 else 0)
        form.addRow("默认音频：", self._audio_combo)

        self._output_mode_combo = QComboBox()
        self._output_mode_combo.addItem("视频 / MP4", OutputMode.VIDEO)
        self._output_mode_combo.addItem("仅音频 / M4A 或 FLAC", OutputMode.AUDIO)
        output_index = self._output_mode_combo.findData(
            self._settings.default_output_mode
        )
        self._output_mode_combo.setCurrentIndex(output_index if output_index >= 0 else 0)
        form.addRow("默认输出：", self._output_mode_combo)

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
        options_layout = QGridLayout()
        self._danmaku_check = QCheckBox("默认下载弹幕")
        self._danmaku_check.setChecked(self._settings.download_danmaku)
        self._subtitle_check = QCheckBox("默认下载字幕")
        self._subtitle_check.setChecked(self._settings.download_subtitle)
        self._all_subtitles_check = QCheckBox("默认下载全部字幕")
        self._all_subtitles_check.setChecked(self._settings.download_all_subtitles)
        self._cover_check = QCheckBox("默认保存封面")
        self._cover_check.setChecked(self._settings.download_cover)
        self._metadata_check = QCheckBox("默认保存元数据")
        self._metadata_check.setChecked(self._settings.download_metadata)
        options_layout.addWidget(self._danmaku_check, 0, 0)
        options_layout.addWidget(self._subtitle_check, 0, 1)
        options_layout.addWidget(self._all_subtitles_check, 0, 2)
        options_layout.addWidget(self._cover_check, 1, 0)
        options_layout.addWidget(self._metadata_check, 1, 1)
        options_layout.setColumnStretch(3, 1)
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
        try:
            render_path_template(
                self._path_template.text(),
                {
                    "title": "title",
                    "author": "author",
                    "bvid": "BV1xx",
                    "page": "1",
                    "part": "part",
                    "part_suffix": "_part",
                    "collection": "collection",
                    "quality": "1080P",
                    "codec": "HEVC",
                },
            )
        except ValueError as exc:
            QMessageBox.warning(self, "下载设置", str(exc))
            return
        self.accept()

    def get_settings(self) -> AppSettings:
        """Return updated settings from dialog."""
        self._settings.output_dir = self._output_dir.text()
        self._settings.default_quality = self._quality_combo.currentData()
        self._settings.default_video_codec = self._codec_combo.currentData()
        self._settings.default_audio_quality = self._audio_combo.currentData()
        self._settings.default_output_mode = self._output_mode_combo.currentData()
        self._settings.path_template = self._path_template.text().strip()
        self._settings.max_concurrent_downloads = self._max_concurrent.value()
        self._settings.ffmpeg_path = self._ffmpeg_path.text()
        self._settings.download_danmaku = self._danmaku_check.isChecked()
        all_subtitles = self._all_subtitles_check.isChecked()
        self._settings.download_subtitle = (
            self._subtitle_check.isChecked() or all_subtitles
        )
        self._settings.download_all_subtitles = all_subtitles
        self._settings.download_cover = self._cover_check.isChecked()
        self._settings.download_metadata = self._metadata_check.isChecked()
        return self._settings
