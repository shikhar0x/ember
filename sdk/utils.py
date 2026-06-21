from pathlib import Path


def sanitize_filename(name: str) -> str:

    if not name:
        return "Unknown"

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        name = name.replace(char, "_")

    return name.strip()


def ms_to_seconds(ms: int) -> float:

    return round(
        ms / 1000,
        2,
    )


def ms_to_minutes(ms: int) -> str:

    seconds = ms // 1000

    minutes = seconds // 60

    seconds %= 60

    return f"{minutes}:{seconds:02}"


def largest_cover(
    sources: list[dict],
):

    if not sources:
        return None

    return max(
        sources,
        key=lambda x:
        x.get(
            "width",
            0,
        ),
    )["url"]


def extract_date(
    date_dict: dict | None,
):

    if not date_dict:
        return None

    return (
        date_dict.get(
            "isoString"
        )
        or date_dict.get(
            "year"
        )
    )


def ensure_directory(
    path: str,
):

    Path(
        path
    ).mkdir(
        parents=True,
        exist_ok=True,
    )


def save_json(
    data,
    filename: str,
):

    import json

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )