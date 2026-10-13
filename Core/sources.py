"""Store source plugin API and loader.

Every ``*.py`` file in the ``Scripts/`` folder (not starting with ``_``) is
imported and scanned for subclasses of :class:`SourceBase`. See
``Scripts/README.md`` for a full guide on writing a source.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logger import get_logger
from .paths import SCRIPTS_DIR, get_scripts_dirs

# Import anchors for PyInstaller static analysis and standalone bundle inclusion
try:
    import asyncio
except ImportError:
    pass

try:
    import websockets
except ImportError:
    pass

log = get_logger(__name__)

USER_AGENT = "OpenSteamLibrary/1.0 (+local game library manager)"


@dataclass
class CatalogItem:
    """A game listed by a store source."""
    source: str
    id: str
    title: str
    description: str = ""
    short_description: str = ""
    cover_url: str = ""
    hero_url: str = ""
    size_bytes: int = 0
    genres: list[str] = field(default_factory=list)
    developer: str = ""
    publisher: str = ""
    release_date: str = ""
    version: str = ""
    screenshots: list[str] = field(default_factory=list)
    system_requirements: str = ""   # plain text or simple HTML
    store_url: str = ""             # used for browse-only sources
    extra: dict[str, Any] = field(default_factory=dict)

    def to_library_record(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "source_id": self.id,
            "cover_url": self.cover_url,
            "hero_url": self.hero_url,
            "description": self.description or self.short_description,
            "developer": self.developer,
            "publisher": self.publisher,
            "release_date": self.release_date,
            "genres": self.genres,
            "system_requirements": self.system_requirements,
            "screenshots": self.screenshots,
            "version": self.version,
            "size_bytes": self.size_bytes,
        }


@dataclass
class DownloadSpec:
    """What the downloader needs to fetch a game archive."""
    url: str                                    # http(s):// or file://
    filename: str                               # archive file name in the temp folder
    headers: dict[str, str] = field(default_factory=dict)
    size_bytes: int = 0                         # expected size if known (for disk checks)
    sha256: str = ""                            # optional integrity check
    archive_password: str = ""                  # optional, for encrypted zips


@dataclass
class SearchPage:
    items: list[CatalogItem]
    has_more: bool
    total: int = -1


class SourceError(Exception):
    """Raised by sources for user-visible failures."""


class SourceBase:
    """Base class for store sources. Override what you need."""

    id: str = ""                 # unique, stable, lowercase identifier
    name: str = ""               # display name
    color: str = "#5b8def"       # badge colour
    can_download: bool = True    # False = browse-only (opens store_url)
    priority: int = 100          # lower sorts first in the source tabs

    def __init__(self, config=None):
        self.config = config

    # Catalog ---------------------------------------------------------------
    def genres(self) -> list[str]:
        return []

    def featured(self) -> list[CatalogItem]:
        return []

    def search(self, query: str = "", genre: str = "", page: int = 1, page_size: int = 24) -> SearchPage:
        raise NotImplementedError

    def details(self, item: CatalogItem) -> CatalogItem:
        """Return the item with full details (description, screenshots, requirements)."""
        return item

    # Download pipeline ---------------------------------------------------------
    def resolve_download(self, item: CatalogItem, temp_dir: Path) -> DownloadSpec:
        raise SourceError(f"{self.name} does not support downloads")

    def find_executable(self, item: CatalogItem, install_dir: Path) -> str | None:
        """Optionally return the game executable after extraction (else auto-detect)."""
        return None

    # Helpers available to scripts --------------------------------------------------
    def setting(self, key: str, default: Any = None) -> Any:
        if self.config is None:
            return default
        return self.config.get(f"source.{self.id}.{key}", default)

    @staticmethod
    def http_get(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 20) -> bytes:
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - surface any network error uniformly
            raise SourceError(f"Request failed: {exc}") from exc

    @classmethod
    def http_json(cls, url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 20) -> Any:
        raw = cls.http_get(url, params, {"Accept": "application/json", **(headers or {})}, timeout)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise SourceError(f"Invalid JSON from {url}") from exc


class SourceRegistry:
    def __init__(self, config=None, scripts_dir: Path | list[Path] | None = None):
        self.config = config
        if scripts_dir is None:
            self.scripts_dirs = get_scripts_dirs()
        elif isinstance(scripts_dir, (list, tuple)):
            self.scripts_dirs = list(scripts_dir)
        else:
            self.scripts_dirs = [scripts_dir]
            for extra in get_scripts_dirs():
                if extra not in self.scripts_dirs:
                    self.scripts_dirs.append(extra)
        self.scripts_dir = self.scripts_dirs[0] if self.scripts_dirs else SCRIPTS_DIR
        self._sources: dict[str, SourceBase] = {}
        self.errors: list[str] = []

    def load(self) -> None:
        self._sources.clear()
        self.errors.clear()
        seen_files: set[str] = set()

        for s_dir in self.scripts_dirs:
            if not s_dir.is_dir():
                continue
            app_dir = str(s_dir.parent)
            if app_dir not in sys.path:
                sys.path.insert(0, app_dir)
            for path in sorted(s_dir.glob("*.py")):
                if path.name.startswith("_") or path.stem in seen_files:
                    continue
                seen_files.add(path.stem)
                mod_name = f"opensteam_source_{path.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, path)
                    module = importlib.util.module_from_spec(spec)
                    assert spec.loader is not None
                    spec.loader.exec_module(module)
                except Exception as exc:  # noqa: BLE001 - a broken script must not crash the app
                    # Fallback to direct module import if dynamic file loading fails
                    module = None
                    try:
                        module = importlib.import_module(f"Scripts.{path.stem}")
                    except Exception:
                        module = None
                    if module is None:
                        msg = f"{path.name}: {exc}"
                        log.exception("Failed to load source script %s", path.name)
                        self.errors.append(msg)
                        continue
                for obj in vars(module).values():
                    if isinstance(obj, type) and issubclass(obj, SourceBase) and obj is not SourceBase and obj.id:
                        if obj.__module__ not in (mod_name, getattr(module, "__name__", "")):
                            continue  # imported, not defined here
                        try:
                            instances = obj.create_all(self.config) if hasattr(obj, "create_all") else [obj(self.config)]
                        except Exception as exc:  # noqa: BLE001
                            log.exception("Failed to initialise source %s", obj.__name__)
                            self.errors.append(f"{path.name}: {exc}")
                            continue
                        for inst in instances:
                            if inst.id in self._sources:
                                log.warning("Duplicate source id %r in %s ignored", inst.id, path.name)
                                continue
                            self._sources[inst.id] = inst
                            log.info("Loaded source %s (%s)", inst.name, inst.id)

        # Ensure essential built-in sources are registered even if filesystem discovery in frozen mode encounters issues
        if "ankergames" not in self._sources:
            try:
                from Scripts.ankergames import AnkerGamesSource
                inst = AnkerGamesSource(self.config)
                self._sources[inst.id] = inst
                self.errors = [e for e in self.errors if not e.startswith("ankergames.py:")]
                log.info("Loaded built-in fallback source %s (%s)", inst.name, inst.id)
            except Exception as exc:
                log.debug("Fallback loading for ankergames failed: %s", exc)


    def all(self) -> list[SourceBase]:
        return sorted(self._sources.values(), key=lambda s: (s.priority, s.name.lower()))

    def get(self, source_id: str) -> SourceBase | None:
        return self._sources.get(source_id)

    def badge_color(self, source_id: str) -> str:
        src = self._sources.get(source_id)
        if src:
            return src.color
        return BUILTIN_BADGES.get(source_id, ("", "#6b7280"))[1]

    def display_name(self, source_id: str) -> str:
        src = self._sources.get(source_id)
        if src:
            return src.name
        return BUILTIN_BADGES.get(source_id, (source_id.title(), ""))[0] or source_id


# Badges for library entries that don't come from a store script.
BUILTIN_BADGES = {
    "steam": ("Steam", "#2a6fb0"),
    "manual": ("Manual", "#6b7280"),
}

# Static import anchors for PyInstaller static analysis to guarantee bundling of built-in scripts
try:
    import Scripts.ankergames
    import Scripts.json_catalog_source
except ImportError:
    pass

