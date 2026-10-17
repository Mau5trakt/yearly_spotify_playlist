"""Creating and filling the per-year playlists."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from .liked_tracks import LikedTrack
from .spotify_api import SpotifyLibrary

#: ``POST /playlists/{id}/items`` accepts at most 100 URIs per request.
ADD_BATCH_SIZE = 100

#: Human-readable status, emitted right before a network call.
StatusCallback = Callable[[str], None]

#: One track has been settled (either added or skipped), for progress reporting.
TrackCallback = Callable[[LikedTrack, bool], None]


@dataclass(frozen=True, slots=True)
class YearResult:
    """Outcome of synchronising a single year."""

    year: int
    playlist_id: str
    created: bool
    added: int
    skipped: int


def playlist_name(year: int) -> str:
    """A playlist is named after the year its songs were liked in."""
    return str(year)


def playlist_description(year: int) -> str:
    """Short description attached to playlists this tool creates."""
    return f"Liked songs in {year}"


def chunked[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Yield consecutive slices of ``items`` of at most ``size`` elements."""
    if size <= 0:
        raise ValueError("size must be positive")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def select_new_tracks(
    tracks: Sequence[LikedTrack], already_present: frozenset[str] | set[str]
) -> list[LikedTrack]:
    """Keep only the tracks that are not in the playlist yet, preserving order."""
    return [track for track in tracks if track.uri not in already_present]


def sync_year(
    library: SpotifyLibrary,
    year: int,
    tracks: Sequence[LikedTrack],
    *,
    existing_playlist: dict | None,
    on_status: StatusCallback,
    on_track: TrackCallback,
) -> YearResult:
    """Create (or reuse) the playlist for ``year`` and add whatever is missing.

    Reusing an existing playlist is what makes the tool safe to re-run: only the
    likes that appeared since the last run are added, so nothing is duplicated
    and nothing already saved is removed.

    ``on_status`` fires before each network call and ``on_track`` once per
    settled track (flagged ``True`` when it was added), so the caller can drive a
    progress bar without owning any of this logic.
    """
    name = playlist_name(year)

    if existing_playlist is None:
        on_status(f"creating playlist {name}")
        playlist_id = library.create_playlist(
            name, description=playlist_description(year)
        )
        already_present: set[str] = set()
        created = True
    else:
        on_status(f"reusing playlist {name}")
        playlist_id = str(existing_playlist["id"])
        already_present = library.playlist_track_uris(playlist_id)
        created = False

    pending = select_new_tracks(tracks, already_present)
    added_uris = {track.uri for track in pending}

    for batch in chunked(pending, ADD_BATCH_SIZE):
        extra = len(batch) - 1
        suffix = f" and {extra} more" if extra else ""
        on_status(f'adding "{batch[0].name}"{suffix} to playlist {name}')
        library.add_tracks(playlist_id, [track.uri for track in batch])
        for track in batch:
            on_track(track, True)

    skipped = 0
    for track in tracks:
        if track.uri not in added_uris:
            skipped += 1
            on_track(track, False)

    return YearResult(
        year=year,
        playlist_id=playlist_id,
        created=created,
        added=len(pending),
        skipped=skipped,
    )
