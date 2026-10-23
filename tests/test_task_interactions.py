"""Row identity, continuous paint and compact directory actions."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QPushButton

from bilibili_downloader.core.models import DownloadItem, TaskStatus, VideoInfo
from bilibili_downloader.gui.resources.styles import theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from tests.test_live_exports import recording
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(8):
        QApplication.processEvents()


def sample(image, x, y):
    scale = image.devicePixelRatio()
    return image.pixelColor(round(x * scale), round(y * scale))


@pytest.mark.parametrize('size', [(900, 640), (1120, 760), (1320, 860)])
def test_directory_button_follows_text_and_long_path_preserves_selection(workspace, size):
    workspace.resize(*size)
    workspace.show()
    for index, bar in enumerate((workspace._download_actions, workspace._batch_page._action_bar)):
        workspace._download_tabs.setCurrentIndex(index)
        bar.directory.set_full_text('保存至 ~/Downloads/BiliFlow')
        flush()
        assert bar.directory_button.x() - (bar.directory.x() + bar.directory.width()) == 8
        assert bar.directory.width() <= bar.directory.sizeHint().width()
        short_button_x = bar.directory_button.x()
        bar.directory.set_full_text('保存至 /下载目录/' + '长路径/' * 70)
        bar.directory.setSelection(5, 6)
        selected = bar.directory.selectedText()
        for width in (size[0], 900, 1320, size[0]):
            workspace.resize(width, size[1])
            flush()
            assert bar.directory.selectedText() == selected
            assert bar.height() == 72
            assert bar.directory_button.x() > short_button_x
            assert bar.directory_button.geometry().right() < bar.primary_button.geometry().left() or bar.directory_button.parentWidget() is not bar.primary_button.parentWidget()


@pytest.mark.parametrize('theme_id', ['star_trail', 'bilibili_blue'])
@pytest.mark.parametrize('dark', [False, True])
def test_hover_crosses_cells_progress_and_buttons_with_one_row_color(workspace, qtbot, qapp, theme_id, dark):
    manager = ThemeManager(qapp, theme_id, 'dark' if dark else 'light')
    table = workspace._download_list
    for identity in (10, 20):
        table.add_item(DownloadItem(video_info=VideoInfo(bvid=f'BV{identity}', title='测试作品')),
                       download_id=identity, status=TaskStatus.PAUSED)
    workspace.resize(1120, 760)
    workspace._show_tasks(0)
    workspace.show()
    table.clearSelection()
    table.setCurrentCell(-1, -1)
    flush()
    changed, selected = [], []
    table.itemChanged.connect(lambda *_: changed.append(True))
    table.itemSelectionChanged.connect(lambda: selected.append(True))
    widgets = [(table.viewport(), table.visualItemRect(table.item(0, col)).center()) for col in (0, 1, 3)]
    progress = table.cellWidget(0, 2).bar
    button = table.cellWidget(0, 4).findChildren(QPushButton)[0]
    widgets += [(progress, progress.rect().center()), (button, button.rect().center())]
    for widget, point in widgets:
        qtbot.mouseMove(widget, point)
        qtbot.waitUntil(lambda: table._row_hover.index.isValid() and table._row_hover.index.row() == 0)
        flush()
        image = table.viewport().grab().toImage()
        y = table.visualItemRect(table.item(0, 0)).top() + 4
        colors = [sample(image, table.columnViewportPosition(col) + table.columnWidth(col) // 2, y).name() for col in range(5)]
        assert colors == [theme_palette(dark, theme_id).row_hover] * 5
    assert changed == selected == []
    table.selectRow(0)
    flush()
    y = table.visualItemRect(table.item(0, 0)).top() + 4
    image = table.viewport().grab().toImage()
    assert sample(image, 10, y).name() == theme_palette(dark, theme_id).selection
    qtbot.mouseMove(table.horizontalHeader(), QPoint(12, 8))
    qtbot.waitUntil(lambda: not table._row_hover.index.isValid())
    manager.deleteLater()


def test_history_hover_includes_indentation_and_tracks_child_rows(workspace, qtbot, tmp_path, qapp):
    manager = ThemeManager(qapp, "star_trail", "light")
    session = recording(tmp_path / 'media')
    workspace._live_controller.repository.save_session(session)
    workspace._live_controller.refresh()
    workspace._show_tasks(2)
    workspace.show()
    tree = workspace._task_page.history
    root = tree.topLevelItem(0)
    root.setExpanded(True)
    tree.clearSelection()
    flush()
    for item in (root, root.child(0)):
        rect = tree.visualItemRect(item)
        qtbot.mouseMove(tree.viewport(), QPoint(5, rect.center().y()))
        qtbot.waitUntil(lambda: tree._row_hover.matches(tree.indexFromItem(item)))
        flush()
        image = tree.viewport().grab().toImage()
        assert sample(image, 3, rect.top() + 4) == QColor(theme_palette(False).row_hover)
        assert sample(image, tree.columnWidth(0) + 12, rect.top() + 4) == QColor(theme_palette(False).row_hover)

    manager.deleteLater()


def test_hover_rehits_after_filter_scroll_and_deletion(workspace, qtbot):
    table = workspace._download_list
    for identity in range(25):
        table.add_item(DownloadItem(video_info=VideoInfo(bvid=f'BV{identity}', title='作品')),
                       download_id=identity, status=TaskStatus.PAUSED)
    workspace.resize(900, 640)
    workspace._show_tasks(0)
    workspace.show()
    flush()
    point = table.visualItemRect(table.item(0, 0)).center()
    qtbot.mouseMove(table.viewport(), point)
    qtbot.waitUntil(lambda: table._row_hover.index.isValid())
    table.setRowHidden(0, True)
    flush()
    assert table._row_hover.index.row() == table.indexAt(point).row()
    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
    flush()
    assert table._row_hover.index.row() == table.indexAt(point).row()
    hovered = table.item(table._row_hover.index.row(), 0).data(Qt.UserRole)
    table.remove_item(hovered)
    flush()
    assert table._row_hover.index.row() == table.indexAt(point).row()
