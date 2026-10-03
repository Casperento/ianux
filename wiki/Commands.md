# Command reference

Ianux provides seven subcommands. Run `ianux <command> --help` for the complete option list.

| Command | Alias | Purpose |
|---|---|---|
| `session` | `s` | Create a multi-window, multi-pane workspace |
| `run` | `r` | Send commands to a detached session |
| `list` | `ls` | Display open sessions and their numeric IDs |
| `attach` | `a` | Select or target a session, window, or pane |
| `kill` | `k` | Select or target a session, window, or pane to close |
| `load` | `l` | Create a workspace from a TOML file |
| `dump` | `d` | Save a session's pane directories to TOML |

If the first argument is not a recognized subcommand, Ianux treats the invocation as `session`. With no arguments, it displays top-level help.

## `session`

Create a session with one or more windows and panes:

```bash
ianux session --panes 6
ianux session --window-panes 2 --window-name editor \
  --window-panes 1 --window-name logs
```

`--panes` sets the pane count for a single window (1–256). For multiple windows, repeat `--window-panes`; optionally repeat `--window-name` in the same order. Repeat `--directory` and `--init-command` to configure panes in order across all windows. If fewer values are supplied than there are panes, the last value is reused. Defaults are the current directory and `p4init`.

Use `--session-name NAME` to choose an exact name, `--detach` to create without attaching, and `--init-command CMD` to set commands run after changing into each pane's directory. The default command is `session`, so `ianux --panes 6` is equivalent to `ianux session --panes 6`.

When the requested name already exists, Ianux chooses a numbered variant (`name-1`, `name-2`, …) and leaves the existing session untouched. Unnamed sessions receive a generated `job_DDHHMMSS` name.

## `run`

Run one or more shell commands sequentially in a new detached session:

```bash
ianux run "make clean" "make all"
ianux run --session mybuild "make clean" "make all"
```

Use `--session NAME` for an explicit session name. Without it, Ianux may interpret the first positional argument as a name when it has no spaces and is not a recognized shell command; otherwise it generates a name. Use `--kill` to wait for the commands to finish, capture their output, and then close the session. `--output FILE` chooses the capture path; its default is `/tmp/<session>.capture-pane`. The monitoring process polls the pane for up to one hour and records completion in `/tmp/<session>.monitor.log`.

## `list`

```bash
ianux list
```

Displays sessions with a numeric ID, name, window/pane counts, creation time, and terminal size. IDs are assigned alphabetically by session name and are used by `attach`, `kill`, and `dump`.

## `attach`

```bash
ianux attach             # interactive picker
ianux attach my-session  # by name
ianux attach 2           # by numeric ID from list
ianux attach 2:1.0       # window 1, pane 0
```

With no target, Ianux prompts you to choose a session. A target can be a name or list ID, optionally followed by a tmux window or pane index.

## `kill`

```bash
ianux kill               # interactive picker
ianux kill my-session
ianux kill 2:0           # window 0 in session ID 2
ianux kill 2:0.1         # pane 1 in window 0
ianux kill my-session:0.*
```

Targets use `SESSION`, `SESSION:WINDOW`, `SESSION:WINDOW.PANE`, or `SESSION:WINDOW.*`. `SESSION` can be a literal name or a numeric ID from `list`. The `.*` target prompts whether to keep one pane or close all panes in the window. Interactive mode repeats until you quit or no sessions remain.

## `load` and `dump`

`load` creates a session from TOML; `dump` records pane directories and window names in that TOML format:

```bash
ianux load project.toml
ianux load --select-config
ianux dump my-session
ianux dump my-session --output ~/configs
```

The default config directory is `~/.config/ianux/sessions/`. See [TOML session configurations](Configuration.md) for the schema and behavior.
