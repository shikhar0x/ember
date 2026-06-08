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


@router.get("/track/info", response_model=InspectResponse)
def get_track_info(url: str):
    """Fetch metadata for a Spotify URL — works for tracks, albums, and playlists."""
    from core.parser import InputParser
    try:
        items = InputParser.parse(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not items:
        raise HTTPException(status_code=404, detail="Could not resolve URL")

                  
    if len(items) == 1:
        return InspectResponse(
            type="track",
            track=_track_to_info(items[0]),
        )

                                         
    t0 = items[0]
    parent_title = getattr(t0, "parent_name", None) or getattr(t0, "album", None) or "Playlist"
    parent_owner = getattr(t0, "parent_owner", None) or "Spotify"
    parent_cover = getattr(t0, "parent_cover", None) or getattr(t0, "cover_url", None)

                                                                            
    albums = {getattr(t, "album", None) for t in items}
    resp_type = "album" if len(albums) == 1 and albums != {None} else "playlist"

    return InspectResponse(
        type=resp_type,
        title=parent_title,
        owner=parent_owner,
        cover_url=parent_cover,
        total_tracks=len(items),
        tracks=[_track_to_info(t) for t in items],
    )


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

