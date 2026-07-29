"""Bulk CSV export of generated problem instances: ``python -m harness.export_csv``.

Sweeps every registered topic, every valid given/find split, every difficulty
band, and a range of seeds; runs each instance through :func:`engine.loop.generate`
and the Data-Fidelity harness (:func:`harness.verify.verify_generic`); and writes
one CSV row per instance. A thin orchestration layer — no new engine logic here.

Each row records the full instance (topic, split, difficulty, seed, given values
with units, the solved answer in display and exact form, the policy applied) plus
a ``status`` column: ``ok`` for a verified instance, ``fidelity_error: ...`` if
the harness rejected it, or ``no_clean_instance`` if the bounded loop gave up.
Rows are deterministic: the same seed range always yields the same CSV.

How to test::

    # Default sweep (all topics, all splits, easy/medium/hard, 10 seeds each)
    python -m harness.export_csv --out dataset.csv

    # Quick smoke run: one topic, one difficulty, 2 seeds
    python -m harness.export_csv --topics suvat --difficulties easy --seeds 2 --out /tmp/smoke.csv

    # Every row of a default sweep should be status=ok (Gate-5 spirit):
    python - <<'EOF'
    import csv
    rows = list(csv.DictReader(open("dataset.csv")))
    bad = [r for r in rows if r["status"] != "ok"]
    print(f"{len(rows)} rows, {len(bad)} not ok")
    EOF
"""

from __future__ import annotations

import argparse
import csv
import sys

from engine import registry
from engine.errors import NoCleanInstanceError
from engine.loop import generate
from harness.verify import FidelityError, verify_generic

DIFFICULTIES = ("easy", "medium", "hard")

FIELDS = [
    "topic", "difficulty", "seed", "given_symbols", "find_symbol",
    "given_values", "answer_value", "answer_exact", "answer_unit",
    "policy_applied", "status",
]


def _row(topic, difficulty, seed, given, find, data, status):
    """One CSV row. ``data`` is the sympy_data dict, or None on generation failure."""
    row = {
        "topic": topic,
        "difficulty": difficulty,
        "seed": seed,
        "given_symbols": ",".join(sorted(s.name for s in given)),
        "find_symbol": find.name,
        "status": status,
    }
    if data is not None:
        row["given_values"] = " | ".join(
            f"{g['symbol']}={g['value']} {g['unit']}" for g in data["given"]
        )
        row["answer_value"] = data["final_answer"]["value"]
        row["answer_exact"] = data["final_answer"]["exact"]
        row["answer_unit"] = data["final_answer"]["unit"]
        row["policy_applied"] = data["policy_applied"]
    return row


def export(out, topics=None, difficulties=DIFFICULTIES, seeds=10, verify=True):
    """Write the sweep to ``out``; return (total_rows, not_ok_rows)."""
    topics = topics or registry.topics()
    total = not_ok = 0
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for topic in topics:
            template = registry.load_template(topic)
            for given, find in template.valid_splits():
                for difficulty in difficulties:
                    for seed in range(seeds):
                        try:
                            data = generate(topic, given=given, find=find,
                                            difficulty=difficulty, seed=seed)
                            status = "ok"
                            if verify:
                                try:
                                    verify_generic(data, template, difficulty)
                                except FidelityError as err:
                                    status = f"fidelity_error: {err}"
                        except NoCleanInstanceError:
                            data, status = None, "no_clean_instance"
                        writer.writerow(_row(topic, difficulty, seed,
                                             given, find, data, status))
                        total += 1
                        not_ok += status != "ok"
            print(f"{topic}: done", file=sys.stderr)
    return total, not_ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export generated problem instances for every topic to CSV."
    )
    parser.add_argument("--out", default="dataset.csv", help="output CSV path")
    parser.add_argument("--topics", help="comma-separated topics (default: all registered)")
    parser.add_argument("--difficulties", default=",".join(DIFFICULTIES),
                        help="comma-separated difficulty bands")
    parser.add_argument("--seeds", type=int, default=10,
                        help="seeds per (topic, split, difficulty)")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip the Data-Fidelity re-check (faster)")
    args = parser.parse_args(argv)

    topics = args.topics.split(",") if args.topics else None
    total, not_ok = export(args.out, topics=topics,
                           difficulties=tuple(args.difficulties.split(",")),
                           seeds=args.seeds, verify=not args.no_verify)
    print(f"wrote {total} rows to {args.out} ({not_ok} not ok)")
    return 1 if not_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
