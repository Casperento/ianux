"""Tests for tmux_wrapper.session.SessionManager's pure pane-layout logic.

The session-setup flow itself (create/attach, existing-session prompt,
multi-window, detach, per-pane directories) is covered end-to-end against a
real tmux server in test_session_e2e.py. What's left here is the pane-count
arithmetic and per-pane directory/command distribution in _create_panes and
_initialize_panes: parametrized index-math that would require a real tmux
session per pane count to re-verify at E2E cost, for no added confidence
over asserting the exact call sequence directly.
"""

from pathlib import Path

from ..session import SessionManager


# ---------------------------------------------------------------------------
# SessionManager._create_panes — pane creation logic
# ---------------------------------------------------------------------------


class TestCreatePanes:
    """Unit-test _create_panes in isolation via mock_client."""

    def _run(self, mock_client, pane_count: int, window: str = "0"):
        mock_client.list_panes.return_value = ["0", "1", "2", "3"]
        manager = SessionManager(mock_client)
        manager._create_panes("sess", window, pane_count)

    def test_single_pane_no_splits(self, mock_client):
        self._run(mock_client, 1)
        mock_client.split_window.assert_not_called()
        mock_client.select_layout.assert_called_once_with("sess", "tiled", window="0")

    def test_four_panes_three_splits_then_tiled(self, mock_client):
        self._run(mock_client, 4)
        assert mock_client.split_window.call_count == 3  # 3 extra after initial pane
        mock_client.select_layout.assert_called_with("sess", "tiled", window="0")

    def test_six_panes_uses_phase2(self, mock_client):
        """6 panes: 3 phase-1 splits (→4 panes) + 2 phase-2 splits."""
        self._run(mock_client, 6)
        # Phase-1: split_window called 3 times (panes 1,2,3)
        # Phase-2: split_window called 2 more times
        assert mock_client.split_window.call_count == 5

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
    def test_per_pane_directories_and_commands_in_order(self, mock_client):
        mock_client.list_panes.return_value = ["0", "1", "2"]
        dirs = [Path("/work/a"), Path("/work/b"), Path("/work/c")]
        SessionManager(mock_client)._initialize_panes("sess", "0", dirs, ["cmd0", "cmd1", "cmd2"])
        sent = [c.args[3] for c in mock_client.send_keys.call_args_list]
        assert sent == [
            "cd /work/a && cmd0",
            "cd /work/b && cmd1",
            "cd /work/c && cmd2",
        ]

    def test_shorter_lists_reuse_last_entry(self, mock_client):
        """Fewer dirs/commands than panes → the last entry fills the remaining panes."""
        mock_client.list_panes.return_value = ["0", "1", "2"]
        SessionManager(mock_client)._initialize_panes(
            "sess", "0", [Path("/x"), Path("/y")], ["alpha"]
        )
        sent = [c.args[3] for c in mock_client.send_keys.call_args_list]
        assert sent == ["cd /x && alpha", "cd /y && alpha", "cd /y && alpha"]

    def test_empty_init_command_sends_bare_cd(self, mock_client):
        """An empty init_command (as written by 'dump') must not leave a
        dangling '&&' — only the cd should be sent."""
        mock_client.list_panes.return_value = ["0"]
        manager = SessionManager(mock_client)
        manager._initialize_panes("sess", "0", [Path("/work/dir")], [""])
        calls = mock_client.send_keys.call_args_list
        assert len(calls) == 1
        assert calls[0].args[3] == "cd /work/dir"
        assert "&&" not in calls[0].args[3]

    def test_non_default_window_threaded_through(self, mock_client):
        mock_client.list_panes.return_value = ["0"]
        manager = SessionManager(mock_client)
        manager._initialize_panes("sess", "2", [Path("/work")], ["bash"])
        mock_client.list_panes.assert_called_with("sess", window="2")
        assert mock_client.send_keys.call_args.args[1] == "2"
