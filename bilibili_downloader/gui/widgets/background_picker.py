"""An isolated background draft with asynchronous local image decoding."""

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.appearance import prepare_background
from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.resources.styles import background_overlay_alpha
from bilibili_downloader.gui.widgets.appearance_preview import (
    BackgroundThumbnail,
    WorkspacePreview,
)
from bilibili_downloader.gui.widgets.workspace_background import background_pixmap


class _ImageSignals(QObject):
    finished = Signal(int, object, str)


class _ImageRunner(QRunnable):
    def __init__(self, signals, generation, path):
        super().__init__()
        self.signals, self.generation, self.path = signals, generation, path

    def run(self):
        try:
            image, error = prepare_background(self.path), ""
        except ValueError as exc:
            image, error = None, str(exc)
        try:
            self.signals.finished.emit(self.generation, image, error)
        except RuntimeError:
            pass  # The editor was closed before decoding finished.


class BackgroundPicker(QWidget):
    changed = Signal()

    def __init__(self, title, store=None, parent=None):
        super().__init__(parent)
        self.store = store
        self._title = title
        self._theme_id = "star_trail"
        self.reference = ""
        self.prepared = None
        self.visibility = BackgroundVisibility()
        self.busy = False
        self._generation = 0
        self._jobs = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        self.preview = BackgroundThumbnail()
        self.preview.setAccessibleName(f"预览{title}背景效果")
        self.preview.setToolTip("点击预览并调节浅色、深色背景可见度")
        self.preview.clicked.connect(self._show_preview)
        row.addWidget(self.preview)
        column = QVBoxLayout()
        self.status = QLabel("使用主题默认背景")
        self.status.setObjectName("MetaLabel")
        self.status.setWordWrap(True)
        column.addWidget(self.status)
        buttons = QHBoxLayout()
        self.choose = QPushButton("选择图片…")
        self.choose.clicked.connect(self._choose)
        self.reset = QPushButton("恢复默认")
        self.reset.clicked.connect(self._restore_default)
        buttons.addWidget(self.choose)
        buttons.addWidget(self.reset)
        buttons.addStretch()
        column.addLayout(buttons)
        row.addLayout(column, 1)

    def set_reference(self, reference):
        self._generation += 1
        self.reference, self.prepared, self.busy = reference, None, False
        self.choose.setEnabled(True)
        self.preview.clear()
        pixmap = QPixmap()
        if reference and self.store:
            try:
                pixmap = background_pixmap(self.store.path(reference), QSize(160, 90))
            except OSError:
                pass
        if not pixmap.isNull():
            self.preview.setPixmap(pixmap)
            self.status.setText("已保存自定义背景 · 点击缩略图预览效果")
        else:
            self.preview.setText("默认背景\n点击预览")
            self.status.setText(
                "背景丢失或损坏，请重新选择图片" if reference else "使用主题默认背景"
            )
        self.reset.setEnabled(bool(reference))
        self.changed.emit()

    def set_theme(self, theme_id):
        self._theme_id = theme_id

    def set_visibility(self, visibility):
        self.visibility = visibility.model_copy(deep=True)
        self.changed.emit()

    def _restore_default(self):
        self.set_visibility(BackgroundVisibility())
        self.set_reference("")

    def _show_preview(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{self._title}背景效果")
        dialog.resize(800, 560)
        layout = QVBoxLayout(dialog)
        pixmap = self.preview.pixmap()
        if self.prepared:
            pixmap = QPixmap()
            pixmap.loadFromData(self.prepared.png)
        elif self.reference and self.store:
            try:
                pixmap = background_pixmap(self.store.path(self.reference), QSize(1000, 700))
            except OSError:
                pass
        preview = WorkspacePreview(
            self._title, pixmap, self._theme_id, visibility=self.visibility
        )
        layout.addWidget(preview, 1)
        controls = QHBoxLayout()
        mode = QCheckBox("深色预览")
        mode.setChecked(preview.is_dark)
        controls.addWidget(mode)
        controls.addStretch()
        reset = QPushButton("恢复当前模式默认")
        controls.addWidget(reset)
        layout.addLayout(controls)
        strength = QHBoxLayout()
        label = QLabel("背景可见度")
        strength.addWidget(label)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        slider.setAccessibleName(f"{self._title}背景可见度")
        slider.setToolTip("向右拖动更清晰；0% 隐藏图片，100% 显示原图")
        label.setBuddy(slider)
        strength.addWidget(slider, 1)
        value = QLabel()
        value.setMinimumWidth(90)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        strength.addWidget(value)
        layout.addLayout(strength)

        def current_mode():
            return "dark" if preview.is_dark else "light"

        def refresh_controls():
            visible = getattr(preview.visibility, current_mode())
            alpha = background_overlay_alpha(preview.is_dark, self._theme_id, visible)
            percentage = round((1 - alpha / 255) * 100)
            slider.blockSignals(True)
            slider.setValue(percentage)
            slider.blockSignals(False)
            value.setText(f"默认 · {percentage}%" if visible is None else f"{visible}%")
            reset.setEnabled(not pixmap.isNull() and visible is not None)
            preview.update()

        def change_visibility(visible):
            setattr(preview.visibility, current_mode(), visible)
            refresh_controls()

        def change_mode(dark):
            preview.is_dark = dark
            refresh_controls()

        def restore_visibility():
            setattr(preview.visibility, current_mode(), None)
            refresh_controls()

        slider.valueChanged.connect(change_visibility)
        mode.toggled.connect(change_mode)
        reset.clicked.connect(restore_visibility)
        slider.setEnabled(not pixmap.isNull())
        refresh_controls()
        hint = QLabel(
            "向右拖动更清晰，浅色和深色分别记忆。点击「使用此效果」后，返回设置页保存生效。"
            if not pixmap.isNull() else "请先选择背景图片，再调节可见度。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("MetaLabel")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        apply = buttons.button(QDialogButtonBox.Ok)
        apply.setText("使用此效果")
        apply.setObjectName("PrimaryButton")
        apply.setEnabled(not pixmap.isNull())
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted and preview.visibility != self.visibility:
            self.set_visibility(preview.visibility)
        dialog.deleteLater()

    def _choose(self):
        path = QFileDialog.getOpenFileName(
            self, "选择背景图片", "", "静态图片 (*.png *.jpg *.jpeg *.webp)"
        )[0]
        if path:
            self.select_path(Path(path))

    def select_path(self, path):
        self._generation += 1
        generation = self._generation
        signals = _ImageSignals(self)
        runner = _ImageRunner(signals, generation, path)
        self._jobs[generation] = (signals, runner)
        signals.finished.connect(self._finished)
        self.busy = True
        self.choose.setEnabled(False)
        self.reset.setEnabled(True)
        self.status.setText("正在读取图片…")
        self.changed.emit()
        QThreadPool.globalInstance().start(runner)

    def _finished(self, generation, image, error):
        job = self._jobs.pop(generation, None)
        if job:
            job[0].deleteLater()
        if generation != self._generation:
            return
        self.busy = False
        self.choose.setEnabled(True)
        if error:
            self.status.setText(error)
        else:
            self.prepared, self.reference = image, image.reference
            pixmap = QPixmap()
            pixmap.loadFromData(image.preview)
            self.preview.setPixmap(
                pixmap.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self.status.setText("图片已准备好，保存设置后生效")
        self.reset.setEnabled(bool(self.reference))
        self.changed.emit()
