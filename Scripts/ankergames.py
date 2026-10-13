"""Anker Games catalog source.

Extracts game catalog, search results, genres, sizes, and metadata
directly from ankergames.net. Download resolution automates the fast-fetch
flow from Scripts/AnkerGames.lua via Chromium DevTools Protocol (Edge/Chrome).
"""
from __future__ import annotations

try:
    import asyncio
except ImportError:
    asyncio = None  # type: ignore
import html
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from Core.logger import get_logger
from Core.sources import CatalogItem, DownloadSpec, SearchPage, SourceBase, SourceError

log = get_logger(__name__)

BASE_URL = "https://ankergames.net"
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


def _find_browser() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def _resolve_cdp_async(game_url: str, temp_dir: Path, timeout: float = 45.0) -> tuple[str, str]:
    if asyncio is None:
        raise SourceError("Missing dependency 'asyncio' required for Anker Games verification.")
    try:
        import websockets
    except ImportError:
        raise SourceError("Missing dependency 'websockets'. Run: pip install websockets")

    browser_exe = _find_browser()
    if not browser_exe:
        raise SourceError(
            "Anker Games downloads require a Chromium browser (Edge or Chrome) for verification.\n"
            "Please ensure Microsoft Edge or Google Chrome is installed."
        )

    user_data_dir = tempfile.mkdtemp(prefix="opensteam_cdp_")
    # Pre-populate First Run marker and disable sync in Local State to prevent Edge/Chrome FRE prompts
    try:
        (Path(user_data_dir) / "First Run").touch()
        (Path(user_data_dir) / "Local State").write_text(
            json.dumps({
                "browser": {"has_seen_welcome_page": True},
                "fre": {"has_user_seen_fre": True},
                "signin": {"allowed": False},
                "sync": {"has_setup_completed": True},
            }),
            encoding="utf-8"
        )
        def_dir = Path(user_data_dir) / "Default"
        def_dir.mkdir(parents=True, exist_ok=True)
        (def_dir / "Preferences").write_text(
            json.dumps({
                "signin": {"allowed": False},
                "sync": {"has_setup_completed": True},
                "edge": {"sync": {"has_setup_completed": True, "user_choice_made": True}},
            }),
            encoding="utf-8"
        )
    except Exception:
        pass

    port = _free_port()
    cmd = [
        browser_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-fre",
        "--disable-sync",
        "--disable-sync-preferences",
        "--disable-features=msFirstRun,msSignInPromo,EdgeSignin,msHub,msEdgeShowWelcomePage,msImplicitSignin,msSmartScreenProtection,msSearchEngineChoiceScreen",
        "--disable-search-engine-choice-screen",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--metrics-recording-only",
        "--no-service-autorun",
        "--password-store=basic",
        "--disable-blink-features=AutomationControlled",
        "--window-position=-2000,-2000",
        "--window-size=1280,800",
        "about:blank",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(cmd, creationflags=creationflags)

    try:
        ws_url = None
        for _ in range(35):
            await asyncio.sleep(0.2)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                    ver_data = json.loads(r.read().decode("utf-8"))
                    ws_url = ver_data.get("webSocketDebuggerUrl")
                    if ws_url:
                        break
            except Exception:
                pass

        if not ws_url:
            raise SourceError("Failed to communicate with browser for Anker Games verification.")

        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "about:blank"}}))
            res = json.loads(await ws.recv())
            target_id = res["result"]["targetId"]

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as r:
                targets = json.loads(r.read().decode("utf-8"))
                page_ws = next((t["webSocketDebuggerUrl"] for t in targets if t["id"] == target_id), None)

            if not page_ws:
                raise SourceError("Failed to open browser tab for Anker Games verification.")

            async with websockets.connect(page_ws) as page_conn:
                msg_id = 1

                async def send(method, params=None):
                    nonlocal msg_id
                    msg_id += 1
                    await page_conn.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
                    return msg_id

                await send("Page.enable")
                await send("Network.enable")
                await send("Browser.setDownloadBehavior", {
                    "behavior": "allowAndName",
                    "downloadPath": str(temp_dir),
                    "eventsEnabled": True,
                })
                await send("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                })

                await send("Page.navigate", {"url": game_url})

                start_t = time.time()
                injected = False
                download_url_found = None
                filename_found = None

                while time.time() - start_t < timeout:
                    try:
                        raw = await asyncio.wait_for(page_conn.recv(), timeout=12)
                    except asyncio.TimeoutError:
                        continue
                    msg = json.loads(raw)
                    method = msg.get("method")

                    should_inject = (method in ("Page.loadEventFired", "Page.domContentEventFired") or (time.time() - start_t > 2.5))
                    if should_inject and not injected:
                        js = """
                        (async function() {
                            let match = document.body.innerHTML.match(/generateDownloadUrl\\(\\s*(\\d+)\\s*\\)/);
                            if (match && match[1]) {
                                let downloadId = match[1];
                                let token = document.querySelector('meta[name="csrf-token"]')?.content || '';
                                try {
                                    let res = await fetch('/generate-download-url/' + downloadId, {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                            'X-CSRF-TOKEN': token,
                                            'X-Requested-With': 'XMLHttpRequest'
                                        },
                                        body: JSON.stringify({})
                                    });
                                    let data = await res.json();
                                    if (data && data.download_url) {
                                        window.location.href = data.download_url;
                                    }
                                } catch (e) {
                                    console.error(e);
                                }
                            }
                        })();
                        """
                        await send("Runtime.evaluate", {"expression": js, "awaitPromise": True})
                        injected = True
                    elif method in ("Browser.downloadWillBegin", "Page.downloadWillBegin"):
                        download_url_found = msg.get("params", {}).get("url")
                        filename_found = msg.get("params", {}).get("suggestedFilename")
                        break
                    elif method == "Network.responseReceived":
                        resp = msg.get("params", {}).get("response", {})
                        headers = resp.get("headers", {})
                        cd = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
                        if "attachment" in cd.lower() and resp.get("url"):
                            download_url_found = resp.get("url")
                            fn_m = re.search(r'filename=["\']?([^"\';]+)["\']?', cd)
                            if fn_m:
                                filename_found = fn_m.group(1).strip()
                            break

                if not download_url_found:
                    raise SourceError("Anker Games verification timed out. Please try again.")

                return download_url_found, filename_found or "game.zip"
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(user_data_dir, ignore_errors=True)


class AnkerGamesSource(SourceBase):
    id = "ankergames"
    name = "Anker Games"
    color = "#10b981"
    can_download = True
    priority = 1  # Primary source

    def _fetch_html(self, path_or_url: str) -> str:
        url = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
        try:
            raw = self.http_get(url, headers=HEADERS, timeout=12)
            return raw.decode("utf-8", errors="replace")
        except SourceError as exc:
            if "404" in str(exc):
                log.info("AnkerGames end of pagination: %s", url)
                return ""
            log.warning("AnkerGames request failed: %s (%s)", url, exc)
            raise
        except Exception as exc:
            log.warning("AnkerGames request failed: %s (%s)", url, exc)
            raise SourceError(f"Failed to connect to Anker Games: {exc}") from exc

    def _parse_articles(self, page_html: str) -> list[CatalogItem]:
        items: list[CatalogItem] = []
        articles = re.findall(r'<article[^>]*>(.*?)</article>', page_html, re.DOTALL)
        for art in articles:
            link_m = re.search(r'href=["\'](https?://ankergames\.net)?/game/([^"\']+)["\']', art)
            if not link_m:
                continue
            slug = link_m.group(2).strip("/")
            game_url = f"{BASE_URL}/game/{slug}"

            title_m = re.search(r'<h3[^>]*title=["\']([^"\']+)["\']', art) or re.search(r'title=["\']([^"\']+)["\']', art)
            title = html.unescape(title_m.group(1).strip()) if title_m else slug.replace("-", " ").title()

            img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', art) or re.search(r'<source[^>]+srcset=["\']([^"\']+)["\']', art)
            cover = img_m.group(1) if img_m else ""
            if cover and not cover.startswith("http"):
                cover = f"{BASE_URL}/{cover.lstrip('/')}"

            ver_m = re.search(r'title=["\'](V\s*[\d.]+)["\']', art) or re.search(r'>(V\s*[\d.]+)</span>', art)
            version = ver_m.group(1).strip() if ver_m else ""

            genre_m = re.search(r'<p[^>]*title=["\']([^"\']+)["\']', art)
            genre_str = genre_m.group(1).strip() if genre_m else ""
            genres = [g.strip() for g in genre_str.split(",") if g.strip()] if genre_str else []

            size_m = re.search(r'>([\d.]+\s*(?:GB|MB|KB))<', art, re.I)
            size_bytes = _parse_size(size_m.group(1)) if size_m else 0
            size_display = size_m.group(1) if size_m else ""

            year_m = re.search(r'>(\d{4})<', art)
            year = year_m.group(1) if year_m else ""

            short_desc = f"{size_display}  ·  {year}".strip(" ·")
            if version:
                short_desc = f"{version}  ·  {short_desc}".strip(" ·")

            item = CatalogItem(
                source=self.id,
                id=slug,
                title=title,
                short_description=short_desc,
                description=f"{title}\n\nAvailable on Anker Games ({size_display}).",
                cover_url=cover,
                size_bytes=size_bytes,
                genres=genres,
                release_date=year,
                version=version,
                store_url=game_url,
                extra={"slug": slug, "size_display": size_display},
            )
            items.append(item)
        return items

    def genres(self) -> list[str]:
        return [
            "Action", "Adventure", "Anime", "Fighting", "Horror", "Indie",
            "Multiplayer", "Open World", "Puzzle", "Racing", "RPG",
            "Shooter", "Simulation", "Sports", "Strategy", "Survival", "VR"
        ]

    def featured(self) -> list[CatalogItem]:
        try:
            page_html = self._fetch_html("/games?page=1") or self._fetch_html("/")
            items = self._parse_articles(page_html)
            return items[:8]
        except Exception as exc:
            log.warning("Could not fetch AnkerGames featured: %s", exc)
            return []

    def search(self, query: str = "", genre: str = "", page: int = 1, page_size: int = 24) -> SearchPage:
        q = query.strip()
        try:
            if q:
                encoded = urllib.parse.quote(q)
                path = f"/search/{encoded}?page={page}"
            elif genre:
                slug = genre.lower().replace(" ", "-")
                path = f"/genre/{slug}?page={page}"
            else:
                path = f"/games?page={page}"

            fallback_games = False
            page_html = self._fetch_html(path)
            if not page_html:
                # If genre path was 404, fallback to /games?page={page} with local filter
                if genre and path.startswith("/genre/"):
                    path = f"/games?page={page}"
                    fallback_games = True
                    page_html = self._fetch_html(path)
                if not page_html:
                    return SearchPage(items=[], has_more=False, total=0)

            items = self._parse_articles(page_html)
            if genre and fallback_games:
                items = [i for i in items if any(genre.lower() in g.lower() for g in i.genres)]

            has_next_page = f"page={page + 1}" in page_html or bool(
                re.search(rf'page={page + 1}\b', page_html)
            )
            if not has_next_page and len(items) >= 56:
                has_next_page = True

            return SearchPage(
                items=items,
                has_more=has_next_page,
                total=-1
            )
        except Exception as exc:
            log.warning("AnkerGames search error: %s", exc)
            return SearchPage(items=[], has_more=False, total=0)

    def details(self, item: CatalogItem) -> CatalogItem:
        slug = item.extra.get("slug") or item.id
        try:
            detail_html = self._fetch_html(f"/game/{slug}")

            # 1. Parse structured JSON-LD (Schema.org VideoGame) for clean specs, screenshots and art
            ld_match = re.search(r'<script type=["\']application/ld\+json["\']>(.*?)</script>', detail_html, re.DOTALL)
            if ld_match:
                try:
                    ld_data = json.loads(ld_match.group(1).strip())
                    ld_items = ld_data if isinstance(ld_data, list) else [ld_data]
                    for obj in ld_items:
                        if isinstance(obj, dict):
                            if "softwareRequirements" in obj and obj["softwareRequirements"]:
                                req = str(obj["softwareRequirements"]).strip()
                                if len(req) > 10:
                                    item.system_requirements = req
                            if "screenshot" in obj and isinstance(obj["screenshot"], list) and obj["screenshot"]:
                                item.screenshots = [s for s in obj["screenshot"] if isinstance(s, str) and s.startswith("http")]
                            if "image" in obj and isinstance(obj["image"], list) and obj["image"]:
                                for img in obj["image"]:
                                    if isinstance(img, str) and img.startswith("http") and not item.cover_url:
                                        item.cover_url = img
                except Exception as exc:
                    log.debug("Could not parse JSON-LD for %s: %s", slug, exc)

            # 2. Extract screenshots from HTML if not found in JSON-LD
            if not item.screenshots:
                screens = re.findall(r'<img[^>]+src=["\']([^"\']*(?:screenshots|uploads/screenshots)[^"\']*)["\']', detail_html)
                if screens:
                    item.screenshots = [s if s.startswith("http") else f"{BASE_URL}/{s.lstrip('/')}" for s in screens[:8]]

            # 3. Resolve hero / banner image (prefer explicit hero, fallback to first widescreen screenshot)
            hero_m = re.search(r'<img[^>]+src=["\']([^"\']*(?:banner|hero)[^"\']*)["\']', detail_html)
            if hero_m:
                h = hero_m.group(1)
                item.hero_url = h if h.startswith("http") else f"{BASE_URL}/{h.lstrip('/')}"
            elif item.screenshots:
                item.hero_url = item.screenshots[0]

            # 4. Resolve download ID
            dl_match = re.search(r'generateDownloadUrl\(\s*(\d+)\s*\)', detail_html)
            if dl_match:
                item.extra["download_id"] = dl_match.group(1)

            # 5. Fallback system requirements if JSON-LD did not provide them
            if not item.system_requirements and ("DirectX" in detail_html or "Windows" in detail_html):
                req_match = re.search(r'(?:Minimum|Recommended)\s*[:\n].*?(?:Storage|DirectX|RAM|Memory|Processor)[^\n<]*', detail_html, re.I | re.DOTALL)
                if req_match:
                    clean = re.sub(r'<[^>]+>', ' ', req_match.group(0))
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    if len(clean) > 20:
                        item.system_requirements = clean
        except Exception as exc:
            log.warning("Could not fetch AnkerGames details for %s: %s", slug, exc)
        return item

    def resolve_download(self, item: CatalogItem, temp_dir: Path) -> DownloadSpec:
        if asyncio is None:
            raise SourceError("Missing dependency 'asyncio' required for Anker Games download.")
        slug = item.extra.get("slug") or item.id
        game_url = item.store_url or f"{BASE_URL}/game/{slug}"
        log.info("Resolving Anker Games download via script for: %s (%s)", item.title, game_url)
        try:
            cdn_url, filename = asyncio.run(_resolve_cdp_async(game_url, temp_dir))
            log.info("Anker Games resolved download successfully: %s -> %s", filename, cdn_url[:60])
            return DownloadSpec(
                url=cdn_url,
                filename=filename,
                size_bytes=item.size_bytes,
                headers={"Referer": BASE_URL},
            )
        except Exception as exc:
            log.exception("Anker Games resolver failed for %s: %s", item.title, exc)
            if isinstance(exc, SourceError):
                raise
            raise SourceError(f"Failed to resolve download for {item.title}: {exc}") from exc
