"""
Unit tests for neuro.utils.terminal_components - the aligned table.
"""

import re

import pytest

from neuro.utils import terminal_components

pytestmark = pytest.mark.unit

ANSI = re.compile(r"\033\[[0-9;]*m")
LONG = "RELEASE: ontology delta-system 4.1 - WebDevice is a continuant, not an interval"
ROWS = [
    ("2026-11-16", "\033[2m·\033[0m", "1.0", "RELEASE: ontology delta-system 5.2", ""),
    ("2026-09-26", "\033[2m·\033[0m", "1.0", LONG, ""),
    ("2026-06-23", "\033[2m·\033[0m", "1.0", "RELEASE: knowledge status", "knowledge/status/1.0"),
    ("2026-06-20", "\033[2m·\033[0m", "0.9", "ADD: knowledge status, the closed vocabulary of five states", "knowledge/status/0.9"),
]
HEADER = ("Date", "Root", "Version", "Subject", "Tags")


def _lines(capsys, **kwargs):
    terminal_components.table(ROWS, header=HEADER, **kwargs)
    return [ANSI.sub("", line) for line in capsys.readouterr().out.splitlines()]


def test_table(capsys):
    lines = _lines(capsys)
    assert lines[2] == f"  2026-09-26  ·     1.0      {LONG}"
    assert all(line == line.rstrip() for line in lines)  # no trailing padding to wrap on
    assert lines[0].index("Tags") == lines[3].index("knowledge/status/1.0") == lines[4].index("knowledge/status/0.9")


def test_table_shrink(capsys):
    lines = _lines(capsys, shrink=3, width=80)
    assert max(map(len, lines)) <= 80
    # nothing to its right: the cell runs over the empty column, to the edge
    assert lines[2] == "  2026-09-26  ·     1.0      RELEASE: ontology delta-system 4.1 - WebDevice is…"
    assert lines[1].endswith("RELEASE: ontology delta-system 5.2")
    # something to its right: held to the column, cut when the row would not fit
    assert lines[4].endswith("ADD: knowledge status, the c…  knowledge/status/0.9")
    assert lines[3].index("knowledge/status/1.0") == lines[4].index("knowledge/status/0.9") == lines[0].index("Tags")
    # wide enough: nothing is cut, and the long subject does not push the tags out
    wide = _lines(capsys, shrink=3, width=200)
    assert wide[2].endswith(LONG) and wide[4].endswith("five states  knowledge/status/0.9")
    assert wide[0].index("Tags") < len(wide[2])
    # not a terminal and no width given: nothing is cut
    assert _lines(capsys, shrink=3)[2].endswith(LONG)
