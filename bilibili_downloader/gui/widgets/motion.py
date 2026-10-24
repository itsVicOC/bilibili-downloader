"""Finite state transitions; no polling, queued effects or stylesheet churn."""

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QVariantAnimation
from PySide6.QtWidgets import QApplication

from bilibili_downloader.gui.resources.styles import UI_METRICS


class StateTransition(QObject):
    def __init__(self, owner, value=0.0, duration=UI_METRICS.motion_fast):
        super().__init__(owner)
        self.owner = owner
        self.value = float(value)
        self.target = self.value
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._update)
        owner.installEventFilter(self)

    def _update(self, value):
        self.value = float(value)
        self.owner.update()

    def settle(self):
        self.animation.stop()
        self._update(self.target)

    def to(self, value):
        self.target = float(value)
        self.animation.stop()
        if (
            not self.owner.isVisible()
            or not self.owner.isEnabled()
            or QApplication.instance().property("uiAnimationsEnabled") is False
            or abs(self.value - self.target) < .001
        ):
            self.settle()
            return
        self.animation.setStartValue(self.value)
        self.animation.setEndValue(self.target)
        self.animation.start()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Hide, QEvent.EnabledChange, QEvent.StyleChange):
            self.settle()
        return False
