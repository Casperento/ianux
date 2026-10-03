"""Per-subcommand configuration dataclasses and shared validation.

Each CLI subcommand has a matching ``*Config`` dataclass here; ``cli.py``
builds one from parsed arguments and passes it to the corresponding manager
(SessionManager, SessionRunner, SessionKiller, SessionAttacher, loader.py,
dumper.py). ``build_session_config()`` centralizes the panes-range checks and
defaulting shared by the 'session' and 'load' subcommands.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .exceptions import AppError

_DEFAULT_INIT_COMMAND = "p4init"
_DEFAULT_PANES = 4
_MAX_PANES = 256
_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "tmux_wrapper" / "sessions"


@dataclass
class WindowConfig:
    """All runtime parameters for a single tmux window.

    Both *directories* and *init_commands* are ordered lists — one entry per
    pane.  When a list is shorter than *panes*, the last entry is reused for
    the remaining panes, so a single-entry list applies uniformly to all panes
    (backward-compatible with the old single-value behaviour).

    *name* is the tmux window name; None leaves it at tmux's own default.
    """

    panes: int
    directories: list[Path]
    init_commands: list[str]
    name: str | None = None


@dataclass
class SessionConfig:
    """All runtime parameters for a tmux session setup.

    *windows* holds one WindowConfig per window, in creation order; a
    single-window session (the common case) is simply a one-element list.

    When *detach* is True the session is created and initialised but not
    attached to; the caller returns immediately after setup.
    """

    windows: list[WindowConfig]
    session_name: str
    detach: bool = False


def build_window_config(
    *,
    panes: int,
    directories: list[Path],
    init_commands: list[str],
    name: str | None = None,
) -> WindowConfig:
    """Validate and assemble a WindowConfig from raw, undefaulted inputs.

    Shared by the CLI's 'session' subcommand and the 'load' (TOML) subcommand
    so both apply identical panes-range checks and identical defaulting for
    empty *directories*/*init_commands* lists (current working directory /
    ``_DEFAULT_INIT_COMMAND`` respectively).
    """
    if panes < 1:
        raise AppError("panes must be >= 1.")
    if panes > _MAX_PANES:
        raise AppError(f"panes must be <= {_MAX_PANES}.")

    return WindowConfig(
        panes=panes,
        directories=directories or [Path.cwd()],
        init_commands=init_commands or [_DEFAULT_INIT_COMMAND],
        name=name,
    )


def build_session_config(
    *,
    windows: list[WindowConfig],
    session_name: str | None,
    detach: bool,
) -> SessionConfig:
    """Assemble a SessionConfig from an already-validated list of windows.

    *session_name* is used verbatim when given; when None (the user didn't
    pass one), an auto-generated name is substituted so every session still
    gets a unique identity without depending on any path/directory name.
    """
    return SessionConfig(
        windows=windows,
        session_name=session_name or auto_session_name(),
        detach=detach,
    )


def auto_session_name() -> str:
    """Generate a unique-ish session name (mirrors tmrun's job_DDHHMMSS)."""
    return f"job_{datetime.now().strftime('%d%H%M%S')}"


@dataclass
class RunConfig:
    """Parameters for the 'run' subcommand.

    When *kill* is True the runner waits for all commands to finish, captures
    the pane scrollback, writes it to *output* (or ``/tmp/<session>.capture-pane``
    when *output* is None), then kills the session.
    """

    session_name: str
    commands: list[str]
    kill: bool = False          # wait → capture → write → kill session
    output: str | None = None   # None → /tmp/<session_name>.capture-pane


@dataclass
class KillConfig:
    """Parameters for the 'kill' subcommand.

    *target* is an optional tmux address to kill directly, bypassing the
    interactive session picker.  Accepted forms:

    ``SESSION``
        Kill the entire named session.
    ``SESSION:WINDOW``
        Kill a specific window (and all its panes).
    ``SESSION:WINDOW.PANE``
        Kill a single pane.
    ``SESSION:WINDOW.*``
        Kill every pane in a window; the user is offered a chance to keep one.

    When *target* is ``None`` the original interactive loop is shown instead.
    """

    target: str | None = None


@dataclass
class AttachConfig:
    """Parameters for the 'attach' subcommand.

    *session_name* is None when the interactive picker should be shown.
    When provided directly, the picker is skipped and the given address is
    attached immediately.  The address is NAME|ID[:WINDOW[.PANE]] — see
    SessionAttacher for the full grammar.
    """

    session_name: str | None = None


@dataclass
class ListConfig:
    """Parameters for the 'list' subcommand (none — just a print)."""


@dataclass
class LoadConfig:
    """Parameters for the 'load' subcommand.

    *path* is a TOML file describing a 'session' subcommand configuration
    (panes, session_name, detach, and one [[pane]] table per pane) — see
    loader.py for the full schema and defaulting rules.

    When *path* is None (selected via '--select-config' with no inline
    value), loader.py prompts the user to pick a file from
    _DEFAULT_CONFIG_DIR instead of reading a path given directly on the CLI.
    """

    path: Path | None = None


@dataclass
class DumpConfig:
    """Parameters for the 'dump' subcommand.

    *session_name* is a literal tmux session name or one of the numeric IDs
    shown by 'list'/'attach'/'kill'.  When None, an interactive picker is
    shown (mirrors AttachConfig/KillConfig).

    *output* is the destination *directory*, not a file path — the filename
    is always ``<session>.toml``, derived automatically.  When None,
    dumper.py defaults to ``_DEFAULT_CONFIG_DIR``.  The directory is created
    if needed.
    """

    session_name: str | None = None
    output: Path | None = None
