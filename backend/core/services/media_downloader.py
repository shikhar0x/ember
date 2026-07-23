"""
core/services/media_downloader.py
==================================
Image / mixed-media download orchestration.
Handles carousel images, mixed image+video posts,
thumbnail fallback, and direct URL fetching.
Completely UI-agnostic. Emits structured event payloads.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from typing import Callable, Optional

import requests
import yt_dlp

from core.http_helper import HTTP_HEADERS
from core.events import emit, status_event, complete_event, error_event
from core.utils import open_folder


def download_media(
    data: dict,
    dest: Path,
    callback: Optional[Callable[[dict], None]] = None,
) -> bool:
    """Save carousel images, download videos, or fall back to thumbnail."""
    dest.mkdir(parents=True, exist_ok=True)

    title = data.get("title", "image")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "image"

    carousel = data.get("carousel", {})
    carousel_frames = carousel.get("frames") or []
    download_urls = carousel.get("download_urls", [])
    media_types = carousel.get("media_types", [])

                                              
    if carousel_frames or download_urls:
        saved = 0
        n_items = max(len(carousel_frames), len(download_urls))
        if not media_types:
            media_types = ["photo"] * n_items

        for i in range(n_items):
            m_type = media_types[i] if i < len(media_types) else "photo"

            if m_type == "photo":
                frame_bytes = carousel_frames[i] if i < len(carousel_frames) else None
                if frame_bytes:
                    ext = "jpg"
                    if frame_bytes[:4] == b'\x89PNG': ext = "png"
                    elif frame_bytes[:4] == b'RIFF': ext = "webp"
                    path = dest / f"{safe_title}_{i+1}.{ext}"
                    with open(path, "wb") as f:
                        f.write(frame_bytes)
                    saved += 1
                elif i < len(download_urls):
                    try:
                        r = requests.get(download_urls[i], timeout=15)
                        if r.status_code == 200:
                            path = dest / f"{safe_title}_{i+1}.jpg"
                            with open(path, "wb") as f:
                                f.write(r.content)
                            saved += 1
                    except Exception:
                        pass

            elif m_type == "video" and i < len(download_urls):
                try:
                    emit(callback, status_event(f"Pulling video {i+1}..."))
                    from core.utils import get_ffmpeg_details
                    _, ffmpeg_loc = get_ffmpeg_details()
                    ydl_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "outtmpl": str(dest / f"{safe_title}_{i+1}.%(ext)s"),
                        "ffmpeg_location": ffmpeg_loc,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([download_urls[i]])
                    saved += 1
                except Exception as e:
                    print(f"Video download failed: {e}")

        if saved:
            open_folder(dest)
            s = saved
            emit(callback, complete_event(True, f"Saved {s} Item{'s' if s > 1 else ''}!"))
            return True

                                  
    thumb_bytes = data.get("thumbnail_bytes")
    if thumb_bytes:
        ext = "jpg"
        if thumb_bytes[:4] == b'\x89PNG': ext = "png"
        path = dest / f"{safe_title}.{ext}"
        with open(path, "wb") as f:
            f.write(thumb_bytes)
        open_folder(dest)
        emit(callback, complete_event(True, "Image Saved!"))
        return True

                                  
    target_url = data.get("url") or data.get("spotify_url")
    if target_url:
        try:
            emit(callback, status_event("Downloading..."))
            r = requests.get(target_url, headers=HTTP_HEADERS, timeout=15)
            if r.status_code == 200 and r.content:
                ct = r.headers.get("content-type", "")
                ext = "jpg"
                if "png" in ct: ext = "png"
                elif "webp" in ct: ext = "webp"
                elif "gif" in ct: ext = "gif"
                path = dest / f"{safe_title}.{ext}"
                with open(path, "wb") as f:
                    f.write(r.content)
                open_folder(dest)
                emit(callback, complete_event(True, "Image Saved!"))
                return True
        except Exception as e:
            print(f"[MediaDL] Direct download failed: {e}")

    emit(callback, error_event("No image to save"))
    return False
