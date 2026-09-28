"""Behavior and geometry regressions for the unified desktop workspaces."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox, QPushButton

from bilibili_downloader.core.live_models import (
    LiveRoom,
    RecordingSegment,
    RecordingSession,
)
from bilibili_downloader.core.models import (
    AppSettings,
    DownloadItem,
    StreamInfo,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.utils.config import ConfigManager


class StubService:
    def __init__(self, *_args):
        self.rows = []
        self.commands = []
        self.pending_messages = []
        self.start_count = 0
        self.stopped = True

    def start(self):
        self.start_count += 1

    def snapshot(self):
        return [dict(row) for row in self.rows]

    def messages(self):
        result, self.pending_messages = self.pending_messages, []
        return result

    def command(self, action, **kwargs):
        self.commands.append((action, kwargs))

    def request_shutdown(self):
        pass

    @property
    def active(self):
        return any(row["active"] for row in self.rows)


def room(state="waiting", enabled=True, room_id=1):
    return dict(
        room_id=room_id,
        author="主播",
        title="很长的直播标题",
        state=state,
        state_label=state,
        enabled=enabled,
        active=state in {"recording", "finalizing"},
        detail="完整状态说明",
        duration=123,
        size=123456,
        speed=1234,
        qualities=[{"label": "原画", "qn": 10000}],
        quality=0,
        output_dir="/tmp/" + "长目录/" * 30,
        segment_seconds=1800,
    )


@pytest.fixture
def workspace(qtbot, tmp_path, monkeypatch):
    def unexpected_dialog(box):
        raise AssertionError(f"Unexpected dialog: {box.text()}")

    monkeypatch.setattr(QMessageBox, "exec", unexpected_dialog)
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    controller = LiveUiController(config, service_factory=StubService)
    window = MainWindow(config, TaskRepository(tmp_path / "tasks.sqlite3"), controller)

    def before_close(widget):
        widget._settings_page.load_settings(widget._settings)
        controller.service.rows = []
        controller.shutdown()

    qtbot.addWidget(window, before_close_func=before_close)
    yield window
    window._settings_page.load_settings(window._settings)
    controller.service.rows = []
    controller.refresh()
    controller.shutdown()


def flush():
    for _ in range(4):
        QApplication.processEvents()


def contained(widget, ancestor):
    rectangle = QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())
    return ancestor.rect().contains(rectangle)


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("size", [(900, 640), (1120, 760), (1320, 860)])
def test_all_workspaces_fit_and_fixed_actions_remain_visible(
    workspace, qapp, dark, size
):
    previous_style, previous_font, previous_palette = (
        qapp.styleSheet(),
        QFont(qapp.font()),
        QPalette(qapp.palette()),
    )
    previous_dark = qapp.property("darkTheme")
    theme = ThemeManager(qapp)
    theme.apply_theme(dark)
    window = workspace
    try:
        window.resize(*size)
        window.show()
        window._live_controller.service.rows = [room("recording")]
        window._live_controller.refresh()
        window._live_page.select_room(1)
        for page in range(4):
            window._show_workspace(page)
            flush()
            assert (window.width(), window.height()) == size
            assert window._workspace_pages.width() == size[0] - window._sidebar.width()
        window._show_workspace(0)
        flush()
        assert contained(window._download_btn, window._workspace_pages.currentWidget())
        window._download_tabs.setCurrentIndex(1)
        batch = window._batch_page
        batch._url_text.setPlainText("BV1GJ411x7h7")
        batch._on_resolved([VideoInfo(bvid="BV1GJ411x7h7", title="作品")], [])
        flush()
        assert contained(batch._add_btn, batch)
        assert not batch._input_card.geometry().intersects(
            batch._preview_card.geometry()
        )
        assert not batch._preview.geometry().intersects(batch._result_label.geometry())
        assert batch._preview.horizontalScrollBar().maximum() == 0
        if size[0] == 900:
            assert batch._collapse_btn.isChecked()
            batch._collapse_btn.setChecked(False)
            flush()
            assert batch._url_text.isVisible()
            assert batch._preview_card.isHidden()
            assert contained(batch._add_btn, batch)
        window._show_workspace(1)
        flush()
        assert contained(window._live_page.start_stop, window._live_page)
        assert window._live_page.rooms.horizontalScrollBar().maximum() == 0
        window._show_tasks(1)
        flush()
        assert window._task_page.current.horizontalScrollBar().maximum() == 0
        table = window._download_list
        for task_id, status in enumerate(
            (
                TaskStatus.DOWNLOADING,
                TaskStatus.PAUSED,
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
            ),
            start=1,
        ):
            table.add_item(
                DownloadItem(video_info=VideoInfo(bvid="BV1GJ411x7h7", title="作品")),
                download_id=task_id,
                status=status,
                progress=0.42,
            )
        window._show_tasks(0)
        flush()
        table.update_progress(1, 0.73, "下载中")
        assert table._progress_at(table._row_for(1)).value() == 73
        table.mark_paused(1)
        assert table._progress_at(table._row_for(1)).objectName() == "PausedProgress"
        table.mark_downloading(1)
        table.mark_done(1)
        flush()
        for row in range(table.rowCount()):
            bar = table._progress_at(row)
            cell_center = table.visualItemRect(table.item(row, 0)).center().y()
            bar_center = bar.mapTo(table.viewport(), bar.rect().center()).y()
            assert abs(bar_center - cell_center) <= 1
        window._show_tasks(2)
        flush()
        assert window._task_page.history.horizontalScrollBar().maximum() == 0
        window._show_settings_tab(0)
        flush()
        assert contained(window._settings_page._save_btn, window._settings_page)
        assert (
            window._settings_page.tabs.currentWidget().horizontalScrollBar().maximum()
            == 0
        )
    finally:
        qapp.setProperty("darkTheme", previous_dark)
        qapp.setPalette(previous_palette)
        qapp.setFont(previous_font)
        qapp.setStyleSheet(previous_style)
        theme.deleteLater()


def test_navigation_preserves_resolve_and_live_service(workspace):
    window = workspace
    window._url_input.setText("BV1GJ411x7h7")
    info = VideoInfo(bvid="BV1GJ411x7h7", title="作品")
    window._on_resolve_success(info, [StreamInfo(id=80, codecid=12)], [], True)
    for index in (1, 2, 3, 0, 2, 1, 0):
        window._show_workspace(index)
    assert window._current_video is info
    assert window._download_btn.isEnabled()
    assert window._url_input.text() == "BV1GJ411x7h7"
    assert window._live_page.controller is window._task_page.controller
    assert window._live_controller.service.start_count == 1
    window._url_input.setText("BV1Q541167Qg")
    assert not window._download_btn.isEnabled()
    assert window._current_video is None


def test_enqueue_stays_on_source_and_reports_duplicates(workspace, monkeypatch):
    window = workspace
    window._url_input.setText("BV1GJ411x7h7")
    info = VideoInfo(bvid="BV1GJ411x7h7", cid=1, title="作品")
    window._on_resolve_success(info, [StreamInfo(id=80, codecid=12)], [], True)
    monkeypatch.setattr(window, "_confirm_copyright_acknowledgement", lambda: True)
    monkeypatch.setattr(window, "_start_download", lambda *_args: None)
    window._on_download_clicked()
    window._on_download_clicked()
    assert window._workspace_pages.currentIndex() == 0
    assert len(window._task_repository.list_tasks()) == 1
    assert "重复" in window._enqueue_notice.label.text()
    window._enqueue_notice.action.click()
    assert window._workspace_pages.currentIndex() == 2


def test_batch_source_edits_invalidate_preview_and_inflight_results(qtbot):
    panel = BatchDialog(embedded=True)
    qtbot.addWidget(panel)
    first = "BV1GJ411x7h7"
    panel._url_text.setPlainText(first)
    panel._on_resolved([VideoInfo(bvid=first, title="作品")], ["来源读取失败"])
    assert panel._add_btn.isEnabled()
    submitted = []
    panel.enqueue_requested.connect(submitted.append)
    panel._url_text.setPlainText("BV1Q541167Qg")
    assert not panel._add_btn.isEnabled()
    panel.accept()
    assert submitted == []
    panel._url_text.setPlainText(first)
    assert panel._add_btn.isEnabled()
    panel._url_text.setPlainText("BV1Q541167Qg")
    panel._request_source = first
    panel._on_resolved([VideoInfo(bvid=first)], [])
    assert not panel._add_btn.isEnabled()
    assert "修改" in panel._notice.label.text()


def test_batch_partial_failure_fits_the_small_workspace(workspace):
    workspace.resize(900, 640)
    workspace.show()
    workspace._download_tabs.setCurrentIndex(1)
    panel = workspace._batch_page
    panel._url_text.setPlainText("BV1GJ411x7h7")
    panel._on_resolved(
        [VideoInfo(bvid="BV1GJ411x7h7", title="作品")], ["来源解析失败" * 30]
    )
    flush()
    assert contained(panel._preview, panel._preview_card)
    assert contained(panel._notice, panel)
    assert not panel._result_label.isVisible()
    panel._url_text.setPlainText("BV1Q541167Qg")
    flush()
    assert contained(panel._preview, panel._preview_card)
    assert not panel._add_btn.isEnabled()


def test_many_live_rooms_use_one_scroll_area_when_details_are_stacked(workspace):
    workspace.resize(900, 640)
    workspace._show_workspace(1)
    workspace.show()
    controller = workspace._live_controller
    controller.service.rows = [room(room_id=i) for i in range(1, 13)]
    controller.refresh()
    flush()
    page = workspace._live_page
    assert page.rooms.verticalScrollBar().maximum() == 0
    assert page._scroll.verticalScrollBar().maximum() > 0
    page.select_room(12)
    assert page._room_id() == 12
    assert page._scroll.verticalScrollBar().value() > 0


def test_settings_merge_preserves_external_updates(qtbot):
    settings = AppSettings(copyright_notice_version=0)
    panel = SettingsDialog(settings, embedded=True)
    qtbot.addWidget(panel)
    panel._max_concurrent.setValue(5)
    latest = settings.model_copy(deep=True)
    latest.copyright_notice_version = 99
    latest.last_login_at = "2026-09-28T12:00:00"
    latest.live.max_concurrent = 4
    merged = panel.merge_into(latest)
    assert merged.max_concurrent_downloads == 5
    assert merged.live.max_concurrent == 4
    assert merged.copyright_notice_version == 99
    assert merged.last_login_at == latest.last_login_at
    panel.load_settings(latest)
    assert not panel.dirty


def test_settings_leave_cancel_discard_and_save(workspace, monkeypatch):
    window = workspace
    window._show_workspace(3)
    panel = window._settings_page
    panel._max_concurrent.setValue(5)
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: QMessageBox.Cancel)
    assert not window._show_workspace(0)
    assert window._workspace_pages.currentIndex() == 3
    assert window._config.load().max_concurrent_downloads == 3
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: QMessageBox.Discard)
    assert window._show_workspace(0)
    assert not panel.dirty
    window._show_workspace(3)
    panel._max_concurrent.setValue(5)
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: QMessageBox.Save)
    assert window._show_workspace(0)
    assert window._config.load().max_concurrent_downloads == 5
    assert window._download_pool.maxThreadCount() == 5
    assert window._live_controller.service.commands[-1][0] == "settings"


def test_failed_settings_save_keeps_draft(workspace, monkeypatch):
    window = workspace
    window._show_workspace(3)
    window._settings_page._max_concurrent.setValue(4)

    def fail(_settings):
        raise OSError("磁盘不可写")

    monkeypatch.setattr(window._config, "save", fail)
    assert not window._save_settings()
    assert window._settings_page.dirty
    assert window._settings.max_concurrent_downloads == 3
    assert "磁盘不可写" in window._settings_page._notice.label.text()
    window._settings_page.load_settings(window._settings)


@pytest.mark.parametrize(
    "state",
    [
        "waiting",
        "disabled",
        "preparing",
        "queued",
        "recording",
        "reconnecting",
        "finalizing",
        "error",
    ],
)
def test_room_controls_follow_state(workspace, state):
    window = workspace
    controller = window._live_controller
    controller.service.rows = [room(state, enabled=state != "disabled")]
    controller.refresh()
    window._live_page.select_room(1)
    page = window._live_page
    assert page.start_stop.isEnabled() == (state != "finalizing")
    assert page.room_settings.isEnabled() == (
        state not in {"recording", "reconnecting", "finalizing"}
    )
    assert page.remove_action.isEnabled() == page.room_settings.isEnabled()
    assert bool(window._task_page._live_rows) == (state not in {"waiting", "disabled"})


def test_live_messages_are_shared_and_consumed_once(workspace):
    controller = workspace._live_controller
    controller.service.pending_messages = ["录制重连提示"]
    controller.refresh()
    assert workspace._live_page.message.text() == "录制重连提示"
    assert workspace._task_page.notice.label.text() == "录制重连提示"
    controller.refresh()
    assert controller.service.pending_messages == []
    assert workspace._task_page.notice.label.text() == "录制重连提示"


def test_room_settings_rechecks_recording_state_before_save(workspace, qtbot):
    controller = workspace._live_controller
    controller.service.rows = [room()]
    controller.refresh()
    dialog = workspace._live_page._build_room_settings_dialog(controller.rows[0])
    qtbot.addWidget(dialog)
    buttons = dialog.findChild(QDialogButtonBox)
    controller.service.rows[0].update(state="recording", active=True)
    controller.refresh()
    buttons.button(QDialogButtonBox.Save).click()
    assert not dialog.result()
    controller.service.rows[0].update(state="waiting", active=False)
    controller.refresh()
    dialog.directory.clear()
    buttons.button(QDialogButtonBox.Save).click()
    assert not dialog.result()
    dialog.directory.setText("/tmp/demo")
    buttons.button(QDialogButtonBox.Save).click()
    assert dialog.result()


def test_history_refresh_keeps_expansion_selection_and_export_eligibility(
    workspace, tmp_path
):
    controller = workspace._live_controller
    file = tmp_path / "part.flv"
    file.touch()
    session = RecordingSession(
        id="one",
        room=LiveRoom(room_id=1, author="主播"),
        directory=str(tmp_path),
        started_at="2026-09-28T00:00:00+00:00",
        status="completed",
        segments=[
            RecordingSegment(
                path=str(file),
                duration=30,
                size=10,
                finalized_at="2026-09-28T00:01:00+00:00",
            )
        ],
    )
    controller.repository.save_session(session)
    controller.refresh()
    page = workspace._task_page
    parent = page.history.topLevelItem(0)
    parent.setExpanded(True)
    page.history.setCurrentItem(parent.child(0))
    assert page.export_button.isEnabled()
    session.warnings = ["完整的录制警告"]
    controller.repository.save_session(session)
    controller.refresh()
    assert page.history.topLevelItem(0).isExpanded()
    assert page.history.currentItem().data(0, Qt.UserRole) == str(file)
    assert "完整的录制警告" in page.history_detail.toPlainText()
    file.unlink()
    page._history_selection()
    assert not page.export_button.isEnabled()
    assert not page.open_button.isEnabled()


def test_export_disables_duplicates_and_retains_source(
    workspace, tmp_path, qtbot, monkeypatch
):
    from bilibili_downloader.core.ffmpeg import FFmpegManager

    source, output = tmp_path / "part.flv", tmp_path / "part.mp4"
    source.write_bytes(b"source")

    def remux(_source, target, *_args):
        Path(target).write_bytes(b"export")
        return True, str(target)

    monkeypatch.setattr(FFmpegManager, "remux_live", remux)
    controller = workspace._live_controller
    controller.export(source, output)
    first = controller._export
    controller.export(source, tmp_path / "duplicate.mp4")
    assert controller._export is first
    qtbot.waitUntil(first.done)
    controller.refresh()
    assert not controller.exporting
    assert controller.export_path == str(output)
    assert source.read_bytes() == b"source"
    assert output.read_bytes() == b"export"
    assert not (tmp_path / "duplicate.mp4").exists()


def test_filters_and_actions_keep_stable_ids_after_removal(workspace):
    table = workspace._download_list
    item = DownloadItem(video_info=VideoInfo(bvid="BV1GJ411x7h7", title="作品"))
    for task_id, status in (
        (10, TaskStatus.PAUSED),
        (20, TaskStatus.FAILED),
        (30, TaskStatus.COMPLETED),
    ):
        table.add_item(item, download_id=task_id, status=status)
    workspace._task_page.filter.setCurrentIndex(
        workspace._task_page.filter.findData("attention")
    )
    assert not table.isRowHidden(table._row_for(20))
    assert table.isRowHidden(table._row_for(10))
    table.remove_item(10)
    workspace._task_page.refresh_downloads()
    retried = []
    table.retry_requested.disconnect(workspace._on_retry_download)
    table.retry_requested.connect(retried.append)
    buttons = table.cellWidget(table._row_for(20), 4).findChildren(QPushButton)
    buttons[0].click()
    assert retried == [20]


def test_settings_preserve_existing_fractional_display_units(qtbot):
    settings = AppSettings()
    settings.live.segment_seconds = 61
    settings.live.minimum_free_bytes = 1024**3 + 1
    panel = SettingsDialog(settings, embedded=True)
    qtbot.addWidget(panel)
    assert not panel.dirty
    assert panel.get_settings().live == settings.live


def test_settings_validation_marks_the_relevant_field(qtbot):
    panel = SettingsDialog(AppSettings(), embedded=True)
    qtbot.addWidget(panel)
    panel._path_template.setText("../{title}")
    assert not panel.validate()
    assert panel.tabs.currentIndex() == 0
    assert panel._field_rows["path_template"].error.text()
    panel.load_settings(AppSettings())
    assert panel._field_rows["path_template"]._error_row.isHidden()
