"""Print a pane's current output to stdout without attaching.

PanePrinter handles the 'print' subcommand.  The target is a fully-specified
pane address — ``NAME|ID:WINDOW.PANE``, or ``WINDOW.PANE`` for the session
you last interacted with — parsed with the same helpers as 'attach'/'kill'.
"""

import sys

from .config import PrintConfig
from .exceptions import AppError
from .killer import _parse_target, resolve_session_id
from .tmux import TmuxClient


class PanePrinter:
    """Capture a single pane and write its contents to stdout."""

    def __init__(self, client: TmuxClient) -> None:
        self._client = client

    def print(self, config: PrintConfig) -> int:
        """Write the target pane's contents to stdout and return 0."""
        raw = config.target
        # Bare "W.P" has no session part: it means the last-used session.
        if ":" not in raw and "." in raw:
            raw = f":{raw}"

        target = _parse_target(raw)
        if target.kind != "pane" or not target.window or not target.pane:
            raise AppError(
                f"Invalid target '{config.target}': expected "
                "SESSION:WINDOW.PANE or WINDOW.PANE."
            )

        if target.session:
            session = resolve_session_id(self._client, target.session)
        else:
            session = self._client.current_session_name()

        if not self._client.session_exists(session):
            raise AppError(f"Session '{session}' does not exist.")

        output = self._client.capture_pane(
            session, target.window, target.pane, scrollback=config.scrollback
        )
        # tmux pads the visible area with empty lines up to the pane height.
        output = output.rstrip()
        if output:
            sys.stdout.write(output + "\n")
        return 0
