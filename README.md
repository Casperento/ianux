<div align="center">
  <img src="assets/ianux-logo.png" alt="Ianux logo" width="180">
  <p>A quick-to-use tmux wrapper for managing sessions.</p>
</div>

ianux is a quick-to-use Python command-line tool for creating and restoring
multi-window, multi-pane tmux sessions, running commands in detached sessions,
and listing, attaching to, or closing sessions. It requires Python 3.11+,
[uv](https://docs.astral.sh/uv/), and `tmux` on `PATH`.

## Quick start

Install Ianux as a standalone command:

```bash
uv tool install .
ianux --help
ianux session -p 4
```

Or run it from a checkout:

```bash
uv sync
uv run ianux --help
uv run ianux session -p 4
```

In `session` mode, `-p` is the short form of `--window-panes` and `-w` is the
short form of `--window-name`. Repeat them to configure multiple windows:

```bash
ianux session -p 2 -w editor -p 1 -w logs
```

Without `-p`/`--window-panes`, Ianux creates one window with four panes.

## Commands

| Command | Alias | Purpose |
|---|---|---|
| `session` | `s` | Create and attach to a multi-window, multi-pane session (default) |
| `list` | `ls` | List open sessions |
| `attach` | `a` | Attach to a session, window, or pane |
| `kill` | `k` | Close a session, window, or pane |
| `load` | `l` | Create a session from TOML |
| `dump` | `d` | Save a session's pane directories to TOML |

Run `ianux <command> --help` for options and examples. See the [wiki](wiki/Home.md)
for the [full command reference](wiki/Commands.md), [TOML configuration guide](wiki/Configuration.md),
and [architecture](wiki/Architecture.md).

To run commands in the background, create a detached session with `session -d`.
Repeat `-p`/`-w` to create multiple windows, and `-c` to assign commands to
panes in order. For example, this starts three commands across two windows:

```bash
ianux session -d -p 2 -w app -p 1 -w logs \
  -c 'npm run dev' -c 'npm test' -c 'tail -f app.log'
```

The session stays available after Ianux exits. Attach later with `ianux attach`.

Interactive pickers for `attach`, `dump`, and `load` show numbered choices;
enter `q` to quit without taking action. The interactive `kill` picker works
the same way. For `kill SESSION:WINDOW.*`, enter a pane index to keep that pane,
`n` to close all panes, or `q` to cancel.

## Development

```bash
uv sync
uv run pytest
uv build
```

End-to-end tests use a real tmux server and skip when `tmux` is unavailable.
See [Development and testing](wiki/Development.md) for details.
