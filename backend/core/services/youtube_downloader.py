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
from core.events import emit, progress_event, complete_event, error_event, TaskCancelledException
from core.utils import sanitize_filename as core_sanitize, open_folder
from core.services.spotify_downloader import _log_final


_CODEC_EXT: dict[str, str] = {
    "mp3":    "mp3",
    "flac":   "flac",
    "m4a":    "m4a",
    "aac":    "m4a",
    "vorbis": "ogg",
    "opus":   "opus",
    "wav":    "wav",
}


def download_generic(
    data: dict | Track,
    options: dict,
    dest: Path,
    callback: Optional[Callable[[dict], None]] = None,
) -> bool:
    """Download audio or video from a YouTube / direct URL via yt-dlp."""
    from core.models import Track
    track_obj = None

    if isinstance(data, dict):
        url = data.get("url")
        title = data.get("title", "audio")
    else:
        track_obj = data
        url = getattr(track_obj, "spotify_url", None) or getattr(track_obj, "url", None)
        title = getattr(track_obj, "title", "audio")

    fmt  = options.get("format", "Audio (MP3)")
    qual = options.get("quality", "Best Available")
    audio_codec = options.get("audio_codec", "mp3")
    audio_quality = options.get("audio_quality", "320")

    if track_obj:
        artist_str = ", ".join(dict.fromkeys(track_obj.artists)) if getattr(track_obj, "artists", None) else "Unknown"
        safe_title = core_sanitize(f"{track_obj.title} - {artist_str}")
    else:
        safe_title = core_sanitize(title) or "audio_download"
        
    ext = _CODEC_EXT.get(audio_codec, "mp3") if "Audio" in fmt else "mp4"
    final_path = _unique_path(dest, safe_title, ext)

    cookie_file = get_cookie_file()
    
    if os.name == "nt":
        cookie_file = None

    from core.utils import get_ffmpeg_details
    ffmpeg_exe, ffmpeg_location = get_ffmpeg_details()

    import threading
    prog_lock = threading.Lock()
    progress_state = {"video": 0.0, "audio": 0.0}

    def make_hook(stream_type: str):
        def _hook(d):
            if callback and getattr(callback, "is_cancelled", lambda: False)():
                raise TaskCancelledException("Task was cancelled")
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
                    if "Audio" in fmt:
                        mean_prog = progress_state["audio"]
                    else:
                        mean_prog = (progress_state["video"] + progress_state["audio"]) / 2.0
                    
                emit(callback, progress_event(mean_prog, f"Downloading: {int(mean_prog * 100)}%"))
        return _hook

    try:
        if callback and getattr(callback, "is_cancelled", lambda: False)():
            raise TaskCancelledException("Task was cancelled")
        temp_stem = f"{safe_title}.temp"
        out_tpl   = str(dest / f"{temp_stem}.%(ext)s")

        if "Audio" in fmt:
            bitrate = "320k"
            if audio_quality and audio_quality.isdigit():
                bitrate = f"{audio_quality}k"
            elif audio_quality == "0" or not audio_quality:
                bitrate = "320k"

            audio_format_str = "bestaudio/best" if os.name == "nt" else "bestaudio[abr>=192]/bestaudio[abr>=160]/bestaudio/best"

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": out_tpl,
                "keepvideo": False,
                "cookiefile": cookie_file,
                "format": audio_format_str,
                "prefer_ffmpeg": True,
                "progress_hooks": [make_hook("audio")],
                "postprocessor_hooks": [lambda d: emit(callback, progress_event(1.0, f"Converting to {audio_codec.upper()}...")) if d["status"] == "started" else None],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_codec,
                    "preferredquality": audio_quality,
                }],
                "postprocessor_args": {
                    "ffmpeg": ["-vn", "-ar", "44100", "-ac", "2"]
                },
            }
            if audio_codec == "mp3":
                ydl_opts["postprocessor_args"]["ffmpeg"].extend(["-b:a", bitrate, "-joint_stereo", "1", "-id3v2_version", "3", "-write_id3v1", "1"])
            else:
                ydl_opts["postprocessor_args"]["ffmpeg"].extend(["-b:a", bitrate])

            if os.name == "nt":
                ydl_opts["extractor_args"] = {
                    "youtube": {
                        "player_client": ["android", "web"]
                    }
                }

            ydl_opts["ffmpeg_location"] = ffmpeg_location
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if callback and getattr(callback, "is_cancelled", lambda: False)():
                raise TaskCancelledException("Task was cancelled")
            temp_ext = _CODEC_EXT.get(audio_codec, audio_codec)
            temp_path = dest / f"{temp_stem}.{temp_ext}"
            if temp_path.exists():
                time.sleep(0.2)
                os.rename(str(temp_path), str(final_path))
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import subprocess
            import glob

            height = qual.replace("p", "").strip()
            vid_fmt = f"bestvideo[height<={height}]/bestvideo/best" if height.isdigit() else "bestvideo/best"
            
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
                if os.name == "nt":
                    opts["extractor_args"] = {
                        "youtube": {
                            "player_client": ["android", "web"]
                        }
                    }
                opts["ffmpeg_location"] = ffmpeg_location
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

            with ThreadPoolExecutor(max_workers=2) as executor:
                f_vid = executor.submit(download_stream, "video", vid_fmt, vid_out_tpl)
                f_aud = executor.submit(download_stream, "audio", "bestaudio/best", aud_out_tpl)
                for f in as_completed([f_vid, f_aud]):
                    f.result() 

            if callback and getattr(callback, "is_cancelled", lambda: False)():
                raise TaskCancelledException("Task was cancelled")
            emit(callback, progress_event(1.0, "Merging streams..."))

            vid_files = glob.glob(str(dest / f"{temp_stem}.video.*"))
            aud_files = glob.glob(str(dest / f"{temp_stem}.audio.*"))

            if not vid_files or not aud_files:
                raise Exception("Failed to locate downloaded streams for merging")

            vid_file = vid_files[0]
            aud_file = aud_files[0]

            merge_cmd = [
                ffmpeg_exe, "-y",
                "-i", vid_file,
                "-i", aud_file,
                "-c:v", "copy",
                "-c:a", "aac",
                str(final_path)
            ]
            if callback and getattr(callback, "is_cancelled", lambda: False)():
                raise TaskCancelledException("Task was cancelled")
            subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            try:
                os.remove(vid_file)
                os.remove(aud_file)
            except OSError:
                pass

        if track_obj:
            emit(callback, progress_event(1.0, "Embedding metadata..."))
            cover_bytes = None
            if getattr(track_obj, "cover_url", None):
                from core.http_helper import get_bytes
                try:
                    cover_bytes = get_bytes(track_obj.cover_url, timeout=10)
                except Exception:
                    pass
            try:
                from core.tagger import tag_audio
                tag_audio(track_obj, str(final_path), cover_bytes)
            except Exception as e:
                print(f"[YoutubeDL] Tagging error: {e}")

            try:
                _log_final(final_path, ext, track_obj)
            except Exception:
                pass

        open_folder(dest)
        emit(callback, complete_event(True, "Success!"))
        return True

    except TaskCancelledException:
        if final_path.exists():
            try:
                os.remove(str(final_path))
            except OSError:
                pass
        for pattern in (f"{safe_title}*", f"{temp_stem}*"):
            for p in dest.glob(pattern):
                try:
                    if p.is_file():
                        os.remove(str(p))
                except OSError:
                    pass
        raise
    except Exception as e:
        print(f"[YoutubeDL] generic download error: {e}")
        emit(callback, error_event("Failed"))
        return False


def _unique_path(dest: Path, stem: str, ext: str) -> Path:
    """Return a collision-free path in *dest*."""
    path = dest / f"{stem}.{ext}"
    counter = 1
    while path.exists():
        path = dest / f"{stem} ({counter}).{ext}"
        counter += 1
    return path
