"""One configuration surface shared by single and batch download views."""

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.layout_policy import output_side_by_side
from bilibili_downloader.gui.widgets.components import (
    ActionButton,
    CollapsibleSection,
    ElidedLabel,
    ResponsiveFields,
    SectionCard,
    repolish,
    reveal_field,
)


class SourceTabs(QTabWidget):
    """Size the current source view without reserving space for hidden results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _: self.updateGeometry())

    def _page_hint(self, minimum=False):
        page = self.currentWidget()
        if page is None:
            return QSize(0, 0)
        hint = page.minimumSizeHint() if minimum else page.sizeHint()
        return QSize(max(0, hint.width()), max(0, hint.height()) + self.tabBar().sizeHint().height() + 16)

    def sizeHint(self):
        return self._page_hint()

    def minimumSizeHint(self):
        return self._page_hint(True)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        page = self.currentWidget()
        if page is None:
            return 0
        height = page.heightForWidth(width) if page.hasHeightForWidth() else page.sizeHint().height()
        return max(page.minimumSizeHint().height(), height) + self.tabBar().sizeHint().height() + 16


class DownloadConfiguration(SectionCard):
    opened = Signal()

    def __init__(self, parent=None):
        super().__init__("下载设置", parent)
        self.setObjectName("ControlPanel")
        self._preconfigured = False
        self._error_field = None
        self._error_control = None
        self.summary = QLabel()
        self.summary.setObjectName("MetaLabel")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)
        self.edit = ActionButton("修改")
        self.edit.setObjectName("TextButton")
        self.edit.clicked.connect(self.open)
        self.header.addWidget(self.edit)
        self.content = QWidget()
        self.fields_layout = QVBoxLayout(self.content)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(16)
        self.fields = ResponsiveFields(column_width=280)
        self.fields_layout.addWidget(self.fields)
        self.advanced = CollapsibleSection("高级设置")
        self.advanced.setProperty("sectionStyle", "plain")
        self.advanced_summary = ElidedLabel()
        self.advanced_summary.setObjectName("MetaLabel")
        # The summary remains visible when advanced controls are collapsed.
        self.advanced.layout().insertWidget(1, self.advanced_summary)
        self.body.addWidget(self.content)
        self.content.hide()

    def open(self):
        self._preconfigured = True
        self.set_context(True)
        self.opened.emit()

    def set_context(self, ready):
        expanded = ready or self._preconfigured
        self.content.setVisible(expanded)
        self.summary.setVisible(not expanded)
        self.edit.setVisible(not expanded)

    def set_summary(self, summary, advanced):
        self.summary.setText(summary)
        self.advanced_summary.set_full_text(advanced)

    def clear_error(self, *_args):
        if self._error_field is not None:
            self._error_field.set_error("")
            self._error_control.setProperty("invalid", False)
            repolish(self._error_control)
            self._error_field = self._error_control = None

    def reveal_error(self, field, message, control=None):
        self.clear_error()
        self.open()
        if self.advanced.isAncestorOf(field):
            self.advanced.set_expanded(True)
        field.set_error(message)
        control = control or field.control
        self._error_field, self._error_control = field, control
        control.setProperty("invalid", True)
        repolish(control)
        control.setFocus(Qt.OtherFocusReason)
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                reveal_field(ancestor, field)
                break
            ancestor = ancestor.parentWidget()


class DownloadWorkspace(QWidget):
    """A content column and one shared settings rail, in a single scroll area."""

    def __init__(self, source, configuration, parent=None):
        super().__init__(parent)
        self.configuration = configuration
        self.row = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(20)
        self.row.addWidget(source, 1)
        self.row.addWidget(configuration, 0, Qt.AlignTop)
        self.space = QWidget()
        self.space.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.row.addWidget(self.space)
        source.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.wide = None
        self._rail_width = None

    def _reflow(self):
        wide = output_side_by_side(self.width())
        rail_width = max(336, self.configuration.minimumSizeHint().width())
        if wide != self.wide or rail_width != self._rail_width:
            self.wide = wide
            self._rail_width = rail_width
            self.row.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
            self.row.setStretch(0, 1 if wide else 0)
            self.row.setStretch(2, 0 if wide else 1)
            self.space.setVisible(not wide)
            self.configuration.setMaximumWidth(rail_width if wide else 16777215)
            self.configuration.setMinimumWidth(rail_width if wide else 0)
            self.setProperty("wide", wide)
            repolish(self)

    def event(self, event):
        if event.type() in (QEvent.LayoutRequest, QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "_rail_width"):
            self._reflow()
        return super().event(event)

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)
