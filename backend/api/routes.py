"""
core/api/routes.py
===================
FastAPI route definitions for the Ember local API.

All download endpoints return a task_id immediately.
Clients poll GET /task/{task_id} for status/events.
"""

from __future__ import annotations

import traceback
import base64
import concurrent.futures

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    SpotifyRequest,
    PlaylistRequest,
    YoutubeRequest,
    YTMusicRequest,
    MediaRequest,
    EmbedMetadataRequest,
    ManualPairRequest,
    TaskResponse,
    TaskStatus,
    CancelResponse,
    TrackInfoResponse,
    InspectResponse,
    TrackSchema,
)
from core.models import Track

router = APIRouter()

                                            
_controller = None
_registry = None


def init_routes(controller, registry):
    """Called once at startup to inject shared instances."""
    global _controller, _registry
    _controller = controller
    _registry = registry

@router.get("/me")
def get_me():
    from core.spotify import _tm
    profile = getattr(_tm, "_user_profile", None)
    is_loading = getattr(_tm, "_profile_loading", False)
    if not profile:
        profile = {"display_name": "User", "avatar_url": None, "uri": ""}
    result = dict(profile)
    result["is_loading"] = is_loading
    return result

def _track_from_schema(s) -> Track:
    """Convert a Pydantic TrackSchema to a core.models.Track dataclass."""
    t = Track(
        title=s.title,
        artists=s.artists,
        album=s.album,
        duration=s.duration,
        track_number=s.track_number,
        total_tracks=s.total_tracks,
        year=s.year,
        genre=s.genre,
        cover_url=s.cover_url,
        spotify_url=s.spotify_url,
        isrc=s.isrc,
        source=s.source,
        media_type=s.media_type,
    )
    if s.spotify_url and "/track/" in s.spotify_url:
        t._spotify_track_id = s.spotify_url.split("/track/")[-1].split("?")[0].strip()
    return t


def _submit(submit_fn, *args, **kwargs) -> TaskResponse:
    """
    Create a task_id + callback before submitting work, avoiding
    the race condition of submitting then retroactively attaching a callback.

    Uses a dummy future to reserve a task_id, creates the callback,
    then submits the real work with the callback wired in.
    """
    dummy = concurrent.futures.Future()
    task_id = _registry.create(dummy)
    cb = _registry.make_callback(task_id)

    fut = submit_fn(*args, callback=cb, **kwargs)

    with _registry._lock:
        _registry._tasks[task_id]["future"] = fut

    return TaskResponse(task_id=task_id)


@router.post("/download/spotify", response_model=TaskResponse)
def download_spotify(req: SpotifyRequest):
    """Start a single Spotify track download."""
    options = req.options.model_dump()
    if req.track:
        track = _track_from_schema(req.track)
        return _submit(_controller.download, track, options)
    elif req.url:
        def _worker(callback=None):
            from core.events import emit, status_event, error_event
            from core.parser import InputParser
            from core.services import spotify_downloader
            emit(callback, status_event("Resolving Spotify URL..."))
            try:
                items = InputParser.parse(req.url)
                if not items:
                    emit(callback, error_event("Failed to resolve Spotify track"))
                    return
                spotify_downloader.download_track(
                    items[0], options, _controller.download_dir, callback
                )
            except Exception as e:
                traceback.print_exc()
                emit(callback, error_event(str(e)))
        
        def _submit_worker(callback=None):
            fut = _controller._executor.submit(_worker, callback=callback)
            return _controller._track_future(fut)
            
        return _submit(_submit_worker)
    else:
        raise HTTPException(status_code=400, detail="Must provide 'url' or 'track'")


@router.post("/download/playlist", response_model=TaskResponse)
def download_playlist(req: PlaylistRequest):
    """Start a playlist batch download."""
    tracks = [_track_from_schema(t) for t in req.tracks]
    options = req.options.model_dump()
    return _submit(
        _controller.download_playlist,
        tracks, options,
        playlist_title=req.playlist_title,
    )


@router.post("/download/youtube", response_model=TaskResponse)
def download_youtube(req: YoutubeRequest):
    """Start a YouTube/generic URL download."""
    options = req.options.model_dump()
    if req.track:
        track = _track_from_schema(req.track)
        if not track.spotify_url and req.url:
            track.spotify_url = req.url
        print(f"[Ember] YouTube Download: Starting download for \"{track.title}\"...")
        return _submit(_controller.download_generic, track, options)
    elif req.url:
        print(f"[Ember] YouTube Download: Starting download for \"{req.title}\"...")
        data = {"url": req.url, "title": req.title}
        return _submit(_controller.download_generic, data, options)
    else:
        raise HTTPException(status_code=400, detail="Must provide 'url' or 'track'")


@router.post("/download/ytmusic", response_model=TaskResponse)
def download_ytmusic(req: YTMusicRequest):
    """Start a YouTube Music track download (via yt-dlp)."""
    options = req.options.model_dump()
    if req.track:
        track = _track_from_schema(req.track)
        if not track.spotify_url and req.url:
            track.spotify_url = req.url
        print(f"[Ember] YTMusic Download: Starting download for \"{track.title}\"...")
        return _submit(_controller.download_generic, track, options)
    elif req.url:
        print(f"[Ember] YTMusic Download: Starting download for \"{req.title}\"...")
        data = {"url": req.url, "title": req.title}
        return _submit(_controller.download_generic, data, options)
    else:
        raise HTTPException(status_code=400, detail="Must provide 'url' or 'track'")


@router.post("/download/media", response_model=TaskResponse)
def download_media(req: MediaRequest):
    """Start an image/mixed-media download."""
    data = {
        "title": req.title,
        "url": req.url,
        "spotify_url": req.spotify_url,
        "carousel": req.carousel or {},
    }
                                         
    if req.thumbnail_bytes_b64:
        data["thumbnail_bytes"] = base64.b64decode(req.thumbnail_bytes_b64)

    return _submit(_controller.download_media, data)


@router.post("/download/cover")
def download_cover(url: str = Query(...), title: str = Query("cover")):
    """Download cover art image to the default download directory."""
    import re
    import requests
    from pathlib import Path

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch cover image")

        safe = re.sub(r'[<>:"/\\|?*]', '_', title).strip() or "cover"
        out_path = Path(_controller.download_dir) / f"{safe}.jpg"

        counter = 1
        while out_path.exists():
            out_path = Path(_controller.download_dir) / f"{safe} ({counter}).jpg"
            counter += 1

        out_path.write_bytes(r.content)
        return {"status": "ok", "path": str(out_path)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embed/metadata", response_model=TaskResponse)
def embed_metadata(req: EmbedMetadataRequest):
    """Embed Spotify/YTMusic metadata onto an existing local audio file."""
    def _worker(callback=None):
        from core.services.metadata_embedder import embed_metadata_on_file
        embed_metadata_on_file(req.file_path, req.source_url, callback)

    def _submit_worker(callback=None):
        fut = _controller._executor.submit(_worker, callback=callback)
        return _controller._track_future(fut)

    return _submit(_submit_worker)


@router.post("/download/manual_pair", response_model=TaskResponse)
def download_manual_pair(req: ManualPairRequest):
    track = _track_from_schema(req.spotify_track)
    options = req.options.model_dump()
    from core.services import spotify_downloader

    def _submit_worker(callback=None):
        fut = _controller._executor.submit(
            spotify_downloader.download_track_manual,
            track, req.youtube_url, options, _controller.download_dir, callback=callback
        )
        return _controller._track_future(fut)

    return _submit(_submit_worker)


@router.get("/audio/cover")
def get_audio_cover(file_path: str):
    import os
    from fastapi import Response
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    import base64

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    ext = os.path.splitext(file_path)[1].lower()
    cover_bytes = None
    mime_type = "image/jpeg"

    try:
        if ext == ".mp3":
            audio = MP3(file_path)
            apics = audio.tags.getall('APIC') if audio.tags else []
            if apics:
                cover_bytes = apics[0].data
                mime_type = apics[0].mime or "image/jpeg"
        elif ext == ".flac":
            audio = FLAC(file_path)
            if audio.pictures:
                cover_bytes = audio.pictures[0].data
                mime_type = audio.pictures[0].mime or "image/jpeg"
        elif ext in (".m4a", ".mp4"):
            audio = MP4(file_path)
            if "covr" in audio:
                cover_bytes = audio["covr"][0]
        elif ext in (".ogg", ".opus"):
            audio = OggVorbis(file_path) if ext == ".ogg" else OggOpus(file_path)
            if "metadata_block_picture" in audio:
                from mutagen.flac import Picture
                for b64_data in audio["metadata_block_picture"]:
                    try:
                        pic_data = base64.b64decode(b64_data)
                        pic = Picture(pic_data)
                        cover_bytes = pic.data
                        mime_type = pic.mime or "image/jpeg"
                        break
                    except Exception:
                        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not cover_bytes:
        raise HTTPException(status_code=404, detail="No cover art found in file")

    return Response(content=cover_bytes, media_type=mime_type)


@router.get("/audio/inspect", response_model=TrackInfoResponse)
def inspect_local_file(file_path: str):
    import os
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    import traceback

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    ext = os.path.splitext(file_path)[1].lower()
    
    meta = {
        "title": os.path.basename(file_path),
        "artists": ["Unknown Artist"],
        "album": "",
        "duration": 0,
        "track_number": None,
        "total_tracks": None,
        "year": None,
        "genre": None,
        "cover_url": None,
        "source": "local",
        "media_type": "audio",
        "local_file_path": file_path
    }

    def _safe_str(val):
        if not val:
            return ""
        if isinstance(val, list):
            return str(val[0]) if len(val) > 0 else ""
        return str(val)

    def _safe_artists(val):
        s = _safe_str(val)
        if not s:
            return ["Unknown Artist"]
        parts = [a.strip() for a in s.replace("/", ";").replace(",", ";").replace(" • ", ";").split(";") if a.strip()]
        return parts if parts else ["Unknown Artist"]

    def _safe_int(val):
        try:
            if not val:
                return None
            if isinstance(val, list) or isinstance(val, tuple):
                return int(val[0]) if len(val) > 0 else None
            return int(val)
        except (ValueError, TypeError):
            return None

    try:
        if ext == ".mp3":
            audio = MP3(file_path)
            if audio.info:
                meta["duration"] = int(audio.info.length)
            if audio.tags:
                tags = audio.tags
                if "TIT2" in tags:
                    title_val = _safe_str(tags["TIT2"].text)
                    if title_val:
                        meta["title"] = title_val
                if "TPE1" in tags:
                    meta["artists"] = _safe_artists(tags["TPE1"].text)
                if "TALB" in tags:
                    meta["album"] = _safe_str(tags["TALB"].text)
                if "TYER" in tags:
                    meta["year"] = _safe_str(tags["TYER"].text)
                elif "TDRC" in tags:
                    meta["year"] = _safe_str(tags["TDRC"].text)
                if "TCON" in tags:
                    meta["genre"] = _safe_str(tags["TCON"].text)
                if "TRCK" in tags:
                    track_val = _safe_str(tags["TRCK"].text)
                    if "/" in track_val:
                        parts = track_val.split("/")
                        meta["track_number"] = _safe_int(parts[0])
                        meta["total_tracks"] = _safe_int(parts[1])
                    else:
                        meta["track_number"] = _safe_int(track_val)
                if tags.getall("APIC"):
                    meta["cover_url"] = f"http://127.0.0.1:8008/audio/cover?file_path={file_path}"
        elif ext == ".flac":
            audio = FLAC(file_path)
            if audio.info:
                meta["duration"] = int(audio.info.length)
            if "title" in audio:
                title_val = _safe_str(audio["title"])
                if title_val:
                    meta["title"] = title_val
            if "artist" in audio:
                meta["artists"] = _safe_artists(audio["artist"])
            if "album" in audio:
                meta["album"] = _safe_str(audio["album"])
            if "date" in audio:
                meta["year"] = _safe_str(audio["date"])
            if "genre" in audio:
                meta["genre"] = _safe_str(audio["genre"])
            if "tracknumber" in audio:
                meta["track_number"] = _safe_int(audio["tracknumber"])
            if "tracktotal" in audio:
                meta["total_tracks"] = _safe_int(audio["tracktotal"])
            if audio.pictures:
                meta["cover_url"] = f"http://127.0.0.1:8008/audio/cover?file_path={file_path}"
        elif ext in (".m4a", ".mp4"):
            audio = MP4(file_path)
            if audio.info:
                meta["duration"] = int(audio.info.length)
            if "\xa9nam" in audio:
                title_val = _safe_str(audio["\xa9nam"])
                if title_val:
                    meta["title"] = title_val
            if "\xa9ART" in audio:
                meta["artists"] = _safe_artists(audio["\xa9ART"])
            elif "aART" in audio:
                meta["artists"] = _safe_artists(audio["aART"])
            if "\xa9alb" in audio:
                meta["album"] = _safe_str(audio["\xa9alb"])
            if "\xa9day" in audio:
                meta["year"] = _safe_str(audio["\xa9day"])
            if "\xa9gen" in audio:
                meta["genre"] = _safe_str(audio["\xa9gen"])
            if "trkn" in audio:
                trkn_val = audio["trkn"]
                if trkn_val and (isinstance(trkn_val, list) or isinstance(trkn_val, tuple)):
                    val = trkn_val[0]
                    if isinstance(val, tuple) or isinstance(val, list):
                        meta["track_number"] = _safe_int(val[0])
                        meta["total_tracks"] = _safe_int(val[1]) if len(val) > 1 else None
                    else:
                        meta["track_number"] = _safe_int(val)
            if "covr" in audio:
                meta["cover_url"] = f"http://127.0.0.1:8008/audio/cover?file_path={file_path}"
        elif ext in (".ogg", ".opus"):
            audio = OggVorbis(file_path) if ext == ".ogg" else OggOpus(file_path)
            if audio.info:
                meta["duration"] = int(audio.info.length)
            if "title" in audio:
                title_val = _safe_str(audio["title"])
                if title_val:
                    meta["title"] = title_val
            if "artist" in audio:
                meta["artists"] = _safe_artists(audio["artist"])
            if "album" in audio:
                meta["album"] = _safe_str(audio["album"])
            if "date" in audio:
                meta["year"] = _safe_str(audio["date"])
            if "genre" in audio:
                meta["genre"] = _safe_str(audio["genre"])
            if "tracknumber" in audio:
                meta["track_number"] = _safe_int(audio["tracknumber"])
            if "tracktotal" in audio:
                meta["total_tracks"] = _safe_int(audio["tracktotal"])
            if "metadata_block_picture" in audio:
                meta["cover_url"] = f"http://127.0.0.1:8008/audio/cover?file_path={file_path}"
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    return TrackInfoResponse(**meta)


@router.get("/task/{task_id}", response_model=TaskStatus)
def get_task(task_id: str):
    """Get full task status including all events."""
    result = _registry.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(**result)


@router.get("/task/{task_id}/events")
def get_task_events(task_id: str, cursor: int = Query(0, ge=0)):
    """Get events since *cursor* (for incremental polling)."""
    result = _registry.get_events_since(task_id, cursor)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/task/{task_id}/cancel", response_model=CancelResponse)
def cancel_task(task_id: str):
    """Cancel a running task."""
    ok, msg = _registry.cancel(task_id)
    return CancelResponse(task_id=task_id, cancelled=ok, message=msg)


@router.post("/task/{task_id}/pause")
def pause_task(task_id: str):
    """Pause a running task."""
    ok, msg = _registry.pause(task_id)
    return {"task_id": task_id, "paused": ok, "message": msg}


@router.post("/task/{task_id}/resume")
def resume_task(task_id: str):
    """Resume a paused task."""
    ok, msg = _registry.resume(task_id)
    return {"task_id": task_id, "resumed": ok, "message": msg}


@router.post("/warmup")
def warmup():
    """Trigger the background warmup sequence."""
    from core.spotify import _tm
    from fastapi import HTTPException
    
    if not getattr(_tm, "_warmup_done", False):
        raise HTTPException(status_code=503, detail="Warming up")
        
    return {"status": "ok"}


def _track_to_info(t) -> TrackInfoResponse:
    """Convert a core.models.Track (or similar) to a TrackInfoResponse."""
    return TrackInfoResponse(
        title=getattr(t, "title", "Unknown"),
        artists=getattr(t, "artists", []),
        album=getattr(t, "album", None),
        duration=getattr(t, "duration", 0),
        track_number=getattr(t, "track_number", None),
        total_tracks=getattr(t, "total_tracks", None),
        year=getattr(t, "year", None),
        genre=getattr(t, "genre", None),
        cover_url=getattr(t, "cover_url", getattr(t, "thumbnail_url", None)),
        spotify_url=getattr(t, "spotify_url", getattr(t, "url", None)),
        isrc=getattr(t, "isrc", None),
        source=getattr(t, "source", "spotify"),
        media_type=getattr(t, "media_type", "audio"),
    )


@router.get("/inspect")
def inspect_url(url: str):
    from fastapi.responses import StreamingResponse
    import json
    import threading
    import concurrent.futures
    import traceback
    import requests
    from requests.adapters import HTTPAdapter

    from core.spotify import _tm
    from core.spotify_client import get_track, get_playlist_generator
    from sdk.isrc import get_track_isrc
    from core.spotify_client import get_playlist_generator

    def stream():
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)
        futures = {}
        
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        session.mount("https://", adapter)

        token = _tm.get_headers()

        def _raw_to_track(t, idx, parent_cover=None):
            return {
                "title": t.get("title", "Unknown"),
                "artists": [a for a in t.get("artists", []) if a],
                "album": t.get("album"),
                "duration": t.get("duration_s", 0),
                "cover_url": t.get("cover_url") or parent_cover,
                "spotify_url": t.get("spotify_url"),
                "isrc": None,
                "year": str(t.get("year")) if t.get("year") else None,
                "source": "spotify",
                "media_type": "audio",
                "track_number": t.get("track_number"),
                "total_tracks": t.get("total_tracks", 0),
                "genre": t.get("genre"),
            }

        try:
            if "playlist/" in url:
                pid = url.split("playlist/")[-1].split("?")[0]
                first_chunk = True
                track_index = 0
                for meta, chunk in get_playlist_generator(pid, _tm):
                    if first_chunk:
                        header = {
                            "type": "header",
                            "meta": {
                                "type": "playlist",
                                "title": meta.get("name"),
                                "owner": meta.get("owner"),
                                "cover_url": meta.get("cover_url"),
                                "total_tracks": meta.get("total") or len(chunk),
                            }
                        }
                        yield f"data: {json.dumps(header)}\n\n"
                        first_chunk = False
                    
                    for t in chunk:
                        track_item = _raw_to_track(t, track_index, meta.get("cover_url"))
                        tid = t.get("track_id")
                        if tid:
                            fut = executor.submit(get_track_isrc, tid, token, session)
                            futures[fut] = (track_index, track_item)
                        
                        yield f"data: {json.dumps({'type': 'track_item', 'index': track_index, 'track': track_item})}\n\n"
                        track_index += 1

            elif "album/" in url:
                aid = url.split("album/")[-1].split("?")[0]
                payload = {
                    "variables": {"uri": f"spotify:album:{aid}", "offset": 0, "limit": 300},
                    "operationName": "queryAlbum",
                    "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "ce390dbf7ca6b61a23aec210619e1094fe9d23d7f101ff773ce1146f84d4dd10"}},
                }
                r = _tm.request("POST", "https://api-partner.spotify.com/pathfinder/v1/query", json=payload)
                album_data = r.json().get("data", {}).get("albumUnion", {})
                
                if not album_data:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Album not found'})}\n\n"
                    return
                    
                cover_sources = album_data.get("coverArt", {}).get("sources", [])
                cover_url = max(cover_sources, key=lambda s: s.get("height", 0)).get("url") if cover_sources else None
                album_name = album_data.get("name", "Unknown")
                album_owner = album_data.get("artists", {}).get("items", [{}])[0].get("profile", {}).get("name", "Unknown")
                
                raw_items = album_data.get("tracksV2", {}).get("items", [])
                raw_tracks = []
                for item in raw_items:
                    t = item.get("track", {})
                    if not t: continue
                    raw_tracks.append({
                        "title": t.get("name", "Unknown"),
                        "artists": [a.get("profile", {}).get("name") for a in t.get("artists", {}).get("items", []) if a.get("profile", {}).get("name")],
                        "album": album_name,
                        "duration_s": t.get("duration", {}).get("totalMilliseconds", 0) // 1000,
                        "track_number": t.get("trackNumber"),
                        "cover_url": cover_url,
                        "spotify_url": f"https://open.spotify.com/track/{t.get('id')}" if t.get("id") else None,
                        "track_id": t.get("id"),
                        "year": str((album_data.get("date") or {}).get("year", "")) if (album_data.get("date") or {}).get("year") else None,
                    })

                header = {
                    "type": "header",
                    "meta": {
                        "type": "album",
                        "title": album_name,
                        "owner": album_owner,
                        "cover_url": cover_url,
                        "total_tracks": len(raw_tracks),
                    }
                }
                yield f"data: {json.dumps(header)}\n\n"
                
                for i, t in enumerate(raw_tracks):
                    track_item = _raw_to_track(t, i, cover_url)
                    tid = t.get("track_id")
                    if tid:
                        fut = executor.submit(get_track_isrc, tid, token, session)
                        futures[fut] = (i, track_item)
                        
                    yield f"data: {json.dumps({'type': 'track_item', 'index': i, 'track': track_item})}\n\n"

            elif "track/" in url:
                tid = url.split("track/")[-1].split("?")[0]
                data = get_track(tid, _tm)
                if not data or data.get("error"):
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Track not found'})}\n\n"
                    return
                
                track_item = _raw_to_track(data, 0, data.get("cover_url"))
                track_id = data.get("track_id") or tid
                if track_id:
                    track_item["isrc"] = get_track_isrc(track_id, token, session)
                
                yield f"data: {json.dumps({'type': 'track', 'track': track_item})}\n\n"

            elif "music.youtube.com" in url:
                from core.ytmusic_metadata import (
                    extract_ids, get_best_thumbnail, process_track,
                    build_album_art_cache, find_album_via_search,
                )
                from ytmusicapi import YTMusic

                video_id, list_id, album_id = extract_ids(url)
                yt = YTMusic()

                def _ytm_track_to_dict(t):
                    """Convert a process_track() result to the standard track dict."""
                    artists = [a["name"] for a in t.get("artists", []) if a.get("name")]
                    return {
                        "title": t.get("title", "Unknown"),
                        "artists": artists or ["Unknown Artist"],
                        "album": (t.get("album") or {}).get("name"),
                        "duration": t.get("duration_seconds", 0) or 0,
                        "cover_url": t.get("cover_art_url") or t.get("video_thumbnail_url"),
                        "spotify_url": t.get("url"),
                        "isrc": None,
                        "year": str(t.get("year")) if t.get("year") else None,
                        "source": "ytmusic",
                        "media_type": "audio",
                        "track_number": None,
                        "total_tracks": None,
                        "genre": None,
                    }

                if album_id and not list_id:
                    print(f"[Ember] YouTube Music: Detected album URL: {album_id}")
                    print(f"[Ember] YouTube Music: Fetching album metadata for {album_id}...")
                    album = yt.get_album(browseId=album_id)
                    album_art_url = get_best_thumbnail(album.get("thumbnails", []), size=544)
                    album_art_cache = {album_id: {"url": album_art_url, "year": album.get("year")}}
                    album_context = {
                        "name": album.get("title"),
                        "id": album_id,
                        "thumbnails": album.get("thumbnails", []),
                        "year": album.get("year"),
                    }
                    raw_tracks = album.get("tracks", [])
                    total = len(raw_tracks)
                    print(f"[Ember] YouTube Music: Album '{album.get('title')}' — {total} tracks")

                    album_artists = album.get("artists", [])
                    owner = album_artists[0].get("name", "Unknown") if album_artists and isinstance(album_artists[0], dict) else str(album_artists[0]) if album_artists else "Unknown"
                    header = {
                        "type": "header",
                        "meta": {
                            "type": "album",
                            "title": album.get("title", "Unknown Album"),
                            "owner": owner,
                            "cover_url": album_art_url,
                            "year": str(album.get("year")) if album.get("year") else None,
                            "total_tracks": total,
                        }
                    }
                    yield f"data: {json.dumps(header)}\n\n"

                    for i, t in enumerate(raw_tracks):
                        result = process_track(t, art_size=544, album_art_cache=album_art_cache, album_context=album_context)
                        track_item = _ytm_track_to_dict(result)
                        track_item["track_number"] = i + 1
                        track_item["total_tracks"] = total
                        track_item["cover_url"] = album_art_url
                        print(f"[Ember] YouTube Music: Streaming track {i+1}/{total}: {track_item['title']}")
                        yield f"data: {json.dumps({'type': 'track_item', 'index': i, 'track': track_item})}\n\n"

                elif list_id and not list_id.startswith("RD"):
                    print(f"[Ember] YouTube Music: Detected playlist URL: {list_id}")
                    print(f"[Ember] YouTube Music: Fetching playlist metadata...")
                    pl = yt.get_playlist(list_id, limit=300)
                    raw_tracks = pl.get("tracks", [])
                    total = len(raw_tracks)
                    playlist_cover = get_best_thumbnail(pl.get("thumbnails", []), size=544)
                    print(f"[Ember] YouTube Music: Resolved {total} tracks from playlist '{pl.get('title')}'")

                    header = {
                        "type": "header",
                        "meta": {
                            "type": "playlist",
                            "title": pl.get("title", "Unknown Playlist"),
                            "owner": (pl.get("author") or {}).get("name", "YouTube Music") if isinstance(pl.get("author"), dict) else str(pl.get("author", "YouTube Music")),
                            "cover_url": playlist_cover,
                            "total_tracks": total,
                        }
                    }
                    yield f"data: {json.dumps(header)}\n\n"

                    track_album_map = {}
                    for i, t in enumerate(raw_tracks):
                        result = process_track(t, art_size=544, album_art_cache={})
                        track_item = _ytm_track_to_dict(result)
                        track_item["track_number"] = i + 1
                        track_item["total_tracks"] = total
                        track_item["cover_url"] = track_item["cover_url"] or playlist_cover
                        print(f"[Ember] YouTube Music: Streaming track {i+1}/{total}: {track_item['title']}")
                        yield f"data: {json.dumps({'type': 'track_item', 'index': i, 'track': track_item})}\n\n"

                        album_data = t.get("album") or {}
                        aid = album_data.get("id") if isinstance(album_data, dict) else None
                        if aid:
                            track_album_map[i] = aid

                    if track_album_map:
                        unique_album_ids = list(set(track_album_map.values()))
                        print(f"[Ember] YouTube Music: Resolving cover art for {len(unique_album_ids)} albums in background...")
                        album_art_cache = build_album_art_cache(unique_album_ids, art_size=544, workers=6)

                        for idx, aid in track_album_map.items():
                            art_data = album_art_cache.get(aid)
                            if art_data:
                                updates = {}
                                if isinstance(art_data, dict):
                                    if art_data.get("url"): updates["cover_url"] = art_data.get("url")
                                    if art_data.get("year"): updates["year"] = str(art_data.get("year"))
                                else:
                                    updates["cover_url"] = art_data
                                if updates:
                                    yield f"data: {json.dumps({'type': 'update', 'index': idx, 'updates': updates})}\n\n"

                        if album_art_cache:
                            from collections import Counter
                            valid_aids = [a for a in track_album_map.values() if a in album_art_cache]
                            if valid_aids:
                                most_common_aid = Counter(valid_aids).most_common(1)[0][0]
                                resolved_data = album_art_cache.get(most_common_aid)
                                header_updates = {}
                                
                                if not playlist_cover:
                                    resolved_cover = resolved_data.get("url") if isinstance(resolved_data, dict) else resolved_data
                                    if resolved_cover:
                                        header_updates["cover_url"] = resolved_cover
                                        
                                if isinstance(resolved_data, dict) and resolved_data.get("year"):
                                    header_updates["year"] = str(resolved_data.get("year"))
                                    
                                if header_updates:
                                    print(f"[Ember] YouTube Music: Updating main header from resolved album metadata")
                                    yield f"data: {json.dumps({'type': 'header_update', 'updates': header_updates})}\n\n"

                        print(f"[Ember] YouTube Music: Cover art resolved for {len(album_art_cache)} albums")

                elif video_id:
                    print(f"[Ember] YouTube Music: Detected track URL: {video_id}")
                    print(f"[Ember] YouTube Music: Fetching track metadata...")
                    song = yt.get_song(videoId=video_id)
                    video_details = song.get("videoDetails", {})
                    watch = {}
                    for _ in range(3):
                        try:
                            watch = yt.get_watch_playlist(videoId=video_id)
                            break
                        except KeyError:
                            import time
                            time.sleep(0.5)
                    track = watch.get("tracks", [{}])[0] if watch.get("tracks") else {}

                    if "thumbnail" not in track and video_details.get("thumbnail"):
                        track["thumbnail"] = video_details["thumbnail"].get("thumbnails", [])
                    track["title"] = track.get("title") or video_details.get("title")
                    track["videoId"] = video_id
                    if "lengthSeconds" in video_details:
                        track["duration_seconds"] = int(video_details["lengthSeconds"])
                    if not track.get("artists") and video_details.get("author"):
                        track["artists"] = [{"name": n.strip(), "id": None} for n in video_details.get("author", "").replace(" - Topic", "").split(" • ") if n.strip()]

                    album_data = track.get("album")
                    if not album_data:
                        artists_list = [{"name": a["name"]} for a in track.get("artists", [])]
                        alb, src = find_album_via_search(yt, track["title"], artists_list, video_id)
                        if alb:
                            track["album"] = alb

                    album_id_resolved = (track.get("album") or {}).get("id") if isinstance(track.get("album"), dict) else None
                    album_art_cache = build_album_art_cache([album_id_resolved], art_size=544, workers=1) if album_id_resolved else {}

                    result = process_track(track, video_id, art_size=544, album_art_cache=album_art_cache)
                    track_item = _ytm_track_to_dict(result)
                    print(f"[Ember] YouTube Music: Resolved track: {track_item['title']} — {', '.join(track_item['artists'])}")
                    yield f"data: {json.dumps({'type': 'track', 'track': track_item})}\n\n"

                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Could not parse YouTube Music URL'})}\n\n"

            else:
                from core.parser import InputParser
                items = InputParser.parse(url)
                if not items:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Unsupported URL'})}\n\n"
                    return
                
                t0 = items[0]
                t0 = items[0]
                if len(items) == 1:
                    uploader = getattr(t0, "uploader", None)
                    artists = getattr(t0, "artists", [])
                    if not artists and uploader:
                        artists = [uploader]

                    track_item = {
                        "title": getattr(t0, "title", "Unknown"),
                        "artists": artists,
                        "album": getattr(t0, "album", None),
                        "duration": getattr(t0, "duration", 0),
                        "cover_url": getattr(t0, "cover_url", getattr(t0, "thumbnail_url", None)),
                        "spotify_url": getattr(t0, "spotify_url", getattr(t0, "url", None)),
                        "isrc": getattr(t0, "isrc", None),
                        "year": getattr(t0, "year", None),
                        "source": getattr(t0, "source", "spotify"),
                        "media_type": getattr(t0, "media_type", "audio"),
                        "track_number": getattr(t0, "track_number", None),
                        "total_tracks": getattr(t0, "total_tracks", 0),
                        "genre": getattr(t0, "genre", None),
                    }
                    yield f"data: {json.dumps({'type': 'track', 'track': track_item})}\n\n"
                else:
                    header = {
                        "type": "header",
                        "meta": {
                            "type": "playlist",
                            "title": getattr(t0, "parent_name", None) or getattr(t0, "album", None) or "Playlist",
                            "owner": getattr(t0, "parent_owner", None) or "Spotify",
                            "cover_url": getattr(t0, "parent_cover", None) or getattr(t0, "cover_url", None),
                            "total_tracks": len(items),
                        }
                    }
                    yield f"data: {json.dumps(header)}\n\n"

                    for i, t in enumerate(items):
                        uploader = getattr(t, "uploader", None)
                        artists = getattr(t, "artists", [])
                        if not artists and uploader:
                            artists = [uploader]

                        track_item = {
                            "title": getattr(t, "title", "Unknown"),
                            "artists": artists,
                            "album": getattr(t, "album", None),
                            "duration": getattr(t, "duration", 0),
                            "cover_url": getattr(t, "cover_url", getattr(t, "thumbnail_url", None)),
                            "spotify_url": getattr(t, "spotify_url", getattr(t, "url", None)),
                            "isrc": getattr(t, "isrc", None),
                            "year": getattr(t, "year", None),
                            "source": getattr(t, "source", "spotify"),
                            "media_type": getattr(t, "media_type", "audio"),
                            "track_number": getattr(t, "track_number", None),
                            "total_tracks": getattr(t, "total_tracks", 0),
                            "genre": getattr(t, "genre", None),
                        }
                        yield f"data: {json.dumps({'type': 'track_item', 'index': i, 'track': track_item})}\n\n"

            for fut in concurrent.futures.as_completed(futures):
                try:
                    isrc = fut.result()
                    if isrc:
                        idx, t = futures[fut]
                        yield f"data: {json.dumps({'type': 'update', 'index': idx, 'updates': {'isrc': isrc}})}\n\n"
                except Exception as e:
                    traceback.print_exc()

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
        finally:
            executor.shutdown(wait=False)
            session.close()

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/track/enrich", response_model=TrackSchema)
def enrich_track(track_data: TrackSchema):
    """Enrich a single track with cover art and ISRC."""
    from core.spotify_client import get_track_with_isrc
    from core.spotify import _tm
    
    t = _track_from_schema(track_data)
    
    sp_url = getattr(t, "spotify_url", None) or ""
    if "/track/" in sp_url:
        tid = sp_url.split("/track/")[-1].split("?")[0].strip()
        if tid:
            try:
                data = get_track_with_isrc(tid, _tm)
                if data and not data.get("error"):
                    if data.get("isrc") and not t.isrc:
                        t.isrc = data["isrc"]
                    if data.get("cover_url") and not t.cover_url:
                        t.cover_url = data["cover_url"]
                    if data.get("album") and (not t.album or t.album == getattr(t, "_playlist_name", None)):
                        t.album = data["album"]
                    if data.get("duration_s") and not t.duration:
                        t.duration = data["duration_s"]
            except Exception as e:
                print(f"[Enrich Error] {tid}: {e}")

    return TrackSchema(
        title=t.title,
        artists=t.artists,
        album=t.album,
        duration=t.duration,
        track_number=t.track_number,
        total_tracks=t.total_tracks,
        year=t.year,
        genre=t.genre,
        cover_url=t.cover_url,
        spotify_url=t.spotify_url,
        isrc=t.isrc,
        source=t.source,
        media_type=t.media_type
    )

