from __future__ import annotations

import pytest

from yearly_spotify_playlist.liked_tracks import (
    group_by_year,
    liked_year,
    parse_saved_track,
)


@pytest.mark.parametrize(
    ("added_at", "expected"),
    [
        ("2023-04-17T09:31:05Z", 2023),
        ("2024-01-01T00:00:00Z", 2024),
        ("2019-12-31T23:59:59Z", 2019),
        ("2007", 2007),
        ("not-a-date", None),
        ("", None),
        (None, None),
        (1234, None),
        ("0000-01-01T00:00:00Z", None),
    ],
)
def test_liked_year(added_at, expected):
    assert liked_year(added_at) == expected


def _item(name: str, uri: str, added_at: str, **track_extra) -> dict:
    track = {
        "name": name,
        "uri": uri,
        "artists": [{"name": "Some Artist"}],
        **track_extra,
    }
    return {"added_at": added_at, "track": track}


def test_parse_saved_track_reads_name_artist_and_year():
    track = parse_saved_track(
        _item("Bohemian Rhapsody", "spotify:track:a", "2023-04-17T09:31:05Z")
    )
    assert track is not None
    assert track.name == "Bohemian Rhapsody"
    assert track.artist == "Some Artist"
    assert track.liked_year == 2023
    assert track.uri == "spotify:track:a"


def test_parse_saved_track_rejects_unusable_entries():
    assert (
        parse_saved_track({"added_at": None, "track": {"name": "x", "uri": "u"}})
        is None
    )
    assert (
        parse_saved_track({"added_at": "2023-01-01T00:00:00Z", "track": None}) is None
    )
    assert parse_saved_track({"added_at": "2023-01-01T00:00:00Z"}) is None
    assert (
        parse_saved_track({"added_at": "2023-01-01T00:00:00Z", "track": {"name": "x"}})
        is None
    )
    assert (
        parse_saved_track(
            _item(
                "local", "spotify:local:a:b:c:d", "2023-01-01T00:00:00Z", is_local=True
            )
        )
        is None
    )


def test_parse_saved_track_tolerates_missing_artists():
    item = {"added_at": "2020-02-02T00:00:00Z", "track": {"name": "n", "uri": "u"}}
    track = parse_saved_track(item)
    assert track is not None
    assert track.artist == ""


def test_group_by_year_sorts_years_desc_and_keeps_input_order():
    items = [
        _item("a", "spotify:track:a", "2023-01-02T00:00:00Z"),
        _item("b", "spotify:track:b", "2023-01-01T00:00:00Z"),
        _item("c", "spotify:track:c", "2024-05-05T00:00:00Z"),
    ]
    grouped = group_by_year(items)

    assert list(grouped) == [2024, 2023]
    assert [t.name for t in grouped[2023]] == ["a", "b"]


def test_group_by_year_drops_duplicates():
    items = [
        _item("a", "spotify:track:a", "2023-01-02T00:00:00Z"),
        _item("a", "spotify:track:a", "2023-01-02T00:00:00Z"),
    ]
    assert len(group_by_year(items)[2023]) == 1


def test_group_by_year_skips_unusable_entries():
    items = [
        {"added_at": None, "track": {"name": "x", "uri": "u"}},
        _item("a", "spotify:track:a", "2023-01-02T00:00:00Z"),
    ]
    assert [t.name for t in group_by_year(items)[2023]] == ["a"]
