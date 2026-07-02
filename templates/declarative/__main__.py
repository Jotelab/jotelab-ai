"""CLI: ``python -m templates.declarative path/to/template.json``.

Runs the five-stage validation gate on a declarative template and prints a
per-stage PASS/FAIL report. Exit 0 only if every stage passes; exit 1 on a
validation failure; exit 2 on a usage error.
"""

from __future__ import annotations

import json
import sys

from templates.declarative.gate import validate_template


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m templates.declarative <template.json>", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        doc = json.load(fh)
    report = validate_template(doc)
    for s in report.stages:
        mark = "PASS" if s.passed else "FAIL"
        line = f"stage {s.number} [{s.name}]: {mark}"
        if not s.passed:
            line += f"  -- {s.reason}"
        print(line)
    print(f"\noverall: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
