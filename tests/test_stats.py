from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from yearly_spotify_playlist.cli import main, parse_args
from yearly_spotify_playlist.config import Settings
from yearly_spotify_playlist.liked_tracks import LikedTrack
from yearly_spotify_playlist.stats import (
    format_stats_chart,
    load_stats_cache,
    save_stats_cache,
    stats_from_tracks,
)


def _settings() -> Settings:
    return Settings(
        client_id="cid",
        client_secret="csec",
        refresh_token="rtok",
        redirect_uri="http://localhost:8888/callback",
        market=None,
    )


def test_stats_from_tracks_counts_by_year_ascending():
    tracks = [
        LikedTrack(uri="s1", name="Track 1", artist="Artist", liked_year=2019),
        LikedTrack(uri="s2", name="Track 2", artist="Artist", liked_year=2014),
        LikedTrack(uri="s3", name="Track 3", artist="Artist", liked_year=2019),
    ]
    counts = stats_from_tracks(tracks)
    assert counts == {2014: 1, 2019: 2}


def test_cache_save_and_load_roundtrip(tmp_path: Path):
    cache_file = tmp_path / "stats_cache.json"
    counts = {2014: 150, 2019: 450}

    save_stats_cache(counts, path=cache_file)
    assert cache_file.exists()

    raw_content = cache_file.read_text(encoding="utf-8")
    parsed = json.loads(raw_content)
    assert "data" in parsed
    loaded = load_stats_cache(path=cache_file)
    assert loaded == counts


def test_cache_expired_after_one_hour(tmp_path: Path):
    cache_file = tmp_path / "stats_cache.json"
    counts = {2014: 10}

    # Save with a timestamp 3601 seconds in the past
    two_hours_ago = time.time() - 3601
    save_stats_cache(counts, path=cache_file, timestamp=two_hours_ago)

    loaded = load_stats_cache(path=cache_file)
    assert loaded is None


def test_cache_corrupted_returns_none(tmp_path: Path):
    cache_file = tmp_path / "stats_cache.json"
    cache_file.write_text("corrupted-not-valid-base64-or-json", encoding="utf-8")

    assert load_stats_cache(path=cache_file) is None


def test_cache_nonexistent_returns_none(tmp_path: Path):
    cache_file = tmp_path / "nonexistent.json"
    assert load_stats_cache(path=cache_file) is None


def test_format_stats_chart_ascending_order_and_header():
    counts = {2019: 450, 2014: 150}
    chart = format_stats_chart(counts, terminal_width=80)
    lines = [line for line in chart.splitlines() if line.strip()]

    assert "Canciones por año" in lines[0]
    assert "2014" in lines[1]
    assert "2019" in lines[2]
    assert "150" in lines[1]
    assert "450" in lines[2]
    assert any(c in lines[1] for c in ("█", "▌", "▎", "▍", "▋", "▊", "▉"))
    assert any(c in lines[2] for c in ("█", "▌", "▎", "▍", "▋", "▊", "▉"))
    assert lines[2].count("█") > lines[1].count("█")
    for line in lines:
        assert len(line) <= 80


def test_format_stats_chart_narrow_terminal_fallback():
    counts = {2014: 150, 2019: 450}
    # With a narrow terminal, it should fall back to just year and count without bars
    chart = format_stats_chart(counts, terminal_width=15)
    lines = chart.splitlines()

    assert lines[0] == "Canciones por año"
    assert lines[1] == "2014 150"
    assert lines[2] == "2019 450"


def test_format_stats_chart_empty():
    chart = format_stats_chart({})
    assert chart == "Canciones por año\nNo hay canciones registradas."


def test_cli_parse_args_stats_flag():
    args_short = parse_args(["-s"])
    assert args_short.stats is True
    assert args_short.update is False

    args_long = parse_args(["--stats"])
    assert args_long.stats is True

    args_default = parse_args([])
    assert args_default.stats is False
    assert args_default.update is False

    args_su = parse_args(["-su"])
    assert args_su.stats == "u"

    args_s_u = parse_args(["-s", "u"])
    assert args_s_u.stats == "u"

    args_s_flag_u = parse_args(["-s", "-u"])
    assert args_s_flag_u.stats is True
    assert args_s_flag_u.update is True

    args_only_u = parse_args(["-u"])
    assert args_only_u.update is True


def test_cli_parse_args_stats_invalid_value():
    with pytest.raises(SystemExit):
        parse_args(["-s", "invalid"])


def test_cli_help_includes_stats_flag(capsys):
    exit_code = main(["--help"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "-s" in captured.out
    assert "--stats" in captured.out


def test_cli_stats_reads_valid_cache_without_calling_spotify(tmp_path: Path, capsys):
    cache_file = tmp_path / "stats_cache.json"
    save_stats_cache({2014: 100, 2018: 200}, path=cache_file)

    with (
        patch("yearly_spotify_playlist.cli.DEFAULT_CACHE_PATH", cache_file),
        patch("yearly_spotify_playlist.cli.load_settings", return_value=_settings()),
        patch("yearly_spotify_playlist.runner.build_spotify") as mock_spotify,
    ):
        exit_code = main(["--stats"])

    assert exit_code == 0
    mock_spotify.assert_not_called()
    captured = capsys.readouterr()
    assert "Canciones por año" in captured.out
    assert "2014" in captured.out
    assert "2018" in captured.out


def test_cli_stats_fetches_when_cache_missing_and_saves_cache(tmp_path: Path, capsys):
    cache_file = tmp_path / "stats_cache.json"
    assert not cache_file.exists()

    fake_tracks = [
        LikedTrack(uri="t1", name="N1", artist="A1", liked_year=2021),
        LikedTrack(uri="t2", name="N2", artist="A2", liked_year=2021),
    ]

    with (
        patch("yearly_spotify_playlist.cli.DEFAULT_CACHE_PATH", cache_file),
        patch("yearly_spotify_playlist.runner.DEFAULT_CACHE_PATH", cache_file),
        patch("yearly_spotify_playlist.cli.load_settings", return_value=_settings()),
        patch(
            "yearly_spotify_playlist.runner._read_liked_tracks",
            return_value={2021: fake_tracks},
        ),
        patch("yearly_spotify_playlist.runner.SpotifyLibrary"),
        patch("yearly_spotify_playlist.runner.build_spotify"),
        patch("yearly_spotify_playlist.runner.sync_year") as mock_sync_year,
    ):
        exit_code = main(["--stats"])

    assert exit_code == 0
    mock_sync_year.assert_not_called()
    assert cache_file.exists()
    assert load_stats_cache(path=cache_file) == {2021: 2}
    captured = capsys.readouterr()
    assert "Canciones por año" in captured.out
    assert "2021" in captured.out


def test_format_stats_chart_default_terminal_width():
    counts = {2014: 100}
    chart = format_stats_chart(counts)
    assert "Canciones por año" in chart
    assert "2014" in chart


def test_format_stats_chart_zero_and_small_counts():
    counts = {2015: 0, 2016: 1, 2020: 10000}
    chart = format_stats_chart(counts, terminal_width=80)
    lines = chart.splitlines()
    assert "2015" in lines[1]
    assert "2016" in lines[2]
    assert "2020" in lines[3]


def test_load_stats_cache_raw_string_and_invalid_counts(tmp_path: Path):
    cache_file = tmp_path / "stats_cache.json"

    # raw json as string
    import base64

    payload = json.dumps({"timestamp": time.time(), "counts": "not-a-dict"}).encode()
    b64 = base64.b64encode(payload).decode("ascii")
    cache_file.write_text(json.dumps(b64), encoding="utf-8")
    assert load_stats_cache(path=cache_file) is None

    # invalid json structure
    cache_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_stats_cache(path=cache_file) is None


def test_run_saves_stats_cache_on_sync(tmp_path: Path):
    from yearly_spotify_playlist.runner import run
    from yearly_spotify_playlist.yearly_playlists import YearResult

    cache_file = tmp_path / "stats_cache.json"
    fake_tracks = [LikedTrack(uri="t1", name="N1", artist="A1", liked_year=2022)]

    with (
        patch("yearly_spotify_playlist.runner.build_spotify"),
        patch("yearly_spotify_playlist.runner.SpotifyLibrary") as mock_lib_cls,
        patch(
            "yearly_spotify_playlist.runner._read_liked_tracks",
            return_value={2022: fake_tracks},
        ),
        patch(
            "yearly_spotify_playlist.runner._sync_all_years",
            return_value=[
                YearResult(
                    year=2022, playlist_id="p1", added=1, skipped=0, created=True
                )
            ],
        ),
    ):
        mock_lib = mock_lib_cls.return_value
        mock_lib.current_user.return_value = {"id": "uid", "display_name": "User"}
        mock_lib.owned_playlists_by_name.return_value = {}

        results = run(_settings(), cache_path=cache_file)

    assert len(results) == 1
    assert cache_file.exists()
    assert load_stats_cache(path=cache_file) == {2022: 1}


def test_cli_stats_force_update_bypasses_cache(tmp_path: Path, capsys):
    cache_file = tmp_path / "stats_cache.json"
    # Old cache has 2010: 50
    save_stats_cache({2010: 50}, path=cache_file)

    fresh_tracks = [LikedTrack(uri="t9", name="N9", artist="A9", liked_year=2024)]

    with (
        patch("yearly_spotify_playlist.cli.DEFAULT_CACHE_PATH", cache_file),
        patch("yearly_spotify_playlist.runner.DEFAULT_CACHE_PATH", cache_file),
        patch("yearly_spotify_playlist.cli.load_settings", return_value=_settings()),
        patch(
            "yearly_spotify_playlist.runner._read_liked_tracks",
            return_value={2024: fresh_tracks},
        ),
        patch("yearly_spotify_playlist.runner.SpotifyLibrary"),
        patch("yearly_spotify_playlist.runner.build_spotify"),
    ):
        exit_code = main(["-su"])

    assert exit_code == 0
    # Cache was updated with fresh data
    assert load_stats_cache(path=cache_file) == {2024: 1}
    captured = capsys.readouterr()
    assert "2024" in captured.out
    assert "2010" not in captured.out
