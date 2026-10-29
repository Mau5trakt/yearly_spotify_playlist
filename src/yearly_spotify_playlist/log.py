"""Package-wide logging, configured from the ``LOG_LEVEL`` environment variable.

The handler writes through :func:`progress.log` so log lines never break the
live progress bars.
"""

from __future__ import annotations

import logging
import os

from . import progress

PACKAGE = __name__.rsplit(".", 1)[0]  # "yearly_spotify_playlist"


class TqdmHandler(logging.Handler):
    """Emit log records through :func:`progress.log` to avoid corrupting bars."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            progress.log(self.format(record))
        except Exception:  # noqa: BLE001 — logging must never crash the app
            self.handleError(record)


RichProgressHandler = TqdmHandler


def setup_logging() -> None:
    """Configure the package logger once, reading ``LOG_LEVEL`` from the env.

    Defaults to ``WARNING`` when the variable is absent or invalid.
    """
    level_name = (os.getenv("LOG_LEVEL") or "WARNING").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.WARNING

    handler = TqdmHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger = logging.getLogger(PACKAGE)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
