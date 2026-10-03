"""Tests for ianux.loader."""

import re
from pathlib import Path

import pytest

from ianux.config import LoadConfig, SessionConfig, WindowConfig
from ianux.exceptions import AppError
from ianux.loader import load_session_config


def _write(tmp_path: Path, text: str) -> LoadConfig:
    path = tmp_path / "session.toml"
    path.write_text(text, encoding="utf-8")
    return LoadConfig(path=path)


class TestFullConfig:
    def test_all_fields(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
            session_name = "demo"
            detach = true

            [[window]]
            name = "editor"
            panes = 2

            [[window.pane]]
            directory = "/tmp/a"
            init_command = "echo one"

            [[window.pane]]
            directory = "/tmp/b"
            init_command = "echo two"
            """,
        )
        result = load_session_config(cfg)
        assert result == SessionConfig(
            windows=[
                WindowConfig(
                    panes=2,
                    directories=[Path("/tmp/a"), Path("/tmp/b")],
                    init_commands=["echo one", "echo two"],
                    name="editor",
                ),
            ],
            session_name="demo",
            detach=True,
        )

    def test_multiple_windows(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
            [[window]]
            name = "editor"
            panes = 2

            [[window.pane]]
            directory = "/tmp/a"

            [[window]]
            name = "logs"
            panes = 1

            [[window.pane]]
            directory = "/tmp/b"
            """,
        )
        result = load_session_config(cfg)
        assert len(result.windows) == 2
        assert result.windows[0].name == "editor"
        assert result.windows[0].panes == 2
        assert result.windows[0].directories == [Path("/tmp/a")]
        assert result.windows[1].name == "logs"
        assert result.windows[1].panes == 1
        assert result.windows[1].directories == [Path("/tmp/b")]


class TestDefaults:
    def test_empty_file_uses_all_defaults(self, tmp_path):
        result = load_session_config(_write(tmp_path, ""))
        assert result.windows == [
            WindowConfig(panes=4, directories=[Path.cwd()], init_commands=["p4init"])
        ]
        assert result.detach is False
        assert re.match(r"^job_\d{8}$", result.session_name)

    def test_no_pane_tables_defaults_to_cwd_and_p4init(self, tmp_path):
        result = load_session_config(_write(tmp_path, "[[window]]\npanes = 2\n"))
        assert result.windows[0].directories == [Path.cwd()]
        assert result.windows[0].init_commands == ["p4init"]

    def test_missing_pane_fields_default_individually(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
            [[window]]
            [[window.pane]]
            directory = "/tmp"
            [[window.pane]]
            init_command = "bash"
            """,
        )
        result = load_session_config(cfg)
        assert result.windows[0].directories == [Path("/tmp"), Path.cwd()]
        assert result.windows[0].init_commands == ["p4init", "bash"]

    def test_window_panes_defaults_to_four(self, tmp_path):
        cfg = _write(tmp_path, '[[window]]\n[[window.pane]]\ndirectory = "/tmp"\n')
        assert load_session_config(cfg).windows[0].panes == 4


class TestPanePadding:
    def test_panes_exceeds_table_count_reuses_last_entry(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
            [[window]]
            panes = 3
            [[window.pane]]
            directory = "/tmp/a"
            init_command = "echo one"
            [[window.pane]]
            directory = "/tmp/b"
            init_command = "echo two"
            """,
        )
        result = load_session_config(cfg)
        # Only two lists are produced; SessionManager reuses the last entry
        # for the third pane at run time (same as the 'session' subcommand).
        assert result.windows[0].directories == [Path("/tmp/a"), Path("/tmp/b")]
        assert result.windows[0].init_commands == ["echo one", "echo two"]
        assert result.windows[0].panes == 3

    def test_extra_tables_beyond_panes_are_kept_but_unused_by_manager(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
            [[window]]
            panes = 1
            [[window.pane]]
            directory = "/tmp/a"
            init_command = "echo one"
            [[window.pane]]
            directory = "/tmp/b"
            init_command = "echo two"
            """,
        )
        result = load_session_config(cfg)
        assert result.windows[0].panes == 1
        assert result.windows[0].directories == [Path("/tmp/a"), Path("/tmp/b")]

    def test_reuse_last_does_not_cross_window_boundary(self, tmp_path):
        """Unlike the CLI's flat -C/-c lists, TOML windows don't share state."""
        cfg = _write(
            tmp_path,
            """
            [[window]]
            panes = 2
            [[window.pane]]
            directory = "/tmp/a"

            [[window]]
            panes = 2
            """,
        )
        result = load_session_config(cfg)
        assert result.windows[0].directories == [Path("/tmp/a")]
        # Second window has no [[window.pane]] tables at all, so it falls back
        # to cwd rather than inheriting "/tmp/a" from the first window.
        assert result.windows[1].directories == [Path.cwd()]


class TestErrors:
    def test_missing_file_raises_app_error(self, tmp_path):
        cfg = LoadConfig(path=tmp_path / "does-not-exist.toml")
        with pytest.raises(AppError):
            load_session_config(cfg)

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("this is not valid toml [[[", id="invalid-syntax"),
            pytest.param("bogus = 1\n", id="unknown-top-key"),
            pytest.param('[[window]]\nbogus = "x"\n', id="unknown-window-key"),
            pytest.param('[[window]]\n[[window.pane]]\nbogus = "x"\n', id="unknown-pane-key"),
            pytest.param('window = "oops"\n', id="window-not-array"),
            pytest.param('[[window]]\npane = "oops"\n', id="pane-not-array"),
            pytest.param('[[window]]\npanes = "six"\n', id="panes-wrong-type"),
            pytest.param("[[window]]\npanes = 0\n", id="panes-out-of-range"),
            pytest.param("[[window]]\nname = 5\n", id="window-name-wrong-type"),
            pytest.param("session_name = 5\n", id="session-name-wrong-type"),
            pytest.param('detach = "yes"\n', id="detach-wrong-type"),
            pytest.param("[[window]]\n[[window.pane]]\ndirectory = 5\n", id="directory-wrong-type"),
            pytest.param("[[window]]\n[[window.pane]]\ninit_command = 5\n", id="init-command-wrong-type"),
        ],
    )
    def test_invalid_content_raises_app_error(self, tmp_path, text):
        with pytest.raises(AppError):
            load_session_config(_write(tmp_path, text))


# ---------------------------------------------------------------------------
# Interactive selection (config.path is None)
# ---------------------------------------------------------------------------


class TestInteractiveSelection:
    def test_missing_config_dir_is_created_and_seeded_with_demo(self, tmp_path):
        nested_dir = tmp_path / "a" / "b" / "c"
        result = load_session_config(
            LoadConfig(), prompt_fn=lambda _: "1", config_dir=nested_dir
        )
        assert (nested_dir / "demo.toml").exists()
        assert result.session_name == "demo"
        assert [w.name for w in result.windows] == ["editor", "logs"]
        assert result.windows[0].panes == 2
        assert result.windows[0].init_commands == ["npm run dev", "flask run"]
        assert result.windows[1].panes == 1

    def test_existing_empty_config_dir_is_not_seeded(self, tmp_path):
        """An already-existing directory (even empty) is left alone — only a
        directory this call itself creates gets the demo."""
        with pytest.raises(AppError, match="No TOML config files found"):
            load_session_config(LoadConfig(), config_dir=tmp_path)
        assert not (tmp_path / "demo.toml").exists()

    def test_valid_selection_loads_that_file(self, tmp_path, capsys):
        (tmp_path / "alpha.toml").write_text("[[window]]\npanes = 1\n", encoding="utf-8")
        (tmp_path / "beta.toml").write_text("[[window]]\npanes = 2\n", encoding="utf-8")
        result = load_session_config(
            LoadConfig(), prompt_fn=lambda _: "2", config_dir=tmp_path
        )
        # Sorted alphabetically: alpha.toml=1, beta.toml=2 → picking "2" loads beta.toml.
        assert result.windows[0].panes == 2
        out = capsys.readouterr().out
        assert "[1] alpha.toml" in out
        assert "[2] beta.toml" in out
