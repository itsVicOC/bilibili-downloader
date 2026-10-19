"""Geometry regressions for the responsive desktop visual system."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

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
from bilibili_downloader.gui.resources.styles import build_component_overrides
from bilibili_downloader.gui.widgets.download_list import (
    DownloadListWidget,
    _StatusDelegate,
)
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
    window._show_tasks()
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


def test_task_center_layout_is_responsive_without_reordering_download_form(
    qtbot, tmp_path
):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    original_position = window._workspace_layout.indexOf(window._content_section)
    for task_id in range(1, 4):
        _add_task(window, task_id)
    assert (
        window._workspace_layout.indexOf(window._content_section) == original_position
    )
    window.show()
    window._show_tasks()
    for size in ((1320, 860), (1120, 760), (900, 640)):
        window.resize(*size)
        QApplication.processEvents()
        assert window._download_list.viewport().height() >= 3 * 56
        assert window._download_list.horizontalScrollBar().maximum() == 0
    assert window._sidebar.width() == 72
    window._show_workspace(0)
    QApplication.processEvents()
    assert window._workspace_scroll.horizontalScrollBar().maximum() == 0


def test_last_task_removal_returns_task_center_to_shared_empty_state(qtbot, tmp_path):
    window = _make_window(tmp_path)
    qtbot.addWidget(window)
    _add_task(window, 1, TaskStatus.COMPLETED)
    window._task_page.refresh_downloads()
    assert window._task_page._download_stack.currentIndex() == 0
    window._download_list.remove_item(1)
    assert window._task_page._download_stack.currentIndex() == 1
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
    qr_rect = QRect(dialog._qr_label.mapTo(dialog, QPoint()), dialog._qr_label.size())
    button_rect = QRect(
        dialog._generate_btn.mapTo(dialog, QPoint()), dialog._generate_btn.size()
    )
    assert not qr_rect.intersects(button_rect)
    assert dialog.rect().contains(button_rect)


def test_long_settings_path_starts_at_leading_edge(qtbot):
    path = "/Users/example/" + "nested-directory/" * 20
    dialog = SettingsDialog(AppSettings(output_dir=path))
    qtbot.addWidget(dialog)
    dialog.show()
    QApplication.processEvents()

    assert dialog._output_dir.cursorPosition() == 0
    assert dialog._output_dir.toolTip() == path
    assert dialog._output_dir.alignment() & Qt.AlignLeft


class _TextRecordingPainter(QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.lines = []

    def drawText(self, rect, flags, text):
        self.lines.append((QRect(rect), flags, text))
        super().drawText(rect, flags, text)


def _paint_status(table, column, scale=1):
    index = table.model().index(0, column)
    option = QStyleOptionViewItem()
    option.initFrom(table)
    option.widget = table
    option.rect = table.visualRect(index)
    delegate = table.itemDelegateForColumn(column)
    delegate.initStyleOption(option, index)
    content = table.style().subElementRect(QStyle.SE_ItemViewItemText, option, table)
    image = QImage(
        round(table.viewport().width() * scale),
        round(table.viewport().height() * scale),
        QImage.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(scale)
    image.fill(Qt.transparent)
    painter = _TextRecordingPainter(image)
    delegate.paint(painter, option, index)
    painter.end()
    return painter.lines, content


@pytest.mark.parametrize("width", [700, 1026])
@pytest.mark.parametrize("scale", [1, 1.25, 1.5])
@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("已暂停，可继续", 1),
        ("下载中 · 2.4 MiB/s", 2),
        ("失败：" + "网络连接超时，请检查网络后继续下载。" * 6, 2),
        ("😀🛰️" * 18 + "弹幕与视频下载", 2),
    ],
)
def test_download_status_is_centered_and_bounded(qtbot, width, scale, text, count):
    table = DownloadListWidget()
    qtbot.addWidget(table)
    table.setStyleSheet(build_component_overrides(False))
    table.add_item(
        DownloadItem(video_info=VideoInfo(bvid="BV1VISUAL01", cid=1, title="示例")),
        status_text=text,
    )
    # Exercise fonts whose two lines need some of the QSS vertical padding.
    font = QFont(table.font())
    font.setPixelSize(18)
    table.item(0, 3).setFont(font)
    table.resize(width, 200)
    table.show()
    QApplication.processEvents()
    lines, content = _paint_status(table, 3, scale)
    assert len(lines) == count
    assert table.horizontalHeaderItem(3).textAlignment() == Qt.AlignCenter
    assert table.item(0, 3).toolTip() == text
    block = QRect()
    for rect, flags, line in lines:
        assert flags & Qt.AlignHCenter
        assert table.visualRect(table.model().index(0, 3)).contains(rect)
        assert rect.left() == content.left() and rect.width() == content.width()
        assert abs(rect.center().x() - content.center().x()) <= 1
        block = block.united(rect)
    assert abs(block.center().y() - content.center().y()) <= 1
    if text.startswith("失败："):
        assert lines[-1][2].endswith("…")


@pytest.mark.parametrize("alignment", [Qt.AlignLeft, Qt.AlignRight])
def test_shared_status_delegate_respects_other_columns(qtbot, alignment):
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    item = QTableWidgetItem("录制中 · 原画")
    item.setTextAlignment(alignment | Qt.AlignVCenter)
    table.setItem(0, 0, item)
    table.setItemDelegateForColumn(0, _StatusDelegate(table))
    table.setColumnWidth(0, 180)
    table.setRowHeight(0, 56)
    table.show()
    QApplication.processEvents()
    lines, _content = _paint_status(table, 0)
    assert lines
    assert all(flags & alignment for _rect, flags, _text in lines)


def test_resolution_errors_and_resumed_status_keep_alignment_and_tooltips(qtbot):
    table = DownloadListWidget()
    qtbot.addWidget(table)
    error_id = table.add_resolution_error("无法解析作品")
    assert table.item(table._row_for(error_id), 3).textAlignment() == Qt.AlignCenter
    task_id = table.add_item(
        DownloadItem(video_info=VideoInfo(bvid="BV1VISUAL01", cid=1, title="示例"))
    )
    row = table._row_for(task_id)
    for transition in (table.mark_paused, table.mark_failed_retry_reset, table.mark_cancelled):
        table.update_progress(task_id, .3, "下载中 · 旧进度详情")
        transition(task_id)
        assert table.item(row, 3).toolTip() == table.item(row, 3).text()
        assert table.item(row, 3).textAlignment() == Qt.AlignCenter
