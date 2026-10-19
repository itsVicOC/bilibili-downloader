"""Focused accessibility and validation tests for desktop dialogs."""

import pytest
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QWidget,
)

from bilibili_downloader.core.models import (
    AppSettings,
    ContentKind,
    DownloadItem,
    OutputMode,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.utils.config import ConfigManager


def test_login_cookie_is_masked_by_default(qtbot):
    dialog = LoginDialog("existing-secret")
    qtbot.addWidget(dialog)

    assert dialog._cookie_input.echoMode() == QLineEdit.Password
    assert dialog._cookie_input.text() == ""
    assert dialog._instructions.wordWrap()
    assert "SESSDATA" in dialog._instructions.text()
    assert dialog._tabs.tabText(1) == "扫码登录"
    assert dialog._qr_label.text() == "点击下方按钮生成二维码"


def test_login_defaults_to_qr_and_signed_in_account_opens_management(qtbot):
    from PySide6.QtWidgets import QPushButton

    login = LoginDialog(None)
    qtbot.addWidget(login)
    assert login._tabs.currentIndex() == 1
    account = LoginDialog("demo-secret", account={"uname": "演示用户", "mid": 123})
    qtbot.addWidget(account)
    assert account._tabs.isHidden()
    assert any(label.text() == "演示用户" for label in account.findChildren(QLabel))
    switch = next(button for button in account.findChildren(QPushButton) if button.text() == "切换账号")
    switch.click()
    assert not account._tabs.isHidden()
    assert account._tabs.currentIndex() == 1
    assert account._account_card.isHidden()
    assert account.height() <= 640


def test_expired_account_opens_qr_login_instead_of_management(qtbot):
    dialog = LoginDialog("expired-demo-cookie", account_valid=False)
    qtbot.addWidget(dialog)
    assert not dialog._tabs.isHidden()
    assert dialog._tabs.currentIndex() == 1
    assert "失效" in dialog._caption.text()


def test_account_management_keeps_switch_action_inside_card(qtbot):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication, QPushButton

    account = LoginDialog("demo-secret", account={"uname": "很长的演示名字" * 12, "mid": 123})
    qtbot.addWidget(account)
    account.show()
    QApplication.processEvents()
    switch = next(button for button in account.findChildren(QPushButton) if button.text() == "切换账号")
    assert account.width() == 500
    assert account._account_card.rect().contains(QRect(switch.mapTo(account._account_card, QPoint()), switch.size()))


@pytest.mark.parametrize("target, url", [
    ("batch", "https://space.bilibili.com/123/favlist?fid=456"),
    ("live", "https://live.bilibili.com/123"),
])
def test_short_link_routes_in_background_before_video_resolution(qapp, monkeypatch, target, url):
    from types import SimpleNamespace

    from bilibili_downloader.gui.threads.resolve_worker import (
        ResolveRunner,
        ResolveWorker,
    )

    monkeypatch.setattr("bilibili_downloader.gui.threads.resolve_worker.resolve_short_url", lambda _: url)
    worker = ResolveWorker(SimpleNamespace(), "https://b23.tv/demo123")
    routed = []
    worker.routed.connect(lambda *args: routed.append(args))
    ResolveRunner(worker).run()
    assert routed == [(target, url)]


def test_settings_dialog_keeps_long_path_in_tooltip(qtbot):
    long_path = "/tmp/" + "nested/" * 30
    dialog = SettingsDialog(AppSettings(output_dir=long_path))
    qtbot.addWidget(dialog)

    assert dialog._output_dir.toolTip() == long_path
    assert dialog.minimumWidth() == 620
    assert dialog._max_concurrent.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert (
        dialog._max_concurrent.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
    )
    assert dialog._concurrency_down.toolTip() == "减少并发数"
    assert dialog._concurrency_up.toolTip() == "增加并发数"
    assert dialog._bangumi_path_template.text().startswith("{series}/{season}")

    dialog._max_concurrent.setValue(1)
    assert not dialog._concurrency_down.isEnabled()
    assert dialog._concurrency_up.isEnabled()

    dialog._max_concurrent.setValue(8)
    assert dialog._concurrency_down.isEnabled()
    assert not dialog._concurrency_up.isEnabled()


def test_settings_all_subtitles_enables_subtitle_download(qtbot):
    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    dialog._subtitle_check.setChecked(False)
    dialog._all_subtitles_check.setChecked(True)

    settings = dialog.get_settings()

    assert settings.download_subtitle
    assert settings.download_all_subtitles


def test_main_window_separates_download_and_service_pools(qtbot, tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    window = MainWindow(config_manager=config, task_repository=repository)
    qtbot.addWidget(window)

    assert window._download_pool is not window._service_pool
    assert window._download_pool.maxThreadCount() == 3
    assert window._service_pool.maxThreadCount() == 4
    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 640

    controls = window.findChild(QWidget, "ControlPanel")
    assert controls.layout().contentsMargins().left() == 20
    assert controls.layout().spacing() == 12
    assert not window._download_btn.isEnabled()

    audio_index = window._output_mode_combo.findData(OutputMode.AUDIO)
    window._output_mode_combo.setCurrentIndex(audio_index)
    assert window._codec_label.text() == "音频质量"
    assert window._codec_stack.currentWidget() is window._audio_combo
    assert not window._quality_combo.isEnabled()

    fallback_index = window._audio_combo.findData(0)
    window._audio_combo.setCurrentIndex(fallback_index)
    window._populate_audio_combo()
    assert window._audio_combo.currentData() == 0


def test_main_window_recovers_interrupted_task_as_paused(qtbot, tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    item = DownloadItem(
        video_info=VideoInfo(bvid="BV1GJ411x7h7", cid=1, title="Interrupted")
    )
    task_id = repository.add(item)
    repository.update(task_id, status=TaskStatus.DOWNLOADING)

    window = MainWindow(config_manager=config, task_repository=repository)
    qtbot.addWidget(window)

    assert repository.get(task_id).status == TaskStatus.PAUSED
    assert window._download_list._states[task_id] == TaskStatus.PAUSED


def test_batch_dialog_selects_only_main_bangumi_episodes_by_default(qtbot):
    dialog = BatchDialog()
    qtbot.addWidget(dialog)
    main = VideoInfo(
        content_kind=ContentKind.BANGUMI_EPISODE,
        episode_id=1,
        cid=11,
        title="正片",
        series_title="系列",
        season_title="季度",
        section_title="正片",
        is_main_section=True,
    )
    extra = main.model_copy(
        update={
            "episode_id": 2,
            "cid": 22,
            "title": "PV",
            "section_title": "PV",
            "is_main_section": False,
        }
    )

    dialog._on_resolved([main, extra], [])

    assert dialog._selectors[0].isChecked()
    assert not dialog._selectors[1].isChecked()
    assert dialog._preview.item(1, 3).text() == "系列 · 季度 · PV"
    assert dialog._preview.rowHeight(0) == UI_METRICS.compact_row_height
    assert dialog._preview.rowHeight(1) == UI_METRICS.compact_row_height


def test_cancelling_copyright_notice_does_not_acknowledge(qtbot, tmp_path, monkeypatch):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    window = MainWindow(config_manager=config, task_repository=repository)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: QMessageBox.Cancel)

    assert window._confirm_copyright_acknowledgement() is False
    assert window._settings.copyright_notice_version == 0
    assert repository.list_tasks() == []
