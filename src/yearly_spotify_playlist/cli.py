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

from . import progress
from .config import load_settings
from .log import PACKAGE, setup_logging
from .progress import make_console_utf8_safe
from .runner import explain, get_stats_chart, run
from .stats import DEFAULT_CACHE_PATH


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
    parser.add_argument(
        "-s",
        "--stats",
        nargs="?",
        const=True,
        default=False,
        metavar="u",
        help=(
            "display statistics of liked songs per year without modifying playlists "
            "(pass 'u' or use -u to force refresh from Spotify)"
        ),
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="force refresh of liked songs from Spotify, bypassing the 1-hour cache",
    )
    args = parser.parse_args(argv)
    if isinstance(args.stats, str) and args.stats.lower() not in (
        "u",
        "update",
        "refresh",
    ):
        parser.error(
            f"invalid value for -s/--stats: {args.stats!r} (expected 'u' or 'update')"
        )
    return args


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
        force_update = bool(
            args.update
            or (
                isinstance(args.stats, str)
                and args.stats.lower() in ("u", "update", "refresh")
            )
        )
        if args.stats:
            chart = get_stats_chart(
                settings,
                cache_path=DEFAULT_CACHE_PATH,
                force_update=force_update,
            )
            progress.log(chart)
            return 0
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
    progress.log(
        f"{prefix}: {len(results)} yearly playlists, {total_added} songs {action}."
    )
    if not settings.dry_run:
        progress.log("")
        progress.log(get_stats_chart(settings, cache_path=DEFAULT_CACHE_PATH))
    return 0


_make_console_utf8_safe = make_console_utf8_safe
