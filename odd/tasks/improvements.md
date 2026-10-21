# Improvements — yearly-spotify-playlist

Batch de mejoras de testing, observabilidad, features y CI.

## Specs

- S1: Agregar tests unitarios para `config.py` (`load_settings`): variables faltantes, defaults, stripping, `market` opcional.
- S2: Agregar tests unitarios para `spotify_api.py` (`SpotifyLibrary`): paginación de playlists, `playlist_track_uris`, `owned_playlists_by_name`, `add_tracks`, `create_playlist` — con mock del cliente `Spotify`.
- S3: Agregar logging estructurado con `logging.getLogger()`. Nivel configurable por variable de entorno `LOG_LEVEL` (default `WARNING`). No romper las barras de tqdm.
- S4: En modo verbose (cuando `LOG_LEVEL=DEBUG`), imprimir el traceback completo ante errores no esperados, además del mensaje amigable que ya existe.
- S5: Loguear un warning cuando `owned_playlists_by_name` encuentra una playlist con nombre repetido y la ignora (usando el logger de S3).
- S6: Agregar modo dry-run con variable de entorno `DRY_RUN=1`. Solo lista las playlists que crearía y cuántas canciones agregaría, sin modificar nada en Spotify.
- S7: Agregar filtro por rango de años con `SPOTIFY_YEARS=2023,2024` (lista explícita) y/o `SPOTIFY_YEAR_FROM=2020` (desde un año). Si ambos están seteados, `SPOTIFY_YEARS` tiene prioridad.
- S8: Rate limiting proactivo: agregar un pequeño sleep configurable entre batches de `add_tracks` (variable `BATCH_DELAY_SECONDS`, default `0.1`).
- S9: Mover `main()` y `_make_console_utf8_safe()` de `__init__.py` a un nuevo módulo `cli.py`. El `__init__.py` solo re-exporta `main`. El entry point en `pyproject.toml` apunta al nuevo módulo.
- S10: Agregar marker `py.typed` en `src/yearly_spotify_playlist/`.
- S11: CI: agregar `ruff check`, `ruff format --check`, coverage con `pytest-cov`, y matrix de OS (Ubuntu + Windows).
- S12: Migrar modo dry-run a argumento CLI `--dry-run` (en lugar de variable de entorno `DRY_RUN`). Agregar argumentos `-h`/`--help` con la descripción del comando y opciones.

## Tasks

| ID  | Specs | Route   | Commit |
|-----|-------|---------|--------|
| T1  | S1    | inline  | 6f5e04c |
| T2  | S2    | inline  | 6f5e04c |
| T3  | S3    | inline  | 10f9aac |
| T4  | S4    | inline  | 10f9aac |
| T5  | S5    | inline  | 10f9aac |
| T6  | S6    | inline  | 636aa38 |
| T7  | S7    | inline  | 636aa38 |
| T8  | S8    | inline  | 636aa38 |
| T9  | S9    | inline  | f74953f |
| T10 | S10   | inline  | f74953f |
| T11 | S11   | inline  | ea8dc9c |
| T12 | S12   | inline  | c87fd25 |

### Order & dependencies

**Phase 1 — Foundation (refactor + trivial)**
- T9 (cli.py) → primero, porque T4 y T6 tocan el entry point
- T10 (py.typed) → trivial, sin dependencias

**Phase 2 — Test coverage gaps**
- T1 (tests config.py) → sin dependencias
- T2 (tests spotify_api.py) → sin dependencias

**Phase 3 — Observability**
- T3 (logging) → primero en esta fase, T4 y T5 dependen de esto
- T4 (verbose traceback) → depende de T3
- T5 (warning duplicados) → depende de T3

**Phase 4 — Features**
- T6 (dry-run) → depende de T9
- T7 (filtro por años) → sin dependencias fuertes
- T8 (rate limiting) → sin dependencias

**Phase 5 — CI**
- T11 (CI) → último, para cubrir todo lo anterior

## Log

- L1: El usuario pidió un plan para todas las mejoras propuestas excepto la de actualizar la descripción de las playlists.
- L2: Implementadas todas las tareas (T1 a T11) cubriendo specs S1 a S11 en slices atómicos con tests y verificación de CI.
- L3: El usuario pidió reemplazar la variable de entorno `DRY_RUN` por el argumento de línea de comandos `--dry-run` y habilitar `-h`/`--help` con la descripción del comando.
