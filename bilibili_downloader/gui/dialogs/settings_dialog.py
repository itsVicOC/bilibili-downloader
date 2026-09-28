"""Reusable settings editor with an isolated draft and field-level merging."""

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    AppSettings,
    OutputMode,
    VideoQuality,
)
from bilibili_downloader.core.recorder import check_recorder, find_recorder
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    FieldRow,
    Notice,
    SectionCard,
    scroll_area,
    stepper,
)
from bilibili_downloader.utils.validators import render_path_template


class _LeadingPathLineEdit(QLineEdit):
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setCursorPosition(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.setCursorPosition(0)


class _ProbeSignals(QObject):
    finished = Signal(bool, str)


class _ProbeRunner(QRunnable):
    def __init__(self, signals, kind, path):
        super().__init__()
        self.signals, self.kind, self.path = signals, kind, path

    def run(self):
        try:
            if self.kind == "ffmpeg":
                ok, message = FFmpegManager.check_available(self.path or None)
            else:
                path = find_recorder(self.path)
                check_recorder(path)
                ok, message = True, f"配套录制引擎可用：{path}"
        except Exception as exc:
            ok, message = False, redact_sensitive_text(str(exc))
        try:
            self.signals.finished.emit(ok, message)
        except RuntimeError:
            # A standalone editor may be destroyed while the tool probe runs.
            pass


class SettingsDialog(QDialog):
    """One editor shared by the settings page and standalone callers."""

    save_requested = Signal()
    cache_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, settings: AppSettings, parent=None, embedded=False):
        super().__init__(parent)
        self._embedded = embedded
        self._settings = settings.model_copy(deep=True)
        self._controls = {}
        self._field_rows = {}
        self._probes = {}
        if embedded:
            self.setWindowFlags(Qt.Widget)
        else:
            self.setMinimumSize(620, 520)
            self.resize(740, 760)
        self.setWindowTitle("BiliFlow 设置")
        self._setup_ui()
        self.load_settings(settings)
        for control in self._controls.values():
            if isinstance(control, QLineEdit):
                control.textChanged.connect(self._draft_changed)
                control.textChanged.connect(
                    lambda text, entry=control: entry.setToolTip(text)
                )
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._draft_changed)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self._draft_changed)
            else:
                control.valueChanged.connect(self._draft_changed)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            0, 0, 0, 0
        ) if self._embedded else layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        download, live, tools = [
            self._tab(name) for name in ("下载", "直播", "工具与存储")
        ]
        paths = SectionCard("保存位置与目录模板")
        self._output_dir = _LeadingPathLineEdit()
        self._output_dir.setReadOnly(True)
        self._controls["output_dir"] = self._output_dir
        self._field(
            "output_dir", paths, "保存目录", self._path_row(self._output_dir, True)
        )
        self._path_template = self._entry("path_template", paths, "目录模板")
        self._path_template.setPlaceholderText("{author}/{title}{part_suffix}")
        self._path_template.setToolTip(
            "字段：title、author、bvid、page、part、part_suffix、collection、quality、codec"
        )
        self._bangumi_path_template = self._entry(
            "bangumi_path_template", paths, "番剧模板"
        )
        hint = QLabel(
            "模板控制相对目录与文件名；支持作品、UP 主、分 P 和番剧章节字段。"
        )
        hint.setObjectName("MetaLabel")
        hint.setWordWrap(True)
        paths.body.addWidget(hint)
        download.addWidget(paths)
        formats = SectionCard("默认媒体规格")
        self._output_mode_combo = self._combo(
            "default_output_mode",
            formats,
            "输出类型",
            [
                ("视频 / MP4", OutputMode.VIDEO),
                ("仅音频 / M4A 或 FLAC", OutputMode.AUDIO),
            ],
        )
        self._quality_combo = self._combo(
            "default_quality", formats, "画面质量", [(q.label, q) for q in VideoQuality]
        )
        self._codec_combo = self._combo(
            "default_video_codec",
            formats,
            "视频编码",
            [("H.265 / HEVC", 12), ("H.264 / AVC", 7), ("AV1", 13)],
        )
        self._audio_combo = self._combo(
            "default_audio_quality",
            formats,
            "音频质量",
            [
                (AUDIO_CODEC_MAP.get(i, str(i)), i)
                for i in (30251, 30250, 30285, 30280, 30216, 0)
            ],
        )
        self._max_concurrent, self._concurrency_down, self._concurrency_up = (
            self._number("max_concurrent_downloads", formats, "最大并发", 1, 8)
        )
        self._concurrency_down.setToolTip("减少并发数")
        self._concurrency_up.setToolTip("增加并发数")
        download.addWidget(formats)
        options = SectionCard("归档附加内容")
        options_grid = QGridLayout()
        options_grid.setHorizontalSpacing(16)
        options_grid.setVerticalSpacing(4)
        positions = [(0, 0), (0, 1), (1, 1), (2, 0), (2, 1)]
        for index, (key, label, attr) in enumerate(
            (
                ("download_danmaku", "默认下载弹幕", "_danmaku_check"),
                ("download_subtitle", "默认下载字幕", "_subtitle_check"),
                ("download_all_subtitles", "默认下载全部字幕", "_all_subtitles_check"),
                ("download_cover", "默认保存封面", "_cover_check"),
                ("download_metadata", "默认保存元数据", "_metadata_check"),
            )
        ):
            control = QCheckBox(label)
            self._controls[key] = control
            setattr(self, attr, control)
            if key == "download_all_subtitles":
                wrapper = QWidget()
                wrapper_layout = QHBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(24, 0, 0, 0)
                wrapper_layout.addWidget(control)
                options_grid.addWidget(wrapper, *positions[index])
            else:
                options_grid.addWidget(control, *positions[index])
        options.body.addLayout(options_grid)
        self._all_subtitles_check.toggled.connect(
            lambda checked: self._subtitle_check.setChecked(True) if checked else None
        )
        download.addWidget(options)
        defaults = SectionCard("默认录制位置与分段")
        self._live_directory = _LeadingPathLineEdit()
        self._controls["live.output_dir"] = self._live_directory
        self._field(
            "live.output_dir",
            defaults,
            "保存目录",
            self._path_row(self._live_directory, True),
        )
        self._number("live.segment_seconds", defaults, "分段时长", 1, 1440, " 分钟")
        defaults.body.addWidget(
            Notice("目录与分段时长只用于新添加的直播间；已有房间请在房间设置中修改。")
        )
        quality_hint = QLabel(
            "默认使用当前可用最高画质；单房间画质可在直播工作台设置，下次拉流生效。"
        )
        quality_hint.setObjectName("MetaLabel")
        quality_hint.setWordWrap(True)
        defaults.body.addWidget(quality_hint)
        live.addWidget(defaults)
        limits = SectionCard("录制并发与空间")
        self._number("live.max_concurrent", limits, "同时录制", 1, 4)
        self._number("live.minimum_free_bytes", limits, "保留空间", 1, 1024, " GiB")
        limits.body.addWidget(
            Notice(
                "应用退出或电脑睡眠时无法录制；断线后会重新拉流，缺失内容无法补录。",
                "warning",
            )
        )
        live.addWidget(limits)
        engines = SectionCard("媒体工具")
        self._ffmpeg_path = QLineEdit()
        self._controls["ffmpeg_path"] = self._ffmpeg_path
        self._ffmpeg_path.setPlaceholderText("留空自动检测内置版本或系统 FFmpeg")
        self._field(
            "ffmpeg_path", engines, "FFmpeg", self._path_row(self._ffmpeg_path, False)
        )
        self._recorder_path = QLineEdit()
        self._controls["live.recorder_path"] = self._recorder_path
        self._recorder_path.setPlaceholderText("full 包自动检测；lite 包选择配套引擎")
        self._field(
            "live.recorder_path",
            engines,
            "录制引擎",
            self._path_row(self._recorder_path, False),
        )
        probe_row = QHBoxLayout()
        for kind, text in (("ffmpeg", "检查 FFmpeg"), ("recorder", "检查录制引擎")):
            button = QPushButton(text)
            button.clicked.connect(
                lambda _checked=False, k=kind, b=button: self._probe(k, b)
            )
            probe_row.addWidget(button)
        probe_row.addStretch()
        engines.body.addLayout(probe_row)
        self._probe_notice = Notice("可检测当前填写的路径；检测不会保存草稿。")
        engines.body.addWidget(self._probe_notice)
        tools.addWidget(engines)
        storage = SectionCard("断点缓存")
        storage.body.addWidget(
            Notice(
                "清理前请暂停全部下载。清理只删除未完成的断点缓存，保留已保存媒体。",
                "warning",
            )
        )
        clear = QPushButton("清理下载缓存")
        clear.setObjectName("DangerButton")
        clear.clicked.connect(self.cache_requested.emit)
        storage.body.addWidget(clear, alignment=Qt.AlignLeft)
        tools.addWidget(storage)
        for column in (download, live, tools):
            column.addStretch()
        self._notice = Notice()
        layout.addWidget(self._notice)
        footer = QHBoxLayout()
        self._draft_label = QLabel("所有修改已保存")
        self._draft_label.setObjectName("MetaLabel")
        footer.addWidget(self._draft_label, 1)
        self._reset_btn = QPushButton("撤销修改")
        self._reset_btn.clicked.connect(lambda: self.load_settings(self._settings))
        footer.addWidget(self._reset_btn)
        self._save_btn = QPushButton("保存设置")
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.clicked.connect(self._accept_if_valid)
        footer.addWidget(self._save_btn)
        if not self._embedded:
            cancel = QPushButton("取消")
            cancel.clicked.connect(self.reject)
            footer.addWidget(cancel)
        layout.addLayout(footer)

    def _tab(self, name):
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(20)
        self.tabs.addTab(scroll_area(body), name)
        return column

    def _field(self, key, card, label, control):
        row = FieldRow(label, control)
        self._field_rows[key] = row
        card.body.addWidget(row)
        return row

    def _entry(self, key, card, label):
        entry = QLineEdit()
        self._controls[key] = entry
        self._field(key, card, label, entry)
        return entry

    def _combo(self, key, card, label, values):
        combo = ComboBox()
        for text, value in values:
            combo.addItem(text, value)
        self._controls[key] = combo
        self._field(key, card, label, combo)
        return combo

    def _number(self, key, card, label, low, high, suffix=""):
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        self._controls[key] = spin
        row, down, up = stepper(spin)
        self._field(key, card, label, row)
        return spin, down, up

    def _path_row(self, entry, folder):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(entry, 1)
        browse = QPushButton("选择…")
        browse.clicked.connect(lambda: self._browse(entry, folder))
        layout.addWidget(browse)
        return row

    def _browse(self, entry, folder):
        value = (
            QFileDialog.getExistingDirectory(self, "选择保存目录", entry.text())
            if folder
            else QFileDialog.getOpenFileName(self, "选择可执行文件", entry.text())[0]
        )
        if value:
            entry.setText(value)
            entry.setToolTip(value)
            entry.setCursorPosition(0)

    def load_settings(self, settings):
        self._settings = settings.model_copy(deep=True)
        for key, control in self._controls.items():
            value = (
                getattr(settings.live, key.split(".")[1])
                if key.startswith("live.")
                else getattr(settings, key)
            )
            if key == "live.segment_seconds":
                value //= 60
            elif key == "live.minimum_free_bytes":
                value //= 1024**3
            control.blockSignals(True)
            if isinstance(control, QLineEdit):
                control.setText(value)
                control.setToolTip(value)
                control.setCursorPosition(0)
            elif isinstance(control, QComboBox):
                control.setCurrentIndex(max(0, control.findData(value)))
            elif isinstance(control, QCheckBox):
                control.setChecked(value)
            else:
                control.setValue(value)
            control.blockSignals(False)
            # Stepper endpoints must also update after loading a blocked spinbox.
            if isinstance(control, QSpinBox):
                control.valueChanged.emit(control.value())
        for row in self._field_rows.values():
            row.set_error("")
        self._notice.set_message("")
        self._draft_changed()

    def _draft_values(self):
        values = {}
        for key, control in self._controls.items():
            if isinstance(control, QLineEdit):
                value = control.text().strip()
            elif isinstance(control, QComboBox):
                value = control.currentData()
            elif isinstance(control, QCheckBox):
                value = control.isChecked()
            else:
                value = control.value()
            if key == "live.segment_seconds":
                value = (
                    self._settings.live.segment_seconds
                    if value == self._settings.live.segment_seconds // 60
                    else value * 60
                )
            elif key == "live.minimum_free_bytes":
                value = (
                    self._settings.live.minimum_free_bytes
                    if value == self._settings.live.minimum_free_bytes // 1024**3
                    else value * 1024**3
                )
            values[key] = value
        values["download_subtitle"] |= values["download_all_subtitles"]
        return values

    def get_settings(self):
        draft = self._settings.model_copy(deep=True)
        for key, value in self._draft_values().items():
            if key.startswith("live."):
                setattr(draft.live, key.split(".")[1], value)
            else:
                setattr(draft, key, value)
        return draft

    def merge_into(self, latest):
        draft = self.get_settings()
        merged = latest.model_copy(deep=True)
        for key in self._controls:
            if key.startswith("live."):
                field = key.split(".")[1]
                if getattr(draft.live, field) != getattr(self._settings.live, field):
                    setattr(merged.live, field, getattr(draft.live, field))
            elif getattr(draft, key) != getattr(self._settings, key):
                setattr(merged, key, getattr(draft, key))
        return merged

    @property
    def dirty(self):
        # Invalid text is still an editable draft; validate only on save.
        return any(
            value
            != (
                getattr(self._settings.live, key.split(".")[1])
                if key.startswith("live.")
                else getattr(self._settings, key)
            )
            for key, value in self._draft_values().items()
        )

    def _draft_changed(self, *_args):
        dirty = self.dirty
        self._draft_label.setText("有未保存的修改" if dirty else "所有修改已保存")
        self._reset_btn.setEnabled(dirty)
        self._save_btn.setEnabled(dirty or not self._embedded)
        self.dirty_changed.emit(dirty)

    def validate(self):
        for row in self._field_rows.values():
            row.set_error("")
        checks = [
            (
                self._output_dir,
                bool(self._output_dir.text().strip()),
                "请选择有效的下载保存目录",
            ),
            (
                self._live_directory,
                bool(self._live_directory.text().strip()),
                "请选择有效的录制保存目录",
            ),
        ]
        for entry in (self._ffmpeg_path, self._recorder_path):
            checks.append(
                (
                    entry,
                    not entry.text().strip()
                    or Path(entry.text().strip()).expanduser().is_file(),
                    "工具路径不是有效文件",
                )
            )
        for entry, valid, message in checks:
            if not valid:
                self._show_validation(entry, message)
                return False
        values = {
            key: key
            for key in (
                "title",
                "author",
                "bvid",
                "page",
                "part",
                "part_suffix",
                "collection",
                "series",
                "season",
                "section",
                "episode",
                "episode_number",
                "quality",
                "codec",
            )
        }
        for entry in (self._path_template, self._bangumi_path_template):
            try:
                render_path_template(entry.text(), values)
            except ValueError as exc:
                self._show_validation(entry, str(exc))
                return False
        self._notice.set_message("")
        return True

    def _show_validation(self, entry, message):
        tab = (
            1
            if entry is self._live_directory
            else 2
            if entry in (self._ffmpeg_path, self._recorder_path)
            else 0
        )
        self.tabs.setCurrentIndex(tab)
        self._notice.set_message(message, "danger")
        for key, control in self._controls.items():
            if control is entry and key in self._field_rows:
                row = self._field_rows[key]
                row.set_error(message)
                self.tabs.currentWidget().ensureWidgetVisible(row)
                break
        entry.setFocus()

    def _accept_if_valid(self):
        if self.validate():
            self.save_requested.emit() if self._embedded else self.accept()

    def _probe(self, kind, button):
        if kind in self._probes:
            return
        button.setEnabled(False)
        signals = _ProbeSignals(self)
        entry = self._ffmpeg_path if kind == "ffmpeg" else self._recorder_path
        requested_path = entry.text().strip()
        runner = _ProbeRunner(signals, kind, requested_path)
        self._probes[kind] = (signals, runner)

        def finished(ok, message):
            button.setEnabled(True)
            if entry.text().strip() != requested_path:
                self._probe_notice.set_message(
                    "检查期间路径已修改，请再次检查当前路径。", "warning"
                )
            else:
                self._probe_notice.set_message(message, "success" if ok else "danger")
            self._probes.pop(kind, None)

        signals.finished.connect(finished)
        self._probe_notice.set_message("正在检查媒体工具…")
        QThreadPool.globalInstance().start(runner)
