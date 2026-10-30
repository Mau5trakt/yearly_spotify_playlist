"""One-time authorization helper.

Run ``python -m yearly_spotify_playlist.auth`` once to turn your Spotify app
credentials into the ``SPOTIFY_REFRESH_TOKEN`` that the main CLI consumes.

This command starts an ephemeral loopback HTTP listener on the configured
redirect URI (default ``http://127.0.0.1:8888/callback``) to automatically capture
the authorization code from Spotify upon redirection, eliminating manual copy-pasting.
If the port is unavailable or times out, it gracefully falls back to prompt for manual URL paste.

This is deliberately a separate command: the main CLI takes no arguments and
never opens a browser, so the interactive login happens exactly once, here.
"""

from __future__ import annotations

import html
import http.server
import ipaddress
import os
import sys
import threading
import urllib.parse
import webbrowser
from dataclasses import replace
from pathlib import Path
from typing import Any, Self

from dotenv import load_dotenv
from spotipy import SpotifyException, SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOauthError

from .config import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_TOKEN_CACHE_PATH,
    SCOPES,
    ConfigError,
    Settings,
    save_token_cache,
)


def _require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise SystemExit(
            f"Missing {name}. Copy .env.example to .env and fill in "
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET before authorizing."
        )
    return value


def parse_redirect_uri(redirect_uri: str) -> tuple[str, int, str] | None:
    """Parse loopback host, port, and path from a redirect URI.

    Returns ``(host, port, path)`` if the URI points to a valid loopback address,
    or ``None`` if it is invalid or not on loopback.
    """
    try:
        parts = urllib.parse.urlsplit(redirect_uri)
    except ValueError:
        return None

    if not parts.scheme or parts.scheme.lower() not in ("http", "https"):
        return None

    host = parts.hostname
    if not host:
        return None

    is_loopback = False
    if host.lower() == "localhost":
        is_loopback = True
    else:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False

    if not is_loopback:
        return None

    port = (
        parts.port
        if parts.port is not None
        else (443 if parts.scheme.lower() == "https" else 80)
    )
    path = parts.path or "/"
    return host, port, path


SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Authorization Successful</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #121212; color: #FFFFFF; }
    .card { text-align: center; background-color: #181818; padding: 40px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); max-width: 400px; }
    h1 { color: #1ED760; margin-bottom: 16px; font-size: 24px; }
    p { color: #B3B3B3; font-size: 16px; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>✓ Authorization Successful</h1>
    <p>You can close this tab and return to your terminal.</p>
  </div>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Authorization Failed</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #121212; color: #FFFFFF; }
    .card { text-align: center; background-color: #181818; padding: 40px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); max-width: 400px; }
    h1 { color: #E22134; margin-bottom: 16px; font-size: 24px; }
    p { color: #B3B3B3; font-size: 16px; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>✗ Authorization Failed</h1>
    <p>Spotify returned an error: <strong>{error}</strong>.</p>
    <p>You can close this tab and try again.</p>
  </div>
</body>
</html>"""


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server: OAuthCallbackServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        parts = urllib.parse.urlsplit(self.path)
        if parts.path != self.server.expected_path:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        query = urllib.parse.parse_qs(parts.query)
        codes = query.get("code")
        errors = query.get("error")

        if codes and codes[0]:
            code = codes[0]
            self.server.result = {"code": code, "error": None}
            body = SUCCESS_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.server.done_event.set()
        elif errors and errors[0]:
            error = errors[0]
            self.server.result = {"code": None, "error": error}
            escaped_error = html.escape(error)
            body = ERROR_HTML.replace("{error}", escaped_error).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.server.done_event.set()
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Missing code or error parameter.")


class OAuthCallbackServer(http.server.HTTPServer):
    """Ephemeral HTTP server to capture OAuth callback requests on loopback."""

    allow_reuse_address = True

    def __init__(
        self,
        host: str,
        port: int,
        expected_path: str = "/callback",
    ) -> None:
        super().__init__((host, port), _CallbackHandler)
        self.expected_path = expected_path
        self.done_event = threading.Event()
        self.result: dict[str, str | None] | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start listening in a background daemon thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self.serve_forever,
            name="OAuthCallbackServer",
            daemon=True,
        )
        self._thread.start()

    def wait_for_callback(self, timeout: float = 60.0) -> dict[str, str | None] | None:
        """Wait up to `timeout` seconds for a callback request to be handled."""
        self.done_event.wait(timeout=timeout)
        return self.result

    def shutdown_and_close(self) -> None:
        """Cleanly shutdown the server and release the bound socket."""
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.shutdown_and_close()


def get_auth_code(
    auth: SpotifyOAuth,
    redirect_uri: str,
    *,
    timeout: float = 60.0,
    open_browser: bool = True,
) -> str:
    """Acquire the Spotify authorization code, attempting loopback capture first."""
    parsed = parse_redirect_uri(redirect_uri)
    server: OAuthCallbackServer | None = None

    if parsed is not None:
        host, port, path = parsed
        try:
            server = OAuthCallbackServer(host, port, expected_path=path)
            server.start()
        except OSError as exc:
            print(
                f"Port {port} is unavailable ({exc}); falling back to manual paste.",
                file=sys.stderr,
            )
            server = None

    url = auth.get_authorize_url()
    print("1. Open this URL in the browser and accept the permissions:")
    print(f"   {url}\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001, S110 - opening a browser is a convenience only
            pass

    if server is not None:
        print(
            f"Waiting up to {int(timeout)}s for Spotify callback on {redirect_uri}..."
        )
        print("Accept the authorization prompt in your browser.\n")
        result = server.wait_for_callback(timeout=timeout)
        server.shutdown_and_close()

        if result is not None:
            if result.get("error"):
                raise SpotifyOauthError(f"Authorization denied: {result['error']}")
            if result.get("code"):
                print("Authorization code received successfully!")
                return result["code"]
        print("Timed out waiting for automatic callback.")

    print(f"2. You will end up on a page like {redirect_uri} that may fail.")
    print("   That is expected: copy the full URL from the address bar.\n")
    pasted = input("URL after authorizing: ")
    return _extract_code(auth, pasted)


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


def authorize_and_get_refresh_token(
    client_id: str,
    client_secret: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    *,
    timeout: float = 60.0,
    open_browser: bool = True,
) -> str:
    """Run the OAuth loopback flow to obtain and return a Spotify refresh token."""
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=" ".join(SCOPES),
        cache_handler=MemoryCacheHandler(),
        open_browser=False,
    )
    code = get_auth_code(auth, redirect_uri, timeout=timeout, open_browser=open_browser)
    auth.get_access_token(code, as_dict=False)
    token_info = auth.cache_handler.get_cached_token() or {}
    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        raise SpotifyOauthError("Spotify did not return a refresh token.")
    return refresh_token


def main(token_cache_path: Path | str = DEFAULT_TOKEN_CACHE_PATH) -> int:
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

    try:
        code = get_auth_code(auth, redirect_uri)
    except EOFError, KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 1
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

    save_token_cache(refresh_token, path=token_cache_path)

    granted = token_info.get("scope", "")
    print(f"\nDone. Saved refresh token to {token_cache_path}")
    print(
        f"Optionally, you can also add this to your .env:\n\nSPOTIFY_REFRESH_TOKEN={refresh_token}"
    )
    if granted and set(granted.split()) != set(SCOPES):
        print(
            f'\nHeads up: the granted scopes were "{granted}" and do not match the '
            "requested ones. Authorize again from scratch so the CLI works.",
            file=sys.stderr,
        )
    print("\nNow you can run: uv run yearly-spotify-playlist")
    return 0


def is_interactive() -> bool:
    """Return True if both stdin and stdout are attached to an interactive terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def is_auth_failure(exc: Exception) -> bool:
    """Check if an exception indicates that the Spotify refresh token is expired or invalid."""
    if isinstance(exc, SpotifyOauthError):
        return True
    return bool(isinstance(exc, SpotifyException) and exc.http_status in (401, 403))


def ensure_authenticated(
    settings: Settings,
    *,
    interactive: bool | None = None,
    token_cache_path: Path | str = DEFAULT_TOKEN_CACHE_PATH,
) -> Settings:
    """Ensure settings contains a refresh_token, prompting for loopback auth if missing."""
    if settings.refresh_token:
        return settings

    if interactive is None:
        interactive = is_interactive()

    if not interactive:
        raise ConfigError(
            "missing SPOTIFY_REFRESH_TOKEN. Copy .env.example to .env and fill in "
            "SPOTIFY_REFRESH_TOKEN, or run 'python -m yearly_spotify_playlist.auth' interactively."
        )

    print("\nNo Spotify refresh token found. Starting loopback authentication...")
    token = authorize_and_get_refresh_token(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
    )
    save_token_cache(token, path=token_cache_path)
    return replace(settings, refresh_token=token)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
