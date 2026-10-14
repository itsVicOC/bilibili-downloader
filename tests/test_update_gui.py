import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from bilibili_downloader.core.models import (
    AppSettings,
    DownloadItem,
    TaskStatus,
    UpdateChannel,
    VideoInfo,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.core.update_protocol import BuildInfo
from bilibili_downloader.core.updater import (
    PreparedUpdate,
    UpdateCancelled,
    UpdateRelease,
)
from bilibili_downloader.gui.dialogs.update_dialog import UpdateDialog
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.utils.config import ConfigManager
from tests.test_workspaces import StubService, room

RELEASE = UpdateRelease(
    "0.9.0b1",
    "v0.9.0b1",
    "2026-10-14T00:00:00Z",
    "<b>plain release notes</b>\n" * 100,
    (),
)


class Service:
    def __init__(self):
        self.channels = []
        self.result = RELEASE
        self.error = None
        self.gate = None

    def load_prepared(self):
        return None

    def check(self, channel, cancel=None):
        self.channels.append(channel)
        if self.gate:
            self.gate.wait(3)
        if self.error:
            raise ValueError(self.error)
        return self.result

    def prepare(self, release, cancel, progress):
        while not cancel.wait(0.01):
            progress(10)
        raise UpdateCancelled("cancelled")


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    controller = LiveUiController(config, service_factory=StubService)
    service = Service()
    window = MainWindow(
        config,
        TaskRepository(tmp_path / "tasks.sqlite3"),
        controller,
        update_service=service,
    )
    monkeypatch.setattr(UpdateDialog, "exec", lambda _dialog: UpdateDialog.LATER)

    def before_close(widget):
        service.gate.set() if service.gate else None
        widget._updates.shutdown()
        widget._updates.pool.waitForDone(3000)
        widget._settings_page.load_settings(widget._settings)
        controller.service.rows = []
        controller.shutdown()

    qtbot.addWidget(window, before_close_func=before_close)
    return window


def wait_idle(qtbot, window):
    qtbot.waitUntil(lambda: not window._updates.busy, timeout=4000)


def test_startup_setting_and_default_channel(qtbot, window):
    assert window._settings.auto_check_updates
    assert window._settings.update_channel == UpdateChannel.STABLE
    window._settings.auto_check_updates = False
    window.start_startup_update_check()
    assert not window._updates.service.channels
    window._settings.auto_check_updates = True
    window.start_startup_update_check()
    wait_idle(qtbot, window)
    assert window._updates.service.channels == [UpdateChannel.STABLE]


def test_manual_check_uses_unsaved_visible_channel(qtbot, window):
    panel = window._settings_page
    panel._update_channel.setCurrentIndex(1)
    panel._check_update_btn.click()
    wait_idle(qtbot, window)
    assert window._updates.service.channels == [UpdateChannel.LATEST]
    assert window._config.load().update_channel == UpdateChannel.STABLE
    assert panel.dirty


@pytest.mark.parametrize("skipped", ["v0.9.0-beta.1", "v0.9-beta.1"])
def test_skipped_version_hidden_automatically_but_shown_manually(
    qtbot, window, monkeypatch, skipped
):
    window._settings.skipped_update_versions = [skipped]
    shown = []
    monkeypatch.setattr(
        UpdateDialog,
        "exec",
        lambda dialog: shown.append(dialog.notes.toPlainText()) or UpdateDialog.LATER,
    )
    window.start_startup_update_check()
    wait_idle(qtbot, window)
    assert shown == []
    window._updates.check("latest")
    wait_idle(qtbot, window)
    assert shown == [RELEASE.notes]


def test_skip_persists_and_settings_draft_does_not_overwrite_it(
    qtbot, window, monkeypatch
):
    panel = window._settings_page
    panel._max_concurrent.setValue(5)
    monkeypatch.setattr(UpdateDialog, "exec", lambda _dialog: UpdateDialog.SKIP)
    window._updates.check("latest")
    wait_idle(qtbot, window)
    assert window._config.load().skipped_update_versions == [RELEASE.version]
    assert panel.dirty and window._config.load().max_concurrent_downloads == 3
    assert window._save_settings()
    assert window._config.load().skipped_update_versions == [RELEASE.version]
    assert ConfigManager(
        window._config._config_path
    ).load().skipped_update_versions == [RELEASE.version]


def test_duplicate_checks_and_changed_channel_discard_old_result(
    qtbot, window, monkeypatch
):
    service = window._updates.service
    service.gate = threading.Event()
    shown = []
    monkeypatch.setattr(
        UpdateDialog, "exec", lambda _dialog: shown.append(True) or UpdateDialog.LATER
    )
    assert window._updates.check("stable")
    assert not window._updates.check("stable")
    qtbot.waitUntil(lambda: bool(service.channels))
    window._settings_page._update_channel.setCurrentIndex(1)
    service.gate.set()
    wait_idle(qtbot, window)
    assert service.channels == ["stable"] and not shown
    assert "通道已修改" in window._settings_page._update_notice.label.text()


def test_automatic_error_is_quiet_and_manual_error_is_visible(
    qtbot, window, monkeypatch
):
    errors = []
    monkeypatch.setattr(window, "_on_update_failed", lambda *args: errors.append(args))
    # Replace the already connected slot for this assertion.
    window._updates.failed.disconnect()
    window._updates.failed.connect(window._on_update_failed)
    window._updates.service.error = "offline"
    window.start_startup_update_check()
    wait_idle(qtbot, window)
    assert errors == [("offline", False)]
    window._updates.check("stable")
    wait_idle(qtbot, window)
    assert errors[-1] == ("offline", True)


def test_manual_no_update_feedback(qtbot, window):
    window._updates.service.result = None
    window._updates.check("stable")
    wait_idle(qtbot, window)
    assert (
        "当前已是所选通道的最新版本"
        in window._settings_page._update_notice.label.text()
    )


def test_manual_check_before_startup_timer_prevents_second_popup(qtbot, window):
    window._updates.check("stable")
    wait_idle(qtbot, window)
    window.start_startup_update_check()
    assert window._updates.service.channels == ["stable"]


def test_reverting_channel_draft_invalidates_inflight_check(qtbot, window):
    service = window._updates.service
    service.gate = threading.Event()
    panel = window._settings_page
    panel._update_channel.setCurrentIndex(1)
    panel._check_update_btn.click()
    qtbot.waitUntil(lambda: bool(service.channels))
    panel.load_settings(window._settings)
    service.gate.set()
    wait_idle(qtbot, window)
    assert "通道已修改" in panel._update_notice.label.text()


def test_download_can_be_cancelled_without_failure_dialog(qtbot, window, monkeypatch):
    failures = []
    window._updates.failed.connect(lambda *args: failures.append(args))
    assert window._updates.download(RELEASE)
    qtbot.waitUntil(lambda: window._settings_page._update_progress.value() == 10)
    window._settings_page._cancel_update_btn.click()
    wait_idle(qtbot, window)
    assert window._updates.pending is None and not failures
    assert "更新已取消" in window._settings_page._update_notice.label.text()


def prepared_update():
    return PreparedUpdate(
        RELEASE,
        BuildInfo(RELEASE.version, "Windows", "x86_64", "lite"),
        Path("/download.zip"),
        "0" * 64,
        Path("/app"),
        Path("/stage"),
    )


def test_active_recording_offers_later_restart_without_stopping(window, monkeypatch):
    window._live_controller.service.rows = [room(state="recording")]
    labels = []

    def later(box):
        labels.extend(button.text() for button in box.buttons())
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "exec", later)
    window._on_update_prepared(prepared_update())
    assert "停止任务并重启" in labels and "稍后重启" in labels
    assert not window._update_in_progress and not window._live_controller._closed


def test_unsaved_settings_cancel_preserves_running_app(window, monkeypatch):
    monkeypatch.setattr(window, "_can_leave_settings", lambda: False)
    window._on_update_prepared(prepared_update())
    assert not window._update_in_progress and window.centralWidget().isEnabled()


def test_shutdown_timeout_aborts_and_restores_live_service(window, monkeypatch):
    failures = []
    monkeypatch.setattr(
        window, "_on_update_failed", lambda *args: failures.append(args)
    )
    window._live_controller.shutdown()
    window._update_shutdown_timer = QTimer(window)
    window._update_deadline = time.monotonic() - 1
    window._update_in_progress = True
    window.centralWidget().setEnabled(False)
    window._wait_update_shutdown()
    assert not window._update_in_progress and window.centralWidget().isEnabled()
    assert window._live_controller.timer.isActive()
    assert "超时" in failures[0][0] or "及时停止" in failures[0][0]


def test_pending_manual_package_has_open_archive_action(window):
    panel = window._settings_page
    panel.set_pending_update(replace(prepared_update(), staged=None, reason="手动安装"))
    assert not panel._open_update_archive.isHidden()
    assert panel._install_update_btn.isHidden()


def test_probation_initializes_data_without_starting_download_or_live(
    qtbot, tmp_path, monkeypatch
):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    repository.add(
        DownloadItem(video_info=VideoInfo(bvid="BV1GJ411x7h7")),
        status=TaskStatus.QUEUED,
    )
    controller = LiveUiController(config, service_factory=StubService, autostart=False)
    started = []
    monkeypatch.setattr(
        MainWindow,
        "_start_download",
        lambda self, item, task_id: started.append(task_id),
    )
    window = MainWindow(
        config, repository, controller, update_service=Service(), startup_paused=True
    )
    qtbot.addWidget(window)
    assert controller.service.start_count == 0 and not started
    window.start_startup_update_check()
    assert not window._updates.service.channels
    window.resume_startup()
    assert controller.service.start_count == 1 and len(started) == 1
