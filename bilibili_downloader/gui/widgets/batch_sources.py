"""Account-scoped source cards for the batch import editor."""

from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.batch import batch_source_key
from bilibili_downloader.core.batch_discovery import (
    MAX_COLLECTION_FEED_PAGES,
    BatchSource,
    load_batch_cover,
    load_batch_sources,
)
from bilibili_downloader.gui.widgets.components import (
    ElidedLabel,
    WorkspaceTabBar,
    scroll_area,
)
from bilibili_downloader.gui.widgets.discovery_cards import (
    DiscoveryCard,
    DiscoveryJob,
    ProgressiveDiscoveryGrid,
)


@dataclass
class _SourceList:
    sources: dict[str, BatchSource] = field(default_factory=dict)
    pages: int = 0
    next_offset: str = ""
    offsets: set[str] = field(default_factory=set)
    notice: str = ""
    error: str = ""
    failed_offset: str = ""
    page_keys: set[tuple[str, ...]] = field(default_factory=set)
    query: str = ""
    search_paused: bool = False
    paging_incomplete: bool = False


class BatchSourcesWidget(QWidget):
    source_requested = Signal(object)
    preview_requested = Signal(object)
    login_requested = Signal()
    account_check_requested = Signal()
    account_changed = Signal()

    def __init__(self, pool, thumbnails):
        super().__init__()
        self.setObjectName("BatchSourceDiscovery")
        self._pool = pool
        self._account = None
        self._mid = None
        self._expired = False
        self._loading_enabled = False
        self._request = None
        self._request_offset = ""
        self._lists = {}
        self._creator = None
        self._following_scroll = (None, 0)
        self._browse_position = (None, 0)
        self._selected_keys = set()
        self._search_key = None
        self._cover_cache = {}
        self._cover_requests = {}
        self._cover_limited = False
        self._view_generation = 0
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._link_editor = None

        layout = QVBoxLayout(self)
        self._source_layout = layout
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(6)
        header = QHBoxLayout()
        self.tabs = WorkspaceTabBar()
        self.tabs.setAccessibleName("切换批量导入来源")
        self._links_tab = self.tabs.addTab("粘贴链接")
        self.tabs.setTabData(self._links_tab, "links")
        self.tabs.setTabData(self.tabs.addTab("我的收藏夹"), "favorites")
        self.tabs.setTabData(self.tabs.addTab("找合集"), "collections")
        header.addWidget(self.tabs)
        header.addStretch(1)
        self.refresh = QPushButton("刷新")
        self.refresh.setObjectName("DiscoveryHeaderAction")
        self.refresh.clicked.connect(self._refresh)
        self.login = QPushButton("登录 B 站")
        self.login.setObjectName("SubtleButton")
        self.login.clicked.connect(self.login_requested.emit)
        header.addWidget(self.login)
        layout.addLayout(header)

        self.collection_tabs = WorkspaceTabBar()
        self.collection_tabs.setAccessibleName("合集查找方式")
        self.collection_tabs.setTabData(self.collection_tabs.addTab("最近动态"), "collections")
        self.collection_tabs.setTabData(self.collection_tabs.addTab("按 UP 主"), "following")
        layout.addWidget(self.collection_tabs, 0, Qt.AlignLeft)

        self.creator_bar = QWidget()
        creator_row = QHBoxLayout(self.creator_bar)
        creator_row.setContentsMargins(0, 0, 0, 0)
        self.back = QPushButton("返回关注列表")
        self.back.setObjectName("DiscoveryHeaderAction")
        self.back.clicked.connect(self._return_to_following)
        creator_row.addWidget(self.back)
        self.creator_name = ElidedLabel()
        self.creator_name.setTextFormat(Qt.PlainText)
        self.creator_name.setObjectName("SectionTitle")
        creator_row.addWidget(self.creator_name, 1)
        layout.addWidget(self.creator_bar)

        self.search_bar = QWidget()
        search_row = QHBoxLayout(self.search_bar)
        search_row.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_changed)
        self.search.returnPressed.connect(self._start_search)
        search_row.addWidget(self.search, 1)
        self.search_action = QPushButton("搜索")
        self.search_action.setObjectName("DiscoveryHeaderAction")
        self.search_action.clicked.connect(self._search_clicked)
        search_row.addWidget(self.search_action)
        search_row.addWidget(self.refresh)
        layout.addWidget(self.search_bar)

        self.status = QLabel()
        self.status.setObjectName("MetaLabel")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.grid = ProgressiveDiscoveryGrid(
            thumbnails, images_for=self._images_for, prefetch_next_row=True, compact=True,
        )
        self.grid.action_requested.connect(self._activate)
        self.grid.secondary_action_requested.connect(self._preview)
        self.grid.next_page_requested.connect(self._next_page)
        self.grid.viewport_changed.connect(self._load_if_needed)
        self.grid.cover_missing.connect(self._request_cover)
        results = QWidget()
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(self.grid)
        results_layout.addStretch()
        self._scroll = scroll_area(results)
        self._scroll.setMinimumHeight(0)
        self._scroll.setAccessibleName("批量导入来源列表")
        self.grid.set_scroll_area(self._scroll)
        layout.addWidget(self._scroll, 1)
        self.tabs.currentChanged.connect(self._change_tab)
        self.collection_tabs.currentChanged.connect(self._change_tab)
        self._present()

    def set_link_editor(self, editor):
        self._link_editor = editor
        self._source_layout.addWidget(editor, 1)
        self._present()

    def set_loading_enabled(self, enabled):
        self._loading_enabled = enabled
        if not enabled:
            self._cancel()
        self._present()
        self._load_if_needed()

    def set_account(self, account, *, mid=None, expired=False):
        if isinstance(mid, str) and mid.isascii() and mid.isdigit() and len(mid) <= 20:
            mid = int(mid)
        mid = mid if type(mid) is int and mid > 0 else None
        if account is self._account and mid == self._mid and expired == self._expired:
            return
        self._cancel()
        self._account, self._mid, self._expired = account, mid, expired
        self._lists.clear()
        self._creator = None
        self._following_scroll = (None, 0)
        self._browse_position = (None, 0)
        self._cover_cache.clear()
        self._cover_limited = False
        self._present(reset_grid=True)
        self._load_if_needed()
        self.account_changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_if_needed()

    def hideEvent(self, event):
        self._cancel()
        self._present()
        super().hideEvent(event)

    def _cancel(self):
        self._view_generation += 1
        self._pause_search()
        if self._request is not None:
            self._request.set()
            self._request = None

    def _kind(self):
        tab = self.tabs.tabData(self.tabs.currentIndex())
        if tab == "collections":
            tab = self.collection_tabs.tabData(self.collection_tabs.currentIndex())
        return "space" if tab == "following" and self._creator is not None else tab

    @property
    def editing_links(self):
        return self._kind() == "links"

    def show_link_editor(self):
        self.tabs.setCurrentIndex(self._links_tab)

    def set_selected_sources(self, sources):
        keys = {batch_source_key(source) for source in sources}
        if keys != self._selected_keys:
            self._selected_keys = keys
            self._present()

    def known_source_titles(self, sources):
        keys = {batch_source_key(source) for source in sources}
        return {
            key: source.title
            for (kind, _), state in self._lists.items() if kind in ("favorites", "collections", "space")
            for source in state.sources.values()
            if (key := batch_source_key(source.url)) in keys
        }

    def _list_key(self):
        kind = self._kind()
        return (kind, self._creator.owner_mid) if kind == "space" else (kind, None)

    def _current(self):
        return self._lists.setdefault(self._list_key(), _SourceList())

    def _change_tab(self):
        self._cancel()
        self._scroll.verticalScrollBar().setValue(0)
        self._present(reset_grid=True)
        self._load_if_needed()

    def _load_if_needed(self):
        state = self._current()
        if not self.editing_links and not state.pages and not state.error and not state.search_paused:
            self._fetch("")

    def _refresh(self):
        if self._account is not None and self._mid is None:
            self.account_check_requested.emit()
            return
        self._cover_limited = False
        self._cover_cache = {key: images for key, images in self._cover_cache.items() if images}
        state = self._current()
        if state.query.strip() and state.error:
            self._start_search()
            return
        self._fetch(state.failed_offset if state.error else "")
        self.grid.refresh_images()

    def _next_page(self):
        state = self._current()
        if state.next_offset and not state.error and not state.query.strip():
            self._fetch(state.next_offset)

    def _filter_changed(self, query):
        if self._search_key is not None:
            self._cancel()
        state = self._current()
        state.query, state.search_paused = query, False
        self._scroll.verticalScrollBar().setValue(0)
        self._present(reset_grid=True)
        self._load_if_needed()

    def _pause_search(self):
        if self._search_key is not None:
            self._lists[self._search_key].search_paused = True
            self._search_key = None

    def _can_search_more(self, state):
        return bool(not state.pages or state.next_offset or state.error or state.paging_incomplete)

    def _start_search(self):
        state = self._current()
        if (not self._loading_enabled or not self.isVisible() or self._search_key is not None
                or self._account is None or self._mid is None
                or self.editing_links or not state.query.strip() or not self._can_search_more(state)):
            return
        self._search_key = self._list_key()
        state.search_paused = False
        if self._request is None:
            self._fetch(state.failed_offset if state.error else state.next_offset)
        self._present()

    def _search_clicked(self):
        if self._search_key is not None:
            self._cancel()
            self._present()
        else:
            self._start_search()

    def _fetch(self, offset):
        if (not self._loading_enabled or not self.isVisible() or self.editing_links or self._account is None
                or self._mid is None or self._expired or self._request is not None):
            return
        kind, mid = self._kind(), self._mid
        cookies = self._account.auth_cookies
        request = self._request = Event()
        self._request_offset = offset
        options = {"creator": self._creator} if kind == "space" else {}
        job = DiscoveryJob(kind, request, lambda: load_batch_sources(cookies, mid, kind, offset, request, **options))
        job.signals.finished.connect(self._finished, Qt.QueuedConnection)
        self._present()
        self._pool.start(job)

    @Slot(str, object, object)
    def _finished(self, kind, request, page):
        if request is not self._request:
            return
        self._request = None
        offset = self._request_offset
        if page.login_required:
            self.set_account(None, expired=True)
            return
        key = self._list_key()
        state = self._lists[key]
        restarting_search = not offset and state.pages > 0 and self._search_key == key
        if page.error:
            state.error = page.error
            state.failed_offset = offset
            self._search_key = None
        else:
            if not offset:
                state = self._lists[key] = _SourceList(
                    sources=state.sources if restarting_search else {},
                    query=state.query, search_paused=state.search_paused,
                )
            for source in page.sources:
                previous = state.sources.get(source.url)
                if previous is None or source.updated_at > previous.updated_at:
                    state.sources[source.url] = source
            state.pages += 1
            state.error = ""
            if page.notice and page.notice not in state.notice:
                state.notice += page.notice
            state.paging_incomplete = page.paging_incomplete
            state.next_offset = page.next_offset
            if (state.next_offset and state.next_offset in state.offsets) or (
                page.page_key and page.page_key in state.page_keys
            ):
                notice = "动态分页已中断。" if kind == "collections" else "列表分页已中断。"
                state.notice = f"{state.notice}{notice}"
                state.next_offset = ""
                state.paging_incomplete = True
            if page.page_key:
                state.page_keys.add(page.page_key)
            if kind == "collections" and state.pages >= MAX_COLLECTION_FEED_PAGES:
                state.next_offset = ""
            if state.next_offset:
                state.offsets.add(state.next_offset)
            elif self._search_key is not None:
                self._search_key = None
        self._present(reset_grid=not offset and not restarting_search and not page.error)
        if self._search_key is not None:
            QTimer.singleShot(0, self, self._continue_search)

    def _continue_search(self):
        if self._search_key == self._list_key() and self._current().next_offset:
            self._fetch(self._current().next_offset)

    def _present(self, *, reset_grid=False, visible_count=None):
        state = self._current()
        kind = self._kind()
        author_list = kind == "following"
        browsing = kind != "links"
        self.collection_tabs.setVisible(kind in ("collections", "following"))
        self.creator_bar.setVisible(kind == "space")
        if kind == "space":
            self.creator_name.set_full_text(self._creator.title)
        login = self._account is None or self._expired
        self.login.setVisible(browsing and login)
        self.refresh.setVisible(browsing and not login and not (state.query.strip() and state.error))
        self.refresh.setEnabled(self._request is None)
        self.refresh.setText("检查账号" if self._mid is None else "重试" if state.error else "刷新")
        self.search_bar.setVisible(browsing and not login)
        self.search.setVisible(self._mid is not None)
        self._scroll.setVisible(browsing)
        if self._link_editor is not None:
            self._link_editor.setVisible(not browsing)
        if self.search.text() != state.query:
            with QSignalBlocker(self.search):
                self.search.setText(state.query)
        hint = {"favorites": "筛选收藏夹", "collections": "搜索近期合集或 UP 主",
                "following": "搜索昵称或 UID", "space": "搜索此 UP 主的合集"}.get(kind, "")
        self.search.setPlaceholderText(hint)
        self.search.setAccessibleName(hint)
        searching = self._search_key is not None
        query = state.query.strip().casefold()
        self.search_action.setText("停止搜索" if searching else "重试搜索" if state.error or state.paging_incomplete
                                   else "继续搜索" if state.search_paused else "搜索更多")
        self.search_action.setVisible(bool(self._mid is not None and (searching or self._can_search_more(state))))
        self.search_action.setEnabled(searching or bool(query))

        message = state.error or state.notice
        if self._request is not None and not state.sources:
            message = "正在读取来源…"
        elif login:
            message = "B 站登录已失效，请重新登录。" if self._expired else "登录 B 站后查看来源。"
        elif self._mid is None:
            message = "等待账号验证。"
        elif state.pages and not state.sources and not message:
            message = {
                "favorites": "暂无收藏夹。",
                "collections": "已读取的关注动态中暂无可识别的合集。",
                "following": "暂无关注的 UP 主。",
                "space": "当前页暂无合集，可继续加载。" if state.next_offset else "该 UP 主暂无可查看的合集。",
            }[kind]
        elif self._cover_limited and not author_list and not message:
            message = "B 站暂时限制了封面请求，可稍后刷新。"
        sources = sorted(state.sources.values(), key=lambda source: source.updated_at, reverse=True)
        if browsing and not login and query:
            sources = [source for source in sources if (
                query in source.title.casefold()
                or (kind == "collections" and query in source.author.casefold())
                or (author_list and query in str(source.owner_mid))
            )]
            scope = {"favorites": "我的收藏夹", "collections": "最近 5 页动态",
                     "following": "关注作者", "space": "当前作者的合集"}[kind]
            if searching:
                search_state = "搜索中…"
            elif state.search_paused:
                search_state = "已停止，可继续搜索"
            elif state.error or state.paging_incomplete:
                search_state = "搜索未完成"
            elif self._can_search_more(state):
                search_state = "可按回车搜索更多"
            else:
                search_state = "已查完" if sources else "没有匹配结果"
            progress = f"{scope} · 已查 {state.pages} 页 · {len(sources)} 个匹配 · {search_state}"
            message = f"{message}\n{progress}" if message and (state.error or state.notice) else progress
        self.status.setText(message)
        self.status.setVisible(browsing and bool(message))

        self.grid.more.setEnabled(self._request is None)
        self.grid.more.setText("加载中…" if self._request is not None else "加载更多")
        self.grid.set_cards(
            (self._card(source, author_list) for source in sources), keep_limit=not reset_grid,
            has_next_page=bool(state.next_offset and not state.error and not query), visible_count=visible_count,
        )

    def _card(self, source, author_list):
        selected = not author_list and batch_source_key(source.url) in self._selected_keys
        details = [source.author] if source.author else []
        if source.count is not None:
            details.append(f"{source.count} 个作品")
        return DiscoveryCard(
            source.url, source.title, " · ".join(details),
            tuple(filter(None, (source.cover, source.first_video_cover))),
            action="查看合集" if author_list else "已加入" if selected else "加入待解析",
            enabled=not selected, secondary_action="" if author_list else "预览",
        )

    def _activate(self, url):
        source = self._current().sources.get(url)
        if source is None:
            return
        if self._kind() != "following":
            self.source_requested.emit(source)
            return
        self._cancel()
        self._following_scroll = self._current_position()
        self._creator = source
        self._scroll.verticalScrollBar().setValue(0)
        self._present(reset_grid=True)
        self._load_if_needed()

    def _preview(self, url):
        if (source := self._current().sources.get(url)) is not None:
            self.preview_requested.emit(source)

    def _current_position(self):
        value = self._scroll.verticalScrollBar().value() if self._scroll is not None else 0
        return self.grid.materialized_count or None, value

    def remember_position(self):
        self._browse_position = self._current_position()

    def restore_position(self):
        self._restore_position(self._browse_position)

    def _return_to_following(self):
        self._cancel()
        self._creator = None
        self._restore_position(self._following_scroll)

    def _restore_position(self, position):
        count, value = position
        self._present(reset_grid=True, visible_count=count)
        generation = self._view_generation

        def restore():
            if generation == self._view_generation and self.isVisible():
                self.grid.restore_scroll(value)

        QTimer.singleShot(0, self, restore)

    def _images_for(self, card):
        return card.images + self._cover_cache.get(card.key, ())

    def _request_cover(self, url):
        if (not self._loading_enabled or self._account is None or self._cover_limited
                or len(self._cover_requests) >= 2 or url in self._cover_cache):
            return
        source = self._current().sources.get(url)
        if source is None or not source.resource_id or source.first_video_cover or source.count == 0:
            return
        generation = self._view_generation
        if (url, generation) in self._cover_requests.values():
            return
        request = Event()
        self._cover_requests[request] = (url, generation)
        cookies, favorite = self._account.auth_cookies, self._kind() == "favorites"

        def load():
            if generation == self._view_generation:
                return load_batch_cover(cookies, source, favorite=favorite)
            return None

        job = DiscoveryJob(url, request, load)
        job.signals.finished.connect(self._cover_finished, Qt.QueuedConnection)
        self._pool.start(job)

    @Slot(str, object, object)
    def _cover_finished(self, url, request, cover):
        _, generation = self._cover_requests.pop(request)
        if generation == self._view_generation and cover is not None:
            if cover.login_required:
                self.set_account(None, expired=True)
                return
            self._cover_cache[url] = cover.images
            if cover.limited:
                self._cover_limited = True
                self._present()
        self.grid.refresh_images()
