"""Shared fixtures and helpers for ianux tests."""

import os
import pty
import select
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ianux.tmux import TmuxClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def make_run_fn(returncode: int = 0, stdout: str = "", raise_file_not_found: bool = False):
    """Return a subprocess.run drop-in for TmuxClient testing.

    Parameters
    ----------
    returncode:
        Exit code the fake process returns.
    stdout:
        Text written to stdout by the fake process.
    raise_file_not_found:
        When True the callable raises FileNotFoundError instead of returning,
        simulating tmux not being on PATH.
    """

    def _run(cmd, **kwargs):
        if raise_file_not_found:
            raise FileNotFoundError("tmux not found")
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


@pytest.fixture
def mock_client():
    """A MagicMock pre-specced to TmuxClient for use in higher-level tests."""
    return MagicMock(spec=TmuxClient)


def run_ianux(*args: str, input: str | None = None) -> subprocess.CompletedProcess:
    """Invoke the real ianux CLI as a subprocess (for E2E tests) and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "ianux", *args],
        input=input,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def e2e_session_name():
    """A unique real tmux session name, killed for real on teardown (pass or fail).

    Also removes the 'run --kill' daemon's conventional sidecar files
    (/tmp/<name>.capture-pane, /tmp/<name>.monitor.log) if a test created
    them — harmless no-op for tests that never do.
    """
    name = f"ianux-e2e-{uuid.uuid4().hex[:8]}"
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], check=False, capture_output=True)
    Path(f"/tmp/{name}.capture-pane").unlink(missing_ok=True)
    Path(f"/tmp/{name}.monitor.log").unlink(missing_ok=True)


def session_index(name: str) -> int:
    """1-based index of *name* in the live tmux session list.

    Sorted alphabetically to match TmuxClient.list_sessions_names() /
    resolve_session_id()'s ordering — this is what the interactive pickers'
    numbered prompts actually index into.

    Tests MUST use this instead of a hardcoded index: the tmux server here
    is shared with the developer's own real sessions, so the position of an
    E2E test's session among *all* open sessions is never guaranteed to be
    first. Asserting the name is found keeps a lookup miss a loud failure
    instead of silently driving an interactive prompt against the wrong
    (real) session.
    """
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    names = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    assert name in names, f"{name!r} not in live tmux session list: {names}"
    return names.index(name) + 1


class AttachedProcess:
    """A `ianux attach`/`ianux session` subprocess running on a real pty.

    tmux's attach-session needs an actual terminal (capture_output=False in
    TmuxClient.attach); a plain subprocess pipe makes it fail immediately
    with "open terminal failed: not a terminal". Allocating a pty lets the
    real attach succeed so the test can verify it against the live tmux
    server, then detach by terminating the client process.
    """

    def __init__(self, proc: subprocess.Popen, master_fd: int) -> None:
        self.proc = proc
        self._master_fd = master_fd

    def read(self, timeout: float = 0.3) -> bytes:
        """Drain whatever the pty has buffered (for debugging a failed test)."""
        ready, _, _ = select.select([self._master_fd], [], [], timeout)
        if not ready:
            return b""
        try:
            return os.read(self._master_fd, 65536)
        except OSError:
            return b""

    def detach(self) -> None:
        """Terminate the attached client (equivalent to a real detach) and clean up."""
        try:
            self.proc.send_signal(signal.SIGTERM)
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()
        finally:
            os.close(self._master_fd)


def run_ianux_attached(*args: str, input: str | None = None) -> AttachedProcess:
    """Launch `python -m ianux <args>` on a pty so a real `tmux attach-session` can succeed.

    When *input* is given, it's written to the pty immediately — used to
    drive an interactive picker prompt that runs before the attach itself.
    """
    master_fd, slave_fd = pty.openpty()
    env = dict(os.environ, TERM=os.environ.get("TERM") or "xterm")
    proc = subprocess.Popen(
        [sys.executable, "-m", "ianux", *args],
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, env=env,
    )
    os.close(slave_fd)
    if input is not None:
        os.write(master_fd, input.encode())
    return AttachedProcess(proc, master_fd)
