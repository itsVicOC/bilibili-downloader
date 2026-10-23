"""Selectable, theme-aware GitHub Markdown without a browser engine."""

import re
from urllib.parse import quote, urljoin

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextLength,
    QTextOption,
    QTextTable,
)
from PySide6.QtWidgets import QApplication, QTextBrowser

from bilibili_downloader.core.updater import REPOSITORY
from bilibili_downloader.gui.resources.styles import theme_palette


class ReleaseNotesBrowser(QTextBrowser):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.setObjectName("ReleaseNotes")
        self.setAccessibleName("更新内容")
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._markdown = release.notes.strip() or "此版本未提供更新说明。"
        self._source_base = f"https://github.com/{REPOSITORY}/blob/{quote(release.tag, safe='')}/"
        self._theme_key = None
        self._refresh_pending = False
        self.anchorClicked.connect(self._open_link)
        self._apply_theme()

    def loadResource(self, resource_type, name):
        # Release bodies are text. Images become explicit links/descriptions;
        # no network request or local-file read is made by the rich-text view.
        return None

    def _resolve(self, value):
        url = QUrl(value)
        return QUrl(urljoin(self._source_base, value)) if url.isRelative() else url

    def _open_link(self, url):
        if not url.path() and url.fragment() and url.isRelative():
            self.scrollToAnchor(url.fragment())
            return
        resolved = self._resolve(url.toString())
        if resolved.scheme().lower() in ("https", "http"):
            QDesktopServices.openUrl(resolved)

    def event(self, event):
        if hasattr(self, "_theme_key") and event.type() in (
            QEvent.StyleChange, QEvent.ApplicationPaletteChange, QEvent.FontChange,
        ) and not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(0, self, self._apply_theme)
        return super().event(event)

    def focusInEvent(self, event):
        self.setProperty("keyboardFocus", event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason))
        self.style().unpolish(self)
        self.style().polish(self)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.setProperty("keyboardFocus", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().focusOutEvent(event)

    def _apply_theme(self):
        self._refresh_pending = False
        app = QApplication.instance()
        dark, theme = bool(app.property("darkTheme")), app.property("colorTheme")
        key = dark, theme, self.font().toString()
        if self._theme_key == key:
            return
        self._theme_key = key
        p = theme_palette(dark, theme)
        selected = self.textCursor()
        anchor, position = selected.anchor(), selected.position()
        scroll = self.verticalScrollBar().value()
        document = self.document()
        document.setDefaultFont(self.font())
        document.setDocumentMargin(4)
        document.setMarkdown(self._markdown, QTextDocument.MarkdownDialectGitHub)
        self._replace_images()
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSizeF(self.font().pointSizeF() * .94)
        headings = {}
        block = document.begin()
        while block.isValid():
            cursor = QTextCursor(block)
            original = block.blockFormat()
            fmt = QTextBlockFormat(original)
            level = original.headingLevel()
            code = original.nonBreakableLines() or original.hasProperty(QTextFormat.BlockCodeFence)
            fmt.setNonBreakableLines(False)
            fmt.setTopMargin(16 if level and block.position() else 0)
            fmt.setBottomMargin(8)
            fmt.setLineHeight(140, QTextBlockFormat.ProportionalHeight.value)
            if original.property(QTextFormat.BlockQuoteLevel):
                fmt.setLeftMargin(16)
                fmt.setBackground(QColor(p.control_fill))
            if code:
                fmt.setBackground(QColor(p.control_fill))
                fmt.setLeftMargin(8)
                fmt.setRightMargin(8)
            cursor.setBlockFormat(fmt)
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    current = fragment.charFormat()
                    style = QTextCharFormat()
                    style.setForeground(QColor(p.active_text if current.anchorHref() else p.text))
                    families = current.fontFamilies() or []
                    if code or current.fontFixedPitch() or "monospace" in families:
                        style.setFontFamilies(mono.families())
                        style.setFontPointSize(mono.pointSizeF())
                        style.setBackground(QColor(p.control_fill))
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    cursor.mergeCharFormat(style)
                iterator += 1
            if level:
                cursor.select(QTextCursor.BlockUnderCursor)
                style = QTextCharFormat()
                style.setFontPointSize(self.font().pointSizeF() * {1: 1.6, 2: 1.35, 3: 1.18}.get(level, 1.05))
                style.setProperty(QTextFormat.FontSizeAdjustment, 0)
                style.setFontWeight(QFont.DemiBold)
                slug = re.sub(r"[^\w\s-]", "", block.text().lower()).strip().replace(" ", "-")
                duplicate = headings.get(slug, 0)
                headings[slug] = duplicate + 1
                style.setAnchor(True)
                style.setAnchorNames([f"{slug}-{duplicate}" if duplicate else slug])
                cursor.mergeCharFormat(style)
            block = block.next()
        self._style_tables(document.rootFrame(), p)
        selected.setPosition(min(anchor, document.characterCount() - 1))
        selected.setPosition(min(position, document.characterCount() - 1), QTextCursor.KeepAnchor)
        self.setTextCursor(selected)
        self.verticalScrollBar().setValue(scroll)

    def _replace_images(self):
        images = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    image = fragment.charFormat().toImageFormat()
                    images.append((fragment.position(), fragment.length(), image))
                iterator += 1
            block = block.next()
        for position, length, image in reversed(images):
            cursor = QTextCursor(self.document())
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            url = self._resolve(image.name())
            if url.scheme() in ("http", "https"):
                fmt.setAnchor(True)
                fmt.setAnchorHref(url.toString())
            description = image.property(QTextFormat.ImageAltText) or image.property(QTextFormat.ImageTitle) or "查看图片"
            cursor.insertText(str(description), fmt)

    def _style_tables(self, frame, palette):
        for child in frame.childFrames():
            if isinstance(child, QTextTable):
                fmt = child.format()
                fmt.setWidth(QTextLength(QTextLength.PercentageLength, 100))
                fmt.setColumnWidthConstraints([QTextLength(QTextLength.PercentageLength, 100 / child.columns())] * child.columns())
                fmt.setBorder(.5)
                fmt.setBorderBrush(QColor(palette.card_border))
                fmt.setCellSpacing(0)
                fmt.setCellPadding(8)
                fmt.setBackground(QColor(palette.surface))
                child.setFormat(fmt)
            self._style_tables(child, palette)
