"""Pixel fidelity, animation lifecycle, fallback and sidebar geometry."""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets import pixel_mascot
from bilibili_downloader.gui.widgets.pixel_mascot import FRAME_DURATIONS, PixelMascot
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(4):
        QApplication.processEvents()


def test_atlas_has_binary_alpha_shared_palette_and_stable_body():
    with Image.open(asset_path("xiaoliu_idle.png")) as source:
        atlas = source.convert("RGBA")
    with Image.open(asset_path("xiaoliu.png")) as source:
        still = source.convert("RGBA")
    assert atlas.size == (240, 40)
    assert still.size == (40, 40)
    assert len(atlas.getcolors()) <= 24
    assert {alpha for _, alpha in atlas.getchannel("A").getcolors()} == {0, 255}
    assert sum(FRAME_DURATIONS) == 4000
    base = atlas.crop((0, 0, 40, 40))
    assert base.tobytes() == still.tobytes()
    for index in range(6):
        frame = atlas.crop((index * 40, 0, (index + 1) * 40, 40))
        assert (
            frame.crop((0, 22, 40, 40)).tobytes()
            == base.crop((0, 22, 40, 40)).tobytes()
        )
    half_closed = atlas.crop((2 * 40 + 12, 13, 2 * 40 + 27, 18))
    closed = atlas.crop((3 * 40 + 12, 13, 3 * 40 + 27, 18))
    assert half_closed.tobytes() != base.crop((12, 13, 27, 18)).tobytes()
    assert closed.tobytes() != half_closed.tobytes()


@pytest.mark.parametrize("dpr", [1, 1.5, 2])
def test_paint_keeps_each_source_pixel_crisp(qtbot, dpr):
    mascot = PixelMascot()
    qtbot.addWidget(mascot)
    image = QImage(round(80 * dpr), round(80 * dpr), QImage.Format_RGBA8888)
    image.setDevicePixelRatio(dpr)
    image.fill(Qt.transparent)
    mascot.render(image)
    block = round(2 * dpr)
    for y in range(40):
        for x in range(40):
            color = image.pixelColor(x * block, y * block)
            for dy in range(block):
                for dx in range(block):
                    assert image.pixelColor(x * block + dx, y * block + dy) == color


def test_animation_pauses_when_hidden_minimized_or_inactive(qtbot, qapp, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    mascot = PixelMascot(host)
    layout.addWidget(mascot)
    active = [True]
    monkeypatch.setattr(mascot, "_application_active", lambda: active[0])
    host.show()
    flush()
    assert mascot._timer.isActive()
    mascot._timer.stop()
    mascot._advance_frame()
    assert mascot._frame_index == 1
    assert mascot._timer.interval() == FRAME_DURATIONS[1]

    mascot.hide()
    assert not mascot._timer.isActive()
    mascot.show()
    assert mascot._frame_index == 1
    assert mascot._timer.isActive()
    host.hide()
    assert not mascot._timer.isActive()
    host.show()
    flush()
    assert mascot._timer.isActive()
    host.showMinimized()
    flush()
    assert not mascot._timer.isActive()
    host.showNormal()
    flush()
    assert mascot._timer.isActive()

    active[0] = False
    qapp.applicationStateChanged.emit(Qt.ApplicationInactive)
    assert not mascot._timer.isActive()
    active[0] = True
    qapp.applicationStateChanged.emit(Qt.ApplicationActive)
    assert mascot._timer.isActive()


@pytest.mark.parametrize("bad_atlas", ["missing", "corrupt", "wrong_size"])
def test_unavailable_animation_uses_static_first_frame(
    qtbot, tmp_path, monkeypatch, bad_atlas
):
    invalid = tmp_path / "atlas.png"
    if bad_atlas == "corrupt":
        invalid.write_bytes(b"not a PNG")
    elif bad_atlas == "wrong_size":
        invalid = Path(asset_path("xiaoliu.png"))
    resolve = pixel_mascot.asset_path
    monkeypatch.setattr(
        pixel_mascot,
        "asset_path",
        lambda name: str(invalid) if name == "xiaoliu_idle.png" else resolve(name),
    )
    mascot = PixelMascot()
    qtbot.addWidget(mascot)
    monkeypatch.setattr(mascot, "_application_active", lambda: True)
    mascot.show()
    flush()
    assert mascot._frames == []
    assert not mascot._timer.isActive()
    assert not mascot._still.isNull()
    assert mascot._still.size().width() == 40
    assert not mascot.grab().isNull()


def test_frozen_bundle_loads_both_assets(qtbot, tmp_path, monkeypatch):
    import sys

    bundle = tmp_path / "bilibili_downloader/gui/assets"
    bundle.mkdir(parents=True)
    for name in ("xiaoliu.png", "xiaoliu_idle.png"):
        (bundle / name).write_bytes(Path(asset_path(name)).read_bytes())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    mascot = PixelMascot()
    qtbot.addWidget(mascot)
    assert len(mascot._frames) == 6
    assert not mascot._still.isNull()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_sidebar_fits_both_mascot_sizes_and_compact_navigation(
    workspace, qapp, monkeypatch, theme_id, dark
):
    previous = (
        qapp.font(),
        qapp.palette(),
        qapp.styleSheet(),
        qapp.property("darkTheme"),
        qapp.property("colorTheme"),
    )
    theme = ThemeManager(qapp, theme_id)
    try:
        theme.apply_theme(dark)
        window = workspace
        card = window._mascot_card
        monkeypatch.setattr(card.mascot, "_application_active", lambda: True)
        window.show()
        # Return through each mode to exercise repeated transitions.
        for width, height in (
            (1120, 640),
            (1120, 760),
            (900, 640),
            (1320, 860),
            (1120, 640),
        ):
            window.resize(width, height)
            flush()
            assert (window.width(), window.height()) == (width, height)
            for control in (
                *window._nav_buttons,
                window._settings_nav,
                window._mode_button,
                window._header_login,
            ):
                rect = QRect(control.mapTo(window._sidebar, QPoint()), control.size())
                assert window._sidebar.rect().contains(rect)
                assert (
                    not control.geometry().intersects(card.geometry())
                    or not card.isVisible()
                )
            if width < 1120:
                assert not card.isVisible()
                assert not card.mascot._timer.isActive()
                continue
            assert card.isVisible()
            required = window._side_layout.minimumSize().height() - card.minimumHeight() + card.height_for_mode(False)
            assert card._mini == (window._sidebar.height() < required)
            assert card.mascot.width() == (40 if card._mini else 80)
            assert card.mascot._timer.isActive()
            for child in (card.mascot, card.caption):
                rect = QRect(child.mapTo(card, QPoint()), child.size())
                assert card.rect().contains(rect)
            assert not card.mascot.geometry().intersects(card.caption.geometry())
    finally:
        qapp.setFont(previous[0])
        qapp.setPalette(previous[1])
        qapp.setStyleSheet(previous[2])
        qapp.setProperty("darkTheme", previous[3])
        qapp.setProperty("colorTheme", previous[4])
        theme.deleteLater()
