# Mixed (Chained) Single Problems Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One generated problem instance can span multiple topics: an ordered chain of single-topic parts where each part's answer is pinned as a declared given of the next part.

**Architecture:** A thin chain layer (`engine/chain.py`) over the unchanged `engine.loop.generate`: validate the chain spec up front (typed errors), generate parts in order passing each answer forward through `conditions`, re-roll the whole chain (bounded, seed-derived) when a downstream part can't find a clean instance. The harness gains `verify_chain` (per-part `verify_generic` + exact link assertions); the CLI gains a repeatable `--part` flag. Spec: `docs/superpowers/specs/2026-07-24-mixed-chained-problems-design.md`.

**Tech Stack:** Python 3.11+, SymPy 1.13.*, pytest. Run everything from the repo root with the project venv: `.venv/bin/python -m pytest`, `.venv/bin/python -m engine`.

## Global Constraints

- All numeric flow uses **exact** SymPy values / contract `exact` strings (ADR-005); the lossy display `value` is never the source of truth.
- Every dead end raises a **typed** `EngineError` subclass — nothing fails silently.
- Generation must stay **bounded** and **deterministic from a single integer seed**.
- Each element of the chain contract's `parts` is an **unmodified** per-topic `sympy_data` dict.
- Match existing docstring style: module docstring citing the spec, `--`-ruled section comments.

---

### Task 1: Exact (non-integer) pinned conditions in sampling

**Files:**
- Modify: `engine/sampling.py:39` (the pinned-value branch of `sample`)
- Test: `tests/test_chain.py` (new file; chain tests accrete here in later tasks)

**Interfaces:**
- Consumes: `engine.sampling.sample(template, given, conditions, difficulty, seed)` (existing).
- Produces: `sample` accepts a pinned condition that is any `sympy.nsimplify`-able exact value (e.g. the string `"7/2"`, a `sympy.Rational`), not just an `int`. Integers still come back as `sympy.Integer`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chain.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify the first fails**

Run: `.venv/bin/python -m pytest tests/test_chain.py -v`
Expected: `test_pinned_condition_accepts_exact_noninteger` FAILS (`TypeError`/`ValueError` from `sympy.Integer("7/2")`); `test_pinned_integer_condition_stays_integer` PASSES.

- [ ] **Step 3: Generalize the pinned-value coercion**

In `engine/sampling.py`, change the `else` branch of `sample`:

```python
        else:
            # An exact pinned value — nsimplify keeps integers Integer and
            # accepts exact non-integers (e.g. "7/2" from a chain link, ADR-005).
            inputs[sym] = sympy.nsimplify(spec)
```

Also update the module docstring's `conditions` sentence to:

```
``conditions`` lets the caller pin a variable (Advanced mode / chain links):
either an exact value (any ``nsimplify``-able number, e.g. ``5`` or ``"7/2"``),
or a ``(lo, hi)`` / ``(lo, hi, signed)`` range override. Conditions may be
keyed by the SymPy symbol or by its name.
```

- [ ] **Step 4: Run tests to verify both pass**

Run: `.venv/bin/python -m pytest tests/test_chain.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Guard against regressions elsewhere**

Run: `.venv/bin/python -m pytest tests/test_loop.py tests/test_cli.py -q`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add engine/sampling.py tests/test_chain.py
git commit -m "feat(engine): accept exact non-integer pinned conditions (chain links)"
```

---

### Task 2: Typed chain errors

**Files:**
- Modify: `engine/errors.py` (append after `NoCleanInstanceError`)
- Test: `tests/test_chain.py` (append)

**Interfaces:**
- Consumes: `engine.errors.EngineError` (existing base).
- Produces: `ChainSpecError(reason)` and `IncompatibleLinkError(topic, symbol, receive_unit, feed_unit)` — both `EngineError` subclasses, importable as `from engine.errors import ChainSpecError, IncompatibleLinkError`. `IncompatibleLinkError` exposes `.topic`, `.symbol`, `.receive_unit`, `.feed_unit`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_chain.py`)

```python
from engine.errors import ChainSpecError, EngineError, IncompatibleLinkError


def test_chain_errors_are_typed_engine_errors():
    assert issubclass(ChainSpecError, EngineError)
    assert issubclass(IncompatibleLinkError, EngineError)
    err = IncompatibleLinkError("suvat", "t", "s", "m/s")
    assert err.topic == "suvat" and err.symbol == "t"
    assert "expects s" in str(err) and "m/s" in str(err)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_chain.py::test_chain_errors_are_typed_engine_errors -v`
Expected: FAIL with `ImportError: cannot import name 'ChainSpecError'`.

- [ ] **Step 3: Implement** (append to `engine/errors.py`)

```python
class ChainSpecError(EngineError):
    """A chained (mixed) problem spec is malformed (chain design doc).

    Raised at validation, before any part is generated: fewer than two parts,
    a missing/unknown ``receive`` variable, or a ``receive`` not among that
    part's givens.
    """

    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"[mixed] invalid chain spec: {reason}")


class IncompatibleLinkError(EngineError):
    """A chain link's units don't match (chain design doc).

    The receiving given of one part must carry the same unit as the previous
    part's find; raised at validation, before any part is generated.
    """

    def __init__(self, topic, symbol, receive_unit, feed_unit):
        self.topic = topic
        self.symbol = symbol
        self.receive_unit = receive_unit
        self.feed_unit = feed_unit
        super().__init__(
            f"[{topic}] link into {symbol!r} expects {receive_unit}, but the "
            f"previous part's answer is {feed_unit}"
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_chain.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add engine/errors.py tests/test_chain.py
git commit -m "feat(engine): typed ChainSpecError / IncompatibleLinkError"
```

---

### Task 3: `engine/chain.py` — validation, bounded generation, chain contract

**Files:**
- Create: `engine/chain.py`
- Test: `tests/test_chain.py` (append)

**Interfaces:**
- Consumes: `generate` (`engine.loop`), `load_template` (`engine.registry`), Task 2 errors, `Template.symbol/unit_for/default_split`.
- Produces: `generate_chain(parts, difficulty="easy", seed=0, max_chain_attempts=20, max_attempts=None) -> dict` returning the chain contract `{"topic": "mixed", "topics": [...], "seed", "policy_applied", "parts": [sympy_data...], "links": [{"from_part", "to_part", "symbol", "exact"}...], "final_answer"}`. Part dicts: `{"topic", "given"?, "find"?, "receive"?, "conditions"?}`. `receive` is **required** on parts after the first (the CLI auto-resolves before calling, Task 5).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_chain.py`)

```python
import json

import pytest

from engine.chain import generate_chain
from engine.errors import NoCleanInstanceError

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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chain.py -v`
Expected: the new tests FAIL with `ModuleNotFoundError: No module named 'engine.chain'`; the Task 1–2 tests still PASS.

- [ ] **Step 3: Implement `engine/chain.py`**

```python
"""Chained mixed problems — one instance spanning multiple topics.

Design: ``docs/superpowers/specs/2026-07-24-mixed-chained-problems-design.md``.

A **chain** is an ordered list of 2+ parts, each a normal single-topic
instance produced by the unchanged :func:`engine.loop.generate`; the answer of
part *i* is pinned (exactly, ADR-005) as one declared given — the ``receive``
variable — of part *i+1*. Every part therefore stays single-equation, so the
existing Data Fidelity harness applies per part; the chain layer adds spec
validation (typed errors), bounded whole-chain re-rolling, and the ``mixed``
contract that wraps the per-part ``sympy_data`` dicts unmodified.
"""

from __future__ import annotations

from engine.errors import (ChainSpecError, IncompatibleLinkError,
                           NoCleanInstanceError)
from engine.loop import generate
from engine.registry import load_template

# Bounded outer loop: whole-chain re-rolls when a pinned link value leaves a
# downstream part with no clean instance (starting value, tune empirically).
MAX_CHAIN_ATTEMPTS = 20


def generate_chain(parts, difficulty="easy", seed=0,
                   max_chain_attempts=MAX_CHAIN_ATTEMPTS, max_attempts=None):
    """Generate one mixed (chained) problem instance.

    ``parts`` is a list of dicts: ``{"topic": str, "given": [names]?,
    "find": name?, "receive": name?, "conditions": dict?}``. The template's
    ``default_split`` fills an omitted split; every part after the first must
    name ``receive`` — the given that takes the previous part's answer.

    Deterministic in ``seed``; bounded by ``max_chain_attempts`` whole-chain
    re-rolls (``max_attempts``, when set, is forwarded to each part's inner
    loop). Raises :class:`ChainSpecError` / :class:`IncompatibleLinkError` at
    validation, or re-raises the last :class:`NoCleanInstanceError` when the
    bounded re-rolls are exhausted.
    """
    resolved = _validate(parts)
    gen_kwargs = {} if max_attempts is None else {"max_attempts": max_attempts}
    last_err = None
    for attempt in range(max_chain_attempts):
        try:
            return _attempt(parts, resolved, difficulty, seed, attempt, gen_kwargs)
        except NoCleanInstanceError as err:
            last_err = err  # re-roll the whole chain with the next derived seed
    raise last_err


# -- one whole-chain attempt ---------------------------------------------------
def _attempt(parts, resolved, difficulty, seed, attempt, gen_kwargs):
    out_parts, links = [], []
    prev_exact = None
    for i, (part, (template, given, find, receive)) in enumerate(zip(parts, resolved)):
        conditions = dict(part.get("conditions") or {})
        if i > 0:
            conditions[receive.name] = prev_exact  # exact string (ADR-005)
        data = generate(
            part["topic"],
            given=[s.name for s in given],
            find=find.name,
            conditions=conditions or None,
            difficulty=difficulty,
            seed=_derive(seed, attempt, i),
            **gen_kwargs,
        )
        if i > 0:
            links.append({"from_part": i - 1, "to_part": i,
                          "symbol": receive.name, "exact": prev_exact})
        prev_exact = data["final_answer"]["exact"]
        out_parts.append(data)
    return {
        "topic": "mixed",
        "topics": [part["topic"] for part in parts],
        "seed": seed,
        "policy_applied": difficulty,
        "parts": out_parts,
        "links": links,
        "final_answer": out_parts[-1]["final_answer"],
    }


def _derive(seed, attempt, part_index):
    """Per-part seed, reproducible from the chain's single integer seed."""
    return seed + 1000 * attempt + part_index


# -- validation (loud, typed; before any generation) ---------------------------
def _validate(parts):
    """Resolve every part's split and link; raise typed errors on bad specs.

    Returns ``[(template, given, find, receive_symbol_or_None), ...]``.
    """
    if len(parts) < 2:
        raise ChainSpecError("a chain needs at least 2 parts")
    resolved = []
    prev_template = prev_find = None
    for i, part in enumerate(parts):
        template = load_template(part["topic"])
        given, find = part.get("given"), part.get("find")
        if given is None or find is None:
            given, find = template.default_split
        given = tuple(template.symbol(g) for g in given)
        find = template.symbol(find)
        receive = None
        if i > 0:
            name = part.get("receive")
            if name is None:
                raise ChainSpecError(
                    f"part {i + 1} ({part['topic']}) must declare its "
                    f"'receive' variable"
                )
            try:
                receive = template.symbol(name)
            except KeyError:
                raise ChainSpecError(
                    f"part {i + 1} ({part['topic']}) has no variable {name!r}"
                )
            if receive not in given:
                raise ChainSpecError(
                    f"receive {name!r} is not among part {i + 1}'s givens"
                )
            feed_unit = prev_template.unit_for(prev_find)
            receive_unit = template.unit_for(receive)
            if feed_unit != receive_unit:
                raise IncompatibleLinkError(
                    part["topic"], name, receive_unit, feed_unit
                )
        resolved.append((template, given, find, receive))
        prev_template, prev_find = template, find
    return resolved
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_chain.py -v`
Expected: all PASSED (the two-part tests generate for real — a few seconds each). If a chain test raises `NoCleanInstanceError`, the seed rolled badly 20 times in a row — investigate rather than bump the seed (the design intends default settings to absorb unlucky links).

- [ ] **Step 5: Commit**

```bash
git add engine/chain.py tests/test_chain.py
git commit -m "feat(engine): generate_chain — chained mixed problems (spec 2026-07-24)"
```

---

### Task 4: `verify_chain` in the harness

**Files:**
- Modify: `harness/verify.py` (append after `verify_generic`; extend module docstring's final paragraph)
- Test: `tests/test_chain.py` (append)

**Interfaces:**
- Consumes: `verify_generic`, `FidelityError`, `exact` (all existing in `harness/verify.py` scope), `load_template`, Task 3's chain contract.
- Produces: `verify_chain(chain_data, difficulty="easy") -> True` raising `FidelityError` on any per-part or link failure. Importable as `from harness.verify import verify_chain`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_chain.py`)

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chain.py -k verify_chain -v`
Expected: FAIL with `ImportError: cannot import name 'verify_chain'`.

- [ ] **Step 3: Implement** (append to `harness/verify.py`)

```python
def verify_chain(chain_data, difficulty="easy"):
    """Data-Fidelity check for a chained mixed instance (chain design doc).

    Every part must pass the full (a)–(e) :func:`verify_generic` battery with
    its own template, and every link must carry the previous part's answer
    exactly: the receiving given's ``exact`` equals the feeding part's
    ``final_answer.exact`` (compared symbolically), units agree, and the
    recorded link ``exact`` matches. Raises :class:`FidelityError` on any
    failure; returns ``True`` when the whole chain is faithful.
    """
    for part in chain_data["parts"]:
        verify_generic(part, load_template(part["topic"]), difficulty)
    for link in chain_data["links"]:
        feed = chain_data["parts"][link["from_part"]]["final_answer"]
        receiving = chain_data["parts"][link["to_part"]]
        recv = next(
            (g for g in receiving["given"] if g["symbol"] == link["symbol"]),
            None,
        )
        if recv is None:
            raise FidelityError(
                f"(link) part {link['to_part'] + 1} has no given "
                f"{link['symbol']!r}"
            )
        if sympy.simplify(exact(recv["exact"]) - exact(feed["exact"])) != 0:
            raise FidelityError(
                f"(link) received {recv['exact']!r} != fed answer "
                f"{feed['exact']!r}"
            )
        if recv["unit"] != feed["unit"]:
            raise FidelityError(
                f"(link) unit {recv['unit']} != fed unit {feed['unit']}"
            )
        if link["exact"] != feed["exact"]:
            raise FidelityError(
                f"(link) recorded link exact {link['exact']!r} != "
                f"final_answer.exact {feed['exact']!r}"
            )
    return True
```

Extend the module docstring's last paragraph (after the `verify` sentence) with:

```
:func:`verify_chain` extends the oracle to chained mixed instances: every part
runs through :func:`verify_generic`, then each link is asserted exact.
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_chain.py -v`
Expected: all PASSED (the sweep test is the slow one — full-system solves per part).

- [ ] **Step 5: Commit**

```bash
git add harness/verify.py tests/test_chain.py
git commit -m "feat(harness): verify_chain — per-part fidelity + exact link checks"
```

---

### Task 5: CLI `--part` flags

**Files:**
- Modify: `engine/__main__.py` (parser, `main`, new `_parse_part`/`_resolve_receives`/`_render_chain` helpers)
- Test: `tests/test_chain.py` (append)

**Interfaces:**
- Consumes: `generate_chain` (Task 3), `verify_chain` (Task 4), existing `_parse_csv`, `_render_human`, `load_template`.
- Produces: `python -m engine --part TOPIC[:GIVEN,CSV:FIND[:RECEIVE]] --part ... [--difficulty] [--seed] [--json] [--verify]`. `--part` is incompatible with `--topic/--given/--find/--condition`; omitted split → default split; omitted receive → auto-picked when exactly one given is unit-compatible, else a loud `SystemExit` listing candidates.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_chain.py`)

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chain.py -k cli_chain -v`
Expected: FAIL — `main` rejects the unknown `--part` flag (`SystemExit` with argparse usage error), so the match-based tests fail on the message and the rc-based tests error.

- [ ] **Step 3: Implement in `engine/__main__.py`**

3a. In `_build_parser`, change the `--topic` default and add `--part` (after the `--topic` argument):

```python
    p.add_argument("--topic", default=None,
                   help=f"topic template (known: {', '.join(topics())})")
    p.add_argument("--part", action="append", default=None,
                   metavar="TOPIC[:GIVEN,CSV:FIND[:RECEIVE]]",
                   help="chain part (repeat 2+ times for a mixed problem); "
                        "omitted split -> the template's default; omitted "
                        "RECEIVE -> auto-picked when unambiguous")
```

3b. Add the chain helpers (after `_random_split`):

```python
def _parse_part(spec):
    """Parse one ``--part`` value into a generate_chain part dict."""
    fields = spec.split(":")
    if len(fields) == 1:
        return {"topic": fields[0]}
    if len(fields) == 3:
        return {"topic": fields[0], "given": _parse_csv(fields[1]),
                "find": fields[2]}
    if len(fields) == 4:
        part = {"topic": fields[0], "given": _parse_csv(fields[1]),
                "find": fields[2]}
        if fields[3]:
            part["receive"] = fields[3]
        return part
    raise SystemExit(
        f"--part expects TOPIC[:GIVEN,CSV:FIND[:RECEIVE]], got {spec!r}"
    )


def _resolve_receives(parts):
    """Auto-pick each part's ``receive`` when exactly one given fits by unit.

    Mutates ``parts`` in place. Loud ``SystemExit`` on ambiguity — the message
    lists the unit-compatible candidates so the user can add ``:RECEIVE``.
    """
    def split_of(part, template):
        given = part.get("given")
        find = part.get("find")
        if given is None or find is None:
            dg, df = template.default_split
            return [s.name for s in dg], df.name
        return list(given), find

    prev_template = load_template(parts[0]["topic"])
    _, prev_find = split_of(parts[0], prev_template)
    prev_unit = prev_template.unit_for(prev_template.symbol(prev_find))
    for i, part in enumerate(parts[1:], start=1):
        template = load_template(part["topic"])
        given, find = split_of(part, template)
        if not part.get("receive"):
            candidates = [
                g for g in given
                if template.unit_for(template.symbol(g)) == prev_unit
            ]
            if len(candidates) != 1:
                raise SystemExit(
                    f"--part {part['topic']}: cannot auto-pick the receive "
                    f"variable for unit {prev_unit} (candidates: "
                    f"{', '.join(candidates) or 'none'}); add :RECEIVE"
                )
            part["receive"] = candidates[0]
        prev_template, prev_unit = template, template.unit_for(
            template.symbol(find)
        )


def _render_chain(data, verified):
    """Readable multi-part rendering: each part via _render_human + link lines."""
    header = (f"topic: mixed ({' + '.join(data['topics'])})   "
              f"difficulty/policy: {data['policy_applied']}   seed: {data['seed']}")
    links_from = {link["from_part"]: link for link in data["links"]}
    blocks = [header]
    for i, part in enumerate(data["parts"]):
        blocks.append(f"-- part {i + 1} ({part['topic']}) " + "-" * 20)
        blocks.append(_render_human(part, None))
        if i in links_from:
            link = links_from[i]
            unit = part["final_answer"]["unit"]
            blocks.append(
                f"   -> feeds {link['symbol']} of part {link['to_part'] + 1} "
                f"({link['exact']} {unit})"
            )
    fa = data["final_answer"]
    blocks.append(f"chain answer: {fa['value']} {fa['unit']}")
    if verified is not None:
        blocks.append(f"data-fidelity verify: {'PASS' if verified else 'FAIL'}")
    return "\n".join(blocks)
```

3c. In `main`, add the chain branch. After `conditions = _parse_conditions(args.condition)` insert:

```python
    if args.part:
        if args.topic or args.given or args.find or conditions:
            raise SystemExit(
                "--part cannot be combined with --topic/--given/--find/--condition"
            )
        if len(args.part) < 2:
            raise SystemExit("a mixed problem needs at least two --part flags")
        return _run_chain(args)
```

then change the line `given, find = args.given, args.find` block's preceding topic resolution: replace every use of `args.topic` in `main` with a local `topic = args.topic or "suvat"` (assign right after the chain branch), i.e. `_random_split(topic)`, `generate(topic, ...)`, `load_template(topic)`.

3d. Add `_run_chain` (above `main`):

```python
def _run_chain(args):
    """Generate, optionally verify, and print a chained mixed problem."""
    from engine.chain import generate_chain
    from engine.errors import EngineError

    seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    parts = [_parse_part(spec) for spec in args.part]
    try:
        _resolve_receives(parts)
        data = generate_chain(parts, difficulty=args.difficulty, seed=seed)
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    verified = None
    if args.verify:
        from harness.verify import FidelityError, verify_chain
        try:
            verified = verify_chain(data, difficulty=args.difficulty)
        except FidelityError as exc:
            verified = False
            print(f"verify error: {exc}", file=sys.stderr)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_render_chain(data, verified))
    return 1 if verified is False else 0
```

- [ ] **Step 4: Run chain CLI tests and the existing CLI suite**

Run: `.venv/bin/python -m pytest tests/test_chain.py tests/test_cli.py -v`
Expected: all PASSED (existing CLI behavior unchanged — `test_cli_default_is_random` etc. still green).

- [ ] **Step 5: Manual smoke**

Run: `.venv/bin/python -m engine --part free-fall --part suvat:u,a,t:s:u --seed 7 --verify`
Expected: readable two-part output, a `-> feeds u of part 2 (...)` line, `chain answer: ...`, `data-fidelity verify: PASS`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add engine/__main__.py tests/test_chain.py
git commit -m "feat(cli): --part flags generate chained mixed problems"
```

---

### Task 6: README testing docs + full-suite gate

**Files:**
- Modify: `README.md` (the `## Running` block, after the validate-declarative line; and the test-count line)

**Interfaces:**
- Consumes: the CLI from Task 5.
- Produces: documented, runnable test commands for mixed problems.

- [ ] **Step 1: Add the mixed-problems commands to `README.md`'s Running block**

After the `python -m templates.declarative ...` line, insert:

```bash
# mixed (chained) problem: part 1's answer feeds a given of part 2
# --part TOPIC[:given,csv:find[:receive]] (2+ parts; receive auto-picked when unambiguous)
python -m engine --part free-fall --part suvat:u,a,t:s:u --verify
pytest tests/test_chain.py     # chain layer: links, typed errors, CLI, fidelity sweep
```

- [ ] **Step 2: Update the test count on the `pytest` line**

Run `.venv/bin/python -m pytest --collect-only -q | tail -1` for the real number N, then set:

```bash
pytest                 # unit + property tests (N green: engine, harness, declarative gate, parity, topics, chains)
```

- [ ] **Step 3: Full-suite verification gate**

Run: `.venv/bin/python -m pytest -q`
Expected: **all tests pass** (previous count 131 + the new chain tests = N). Paste the summary line into the commit message body.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: how to generate and test mixed (chained) problems"
```
