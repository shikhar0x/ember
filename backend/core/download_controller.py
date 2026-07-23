"""
core/download_controller.py
============================
Thin facade: owns ONE shared ThreadPoolExecutor, tracks futures,
exposes public API, and delegates all actual work to service modules.

All callbacks receive ONE structured dict payload (see core/events.py).

GUI interaction contract:
    controller.download(track, options, callback=cb)
    controller.download_playlist(tracks, options, callback=cb)
    controller.download_generic(data, options, callback=cb)
    controller.download_media(data, callback=cb)
    controller.shutdown()
"""

from __future__ import annotations

import threading
import concurrent.futures
from pathlib import Path
from typing import Callable, Optional

from core.utils import sanitize_filename as core_sanitize, open_folder
from core.events import emit, batch_event, batch_end_event, progress_event

                                                                      
from core.http_helper import get_bytes

                 
from core.services import spotify_downloader as _spotify
from core.services import youtube_downloader as _youtube
from core.services import media_downloader   as _media


class DownloadController:
    """
    Owns ONE shared ThreadPoolExecutor for all background download work.
    Tracks futures so they can be cancelled.
    All heavy lifting delegated to core.services.*.
    """

    def __init__(self, download_dir: Path, max_workers: int = 3):
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._futures: list[concurrent.futures.Future] = []
        self._lock = threading.Lock()

    def _track_future(self, fut: concurrent.futures.Future) -> concurrent.futures.Future:
        """Register a future and auto-remove it on completion."""
        with self._lock:
            self._futures.append(fut)

        def _cleanup(f):
            with self._lock:
                if f in self._futures:
                    self._futures.remove(f)
        fut.add_done_callback(_cleanup)
        return fut

    def download(
        self,
        track,
        options: dict,
        *,
        target_dir: Optional[Path] = None,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> concurrent.futures.Future:
        """Submit a single-track Spotify download to the executor."""
        fut = self._executor.submit(
            _spotify.download_track,
            track, options, target_dir or self.download_dir, callback,
        )
        return self._track_future(fut)

    def download_playlist(
        self,
        tracks: list,
        options: dict,
        *,
        playlist_title: str = "Playlist",
        callback: Optional[Callable[[dict], None]] = None,
    ) -> concurrent.futures.Future:
        """Submit a full playlist batch download to the executor."""
        fut = self._executor.submit(
            self._playlist_worker,
            tracks, options, playlist_title, callback,
        )
        return self._track_future(fut)

    def download_generic(
        self,
        data: dict,
        options: dict,
        *,
        target_dir: Optional[Path] = None,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> concurrent.futures.Future:
        """Submit a YouTube / direct-URL download to the executor."""
        fut = self._executor.submit(
            _youtube.download_generic,
            data, options, target_dir or self.download_dir, callback,
        )
        return self._track_future(fut)

    def download_media(
        self,
        data: dict,
        *,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> concurrent.futures.Future:
        """Submit an image/mixed-media download to the executor."""
        fut = self._executor.submit(
            _media.download_media,
            data, self.download_dir, callback,
        )
        return self._track_future(fut)

    def shutdown(self) -> None:
        """Clean executor shutdown — called on app close."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _playlist_worker(
        self,
        tracks: list,
        options: dict,
        playlist_title: str,
        callback: Optional[Callable[[dict], None]],
    ) -> None:
        """Batch-download selected tracks using the shared executor."""
        safe_pl = core_sanitize(playlist_title) or "Playlist_Download"
        pl_dir  = self.download_dir / safe_pl
        pl_dir.mkdir(parents=True, exist_ok=True)

        total     = len(tracks)
        completed = 0
        succeeded = 0
        failed    = 0

        pl_dir.mkdir(parents=True, exist_ok=True)

        track_futures = {}
        track_progress = {i: 0.0 for i in range(total)}
        progress_lock = threading.Lock()

        def make_callback(index: int):
            def _cb(event: dict):
                if event.get("type") == "progress":
                    with progress_lock:
                        track_progress[index] = event.get("progress", 0.0)
                        overall_pct = (completed + sum(track_progress.values())) / total
                    current_song = completed + 1 if completed + 1 <= total else total
                    emit(callback, progress_event(overall_pct, f"Downloading {current_song}/{total} songs..."))
            _cb.is_cancelled = lambda: getattr(callback, "is_cancelled", lambda: False)()
            return _cb

        import api.task_registry as tr
        task_id = getattr(callback, "task_id", None)

        for i, t in enumerate(tracks):
            if getattr(t, "source", "spotify") == "ytmusic":
                dl_url = getattr(t, "spotify_url", None) or getattr(t, "url", None)
                if dl_url:
                    fut = self._executor.submit(
                        _youtube.download_generic, t, options, pl_dir, make_callback(i),
                    )
                else:
                    fut = self._executor.submit(lambda: False)
            else:
                fut = self._executor.submit(
                    _spotify.download_track, t, options, pl_dir, make_callback(i),
                )
            self._track_future(fut)
            track_futures[fut] = (i, t.title)
            if task_id and tr._active_registry:
                tr._active_registry.register_sub_future(task_id, fut)

        for fut in concurrent.futures.as_completed(track_futures.keys()):
            idx, current_title = track_futures[fut]
            with progress_lock:
                completed += 1
                track_progress[idx] = 0.0
            try:
                if fut.result():
                    succeeded += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            emit(callback, batch_event(completed, total, succeeded, failed, current_title=current_title))

        emit(callback, batch_end_event(succeeded, failed))
        open_folder(pl_dir)
