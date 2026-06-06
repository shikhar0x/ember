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

    import threading
    prog_lock = threading.Lock()
    progress_state = {"video": 0.0, "audio": 0.0}

    def make_hook(stream_type: str):
        def _hook(d):
            if d["status"] == "downloading" and callback:
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                
                if total > 0:
                    prog_val = float(downloaded) / float(total)
                else:
                    p_str = d.get("_percent_str", "0%")
                    import re
                    p_str_clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', p_str)
                    p_num = "".join(c for c in p_str_clean if c.isdigit() or c == ".")
                    try:
                        prog_val = float(p_num) / 100.0 if p_num else 0.0
                    except ValueError:
                        prog_val = 0.0
                        
                with prog_lock:
                    progress_state[stream_type] = prog_val
                    mean_prog = (progress_state["video"] + progress_state["audio"]) / 2.0
                    
                emit(callback, progress_event(mean_prog, f"Downloading: {int(mean_prog * 100)}%"))
        return _hook

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
                "progress_hooks": [make_hook("audio")],
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
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import subprocess
            import glob

            height = qual.replace("p", "").strip()
            vid_fmt = f"bestvideo[height<={height}]" if height.isdigit() else "bestvideo"
            
            vid_out_tpl = str(dest / f"{temp_stem}.video.%(ext)s")
            aud_out_tpl = str(dest / f"{temp_stem}.audio.%(ext)s")

            def download_stream(stream_type, format_selector, tpl):
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": tpl,
                    "keepvideo": True,
                    "cookiefile": cookie_file,
                    "format": format_selector,
                    "progress_hooks": [make_hook(stream_type)],
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([data["url"]])

            with ThreadPoolExecutor(max_workers=2) as executor:
                f_vid = executor.submit(download_stream, "video", vid_fmt, vid_out_tpl)
                f_aud = executor.submit(download_stream, "audio", "bestaudio/best", aud_out_tpl)
                for f in as_completed([f_vid, f_aud]):
                    f.result() 

            emit(callback, progress_event(1.0, "Merging streams..."))

            vid_files = glob.glob(str(dest / f"{temp_stem}.video.*"))
            aud_files = glob.glob(str(dest / f"{temp_stem}.audio.*"))

            if not vid_files or not aud_files:
                raise Exception("Failed to locate downloaded streams for merging")

            vid_file = vid_files[0]
            aud_file = aud_files[0]

            merge_cmd = [
                "ffmpeg", "-y",
                "-i", vid_file,
                "-i", aud_file,
                "-c", "copy",
                str(final_path)
            ]
            subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            try:
                os.remove(vid_file)
                os.remove(aud_file)
            except OSError:
                pass

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
