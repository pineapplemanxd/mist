"""Read-only Steam library detection.

Finds Steam installs, reads ``libraryfolders.vdf`` for extra library folders
and parses ``appmanifest_*.acf`` files. Nothing under the Steam directory is
ever written to.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .logger import get_logger

log = get_logger(__name__)

# Tools/runtimes that show up as "apps" but aren't games.
IGNORED_APPIDS = {
    "228980",   # Steamworks Common Redistributables
    "1070560", "1391110", "1628350",  # Steam Linux Runtimes
    "1493710", "1826330", "2180100", "2348590", "961940", "1054830", "1113280", "1245040",  # Proton
    "250820",   # SteamVR
}
IGNORED_NAME_PATTERNS = re.compile(r"(redistributable|steamworks|proton|steam linux runtime|dedicated server|sdk$)", re.I)

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text: str) -> dict:
    """Minimal parser for Valve's text KeyValues format (VDF/ACF)."""
    root: dict = {}
    stack = [root]
    pending_key: str | None = None
    for m in _TOKEN.finditer(text):
        quoted, brace = m.groups()
        if brace == "{":
            new: dict = {}
            if pending_key is not None:
                stack[-1][pending_key] = new
            stack.append(new)
            pending_key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            pending_key = None
        else:
            value = quoted.replace('\\\\', '\\').replace('\\"', '"')
            if pending_key is None:
                pending_key = value
            else:
                stack[-1][pending_key] = value
                pending_key = None
    return root


def _ci_get(d: dict, key: str, default=None):
    """Case-insensitive dict get (Valve files aren't consistent with casing)."""
    if key in d:
        return d[key]
    lk = key.lower()
    for k, v in d.items():
        if k.lower() == lk:
            return v
    return default


@dataclass
class SteamGame:
    appid: str
    name: str
    install_dir: Path
    size_bytes: int = 0
    last_played: int = 0
    cover_path: str = ""
    hero_path: str = ""
    extra: dict = field(default_factory=dict)


def find_steam_roots() -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            for hive, sub in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as key:
                        for value_name in ("SteamPath", "InstallPath"):
                            try:
                                val, _ = winreg.QueryValueEx(key, value_name)
                                candidates.append(Path(val))
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates += [Path(pf86) / "Steam", Path(pf) / "Steam"]
    else:
        home = Path.home()
        candidates += [home / ".steam/steam", home / ".local/share/Steam",
                       home / "Library/Application Support/Steam"]

    seen: set[str] = set()
    roots: list[Path] = []
    for c in candidates:
        try:
            key = str(c.resolve()).lower()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if (c / "steamapps").is_dir():
            roots.append(c)
    return roots


def find_library_folders(steam_root: Path) -> list[Path]:
    libs = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        try:
            data = parse_vdf(vdf.read_text(encoding="utf-8", errors="replace"))
            folders = _ci_get(data, "libraryfolders", {}) or {}
            for _, entry in folders.items():
                if isinstance(entry, dict):
                    p = _ci_get(entry, "path")
                elif isinstance(entry, str) and os.path.isdir(entry):  # old format: "1" "D:\\SteamLibrary"
                    p = entry
                else:
                    p = None
                if p:
                    libs.append(Path(p))
        except OSError as exc:
            log.warning("Could not read %s: %s", vdf, exc)
    unique: list[Path] = []
    seen: set[str] = set()
    for lib in libs:
        k = os.path.normcase(str(lib))
        if k not in seen and (lib / "steamapps").is_dir():
            seen.add(k)
            unique.append(lib)
    return unique


def _find_cached_art(steam_root: Path, appid: str, names: tuple[str, ...]) -> str:
    """Locate artwork in Steam's local library cache (read-only, no network)."""
    cache = steam_root / "appcache" / "librarycache"
    if not cache.is_dir():
        return ""
    for name in names:
        old = cache / f"{appid}_{name}"
        if old.is_file():
            return str(old)
    app_dir = cache / appid
    if app_dir.is_dir():
        for name in names:
            direct = app_dir / name
            if direct.is_file():
                return str(direct)
            for hit in app_dir.glob(f"*/{name}"):
                return str(hit)
    return ""


def scan_steam() -> list[SteamGame]:
    games: dict[str, SteamGame] = {}
    for root in find_steam_roots():
        for lib in find_library_folders(root):
            steamapps = lib / "steamapps"
            for acf in steamapps.glob("appmanifest_*.acf"):
                try:
                    data = parse_vdf(acf.read_text(encoding="utf-8", errors="replace"))
                except OSError as exc:
                    log.warning("Skipping unreadable manifest %s: %s", acf, exc)
                    continue
                state = _ci_get(data, "AppState", {}) or {}
                appid = str(_ci_get(state, "appid", "") or "")
                name = _ci_get(state, "name", "") or ""
                installdir = _ci_get(state, "installdir", "") or ""
                if not appid or not name or appid in IGNORED_APPIDS or IGNORED_NAME_PATTERNS.search(name):
                    continue
                path = steamapps / "common" / installdir
                if not path.is_dir():
                    continue
                try:
                    size = int(_ci_get(state, "SizeOnDisk", 0) or 0)
                except ValueError:
                    size = 0
                try:
                    last_played = int(_ci_get(state, "LastPlayed", 0) or 0)
                except ValueError:
                    last_played = 0
                games[appid] = SteamGame(
                    appid=appid,
                    name=name,
                    install_dir=path,
                    size_bytes=size,
                    last_played=last_played,
                    cover_path=_find_cached_art(root, appid, ("library_600x900.jpg", "library_capsule.jpg", "header.jpg")),
                    hero_path=_find_cached_art(root, appid, ("library_hero.jpg", "header.jpg")),
                )
    log.info("Steam scan found %d games", len(games))
    return sorted(games.values(), key=lambda g: g.name.lower())
