from __future__ import annotations

import socket
import threading
import time

import pytest

from yearly_spotify_playlist.auth import (
    OAuthCallbackServer,
    _extract_code,
    _require,
    get_auth_code,
    main,
    parse_redirect_uri,
)
from yearly_spotify_playlist.config import DEFAULT_REDIRECT_URI


def test_parse_default_redirect_uri() -> None:
    result = parse_redirect_uri(DEFAULT_REDIRECT_URI)
    assert result is not None
    host, port, path = result
    assert host == "127.0.0.1"
    assert port == 8888
    assert path == "/callback"


@pytest.mark.parametrize(
    ("uri", "expected_host", "expected_port", "expected_path"),
    [
        ("http://127.0.0.1:8888/callback", "127.0.0.1", 8888, "/callback"),
        ("http://127.0.0.2:9999/auth", "127.0.0.2", 9999, "/auth"),
        ("http://localhost:8080/cb", "localhost", 8080, "/cb"),
        ("http://127.0.0.1/callback", "127.0.0.1", 80, "/callback"),
        ("http://127.0.0.1:8888", "127.0.0.1", 8888, "/"),
        ("http://[::1]:8888/callback", "::1", 8888, "/callback"),
    ],
)
def test_parse_valid_loopback_uris(
    uri: str, expected_host: str, expected_port: int, expected_path: str
) -> None:
    result = parse_redirect_uri(uri)
    assert result == (expected_host, expected_port, expected_path)


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/callback",
        "http://192.168.1.50:8888/callback",
        "http://google.com:8888/callback",
        "invalid-uri",
        "",
        "://bad",
    ],
)
def test_parse_non_loopback_or_invalid_uris(uri: str) -> None:
    assert parse_redirect_uri(uri) is None


def test_callback_server_captures_code_and_returns_200() -> None:
    import urllib.error
    import urllib.request

    with OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback") as server:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/callback?code=mock_auth_code_xyz"

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            content_type = resp.headers.get("Content-Type", "")

        assert status == 200
        assert "text/html" in content_type
        assert "Authorization Successful" in body or "close this tab" in body

        result = server.wait_for_callback(timeout=2.0)
        assert result is not None
        assert result.get("code") == "mock_auth_code_xyz"
        assert result.get("error") is None


def test_callback_server_captures_error_and_returns_400() -> None:
    import urllib.error
    import urllib.request

    with OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback") as server:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/callback?error=access_denied"

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url)

        assert exc_info.value.code == 400
        body = exc_info.value.read().decode("utf-8")
        assert "access_denied" in body

        result = server.wait_for_callback(timeout=2.0)
        assert result is not None
        assert result.get("code") is None
        assert result.get("error") == "access_denied"


def test_callback_server_missing_params_returns_400() -> None:
    import urllib.error
    import urllib.request

    with OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback") as server:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/callback"

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url)

        assert exc_info.value.code == 400
        body = exc_info.value.read().decode("utf-8")
        assert "Missing code or error parameter." in body


def test_callback_server_start_idempotent() -> None:
    server = OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback")
    with server:
        first_thread = server._thread
        server.start()
        assert server._thread is first_thread


def test_get_auth_code_opens_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    from spotipy import SpotifyOAuth

    opened_urls: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened_urls.append(url))
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: (
            "http://127.0.0.1:8888/callback?code=mock_code_12345678901234567890"
        ),
    )

    auth = SpotifyOAuth(
        client_id="dummy_id",
        client_secret="dummy_secret",
        redirect_uri="http://127.0.0.1:0/callback",
        open_browser=False,
    )

    code = get_auth_code(
        auth, "http://127.0.0.1:0/callback", timeout=0.01, open_browser=True
    )
    assert code == "mock_code_12345678901234567890"
    assert len(opened_urls) == 1

    import urllib.error
    import urllib.request

    with OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback") as server:
        port = server.server_address[1]

        # 1. Request favicon (should return 404 and not finish the callback wait)
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/favicon.ico")
        assert exc_info.value.code == 404

        # Callback must still be pending
        assert server.wait_for_callback(timeout=0.1) is None

        # 2. Now request real callback
        urllib.request.urlopen(f"http://127.0.0.1:{port}/callback?code=actual_code")
        result = server.wait_for_callback(timeout=2.0)
        assert result is not None
        assert result.get("code") == "actual_code"


def test_callback_server_timeout_returns_none() -> None:
    server = OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback")
    with server:
        start = time.monotonic()
        result = server.wait_for_callback(timeout=0.15)
        elapsed = time.monotonic() - start

        assert result is None
        assert elapsed >= 0.1


def test_callback_server_shutdown_releases_socket_and_terminates_thread() -> None:
    server = OAuthCallbackServer("127.0.0.1", 0, expected_path="/callback")
    server.start()
    port = server.server_address[1]
    thread = server._thread
    assert thread is not None
    assert thread.is_alive()

    server.shutdown_and_close()

    assert not thread.is_alive()
    assert server._thread is None

    # Verify that the socket was released and can be rebound immediately
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_get_auth_code_port_collision_falls_back_to_manual_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 1. Bind a dummy socket to a port to simulate port collision
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        busy_port = blocker.getsockname()[1]
        redirect_uri = f"http://127.0.0.1:{busy_port}/callback"

        # Mock input() to simulate user pasting the URL manually
        monkeypatch.setattr(
            "builtins.input",
            lambda prompt: (
                f"http://127.0.0.1:{busy_port}/callback?code=manual_code_12345678901234567890"
            ),
        )

        from spotipy import SpotifyOAuth

        auth = SpotifyOAuth(
            client_id="dummy_id",
            client_secret="dummy_secret",
            redirect_uri=redirect_uri,
            open_browser=False,
        )

        code = get_auth_code(auth, redirect_uri, open_browser=False)
        assert code == "manual_code_12345678901234567890"

        captured = capsys.readouterr()
        assert f"Port {busy_port} is unavailable" in captured.err


def test_get_auth_code_timeout_falls_back_to_manual_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    redirect_uri = "http://127.0.0.1:0/callback"
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: (
            "http://127.0.0.1:8888/callback?code=timeout_fallback_code_1234567890"
        ),
    )

    from spotipy import SpotifyOAuth

    auth = SpotifyOAuth(
        client_id="dummy_id",
        client_secret="dummy_secret",
        redirect_uri=redirect_uri,
        open_browser=False,
    )

    code = get_auth_code(auth, redirect_uri, timeout=0.1, open_browser=False)
    assert code == "timeout_fallback_code_1234567890"

    captured = capsys.readouterr()
    assert "Timed out waiting for automatic callback." in captured.out


def test_get_auth_code_successful_loopback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import urllib.request

    # Start loopback on OS assigned port
    from spotipy import SpotifyOAuth

    auth = SpotifyOAuth(
        client_id="dummy_id",
        client_secret="dummy_secret",
        redirect_uri="http://127.0.0.1:0/callback",
        open_browser=False,
    )

    # In a separate thread simulate browser redirect
    def simulate_browser(server_holder: list[OAuthCallbackServer]) -> None:
        for _ in range(50):
            if server_holder:
                break
            time.sleep(0.02)
        server = server_holder[0]
        port = server.server_address[1]
        urllib.request.urlopen(
            f"http://127.0.0.1:{port}/callback?code=auto_captured_code_1234567890"
        )

    server_holder: list[OAuthCallbackServer] = []
    real_init = OAuthCallbackServer.__init__

    def intercept_init(
        self: OAuthCallbackServer,
        host: str,
        port: int,
        expected_path: str = "/callback",
    ) -> None:
        real_init(self, host, 0, expected_path)
        server_holder.append(self)

    monkeypatch.setattr(OAuthCallbackServer, "__init__", intercept_init)

    sim_thread = threading.Thread(target=simulate_browser, args=(server_holder,))
    sim_thread.start()

    code = get_auth_code(
        auth, "http://127.0.0.1:8888/callback", timeout=3.0, open_browser=False
    )
    sim_thread.join()

    assert code == "auto_captured_code_1234567890"
    captured = capsys.readouterr()
    assert "Authorization code received successfully!" in captured.out


def test_get_auth_code_callback_error_raises_spotipy_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request

    from spotipy import SpotifyOAuth
    from spotipy.oauth2 import SpotifyOauthError

    auth = SpotifyOAuth(
        client_id="dummy_id",
        client_secret="dummy_secret",
        redirect_uri="http://127.0.0.1:0/callback",
        open_browser=False,
    )

    server_holder: list[OAuthCallbackServer] = []
    real_init = OAuthCallbackServer.__init__

    def intercept_init(
        self: OAuthCallbackServer,
        host: str,
        port: int,
        expected_path: str = "/callback",
    ) -> None:
        real_init(self, host, 0, expected_path)
        server_holder.append(self)

    monkeypatch.setattr(OAuthCallbackServer, "__init__", intercept_init)

    def simulate_error() -> None:
        for _ in range(50):
            if server_holder:
                break
            time.sleep(0.02)
        server = server_holder[0]
        port = server.server_address[1]
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/callback?error=user_cancelled"
            )
        except urllib.error.HTTPError:
            pass

    sim_thread = threading.Thread(target=simulate_error)
    sim_thread.start()

    with pytest.raises(SpotifyOauthError, match="Authorization denied: user_cancelled"):
        get_auth_code(
            auth, "http://127.0.0.1:8888/callback", timeout=3.0, open_browser=False
        )
    sim_thread.join()


def test_require_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_VAR", "hello")
    assert _require("TEST_VAR") == "hello"

    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(SystemExit, match="Missing MISSING_VAR"):
        _require("MISSING_VAR")


def test_extract_code() -> None:
    from spotipy import SpotifyOAuth

    auth = SpotifyOAuth(
        client_id="id",
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        open_browser=False,
    )

    valid_code = "AQD_valid_code_from_spotify_12345"
    assert (
        _extract_code(auth, f"http://127.0.0.1:8888/callback?code={valid_code}")
        == valid_code
    )
    assert _extract_code(auth, valid_code) == valid_code
    assert _extract_code(auth, f'  "{valid_code}"  ') == valid_code

    with pytest.raises(
        SystemExit, match="That does not look like an authorization code"
    ):
        _extract_code(auth, "short")

    with pytest.raises(
        SystemExit, match="That does not look like an authorization code"
    ):
        _extract_code(auth, "code with spaces 1234567890")


def test_main_missing_client_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "yearly_spotify_playlist.auth.load_dotenv", lambda *args, **kwargs: None
    )
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    with pytest.raises(SystemExit, match="Missing SPOTIFY_CLIENT_ID"):
        main()


def test_main_successful_flow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    from yearly_spotify_playlist.config import SCOPES

    # Mock get_auth_code
    monkeypatch.setattr(
        "yearly_spotify_playlist.auth.get_auth_code",
        lambda auth, redirect_uri: "mock_auth_code_123456789012345",
    )

    # Mock SpotifyOAuth methods
    from spotipy import SpotifyOAuth

    def mock_get_access_token(
        self: SpotifyOAuth, code: str, as_dict: bool = False
    ) -> None:
        self.cache_handler.save_token_to_cache(
            {
                "refresh_token": "mock_refresh_token_xyz",
                "scope": " ".join(SCOPES),
            }
        )

    monkeypatch.setattr(SpotifyOAuth, "get_access_token", mock_get_access_token)

    exit_code = main()
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "SPOTIFY_REFRESH_TOKEN=mock_refresh_token_xyz" in captured.out
    assert "Now you can run: uv run yearly-spotify-playlist" in captured.out


def test_main_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_client_secret")

    def mock_cancel(*args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr("yearly_spotify_playlist.auth.get_auth_code", mock_cancel)

    exit_code = main()
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Cancelled." in captured.err


def test_main_oauth_error_on_auth_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_client_secret")

    from spotipy.oauth2 import SpotifyOauthError

    def mock_error(*args: object, **kwargs: object) -> str:
        raise SpotifyOauthError("Access was denied")

    monkeypatch.setattr("yearly_spotify_playlist.auth.get_auth_code", mock_error)

    exit_code = main()
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Spotify rejected the authorization: Access was denied" in captured.err


def test_main_token_exchange_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_client_secret")

    from spotipy import SpotifyOAuth
    from spotipy.oauth2 import SpotifyOauthError

    monkeypatch.setattr(
        "yearly_spotify_playlist.auth.get_auth_code",
        lambda auth, redirect_uri: "mock_auth_code_123456789012345",
    )

    def mock_failed_token(self: SpotifyOAuth, code: str, as_dict: bool = False) -> None:
        raise SpotifyOauthError("invalid_grant")

    monkeypatch.setattr(SpotifyOAuth, "get_access_token", mock_failed_token)

    exit_code = main()
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Could not exchange the code: invalid_grant" in captured.err


def test_main_no_refresh_token_returned(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_client_secret")

    from spotipy import SpotifyOAuth

    monkeypatch.setattr(
        "yearly_spotify_playlist.auth.get_auth_code",
        lambda auth, redirect_uri: "mock_auth_code_123456789012345",
    )

    def mock_empty_token(self: SpotifyOAuth, code: str, as_dict: bool = False) -> None:
        self.cache_handler.save_token_to_cache({})

    monkeypatch.setattr(SpotifyOAuth, "get_access_token", mock_empty_token)

    exit_code = main()
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Spotify did not return a refresh token" in captured.err


def test_main_scopes_mismatch_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_client_secret")

    from spotipy import SpotifyOAuth

    monkeypatch.setattr(
        "yearly_spotify_playlist.auth.get_auth_code",
        lambda auth, redirect_uri: "mock_auth_code_123456789012345",
    )

    def mock_partial_scope_token(
        self: SpotifyOAuth, code: str, as_dict: bool = False
    ) -> None:
        self.cache_handler.save_token_to_cache(
            {
                "refresh_token": "mock_refresh_token_xyz",
                "scope": "user-library-read",
            }
        )

    monkeypatch.setattr(SpotifyOAuth, "get_access_token", mock_partial_scope_token)

    exit_code = main()
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Heads up: the granted scopes were" in captured.err
