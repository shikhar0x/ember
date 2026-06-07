import json
import time
import urllib.parse
from pathlib import Path

import re
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL
)
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session = requests.Session()

adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
    max_retries=Retry(total=1, backoff_factor=0.1),
)

_session.mount("https://", adapter)
_session.mount("http://", adapter)

from typing import List
from core.models import Track
from core.isrc import get_isrc
from core.spotify_client import TokenManager

# ------------------------------------------------------------------ #

TOKEN_URL      = "https://accounts.spotify.com/api/token"
TRACK_URL      = "https://api.spotify.com/v1/tracks/{}"
PLAYLIST_URL   = "https://api.spotify.com/v1/playlists/{}"
SEARCH_URL     = "https://api.spotify.com/v1/search"
DEFAULT_MARKET = "IN"

# ------------------------------------------------------------------ #

def _extract_track_id(url: str) -> str: return url.split("/track/")[-1].split("?")[0].strip()
def _extract_album_id(url: str) -> str: return url.split("/album/")[-1].split("?")[0].strip()
def _extract_playlist_id(url: str) -> str: return url.split("/playlist/")[-1].split("?")[0].strip()

# ------------------------------------------------------------------ #

import threading

_mb_lock = threading.Lock()
_mb_last_time = 0.0


def get_isrc_fallback(title, artist):
    """Hits MusicBrainz with a fuzzy query if the strict search fails."""
    query = f"{title} {artist}"
    url = "http://musicbrainz.org/ws/2/recording/"
    params = {
        "query": query,
        "fmt": "json",
        "limit": 5,
    }
    headers = {"User-Agent": "Spyde/1.0 ( support@spyde.app )"}

    try:
        r = _session.get(url, params=params, headers=headers, timeout=5)
        data = r.json()
        recordings = data.get("recordings", [])
        for rec in recordings:
            isrcs = rec.get("isrcs", [])
            if isrcs:
                return isrcs[0]
    except Exception as e:
        print(f"[ISRC Fallback] MusicBrainz fuzzy query failed: {e}")
    return None


def _fetch_extra_metadata_from_musicbrainz(title: str, artist: str) -> dict:
    """
    Search MusicBrainz for a track's ISRC, Album, Year, and Genre.
    Strictly rate-limited to 1 request per second globally.
    """
    global _mb_last_time

    with _mb_lock:
        now = time.time()
        elapsed = now - _mb_last_time
        if elapsed < 1.02:
            time.sleep(1.02 - elapsed)
        _mb_last_time = time.time()

    print(f"[Spyde] Searching MusicBrainz: {title} - {artist}")
    meta = {"isrc": None, "album": None, "year": None, "genre": None}
    try:
        url = "http://musicbrainz.org/ws/2/recording/"
        params = {
            "query": f'recording:"{title}" AND artist:"{artist}"',
            "fmt": "json",
            "limit": 5,
        }
        headers = {"User-Agent": "SpydeBackend/1.0 ( support@spyde.app )"}
        r = _session.get(url, params=params, headers=headers, timeout=5)
        if r.status_code == 200:
            recs = r.json().get("recordings", [])
            if recs:
                rec = recs[0]
                meta["isrc"] = rec.get("isrcs", [])[0] if rec.get("isrcs") else None

                if not meta["isrc"]:
                    print("[Spyde] Basic ISRC match failed. Running aggressive fallback...")
                    meta["isrc"] = get_isrc_fallback(title, artist)

                rel = rec.get("releases", [])[0] if rec.get("releases") else {}
                meta["album"] = rel.get("title")
                date = rel.get("date")
                if date:
                    meta["year"] = date[:4]

                tags = rec.get("tags", [])
                if tags:
                    meta["genre"] = tags[0].get("name", "").title()
    except Exception as e:
        print(f"[Spyde] MusicBrainz failed: {e}")
    return meta


def _fetch_track_via_embed(track_id: str) -> Track:
    """Fast embed-only fetch (single request, no OG scrape)."""
    print(f"[Spyde] Fetching track {track_id} via Embed Loophole...")

    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = _session.get(embed_url, headers=headers, timeout=15)
    r.raise_for_status()

    match = _NEXT_DATA_RE.search(r.text)
    if not match:
        raise ValueError("Could not find data in embed.")

    data = json.loads(match.group(1))

    entity = (
        data.get("props", {})
            .get("pageProps", {})
            .get("state", {})
            .get("data", {})
            .get("entity", {})
    )

    if not entity:
        raise ValueError("No track data in embed.")

    track_cover = None
    visual = entity.get("visualIdentity", {})
    images = visual.get("image", [])
    if images:
        best_image = max(images, key=lambda x: x.get("maxHeight", 0))
        track_cover = best_image.get("url")

    artists = [a.get("name", "Unknown") for a in entity.get("artists", [])] or ["Unknown Artist"]
    title = entity.get("name") or entity.get("title") or "Unknown Title"
    release_date = entity.get("releaseDate", {}).get("isoString", "")
    year = release_date[:4] if release_date else None
    duration = entity.get("duration", 0) // 1000

    t = Track(
        title=title,
        artists=artists,
        album=None,
        duration=duration,
        track_number=1,
        total_tracks=1,
        year=year,
        genre=None,
        cover_url=track_cover,
        spotify_url=f"https://open.spotify.com/track/{track_id}",
        isrc=None,
        source="spotify",
    )
    t._enriched = False
    return t


def _quick_fetch_via_embed(playlist_id: str) -> List[Track]:
    """
    Embed fallback: build basic Track objects from the playlist embed's trackList.
    No individual embed scrapes — shows the UI immediately with titles/artists/duration.
    """
    print("[Spyde] Fetching playlist via Spotify Embed Loophole...")
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    r = _session.get(embed_url, headers=headers, timeout=15)
    r.raise_for_status()

    match = _NEXT_DATA_RE.search(r.text)
    if not match:
        raise ValueError("Could not find data in embed.")
    data = json.loads(match.group(1))

    entity = (
        data.get("props", {})
            .get("pageProps", {})
            .get("state", {})
            .get("data", {})
            .get("entity", {})
    )
    track_list = entity.get("trackList", [])

    playlist_name = entity.get("name") or entity.get("title") or "Unknown Playlist"
    playlist_owner = entity.get("owner", {}).get("name") or "Spotify Collection"
    playlist_cover = None
    visual = entity.get("visualIdentity", {})
    images = visual.get("image", [])
    if images:
        best_image = max(images, key=lambda x: x.get("maxHeight", 0))
        playlist_cover = best_image.get("url")

    total = len([i for i in track_list if i.get("title") and i.get("uri")])
    tracks = []
    real_idx = 0

    for idx, item in enumerate(track_list, 1):
        if not item.get("title") or not item.get("uri"):
            print(f"[Spyde] Skipped invalid track at index {idx}")
            continue
        real_idx += 1

        t = Track(
            title=item.get("title"),
            artists=[a.strip() for a in item.get("subtitle", "Unknown").split(",")],
            album=playlist_name,
            duration=item.get("duration", 0) // 1000,
            track_number=real_idx,
            total_tracks=total,
            year=None,
            genre=None,
            cover_url=None,
            spotify_url=item.get("uri", "").replace("spotify:track:", "https://open.spotify.com/track/"),
            isrc=None,
            source="spotify",
        )
        t._spotify_track_id = item.get("uri", "").replace("spotify:track:", "")
        t._enriched = False
        t._playlist_name = playlist_name
        t._playlist_cover = playlist_cover

        if real_idx == 1:
            t.parent_name = playlist_name
            t.parent_owner = playlist_owner
            t.parent_cover = playlist_cover

        tracks.append(t)

    print(f"[Spyde] Embed loaded {len(tracks)} tracks.")
    return tracks


def _fetch_via_embed(playlist_id: str) -> List[Track]:
    return _quick_fetch_via_embed(playlist_id)


def _fetch_album_via_embed(album_id: str) -> List[Track]:
    """Extract album tracks using Spotify embed (no API, no token)."""
    print(f"[Spyde] Fetching album {album_id} via Embed...")

    embed_url = f"https://open.spotify.com/embed/album/{album_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = _session.get(embed_url, headers=headers, timeout=15)
    r.raise_for_status()

    match = _NEXT_DATA_RE.search(r.text)
    if not match:
        raise ValueError("Could not find album data in embed.")

    data = json.loads(match.group(1))

    entity = (
        data.get("props", {})
            .get("pageProps", {})
            .get("state", {})
            .get("data", {})
            .get("entity", {})
    )
    if not entity:
        raise ValueError("No album data in embed.")

    track_list = entity.get("trackList", [])
    album_name = entity.get("name") or entity.get("title") or "Unknown Album"

    visual = entity.get("visualIdentity", {})
    images = visual.get("image", [])
    album_cover = None
    if images:
        best = max(images, key=lambda x: x.get("maxHeight", 0))
        album_cover = best.get("url")

    total = len([t for t in track_list if t.get("title") and t.get("uri")])
    tracks = []
    idx_real = 0

    for item in track_list:
        if not item.get("title") or not item.get("uri"):
            continue
        idx_real += 1

        track_id = item.get("uri", "").replace("spotify:track:", "")

        t = Track(
            title=item.get("title"),
            artists=[a.strip() for a in item.get("subtitle", "").split(",") if a.strip()],
            album=album_name,
            duration=item.get("duration", 0) // 1000,
            track_number=idx_real,
            total_tracks=total,
            year=None,
            genre=None,
            cover_url=album_cover,
            spotify_url=f"https://open.spotify.com/track/{track_id}",
            isrc=None,
            source="spotify",
        )
        t._spotify_track_id = track_id
        t._enriched = False
        t._album_name = album_name
        t._album_cover = album_cover

        if idx_real == 1:
            t.parent_name = album_name
            t.parent_owner = "Spotify Album"
            t.parent_cover = album_cover

        tracks.append(t)

    print(f"[Spyde] Loaded {len(tracks)} album tracks via embed.")
    return tracks


# ------------------------------------------------------------------ #

_tm = TokenManager(session=_session)

_cache = {}


def get_track(url: str) -> Track:
    track_id = _extract_track_id(url)

    if track_id in _cache:
        return _cache[track_id]

    # --- Fast path: Pathfinder + spclient ISRC in parallel ---
    try:
        from core.spotify_client import get_track_with_isrc
        data = get_track_with_isrc(track_id, _tm)

        if data.get("error"):
            raise Exception(data.get("reason", "Pathfinder error"))

        track = Track(
            title=data["title"],
            artists=data["artists"],
            album=data["album"],
            duration=data["duration_s"],
            track_number=data.get("track_number"),
            total_tracks=None,
            year=str(data.get("year")) if data.get("year") else None,
            genre=None,
            cover_url=data.get("cover_url"),
            spotify_url=data["spotify_url"],
            isrc=data.get("isrc"),
            source="spotify",
        )

        # IFPI fallback if spclient returned nothing
        if not track.isrc:
            result = get_isrc(track.artists[0], track.title)
            if result and result.get("isrc"):
                res_title = (result.get("title") or "").lower()
                if track.title.lower() in res_title or res_title in track.title.lower():
                    track.isrc = result["isrc"]

        _cache[track_id] = track
        return track

    except Exception as e:
        print(f"[Spyde] Pathfinder failed, falling back to embed: {e}")

    # --- Fallback: embed scrape ---
    track = _fetch_track_via_embed(track_id)

    if not track.isrc:
        try:
            from core.spotify_client import get_isrc as spotify_get_isrc
            track.isrc = spotify_get_isrc(track_id, _tm)
        except Exception:
            pass

    if not track.isrc:
        result = get_isrc(track.artists[0], track.title)
        if result and result.get("isrc"):
            res_title = (result.get("title") or "").lower()
            if track.title.lower() in res_title or res_title in track.title.lower():
                track.isrc = result["isrc"]

    _cache[track_id] = track
    return track


def get_album(url: str) -> List[Track]:
    album_id = _extract_album_id(url)

    try:
        return _fetch_album_via_embed(album_id)
    except Exception as e:
        print(f"[Spyde] Album embed failed: {e}")
        raise


def get_playlist(url: str) -> List[Track]:
    playlist_id = _extract_playlist_id(url)
    print(f"\n[Spyde] Resolving playlist: {playlist_id}")

    # --- Fast path: Pathfinder API with pagination ---
    try:
        from core.spotify_client import get_playlist as _pathfinder_get_playlist
        result = _pathfinder_get_playlist(playlist_id, _tm)
        raw_tracks = result.get("tracks", [])

        if raw_tracks:
            playlist_name = result.get("name") or "Playlist"
            playlist_owner = result.get("owner") or "Spotify"
            playlist_cover = result.get("cover_url")
            total = len(raw_tracks)

            tracks = []
            for idx, t in enumerate(raw_tracks, 1):
                track = Track(
                    title=t["title"],
                    artists=t["artists"],
                    album=t.get("album") or playlist_name,
                    duration=t.get("duration_s", 0),
                    track_number=t.get("track_number") or idx,
                    total_tracks=total,
                    year=t.get("year"),
                    genre=None,
                    cover_url=t.get("cover_url"),
                    spotify_url=t.get("spotify_url"),
                    isrc=None,
                    source="spotify",
                )
                track_id = t.get("track_id")
                if track_id:
                    track._spotify_track_id = track_id
                track._enriched = False
                track._playlist_name = playlist_name

                if idx == 1:
                    track.parent_name = playlist_name
                    track.parent_owner = playlist_owner
                    track.parent_cover = playlist_cover

                tracks.append(track)

            print(f"[Spyde] Pathfinder loaded {len(tracks)} tracks.")
            return tracks

    except Exception as e:
        print(f"[Spyde] Pathfinder playlist failed: {e}")

    # --- Fallback: embed ---
    print("[Spyde] Falling back to embed...")
    return _fetch_via_embed(playlist_id)