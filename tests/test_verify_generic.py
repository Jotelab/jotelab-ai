"""Topic-generic Data-Fidelity verify_generic; suvat.verify delegates (ADR-007)."""

import json
from pathlib import Path
from templates.declarative import parse_template
from engine import registry
from engine.loop import generate
from harness.verify import verify_generic, verify

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def test_verify_generic_passes_on_data_template():
    tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    with registry.temporary(tpl):
        data = generate("suvat", given=("u", "a", "t"), find="v", difficulty="medium", seed=99)
    assert verify_generic(data, tpl, difficulty="medium") is True


def test_existing_suvat_verify_still_works():
    data = generate("suvat", given=("u", "a", "t"), find="v",
                    conditions={"u": 0, "a": 2, "t": 5}, difficulty="easy", seed=80421)
    assert verify(data, difficulty="easy") is True
