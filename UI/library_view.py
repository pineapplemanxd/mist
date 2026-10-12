"""Library page: grid/list of games with search, sort, filters, recently played strip."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListView, QMenu, QPushButton,
                               QStackedWidget, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget)

from . import actions, theme
from .common import (draw_badge, draw_pixmap_cover, fmt_ago, fmt_playtime, fmt_size, paint_placeholder, rounded_path,
                     theme_color)

GameRole = Qt.UserRole + 1


class LibraryModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._games: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._games)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        g = self._games[index.row()]
        if role == GameRole:
            return g
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return g["title"]
        return None

    def set_games(self, games: list[dict]) -> None:
        self.beginResetModel()
        self._games = games
        self.endResetModel()

    def update_game(self, game: dict) -> None:
        for row, g in enumerate(self._games):
            if g["id"] == game["id"]:
                self._games[row] = game
                idx = self.index(row)
                self.dataChanged.emit(idx, idx)
                return


# ------------------------------------------------------------------- delegates

class GameTileDelegate(QStyledItemDelegate):
    """Portrait cover tile (grid & recently-played strip)."""

    PAD = 8
    TEXT_H = 50

    def __init__(self, ctx, cover_w: int = 168, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.cover_w = cover_w
        self.cover_h = int(cover_w * 1.5)

    def sizeHint(self, option, index):
        return QSize(self.cover_w + self.PAD * 2, self.cover_h + self.TEXT_H + self.PAD * 2)

    def cover_rect(self, r: QRect) -> QRect:
        return QRect(r.x() + self.PAD, r.y() + self.PAD, self.cover_w, self.cover_h)

    def play_rect(self, r: QRect) -> QRect:
        c = self.cover_rect(r)
        s = 52
        return QRect(c.center().x() - s // 2, c.bottom() - s - 14, s, s)

    def paint(self, p: QPainter, option, index):
        g = index.data(GameRole)
        if not g:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hover = bool(option.state & QStyle.State_MouseOver)
        cover = self.cover_rect(option.rect)
        if hover:
            cover = cover.adjusted(-2, -3, 2, 1)
        path = rounded_path(cover, theme.card_radius())

        p.save()
        p.setClipPath(path)
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pm = self.ctx.images.get(g.get("cover_url") or "", QSize(int(self.cover_w * dpr), int(self.cover_h * dpr)))
        if pm is not None:
            draw_pixmap_cover(p, cover, pm)
        else:
            paint_placeholder(p, cover, g["title"])
        if not g.get("installed"):
            p.fillRect(cover, QColor(0, 0, 0, 150))
        p.restore()

        # Border/hover glow
        p.setPen(QPen(theme_color("accent") if hover else theme_color("border"), 2 if hover else 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Badges
        src = g.get("source", "")
        draw_badge(p, QPoint(cover.x() + 8, cover.y() + 8), self.ctx.sources.display_name(src),
                   self.ctx.sources.badge_color(src), 10)
        if g.get("favorite"):
            f = QFont(p.font())
            f.setPixelSize(18)
            p.setFont(f)
            p.setPen(QColor("#fbbf24"))
            p.drawText(QRect(cover.right() - 30, cover.y() + 4, 26, 26), Qt.AlignCenter, "★")
        running = self.ctx.library.is_running(g["id"])
        if running:
            draw_badge(p, QPoint(cover.x() + 8, cover.bottom() - 26), "● Running", "#16a34a", 10)
        elif not g.get("installed"):
            draw_badge(p, QPoint(cover.x() + 8, cover.bottom() - 26), "Not installed", "#4b5563", 10)
        elif hover:
            pr = self.play_rect(option.rect)
            p.setPen(Qt.NoPen)
            p.setBrush(theme_color("accent"))
            p.drawEllipse(pr)
            p.setBrush(QColor("#ffffff"))
            cx, cy = pr.center().x() + 2, pr.center().y()
            from PySide6.QtGui import QPolygon
            p.drawPolygon(QPolygon([QPoint(cx - 7, cy - 10), QPoint(cx - 7, cy + 10), QPoint(cx + 10, cy)]))

        # Text
        tr = QRect(option.rect.x() + self.PAD, cover.bottom() + 8, self.cover_w, 20)
        f = QFont(p.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(theme_color("text"))
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(g["title"], Qt.ElideRight, tr.width()))
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(theme_color("muted"))
        meta = f"{fmt_playtime(g.get('playtime_seconds', 0))}  ·  {fmt_ago(g.get('last_played', 0))}"
        mr = tr.translated(0, 19)
        p.drawText(mr, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(meta, Qt.ElideRight, mr.width()))
        p.restore()


class GameRowDelegate(QStyledItemDelegate):
    """Compact row for list mode."""

    H = 72

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def sizeHint(self, option, index):
        return QSize(option.rect.width() or 800, self.H)

    def play_rect(self, r: QRect) -> QRect:
        return QRect(r.right() - 108, r.center().y() - 16, 92, 32)

    def paint(self, p: QPainter, option, index):
        g = index.data(GameRole)
        if not g:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = option.rect.adjusted(4, 3, -8, -3)
        hover = bool(option.state & QStyle.State_MouseOver)
        p.setPen(Qt.NoPen)
        p.setBrush(theme_color("surface2" if hover else "surface"))
        p.drawRoundedRect(r, 8, 8)

        cover = QRect(r.x() + 8, r.y() + 5, 40, 56)
        p.save()
        p.setClipPath(rounded_path(cover, 4))
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pm = self.ctx.images.get(g.get("cover_url") or "", QSize(int(80 * dpr), int(112 * dpr)))
        if pm is not None:
            draw_pixmap_cover(p, cover, pm)
        else:
            paint_placeholder(p, cover, g["title"], 14)
        p.restore()

        x = cover.right() + 14
        play = self.play_rect(option.rect)
        cols_w = 380
        title_w = max(120, play.left() - cols_w - x - 10)
        f = QFont(p.font())
        f.setPixelSize(14)
        f.setBold(True)
        p.setFont(f)
        p.setPen(theme_color("text" if g.get("installed") else "muted"))
        title_rect = QRect(x, r.y() + 12, title_w, 22)
        title = p.fontMetrics().elidedText(g["title"], Qt.ElideRight, title_w)
        p.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)
        star = " ★" if g.get("favorite") else ""
        src = g.get("source", "")
        b = draw_badge(p, QPoint(x, r.y() + 38), self.ctx.sources.display_name(src), self.ctx.sources.badge_color(src), 10)
        f.setBold(False)
        f.setPixelSize(12)
        p.setFont(f)
        if star:
            p.setPen(QColor("#fbbf24"))
            p.drawText(QRect(b.right() + 6, b.y(), 20, b.height()), Qt.AlignVCenter, "★")

        p.setPen(theme_color("muted"))
        cx = play.left() - cols_w
        for w, label, value in ((130, "Playtime", fmt_playtime(g.get("playtime_seconds", 0))),
                                (140, "Last played", fmt_ago(g.get("last_played", 0))),
                                (100, "Size", fmt_size(g.get("size_bytes", 0)))):
            p.setPen(theme_color("muted"))
            p.drawText(QRect(cx, r.y() + 12, w, 18), Qt.AlignLeft, label)
            p.setPen(theme_color("text"))
            p.drawText(QRect(cx, r.y() + 34, w, 20), Qt.AlignLeft, value)
            cx += w + 5

        if self.ctx.library.is_running(g["id"]):
            draw_badge(p, QPoint(play.x() + 4, play.y() + 6), "● Running", "#16a34a", 11)
        elif g.get("installed"):
            p.setPen(Qt.NoPen)
            p.setBrush(theme_color("success"))
            p.drawRoundedRect(play, 7, 7)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(play, Qt.AlignCenter, "▶  Play")
        else:
            p.setPen(theme_color("muted"))
            p.drawText(play, Qt.AlignCenter, "Not installed")
        p.restore()


class GameView(QListView):
    play_requested = Signal(int)
    open_requested = Signal(int)
    menu_requested = Signal(int, QPoint)

    def __init__(self, ctx, mode: str = "grid", parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.viewport().setCursor(Qt.PointingHandCursor)
        self.setSelectionMode(QListView.NoSelection)
        self.setEditTriggers(QListView.NoEditTriggers)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setHorizontalScrollMode(QListView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setUniformItemSizes(True)
        self._tile = GameTileDelegate(ctx, 168, self)
        self._strip_tile = GameTileDelegate(ctx, 124, self)
        self._row = GameRowDelegate(ctx, self)
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == "list":
            self.setViewMode(QListView.ListMode)
            self.setFlow(QListView.TopToBottom)
            self.setWrapping(False)
            self.setItemDelegate(self._row)
            self.setSpacing(0)
            self.setGridSize(QSize())
        else:
            delegate = self._strip_tile if mode == "strip" else self._tile
            self.setItemDelegate(delegate)
            self.setViewMode(QListView.IconMode)
            self.setMovement(QListView.Static)
            self.setResizeMode(QListView.Adjust)
            self.setSpacing(4)
            if mode == "strip":
                self.setFlow(QListView.LeftToRight)
                self.setWrapping(False)
                self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            else:
                self.setFlow(QListView.LeftToRight)
                self.setWrapping(True)
        self.scheduleDelayedItemsLayout()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                g = idx.data(GameRole)
                rect = self.visualRect(idx)
                if (g.get("installed") and not self.ctx.library.is_running(g["id"])
                        and self.itemDelegate().play_rect(rect).contains(e.position().toPoint())):
                    self.play_requested.emit(g["id"])
                else:
                    self.open_requested.emit(g["id"])
                e.accept()
                return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        idx = self.indexAt(e.pos())
        if idx.isValid():
            self.menu_requested.emit(idx.data(GameRole)["id"], e.globalPos())

    def wheelEvent(self, e):
        if self.mode == "strip" and abs(e.angleDelta().y()) > abs(e.angleDelta().x()):
            sb = self.horizontalScrollBar()
            sb.setValue(sb.value() - e.angleDelta().y())
            e.accept()
            return
        super().wheelEvent(e)


# ------------------------------------------------------------------------ page

SORTS = {
    "name": ("Name", lambda g: g["title"].lower(), False),
    "recent": ("Recently played", lambda g: g.get("last_played") or 0, True),
    "playtime": ("Playtime", lambda g: g.get("playtime_seconds") or 0, True),
    "source": ("Source", lambda g: (g.get("source", ""), g["title"].lower()), False),
    "size": ("Install size", lambda g: g.get("size_bytes") or 0, True),
    "added": ("Recently added", lambda g: g.get("added_at") or 0, True),
}


class LibraryView(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self._filter = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 20, 8)
        root.setSpacing(12)

        # Header ----------------------------------------------------------------
        header = QHBoxLayout()
        title = QLabel("LIBRARY")
        title.setObjectName("PageTitle")
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("Muted")
        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self.count_lbl, 0, Qt.AlignBottom)
        header.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search library…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        header.addWidget(self.search)
        add_btn = QPushButton("+ Add game")
        add_btn.setToolTip("Add a game manually by selecting its executable")
        add_btn.clicked.connect(lambda: actions.add_game_manually(self.ctx, self))
        header.addWidget(add_btn)
        root.addLayout(header)

        # Filters ----------------------------------------------------------------
        bar = QHBoxLayout()
        self.pills = QButtonGroup(self)
        self.pills.setExclusive(True)
        for key, label in (("all", "All games"), ("favorites", "★ Favorites"), ("installed", "Installed"),
                           ("recent", "Recently played")):
            b = QPushButton(label)
            b.setObjectName("Pill")
            b.setCheckable(True)
            b.setProperty("key", key)
            b.setChecked(key == "all")
            self.pills.addButton(b)
            bar.addWidget(b)
        self.pills.buttonClicked.connect(self._on_pill)
        bar.addStretch(1)
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(140)
        bar.addWidget(self.source_combo)
        self.sort_combo = QComboBox()
        for key, (label, _, _) in SORTS.items():
            self.sort_combo.addItem(f"Sort: {label}", key)
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(ctx.config.get("library_sort", "name"))))
        bar.addWidget(self.sort_combo)
        self.grid_btn = QToolButton(text="▦ Grid", checkable=True)
        self.list_btn = QToolButton(text="☰ List", checkable=True)
        vg = QButtonGroup(self)
        vg.addButton(self.grid_btn)
        vg.addButton(self.list_btn)
        bar.addWidget(self.grid_btn)
        bar.addWidget(self.list_btn)
        root.addLayout(bar)

        # Recently played strip ----------------------------------------------------
        self.recent_box = QWidget()
        rl = QVBoxLayout(self.recent_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        sec = QLabel("Recently Played")
        sec.setObjectName("SectionTitle")
        rl.addWidget(sec)
        self.recent_model = LibraryModel(self)
        self.recent_view = GameView(ctx, "strip")
        self.recent_view.setModel(self.recent_model)
        self.recent_view.setFixedHeight(124 * 3 // 2 + 50 + 16 + 14)
        rl.addWidget(self.recent_view)
        root.addWidget(self.recent_box)

        self.all_lbl = QLabel("All Games")
        self.all_lbl.setObjectName("SectionTitle")
        root.addWidget(self.all_lbl)

        # Main view -----------------------------------------------------------------
        self.stack = QStackedWidget()
        self.model = LibraryModel(self)
        self.view = GameView(ctx, ctx.config.get("library_view_mode", "grid"))
        self.view.setModel(self.model)
        self.empty = QLabel()
        self.empty.setObjectName("EmptyState")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.empty)
        root.addWidget(self.stack, 1)
        (self.list_btn if self.view.mode == "list" else self.grid_btn).setChecked(True)

        for v in (self.view, self.recent_view):
            v.play_requested.connect(lambda gid: actions.launch_game(self.ctx, gid, self))
            v.open_requested.connect(lambda gid: self.ctx.window.open_game(gid))
            v.menu_requested.connect(self._context_menu)

        # Signals -------------------------------------------------------------------
        self._refresh_timer = QTimer(self, singleShot=True, interval=60, timeout=self.refresh)
        self._paint_timer = QTimer(self, singleShot=True, interval=40, timeout=self._repaint)
        self.search.textChanged.connect(lambda: self._refresh_timer.start(120))
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        self.source_combo.currentIndexChanged.connect(lambda: self._refresh_timer.start())
        self.grid_btn.clicked.connect(lambda: self._set_mode("grid"))
        self.list_btn.clicked.connect(lambda: self._set_mode("list"))
        ctx.library.changed.connect(lambda: self._refresh_timer.start())
        ctx.library.game_updated.connect(self._on_game_updated)
        ctx.library.running_changed.connect(lambda *_: self._paint_timer.start())
        ctx.images.image_ready.connect(lambda _k: self._paint_timer.start() if self.isVisible() else None)

        find = QAction(self)
        find.setShortcut("Ctrl+F")
        find.triggered.connect(lambda: (self.search.setFocus(), self.search.selectAll()))
        self.addAction(find)
        self.refresh()

    # ------------------------------------------------------------------ logic
    def _on_pill(self, btn) -> None:
        self._filter = btn.property("key")
        self.refresh()

    def _on_sort(self) -> None:
        self.ctx.config.set("library_sort", self.sort_combo.currentData())
        self.refresh()

    def _set_mode(self, mode: str) -> None:
        self.view.set_mode(mode)
        self.ctx.config.set("library_view_mode", mode)

    def _repaint(self) -> None:
        self.view.viewport().update()
        self.recent_view.viewport().update()

    def _on_game_updated(self, gid: int) -> None:
        g = self.ctx.library.game(gid)
        if g:
            self.model.update_game(g)
            self.recent_model.update_game(g)
        if self._filter in ("favorites", "recent") or self.sort_combo.currentData() in ("recent", "playtime"):
            self._refresh_timer.start()
        else:
            self._update_recent(self.ctx.library.games())

    def _update_sources(self, games: list[dict]) -> None:
        current = self.source_combo.currentData()
        srcs = sorted({g["source"] for g in games})
        wanted = [None] + srcs
        have = [self.source_combo.itemData(i) for i in range(self.source_combo.count())]
        if wanted != have:
            self.source_combo.blockSignals(True)
            self.source_combo.clear()
            self.source_combo.addItem("All sources", None)
            for s in srcs:
                self.source_combo.addItem(self.ctx.sources.display_name(s), s)
            idx = self.source_combo.findData(current)
            self.source_combo.setCurrentIndex(max(0, idx))
            self.source_combo.blockSignals(False)

    def _update_recent(self, games: list[dict]) -> None:
        recent = sorted((g for g in games if g.get("last_played") and g.get("installed")),
                        key=lambda g: g["last_played"], reverse=True)[:12]
        show = bool(recent) and self._filter == "all" and not self.search.text().strip()
        if show:
            self.recent_model.set_games(recent)
        self.recent_box.setVisible(show)
        self.all_lbl.setVisible(show)

    def refresh(self) -> None:
        games = self.ctx.library.games()
        self._update_sources(games)
        q = self.search.text().strip().lower()
        src = self.source_combo.currentData()
        out = games
        if self._filter == "favorites":
            out = [g for g in out if g.get("favorite")]
        elif self._filter == "installed":
            out = [g for g in out if g.get("installed")]
        elif self._filter == "recent":
            out = [g for g in out if g.get("last_played")]
        if src:
            out = [g for g in out if g["source"] == src]
        if q:
            out = [g for g in out if q in g["title"].lower()]
        key = self.sort_combo.currentData() or "name"
        if self._filter == "recent":
            key = "recent"
        _, fn, rev = SORTS[key]
        out.sort(key=fn, reverse=rev)
        self.model.set_games(out)
        self._update_recent(games)
        installed = sum(1 for g in games if g.get("installed"))
        self.count_lbl.setText(f"{len(out)} shown · {installed} installed")
        if out:
            self.stack.setCurrentWidget(self.view)
        else:
            if not games:
                self.empty.setText("Your library is empty.\n\nBrowse the Store to install games, add one manually "
                                   "with “+ Add game”, or scan for Steam games in Settings.")
            else:
                self.empty.setText("No games match the current filters.")
            self.stack.setCurrentWidget(self.empty)

    def _context_menu(self, gid: int, pos) -> None:
        g = self.ctx.library.game(gid)
        if not g:
            return
        m = QMenu(self)
        a_play = m.addAction("▶  Play")
        a_play.setEnabled(bool(g.get("installed")) and not self.ctx.library.is_running(gid))
        a_open = m.addAction("Open details")
        m.addSeparator()
        a_fav = m.addAction("Remove from favorites" if g.get("favorite") else "★ Add to favorites")
        a_folder = m.addAction("Open install folder")
        a_folder.setEnabled(bool(g.get("install_dir")))
        a_exe = m.addAction("Set executable…")
        a_exe.setEnabled(g.get("source") != "steam")
        m.addSeparator()
        a_uninst = m.addAction("Uninstall…") if actions.can_uninstall(g) else None
        a_remove = m.addAction("Remove from library")
        chosen = m.exec(pos)
        if chosen is None:
            return
        if chosen == a_play:
            actions.launch_game(self.ctx, gid, self)
        elif chosen == a_open:
            self.ctx.window.open_game(gid)
        elif chosen == a_fav:
            actions.toggle_favorite(self.ctx, gid)
        elif chosen == a_folder:
            actions.open_folder(g.get("install_dir", ""), self)
        elif chosen == a_exe:
            actions.pick_executable(self.ctx, gid, self)
        elif a_uninst is not None and chosen == a_uninst:
            actions.uninstall_game(self.ctx, gid, self)
        elif chosen == a_remove:
            actions.remove_from_library(self.ctx, gid, self)
