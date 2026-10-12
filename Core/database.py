"""SQLite persistence layer.

A single connection is shared between threads and guarded by a lock. Writes
are tiny (library rows), so this is simpler and cheaper than a pool.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .logger import get_logger
from .paths import DB_FILE

log = get_logger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    source           TEXT NOT NULL DEFAULT 'manual',
    source_id        TEXT NOT NULL DEFAULT '',
    installed        INTEGER NOT NULL DEFAULT 1,
    install_dir      TEXT DEFAULT '',
    executable       TEXT DEFAULT '',
    launch_args      TEXT DEFAULT '',
    launch_uri       TEXT DEFAULT '',
    cover_url        TEXT DEFAULT '',
    hero_url         TEXT DEFAULT '',
    description      TEXT DEFAULT '',
    developer        TEXT DEFAULT '',
    publisher        TEXT DEFAULT '',
    release_date     TEXT DEFAULT '',
    genres           TEXT DEFAULT '[]',
    system_requirements TEXT DEFAULT '',
    screenshots      TEXT DEFAULT '[]',
    version          TEXT DEFAULT '',
    size_bytes       INTEGER DEFAULT 0,
    playtime_seconds INTEGER NOT NULL DEFAULT 0,
    last_played      INTEGER DEFAULT 0,
    favorite         INTEGER NOT NULL DEFAULT 0,
    added_at         INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_games_last_played ON games(last_played);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

JSON_FIELDS = ("genres", "screenshots")
GAME_FIELDS = (
    "title", "source", "source_id", "installed", "install_dir", "executable", "launch_args",
    "launch_uri", "cover_url", "hero_url", "description", "developer", "publisher",
    "release_date", "genres", "system_requirements", "screenshots", "version", "size_bytes",
    "playtime_seconds", "last_played", "favorite", "added_at",
)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for f in JSON_FIELDS:
        try:
            d[f] = json.loads(d.get(f) or "[]")
        except ValueError:
            d[f] = []
    return d


def _encode(values: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in values.items():
        if k not in GAME_FIELDS:
            continue
        if k in JSON_FIELDS and not isinstance(v, str):
            v = json.dumps(list(v or []))
        if isinstance(v, bool):
            v = int(v)
        out[k] = v
    return out


class Database:
    def __init__(self, path: Path | str = DB_FILE):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ games
    def all_games(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM games").fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_game(self, game_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def find_game(self, source: str, source_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM games WHERE source=? AND source_id=?", (source, source_id)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def upsert_game(self, values: dict[str, Any]) -> int:
        """Insert or update a game identified by (source, source_id). Returns the row id.

        User-owned fields (playtime, favorite, last_played, a manually chosen
        executable) are never overwritten by an update.
        """
        data = _encode(values)
        data.setdefault("source", "manual")
        data.setdefault("source_id", data.get("title", ""))
        with self._lock:
            existing = self._conn.execute(
                "SELECT id, executable FROM games WHERE source=? AND source_id=?",
                (data["source"], data["source_id"]),
            ).fetchone()
            if existing:
                protected = {"playtime_seconds", "favorite", "last_played", "added_at", "source", "source_id"}
                if existing["executable"]:
                    protected.add("executable")
                upd = {k: v for k, v in data.items() if k not in protected}
                if upd:
                    cols = ", ".join(f"{k}=?" for k in upd)
                    self._conn.execute(f"UPDATE games SET {cols} WHERE id=?", (*upd.values(), existing["id"]))
                return int(existing["id"])
            data.setdefault("added_at", int(time.time()))
            cols = ", ".join(data)
            marks = ", ".join("?" for _ in data)
            cur = self._conn.execute(f"INSERT INTO games ({cols}) VALUES ({marks})", tuple(data.values()))
            return int(cur.lastrowid)

    def update_game(self, game_id: int, **values: Any) -> None:
        data = _encode(values)
        if not data:
            return
        cols = ", ".join(f"{k}=?" for k in data)
        with self._lock:
            self._conn.execute(f"UPDATE games SET {cols} WHERE id=?", (*data.values(), game_id))

    def add_playtime(self, game_id: int, seconds: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE games SET playtime_seconds = playtime_seconds + ? WHERE id=?", (int(seconds), game_id)
            )

    def delete_game(self, game_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM games WHERE id=?", (game_id,))

    def delete_games(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        with self._lock:
            self._conn.executemany("DELETE FROM games WHERE id=?", [(i,) for i in ids])

    # ------------------------------------------------------------------- meta
    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))
