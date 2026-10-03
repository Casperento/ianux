"""Tests for tmux_wrapper.tmux.TmuxClient."""

import subprocess

import pytest

from .conftest import make_run_fn
from ..exceptions import AppError
from ..tmux import TmuxClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(returncode: int = 0, stdout: str = "") -> TmuxClient:
    return TmuxClient(run_fn=make_run_fn(returncode, stdout))


def _capturing_client(stdout: str = "0\n") -> tuple[TmuxClient, list[list[str]]]:
    """Client that succeeds and records every argv it is asked to run."""
    cmds: list[list[str]] = []

    def _run(cmd, **kwargs):
        cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return TmuxClient(run_fn=_run), cmds


# ---------------------------------------------------------------------------
# Exit-code handling — every method that raises on a non-zero tmux exit
# ---------------------------------------------------------------------------


_RAISING_CALLS = [
    pytest.param(lambda c: c.new_session("s"), "Failed to create tmux session", id="new_session"),
    pytest.param(lambda c: c.kill_session("s"), "Failed to kill session", id="kill_session"),
    pytest.param(lambda c: c.new_window("s"), "Failed to create a new window", id="new_window"),
    pytest.param(lambda c: c.select_window("s", "1"), "Failed to select window", id="select_window"),
    pytest.param(lambda c: c.split_window("s", 2), "Failed while creating pane", id="split_window"),
    pytest.param(lambda c: c.select_layout("s", "tiled"), "Failed to apply", id="select_layout"),
    pytest.param(lambda c: c.list_panes("s"), "Failed to list panes", id="list_panes"),
    pytest.param(lambda c: c.send_keys("s", "0", "0", "make"), "Failed to initialize pane", id="send_keys"),
    pytest.param(
        lambda c: c.pane_current_path("s", "0", "0"), "Failed to query current directory",
        id="pane_current_path",
    ),
    pytest.param(lambda c: c.attach("s"), "Failed to attach", id="attach"),
]


@pytest.mark.parametrize("call, match", _RAISING_CALLS)
def test_raises_only_on_nonzero_exit(call, match):
    call(_client(returncode=0, stdout="0\n"))  # must not raise
    with pytest.raises(AppError, match=match):
        call(_client(returncode=1))


def test_tmux_missing_from_path_raises_app_error():
    client = TmuxClient(run_fn=make_run_fn(raise_file_not_found=True))
    with pytest.raises(AppError, match="not available in PATH"):
        client.session_exists("sess")


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call, argv",
    [
        pytest.param(
            lambda c: c.new_session("my-session"),
            ["new-session", "-d", "-s", "my-session"],
            id="new_session",
        ),
        pytest.param(
            lambda c: c.new_session("my-session", window_name="editor"),
            ["new-session", "-d", "-s", "my-session", "-n", "editor"],
            id="new_session-window-name",
        ),
        pytest.param(
            lambda c: c.new_window("sess", name="logs"),
            ["new-window", "-t", "sess:", "-P", "-F", "#{window_index}", "-n", "logs"],
            id="new_window-name",
        ),
        pytest.param(
            lambda c: c.split_window("sess", 1),
            ["split-window", "-t", "sess:0"],
            id="split_window-active-pane",
        ),
        pytest.param(
            lambda c: c.split_window("sess", 2, target_pane="3"),
            ["split-window", "-t", "sess:0.3"],
            id="split_window-target-pane",
        ),
        pytest.param(
            lambda c: c.split_window("sess", 1, window="2"),
            ["split-window", "-t", "sess:2"],
            id="split_window-window",
        ),
        pytest.param(
            lambda c: c.list_panes("sess", window="3"),
            ["list-panes", "-t", "sess:3", "-F", "#{pane_index}"],
            id="list_panes-window",
        ),
        pytest.param(
            lambda c: c.send_keys("sess", "1", "0", "make all"),
            ["send-keys", "-t", "sess:1.0", "make all", "C-m"],
            id="send_keys",
        ),
    ],
)
def test_builds_expected_argv(call, argv):
    client, cmds = _capturing_client()
    call(client)
    assert cmds == [["tmux"] + argv]


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("returncode, expected", [(0, True), (1, False)])
def test_session_exists_reflects_exit_code(returncode, expected):
    assert _client(returncode=returncode).session_exists("s") is expected


def test_new_window_returns_window_index():
    assert _client(stdout="2\n").new_window("sess") == "2"


def test_window_names_parses_index_to_name_mapping():
    names = _client(stdout="0:editor\n1:logs\n").window_names("sess")
    assert names == {"0": "editor", "1": "logs"}


def test_window_names_empty_on_failure():
    assert _client(returncode=1).window_names("sess") == {}


def test_list_sessions_names_sorted_and_stripped():
    stdout = "  gamma  \nalpha\n\n  beta\n"
    assert _client(stdout=stdout).list_sessions_names() == ["alpha", "beta", "gamma"]


@pytest.mark.parametrize(
    "returncode, stdout",
    [pytest.param(1, "", id="server-not-running"), pytest.param(0, "", id="no-sessions")],
)
def test_list_sessions_names_empty(returncode, stdout):
    assert _client(returncode=returncode, stdout=stdout).list_sessions_names() == []


def test_list_panes_returns_pane_indices():
    assert _client(stdout="0\n1\n2\n").list_panes("sess") == ["0", "1", "2"]


def test_list_panes_empty_output_raises():
    with pytest.raises(AppError, match="No panes found"):
        _client(stdout="").list_panes("sess")


def test_pane_current_path_strips_output():
    path = _client(stdout="/home/user/project\n").pane_current_path("sess", "0", "0")
    assert path == "/home/user/project"
