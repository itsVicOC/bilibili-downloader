"""Main application window for the Bilibili Downloader."""

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.api.live import BilibiliLiveClient
from bilibili_downloader.core.appearance import BackgroundStore
from bilibili_downloader.core.batch import is_collection_source
from bilibili_downloader.core.builtin_backgrounds import builtin_background
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
    WORKSPACE_NAMES,
    DownloadItem,
    OutputMode,
    TaskStatus,
    VideoInfo,
    VideoQuality,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.core.update_protocol import UpdateError, atomic_json
from bilibili_downloader.core.updater import RELEASES_PAGE
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.dialogs.update_dialog import UpdateDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.resources.paths import asset_path, background_path
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.settings_sections import APPEARANCE_MODES, SettingsSection
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
from bilibili_downloader.gui.update_controller import UpdateController
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    AccountButton,
    FieldRow,
    IconButton,
    MessageBox,
    Notice,
    OutputActionBar,
    PageHeader,
    PopupMenu,
    ResponsiveFields,
    SectionCard,
    WindowDragSurface,
    repolish,
    scroll_area,
)
from bilibili_downloader.gui.widgets.download_list import DownloadListWidget
from bilibili_downloader.gui.widgets.download_options import (
    DownloadOptionCard,
    DownloadOptions,
)
from bilibili_downloader.gui.widgets.hero_panel import HeroPanel
from bilibili_downloader.gui.widgets.live_page import LivePage
from bilibili_downloader.gui.widgets.pixel_mascot import MascotCard
from bilibili_downloader.gui.widgets.task_page import TaskPage
from bilibili_downloader.gui.widgets.video_info import VideoInfoWidget
from bilibili_downloader.gui.widgets.workspace_background import WorkspaceStack
from bilibili_downloader.gui.window_chrome import WindowChrome
from bilibili_downloader.utils.config import ConfigManager
from bilibili_downloader.utils.validators import is_bilibili_url

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config_manager=None, task_repository=None, live_controller=None, *, update_service=None, startup_paused=False, theme_manager=None, desktop_platform=None):
        super().__init__()
        self.setWindowTitle("BiliFlow · 星轨收藏站")
        self.setMinimumSize(900, 640)
        self.resize(1320, 860)
        self._desktop_platform = desktop_platform or sys.platform
        self._chrome = WindowChrome(self, self._desktop_platform)
        self._lifecycle = None
        self._quit_requested = False
        self._quit_prompt_open = False
        self._shutdown_started = False
        self._shutdown_complete = False
        self._deferred_update = None
        # Components
        self._config = config_manager or ConfigManager()
        self._settings = self._config.load()
        self._background_store = BackgroundStore(self._config.data_dir)
        self._theme_manager = theme_manager
        if self._theme_manager is None and (self._settings.appearance.theme != (
            QApplication.instance().property("colorTheme") or "star_trail"
        ) or self._settings.appearance.mode != (QApplication.instance().property("appearanceMode") or "system")):
            self._theme_manager = ThemeManager(QApplication.instance(), self._settings.appearance.theme, self._settings.appearance.mode)
            self._theme_manager.setParent(self)
        if self._theme_manager is not None:
            self._theme_manager.set_color_theme(self._settings.appearance.theme)
            if self._theme_manager.mode != self._settings.appearance.mode:
                self._theme_manager.set_mode(self._settings.appearance.mode)
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
        self._user_profile = {}
        self._login_verified = None
        self._account_state = "unknown"
        self._account_dialog = None
        self._removed_task_records = []
        self._close_confirmed = False
        self._startup_paused = startup_paused
        self._startup_downloads = []
        self._update_in_progress = False
        self._update_ready_to_close = False
        self._update_mutex = None
        self._update_transaction = None
        self._update_helper = None
        self._provided_live_controller = live_controller
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()
        self._setup_updates(update_service)
        self._set_shell_enabled(not startup_paused)
        self._restore_tasks()

        # Check login status on startup
        self._user_face = ""
        if not startup_paused and (getattr(self._config, "auth_cookies", None) or self._settings.sessdata):
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
        self._sidebar = WindowDragSurface()
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
        divider = QFrame()
        divider.setObjectName("SidebarDivider")
        divider.setFixedHeight(1)
        self._side_layout.addWidget(divider)
        self._settings_nav = IconButton("设置", "settings", "NavButton")
        self._settings_nav.clicked.connect(self._on_settings_triggered)
        self._side_layout.addWidget(self._settings_nav)
        self._side_layout.addStretch()
        self._mascot_card = MascotCard(self._sidebar)
        self._side_layout.addWidget(self._mascot_card)
        self._mode_button = IconButton("跟随系统", "appearance", "SidebarAction")
        self._mode_menu = PopupMenu(self._mode_button)
        self._mode_group = QActionGroup(self)
        self._mode_actions = {}
        for label, mode in APPEARANCE_MODES:
            item = self._mode_menu.addAction(label)
            item.setCheckable(True)
            self._mode_group.addAction(item)
            item.triggered.connect(lambda _checked=False, value=mode: self._set_appearance_mode(value))
            self._mode_actions[mode] = item
        self._mode_button.setMenu(self._mode_menu)
        self._side_layout.addWidget(self._mode_button)
        self._account_text = "未登录"
        self._header_login = AccountButton()
        self._header_login.clicked.connect(self._on_login_triggered)
        self._side_layout.addWidget(self._header_login)
        shell.addWidget(self._sidebar)
        workspace = QWidget()
        self._workspace_shell_layout = QVBoxLayout(workspace)
        self._workspace_shell_layout.setContentsMargins(0, 0, 0, 0)
        self._workspace_shell_layout.setSpacing(0)
        shell.addWidget(workspace, 1)
        self._workspace_pages = WorkspaceStack()
        self._workspace_shell_layout.addWidget(self._workspace_pages, 1)
        self._build_download_page()
        self._live_controller = self._provided_live_controller or LiveUiController(
            self._config, self, autostart=not self._startup_paused
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
        self._task_page.undo_remove_requested.connect(self._undo_removed_tasks)
        self._workspace_pages.addWidget(self._task_page)
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(24, 24, 24, 24)
        settings_layout.setSpacing(16)
        settings_header = PageHeader("设置", "统一管理下载偏好、直播录制与媒体工具")
        settings_layout.addWidget(settings_header)
        self._settings_page = SettingsDialog(
            self._settings, embedded=True, background_store=self._background_store,
            desktop_platform=self._desktop_platform,
        )
        self._settings_page.save_requested.connect(self._save_settings)
        self._settings_page.appearance_mode_requested.connect(self._set_appearance_mode)
        self._sync_appearance_mode()
        self._settings_page.cache_requested.connect(self._on_clear_cache)
        self._live_controller.snapshot_changed.connect(self._settings_page.set_live_rooms)
        self._settings_page.set_live_rooms(self._live_controller.rows)
        self._live_controller.settings_applied.connect(
            lambda ok, message: self._settings_page._notice.set_message(message, "success" if ok else "danger")
        )
        settings_layout.addWidget(self._settings_page, 1)
        self._workspace_pages.addWidget(settings_page)
        self._setup_workspace_toolbar((
            self._download_header, self._live_page.header,
            self._task_page.header, settings_header,
        ))
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
        layout.setSpacing(16)
        self._download_header = PageHeader("视频下载", "把喜欢的作品，带回自己的收藏空间")
        layout.addWidget(self._download_header)
        self._download_tabs = QTabWidget()
        layout.addWidget(self._download_tabs, 1)
        body = QWidget()
        self._workspace_layout = QVBoxLayout(body)
        self._workspace_layout.setContentsMargins(0, 0, 4, 0)
        self._workspace_layout.setSpacing(16)
        self._hero = HeroPanel()
        self._hero.set_compact(True)
        self._hero_layout = QVBoxLayout(self._hero)
        self._hero_layout.setContentsMargins(16, 16, 16, 16)
        self._hero_layout.setSpacing(10)
        self._hero_title = QLabel("喜欢的这一集，现在就带回本地。")
        self._hero_title.setObjectName("HeroTitle")
        self._hero_layout.addWidget(self._hero_title)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._url_input = ChineseLineEdit()
        self._url_input.setPlaceholderText("B 站链接、BV / AV / ep 号或 b23.tv 短链")
        self._url_input.setAccessibleName("视频链接或作品编号")
        self._url_input.returnPressed.connect(self._on_resolve_clicked)
        self._url_input.textChanged.connect(self._source_changed)
        row.addWidget(self._url_input, 1)
        self._resolve_btn = QPushButton("开始解析")
        self._resolve_btn.setObjectName("PrimaryButton")
        self._resolve_btn.clicked.connect(self._on_resolve_clicked)
        row.addWidget(self._resolve_btn)
        self._hero_layout.addLayout(row)
        self._workspace_layout.addWidget(self._hero)
        self._resolve_notice = Notice(callback=self._route_current_source)
        self._workspace_layout.addWidget(self._resolve_notice)
        self._empty_download = QWidget()
        empty_layout = QHBoxLayout(self._empty_download)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_hint = QLabel("粘贴作品链接或 BV / AV / ep 号，解析后选择画质、分 P 与保存位置。")
        empty_hint.setWordWrap(True)
        empty_hint.setObjectName("MetaLabel")
        empty_layout.addWidget(empty_hint, 1)
        import_collection = QPushButton("导入收藏夹或合集 →")
        import_collection.setObjectName("TextButton")
        import_collection.clicked.connect(self._on_batch_clicked)
        empty_layout.addWidget(import_collection)
        self._hero_layout.addWidget(self._empty_download)
        self._content_section = QWidget()
        self._content_layout = QBoxLayout(QBoxLayout.LeftToRight, self._content_section)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
        self._video_info = VideoInfoWidget()
        self._content_layout.addWidget(self._video_info, 2, Qt.AlignTop)
        self._build_output_card()
        self._workspace_layout.addWidget(self._content_section)
        self._content_section.hide()
        self._workspace_layout.addStretch()
        self._workspace_scroll = scroll_area(body)
        self._download_tabs.addTab(self._workspace_scroll, "单个解析")
        self._batch_page = BatchDialog(
            api_client=self._api_client,
            existing_content_identities=self._task_repository.known_content_identities(),
            embedded=True,
        )
        self._batch_page.enqueue_requested.connect(self._enqueue_batch_from_page)
        self._batch_page._action_bar.edit_requested.connect(self._show_output_options)
        self._download_tabs.addTab(self._batch_page, "批量导入")
        self._enqueue_notice = Notice(
            action="查看任务", callback=lambda: self._show_tasks(0)
        )
        layout.addWidget(self._enqueue_notice)
        layout.addWidget(self._download_actions)
        self._download_tabs.currentChanged.connect(
            lambda index: self._download_actions.setVisible(index == 0)
        )
        for combo in (self._page_combo, self._quality_combo, self._codec_combo, self._audio_combo, self._output_mode_combo):
            combo.currentIndexChanged.connect(self._refresh_download_summary)
        self._refresh_download_summary()
        self._workspace_pages.addWidget(page)

    def _build_output_card(self):
        controls = SectionCard("输出规格")
        controls.setObjectName("ControlPanel")
        self._output_card = controls
        fields = ResponsiveFields()
        controls.body.addWidget(fields)
        self._page_combo = ComboBox()
        self._page_combo.addItem("当前视频", "current")
        fields.add_field(FieldRow("分 P 范围", self._page_combo))
        self._output_mode_combo = ComboBox()
        self._output_mode_combo.addItem("视频 / MP4", OutputMode.VIDEO)
        self._output_mode_combo.addItem("仅音频 / M4A 或 FLAC", OutputMode.AUDIO)
        self._output_mode_combo.setCurrentIndex(
            max(0, self._output_mode_combo.findData(self._settings.default_output_mode))
        )
        self._output_mode_combo.currentIndexChanged.connect(
            self._sync_output_mode_controls
        )
        fields.add_field(FieldRow("输出类型", self._output_mode_combo))
        self._quality_combo = ComboBox()
        self._populate_quality_combo()
        self._quality_combo.currentIndexChanged.connect(self._refresh_codec_options)
        fields.add_field(FieldRow("画面质量", self._quality_combo))
        self._codec_stack = QStackedWidget()
        self._codec_combo = ComboBox()
        self._populate_codec_combo()
        self._audio_combo = ComboBox()
        self._populate_audio_combo()
        self._codec_stack.addWidget(self._codec_combo)
        self._codec_stack.addWidget(self._audio_combo)
        codec_row = FieldRow("视频编码", self._codec_stack)
        self._codec_label = codec_row.label
        fields.add_field(codec_row)
        self._danmaku_check = DownloadOptionCard("下载弹幕", "ASS", "star")
        self._danmaku_check.setChecked(self._settings.download_danmaku)
        self._subtitle_check = DownloadOptionCard("下载字幕", "SRT", "info")
        self._subtitle_check.setChecked(self._settings.download_subtitle)
        self._all_subtitles_check = self._create_checkbox(
            "全部字幕", self._settings.download_all_subtitles
        )
        self._cover_check = DownloadOptionCard("保存封面", "图片", "folder")
        self._cover_check.setChecked(self._settings.download_cover)
        self._metadata_check = DownloadOptionCard("保存元数据", "JSON", "tasks")
        self._metadata_check.setChecked(self._settings.download_metadata)
        self._subtitle_check.setEnabled(False)
        self._all_subtitles_check.setEnabled(False)
        self._subtitle_check.toggled.connect(
            lambda checked: self._all_subtitles_check.setEnabled(
                checked and self._subtitle_check.isEnabled()
            )
        )
        controls.body.addWidget(DownloadOptions(
            self._danmaku_check, self._subtitle_check, self._all_subtitles_check,
            self._cover_check, self._metadata_check,
        ))
        self._output_summary = QLineEdit(self._settings.output_dir)
        self._output_summary.setReadOnly(True)
        self._output_summary.setToolTip(self._settings.output_dir)
        self._output_summary.setCursorPosition(0)
        controls.body.addWidget(FieldRow("保存目录", self._output_summary))
        self._download_actions = OutputActionBar()
        self._download_hint = self._download_actions.specs
        self._download_path_hint = self._download_actions.directory
        self._edit_output_btn = self._download_actions.edit_button
        self._download_btn = self._download_actions.primary_button
        self._download_actions.edit_requested.connect(self._show_output_options)
        self._download_actions.submit_requested.connect(self._on_download_clicked)
        controls.body.addStretch()
        self._sync_output_mode_controls()
        self._content_layout.addWidget(controls, 3, Qt.AlignTop)

    def _show_output_options(self):
        self._download_tabs.setCurrentIndex(0)
        self._content_section.show()
        self._empty_download.hide()
        self._video_info.setVisible(self._current_video is not None)
        QTimer.singleShot(0, lambda: self._workspace_scroll.ensureWidgetVisible(self._output_card, 0, 12))
        self._quality_combo.setFocus()

    def _refresh_download_summary(self, *_args):
        if not hasattr(self, "_download_hint"):
            return
        audio = self._output_mode_combo.currentData() == OutputMode.AUDIO
        quality = self._quality_combo.currentText() or self._settings.default_quality.label
        codec = {7: "AVC", 12: "HEVC", 13: "AV1"}.get(self._codec_combo.currentData(), "自动编码")
        selection = self._page_combo.currentData()
        count = len(self._current_video.pages) if self._current_video and selection == "all" else 1
        pages = (
            "解析后选择分 P" if self._current_video is None else
            f"全部 {count}P" if selection == "all" else self._page_combo.currentText()
        )
        specs = f"{self._audio_combo.currentText()} · 仅音频 · {pages}" if audio else f"{quality} · {codec} · {pages}"
        state = "已选 1 项" if self._current_video else getattr(self, "_download_result_state", "待解析")
        self._download_actions.status.setText(state)
        if not self._current_video and state != "待解析":
            specs = f"{state}，请重新解析后加入队列"
        self._download_btn.setToolTip("加入下载队列" if self._current_video else "请先成功解析当前来源")
        self._download_hint.set_full_text(specs)
        directory = f"保存至 {self._settings.output_dir}"
        self._download_path_hint.set_full_text(directory)
        if hasattr(self, "_batch_page"):
            batch_specs = f"{self._audio_combo.currentText()} · 仅音频" if audio else f"{quality} · {codec}"
            self._batch_page.set_output_summary(f"{batch_specs} · 各作品全部分 P", directory)

    def _show_workspace(self, index):
        if not getattr(self, "_shell_enabled", True):
            return False
        if (
            self._workspace_pages.currentIndex() == 3
            and index != 3
            and not self._can_leave_settings()
        ):
            self._sync_workspace_actions()
            return False
        if index == 3 and not self._settings_page.dirty:
            self._settings_page.load_settings(self._settings)
        self._workspace_pages.setCurrentIndex(index)
        self._refresh_workspace_background()
        if hasattr(self, "_header_stack"):
            self._header_stack.setCurrentIndex(index)
        self._sync_workspace_actions()
        for i, button in enumerate([*self._nav_buttons, self._settings_nav]):
            button.setObjectName("NavButtonActive" if i == index else "NavButton")
            repolish(button)
            button._sync_icon()
        return True

    def _refresh_workspace_background(self):
        workspace = WORKSPACE_NAMES[self._workspace_pages.currentIndex()]
        reference = getattr(self._settings.appearance.backgrounds, workspace)
        entry = builtin_background(reference)
        self._workspace_pages.set_background(
            background_path(reference, self._background_store),
            builtin=entry is not None,
            pixel_art=entry is not None and entry.style == "pixel",
        )
        self._workspace_pages.set_visibility(
            getattr(self._settings.appearance.background_visibility, workspace)
        )
        self._workspace_pages.set_glass_blur(self._settings.appearance.glass_blur)

    def _sync_workspace_actions(self):
        for index, action in enumerate(getattr(self, "_workspace_actions", ())):
            action.setChecked(index == self._workspace_pages.currentIndex())

    def _setup_workspace_toolbar(self, headers):
        """Keep the page toolbar inside the workspace beside the full sidebar."""
        self._workspace_toolbar = QToolBar("工作区", self)
        self._workspace_toolbar.setObjectName("WorkspaceToolbar")
        self._workspace_toolbar.setMovable(False)
        self._workspace_toolbar.setFloatable(False)
        self._workspace_toolbar.setAllowedAreas(Qt.TopToolBarArea)
        self._workspace_toolbar.layout().setContentsMargins(0, 0, 0, 0)
        self._header_stack = QStackedWidget()
        self._header_stack.setObjectName("WorkspaceHeaders")
        self._header_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for header in headers:
            header.parentWidget().layout().removeWidget(header)
            header.set_shell_geometry(self._sidebar.width(), self._chrome.header_margins)
            self._header_stack.addWidget(header)
        self._workspace_toolbar.addWidget(self._header_stack)
        self._workspace_shell_layout.insertWidget(0, self._workspace_toolbar)

    def nativeEvent(self, event_type, message):
        result = self._chrome.native_event(message)
        if result is not None:
            return True, result
        return super().nativeEvent(event_type, message)

    def _focus_download_input(self):
        if self._show_workspace(0):
            self._download_tabs.setCurrentIndex(0)
            self._url_input.setFocus(Qt.ShortcutFocusReason)
            self._url_input.selectAll()

    def _set_shell_enabled(self, enabled):
        """Include the native toolbar, menus and shortcuts in update isolation."""
        self._shell_enabled = enabled
        for widget in (self.centralWidget(), self._workspace_toolbar, self.menuBar(), self._status_bar):
            widget.setEnabled(enabled)
        for item in self._actions.values():
            item.setEnabled(enabled)
        if enabled:
            self._actions["updates"].setEnabled(not self._updates.busy)
        self._sync_edit_actions()

    def _show_tasks(self, tab=0):
        if self._show_workspace(2):
            self._task_page.tabs.setCurrentIndex(tab)

    def _show_room(self, room_id):
        if self._show_workspace(1):
            self._live_page.select_room(room_id)

    def _show_settings_tab(self, tab):
        if self._show_workspace(3):
            self._settings_page.show_section(tab)

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
        self._codec_stack.setFocusProxy(self._codec_stack.currentWidget())

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
        if hasattr(self, "_header_stack"):
            for index in range(self._header_stack.count()):
                self._header_stack.widget(index).set_shell_geometry(
                    self._sidebar.width(), self._chrome.header_margins
                )
        self._side_layout.setContentsMargins(
            12 if compact else 16,
            48 if self._chrome.expanded and self._desktop_platform == "darwin" else 24,
            12 if compact else 16, 16,
        )
        for widget in (self._brand_copy, self._nav_caption, self._mascot_card):
            widget.setVisible(not compact)
        for button in [*self._nav_buttons, self._settings_nav, self._mode_button, self._header_login]:
            button.set_compact(compact)
        if not compact:
            self._header_login.setText(
                self._header_login.fontMetrics().elidedText(
                    self._account_text, Qt.ElideRight, 108
                )
            )
        content_width = width - (72 if compact else 208) - 48
        self._content_layout.setDirection(
            QBoxLayout.TopToBottom if content_width < 760 else QBoxLayout.LeftToRight
        )

    def resizeEvent(self, event):
        self._update_responsive_layout(event.size().width())
        super().resizeEvent(event)

    def _setup_menu(self):
        """Share actions between system menus, navigation and keyboard access."""
        menubar = self.menuBar()
        menubar.setNativeMenuBar(self._desktop_platform == "darwin")
        menubar.setVisible(self._desktop_platform != "win32" and not (
            self._desktop_platform == "darwin" and QApplication.platformName().startswith("offscreen")
        ))
        self._actions = {}

        def action(key, text, callback, shortcut=None, role=QAction.NoRole):
            item = QAction(text, self)
            item.setMenuRole(role)
            if shortcut is not None:
                item.setShortcut(shortcut)
            item.triggered.connect(callback)
            self.addAction(item)
            self._actions[key] = item
            return item

        # File menu
        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction(action("focus_source", "输入下载链接", self._focus_download_input, QKeySequence("Ctrl+L")))
        file_menu.addAction(action("batch", "批量导入…", self._on_batch_clicked))
        file_menu.addSeparator()
        preferences = QKeySequence.StandardKey.Preferences if sys.platform == "darwin" else QKeySequence("Ctrl+,")
        file_menu.addAction(action("settings", "设置…", self._on_settings_triggered, preferences, QAction.PreferencesRole))
        if self._desktop_platform == "darwin":
            file_menu.addAction(action("close_window", "关闭窗口", self.close, QKeySequence.StandardKey.Close))
        file_menu.addAction(action("quit", "退出 BiliFlow", self.request_quit, QKeySequence.StandardKey.Quit, QAction.QuitRole))

        edit_menu = menubar.addMenu("编辑(&E)")
        for key, label, standard in (
            ("undo", "撤销", QKeySequence.Undo), ("redo", "重做", QKeySequence.Redo),
            ("cut", "剪切", QKeySequence.Cut), ("copy", "复制", QKeySequence.Copy),
            ("paste", "粘贴", QKeySequence.Paste), ("selectAll", "全选", QKeySequence.SelectAll),
        ):
            def edit(_checked=False, method=key):
                editor = QApplication.focusWidget()
                handler = getattr(editor, method, None)
                if callable(handler):
                    handler()
            edit_menu.addAction(action(key, label, edit, standard))

        view_menu = menubar.addMenu("显示(&V)")
        workspace_group = QActionGroup(self)
        self._workspace_actions = []
        for index, text in enumerate(("视频下载", "直播录制", "任务中心", "设置")):
            item = action(f"workspace_{index}", text, lambda _checked=False, page=index: self._show_workspace(page), QKeySequence(f"Ctrl+{index + 1}"))
            item.setCheckable(True)
            workspace_group.addAction(item)
            item.setChecked(self._workspace_pages.currentIndex() == index)
            self._workspace_actions.append(item)
            view_menu.addAction(item)
        tools_menu = menubar.addMenu("工具(&T)")
        tools_menu.addAction(action("login", "账号与登录…", self._on_login_triggered))
        tools_menu.addAction(action("ffmpeg", "检查 FFmpeg", self._on_check_ffmpeg))
        tools_menu.addAction(action("updates", "检查更新…", self._check_updates_from_menu))
        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction(action("about", "关于 BiliFlow", self._on_about_triggered, role=QAction.AboutRole))
        # Buttons consume the same QAction; signals already connected above are
        # disconnected to avoid executing an operation twice.
        for button, key in ((self._settings_nav, "settings"), (self._header_login, "login")):
            button.clicked.disconnect()
            button.clicked.connect(self._actions[key].trigger)
            self._actions[key].changed.connect(lambda b=button, a=self._actions[key]: b.setEnabled(a.isEnabled()))
        edit_menu.aboutToShow.connect(self._sync_edit_actions)
        QApplication.instance().focusChanged.connect(self._sync_edit_actions)
        QApplication.clipboard().dataChanged.connect(self._sync_edit_actions)
        for editor in self.findChildren(QLineEdit) + self.findChildren(QPlainTextEdit) + self.findChildren(QTextEdit):
            editor.selectionChanged.connect(self._sync_edit_actions)
            editor.textChanged.connect(self._sync_edit_actions)
        self._sync_edit_actions()

    def _sync_edit_actions(self, *_args):
        editor = QApplication.focusWidget()
        editable = isinstance(editor, (QLineEdit, QPlainTextEdit, QTextEdit))
        writable = editable and not editor.isReadOnly()
        line = isinstance(editor, QLineEdit)
        selected = editable and (editor.hasSelectedText() if line else editor.textCursor().hasSelection())
        history = editor if line else editor.document() if editable else None
        states = {
            "undo": writable and history.isUndoAvailable(),
            "redo": writable and history.isRedoAvailable(),
            "cut": writable and selected,
            "copy": selected,
            "paste": writable and bool(QApplication.clipboard().text()),
            "selectAll": editable and bool(editor.text() if line else editor.toPlainText()),
        }
        for name, enabled in states.items():
            self._actions[name].setEnabled(bool(enabled) and getattr(self, "_shell_enabled", True))

    def _setup_updates(self, service):
        self._updates = UpdateController(self._config, self, service=service)
        panel = self._settings_page
        panel.update_check_requested.connect(self._updates.check)
        panel.update_install_requested.connect(self._updates.prepare_install)
        panel.update_cancel_requested.connect(self._updates.cancel)
        panel.update_archive_requested.connect(self._open_update_archive)
        panel.update_page_requested.connect(self._open_release_page)
        panel.update_channel_changed.connect(self._updates.invalidate_check)
        self._updates.status_changed.connect(panel._update_notice.set_message)
        self._updates.busy_changed.connect(panel.set_update_busy)
        self._updates.busy_changed.connect(lambda busy, _kind: self._actions["updates"].setEnabled(not busy and self._shell_enabled))
        self._updates.progress_changed.connect(panel._update_progress.setValue)
        self._updates.pending_changed.connect(panel.set_pending_update)
        self._updates.available.connect(self._on_update_available)
        self._updates.prepared.connect(self._on_update_prepared)
        self._updates.failed.connect(self._on_update_failed)
        panel.set_pending_update(self._updates.pending)
        if self._updates.pending:
            panel._update_notice.set_message(
                self._updates.pending.reason or f"v{self._updates.pending.release.version} 已下载，可安装并重启。",
                "warning" if self._updates.pending.reason else "success",
            )

    def start_startup_update_check(self):
        # Called by the real entry point after show(); standalone widgets/tests stay offline.
        if self._settings.auto_check_updates and not self._startup_paused and not self._updates.busy and not self._updates.has_checked:
            self._updates.check(self._settings.update_channel, manual=False)

    def resume_startup(self):
        self._startup_paused = False
        self._set_shell_enabled(True)
        self._live_controller.start_background()
        for item, task_id in self._startup_downloads:
            self._start_download(item, task_id)
        self._startup_downloads.clear()
        if self._settings.sessdata:
            self._update_login_status()

    def _on_update_available(self, release):
        if self._update_in_progress or self._quit_requested:
            return
        if self._quit_prompt_open or (self._lifecycle and self.isHidden()):
            self._deferred_update = release
            return
        choice = UpdateDialog(release, self).exec()
        if choice == UpdateDialog.SKIP:
            latest = self._config.load().model_copy(deep=True)
            if release.version not in latest.skipped_update_versions:
                latest.skipped_update_versions.append(release.version)
            try:
                self._config.save(latest)
                self._settings = latest
                self._settings_page._update_notice.set_message(f"已跳过 v{release.version}；手动检查仍可更新。")
            except OSError as exc:
                self._show_error(f"无法保存跳过版本记录：{exc}")
        elif choice == UpdateDialog.UPDATE:
            self._show_settings_tab(SettingsSection.ABOUT)
            self._updates.download(release)

    def show_deferred_update(self):
        release, self._deferred_update = self._deferred_update, None
        if release is not None:
            QTimer.singleShot(0, lambda: self._on_update_available(release))

    def _open_release_page(self):
        release = self._updates.release
        QDesktopServices.openUrl(QUrl(release.page_url if release else RELEASES_PAGE))

    def _open_update_archive(self):
        if self._updates.pending and self._updates.pending.archive.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._updates.pending.archive)))

    def _on_update_failed(self, message, manual):
        if manual:
            box = MessageBox("更新未完成", message, self, tone="warning", buttons=QMessageBox.Ok | QMessageBox.Open, default=QMessageBox.Ok)
            box.button(QMessageBox.Open).setText("版本下载页")
            if box.exec() == QMessageBox.Open:
                self._open_release_page()

    def _on_update_prepared(self, prepared):
        if self._quit_requested:
            return
        if self._lifecycle and self.isHidden():
            self._lifecycle.restore_window()
        if prepared.reason:
            self._on_update_failed(prepared.reason, True)
            return
        active = self._download_list.has_active_workers or self._live_controller.exporting or (
            self._live_controller.service and self._live_controller.service.active
        )
        if active:
            box = MessageBox(
                "更新已准备好", "安装更新需要重启：下载将暂停并保留断点，直播录制将停止并保留文件，正在导出的任务将取消。",
                self, tone="warning", buttons=QMessageBox.Yes | QMessageBox.No, default=QMessageBox.No,
            )
            box.button(QMessageBox.Yes).setText("停止任务并重启")
            box.button(QMessageBox.No).setText("稍后重启")
            if box.exec() != QMessageBox.Yes:
                return
        if not self._can_leave_settings():
            return
        self._update_mutex = self._updates.service.install_mutex()
        try:
            if not self._update_mutex.acquire():
                raise UpdateError("另一个实例正在安装更新，请稍后重试")
        except (OSError, UpdateError) as exc:
            self._on_update_failed(str(exc), True)
            return
        self._update_in_progress = True
        self._set_shell_enabled(False)
        self._update_deadline = time.monotonic() + 120
        self._download_list.pause_all_workers()
        self._live_controller.shutdown()
        self._settings_page._update_notice.set_message("正在停止后台任务并完成录制收尾…")
        self._update_shutdown_timer = QTimer(self)
        self._update_shutdown_timer.setInterval(100)
        self._update_shutdown_timer.timeout.connect(self._wait_update_shutdown)
        self._update_shutdown_timer.start()

    def _wait_update_shutdown(self):
        if time.monotonic() > self._update_deadline:
            self._abort_update_install("后台任务未能及时停止，更新已中止；已下载更新包仍保留。")
            return
        if not (self._download_pool.waitForDone(0) and self._service_pool.waitForDone(0) and self._live_controller.background_stopped):
            return
        if self._update_helper is None:
            try:
                self._update_helper, self._update_transaction = self._updates.service.launch_helper(
                    self._updates.pending,
                    protected_paths=(self._live_controller.export_path, self._live_controller.export_destination),
                )
                self._helper_deadline = time.monotonic() + 20
                self._settings_page._update_notice.set_message("正在启动独立更新程序…")
            except (OSError, UpdateError) as exc:
                self._abort_update_install(str(exc))
            return
        directory = self._update_transaction.parent
        try:
            expected = json.loads(self._update_transaction.read_text("utf-8"))["token"]
            ready = json.loads((directory / "helper-ready.json").read_text("utf-8"))
            initialized = ready.get("token") == expected
        except (OSError, ValueError, KeyError):
            initialized = False
        if initialized:
            self._update_shutdown_timer.stop()
            self._close_confirmed = True
            self._update_ready_to_close = True
            self.request_quit(confirmed=True, reason="update")
        elif self._update_helper.poll() is not None or time.monotonic() > self._helper_deadline:
            try:
                message = json.loads((directory / "status.json").read_text("utf-8"))["message"]
            except (OSError, ValueError, KeyError):
                message = "独立更新程序未能启动，当前程序已保留。"
            self._abort_update_install(message)

    def _abort_update_install(self, message):
        self._update_shutdown_timer.stop()
        if self._update_transaction:
            atomic_json(self._update_transaction.parent / "cancel.json", {})
        if self._update_mutex:
            self._update_mutex.release()
        self._update_in_progress = False
        self._update_helper = None
        self._update_transaction = None
        self._set_shell_enabled(True)
        if not self._live_controller.restart_after_update_abort():
            self._status_bar.showMessage("后台任务仍在收尾，请稍后重新打开软件。")
        self._settings_page._update_notice.set_message(message, "danger")
        self._on_update_failed(message, True)

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
        if self._lifecycle:
            self._lifecycle.refresh_activity()

    def _set_login_status_label(self, text, style_name, tooltip="", *, account_name=None):
        self._login_status_label.setText(text)
        self._login_status_label.setObjectName(style_name)
        self._account_text = account_name or text
        self._header_login.full_text = self._account_text
        self._header_login.setProperty("signedIn", account_name is not None)
        repolish(self._header_login)
        self._login_verified = True if account_name is not None else False if text == "未登录" else None
        if account_name is None:
            self._header_login.set_avatar()
            self._user_face = ""
            self._user_profile = {}
        compact = self._sidebar.width() == 72
        self._header_login.set_compact(compact)
        if not compact:
            self._header_login.setText(
                self._header_login.fontMetrics().elidedText(self._account_text, Qt.ElideRight, 108)
            )
        self._header_login.setToolTip(
            " · ".join(part for part in (text, tooltip) if part)
        )
        self._header_login.setAccessibleName(text)

    def _source_changed(self, text):
        self._resolve_notice.action.hide()
        if hasattr(self, "_download_btn") and text.strip() != getattr(
            self, "_resolved_url", ""
        ):
            self._current_video = None
            self._download_result_state = "来源已修改" if getattr(self, "_resolved_url", "") else "待解析"
            self._download_btn.setEnabled(False)
            self._video_info._state_label.setText("等待解析")
            self._video_info._state_label.set_tone("muted")
            self._refresh_download_summary()
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
            if self._startup_paused:
                self._startup_downloads.append((item, task_id))
            else:
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

        if is_collection_source(url):
            self._suggest_source_route("batch", "这是收藏夹、合集或番剧季度，可转到批量导入。")
            return
        if url.startswith(("https://live.bilibili.com/", "http://live.bilibili.com/")):
            try:
                BilibiliLiveClient.parse_room_id(url)
            except ValueError:
                pass
            else:
                self._suggest_source_route("live", "这是直播间，可转到直播录制。")
                return
        self._resolve_notice.action.hide()
        if not is_bilibili_url(url):
            self._resolve_notice.set_message(
                "无法识别这个来源。番剧季度、合集和收藏夹请使用批量导入。", "warning"
            )
            return

        self._resolve_request_url = url
        self._current_video = None
        self._download_btn.setEnabled(False)
        self._refresh_download_summary()
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
        self._resolve_worker.routed.connect(self._on_resolve_route)
        self._service_pool.start(self._resolve_runner)

    def _on_resolve_route(self, target, source):
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("开始解析")
        self._video_info._state_label.setText("等待解析")
        if self._resolve_request_url != self._url_input.text().strip():
            self._resolve_notice.set_message("来源已修改，请重新解析。", "warning")
            return
        self._status_bar.showMessage("已识别来源，请选择对应工作区。")
        self._suggest_source_route(target, "短链已识别为批量来源。" if target == "batch" else "短链已识别为直播间。", source)

    def _suggest_source_route(self, target, message, source=None):
        self._resolve_notice.set_message(message, "info")
        self._source_route_target = target
        self._source_route_url = source
        self._resolve_notice.action.setText("转到批量导入" if target == "batch" else "转到直播录制")
        self._resolve_notice.action.show()

    def _route_current_source(self):
        source = self._source_route_url or self._url_input.text().strip()
        if self._source_route_target == "batch":
            self._on_batch_clicked()
            existing = self._batch_page._url_text.toPlainText().strip()
            if source not in existing.splitlines():
                self._batch_page._url_text.setPlainText("\n".join(part for part in (existing, source) if part))
            self._batch_page._collapse_btn.setChecked(False)
            self._batch_page._url_text.setFocus()
        elif self._show_workspace(1):
            self._live_page.source.setText(source)
            self._live_page.source.setFocus()

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
        preferred_quality = self._quality_combo.currentData()
        self._resolve_notice.set_message("")
        self._download_btn.setEnabled(True)
        self._status_bar.showMessage(f"已解析：{info.title}")

        self._current_video = info
        self._download_result_state = "已解析"
        self._content_section.show()
        self._empty_download.hide()
        self._video_info.show()
        self._current_video.video_streams = video_streams
        self._current_video.audio_streams = audio_streams
        self._video_info.set_video_info(info)
        self._populate_page_combo(info)

        QUALITY_ID_TO_ENUM = {q.value: q for q in VideoQuality}

        self._quality_combo.blockSignals(True)
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
                default_index = self._quality_combo.findData(preferred_quality)
                self._quality_combo.setCurrentIndex(
                    default_index if default_index >= 0 else 0
                )
            else:
                self._populate_quality_combo()
        else:
            # playurl failed or no streams — fallback to full list
            self._quality_combo.clear()
            self._populate_quality_combo()
            preferred_index = self._quality_combo.findData(preferred_quality)
            if preferred_index >= 0:
                self._quality_combo.setCurrentIndex(preferred_index)
        self._quality_combo.blockSignals(False)

        self._refresh_codec_options()
        available_audio = {stream.id for stream in audio_streams}
        self._populate_audio_combo(available_audio or None)
        self._subtitle_check.setEnabled(True)
        self._subtitle_check.setToolTip("每个分 P 下载时会单独查询可用字幕轨道")
        self._all_subtitles_check.setEnabled(self._subtitle_check.isChecked())
        self._refresh_download_summary()

    def _on_resolve_error(self, error: str):
        """Handle resolution error."""
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("开始解析")
        self._status_bar.showMessage("解析失败")
        self._download_btn.setEnabled(False)
        self._current_video = None
        self._download_result_state = "解析失败"
        self._refresh_download_summary()
        self._video_info._state_label.setText("结果已失效")
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
        self._remove_task_records([download_id])

    def _remove_task_records(self, task_ids):
        try:
            records = [record for task_id in task_ids if (record := self._task_repository.get(task_id)) is not None]
            self._task_repository.delete_many(task_ids)
        except (OSError, sqlite3.Error) as exc:
            self._show_error(f"移除记录失败：{exc}")
            return
        for task_id in task_ids:
            self._download_list.remove_item(task_id)
        self._removed_task_records = records
        if task_ids:
            self._task_page.undo_notice.set_message(f"已移除 {len(task_ids)} 条记录，媒体文件和断点仍保留。", "info")
            self._task_page.undo_notice.action.setVisible(bool(records))
        self._task_page.refresh_downloads()

    def _undo_removed_tasks(self):
        restored = 0
        try:
            records = self._task_repository.restore_records(self._removed_task_records)
        except (OSError, sqlite3.Error) as exc:
            self._task_page.undo_notice.set_message(f"恢复记录失败，可重试：{exc}", "danger")
            return
        for record in records:
            self._download_list.add_item(
                record.item, download_id=record.id, status=record.status,
                progress=record.progress, status_text=record.status_text,
                output_path=record.output_path, warnings=record.warnings,
            )
            restored += 1
        skipped = len(self._removed_task_records) - restored
        self._removed_task_records = []
        self._task_page.undo_notice.set_message("")
        self._status_bar.showMessage(f"已恢复 {restored} 条记录" + (f"，{skipped} 条已有相同任务" if skipped else ""), 5000)
        self._task_page.refresh_downloads()

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
        task_ids = self._task_page.bulk_ids("pause")
        for task_id in task_ids:
            self._download_list._on_pause_clicked(task_id)
        self._status_bar.showMessage(f"正在暂停 {len(task_ids)} 项任务…")

    def _on_resume_all(self):
        task_ids = self._task_page.bulk_ids("resume")
        for task_id in task_ids:
            self._on_retry_download(task_id)
        self._status_bar.showMessage(f"已继续 {len(task_ids)} 个任务")

    def _on_clear_completed(self):
        self._remove_task_records(self._task_page.bulk_ids("clear"))

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
            self._settings_page.install_backgrounds(self._background_store)
            self._config.save(new_settings)
        except (OSError, ValueError) as exc:
            self._settings_page._notice.set_message(f"设置保存失败：{exc}", "danger")
            return False
        theme_changed = new_settings.appearance.theme != self._settings.appearance.theme
        self._settings = new_settings
        if self._theme_manager is None and theme_changed:
            self._theme_manager = ThemeManager(QApplication.instance(), new_settings.appearance.theme, new_settings.appearance.mode)
            self._theme_manager.setParent(self)
        elif self._theme_manager is not None and theme_changed:
            self._theme_manager.set_color_theme(new_settings.appearance.theme)
        self._refresh_workspace_background()
        try:
            self._background_store.cleanup(new_settings.appearance.backgrounds.model_dump().values())
        except OSError:
            logger.warning("Unused background images could not be removed")
        self._apply_thread_pool_settings()
        self._apply_settings_to_controls()
        modes = self._settings_page.directory_modes()
        self._live_controller.apply_live_settings(new_settings.live, modes)
        self._live_page.check_engine()
        self._settings_page.load_settings(new_settings, keep_directory_choices=bool(modes))
        self._settings_page._notice.set_message("设置已保存，正在应用房间目录规则…" if modes else "设置已保存", "info" if modes else "success")
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
        self._refresh_download_summary()

    def _on_login_triggered(self):
        """Open login dialog."""
        current_cookies = getattr(self._config, "auth_cookies", {})
        dialog = LoginDialog(current_cookies or self._settings.sessdata, self, account=self._user_profile, avatar_icon=self._header_login.account_icon(), account_valid=self._login_verified, account_state=self._account_state)
        self._account_dialog = dialog
        try:
            accepted = dialog.exec()
        finally:
            self._account_dialog = None
            dialog.deleteLater()
        if accepted:
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
            self._user_profile = {}
            self._user_face = ""
            self._header_login.set_avatar()
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
        self._account_state = "checking"
        self._set_login_status_label("正在检查账号...", "MutedLabel", account_name=self._user_profile.get("uname"))
        self._login_verified = None
        self._sync_account_dialog()
        self._login_status_worker = LoginStatusWorker(self._api_client, request_id)
        self._login_status_worker.finished.connect(self._on_login_status_result)
        self._login_status_worker.error.connect(self._on_login_status_error)
        self._login_status_worker.avatar_ready.connect(self._on_login_status_avatar)
        self._login_status_runner = LoginStatusRunner(self._login_status_worker)
        self._service_pool.start(self._login_status_runner)

    def _on_login_status_result(self, request_id: int, nav_info: dict):
        if request_id != self._login_status_request_id:
            return
        if nav_info.get("isLogin"):
            self._account_state = "valid"
            if self._user_profile.get("mid") != nav_info.get("mid") or self._user_face != nav_info.get("face", ""):
                self._header_login.set_avatar()
            self._user_profile = {key: nav_info.get(key) for key in ("uname", "mid", "vipStatus", "vip")}
            uname = str(nav_info.get("uname") or "未知用户")
            mid = nav_info.get("mid", "")
            self._user_face = nav_info.get("face", "")
            vip = nav_info.get("vip") or {}
            is_vip = bool(nav_info.get("vipStatus") or vip.get("status"))
            member = "大会员" if is_vip else "普通会员" if nav_info.get("vipStatus") is not None or vip.get("status") is not None else "会员状态待确认"
            self._set_login_status_label(
                f"已登录：{uname} · {member}",
                "StatusPill",
                f"UID: {mid}",
                account_name=uname,
            )
        else:
            self._account_state = "expired"
            self._set_login_status_label("未登录", "MutedLabel")
        self._sync_account_dialog()

    def _on_login_status_avatar(self, request_id: int, data: bytes):
        if request_id == self._login_status_request_id and self._user_face:
            self._header_login.set_avatar(data)
            self._sync_account_dialog()

    def _on_login_status_error(self, request_id: int, error: str):
        if request_id != self._login_status_request_id:
            return
        logger.warning("Login status check failed: %s", error)
        self._account_state = "unknown"
        self._set_login_status_label("登录状态未知", "MutedLabel", account_name=self._user_profile.get("uname"))
        self._login_verified = None
        self._sync_account_dialog()

    def _sync_account_dialog(self):
        dialog = self._account_dialog
        if dialog is not None:
            dialog.set_account(self._user_profile, self._header_login.account_icon(), self._login_verified, self._account_state)

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
        if not self._actions["ffmpeg"].isEnabled():
            return
        self._actions["ffmpeg"].setEnabled(False)
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
        self._actions["ffmpeg"].setEnabled(self._shell_enabled)
        self._show_settings_tab(SettingsSection.TOOLS)
        self._settings_page._probe_notice.set_message(
            f"FFmpeg {'可用' if available else '不可用，请选择有效路径后重试'}：{msg}",
            "success" if available else "danger",
        )

    def _on_about_triggered(self):
        self._show_settings_tab(SettingsSection.ABOUT)

    def _check_updates_from_menu(self):
        self._show_settings_tab(SettingsSection.ABOUT)
        self._updates.check(self._settings_page._update_channel.currentData())

    def _sync_appearance_mode(self):
        mode = self._settings.appearance.mode
        self._mode_actions[mode].setChecked(True)
        label = dict((value, text) for text, value in APPEARANCE_MODES)[mode]
        self._mode_button.full_text = label
        self._mode_button.setText("" if self.width() < 1120 else label)
        self._mode_button.setToolTip(f"外观模式：{label}")
        self._mode_button.setAccessibleName(f"外观模式：{label}")
        self._settings_page.sync_appearance_mode(mode)

    def _set_appearance_mode(self, mode):
        latest = self._config.load().model_copy(deep=True)
        latest.appearance.mode = mode
        try:
            self._config.save(latest)
        except (OSError, ValueError) as exc:
            self._sync_appearance_mode()
            self._status_bar.showMessage(f"外观模式保存失败：{exc}")
            self._settings_page._notice.set_message(f"外观模式保存失败：{exc}", "danger")
            return False
        self._settings.appearance.mode = latest.appearance.mode
        if self._theme_manager is None:
            self._theme_manager = ThemeManager(QApplication.instance(), self._settings.appearance.theme, mode)
            self._theme_manager.setParent(self)
        else:
            self._theme_manager.set_mode(mode)
        self._sync_appearance_mode()
        self._refresh_workspace_background()
        return True

    def _show_error(self, message: str):
        MessageBox("任务出现问题", message, self, tone="danger").exec()

    def _show_info(self, message: str):
        MessageBox("运行信息", message, self).exec()

    def has_background_tasks(self):
        controller = self._live_controller
        rows = controller.service.snapshot() if controller.service else controller.rows
        return (
            self._download_list.has_active_workers
            or controller.exporting
            or (not controller._closed and (
                (controller.service is not None and controller.service.active)
                or any(row.get("enabled") for row in rows)
            ))
        )

    def remember_close_action(self, action):
        latest = self._config.load().model_copy(deep=True)
        latest.windows_close_action = action
        try:
            self._config.save(latest)
        except (OSError, ValueError) as exc:
            self._settings_page._notice.set_message(f"无法记住关闭选择，本次操作仍会执行：{exc}", "warning")
            self._status_bar.showMessage("无法记住关闭选择，下次仍会询问；本次操作继续执行。")
            return
        self._settings.windows_close_action = action
        self._settings_page.sync_close_action(action)

    def request_quit(self, _checked=False, *, confirmed=False, reason="user"):
        """Approve a real exit, then drain owned workers without blocking Qt."""
        if self._quit_requested:
            return True
        if self._quit_prompt_open:
            return False
        if self._update_in_progress and not self._update_ready_to_close:
            return False
        self._quit_prompt_open = True
        try:
            needs_confirmation = self.has_background_tasks() and not (confirmed or self._close_confirmed)
            if reason != "update":
                if self.isHidden() and (self._settings_page.dirty or needs_confirmation):
                    if self._lifecycle:
                        self._lifecycle.restore_window()
                    else:
                        self.show()
                if not self._can_leave_settings():
                    return False
                if needs_confirmation:
                    box = MessageBox(
                        "退出 BiliFlow",
                        "仍有下载、直播监控、录制或导出任务。退出会暂停下载并保留断点，"
                        "停止监控和录制并保留文件，中止导出。直播离线期间无法补录。",
                        self, tone="warning", buttons=QMessageBox.Yes | QMessageBox.No,
                        default=QMessageBox.No,
                    )
                    box.button(QMessageBox.Yes).setText("停止任务并退出")
                    box.button(QMessageBox.Yes).setObjectName("DangerButton")
                    if box.exec() != QMessageBox.Yes:
                        return False
            self._close_confirmed = True
            self._quit_requested = True
        finally:
            self._quit_prompt_open = False
        self._begin_shutdown()
        return True

    def _begin_shutdown(self):
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._set_shell_enabled(False)
        self._status_bar.showMessage("正在停止后台任务并完成录制收尾…")
        self._batch_page.cancel_resolution()
        self._updates.shutdown()
        if not self._live_controller._closed:
            self._live_page.shutdown()
        self._download_list.pause_all_workers()
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(100)
        self._shutdown_timer.timeout.connect(self._poll_shutdown)
        self._shutdown_timer.start()
        QTimer.singleShot(0, self._poll_shutdown)

    def _poll_shutdown(self):
        if self._shutdown_complete:
            return
        if not (self._live_controller.background_stopped
                and self._download_pool.waitForDone(0)
                and self._service_pool.waitForDone(0)
                and self._updates.pool.waitForDone(0)
                and not self._batch_page._busy):
            return
        self._shutdown_timer.stop()
        for client in [self._api_client, *self._retired_api_clients]:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.debug("Failed to close API client", exc_info=True)
        self._shutdown_complete = True
        self.close()
        if self._lifecycle:
            self._lifecycle.finish_quit()

    def closeEvent(self, event: QCloseEvent):
        if self._shutdown_complete:
            super().closeEvent(event)
            return
        event.ignore()
        if self._update_in_progress and not self._update_ready_to_close:
            return
        if self._quit_requested:
            return
        if self._lifecycle and self._lifecycle.platform in ("darwin", "win32"):
            self._lifecycle.close_window()
        else:
            self.request_quit()


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
