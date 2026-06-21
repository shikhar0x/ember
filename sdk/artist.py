from .client import SpotifyGraphQL
from .constants import ARTIST_SHA256

spotify = SpotifyGraphQL()


def get_artist(artist_id: str):

    return spotify.query(
        operation="queryArtist",
        sha256=ARTIST_SHA256,
        variables={
            "uri": f"spotify:artist:{artist_id}",
            "usePreReleaseV2": False,
        },
    )


def get_artist_name(artist_id: str):

    data = get_artist(artist_id)

    return (
        data["data"]
        ["artistUnion"]
        ["profile"]
        ["name"]
    )


def get_artist_monthly_listeners(
    artist_id: str,
):

    data = get_artist(artist_id)

    try:

        return (
            data["data"]
            ["artistUnion"]
            ["stats"]
            ["monthlyListeners"]
        )

    except KeyError:

        return None


def get_artist_avatar(
    artist_id: str,
):

    data = get_artist(artist_id)

    try:

        return (
            data["data"]
            ["artistUnion"]
            ["visuals"]
            ["avatarImage"]
            ["sources"]
        )

    except KeyError:

        return []


def get_artist_data(
    artist_id: str,
):

    data = get_artist(artist_id)

    return {
        "artist_data": data,
        "name": get_artist_name(artist_id),
        "monthly_listeners":
            get_artist_monthly_listeners(
                artist_id
            ),
        "avatar":
            get_artist_avatar(
                artist_id
            ),
    }