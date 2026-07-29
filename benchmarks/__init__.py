"""Benchmark suite (DEVELOPMENT_PLAN C4): ``python -m benchmarks run``.

One command produces the engine-side benchmark table — markdown + CSV under
``benchmarks/results/`` — that goes verbatim into the NSC report:

* **Data Fidelity at source** — every registered topic, every valid split,
  seeded batches through :func:`engine.loop.generate` and the
  :func:`harness.verify.verify_generic` battery.
* **Chain fidelity** — every sanctioned link (``engine.chain.SANCTIONED_LINKS``)
  generated end to end and re-verified with :func:`harness.verify.verify_chain`.
* **Diagram coverage** — which topics emit the engine-owned ``diagram`` payload.

The run is deterministic: fixed seed ranges, no timestamps in the output, so
running the same command twice yields byte-identical tables (the C4 exit-gate
reproducibility check). Metrics that need an LLM provider or the TikZ
toolchain (end-to-end fidelity over Thai text, Schema Adherence, LLM-as-a-Judge,
TikZ compilation rate, the coaching student pilot) are listed in the output as
**not run** with what each needs — never silently omitted.

How to test::

    python -m benchmarks run --topics suvat --seeds 2   # quick smoke
    python -m benchmarks run                            # the full table
    python -m benchmarks run && python -m benchmarks run && \
        git diff --exit-code benchmarks/results/         # reproducibility
"""
