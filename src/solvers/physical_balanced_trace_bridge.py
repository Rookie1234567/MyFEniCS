"""Small full-p6/active-trace bridges for the reviewed BAL_H path.

``J`` extracts the locally owned active trace entries from a reconstructed
full-space solution.  ``J^H`` injects an active residual into a
caller-provided full-space vector and deliberately leaves every eliminated
interior entry zero.
The latter is an algebraic RHS injection; it does not recover a nonzero
interior field.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import copy_full_solution_to_active_trace


def extract_full_p6_to_active_trace(
    condensed: Any,
    full_solution: PETSc.Vec | Any,
) -> PETSc.Vec:
    """Apply ``J`` using the existing owned active-trace extractor."""

    return copy_full_solution_to_active_trace(condensed, full_solution)


def inject_active_residual_to_full_p6(
    condensed: Any,
    active_residual: PETSc.Vec,
    full_rhs: PETSc.Vec | Any,
) -> PETSc.Vec:
    """Apply ``J^H`` by locally injecting active rows into a full p6 RHS.

    ``full_rhs`` is caller-owned storage with the full p6 PETSc layout.  Its
    local entries are zeroed first, then the locally owned active original
    rows are inserted.  No cell-interior recovery or global numerical gather
    is involved.
    """

    target = getattr(getattr(full_rhs, "x", None), "petsc_vec", full_rhs)
    if not hasattr(active_residual, "getSize") or not hasattr(
        target, "getSize"
    ):
        raise TypeError("J^H requires PETSc vectors")
    if int(active_residual.getSize()) != int(condensed.active_rows):
        raise ValueError("active residual size differs from condensed metadata")
    if int(target.getSize()) != int(condensed.full_rows):
        raise ValueError("full RHS size differs from condensed metadata")

    active_original = np.asarray(
        condensed.trace_constraints.owned_active_original_dofs,
        dtype=PETSc.IntType,
    )
    if active_original.size != int(condensed.owned_active_rows):
        raise ValueError("active-trace ownership metadata is inconsistent")
    if int(active_residual.getLocalSize()) != active_original.size:
        raise ValueError("active residual ownership differs from condensed metadata")

    first, last = (int(value) for value in target.getOwnershipRange())
    if active_original.size and (
        int(active_original.min()) < first or int(active_original.max()) >= last
    ):
        raise ValueError("active-trace rows are not locally owned by the full RHS")

    target.set(0)
    if active_original.size:
        target.setValues(
            active_original,
            np.asarray(active_residual.getArray(readonly=True), dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    target.assemble()
    return target


__all__ = [
    "extract_full_p6_to_active_trace",
    "inject_active_residual_to_full_p6",
]
