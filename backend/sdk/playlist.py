from .client import SpotifyGraphQL
from .constants import PLAYLIST_SHA256

spotify = SpotifyGraphQL()


def get_playlist(
    playlist_id: str,
    offset: int = 0,
    limit: int = 100,
):

    return spotify.query(
        operation="queryPlaylist",
        sha256=PLAYLIST_SHA256,
        variables={
            "uri": f"spotify:playlist:{playlist_id}",
            "offset": offset,
            "limit": limit,
        },
    )


def get_playlist_name(
    playlist_id: str,
):

    data = get_playlist(playlist_id)

    return (
        data["data"]
        ["playlistV2"]
        ["name"]
    )


def get_playlist_owner(
    playlist_id: str,
):

    data = get_playlist(playlist_id)

    try:

        return (
            data["data"]
            ["playlistV2"]
            ["ownerV2"]
            ["data"]
            ["name"]
        )

    except KeyError:

        return None


def get_playlist_tracks(
    playlist_id: str,
):
    """Fetch all tracks from a playlist, paginating if needed."""

    all_tracks = []
    offset = 0
    limit = 100

    while True:

        data = get_playlist(
            playlist_id,
            offset=offset,
            limit=limit,
        )

        content = (
            data["data"]
            ["playlistV2"]
            ["content"]
        )

        items = content.get("items", [])

        if not items:
            break

        for item in items:

            try:

                track_data = (
                    item
                    .get("itemV2", {})
                    .get("data", {})
                )

                if not track_data:
                    continue

                typename = track_data.get(
                    "__typename", ""
                )

                if typename not in (
                    "TrackItem",
                    "Track",
                    "",
                ):
                    continue

                all_tracks.append(track_data)

            except (KeyError, AttributeError):
                continue

        total = content.get("totalCount", 0)
        offset += len(items)

        if offset >= total:
            break

    return all_tracks


def get_playlist_track_count(
    playlist_id: str,
):

    data = get_playlist(playlist_id)

    return (
        data["data"]
        ["playlistV2"]
        ["content"]
        .get("totalCount", 0)
    )


def get_playlist_data(
    playlist_id: str,
):

    return {
        "playlist_data":
            get_playlist(
                playlist_id
            ),

        "name":
            get_playlist_name(
                playlist_id
            ),

        "owner":
            get_playlist_owner(
                playlist_id
            ),

        "track_count":
            get_playlist_track_count(
                playlist_id
            ),

        "tracks":
            get_playlist_tracks(
                playlist_id
            ),
    }