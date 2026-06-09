"""Main application window for the Bilibili Downloader."""

import logging

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWidgets import QCheckBox

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import (
    DownloadItem,
    VideoInfo,
    VideoQuality,
)
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.threads.batch_worker import BatchRunner, BatchWorker
from bilibili_downloader.gui.threads.download_worker import DownloadRunner, DownloadWorker
from bilibili_downloader.gui.threads.resolve_worker import ResolveRunner, ResolveWorker
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.download_list import DownloadListWidget
from bilibili_downloader.gui.widgets.video_info import VideoInfoWidget
from bilibili_downloader.utils.config import ConfigManager
from bilibili_downloader.utils.validators import is_bilibili_url

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("哔哩哔哩视频下载器")
        self.setMinimumSize(920, 640)
        self.setStyleSheet(load_stylesheet())

        # Components
        self._config = ConfigManager()
        self._settings = self._config.load()
        self._api_client = self._create_api_client()
        self._thread_pool = QThreadPool()
        self._apply_thread_pool_settings()

        # State
        self._current_video: VideoInfo | None = None
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()

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
        self._thread_pool.setMaxThreadCount(max_downloads)

    def _setup_ui(self):
        """Build the main UI layout."""
        central = QWidget()
        central.setObjectName("AppSurface")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        # -- Top Section --
        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_layout = QVBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 14, 16, 16)
        top_layout.setSpacing(12)

        heading_layout = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        app_title = QLabel("哔哩哔哩视频下载器")
        app_title.setObjectName("AppTitle")
        app_caption = QLabel("视频解析、画质选择与下载队列")
        app_caption.setObjectName("Caption")
        title_block.addWidget(app_title)
        title_block.addWidget(app_caption)
        heading_layout.addLayout(title_block)
        heading_layout.addStretch()
        top_layout.addLayout(heading_layout)

        url_layout = QHBoxLayout()
        url_layout.setSpacing(10)

        self._url_input = ChineseLineEdit()
        self._url_input.setObjectName("UrlInput")
        self._url_input.setPlaceholderText(
            "粘贴视频链接、BV号、AV号或 b23.tv 短链"
        )
        url_layout.addWidget(self._url_input)

        self._resolve_btn = QPushButton("解析")
        self._resolve_btn.setObjectName("PrimaryButton")
        self._resolve_btn.clicked.connect(self._on_resolve_clicked)
        url_layout.addWidget(self._resolve_btn)

        top_layout.addLayout(url_layout)
        layout.addWidget(top_bar)

        # -- Video Info Section --
        self._video_info = VideoInfoWidget()
        layout.addWidget(self._video_info)

        # -- Download Controls --
        controls = QWidget()
        controls.setObjectName("Toolbar")
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setHorizontalSpacing(12)
        controls_layout.setVerticalSpacing(10)

        settings_label = QLabel("下载设置")
        settings_label.setObjectName("SectionTitle")
        controls_layout.addWidget(settings_label, 0, 0)

        vq_label = QLabel("画质")
        vq_label.setObjectName("MetaLabel")
        controls_layout.addWidget(vq_label, 0, 1)
        self._quality_combo = QComboBox()
        self._populate_quality_combo()
        controls_layout.addWidget(self._quality_combo, 0, 2)

        vc_label = QLabel("编码")
        vc_label.setObjectName("MetaLabel")
        controls_layout.addWidget(vc_label, 0, 3)
        self._codec_combo = QComboBox()
        self._codec_combo.addItem("HEVC/H.265（推荐）", 12)
        self._codec_combo.addItem("AVC/H.264（兼容性好）", 7)
        self._codec_combo.addItem("AV1（体积最小）", 13)
        controls_layout.addWidget(self._codec_combo, 0, 4)

        self._danmaku_check = self._create_checkbox("下载弹幕", self._settings.download_danmaku)
        self._subtitle_check = self._create_checkbox("下载字幕", self._settings.download_subtitle)
        controls_layout.addWidget(self._danmaku_check, 1, 1, 1, 2)
        controls_layout.addWidget(self._subtitle_check, 1, 3, 1, 2)

        self._download_btn = QPushButton("下载")
        self._download_btn.setObjectName("PrimaryButton")
        self._download_btn.clicked.connect(self._on_download_clicked)
        controls_layout.addWidget(self._download_btn, 0, 6)

        self._batch_btn = QPushButton("批量下载")
        self._batch_btn.setObjectName("SubtleButton")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        controls_layout.addWidget(self._batch_btn, 1, 6)
        controls_layout.setColumnStretch(5, 1)

        layout.addWidget(controls)

        # -- Download List --
        queue_header = QHBoxLayout()
        queue_title = QLabel("下载队列")
        queue_title.setObjectName("SectionTitle")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        layout.addLayout(queue_header)

        self._download_list = DownloadListWidget()
        self._download_list.retry_requested.connect(self._on_retry_download)
        layout.addWidget(self._download_list)

    def _create_checkbox(self, text: str, checked: bool):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        return cb

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

    def _setup_menu(self):
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("文件(&F)")

        settings_action = QAction("设置(&S)", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_settings_triggered)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
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

    # -- Event Handlers --

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
        self._thread_pool.start(self._resolve_runner)

    def _on_resolve_success(self, info, video_streams, audio_streams, playurl_ok):
        """Handle successful URL resolution."""
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("解析")
        self._status_bar.showMessage(f"已解析：{info.title}")

        self._current_video = info
        self._current_video.video_streams = video_streams
        self._current_video.audio_streams = audio_streams
        self._video_info.set_video_info(info)

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
            # Auto-select highest (first) quality
            self._quality_combo.setCurrentIndex(0)
        else:
            # playurl failed or no streams — fallback to full list
            self._quality_combo.clear()
            self._populate_quality_combo()

        # Update subtitle checkbox based on available subtitles
        if info.subtitle_list:
            self._subtitle_check.setEnabled(True)
            self._subtitle_check.setChecked(True)
        else:
            self._subtitle_check.setChecked(False)

    def _on_resolve_error(self, error: str):
        """Handle resolution error."""
        self._resolve_btn.setEnabled(True)
        self._resolve_btn.setText("解析")
        self._status_bar.showMessage("解析失败")
        self._show_error(f"解析视频失败：{error}")

    def _on_retry_download(self, download_id: int):
        """Retry a failed download."""
        item = self._download_list.get_item(download_id)
        if item:
            # Reset UI
            self._download_list.mark_failed_retry_reset(download_id)
            self._start_download(item, download_id)
            self._status_bar.showMessage(f"重试下载：{item.video_info.title}")

    def _on_download_clicked(self):
        """Start downloading the resolved video."""
        if self._current_video is None:
            self._show_error("请先解析一个视频链接")
            return

        quality = self._quality_combo.currentData()
        codec = self._codec_combo.currentData()

        item = DownloadItem(
            video_info=self._current_video,
            selected_quality=quality,
            selected_video_codec=codec,
            download_danmaku=self._danmaku_check.isChecked(),
            download_subtitle=self._subtitle_check.isChecked(),
        )

        # Add to download list
        download_id = self._download_list.add_item(item)
        self._status_bar.showMessage(f"已加入队列：{item.video_info.title}")

        # Start download in background thread
        self._start_download(item, download_id)

    def _start_download(self, item, download_id: int):
        """Start a download in a background thread via thread pool."""
        worker = DownloadWorker(
            api_client=self._api_client,
            item=item,
            output_dir=self._settings.output_dir,
            download_danmaku=item.download_danmaku,
            download_subtitle=item.download_subtitle,
            download_id=download_id,
            ffmpeg_path=self._settings.ffmpeg_path or None,
        )
        runner = DownloadRunner(worker)

        # Connect signals
        worker.progress.connect(
            lambda idx, pct, text: self._download_list.update_progress(
                idx, pct, text
            )
        )
        worker.finished.connect(self._on_download_finished)
        worker.error.connect(self._on_download_error)

        self._thread_pool.start(runner)
        self._download_list.register_worker(download_id, worker)

    def _start_batch_download(self, urls: list[str]):
        """Resolve multiple videos in background and add to download queue."""
        self._status_bar.showMessage(f"正在批量解析 {len(urls)} 个视频...")
        self._batch_worker = BatchWorker()
        self._batch_worker.item_ready.connect(self._on_batch_item_ready)
        self._batch_worker.error.connect(self._on_batch_item_error)
        self._batch_worker.finished.connect(
            lambda: self._status_bar.showMessage("批量解析完成")
        )

        runner = BatchRunner(
            self._batch_worker,
            self._api_client,
            urls,
            self._quality_combo.currentData(),
            self._codec_combo.currentData(),
            self._danmaku_check.isChecked(),
            self._subtitle_check.isChecked(),
        )
        self._thread_pool.start(runner)

    def _on_batch_item_ready(self, item):
        """Handle a single resolved video from batch processing."""
        download_id = self._download_list.add_item(item)
        self._start_download(item, download_id)
        self._status_bar.showMessage(f"已加入队列：{item.video_info.title}")

    def _on_batch_item_error(self, error: str):
        """Handle a single failed resolution from batch processing."""
        self._show_error(error)

    def _on_download_finished(self, download_id: int, path: str):
        """Handle download completion."""
        self._download_list.mark_done(download_id)
        self._status_bar.showMessage(f"下载完成：{path}")

    def _on_download_error(self, download_id: int, error: str):
        """Handle download error."""
        self._download_list.mark_failed(download_id, error)
        self._status_bar.showMessage(f"下载失败：{error}")

    def _on_settings_triggered(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self._config.save(new_settings)
            self._settings = new_settings
            self._apply_thread_pool_settings()
            self._api_client = self._create_api_client()

    def _on_login_triggered(self):
        """Open login dialog."""
        dialog = LoginDialog(self._settings.sessdata, self)
        if dialog.exec():
            sessdata = dialog.get_sessdata()
            self._settings.sessdata = sessdata
            self._config.save(self._settings)
            self._api_client = self._create_api_client()
            # Fetch and display user info
            self._update_login_status()

    def _update_login_status(self):
        """Fetch user info and update the login status display."""
        try:
            nav_info = self._api_client.get_nav_info()
            if nav_info.get("isLogin"):
                uname = nav_info.get("uname", "未知用户")
                mid = nav_info.get("mid", "")
                face_url = nav_info.get("face", "")
                self._set_login_status_label(
                    f"已登录：{uname}",
                    "StatusPill",
                    f"UID: {mid}",
                )
                # Store face URL for potential avatar display
                self._user_face = face_url
            else:
                self._set_login_status_label("未登录", "MutedLabel")
        except Exception:  # noqa: BLE001
            # Network or API errors — non-critical, just show unknown state
            self._set_login_status_label("登录状态未知", "MutedLabel")

    def _on_batch_clicked(self):
        """Open batch download dialog."""
        dialog = BatchDialog(self._api_client, self)
        if dialog.exec():
            urls = dialog.get_urls()
            if urls:
                self._start_batch_download(urls)

    def _on_check_ffmpeg(self):
        """Check FFmpeg availability."""
        available, msg = FFmpegManager.check_available(self._settings.ffmpeg_path or None)
        if available:
            self._show_info(f"FFmpeg 可用：\n{msg}")
        else:
            self._show_error(f"FFmpeg 不可用：\n{msg}")

    def _on_about_triggered(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "关于",
            "哔哩哔哩视频下载器 v0.2.0\n\n"
            "一款桌面端B站视频下载工具。\n"
            "支持4K、HDR、杜比视界、弹幕和字幕下载。",
        )

    def _show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)

    def _show_info(self, message: str):
        QMessageBox.information(self, "Info", message)

    def closeEvent(self, event: QCloseEvent):
        """Cancel running downloads and close API client on window close."""
        # Cancel all active workers
        self._download_list.cancel_all_workers()

        # Close API client
        self._api_client.close()

        super().closeEvent(event)
