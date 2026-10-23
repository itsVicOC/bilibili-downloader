"""Interaction, accessibility and lifecycle regressions for Fluent state layers."""

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import contrast_ratio, theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.components import (
    CollapsibleSection,
    IconButton,
    repolish,
)
from bilibili_downloader.gui.widgets.download_options import DownloadOptionCard
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import room
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_reading_surfaces_keep_small_text_readable(theme_id, dark):
    p = theme_palette(dark, theme_id)
    for surface in (p.surface, p.control_fill, p.popup, p.subtle_selection, p.table_header):
        for text in (p.text, p.muted, p.active_text):
            assert contrast_ratio(text, surface) >= 4.5
    for tone in ("success", "warning", "danger", "active"):
        text = p.active_text if tone == "active" else getattr(p, tone)
        assert contrast_ratio(text, p.tone_surface(tone)) >= 4.5


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_text_selection_remains_visible_with_and_without_keyboard_focus(qapp, qtbot, theme_id, dark):
    """Check actual editor pixels, not only the configured palette roles."""
    from pathlib import Path

    theme = ThemeManager(qapp, theme_id)
    theme.set_mode("dark" if dark else "light")
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    fields = [QLineEdit(), QTextEdit(), QPlainTextEdit()]
    for field in fields:
        field.setFixedHeight(80 if not isinstance(field, QLineEdit) else 44)
        text = "https://www.bilibili.com/video/BV1234567890 测试选中文本"
        if isinstance(field, QLineEdit):
            field.setText(text)
        else:
            field.setPlainText(text)
        layout.addWidget(field)
    button = QPushButton("键盘焦点")
    button.setObjectName("PrimaryButton")
    layout.addWidget(button)
    host.resize(680, 320)
    host.show()
    host.raise_()
    host.activateWindow()
    qtbot.waitExposed(host)
    qtbot.waitUntil(host.isActiveWindow)
    p = theme_palette(dark, theme_id)
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        assert qapp.palette().color(group, QPalette.Highlight) == QColor(p.text_selection)
        assert qapp.palette().color(group, QPalette.HighlightedText) == QColor(p.text_selection_text)
    for index, field in enumerate(fields):
        field.setFocus()
        qtbot.waitUntil(field.hasFocus)
        field.selectAll()
        qtbot.wait(30)
        for focused in (True, False):
            if not focused:
                button.setFocus()
                qtbot.waitUntil(button.hasFocus)
                qapp.processEvents()
                # QLineEdit normally deselects on Tab/mouse focus loss. A
                # programmatic selection in an unfocused field must still use
                # the same readable inactive palette.
                field.selectAll()
                qtbot.wait(30)
            selection = field.selectedText() if isinstance(field, QLineEdit) else field.textCursor().selectedText()
            assert selection, (index, focused, field.hasFocus(), host.isActiveWindow())
            image = field.grab().toImage()
            colors = [image.pixelColor(x, y).name()
                      for x in range(image.width()) for y in range(image.height())]
            selected_pixels = colors.count(p.text_selection)
            selected_text_pixels = colors.count(p.text_selection_text)
            assert selected_pixels > 200, (index, focused, selected_pixels)
            assert selected_text_pixels > 20, (index, focused, selected_text_pixels)
    evidence = Path("build/ui-parity/selection")
    evidence.mkdir(parents=True, exist_ok=True)
    assert host.grab().save(str(evidence / f"{theme_id}-{'dark' if dark else 'light'}.png"))
    theme.deleteLater()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_control_states_do_not_move_the_form(qapp, qtbot, theme_id, dark):
    theme = ThemeManager(qapp, theme_id, "dark" if dark else "light")
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    entry, button = QLineEdit("测试输入"), QPushButton("操作")
    layout.addWidget(entry)
    layout.addWidget(button)
    host.show()
    qtbot.waitExposed(host)
    original = (entry.geometry(), button.geometry(), host.sizeHint())
    entry.setFocus()
    qapp.processEvents()
    assert (entry.geometry(), button.geometry(), host.sizeHint()) == original
    entry.setReadOnly(True)
    button.setEnabled(False)
    qapp.processEvents()
    assert (entry.geometry(), button.geometry(), host.sizeHint()) == original
    theme.deleteLater()


def test_navigation_retargets_without_queued_animations(qapp, qtbot):
    button = IconButton("下载", "download", "NavButton")
    qtbot.addWidget(button)
    button.show()
    button.setObjectName("NavButtonActive")
    repolish(button)
    qtbot.waitUntil(lambda: button._nav_transition.value > 0)
    intermediate = button._nav_transition.value
    button.setObjectName("NavButton")
    repolish(button)
    # Reversal starts at the currently rendered value rather than either end.
    assert button._nav_transition.value == pytest.approx(intermediate)
    qtbot.waitUntil(lambda: button._nav_transition.animation.state() == QAbstractAnimation.Stopped)
    assert button._nav_transition.value == 0
    button.setObjectName("NavButtonActive")
    repolish(button)
    button.hide()
    assert button._nav_transition.value == 1
    assert button._nav_transition.animation.state() == QAbstractAnimation.Stopped


def test_option_rapid_keyboard_toggle_and_disable_settle(qtbot):
    card = DownloadOptionCard("下载字幕", "SRT", "info")
    qtbot.addWidget(card)
    card.show()
    card.setFocus()
    for _ in range(3):
        qtbot.keyClick(card, Qt.Key_Space)
    assert card.isChecked()
    card.setEnabled(False)
    assert card._selection.value == 1
    assert card._selection.animation.state() == QAbstractAnimation.Stopped
    qtbot.keyClick(card, Qt.Key_Space)
    assert card.isChecked()


def test_expanding_content_and_validation_do_not_wait_for_animation(qtbot):
    section = CollapsibleSection("高级选项")
    qtbot.addWidget(section)
    section.show()
    section.toggle.click()
    assert section.content.isVisible()
    section.toggle.click()
    assert section.content.isHidden()
    section.set_expanded(True)
    assert section.content.isVisible()
    qtbot.waitUntil(lambda: section.toggle._turn.animation.state() == QAbstractAnimation.Stopped)
    assert section.toggle._turn.value == 1


def test_deterministic_previews_can_disable_motion(qapp, qtbot):
    previous = qapp.property("uiAnimationsEnabled")
    qapp.setProperty("uiAnimationsEnabled", False)
    try:
        card = DownloadOptionCard("保存封面", "图片", "folder")
        qtbot.addWidget(card)
        card.show()
        card.setChecked(True)
        qapp.sendEvent(card, QEvent(QEvent.HoverEnter))
        assert card._selection.value == card._hover.value == 1
        assert card._selection.animation.state() == QAbstractAnimation.Stopped
    finally:
        qapp.setProperty("uiAnimationsEnabled", previous)


def test_tabs_keep_keyboard_focus_without_mouse_focus_ring(qapp, qtbot):
    from PySide6.QtWidgets import QTabBar

    manager = ThemeManager(qapp)
    tabs = QTabBar()
    tabs.addTab("下载队列")
    tabs.addTab("录制历史")
    qtbot.addWidget(tabs)
    tabs.show()
    tabs.activateWindow()
    # These tests synthesize Qt input; the desktop may keep Codex or another
    # application in front after the preceding minimize/restore tests.
    qapp.setActiveWindow(tabs)
    qtbot.waitUntil(tabs.isActiveWindow)
    qtbot.mouseClick(tabs, Qt.LeftButton, pos=tabs.tabRect(1).center())
    assert tabs.property("keyboardFocus") is False
    before = tabs.sizeHint()
    tabs.clearFocus()
    tabs.setFocus(Qt.TabFocusReason)
    qapp.processEvents()
    assert tabs.property("keyboardFocus") is True
    assert tabs.sizeHint() == before
    manager.deleteLater()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_wallpaper_tabs_keep_a_readable_surface(workspace, qapp, dark, theme_id):
    from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS

    theme = ThemeManager(qapp, theme_id, "dark" if dark else "light")
    workspace._settings.appearance.backgrounds.download = BUILTIN_BACKGROUNDS[0].reference
    workspace._refresh_workspace_background()
    workspace.show()
    bar = workspace._download_tabs.tabBar()
    bar.setTabText(1, "")
    qapp.processEvents()
    image = bar.grab().toImage()
    center = bar.tabRect(1).center()
    dpr = image.devicePixelRatio()
    background = image.pixelColor(round(center.x() * dpr), round(center.y() * dpr)).name()
    colors = theme_palette(dark, theme_id)
    assert background == colors.surface
    assert contrast_ratio(colors.muted, background) >= 4.5
    theme.deleteLater()


def test_live_duration_remains_readable_at_all_window_sizes(workspace, qapp):
    row = room()
    row["duration"] = 360000  # A long-running monitor can pass 99 hours.
    workspace._live_controller.service.rows = [row]
    workspace._live_controller.refresh()
    workspace._show_workspace(1)
    workspace.show()
    for size in ((900, 640), (1120, 760), (1320, 860)):
        workspace.resize(*size)
        qapp.processEvents()
        table = workspace._live_page.rooms
        item = table.item(0, 2)
        assert item.text() == "100:00:00"
        assert table.columnWidth(2) >= table.fontMetrics().horizontalAdvance(item.text()) + 16
        assert table.horizontalScrollBar().maximum() == 0
