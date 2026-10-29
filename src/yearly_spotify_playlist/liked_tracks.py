"""Turn ``GET /me/tracks`` pages into tracks grouped by the year they were liked."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LikedTrack:
    """A single saved song, reduced to what the playlists need."""

    uri: str
    name: str
    artist: str
    liked_year: int
    added_at: str | None = None


def liked_year(added_at: str | None) -> int | None:
    """Extract the calendar year from a Spotify ``added_at`` timestamp.

    Spotify returns ISO 8601 UTC (``2023-04-17T09:31:05Z``), so the year is
    always the first four characters. Returns ``None`` for anything unusable.
    """
    if not isinstance(added_at, str):
        return None
    head = added_at.strip()
    if len(head) < 4 or not head[:4].isdigit():
        return None
    year = int(head[:4])
    return year if year > 0 else None


def parse_saved_track(item: Mapping[str, Any]) -> LikedTrack | None:
    """Normalise one ``SavedTrackObject`` entry.

    Returns ``None`` when the entry cannot be placed in a playlist: missing or
    unparseable ``added_at``, a missing track object, a track without a URI, or
    a local file track (which has no playlist-addressable URI).
    """
    track = item.get("track")
    if not isinstance(track, Mapping):
        return None

    raw_added_at = item.get("added_at")
    year = liked_year(raw_added_at)
    if year is None:
        return None

    uri = track.get("uri")
    name = track.get("name")
    if not isinstance(uri, str) or not uri:
        return None
    if not isinstance(name, str):
        return None
    if track.get("is_local"):
        return None

    return LikedTrack(
        uri=uri,
        name=name,
        artist=_first_artist(track),
        liked_year=year,
        added_at=raw_added_at.strip() if isinstance(raw_added_at, str) else None,
    )


def group_by_year(items: Iterable[Mapping[str, Any]]) -> dict[int, list[LikedTrack]]:
    """Group saved tracks into ``{year: tracks}``, newest year first.

    Order is preserved inside each year, so each playlist ends up sorted from
    most recently liked to least. Repeat URIs are dropped: a song can only be
    saved once, and a duplicate would be rejected by the playlist endpoint.
    """
    grouped: dict[int, list[LikedTrack]] = {}
    seen: set[str] = set()

    for item in items:
        track = parse_saved_track(item)
        if track is None or track.uri in seen:
            continue
        seen.add(track.uri)
        grouped.setdefault(track.liked_year, []).append(track)

    return dict(sorted(grouped.items(), reverse=True))


def _first_artist(track: Mapping[str, Any]) -> str:
    artists = track.get("artists")
    if not isinstance(artists, list):
        return ""
    for artist in artists:
        if isinstance(artist, Mapping) and isinstance(artist.get("name"), str):
            return artist["name"]
    return ""
