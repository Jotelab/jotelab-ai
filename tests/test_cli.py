"""Smoke tests for the ``python -m engine`` CLI (engine/__main__.py)."""

import json
import random
import re

import pytest

from engine.__main__ import main


def test_cli_basic_mode(capsys):
    """A pinned run prints a readable summary and exits 0."""
    rc = main(["--given", "u,a,t", "--find", "v", "--seed", "42"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "topic: suvat" in out
    assert "answer:" in out


def _seed_of(out):
    return re.search(r"seed:\s*(\d+)", out).group(1)


def test_cli_default_is_random(capsys):
    """With no --seed/--given/--find, each run is a fresh random problem.

    The seed is drawn from the stdlib RNG, so different RNG state → different
    problem; both runs still succeed and echo their seed (so they stay
    reproducible). Seeding stdlib random keeps the test itself deterministic.
    """
    random.seed(1)
    assert main([]) == 0
    first = capsys.readouterr().out
    random.seed(2)
    assert main([]) == 0
    second = capsys.readouterr().out
    assert _seed_of(first) != _seed_of(second)


def test_cli_pinned_is_reproducible(capsys):
    """Pinning the split and seed reproduces byte-identical output."""
    argv = ["--given", "u,a,t", "--find", "v", "--seed", "42"]
    main(argv)
    one = capsys.readouterr().out
    main(argv)
    two = capsys.readouterr().out
    assert one == two


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
    # find carries the display value plus the authoritative exact string (ADR-005).
    assert data["find"] == {"symbol": "v", "value": 10, "exact": "10", "unit": "m/s"}


def test_cli_generates_and_verifies_declarative_topic(capsys):
    """--verify works for a declarative topic (vectors-1d), not just SUVAT.

    Also exercises the signed path: a pinned negative displacement yields a
    negative average velocity, and the Data Fidelity check passes (rc 0).
    """
    rc = main([
        "--topic", "vectors-1d", "--given", "s,t", "--find", "v",
        "--condition", "s=-12", "--condition", "t=4",
        "--json", "--verify",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["find"] == {"symbol": "v", "value": -3, "exact": "-3", "unit": "m/s"}


def test_cli_unsolvable_exits_nonzero(capsys):
    """An unsolvable request reports an error and exits non-zero."""
    rc = main(["--given", "u,a", "--find", "v"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "cannot solve" in err
