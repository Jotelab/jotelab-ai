"""Command-line entry point: ``python -m engine``.

Generate one fully-solved physics problem instance and print it, optionally
re-checking it through the Data Fidelity harness. A thin wrapper over
:func:`engine.loop.generate` — no new engine logic lives here.

By default each run is **fresh**: with no ``--given``/``--find`` the CLI picks a
random valid given/find split, and with no ``--seed`` it picks a random seed — so
calling it repeatedly yields different problems. Both choices are echoed in the
output (the ``seed`` line and the ``given``/``find`` lines), so any run is exactly
reproducible by passing that seed (and split) back. Provide ``--seed`` and/or
``--given``/``--find`` to pin them.

Examples::

    # Basic mode — a different random clean SUVAT problem each run
    python -m engine

    # Reproduce a specific problem (pin the split and the seed)
    python -m engine --given u,a,t --find v --seed 42

    # Advanced mode — pin Given values, choose the Find target
    python -m engine --given u,a,t --find v --condition u=0 --condition a=2 --condition t=5

    # Raw sympy_data contract, and run the verifier
    python -m engine --seed 42 --json --verify
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from engine.errors import EngineError
from engine.loop import generate
from engine.registry import load_template, topics


def _parse_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_conditions(pairs):
    """Parse ``--condition u=0`` entries (repeatable) into ``{name: int}``."""
    conditions = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--condition expects NAME=VALUE, got {pair!r}")
        name, _, raw = pair.partition("=")
        try:
            conditions[name.strip()] = int(raw)
        except ValueError:
            raise SystemExit(f"--condition value must be an integer, got {raw!r}")
    return conditions


def _build_parser():
    p = argparse.ArgumentParser(
        prog="python -m engine",
        description="Generate a clean, fully-solved physics problem (SymPy engine).",
    )
    p.add_argument("--topic", default="suvat",
                   help=f"topic template (known: {', '.join(topics())})")
    p.add_argument("--given", type=_parse_csv, default=None,
                   help="comma-separated Given variables, e.g. u,a,t (Advanced mode)")
    p.add_argument("--find", default=None,
                   help="the single Find/target variable, e.g. v (Advanced mode)")
    p.add_argument("--condition", action="append", default=[], metavar="NAME=VALUE",
                   help="pin a variable to an exact value (repeatable)")
    p.add_argument("--difficulty", default="easy",
                   choices=["easy", "medium", "hard"])
    p.add_argument("--seed", type=int, default=None,
                   help="RNG seed (reproducible); random each run if omitted")
    p.add_argument("--json", action="store_true",
                   help="print the raw sympy_data JSON instead of a readable summary")
    p.add_argument("--verify", action="store_true",
                   help="re-check the instance through the Data Fidelity harness")
    return p


def _render_human(data, verified):
    lines = [f"topic: {data['topic']}   difficulty/policy: {data['policy_applied']}"
             f"   seed: {data['seed']}"]
    given = "   ".join(
        f"{g['symbol']} = {g['value']} {g['unit']}" for g in data["given"]
    )
    lines.append(f"given:  {given}")
    f = data["find"]
    lines.append(f"find:   {f['symbol']} = {f['value']} {f['unit']}")
    lines.append("steps:")
    for step in data["steps"]:
        lines.append(f"   {step['expr_latex']}")
        lines.append(f"   {step['substituted_latex']}")
        lines.append(f"   {step['result_latex']}")
    fa = data["final_answer"]
    lines.append(f"answer: {fa['value']} {fa['unit']}   (LaTeX: {fa['latex']})")
    lines.append(f"plausible: {data['plausible']}")
    if verified is not None:
        lines.append(f"data-fidelity verify: {'PASS' if verified else 'FAIL'}")
    return "\n".join(lines)


def _random_split(topic):
    """Pick a random valid ``(given, find)`` split for ``topic`` (as names).

    Keeps the deterministic library untouched: the randomness is an entry-point
    convenience so a bare ``python -m engine`` gives a fresh problem each run. The
    chosen split is echoed in the output, so the run stays reproducible.
    """
    template = load_template(topic)
    given, find = random.choice(template.valid_splits())
    return [s.name for s in given], find.name


def main(argv=None):
    args = _build_parser().parse_args(argv)
    conditions = _parse_conditions(args.condition)

    # Fresh-by-default (unless pinned): random seed if none given, and a random
    # valid split if neither --given nor --find was provided.
    seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    given, find = args.given, args.find
    try:
        if given is None and find is None:
            given, find = _random_split(args.topic)
        data = generate(
            args.topic,
            given=given,
            find=find,
            conditions=conditions or None,
            difficulty=args.difficulty,
            seed=seed,
        )
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:  # unknown topic / variable name
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verified = None
    if args.verify:
        from harness.verify import FidelityError, verify_generic
        try:
            # verify_generic reads the topic's symbols/equations/units/constraints
            # off its own template, so --verify works for every topic (SUVAT and
            # every declarative strand), not just SUVAT.
            verified = verify_generic(
                data, load_template(args.topic), difficulty=args.difficulty
            )
        except FidelityError as exc:
            verified = False
            print(f"verify error: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_render_human(data, verified))

    # Non-zero exit if an explicit --verify failed, so scripts can gate on it.
    return 1 if verified is False else 0


if __name__ == "__main__":
    sys.exit(main())
