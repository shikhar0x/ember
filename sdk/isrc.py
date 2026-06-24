"""
ISRC extraction module for the Spotify GraphQL SDK.

Extracts ISRCs from Spotify's internal metadata endpoint by converting
track IDs from base62 to hex GIDs, then scanning the raw protobuf
response bytes for the 12-character ISRC pattern (CC-XXX-YY-NNNNN).
"""

import re
import json

from .client import SpotifyGraphQL
from .album import get_album_tracks
from .playlist import get_playlist_tracks
from .artist import get_artist
from .batch import batch_fetch

from .utils import (
    ensure_directory,
    sanitize_filename,
)

spotify = SpotifyGraphQL()

BASE62 = (
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def _track_id_to_gid(
    track_id: str,
) -> str | None:
    """Convert a Spotify base62 track ID to a hex GID."""

    try:
        n = 0
        for char in track_id:
            n = n * 62 + BASE62.index(char)
        return hex(n)[2:].zfill(32)

    except ValueError:
        return None


def _extract_isrc_from_bytes(
    raw: bytes,
) -> str | None:
    """Scan raw protobuf bytes for an ISRC pattern."""

    matches = re.findall(
        rb"[A-Z]{2}[A-Z0-9]{3}\d{7}",
        raw,
    )

    for m in matches:
        isrc = m.decode()
        if (
            len(isrc) == 12
            and isrc[:2].isalpha()
        ):
            return isrc

    return None


# ── Single track ──────────────────────────────────────────────────────────────


def get_track_isrc(
    track_id: str,
    headers: dict | None = None,
    session=None,
) -> str | None:
    """
    Fetch the ISRC for a single track.

    Converts the track ID to a hex GID, hits Spotify's
    internal metadata endpoint, and scans the protobuf
    response for the 12-char ISRC code.

    When `headers` is provided, bypasses internal lock
    contention by using pre-resolved auth context.
    When `session` is provided, reuses the given connection pool.

    Returns the ISRC string or None if not found.
    """

    gid = _track_id_to_gid(track_id)

    if not gid:
        return None

    url = (
        f"https://spclient.wg.spotify.com"
        f"/metadata/4/track/{gid}"
        f"?market=from_token"
    )

    try:
        if session and headers:
            response = session.request(
                "GET", url, headers=headers, timeout=10,
            )
        elif headers:
            response = spotify._tm.raw_request(
                "GET", url, headers=headers,
            )
        else:
            response = spotify._tm.request(
                "GET", url,
            )

        if response.status_code != 200:
            return None

        return _extract_isrc_from_bytes(
            response.content
        )

    except Exception as e:
        pass
        return None

def get_track_isrc_batch(
    track_ids: list[str],
    headers: dict | None = None,
    session=None,
) -> dict[str, str | None]:
    """
    Process a batch of track IDs sequentially in one thread.
    When headers are provided, all requests bypass lock contention.
    Returns a dictionary mapped by identifier: { track_id: isrc_or_none }
    """
    results = {}
    for tid in track_ids:
        results[tid] = get_track_isrc(tid, headers=headers, session=session)
    return results

def get_track_isrc_bulk(
    track_ids: list[str],
    session,
    headers: dict,
) -> dict[str, str]:
    """
    Fetches ISRC data for a list of track IDs in a single batch call.
    Returns a dictionary mapping {tid: isrc}.
    """
    ids_param = ",".join(track_ids)
    url = f"https://api.spotify.com/v1/tracks?ids={ids_param}"
    
    # We only need the authorization bearer for the v1 API
    v1_headers = {
        "Authorization": headers.get("authorization", "")
    }
    
    try:
        response = session.get(url, headers=v1_headers)
        if response.status_code != 200:
            return {}
            
        results = {}
        tracks_data = response.json().get("tracks", [])
        
        for track in tracks_data:
            if track:
                tid = track.get("id")
                if tid:
                    isrc = track.get("external_ids", {}).get("isrc", "")
                    results[tid] = isrc
                    
        return results
    except Exception:
        return {}


# ── Album ─────────────────────────────────────────────────────────────────────


def get_album_isrcs(
    album_id: str,
    max_workers: int = 5,
) -> list[dict]:
    """
    Fetch ISRCs for all tracks in an album.

    Uses the SDK's get_album_tracks() to get
    track IDs, then resolves ISRCs in parallel.

    Returns a list of dicts:
        [{"track_id": str, "isrc": str | None}, ...]
    """

    track_ids = get_album_tracks(album_id)

    def _resolve(tid):
        return {
            "track_id": tid,
            "isrc": get_track_isrc(tid),
        }

    return batch_fetch(
        track_ids,
        _resolve,
        max_workers,
    )


# ── Playlist ──────────────────────────────────────────────────────────────────


def get_playlist_isrcs(
    playlist_id: str,
    max_workers: int = 5,
) -> list[dict]:
    """
    Fetch ISRCs for all tracks in a playlist.

    Uses get_playlist_tracks() to fetch all track items,
    extracts each track's ID from its URI, and resolves
    ISRCs in parallel.

    Returns a list of dicts:
        [{"track_id": str, "name": str, "isrc": str | None}, ...]
    """

    tracks = get_playlist_tracks(playlist_id)

    entries = []

    for t in tracks:

        uri = t.get("uri", "")

        if "spotify:track:" not in uri:
            continue

        track_id = uri.split(":")[-1]

        entries.append({
            "track_id": track_id,
            "name": t.get("name", "Unknown"),
        })

    def _resolve(entry):
        return {
            "track_id": entry["track_id"],
            "name": entry["name"],
            "isrc": get_track_isrc(
                entry["track_id"]
            ),
        }

    return batch_fetch(
        entries,
        _resolve,
        max_workers,
    )


# ── Artist ────────────────────────────────────────────────────────────────────


def get_artist_isrcs(
    artist_id: str,
    max_workers: int = 5,
) -> list[dict]:
    """
    Fetch ISRCs for an artist's top tracks.

    Pulls the artist's top tracks from the GraphQL
    response and resolves ISRCs in parallel.

    Returns a list of dicts:
        [{"track_id": str, "name": str, "isrc": str | None}, ...]
    """

    data = get_artist(artist_id)

    top_tracks = (
        data.get("data", {})
        .get("artistUnion", {})
        .get("discography", {})
        .get("topTracks", {})
        .get("items", [])
    )

    entries = []

    for item in top_tracks:

        track = item.get("track", {})
        track_id = track.get("id")
        name = track.get("name", "Unknown")

        if track_id:
            entries.append({
                "track_id": track_id,
                "name": name,
            })

    def _resolve(entry):
        return {
            "track_id": entry["track_id"],
            "name": entry["name"],
            "isrc": get_track_isrc(
                entry["track_id"]
            ),
        }

    return batch_fetch(
        entries,
        _resolve,
        max_workers,
    )


# ── Save to file ──────────────────────────────────────────────────────────────


def save_isrcs(
    isrcs: list[dict],
    name: str,
    output_dir: str = "Results",
):
    """
    Save a list of ISRC results to a JSON file.

    Writes to Results/<name>/<name>_isrcs.json.
    Returns the file path.
    """

    folder = (
        f"{output_dir}/"
        f"{sanitize_filename(name)}"
    )

    ensure_directory(folder)

    filepath = (
        f"{folder}/"
        f"{sanitize_filename(name)}_isrcs.json"
    )

    with open(
        filepath,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            isrcs,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return filepath
