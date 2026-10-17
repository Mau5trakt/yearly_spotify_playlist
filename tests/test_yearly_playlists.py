from __future__ import annotations

import pytest

from yearly_spotify_playlist.liked_tracks import LikedTrack
from yearly_spotify_playlist.yearly_playlists import (
    ADD_BATCH_SIZE,
    chunked,
    playlist_description,
    playlist_name,
    select_new_tracks,
    sync_year,
)


def _track(index: int) -> LikedTrack:
    return LikedTrack(
        uri=f"spotify:track:{index}", name=f"Song {index}", artist="A", liked_year=2023
    )


def _tracks(count: int) -> list[LikedTrack]:
    return [_track(i) for i in range(count)]


class FakeLibrary:
    """Records the calls sync_year makes instead of hitting the API."""

    def __init__(self, existing_items: set[str] | None = None) -> None:
        self.created: list[tuple[str, str]] = []
        self.added: list[tuple[str, list[str]]] = []
        self.existing_items = existing_items or set()
        self.contents_read: list[str] = []

    def create_playlist(self, name: str, *, description: str) -> str:
        self.created.append((name, description))
        return "new-id"

    def playlist_track_uris(self, playlist_id: str) -> set[str]:
        self.contents_read.append(playlist_id)
        return self.existing_items

    def add_tracks(self, playlist_id: str, uris: list[str]) -> None:
        self.added.append((playlist_id, uris))


def _run(library, year, tracks, existing_playlist=None):
    statuses: list[str] = []
    settled: list[tuple[str, bool]] = []
    result = sync_year(
        library,
        year,
        tracks,
        existing_playlist=existing_playlist,
        on_status=statuses.append,
        on_track=lambda t, added: settled.append((t.name, added)),
    )
    return result, statuses, settled


def test_playlist_name_and_description():
    assert playlist_name(2023) == "2023"
    assert playlist_description(2023) == "Liked songs in 2023"


def test_chunked_splits_in_batches_of_size():
    assert [list(c) for c in chunked([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]
    assert list(chunked([], 2)) == []


def test_chunked_rejects_non_positive_size():
    with pytest.raises(ValueError):
        list(chunked([1], 0))


def test_select_new_tracks_filters_while_preserving_order():
    tracks = _tracks(4)
    assert [
        t.uri for t in select_new_tracks(tracks, {"spotify:track:0", "spotify:track:2"})
    ] == [
        "spotify:track:1",
        "spotify:track:3",
    ]


def test_sync_year_creates_playlist_when_missing():
    library = FakeLibrary()
    tracks = _tracks(3)

    result, statuses, settled = _run(library, 2023, tracks)

    assert library.created == [("2023", "Liked songs in 2023")]
    assert library.added == [
        ("new-id", ["spotify:track:0", "spotify:track:1", "spotify:track:2"])
    ]
    assert result.created is True
    assert (result.added, result.skipped) == (3, 0)
    assert all(added for _, added in settled)
    assert statuses[0] == "creating playlist 2023"
    assert 'adding "Song 0" and 2 more to playlist 2023' in statuses


def test_sync_year_reuses_existing_playlist_and_skips_known_tracks():
    library = FakeLibrary(existing_items={"spotify:track:0", "spotify:track:1"})
    tracks = _tracks(3)

    result, statuses, settled = _run(
        library, 2023, tracks, existing_playlist={"id": "old-id"}
    )

    assert library.created == []
    assert library.contents_read == ["old-id"]
    assert library.added == [("old-id", ["spotify:track:2"])]
    assert result.created is False
    assert (result.added, result.skipped) == (1, 2)
    assert settled == [("Song 2", True), ("Song 0", False), ("Song 1", False)]
    assert statuses[0] == "reusing playlist 2023"


def test_sync_year_is_a_noop_when_everything_is_already_there():
    library = FakeLibrary(existing_items={f"spotify:track:{i}" for i in range(3)})

    result, _, settled = _run(
        library, 2023, _tracks(3), existing_playlist={"id": "old-id"}
    )

    assert library.added == []
    assert (result.added, result.skipped) == (0, 3)
    assert all(not added for _, added in settled)


def test_sync_year_batches_at_the_api_limit():
    count = ADD_BATCH_SIZE * 2 + 5
    library = FakeLibrary()

    result, statuses, settled = _run(library, 2023, _tracks(count))

    assert [len(uris) for _, uris in library.added] == [
        ADD_BATCH_SIZE,
        ADD_BATCH_SIZE,
        5,
    ]
    assert result.added == count
    assert len(settled) == count
    assert all(len(uris) <= ADD_BATCH_SIZE for _, uris in library.added)
    assert "and 99 more" in statuses[1]
