"""E2E tests for the 'attach' subcommand against a real tmux server.

Attaching needs a real terminal (TmuxClient.attach uses capture_output=False),
so these tests run the CLI on a pty via run_tmw_attached() and verify the
real attach happened (and landed on the right window/pane) with independent
`tmux` queries, then detach by terminating the client process.
"""

import shutil
import subprocess
import time

import pytest

from .conftest import run_tmw, run_tmw_attached, session_index

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not on PATH"),
]


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _create_session(name: str, windows: int = 1, panes_in_window_0: int = 1) -> None:
    _tmux("new-session", "-d", "-s", name)
    for _ in range(panes_in_window_0 - 1):
        _tmux("split-window", "-t", f"{name}:0")
    for _ in range(windows - 1):
        _tmux("new-window", "-t", f"{name}:")
    # Deterministic starting point: window 0, pane 0 active, regardless of
    # whatever new-window/split-window left active.
    _tmux("select-window", "-t", f"{name}:0")
    _tmux("select-pane", "-t", f"{name}:0.0")


def _is_attached(session: str) -> bool:
    return _tmux("display-message", "-p", "-t", session, "#{session_attached}").stdout.strip() == "1"


def _current_window(session: str) -> str:
    return _tmux("display-message", "-p", "-t", session, "#{window_index}").stdout.strip()


def _current_pane(session: str) -> str:
    return _tmux("display-message", "-p", "-t", session, "#{pane_index}").stdout.strip()


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestAttachDirect:
    def test_attaches_by_literal_session_name(self, e2e_session_name):
        _create_session(e2e_session_name)
        attached = run_tmw_attached("attach", e2e_session_name)
        try:
            assert _wait_until(lambda: _is_attached(e2e_session_name))
        finally:
            attached.detach()

    def test_attaches_by_numeric_id(self, e2e_session_name):
        """Resolves the numeric ID shown by 'list' back to this session's real name."""
        _create_session(e2e_session_name)
        idx = session_index(e2e_session_name)
        attached = run_tmw_attached("attach", str(idx))
        try:
            assert _wait_until(lambda: _is_attached(e2e_session_name))
        finally:
            attached.detach()

    def test_attaches_directly_to_a_window_target(self, e2e_session_name):
        _create_session(e2e_session_name, windows=2)
        attached = run_tmw_attached("attach", f"{e2e_session_name}:1")
        try:
            assert _wait_until(lambda: _current_window(e2e_session_name) == "1")
        finally:
            attached.detach()

    def test_attaches_directly_to_a_pane_target(self, e2e_session_name):
        _create_session(e2e_session_name, panes_in_window_0=2)
        attached = run_tmw_attached("attach", f"{e2e_session_name}:0.1")
        try:
            assert _wait_until(lambda: _current_pane(e2e_session_name) == "1")
        finally:
            attached.detach()

    def test_raises_when_session_missing(self, e2e_session_name):
        # e2e_session_name is unique and never created here — guaranteed absent.
        result = run_tmw("attach", e2e_session_name)
        assert result.returncode != 0
        assert "does not exist" in result.stderr


class TestAttachInteractive:
    def test_picks_and_attaches_by_computed_index(self, e2e_session_name):
        _create_session(e2e_session_name)
        idx = session_index(e2e_session_name)
        attached = run_tmw_attached("attach", input=f"{idx}\n")
        try:
            assert _wait_until(lambda: _is_attached(e2e_session_name))
        finally:
            attached.detach()
