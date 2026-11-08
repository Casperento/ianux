"""Tests for ianux.cli."""

from pathlib import Path

import pytest

from ianux.cli import (
    _normalize_argv,
    _slice_by_window,
    parse_args,
)
from ianux.config import (
    AttachConfig,
    DumpConfig,
    KillConfig,
    ListConfig,
    LoadConfig,
    PrintConfig,
    SessionConfig,
)


# ---------------------------------------------------------------------------
# _normalize_argv
# ---------------------------------------------------------------------------


class TestNormalizeArgv:
    @pytest.mark.parametrize(
        "argv, expected",
        [
            ([], ["--help"]),
            (["session"], ["session"]),
            (["k"], ["k"]),
            (["p"], ["p"]),
            (["print"], ["print"]),
            (["-h"], ["-h"]),
            (["--help"], ["--help"]),
            (["--window-panes", "6"], ["session", "--window-panes", "6"]),
            (["myproject"], ["session", "myproject"]),
        ],
    )
    def test_normalize(self, argv, expected):
        assert _normalize_argv(argv) == expected


# ---------------------------------------------------------------------------
# Subcommand aliases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv, config_type",
    [
        (["s"], SessionConfig),
        (["a"], AttachConfig),
        (["k"], KillConfig),
        (["ls"], ListConfig),
        (["l", "myproject.toml"], LoadConfig),
        (["d", "my-session"], DumpConfig),
        (["p", "s:0.0"], PrintConfig),
        (["print", "s:0.0"], PrintConfig),
    ],
)
def test_alias_routes_to_subcommand(argv, config_type):
    assert isinstance(parse_args(argv), config_type)


# ---------------------------------------------------------------------------
# parse_args — session subcommand
# ---------------------------------------------------------------------------


class TestParseArgsSession:
    def test_defaults(self):
        cfg = parse_args(["session"])
        assert isinstance(cfg, SessionConfig)
        assert len(cfg.windows) == 1
        win = cfg.windows[0]
        assert win.panes == 4  # _DEFAULT_PANES
        assert win.directories == [Path.cwd()]
        assert len(win.init_commands) == 1 and win.init_commands[0]  # non-empty default
        assert cfg.detach is False

    def test_window_panes_flag_for_one_window(self):
        assert parse_args(["session", "--window-panes", "8"]).windows[0].panes == 8

    @pytest.mark.parametrize("panes", ["0", "999"])
    def test_window_panes_out_of_range_exits(self, panes):
        with pytest.raises(SystemExit):
            parse_args(["session", "--window-panes", panes])

    def test_multiple_directory_flags(self):
        cfg = parse_args([
            "session", "--window-panes", "3",
            "--directory", "/tmp/a",
            "--directory", "/tmp/b",
            "--directory", "/tmp/c",
        ])
        assert cfg.windows[0].directories == [Path("/tmp/a"), Path("/tmp/b"), Path("/tmp/c")]

    def test_multiple_init_commands(self):
        cfg = parse_args([
            "session", "--window-panes", "3",
            "--init-command", "cmd1",
            "--init-command", "cmd2",
            "--init-command", "cmd3",
        ])
        assert cfg.windows[0].init_commands == ["cmd1", "cmd2", "cmd3"]

    @pytest.mark.parametrize("flag", ["--detach", "-d"])
    def test_detach_flag(self, flag):
        assert parse_args(["session", flag]).detach is True


# ---------------------------------------------------------------------------
# parse_args — session subcommand, multiple windows
# ---------------------------------------------------------------------------


class TestParseArgsSessionMultiWindow:
    def test_short_window_options(self):
        cfg = parse_args([
            "session", "-p", "2", "-w", "editor", "-p", "1", "-w", "logs",
        ])
        assert [(w.panes, w.name) for w in cfg.windows] == [(2, "editor"), (1, "logs")]

    def test_window_name_aligned_with_window_panes(self):
        cfg = parse_args([
            "session",
            "--window-panes", "2", "--window-name", "editor",
            "--window-panes", "1", "--window-name", "logs",
        ])
        assert [w.name for w in cfg.windows] == ["editor", "logs"]

    def test_window_name_single_window_shorthand(self):
        cfg = parse_args(["session", "--window-name", "editor"])
        assert cfg.windows[0].name == "editor"

    def test_missing_window_names_default_to_none(self):
        cfg = parse_args([
            "session", "--window-panes", "2", "--window-panes", "1", "--window-name", "editor",
        ])
        assert [w.name for w in cfg.windows] == ["editor", None]

    def test_too_many_window_names_is_error(self):
        with pytest.raises(SystemExit):
            parse_args([
                "session", "--window-panes", "1",
                "--window-name", "a", "--window-name", "b",
            ])

    def test_directories_span_window_boundaries(self):
        cfg = parse_args([
            "session",
            "--window-panes", "2", "--window-panes", "1",
            "--directory", "/tmp/a", "--directory", "/tmp/b", "--directory", "/tmp/c",
        ])
        assert [str(d) for d in cfg.windows[0].directories] == ["/tmp/a", "/tmp/b"]
        assert [str(d) for d in cfg.windows[1].directories] == ["/tmp/c"]

    def test_directories_reuse_last_across_window_boundary(self):
        """When -C runs out before a later window, that window still starts
        from the last value seen — SessionManager's own reuse-last then
        expands it to fill that window's remaining panes at setup time."""
        cfg = parse_args([
            "session",
            "--window-panes", "1", "--window-panes", "2",
            "--directory", "/tmp/only",
        ])
        assert [str(d) for d in cfg.windows[0].directories] == ["/tmp/only"]
        assert [str(d) for d in cfg.windows[1].directories] == ["/tmp/only"]


# ---------------------------------------------------------------------------
# _slice_by_window
# ---------------------------------------------------------------------------


class TestSliceByWindow:
    def test_exact_fit(self):
        assert _slice_by_window(["a", "b", "c"], [2, 1]) == [["a", "b"], ["c"]]

    def test_no_padding_within_a_window(self):
        """A window's own reuse-last is SessionManager's job, not this slicer's."""
        assert _slice_by_window(["a", "b"], [1, 2]) == [["a"], ["b"]]

    def test_reuse_last_carried_into_next_window(self):
        assert _slice_by_window(["only"], [1, 2]) == [["only"], ["only"]]

    def test_empty_flat_list_yields_empty_chunks(self):
        assert _slice_by_window([], [2, 1]) == [[], []]


# ---------------------------------------------------------------------------
# parse_args — attach subcommand
# ---------------------------------------------------------------------------


class TestParseArgsAttach:
    def test_no_session_name(self):
        cfg = parse_args(["attach"])
        assert isinstance(cfg, AttachConfig)
        assert cfg.session_name is None

    def test_with_session_name(self):
        cfg = parse_args(["attach", "my-session"])
        assert isinstance(cfg, AttachConfig)
        assert cfg.session_name == "my-session"


# ---------------------------------------------------------------------------
# parse_args — kill subcommand
# ---------------------------------------------------------------------------


class TestParseArgsKill:
    @pytest.mark.parametrize("argv, target", [
        (["kill"], None),
        (["kill", "test:0.*"], "test:0.*"),
    ])
    def test_target(self, argv, target):
        assert parse_args(argv).target == target


# ---------------------------------------------------------------------------
# parse_args — load subcommand
# ---------------------------------------------------------------------------


class TestParseArgsLoad:
    def test_load_returns_load_config(self):
        cfg = parse_args(["load", "myproject.toml"])
        assert isinstance(cfg, LoadConfig)
        assert cfg.path == Path("myproject.toml")
        assert cfg.detach is False

    def test_load_without_path_triggers_interactive_picker(self):
        cfg = parse_args(["load"])
        assert isinstance(cfg, LoadConfig)
        assert cfg.path is None

    @pytest.mark.parametrize("flag", ["-d", "--detach"])
    def test_load_detach_flag(self, flag):
        cfg = parse_args(["load", flag, "p.toml"])
        assert cfg.detach is True
        assert cfg.path == Path("p.toml")


# ---------------------------------------------------------------------------
# parse_args — dump subcommand
# ---------------------------------------------------------------------------


class TestParseArgsDump:
    def test_dump_returns_dump_config(self):
        cfg = parse_args(["dump", "my-session"])
        assert isinstance(cfg, DumpConfig)
        assert cfg.session_name == "my-session"
        assert cfg.output is None

    def test_dump_without_session_is_interactive(self):
        cfg = parse_args(["dump"])
        assert isinstance(cfg, DumpConfig)
        assert cfg.session_name is None

    def test_dump_output_flag(self):
        cfg = parse_args(["dump", "my-session", "-o", "configs"])
        assert isinstance(cfg, DumpConfig)
        assert cfg.output == Path("configs")


# ---------------------------------------------------------------------------
# parse_args — print subcommand
# ---------------------------------------------------------------------------


class TestParseArgsPrint:
    def test_print_returns_print_config(self):
        cfg = parse_args(["print", "abc:0.1"])
        assert isinstance(cfg, PrintConfig)
        assert cfg.target == "abc:0.1"
        assert cfg.scrollback is False

    @pytest.mark.parametrize("flag", ["-s", "--scrollback"])
    def test_scrollback_flag(self, flag):
        cfg = parse_args(["p", flag, "0.1"])
        assert isinstance(cfg, PrintConfig)
        assert cfg.target == "0.1"
        assert cfg.scrollback is True

    def test_target_is_required(self):
        with pytest.raises(SystemExit):
            parse_args(["print"])
