"""SessionDumper — save an existing session's windows/panes to a TOML file.

Captures the current working directory of every pane in every window of a
tmux session and writes them out in the same nested schema ``loader.py``
reads for the 'load' subcommand ([[window]] / [[window.pane]]).
``init_command`` is always written as an empty string — dump only records
directories; commands are filled in by hand afterwards. ``session_name``
is written as the dumped session's full name, so reloading the file
reproduces the exact same session name instead of falling back to 'load''s
auto-generated default; ``detach`` is still omitted since it isn't
recoverable from a live session.

Two usage modes, mirroring SessionAttacher/SessionKiller:

  Interactive (session_name is None)
      Lists all open tmux sessions with numeric IDs and prompts the user to
      choose one.

  Direct (session_name is provided)
      A literal session name or one of the numeric IDs shown by
      'list'/'attach'/'kill'.
"""

from typing import Callable

from .config import DumpConfig, _DEFAULT_CONFIG_DIR
from .exceptions import AppError
from .killer import resolve_session_id
from .picker import pick_session
from .tmux import TmuxClient


class SessionDumper:
    """Handles the 'dump' subcommand: save a session's windows/panes to TOML."""

    def __init__(
        self,
        client: TmuxClient,
        prompt_fn: Callable[[str], str] = input,
    ) -> None:
        self._client = client
        self._prompt = prompt_fn

    def dump(self, config: DumpConfig) -> int:
        session = self._resolve_session(config.session_name)

        win_panes = self._client.list_panes_all(session)
        names = self._client.window_names(session)

        windows: list[tuple[str, list[str]]] = []
        total_panes = 0
        for window in sorted(win_panes, key=lambda w: (int(w) if w.isdigit() else w)):
            panes = win_panes[window]
            directories = [
                self._client.pane_current_path(session, window, p) for p in panes
            ]
            windows.append((names.get(window, ""), directories))
            total_panes += len(panes)

        output_dir = config.output or _DEFAULT_CONFIG_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{session}.toml"
        output_path.write_text(_render_toml(session, windows))

        print(
            f"Dumped '{session}' ({len(windows)} window(s), {total_panes} pane(s))"
            f" to '{output_path}'."
        )
        return 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_session(self, session_name: str | None) -> str:
        if session_name is None:
            return pick_session(self._client, self._prompt, "Select a session to dump")

        session = resolve_session_id(self._client, session_name)
        if not self._client.session_exists(session):
            raise AppError(f"Session '{session}' does not exist.")
        return session


def _render_toml(session: str, windows: list[tuple[str, list[str]]]) -> str:
    """Render *windows* (name, directories) pairs as a 'load'-compatible TOML document.

    *session* (the dumped session's full tmux name) is written as
    ``session_name`` so that reloading the file reproduces the exact same
    session name, rather than falling back to 'load''s auto-generated
    default.
    """
    lines: list[str] = [f"session_name = {_toml_string(session)}", ""]
    for name, directories in windows:
        lines.append("[[window]]")
        if name:
            lines.append(f"name = {_toml_string(name)}")
        lines.append(f"panes = {len(directories)}")
        lines.append("")
        for directory in directories:
            lines.append("[[window.pane]]")
            lines.append(f"directory = {_toml_string(directory)}")
            lines.append('init_command = ""')
            lines.append("")
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    """Quote *value* as a TOML basic string (backslash/quote escaping)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
