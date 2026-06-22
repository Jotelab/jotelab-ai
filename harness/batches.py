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

# Gate 5 must hold across *every* difficulty band, not just `easy` (fix F3). The
# `medium`/`hard` bands exercise fractional and non-positive clean answers, which
# is exactly where the lossy-display bug (F1) and the difficulty-blind oracle (F2)
# used to hide.
_DIFFICULTIES = ("easy", "medium", "hard")


def suvat_batch(n_seeds=12, difficulties=_DIFFICULTIES):
    """A SUVAT seed batch: every valid split across ``n_seeds`` seeds, per band.

    Spans ``difficulties`` (all three by default) so the Data Fidelity gate proves
    100% on the fractional/negative-answer paths too, not only the integer `easy`
    path (fix F3).
    """
    batch = []
    for diff_idx, difficulty in enumerate(difficulties):
        for split_idx, (given, find) in enumerate(_SUVAT_SPLITS):
            for k in range(n_seeds):
                seed = 80421 + 100_000 * diff_idx + 1000 * split_idx + k
                batch.append(
                    {
                        "topic": "suvat",
                        "given": given,
                        "find": find,
                        "difficulty": difficulty,
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
