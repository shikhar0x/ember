from .client import SpotifyGraphQL
from .constants import (
    BROWSE_SHA256,
    BROWSE_START_SHA256,
)

spotify = SpotifyGraphQL()


def browse(
    uri: str = "spotify:page:browse",
):

    return spotify.query(
        operation="browse",
        sha256=BROWSE_SHA256,
        variables={
            "uri": uri,

            "pagePagination": {
                "offset": 0,
                "limit": 50,
            },

            "sectionPagination": {
                "offset": 0,
                "limit": 50,
            },
        },
    )


def browse_start():

    return spotify.query(
        operation="browseStart",
        sha256=BROWSE_START_SHA256,
        variables={},
    )


def get_browse_data():

    return {
        "browse": browse(),
        "browse_start": browse_start(),
    }