"""Scene compiler ontology (spec 2026-07-29, Task 1): names, units, rendering.

Fixes the quantity-naming convention every later scene-compiler task relies on:

| Quantity                          | Name             | Unit  | Role                |
|------------------------------------|------------------|-------|---------------------|
| duration of phase i (auto)         | ``t_<i>``        | s     | auxiliary           |
| displacement of body b in phase i  | ``s_<body>_<i>`` | m     | auxiliary           |
| end velocity of body b in phase i  | ``vend_<body>_<i>`` | m/s | auxiliary           |
| meet position                      | ``x_meet``       | m     | auxiliary           |
| sought                             | its scene ``name``   | its scene ``unit`` | find |

``render`` turns a single phase-field value (as it appears in a scene document)
into an equation fragment: a given's name, a numeric literal, or a negated
reference. It never handles ``"auto"`` — that sentinel is the compiler's own
signal to derive a value itself, and reaching ``render`` with it is a bug.
"""

from __future__ import annotations

import sympy


class SceneError(ValueError):
    """A scene document is malformed in a way the compiler cannot proceed past."""


def duration_name(i):
    """Name of the (auto) duration of phase ``i``: ``t_<i>``."""
    return f"t_{i}"


def displacement_name(body, i):
    """Name of body ``body``'s displacement in phase ``i``: ``s_<body>_<i>``."""
    return f"s_{body}_{i}"


def vend_name(body, i):
    """Name of body ``body``'s end velocity in phase ``i``: ``vend_<body>_<i>``."""
    return f"vend_{body}_{i}"


MEET_NAME = "x_meet"

UNITS = {"duration": "s", "displacement": "m", "velocity": "m/s"}


def render(value, given_names):
    """Render one phase-field ``value`` as an equation fragment (string).

    * A string equal to one of ``given_names`` renders as itself.
    * A string of the form ``"neg:NAME"`` renders as ``"(-NAME)"`` (the NAME
      itself is not validated here — that is the compiler's job).
    * An ``int``/``float`` renders as its exact numeral via
      ``sympy.nsimplify``. A float that is not exactly that rational (e.g. the
      classic ``0.1 + 0.2`` binary artifact) raises :class:`SceneError` rather
      than silently rendering a rounded value.
    * Anything else — including the ``"auto"`` sentinel, which the compiler
      must resolve itself before ever reaching ``render`` — raises
      :class:`SceneError`.
    """
    if isinstance(value, str):
        if value in given_names:
            return value
        if value.startswith("neg:"):
            return f"(-{value[len('neg:'):]})"
        raise SceneError(
            f"cannot render {value!r}: not a given name and not 'neg:'-prefixed"
        )
    if isinstance(value, bool):
        raise SceneError(f"cannot render {value!r}: booleans are not values")
    if isinstance(value, (int, float)):
        exact = sympy.nsimplify(value, rational=True)
        if isinstance(value, float) and float(exact) != value:
            raise SceneError(f"{value!r} is not an exact value")
        return str(exact)
    raise SceneError(f"cannot render value of type {type(value).__name__}: {value!r}")
