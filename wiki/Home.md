# Ianux Wiki

Ianux is a command-line wrapper for common [tmux](https://github.com/tmux/tmux) session workflows. It can create multi-window, multi-pane workspaces, launch detached commands, list and attach to sessions, close sessions or panes, and save or restore session layouts.

## Wiki pages

- [Installation and setup](Installation.md)
- [Command reference](Commands.md)
- [TOML session configurations](Configuration.md)
- [Architecture](Architecture.md)
- [Development and testing](Development.md)

## Quick start

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and `tmux` available on `PATH`.

```bash
uv tool install .
ianux --help
ianux session --panes 4
```

For a checkout-local environment, use `uv sync` and prefix commands with `uv run`.

## Commands

| Command | Alias | Use |
|---|---|---|
| `session` | `s` | Create a workspace and attach to it (the default command) |
| `run` | `r` | Run commands in a new detached session |
| `list` | `ls` | List open sessions with numeric IDs |
| `attach` | `a` | Attach interactively or to a session/window/pane |
| `kill` | `k` | Kill a session, window, or pane |
| `load` | `l` | Create a workspace from TOML |
| `dump` | `d` | Save pane directories from a session as TOML |

Run `ianux <command> --help` for current options. The [command reference](Commands.md) describes the main workflows and addressing rules.
