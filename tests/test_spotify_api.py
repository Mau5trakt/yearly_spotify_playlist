from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

from yearly_spotify_playlist.spotify_api import (
    PLAYLIST_ITEMS_PAGE_SIZE,
    PLAYLIST_PAGE_SIZE,
    SAVED_TRACKS_PAGE_SIZE,
    SpotifyLibrary,
)


def _library(
    client: MagicMock | None = None, market: str | None = None
) -> SpotifyLibrary:
    return SpotifyLibrary(client or MagicMock(), market=market)


# -- current_user -------------------------------------------------------------


def test_current_user_delegates_to_client():
    client = MagicMock()
    client.current_user.return_value = {"id": "user1", "display_name": "Test"}
    lib = _library(client)

    user = lib.current_user()

    assert user["id"] == "user1"
    client.current_user.assert_called_once()


# -- iter_saved_track_pages ---------------------------------------------------


def test_iter_saved_track_pages_yields_single_page():
    client = MagicMock()
    page: dict[str, Any] = {"items": [{"track": {"uri": "a"}}], "next": None}
    client.current_user_saved_tracks.return_value = page

    lib = _library(client, market="ES")
    pages = list(lib.iter_saved_track_pages())

    assert pages == [page]
    client.current_user_saved_tracks.assert_called_once_with(
        limit=SAVED_TRACKS_PAGE_SIZE,
        offset=0,
        market="ES",
    )


def test_iter_saved_track_pages_follows_next():
    client = MagicMock()
    page1: dict[str, Any] = {"items": [{"track": {"uri": "a"}}], "next": "http://next"}
    page2: dict[str, Any] = {"items": [{"track": {"uri": "b"}}], "next": None}
    client.current_user_saved_tracks.return_value = page1
    client.next.return_value = page2

    lib = _library(client)
    pages = list(lib.iter_saved_track_pages())

    assert pages == [page1, page2]
    client.next.assert_called_once_with(page1)


def test_iter_saved_track_pages_passes_market_none():
    client = MagicMock()
    client.current_user_saved_tracks.return_value = {"items": [], "next": None}

    lib = _library(client, market=None)
    list(lib.iter_saved_track_pages())

    client.current_user_saved_tracks.assert_called_once_with(
        limit=SAVED_TRACKS_PAGE_SIZE,
        offset=0,
        market=None,
    )


# -- owned_playlists_by_name --------------------------------------------------


def _playlist(name: str, owner_id: str, playlist_id: str) -> dict[str, Any]:
    return {"name": name, "id": playlist_id, "owner": {"id": owner_id}}


def test_owned_playlists_by_name_filters_by_owner():
    client = MagicMock()
    client.current_user_playlists.return_value = {
        "items": [
            _playlist("2023", "me", "p1"),
            _playlist("Other", "someone_else", "p2"),
            _playlist("2024", "me", "p3"),
        ],
        "next": None,
    }

    lib = _library(client)
    result = lib.owned_playlists_by_name("me")

    assert set(result) == {"2023", "2024"}
    assert result["2023"]["id"] == "p1"
    assert result["2024"]["id"] == "p3"


def test_owned_playlists_by_name_keeps_first_duplicate():
    client = MagicMock()
    client.current_user_playlists.return_value = {
        "items": [
            _playlist("2023", "me", "first"),
            _playlist("2023", "me", "second"),
        ],
        "next": None,
    }

    lib = _library(client)
    result = lib.owned_playlists_by_name("me")

    assert result["2023"]["id"] == "first"


def test_owned_playlists_by_name_paginates():
    client = MagicMock()
    client.current_user_playlists.side_effect = [
        {
            "items": [_playlist("2023", "me", "p1")],
            "next": "http://page2",
        },
        {
            "items": [_playlist("2024", "me", "p2")],
            "next": None,
        },
    ]

    lib = _library(client)
    result = lib.owned_playlists_by_name("me")

    assert set(result) == {"2023", "2024"}
    assert client.current_user_playlists.call_args_list == [
        call(limit=PLAYLIST_PAGE_SIZE, offset=0),
        call(limit=PLAYLIST_PAGE_SIZE, offset=PLAYLIST_PAGE_SIZE),
    ]


def test_owned_playlists_by_name_skips_missing_owner_or_name():
    client = MagicMock()
    client.current_user_playlists.return_value = {
        "items": [
            {"name": "2023", "id": "p1", "owner": None},
            {"name": None, "id": "p2", "owner": {"id": "me"}},
            _playlist("2024", "me", "p3"),
        ],
        "next": None,
    }

    lib = _library(client)
    result = lib.owned_playlists_by_name("me")

    assert list(result) == ["2024"]


# -- playlist_track_uris ------------------------------------------------------


def test_playlist_track_uris_collects_uris():
    client = MagicMock()
    client.playlist_items.return_value = {
        "items": [
            {"item": {"uri": "spotify:track:a"}},
            {"item": {"uri": "spotify:track:b"}},
        ],
        "next": None,
    }

    lib = _library(client)
    uris = lib.playlist_track_uris("pid")

    assert uris == {"spotify:track:a", "spotify:track:b"}
    client.playlist_items.assert_called_once_with(
        "pid",
        limit=PLAYLIST_ITEMS_PAGE_SIZE,
        offset=0,
    )


def test_playlist_track_uris_paginates():
    client = MagicMock()
    client.playlist_items.side_effect = [
        {
            "items": [{"item": {"uri": "spotify:track:a"}}],
            "next": "http://page2",
        },
        {
            "items": [{"item": {"uri": "spotify:track:b"}}],
            "next": None,
        },
    ]

    lib = _library(client)
    uris = lib.playlist_track_uris("pid")

    assert uris == {"spotify:track:a", "spotify:track:b"}
    assert client.playlist_items.call_args_list == [
        call("pid", limit=PLAYLIST_ITEMS_PAGE_SIZE, offset=0),
        call("pid", limit=PLAYLIST_ITEMS_PAGE_SIZE, offset=PLAYLIST_ITEMS_PAGE_SIZE),
    ]


def test_playlist_track_uris_skips_missing_item_or_uri():
    client = MagicMock()
    client.playlist_items.return_value = {
        "items": [
            {"item": None},
            {"item": {"uri": ""}},
            {"item": {"uri": "spotify:track:ok"}},
            {},
        ],
        "next": None,
    }

    lib = _library(client)
    uris = lib.playlist_track_uris("pid")

    assert uris == {"spotify:track:ok"}


# -- create_playlist -----------------------------------------------------------


def test_create_playlist_returns_id():
    client = MagicMock()
    client.current_user_playlist_create.return_value = {"id": "new-id"}

    lib = _library(client)
    pid = lib.create_playlist("2023", description="Liked songs in 2023")

    assert pid == "new-id"
    client.current_user_playlist_create.assert_called_once_with(
        name="2023",
        public=True,
        description="Liked songs in 2023",
    )


# -- add_tracks ----------------------------------------------------------------


def test_add_tracks_posts_uris():
    client = MagicMock()
    lib = _library(client)

    lib.add_tracks("pid", ["spotify:track:a", "spotify:track:b"])

    client._post.assert_called_once_with(
        "playlists/pid/items",
        payload={"uris": ["spotify:track:a", "spotify:track:b"]},
    )
