"""Pure algebraic adapters for a condensed trace residual and h10 partitions.

The helpers here do not assemble or solve a PDE.  They encode the coordinate
maps needed by a later Stage4 solver port:

* ``expansion_by_original`` stores rows of the primal trace expansion ``E``.
* A reduced trace dual ``r`` is lifted by placing each owned independent entry
  on its original master row.  This gives ``E.conj().T @ lift(r) == r`` after
  owner contributions are assembled.  Slave and interior rows receive zero.
* Full trace duals are restricted with the Hermitian transpose, including
  complex Floquet/MPC phases.

The input map is the existing ``TraceConstraintMap`` duck type from
``hcurl_assembly_time_condensation``; keeping this module NumPy-only makes the
coordinate identities easy to test without PETSc or DOLFINx.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np


def balanced_partition_bounds(layer_count: int, partition_count: int) -> tuple[int, ...]:
    """Return deterministic contiguous integer cuts with widths differing by ≤1.

    The floor rule matches the current grid's existing z planes.  In particular,
    14 layers and four partitions produce ``(0, 3, 7, 10, 14)``; no mesh plane
    or cell is introduced or moved.
    """
    if type(layer_count) is not int or layer_count < 1:
        raise ValueError("layer_count must be a positive integer")
    if type(partition_count) is not int or not 1 <= partition_count <= layer_count:
        raise ValueError("partition_count must be an integer in [1, layer_count]")
    bounds = tuple((index * layer_count) // partition_count
                   for index in range(partition_count + 1))
    widths = np.diff(np.asarray(bounds, dtype=np.int64))
    if np.any(widths < 1) or int(widths.max() - widths.min()) > 1:
        raise RuntimeError("balanced partition construction invariant failed")
    return bounds


def _validated_map(trace_constraints: Any) -> tuple[int, int, dict[int, int], dict[int, tuple[np.ndarray, np.ndarray]]]:
    """Normalize and validate the public trace-map fields used by these helpers."""
    active_rows = int(trace_constraints.active_rows)
    full_trace_rows = int(trace_constraints.full_trace_rows)
    if active_rows < 0 or full_trace_rows < active_rows:
        raise ValueError("trace-map row counts are inconsistent")

    raw_mapping = trace_constraints.original_to_active
    if not isinstance(raw_mapping, Mapping):
        raise TypeError("original_to_active must be a mapping")
    original_to_active = {int(original): int(active)
                          for original, active in raw_mapping.items()}
    if (len(set(original_to_active.values())) != len(original_to_active)
            or set(original_to_active.values()) != set(range(active_rows))):
        raise ValueError("original_to_active must bijectively cover all active rows")

    raw_expansion = trace_constraints.expansion_by_original
    if not isinstance(raw_expansion, Mapping) or len(raw_expansion) != full_trace_rows:
        raise ValueError("expansion_by_original must contain every full trace row")
    expansion: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for original, raw_entry in raw_expansion.items():
        row = int(original)
        if row < 0 or not isinstance(raw_entry, tuple) or len(raw_entry) != 2:
            raise ValueError("invalid trace expansion row")
        indices = np.asarray(raw_entry[0], dtype=np.int64)
        coefficients = np.asarray(raw_entry[1], dtype=np.complex128)
        if (indices.ndim != 1 or coefficients.ndim != 1
                or indices.shape != coefficients.shape or len(indices) == 0
                or np.any(indices < 0) or np.any(indices >= active_rows)
                or not np.all(np.isfinite(coefficients))):
            raise ValueError(f"invalid expansion data for original trace row {row}")
        expansion[row] = (indices, coefficients)

    for original, active in original_to_active.items():
        entry = expansion.get(original)
        if entry is None:
            raise ValueError(f"active original row {original} is absent from expansion")
        indices, coefficients = entry
        if (len(indices) != 1 or int(indices[0]) != active
                or complex(coefficients[0]) != 1.0 + 0.0j):
            raise ValueError("active master rows must have exact identity expansion")
    return active_rows, full_trace_rows, original_to_active, expansion


def _active_originals(trace_constraints: Any, original_to_active: dict[int, int],
                      *, owned_only: bool) -> np.ndarray:
    if owned_only:
        originals = np.asarray(trace_constraints.owned_active_original_dofs,
                                dtype=np.int64)
        if originals.ndim != 1:
            raise ValueError("owned_active_original_dofs must be one-dimensional")
        active_ids = [original_to_active.get(int(original)) for original in originals]
        if any(active is None for active in active_ids):
            raise ValueError("owned active original row is absent from global map")
        if len(set(int(active) for active in active_ids)) != len(active_ids):
            raise ValueError("owned active rows contain a duplicate")
        return originals
    by_active = {active: original for original, active in original_to_active.items()}
    return np.asarray([by_active[index] for index in range(len(by_active))],
                      dtype=np.int64)


def inject_trace_dual(
    trace_constraints: Any,
    active_dual: np.ndarray,
    full_rows: int,
    *,
    owned_only: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Inject active trace dual entries on independent original master rows.

    Returns ``(global_original_row_ids, values)`` rather than a dense full vector,
    so an MPI caller can add each rank's owned contributions to its PETSc vector.
    For a serial map, ``E.conj().T @ lift == active_dual``.  Slave, cell-interior,
    and non-trace rows are intentionally absent and therefore remain zero.

    ``active_dual`` is in global active-row numbering.  With ``owned_only=True``
    (the default), the returned rows belong to this rank according to the
    existing ``owned_active_original_dofs`` field; the caller performs the
    normal additive vector assembly across ranks.
    """
    active_rows, _full_trace_rows, original_to_active, _expansion = _validated_map(
        trace_constraints)
    residual = np.asarray(active_dual, dtype=np.complex128)
    if residual.ndim != 1 or residual.size != active_rows:
        raise ValueError("active_dual must have one value per global active row")
    if not np.all(np.isfinite(residual)):
        raise ValueError("active_dual contains non-finite values")
    originals = _active_originals(trace_constraints, original_to_active,
                                  owned_only=owned_only)
    if np.any(originals < 0) or np.any(originals >= full_rows):
        raise ValueError("active original row is outside the full FE vector")
    active_ids = np.fromiter((original_to_active[int(row)] for row in originals),
                             dtype=np.int64, count=len(originals))
    return originals.copy(), residual[active_ids].copy()


def restrict_trace_dual(
    trace_constraints: Any,
    full_dual: np.ndarray,
    full_rows: int,
) -> np.ndarray:
    """Apply the exact Hermitian trace restriction ``E.conj().T @ full_dual``.

    The input may also contain nonzero storage/interior entries.  Only rows in
    ``expansion_by_original`` contribute; complex MPC coefficients are conjugated
    as required by the dual map.
    """
    active_rows, _full_trace_rows, _original_to_active, expansion = _validated_map(
        trace_constraints)
    dual = np.asarray(full_dual, dtype=np.complex128)
    if dual.ndim != 1 or dual.size != full_rows:
        raise ValueError("full_dual must match the full FE row count")
    if not np.all(np.isfinite(dual)):
        raise ValueError("full_dual contains non-finite values")
    reduced = np.zeros(active_rows, dtype=np.complex128)
    for original, (indices, coefficients) in expansion.items():
        if original >= full_rows:
            raise ValueError("trace original row is outside the full FE vector")
        np.add.at(reduced, indices, np.conjugate(coefficients) * dual[original])
    return reduced


def restrict_trace_primal(
    trace_constraints: Any,
    full_primal: np.ndarray,
    full_rows: int,
    *,
    owned_only: bool = False,
) -> np.ndarray:
    """Select independent master coefficients from a full primal FE vector."""
    _active_rows, _full_trace_rows, original_to_active, _expansion = _validated_map(
        trace_constraints)
    primal = np.asarray(full_primal, dtype=np.complex128)
    if primal.ndim != 1 or primal.size != full_rows:
        raise ValueError("full_primal must match the full FE row count")
    if not np.all(np.isfinite(primal)):
        raise ValueError("full_primal contains non-finite values")
    originals = _active_originals(trace_constraints, original_to_active,
                                  owned_only=owned_only)
    if np.any(originals < 0) or np.any(originals >= full_rows):
        raise ValueError("active original row is outside the full FE vector")
    if owned_only:
        return primal[originals].copy()
    result = np.empty(len(original_to_active), dtype=np.complex128)
    for original in originals:
        result[original_to_active[int(original)]] = primal[int(original)]
    return result


def expand_trace_primal(
    trace_constraints: Any,
    active_primal: np.ndarray,
    full_rows: int,
) -> np.ndarray:
    """Expand active primal coefficients to trace rows; leave storage rows zero."""
    active_rows, _full_trace_rows, _original_to_active, expansion = _validated_map(
        trace_constraints)
    primal = np.asarray(active_primal, dtype=np.complex128)
    if primal.ndim != 1 or primal.size != active_rows:
        raise ValueError("active_primal must have one value per global active row")
    if not np.all(np.isfinite(primal)):
        raise ValueError("active_primal contains non-finite values")
    full = np.zeros(full_rows, dtype=np.complex128)
    for original, (indices, coefficients) in expansion.items():
        if original >= full_rows:
            raise ValueError("trace original row is outside the full FE vector")
        full[original] = np.dot(coefficients, primal[indices])
    return full
