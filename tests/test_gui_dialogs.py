"""Focused accessibility and validation tests for desktop dialogs."""

from PySide6.QtWidgets import (
    QAbstractSpinBox,
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
    assert controls.minimumHeight() == 340
    assert controls.layout().verticalSpacing() == 8

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
