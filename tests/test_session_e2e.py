"""E2E tests for the 'session' subcommand (and a 'list' bonus) against a real tmux server.

Unlike the rest of the suite, these tests invoke the real CLI (python -m tmw) as a
subprocess and verify behavior with raw `tmux` queries run independently of
the code under test — no TmuxClient mocking anywhere. Skipped automatically
when tmux isn't on PATH.
"""

import shutil
import subprocess
import time

import pytest

from .conftest import run_tmw

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not on PATH"),
]


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _pane_indices(session: str, window: str = "0") -> list[str]:
    result = _tmux("list-panes", "-t", f"{session}:{window}", "-F", "#{pane_index}")
    return [line for line in result.stdout.splitlines() if line]


def _pane_path(session: str, window: str, pane: str) -> str:
    result = _tmux(
        "display-message", "-p", "-t", f"{session}:{window}.{pane}",
        "#{pane_current_path}",
    )
    return result.stdout.strip()


def _session_exists(session: str) -> bool:
    return _tmux("has-session", "-t", session).returncode == 0


def _wait_for_pane_path(session: str, window: str, pane: str, expected: str, timeout: float = 2.0) -> str:
    """Poll pane_current_path until it matches *expected* or *timeout* elapses.

    send-keys is fire-and-forget: the shell needs a moment to process the
    'cd' before its cwd reflects it, so a single immediate read is flaky.
    """
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = _pane_path(session, window, pane)
        if last == expected:
            return last
        time.sleep(0.05)
    return last


class TestSessionCreation:
    def test_creates_session_with_panes_in_requested_directories(self, e2e_session_name, tmp_path):
        dira = tmp_path / "frontend"
        dirb = tmp_path / "backend"
        dira.mkdir()
        dirb.mkdir()

        result = run_tmw(
            "session",
            "--panes", "2",
            "--session-name", e2e_session_name,
            "--directory", str(dira),
            "--directory", str(dirb),
            "--init-command", "",
            "--detach",
        )

        assert result.returncode == 0, result.stderr
        assert _session_exists(e2e_session_name)

        panes = _pane_indices(e2e_session_name)
        assert len(panes) == 2
        assert _wait_for_pane_path(e2e_session_name, "0", panes[0], str(dira)) == str(dira)
        assert _wait_for_pane_path(e2e_session_name, "0", panes[1], str(dirb)) == str(dirb)

        # --detach must print a ready confirmation and never attach the terminal.
        assert e2e_session_name in result.stdout
        assert "detach" in result.stdout.lower()


class TestMultipleWindows:
    def test_two_windows_get_names_pane_counts_and_window_zero_stays_active(
        self, e2e_session_name, tmp_path
    ):
        dir_editor = tmp_path / "editor_dir"
        dir_logs_a = tmp_path / "logs_a"
        dir_logs_b = tmp_path / "logs_b"
        for d in (dir_editor, dir_logs_a, dir_logs_b):
            d.mkdir()

        result = run_tmw(
            "session",
            "--session-name", e2e_session_name,
            "--window-panes", "1",
            "--window-panes", "2",
            "--window-name", "editor",
            "--window-name", "logs",
            "--directory", str(dir_editor),
            "--directory", str(dir_logs_a),
            "--directory", str(dir_logs_b),
            "--init-command", "",
            "--detach",
        )
        assert result.returncode == 0, result.stderr
        assert _session_exists(e2e_session_name)

        windows = _tmux(
            "list-windows", "-t", e2e_session_name,
            "-F", "#{window_index}:#{window_name}:#{window_active}",
        ).stdout.splitlines()
        by_index = {line.split(":")[0]: line.split(":")[1:] for line in windows if line}

        assert len(by_index) == 2
        assert by_index["0"][0] == "editor"
        assert by_index["1"][0] == "logs"
        # select-window(session, "0") runs after both windows are created,
        # so window 0 (not the just-created window 1) is the active one.
        assert by_index["0"][1] == "1"
        assert by_index["1"][1] == "0"

        assert len(_pane_indices(e2e_session_name, window="0")) == 1
        assert len(_pane_indices(e2e_session_name, window="1")) == 2


class TestDuplicateSessionName:
    def test_duplicate_name_gets_numbered_instead_of_prompting(self, e2e_session_name, tmp_path):
        d = tmp_path / "work"
        d.mkdir()

        first = run_tmw(
            "session", "--panes", "1", "--session-name", e2e_session_name,
            "--directory", str(d), "--init-command", "", "--detach",
        )
        assert first.returncode == 0, first.stderr
        assert _session_exists(e2e_session_name)

        numbered = f"{e2e_session_name}-1"
        try:
            second = run_tmw(
                "session", "--panes", "3", "--session-name", e2e_session_name,
                "--directory", str(d), "--init-command", "", "--detach",
            )
            assert second.returncode == 0, second.stderr

            # No prompt, no kill: the original session is untouched...
            assert _session_exists(e2e_session_name)
            assert len(_pane_indices(e2e_session_name)) == 1
            # ...and the new session was created under a numbered name.
            assert _session_exists(numbered)
            assert len(_pane_indices(numbered)) == 3
        finally:
            _tmux("kill-session", "-t", numbered)


class TestListSubcommand:
    def test_list_shows_the_session_and_its_pane_count(self, e2e_session_name, tmp_path):
        d = tmp_path / "work"
        d.mkdir()

        created = run_tmw(
            "session", "--panes", "2", "--session-name", e2e_session_name,
            "--directory", str(d), "--init-command", "", "--detach",
        )
        assert created.returncode == 0, created.stderr

        listed = run_tmw("list")
        assert listed.returncode == 0, listed.stderr
        assert e2e_session_name in listed.stdout
        assert "2 panes" in listed.stdout
