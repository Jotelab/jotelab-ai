"""Seed-batch definitions for the Data Fidelity metric (build guide §10, §11).

A batch is a list of generation requests (topic + given/find split + difficulty +
seed). Running every instance in a batch through :func:`harness.verify.verify` and
getting 100% is **Gate 5** — the milestone that unblocks the AI and web tracks
(build guide §12).
"""

from __future__ import annotations

from templates.suvat import a, s, t, u, v

# Every valid single-equation SUVAT split (each leaves exactly one variable
# unused), exercised across a spread of seeds.
_SUVAT_SPLITS = [
    ((u, a, t), v),   # E1, excludes s — the spec §8 worked example
    ((u, t, a), s),   # E2, excludes v
    ((u, v, a), s),   # E3, excludes t
    ((u, v, t), a),   # E4, excludes a
    ((v, a, t), s),   # E5, excludes u
    ((u, a, t), s),   # E2, find s
    ((u, a, t), v),   # repeat with different seeds
]


def suvat_batch(n_seeds=12):
    """A SUVAT seed batch: every valid split across ``n_seeds`` seeds (easy)."""
    batch = []
    for split_idx, (given, find) in enumerate(_SUVAT_SPLITS):
        for k in range(n_seeds):
            seed = 80421 + 1000 * split_idx + k
            batch.append(
                {
                    "topic": "suvat",
                    "given": given,
                    "find": find,
                    "difficulty": "easy",
                    "seed": seed,
                }
            )
    return batch


# The canonical spec §8 worked example, called out for direct testing.
WORKED_EXAMPLE = {
    "topic": "suvat",
    "given": (u, a, t),
    "find": v,
    "difficulty": "easy",
    "seed": 80421,
}
