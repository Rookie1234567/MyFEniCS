"""Local tensor expansion and static condensation for Task035d variable-p.

Only degree-six *cell tensors* are used as a reusable reference container.
The global matrix is assembled in the physically active variable-p trace
numbering.  Inactive p6 modes therefore never acquire a global row.  This is
different from assembling a p6 matrix and subsequently masking coefficients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from src.adaptivity.exact_sequence_variable_p import (
    VariablePReferenceSpace,
)


@dataclass(frozen=True)
class VariablePLocalSchur:
    """Condensed active trace tensor plus exact interior recovery data."""

    space: VariablePReferenceSpace
    active_tensor: np.ndarray
    active_rhs: np.ndarray
    schur_tensor: np.ndarray
    schur_rhs: np.ndarray
    interior_from_trace: np.ndarray
    interior_load: np.ndarray
    audit: dict[str, Any]

    def recover_active_coefficients(
        self,
        trace_coefficients: np.ndarray,
    ) -> np.ndarray:
        """Recover all active local coefficients from a trace solution."""

        trace = np.asarray(trace_coefficients)
        if trace.shape != (len(self.space.trace_dofs),):
            raise ValueError(
                "trace coefficient vector has the wrong local dimension"
            )
        interior = self.interior_load - self.interior_from_trace @ trace
        active = np.zeros(
            self.space.hcurl_dimension,
            dtype=np.result_type(trace, self.active_rhs),
        )
        active[self.space.trace_dofs] = trace
        active[self.space.interior_dofs] = interior
        return active

    def recover_p6_coefficients(
        self,
        trace_coefficients: np.ndarray,
    ) -> np.ndarray:
        """Recover the local field representation in the p6 container."""

        return self.space.expand_hcurl_coefficients(
            self.recover_active_coefficients(trace_coefficients)
        )


def project_p6_local_tensor(
    space: VariablePReferenceSpace,
    p6_tensor: np.ndarray,
) -> np.ndarray:
    """Form ``E_K^H A_K,p6 E_K`` without a p6 global matrix."""

    tensor = np.asarray(p6_tensor)
    expected = (
        space.hcurl_to_p6.shape[0],
        space.hcurl_to_p6.shape[0],
    )
    if tensor.shape != expected:
        raise ValueError(
            f"p6 local tensor shape {tensor.shape} does not match {expected}"
        )
    if not np.all(np.isfinite(tensor)):
        raise ValueError("p6 local tensor contains non-finite entries")
    expansion = np.asarray(space.hcurl_to_p6)
    return np.ascontiguousarray(expansion.conj().T @ tensor @ expansion)


def project_p6_local_vector(
    space: VariablePReferenceSpace,
    p6_vector: np.ndarray,
) -> np.ndarray:
    """Project one p6 local load into the active coefficient dual."""

    vector = np.asarray(p6_vector)
    expected = (space.hcurl_to_p6.shape[0],)
    if vector.shape != expected:
        raise ValueError(
            f"p6 local vector shape {vector.shape} does not match {expected}"
        )
    if not np.all(np.isfinite(vector)):
        raise ValueError("p6 local vector contains non-finite entries")
    return np.ascontiguousarray(space.hcurl_to_p6.conj().T @ vector)


def condense_variable_p_local_tensor(
    space: VariablePReferenceSpace,
    p6_tensor: np.ndarray,
    p6_rhs: np.ndarray | None = None,
) -> VariablePLocalSchur:
    """Project and statically condense one active variable-p cell.

    The returned Schur tensor is indexed only by active edge/face modes.  Cell
    modes are eliminated locally.  The p6 input is a cell-local tensor, not a
    global matrix, and is not retained by the result.
    """

    active_tensor = project_p6_local_tensor(space, p6_tensor)
    if p6_rhs is None:
        active_rhs = np.zeros(
            space.hcurl_dimension,
            dtype=active_tensor.dtype,
        )
    else:
        active_rhs = project_p6_local_vector(space, p6_rhs)
    trace = np.asarray(space.trace_dofs, dtype=np.int32)
    interior = np.asarray(space.interior_dofs, dtype=np.int32)
    if len(trace) == 0 or len(interior) == 0:
        raise ValueError(
            "variable-p static condensation requires trace and interior modes"
        )
    A_tt = np.asarray(active_tensor[np.ix_(trace, trace)])
    A_ti = np.asarray(active_tensor[np.ix_(trace, interior)])
    A_it = np.asarray(active_tensor[np.ix_(interior, trace)])
    A_ii = np.asarray(active_tensor[np.ix_(interior, interior)])
    b_t = np.asarray(active_rhs[trace])
    b_i = np.asarray(active_rhs[interior])
    try:
        interior_from_trace = np.linalg.solve(A_ii, A_it)
        interior_load = np.linalg.solve(A_ii, b_i)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "active cell-interior block is singular; refusing condensation"
        ) from exc
    schur_tensor = np.ascontiguousarray(
        A_tt - A_ti @ interior_from_trace
    )
    schur_rhs = np.ascontiguousarray(b_t - A_ti @ interior_load)
    interior_residual = (
        A_ii @ interior_load - b_i
        if len(interior)
        else np.empty(0, dtype=active_tensor.dtype)
    )
    audit = {
        "schema_version": "task035d.variable-p-local-schur.v1",
        "status": "variable_p_local_static_condensation_pass",
        "pass": True,
        "degree_map": space.degree_map.to_dict(),
        "p6_local_rows": int(space.hcurl_to_p6.shape[0]),
        "active_local_rows": space.hcurl_dimension,
        "active_trace_rows": len(trace),
        "active_cell_interior_rows": len(interior),
        "inactive_p6_local_modes": int(
            space.hcurl_to_p6.shape[0] - space.hcurl_dimension
        ),
        "schur_rows": len(trace),
        "interior_load_residual_max": float(
            np.max(np.abs(interior_residual), initial=0.0)
        ),
        "full_p6_global_matrix_constructed": False,
        "inactive_p6_rows_globally_numbered": False,
        "active_tensor_retained_for_fixture_audit": True,
        "ordinary_default_changed": False,
    }
    for array in (
        active_tensor,
        active_rhs,
        schur_tensor,
        schur_rhs,
        interior_from_trace,
        interior_load,
    ):
        array.setflags(write=False)
    return VariablePLocalSchur(
        space=space,
        active_tensor=active_tensor,
        active_rhs=active_rhs,
        schur_tensor=schur_tensor,
        schur_rhs=schur_rhs,
        interior_from_trace=np.ascontiguousarray(interior_from_trace),
        interior_load=np.ascontiguousarray(interior_load),
        audit=audit,
    )


__all__ = [
    "VariablePLocalSchur",
    "condense_variable_p_local_tensor",
    "project_p6_local_tensor",
    "project_p6_local_vector",
]
