"""Topic registry — ``load_template(topic) -> Template`` (build guide §5).

A flat lookup from a topic name to its :class:`~templates.base.Template`. New
strands register here; the loop is topic-agnostic and goes through this map.
"""

from __future__ import annotations

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
