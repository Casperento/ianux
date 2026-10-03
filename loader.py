"""Build a SessionConfig from a TOML file for the 'load' subcommand.

Schema
------
::

    session_name = "demo"   # optional string, default: auto-generated (e.g. job_DDHHMMSS)
    detach = false           # optional bool, default false

    [[window]]
    name = "editor"                  # optional, default: tmux's own default
    panes = 2                        # optional int, default 4

    [[window.pane]]
    directory = "~/src/frontend"     # optional, default: current working directory
    init_command = "npm run dev"     # optional, default: "p4init"

    [[window.pane]]
    directory = "~/src/backend"
    init_command = "flask run"

    [[window]]
    name = "logs"
    panes = 1

Each ``[[window]]`` table describes one tmux window; each of its
``[[window.pane]]`` sub-tables contributes one entry to that window's
ordered ``directories``/``init_commands`` lists — identical semantics to
repeating ``--directory``/``--init-command`` once per pane on the ``session``
subcommand, but scoped to the window: when a window's ``panes`` exceeds the
number of its ``[[window.pane]]`` tables, the last table's values are reused
for the remaining panes of *that window*; extra tables beyond ``panes`` are
simply unused. Omitting ``[[window.pane]]`` entirely falls back to the
current working directory / ``"p4init"`` for that window. Omitting
``[[window]]`` entirely produces a single default window (panes=4, cwd,
``"p4init"``), exactly like omitting ``-C``/``-c``/``--window-panes`` on the
CLI.

This module only builds the SessionConfig; ``__main__.py`` runs it through
the same ``build_resolver()`` + ``SessionManager`` path used by the
``session`` subcommand.

Interactive selection
----------------------
When ``config.path`` is ``None`` (the CLI's ``--select-config`` given with
no inline value), ``load_session_config()`` lists the ``*.toml`` files in
``_DEFAULT_CONFIG_DIR`` and prompts the user to pick one, mirroring the
numbered-picker UX used by ``attach``/``kill``. The very first time
``_DEFAULT_CONFIG_DIR`` itself is created, it's seeded with a ``demo.toml``
matching the example above, so a first run has something selectable.
"""

import tomllib
from pathlib import Path
from typing import Any, Callable

from .config import (
    _DEFAULT_CONFIG_DIR,
    _DEFAULT_INIT_COMMAND,
    _DEFAULT_PANES,
    LoadConfig,
    SessionConfig,
    WindowConfig,
    build_session_config,
    build_window_config,
)
from .exceptions import AppError
from .picker import pick

_ALLOWED_TOP_KEYS = frozenset({"session_name", "detach", "window"})
_ALLOWED_WINDOW_KEYS = frozenset({"name", "panes", "pane"})
_ALLOWED_PANE_KEYS = frozenset({"directory", "init_command"})

# Mirrors the "Example" in the 'load --help' description — seeded into a
# fresh _DEFAULT_CONFIG_DIR so '--select-config' has something to pick on a
# first run instead of an empty list.
_DEMO_TOML = """\
session_name = "demo"

[[window]]
name = "editor"
panes = 2

[[window.pane]]
directory = "~/src/frontend"
init_command = "npm run dev"

[[window.pane]]
directory = "~/src/backend"
init_command = "flask run"

[[window]]
name = "logs"
panes = 1
"""


def load_session_config(
    config: LoadConfig,
    *,
    prompt_fn: Callable[[str], str] = input,
    config_dir: Path = _DEFAULT_CONFIG_DIR,
) -> SessionConfig:
    """Parse *config.path* and return a validated SessionConfig.

    When *config.path* is None, a config file is picked interactively from
    *config_dir* first (see ``_select_config_path``).
    """
    path = config.path if config.path is not None else _select_config_path(config_dir, prompt_fn)
    data = _read_toml(path)
    _check_unknown_keys(data, _ALLOWED_TOP_KEYS, "top-level")

    window_tables = data.get("window", [])
    if not isinstance(window_tables, list):
        raise AppError("'window' must be an array of tables (use [[window]]).")

    if not window_tables:
        windows = [build_window_config(panes=_DEFAULT_PANES, directories=[], init_commands=[])]
    else:
        windows = [_parse_window_table(w) for w in window_tables]

    session_name = data.get("session_name")
    if session_name is not None and not isinstance(session_name, str):
        raise AppError(f"'session_name' must be a string, got {session_name!r}.")

    detach = data.get("detach", False)
    if not isinstance(detach, bool):
        raise AppError(f"'detach' must be a boolean, got {detach!r}.")

    return build_session_config(
        windows=windows,
        session_name=session_name,
        detach=detach,
    )


def _parse_window_table(table: Any) -> WindowConfig:
    """Parse one ``[[window]]`` table into a validated WindowConfig."""
    if not isinstance(table, dict):
        raise AppError("Each [[window]] entry must be a table.")
    _check_unknown_keys(table, _ALLOWED_WINDOW_KEYS, "[[window]]")

    name = table.get("name")
    if name is not None and not isinstance(name, str):
        raise AppError(f"[[window]] 'name' must be a string, got {name!r}.")

    panes = table.get("panes", _DEFAULT_PANES)
    if not isinstance(panes, int) or isinstance(panes, bool):
        raise AppError(f"[[window]] 'panes' must be an integer, got {panes!r}.")

    pane_tables = table.get("pane", [])
    if not isinstance(pane_tables, list):
        raise AppError("[[window]] 'pane' must be an array of tables (use [[window.pane]]).")
    for entry in pane_tables:
        if not isinstance(entry, dict):
            raise AppError("Each [[window.pane]] entry must be a table.")
        _check_unknown_keys(entry, _ALLOWED_PANE_KEYS, "[[window.pane]]")

    directories = [Path(_pane_field(p, "directory", Path.cwd())) for p in pane_tables]
    init_commands = [_pane_field(p, "init_command", _DEFAULT_INIT_COMMAND) for p in pane_tables]

    return build_window_config(
        panes=panes,
        directories=directories,
        init_commands=init_commands,
        name=name,
    )


def _select_config_path(config_dir: Path, prompt_fn: Callable[[str], str]) -> Path:
    """List *.toml files in *config_dir* and prompt the user to pick one.

    *config_dir* is created (including parents) if it doesn't exist yet —
    mirrors 'dump', which creates the same directory when writing to it. The
    very first time the directory itself is created, it's seeded with
    'demo.toml' (see _DEMO_TOML) so a first-time '--select-config' has
    something to pick instead of an empty list. An already-existing
    directory (even an empty one) is left alone.
    """
    if not config_dir.is_dir():
        config_dir.mkdir(parents=True)
        (config_dir / "demo.toml").write_text(_DEMO_TOML, encoding="utf-8")

    tomls = sorted(config_dir.glob("*.toml"))
    if not tomls:
        raise AppError(f"No TOML config files found in '{config_dir}'.")

    return pick(
        tomls,
        prompt_fn,
        heading=f"TOML configs in {config_dir}:",
        prompt="Select a config",
        label=lambda p: p.name,
    )


def _pane_field(pane: dict, key: str, default: Any) -> Any:
    """Return pane[key] if present (type-checked as str), else *default* unchanged."""
    if key not in pane:
        return default
    value = pane[key]
    if not isinstance(value, str):
        raise AppError(f"[[window.pane]] '{key}' must be a string, got {value!r}.")
    return value


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise AppError(f"TOML config file not found: {path}")
    except tomllib.TOMLDecodeError as exc:
        raise AppError(f"Invalid TOML in '{path}': {exc}")


def _check_unknown_keys(table: dict, allowed: frozenset[str], where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise AppError(f"Unknown key(s) in {where}: {', '.join(sorted(unknown))}")
