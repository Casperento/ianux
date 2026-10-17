"""Session orchestration.

SessionManager is the single place that knows the full session-setup
sequence.  It delegates every tmux call to TmuxClient (Facade) and every
directory decision to a DirectoryResolver (Strategy), keeping its own
responsibility to orchestration only.
"""

import shlex
from pathlib import Path

from .config import _DEFAULT_SPLIT_DIRECTION, SessionConfig
from .directory import DirectoryResolver, ExplicitResolver
from .tmux import TmuxClient


class SessionManager:
    """Orchestrates the 'session' subcommand: create panes, then attach."""

    def __init__(self, client: TmuxClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setup(self, config: SessionConfig, resolver: DirectoryResolver) -> int:
        """Run the full session-setup flow.  Returns 0 on success."""
        first_window = config.windows[0]

        # Build window 0's per-pane directory list.
        # When explicit directories are given, validate and resolve all of them.
        # When the list is empty, fall back to the resolver (interactive picker
        # or single explicit dir — whichever build_resolver chose).
        if first_window.directories:
            first_directories = self._resolve_directories(first_window.directories)
        else:
            first_directories = [resolver.resolve()]

        session_name = self._unique_session_name(config.session_name)

        self._client.new_session(session_name, window_name=first_window.name)
        self._create_panes(
            session_name, "0", first_window.panes, first_window.split_direction
        )
        self._initialize_panes(session_name, "0", first_directories, first_window.init_commands)

        for window in config.windows[1:]:
            window_index = self._client.new_window(session_name, name=window.name)
            window_directories = self._resolve_directories(window.directories)
            self._create_panes(
                session_name, window_index, window.panes, window.split_direction
            )
            self._initialize_panes(session_name, window_index, window_directories, window.init_commands)

        if len(config.windows) > 1:
            self._client.select_window(session_name, "0")

        self._attach_or_confirm(session_name, config.detach)
        return 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_directories(self, directories: list[Path]) -> list[Path]:
        """Validate and resolve each raw directory via ExplicitResolver."""
        return [ExplicitResolver(d).resolve() for d in directories]

    def _unique_session_name(self, name: str) -> str:
        """Return *name*, or the first "<name>-N" (N >= 1) not already in use."""
        if not self._client.session_exists(name):
            return name
        n = 1
        while self._client.session_exists(f"{name}-{n}"):
            n += 1
        return f"{name}-{n}"

    def _attach_or_confirm(self, session_name: str, detach: bool) -> None:
        """Attach to *session_name*, or print a confirmation when detached."""
        if detach:
            print(f"Session '{session_name}' ready (detached).")
        else:
            self._client.attach(session_name)

    def _create_panes(
        self,
        session_name: str,
        window: str,
        pane_count: int,
        split_direction: str = _DEFAULT_SPLIT_DIRECTION,
    ) -> None:
        """Create panes in an alternating split pattern.

        The first split follows *split_direction*. For pane three, split the
        second pane across the other axis; for pane four, split the original
        pane across that same axis. This makes a balanced 2×2 grid. Larger
        counts use that grid as a base and return to tmux's tiled layout while
        subdividing its panes to keep further splits viable.
        """
        if pane_count <= 1:
            return

        other_direction = "horizontal" if split_direction == "vertical" else "vertical"

        # The first split always divides the original pane in half.
        self._client.split_window(
            session_name, 2, window=window, direction=split_direction
        )
        if pane_count == 2:
            layout = "even-horizontal" if split_direction == "vertical" else "even-vertical"
            self._client.select_layout(session_name, layout, window=window)
            return

        # Split the newly-created pane for pane three, leaving the first pane
        # at half the window and making the other two panes quarter-sized.
        pane_indices = self._client.list_panes(session_name, window=window)
        first_pane = pane_indices[0]
        second_pane = pane_indices[-1]
        self._client.split_window(
            session_name, 3, window=window, target_pane=second_pane,
            direction=other_direction,
        )

        if pane_count == 3:
            return

        # Split the original pane across the same axis to complete four equal
        # quadrants.
        self._client.split_window(
            session_name, 4, window=window, target_pane=first_pane,
            direction=other_direction,
        )
        if pane_count == 4:
            return

        # For larger counts, rebalance the four-pane base before splitting
        # each base pane in round-robin order. Re-tiling after each split
        # keeps subsequent panes large enough to split.
        self._client.select_layout(session_name, "tiled", window=window)
        base_indices = self._client.list_panes(session_name, window=window)
        for i in range(pane_count - 4):
            target = base_indices[i % len(base_indices)]
            self._client.split_window(
                session_name,
                5 + i,
                window=window,
                target_pane=target,
                direction=split_direction,
            )
            self._client.select_layout(session_name, "tiled", window=window)

    def _initialize_panes(
        self,
        session_name: str,
        window: str,
        directories: list[Path],
        init_commands: list[str],
    ) -> None:
        """Send a per-pane cd + init command to every pane.

        Both *directories* and *init_commands* are indexed by pane position.
        When either list is shorter than the number of panes, its last entry
        is reused for all remaining panes so that a single-entry list applies
        uniformly (the common case).
        """
        for i, pane_index in enumerate(self._client.list_panes(session_name, window=window)):
            target_dir = directories[min(i, len(directories) - 1)]
            cmd = init_commands[min(i, len(init_commands) - 1)]
            cd = f"cd {shlex.quote(str(target_dir))}"
            command = f"{cd} && {cmd}" if cmd.strip() else cd
            self._client.send_keys(session_name, window, pane_index, command)
