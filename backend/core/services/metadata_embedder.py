"""
core/services/metadata_embedder.py
====================================
Resolve metadata from a Spotify or YouTube Music link and embed it
onto an existing local audio file. No audio is fetched — tags only.
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional

from core.models import Track
from core.tagger import tag_audio
from core.http_helper import get_bytes
from core.events import emit, status_event, complete_event, error_event

_SUPPORTED_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus"}


def resolve_metadata_track(url: str) -> Track:
    """Resolve a Spotify track URL or YTMusic track URL into a Track."""
    if "open.spotify.com" in url and "/track/" in url:
        from core.spotify import get_track
        return get_track(url)

    if "music.youtube.com" in url:
        from core.ytmusic_metadata import extract_ids, process_track, build_album_art_cache
        from ytmusicapi import YTMusic

        video_id, _, _ = extract_ids(url)
        if not video_id:
            raise ValueError("Could not parse a YouTube Music track from this URL")

        yt = YTMusic()
        video_details = yt.get_song(videoId=video_id).get("videoDetails", {})
        watch = yt.get_watch_playlist(videoId=video_id)
        raw = watch.get("tracks", [{}])[0] if watch.get("tracks") else {}
        raw["title"] = raw.get("title") or video_details.get("title")
        raw["videoId"] = video_id
        if "lengthSeconds" in video_details:
            raw["duration_seconds"] = int(video_details["lengthSeconds"])
        if not raw.get("artists") and video_details.get("author"):
            raw["artists"] = [
                {"name": n.strip(), "id": None}
                for n in video_details.get("author", "").replace(" - Topic", "").split(" • ")
                if n.strip()
            ]

        album_id = (raw.get("album") or {}).get("id") if isinstance(raw.get("album"), dict) else None
        cache = build_album_art_cache([album_id], art_size=1000, workers=1) if album_id else {}
        result = process_track(raw, video_id, art_size=1000, album_art_cache=cache)

        artists = [a["name"] for a in result.get("artists", []) if a.get("name")] or ["Unknown Artist"]
        return Track(
            title=result.get("title", "Unknown"),
            artists=artists,
            album=(result.get("album") or {}).get("name"),
            duration=result.get("duration_seconds") or 0,
            track_number=None, total_tracks=None, year=None, genre=None,
            cover_url=result.get("cover_art_url") or result.get("video_thumbnail_url"),
            spotify_url=result.get("url"),
            isrc=None,
            source="ytmusic",
        )

    raise ValueError("Provide a Spotify track link or a YouTube Music track link")


def embed_metadata_on_file(
    file_path: str,
    source_url: str,
    callback: Optional[Callable[[dict], None]] = None,
) -> bool:
    path = Path(file_path)
    if not path.is_file():
        emit(callback, error_event("File not found"))
        return False
    if path.suffix.lower() not in _SUPPORTED_EXTS:
        emit(callback, error_event(f"Unsupported file type: {path.suffix}"))
        return False

    try:
        emit(callback, status_event("Resolving metadata..."))
        track = resolve_metadata_track(source_url)

        cover_bytes = get_bytes(track.cover_url, timeout=10) if track.cover_url else None

        emit(callback, status_event("Embedding metadata..."))
        tag_audio(track, str(path), cover_bytes)

        emit(callback, complete_event(True, "Metadata embedded!"))
        return True
    except Exception as e:
        emit(callback, error_event(f"Failed: {e}"))
        return False
