"""Configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Spotify rejects "localhost" as a redirect URI; only loopback IP literals are allowed.
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"

#: Scopes the tool needs. ``playlist-modify-public`` covers creating the playlists;
#: ``playlist-read-private`` is what lets an existing playlist be found and reused.
SCOPES: tuple[str, ...] = (
    "user-library-read",
    "playlist-modify-private",
    "playlist-modify-public",
    "playlist-read-private",
)


class ConfigError(RuntimeError):
    """Raised when the environment does not describe a usable configuration."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the CLI needs to talk to Spotify, resolved from the environment."""

    client_id: str
    client_secret: str
    refresh_token: str
    redirect_uri: str
    market: str | None
    dry_run: bool = False
    years: tuple[int, ...] | None = None
    year_from: int | None = None
    batch_delay_seconds: float = 0.1

    @property
    def scope(self) -> str:
        """Scope string shared by the auth manager and the cached token info."""
        return " ".join(SCOPES)


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes")


def _parse_years(value: str | None) -> tuple[int, ...] | None:
    if not value or not value.strip():
        return None
    try:
        years = tuple(int(y.strip()) for y in value.split(",") if y.strip())
    except ValueError as exc:
        raise ConfigError(
            f"invalid SPOTIFY_YEARS: expected comma-separated integers, got {value!r}"
        ) from exc
    if not years:
        raise ConfigError(
            f"invalid SPOTIFY_YEARS: expected comma-separated integers, got {value!r}"
        )
    return years


def _parse_year_from(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ConfigError(
            f"invalid SPOTIFY_YEAR_FROM: expected integer, got {value!r}"
        ) from exc


def _parse_batch_delay(value: str | None) -> float:
    if not value or not value.strip():
        return 0.1
    try:
        val = float(value.strip())
    except ValueError as exc:
        raise ConfigError(
            f"invalid BATCH_DELAY_SECONDS: expected float, got {value!r}"
        ) from exc
    if val < 0:
        raise ConfigError(
            f"invalid BATCH_DELAY_SECONDS: expected non-negative number, got {val}"
        )
    return val


def load_settings(*, env_file: str | os.PathLike[str] | None = None) -> Settings:
    """Build :class:`Settings` from the environment.

    A ``.env`` file sitting next to the project is loaded first so that real
    environment variables keep precedence over it.

    Raises:
        ConfigError: when a required variable is missing or empty.
    """
    load_dotenv(env_file)

    missing = [
        name
        for name in (
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
            "SPOTIFY_REFRESH_TOKEN",
        )
        if not (os.getenv(name) or "").strip()
    ]
    if missing:
        raise ConfigError(
            "missing environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env, fill in the values and try again."
        )

    return Settings(
        client_id=(os.environ["SPOTIFY_CLIENT_ID"]).strip(),
        client_secret=(os.environ["SPOTIFY_CLIENT_SECRET"]).strip(),
        refresh_token=(os.environ["SPOTIFY_REFRESH_TOKEN"]).strip(),
        redirect_uri=(
            os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI
        ).strip(),
        market=(os.getenv("SPOTIFY_MARKET") or "").strip() or None,
        dry_run=_parse_bool(os.getenv("DRY_RUN")),
        years=_parse_years(os.getenv("SPOTIFY_YEARS")),
        year_from=_parse_year_from(os.getenv("SPOTIFY_YEAR_FROM")),
        batch_delay_seconds=_parse_batch_delay(os.getenv("BATCH_DELAY_SECONDS")),
    )
