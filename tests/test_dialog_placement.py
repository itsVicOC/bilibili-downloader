"""Dialogs use global owner geometry without taking over subsequent movement."""

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QVBoxLayout, QWidget

from bilibili_downloader.gui.dialogs.placement import (
    DialogPlacement,
    dialog_geometry,
)
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.components import MessageBox


def centered(dialog, owner):
    return (dialog.frameGeometry().center() - owner.frameGeometry().center()).manhattanLength() <= 2


@pytest.fixture
def owner(qapp, qtbot):
    window = QWidget()
    qtbot.addWidget(window)
    available = window.screen().availableGeometry()
    window.resize(600, 520)
    window.move(available.topLeft() + QPoint(100, 100))
    window._placement = DialogPlacement(window)
    panel = QDialog(window)
    panel.setWindowFlags(Qt.Widget)
    QVBoxLayout(window).addWidget(panel)
    panel._source = QWidget(panel)
    panel._source.setGeometry(15, 20, 250, 120)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(80)
    window._panel = panel
    return window


@pytest.mark.parametrize("kind", ["plain", "workflow", "message", "long_message", "file_picker"])
def test_dialog_from_nested_page_centers_on_the_actual_window(owner, qtbot, kind):
    source = owner._panel._source
    if kind == "workflow":
        dialog = WorkflowDialog("选择分 P", parent=source, width=420)
    elif kind == "long_message":
        dialog = MessageBox("处理结果", "演示诊断信息\n" * 40, source)
    elif kind == "message":
        dialog = MessageBox("处理结果", "媒体已保存，字幕待补全。", source)
    elif kind == "file_picker":
        dialog = QFileDialog(source)
        dialog.setOption(QFileDialog.DontUseNativeDialog)
    else:
        dialog = QDialog(source)
    qtbot.addWidget(dialog)
    dialog.resize(440, 300)
    dialog.show()
    qtbot.waitUntil(lambda: centered(dialog, owner))
    qtbot.wait(100)
    assert centered(dialog, owner)
    assert not owner._panel.property("placementFitted")


def test_nested_dialog_centers_on_its_dialog_owner(owner, qtbot):
    parent = QDialog(owner._panel)
    qtbot.addWidget(parent)
    parent.resize(500, 400)
    parent.show()
    qtbot.waitUntil(lambda: centered(parent, owner))
    parent.move(parent.pos() + QPoint(30, 20))
    dialog = MessageBox("验证结果", "请检查后继续。", parent)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: centered(dialog, parent))


def test_reopening_uses_the_moved_and_resized_owner(owner, qtbot):
    dialog = QDialog(owner._panel)
    qtbot.addWidget(dialog)
    dialog.resize(240, 180)
    dialog.show()
    qtbot.waitUntil(lambda: centered(dialog, owner))
    dialog.hide()
    owner.move(owner.pos() + QPoint(45, -20))
    owner.resize(620, 500)
    qtbot.wait(30)
    dialog.show()
    qtbot.waitUntil(lambda: centered(dialog, owner))


def test_dialog_can_be_moved_after_opening(owner, qtbot):
    dialog = QDialog(owner._panel)
    qtbot.addWidget(dialog)
    dialog.resize(240, 180)
    dialog.show()
    qtbot.waitUntil(lambda: centered(dialog, owner))
    qtbot.wait(30)
    destination = dialog.frameGeometry().topLeft() + QPoint(30, 20)
    dialog.move(destination)
    qtbot.wait(100)
    assert (dialog.frameGeometry().topLeft() - destination).manhattanLength() <= 2


def test_other_window_dialog_is_not_repositioned(owner, qtbot):
    other = QWidget()
    qtbot.addWidget(other)
    other.show()
    dialog = QDialog(other)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(30)
    assert not dialog.property("placementFitted")


@pytest.mark.parametrize(
    "available,owner_frame,size,decoration",
    [
        (QRect(0, 0, 1920, 1040), QRect(500, 200, 900, 640), QSize(500, 350), QSize(16, 39)),
        (QRect(-1920, 0, 1920, 1040), QRect(-1600, 100, 900, 640), QSize(500, 350), QSize(0, 28)),
        (QRect(1920, 0, 1280, 720), QRect(3000, 450, 900, 640), QSize(500, 350), QSize(16, 39)),
        (QRect(0, 24, 720, 456), QRect(0, 24, 720, 456), QSize(1000, 800), QSize(16, 39)),
    ],
)
def test_global_geometry_centers_the_outer_frame_and_respects_screen(available, owner_frame, size, decoration):
    rect = dialog_geometry(size, decoration, available, owner_frame)
    outer = QRect(rect.topLeft(), rect.size() + decoration)
    assert available.contains(outer)
    desired = QRect(QPoint(), outer.size())
    desired.moveCenter(owner_frame.center())
    if available.contains(desired):
        # QRect integer centers may round by one pixel at negative coordinates.
        assert (outer.center() - owner_frame.center()).manhattanLength() <= 1


def test_parentless_geometry_uses_the_available_desktop():
    available = QRect(-1600, 24, 1600, 876)
    rect = dialog_geometry(QSize(500, 350), QSize(0, 28), available)
    outer = QRect(rect.topLeft(), rect.size() + QSize(0, 28))
    assert (outer.center() - available.center()).manhattanLength() <= 1
