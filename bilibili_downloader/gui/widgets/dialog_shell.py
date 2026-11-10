"""Dialog bounds and focus restoration, independent of dialog implementations."""

import weakref

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QPlainTextEdit, QPushButton
from shiboken6 import isValid

from bilibili_downloader.gui.window_bounds import ScreenBounds


def prepare_dialog(dialog):
    if not dialog.isWindow():
        return
    if not hasattr(dialog, "_screen_bounds"):
        dialog._screen_bounds = ScreenBounds(dialog, QSize(min(420, dialog.minimumWidth()), 0))
    dialog._screen_bounds.schedule()
    for button in dialog.findChildren(QPushButton):
        button.setAutoDefault(False)


def restore_focus(dialog):
    reference = getattr(dialog, "_return_focus", None)
    target = reference() if reference else None
    if dialog.isWindow() and target is not None and isValid(target) and target.isVisible() and target.isEnabled():
        target.setFocus(Qt.TabFocusReason if dialog._return_keyboard else Qt.OtherFocusReason)


def remember_focus(dialog, parent):
    target = parent.window().focusWidget() if parent else None
    dialog._return_focus = weakref.ref(target) if target else None
    dialog._return_keyboard = bool(target and target.property("keyboardFocus"))
    reference = weakref.ref(dialog)
    def finished(_):
        current = reference()
        if current is not None and isValid(current):
            restore_focus(current)
    dialog.finished.connect(finished)


class AppDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        remember_focus(self, parent)

    def showEvent(self, event):
        prepare_dialog(self)
        super().showEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and isinstance(self.focusWidget(), (QLineEdit, QPlainTextEdit)):
            event.accept()
            return
        super().keyPressEvent(event)
