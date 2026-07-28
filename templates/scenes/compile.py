"""Scene -> system-template compiler (spec 2026-07-29, Task 3).

``compile_scene(scene: dict) -> dict`` takes a physics *scene* document (bodies
walking through phases, an optional meet event, a sought quantity) and
compiles it into the exact declarative doc shape ``templates.declarative.parse
.parse_template`` accepts and ``templates.declarative.gate.validate_template``
gates. See the scene-compiler plan
(docs/superpowers/plans/2026-07-29-scene-compiler.md) for the full scene
format; this module implements its six-step algorithm:

1. Validate the scene's structure (closed top-level key set, unique body
   names, known phase kinds, declared given references, a sought name that
   doesn't collide with a given or an emitted auxiliary).
2. Walk each body's phases, resolving ``u: "auto"`` chains, ``duration:
   "auto"`` auxiliaries, and ``end_condition`` closures.
3. Process ``events`` (v1: ``meet`` only).
4. Process ``sought`` per its kind.
5. Assemble the compiled doc.
6. Run the well-posedness (determinism) check.

Interface note (deviation from the plan's literal equation form, forced by the
frozen gate): the plan's "Compiler-emitted equations" section says an
``end_condition {"v": k}`` emits ``Eq(vend_b_i, k)``. That literal equation
cannot pass the existing (frozen, unmodified) dimensional-homogeneity gate
stage for *any* k, because a bare numeral is dimensionless and can never equal
a dimensioned symbol under ``templates.declarative.units.check_homogeneous``
(verified empirically). Instead, this compiler still emits ``vend_b_i``'s
ordinary kb equation (so it remains a declared auxiliary, matching the plan's
naming table) and encodes the boundary condition as the equation that
*derives the auto duration from it*: ``Eq(duration_sym, (k - u_expr) /
a_expr)``. For k == 0 (the plan's own worked example and the only value v1
needs), the literal ``0`` cancels away during SymPy's parse-time
simplification (``0 - u_expr`` -> ``-u_expr``), leaving a fully symbolic,
dimensionally-sound equation that reproduces the exact same numbers. A
nonzero k would leave a bare numeral that legitimately fails dimensional
homogeneity (correctly so -- physically, "5" alone is not a velocity); v1
scenes should stick to k == 0 until a follow-up task threads pinned-constant
givens through for nonzero targets.
"""

from __future__ import annotations

import ast

from .kb import phase_equations
from .ontology import (
    MEET_NAME,
    UNITS,
    SceneError,
    displacement_name,
    duration_name,
    render,
    vend_name,
)

_TOP_LEVEL_KEYS = {
    "topic", "bodies", "given", "sought", "events", "constraints",
    "golden_cases", "trust_state",
}
_PHASE_KINDS = {"constant-velocity", "constant-acceleration"}
_SOUGHT_QUANTITIES = {"total_displacement", "duration_of_phase", "phase_field"}
_PHASE_FIELD_FIELDS = {"a", "v", "u"}
_RESERVED_GIVEN_NAMES = {"Eq", "sqrt", "Rational"}


def compile_scene(scene: dict) -> dict:
    """Compile a scene document into a system-template doc (spec 2026-07-29)."""
    _validate_top_level(scene)

    bodies = scene["bodies"]
    given = scene["given"]
    given_names = set(given)
    sought = scene["sought"]
    events = scene.get("events", [])

    bodies_by_name = _validate_bodies_structure(bodies)
    _validate_multi_body_v1(bodies)
    _validate_sought_structure(sought, given_names)

    duration_override = _duration_override_for_sought(sought, bodies_by_name)

    equations = []
    aux = {}
    for body in bodies:
        b_equations, b_aux = _compile_body(body, given_names, duration_override)
        equations.extend(b_equations)
        aux.update(b_aux)

    ev_equations, ev_aux, meet_present = _process_events(events, bodies_by_name, given_names)
    equations.extend(ev_equations)
    aux.update(ev_aux)

    remaining_given_names = set(given_names)
    quantity = sought["quantity"]

    if quantity == "total_displacement":
        find_name = sought["name"]
        _check_sought_name_collision(find_name, remaining_given_names, aux)
        body = _lookup_body(bodies_by_name, sought["body"])
        n = len(body["phases"])
        terms = " + ".join(displacement_name(body["name"], j) for j in range(1, n + 1))
        equations.append(f"Eq({find_name}, {terms})")
        find_unit = sought["unit"]
        find_ranges = sought["ranges"]

    elif quantity == "duration_of_phase":
        find_name = sought["name"]
        _check_sought_name_collision(find_name, remaining_given_names, aux)
        find_unit = sought["unit"]
        find_ranges = sought["ranges"]

    elif quantity == "phase_field":
        body = _lookup_body(bodies_by_name, sought["body"])
        phase_idx = sought["phase"]
        field = sought["field"]
        if field not in _PHASE_FIELD_FIELDS:
            raise SceneError(f"sought.field must be one of {_PHASE_FIELD_FIELDS}, got {field!r}")
        if not isinstance(phase_idx, int) or not (1 <= phase_idx <= len(body["phases"])):
            raise SceneError(f"sought.phase {phase_idx!r} is out of range for body {sought['body']!r}")
        phase = body["phases"][phase_idx - 1]
        given_ref = phase.get(field)
        if not isinstance(given_ref, str) or given_ref not in given_names:
            raise SceneError(
                f"sought phase_field targets {field!r} of phase {phase_idx} of "
                f"{sought['body']!r}, but it is not a declared given name: {given_ref!r}"
            )
        if sought["name"] != given_ref:
            raise SceneError(
                f"sought.name {sought['name']!r} must equal the given name it replaces "
                f"({given_ref!r}) for phase_field"
            )
        _check_sought_name_collision(given_ref, remaining_given_names - {given_ref}, aux)
        remaining_given_names.discard(given_ref)
        find_name = given_ref
        find_unit = given[given_ref]["unit"]
        find_ranges = given[given_ref]["ranges"]

    else:  # pragma: no cover - guarded by _validate_sought_structure
        raise SceneError(f"unknown sought.quantity {quantity!r}")

    # Name-sorted, not set-ordered: the emitted dict's key order becomes the
    # Template's symbol order, which drives Template.valid_splits() and hence
    # the CLI's random split pick. Iterating the set directly made that order
    # vary per process (string hash randomization), so a bare `python -m engine`
    # run was reproducible only within one process — and the random-topic CLI
    # test flaked whenever the roll landed on a split this v1 scene cannot
    # solve inside the re-roll budget.
    variables = {
        name: {"unit": given[name]["unit"], "ranges": given[name]["ranges"]}
        for name in sorted(remaining_given_names)
    }
    variables[find_name] = {"unit": find_unit, "ranges": find_ranges}

    constraints = list(scene.get("constraints", []))
    auto_duration_names = sorted(n for n, unit in aux.items() if unit == UNITS["duration"])
    for dname in auto_duration_names:
        constraints.append({"var": dname, "op": ">", "value": 0})
    if meet_present:
        constraints.append({"var": MEET_NAME, "op": ">", "value": 0})

    golden_cases = [
        {**case, "find": find_name} for case in scene.get("golden_cases", [])
    ]

    doc = {
        "topic": scene["topic"],
        "variables": variables,
        "auxiliary": {name: {"unit": unit} for name, unit in aux.items()},
        "equations": equations,
        "root_policy": {"name": "smallest_positive_physical"},
        "constraints": constraints,
        "default_split": {"given": sorted(remaining_given_names), "find": find_name},
        "golden_cases": golden_cases,
        "trust_state": scene.get("trust_state", "unverified"),
    }

    _check_determinism(equations, aux)
    _check_no_unused_given(equations, constraints, remaining_given_names)

    return doc


# --- Step 1: structural validation ------------------------------------------


def _validate_top_level(scene):
    if not isinstance(scene, dict):
        raise SceneError(f"scene must be a dict, got {type(scene).__name__}")
    unknown = set(scene) - _TOP_LEVEL_KEYS
    if unknown:
        raise SceneError(f"scene has unknown top-level key(s): {sorted(unknown)}")
    for required in ("topic", "bodies", "given", "sought"):
        if required not in scene:
            raise SceneError(f"scene is missing required key {required!r}")
    if not isinstance(scene["bodies"], list) or not scene["bodies"]:
        raise SceneError("scene.bodies must be a non-empty list")
    if not isinstance(scene["given"], dict):
        raise SceneError("scene.given must be a dict")
    for gname, gspec in scene["given"].items():
        if not isinstance(gname, str) or not gname.isidentifier():
            raise SceneError(f"given name {gname!r} must be a valid Python identifier")
        if gname in _RESERVED_GIVEN_NAMES:
            raise SceneError(
                f"given name {gname!r} is reserved (parser built-in) and cannot be used"
            )
        if not isinstance(gspec, dict) or "unit" not in gspec or "ranges" not in gspec:
            raise SceneError(f"given {gname!r} needs a 'unit' and 'ranges'")


def _validate_bodies_structure(bodies):
    """Validate body names are unique, identifier-safe, and have phases; return name->body."""
    bodies_by_name = {}
    for body in bodies:
        if not isinstance(body, dict) or "name" not in body:
            raise SceneError("each body needs a 'name'")
        name = body["name"]
        if not isinstance(name, str) or not name.isidentifier():
            raise SceneError(f"body name {name!r} must be a valid Python identifier")
        if name in bodies_by_name:
            raise SceneError(f"duplicate body name {name!r}")
        phases = body.get("phases")
        if not isinstance(phases, list) or not phases:
            raise SceneError(f"body {name!r} needs a non-empty 'phases' list")
        bodies_by_name[name] = body
    return bodies_by_name


def _validate_multi_body_v1(bodies):
    if len(bodies) > 1:
        for body in bodies:
            if len(body["phases"]) != 1:
                raise SceneError(
                    "v1 only supports multi-body scenes with exactly one phase per "
                    "body; multi-phase multi-body scenes are v2"
                )


def _validate_sought_structure(sought, given_names):
    if not isinstance(sought, dict):
        raise SceneError("scene.sought must be a dict")
    for required in ("quantity", "name", "unit", "ranges"):
        if required not in sought:
            raise SceneError(f"sought is missing required key {required!r}")
    quantity = sought["quantity"]
    if quantity not in _SOUGHT_QUANTITIES:
        raise SceneError(f"unknown sought.quantity {quantity!r}; known: {sorted(_SOUGHT_QUANTITIES)}")
    name = sought["name"]
    if not isinstance(name, str) or not name.isidentifier():
        raise SceneError(f"sought.name {name!r} must be a valid Python identifier")
    if quantity in ("total_displacement", "phase_field") and "body" not in sought:
        raise SceneError(f"sought.quantity {quantity!r} requires a 'body'")
    if quantity == "duration_of_phase" and ("body" not in sought or "phase" not in sought):
        raise SceneError("sought.quantity 'duration_of_phase' requires a 'body' and a 'phase'")
    if quantity == "phase_field" and ("phase" not in sought or "field" not in sought):
        raise SceneError("sought.quantity 'phase_field' requires 'phase' and 'field'")


def _lookup_body(bodies_by_name, body_name):
    body = bodies_by_name.get(body_name)
    if body is None:
        raise SceneError(f"sought.body {body_name!r} is not a declared body")
    return body


def _check_sought_name_collision(name, given_names, aux):
    if name in given_names:
        raise SceneError(f"sought name {name!r} collides with a given name")
    if name in aux:
        raise SceneError(f"sought name {name!r} collides with an auxiliary name")


def _validate_declared_ref(value, given_names, context):
    """Validate a ``neg:NAME`` reference's NAME is a declared given (render() doesn't)."""
    if isinstance(value, str) and value.startswith("neg:"):
        target = value[len("neg:"):]
        if target not in given_names:
            raise SceneError(f"{context}: neg:-prefixed reference {target!r} is not a declared given")


# --- Step 2: per-body phase walk --------------------------------------------


def _validate_phase_fields(phase, i, body_name):
    kind = phase.get("kind")
    if kind not in _PHASE_KINDS:
        raise SceneError(f"body {body_name!r} phase {i}: unknown phase kind {kind!r}")
    if "duration" not in phase:
        raise SceneError(f"body {body_name!r} phase {i}: missing 'duration'")
    if kind == "constant-velocity" and "v" not in phase:
        raise SceneError(f"body {body_name!r} phase {i}: constant-velocity requires 'v'")
    if kind == "constant-acceleration":
        if "u" not in phase:
            raise SceneError(f"body {body_name!r} phase {i}: constant-acceleration requires 'u'")
        if "a" not in phase:
            raise SceneError(f"body {body_name!r} phase {i}: constant-acceleration requires 'a'")
    return kind


def _compile_body(body, given_names, duration_override):
    name = body["name"]
    phases = body["phases"]
    n = len(phases)

    kinds = [_validate_phase_fields(phase, i, name) for i, phase in enumerate(phases, start=1)]

    # Pass 1: which phases are forced to emit their end velocity.
    needs_vend = {i: False for i in range(1, n + 1)}
    for i, phase in enumerate(phases, start=1):
        if "end_condition" in phase:
            needs_vend[i] = True
        if phase.get("u") == "auto":
            if i == 1:
                raise SceneError(f"body {name!r} phase 1 cannot chain u from a previous phase")
            needs_vend[i - 1] = True

    equations = []
    aux = {}

    for i, phase in enumerate(phases, start=1):
        kind = kinds[i - 1]

        # Resolve duration.
        duration_field = phase["duration"]
        if duration_field == "auto":
            override_name = duration_override.get(i)
            duration_sym = override_name or duration_name(i)
            if override_name is None:
                aux[duration_sym] = UNITS["duration"]
        elif isinstance(duration_field, str) and duration_field in given_names:
            duration_sym = duration_field
        else:
            raise SceneError(
                f"body {name!r} phase {i}: duration must be a declared given name or "
                f"'auto', got {duration_field!r}"
            )

        resolved_phase = dict(phase)
        resolved_phase["duration"] = duration_sym

        # Resolve u_expr (constant-acceleration only).
        u_expr = None
        a_expr = None
        if kind == "constant-acceleration":
            u_field = phase["u"]
            if u_field == "auto":
                if i == 1:
                    raise SceneError(f"body {name!r} phase 1 cannot chain u from a previous phase")
                u_expr = vend_name(name, i - 1)
            else:
                _validate_declared_ref(u_field, given_names, f"body {name!r} phase {i} u")
                u_expr = render(u_field, given_names)
            _validate_declared_ref(phase["a"], given_names, f"body {name!r} phase {i} a")
            a_expr = render(phase["a"], given_names)
        else:
            _validate_declared_ref(phase["v"], given_names, f"body {name!r} phase {i} v")
            render(phase["v"], given_names)  # validate now; kb.py re-renders it itself

        b_eqs, b_aux = phase_equations(name, i, resolved_phase, u_expr, needs_vend[i], given_names)
        equations.extend(b_eqs)
        aux.update(b_aux)

        if "end_condition" in phase:
            if kind != "constant-acceleration":
                raise SceneError(
                    f"body {name!r} phase {i}: end_condition is only supported for "
                    "constant-acceleration phases"
                )
            if duration_field != "auto":
                raise SceneError(
                    f"body {name!r} phase {i}: end_condition requires an 'auto' duration"
                )
            end_condition = phase["end_condition"]
            if not isinstance(end_condition, dict) or "v" not in end_condition:
                raise SceneError(f"body {name!r} phase {i}: end_condition must be {{'v': <number>}}")
            k = end_condition["v"]
            _validate_declared_ref(k, given_names, f"body {name!r} phase {i} end_condition.v")
            if not isinstance(k, (int, float)) or isinstance(k, bool):
                raise SceneError(
                    f"body {name!r} phase {i}: end_condition.v must be a number, got {k!r}"
                )
            if k != 0:
                # See module docstring: nonzero end-velocity targets leave a bare,
                # dimensionless residual literal in the derived-duration equation below
                # and would legitimately fail the frozen dimensional-homogeneity gate
                # downstream. Reject here rather than let the compiler emit a doc that
                # only fails several stages later, naming an equation the scene author
                # never wrote.
                raise SceneError(
                    f"body {name!r} phase {i}: end_condition.v={k!r} is unsupported in "
                    "v1 (only v == 0 boundary conditions are supported; nonzero targets "
                    "require a pinned-constant given, not yet implemented)"
                )
            k_str = render(k, given_names)
            # This derives the auto duration from the boundary condition rather than
            # literally pinning vend_b_i to k (which cannot pass the frozen dimensional-
            # homogeneity gate for a bare numeral -- see module docstring).
            equations.append(f"Eq({duration_sym}, ({k_str} - {u_expr})/{a_expr})")

    return equations, aux


def _duration_override_for_sought(sought, bodies_by_name):
    """For ``duration_of_phase``, the sought name replaces the phase's t_<i> aux.

    Implemented as a lookup the phase walk consults so the sought name is
    emitted directly into equations (no post-hoc string substitution).
    """
    if sought.get("quantity") != "duration_of_phase":
        return {}
    body_name = sought.get("body")
    phase_idx = sought.get("phase")
    body = _lookup_body(bodies_by_name, body_name)
    phases = body["phases"]
    if not isinstance(phase_idx, int) or not (1 <= phase_idx <= len(phases)):
        raise SceneError(f"sought.phase {phase_idx!r} is out of range for body {body_name!r}")
    if phases[phase_idx - 1].get("duration") != "auto":
        raise SceneError(
            f"sought duration_of_phase targets phase {phase_idx} of {body_name!r}, "
            "but that phase's duration is not 'auto'"
        )
    return {phase_idx: sought["name"]}


# --- Step 3: events -----------------------------------------------------------


def _process_events(events, bodies_by_name, given_names):
    equations = []
    aux = {}
    meet_present = False
    for event in events:
        kind = event.get("kind")
        if kind != "meet":
            raise SceneError(f"unknown event kind {kind!r}; v1 supports only 'meet'")
        ev_bodies = event.get("bodies")
        if not isinstance(ev_bodies, list) or len(ev_bodies) != 2:
            raise SceneError("meet event requires exactly two 'bodies'")
        if ev_bodies[0] == ev_bodies[1]:
            raise SceneError(
                f"meet event bodies must be two distinct bodies, got {ev_bodies[0]!r} twice"
            )
        for bn in ev_bodies:
            if bn not in bodies_by_name:
                raise SceneError(f"meet event references undeclared body {bn!r}")
        at_end = event.get("at_end_of_phase")
        if at_end != 1:
            raise SceneError(
                "meet events deeper than phase 1 are not supported in v1 (v2)"
            )
        head_start = event.get("head_start", {})
        hs_body = head_start.get("body")
        hs_given = head_start.get("given")
        if hs_body not in ev_bodies:
            raise SceneError(f"meet event head_start.body {hs_body!r} must be one of {ev_bodies}")
        if hs_given not in given_names:
            raise SceneError(f"meet event head_start.given {hs_given!r} is not a declared given")

        meet_present = True
        aux[MEET_NAME] = UNITS["displacement"]
        for bn in ev_bodies:
            term = displacement_name(bn, at_end)
            if bn == hs_body:
                equations.append(f"Eq({MEET_NAME}, {hs_given} + {term})")
            else:
                equations.append(f"Eq({MEET_NAME}, {term})")
    return equations, aux, meet_present


# --- Step 6: determinism check -----------------------------------------------


def _check_determinism(equations, aux):
    n_equations = len(equations)
    n_unknowns = 1 + len(aux)
    if n_equations != n_unknowns:
        raise SceneError(
            f"scene is underdetermined/overdetermined: {n_equations} equations "
            f"for {n_unknowns} unknowns"
        )


def _referenced_names(equations):
    """Collect every identifier referenced across a list of ``Eq(...)`` strings.

    Each equation string is shaped like a Python expression (it is literally
    parsed and evaluated as one downstream), so an AST parse in expression
    mode is the safest way to find every name it mentions -- including names
    that appear only inside a ``(-NAME)`` fragment emitted for a ``neg:NAME``
    reference, which ``ast.Name`` naturally sees like any other identifier.
    """
    names = set()
    for eq_str in equations:
        tree = ast.parse(eq_str, mode="eval")
        names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    return names


def _referenced_names_in_constraints(constraints):
    """Collect names referenced by the doc's own ``constraints`` entries.

    ``templates.declarative.constraints.compile_constraints`` treats a
    constraint's ``var`` field as a plain symbol name (looked up directly in
    the template's symbol table), so it always counts as a reference. Its
    ``value`` field is passed through ``sympy.nsimplify`` before comparison,
    which -- for a string value -- sympifies it as an expression rather than
    a bare numeral, so a symbolic ``value`` (e.g. a name or an expression
    naming one) can also reference a given. Both fields are accounted for
    here so a given that is only ever bounded by a constraint (spec-
    sanctioned: constraints genuinely restrict sampling) is not mistaken for
    unused.
    """
    names = set()
    for c in constraints:
        if not isinstance(c, dict):
            continue
        var = c.get("var")
        if isinstance(var, str):
            names.add(var)
        value = c.get("value")
        if isinstance(value, str):
            try:
                tree = ast.parse(value, mode="eval")
            except SyntaxError:
                continue
            names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    return names


def _check_no_unused_given(equations, constraints, remaining_given_names):
    """Reject a given that no emitted equation or constraint references.

    An unused given would otherwise pass compile + the full gate and ship as
    a red-herring fact in generated problems: the engine samples a value for
    it, but nothing ever constrains it.
    """
    referenced = _referenced_names(equations) | _referenced_names_in_constraints(constraints)
    for name in sorted(remaining_given_names):
        if name not in referenced:
            raise SceneError(f"given {name!r} is declared but never used by any equation")
