"""Generic JSON catalog source — add a store without writing Python.

Every ``Scripts/catalogs/*.json`` file becomes its own store tab. The file can
either embed the game list (``"games": [...]``) or point to a remote JSON
document with the same structure (``"catalog_url": "https://..."``).

See ``Scripts/catalogs/example_catalog.json`` and ``Scripts/README.md`` for the
full schema.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from Core.logger import get_logger
from Core.sources import CatalogItem, DownloadSpec, SearchPage, SourceBase, SourceError

log = get_logger(__name__)

CATALOG_DIR = Path(__file__).resolve().parent / "catalogs"
_UNITS = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4}


def parse_size(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    m = re.match(r"\s*([\d.]+)\s*([kmgt]?b)\s*$", str(value or ""), re.I)
    return int(float(m.group(1)) * _UNITS[m.group(2).lower()]) if m else 0


class JsonCatalogSource(SourceBase):
    id = "json-catalog"          # replaced per catalog file
    name = "JSON Catalog"
    CACHE_TTL = 15 * 60

    def __init__(self, config=None, manifest: dict | None = None, path: Path | None = None):
        super().__init__(config)
        self.manifest = manifest or {}
        self.path = path
        self.id = str(self.manifest.get("id") or (path.stem if path else "json-catalog")).lower()
        self.name = self.manifest.get("name") or self.id
        self.color = self.manifest.get("color", "#0ea5e9")
        self.priority = int(self.manifest.get("priority", 50))
        self.can_download = bool(self.manifest.get("can_download", True))
        self._cache: list[dict] | None = None
        self._cache_time = 0.0

    @classmethod
    def create_all(cls, config=None) -> list["JsonCatalogSource"]:
        sources = []
        if not CATALOG_DIR.is_dir():
            return sources
        for path in sorted(CATALOG_DIR.glob("*.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.error("Invalid catalog file %s: %s", path.name, exc)
                continue
            if not manifest.get("enabled", True):
                continue
            sources.append(cls(config, manifest, path))
        return sources

    # ----------------------------------------------------------------- data
    def _games(self) -> list[dict]:
        if self._cache is not None and time.time() - self._cache_time < self.CACHE_TTL:
            return self._cache
        games = list(self.manifest.get("games") or [])
        url = self.manifest.get("catalog_url")
        if url:
            data = self.http_json(url, headers=self.manifest.get("headers") or {})
            remote = data.get("games") if isinstance(data, dict) else data
            if not isinstance(remote, list):
                raise SourceError("Remote catalog has no 'games' list")
            games += remote
        self._cache, self._cache_time = games, time.time()
        return games

    def _to_item(self, g: dict) -> CatalogItem:
        return CatalogItem(
            source=self.id,
            id=str(g.get("id") or g.get("title")),
            title=g.get("title", "Untitled"),
            description=g.get("description", ""),
            short_description=g.get("short_description") or (g.get("description", "")[:220]),
            cover_url=g.get("cover", ""),
            hero_url=g.get("hero", ""),
            size_bytes=parse_size(g.get("size_bytes") or g.get("size")),
            genres=list(g.get("genres") or []),
            developer=g.get("developer", ""),
            publisher=g.get("publisher", ""),
            release_date=str(g.get("release_date", "")),
            version=str(g.get("version", "")),
            screenshots=list(g.get("screenshots") or []),
            system_requirements=g.get("system_requirements", ""),
            store_url=g.get("store_url", ""),
            extra={k: g.get(k) for k in ("download_url", "filename", "sha256", "password", "headers", "featured")},
        )

    # ------------------------------------------------------------- catalog
    def genres(self) -> list[str]:
        return sorted({x for g in self._games() for x in (g.get("genres") or [])})

    def featured(self) -> list[CatalogItem]:
        games = self._games()
        picked = [g for g in games if g.get("featured")] or games[:4]
        return [self._to_item(g) for g in picked[:8]]

    def search(self, query: str = "", genre: str = "", page: int = 1, page_size: int = 24) -> SearchPage:
        q = query.lower().strip()
        matches = [g for g in self._games()
                   if (not q or q in g.get("title", "").lower())
                   and (not genre or genre in (g.get("genres") or []))]
        start = (page - 1) * page_size
        return SearchPage([self._to_item(g) for g in matches[start:start + page_size]],
                          start + page_size < len(matches), len(matches))

    def resolve_download(self, item: CatalogItem, temp_dir: Path) -> DownloadSpec:
        url = item.extra.get("download_url")
        if not url:
            raise SourceError("This catalog entry has no download_url")
        filename = item.extra.get("filename") or url.split("?")[0].rstrip("/").split("/")[-1] or f"{item.id}.zip"
        return DownloadSpec(
            url=url, filename=filename, size_bytes=item.size_bytes,
            headers=item.extra.get("headers") or {}, sha256=item.extra.get("sha256") or "",
            archive_password=item.extra.get("password") or "",
        )
