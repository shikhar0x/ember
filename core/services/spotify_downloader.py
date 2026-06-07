"""
core/services/spotify_downloader.py
====================================
Spotify track download orchestration:
    resolve → fetch_audio → rename → enrich → tag
Completely UI-agnostic. Emits structured event payloads.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from core.pipeline import resolve
from core.fetcher import fetch_audio
from core.tagger import tag_audio
from core.utils import sanitize_filename as core_sanitize
from core.http import get_bytes
from core.events import emit, progress_event, complete_event, error_event


                                            
_CODEC_EXT: dict[str, str] = {
    "mp3":    "mp3",
    "flac":   "flac",
    "m4a":    "m4a",
    "aac":    "m4a",
    "vorbis": "ogg",
    "opus":   "opus",
    "wav":    "wav",
}


def download_track(
    track,
    options: dict,
    dest: Path,
    callback: Optional[Callable[[dict], None]] = None,
) -> bool:
    """Full pipeline: resolve → fetch → rename → enrich → tag for one Track."""
    audio_codec  = options.get("audio_codec",   "mp3")
    audio_quality = options.get("audio_quality", "0")

    ext = _CODEC_EXT.get(audio_codec, audio_codec)

    # --- Filename / collision guard ---
    artist_str = ", ".join(dict.fromkeys(track.artists)) if track.artists else "Unknown"
    safe_title = core_sanitize(f"{track.title} - {artist_str}")
    final_path = _unique_path(dest, safe_title, ext)

    try:
                          
        # --- Ensure track is fully enriched before resolving ---
        if not getattr(track, "_enriched", False):
            from core.enrich import enrich_tracks, apply_enrichment_updates
            updates, _ = enrich_tracks([track])
            if updates:
                apply_enrichment_updates(updates)

        emit(callback, progress_event(0.0, "Finding best match..."))
        candidates = resolve(track)
        if not candidates:
            emit(callback, error_event("No match found"))
            return False

        emit(callback, progress_event(0.05, "Downloading audio..."))

        def _hook(d):
            if d["status"] == "downloading" and callback:
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    raw_pct = float(downloaded) / float(total)
                else:
                    p_str = d.get("_percent_str", "0%")
                    import re
                    p_str_clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', p_str)
                    p_num = "".join(c for c in p_str_clean if c.isdigit() or c == ".")
                    try:
                        raw_pct = float(p_num) / 100.0 if p_num else 0.0
                    except ValueError:
                        raw_pct = 0.0
                emit(callback, progress_event(raw_pct, f"Downloading: {int(raw_pct*100)}%"))

        result = None
        for c in candidates:
            try:
                result = fetch_audio(
                    c.video_id,
                    output_dir=str(dest),
                    progress_hook=_hook,
                    audio_codec=audio_codec,
                    audio_quality=audio_quality,
                )
                break
            except Exception as e:
                print(f"[SpotifyDL] Fetch error on {c.title}: {e}")
                continue

        emit(callback, progress_event(1.0, "Finalizing..."))

        if not result:
            emit(callback, error_event("Download failed"))
            return False

        raw_path = result["path"]
        yt_thumb = result["thumbnail_bytes"]

        if raw_path != str(final_path):
            if final_path.exists():
                os.remove(str(final_path))
            shutil.move(raw_path, str(final_path))

                                      
        emit(callback, progress_event(1.0, "Embedding metadata..."))
        cover_bytes = _resolve_cover(track, yt_thumb)
        tag_audio(track, str(final_path), cover_bytes)

        _log_final(final_path, ext, track)
        emit(callback, complete_event(True, "Success!"))
        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SpotifyDL] download_track error: {e}")
        emit(callback, error_event(f"Failed: {e}"))
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_path(dest: Path, stem: str, ext: str) -> Path:
    """Return a collision-free path in *dest*."""
    path = dest / f"{stem}.{ext}"
    counter = 1
    while path.exists():
        path = dest / f"{stem} ({counter}).{ext}"
        counter += 1
    return path


def _resolve_cover(track, yt_thumb: Optional[bytes]) -> Optional[bytes]:
    """Try track cover URL first, fall back to yt_thumb."""
    if track.cover_url:
        cover = get_bytes(track.cover_url, timeout=10)
        if cover:
            return cover
    return yt_thumb


def _log_final(path: Path, ext: str, track) -> None:
    if not path.exists():
        return
    size = path.stat().st_size / (1024 * 1024)
    print(f"\nFinal File:")
    print(f"  Path: {path.name}")
    print(f"  Format: {ext.upper()}")
    print(f"  ISRC: {getattr(track, 'isrc', 'Not Found')}")
    try:
        import mutagen
        mf = mutagen.File(str(path))
        if mf and mf.info:
            dur = int(mf.info.length)
            br  = int(getattr(mf.info, "bitrate", 0) / 1000)
            print(f"  Bitrate: {br} kbps" if br else "  Bitrate: Lossless")
            print(f"  Duration: {dur // 60}:{dur % 60:02d}")
    except Exception:
        pass
    print(f"  Size: {size:.1f} MB\n")
