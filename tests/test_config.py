"""Tests for tmux_wrapper.config."""

import re
from pathlib import Path

import pytest

from ..config import (
    SessionConfig,
    WindowConfig,
    build_session_config,
    build_window_config,
)
from ..exceptions import AppError


class TestBuildWindowConfig:
    def test_valid_inputs_pass_through(self):
        win = build_window_config(
            panes=6, directories=[Path("/work")], init_commands=["bash"], name="editor",
        )
        assert win == WindowConfig(
            panes=6, directories=[Path("/work")], init_commands=["bash"], name="editor",
        )

    def test_empty_directories_default_to_cwd(self):
        win = build_window_config(panes=4, directories=[], init_commands=["bash"])
        assert win.directories == [Path.cwd()]

    def test_empty_init_commands_default(self):
        win = build_window_config(panes=4, directories=[], init_commands=[])
        assert win.init_commands == ["p4init"]

    @pytest.mark.parametrize("panes", [0, 999])
    def test_panes_out_of_range_raises(self, panes):
        with pytest.raises(AppError):
            build_window_config(panes=panes, directories=[], init_commands=[])


class TestBuildSessionConfig:
    def test_assembles_from_windows(self):
        win1 = build_window_config(panes=2, directories=[], init_commands=["a"], name="first")
        win2 = build_window_config(panes=1, directories=[], init_commands=["b"], name="second")
        cfg = build_session_config(windows=[win1, win2], session_name="dev", detach=True)
        assert cfg == SessionConfig(windows=[win1, win2], session_name="dev", detach=True)

    def test_none_session_name_is_auto_generated(self):
        win = build_window_config(panes=1, directories=[], init_commands=["a"])
        cfg = build_session_config(windows=[win], session_name=None, detach=False)
        assert re.match(r"^job_\d{8}$", cfg.session_name)
