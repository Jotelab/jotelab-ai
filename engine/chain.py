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
    bounded re-rolls are exhausted. UnsolvableError or OverDeterminedError from
    an invalid split propagate immediately; re-rolling cannot fix a structurally
    unsolvable split.
    """
    if max_chain_attempts < 1:
        raise ChainSpecError("max_chain_attempts must be at least 1")
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
