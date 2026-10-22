"""Interaction, accessibility and lifecycle regressions for Fluent state layers."""

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, Qt
from PySide6.QtWidgets import QLineEdit, QPushButton, QVBoxLayout, QWidget

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
    for surface in (p.surface, p.control_fill, p.popup, p.subtle_selection):
        for text in (p.text, p.muted, p.active_text):
            assert contrast_ratio(text, surface) >= 4.5
    for tone in ("success", "warning", "danger", "active"):
        text = p.active_text if tone == "active" else getattr(p, tone)
        assert contrast_ratio(text, p.tone_surface(tone)) >= 4.5


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
