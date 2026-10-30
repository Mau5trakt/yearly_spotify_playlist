# yearly-spotify-playlist

[![Python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-0.12.5-261230?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![spotipy](https://img.shields.io/pypi/v/spotipy?label=spotipy&logo=spotify&logoColor=1ED760)](https://pypi.org/project/spotipy/)

[![Built with Gentle-AI](https://raw.githubusercontent.com/Gentleman-Programming/gentle-ai/main/docs/assets/brand/built-with-gentle-ai.png)](https://github.com/Gentleman-Programming/gentle-ai)

A single-purpose CLI: it walks through every song you liked on Spotify and creates
**one playlist per year**, named after the year.

The rule is simple: the `2023` playlist contains exactly the songs you saved during
2023. Not one more, not one less.

Configuration comes from environment variables, with optional CLI flags for
previewing (`--dry-run`) and help (`--help`).

```
Connected as Enrique (enriqueal)

⢹ Reading your liked songs ━━━━━━━━━━━━━━━━━━━━━━━━ 2338/2338 100%
2.3k liked songs spread across 6 years: 2026, 2025, 2024, 2023, 2019, 2014

⢹ Yearly playlists  ━━━━━━━━━━━━━━━━━━━━━━━━ 6/6 100% 2026
  2026: playlist reused | 8 added | 602 already there
  ...
Done: 6 yearly playlists, 8 songs added.

                         Songs per year                         
 2014 ██▊                                                    41 
                                                                
 2019 ███████████▌                                          171 
                                                                
 2023 ██████████████████████████████████████████████████ 👑 741 
                                                                
 2024 ████████████████████████████████▍                     480 
                                                                
 2025 ███████████████████▉                                  295 
                                                                
 2026 █████████████████████████████████████████▏            610 

You have liked 2338 songs in Spotify.
Your first saved song was "Nuclear (Album Version) - Original Mix" by Zomboy on 2014-12-27T00:02:46Z.
```

---

## Table of Contents

- [What It Does Exactly](#what-it-does-exactly)
- [Requirements](#requirements)
- [Installation](#installation)
  - [1. Create the App in Spotify](#1-create-the-app-in-spotify)
  - [2. Install Dependencies](#2-install-dependencies)
  - [3. Get the Refresh Token](#3-get-the-refresh-token)
  - [4. Configure the `.env`](#4-configure-the-env)
- [Usage](#usage)
- [Statistics and Visual Highlights](#statistics-and-visual-highlights)
- [Environment Variables](#environment-variables)
- [How It Works Internally](#how-it-works-internally)
- [Re-runs: It Is Idempotent](#re-runs-it-is-idempotent)
- [Manual Playlist Deletions and Re-sync Order](#manual-playlist-deletions-and-re-sync-order)
- [Project Structure](#project-structure)
- [Tests](#tests)
- [Notes on the Spotify API in 2026](#notes-on-the-spotify-api-in-2026)
- [Rate Limits](#rate-limits)
- [Troubleshooting](#troubleshooting)
- [Security](#security)

---

## What It Does Exactly

1. Reads **all** your liked songs with `GET /me/tracks`, paging until the end.
2. Extracts the year from each record's `added_at` field — that is, **when you liked
   it**, not when the song was released.
3. Groups the tracks by year.
4. For each year: if the `2023` playlist already exists, it is reused; otherwise it is
   created.
5. Adds the missing songs **100 per request** (Spotify's maximum) and skips the ones
   already there.

Songs that are dropped (they break nothing, they simply do not make it in):
- Local tracks (`spotify:local:...`): they cannot be added to playlists.
- Records with an invalid or missing `added_at`.
- Duplicate URIs.

Within each playlist the order is **newest to oldest** (the order Spotify returns your
likes in), not alphabetical and not by release date.

## Requirements

- **Python 3.14+** (uv manages the environment).
- **[uv](https://docs.astral.sh/uv/)**.
- An app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
- A Spotify account (the app owner needs **Premium**, see below).

## Installation

### 1. Create the App in Spotify

Go to <https://developer.spotify.com/dashboard> → **Create app**:

- **App name**: whatever you like, for example `yearly-spotify-playlist`.
- **App description**: briefly describe what you use it for.
- **Redirect URI**: `http://127.0.0.1:8888/callback`

> **Watch out for the redirect URI.** Spotify no longer accepts `localhost`. It only
> allows a literal loopback IP (`http://127.0.0.1:PORT`) or HTTPS. The address must
> match `SPOTIFY_REDIRECT_URI` **exactly**.
>
> The port is flexible: register it without a port and Spotify will accept any
> loopback port.

Open the app and copy the **Client ID** and **Client Secret**.

### 2. Install Dependencies

```bash
uv sync
```

### 3. Configure the `.env`

```bash
cp .env.example .env
```

Fill in `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`.
The `.env` is in `.gitignore`: **never commit it**.

### 4. Authentication (Automatic Loopback or Manual Helper)

The CLI features **automatic interactive authentication**:

1. Run the CLI directly:
   ```bash
   uv run yearly-spotify-playlist
   ```
2. If no token is detected, it automatically starts an ephemeral HTTP listener on `127.0.0.1:8888/callback`, opens your browser, captures Spotify's authorization code, and exchanges it for a refresh token.
3. The token is automatically cached locally in `.spotify_token.json` (gitignored), so you don't even need to copy and paste it into `.env`.
4. If your token ever expires or gets revoked, the CLI automatically prompts for re-authentication and refreshes the cache.

*(Optional)* You can also run the standalone auth helper whenever you want:
```bash
uv run python -m yearly_spotify_playlist.auth
```
And if you run in headless or CI environments, setting `SPOTIFY_REFRESH_TOKEN` in `.env` or system environment variables is still fully supported and takes precedence over the cached file.

## Usage

```bash
uv run yearly-spotify-playlist
```

Preview changes without modifying Spotify:

```bash
uv run yearly-spotify-playlist --dry-run
```

Display horizontal bar chart statistics of liked songs per year without modifying playlists:

```bash
uv run yearly-spotify-playlist --stats
# or
uv run yearly-spotify-playlist -s
```

Force a fresh update from Spotify, ignoring the local 1-hour cache:

```bash
uv run yearly-spotify-playlist -su
# or
uv run yearly-spotify-playlist -s u
# or
uv run yearly-spotify-playlist --stats --update
```

The stats command uses a local 1-hour cache (`stats_cache.json`, base64-encoded and gitignored) to avoid redundant Spotify requests. If the cache is expired, missing, or the `u` / `--update` flag is passed, it fetches fresh liked songs and refreshes the cache.

Show available options and help:

```bash
uv run yearly-spotify-playlist --help
```

It also works as a module:

```bash
uv run python -m yearly_spotify_playlist
```

Exit code: `0` if everything succeeded, `1` if it failed (or `130` if interrupted).

## Statistics and Visual Highlights

The CLI includes an interactive horizontal bar chart powered by Rich, rendered automatically after every live run or on demand via `-s` / `--stats`:

- **One-hour Cache:** Stats are cached locally in `stats_cache.json` (base64-encoded, gitignored) to avoid redundant Spotify requests. Use `-u` / `--update` to bypass the cache.
- **Top Year Spotlight:** When a single year has strictly more liked songs than any other year, its bar is highlighted in gold (`gold1`) and badged with a crown emoji (`👑`). If two or more years tie for the top count, all bars remain in standard green.
- **First Saved Song:** Displays your all-time earliest saved song from your Spotify library, with its title, artist, and exact ISO timestamp.
- **Customizable Spinners:** Loading bars feature Rich animated spinners (configured via `DEFAULT_SPINNER` in `progress.py`, defaulting to `dots9`).

## Environment Variables

| Variable | Required | Default | What it does |
|---|---|---|---|
| `SPOTIFY_CLIENT_ID` | Yes | — | Client ID of your dashboard app. |
| `SPOTIFY_CLIENT_SECRET` | Yes | — | Client Secret of your dashboard app. |
| `SPOTIFY_REFRESH_TOKEN` | No | *(reads from `.spotify_token.json` or auto-authenticates)* | Optional explicit refresh token override. If omitted, the CLI checks `.spotify_token.json` or launches interactive loopback login. |
| `SPOTIFY_REDIRECT_URI` | No | `http://127.0.0.1:8888/callback` | Must match exactly the one registered in the dashboard. Only used during authorization. |
| `SPOTIFY_MARKET` | No | *(empty)* | ISO 3166-1 alpha-2 country code (e.g. `ES`). Filters out content unavailable in your market. If left empty, your account's country is used. |
| `SPOTIFY_YEARS` | No | *(empty)* | Comma-separated list of explicit years to sync (e.g. `2023,2024`). Takes precedence over `SPOTIFY_YEAR_FROM`. |
| `SPOTIFY_YEAR_FROM` | No | *(empty)* | Sync only tracks from this year onward (e.g. `2020`). |
| `BATCH_DELAY_SECONDS` | No | `0.1` | Delay in seconds between track-adding batches for proactive rate limiting. |
| `LOG_LEVEL` | No | `WARNING` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). When set to `DEBUG`, full tracebacks are printed on error. |
Real environment variables take precedence over the `.env`.

> **Playlists are always public.** A Spotify app in Development Mode cannot create
> private playlists: it sends `public: false`, the API echoes `false` back, and the
> playlist is still created public. There is no API workaround, so there is no flag.

### Scopes

The authorization command requests these four:

| Scope | Why |
|---|---|
| `user-library-read` | Read your liked songs (`GET /me/tracks`). |
| `playlist-modify-public` | Create the playlists. |
| `playlist-modify-private` | Modify the private ones you already have. |
| `playlist-read-private` | See your playlists so existing ones can be reused. |

`user-library-modify` is **not** requested: the program only **reads** your library.
It never deletes or unlikes anything.

## How It Works Internally

```
main()                                    src/yearly_spotify_playlist/cli.py
 └─ run(settings)                         runner.py
     ├─ SpotifyLibrary.current_user()            → GET  /me
     ├─ _read_liked_tracks()                     → GET  /me/tracks?offset=N   (paginated)
     │    └─ group_by_year()                     liked_tracks.py
     ├─ owned_playlists_by_name(user_id)         → GET  /me/playlists         (paginated)
     └─ _sync_all_years()                        for each year:
          └─ sync_year()                        yearly_playlists.py
               ├─ create_playlist()              → POST /me/playlists          (if missing)
               ├─ playlist_track_uris()          → GET  /playlists/{id}/items (if it exists)
               └─ add_tracks()                   → POST /playlists/{id}/items (up to 100 URIs)
```

### The Endpoints That Are Used

| Operation | Endpoint | Scopes |
|---|---|---|
| User profile | `GET /me` | — |
| Your liked songs | `GET /me/tracks` | `user-library-read` |
| Your playlists | `GET /me/playlists` | `playlist-read-private` |
| Create playlist | `POST /me/playlists` | `playlist-modify-private` / `-public` |
| Playlist contents | `GET /playlists/{id}/items` | `playlist-read-private` |
| Add songs | `POST /playlists/{id}/items` | `playlist-modify-private` / `-public` |

### The Authentication Flow

The CLI keeps no session and no token file:

1. `SPOTIFY_REFRESH_TOKEN` is injected into a spotipy `MemoryCacheHandler` with
   `expires_at=0` to mark the access token as expired.
2. On the first authenticated call, spotipy exchanges it for an access token via
   `grant_type=refresh_token`.
3. The access token lives in memory and is reused until it expires.

That is why the process **never opens a browser** and uses `open_browser=False`.

### The Progress Bar

There are two phases rendered with Rich, each featuring animated spinners and progress live:

**Phase 1 — reading.** One bar with the total number of liked songs (`total` comes
from the first API response).

**Phase 2 — syncing.** An outer bar with one step per year, and inside it one bar per
year with one step per track. Dynamic status appears to the right of the active task:

```
⢹ Yearly playlists  ━━━━━━━━━━━━━━━━━━╸━━━━━ 3/9 33% 2024
⢹ Playlist 2024     ━━━━━━━━━━━━━╸━━━━━━━━━━ 184/412 45% adding "Bohemian Rhapsody" and 99 more to playlist 2024
```

When a song was already there, the action reads `"X" was already in playlist 2024`.

## Re-runs: It Is Idempotent

You can run the program as many times as you want:

- If the `2023` playlist **already exists** and is yours, it is reused. The program
  reads its contents (`GET /playlists/{id}/items`) and only adds what is missing.
- Newly liked songs are inserted **at the top (position 0)** of the playlist in
  newest-to-oldest order.
- If it already had everything, it makes no write calls at all.
- If it does not exist, it is created.

**It never deletes or removes songs.** If you manually remove a song from the
playlist and run it again, the program adds it back, because it is still among your
likes.

What is **not** idempotent: if you have a playlist of your own named after a year
that was not created by this tool, it will be used. Delete it if you do not want that
to happen.

One more caveat: the playlist description is only written **when the playlist is
created**. Re-running the program against an existing playlist leaves its description
untouched.

## Manual Playlist Deletions and Re-sync Order

Each yearly playlist is maintained in **reverse chronological order**: the most recently liked songs sit at the top of the playlist, and older songs are at the bottom.

When you run the tool again:
1. It compares your Spotify likes against the tracks currently in the playlist.
2. Any song present in your likes but missing from the playlist is considered **new**.
3. All missing tracks are prepended to the **very top (position 0)** of the playlist.

### What happens if you delete an old song from a playlist?

If you manually delete an older song from a playlist directly in Spotify (such as the oldest track at the bottom) but **do not unlike it** in your library:

The next time `yearly-spotify-playlist` runs, it will detect that the song is missing from the playlist. Because the sync process treats any missing track as a new addition that belongs at the head of the playlist, **it will re-insert that song at the very top (first position)** of the playlist.

> **Tip:** If you genuinely want a song excluded from your yearly playlist, remove it from your **Liked Songs** in Spotify. The tool operates on a fast, incremental model rather than reconstructing your full playlist from scratch on every run.

## Project Structure

```
src/yearly_spotify_playlist/
├── __init__.py          facade: re-exports main()
├── __main__.py          python -m yearly_spotify_playlist
├── auth.py              interactive authorization, run once
├── cli.py               CLI entry point, presentation, and exit codes
├── config.py            environment variables → Settings
├── log.py               logging setup with TqdmHandler
├── py.typed             PEP 561 typing marker
├── spotify_api.py       authenticated client + the exact endpoints
├── liked_tracks.py      added_at parsing and year grouping
├── yearly_playlists.py  create/reuse playlist and add in batches
├── stats.py             statistics calculation, base64 cache, and rich horizontal bar chart
├── progress.py          rich progress bars and status reporting
└── runner.py            orchestration of the run

tests/
├── test_cli.py
├── test_config.py
├── test_liked_tracks.py
├── test_observability.py
├── test_runner.py
├── test_spotify_api.py
├── test_stats.py
└── test_yearly_playlists.py
```

Each module has a single responsibility. `spotify_api.py` is the only one that knows
the shape of Spotify's responses; the rest work with clean data.

## Tests

```bash
uv run pytest
```

## Linting and Formatting

[ruff](https://docs.astral.sh/ruff/) does both jobs; it is the only tool
configured, in `[tool.ruff]` under `pyproject.toml`.

```bash
uv run ruff check          # lint
uv run ruff format         # format in place
uv run ruff format --check # fail if anything is unformatted
```

They cover the pure logic: year extraction, discarding invalid entries, grouping,
deduplication, chunking into batches of 100, playlist reuse, and skipped-count
bookkeeping. They do not touch the network — the part that actually talks to Spotify
is verified by running the program.

## Notes on the Spotify API in 2026

This explains code decisions that would otherwise look strange:

| Change | Impact on this project |
|---|---|
| `POST /users/{user_id}/playlists` was **removed** in Feb 2026 for apps in Development Mode. | `POST /me/playlists` (`current_user_playlist_create`) is used instead. spotipy's old `user_playlist_create` method points at the dead route. |
| `POST /playlists/{id}/tracks` is **deprecated** → `POST /playlists/{id}/items`. | The new route is used. On top of that, spotipy 2.26.0 sends a bare JSON array instead of `{"uris": [...]}` ([issue #1075](https://github.com/spotipy-dev/spotipy/issues/1075)), so `add_tracks` makes the call directly with the documented body. |
| `localhost` is **not valid** as a redirect URI. | The default is `http://127.0.0.1:8888/callback`. |
| Development Mode: the app owner needs **Premium**, and the app is limited to **5 users**. | If you lose Premium, the app stops working. For personal use that is not a problem. |
| Quota is counted per **developer account**, shared across Client IDs. | A 429 can mean the daily quota is exhausted, not "you are going too fast". |
| `GET /me/tracks` is still current, maximum 50 items per page. | Paging uses 50. |

If your app is in **Extended Quota Mode**, the old endpoints work too, but this code
uses the new ones regardless: they are what will keep working tomorrow.

## Rate Limits

spotipy retries `429`, `500`, `502`, `503` and `504` on its own. This project raises
that setting from 3 to **5 retries** with a 0.8s backoff, because a single run can
make hundreds of requests and one 429 should not kill a job that takes minutes.

If the retries are exhausted, the program tells you to try again later and shows the
`Retry-After` value Spotify suggests, if it sends one.

Fetching 3000 songs is roughly 60 read requests plus ~30 write requests. Not much.

## Troubleshooting

**`missing environment variables: ...`**
Copy `.env.example` to `.env` in the project directory and fill it in. The `.env` is
searched from the current directory upwards.

**`Spotify rejected the request (401)` / `(403)`**
The refresh token expired, was revoked, or was generated by a different app / with
different scopes. Re-run `uv run python -m yearly_spotify_playlist.auth` and replace
`SPOTIFY_REFRESH_TOKEN`.

**`Spotify's request limit was reached (429)`**
Quota or rate limit. Wait and try again. The run is idempotent, so you can safely
repeat it.

**`unsupported_version` / `invalid_client`**
The Client ID or Secret do not belong to this app, or the Secret was regenerated and
the one you have is the previous one.

**`unsupported_grant_type` / `invalid_grant` while authorizing**
A stale URL or an already-used code was pasted in. Codes are single-use: start the
flow over from step 3.

**The browser says it cannot connect to `127.0.0.1:8888`**
Expected. Copy the URL from the address bar and paste it into the prompt.

**A year's playlist does not appear**
If that year has no liked songs, nothing is created. The program tells you which
years it found at the end of the reading phase.

**Songs that do not show up**
Only those in "Liked Songs". Podcasts, audiobooks, and songs liked from local files
are not included.

## Security

- `SPOTIFY_REFRESH_TOKEN` is long-lived: treat it like a password. Anyone holding it
  can access your library for as long as it stays valid.
- To revoke it: go to <https://developer.spotify.com/dashboard> → your app →
  **Settings** → *Revoke client secret* and re-authorize.
- The program only requests read access to your library. It never deletes anything.
- Playlists are created **public**. Spotify does not allow a Development Mode app to
  create private ones, so this is not a choice the tool makes. To hide a playlist,
  use the client's own *Make private* action.
