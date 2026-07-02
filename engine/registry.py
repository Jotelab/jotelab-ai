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
    try:
        return _REGISTRY[topic]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"unknown topic {topic!r}; known topics: {known}")


def register(template: Template) -> None:
    """Register a new topic template (used as strands are added; build guide §12)."""
    _REGISTRY[template.topic] = template


def topics() -> list:
    return sorted(_REGISTRY)


@contextlib.contextmanager
def temporary(template):
    """Register ``template`` under its topic for the duration of the block only.

    Lets the validation gate (stage 5) and the parity test drive the unchanged
    ``loop.generate()`` on a candidate template without permanently registering it
    (ADR-007: register only on all-pass). Restores any previous entry — or removes
    a newly-added topic — on exit, even on error.
    """
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
