from __future__ import annotations

import pytest

from yearly_spotify_playlist.config import load_settings

_ENV_VARS = (
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "SPOTIFY_REFRESH_TOKEN",
    "SPOTIFY_REDIRECT_URI",
    "SPOTIFY_MARKET",
    "SPOTIFY_PUBLIC_PLAYLISTS",
)


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _env_file(tmp_path, *, public_playlists: str | None = None):
    lines = [
        "SPOTIFY_CLIENT_ID=id",
        "SPOTIFY_CLIENT_SECRET=secret",
        "SPOTIFY_REFRESH_TOKEN=token",
    ]
    if public_playlists is not None:
        lines.append(f"SPOTIFY_PUBLIC_PLAYLISTS={public_playlists}")
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_playlists_are_private_when_the_flag_is_unset(tmp_path):
    settings = load_settings(env_file=_env_file(tmp_path))

    assert settings.public_playlists is False


def test_playlists_are_private_when_the_flag_is_explicitly_false(tmp_path):
    settings = load_settings(env_file=_env_file(tmp_path, public_playlists="false"))

    assert settings.public_playlists is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "y", "on"])
def test_the_env_var_still_opts_into_public_playlists(tmp_path, value):
    settings = load_settings(env_file=_env_file(tmp_path, public_playlists=value))

    assert settings.public_playlists is True


def test_the_env_var_is_not_ignored_when_a_real_variable_is_set(monkeypatch, tmp_path):
    monkeypatch.setenv("SPOTIFY_PUBLIC_PLAYLISTS", "true")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "real-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "real-secret")
    monkeypatch.setenv("SPOTIFY_REFRESH_TOKEN", "real-token")

    settings = load_settings(env_file=_env_file(tmp_path))

    assert settings.public_playlists is True