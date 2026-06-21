from .client import SpotifyGraphQL
from .constants import SEARCH_SHA256

spotify = SpotifyGraphQL()


def _search(
    operation: str,
    query: str,
):

    return spotify.query(
        operation=operation,
        sha256=SEARCH_SHA256,
        variables={
            "query": query,
        },
    )


def search_top_results(
    query: str,
):

    return _search(
        "findTopResults",
        query,
    )


def search_tracks(
    query: str,
):

    return _search(
        "findTracks",
        query,
    )


def search_albums(
    query: str,
):

    return _search(
        "findAlbums",
        query,
    )


def search_artists(
    query: str,
):

    return _search(
        "findArtists",
        query,
    )


def search_playlists(
    query: str,
):

    return _search(
        "findPlaylists",
        query,
    )


def search_users(
    query: str,
):

    return _search(
        "findUsers",
        query,
    )


def search_genres(
    query: str,
):

    return _search(
        "findGenres",
        query,
    )


def search_podcasts(
    query: str,
):

    return _search(
        "findPodcasts",
        query,
    )


def search_audiobooks(
    query: str,
):

    return _search(
        "findAudiobooks",
        query,
    )