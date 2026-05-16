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

from src.core.models import AppSettings, VideoInfo
from src.gui.dialogs.settings_dialog import SettingsDialog
from src.gui.dialogs.login_dialog import LoginDialog
from src.gui.widgets.download_list import DownloadListWidget
from src.gui.widgets.video_info import VideoInfoWidget
from src.utils.config import ConfigManager
from src.utils.validators import extract_bvid, is_bilibili_url, SHORT_URL_PATTERN
from src.gui.widgets.chinese_input import ChineseLineEdit

logger = logging.getLogger(__name__)


# B站主题 QSS 样式表
# 配色: 主色 #00A1D6(哔哩蓝), 辅色 #FB7299(哔哩粉), 深色背景 #212121
DARK_STYLE = """
    QMainWindow, QWidget {
        background-color: #212121;
        color: #e0e0e0;
        font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
        font-size: 13px;
    }

    /* ── GroupBox ── */
    QGroupBox {
        font-weight: bold;
        border: 1px solid #333333;
        border-radius: 8px;
        margin-top: 1.2ex;
        padding-top: 14px;
        background-color: #262626;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: #00A1D6;
        font-size: 13px;
    }

    /* ── Input Fields ── */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        padding: 8px 12px;
        color: #e0e0e0;
        font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
        font-size: 13px;
        selection-background-color: #00A1D6;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid #00A1D6;
        background-color: #2d2d2d;
    }
    QLineEdit:disabled, QTextEdit:disabled {
        background-color: #222222;
        color: #666;
    }

    /* ── ComboBox ── */
    QComboBox {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        padding: 7px 32px 7px 12px;
        color: #e0e0e0;
        min-width: 140px;
        font-size: 13px;
    }
    QComboBox:hover {
        border-color: #00A1D6;
        background-color: #2d2d2d;
    }
    QComboBox:disabled {
        background-color: #222222;
        color: #555;
        border-color: #303030;
    }
    QComboBox::drop-down {
        border: none;
        width: 28px;
        border-left: 1px solid #3a3a3a;
    }
    QComboBox:hover::drop-down {
        border-left-color: #00A1D6;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #999;
        margin-right: 6px;
    }
    QComboBox:pressed::down-arrow {
        border-top-color: #00A1D6;
    }
    QComboBox:on {
        border-color: #00A1D6;
    }
    QComboBox QAbstractItemView {
        background-color: #2a2a2a;
        color: #e0e0e0;
        border: 1px solid #404040;
        border-radius: 6px;
        selection-background-color: #00A1D6;
        selection-color: white;
        outline: none;
        padding: 4px 0;
        font-size: 13px;
    }
    QComboBox QAbstractItemView::item {
        min-height: 32px;
        padding: 0 12px;
        border: none;
    }
    QComboBox QAbstractItemView::item:hover {
        background-color: rgba(0, 161, 214, 0.2);
    }
    QComboBox QAbstractItemView::item:selected {
        background-color: #00A1D6;
        color: white;
    }

    /* ── Table ── */
    QTableWidget {
        background-color: #252525;
        gridline-color: #2e2e2e;
        border: 1px solid #333333;
        border-radius: 6px;
        color: #e0e0e0;
        alternate-background-color: #2a2a2a;
    }
    QTableWidget::item {
        padding: 4px;
    }
    QTableWidget::item:selected {
        background-color: rgba(0, 161, 214, 0.3);
        color: white;
    }
    QHeaderView::section {
        background-color: #2a2a2a;
        color: #00A1D6;
        font-weight: bold;
        border: none;
        border-bottom: 1px solid #333333;
        padding: 8px;
    }

    /* ── Buttons ── */
    QPushButton {
        background-color: #333333;
        border: 1px solid #404040;
        border-radius: 6px;
        padding: 7px 18px;
        color: #e0e0e0;
        font-size: 13px;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #3d3d3d;
        border: 1px solid #00A1D6;
    }
    QPushButton:pressed {
        background-color: #1d1d1d;
        padding-top: 8px;
        padding-bottom: 6px;
    }
    QPushButton:disabled {
        background-color: #262626;
        color: #555;
        border-color: #303030;
    }

    /* Primary / accent buttons */
    QPushButton#PrimaryButton {
        background-color: #00A1D6;
        border: 1px solid #00A1D6;
        color: white;
        font-weight: bold;
    }
    QPushButton#PrimaryButton:hover {
        background-color: #23a2d9;
    }
    QPushButton#PrimaryButton:pressed {
        background-color: #0088b8;
        padding-top: 9px;
        padding-bottom: 7px;
    }
    QPushButton#PrimaryButton:disabled {
        background-color: #1a4a5c;
        border-color: #1a4a5c;
        color: #557788;
    }

    QPushButton#DangerButton {
        background-color: #d32f2f;
        border: 1px solid #d32f2f;
        color: white;
    }
    QPushButton#DangerButton:hover {
        background-color: #e03e3e;
    }

    QPushButton#SuccessButton {
        background-color: #2e7d32;
        border: 1px solid #2e7d32;
        color: white;
    }
    QPushButton#SuccessButton:hover {
        background-color: #3a8f3e;
    }

    /* ── Menu Bar ── */
    QMenuBar {
        background-color: #212121;
        color: #e0e0e0;
        border-bottom: 1px solid #333333;
    }
    QMenuBar::item {
        padding: 6px 10px;
        border-radius: 4px;
        margin: 2px;
    }
    QMenuBar::item:selected {
        background-color: rgba(0, 161, 214, 0.3);
    }
    QMenu {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #404040;
        border-radius: 6px;
        padding: 6px;
    }
    QMenu::item {
        padding: 6px 24px 6px 12px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: rgba(0, 161, 214, 0.3);
    }
    QMenu::separator {
        height: 1px;
        background-color: #404040;
        margin: 4px 8px;
    }

    /* ── Status Bar ── */
    QStatusBar {
        background-color: #212121;
        color: #777;
        border-top: 1px solid #333333;
    }

    /* ── Progress Bar ── */
    QProgressBar {
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        text-align: center;
        color: #e0e0e0;
        background-color: #333333;
        font-size: 11px;
        height: 18px;
    }
    QProgressBar::chunk {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #00A1D6, stop:1 #0088b8);
        border-radius: 5px;
    }

    /* ── CheckBox ── */
    QCheckBox {
        color: #e0e0e0;
        spacing: 6px;
        padding: 2px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 2px solid #404040;
        border-radius: 4px;
        background-color: #2a2a2a;
    }
    QCheckBox::indicator:hover {
        border-color: #00A1D6;
    }
    QCheckBox::indicator:checked {
        background-color: #00A1D6;
        border-color: #00A1D6;
    }

    /* ── Tab Widget ── */
    QTabWidget::pane {
        border: 1px solid #333333;
        border-radius: 6px;
        background-color: #262626;
    }
    QTabBar::tab {
        background-color: #2a2a2a;
        color: #888;
        padding: 8px 24px;
        border: 1px solid #333333;
        border-bottom: none;
        border-radius: 6px 6px 0 0;
    }
    QTabBar::tab:selected {
        background-color: #00A1D6;
        color: white;
    }
    QTabBar::tab:hover:!selected {
        color: #00A1D6;
        background-color: #303030;
    }

    /* ── Label ── */
    QLabel { color: #e0e0e0; }

    /* ── Dialog ── */
    QMessageBox { background-color: #212121; }
    QMessageBox QLabel { color: #e0e0e0; }
    QMessageBox QPushButton { min-width: 80px; }
"""


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("哔哩哔哩视频下载器")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(DARK_STYLE)

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
        from src.api.client import BilibiliAPIClient
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
        from PySide6.QtWidgets import QCheckBox
        cb = QCheckBox(text)
        cb.setChecked(checked)
        return cb

    def _populate_quality_combo(self):
        """Fill quality combo box with all available qualities."""
        from src.core.models import VideoQuality
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
        from src.utils.validators import is_short_link, resolve_short_link
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
        from PySide6.QtCore import QRunnable, Signal
        from PySide6.QtCore import QObject
        from src.core.models import VideoQuality

        class ResolveWorker(QObject):
            finished = Signal(object, list, list, bool)  # info, video_streams, audio_streams, playurl_ok
            error = Signal(str)

            def __init__(self, client, bvid):
                super().__init__()
                self._client = client
                self._bvid = bvid

        class ResolveRunner(QRunnable):
            def __init__(self, worker):
                super().__init__()
                self._worker = worker

            def run(self):
                try:
                    info = self._worker._client.get_video_info(self._worker._bvid)
                    # Try to fetch playurl for quality discovery (degraded on failure)
                    video_streams = []
                    audio_streams = []
                    playurl_ok = False
                    try:
                        playurl_data = self._worker._client.get_play_url(
                            bvid=info.bvid,
                            cid=info.cid,
                            quality=VideoQuality.Q1080P,
                            need_hdr=True,
                            need_dolby=True,
                        )
                        video_streams = playurl_data.get("video_streams", [])
                        audio_streams = playurl_data.get("audio_streams", [])
                        playurl_ok = True
                    except Exception as e:
                        # playurl failure is non-fatal; show video info anyway
                        logger.warning("Playurl fetch failed for %s: %s", info.bvid, e)

                    self._worker.finished.emit(
                        info, video_streams, audio_streams, playurl_ok
                    )
                except Exception as e:
                    self._worker.error.emit(str(e))

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

        from src.core.models import VIDEO_CODEC_MAP, VideoQuality
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

    def _on_retry_download(self, row: int):
        """Retry a failed download."""
        item = self._download_list.get_item(row)
        if item:
            # Reset UI
            self._download_list.mark_failed_retry_reset(row)
            self._start_download(item, row)
            self._status_bar.showMessage(f"重试下载：{item.video_info.title}")

    def _on_download_clicked(self):
        """Start downloading the resolved video."""
        if self._current_video is None:
            self._show_error("请先解析一个视频链接")
            return

        quality = self._quality_combo.currentData()
        codec = self._codec_combo.currentData()

        from src.core.models import DownloadItem
        item = DownloadItem(
            video_info=self._current_video,
            selected_quality=quality,
            selected_video_codec=codec,
            download_danmaku=self._danmaku_check.isChecked(),
            download_subtitle=self._subtitle_check.isChecked(),
        )

        # Add to download list
        row = self._download_list.rowCount()
        self._download_list.add_item(item)
        self._status_bar.showMessage(f"已加入队列：{item.video_info.title}")

        # Start download in background thread
        self._start_download(item, row)

    def _start_download(self, item, row_index: int):
        """Start a download in a background thread via thread pool."""
        from src.gui.threads.download_worker import DownloadRunner, DownloadWorker

        worker = DownloadWorker(
            api_client=self._api_client,
            item=item,
            output_dir=self._settings.output_dir,
            download_danmaku=item.download_danmaku,
            download_subtitle=item.download_subtitle,
            row_index=row_index,
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
        self._download_list.register_worker(row_index, worker)

    def _start_batch_download(self, urls: list[str]):
        """Download multiple videos sequentially."""
        from src.utils.validators import extract_bvid

        for url in urls:
            bvid = extract_bvid(url)
            if not bvid:
                continue

            try:
                info = self._api_client.get_video_info(bvid)
                from src.core.models import DownloadItem
                item = DownloadItem(
                    video_info=info,
                    selected_quality=self._quality_combo.currentData(),
                    selected_video_codec=self._codec_combo.currentData(),
                    download_danmaku=self._danmaku_check.isChecked(),
                    download_subtitle=self._subtitle_check.isChecked(),
                )
                row = self._download_list.rowCount()
                self._download_list.add_item(item)
                self._start_download(item, row)
            except Exception as e:
                self._show_error(f"Failed to queue {bvid}: {e}")

    def _on_download_finished(self, index: int, path: str):
        """Handle download completion."""
        self._download_list.mark_done(index)
        self._status_bar.showMessage(f"下载完成：{path}")

    def _on_download_error(self, index: int, error: str):
        """Handle download error."""
        self._download_list.mark_failed(index, error)
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
        except Exception:
            self._login_status_label.setText("登录状态未知")
            self._login_status_label.setStyleSheet(
                "QLabel { color: #888; padding: 0 8px; }"
            )

    def _on_batch_clicked(self):
        """Open batch download dialog."""
        from src.gui.dialogs.batch_dialog import BatchDialog
        dialog = BatchDialog(self._api_client, self)
        if dialog.exec():
            urls = dialog.get_urls()
            if urls:
                self._start_batch_download(urls)

    def _on_check_ffmpeg(self):
        """Check FFmpeg availability."""
        from src.core.ffmpeg import FFmpegManager
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
        for row, worker in self._download_list._workers.items():
            if worker and worker.is_running:
                worker.cancel()

        # Close API client
        self._api_client.close()

        super().closeEvent(event)
