"""Height reflow, persistent placement and non-disruptive feedback regressions."""

import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.models import VideoInfo
from bilibili_downloader.gui.window_state import WindowStateStore
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(8):
        QApplication.processEvents()


@pytest.mark.parametrize("size", [(900, 640), (1120, 760)])
def test_compact_download_keeps_core_specs_and_confirmation_visible(workspace, size):
    workspace.resize(*size)
    workspace.show()
    workspace._url_input.setText("BV1DEMO2026A")
    workspace._on_resolve_success(VideoInfo(bvid="BV1DEMO2026A", title="城市夜航"), [], [], True)
    flush()
    assert workspace._density.compact
    controls = [workspace._page_combo, workspace._output_mode_combo, workspace._quality_combo,
                workspace._codec_combo, workspace._download_btn, workspace._output_summary]
    if size[0] == 1120:
        controls += [workspace._metadata_check, workspace._all_subtitles_check]
        assert workspace._workspace_scroll.verticalScrollBar().maximum() == 0
    for control in controls:
        assert control.visibleRegion().boundingRect().contains(control.rect())
    assert workspace._video_info._cover_label.size().width() == 128
    assert workspace._download_actions.height() == 72


def test_density_hysteresis_preserves_selection_focus_and_draft(workspace):
    workspace.show()
    QApplication.setActiveWindow(workspace)
    workspace._url_input.setText("BV1DEMO2026A")
    workspace._url_input.setSelection(2, 4)
    workspace._url_input.setFocus()
    workspace._settings_page._path_template.setText("draft/{title}")
    for height, compact in [(799, True), (810, True), (824, False), (810, False), (799, True)]:
        workspace.resize(1120, height)
        flush()
        assert workspace._density.compact == compact
        assert workspace._url_input.selectedText() == "1DEM"
        assert QApplication.focusWidget() is workspace._url_input
        assert workspace._settings_page._path_template.text() == "draft/{title}"


def test_status_feedback_does_not_change_content_geometry_and_uses_one_callback(workspace):
    workspace.show()
    flush()
    before = workspace._download_tabs.geometry()
    calls = []
    workspace._status_bar.show_feedback("已添加", "查看任务", lambda: calls.append(1))
    workspace._status_bar.show_feedback("已跳过重复", "查看任务", lambda: calls.append(2))
    flush()
    assert workspace._download_tabs.geometry() == before
    workspace._status_bar.action.click()
    assert calls == [2]
    workspace._status_bar.clearMessage()
    assert workspace._status_bar.action.isHidden()


def test_small_work_area_fits_main_window_and_keeps_primary_action(workspace, monkeypatch, tmp_path):
    if QApplication.platformName() != "offscreen":
        pytest.skip("Virtual negative-coordinate desktop uses the offscreen backend")
    area = QRect(-960, 0, 960, 540)
    screen = SimpleNamespace(name=lambda: "test", availableGeometry=lambda: area)
    monkeypatch.setattr("bilibili_downloader.gui.window_state.choose_screen", lambda *_: screen)
    store = WindowStateStore(workspace, tmp_path / "ui-state.json")
    workspace._window_state = store
    store.show_initial()
    flush()
    assert area.contains(workspace.frameGeometry())
    assert workspace._download_btn.visibleRegion().boundingRect().contains(workspace._download_btn.rect())
    assert not workspace.isMinimized()


def test_hidden_window_flushes_without_saving_business_draft(workspace, tmp_path):
    config_before = workspace._config._config_path.read_bytes()
    store = WindowStateStore(workspace, tmp_path / "ui-state.json")
    workspace._window_state = store
    store.show_initial()
    flush()
    workspace._settings_page._path_template.setText("draft/{title}")
    workspace.setWindowState(Qt.WindowMinimized)
    workspace.hide()
    flush()
    assert store.path.exists()
    assert workspace._config._config_path.read_bytes() == config_before
    assert workspace._settings_page.dirty


def test_embedded_settings_remains_inside_workspace_margins(workspace):
    workspace.resize(900, 640)
    workspace.show()
    workspace._show_workspace(3)
    flush()
    panel = workspace._settings_page
    assert not panel.isWindow()
    assert panel.x() == workspace._density.page_margin
    assert panel.y() == workspace._density.page_margin
    assert not panel.property("placementFitted")


def test_long_error_is_scrollable_selectable_and_actions_are_reachable(workspace, qtbot):
    from bilibili_downloader.gui.widgets.components import MessageBox
    text = "完整诊断与长路径：/example/" * 500
    box = MessageBox("操作失败", text, workspace, tone="danger")
    qtbot.addWidget(box)
    box.show()
    flush()
    assert box.reading_area.toPlainText() == text
    assert box.reading_area.isReadOnly()
    box.reading_area.selectAll()
    assert box.reading_area.textCursor().selectedText() == text
    for control in [box.reading_area, *box.buttons()]:
        assert control.visibleRegion().boundingRect().contains(control.rect())


def test_native_main_window_maximize_preserves_its_restore_geometry(workspace, tmp_path, qtbot):
    store = WindowStateStore(workspace, tmp_path / "ui-state.json")
    workspace._window_state = store
    store.show_initial()
    flush()
    store.flush()
    original = json.loads(store.path.read_text())["normal_rect"]
    workspace.showMaximized()
    qtbot.waitUntil(workspace.isMaximized)
    flush()
    store.flush()
    value = json.loads(store.path.read_text())
    assert value["maximized"] and value["normal_rect"] == original
    workspace.showNormal()
    qtbot.waitUntil(lambda: not workspace.isMaximized())
    flush()
    store.flush()
    assert not json.loads(store.path.read_text())["maximized"]
    assert workspace.isVisible()
