"""yearly-spotify-playlist: one playlist per year, based on when you liked the song.

This package exposes a single-purpose CLI. It takes no arguments: every setting
comes from environment variables.
"""

from __future__ import annotations

from .cli import main

__all__ = ["main"]
