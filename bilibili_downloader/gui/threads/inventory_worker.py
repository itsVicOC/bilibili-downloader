"""Inventory checks run outside the GUI thread."""

from PySide6.QtCore import QObject, QRunnable, Signal


class InventorySignals(QObject):
    finished = Signal(object)


class InventoryMatchRunner(QRunnable):
    def __init__(self, repository, groups):
        super().__init__()
        self.signals = InventorySignals()
        self.repository, self.groups = repository, groups

    def run(self):
        try:
            result = [all(self.repository.match_media(item).state == "saved" for item in group)
                      for group in self.groups]
        except Exception as exc:
            result = exc
        self.signals.finished.emit(result)
