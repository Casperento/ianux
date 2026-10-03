"""Tests for tmw.dumper that don't fit test_dumper_e2e.py.

Everything observable through dump's real behavior (window/pane directory
capture, numeric-id resolution, name omission, missing-session error,
directory creation, round-tripping through the loader) is covered end-to-end
against a real tmux server in test_dumper_e2e.py.

What's left is the default-output-directory fallback: verifying it for real
would write into the developer's actual ~/.config/tmw/sessions/,
an undesirable side effect to leave behind just for a test.
"""

from tmw.config import DumpConfig
from tmw.dumper import SessionDumper


class TestDumpDirect:
    def test_default_output_dir_uses_default_config_dir(self, mock_client, tmp_path, monkeypatch):
        monkeypatch.setattr("tmw.dumper._DEFAULT_CONFIG_DIR", tmp_path / "sessions")
        mock_client.session_exists.return_value = True
        mock_client.list_panes_all.return_value = {"0": ["0"]}
        mock_client.window_names.return_value = {"0": ""}
        mock_client.pane_current_path.return_value = "/work"

        SessionDumper(mock_client).dump(DumpConfig(session_name="my-session"))

        assert (tmp_path / "sessions" / "my-session.toml").exists()
