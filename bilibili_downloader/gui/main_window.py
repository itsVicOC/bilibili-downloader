"""Main application window for the Bilibili Downloader."""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
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
    AppSettings,
    DownloadItem,
    VIDEO_CODEC_MAP,
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
from bilibili_downloader.utils.validators import (
    extract_bvid,
    is_bilibili_url,
    is_short_link,
    resolve_short_link,
    SHORT_URL_PATTERN,
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("哔哩哔哩视频下载器")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(load_stylesheet())

        # Components
        self._config = ConfigManager()
        self._settings = self._config.load()
        self._api_client = self._create_api_client()
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(4)

        # State
        self._current_video: VideoInfo | None = None
        self._downloads: list = []
        self._available_qualities: list = []  # Available quality IDs from playurl

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

    def _setup_ui(self):
        """Build the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # -- URL Input Section --
        url_group = QGroupBox("视频链接")
        url_layout = QHBoxLayout(url_group)

        self._url_input = ChineseLineEdit()
        self._url_input.setPlaceholderText(
            "粘贴 B站视频链接 或 BV号（如 BV1GJ411x7h7）"
        )
        url_layout.addWidget(self._url_input)

        self._resolve_btn = QPushButton("解析")
        self._resolve_btn.clicked.connect(self._on_resolve_clicked)
        url_layout.addWidget(self._resolve_btn)

        layout.addWidget(url_group)

        # -- Video Info Section --
        self._video_info = VideoInfoWidget()
        layout.addWidget(self._video_info)

        # -- Quality Selection --
        quality_group = QGroupBox("画质设置")
        quality_layout = QVBoxLayout(quality_group)

        # Video quality
        vq_layout = QHBoxLayout()
        vq_layout.addWidget(QLabel("视频画质："))
        self._quality_combo = QComboBox()
        self._populate_quality_combo()
        vq_layout.addWidget(self._quality_combo)
        vq_layout.addStretch()
        quality_layout.addLayout(vq_layout)

        # Video codec
        vc_layout = QHBoxLayout()
        vc_layout.addWidget(QLabel("视频编码："))
        self._codec_combo = QComboBox()
        self._codec_combo.addItem("HEVC/H.265（推荐）", 12)
        self._codec_combo.addItem("AVC/H.264（兼容性好）", 7)
        self._codec_combo.addItem("AV1（体积最小）", 13)
        vc_layout.addWidget(self._codec_combo)
        vc_layout.addStretch()
        quality_layout.addLayout(vc_layout)

        # Danmaku & Subtitle checkboxes
        options_layout = QHBoxLayout()
        self._danmaku_check = self._create_checkbox("下载弹幕", self._settings.download_danmaku)
        self._subtitle_check = self._create_checkbox("下载字幕", self._settings.download_subtitle)
        options_layout.addWidget(self._danmaku_check)
        options_layout.addWidget(self._subtitle_check)
        options_layout.addStretch()
        quality_layout.addLayout(options_layout)

        layout.addWidget(quality_group)

        # -- Action Buttons --
        btn_layout = QHBoxLayout()

        self._download_btn = QPushButton("下载")
        self._download_btn.clicked.connect(self._on_download_clicked)
        self._download_btn.setStyleSheet(
            "QPushButton { background-color: #00A1D6; color: white; "
            "padding: 8px 24px; font-weight: bold; border-radius: 6px; font-size: 14px; }"
            "QPushButton:hover { background-color: #23a2d9; }"
            "QPushButton:pressed { background-color: #0088b8; }"
        )
        btn_layout.addWidget(self._download_btn)

        self._batch_btn = QPushButton("批量下载")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        btn_layout.addWidget(self._batch_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # -- Download List --
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

        # Login status label on the right side of status bar
        from PySide6.QtWidgets import QLabel
        self._login_status_label = QLabel("未登录")
        self._login_status_label.setStyleSheet(
            "QLabel { color: #888; padding: 0 8px; }"
        )
        self._status_bar.addPermanentWidget(self._login_status_label)

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

        # Handle b23.tv short links
        if is_short_link(url):
            self._status_bar.showMessage("正在解析短链...")
            bvid = resolve_short_link(url)
            if not bvid:
                self._show_error("无法解析b23.tv短链，请粘贴完整链接或BV号")
                self._status_bar.showMessage("短链解析失败")
                return
            self._status_bar.showMessage(f"短链展开：{bvid}")
        else:
            bvid = extract_bvid(url)
            if not bvid:
                self._show_error("无法从链接中提取BV号")
                return

        self._resolve_btn.setEnabled(False)
        self._resolve_btn.setText("解析中...")
        self._status_bar.showMessage(f"正在解析 {bvid}...")

        # Use QThreadPool for async resolve
        self._resolve_worker = ResolveWorker(self._api_client, bvid)
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
                self._login_status_label.setText(f"已登录：{uname}")
                self._login_status_label.setStyleSheet(
                    "QLabel { color: #00A1D6; font-weight: bold; padding: 0 8px; }"
                )
                self._login_status_label.setToolTip(f"UID: {mid}")
                # Store face URL for potential avatar display
                self._user_face = face_url
            else:
                self._login_status_label.setText("未登录")
                self._login_status_label.setStyleSheet(
                    "QLabel { color: #888; padding: 0 8px; }"
                )
                self._login_status_label.setToolTip("")
        except Exception:  # noqa: BLE001
            # Network or API errors — non-critical, just show unknown state
            self._login_status_label.setText("登录状态未知")
            self._login_status_label.setStyleSheet(
                "QLabel { color: #888; padding: 0 8px; }"
            )

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
            "哔哩哔哩视频下载器 v0.1.0\n\n"
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
