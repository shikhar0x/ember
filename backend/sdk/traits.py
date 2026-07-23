from .client import SpotifyGraphQL
from .constants import ENTITY_TRAITS_SHA256

spotify = SpotifyGraphQL()


def get_entity_traits(
    uri: str,
):

    return spotify.query(
        operation="getEntityTraits",
        sha256=ENTITY_TRAITS_SHA256,
        variables={
            "uri": uri,
        },
    )


def get_track_traits(
    track_id: str,
):

    return get_entity_traits(
        f"spotify:track:{track_id}"
    )


def get_album_traits(
    album_id: str,
):

    return get_entity_traits(
        f"spotify:album:{album_id}"
    )


def get_artist_traits(
    artist_id: str,
):

    return get_entity_traits(
        f"spotify:artist:{artist_id}"
    )


def get_playlist_traits(
    playlist_id: str,
):

    return get_entity_traits(
        f"spotify:playlist:{playlist_id}"
    )