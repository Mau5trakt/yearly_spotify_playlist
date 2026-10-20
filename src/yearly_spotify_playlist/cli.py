"""Command-line entry point for yearly-spotify-playlist.

All presentation logic (console encoding, exit codes, user-facing messages)
lives here so that ``__init__.py`` stays a clean package facade.
"""

from __future__ import annotations

import sys

from .config import load_settings
from .runner import explain, run


def main() -> int:
    """Entry point for the ``yearly-spotify-playlist`` console script."""
    _make_console_utf8_safe()
    try:
        settings = load_settings()
        results = run(settings)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - the CLI turns anything into advice
        print(explain(exc), file=sys.stderr)
        return 1

    total_added = sum(result.added for result in results)
    print(f"Done: {len(results)} yearly playlists, {total_added} songs added.")
    return 0


def _make_console_utf8_safe() -> None:
    """Never crash printing Spanish accents on a legacy Windows code page.

    The console keeps its own encoding; only unencodable characters degrade to a
    replacement mark instead of raising ``UnicodeEncodeError``.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):  # pragma: no cover - detached stream
                pass
