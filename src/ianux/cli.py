"""Command-line interface.

Subcommands
-----------
session  (s)  — default
    Create / attach to a multi-window, multi-pane dev tmux session.
    Existing callers using bare flags (``ianux --panes 6``) are
    kept working: if the first argument is not a recognised subcommand, the
    parser silently inserts ``session`` before it.

    Multiple windows
    ~~~~~~~~~~~~~~~~
    ``-a/--panes`` (single window, the default) and ``--window-panes``
    (repeatable, once per window) are mutually exclusive.  ``--window-name``
    optionally names each window, aligned by position with ``--window-panes``.

    Per-pane directories and init commands
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Both ``--directory`` and ``--init-command`` may be repeated once per pane
    (in order, spanning window boundaries when multiple windows are given).
    When fewer entries are given than the total pane count, the last entry
    is reused for the remaining panes.  A single value therefore applies
    uniformly to every pane — backward compatible with the old single-value
    form.  Omitting ``--directory`` entirely uses the current working
    directory.

    Example (2 windows: 2 panes then 1 pane)::

        ianux session \\
            --window-panes 2 --window-name editor \\
            --window-panes 1 --window-name logs \\
            --directory ~/src/frontend  --init-command 'npm run dev' \\
            --directory ~/src/backend   --init-command 'flask run'   \\
            --directory ~/src/infra     --init-command 'bash'

    Detached mode (-d / --detach)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Pass ``-d`` to create the session and initialise all panes without
    attaching.  The session runs in the background; use
    ``ianux attach`` (or ``tmux attach-session``) to connect later::

        ianux session -d --panes 4 --init-command 'p4init'

run  (r)
    Create a new detached tmux session and send one or more shell commands
    into it, sequentially — equivalent to the tmrun() bash function.

attach  (a)
    List all open tmux sessions and let the user pick one interactively.
    Accepts an optional SESSION argument to skip the picker and attach
    directly by name, numeric ID, or a SESSION:WINDOW[.PANE] address (see
    the 'kill' target format below).

kill  (k)
    Interactively kill sessions one at a time.  After each kill the list
    is refreshed; the loop continues until no sessions remain or the user
    quits.  Direct targets accept the same NAME|ID[:WINDOW[.PANE]] address
    form as 'attach'.

load  (l)
    Load a TOML file describing a 'session' configuration (one or more
    windows, each with its own panes) and create/attach the session exactly
    as 'session' would.  TOML_FILE may be given directly, or picked
    interactively with '--select-config' (see below).

dump  (d)
    Save an existing session's windows/panes/working-directories to a TOML
    file in the same schema 'load' reads.  init_command is left empty ('')
    on every pane — dump only records directories.

Factories
---------
parse_args()     → SessionConfig | RunConfig | AttachConfig | KillConfig | DumpConfig
build_resolver() → DirectoryResolver        (session subcommand only)
"""

import argparse
import sys
from pathlib import Path
from typing import TypeVar

from .config import (
    _DEFAULT_CONFIG_DIR,
    _DEFAULT_INIT_COMMAND,
    _DEFAULT_PANES,
    AttachConfig,
    DumpConfig,
    KillConfig,
    ListConfig,
    LoadConfig,
    RunConfig,
    SessionConfig,
    WindowConfig,
    auto_session_name,
    build_session_config,
    build_window_config,
)
from .directory import DirectoryResolver, ExplicitResolver
from .exceptions import AppError

# ---------------------------------------------------------------------------
# Tokens that look like commands rather than session names (mirrors tmrun).
# ---------------------------------------------------------------------------
_COMMAND_TOKENS = frozenset(
    {
        "bash",
        "cd",
        "docker",
        "echo",
        "git",
        "ls",
        "node",
        "npm",
        "python",
        "python3",
        "sh",
    }
)

# Subcommand names (full and short aliases).
_SUBCOMMANDS = frozenset(
    {
        "session", "run", "attach", "kill", "list", "load", "dump",
        "s", "r", "a", "k", "ls", "l", "d",
    }
)

# Maps short aliases to their canonical subcommand names.
_ALIAS_MAP: dict[str, str] = {
    "a": "attach",
    "k": "kill",
    "r": "run",
    "s": "session",
    "ls": "list",
    "l": "load",
    "d": "dump",
}


# ---------------------------------------------------------------------------
# Backward-compat normalisation
# ---------------------------------------------------------------------------


def _normalize_argv(argv: list[str]) -> list[str]:
    """Prepend 'session' when no subcommand is present (backward compat).

    Empty argv shows top-level help so that bare invocation is informative
    rather than dropping silently into the interactive session flow.

    This lets callers continue to use ``ianux --panes 6`` without
    any change while also supporting ``ianux session --panes 6``
    and ``ianux run ...``.
    """
    if not argv:
        return ["--help"]
    if argv[0] in _SUBCOMMANDS or argv[0] in ("-h", "--help"):
        return argv
    return ["session"] + argv


# ---------------------------------------------------------------------------
# Top-level parser factory
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ianux",
        description="tmux session utilities.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    _add_session_subparser(subparsers)
    _add_run_subparser(subparsers)
    _add_attach_subparser(subparsers)
    _add_kill_subparser(subparsers)
    _add_list_subparser(subparsers)
    _add_load_subparser(subparsers)
    _add_dump_subparser(subparsers)

    return parser


# ---------------------------------------------------------------------------
# 'session' subcommand
# ---------------------------------------------------------------------------


def _add_session_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "session",
        aliases=["s"],
        help="Create and attach to a multi-window, multi-pane dev tmux session.",
        description=(
            "Create and attach to a tmux development session"
            " with configurable windows and pane counts."
        ),
    )
    panes_group = p.add_mutually_exclusive_group()
    panes_group.add_argument(
        "-a", "--panes",
        type=int,
        default=_DEFAULT_PANES,
        help="Number of panes to create in the tmux window (default: %(default)s).",
    )
    panes_group.add_argument(
        "--window-panes",
        type=int,
        action="append",
        dest="window_panes",
        default=None,
        metavar="N",
        help=(
            "Pane count for one window.  Repeat once per window (in order) to"
            " create multiple windows.  Mutually exclusive with -a/--panes"
            " (which is shorthand for a single window)."
        ),
    )
    p.add_argument(
        "--window-name",
        action="append",
        dest="window_names",
        default=None,
        metavar="NAME",
        help=(
            "Name for one window.  Repeat once per window (in order),"
            " aligned with --window-panes.  Windows without a corresponding"
            " --window-name keep tmux's own default name."
        ),
    )
    p.add_argument(
        "-C", "--directory",
        action="append",
        dest="directories",
        default=None,
        metavar="DIR",
        help=(
            "Working directory for a pane.  Repeat once per pane (in order,"
            " spanning window boundaries when --window-panes defines more"
            " than one window)."
            " When fewer entries than the total pane count are given, the"
            " last entry is reused for remaining panes."
            " If omitted entirely, the current working directory is used."
        ),
    )
    p.add_argument(
        "-n", "--session-name",
        default=None,
        help="Exact tmux session name to use (default: auto-generated, e.g. job_DDHHMMSS).",
    )
    p.add_argument(
        "-c", "--init-command",
        action="append",
        dest="init_commands",
        default=None,
        metavar="CMD",
        help=(
            "Command run in a pane after cd.  Repeat once per pane (in order,"
            " spanning window boundaries the same way as --directory)."
            " When fewer entries than the total pane count are given, the"
            f" last entry is reused for remaining panes.  Default (single entry): {_DEFAULT_INIT_COMMAND!r}."
        ),
    )
    p.add_argument(
        "-d", "--detach",
        action="store_true",
        default=False,
        help=(
            "Create and initialise the session but do not attach to it."
            " The session runs in the background; attach later with"
            " 'ianux attach' or 'tmux attach-session -t <name>'."
        ),
    )


# ---------------------------------------------------------------------------
# 'run' subcommand
# ---------------------------------------------------------------------------


def _add_run_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "run",
        aliases=["r"],
        help="Run commands in a new detached tmux session.",
        description=(
            "Create a detached tmux session and send one or more shell\n"
            "commands into it sequentially.\n\n"
            "SESSION_NAME is optional.  When omitted (or when the first\n"
            "positional looks like a shell command), a name is generated\n"
            "automatically as job_DDHHMMSS.\n\n"
            "Examples:\n"
            "  ianux run build  make clean  make all\n"
            "  ianux run mybuild  make clean  make all\n"
            "  ianux run --session mybuild  make clean  make all"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--session",
        metavar="NAME",
        help=(
            "Explicit session name."
            " Overrides the auto-detection heuristic for the first positional."
        ),
    )
    p.add_argument(
        "-k", "--kill",
        action="store_true",
        default=False,
        help=(
            "Wait for all commands to finish, capture the full pane scrollback,"
            " write it to a file, then kill the session."
            " Default output file: /tmp/<session-name>.capture-pane"
        ),
    )
    p.add_argument(
        "-o", "--output",
        metavar="FILE",
        default=None,
        help=(
            "File path for the captured pane output (requires --kill)."
            " Default: /tmp/<session-name>.capture-pane"
        ),
    )
    p.add_argument(
        "args",
        nargs="+",
        metavar="[SESSION_NAME] CMD [CMD ...]",
        help=(
            "Optional session name followed by one or more shell commands."
            " A token is treated as the session name when it contains no spaces"
            " and is not a recognised shell command."
        ),
    )


# ---------------------------------------------------------------------------
# 'attach' subcommand
# ---------------------------------------------------------------------------


def _add_attach_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "attach",
        aliases=["a"],
        help="Interactively select and attach to an open tmux session.",
        description=(
            "List all open tmux sessions and attach to the chosen one.\n\n"
            "Without SESSION, an interactive numbered list is shown.\n"
            "With SESSION, the picker is skipped and that address is attached\n"
            "directly — useful for scripting or when the name is known.\n"
            "SESSION may be a literal name, the numeric ID shown by\n"
            "'ianux list' or the interactive picker, and may optionally\n"
            "be followed by :WINDOW or :WINDOW.PANE (tmux's own indices, also\n"
            "shown by 'list') to attach directly to that window/pane.\n\n"
            "Examples:\n"
            "  ianux attach\n"
            "  ianux attach ianux-session-name\n"
            "  ianux attach 2\n"
            "  ianux attach 2:1.0"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "session_name",
        nargs="?",
        metavar="SESSION",
        help=(
            "Address of the session (and optional window/pane) to attach to"
            " directly: NAME|ID[:WINDOW[.PANE]]."
            " When omitted, an interactive list is shown."
        ),
    )


# ---------------------------------------------------------------------------
# 'kill' subcommand
# ---------------------------------------------------------------------------


def _add_kill_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "kill",
        aliases=["k"],
        help="Kill a tmux session, window, or pane — or pick one interactively.",
        description=(
            "Kill a tmux session, window, or pane by its tmux address.\n\n"
            "TARGET formats\n"
            "--------------\n"
            "  SESSION            kill the entire session\n"
            "  SESSION:WINDOW     kill a window (and all its panes)\n"
            "  SESSION:WINDOW.PANE kill a single pane\n"
            "  SESSION:WINDOW.*   kill every pane in a window\n"
            "                     (you will be asked whether to keep one open)\n\n"
            "SESSION may be a literal name or the numeric ID shown by\n"
            "'ianux list' or the interactive picker (same IDs used by\n"
            "'attach').  WINDOW and PANE are tmux's own indices.\n\n"
            "Without TARGET an interactive numbered list is shown so you can\n"
            "kill sessions one at a time.  Enter 'q', 'done', or press Enter\n"
            "to stop; the loop also exits when no sessions remain.\n\n"
            "Examples\n"
            "--------\n"
            "  ianux k abc        # kill session 'abc'\n"
            "  ianux k 2          # kill session with ID 2 (from 'list')\n"
            "  ianux k 2:0        # kill window 0 of session ID 2\n"
            "  ianux k 2:0.1      # kill pane 1 in window 0 of session ID 2\n"
            "  ianux k test:0.*   # kill all panes in window 0 of 'test'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "target",
        nargs="?",
        metavar="TARGET",
        help=(
            "Address to kill: NAME|ID[:WINDOW[.PANE]]."
            " Omit to enter the interactive session picker."
        ),
    )


# ---------------------------------------------------------------------------
# 'list' subcommand
# ---------------------------------------------------------------------------
def _add_list_subparser(subparsers) -> None:
    subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List existing tmux sessions.",
        description="List existing tmux sessions.",
    )


# ---------------------------------------------------------------------------
# 'load' subcommand
# ---------------------------------------------------------------------------


def _add_load_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "load",
        aliases=["l"],
        help="Create a session from a TOML config file.",
        description=(
            "Load a TOML file describing a 'session' subcommand configuration\n"
            "and create/attach the session exactly as 'session' would.\n\n"
            "Schema\n"
            "------\n"
            "  session_name    optional string, default: auto-generated (e.g. job_DDHHMMSS)\n"
            "  detach          optional bool, default false\n"
            "  [[window]]      zero or more tables, one per window:\n"
            "    name           optional string, default: tmux's own default\n"
            "    panes          optional int, default 4\n"
            "    [[window.pane]] zero or more tables, one per pane:\n"
            "      directory      optional string, default: current working directory\n"
            "      init_command   optional string, default: 'p4init'\n\n"
            "When a window's 'panes' exceeds the number of its [[window.pane]]\n"
            "tables, the last table's values are reused for the remaining\n"
            "panes of that window.  Extra tables beyond 'panes' are simply\n"
            "unused.  Omitting [[window]] entirely produces a single default\n"
            "window (panes=4, cwd, 'p4init').\n\n"
            "TOML_FILE and --select-config are mutually exclusive: give exactly\n"
            "one, or use --select-config with no value to pick a file\n"
            f"interactively from {_DEFAULT_CONFIG_DIR}.\n\n"
            "Example\n"
            "-------\n"
            "  session_name = \"demo\"\n\n"
            "  [[window]]\n"
            "  name = \"editor\"\n"
            "  panes = 2\n\n"
            "  [[window.pane]]\n"
            "  directory = \"~/src/frontend\"\n"
            "  init_command = \"npm run dev\"\n\n"
            "  [[window.pane]]\n"
            "  directory = \"~/src/backend\"\n"
            "  init_command = \"flask run\"\n\n"
            "  [[window]]\n"
            "  name = \"logs\"\n"
            "  panes = 1\n\n"
            "  ianux load myproject.toml\n"
            "  ianux load --select-config\n"
            "  ianux load --select-config myproject.toml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        metavar="TOML_FILE",
        help="Path to the TOML config file. Omit and use --select-config instead.",
    )
    p.add_argument(
        "--select-config",
        nargs="?",
        const="",
        default=None,
        dest="select_config",
        metavar="PATH",
        help=(
            "Pick a config interactively from"
            f" {_DEFAULT_CONFIG_DIR} when given with no value"
            " (seeded with a demo.toml the first time that directory is"
            " created), or load PATH directly when a value is given."
            " Mutually exclusive with TOML_FILE."
        ),
    )


# ---------------------------------------------------------------------------
# 'dump' subcommand
# ---------------------------------------------------------------------------


def _add_dump_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "dump",
        aliases=["d"],
        help="Save an existing session's pane directories to a TOML config.",
        description=(
            "Capture the working directory of every pane in every window of\n"
            "an existing tmux session and write them to a TOML file in the\n"
            "same format 'load' consumes.  init_command is left empty ('')\n"
            "for every pane — dump only records directories; fill in\n"
            "commands by hand afterwards.\n\n"
            "SESSION may be a literal name or the numeric ID shown by 'list'\n"
            "(same IDs used by 'attach'/'kill').  When omitted, an interactive\n"
            "session picker is shown.\n\n"
            "The output filename is always '<session>.toml' — derived\n"
            "automatically, not user-supplied.  -o/--output only chooses the\n"
            f"destination *directory* (default: {_DEFAULT_CONFIG_DIR}),\n"
            "which is created automatically if it doesn't exist yet.\n\n"
            "Examples\n"
            "--------\n"
            "  ianux dump\n"
            "  ianux dump my-session\n"
            "  ianux dump 2 -o ~/configs      # writes ~/configs/<session>.toml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "session_name",
        nargs="?",
        metavar="SESSION",
        help="Session to dump. Omit for an interactive picker.",
    )
    p.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Destination directory (default: "
            f"{_DEFAULT_CONFIG_DIR}). The file is always named"
            " '<session>.toml'."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_args(
    argv: list[str] | None = None,
) -> (
    SessionConfig | RunConfig | AttachConfig | KillConfig | ListConfig
    | LoadConfig | DumpConfig
):
    """Parse argv and return the appropriate config dataclass."""
    # When argv is None read from sys.argv[1:] explicitly so that
    # _normalize_argv always sees the real arguments before argparse does.
    effective = list(argv) if argv is not None else sys.argv[1:]
    effective = _normalize_argv(effective)
    arg_parser = _build_parser()
    namespace_parsed = arg_parser.parse_args(effective)

    # Resolve short aliases to their canonical subcommand name so the
    # dispatch below never has to handle both forms.
    namespace_parsed.command = _ALIAS_MAP.get(namespace_parsed.command, namespace_parsed.command)

    if namespace_parsed.command == "run":
        return _parse_run_config(arg_parser, namespace_parsed)
    if namespace_parsed.command == "attach":
        return _parse_attach_config(namespace_parsed)
    if namespace_parsed.command == "kill":
        return KillConfig(target=getattr(namespace_parsed, "target", None))
    if namespace_parsed.command == "list":
        return ListConfig()
    if namespace_parsed.command == "load":
        return _parse_load_config(arg_parser, namespace_parsed)
    if namespace_parsed.command == "dump":
        return DumpConfig(
            session_name=namespace_parsed.session_name,
            output=namespace_parsed.output,
        )

    return _parse_session_config(arg_parser, namespace_parsed)


def build_resolver(config: SessionConfig) -> DirectoryResolver:
    """Select the appropriate DirectoryResolver strategy from the config.

    The first directory of the first window is wrapped to resolve/validate
    it.  SessionManager.setup() handles the full per-pane, per-window
    directory lists.
    """
    return ExplicitResolver(config.windows[0].directories[0])


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


_T = TypeVar("_T")


def _slice_by_window(flat: list[_T], window_panes: list[int]) -> list[list[_T]]:
    """Slice a flat, globally-ordered list into one chunk per window.

    Each window takes up to *n* still-unconsumed items straight off the
    front of *flat* (no padding within a window — SessionManager already
    reuses a window's own last entry for any panes beyond its list, exactly
    as it does for a single window today). Only when *flat* is already
    exhausted before a window's turn does that window fall back to a
    single-item chunk carrying the last value handed out — this is what
    lets reuse-last cross a window boundary instead of resetting to that
    window's cwd/p4init default.
    """
    windows: list[list[_T]] = []
    idx = 0
    last: _T | None = None
    for n in window_panes:
        take = min(n, max(len(flat) - idx, 0))
        chunk = list(flat[idx:idx + take])
        idx += take
        if chunk:
            last = chunk[-1]
        elif last is not None:
            chunk = [last]
        windows.append(chunk)
    return windows


def _parse_session_config(
    parser: argparse.ArgumentParser, parsed: argparse.Namespace
) -> SessionConfig:
    window_panes: list[int] = parsed.window_panes or [parsed.panes]
    window_names: list[str] = parsed.window_names or []

    if len(window_names) > len(window_panes):
        parser.error(
            f"session: got {len(window_names)} --window-name value(s)"
            f" for {len(window_panes)} window(s)."
        )

    # action="append" leaves None when the flag was never passed.
    # build_window_config() defaults an empty list to the current working
    # directory / _DEFAULT_INIT_COMMAND.
    flat_directories: list[Path] = (
        [Path(d) for d in parsed.directories] if parsed.directories else []
    )
    flat_init_commands: list[str] = parsed.init_commands or []

    per_window_directories = _slice_by_window(flat_directories, window_panes)
    per_window_init_commands = _slice_by_window(flat_init_commands, window_panes)

    windows: list[WindowConfig] = []
    try:
        for i, panes in enumerate(window_panes):
            windows.append(
                build_window_config(
                    panes=panes,
                    directories=per_window_directories[i],
                    init_commands=per_window_init_commands[i],
                    name=window_names[i] if i < len(window_names) else None,
                )
            )
        return build_session_config(
            windows=windows,
            session_name=parsed.session_name,
            detach=parsed.detach,
        )
    except AppError as exc:
        parser.error(str(exc))


def _parse_run_config(
    arg_parser: argparse.ArgumentParser, namespace_parsed: argparse.Namespace
) -> RunConfig:
    raw: list[str] = namespace_parsed.args
    kill: bool = namespace_parsed.kill
    output: str | None = namespace_parsed.output

    if namespace_parsed.session:
        # Explicit --session flag: everything in args is a command.
        if not raw:
            arg_parser.error("run: provide at least one command.")
        return RunConfig(
            session_name=namespace_parsed.session,
            commands=raw,
            kill=kill,
            output=output,
        )

    # Heuristic: first token is a session name when it has no spaces and is
    # not a recognised shell command — mirrors the tmrun() bash function.
    if len(raw) >= 2 and _looks_like_session_name(raw[0]):
        return RunConfig(
            session_name=raw[0],
            commands=raw[1:],
            kill=kill,
            output=output,
        )

    if not raw:
        arg_parser.error("run: provide at least one command.")

    return RunConfig(
        session_name=auto_session_name(),
        commands=raw,
        kill=kill,
        output=output,
    )


def _parse_load_config(
    parser: argparse.ArgumentParser, parsed: argparse.Namespace
) -> LoadConfig:
    positional: Path | None = parsed.path
    select: str | None = parsed.select_config

    if positional is not None and select is not None:
        parser.error("load: specify TOML_FILE or --select-config, not both.")
    if select == "":
        return LoadConfig(path=None)
    if select is not None:
        return LoadConfig(path=Path(select))
    if positional is None:
        parser.error("load: provide TOML_FILE or --select-config.")
    return LoadConfig(path=positional)


def _parse_attach_config(parsed: argparse.Namespace) -> AttachConfig:
    return AttachConfig(session_name=parsed.session_name)


def _looks_like_session_name(token: str) -> bool:
    """True when a token should be treated as a session name, not a command."""
    return " " not in token and token not in _COMMAND_TOKENS


