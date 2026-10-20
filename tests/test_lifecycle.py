"""Window residency must never accidentally become application shutdown."""

import json
import os
import subprocess
import sys
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRunnable, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from bilibili_downloader.core.models import AppSettings, WindowCloseAction
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.close_dialog import CloseWindowDialog
from bilibili_downloader.gui.lifecycle import ApplicationLifecycle
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.utils.config import ConfigManager
from tests.test_workspaces import StubService, room


class TrayStub(QObject):
    activated = Signal(object)
    messageClicked = Signal()
    available = True

    def __init__(self, icon, parent):
        super().__init__(parent)
        self.icon = icon
        self.visible = False
        self.messages = []

    @classmethod
    def isSystemTrayAvailable(cls):
        return cls.available

    @staticmethod
    def supportsMessages():
        return True

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, text):
        self.tooltip = text

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def showMessage(self, *args):
        self.messages.append(args)


@pytest.fixture
def desktop(qapp, qtbot, tmp_path, monkeypatch):
    previous = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)
    monkeypatch.setattr(TrayStub, "available", True)
    quit_calls = []
    monkeypatch.setattr(qapp, "quit", lambda: quit_calls.append(True))
    windows = []

    def unexpected_dialog(box):
        pytest.fail(f"Unexpected exit confirmation: {box.text()}")

    monkeypatch.setattr(QMessageBox, "exec", unexpected_dialog)

    def make(platform="win32"):
        directory = tmp_path / str(len(windows))
        config = ConfigManager(directory / "config.json")
        config.save(AppSettings(output_dir=str(directory / "downloads")))
        controller = LiveUiController(config, service_factory=StubService)
        window = MainWindow(config, TaskRepository(directory / "tasks.sqlite3"),
                            controller, desktop_platform=platform)
        lifecycle = ApplicationLifecycle(qapp, window, desktop_platform=platform,
                                         tray_factory=TrayStub)
        def cleanup(widget):
            widget._settings_page.load_settings(widget._settings)
            widget._live_controller.rows = []
            widget._live_controller.service.rows = []
            widget._live_controller.exporting = False
            widget.request_quit(confirmed=True)
            qtbot.waitUntil(lambda: widget._shutdown_complete, timeout=5000)
            lifecycle.dispose()

        qtbot.addWidget(window, before_close_func=cleanup)
        windows.append((window, lifecycle))
        window.show()
        return window, lifecycle, quit_calls

    yield make
    qapp.setQuitOnLastWindowClosed(previous)


def choose(monkeypatch, result, *, remember=False):
    def execute(dialog):
        dialog.remember.setChecked(remember)
        return result
    monkeypatch.setattr(CloseWindowDialog, "exec", execute)


@pytest.mark.parametrize("value", [None, "invalid", {}, 3])
def test_invalid_close_preference_does_not_reset_other_settings(tmp_path, value):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"output_dir": "/saved", "windows_close_action": value}))
    settings = ConfigManager(path).load()
    assert settings.windows_close_action == WindowCloseAction.ASK
    assert settings.output_dir == "/saved"
    assert not path.with_suffix(".json.bak").exists()


def test_macos_close_preserves_window_drafts_services_and_workers(desktop, qtbot, monkeypatch):
    window, lifecycle, quits = desktop("darwin")
    window._show_workspace(3)
    window._settings_page._path_template.setText("draft/{title}")
    window._url_input.setText("BV1GJ411x7h7")
    pause = Mock(wraps=window._download_list.pause_all_workers)
    monkeypatch.setattr(window._download_list, "pause_all_workers", pause)
    window._live_controller.service.rows = [room("recording")]
    window._live_controller.refresh()
    gate, started = Event(), Event()

    class Job(QRunnable):
        def run(self):
            started.set()
            gate.wait(5)

    window._download_pool.start(Job())
    assert started.wait(1)
    try:
        window.close()
        assert window.isHidden() and not window._quit_requested
        assert not window._live_controller._closed and not window._updates._closed
        assert window._live_controller.timer.isActive()
        assert window._download_pool.activeThreadCount() == 1
        pause.assert_not_called()
        assert not quits
        QCoreApplication.sendEvent(lifecycle.app, QEvent(QEvent.ApplicationActivate))
        qtbot.waitUntil(window.isVisible)
        assert window._workspace_pages.currentIndex() == 3
        assert window._url_input.text() == "BV1GJ411x7h7"
        assert window._settings_page._path_template.text() == "draft/{title}"
        assert window._settings_page.dirty
        assert "close_window" in window._actions
    finally:
        gate.set()
        window._download_pool.waitForDone(1000)


def test_windows_close_to_tray_remembers_without_losing_other_drafts(desktop, monkeypatch):
    window, lifecycle, _ = desktop()
    window._show_workspace(3)
    panel = window._settings_page
    panel._path_template.setText("draft/{title}")
    choose(monkeypatch, CloseWindowDialog.TRAY, remember=True)
    window.close()
    assert window.isHidden() and lifecycle.tray.visible
    assert len(lifecycle.tray.messages) == 1
    assert window._config.load().windows_close_action == WindowCloseAction.TRAY
    assert ConfigManager(window._config.data_dir / "config.json").load().windows_close_action == WindowCloseAction.TRAY
    assert panel.dirty and panel._path_template.text() == "draft/{title}"
    assert panel._controls["windows_close_action"].currentData() == WindowCloseAction.TRAY
    assert panel.merge_into(window._config.load()).windows_close_action == WindowCloseAction.TRAY
    lifecycle.tray.activated.emit(QSystemTrayIcon.Trigger)
    assert window.isVisible()
    window.close()
    assert window.isHidden() and len(lifecycle.tray.messages) == 1
    lifecycle.tray.messageClicked.emit()
    assert window.isVisible()


@pytest.mark.parametrize("result", [CloseWindowDialog.CANCEL, CloseWindowDialog.TRAY])
def test_without_remember_does_not_change_preference(desktop, monkeypatch, result):
    window, _, _ = desktop()
    choose(monkeypatch, result)
    window.close()
    assert window._config.load().windows_close_action == WindowCloseAction.ASK
    assert window.isVisible() == (result == CloseWindowDialog.CANCEL)


def test_cancel_does_not_remember_even_if_checkbox_is_selected(desktop, monkeypatch):
    window, _, _ = desktop()
    choose(monkeypatch, CloseWindowDialog.CANCEL, remember=True)
    window.close()
    assert window.isVisible() and not window._quit_requested
    assert window._config.load().windows_close_action == WindowCloseAction.ASK


def test_close_preference_save_failure_still_hides_and_explains_failure(desktop, monkeypatch):
    window, lifecycle, _ = desktop()
    choose(monkeypatch, CloseWindowDialog.TRAY, remember=True)
    monkeypatch.setattr(window._config, "save", Mock(side_effect=OSError("read only")))
    window.close()
    assert window.isHidden()
    lifecycle.restore_window()
    assert "无法记住" in window._settings_page._notice.label.text()
    assert window._settings.windows_close_action == WindowCloseAction.ASK


@pytest.mark.parametrize("saved", [WindowCloseAction.ASK, WindowCloseAction.TRAY])
def test_unavailable_tray_keeps_window_reachable(desktop, monkeypatch, saved):
    window, _, _ = desktop()
    window._settings.windows_close_action = saved
    monkeypatch.setattr(TrayStub, "available", False)

    def cancel(dialog):
        assert not dialog.tray_button.isEnabled()
        assert not dialog.unavailable.isHidden()
        assert dialog.cancel_button.isDefault()
        return CloseWindowDialog.CANCEL

    monkeypatch.setattr(CloseWindowDialog, "exec", cancel)
    window.close()
    assert window.isVisible() and not window._quit_requested


def test_tray_loss_while_choosing_does_not_hide_window(desktop, monkeypatch):
    window, _, _ = desktop()

    def lost(dialog):
        TrayStub.available = False
        return CloseWindowDialog.TRAY

    monkeypatch.setattr(CloseWindowDialog, "exec", lost)
    window.close()
    assert window.isVisible()
    assert "不可用" in window._status_bar.currentMessage()


def test_tray_menu_and_activation_restore_existing_window(desktop):
    window, lifecycle, _ = desktop()
    window._settings.windows_close_action = WindowCloseAction.TRAY
    for reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
        window.close()
        lifecycle.tray.activated.emit(reason)
        assert window.isVisible()
    actions = lifecycle.tray.menu.actions()
    assert [action.text() for action in actions] == [
        "显示主窗口", "任务中心", "设置", "", "退出 BiliFlow",
    ]
    window.close()
    actions[1].trigger()
    assert window.isVisible() and window._workspace_pages.currentIndex() == 2
    window.close()
    actions[2].trigger()
    assert window.isVisible() and window._workspace_pages.currentIndex() == 3


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_explicit_exit_drains_once_then_ends_app(desktop, qtbot, monkeypatch, platform):
    window, lifecycle, quits = desktop(platform)
    shutdown = Mock(wraps=window._live_controller.shutdown)
    monkeypatch.setattr(window._live_controller, "shutdown", shutdown)
    window._actions["quit"].trigger()
    window.close()
    window.request_quit()
    qtbot.waitUntil(lambda: bool(quits))
    assert window._shutdown_complete and window.isHidden()
    shutdown.assert_called_once()
    assert not window.centralWidget().isEnabled()
    assert not lifecycle.tray or not lifecycle.tray.visible


@pytest.mark.parametrize("task", ["monitor", "record", "export", "download"])
def test_remembered_quit_still_confirms_tasks(desktop, monkeypatch, task):
    window, _, _ = desktop()
    window._settings.windows_close_action = WindowCloseAction.QUIT
    if task == "monitor":
        window._live_controller.service.rows = [room("waiting")]
    elif task == "record":
        window._live_controller.service.rows = [room("recording")]
    elif task == "export":
        window._live_controller.exporting = True
    else:
        window._download_list._workers[10] = Mock()
    prompts = []

    def cancel(box):
        prompts.append(box.button(QMessageBox.Yes).text())
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    try:
        window.close()
        assert prompts == ["停止任务并退出"]
        assert window.isVisible() and not window._quit_requested
        assert not window._live_controller._closed
    finally:
        window._download_list._workers.clear()


def test_dialog_exit_is_already_confirmed_and_remembered(desktop, monkeypatch):
    window, _, _ = desktop()
    window._live_controller.service.rows = [room("waiting")]
    choose(monkeypatch, CloseWindowDialog.QUIT, remember=True)
    window.close()
    assert window._quit_requested
    assert window._config.load().windows_close_action == WindowCloseAction.QUIT


def test_cancel_unsaved_draft_cancels_exit_without_remembering(desktop, monkeypatch):
    window, _, _ = desktop()
    window._settings_page._path_template.setText("draft/{title}")
    choose(monkeypatch, CloseWindowDialog.QUIT, remember=True)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.Cancel)
    window.close()
    assert not window._quit_requested and window._settings_page.dirty
    assert window._config.load().windows_close_action == WindowCloseAction.ASK


def test_native_application_quit_is_routed_even_with_hidden_window(desktop, qtbot):
    window, lifecycle, quits = desktop("darwin")
    lifecycle.hide_window()
    event = QEvent(QEvent.Quit)
    QCoreApplication.sendEvent(lifecycle.app, event)
    assert not event.isAccepted()
    qtbot.waitUntil(lambda: bool(quits))
    assert window._shutdown_complete


def test_hidden_exit_confirmation_restores_parent_and_can_cancel(desktop, monkeypatch):
    window, lifecycle, _ = desktop("darwin")
    window._live_controller.service.rows = [room("waiting")]
    lifecycle.hide_window()
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.No)
    assert not window.request_quit()
    assert window.isVisible() and not window._quit_requested


def test_updates_and_minimize_do_not_use_close_policy(desktop, qtbot, monkeypatch):
    window, lifecycle, quits = desktop()
    window._settings.windows_close_action = WindowCloseAction.TRAY
    window.showMinimized()
    assert window.isMinimized() and not window.isHidden()
    lifecycle.restore_window()
    window._update_in_progress = True
    window.close()
    assert window.isVisible() and not window._quit_requested
    window._update_ready_to_close = True
    window.request_quit(confirmed=True, reason="update")
    qtbot.waitUntil(lambda: bool(quits))
    assert window._shutdown_complete


def test_auto_update_offer_waits_until_window_restored(desktop, qtbot, monkeypatch):
    from tests.test_update_gui import RELEASE

    window, lifecycle, _ = desktop("darwin")
    offers = []
    monkeypatch.setattr("bilibili_downloader.gui.main_window.UpdateDialog.exec",
                        lambda _: offers.append(True))
    lifecycle.hide_window()
    window._on_update_available(RELEASE)
    assert not offers and window.isHidden()
    lifecycle.restore_window()
    qtbot.waitUntil(lambda: bool(offers))
    lifecycle.restore_window()
    assert len(offers) == 1


def test_settings_save_applies_new_close_behavior(desktop):
    window, lifecycle, _ = desktop()
    panel = window._settings_page
    control = panel._controls["windows_close_action"]
    control.setCurrentIndex(control.findData(WindowCloseAction.TRAY))
    assert window._save_settings()
    window.close()
    assert window.isHidden()
    lifecycle.restore_window()
    control.setCurrentIndex(control.findData(WindowCloseAction.ASK))
    assert window._save_settings()
    assert window._config.load().windows_close_action == WindowCloseAction.ASK


def test_close_dialog_keyboard_defaults_cancel_and_task_label(qtbot):
    dialog = CloseWindowDialog(active=True)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.tray_button.isDefault() and not dialog.quit_button.isDefault()
    assert not dialog.remember.isChecked()
    assert dialog.quit_button.text() == "停止并退出"
    qtbot.keyClick(dialog, Qt.Key_Escape)
    assert dialog.result() == CloseWindowDialog.CANCEL
    dialog.show()
    qtbot.keyClick(dialog, Qt.Key_Return)
    assert dialog.result() == CloseWindowDialog.TRAY


def test_exit_waits_for_worker_and_recording_finalization(desktop, qtbot, monkeypatch):
    window, _, quits = desktop()
    service = window._live_controller.service
    service.stopped = False
    gate, started = Event(), Event()

    class Job(QRunnable):
        def run(self):
            started.set()
            gate.wait(5)

    client_close = Mock(wraps=window._api_client.close)
    monkeypatch.setattr(window._api_client, "close", client_close)
    window._service_pool.start(Job())
    assert started.wait(1)
    try:
        window.request_quit(confirmed=True)
        window.close()
        qtbot.wait(120)
        assert not window._shutdown_complete and not quits
        client_close.assert_not_called()
        service.stopped = True
        qtbot.wait(120)
        assert not window._shutdown_complete
    finally:
        service.stopped = True
        gate.set()
    qtbot.waitUntil(lambda: bool(quits))
    client_close.assert_called_once()


def test_tray_restores_maximized_state(desktop):
    window, lifecycle, _ = desktop()
    window.showMaximized()
    lifecycle.hide_window()
    lifecycle.restore_window()
    assert window.isMaximized()


def test_update_offer_during_exit_confirmation_is_deferred(desktop, monkeypatch):
    from tests.test_update_gui import RELEASE

    window, _, _ = desktop()
    window._live_controller.service.rows = [room("waiting")]
    offers = Mock()
    monkeypatch.setattr("bilibili_downloader.gui.main_window.UpdateDialog.exec", offers)

    def cancel(box):
        window._on_update_available(RELEASE)
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    assert not window.request_quit()
    offers.assert_not_called()
    assert window._deferred_update is RELEASE


@pytest.mark.parametrize("platform", ["darwin", "win32"])
@pytest.mark.parametrize("reason", ["user", "update"])
def test_real_event_loop_process_exits_after_hiding(qapp, tmp_path, platform, reason):
    source = '''
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from bilibili_downloader.core.models import WindowCloseAction
from bilibili_downloader.gui.lifecycle import ApplicationLifecycle
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.utils.config import ConfigManager
from tests.test_lifecycle import TrayStub
from tests.test_workspaces import StubService
app = QApplication([])
config = ConfigManager(Path(sys.argv[1]) / "config.json")
controller = LiveUiController(config, service_factory=StubService)
window = MainWindow(config, live_controller=controller, desktop_platform=sys.argv[2])
lifecycle = ApplicationLifecycle(app, window, desktop_platform=sys.argv[2], tray_factory=TrayStub)
window._settings.windows_close_action = WindowCloseAction.TRAY
window.show()
# Let the platform deliver its startup activation before simulating a close.
QTimer.singleShot(100, window.close)
def quit_after_hide():
    assert window.isHidden() and not window._shutdown_started
    if sys.argv[3] == "update":
        window._update_in_progress = True
        window._update_ready_to_close = True
        window.request_quit(confirmed=True, reason="update")
    else:
        window._actions["quit"].trigger()
QTimer.singleShot(200, quit_after_hide)
QTimer.singleShot(3000, lambda: app.exit(19))
code = app.exec()
assert code == 0 and window._shutdown_complete
assert not lifecycle.tray or not lifecycle.tray.visible
print("shutdown-complete")
'''
    result = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path), platform, reason],
        env={**os.environ, "QT_QPA_PLATFORM": qapp.platformName()},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "shutdown-complete" in result.stdout
