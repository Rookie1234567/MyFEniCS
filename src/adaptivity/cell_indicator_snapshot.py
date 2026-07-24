"""Portable full-cell indicator snapshots for Task035/Task035b research."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
from mpi4py import MPI


def build_cell_indicator_snapshot(
    comm: MPI.Intracomm,
    canonical_cell_ids: np.ndarray,
    indicator_values: np.ndarray,
    *,
    indicator_name: str,
    mesh_geometry_sha256: str,
) -> dict[str, Any]:
    """Gather one small research mesh's complete indicator vector.

    The returned arrays are sorted by partition-independent canonical cell ID
    and are identical on every rank.  Task035b's p4/p5/p6 base mesh has only
    252 cells, so an inline record is both reviewable and much smaller than a
    field or matrix artifact.
    """

    local_ids = np.asarray(canonical_cell_ids, dtype=np.int64)
    local_values = np.asarray(indicator_values, dtype=np.float64)
    if (
        local_ids.ndim != 1
        or local_values.shape != local_ids.shape
        or not np.all(np.isfinite(local_values))
        or np.any(local_values < 0.0)
    ):
        raise ValueError(
            "cell indicator snapshot requires aligned finite nonnegative arrays"
        )
    packets = comm.allgather((local_ids, local_values))
    all_ids = np.concatenate([packet[0] for packet in packets])
    all_values = np.concatenate([packet[1] for packet in packets])
    if len(np.unique(all_ids)) != len(all_ids):
        raise ValueError("canonical cell IDs must be globally unique")
    order = np.argsort(all_ids, kind="mergesort")
    ordered_ids = all_ids[order]
    ordered_values = all_values[order]
    expected_ids = np.arange(len(ordered_ids), dtype=np.int64)
    if not np.array_equal(ordered_ids, expected_ids):
        raise ValueError(
            "canonical cell IDs must be contiguous from zero through cell_count-1"
        )
    digest = hashlib.sha256()
    digest.update(ordered_ids.astype("<i8", copy=False).tobytes())
    digest.update(ordered_values.astype("<f8", copy=False).tobytes())
    total = float(np.sum(ordered_values))
    return {
        "schema_version": "task035.cell-indicator-snapshot.v1",
        "indicator_name": str(indicator_name),
        "storage": "inline_complete_vector",
        "cell_count": int(len(ordered_ids)),
        "canonical_cell_ids": ordered_ids.tolist(),
        "indicator_values": ordered_values.tolist(),
        "indicator_sum": total,
        "indicator_max": float(np.max(ordered_values, initial=0.0)),
        "indicator_l2_norm": float(np.linalg.norm(ordered_values)),
        "canonical_ids_and_values_sha256": digest.hexdigest(),
        "mesh_geometry_sha256": str(mesh_geometry_sha256),
        "partition_independent": True,
    }


__all__ = ["build_cell_indicator_snapshot"]
