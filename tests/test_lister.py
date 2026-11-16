"""Tests for ianux.lister.SessionLister."""

import re

from ianux.config import ListConfig
from ianux.lister import SessionLister

_ANSI = re.compile(r"\033\[[0-9;]*m")


def test_list_shows_attached_column(mock_client, capsys):
    created = "(created Wed Aug 19 05:58:11 2026) [80x24]"
    mock_client.list_sessions.return_value = [
        f"solo: 1 windows {created}",
        f"duo: 1 windows {created}",
        f"idle: 1 windows {created}",
    ]
    mock_client.session_attached_counts.return_value = {"solo": 1, "duo": 2, "idle": 0}
    mock_client.list_panes_all.return_value = {"0": ["0"]}

    assert SessionLister(mock_client).list(ListConfig()) == 0

    lines = _ANSI.sub("", capsys.readouterr().out).splitlines()
    header = next(line for line in lines if "Name" in line)
    assert header.split()[:3] == ["#", "Name", "Attached"]

    rows = {
        line.split()[1]: line.split()[2:4]
        for line in lines
        if line.strip()[:1].isdigit()
    }
    assert rows["solo"][0] == "yes"
    assert rows["duo"] == ["yes", "(2)"]
    assert rows["idle"][0] == "-"
