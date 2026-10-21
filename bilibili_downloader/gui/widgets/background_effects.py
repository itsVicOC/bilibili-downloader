"""Shared, isolated appearance controls for imported and bundled pictures."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR, MAX_GLASS_BLUR
from bilibili_downloader.gui.resources.styles import background_overlay_alpha
from bilibili_downloader.gui.widgets.appearance_preview import WorkspacePreview


class GlassBlurControl(QWidget):
    """Keyboard-accessible global blur preference in appearance settings."""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        label = QLabel("玻璃模糊")
        row.addWidget(label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, MAX_GLASS_BLUR)
        self.slider.setPageStep(4)
        self.slider.setAccessibleName("玻璃模糊程度")
        self.slider.setToolTip("向左保留背景细节，向右更柔和；所有工作区共用")
        label.setBuddy(self.slider)
        row.addWidget(self.slider, 1)
        self.display = QLabel()
        self.display.setMinimumWidth(48)
        self.display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.display)
        self.reset = QPushButton("重置")
        self.reset.setObjectName("OutputSecondaryButton")
        self.reset.setAccessibleName("恢复玻璃模糊默认值")
        self.reset.clicked.connect(lambda: self.setValue(DEFAULT_GLASS_BLUR))
        row.addWidget(self.reset)
        self.slider.valueChanged.connect(self._changed)
        self.setValue(DEFAULT_GLASS_BLUR)

    def value(self):
        return self.slider.value()

    def setValue(self, value):
        self.slider.setValue(value)

    def _changed(self, value):
        self.display.setText(f"{value} px")
        self.reset.setEnabled(value != DEFAULT_GLASS_BLUR)
        self.valueChanged.emit(value)


class BackgroundEffects(QWidget):
    def __init__(self, title, theme_id, visibility, parent=None, *, workspace="download", glass_blur=DEFAULT_GLASS_BLUR):
        super().__init__(parent)
        self._theme_id = theme_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview = WorkspacePreview(
            title, QPixmap(), theme_id, visibility=visibility, workspace=workspace
        )
        self.preview.setMinimumHeight(160)
        self.preview.glass_blur = glass_blur
        row = QHBoxLayout()
        row.setSpacing(4)
        self._views = QButtonGroup(self)
        self.page_button = self._segment("页面效果", self._views, row)
        self.original_button = self._segment("原图", self._views, row)
        self.page_button.setChecked(True)
        self.original_button.toggled.connect(self._change_view)
        row.addStretch()
        self._modes = QButtonGroup(self)
        self.light_button = self._segment("浅色", self._modes, row)
        self.dark_button = self._segment("深色", self._modes, row)
        (self.dark_button if self.preview.is_dark else self.light_button).setChecked(True)
        self.dark_button.toggled.connect(self._change_mode)
        layout.addLayout(row)
        layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        label = QLabel("背景可见度")
        row.addWidget(label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setPageStep(10)
        self.slider.setAccessibleName(f"{title}背景可见度")
        self.slider.setToolTip("向右拖动更清晰；0% 隐藏图片，100% 显示原图")
        self.slider.valueChanged.connect(self._change_visibility)
        label.setBuddy(self.slider)
        row.addWidget(self.slider, 1)
        self.value = QLabel()
        self.value.setMinimumWidth(80)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.value)
        self.reset = QPushButton("重置")
        self.reset.setObjectName("OutputSecondaryButton")
        self.reset.setAccessibleName("恢复当前模式背景可见度")
        self.reset.setToolTip("恢复当前深浅模式的默认可见度")
        self.reset.clicked.connect(self._reset)
        row.addWidget(self.reset)
        layout.addLayout(row)
        self._refresh()

    def _segment(self, title, group, row):
        button = QPushButton(title)
        button.setObjectName("SegmentButton")
        button.setCheckable(True)
        button.setAutoDefault(False)
        group.addButton(button)
        row.addWidget(button)
        return button

    def set_image(self, pixmap, *, builtin=False, pixel_art=False):
        self.preview.pixmap = pixmap
        self.preview.builtin = builtin and not pixmap.isNull()
        self.preview.pixel_art = pixel_art
        self._refresh()

    def _current_mode(self):
        return "dark" if self.preview.is_dark else "light"

    def _refresh(self):
        visible = getattr(self.preview.visibility, self._current_mode())
        alpha = background_overlay_alpha(
            self.preview.is_dark, self._theme_id, visible, builtin=self.preview.builtin
        )
        percentage = round((1 - alpha / 255) * 100)
        self.slider.blockSignals(True)
        self.slider.setValue(percentage)
        self.slider.blockSignals(False)
        self.slider.setEnabled(not self.preview.pixmap.isNull())
        self.original_button.setEnabled(not self.preview.pixmap.isNull())
        if self.preview.pixmap.isNull() and self.original_button.isChecked():
            self.page_button.setChecked(True)
        self.value.setText(
            f"默认 · {percentage}%" if visible is None else f"{visible}%"
        )
        self.reset.setEnabled(not self.preview.pixmap.isNull() and visible is not None)
        self.preview.update()

    def _change_mode(self, dark):
        self.preview.is_dark = dark
        self._refresh()

    def _change_view(self, original):
        self.preview.original = original
        self._refresh()

    def _change_visibility(self, value):
        setattr(self.preview.visibility, self._current_mode(), value)
        self._refresh()

    def _reset(self):
        setattr(self.preview.visibility, self._current_mode(), None)
        self._refresh()
