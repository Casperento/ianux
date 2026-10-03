"""SessionKiller — kill tmux sessions, windows, and panes.

Direct-target mode (``config.target`` is set)
----------------------------------------------
A tmux address is parsed and the appropriate kill command is issued
immediately — no interactive loop.

Accepted address forms:

``SESSION``
    Kill the entire named session.
``SESSION:WINDOW``
    Kill a specific window (and all its panes).
``SESSION:WINDOW.PANE``
    Kill a single pane.
``SESSION:WINDOW.*``
    Kill every pane in the window.  The user is asked first whether they
    would like to keep one pane open; if so, a numbered list is shown and
    only the remaining panes are killed.

Interactive mode (no target)
-----------------------------
When *target* is ``None`` the original interactive session-picker loop is
shown: the session list is displayed, the user picks one by index, that
session is killed, and the list is refreshed.  The loop continues until no
sessions remain or the user quits.

Invalid selections (non-numeric input, out-of-range index) print a short
warning and re-prompt rather than exiting — the user can always type 'q' or
press Ctrl-C to get out.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from .config import KillConfig
from .exceptions import AppError
from .picker import print_numbered
from .tmux import TmuxClient

# Any of these inputs end the interactive loop.
_QUIT_TOKENS = frozenset({"q", "quit", "exit", "done", ""})

# Inputs that mean "kill everything, keep nothing".
_KEEP_NONE_TOKENS = frozenset({"n", "no", "none", ""})


# ---------------------------------------------------------------------------
# Target parsing
# ---------------------------------------------------------------------------


class _Target(NamedTuple):
    """Parsed representation of a tmux kill address."""

    kind: str          # "session" | "window" | "pane" | "panes_all"
    session: str
    window: str | None
    pane: str | None


def _parse_target(raw: str) -> _Target:
    """Parse a raw tmux address string into a structured ``_Target``.

    Examples
    --------
    >>> _parse_target("abc")
    _Target(kind='session', session='abc', window=None, pane=None)
    >>> _parse_target("0:0")
    _Target(kind='window', session='0', window='0', pane=None)
    >>> _parse_target("0:0.0")
    _Target(kind='pane', session='0', window='0', pane='0')
    >>> _parse_target("test:0.*")
    _Target(kind='panes_all', session='test', window='0', pane=None)
    """
    if ":" not in raw:
        return _Target("session", raw, None, None)

    session, rest = raw.split(":", 1)

    if "." not in rest:
        return _Target("window", session, rest, None)

    window, pane = rest.split(".", 1)
    if pane == "*":
        return _Target("panes_all", session, window, None)

    return _Target("pane", session, window, pane)


def resolve_session_id(client: TmuxClient, token: str) -> str:
    """Resolve a numeric ID (as shown by 'list'/'attach'/'kill') to a session name.

    Falls back to treating *token* as a literal session name when it is not
    a digit string or is out of range for the current session list.
    """
    if not token.isdigit():
        return token
    sessions = client.list_sessions_names()
    idx = int(token) - 1
    if 0 <= idx < len(sessions):
        return sessions[idx]
    return token


# ---------------------------------------------------------------------------
# Killer
# ---------------------------------------------------------------------------


class SessionKiller:
    """Handles the 'kill' subcommand: direct-target and interactive modes."""

    def __init__(
        self,
        client: TmuxClient,
        prompt_fn: Callable[[str], str] = input,
    ) -> None:
        self._client = client
        self._prompt = prompt_fn

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def kill(self, config: KillConfig) -> int:
        """Dispatch to direct-target or interactive kill.  Returns 0."""
        if config.target is not None:
            return self._kill_target(_parse_target(config.target))
        return self._interactive_loop()

    # ------------------------------------------------------------------
    # Direct-target dispatch
    # ------------------------------------------------------------------

    def _kill_target(self, t: _Target) -> int:
        session = resolve_session_id(self._client, t.session)

        if t.kind == "session":
            self._assert_session(session)
            self._client.kill_session(session)
            print(f"  Killed session '{session}'.")

        elif t.kind == "window":
            self._assert_session(session)
            self._client.kill_window(session, t.window)  # type: ignore[arg-type]
            print(f"  Killed window '{session}:{t.window}'.")

        elif t.kind == "pane":
            self._assert_session(session)
            self._client.kill_pane(session, t.window, t.pane)  # type: ignore[arg-type]
            print(f"  Killed pane '{session}:{t.window}.{t.pane}'.")

        elif t.kind == "panes_all":
            self._assert_session(session)
            self._kill_all_panes(session, t.window)  # type: ignore[arg-type]

        return 0

    def _assert_session(self, session: str) -> None:
        if not self._client.session_exists(session):
            raise AppError(f"No tmux session named '{session}'.")

    # ------------------------------------------------------------------
    # Wildcard pane killer
    # ------------------------------------------------------------------

    def _kill_all_panes(self, session: str, window: str) -> None:
        """Kill every pane in *window*, optionally keeping one alive."""
        panes = self._client.list_panes_in_window(session, window)
        if not panes:
            raise AppError(
                f"No panes found in '{session}:{window}' — "
                "does the window exist?"
            )

        print(f"  Window '{session}:{window}' has {len(panes)} pane(s):")
        for i, p in enumerate(panes):
            print(f"    [{i}]  pane {p}")
        print()

        keep_pane: str | None = None

        if len(panes) > 1:
            raw = self._prompt(
                "  Keep one pane open? Enter its index, or 'n' to kill all: "
            ).strip()

            if raw.lower() not in _KEEP_NONE_TOKENS:
                try:
                    idx = int(raw)
                    if 0 <= idx < len(panes):
                        keep_pane = panes[idx]
                    else:
                        print(f"  Index {raw} out of range — killing all panes.")
                except ValueError:
                    print(f"  '{raw}' is not a valid index — killing all panes.")

        if keep_pane is None:
            # No pane to preserve — kill the whole window at once.
            self._client.kill_window(session, window)
            print(f"  Killed window '{session}:{window}' ({len(panes)} pane(s)).")
        else:
            killed = 0
            # Kill highest index first: some tmux versions renumber the
            # remaining panes downward after each kill-pane, which would
            # invalidate a still-queued lower index (or even shift the pane
            # we're keeping onto an index we're about to kill).  Descending
            # order means every kill targets a pane that hasn't moved yet.
            to_kill = sorted((p for p in panes if p != keep_pane), key=int, reverse=True)
            for p in to_kill:
                self._client.kill_pane(session, window, p)
                killed += 1
            print(
                f"  Killed {killed} pane(s) in '{session}:{window}'."
                f"  Kept pane {keep_pane}."
            )

    # ------------------------------------------------------------------
    # Interactive session loop (no target)
    # ------------------------------------------------------------------

    def _interactive_loop(self) -> int:
        sessions = self._client.list_sessions_names()
        if not sessions:
            raise AppError("No tmux sessions are currently open.")

        killed = 0
        first = True

        while sessions:
            if not first:
                print()  # blank line between iterations for readability
            first = False

            print_numbered("Open tmux sessions:", sessions)
            raw = self._prompt(
                f"Kill session (1-{len(sessions)}, or q to quit): "
            ).strip()

            if raw.lower() in _QUIT_TOKENS:
                break

            try:
                idx = int(raw)
            except ValueError:
                print(f"  Invalid selection: '{raw}' — enter a number or 'q'.")
                continue

            if idx < 1 or idx > len(sessions):
                print(f"  Out of range: {raw}.")
                continue

            name = sessions[idx - 1]
            self._client.kill_session(name)
            print(f"  Killed '{name}'.")
            killed += 1

            sessions = self._client.list_sessions_names()

        if not sessions and killed > 0:
            print("No more sessions remain.")

        return 0
