"""SessionAttacher — list open sessions and attach to one interactively.

Two usage modes:

  Interactive (session_name is None)
      Lists all open tmux sessions with numeric IDs (1-based, matching the
      'list' subcommand), prompts the user to choose one, then attaches.

  Direct (session_name is provided)
      Accepts a tmux-style address: ``SESSION``, ``SESSION:WINDOW`` or
      ``SESSION:WINDOW.PANE`` (mirrors the 'kill' subcommand's target
      format).  SESSION may be a literal name or one of the numeric IDs
      shown by 'list'/the picker; WINDOW and PANE are tmux's own indices,
      as displayed in 'list'.  Validates the session exists and attaches
      immediately, skipping the picker.
"""

from typing import Callable

from .config import AttachConfig
from .exceptions import AppError
from .killer import _Target, _parse_target, resolve_session_id
from .picker import pick_session
from .tmux import TmuxClient


class SessionAttacher:
    """Handles the 'attach' subcommand: direct-target and interactive modes."""

    def __init__(
        self,
        client: TmuxClient,
        prompt_fn: Callable[[str], str] = input,
    ) -> None:
        self._client = client
        self._prompt = prompt_fn

    def attach(self, config: AttachConfig) -> int:
        if config.session_name is not None:
            return self._attach_direct(config.session_name)
        return self._attach_interactive()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _attach_direct(self, address: str) -> int:
        t = _parse_target(address)
        session = resolve_session_id(self._client, t.session)
        if not self._client.session_exists(session):
            raise AppError(f"Session '{session}' does not exist.")
        self._client.attach(self._build_target(session, t))
        return 0

    def _build_target(self, session: str, t: _Target) -> str:
        """Combine the resolved session name with the window/pane part of *t*."""
        if t.kind == "pane":
            return f"{session}:{t.window}.{t.pane}"
        if t.kind in ("window", "panes_all"):
            return f"{session}:{t.window}"
        return session

    def _attach_interactive(self) -> int:
        self._client.attach(pick_session(self._client, self._prompt))
        return 0
