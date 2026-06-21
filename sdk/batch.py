"""
Centralized batch-fetch utility for the Spotify GraphQL SDK.

Eliminates ThreadPoolExecutor duplication across modules by
providing a single `batch_fetch` primitive and typed wrappers
for common entity types.
"""

from concurrent.futures import ThreadPoolExecutor

DEFAULT_WORKERS = 10


def batch_fetch(
    items: list,
    function: callable,
    max_workers: int = DEFAULT_WORKERS,
) -> list:
    """
    Apply `function` to each item in `items` concurrently.

    Returns results in the same order as the input list.
    This is the single source of truth for all parallel
    work in the SDK — no other module should instantiate
    its own ThreadPoolExecutor.
    """

    if not items:
        return []

    with ThreadPoolExecutor(
        max_workers=max_workers,
    ) as executor:

        return list(
            executor.map(
                function,
                items,
            )
        )


# ── Chunking Utilities ────────────────────────────────────────────────────────
def chunked(iterable: list, n: int = 50):
    """Generator to split collections into static blocks of size n."""
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]

def chunked_batch_fetch(
    items: list,
    function: callable,
    chunk_size: int = 50,
    max_workers: int = DEFAULT_WORKERS,
) -> list:
    """
    Apply `function` to blocks of items concurrently instead of row-by-row.
    The function must accept a list (chunk) and return a list/dict of results.
    """
    if not items:
        return []

    chunks = list(chunked(items, chunk_size))
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for chunk_result in executor.map(function, chunks):
            # If function modifies objects in-place, it may return None
            if chunk_result:
                if isinstance(chunk_result, dict):
                    results.append(chunk_result)
                else:
                    results.extend(chunk_result)
                    
    return results

# ── Typed wrappers ────────────────────────────────────────────────────────────


def batch_tracks(
    track_ids: list[str],
    max_workers: int = DEFAULT_WORKERS,
) -> list[dict]:
    """Fetch multiple tracks by ID in parallel."""

    from .track import get_track

    return batch_fetch(
        track_ids,
        get_track,
        max_workers,
    )


def batch_albums(
    album_ids: list[str],
    max_workers: int = DEFAULT_WORKERS,
) -> list[dict]:
    """Fetch multiple albums by ID in parallel."""

    from .album import get_album

    return batch_fetch(
        album_ids,
        get_album,
        max_workers,
    )


def batch_artists(
    artist_ids: list[str],
    max_workers: int = DEFAULT_WORKERS,
) -> list[dict]:
    """Fetch multiple artists by ID in parallel."""

    from .artist import get_artist

    return batch_fetch(
        artist_ids,
        get_artist,
        max_workers,
    )


def batch_playlists(
    playlist_ids: list[str],
    max_workers: int = DEFAULT_WORKERS,
) -> list[dict]:
    """Fetch multiple playlists by ID in parallel."""

    from .playlist import get_playlist

    return batch_fetch(
        playlist_ids,
        get_playlist,
        max_workers,
    )
