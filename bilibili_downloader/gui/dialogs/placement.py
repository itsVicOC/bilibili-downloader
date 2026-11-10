"""Keep application dialogs on the parent's available desktop work area."""

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
from shiboken6 import isValid

from bilibili_downloader.gui.window_state import fit_rect


def dialog_geometry(size, decoration, available, owner_frame=None):
    """Return client size and global frame position, including native chrome."""
    rect = fit_rect(QRect(QPoint(), size), available, decoration)
    frame = QRect(QPoint(), rect.size() + decoration)
    frame.moveCenter(owner_frame.center() if owner_frame is not None else available.center())
    rect.moveTopLeft(frame.topLeft())
    return fit_rect(rect, available, decoration)


def fit_dialog(dialog, *, center=False):
    if not isValid(dialog) or not dialog.isVisible() or not dialog.isWindow():
        return
    parent = dialog.parentWidget()
    # Embedded pages use local coordinates. Only a real top-level window has
    # the global frame geometry needed to position a separate dialog.
    owner = parent.window() if parent else None
    screen = owner.screen() if owner else dialog.screen()
    if not screen:
        return
    available = screen.availableGeometry().adjusted(8, 8, -8, -8)
    frame = dialog.frameGeometry()
    decoration = frame.size() - dialog.size()
    dialog.setMinimumSize(min(dialog.minimumWidth(), max(1, available.width() - max(0, decoration.width()))),
                          min(dialog.minimumHeight(), max(1, available.height() - max(0, decoration.height()))))
    rect = QRect(frame.topLeft(), dialog.size())
    rect = (dialog_geometry(dialog.size(), decoration, available,
                            owner.frameGeometry() if owner else None)
            if center else fit_rect(rect, available, decoration))
    if dialog.size() != rect.size():
        dialog.resize(rect.size())
    if dialog.frameGeometry().topLeft() != rect.topLeft():
        dialog.move(rect.topLeft())


class DialogPlacement(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, target, event):
        if isinstance(target, QDialog) and target.isWindow():
            if event.type() == QEvent.NonClientAreaMouseButtonPress:
                target.setProperty("placementAutoCenter", False)
            elif event.type() in (QEvent.LayoutRequest, QEvent.Resize) and target.isVisible() and target.property("placementAutoCenter"):
                if not target.property("placementCenterQueued"):
                    target.setProperty("placementCenterQueued", True)
                    def settle():
                        target.setProperty("placementCenterQueued", False)
                        # Headless callers own large test canvases; the default
                        # 800px virtual desktop must not shrink an explicit resize.
                        available = target.screen().availableGeometry()
                        if QGuiApplication.platformName() in {"offscreen", "minimal"} and (
                            target.width() > available.width() - 16 or target.height() > available.height() - 16
                        ):
                            return
                        fit_dialog(target, center=True)
                    QTimer.singleShot(0, target, settle)
        if event.type() == QEvent.Show and isinstance(target, QDialog) and target.isWindow():
            # QWidget.isAncestorOf may stop at native child-window boundaries.
            # Follow QObject ownership so dialogs opened by embedded pages or
            # another dialog still belong to the same application window.
            owner = target.parent()
            while owner is not None and owner is not self.parent():
                owner = owner.parent()
            if owner is None:
                return False
            if isinstance(target, QFileDialog) and not target.testOption(QFileDialog.DontUseNativeDialog):
                return False
            target.setProperty("placementFitted", True)
            target.setProperty("placementAutoCenter", True)
            # Position before the first paint, then account for the final
            # native frame and showEvent adjustments. Reopening uses the
            # owner's current position rather than the previous dialog location.
            fit_dialog(target, center=True)
            QTimer.singleShot(0, target, lambda: fit_dialog(target, center=True))
        return False
