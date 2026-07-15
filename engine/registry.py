"""Topic registry — ``load_template(topic) -> Template`` (build guide §5).

A flat lookup from a topic name to its :class:`~templates.base.Template`. New
strands register here; the loop is topic-agnostic and goes through this map.
"""

from __future__ import annotations

import contextlib

from templates.base import Template
from templates.suvat import SUVAT

_REGISTRY = {
    SUVAT.topic: SUVAT,
}


def load_template(topic: str) -> Template:
    """Return the template for ``topic`` (e.g. ``"suvat"``)."""
    _ensure_declarative_loaded()
    try:
        return _REGISTRY[topic]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"unknown topic {topic!r}; known topics: {known}")


def register(template: Template) -> None:
    """Register a new topic template (used as strands are added; build guide §12)."""
    _REGISTRY[template.topic] = template


def topics() -> list:
    _ensure_declarative_loaded()
    return sorted(_REGISTRY)


@contextlib.contextmanager
def temporary(template):
    """Register ``template`` under its topic for the duration of the block only.

    Lets the validation gate (stage 5) and the parity test drive the unchanged
    ``loop.generate()`` on a candidate template without permanently registering it
    (ADR-007: register only on all-pass). Restores any previous entry — or removes
    a newly-added topic — on exit, even on error.
    """
    # Populate declarative topics *before* snapshotting, so that entering a
    # ``temporary`` block whose key is a declarative topic sees ``had=True`` and
    # restores the permanent entry on exit — rather than popping it because the
    # lazy load hadn't run yet when the snapshot was taken.
    _ensure_declarative_loaded()
    key = template.topic
    had = key in _REGISTRY
    prev = _REGISTRY.get(key)
    _REGISTRY[key] = template
    try:
        yield template
    finally:
        if had:
            _REGISTRY[key] = prev
        else:
            _REGISTRY.pop(key, None)


# --- Declarative topic strands (ADR-007) -----------------------------------
# Topics authored as JSON in ``templates/data/`` and vetted by the five-stage
# validation gate in CI (``tests/test_*`` + ``python -m templates.declarative``).
# They are parsed straight into the registry — the gate is a build-time check,
# not an import-time cost.
_DECLARATIVE_TOPICS = ("vectors_1d.json", "free_fall.json")
_declarative_loaded = False


def _ensure_declarative_loaded() -> None:
    """Parse and register the declarative JSON topics on first lookup.

    Done lazily — on the first ``load_template``/``topics`` call — rather than at
    registry-import time. Parsing pulls in the ``templates.declarative`` package,
    whose ``gate`` module imports ``engine.loop.generate``; at registry-import
    time ``engine.loop`` is still mid-initialization (the loop's own
    ``from engine.registry import load_template`` is what triggers this module),
    so an eager parse would deadlock the import graph. By the time anything
    *calls* ``load_template``/``topics`` every module is fully imported. The flag
    is set before parsing so a re-entrant lookup during load can't recurse.
    """
    global _declarative_loaded
    if _declarative_loaded:
        return
    _declarative_loaded = True

    import json
    from pathlib import Path

    from templates.declarative.parse import parse_template

    data_dir = Path(__file__).resolve().parents[1] / "templates" / "data"
    for filename in _DECLARATIVE_TOPICS:
        template = parse_template(json.loads((data_dir / filename).read_text()))
        _REGISTRY.setdefault(template.topic, template)
