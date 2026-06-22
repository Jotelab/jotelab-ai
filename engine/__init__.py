"""Jotelab constrained symbolic computation engine (SymPy).

Owns all mathematics for the Batch Generation Engine: given a topic and
constraints it produces a fully-solved problem instance — sampled inputs, the
worked step-by-step solution, units, and the final answer — guaranteed
mathematically correct (spec §1). The LLM downstream phrases and draws; it never
computes.
"""

from engine.loop import generate

__all__ = ["generate"]
