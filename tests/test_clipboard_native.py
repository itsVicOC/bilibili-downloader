"""Real platform clipboard and window activation; no background parser requests."""

import pytest
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtWidgets import QApplication

from bilibili_downloader.gui.clipboard_controller import ClipboardController
from tests.test_workspaces import workspace as workspace


def test_native_clipboard_preexisting_hide_restore_and_confirmation(workspace, qtbot, qapp, monkeypatch):
    if qapp.platformName() not in {'windows', 'cocoa'}:
        pytest.skip('Requires a Windows or Cocoa desktop clipboard')
    clipboard = QApplication.clipboard()
    original = QMimeData()
    mime = clipboard.mimeData()
    if mime is not None:
        for name in mime.formats():
            original.setData(name, mime.data(name))
    calls = []
    monkeypatch.setattr(workspace._service_pool, 'start', lambda runner: calls.append(runner))
    clipboard.setText('BV1GJ411x7h7')
    manager = ClipboardController(workspace)
    workspace._clipboard = manager
    try:
        workspace.show()
        workspace.raise_()
        workspace.activateWindow()
        qtbot.waitUntil(lambda: qapp.applicationState() == Qt.ApplicationActive and workspace.isActiveWindow(), timeout=5000)
        qtbot.waitUntil(manager.prompt.isVisible, timeout=5000)
        assert calls == [] and workspace._url_input.text() == ''
        manager.dismiss()
        workspace.hide()
        clipboard.setText('ep123')
        manager.check()
        assert not manager.prompt.isVisible()
        workspace.show()
        workspace.raise_()
        workspace.activateWindow()
        qtbot.waitUntil(manager.prompt.isVisible, timeout=5000)
        assert manager.candidate.sources == ('ep123',)
        manager.prompt.confirm.click()
        assert len(calls) == 1 and workspace._url_input.text() == 'ep123'
    finally:
        manager.dispose()
        workspace._clipboard = None
        clipboard.setMimeData(original)
