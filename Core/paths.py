"""Central place for all filesystem locations used by the application.

User state (configuration, database, image caches, logs, temporary downloads)
is stored in standard per-user AppData (%LOCALAPPDATA%\\Mist on Windows),
ensuring the standalone executable runs completely self-contained without
requiring any folders or files next to it.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


def get_user_data_dir() -> Path:
    """Returns the dedicated user application data directory in AppData / LocalAppData."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Mist"
        return Path.home() / "AppData" / "Local" / "Mist"
    return Path.home() / ".mist"


USER_DATA_DIR = get_user_data_dir()

if getattr(sys, "frozen", False):  # PyInstaller / standalone executable
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = APP_DIR

# Bundled read-only assets & scripts live in BUNDLE_DIR
ASSETS_DIR = BUNDLE_DIR / "Assets" if (BUNDLE_DIR / "Assets").is_dir() else (APP_DIR / "Assets")
SCRIPTS_DIR = BUNDLE_DIR / "Scripts" if (BUNDLE_DIR / "Scripts").is_dir() else (APP_DIR / "Scripts")
ROOT_SCRIPTS_DIR = APP_DIR.parent / "Scripts"

# User state files live in USER_DATA_DIR (AppData) so no files/folders are needed in the app directory
CONFIG_FILE = USER_DATA_DIR / "config.json"
DATA_DIR = USER_DATA_DIR / "data"
CACHE_DIR = USER_DATA_DIR / "cache"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
LOG_DIR = USER_DATA_DIR / "logs"
DEFAULT_TEMP_DIR = USER_DATA_DIR / "temp"
DB_FILE = DATA_DIR / "library.db"


def get_scripts_dirs() -> list[Path]:
    dirs: list[Path] = []
    if SCRIPTS_DIR.is_dir():
        dirs.append(SCRIPTS_DIR)
    # Also support user-added scripts placed next to the executable or in AppData
    appdata_scripts = USER_DATA_DIR / "Scripts"
    if appdata_scripts.is_dir() and appdata_scripts.resolve() not in [d.resolve() for d in dirs]:
        dirs.append(appdata_scripts)
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
    for d in (USER_DATA_DIR, DATA_DIR, CACHE_DIR, IMAGE_CACHE_DIR, LOG_DIR, DEFAULT_TEMP_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    # If the user's config.json does not exist yet in AppData, seed it from bundled/local template
    if not CONFIG_FILE.exists():
        template = BUNDLE_DIR / "config.json" if (BUNDLE_DIR / "config.json").is_file() else (APP_DIR / "config.json")
        if template.is_file():
            try:
                shutil.copy2(template, CONFIG_FILE)
            except OSError:
                pass
