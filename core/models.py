from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Track:
    """Spotify/music track."""
    title: str
    artists: list[str]
    album: str
    duration: int
    track_number: Optional[int]
    total_tracks: Optional[int]
    year: Optional[str]
    genre: Optional[str]
    cover_url: Optional[str]
    spotify_url: Optional[str]
    isrc: Optional[str]
    source: str = "spotify"
    media_type: str = "audio"


@dataclass
class VideoItem:
    """YouTube, Shorts, Reels, TikTok, Twitter video, Story video."""
    title: str
    uploader: str
    url: str
    duration: int = 0
    thumbnail_url: Optional[str] = None
    source: str = "youtube"                                                
    media_type: str = "video"


@dataclass
class ImagePost:
    """Instagram photos, Twitter images, Reddit galleries."""
    title: str
    author: str
    caption: str
    download_urls: list[str]
    media_types: list[str]                                      
    source: str = "instagram"                                       
    media_type: str = "image"
    cover_url: Optional[str] = None


@dataclass
class Candidate:
    video_id: str
    title: str
    uploader: str
    duration: int
    score: float = 0.0
    is_isrc: bool = False