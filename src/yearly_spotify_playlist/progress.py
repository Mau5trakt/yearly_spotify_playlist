"""Rich progress reporting for the two phases of a run."""

from __future__ import annotations

import sys
from types import TracebackType
from typing import Any, Self

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)

_console: Console | None = None
_active_progress: Progress | None = None
_shared_sync_progress: Progress | None = None


def make_console_utf8_safe() -> None:
    """Ensure standard streams support UTF-8 on legacy Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except ValueError, OSError:  # pragma: no cover - detached stream
                pass


def get_console() -> Console:
    """Get the active console instance, lazily created."""
    global _console
    if _console is None:
        make_console_utf8_safe()
        _console = Console()
    return _console


def log(message: Any) -> None:
    """Print ``message`` above the live bars without breaking them."""
    if _active_progress is not None:
        _active_progress.console.print(message)
    else:
        get_console().print(message)


class ProgressBar:
    """Adapter matching the progress bar protocol used by runner and callbacks."""

    def __init__(
        self,
        progress: Progress,
        task_id: TaskID,
        *,
        manage_progress: bool = False,
        on_exit: Any = None,
    ) -> None:
        self._progress = progress
        self._task_id = task_id
        self._manage_progress = manage_progress
        self._on_exit = on_exit

    def update(self, advance: int = 1) -> None:
        self._progress.update(self._task_id, advance=advance)

    def set_postfix_str(self, message: str, refresh: bool = True) -> None:
        self._progress.update(self._task_id, status=message)

    def __enter__(self) -> Self:
        global _active_progress
        if self._manage_progress:
            _active_progress = self._progress
            if not self._progress.live.is_started:
                self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        global _active_progress
        if self._on_exit is not None:
            self._on_exit(exc_type, exc_val, exc_tb)
        elif self._manage_progress:
            self._progress.stop()
            _active_progress = None
        else:
            self._progress.remove_task(self._task_id)


def scan_progress(total: int) -> ProgressBar:
    """Bar for the phase that reads every saved track from the API."""
    p = Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}"),
        console=get_console(),
        transient=True,
    )
    task_id = p.add_task("Reading your liked songs", total=total, status="")
    return ProgressBar(p, task_id, manage_progress=True)


def year_progress(total_years: int) -> ProgressBar:
    """Outer bar: one step per year playlist."""
    global _shared_sync_progress, _active_progress
    _shared_sync_progress = Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}"),
        console=get_console(),
        transient=True,
    )
    _active_progress = _shared_sync_progress
    _shared_sync_progress.start()
    task_id = _shared_sync_progress.add_task(
        "Yearly playlists", total=total_years, status=""
    )

    def _on_exit(
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        global _shared_sync_progress, _active_progress
        if _shared_sync_progress is not None:
            _shared_sync_progress.stop()
            _shared_sync_progress = None
            _active_progress = None

    return ProgressBar(
        _shared_sync_progress,
        task_id,
        manage_progress=False,
        on_exit=_on_exit,
    )


def track_progress(year: int, total_tracks: int) -> ProgressBar:
    """Inner bar: one step per track of the year currently being synced."""
    if _shared_sync_progress is None:
        p = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[status]}"),
            console=get_console(),
            transient=True,
        )
        task_id = p.add_task(f"Playlist {year}", total=total_tracks, status="")
        return ProgressBar(p, task_id, manage_progress=True)

    task_id = _shared_sync_progress.add_task(
        f"Playlist {year}", total=total_tracks, status=""
    )
    return ProgressBar(_shared_sync_progress, task_id, manage_progress=False)


def describe(bar: Any, message: str) -> None:
    """Show ``message`` next to ``bar`` and repaint immediately."""
    bar.set_postfix_str(message)
