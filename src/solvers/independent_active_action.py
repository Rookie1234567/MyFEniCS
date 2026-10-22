"""Small numerical helpers for residuals in constrained active test spaces."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def project_trace_dual_blocks(
    full_trace_dual: np.ndarray,
    independent_trace_rows: int,
    blocks: Iterable[Any],
) -> np.ndarray:
    """Accumulate selected entity-block contributions to ``C^H r``.

    ``blocks`` must contain each full trace entity exactly once across the
    calling communicator. The caller handles MPI reduction when blocks are
    distributed by work owner.
    """

    full = np.asarray(full_trace_dual, dtype=np.complex128)
    independent_count = int(independent_trace_rows)
    if full.ndim != 1 or not np.all(np.isfinite(full)):
        raise ValueError("full trace dual must be a finite one-dimensional vector")
    if independent_count < 0:
        raise ValueError("independent trace row count must be non-negative")
    projected = np.zeros(independent_count, dtype=np.complex128)
    for block in blocks:
        full_rows = np.asarray(block.full_rows, dtype=np.int64)
        independent_rows = np.asarray(block.independent_rows, dtype=np.int64)
        expansion = np.asarray(
            block.full_from_independent,
            dtype=np.complex128,
        )
        if (
            full_rows.ndim != 1
            or independent_rows.ndim != 1
            or expansion.shape != (len(full_rows), len(independent_rows))
            or len(full_rows) == 0
            or len(independent_rows) == 0
            or np.any(full_rows < 0)
            or np.any(full_rows >= len(full))
            or np.any(independent_rows < 0)
            or np.any(independent_rows >= independent_count)
            or not np.all(np.isfinite(expansion))
        ):
            raise ValueError("trace dual block has invalid rows or expansion")
        local = expansion.conj().T @ full[full_rows]
        np.add.at(projected, independent_rows, local)
    return projected


def action_group_metrics(values: np.ndarray) -> dict[str, Any]:
    """Return unweighted raw dual-vector norms without a Gram transformation."""

    vector = np.asarray(values, dtype=np.complex128)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        raise ValueError("residual group must be a finite one-dimensional vector")
    return {
        "row_count": int(vector.size),
        "raw_l2_norm": float(np.linalg.norm(vector)),
        "raw_max_abs": float(np.max(np.abs(vector), initial=0.0)),
    }
