from __future__ import annotations

import pytest

from yearly_spotify_playlist.config import (
    DEFAULT_REDIRECT_URI,
    SCOPES,
    ConfigError,
    Settings,
    load_settings,
)

# -- Minimal valid environment ------------------------------------------------

_REQUIRED = {
    "SPOTIFY_CLIENT_ID": "test-client-id",
    "SPOTIFY_CLIENT_SECRET": "test-client-secret",
    "SPOTIFY_REFRESH_TOKEN": "test-refresh-token",
}


def _set_env(monkeypatch, overrides: dict[str, str] | None = None) -> None:
    """Populate the environment with the required variables (and optional extras)."""
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)
    for key, value in (overrides or {}).items():
        monkeypatch.setenv(key, value)


def _load(env_file: str = "nonexistent.env"):
    """Call load_settings with a dummy env_file so the real .env is never read."""
    return load_settings(env_file=env_file)


# -- Happy path ---------------------------------------------------------------


def test_load_settings_returns_all_fields(monkeypatch):
    _set_env(monkeypatch)
    settings = _load()

    assert settings.client_id == "test-client-id"
    assert settings.client_secret == "test-client-secret"
    assert settings.refresh_token == "test-refresh-token"
    assert settings.redirect_uri == DEFAULT_REDIRECT_URI
    assert settings.market is None


def test_load_settings_reads_optional_redirect_uri(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_REDIRECT_URI": "http://127.0.0.1:9999/cb"})
    assert _load().redirect_uri == "http://127.0.0.1:9999/cb"


def test_load_settings_reads_optional_market(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_MARKET": "ES"})
    assert _load().market == "ES"


def test_load_settings_strips_whitespace(monkeypatch):
    _set_env(
        monkeypatch,
        {
            "SPOTIFY_CLIENT_ID": "  id  ",
            "SPOTIFY_CLIENT_SECRET": " secret ",
            "SPOTIFY_REFRESH_TOKEN": " token\n",
            "SPOTIFY_REDIRECT_URI": "  http://127.0.0.1:8888/callback  ",
            "SPOTIFY_MARKET": " AR ",
        },
    )
    settings = _load()

    assert settings.client_id == "id"
    assert settings.client_secret == "secret"
    assert settings.refresh_token == "token"
    assert settings.redirect_uri == "http://127.0.0.1:8888/callback"
    assert settings.market == "AR"


# -- Missing / empty required variables --------------------------------------


@pytest.mark.parametrize("missing_var", list(_REQUIRED))
def test_load_settings_raises_when_required_var_is_missing(monkeypatch, missing_var):
    _set_env(monkeypatch)
    monkeypatch.delenv(missing_var)

    with pytest.raises(ConfigError, match=missing_var):
        _load()


@pytest.mark.parametrize("missing_var", list(_REQUIRED))
def test_load_settings_raises_when_required_var_is_empty(monkeypatch, missing_var):
    _set_env(monkeypatch)
    monkeypatch.setenv(missing_var, "")

    with pytest.raises(ConfigError, match=missing_var):
        _load()


@pytest.mark.parametrize("missing_var", list(_REQUIRED))
def test_load_settings_raises_when_required_var_is_only_whitespace(
    monkeypatch, missing_var
):
    _set_env(monkeypatch)
    monkeypatch.setenv(missing_var, "   ")

    with pytest.raises(ConfigError, match=missing_var):
        _load()


def test_load_settings_lists_all_missing_vars_at_once(monkeypatch):
    # None of the required vars are set.
    for key in _REQUIRED:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError, match="SPOTIFY_CLIENT_ID") as exc_info:
        _load()

    message = str(exc_info.value)
    for key in _REQUIRED:
        assert key in message


# -- Empty optional variables default correctly --------------------------------


def test_empty_redirect_uri_falls_back_to_default(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_REDIRECT_URI": ""})
    assert _load().redirect_uri == DEFAULT_REDIRECT_URI


def test_empty_market_becomes_none(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_MARKET": ""})
    assert _load().market is None


def test_whitespace_only_market_becomes_none(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_MARKET": "   "})
    assert _load().market is None


# -- New feature settings (DRY_RUN, SPOTIFY_YEARS, SPOTIFY_YEAR_FROM, BATCH_DELAY_SECONDS)


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "YES", " true "])
def test_load_settings_dry_run_truthy(monkeypatch, val):
    _set_env(monkeypatch, {"DRY_RUN": val})
    assert _load().dry_run is True


@pytest.mark.parametrize("val", ["0", "false", "no", "", "other"])
def test_load_settings_dry_run_falsy(monkeypatch, val):
    _set_env(monkeypatch, {"DRY_RUN": val})
    assert _load().dry_run is False


def test_load_settings_dry_run_default_is_false(monkeypatch):
    _set_env(monkeypatch)
    assert _load().dry_run is False


def test_load_settings_parses_years_list(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_YEARS": "2022, 2023, 2024"})
    assert _load().years == (2022, 2023, 2024)


def test_load_settings_parses_single_year(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_YEARS": "2024"})
    assert _load().years == (2024,)


def test_load_settings_invalid_years_raises(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_YEARS": "2024, not-a-year"})
    with pytest.raises(ConfigError, match="invalid SPOTIFY_YEARS"):
        _load()


def test_load_settings_parses_year_from(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_YEAR_FROM": "2021"})
    assert _load().year_from == 2021


def test_load_settings_invalid_year_from_raises(monkeypatch):
    _set_env(monkeypatch, {"SPOTIFY_YEAR_FROM": "abc"})
    with pytest.raises(ConfigError, match="invalid SPOTIFY_YEAR_FROM"):
        _load()


def test_load_settings_batch_delay_default(monkeypatch):
    _set_env(monkeypatch)
    assert _load().batch_delay_seconds == 0.1


def test_load_settings_batch_delay_custom(monkeypatch):
    _set_env(monkeypatch, {"BATCH_DELAY_SECONDS": "0.5"})
    assert _load().batch_delay_seconds == 0.5


def test_load_settings_batch_delay_negative_raises(monkeypatch):
    _set_env(monkeypatch, {"BATCH_DELAY_SECONDS": "-1"})
    with pytest.raises(ConfigError, match="invalid BATCH_DELAY_SECONDS"):
        _load()


def test_load_settings_batch_delay_invalid_raises(monkeypatch):
    _set_env(monkeypatch, {"BATCH_DELAY_SECONDS": "abc"})
    with pytest.raises(ConfigError, match="invalid BATCH_DELAY_SECONDS"):
        _load()


# -- Settings.scope property ---------------------------------------------------


def test_scope_joins_all_scopes():
    settings = Settings(
        client_id="id",
        client_secret="secret",
        refresh_token="token",
        redirect_uri="http://localhost",
        market=None,
    )
    assert settings.scope == " ".join(SCOPES)
