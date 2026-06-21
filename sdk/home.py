from .client import SpotifyGraphQL
from .constants import (
    HOME_SHA256,
    HOME_SECTION_SHA256,
)

spotify = SpotifyGraphQL()


def get_home(
    time_zone: str = "UTC",
):

    return spotify.query(
        operation="queryHome",
        sha256=HOME_SHA256,
        variables={
            "timeZone": time_zone,
        },
    )


def get_home_section(
    section_uri: str,
):

    return spotify.query(
        operation="queryHomeSection",
        sha256=HOME_SECTION_SHA256,
        variables={
            "uri": section_uri,
        },
    )


def get_home_data():

    return {
        "home": get_home(),
    }