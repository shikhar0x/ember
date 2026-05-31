from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import requests

# ── NEW: cross-platform browser/driver discovery ──────────────────────────────
from core.browser_finder import (
    BrowserInfo,
    BrowserNotFoundError,
    ChromeDriverNotFoundError,
    find_browser,
    find_chromedriver,
)

# ── Selenium imports (unchanged) ──────────────────────────────────────────────
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


class TokenManager:
    CACHE_FILE = "tokens.json"

    def __init__(self, session=None):
        self._session = session or requests.Session()
        self._bearer = None
        self._expires_at = 0
        self._lock = threading.Lock()

                                                                                  
        self._browser_info: BrowserInfo | None = None
        self._driver_path: str | None = None

                                     
        try:
            with open(self.CACHE_FILE, "r") as f:
                data = json.load(f)
                self._bearer = data.get("bearer")
                self._expires_at = data.get("expires_at", 0)
                if self._bearer and time.time() < self._expires_at:
                    print("[TokenManager] Loaded cached token")
                else:
                    self._bearer = None
        except Exception:
            pass

    # ── Browser/driver resolution (cached after first call) ──────────────────

    def _get_browser_and_driver(self) -> tuple[BrowserInfo, str]:
        """
        Discover the browser binary and chromedriver once, then cache the
        result so repeated token harvests don't re-scan the filesystem.
        """
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

    # ── Token fetch (CDP interception — strategy unchanged) ───────────────────

    def _fetch_token(self) -> None:
        browser_info, driver_path = self._get_browser_and_driver()
        print(f"[TokenManager] Harvesting token via {browser_info.name} "
              f"(v{browser_info.major_version}) ...")

        options = Options()

        # Connect Selenium to the user's local Brave/Chrome binary
        options.binary_location = browser_info.binary

        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")                          
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Enable Chrome DevTools Protocol (CDP) performance logging to intercept the Bearer token
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        driver = webdriver.Chrome(
            service=Service(driver_path),
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

        self._bearer = bearer
        self._expires_at = time.time() + 3300                                    

        with open(self.CACHE_FILE, "w") as f:
            json.dump(
                {"bearer": self._bearer, "expires_at": self._expires_at},
                f,
                indent=2,
            )
        print(f"[TokenManager] Token harvested successfully from {browser_info.name}.")

    # ── Public API (unchanged from original) ─────────────────────────────────

    def get_headers(self) -> dict:
        if not self._bearer:
            with self._lock:
                if not self._bearer:                                     
                    self._fetch_token()

        return {
            "authorization": self._bearer,
            "app-platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0",
            "content-type": "application/json",
        }

    class _ErrorResponse:
        """Structured error sentinel — mimics Response interface."""
        status_code = 0
        content = b""

        def __init__(self, reason="Request failed"):
            self._reason = reason

        def json(self):
            return {"error": True, "reason": self._reason}

    def request(self, method: str, url: str, **kwargs):
        kwargs["headers"] = self.get_headers()

        for attempt in range(2):
            try:
                r = self._session.request(method, url, timeout=10, **kwargs)

                if r.status_code == 401 and attempt == 0:
                    print("[TokenManager] Token rejected — re-harvesting...")
                    self._bearer = None
                    self._expires_at = 0
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


# ── Everything below this line is unchanged from your original file ───────────
                                                                       

SHA256 = "612585ae06ba435ad26369870deaae23b5c8800a256cd8a57e08eddc25a37294"


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
    n = 0
    for char in track_id:
        n = n * 62 + BASE62.index(char)
    gid = hex(n)[2:].zfill(32)

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