from __future__ import annotations

from yearly_spotify_playlist.liked_tracks import LikedTrack
from yearly_spotify_playlist.runner import _bar_callbacks


class FakeBar:
    """Stands in for the tqdm bar the callbacks write their message to."""

    def __init__(self) -> None:
        self.postfix: list[str] = []
        self.updates = 0

    def set_postfix_str(self, message: str, *, refresh: bool = False) -> None:
        self.postfix.append(message)

    def update(self, n: int = 1) -> None:
        self.updates += n


def _track(name: str) -> LikedTrack:
    return LikedTrack(
        uri=f"spotify:track:{name}", name=name, artist="A", liked_year=2023
    )


def test_track_callbacks_keep_the_year_and_bar_they_were_built_for():
    first_bar, second_bar = FakeBar(), FakeBar()
    _, first_on_track = _bar_callbacks(first_bar, "2023")
    _, second_on_track = _bar_callbacks(second_bar, "2024")

    # Both are invoked only after the second playlist already has its callbacks.
    first_on_track(_track("A"), True)
    second_on_track(_track("B"), False)

    assert first_bar.postfix == ['added "A" to playlist 2023']
    assert second_bar.postfix == ['"B" was already in playlist 2024']
    assert (first_bar.updates, second_bar.updates) == (1, 1)


def test_status_callbacks_write_to_their_own_bar():
    first_bar, second_bar = FakeBar(), FakeBar()
    first_on_status, _ = _bar_callbacks(first_bar, "2023")
    second_on_status, _ = _bar_callbacks(second_bar, "2024")

    first_on_status("creating playlist 2023")
    second_on_status("reusing playlist 2024")

    assert first_bar.postfix == ["creating playlist 2023"]
    assert second_bar.postfix == ["reusing playlist 2024"]
