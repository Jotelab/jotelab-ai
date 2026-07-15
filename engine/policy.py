"""The clean-answer policy (spec §6, build guide §9).

"Clean" is a *policy* decision, not a mathematical fact: it defines what makes an
answer appropriate for the grade band, and it drives re-roll cost. Two orthogonal
checks live here and the loop combines them in ``satisfies()``:

* **Cleanliness tier** (loosenable) — how many decimal places / what fraction
  denominators are acceptable. Driven by difficulty; loosened once at
  ``SOFT_LIMIT`` before the loop gives up.
* **Plausibility** (never loosened) — lives in the template's constraints, not
  here; ``loosen()`` only relaxes cleanliness.

Cleanliness is tested on the **exact** SymPy value (build guide §9): a float can
"look" clean even when the exact value isn't, which would let an ugly number slip
past the gate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import sympy

# Loosening cap: never accept more than 3 decimal places, even after loosening.
_MAX_PLACES_CAP = 3


@dataclass(frozen=True)
class Policy:
    """A clean-answer policy tier.

    ``max_places``   — maximum terminating-decimal places allowed.
    ``allow_fraction`` — also accept a clean rational (small denominator).
    ``require_positive`` — the answer itself must be positive (easy band).
    ``difficulty``   — the originating difficulty (for ``policy_applied``).
    ``loosened``     — whether this tier was already loosened once.
    """

    difficulty: str
    max_places: int
    allow_fraction: bool
    require_positive: bool
    loosened: bool = False

    def is_clean(self, value) -> bool:
        """Is ``value`` (an exact SymPy number) clean under this tier?"""
        val = sympy.nsimplify(value)
        if not (val.is_real and val.is_number):
            return False
        if self.require_positive and val.is_negative:
            return False
        if self.allow_fraction and val.is_Rational and abs(val.q) <= 12:
            return True
        scaled = sympy.nsimplify(val * sympy.Integer(10) ** self.max_places)
        return bool(scaled.is_Integer)

    @property
    def label(self) -> str:
        return f"{self.difficulty}{'+loosened' if self.loosened else ''}"


# Default tiers per difficulty (spec §6).
_DEFAULTS = {
    # Easy = integer or terminating 1-decimal; positive.
    "easy": dict(max_places=1, allow_fraction=False, require_positive=True),
    # Medium = up to 2 decimals, or a clean fraction.
    "medium": dict(max_places=2, allow_fraction=True, require_positive=False),
    # Hard = 2 decimals; intermediate steps may be non-integer.
    "hard": dict(max_places=2, allow_fraction=False, require_positive=False),
}


def for_(topic: str, difficulty: str) -> Policy:
    """Starting clean-answer policy for a topic+difficulty (spec §6)."""
    if difficulty not in _DEFAULTS:
        raise ValueError(
            f"unknown difficulty {difficulty!r}; expected one of {sorted(_DEFAULTS)}"
        )
    return Policy(difficulty=difficulty, **_DEFAULTS[difficulty])


def permit_sign(policy: Policy) -> Policy:
    """Drop the positive-answer requirement — for vector/direction topics (spec §6).

    On the easy band the default tier sets ``require_positive`` so scalar answers
    come out forward/non-negative. A signed topic (displacement, average velocity)
    needs the sign to survive, since it *encodes direction*; this relaxes only that
    one flag, leaving the cleanliness tier (decimal places / fractions) intact.
    Applied by the loop when ``template.signed_answer`` is set.
    """
    return replace(policy, require_positive=False)


def loosen(policy: Policy) -> Policy:
    """Relax the cleanliness tier one notch (spec §5, §6).

    Increments the allowed decimal places (e.g. integer→1-decimal→2-decimal),
    capped at :data:`_MAX_PLACES_CAP`. Plausibility constraints are *not* touched
    — those live in the template and are never loosened.
    """
    return replace(
        policy,
        max_places=min(policy.max_places + 1, _MAX_PLACES_CAP),
        loosened=True,
    )
