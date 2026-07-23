from concurrent.futures import ThreadPoolExecutor

from .track import get_track
from .album import get_album
from .artist import get_artist
from .playlist import (
    get_playlist,
    get_playlist_tracks,
)

from .library import get_liked_songs

from .isrc import get_track_isrc

from .normalizers import (
    normalize_track,
    normalize_album,
    normalize_artist,
    normalize_playlist,
    normalize_raw_playlist_track,
)

from .markdown_writer import (
    write_markdown,
    track_markdown,
    album_markdown,
    artist_markdown,
    playlist_markdown,
)


def _resolve_isrc(track_id: str) -> str:
    """Resolve ISRC for a single track ID, return empty string on failure."""
    return get_track_isrc(track_id) or ""


def _enrich_tracks_with_isrcs(
    tracks: list[dict],
):
    """
    Enriches track data concurrently using a multi-worker pool.
    Configures a widened keep-alive connection pool to eliminate session contention.
    """
    if not tracks:
        return

    import requests
    from concurrent.futures import ThreadPoolExecutor
    from .client import SpotifyGraphQL
    from .isrc import get_track_isrc

    token = SpotifyGraphQL()._tm.get_headers()

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    def fetch_single(track):
        uri = track.get("uri", "")
        if "spotify:track:" not in uri:
            return track, ""
            
        tid = uri.split(":")[-1]
        try:
            isrc = get_track_isrc(tid, headers=token, session=session)
            return track, isrc
        except Exception:
            return track, ""

    with ThreadPoolExecutor(max_workers=20, thread_name_prefix="ISRCWorker") as executor:
        results = executor.map(fetch_single, tracks)

    for t, isrc in results:
        t["isrc"] = isrc or ""


class SpotifyGraphQLSDK:

    def track(
        self,
        track_id: str,
    ):

        data = normalize_track(
            get_track(
                track_id
            )
        )

        data["isrc"] = _resolve_isrc(
            track_id
        )

        path = write_markdown(
            data["title"],
            track_markdown(
                data
            ),
        )

        return {
            "data": data,
            "markdown": path,
        }

    def album(
        self,
        album_id: str,
    ):

        data = normalize_album(
            get_album(
                album_id
            )
        )

        tracks = data.get("tracks", [])
        if tracks:
            _enrich_tracks_with_isrcs(tracks)

        path = write_markdown(
            data["name"],
            album_markdown(
                data
            ),
        )

        return {
            "data": data,
            "markdown": path,
        }

    def artist(
        self,
        artist_id: str,
    ):

        data = normalize_artist(
            get_artist(
                artist_id
            )
        )

        tracks = data.get("top_tracks", [])
        if tracks:
            self._enrich_durations(tracks)
            _enrich_tracks_with_isrcs(tracks)

        path = write_markdown(
            data["name"],
            artist_markdown(
                data
            ),
        )

        return {
            "data": data,
            "markdown": path,
        }

    @staticmethod
    def _enrich_durations(
        tracks: list[dict],
    ):
        """Fill in missing durations by fetching individual track data."""
        from .utils import ms_to_minutes

        missing = [
            (i, t["uri"].split(":")[-1])
            for i, t in enumerate(tracks)
            if not t.get("duration") and t.get("uri")
        ]

        if not missing:
            return

        def _fetch_duration(args):
            idx, tid = args
            try:
                raw = get_track(tid)
                ms = (
                    raw.get("data", {})
                    .get("trackUnion", {})
                    .get("duration", {})
                    .get("totalMilliseconds", 0)
                )
                return idx, ms
            except Exception:
                return idx, 0

        with ThreadPoolExecutor(
            max_workers=5
        ) as ex:
            for idx, ms in ex.map(
                _fetch_duration, missing
            ):
                if ms:
                    tracks[idx]["duration"] = (
                        ms_to_minutes(ms)
                    )

    def playlist(
        self,
        playlist_id: str,
    ):

        data = normalize_playlist(
            get_playlist(
                playlist_id
            )
        )

        raw_tracks = get_playlist_tracks(
            playlist_id
        )

        tracks = [
            t for t in (
                normalize_raw_playlist_track(r)
                for r in raw_tracks
            )
            if t is not None
        ]

        data["tracks"] = tracks
        data["total_tracks"] = len(tracks)

        if tracks:
            _enrich_tracks_with_isrcs(tracks)

        path = write_markdown(
            data["name"],
            playlist_markdown(
                data
            ),
        )

        return {
            "data": data,
            "markdown": path,
        }


if __name__ == "__main__":

    sdk = SpotifyGraphQLSDK()

    while True:

        url = input(
            "\nEnter Spotify URL (or 'exit'): "
        ).strip()

        if url.lower() == "exit":
            break

        try:

            if "/track/" in url:

                track_id = (
                    url
                    .split("/track/")[1]
                    .split("?")[0]
                )

                result = sdk.track(
                    track_id
                )

            elif "/album/" in url:

                album_id = (
                    url
                    .split("/album/")[1]
                    .split("?")[0]
                )

                result = sdk.album(
                    album_id
                )

            elif "/artist/" in url:

                artist_id = (
                    url
                    .split("/artist/")[1]
                    .split("?")[0]
                )

                result = sdk.artist(
                    artist_id
                )

            elif "/playlist/" in url:

                playlist_id = (
                    url
                    .split("/playlist/")[1]
                    .split("?")[0]
                )

                result = sdk.playlist(
                    playlist_id
                )

            elif "/collection/tracks" in url:

                result = {
                    "data":
                        get_liked_songs(),

                    "markdown":
                        None,
                }

            else:

                print(
                    "\nUnsupported URL."
                )

                continue

            print(
                "\nData:\n"
            )

            print(
                result["data"]
            )

            if result["markdown"]:

                print(
                    "\nMarkdown saved to:"
                )

                print(
                    result["markdown"]
                )

        except Exception as e:

            print(
                "\nError:",
                e
            )