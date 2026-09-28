"""Desktop controls and lifetime guards for live recording."""

from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.live_models import LiveSettings
from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.gui.widgets.live_page import LivePage
from bilibili_downloader.utils.config import ConfigManager


def test_live_page_fits_small_window_and_navigation_preserves_downloads(
    qtbot, tmp_path
):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings())
    window = MainWindow(
        config_manager=config,
        task_repository=TaskRepository(tmp_path / "tasks.sqlite3"),
    )
    qtbot.addWidget(window)
    window.resize(900, 640)
    window.show()
    window._live_nav.click()
    QApplication.processEvents()
    assert window._workspace_pages.currentWidget() is window._live_page
    assert window.width() == 900
    assert window._live_page.source.isVisible()
    assert window._live_page._room_stack.height() >= 180
    assert window._live_page.controller is window._task_page.controller
    window._home_nav.click()
    assert window._workspace_pages.currentIndex() == 0
    window._live_page.service.shutdown()
    window._live_page.shutdown()


def test_second_gui_instance_cannot_start_a_second_live_supervisor(qtbot, tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    first = LivePage(config, lambda: True)
    second = LivePage(config, lambda: True)
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    try:
        assert first.service is not None
        assert second.service is None
        assert "另一个" in second.message.text()
    finally:
        first.service.shutdown()
        first.shutdown()
        second.shutdown()


def test_download_settings_keep_live_preferences(qtbot):
    settings = AppSettings(
        live=LiveSettings(max_concurrent=4, recorder_path="/custom/recorder")
    )
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    saved = dialog.get_settings()
    assert saved.live == settings.live
