"""E2E tests for the 'run' subcommand against a real tmux server.

The --kill path spawns a real double-fork daemon (no mocking of _daemonize
or time.sleep possible from outside the subprocess) that polls the real
pane, writes real files, and kills the real session — so this is the
clearest case in the whole suite of "the real implementation is the only
way to prove this actually works."
"""

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from .conftest import run_ianux

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not on PATH"),
]


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _session_exists(name: str) -> bool:
    return _tmux("has-session", "-t", name).returncode == 0


def _capture_pane(name: str) -> str:
    return _tmux("capture-pane", "-p", "-S", "-", "-t", f"{name}:0.0").stdout


def _wait_until(predicate, timeout: float, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestRunWithoutKill:
    def test_sends_commands_in_order_and_leaves_session_running(self, e2e_session_name):
        result = run_ianux(
            "run", "--session", e2e_session_name, "echo first", "echo second",
        )
        assert result.returncode == 0, result.stderr
        assert "2 commands" in result.stdout

        assert _wait_until(
            lambda: "second" in _capture_pane(e2e_session_name), timeout=2.0
        )
        output = _capture_pane(e2e_session_name)
        # Both ran, in order — "first" appears before "second".
        assert output.index("first") < output.index("second")
        assert _session_exists(e2e_session_name)

    def test_raises_when_session_already_exists(self, e2e_session_name):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        result = run_ianux("run", "--session", e2e_session_name, "echo hi")
        assert result.returncode != 0
        assert "already exists" in result.stderr
        assert _session_exists(e2e_session_name)  # untouched, not recreated


class TestRunWithKill:
    def test_monitor_daemon_captures_output_and_kills_session(self, e2e_session_name):
        result = run_ianux(
            "run", "--session", e2e_session_name, "--kill", "echo kill-path-marker",
        )
        assert result.returncode == 0, result.stderr
        assert "running in background" in result.stdout

        out_path = f"/tmp/{e2e_session_name}.capture-pane"
        log_path = f"/tmp/{e2e_session_name}.monitor.log"

        # The real daemon polls every _POLL_INTERVAL_S (2s); give it a few cycles.
        assert _wait_until(lambda: not _session_exists(e2e_session_name), timeout=10.0)
        assert _wait_until(lambda: _read_if_exists(log_path) is not None, timeout=2.0)

        assert "kill-path-marker" in _read_if_exists(out_path)
        assert "[DONE]" in _read_if_exists(log_path)

    def test_custom_output_path_is_honored(self, e2e_session_name, tmp_path):
        custom_out = tmp_path / "custom.capture"
        result = run_ianux(
            "run", "--session", e2e_session_name, "--kill",
            "-o", str(custom_out), "echo custom-path-marker",
        )
        assert result.returncode == 0, result.stderr
        assert str(custom_out) in result.stdout

        assert _wait_until(lambda: not _session_exists(e2e_session_name), timeout=10.0)
        assert _wait_until(lambda: custom_out.exists(), timeout=2.0)
        assert "custom-path-marker" in custom_out.read_text()


def _read_if_exists(path: str) -> str | None:
    p = Path(path)
    return p.read_text() if p.exists() else None
