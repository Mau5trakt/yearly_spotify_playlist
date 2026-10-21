from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from yearly_spotify_playlist.config import Settings
from yearly_spotify_playlist.liked_tracks import LikedTrack
from yearly_spotify_playlist.runner import (
    RunError,
    YearResult,
    _bar_callbacks,
    _summary_line,
    run,
)


def _settings(**kwargs) -> Settings:
    defaults = {
        "client_id": "cid",
        "client_secret": "csec",
        "refresh_token": "rtok",
        "redirect_uri": "http://localhost:8888/callback",
        "market": None,
        "dry_run": False,
        "years": None,
        "year_from": None,
        "batch_delay_seconds": 0.1,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


class FakeBar:
    """Stands in for the tqdm bar the callbacks write their message to."""

    def __init__(self) -> None:
        self.postfix: list[str] = []
        self.updates = 0

    def set_postfix_str(self, message: str, *, refresh: bool = False) -> None:
        self.postfix.append(message)

    def update(self, n: int = 1) -> None:
        self.updates += n


def _track(name: str) -> LikedTrack:
    return LikedTrack(
        uri=f"spotify:track:{name}", name=name, artist="A", liked_year=2023
    )


def test_track_callbacks_keep_the_year_and_bar_they_were_built_for():
    first_bar, second_bar = FakeBar(), FakeBar()
    _, first_on_track = _bar_callbacks(first_bar, "2023")
    _, second_on_track = _bar_callbacks(second_bar, "2024")

    # Both are invoked only after the second playlist already has its callbacks.
    first_on_track(_track("A"), True)
    second_on_track(_track("B"), False)

    assert first_bar.postfix == ['added "A" to playlist 2023']
    assert second_bar.postfix == ['"B" was already in playlist 2024']
    assert (first_bar.updates, second_bar.updates) == (1, 1)


def test_status_callbacks_write_to_their_own_bar():
    first_bar, second_bar = FakeBar(), FakeBar()
    first_on_status, _ = _bar_callbacks(first_bar, "2023")
    second_on_status, _ = _bar_callbacks(second_bar, "2024")

    first_on_status("creating playlist 2023")
    second_on_status("reusing playlist 2024")

    assert first_bar.postfix == ["creating playlist 2023"]
    assert second_bar.postfix == ["reusing playlist 2024"]


# -- Summary line formatting ---------------------------------------------------


def test_summary_line_standard():
    created = YearResult(year=2023, playlist_id="p1", added=5, skipped=2, created=True)
    reused = YearResult(year=2022, playlist_id="p2", added=0, skipped=10, created=False)

    assert (
        _summary_line(created) == "  2023: playlist created | 5 added | 2 already there"
    )
    assert (
        _summary_line(reused) == "  2022: playlist reused | 0 added | 10 already there"
    )


def test_summary_line_dry_run():
    created = YearResult(year=2023, playlist_id="p1", added=5, skipped=2, created=True)
    reused = YearResult(year=2022, playlist_id="p2", added=0, skipped=10, created=False)

    assert _summary_line(created, dry_run=True) == (
        "  2023: playlist would create | 5 would be added | 2 already there"
    )
    assert _summary_line(reused, dry_run=True) == (
        "  2022: playlist would reuse | 0 would be added | 10 already there"
    )


# -- Filtering by year in run() ------------------------------------------------


@pytest.fixture
def mock_run_context():
    with (
        patch("yearly_spotify_playlist.runner.build_spotify"),
        patch("yearly_spotify_playlist.runner.SpotifyLibrary") as mock_lib_cls,
        patch("yearly_spotify_playlist.runner._read_liked_tracks") as mock_read,
        patch("yearly_spotify_playlist.runner._sync_all_years") as mock_sync,
    ):
        mock_lib = MagicMock()
        mock_lib.current_user.return_value = {
            "id": "user1",
            "display_name": "Test User",
        }
        mock_lib.owned_playlists_by_name.return_value = {}
        mock_lib_cls.return_value = mock_lib

        # Grouped tracks for 2021, 2022, 2023
        mock_read.return_value = {
            2021: [_track("A")],
            2022: [_track("B")],
            2023: [_track("C")],
        }
        mock_sync.return_value = []
        yield mock_sync


def test_run_applies_years_filter(mock_run_context):
    mock_sync = mock_run_context
    run(_settings(years=(2021, 2023)))

    # _sync_all_years was called with grouped filtered to 2021 and 2023
    assert mock_sync.call_count == 1
    grouped_arg = mock_sync.call_args[0][1]
    assert set(grouped_arg.keys()) == {2021, 2023}


def test_run_applies_year_from_filter(mock_run_context):
    mock_sync = mock_run_context
    run(_settings(year_from=2022))

    assert mock_sync.call_count == 1
    grouped_arg = mock_sync.call_args[0][1]
    assert set(grouped_arg.keys()) == {2022, 2023}


def test_run_years_filter_takes_precedence_over_year_from(mock_run_context):
    mock_sync = mock_run_context
    run(_settings(years=(2021,), year_from=2022))

    assert mock_sync.call_count == 1
    grouped_arg = mock_sync.call_args[0][1]
    assert set(grouped_arg.keys()) == {2021}


def test_run_raises_when_no_songs_match_filter(mock_run_context):
    with pytest.raises(
        RunError, match="No liked songs match the specified year filter"
    ):
        run(_settings(years=(2019, 2020)))


def test_run_raises_when_no_liked_songs_at_all():
    with (
        patch("yearly_spotify_playlist.runner.build_spotify"),
        patch("yearly_spotify_playlist.runner.SpotifyLibrary") as mock_lib_cls,
        patch("yearly_spotify_playlist.runner._read_liked_tracks", return_value={}),
    ):
        mock_lib = MagicMock()
        mock_lib.current_user.return_value = {"id": "user1"}
        mock_lib_cls.return_value = mock_lib

        with pytest.raises(RunError, match="No liked songs were found"):
            run(_settings())
