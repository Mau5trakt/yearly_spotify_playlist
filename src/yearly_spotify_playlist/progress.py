"""tqdm progress reporting for the two phases of a run."""

from __future__ import annotations

from tqdm import tqdm


def scan_progress(total: int) -> tqdm:
    """Bar for the phase that reads every saved track from the API."""
    return tqdm(
        total=total,
        desc="Reading your liked songs",
        unit="song",
        unit_scale=True,
        dynamic_ncols=True,
        leave=False,
    )


def year_progress(total_years: int) -> tqdm:
    """Outer bar: one step per year playlist."""
    return tqdm(
        total=total_years,
        desc="Yearly playlists",
        unit="year",
        dynamic_ncols=True,
        position=0,
        leave=False,
    )


def track_progress(year: int, total_tracks: int) -> tqdm:
    """Inner bar: one step per track of the year currently being synced."""
    return tqdm(
        total=total_tracks,
        desc=f"Playlist {year}",
        unit="track",
        dynamic_ncols=True,
        position=1,
        leave=False,
    )


def describe(bar: tqdm, message: str) -> None:
    """Show ``message`` next to ``bar`` and repaint immediately."""
    bar.set_postfix_str(message, refresh=True)


def log(message: str) -> None:
    """Print ``message`` above the live bars without breaking them."""
    tqdm.write(message)