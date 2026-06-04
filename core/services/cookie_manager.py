"""
core/services/cookie_manager.py
================================
Single source of truth for ghost-cookie lifecycle.
Exports Brave browser cookies to a Netscape cookie file,
validates freshness, and returns a usable path.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import yt_dlp


_GHOST_COOKIE_PATH = os.path.join(tempfile.gettempdir(), "spyde_ghost_cookies.txt")

def get_brave_cookie_paths() -> list[Path]:
    """Return platform-specific Brave cookie database locations."""
    home = Path.home()

    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            local / "BraveSoftware/Brave-Browser/User Data/Default/Network/Cookies",
            local / "BraveSoftware/Brave-Browser/User Data/Default/Cookies",
        ]

    if sys.platform == "darwin":
        return [
            home / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies",
        ]

                                                           
    return [
        home / ".config/BraveSoftware/Brave-Browser/Default/Network/Cookies",
        home / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
        home / "snap/brave/current/.config/BraveSoftware/Brave-Browser/Default/Network/Cookies",
        home / "snap/brave/current/.config/BraveSoftware/Brave-Browser/Default/Cookies",
        home / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Network/Cookies",
        home / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Cookies",
    ]

def _open_folder(path: Path) -> None:
    """Open a folder in the system file manager (non-blocking)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["explorer", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass

def get_cookie_file() -> Optional[str]:
    """
    Export Brave cookies to a Netscape cookie file if needed, then return the
    path.  Returns None when no usable cookie file can be produced.
    """
                                                             
    if os.path.exists(_GHOST_COOKIE_PATH):
        age = time.time() - os.path.getmtime(_GHOST_COOKIE_PATH)
        if age < 1800:
            return _GHOST_COOKIE_PATH

                                                            
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "cookiesfrombrowser": ("brave",),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.cookiejar.save(_GHOST_COOKIE_PATH, ignore_discard=True)
        if os.path.exists(_GHOST_COOKIE_PATH) and os.path.getsize(_GHOST_COOKIE_PATH) > 0:
            return _GHOST_COOKIE_PATH
    except Exception as e:
        print(f"[Cookies] Brave export failed: {e}")

                                                          
    if os.path.exists(_GHOST_COOKIE_PATH):
        return _GHOST_COOKIE_PATH

    return None
