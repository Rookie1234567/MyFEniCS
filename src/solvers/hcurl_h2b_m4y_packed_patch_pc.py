"""Opt-in M4Y full-space residual-minimizing packed-patch preconditioner.

The M3Y cold store owns 84 read-only packed factors and 252 cell-to-row
references.  This module only applies those references in deterministic cell
order.  It never copies a factor per cell, retains a cell solution, or builds
an assembled matrix, Schur complement, trace slab, or KSP object.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
from typing import Any

import numpy as np

__all__ = (
    "H2B_M4Y_PACKED_PC_SCHEMA",
    "H2B_M4Y_POU_CLOSURE_LIMIT",
    "H2B_M4Y_ACTION_REPEAT_LIMIT",
    "H2B_M4Y_RHO_LIMITS",
    "H2BM4YPackedPatchPC",
    "build_h2b_m4y_packed_patch_pc",
)


H2B_M4Y_PACKED_PC_SCHEMA = "task037.extra.h2b.m4y.packed-patch-pc.v1"
H2B_M4Y_POU_CLOSURE_LIMIT = 1.0e-14
H2B_M4Y_ACTION_REPEAT_LIMIT = 1.0e-11
H2B_M4Y_RHO_LIMITS = {
    "checkerboard/high-frequency": 0.70,
    "mixed": 0.80,
    "gradient-dominated": 0.90,
    "curl-dominated": 0.90,
    "physical-RHS-like": 0.90,
}
_COMPLEX128_BYTES = np.dtype(np.complex128).itemsize


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _finite_vector(value: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.dtype != np.dtype(np.complex128)
        or array.ndim != 1
        or array.shape[0] != size
        or not array.flags.c_contiguous
        or not np.all(np.isfinite(array))
    ):
        raise ValueError(f"M4Y {name} must be a finite C-contiguous complex128 vector")
    return array


def _required_false_materialization(value: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping):
        return False
    required = (
        "global_matrix",
        "global_constraint_matrix",
        "patch_matrices",
        "static_condensation",
        "trace_slab",
        "schur",
        "slab_factor",
        "ql_qh_transform",
        "per_cell_factor",
    )
    return all(value.get(key) is False for key in required)


class H2BM4YPackedPatchPC:
    """One additive full-space packed-patch PC with residual minimization.

    ``exact_action`` is an in-place full-space callback.  It receives the
    correction and a preallocated target and must return ``None``.  The
    callback is called exactly once per ``apply``.
    """

    def __init__(
        self,
        factor_store: Any,
        *,
        global_row_count: int,
        exact_action: Callable[[np.ndarray, np.ndarray], None],
        slave_identity_rows: Sequence[int] = (),
        task037_extra_h2b: bool = False,
    ) -> None:
        if task037_extra_h2b is not True:
            raise ValueError("M4Y PC requires explicit task037_extra_h2b opt-in")
        if type(global_row_count) is not int or global_row_count <= 0:
            raise ValueError("M4Y global row count is invalid")
        if not callable(exact_action):
            raise TypeError("M4Y exact action must be callable")
        audit = factor_store.audit_jsonable()
        if (
            not isinstance(audit, Mapping)
            or audit.get("packed_cholesky") is not True
            or audit.get("full_dense_factor_count") != 0
            or audit.get("pivots_retained") is not False
            or audit.get("retained_total_gate") is not True
            or audit.get("ordinary_default_changed") is not False
            or not _required_false_materialization(
                audit.get("materialization_identity", {})
            )
        ):
            raise ValueError("M4Y requires a closed M3Y packed store")

        self._store = factor_store
        self._global_row_count = global_row_count
        self._exact_action = exact_action
        self._cell_count = int(factor_store.cell_neighborhood_ids.size)
        if self._cell_count <= 0:
            raise ValueError("M4Y packed store has no cell references")

        cell_rows: list[np.ndarray] = []
        for cell_id in range(self._cell_count):
            rows = np.asarray(factor_store.cell_rows(cell_id))
            if (
                rows.dtype != np.dtype(np.int64)
                or rows.ndim != 1
                or rows.size == 0
                or np.any(rows < 0)
                or np.any(rows >= global_row_count)
                or np.unique(rows).size != rows.size
            ):
                raise ValueError("M4Y cell row mapping is invalid")
            factor = factor_store.factor_for_cell(cell_id)
            if rows.size != int(factor.n):
                raise ValueError("M4Y cell rows do not match packed factor order")
            rows.setflags(write=False)
            cell_rows.append(rows)
        self._cell_rows = tuple(cell_rows)

        slaves = np.asarray(slave_identity_rows, dtype=np.int64)
        if slaves.ndim != 1 or np.unique(slaves).size != slaves.size:
            raise ValueError("M4Y slave identity rows are invalid")
        if slaves.size and (
            np.any(slaves < 0) or np.any(slaves >= global_row_count)
        ):
            raise ValueError("M4Y slave identity rows are out of range")
        slaves = np.unique(slaves)
        covered = np.unique(np.concatenate(self._cell_rows))
        if np.intersect1d(covered, slaves).size:
            raise ValueError("M4Y cell rows contain slave identity rows")
        expected_slaves = np.setdiff1d(
            np.arange(global_row_count, dtype=np.int64), covered
        )
        if not np.array_equal(expected_slaves, slaves):
            raise ValueError("M4Y cell rows and slave identity rows do not partition full space")
        self._slave_rows = np.array(slaves, dtype=np.int64, order="C", copy=True)
        self._slave_rows.setflags(write=False)
        self._independent_rows = np.array(covered, dtype=np.int64, order="C", copy=True)
        self._independent_rows.setflags(write=False)

        multiplicity = np.zeros(global_row_count, dtype=np.int32)
        for rows in self._cell_rows:
            np.add.at(multiplicity, rows, 1)
        partition_sum = np.zeros(global_row_count, dtype=np.float64)
        for rows in self._cell_rows:
            np.add.at(partition_sum, rows, 1.0 / multiplicity[rows])
        closure = float(
            np.max(np.abs(partition_sum[self._independent_rows] - 1.0))
        )
        if not np.isfinite(closure) or closure > H2B_M4Y_POU_CLOSURE_LIMIT:
            raise ValueError("M4Y partition-of-unity closure failed")
        multiplicity.setflags(write=False)
        self._multiplicity = multiplicity
        self._pou_closure_error = closure
        self._audit = self._make_audit(audit)

    def _make_audit(self, store_audit: Mapping[str, Any]) -> dict[str, Any]:
        global_vectors = 4 * self._global_row_count * _COMPLEX128_BYTES
        local_vectors = max(rows.size for rows in self._cell_rows)
        local_workspace = 2 * local_vectors * _COMPLEX128_BYTES
        materialization = {
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "static_condensation": False,
            "trace_slab": False,
            "schur": False,
            "slab_factor": False,
            "ql_qh_transform": False,
            "per_cell_factor": False,
        }
        return {
            "schema": H2B_M4Y_PACKED_PC_SCHEMA,
            "global_row_count": self._global_row_count,
            "cell_count": self._cell_count,
            "unique_factor_count": int(store_audit["packed_factor_count"]),
            "factor_reuse_count": self._cell_count
            - int(store_audit["packed_factor_count"]),
            "factor_copy_count": 0,
            "per_cell_solution_retained": False,
            "multiplicity_bytes": int(self._multiplicity.nbytes),
            "m3y_retained_total_bytes": int(store_audit["retained_total_bytes"]),
            "bounded_apply_workspace_bytes": int(global_vectors + local_workspace),
            "workspace_components": {
                "four_full_space_vectors_bytes": int(global_vectors),
                "local_rhs_and_solution_bytes": int(local_workspace),
            },
            "partition_of_unity_closure_error": self._pou_closure_error,
            "fine_space": "uncondensed_fullspace",
            "materialization_identity": materialization,
            "ordinary_default_changed": False,
        }

    @property
    def audit(self) -> dict[str, Any]:
        return dict(self._audit)

    @property
    def multiplicity(self) -> np.ndarray:
        return self._multiplicity.copy()

    def _build_additive_correction(self, rhs: np.ndarray) -> np.ndarray:
        correction = np.zeros(self._global_row_count, dtype=np.complex128)
        for cell_id, rows in enumerate(self._cell_rows):
            local_rhs = np.array(rhs[rows], dtype=np.complex128, order="C", copy=True)
            local_solution = self._store.solve(cell_id, local_rhs)
            if (
                local_solution.dtype != np.dtype(np.complex128)
                or local_solution.shape != rows.shape
                or not np.all(np.isfinite(local_solution))
            ):
                raise ValueError("M4Y packed solve returned invalid values")
            correction[rows] += local_solution / self._multiplicity[rows]
            del local_rhs, local_solution
        if self._slave_rows.size:
            correction[self._slave_rows] = rhs[self._slave_rows]
        return correction

    def apply_with_measurement(
        self, rhs: np.ndarray
    ) -> tuple[np.ndarray, dict[str, Any]]:
        residual_rhs = _finite_vector(rhs, self._global_row_count, "residual")
        correction0 = self._build_additive_correction(residual_rhs)
        action_output = np.empty(self._global_row_count, dtype=np.complex128)
        returned = self._exact_action(correction0, action_output)
        if returned is not None:
            raise TypeError("M4Y exact action must fill target and return None")
        if not np.all(np.isfinite(action_output)):
            raise FloatingPointError("M4Y exact action returned nonfinite values")
        denominator = np.vdot(action_output, action_output)
        if not np.isfinite(denominator.real) or denominator.real <= 0.0:
            raise FloatingPointError("M4Y exact action has zero or invalid norm")
        omega = complex(np.vdot(action_output, residual_rhs) / denominator)
        correction = np.asarray(omega * correction0, dtype=np.complex128, order="C")
        residual = np.asarray(
            residual_rhs - omega * action_output,
            dtype=np.complex128,
            order="C",
        )
        rhs_norm = float(np.linalg.norm(residual_rhs))
        rho = float(np.linalg.norm(residual) / max(rhs_norm, np.finfo(float).tiny))
        measurement = {
            "schema": H2B_M4Y_PACKED_PC_SCHEMA,
            "rhs_sha256": _array_sha256(residual_rhs),
            "correction0_sha256": _array_sha256(correction0),
            "correction_sha256": _array_sha256(correction),
            "action_sha256": _array_sha256(action_output),
            "residual_sha256": _array_sha256(residual),
            "omega": [float(omega.real), float(omega.imag)],
            "rho": rho,
            "finite": bool(np.all(np.isfinite(correction)) and np.all(np.isfinite(residual))),
            "exact_action_count": 1,
            "partition_of_unity_closure_error": self._pou_closure_error,
        }
        return correction, measurement

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        correction, _measurement = self.apply_with_measurement(rhs)
        return correction


def build_h2b_m4y_packed_patch_pc(
    factor_store: Any,
    *,
    global_row_count: int,
    exact_action: Callable[[np.ndarray, np.ndarray], None],
    slave_identity_rows: Sequence[int] = (),
    task037_extra_h2b: bool = False,
) -> H2BM4YPackedPatchPC:
    """Build the explicitly opted-in M4Y packed-patch PC."""

    return H2BM4YPackedPatchPC(
        factor_store,
        global_row_count=global_row_count,
        exact_action=exact_action,
        slave_identity_rows=slave_identity_rows,
        task037_extra_h2b=task037_extra_h2b,
    )
