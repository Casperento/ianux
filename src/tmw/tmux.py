"""Facade over the tmux CLI.

Every interaction with tmux goes through TmuxClient.  Callers never
construct subprocess arguments directly; they call named methods that each
map to a single tmux sub-command.

The optional *run_fn* constructor argument replaces subprocess.run, making
the client fully testable without a live tmux installation.
"""

import subprocess
from typing import Callable

from .exceptions import AppError


class TmuxClient:
    """Thin, testable wrapper around every ``tmux`` sub-command this app needs."""

    def __init__(self, run_fn: Callable = subprocess.run):
        self._run = run_fn

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _tmux(
        self, args: list[str], *, capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        try:
            return self._run(
                ["tmux"] + args,
                check=False,
                text=True,
                capture_output=capture_output,
            )
        except FileNotFoundError:
            raise AppError("tmux is not available in PATH.")

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def session_exists(self, name: str) -> bool:
        """Return True if a session named *name* is currently open."""
        return self._tmux(["has-session", "-t", name]).returncode == 0

    def new_session(self, name: str, window_name: str | None = None) -> None:
        """Create a new detached session named *name*.

        *window_name* names the session's initial window (tmux's window 0);
        omitted, tmux assigns its own default name.
        """
        args = ["new-session", "-d", "-s", name]
        if window_name is not None:
            args += ["-n", window_name]
        result = self._tmux(args)
        if result.returncode != 0:
            raise AppError(f"Failed to create tmux session '{name}'.")

    def kill_session(self, name: str) -> None:
        """Kill the entire session named *name*."""
        result = self._tmux(["kill-session", "-t", name])
        if result.returncode != 0:
            raise AppError(f"Failed to kill session '{name}'.")

    def list_sessions_names(self) -> list[str]:
        """Return names of all open sessions names sorted alphabetically.

        Returns an empty list (rather than raising) when the tmux server is
        not running or has no sessions — callers decide how to handle it.
        """
        result = self._tmux(["list-sessions", "-F", "#{session_name}"])
        if result.returncode != 0:
            return []
        return sorted(
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip()
        )

    def new_window(self, session: str, name: str | None = None) -> str:
        """Create a new window in *session*; return the index tmux assigned.

        Uses ``-P -F`` to have tmux print back the real window index rather
        than assuming sequential numbering (which doesn't hold when
        ``base-index`` is customised or windows have been removed).
        """
        args = ["new-window", "-t", f"{session}:", "-P", "-F", "#{window_index}"]
        if name is not None:
            args += ["-n", name]
        result = self._tmux(args)
        if result.returncode != 0:
            raise AppError(f"Failed to create a new window in session '{session}'.")
        return (result.stdout or "").strip()

    def select_window(self, session: str, window: str) -> None:
        """Make *window* the current (attach-target) window of *session*."""
        result = self._tmux(["select-window", "-t", f"{session}:{window}"])
        if result.returncode != 0:
            raise AppError(f"Failed to select window '{session}:{window}'.")

    def window_names(self, session: str) -> dict[str, str]:
        """Return ``{window_index: window_name}`` for every window in *session*."""
        result = self._tmux(
            ["list-windows", "-t", session, "-F", "#{window_index}:#{window_name}"]
        )
        if result.returncode != 0:
            return {}
        names: dict[str, str] = {}
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            index, _, name = line.partition(":")
            names[index] = name
        return names

    def list_sessions(self) -> list[str]:
        """Return names of all open sessions names sorted alphabetically.

        Returns an empty list (rather than raising) when the tmux server is
        not running or has no sessions — callers decide how to handle it.
        """
        result = self._tmux(["list-sessions"])
        if result.returncode != 0:
            return []
        return sorted(
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip()
        )

    # ------------------------------------------------------------------
    # Window / pane management
    # ------------------------------------------------------------------

    def split_window(
        self,
        session: str,
        pane_number: int,
        window: str = "0",
        target_pane: str | None = None,
    ) -> None:
        """Split a window to add one pane.

        *target_pane* is the pane index string (e.g. ``"2"``) of the pane to
        split.  When omitted, tmux splits whichever pane is currently active,
        which is fine for the initial sequential creation pass.
        """
        if target_pane is not None:
            target = f"{session}:{window}.{target_pane}"
        else:
            target = f"{session}:{window}"
        result = self._tmux(["split-window", "-t", target])
        if result.returncode != 0:
            raise AppError(
                f"Failed while creating pane {pane_number} in session '{session}'."
            )

    def select_layout(self, session: str, layout: str, window: str = "0") -> None:
        """Apply a named tmux layout (e.g. ``"tiled"``) to a window of *session*."""
        result = self._tmux(["select-layout", "-t", f"{session}:{window}", layout])
        if result.returncode != 0:
            raise AppError(
                f"Failed to apply {layout!r} layout for session '{session}'."
            )

    def kill_window(self, session: str, window: str) -> None:
        """Kill *window* (and all its panes) in *session*."""
        result = self._tmux(["kill-window", "-t", f"{session}:{window}"])
        if result.returncode != 0:
            raise AppError(f"Failed to kill window '{session}:{window}'.")

    def kill_pane(self, session: str, window: str, pane: str) -> None:
        """Kill a single *pane* within *window* of *session*."""
        result = self._tmux(["kill-pane", "-t", f"{session}:{window}.{pane}"])
        if result.returncode != 0:
            raise AppError(f"Failed to kill pane '{session}:{window}.{pane}'.")

    def list_windows(self, session: str) -> list[str]:
        """Return window indices for *session* in index order."""
        result = self._tmux(
            ["list-windows", "-t", session, "-F", "#{window_index}"]
        )
        if result.returncode != 0:
            return []
        return [
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip()
        ]

    def list_panes_in_window(self, session: str, window: str) -> list[str]:
        """Return pane indices for *window* in *session*, in index order."""
        result = self._tmux(
            ["list-panes", "-t", f"{session}:{window}", "-F", "#{pane_index}"]
        )
        if result.returncode != 0:
            return []
        return [
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip()
        ]

    def list_panes_all(self, session: str) -> dict[str, list[str]]:
        """Return ``{window_index: [pane_index, ...]}`` for every window in *session*.

        Runs ``tmux list-panes -s -t SESSION`` so all windows are covered in one
        call.  Returns an empty dict (rather than raising) when the session cannot
        be queried — callers decide how to handle it.
        """
        result = self._tmux(
            ["list-panes", "-s", "-t", session, "-F", "#{window_index}:#{pane_index}"]
        )
        if result.returncode != 0:
            return {}
        panes: dict[str, list[str]] = {}
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            win, _, pane = line.partition(":")
            panes.setdefault(win, []).append(pane)
        return panes

    def list_panes(self, session: str, window: str = "0") -> list[str]:
        """Return pane indices for a window of *session*, in index order."""
        result = self._tmux(
            ["list-panes", "-t", f"{session}:{window}", "-F", "#{pane_index}"]
        )
        if result.returncode != 0:
            raise AppError(f"Failed to list panes for session '{session}'.")
        panes = [
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip()
        ]
        if not panes:
            raise AppError(
                f"No panes found in session '{session}' after creation."
            )
        return panes

    def send_keys(self, session: str, window: str, pane: str, keys: str) -> None:
        """Type *keys* into *pane* of *window* in *session*, followed by Enter."""
        result = self._tmux(
            ["send-keys", "-t", f"{session}:{window}.{pane}", keys, "C-m"]
        )
        if result.returncode != 0:
            raise AppError(
                f"Failed to initialize pane {pane} in session '{session}'."
            )

    # ------------------------------------------------------------------
    # Pane inspection
    # ------------------------------------------------------------------

    def capture_pane(self, session: str, window: str, pane: str) -> str:
        """Capture the full scrollback of *pane* and return it as a string.

        ``-S -`` tells tmux to start from the very beginning of the scrollback
        buffer rather than only the visible terminal area, so the full output
        of a long-running command is preserved.
        """
        result = self._tmux(
            ["capture-pane", "-p", "-S", "-", "-t", f"{session}:{window}.{pane}"]
        )
        if result.returncode != 0:
            raise AppError(
                f"Failed to capture pane {pane} in session '{session}'."
            )
        return result.stdout or ""

    def pane_current_command(self, session: str, window: str, pane: str) -> str:
        """Return the name of the foreground process running in *pane*.

        Used by the idle-poll loop to detect when user commands have finished
        and the shell has returned to the foreground.
        """
        result = self._tmux(
            [
                "display-message", "-p",
                "-t", f"{session}:{window}.{pane}",
                "#{pane_current_command}",
            ]
        )
        if result.returncode != 0:
            raise AppError(
                f"Failed to query current command for pane {pane}"
                f" in session '{session}'."
            )
        return (result.stdout or "").strip()

    def pane_current_path(self, session: str, window: str, pane: str) -> str:
        """Return the current working directory of *pane*.

        Used by 'dump' to capture each pane's directory into a TOML config.
        """
        result = self._tmux(
            [
                "display-message", "-p",
                "-t", f"{session}:{window}.{pane}",
                "#{pane_current_path}",
            ]
        )
        if result.returncode != 0:
            raise AppError(
                f"Failed to query current directory for pane {pane}"
                f" in session '{session}'."
            )
        return (result.stdout or "").strip()

    # ------------------------------------------------------------------
    # Attach — interactive; must NOT capture output
    # ------------------------------------------------------------------

    def attach(self, session: str) -> None:
        """Attach the current terminal to *session* (interactive, uncaptured)."""
        result = self._tmux(["attach-session", "-t", session], capture_output=False)
        if result.returncode != 0:
            raise AppError(f"Failed to attach to session '{session}'.")
