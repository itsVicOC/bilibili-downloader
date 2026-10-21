"""Wallpaper readability, browsing and cancellation at real widget boundaries."""

from pathlib import Path

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMimeData,
    QPoint,
    QPointF,
    Qt,
    QUrl,
)
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

from bilibili_downloader.core.appearance import BackgroundStore
from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery
from bilibili_downloader.gui.resources.styles import contrast_ratio, theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.background_picker import BackgroundPicker
from bilibili_downloader.gui.widgets.hero_panel import HeroPanel
from bilibili_downloader.gui.widgets.workspace_background import WorkspaceStack
from tests.test_builtin_backgrounds import restore_theme as restore_theme


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("card_kind", ["section", "hero"])
def test_real_labels_keep_contrast_without_covering_blank_card_space(qapp, qtbot, tmp_path, theme_id, dark, card_kind):
    theme = ThemeManager(qapp, theme_id)
    theme.apply_theme(dark)
    colors = theme_palette(dark, theme_id)
    stack = WorkspaceStack()
    qtbot.addWidget(stack)
    page = HeroPanel() if card_kind == "hero" else QWidget()
    if card_kind == "section":
        page.setObjectName("SectionCard")
    stack.addWidget(page)
    stack.resize(640, 360)
    labels = []
    for i, name in enumerate(("SectionTitle", "MetaLabel")):
        label = QLabel("背景文字", page)
        label.setObjectName(name)
        label.setGeometry(20, 30 + i * 40, 300, 30)
        labels.append(label)
    stack.show()
    for pattern in ("black", "white", "checker"):
        source = QImage(640, 360, QImage.Format_RGB32)
        source.fill(Qt.black if pattern == "black" else Qt.white)
        if pattern == "checker":
            for y in range(source.height()):
                for x in range(source.width()):
                    source.setPixelColor(x, y, Qt.black if (x // 8 + y // 8) % 2 else Qt.white)
        path = tmp_path / f"{pattern}.png"
        source.save(str(path))
        stack.set_background(path)
        stack.set_visibility(BackgroundVisibility(light=100, dark=100))
        QApplication.processEvents()
        assert stack.property("customBackground")
        for label in labels:
            label.hide()
        without_text = stack.grab().toImage()
        for label in labels:
            label.show()
        image = stack.grab().toImage()
        dpr = image.devicePixelRatio()
        for label in labels:
            x = label.fontMetrics().horizontalAdvance(label.text()) + 2
            point = label.mapTo(stack, QPoint(x, 15))
            background = image.pixelColor(round(point.x() * dpr), round(point.y() * dpr)).name()
            foreground = label.palette().color(QPalette.WindowText).name()
            assert contrast_ratio(foreground, background) >= 4.5
            assert background == without_text.pixelColor(round(point.x() * dpr), round(point.y() * dpr)).name()
        if pattern != "white":
            assert image.pixelColor(round(500 * dpr), round(200 * dpr)).name() != colors.surface
    stack.set_background(None)
    QApplication.processEvents()
    assert not stack.property("customBackground")
    image = stack.grab().toImage()
    assert image.pixelColor(round(500 * image.devicePixelRatio()), round(200 * image.devicePixelRatio())).name() == colors.surface
    theme.deleteLater()


def test_keyboard_browsing_and_preview_changes_do_not_decode_again(qtbot, tmp_path):
    picker = BackgroundPicker("任务中心", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    gallery = BackgroundGallery(picker)
    qtbot.addWidget(gallery)
    gallery.show()
    qtbot.waitUntil(lambda: gallery.scroll.viewport().width() > 200)
    assert gallery.tabs.tabText(0) == "小流"
    assert len(gallery._visible_cards) == 12
    assert all(c.recommended for c in gallery._visible_cards[:3])
    first, second = gallery._visible_cards[:2]
    first.setFocus()
    qtbot.keyClick(first, Qt.Key_Return)
    qtbot.waitUntil(lambda: not gallery.busy)
    qtbot.keyClick(first, Qt.Key_Right)
    # Cocoa test processes can remain inactive; the window still remembers
    # its focus target, which becomes active when the user activates it.
    assert gallery.focusWidget() == second
    assert gallery.reference == first.entry.reference
    qtbot.keyClick(second, Qt.Key_Space)
    qtbot.waitUntil(lambda: not gallery.busy)
    assert gallery.reference == second.entry.reference
    assert gallery.result() != QDialog.Accepted
    generation = gallery._generation
    image_key = gallery.effects.preview.pixmap.cacheKey()
    gallery.effects.slider.setValue(77)
    gallery.effects.dark_button.click()
    gallery.effects.original_button.click()
    assert not gallery.effects.preview.grab().isNull()
    assert gallery.effects.preview.original
    gallery.effects.page_button.click()
    assert gallery.effects.preview.pixmap.cacheKey() == image_key
    assert gallery._generation == generation
    assert picker.reference == ""
    assert not picker.store.directory.exists()
    for width, height in ((720, 520), (1080, 720)):
        gallery.resize(width, height)
        QApplication.processEvents()
        assert gallery.size().width() == width and gallery.size().height() == height
        if width < 900:
            assert gallery.tabs.isVisible() and gallery._preview_pane.isHidden()
            gallery._view_buttons["preview"].click()
            QApplication.processEvents()
        for widget in (gallery.apply_button, gallery.effects.preview, gallery.default_button):
            assert widget.isVisible()
            assert gallery.rect().contains(widget.mapTo(gallery, QPoint()))
            assert gallery.rect().contains(widget.mapTo(gallery, widget.rect().bottomRight()))
        assert gallery.effects.preview.visibleRegion().boundingRect().contains(gallery.effects.preview.rect())
        if width < 900:
            gallery._view_buttons["browse"].click()
            QApplication.processEvents()
        assert gallery.scroll.horizontalScrollBar().maximum() == 0
    assert gallery._generation == generation
    qtbot.keyClick(gallery, Qt.Key_Escape)
    assert gallery.result() == QDialog.Rejected
    assert picker.reference == ""


def test_file_drop_default_restore_and_stale_decodes_are_isolated(qtbot, tmp_path):
    picker = BackgroundPicker("设置", BackgroundStore(tmp_path))
    picker.set_visibility(BackgroundVisibility(light=25, dark=35))
    qtbot.addWidget(picker)
    gallery = BackgroundGallery(picker)
    qtbot.addWidget(gallery)
    gallery.show()
    source = QImage(480, 270, QImage.Format_RGB32)
    source.fill(Qt.cyan)
    path = tmp_path / "custom.png"
    source.save(str(path))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    enter = QDragEnterEvent(QPoint(20, 20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(gallery, enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(20, 20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(gallery, drop)
    assert drop.isAccepted()
    qtbot.waitUntil(lambda: not gallery.busy)
    assert gallery.prepared is not None
    assert not gallery.drop_area.image.isNull()
    assert gallery.tabs.currentIndex() == 1
    assert picker.reference == "" and picker.visibility.light == 25
    assert not picker.store.directory.exists()
    gallery.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
    stale_generation = gallery._generation
    gallery.effects.original_button.click()
    gallery.restore_default()
    gallery._decode_finished(stale_generation, source)
    assert gallery.reference == "" and gallery.prepared is None
    assert gallery.visibility == BackgroundVisibility()
    assert gallery.apply_button.isEnabled()
    assert gallery.effects.preview.pixmap.isNull()
    assert gallery.effects.page_button.isChecked()
    assert not gallery.effects.original_button.isEnabled()
    assert picker.visibility == BackgroundVisibility(light=25, dark=35)
    gallery.reject()
    gallery.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qtbot.wait(30)  # Queued decoder/timer callbacks must not access deleted cards.


def test_missing_original_is_disabled_and_default_is_available(qtbot, tmp_path, monkeypatch):
    import bilibili_downloader.gui.dialogs.background_gallery as module
    original = module.background_path
    monkeypatch.setattr(module, "background_path", lambda reference, store=None, *, thumbnail=False:
                        original(reference, store, thumbnail=True) if thumbnail else Path(tmp_path / "missing.webp"))
    picker = BackgroundPicker("视频下载", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    gallery = BackgroundGallery(picker)
    qtbot.addWidget(gallery)
    gallery.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
    qtbot.waitUntil(lambda: not gallery.busy)
    assert not gallery.apply_button.isEnabled()
    assert "丢失" in gallery.selection_label.text()
    gallery.restore_default()
    assert gallery.apply_button.isEnabled()
    assert picker.reference == ""
