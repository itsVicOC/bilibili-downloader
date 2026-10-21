"""Owned, asynchronous file dialogs without a nested native modal loop."""

import os
import sys

from PySide6.QtCore import QDir, QEvent, QObject, Qt
from PySide6.QtWidgets import QDialog, QFileDialog
from shiboken6 import isValid


class FilePicker(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.dialog = None
        self._selected = None
        owner.installEventFilter(self)

    def directory(self, title, start, selected):
        return self._open(title, start, selected, QFileDialog.Directory)

    def open_file(self, title, start, name_filter, selected):
        return self._open(title, start, selected, QFileDialog.ExistingFile, name_filter)

    def save_file(self, title, start, name_filter, selected, *, suffix=""):
        return self._open(title, start, selected, QFileDialog.AnyFile, name_filter, suffix)

    def _open(self, title, start, selected, mode, name_filter="", suffix=""):
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return self.dialog
        owner = self.parent()
        # An embedded SettingsDialog is a Qt.Widget: attach to its real window.
        dialog = QFileDialog(owner.window())
        # On macOS avoid the invisible NSOpenPanel / blocked-parent failure.
        # Set the option before configuring or showing the dialog (Qt requirement).
        dialog.setOption(QFileDialog.DontUseNativeDialog, sys.platform == "darwin")
        dialog.setOption(QFileDialog.DontUseCustomDirectoryIcons, True)
        dialog.setWindowTitle(title)
        dialog.setFileMode(mode)
        dialog.setWindowModality(Qt.WindowModal)
        saving = mode == QFileDialog.AnyFile
        dialog.setAcceptMode(QFileDialog.AcceptSave if saving else QFileDialog.AcceptOpen)
        dialog.setLabelText(QFileDialog.LookIn, "位置")
        dialog.setLabelText(QFileDialog.FileName, "目录" if mode == QFileDialog.Directory else "文件名")
        dialog.setLabelText(QFileDialog.FileType, "文件类型")
        dialog.setLabelText(QFileDialog.Accept, "保存" if saving else "选择")
        dialog.setLabelText(QFileDialog.Reject, "取消")
        if mode == QFileDialog.Directory:
            dialog.setOption(QFileDialog.ShowDirsOnly, True)
            if start:
                dialog.setDirectory(os.path.expanduser(start))
        elif start:
            dialog.selectFile(os.path.expanduser(start))
        if name_filter:
            dialog.setNameFilter(name_filter)
        if suffix:
            dialog.setDefaultSuffix(suffix)
        self.dialog, self._selected = dialog, selected
        owner.destroyed.connect(dialog.reject)
        dialog.finished.connect(self._finished)
        dialog.resize(760, 520)
        dialog.open()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _finished(self, result):
        dialog, selected = self.dialog, self._selected
        if dialog is None:
            return
        paths = dialog.selectedFiles() if result == QDialog.Accepted else []
        self.dialog, self._selected = None, None
        dialog.deleteLater()
        owner = self.parent()
        if paths and isValid(owner) and owner.isVisible():
            # Qt returns forward slashes on Windows; keep stored/displayed paths native.
            selected(QDir.toNativeSeparators(paths[0]))

    def cancel(self):
        if self.dialog is not None:
            self.dialog.reject()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Hide, QEvent.Close):
            self.cancel()
        return False


def file_picker(owner):
    """Keep one picker alive per owner, including during window-modal selection."""
    picker = getattr(owner, "_file_picker", None)
    if picker is None:
        picker = owner._file_picker = FilePicker(owner)
    return picker
