"""
core/api/routes.py
===================
FastAPI route definitions for the Spyde local API.

All download endpoints return a task_id immediately.
Clients poll GET /task/{task_id} for status/events.
"""

from __future__ import annotations

import traceback
import base64
import concurrent.futures

from fastapi import APIRouter, HTTPException, Query

from core.api.schemas import (
    SpotifyRequest,
    PlaylistRequest,
    YoutubeRequest,
    MediaRequest,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    # Pydantic schemas omit hidden attributes. Re-inject the Spotify Track ID
    # so the background enrichment pipelines can identify the track.
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

    # Swap the dummy future for the real executor future
    with _registry._lock:
        _registry._tasks[task_id]["future"] = fut

    return TaskResponse(task_id=task_id)


# ── Download endpoints ────────────────────────────────────────────────────────

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
    data = {"url": req.url, "title": req.title}
    options = req.options.model_dump()
    return _submit(_controller.download_generic, data, options)


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

        # Sanitize filename
        safe = re.sub(r'[<>:"/\\|?*]', '_', title).strip() or "cover"
        out_path = Path(_controller.download_dir) / f"{safe}.jpg"

        # Avoid overwriting — append counter if needed
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


# ── Task status / polling ─────────────────────────────────────────────────────

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


# ── Cancellation ──────────────────────────────────────────────────────────────

@router.post("/task/{task_id}/cancel", response_model=CancelResponse)
def cancel_task(task_id: str):
    """Cancel a running task."""
    ok, msg = _registry.cancel(task_id)
    return CancelResponse(task_id=task_id, cancelled=ok, message=msg)


# ── Warmup ────────────────────────────────────────────────────────────────────

@router.post("/warmup")
def warmup():
    """Trigger the background warmup sequence."""
    from core.spotify import _tm
    from fastapi import HTTPException
    
    if not getattr(_tm, "_warmup_done", False):
        raise HTTPException(status_code=503, detail="Warming up")
        
    return {"status": "ok"}


# ── Track / playlist info ─────────────────────────────────────────────────────

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
                # Direct Pathfinder query for album to get high-fidelity metadata
                payload = {
                    "variables": {"uri": f"spotify:album:{aid}", "offset": 0, "limit": 300},
                    "operationName": "queryAlbum", # Standard web player album query
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
                    # Synchronous ISRC fetch for single track since frontend closes connection immediately
                    track_item["isrc"] = get_track_isrc(track_id, token, session)
                
                yield f"data: {json.dumps({'type': 'track', 'track': track_item})}\n\n"

            else:
                from core.parser import InputParser
                items = InputParser.parse(url)
                if not items:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Unsupported URL'})}\n\n"
                    return
                
                t0 = items[0]
                t0 = items[0]
                if len(items) == 1:
                    track_item = {
                        "title": getattr(t0, "title", "Unknown"),
                        "artists": getattr(t0, "artists", []),
                        "album": getattr(t0, "album", None),
                        "duration": getattr(t0, "duration", 0),
                        "cover_url": getattr(t0, "cover_url", None),
                        "spotify_url": getattr(t0, "spotify_url", None),
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
                        track_item = {
                            "title": getattr(t, "title", "Unknown"),
                            "artists": getattr(t, "artists", []),
                            "album": getattr(t, "album", None),
                            "duration": getattr(t, "duration", 0),
                            "cover_url": getattr(t, "cover_url", None),
                            "spotify_url": getattr(t, "spotify_url", None),
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

