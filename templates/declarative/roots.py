"""Named root-selection policies (ADR-007 sub-decision b).

Authors *pick* a vetted policy; they never write selection logic. v1 offers one:
``smallest_positive_physical``, which reproduces ``templates/suvat.py::root_select``
— filter candidates by the template's per-``find`` physical predicate, take the
smallest strictly-positive real, and (only for a declared set of variables that may
legitimately be zero) fall back to the smallest non-negative real.
"""

from __future__ import annotations

import sympy


def make_root_select(policy, constraints):
    """Build a ``root_select(values, find, difficulty)`` callable from a policy dict."""
    name = policy.get("name")
    if name != "smallest_positive_physical":
        raise ValueError(f"unknown root policy {name!r}")
    fallback = set(policy.get("nonneg_fallback_vars", []))

    def root_select(values, find, difficulty):
        physical = []
        for val in values:
            val = sympy.nsimplify(val)
            if not (val.is_real and val.is_number):
                continue
            if not constraints.is_physical(val, find, difficulty):
                continue
            physical.append(val)
        positive = [x for x in physical if x.is_positive]
        if positive:
            return min(positive)
        nonneg = [x for x in physical if x.is_nonnegative]
        if nonneg and find.name in fallback:
            return min(nonneg)
        return None

    return root_select
