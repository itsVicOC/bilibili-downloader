"""Persistence, navigation and authentication boundaries for the refreshed shell."""

import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.settings_sections import SettingsSection
from bilibili_downloader.gui.widgets.download_options import (
    DownloadOptionCard,
    DownloadOptions,
)
from bilibili_downloader.utils.config import ConfigManager
from tests.test_workspaces import avatar_png
from tests.test_workspaces import workspace as workspace


@pytest.fixture(autouse=True)
def restore_theme(qapp):
    previous = (QFont(qapp.font()), QPalette(qapp.palette()), qapp.styleSheet())
    properties = {
        key: qapp.property(key) for key in ("appearanceMode", "darkTheme", "colorTheme")
    }
    yield
    if hasattr(qapp.styleHints(), "unsetColorScheme"):
        qapp.styleHints().unsetColorScheme()
    qapp.setFont(previous[0])
    qapp.setPalette(previous[1])
    qapp.setStyleSheet(previous[2])
    for key, value in properties.items():
        qapp.setProperty(key, value)


@pytest.mark.parametrize("value", [None, [], {}, "auto", 42])
def test_invalid_mode_falls_back_without_resetting_other_preferences(value):
    settings = AppSettings(
        output_dir="/keep", appearance={"mode": value, "theme": "bilibili_blue"}
    )
    assert settings.appearance.mode == "system"
    assert settings.appearance.theme == "bilibili_blue"
    assert settings.output_dir == "/keep"


def test_old_config_and_manual_mode_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"output_dir": "/keep"}))
    config = ConfigManager(path)
    settings = config.load()
    assert settings.appearance.mode == "system"
    settings.appearance.mode = "dark"
    config.save(settings)
    assert ConfigManager(path).load().appearance.mode == "dark"


@pytest.mark.parametrize("mode,dark", [("light", False), ("dark", True)])
def test_manual_mode_ignores_system_notifications(qapp, mode, dark):
    manager = ThemeManager(qapp, mode=mode)
    try:
        manager._on_color_scheme_changed(
            Qt.ColorScheme.Light if dark else Qt.ColorScheme.Dark
        )
        assert manager.is_dark is dark
        assert manager.mode == mode
    finally:
        manager.deleteLater()


def test_returning_to_system_uses_current_preference(qapp, monkeypatch):
    manager = ThemeManager(qapp, mode="light")
    try:
        monkeypatch.setattr(manager, "_system_prefers_dark", lambda: True)
        manager.set_mode("system")
        assert manager.is_dark
        manager._on_color_scheme_changed(Qt.ColorScheme.Light)
        assert not manager.is_dark
    finally:
        manager.deleteLater()


def test_immediate_mode_preserves_invalid_draft_and_survives_revert(workspace):
    panel = workspace._settings_page
    panel._path_template.setText("../unsaved")
    assert workspace._set_appearance_mode("dark")
    assert workspace._settings.appearance.mode == "dark"
    assert panel._path_template.text() == "../unsaved"
    assert panel.dirty
    assert workspace._mode_actions["dark"].isChecked()
    assert panel._mode_buttons.checkedId() == 2
    assert (
        ConfigManager(workspace._config._config_path).load().appearance.mode == "dark"
    )
    panel.load_settings(panel._settings)
    assert not panel.dirty
    assert panel._settings.appearance.mode == "dark"


def test_failed_mode_save_restores_both_controls(workspace, monkeypatch):
    panel = workspace._settings_page
    panel._path_template.setText("draft/{title}")
    previous = workspace._settings.appearance.mode

    def fail(_settings):
        raise OSError("read-only config")

    monkeypatch.setattr(workspace._config, "save", fail)
    panel._mode_buttons.button(2).click()
    assert workspace._settings.appearance.mode == previous
    assert workspace._mode_actions[previous].isChecked()
    assert panel._mode_buttons.checkedId() == 0
    assert panel._path_template.text() == "draft/{title}"
    assert "保存失败" in panel._notice.label.text()


def test_later_save_merges_immediate_mode(workspace):
    panel = workspace._settings_page
    panel._path_template.setText("edited/{title}")
    workspace._set_appearance_mode("dark")
    assert workspace._save_settings()
    assert workspace._settings.path_template == "edited/{title}"
    assert workspace._settings.appearance.mode == "dark"


def test_navigation_and_about_share_stable_settings_destinations(workspace):
    panel = workspace._settings_page
    assert panel.current_section == SettingsSection.DOWNLOAD
    panel._path_template.setText("draft/{title}")
    workspace._on_about_triggered()
    assert workspace._workspace_pages.currentIndex() == 3
    assert panel.current_section == SettingsSection.ABOUT
    workspace._show_settings_tab(SettingsSection.LIVE)
    assert panel.current_section == SettingsSection.LIVE
    assert panel._path_template.text() == "draft/{title}"
    panel.load_settings(panel._settings)
    workspace._show_workspace(0)
    workspace._on_settings_triggered()
    assert panel.current_section == SettingsSection.LIVE


def test_sidebar_groups_settings_above_the_companion(workspace, qtbot):
    workspace.resize(1320, 860)
    workspace.show()
    QApplication.processEvents()
    assert workspace._settings_nav.y() > workspace._tasks_nav.y()
    assert workspace._settings_nav.geometry().bottom() < workspace._mascot_card.y()
    assert workspace._mode_button.geometry().bottom() < workspace._header_login.y()
    workspace.resize(900, 640)
    QApplication.processEvents()
    assert not workspace._mode_button.text()
    assert "跟随系统" in workspace._mode_button.toolTip()


def test_windows_has_no_menu_row_but_keeps_actions(tmp_path, qtbot):
    config = ConfigManager(tmp_path / "config.json")
    window = MainWindow(
        config_manager=config, desktop_platform="win32", startup_paused=True
    )
    qtbot.addWidget(window)
    assert window.menuBar().isHidden()
    assert all(
        window._actions[key] in window.actions()
        for key in ("focus_source", "settings", "login", "quit", "about")
    )


def test_card_whole_surface_and_keyboard_toggle(qtbot):
    card = DownloadOptionCard("下载弹幕", "ASS", "star")
    qtbot.addWidget(card)
    card.resize(180, 76)
    card.show()
    qtbot.mouseClick(card, Qt.LeftButton, pos=QPoint(170, 67))
    assert card.isChecked()
    qtbot.keyClick(card, Qt.Key_Space)
    assert not card.isChecked()
    card.setEnabled(False)
    qtbot.mouseClick(card, Qt.LeftButton, pos=QPoint(15, 15))
    assert not card.isChecked()


def test_download_cards_reflow_without_losing_values(qtbot):
    panel = SettingsDialog(AppSettings())
    qtbot.addWidget(panel)
    grid = panel.findChild(DownloadOptions)
    grid.setParent(None)
    qtbot.addWidget(grid)
    panel._danmaku_check.setChecked(True)
    for width, columns in ((450, 2), (260, 1), (450, 2)):
        grid.resize(width, 250)
        grid.show()
        QApplication.processEvents()
        assert grid._columns == columns
        assert panel._danmaku_check.isChecked()
    panel._subtitle_check.setChecked(False)
    assert not panel._all_subtitles_check.isEnabled()
    panel._all_subtitles_check.setChecked(True)
    assert panel._subtitle_check.isChecked()
    panel._subtitle_check.setChecked(False)
    assert not panel.get_settings().download_subtitle
    assert not panel.get_settings().download_all_subtitles


def test_account_back_and_closed_dialog_ignore_late_login(qtbot):
    dialog = LoginDialog(
        "original", account={"uname": "演示用户", "mid": 123}, account_valid=True
    )
    qtbot.addWidget(dialog)
    dialog._show_login_methods()
    generation = dialog._generation
    dialog._cookie_input.setText("new draft")
    dialog._show_account()
    called = []
    dialog._deliver(generation, lambda: called.append(True))
    assert not called
    assert dialog.get_auth_cookies() == {"SESSDATA": "original"}
    assert not dialog._cookie_input.text()
    assert dialog._tabs.isHidden()
    dialog._show_login_methods()
    generation = dialog._generation
    dialog.reject()
    dialog._deliver(generation, lambda: called.append(True))
    assert not called


@pytest.mark.parametrize(
    "state,label",
    [
        ("valid", "已登录"),
        ("checking", "正在检查"),
        ("unknown", "暂时无法确认"),
        ("expired", "登录已失效"),
    ],
)
def test_account_status_and_missing_membership(qtbot, state, label):
    dialog = LoginDialog(
        "original",
        account={"uname": "长昵称" * 40, "mid": 123},
        account_valid=True,
        account_state=state,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    QApplication.processEvents()
    assert dialog._account_status.text() == label
    assert dialog._account_member.text() == "会员状态待确认"
    assert dialog._avatar_label.pixmap().width() >= 64
    assert dialog._account_name.height() >= dialog._account_name.fontMetrics().height()
    avatar = dialog._avatar_label.mapTo(dialog, QPoint(0, 0))
    name = dialog._account_name.mapTo(dialog, QPoint(0, 0))
    details = dialog._account_details.mapTo(dialog, QPoint(0, 0))
    assert abs(avatar.x() + 32 - dialog.width() / 2) <= 1
    assert name.y() >= avatar.y() + 64
    assert details.y() >= name.y() + dialog._account_name.height()
    assert abs(details.x() + dialog._account_details.width() / 2 - dialog.width() / 2) <= 1
    assert dialog._account_details.width() <= dialog.width() * 0.6
    for value in (dialog._account_member, dialog._account_status):
        assert value.width() >= value.sizeHint().width()
    assert dialog._account_name.alignment() == Qt.AlignCenter
    assert dialog._title.isHidden() and dialog._caption.isHidden()
    assert dialog._account_detail.isHidden() is (state == "valid")
    assert dialog._account_name.toolTip() == "长昵称" * 40
    assert dialog._account_uid.textInteractionFlags() & Qt.TextSelectableByMouse
    assert dialog._switch_button.mapTo(dialog, QPoint(0, 0)).x() > dialog.width() / 2
    assert dialog._switch_button.mapTo(dialog, QPoint(0, 0)).y() >= details.y() + dialog._account_details.height()


def test_account_overview_restores_layout_after_switching(qtbot):
    dialog = LoginDialog("original", account={"uname": "用户", "mid": 123}, account_valid=True)
    qtbot.addWidget(dialog)
    dialog.show()
    QApplication.processEvents()
    overview_height = dialog.height()
    dialog._switch_button.click()
    assert dialog.windowTitle() == "切换账号"
    assert not dialog._title.isHidden()
    assert dialog._switch_button.isHidden()
    assert not dialog._tabs.isHidden()
    dialog._back_button.click()
    QApplication.processEvents()
    assert dialog.windowTitle() == "当前账号"
    assert dialog._title.isHidden()
    assert not dialog._switch_button.isHidden()
    assert dialog.height() == overview_height
    assert dialog.get_auth_cookies() == {"SESSDATA": "original"}


@pytest.mark.parametrize("width,height", [(900, 640), (1120, 760), (1320, 860)])
def test_compact_header_aligns_with_content_and_keeps_page_actions(workspace, qtbot, width, height):
    workspace.resize(width, height)
    workspace.show()
    QApplication.processEvents()
    assert workspace._sidebar.mapTo(workspace.centralWidget(), QPoint()).y() == 0
    assert workspace._workspace_toolbar.mapTo(workspace.centralWidget(), QPoint()).y() == 0
    assert workspace._workspace_toolbar.mapTo(workspace, QPoint()).x() == workspace._sidebar.width()
    corner = workspace.grab().toImage()
    dpr = corner.devicePixelRatio()
    assert corner.pixelColor(round(4 * dpr), round(55 * dpr)) == corner.pixelColor(round(4 * dpr), round(56 * dpr))
    for index in range(4):
        workspace._show_workspace(index)
        QApplication.processEvents()
        header = workspace._header_stack.currentWidget()
        assert header.height() == 56
        assert header.caption.isHidden()
        assert header.accessibleDescription() == header.caption.text()
        assert header.title.mapTo(workspace, QPoint(0, 0)).x() == workspace._sidebar.width() + 24
    workspace._show_workspace(1)
    header = workspace._header_stack.currentWidget()
    history = header.actions.itemAt(0).widget()
    settings = header.actions.itemAt(1).widget()
    assert history.isVisible() and settings.isVisible()
    assert settings.geometry().right() <= header.width() - workspace._chrome.header_margins[2]
    qtbot.mouseClick(history, Qt.LeftButton)
    assert workspace._workspace_pages.currentIndex() == 2
    assert workspace._task_page.tabs.currentIndex() == 2
    workspace._show_workspace(1)
    qtbot.mouseClick(settings, Qt.LeftButton)
    assert workspace._settings_page.current_section == SettingsSection.LIVE


def test_header_blank_space_drags_and_double_clicks_without_affecting_actions(workspace, qtbot, monkeypatch):
    workspace.show()
    workspace._show_workspace(1)
    QApplication.processEvents()
    header = workspace._header_stack.currentWidget()
    moves = []
    monkeypatch.setattr(workspace.windowHandle(), "startSystemMove", lambda: moves.append(True) or True)
    qtbot.mouseClick(header, Qt.LeftButton, pos=QPoint(header.width() // 2, 28))
    assert moves == [True]
    qtbot.mouseDClick(header, Qt.LeftButton, pos=QPoint(header.width() // 2, 28))
    assert workspace.isMaximized()
    qtbot.mouseDClick(header, Qt.LeftButton, pos=QPoint(header.width() // 2, 28))
    assert not workspace.isMaximized()
    moves.clear()
    qtbot.mouseClick(header.actions.itemAt(0).widget(), Qt.LeftButton)
    assert not moves
    assert workspace._workspace_pages.currentIndex() == 2
    qtbot.mouseClick(workspace._sidebar, Qt.LeftButton, pos=QPoint(4, 40))
    assert moves == [True]
    moves.clear()
    qtbot.mouseClick(workspace._home_nav, Qt.LeftButton)
    assert not moves
    assert workspace._workspace_pages.currentIndex() == 0


def test_network_error_preserves_identity_and_rejects_old_result(workspace):
    workspace._on_login_status_result(
        0, {"isLogin": True, "uname": "演示用户", "mid": 123, "face": "demo"}
    )
    workspace._on_login_status_avatar(0, avatar_png())
    workspace._login_status_request_id = 1
    workspace._on_login_status_error(1, "offline")
    workspace._on_login_status_result(0, {"isLogin": False})
    assert workspace._account_text == "演示用户"
    assert not workspace._header_login._avatar.isNull()
    assert workspace._login_verified is None
    assert workspace._account_state == "unknown"


def test_cocoa_keeps_native_buttons_and_roundtrips_fullscreen(workspace, qtbot):
    import ctypes
    import sys

    if sys.platform != "darwin" or QApplication.platformName() != "cocoa":
        pytest.skip("Requires the native macOS desktop backend")
    window = workspace
    if not window._chrome.expanded:
        pytest.skip("Requires Qt expanded-client-area support")
    window.show()
    QApplication.processEvents()
    window._chrome._sync_native()
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
    pointer = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
        address
    )
    native = pointer(int(window.winId()), objc.sel_registerName(b"window"))
    integer = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(address)
    button = ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long
    )(address)
    boolean = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(address)
    assert integer(native, objc.sel_registerName(b"titleVisibility")) == 1
    for kind in (0, 1, 2):
        control = button(native, objc.sel_registerName(b"standardWindowButton:"), kind)
        assert control
        assert not boolean(control, objc.sel_registerName(b"isHidden"))
        assert boolean(control, objc.sel_registerName(b"isEnabled"))
    try:
        window.showFullScreen()
        qtbot.waitUntil(
            lambda: (
                bool(integer(native, objc.sel_registerName(b"styleMask")) & (1 << 14))
                and boolean(native, objc.sel_registerName(b"qt_fullScreen"))
            ),
            timeout=5000,
        )
        assert window.isFullScreen()
    finally:
        window.showNormal()
        qtbot.waitUntil(
            lambda: (
                not bool(
                    integer(native, objc.sel_registerName(b"styleMask")) & (1 << 14)
                )
                and not boolean(native, objc.sel_registerName(b"qt_fullScreen"))
            ),
            timeout=5000,
        )
