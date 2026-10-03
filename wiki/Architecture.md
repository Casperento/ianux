# Architecture

Ianux is a Python 3.11+ package under `src/ianux/`. It separates command-line parsing, configuration, tmux process access, and command orchestration.

```text
argv
  └── cli.parse_args() → a typed *Config
       └── __main__.main() → command orchestrator
            └── TmuxClient → tmux subprocess CLI
```

## Package modules

| Module | Responsibility |
|---|---|
| `cli.py` | Parse arguments into command config dataclasses and build directory resolvers |
| `config.py` | Config dataclasses and shared validation |
| `directory.py` | Directory resolver protocol and explicit path strategy |
| `picker.py` | Shared interactive selection and numbered output |
| `exceptions.py` | `AppError`, handled by the application entrypoint |
| `session.py` | Create and initialize multi-window sessions |
| `runner.py` | Launch detached command sessions and capture output |
| `lister.py` | Format and print session listings |
| `attacher.py` | Resolve and attach to a session target |
| `killer.py` | Parse targets and kill sessions, windows, or panes |
| `loader.py` | Parse and validate TOML session configuration |
| `dumper.py` | Write live session pane directories to TOML |
| `tmux.py` | `TmuxClient`, the sole wrapper for tmux subprocess calls |

`__main__.main()` dispatches the parsed config to an orchestrator. Each orchestrator receives a `TmuxClient`. `entrypoint()` catches `AppError`, prints a concise error to stderr, and returns exit status 1 rather than exposing a traceback.

The `load` command converts its `LoadConfig` to a `SessionConfig` and then uses the same resolver and `SessionManager` path as the `session` command. `attach` and `kill` share target parsing and numeric session-ID resolution from `killer.py`. Interactive commands reuse the prompt helpers in `picker.py`.

## tmux boundary

All tmux commands go through `TmuxClient` in `tmux.py`; other modules do not construct tmux subprocess arguments. Its injectable `run_fn` defaults to `subprocess.run`, allowing unit tests to provide canned subprocess results without a tmux server.

## Session layout

Each window is laid out independently. Up to four panes are created through sequential splits and arranged with tmux's tiled layout. For larger counts, the existing 2×2 base is subdivided round-robin and re-tiled after each split to keep the result balanced.
