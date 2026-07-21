"""Background worker for checking the current Bilibili login state."""

from PySide6.QtCore import QObject, QRunnable, Signal


class LoginStatusWorker(QObject):
    finished = Signal(int, object)
    error = Signal(int, str)

    def __init__(self, client, request_id: int):
        super().__init__()
        self.client = client
        self.request_id = request_id


class LoginStatusRunner(QRunnable):
    def __init__(self, worker: LoginStatusWorker):
        super().__init__()
        self._worker = worker
        self.setAutoDelete(True)

    def run(self):
        try:
            info = self._worker.client.get_nav_info()
            self._worker.finished.emit(self._worker.request_id, info)
        except Exception as e:  # noqa: BLE001
            self._worker.error.emit(self._worker.request_id, str(e))
