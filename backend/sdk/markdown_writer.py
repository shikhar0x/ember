from .utils import (
    ensure_directory,
    sanitize_filename,
)


def write_markdown(
    title: str,
    content: str,
    output_dir: str = "Results",
):

    folder = (
        f"{output_dir}/"
        f"{sanitize_filename(title)}"
    )

    ensure_directory(
        folder
    )

    filename = (
        f"{folder}/"
        f"{sanitize_filename(title)}.md"
    )

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            content
        )

    return filename


def track_markdown(
    track: dict,
):

    track_id = track.get('uri', '').split(':')[-1] if track.get('uri') else track.get('id', '')

    return f"""# {track['title']}

| Field | Value |
|---------|---------|
| Track ID | {track_id} |
| Artists | {', '.join(track['artists'])} |
| Album | {track['album']} |
| Release Date | {track['release_date']} |
| Duration | {track['duration']} |
| ISRC | {track.get('isrc', '')} |
| Cover | {track.get('cover_url', '')} |
| Playable | {track['playable']} |
| Preview URL | {track['preview_url']} |
"""


def _tracks_table(
    tracks: list[dict],
    include_album: bool = True,
):
    """Render a tracks table with ISRC and Cover columns."""

    if not tracks:
        return ""

    lines = []

    if include_album:
        lines.append(
            "| # | Title | Artists "
            "| Album | Duration | ISRC "
            "| Cover | Track ID |"
        )
        lines.append(
            "|---|-------|---------|"
            "-------|----------|------"
            "|-------|----------|"
        )
    else:
        lines.append(
            "| # | Title | Artists "
            "| Duration | ISRC "
            "| Cover | Track ID |"
        )
        lines.append(
            "|---|-------|---------|"
            "----------|------"
            "|-------|----------|"
        )

    for i, t in enumerate(
        tracks, start=1
    ):

        artists = ", ".join(
            t.get("artists", [])
        )

        isrc = t.get("isrc", "")

        cover = t.get("cover_url", "") or ""

        duration = t.get("duration", "") or ""

        uri = t.get("uri", "")
        track_id = (
            uri.split(":")[-1]
            if uri else ""
        )

        if include_album:
            lines.append(
                f"| {i} "
                f"| {t.get('name', '')} "
                f"| {artists} "
                f"| {t.get('album', '')} "
                f"| {duration} "
                f"| {isrc} "
                f"| {cover} "
                f"| {track_id} |"
            )
        else:
            lines.append(
                f"| {i} "
                f"| {t.get('name', '')} "
                f"| {artists} "
                f"| {duration} "
                f"| {isrc} "
                f"| {cover} "
                f"| {track_id} |"
            )

    lines.append("")

    return "\n".join(lines)


def album_markdown(
    album: dict,
):

    lines = [
        f"# {album['name']}",
        "",
        "| Field | Value |",
        "|---------|---------|",
        f"| Artists | {', '.join(album['artists'])} |",
        f"| Release Date | {album['release_date']} |",
        f"| Track Count | {album['track_count']} |",
        f"| Type | {album['type']} |",
        f"| Cover | {album.get('cover_url', '')} |",
        "",
    ]

    tracks = album.get("tracks", [])

    if tracks:
        lines.append("## Tracks")
        lines.append("")
        lines.append(
            _tracks_table(
                tracks,
                include_album=False,
            )
        )

    return "\n".join(lines)


def artist_markdown(
    artist: dict,
):

    lines = [
        f"# {artist['name']}",
        "",
        "| Field | Value |",
        "|---------|---------|",
        f"| Monthly Listeners | {artist['monthly_listeners']} |",
        f"| URI | {artist['uri']} |",
        f"| Cover | {artist.get('avatar', '')} |",
        "",
    ]

    tracks = artist.get("top_tracks", [])

    if tracks:
        lines.append("## Top Tracks")
        lines.append("")
        lines.append(
            _tracks_table(
                tracks,
                include_album=True,
            )
        )

    return "\n".join(lines)


def playlist_markdown(
    playlist: dict,
):

    lines = [
        f"# {playlist['name']}",
        "",
        "| Field | Value |",
        "|---------|---------|",
        f"| Owner | {playlist['owner']} |",
        f"| Description | {playlist['description']} |",
        f"| Tracks | {playlist['total_tracks']} |",
        f"| URI | {playlist['uri']} |",
        f"| Cover | {playlist.get('cover_url', '')} |",
        "",
    ]

    tracks = playlist.get("tracks", [])

    if tracks:
        lines.append("## Tracks")
        lines.append("")
        lines.append(
            _tracks_table(
                tracks,
                include_album=True,
            )
        )

    return "\n".join(lines)