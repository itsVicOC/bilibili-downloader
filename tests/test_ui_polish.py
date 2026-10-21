"""Content-level layout regressions for the desktop UI audit fixes."""

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTableWidget

from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.models import (
    AppSettings,
    StreamInfo,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.settings_sections import SettingsSection
from bilibili_downloader.gui.threads.batch_worker import ImportIssue, ImportReport
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_visual_layout import _add_task
from tests.test_workspaces import room
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(4):
        QApplication.processEvents()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("size", [(900, 640), (1120, 760), (1320, 860)])
def test_empty_download_guidance_is_complete_and_does_not_overlap(workspace, qapp, theme_id, dark, size):
    manager = ThemeManager(qapp, theme_id=theme_id, mode="dark" if dark else "light")
    workspace.resize(*size)
    workspace.show()
    flush()
    hero = workspace._hero
    hint = workspace._empty_download.findChild(QLabel)
    link = workspace._empty_download.findChild(QPushButton)
    controls = (workspace._hero_title, workspace._url_input, workspace._resolve_btn, hint, link)
    bounds = [QRect(control.mapTo(hero, QPoint()), control.size()) for control in controls]
    for control, rect in zip(controls, bounds):
        assert hero.rect().adjusted(8, 8, -8, -8).contains(rect)
        assert control.visibleRegion().boundingRect().contains(control.rect())
    assert bounds[0].bottom() < bounds[1].top()
    assert max(bounds[1].bottom(), bounds[2].bottom()) < min(bounds[3].top(), bounds[4].top())
    text = hint.fontMetrics().boundingRect(hint.contentsRect(), int(Qt.TextWordWrap), hint.text())
    assert text.height() <= hint.height()
    assert workspace._download_actions.visibleRegion().boundingRect().contains(workspace._download_actions.rect())
    manager.deleteLater()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("size", [(900, 640), (1120, 760), (1320, 860)])
def test_all_option_card_content_survives_small_viewports(workspace, qapp, theme_id, dark, size):
    manager = ThemeManager(qapp, theme_id=theme_id, mode="dark" if dark else "light")
    workspace.resize(*size)
    workspace.show()
    workspace._on_resolve_success(VideoInfo(bvid="BV1DEMO", title="演示作品"), [StreamInfo(id=80, codecid=12)], [], True)
    flush()
    cards = (workspace._danmaku_check, workspace._subtitle_check, workspace._cover_check, workspace._metadata_check)
    for card in cards:
        workspace._workspace_scroll.ensureWidgetVisible(card, 0, 8)
        flush()
        assert card.height() == UI_METRICS.option_card_height
        assert card.height() >= 36 + card.fontMetrics().height() + 4
        assert card.width() >= card.fontMetrics().horizontalAdvance(card.text()) + 24
        assert card.visibleRegion().boundingRect().contains(card.rect())
    workspace._workspace_scroll.ensureWidgetVisible(workspace._all_subtitles_check, 0, 8)
    flush()
    assert workspace._all_subtitles_check.visibleRegion().boundingRect().contains(workspace._all_subtitles_check.rect())
    manager.deleteLater()


@pytest.mark.parametrize("state", ["initial", "generated", "expired", "network-error"])
def test_switch_login_keeps_whole_qr_visible(qtbot, qapp, state):
    manager = ThemeManager(qapp, mode="light")
    dialog = LoginDialog("original", account={"uname": "演示用户", "mid": 123}, account_valid=True)
    qtbot.addWidget(dialog)
    dialog._show_login_methods()
    if state != "initial":
        dialog._generate_btn.hide()
        dialog._on_qr_generated("unused", "demo", Image.new("RGB", (220, 220), "white"))
        dialog._poll_timer.stop()
    if state == "expired":
        dialog._on_qr_status_result({"status": 86038})
    if state == "network-error":
        dialog._on_qr_status_error("离线错误" * 80)
    dialog.show()
    flush()
    qr = dialog._qr_label
    assert qr.visibleRegion().boundingRect().contains(qr.rect())
    assert dialog.rect().contains(QRect(qr.mapTo(dialog, QPoint()), qr.size()))
    assert dialog.height() <= 640
    assert dialog._back_button.mapTo(dialog, QPoint()).y() == dialog._close_button.y()
    dialog._back_button.click()
    assert dialog.get_auth_cookies() == {"SESSDATA": "original"}
    assert dialog._tabs.isHidden()
    manager.deleteLater()


def test_failed_parse_invalidates_old_result_and_explains_disabled_action(workspace):
    workspace._on_resolve_success(VideoInfo(bvid="BV1DEMO", title="旧作品"), [], [], True)
    workspace._on_resolve_error("网络异常")
    assert workspace._current_video is None
    assert not workspace._download_btn.isEnabled()
    assert workspace._download_actions.status.text() == "解析失败"
    assert "重新解析" in workspace._download_hint.toolTip()
    assert workspace._video_info._state_label.text() == "结果已失效"


def test_live_details_stay_beside_list_then_collapse_in_narrow_window(workspace):
    page = workspace._live_page
    workspace._live_controller.service.rows = [room()]
    workspace._live_controller.refresh()
    workspace._show_workspace(1)
    workspace.resize(1120, 760)
    workspace.show()
    flush()
    page.select_room(1)
    flush()
    assert not page._stacked_details
    assert page._detail_card.x() > page._rooms_card.x()
    assert page._detail_controls.isVisible()
    workspace.resize(900, 640)
    flush()
    assert page._stacked_details
    assert page._detail_controls.isHidden()
    page._detail_toggle.click()
    assert page._detail_controls.isVisible()
    assert page._action_bar.isVisible()


def test_advanced_templates_keep_draft_and_open_for_validation(qtbot):
    panel = SettingsDialog(AppSettings())
    qtbot.addWidget(panel)
    panel.resize(760, 600)
    panel.show()
    assert panel._templates_section.content.isHidden()
    panel._path_template.setText("{author}/新目录/{title}")
    assert "新目录" in panel._template_previews["path_template"].text()
    panel.show_section(SettingsSection.DOWNLOAD)
    panel.show_section(SettingsSection.DOWNLOAD)
    assert panel.dirty
    assert panel._path_template.text() == "{author}/新目录/{title}"
    panel._path_template.setText("../invalid")
    assert not panel.validate()
    flush()
    assert not panel._templates_section.content.isHidden()
    assert panel._field_rows["path_template"].error.text()
    assert panel._path_template.visibleRegion().boundingRect().contains(panel._path_template.rect())


def test_tool_results_are_local_and_do_not_save_drafts(qtbot, monkeypatch):
    panel = SettingsDialog(AppSettings())
    qtbot.addWidget(panel)
    monkeypatch.setattr("bilibili_downloader.gui.dialogs.settings_dialog.QThreadPool.globalInstance", lambda: type("Pool", (), {"start": lambda *_: None})())
    buttons = {b.accessibleName(): b for b in panel.findChildren(QPushButton)}
    panel._probe("ffmpeg", buttons["检查 FFmpeg"])
    panel._probe("recorder", buttons["检查录制引擎"])
    panel._ffmpeg_path.setText("/changed")
    panel._probes["ffmpeg"][0].finished.emit(True, "旧路径可用")
    panel._probes["recorder"][0].finished.emit(False, "引擎不可用")
    assert "路径已修改" in panel._probe_notices["ffmpeg"].label.text()
    assert panel._probe_notices["ffmpeg"].property("tone") == "warning"
    assert panel._probe_notices["recorder"].label.text() == "引擎不可用"
    assert panel._settings.ffmpeg_path == ""
    assert panel.dirty


def test_task_summary_separates_identity_status_and_path(workspace):
    _add_task(workspace, 1, TaskStatus.FAILED)
    workspace._download_list._output_paths[1] = "/tmp/演示作品.mp4"
    workspace._download_list.selectRow(0)
    workspace._task_page.refresh_downloads()
    detail = workspace._task_page.download_detail
    assert detail.title.toolTip()
    assert detail.status.text()
    assert detail.path.toolTip() == "保存位置：/tmp/演示作品.mp4"
    assert "保存位置" in detail.toPlainText()
    assert detail.details_button.isEnabled()


def test_background_gallery_switches_views_without_losing_selection(workspace, qtbot):
    gallery = BackgroundGallery(workspace._settings_page._background_pickers["download"])
    qtbot.addWidget(gallery)
    gallery.resize(720, 540)
    gallery.show()
    flush()
    assert gallery.tabs.isVisible() and gallery._preview_pane.isHidden()
    gallery.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
    qtbot.waitUntil(lambda: not gallery.busy)
    gallery._view_buttons["preview"].click()
    assert gallery._preview_pane.isVisible() and gallery.tabs.isHidden()
    reference = gallery.reference
    gallery.resize(1080, 720)
    flush()
    assert gallery._preview_pane.isVisible() and gallery.tabs.isVisible()
    assert gallery.reference == reference
    assert not workspace._settings_page.dirty


def test_failure_details_prioritize_reason_and_keep_copy_link(qtbot, monkeypatch):
    panel = BatchDialog()
    qtbot.addWidget(panel)
    reason = "来源已失效或当前账号没有访问权限，请检查后重试。"
    panel._report = ImportReport([], [ImportIssue("来源", reason, "https://example.com/demo", "作品", "item")])
    def inspect(dialog):
        dialog.show()
        flush()
        table = dialog.findChild(QTableWidget)
        assert table.columnWidth(1) > table.columnWidth(0)
        assert table.wordWrap()
        assert table.item(0, 1).text() == reason
        assert table.cellWidget(0, 2).toolTip() == "https://example.com/demo"
        dialog.hide()
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec", inspect)
    panel._show_errors()
