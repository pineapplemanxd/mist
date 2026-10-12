"""User settings stored in ``config.json``.

Settings are a flat dict with defaults; unknown keys are preserved so that
source scripts can store their own options (namespaced, e.g. ``"source.gog.locale"``).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .logger import get_logger
from .paths import CONFIG_FILE, DEFAULT_TEMP_DIR, default_games_dir

log = get_logger(__name__)

DEFAULTS: dict[str, Any] = {
    "first_run_complete": False,
    "games_dir": str(default_games_dir()),
    "temp_dir": str(DEFAULT_TEMP_DIR),
    "default_source": "ankergames",
    "max_concurrent_downloads": 2,
    "bandwidth_limit_kbps": 0,          # 0 = unlimited (KiB/s)
    "theme": "dark",                    # dark | light (legacy alias)
    "theme_preset": "steam_modern",     # steam_modern | steam_2003 | epic_sidebar | gog_galaxy | light
    "layout_mode": "preset",           # preset | top_nav | sidebar
    "big_picture_style": "classic",     # classic | console (PS5)
    "controller_enabled": True,
    "auto_scan_steam": True,
    "library_view_mode": "grid",        # grid | list
    "library_sort": "name",
    "delete_archive_after_install": True,
    "store_page_size": 24,
}


class Config:
    def __init__(self, path: Path = CONFIG_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self._data.update(stored)
                if "theme" in stored and "theme_preset" not in stored:
                    self._data["theme_preset"] = stored["theme"]
                # Ensure temp_dir works across any user machine
                stored_temp = stored.get("temp_dir")
                if stored_temp:
                    try:
                        p = Path(stored_temp)
                        if not p.exists() and not p.parent.exists():
                            self._data["temp_dir"] = str(DEFAULT_TEMP_DIR)
                    except (OSError, ValueError):
                        self._data["temp_dir"] = str(DEFAULT_TEMP_DIR)
                else:
                    self._data["temp_dir"] = str(DEFAULT_TEMP_DIR)
        except (OSError, ValueError) as exc:
            log.error("Could not read config %s: %s (using defaults)", self._path, exc)

    def save(self) -> None:
        with self._lock:
            tmp = self._path.with_suffix(".tmp")
            try:
                with tmp.open("w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2, sort_keys=True)
                tmp.replace(self._path)
            except OSError as exc:
                log.error("Could not save config: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            return self._data[key]
        return DEFAULTS.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self._data[key] = value
        if save:
            self.save()

    def update(self, values: dict[str, Any]) -> None:
        self._data.update(values)
        self.save()

    def get_theme_preset(self) -> str:
        """Return the active theme preset, checking stored theme_preset then legacy theme."""
        if "theme_preset" in self._data:
            return str(self._data["theme_preset"])
        if "theme" in self._data:
            return str(self._data["theme"])
        return str(DEFAULTS.get("theme_preset", "steam_modern"))

    # Convenience typed accessors -------------------------------------------------
    @property
    def games_dir(self) -> Path:
        return Path(self.get("games_dir"))

    @property
    def temp_dir(self) -> Path:
        return Path(self.get("temp_dir"))
