from .client import SpotifyGraphQL
from .constants import EXTRACTED_COLORS_SHA256

spotify = SpotifyGraphQL()


def get_colors(
    image_uris: list[str],
):

    return spotify.query(
        operation="fetchExtractedColors",
        sha256=EXTRACTED_COLORS_SHA256,
        variables={
            "imageUris": image_uris,
        },
    )


def get_album_colors(
    album_id: str,
):

    return get_colors(
        f"spotify:album:{album_id}"
    )


def get_track_colors(
    track_id: str,
):

    return get_colors(
        f"spotify:track:{track_id}"
    )


def get_artist_colors(
    artist_id: str,
):

    return get_colors(
        f"spotify:artist:{artist_id}"
    )