"""Store page: catalog browsing, source tabs, featured section, search, filters and direct downloads."""
from __future__ import annotations

import webbrowser
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QMessageBox, QPushButton, QScrollArea,
                               QStackedWidget, QStyle, QStyledItemDelegate, QTabBar,
                               QVBoxLayout, QWidget)

from Core.logger import get_logger
from Core.sources import CatalogItem, SearchPage
from .common import (draw_badge, draw_pixmap_cover, fmt_size, paint_placeholder,
                     rounded_path, run_async, theme_color)
from . import theme

log = get_logger(__name__)
ItemRole = Qt.UserRole + 1


class StoreCardDelegate(QStyledItemDelegate):
    CARD_W = 180
    COVER_H = 240
    PAD = 8
    TEXT_H = 46

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def sizeHint(self, option, index):
        return QSize(self.CARD_W + self.PAD * 2, self.COVER_H + self.TEXT_H + self.PAD * 2)

    def cover_rect(self, r: QRect) -> QRect:
        return QRect(r.x() + self.PAD, r.y() + self.PAD, self.CARD_W, self.COVER_H)

    def button_rect(self, r: QRect) -> QRect:
        return QRect()

    def paint(self, p: QPainter, option, index):
        item: CatalogItem = index.data(ItemRole)
        if not item:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        hover = bool(option.state & QStyle.State_MouseOver)
        cover = self.cover_rect(option.rect)
        if hover:
            cover = cover.adjusted(-2, -3, 2, 1)
        cr = theme.card_radius()
        path = rounded_path(cover, cr)

        # Draw cover art
        p.save()
        p.setClipPath(path)
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pm = self.ctx.images.get(item.cover_url or "", QSize(int(self.CARD_W * dpr), int(self.COVER_H * dpr)))
        if pm is not None:
            draw_pixmap_cover(p, cover, pm)
        else:
            paint_placeholder(p, cover, item.title)
        p.restore()

        # Border
        p.setPen(QPen(theme_color("accent") if hover else theme_color("border"), 2 if hover else 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Source badge
        src_color = self.ctx.sources.badge_color(item.source)
        src_name = self.ctx.sources.display_name(item.source)
        draw_badge(p, QPoint(cover.x() + 8, cover.y() + 8), src_name, src_color, 10)

        # Size badge if available
        if item.size_bytes:
            sz_str = fmt_size(item.size_bytes)
            f = QFont(p.font())
            f.setPixelSize(10)
            f.setBold(True)
            p.setFont(f)
            w = p.fontMetrics().horizontalAdvance(sz_str) + 10
            r_sz = QRect(cover.right() - w - 6, cover.y() + 8, w, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 180))
            p.drawRoundedRect(r_sz, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(r_sz, Qt.AlignCenter, sz_str)

        # Title text
        tr = QRect(option.rect.x() + self.PAD, cover.bottom() + 6, self.CARD_W, 20)
        f = QFont(p.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(theme_color("text"))
        title_elided = p.fontMetrics().elidedText(item.title, Qt.ElideRight, tr.width())
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, title_elided)

        # Description / genre text
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(theme_color("muted"))
        desc_text = item.short_description or (", ".join(item.genres) if item.genres else "")
        mr = QRect(option.rect.x() + self.PAD, tr.bottom() + 2, self.CARD_W, 16)
        desc_elided = p.fontMetrics().elidedText(desc_text, Qt.ElideRight, mr.width())
        p.drawText(mr, Qt.AlignLeft | Qt.AlignVCenter, desc_elided)

        p.restore()


class StoreListView(QListView):
    card_clicked = Signal(object)      # CatalogItem
    button_clicked = Signal(object)    # CatalogItem

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.viewport().setCursor(Qt.PointingHandCursor)
        self.setSelectionMode(QListView.NoSelection)
        self.setEditTriggers(QListView.NoEditTriggers)
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(30)
        self.setItemDelegate(StoreCardDelegate(ctx, self))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                item = idx.data(ItemRole)
                self.card_clicked.emit(item)
                e.accept()
                return
        super().mouseReleaseEvent(e)


from PySide6.QtCore import QAbstractListModel, QModelIndex

class StoreModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[CatalogItem] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == ItemRole:
            return item
        if role == Qt.DisplayRole:
            return item.title
        return None

    def set_items(self, items: list[CatalogItem]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()


ALL_SOURCES_ID = "all"


class StoreView(QWidget):
    open_detail = Signal(object)  # CatalogItem

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self.current_page = 1
        self.page_size = 24
        self.current_source_id = ctx.config.get("default_source", ALL_SOURCES_ID)
        self.has_more = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 20, 12)
        root.setSpacing(14)

        # Header with Title and Search
        header = QHBoxLayout()
        title = QLabel("STORE")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("Search")
        self.search_box.setPlaceholderText("Search all games and sources…")
        self.search_box.setClearButtonEnabled(True)
        header.addWidget(self.search_box)
        root.addLayout(header)

        # Source Selection Tabs
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self._source_ids: list[str] = []
        root.addWidget(self.tabs)

        # Filter bar: Genre selector + Stats
        filter_bar = QHBoxLayout()
        self.genre_combo = QComboBox()
        self.genre_combo.setMinimumWidth(160)
        filter_bar.addWidget(QLabel("Category:"))
        filter_bar.addWidget(self.genre_combo)
        filter_bar.addStretch(1)

        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("Muted")
        filter_bar.addWidget(self.status_lbl)
        root.addLayout(filter_bar)

        # Content stack: List or Empty/Loading
        self.stack = QStackedWidget()

        self.store_model = StoreModel(self)
        self.store_view = StoreListView(ctx)
        self.store_view.setModel(self.store_model)
        self.store_view.card_clicked.connect(self._on_card_clicked)
        self.store_view.button_clicked.connect(self._on_button_clicked)

        self.empty_lbl = QLabel()
        self.empty_lbl.setObjectName("EmptyState")
        self.empty_lbl.setAlignment(Qt.AlignCenter)

        self.stack.addWidget(self.store_view)
        self.stack.addWidget(self.empty_lbl)
        root.addWidget(self.stack, 1)

        # Pagination bar
        pag_bar = QHBoxLayout()
        pag_bar.addStretch(1)
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self._prev_page)
        self.page_lbl = QLabel("Page 1")
        self.page_lbl.setObjectName("Muted")
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._next_page)
        pag_bar.addWidget(self.prev_btn)
        pag_bar.addWidget(self.page_lbl)
        pag_bar.addWidget(self.next_btn)
        pag_bar.addStretch(1)
        root.addLayout(pag_bar)

        # Timers and Connections
        self._search_timer = QTimer(self, singleShot=True, interval=250, timeout=self._do_search)
        self.search_box.textChanged.connect(lambda: self._search_timer.start())
        self.genre_combo.currentIndexChanged.connect(lambda: self._reset_and_search())
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Debounced viewport refresh on image load for 60 FPS performance
        self._viewport_debounce = QTimer(self, singleShot=True, interval=60, timeout=self._refresh_viewport)
        ctx.images.image_ready.connect(lambda _k: self._viewport_debounce.start() if self.isVisible() else None)
        ctx.downloads.task_updated.connect(lambda _tid: self._viewport_debounce.start() if self.isVisible() else None)
        ctx.library.changed.connect(lambda: self._viewport_debounce.start() if self.isVisible() else None)

        self.reload_sources()

    def _refresh_viewport(self) -> None:
        if self.isVisible():
            self.store_view.viewport().update()

    def reload_sources(self) -> None:
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        self._source_ids.clear()

        # Add "All Sources" tab first
        self.tabs.addTab("ALL SOURCES")
        self._source_ids.append(ALL_SOURCES_ID)

        all_sources = self.ctx.sources.all()
        target_idx = 0
        for i, src in enumerate(all_sources):
            self.tabs.addTab(src.name.upper())
            self._source_ids.append(src.id)
            if src.id == self.current_source_id:
                target_idx = i + 1

        if self.current_source_id == ALL_SOURCES_ID:
            target_idx = 0

        self.tabs.setCurrentIndex(target_idx if self._source_ids else -1)
        self.tabs.blockSignals(False)
        self._update_genres()
        self._reset_and_search()

    def _on_tab_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._source_ids):
            self.current_source_id = self._source_ids[idx]
            self._update_genres()
            self._reset_and_search()

    def _update_genres(self) -> None:
        self.genre_combo.blockSignals(True)
        self.genre_combo.clear()
        self.genre_combo.addItem("All Categories", "")
        if self.current_source_id == ALL_SOURCES_ID:
            genres_set: set[str] = set()
            for s in self.ctx.sources.all():
                for g in s.genres():
                    genres_set.add(g)
            for g in sorted(genres_set):
                self.genre_combo.addItem(g, g)
        else:
            src = self.ctx.sources.get(self.current_source_id)
            if src:
                for g in src.genres():
                    self.genre_combo.addItem(g, g)
        self.genre_combo.blockSignals(False)

    def _reset_and_search(self) -> None:
        self.current_page = 1
        self._do_search()

    def _prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._do_search()

    def _next_page(self) -> None:
        if self.has_more:
            self.current_page += 1
            self._do_search()

    def _do_search(self) -> None:
        query = self.search_box.text().strip()
        genre = self.genre_combo.currentData() or ""
        page = self.current_page

        self.status_lbl.setText("Loading catalog…")

        if self.current_source_id == ALL_SOURCES_ID:
            sources = self.ctx.sources.all()
            if not sources:
                self.store_model.set_items([])
                self.empty_lbl.setText("No sources configured.")
                self.stack.setCurrentWidget(self.empty_lbl)
                return

            def fetch():
                all_items: list[CatalogItem] = []
                any_more = False
                total_count = 0
                for s in sources:
                    try:
                        res = s.search(query=query, genre=genre, page=page, page_size=self.page_size)
                        if res.items:
                            all_items.extend(res.items)
                        if res.has_more:
                            any_more = True
                        if res.total > 0:
                            total_count += res.total
                    except Exception as exc:
                        log.warning("Search failed for source %s: %s", s.id, exc)

                # Interleave items across sources when browsing without query so discovery is varied
                if not query and len(sources) > 1:
                    by_src: dict[str, list[CatalogItem]] = {}
                    for it in all_items:
                        by_src.setdefault(it.source, []).append(it)
                    max_len = max(len(v) for v in by_src.values()) if by_src else 0
                    interleaved: list[CatalogItem] = []
                    for i in range(max_len):
                        for s_list in by_src.values():
                            if i < len(s_list):
                                interleaved.append(s_list[i])
                    all_items = interleaved

                return SearchPage(items=all_items, has_more=any_more, total=total_count if total_count > 0 else len(all_items))

            source_display_name = "All Sources"
        else:
            src = self.ctx.sources.get(self.current_source_id)
            if not src:
                self.store_model.set_items([])
                self.empty_lbl.setText("Selected source is unavailable.")
                self.stack.setCurrentWidget(self.empty_lbl)
                return

            def fetch():
                return src.search(query=query, genre=genre, page=page, page_size=self.page_size)

            source_display_name = src.name

        def on_done(result: SearchPage):
            self.has_more = result.has_more
            self.store_model.set_items(result.items)
            self.page_lbl.setText(f"Page {self.current_page}")
            self.prev_btn.setEnabled(self.current_page > 1)
            self.next_btn.setEnabled(self.has_more)
            total_text = f" ({result.total} total)" if result.total > 0 else ""
            self.status_lbl.setText(f"{len(result.items)} items shown{total_text}")

            if result.items:
                self.stack.setCurrentWidget(self.store_view)
            else:
                self.empty_lbl.setText(f"No games found in {source_display_name} matching your search.")
                self.stack.setCurrentWidget(self.empty_lbl)

        def on_error(err: str):
            self.status_lbl.setText("Error loading catalog")
            self.empty_lbl.setText(f"Failed to load catalog from {source_display_name}:\n\n{err}")
            self.stack.setCurrentWidget(self.empty_lbl)

        run_async(fetch, on_done, on_error, context=self)

    def _on_card_clicked(self, item: CatalogItem) -> None:
        self.open_detail.emit(item)

    def _on_button_clicked(self, item: CatalogItem) -> None:
        src = self.ctx.sources.get(item.source)
        if not src:
            return

        existing = self.ctx.library.find(item.source, item.id)
        if existing and existing.get("installed"):
            from .actions import launch_game
            launch_game(self.ctx, existing["id"], self)
            return

        if not src.can_download:
            # Browse-only source
            url = item.store_url
            if url:
                webbrowser.open(url)
                self.ctx.toast(f"Opening store page for {item.title}…")
            return

        # Open the detail view where user can review game, select download source, and install
        self.open_detail.emit(item)
