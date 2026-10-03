"""E2E tests for the 'dump' subcommand against a real tmux server.

Builds real sessions with known pane directories via raw tmux commands
(independent of session.py), runs `tmw dump` as a real subprocess, and
verifies the written TOML — including round-tripping it through the real
loader, exactly as 'load'/'session' would consume it.
"""

import shutil
import subprocess
import time
import tomllib

import pytest

from tmw.config import LoadConfig
from tmw.loader import load_session_config
from .conftest import run_tmw, session_index

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not on PATH"),
]


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _read_toml(path):
    return tomllib.loads(path.read_text())


def _set_pane_cwd(session: str, window: str, pane: str, path, timeout: float = 2.0) -> None:
    """cd a real pane into *path* and block until the shell has actually done it."""
    _tmux("send-keys", "-t", f"{session}:{window}.{pane}", f"cd {path}", "C-m")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = _tmux(
            "display-message", "-p", "-t", f"{session}:{window}.{pane}", "#{pane_current_path}"
        ).stdout.strip()
        if current == str(path):
            return
        time.sleep(0.05)
    raise AssertionError(f"pane never cd'd to {path!r} (stuck at {current!r})")


class TestDumpDirect:
    def test_dumps_single_window_single_pane_directory(self, e2e_session_name, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        _tmux("new-session", "-d", "-s", e2e_session_name)
        _set_pane_cwd(e2e_session_name, "0", "0", work)

        result = run_tmw("dump", e2e_session_name, "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr

        data = _read_toml(tmp_path / f"{e2e_session_name}.toml")
        assert data["session_name"] == e2e_session_name
        assert len(data["window"]) == 1
        assert data["window"][0]["panes"] == 1
        assert data["window"][0]["pane"][0]["directory"] == str(work)
        assert data["window"][0]["pane"][0]["init_command"] == ""

        # Round-trips through the real loader exactly as 'load' would read it.
        reloaded = load_session_config(LoadConfig(path=tmp_path / f"{e2e_session_name}.toml"))
        assert reloaded.session_name == e2e_session_name

    def test_dumps_multiple_windows_in_index_order_with_names(self, e2e_session_name, tmp_path):
        dir0 = tmp_path / "editor_dir"
        dir1 = tmp_path / "logs_dir"
        dir0.mkdir()
        dir1.mkdir()

        _tmux("new-session", "-d", "-s", e2e_session_name)
        _tmux("rename-window", "-t", f"{e2e_session_name}:0", "editor")
        _set_pane_cwd(e2e_session_name, "0", "0", dir0)
        _tmux("new-window", "-t", f"{e2e_session_name}:", "-n", "logs")
        _set_pane_cwd(e2e_session_name, "1", "0", dir1)

        result = run_tmw("dump", e2e_session_name, "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr

        data = _read_toml(tmp_path / f"{e2e_session_name}.toml")
        assert [w["name"] for w in data["window"]] == ["editor", "logs"]
        assert data["window"][0]["pane"][0]["directory"] == str(dir0)
        assert data["window"][1]["pane"][0]["directory"] == str(dir1)

    def test_window_with_empty_name_omits_name_field(self, e2e_session_name, tmp_path):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        _tmux("rename-window", "-t", f"{e2e_session_name}:0", "")

        result = run_tmw("dump", e2e_session_name, "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr

        data = _read_toml(tmp_path / f"{e2e_session_name}.toml")
        assert "name" not in data["window"][0]

    def test_dumps_by_numeric_id_using_resolved_name(self, e2e_session_name, tmp_path):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        idx = session_index(e2e_session_name)

        result = run_tmw("dump", str(idx), "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr
        assert _read_toml(tmp_path / f"{e2e_session_name}.toml")["session_name"] == e2e_session_name

    def test_creates_nested_output_directory_if_missing(self, e2e_session_name, tmp_path):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        out_dir = tmp_path / "nested" / "dir"

        result = run_tmw("dump", e2e_session_name, "-o", str(out_dir))
        assert result.returncode == 0, result.stderr
        assert (out_dir / f"{e2e_session_name}.toml").exists()

    def test_raises_when_session_missing(self, e2e_session_name, tmp_path):
        result = run_tmw("dump", e2e_session_name, "-o", str(tmp_path))
        assert result.returncode != 0
        assert "does not exist" in result.stderr


class TestDumpInteractive:
    def test_dumps_picked_session_by_computed_index(self, e2e_session_name, tmp_path):
        _tmux("new-session", "-d", "-s", e2e_session_name)
        idx = session_index(e2e_session_name)

        result = run_tmw("dump", "-o", str(tmp_path), input=f"{idx}\n")
        assert result.returncode == 0, result.stderr
        assert (tmp_path / f"{e2e_session_name}.toml").exists()
