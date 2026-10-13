"""Shared UI helpers: async runner, formatting, painting helpers, small widgets."""
from __future__ import annotations

import hashlib
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QRectF, QRunnable, QSize, Qt,
                            QThreadPool, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QLayout, QWidget

from . import theme

# --------------------------------------------------------------------------- async


class _AsyncSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class _AsyncJob(QRunnable):
    def __init__(self, fn: Callable[[], Any], signals: _AsyncSignals):
        super().__init__()
        self.fn, self.signals = fn, signals

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            try:
                self.signals.error.emit(str(exc) or exc.__class__.__name__)
            except RuntimeError:
                pass
        else:
            try:
                self.signals.done.emit(result)
            except RuntimeError:
                pass


_io_pool = QThreadPool()
_io_pool.setMaxThreadCount(4)
_live_signals: set[_AsyncSignals] = set()


def run_async(fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
              on_error: Callable[[str], None] | None = None, context: QObject | None = None) -> None:
    """Run ``fn`` on a worker thread; callbacks are invoked on the GUI thread.

    If ``context`` is given and gets destroyed before completion the callbacks
    are skipped (avoids touching deleted widgets).
    """
    sig = _AsyncSignals()
    _live_signals.add(sig)
    alive = [True]
    if context is not None:
        context.destroyed.connect(lambda *_: alive.__setitem__(0, False))

    def finish(cb, value):
        _live_signals.discard(sig)
        if cb and alive[0]:
            cb(value)

    sig.done.connect(lambda r: finish(on_done, r))
    sig.error.connect(lambda e: finish(on_error, e))
    _io_pool.start(_AsyncJob(fn, sig))


def shutdown_async(wait_ms: int = 1500) -> None:
    """Wait for running async tasks to finish and clear pending signals."""
    try:
        _io_pool.clear()
        _io_pool.waitForDone(wait_ms)
        _live_signals.clear()
    except Exception:
        pass


# ------------------------------------------------------------------------ format

def fmt_size(n: int) -> str:
    if not n:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def fmt_playtime(seconds: int) -> str:
    if not seconds:
        return "Never played"
    if seconds < 60:
        return "< 1 min"
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m}m" if h else f"{m} min"


def fmt_ago(ts: int) -> str:
    if not ts:
        return "Never"
    d = time.time() - ts
    if d < 60:
        return "Just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    if d < 86400 * 2:
        return "Yesterday"
    if d < 86400 * 30:
        return f"{int(d // 86400)} days ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def fmt_eta(seconds: float) -> str:
    if seconds < 0:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------- painting

def _hash_hue(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:6], 16) % 360


def paint_placeholder(p: QPainter, rect: QRect, title: str, font_px: int | None = None) -> None:
    """Deterministic gradient cover with the game's initials (no network needed)."""
    hue = _hash_hue(title or "?")
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor.fromHsl(hue, 120, 70))
    grad.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 140, 28))
    p.fillRect(rect, grad)
    words = [w for w in (title or "?").replace(":", " ").split() if w[:1].isalnum()]
    initials = "".join(w[0] for w in words[:2]).upper() or "?"
    f = QFont(p.font())
    f.setPixelSize(font_px or max(14, rect.height() // 5))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 220))
    p.drawText(rect.adjusted(6, 6, -6, -rect.height() // 4), Qt.AlignCenter, initials)
    f.setPixelSize(max(10, rect.height() // 16))
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 200))
    p.drawText(rect.adjusted(8, rect.height() // 2, -8, -8), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, title)


def draw_pixmap_cover(p: QPainter, rect: QRect, pm: QPixmap) -> None:
    """Draw ``pm`` filling ``rect`` (center-crop, keeps aspect)."""
    if pm.isNull():
        return
    src_ratio = pm.width() / max(1, pm.height())
    dst_ratio = rect.width() / max(1, rect.height())
    if src_ratio > dst_ratio:
        w = int(pm.height() * dst_ratio)
        src = QRect((pm.width() - w) // 2, 0, w, pm.height())
    else:
        h = int(pm.width() / dst_ratio)
        src = QRect(0, (pm.height() - h) // 2, pm.width(), h)
    p.drawPixmap(rect, pm, src)


def draw_badge(p: QPainter, pos: QPoint, text: str, bg: str, font_px: int = 10) -> QRect:
    f = QFont(p.font())
    f.setPixelSize(font_px)
    f.setBold(True)
    p.setFont(f)
    w = p.fontMetrics().horizontalAdvance(text) + 12
    h = font_px + 8
    r = QRect(pos.x(), pos.y(), w, h)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setPen(QColor("#ffffff"))
    p.drawText(r, Qt.AlignCenter, text)
    return r


def rounded_path(rect: QRect | QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    return path


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0, QColor("#171a21"))
        grad.setColorAt(1, QColor("#66c0f4"))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        p.setBrush(QColor("#ffffff"))
        tri = QPainterPath()
        tri.moveTo(size * 0.38, size * 0.28)
        tri.lineTo(size * 0.38, size * 0.72)
        tri.lineTo(size * 0.74, size * 0.5)
        tri.closeSubpath()
        p.drawPath(tri)
        p.end()
        icon.addPixmap(pm)
    return icon


# ----------------------------------------------------------------------- widgets

class Toast(QLabel):
    """Small transient notification shown at the bottom-right of a parent widget."""

    def __init__(self, parent: QWidget, text: str, ms: int = 3500):
        super().__init__(text, parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.setMaximumWidth(380)
        self.adjustSize()
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._reposition()
        self.show()
        self.raise_()
        QTimer.singleShot(ms, self._fade)

    def _reposition(self) -> None:
        par = self.parentWidget()
        siblings = [c for c in par.findChildren(Toast) if c is not self and c.isVisible()]
        offset = sum(s.height() + 8 for s in siblings)
        self.move(par.width() - self.width() - 24, par.height() - self.height() - 24 - offset)

    def _fade(self) -> None:
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(400)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.OutQuad)
        anim.finished.connect(self.deleteLater)
        anim.start()


class FlowLayout(QLayout):
    """Wrapping layout for chips/tags."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        if 0 <= i < len(self._items):
            item = self._items.pop(i)
            self.invalidate()
            return item
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do_layout(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            w = it.sizeHint()
            if x + w.width() > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + self._spacing
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), w))
            x += w.width() + self._spacing
            line_h = max(line_h, w.height())
        return y + line_h - rect.y()


def chip(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("Chip")
    return lbl


def muted(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Muted")
    return lbl


def theme_color(name: str, alpha: int | None = None) -> QColor:
    return theme.color(name, alpha)
