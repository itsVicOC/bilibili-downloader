"""Content, focus and action regressions for the third Fluent refinement."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QBoxLayout, QPushButton

from bilibili_downloader.core.models import (
    DownloadItem,
    OutputMode,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.download_list import DownloadListWidget
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(6):
        QApplication.processEvents()


def resolve(window, title="城市夜航"):
    window._url_input.setText("BV1DEMO2026A")
    window._on_resolve_success(VideoInfo(bvid="BV1DEMO2026A", title=title), [], [], True)


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_resolved_download_is_complete_in_standard_window(workspace, qapp, theme_id, dark):
    theme = ThemeManager(qapp, theme_id, "dark" if dark else "light")
    resolve(workspace)
    workspace.resize(1320, 860)
    workspace.show()
    flush()
    assert workspace._resolve_btn.text() == "重新解析"
    assert workspace._hero.height() < 90
    assert workspace._video_info.height() < 170
    assert workspace._workspace_scroll.verticalScrollBar().maximum() == 0
    for control in (workspace._video_info, workspace._page_combo, workspace._quality_combo,
                    workspace._codec_combo, workspace._output_summary,
                    workspace._danmaku_check, workspace._subtitle_check,
                    workspace._all_subtitles_check, workspace._cover_check,
                    workspace._metadata_check, workspace._download_btn):
        assert control.visibleRegion().boundingRect().contains(control.rect())
    theme.deleteLater()


def test_reflow_uses_viewport_and_preserves_controls_selection_and_audio_mode(workspace):
    resolve(workspace, "非常长的作品标题🌠" * 35)
    workspace._output_mode_combo.setCurrentIndex(workspace._output_mode_combo.findData(OutputMode.AUDIO))
    workspace._danmaku_check.setChecked(True)
    original = tuple(workspace._download_fields._rows)
    workspace.show()
    flush()
    workspace._output_summary.setSelection(2, 5)
    selected = workspace._output_summary.selectedText()
    for size in ((1320, 860), (900, 640), (1120, 760), (1320, 860)):
        workspace.resize(*size)
        flush()
        split = workspace._output_sections
        wide = split.width() >= UI_METRICS.output_split_width
        assert split.row.direction() == (QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
        assert workspace._download_fields._columns == (2 if workspace._download_fields.width() >= 440 else 1)
        assert tuple(workspace._download_fields._rows) == original
        assert workspace._output_summary.selectedText() == selected
        assert workspace._codec_stack.currentWidget() is workspace._audio_combo
        assert not workspace._quality_combo.isEnabled()
        assert workspace._danmaku_check.isChecked()
        assert workspace._workspace_scroll.horizontalScrollBar().maximum() == 0
        title = workspace._video_info._title_label
        assert title.height() <= title.fontMetrics().lineSpacing() * 2
        assert title.toolTip() == "非常长的作品标题🌠" * 35
        # Painting very long UTF-16 text must not split an emoji surrogate pair.
        assert not title.grab().isNull()


@pytest.mark.parametrize("mode", [OutputMode.VIDEO, OutputMode.AUDIO])
def test_directory_precedes_extras_in_keyboard_order(workspace, qtbot, mode):
    resolve(workspace)
    workspace._output_mode_combo.setCurrentIndex(workspace._output_mode_combo.findData(mode))
    workspace.show()
    flush()
    codec = workspace._codec_stack.currentWidget()
    codec.setFocus()
    qtbot.keyClick(codec, Qt.Key_Tab)
    assert QApplication.focusWidget() is workspace._output_summary
    qtbot.keyClick(workspace._output_summary, Qt.Key_Tab)
    assert QApplication.focusWidget() is workspace._danmaku_check


def test_settings_bar_stays_compact_and_actions_remain_visible(workspace):
    workspace.resize(900, 640)
    workspace._show_workspace(3)
    workspace.show()
    flush()
    panel = workspace._settings_page
    before = panel._action_bar.geometry()
    panel._path_template.setText("draft/{title}")
    flush()
    assert panel.dirty
    assert panel._action_bar.geometry() == before
    assert before.height() == UI_METRICS.settings_bar_height
    for control in (panel._draft_label, panel._reset_btn, panel._save_btn):
        rect = QRect(control.mapTo(panel._action_bar, QPoint()), control.size())
        assert panel._action_bar.rect().contains(rect)
    panel.load_settings(panel._settings)


def test_row_menu_retains_task_identity_after_row_removal(qtbot):
    table = DownloadListWidget()
    qtbot.addWidget(table)
    deleted, retried = [], []
    table.delete_requested.connect(deleted.append)
    table.retry_requested.connect(retried.append)
    for task_id in (10, 20):
        table.add_item(DownloadItem(video_info=VideoInfo(bvid=f"BV{task_id}")),
                       download_id=task_id, status=TaskStatus.FAILED)
    table.remove_item(10)
    controls = table.cellWidget(0, 4).findChildren(QPushButton)
    assert [button.text() for button in controls] == ["重试", "更多"]
    controls[0].click()
    controls[1].menu().actions()[0].trigger()
    assert retried == deleted == [20]


def test_bulk_more_action_keeps_current_filter_scope_and_toolbar_can_wrap(workspace):
    page = workspace._task_page
    for task_id, state in ((1, TaskStatus.COMPLETED), (2, TaskStatus.PAUSED)):
        workspace._download_list.add_item(DownloadItem(video_info=VideoInfo(bvid=f"BV{task_id}")),
                                          download_id=task_id, status=state)
    page.filter.setCurrentIndex(page.filter.findData("paused"))
    page.refresh_downloads()
    assert not page._clear_completed_action.isEnabled()
    page.scope.setCurrentIndex(page.scope.findData("all"))
    assert page._clear_completed_action.isEnabled()
    called = []
    page.clear_completed_requested.connect(lambda: called.append(True))
    page._clear_completed_action.trigger()
    assert called == [True]
    assert 1 not in workspace._download_list._states
    assert 2 in workspace._download_list._states
    workspace._show_workspace(2)
    workspace.show()
    flush()
    bar = page._download_tools
    # Exercise wrapping independently of the main window's 900px minimum.
    bar.setFixedWidth(540)
    flush()
    assert bar.wrapped
    assert bar._actions.y() > bar._filters.y()
    for button in bar.findChildren(QPushButton):
        rect = QRect(button.mapTo(bar, QPoint()), button.size())
        assert bar.rect().contains(rect)
