from concurrent.futures import ThreadPoolExecutor

from .client import SpotifyGraphQL
from .constants import TRACK_SHA256

spotify = SpotifyGraphQL()


def get_track(track_id: str):

    return spotify.query(
        operation="queryTrack",
        sha256=TRACK_SHA256,
        variables={
            "uri": f"spotify:track:{track_id}"
        },
    )


def get_isrc(track_id: str):

    # Placeholder for now.
    # Replace later with the implementation from spotify_client.py.
    return None


def get_track_with_isrc(track_id: str):

    track_data = get_track(track_id)

    return {
        "track_data": track_data,
        "isrc": get_isrc(track_id),
    }


def get_tracks_parallel(
    track_ids: list[str],
    max_workers: int = 10,
):

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        results = list(
            executor.map(
                get_track_with_isrc,
                track_ids,
            )
        )

    return results