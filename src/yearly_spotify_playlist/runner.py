"""Orchestration of a full run: read likes, then sync one playlist per year."""

from __future__ import annotations

from typing import Any

from spotipy import SpotifyException

from . import progress
from .config import ConfigError, Settings
from .liked_tracks import LikedTrack, group_by_year
from .spotify_api import SpotifyLibrary, build_spotify
from .yearly_playlists import YearResult, playlist_name, sync_year


class RunError(RuntimeError):
    """Raised when the run cannot continue and the user needs to act."""


def run(settings: Settings) -> list[YearResult]:
    """Execute the single purpose of this CLI and return the per-year results."""
    library = SpotifyLibrary(build_spotify(settings), market=settings.market)

    user = library.current_user()
    user_id = user["id"]
    progress.log(f"Connected as {user.get('display_name') or user_id} ({user_id})")

    grouped = _read_liked_tracks(library)
    if not grouped:
        raise RunError(
            "No liked songs were found in your Spotify library."
        )

    total_tracks = sum(len(tracks) for tracks in grouped.values())
    years = ", ".join(str(year) for year in sorted(grouped, reverse=True))
    progress.log(
        f"{total_tracks} liked songs spread across {len(grouped)} years: {years}"
    )

    existing = library.owned_playlists_by_name(user_id)
    return _sync_all_years(library, grouped, existing, settings)


def _read_liked_tracks(library: SpotifyLibrary) -> dict[int, list[LikedTrack]]:
    """Page through ``GET /me/tracks`` and bucket everything by liked year."""
    pages = library.iter_saved_track_pages()
    first = next(pages, None)
    if first is None:
        return {}

    items: list[Any] = list(first.get("items", []))
    total = first.get("total") or len(items)

    with progress.scan_progress(total) as bar:
        progress.describe(bar, "requesting the first page")
        bar.update(len(items))
        for page in pages:
            page_items = page.get("items", [])
            items.extend(page_items)
            bar.update(len(page_items))

    return group_by_year(items)


def _sync_all_years(
    library: SpotifyLibrary,
    grouped: dict[int, list[LikedTrack]],
    existing: dict[str, dict[str, Any]],
    settings: Settings,
) -> list[YearResult]:
    results: list[YearResult] = []

    with progress.year_progress(len(grouped)) as years_bar:
        for year, tracks in grouped.items():
            name = playlist_name(year)
            years_bar.set_postfix_str(name, refresh=True)

            with progress.track_progress(year, len(tracks)) as tracks_bar:

                def on_status(message: str) -> None:
                    progress.describe(tracks_bar, message)

                def on_track(track: LikedTrack, added: bool) -> None:
                    if added:
                        progress.describe(
                            tracks_bar, f'added "{track.name}" to playlist {name}'
                        )
                    else:
                        progress.describe(
                            tracks_bar, f'"{track.name}" was already in playlist {name}'
                        )
                    tracks_bar.update(1)

                result = sync_year(
                    library,
                    year,
                    tracks,
                    existing_playlist=existing.get(name),
                    on_status=on_status,
                    on_track=on_track,
                )

            results.append(result)
            progress.log(_summary_line(result))
            years_bar.update(1)

    return results


def _summary_line(result: YearResult) -> str:
    origin = "created" if result.created else "reused"
    parts = [f"  {result.year}: playlist {origin}"]
    parts.append(f"{result.added} added")
    if result.skipped:
        parts.append(f"{result.skipped} already there")
    return " | ".join(parts)


def explain(exc: Exception) -> str:
    """Turn a low-level failure into something the user can act on."""
    if isinstance(exc, ConfigError):
        return str(exc)

    if isinstance(exc, SpotifyException):
        status = exc.http_status
        if status in (401, 403):
            return (
                f"Spotify rejected the request ({status}). Your refresh token expired or "
                "lacks the required permissions. Re-authorize the app with "
                "`python -m yearly_spotify_playlist.auth` and update "
                "SPOTIFY_REFRESH_TOKEN in your .env."
            )
        if status == 429:
            retry_after = (exc.headers or {}).get("Retry-After")
            wait = f" Spotify suggests retrying in {retry_after} seconds." if retry_after else ""
            return (
                "Spotify's request limit was reached (429) even after "
                f"retrying.{wait}"
            )
        return f"Spotify returned an error ({status}): {exc}"

    return f"Run failed: {type(exc).__name__}: {exc}"