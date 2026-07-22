"""The optional graph_spec hook: a template may attach engine-computed graph
data to sympy_data; every hook-less topic's contract is unchanged (no "graph"
key)."""

import dataclasses

from engine import registry
from engine.loop import generate


def test_topics_without_hook_emit_no_graph_key():
    data = generate("suvat", difficulty="easy", seed=3)
    assert "graph" not in data


def test_hooked_template_emits_graph_payload():
    base = registry.load_template("suvat")
    seen = {}

    def spec(values):
        seen.update(values)
        return {"kind": "test", "n": len(values)}

    hooked = dataclasses.replace(base, graph_spec=spec)
    with registry.temporary(hooked):
        data = generate("suvat", difficulty="easy", seed=3)
    assert data["graph"] == {"kind": "test", "n": 4}  # 3 givens + the find
    find_sym = base.symbol(data["find"]["symbol"])
    assert find_sym in seen  # the hook sees the solved find, not just givens
