"""E2E tests for the 'kill' subcommand against a real tmux server.

Direct-target kills (session/window/pane/wildcard) never touch a terminal,
so these run as plain subprocess calls via run_tmw(). The interactive loop
lists *every* open session on the server — this machine has the developer's
own real sessions alongside the test's — so it always drives the prompt with
session_index()'s computed index, never a hardcoded one, to guarantee it can
never select someone else's session.
"""

import shutil
import subprocess

import pytest

from .conftest import run_tmw, session_index

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


def _session_exists(name: str) -> bool:
    return _tmux("has-session", "-t", name).returncode == 0


def _window_indices(session: str) -> list[str]:
    return [l for l in _tmux("list-windows", "-t", session, "-F", "#{window_index}").stdout.splitlines() if l]


def _pane_indices(session: str, window: str = "0") -> list[str]:
    return [
        l for l in _tmux("list-panes", "-t", f"{session}:{window}", "-F", "#{pane_index}").stdout.splitlines() if l
    ]


def _pane_ids(session: str, window: str = "0") -> list[str]:
    """Pane IDs (``%N``, globally stable) — unlike pane_index, these survive
    the renumbering tmux does on the *other* panes after a kill-pane, so
    they're the only reliable way to check which physical pane survived."""
    return [
        l for l in _tmux("list-panes", "-t", f"{session}:{window}", "-F", "#{pane_id}").stdout.splitlines() if l
    ]


class TestKillDirectTarget:
    def test_kills_entire_session(self, e2e_session_name):
        _create_session(e2e_session_name)
        result = run_tmw("kill", e2e_session_name)
        assert result.returncode == 0, result.stderr
        assert not _session_exists(e2e_session_name)
        assert e2e_session_name in result.stdout

    def test_kills_one_window_leaves_the_rest(self, e2e_session_name):
        _create_session(e2e_session_name, windows=2)
        result = run_tmw("kill", f"{e2e_session_name}:1")
        assert result.returncode == 0, result.stderr
        assert _window_indices(e2e_session_name) == ["0"]

    def test_kills_one_pane_leaves_the_rest(self, e2e_session_name):
        _create_session(e2e_session_name, panes_in_window_0=2)
        panes_before = _pane_indices(e2e_session_name)
        result = run_tmw("kill", f"{e2e_session_name}:0.{panes_before[1]}")
        assert result.returncode == 0, result.stderr
        assert _pane_indices(e2e_session_name) == [panes_before[0]]

    def test_kills_by_numeric_id(self, e2e_session_name):
        _create_session(e2e_session_name)
        idx = session_index(e2e_session_name)
        result = run_tmw("kill", str(idx))
        assert result.returncode == 0, result.stderr
        assert not _session_exists(e2e_session_name)

    def test_raises_when_session_missing(self, e2e_session_name):
        result = run_tmw("kill", e2e_session_name)
        assert result.returncode != 0
        assert "No tmux session" in result.stderr


class TestKillAllPanesWildcard:
    def test_declining_to_keep_a_pane_kills_the_whole_window(self, e2e_session_name):
        """Window 0 is the session's only window, so killing it also ends
        the session — tmux destroys a session once its last window closes."""
        _create_session(e2e_session_name, panes_in_window_0=3)
        result = run_tmw("kill", f"{e2e_session_name}:0.*", input="n\n")
        assert result.returncode == 0, result.stderr
        assert not _session_exists(e2e_session_name)

    def test_keeping_a_pane_by_index_kills_only_the_others(self, e2e_session_name):
        """Kill all but index 1. tmux renumbers the survivor to index 0
        afterwards, so identity is checked via pane_id, not pane_index."""
        _create_session(e2e_session_name, panes_in_window_0=3)
        ids_before = _pane_ids(e2e_session_name)
        result = run_tmw("kill", f"{e2e_session_name}:0.*", input="1\n")
        assert result.returncode == 0, result.stderr
        assert _pane_ids(e2e_session_name) == [ids_before[1]]

    def test_single_pane_kills_window_without_prompting(self, e2e_session_name):
        """A single pane kills the window with no stdin needed (nothing to keep);
        since it's also the session's only window, the session ends too."""
        _create_session(e2e_session_name, panes_in_window_0=1)
        result = run_tmw("kill", f"{e2e_session_name}:0.*", input="")
        assert result.returncode == 0, result.stderr
        assert not _session_exists(e2e_session_name)


class TestKillInteractive:
    def test_picks_by_computed_index_then_quits(self, e2e_session_name):
        _create_session(e2e_session_name)
        idx = session_index(e2e_session_name)
        result = run_tmw("kill", input=f"{idx}\nq\n")
        assert result.returncode == 0, result.stderr
        assert not _session_exists(e2e_session_name)
        assert f"Killed '{e2e_session_name}'" in result.stdout

    def test_quit_token_exits_without_killing_anything(self, e2e_session_name):
        _create_session(e2e_session_name)
        result = run_tmw("kill", input="q\n")
        assert result.returncode == 0, result.stderr
        assert _session_exists(e2e_session_name)

    def test_invalid_input_warns_and_reprompts_without_killing(self, e2e_session_name):
        """Bad input never selects a session by index, so this is safe to run
        against the shared server regardless of what else is open."""
        _create_session(e2e_session_name)
        result = run_tmw("kill", input="xyz\nq\n")
        assert result.returncode == 0, result.stderr
        assert "Invalid" in result.stdout
        assert _session_exists(e2e_session_name)

    def test_out_of_range_index_warns_and_reprompts_without_killing(self, e2e_session_name):
        _create_session(e2e_session_name)
        result = run_tmw("kill", input="999999\nq\n")
        assert result.returncode == 0, result.stderr
        assert "out of range" in result.stdout.lower()
        assert _session_exists(e2e_session_name)
