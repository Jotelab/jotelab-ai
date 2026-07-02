"""Infra for declarative templates: typed error + registry.temporary (ADR-007)."""

from engine.errors import EngineError, TemplateValidationError
from engine import registry
from engine.registry import load_template


def test_template_validation_error_carries_stage():
    err = TemplateValidationError(2, "dimensional homogeneity", "v = u + a t^2 is inhomogeneous")
    assert isinstance(err, EngineError)
    assert err.stage == 2
    assert err.stage_name == "dimensional homogeneity"
    assert "inhomogeneous" in str(err)


def test_registry_temporary_swaps_and_restores():
    original = load_template("suvat")

    class Fake:
        topic = "suvat"

    fake = Fake()
    with registry.temporary(fake) as t:
        assert t is fake
        assert load_template("suvat") is fake
    assert load_template("suvat") is original


def test_registry_temporary_new_topic_is_removed_after():
    class Fake:
        topic = "brand_new_topic"

    with registry.temporary(Fake()):
        assert "brand_new_topic" in registry.topics()
    assert "brand_new_topic" not in registry.topics()
