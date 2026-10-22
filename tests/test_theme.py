"""Tests for day and night stylesheet generation."""

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QFocusEvent, QFont, QFontInfo, QFontMetricsF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.resources.styles import (
    BLUE_DARK_PALETTE,
    BLUE_LIGHT_PALETTE,
    DARK_PALETTE,
    LIGHT_PALETTE,
    UI_METRICS,
    background_overlay_alpha,
    background_reading_alpha,
    readable_fill_text,
    scale_font_sizes,
    theme_palette,
)
from bilibili_downloader.gui.resources.theme import ThemeManager, platform_font_scale


def test_dark_and_light_styles_are_distinct():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert dark != light
    assert "background: #14131b" in dark
    assert "background: #f7f5fb" in light


@pytest.mark.parametrize("reason,visible", [
    (Qt.ActiveWindowFocusReason, False), (Qt.OtherFocusReason, False),
    (Qt.MouseFocusReason, False), (Qt.TabFocusReason, True),
    (Qt.BacktabFocusReason, True), (Qt.ShortcutFocusReason, True),
])
def test_button_activation_does_not_show_a_keyboard_outline(qapp, qtbot, reason, visible):
    from bilibili_downloader.gui.resources.theme import _ButtonFocusFilter

    button = QPushButton("视频下载")
    qtbot.addWidget(button)
    focus_filter = _ButtonFocusFilter(button)
    button.installEventFilter(focus_filter)
    QCoreApplication.sendEvent(button, QFocusEvent(QEvent.FocusIn, reason))
    assert button.property("keyboardFocus") is visible


def test_macos_typography_scale_increases_all_point_sizes():
    scaled = load_stylesheet(True, font_scale=1.15)

    assert "font-size: 12.075pt;" in scaled
    assert "font-size: 20.7pt;" in scaled
    assert scale_font_sizes("font-size: 10pt;", 1.0) == "font-size: 10pt;"


@pytest.mark.parametrize("dpi", [72.0, 96.0, 144.0])
def test_macos_point_conversion_preserves_reference_size(dpi):
    scale = platform_font_scale("darwin", dpi)
    assert 10.5 * scale * dpi / 72 == pytest.approx(14)
    assert platform_font_scale("win32", dpi) == 1.0
    assert platform_font_scale("linux", dpi) == 1.0


def test_theme_applies_same_font_to_body_and_native_bold_labels(qapp, qtbot):
    previous = (
        QFont(qapp.font()), qapp.styleSheet(), qapp.palette(), qapp.property("darkTheme")
    )
    theme = ThemeManager(qapp)
    try:
        body = QLineEdit("1080P60")
        heading = QLabel("视频下载")
        heading.setObjectName("PageTitle")
        dialog_heading = QLabel("连接 B 站账号")
        dialog_heading.setObjectName("DialogTitle")
        for widget in (body, heading, dialog_heading):
            qtbot.addWidget(widget)
            widget.ensurePolished()
        dpi = qapp.primaryScreen().logicalDotsPerInchY()
        reference_dpi = 96 if sys.platform == "darwin" else dpi
        for widget, points in ((body, 10.5), (heading, None), (dialog_heading, 18)):
            info = QFontInfo(widget.font())
            assert info.family() == QFontInfo(qapp.font()).family()
            # Windows can report -1 for a point-sized font's pixelSize().
            # Compare actual paint-device metrics against the intended size.
            expected = QFont(qapp.font())
            if points is None:
                expected.setPixelSize(18)
            else:
                expected.setPointSizeF(points * reference_dpi / dpi)
            expected.setWeight(widget.font().weight())
            actual_metrics = QFontMetricsF(widget.font(), widget)
            expected_metrics = QFontMetricsF(expected, widget)
            assert actual_metrics.height() == pytest.approx(
                expected_metrics.height(), abs=0.5
            )
            assert actual_metrics.horizontalAdvance("视频下载1080P60") == pytest.approx(
                expected_metrics.horizontalAdvance("视频下载1080P60"), abs=0.5
            )
    finally:
        qapp.styleHints().colorSchemeChanged.disconnect(theme._on_color_scheme_changed)
        theme.deleteLater()
        qapp.setFont(previous[0])
        qapp.setPalette(previous[2])
        qapp.setProperty("darkTheme", previous[3])
        qapp.setStyleSheet(previous[1])


def test_light_theme_overrides_core_surfaces():
    light = load_stylesheet(False)

    assert "#Sidebar" in light
    assert "QTableWidget" in light
    assert "QDialog" in light
    assert "background: #ffffff" in light


def test_styles_use_compact_scrollbars_with_interaction_states():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QScrollBar::handle:vertical" in dark
    assert "width: 10px" in dark
    assert "min-height: 32px" in dark
    assert "QScrollBar::handle:vertical:hover" in dark
    assert "background: #8b8098" in light


def test_spinbox_uses_segmented_stepper_controls():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QPushButton#StepperButton" in dark
    assert "min-width: 32px" in dark
    assert "background: #292635" in dark
    assert "background: #f0edf6" in light


def test_login_instructions_use_a_non_scrolling_information_surface():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QLabel#LoginInstructions" in dark
    assert "background: #292635" in dark
    assert "background: #f0edf6" in light


def test_checkbox_focus_is_local_and_uses_product_accent():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QCheckBox::indicator:focus" in dark
    assert "QCheckBox:focus::indicator" not in dark
    assert "border: 2px solid #ff9ac5" in dark
    assert "QCheckBox::indicator:disabled" in light
    assert "__CHECKMARK_ICON__" not in dark
    assert "checkmark.svg" in dark
    assert "border: 2px solid #62d5ff" not in dark
    assert "border-color: #007f9f" not in light


def test_semantic_button_layer_covers_interaction_states():
    dark = load_stylesheet(True)

    assert "QPushButton#PrimaryButton:pressed" in dark
    assert "QPushButton#PrimaryButton:disabled" in dark
    assert "QPushButton#DangerButton:pressed" in dark
    assert "QPushButton#TablePrimaryButton" in dark
    assert "QPushButton#TableDangerButton:disabled" in dark
    assert UI_METRICS.control_height == 40
    assert UI_METRICS.compact_button_height == 32
    assert UI_METRICS.primary_height == 44


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_primary_buttons_share_keyboard_focus_without_a_permanent_outline(qapp, qtbot, theme_id, dark):
    previous = (qapp.styleSheet(), QFont(qapp.font()), qapp.palette(),
                qapp.property("darkTheme"), qapp.property("colorTheme"))
    theme = ThemeManager(qapp, theme_id)
    theme.apply_theme(dark)
    window = QWidget()
    qtbot.addWidget(window)
    row = QHBoxLayout(window)
    buttons = []
    for role in ("PrimaryButton", "OutputPrimaryButton"):
        button = QPushButton("确认")
        button.setObjectName(role)
        button.setFixedSize(160, 44)
        row.addWidget(button)
        buttons.append(button)
    try:
        window.show()
        window.activateWindow()
        qtbot.waitUntil(window.isActiveWindow)
        p = theme_palette(dark, theme_id)
        focus_color = p.primary_text or p.accent_text
        for button in buttons:
            qtbot.mouseClick(button, Qt.LeftButton)
            # Cocoa may leave mouse-clicked buttons unfocused according to
            # Full Keyboard Access. Exercise the mouse focus visual explicitly.
            button.setFocus(Qt.MouseFocusReason)
            assert button.hasFocus()
            assert button.grab().toImage().pixelColor(1, 22).name() != focus_color
        if qapp.platformName() == "cocoa":
            # Tab traversal follows macOS Full Keyboard Access. Test the visual
            # focus reason without changing that system preference.
            buttons[0].setFocus(Qt.TabFocusReason)
        else:
            qtbot.keyClick(buttons[1], Qt.Key_Tab)
        assert buttons[0].hasFocus()
        assert buttons[0].grab().toImage().pixelColor(1, 22).name() == focus_color
        if qapp.platformName() == "cocoa":
            buttons[1].setFocus(Qt.TabFocusReason)
        else:
            qtbot.keyClick(buttons[0], Qt.Key_Tab)
        assert buttons[1].hasFocus()
        assert buttons[1].grab().toImage().pixelColor(1, 22).name() == focus_color
        with qtbot.waitSignal(buttons[1].clicked):
            qtbot.keyClick(buttons[1], Qt.Key_Space)
    finally:
        window.close()
        theme.deleteLater()
        qapp.setProperty("darkTheme", previous[3])
        qapp.setProperty("colorTheme", previous[4])
        qapp.setPalette(previous[2])
        qapp.setFont(previous[1])
        qapp.setStyleSheet(previous[0])


def test_theme_tokens_meet_text_and_control_contrast_targets():
    for palette in (DARK_PALETTE, LIGHT_PALETTE, BLUE_DARK_PALETTE, BLUE_LIGHT_PALETTE):
        assert _contrast(palette.text, palette.surface) >= 4.5
        assert _contrast(palette.muted, palette.surface) >= 4.5
        assert _contrast(palette.border, palette.surface) >= 3.0
        assert _contrast(palette.accent_text, palette.accent) >= 4.5
        assert _contrast(palette.muted, palette.surface_raised) >= 4.5
        assert _contrast(palette.border, palette.surface_raised) >= 3.0
        assert _contrast(palette.focus, palette.surface) >= 3.0
        for foreground in (
            palette.text,
            palette.muted,
            palette.active_text,
            palette.success,
            palette.warning,
            palette.danger,
        ):
            assert _contrast(foreground, palette.surface_raised) >= 4.5
        for fill in (
            palette.accent,
            palette.success,
            palette.warning,
            palette.border,
            palette.danger_border,
        ):
            assert _contrast(readable_fill_text(fill, palette.accent_text), fill) >= 4.5
        # Official Bilibili pink/white is an explicit brand choice; retain AA
        # for the blue primary and all ordinary text/selection surfaces.
        for fill in (palette.primary, palette.primary_hover, palette.primary_pressed):
            if palette in (BLUE_DARK_PALETTE, BLUE_LIGHT_PALETTE):
                assert _contrast(palette.primary_text, fill) >= 4.5
        assert _contrast(palette.text_selection_text, palette.text_selection) >= 4.5
        assert _contrast(palette.text_selection, palette.control_fill) >= 2.0


@pytest.mark.parametrize("dark, expected", [
    (False, ("#ff6699", "#ff8cb0", "#e84b85")),
    (True, ("#d44e7d", "#dc6d94", "#a73e65")),
])
def test_pink_primary_uses_bilibili_white_text_and_official_pink_steps(dark, expected):
    p = theme_palette(dark)
    assert (p.primary, p.primary_hover, p.primary_pressed) == expected
    assert p.primary_text == "#ffffff"


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [True, False])
def test_local_reading_surfaces_preserve_contrast_over_extreme_images(theme_id, dark):
    p = theme_palette(dark, theme_id)
    assert background_overlay_alpha(dark, theme_id) == round(255 * (.2 if dark else .1))
    for foreground in (p.text, p.muted, p.active_text, p.success, p.warning, p.danger):
        alpha = background_reading_alpha(p.surface, foreground) / 255
        for image_channel in (0, 255):
            background = "#" + "".join(
                f"{round(int(p.surface[i:i + 2], 16) * alpha + image_channel * (1 - alpha)):02x}"
                for i in (1, 3, 5)
            )
            assert _contrast(foreground, background) >= 4.5


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
def test_source_input_card_uses_a_plain_readable_surface(qapp, qtbot, dark, theme_id):
    from bilibili_downloader.gui.widgets.hero_panel import HeroPanel

    previous = (qapp.property("darkTheme"), qapp.property("colorTheme"))
    try:
        qapp.setProperty("darkTheme", dark)
        qapp.setProperty("colorTheme", theme_id)
        hero = HeroPanel()
        qtbot.addWidget(hero)
        hero.resize(800, 190)
        image = hero.grab().toImage()
        p = theme_palette(dark, theme_id)
        for x in range(20, 780, 40):
            for y in (20, 50, 100, 170):
                background = image.pixelColor(x, y).name()
                assert background == p.surface
                assert _contrast(p.active_text, background) >= 4.5
                assert _contrast(p.text, background) >= 4.5
    finally:
        qapp.setProperty("darkTheme", previous[0])
        qapp.setProperty("colorTheme", previous[1])


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [True, False])
def test_workspace_header_has_one_quiet_surface(theme_id, dark):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter

    from bilibili_downloader.gui.widgets.header_backdrop import paint_header_backdrop

    image = QImage(1320, 56, QImage.Format_RGB32)
    painter = QPainter(image)
    paint_header_backdrop(painter, QRect(0, 0, 1320, 56), dark, theme_id)
    painter.end()
    p = theme_palette(dark, theme_id)
    assert image.pixelColor(24, 32).name() == p.background
    assert image.pixelColor(1200, 55).name() == p.divider
    for x in range(20, 1300, 20):
        for y in (8, 24, 44):
            background = image.pixelColor(x, y).name()
            assert background == p.background
            assert _contrast(p.text, background) >= 4.5
            assert _contrast(p.muted, background) >= 4.5


def test_status_badges_keep_semantic_colors_under_the_shared_stylesheet(qapp, qtbot):
    from PySide6.QtGui import QPalette

    from bilibili_downloader.gui.widgets.components import StatusBadge

    previous = qapp.styleSheet()
    try:
        for dark, palette in ((True, DARK_PALETTE), (False, LIGHT_PALETTE)):
            qapp.setStyleSheet(load_stylesheet(dark))
            for tone, color in (
                ("active", palette.active_text),
                ("success", palette.success),
                ("warning", palette.warning),
                ("danger", palette.danger),
            ):
                badge = StatusBadge("状态", tone)
                qtbot.addWidget(badge)
                badge.ensurePolished()
                assert badge.palette().color(QPalette.WindowText).name() == color
    finally:
        qapp.setStyleSheet(previous)


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _luminance(color: str) -> float:
    values = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
