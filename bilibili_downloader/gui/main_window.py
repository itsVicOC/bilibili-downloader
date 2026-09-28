"""Main application window for the Bilibili Downloader."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
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
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader import __version__
from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.cache import clear_download_cache, inspect_download_cache
from bilibili_downloader.core.copyright import (
    BILIBILI_TERMS_URL,
    COPYRIGHT_DOCUMENT_URL,
    COPYRIGHT_NOTICE_SUMMARY,
    COPYRIGHT_NOTICE_TITLE,
    COPYRIGHT_NOTICE_VERSION,
)
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
from bilibili_downloader.gui.live_controller import LiveUiController
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
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    FieldRow,
    IconButton,
    MessageBox,
    Notice,
    PageHeader,
    SectionCard,
    repolish,
    scroll_area,
)
from bilibili_downloader.gui.widgets.download_list import DownloadListWidget
from bilibili_downloader.gui.widgets.hero_panel import HeroPanel
from bilibili_downloader.gui.widgets.live_page import LivePage
from bilibili_downloader.gui.widgets.task_page import TaskPage
from bilibili_downloader.gui.widgets.video_info import VideoInfoWidget
from bilibili_downloader.utils.config import ConfigManager
from bilibili_downloader.utils.validators import is_bilibili_url

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config_manager=None, task_repository=None, live_controller=None):
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
        self._provided_live_controller = live_controller
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()
        self._restore_tasks()

        # Check login status on startup
        self._user_face = ""
        if getattr(self._config, "auth_cookies", None) or self._settings.sessdata:
            if not getattr(self._config, "credentials_persistent", True):
                self._status_bar.showMessage(
                    "系统凭据库不可用：登录仅在本次运行有效，重启后需重新登录"
                )
            self._update_login_status()

    def _create_api_client(self):
        """Create API client with current settings."""
        auth_cookies = getattr(self._config, "auth_cookies", {})
        return BilibiliAPIClient(
            sessdata=self._settings.sessdata or None,
            auth_cookies=auth_cookies,
        )

    def _apply_thread_pool_settings(self):
        """Apply user-configured concurrency limits."""
        max_downloads = max(1, min(8, self._settings.max_concurrent_downloads))
        self._download_pool.setMaxThreadCount(max_downloads)

    def _replace_api_client(self):
        """Swap credentials without invalidating in-flight worker requests."""
        previous = self._api_client
        self._api_client = self._create_api_client()
        self._retired_api_clients.append(previous)
        self._batch_page._api_client = self._api_client
        if self._live_page.service:
            self._live_page.service.command("auth", cookies=self._config.auth_cookies)

    def _setup_ui(self):
        """Persistent workspaces sharing navigation, theme and service ownership."""
        central = QWidget()
        central.setObjectName("AppSurface")
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self._sidebar = QFrame()
        self._sidebar.setObjectName("Sidebar")
        self._sidebar.setFixedWidth(208)
        self._side_layout = QVBoxLayout(self._sidebar)
        self._side_layout.setContentsMargins(16, 24, 16, 16)
        self._side_layout.setSpacing(12)
        brand = QHBoxLayout()
        brand.setSpacing(12)
        brand_icon = QLabel()
        brand_icon.setPixmap(QIcon(asset_path("app_icon.png")).pixmap(40, 40))
        brand_icon.setFixedSize(40, 40)
        brand.addWidget(brand_icon)
        self._brand_copy = QWidget()
        copy = QVBoxLayout(self._brand_copy)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        title = QLabel("BiliFlow")
        title.setObjectName("BrandTitle")
        caption = QLabel("星轨收藏站")
        caption.setObjectName("SidebarCaption")
        copy.addWidget(title)
        copy.addWidget(caption)
        brand.addWidget(self._brand_copy, 1)
        self._side_layout.addLayout(brand)
        self._side_layout.addSpacing(16)
        self._nav_caption = QLabel("工作区")
        self._nav_caption.setObjectName("NavSection")
        self._side_layout.addWidget(self._nav_caption)
        self._nav_buttons = []
        for index, (text, icon) in enumerate(
            (("视频下载", "download"), ("直播录制", "live"), ("任务中心", "tasks"))
        ):
            button = IconButton(text, icon, "NavButton")
            button.clicked.connect(
                lambda _checked=False, page=index: self._show_workspace(page)
            )
            self._nav_buttons.append(button)
            self._side_layout.addWidget(button)
        self._home_nav, self._live_nav, self._tasks_nav = self._nav_buttons
        self._side_layout.addStretch()
        self._mascot_card = SectionCard()
        mascot = QLabel()
        mascot.setPixmap(QIcon(asset_path("alien.png")).pixmap(28, 28))
        self._mascot_card.body.addWidget(mascot)
        welcome = QLabel("次元收藏，随时继续")
        welcome.setObjectName("SidebarCaption")
        welcome.setWordWrap(True)
        self._mascot_card.body.addWidget(welcome)
        self._side_layout.addWidget(self._mascot_card)
        self._settings_nav = IconButton("设置", "settings", "NavButton")
        self._settings_nav.clicked.connect(self._on_settings_triggered)
        self._side_layout.addWidget(self._settings_nav)
        self._account_text = "未登录"
        self._header_login = IconButton("未登录", "account", "SidebarAction")
        self._header_login.clicked.connect(self._on_login_triggered)
        self._side_layout.addWidget(self._header_login)
        shell.addWidget(self._sidebar)
        self._workspace_pages = QStackedWidget()
        shell.addWidget(self._workspace_pages, 1)
        self._build_download_page()
        self._live_controller = self._provided_live_controller or LiveUiController(
            self._config, self
        )
        self._live_page = LivePage(
            self._config,
            self._confirm_copyright_acknowledgement,
            self,
            self._live_controller,
        )
        self._live_page.settings_requested.connect(self._show_settings_tab)
        self._live_page.history_requested.connect(lambda: self._show_tasks(2))
        self._workspace_pages.addWidget(self._live_page)
        self._download_list = DownloadListWidget()
        self._download_list.retry_requested.connect(self._on_retry_download)
        self._download_list.pause_requested.connect(self._on_pause_requested)
        self._download_list.delete_requested.connect(self._on_delete_download)
        self._download_list.open_requested.connect(self._on_open_download)
        self._task_page = TaskPage(self._download_list, self._live_controller)
        self._task_page.download_requested.connect(lambda: self._show_workspace(0))
        self._task_page.room_requested.connect(self._show_room)
        self._task_page.pause_all_requested.connect(self._on_pause_all)
        self._task_page.resume_all_requested.connect(self._on_resume_all)
        self._task_page.clear_completed_requested.connect(self._on_clear_completed)
        self._task_page.clear_cache_requested.connect(self._on_clear_cache)
        self._workspace_pages.addWidget(self._task_page)
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(24, 24, 24, 24)
        settings_layout.setSpacing(20)
        settings_header = PageHeader("设置", "统一管理下载偏好、直播录制与媒体工具")
        about_button = QPushButton("关于 BiliFlow")
        about_button.setObjectName("TextButton")
        about_button.clicked.connect(self._on_about_triggered)
        settings_header.actions.addWidget(about_button)
        settings_layout.addWidget(settings_header)
        self._settings_page = SettingsDialog(self._settings, embedded=True)
        self._settings_page.save_requested.connect(self._save_settings)
        self._settings_page.cache_requested.connect(self._on_clear_cache)
        settings_layout.addWidget(self._settings_page, 1)
        self._workspace_pages.addWidget(settings_page)
        self._live_controller.snapshot_changed.connect(self._refresh_activity)
        self._activity_timer = QTimer(self)
        self._activity_timer.timeout.connect(self._refresh_activity)
        self._activity_timer.start(1000)
        self._show_workspace(0)
        self._update_responsive_layout(self.width())

    def _build_download_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(PageHeader("视频下载", "把喜欢的作品，带回自己的收藏空间"))
        self._download_tabs = QTabWidget()
        layout.addWidget(self._download_tabs, 1)
        body = QWidget()
        self._workspace_layout = QVBoxLayout(body)
        self._workspace_layout.setContentsMargins(0, 0, 4, 0)
        self._workspace_layout.setSpacing(20)
        self._hero = HeroPanel()
        self._hero.set_compact(True)
        self._hero_layout = QVBoxLayout(self._hero)
        self._hero_layout.setContentsMargins(20, 16, 20, 16)
        self._hero_layout.setSpacing(10)
        self._hero_title = QLabel("喜欢的这一集，现在就带回本地。")
        self._hero_title.setObjectName("HeroTitle")
        self._hero_layout.addWidget(self._hero_title)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._url_input = ChineseLineEdit()
        self._url_input.setPlaceholderText("B 站链接、BV / AV / ep 号或 b23.tv 短链")
        self._url_input.returnPressed.connect(self._on_resolve_clicked)
        self._url_input.textChanged.connect(self._source_changed)
        row.addWidget(self._url_input, 1)
        self._resolve_btn = QPushButton("开始解析")
        self._resolve_btn.setObjectName("PrimaryButton")
        self._resolve_btn.clicked.connect(self._on_resolve_clicked)
        row.addWidget(self._resolve_btn)
        self._hero_layout.addLayout(row)
        self._workspace_layout.addWidget(self._hero)
        self._resolve_notice = Notice()
        self._workspace_layout.addWidget(self._resolve_notice)
        self._content_section = QWidget()
        self._content_layout = QBoxLayout(QBoxLayout.LeftToRight, self._content_section)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(20)
        self._video_info = VideoInfoWidget()
        self._content_layout.addWidget(self._video_info, 5)
        self._build_output_card()
        self._workspace_layout.addWidget(self._content_section)
        self._workspace_layout.addStretch()
        self._workspace_scroll = scroll_area(body)
        self._download_tabs.addTab(self._workspace_scroll, "单个解析")
        self._batch_page = BatchDialog(
            api_client=self._api_client,
            existing_content_identities=self._task_repository.known_content_identities(),
            embedded=True,
        )
        self._batch_page.enqueue_requested.connect(self._enqueue_batch_from_page)
        batch_format = QPushButton("调整输出规格")
        batch_format.setObjectName("TableSubtleButton")
        batch_format.clicked.connect(lambda: self._download_tabs.setCurrentIndex(0))
        self._batch_page._preview_card.header.addWidget(batch_format)
        self._download_tabs.addTab(self._batch_page, "批量导入")
        self._enqueue_notice = Notice(
            action="查看任务", callback=lambda: self._show_tasks(0)
        )
        layout.addWidget(self._enqueue_notice)
        layout.addWidget(self._download_actions)
        self._download_tabs.currentChanged.connect(
            lambda index: self._download_actions.setVisible(index == 0)
        )
        self._workspace_pages.addWidget(page)

    def _build_output_card(self):
        controls = SectionCard("输出规格")
        controls.setObjectName("ControlPanel")
        self._output_card = controls
        self._page_combo = ComboBox()
        self._page_combo.addItem("当前视频", "current")
        controls.body.addWidget(FieldRow("分 P 范围", self._page_combo))
        self._output_mode_combo = ComboBox()
        self._output_mode_combo.addItem("视频 / MP4", OutputMode.VIDEO)
        self._output_mode_combo.addItem("仅音频 / M4A 或 FLAC", OutputMode.AUDIO)
        self._output_mode_combo.setCurrentIndex(
            max(0, self._output_mode_combo.findData(self._settings.default_output_mode))
        )
        self._output_mode_combo.currentIndexChanged.connect(
            self._sync_output_mode_controls
        )
        controls.body.addWidget(FieldRow("输出类型", self._output_mode_combo))
        self._quality_combo = ComboBox()
        self._populate_quality_combo()
        self._quality_combo.currentIndexChanged.connect(self._refresh_codec_options)
        controls.body.addWidget(FieldRow("画面质量", self._quality_combo))
        self._codec_stack = QStackedWidget()
        self._codec_combo = ComboBox()
        self._populate_codec_combo()
        self._audio_combo = ComboBox()
        self._populate_audio_combo()
        self._codec_stack.addWidget(self._codec_combo)
        self._codec_stack.addWidget(self._audio_combo)
        codec_row = FieldRow("视频编码", self._codec_stack)
        self._codec_label = codec_row.label
        controls.body.addWidget(codec_row)
        self._danmaku_check = self._create_checkbox(
            "下载弹幕", self._settings.download_danmaku
        )
        self._subtitle_check = self._create_checkbox(
            "下载字幕", self._settings.download_subtitle
        )
        self._all_subtitles_check = self._create_checkbox(
            "全部字幕", self._settings.download_all_subtitles
        )
        self._cover_check = self._create_checkbox(
            "保存封面", self._settings.download_cover
        )
        self._metadata_check = self._create_checkbox(
            "保存元数据", self._settings.download_metadata
        )
        self._subtitle_check.setEnabled(False)
        self._all_subtitles_check.setEnabled(False)
        self._subtitle_check.toggled.connect(
            lambda checked: self._all_subtitles_check.setEnabled(
                checked and self._subtitle_check.isEnabled()
            )
        )
        archive = QGridLayout()
        archive.setHorizontalSpacing(16)
        archive.setVerticalSpacing(4)
        archive.addWidget(self._danmaku_check, 0, 0)
        archive.addWidget(self._subtitle_check, 0, 1)
        subtitle_options = QWidget()
        subtitle_layout = QHBoxLayout(subtitle_options)
        subtitle_layout.setContentsMargins(24, 0, 0, 0)
        subtitle_layout.addWidget(self._all_subtitles_check)
        archive.addWidget(subtitle_options, 1, 1)
        archive.addWidget(self._cover_check, 2, 0)
        archive.addWidget(self._metadata_check, 2, 1)
        controls.body.addLayout(archive)
        self._output_summary = QLineEdit(self._settings.output_dir)
        self._output_summary.setReadOnly(True)
        self._output_summary.setToolTip(self._settings.output_dir)
        self._output_summary.setCursorPosition(0)
        controls.body.addWidget(FieldRow("保存目录", self._output_summary))
        self._download_actions = QWidget()
        actions = QHBoxLayout(self._download_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)
        self._download_hint = QLabel("选择输出规格后，加入下载队列")
        self._download_hint.setObjectName("MetaLabel")
        actions.addWidget(self._download_hint, 1)
        self._download_btn = QPushButton("加入下载队列")
        self._download_btn.setObjectName("PrimaryButton")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download_clicked)
        actions.addWidget(self._download_btn)
        self._batch_btn = QPushButton("批量导入")
        self._batch_btn.setObjectName("TextButton")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        actions.addWidget(self._batch_btn)
        controls.body.addStretch()
        self._sync_output_mode_controls()
        self._content_layout.addWidget(controls, 4)

    def _show_workspace(self, index):
        if (
            self._workspace_pages.currentIndex() == 3
            and index != 3
            and not self._can_leave_settings()
        ):
            return False
        if index == 3 and not self._settings_page.dirty:
            self._settings_page.load_settings(self._settings)
        self._workspace_pages.setCurrentIndex(index)
        for i, button in enumerate([*self._nav_buttons, self._settings_nav]):
            button.setObjectName("NavButtonActive" if i == index else "NavButton")
            repolish(button)
        return True

    def _show_tasks(self, tab=0):
        if self._show_workspace(2):
            self._task_page.tabs.setCurrentIndex(tab)

    def _show_room(self, room_id):
        if self._show_workspace(1):
            self._live_page.select_room(room_id)

    def _show_settings_tab(self, tab):
        if self._show_workspace(3):
            self._settings_page.tabs.setCurrentIndex(tab)

    def _can_leave_settings(self):
        if not self._settings_page.dirty:
            return True
        box = MessageBox(
            "保存设置修改",
            "设置中有未保存的修改。",
            self,
            buttons=QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            default=QMessageBox.Cancel,
        )
        box.button(QMessageBox.Save).setText("保存修改")
        box.button(QMessageBox.Save).setObjectName("PrimaryButton")
        box.button(QMessageBox.Discard).setText("放弃修改")
        box.button(QMessageBox.Cancel).setText("继续编辑")
        box.setDefaultButton(QMessageBox.Cancel)
        answer = box.exec()
        if answer == QMessageBox.Save:
            return self._save_settings()
        if answer == QMessageBox.Discard:
            self._settings_page.load_settings(self._settings)
            return True
        return False

    def _live_settings_changed(self, settings):
        self._settings = settings

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
        previous = (
            self._codec_combo.currentData() if self._codec_combo.count() else None
        )
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
        previous = (
            self._audio_combo.currentData() if self._audio_combo.count() else None
        )
        preferred = (
            previous if previous is not None else self._settings.default_audio_quality
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

    def _update_responsive_layout(self, width):
        if not hasattr(self, "_sidebar"):
            return
        compact = width < 1120
        self._sidebar.setFixedWidth(72 if compact else 208)
        self._side_layout.setContentsMargins(
            12 if compact else 16, 24, 12 if compact else 16, 16
        )
        for widget in (self._brand_copy, self._nav_caption, self._mascot_card):
            widget.setVisible(not compact)
        for button in [*self._nav_buttons, self._settings_nav, self._header_login]:
            button.set_compact(compact)
        if not compact:
            self._header_login.setText(
                self._header_login.fontMetrics().elidedText(
                    self._account_text, Qt.ElideRight, 116
                )
            )
        content_width = width - (72 if compact else 208) - 48
        self._content_layout.setDirection(
            QBoxLayout.TopToBottom if content_width < 900 else QBoxLayout.LeftToRight
        )

    def resizeEvent(self, event):
        self._update_responsive_layout(event.size().width())
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
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")
        self._login_status_label = QLabel("未登录")
        self._login_status_label.setObjectName("MutedLabel")
        # Account status is presented once, in the sidebar.
        self._download_activity = QPushButton("下载 0")
        self._download_activity.setObjectName("ActivityButton")
        self._download_activity.clicked.connect(lambda: self._show_tasks(0))
        self._record_activity = QPushButton("录制 0")
        self._record_activity.setObjectName("ActivityButton")
        self._record_activity.clicked.connect(lambda: self._show_tasks(1))
        self._status_bar.addPermanentWidget(self._download_activity)
        self._status_bar.addPermanentWidget(self._record_activity)
        self._refresh_activity()

    def _refresh_activity(self, *_args):
        if not hasattr(self, "_status_bar"):
            return
        count = sum(
            state in {TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.MERGING}
            for state in self._download_list._states.values()
        )
        recording = sum(row["active"] for row in self._live_controller.rows)
        self._download_activity.setText(f"下载 {count}")
        self._record_activity.setText(f"录制 {recording}")
        self._tasks_nav.setToolTip(f"任务中心 · {count} 项下载 / {recording} 场录制")
        self._live_nav.setToolTip(f"直播录制 · {recording} 场正在录制")
        self._task_page.refresh_downloads()

    def _set_login_status_label(self, text, style_name, tooltip=""):
        self._login_status_label.setText(text)
        self._login_status_label.setObjectName(style_name)
        self._account_text = text
        self._header_login.full_text = text
        compact = self._sidebar.width() == 72
        self._header_login.set_compact(compact)
        if not compact:
            self._header_login.setText(
                self._header_login.fontMetrics().elidedText(text, Qt.ElideRight, 116)
            )
        self._header_login.setToolTip(
            " · ".join(part for part in (text, tooltip) if part)
        )
        self._header_login.setAccessibleName(text)

    def _source_changed(self, text):
        if hasattr(self, "_download_btn") and text.strip() != getattr(
            self, "_resolved_url", ""
        ):
            self._current_video = None
            self._download_btn.setEnabled(False)
            self._video_info._state_label.setText("等待解析")
            self._video_info._state_label.set_tone("muted")
            if getattr(self, "_resolved_url", ""):
                self._resolve_notice.set_message("来源已修改，请重新解析。")

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
                f"任务数据库损坏，原文件已隔离并建立新任务库：{recovered_database.name}"
            )
        elif recovered:
            self._status_bar.showMessage(f"已恢复 {recovered} 个中断任务，可继续下载")

    def _on_resolve_clicked(self):
        """Resolve URL and show video info."""
        if not self._resolve_btn.isEnabled():
            return
        url = self._url_input.text().strip()
        if not url:
            self._resolve_notice.set_message(
                "请输入 B 站链接或 BV / AV / ep 号。", "warning"
            )
            return

        if not is_bilibili_url(url):
            self._resolve_notice.set_message(
                "无法识别这个来源。番剧季度、合集和收藏夹请使用批量导入。", "warning"
            )
            return

        self._resolve_request_url = url
        self._current_video = None
        self._download_btn.setEnabled(False)
        self._resolve_notice.set_message("正在读取作品与可用规格…")
        self._video_info._state_label.setText("解析中")
        self._video_info._state_label.set_tone("active")
        self._video_info._state_label.setText("解析中")
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
        self._resolve_btn.setText("开始解析")
        if (
            getattr(self, "_resolve_request_url", self._url_input.text().strip())
            != self._url_input.text().strip()
        ):
            self._resolve_notice.set_message(
                "解析期间来源已修改，请重新解析。", "warning"
            )
            return
        self._resolved_url = self._url_input.text().strip()
        self._resolve_notice.set_message("")
        self._download_btn.setEnabled(True)
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
                default_index = self._quality_combo.findData(
                    self._settings.default_quality
                )
                self._quality_combo.setCurrentIndex(
                    default_index if default_index >= 0 else 0
                )
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
        self._resolve_btn.setText("开始解析")
        self._status_bar.showMessage("解析失败")
        self._download_btn.setEnabled(False)
        self._video_info._state_label.setText("解析失败")
        self._video_info._state_label.set_tone("danger")
        self._resolve_notice.set_message(f"解析失败：{error}", "danger")

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
        if not self._confirm_copyright_acknowledgement():
            return

        page_selection = self._page_combo.currentData()
        if page_selection == "all":
            video_infos = [
                self._current_video.for_page(page) for page in self._current_video.pages
            ]
        elif hasattr(page_selection, "cid"):
            video_infos = [self._current_video.for_page(page_selection)]
        else:
            video_infos = [self._current_video]

        added = sum(
            self._enqueue_download(self._make_download_item(video_info))
            for video_info in video_infos
        )
        skipped = len(video_infos) - added
        message = f"已加入 {added} 个下载任务" + (
            f"，跳过 {skipped} 个重复项" if skipped else ""
        )
        self._status_bar.showMessage(message)
        self._enqueue_notice.set_message(message, "success" if added else "info")
        self._refresh_activity()

    def _make_download_item(self, video_info: VideoInfo) -> DownloadItem:
        all_subtitles = (
            self._subtitle_check.isChecked() and self._all_subtitles_check.isChecked()
        )
        return DownloadItem(
            video_info=video_info,
            selected_quality=(
                self._quality_combo.currentData() or self._settings.default_quality
            ),
            selected_video_codec=(
                self._codec_combo.currentData() or self._settings.default_video_codec
            ),
            selected_audio_quality=(
                self._audio_combo.currentData()
                if self._audio_combo.currentData() is not None
                else self._settings.default_audio_quality
            ),
            output_mode=self._output_mode_combo.currentData(),
            path_template=(
                self._settings.bangumi_path_template
                if video_info.episode_id
                else self._settings.path_template
            ),
            download_danmaku=self._danmaku_check.isChecked(),
            download_subtitle=self._subtitle_check.isChecked(),
            download_all_subtitles=all_subtitles,
            download_cover=self._cover_check.isChecked(),
            download_metadata=self._metadata_check.isChecked(),
        )

    def _enqueue_download(self, item: DownloadItem) -> bool:
        duplicate = self._task_repository.find_duplicate(item)
        if duplicate is not None:
            self._status_bar.showMessage(f"已跳过重复任务：{item.video_info.title}")
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
        state = (
            TaskStatus.MERGING
            if "合并" in text or "封装" in text
            else TaskStatus.DOWNLOADING
        )
        self._download_list.update_progress(download_id, progress, text, state)
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
        box = MessageBox(
            "清理断点缓存",
            f"将删除 {summary.file_count} 个断点文件（{size}）。\n"
            "删除后未完成任务需要重新下载，确认继续吗？",
            self,
            tone="warning",
            buttons=QMessageBox.Yes | QMessageBox.No,
            default=QMessageBox.No,
        )
        box.button(QMessageBox.Yes).setText("清理缓存")
        box.button(QMessageBox.Yes).setObjectName("DangerButton")
        if box.exec() != QMessageBox.Yes:
            return
        cleared = clear_download_cache(self._settings.output_dir)
        self._status_bar.showMessage(f"已清理 {cleared.file_count} 个断点文件")

    def _on_settings_triggered(self):
        self._show_workspace(3)

    def _save_settings(self):
        if not self._settings_page.validate():
            return False
        new_settings = self._settings_page.merge_into(self._config.load())
        try:
            self._config.save(new_settings)
        except OSError as exc:
            self._settings_page._notice.set_message(f"设置保存失败：{exc}", "danger")
            return False
        self._settings = new_settings
        self._apply_thread_pool_settings()
        self._apply_settings_to_controls()
        self._live_controller.command("settings", settings=new_settings.live)
        self._live_page.check_engine()
        self._settings_page.load_settings(new_settings)
        self._settings_page._notice.set_message("设置已保存", "success")
        return True

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
        self._all_subtitles_check.setChecked(self._settings.download_all_subtitles)
        self._cover_check.setChecked(self._settings.download_cover)
        self._metadata_check.setChecked(self._settings.download_metadata)
        self._sync_output_mode_controls()
        self._output_summary.setText(self._settings.output_dir)
        self._output_summary.setToolTip(self._settings.output_dir)
        self._output_summary.setCursorPosition(0)

    def _on_login_triggered(self):
        """Open login dialog."""
        current_cookies = getattr(self._config, "auth_cookies", {})
        dialog = LoginDialog(current_cookies or self._settings.sessdata, self)
        if dialog.exec():
            if dialog.logout_requested:
                new_settings = self._settings.model_copy(
                    update={"sessdata": "", "last_login_at": None},
                    deep=True,
                )
                try:
                    if hasattr(self._config, "clear_auth_cookies"):
                        self._config.clear_auth_cookies()
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

            cookies = dialog.get_auth_cookies()
            if not cookies.get("SESSDATA"):
                self._show_error("登录未返回有效凭据，请重新验证")
                return
            new_settings = self._settings.model_copy(
                update={"sessdata": cookies["SESSDATA"]}, deep=True
            )
            try:
                persistent = True
                if hasattr(self._config, "save_auth_cookies"):
                    persistent = self._config.save_auth_cookies(cookies)
                self._config.save(new_settings)
            except OSError as e:
                self._show_error(f"登录信息保存失败：{e}")
                return
            self._settings = new_settings
            self._replace_api_client()
            if not persistent:
                QMessageBox.warning(
                    self,
                    "登录仅在本次运行有效",
                    "系统凭据库不可用，Cookie 仅保存在当前进程内存中；"
                    "重启 BiliFlow 后需要重新登录。",
                )
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
            vip = nav_info.get("vip") or {}
            is_vip = bool(nav_info.get("vipStatus") or vip.get("status"))
            member = "大会员" if is_vip else "普通会员"
            self._set_login_status_label(
                f"已登录：{uname} · {member}",
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
        if self._show_workspace(0):
            self._download_tabs.setCurrentIndex(1)
            self._batch_page._api_client = self._api_client
            self._batch_page._existing_content_identities = (
                self._task_repository.known_content_identities()
            )

    def _enqueue_batch_from_page(self, infos):
        if infos and self._confirm_copyright_acknowledgement():
            self._enqueue_batch_infos(infos)

    def _confirm_copyright_acknowledgement(self) -> bool:
        if self._settings.copyright_notice_version >= COPYRIGHT_NOTICE_VERSION:
            return True
        text = (
            COPYRIGHT_NOTICE_SUMMARY.replace("\n", "<br>")
            + "<br><br>"
            + (
                f'<a href="{COPYRIGHT_DOCUMENT_URL}">项目版权说明</a> · '
                f'<a href="{BILIBILI_TERMS_URL}">Bilibili 服务协议</a>'
            )
        )
        box = MessageBox(
            COPYRIGHT_NOTICE_TITLE,
            text,
            self,
            tone="warning",
            buttons=QMessageBox.Yes | QMessageBox.Cancel,
            default=QMessageBox.Cancel,
            rich_text=True,
        )
        box.button(QMessageBox.Yes).setText("我已了解并继续")
        box.button(QMessageBox.Yes).setObjectName("PrimaryButton")
        box.button(QMessageBox.Cancel).setText("取消")
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return False
        updated = self._settings.model_copy(
            update={"copyright_notice_version": COPYRIGHT_NOTICE_VERSION},
            deep=True,
        )
        try:
            self._config.save(updated)
        except OSError as exc:
            self._show_error(f"无法保存版权确认：{exc}")
            return False
        self._settings = updated
        return True

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
        message = f"已加入 {added} 个任务" + (
            f"，跳过 {skipped} 个重复项" if skipped else ""
        )
        self._status_bar.showMessage(message)
        self._enqueue_notice.set_message(message, "success" if added else "info")
        self._batch_page._existing_content_identities = (
            self._task_repository.known_content_identities()
        )
        self._refresh_activity()

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
        MessageBox(
            "关于 BiliFlow",
            f"BiliFlow · 星轨收藏站 v{__version__}\n\n"
            "视频下载、批量导入与直播录制，统一的本地收藏工作台。\n"
            "支持多 P、番剧、弹幕、字幕与可恢复任务。",
            self,
        ).exec()

    def _show_error(self, message: str):
        MessageBox("任务出现问题", message, self, tone="danger").exec()

    def _show_info(self, message: str):
        MessageBox("运行信息", message, self).exec()

    def closeEvent(self, event: QCloseEvent):
        """Cancel running downloads and close API client on window close."""
        if self._settings_page.dirty and not self._can_leave_settings():
            event.ignore()
            return
        live_service = self._live_page.service
        if (
            self._download_list.has_active_workers
            or (live_service and live_service.active)
        ) and not self._close_confirmed:
            box = MessageBox(
                "退出 BiliFlow",
                "仍有下载或直播录制正在运行。退出将停止录制并保留文件；直播离线期间无法补录。确认退出吗？",
                self,
                tone="warning",
                buttons=QMessageBox.Yes | QMessageBox.No,
                default=QMessageBox.No,
            )
            box.button(QMessageBox.Yes).setText("停止并退出")
            box.button(QMessageBox.Yes).setObjectName("DangerButton")
            if box.exec() != QMessageBox.Yes:
                event.ignore()
                return
            self._close_confirmed = True

        if live_service and not live_service.stopped:
            self._close_confirmed = True
            self._live_page.shutdown()
            self._download_list.pause_all_workers()
            event.ignore()
            QTimer.singleShot(100, self.close)
            return

        self._live_page.shutdown()
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
