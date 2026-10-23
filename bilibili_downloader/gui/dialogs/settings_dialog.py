"""Reusable settings editor with an isolated draft and field-level merging."""

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader import __version__
from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    WORKSPACE_NAMES,
    AppSettings,
    OutputMode,
    UpdateChannel,
    VideoQuality,
    WindowCloseAction,
)
from bilibili_downloader.core.recorder import check_recorder, find_recorder
from bilibili_downloader.gui.dialogs.file_picker import file_picker
from bilibili_downloader.gui.resources.paths import background_path
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.settings_sections import APPEARANCE_MODES, SettingsSection
from bilibili_downloader.gui.widgets.appearance_preview import ThemePreviewButton
from bilibili_downloader.gui.widgets.background_effects import GlassBlurControl
from bilibili_downloader.gui.widgets.background_picker import BackgroundPicker
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    ActionBar,
    CollapsibleSection,
    ElidedLabel,
    FieldRow,
    Notice,
    ResponsiveFields,
    SectionCard,
    help_text,
    scroll_area,
    stepper,
)
from bilibili_downloader.gui.widgets.download_options import (
    DownloadOptionCard,
    DownloadOptions,
)
from bilibili_downloader.gui.widgets.workspace_background import WorkspaceStack
from bilibili_downloader.utils.validators import render_path_template


def _setting_value(settings, key):
    for field in key.split("."):
        settings = getattr(settings, field)
    return settings


def _set_setting_value(settings, key, value):
    fields = key.split(".")
    for field in fields[:-1]:
        settings = getattr(settings, field)
    setattr(settings, fields[-1], value)


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
    update_check_requested = Signal(object)
    update_install_requested = Signal()
    update_cancel_requested = Signal()
    update_archive_requested = Signal()
    update_page_requested = Signal()
    update_channel_changed = Signal()
    dirty_changed = Signal(bool)
    appearance_mode_requested = Signal(str)

    def __init__(self, settings: AppSettings, parent=None, embedded=False, background_store=None, *, desktop_platform=None):
        super().__init__(parent)
        self._embedded = embedded
        self._desktop_platform = desktop_platform or sys.platform
        self.setObjectName("SettingsEditor")
        self.setProperty("embedded", embedded)
        self._settings = settings.model_copy(deep=True)
        self._controls = {}
        self._field_rows = {}
        self._probes = {}
        self._background_store = background_store
        self._background_pickers = {}
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
        self._sections = {}
        download, live, appearance, tools, updates = [
            self._tab(name, section) for name, section in (
                ("下载", SettingsSection.DOWNLOAD),
                ("直播", SettingsSection.LIVE), ("外观", SettingsSection.APPEARANCE),
                ("工具与存储", SettingsSection.TOOLS), ("关于与更新", SettingsSection.ABOUT),
            )
        ]
        paths = SectionCard("保存位置")
        self._output_dir = _LeadingPathLineEdit()
        self._controls["output_dir"] = self._output_dir
        self._field(
            "output_dir", paths, "保存目录", self._path_row(self._output_dir, True)
        )
        download.addWidget(paths)
        recognition = SectionCard("来源识别")
        self._clipboard_check = QCheckBox("前台识别剪贴板中的 B 站内容")
        self._controls["clipboard_monitor_enabled"] = self._clipboard_check
        recognition.body.addWidget(self._clipboard_check)
        recognition.body.addWidget(help_text("启动和切回前台时也会检查已复制的内容；确认后才联网解析。"))
        download.addWidget(recognition)
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
        format_fields = ResponsiveFields(column_width=430)
        for key in ("default_output_mode", "default_quality", "default_video_codec",
                    "default_audio_quality", "max_concurrent_downloads"):
            row = self._field_rows[key]
            row.setMinimumWidth(row.maximumWidth())
            formats.body.removeWidget(row)
            format_fields.add_field(row)
        formats.body.addWidget(format_fields)
        download.addWidget(formats)
        options = SectionCard("归档附加内容")
        for key, label, description, icon, attr in (
            ("download_danmaku", "下载弹幕", "ASS", "star", "_danmaku_check"),
            ("download_subtitle", "下载字幕", "SRT", "info", "_subtitle_check"),
            ("download_cover", "保存封面", "图片", "folder", "_cover_check"),
            ("download_metadata", "保存元数据", "JSON", "tasks", "_metadata_check"),
        ):
            control = DownloadOptionCard(label, description, icon)
            self._controls[key] = control
            setattr(self, attr, control)
        self._all_subtitles_check = QCheckBox("全部字幕")
        self._controls["download_all_subtitles"] = self._all_subtitles_check
        self._subtitle_check.toggled.connect(self._all_subtitles_check.setEnabled)
        self._subtitle_check.toggled.connect(
            lambda checked: self._all_subtitles_check.setChecked(False) if not checked else None
        )
        self._all_subtitles_check.toggled.connect(
            lambda checked: self._subtitle_check.setChecked(True) if checked else None
        )
        options.body.addWidget(DownloadOptions(
            self._danmaku_check, self._subtitle_check, self._all_subtitles_check,
            self._cover_check, self._metadata_check, max_columns=2,
        ))
        download.addWidget(options)
        self._templates_section = CollapsibleSection("高级命名与目录模板")
        self._template_previews = {}
        for key, label, attr in (
            ("path_template", "目录模板", "_path_template"),
            ("bangumi_path_template", "番剧模板", "_bangumi_path_template"),
        ):
            entry = self._entry(key, self._templates_section, label)
            setattr(self, attr, entry)
            preview = help_text("")
            self._template_previews[key] = preview
            self._templates_section.body.addWidget(preview)
            entry.textChanged.connect(self._update_template_previews)
        self._path_template.setPlaceholderText("{author}/{title}{part_suffix}")
        self._templates_section.body.addWidget(help_text(
            "支持 title、author、bvid、part_suffix、collection 和番剧章节字段；扩展名由输出格式决定。"
        ))
        download.addWidget(self._templates_section)
        defaults = SectionCard("默认录制位置与分段")
        self._review_directories_button = QPushButton("核对旧房间目录")
        self._review_directories_button.setObjectName("TextButton")
        self._review_directories_button.clicked.connect(
            lambda: self.tabs.widget(self._sections[SettingsSection.LIVE]).ensureWidgetVisible(self._directory_review)
        )
        self._review_directories_button.hide()
        defaults.header.addWidget(self._review_directories_button)
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
            help_text("跟随全局的房间在下一场使用此目录；本场录制继续保存在原位置。分段时长用于新增房间。")
        )
        self._auto_merge_live = QCheckBox("录制结束后自动合并 MP4")
        self._controls["live.auto_merge_mp4"] = self._auto_merge_live
        defaults.body.addWidget(self._auto_merge_live)
        defaults.body.addWidget(help_text("正常下播或手动停止后合并到场次目录，保留原始分段。"))
        quality_hint = QLabel(
            "默认使用当前可用最高画质；单房间画质可在直播工作台设置，下次拉流生效。"
        )
        quality_hint.setObjectName("MetaLabel")
        quality_hint.setWordWrap(True)
        defaults.body.addWidget(quality_hint)
        live.addWidget(defaults)
        self._directory_review = SectionCard("核对已有房间的保存位置")
        self._directory_review.body.addWidget(Notice(
            "旧版本未记录目录来源。请逐个选择跟随全局或保留独立目录，保存前继续使用原位置。", "warning"
        ))
        self._directory_choices = {}
        self._live_directory.textChanged.connect(self._update_directory_previews)
        self._directory_review.hide()
        live.addWidget(self._directory_review)
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
        self._ffmpeg_path = QLineEdit()
        self._controls["ffmpeg_path"] = self._ffmpeg_path
        self._ffmpeg_path.setPlaceholderText("留空自动检测内置版本或系统 FFmpeg")
        self._recorder_path = QLineEdit()
        self._controls["live.recorder_path"] = self._recorder_path
        self._recorder_path.setPlaceholderText("full 包自动检测；lite 包选择配套引擎")
        self._probe_notices = {}
        engines = SectionCard("工具路径")
        tools.addWidget(engines)
        for kind, text in (("ffmpeg", "检查 FFmpeg"), ("recorder", "检查录制引擎")):
            key = "ffmpeg_path" if kind == "ffmpeg" else "live.recorder_path"
            entry = self._controls[key]
            path_row = self._path_row(entry, False)
            self._field(key, engines, "FFmpeg" if kind == "ffmpeg" else "录制引擎", path_row)
            button = QPushButton("检测")
            button.setAccessibleName(text)
            button.setObjectName("TextButton")
            button.clicked.connect(
                lambda _checked=False, k=kind, b=button: self._probe(k, b)
            )
            path_row.layout().addWidget(button)
            notice = Notice()
            self._probe_notices[kind] = notice
            entry.textChanged.connect(lambda _text, n=notice: n.set_message(""))
            engines.body.addWidget(notice)
        engines.body.addWidget(help_text("检测使用当前草稿路径，不会自动保存设置。"))
        self._probe_notice = self._probe_notices["ffmpeg"]
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
        identity = SectionCard("BiliFlow · 星轨收藏站")
        description = QLabel("视频下载、批量导入与直播录制，统一的本地收藏工作台。")
        description.setWordWrap(True)
        description.setObjectName("MetaLabel")
        identity.body.addWidget(description)
        update_card = SectionCard("软件更新")
        version = QLabel(f"当前版本：v{__version__}")
        version.setObjectName("MetaLabel")
        update_card.body.addWidget(version)
        self._auto_update_check = QCheckBox("打开软件时自动检查更新")
        self._controls["auto_check_updates"] = self._auto_update_check
        update_card.body.addWidget(self._auto_update_check)
        self._update_channel = self._combo(
            "update_channel", update_card, "更新通道",
            [("仅更新正式版", UpdateChannel.STABLE), ("更新最新版（包含 beta、rc 版）", UpdateChannel.LATEST)],
        )
        self._update_channel.currentIndexChanged.connect(lambda *_args: self.update_channel_changed.emit())
        update_card.body.addWidget(help_text("启动检查使用已保存设置；手动检查使用当前通道，也能查看已跳过的版本。"))
        self._update_notice = Notice()
        update_card.body.addWidget(self._update_notice)
        self._update_progress = QProgressBar()
        self._update_progress.setRange(0, 100)
        self._update_progress.hide()
        update_card.body.addWidget(self._update_progress)
        update_actions = QHBoxLayout()
        self._check_update_btn = QPushButton("检查更新")
        self._check_update_btn.setObjectName("PrimaryButton")
        self._check_update_btn.clicked.connect(lambda: self.update_check_requested.emit(self._update_channel.currentData()))
        update_card.header.addWidget(self._check_update_btn)
        self._install_update_btn = QPushButton("安装并重启")
        self._install_update_btn.setObjectName("PrimaryButton")
        self._install_update_btn.clicked.connect(self.update_install_requested.emit)
        self._install_update_btn.hide()
        self._cancel_update_btn = QPushButton("取消下载")
        self._cancel_update_btn.clicked.connect(self.update_cancel_requested.emit)
        self._cancel_update_btn.hide()
        for button in (self._install_update_btn, self._cancel_update_btn):
            update_actions.addWidget(button)
        update_actions.addStretch()
        update_card.body.addLayout(update_actions)
        self._open_update_archive = QPushButton("打开已下载更新包")
        self._open_update_archive.clicked.connect(self.update_archive_requested.emit)
        self._open_update_archive.hide()
        update_card.body.addWidget(self._open_update_archive, alignment=Qt.AlignLeft)
        release_page = QPushButton("打开版本下载页")
        release_page.setObjectName("TextButton")
        release_page.clicked.connect(self.update_page_requested.emit)
        update_card.body.addWidget(release_page, alignment=Qt.AlignLeft)
        updates.addWidget(update_card)
        updates.addWidget(identity)
        mode_card = SectionCard("显示模式 · 立即生效")
        self._mode_buttons = QButtonGroup(self)
        modes = QHBoxLayout()
        for index, (label, mode) in enumerate(APPEARANCE_MODES):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("SegmentButton")
            button.setAccessibleName(f"外观模式：{label}")
            button.setMinimumWidth(100)
            button.setMaximumWidth(144)
            self._mode_buttons.addButton(button, index)
            modes.addWidget(button)
        self._mode_buttons.idClicked.connect(
            lambda index: self.appearance_mode_requested.emit(APPEARANCE_MODES[index][1])
        )
        modes.addStretch()
        mode_card.body.addLayout(modes)
        appearance.addWidget(mode_card)
        if self._desktop_platform == "win32":
            window_card = SectionCard("窗口")
            self._combo(
                "windows_close_action", window_card, "关闭窗口时",
                [("每次询问", WindowCloseAction.ASK),
                 ("最小化到系统托盘", WindowCloseAction.TRAY),
                 ("彻底退出", WindowCloseAction.QUIT)],
            )
            appearance.addWidget(window_card)
        theme = SectionCard("应用配色 · 保存后生效")
        self._theme_combo = self._combo(
            "appearance.theme", theme, "主题",
            [("星河", "star_trail"), ("晴海", "bilibili_blue")],
        )
        self._theme_combo.setItemData(0, "粉紫星空，支持日间与夜间", Qt.ToolTipRole)
        self._theme_combo.setItemData(1, "晴空青蓝与柔粉微光，支持日间与夜间", Qt.ToolTipRole)
        self._field_rows["appearance.theme"].hide()
        previews = QHBoxLayout()
        self._theme_buttons = QButtonGroup(self)
        for index, (name, description, theme_id) in enumerate((
            ("星河", "粉紫星空 · 温暖柔和", "star_trail"),
            ("晴海", "晴空青蓝 · 柔粉微光", "bilibili_blue"),
        )):
            button = ThemePreviewButton(name, description, theme_id)
            self._theme_buttons.addButton(button, index)
            previews.addWidget(button, 1)
        self._theme_buttons.idClicked.connect(self._theme_combo.setCurrentIndex)
        self._theme_combo.currentIndexChanged.connect(self._sync_appearance_preview)
        theme.body.addLayout(previews)
        appearance.addWidget(theme)
        glass = SectionCard("玻璃效果 · 保存后生效")
        self._glass_card = glass
        self._glass_blur = GlassBlurControl()
        self._controls["appearance.glass_blur"] = self._glass_blur
        glass.body.addWidget(self._glass_blur)
        self._glass_preview = WorkspaceStack()
        self._glass_preview.setFixedHeight(160)
        example_page = QWidget()
        example_layout = QVBoxLayout(example_page)
        example_layout.setContentsMargins(16, 16, 16, 16)
        example_card = SectionCard("玻璃效果预览")
        example_card.body.addWidget(help_text("背景保留细节，文字清晰可读。"))
        example_layout.addWidget(example_card)
        example_layout.addStretch()
        self._glass_preview.addWidget(example_page)
        self._glass_preview.set_background(background_path(BUILTIN_BACKGROUNDS[0].reference), builtin=True)
        glass.body.addWidget(self._glass_preview)
        glass.body.addWidget(help_text("应用于所有工作区的图片背景。"))
        self._glass_blur.valueChanged.connect(self._sync_glass_blur)
        appearance.addWidget(glass)
        self._background_grid = QGridLayout()
        self._background_grid.setSpacing(16)
        self._background_cards = []
        self._appearance_columns = 0
        appearance.addLayout(self._background_grid)
        for workspace, title in zip(WORKSPACE_NAMES, ("视频下载", "直播录制", "任务中心", "设置")):
            card = SectionCard(f"{title}背景")
            picker = BackgroundPicker(title, self._background_store, workspace=workspace)
            picker.changed.connect(self._draft_changed)
            card.body.addWidget(picker)
            self._background_cards.append(card)
            self._background_pickers[workspace] = picker
        self._layout_background_cards()
        appearance.addWidget(help_text("背景在保存设置后生效。四个页面独立设置，支持小流图库和 PNG、JPEG、WebP 图片，以及深浅模式可见度调节。"))
        for column in (download, live, tools, updates, appearance):
            column.addStretch()
        self._notice = Notice()
        layout.addWidget(self._notice)
        self._action_bar = ActionBar(compact=True)
        self._action_bar.setAccessibleName("设置保存操作")
        footer = self._action_bar.row
        self._draft_label = ElidedLabel("所有修改已保存")
        self._draft_label.setObjectName("MetaLabel")
        footer.addWidget(self._draft_label, 1)
        self._reset_btn = QPushButton("撤销修改")
        self._reset_btn.setObjectName("OutputSecondaryButton")
        self._reset_btn.clicked.connect(lambda: self.load_settings(self._settings))
        footer.addWidget(self._reset_btn)
        self._save_btn = QPushButton("保存设置")
        self._save_btn.setAutoDefault(not self._embedded)
        self._save_btn.setDefault(not self._embedded)
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.setMinimumWidth(128)
        self._save_btn.setFixedHeight(44)
        self._save_btn.clicked.connect(self._accept_if_valid)
        if not self._embedded:
            cancel = QPushButton("取消")
            cancel.setObjectName("OutputSecondaryButton")
            cancel.clicked.connect(self.reject)
            footer.addWidget(cancel)
        footer.addWidget(self._save_btn)
        layout.addWidget(self._action_bar)

    def _sync_appearance_preview(self, *_args):
        index = self._theme_combo.currentIndex()
        button = self._theme_buttons.button(index)
        if button:
            button.setChecked(True)
        for picker in self._background_pickers.values():
            picker.set_theme(self._theme_combo.currentData())

    def _sync_glass_blur(self, *_args):
        value = self._glass_blur.value()
        self._glass_preview.set_glass_blur(value)
        for picker in self._background_pickers.values():
            picker.set_glass_blur(value)

    def _update_template_previews(self, *_args):
        values = dict(title="星轨旅记", author="示例UP主", bvid="BV1DEMO", page="1",
                      part="正片", part_suffix="_P1", collection="城市漫游", quality="1080P",
                      codec="HEVC", series="示例番剧", season="第一季", section="正片",
                      episode="出发", episode_number="01")
        for key, preview in self._template_previews.items():
            try:
                path = render_path_template(self._controls[key].text(), values)
                preview.setText(f"示例路径：{path}")
            except ValueError as exc:
                preview.setText(f"示例暂不可用：{exc}")

    def _layout_background_cards(self):
        columns = 2 if self.width() >= 960 else 1
        if columns == self._appearance_columns:
            return
        self._appearance_columns = columns
        for index, card in enumerate(self._background_cards):
            self._background_grid.removeWidget(card)
            self._background_grid.addWidget(card, index // columns, index % columns)
        self._background_grid.setColumnStretch(0, 1)
        self._background_grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event):
        if hasattr(self, "_background_grid"):
            self._layout_background_cards()
        super().resizeEvent(event)

    def set_update_busy(self, busy, kind):
        self._check_update_btn.setEnabled(not busy)
        self._install_update_btn.setEnabled(not busy)
        self._update_progress.setRange(0, 0 if busy and kind == "stage" else 100)
        self._update_progress.setVisible(busy and kind in ("download", "stage"))
        self._cancel_update_btn.setVisible(busy and kind in ("download", "stage"))
        self._cancel_update_btn.setText("取消下载" if kind == "download" else "取消准备")

    def set_pending_update(self, prepared):
        self._install_update_btn.setVisible(prepared is not None and not prepared.reason)
        self._open_update_archive.setVisible(prepared is not None)

    def _tab(self, name, section):
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(16)
        self._sections[section] = self.tabs.addTab(scroll_area(body), name)
        return column

    def show_section(self, section):
        self.tabs.setCurrentIndex(self._sections[SettingsSection(section)])

    @property
    def current_section(self):
        return next(section for section, index in self._sections.items() if index == self.tabs.currentIndex())

    def sync_appearance_mode(self, mode):
        """Rebase the immediate preference without replacing any other draft."""
        self._settings.appearance.mode = mode
        index = next(i for i, (_, value) in enumerate(APPEARANCE_MODES) if value == mode)
        self._mode_buttons.button(index).setChecked(True)
        self._draft_changed()

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
        combo.setMaximumWidth(UI_METRICS.short_field_width)
        self._field_rows[key].setMaximumWidth(104 + UI_METRICS.short_field_width)
        return combo

    def _number(self, key, card, label, low, high, suffix=""):
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        self._controls[key] = spin
        row, down, up = stepper(spin)
        self._field(key, card, label, row)
        row.setMaximumWidth(UI_METRICS.number_field_width)
        self._field_rows[key].setMaximumWidth(104 + UI_METRICS.number_field_width)
        return spin, down, up

    def _path_row(self, entry, folder):
        # Directories share one picker interaction; executable paths remain editable.
        entry.setReadOnly(folder)
        row = QWidget()
        row.setFocusProxy(entry)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(entry, 1)
        browse = QPushButton("选择…")
        browse.clicked.connect(lambda: self._browse(entry, folder))
        layout.addWidget(browse)
        return row

    def _browse(self, entry, folder):
        def selected(value):
            entry.setText(value)
            entry.setToolTip(value)
            entry.setCursorPosition(0)
        picker = file_picker(self)
        if folder:
            picker.directory("选择保存目录", entry.text(), selected)
        else:
            picker.open_file("选择可执行文件", entry.text(), "", selected)

    def load_settings(self, settings, *, keep_directory_choices=False):
        previous_channel = self._update_channel.currentData()
        self._settings = settings.model_copy(deep=True)
        for _, choice in (() if keep_directory_choices else getattr(self, "_directory_choices", {}).values()):
            choice.blockSignals(True)
            choice.setCurrentIndex(0)
            choice.blockSignals(False)
        for key, control in self._controls.items():
            value = _setting_value(settings, key)
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
        for workspace, picker in self._background_pickers.items():
            picker.set_reference(getattr(settings.appearance.backgrounds, workspace))
            picker.set_visibility(getattr(settings.appearance.background_visibility, workspace))
        self._notice.set_message("")
        for notice in self._probe_notices.values():
            notice.set_message("")
        self._update_directory_previews()
        self._draft_changed()
        self._sync_appearance_preview()
        self._sync_glass_blur()
        self.sync_appearance_mode(settings.appearance.mode)
        self._all_subtitles_check.setEnabled(self._subtitle_check.isChecked())
        self._update_template_previews()
        if previous_channel != self._update_channel.currentData():
            self.update_channel_changed.emit()

    def sync_close_action(self, action):
        """Rebase just this preference without overwriting other edited fields."""
        self._settings.windows_close_action = action
        control = self._controls.get("windows_close_action")
        if control is not None:
            control.blockSignals(True)
            control.setCurrentIndex(control.findData(action))
            control.blockSignals(False)
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
        for workspace, picker in self._background_pickers.items():
            values[f"appearance.backgrounds.{workspace}"] = picker.reference
            for mode in ("light", "dark"):
                values[f"appearance.background_visibility.{workspace}.{mode}"] = getattr(
                    picker.visibility, mode
                )
        values["download_subtitle"] |= values["download_all_subtitles"]
        return values

    def get_settings(self):
        draft = self._settings.model_copy(deep=True)
        for key, value in self._draft_values().items():
            _set_setting_value(draft, key, value)
        return draft

    def merge_into(self, latest):
        draft = self.get_settings()
        merged = latest.model_copy(deep=True)
        for key in self._draft_values():
            value = _setting_value(draft, key)
            if value != _setting_value(self._settings, key):
                _set_setting_value(merged, key, value)
        return merged

    @property
    def dirty(self):
        # Invalid text is still an editable draft; validate only on save.
        return bool(self.directory_modes()) or any(
            picker.busy or picker.prepared is not None
            for picker in self._background_pickers.values()
        ) or any(
            value
            != _setting_value(self._settings, key)
            for key, value in self._draft_values().items()
        )

    def set_live_rooms(self, rows):
        """Keep a migration draft stable while live snapshots refresh."""
        legacy = {row["room_id"]: row for row in rows if row.get("output_dir_mode", "known") is None}
        changed = set(self._directory_choices) != legacy.keys()
        for room_id in set(self._directory_choices) - legacy.keys():
            field, _ = self._directory_choices.pop(room_id)
            self._directory_review.body.removeWidget(field)
            field.deleteLater()
        for room_id, row in legacy.items():
            if room_id in self._directory_choices:
                continue
            choice = ComboBox()
            choice.addItem("待确认 · 暂用原目录", None)
            choice.addItem("跟随全局保存目录", "default")
            choice.addItem("保留独立目录", "custom")
            choice.setMinimumWidth(180)
            field = QWidget()
            heading = QHBoxLayout(field)
            heading.setContentsMargins(0, 0, 0, 0)
            room_name = ElidedLabel(f"{row['author'] or '未命名直播间'} · 房间 {room_id}")
            heading.addWidget(room_name, 1)
            heading.addWidget(choice)
            field.setToolTip(row["output_dir"])
            # Show the original path without forcing the settings page wider.
            wrapper = QWidget()
            column = QVBoxLayout(wrapper)
            column.setContentsMargins(0, 0, 0, 0)
            column.addWidget(field)
            path = ElidedLabel(f"原目录：{row['output_dir']}")
            path.setObjectName("MetaLabel")
            column.addWidget(path)
            wrapper.original_directory = row["output_dir"]
            wrapper.preview = ElidedLabel("下一场：等待核对")
            wrapper.preview.setObjectName("MetaLabel")
            column.addWidget(wrapper.preview)
            self._directory_review.body.addWidget(wrapper)
            self._directory_choices[room_id] = (wrapper, choice)
            choice.currentIndexChanged.connect(self._draft_changed)
            choice.currentIndexChanged.connect(self._update_directory_previews)
        self._directory_review.setVisible(bool(legacy))
        self._review_directories_button.setText(f"核对 {len(legacy)} 个旧房间")
        self._review_directories_button.setVisible(bool(legacy))
        if changed:
            self._draft_changed()

    def _update_directory_previews(self, *_args):
        for wrapper, choice in self._directory_choices.values():
            mode = choice.currentData()
            path = self._live_directory.text().strip() if mode == "default" else wrapper.original_directory
            wrapper.preview.set_full_text(f"下一场：{path}" if mode else "下一场：待确认，继续使用原目录")

    def directory_modes(self):
        return {room_id: choice.currentData() for room_id, (_, choice) in self._directory_choices.items()
                if choice.currentData() is not None}

    def _draft_changed(self, *_args):
        dirty = self.dirty
        self._draft_label.set_full_text("有未保存的修改" if dirty else "所有修改已保存")
        self._reset_btn.setEnabled(dirty)
        self._save_btn.setEnabled(
            (dirty or not self._embedded)
            and not any(picker.busy for picker in self._background_pickers.values())
        )
        self.dirty_changed.emit(dirty)

    def validate(self):
        if any(picker.busy for picker in self._background_pickers.values()):
            self._notice.set_message("图片正在读取，请稍后保存。", "warning")
            return False
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
                bool(self._live_directory.text().strip()) and not Path(self._live_directory.text().strip()).expanduser().is_file(),
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

    def install_backgrounds(self, store):
        for picker in self._background_pickers.values():
            if picker.prepared is not None:
                store.install(picker.prepared)

    def _show_validation(self, entry, message):
        section = (
            SettingsSection.LIVE if entry is self._live_directory else
            SettingsSection.TOOLS if entry in (self._ffmpeg_path, self._recorder_path) else
            SettingsSection.DOWNLOAD
        )
        self.show_section(section)
        if entry in (self._path_template, self._bangumi_path_template):
            self._templates_section.set_expanded(True)
        self._notice.set_message(message, "danger")
        for key, control in self._controls.items():
            if control is entry and key in self._field_rows:
                row = self._field_rows[key]
                row.set_error(message)
                scroll = self.tabs.currentWidget()
                # Expansion and error text change the layout on the next pass.
                QTimer.singleShot(0, scroll, lambda: scroll.ensureWidgetVisible(row, 0, 16))
                break
        entry.setFocus()

    def _accept_if_valid(self):
        if self.validate():
            self.save_requested.emit() if self._embedded else self.accept()

    def _probe(self, kind, button):
        if kind in self._probes:
            return
        button.setEnabled(False)
        button.setText("检测中…")
        notice = self._probe_notices[kind]
        self._probe_notice = notice
        signals = _ProbeSignals(self)
        entry = self._ffmpeg_path if kind == "ffmpeg" else self._recorder_path
        requested_path = entry.text().strip()
        runner = _ProbeRunner(signals, kind, requested_path)
        self._probes[kind] = (signals, runner)

        def finished(ok, message):
            button.setEnabled(True)
            button.setText("检测")
            if entry.text().strip() != requested_path:
                notice.set_message(
                    "检查期间路径已修改，请再次检查当前路径。", "warning"
                )
            else:
                notice.set_message(message, "success" if ok else "danger")
            self._probes.pop(kind, None)

        signals.finished.connect(finished)
        notice.set_message("正在检查当前路径…")
        QThreadPool.globalInstance().start(runner)
