from concurrent.futures import ThreadPoolExecutor

from .client import SpotifyGraphQL
from .constants import ALBUM_SHA256
from .track import get_track_with_isrc

spotify = SpotifyGraphQL()


def get_album(album_id: str):

    return spotify.query(
        operation="queryAlbum",
        sha256=ALBUM_SHA256,
        variables={
            "uri": f"spotify:album:{album_id}",
            "offset": 0,
        },
    )


def get_album_tracks(album_id: str):

    data = get_album(album_id)

    tracks = (
        data["data"]
        ["albumUnion"]
        ["tracksV2"]
        ["items"]
    )

    return [
        track["track"]["id"]
        for track in tracks
    ]


def get_album_with_isrc(
    album_id: str,
    max_workers: int = 10,
):

    album_data = get_album(album_id)

    track_ids = get_album_tracks(album_id)

    with ThreadPoolExecutor(
        max_workers=max_workers
    ) as executor:

        enriched_tracks = list(
            executor.map(
                get_track_with_isrc,
                track_ids,
            )
        )

    return {
        "album_data": album_data,
        "tracks": enriched_tracks,
    }