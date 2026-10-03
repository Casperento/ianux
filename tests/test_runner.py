"""Tests for tmw.runner that don't fit test_runner_e2e.py.

The happy paths (commands sent in order, --kill spawns a real daemon that
captures output and kills the session, already-exists error, custom output
path) are covered end-to-end against a real tmux server and a real
double-fork daemon in test_runner_e2e.py.

What's left here needs either a genuine race (the session disappearing or
an unexpected exception mid-poll) or an absurd real wait (the 1-hour
timeout) to reproduce for real — both impractical to force deterministically
against a live tmux server, so they stay as direct, mocked tests of
_wait_for_done/_monitor_loop. The PTY-echo sentinel-matching regression test
is kept too: it's the documented core invariant of the whole polling
design, and asserting it directly against canned capture_pane text is both
faster and more deterministic than depending on real terminal-echo timing.
"""

import time
from unittest.mock import patch

import pytest

from tmw.exceptions import AppError
from tmw.runner import SessionRunner, _monitor_loop, _POLL_TIMEOUT_S, _SENTINEL


class TestMonitorLoop:
    def test_app_error_writes_error_log(self, mock_client, tmp_path):
        """AppError in _wait_for_done → [ERROR] written to log, no output file."""
        mock_client.session_exists.return_value = False  # triggers "disappeared"
        out_path = tmp_path / "out.capture-pane"
        log_path = tmp_path / "out.monitor.log"

        _monitor_loop(mock_client, "gone", "0", "0", out_path, log_path)

        assert not out_path.exists()
        log = log_path.read_text()
        assert "[ERROR]" in log
        assert "gone" in log

    def test_unexpected_exception_writes_error_log(self, mock_client, tmp_path):
        """Unexpected exception → [ERROR] in log, process does not crash."""
        mock_client.session_exists.side_effect = RuntimeError("boom")
        out_path = tmp_path / "out.capture-pane"
        log_path = tmp_path / "out.monitor.log"

        _monitor_loop(mock_client, "s", "0", "0", out_path, log_path)

        log = log_path.read_text()
        assert "[ERROR]" in log
        assert "boom" in log


class TestWaitForDone:
    def test_wait_for_done_ignores_terminal_echo_of_sentinel_cmd(self, mock_client):
        """The command echo (``echo <sentinel>``) must NOT trigger early return.

        This is the core regression test for the PTY-echo race: when send_keys
        fires, the PTY driver echoes the typed text instantly.  That echo line
        contains the sentinel as a substring but is NOT a standalone sentinel
        line, so exact-line matching must keep polling until the real output
        appears.
        """
        mock_client.session_exists.return_value = True
        mock_client.capture_pane.side_effect = [
            f"make output\necho {_SENTINEL}\n",   # terminal echo only — keep polling
            f"make output\necho {_SENTINEL}\n{_SENTINEL}\n",  # real output — return
        ]

        runner = SessionRunner(mock_client)
        with patch("tmw.runner.time.sleep"):
            result = runner._wait_for_done("s", "0", "0")

        assert mock_client.capture_pane.call_count == 2
        assert _SENTINEL not in result
        assert "make output" in result

    def test_wait_for_done_strips_sentinel_lines(self, mock_client):
        """Both the sentinel output line and the echoed command line are stripped."""
        mock_client.session_exists.return_value = True
        mock_client.capture_pane.return_value = (
            f"line1\necho {_SENTINEL}\nline2\n{_SENTINEL}\nline3\n"
        )

        runner = SessionRunner(mock_client)
        with patch("tmw.runner.time.sleep"):
            result = runner._wait_for_done("s", "0", "0")

        assert _SENTINEL not in result
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_wait_for_done_session_disappears(self, mock_client):
        """AppError is raised promptly if the session is killed externally."""
        mock_client.session_exists.return_value = False
        runner = SessionRunner(mock_client)
        with pytest.raises(AppError, match="disappeared"):
            runner._wait_for_done("gone", "0", "0")
        mock_client.capture_pane.assert_not_called()

    def test_wait_for_done_timeout(self, mock_client):
        """AppError is raised when the deadline passes."""
        mock_client.session_exists.return_value = True
        mock_client.capture_pane.return_value = "still running\n"

        runner = SessionRunner(mock_client)
        start = time.monotonic()
        with patch(
            "tmw.runner.time.monotonic",
            side_effect=[start, start + _POLL_TIMEOUT_S + 1],
        ):
            with patch("tmw.runner.time.sleep"):
                with pytest.raises(AppError, match="Timed out"):
                    runner._wait_for_done("s", "0", "0")
