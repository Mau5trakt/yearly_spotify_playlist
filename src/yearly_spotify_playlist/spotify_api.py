"""Authenticated Spotify client and the exact Web API calls this tool needs."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from spotipy import Spotify, SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler

from .config import Settings

#: ``GET /me/tracks`` accepts at most 50 items per page.
SAVED_TRACKS_PAGE_SIZE = 50

#: ``GET /playlists/{id}/items`` accepts at most 50 items per page since the
#: 2026 endpoint changes.
PLAYLIST_ITEMS_PAGE_SIZE = 50

#: Playlist pages come 50 at a time.
PLAYLIST_PAGE_SIZE = 50

#: More retries than spotipy's default of 3: the whole run is API-heavy and a
#: single 429 should never kill a job that takes minutes.
RETRIES = 5
BACKOFF_FACTOR = 0.8
REQUEST_TIMEOUT = 20


def build_spotify(settings: Settings) -> Spotify:
    """Create a :class:`~spotipy.Spotify` client backed by the stored refresh token.

    spotipy has no ``refresh_token=`` argument, so the token is injected through a
    :class:`MemoryCacheHandler`. ``expires_at=0`` marks the cached access token as
    already expired, which makes spotipy exchange the refresh token for a fresh
    access token on the first authenticated call instead of opening a browser.
    """
    token_info: dict[str, Any] = {
        "access_token": "",
        "token_type": "Bearer",
        "refresh_token": settings.refresh_token,
        "expires_at": 0,
        # spotipy refuses to use a token whose scopes do not cover the ones the
        # auth manager was built with, so both strings must stay identical.
        "scope": settings.scope,
    }

    auth_manager = SpotifyOAuth(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        scope=settings.scope,
        cache_handler=MemoryCacheHandler(token_info=token_info),
        open_browser=False,
    )

    return Spotify(
        auth_manager=auth_manager,
        retries=RETRIES,
        status_retries=RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        requests_timeout=REQUEST_TIMEOUT,
    )


class SpotifyLibrary:
    """The handful of Spotify operations this tool performs.

    Thin wrapper on purpose: it pins the exact endpoints, page sizes and payload
    shapes required by the 2026 Web API, so the rest of the code never touches a
    raw spotipy response.
    """

    def __init__(self, client: Spotify, *, market: str | None = None) -> None:
        self._client = client
        self._market = market

    # -- identity ---------------------------------------------------------

    def current_user(self) -> dict[str, Any]:
        """Profile of the account the access token belongs to."""
        return self._client.current_user()

    # -- liked songs ------------------------------------------------------

    def iter_saved_track_pages(self) -> Iterator[dict[str, Any]]:
        """Yield every page of ``GET /me/tracks``, newest like first."""
        page = self._client.current_user_saved_tracks(
            limit=SAVED_TRACKS_PAGE_SIZE, offset=0, market=self._market
        )
        yield page
        while page.get("next"):
            page = self._client.next(page)
            yield page

    # -- playlists --------------------------------------------------------

    def owned_playlists_by_name(self, user_id: str) -> dict[str, dict[str, Any]]:
        """Map playlist name to playlist for playlists owned by ``user_id``."""
        owned: dict[str, dict[str, Any]] = {}
        offset = 0
        while True:
            page = self._client.current_user_playlists(limit=PLAYLIST_PAGE_SIZE, offset=offset)
            for playlist in page.get("items", []):
                owner = playlist.get("owner") or {}
                name = playlist.get("name")
                if owner.get("id") == user_id and isinstance(name, str):
                    owned.setdefault(name, playlist)
            if not page.get("next"):
                return owned
            offset += PLAYLIST_PAGE_SIZE

    def playlist_track_uris(self, playlist_id: str) -> set[str]:
        """URIs already present in a playlist (only populated for playlists you own)."""
        uris: set[str] = set()
        offset = 0
        while True:
            page = self._client.playlist_items(
                playlist_id, limit=PLAYLIST_ITEMS_PAGE_SIZE, offset=offset
            )
            for entry in page.get("items", []):
                # Entries are named "item", not "track", since the endpoint rename.
                item = entry.get("item") or {}
                uri = item.get("uri")
                if isinstance(uri, str) and uri:
                    uris.add(uri)
            if not page.get("next"):
                return uris
            offset += PLAYLIST_ITEMS_PAGE_SIZE

    def create_playlist(self, name: str, *, public: bool, description: str) -> str:
        """Create a playlist via ``POST /me/playlists`` and return its id.

        ``POST /users/{user_id}/playlists`` was removed for Development Mode apps
        in February 2026; spotipy's ``user_playlist_create`` still targets it.
        """
        created = self._client.current_user_playlist_create(
            name=name, public=public, description=description
        )
        return str(created["id"])

    def add_tracks(self, playlist_id: str, uris: list[str]) -> None:
        """Append up to 100 tracks to a playlist.

        ``playlist_add_items`` posts a bare JSON array, but the documented body
        for ``POST /playlists/{id}/items`` is ``{"uris": [...]}``, so the request
        is issued directly with the documented payload.
        """
        self._client._post(f"playlists/{playlist_id}/items", payload={"uris": uris})