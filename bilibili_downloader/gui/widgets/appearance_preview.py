"""Theme selection cards and faithful, isolated wallpaper effect previews."""

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QSizePolicy, QWidget

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR, BackgroundVisibility
from bilibili_downloader.gui.layout_policy import (
    density_for_height,
    path_preferred_width,
)
from bilibili_downloader.gui.resources.styles import (
    READING_FIELD_OPACITY,
    TABLE_DIVIDER_OPACITY,
    TABLE_HEADER_OPACITY,
    UI_METRICS,
    theme_palette,
    wallpaper_palette,
)
from bilibili_downloader.gui.widgets.background_readability import paint_reading_surface
from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.glass_surface import (
    HEADER_BLEND_HEIGHT,
    GlassBackdrop,
)
from bilibili_downloader.gui.widgets.header_backdrop import HEADER_HEIGHT
from bilibili_downloader.gui.widgets.workspace_background import (
    paint_workspace_background,
)


class ThemePreviewButton(QAbstractButton):
    def __init__(self, name, description, theme_id, parent=None):
        super().__init__(parent)
        self.theme_id = theme_id
        self.name, self.description = name, description
        self.setCheckable(True)
        self.setAccessibleName(f"{name}主题，{description}")
        self.setToolTip(f"{name} · {description}；保存后应用")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.sizeHint().height())
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("focusRadius", UI_METRICS.card_radius - 2)
        self.setCursor(Qt.PointingHandCursor)
        self.toggled.connect(self._describe_selection)
        self._describe_selection(False)

    def _describe_selection(self, selected):
        self.setAccessibleDescription(
            "已选，保存设置后应用" if selected else "空格选择，保存设置后应用"
        )

    def sizeHint(self):
        return QSize(max(88, self.fontMetrics().horizontalAdvance(self.name) + 58),
                     max(38, self.fontMetrics().height() + 14))

    def event(self, event):
        if event.type() in (QEvent.StyleChange, QEvent.FontChange) and hasattr(self, "description"):
            self.setMinimumHeight(self.sizeHint().height())
            self.updateGeometry()
            self.update()
        return super().event(event)

    def paintEvent(self, event):
        dark = bool(QApplication.instance().property("darkTheme"))
        p = theme_palette(dark, self.theme_id)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        selected = self.isChecked()
        painter.setPen(QPen(QColor(palette().focus if selected else palette().card_border), 2 if selected else 1))
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), UI_METRICS.card_radius, UI_METRICS.card_radius)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.accent))
        painter.drawEllipse(QRectF(12, (self.height() - 14) / 2, 14, 14))
        selected_width = self.fontMetrics().horizontalAdvance("✓") + 8 if selected else 0
        name = QRectF(34, 0, self.width() - 44 - selected_width, self.height())
        painter.setPen(QColor(p.text))
        painter.drawText(name, Qt.AlignLeft | Qt.AlignVCenter, self.name)
        if self.isChecked():
            painter.setPen(QColor(palette().active_text))
            painter.drawText(
                QRectF(self.width() - 10 - selected_width, 0, selected_width, self.height()),
                Qt.AlignRight | Qt.AlignVCenter,
                "✓",
            )
        painter.end()


class BackgroundThumbnail(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.pixel_art = False
        self.setText("默认背景")
        self.setFixedSize(160, 90)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    def clear(self):
        self._pixmap = QPixmap()
        self.update()

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def pixmap(self):
        return self._pixmap

    def paintEvent(self, event):
        p = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(p.surface_raised))
        painter.setPen(QPen(QColor(p.focus if self.hasFocus() else p.divider), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        if self._pixmap.isNull():
            painter.setPen(QColor(p.muted))
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        else:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 7, 7)
            painter.setClipPath(clip)
            dpr = self.devicePixelRatioF()
            scaled = self._pixmap.scaled(QSize(round((self.width() - 4) * dpr), round((self.height() - 4) * dpr)),
                                         Qt.KeepAspectRatioByExpanding,
                                         Qt.FastTransformation if self.pixel_art else Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            size = scaled.deviceIndependentSize()
            painter.drawPixmap(
                QPointF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2), scaled,
            )
        painter.end()


class WorkspacePreview(QWidget):
    def __init__(self, title, pixmap, theme_id, parent=None, visibility=None, *, builtin=False, pixel_art=False, workspace="download"):
        super().__init__(parent)
        self.title, self.pixmap, self.theme_id = title, pixmap, theme_id
        self.builtin, self.pixel_art = builtin, pixel_art
        self.visibility = (visibility or BackgroundVisibility()).model_copy(deep=True)
        self.is_dark = None
        self.workspace = workspace
        self.viewport_size = QSize(1320, 860)
        self.original = False
        self._glass = GlassBackdrop()
        self.glass_blur = DEFAULT_GLASS_BLUR
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def canvas_rect(self):
        size = self.viewport_size.scaled(self.size() - QSize(4, 4), Qt.KeepAspectRatio)
        return QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())

    def background_rect(self):
        return QRectF(0, 0, self.viewport_size.width(), self.viewport_size.height())

    def paintEvent(self, event):
        dark = bool(QApplication.instance().property("darkTheme")) if self.is_dark is None else self.is_dark
        colors = theme_palette(dark, self.theme_id)
        p = colors if self.pixmap.isNull() else wallpaper_palette(colors, dark)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if self.original and not self.pixmap.isNull():
            painter.setBrush(QColor(p.surface_raised))
            painter.drawRoundedRect(QRectF(self.rect()), UI_METRICS.radius, UI_METRICS.radius)
            size = self.pixmap.size().scaled(self.size() - QSize(16, 16), Qt.KeepAspectRatio)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, not self.pixel_art)
            painter.drawPixmap(QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height()), self.pixmap, QRectF(self.pixmap.rect()))
            painter.end()
            return
        canvas = self.canvas_rect()
        painter.setPen(QPen(QColor(p.card_border), 1))
        painter.setBrush(Qt.NoBrush)
        radius = canvas.width() / self.viewport_size.width() * UI_METRICS.card_radius
        painter.drawRoundedRect(canvas.adjusted(-1, -1, 1, 1), radius, radius)
        painter.setPen(Qt.NoPen)
        painter.translate(canvas.topLeft())
        painter.scale(canvas.width() / self.viewport_size.width(), canvas.height() / self.viewport_size.height())
        width, height = self.viewport_size.width(), self.viewport_size.height()
        background = self.background_rect()
        clip = QPainterPath()
        clip.addRoundedRect(background, UI_METRICS.card_radius, UI_METRICS.card_radius)
        painter.setClipPath(clip)
        visible = self.visibility.dark if dark else self.visibility.light
        paint_workspace_background(
            painter, background, self.pixmap, dark, self.theme_id, visible,
            builtin=self.builtin, pixel_art=self.pixel_art,
        )
        key = (self.pixmap.cacheKey(), self.theme_id, visible, self.builtin, self.pixel_art, self.devicePixelRatioF())
        self._glass.prepare(
            key, self.viewport_size,
            lambda p, r: paint_workspace_background(p, r, self.pixmap, dark, self.theme_id, visible, builtin=self.builtin, pixel_art=self.pixel_art),
            dark, colors, self.glass_blur, ambient=self.pixmap.isNull(),
        )
        metrics = UI_METRICS
        compact_sidebar = width < metrics.sidebar_breakpoint
        sidebar = metrics.sidebar_compact_width if compact_sidebar else metrics.sidebar_width
        content = QRectF(sidebar, HEADER_HEIGHT, width - sidebar, height - HEADER_HEIGHT - 36)
        rail = QRectF(0, 0, sidebar, height - 36)
        self._glass.paint(painter, rail, rail, edge=Qt.RightEdge)
        header = QRectF(sidebar, 0, width - sidebar, HEADER_HEIGHT)
        handoff = QRectF(sidebar, HEADER_HEIGHT, width - sidebar, HEADER_BLEND_HEIGHT)
        self._glass.paint_header_handoff(painter, handoff, handoff)
        status_bar = QRectF(0, height - 36, width, 36)
        self._glass.paint(painter, header, header, edge=Qt.BottomEdge)
        self._glass.paint(painter, status_bar, status_bar, clear=True, edge=Qt.TopEdge)
        font = QFont(painter.font())
        font.setPixelSize(14)
        painter.setFont(font)

        def text(rect, value, *, muted=False, protected=False, bold=False):
            rect = QRectF(rect)
            painter.save()
            f = QFont(painter.font())
            f.setBold(bold)
            painter.setFont(f)
            color = p.muted if muted else p.text
            label = painter.fontMetrics().elidedText(value, Qt.ElideRight, max(1, int(rect.width())))
            if protected and not self.pixmap.isNull():
                bounds = painter.fontMetrics().boundingRect(rect.toRect(), int(Qt.AlignLeft | Qt.AlignVCenter), label)
                paint_reading_surface(painter, bounds.adjusted(-4, -3, 4, 3), p.surface, color)
            painter.setPen(QColor(color))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.restore()

        def card(rect, glass=False, *, clear=True):
            if glass:
                self._glass.paint(painter, rect, rect, clear=clear)
                return
            self._glass.paint_reading(painter, rect, rect)

        def tabs(x, y, labels, current=0):
            widths = [painter.fontMetrics().horizontalAdvance(label) + 30 for label in labels]
            card(QRectF(x, y, sum(widths) + 8, 40), True, clear=False)
            x += 4
            for index, (label, tab_width) in enumerate(zip(labels, widths)):
                box = QRectF(x + 2, y + 5, tab_width - 4, 30)
                if index == current:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(p.subtle_selection))
                    painter.drawRoundedRect(box, metrics.radius, metrics.radius)
                text(box.adjusted(11, 0, -9, 0), label, muted=index != current, bold=index == current)
                x += tab_width

        def control(rect, value, primary=False):
            painter.setPen(QPen(QColor((p.primary or p.accent) if primary else p.control_border), 1))
            fill = QColor((p.primary or p.accent) if primary else p.surface_raised)
            if not primary and not self.pixmap.isNull():
                fill.setAlpha(READING_FIELD_OPACITY)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, UI_METRICS.radius, UI_METRICS.radius)
            painter.setPen(QColor((p.primary_text or p.accent_text) if primary else p.text))
            painter.drawText(rect.adjusted(12, 0, -8, 0), Qt.AlignVCenter, value)

        def table(rect, headers, rows):
            self._glass.paint_reading(painter, rect, rect, clear_below=rect.top() + 48 + len(rows) * 56)
            inset = metrics.surface_inset
            rect = rect.adjusted(inset, inset, -inset, -inset)
            cell = rect.width() / len(headers)
            header = QColor(p.surface_raised)
            header.setAlpha(TABLE_HEADER_OPACITY)
            painter.setPen(Qt.NoPen)
            painter.setBrush(header)
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width(), 40), UI_METRICS.radius, UI_METRICS.radius)
            for column, label in enumerate(headers):
                text(QRectF(rect.left() + column * cell + 12, rect.top(), cell - 24, 40), label, muted=True, protected=False)
            for row, values in enumerate(rows):
                row_rect = QRectF(rect.left(), rect.top() + 40 + row * 56, rect.width(), 56)
                divider = QColor(p.row_divider)
                divider.setAlpha(TABLE_DIVIDER_OPACITY)
                painter.setPen(divider)
                painter.drawLine(row_rect.bottomLeft(), row_rect.bottomRight())
                for column, label in enumerate(values):
                    value = QRectF(rect.left() + column * cell + 12, row_rect.top(), cell - 24, 56)
                    if headers[column] == "进度":
                        track = QRectF(value.left(), value.center().y() - 4, max(0, value.width() - 43), 8)
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(p.control_border))
                        painter.drawRoundedRect(track, 4, 4)
                        track.setWidth(track.width() * int(label.removesuffix("%")) / 100)
                        painter.setBrush(QColor((p.accent, p.muted, p.success)[row]))
                        painter.drawRoundedRect(track, 4, 4)
                        value.setLeft(value.right() - 37)
                    text(value, label)

        text(QRectF(sidebar + 24, 0, width - sidebar - 48, HEADER_HEIGHT), self.title, protected=False, bold=True)
        names = ("视频下载", "直播录制", "任务中心", "设置")
        keys = ("download", "live", "tasks", "settings")
        for i, name in enumerate(names):
            rect = QRectF(12, 130 + i * 56, sidebar - 24, 42)
            if keys[i] == self.workspace:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(p.subtle_selection))
                painter.drawRoundedRect(rect, UI_METRICS.radius, UI_METRICS.radius)
            text(rect.adjusted(12, 0, -2, 0), name[:2] if compact_sidebar else name, bold=keys[i] == self.workspace)
        if not compact_sidebar:
            text(QRectF(24, 48, sidebar - 40, 36), "BiliFlow", protected=False, bold=True)
        density = density_for_height(height)
        margin, padding, gap = density.page_margin, density.card_padding, density.section_gap
        inner = content.adjusted(margin, margin, -margin, -margin)
        footer_height = UI_METRICS.settings_bar_height if self.workspace == "settings" else 72
        footer = QRectF(inner.left(), inner.bottom() - footer_height, inner.width(), footer_height)
        top = inner.top()
        painter.save()
        painter.setClipRect(QRectF(inner.left(), top, inner.width(), max(0, footer.top() - top - gap)))
        if self.workspace == "download":
            wide = inner.width() >= UI_METRICS.output_split_width
            source_width = inner.width() - 336 - gap if wide else inner.width()
            source = QRectF(inner.left(), top, source_width, 186)
            tabs(source.left(), top, ("单个解析", "批量导入"))
            text(QRectF(source.left() + 8, top + 42, source.width() - 108, 26), "BV1DEMO2026A", muted=True)
            text(QRectF(source.right() - 84, top + 42, 76, 26), "编辑来源", muted=True)
            large = wide and not density.compact
            cover_width = min(520, source.width() - padding * 2) if large else 128
            cover_height = cover_width * 9 / 16
            preview_card = QRectF(source.left(), top + 78, source.width(), cover_height + (126 if large else 30))
            card(preview_card)
            cover = QRectF(source.left() + padding, preview_card.top() + 14, cover_width, cover_height)
            control(cover, "视频封面")
            x = source.left() + padding if large else cover.right() + gap
            y = cover.bottom() + 12 if large else cover.top()
            text(QRectF(x, y, source.right() - x - padding, 32), "星轨旅记：城市夜航", bold=True)
            text(QRectF(x, y + 40, source.right() - x - padding, 24), "UP 主 · 小流", muted=True)
            text(QRectF(x, y + 72, source.right() - x - padding, 24), "12:34 · BV1DEMO2026A", muted=True)
            settings = QRectF(source.right() + gap if wide else inner.left(), top if wide else source.bottom() + gap,
                              336 if wide else inner.width(), 552 if wide else 340)
            card(settings)
            text(QRectF(settings.left() + padding, settings.top() + padding, settings.width() - padding * 2, 28), "下载设置", bold=True)
            for i, (label, value) in enumerate((("分 P", "全部 2 P"), ("输出类型", "视频 / MP4"), ("画质", "1080P"))):
                columns = 1 if wide or settings.width() < 550 else 2
                field_width = (settings.width() - padding * 2 - gap * (columns - 1)) / columns
                x = settings.left() + padding + (i % columns) * (field_width + gap)
                y = settings.top() + padding + 36 + (i // columns) * 48
                text(QRectF(x, y, 76, 40), label, muted=True)
                control(QRectF(x + 84, y, field_width - 84, 40), value)
            y += 48
            text(QRectF(settings.left() + padding, y, settings.width() - padding * 2, 28), "一起保存", bold=True)
            for i, label in enumerate(("✓ 弹幕 · ASS", "✓ 字幕 · SRT", "✓ 封面 · 图片", "✓ 元数据 · JSON")):
                text(QRectF(settings.left() + padding, y + 36 + i * 44, settings.width() - padding * 2, 40), label)
            text(QRectF(settings.left() + padding, y + 224, settings.width() - padding * 2, 28), "高级设置    展开", bold=True)
            text(QRectF(settings.left() + padding, y + 256, settings.width() - padding * 2, 24), "HEVC · AAC 192kbps", muted=True)
        elif self.workspace == "live":
            hero = QRectF(inner.left(), top, inner.width(), 72)
            card(hero, True)
            control(QRectF(hero.left() + padding, top + 16, hero.width() - 152, 40), "直播间链接或房间号")
            control(QRectF(hero.right() - 128, top + 16, 112, 40), "添加并监控", True)
            top = hero.bottom() + gap
            wide = inner.width() >= 880
            left_width = (inner.width() - gap) * .62 if wide else inner.width()
            left = QRectF(inner.left(), top, left_width, 220)
            table(left, ("直播间", "状态", "时长"), (("城市漫游", "录制中", "00:43:12"), ("星轨电台", "等待开播", "00:00:00")))
            right = QRectF(left.right() + gap if wide else inner.left(), top if wide else left.bottom() + gap,
                           inner.width() - left_width - gap if wide else inner.width(), 304)
            card(right)
            for i, value in enumerate(("房间详情 · 城市漫游", "录制中 · 43:12 · 128 MB", "保存位置：~/Videos/BiliFlow", "下次拉流 · 当前最高画质", "✓ 自动监控并录制")):
                text(QRectF(right.left() + padding, right.top() + padding + i * 44, right.width() - padding * 2, 40), value, bold=i == 0)
            control(QRectF(right.right() - 132, right.bottom() - 54, 116, 40), "停止本场")
        elif self.workspace == "tasks":
            tabs(inner.left(), top, ("下载队列", "当前录制", "录制历史", "下载文件"))
            tools = QRectF(inner.left(), top + 50, inner.width(), 44)
            card(tools, True, clear=False)
            text(tools.adjusted(12, 0, -12, 0), "全部任务       当前筛选       3 项          暂停    继续    更多", protected=False)
            docked = inner.width() >= metrics.queue_detail_breakpoint
            list_width = inner.width() - metrics.queue_detail_width - metrics.queue_detail_gap if docked else inner.width()
            task_table = QRectF(inner.left(), top + 106, list_width, max(200, inner.height() - 224))
            table(task_table, ("作品", "规格", "进度", "状态", "操作"), (("城市夜航", "4K · HEVC", "68%", "下载中", "暂停"), ("晨光抵达", "1080P · AVC", "32%", "已暂停", "继续"), ("创作幕后", "FLAC", "100%", "完成", "打开目录")))
            summary = QRectF(task_table.right() + metrics.queue_detail_gap if docked else inner.left(),
                             task_table.top() if docked else task_table.bottom() + gap,
                             metrics.queue_detail_width if docked else inner.width(),
                             task_table.height() if docked else 84)
            card(summary)
            text(summary.adjusted(16, 8, -16, 36 - summary.height()), "城市夜航", bold=True)
            text(QRectF(summary.left() + 16, summary.top() + 44, summary.width() - 32, 28), "4K · HEVC      完整详情", muted=True)
        else:
            tabs(inner.left(), top, ("下载", "直播", "外观", "工具与存储", "关于与更新"), 2)
            form = QRectF(inner.left(), top + 52, inner.width(), 340)
            card(form)
            for i, value in enumerate(("跟随系统      日间      夜间                        星河      晴海",
                                        "玻璃模糊     18 px",
                                        "任务中心      选择背景…      恢复默认")):
                control(QRectF(form.left() + padding, form.top() + padding + i * 48, form.width() - 2 * padding, 40), value)
            card(QRectF(form.left() + form.width() * .27, form.top() + 176, form.width() * .46, 150))
        painter.restore()
        if self.workspace in ("download", "settings"):
            card(footer, True)
            text(footer.adjusted(16, 0, -156, -20 if self.workspace == "download" else 0), "已保存" if self.workspace == "settings" else "已选 2 个任务", protected=False)
            if self.workspace == "download":
                path = "保存至 ~/Downloads/BiliFlow"
                path_width = min(path_preferred_width(painter.fontMetrics(), path), max(32, footer.width() - 300))
                text(QRectF(footer.left() + 16, footer.top() + 36, path_width, 24), path, muted=True, protected=False)
                text(QRectF(footer.left() + 16 + path_width + 8, footer.top() + 36, 80, 24), "修改目录", muted=True, protected=False)
            button_height = 32 if self.workspace == "settings" else 44
            control(QRectF(footer.right() - 144, footer.center().y() - button_height / 2, 128, button_height), "保存设置" if self.workspace == "settings" else "加入队列", True)
        painter.end()
