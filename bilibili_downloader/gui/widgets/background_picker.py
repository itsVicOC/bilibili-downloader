"""An isolated background draft with asynchronous local image decoding."""


from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.appearance import prepare_background
from bilibili_downloader.core.builtin_backgrounds import (
    WORKSPACE_TITLES,
    builtin_background,
)
from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.resources.paths import background_path
from bilibili_downloader.gui.widgets.appearance_preview import (
    BackgroundThumbnail,
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

    def __init__(self, title, store=None, parent=None, *, workspace=None):
        super().__init__(parent)
        self.store = store
        self._title = title
        self.workspace = workspace or next((key for key, value in WORKSPACE_TITLES.items() if value == title), "download")
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
        self.preview.setToolTip("选择背景并预览浅色、深色效果")
        self.preview.clicked.connect(self._show_preview)
        row.addWidget(self.preview)
        column = QVBoxLayout()
        self.status = QLabel("使用主题默认背景")
        self.status.setObjectName("MetaLabel")
        self.status.setWordWrap(True)
        column.addWidget(self.status)
        buttons = QHBoxLayout()
        self.choose = QPushButton("选择背景…")
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
        self._refresh_thumbnail()
        self.changed.emit()

    def _refresh_thumbnail(self):
        self.preview.clear()
        entry = builtin_background(self.reference)
        self.preview.pixel_art = entry is not None and entry.style == "pixel"
        pixmap = QPixmap()
        if self.prepared is not None:
            pixmap.loadFromData(self.prepared.preview)
        elif self.reference:
            try:
                pixmap = background_pixmap(background_path(self.reference, self.store, thumbnail=entry is not None), QSize(160, 90), pixel_art=self.preview.pixel_art)
            except OSError:
                pass
        if not pixmap.isNull():
            self.preview.setPixmap(pixmap)
            self.status.setText(f"小流 · {entry.title} · 点击预览效果" if entry else "图片已准备好，保存设置后生效" if self.prepared else "已保存自定义背景 · 点击缩略图预览效果")
        else:
            self.preview.setText("默认背景\n点击预览")
            self.status.setText(
                "背景丢失或损坏，请重新选择图片" if self.reference else "使用主题默认背景"
            )
        self.reset.setEnabled(bool(self.reference))

    def set_theme(self, theme_id):
        self._theme_id = theme_id

    def set_visibility(self, visibility):
        self.visibility = visibility.model_copy(deep=True)
        self.changed.emit()

    def _restore_default(self):
        self.set_visibility(BackgroundVisibility())
        self.set_reference("")

    def _show_preview(self):
        self._choose()

    def _choose(self):
        from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery

        dialog = BackgroundGallery(self)
        if dialog.exec() == QDialog.Accepted:
            self._generation += 1
            self.busy = False
            self.reference, self.prepared = dialog.reference, dialog.prepared
            self.visibility = dialog.visibility.model_copy(deep=True)
            self.choose.setEnabled(True)
            self._refresh_thumbnail()
            self.changed.emit()
        dialog.deleteLater()

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
            self._refresh_thumbnail()
        self.reset.setEnabled(bool(self.reference))
        self.changed.emit()
