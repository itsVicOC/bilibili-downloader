"""Offline wallpaper browser with a large, isolated page preview."""

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QObject,
    QRectF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QImage,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.builtin_backgrounds import (
    BUILTIN_BACKGROUNDS,
    STYLE_TITLES,
    WORKSPACE_TITLES,
    builtin_background,
)
from bilibili_downloader.core.models import BackgroundVisibility
from bilibili_downloader.gui.resources.paths import background_path
from bilibili_downloader.gui.resources.styles import readable_fill_text
from bilibili_downloader.gui.widgets.background_effects import BackgroundEffects
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.workspace_background import background_pixmap


class _DecodeSignals(QObject):
    finished = Signal(int, object)


class _DecodeRunner(QRunnable):
    def __init__(self, signals, generation, path):
        super().__init__()
        self.signals, self.generation, self.path = signals, generation, path

    def run(self):
        image = QImage()
        try:
            if self.path and self.path.stat().st_size <= 64 * 1024 * 1024:
                reader = QImageReader(str(self.path))
                dimensions = reader.size()
                if dimensions.isValid() and max(dimensions.width(), dimensions.height()) <= 3840:
                    image = reader.read()
        except OSError:
            pass
        try:
            self.signals.finished.emit(self.generation, image)
        except RuntimeError:
            pass  # Closing a gallery never keeps its decoder or widgets alive.


class WallpaperCard(QAbstractButton):
    navigate = Signal(object, int)

    def __init__(self, entry, recommended=False, parent=None):
        super().__init__(parent)
        self.entry, self.recommended = entry, recommended
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"{entry.title}，{STYLE_TITLES[entry.style]}，推荐{WORKSPACE_TITLES[entry.workspace]}")
        self.setToolTip(f"{entry.title} · {entry.description}\n推荐用于{WORKSPACE_TITLES[entry.workspace]}")
        self._image = background_pixmap(background_path(entry.reference, thumbnail=True))
        self.setEnabled(not self._image.isNull())
        self.set_card_width(144)

    def set_card_width(self, width):
        self.setFixedSize(width, round((width - 12) * 9 / 16) + 48)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            self.navigate.emit(self, event.key())
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        colors = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(colors.focus if self.isChecked() else colors.divider), 2 if self.isChecked() else 1))
        painter.setBrush(QColor(colors.selection if self.isChecked() else colors.surface_raised if self.underMouse() else colors.surface))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 9, 9)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(colors.focus), 1, Qt.DashLine))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 11, 11)
        thumb = QRectF(6, 6, self.width() - 12, (self.width() - 12) * 9 / 16)
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(thumb, 5, 5)
        painter.setClipPath(clip)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.entry.style != "pixel")
        painter.drawPixmap(thumb, self._image, QRectF(self._image.rect()))
        painter.restore()
        if self.recommended:
            badge = QRectF(10, 10, 36, 20)
            painter.setBrush(QColor(colors.surface))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge, 5, 5)
            painter.setPen(QColor(colors.active_text))
            font = painter.font()
            font.setPointSizeF(font.pointSizeF() * .78)
            painter.save()
            painter.setFont(font)
            painter.drawText(badge, Qt.AlignCenter, "推荐")
            painter.restore()
        if self.isChecked():
            fill = colors.primary or colors.accent
            painter.setBrush(QColor(fill))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(self.width() - 31, 10, 21, 21))
            painter.setPen(QPen(QColor(readable_fill_text(fill, colors.accent_text)), 2))
            x = self.width() - 26
            painter.drawLine(x, 20, x + 4, 24)
            painter.drawLine(x + 4, 24, x + 11, 16)
        painter.setPen(QColor(colors.text))
        painter.drawText(QRectF(9, thumb.bottom() + 4, self.width() - 18, 22), Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(self.entry.title, Qt.ElideRight, self.width() - 18))
        font = painter.font()
        font.setPointSizeF(font.pointSizeF() * .78)
        painter.setFont(font)
        painter.setPen(QColor(colors.muted))
        painter.drawText(QRectF(9, thumb.bottom() + 24, self.width() - 18, 16), Qt.AlignVCenter,
                         f"{STYLE_TITLES[self.entry.style]} · {WORKSPACE_TITLES[self.entry.workspace]}")
        painter.end()


def _dropped_path(mime):
    urls = mime.urls() if mime.hasUrls() else []
    if len(urls) == 1 and urls[0].isLocalFile():
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return path
    return None


class ImageDropArea(QAbstractButton):
    file_dropped = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(196)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("拖放或选择自定义背景图片")
        self.image = QPixmap()

    def dragEnterEvent(self, event):
        if _dropped_path(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = _dropped_path(event.mimeData())
        if path:
            self.file_dropped.emit(path)
            event.acceptProposedAction()

    def paintEvent(self, event):
        p = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(p.focus if self.hasFocus() or self.underMouse() else p.border), 1, Qt.DashLine))
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 12, 12)
        if not self.image.isNull():
            space = self.rect().adjusted(16, 16, -16, -76)
            size = self.image.size().scaled(space.size(), Qt.KeepAspectRatio)
            painter.drawPixmap(space.center().x() - size.width() // 2, space.center().y() - size.height() // 2, size.width(), size.height(), self.image)
            title = self.rect().adjusted(12, 12, -12, -40)
            caption = self.rect().adjusted(12, 12, -12, -16)
        else:
            center = self.rect().center()
            frame = QRectF(center.x() - 32, center.y() - 58, 64, 48)
            painter.setPen(QPen(QColor(p.muted), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(frame, 7, 7)
            painter.drawEllipse(QRectF(frame.left() + 12, frame.top() + 10, 9, 9))
            painter.drawLine(int(frame.left() + 7), int(frame.bottom() - 9), int(frame.left() + 26), int(frame.top() + 25))
            painter.drawLine(int(frame.left() + 26), int(frame.top() + 25), int(frame.left() + 38), int(frame.bottom() - 9))
            painter.drawLine(int(frame.left() + 38), int(frame.bottom() - 9), int(frame.right() - 10), int(frame.top() + 20))
            title = QRectF(12, center.y() + 6, self.width() - 24, 24)
            caption = QRectF(12, center.y() + 34, self.width() - 24, 24)
        painter.setPen(QColor(p.text))
        painter.drawText(title, Qt.AlignHCenter | Qt.AlignBottom,
                         "更换图片" if not self.image.isNull() else "拖放图片到这里")
        painter.setPen(QColor(p.muted))
        painter.drawText(caption, Qt.AlignHCenter | Qt.AlignBottom, "或点击选择本地图片")
        painter.end()


class BackgroundGallery(QDialog):
    def __init__(self, picker):
        super().__init__(picker)
        self.setWindowTitle(f"选择{picker._title}背景")
        self.setMinimumSize(720, 520)
        self.setAcceptDrops(True)
        available = self.screen().availableGeometry().size()
        self.resize(min(1080, available.width() - 48), min(720, available.height() - 64))
        self.reference, self.prepared = picker.reference, picker.prepared
        self._store, self._workspace = picker.store, picker.workspace
        self._generation, self._jobs = 0, {}
        self._cache = OrderedDict()
        self._selected_image = QPixmap()
        self._selection_valid = not self.reference
        self.busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("选择背景")
        title.setObjectName("DialogTitle")
        header.addWidget(title)
        header.addStretch()
        target = QLabel(f"用于{WORKSPACE_TITLES[self._workspace]}")
        target.setObjectName("MetaLabel")
        header.addWidget(target)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(16)
        layout.addLayout(body, 1)
        left = QVBoxLayout()
        left.setSpacing(8)
        self.selection_label = QLabel()
        self.selection_label.setObjectName("SectionTitle")
        left.addWidget(self.selection_label)
        self.effects = BackgroundEffects(picker._title, picker._theme_id, picker.visibility, workspace=self._workspace)
        if picker.window().width() >= 720:
            self.effects.preview.viewport_size = picker.window().size()
        left.addWidget(self.effects, 1)
        body.addLayout(left, 1)
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(288)
        self.tabs.setMaximumWidth(340)
        body.addWidget(self.tabs)
        bundled = QWidget()
        column = QVBoxLayout(bundled)
        column.setContentsMargins(0, 4, 0, 0)
        column.setSpacing(8)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.page_filter = ComboBox()
        self.page_filter.addItem("全部页面", "")
        for key, name in WORKSPACE_TITLES.items():
            self.page_filter.addItem(name, key)
        self.page_filter.setAccessibleName("背景推荐页面")
        filters.addWidget(self.page_filter)
        self.style_filter = ComboBox()
        self.style_filter.addItem("全部画风", "")
        for key, name in STYLE_TITLES.items():
            self.style_filter.addItem(name, key)
        self.style_filter.setAccessibleName("背景画风")
        filters.addWidget(self.style_filter)
        column.addLayout(filters)
        self.filter_status = QLabel()
        self.filter_status.setObjectName("MetaLabel")
        self.filter_status.setWordWrap(True)
        column.addWidget(self.filter_status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(content)
        column.addWidget(self.scroll, 1)
        self._cards = []
        self._group = QButtonGroup(self)
        entries = sorted(BUILTIN_BACKGROUNDS, key=lambda e: e.workspace != self._workspace)
        for entry in entries:
            card = WallpaperCard(entry, entry.workspace == self._workspace, content)
            self._cards.append(card)
            self._group.addButton(card)
            card.setChecked(entry.reference == self.reference)
            card.clicked.connect(lambda _checked=False, e=entry: self.select_builtin(e.reference))
            card.navigate.connect(self._navigate)
        self.page_filter.currentIndexChanged.connect(self._reflow)
        self.style_filter.currentIndexChanged.connect(self._reflow)
        self.tabs.addTab(bundled, "小流")
        custom = QWidget()
        column = QVBoxLayout(custom)
        column.setContentsMargins(0, 4, 0, 0)
        self.drop_area = ImageDropArea()
        self.drop_area.clicked.connect(self._choose_custom)
        self.drop_area.file_dropped.connect(self.select_path)
        column.addWidget(self.drop_area, 1)
        self.import_button = QPushButton("选择本地图片…")
        self.import_button.clicked.connect(self._choose_custom)
        column.addWidget(self.import_button)
        self.import_status = QLabel("支持 PNG、JPEG、WebP，最大 20 MiB。保存时保留应用内副本。")
        self.import_status.setObjectName("MetaLabel")
        self.import_status.setWordWrap(True)
        column.addWidget(self.import_status)
        self.tabs.addTab(custom, "自定义图片")
        if self.reference and builtin_background(self.reference) is None:
            self.tabs.setCurrentIndex(1)
        footer = QHBoxLayout()
        self.default_button = QPushButton("恢复主题默认")
        self.default_button.setObjectName("OutputSecondaryButton")
        self.default_button.clicked.connect(self.restore_default)
        footer.addWidget(self.default_button)
        footer.addStretch()
        self.save_hint = QLabel("保存设置后生效")
        self.save_hint.setObjectName("MetaLabel")
        footer.addWidget(self.save_hint)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.Ok)
        self.apply_button.setText("使用此背景")
        self.apply_button.setObjectName("PrimaryButton")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        layout.addLayout(footer)
        self._reflow()
        if self.prepared is not None:
            self._selected_image.loadFromData(self.prepared.png)
            self._selection_valid = not self._selected_image.isNull()
            self._refresh_selection()
        elif self.reference:
            self._load_reference()
        else:
            self._refresh_selection()
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.timeout.connect(self._reveal_selection)
        self._reveal_timer.start(0)

    @property
    def visibility(self):
        return self.effects.preview.visibility

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tabs"):
            self.tabs.setFixedWidth(max(288, min(340, round(self.width() * .30))))

    def _reflow(self, *_args):
        if not hasattr(self, "_cards"):
            return
        width = self.scroll.viewport().width() - 4
        self._columns = 2 if width >= 264 else 1
        card_width = max(128, min(192, (width - 8 * (self._columns - 1)) // self._columns))
        page, style = self.page_filter.currentData(), self.style_filter.currentData()
        self._visible_cards = []
        for card in self._cards:
            self.grid.removeWidget(card)
            visible = (not page or card.entry.workspace == page) and (not style or card.entry.style == style)
            card.setVisible(visible)
            if visible:
                index = len(self._visible_cards)
                card.set_card_width(card_width)
                self.grid.addWidget(card, index // self._columns, index % self._columns)
                self._visible_cards.append(card)
        hidden = self.reference and builtin_background(self.reference) and not any(c.isChecked() for c in self._visible_cards)
        self.filter_status.setText("当前选择不在此筛选中" if hidden else f"{len(self._visible_cards)} 幅作品 · 此页推荐优先")

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._reflow()
        return super().eventFilter(watched, event)

    def _navigate(self, card, key):
        if card not in self._visible_cards:
            return
        index = self._visible_cards.index(card)
        step = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -self._columns, Qt.Key_Down: self._columns}[key]
        index = max(0, min(len(self._visible_cards) - 1, index + step))
        target = self._visible_cards[index]
        target.setFocus(Qt.TabFocusReason)
        self.scroll.ensureWidgetVisible(target, 8, 8)

    def _reveal_selection(self):
        for card in self._cards:
            if card.isChecked() and not card.isHidden():
                self.scroll.ensureWidgetVisible(card, 8, 8)
                break

    def _check_selection(self):
        self._group.setExclusive(False)
        for card in self._cards:
            card.setChecked(card.entry.reference == self.reference)
        self._group.setExclusive(True)
        self._reflow()

    def select_builtin(self, reference):
        if builtin_background(reference) is None:
            return
        self.tabs.setCurrentIndex(0)
        self.reference, self.prepared = reference, None
        self.import_status.setText("支持 PNG、JPEG、WebP，最大 20 MiB。保存时保留应用内副本。")
        self._check_selection()
        self._load_reference()

    def _load_reference(self):
        self._generation += 1
        generation = self._generation
        entry = builtin_background(self.reference)
        if self.reference in self._cache:
            self._cache.move_to_end(self.reference)
            self._selected_image = self._cache[self.reference]
            self.busy = False
            self._selection_valid = True
            self._refresh_selection()
            return
        self._selected_image = background_pixmap(background_path(self.reference, thumbnail=True)) if entry else QPixmap()
        self.busy, self._selection_valid = True, False
        signals = _DecodeSignals(self)
        runner = _DecodeRunner(signals, generation, background_path(self.reference, self._store))
        self._jobs[generation] = (signals, runner)
        signals.finished.connect(self._decode_finished)
        self._refresh_selection()
        QThreadPool.globalInstance().start(runner)

    def _pop_job(self, generation):
        job = self._jobs.pop(generation, None)
        if job:
            job[0].deleteLater()

    def _decode_finished(self, generation, image):
        self._pop_job(generation)
        if generation != self._generation:
            return
        self.busy = False
        self._selected_image = QPixmap.fromImage(image)
        self._selection_valid = not image.isNull()
        if self._selection_valid:
            self._cache[self.reference] = self._selected_image
            while len(self._cache) > 2:
                self._cache.popitem(last=False)
        self._refresh_selection()

    def _refresh_selection(self):
        entry = builtin_background(self.reference)
        self.effects.set_image(self._selected_image, builtin=entry is not None, pixel_art=entry is not None and entry.style == "pixel")
        self.selection_label.setText(f"{entry.title} · {STYLE_TITLES[entry.style]}" if entry else "自定义图片" if self.reference else "主题默认")
        if self.busy:
            self.selection_label.setText(self.selection_label.text() + " · 正在读取…")
        elif not self._selection_valid:
            self.selection_label.setText("背景丢失或损坏，请选择其他图片")
        self.drop_area.image = self._selected_image if self.reference and not entry else QPixmap()
        self.drop_area.update()
        self.apply_button.setEnabled(self._selection_valid and not self.busy)
        self.default_button.setEnabled(bool(self.reference) or self.visibility != BackgroundVisibility())

    def restore_default(self):
        self._generation += 1
        self.reference, self.prepared, self.busy = "", None, False
        self._selected_image = QPixmap()
        self._selection_valid = True
        self.effects.preview.visibility = BackgroundVisibility()
        self._check_selection()
        self._refresh_selection()

    def _choose_custom(self):
        path = QFileDialog.getOpenFileName(self, "选择背景图片", "", "静态图片 (*.png *.jpg *.jpeg *.webp)")[0]
        if path:
            self.select_path(Path(path))

    def dragEnterEvent(self, event):
        if _dropped_path(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = _dropped_path(event.mimeData())
        if path:
            self.select_path(path)
            event.acceptProposedAction()

    def select_path(self, path):
        from bilibili_downloader.gui.widgets.background_picker import (
            _ImageRunner,
            _ImageSignals,
        )

        self.tabs.setCurrentIndex(1)
        self._generation += 1
        generation = self._generation
        signals = _ImageSignals(self)
        runner = _ImageRunner(signals, generation, Path(path))
        self._jobs[generation] = (signals, runner)
        signals.finished.connect(self._import_finished)
        self.busy = True
        self.apply_button.setEnabled(False)
        self.import_status.setText("正在读取图片…")
        QThreadPool.globalInstance().start(runner)

    def _import_finished(self, generation, image, error):
        self._pop_job(generation)
        if generation != self._generation:
            return
        self.busy = False
        if error:
            self.import_status.setText(error)
        else:
            self.reference, self.prepared = image.reference, image
            self._selected_image.loadFromData(image.png)
            self._selection_valid = not self._selected_image.isNull()
            self.import_status.setText("图片已准备好。使用此背景后，返回设置页保存。")
            self._check_selection()
        self._refresh_selection()

    def done(self, result):
        self._generation += 1
        super().done(result)
