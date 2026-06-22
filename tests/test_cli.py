"""Smoke tests for the ``python -m engine`` CLI (engine/__main__.py)."""

import json

import pytest

from engine.__main__ import main


def test_cli_basic_mode(capsys):
    """Basic mode prints a readable summary and exits 0."""
    rc = main(["--seed", "42"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "topic: suvat" in out
    assert "answer:" in out


def test_cli_advanced_json_verify(capsys):
    """Advanced mode with pinned conditions reproduces the worked example as JSON."""
    rc = main([
        "--given", "u,a,t", "--find", "v",
        "--condition", "u=0", "--condition", "a=2", "--condition", "t=5",
        "--json", "--verify",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["find"] == {"symbol": "v", "value": 10, "unit": "m/s"}


def test_cli_unsolvable_exits_nonzero(capsys):
    """An unsolvable request reports an error and exits non-zero."""
    rc = main(["--given", "u,a", "--find", "v"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "cannot solve" in err
