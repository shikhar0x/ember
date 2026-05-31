"""
core/api/schemas.py
====================
Pydantic request/response models for the Spyde local API.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── Track serialization ──────────────────────────────────────────────────────

class TrackSchema(BaseModel):
    """JSON-serializable mirror of core.models.Track."""
    title: str
    artists: list[str]
    album: str
    duration: int
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    cover_url: Optional[str] = None
    spotify_url: Optional[str] = None
    isrc: Optional[str] = None
    source: str = "spotify"
    media_type: str = "audio"


# ── Request bodies ────────────────────────────────────────────────────────────

class DownloadOptions(BaseModel):
    format: str = "Audio (MP3)"
    quality: str = "Best Available"
    audio_codec: str = "mp3"
    audio_quality: str = "0"


class SpotifyRequest(BaseModel):
    url: Optional[str] = None
    track: Optional[TrackSchema] = None
    options: DownloadOptions = Field(default_factory=DownloadOptions)


class PlaylistRequest(BaseModel):
    tracks: list[TrackSchema]
    options: DownloadOptions = Field(default_factory=DownloadOptions)
    playlist_title: str = "Playlist"


class YoutubeRequest(BaseModel):
    """Minimal data dict for YouTube/generic downloads."""
    url: str
    title: str = "audio"
    options: DownloadOptions = Field(default_factory=DownloadOptions)


class MediaRequest(BaseModel):
    """Data dict for image/mixed-media downloads."""
    title: str = "image"
    url: Optional[str] = None
    spotify_url: Optional[str] = None
    thumbnail_bytes_b64: Optional[str] = None                  
    carousel: Optional[dict] = None


class CancelRequest(BaseModel):
    pass                                           


# ── Response bodies ───────────────────────────────────────────────────────────

class TaskResponse(BaseModel):
    task_id: str


class TaskStatus(BaseModel):
    task_id: str
    state: str                                                                      
    latest: Optional[dict] = None
    events: list[dict] = Field(default_factory=list)


class CancelResponse(BaseModel):
    task_id: str
    cancelled: bool
    message: str = ""


class TrackInfoResponse(BaseModel):
    """Full track metadata returned by GET /track/info."""
    title: str
    artists: list[str]
    album: Optional[str] = None
    duration: int = 0
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    cover_url: Optional[str] = None
    spotify_url: Optional[str] = None
    isrc: Optional[str] = None
    source: str = "spotify"
    media_type: str = "audio"


class InspectResponse(BaseModel):
    """Unified response for GET /track/info — works for tracks, albums, and playlists."""
    type: str                                  
                                                   
    track: Optional[TrackInfoResponse] = None
                                                            
    title: Optional[str] = None
    owner: Optional[str] = None
    cover_url: Optional[str] = None
    total_tracks: Optional[int] = None
    tracks: Optional[list[TrackInfoResponse]] = None