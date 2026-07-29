"""Tests for chained mixed problems (engine/chain.py + harness verify_chain).

Spec: docs/superpowers/specs/2026-07-24-mixed-chained-problems-design.md.
"""

import sympy

from engine import sampling
from engine.registry import load_template


def _suvat_syms(*names):
    template = load_template("suvat")
    return template, tuple(template.symbol(n) for n in names)


def test_pinned_condition_accepts_exact_noninteger():
    """A link value like 7/2 must flow through `conditions` without rounding."""
    template, (u, a, t) = _suvat_syms("u", "a", "t")
    inputs = sampling.sample(template, (u, a, t), {"u": "7/2"}, "easy", seed=1)
    assert inputs[u] == sympy.Rational(7, 2)


def test_pinned_integer_condition_stays_integer():
    """Backwards compatibility: integer pins remain sympy.Integer."""
    template, (u, a, t) = _suvat_syms("u", "a", "t")
    inputs = sampling.sample(template, (u, a, t), {"u": 5}, "easy", seed=1)
    assert inputs[u] == sympy.Integer(5)
    assert inputs[u].is_Integer


from engine.errors import ChainSpecError, EngineError, IncompatibleLinkError


def test_chain_errors_are_typed_engine_errors():
    assert issubclass(ChainSpecError, EngineError)
    assert issubclass(IncompatibleLinkError, EngineError)
    err = IncompatibleLinkError("suvat", "t", "s", "m/s")
    assert err.topic == "suvat" and err.symbol == "t"
    assert "expects s" in str(err) and "m/s" in str(err)


# -- tests for generate_chain ---------------------------------------------------

import json

import pytest

from engine.chain import SANCTIONED_LINKS, generate_chain
from engine.errors import NoCleanInstanceError, UnsanctionedLinkError

# free-fall default split is (u, g, t) -> v [m/s]; suvat's u is m/s-compatible.
PARTS = [
    {"topic": "free-fall"},
    {"topic": "suvat", "given": ["u", "a", "t"], "find": "s", "receive": "u"},
]


def test_link_value_flows_exactly():
    data = generate_chain(PARTS, difficulty="easy", seed=7)
    feed = data["parts"][0]["final_answer"]["exact"]
    recv = next(g for g in data["parts"][1]["given"] if g["symbol"] == "u")
    assert recv["exact"] == feed
    assert data["links"] == [
        {"from_part": 0, "to_part": 1, "symbol": "u", "exact": feed}
    ]


def test_chain_contract_shape():
    data = generate_chain(PARTS, seed=3)
    assert data["topic"] == "mixed"
    assert data["topics"] == ["free-fall", "suvat"]
    assert data["policy_applied"] == "easy"
    assert data["seed"] == 3
    assert len(data["parts"]) == 2
    assert data["parts"][0]["topic"] == "free-fall"   # unmodified sympy_data
    assert data["final_answer"] == data["parts"][-1]["final_answer"]


def test_chain_deterministic_from_seed():
    one = generate_chain(PARTS, seed=11)
    two = generate_chain(PARTS, seed=11)
    assert json.dumps(one) == json.dumps(two)


def test_three_part_chain():
    parts = [
        {"topic": "free-fall"},
        {"topic": "suvat", "given": ["u", "a", "t"], "find": "v", "receive": "u"},
        {"topic": "upward-throw", "given": ["u", "g", "t"], "find": "h",
         "receive": "u"},
    ]
    data = generate_chain(parts, difficulty="easy", seed=2)
    assert data["topics"] == ["free-fall", "suvat", "upward-throw"]
    assert [(l["from_part"], l["to_part"]) for l in data["links"]] == [(0, 1), (1, 2)]


def test_single_part_rejected():
    with pytest.raises(ChainSpecError, match="at least 2 parts"):
        generate_chain([{"topic": "suvat"}])


def test_missing_receive_rejected():
    with pytest.raises(ChainSpecError, match="receive"):
        generate_chain([{"topic": "free-fall"}, {"topic": "suvat"}])


def test_unknown_receive_rejected():
    with pytest.raises(ChainSpecError, match="zz"):
        generate_chain([{"topic": "free-fall"},
                        {"topic": "suvat", "receive": "zz"}])


def test_receive_not_among_givens_rejected():
    # suvat default split given is (u, a, t); s is a valid symbol but not a given.
    with pytest.raises(ChainSpecError, match="not among"):
        generate_chain([{"topic": "free-fall"},
                        {"topic": "suvat", "receive": "s"}])


def test_incompatible_units_rejected():
    # free-fall find v is m/s; suvat's t is s.
    with pytest.raises(IncompatibleLinkError):
        generate_chain([{"topic": "free-fall"},
                        {"topic": "suvat", "receive": "t"}])


def test_bounded_failure_raises_no_clean_instance():
    """A downstream part whose pinned condition violates plausibility always
    (t = -5 breaks time-positivity) fails loudly after the bounded re-rolls."""
    parts = [
        {"topic": "free-fall"},
        {"topic": "suvat", "given": ["u", "a", "t"], "find": "v",
         "receive": "u", "conditions": {"t": -5}},
    ]
    with pytest.raises(NoCleanInstanceError):
        generate_chain(parts, seed=1, max_chain_attempts=2, max_attempts=5)


def test_nonpositive_chain_attempts_rejected():
    with pytest.raises(ChainSpecError, match="at least 1"):
        generate_chain(PARTS, max_chain_attempts=0)


# -- tests for verify_chain ---------------------------------------------------

from harness.verify import FidelityError, verify_chain


def test_verify_chain_passes_on_generated_chain():
    data = generate_chain(PARTS, difficulty="easy", seed=7)
    assert verify_chain(data, difficulty="easy") is True


def test_verify_chain_catches_tampered_link():
    """Tamper only the recorded link — parts stay individually valid, so this
    isolates the link assertion (a broken given would trip part checks first)."""
    data = generate_chain(PARTS, difficulty="easy", seed=7)
    data["links"][0]["exact"] = "999999"
    with pytest.raises(FidelityError, match=r"\(link\)"):
        verify_chain(data, difficulty="easy")


def test_chain_sweep_across_bands():
    """Generate + fully verify representative chains on every difficulty band."""
    for band in ("easy", "medium", "hard"):
        data = generate_chain(PARTS, difficulty=band, seed=5)
        assert verify_chain(data, difficulty=band) is True
    parts2 = [
        {"topic": "suvat", "given": ["u", "a", "t"], "find": "v"},
        {"topic": "upward-throw", "given": ["u", "g", "t"], "find": "h",
         "receive": "u"},
    ]
    for band in ("easy", "medium"):
        data = generate_chain(parts2, difficulty=band, seed=5)
        assert verify_chain(data, difficulty=band) is True


# -- tests for the CLI --part flags --------------------------------------------

from engine.__main__ import main


def test_cli_chain_json_verify(capsys):
    rc = main([
        "--part", "free-fall", "--part", "suvat:u,a,t:s:u",
        "--seed", "7", "--json", "--verify",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["topic"] == "mixed"
    assert data["topics"] == ["free-fall", "suvat"]


def test_cli_chain_auto_receive(capsys):
    """suvat given u,a,t has exactly one m/s given (u) — receive is inferred."""
    rc = main(["--part", "free-fall", "--part", "suvat:u,a,t:s", "--seed", "7"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "topic: mixed (free-fall + suvat)" in out
    assert "part 1" in out and "part 2" in out


def test_cli_chain_ambiguous_receive_is_loud():
    """suvat given u,v,t (find s) has two m/s givens — must demand :RECEIVE."""
    with pytest.raises(SystemExit, match="u.*v|v.*u"):
        main(["--part", "free-fall", "--part", "suvat:u,v,t:s"])


def test_cli_chain_needs_two_parts():
    with pytest.raises(SystemExit, match="at least two"):
        main(["--part", "free-fall"])


def test_cli_chain_rejects_topic_mix():
    with pytest.raises(SystemExit, match="--part cannot be combined"):
        main(["--part", "free-fall", "--part", "suvat:u,a,t:s:u",
              "--given", "u,a,t"])


def test_cli_chain_unknown_topic_is_loud(capsys):
    """An unknown --part topic reports error: ... and exits 1, no traceback."""
    rc = main(["--part", "bogus-topic", "--part", "suvat:u,a,t:s:u"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "error:" in err and "bogus-topic" in err


# --- sanctioned links (physical composition, not just matching units) --------


def test_cross_convention_link_is_refused():
    """free-fall is down-positive; upward-throw is up-positive.

    Feeding a falling speed straight into a launch speed type-checks — both are
    m/s — but silently flips the sign convention: nothing in the problem says
    the body bounced. Unit compatibility is not physical compatibility, so the
    pair must be sanctioned explicitly or refused.
    """
    with pytest.raises(UnsanctionedLinkError, match="free-fall"):
        generate_chain([
            {"topic": "free-fall"},
            {"topic": "upward-throw", "given": ["u", "g", "t"], "find": "v",
             "receive": "u"},
        ], seed=5)


def test_refusal_names_the_pair_and_how_to_sanction_it():
    """The message has to tell an author what to do next."""
    with pytest.raises(UnsanctionedLinkError) as excinfo:
        generate_chain([
            {"topic": "free-fall"},
            {"topic": "upward-throw", "given": ["u", "g", "t"], "find": "v",
             "receive": "u"},
        ], seed=5)
    message = str(excinfo.value)
    assert "v" in message and "u" in message
    assert "SANCTIONED_LINKS" in message


def test_every_sanctioned_link_carries_a_narrative():
    """A pair is admitted because someone wrote down why it makes sense."""
    assert SANCTIONED_LINKS
    for (from_topic, from_find, to_topic, to_receive), why in SANCTIONED_LINKS.items():
        assert all(isinstance(part, str) and part for part in
                   (from_topic, from_find, to_topic, to_receive))
        assert isinstance(why, str) and len(why) > 30, (from_topic, to_topic)
