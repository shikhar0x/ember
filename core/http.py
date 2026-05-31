"""
core/http.py
============
Shared HTTP utilities used across the Spyde backend.
"""

from __future__ import annotations

import requests
from typing import Optional


HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_bytes(url: str, timeout: int = 20, headers: Optional[dict] = None) -> Optional[bytes]:
    """Fetch raw bytes from *url*.  Pass timeout=3 for fast preview loading."""
    if not url:
        return None
    try:
        h = {**HTTP_HEADERS, **(headers or {})}
        r = requests.get(url, headers=h, timeout=timeout)
        return r.content if r.status_code == 200 else None
    except Exception as e:
        print(f"[get_bytes] Failed ({timeout}s): {e}")
        return None
