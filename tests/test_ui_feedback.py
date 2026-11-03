"""Visible actions, input modality and screen limits under real layout pressure."""

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QMenu,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.resources.styles import theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import (
    CommandBar,
    OutputActionBar,
    TaskDetailPanel,
)
from bilibili_downloader.gui.widgets.responsive_actions import (
    ActionButton,
    ResponsiveActions,
)
from bilibili_downloader.gui.widgets.row_hover import RowHoverTable
from bilibili_downloader.gui.widgets.selection import SelectionBar, SelectionState
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


def flush(app):
    for _ in range(12):
        app.processEvents()


def assert_buttons_fit(host):
    rectangles = []
    for button in host.findChildren(QPushButton):
        if button.isVisible():
            rect = QRect(button.mapTo(host, QPoint()), button.size())
            assert host.rect().contains(rect), (button.text(), rect, host.rect())
            assert button.width() >= button.sizeHint().width(), button.text()
            ancestor = button.parentWidget()
            while ancestor is not None and ancestor is not host:
                local = QRect(button.mapTo(ancestor, QPoint()), button.size())
                assert ancestor.rect().contains(local), (button.text(), ancestor, local, ancestor.rect())
                ancestor = ancestor.parentWidget()
            rectangles.append((button.text(), rect))
    for n, (text, rect) in enumerate(rectangles):
        for other, second in rectangles[n + 1:]:
            assert not rect.intersects(second), (text, other)


@pytest.mark.parametrize("kind", ["selection", "output", "detail", "commands"])
@pytest.mark.parametrize("width", [420, 560, 780])
@pytest.mark.parametrize("font_scale", [1, 1.25, 1.5])
def test_actions_fit_with_counts_long_paths_and_actual_scaled_fonts(qapp, qtbot, kind, width, font_scale):
    theme = ThemeManager(qapp, "star_trail", "light")
    probe = QPushButton("加入 10000 个任务")
    original = probe.fontMetrics().horizontalAdvance(probe.text())
    qapp.setStyleSheet(load_stylesheet(False, font_scale=theme._font_scale * font_scale,
                                     font_family=theme._font_family, theme_id="star_trail"))
    probe.ensurePolished()
    if font_scale > 1:
        assert probe.fontMetrics().horizontalAdvance(probe.text()) > original
    probe.deleteLater()
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    if kind == "selection":
        widget = SelectionBar()
        widget.update_state(SelectionState(order=list(range(10000)), selected=set(range(10000)), visible={1, 2}))
    elif kind == "output":
        widget = OutputActionBar("已选 10000 个作品 · 10000 个任务")
        widget.directory.set_full_text("保存至 /" + "长目录/" * 80)
        widget.specs.set_full_text("1080P · HEVC · AAC · MP4")
        widget.primary_button.setText("加入 10000 个任务")
        widget.primary_button.setEnabled(True)
    elif kind == "commands":
        widget = CommandBar()
        search = QLineEdit()
        search.setMinimumWidth(160)
        widget.filters.addWidget(search)
        for text in ("全部类型", "全部状态"):
            combo = ComboBox()
            combo.addItem(text)
            combo.setFixedWidth(112)
            widget.filters.addWidget(combo)
        for text in ("检查 10000 项", "核验媒体轨道与时长", "重新定位整个目录"):
            button = ActionButton(text)
            if text.startswith("检查"):
                button.setProperty("alwaysVisible", True)
            widget.actions.addWidget(button)
    else:
        widget = TaskDetailPanel()
        widget.set_details("作品", "需要处理", "", "/" + "长目录/" * 80)
        widget.set_actions(("重新选择位置…", lambda: None), ("打开文件夹", lambda: None))
        widget.result_row.show()
        widget.status.hide()
        for badge, text in zip(widget.result_badges, ("媒体无法访问", "规格尚未确认", "字幕等附件待补全")):
            badge.setText(text)
    layout.addWidget(widget)
    layout.addStretch()
    host.resize(width, 620)
    host.show()
    flush(qapp)
    assert host.width() == width
    assert_buttons_fit(host)
    if kind == "selection":
        assert "筛选外 9998 项" in widget.summary.text()
        assert widget.summary.height() >= widget.summary.heightForWidth(widget.summary.width())
    if kind == "output":
        assert widget.primary_button.isVisible()
        assert "10000" in widget.primary_button.text()
        assert widget.status.height() >= widget.status.heightForWidth(widget.status.width())
        assert widget.specs.isVisible() and widget.specs.width() >= 60
        assert widget.directory.height() >= widget.directory.fontMetrics().height() + 2


@pytest.mark.parametrize("text", ["0 个任务", "6 个任务", "110 个任务", "已选 2 个任务"])
def test_short_output_count_keeps_whole_words_beside_long_specs(qapp, qtbot, text):
    ThemeManager(qapp, "star_trail", "light")
    bar = OutputActionBar(text)
    qtbot.addWidget(bar)
    bar.specs.set_full_text("视频 · 1080P · HEVC · 各作品全部分 P，实际规格逐项确认")
    bar.resize(1064, 150)
    bar.show()
    flush(qapp)
    assert bar.status.width() >= bar.status.fontMetrics().horizontalAdvance(text)
    assert bar.status.heightForWidth(bar.status.width()) <= bar.status.fontMetrics().height() + 2
    assert_buttons_fit(bar)


def test_overflow_uses_one_action_and_preserves_dynamic_state_and_focus(qapp, qtbot):
    ThemeManager(qapp, "star_trail", "light")
    strip = ResponsiveActions()
    qtbot.addWidget(strip)
    hits = []
    secondary = ActionButton("低频操作")
    secondary.clicked.connect(lambda: hits.append("secondary"))
    primary = ActionButton("开始处理")
    primary.setProperty("alwaysVisible", True)
    primary.clicked.connect(lambda: hits.append("primary"))
    strip.row.addWidget(secondary)
    strip.row.addWidget(primary)
    strip.resize(500, 44)
    strip.show()
    secondary.setFocus(Qt.TabFocusReason)
    flush(qapp)
    strip.resize(primary.sizeHint().width() + strip.more.sizeHint().width() + 8, 44)
    flush(qapp)
    assert secondary.isHidden() and strip.more.isVisible()
    assert secondary.action in strip.more.menu().actions()
    assert QApplication.focusWidget() is strip.more
    secondary.setText("处理 10000 项")
    secondary.setDisabled(True)
    flush(qapp)
    assert secondary.action.text() == "处理 10000 项" and not secondary.action.isEnabled()
    secondary.action.trigger()
    assert hits == []
    secondary.setEnabled(True)
    secondary.action.trigger()
    assert hits == ["secondary"]
    strip.resize(500, 44)
    flush(qapp)
    assert secondary.isVisible() and secondary.action not in strip.more.menu().actions()
    secondary.click()
    assert hits == ["secondary", "secondary"]


def test_existing_more_menu_keeps_its_actions_and_appends_overflow(qapp, qtbot):
    ThemeManager(qapp, "star_trail", "light")
    strip = ResponsiveActions()
    qtbot.addWidget(strip)
    more = QPushButton("更多")
    menu = QMenu(more)
    hits = []
    original = menu.addAction("原有操作", lambda: hits.append("original"))
    more.setMenu(menu)
    strip.row.addWidget(more)
    strip.row.addStretch()
    for text in ("打开所在文件夹", "复制完整保存路径", "合并导出 MP4"):
        button = ActionButton(text)
        if text.startswith("合并"):
            button.setProperty("alwaysVisible", True)
        strip.row.addWidget(button)
    strip.resize(260, 64)
    strip.show()
    flush(qapp)
    assert menu.actions()[0] is original and len(menu.actions()) > 1
    assert_buttons_fit(strip)
    original.trigger()
    assert hits == ["original"]


def test_retry_stop_remains_available_alongside_primary_action(qapp, qtbot):
    ThemeManager(qapp, "star_trail", "light")
    detail = TaskDetailPanel()
    qtbot.addWidget(detail)
    detail.set_details("等待重试", "30 秒后重试", "", "~/demo.mp4")
    detail.set_actions(("立即重试", lambda: None), ("停止等待", lambda: None), secondary_required=True)
    detail.resize(420, 180)
    detail.show()
    flush(qapp)
    assert detail.primary_action.isVisible() and detail.secondary_action.isVisible()
    assert_buttons_fit(detail)


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_dropdown_hover_has_fill_without_edge_lines_and_keyboard_focus_is_inset(qapp, qtbot, theme_id, dark):
    ThemeManager(qapp, theme_id, "dark" if dark else "light")
    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["当前", "其他选项"])
    combo.view().setCurrentIndex(combo.model().index(1, 0))
    delegate = combo.itemDelegate()
    opt = QStyleOptionViewItem()
    opt.widget = combo.view()
    opt.rect = QRect(0, 0, 260, 44)
    opt.state = QStyle.State_Enabled | QStyle.State_MouseOver
    images = []
    for keyboard in (False, True):
        combo.view().setProperty("keyboardFocus", keyboard)
        image = QImage(QSize(260, 44), QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        delegate.paint(painter, opt, combo.model().index(1, 0))
        painter.end()
        images.append(image)
        assert image.pixelColor(0, 22) == QColor(theme_palette(dark, theme_id).control_hover)
    assert images[0] != images[1]
    # A stationary pointer on another row must not create a second focus frame.
    combo.view().setCurrentIndex(combo.model().index(0, 0))
    image = QImage(QSize(260, 44), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    delegate.paint(painter, opt, combo.model().index(1, 0))
    painter.end()
    assert image == images[0]


def test_table_keyboard_focus_switches_back_to_pointer_without_changing_current(qapp, qtbot):
    ThemeManager(qapp, "star_trail", "light")
    table = RowHoverTable(2, 2)
    qtbot.addWidget(table)
    for row in range(2):
        for col in range(2):
            table.setItem(row, col, QTableWidgetItem(str(row)))
    table.show()
    table.raise_()
    table.activateWindow()
    QApplication.setActiveWindow(table)
    # Cocoa positions newly shown windows asynchronously; move after exposure.
    qtbot.waitExposed(table)
    qtbot.wait(80)
    start = table.visualItemRect(table.item(1, 0)).center()
    qtbot.mouseMove(table.viewport(), start)
    qtbot.waitUntil(lambda: table._row_hover._pointer_pos == table.viewport().mapToGlobal(start))
    table.setCurrentCell(0, 0)
    table.setFocus(Qt.TabFocusReason)
    qtbot.keyClick(table, Qt.Key_Down)
    flush(qapp)
    assert table.property("keyboardFocus") and table.currentRow() == 1
    qtbot.mouseMove(table.viewport(), table.visualItemRect(table.item(0, 0)).center())
    qtbot.waitUntil(lambda: not table.property("keyboardFocus"))
    assert not table.property("keyboardFocus") and table.currentRow() == 1


@pytest.mark.parametrize("available", [QRect(50, 60, 800, 560), QRect(50, 60, 720, 480)])
def test_dialog_bounds_and_footer_remain_visible_when_content_grows(qapp, qtbot, available):
    ThemeManager(qapp, "star_trail", "light")
    dialog = WorkflowDialog("处理结果", "一段说明" * 25, confirm="开始处理（10000 项）")
    qtbot.addWidget(dialog)
    dialog._screen_bounds.available_geometry = lambda: available
    for _ in range(20):
        entry = QLineEdit("长内容" * 80)
        dialog.body.addWidget(entry)
    dialog.resize(1000, 900)
    dialog.show()
    qtbot.waitUntil(lambda: available.contains(dialog.frameGeometry()))
    flush(qapp)
    assert available.contains(dialog.frameGeometry())
    assert dialog.scroller.verticalScrollBar().maximum() > 0
    assert_buttons_fit(dialog)
    assert dialog.confirm_button.isVisible() and dialog.cancel_button.isVisible()
    dialog.notice.set_message("目录不可写，请重新选择保存位置。" * 5, "danger")
    flush(qapp)
    assert available.contains(dialog.frameGeometry())
    assert_buttons_fit(dialog)


@pytest.mark.parametrize("available", [QRect(0, 0, 800, 560), QRect(0, 0, 720, 480)])
def test_small_desktop_keeps_main_window_and_confirmation_in_bounds(workspace, qapp, available):
    workspace._screen_bounds.available_geometry = lambda: available
    workspace.resize(1320, 860)
    workspace.show()
    flush(qapp)
    assert available.contains(workspace.frameGeometry())
    bar = workspace._download_actions
    for button in (bar.primary_button, bar.directory_button):
        assert button.isVisible()
        assert workspace.rect().contains(QRect(button.mapTo(workspace, QPoint()), button.size()))
