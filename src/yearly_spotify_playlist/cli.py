"""Command-line entry point for yearly-spotify-playlist.

All presentation logic (console encoding, exit codes, user-facing messages)
lives here so that ``__init__.py`` stays a clean package facade.
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from collections.abc import Sequence
from dataclasses import replace

from .config import load_settings
from .log import PACKAGE, setup_logging
from .runner import explain, run


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the yearly-spotify-playlist script."""
    parser = argparse.ArgumentParser(
        prog="yearly-spotify-playlist",
        description=(
            "Create one Spotify playlist per year based on when you liked each song."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview playlist creations and track additions without modifying Spotify",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``yearly-spotify-playlist`` console script."""
    _make_console_utf8_safe()
    setup_logging()
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)

    try:
        settings = load_settings(dry_run=args.dry_run)
        settings = replace(settings, dry_run=args.dry_run)
        results = run(settings)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - the CLI turns anything into advice
        if logging.getLogger(PACKAGE).isEnabledFor(logging.DEBUG):
            traceback.print_exc()
        print(explain(exc), file=sys.stderr)
        return 1

    total_added = sum(result.added for result in results)
    action = "would be added" if settings.dry_run else "added"
    prefix = "Done (dry-run)" if settings.dry_run else "Done"
    print(f"{prefix}: {len(results)} yearly playlists, {total_added} songs {action}.")
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
            except ValueError, OSError:  # pragma: no cover - detached stream
                pass
