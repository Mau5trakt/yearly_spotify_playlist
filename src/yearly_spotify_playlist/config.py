"""Configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Spotify rejects "localhost" as a redirect URI; only loopback IP literals are allowed.
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_TOKEN_CACHE_PATH = Path(".spotify_token.json")

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
    redirect_uri: str
    market: str | None
    refresh_token: str | None = None
    dry_run: bool = False
    years: tuple[int, ...] | None = None
    year_from: int | None = None
    batch_delay_seconds: float = 0.1

    @property
    def scope(self) -> str:
        """Scope string shared by the auth manager and the cached token info."""
        return " ".join(SCOPES)


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


def load_token_cache(path: Path | str = DEFAULT_TOKEN_CACHE_PATH) -> str | None:
    """Read the stored refresh token from a JSON file, or None if missing/invalid."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            token = data.get("refresh_token")
            if isinstance(token, str) and token.strip():
                return token.strip()
    except Exception:  # noqa: BLE001
        return None
    return None


def save_token_cache(
    refresh_token: str, path: Path | str = DEFAULT_TOKEN_CACHE_PATH
) -> None:
    """Save the refresh token to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"refresh_token": refresh_token.strip()}, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_token_cache(path: Path | str = DEFAULT_TOKEN_CACHE_PATH) -> None:
    """Remove the token cache file if present."""
    p = Path(path)
    p.unlink(missing_ok=True)


def load_settings(
    *,
    env_file: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    token_cache_path: Path | str = DEFAULT_TOKEN_CACHE_PATH,
) -> Settings:
    """Build :class:`Settings` from the environment and token cache.

    A ``.env`` file sitting next to the project is loaded first so that real
    environment variables keep precedence over it.

    Raises:
        ConfigError: when a required variable (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET) is missing or empty.
    """
    load_dotenv(env_file)

    missing = [
        name
        for name in (
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
        )
        if not (os.getenv(name) or "").strip()
    ]
    if missing:
        raise ConfigError(
            "missing environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env, fill in the values and try again."
        )

    env_token = (os.getenv("SPOTIFY_REFRESH_TOKEN") or "").strip() or None
    refresh_token = env_token or load_token_cache(path=token_cache_path)

    return Settings(
        client_id=(os.environ["SPOTIFY_CLIENT_ID"]).strip(),
        client_secret=(os.environ["SPOTIFY_CLIENT_SECRET"]).strip(),
        refresh_token=refresh_token,
        redirect_uri=(
            os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI
        ).strip(),
        market=(os.getenv("SPOTIFY_MARKET") or "").strip() or None,
        dry_run=dry_run,
        years=_parse_years(os.getenv("SPOTIFY_YEARS")),
        year_from=_parse_year_from(os.getenv("SPOTIFY_YEAR_FROM")),
        batch_delay_seconds=_parse_batch_delay(os.getenv("BATCH_DELAY_SECONDS")),
    )
