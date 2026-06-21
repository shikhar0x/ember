from typing import Any

from core.spotify_client import TokenManager

from .constants import PATHFINDER_URL


class SpotifyGraphQL:
    """Singleton GraphQL client — all SDK modules share one TokenManager."""

    _instance = None
    _tm = None

    def __new__(cls):
        import requests
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            
            # 1. Establish Singleton Session Life Cycle & Adjust Pool Size Limits
            cls._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=100, 
                pool_maxsize=100
            )
            cls._session.mount("https://", adapter)
            cls._session.mount("http://", adapter)
            
            # 2. Pass Session Context as Dependency
            cls._tm = TokenManager(session=cls._session)
        return cls._instance

    def query(
        self,
        operation: str,
        sha256: str,
        variables: dict[str, Any],
    ):

        payload = {
            "operationName": operation,
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256,
                }
            },
        }

        response = self._tm.request(
            "POST",
            PATHFINDER_URL,
            json=payload,
        )

        response.raise_for_status()

        return response.json()