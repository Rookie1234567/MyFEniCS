"""Tiny full-space/trace Schur identity oracle.

The oracle is deliberately cell-local: it applies oriented full-space blocks
one cell at a time and accumulates only the requested slab active rows.  It
does not assemble a global uncondensed operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import scipy.sparse as sp


_TINY = np.finfo(float).tiny


def _readonly_array(values: np.ndarray, dtype: np.dtype) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(values, dtype=dtype)).copy()
    array.setflags(write=False)
    return array


def _readonly_csr(values: sp.spmatrix | np.ndarray) -> sp.csr_matrix:
    matrix = sp.csr_matrix(values, dtype=np.complex128, copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    data = np.asarray(matrix.data, dtype=np.complex128).copy()
    indices = np.asarray(matrix.indices).copy()
    indptr = np.asarray(matrix.indptr).copy()
    result = sp.csr_matrix(
        (data, indices, indptr),
        shape=matrix.shape,
    )
    for array in (result.data, result.indices, result.indptr):
        array.setflags(write=False)
    return result


@dataclass(frozen=True)
class FullSpaceSlabBlockRecord:
    """One oriented full-space cell-class block and its supplied Schur block."""

    a_ii: np.ndarray
    a_it: np.ndarray
    a_ti: np.ndarray
    a_tt: np.ndarray
    schur: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "a_ii",
            "a_it",
            "a_ti",
            "a_tt",
            "schur",
        ):
            object.__setattr__(
                self,
                name,
                _readonly_array(getattr(self, name), np.dtype(np.complex128)),
            )


@dataclass(frozen=True)
class FullSpaceSlabCellRecord:
    """A cell reference to a block, its expansion, and active positions.

    ``trace_expansion`` is the local full-trace-by-active-trace matrix ``C``;
    ``active_positions`` locates its columns in the slab vector.  Multiple
    cells may share one ``block`` object.  ``canonical_cell_id`` is the
    partition-independent identity of this cell.
    """

    block: FullSpaceSlabBlockRecord
    canonical_cell_id: int
    trace_expansion: sp.csr_matrix
    active_positions: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_cell_id", int(self.canonical_cell_id))
        object.__setattr__(
            self,
            "trace_expansion",
            _readonly_csr(self.trace_expansion),
        )
        positions = _readonly_array(self.active_positions, np.dtype(np.int64))
        if positions.ndim != 1 or np.any(positions < 0):
            raise ValueError("active positions must be nonnegative and one-dimensional")
        if len(np.unique(positions)) != positions.size:
            raise ValueError("cell active positions must be unique")
        object.__setattr__(self, "active_positions", positions)


def _cell_actions(
    cell: FullSpaceSlabCellRecord,
    vector: np.ndarray,
    recovery: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    positions = cell.active_positions
    expansion = cell.trace_expansion
    if expansion.ndim != 2 or expansion.shape[1] != positions.size:
        raise ValueError("trace expansion columns and active positions disagree")
    trace = expansion @ vector[positions]
    interior = recovery @ trace
    full_trace_action = cell.block.a_ti @ interior + cell.block.a_tt @ trace
    schur_trace_action = cell.block.schur @ trace
    return (
        expansion.conj().T @ full_trace_action,
        expansion.conj().T @ schur_trace_action,
    )


def _apply_cell_stream(
    cells: Sequence[FullSpaceSlabCellRecord],
    vector: np.ndarray,
    *,
    active_size: int,
    trace_shift: np.ndarray | None,
    recovery_by_block: dict[int, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    full_action = np.zeros(active_size, dtype=np.complex128)
    schur_action = np.zeros(active_size, dtype=np.complex128)
    for cell in cells:
        full_local, schur_local = _cell_actions(
            cell,
            vector,
            recovery_by_block[id(cell.block)],
        )
        np.add.at(full_action, cell.active_positions, full_local)
        np.add.at(schur_action, cell.active_positions, schur_local)
    if trace_shift is not None:
        shifted = trace_shift * vector
        full_action += shifted
        schur_action += shifted
    return full_action, schur_action


def measure_fullspace_slab_identity(
    cells: Sequence[FullSpaceSlabCellRecord],
    vectors: Iterable[np.ndarray],
    *,
    active_size: int,
    trace_shift: np.ndarray | None = None,
) -> dict[str, object]:
    """Measure full-space versus Schur actions for fixed active vectors.

    The relative error is ``||full-reference|| / max(||reference||, tiny)``.
    ``trace_shift`` is an active-vector diagonal term and is added identically
    to both actions; it is not interpreted as a full-interior shift.
    """

    if not cells:
        raise ValueError("at least one slab cell is required")
    active_size = int(active_size)
    if active_size <= 0:
        raise ValueError("active size must be positive")
    normalized_vectors = tuple(
        np.asarray(vector, dtype=np.complex128) for vector in vectors
    )
    if not normalized_vectors:
        raise ValueError("at least one active vector is required")
    if any(vector.shape != (active_size,) for vector in normalized_vectors):
        raise ValueError("active vectors must match active_size")
    shift = None
    if trace_shift is not None:
        shift = np.asarray(trace_shift, dtype=np.complex128)
        if shift.shape != (active_size,):
            raise ValueError("trace shift must match active_size")

    recovery_by_block: dict[int, np.ndarray] = {}
    for cell in cells:
        block_id = id(cell.block)
        if block_id not in recovery_by_block:
            recovery_by_block[block_id] = np.linalg.solve(
                cell.block.a_ii,
                -cell.block.a_it,
            )

    first_actions = tuple(
        _apply_cell_stream(
            cells,
            vector,
            active_size=active_size,
            trace_shift=shift,
            recovery_by_block=recovery_by_block,
        )
        for vector in normalized_vectors
    )
    repeated_actions = tuple(
        _apply_cell_stream(
            cells,
            vector,
            active_size=active_size,
            trace_shift=shift,
            recovery_by_block=recovery_by_block,
        )
        for vector in normalized_vectors
    )
    measurements: list[dict[str, object]] = []
    for index, ((full, reference), (full_again, reference_again)) in enumerate(
        zip(first_actions, repeated_actions, strict=True)
    ):
        error = float(
            np.linalg.norm(full - reference)
            / max(float(np.linalg.norm(reference)), _TINY)
        )
        full_repeat_error = float(
            np.linalg.norm(full - full_again)
            / max(float(np.linalg.norm(full)), _TINY)
        )
        reference_repeat_error = float(
            np.linalg.norm(reference - reference_again)
            / max(float(np.linalg.norm(reference)), _TINY)
        )
        finite = bool(
            np.isfinite(normalized_vectors[index]).all()
            and np.isfinite(full).all()
            and np.isfinite(reference).all()
            and np.isfinite(error)
        )
        measurements.append(
            {
                "index": int(index),
                "relative_error": error,
                "full_norm": float(np.linalg.norm(full)),
                "reference_norm": float(np.linalg.norm(reference)),
                "determinism_relative_error": max(
                    full_repeat_error,
                    reference_repeat_error,
                ),
                "deterministic": bool(
                    np.array_equal(full, full_again)
                    and np.array_equal(reference, reference_again)
                ),
                "finite": finite,
            }
        )
    return {
        "cell_count": int(len(cells)),
        "vector_count": int(len(measurements)),
        "trace_shift_applied": trace_shift is not None,
        "vectors": measurements,
        "max_relative_error": max(
            float(item["relative_error"]) for item in measurements
        ),
        "max_determinism_relative_error": max(
            float(item["determinism_relative_error"]) for item in measurements
        ),
        "deterministic": all(bool(item["deterministic"]) for item in measurements),
        "finite": all(bool(item["finite"]) for item in measurements),
    }


__all__ = (
    "FullSpaceSlabBlockRecord",
    "FullSpaceSlabCellRecord",
    "measure_fullspace_slab_identity",
)
