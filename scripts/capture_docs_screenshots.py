#!/usr/bin/env python3
"""Render deterministic, credential-free screenshots for the documentation."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

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
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
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
    output = OUTPUT_DIR / filename
    captured = widget.grab()
    flattened = QPixmap(captured.size())
    flattened.fill(QColor("#15151a" if app.property("darkTheme") else "#ffffff"))
    painter = QPainter(flattened)
    painter.drawPixmap(0, 0, captured)
    painter.end()
    if not flattened.save(str(output), "PNG"):
        raise RuntimeError(f"无法保存截图：{output}")
    widget.hide()


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
        )
    )
    repository = TaskRepository(workdir / "tasks.sqlite3")
    window = MainWindow(config_manager=config, task_repository=repository)
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
    window._on_resolve_success(info, video_streams, audio_streams, True)
    window._url_input.setText("BV1DEMO2026A")
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


def _make_settings_dialog() -> SettingsDialog:
    dialog = SettingsDialog(
        AppSettings(
            output_dir="~/Downloads/BiliFlow",
            default_quality=VideoQuality.Q4K,
            default_video_codec=12,
            default_audio_quality=30280,
            path_template="{author}/{collection}/{title}{part_suffix}",
            bangumi_path_template=(
                "{series}/{season}/{section}/{episode_number} - {episode}"
            ),
            download_danmaku=True,
            download_subtitle=True,
            download_cover=True,
            download_metadata=True,
            max_concurrent_downloads=3,
        )
    )
    dialog.resize(720, 860)
    return dialog


def _populate_live_page(window: MainWindow, workdir: Path) -> None:
    page = window._live_page
    page.service.shutdown()
    page.service._snapshots = [
        {"room_id": 100001, "author": "城市漫游（演示）", "title": "夜间散步 · 离线界面演示",
         "enabled": True, "active": False, "state": "recording", "state_label": "录制中",
         "detail": "原画 · AVC/AAC · FLV", "duration": 2592, "size": 2480000000,
         "speed": 1300000, "qualities": [], "quality": 0,
         "output_dir": str(workdir), "segment_seconds": 1800},
        {"room_id": 100002, "author": "星轨电台（演示）", "title": "音乐与日常",
         "enabled": True, "active": False, "state": "waiting", "state_label": "等待开播",
         "detail": "等待下一场直播", "duration": 0, "size": 0, "speed": 0,
         "qualities": [], "quality": 0, "output_dir": str(workdir), "segment_seconds": 1800},
    ]
    session = RecordingSession(id="demo-recording", room=LiveRoom(room_id=100001, author="城市漫游（演示）"),
        directory=str(workdir), started_at="2026-09-27T12:00:00+00:00", status="completed",
        ended_at="2026-09-27T13:00:00+00:00", quality_label="原画", format="flv",
        segments=[RecordingSegment(path=str(workdir / "attempt_0001/part_000.flv"),
            duration=1800, size=1700000000, finalized_at="2026-09-27T12:30:00+00:00")])
    page.repository.save_session(session)
    page.refresh()
    page.history.expandAll()
    window._show_workspace(1)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("BiliFlow Docs")
    app.setWindowIcon(QIcon(asset_path("app_icon.png")))
    theme = ThemeManager(app)

    with tempfile.TemporaryDirectory(prefix="biliflow-docs-") as temp_dir:
        temp_root = Path(temp_dir)

        empty_window = _make_main_window(temp_root / "empty")
        theme.apply_theme(True)
        _save_widget(app, empty_window, "biliflow-dark.png")
        theme.apply_theme(False)
        _save_widget(app, empty_window, "biliflow-light.png")

        theme.apply_theme(True)
        tasks_window = _make_main_window(temp_root / "tasks")
        _populate_main_window(tasks_window)
        _save_widget(app, tasks_window, "biliflow-tasks.png")

        live_window = _make_main_window(temp_root / "live")
        _populate_live_page(live_window, temp_root / "live" / "demo-recording")
        _save_widget(app, live_window, "biliflow-live.png")

        batch_dialog = _make_batch_dialog()
        _save_widget(app, batch_dialog, "biliflow-batch.png")

        settings_dialog = _make_settings_dialog()
        _save_widget(app, settings_dialog, "biliflow-settings.png")

        login_dialog = LoginDialog(None)
        login_dialog.resize(560, 660)
        _save_widget(app, login_dialog, "biliflow-login.png")

        for window in (empty_window, tasks_window, live_window):
            window._live_page.service.shutdown()
            window._live_page._lock_file.unlock()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
