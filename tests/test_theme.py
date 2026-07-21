"""Tests for day and night stylesheet generation."""

from bilibili_downloader.gui.resources import load_stylesheet


def test_dark_and_light_styles_are_distinct():
    dark = load_stylesheet(True)
    light = load_stylesheet(False)

    assert dark != light
    assert "background-color: #15151a" in dark
    assert "background-color: #f5f5f8" in light


def test_light_theme_overrides_core_surfaces():
    light = load_stylesheet(False)

    assert "#Sidebar" in light
    assert "QTableWidget" in light
    assert "QDialog" in light
    assert "background-color: #ffffff" in light
