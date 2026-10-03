"""Session orchestration.

SessionManager is the single place that knows the full session-setup
sequence.  It delegates every tmux call to TmuxClient (Facade) and every
directory decision to a DirectoryResolver (Strategy), keeping its own
responsibility to orchestration only.
"""

import shlex
from pathlib import Path

from .config import SessionConfig
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
        self._create_panes(session_name, "0", first_window.panes)
        self._initialize_panes(session_name, "0", first_directories, first_window.init_commands)

        for window in config.windows[1:]:
            window_index = self._client.new_window(session_name, name=window.name)
            window_directories = self._resolve_directories(window.directories)
            self._create_panes(session_name, window_index, window.panes)
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

    # Number of base panes that form the first tiled grid.
    # Extra panes are added by sub-dividing those base panes rather than by
    # continuing to split the window sequentially, which would produce an
    # increasingly narrow column of panes instead of a balanced grid.
    _BASE_PANE_COUNT = 4

    def _create_panes(self, session_name: str, window: str, pane_count: int) -> None:
        """Create *pane_count* panes using a two-phase strategy.

        Phase 1 — base grid (≤ _BASE_PANE_COUNT panes)
            Split the window sequentially and apply a tiled layout.  For
            requests of four panes or fewer this is the only phase.

        Phase 2 — subdivide base panes (pane_count > _BASE_PANE_COUNT)
            Query the real pane indices that tmux assigned after the tiled
            layout, then split those base panes in round-robin order until
            the total reaches *pane_count*.  Tiled is re-applied after every
            individual split so that every pane stays at maximum available
            size — without this rebalance, panes squeezed by earlier splits
            can fall below tmux's minimum splittable height.

        Example — 6 panes:
            Phase 1 → panes 0-3 in a 2×2 grid.
            Phase 2 → split pane 0 (→ pane 4), tiled; split pane 1 (→ pane 5), tiled.
            Result  → 6 panes, two columns of 3.
        """
        base = min(pane_count, self._BASE_PANE_COUNT)

        # ── Phase 1: base grid ──────────────────────────────────────────────
        for n in range(1, base):
            self._client.split_window(session_name, n, window=window)
        self._client.select_layout(session_name, "tiled", window=window)

        if pane_count <= self._BASE_PANE_COUNT:
            return

        # ── Phase 2: sub-divide base panes ─────────────────────────────────
        # Fetch real pane indices *after* the layout so we target the correct
        # panes even if tmux has reordered them internally.
        base_indices = self._client.list_panes(session_name, window=window)
        extra = pane_count - base
        for i in range(extra):
            target = base_indices[i % len(base_indices)]
            self._client.split_window(session_name, base + 1 + i, window=window, target_pane=target)
            # Re-apply tiled immediately so the next targeted pane has the
            # maximum available height rather than the squeezed height left
            # over from the split that just happened.
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
