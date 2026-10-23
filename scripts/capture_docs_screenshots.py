#!/usr/bin/env python3
"""Render deterministic, credential-free screenshots for the documentation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QRect, QSize, Qt, qVersion
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFontInfo,
    QFontMetricsF,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
)

from bilibili_downloader.core.appearance import prepare_background
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
from bilibili_downloader.core.updater import UpdateRelease
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.close_dialog import CloseWindowDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.update_dialog import UpdateDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.styles import theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.settings_sections import SettingsSection
from bilibili_downloader.gui.widgets.components import ElidedLabel
from bilibili_downloader.gui.widgets.pixel_mascot import PixelMascot
from bilibili_downloader.utils.config import ConfigManager

OUTPUT_DIR = PROJECT_ROOT / "docs" / "images"
DEMO_RELEASE_NOTES = """## Fluent 界面精修

- **统一材质与交互**：保留粉紫／青蓝品牌，让内容更清晰。
- 修复 Windows 窗口按钮的色差、悬停与图标对齐。
- 更新说明支持标题、列表、表格与 `行内代码`。

### 兼容与验证

| 项目 | 说明 |
| --- | --- |
| 用户数据 | 保留账号、任务、录制历史和外观设置 |
| 窗口行为 | 保留拖动、缩放和关闭流程 |

> 此处为离线演示数据，不会执行更新。

[查看发布说明](https://github.com/itsVicOC/bilibili-downloader/releases/tag/v0.8.9b1)
"""


def _flush_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def _save_widget(app: QApplication, widget, filename: str, popup=None) -> None:
    widget.ensurePolished()
    widget.show()
    _flush_events(app)
    if not filename.startswith(("biliflow-mascot-", "xiaoliu-")):
        for mascot in widget.findChildren(PixelMascot):
            mascot._freeze_preview(datetime(2026, 10, 21, 10))
    # Keep the actual temporary files for eligibility checks, but display a
    # stable demonstration path instead of machine-specific temporary roots.
    masked = []
    temp_root = app.property("docsTempRoot")
    masked_labels = []
    for entry in widget.findChildren(ElidedLabel):
        if temp_root and temp_root in entry._full_text:
            masked_labels.append((entry, entry._full_text))
            entry.set_full_text(entry._full_text.replace(temp_root, "~/BiliFlow-demo"))
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
    if isinstance(widget, LoginDialog) and widget._login_active and widget._tabs.currentIndex() == 1:
        if not widget._qr_label.visibleRegion().boundingRect().contains(widget._qr_label.rect()):
            raise AssertionError(f"二维码内容被裁切：{filename}")
    if filename.startswith("ui-") and "-options-" in filename:
        cards = (widget._danmaku_check, widget._subtitle_check, widget._cover_check, widget._metadata_check)
        if not all(card.visibleRegion().boundingRect().contains(card.rect()) for card in cards):
            raise AssertionError(f"下载附加项内容被裁切：{filename}")
    captured = widget.grab()
    capture_origin = widget.mapToGlobal(QPoint())
    # QWidget.grab is physical pixels on Retina; popup positions are logical.
    # Export at one pixel per logical pixel so native/offscreen images compare.
    bounds = QRect(QPoint(), captured.deviceIndependentSize().toSize())
    popup_rect = None
    if popup is not None:
        popup_rect = QRect(
            popup.mapToGlobal(QPoint()) - capture_origin, popup.size()
        )
        bounds = bounds.united(popup_rect)
    flattened = QPixmap(bounds.size())
    flattened.fill(app.palette().color(QPalette.Window))
    painter = QPainter(flattened)
    painter.drawPixmap(-bounds.topLeft(), captured)
    if popup_rect is not None:
        painter.drawPixmap(popup_rect.topLeft() - bounds.topLeft(), popup.grab())
    painter.end()
    result = captured if app.property("capturePhysicalPixels") and popup is None else flattened
    if not result.save(str(output), "PNG"):
        raise RuntimeError(f"无法保存截图：{output}")
    for entry, text in masked:
        if isinstance(entry, QLineEdit):
            entry.setText(text)
            entry.setCursorPosition(0)
        else:
            entry.setPlainText(text)
    for entry, text in masked_labels:
        entry.set_full_text(text)
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


def _make_main_window(workdir: Path, *, desktop_platform=None) -> MainWindow:
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
        config_manager=config, task_repository=repository, live_controller=controller,
        desktop_platform=desktop_platform, remember_window=False,
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
            "qualities": [
                {"qn": 10000, "label": "原画"},
                {"qn": 400, "label": "蓝光"},
                {"qn": 250, "label": "超清"},
                {"qn": 150, "label": "高清"},
                {"qn": 80, "label": "流畅"},
            ],
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


def _capture_dropdowns(app, theme, window):
    """Include the actual top-level popup, which QWidget.grab alone excludes."""
    for dark in (True, False):
        theme.apply_theme(dark)
        for width, height in ((900, 640), (1120, 760), (1320, 860)):
            window.resize(width, height)
            controls = (
                (
                    "download",
                    lambda: (
                        window._show_workspace(0),
                        window._download_tabs.setCurrentIndex(0),
                    ),
                    window._quality_combo,
                    window._workspace_scroll,
                ),
                (
                    "live",
                    lambda: window._show_workspace(1),
                    window._live_page.quality,
                    window._live_page._scroll,
                ),
                (
                    "tasks",
                    lambda: window._show_tasks(0),
                    window._task_page.filter,
                    None,
                ),
                (
                    "settings",
                    lambda: window._show_settings_tab(SettingsSection.DOWNLOAD),
                    window._settings_page._quality_combo,
                    window._settings_page.tabs.widget(window._settings_page._sections[SettingsSection.DOWNLOAD]),
                ),
            )
            for name, navigate, combo, scroll in controls:
                navigate()
                window.show()
                _flush_events(app)
                if scroll:
                    scroll.ensureWidgetVisible(combo, 0, 16)
                    _flush_events(app)
                combo.showPopup()
                _flush_events(app)
                _save_widget(
                    app,
                    window,
                    f"biliflow-dropdown-{name}-{'dark' if dark else 'light'}-{width}.png",
                    popup=combo.view().window(),
                )
                combo.hidePopup()
                if scroll:
                    scroll.verticalScrollBar().setValue(0)
            window._show_tasks(0)
            window.show()
            _flush_events(app)
            button = next(
                button
                for button in window._task_page.findChildren(QPushButton)
                if button.menu()
            )
            menu = button.menu()
            button.showMenu()
            menu.setActiveAction(menu.actions()[0])
            _flush_events(app)
            _save_widget(
                app,
                window,
                f"biliflow-dropdown-more-{'dark' if dark else 'light'}-{width}.png",
                popup=menu,
            )
            menu.hide()


def _capture_platform_checks(app, theme, window):
    """Match the unparsed download form and long list seen on a real desktop."""
    checks = []
    combo = window._quality_combo
    combo.setCurrentIndex(combo.findData(VideoQuality.Q1080P60))
    for dark in (True, False):
        theme.apply_theme(dark)
        for width, height in ((900, 640), (1120, 760), (1320, 860)):
            window.resize(width, height)
            window.show()
            _flush_events(app)
            _save_widget(
                app,
                window,
                f"biliflow-platform-download-{'dark' if dark else 'light'}-{width}.png",
            )
            window.show()
            _flush_events(app)
            window._workspace_scroll.ensureWidgetVisible(combo, 0, 16)
            _flush_events(app)
            combo.showPopup()
            _flush_events(app)
            popup = combo.view().window()
            field = QRect(combo.mapToGlobal(QPoint()), combo.size())
            title = window.findChild(QLabel, "PageTitle")
            body_font, title_font = QFontInfo(combo.font()), QFontInfo(title.font())
            checks.append(
                {
                    "theme": "dark" if dark else "light",
                    "window": [width, height],
                    "body_font": {
                        "family": body_font.family(), "pixels": body_font.pixelSize(),
                        "line_height": QFontMetricsF(window._url_input.font(), window._url_input).height(),
                    },
                    "title_font": {
                        "family": title_font.family(), "pixels": title_font.pixelSize()
                    },
                    "field": field.getRect(),
                    "popup": popup.geometry().getRect(),
                    "inside_screen": combo.screen().availableGeometry().contains(
                        popup.geometry()
                    ),
                    "overlaps_field": field.intersects(popup.geometry()),
                }
            )
            _save_widget(
                app,
                window,
                f"biliflow-platform-dropdown-{'dark' if dark else 'light'}-{width}.png",
                popup=popup,
            )
            combo.hidePopup()
            window._workspace_scroll.verticalScrollBar().setValue(0)
    screen = app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(
        json.dumps(
            {
                "platform": sys.platform,
                "qt": qVersion(),
                "backend": app.platformName(),
                "logical_dpi": screen.logicalDotsPerInchY(),
                "device_pixel_ratio": screen.devicePixelRatio(),
                "scale_factor": os.environ.get("QT_SCALE_FACTOR", "system"),
                "available_screen": screen.availableGeometry().getRect(),
                "checks": checks,
            },
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )


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
    window._show_settings_tab(SettingsSection.DOWNLOAD)
    window._settings_page._path_template.setText("../{title}")
    window._settings_page.validate()
    _save_widget(app, window, "biliflow-state-settings-invalid.png")
    window._settings_page.load_settings(window._settings)
    for tab, name in ((SettingsSection.DOWNLOAD, "download"), (SettingsSection.LIVE, "live"), (SettingsSection.TOOLS, "tools")):
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
        window._on_about_triggered()
        _save_widget(app, window, f"biliflow-about-updates{suffix}.png")
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


def _capture_appearance(app, theme, window, temp_root):
    """Exercise real managed images with generated, credential-free demo art."""
    from bilibili_downloader.core.models import BackgroundVisibility
    # Restore a coherent demo after error/quit states captured earlier.
    window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.VIDEO))
    window._video_info._cover_label.set_source_pixmap(QPixmap(asset_path("nebula.jpg")), expand=True)
    if window._live_controller.service.rows:
        window._live_controller.service.rows[0].update(
            state="recording", state_label="录制中", active=True, detail="原画 · AVC/AAC · FLV"
        )
        window._live_controller.notify("")
        window._live_controller.refresh()
    avatar = QImage(96, 96, QImage.Format_RGB32)
    avatar.fill(QColor("#b9e9f6"))
    painter = QPainter(avatar)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#324b69"))
    painter.setBrush(QColor("#324b69"))
    painter.drawEllipse(20, 18, 56, 64)
    painter.setBrush(QColor("#ffe1ce"))
    painter.drawEllipse(28, 32, 40, 42)
    painter.setBrush(QColor("#4f8db8"))
    painter.drawEllipse(18, 74, 60, 54)
    painter.drawEllipse(39, 48, 2, 3)
    painter.drawEllipse(55, 48, 2, 3)
    painter.drawArc(40, 53, 16, 10, 180 * 16, 180 * 16)
    painter.end()
    avatar_path = temp_root / "demo-avatar.png"
    avatar.save(str(avatar_path))
    window._on_login_status_result(window._login_status_request_id, {
        "isLogin": True, "uname": "星海漫游", "mid": "演示账号",
        "face": "demo://avatar",
    })
    window._on_login_status_avatar(window._login_status_request_id, avatar_path.read_bytes())
    for workspace, colors in zip(
        ("download", "live", "tasks", "settings"),
        (("#378ec1", "#9be0c9"), ("#617bc4", "#b5c9ed"),
         ("#579c9b", "#cce7bd"), ("#a4a7ce", "#e6cfdd")),
    ):
        path = temp_root / f"{workspace}-background.png"
        image = QImage(1600, 1000, QImage.Format_RGB32)
        painter = QPainter(image)
        gradient = QLinearGradient(0, 0, 1600, 1000)
        gradient.setColorAt(0, QColor(colors[0]))
        gradient.setColorAt(1, QColor(colors[1]))
        painter.fillRect(image.rect(), gradient)
        painter.setPen(QColor(255, 255, 255, 55))
        for x in range(-800, 1800, 110):
            painter.drawLine(x, 1000, x + 950, 0)
        painter.setBrush(QColor(255, 255, 255, 60))
        painter.drawEllipse(1050, -150, 600, 600)
        painter.drawEllipse(800, 650, 800, 700)
        painter.end()
        image.save(str(path))
        prepared = prepare_background(path)
        window._background_store.install(prepared)
        setattr(window._settings.appearance.backgrounds, workspace, prepared.reference)
        setattr(window._settings.appearance.background_visibility, workspace, BackgroundVisibility(light=80, dark=65))

    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        window._settings_page.load_settings(window._settings)
        theme.set_color_theme(theme_id)
        for dark in (True, False):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for width, height in ((900, 640), (1120, 760), (1320, 860)):
                window.resize(width, height)
                for index, name in enumerate(("download", "live", "tasks", "settings")):
                    window._show_workspace(index)
                    if index == 0:
                        window._download_tabs.setCurrentIndex(0)
                    if index == 3:
                        window._settings_page.show_section(SettingsSection.APPEARANCE)
                    _save_widget(app, window, f"biliflow-appearance-{theme_id}-{name}-{mode}-{width}.png")
                    if index == 3 and width == 1320:
                        panel = window._settings_page
                        focused = panel._theme_buttons.button(1 - panel._theme_combo.currentIndex())
                        window.show()
                        window.activateWindow()
                        app.setActiveWindow(window)
                        _flush_events(app)
                        focused.setFocus(Qt.TabFocusReason)
                        _flush_events(app)
                        assert focused.hasFocus() and focused.property("keyboardFocus")
                        _save_widget(app, window, f"biliflow-appearance-{theme_id}-theme-focus-{mode}.png")
                        focused.clearFocus()
                if width == 900:
                    scroll = window._settings_page.tabs.currentWidget()
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    _save_widget(app, window, f"biliflow-appearance-{theme_id}-backgrounds-{mode}-{width}.png")
                    scroll.verticalScrollBar().setValue(0)
            window._show_settings_tab(SettingsSection.DOWNLOAD)
            combo = window._settings_page._quality_combo
            combo.showPopup()
            _save_widget(app, window, f"biliflow-appearance-{theme_id}-dropdown-{mode}.png", popup=combo.view().window())
            combo.hidePopup()
            dialog = LoginDialog(None)
            _save_widget(app, dialog, f"biliflow-appearance-{theme_id}-login-{mode}.png")
            dialog.deleteLater()

    # Show the default blue theme independently of the optional demo wallpaper.
    for workspace in ("download", "live", "tasks", "settings"):
        setattr(window._settings.appearance.backgrounds, workspace, "")
    window._settings_page.load_settings(window._settings)
    for dark in (True, False):
        theme.apply_theme(dark)
        mode = "dark" if dark else "light"
        window.resize(1120, 760)
        window._show_workspace(0)
        window._download_tabs.setCurrentIndex(0)
        _save_widget(app, window, f"biliflow-appearance-bilibili_blue-default-download-{mode}-1120.png")
        window.resize(900, 640)
        window._show_settings_tab(SettingsSection.APPEARANCE)
        _save_widget(app, window, f"biliflow-appearance-bilibili_blue-default-settings-{mode}-900.png")


def _capture_ux_states(app, theme, temp_root):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog

    from bilibili_downloader.gui.threads.batch_worker import (
        ImportIssue,
        ImportReport,
    )
    from bilibili_downloader.gui.widgets.appearance_preview import WorkspacePreview

    window = _make_main_window(temp_root / "ux-review")
    window.resize(900, 640)
    for dark in (True, False):
        theme.apply_theme(dark)
        mode = "dark" if dark else "light"
        window._show_workspace(0)
        window._download_tabs.setCurrentIndex(0)
        _save_widget(app, window, f"biliflow-ux-empty-{mode}.png")
        window._url_input.setText("https://space.bilibili.com/123/favlist?fid=456")
        window._resolve_btn.click()
        _save_widget(app, window, f"biliflow-ux-source-route-{mode}.png")
        window._url_input.clear()
        window._resolve_notice.set_message("")
        window._resolve_notice.action.hide()
        window._download_tabs.setCurrentIndex(1)
        batch = window._batch_page
        batch._url_text.setPlainText("https://space.bilibili.com/123/favlist?fid=456")
        with patch("bilibili_downloader.gui.dialogs.batch_dialog.QThreadPool.globalInstance", return_value=SimpleNamespace(start=lambda _: None)):
            batch._begin_resolve([batch._url_text.toPlainText()])
        batch._on_progress({
            "source": batch._url_text.toPlainText(), "source_index": 1, "sources": 1,
            "stage": "解析作品", "completed": 42, "total": 158, "items": 38,
        })
        _save_widget(app, window, f"biliflow-ux-batch-progress-{mode}.png")
        batch._on_report(ImportReport([], [ImportIssue(batch._url_text.toPlainText(), "离线演示：来源暂时不可用，请稍后重试", batch._url_text.toPlainText())]))
        _save_widget(app, window, f"biliflow-ux-batch-all-failed-{mode}.png")
        batch._on_report(ImportReport(
            [VideoInfo(bvid="BV1DEMO2026A", title="演示作品：收藏片段", author="示例 UP 主")],
            [ImportIssue(batch._url_text.toPlainText(), "作品已失效或当前账号无法访问", "https://www.bilibili.com/video/BV1DEMOFAIL1", "演示失效作品", "item")],
            cancelled=True,
        ))
        _save_widget(app, window, f"biliflow-ux-batch-cancelled-{mode}.png")
        with patch.object(QDialog, "exec", lambda dialog: (_save_widget(app, dialog, f"biliflow-ux-failure-details-{mode}.png"), QDialog.Rejected)[1]):
            batch._show_errors()
        dialog = LoginDialog("demo-session", account={"uname": "星海漫游（演示）", "mid": "演示 UID", "vipStatus": 0}, account_valid=True, avatar_icon=QIcon(asset_path("alien.png")))
        _save_widget(app, dialog, f"biliflow-ux-account-{mode}.png")
        dialog.deleteLater()
        window._show_settings_tab(SettingsSection.APPEARANCE)
        picker = window._settings_page._background_pickers["download"]
        prepared = prepare_background(Path(asset_path("nebula.jpg")))
        window._background_store.install(prepared)
        picker.set_reference(prepared.reference)
        def preview_capture(dialog):
            preview = dialog.findChild(WorkspacePreview)
            preview.is_dark = dark
            for _ in range(100):
                if not dialog.busy:
                    break
                QTest.qWait(10)
            (dialog.effects.dark_button if dark else dialog.effects.light_button).setChecked(True)
            dialog.findChild(QSlider).setValue(45 if dark else 60)
            _save_widget(app, dialog, f"biliflow-ux-background-preview-{mode}.png")
            return QDialog.Rejected
        with patch.object(QDialog, "exec", preview_capture):
            picker._show_preview()
        window._settings_page.load_settings(window._settings)
    window._live_controller.shutdown()


def _capture_batch_polish(app, theme, temp_root):
    from bilibili_downloader.core.models import BackgroundVisibility
    from bilibili_downloader.gui.threads.batch_worker import ImportIssue, ImportReport

    window = _make_main_window(temp_root / "batch-review")
    window._show_workspace(0)
    window._download_tabs.setCurrentIndex(1)
    panel = window._batch_page
    source = "https://space.bilibili.com/123/favlist?fid=456"
    panel._url_text.setPlainText(source)
    titles = (
        "童年动画音乐精选 · 重温那些熟悉的旋律",
        "城市夜航：沿着灯光与人群慢慢前行",
        "周末散步计划｜山野、公园与一小段旅程",
        "创作手记：从一张草图到完整的故事",
        "收藏的现场：夏日特别演出",
        "桌面与生活：把喜欢的东西留在身边",
    )
    report = ImportReport(
        [VideoInfo(
            bvid=f"BV1DEMO{i:05d}", title=f"{titles[i % len(titles)]} {i + 1:02d}",
            author=("星海漫游", "城市观察员", "音乐收藏室")[i % 3],
            collection_title="日常灵感收藏夹",
        ) for i in range(130)],
        [ImportIssue(source, "视频已失效或暂时不可用", source, f"演示失效作品 {i + 1}", "item") for i in range(28)],
    )
    panel._on_report(report)
    background = prepare_background(Path(asset_path("nebula.jpg")))
    window._background_store.install(background)
    window._settings.appearance.background_visibility.download = BackgroundVisibility(light=60, dark=45)
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for custom in (False, True):
                window._settings.appearance.backgrounds.download = background.reference if custom else ""
                window._refresh_workspace_background()
                for width, height in ((900, 640), (1120, 760), (1320, 860)):
                    window.resize(width, height)
                    panel._collapse_btn.setChecked(True)
                    kind = "background" if custom else "default"
                    _save_widget(app, window, f"biliflow-batch-refined-{theme_id}-{kind}-{mode}-{width}.png")
            if theme_id == "star_trail" and not dark:
                window.resize(1320, 860)
                panel._collapse_btn.setChecked(False)
                _save_widget(app, window, "biliflow-batch-refined-edit.png")
                panel._collapse_btn.setChecked(True)
    window._live_controller.shutdown()


def _capture_output_actions(app, theme, temp_root):
    from bilibili_downloader.core.models import BackgroundVisibility
    from bilibili_downloader.gui.threads.batch_worker import ImportReport

    window = _make_main_window(temp_root / "output-review")
    _populate_main_window(window)
    info = window._current_video.model_copy(deep=True)
    background = prepare_background(Path(asset_path("nebula.jpg")))
    window._background_store.install(background)
    window._settings.appearance.backgrounds.download = background.reference
    window._settings.appearance.background_visibility.download = BackgroundVisibility(light=60, dark=45)
    source = "https://space.bilibili.com/123/favlist?fid=456"
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for width, height in ((900, 640), (1120, 760), (1320, 860)):
                window.resize(width, height)
                window._show_workspace(0)
                window._download_tabs.setCurrentIndex(0)
                window._resolved_url = ""
                window._url_input.clear()
                window._current_video = None
                window._download_btn.setEnabled(False)
                window._refresh_download_summary()
                window._resolve_notice.set_message("")
                window._content_section.hide()
                window._empty_download.show()
                _save_widget(app, window, f"biliflow-output-{theme_id}-single-empty-{mode}-{width}.png")
                window._url_input.setText(info.bvid)
                window._on_resolve_success(info.model_copy(deep=True), [], [], False)
                window._video_info._cover_label.set_source_pixmap(QPixmap(asset_path("nebula.jpg")), expand=True)
                window._workspace_scroll.verticalScrollBar().setValue(0)
                _save_widget(app, window, f"biliflow-output-{theme_id}-single-ready-{mode}-{width}.png")
                if theme_id == "bilibili_blue" and not dark and width == 1320:
                    window._download_actions.grab().save(str(OUTPUT_DIR / "biliflow-output-single-bar-light.png"))
                window._download_tabs.setCurrentIndex(1)
                batch = window._batch_page
                batch._request_source = None
                batch._url_text.clear()
                batch._on_report(ImportReport())
                batch._resolved_source = None
                batch._resolve_btn.setText("解析并预览")
                _save_widget(app, window, f"biliflow-output-{theme_id}-batch-empty-{mode}-{width}.png")
                batch._url_text.setPlainText(source)
                batch._on_report(ImportReport([
                    info.model_copy(update={"collection_title": "日常灵感收藏夹"}, deep=True),
                    info.model_copy(update={"bvid": "BV1DEMO2026B", "title": "星轨旅记：晨光抵达（文档演示）", "collection_title": "日常灵感收藏夹"}, deep=True),
                ]))
                _save_widget(app, window, f"biliflow-output-{theme_id}-batch-ready-{mode}-{width}.png")
                if theme_id == "bilibili_blue" and not dark and width == 1320:
                    batch._action_bar.grab().save(str(OUTPUT_DIR / "biliflow-output-batch-bar-light.png"))
    window._live_controller.shutdown()


def _capture_lifecycle(app, theme, temp_root):
    screen = app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "backend": app.platformName(),
        "host_platform": sys.platform,
        "scale_factor": os.environ.get("QT_SCALE_FACTOR", "1"),
        "device_pixel_ratio": screen.devicePixelRatio(),
        "logical_dpi": screen.logicalDotsPerInch(),
        "qt_version": qVersion(),
        "note": "Images normalized to logical pixels; Windows behavior is simulated on macOS. Native Windows tray is not verified by these captures.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for platform in ("win32", "darwin"):
        window = _make_main_window(temp_root / f"lifecycle-{platform}", desktop_platform=platform)
        window._show_settings_tab(SettingsSection.APPEARANCE)
        for theme_id in ("star_trail", "bilibili_blue"):
            theme.set_color_theme(theme_id)
            for dark in (False, True):
                theme.apply_theme(dark)
                mode = "dark" if dark else "light"
                for width in (900, 1320):
                    window.resize(width, 640 if width == 900 else 860)
                    _save_widget(app, window, f"biliflow-background-{platform}-{theme_id}-{mode}-{width}.png")
                if platform == "win32":
                    for state, active, available in (("idle", False, True), ("active", True, True), ("unavailable", True, False)):
                        dialog = CloseWindowDialog(window, active=active, tray_available=available)
                        _save_widget(app, dialog, f"biliflow-close-{state}-{theme_id}-{mode}.png")
                        for button in (dialog.cancel_button, dialog.quit_button, dialog.tray_button):
                            assert dialog.rect().contains(QRect(button.mapTo(dialog, QPoint()), button.size()))
                            assert button.width() >= button.sizeHint().width()
                        dialog.hide()
                        dialog.deleteLater()
        window._live_controller.shutdown()
        window.request_quit(confirmed=True)
        _flush_events(app)
        window.deleteLater()


def _capture_refinement(app, theme, window):
    """Exercise the reorganized layout with content that a normal demo omits."""
    _populate_main_window(window)
    info = window._current_video.model_copy(deep=True)
    directory = window._settings.output_dir
    checks = []
    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for width, height in ((900, 640), (1120, 760), (1320, 860)):
                window.resize(width, height)
                for state in ("audio", "long-content", "failed", "settings-draft", "task-filter"):
                    window._settings.output_dir = directory
                    window._output_summary.setText(directory)
                    window._on_resolve_success(info, info.video_streams, info.audio_streams, True)
                    window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.VIDEO))
                    window._show_workspace(0)
                    window._workspace_scroll.verticalScrollBar().setValue(0)
                    if state == "audio":
                        window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.AUDIO))
                        assert not window._quality_combo.isEnabled()
                    elif state == "long-content":
                        long_info = info.model_copy(update={
                            "title": "星轨旅记🌠：穿过漫长的夜色与城市街巷，记录沿途的每一束光。" * 8,
                            "author": "一个非常长的离线演示 UP 主昵称" * 5,
                        })
                        window._video_info.set_video_info(long_info)
                        long_path = "~/Downloads/" + "长目录与 Unicode 演示/" * 12 + "BiliFlow"
                        window._settings.output_dir = long_path
                        window._output_summary.setText(long_path)
                        window._refresh_download_summary()
                    elif state == "failed":
                        window._on_resolve_error("网络连接暂时不可用，请检查连接后重新解析。")
                        assert not window._download_btn.isEnabled()
                    elif state == "settings-draft":
                        panel = window._settings_page
                        panel._path_template.setText("待保存/{author}/{title}{part_suffix}")
                        window._show_settings_tab(SettingsSection.DOWNLOAD)
                    else:
                        page = window._task_page
                        page.filter.setCurrentIndex(page.filter.findData("paused"))
                        window._show_tasks(0)
                    window._url_input.deselect()
                    _save_widget(app, window, f"refine-{theme_id}-{state}-{mode}-{width}.png")
                    checks.append({"theme": theme_id, "mode": mode, "state": state,
                                   "requested_size": [width, height],
                                   "actual_size": [window.width(), window.height()],
                                   "horizontal_scroll": window._workspace_scroll.horizontalScrollBar().maximum()})
                    window._settings_page.load_settings(window._settings_page._settings)
                    window._task_page.filter.setCurrentIndex(0)
    (OUTPUT_DIR / "refinement-checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")


def _capture_builtin_backgrounds(app, theme, window, temp_root):
    from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
    from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery

    _populate_main_window(window)
    _populate_live_page(window, temp_root / "background-demo")
    window._settings.appearance.theme = "bilibili_blue"
    theme.set_color_theme("bilibili_blue")
    for entry in BUILTIN_BACKGROUNDS:
        setattr(window._settings.appearance.backgrounds, entry.workspace, entry.reference)
        theme.apply_theme(entry.style == "pixel")
        mode = "dark" if entry.style == "pixel" else "light"
        window.resize(1320, 860)
        window._show_workspace(("download", "live", "tasks", "settings").index(entry.workspace))
        if entry.workspace == "settings":
            window._settings_page.show_section(SettingsSection.APPEARANCE)
        window.show()
        _flush_events(app)
        assert window._workspace_pages.property("mascotBackground")
        _save_widget(app, window, f"biliflow-background-{entry.id}-{mode}.png")

    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            for size in ((900, 640), (1120, 760), (1320, 860)):
                window.resize(*size)
                window.show()
                for page in range(4):
                    window._show_workspace(page)
                    _flush_events(app)
                    assert window.size().width() == size[0] and window.size().height() == size[1]
                    assert window._workspace_pages.property("mascotBackground")
    theme.set_color_theme("bilibili_blue")
    theme.apply_theme(False)
    picker = window._settings_page._background_pickers["download"]
    for size in ((1080, 720), (980, 660), (720, 540)):
        dialog = BackgroundGallery(picker)
        dialog.resize(*size)
        dialog.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
        dialog.page_filter.setCurrentIndex(0)
        dialog.show()
        _flush_events(app)
        from PySide6.QtTest import QTest
        for _ in range(100):
            if not dialog.busy:
                break
            QTest.qWait(10)
        assert not dialog.busy
        assert dialog.scroll.horizontalScrollBar().maximum() == 0
        assert dialog.rect().contains(QRect(dialog.apply_button.mapTo(dialog, QPoint()), dialog.apply_button.size()))
        _save_widget(app, dialog, f"biliflow-background-gallery-{size[0]}.png")
        if size[0] < 900:
            dialog._set_compact_view("preview")
            _save_widget(app, dialog, f"biliflow-background-gallery-preview-{size[0]}.png")
        if size[0] == 1080:
            dialog.effects.original_button.click()
            _save_widget(app, dialog, "biliflow-background-gallery-original.png")
            dialog.effects.page_button.click()
            dialog.tabs.setCurrentIndex(1)
            _save_widget(app, dialog, "biliflow-background-gallery-custom.png")
        dialog.deleteLater()
    screen = app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "platform": app.platformName(), "qt_version": qVersion(),
        "logical_dpi": screen.logicalDotsPerInch(), "dpr": screen.devicePixelRatio(),
        "note": "Offline services and isolated configuration; twelve wallpapers plus both themes, modes and three window sizes checked.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _capture_mascot(app, theme, window):
    """Exercise full, short and narrow sidebars without production services."""
    _populate_main_window(window)
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for width, height in ((900, 640), (1120, 640), (1120, 760), (1320, 860)):
                window.resize(width, height)
                window.show()
                _flush_events(app)
                card = window._mascot_card
                card.mascot._freeze_preview(datetime(2026, 10, 21, 10))
                for control in (*window._nav_buttons, window._settings_nav, window._header_login):
                    assert window._sidebar.rect().contains(QRect(control.mapTo(window._sidebar, QPoint()), control.size()))
                assert card.isVisible() == (width >= 1120)
                if width >= 1120:
                    assert card._mini == (height == 640)
                    for child in (card.mascot, card.caption):
                        assert card.rect().contains(QRect(child.mapTo(card, QPoint()), child.size()))
                _save_widget(app, window, f"biliflow-mascot-{theme_id}-{mode}-{width}x{height}.png")
                if width == 1120:
                    _save_widget(app, card, f"xiaoliu-card-{theme_id}-{mode}-{'mini' if card._mini else 'full'}.png")
            for hour, key, action in ((6, "morning", "stretch"), (10, "day", "cheer"),
                                      (14, "afternoon", "sip"), (20, "evening", "stargaze"),
                                      (1, "night", "doze")):
                for height in (640, 760):
                    window.resize(1120, height)
                    window.show()
                    window._mascot_card.show()
                    _flush_events(app)
                    card = window._mascot_card
                    assert card._mini == (height == 640)
                    card.mascot._freeze_preview(datetime(2026, 10, 21, hour), action, 3)
                    _save_widget(app, card, f"xiaoliu-{key}-{theme_id}-{mode}-{'mini' if card._mini else 'full'}.png")
    screen = app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "platform": app.platformName(), "qt_version": qVersion(),
        "logical_dpi": screen.logicalDotsPerInch(), "dpr": screen.devicePixelRatio(),
        "note": "Offline demonstration data; screenshots normalized to logical pixels.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _refresh_document_previews(group):
    """Refresh the stable filenames linked by guides from the captured matrix."""
    aliases = {
        "appearance-controls": {
            "settings-light": "controls-star_trail-settings-light-1320",
            "live-settings-light": "controls-star_trail-live-settings-light-1320",
            "blur-light": "controls-star_trail-glass-light-900",
            "blur-clear": "controls-star_trail-blur-0-light",
            "blur-soft": "controls-star_trail-blur-40-light",
            "gallery-light": "controls-star_trail-gallery-light",
            "gallery-small": "controls-star_trail-gallery-small-light",
        },
        "glass": {
            "download-empty-light": "glass-star_trail-builtin-empty-light-1320",
            "download-resolved-light": "glass-star_trail-builtin-resolved-light-1320",
            "live-light": "glass-star_trail-builtin-live-light-1320",
            "custom-dark": "glass-star_trail-custom-resolved-dark-1120",
            "download-empty-small": "glass-star_trail-builtin-empty-light-900",
        },
        "ui-refresh": {
            "download-light": "ui-star_trail-download-light-1320",
            "live-light-1120": "ui-star_trail-live-light-1120",
            "live-dark-900": "ui-star_trail-live-dark-900",
            "tasks-light": "ui-star_trail-tasks-light-1120",
            "options-dark": "ui-star_trail-options-dark-900",
            "appearance-light": "ui-star_trail-settings-appearance-light-1320",
            "about-light": "ui-star_trail-settings-about-light-900",
            "account-light": "ui-star_trail-account-valid-light",
            "account-unknown-light": "ui-star_trail-account-unknown-light",
            "account-long-name-dark": "ui-star_trail-account-long-name-dark",
            "native-options-light": "ui-star_trail-options-light-900",
            "native-account-light": "ui-star_trail-account-valid-light",
            "native-switch-light": "ui-star_trail-switch-qr-light",
            "naming-light": "ui-star_trail-naming-light-900",
            "tools-light": "ui-star_trail-settings-tools-light-1120",
        },
    }
    for name, source in aliases[group].items():
        image = QImage(str(OUTPUT_DIR / f"{source}.png"))
        if image.isNull():
            raise RuntimeError(f"Missing screenshot source: {source}")
        target = OUTPUT_DIR / f"{name}.png"
        previous = QImage(str(target))
        if not previous.isNull() and previous.size() != image.size():
            # Keep the established logical/physical pixel sizes of linked images.
            if abs(previous.width() / previous.height() - image.width() / image.height()) > 0.01:
                raise RuntimeError(f"Unexpected screenshot aspect ratio: {name}")
            image = image.scaled(previous.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if not image.save(str(target)):
            raise RuntimeError(f"Cannot save documentation preview: {target}")


def _capture_ui_refresh(app, theme, window):
    """Seven UI improvements, using isolated fixtures and native-resolution evidence."""
    import qrcode

    _populate_main_window(window)
    _populate_live_page(window, Path(app.property("docsTempRoot")) / "ui-live")
    batch = _make_batch_dialog()
    window._batch_page._url_text.setPlainText(batch._url_text.toPlainText())
    window._batch_page._on_resolved(batch._resolved_items, [])
    batch.deleteLater()
    checks = []
    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for width, height in ((900, 640), (1120, 760), (1320, 860)):
                window.resize(width, height)
                window._show_workspace(0)
                window._workspace_scroll.verticalScrollBar().setValue(0)
                window.show()
                _flush_events(app)
                # Native frame margins settle on first exposure. Set the final
                # client viewport after that, then verify the actual result.
                window.resize(width, height)
                _flush_events(app)
                # Qt 6.11 Windows may report its initial expanded-frame
                # increment in the client size. Record that small difference;
                # a desktop-clamped 1024px sample must still fail this matrix.
                native_frame_increment = app.platformName() == "windows" and (
                    0 <= window.width() - width <= 8 and 0 <= window.height() - height <= 36
                )
                if window.size() != QSize(width, height) and not native_frame_increment:
                    raise AssertionError(f"Desktop clamped requested UI size {width}x{height} to {window.width()}x{window.height()}")
                _save_widget(app, window, f"ui-{theme_id}-download-{mode}-{width}.png")
                window._workspace_scroll.ensureWidgetVisible(window._metadata_check, 0, 12)
                _save_widget(app, window, f"ui-{theme_id}-options-{mode}-{width}.png")
                cards = (window._danmaku_check, window._subtitle_check, window._cover_check, window._metadata_check)
                assert all(card.height() >= card.fontMetrics().height() + 16 for card in cards)
                for section in SettingsSection:
                    window._show_settings_tab(section)
                    _save_widget(app, window, f"ui-{theme_id}-settings-{section.value}-{mode}-{width}.png")
                    if section == SettingsSection.DOWNLOAD:
                        window._settings_page._templates_section.set_expanded(True)
                        window.show()
                        _flush_events(app)
                        window._settings_page.tabs.currentWidget().ensureWidgetVisible(window._settings_page._templates_section)
                        _save_widget(app, window, f"ui-{theme_id}-naming-{mode}-{width}.png")
                        window._settings_page._templates_section.set_expanded(False)
                for index, name in ((1, "live"), (2, "tasks")):
                    window._show_workspace(index)
                    _save_widget(app, window, f"ui-{theme_id}-{name}-{mode}-{width}.png")
                for index, name in ((1, "recording"), (2, "history")):
                    window._show_tasks(index)
                    _save_widget(app, window, f"ui-{theme_id}-{name}-{mode}-{width}.png")
                window._show_workspace(0)
                window._download_tabs.setCurrentIndex(1)
                _save_widget(app, window, f"ui-{theme_id}-batch-{mode}-{width}.png")
                window._download_tabs.setCurrentIndex(0)
                checks.append({
                    "theme": theme_id, "mode": mode, "size": [width, height],
                    "actual_size": [window.width(), window.height()],
                    "menu_visible": not window.menuBar().isHidden(),
                    "font": window._url_input.font().family(),
                    "resolved_font": QFontInfo(window._url_input.font()).family(),
                    "font_pixels": QFontInfo(window._url_input.font()).pixelSize(),
                    "font_height": window._url_input.fontMetrics().height(),
                    "sidebar_width": window._sidebar.width(),
                    "option_card_heights": [card.height() for card in cards],
                })
            for state in ("valid", "checking", "unknown", "expired"):
                dialog = LoginDialog("demo-session", account={
                    "uname": "星海漫游（离线演示）", "mid": "演示 UID", "vipStatus": 1,
                }, account_valid=True, account_state=state,
                    avatar_icon=QIcon(asset_path("app_icon.png")))
                _save_widget(app, dialog, f"ui-{theme_id}-account-{state}-{mode}.png")
                if state == "valid":
                    dialog._show_login_methods()
                    _save_widget(app, dialog, f"ui-{theme_id}-switch-{mode}.png")
                    dialog._generate_btn.hide()
                    dialog._on_qr_generated("offline", "demo", qrcode.make("BiliFlow offline layout demo"))
                    dialog._poll_timer.stop()
                    dialog._qr_status.setText("离线演示二维码，仅用于布局验收")
                    _save_widget(app, dialog, f"ui-{theme_id}-switch-qr-{mode}.png")
                    dialog._tabs.setCurrentIndex(0)
                    _save_widget(app, dialog, f"ui-{theme_id}-switch-cookie-{mode}.png")
                dialog.deleteLater()
            update = UpdateDialog(UpdateRelease(
                "0.9.0", "v0.9.0", "2026-10-21T00:00:00Z", DEMO_RELEASE_NOTES, (),
            ), window)
            _save_widget(app, update, f"ui-{theme_id}-update-{mode}.png")
            update.deleteLater()
            for sample, account in (
                ("long-name", {"uname": "星海漫游的超长昵称" * 12, "mid": "123456789"}),
                ("missing-avatar", {"uname": "星海漫游", "mid": "123456789"}),
            ):
                dialog = LoginDialog("demo-session", account=account, account_valid=True)
                _save_widget(app, dialog, f"ui-{theme_id}-account-{sample}-{mode}.png")
                dialog.deleteLater()
    screen = app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "platform": sys.platform, "backend": app.platformName(), "qt": qVersion(),
        "logical_dpi": screen.logicalDotsPerInchY(), "dpr": screen.devicePixelRatio(),
        "scale_factor": os.environ.get("QT_SCALE_FACTOR", "system"),
        "physical_pixels": bool(app.property("capturePhysicalPixels")), "checks": checks,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _refresh_document_previews("ui-refresh")


def _capture_interactions(app, theme, window):
    """Actual row feedback, history menus and injected clipboard offers, offline."""
    from PySide6.QtCore import QMimeData, QObject, Signal
    from PySide6.QtTest import QTest

    from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
    from bilibili_downloader.gui.clipboard_controller import ClipboardController

    class DemoClipboard(QObject):
        dataChanged = Signal()

        def __init__(self):
            super().__init__()
            self.mime = QMimeData()

        def set(self, value):
            self.mime.setText(value)
            self.dataChanged.emit()

        def mimeData(self):
            return self.mime

    _populate_main_window(window)
    root = Path(app.property("docsTempRoot"))
    _populate_live_page(window, root / "interaction-live")
    clipboard = DemoClipboard()
    controller = ClipboardController(window, clipboard=clipboard, foreground=lambda: True)
    source = root / "interaction-contrast.png"
    image = QImage(480, 320, QImage.Format_RGB32)
    for y in range(320):
        for x in range(480):
            image.setPixelColor(x, y, QColor("#ffffff" if (x // 12 + y // 12) % 2 else "#080825"))
    image.save(str(source))
    custom = prepare_background(source)
    window._background_store.install(custom)
    checks = []

    def capture(filename, popup=None):
        _save_widget(app, window, filename, popup=popup)
        window.show()
        window.raise_()
        window.activateWindow()
        _flush_events(app)

    def hover(view, index):
        view.clearSelection()
        _flush_events(app)
        rect = view.visualRect(index)
        QTest.mouseMove(view.viewport(), QPoint(30, rect.center().y()))
        QTest.qWait(60)
        _flush_events(app)
        if not view._row_hover.matches(index):
            raise AssertionError(f"Row hover did not follow actual mouse input: visible={view.isVisible()}, rect={rect}")

    try:
        for theme_id in ("star_trail", "bilibili_blue"):
            theme.set_color_theme(theme_id)
            window._settings.appearance.theme = theme_id
            for dark in (False, True):
                theme.apply_theme(dark)
                mode = "dark" if dark else "light"
                for width, height in ((900, 640), (1120, 760), (1320, 860)):
                    clipboard.set("")
                    controller.check()
                    window.resize(width, height)
                    window.show()
                    _flush_events(app)
                    for tab, name, view in ((0, "downloads", window._download_list),
                                            (1, "recording", window._task_page.current),
                                            (2, "history", window._task_page.history)):
                        window._show_tasks(tab)
                        view.clearSelection()
                        QTest.mouseMove(window, QPoint(12, 80))
                        capture(f"interaction-{theme_id}-{name}-default-{mode}-{width}.png")
                        index = view.model().index(0, 0)
                        hover(view, index)
                        capture(f"interaction-{theme_id}-{name}-hover-{mode}-{width}.png")
                        view.setCurrentIndex(index)
                        capture(f"interaction-{theme_id}-{name}-selected-hover-{mode}-{width}.png")
                    history = window._task_page.history
                    history.expandAll()
                    child = history.topLevelItem(0).child(0)
                    hover(history, history.indexFromItem(child))
                    capture(f"interaction-{theme_id}-history-child-hover-{mode}-{width}.png")
                    history.setCurrentItem(child)
                    menu = window._task_page.history_menu
                    owner = window._task_page.history_more
                    menu.popup(owner.mapToGlobal(QPoint(0, -menu.sizeHint().height())))
                    capture(f"interaction-{theme_id}-history-menu-{mode}-{width}.png", popup=menu)
                    menu.hide()
                    window._show_workspace(0)
                    window._download_tabs.setCurrentIndex(0)
                    _flush_events(app)
                    before = window._workspace_scroll.geometry()
                    focus = QApplication.focusWidget()
                    clipboard.set("【分享】BV1GJ411x7h7")
                    controller.check()
                    assert QApplication.focusWidget() is focus
                    capture(f"interaction-{theme_id}-clipboard-{mode}-{width}.png")
                    assert window._workspace_scroll.geometry() == before
                    assert controller.prompt.geometry().right() < window._workspace_pages.width() - 14
                    window._resolve_btn.setEnabled(False)
                    controller.refresh_prompt()
                    capture(f"interaction-{theme_id}-clipboard-busy-{mode}-{width}.png")
                    window._resolve_btn.setEnabled(True)
                    clipboard.set("ep123\nss456")
                    controller.check()
                    capture(f"interaction-{theme_id}-clipboard-batch-{mode}-{width}.png")
                    clipboard.set("")
                    controller.check()
                    checks.append({"theme": theme_id, "dark": dark, "size": [width, height], "hover": True, "clipboard_layout_stable": True})
                window._show_tasks(2)
                assert window._live_controller.remove_history("demo-recording")
                capture(f"interaction-{theme_id}-history-removed-{mode}.png")
                assert window._live_controller.undo_remove_history()
                capture(f"interaction-{theme_id}-history-restored-{mode}.png")
                for kind, reference in (("builtin", BUILTIN_BACKGROUNDS[0].reference), ("contrast", custom.reference)):
                    window.resize(1120, 760)
                    window._settings.appearance.backgrounds.tasks = reference
                    window._settings.appearance.backgrounds.download = reference
                    window._show_tasks(0)
                    hover(window._download_list, window._download_list.model().index(0, 0))
                    capture(f"interaction-{theme_id}-hover-{kind}-{mode}.png")
                    window._show_workspace(0)
                    clipboard.set("av170001")
                    controller.check()
                    capture(f"interaction-{theme_id}-clipboard-{kind}-{mode}.png")
                    clipboard.set("")
                    controller.check()
                window._settings.appearance.backgrounds.tasks = ""
                window._settings.appearance.backgrounds.download = ""
        (OUTPUT_DIR / "interaction-checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        controller.dispose()


def _capture_native_chrome(app, theme, window):
    """Capture the desktop compositor, including the native frame boundaries.

    QWidget.grab() alone cannot catch a reappearing system titlebar or frame.
    Use only offline fixtures, and record the actual desktop/backend/DPI.
    """
    from PySide6.QtTest import QTest

    if app.platformName() not in ("windows", "cocoa"):
        raise RuntimeError("Chrome checks require a native desktop backend")
    checks = []
    window.resize(900, 640)
    window.move(window.screen().availableGeometry().topLeft() + QPoint(24, 40))
    for dark in (False, True):
        # Exercise the user-facing mode transition too: Qt's Windows caption
        # layer follows styleHints().colorScheme(), not just the widget palette.
        theme.set_mode("dark" if dark else "light")
        mode = "dark" if dark else "light"
        for name, transition in (
            ("windowed", window.showNormal),
            ("maximized", window.showMaximized),
            ("restored", window.showNormal),
        ):
            transition()
            window.raise_()
            window.activateWindow()
            QTest.qWait(250)
            window._chrome._sync_native()
            _flush_events(app)
            if name != "maximized":
                window.resize(900, 640)
                QTest.qWait(100)
            handle = window.windowHandle()
            frame = window.frameGeometry()
            screen = window.screen()
            pixmap = screen.grabWindow(0, *frame.getRect())
            if pixmap.isNull():
                raise AssertionError("Native frame capture is unavailable")
            filename = f"chrome-{mode}-{name}.png"
            pixmap.save(str(OUTPUT_DIR / filename))
            if sys.platform == "win32":
                assert handle.flags() & Qt.FramelessWindowHint
                assert not handle.flags() & Qt.ExpandedClientAreaHint
                assert not handle.icon().isNull()
                # The sidebar starts its brand below y=24. This previously
                # empty strip contained the duplicate 16px caption icon.
                origin = window.mapToGlobal(QPoint(12, 6)) - frame.topLeft()
                dpr = pixmap.devicePixelRatio()
                image = pixmap.toImage()
                expected = theme_palette(dark, theme.theme_id).sidebar
                sample = QColor(expected)
                colors = [
                    image.pixelColor(round((origin.x() + x) * dpr), round((origin.y() + y) * dpr))
                    for x in range(48) for y in range(12)
                ]
                matching = sum(
                    max(abs(color.red() - sample.red()), abs(color.green() - sample.green()),
                        abs(color.blue() - sample.blue())) <= 3 for color in colors
                )
                assert matching / len(colors) >= 0.98, "Duplicate native caption is visible over the sidebar"
                buttons = window.mapToGlobal(QPoint(window.width() - 144, 6)) - frame.topLeft()
                glyph_pixels = sum(
                    (image.pixelColor(round((buttons.x() + x) * dpr), round((buttons.y() + y) * dpr)).lightness() > 200)
                    if dark else
                    (image.pixelColor(round((buttons.x() + x) * dpr), round((buttons.y() + y) * dpr)).lightness() < 70)
                    for x in range(136) for y in range(20)
                )
                assert glyph_pixels >= 8, "Caption buttons do not contrast with the selected appearance mode"
            checks.append({
                "mode": mode, "state": name, "image": filename,
                "frame": frame.getRect(), "client": window.geometry().getRect(),
                "qwidget_flags": int(window.windowFlags()), "qwindow_flags": int(handle.flags()),
                "title": handle.title(), "icon_present": not handle.icon().isNull(),
            })
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "platform": sys.platform, "backend": app.platformName(), "qt": qVersion(),
        "logical_dpi": screen.logicalDotsPerInchY(), "dpr": screen.devicePixelRatio(),
        "capture": "desktop compositor with client-painted Fluent caption controls",
        "enum_inverted_title_hint": int(~Qt.WindowTitleHint), "checks": checks,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def _capture_glass(app, theme, window):
    from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS

    prepared = prepare_background(Path(asset_path("nebula.jpg")))
    window._background_store.install(prepared)
    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for source, reference in (("builtin", BUILTIN_BACKGROUNDS[0].reference), ("custom", prepared.reference)):
                window._settings.appearance.backgrounds.download = reference
                window._settings.appearance.backgrounds.live = reference
                for width, height in ((900, 640), (1120, 760), (1320, 860)):
                    window.resize(width, height)
                    window._show_workspace(0)
                    window._current_video = None
                    window._resolved_url = ""
                    window._download_result_state = "待解析"
                    window._download_btn.setEnabled(False)
                    window._content_section.hide()
                    window._empty_download.show()
                    window._url_input.clear()
                    window._resolve_notice.set_message("")
                    window._refresh_download_summary()
                    window._workspace_scroll.verticalScrollBar().setValue(0)
                    window.show()
                    _flush_events(app)
                    hero = window._hero
                    for control in (window._hero_title, window._url_input, window._resolve_btn, window._empty_download):
                        assert hero.rect().contains(QRect(control.mapTo(hero, QPoint()), control.size()))
                    _save_widget(app, window, f"glass-{theme_id}-{source}-empty-{mode}-{width}.png")
                    _populate_main_window(window)
                    _save_widget(app, window, f"glass-{theme_id}-{source}-resolved-{mode}-{width}.png")
                    window._show_workspace(1)
                    _save_widget(app, window, f"glass-{theme_id}-{source}-live-{mode}-{width}.png")
    screen = app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "backend": app.platformName(), "qt": qVersion(), "dpr": screen.devicePixelRatio(),
        "physical_pixels": bool(app.property("capturePhysicalPixels")),
        "material": "Qt wallpaper glass: cached blur, refraction rim and highlights; native text remains separate",
        "matrix": "2 palettes x 2 modes x 2 wallpaper sources x 3 sizes x 3 states",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _refresh_document_previews("glass")



def _capture_appearance_controls(app, theme, window):
    from PySide6.QtTest import QTest

    from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
    from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery

    window._on_login_status_result(window._login_status_request_id, {"isLogin":True,"uname":"星海漫游","mid":123})
    window._header_login.set_avatar(Path(asset_path("app_icon.png")).read_bytes())
    panel = window._settings_page
    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for width, height in ((900,640), (1120,760), (1320,860)):
                window.resize(width,height)
                window._show_settings_tab(SettingsSection.DOWNLOAD)
                _save_widget(app,window,f"controls-{theme_id}-settings-{mode}-{width}.png")
                window._show_settings_tab(SettingsSection.LIVE)
                _save_widget(app,window,f"controls-{theme_id}-live-settings-{mode}-{width}.png")
                window._show_settings_tab(SettingsSection.APPEARANCE)
                window.show()
                _flush_events(app)
                panel.tabs.currentWidget().ensureWidgetVisible(panel._glass_card, 0, 8)
                _save_widget(app,window,f"controls-{theme_id}-glass-{mode}-{width}.png")
            for value in (0,40):
                panel._glass_blur.setValue(value)
                _save_widget(app,window,f"controls-{theme_id}-blur-{value}-{mode}.png")
            panel.load_settings(window._settings)
            gallery = BackgroundGallery(panel._background_pickers["download"])
            gallery.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
            for _ in range(100):
                if not gallery.busy:
                    break
                QTest.qWait(10)
            _save_widget(app,gallery,f"controls-{theme_id}-gallery-{mode}.png")
            gallery.resize(720,520)
            gallery._set_compact_view("preview")
            _save_widget(app,gallery,f"controls-{theme_id}-gallery-small-{mode}.png")
            gallery.deleteLater()
    screen=app.primaryScreen()
    (OUTPUT_DIR / "rendering-profile.json").write_text(json.dumps({
        "backend":app.platformName(),"qt":qVersion(),"dpr":screen.devicePixelRatio(),
        "physical_pixels":bool(app.property("capturePhysicalPixels")),
        "sections":[section.value for section in SettingsSection],
        "blur_range":[0,40],"default_blur":18,
        "blur_control":"appearance settings only; gallery uses the current draft for preview",
        "directories":"shared read-only picker for download and live",
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    _refresh_document_previews("appearance-controls")



def main(argv=None) -> int:
    global OUTPUT_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native", action="store_true",
        help="Use the native desktop Qt backend instead of offscreen",
    )
    parser.add_argument(
        "--checks-only", action="store_true",
        help="Capture font and long-dropdown checks at all three sizes",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--color-theme", choices=("star_trail", "bilibili_blue"), default="star_trail", help="Color theme for the complete workspace and dialog matrix")
    parser.add_argument("--ui-refresh-only", action="store_true", help="Capture navigation, download cards, modes and account states")
    parser.add_argument("--interactions-only", action="store_true", help="Capture row hover, history removal and isolated clipboard prompts")
    parser.add_argument("--refinement-only", action="store_true", help="Capture audio, long-content, failure, draft and filtered-task states")
    parser.add_argument("--chrome-only", action="store_true", help="Check native captions using desktop compositor captures")
    parser.add_argument("--glass-only", action="store_true", help="Capture glass wallpaper and complete download guidance in both modes")
    parser.add_argument("--appearance-controls-only", action="store_true", help="Capture centered account, five settings sections and blur controls")
    parser.add_argument("--physical-pixels", action="store_true", help="Preserve native pixels for typography review")
    parser.add_argument("--updates-only", action="store_true", help="Capture settings tabs and update dialogs only")
    parser.add_argument("--appearance-only", action="store_true", help="Capture both color themes and custom background workspaces")
    parser.add_argument("--ux-only", action="store_true", help="Capture source routing, import progress, account and wallpaper preview states")
    parser.add_argument("--batch-only", action="store_true", help="Capture the compact import workspace with 130 demo works and partial failures")
    parser.add_argument("--actions-only", action="store_true", help="Compare single and batch output cards before and after resolving")
    parser.add_argument("--lifecycle-only", action="store_true", help="Capture close dialogs and background operation settings with offline data")
    parser.add_argument("--mascot-only", action="store_true", help="Capture Xiao Liu at full, short and narrow sidebar sizes in both themes")
    parser.add_argument("--builtin-backgrounds-only", action="store_true", help="Capture the twelve bundled Xiao Liu wallpapers and gallery")
    args = parser.parse_args(argv)
    OUTPUT_DIR = args.output_dir.resolve()
    if args.native:
        os.environ.pop("QT_QPA_PLATFORM", None)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            from scripts.configure_ui_test_display import main as configure_display

            # Configure the ephemeral runner session before Qt reads its screen
            # geometry, including when this scene is run separately.
            configure_display()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biliflow-docs-") as temp_dir, ExitStack() as cleanup:
        temp_root = Path(temp_dir)
        if (
            not QApplication.instance()
            and os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        ):
            # Qt's default 800x800 virtual screen would clamp a large window's
            # dropdown far away from its field. Keep the original DPI and scale.
            screen_config = temp_root / "screen.json"
            screen_config.write_text(
                json.dumps(
                    {
                        "screens": [
                            {
                                "name": "docs",
                                "width": 2000,
                                "height": 1200,
                                "logicalDpi": 96,
                                "logicalBaseDpi": 96,
                                "dpr": 1.0,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={screen_config}"
        app = QApplication.instance() or QApplication(sys.argv)
        app.setProperty("uiAnimationsEnabled", False)
        app.setApplicationName("BiliFlow Docs")
        app.setWindowIcon(QIcon(asset_path("app_icon.png")))
        theme = ThemeManager(app)
        app.setProperty("docsTempRoot", str(temp_root))
        app.setProperty("capturePhysicalPixels", args.physical_pixels)

        if args.lifecycle_only:
            _capture_lifecycle(app, theme, temp_root)
            return 0
        window = _make_main_window(temp_root / "workspace")
        window._settings.appearance.theme = args.color_theme
        theme.set_color_theme(args.color_theme)
        cleanup.callback(window._live_controller.shutdown)
        if args.chrome_only:
            _capture_native_chrome(app, theme, window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.appearance_controls_only:
            _capture_appearance_controls(app,theme,window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.glass_only:
            _capture_glass(app, theme, window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.interactions_only:
            _capture_interactions(app, theme, window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.ui_refresh_only:
            _capture_ui_refresh(app, theme, window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.builtin_backgrounds_only:
            _capture_builtin_backgrounds(app, theme, window, temp_root)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.mascot_only:
            _capture_mascot(app, theme, window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.refinement_only:
            _capture_refinement(app, theme, window)
            window._live_controller.shutdown()
            window.request_quit(confirmed=True)
            return 0
        if args.actions_only:
            _capture_output_actions(app, theme, temp_root)
            window._live_controller.shutdown()
            return 0
        if args.batch_only:
            _capture_batch_polish(app, theme, temp_root)
            window._live_controller.shutdown()
            return 0
        if args.ux_only:
            _capture_ux_states(app, theme, temp_root)
            window._live_controller.shutdown()
            return 0
        if args.checks_only:
            _capture_platform_checks(app, theme, window)
            window._live_controller.shutdown()
            return 0
        _populate_main_window(window)
        _populate_live_page(window, temp_root / "workspace" / "demo-recording")
        preview = _make_batch_dialog()
        window._batch_page._url_text.setPlainText(preview._url_text.toPlainText())
        window._batch_page._on_resolved(preview._resolved_items, [])
        preview.deleteLater()
        if args.appearance_only:
            _capture_appearance(app, theme, window, temp_root)
            window._live_controller.shutdown()
            return 0
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
            "settings": lambda: window._show_settings_tab(SettingsSection.DOWNLOAD),
            "live-settings": lambda: window._show_settings_tab(SettingsSection.LIVE),
            "tools": lambda: window._show_settings_tab(SettingsSection.TOOLS),
            "updates": lambda: window._show_settings_tab(SettingsSection.ABOUT),
            "appearance": lambda: window._show_settings_tab(SettingsSection.APPEARANCE),
        }
        if args.updates_only:
            pages = {name: pages[name] for name in ("settings", "live-settings", "tools", "updates")}
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
        for dark in (True, False):
            theme.apply_theme(dark)
            dialog = UpdateDialog(UpdateRelease(
                "0.9.0b1", "v0.9.0b1", "2026-10-14T00:00:00Z",
                DEMO_RELEASE_NOTES, (),
            ), window)
            _save_widget(app, dialog, f"biliflow-dialog-update{'-light' if not dark else ''}.png")
            dialog.hide()
        if args.updates_only:
            theme.apply_theme(True)
            window.resize(1320, 860)
            pages["settings"]()
            _save_widget(app, window, "biliflow-settings.png")
            window._live_controller.shutdown()
            return 0
        window.resize(1320, 860)
        theme.apply_theme(True)
        for name in ("live", "tasks", "batch", "settings"):
            pages[name]()
            _save_widget(app, window, f"biliflow-{name}.png")
        pages["download"]()
        _save_widget(app, window, "biliflow-dark.png")
        theme.apply_theme(False)
        _save_widget(app, window, "biliflow-light.png")
        _capture_dropdowns(app, theme, window)
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
        _capture_ux_states(app, theme, temp_root)
        _capture_appearance(app, theme, window, temp_root)
        window._live_controller.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
