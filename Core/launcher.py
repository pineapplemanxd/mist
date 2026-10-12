"""Game executable detection, launching and playtime tracking."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .logger import get_logger

log = get_logger(__name__)

try:
    import psutil  # optional but strongly recommended for accurate tracking
except ImportError:  # pragma: no cover
    psutil = None

LAUNCHABLE = {".exe", ".bat", ".cmd", ".lnk", ".url"} if os.name == "nt" else {".sh", ".x86_64", ".AppImage", ""}

_BAD_EXE = re.compile(
    r"(unins|uninst|setup|install|redist|vcredist|vc_redist|dxsetup|directx|dotnet|crash|report|"
    r"helper|launcherhelper|easyanticheat|eac_|battleye|be_service|ue4prereq|prereq|updater|"
    r"cefprocess|webhelper|unitycrashhandler|touchup|quicksfv|notification|config|settings)",
    re.I,
)
_BAD_DIRS = re.compile(r"(redist|_commonredist|directx|vcredist|support|prereq|__installer|dotnet|easyanticheat|battleye)", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_executables(install_dir: Path, max_depth: int = 4) -> list[Path]:
    """All launchable files below ``install_dir`` (bounded depth)."""
    found: list[Path] = []
    base_depth = len(install_dir.parts)
    for root, dirs, files in os.walk(install_dir):
        depth = len(Path(root).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not _BAD_DIRS.search(d)]
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in {".exe", ".bat", ".cmd"} if os.name == "nt" else os.access(p, os.X_OK):
                found.append(p)
    return found


def guess_executable(install_dir: Path, title: str = "") -> str:
    """Best-effort pick of the main game executable."""
    if not install_dir.is_dir():
        return ""
    candidates = find_executables(install_dir)
    if not candidates:
        return ""
    t = _norm(title)
    base_depth = len(install_dir.parts)

    def score(p: Path) -> float:
        s = 0.0
        stem = _norm(p.stem)
        if _BAD_EXE.search(p.stem):
            s -= 100
        if t and stem:
            if stem == t:
                s += 60
            elif stem in t or t in stem:
                s += 35
        if p.suffix.lower() == ".exe":
            s += 10
        if "launcher" in stem:
            s += 5
        if re.search(r"(win64|x64|binaries|bin)", str(p.parent), re.I):
            s += 4
        if "shipping" in stem:
            s += 8
        s -= (len(p.parts) - base_depth) * 3
        try:
            s += min(p.stat().st_size / (1024 * 1024), 200) / 10  # bigger binaries are likelier games
        except OSError:
            pass
        return s

    best = max(candidates, key=score)
    return str(best) if score(best) > -50 else ""


class PlaytimeTracker(QObject):
    """Tracks running time of launched games.

    With ``psutil`` the tracker watches *any* process whose executable lives in
    the game's install folder, which also covers games started through a
    launcher stub or via Steam. Without psutil it falls back to the PID it
    spawned.
    """

    game_started = Signal(int)            # game_id
    game_stopped = Signal(int, int)       # game_id, seconds played this session

    POLL = 5.0
    STARTUP_GRACE = 90.0                  # seconds to wait for the game process to appear

    def __init__(self):
        super().__init__()
        self._sessions: dict[int, dict] = {}
        self._lock = threading.Lock()

    def is_running(self, game_id: int) -> bool:
        with self._lock:
            return game_id in self._sessions

    def track(self, game_id: int, install_dir: str, popen: subprocess.Popen | None) -> None:
        with self._lock:
            if game_id in self._sessions:
                return
            self._sessions[game_id] = {"dir": install_dir, "popen": popen}
        threading.Thread(target=self._watch, args=(game_id,), name=f"playtime-{game_id}", daemon=True).start()
        self.game_started.emit(game_id)

    def _alive(self, sess: dict) -> bool:
        install_dir = sess["dir"]
        if psutil and install_dir:
            prefix = os.path.normcase(os.path.abspath(install_dir)) + os.sep
            for pid in list(sess.get("pids", ())):
                try:
                    if psutil.pid_exists(pid) and psutil.Process(pid).is_running():
                        return True
                except (psutil.Error, OSError):
                    pass
            pids = []
            for proc in psutil.process_iter(["exe"]):
                try:
                    exe = proc.info.get("exe")
                except (psutil.Error, OSError):
                    continue
                if exe and os.path.normcase(exe).startswith(prefix):
                    pids.append(proc.pid)
            sess["pids"] = pids
            if pids:
                return True
        popen = sess.get("popen")
        return bool(popen and popen.poll() is None)

    def _watch(self, game_id: int) -> None:
        sess = self._sessions[game_id]
        launched = time.monotonic()
        started: float | None = None
        last_seen = launched
        while True:
            time.sleep(self.POLL)
            alive = self._alive(sess)
            now = time.monotonic()
            if alive:
                if started is None:
                    started = now - self.POLL
                last_seen = now
            elif started is not None:
                break
            elif now - launched > self.STARTUP_GRACE:
                break
        seconds = int(last_seen - started) if started is not None else 0
        with self._lock:
            self._sessions.pop(game_id, None)
        log.info("Game %s session ended: %ss", game_id, seconds)
        self.game_stopped.emit(game_id, seconds)


class LaunchError(Exception):
    pass


def launch(game: dict) -> subprocess.Popen | None:
    """Start a game. Returns the Popen when we spawned a process ourselves."""
    uri = game.get("launch_uri") or ""
    exe = game.get("executable") or ""
    args = game.get("launch_args") or ""
    if exe:
        path = Path(exe)
        if not path.exists():
            raise LaunchError(f"Executable not found:\n{exe}")
        if path.suffix.lower() in {".lnk", ".url"}:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return None
        cmd = [str(path)] + (args.split() if args else [])
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            if path.suffix.lower() in {".bat", ".cmd"}:
                flags = subprocess.CREATE_NEW_CONSOLE
        try:
            return subprocess.Popen(cmd, cwd=str(path.parent), creationflags=flags, close_fds=True)
        except OSError as exc:
            raise LaunchError(f"Could not start game: {exc}") from exc
    if uri:
        try:
            if os.name == "nt":
                os.startfile(uri)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", uri])
        except OSError as exc:
            raise LaunchError(f"Could not open {uri}: {exc}") from exc
        return None
    raise LaunchError("No executable configured for this game. Use 'Set executable…' to pick one.")
