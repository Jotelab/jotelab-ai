"""The optional diagram_spec hook: a template may attach an engine-authored
figure spec to sympy_data. Every hook-less topic's contract is unchanged (no
"diagram" key). Replaces the graph_spec contract test — see spec 2026-07-27."""

import dataclasses

from engine import registry
from engine.loop import generate


def test_topics_without_hook_emit_no_diagram_key():
    """A template with no diagram_spec emits no "diagram" key at all.

    Constructed rather than naming a real topic: by the end of this plan every
    registered topic has a hook, so any named example would go stale.
    """
    base = registry.load_template("suvat")
    hookless = dataclasses.replace(base, diagram_spec=None)
    with registry.temporary(hookless):
        data = generate("suvat", difficulty="easy", seed=3)
    assert "diagram" not in data


def test_graph_key_is_gone_entirely():
    """graph_spec is superseded; nothing may still emit the old key."""
    data = generate("motion-graphs", difficulty="easy", seed=3)
    assert "graph" not in data


def test_hooked_template_receives_a_context_and_emits_its_payload():
    base = registry.load_template("suvat")
    seen = {}

    def spec(ctx):
        seen["values"] = ctx.values
        seen["given"] = ctx.given
        seen["find"] = ctx.find
        return {"kind": "test", "n": len(ctx.values)}

    hooked = dataclasses.replace(base, diagram_spec=spec)
    with registry.temporary(hooked):
        data = generate("suvat", difficulty="easy", seed=3)

    assert data["diagram"] == {"kind": "test", "n": 4}  # 3 givens + the find
    find_sym = base.symbol(data["find"]["symbol"])
    assert seen["find"] == find_sym
    assert find_sym in seen["values"]      # the hook sees the solved answer
    assert find_sym not in seen["given"]   # ...but knows it is not a given
