"""Central place for all filesystem locations used by the application.

The app is portable: everything (config, database, cache, logs) lives next to
``main.py`` unless the user points the games/temp folders somewhere else.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # PyInstaller / similar
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = APP_DIR / "Assets"
SCRIPTS_DIR = APP_DIR / "Scripts"
ROOT_SCRIPTS_DIR = APP_DIR.parent / "Scripts"
DATA_DIR = APP_DIR / "data"
CACHE_DIR = APP_DIR / "cache"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
LOG_DIR = APP_DIR / "logs"
DEFAULT_TEMP_DIR = APP_DIR / "temp"
CONFIG_FILE = APP_DIR / "config.json"
DB_FILE = DATA_DIR / "library.db"


def get_scripts_dirs() -> list[Path]:
    dirs = [SCRIPTS_DIR]
    if ROOT_SCRIPTS_DIR.is_dir() and ROOT_SCRIPTS_DIR.resolve() != SCRIPTS_DIR.resolve():
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
