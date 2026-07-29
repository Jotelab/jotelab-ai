"""Tests for the C4 benchmark runner (``python -m benchmarks run``)."""

import csv

import pytest

from benchmarks.run import chain_sweep, fidelity_sweep, main


def test_fidelity_sweep_counts_and_total():
    rows, diagram_topics = fidelity_sweep(["suvat"], ("easy",), seeds=2)
    assert [r["name"] for r in rows] == ["suvat", "TOTAL"]
    suvat = rows[0]
    # Every generated instance must pass its own harness at the source.
    assert suvat["fidelity_error"] == 0
    assert int(suvat["instances"]) > 0
    total = rows[-1]
    assert total["instances"] == suvat["instances"]
    # SUVAT carries an engine-owned diagram spec.
    assert diagram_topics == {"suvat": True}


def test_chain_sweep_covers_every_sanctioned_link():
    from engine.chain import SANCTIONED_LINKS

    rows = chain_sweep(("easy",), seeds=1)
    names = [r["name"] for r in rows]
    assert names[-1] == "TOTAL"
    assert len(names) == len(SANCTIONED_LINKS) + 1
    assert all(r["fidelity_error"] == 0 for r in rows)


def test_run_is_deterministic_and_writes_both_files(tmp_path):
    argv = ["run", "--topics", "suvat", "--difficulties", "easy",
            "--seeds", "1", "--out-dir", str(tmp_path)]
    assert main(argv) == 0
    first = (tmp_path / "engine-benchmarks.md").read_text()
    assert main(argv) == 0
    second = (tmp_path / "engine-benchmarks.md").read_text()
    # The C4 exit gate: same seeds, byte-identical table.
    assert first == second

    with open(tmp_path / "engine-benchmarks.csv") as fh:
        rows = list(csv.DictReader(fh))
    assert any(r["scope"] == "topic" and r["name"] == "TOTAL" for r in rows)
    assert any(r["scope"] == "chain" and r["name"] == "TOTAL" for r in rows)

    # The pending metrics are declared, never silently omitted.
    assert "Not run by this command" in first
    assert "Schema Adherence" in first


def test_unknown_topic_fails_loudly():
    with pytest.raises(KeyError):
        fidelity_sweep(["nope"], ("easy",), seeds=1)
