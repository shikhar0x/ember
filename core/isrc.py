import requests
import time
from playwright.sync_api import sync_playwright

# --------------------------------
                    
# --------------------------------
_TOKEN_CACHE = {
    "value": None,
    "timestamp": 0
}

TOKEN_TTL = 60 * 10              


# --------------------------------
# TOKEN FETCH
# --------------------------------
def _get_token() -> str:
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        token = None

        def handle_request(request):
            nonlocal token
            if "/api/ext/recordings" in request.url:
                auth = request.headers.get("authorization")
                if auth:
                    token = auth.replace("Token ", "")

        page.on("request", handle_request)

        page.goto("https://isrcsearch.ifpi.org/?tab=simple&artistName=test&title=test")
        page.wait_for_load_state("networkidle")

        browser.close()

        if not token:
            raise RuntimeError("ISRC token capture failed")

        return token


def _get_cached_token() -> str:
    now = time.time()

    if (
        _TOKEN_CACHE["value"]
        and now - _TOKEN_CACHE["timestamp"] < TOKEN_TTL
    ):
        return _TOKEN_CACHE["value"]

    token = _get_token()
    _TOKEN_CACHE["value"] = token
    _TOKEN_CACHE["timestamp"] = now

    return token


# --------------------------------
# API CALL
# --------------------------------
def _fetch_data(token: str, artist: str, title: str) -> dict:
    url = "https://isrc-api.soundexchange.com/api/ext/recordings"

    headers = {
        "authorization": f"Token {token}",
        "content-type": "application/json",
        "origin": "https://isrcsearch.ifpi.org",
        "referer": "https://isrcsearch.ifpi.org/"
    }

    payload = {
        "searchFields": {
            "recordingArtistName": {"value": artist},
            "recordingTitle": {"value": title},
            "releaseName": {"value": ""}
        },
        "start": 0,
        "number": 50,
        "showReleases": True
    }

    r = requests.post(url, json=payload, headers=headers, timeout=10)

    if r.status_code != 200:
        raise RuntimeError(f"ISRC API failed: {r.status_code}")

    return r.json()


# --------------------------------
                
# --------------------------------
def _process(data: dict, artist: str, title: str) -> dict:
    unique = {}

    for r in data.get("recordings", []):
        isrc = r.get("isrc")
        if not isrc:
            continue

        if isrc not in unique:
            unique[isrc] = {
                "artist": r.get("recordingArtistName", ""),
                "title": r.get("recordingTitle", ""),
                "year": r.get("recordingYear"),
                "duration": r.get("duration"),
                "isrc": isrc,
                "type": r.get("recordingType", "")
            }

    filtered = []

    for r in unique.values():
        t = (r["title"] or "").lower()
        a = (r["artist"] or "").lower()

        if artist.lower() in a and title.lower() in t:
            if not any(x in t for x in ["remix", "karaoke", "cover", "fitness"]):
                filtered.append(r)

    def _score(x):
        s = 0
        if x["type"] == "Audio":
            s += 3
        if x["year"]:
            s += 2
        if "live" not in (x["title"] or "").lower():
            s += 2
        return s

    filtered.sort(key=_score, reverse=True)

    return {
        "best": filtered[0] if filtered else None,
        "all": filtered
    }


# --------------------------------
                    
# --------------------------------
def get_isrc(artist: str, title: str, retries: int = 2) -> dict | None:
    """
    Returns:
        {
            "isrc": str,
            "duration": int,
            "title": str,
            "artist": str
        }
    OR None
    """

    for attempt in range(retries + 1):
        try:
            token = _get_cached_token()
            data = _fetch_data(token, artist, title)
            result = _process(data, artist, title)

            if result["best"]:
                return result["best"]

            return None

        except Exception as e:
            print(f"[ISRC] Attempt {attempt+1} failed: {e}")
            _TOKEN_CACHE["value"] = None
            time.sleep(1)

    return None