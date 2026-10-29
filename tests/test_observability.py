from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from yearly_spotify_playlist.cli import main
from yearly_spotify_playlist.log import PACKAGE, TqdmHandler, setup_logging
from yearly_spotify_playlist.spotify_api import SpotifyLibrary

# -- T3: setup_logging --------------------------------------------------------


def test_setup_logging_defaults_to_warning(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging()

    logger = logging.getLogger(PACKAGE)
    assert logger.level == logging.WARNING
    assert any(isinstance(h, TqdmHandler) for h in logger.handlers)


@pytest.mark.parametrize(
    ("env_val", "expected_level"),
    [
        ("debug", logging.DEBUG),
        ("DEBUG", logging.DEBUG),
        ("info", logging.INFO),
        ("ERROR", logging.ERROR),
        ("not-a-level", logging.WARNING),
        ("", logging.WARNING),
    ],
)
def test_setup_logging_respects_log_level(monkeypatch, env_val, expected_level):
    monkeypatch.setenv("LOG_LEVEL", env_val)
    setup_logging()

    logger = logging.getLogger(PACKAGE)
    assert logger.level == expected_level


def test_tqdm_handler_writes_through_tqdm():
    handler = TqdmHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello tqdm",
        args=(),
        exc_info=None,
    )

    with patch("yearly_spotify_playlist.log.progress.log") as mock_write:
        handler.emit(record)
        mock_write.assert_called_once_with("hello tqdm")


# -- T4: verbose traceback on error -------------------------------------------


def test_main_prints_traceback_when_debug(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    with (
        patch(
            "yearly_spotify_playlist.cli.load_settings",
            side_effect=RuntimeError("boom"),
        ),
        patch("traceback.print_exc") as mock_traceback,
    ):
        exit_code = main([])

    assert exit_code == 1
    mock_traceback.assert_called_once()


def test_main_omits_traceback_when_not_debug(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    with (
        patch(
            "yearly_spotify_playlist.cli.load_settings",
            side_effect=RuntimeError("boom"),
        ),
        patch("traceback.print_exc") as mock_traceback,
    ):
        exit_code = main([])

    assert exit_code == 1
    mock_traceback.assert_not_called()


# -- T5: warning on duplicate playlist names ----------------------------------


def test_owned_playlists_by_name_logs_warning_on_duplicates(caplog):
    client = MagicMock()
    client.current_user_playlists.return_value = {
        "items": [
            {"name": "2023", "id": "first-id", "owner": {"id": "me"}},
            {"name": "2023", "id": "second-id", "owner": {"id": "me"}},
        ],
        "next": None,
    }

    lib = SpotifyLibrary(client)
    with caplog.at_level(logging.WARNING, logger="yearly_spotify_playlist.spotify_api"):
        result = lib.owned_playlists_by_name("me")

    assert result["2023"]["id"] == "first-id"
    assert any("Found duplicate playlist '2023'" in r.message for r in caplog.records)


# -- Rich Progress unit tests -------------------------------------------------


def test_rich_progress_lifecycle():
    from yearly_spotify_playlist import progress

    progress.log("Test log outside bar")

    with progress.scan_progress(10) as bar:
        progress.describe(bar, "first step")
        bar.update(5)
        progress.log("Test log inside bar")

    with progress.year_progress(2) as y_bar:
        y_bar.set_postfix_str("2023")
        with progress.track_progress(2023, 5) as t_bar:
            t_bar.update(2)
            progress.describe(t_bar, "added song")
        y_bar.update(1)

    # Standalone track progress fallback
    with progress.track_progress(2024, 3) as single_bar:
        single_bar.update(1)


def test_progress_bars_have_spinner_column():
    from rich.progress import SpinnerColumn

    from yearly_spotify_playlist import progress

    with progress.scan_progress(10) as bar:
        assert isinstance(bar._progress.columns[0], SpinnerColumn)

    with progress.year_progress(2) as bar:
        assert isinstance(bar._progress.columns[0], SpinnerColumn)

    with progress.track_progress(2023, 5) as bar:
        assert isinstance(bar._progress.columns[0], SpinnerColumn)
