"""Real file windows: responsive event loop, acceptance, cancellation and ownership."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from bilibili_downloader.core.appearance import BackgroundStore
from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery
from bilibili_downloader.gui.dialogs.file_picker import file_picker
from bilibili_downloader.gui.widgets.background_picker import BackgroundPicker


@pytest.fixture(autouse=True)
def no_blocking_file_dialog(monkeypatch, qapp):
    def blocked(*_args, **_kwargs):
        pytest.fail("File selection must return immediately without exec/static native calls")
    for method in ("exec", "getExistingDirectory", "getOpenFileName", "getSaveFileName"):
        monkeypatch.setattr(QFileDialog, method, blocked)
    # Unexpected QFileDialog validation must fail instead of leaving CI in a
    # system NSAlert modal loop, which cannot be dismissed by pytest-qt.
    previous = qapp.testAttribute(Qt.AA_DontUseNativeDialogs)
    qapp.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    errors = []
    def close_unexpected_message():
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMessageBox) and widget.isVisible():
                errors.append(widget.text())
                widget.reject()
    watchdog = QTimer()
    watchdog.timeout.connect(close_unexpected_message)
    watchdog.start(10)
    yield
    watchdog.stop()
    qapp.setAttribute(Qt.AA_DontUseNativeDialogs, previous)
    assert not errors


@pytest.mark.parametrize("kind", ["directory", "open_file", "save_file"])
def test_real_file_window_returns_immediately_and_keeps_timers_running(qtbot, tmp_path, kind):
    window = QWidget()
    qtbot.addWidget(window)
    owner = QWidget(window)
    QVBoxLayout(window).addWidget(owner)
    window.show()
    picker, selected = file_picker(owner), []
    ticks = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    if kind == "directory":
        dialog = picker.directory("选择目录", str(tmp_path), selected.append)
    elif kind == "open_file":
        dialog = picker.open_file("选择图片", "", "PNG (*.png)", selected.append)
    else:
        dialog = picker.save_file("导出", str(tmp_path / "new.mp4"), "MP4 (*.mp4)", selected.append, suffix="mp4")
    assert picker.dialog is dialog and dialog.isVisible()
    assert dialog.parentWidget() is window
    assert dialog.windowModality() == Qt.WindowModal
    assert not dialog.windowFlags() & getattr(Qt, "ExpandedClientAreaHint", 0)
    assert dialog.testOption(QFileDialog.DontUseNativeDialog) == (sys.platform == "darwin")
    qtbot.waitUntil(lambda: len(ticks) >= 3)
    assert file_picker(owner) is picker
    assert picker.directory("重复点击", "", selected.append) is dialog
    qtbot.keyClick(dialog, Qt.Key_Escape)
    qtbot.waitUntil(lambda: picker.dialog is None)
    assert not selected and window.isEnabled()
    timer.stop()


@pytest.mark.parametrize("kind", ["directory", "open_file", "save_file"])
def test_file_selection_is_committed_once_and_reopens_after_cancel(qtbot, tmp_path, kind):
    owner = QWidget()
    qtbot.addWidget(owner)
    owner.show()
    picker, selected = file_picker(owner), []
    picker.directory("先取消", str(tmp_path), selected.append).reject()
    assert picker.dialog is None and not selected
    if kind == "directory":
        path = tmp_path / "chosen directory"
        path.mkdir()
        dialog = picker.directory("目录", str(tmp_path), selected.append)
    elif kind == "open_file":
        path = tmp_path / "sample.png"
        image = QImage(32, 32, QImage.Format_RGB32)
        image.fill(Qt.cyan)
        image.save(str(path))
        dialog = picker.open_file("图片", str(path), "PNG (*.png)", selected.append)
    else:
        path = tmp_path / "recording.mp4"
        dialog = picker.save_file("导出", str(path), "MP4 (*.mp4)", selected.append, suffix="mp4")
    # selectFile deliberately leaves a focused, visible filename editor alone.
    dialog.findChild(QLineEdit, "fileNameEdit").setText(str(path))
    assert [Path(selected_path) for selected_path in dialog.selectedFiles()] == [path]
    dialog.accept()
    qtbot.waitUntil(lambda: picker.dialog is None)
    assert selected == [str(path)]
    qtbot.wait(20)
    assert selected == [str(path)]
    if kind == "save_file":
        assert not path.exists()  # Selection does not itself create or export a file.


@pytest.mark.parametrize("action", ["hide", "close", "delete"])
def test_owner_disappearance_closes_picker_without_applying_late_result(qtbot, tmp_path, action):
    owner = QWidget()
    if action != "delete":
        qtbot.addWidget(owner)
    owner.show()
    picker, selected = file_picker(owner), []
    dialog = picker.directory("目录", str(tmp_path), selected.append)
    if action == "delete":
        owner.deleteLater()
        qtbot.waitUntil(lambda: not isValid(owner))
    else:
        getattr(owner, action)()
    qtbot.waitUntil(lambda: not isValid(dialog) or not dialog.isVisible())
    assert not selected


def test_gallery_image_window_stays_above_gallery_and_import_is_still_a_draft(qtbot, tmp_path):
    source = tmp_path / "source.png"
    image = QImage(48, 32, QImage.Format_RGB32)
    image.fill(Qt.blue)
    image.save(str(source))
    background = BackgroundPicker("视频下载", BackgroundStore(tmp_path / "store"), workspace="download")
    qtbot.addWidget(background)
    gallery = BackgroundGallery(background)
    qtbot.addWidget(gallery)
    gallery.show()
    gallery.tabs.setCurrentIndex(1)
    gallery.import_button.click()
    picker = gallery._file_picker
    assert picker.dialog.isVisible() and picker.dialog.parentWidget() is gallery
    assert picker.dialog.fileMode() == QFileDialog.ExistingFile
    picker.dialog.reject()
    assert gallery.reference == "" and background.reference == ""
    gallery.import_button.click()
    picker.dialog.findChild(QLineEdit, "fileNameEdit").setText(str(source))
    picker.dialog.accept()
    qtbot.waitUntil(lambda: picker.dialog is None and gallery.prepared is not None)
    assert not gallery.busy and gallery.apply_button.isEnabled()
    assert background.reference == "" and not background.store.directory.exists()
    gallery.import_button.click()
    pending = picker.dialog
    gallery.reject()
    qtbot.waitUntil(lambda: not isValid(pending) or not pending.isVisible())
    assert background.reference == "" and gallery.result() == QDialog.Rejected
