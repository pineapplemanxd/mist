"""Downloads page: active and queued downloads with speed, ETA, progress and controls."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from Core.downloader import ACTIVE, FINISHED, DownloadTask, Status
from . import actions
from .common import (draw_badge, fmt_eta, fmt_size, paint_placeholder,
                     theme_color)


class DownloadCard(QFrame):
    def __init__(self, ctx, task: DownloadTask, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.task_id = task.id
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Top row: Thumbnail, Title, Source badge, Status badge, Action buttons
        top = QHBoxLayout()
        top.setSpacing(14)

        self.thumb = QLabel()
        self.thumb.setFixedSize(48, 64)
        self.thumb.setObjectName("Card")
        self.thumb.setAlignment(Qt.AlignCenter)
        top.addWidget(self.thumb)

        info = QVBoxLayout()
        info.setSpacing(4)
        self.title_lbl = QLabel(task.item.title)
        f = self.title_lbl.font()
        f.setPixelSize(14)
        f.setBold(True)
        self.title_lbl.setFont(f)

        sub_info = QHBoxLayout()
        sub_info.setSpacing(8)
        self.source_lbl = QLabel(ctx.sources.display_name(task.source_id))
        self.source_lbl.setObjectName("Chip")
        self.status_badge = QLabel(task.status.value)
        self.status_badge.setObjectName("Chip")
        sub_info.addWidget(self.source_lbl)
        sub_info.addWidget(self.status_badge)
        sub_info.addStretch(1)

        info.addWidget(self.title_lbl)
        info.addLayout(sub_info)
        top.addLayout(info, 1)

        # Action buttons
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.remove_btn = QPushButton("✕ Remove")
        self.remove_btn.clicked.connect(self._remove)
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setObjectName("Play")
        self.play_btn.clicked.connect(self._play)

        top.addWidget(self.pause_btn)
        top.addWidget(self.cancel_btn)
        top.addWidget(self.remove_btn)
        top.addWidget(self.play_btn)
        layout.addLayout(top)

        # Progress bar
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        layout.addWidget(self.prog_bar)

        # Bottom stats row
        bottom = QHBoxLayout()
        self.stats_lbl = QLabel()
        self.stats_lbl.setObjectName("Muted")
        self.speed_lbl = QLabel()
        self.speed_lbl.setObjectName("Muted")
        bottom.addWidget(self.stats_lbl)
        bottom.addStretch(1)
        bottom.addWidget(self.speed_lbl)
        layout.addLayout(bottom)

        self.update_task(task)

    def update_task(self, task: DownloadTask):
        self.title_lbl.setText(task.item.title)
        self.status_badge.setText(task.status.value)

        # Thumbnail
        dpr = self.devicePixelRatioF()
        if task.item.cover_url:
            pm = self.ctx.images.get(task.item.cover_url, QSize(int(48 * dpr), int(64 * dpr)))
            if pm:
                self.thumb.setPixmap(pm.scaled(self.thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))

        # Progress
        pct = int(task.progress * 100)
        self.prog_bar.setValue(pct)

        # Status & button visibility
        st = task.status
        self.pause_btn.setVisible(st in (Status.DOWNLOADING, Status.RESOLVING, Status.QUEUED, Status.PAUSED))
        self.pause_btn.setText("Resume" if st in (Status.PAUSED, Status.FAILED) else "Pause")
        self.cancel_btn.setVisible(st not in FINISHED)
        self.remove_btn.setVisible(st in FINISHED)
        self.play_btn.setVisible(st == Status.COMPLETED and task.game_id > 0)

        # Style status badge
        if st == Status.COMPLETED:
            self.status_badge.setStyleSheet("background: #16a34a; color: white;")
        elif st == Status.FAILED:
            self.status_badge.setStyleSheet("background: #ef4444; color: white;")
        elif st == Status.DOWNLOADING:
            self.status_badge.setStyleSheet("background: #3d8bfd; color: white;")
        elif st == Status.EXTRACTING:
            self.status_badge.setStyleSheet("background: #8b5cf6; color: white;")
        else:
            self.status_badge.setStyleSheet("")

        # Stats text
        if st == Status.DOWNLOADING:
            dl_str = fmt_size(task.downloaded)
            tot_str = fmt_size(task.total) if task.total else "—"
            speed_str = f"{fmt_size(int(task.speed))}/s"
            eta_str = fmt_eta(task.eta)
            self.stats_lbl.setText(f"{dl_str} of {tot_str} ({pct}%)")
            self.speed_lbl.setText(f"{speed_str}  ·  ETA: {eta_str}")
        elif st == Status.EXTRACTING:
            self.stats_lbl.setText(f"Unpacking and verifying files… ({pct}%)")
            self.speed_lbl.setText("Installing")
        elif st == Status.VERIFYING:
            self.stats_lbl.setText("Verifying archive integrity…")
            self.speed_lbl.setText("")
        elif st == Status.RESOLVING:
            self.stats_lbl.setText("Resolving download package…")
            self.speed_lbl.setText("")
        elif st == Status.COMPLETED:
            self.stats_lbl.setText(f"Installed to {task.install_dir}")
            self.speed_lbl.setText("Ready to play")
        elif st == Status.FAILED:
            self.stats_lbl.setText(f"Error: {task.error or 'Failed'}")
            self.speed_lbl.setText("Click Resume to retry")
        elif st == Status.PAUSED:
            self.stats_lbl.setText("Download paused")
            self.speed_lbl.setText("")
        elif st == Status.CANCELLED:
            self.stats_lbl.setText("Download cancelled")
            self.speed_lbl.setText("")
        else:
            self.stats_lbl.setText("Waiting in queue…")
            self.speed_lbl.setText("")

    def _toggle_pause(self):
        t = self.ctx.downloads.task(self.task_id)
        if not t:
            return
        if t.status in (Status.PAUSED, Status.FAILED):
            self.ctx.downloads.resume(self.task_id)
        else:
            self.ctx.downloads.pause(self.task_id)

    def _cancel(self):
        self.ctx.downloads.cancel(self.task_id)

    def _remove(self):
        self.ctx.downloads.remove(self.task_id)

    def _play(self):
        t = self.ctx.downloads.task(self.task_id)
        if t and t.game_id:
            actions.launch_game(self.ctx, t.game_id, self)


class DownloadsView(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self._cards: dict[int, DownloadCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 16)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title = QLabel("DOWNLOADS")
        title.setObjectName("PageTitle")
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("Muted")
        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self.count_lbl, 0, Qt.AlignBottom)
        header.addStretch(1)

        self.clear_btn = QPushButton("Clear Finished")
        self.clear_btn.clicked.connect(self._clear_finished)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        # Scroll container for download cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll_body = QWidget()
        self.scroll_body.setObjectName("ScrollBody")
        self.cards_layout = QVBoxLayout(self.scroll_body)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.scroll_body)
        root.addWidget(self.scroll, 1)

        self.empty_lbl = QLabel("No active or recent downloads.\n\nBrowse the Store to find games and start downloading.")
        self.empty_lbl.setObjectName("EmptyState")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.cards_layout.insertWidget(0, self.empty_lbl)

        # Connect download manager signals
        ctx.downloads.task_added.connect(self._on_task_added)
        ctx.downloads.task_updated.connect(self._on_task_updated)
        ctx.downloads.task_removed.connect(self._on_task_removed)
        ctx.downloads.task_finished.connect(lambda *_: self._refresh_stats())
        ctx.images.image_ready.connect(lambda *_: self._update_thumbs())

        self.refresh()

    def refresh(self):
        tasks = self.ctx.downloads.tasks()
        for t in tasks:
            self._on_task_added(t.id)
            self._on_task_updated(t.id)
        self._refresh_stats()

    def _refresh_stats(self):
        tasks = self.ctx.downloads.tasks()
        active = sum(1 for t in tasks if t.status in ACTIVE)
        total = len(tasks)
        self.count_lbl.setText(f"{active} active · {total} total")
        self.empty_lbl.setVisible(total == 0)
        self.clear_btn.setEnabled(any(t.status in FINISHED for t in tasks))

    def _on_task_added(self, tid: int):
        task = self.ctx.downloads.task(tid)
        if not task:
            return
        if tid not in self._cards:
            card = DownloadCard(self.ctx, task)
            self._cards[tid] = card
            # Insert above the stretch item
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._refresh_stats()

    def _on_task_updated(self, tid: int):
        card = self._cards.get(tid)
        task = self.ctx.downloads.task(tid)
        if card and task:
            card.update_task(task)
        self._refresh_stats()

    def _on_task_removed(self, tid: int):
        card = self._cards.pop(tid, None)
        if card:
            card.deleteLater()
        self._refresh_stats()

    def _clear_finished(self):
        self.ctx.downloads.clear_finished()

    def _update_thumbs(self):
        for card in self._cards.values():
            t = self.ctx.downloads.task(card.task_id)
            if t:
                card.update_task(t)
