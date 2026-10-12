"""Game actions shared by the library and detail views."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from Core.launcher import LaunchError, find_executables
from Core.logger import get_logger

log = get_logger(__name__)


def launch_game(ctx, game_id: int, parent: QWidget) -> None:
    g = ctx.library.game(game_id)
    if not g:
        return
    if not g.get("installed"):
        QMessageBox.information(parent, "Not installed", f"{g['title']} is not installed.")
        return
    try:
        ctx.library.launch(game_id)
        ctx.toast(f"▶  Launching {g['title']}…")
    except LaunchError as exc:
        if not g.get("launch_uri") and g.get("install_dir"):
            res = QMessageBox.question(parent, "Cannot launch", f"{exc}\n\nPick the game executable now?")
            if res == QMessageBox.Yes and pick_executable(ctx, game_id, parent):
                launch_game(ctx, game_id, parent)
            return
        QMessageBox.warning(parent, "Cannot launch", str(exc))


def pick_executable(ctx, game_id: int, parent: QWidget) -> bool:
    g = ctx.library.game(game_id)
    if not g:
        return False
    start = g.get("install_dir") or ""
    flt = "Programs (*.exe *.bat *.cmd *.lnk);;All files (*)" if os.name == "nt" else "All files (*)"
    path, _ = QFileDialog.getOpenFileName(parent, f"Select executable for {g['title']}", start, flt)
    if not path:
        return False
    ctx.library.set_executable(game_id, os.path.normpath(path))
    if not g.get("install_dir"):
        ctx.library.db.update_game(game_id, install_dir=str(Path(path).parent))
    ctx.toast("Executable updated")
    return True


def open_folder(path: str, parent: QWidget | None = None) -> None:
    if not path or not os.path.isdir(path):
        QMessageBox.information(parent, "Folder not found", f"The folder does not exist:\n{path}")
        return
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def toggle_favorite(ctx, game_id: int) -> None:
    g = ctx.library.game(game_id)
    if g:
        ctx.library.set_favorite(game_id, not g["favorite"])


def remove_from_library(ctx, game_id: int, parent: QWidget) -> bool:
    g = ctx.library.game(game_id)
    if not g:
        return False
    res = QMessageBox.question(
        parent, "Remove from library",
        f"Remove {g['title']} from the library?\n\nGame files are NOT deleted.")
    if res != QMessageBox.Yes:
        return False
    ctx.library.remove(game_id)
    return True


def can_uninstall(g: dict) -> bool:
    return bool(g.get("installed")) and g.get("source") not in ("steam", "manual")


def uninstall_game(ctx, game_id: int, parent: QWidget) -> bool:
    g = ctx.library.game(game_id)
    if not g:
        return False
    if g["source"] == "steam":
        QMessageBox.information(parent, "Steam game",
                                "Steam games are managed by Steam. Uninstall them from the Steam client.")
        return False
    res = QMessageBox.warning(
        parent, "Uninstall",
        f"Permanently delete {g['title']}?\n\n{g.get('install_dir')}\n\nThis cannot be undone.",
        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
    if res != QMessageBox.Yes:
        return False
    try:
        ctx.library.uninstall(game_id, ctx.config.games_dir)
        ctx.toast(f"{g['title']} uninstalled")
        return True
    except (OSError, PermissionError) as exc:
        log.exception("Uninstall failed")
        QMessageBox.critical(parent, "Uninstall failed", str(exc))
        return False


def add_game_manually(ctx, parent: QWidget) -> None:
    flt = "Programs (*.exe *.bat *.cmd *.lnk);;All files (*)" if os.name == "nt" else "All files (*)"
    path, _ = QFileDialog.getOpenFileName(parent, "Add a game executable", "", flt)
    if path:
        ctx.library.add_manual(os.path.normpath(path))
        ctx.toast("Game added to library")


def import_existing_folders(ctx, root: Path) -> int:
    """Register sub-folders of the games directory that contain an executable."""
    from Core.launcher import guess_executable
    if not root.is_dir():
        return 0
    known = {os.path.normcase(g["install_dir"]) for g in ctx.library.games() if g.get("install_dir")}
    added = 0
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith(".") or os.path.normcase(str(sub)) in known:
            continue
        if not find_executables(sub, max_depth=3):
            continue
        exe = guess_executable(sub, sub.name)
        ctx.library.db.upsert_game({
            "title": sub.name, "source": "manual", "source_id": os.path.normcase(str(sub)),
            "install_dir": str(sub), "executable": exe, "installed": 1,
        })
        added += 1
    if added:
        ctx.library.changed.emit()
    return added
