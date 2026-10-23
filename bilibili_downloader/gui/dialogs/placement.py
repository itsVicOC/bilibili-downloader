"""Keep application dialogs on the parent's available desktop work area."""

from PySide6.QtCore import QEvent, QObject, QRect, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
from shiboken6 import isValid

from bilibili_downloader.gui.window_state import fit_rect


def fit_dialog(dialog, *, center=False):
    if not isValid(dialog) or not dialog.isVisible() or not dialog.isWindow():
        return
    parent = dialog.parentWidget()
    screen = parent.screen() if parent else dialog.screen()
    if not screen:
        return
    available = screen.availableGeometry().adjusted(8, 8, -8, -8)
    frame = dialog.frameGeometry()
    decoration = frame.size() - dialog.size()
    dialog.setMinimumSize(min(dialog.minimumWidth(), max(1, available.width() - max(0, decoration.width()))),
                          min(dialog.minimumHeight(), max(1, available.height() - max(0, decoration.height()))))
    rect = QRect(frame.topLeft(), dialog.size())
    if center:
        rect.moveCenter(parent.frameGeometry().center() if parent else available.center())
    rect = fit_rect(rect, available, decoration)
    dialog.resize(rect.size())
    dialog.move(rect.topLeft())


class DialogPlacement(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, target, event):
        if event.type() == QEvent.Show and isinstance(target, QDialog) and target.isWindow():
            if isinstance(target, QFileDialog) and not target.testOption(QFileDialog.DontUseNativeDialog):
                return False
            first = not target.property("placementFitted")
            target.setProperty("placementFitted", True)
            QTimer.singleShot(0, lambda: fit_dialog(target, center=first))
        return False
