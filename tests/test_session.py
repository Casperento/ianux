"""Tests for ianux.session.SessionManager's pure pane-layout logic.

The session-setup flow itself (create/attach, existing-session prompt,
multi-window, detach, per-pane directories) is covered end-to-end against a
real tmux server in test_session_e2e.py. What's left here is the pane-count
arithmetic and per-pane directory/command distribution in _create_panes and
_initialize_panes: parametrized index-math that would require a real tmux
session per pane count to re-verify at E2E cost, for no added confidence
over asserting the exact call sequence directly.
"""

from pathlib import Path

from ianux.config import SessionConfig, WindowConfig
from ianux.session import SessionManager


# ---------------------------------------------------------------------------
# SessionManager._create_panes — pane creation logic
# ---------------------------------------------------------------------------


class TestCreatePanes:
    """Unit-test _create_panes in isolation via mock_client."""

    def _run(self, mock_client, pane_count: int, window: str = "0"):
        mock_client.list_panes.return_value = (
            ["0", "1"] if pane_count <= 4 else ["0", "1", "2", "3"]
        )
        manager = SessionManager(mock_client)
        manager._create_panes("sess", window, pane_count)

    def test_single_pane_no_splits(self, mock_client):
        self._run(mock_client, 1)
        mock_client.split_window.assert_not_called()
        mock_client.select_layout.assert_not_called()

    def test_four_panes_split_perpendicularly_into_equal_quadrants(self, mock_client):
        self._run(mock_client, 4)
        assert mock_client.split_window.call_count == 3
        calls = mock_client.split_window.call_args_list
        assert calls[0].kwargs == {"window": "0", "direction": "horizontal"}
        assert calls[1].kwargs == {
            "window": "0", "target_pane": "1", "direction": "vertical"
        }
        assert calls[2].kwargs == {
            "window": "0", "target_pane": "0", "direction": "vertical"
        }
        mock_client.select_layout.assert_not_called()

    def test_six_panes_uses_phase2(self, mock_client):
        """6 panes: 3 phase-1 splits (→4 panes) + 2 phase-2 splits."""
        self._run(mock_client, 6)
        # Phase-1: split_window called 3 times (panes 1,2,3)
        # Phase-2: split_window called 2 more times
        assert mock_client.split_window.call_count == 5

    def test_each_split_starts_in_the_directory_of_its_final_index(self, mock_client):
        """tmux inserts a split pane right after its target, so the 4th pane
        created ends up at index 1: it must get directory 1, not directory 3."""
        dirs = [Path(f"/work/{n}") for n in range(4)]
        mock_client.list_panes.return_value = ["0", "1"]
        SessionManager(mock_client)._create_panes("sess", "0", 4, directories=dirs)
        started = [c.kwargs["start_directory"] for c in mock_client.split_window.call_args_list]
        # Creation order → final index is [0, 2, 3, 1] (see _creation_to_index).
        assert started == [dirs[2], dirs[3], dirs[1]]

    def test_non_default_window_threaded_through(self, mock_client):
        self._run(mock_client, 6, window="3")
        for c in mock_client.split_window.call_args_list:
            assert c.kwargs["window"] == "3"
        for c in mock_client.select_layout.call_args_list:
            assert c.kwargs["window"] == "3"
        mock_client.list_panes.assert_called_with("sess", window="3")


# ---------------------------------------------------------------------------
# SessionManager._initialize_panes
# ---------------------------------------------------------------------------


class TestInitializePanes:
    def test_per_pane_commands_in_order_without_cd(self, mock_client):
        mock_client.list_panes.return_value = ["0", "1", "2"]
        SessionManager(mock_client)._initialize_panes("sess", "0", ["cmd0", "cmd1", "cmd2"])
        sent = [c.args[3] for c in mock_client.send_keys.call_args_list]
        assert sent == ["cmd0", "cmd1", "cmd2"]

    def test_shorter_lists_reuse_last_entry(self, mock_client):
        """Fewer commands than panes → the last entry fills the remaining panes."""
        mock_client.list_panes.return_value = ["0", "1", "2"]
        SessionManager(mock_client)._initialize_panes("sess", "0", ["alpha", "beta"])
        sent = [c.args[3] for c in mock_client.send_keys.call_args_list]
        assert sent == ["alpha", "beta", "beta"]

    def test_empty_init_command_sends_nothing(self, mock_client):
        """An empty init_command (as written by 'dump') sends no keys at all:
        the pane already starts in its directory."""
        mock_client.list_panes.return_value = ["0"]
        SessionManager(mock_client)._initialize_panes("sess", "0", [""])
        mock_client.send_keys.assert_not_called()

    def test_non_default_window_threaded_through(self, mock_client):
        mock_client.list_panes.return_value = ["0"]
        manager = SessionManager(mock_client)
        manager._initialize_panes("sess", "2", ["bash"])
        mock_client.list_panes.assert_called_with("sess", window="2")
        assert mock_client.send_keys.call_args.args[1] == "2"


class TestWindowLayout:
    def test_layout_applied_after_panes_are_created(self, mock_client, tmp_path):
        mock_client.session_exists.return_value = False
        mock_client.list_panes.return_value = ["0", "1", "2"]
        config = SessionConfig(
            windows=[WindowConfig(
                panes=3, directories=[tmp_path], init_commands=["x"], layout="main-vertical",
            )],
            session_name="sess",
            detach=True,
        )

        SessionManager(mock_client).setup(config, resolver=None)

        names = [c[0] for c in mock_client.method_calls]
        last_split = max(i for i, n in enumerate(names) if n == "split_window")
        layout_call = names.index("select_layout")
        assert layout_call > last_split
        assert mock_client.select_layout.call_args.args[:2] == ("sess", "main-vertical")
