"""The C4 benchmark runner — see :mod:`benchmarks` for the contract."""

from __future__ import annotations

import argparse
import csv
import os
import sys

from engine import registry
from engine.chain import SANCTIONED_LINKS, generate_chain
from engine.errors import NoCleanInstanceError
from engine.loop import generate
from harness.verify import FidelityError, verify_chain, verify_generic

DIFFICULTIES = ("easy", "medium", "hard")

CSV_FIELDS = [
    "scope", "name", "difficulty", "instances", "ok",
    "fidelity_error", "no_clean_instance", "ok_rate",
]

#: Metrics the report promises that this runner cannot compute by itself.
#: Listed in every output so a partial table never reads as the whole suite.
PENDING_METRICS = [
    ("Data Fidelity (end-to-end)",
     "needs an LLM provider key: compares Thai question_text against sympy_data"),
    ("Schema Adherence",
     "needs both providers configured: first-pass Zod validity per model"),
    ("LLM-as-a-Judge",
     "needs a frontier model key + the 100-question sample"),
    ("TikZ Compilation Rate",
     "needs the web repo's TikZ toolchain; engine emits diagram specs only"),
    ("Coaching Effectiveness (classification)",
     "lives in the web repo: npx vitest run features/coach/classification-benchmark.test.ts"),
    ("Coaching Effectiveness (student pilot)",
     "human pilot (>= 5 students); log solved-after-hint rate"),
]


def _stat_row(scope, name, difficulty, ok, fidelity_error, no_clean):
    instances = ok + fidelity_error + no_clean
    return {
        "scope": scope,
        "name": name,
        "difficulty": difficulty,
        "instances": instances,
        "ok": ok,
        "fidelity_error": fidelity_error,
        "no_clean_instance": no_clean,
        "ok_rate": f"{ok / instances:.4f}" if instances else "n/a",
    }


def fidelity_sweep(topics, difficulties, seeds):
    """Per-topic Data-Fidelity-at-source stats + diagram coverage.

    Returns ``(rows, diagram_topics)`` where ``rows`` has one stat row per
    (topic, difficulty) plus a TOTAL row, and ``diagram_topics`` maps topic ->
    bool (whether its instances carry the engine-owned ``diagram`` payload).
    """
    rows = []
    diagram_topics = {}
    totals = {"ok": 0, "fidelity_error": 0, "no_clean_instance": 0}
    for topic in topics:
        template = registry.load_template(topic)
        saw_diagram = False
        for difficulty in difficulties:
            ok = fidelity_error = no_clean = 0
            for given, find in template.valid_splits():
                for seed in range(seeds):
                    try:
                        data = generate(topic, given=given, find=find,
                                        difficulty=difficulty, seed=seed)
                    except NoCleanInstanceError:
                        no_clean += 1
                        continue
                    saw_diagram = saw_diagram or "diagram" in data
                    try:
                        verify_generic(data, template, difficulty)
                        ok += 1
                    except FidelityError:
                        fidelity_error += 1
            rows.append(_stat_row("topic", topic, difficulty,
                                  ok, fidelity_error, no_clean))
            totals["ok"] += ok
            totals["fidelity_error"] += fidelity_error
            totals["no_clean_instance"] += no_clean
        diagram_topics[topic] = saw_diagram
        print(f"{topic}: done", file=sys.stderr)
    rows.append(_stat_row("topic", "TOTAL", "all", totals["ok"],
                          totals["fidelity_error"], totals["no_clean_instance"]))
    return rows, diagram_topics


def _split_with_find(template, find_name):
    """A valid split of ``template`` whose find is ``find_name``."""
    for given, find in template.valid_splits():
        if find.name == find_name:
            return [s.name for s in given], find.name
    raise LookupError(f"{template.topic} has no valid split finding {find_name!r}")


def _split_receiving(template, receive_name):
    """A valid split of ``template`` whose givens include ``receive_name``."""
    for given, find in template.valid_splits():
        if any(s.name == receive_name for s in given):
            return [s.name for s in given], find.name
    raise LookupError(f"{template.topic} has no valid split given {receive_name!r}")


def chain_sweep(difficulties, seeds):
    """Every sanctioned link, generated and re-verified end to end."""
    rows = []
    totals = {"ok": 0, "fidelity_error": 0, "no_clean_instance": 0}
    for (from_topic, from_find, to_topic, to_receive) in SANCTIONED_LINKS:
        from_given, _ = _split_with_find(
            registry.load_template(from_topic), from_find)
        to_given, to_find = _split_receiving(
            registry.load_template(to_topic), to_receive)
        parts = [
            {"topic": from_topic, "given": from_given, "find": from_find},
            {"topic": to_topic, "given": to_given, "find": to_find,
             "receive": to_receive},
        ]
        name = f"{from_topic}.{from_find} -> {to_topic}.{to_receive}"
        for difficulty in difficulties:
            ok = fidelity_error = no_clean = 0
            for seed in range(seeds):
                try:
                    data = generate_chain(parts, difficulty=difficulty, seed=seed)
                except NoCleanInstanceError:
                    no_clean += 1
                    continue
                try:
                    verify_chain(data, difficulty=difficulty)
                    ok += 1
                except FidelityError:
                    fidelity_error += 1
            rows.append(_stat_row("chain", name, difficulty,
                                  ok, fidelity_error, no_clean))
            totals["ok"] += ok
            totals["fidelity_error"] += fidelity_error
            totals["no_clean_instance"] += no_clean
        print(f"chain {name}: done", file=sys.stderr)
    rows.append(_stat_row("chain", "TOTAL", "all", totals["ok"],
                          totals["fidelity_error"], totals["no_clean_instance"]))
    return rows


def _markdown_table(rows, name_header):
    lines = [
        f"| {name_header} | difficulty | instances | ok | fidelity_error | no_clean_instance | ok rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['name']} | {row['difficulty']} | {row['instances']} | "
            f"{row['ok']} | {row['fidelity_error']} | "
            f"{row['no_clean_instance']} | {row['ok_rate']} |"
        )
    return "\n".join(lines)


def render_markdown(topic_rows, chain_rows, diagram_topics, config):
    """The report-ready markdown. Deterministic: no timestamps."""
    diagram_yes = sorted(t for t, has in diagram_topics.items() if has)
    diagram_no = sorted(t for t, has in diagram_topics.items() if not has)
    parts = [
        "# Engine benchmark results (DEVELOPMENT_PLAN C4)",
        "",
        f"Configuration: topics={config['topics']}, "
        f"difficulties={','.join(config['difficulties'])}, "
        f"seeds per (topic, split, difficulty)={config['seeds']}. "
        "Deterministic — rerunning this command reproduces this file exactly.",
        "",
        "## Data Fidelity at source",
        "",
        "Every instance is generated by the symbolic engine and re-checked by the",
        "Data Fidelity harness (`verify_generic`, the (a)-(e) battery). `ok rate`",
        "is the fraction of generated instances the engine itself vouches for —",
        "the source-side bound on the report's Data Fidelity metric.",
        "",
        _markdown_table(topic_rows, "topic"),
        "",
        "## Chain fidelity (sanctioned links)",
        "",
        "Each sanctioned composition (`engine/chain.py:SANCTIONED_LINKS`) is",
        "generated as a two-part chained problem and re-verified end to end",
        "(`verify_chain`: per-part battery + exact link values).",
        "",
        _markdown_table(chain_rows, "link"),
        "",
        "## Engine-owned diagram coverage",
        "",
        f"- topics emitting a `diagram` payload: {', '.join(diagram_yes) or 'none'}",
        f"- topics without one: {', '.join(diagram_no) or 'none'}",
        "",
        "## Not run by this command",
        "",
        "The following C4 metrics need resources this repository does not have;",
        "they are pending, not passing:",
        "",
    ]
    for name, needs in PENDING_METRICS:
        parts.append(f"- **{name}** — {needs}")
    parts.append("")
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks",
        description="Engine-side C4 benchmarks: fidelity, chains, diagrams.",
    )
    parser.add_argument("command", nargs="?", default="run", choices=["run"],
                        help="the only subcommand (default: run)")
    parser.add_argument("--topics",
                        help="comma-separated topics (default: all registered)")
    parser.add_argument("--difficulties", default=",".join(DIFFICULTIES),
                        help="comma-separated difficulty bands")
    parser.add_argument("--seeds", type=int, default=5,
                        help="seeds per (topic, split, difficulty); default 5")
    parser.add_argument("--out-dir", default="benchmarks/results",
                        help="where the .md and .csv tables are written")
    args = parser.parse_args(argv)

    topics = args.topics.split(",") if args.topics else registry.topics()
    difficulties = tuple(args.difficulties.split(","))

    topic_rows, diagram_topics = fidelity_sweep(topics, difficulties, args.seeds)
    chain_rows = chain_sweep(difficulties, args.seeds)

    os.makedirs(args.out_dir, exist_ok=True)
    config = {"topics": ",".join(topics),
              "difficulties": difficulties, "seeds": args.seeds}
    md_path = os.path.join(args.out_dir, "engine-benchmarks.md")
    with open(md_path, "w") as fh:
        fh.write(render_markdown(topic_rows, chain_rows, diagram_topics, config))
    csv_path = os.path.join(args.out_dir, "engine-benchmarks.csv")
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(topic_rows + chain_rows)

    total = next(r for r in topic_rows if r["name"] == "TOTAL")
    chain_total = next(r for r in chain_rows if r["name"] == "TOTAL")
    print(f"wrote {md_path} and {csv_path}")
    print(f"topics: {total['ok']}/{total['instances']} ok "
          f"(rate {total['ok_rate']}); "
          f"chains: {chain_total['ok']}/{chain_total['instances']} ok "
          f"(rate {chain_total['ok_rate']})")
    # A no_clean_instance is the engine's gate refusing to ship — expected for
    # some hard splits and visible in the table. Only a fidelity_error (the
    # engine emitted something its own harness rejects) fails the run.
    failures = int(total["fidelity_error"]) + int(chain_total["fidelity_error"])
    return 1 if failures else 0
