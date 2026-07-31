"""Hash-bound deterministic training-only space-filling folds."""

from __future__ import annotations

import hashlib
import json
from typing import Iterator

import numpy as np


FOLD_SEED = 20260731


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def folds(x: np.ndarray, *, n_splits: int = 5, seed: int = FOLD_SEED
          ) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate deterministic folds with maximin ordering and no validation use."""

    x = np.asarray(x, dtype=np.float64)
    if n_splits < 2 or len(x) < n_splits:
        raise ValueError("invalid fold count")
    remaining = set(range(len(x)))
    first = min(remaining, key=lambda i: tuple(x[i]))
    order = [first]
    remaining.remove(first)
    distance = np.linalg.norm(x - x[first], axis=1)
    while remaining:
        index = max(remaining, key=lambda i: (float(distance[i]), -i))
        order.append(index)
        remaining.remove(index)
        distance = np.minimum(distance, np.linalg.norm(x - x[index], axis=1))
    # A fixed rotation based on the declared seed changes fold labels without
    # changing the maximin point order.
    rotation = int(seed) % n_splits
    test_sets = [np.asarray(order[k::n_splits], dtype=np.int64)
                 for k in range(n_splits)]
    test_sets = test_sets[rotation:] + test_sets[:rotation]
    all_indices = np.arange(len(x), dtype=np.int64)
    return [(np.setdiff1d(all_indices, test, assume_unique=True), test)
            for test in test_sets]


def fold_identity(x: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                  *, seed: int = FOLD_SEED) -> dict[str, object]:
    rows = [{"train": tr.tolist(), "test": te.tolist()} for tr, te in split]
    return {"schema_version": "task003.training-folds.v1", "seed": seed,
            "n_splits": len(split), "folds": rows,
            "fold_sha256": _hash(rows)}

