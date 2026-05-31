"""
core/services/youtube_downloader.py
====================================
YouTube / generic URL download orchestration via yt-dlp.
Handles audio extraction and video downloads.
Completely UI-agnostic. Emits structured event payloads.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from core.services.cookie_manager import get_cookie_file
from core.events import emit, progress_event, complete_event, error_event


def download_generic(
    data: dict,
    options: dict,
    dest: Path,
    callback: Optional[Callable[[dict], None]] = None,
) -> bool:
    """Download audio or video from a YouTube / direct URL via yt-dlp."""
    fmt  = options.get("format", "Audio (MP3)")
    qual = options.get("quality", "Best Available")

    title      = data.get("title", "audio")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "audio_download"
    ext        = "mp3" if "Audio" in fmt else "mp4"
    final_path = _unique_path(dest, safe_title, ext)

    cookie_file = get_cookie_file()

    def _hook(d):
        if d["status"] == "downloading" and callback:
            p_str = d.get("_percent_str", "0%").strip()
            p_clean = "".join(c for c in p_str if c.isdigit() or c in ".%")
            emit(callback, progress_event(0.5, f"Downloading: {p_clean}"))

    try:
        temp_stem = f"{safe_title}.temp"
        out_tpl   = str(dest / f"{temp_stem}.%(ext)s")

        if "Audio" in fmt:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": out_tpl,
                "keepvideo": False,
                "cookiefile": cookie_file,
                "format": "bestaudio[abr>=192]/bestaudio[abr>=160]/bestaudio/best",
                "prefer_ffmpeg": True,
                "progress_hooks": [_hook],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }],
                "postprocessor_args": {
                    "ffmpeg": ["-vn", "-ar", "44100", "-ac", "2", "-b:a", "320k"]
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([data["url"]])

            temp_path = dest / f"{temp_stem}.mp3"
            if temp_path.exists():
                time.sleep(0.2)
                os.rename(str(temp_path), str(final_path))
        else:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": out_tpl,
                "keepvideo": False,
                "cookiefile": cookie_file,
                "merge_output_format": "mp4",
                "progress_hooks": [_hook],
            }
            height = qual.replace("p", "").strip()
            if height.isdigit():
                ydl_opts["format"] = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
            else:
                ydl_opts["format"] = "bestvideo+bestaudio/best"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([data["url"]])

            temp_path = dest / f"{temp_stem}.mp4"
            if temp_path.exists():
                os.rename(str(temp_path), str(final_path))

        emit(callback, complete_event(True, "Success!"))
        return True

    except Exception as e:
        print(f"[YoutubeDL] generic download error: {e}")
        emit(callback, error_event("Failed"))
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
