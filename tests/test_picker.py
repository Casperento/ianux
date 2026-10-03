"""Tests for tmw.picker."""

import pytest

from tmw.exceptions import AppError
from tmw.picker import pick, pick_session


class TestPick:
    def test_returns_selected_item_and_lists_labels(self, capsys):
        result = pick(
            ["a.toml", "b.toml"], lambda _: "2",
            heading="Configs:", prompt="Select", label=str.upper,
        )
        assert result == "b.toml"
        out = capsys.readouterr().out
        assert "Configs:" in out
        assert "[1] A.TOML" in out
        assert "[2] B.TOML" in out

    @pytest.mark.parametrize(
        "raw, match",
        [("abc", "Invalid selection"), ("0", "out of range"),
         ("-1", "out of range"), ("5", "out of range")],
    )
    def test_bad_input_raises(self, raw, match):
        with pytest.raises(AppError, match=match):
            pick(["a", "b"], lambda _: raw, heading="h", prompt="p")


class TestPickSession:
    def test_raises_when_no_sessions(self, mock_client):
        mock_client.list_sessions_names.return_value = []
        with pytest.raises(AppError, match="No tmux sessions"):
            pick_session(mock_client, lambda _: "1")

    def test_custom_prompt_is_shown(self, mock_client):
        mock_client.list_sessions_names.return_value = ["alpha"]
        prompts = []
        pick_session(mock_client, lambda p: prompts.append(p) or "1", "Select a session to dump")
        assert prompts == ["Select a session to dump (1-1): "]
