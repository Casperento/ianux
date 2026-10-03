"""Tests for tmux_wrapper.__main__ (main / entrypoint)."""

from unittest.mock import patch

import pytest

from pathlib import Path

from ..__main__ import entrypoint, main
from ..config import (
    AttachConfig,
    DumpConfig,
    KillConfig,
    LoadConfig,
    RunConfig,
    SessionConfig,
    WindowConfig,
)
from ..exceptions import AppError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_parse(config):
    """Patch parse_args to return *config*."""
    return patch("tmux_wrapper.__main__.parse_args", return_value=config)


# ---------------------------------------------------------------------------
# main() routing
# ---------------------------------------------------------------------------


class TestMainRouting:
    @pytest.mark.parametrize(
        "cfg, handler, method",
        [
            pytest.param(AttachConfig(session_name="s"), "SessionAttacher", "attach", id="attach"),
            pytest.param(KillConfig(), "SessionKiller", "kill", id="kill"),
            pytest.param(RunConfig(session_name="j", commands=["make"]), "SessionRunner", "run", id="run"),
            pytest.param(DumpConfig(session_name="s"), "SessionDumper", "dump", id="dump"),
        ],
    )
    def test_routes_config_to_handler(self, mock_client, cfg, handler, method):
        with _patch_parse(cfg), patch("tmux_wrapper.__main__.TmuxClient", return_value=mock_client), \
             patch(f"tmux_wrapper.__main__.{handler}") as MockHandler:
            getattr(MockHandler.return_value, method).return_value = 0
            result = main([])
        assert result == 0
        MockHandler.assert_called_once_with(mock_client)
        getattr(MockHandler.return_value, method).assert_called_once_with(cfg)

    def test_routes_session_config(self, mock_client):
        cfg = SessionConfig(
            windows=[WindowConfig(panes=4, directories=[], init_commands=["bash"])],
            session_name="tmw",
        )
        with _patch_parse(cfg), patch("tmux_wrapper.__main__.TmuxClient", return_value=mock_client):
            with patch("tmux_wrapper.__main__.SessionManager") as MockManager, \
                 patch("tmux_wrapper.__main__.build_resolver") as mock_resolver:
                MockManager.return_value.setup.return_value = 0
                result = main([])
        assert result == 0
        MockManager.return_value.setup.assert_called_once()

    def test_routes_load_config(self, mock_client):
        load_cfg = LoadConfig(path=Path("myproject.toml"))
        session_cfg = SessionConfig(
            windows=[WindowConfig(panes=3, directories=[Path("/tmp")], init_commands=["bash"])],
            session_name="tmw",
        )
        with _patch_parse(load_cfg), patch("tmux_wrapper.__main__.TmuxClient", return_value=mock_client):
            with patch("tmux_wrapper.__main__.load_session_config", return_value=session_cfg) as mock_load, \
                 patch("tmux_wrapper.__main__.SessionManager") as MockManager, \
                 patch("tmux_wrapper.__main__.build_resolver") as mock_resolver:
                MockManager.return_value.setup.return_value = 0
                result = main([])
        assert result == 0
        mock_load.assert_called_once_with(load_cfg)
        MockManager.return_value.setup.assert_called_once_with(session_cfg, mock_resolver.return_value)


# ---------------------------------------------------------------------------
# entrypoint() error handling
# ---------------------------------------------------------------------------


class TestEntrypoint:
    def test_app_error_prints_to_stderr_and_returns_1(self, capsys):
        with patch("tmux_wrapper.__main__.main", side_effect=AppError("something went wrong")):
            result = entrypoint()
        assert result == 1
        assert "something went wrong" in capsys.readouterr().err

    def test_returns_main_exit_code_on_success(self):
        with patch("tmux_wrapper.__main__.main", return_value=0):
            result = entrypoint()
        assert result == 0
