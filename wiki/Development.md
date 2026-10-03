# Development and testing

## Set up a checkout

TMW uses uv for its environment and build workflow. Sync the project and its development dependencies:

```bash
uv sync
```

The development dependency group includes pytest. The package requires Python 3.11 or later, and end-to-end tests need `tmux` available on `PATH`.

## Run tests

```bash
uv run pytest
```

End-to-end tests use a real tmux server and skip automatically when `tmux` is unavailable. To run only tests that do not require the end-to-end suite:

```bash
uv run pytest -m "not e2e"
```

The E2E harness is in `tests/conftest.py`. It launches TMW as a subprocess and verifies behavior with independent tmux queries. Interactive tests derive prompt indexes from the live session list, avoiding hardcoded selections that could target a developer's own session.

Unit tests cover logic that is best checked in isolation: CLI parsing and dispatch, configuration validation, directory resolution, picker behavior, and the exact argument and error-mapping contract at the `TmuxClient` boundary. A small number of orchestration unit tests cover pure edge cases, races, and machine-side effects that are unsuitable for E2E tests.

## Build

```bash
uv build
```

This produces a wheel and source distribution in `dist/`. Use `uv build --clear` to remove previous build outputs before building.
