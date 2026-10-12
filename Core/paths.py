"""Central place for all filesystem locations used by the application.

The app is portable: everything (config, database, cache, logs) lives next to
``main.py`` unless the user points the games/temp folders somewhere else.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # PyInstaller / standalone executable
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = APP_DIR

# Bundled assets & scripts live in BUNDLE_DIR (or next to exe if directory mode)
ASSETS_DIR = BUNDLE_DIR / "Assets" if (BUNDLE_DIR / "Assets").is_dir() else (APP_DIR / "Assets")
SCRIPTS_DIR = BUNDLE_DIR / "Scripts" if (BUNDLE_DIR / "Scripts").is_dir() else (APP_DIR / "Scripts")
ROOT_SCRIPTS_DIR = APP_DIR.parent / "Scripts"
DATA_DIR = APP_DIR / "data"
CACHE_DIR = APP_DIR / "cache"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
LOG_DIR = APP_DIR / "logs"
DEFAULT_TEMP_DIR = APP_DIR / "temp"
CONFIG_FILE = APP_DIR / "config.json"
DB_FILE = DATA_DIR / "library.db"


def get_scripts_dirs() -> list[Path]:
    dirs: list[Path] = []
    if SCRIPTS_DIR.is_dir():
        dirs.append(SCRIPTS_DIR)
    # Also support user scripts placed next to the executable
    ext_scripts = APP_DIR / "Scripts"
    if ext_scripts.is_dir() and ext_scripts.resolve() not in [d.resolve() for d in dirs]:
        dirs.append(ext_scripts)
    if ROOT_SCRIPTS_DIR.is_dir() and ROOT_SCRIPTS_DIR.resolve() not in [d.resolve() for d in dirs]:
        dirs.append(ROOT_SCRIPTS_DIR)
    return dirs


def default_games_dir() -> Path:
    """Sensible default suggestion for the games folder."""
    if os.name == "nt":
        drive = Path(os.environ.get("SystemDrive", "C:") + "\\")
        return drive / "Games"
    return Path.home() / "Games"


def ensure_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, IMAGE_CACHE_DIR, LOG_DIR, DEFAULT_TEMP_DIR, ASSETS_DIR, SCRIPTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
