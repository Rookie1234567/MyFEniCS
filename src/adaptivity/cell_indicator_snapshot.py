"""Portable full-cell indicator snapshots for Task035/Task035b research."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np
from mpi4py import MPI


def _collective_local_validation(
    comm: MPI.Intracomm,
    local_error: str | None,
    *,
    context: str,
) -> None:
    errors = comm.allgather(local_error)
    failures = [
        f"rank {rank}: {error}"
        for rank, error in enumerate(errors)
        if error is not None
    ]
    if failures:
        raise ValueError(f"{context}: " + "; ".join(failures))


def validate_cell_indicator_snapshot(
    snapshot: dict[str, Any],
    *,
    expected_mesh_geometry_sha256: str | None = None,
    expected_cell_count: int | None = None,
) -> dict[str, bool]:
    """Recompute the portable structural and content checks for a snapshot."""

    ids = np.asarray(snapshot.get("canonical_cell_ids"), dtype=np.int64)
    values = np.asarray(snapshot.get("indicator_values"), dtype=np.float64)
    cell_count = int(snapshot.get("cell_count", -1))
    checks = {
        "schema": (
            snapshot.get("schema_version")
            == "task035.cell-indicator-snapshot.v1"
        ),
        "inline_complete_vector": (
            snapshot.get("storage") == "inline_complete_vector"
        ),
        "one_dimensional_aligned_arrays": (
            ids.ndim == 1 and values.shape == ids.shape
        ),
        "cell_count": (
            cell_count == len(ids)
            and (
                expected_cell_count is None
                or cell_count == int(expected_cell_count)
            )
        ),
        "canonical_ids_contiguous": (
            ids.ndim == 1
            and np.array_equal(ids, np.arange(len(ids), dtype=np.int64))
        ),
        "finite_nonnegative_values": (
            values.ndim == 1
            and bool(np.all(np.isfinite(values)))
            and bool(np.all(values >= 0.0))
        ),
        "mesh_geometry_identity": (
            expected_mesh_geometry_sha256 is None
            or snapshot.get("mesh_geometry_sha256")
            == expected_mesh_geometry_sha256
        ),
    }
    if all(
        checks[name]
        for name in (
            "one_dimensional_aligned_arrays",
            "finite_nonnegative_values",
        )
    ):
        digest = hashlib.sha256()
        digest.update(ids.astype("<i8", copy=False).tobytes())
        digest.update(values.astype("<f8", copy=False).tobytes())
        total = float(np.sum(values))
        maximum = float(np.max(values, initial=0.0))
        norm = float(np.linalg.norm(values))
        scale = max(abs(total), abs(maximum), abs(norm), 1.0)
        absolute_tolerance = 64.0 * np.finfo(np.float64).eps * scale
        checks.update(
            {
                "content_hash": (
                    snapshot.get("canonical_ids_and_values_sha256")
                    == digest.hexdigest()
                ),
                "indicator_sum": math.isclose(
                    float(snapshot.get("indicator_sum", math.nan)),
                    total,
                    rel_tol=1.0e-13,
                    abs_tol=absolute_tolerance,
                ),
                "indicator_max": math.isclose(
                    float(snapshot.get("indicator_max", math.nan)),
                    maximum,
                    rel_tol=1.0e-13,
                    abs_tol=absolute_tolerance,
                ),
                "indicator_l2_norm": math.isclose(
                    float(snapshot.get("indicator_l2_norm", math.nan)),
                    norm,
                    rel_tol=1.0e-13,
                    abs_tol=absolute_tolerance,
                ),
            }
        )
    else:
        checks.update(
            {
                "content_hash": False,
                "indicator_sum": False,
                "indicator_max": False,
                "indicator_l2_norm": False,
            }
        )
    return checks


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
    local_error = None
    if local_ids.ndim != 1 or local_values.shape != local_ids.shape:
        local_error = "indicator arrays are not one-dimensional and aligned"
    elif not np.all(np.isfinite(local_values)):
        local_error = "indicator values are not finite"
    elif np.any(local_values < 0.0):
        local_error = "indicator values are negative"
    _collective_local_validation(
        comm,
        local_error,
        context="cell indicator snapshot local validation failed",
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
        "partition_independence_scope": (
            "canonical_cell_id_ordering_only; floating values are not "
            "claimed byte-identical across MPI partition counts"
        ),
        "floating_values_bitwise_mpi_invariant": False,
    }


__all__ = [
    "build_cell_indicator_snapshot",
    "validate_cell_indicator_snapshot",
]
