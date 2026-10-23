"""Fixed status feedback with a single optional contextual action."""

from PySide6.QtWidgets import QPushButton, QStatusBar


class FeedbackBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._callback = None
        self.action = QPushButton()
        self.action.setObjectName("TableSubtleButton")
        self.action.setFixedHeight(32)
        self.action.hide()
        self.action.clicked.connect(self._activate)
        self.addPermanentWidget(self.action)
        self.messageChanged.connect(self._message_changed)

    def _message_changed(self, message):
        if not message:
            self.action.hide()
            self._callback = None

    def showMessage(self, message, timeout=8000):
        self.action.hide()
        self._callback = None
        super().showMessage(message, timeout)

    def show_feedback(self, message, action="", callback=None):
        self.showMessage(message)
        self._callback = callback
        self.action.setText(action)
        self.action.setVisible(bool(action and callback))

    def _activate(self):
        callback = self._callback
        if callback:
            callback()
