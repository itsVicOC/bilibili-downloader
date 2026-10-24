"""Theme selection cards and faithful, isolated wallpaper effect previews."""

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QSizePolicy, QWidget

from bilibili_downloader.core.models import DEFAULT_GLASS_BLUR, BackgroundVisibility
from bilibili_downloader.gui.layout_policy import (
    density_for_height,
    field_columns,
    output_side_by_side,
    path_preferred_width,
)
from bilibili_downloader.gui.resources.styles import (
    UI_METRICS,
    background_reading_alpha,
    glass_text_color,
    theme_palette,
)
from bilibili_downloader.gui.widgets.background_readability import paint_reading_surface
from bilibili_downloader.gui.widgets.components import palette
from bilibili_downloader.gui.widgets.glass_surface import GlassBackdrop
from bilibili_downloader.gui.widgets.header_backdrop import (
    HEADER_HEIGHT,
    paint_header_backdrop,
)
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
        self.setMinimumHeight(140)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.toggled.connect(self._describe_selection)
        self._describe_selection(False)

    def _describe_selection(self, selected):
        self.setAccessibleDescription(
            "已选中，保存设置后应用" if selected else "按空格选择此主题，保存设置后应用"
        )

    def sizeHint(self):
        return QSize(260, 140)

    def event(self, event):
        if event.type() == QEvent.StyleChange:
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
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(5, 5, -5, -5), UI_METRICS.card_radius, UI_METRICS.card_radius)
        if self.hasFocus() and self.property("keyboardFocus"):
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(palette().focus), 1.5, Qt.DashLine))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)
        canvas = QRectF(12, 12, self.width() - 24, 74)
        painter.fillRect(canvas, QColor(p.background))
        painter.fillRect(QRectF(12, 12, 28, 74), QColor(p.sidebar))
        painter.fillRect(QRectF(18, 32, 16, 5), QColor(p.accent))
        painter.fillRect(QRectF(48, 18, self.width() - 62, 14), QColor(p.background))
        painter.fillRect(QRectF(48, 34, self.width() - 62, 1), QColor(p.divider))
        painter.fillRect(QRectF(48, 39, self.width() - 130, 5), QColor(p.muted))
        painter.fillRect(QRectF(48, 51, self.width() - 130, 26), QColor(p.surface))
        painter.fillRect(
            QRectF(self.width() - 73, 51, 58, 26), QColor(p.primary or p.accent)
        )
        painter.setPen(QColor(p.text))
        painter.drawText(14, 107, self.name)
        painter.setPen(QColor(p.muted))
        painter.drawText(14, 128, self.description)
        if self.isChecked():
            painter.setPen(QColor(palette().active_text))
            painter.drawText(
                QRectF(self.width() - 90, 90, 72, 26),
                Qt.AlignRight | Qt.AlignVCenter,
                "✓ 已选",
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
            scaled = self._pixmap.scaled(
                156, 86, Qt.KeepAspectRatioByExpanding,
                Qt.FastTransformation if self.pixel_art else Qt.SmoothTransformation,
            )
            painter.setClipRect(self.rect().adjusted(2, 2, -2, -2))
            painter.drawPixmap(
                (self.width() - scaled.width()) // 2,
                (self.height() - scaled.height()) // 2,
                scaled,
            )
        painter.end()


class WorkspacePreview(QWidget):
    def __init__(self, title, pixmap, theme_id, parent=None, visibility=None, *, builtin=False, pixel_art=False, workspace="download"):
        super().__init__(parent)
        self.title, self.pixmap, self.theme_id = title, pixmap, theme_id
        self.builtin, self.pixel_art = builtin, pixel_art
        self.visibility = (visibility or BackgroundVisibility()).model_copy(deep=True)
        self.is_dark = bool(QApplication.instance().property("darkTheme"))
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
        sidebar = 72 if self.viewport_size.width() < 1120 else 208
        return QRectF(sidebar, HEADER_HEIGHT, self.viewport_size.width() - sidebar, self.viewport_size.height() - HEADER_HEIGHT - 36)

    def paintEvent(self, event):
        p = theme_palette(self.is_dark, self.theme_id)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(p.surface_raised))
        if self.original and not self.pixmap.isNull():
            size = self.pixmap.size().scaled(self.size() - QSize(16, 16), Qt.KeepAspectRatio)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, not self.pixel_art)
            painter.drawPixmap(QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height()), self.pixmap, QRectF(self.pixmap.rect()))
            painter.end()
            return
        canvas = self.canvas_rect()
        painter.translate(canvas.topLeft())
        painter.scale(canvas.width() / self.viewport_size.width(), canvas.height() / self.viewport_size.height())
        width, height = self.viewport_size.width(), self.viewport_size.height()
        painter.setClipRect(QRectF(0, 0, width, height))
        painter.fillRect(QRectF(0, 0, width, height), QColor(p.background))
        content = self.background_rect()
        paint_workspace_background(
            painter, content, self.pixmap, self.is_dark, self.theme_id,
            self.visibility.dark if self.is_dark else self.visibility.light,
            builtin=self.builtin, pixel_art=self.pixel_art,
        )
        if not self.pixmap.isNull():
            visible = self.visibility.dark if self.is_dark else self.visibility.light
            key = (self.pixmap.cacheKey(), self.theme_id, visible, self.builtin, self.pixel_art)
            self._glass.prepare(
                key, content.size().toSize(),
                lambda p, r: paint_workspace_background(p, r, self.pixmap, self.is_dark, self.theme_id, visible, builtin=self.builtin, pixel_art=self.pixel_art),
                self.is_dark, p, self.glass_blur,
            )
        sidebar = content.left()
        painter.fillRect(QRectF(0, 0, sidebar, height), QColor(p.sidebar))
        painter.fillRect(QRectF(sidebar - 1, 0, 1, height), QColor(p.divider))
        paint_header_backdrop(
            painter, QRectF(sidebar, 0, width - sidebar, HEADER_HEIGHT),
            self.is_dark, self.theme_id,
        )
        painter.fillRect(QRectF(0, height - 36, width, 36), QColor(p.sidebar))
        font = QFont(painter.font())
        font.setPixelSize(14)
        painter.setFont(font)

        def text(rect, value, *, muted=False, protected=False, bold=False):
            rect = QRectF(rect)
            painter.save()
            f = QFont(painter.font())
            f.setBold(bold)
            painter.setFont(f)
            color = (glass_text_color(p) if not self.pixmap.isNull() else p.muted) if muted else p.text
            label = painter.fontMetrics().elidedText(value, Qt.ElideRight, max(1, int(rect.width())))
            if protected and not self.pixmap.isNull():
                bounds = painter.fontMetrics().boundingRect(rect.toRect(), int(Qt.AlignLeft | Qt.AlignVCenter), label)
                paint_reading_surface(painter, bounds.adjusted(-4, -3, 4, 3), p.surface, color)
            painter.setPen(QColor(color))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.restore()

        def card(rect, solid=False):
            if not self.pixmap.isNull():
                self._glass.paint(painter, rect, QRectF(rect).translated(-content.topLeft()))
                return
            surface = QColor(p.surface)
            if not solid and not self.pixmap.isNull():
                surface.setAlpha(background_reading_alpha(p.surface, p.text, p.muted, p.active_text))
            painter.setBrush(surface)
            painter.setPen(QPen(QColor(p.divider), 1))
            painter.drawRoundedRect(rect, 14, 14)

        def control(rect, value, primary=False):
            painter.setPen(QPen(QColor(p.border), 1))
            painter.setBrush(QColor((p.primary or p.accent) if primary else p.surface))
            painter.drawRoundedRect(rect, 8, 8)
            painter.setPen(QColor((p.primary_text or p.accent_text) if primary else p.text))
            painter.drawText(rect.adjusted(12, 0, -8, 0), Qt.AlignVCenter, value)

        def table(rect, headers, rows):
            card(rect)
            cell = rect.width() / len(headers)
            painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 40), QColor(p.surface_raised))
            for column, label in enumerate(headers):
                text(QRectF(rect.left() + column * cell + 12, rect.top(), cell - 24, 40), label, muted=True, protected=False)
            for row, values in enumerate(rows):
                row_rect = QRectF(rect.left(), rect.top() + 40 + row * 56, rect.width(), 56)
                surface = QColor(p.surface)
                if not self.pixmap.isNull():
                    surface.setAlpha(background_reading_alpha(p.surface, p.text))
                painter.fillRect(row_rect, surface)
                for column, label in enumerate(values):
                    text(QRectF(rect.left() + column * cell + 12, row_rect.top(), cell - 24, 56), label, protected=False)

        text(QRectF(sidebar + 24, 0, width - sidebar - 48, HEADER_HEIGHT), self.title, protected=False, bold=True)
        names = ("视频下载", "直播录制", "任务中心", "设置")
        keys = ("download", "live", "tasks", "settings")
        for i, name in enumerate(names):
            rect = QRectF(12, 130 + i * 56, sidebar - 24, 42)
            if keys[i] == self.workspace:
                painter.fillRect(rect, QColor(p.selection))
            text(rect.adjusted(12, 0, -2, 0), name if sidebar > 100 else name[:2], protected=False)
        if sidebar > 100:
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
            text(QRectF(inner.left(), top, inner.width(), 32), "单个解析       批量导入", bold=True)
            top += 40
            hero = QRectF(inner.left(), top, inner.width(), UI_METRICS.source_resolved_height)
            card(hero)
            control(QRectF(hero.left() + padding, top + 12, hero.width() - 144 - padding, 44), "BV1DEMO2026A")
            control(QRectF(hero.right() - 120, top + 12, 108, 44), "重新解析", True)
            top = hero.bottom() + gap
            summary = QRectF(inner.left(), top, inner.width(), density.cover_height + padding * 2)
            card(summary)
            cover = QRectF(summary.left() + padding, top + padding, density.cover_width, density.cover_height)
            control(cover, "视频封面")
            x = cover.right() + gap
            text(QRectF(x, top + padding, summary.right() - x - 16, 28), "星轨旅记：城市夜航", bold=True)
            text(QRectF(x, top + padding + 32, summary.right() - x - 16, 22), "UP 主 · 小流    已解析", muted=True)
            text(QRectF(x, top + padding + 56, summary.right() - x - 16, 22), "12:34 · BV1DEMO2026A", muted=True)
            top = summary.bottom() + gap
            wide = output_side_by_side(inner.width())
            spec_width = (inner.width() - gap) * .6 if wide else inner.width()
            columns = field_columns(spec_width - 2 * padding)
            field_height = 40 if density.compact else 68
            specs = QRectF(inner.left(), top, spec_width, padding * 2 + 28 + gap + 2 * field_height + 12)
            if columns == 1:
                specs.setHeight(specs.height() + 2 * (field_height + 12))
            card(specs)
            text(QRectF(specs.left() + padding, top + padding, specs.width() - 2 * padding, 28), "输出规格", bold=True)
            field_width = (specs.width() - 2 * padding - (columns - 1) * 12) / columns
            for i, (label, value) in enumerate((("分 P 范围", "当前视频"), ("输出类型", "视频 / MP4"), ("画面质量", "1080P"), ("视频编码", "AVC"))):
                x = specs.left() + padding + i % columns * (field_width + 12)
                y = specs.top() + padding + 28 + gap + i // columns * (field_height + 12)
                if density.compact:
                    text(QRectF(x, y, 76, 40), label)
                    control(QRectF(x + 84, y, max(40, field_width - 84), 40), value)
                else:
                    text(QRectF(x, y, field_width, 20), label)
                    control(QRectF(x, y + 28, field_width, 40), value)
            extras = QRectF(specs.right() + gap if wide else inner.left(), top if wide else specs.bottom() + gap,
                            inner.width() - spec_width - gap if wide else inner.width(), padding * 2 + 28 + gap + 4 * 40 + 28)
            card(extras)
            text(QRectF(extras.left() + padding, extras.top() + padding, extras.width() - padding * 2, 28), "附加内容", bold=True)
            for i, label in enumerate(("✓  下载弹幕 · ASS", "✓  下载字幕 · SRT", "✓  保存封面 · 图片", "✓  保存元数据 · JSON")):
                y = extras.top() + padding + 28 + gap + i * 40 + (28 if i > 1 else 0)
                text(QRectF(extras.left() + padding, y, extras.width() - padding * 2, 40), label)
                if i == 1:
                    text(QRectF(extras.left() + padding + 24, y + 40, extras.width() - padding * 2 - 24, 28), "□  全部字幕", muted=True)
        elif self.workspace == "live":
            hero = QRectF(inner.left(), top, inner.width(), 96)
            card(hero)
            text(QRectF(hero.left() + padding, top + 8, hero.width() - 2 * padding, 28), "添加直播间 · 开播自动录制", bold=True)
            control(QRectF(hero.left() + padding, top + 44, hero.width() - 152, 40), "直播间链接或房间号")
            control(QRectF(hero.right() - 128, top + 44, 112, 40), "添加并监控", True)
            top = hero.bottom() + gap
            wide = inner.width() >= 880
            left_width = (inner.width() - gap) * .62 if wide else inner.width()
            left = QRectF(inner.left(), top, left_width, 220)
            table(left, ("直播间", "状态", "时长", "操作"), (("城市漫游", "录制中", "00:43:12", "停止本场"), ("星轨电台", "等待开播", "00:00:00", "更多")))
            right = QRectF(left.right() + gap if wide else inner.left(), top if wide else left.bottom() + gap,
                           inner.width() - left_width - gap if wide else inner.width(), 260)
            card(right)
            for i, value in enumerate(("房间详情 · 城市漫游", "录制中 · 43:12 · 128 MB", "保存位置：~/Videos/BiliFlow", "下次拉流 · 当前最高画质", "✓ 自动监控并录制")):
                text(QRectF(right.left() + padding, right.top() + padding + i * 44, right.width() - padding * 2, 40), value, bold=i == 0)
        elif self.workspace == "tasks":
            text(QRectF(inner.left(), top, inner.width(), 36), "下载队列       当前录制       录制历史", bold=True)
            tools = QRectF(inner.left(), top + 44, inner.width(), 44)
            card(tools, True)
            text(tools.adjusted(12, 0, -12, 0), "全部任务       当前筛选       3 项          暂停    继续    更多", protected=False)
            table(QRectF(inner.left(), top + 100, inner.width(), max(200, inner.height() - 224)), ("作品", "规格", "进度", "状态", "操作"), (("城市夜航", "4K · HEVC", "68%", "下载中", "暂停"), ("晨光抵达", "1080P · AVC", "32%", "已暂停", "继续"), ("创作幕后", "FLAC", "100%", "完成", "打开目录")))
        else:
            text(QRectF(inner.left(), top, inner.width(), 36), "下载    直播    外观    工具与存储    关于与更新", bold=True)
            for i, (heading, value) in enumerate((("显示模式 · 立即生效", "跟随系统      日间      夜间"), ("应用配色 · 保存后生效", "星河 · 粉紫星空       晴海 · 晴空青蓝"), ("工作区背景", "视频下载      直播录制      任务中心      设置"))):
                panel = QRectF(inner.left(), top + 44 + i * (116 + gap), inner.width(), 116)
                card(panel)
                text(QRectF(panel.left() + padding, panel.top() + padding, panel.width() - 2 * padding, 28), heading, bold=True)
                control(QRectF(panel.left() + padding, panel.top() + 56, panel.width() - 2 * padding, 40), value)
        painter.restore()
        if self.workspace != "tasks":
            card(footer, True)
            text(footer.adjusted(16, 0, -156, -20 if self.workspace == "download" else 0), "所有修改已保存" if self.workspace == "settings" else "已选 1 项 · 当前输出设置", protected=False)
            if self.workspace == "download":
                path = "保存至 ~/Downloads/BiliFlow"
                path_width = min(path_preferred_width(painter.fontMetrics(), path), max(32, footer.width() - 300))
                text(QRectF(footer.left() + 16, footer.top() + 36, path_width, 24), path, muted=True, protected=False)
                text(QRectF(footer.left() + 16 + path_width + 8, footer.top() + 36, 80, 24), "修改目录", muted=True, protected=False)
            button_height = 32 if self.workspace == "settings" else 44
            control(QRectF(footer.right() - 144, footer.center().y() - button_height / 2, 128, button_height), "保存设置" if self.workspace == "settings" else "停止本场" if self.workspace == "live" else "加入下载队列", True)
        painter.end()
