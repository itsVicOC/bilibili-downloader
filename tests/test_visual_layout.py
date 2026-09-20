"""Geometry regressions for the responsive desktop visual system."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from bilibili_downloader.core.models import (
    AppSettings,
    DownloadItem,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.main_window import MainWindow
from bilibili_downloader.utils.config import ConfigManager


def _make_window(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    return MainWindow(config_manager=config, task_repository=repository)


def _add_task(window, task_id, status=TaskStatus.DOWNLOADING):
    item = DownloadItem(
        video_info=VideoInfo(
            bvid=f"BV1VISUAL{task_id:02d}",
            cid=task_id,
            title=f"用于视觉回归的较长作品标题 {task_id}",
        )
    )
    window._download_list.add_item(
        item,
        download_id=task_id,
        status=status,
        progress=0.42,
        status_text="这是一个足够长、需要自动省略的任务状态",
    )


def test_table_action_buttons_have_consistent_valid_geometry(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    _add_task(window, 1, TaskStatus.FAILED)
    window.resize(1320, 860)
    window.show()
    QApplication.processEvents()

    action_buttons = [
        button
        for button in window._download_list.findChildren(QPushButton)
        if button.objectName().startswith("Table")
    ]
    assert action_buttons
    for button in action_buttons:
        assert button.height() == 32
        assert button.width() >= button.sizeHint().width()
        assert button.minimumHeight() <= button.maximumHeight()


def test_task_priority_layout_is_responsive(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    for task_id in range(1, 4):
        _add_task(window, task_id)

    window.resize(1320, 860)
    window.show()
    QApplication.processEvents()
    assert window._task_priority_mode
    assert window._workspace_layout.indexOf(window._content_section) == 2
    assert window._workspace_layout.indexOf(window._queue_section) == 3
    assert window._download_list.viewport().height() >= 3 * 48

    window.resize(900, 640)
    QApplication.processEvents()
    assert window._workspace_layout.indexOf(window._queue_section) == 2
    assert window._workspace_layout.indexOf(window._content_section) == 3
    assert window._download_list.horizontalScrollBar().maximum() == 0
    assert window._workspace_scroll.horizontalScrollBar().maximum() == 0


def test_task_priority_mode_returns_to_branded_empty_state(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    _add_task(window, 1, TaskStatus.COMPLETED)
    assert window._task_priority_mode

    window._download_list.remove_item(1)

    assert not window._task_priority_mode
    assert not window._hero_eyebrow.isHidden()
    assert not window._hero_title.isHidden()


def test_login_qr_controls_do_not_overlap_at_minimum_size(qtbot):
    dialog = LoginDialog(None)
    qtbot.addWidget(dialog)
    dialog.resize(dialog.minimumSize())
    dialog._tabs.setCurrentIndex(1)
    dialog.show()
    QApplication.processEvents()

    assert dialog._qr_label.width() == 220
    assert dialog._qr_label.height() == 220
    assert not dialog._qr_label.geometry().intersects(
        dialog._generate_btn.geometry()
    )


def test_long_settings_path_starts_at_leading_edge(qtbot):
    path = "/Users/example/" + "nested-directory/" * 20
    dialog = SettingsDialog(AppSettings(output_dir=path))
    qtbot.addWidget(dialog)
    dialog.show()
    QApplication.processEvents()

    assert dialog._output_dir.cursorPosition() == 0
    assert dialog._output_dir.toolTip() == path
    assert dialog._output_dir.alignment() & Qt.AlignLeft
