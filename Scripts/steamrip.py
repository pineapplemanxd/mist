"""SteamRip source plugin for OpenSteam.

Bridges the SteamRip catalog and file-host resolvers from Scripts/SteamRip.lua.
Provides game browsing, search, metadata, and mirror link resolution.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path
from typing import Any

from Core.logger import get_logger
from Core.sources import CatalogItem, DownloadSpec, SearchPage, SourceBase, SourceError

log = get_logger(__name__)

BASE_URL = "https://steamrip.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_UNITS = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4}


def _parse_size(text: str) -> int:
    m = re.search(r"([\d.]+)\s*([kmgt]?b)", text or "", re.I)
    if m:
        val = float(m.group(1))
        unit = m.group(2).lower()
        return int(val * _UNITS.get(unit, 1))
    return 0


def _clean_title(raw_title: str) -> tuple[str, str]:
    """Clean 'Game Free Download (v1.2.3)' -> ('Game', 'v1.2.3')."""
    version = ""
    v_match = re.search(r"\((v?[\d.]+[^)]*)\)", raw_title, re.I)
    if v_match:
        version = v_match.group(1).strip()
    title = re.sub(r"\s*Free Download.*$", "", raw_title, flags=re.I).strip()
    return title or raw_title, version


class SteamRipSource(SourceBase):
    id = "steamrip"
    name = "SteamRip"
    color = "#8b5cf6"
    can_download = True
    priority = 3

    def _fetch_html(self, url: str) -> str:
        try:
            raw = self.http_get(url, headers=HEADERS, timeout=14)
            return raw.decode("utf-8", errors="replace")
        except SourceError as exc:
            if "404" in str(exc):
                return ""
            raise
        except Exception as exc:
            raise SourceError(f"Failed to connect to SteamRip: {exc}") from exc

    def genres(self) -> list[str]:
        return [
            "Action", "Adventure", "Anime", "Horror", "Multiplayer",
            "Open World", "Racing", "RPG", "Sci-Fi", "Shooter",
            "Simulation", "Sports", "Strategy", "Survival", "VR"
        ]

    def search(self, query: str = "", genre: str = "", page: int = 1, page_size: int = 24) -> SearchPage:
        if query:
            q_enc = urllib.parse.quote_plus(query.replace(":", ""))
            if page > 1:
                url = f"{BASE_URL}/page/{page}/?s={q_enc}"
            else:
                url = f"{BASE_URL}/?s={q_enc}"
        elif genre:
            slug = genre.lower().replace(" ", "-")
            if page > 1:
                url = f"{BASE_URL}/category/{slug}/page/{page}/"
            else:
                url = f"{BASE_URL}/category/{slug}/"
        else:
            # Empty query: search with empty string returns standard latest game cards with pagination
            url = f"{BASE_URL}/page/{page}/?s=" if page > 1 else f"{BASE_URL}/?s="

        page_html = self._fetch_html(url)
        if not page_html:
            return SearchPage(items=[], has_more=False)

        items: list[CatalogItem] = []
        seen_slugs: set[str] = set()

        # Extract card elements flexibly across search, category, and homepage layouts
        card_chunks = re.findall(
            r'(<(?:div|li)[^>]*class=["\'][^"\']*(?:slide|post-item)[^"\']*["\'][^>]*>.*?(?=<(?:div|li)[^>]*class=["\'][^"\']*(?:slide|post-item)[^"\']*["\']|<div class=["\']pagination|$))',
            page_html,
            re.DOTALL
        )
        if not card_chunks:
            card_chunks = re.findall(
                r'(<div[^>]*data-back=["\'][^"\']+["\'][^>]*>.*?)(?=<div[^>]*data-back=["\']|$)',
                page_html,
                re.DOTALL
            )

        for chunk in card_chunks:
            # 1. Link
            link_m = (
                re.search(r'href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*all-over-thumb-link', chunk)
                or re.search(r'class=["\'][^"\']*all-over-thumb-link[^"\']*["\'][^>]*href=["\']([^"\']+)["\']', chunk)
                or re.search(r'<h2[^>]*class=["\'][^"\']*(?:thumb-title|the-post-title|post-title)[^"\']*["\'][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\']', chunk)
                or re.search(r'href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*post-thumb', chunk)
            )
            if not link_m:
                continue
            link = link_m.group(1).strip()
            if link.startswith("#") or "category/" in link or link == BASE_URL or link == f"{BASE_URL}/":
                continue

            # Build full link
            if link.startswith("http"):
                store_url = link
            else:
                store_url = f"{BASE_URL}/{link.lstrip('/')}"

            slug_match = re.search(r'/([^/?#]+)/?$', store_url)
            slug = slug_match.group(1) if slug_match else ""
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # 2. Title
            title_m = (
                re.search(r'<span[^>]*class=["\']screen-reader-text["\'][^>]*>(.*?)</span>', chunk)
                or re.search(r'aria-label=["\']([^"\']+)["\']', chunk)
                or re.search(r'<h2[^>]*class=["\'][^"\']*(?:thumb-title|the-post-title|post-title)[^"\']*["\'][^>]*>(?:<a[^>]*>)?([^<]+)', chunk)
            )
            if not title_m:
                continue
            raw_title = html.unescape(title_m.group(1).strip())
            if not raw_title or len(raw_title) < 2:
                continue
            title, detected_ver = _clean_title(raw_title)

            # 3. Cover URL
            cov_m = (
                re.search(r'data-back=["\']([^"\']+)["\']', chunk)
                or re.search(r'data-src=["\']([^"\']+)["\']', chunk)
                or re.search(r'src=["\']([^"\']*(?:uploads|thumbnails)[^"\']*)["\']', chunk)
            )
            cover = cov_m.group(1).strip() if cov_m else ""
            if cover and not cover.startswith("http"):
                cover = f"{BASE_URL}/{cover.lstrip('/')}"

            # 4. Meta line (Year | Size)
            meta_m = re.search(r'<span[^>]*class=["\'][^"\']*game-meta-line[^"\']*["\']>([^<]*)</span>', chunk)
            meta = meta_m.group(1).strip() if meta_m else ""
            year = ""
            size_str = ""
            if meta:
                meta_parts = [p.strip() for p in meta.split("|")]
                for part in meta_parts:
                    if re.match(r"^\d{4}$", part):
                        year = part
                    elif any(u in part.upper() for u in ("GB", "MB", "KB")):
                        size_str = part

            size_bytes = _parse_size(size_str)
            item = CatalogItem(
                source=self.id,
                id=slug,
                title=title,
                cover_url=cover,
                size_bytes=size_bytes,
                release_date=year,
                version=detected_ver,
                store_url=store_url,
                extra={"slug": slug, "raw_title": raw_title, "size_str": size_str},
            )
            items.append(item)

        has_more = bool(
            re.search(r'class=["\'][^"\']*\bnext\b[^"\']*page-numbers', page_html)
            or re.search(r'class=["\'][^"\']*page-numbers[^"\']*\bnext\b', page_html)
        )
        return SearchPage(items=items, has_more=has_more)

    def details(self, item: CatalogItem) -> CatalogItem:
        if not item.store_url:
            item.store_url = f"{BASE_URL}/{item.id}/"
        page_html = self._fetch_html(item.store_url)
        if not page_html:
            return item

        # 1. Version
        v_m = re.search(r'<strong>Version</strong>\s*:\s*([^<]+)', page_html)
        if v_m:
            item.version = html.unescape(v_m.group(1).strip())

        # 2. Size
        s_m = re.search(r'<strong>Game Size:?\s*</strong>\s*([^<]+)', page_html)
        if s_m:
            size_display = s_m.group(1).strip()
            item.size_bytes = _parse_size(size_display)

        # 3. Description
        desc_m = re.search(r'<div[^>]*class=["\']entry-content[^"\']*["\'][^>]*>(.*?)</div>', page_html, re.DOTALL)
        if desc_m:
            desc_html = desc_m.group(1)
            # Find first substantive paragraph
            for p in re.findall(r'<p>(.*?)</p>', desc_html, re.DOTALL):
                clean_p = re.sub(r'<[^>]+>', '', p).strip()
                if len(clean_p) > 40 and not clean_p.lower().startswith("how to"):
                    item.description = html.unescape(clean_p)
                    break

        # 4. Screenshots & Hero
        shots = re.findall(r'<img[^>]+src=["\']([^"\']*(?:wp-content/uploads)[^"\']*)["\']', page_html)
        if shots:
            clean_shots = [s if s.startswith("http") else f"{BASE_URL}/{s.lstrip('/')}" for s in shots if not s.endswith(".svg")]
            item.screenshots = clean_shots[:8]
            if clean_shots:
                item.hero_url = clean_shots[0]

        # 5. Extract Mirrors (Gofile, Buzzheavier, Pixeldrain, MegaDB, Mediafire, etc.)
        mirrors = []
        host_re = re.compile(r'<a[^>]+href=["\']([^"\']*(?:buzzheavier|gofile|pixeldrain|megadb|megaup|mediafire|vikingfile|qiwi)[^"\']*)["\'][^>]*>(.*?)</a>', re.I)
        for m in host_re.finditer(page_html):
            href, txt = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if href.startswith("//"):
                href = f"https:{href}"
            elif not href.startswith("http"):
                href = f"https://{href}"

            # Host name identification
            host_name = "Download"
            h_lower = href.lower()
            if "gofile" in h_lower:
                host_name = "Gofile"
            elif "buzzheavier" in h_lower:
                host_name = "Buzzheavier"
            elif "pixeldrain" in h_lower:
                host_name = "Pixeldrain"
            elif "megadb" in h_lower:
                host_name = "MegaDB"
            elif "megaup" in h_lower:
                host_name = "MegaUp"
            elif "mediafire" in h_lower:
                host_name = "Mediafire"
            elif "vikingfile" in h_lower:
                host_name = "VikingFile"

            mirrors.append({"name": host_name, "url": href})

        if mirrors:
            item.extra["mirrors"] = mirrors
        return item

    def resolve_download(self, item: CatalogItem, temp_dir: Path) -> DownloadSpec:
        mirrors = item.extra.get("mirrors") or []
        if not mirrors:
            # Re-fetch details to extract mirrors
            item = self.details(item)
            mirrors = item.extra.get("mirrors") or []

        if not mirrors:
            raise SourceError(f"No active download mirrors found for {item.title} on SteamRip.")

        # Pick the best mirror: Pixeldrain or Buzzheavier or Gofile
        chosen = None
        for pref in ("Pixeldrain", "Buzzheavier", "Gofile", "MegaDB", "Mediafire"):
            for m in mirrors:
                if pref.lower() in m["name"].lower():
                    chosen = m
                    break
            if chosen:
                break
        if not chosen:
            chosen = mirrors[0]

        url = chosen["url"]
        log.info("SteamRip resolving mirror %s: %s", chosen["name"], url)

        # Pixeldrain direct API resolution
        if "pixeldrain.com/u/" in url:
            file_id = url.split("/u/")[-1].split("?")[0].split("/")[0]
            direct_url = f"https://pixeldrain.com/api/file/{file_id}"
            return DownloadSpec(
                url=direct_url,
                filename=f"{item.title}-SteamRip.zip",
                size_bytes=item.size_bytes,
                headers={"Referer": BASE_URL},
            )

        # Default fallback
        return DownloadSpec(
            url=url,
            filename=f"{item.title}-SteamRip.zip",
            size_bytes=item.size_bytes,
            headers={"Referer": BASE_URL},
        )
