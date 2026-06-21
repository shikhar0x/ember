from .client import SpotifyGraphQL
from .constants import USER_SHA256

spotify = SpotifyGraphQL()


def get_user(
    user_id: str,
):

    return spotify.query(
        operation="queryUser",
        sha256=USER_SHA256,
        variables={
            "uri": f"spotify:user:{user_id}",
        },
    )


def get_user_name(
    user_id: str,
):

    data = get_user(user_id)

    try:

        return (
            data["data"]
            ["user"]
            ["profile"]
            ["name"]
        )

    except KeyError:

        return None


def get_user_avatar(
    user_id: str,
):

    data = get_user(user_id)

    try:

        return (
            data["data"]
            ["user"]
            ["avatar"]
            ["sources"]
        )

    except KeyError:

        return []


def get_user_followers(
    user_id: str,
):

    data = get_user(user_id)

    try:

        return (
            data["data"]
            ["user"]
            ["followersCount"]
        )

    except KeyError:

        return None


def get_user_data(
    user_id: str,
):

    return {
        "user_data":
            get_user(
                user_id
            ),

        "name":
            get_user_name(
                user_id
            ),

        "followers":
            get_user_followers(
                user_id
            ),

        "avatar":
            get_user_avatar(
                user_id
            ),
    }