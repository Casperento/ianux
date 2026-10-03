"""Tests for tmw.killer that don't fit test_killer_e2e.py.

Direct-target kills, the wildcard keep/kill-all flow, and the interactive
loop's happy and bad-input paths are covered end-to-end against a real tmux
server in test_killer_e2e.py. What's left here is:

- _parse_target: a pure string-parsing function with no tmux/I/O dependency.
- the "no sessions open" error path: untestable at E2E on this machine,
  since the tmux server is shared with the developer's own real sessions —
  there's no way to safely get to "zero sessions open" without killing them.
"""

import pytest

from tmw.config import KillConfig
from tmw.exceptions import AppError
from tmw.killer import SessionKiller, _parse_target, _Target


class TestParseTarget:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("abc", _Target("session", "abc", None, None)),
            ("test:2", _Target("window", "test", "2", None)),
            ("test:1.3", _Target("pane", "test", "1", "3")),
            ("test:0.*", _Target("panes_all", "test", "0", None)),
        ],
    )
    def test_parses_address(self, raw, expected):
        assert _parse_target(raw) == expected


class TestInteractiveMode:
    def test_raises_when_no_sessions(self, mock_client):
        mock_client.list_sessions_names.return_value = []
        killer = SessionKiller(mock_client)
        with pytest.raises(AppError, match="No tmux sessions"):
            killer.kill(KillConfig())
