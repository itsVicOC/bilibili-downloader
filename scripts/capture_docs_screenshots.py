#!/usr/bin/env python3
"""Render deterministic, credential-free screenshots for the documentation."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QCloseEvent, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QPlainTextEdit

from bilibili_downloader.core.live_models import (
    LiveRoom,
    RecordingSegment,
    RecordingSession,
)
from bilibili_downloader.core.models import (
    AppSettings,
    ContentKind,
    DownloadItem,
    OutputMode,
    StreamInfo,
    TaskStatus,
    VideoInfo,
    VideoPage,
    VideoQuality,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.utils.config import ConfigManager

OUTPUT_DIR = PROJECT_ROOT / "docs" / "images"


def _flush_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def _save_widget(app: QApplication, widget, filename: str) -> None:
    widget.ensurePolished()
    widget.show()
    _flush_events(app)
    # Keep the actual temporary files for eligibility checks, but display a
    # stable demonstration path instead of machine-specific temporary roots.
    masked = []
    temp_root = app.property("docsTempRoot")
    for entry in widget.findChildren(QLineEdit) + widget.findChildren(QPlainTextEdit):
        if not temp_root or not entry.isReadOnly():
            continue
        text = entry.text() if isinstance(entry, QLineEdit) else entry.toPlainText()
        if temp_root in text:
            masked.append((entry, text))
            visible = text.replace(temp_root, "~/BiliFlow-demo")
            if isinstance(entry, QLineEdit):
                entry.setText(visible)
                entry.setCursorPosition(0)
            else:
                entry.setPlainText(visible)
    _flush_events(app)
    output = OUTPUT_DIR / filename
    captured = widget.grab()
    flattened = QPixmap(captured.size())
    flattened.fill(QColor("#14131b" if app.property("darkTheme") else "#f7f5fb"))
    painter = QPainter(flattened)
    painter.drawPixmap(0, 0, captured)
    painter.end()
    if not flattened.save(str(output), "PNG"):
        raise RuntimeError(f"无法保存截图：{output}")
    for entry, text in masked:
        if isinstance(entry, QLineEdit):
            entry.setText(text)
            entry.setCursorPosition(0)
        else:
            entry.setPlainText(text)
    widget.hide()


class DemoLiveService:
    """Deterministic offline service; never starts a thread or a network request."""

    def __init__(self, *_args):
        self.rows = []
        self.stopped = True

    def start(self):
        pass

    def snapshot(self):
        return [dict(row) for row in self.rows]

    def messages(self):
        return []

    @property
    def active(self):
        return any(row["active"] for row in self.rows)

    def command(self, *_args, **_kwargs):
        pass

    def request_shutdown(self):
        pass

    def shutdown(self):
        return True


def _make_main_window(workdir: Path) -> MainWindow:
    config = ConfigManager(workdir / "config.json")
    config.save(
        AppSettings(
            output_dir="~/Downloads/BiliFlow",
            path_template="{author}/{collection}/{title}{part_suffix}",
            download_danmaku=True,
            download_subtitle=True,
            download_cover=True,
            download_metadata=True,
            live={"output_dir": "~/Downloads/BiliFlow/live"},
        )
    )
    repository = TaskRepository(workdir / "tasks.sqlite3")
    controller = LiveUiController(config, service_factory=DemoLiveService)
    window = MainWindow(
        config_manager=config, task_repository=repository, live_controller=controller
    )
    controller.timer.stop()
    window.resize(1320, 860)
    return window


def _demo_video() -> VideoInfo:
    return VideoInfo(
        bvid="BV1DEMO2026A",
        cid=20260920,
        title="星轨旅记：城市夜航（文档演示）",
        desc="用于文档截图的离线演示数据。",
        duration=12 * 60 + 34,
        author="示例 UP 主",
        collection_title="城市漫游",
        pages=[
            VideoPage(cid=20260920, page=1, part="夜航篇", duration=754),
            VideoPage(cid=20260921, page=2, part="晨光篇", duration=682),
        ],
    )


def _populate_main_window(window: MainWindow) -> None:
    info = _demo_video()
    video_streams = [
        StreamInfo(id=120, codecid=12),
        StreamInfo(id=80, codecid=12),
        StreamInfo(id=80, codecid=7),
    ]
    audio_streams = [StreamInfo(id=30280), StreamInfo(id=30216)]
    window._url_input.setText("BV1DEMO2026A")
    window._on_resolve_success(info, video_streams, audio_streams, True)
    window._danmaku_check.setChecked(True)
    window._subtitle_check.setChecked(True)
    window._cover_check.setChecked(True)
    window._metadata_check.setChecked(True)
    cover = QPixmap(asset_path("nebula.jpg"))
    window._video_info._cover_label.set_source_pixmap(cover, expand=True)

    tasks = [
        (
            DownloadItem(
                video_info=info,
                selected_quality=VideoQuality.Q4K,
                selected_video_codec=12,
                download_danmaku=True,
                download_subtitle=True,
                download_cover=True,
                download_metadata=True,
            ),
            TaskStatus.DOWNLOADING,
            0.68,
            "14.2 MB/s · 剩余 01:42",
        ),
        (
            DownloadItem(
                video_info=info.model_copy(
                    update={
                        "cid": 20260921,
                        "title": "星轨旅记：晨光抵达（文档演示）",
                    },
                    deep=True,
                ),
                selected_quality=VideoQuality.Q1080P,
                selected_video_codec=7,
            ),
            TaskStatus.PAUSED,
            0.32,
            "已暂停 · 可保留断点继续",
        ),
        (
            DownloadItem(
                video_info=VideoInfo(
                    bvid="BV1DEMO2026B",
                    cid=20260922,
                    title="示例访谈：创作幕后",
                    author="示例 UP 主",
                ),
                selected_audio_quality=30251,
                output_mode=OutputMode.AUDIO,
            ),
            TaskStatus.COMPLETED,
            1.0,
            "完成 · Hi-Res FLAC",
        ),
    ]
    for task_id, (item, status, progress, status_text) in enumerate(tasks, start=1):
        window._download_list.add_item(
            item,
            download_id=task_id,
            status=status,
            progress=progress,
            status_text=status_text,
        )
    window._status_bar.showMessage("文档演示数据 · 未连接网络")


def _make_batch_dialog() -> BatchDialog:
    episode = VideoInfo(
        cid=910001,
        title="第 01 话 出发",
        author="示例出品方",
        content_kind=ContentKind.BANGUMI_EPISODE,
        episode_id=900001,
        series_title="示例番剧",
        season_title="第一季",
        section_title="正片",
        episode_number="01",
        is_main_section=True,
    )
    pv = episode.model_copy(
        update={
            "cid": 910002,
            "title": "先导预告",
            "episode_id": 900002,
            "section_title": "PV",
            "episode_number": "PV1",
            "is_main_section": False,
        },
        deep=True,
    )
    video = _demo_video()
    dialog = BatchDialog(existing_content_identities={video.content_identity})
    dialog.resize(900, 680)
    dialog._url_text.setPlainText(
        "https://www.bilibili.com/bangumi/play/ss123456\n"
        "https://space.bilibili.com/123456/lists/654321?type=season\n"
        "BV1DEMO2026A"
    )
    dialog._on_resolved([episode, pv, video], [])
    return dialog


def _populate_live_page(window: MainWindow, workdir: Path) -> None:
    page = window._live_page
    page.service.shutdown()
    page.service.rows = [
        {
            "room_id": 100001,
            "author": "城市漫游（演示）",
            "title": "夜间散步 · 离线界面演示",
            "enabled": True,
            "active": True,
            "state": "recording",
            "state_label": "录制中",
            "detail": "原画 · AVC/AAC · FLV",
            "duration": 2592,
            "size": 2480000000,
            "speed": 1300000,
            "qualities": [],
            "quality": 0,
            "output_dir": str(workdir),
            "segment_seconds": 1800,
        },
        {
            "room_id": 100002,
            "author": "星轨电台（演示）",
            "title": "音乐与日常",
            "enabled": True,
            "active": False,
            "state": "waiting",
            "state_label": "等待开播",
            "detail": "等待下一场直播",
            "duration": 0,
            "size": 0,
            "speed": 0,
            "qualities": [],
            "quality": 0,
            "output_dir": str(workdir),
            "segment_seconds": 1800,
        },
    ]
    session = RecordingSession(
        id="demo-recording",
        room=LiveRoom(room_id=100001, author="城市漫游（演示）"),
        directory=str(workdir),
        started_at="2026-09-27T12:00:00+00:00",
        status="completed",
        ended_at="2026-09-27T13:00:00+00:00",
        quality_label="原画",
        format="flv",
        segments=[
            RecordingSegment(
                path=str(workdir / "attempt_0001/part_000.flv"),
                duration=1800,
                size=1700000000,
                finalized_at="2026-09-27T12:30:00+00:00",
            )
        ],
    )
    page.repository.save_session(session)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "attempt_0001").mkdir(exist_ok=True)
    (workdir / "attempt_0001/part_000.flv").touch()
    page.refresh()
    page.rooms.selectRow(0)
    window._task_page.history.expandAll()
    window._show_workspace(1)


def _capture_states(app, theme, window, temp_root):
    """Render real UI components with deterministic edge states, without workers."""
    theme.apply_theme(True)
    window.resize(900, 640)
    empty = _make_main_window(temp_root / "empty")
    empty.resize(900, 640)
    for name, index in (("download-empty", 0), ("live-empty", 1), ("tasks-empty", 2)):
        empty._show_workspace(index)
        _save_widget(app, empty, f"biliflow-state-{name}.png")
    empty._live_controller.shutdown()

    window._show_workspace(0)
    window._download_tabs.setCurrentIndex(0)
    window._resolve_btn.setText("解析中…")
    window._resolve_btn.setEnabled(False)
    window._download_btn.setEnabled(False)
    window._resolve_notice.set_message("正在读取作品与可用规格…")
    window._video_info._state_label.setText("解析中")
    window._video_info._state_label.set_tone("active")
    _save_widget(app, window, "biliflow-state-parsing.png")
    window._on_resolve_error("离线示例：接口暂时不可用，请稍后重新解析。")
    _save_widget(app, window, "biliflow-state-parse-error.png")
    info = _demo_video()
    window._on_resolve_success(
        info, [StreamInfo(id=80, codecid=7)], [StreamInfo(id=30280)], True
    )
    window.show()
    _flush_events(app)
    scroll = window._workspace_scroll.verticalScrollBar()
    scroll.setValue(scroll.maximum())
    _save_widget(app, window, "biliflow-state-download-specs-small.png")
    scroll.setValue(0)
    window._output_mode_combo.setCurrentIndex(
        window._output_mode_combo.findData(OutputMode.AUDIO)
    )
    window.resize(1320, 860)
    theme.apply_theme(False)
    _save_widget(app, window, "biliflow-state-audio.png")
    theme.apply_theme(True)
    window.resize(900, 640)
    batch = window._batch_page
    window._download_tabs.setCurrentIndex(1)
    batch._on_resolved(
        batch._resolved_items,
        ["BV1DEMOFAIL：离线示例，来源已删除或当前账号无权访问。"],
    )
    _save_widget(app, window, "biliflow-state-batch-partial.png")
    batch._url_text.appendPlainText("BV1NEWDEMO")
    _save_widget(app, window, "biliflow-state-batch-stale.png")

    window._show_workspace(1)
    service = window._live_controller.service
    for state, label, active, detail in (
        ("waiting", "等待开播", False, "自动监控已开启，等待下一场直播。"),
        ("queued", "等待录制", False, "其他直播间正在录制，等待可用录制槽位。"),
        ("preparing", "准备中", True, "正在获取当前账号可用的直播流。"),
        ("reconnecting", "重连中", True, "连接中断，5 秒后重新获取直播流。"),
        ("finalizing", "收尾中", True, "正在封口最后一个片段，请等待完成。"),
        ("error", "需要处理", False, "保存目录剩余空间不足，请释放空间后手动恢复。"),
    ):
        service.rows[0].update(
            state=state, state_label=label, active=active, detail=detail
        )
        window._live_controller.refresh()
        _save_widget(app, window, f"biliflow-state-live-{state}.png")
    window.show()
    _flush_events(app)
    scroll = window._live_page._scroll.verticalScrollBar()
    scroll.setValue(scroll.maximum())
    _save_widget(app, window, "biliflow-state-live-details-small.png")
    scroll.setValue(0)
    dialog = window._live_page._build_room_settings_dialog(service.rows[1])
    dialog.directory.setText("~/BiliFlow-demo/live")
    dialog.directory.setCursorPosition(0)
    dialog.resize(640, 380)
    _save_widget(app, dialog, "biliflow-room-settings.png")
    window._show_tasks(2)
    session = window._live_controller.sessions[0].model_copy(deep=True)
    session.status = "interrupted"
    session.warnings = ["离线示例：连接中断后已恢复，源片段均已封口。"]
    session.gaps = [{"start": "20:30:00", "end": "20:30:05", "reason": "连接中断"}]
    window._task_page.update_history([session])
    tree = window._task_page.history
    tree.expandAll()
    tree.setCurrentItem(tree.topLevelItem(0).child(0))
    _save_widget(app, window, "biliflow-state-history-warning.png")
    window._live_controller.exporting = True
    window._task_page._export_changed(True, "")
    _save_widget(app, window, "biliflow-state-exporting.png")
    window._live_controller.exporting = False
    exported = temp_root / "demo-export.mp4"
    exported.touch()
    window._live_controller.export_path = str(exported)
    window._live_controller.notify("MP4 导出完成（离线演示）", "success")
    window._task_page._export_changed(False, str(exported))
    _save_widget(app, window, "biliflow-state-export-done.png")
    window._show_settings_tab(0)
    window._settings_page._path_template.setText("../{title}")
    window._settings_page.validate()
    _save_widget(app, window, "biliflow-state-settings-invalid.png")
    window._settings_page.load_settings(window._settings)
    for tab, name in ((0, "download"), (1, "live"), (2, "tools")):
        window._show_settings_tab(tab)
        window.show()
        _flush_events(app)
        scroll = window._settings_page.tabs.currentWidget().verticalScrollBar()
        scroll.setValue(scroll.maximum())
        _save_widget(app, window, f"biliflow-state-settings-{name}-small.png")
        scroll.setValue(0)


def _capture_dialogs(app, window, suffix=""):
    """Capture the application's real confirmation builders, then cancel them."""
    import bilibili_downloader.gui.main_window as main_module

    name = ""

    def capture(box):
        _save_widget(app, box, f"biliflow-dialog-{name}{suffix}.png")
        return QMessageBox.Cancel

    with patch.object(QMessageBox, "exec", capture):
        name = "copyright"
        window._confirm_copyright_acknowledgement()
        name = "about"
        window._on_about_triggered()
        name = "error"
        window._show_error("离线示例：保存目录暂时不可用，请检查目录权限并重试。")
        name = "settings-leave"
        window._settings_page._max_concurrent.setValue(4)
        window._can_leave_settings()
        window._settings_page.load_settings(window._settings)
        name = "cache"
        with patch.object(
            main_module,
            "inspect_download_cache",
            return_value=SimpleNamespace(file_count=3, size_bytes=24 * 1024**2),
        ):
            window._on_clear_cache()
        name = "quit"
        window._live_controller.service.rows[0].update(state="recording", active=True)
        window._live_controller.refresh()
        window.closeEvent(QCloseEvent())


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("BiliFlow Docs")
    app.setWindowIcon(QIcon(asset_path("app_icon.png")))
    theme = ThemeManager(app)

    with tempfile.TemporaryDirectory(prefix="biliflow-docs-") as temp_dir:
        temp_root = Path(temp_dir)
        app.setProperty("docsTempRoot", str(temp_root))

        window = _make_main_window(temp_root / "workspace")
        _populate_main_window(window)
        _populate_live_page(window, temp_root / "workspace" / "demo-recording")
        preview = _make_batch_dialog()
        window._batch_page._url_text.setPlainText(preview._url_text.toPlainText())
        window._batch_page._on_resolved(preview._resolved_items, [])
        preview.deleteLater()
        pages = {
            "download": lambda: (
                window._show_workspace(0),
                window._download_tabs.setCurrentIndex(0),
            ),
            "batch": lambda: (
                window._show_workspace(0),
                window._download_tabs.setCurrentIndex(1),
            ),
            "live": lambda: window._show_workspace(1),
            "tasks": lambda: (
                window._show_tasks(0),
                window._download_list.selectRow(0),
            ),
            "recording": lambda: (
                window._show_tasks(1),
                window._task_page.current.selectRow(0),
            ),
            "history": lambda: (
                window._show_tasks(2),
                window._task_page.history.setCurrentItem(
                    window._task_page.history.topLevelItem(0).child(0)
                ),
            ),
            "settings": lambda: window._show_settings_tab(0),
            "live-settings": lambda: window._show_settings_tab(1),
            "tools": lambda: window._show_settings_tab(2),
        }
        for dark in (True, False):
            theme.apply_theme(dark)
            for width, height in ((900, 640), (1120, 760), (1320, 860)):
                window.resize(width, height)
                for name, navigate in pages.items():
                    navigate()
                    _save_widget(
                        app,
                        window,
                        f"biliflow-{name}-{'dark' if dark else 'light'}-{width}.png",
                    )
        window.resize(1320, 860)
        theme.apply_theme(True)
        for name in ("live", "tasks", "batch", "settings"):
            pages[name]()
            _save_widget(app, window, f"biliflow-{name}.png")
        pages["download"]()
        _save_widget(app, window, "biliflow-dark.png")
        theme.apply_theme(False)
        _save_widget(app, window, "biliflow-light.png")
        theme.apply_theme(True)
        login_dialog = LoginDialog(None)
        login_dialog.resize(560, 660)
        _save_widget(app, login_dialog, "biliflow-login.png")
        login_dialog._tabs.setCurrentIndex(1)
        _save_widget(app, login_dialog, "biliflow-login-qr.png")
        login_dialog._generate_btn.hide()
        login_dialog._on_qr_status_result({"status": 86038})
        _save_widget(app, login_dialog, "biliflow-state-login-expired.png")
        _capture_states(app, theme, window, temp_root)
        _capture_dialogs(app, window)
        theme.apply_theme(False)
        _capture_dialogs(app, window, "-light")
        window._live_controller.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
