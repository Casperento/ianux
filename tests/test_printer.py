"""Tests for ianux.printer."""

import pytest

from ianux.config import PrintConfig
from ianux.exceptions import AppError
from ianux.printer import PanePrinter


@pytest.fixture
def client(mock_client):
    mock_client.session_exists.return_value = True
    mock_client.list_sessions_names.return_value = ["alpha", "beta"]
    mock_client.current_session_name.return_value = "cur"
    mock_client.capture_pane.return_value = "output\n"
    return mock_client


def _print(client, target, scrollback=False):
    return PanePrinter(client).print(PrintConfig(target=target, scrollback=scrollback))


def test_named_session_prints_pane(client, capsys):
    assert _print(client, "alpha:1.2") == 0
    client.capture_pane.assert_called_once_with("alpha", "1", "2", scrollback=False)
    assert capsys.readouterr().out == "output\n"


def test_trailing_blank_lines_are_trimmed(client, capsys):
    client.capture_pane.return_value = "a\nb\n\n\n   \n"
    _print(client, "alpha:0.0")
    assert capsys.readouterr().out == "a\nb\n"


def test_empty_pane_prints_nothing(client, capsys):
    client.capture_pane.return_value = "\n\n"
    _print(client, "alpha:0.0")
    assert capsys.readouterr().out == ""


def test_numeric_id_resolves_to_session_name(client):
    _print(client, "2:0.0")
    client.capture_pane.assert_called_once_with("beta", "0", "0", scrollback=False)


@pytest.mark.parametrize("target", ["0.1", ":0.1"])
def test_missing_session_uses_current_session(client, target):
    _print(client, target)
    client.session_exists.assert_called_once_with("cur")
    client.capture_pane.assert_called_once_with("cur", "0", "1", scrollback=False)


def test_scrollback_is_forwarded(client):
    _print(client, "alpha:0.0", scrollback=True)
    client.capture_pane.assert_called_once_with("alpha", "0", "0", scrollback=True)


@pytest.mark.parametrize("target", ["alpha", "alpha:0", "alpha:0.*", "0", "alpha:.", "alpha:0."])
def test_non_pane_targets_rejected(client, target):
    with pytest.raises(AppError, match="expected SESSION:WINDOW.PANE"):
        _print(client, target)
    client.capture_pane.assert_not_called()


def test_missing_session_raises(client):
    client.session_exists.return_value = False
    with pytest.raises(AppError, match="does not exist"):
        _print(client, "ghost:0.0")
    client.capture_pane.assert_not_called()
