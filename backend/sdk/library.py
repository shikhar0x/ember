from .client import SpotifyGraphQL
from .constants import (
    LIKED_SONGS_SHA256,
    IS_IN_LIBRARY_SHA256,
)

spotify = SpotifyGraphQL()


def get_liked_songs():

    return spotify.query(
        operation="getLikedSongs",
        sha256=LIKED_SONGS_SHA256,
        variables={},
    )


def is_in_library(
    uris: list[str],
):

    return spotify.query(
        operation="isInLibrary",
        sha256=IS_IN_LIBRARY_SHA256,
        variables={
            "uris": uris,
        },
    )


def get_library_data():

    return {
        "liked_songs":
            get_liked_songs(),
    }