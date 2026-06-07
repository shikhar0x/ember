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
    Export browser cookies to a Netscape cookie file if needed, then return the
    path. Returns None when no usable cookie file can be produced.
    Dynamically finds an installed browser (Brave, Chrome, Chromium, Edge).
    """
    if os.path.exists(_GHOST_COOKIE_PATH):
        age = time.time() - os.path.getmtime(_GHOST_COOKIE_PATH)
        if age < 1800:
            return _GHOST_COOKIE_PATH

    import http.cookiejar
    import browser_cookie3

    combined_jar = http.cookiejar.MozillaCookieJar(_GHOST_COOKIE_PATH)
    def extract_domain(domain: str):
        # 1. Brave (explicit path required on Windows sometimes)
        for path in get_brave_cookie_paths():
            if path.exists():
                try:
                    cj = browser_cookie3.brave(cookie_file=str(path), domain_name=domain)
                    if domain == ".youtube.com" and any(c.name in ("LOGIN_INFO", "SAPISID", "__Secure-3PSID") for c in cj):
                        return cj
                    if domain == ".instagram.com" and any(c.name == "sessionid" for c in cj):
                        return cj
                except Exception:
                    pass

        # 2. Fallbacks
        for browser in [browser_cookie3.firefox, browser_cookie3.chrome, browser_cookie3.chromium, browser_cookie3.edge]:
            try:
                cj = browser(domain_name=domain)
                if domain == ".youtube.com" and any(c.name in ("LOGIN_INFO", "SAPISID", "__Secure-3PSID") for c in cj):
                    return cj
                if domain == ".instagram.com" and any(c.name == "sessionid" for c in cj):
                    return cj
            except Exception:
                pass
        return []

    # Extract YouTube cookies
    YT_ESSENTIALS = {
        "LOGIN_INFO", "SAPISID", "__Secure-3PSID", "__Secure-1PSID",
        "__Secure-1PAPISID", "__Secure-3PAPISID", "SID", "HSID",
        "SSID", "PREF", "YSC", "VISITOR_INFO1_LIVE"
    }
    for c in extract_domain(".youtube.com"):
        if c.name in YT_ESSENTIALS:
            combined_jar.set_cookie(c)

    # Extract Instagram cookies
    for c in extract_domain(".instagram.com"):
        combined_jar.set_cookie(c)

    try:
        combined_jar.save(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        print(f"[Cookies] Failed to save combined cookie jar: {e}")
    
    if os.path.exists(_GHOST_COOKIE_PATH) and os.path.getsize(_GHOST_COOKIE_PATH) > 0:
        return _GHOST_COOKIE_PATH

    return None
