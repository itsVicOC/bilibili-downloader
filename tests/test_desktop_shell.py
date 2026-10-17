import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QToolBar

from bilibili_downloader.core.models import TaskStatus
from tests.test_visual_layout import _add_task, _make_window


def test_toolbar_follows_workspace_and_preserves_source_and_selection(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    window.show()
    window._url_input.setText("BV1DEMO00001")
    for index, title in enumerate(("视频下载", "直播录制", "任务中心", "设置")):
        window._workspace_actions[index].trigger()
        assert window._header_stack.currentWidget().title.text() == title
        assert window._workspace_pages.currentIndex() == index
        assert window._workspace_actions[index].isChecked()
    assert window._url_input.text() == "BV1DEMO00001"
    toolbar = window.findChild(QToolBar, "WorkspaceToolbar")
    assert not toolbar.isMovable() and not toolbar.isFloatable()
    assert window._actions["settings"].menuRole() == QAction.PreferencesRole
    assert window._actions["quit"].menuRole() == QAction.QuitRole
    assert window._actions["about"].menuRole() == QAction.AboutRole


def test_focus_source_shortcut_navigates_once_and_selects_source(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    window._url_input.setText("BV1DEMO00001")
    window._show_workspace(2)
    qtbot.keySequence(window, window._actions["focus_source"].shortcut())
    QApplication.processEvents()
    assert window._workspace_pages.currentIndex() == 0
    assert window._url_input.hasFocus()
    assert window._url_input.selectedText() == "BV1DEMO00001"


def test_multiline_enter_and_input_method_commit_do_not_enqueue(qtbot, tmp_path):
    from PySide6.QtGui import QInputMethodEvent
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    window.show()
    window._show_workspace(0)
    window._download_tabs.setCurrentIndex(1)
    editor = window._batch_page._url_text
    editor.setFocus()
    event = QInputMethodEvent()
    event.setCommitString("测试来源")
    QApplication.sendEvent(editor, event)
    qtbot.keyClick(editor, Qt.Key_Return)
    assert editor.toPlainText() == "测试来源\n"
    assert not window._download_list._states


def test_bulk_actions_only_enable_for_eligible_tasks(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    buttons = window._task_page._bulk_buttons
    assert not any(button.isEnabled() for button in buttons)
    _add_task(window, 1, TaskStatus.PAUSED)
    window._task_page.refresh_downloads()
    assert [button.isEnabled() for button in buttons] == [False, True, False]
    _add_task(window, 2, TaskStatus.COMPLETED)
    _add_task(window, 3, TaskStatus.DOWNLOADING)
    window._task_page.refresh_downloads()
    assert all(button.isEnabled() for button in buttons)


def test_cancelled_navigation_keeps_current_menu_selection_and_draft(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    window._show_workspace(3)
    window._settings_page._output_dir.setText("/edited/path")
    monkeypatch.setattr(QMessageBox, "exec", lambda box: QMessageBox.Cancel)
    window._workspace_actions[0].trigger()
    assert window._workspace_pages.currentIndex() == 3
    assert [item.isChecked() for item in window._workspace_actions] == [False, False, False, True]
    assert window._settings_page._output_dir.text() == "/edited/path"
    window._settings_page.load_settings(window._settings)


@pytest.mark.parametrize("status,enabled", [
    (TaskStatus.MERGING, [True, False, False]),
    (TaskStatus.FAILED, [False, True, False]),
    (TaskStatus.CANCELLED, [False, True, False]),
])
def test_bulk_controls_cover_merging_failed_and_cancelled(qtbot, tmp_path, status, enabled):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    _add_task(window, 1, status)
    window._task_page.refresh_downloads()
    assert [button.isEnabled() for button in window._task_page._bulk_buttons] == enabled


def test_update_isolation_disables_native_toolbar_menus_and_shortcuts(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    window._set_shell_enabled(False)
    window._sync_edit_actions()
    assert not window._workspace_toolbar.isEnabled()
    assert not window.menuBar().isEnabled()
    assert not any(item.isEnabled() for item in window._actions.values())
    assert not window._show_workspace(2)
    window._set_shell_enabled(True)
    assert window._actions["focus_source"].isEnabled()
    assert window._show_workspace(2)
