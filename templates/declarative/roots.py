"""Named root-selection policies (ADR-007 sub-decision b).

Authors *pick* a vetted policy; they never write selection logic. Two exist:

* ``smallest_positive_physical`` — reproduces ``templates/suvat.py::root_select``:
  filter candidates by the template's per-``find`` physical predicate, take the
  smallest strictly-positive real, and (only for a declared set of variables that
  may legitimately be zero) fall back to the smallest non-negative real. This is
  the policy for scalar/magnitude topics where the answer is never negative.
  Optional signed fallback (spec 2026-07-24): with ``signed_fallback_vars``
  (and ``signed_fallback_difficulties``, default medium+hard) a declared
  find may take a negative root — smallest magnitude — when no positive
  root exists.

* ``signed_physical`` — for **vector / direction** topics where the sign of the
  answer *is* physically meaningful (negative displacement, average velocity, or
  acceleration pointing the other way). It keeps every real candidate that passes
  the per-``find`` physical predicate and does **not** discard negatives; a
  deterministic smallest-magnitude tiebreak is applied for the rare multi-root
  case (linear relations have a single root). Positivity of *specific* variables
  (e.g. time) is still enforced — but through the template's own constraints
  (``{"var": "t", "op": ">", "value": 0}``), not baked into the policy.
"""

from __future__ import annotations

import sympy

_DIFFICULTIES = {"easy", "medium", "hard"}


def _signed_fallback_config(policy):
    """Validate and normalize the optional signed-fallback policy keys."""
    names = policy.get("signed_fallback_vars")
    if names is None:
        if "signed_fallback_difficulties" in policy:
            raise ValueError(
                "signed_fallback_difficulties requires signed_fallback_vars")
        return set(), set()
    if (not isinstance(names, list) or not names
            or not all(isinstance(n, str) for n in names)):
        raise ValueError(
            "signed_fallback_vars must be a non-empty list of variable names")
    bands = policy.get("signed_fallback_difficulties", ["medium", "hard"])
    if (not isinstance(bands, list) or not bands
            or not all(isinstance(b, str) for b in bands)
            or not set(bands) <= _DIFFICULTIES):
        raise ValueError("signed_fallback_difficulties must be a non-empty "
                         "subset of easy/medium/hard")
    return set(names), set(bands)


def make_root_select(policy, constraints):
    """Build a ``root_select(values, find, difficulty)`` callable from a policy dict."""
    name = policy.get("name")
    if name == "smallest_positive_physical":
        return _smallest_positive_physical(policy, constraints)
    if name == "signed_physical":
        return _signed_physical(constraints)
    raise ValueError(f"unknown root policy {name!r}")


def _physical_candidates(values, find, difficulty, constraints):
    """Real, numeric candidates that pass the template's per-``find`` predicate."""
    out = []
    for val in values:
        val = sympy.nsimplify(val)
        if not (val.is_real and val.is_number):
            continue
        if not constraints.is_physical(val, find, difficulty):
            continue
        out.append(val)
    return out


def _smallest_positive_physical(policy, constraints):
    fallback = set(policy.get("nonneg_fallback_vars", []))
    signed_vars, signed_bands = _signed_fallback_config(policy)

    def root_select(values, find, difficulty):
        physical = _physical_candidates(values, find, difficulty, constraints)
        positive = [x for x in physical if x.is_positive]
        if positive:
            return min(positive)
        nonneg = [x for x in physical if x.is_nonnegative]
        if nonneg and find.name in fallback:
            return min(nonneg)
        # Signed fallback (spec 2026-07-24): a direction-carrying find may be
        # negative in the declared bands when no positive root exists.
        negative = [x for x in physical if x.is_negative]
        if negative and find.name in signed_vars and difficulty in signed_bands:
            return max(negative)  # smallest magnitude, exact comparison
        return None

    return root_select


def _signed_physical(constraints):
    def root_select(values, find, difficulty):
        physical = _physical_candidates(values, find, difficulty, constraints)
        if not physical:
            return None
        # Linear relations yield a single root; the float key is a deterministic
        # tiebreak only (values themselves stay exact SymPy numbers).
        return min(physical, key=lambda x: (abs(float(x)), float(x)))

    return root_select
