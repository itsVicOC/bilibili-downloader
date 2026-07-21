"""Focused accessibility and validation tests for desktop dialogs."""

from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.main_window import MainWindow


def test_login_cookie_is_masked_by_default(qtbot):
    dialog = LoginDialog("existing-secret")
    qtbot.addWidget(dialog)

    assert dialog._cookie_input.echoMode() == QLineEdit.Password
    assert dialog._cookie_input.text() == ""
    assert dialog._instructions.wordWrap()
    assert "SESSDATA" in dialog._instructions.text()
    assert dialog._tabs.tabText(1) == "扫码登录"
    assert dialog._qr_label.text() == "点击下方按钮生成二维码"


def test_settings_dialog_keeps_long_path_in_tooltip(qtbot):
    long_path = "/tmp/" + "nested/" * 30
    dialog = SettingsDialog(AppSettings(output_dir=long_path))
    qtbot.addWidget(dialog)

    assert dialog._output_dir.toolTip() == long_path
    assert dialog.minimumWidth() == 620
    assert dialog._max_concurrent.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert (
        dialog._max_concurrent.sizePolicy().horizontalPolicy()
        == QSizePolicy.Expanding
    )
    assert dialog._concurrency_down.toolTip() == "减少并发数"
    assert dialog._concurrency_up.toolTip() == "增加并发数"

    dialog._max_concurrent.setValue(1)
    assert not dialog._concurrency_down.isEnabled()
    assert dialog._concurrency_up.isEnabled()

    dialog._max_concurrent.setValue(8)
    assert dialog._concurrency_down.isEnabled()
    assert not dialog._concurrency_up.isEnabled()


def test_main_window_separates_download_and_service_pools(qtbot, monkeypatch):
    monkeypatch.setattr(
        "bilibili_downloader.gui.main_window.ConfigManager.load",
        lambda self: AppSettings(),
    )
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._download_pool is not window._service_pool
    assert window._download_pool.maxThreadCount() == 3
    assert window._service_pool.maxThreadCount() == 4
    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 640

    controls = window.findChild(QWidget, "ControlPanel")
    assert controls.minimumHeight() == 340
    assert controls.layout().verticalSpacing() == 8
