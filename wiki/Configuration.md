# TOML session configurations

`ianux load FILE.toml` creates a session from a TOML configuration. `ianux dump SESSION` writes the pane directories and window names from an existing session in the same format.

## Example

```toml
session_name = "demo" # optional; generated if omitted
detach = false         # optional; defaults to false

[[window]]
name = "editor"       # optional; tmux chooses a default if omitted
panes = 2              # optional; defaults to 4

[[window.pane]]
directory = "~/src/frontend"
init_command = "npm run dev"

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

## Schema and defaults

- Top-level `session_name` is an optional string; if omitted, Ianux generates a name such as `job_DDHHMMSS`.
- Top-level `detach` is an optional boolean and defaults to `false`.
- Each `[[window]]` table defines one window. `name` is optional; `panes` is an optional integer defaulting to 4.
- Each `[[window.pane]]` table supplies an optional `directory` and `init_command` for one pane. Their defaults are the current working directory and `p4init`.
- Pane tables are ordered within each window. If a window has more panes than pane tables, the final table's values are reused for the remaining panes in that window.
- Pane tables beyond a window's `panes` count are ignored.
- If a window has no pane tables, all its panes use the default directory and command.
- If there are no `[[window]]` tables, Ianux creates one default window with four panes.

Unknown keys at the top level, window level, or pane level are rejected to help catch typos.

## Select a config interactively

```bash
ianux load --select-config
```

This lists TOML files in `~/.config/ianux/sessions/`. If that directory does not exist, Ianux creates it and seeds it with `demo.toml`. An existing directory, including an empty one, is left as-is. You can also provide a TOML path with `--select-config`; in that case the path is loaded directly without prompting.

## Dumping sessions

```bash
ianux dump my-session
ianux dump my-session --output ~/configs
```

The `--output` value is a directory; the output filename is derived from the session name. By default, files go to `~/.config/ianux/sessions/`, where they can be selected by `load --select-config`.

Dumped files include the session name, each window's reported name, pane count, and pane directories. `init_command` is written as an empty string because a running pane's original startup command cannot be recovered. `detach` is omitted because it is not a property recoverable from the live session. Edit the generated file to add startup commands or adjust window names before reloading if needed.
