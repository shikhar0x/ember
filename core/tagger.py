import os
import base64
import struct

from mutagen.id3 import (
    ID3, APIC,
    TIT2,          
    TPE1,           
    TPE2,                 
    TALB,          
    TRCK,                 
    TDRC,         
    TCON,          
    TSRC,   # ISRC
)
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus


def tag_audio(track, file_path: str, cover_bytes: bytes | None) -> None:
    """Dispatch metadata tagging to the correct handler based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()

    handlers = {
        ".mp3":  _tag_mp3,
        ".flac": _tag_flac,
        ".m4a":  _tag_m4a,
        ".ogg":  _tag_ogg,
        ".opus": _tag_opus,
    }

    handler = handlers.get(ext)
    if handler:
        handler(track, file_path, cover_bytes)
    elif ext == ".wav":
        print("[Tagger] WAV format — no metadata embedded (not supported by format)")
    else:
        print(f"[Tagger] Unsupported format: {ext}")


# ──────────────────────────────────────────────────────────────
                
# ──────────────────────────────────────────────────────────────
def _tag_mp3(track, file_path: str, cover_bytes: bytes | None) -> None:
    audio = MP3(file_path, ID3=ID3)

    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags

    # ---- Clear existing ----
    for tag in ["TIT2", "TPE1", "TPE2", "TALB", "TRCK", "TDRC", "TCON", "APIC:"]:
        tags.delall(tag)

    # ---- Title ----
    tags.add(TIT2(encoding=3, text=track.title))

    # ---- Artists ----
    artist_str = ", ".join(track.artists)
    tags.add(TPE1(encoding=3, text=artist_str))
    tags.add(TPE2(encoding=3, text=artist_str))

    # ---- Album ----
    if track.album:
        tags.add(TALB(encoding=3, text=track.album))

    # ---- Track number ----
    if track.track_number is not None:
        if track.total_tracks is not None:
            trck = f"{track.track_number}/{track.total_tracks}"
        else:
            trck = str(track.track_number)
        tags.add(TRCK(encoding=3, text=trck))

    # ---- Year ----
    if track.year:
        tags.add(TDRC(encoding=3, text=track.year))

    # ---- Genre ----
    if track.genre:
        tags.add(TCON(encoding=3, text=track.genre))

    # ---- ISRC ----
    if hasattr(track, 'isrc') and track.isrc:
        tags.add(TSRC(encoding=3, text=track.isrc))

    # ---- Cover art ----
    if cover_bytes:
                                                                      
        audio.tags.delall('APIC') 

                                           
        audio.tags.add(
            APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,                   
                desc='Cover',
                data=cover_bytes
            )
        )
    audio.save(v2_version=3)


# ──────────────────────────────────────────────────────────────
#  FLAC
# ──────────────────────────────────────────────────────────────
def _tag_flac(track, file_path: str, cover_bytes: bytes | None) -> None:
    audio = FLAC(file_path)

    audio["title"] = track.title
    audio["artist"] = ", ".join(track.artists)
    if track.album:
        audio["album"] = track.album
    if track.track_number is not None:
        audio["tracknumber"] = str(track.track_number)
        if track.total_tracks is not None:
            audio["tracktotal"] = str(track.total_tracks)
    if track.year:
        audio["date"] = track.year
    if track.genre:
        audio["genre"] = track.genre
    if hasattr(track, 'isrc') and track.isrc:
        audio["isrc"] = track.isrc

    if cover_bytes:
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3               
        pic.mime = "image/jpeg"
        pic.desc = "Cover"
        pic.data = cover_bytes
        audio.add_picture(pic)

    audio.save()


# ──────────────────────────────────────────────────────────────
                            
# ──────────────────────────────────────────────────────────────
def _tag_m4a(track, file_path: str, cover_bytes: bytes | None) -> None:
    audio = MP4(file_path)

    audio["\xa9nam"] = [track.title]
    audio["\xa9ART"] = [", ".join(track.artists)]
    audio["aART"] = [", ".join(track.artists)]
    if track.album:
        audio["\xa9alb"] = [track.album]
    if track.track_number is not None:
        total = track.total_tracks or 0
        audio["trkn"] = [(track.track_number, total)]
    if track.year:
        audio["\xa9day"] = [track.year]
    if track.genre:
        audio["\xa9gen"] = [track.genre]

    if cover_bytes:
        audio["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]

    audio.save()


# ──────────────────────────────────────────────────────────────
             
# ──────────────────────────────────────────────────────────────
def _tag_ogg(track, file_path: str, cover_bytes: bytes | None) -> None:
    audio = OggVorbis(file_path)

    audio["title"] = [track.title]
    audio["artist"] = [", ".join(track.artists)]
    if track.album:
        audio["album"] = [track.album]
    if track.track_number is not None:
        audio["tracknumber"] = [str(track.track_number)]
        if track.total_tracks is not None:
            audio["tracktotal"] = [str(track.total_tracks)]
    if track.year:
        audio["date"] = [track.year]
    if track.genre:
        audio["genre"] = [track.genre]
    if hasattr(track, 'isrc') and track.isrc:
        audio["isrc"] = [track.isrc]

    if cover_bytes:
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.desc = "Cover"
        pic.data = cover_bytes
        audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]

    audio.save()


# ──────────────────────────────────────────────────────────────
                           
# ──────────────────────────────────────────────────────────────
def _tag_opus(track, file_path: str, cover_bytes: bytes | None) -> None:
    audio = OggOpus(file_path)

    audio["title"] = [track.title]
    audio["artist"] = [", ".join(track.artists)]
    if track.album:
        audio["album"] = [track.album]
    if track.track_number is not None:
        audio["tracknumber"] = [str(track.track_number)]
        if track.total_tracks is not None:
            audio["tracktotal"] = [str(track.total_tracks)]
    if track.year:
        audio["date"] = [track.year]
    if track.genre:
        audio["genre"] = [track.genre]
    if hasattr(track, 'isrc') and track.isrc:
        audio["isrc"] = [track.isrc]

    if cover_bytes:
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.desc = "Cover"
        pic.data = cover_bytes
        audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]

    audio.save()