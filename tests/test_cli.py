from __future__ import annotations

from unittest.mock import patch

from yearly_spotify_playlist.cli import main
from yearly_spotify_playlist.config import Settings
from yearly_spotify_playlist.runner import YearResult


def _settings(*, dry_run: bool = False) -> Settings:
    return Settings(
        client_id="cid",
        client_secret="csec",
        refresh_token="rtok",
        redirect_uri="http://localhost:8888/callback",
        market=None,
        dry_run=dry_run,
    )


def test_main_success_prints_done_summary(capsys):
    results = [
        YearResult(year=2023, playlist_id="p1", added=10, skipped=0, created=True),
        YearResult(year=2022, playlist_id="p2", added=5, skipped=2, created=False),
    ]

    with (
        patch(
            "yearly_spotify_playlist.cli.load_settings",
            return_value=_settings(dry_run=False),
        ),
        patch("yearly_spotify_playlist.cli.run", return_value=results),
    ):
        exit_code = main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Done: 2 yearly playlists, 15 songs added."


def test_main_dry_run_prints_dry_run_summary(capsys):
    results = [
        YearResult(year=2023, playlist_id="dry-2023", added=7, skipped=1, created=True),
    ]

    with (
        patch(
            "yearly_spotify_playlist.cli.load_settings",
            return_value=_settings(dry_run=True),
        ),
        patch("yearly_spotify_playlist.cli.run", return_value=results),
    ):
        exit_code = main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert (
        captured.out.strip()
        == "Done (dry-run): 1 yearly playlists, 7 songs would be added."
    )


def test_main_keyboard_interrupt_returns_130(capsys):
    with patch(
        "yearly_spotify_playlist.cli.load_settings", side_effect=KeyboardInterrupt
    ):
        exit_code = main()

    assert exit_code == 130
    captured = capsys.readouterr()
    assert "Interrupted." in captured.err


def test_main_exception_returns_1(capsys):
    with patch(
        "yearly_spotify_playlist.cli.load_settings", side_effect=ValueError("bad value")
    ):
        exit_code = main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "bad value" in captured.err
