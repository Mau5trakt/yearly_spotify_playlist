"""One-time authorization helper.

Run ``python -m yearly_spotify_playlist.auth`` once to turn your Spotify app
credentials into the ``SPOTIFY_REFRESH_TOKEN`` that the main CLI consumes.

This is deliberately a separate command: the main CLI takes no arguments and
never opens a browser, so the interactive login happens exactly once, here.
"""

from __future__ import annotations

import os
import sys
import webbrowser

from dotenv import load_dotenv
from spotipy import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOauthError

from .config import DEFAULT_REDIRECT_URI, SCOPES


def _require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise SystemExit(
            f"Missing {name}. Copy .env.example to .env and fill in "
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET before authorizing."
        )
    return value


def _extract_code(auth: SpotifyOAuth, pasted: str) -> str:
    """Accept either the full redirect URL or just the code."""
    pasted = pasted.strip().strip('"').strip("'")
    code = auth.parse_response_code(pasted)
    # parse_response_code returns the input untouched when it cannot find a code,
    # so reject anything that still looks like a URL or is too short to be one.
    if "://" in code or len(code) < 20 or any(c.isspace() for c in code):
        raise SystemExit(
            "That does not look like an authorization code. Copy the full URL that "
            "Spotify redirected you to, or the value of the 'code' parameter."
        )
    return code


def main() -> int:
    """Walk the user through the authorization code flow and print the token."""
    load_dotenv()

    client_id = _require("SPOTIFY_CLIENT_ID")
    client_secret = _require("SPOTIFY_CLIENT_SECRET")
    redirect_uri = (os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI).strip()

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=" ".join(SCOPES),
        cache_handler=MemoryCacheHandler(),
        open_browser=False,
    )

    print("Scopes that will be requested:")
    for scope in SCOPES:
        print(f"  - {scope}")
    print()

    url = auth.get_authorize_url()
    print("1. Open this URL in the browser and accept the permissions:")
    print(f"   {url}\n")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - opening a browser is a convenience only
        pass

    print(f"2. You will end up on a page like {redirect_uri} that may fail.")
    print("   That is expected: copy the full URL from the address bar.\n")
    try:
        pasted = input("URL after authorizing: ")
    except EOFError:
        print("\nCancelled.", file=sys.stderr)
        return 1

    try:
        code = _extract_code(auth, pasted)
    except SpotifyOauthError as exc:
        print(f"\nSpotify rejected the authorization: {exc}", file=sys.stderr)
        return 1

    print("\n3. Exchanging the code for a refresh token...")
    try:
        auth.get_access_token(code, as_dict=False)
    except SpotifyOauthError as exc:
        print(f"\nCould not exchange the code: {exc}", file=sys.stderr)
        return 1

    token_info = auth.cache_handler.get_cached_token() or {}
    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        print(
            "\nSpotify did not return a refresh token. Start the flow over.",
            file=sys.stderr,
        )
        return 1

    granted = token_info.get("scope", "")
    print("\nDone. Add this to your .env:\n")
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    if granted and set(granted.split()) != set(SCOPES):
        print(
            f'\nHeads up: the granted scopes were "{granted}" and do not match the '
            "requested ones. Authorize again from scratch so the CLI works.",
            file=sys.stderr,
        )
    print("\nNow you can run: uv run yearly-spotify-playlist")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
