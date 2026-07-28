"""The product promise, asserted across the whole registry: an engine-authored
figure never carries the answer. Adding a topic with a diagram_spec that leaks
its find value fails here, not in review."""

import pytest

from engine import registry
from engine.errors import NoCleanInstanceError, UnsolvableError
from engine.loop import generate

TOPICS = [t for t in registry.topics()
          if registry.load_template(t).diagram_spec is not None]

# plot-2d is the deliberate exception: its polyline is the problem statement for
# graph-reading splits (spec 2026-07-27), so points are shown by design.
POINT_BEARING_KINDS = {"plot-2d"}


def _labels(spec):
    """Every label dict in a diagram, whatever its kind.

    Totals are swept alongside segments and bodies: a whole-trip quantity is as
    capable of carrying the answer as a per-segment one, and `s`, `h`, `disp`
    and `dist` are all commonly the find.
    """
    for segment in spec.get("segments", []):
        for key, val in segment.items():
            if isinstance(val, dict):
                yield val
    for body in spec.get("bodies", []):
        yield body["velocity"]
    for total in spec.get("totals", []):
        yield total


@pytest.mark.parametrize("topic", TOPICS)
def test_no_diagram_label_ever_carries_the_find_value(topic):
    template = registry.load_template(topic)
    checked = 0
    for given, find in template.valid_splits():
        for seed in range(5):
            try:
                data = generate(topic, given=tuple(s.name for s in given),
                                find=find.name, difficulty="easy", seed=seed)
            except (UnsolvableError, NoCleanInstanceError):
                continue
            spec = data["diagram"]
            if spec["kind"] in POINT_BEARING_KINDS:
                continue
            for label in _labels(spec):
                if label["symbol"] == data["find"]["symbol"]:
                    assert label["role"] == "find"
                    assert "value" not in label, (topic, given, find, seed)
                    assert "exact" not in label, (topic, given, find, seed)
            checked += 1
    if not checked:
        pytest.skip(f"{topic} produced no drawable instance to sweep")


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


@pytest.mark.parametrize("topic", TOPICS)
def test_a_total_declares_what_it_measures(topic):
    """A bracket across the figure is ambiguous without it: net displacement,
    path length, elapsed time and average rate are drawn differently."""
    from templates.diagrams import TOTAL_MEASURES

    template = registry.load_template(topic)
    given, find = template.default_split
    data = generate(topic, given=tuple(s.name for s in given), find=find.name,
                    difficulty="easy", seed=1)
    for total in data["diagram"].get("totals", []):
        assert total["measures"] in TOTAL_MEASURES
