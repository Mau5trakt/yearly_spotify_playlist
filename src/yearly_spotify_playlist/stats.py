"""Statistics computation, caching in base64 JSON, and terminal bar chart formatting."""

from __future__ import annotations

import base64
import json
import shutil
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rich.bar import Bar
from rich.console import Console, Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from .liked_tracks import LikedTrack

DEFAULT_CACHE_PATH = Path("stats_cache.json")
CACHE_TTL_SECONDS = 3600  # 1 hour
MIN_BAR_WIDTH = 10


class StatsCounts(dict[int, int]):
    """Mapping of year to song count, with optional first saved track metadata."""

    def __init__(
        self,
        *args: Any,
        first_track: dict[str, str] | LikedTrack | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.first_track = first_track


def _extract_first_track(track_obj: Any) -> tuple[str, str, str] | None:
    if track_obj is None:
        return None
    if isinstance(track_obj, dict):
        name = track_obj.get("name")
        artist = track_obj.get("artist")
        added_at = track_obj.get("added_at")
    else:
        name = getattr(track_obj, "name", None)
        artist = getattr(track_obj, "artist", None)
        added_at = getattr(track_obj, "added_at", None)
    if name and artist and added_at:
        return str(name), str(artist), str(added_at)
    return None


def first_saved_track(tracks: Iterable[LikedTrack]) -> LikedTrack | None:
    """Find the earliest saved track by ISO timestamp."""
    valid = [t for t in tracks if t.added_at]
    if not valid:
        return None
    return min(valid, key=lambda t: t.added_at)


def stats_from_tracks(tracks: Iterable[LikedTrack]) -> StatsCounts:
    """Calculate the number of saved songs per liked year, sorted ascending."""
    counts: dict[int, int] = {}
    track_list = list(tracks)
    for track in track_list:
        counts[track.liked_year] = counts.get(track.liked_year, 0) + 1
    earliest = first_saved_track(track_list)
    first_dict = (
        {
            "name": earliest.name,
            "artist": earliest.artist,
            "added_at": earliest.added_at,
        }
        if earliest and earliest.added_at
        else None
    )
    return StatsCounts(sorted(counts.items()), first_track=first_dict)


def save_stats_cache(
    counts: dict[int, int],
    path: Path | str = DEFAULT_CACHE_PATH,
    timestamp: float | None = None,
    first_track: dict[str, str] | LikedTrack | None = None,
) -> None:
    """Save statistics to a base64-encoded JSON cache file."""
    cache_path = Path(path)
    now = time.time() if timestamp is None else timestamp
    payload: dict[str, Any] = {
        "version": 1,
        "timestamp": now,
        "counts": {str(year): count for year, count in sorted(counts.items())},
    }
    extracted = _extract_first_track(
        first_track if first_track is not None else getattr(counts, "first_track", None)
    )
    if extracted:
        payload["first_track"] = {
            "name": extracted[0],
            "artist": extracted[1],
            "added_at": extracted[2],
        }
    json_bytes = json.dumps(payload).encode("utf-8")
    b64_str = base64.b64encode(json_bytes).decode("ascii")
    container = {
        "format": "yearly-spotify-playlist-stats-v1",
        "data": b64_str,
    }
    cache_path.write_text(json.dumps(container, indent=2), encoding="utf-8")


def load_stats_cache(
    path: Path | str = DEFAULT_CACHE_PATH,
    max_age_seconds: float = CACHE_TTL_SECONDS,
) -> StatsCounts | None:
    """Load statistics from the base64-encoded JSON cache if present and valid.

    Returns ``None`` if the file does not exist, is corrupted, or has expired (> 1 hour).
    """
    cache_path = Path(path)
    if not cache_path.exists():
        return None

    try:
        raw = cache_path.read_text(encoding="utf-8")
        raw_json = json.loads(raw)
        if isinstance(raw_json, dict) and "data" in raw_json:
            b64_data = raw_json["data"]
        elif isinstance(raw_json, str):
            b64_data = raw_json
        else:
            return None

        decoded = base64.b64decode(b64_data.encode("ascii"))
        payload: dict[str, Any] = json.loads(decoded.decode("utf-8"))

        ts = float(payload.get("timestamp", 0))
        if time.time() - ts > max_age_seconds:
            return None

        counts_dict = payload.get("counts")
        if not isinstance(counts_dict, dict):
            return None

        first_track = payload.get("first_track")
        return StatsCounts(
            {int(year): int(count) for year, count in counts_dict.items()},
            first_track=first_track if isinstance(first_track, dict) else None,
        )
    except Exception:  # noqa: BLE001 - any malformed or corrupted cache behaves as miss
        return None


def get_stats_renderable(
    counts: dict[int, int],
    terminal_width: int | None = None,
    bar_color: str = "green",
    first_track: dict[str, str] | LikedTrack | None = None,
) -> Any:
    """Return a Rich renderable (Group, Table, or Text) for the stats chart."""
    header = "Songs per year"
    if not counts:
        return f"{header}\nNo saved tracks found."

    sorted_years = sorted(counts.keys())
    if terminal_width is None:
        terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns

    max_count = max(counts.values())
    max_count_len = max(len(str(c)) for c in counts.values())
    year_col_width = max(len(str(y)) for y in sorted_years)

    top_years = [
        year for year, count in counts.items() if count == max_count and max_count > 0
    ]
    winner_year = top_years[0] if len(top_years) == 1 else None

    non_bar_space = year_col_width + max_count_len + 8
    total = sum(counts.values())
    song_word = "song" if total == 1 else "songs"
    summary_line = f"You have liked {total} {song_word} in Spotify."

    first_info = _extract_first_track(
        first_track if first_track is not None else getattr(counts, "first_track", None)
    )
    first_plain = ""
    if first_info:
        first_plain = f'\nYour first saved song was "{first_info[0]}" by {first_info[1]} on {first_info[2]}.'

    if terminal_width - non_bar_space < MIN_BAR_WIDTH:
        # Fallback to simple list
        lines = [f"{year} {counts[year]}" for year in sorted_years]
        return f"{header}\n" + "\n".join(lines) + f"\n\n{summary_line}{first_plain}"

    available_bar_width = max(MIN_BAR_WIDTH, min(terminal_width - non_bar_space, 50))
    table = Table(
        title=header,
        show_header=False,
        box=None,
        padding=(0, 1),
        collapse_padding=True,
    )
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True, justify="right")

    effective_max = max(max_count, 1)
    for idx, year in enumerate(sorted_years):
        if idx > 0:
            table.add_row("", "", "", "")
        count = counts[year]
        is_top = year == winner_year
        color = "gold1" if is_top else bar_color
        crown = "👑" if is_top else ""
        bar = Bar(
            size=effective_max,
            begin=0,
            end=count,
            width=available_bar_width,
            color=color,
        )
        table.add_row(str(year), bar, crown, str(count))

    summary_markup = f"\nYou have liked [green]{total}[/green] {song_word} in Spotify."
    if first_info:
        summary_markup += f'\nYour first saved song was "[green]{escape(first_info[0])}[/green]" by [green]{escape(first_info[1])}[/green] on [green]{escape(first_info[2])}[/green].'
    summary = Text.from_markup(summary_markup, style="bold")
    return Group(table, summary)


def format_stats_chart(
    counts: dict[int, int],
    terminal_width: int | None = None,
    bar_color: str = "green",
    first_track: dict[str, str] | LikedTrack | None = None,
) -> str:
    """Render a horizontal bar chart of songs per year in ascending order using Rich.

    If terminal width is too narrow to display a meaningful bar (at least
    ``MIN_BAR_WIDTH`` chars), falls back to a simple list of year and count.
    """
    renderable = get_stats_renderable(
        counts,
        terminal_width=terminal_width,
        bar_color=bar_color,
        first_track=first_track,
    )
    if isinstance(renderable, str):
        return renderable
    console = Console(width=terminal_width or 80, record=True, no_color=True)
    console.print(renderable)
    return console.export_text().rstrip("\n")
