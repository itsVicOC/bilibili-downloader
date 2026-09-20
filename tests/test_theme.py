"""Tests for day and night stylesheet generation."""

from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.resources.styles import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    UI_METRICS,
    scale_font_sizes,
)


def test_dark_and_light_styles_are_distinct():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert dark != light
    assert "background-color: #15151a" in dark
    assert "background-color: #f5f5f8" in light


def test_macos_typography_scale_increases_all_point_sizes():
    scaled = load_stylesheet(True, font_scale=1.15)

    assert "font-size: 11.5pt;" in scaled
    assert "font-size: 23.2875pt;" in scaled
    assert scale_font_sizes("font-size: 10pt;", 1.0) == "font-size: 10pt;"


def test_light_theme_overrides_core_surfaces():
    light = load_stylesheet(False)

    assert "#Sidebar" in light
    assert "QTableWidget" in light
    assert "QDialog" in light
    assert "background-color: #ffffff" in light


def test_styles_use_compact_scrollbars_with_interaction_states():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QScrollBar::handle:vertical" in dark
    assert "width: 10px" in dark
    assert "min-height: 32px" in dark
    assert "QScrollBar::handle:vertical:hover" in dark
    assert "background-color: #c5c0c9" in light


def test_spinbox_uses_segmented_stepper_controls():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QPushButton#StepperButton" in dark
    assert "min-width: 36px" in dark
    assert "background-color: #24232a" in dark
    assert "background-color: #f3f1f5" in light


def test_login_instructions_use_a_non_scrolling_information_surface():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert "QLabel#LoginInstructions" in dark
    assert "background-color: #19191f" in dark
    assert "background-color: #f8f6f9" in light


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
    assert UI_METRICS.control_height == 36
    assert UI_METRICS.compact_button_height == 32
    assert UI_METRICS.primary_height == 44


def test_theme_tokens_meet_text_and_control_contrast_targets():
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        assert _contrast(palette.text, palette.surface) >= 4.5
        assert _contrast(palette.muted, palette.surface) >= 4.5
        assert _contrast(palette.border, palette.surface) >= 3.0
        assert _contrast(palette.accent_text, palette.accent) >= 4.5


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _luminance(color: str) -> float:
    values = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92
        if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
