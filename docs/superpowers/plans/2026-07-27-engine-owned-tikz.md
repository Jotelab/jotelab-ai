# Engine-Owned TikZ Diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move authorship of diagram geometry and every glyph in it from the LLM to the symbolic engine, across all nine linear-motion topics.

**Architecture:** Each topic template gains an optional `diagram_spec` hook (replacing today's `graph_spec`) that returns a JSON-able **diagram spec** — not TikZ source — carried at `sympy_data["diagram"]`. Because `sympy_data` is already persisted whole, this needs no DB migration. The web app parses the spec at its Zod trust boundary and serializes it to TikZ with a pure renderer; the existing ADR-006 compile pipeline is untouched. There is **no web-side fallback** — no spec means no diagram.

**Tech Stack:** Python 3 + SymPy + pytest (engine, repo `jotelab-ai`); TypeScript + Zod + Vitest + Next.js (web, repo `physics-jotelab`); node-tikzjax for TeX→SVG.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-27-engine-owned-tikz-design.md`. Read it before Task 1.
- **Two repositories.** Tasks 1–11 are in `jotelab-ai` (this worktree). Tasks 12–17 are in `physics-jotelab`, which gets **its own worktree** (see the Web tasks header) — never commit web changes from the engine worktree, and never work on its `master`.
- **Python interpreter.** This worktree has no `.venv`. Run every Python command through the main checkout's interpreter:
  `/home/thanakorn/Projects/Jotelab-Project/jotelab-ai/jotelab-ai/.venv/bin/python -m pytest`
  (and `… -m engine --topic X --verify`, `… -m templates.declarative`). A bare `pytest` or `python3` will fail with `ModuleNotFoundError: No module named 'sympy'`.
- **Baseline:** 156 tests pass before Task 1, in ~2 minutes. The suite must be green at the end of every task.
- **Task 10 is merged into Task 5.** Do not dispatch it.
- **ADR-005 two-form numbers.** Every numeric field carries `value` (display only, `to_display`) *and* `exact` (authoritative string, `to_exact`). Never emit one without the other.
- **Answer-hiding is by omission.** An element bound to the find symbol carries **no** `value` and **no** `exact` key. This is the load-bearing invariant; `role` tagging is presentation only.
- **`plot-2d` is the exception.** Its polyline and axis values are always shown (they are the problem statement for graph-reading splits). Only *annotation* of the find quantity is withheld.
- **No Thai in TikZ.** Labels are math symbols, digits, and Latin units only — node-tikzjax has no Thai fonts.
- **The LLM authors prose only.** Nothing in this plan may reintroduce a model-authored diagram path.
- **Test commands** must appear in every doc change (project convention).

---

## File Structure

**Engine (`jotelab-ai`):**

| File | Responsibility |
| --- | --- |
| `templates/diagrams.py` | **New.** `DiagramContext` + the three shared builders (`motion_1d`, `plot_2d`, `actors`) and the TeX label map. The answer-hiding rule lives here, in one function. |
| `templates/base.py` | `Template.graph_spec` → `Template.diagram_spec`. |
| `engine/contract.py` | `build_sympy_data` emits `data["diagram"]`. |
| `templates/{suvat,average_speed,multi_stage,upward_throw,distance_displacement,motion_graphs}.py` | One `diagram_spec=` hook each. |
| `templates/declarative/parse.py` | Optional `"diagram"` JSON key → a `diagram_spec` closure. |
| `templates/declarative/gate.py` | Validate symbols named in `"diagram"`. |
| `templates/data/{vectors_1d,free_fall,relative_velocity}.json` | Declare `"diagram"` structure. |
| `tests/test_diagrams.py` | Builder unit tests. |
| `tests/test_diagram_contract.py` | Replaces `test_graph_contract.py`: hook wiring. |
| `tests/test_diagram_invariants.py` | Cross-topic find-omission sweep. |

**Web (`physics-jotelab`):**

| File | Responsibility |
| --- | --- |
| `lib/engine/sympy-data.ts` | Optional `diagramSchema` at the trust boundary. |
| `lib/tikz/diagram/spec-to-tikz.ts` | **New.** Pure `spec → tikzpicture`. No physics. |
| `lib/tikz/diagram/spec-to-tikz.test.ts` | Golden TikZ per kind. |
| `lib/tikz/attach-diagram.ts` | Call `specToTikz`; no fallback. |
| `lib/tikz/templates/` | **Deleted.** |
| `docs/adr/008-engine-owned-diagrams.md` | **New.** Records the contract. |

---

## Task 1: Confirm the engine transport

The spec's one open assumption. This is investigation with a written outcome, not code — but it gates how much work Tasks 12–17 really are, so it runs first.

**Files:**
- Modify: `docs/superpowers/specs/2026-07-27-engine-owned-tikz-design.md` (the "Assumption to confirm" section)

- [ ] **Step 1: Locate the engine HTTP service**

`physics-jotelab/lib/engine/client.ts` posts to `${ENGINE_BASE_URL}/generate` and documents it as `jotelab-ai service/app.py`, which does not exist in this repo.

```bash
# In the engine repo:
git log --all --oneline -- 'service/*' | head
git branch -a
# In the web repo:
grep -rn "ENGINE_BASE_URL" .env.example
```

- [ ] **Step 2: Record the finding**

Replace the spec's "Assumption to confirm" section with one of:

- **Service exists (deployed elsewhere):** note where, and confirm it serializes `build_sympy_data`'s return verbatim — if it does, `diagram` flows through with zero transport work.
- **Service does not exist:** note that a `POST /generate` FastAPI wrapper over `engine.loop.generate` is a **prerequisite**, and stop. That work is out of this plan's scope and needs its own spec.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-07-27-engine-owned-tikz-design.md
git commit -m "docs: record engine transport finding for diagram contract"
```

---

## Task 2: `templates/diagrams.py` — context and the answer-hiding rule

The single most important task: the omission invariant is implemented once, here, and every topic inherits it.

**Files:**
- Create: `templates/diagrams.py`
- Test: `tests/test_diagrams.py`

**Interfaces:**
- Consumes: `engine.contract.to_display`, `engine.contract.to_exact`.
- Produces: `DiagramContext(template, values, given, find)` with method `.label(sym, tex=None) -> dict | None`; module constant `TEX_LABELS: dict[str, str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diagrams.py
"""The shared diagram builders. The answer-hiding rule (find elements carry no
value/exact) is enforced in DiagramContext.label, so every topic inherits it."""

import sympy

from templates.diagrams import DiagramContext
from templates.suvat import SUVAT


def _ctx(find_name="v"):
    u, a, t, v = (SUVAT.symbol(n) for n in ("u", "a", "t", "v"))
    values = {u: sympy.Integer(5), a: sympy.Integer(2),
              t: sympy.Integer(3), v: sympy.Integer(11)}
    return DiagramContext(SUVAT, values, given={u, a, t},
                          find=SUVAT.symbol(find_name))


def test_given_label_carries_both_numeric_forms_and_unit():
    label = _ctx().label(SUVAT.symbol("u"))
    assert label == {"symbol": "u", "label": "v_0", "role": "given",
                     "value": 5, "exact": "5", "unit": "m/s"}


def test_find_label_omits_value_and_exact():
    """The load-bearing invariant: the answer is never on the wire."""
    label = _ctx().label(SUVAT.symbol("v"))
    assert label == {"symbol": "v", "label": "v", "role": "find"}
    assert "value" not in label and "exact" not in label


def test_non_given_non_find_symbol_is_derived():
    """A value the engine computed that is not the answer is safe to show."""
    ctx = _ctx(find_name="s")
    ctx.values[SUVAT.symbol("v")] = sympy.Integer(11)
    label = ctx.label(SUVAT.symbol("v"))
    assert label["role"] == "derived"
    assert label["exact"] == "11"


def test_symbol_absent_from_the_instance_yields_none():
    """Callers drop the element entirely rather than drawing an empty arrow."""
    ctx = _ctx()
    del ctx.values[SUVAT.symbol("a")]
    assert ctx.label(SUVAT.symbol("a")) is None


def test_exact_form_survives_a_non_terminating_rational():
    """ADR-005: exact is authoritative; value may be a lossy round."""
    ctx = _ctx()
    ctx.values[SUVAT.symbol("u")] = sympy.Rational(1, 3)
    label = ctx.label(SUVAT.symbol("u"))
    assert label["exact"] == "1/3"
    assert label["value"] == 0.333333
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagrams.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'templates.diagrams'`

- [ ] **Step 3: Write minimal implementation**

```python
# templates/diagrams.py
"""Shared diagram-spec builders (spec 2026-07-27, engine-owned TikZ).

A template declares an optional ``diagram_spec`` hook; these builders turn the
instance's values plus its split into the JSON-able payload carried at
``sympy_data["diagram"]``. The web app serializes that payload to TikZ — it
derives nothing and decides nothing beyond obeying ``role``.

**The answer-hiding rule lives in :meth:`DiagramContext.label` and nowhere
else.** An element bound to the find symbol is emitted without ``value`` or
``exact``, so no downstream bug can leak the answer: there is nothing to leak.
"""

from __future__ import annotations

from engine.contract import to_display, to_exact

# Engine symbol name -> the TeX math label drawn in the figure. Math and Latin
# only: node-tikzjax embeds Computer Modern, and Thai would fail to compile.
TEX_LABELS = {
    "u": "v_0", "v": "v", "a": "a", "t": "t", "s": "s",
    "g": "g", "h": "h",
    "t1": "t_1", "t2": "t_2",
    "d1": "d_1", "d2": "d_2", "disp": r"\Delta x", "dist": "d",
    "sp": "v", "vavg": r"\bar{v}",
    "va": "v_A", "vb": "v_B", "vab": "v_{AB}",
}


class DiagramContext:
    """Everything a diagram builder needs about one generated instance.

    ``values`` holds ``given ∪ {find}`` (the solved answer included), ``given``
    is the set of sampled symbols, and ``find`` is the single target symbol.
    """

    def __init__(self, template, values, given, find):
        self.template = template
        self.values = dict(values)
        self.given = set(given)
        self.find = find

    def label(self, sym, tex=None):
        """One labelled quantity, or ``None`` if this instance has no such value.

        Returns a value-less dict when ``sym`` is the find target — see the
        module docstring. ``None`` tells the caller to omit the element rather
        than draw an unlabelled one.
        """
        if sym is None:
            return None
        out = {"symbol": sym.name, "label": tex or TEX_LABELS.get(sym.name, sym.name)}
        if sym == self.find:
            out["role"] = "find"
            return out
        if sym not in self.values:
            return None
        out["role"] = "given" if sym in self.given else "derived"
        out["value"] = to_display(self.values[sym])
        out["exact"] = to_exact(self.values[sym])
        out["unit"] = self.template.unit_for(sym)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_diagrams.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add templates/diagrams.py tests/test_diagrams.py
git commit -m "feat(engine): DiagramContext with answer-hiding label rule"
```

---

## Task 3: The `motion_1d` builder

**Files:**
- Modify: `templates/diagrams.py`
- Test: `tests/test_diagrams.py`

**Interfaces:**
- Consumes: `DiagramContext` from Task 2.
- Produces: `motion_1d(ctx, *, orientation="horizontal", segments) -> dict`. `segments` is a list of dicts whose keys are a subset of `direction`, `velocity_in`, `acceleration`, `velocity_out`, `span`, `duration`; every value except `direction` is a **SymPy symbol**, and `direction` is `"forward"` or `"reverse"`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_diagrams.py
from templates.diagrams import motion_1d


def test_motion_1d_emits_kind_orientation_and_segments():
    ctx = _ctx()
    spec = motion_1d(ctx, segments=[{
        "velocity_in": SUVAT.symbol("u"),
        "acceleration": SUVAT.symbol("a"),
        "velocity_out": SUVAT.symbol("v"),
        "duration": SUVAT.symbol("t"),
    }])
    assert spec["kind"] == "motion-1d"
    assert spec["orientation"] == "horizontal"
    assert len(spec["segments"]) == 1
    seg = spec["segments"][0]
    assert seg["direction"] == "forward"
    assert seg["velocity_in"]["exact"] == "5"
    assert seg["velocity_out"] == {"symbol": "v", "label": "v", "role": "find"}


def test_motion_1d_drops_roles_absent_from_the_instance():
    """s is not in this split, so no displacement bracket is drawn."""
    ctx = _ctx()
    spec = motion_1d(ctx, segments=[{
        "velocity_in": SUVAT.symbol("u"),
        "span": SUVAT.symbol("s"),
    }])
    assert "span" not in spec["segments"][0]
    assert "velocity_in" in spec["segments"][0]


def test_motion_1d_carries_orientation_and_reverse_direction():
    """Vertical + reversal is the upward-throw / out-and-back shape."""
    ctx = _ctx()
    spec = motion_1d(ctx, orientation="vertical", segments=[
        {"velocity_in": SUVAT.symbol("u")},
        {"direction": "reverse", "velocity_out": SUVAT.symbol("v")},
    ])
    assert spec["orientation"] == "vertical"
    assert [s["direction"] for s in spec["segments"]] == ["forward", "reverse"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagrams.py -k motion_1d -v`
Expected: FAIL with `ImportError: cannot import name 'motion_1d'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to templates/diagrams.py

SEGMENT_ROLES = ("velocity_in", "acceleration", "velocity_out", "span", "duration")


def motion_1d(ctx, *, orientation="horizontal", segments):
    """A 1-D motion figure: an oriented axis plus ordered segments.

    Segments are ordered because ``upward-throw`` (up then down) and
    ``distance-displacement`` (out then back) reverse direction mid-problem;
    a flat element bag cannot express that. Roles whose symbol is absent from
    this instance are dropped, so the figure is variable-consistent — it draws
    only what the problem actually involves.
    """
    built = []
    for seg in segments:
        out = {"direction": seg.get("direction", "forward")}
        for role in SEGMENT_ROLES:
            label = ctx.label(seg.get(role))
            if label is not None:
                out[role] = label
        built.append(out)
    return {"kind": "motion-1d", "orientation": orientation, "segments": built}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_diagrams.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add templates/diagrams.py tests/test_diagrams.py
git commit -m "feat(engine): motion_1d diagram builder with ordered segments"
```

---

## Task 4: `plot_2d` and `actors` builders

**Files:**
- Modify: `templates/diagrams.py`
- Test: `tests/test_diagrams.py`

**Interfaces:**
- Produces:
  - `plot_2d(ctx, *, axes, points) -> dict` — `axes` is `{"x": {"symbol": str, "unit": str}, "y": {...}}`; `points` is a list of `(x_sympy, y_sympy)` pairs. Emits `{"kind": "plot-2d", "axes": ..., "points": [{"x": {"value","exact"}, "y": {...}}, ...]}`.
  - `actors(ctx, *, bodies) -> dict` — `bodies` is a list of `{"name": str, "velocity": sympy.Symbol}`. Emits `{"kind": "actors", "bodies": [{"name": str, "velocity": <label>}, ...]}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_diagrams.py
from templates.diagrams import actors, plot_2d


def test_plot_2d_emits_two_form_points_and_shows_all_values():
    """plot-2d is the deliberate exception: the polyline IS the problem
    statement for graph-reading splits, so points are always shown."""
    ctx = _ctx(find_name="s")
    spec = plot_2d(
        ctx,
        axes={"x": {"symbol": "t", "unit": "s"},
              "y": {"symbol": "v", "unit": "m/s"}},
        points=[(sympy.Integer(0), sympy.Integer(4)),
                (sympy.Integer(3), sympy.Integer(10))],
    )
    assert spec["kind"] == "plot-2d"
    assert spec["axes"]["y"] == {"symbol": "v", "unit": "m/s"}
    assert spec["points"][1] == {"x": {"value": 3, "exact": "3"},
                                 "y": {"value": 10, "exact": "10"}}


def test_plot_2d_never_annotates_the_find_quantity():
    """Points stay; a caption of the answer does not."""
    ctx = _ctx(find_name="s")
    spec = plot_2d(ctx, axes={"x": {"symbol": "t", "unit": "s"},
                              "y": {"symbol": "v", "unit": "m/s"}},
                   points=[(sympy.Integer(0), sympy.Integer(4))])
    assert "annotations" not in spec


def test_actors_labels_each_body_velocity():
    ctx = _ctx()
    spec = actors(ctx, bodies=[{"name": "A", "velocity": SUVAT.symbol("u")},
                               {"name": "B", "velocity": SUVAT.symbol("v")}])
    assert spec["kind"] == "actors"
    assert spec["bodies"][0]["name"] == "A"
    assert spec["bodies"][0]["velocity"]["exact"] == "5"
    assert spec["bodies"][1]["velocity"]["role"] == "find"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagrams.py -k "plot_2d or actors" -v`
Expected: FAIL with `ImportError: cannot import name 'actors'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to templates/diagrams.py

def plot_2d(ctx, *, axes, points):
    """A 2-D plot: labelled axes and a polyline.

    **The exception to the answer-hiding rule.** ``motion-graphs`` exists to
    produce graph-reading splits, where the student derives the slope (``a``) or
    the area under the polyline (``s``) *from the figure*. Withholding the
    polyline because the find is derivable from it would delete the question. So
    every point ships; what never ships is an *annotation* naming the find's
    value (no ``$a = 2$`` slope caption, no labelled shaded area).
    """
    return {
        "kind": "plot-2d",
        "axes": axes,
        "points": [
            {"x": {"value": to_display(x), "exact": to_exact(x)},
             "y": {"value": to_display(y), "exact": to_exact(y)}}
            for x, y in points
        ],
    }


def actors(ctx, *, bodies):
    """Two or more named bodies with velocity arrows on a shared axis.

    The relative-velocity figure: the frame comparison is the point, so each
    body is named rather than positioned.
    """
    built = []
    for body in bodies:
        label = ctx.label(body["velocity"])
        if label is None:
            continue
        built.append({"name": body["name"], "velocity": label})
    return {"kind": "actors", "bodies": built}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_diagrams.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add templates/diagrams.py tests/test_diagrams.py
git commit -m "feat(engine): plot_2d and actors diagram builders"
```

---

## Task 5: Wire the hook into `Template` and `build_sympy_data`, and convert `motion-graphs`

Replaces `graph_spec` outright. `tests/test_graph_contract.py` is rewritten, not deleted — its coverage of "hook-less topics emit no key" still matters.

**`motion-graphs` converts in this same task, deliberately.** Removing `graph_spec` breaks `tests/test_motion_graphs.py`, and deferring its repair to a later task would leave the suite red across several reviews — hiding any real regression inside an expected failure. Hook removal and hook replacement belong in one commit range.

**Files:**
- Modify: `templates/base.py:55`
- Modify: `engine/contract.py:136-139`
- Modify: `templates/motion_graphs.py:55-95`
- Modify: `tests/test_motion_graphs.py:14-40`
- Delete: `tests/test_graph_contract.py`
- Create: `tests/test_diagram_contract.py`

**Interfaces:**
- Consumes: `DiagramContext` (Task 2).
- Produces: `Template.diagram_spec: Callable = None`, taking a single `DiagramContext` and returning a JSON-able dict. Emitted at `sympy_data["diagram"]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diagram_contract.py
"""The optional diagram_spec hook: a template may attach an engine-authored
figure spec to sympy_data. Every hook-less topic's contract is unchanged (no
"diagram" key). Replaces the graph_spec contract test — see spec 2026-07-27."""

import dataclasses

from engine import registry
from engine.loop import generate


def test_topics_without_hook_emit_no_diagram_key():
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagram_contract.py -v`
Expected: FAIL — `dataclasses.replace` raises `TypeError: got an unexpected keyword argument 'diagram_spec'`

- [ ] **Step 3: Write minimal implementation**

In `templates/base.py`, replace the `graph_spec` field:

```python
    signed_answer: bool = False  # vector/direction topics: allow a negative answer
    # values -> JSON-able diagram payload ("diagram" key). Supersedes the former
    # graph_spec hook: the engine owns every glyph in a figure (spec 2026-07-27).
    diagram_spec: Callable = None
```

In `engine/contract.py`, replace the graph branch at the end of `build_sympy_data`:

```python
    if template.diagram_spec is not None:
        # Imported here, not at module scope: templates.diagrams imports
        # to_display/to_exact from this module, so a top-level import would
        # close an import cycle. Same deferral rationale as
        # registry._ensure_declarative_loaded.
        from templates.diagrams import DiagramContext

        values = dict(inputs)
        values[find] = value
        ctx = DiagramContext(template, values, given=set(given), find=find)
        data["diagram"] = template.diagram_spec(ctx)
    return data
```

In `templates/motion_graphs.py`, replace the `graph_spec` function (and drop its now-unused `_point` helper) with a `diagram_spec` that keeps the identical exact arithmetic:

```python
from .diagrams import plot_2d


def diagram_spec(ctx):
    """The v–t polyline ``(0, u) -> (t1, v) -> (t1+t2, v)``, exact.

    ``ctx.values`` holds ``given ∪ {find}`` only, so on the acceleration-form
    splits the cruise velocity is absent — it is derived exactly here
    (``v = u + a*t1``, SymPy arithmetic): engine-computed, invariant-safe.

    Every point ships even when the find is derivable from the figure: this
    topic's whole purpose is graph-reading splits (slope -> a, area -> s).
    """
    values = ctx.values
    uu, tt1, tt2 = values[u], values[t1], values[t2]
    vv = values[v] if v in values else sympy.nsimplify(uu + values[a] * tt1)
    return plot_2d(
        ctx,
        axes={"x": {"symbol": "t", "unit": "s"},
              "y": {"symbol": "v", "unit": "m/s"}},
        points=[(0, uu), (tt1, vv), (tt1 + tt2, vv)],
    )
```

then replace `graph_spec=graph_spec,` with `diagram_spec=diagram_spec,` in the `MOTION_GRAPHS = Template(...)` call.

- [ ] **Step 4: Update the motion-graphs tests**

In `tests/test_motion_graphs.py`, repoint the helper and the shape assertion at the new key. **The physics assertions (area == displacement, etc.) stay exactly as they are** — only the path into the payload changes:

```python
def _exact_points(data):
    return [(sympy.Rational(p["x"]["exact"]), sympy.Rational(p["y"]["exact"]))
            for p in data["diagram"]["points"]]


def test_graph_payload_shape_and_values():
    """u=4, a=2, t1=3, t2=5: polyline (0,4) -> (3,10) -> (8,10)."""
    data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 4, "a": 2, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["diagram"]["kind"] == "plot-2d"
    assert data["diagram"]["axes"] == {"x": {"symbol": "t", "unit": "s"},
                                       "y": {"symbol": "v", "unit": "m/s"}}
    assert _exact_points(data) == [(0, 4), (3, 10), (8, 10)]
    assert data["find"]["exact"] == "71"
```

Also update the module docstring's `sympy_data["graph"]` reference to `sympy_data["diagram"]`.

- [ ] **Step 5: Run the full suite — it must be green**

```bash
pytest tests/test_diagram_contract.py tests/test_motion_graphs.py -v
pytest
python -m engine --topic motion-graphs --verify
```
Expected: **the entire suite passes.** Removing the old hook and installing the new one happen together precisely so there is no red window. If anything is red, do not commit.

- [ ] **Step 6: Commit**

```bash
git rm tests/test_graph_contract.py
git add templates/base.py engine/contract.py templates/motion_graphs.py tests/test_diagram_contract.py tests/test_motion_graphs.py
git commit -m "feat(engine): diagram_spec hook replaces graph_spec; motion-graphs emits plot-2d"
```

---

## Task 6: `suvat` and `vectors-1d` diagrams

`vectors-1d` is declarative, so this task also builds the JSON `"diagram"` parser.

**Files:**
- Modify: `templates/suvat.py:152`
- Modify: `templates/declarative/parse.py:137-180`
- Modify: `templates/data/vectors_1d.json`
- Test: `tests/test_suvat.py`, `tests/test_vectors_1d.py`

**Interfaces:**
- Consumes: `motion_1d`, `DiagramContext`.
- Produces: `templates.declarative.parse._diagram_hook(doc, symbols) -> Callable | None`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_suvat.py
def test_diagram_is_variable_consistent_and_hides_the_answer():
    """The figure draws the split's own quantities, and never the answer."""
    data = generate("suvat", given=("u", "a", "t"), find="v",
                    difficulty="easy", seed=7)
    seg = data["diagram"]["segments"][0]
    assert data["diagram"]["kind"] == "motion-1d"
    assert data["diagram"]["orientation"] == "horizontal"
    assert seg["velocity_in"]["role"] == "given"
    assert seg["velocity_out"] == {"symbol": "v", "label": "v", "role": "find"}
    assert "span" not in seg          # s is not in this split
    assert seg["duration"]["unit"] == "s"
```

```python
# append to tests/test_vectors_1d.py
def test_declarative_diagram_key_produces_a_motion_1d_spec():
    data = generate("vectors-1d", given=("s", "t"), find="v",
                    difficulty="easy", seed=4)
    seg = data["diagram"]["segments"][0]
    assert data["diagram"]["kind"] == "motion-1d"
    assert seg["span"]["symbol"] == "s"
    assert seg["velocity_out"]["role"] == "find"
    assert "value" not in seg["velocity_out"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_suvat.py::test_diagram_is_variable_consistent_and_hides_the_answer tests/test_vectors_1d.py::test_declarative_diagram_key_produces_a_motion_1d_spec -v`
Expected: FAIL with `KeyError: 'diagram'`

- [ ] **Step 3: Write minimal implementation**

In `templates/suvat.py`, add the hook and its import:

```python
from .diagrams import motion_1d


def diagram_spec(ctx):
    """One forward segment carrying whichever of u/a/v/s/t this split uses."""
    return motion_1d(ctx, segments=[{
        "velocity_in": u, "acceleration": a, "velocity_out": v,
        "span": s, "duration": t,
    }])
```

and pass `diagram_spec=diagram_spec,` in the `SUVAT = Template(...)` call.

In `templates/declarative/parse.py`, add the hook compiler and call it:

```python
from templates.diagrams import actors as _actors
from templates.diagrams import motion_1d as _motion_1d


def _diagram_hook(doc, symbols):
    """Compile an optional "diagram" JSON block into a diagram_spec callable.

    The JSON declares *structure only* — which builder, and how the topic's
    symbols map onto its roles. Values, roles, and units are filled in at
    generation time by the shared builder, so a declarative topic can never
    author a number.
    """
    decl = doc.get("diagram")
    if decl is None:
        return None

    kind = decl.get("kind")
    if kind == "motion-1d":
        orientation = decl.get("orientation", "horizontal")
        segments = []
        for seg in decl.get("segments", []):
            out = {"direction": seg.get("direction", "forward")}
            for role, name in seg.items():
                if role == "direction":
                    continue
                try:
                    out[role] = symbols[name]
                except KeyError:
                    _fail(f"diagram references undeclared variable {name!r}")
            segments.append(out)
        return lambda ctx: _motion_1d(ctx, orientation=orientation,
                                      segments=segments)

    if kind == "actors":
        bodies = []
        for body in decl.get("bodies", []):
            try:
                bodies.append({"name": body["name"],
                               "velocity": symbols[body["velocity"]]})
            except KeyError as exc:
                _fail(f"diagram body is malformed or undeclared: {exc}")
        return lambda ctx: _actors(ctx, bodies=bodies)

    _fail(f"unknown diagram kind {kind!r}")
```

and in `parse_template`'s `return Template(...)`, add:

```python
        signed_answer=bool(doc.get("signed_answer", False)),
        diagram_spec=_diagram_hook(doc, symbols),
```

In `templates/data/vectors_1d.json`, add a top-level key:

```json
  "diagram": {
    "kind": "motion-1d",
    "orientation": "horizontal",
    "segments": [
      {"direction": "forward", "velocity_out": "v", "span": "s", "duration": "t"}
    ]
  }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_suvat.py tests/test_vectors_1d.py -v
pytest tests/test_declarative_parse.py -v
python -m engine --topic suvat --verify
python -m engine --topic vectors-1d --verify
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/suvat.py templates/declarative/parse.py templates/data/vectors_1d.json tests/test_suvat.py tests/test_vectors_1d.py
git commit -m "feat(engine): suvat and vectors-1d diagram specs"
```

---

## Task 7: `free-fall` and `relative-velocity` (declarative, vertical + actors)

**Files:**
- Modify: `templates/data/free_fall.json`, `templates/data/relative_velocity.json`
- Modify: `templates/declarative/gate.py`
- Test: `tests/test_free_fall.py`, `tests/test_relative_velocity.py`, `tests/test_validation_gate.py`

**Interfaces:**
- Consumes: `_diagram_hook` (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_free_fall.py
def test_diagram_is_vertical_and_hides_the_answer():
    data = generate("free-fall", given=("u", "g", "t"), find="v",
                    difficulty="easy", seed=2)
    assert data["diagram"]["orientation"] == "vertical"
    seg = data["diagram"]["segments"][0]
    assert seg["acceleration"]["symbol"] == "g"
    assert "exact" not in seg["velocity_out"]
```

```python
# append to tests/test_relative_velocity.py
def test_diagram_names_both_bodies():
    data = generate("relative-velocity", given=("va", "vb"), find="vab",
                    difficulty="easy", seed=5)
    assert data["diagram"]["kind"] == "actors"
    assert [b["name"] for b in data["diagram"]["bodies"]] == ["A", "B"]
    assert data["diagram"]["bodies"][0]["velocity"]["role"] == "given"
```

```python
# append to tests/test_validation_gate.py
def test_gate_rejects_a_diagram_naming_an_undeclared_variable():
    """A typo in a declarative diagram must fail the gate, not ship silently."""
    import json
    import pathlib

    import pytest

    from templates.declarative.parse import parse_template

    doc = json.loads(
        (pathlib.Path("templates/data/free_fall.json")).read_text()
    )
    doc["diagram"]["segments"][0]["velocity_in"] = "nope"
    with pytest.raises(Exception, match="undeclared variable"):
        parse_template(doc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_free_fall.py tests/test_relative_velocity.py tests/test_validation_gate.py -v`
Expected: FAIL with `KeyError: 'diagram'`

- [ ] **Step 3: Write minimal implementation**

In `templates/data/free_fall.json`:

```json
  "diagram": {
    "kind": "motion-1d",
    "orientation": "vertical",
    "segments": [
      {"direction": "forward", "velocity_in": "u", "acceleration": "g",
       "velocity_out": "v", "span": "h", "duration": "t"}
    ]
  }
```

In `templates/data/relative_velocity.json`:

```json
  "diagram": {
    "kind": "actors",
    "bodies": [{"name": "A", "velocity": "va"}, {"name": "B", "velocity": "vb"}]
  }
```

The gate check is already delivered by `_diagram_hook`'s `_fail` calls from Task 6 — verify the test passes without new code. If `_fail` does not raise on the undeclared symbol, fix `_diagram_hook`, not the test.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_free_fall.py tests/test_relative_velocity.py tests/test_validation_gate.py -v
python -m templates.declarative
python -m engine --topic free-fall --verify
python -m engine --topic relative-velocity --verify
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/data/free_fall.json templates/data/relative_velocity.json tests/test_free_fall.py tests/test_relative_velocity.py tests/test_validation_gate.py
git commit -m "feat(engine): free-fall and relative-velocity diagram specs"
```

---

## Task 8: `average-speed` and `multi-stage-motion` (two forward segments)

**Files:**
- Modify: `templates/average_speed.py:93`, `templates/multi_stage.py:131`
- Test: `tests/test_average_speed.py`, `tests/test_multi_stage.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_average_speed.py
def test_diagram_draws_both_legs():
    data = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    difficulty="easy", seed=6)
    segs = data["diagram"]["segments"]
    assert len(segs) == 2
    assert segs[0]["span"]["symbol"] == "d1"
    assert segs[1]["span"]["symbol"] == "d2"
    assert all(s["direction"] == "forward" for s in segs)
```

```python
# append to tests/test_multi_stage.py
def test_diagram_draws_the_two_phases_with_their_own_durations():
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    difficulty="easy", seed=6)
    segs = data["diagram"]["segments"]
    assert len(segs) == 2
    assert segs[0]["acceleration"]["symbol"] == "a"
    assert segs[0]["duration"]["symbol"] == "t1"
    assert segs[1]["duration"]["symbol"] == "t2"
    assert "acceleration" not in segs[1]   # phase 2 is constant-velocity
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_average_speed.py tests/test_multi_stage.py -k diagram -v`
Expected: FAIL with `KeyError: 'diagram'`

- [ ] **Step 3: Write minimal implementation**

In `templates/average_speed.py`, add `from .diagrams import motion_1d` and:

```python
def diagram_spec(ctx):
    """Two sequential legs on one line; the rate label rides on the whole trip."""
    return motion_1d(ctx, segments=[
        {"span": d1},
        {"span": d2, "duration": t},
    ])
```

then pass `diagram_spec=diagram_spec,` in `AVERAGE_SPEED = Template(...)`.

In `templates/multi_stage.py`, add `from .diagrams import motion_1d` and:

```python
def diagram_spec(ctx):
    """Phase 1 accelerates from u to the cruise velocity; phase 2 holds it."""
    return motion_1d(ctx, segments=[
        {"velocity_in": u, "acceleration": a, "velocity_out": v,
         "duration": t1},
        {"velocity_in": v, "duration": t2, "span": s},
    ])
```

then pass `diagram_spec=diagram_spec,` in `MULTI_STAGE = Template(...)`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_average_speed.py tests/test_multi_stage.py -v
python -m engine --topic average-speed --verify
python -m engine --topic multi-stage-motion --verify
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/average_speed.py templates/multi_stage.py tests/test_average_speed.py tests/test_multi_stage.py
git commit -m "feat(engine): average-speed and multi-stage diagram specs"
```

---

## Task 9: `upward-throw` and `distance-displacement` (direction reversal)

The hard case the spec flags: both topics reverse direction mid-problem.

**Files:**
- Modify: `templates/upward_throw.py:128`, `templates/distance_displacement.py:93`
- Test: `tests/test_upward_throw.py`, `tests/test_distance_displacement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_upward_throw.py
def test_diagram_is_vertical_with_an_up_then_down_reversal():
    """The projectile rises, then falls: two segments, opposite directions."""
    data = generate("upward-throw", given=("u", "g", "t"), find="v",
                    difficulty="easy", seed=8)
    spec = data["diagram"]
    assert spec["orientation"] == "vertical"
    assert [s["direction"] for s in spec["segments"]] == ["forward", "reverse"]
    assert spec["segments"][0]["velocity_in"]["symbol"] == "u"
    assert spec["segments"][1]["velocity_out"]["role"] == "find"
```

```python
# append to tests/test_distance_displacement.py
def test_diagram_draws_the_out_and_back_legs():
    """d1 out, d2 back: the reversal is exactly what makes distance differ
    from displacement, so the figure must show it."""
    data = generate("distance-displacement", given=("d1", "d2"), find="disp",
                    difficulty="easy", seed=9)
    segs = data["diagram"]["segments"]
    assert [s["direction"] for s in segs] == ["forward", "reverse"]
    assert segs[0]["span"]["symbol"] == "d1"
    assert segs[1]["span"]["symbol"] == "d2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_upward_throw.py tests/test_distance_displacement.py -k diagram -v`
Expected: FAIL with `KeyError: 'diagram'`

- [ ] **Step 3: Write minimal implementation**

In `templates/upward_throw.py`, add `from .diagrams import motion_1d` and:

```python
def diagram_spec(ctx):
    """Rise then fall. h is the height reached at the top of the first segment;
    g labels the (downward) acceleration throughout."""
    return motion_1d(ctx, orientation="vertical", segments=[
        {"velocity_in": u, "acceleration": g, "span": h, "duration": t},
        {"direction": "reverse", "velocity_out": v},
    ])
```

then pass `diagram_spec=diagram_spec,` in `UPWARD_THROW = Template(...)`.

In `templates/distance_displacement.py`, add `from .diagrams import motion_1d` and:

```python
def diagram_spec(ctx):
    """Out along d1, back along d2. The net arrow (disp) and the path total
    (dist) are whichever of the two this split asks for."""
    return motion_1d(ctx, segments=[
        {"span": d1},
        {"direction": "reverse", "span": d2},
    ])
```

then pass `diagram_spec=diagram_spec,` in `DISTANCE_DISPLACEMENT = Template(...)`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_upward_throw.py tests/test_distance_displacement.py -v
python -m engine --topic upward-throw --verify
python -m engine --topic distance-displacement --verify
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/upward_throw.py templates/distance_displacement.py tests/test_upward_throw.py tests/test_distance_displacement.py
git commit -m "feat(engine): upward-throw and distance-displacement reversal diagrams"
```

---

## Task 10: (merged into Task 5 — do not dispatch)

The `motion-graphs` → `plot-2d` conversion originally lived here. It moved into
Task 5 so that removing `graph_spec` and installing its replacement happen in one
commit range, leaving the suite green after every task.

The task number is retained rather than renumbering Tasks 11–17, so brief
extraction (`scripts/task-brief PLAN_FILE N`) keeps matching the numbers used in
the ledger. **Skip this task.**

## Task 11: Cross-topic invariant sweep + engine docs

The test that actually guarantees the product promise: sweep every topic and every split, and assert the answer is never on the wire.

**Files:**
- Create: `tests/test_diagram_invariants.py`
- Modify: `README.md:9,30,47`, `../DEVELOPMENT_PLAN.md:21,205`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diagram_invariants.py
"""The product promise, asserted across the whole registry: an engine-authored
figure never carries the answer. Adding a topic with a diagram_spec that leaks
its find value fails here, not in review."""

import pytest

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate

TOPICS = [t for t in registry.topics()
          if registry.load_template(t).diagram_spec is not None]

# plot-2d is the deliberate exception: its polyline is the problem statement for
# graph-reading splits (spec 2026-07-27), so points are shown by design.
POINT_BEARING_KINDS = {"plot-2d"}


def _labels(spec):
    """Every label dict in a diagram, whatever its kind."""
    for segment in spec.get("segments", []):
        for key, val in segment.items():
            if isinstance(val, dict):
                yield val
    for body in spec.get("bodies", []):
        yield body["velocity"]


@pytest.mark.parametrize("topic", TOPICS)
def test_no_diagram_label_ever_carries_the_find_value(topic):
    template = registry.load_template(topic)
    for given, find in template.valid_splits():
        for seed in range(5):
            try:
                data = generate(topic, given=tuple(s.name for s in given),
                                find=find.name, difficulty="easy", seed=seed)
            except UnsolvableError:
                continue
            spec = data["diagram"]
            if spec["kind"] in POINT_BEARING_KINDS:
                continue
            for label in _labels(spec):
                if label["symbol"] == data["find"]["symbol"]:
                    assert label["role"] == "find"
                    assert "value" not in label, (topic, given, find, seed)
                    assert "exact" not in label, (topic, given, find, seed)


@pytest.mark.parametrize("topic", TOPICS)
def test_every_shown_label_carries_both_numeric_forms(topic):
    """ADR-005: display and authoritative values always travel together."""
    template = registry.load_template(topic)
    given, find = template.default_split
    data = generate(topic, given=tuple(s.name for s in given), find=find.name,
                    difficulty="easy", seed=1)
    spec = data["diagram"]
    if spec["kind"] in POINT_BEARING_KINDS:
        pytest.skip("plot-2d carries points, not labels")
    for label in _labels(spec):
        if label["role"] == "find":
            continue
        assert "value" in label and "exact" in label and "unit" in label
```

- [ ] **Step 2: Run test to verify it passes (or catches a real leak)**

Run: `pytest tests/test_diagram_invariants.py -v`
Expected: PASS. **If any topic fails, that is a genuine answer leak introduced in Tasks 6–10** — fix the topic's `diagram_spec`, never the assertion.

- [ ] **Step 3: Correct the stale docs**

The invariant sentence in `README.md:9` and `DEVELOPMENT_PLAN.md:21` still says the LLM emits TikZ. Update all of:

- `README.md:9` — "…owns only the natural-Thai phrasing —" (drop "and the TikZ diagram code")
- `README.md:30` — "2. Qwen 3.5 + Zod → phrases the problem in Thai (never computes, never draws)"
- `README.md:47` — "Thai phrasing only; no computation, no diagrams"
- `README.md:55` — note that TikZ figures are engine-authored from `sympy_data["diagram"]`
- `DEVELOPMENT_PLAN.md:21` — "…it only phrases Thai text."
- `DEVELOPMENT_PLAN.md:205` — the "LLM-generated TikZ" risk row becomes **Resolved**: diagrams are engine-authored, so the risk is retired rather than mitigated.

Then retarget the fine-tune spec, which still names TikZ as a model output:

- `2026-07-17-template-authoring-finetune-design.md:25` — the Phase 3.1 task is
  `sympy_data → Thai prose`, no longer `sympy_data → Thai prose + TikZ`.
- `:233` — the out-of-scope note "TikZ authoring by the template model (that is
  the Phase 3.1 model's job…)" becomes: TikZ is authored by **no** model; it is
  engine-owned per spec 2026-07-27.

```bash
# Locate the canonical copy first — it exists both at the project root and on an
# unmerged branch, and only the canonical one should be edited:
ls ../../Documents/2026-07-17-template-authoring-finetune-design.md
git log --all --oneline -- '*template-authoring-finetune-design.md'
```

If the only copy lives on an unmerged branch, leave a note in this plan's Done
criteria rather than editing a branch this work does not own.

Add a "What was just added" entry to the README coverage table **including the how-to-test commands**:

```bash
pytest tests/test_diagrams.py tests/test_diagram_contract.py tests/test_diagram_invariants.py
python -m engine --topic suvat --verify
```

- [ ] **Step 4: Run the full suite**

Run: `pytest && python -m templates.declarative`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_diagram_invariants.py README.md ../DEVELOPMENT_PLAN.md
git commit -m "test(engine): cross-topic answer-hiding sweep; correct LLM-owns-TikZ docs"
```

---

# Web tasks — repository `physics-jotelab`

> **Stop.** Tasks 12–17 are in a **different git repository**:
> `/home/thanakorn/Projects/Jotelab-Project/physics-jotelab/physics-jotelab`.
> That checkout sits on `master` and is the human's working copy — **do not
> implement there.** The controller creates an isolated worktree for the web
> work and dispatches these tasks inside it; if you find yourself on `master`,
> stop and report BLOCKED.
>
> Node commands run normally there (`npm test`, `npm run lint`, `npx tsc
> --noEmit`) — the `.venv` constraint above applies only to the engine repo.

---

## Task 12: Parse the diagram spec at the Zod trust boundary

**Files:**
- Modify: `lib/engine/sympy-data.ts:43-53`
- Test: `lib/engine/sympy-data.test.ts`

**Interfaces:**
- Produces: `diagramSchema`, `type Diagram`, and `sympyDataSchema.diagram?: Diagram`.

- [ ] **Step 1: Write the failing test**

```typescript
// lib/engine/sympy-data.test.ts
import { describe, expect, it } from "vitest"

import { sympyDataSchema } from "./sympy-data"

const BASE = {
  topic: "suvat", seed: 1,
  given: [{ symbol: "u", value: 5, exact: "5", unit: "m/s" }],
  find: { symbol: "v", value: 11, exact: "11", unit: "m/s" },
  steps: [{ expr_latex: "a", substituted_latex: "b", result_latex: "c" }],
  final_answer: { value: 11, exact: "11", unit: "m/s", latex: "11" },
  policy_applied: "easy", plausible: true,
}

describe("diagram", () => {
  it("is optional — payloads from before the diagram contract still parse", () => {
    expect(sympyDataSchema.parse(BASE).diagram).toBeUndefined()
  })

  it("parses a motion-1d spec whose find label carries no value", () => {
    const parsed = sympyDataSchema.parse({
      ...BASE,
      diagram: {
        kind: "motion-1d", orientation: "horizontal",
        segments: [{
          direction: "forward",
          velocity_in: { symbol: "u", label: "v_0", role: "given",
                         value: 5, exact: "5", unit: "m/s" },
          velocity_out: { symbol: "v", label: "v", role: "find" },
        }],
      },
    })
    expect(parsed.diagram?.kind).toBe("motion-1d")
  })

  it("rejects an unknown diagram kind rather than rendering nothing silently", () => {
    expect(() =>
      sympyDataSchema.parse({ ...BASE, diagram: { kind: "pie-chart" } })
    ).toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- lib/engine/sympy-data.test.ts`
Expected: FAIL — the unknown-kind case parses instead of throwing

- [ ] **Step 3: Write minimal implementation**

Add to `lib/engine/sympy-data.ts` above `sympyDataSchema`:

```typescript
/**
 * Engine-authored diagram spec (spec 2026-07-27). The engine owns every glyph
 * in a figure; this app only serializes the spec to TikZ.
 *
 * A label bound to the Find target carries `role: "find"` and — deliberately —
 * **no** `value`/`exact`. The answer is never on the wire, so no rendering bug
 * can leak it. `.optional()` because rows persisted before this contract have
 * no `diagram`; those questions simply render without a picture.
 */
export const diagramLabelSchema = z.object({
  symbol: z.string().min(1),
  label: z.string().min(1),
  role: z.enum(["given", "find", "derived"]),
  value: z.number().optional(),
  exact: z.string().optional(),
  unit: z.string().optional(),
})

const axisSchema = z.object({ symbol: z.string().min(1), unit: z.string() })
const pointSchema = z.object({
  x: z.object({ value: z.number(), exact: z.string() }),
  y: z.object({ value: z.number(), exact: z.string() }),
})

export const diagramSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("motion-1d"),
    orientation: z.enum(["horizontal", "vertical"]),
    // Explicit optional roles rather than `.catchall(diagramLabelSchema)`: a
    // catchall index signature does not admit `direction`'s string enum, and
    // `tsc --noEmit` rejects the resulting intersection.
    segments: z.array(
      z.object({
        direction: z.enum(["forward", "reverse"]),
        velocity_in: diagramLabelSchema.optional(),
        acceleration: diagramLabelSchema.optional(),
        velocity_out: diagramLabelSchema.optional(),
        span: diagramLabelSchema.optional(),
        duration: diagramLabelSchema.optional(),
      })
    ),
  }),
  z.object({
    kind: z.literal("plot-2d"),
    axes: z.object({ x: axisSchema, y: axisSchema }),
    points: z.array(pointSchema).min(2),
  }),
  z.object({
    kind: z.literal("actors"),
    bodies: z.array(
      z.object({ name: z.string().min(1), velocity: diagramLabelSchema })
    ),
  }),
])

export type Diagram = z.infer<typeof diagramSchema>
export type DiagramLabel = z.infer<typeof diagramLabelSchema>
```

and add `diagram: diagramSchema.optional(),` to `sympyDataSchema`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- lib/engine/sympy-data.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/engine/sympy-data.ts lib/engine/sympy-data.test.ts
git commit -m "feat: parse the engine diagram spec at the trust boundary"
```

---

## Task 13: `spec-to-tikz` — the `motion-1d` renderer

**Files:**
- Create: `lib/tikz/diagram/spec-to-tikz.ts`
- Test: `lib/tikz/diagram/spec-to-tikz.test.ts`

**Interfaces:**
- Consumes: `Diagram`, `DiagramLabel` (Task 12).
- Produces: `specToTikz(diagram: Diagram): string`, `renderLabel(label: DiagramLabel): string`.

- [ ] **Step 1: Write the failing test**

```typescript
// lib/tikz/diagram/spec-to-tikz.test.ts
import { describe, expect, it } from "vitest"

import { renderLabel, specToTikz } from "./spec-to-tikz"

describe("renderLabel", () => {
  it("shows value and unit for a given", () => {
    expect(renderLabel({ symbol: "u", label: "v_0", role: "given",
                         value: 5, exact: "5", unit: "m/s" }))
      .toBe("$v_0 = 5\\ \\mathrm{m/s}$")
  })

  it("shows a question mark for the find, never a number", () => {
    expect(renderLabel({ symbol: "v", label: "v", role: "find" }))
      .toBe("$v = ?$")
  })

  it("superscripts a squared unit", () => {
    expect(renderLabel({ symbol: "a", label: "a", role: "given",
                         value: 2, exact: "2", unit: "m/s^2" }))
      .toBe("$a = 2\\ \\mathrm{m/s^{2}}$")
  })
})

describe("specToTikz motion-1d", () => {
  const spec = {
    kind: "motion-1d" as const,
    orientation: "horizontal" as const,
    segments: [{
      direction: "forward" as const,
      velocity_in: { symbol: "u", label: "v_0", role: "given" as const,
                     value: 5, exact: "5", unit: "m/s" },
      velocity_out: { symbol: "v", label: "v", role: "find" as const },
    }],
  }

  it("wraps output in a tikzpicture", () => {
    const tikz = specToTikz(spec)
    expect(tikz.startsWith("\\begin{tikzpicture}")).toBe(true)
    expect(tikz.trimEnd().endsWith("\\end{tikzpicture}")).toBe(true)
  })

  it("draws the given value and hides the answer", () => {
    const tikz = specToTikz(spec)
    expect(tikz).toContain("$v_0 = 5\\ \\mathrm{m/s}$")
    expect(tikz).toContain("$v = ?$")
    expect(tikz).not.toContain("11")
  })

  it("is deterministic — same spec, same string", () => {
    expect(specToTikz(spec)).toBe(specToTikz(spec))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- lib/tikz/diagram/spec-to-tikz.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```typescript
// lib/tikz/diagram/spec-to-tikz.ts
import type { Diagram, DiagramLabel } from "@/lib/engine/sympy-data"

/**
 * Pure `diagram spec -> tikzpicture` serializer (spec 2026-07-27).
 *
 * This module contains **no physics**. It derives no value, decides nothing
 * about what a figure should contain, and never inspects `sympy_data` — the
 * engine already made every one of those decisions. Its only judgement call is
 * layout, and its only rule is: obey `role`.
 */

/** `m/s^2` -> `\mathrm{m/s^{2}}` — TeX-safe, Latin-only, no Thai. */
function renderUnit(unit: string): string {
  return `\\mathrm{${unit.replace(/\^(\w+)/g, "^{$1}")}}`
}

/**
 * One label. A `find` label renders as `?`: the engine sent no value for it, so
 * there is nothing here that could leak the answer even by accident.
 */
export function renderLabel(label: DiagramLabel): string {
  if (label.role === "find" || label.value === undefined) {
    return `$${label.label} = ?$`
  }
  const unit = label.unit ? `\\ ${renderUnit(label.unit)}` : ""
  return `$${label.label} = ${label.value}${unit}$`
}

const SEGMENT_WIDTH = 6
const AXIS_Y = 0

type MotionDiagram = Extract<Diagram, { kind: "motion-1d" }>
type MotionSegment = MotionDiagram["segments"][number]

function motionSegment(
  segment: MotionSegment,
  index: number,
  vertical: boolean
): string[] {
  const reverse = segment.direction === "reverse"
  const x0 = index * SEGMENT_WIDTH
  const x1 = x0 + SEGMENT_WIDTH
  const [from, to] = reverse ? [x1, x0] : [x0, x1]
  const lines: string[] = []
  const at = (x: number, y: number) => (vertical ? `(${y},${x})` : `(${x},${y})`)

  lines.push(`\\draw[thick] ${at(x0, AXIS_Y)} -- ${at(x1, AXIS_Y)};`)

  const vIn = segment.velocity_in
  if (vIn) {
    lines.push(
      `\\draw[->,very thick] ${at(from, 0.5)} -- ${at(from + (reverse ? -1.4 : 1.4), 0.5)} node[midway,above]{${renderLabel(vIn)}};`
    )
  }
  const accel = segment.acceleration
  if (accel) {
    lines.push(
      `\\draw[->,thick] ${at(x0 + 2, 1.3)} -- ${at(x0 + 3.4, 1.3)} node[midway,above]{${renderLabel(accel)}};`
    )
  }
  const vOut = segment.velocity_out
  if (vOut) {
    lines.push(
      `\\draw[->,very thick] ${at(to, 0.5)} -- ${at(to + (reverse ? -1.4 : 1.4), 0.5)} node[midway,above]{${renderLabel(vOut)}};`
    )
  }
  const duration = segment.duration
  if (duration) {
    lines.push(
      `\\draw[<->] ${at(x0, 2.1)} -- ${at(x1, 2.1)} node[midway,above]{${renderLabel(duration)}};`
    )
  }
  const span = segment.span
  if (span) {
    lines.push(
      `\\draw[<->] ${at(x0, -0.6)} -- ${at(x1, -0.6)} node[midway,below]{${renderLabel(span)}};`
    )
  }
  return lines
}

export function specToTikz(diagram: Diagram): string {
  const lines = ["\\begin{tikzpicture}[>=latex,line join=round]"]

  if (diagram.kind === "motion-1d") {
    const vertical = diagram.orientation === "vertical"
    diagram.segments.forEach((segment, index) => {
      lines.push(...motionSegment(segment, index, vertical))
    })
  }

  lines.push("\\end{tikzpicture}")
  return lines.join("\n")
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- lib/tikz/diagram/spec-to-tikz.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/tikz/diagram/spec-to-tikz.ts lib/tikz/diagram/spec-to-tikz.test.ts
git commit -m "feat: pure motion-1d diagram spec -> TikZ serializer"
```

---

## Task 14: `plot-2d` and `actors` renderers

**Files:**
- Modify: `lib/tikz/diagram/spec-to-tikz.ts`
- Test: `lib/tikz/diagram/spec-to-tikz.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// append to lib/tikz/diagram/spec-to-tikz.test.ts
describe("specToTikz plot-2d", () => {
  const spec = {
    kind: "plot-2d" as const,
    axes: { x: { symbol: "t", unit: "s" }, y: { symbol: "v", unit: "m/s" } },
    points: [
      { x: { value: 0, exact: "0" }, y: { value: 4, exact: "4" } },
      { x: { value: 3, exact: "3" }, y: { value: 10, exact: "10" } },
      { x: { value: 8, exact: "8" }, y: { value: 10, exact: "10" } },
    ],
  }

  it("draws axes and the polyline through every point", () => {
    const tikz = specToTikz(spec)
    expect(tikz).toContain("\\draw[->] (0,0) --")
    expect(tikz).toContain("(0,4) -- (3,10) -- (8,10)")
  })

  it("labels the axes with symbol and unit", () => {
    const tikz = specToTikz(spec)
    expect(tikz).toContain("$t\\ \\mathrm{s}$")
    expect(tikz).toContain("$v\\ \\mathrm{m/s}$")
  })
})

describe("specToTikz actors", () => {
  it("draws one labelled body per actor", () => {
    const tikz = specToTikz({
      kind: "actors" as const,
      bodies: [
        { name: "A", velocity: { symbol: "va", label: "v_A", role: "given" as const,
                                 value: 12, exact: "12", unit: "m/s" } },
        { name: "B", velocity: { symbol: "vb", label: "v_B", role: "find" as const } },
      ],
    })
    expect(tikz).toContain("$v_A = 12\\ \\mathrm{m/s}$")
    expect(tikz).toContain("$v_B = ?$")
    expect(tikz).toContain("{A}")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- lib/tikz/diagram/spec-to-tikz.test.ts`
Expected: FAIL — plot-2d and actors produce an empty picture

- [ ] **Step 3: Write minimal implementation**

Add to `lib/tikz/diagram/spec-to-tikz.ts`, and extend `specToTikz`'s branching:

```typescript
const PLOT_SCALE = 0.6

function plotLines(diagram: Extract<Diagram, { kind: "plot-2d" }>): string[] {
  const xs = diagram.points.map((p) => p.x.value)
  const ys = diagram.points.map((p) => p.y.value)
  const xMax = Math.max(...xs) * 1.15
  const yMax = Math.max(...ys) * 1.15

  const path = diagram.points
    .map((p) => `(${p.x.value},${p.y.value})`)
    .join(" -- ")

  return [
    `\\draw[->] (0,0) -- (${xMax.toFixed(2)},0) node[right]{$${diagram.axes.x.symbol}\\ ${renderUnit(diagram.axes.x.unit)}$};`,
    `\\draw[->] (0,0) -- (0,${yMax.toFixed(2)}) node[above]{$${diagram.axes.y.symbol}\\ ${renderUnit(diagram.axes.y.unit)}$};`,
    `\\draw[very thick] ${path};`,
  ]
}

function actorLines(diagram: Extract<Diagram, { kind: "actors" }>): string[] {
  const lines: string[] = []
  diagram.bodies.forEach((body, index) => {
    const y = -index * 2
    lines.push(`\\draw[fill=black!8] (0,${y}) rectangle (1,${y + 0.9}) node[midway]{${body.name}};`)
    lines.push(
      `\\draw[->,very thick] (1.2,${y + 0.45}) -- (3.2,${y + 0.45}) node[midway,above]{${renderLabel(body.velocity)}};`
    )
  })
  return lines
}
```

Then in `specToTikz`, after the `motion-1d` branch:

```typescript
  } else if (diagram.kind === "plot-2d") {
    lines.push(`\\begin{scope}[scale=${PLOT_SCALE}]`)
    lines.push(...plotLines(diagram))
    lines.push("\\end{scope}")
  } else {
    lines.push(...actorLines(diagram))
  }
```

(Change the existing `if (diagram.kind === "motion-1d") { ... }` into the head of this chain.)

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- lib/tikz/diagram/spec-to-tikz.test.ts`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/tikz/diagram/spec-to-tikz.ts lib/tikz/diagram/spec-to-tikz.test.ts
git commit -m "feat: plot-2d and actors diagram renderers"
```

---

## Task 15: Wire `attach-diagram`, delete the TypeScript templates

The moment the LLM-era authoring path leaves the codebase.

**Files:**
- Modify: `lib/tikz/attach-diagram.ts:7,71,80,84,90`
- Delete: `lib/tikz/templates/suvat.ts`, `lib/tikz/templates/suvat.test.ts`, `lib/tikz/templates/index.ts`
- Test: `lib/tikz/attach-diagram.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// append to lib/tikz/attach-diagram.test.ts
it("attaches a diagram built from the engine spec", async () => {
  const compile = vi.fn().mockResolvedValue("<svg/>")
  const question = {
    ...BASE_QUESTION,
    sympy_data: {
      ...BASE_SYMPY_DATA,
      diagram: {
        kind: "motion-1d", orientation: "horizontal",
        segments: [{
          direction: "forward",
          velocity_in: { symbol: "u", label: "v_0", role: "given",
                         value: 5, exact: "5", unit: "m/s" },
        }],
      },
    },
  }

  const result = await attachQuestionDiagram(question, { compile })

  expect(result.diagram_svg).toBe("<svg/>")
  expect(result.tikz_code).toContain("$v_0 = 5\\ \\mathrm{m/s}$")
})

it("attaches nothing when the engine sent no diagram — there is no fallback", async () => {
  const compile = vi.fn().mockResolvedValue("<svg/>")
  const question = { ...BASE_QUESTION, sympy_data: BASE_SYMPY_DATA }

  const result = await attachQuestionDiagram(question, { compile })

  expect(result.tikz_code).toBeUndefined()
  expect(result.diagram_svg).toBeUndefined()
  expect(compile).not.toHaveBeenCalled()
})
```

Delete any existing test in this file that asserts a SUVAT template fallback.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- lib/tikz/attach-diagram.test.ts`
Expected: FAIL — the no-diagram case still builds a template diagram

- [ ] **Step 3: Write minimal implementation**

In `lib/tikz/attach-diagram.ts`:

```typescript
import { specToTikz } from "./diagram/spec-to-tikz"
```
(replacing `import { buildTemplateTikz } from "./templates"`)

and in `attachQuestionDiagram`:

```typescript
  // The engine authors every diagram. No spec means no picture — there is no
  // web-side fallback, because a second author is exactly what this contract
  // exists to remove (spec 2026-07-27).
  const diagram = question.sympy_data.diagram
  if (!diagram) {
    return question
  }
  const tikz = specToTikz(diagram)
```

Update the module docstring's "re-derive the TikZ from `sympy_data`" paragraph to say the spec is engine-authored and merely serialized here. Change both `logTikzAttempt` calls' `source: "template"` to `source: "engine"`.

Then delete the templates directory:

```bash
git rm lib/tikz/templates/suvat.ts lib/tikz/templates/suvat.test.ts lib/tikz/templates/index.ts
```

- [ ] **Step 4: Run the full suite**

```bash
npm test
npm run lint
npx tsc --noEmit
```
Expected: PASS. `tsc` catches any lingering import of the deleted templates.

- [ ] **Step 5: Commit**

```bash
git add lib/tikz/attach-diagram.ts lib/tikz/attach-diagram.test.ts
git commit -m "feat: serialize engine diagram specs; delete the TS templates"
```

---

## Task 16: Real-compile integration check

String assertions cannot catch TeX that does not compile. One real compile per kind.

**Files:**
- Create: `lib/tikz/diagram/spec-to-tikz.integration.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// lib/tikz/diagram/spec-to-tikz.integration.test.ts
/**
 * Real node-tikzjax compiles — slow (seconds each), but the only thing that
 * proves a renderer emits TeX the engine actually accepts. String assertions
 * in spec-to-tikz.test.ts happily pass on TeX that fails to compile.
 */
import { describe, expect, it } from "vitest"

import { compileTikz } from "../compile"
import { specToTikz } from "./spec-to-tikz"

const CASES = {
  "motion-1d": {
    kind: "motion-1d" as const, orientation: "horizontal" as const,
    segments: [{
      direction: "forward" as const,
      velocity_in: { symbol: "u", label: "v_0", role: "given" as const,
                     value: 5, exact: "5", unit: "m/s" },
      acceleration: { symbol: "a", label: "a", role: "given" as const,
                      value: 2, exact: "2", unit: "m/s^2" },
      velocity_out: { symbol: "v", label: "v", role: "find" as const },
    }],
  },
  "motion-1d-reverse": {
    kind: "motion-1d" as const, orientation: "vertical" as const,
    segments: [
      { direction: "forward" as const,
        velocity_in: { symbol: "u", label: "v_0", role: "given" as const,
                       value: 20, exact: "20", unit: "m/s" } },
      { direction: "reverse" as const,
        velocity_out: { symbol: "v", label: "v", role: "find" as const } },
    ],
  },
  "plot-2d": {
    kind: "plot-2d" as const,
    axes: { x: { symbol: "t", unit: "s" }, y: { symbol: "v", unit: "m/s" } },
    points: [
      { x: { value: 0, exact: "0" }, y: { value: 4, exact: "4" } },
      { x: { value: 3, exact: "3" }, y: { value: 10, exact: "10" } },
    ],
  },
  actors: {
    kind: "actors" as const,
    bodies: [{ name: "A", velocity: { symbol: "va", label: "v_A",
                                      role: "given" as const, value: 12,
                                      exact: "12", unit: "m/s" } }],
  },
}

describe("engine diagram specs compile", () => {
  for (const [name, spec] of Object.entries(CASES)) {
    it(`compiles ${name} to SVG`, async () => {
      const svg = await compileTikz(specToTikz(spec))
      expect(svg).toContain("<svg")
    }, 60_000)
  }
})
```

- [ ] **Step 2: Run test**

Run: `npm test -- lib/tikz/diagram/spec-to-tikz.integration.test.ts`
Expected: PASS. **If a case fails, the renderer emits invalid TeX** — fix `spec-to-tikz.ts`. The likeliest culprit is an unescaped character in a unit or label.

- [ ] **Step 3: Commit**

```bash
git add lib/tikz/diagram/spec-to-tikz.integration.test.ts
git commit -m "test: real node-tikzjax compile per diagram kind"
```

---

## Task 17: Web documentation

**Files:**
- Create: `docs/adr/008-engine-owned-diagrams.md`
- Modify: `docs/adr/007-diagram-generation.md` (status line only)

- [ ] **Step 1: Write ADR-008**

Cover, in the house ADR style (Context / Decision / Consequences):

- **Context:** ADR-007 put template logic web-side because the SUVAT diagram was a pure function of `sympy_data` and needed no migration. That reasoning holds for one topic; across nine it splits authorship of the figure from authorship of the numbers, and leaves the Phase 3.1 fine-tune target still pointed at LLM-authored TikZ.
- **Decision:** the engine emits a structured diagram spec at `sympy_data["diagram"]`; the web app serializes and compiles it. No fallback.
- **Why a spec, not TikZ source:** renderer freedom, testability without TeX in Python, and no `tikz_code` persistence.
- **Answer-hiding by omission**, and the deliberate `plot-2d` exception for graph-reading splits.
- **Consequences:** questions persisted before this contract have no `diagram` key and **render without diagrams until regenerated** — accepted, because a legacy TypeScript path would preserve the split authorship this work removes.
- **How to test:**

```bash
npm test -- lib/tikz/diagram
npm test -- lib/engine/sympy-data.test.ts
npm test
```

- [ ] **Step 2: Mark ADR-007 superseded**

Change its status line to:

```markdown
- **Status:** Superseded by ADR-008 (2026-07-27) — diagram authoring moved
  engine-side. The compile pipeline (ADR-006) it builds on is unchanged.
```

- [ ] **Step 3: Verify the docs match reality**

Run: `npm test && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add docs/adr/008-engine-owned-diagrams.md docs/adr/007-diagram-generation.md
git commit -m "docs: ADR-008 engine-owned diagrams; supersede ADR-007"
```

---

## Done criteria

- [ ] `pytest && python -m templates.declarative` green in `jotelab-ai`.
- [ ] `npm test && npm run lint && npx tsc --noEmit` green in `physics-jotelab`.
- [ ] All nine topics emit a `diagram`; `tests/test_diagram_invariants.py` passes for every split.
- [ ] `lib/tikz/templates/` no longer exists.
- [ ] No file in either repo claims the LLM emits TikZ.
