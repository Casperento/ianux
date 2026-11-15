"""Tests for ianux.dumper that don't fit test_dumper_e2e.py.

Everything observable through dump's real behavior (window/pane directory
capture, numeric-id resolution, name omission, missing-session error,
directory creation, round-tripping through the loader) is covered end-to-end
against a real tmux server in test_dumper_e2e.py.

What's left is the default-output-directory fallback: verifying it for real
would write into the developer's actual ~/.config/ianux/sessions/,
an undesirable side effect to leave behind just for a test.
"""

from ianux.config import DumpConfig, LoadConfig
from ianux.dumper import SessionDumper
from ianux.loader import load_session_config


class TestDumpDirect:
    def test_default_output_dir_uses_default_config_dir(self, mock_client, tmp_path, monkeypatch):
        monkeypatch.setattr("ianux.dumper._DEFAULT_CONFIG_DIR", tmp_path / "sessions")
        mock_client.session_exists.return_value = True
        mock_client.list_panes_all.return_value = {"0": ["0"]}
        mock_client.window_names.return_value = {"0": ""}
        mock_client.window_layouts.return_value = {}
        mock_client.pane_current_path.return_value = "/work"

        SessionDumper(mock_client).dump(DumpConfig(session_name="my-session"))

        assert (tmp_path / "sessions" / "my-session.toml").exists()

    def test_window_layout_is_dumped_and_loads_back(self, mock_client, tmp_path):
        layout = "b25d,238x64,0,0{119x64,0,0,0,118x64,120,0,1}"
        mock_client.session_exists.return_value = True
        mock_client.list_panes_all.return_value = {"0": ["0", "1"]}
        mock_client.window_names.return_value = {"0": "editor"}
        mock_client.window_layouts.return_value = {"0": layout}
        mock_client.pane_current_path.return_value = str(tmp_path)

        SessionDumper(mock_client).dump(DumpConfig(session_name="s", output=tmp_path))

        toml = tmp_path / "s.toml"
        assert f'layout = "{layout}"' in toml.read_text()
        loaded = load_session_config(LoadConfig(path=toml))
        assert loaded.windows[0].layout == layout
