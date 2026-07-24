"""Byte-for-byte parity: declarative SUVAT == code SUVAT (ADR-007 v1 exit gate).

The single test that ratifies ADR-007 v1: the declarative ``suvat.json`` must drive
the unchanged loop to emit ``sympy_data`` *byte-for-byte identical* to the code
``templates.suvat.SUVAT`` across the full Data-Fidelity batch, and pass the generic
fidelity oracle at 100%.
"""

import json
from pathlib import Path
from engine import registry
from engine.loop import generate
from harness.batches import suvat_batch
from harness.verify import verify_generic
from templates.declarative import parse_template

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def _gen(req):
    return generate(req["topic"], given=[s.name for s in req["given"]],
                    find=req["find"].name, difficulty=req["difficulty"], seed=req["seed"])


def test_declarative_suvat_is_byte_for_byte_identical_to_code_suvat():
    data_tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    batch = suvat_batch(n_seeds=6)  # every split x 3 bands x 6 seeds
    mismatches = []
    for req in batch:
        code_out = _gen(req)  # code SUVAT is the registered "suvat"
        with registry.temporary(data_tpl):
            data_out = _gen(req)
        if json.dumps(code_out, sort_keys=True) != json.dumps(data_out, sort_keys=True):
            mismatches.append((req["given"], req["find"], req["difficulty"], req["seed"]))
    assert not mismatches, f"{len(mismatches)} parity mismatches, first: {mismatches[:3]}"


def test_declarative_suvat_batch_fidelity_100_percent():
    # Independent full-system re-derivation is expensive, so fewer seeds here; the
    # byte-parity test above already covers the wider batch generate-only.
    data_tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    with registry.temporary(data_tpl):
        for req in suvat_batch(n_seeds=3):
            data = _gen(req)
            assert verify_generic(data, data_tpl, difficulty=req["difficulty"]) is True


def test_parity_holds_for_negative_finds():
    # The three exam-problem shapes the signed fallback exists for
    # (spec 2026-07-24): a = -10, v = -8, s = -150.
    data_tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    cases = [
        (["u", "v", "t"], "a", {"u": 30, "v": 10, "t": 2}, "-10"),
        (["a", "s", "t"], "v", {"a": -10, "s": 4, "t": 2}, "-8"),
        (["u", "a", "t"], "s", {"u": 5, "a": -10, "t": 6}, "-150"),
    ]
    for given, find, conds, expected in cases:
        code_out = generate("suvat", given=given, find=find, conditions=conds,
                            difficulty="medium", seed=7)
        with registry.temporary(data_tpl):
            data_out = generate("suvat", given=given, find=find,
                                conditions=conds, difficulty="medium", seed=7)
        assert code_out["final_answer"]["exact"] == expected
        assert (json.dumps(code_out, sort_keys=True)
                == json.dumps(data_out, sort_keys=True))
