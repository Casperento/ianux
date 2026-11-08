# Command reference

Ianux provides seven subcommands. Run `ianux <command> --help` for the complete option list.

| Command | Alias | Purpose |
|---|---|---|
| `session` | `s` | Create a multi-window, multi-pane workspace |
| `list` | `ls` | Display open sessions and their numeric IDs |
| `attach` | `a` | Select or target a session, window, or pane |
| `kill` | `k` | Select or target a session, window, or pane to close |
| `load` | `l` | Create a workspace from a TOML file |
| `dump` | `d` | Save a session's pane directories to TOML |
| `print` | `p` | Print a pane's current output without attaching |

If the first argument is not a recognized subcommand, Ianux treats the invocation as `session`. With no arguments, it displays top-level help.

Use `--version` (or `-v`) to print the installed Ianux package version:

```bash
ianux --version
ianux -v
```

## `session`

Create a session with one or more windows and panes:

```bash
ianux session -p 6
ianux session -p 2 -w editor \
  -p 1 -w logs
```

Use `-p`/`--window-panes` once per window to set its pane count (1–256); if omitted, one window with four panes is created. Optionally repeat `-w`/`--window-name` in the same order. Repeat `--directory` and `--init-command` to configure panes in order across all windows. If fewer values are supplied than there are panes, the last value is reused. Defaults are the current directory and `echo Hello`.

The long forms `--window-panes` and `--window-name` can be used in place of `-p` and `-w`. Use `--split-direction horizontal` (the default) to make the first split top-to-bottom, or `--split-direction vertical` to make it side-by-side. Subsequent splits alternate axes to make four equal quadrants. This applies to every window created by the command.

Use `--session-name NAME` to choose an exact name, `--detach` to create without attaching, and `--init-command CMD` to set commands run after changing into each pane's directory. The default command is `session`, so `ianux --window-panes 6` is equivalent to `ianux session --window-panes 6`.

When the requested name already exists, Ianux chooses a numbered variant (`name-1`, `name-2`, …) and leaves the existing session untouched. Unnamed sessions receive a generated `job_DDHHMMSS` name.

## Run commands in a detached session

Use `session -d` to initialize panes with commands and leave the tmux session
running in the background. Repeat `-p`/`-w` to make multiple windows and repeat
`-c` once per pane to provide commands in order across those windows:

```bash
ianux session -d -p 2 -w app -p 1 -w logs \
  -c 'npm run dev' -c 'npm test' -c 'tail -f app.log'
```

The first two commands start in separate panes of the `app` window; the third
starts in the `logs` window. If fewer commands are provided than panes, the last
command is reused. Attach later with `ianux attach` (or `tmux attach-session`).

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

With no target, Ianux shows a numbered session list. Enter the number to
continue or `q` to quit without attaching. A target can be a name or list ID,
optionally followed by a tmux window or pane index.

## `kill`

```bash
ianux kill               # interactive picker
ianux kill my-session
ianux kill 2:0           # window 0 in session ID 2
ianux kill 2:0.1         # pane 1 in window 0
ianux kill my-session:0.*
```

Targets use `SESSION`, `SESSION:WINDOW`, `SESSION:WINDOW.PANE`, or `SESSION:WINDOW.*`. `SESSION` can be a literal name or a numeric ID from `list`. Interactive mode shows a numbered list and repeats until you enter `q` or no sessions remain. The `.*` target lists pane indexes; enter an index to keep that pane, `n` to close all panes, or `q` to cancel.

## `print`

Print a pane's current output to stdout without attaching to its session:

```bash
ianux print my-session:0.1   # visible output of pane 1 in window 0
ianux p 2:0.0                # same, using the numeric ID from list
ianux p 1.0                  # pane 0 of window 1 in the current (or last-used) session
ianux p -s 2:0.0             # full scrollback instead of the visible area
```

The target must be a full pane address: `SESSION:WINDOW.PANE`, or `WINDOW.PANE` to address the current session. The current session is the or last-used one, i.e. the session you are currently attached to: inside tmux, the session your shell runs in; from another terminal, the session of the most recently active tmux client (falling back to the most recently created session if no client is attached). This lets you print the output of any other window or pane of that session without switching away from the one you are working in, or without attaching at all. `SESSION` can be a literal name or a numeric ID from `list`. Session-only, window-only, and `.*` targets are rejected. Trailing blank lines in the visible area are trimmed.

## `load` and `dump`

`load` creates a session from TOML; `dump` records pane directories and window names in that TOML format:

```bash
ianux load project.toml
ianux load
ianux dump my-session
ianux dump my-session --output ~/configs
```

The default config directory is `~/.config/ianux/sessions/`. Interactive `load` and `dump` pickers show numbered session/config choices; enter `q` to quit without loading or writing a dump. See [TOML session configurations](Configuration.md) for the schema and behavior.
