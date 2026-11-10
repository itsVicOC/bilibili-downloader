"""Rendered states, edit semantics and native-event detail regressions."""

import warnings

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QInputMethodEvent, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import contrast_ratio, theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.check_box import CheckBox
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import FieldRow
from bilibili_downloader.gui.widgets.file_table import FileTable
from bilibili_downloader.gui.widgets.popup_menu import PopupMenu
from bilibili_downloader.gui.widgets.selection import TableSelection
from bilibili_downloader.gui.widgets.text_menu import text_context_menu
from bilibili_downloader.gui.widgets.video_info import _AspectCoverLabel
from tests.test_ui_refresh import restore_theme as restore_theme


def flush():
    for _ in range(12):
        QApplication.processEvents()


def show_active(qtbot, widget):
    widget.show()
    # Cocoa can keep an automation process inactive after its last window closes.
    # Set Qt's active window without changing macOS keyboard-access preferences.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*setActiveWindow.*")
        QApplication.setActiveWindow(widget)
    flush()
    assert widget.isActiveWindow()


def color(widget, x, y):
    image = widget.grab().toImage()
    dpr = image.devicePixelRatio()
    return image.pixelColor(round(x * dpr), round(y * dpr)).name()


@pytest.mark.parametrize("theme", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_text_control_boundaries_and_action_labels_meet_contrast(theme, dark):
    p = theme_palette(dark, theme)
    for surface in (p.surface, p.surface_raised, p.control_fill, p.popup):
        for text in (p.text, p.muted):
            assert contrast_ratio(surface, text) >= 4.5
    assert contrast_ratio(p.control_border, p.control_fill) >= 3
    assert contrast_ratio(p.focus, p.control_fill) >= 3
    for fill in (p.primary, p.primary_hover, p.primary_pressed):
        assert contrast_ratio(p.primary_text, fill) >= 4.5


@pytest.mark.parametrize("multiline", [False, True])
def test_readonly_menu_preserves_text_and_copy_while_disabling_mutation(qtbot, multiline):
    editor = QPlainTextEdit("收藏，从这里开始。") if multiline else QLineEdit("收藏，从这里开始。")
    qtbot.addWidget(editor)
    editor.setReadOnly(True)
    editor.selectAll()
    QApplication.clipboard().setText("replacement")
    menu = text_context_menu(editor)
    actions = {action.text(): action for action in menu.actions()}
    for name in ("撤销", "重做", "剪切", "粘贴", "删除"):
        assert not actions[name].isEnabled()
    assert actions["复制"].isEnabled()
    actions["复制"].trigger()
    assert QApplication.clipboard().text() == "收藏，从这里开始。"
    menu.deleteLater()


def test_password_menu_does_not_expose_selected_credentials(qtbot):
    editor = QLineEdit("offline-credential")
    qtbot.addWidget(editor)
    editor.setEchoMode(QLineEdit.Password)
    editor.selectAll()
    menu = text_context_menu(editor)
    actions = {action.text(): action for action in menu.actions()}
    assert not actions["复制"].isEnabled() and not actions["剪切"].isEnabled()
    menu.deleteLater()


def test_chinese_ime_commit_and_undo_remain_native(qtbot):
    editor = QLineEdit()
    qtbot.addWidget(editor)
    show_active(qtbot, editor)
    editor.setFocus()
    QApplication.sendEvent(editor, QInputMethodEvent("manman", []))
    assert editor.text() == ""
    commit = QInputMethodEvent()
    commit.setCommitString("慢慢看")
    QApplication.sendEvent(editor, commit)
    assert editor.text() == "慢慢看"
    editor.undo()
    assert editor.text() == ""
    editor.redo()
    assert editor.text() == "慢慢看"


@pytest.mark.parametrize("kind", ["combo", "spin", "slider"])
def test_unfocused_wheel_scrolls_page_and_preserves_focused_native_policy(qtbot, qapp, kind):
    ThemeManager(qapp, "star_trail", "light")
    body = QWidget()
    layout = QVBoxLayout(body)
    control = ComboBox() if kind == "combo" else QSpinBox() if kind == "spin" else QSlider(Qt.Horizontal)
    if kind == "combo":
        control.addItems(["低", "中", "高"])
        control.setCurrentIndex(1)
    else:
        control.setRange(0, 100)
        control.setValue(50)
    layout.addWidget(control)
    filler = QWidget()
    filler.setMinimumHeight(1200)
    layout.addWidget(filler)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(body)
    scroll.resize(440, 300)
    qtbot.addWidget(scroll)
    show_active(qtbot, scroll)
    control.clearFocus()
    value = lambda: control.currentIndex() if kind == "combo" else control.value()
    initial = value()
    def wheel(delta):
        point = control.rect().center()
        event = QWheelEvent(QPointF(point), QPointF(control.mapToGlobal(point)), QPoint(), QPoint(0, delta),
                            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(control, event)
        flush()
    wheel(-120)
    assert value() == initial and scroll.verticalScrollBar().value() > 0
    control.setFocus(Qt.TabFocusReason)
    wheel(120)
    if kind == "combo" and not control.style().styleHint(QStyle.SH_ComboBox_AllowWheelScrolling, None, control):
        assert value() == initial
    else:
        assert value() != initial


def test_error_border_and_keyboard_ring_coexist_without_geometry_change(qtbot, qapp):
    ThemeManager(qapp, "star_trail", "light")
    entry = QLineEdit("示例输入")
    field = FieldRow("保存目录", entry)
    qtbot.addWidget(field)
    field.resize(440, 100)
    show_active(qtbot, field)
    before = entry.geometry()
    field.set_error("请选择可写目录。")
    entry.clearFocus()
    entry.setFocus(Qt.TabFocusReason)
    flush()
    p = theme_palette(False)
    assert color(entry, 0, entry.height() // 2) == p.danger_border
    assert color(entry, 3, entry.height() // 2) == p.focus
    assert entry.width() == before.width() and entry.height() == before.height()
    assert "请选择可写目录" in entry.accessibleDescription()
    field.set_error("")
    assert "请选择可写目录" not in entry.accessibleDescription()


def test_checkbox_space_cycles_three_states_and_table_enum_state_is_painted(qtbot, qapp):
    ThemeManager(qapp, "star_trail", "light")
    check = CheckBox("全部字幕")
    check.setTristate(True)
    qtbot.addWidget(check)
    show_active(qtbot, check)
    for state in (Qt.PartiallyChecked, Qt.Checked, Qt.Unchecked):
        qtbot.keyClick(check, Qt.Key_Space)
        assert check.checkState() == state
    table = FileTable()
    table.replace_rows([["作品", "", "", "", "", ""]], [1], ["作品"])
    binding = TableSelection(table, paint_only=True)
    binding.reset([1])
    qtbot.addWidget(table)
    table.resize(500, 150)
    show_active(qtbot, table)
    binding.toggle(1)
    qtbot.mouseMove(table.viewport(), table.viewport().rect().bottomRight())
    flush()
    assert table.model().index(0, 0).data(Qt.CheckStateRole) == Qt.Checked
    rect = table.visualRect(table.model().index(0, 0))
    assert color(table.viewport(), rect.left() + 10, rect.center().y()) == theme_palette(False).primary


def test_checkbox_label_reserves_the_shared_indicator_and_gap(qtbot, qapp):
    ThemeManager(qapp, "star_trail", "light")
    check = CheckBox("前台识别 B 站剪贴板内容")
    qtbot.addWidget(check)
    check.resize(420, 40)
    check.show()
    flush()
    option = QStyleOptionButton()
    check.initStyleOption(option)
    indicator = check.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, check)
    label = check.style().subElementRect(QStyle.SE_CheckBoxContents, option, check)
    assert indicator.width() == 18
    assert label.left() - indicator.right() >= 8
    assert label.width() >= check.fontMetrics().horizontalAdvance(check.text())


def test_cover_uses_rounded_clip_and_native_pixel_density(qtbot, qapp):
    from PySide6.QtGui import QPixmap
    ThemeManager(qapp, "star_trail", "light")
    cover = _AspectCoverLabel()
    qtbot.addWidget(cover)
    cover.resize(176, 99)
    cover.show()
    pixmap = QPixmap(1000, 560)
    pixmap.fill(Qt.red)
    cover.set_source_pixmap(pixmap, expand=True)
    flush()
    assert cover.pixmap().devicePixelRatio() == cover.devicePixelRatioF()
    assert color(cover, 0, 0) != "#ff0000"
    assert color(cover, cover.width() // 2, cover.height() // 2) == "#ff0000"


def test_menu_keyboard_skips_disabled_actions_and_escape_keeps_callbacks_idle(qtbot, qapp):
    ThemeManager(qapp, "star_trail", "light")
    owner = QWidget()
    qtbot.addWidget(owner)
    show_active(qtbot, owner)
    menu = PopupMenu(owner)
    first = menu.addAction("打开文件夹")
    menu.addAction("暂不可用").setEnabled(False)
    last = menu.addAction("复制完整路径")
    activated = []
    menu.triggered.connect(lambda action: activated.append(action.text()))
    qtbot.mouseMove(owner, owner.rect().bottomRight())
    menu.popup(owner.mapToGlobal(QPoint(10, 10)))
    flush()
    size = menu.size()
    qtbot.keyClick(menu, Qt.Key_Down)
    assert menu.activeAction() is first
    qtbot.keyClick(menu, Qt.Key_Down)
    assert menu.activeAction() is last and menu.property("keyboardFocus")
    rect = menu.actionGeometry(last)
    assert color(menu, rect.left() + 2, rect.center().y()) == theme_palette(False).focus
    assert menu.size() == size
    qtbot.keyClick(menu, Qt.Key_Escape)
    assert not menu.isVisible() and not activated
