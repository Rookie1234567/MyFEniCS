"""R7a cell-local p4-core partial condensation oracle.

The component keeps the standard p6 trace and p4 cell-interior range in an
oriented local basis.  It eliminates only the p5/p6 interior complement and
does not create a global p6 matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.linalg import lu_factor, lu_solve, qr

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    VariablePReferenceSpace,
    apply_active_dof_transformation,
    build_variable_p_reference_space,
)


_ORIENTATION_TOLERANCE = 1.0e-11
_RANK_RELATIVE_TOLERANCE = 1.0e-12


def _relative_error(observed: np.ndarray, reference: np.ndarray) -> float:
    difference = np.linalg.norm(np.asarray(observed) - np.asarray(reference))
    scale = max(float(np.linalg.norm(np.asarray(reference))), 1.0e-30)
    return float(difference / scale)


def _readonly(values: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(values)
    result.setflags(write=False)
    return result


def _rank_revealing_basis(
    values: np.ndarray,
    expected_rank: int,
    *,
    label: str,
) -> tuple[np.ndarray, int, float]:
    matrix = np.asarray(values)
    q_factor, r_factor, _pivot = qr(
        matrix,
        mode="economic",
        pivoting=True,
    )
    diagonal = np.abs(np.diag(r_factor))
    scale = float(diagonal[0]) if diagonal.size else 0.0
    tolerance = _RANK_RELATIVE_TOLERANCE * scale
    rank = int(np.count_nonzero(diagonal > tolerance))
    if rank != int(expected_rank):
        raise RuntimeError(f"{label} rank {rank} != expected {expected_rank}")
    return (
        _readonly(q_factor[:, :rank]),
        rank,
        float(tolerance),
    )


def _oriented_interior_embedding(
    source: VariablePReferenceSpace,
    p6: VariablePReferenceSpace,
    *,
    cell_info: int,
) -> np.ndarray:
    """Return the full-space interior-column p->p6 embedding."""

    interior = np.asarray(source.interior_dofs, dtype=np.int32)
    coefficients = np.zeros(
        (source.hcurl_dimension, interior.size),
        dtype=np.float64,
    )
    coefficients[interior, np.arange(interior.size)] = 1.0
    coefficients_reference = source.apply_hcurl_dof_transform(
        coefficients,
        cell_info=cell_info,
        transpose=True,
    )
    expanded_reference = source.hcurl_to_p6 @ coefficients_reference
    return np.ascontiguousarray(
        apply_active_dof_transformation(
            p6,
            expanded_reference,
            family="hcurl",
            cell_info=cell_info,
        )
    )


@dataclass(frozen=True)
class P4CorePartialCondensation:
    """Partial p6 condensation with a retained trace-plus-p4-core vector."""

    partial_schur: np.ndarray
    partial_rhs: np.ndarray
    core_basis: np.ndarray
    eliminated_basis: np.ndarray
    eliminated_from_retained: np.ndarray
    eliminated_load: np.ndarray
    p6_trace_dofs: np.ndarray
    p6_interior_dofs: np.ndarray
    audit: dict[str, Any]

    def recover_p6_coefficients(
        self,
        retained_coefficients: np.ndarray,
    ) -> np.ndarray:
        """Recover oriented p6 coefficients from ``[trace, p4-core]``."""

        retained = np.asarray(retained_coefficients, dtype=np.complex128)
        expected = int(self.partial_schur.shape[0])
        if retained.shape != (expected,):
            raise ValueError(
                "retained coefficient vector must have trace-plus-core size"
            )
        eliminated = self.eliminated_load + self.eliminated_from_retained @ retained
        interior = (
            self.core_basis @ retained[self.p6_trace_dofs.size :]
            + self.eliminated_basis @ eliminated
        )
        result = np.zeros(882, dtype=np.complex128)
        result[self.p6_trace_dofs] = retained[: self.p6_trace_dofs.size]
        result[self.p6_interior_dofs] = interior
        if not np.all(np.isfinite(result)):
            raise RuntimeError("partial p4-core recovery is non-finite")
        return result


def condense_p6_local_to_p4_core(
    p6_tensor_reference: np.ndarray,
    p6_rhs_reference: np.ndarray | None = None,
    *,
    cell_info: int,
) -> P4CorePartialCondensation:
    """Eliminate the p5/p6 interior complement of one oriented p6 cell.

    The input tensor and RHS are reference-oriented.  Orientation is applied
    to the complete p6 tensor and RHS before semantic trace/interior slicing.
    Only the resulting 540-row partial Schur and fixed recovery data survive.
    """

    tensor = np.asarray(p6_tensor_reference, dtype=np.complex128)
    if tensor.shape != (882, 882):
        raise ValueError("R7a requires a complete 882x882 p6 tensor")
    if not np.all(np.isfinite(tensor)):
        raise ValueError("p6 tensor contains non-finite entries")
    if p6_rhs_reference is None:
        rhs_reference = np.zeros(882, dtype=np.complex128)
        rhs_was_supplied = False
    else:
        rhs_reference = np.asarray(p6_rhs_reference, dtype=np.complex128)
        if rhs_reference.shape != (882,):
            raise ValueError("p6 RHS must have complete length 882")
        if not np.all(np.isfinite(rhs_reference)):
            raise ValueError("p6 RHS contains non-finite entries")
        rhs_was_supplied = True

    p4 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(4))
    p5 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(5))
    p6 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(6))
    if p6.hcurl_dimension != 882:
        raise RuntimeError("uniform p6 reference space is not 882-dimensional")

    oriented_tensor = p6.orient_hcurl_tensor(
        tensor,
        cell_info=int(cell_info),
    )
    oriented_rhs = p6.apply_hcurl_dof_transform(
        rhs_reference,
        cell_info=int(cell_info),
    )
    oriented_p4 = _oriented_interior_embedding(
        p4,
        p6,
        cell_info=int(cell_info),
    )
    oriented_p5 = _oriented_interior_embedding(
        p5,
        p6,
        cell_info=int(cell_info),
    )
    trace_dofs = np.asarray(p6.trace_dofs, dtype=np.int32)
    interior_dofs = np.asarray(p6.interior_dofs, dtype=np.int32)
    p4_trace_leakage = float(np.max(np.abs(oriented_p4[trace_dofs]), initial=0.0))
    p5_trace_leakage = float(np.max(np.abs(oriented_p5[trace_dofs]), initial=0.0))
    if max(p4_trace_leakage, p5_trace_leakage) > _ORIENTATION_TOLERANCE:
        raise RuntimeError("p4/p5 interior embedding leaks into p6 trace")

    p4_interior = oriented_p4[interior_dofs]
    p5_interior = oriented_p5[interior_dofs]
    q4, p4_rank, p4_rank_tolerance = _rank_revealing_basis(
        p4_interior,
        108,
        label="p4 interior embedding",
    )
    q5_full, p5_rank, p5_rank_tolerance = _rank_revealing_basis(
        p5_interior,
        240,
        label="p5 interior embedding",
    )
    nested_error = _relative_error(
        q5_full @ (q5_full.conj().T @ p4_interior),
        p4_interior,
    )
    if nested_error > _ORIENTATION_TOLERANCE:
        raise RuntimeError("p4 interior range is not nested in p5")

    p5_perpendicular = p5_interior - q4 @ (q4.conj().T @ p5_interior)
    q5, p5_increment_rank, p5_increment_tolerance = _rank_revealing_basis(
        p5_perpendicular,
        132,
        label="p5 increment",
    )
    q45 = np.column_stack((q4, q5))
    q_complete, _ = qr(q45, mode="full")
    q6 = _readonly(q_complete[:, 240:])
    q = np.column_stack((q4, q5, q6))
    orthogonality_error = float(
        np.max(
            np.abs(q.conj().T @ q - np.eye(450, dtype=q.dtype)),
            initial=0.0,
        )
    )
    if orthogonality_error > _ORIENTATION_TOLERANCE:
        raise RuntimeError("p4/p5/p6 interior basis is not orthogonal")

    basis = np.zeros((882, 882), dtype=np.complex128)
    basis[np.ix_(trace_dofs, np.arange(trace_dofs.size))] = np.eye(
        trace_dofs.size,
        dtype=np.complex128,
    )
    basis[np.ix_(interior_dofs, np.arange(trace_dofs.size, 882))] = q
    transformed_tensor = basis.conj().T @ oriented_tensor @ basis
    transformed_rhs = basis.conj().T @ oriented_rhs
    retained_rows = trace_dofs.size + q4.shape[1]
    eliminated_rows = 882 - retained_rows
    A_rr = transformed_tensor[:retained_rows, :retained_rows]
    A_re = transformed_tensor[:retained_rows, retained_rows:]
    A_er = transformed_tensor[retained_rows:, :retained_rows]
    A_ee = transformed_tensor[retained_rows:, retained_rows:]
    factor = lu_factor(A_ee)
    eliminated_from_retained = -lu_solve(factor, A_er)
    eliminated_load = lu_solve(factor, transformed_rhs[retained_rows:])
    partial_schur = A_rr + A_re @ eliminated_from_retained
    partial_rhs = transformed_rhs[:retained_rows] - A_re @ eliminated_load
    audit = {
        "schema_version": "task037.r7a.p4-core-partial-condensation.v1",
        "status": "p4_core_partial_condensation_built",
        "cell_info": int(cell_info),
        "p4_full_rows": int(p4.hcurl_dimension),
        "p5_full_rows": int(p5.hcurl_dimension),
        "p6_full_rows": int(p6.hcurl_dimension),
        "p4_interior_rows": 108,
        "p5_interior_rows": 240,
        "p6_interior_rows": int(interior_dofs.size),
        "p6_trace_rows": int(trace_dofs.size),
        "p4_interior_embedding_rank": p4_rank,
        "p5_interior_embedding_rank": p5_rank,
        "p5_increment_rank": p5_increment_rank,
        "p6_increment_rank": int(q6.shape[1]),
        "nested_range_relative_error": nested_error,
        "p4_rank_tolerance": p4_rank_tolerance,
        "p5_rank_tolerance": p5_rank_tolerance,
        "p5_increment_rank_tolerance": p5_increment_tolerance,
        "orthogonality_error_max": orthogonality_error,
        "p6_trace_leakage_max": max(p4_trace_leakage, p5_trace_leakage),
        "p4_trace_leakage_max": p4_trace_leakage,
        "p5_trace_leakage_max": p5_trace_leakage,
        "retained_rows": retained_rows,
        "eliminated_rows": eliminated_rows,
        "partial_schur_rows": int(partial_schur.shape[0]),
        "rhs_supplied": rhs_was_supplied,
        "orientation_applied_to_full_p6_tensor": True,
        "prefix_assumption_used": False,
        "raw_p6_tensor_retained": False,
        "research_only": True,
        "ordinary_default_changed": False,
    }
    if retained_rows != 540 or eliminated_rows != 342:
        raise RuntimeError("R7a retained/eliminated dimensions are incorrect")
    for values in (
        partial_schur,
        partial_rhs,
        q4,
        q,
        eliminated_from_retained,
        eliminated_load,
        trace_dofs,
        interior_dofs,
    ):
        values.setflags(write=False)
    return P4CorePartialCondensation(
        partial_schur=partial_schur,
        partial_rhs=partial_rhs,
        core_basis=_readonly(q4),
        eliminated_basis=_readonly(q[:, 108:]),
        eliminated_from_retained=_readonly(eliminated_from_retained),
        eliminated_load=_readonly(eliminated_load),
        p6_trace_dofs=_readonly(trace_dofs),
        p6_interior_dofs=_readonly(interior_dofs),
        audit=audit,
    )


__all__ = (
    "P4CorePartialCondensation",
    "condense_p6_local_to_p4_core",
)
