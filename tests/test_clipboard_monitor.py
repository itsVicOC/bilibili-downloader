"""Foreground clipboard offers never start work or replace drafts implicitly."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMimeData, QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog

from bilibili_downloader.core.models import AppSettings, VideoInfo
from bilibili_downloader.gui.clipboard_controller import ClipboardController
from tests.test_workspaces import workspace as workspace


class Clipboard(QObject):
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self.mime = QMimeData()
        self.reads = 0

    def set(self, text):
        self.mime.setText(text)
        self.dataChanged.emit()

    def mimeData(self):
        self.reads += 1
        return self.mime

    def text(self):
        self.reads += 1
        return self.mime.text()


@pytest.fixture
def monitor(workspace, qtbot, monkeypatch):
    workspace.show()
    focus = SimpleNamespace(active=True)
    clipboard = Clipboard()
    clipboard.set('BV1GJ411x7h7')  # Copied before the monitoring object exists.
    calls = []
    monkeypatch.setattr(workspace._service_pool, 'start', lambda runner: calls.append(runner))
    manager = ClipboardController(workspace, clipboard=clipboard,
                                  foreground=lambda: focus.active and workspace.isVisible() and not workspace.isMinimized())
    workspace._clipboard = manager
    yield manager, clipboard, focus, calls
    manager.dispose()
    workspace._clipboard = None


def test_preexisting_clipboard_is_offered_without_mutation_or_network(monitor, workspace, qtbot):
    manager, clipboard, _, calls = monitor
    before = workspace._url_input.text()
    qtbot.waitUntil(manager.prompt.isVisible)
    assert clipboard.reads > 0
    assert workspace._url_input.text() == before
    assert calls == []
    manager.prompt.confirm.click()
    manager.prompt.confirm.click()
    assert workspace._url_input.text() == 'BV1GJ411x7h7'
    assert len(calls) == 1
    assert workspace._current_video is None
    assert not workspace._download_btn.isEnabled()


def test_background_activation_and_ignore_deduplication(monitor):
    manager, clipboard, focus, _ = monitor
    focus.active = False
    clipboard.reads = 0
    clipboard.set('ep123')
    manager.check()
    assert clipboard.reads == 0 and not manager.prompt.isVisible()
    focus.active = True
    manager.check()
    assert manager.prompt.isVisible()
    manager.dismiss()
    manager.check()
    assert not manager.prompt.isVisible()
    clipboard.set('ordinary text')
    manager.check()
    clipboard.set('ep123')
    manager.check()
    assert manager.prompt.isVisible()


def test_confirm_uses_displayed_snapshot_and_one_request(monitor, workspace):
    manager, clipboard, _, calls = monitor
    manager.check()
    clipboard.mime.setText('ep123')  # Change after presentation, before a queued notification.
    manager.confirm()
    assert workspace._url_input.text() == 'BV1GJ411x7h7'
    assert len(calls) == 1


def test_existing_content_is_replaced_only_after_confirmation(monitor, workspace):
    manager, _, _, calls = monitor
    workspace._url_input.setText('av170001')
    workspace._on_resolve_success(VideoInfo(bvid='old', title='old result'), [], [], True)
    manager.check()
    assert manager.prompt.confirm.text() == '替换并解析'
    assert workspace._current_video.title == 'old result'
    assert not calls
    manager.confirm()
    assert workspace._current_video is None and len(calls) == 1


def test_editing_source_updates_replacement_warning_without_reading_clipboard(monitor, workspace):
    manager, clipboard, _, calls = monitor
    manager.check()
    assert manager.prompt.confirm.text() == '解析'
    reads = clipboard.reads
    workspace._url_input.setText('av170001')
    assert manager.prompt.confirm.text() == '替换并解析'
    assert clipboard.reads == reads and not calls


def test_idle_prompt_settles_without_clipboard_polling(monitor, qtbot):
    manager, clipboard, _, _ = monitor
    qtbot.waitUntil(manager.prompt.isVisible)
    qtbot.wait(350)  # Allow the one show-event debounce to settle.
    reads = clipboard.reads
    qtbot.wait(400)
    assert clipboard.reads == reads
    assert not manager.timer.isActive()


def test_multiple_inputs_go_directly_to_batch_after_confirmation(monitor, workspace, monkeypatch):
    manager, clipboard, _, calls = monitor
    batch = workspace._batch_page
    started = []
    monkeypatch.setattr(batch, '_start_resolve', lambda: started.append(batch._url_text.toPlainText()))
    clipboard.set('分享 BV1GJ411x7h7\nep123')
    manager.check()
    assert manager.prompt.confirm.text() == '批量解析'
    manager.confirm()
    assert workspace._download_tabs.currentIndex() == 1
    assert started == ['BV1GJ411x7h7\nep123']
    assert not calls


def test_confirmed_short_link_routes_to_batch_without_another_prompt(monitor, workspace, monkeypatch):
    manager, clipboard, _, calls = monitor
    started = []
    monkeypatch.setattr(workspace._batch_page, '_start_resolve', lambda: started.append(workspace._batch_page._url_text.toPlainText()))
    clipboard.set('https://b23.tv/AbCd123')
    manager.check()
    manager.confirm()
    assert len(calls) == 1
    workspace._resolve_worker.routed.emit('batch', 'ss123')
    assert started == ['ss123']
    assert workspace._download_tabs.currentIndex() == 1


def test_live_short_link_is_not_added_to_monitoring(monitor, workspace):
    manager, clipboard, _, _ = monitor
    clipboard.set('https://b23.tv/AbCd123')
    manager.check()
    manager.confirm()
    workspace._resolve_worker.routed.emit('live', 'https://live.bilibili.com/123')
    assert workspace._workspace_pages.currentIndex() == 0
    assert '直播间' in workspace._resolve_notice.label.text()
    assert workspace._live_controller.service.commands == []


def test_busy_resolution_keeps_latest_candidate_without_queueing(monitor, workspace, qtbot):
    manager, clipboard, _, calls = monitor
    manager.check()
    manager.confirm()
    clipboard.set('ep123')
    manager.check()
    assert manager.prompt.isVisible() and not manager.prompt.confirm.isEnabled()
    assert len(calls) == 1
    workspace._resolve_worker.finished.emit(VideoInfo(bvid='BV1GJ411x7h7'), [], [], True)
    qtbot.waitUntil(manager.prompt.confirm.isEnabled)
    assert len(calls) == 1
    manager.confirm()
    assert len(calls) == 2 and workspace._url_input.text() == 'ep123'


def test_cancel_leaving_settings_preserves_draft_and_candidate(monitor, workspace, monkeypatch):
    manager, _, _, calls = monitor
    workspace._show_workspace(3)
    workspace._settings_page._path_template.setText('draft/{title}')
    monkeypatch.setattr(workspace, '_can_leave_settings', lambda: False)
    manager.check()
    before = workspace._url_input.text()
    manager.confirm()
    assert workspace._workspace_pages.currentIndex() == 3
    assert workspace._url_input.text() == before
    assert workspace._settings_page.dirty
    assert manager.prompt.isVisible() and not calls


def test_modal_update_and_setting_disable_suspend_monitoring(monitor, workspace, qtbot):
    manager, clipboard, _, _ = monitor
    manager.check()
    dialog = QDialog(workspace)
    qtbot.addWidget(dialog)
    dialog.setModal(True)
    dialog.show()
    clipboard.reads = 0
    manager.check()
    assert clipboard.reads == 0 and not manager.prompt.isVisible()
    dialog.hide()
    workspace._update_in_progress = True
    manager.check()
    assert clipboard.reads == 0
    workspace._update_in_progress = False
    workspace._settings.clipboard_monitor_enabled = False
    manager.settings_changed()
    manager.check()
    assert manager.candidate is None and not manager.timer.isActive()
    workspace._settings.clipboard_monitor_enabled = True
    manager.settings_changed()
    manager.check()
    assert manager.prompt.isVisible()


def test_clipboard_setting_is_a_saved_draft_and_legacy_default_is_enabled(monitor, workspace, monkeypatch):
    manager, _, _, _ = monitor
    assert AppSettings.model_validate({}).clipboard_monitor_enabled
    panel = workspace._settings_page
    panel._clipboard_check.setChecked(False)
    assert panel.dirty and workspace._settings.clipboard_monitor_enabled
    panel.load_settings(workspace._settings)
    assert panel._clipboard_check.isChecked() and not panel.dirty
    panel._clipboard_check.setChecked(False)
    monkeypatch.setattr(workspace._live_page, 'check_engine', lambda: None)
    assert workspace._save_settings()
    assert not workspace._settings.clipboard_monitor_enabled
    assert not workspace._config.load().clipboard_monitor_enabled
    assert manager.candidate is None


def test_existing_edit_menu_does_not_read_clipboard_in_background(monitor, workspace, monkeypatch):
    _, clipboard, focus, _ = monitor
    focus.active = False
    monkeypatch.setattr(QApplication, 'clipboard', lambda: clipboard)
    monkeypatch.setattr('bilibili_downloader.gui.main_window.clipboard_access_allowed', lambda _: False)
    clipboard.reads = 0
    workspace._sync_edit_actions()
    assert clipboard.reads == 0
