"""Declarative topic templates (ADR-007): parse + validate JSON into a Template."""

from templates.declarative.parse import parse_template, trust_state_of
from templates.declarative.gate import validate_template, register_declarative, Report

__all__ = ["parse_template", "trust_state_of", "validate_template",
           "register_declarative", "Report"]
