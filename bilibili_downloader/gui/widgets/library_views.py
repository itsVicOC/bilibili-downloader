"""Model-backed view and delegates for browsing downloaded media."""

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from bilibili_downloader.gui.widgets.check_box import draw_check_indicator
from bilibili_downloader.gui.widgets.components import line_icon, palette
from bilibili_downloader.gui.widgets.file_table import DIRECTORY_COLUMN, STATE_COLUMN
from bilibili_downloader.gui.widgets.glass_surface import ScrollAreaSurface
from bilibili_downloader.gui.widgets.row_hover import row_option

_BLOCKING_STATES = {"missing", "inaccessible", "recycled"}


def _summary(record):
    return " · ".join((record.kind, record.codec))


def _tooltip(record):
    return "\n".join(filter(None, (record.title, record.author, _summary(record),
                                     record.state, str(record.path))))


def _check_role(binding, record, role):
    if role == Qt.CheckStateRole:
        return Qt.Checked if record.id in binding.state.selected else Qt.Unchecked
    if role == Qt.UserRole:
        return record.id
    if role == Qt.ToolTipRole:
        return _tooltip(record)
    return None


def _change_check(binding, record, value, role):
    if record is None or role != Qt.CheckStateRole:
        return False
    checked = value in (Qt.Checked, Qt.Checked.value)
    if checked != (record.id in binding.state.selected):
        binding.toggle(record.id)
    return True


class _GridModel(QAbstractListModel):
    def __init__(self, binding, parent):
        super().__init__(parent)
        self.binding = binding
        self.records = []
        self.rows_by_id = {}

    def replace(self, records):
        self.beginResetModel()
        self.records = records
        self.rows_by_id = {record.id: row for row, record in enumerate(records)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def index_for(self, asset_id):
        return self.index(self.rows_by_id.get(asset_id, -1), 0)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        record = self.records[index.row()]
        if role == Qt.DisplayRole:
            return record.title
        if role == Qt.AccessibleTextRole:
            return _tooltip(record)
        return _check_role(self.binding, record, role)

    def flags(self, index):
        return (super().flags(index) | Qt.ItemIsUserCheckable) if index.isValid() else Qt.NoItemFlags

    def setData(self, index, value, role=Qt.EditRole):
        return index.isValid() and _change_check(self.binding, self.records[index.row()], value, role)


class _CoverPainter:
    def __init__(self, icon_size):
        self.icon_size = icon_size
        self.icons = {}

    def paint(self, painter, rect, audio, image, colors):
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors.surface_raised))
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(rect), 5, 5)
        painter.drawPath(outline)
        if image.isNull():
            name = "audio" if audio else "live"
            key = name, colors.muted
            if key not in self.icons:
                self.icons[key] = line_icon(name, colors.muted, self.icon_size)
            target = QRect(QPoint(), QSize(self.icon_size, self.icon_size))
            target.moveCenter(rect.center())
            self.icons[key].paint(painter, target)
        else:
            target = QRect(QPoint(), image.size().scaled(rect.size(), Qt.KeepAspectRatio))
            target.moveCenter(rect.center())
            painter.setClipPath(outline, Qt.IntersectClip)
            painter.drawImage(target, image)
        painter.restore()


class FileLabelDelegate(QStyledItemDelegate):
    """Paint the list's title, specification and file status over native row feedback."""

    def __init__(self, parent, thumbnail_for=None):
        super().__init__(parent)
        self.thumbnail_for = thumbnail_for
        self.cover_painter = _CoverPainter(19)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator
        lines, opt.text = opt.text.splitlines()[:2], ""
        column = index.column()
        if column != 0:
            opt.widget.style().drawControl(QStyle.CE_ItemViewItem, row_option(opt, index), painter, opt.widget)
        painter.save()
        painter.setClipRect(opt.rect)
        colors = palette(opt.widget)
        x = opt.rect.left() + 10
        primary = QFont(opt.font)
        if self.thumbnail_for is not None:
            cover = QRect(x, opt.rect.center().y() - 17, 64, 36)
            audio, image = self.thumbnail_for(index.data(Qt.UserRole))
            self.cover_painter.paint(painter, cover, audio, image, colors)
            x = cover.right() + 11
            primary.setWeight(QFont.DemiBold)
        secondary = QFont(opt.font)
        if secondary.pixelSize() > 0:
            secondary.setPixelSize(max(1, round(secondary.pixelSize() * .9)))
        else:
            secondary.setPointSizeF(secondary.pointSizeF() * .9)
        fonts = (primary, secondary)
        metrics = [QFontMetrics(font, painter.device()) for font in fonts[:len(lines)]]
        top = opt.rect.center().y() - sum(font.height() for font in metrics) // 2 + 1
        for number, (line, font_metrics) in enumerate(zip(lines, metrics)):
            painter.setFont(fonts[number])
            if column == STATE_COLUMN:
                color = colors.warning if line in {"文件缺失", "无法访问", "媒体异常"} else colors.muted
            elif column == DIRECTORY_COLUMN or number:
                color = colors.muted
            else:
                color = colors.text
            painter.setPen(QColor(color))
            elision = Qt.ElideLeft if column == DIRECTORY_COLUMN else Qt.ElideRight
            label = font_metrics.elidedText(line, elision, max(0, opt.rect.right() - x - 9))
            painter.drawText(x, top + font_metrics.ascent(), label)
            top += font_metrics.height()
        painter.restore()


class _GridDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.cover_painter = _CoverPainter(30)

    def sizeHint(self, option, index):
        return self.view.gridSize()

    @staticmethod
    def _cover(rect):
        card = rect.adjusted(8, 6, -8, -6)
        width = card.width() - 8
        return QRect(card.left() + 4, card.top() + 4, width, width * 9 // 16)

    @classmethod
    def check_rect(cls, rect):
        return QRect(cls._cover(rect).topLeft() + QPoint(8, 8), QSize(25, 25))

    def paint(self, painter, option, index):
        view = self.view
        record = index.model().records[index.row()]
        colors = palette(view)
        checked = record.id in index.model().binding.state.selected
        hovered = bool(option.state & QStyle.State_MouseOver)
        focused = view.currentIndex() == index
        card = QRectF(option.rect.adjusted(8, 6, -8, -6))
        cover = self._cover(option.rect)
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        painter.setPen(QPen(QColor(colors.focus if focused else colors.accent if checked else
                                   colors.border_hover if hovered else colors.card_border),
                            2 if focused and view.hasFocus() else 1))
        painter.setBrush(QColor(colors.selection if checked else colors.surface_raised if hovered else colors.surface))
        painter.drawRoundedRect(card, 8, 8)
        audio, image = view.thumbnail_for(record.id)
        self.cover_painter.paint(painter, cover, audio, image, colors)
        check_rect = self.check_rect(option.rect)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors.surface))
        painter.drawRoundedRect(QRectF(check_rect), 5, 5)
        indicator = QRect(QPoint(), QSize(16, 16))
        indicator.moveCenter(check_rect.center())
        draw_check_indicator(painter, indicator, checked=checked, hovered=hovered)

        title_font = QFont(option.font)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(colors.text))
        text_rect = option.rect.adjusted(18, cover.bottom() - option.rect.top() + 4, -18, -6)
        self._paint_title(painter, text_rect, record.title)
        painter.setFont(option.font)
        metrics = painter.fontMetrics()
        caption = " · ".join(filter(None, (record.author, record.kind, record.codec)))
        painter.setPen(QColor(colors.muted))
        painter.drawText(text_rect.left(), text_rect.bottom() - metrics.height() - 2,
                         metrics.elidedText(caption, Qt.ElideRight, text_rect.width()))
        if record.media.get("state") in _BLOCKING_STATES or record.state == "媒体异常":
            painter.setPen(QColor(colors.warning))
            painter.drawText(text_rect.left(), text_rect.bottom() - 1, record.state)
        painter.restore()

    @staticmethod
    def _paint_title(painter, rect, title):
        title = " ".join(title.split())
        layout = QTextLayout(title, painter.font(), painter.device())
        wrap = QTextOption()
        wrap.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(wrap)
        layout.beginLayout()
        first = layout.createLine()
        if first.isValid():
            first.setLineWidth(rect.width())
        layout.endLayout()
        if first.isValid():
            first.draw(painter, rect.topLeft())
            # QTextLine reports positions in UTF-16 code units.
            remaining = title.encode("utf-16-le")[2 * first.textLength():].decode("utf-16-le").lstrip()
            if remaining:
                metrics = painter.fontMetrics()
                painter.drawText(rect.left(), rect.top() + metrics.height() + metrics.ascent(),
                                 metrics.elidedText(remaining, Qt.ElideRight, rect.width()))

    def editorEvent(self, event, model, option, index):
        if (event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton
                and self.check_rect(option.rect).contains(event.position().toPoint())):
            value = Qt.Unchecked if index.data(Qt.CheckStateRole) == Qt.Checked else Qt.Checked
            return model.setData(index, value, Qt.CheckStateRole)
        return False


class LibraryGrid(QListView):
    def __init__(self, binding, thumbnail_for, parent=None):
        super().__init__(parent)
        self.thumbnail_for = thumbnail_for
        self.setAccessibleName("下载文件网格")
        self.setModel(_GridModel(binding, self))
        self.setItemDelegate(_GridDelegate(self))
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setProperty("readingView", True)
        self._surface = ScrollAreaSurface(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Allow for Qt's internal icon-view margin at the row boundary.
        width = max(1, self.viewport().width() - 10)
        cell = width // max(1, width // 216)
        height = max(0, cell - 24) * 9 // 16 + 4 * self.fontMetrics().height() + 19
        self.setGridSize(QSize(cell, height))

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and self.itemDelegate().check_rect(self.visualRect(index)).contains(event.position().toPoint()):
            return
        super().mouseDoubleClickEvent(event)


def handle_browse_key(view, event, select_all, open_file):
    if event.matches(QKeySequence.SelectAll):
        select_all()
        return True
    index = view.currentIndex()
    if not index.isValid():
        return False
    if event.key() in (Qt.Key_Return, Qt.Key_Enter):
        if index.siblingAtColumn(0).data(Qt.UserRole) is not None:
            open_file()
        return True
    if event.key() == Qt.Key_Space and not hasattr(view, "_selection_binding"):
        value = Qt.Unchecked if index.data(Qt.CheckStateRole) == Qt.Checked else Qt.Checked
        return index.model().setData(index, value, Qt.CheckStateRole)
    return False
