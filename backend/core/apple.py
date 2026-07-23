import requests


def search_apple_music(title: str, artist: str) -> dict | None:
    query = f"{title} {artist}"
    url = "https://itunes.apple.com/search"

    params = {
        "term": query,
        "entity": "song",
        "limit": 5
    }

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        results = data.get("results", [])
        if not results:
            return None

        best = results[0]

        return {
            "title": best.get("trackName"),
            "artist": best.get("artistName"),
            "duration": (best.get("trackTimeMillis") or 0) // 1000,
            "album": best.get("collectionName"),
        }

    except Exception:
        return None