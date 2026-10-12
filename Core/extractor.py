"""Archive extraction with verification.

ZIP is handled natively (with CRC verification) or via external tools (Windows tar.exe / 7z)
if advanced compression (e.g. Zstandard, Deflate64) or encryption is encountered.
``.tar.*`` archives use the standard library with external fallback.
``.7z``/``.rar`` are extracted with an external ``7z``, ``tar``, or ``unrar`` executable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Callable

from .logger import get_logger
from .paths import APP_DIR, SCRIPTS_DIR

log = get_logger(__name__)

ProgressFn = Callable[[int, int], None]          # (done, total)
CancelFn = Callable[[], bool]


class ExtractionError(Exception):
    pass


class ExtractionCancelled(ExtractionError):
    pass


def _find_tar() -> str | None:
    candidates: list[Path] = []
    if os.name == "nt":
        sys_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        candidates.extend([
            sys_root / "System32" / "tar.exe",
            Path(r"C:\Windows\System32\tar.exe"),
        ])
    found = shutil.which("tar")
    if found:
        candidates.append(Path(found))
    candidates.extend([
        SCRIPTS_DIR / "bin" / "tar.exe",
        SCRIPTS_DIR / "bin" / "tar",
        APP_DIR / "bin" / "tar.exe",
        APP_DIR.parent / "bin" / "tar.exe",
    ])
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def _find_7z() -> str | None:
    for cand in (
        SCRIPTS_DIR / "bin" / "7z.exe",
        SCRIPTS_DIR / "bin" / "7za.exe",
        SCRIPTS_DIR / "bin" / "7z",
        APP_DIR / "bin" / "7z.exe",
        APP_DIR / "bin" / "7za.exe",
    ):
        if cand.is_file():
            return str(cand)
    for name in ("7z", "7za", "7zr"):
        found = shutil.which(name)
        if found:
            return found
    pf_dirs = [
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramW6432", ""),
        str(Path.home() / "AppData" / "Local" / "Programs"),
    ]
    for pf in pf_dirs:
        if pf:
            for sub in ("7-Zip", "7z"):
                for exe in ("7z.exe", "7za.exe"):
                    cand = Path(pf) / sub / exe
                    if cand.is_file():
                        return str(cand)
    for cand in (
        APP_DIR.parent / "Project-GLD" / "dependencies" / "7z.exe",
        APP_DIR.parent / "Project-GLD" / "dependencies" / "7za.exe",
        APP_DIR.parent / "Project-GLD" / "External" / "7z.exe",
        APP_DIR.parent / "Project-GLD" / "External" / "7za.exe",
        APP_DIR.parent / "Project-GLD" / "7z.exe",
        APP_DIR.parent / "Project-GLD" / "7za.exe",
        Path.cwd() / "Project-GLD" / "dependencies" / "7z.exe",
        Path.cwd() / "Project-GLD" / "dependencies" / "7za.exe",
    ):
        if cand.is_file():
            return str(cand)
    return None


def _find_unrar() -> str | None:
    found = shutil.which("unrar")
    if found:
        return found
    for pf in (
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramW6432", ""),
    ):
        if pf:
            for cand in (
                Path(pf) / "WinRAR" / "UnRAR.exe",
                Path(pf) / "WinRAR" / "unrar.exe",
                Path(pf) / "WinRAR" / "WinRAR.exe",
            ):
                if cand.is_file():
                    return str(cand)
    for cand in (
        SCRIPTS_DIR / "bin" / "unrar.exe",
        APP_DIR / "bin" / "unrar.exe",
    ):
        if cand.is_file():
            return str(cand)
    return None


def _safe_target(base: Path, member: str) -> Path:
    """Prevent path traversal ("zip slip")."""
    p_member = Path(member)
    if p_member.is_absolute() or p_member.drive:
        raise ExtractionError(f"Unsafe path in archive: {member}")
    base_resolved = base.resolve()
    try:
        target = (base_resolved / member).resolve()
        if os.path.commonpath([str(base_resolved), str(target)]) != str(base_resolved):
            raise ExtractionError(f"Unsafe path in archive: {member}")
        return target
    except (ValueError, OSError) as exc:
        raise ExtractionError(f"Unsafe path in archive: {member}") from exc


def _check_zip_slip(archive: Path, dest: Path) -> None:
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    _safe_target(dest, info.filename)
    except (ExtractionError, ExtractionCancelled):
        raise
    except Exception:
        pass
    try:
        if tarfile.is_tarfile(archive):
            with tarfile.open(archive) as tf:
                for member in tf.getmembers():
                    _safe_target(dest, member.name)
    except (ExtractionError, ExtractionCancelled):
        raise
    except Exception:
        pass


_TAR_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}


def uncompressed_size(archive: Path) -> int:
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                total = sum(i.file_size for i in zf.infolist())
                if total > 0:
                    return total
    except Exception:
        pass
    try:
        if tarfile.is_tarfile(archive):
            with tarfile.open(archive) as tf:
                total = sum(m.size for m in tf.getmembers())
                if total > 0:
                    return total
    except Exception:
        pass
    tar_exe = _find_tar()
    if tar_exe:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(
                [tar_exe, "-tvf", str(archive)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                creationflags=flags,
                timeout=30,
            )
            if proc.returncode == 0:
                total = 0
                for line in proc.stdout.splitlines():
                    if not line.startswith("-"):
                        continue
                    parts = line.split()
                    parsed = False
                    for idx in range(1, len(parts)):
                        p_lower = parts[idx].lower().rstrip(".")
                        if p_lower in _TAR_MONTHS:
                            if idx >= 2 and parts[idx - 1].isdigit() and (1 <= int(parts[idx - 1]) <= 31) and parts[idx - 2].isdigit():
                                total += int(parts[idx - 2])
                                parsed = True
                                break
                            if idx >= 1 and parts[idx - 1].isdigit():
                                total += int(parts[idx - 1])
                                parsed = True
                                break
                        elif len(parts[idx]) == 10 and parts[idx][4] == "-" and parts[idx][7] == "-":
                            if idx >= 1 and parts[idx - 1].isdigit():
                                total += int(parts[idx - 1])
                                parsed = True
                                break
                    if not parsed:
                        for idx in (4, 3, 5, 2):
                            if idx < len(parts) and parts[idx].isdigit():
                                total += int(parts[idx])
                                break
                if total > 0:
                    return total
        except Exception:
            pass
    exe_7z = _find_7z()
    if exe_7z:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(
                [exe_7z, "l", str(archive)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                creationflags=flags,
                timeout=30,
            )
            if proc.returncode == 0:
                for line in reversed(proc.stdout.splitlines()):
                    if "files" in line or "folders" in line:
                        parts = line.split()
                        num_tokens = []
                        for p in parts:
                            if (len(p) == 10 and p[4] == "-" and p[7] == "-") or (":" in p):
                                continue
                            if p.isdigit():
                                num_tokens.append(int(p))
                        if num_tokens:
                            return num_tokens[0]
        except Exception:
            pass
    return 0


_ZIP_SUPPORTED_COMPRESSIONS = {
    zipfile.ZIP_STORED,    # 0
    zipfile.ZIP_DEFLATED,  # 8
    getattr(zipfile, "ZIP_BZIP2", 12),  # 12
    getattr(zipfile, "ZIP_LZMA", 14),   # 14
}


def _can_extract_zip_natively(archive: Path) -> tuple[bool, str]:
    """Check if Python's zipfile can decompress this archive without NotImplementedError."""
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.compress_type not in _ZIP_SUPPORTED_COMPRESSIONS:
                    return False, f"unsupported compression type {info.compress_type}"
                if (info.flag_bits & 0x1) and (info.compress_type == 99 or (info.flag_bits & 0x40)):
                    return False, "unsupported encryption method (AES)"
        return True, ""
    except NotImplementedError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def _extract_external(
    archive: Path,
    dest: Path,
    password: str = "",
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
    prefer_7z: bool = False,
) -> None:
    if cancelled and cancelled():
        raise ExtractionCancelled("Cancelled")

    dest.mkdir(parents=True, exist_ok=True)
    _check_zip_slip(archive, dest)

    tar_exe = _find_tar()
    exe_7z = _find_7z()
    is_rar = archive.name.lower().endswith(".rar")
    unrar_exe = _find_unrar() if is_rar else None

    tools_to_try: list[tuple[str, list[str]]] = []

    def make_tar_args(exe: str) -> list[str]:
        args = [exe]
        if password:
            args.extend(["--passphrase", password])
        args.extend(["-xf", str(archive), "-C", str(dest)])
        return args

    def make_7z_args(exe: str) -> list[str]:
        args = [exe, "x", str(archive), f"-o{dest}", "-y"]
        args.append(f"-p{password}" if password else "-p-")
        return args

    def make_unrar_args(exe: str) -> list[str]:
        args = [exe, "x", "-y"]
        args.append(f"-p{password}" if password else "-p-")
        args.extend([str(archive), str(dest) + os.sep])
        return args

    if is_rar:
        # RAR archives: prioritize 7z and unrar over bsdtar (bsdtar has limited/no RAR5 support)
        if exe_7z:
            tools_to_try.append(("7-Zip", make_7z_args(exe_7z)))
        if unrar_exe:
            tools_to_try.append(("UnRAR", make_unrar_args(unrar_exe)))
        if tar_exe:
            tools_to_try.append(("tar", make_tar_args(tar_exe)))
    elif prefer_7z:
        if exe_7z:
            tools_to_try.append(("7-Zip", make_7z_args(exe_7z)))
        if tar_exe:
            tools_to_try.append(("tar", make_tar_args(tar_exe)))
    else:
        if tar_exe:
            tools_to_try.append(("tar", make_tar_args(tar_exe)))
        if exe_7z:
            tools_to_try.append(("7-Zip", make_7z_args(exe_7z)))
        if unrar_exe:
            tools_to_try.append(("UnRAR", make_unrar_args(unrar_exe)))

    if not tools_to_try:
        raise ExtractionError(
            "No external extraction tool available (need tar.exe, 7z.exe, or 7za.exe)"
        )

    last_error = ""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    for tool_name, args in tools_to_try:
        if cancelled and cancelled():
            raise ExtractionCancelled("Cancelled")
        if progress:
            progress(0, 1)
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flags,
            )
            while True:
                if cancelled and cancelled():
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise ExtractionCancelled("Cancelled")
                try:
                    stdout, stderr = proc.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue

            if proc.returncode == 0:
                if progress:
                    progress(1, 1)
                return
            err_msg = stderr.strip() or stdout.strip() or f"exit code {proc.returncode}"
            last_error = f"{tool_name} failed: {err_msg}"
            log.warning(
                "External extraction with %s failed: %s; trying next available tool",
                tool_name,
                err_msg,
            )
        except ExtractionCancelled:
            raise
        except Exception as exc:
            last_error = f"{tool_name} error: {exc}"
            log.warning("External extraction error with %s: %s", tool_name, exc)

    err_lower = last_error.lower()
    is_corrupted = any(
        kw in err_lower
        for kw in (
            "unrecognized archive",
            "not recognized",
            "can not open",
            "cannot open",
            "corrupt",
            "damaged",
            "data error",
            "crc failed",
            "bad zip",
        )
    )
    if is_corrupted:
        raise ExtractionError(f"Corrupted archive: {last_error}")
    raise ExtractionError(last_error or "Archive extraction failed with external tools")


def extract(
    archive: Path,
    dest: Path,
    password: str = "",
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
) -> Path:
    """Extract ``archive`` into ``dest`` and verify the result. Returns ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if zipfile.is_zipfile(archive) or name.endswith(".zip"):
        _extract_zip(archive, dest, password, progress, cancelled)
    elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
        _extract_tar(archive, dest, progress, cancelled)
    elif name.endswith((".7z", ".rar")):
        _extract_7z(archive, dest, password, progress, cancelled)
    else:
        try:
            _extract_external(archive, dest, password, progress, cancelled)
        except (ExtractionCancelled, ExtractionError):
            raise
        except Exception as exc:
            raise ExtractionError(f"Unsupported or corrupted archive ({exc})") from exc
    if not any(dest.iterdir()):
        raise ExtractionError("Extraction produced no files")
    return dest


def _extract_zip(
    archive: Path,
    dest: Path,
    password: str = "",
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
) -> None:
    can_native, reason = _can_extract_zip_natively(archive)
    if not can_native:
        log.info(
            "Archive %s requires external extractor (%s); falling back to tar/7z",
            archive.name,
            reason,
        )
        _extract_external(archive, dest, password, progress, cancelled, prefer_7z=False)
        return

    try:
        with zipfile.ZipFile(archive) as zf:
            pwd = password.encode() if password else None
            infos = zf.infolist()
            total = sum(i.file_size for i in infos) or 1
            done = 0
            for info in infos:
                if cancelled and cancelled():
                    raise ExtractionCancelled("Cancelled")
                target = _safe_target(dest, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                # Reading through ZipFile.open verifies the CRC at end of stream.
                with zf.open(info, pwd=pwd) as src, open(target, "wb") as out:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
                if target.stat().st_size != info.file_size:
                    raise ExtractionError(f"Size mismatch for {info.filename}")
    except (ExtractionCancelled, ExtractionError):
        raise
    except NotImplementedError as exc:
        log.info(
            "ZipFile encountered unsupported compression during extraction (%s); falling back to external tool",
            exc,
        )
        _extract_external(archive, dest, password, progress, cancelled, prefer_7z=False)
    except zipfile.BadZipFile as exc:
        log.warning("zipfile reported BadZipFile (%s); attempting fallback to external tool", exc)
        try:
            _extract_external(archive, dest, password, progress, cancelled, prefer_7z=False)
        except (ExtractionCancelled, ExtractionError):
            raise
        except Exception:
            raise ExtractionError(f"Corrupted archive: {exc}") from exc
    except RuntimeError as exc:  # wrong/missing password
        raise ExtractionError(f"Cannot extract: {exc}") from exc
    except OSError as exc:
        raise ExtractionError(f"Write error during extraction: {exc}") from exc


def _extract_tar(
    archive: Path,
    dest: Path,
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
) -> None:
    try:
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            total = len(members) or 1
            for n, m in enumerate(members, 1):
                if cancelled and cancelled():
                    raise ExtractionCancelled("Cancelled")
                _safe_target(dest, m.name)
                if m.issym() or m.islnk():
                    continue
                tf.extract(m, dest, filter="data") if hasattr(tarfile, "data_filter") else tf.extract(m, dest)
                if progress:
                    progress(n, total)
    except (ExtractionCancelled, ExtractionError):
        raise
    except (tarfile.TarError, OSError) as exc:
        log.warning("tarfile extraction failed (%s); trying external extractor", exc)
        try:
            _extract_external(archive, dest, "", progress, cancelled, prefer_7z=False)
        except (ExtractionCancelled, ExtractionError):
            raise
        except Exception:
            raise ExtractionError(f"Corrupted archive: {exc}") from exc


def _extract_7z(
    archive: Path,
    dest: Path,
    password: str = "",
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
) -> None:
    _extract_external(archive, dest, password, progress, cancelled, prefer_7z=True)


def flatten_single_folder(dest: Path) -> Path:
    """If the archive contained exactly one top-level folder, return that folder."""
    entries = [e for e in dest.iterdir() if not e.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return dest
