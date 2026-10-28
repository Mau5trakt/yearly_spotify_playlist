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
from rich.table import Table
from rich.text import Text

from .liked_tracks import LikedTrack

DEFAULT_CACHE_PATH = Path("stats_cache.json")
CACHE_TTL_SECONDS = 3600  # 1 hour
MIN_BAR_WIDTH = 10


def stats_from_tracks(tracks: Iterable[LikedTrack]) -> dict[int, int]:
    """Calculate the number of saved songs per liked year, sorted ascending."""
    counts: dict[int, int] = {}
    for track in tracks:
        counts[track.liked_year] = counts.get(track.liked_year, 0) + 1
    return dict(sorted(counts.items()))


def save_stats_cache(
    counts: dict[int, int],
    path: Path | str = DEFAULT_CACHE_PATH,
    timestamp: float | None = None,
) -> None:
    """Save statistics to a base64-encoded JSON cache file."""
    cache_path = Path(path)
    now = time.time() if timestamp is None else timestamp
    payload = {
        "version": 1,
        "timestamp": now,
        "counts": {str(year): count for year, count in sorted(counts.items())},
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
) -> dict[int, int] | None:
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

        return {int(year): int(count) for year, count in counts_dict.items()}
    except Exception:  # noqa: BLE001 - any malformed or corrupted cache behaves as miss
        return None


def get_stats_renderable(
    counts: dict[int, int],
    terminal_width: int | None = None,
    bar_color: str = "green",
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

    non_bar_space = year_col_width + max_count_len + 6
    total = sum(counts.values())
    song_word = "song" if total == 1 else "songs"
    summary_line = f"You have liked {total} {song_word} in Spotify."

    if terminal_width - non_bar_space < MIN_BAR_WIDTH:
        # Fallback to simple list
        lines = [f"{year} {counts[year]}" for year in sorted_years]
        return f"{header}\n" + "\n".join(lines) + f"\n\n{summary_line}"

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
    table.add_column(no_wrap=True, justify="right")

    effective_max = max(max_count, 1)
    for idx, year in enumerate(sorted_years):
        if idx > 0:
            table.add_row("", "", "")
        count = counts[year]
        bar = Bar(
            size=effective_max,
            begin=0,
            end=count,
            width=available_bar_width,
            color=bar_color,
        )
        table.add_row(str(year), bar, str(count))

    summary = Text.from_markup(
        f"\nYou have liked [green]{total}[/green] {song_word} in Spotify.",
        style="bold",
    )
    return Group(table, summary)


def format_stats_chart(
    counts: dict[int, int],
    terminal_width: int | None = None,
    bar_color: str = "green",
) -> str:
    """Render a horizontal bar chart of songs per year in ascending order using Rich.

    If terminal width is too narrow to display a meaningful bar (at least
    ``MIN_BAR_WIDTH`` chars), falls back to a simple list of year and count.
    """
    renderable = get_stats_renderable(
        counts, terminal_width=terminal_width, bar_color=bar_color
    )
    if isinstance(renderable, str):
        return renderable
    console = Console(width=terminal_width or 80, record=True, no_color=True)
    console.print(renderable)
    return console.export_text().rstrip("\n")
