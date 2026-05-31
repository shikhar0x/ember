import requests
import re
from rapidfuzz import fuzz


def _sim(a, b):
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100


def _is_remix(title: str):
    return any(k in title.lower() for k in ["remix", "mix", "edit", "version"])


def _base_track(title: str):
    return title.split(" - ")[0].strip()


def _is_bad_album(album: str, title: str):
    if not album:
        return True

    a = album.lower()
    t = title.lower()

    bad_keywords = [
        "dj mix", "mix", "remix", "karaoke",
        "tribute", "workout", "morning",
        "playlist", "top hits", "best of"
    ]

    for word in bad_keywords:
        if word in a and word not in t:
            return True

    return False


def _clean(album: str):
    if not album:
        return album

    album = re.sub(r'\s*-\s*single$', '', album, flags=re.I)
    album = re.sub(r'\[feat\..*?\]', '', album, flags=re.I)

    return album.strip()


def fetch_album(title: str, artist: str) -> str | None:
    try:
        r = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": f"{title} {artist}",
                "entity": "song",
                "limit": 5
            },
            timeout=10
        ).json()

        for item in r.get("results", []):
            t = item.get("trackName", "")
            a = item.get("artistName", "")
            album = item.get("collectionName")

            if _sim(title, t) > 0.85 and _sim(artist, a) > 0.7:
                if not _is_bad_album(album, title):
                    return album

        return None

    except:
        return None


def resolve_album(title: str, artist: str) -> str:
    apple = fetch_album(title, artist)

    if not apple:
        return _base_track(title)

    if _is_remix(title):
        return _clean(apple)

    if "single" in apple.lower():
        return _base_track(title)

    return _clean(apple)