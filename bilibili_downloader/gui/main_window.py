"""Main application window for the Bilibili Downloader."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThreadPool, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader import __version__
from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.cache import clear_download_cache, inspect_download_cache
from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    DownloadItem,
    OutputMode,
    TaskStatus,
    VideoInfo,
    VideoQuality,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.threads.download_worker import (
    DownloadRunner,
    DownloadWorker,
)
from bilibili_downloader.gui.threads.ffmpeg_worker import (
    FFmpegCheckRunner,
    FFmpegCheckWorker,
)
from bilibili_downloader.gui.threads.login_status_worker import (
    LoginStatusRunner,
    LoginStatusWorker,
)
from bilibili_downloader.gui.threads.resolve_worker import ResolveRunner, ResolveWorker
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.download_list import DownloadListWidget
from bilibili_downloader.gui.widgets.hero_panel import HeroPanel
from bilibili_downloader.gui.widgets.video_info import VideoInfoWidget
from bilibili_downloader.utils.config import ConfigManager
from bilibili_downloader.utils.validators import is_bilibili_url

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config_manager=None, task_repository=None):
        super().__init__()
        self.setWindowTitle("BiliFlow · 星轨下载站")
        self.setMinimumSize(900, 640)
        self.resize(1320, 860)
        # Components
        self._config = config_manager or ConfigManager()
        self._settings = self._config.load()
        self._task_repository = task_repository or TaskRepository(
            self._config.task_database_path
        )
        self._api_client = self._create_api_client()
        self._retired_api_clients = []
        self._download_pool = QThreadPool()
        self._service_pool = QThreadPool()
        self._service_pool.setMaxThreadCount(4)
        self._apply_thread_pool_settings()

        # State
        self._current_video: VideoInfo | None = None
        self._login_status_request_id = 0
        self._close_confirmed = False
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()
        self._restore_tasks()

        # Check login status on startup
        self._user_face = ""
        if self._settings.sessdata:
            self._update_login_status()

    def _create_api_client(self):
        """Create API client with current settings."""
        return BilibiliAPIClient(sessdata=self._settings.sessdata or None)

    def _apply_thread_pool_settings(self):
        """Apply user-configured concurrency limits."""
        max_downloads = max(1, min(8, self._settings.max_concurrent_downloads))
        self._download_pool.setMaxThreadCount(max_downloads)

    def _replace_api_client(self):
        """Swap credentials without invalidating in-flight worker requests."""
        previous = self._api_client
        self._api_client = self._create_api_client()
        self._retired_api_clients.append(previous)

    def _setup_ui(self):
        """Build the main UI layout."""
        central = QWidget()
        central.setObjectName("AppSurface")
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(212)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 22, 18, 18)
        side_layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setObjectName("BrandIcon")
        brand_icon.setPixmap(QIcon(asset_path("clapper.png")).pixmap(QSize(40, 40)))
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        brand_title = QLabel("BiliFlow")
        brand_title.setObjectName("BrandTitle")
        brand_caption = QLabel("星轨下载站")
        brand_caption.setObjectName("SidebarCaption")
        brand_copy.addWidget(brand_title)
        brand_copy.addWidget(brand_caption)
        brand_row.addWidget(brand_icon)
        brand_row.addLayout(brand_copy)
        brand_row.addStretch()
        side_layout.addLayout(brand_row)
        side_layout.addSpacing(20)

        section_label = QLabel("WORKSPACE")
        section_label.setObjectName("NavSection")
        side_layout.addWidget(section_label)
        home_btn = QPushButton("  首页 / HOME")
        home_btn.setObjectName("NavButtonActive")
        side_layout.addWidget(home_btn)
        batch_nav = QPushButton("  批量任务 / BATCH")
        batch_nav.setObjectName("NavButton")
        batch_nav.clicked.connect(self._on_batch_clicked)
        side_layout.addWidget(batch_nav)
        settings_nav = QPushButton("  下载设置 / CONFIG")
        settings_nav.setObjectName("NavButton")
        settings_nav.clicked.connect(self._on_settings_triggered)
        side_layout.addWidget(settings_nav)
        side_layout.addStretch()

        mascot_card = QFrame()
        mascot_card.setObjectName("MascotCard")
        mascot_layout = QVBoxLayout(mascot_card)
        mascot_layout.setContentsMargins(14, 14, 14, 14)
        mascot_layout.setSpacing(5)
        mascot_icon = QLabel()
        mascot_icon.setPixmap(QIcon(asset_path("alien.png")).pixmap(QSize(50, 50)))
        mascot_title = QLabel("次元传送已就绪")
        mascot_title.setObjectName("MascotTitle")
        mascot_text = QLabel("支持 8K · HDR · 弹幕 · 字幕")
        mascot_text.setObjectName("SidebarCaption")
        mascot_text.setWordWrap(True)
        mascot_layout.addWidget(mascot_icon)
        mascot_layout.addWidget(mascot_title)
        mascot_layout.addWidget(mascot_text)
        side_layout.addWidget(mascot_card)

        login_btn = QPushButton("登录 B 站账号")
        login_btn.setObjectName("SidebarAction")
        login_btn.clicked.connect(self._on_login_triggered)
        side_layout.addWidget(login_btn)
        shell.addWidget(sidebar)

        workspace = QWidget()
        workspace.setObjectName("Workspace")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(26, 22, 26, 16)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        page_copy = QVBoxLayout()
        page_copy.setSpacing(2)
        page_title = QLabel("下载控制台")
        page_title.setObjectName("PageTitle")
        page_caption = QLabel("把在线视频、MAD 与收藏，变成本地永久收藏")
        page_caption.setObjectName("Caption")
        page_copy.addWidget(page_title)
        page_copy.addWidget(page_caption)
        header_row.addLayout(page_copy)
        header_row.addStretch()
        self._header_login = QPushButton("未登录")
        self._header_login.setObjectName("GhostButton")
        self._header_login.clicked.connect(self._on_login_triggered)
        header_row.addWidget(self._header_login)
        layout.addLayout(header_row)

        hero = HeroPanel()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 26)
        hero_layout.setSpacing(10)
        eyebrow = QLabel("ANIME STREAM STUDIO  /  ONLINE")
        eyebrow.setObjectName("HeroEyebrow")
        hero_title = QLabel("喜欢的这一集，\n现在就带回本地。")
        hero_title.setObjectName("HeroTitle")
        hero_layout.addWidget(eyebrow)
        hero_layout.addWidget(hero_title)
        hero_layout.addStretch()

        url_layout = QHBoxLayout()
        url_layout.setSpacing(10)
        self._url_input = ChineseLineEdit()
        self._url_input.setObjectName("UrlInput")
        self._url_input.setPlaceholderText("粘贴 B 站链接、BV / AV 号或 b23.tv 短链")
        self._url_input.returnPressed.connect(self._on_resolve_clicked)
        url_layout.addWidget(self._url_input)
        self._resolve_btn = QPushButton("开始解析  →")
        self._resolve_btn.setObjectName("HeroButton")
        self._resolve_btn.clicked.connect(self._on_resolve_clicked)
        url_layout.addWidget(self._resolve_btn)
        hero_layout.addLayout(url_layout)
        layout.addWidget(hero)

        self._content_layout = QHBoxLayout()
        self._content_layout.setSpacing(16)
        self._video_info = VideoInfoWidget()
        self._video_info.setMinimumHeight(264)
        self._content_layout.addWidget(self._video_info, 5)

        controls = QWidget()
        controls.setObjectName("ControlPanel")
        controls.setMinimumHeight(340)
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setHorizontalSpacing(10)
        controls_layout.setVerticalSpacing(8)

        settings_label = QLabel("输出规格")
        settings_label.setObjectName("SectionTitle")
        controls_layout.addWidget(settings_label, 0, 0, 1, 2)
        settings_hint = QLabel("按收藏场景选择最合适的组合")
        settings_hint.setObjectName("MetaLabel")
        settings_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls_layout.addWidget(settings_hint, 0, 1)

        page_label = QLabel("分 P 范围")
        page_label.setObjectName("FieldLabel")
        controls_layout.addWidget(page_label, 1, 0)
        self._page_combo = QComboBox()
        self._page_combo.addItem("当前视频", "current")
        controls_layout.addWidget(self._page_combo, 1, 1)

        vq_label = QLabel("画面质量")
        vq_label.setObjectName("FieldLabel")
        controls_layout.addWidget(vq_label, 2, 0)
        self._quality_combo = QComboBox()
        self._populate_quality_combo()
        self._quality_combo.currentIndexChanged.connect(self._refresh_codec_options)
        controls_layout.addWidget(self._quality_combo, 2, 1)

        self._codec_label = QLabel("视频编码")
        self._codec_label.setObjectName("FieldLabel")
        controls_layout.addWidget(self._codec_label, 3, 0)
        self._codec_stack = QStackedWidget()
        self._codec_combo = QComboBox()
        self._populate_codec_combo()
        self._codec_combo.setToolTip("H.265 体积与画质均衡；H.264 兼容性更好；AV1 体积更小")
        self._audio_combo = QComboBox()
        self._populate_audio_combo()
        self._codec_stack.addWidget(self._codec_combo)
        self._codec_stack.addWidget(self._audio_combo)
        controls_layout.addWidget(self._codec_stack, 3, 1)

        output_label = QLabel("输出类型")
        output_label.setObjectName("FieldLabel")
        controls_layout.addWidget(output_label, 4, 0)
        self._output_mode_combo = QComboBox()
        self._output_mode_combo.addItem("视频 / MP4", OutputMode.VIDEO)
        self._output_mode_combo.addItem("仅音频 / M4A 或 FLAC", OutputMode.AUDIO)
        output_index = self._output_mode_combo.findData(
            self._settings.default_output_mode
        )
        self._output_mode_combo.setCurrentIndex(output_index if output_index >= 0 else 0)
        self._output_mode_combo.currentIndexChanged.connect(
            self._sync_output_mode_controls
        )
        controls_layout.addWidget(self._output_mode_combo, 4, 1)

        self._danmaku_check = self._create_checkbox("下载弹幕", self._settings.download_danmaku)
        self._subtitle_check = self._create_checkbox("下载字幕", self._settings.download_subtitle)
        self._subtitle_check.setEnabled(False)
        self._all_subtitles_check = self._create_checkbox(
            "全部字幕", self._settings.download_all_subtitles
        )
        self._all_subtitles_check.setEnabled(False)
        self._cover_check = self._create_checkbox(
            "保存封面", self._settings.download_cover
        )
        self._metadata_check = self._create_checkbox(
            "保存元数据", self._settings.download_metadata
        )
        self._subtitle_check.toggled.connect(
            lambda checked: self._all_subtitles_check.setEnabled(
                checked and self._subtitle_check.isEnabled()
            )
        )
        controls_layout.addWidget(self._danmaku_check, 5, 0)
        controls_layout.addWidget(self._subtitle_check, 5, 1)
        archive_options = QHBoxLayout()
        archive_options.setSpacing(10)
        archive_options.addWidget(self._all_subtitles_check)
        archive_options.addWidget(self._cover_check)
        archive_options.addWidget(self._metadata_check)
        controls_layout.addLayout(archive_options, 6, 0, 1, 2)
        self._sync_output_mode_controls()

        self._download_btn = QPushButton("加入下载队列")
        self._download_btn.setObjectName("DownloadButton")
        self._download_btn.clicked.connect(self._on_download_clicked)

        self._batch_btn = QPushButton("批量导入链接")
        self._batch_btn.setObjectName("SecondaryButton")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        action_layout.addWidget(self._download_btn, 3)
        action_layout.addWidget(self._batch_btn, 2)
        controls_layout.addLayout(action_layout, 7, 0, 1, 2)
        controls_layout.setRowStretch(8, 1)
        self._content_layout.addWidget(controls, 3)
        layout.addLayout(self._content_layout)

        queue_header = QHBoxLayout()
        queue_title = QLabel("任务轨道")
        queue_title.setObjectName("SectionTitle")
        queue_header.addWidget(queue_title)
        queue_hint = QLabel("实时进度与失败重试")
        queue_hint.setObjectName("MetaLabel")
        queue_header.addWidget(queue_hint)
        queue_header.addStretch()
        pause_all = QPushButton("全部暂停")
        pause_all.setObjectName("SubtleButton")
        pause_all.clicked.connect(self._on_pause_all)
        queue_header.addWidget(pause_all)
        resume_all = QPushButton("全部继续")
        resume_all.setObjectName("SubtleButton")
        resume_all.clicked.connect(self._on_resume_all)
        queue_header.addWidget(resume_all)
        clear_done = QPushButton("清除完成")
        clear_done.setObjectName("SubtleButton")
        clear_done.clicked.connect(self._on_clear_completed)
        queue_header.addWidget(clear_done)
        clear_cache = QPushButton("清理缓存")
        clear_cache.setObjectName("SubtleButton")
        clear_cache.clicked.connect(self._on_clear_cache)
        queue_header.addWidget(clear_cache)
        layout.addLayout(queue_header)

        self._download_list = DownloadListWidget()
        self._download_list.retry_requested.connect(self._on_retry_download)
        self._download_list.pause_requested.connect(self._on_pause_requested)
        self._download_list.delete_requested.connect(self._on_delete_download)
        self._download_list.open_requested.connect(self._on_open_download)
        layout.addWidget(self._download_list)
        workspace_scroll = QScrollArea()
        workspace_scroll.setObjectName("WorkspaceScroll")
        workspace_scroll.setWidgetResizable(True)
        workspace_scroll.setFrameShape(QFrame.NoFrame)
        workspace_scroll.setAttribute(Qt.WA_MacShowFocusRect, False)
        workspace_scroll.setWidget(workspace)
        shell.addWidget(workspace_scroll, 1)

    def _create_checkbox(self, text: str, checked: bool):
        cb = QCheckBox(text)
        cb.setAttribute(Qt.WA_MacShowFocusRect, False)
        cb.setChecked(checked)
        return cb

    def _sync_output_mode_controls(self):
        video_mode = self._output_mode_combo.currentData() == OutputMode.VIDEO
        self._quality_combo.setEnabled(video_mode)
        self._codec_label.setText("视频编码" if video_mode else "音频质量")
        self._codec_stack.setCurrentWidget(
            self._codec_combo if video_mode else self._audio_combo
        )

    def _populate_quality_combo(self):
        """Fill quality combo box with all available qualities."""
        qualities = [
            (VideoQuality.Q8K, "8K"),
            (VideoQuality.Q4K, "4K"),
            (VideoQuality.QHDR, "HDR"),
            (VideoQuality.Q_DOLBY, "杜比视界"),
            (VideoQuality.Q1080P60, "1080P60"),
            (VideoQuality.Q1080P_PLUS, "1080P+ 高码率"),
            (VideoQuality.Q1080P, "1080P"),
            (VideoQuality.Q720P, "720P"),
            (VideoQuality.Q480P, "480P"),
            (VideoQuality.Q360P, "360P"),
            (VideoQuality.Q240P, "240P"),
        ]
        # Select default based on settings
        default_idx = 6  # 1080P
        for i, (quality, label) in enumerate(qualities):
            self._quality_combo.addItem(label, quality)
            if quality == self._settings.default_quality:
                default_idx = i
        self._quality_combo.setCurrentIndex(default_idx)

    def _populate_codec_combo(self, available: set[int] | None = None):
        """Populate codecs while preserving the configured or current choice."""
        labels = {
            12: "H.265 / HEVC",
            7: "H.264 / AVC",
            13: "AV1",
        }
        previous = self._codec_combo.currentData() if self._codec_combo.count() else None
        preferred = previous or self._settings.default_video_codec
        self._codec_combo.blockSignals(True)
        self._codec_combo.clear()
        for codec in (12, 7, 13):
            if available is None or codec in available:
                self._codec_combo.addItem(labels[codec], codec)
        index = self._codec_combo.findData(preferred)
        self._codec_combo.setCurrentIndex(index if index >= 0 else 0)
        self._codec_combo.blockSignals(False)

    def _populate_audio_combo(self, available: set[int] | None = None):
        previous = self._audio_combo.currentData() if self._audio_combo.count() else None
        preferred = (
            previous
            if previous is not None
            else self._settings.default_audio_quality
        )
        self._audio_combo.blockSignals(True)
        self._audio_combo.clear()
        for audio_id in (30251, 30250, 30285, 30280, 30216, 0):
            if available is None or audio_id in available:
                self._audio_combo.addItem(
                    AUDIO_CODEC_MAP.get(audio_id, f"音频 {audio_id}"), audio_id
                )
        index = self._audio_combo.findData(preferred)
        self._audio_combo.setCurrentIndex(index if index >= 0 else 0)
        self._audio_combo.blockSignals(False)

    def _refresh_codec_options(self):
        if not hasattr(self, "_codec_combo"):
            return
        if self._current_video is None or not self._current_video.video_streams:
            self._populate_codec_combo()
            return
        quality = self._quality_combo.currentData()
        available = {
            stream.codecid
            for stream in self._current_video.video_streams
            if quality is not None and stream.id == quality.value
        }
        self._populate_codec_combo(available or None)

    def _populate_page_combo(self, info: VideoInfo):
        self._page_combo.clear()
        if info.is_multi_part:
            self._page_combo.addItem(f"全部 {len(info.pages)} P", "all")
            for page in info.pages:
                label = f"P{page.page} · {page.part or '未命名'}"
                self._page_combo.addItem(label, page)
        else:
            self._page_combo.addItem("单 P 视频", "current")

    def resizeEvent(self, event):
        """Stack the dense content panels on narrower screens."""
        if hasattr(self, "_content_layout"):
            direction = (
                QBoxLayout.Direction.TopToBottom
                if event.size().width() < 1120
                else QBoxLayout.Direction.LeftToRight
            )
            self._content_layout.setDirection(direction)
        super().resizeEvent(event)

    def _setup_menu(self):
        """Create menu bar."""
        menubar = self.menuBar()
        menubar.hide()

        # File menu
        file_menu = menubar.addMenu("文件(&F)")

        settings_action = QAction("设置(&S)", self)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.triggered.connect(self._on_settings_triggered)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools menu
        tools_menu = menubar.addMenu("工具(&T)")

        login_action = QAction("登录(&L)", self)
        login_action.triggered.connect(self._on_login_triggered)
        tools_menu.addAction(login_action)

        ffmpeg_action = QAction("检查 FFmpeg(&F)", self)
        ffmpeg_action.triggered.connect(self._on_check_ffmpeg)
        tools_menu.addAction(ffmpeg_action)

        # Help menu
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._on_about_triggered)
        help_menu.addAction(about_action)

    def _setup_status_bar(self):
        """Create status bar."""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")

        self._login_status_label = QLabel("未登录")
        self._login_status_label.setObjectName("MutedLabel")
        self._status_bar.addPermanentWidget(self._login_status_label)

    def _set_login_status_label(self, text: str, style_name: str, tooltip: str = ""):
        """Update login status label and refresh QSS-dependent styling."""
        self._login_status_label.setText(text)
        self._login_status_label.setObjectName(style_name)
        self._login_status_label.setToolTip(tooltip)
        self._login_status_label.style().unpolish(self._login_status_label)
        self._login_status_label.style().polish(self._login_status_label)
        if hasattr(self, "_header_login"):
            self._header_login.setText(text)

    # -- Event Handlers --

    def _restore_tasks(self):
        recovered = self._task_repository.recover_interrupted()
        queued = []
        for record in self._task_repository.list_tasks():
            item = record.item.model_copy(update={"status": record.status}, deep=True)
            self._download_list.add_item(
                item,
                download_id=record.id,
                status=record.status,
                progress=record.progress,
                status_text=record.status_text,
                output_path=record.output_path,
                warnings=record.warnings,
            )
            if record.status == TaskStatus.QUEUED:
                queued.append((item, record.id))
        for item, task_id in queued:
            self._start_download(item, task_id)
        recovered_database = getattr(
            self._task_repository, "recovered_database_path", None
        )
        if recovered_database:
            self._status_bar.showMessage(
                "任务数据库损坏，原文件已隔离并建立新任务库："
                f"{recovered_database.name}"
            )
        elif recovered:
            self._status_bar.showMessage(f"已恢复 {recovered} 个中断任务，可继续下载")

    def _on_resolve_clicked(self):
        """Resolve URL and show video info."""
        url = self._url_input.text().strip()
        if not url:
            self._show_error("请输入B站视频链接或BV号")
            return

        if not is_bilibili_url(url):
            self._show_error("无效的B站视频链接格式")
            return

        self._resolve_btn.setEnabled(False)
        self._resolve_btn.setText("解析中...")
        self._status_bar.showMessage("正在解析视频...")

        # Use QThreadPool for async resolve
        self._resolve_worker = ResolveWorker(self._api_client, url)
        self._resolve_runner = ResolveRunner(self._resolve_worker)
        self._resolve_worker.finished.connect(self._on_resolve_success)
        self._resolve_worker.error.connect(self._on_resolve_error)
        self._service_pool.start(self._resolve_runner)

    def _on_resolve_success(self, info, video_streams, audio_streams, playurl_ok):
        """Handle successful URL resolution."""
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("开始解析  →")
        self._status_bar.showMessage(f"已解析：{info.title}")

        self._current_video = info
        self._current_video.video_streams = video_streams
        self._current_video.audio_streams = audio_streams
        self._video_info.set_video_info(info)
        self._populate_page_combo(info)

        QUALITY_ID_TO_ENUM = {q.value: q for q in VideoQuality}

        if playurl_ok and video_streams:
            # Extract available quality IDs from video streams
            available_qids = set()
            for stream in video_streams:
                available_qids.add(stream.id)

            # Filter to only available qualities, ordered by priority
            QUALITY_PRIORITY = [127, 126, 125, 120, 116, 112, 80, 64, 32, 16, 6]
            available = [qid for qid in QUALITY_PRIORITY if qid in available_qids]

            # Populate quality combo with available options
            self._quality_combo.clear()
            for qid in available:
                enum_val = QUALITY_ID_TO_ENUM.get(qid)
                label = enum_val.label if enum_val else str(qid)
                self._quality_combo.addItem(label, enum_val)
            if available:
                default_index = self._quality_combo.findData(self._settings.default_quality)
                self._quality_combo.setCurrentIndex(default_index if default_index >= 0 else 0)
            else:
                self._populate_quality_combo()
        else:
            # playurl failed or no streams — fallback to full list
            self._quality_combo.clear()
            self._populate_quality_combo()

        self._refresh_codec_options()
        available_audio = {stream.id for stream in audio_streams}
        self._populate_audio_combo(available_audio or None)
        self._subtitle_check.setEnabled(True)
        self._subtitle_check.setChecked(self._settings.download_subtitle)
        self._subtitle_check.setToolTip("每个分 P 下载时会单独查询可用字幕轨道")
        self._all_subtitles_check.setEnabled(self._subtitle_check.isChecked())

    def _on_resolve_error(self, error: str):
        """Handle resolution error."""
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("开始解析  →")
        self._status_bar.showMessage("解析失败")
        self._show_error(f"解析视频失败：{error}")

    def _on_retry_download(self, download_id: int):
        """Retry a failed download."""
        item = self._download_list.get_item(download_id)
        if item:
            self._download_list.mark_failed_retry_reset(download_id)
            self._task_repository.update(
                download_id,
                status=TaskStatus.QUEUED,
                progress=0.0,
                status_text="等待继续",
                error=None,
                speed_bytes_per_second=0,
                eta_seconds=None,
            )
            self._start_download(item, download_id)
            self._status_bar.showMessage(f"重试下载：{item.video_info.title}")

    def _on_download_clicked(self):
        """Start downloading the resolved video."""
        if self._current_video is None:
            self._show_error("请先解析一个视频链接")
            return

        quality = self._quality_combo.currentData()
        if quality is None:
            self._show_error("当前视频没有可用画质，请重新解析或登录后重试")
            return

        page_selection = self._page_combo.currentData()
        if page_selection == "all":
            video_infos = [self._current_video.for_page(page) for page in self._current_video.pages]
        elif hasattr(page_selection, "cid"):
            video_infos = [self._current_video.for_page(page_selection)]
        else:
            video_infos = [self._current_video]

        added = sum(
            self._enqueue_download(self._make_download_item(video_info))
            for video_info in video_infos
        )
        self._status_bar.showMessage(f"已加入 {added} 个下载任务")

    def _make_download_item(self, video_info: VideoInfo) -> DownloadItem:
        all_subtitles = (
            self._subtitle_check.isChecked()
            and self._all_subtitles_check.isChecked()
        )
        return DownloadItem(
            video_info=video_info,
            selected_quality=(
                self._quality_combo.currentData() or self._settings.default_quality
            ),
            selected_video_codec=(
                self._codec_combo.currentData()
                or self._settings.default_video_codec
            ),
            selected_audio_quality=(
                self._audio_combo.currentData()
                if self._audio_combo.currentData() is not None
                else self._settings.default_audio_quality
            ),
            output_mode=self._output_mode_combo.currentData(),
            path_template=self._settings.path_template,
            download_danmaku=self._danmaku_check.isChecked(),
            download_subtitle=self._subtitle_check.isChecked(),
            download_all_subtitles=all_subtitles,
            download_cover=self._cover_check.isChecked(),
            download_metadata=self._metadata_check.isChecked(),
        )

    def _enqueue_download(self, item: DownloadItem) -> bool:
        duplicate = self._task_repository.find_duplicate(item)
        if duplicate is not None:
            self._status_bar.showMessage(
                f"已跳过重复任务：{item.video_info.title}"
            )
            return False
        download_id = self._task_repository.add(item)
        self._download_list.add_item(item, download_id=download_id)
        self._start_download(item, download_id)
        return True

    def _start_download(self, item, download_id: int):
        """Start a download in a background thread via thread pool."""
        worker = DownloadWorker(
            api_client=self._api_client,
            item=item,
            output_dir=self._settings.output_dir,
            download_id=download_id,
            ffmpeg_path=self._settings.ffmpeg_path or None,
        )
        runner = DownloadRunner(worker)

        # Connect signals
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(self._on_download_finished)
        worker.error.connect(self._on_download_error)
        worker.cancelled.connect(self._on_download_cancelled)
        worker.paused.connect(self._on_download_paused)
        worker.metrics.connect(self._on_download_metrics)

        self._download_list.register_worker(download_id, worker)
        self._download_list.mark_downloading(download_id)
        self._task_repository.update(
            download_id,
            status=TaskStatus.DOWNLOADING,
            status_text="正在启动下载",
            error=None,
        )
        self._download_pool.start(runner)

    def _on_download_finished(self, download_id: int, outcome):
        """Handle download completion."""
        self._download_list.mark_done(download_id, outcome)
        self._task_repository.update(
            download_id,
            status=TaskStatus.COMPLETED,
            progress=1.0,
            status_text="部分完成" if outcome.warnings else "完成",
            error=None,
            output_path=outcome.video_path,
            speed_bytes_per_second=0,
            eta_seconds=None,
            completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            warnings=outcome.warnings,
        )
        if outcome.warnings:
            self._status_bar.showMessage(
                f"视频已保存，但有 {len(outcome.warnings)} 项警告"
            )
        else:
            self._status_bar.showMessage(f"下载完成：{outcome.video_path}")

    def _on_download_error(self, download_id: int, error: str):
        """Handle download error."""
        self._download_list.mark_failed(download_id, error)
        self._task_repository.update(
            download_id,
            status=TaskStatus.FAILED,
            status_text=f"失败：{error[:120]}",
            error=error,
            speed_bytes_per_second=0,
            eta_seconds=None,
        )
        self._status_bar.showMessage(f"下载失败：{error}")

    def _on_download_cancelled(self, download_id: int):
        """Handle a task cancelled by the user."""
        self._download_list.mark_cancelled(download_id)
        self._task_repository.update(
            download_id,
            status=TaskStatus.CANCELLED,
            status_text="已取消",
            speed_bytes_per_second=0,
            eta_seconds=None,
        )
        self._status_bar.showMessage("下载已取消")

    def _on_download_progress(self, download_id: int, progress: float, text: str):
        self._download_list.update_progress(download_id, progress, text)
        state = (
            TaskStatus.MERGING
            if "合并" in text or "封装" in text
            else TaskStatus.DOWNLOADING
        )
        self._task_repository.update(
            download_id,
            status=state,
            progress=max(0.0, min(1.0, progress)),
            status_text=text,
        )

    def _on_download_metrics(self, download_id: int, speed: float, eta):
        self._task_repository.update(
            download_id,
            speed_bytes_per_second=max(0.0, speed),
            eta_seconds=eta,
        )

    def _on_pause_requested(self, download_id: int):
        self._task_repository.update(
            download_id,
            status=TaskStatus.PAUSED,
            status_text="暂停中",
            speed_bytes_per_second=0,
            eta_seconds=None,
        )

    def _on_download_paused(self, download_id: int):
        self._download_list.mark_paused(download_id)
        self._task_repository.update(
            download_id,
            status=TaskStatus.PAUSED,
            status_text="已暂停，可继续",
            speed_bytes_per_second=0,
            eta_seconds=None,
        )
        self._status_bar.showMessage("任务已暂停，断点数据已保留")

    def _on_delete_download(self, download_id: int):
        self._task_repository.delete(download_id)

    def _on_open_download(self, download_id: int):
        record = self._task_repository.get(download_id)
        if record is None or not record.output_path:
            self._show_error("找不到该任务的输出文件")
            return
        path = Path(record.output_path)
        if not path.exists():
            self._show_error(f"文件已经移动或删除：\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _on_pause_all(self):
        self._download_list.pause_all_workers()
        self._status_bar.showMessage("正在暂停全部任务...")

    def _on_resume_all(self):
        task_ids = self._download_list.resumable_ids
        for task_id in task_ids:
            self._on_retry_download(task_id)
        self._status_bar.showMessage(f"已继续 {len(task_ids)} 个任务")

    def _on_clear_completed(self):
        task_ids = self._download_list.completed_ids
        for task_id in task_ids:
            self._download_list.remove_item(task_id)
        deleted = self._task_repository.clear_completed()
        self._status_bar.showMessage(f"已清除 {deleted} 条完成记录，媒体文件仍保留")

    def _on_clear_cache(self):
        if self._download_list.has_active_workers:
            self._show_error("请先暂停全部任务，再清理断点缓存")
            return
        summary = inspect_download_cache(self._settings.output_dir)
        if summary.file_count == 0:
            self._show_info("当前没有断点缓存")
            return
        size = _format_bytes(summary.size_bytes)
        answer = QMessageBox.question(
            self,
            "清理断点缓存",
            f"将删除 {summary.file_count} 个断点文件（{size}）。\n"
            "删除后未完成任务需要重新下载，确认继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        cleared = clear_download_cache(self._settings.output_dir)
        self._status_bar.showMessage(f"已清理 {cleared.file_count} 个断点文件")

    def _on_settings_triggered(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            new_settings = dialog.get_settings()
            try:
                self._config.save(new_settings)
            except OSError as e:
                self._show_error(f"设置保存失败：{e}")
                return
            self._settings = new_settings
            self._apply_thread_pool_settings()
            self._apply_settings_to_controls()

    def _apply_settings_to_controls(self):
        quality_index = self._quality_combo.findData(self._settings.default_quality)
        if quality_index >= 0:
            self._quality_combo.setCurrentIndex(quality_index)
        codec_index = self._codec_combo.findData(self._settings.default_video_codec)
        if codec_index >= 0:
            self._codec_combo.setCurrentIndex(codec_index)
        audio_index = self._audio_combo.findData(self._settings.default_audio_quality)
        if audio_index >= 0:
            self._audio_combo.setCurrentIndex(audio_index)
        output_index = self._output_mode_combo.findData(
            self._settings.default_output_mode
        )
        if output_index >= 0:
            self._output_mode_combo.setCurrentIndex(output_index)
        self._danmaku_check.setChecked(self._settings.download_danmaku)
        self._subtitle_check.setChecked(self._settings.download_subtitle)
        self._all_subtitles_check.setChecked(
            self._settings.download_all_subtitles
        )
        self._cover_check.setChecked(self._settings.download_cover)
        self._metadata_check.setChecked(self._settings.download_metadata)
        self._sync_output_mode_controls()

    def _on_login_triggered(self):
        """Open login dialog."""
        dialog = LoginDialog(self._settings.sessdata, self)
        if dialog.exec():
            if dialog.logout_requested:
                new_settings = self._settings.model_copy(
                    update={"sessdata": "", "last_login_at": None},
                    deep=True,
                )
                try:
                    self._config.save(new_settings)
                except OSError as e:
                    self._show_error(f"退出登录失败：{e}")
                    return
                self._settings = new_settings
                self._replace_api_client()
                self._login_status_request_id += 1
                self._set_login_status_label("未登录", "MutedLabel")
                self._status_bar.showMessage("已退出登录并清除本机凭据")
                return

            sessdata = dialog.get_sessdata()
            if not sessdata:
                self._show_error("登录未返回有效凭据，请重新验证")
                return
            new_settings = self._settings.model_copy(
                update={"sessdata": sessdata}, deep=True
            )
            try:
                self._config.save(new_settings)
            except OSError as e:
                self._show_error(f"登录信息保存失败：{e}")
                return
            self._settings = new_settings
            self._replace_api_client()
            # Fetch and display user info
            self._update_login_status()

    def _update_login_status(self):
        """Fetch user info without blocking the GUI event loop."""
        self._login_status_request_id += 1
        request_id = self._login_status_request_id
        self._set_login_status_label("正在检查账号...", "MutedLabel")
        self._login_status_worker = LoginStatusWorker(self._api_client, request_id)
        self._login_status_worker.finished.connect(self._on_login_status_result)
        self._login_status_worker.error.connect(self._on_login_status_error)
        self._login_status_runner = LoginStatusRunner(self._login_status_worker)
        self._service_pool.start(self._login_status_runner)

    def _on_login_status_result(self, request_id: int, nav_info: dict):
        if request_id != self._login_status_request_id:
            return
        if nav_info.get("isLogin"):
            uname = nav_info.get("uname", "未知用户")
            mid = nav_info.get("mid", "")
            self._user_face = nav_info.get("face", "")
            self._set_login_status_label(
                f"已登录：{uname}",
                "StatusPill",
                f"UID: {mid}",
            )
        else:
            self._set_login_status_label("未登录", "MutedLabel")

    def _on_login_status_error(self, request_id: int, error: str):
        if request_id != self._login_status_request_id:
            return
        logger.warning("Login status check failed: %s", error)
        self._set_login_status_label("登录状态未知", "MutedLabel")

    def _on_batch_clicked(self):
        """Open batch download dialog."""
        dialog = BatchDialog(
            api_client=self._api_client,
            existing_bvids=self._task_repository.known_bvids(),
            parent=self,
        )
        if dialog.exec():
            infos = dialog.get_video_infos()
            if infos:
                self._enqueue_batch_infos(infos)

    def _enqueue_batch_infos(self, infos: list[VideoInfo]):
        added = 0
        skipped = 0
        for info in infos:
            page_infos = (
                [info.for_page(page) for page in info.pages]
                if info.is_multi_part
                else [info]
            )
            for page_info in page_infos:
                item = self._make_download_item(page_info)
                if self._enqueue_download(item):
                    added += 1
                else:
                    skipped += 1
        self._status_bar.showMessage(
            f"已加入 {added} 个任务" + (f"，跳过 {skipped} 个重复项" if skipped else "")
        )

    def _on_check_ffmpeg(self):
        """Check FFmpeg availability."""
        self._status_bar.showMessage("正在检查 FFmpeg...")
        self._ffmpeg_check_worker = FFmpegCheckWorker()
        self._ffmpeg_check_worker.finished.connect(self._on_ffmpeg_checked)
        self._ffmpeg_check_runner = FFmpegCheckRunner(
            self._ffmpeg_check_worker,
            self._settings.ffmpeg_path or None,
        )
        self._service_pool.start(self._ffmpeg_check_runner)

    def _on_ffmpeg_checked(self, available: bool, msg: str):
        self._status_bar.showMessage("FFmpeg 检查完成")
        if available:
            self._show_info(f"FFmpeg 可用：\n{msg}")
        else:
            self._show_error(f"FFmpeg 不可用：\n{msg}")

    def _on_about_triggered(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "关于",
            f"哔哩哔哩视频下载器 v{__version__}\n\n"
            "一款桌面端B站视频下载工具。\n"
            "支持4K、HDR、杜比视界、弹幕和字幕下载。",
        )

    def _show_error(self, message: str):
        QMessageBox.critical(self, "任务出现问题", message)

    def _show_info(self, message: str):
        QMessageBox.information(self, "运行信息", message)

    def closeEvent(self, event: QCloseEvent):
        """Cancel running downloads and close API client on window close."""
        if self._download_list.has_active_workers and not self._close_confirmed:
            answer = QMessageBox.question(
                self,
                "退出 BiliFlow",
                "仍有下载任务正在运行。退出将保留断点数据，确认停止并退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._close_confirmed = True

        # Pause active workers so their durable tasks remain resumable.
        self._download_list.pause_all_workers()
        # Give both pools a short grace period before closing their shared clients.
        downloads_stopped = self._download_pool.waitForDone(2000)
        services_stopped = self._service_pool.waitForDone(1000)
        workers_stopped = downloads_stopped and services_stopped
        if not workers_stopped:
            logger.warning("Background tasks did not stop before window shutdown")

        if workers_stopped:
            for client in [self._api_client, *self._retired_api_clients]:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to close API client", exc_info=True)

        super().closeEvent(event)


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
