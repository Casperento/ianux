# tmw

A small Python CLI that wraps common `tmux` workflows: spinning up a
multi-window, multi-pane development session, saving that layout to a TOML
file and recreating it later, firing off a detached job and grabbing its
output when it's done, and listing/attaching/killing sessions, windows, or
panes without memorising tmux target syntax.

It ships as a proper Python package (`tmux_wrapper/`) built around a few
focused classes — a `TmuxClient` facade over the `tmux` binary, one
orchestrator class per subcommand, and typed config dataclasses produced by
the argument parser.

## Requirements

- Python 3.11+
- `tmux` available on `PATH`

## Installation / invocation

No packaging/install step is required. Run it any of these ways from the
project directory:

```bash
python3.11 -m tmux_wrapper <command> [options]
./tmw.py <command> [options]
```

`tmw.py` is a thin executable shim: it adds the parent directory to
`sys.path` and delegates straight to `tmux_wrapper.__main__.entrypoint()`, so
both invocation styles run identical code.

For convenience you can put a wrapper/alias on `PATH`, e.g.:

```bash
alias tmw='python3.11 -m tmux_wrapper'
```

## Commands overview

The CLI has seven subcommands, each with a short alias:

| Command | Alias | Purpose |
|---|---|---|
| `session` | `s` | Create/attach a multi-window, multi-pane dev tmux session (**default**) |
| `run` | `r` | Fire commands into a new detached session |
| `list` | `ls` | Pretty-print all open tmux sessions |
| `attach` | `a` | Interactively (or directly) attach to a session |
| `kill` | `k` | Interactively (or directly) kill a session/window/pane |
| `load` | `l` | Create a session from a TOML config file |
| `dump` | `d` | Save an existing session's pane directories to a TOML config file |

For backward compatibility, if the first argument isn't a recognised
subcommand, `session` is silently inserted — so bare-flag invocations like
`tmw --panes 6` still work. Running with no arguments at all shows
top-level help instead of silently starting a session.

---

## `session` — multi-window, multi-pane dev session

Creates a tmux session with a configurable number of windows, each with its
own configurable number of panes; `cd`s each pane into a working directory
and runs an init command in it.

```bash
# All equivalent:
./tmw.py --panes 6
./tmw.py session --panes 6
python3.11 -m tmux_wrapper session --panes 6
```

| Flag | Default | Description |
|---|---|---|
| `-a, --panes N` | `4` | Number of panes in a single window (`1 ≤ N ≤ 256`). Mutually exclusive with `--window-panes` |
| `--window-panes N` | — | Pane count for one window; repeat once per window to create multiple windows |
| `--window-name NAME` | tmux default | Name for one window; repeat once per window, aligned with `--window-panes` |
| `-C, --directory PATH` | current directory | Pane working directory; repeat once per pane, spanning window boundaries |
| `-n, --session-name NAME` | auto-generated | Exact tmux session name to use |
| `-c, --init-command CMD` | `p4init` | Command run in a pane after `cd`; repeat once per pane, spanning window boundaries |
| `-d, --detach` | off | Create and initialize the session but don't attach to it |

**Session naming**: when `-n/--session-name` is given, it is used verbatim as
the session name. When omitted, an auto-generated name (`job_DDHHMMSS`) is
used instead — session naming never depends on directory/path names.

**Multiple windows**: `--window-panes` is repeatable — each occurrence
defines one window's pane count, in order. It's mutually exclusive with
`-a`/`--panes`, which is just shorthand for a single window. `--window-name`
optionally names each window, aligned by position; windows without a
corresponding `--window-name` keep tmux's own default name.

**Per-pane directories/commands**: both `-C` and `-c` can be repeated, once
per pane, in order — across *all* panes of *all* windows, not reset at each
window boundary. If fewer values are given than the total pane count, the
last value is reused for the remaining panes — so a single value applies
uniformly to every pane (the common case). Example, 2 windows (2 panes then
1 pane):

```bash
tmw session \
    --window-panes 2 --window-name editor \
    --window-panes 1 --window-name logs \
    --directory ~/src/frontend  --init-command 'npm run dev' \
    --directory ~/src/backend   --init-command 'flask run'   \
    --directory ~/src/infra     --init-command 'bash'
```

> Note: this global, flat-list behavior is specific to the CLI. The
> equivalent TOML config (see `load` below) scopes reuse-last to each
> window's own `[[window.pane]]` tables instead — see that section for why.

**Pane layout strategy** (per window): up to 4 panes are created with
sequential splits and a `tiled` layout (a balanced grid). Beyond 4, the base
2×2 grid's panes are sub-divided round-robin, re-tiling after every split,
producing a balanced grid instead of an ever-narrower column of panes.

**Existing session**: if a session with the computed name already exists,
the new session is created under a numbered variant instead
(`<name>-1`, `<name>-2`, …) — the existing session is left untouched.

**Detached mode**: pass `-d`/`--detach` to set up the session (windows,
panes, `cd`, init command) without attaching. Attach later with
`tmw attach` (or plain `tmux attach-session -t <name>`):

```bash
tmw session -d --panes 4 --init-command 'p4init'
```

---

## `run` — fire-and-forget commands in a detached session

Creates a new detached tmux session and sends one or more shell commands into
it sequentially — one window, one pane, no splitting. Mirrors the classic
`tmrun()` shell-function pattern.

```bash
# Auto-generated name (job_DDHHMMSS):
./tmw.py run "make clean" "make all"

# First token auto-detected as the session name (no spaces, not a known command):
./tmw.py run mybuild "make clean" "make all"

# Explicit name via flag (always unambiguous):
./tmw.py run --session mybuild "make clean" "make all"
```

| Flag | Description |
|---|---|
| `--session NAME` | Explicit session name; overrides the positional heuristic |
| `-k, --kill` | Wait for completion, capture output, write it to a file, then kill the session |
| `-o, --output FILE` | Output file path for `-k` (default: `/tmp/<session>.capture-pane`) |

**Session-name heuristic**: the first positional argument is treated as the
session name when it contains no spaces *and* isn't a recognised shell
command (`bash`, `cd`, `docker`, `echo`, `git`, `ls`, `node`, `npm`,
`python`, `python3`, `sh`). Otherwise a name is auto-generated as
`job_DDHHMMSS`. Use `--session` whenever the name matters and you want to be
explicit rather than relying on the heuristic.

**Wait-and-capture mode (`-k`/`--kill`)**: after sending your commands, a
sentinel `echo` is queued behind them. A detached background daemon process
(double-fork, fully disconnected from your terminal) polls the pane's
scrollback every 2 seconds — up to a 1-hour ceiling — until the sentinel line
appears, which is proof every prior command has finished (since a shell
executes queued input in order). It then:

1. Strips the sentinel lines out of the captured output.
2. Writes the clean output to `--output` (default
   `/tmp/<session>.capture-pane`).
3. Kills the tmux session.
4. Appends a `[DONE]` (or `[ERROR]` on failure) line to
   `/tmp/<session>.monitor.log`.

Your shell prompt is not blocked — the foreground command returns as soon as
the daemon is spawned, printing the daemon PID plus the output/log paths.

---

## `list` — show open sessions

```bash
./tmw.py list
```

Prints a colourized, aligned table of every open tmux session: a stable
numeric ID (matching what `attach`/`kill` accept), name, window/pane
breakdown, creation time, and terminal size. The numeric IDs are assigned by
sorting session names alphabetically, so they stay consistent across `list`,
`attach`, and `kill` in the same tmux server state.

---

## `attach` — pick or target a session

```bash
tmw attach                                   # interactive picker
tmw attach tmw-session-name                  # attach by name
tmw attach 2                                 # attach by numeric ID (from 'list')
tmw attach 2:1.0                             # attach directly to window 1, pane 0
```

With no argument, an interactive numbered list of open sessions is shown and
you pick one. With an argument, the picker is skipped: `SESSION` may be a
literal session name or one of the numeric IDs shown by `list`/the picker,
optionally followed by `:WINDOW` or `:WINDOW.PANE` (tmux's own indices, also
shown by `list`) to attach directly to that window or pane.

---

## `kill` — kill a session, window, or pane

```bash
tmw kill                  # interactive: pick sessions to kill, one at a time
tmw kill abc              # kill session 'abc'
tmw kill 2                # kill session with numeric ID 2 (from 'list')
tmw kill 2:0              # kill window 0 of session ID 2
tmw kill 2:0.1            # kill pane 1 in window 0 of session ID 2
tmw kill test:0.*         # kill every pane in window 0 of session 'test'
```

**Target address format** — `SESSION`, `SESSION:WINDOW`,
`SESSION:WINDOW.PANE`, or `SESSION:WINDOW.*`. `SESSION` accepts either a
literal name or a numeric ID from `list`/`attach`. The `.*` form kills every
pane in a window, first asking whether you'd like to keep one pane open (by
index) or kill them all.

**Interactive mode** (no target given): shows a numbered list of sessions,
kills the one you pick, then refreshes the list and repeats. Enter `q`,
`quit`, `exit`, `done`, or just press Enter to stop; the loop also ends
automatically once no sessions remain. Invalid input (non-numeric, or
out-of-range) prints a warning and re-prompts instead of exiting.

---

## `load` — build a session from a TOML file

Reads a TOML file (parsed with the stdlib `tomllib`) describing a `session`
configuration and creates/attaches the session exactly as `session` would —
no way to override the file's values from the command line.

```bash
tmw load myproject.toml
tmw l myproject.toml      # alias
```

**`--select-config`**: pick a config interactively instead of naming a path.
Mutually exclusive with `TOML_FILE` — give exactly one:

```bash
# Lists *.toml files in ~/.config/tmux_wrapper/sessions/ and prompts for one:
tmw load --select-config

# Equivalent to the positional form — loads the path directly, no prompt:
tmw load --select-config myproject.toml
```

**First run**: if `~/.config/tmux_wrapper/sessions/` doesn't exist yet, it's
created and seeded with a `demo.toml` — the same example shown in
`tmw load --help` — so `--select-config` has something to pick instead of an
empty list. This only happens the first time the directory itself is
created; an existing (even empty) directory is left alone.

**Schema**:

```toml
session_name = "demo"   # optional string, default: auto-generated (e.g. job_DDHHMMSS)
detach = false           # optional bool, default false

[[window]]
name = "editor"                  # optional, default: tmux's own default
panes = 2                        # optional int, default 4  (same default as 'session' --panes)

[[window.pane]]
directory = "~/src/frontend"     # optional, default: current working directory
init_command = "npm run dev"     # optional, default: "p4init"

[[window.pane]]
directory = "~/src/backend"
init_command = "flask run"

[[window]]
name = "logs"
panes = 1

[[window.pane]]
directory = "~/src/infra"
init_command = "bash"
```

**Semantics mirror `session` exactly**, since `load` builds the same
`SessionConfig` (one `WindowConfig` per `[[window]]` table) and hands it to
the same `SessionManager`:

- Each `[[window]]` table describes one window; each of its
  `[[window.pane]]` sub-tables contributes one entry to *that window's*
  ordered directories/init-commands lists, positionally. If a window's
  `panes` exceeds the number of its `[[window.pane]]` tables, the **last**
  table's values are reused for the remaining panes **of that window** —
  unlike `session`'s CLI flags, this reuse is scoped per window, not global,
  because each window's panes are written as their own nested tables rather
  than one flat sequence (see the note in `session` above).
- Tables beyond a window's `panes` are simply unused.
- Omitting a window's `[[window.pane]]` entirely falls back to `[cwd]` /
  `["p4init"]` for that window.
- Omitting `[[window]]` entirely produces a single default window (4 panes,
  cwd, `p4init`) — the same defaults `session` uses when no window flags are
  given.
- Unknown top-level keys (anything besides `session_name`, `detach`,
  `window`), unknown per-window keys (`name`, `panes`, `pane`), or unknown
  per-pane keys (`directory`, `init_command`) are rejected as configuration
  errors, to catch typos early.

---

## `dump` — save a session to a TOML file

The reverse of `load`: captures the working directory of every pane in every
window of an existing tmux session and writes a TOML file in the same nested
schema `load` reads. `init_command` is always written as `""` — `dump` only
records directories; fill in commands by hand afterwards. Each window's
`name` is written as whatever tmux currently reports for it (its default is
usually the name of the shell/command running in that window, e.g. `bash`,
if it was never explicitly named) — edit or remove it by hand if it isn't
meaningful.

```bash
tmw dump                       # interactive session picker
tmw dump my-session            # dump a session by name
tmw dump 2                     # dump a session by numeric ID (see 'list')
tmw dump my-session -o ~/configs   # writes ~/configs/my-session.toml
tmw d my-session               # alias
```

**Output directory**: `-o`/`--output` names the destination *directory*,
not a file — the filename is always `<session>.toml`, derived
automatically. Defaults to `~/.config/tmux_wrapper/sessions/` (created
automatically if it doesn't exist yet). Writing into the default directory
is what makes a dumped session immediately selectable with
`tmw load --select-config`.

**Example output** (session `my-session`, 1 window, 2 panes):

```toml
session_name = "my-session"

[[window]]
name = "bash"
panes = 2

[[window.pane]]
directory = "/home/user/src/frontend"
init_command = ""

[[window.pane]]
directory = "/home/user/src/backend"
init_command = ""
```

`session_name` is written as the dumped session's full name, so reloading
the file reproduces the exact same session name (`my-session`) instead of
falling back to `load`'s auto-generated default. `detach` is still omitted —
it isn't recoverable from a live tmux session — so `load` falls back to its
own default (`false`) for it.

---

## Architecture

```
tmux_wrapper/
├── __init__.py        package version
├── __main__.py         entry point — main() dispatches on config type; entrypoint() adds error handling
├── cli.py              argparse setup → *Config dataclasses; build_resolver()
├── config.py           WindowConfig / SessionConfig / RunConfig / AttachConfig / KillConfig / ListConfig / LoadConfig / DumpConfig
│                       dataclasses + build_window_config()/build_session_config() (shared 'session'/'load' validation)
├── directory.py        DirectoryResolver protocol + ExplicitResolver strategy
├── picker.py           print_numbered()/pick()/pick_session() — the numbered
│                       interactive prompt shared by 'attach', 'dump', 'kill', 'load'
├── exceptions.py        AppError — the one exception type entrypoint() catches
├── session.py          SessionManager — orchestrates the 'session' flow across one or more windows
├── runner.py           SessionRunner — orchestrates the 'run' flow (+ daemonized wait/capture/kill)
├── lister.py           SessionLister — orchestrates the 'list' flow (formatting/printing)
├── attacher.py         SessionAttacher — orchestrates the 'attach' flow
├── killer.py           SessionKiller — orchestrates the 'kill' flow (+ target address parsing)
├── loader.py           load_session_config() — TOML file (direct or interactively-picked) → SessionConfig for 'load'
├── dumper.py           SessionDumper — orchestrates the 'dump' flow (session's windows/panes → TOML file)
├── tmux.py             TmuxClient — window-aware facade over the `tmux` subprocess CLI
└── tmw.py     thin shim kept for backward-compatible ./invocation
```

**Flow**: `cli.parse_args()` turns `argv` into one of the `*Config`
dataclasses from `config.py`. `__main__.main()` inspects the config's type
and dispatches to the matching orchestrator (`SessionManager`,
`SessionRunner`, `SessionLister`, `SessionAttacher`, `SessionKiller`, or
`SessionDumper`), each constructed around a single `TmuxClient`. A
`LoadConfig` is first turned into a `SessionConfig` by
`loader.load_session_config()` (prompting interactively first when no path
was given), then handed to `build_resolver()`/`SessionManager` — the exact
same path the `session` subcommand uses, so `load` adds no new
orchestration logic of its own. `entrypoint()` wraps `main()` so any
`AppError` raised along the way (including TOML parsing/validation errors
from `loader.py`) is printed to stderr and turned into exit code `1` instead
of a traceback.

Every actual `tmux` invocation goes through `TmuxClient` (`tmux.py`) — no
other module builds subprocess arguments directly. Its `run_fn` constructor
argument (defaults to `subprocess.run`) is what makes the whole suite
testable without a live tmux server: tests substitute a fake `run_fn` that
returns canned `CompletedProcess` results.

`kill` and `attach` share the same tmux-address grammar
(`SESSION[:WINDOW[.PANE]]`, with `PANE` also accepting `*`); the parser and
numeric-ID resolution live in `killer.py` (`_parse_target`,
`resolve_session_id`) and are imported by `attacher.py`.

The "list sessions, prompt for a 1-based number, reject bad input" prompt
used by `attach`, `dump`, `kill`, and `load --select-config` is implemented
once in `picker.py` (`pick()`/`pick_session()`/`print_numbered()`) rather
than copied into each orchestrator.

## Testing

Tests live under `tests/` and use `pytest`. `pytest.ini` configures test
discovery to that directory:

```bash
python3.11 -m pytest
```

Most coverage is end-to-end: `test_*_e2e.py` files invoke the real `tmw.py`
CLI as a subprocess against a real `tmux` server and verify behavior with
independent `tmux` queries — no `TmuxClient` mocking. Every orchestrator has
one: `test_session_e2e.py`, `test_attacher_e2e.py`, `test_killer_e2e.py`,
`test_dumper_e2e.py`, `test_runner_e2e.py` (including the `--kill` path's
real double-fork daemon). These tests are marked `e2e` and skip
automatically when `tmux` isn't on `PATH`
(`python3.11 -m pytest -m "not e2e"` to exclude them explicitly).

Because this tmux server is shared with whatever real sessions a developer
already has open, the interactive tests never hardcode a numbered-prompt
index — they compute it from the live session list via
`conftest.session_index()` so a test can never select someone else's
session.

A few files remain unit tests, by design:
- `test_cli.py` / `test_config.py` / `test_main.py` — argument parsing,
  dataclass validation, and dispatch routing: inherently isolated logic with
  no tmux-dependent behavior to exercise.
- `test_directory.py` — already uses real filesystem paths, nothing to
  convert.
- `test_tmux.py` — the facade boundary. Verifies the exact argv built per
  tmux subcommand and exit-code→`AppError` mapping across every client
  method; an E2E test checks outcomes, not the precise command-line
  contract, and reproducing a real failure for every subcommand would be
  brittle and tmux-version-dependent.
- `test_picker.py` — pure selection/formatting logic with no tmux
  dependency at all.
- `test_session.py`, `test_killer.py`, `test_runner.py`, `test_dumper.py` —
  each trimmed to the handful of cases that are either pure logic
  impractical to re-verify per-case at E2E cost, or depend on a genuine race/
  timing window or a real-machine side effect (writing into the developer's
  actual `~/.config`) that's impractical or unsafe to force for real.

`tests/conftest.py` provides the E2E harness (`run_tmw()`, `e2e_session_name`,
`session_index()`, `run_tmw_attached()` for pty-backed `attach` tests), plus
`make_run_fn()` (a fake `subprocess.run` drop-in for `TmuxClient`) and a
`mock_client` fixture (`MagicMock` speced to `TmuxClient`) for the remaining
mock-based tests.
