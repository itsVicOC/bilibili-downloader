"""Paint-only focus rings and scroll-safe controls across the application."""

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabBar,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import UI_METRICS, theme_palette
from bilibili_downloader.gui.widgets.text_menu import text_context_menu


class _FocusRing(QWidget):
    def __init__(self, control):
        super().__init__(control)
        self.setObjectName("ControlFocusRing")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        target = self.parentWidget()
        if not target.isEnabled() or not target.hasFocus() or not target.property("keyboardFocus"):
            return
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        p = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        primary = target.objectName() in {"PrimaryButton", "DownloadButton", "HeroButton", "OutputPrimaryButton"}
        color = p.primary_text if primary else p.focus
        rect = QRectF(target.tabRect(target.currentIndex()) if isinstance(target, QTabBar) else self.rect())
        compact_path = target.objectName() == "FooterPath"
        inset = target.property("focusInset")
        if inset is None:
            inset = 1 if compact_path or isinstance(target, QCheckBox) and target.objectName() != "DownloadOptionCard" else 3
        rect.adjust(inset, inset, -inset, -inset)
        radius = target.property("focusRadius")
        if radius is None:
            radius = UI_METRICS.small_radius if compact_path else UI_METRICS.radius - inset
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(color), UI_METRICS.focus_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)


class ControlPolish(QObject):
    def _fit_text(self, target):
        target._detail_font_pending = False
        if target.objectName() == "FooterPath":
            return
        if isinstance(target, QLineEdit) and isinstance(target.parentWidget(), (QAbstractSpinBox, QComboBox)):
            return
        if not isinstance(target, (QPushButton, QLineEdit, QAbstractSpinBox, QComboBox)):
            return
        base = getattr(target, "_detail_base_height", None)
        if base is None:
            role = target.objectName()
            compact = role in {"SegmentButton", "TablePrimaryButton", "TableSubtleButton", "TableDangerButton",
                               "TableRemoveButton", "ActivityButton", "OutputSecondaryButton", "ClipboardResolveButton"}
            compact = compact or bool(target.parentWidget() and target.parentWidget().objectName() == "PageHeader")
            primary = role in {"PrimaryButton", "DownloadButton", "HeroButton", "OutputPrimaryButton", "NavButton", "NavButtonActive"}
            base = UI_METRICS.primary_height if primary else UI_METRICS.compact_button_height if compact else UI_METRICS.control_height
            base = max(base, target.minimumHeight())
            target._detail_base_height = base
            target._detail_was_fixed = target.maximumHeight() == target.minimumHeight()
        height = max(base, target.fontMetrics().height() + (12 if base <= 32 else 16))
        changed = target.minimumHeight() != height
        if changed:
            target.setMinimumHeight(height)
        if target._detail_was_fixed and target.maximumHeight() != height:
            target.setMaximumHeight(height)
            changed = True
        if changed:
            target.updateGeometry()
        parent = target.parentWidget()
        if isinstance(parent, QDialogButtonBox):
            height = max((max(button.minimumHeight(), button.sizeHint().height()) for button in parent.buttons()), default=0)
            parent.setMinimumHeight(height + parent.contentsMargins().top() + parent.contentsMargins().bottom())

    def eventFilter(self, target, event):
        if not isinstance(target, QWidget) or isinstance(target, _FocusRing):
            return False
        kind = event.type()
        if kind == QEvent.Show and isinstance(target, QToolButton) and isinstance(target.parentWidget(), QLineEdit):
            if target.parentWidget().isClearButtonEnabled():
                target.setAccessibleName("清除输入")
                target.setToolTip("清除输入")
        if kind in (QEvent.Show, QEvent.FontChange, QEvent.StyleChange) and not getattr(target, "_detail_font_pending", False):
            if isinstance(target, (QPushButton, QLineEdit, QAbstractSpinBox, QComboBox)):
                target._detail_font_pending = True
                QTimer.singleShot(0, target, lambda: self._fit_text(target))
        if kind == QEvent.ContextMenu and isinstance(target, (QLineEdit, QPlainTextEdit, QTextEdit)) and not isinstance(target, QTextBrowser):
            menu = text_context_menu(target)
            menu.exec(event.globalPos())
            menu.deleteLater()
            return True
        if kind == QEvent.Wheel and isinstance(target, (QComboBox, QAbstractSpinBox, QSlider)) and not target.hasFocus():
            ancestor = target.parentWidget()
            while ancestor is not None:
                if isinstance(ancestor, QAbstractScrollArea):
                    viewport = ancestor.viewport()
                    position = viewport.mapFromGlobal(event.globalPosition().toPoint())
                    forwarded = QWheelEvent(position, event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                                            event.buttons(), event.modifiers(), event.phase(), event.inverted(), event.source())
                    QCoreApplication.sendEvent(viewport, forwarded)
                    break
                ancestor = ancestor.parentWidget()
            event.accept()
            return True
        if not isinstance(target, (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QSlider, QTabBar)):
            return False
        if isinstance(target, QLineEdit) and isinstance(target.parentWidget(), (QAbstractSpinBox, QComboBox)):
            return False
        if kind == QEvent.FocusIn:
            target.setAttribute(Qt.WA_MacShowFocusRect, False)
            visible = bool(target.property("invalid")) or event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        elif kind in (QEvent.FocusOut, QEvent.MouseButtonPress):
            visible = False
        elif kind == QEvent.KeyPress:
            visible = True
        elif kind in (QEvent.Resize, QEvent.EnabledChange, QEvent.StyleChange):
            visible = bool(target.property("keyboardFocus"))
        elif kind == QEvent.DynamicPropertyChange and event.propertyName() == b"keyboardFocus":
            visible = bool(target.property("keyboardFocus"))
        else:
            return False
        if kind in (QEvent.FocusIn, QEvent.FocusOut, QEvent.MouseButtonPress, QEvent.KeyPress):
            target.setProperty("keyboardFocus", visible)
        if target.property("ownFocusRing"):
            target.update()
            return False
        overlay = getattr(target, "_control_focus_ring", None)
        if overlay is None and visible:
            overlay = target._control_focus_ring = _FocusRing(target)
        if overlay is not None:
            overlay.setGeometry(target.rect())
            overlay.setVisible(visible and target.isEnabled())
            overlay.raise_()
            overlay.update()
        return False


def install_control_polish(app):
    if not hasattr(app, "_control_polish"):
        app._control_polish = ControlPolish(app)
        app.installEventFilter(app._control_polish)
