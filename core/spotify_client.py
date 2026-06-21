from __future__ import annotations

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import requests

# ── cross-platform browser/driver discovery ───────────────────────────────────
from core.browser_finder import (
    BrowserInfo,
    BrowserNotFoundError,
    ChromeDriverNotFoundError,
    find_browser,
    find_chromedriver,
)

# ── Selenium imports ──────────────────────────────────────────────────────────
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


class TokenManager:
    CACHE_FILE = "tokens.json"

    def __init__(self, session=None):
        if session:
            self._session = session
        else:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        
        self._bearer = None
        self._expires_at = 0
        self._client_token: str = ""
        self._client_token_expires_at: float = 0.0
        self._lock = threading.Lock()

        self._browser_info: BrowserInfo | None = None
        self._driver_path: str | None = None

        try:
            with open(self.CACHE_FILE, "r") as f:
                data = json.load(f)
                self._bearer = data.get("bearer")
                self._expires_at = data.get("expires_at", 0)
                self._client_token = data.get("client_token", "")
                self._client_token_expires_at = data.get("client_token_expires_at", 0.0)
                if self._bearer and time.time() < self._expires_at:
                    print("[TokenManager] Loaded cached token")
                else:
                    self._bearer = None
        except Exception:
            pass

    # ── Browser/driver resolution (cached after first call) ──────────────────

    def _get_browser_and_driver(self) -> tuple[BrowserInfo, str]:
        if self._browser_info is None or self._driver_path is None:
            try:
                self._browser_info = find_browser()
            except BrowserNotFoundError as e:
                raise RuntimeError(str(e)) from e

            try:
                self._driver_path = find_chromedriver(self._browser_info)
            except ChromeDriverNotFoundError as e:
                raise RuntimeError(str(e)) from e

        return self._browser_info, self._driver_path

    # ── Client-token fetch ────────────────────────────────────────────────────

    def _fetch_client_token(self) -> str:
        """Fetch a short-lived client-token from Spotify's client-token endpoint."""
        try:
            r = self._session.post(
                "https://clienttoken.spotify.com/v1/client-token",
                json={
                    "client_data": {
                        "client_version": "1.2.92.73.g916d0757",
                        "client_id": "d8a5ed958d274c2e8ee717e6a4b0971d",
                        "js_sdk_data": {
                            "device_brand": "unknown",
                            "device_model": "unknown",
                            "os": "linux" if sys.platform.startswith("linux") else ("macos" if sys.platform == "darwin" else "windows"),
                            "os_version": "unknown" if sys.platform != "win32" else "NT 10.0",
                            "device_id": "",
                            "device_type": "computer",
                        },
                    }
                },
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                granted = data.get("granted_token", {})
                token = granted.get("token") or data.get("client_token", "")
                ttl = granted.get("expires_after_seconds", 3600)
                if token:
                    self._client_token = token
                    self._client_token_expires_at = time.time() + ttl - 60
                    print("[TokenManager] client-token fetched.")
                    return token
        except Exception as e:
            print(f"[TokenManager] client-token fetch failed: {e}")
        return ""

    # ── Bearer token fetch (CDP interception) ────────────────────────────────

    def _fetch_token(self) -> None:
        browser_info, driver_path = self._get_browser_and_driver()
        print(f"[TokenManager] Harvesting token via {browser_info.name} "
              f"(v{browser_info.major_version}) ...")

        options = Options()
        options.binary_location = browser_info.binary
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        import subprocess
        service_kwargs = {}
        if sys.platform == "win32":
            service_kwargs["creation_flags"] = subprocess.CREATE_NO_WINDOW

        driver = webdriver.Chrome(
            service=Service(driver_path, **service_kwargs),
            options=options,
        )

        bearer = None

        try:
            driver.get("https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b")

            deadline = time.time() + 15
            while time.time() < deadline:
                time.sleep(1)
                for log in driver.get_log("performance"):
                    msg = json.loads(log["message"])["message"]
                    if msg.get("method") == "Network.requestWillBeSentExtraInfo":
                        headers = msg.get("params", {}).get("headers", {})
                        auth = (
                            headers.get("authorization")
                            or headers.get("Authorization")
                        )
                        if auth and "Bearer" in auth:
                            bearer = auth
                if bearer:
                    break
        finally:
            driver.quit()

        if not bearer:
            raise RuntimeError(
                f"[TokenManager] Failed to harvest token from {browser_info.name}. "
                "Make sure you are logged in to Spotify in that browser."
            )

        # Invalidate stale client-token — forces re-fetch below
        self._client_token = ""
        self._client_token_expires_at = 0.0

        self._bearer = bearer
        self._expires_at = time.time() + 3300

        # Fetch fresh client-token now so we can persist both together
        self._fetch_client_token()

        with open(self.CACHE_FILE, "w") as f:
            json.dump(
                {
                    "bearer": self._bearer,
                    "expires_at": self._expires_at,
                    "client_token": self._client_token,
                    "client_token_expires_at": self._client_token_expires_at,
                },
                f,
                indent=2,
            )
        print(f"[TokenManager] Token harvested successfully from {browser_info.name}.")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_headers(self) -> dict:
        if not self._bearer:
            with self._lock:
                if not self._bearer:
                    self._fetch_token()

        if not self._client_token or time.time() >= self._client_token_expires_at:
            with self._lock:
                if not self._client_token or time.time() >= self._client_token_expires_at:
                    self._fetch_client_token()

        headers = {
            "authorization": self._bearer,
            "app-platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0",
            "content-type": "application/json",
        }
        if self._client_token:
            headers["client-token"] = self._client_token
        return headers

    def _probe_token(self) -> bool:
        """Validate the current bearer against Spotify's API (lightweight probe)."""
        if not self._bearer:
            return False
        try:
            r = self._session.post(
                "https://api-partner.spotify.com/pathfinder/v1/query",
                headers={
                    "authorization": self._bearer,
                    "app-platform": "WebPlayer",
                    "User-Agent": "Mozilla/5.0",
                    "content-type": "application/json",
                },
                json={
                    "variables": {"uri": "spotify:track:0VjIjW4GlUZAMYd2vXMi3b"},
                    "operationName": "getTrack",
                    "extensions": {
                        "persistedQuery": {
                            "version": 1,
                            "sha256Hash": SHA256,
                        }
                    },
                },
                timeout=10,
            )
            return r.status_code != 401
        except Exception:
            return True  # network error ≠ token problem

    class _ErrorResponse:
        """Structured error sentinel — mimics Response interface."""
        status_code = 0
        content = b""

        def __init__(self, reason="Request failed"):
            self._reason = reason

        def json(self):
            return {"error": True, "reason": self._reason}

    def request(self, method: str, url: str, **kwargs):
        if "headers" not in kwargs:
            kwargs["headers"] = self.get_headers()

        for attempt in range(2):
            try:
                r = self._session.request(method, url, timeout=10, **kwargs)

                if r.status_code == 401 and attempt == 0:
                    # Race-safe: only invalidate if no other thread already refreshed
                    used_bearer = kwargs["headers"].get("authorization")
                    with self._lock:
                        if self._bearer == used_bearer:
                            print("[TokenManager] Token rejected — re-harvesting...")
                            self._bearer = None
                            self._expires_at = 0
                        else:
                            print("[TokenManager] Token already refreshed by another thread.")
                    kwargs["headers"] = self.get_headers()
                    continue

                return r

            except Exception as e:
                if attempt == 0:
                    print(f"[TokenManager] Request failed (attempt {attempt + 1}): {e}")
                    continue
                print(f"[TokenManager] Request failed permanently: {e}")
                return self._ErrorResponse(str(e))

        return self._ErrorResponse("All retries exhausted")

    def raw_request(self, method: str, url: str, headers: dict, **kwargs):
        """Fire a request with pre-resolved headers (no lock, no get_headers)."""
        try:
            r = self._session.request(method, url, headers=headers, timeout=10, **kwargs)
            if r.status_code == 401:
                # Fallback: full retry path with re-harvest
                return self.request(method, url, **kwargs)
            return r
        except Exception as e:
            return self._ErrorResponse(str(e))


# ─────────────────────────────────────────────────────────────────────────────

SHA256 = "612585ae06ba435ad26369870deaae23b5c8800a256cd8a57e08eddc25a37294"
PLAYLIST_SHA256 = "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4"
PLAYLIST_LIMIT = 50


def get_track(track_id: str, tm: TokenManager) -> dict:
    payload = {
        "variables": {"uri": f"spotify:track:{track_id}"},
        "operationName": "getTrack",
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": SHA256,
            }
        },
    }

    try:
        r = tm.request(
            "POST",
            "https://api-partner.spotify.com/pathfinder/v1/query",
            json=payload,
        )
        data = r.json()["data"]["trackUnion"]
        album = data["albumOfTrack"]

        return {
            "title": data["name"],
            "artists": (
                [a["profile"]["name"] for a in data["firstArtist"]["items"]]
                + [a["profile"]["name"] for a in data.get("otherArtists", {}).get("items", [])]
            ),
            "album": album["name"],
            "album_id": album["id"],
            "year": album["date"]["year"],
            "duration_s": data["duration"]["totalMilliseconds"] // 1000,
            "track_number": data["trackNumber"],
            "cover_url": next(
                (
                    s["url"]
                    for s in sorted(
                        album.get("coverArt", {}).get("sources", []),
                        key=lambda s: s.get("height", 0),
                        reverse=True,
                    )
                ),
                None,
            ),
            "spotify_url": f"https://open.spotify.com/track/{track_id}",
            "track_id": track_id,
            "isrc": None,
        }
    except Exception as e:
        return {"error": True, "reason": str(e), "track_id": track_id}


def get_isrc(track_id: str, tm: TokenManager) -> str | None:
    """Extract ISRC from Spotify's metadata endpoint via raw byte scan."""
    BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    try:
        n = 0
        for char in track_id:
            n = n * 62 + BASE62.index(char)
        gid = hex(n)[2:].zfill(32)
    except ValueError:
        print(f"[ISRC Error] Malformed track_id: {track_id!r}")
        return None

    try:
        r = tm.request(
            "GET",
            f"https://spclient.wg.spotify.com/metadata/4/track/{gid}?market=from_token",
        )
        if r.status_code != 200:
            return None

        matches = re.findall(rb"[A-Z]{2}[A-Z0-9]{3}\d{7}", r.content)
        for m in matches:
            isrc = m.decode()
            if len(isrc) == 12 and isrc[:2].isalpha():
                return isrc
    except Exception as e:
        print(f"[ISRC Error] {track_id}: {e}")
    return None


def get_track_with_isrc(track_id: str, tm: TokenManager) -> dict:
    """Fetch track metadata and ISRC simultaneously."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_track = executor.submit(get_track, track_id, tm)
        future_isrc = executor.submit(get_isrc, track_id, tm)

        try:
            track = future_track.result()
        except Exception as e:
            return {"error": True, "reason": str(e), "track_id": track_id}

        if track.get("error"):
            return track

        try:
            isrc = future_isrc.result()
        except Exception:
            isrc = None

    track["isrc"] = isrc
    return track


def get_tracks_parallel(track_ids, tm, max_workers=5):
    fetch_fn = partial(get_track_with_isrc, tm=tm)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(fetch_fn, track_ids))
    return results


def get_playlist(playlist_id: str, tm: TokenManager, limit: int = PLAYLIST_LIMIT) -> dict:
    """
    Fetch a full playlist via Pathfinder, paginating automatically.
    Returns: {name, owner, cover_url, tracks: list[dict]}
    Each track dict has the same shape as get_track() output plus track_id.
    """
    all_tracks = []
    offset = 0
    playlist_name = None
    playlist_owner = None
    playlist_cover = None
    total = None

    while True:
        payload = {
            "variables": {
                "uri": f"spotify:playlist:{playlist_id}",
                "offset": offset,
                "limit": limit,
                "enableWatchFeedEntrypoint": False,
                "includeEpisodeContentRatingsV2": False,
            },
            "operationName": "fetchPlaylist",
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": PLAYLIST_SHA256,
                },
            },
        }

        try:
            r = tm.request(
                "POST",
                "https://api-partner.spotify.com/pathfinder/v1/query",
                json=payload,
            )
            data = r.json()
        except Exception as e:
            print(f"[get_playlist] Request failed at offset {offset}: {e}")
            break

        pl = (
            data.get("data", {}).get("playlistV2")
            or data.get("data", {}).get("playlist")
        )
        if not pl:
            print(f"[get_playlist] Unexpected schema: {list(data.get('data', {}).keys())}")
            break

        # Playlist-level metadata — only needed from first page
        if offset == 0:
            playlist_name = (
                pl.get("name")
                or pl.get("attributes", {}).get("name")
            )
            owner_data = (
                pl.get("ownerV2", {}).get("data", {})
                or pl.get("owner", {})
            )
            playlist_owner = (
                owner_data.get("name")
                or owner_data.get("displayName")
            )
            images = (
                pl.get("images", {}).get("items")
                or pl.get("coverArt", {}).get("sources")
                or []
            )
            if images:
                best = max(
                    images,
                    key=lambda x: x.get("maxWidth") or x.get("width") or x.get("height") or 0,
                )
                sources = best.get("sources") or []
                playlist_cover = (
                    best.get("url")
                    or (sources[0].get("url") if sources else None)
                )

        content = pl.get("content") or pl.get("tracks") or {}
        items = content.get("items") or content.get("edges") or []
        if total is None:
            total = content.get("totalCount") or content.get("total")

        if not items:
            break

        for item in items:
            track_data = (
                item.get("itemV2", {}).get("data")
                or item.get("track")
                or item.get("node", {}).get("data")
                or {}
            )
            if not track_data or track_data.get("__typename") == "Episode":
                continue

            try:
                album = (
                    track_data.get("albumOfTrack")
                    or track_data.get("album")
                    or {}
                )

                first = [
                    a["profile"]["name"]
                    for a in track_data.get("firstArtist", {}).get("items", [])
                ]
                others = [
                    a["profile"]["name"]
                    for a in track_data.get("otherArtists", {}).get("items", [])
                ]
                if not first:
                    first = [
                        a.get("profile", {}).get("name") or a.get("name", "")
                        for a in (
                            track_data.get("artists", {}).get("items")
                            or track_data.get("artists")
                            or []
                        )
                    ]
                artists = [a for a in (first + others) if a]
                if not artists:
                    artists = ["Unknown Artist"]

                cover_sources = (
                    album.get("coverArt", {}).get("sources")
                    or album.get("images")
                    or []
                )
                cover_url = None
                if cover_sources:
                    best_img = max(
                        cover_sources,
                        key=lambda s: s.get("height") or s.get("width") or 0,
                    )
                    cover_url = best_img.get("url")

                raw_id = track_data.get("uri") or ""
                track_id = (
                    track_data.get("id")
                    or track_data.get("trackV2", {}).get("data", {}).get("id")
                )
                if not track_id and "spotify:track:" in raw_id:
                    track_id = raw_id.split(":")[-1]

                date = album.get("date") or {}
                iso = (date.get("isoString") or "")[:4]
                raw_year = date.get("year")
                year = iso or (str(raw_year) if raw_year else None)

                all_tracks.append({
                    "title": track_data.get("name", "Unknown"),
                    "artists": artists,
                    "album": album.get("name"),
                    "album_id": album.get("id"),
                    "year": year,
                    "duration_s": (
                        track_data.get("duration", {}).get("totalMilliseconds") or 0
                    ) // 1000,
                    "track_number": track_data.get("trackNumber"),
                    "cover_url": cover_url,
                    "spotify_url": (
                        f"https://open.spotify.com/track/{track_id}"
                        if track_id else None
                    ),
                    "track_id": track_id,
                    "isrc": None,
                })
            except Exception as e:
                print(f"[get_playlist] Skipped track due to parse error: {e}")
                continue

        offset += len(items)
        if total is not None and offset >= total:
            break
        if len(items) < limit:
            break

    print(f"[get_playlist] Fetched {len(all_tracks)} tracks for '{playlist_name}'")
    return {
        "name": playlist_name,
        "owner": playlist_owner,
        "cover_url": playlist_cover,
        "tracks": all_tracks,
    }