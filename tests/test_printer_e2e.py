"""E2E tests for the 'print' subcommand against a real tmux server."""

import shutil
import subprocess
import time

import pytest

from .conftest import run_ianux, session_index

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not on PATH"),
]


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _echo_in_pane(session: str, marker: str, timeout: float = 3.0) -> None:
    """Echo *marker* in the pane and block until it shows up on screen."""
    _tmux("send-keys", "-t", f"{session}:0.0", f"echo {marker}", "C-m")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = _tmux("capture-pane", "-p", "-t", f"{session}:0.0").stdout
        if out.count(marker) >= 2:  # typed command + its output
            return
        time.sleep(0.05)
    raise AssertionError(f"{marker!r} never appeared in pane")


class TestPrintDirect:
    def test_prints_pane_output_by_name(self, e2e_session_name):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        _echo_in_pane(e2e_session_name, "ianux-print-marker")

        result = run_ianux("p", f"{e2e_session_name}:0.0")
        assert result.returncode == 0, result.stderr
        assert "ianux-print-marker" in result.stdout

    def test_prints_pane_output_by_numeric_id(self, e2e_session_name):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        _echo_in_pane(e2e_session_name, "ianux-id-marker")

        result = run_ianux("print", f"{session_index(e2e_session_name)}:0.0")
        assert result.returncode == 0, result.stderr
        assert "ianux-id-marker" in result.stdout

    def test_scrollback_includes_history(self, e2e_session_name):
        _tmux("new-session", "-d", "-s", e2e_session_name, "-x", "80", "-y", "10")
        _tmux("send-keys", "-t", f"{e2e_session_name}:0.0", "seq 1 50; echo done-$((40+2))", "C-m")
        deadline = time.monotonic() + 3
        while "done-42" not in _tmux("capture-pane", "-p", "-t", f"{e2e_session_name}:0.0").stdout:
            assert time.monotonic() < deadline
            time.sleep(0.05)

        visible = run_ianux("p", f"{e2e_session_name}:0.0").stdout
        full = run_ianux("p", "-s", f"{e2e_session_name}:0.0").stdout
        assert "\n2\n" not in visible
        assert "\n2\n" in full

    def test_missing_session_errors(self, e2e_session_name):
        result = run_ianux("p", f"{e2e_session_name}:0.0")
        assert result.returncode == 1
        assert "does not exist" in result.stderr

    def test_session_only_target_errors(self, e2e_session_name):
        result = run_ianux("p", e2e_session_name)
        assert result.returncode == 1
        assert "expected SESSION:WINDOW.PANE" in result.stderr
