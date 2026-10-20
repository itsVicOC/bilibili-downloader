"""Behavior and geometry regressions for the unified desktop workspaces."""

import io
from pathlib import Path

import pytest
from PIL import Image
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
    OutputMode,
    StreamInfo,
    TaskStatus,
    VideoInfo,
    VideoQuality,
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
@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("size", [(900, 640), (1120, 760), (1320, 860)])
def test_all_workspaces_fit_and_fixed_actions_remain_visible(
    workspace, qapp, dark, size, theme_id
):
    previous_style, previous_font, previous_palette = (
        qapp.styleSheet(),
        QFont(qapp.font()),
        QPalette(qapp.palette()),
    )
    previous_dark = qapp.property("darkTheme")
    previous_color_theme = qapp.property("colorTheme")
    theme = ThemeManager(qapp, theme_id)
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
        single_bar = window._download_actions
        single_position = single_bar.mapTo(window._workspace_pages.currentWidget(), QPoint())
        single_size = single_bar.size()
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
        assert batch._action_bar.size() == single_size
        assert batch._action_bar.mapTo(window._workspace_pages.currentWidget(), QPoint()) == single_position
        assert batch._add_btn.size() == window._download_btn.size()
        assert batch._action_bar.edit_button.size() == window._edit_output_btn.size()
        assert batch._collapse_btn.isChecked()
        if size[0] == 900:
            batch._collapse_btn.setChecked(False)
            flush()
            assert batch._url_text.isVisible()
            assert batch._preview_card.isHidden()
            assert contained(batch._add_btn, batch)
        window._show_workspace(1)
        flush()
        assert contained(window._live_page.start_stop, window._live_page)
        live_bar = window._live_page._action_bar
        assert live_bar.height() == single_size.height()
        assert contained(window._live_page.monitor, live_bar)
        assert contained(window._live_page.room_settings, live_bar)
        assert window._live_page.start_stop.x() > window._live_page.room_settings.x()
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
        assert contained(window._task_page._download_tools, window._task_page.tabs.currentWidget())
        for button in window._task_page._download_tools.findChildren(QPushButton):
            assert contained(button, window._task_page._download_tools)
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
        assert window._settings_page._action_bar.height() == single_size.height()
        assert window._settings_page._save_btn.height() == window._download_btn.height()
        assert (
            window._settings_page.tabs.currentWidget().horizontalScrollBar().maximum()
            == 0
        )
        window._show_settings_tab(4)
        flush()
        assert contained(window._settings_page._save_btn, window._settings_page)
        assert window._settings_page.tabs.currentWidget().horizontalScrollBar().maximum() == 0
        combo = window._settings_page._theme_combo
        combo.showPopup()
        flush()
        assert combo.view().isVisible()
        combo.hidePopup()
    finally:
        qapp.setProperty("darkTheme", previous_dark)
        qapp.setProperty("colorTheme", previous_color_theme)
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
    assert panel._notice.isHidden()
    assert contained(panel._issue_btn, panel._preview_card)
    assert panel._issue_btn.isVisible()
    assert panel._result_label.isVisible()
    assert "成功 1 项" in panel._result_label.text()
    assert not panel._preview.geometry().intersects(panel._result_label.geometry())
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


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("size", [(900, 640), (1120, 760), (1320, 860)])
def test_recording_task_actions_fit_and_retry_works(workspace, qapp, dark, size):
    previous = (
        qapp.styleSheet(), QFont(qapp.font()), QPalette(qapp.palette()),
        qapp.property("darkTheme"),
    )
    theme = ThemeManager(qapp)
    try:
        theme.apply_theme(dark)
        workspace.resize(*size)
        workspace.show()
        workspace._show_tasks()
        page = workspace._task_page
        page.tabs.setCurrentIndex(1)
        controller = workspace._live_controller
        controller.service.rows = [room("recording")]
        controller.refresh()
        flush()
        controls = page.current.cellWidget(0, 4)
        stop, view = controls.findChildren(QPushButton)
        for button in (stop, view):
            assert button.height() == 32
            assert button.width() >= button.sizeHint().width()
            assert contained(button, controls)
        assert not stop.geometry().intersects(view.geometry())
        assert page.current.horizontalScrollBar().maximum() == 0
        stop.click()
        assert controller.service.commands[-1] == ("stop", {"room_id": 1})
        controller.service.rows = [room("error")]
        controller.refresh()
        flush()
        assert stop.isEnabled()
        assert stop.text() == "重试录制"
        stop.click()
        assert controller.service.commands[-1] == ("start", {"room_id": 1})
        controller.service.rows = [room("finalizing")]
        controller.refresh()
        assert not stop.isEnabled()
        assert view.isEnabled()
        controller.service.rows = [room("recording", room_id=2)]
        controller.refresh()
        assert controls.isHidden()
        assert page.current.cellWidget(0, 4).property("roomId") == 2
    finally:
        qapp.styleHints().colorSchemeChanged.disconnect(theme._on_color_scheme_changed)
        theme.deleteLater()
        qapp.setStyleSheet(previous[0])
        qapp.setFont(previous[1])
        qapp.setPalette(previous[2])
        qapp.setProperty("darkTheme", previous[3])


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


def test_legacy_directory_choices_are_drafts_until_saved(workspace):
    panel = workspace._settings_page
    legacy = room("waiting")
    legacy["output_dir_mode"] = None
    panel.set_live_rooms([legacy])
    wrapper, choice = panel._directory_choices[1]
    assert panel.directory_modes() == {}
    choice.setCurrentIndex(1)
    panel._live_directory.setText("~/新 直播目录")
    assert panel.directory_modes() == {1: "default"}
    assert "~/新 直播目录" in wrapper.preview._full_text
    assert panel.dirty
    panel.load_settings(workspace._settings)
    assert panel.directory_modes() == {}
    choice.setCurrentIndex(2)
    panel.load_settings(workspace._settings, keep_directory_choices=True)
    assert panel.directory_modes() == {1: "custom"}
    legacy["output_dir_mode"] = "custom"
    panel.set_live_rooms([legacy])
    assert not panel._directory_choices
    assert not panel.dirty


def test_room_directory_modes_preserve_custom_draft(workspace, qtbot):
    value = room("waiting")
    value["output_dir_mode"] = "custom"
    dialog = workspace._live_page._build_room_settings_dialog(value)
    qtbot.addWidget(dialog)
    dialog.directory.setText("/tmp/custom")
    dialog.directory.textEdited.emit("/tmp/custom")
    dialog.directory_mode.setCurrentIndex(0)
    assert not dialog.directory.isEnabled()
    assert dialog.directory.text() == workspace._config.load().live.output_dir
    dialog.directory_mode.setCurrentIndex(1)
    assert dialog.directory.isEnabled() and dialog.directory.text() == "/tmp/custom"


def test_session_export_controls_show_selected_session_result(workspace, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from bilibili_downloader.core.live_models import LiveExport

    source = tmp_path / "part.flv"
    source.touch()
    session = RecordingSession(
        id="selected", room=LiveRoom(room_id=1, author="演示"),
        directory=str(tmp_path), started_at="2026-10-20T01:00:00+00:00", status="completed",
        segments=[RecordingSegment(path=str(source), duration=5, finalized_at="2026-10-20T01:00:05+00:00")],
    )
    page = workspace._task_page
    page.update_history([session])
    page.history.setCurrentItem(page.history.topLevelItem(0))
    assert page.export_button.isEnabled() and page.export_button.text() == "合并导出 MP4"
    calls = []
    monkeypatch.setattr(workspace._live_controller, "export_session", lambda *args: calls.append(args))
    target = tmp_path / "whole.mp4"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(target), "MP4"))
    page.export_button.click()
    assert calls == [(session.id, str(target))]
    session.mp4_export = LiveExport(path=str(target), status="failed", error="片段缺失")
    page.update_history([session])
    assert page.history_notice.label.text() == "片段缺失"
    assert page.export_button.text() == "重试合并 MP4"
    session.mp4_export.status = "completed"
    session.mp4_export.error = ""
    target.touch()
    page.update_history([session])
    assert not page.export_play.isHidden() and not page.export_location.isHidden()
    child_target = tmp_path / "part.mp4"
    child_target.touch()
    workspace._live_controller.export_source = str(source.resolve())
    workspace._live_controller.export_path = str(child_target)
    page.history.setCurrentItem(page.history.topLevelItem(0).child(0))
    assert page._selected_export_path() == child_target
    page.history.setCurrentItem(page.history.topLevelItem(0))
    assert page._selected_export_path() == target
    session.status = "recording"
    session.mp4_export = None
    page.update_history([session])
    assert not page.export_button.isEnabled()
    assert "收尾后" in page.history_stage._full_text
    page.history.setCurrentItem(page.history.topLevelItem(0).child(0))
    assert page.export_button.text() == "导出片段 MP4" and page.export_button.isEnabled()


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


def avatar_png():
    output = io.BytesIO()
    Image.new("RGB", (96, 96), "skyblue").save(output, format="PNG")
    return output.getvalue()


def test_sidebar_shows_username_avatar_and_retains_account_action(workspace, qapp):
    window = workspace
    request_id = window._login_status_request_id
    name = "示例&用户名字很长很长"
    window._on_login_status_result(request_id, {
        "isLogin": True, "uname": name, "mid": 123,
        "face": "https://i0.hdslb.com/demo.png", "vip": {"status": 1},
    })
    button = window._header_login
    assert window._account_text == name
    assert button.full_text == name
    assert "已登录" not in button.text()
    assert name in button.toolTip() and "UID: 123" in button.toolTip()
    assert "大会员" in button.accessibleName()
    window._on_login_status_avatar(request_id, avatar_png())
    assert not button._avatar.isNull()
    assert button.iconSize().width() == 28
    window.show()
    window.resize(900, 640)
    flush()
    assert button.text() == ""
    assert contained(button, window._sidebar)
    window.resize(1120, 760)
    flush()
    assert button.text() and "已登录" not in button.text()
    # Theme changes recolor fallback icons without replacing a loaded avatar.
    button._sync_icon()
    assert button.iconSize().width() == 28
    triggered = []
    window._actions["login"].triggered.connect(lambda: triggered.append(True))
    window._actions["login"].triggered.disconnect(window._on_login_triggered)
    button.click()
    assert triggered


@pytest.mark.parametrize("state", ["logout", "expired", "error"])
def test_sidebar_clears_identity_and_rejects_stale_avatar(workspace, state):
    window = workspace
    window._on_login_status_result(0, {
        "isLogin": True, "uname": "示例用户", "face": "demo",
    })
    window._on_login_status_avatar(0, avatar_png())
    window._login_status_request_id = 1
    if state == "logout":
        window._set_login_status_label("未登录", "MutedLabel")
    elif state == "expired":
        window._on_login_status_result(1, {"isLogin": False})
    else:
        window._on_login_status_error(1, "offline")
    window._on_login_status_avatar(0, avatar_png())
    window._on_login_status_result(0, {"isLogin": True, "uname": "旧账号", "face": "old"})
    assert window._header_login._avatar.isNull()
    assert "示例用户" not in window._header_login.toolTip()
    assert window._account_text in ("未登录", "登录状态未知")


def test_appearance_names_keep_existing_configuration_ids(qtbot):
    panel = SettingsDialog(AppSettings(), embedded=True)
    qtbot.addWidget(panel)
    assert [(panel._theme_combo.itemText(i), panel._theme_combo.itemData(i)) for i in range(2)] == [
        ("星河", "star_trail"), ("晴海", "bilibili_blue"),
    ]


def test_new_account_rejects_old_avatar_and_corrupt_avatar_keeps_username(workspace):
    window = workspace
    window._login_status_request_id = 2
    window._on_login_status_result(2, {
        "isLogin": True, "uname": "新账号", "face": "demo://new-avatar",
    })
    window._on_login_status_avatar(1, avatar_png())
    assert window._header_login._avatar.isNull()
    window._on_login_status_avatar(2, b"corrupt image")
    assert window._header_login._avatar.isNull()
    assert window._header_login.full_text == "新账号"
    window._on_login_status_avatar(2, avatar_png())
    assert not window._header_login._avatar.isNull()


def test_empty_download_is_compact_and_parsed_summary_is_always_visible(workspace):
    from bilibili_downloader.core.models import VideoPage

    window = workspace
    window.resize(900, 640)
    window.show()
    flush()
    assert window._content_section.isHidden()
    assert window._empty_download.isVisible()
    window._url_input.setText("BV1GJ411x7h7")
    video = VideoInfo(bvid="BV1GJ411x7h7", pages=[VideoPage(cid=1, page=1), VideoPage(cid=2, page=2)])
    window._on_resolve_success(video, [], [], False)
    flush()
    assert window._empty_download.isHidden()
    assert not window._content_section.isHidden()
    assert "全部 2P" in window._download_hint.toolTip()
    assert window._settings.output_dir in window._download_path_hint.toolTip()
    assert contained(window._download_actions, window._workspace_pages.currentWidget())
    window._edit_output_btn.click()
    flush()
    assert window._workspace_scroll.verticalScrollBar().value() > 0
    window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.AUDIO))
    assert "仅音频" in window._download_hint.toolTip()
    assert "各作品全部分 P" in window._batch_page._output_specs.toolTip()


def test_output_cards_allow_preconfiguration_and_keep_available_choices(workspace):
    window = workspace
    window.resize(900, 640)
    window.show()
    flush()
    assert not window._download_btn.isEnabled()
    assert window._edit_output_btn.isEnabled()
    window._edit_output_btn.click()
    flush()
    assert window._content_section.isVisible() and window._video_info.isHidden()
    window._quality_combo.setCurrentIndex(window._quality_combo.findData(VideoQuality.Q720P))
    window._codec_combo.setCurrentIndex(window._codec_combo.findData(7))
    window._subtitle_check.setChecked(True)
    assert "720P" in window._download_hint.toolTip()
    assert "解析后选择分 P" in window._download_hint.toolTip()
    assert not window._download_btn.isEnabled()
    window._url_input.setText("BV1GJ411x7h7")
    info = VideoInfo(bvid="BV1GJ411x7h7")
    window._on_resolve_success(info, [StreamInfo(id=80, codecid=12), StreamInfo(id=64, codecid=7)], [], True)
    assert window._quality_combo.currentData() == VideoQuality.Q720P
    assert window._codec_combo.currentData() == 7
    assert window._subtitle_check.isChecked()
    assert window._download_btn.isEnabled()
    assert window._download_actions.status.text() == "已选 1 项"
    window._url_input.setText("BV1Q541167Qg")
    assert not window._download_btn.isEnabled()
    assert window._download_actions.status.text() == "待解析"
    window._on_resolve_success(VideoInfo(bvid="BV1Q541167Qg"), [StreamInfo(id=80, codecid=12)], [], True)
    assert window._quality_combo.currentData() == VideoQuality.Q1080P
    assert window._codec_combo.currentData() == 12
    window._download_tabs.setCurrentIndex(1)
    batch = window._batch_page
    batch._action_bar.edit_button.click()
    assert window._download_tabs.currentIndex() == 0
    assert window._content_section.isVisible()


@pytest.mark.parametrize("source, target", [
    ("https://space.bilibili.com/123/favlist?fid=456&ftype=create", "batch"),
    ("ss123", "batch"),
    ("https://live.bilibili.com/21414905", "live"),
])
def test_misplaced_source_can_be_transferred_without_network(workspace, source, target):
    window = workspace
    window._url_input.setText(source)
    window._resolve_btn.click()
    assert not window._resolve_notice.action.isHidden()
    window._resolve_notice.action.click()
    if target == "batch":
        assert window._download_tabs.currentIndex() == 1
        assert source in window._batch_page._url_text.toPlainText()
    else:
        assert window._workspace_pages.currentIndex() == 1
        assert window._live_page.source.text() == source


def test_bulk_actions_respect_scope_and_explain_affected_count(workspace, monkeypatch):
    window = workspace
    table, page = window._download_list, window._task_page
    for task_id, state in ((1, TaskStatus.PAUSED), (2, TaskStatus.FAILED)):
        table.add_item(DownloadItem(video_info=VideoInfo(bvid="BV1GJ411x7h7", cid=task_id)), download_id=task_id, status=state)
    page.filter.setCurrentIndex(page.filter.findData("paused"))
    assert page.bulk_ids("resume") == [1]
    assert page._bulk_buttons[1].text() == "继续 1"
    submitted = []
    monkeypatch.setattr(window, "_on_retry_download", submitted.append)
    page._bulk_buttons[1].click()
    assert submitted == [1]
    page.scope.setCurrentIndex(page.scope.findData("all"))
    assert page.bulk_ids("resume") == [1, 2]
    assert "2 项" in page._bulk_buttons[1].toolTip()


def test_remove_filtered_completed_records_and_undo_preserve_files(workspace, tmp_path):
    window = workspace
    repo, table, page = window._task_repository, window._download_list, window._task_page
    output = tmp_path / "already-downloaded.mp4"
    output.write_bytes(b"demo-file")
    ids = []
    for cid, warnings in ((1, ["字幕失败"]), (2, [])):
        item = DownloadItem(video_info=VideoInfo(bvid="BV1GJ411x7h7", cid=cid))
        task_id = repo.add(item, TaskStatus.COMPLETED)
        repo.update(task_id, progress=1.0, output_path=str(output), warnings=warnings)
        table.add_item(item, download_id=task_id, status=TaskStatus.COMPLETED, progress=1.0, output_path=str(output), warnings=warnings)
        ids.append(task_id)
    page.filter.setCurrentIndex(page.filter.findData("attention"))
    assert page.bulk_ids("clear") == [ids[0]]
    window._on_clear_completed()
    assert repo.get(ids[0]) is None
    assert repo.get(ids[1]) is not None
    assert "文件和断点仍保留" in page.undo_notice.label.text()
    page.undo_notice.action.click()
    assert repo.get(ids[0]).warnings == ["字幕失败"]
    assert repo.get(ids[0]).progress == 1.0
    assert output.read_bytes() == b"demo-file"


def test_remove_failure_does_not_hide_existing_task(workspace, monkeypatch):
    import sqlite3

    window = workspace
    item = DownloadItem(video_info=VideoInfo(bvid="BV1GJ411x7h7"))
    task_id = window._task_repository.add(item, TaskStatus.COMPLETED)
    window._download_list.add_item(item, download_id=task_id, status=TaskStatus.COMPLETED)
    def fail(_ids):
        raise sqlite3.OperationalError("read only")
    monkeypatch.setattr(window._task_repository, "delete_many", fail)
    errors = []
    monkeypatch.setattr(window, "_show_error", errors.append)
    window._download_list._on_delete_clicked(task_id)
    assert window._download_list._row_for(task_id) is not None
    assert window._task_repository.get(task_id) is not None
    assert errors


def test_live_actions_keep_selected_room_identity_visible(workspace):
    window = workspace
    first, second = room("recording", room_id=1), room("waiting", room_id=2)
    first["author"], second["author"] = "主播甲", "主播乙"
    window._live_controller.service.rows = [first, second]
    window._live_controller.refresh()
    window.resize(900, 640)
    window.show()
    window._show_workspace(1)
    window._live_page.select_room(2)
    flush()
    assert "主播乙" in window._live_page._action_target.toolTip()
    assert "主播乙" in window._live_page.start_stop.accessibleName()
    assert contained(window._live_page._action_bar, window._live_page)


def test_theme_cards_are_drafts_and_background_grid_adapts(workspace, qapp):
    window = workspace
    previous = qapp.property("colorTheme")
    window.resize(1320, 860)
    window.show()
    window._show_settings_tab(4)
    flush()
    panel = window._settings_page
    assert panel._appearance_columns == 2
    panel._theme_buttons.button(1).click()
    assert panel._theme_combo.currentData() == "bilibili_blue"
    assert panel.dirty
    assert qapp.property("colorTheme") == previous
    first, selected = panel._theme_buttons.button(0), panel._theme_buttons.button(1)
    first.setFocus(Qt.TabFocusReason)
    flush()
    assert first.hasFocus() and not first.isChecked()
    assert selected.isChecked()
    assert "按空格" in first.accessibleDescription()
    assert "已选中" in selected.accessibleDescription()
    window.resize(900, 640)
    flush()
    assert panel._appearance_columns == 1
    panel._reset_btn.click()
    assert not panel.dirty and panel._theme_buttons.button(0).isChecked()


def test_batch_progress_keeps_compact_input_and_disables_stale_selection(workspace, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtCore import QThreadPool

    monkeypatch.setattr(QThreadPool, "globalInstance", lambda: SimpleNamespace(start=lambda _: None))
    window = workspace
    window.resize(900, 640)
    window.show()
    window._download_tabs.setCurrentIndex(1)
    panel = window._batch_page
    panel._url_text.setPlainText("BV1GJ411x7h7")
    panel._on_resolved([VideoInfo(bvid="BV1GJ411x7h7")], [])
    panel._begin_resolve(["BV1GJ411x7h7"])
    flush()
    assert panel._count_label.height() < 40
    assert panel._preview_card.isHidden()
    assert panel._selected_label.text() == "已选 0 项"
    assert not panel._add_btn.isEnabled()
    assert contained(panel._progress_area, panel)
    assert contained(panel._cancel_btn, panel)
    panel.cancel_resolution()
    from bilibili_downloader.gui.threads.batch_worker import ImportIssue, ImportReport
    panel._on_report(ImportReport([], [ImportIssue("BV1GJ411x7h7", "离线演示失败", "BV1GJ411x7h7")]))
    flush()
    assert panel._preview_card.isHidden()
    assert "成功 0 项" in panel._notice.label.text()
    assert contained(panel._notice, panel)
    assert (window.width(), window.height()) == (900, 640)


@pytest.mark.parametrize("size,min_rows", [((900, 640), 2), ((1120, 760), 5), ((1320, 860), 7)])
def test_large_favorite_import_prioritizes_results_and_preserves_edits(workspace, size, min_rows):
    from bilibili_downloader.gui.threads.batch_worker import ImportIssue, ImportReport

    window = workspace
    window.resize(*size)
    window.show()
    window._download_tabs.setCurrentIndex(1)
    panel = window._batch_page
    source = "https://space.bilibili.com/123/favlist?fid=456"
    panel._url_text.setPlainText(source)
    items = [
        VideoInfo(bvid=f"BV1DEMO{i:05d}", title=f"收藏作品 {i + 1}", collection_title="演示收藏夹")
        for i in range(130)
    ]
    panel._on_report(ImportReport(items, [ImportIssue(source, "失效作品", source, kind="item")] * 28))
    flush()
    assert panel._collapse_btn.isChecked() and panel._url_text.isHidden()
    assert panel._source_summary.toolTip() == source
    assert "演示收藏夹" in panel._source_summary._full_text
    assert panel._preview.isColumnHidden(3)
    assert panel._preview.viewport().height() // panel._preview.rowHeight(0) >= min_rows
    assert panel._notice.isHidden() and panel._issue_btn.isVisible()
    assert "跳过 28 项" in panel._result_label.text()
    assert contained(panel._action_bar, panel)
    assert contained(panel._add_btn, panel._action_bar)
    panel._selectors[0].setChecked(False)
    panel._collapse_btn.setChecked(False)
    flush()
    assert panel._url_text.isVisible()
    assert len(panel.get_video_infos()) == 129
    panel._url_text.appendPlainText("BV1GJ411x7h7")
    assert not panel._add_btn.isEnabled()
    panel._collapse_btn.setChecked(True)
    assert panel._source_summary._full_text.endswith("等 2 个来源")
    assert "BV1GJ411x7h7" in panel._source_summary.toolTip()
    panel._url_text.setPlainText(source)
    assert panel._add_btn.isEnabled() and len(panel.get_video_infos()) == 129
    items[1].collection_title = "另一个来源"
    panel._on_report(ImportReport(items))
    assert not panel._preview.isColumnHidden(3)
    assert panel._issue_btn.isHidden()
