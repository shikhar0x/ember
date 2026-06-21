from .utils import (
    ms_to_minutes,
    largest_cover,
    extract_date,
)


def normalize_track(
    data: dict,
):

    track = (
        data.get("data", {})
        .get("trackUnion", {})
    )

    album = track.get(
        "albumOfTrack",
        {},
    )

    artists = [

        artist.get(
            "profile",
            {},
        ).get(
            "name"
        )

        for artist in

        track.get(
            "firstArtist",
            {},
        ).get(
            "items",
            [],
        )
    ]

    preview_items = (

        track.get(
            "previews",
            {},
        ).get(
            "audioPreviews",
            {},
        ).get(
            "items",
            [],
        )
    )

    return {

        "id":
            track.get("id"),

        "uri":
            track.get("uri"),

        "title":
            track.get("name"),

        "artists":
            artists,

        "album":
            album.get("name"),

        "release_date":
            extract_date(
                album.get(
                    "date"
                )
            ),

        "duration_ms":
            track.get(
                "duration",
                {},
            ).get(
                "totalMilliseconds"
            ),

        "duration":
            ms_to_minutes(

                track.get(
                    "duration",
                    {},
                ).get(
                    "totalMilliseconds",
                    0,
                )
            ),

        "cover_url":
            largest_cover(

                album.get(
                    "coverArt",
                    {},
                ).get(
                    "sources",
                    [],
                )
            ),

        "playable":

            track.get(
                "playability",
                {},
            ).get(
                "playable"
            ),

        "preview_url":

            preview_items[0]["url"]

            if preview_items

            else None,
    }


def normalize_album(
    data: dict,
):

    album = (

        data.get(
            "data",
            {},
        ).get(
            "albumUnion",
            {},
        )
    )

    artists = [

        artist.get(
            "profile",
            {},
        ).get(
            "name"
        )

        for artist in

        album.get(
            "artists",
            {},
        ).get(
            "items",
            [],
        )
    ]

    # Extract tracks from tracksV2
    tracks_data = (
        album
        .get("tracksV2", {})
        .get("items", [])
    )

    # Album-level cover (used as fallback for tracks without albumOfTrack)
    album_cover = largest_cover(
        album.get(
            "coverArt", {}
        ).get(
            "sources", []
        )
    )

    tracks = []

    for item in tracks_data:

        try:

            t = item.get("track", {})

            if not t:
                continue

            t_artists = [

                a.get(
                    "profile", {}
                ).get("name", "")

                for a in
                t.get(
                    "artists", {}
                ).get("items", [])
            ]

            duration_ms = (
                t
                .get("duration", {})
                .get("totalMilliseconds", 0)
            )

            tracks.append({

                "name":
                    t.get("name"),

                "artists":
                    t_artists,

                "duration":
                    ms_to_minutes(
                        duration_ms
                    ),

                "cover_url":
                    album_cover,

                "uri":
                    t.get("uri"),
            })

        except (KeyError, AttributeError):
            continue

    return {

        "id":
            album.get("id"),

        "uri":
            album.get("uri"),

        "name":
            album.get("name"),

        "artists":
            artists,

        "release_date":

            extract_date(

                album.get(
                    "date"
                )
            ),

        "cover_url":

            largest_cover(

                album.get(
                    "coverArt",
                    {},
                ).get(
                    "sources",
                    [],
                )
            ),

        "track_count":

            album.get(
                "tracksV2",
                {},
            ).get(
                "totalCount"
            ),

        "type":
            album.get("type"),

        "tracks":
            tracks,
    }


def normalize_artist(
    data: dict,
):

    artist = (

        data.get(
            "data",
            {},
        ).get(
            "artistUnion",
            {},
        )
    )

    avatar_sources = (

        artist.get(
            "visuals",
            {},
        ).get(
            "avatarImage",
            {}
        ) or {}

    ).get(
        "sources",
        [],
    )

    # Extract top tracks
    top_items = (
        artist
        .get("discography", {})
        .get("topTracks", {})
        .get("items", [])
    )

    top_tracks = []

    for item in top_items:

        try:

            t = item.get("track", {})

            if not t:
                continue

            t_artists = [

                a.get(
                    "profile", {}
                ).get("name", "")

                for a in
                t.get(
                    "artists", {}
                ).get("items", [])
            ]

            duration_ms = (
                (t.get("duration") or {})
                .get("totalMilliseconds", 0)
            )

            album = t.get(
                "albumOfTrack", {}
            )

            top_tracks.append({

                "name":
                    t.get("name"),

                "artists":
                    t_artists,

                "album":
                    album.get("name"),

                "duration":
                    ms_to_minutes(
                        duration_ms
                    ) if duration_ms else None,

                "cover_url":
                    largest_cover(
                        album.get(
                            "coverArt", {}
                        ).get(
                            "sources", []
                        )
                    ),

                "uri":
                    t.get("uri"),
            })

        except (KeyError, AttributeError):
            continue

    return {

        "id":
            artist.get("id"),

        "uri":
            artist.get("uri"),

        "name":

            artist.get(
                "profile",
                {},
            ).get(
                "name"
            ),

        "monthly_listeners":

            artist.get(
                "stats",
                {},
            ).get(
                "monthlyListeners"
            ),

        "avatar":

            largest_cover(
                avatar_sources
            ),

        "top_tracks":
            top_tracks,
    }


def normalize_raw_playlist_track(
    track: dict,
) -> dict | None:
    """Normalize a single raw playlist track dict (itemV2.data)."""

    try:

        if not track:
            return None

        typename = track.get(
            "__typename", ""
        )

        if typename not in (
            "TrackItem",
            "Track",
            "",
        ):
            return None

        artists = [

            a.get(
                "profile", {}
            ).get("name", "")

            for a in
            track.get(
                "artists", {}
            ).get("items", [])
        ]

        album = track.get(
            "albumOfTrack", {}
        )

        duration_ms = (
            track
            .get("duration", {})
            .get("totalMilliseconds", 0)
        )

        return {

            "name":
                track.get("name"),

            "artists":
                artists,

            "album":
                album.get("name"),

            "duration":
                ms_to_minutes(
                    duration_ms
                ),

            "cover_url":
                largest_cover(
                    album.get(
                        "coverArt", {}
                    ).get(
                        "sources", []
                    )
                ),

            "uri":
                track.get("uri"),
        }

    except (KeyError, AttributeError):
        return None


def normalize_playlist(
    data: dict,
):

    playlist = (

        data.get(
            "data",
            {},
        ).get(
            "playlistV2",
            {},
        )
    )

    owner = (

        playlist.get(
            "ownerV2",
            {}
        ) or {}

    ).get(
        "data",
        {},
    )

    # Extract tracks from content items
    content = playlist.get(
        "content", {}
    )

    items = content.get("items", [])

    tracks = []

    for item in items:

        try:

            track = (
                item
                .get("itemV2", {})
                .get("data", {})
            )

            if not track:
                continue

            typename = track.get(
                "__typename", ""
            )

            if typename not in (
                "TrackItem",
                "Track",
                "",
            ):
                continue

            artists = [

                a.get(
                    "profile", {}
                ).get("name", "")

                for a in
                track.get(
                    "artists", {}
                ).get("items", [])
            ]

            album = track.get(
                "albumOfTrack", {}
            )

            duration_ms = (
                track
                .get("duration", {})
                .get("totalMilliseconds", 0)
            )

            tracks.append({

                "name":
                    track.get("name"),

                "artists":
                    artists,

                "album":
                    album.get("name"),

                "duration":
                    ms_to_minutes(
                        duration_ms
                    ),

                "cover_url":
                    largest_cover(
                        album.get(
                            "coverArt", {}
                        ).get(
                            "sources", []
                        )
                    ),

                "uri":
                    track.get("uri"),
            })

        except (KeyError, AttributeError):
            continue

    return {

        "uri":
            playlist.get("uri"),

        "name":
            playlist.get("name"),

        "description":
            playlist.get("description"),

        "owner":
            owner.get(
                "name"
            ),

        "total_tracks":
            content.get(
                "totalCount", len(tracks)
            ),

        "tracks":
            tracks,
    }