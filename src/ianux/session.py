"""Session orchestration.

SessionManager is the single place that knows the full session-setup
sequence.  It delegates every tmux call to TmuxClient (Facade) and every
directory decision to a DirectoryResolver (Strategy), keeping its own
responsibility to orchestration only.
"""

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

        self._client.new_session(
            session_name,
            window_name=first_window.name,
            start_directory=_directory_for(first_directories, 0),
        )
        self._create_panes(
            session_name, "0", first_window.panes, first_window.split_direction,
            first_directories,
        )
        self._apply_layout(session_name, "0", first_window.layout)
        self._initialize_panes(session_name, "0", first_window.init_commands)

        for window in config.windows[1:]:
            window_directories = self._resolve_directories(window.directories)
            window_index = self._client.new_window(
                session_name,
                name=window.name,
                start_directory=_directory_for(window_directories, 0),
            )
            self._create_panes(
                session_name, window_index, window.panes, window.split_direction,
                window_directories,
            )
            self._apply_layout(session_name, window_index, window.layout)
            self._initialize_panes(session_name, window_index, window.init_commands)

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
        directories: list[Path] | None = None,
    ) -> None:
        """Create panes in an alternating split pattern.

        The first split follows *split_direction*. For pane three, split the
        second pane across the other axis; for pane four, split the original
        pane across that same axis. This makes a balanced 2×2 grid. Larger
        counts use that grid as a base and return to tmux's tiled layout while
        subdividing its panes to keep further splits viable.

        Each new pane starts in its own entry of *directories* (tmux ``-c``),
        chosen by the pane index it ends up with once every split is done (see
        ``_creation_to_index``), so directory N always lands on pane N.
        """
        if pane_count <= 1:
            return

        directories = directories or []
        final_index = _creation_to_index(pane_count)

        def start_dir(created: int) -> Path | None:
            return _directory_for(directories, final_index[created])

        other_direction = "horizontal" if split_direction == "vertical" else "vertical"

        # The first split always divides the original pane in half.
        self._client.split_window(
            session_name, 2, window=window, direction=split_direction,
            **_dir_kwarg(start_dir(1)),
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
            direction=other_direction, **_dir_kwarg(start_dir(2)),
        )

        if pane_count == 3:
            return

        # Split the original pane across the same axis to complete four equal
        # quadrants.
        self._client.split_window(
            session_name, 4, window=window, target_pane=first_pane,
            direction=other_direction, **_dir_kwarg(start_dir(3)),
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
                **_dir_kwarg(start_dir(4 + i)),
            )
            self._client.select_layout(session_name, "tiled", window=window)

    def _apply_layout(self, session_name: str, window: str, layout: str | None) -> None:
        """Apply the window's configured tmux *layout*, if any.

        A raw layout string whose pane count doesn't match the window makes
        tmux fail; ``select_layout`` turns that into an AppError, stopping
        the setup rather than silently keeping a different layout.
        """
        if layout is not None:
            self._client.select_layout(session_name, layout, window=window)

    def _initialize_panes(
        self,
        session_name: str,
        window: str,
        init_commands: list[str],
    ) -> None:
        """Send each pane its init command; panes already start in their directory.

        *init_commands* is indexed by pane position. When it is shorter than
        the number of panes, its last entry is reused for the remaining panes
        so that a single-entry list applies uniformly (the common case). An
        empty command (as written by 'dump') sends nothing.
        """
        if not any(cmd.strip() for cmd in init_commands):
            return
        for i, pane_index in enumerate(self._client.list_panes(session_name, window=window)):
            cmd = init_commands[min(i, len(init_commands) - 1)]
            if cmd.strip():
                self._client.send_keys(session_name, window, pane_index, cmd)


def _directory_for(directories: list[Path], index: int) -> Path | None:
    """Return the directory for pane *index*, reusing the last entry; None if empty."""
    if not directories:
        return None
    return directories[min(index, len(directories) - 1)]


def _dir_kwarg(directory: Path | None) -> dict:
    """``{"start_directory": directory}`` when set, else nothing (keeps call args minimal)."""
    return {} if directory is None else {"start_directory": directory}


def _creation_to_index(pane_count: int) -> list[int]:
    """Return the final pane index (position) of each pane, in creation order.

    Replays ``SessionManager._create_panes``'s split sequence on a plain
    list. tmux inserts a new pane directly after its split target in index
    order, renumbering the panes behind it, so creation order and final index
    differ (with 4 panes, the 4th pane created ends up at index 1). The
    split direction never affects the order, only the geometry.

    Targets are replayed exactly as ``_create_panes`` passes them: index
    strings read once from ``list_panes``, so beyond 4 panes the round-robin
    targets the pane *currently* at that index, not the original base pane.
    """
    panes = [0]  # creation numbers, in pane-index order

    def split(target_position: int) -> None:
        panes.insert(target_position + 1, len(panes))

    if pane_count >= 2:
        split(0)  # active pane: the window's only pane
    if pane_count >= 3:
        split(1)  # the second pane (pane_indices[-1] of a 2-pane window)
    if pane_count >= 4:
        split(0)  # the original pane
    for i in range(pane_count - 4):
        split(i % 4)  # base_indices[i % 4], read before these splits

    final = [0] * pane_count
    for position, created in enumerate(panes):
        final[created] = position
    return final
