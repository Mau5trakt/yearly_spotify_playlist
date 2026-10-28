"""Statistics computation, caching in base64 JSON, and terminal bar chart formatting."""

from __future__ import annotations

import base64
import json
import shutil
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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


def format_stats_chart(
    counts: dict[int, int],
    terminal_width: int | None = None,
    bar_char: str = "-",
) -> str:
    """Render a horizontal bar chart of songs per year in ascending order.

    If terminal width is too narrow to display a meaningful bar (at least
    ``MIN_BAR_WIDTH`` chars), falls back to a simple list of year and count.
    """
    header = "Canciones por año"
    if not counts:
        return f"{header}\nNo hay canciones registradas."

    sorted_years = sorted(counts.keys())
    if terminal_width is None:
        terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns

    max_count = max(counts.values())
    max_count_len = max(len(str(c)) for c in counts.values())
    year_col_width = max(len(str(y)) for y in sorted_years)

    # Line layout: "<year> <bar> <count>"
    # Non-bar space needed: year + 1 space + 1 space + count
    non_bar_space = year_col_width + 1 + 1 + max_count_len
    available_bar_width = terminal_width - non_bar_space

    if available_bar_width < MIN_BAR_WIDTH:
        # Fallback to simple list
        lines = [f"{year} {counts[year]}" for year in sorted_years]
        return f"{header}\n" + "\n".join(lines)

    lines = []
    for year in sorted_years:
        count = counts[year]
        if max_count > 0:
            bar_len = round((count / max_count) * available_bar_width)
            if count > 0 and bar_len == 0:
                bar_len = 1
        else:
            bar_len = 0
        bar = bar_char * bar_len
        lines.append(f"{year} {bar} {count}")

    return f"{header}\n" + "\n".join(lines)
