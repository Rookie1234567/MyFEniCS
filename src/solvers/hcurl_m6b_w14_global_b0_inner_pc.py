"""Research-only fixed global B0 inner-PC wrapper for W14.

The wrapper owns one reusable RHS vector and borrows the existing M5
MatPython operator and right-PC context.  The fixed M5 solve remains the
single implementation of the 20-step FGMRES algorithm; this module only
records a scalar/hash audit and enforces its inner true-residual gate.
"""

from __future__ import annotations

from collections.abc import Mapping
import time
from typing import Any

import numpy as np
from petsc4py import PETSc

from .hcurl_h2b_m5_coercive import (
    M5B0MatPythonContext,
    M5M4YPCContext,
    _array_sha256,
    solve_m5_b0_fixed,
)


__all__ = ("W14GlobalB0InnerPC",)


_W14_SCHEMA = "task037.extra.h2b.w14.global-b0-inner-pc.v1"
_W14_MAX_IT = 20
_W14_RESTART = 20
_W14_TRUE_RESIDUAL_LIMIT = 1.0e-2


def _require_context_audits(
    operator_context: M5B0MatPythonContext,
    pc_context: M5M4YPCContext,
    rows: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operator_audit = operator_context.audit
    pc_audit = pc_context.audit
    if not isinstance(operator_audit, Mapping) or not isinstance(pc_audit, Mapping):
        raise TypeError("W14 underlying audits must be mappings")
    if (
        operator_audit["mat_python"] is not True
        or operator_audit["global_matrix_materialized"] is not False
        or operator_audit["owned_rows"] != rows
        or operator_audit["global_rows"] != rows
    ):
        raise ValueError("W14 B0 MatPython audit is incompatible")
    if (
        pc_audit["pc_python"] is not True
        or pc_audit["pc_side"] != "right"
        or pc_audit["mpi_size"] != 1
        or pc_audit["global_rows"] != rows
    ):
        raise ValueError("W14 M5 PC audit is incompatible")
    return dict(operator_audit), dict(pc_audit)


class W14GlobalB0InnerPC:
    """Apply the fixed 20-step global coercive B0 solve as a right PC."""

    def __init__(
        self,
        operator: PETSc.Mat,
        pc_context: M5M4YPCContext,
        operator_context: M5B0MatPythonContext,
    ) -> None:
        if not isinstance(operator_context, M5B0MatPythonContext):
            raise TypeError("W14 requires the existing M5 B0 MatPython context")
        if not isinstance(pc_context, M5M4YPCContext):
            raise TypeError("W14 requires the existing M5 M4Y PC context")
        if operator.getComm().getSize() != 1:
            raise ValueError("W14 global B0 inner PC is fixed to MPI1")
        local_rows, local_cols = operator.getLocalSize()
        global_rows, global_cols = operator.getSize()
        if (
            local_rows != local_cols
            or global_rows != global_cols
            or local_rows != global_rows
            or global_rows <= 0
        ):
            raise ValueError("W14 requires a single-rank owner-local square operator")
        self._operator = operator
        self._pc_context = pc_context
        self._operator_context = operator_context
        self._rows = int(global_rows)
        _require_context_audits(operator_context, pc_context, self._rows)
        self._rhs_vec = operator.createVecRight()
        if self._rhs_vec.getLocalSize() != self._rows:
            self._rhs_vec.destroy()
            raise ValueError("W14 RHS Vec ownership differs from B0 operator")
        self._records: list[dict[str, Any]] = []

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        """Apply fixed zero-start B0 FGMRES and enforce the true-residual gate."""

        if self._rhs_vec is None:
            raise RuntimeError("W14 inner PC has been destroyed")
        values = np.asarray(rhs)
        if (
            values.dtype != np.dtype(np.complex128)
            or values.ndim != 1
            or values.size != self._rows
            or not np.all(np.isfinite(values))
        ):
            raise ValueError("W14 RHS must be a finite complex128 owner-local vector")
        np.copyto(self._rhs_vec.getArray(), values)
        self._rhs_vec.assemble()
        operator_before = int(self._operator_context.apply_count)
        pc_before = int(self._pc_context.apply_count)
        started = time.perf_counter()
        result = solve_m5_b0_fixed(
            self._operator,
            self._rhs_vec,
            pc_context=self._pc_context,
            max_it=_W14_MAX_IT,
            operator_context=self._operator_context,
        )
        elapsed = float(time.perf_counter() - started)
        solution = result.pop("solution")
        operator_delta = int(self._operator_context.apply_count) - operator_before
        pc_delta = int(self._pc_context.apply_count) - pc_before
        true_residual = float(result["true_residual"])
        finite = bool(
            np.all(np.isfinite(solution)) and np.isfinite(true_residual)
        )
        gate_pass = bool(finite and true_residual <= _W14_TRUE_RESIDUAL_LIMIT)
        record = {
            "apply_index": len(self._records) + 1,
            "algorithm": "fgmres_right_b0_fixed20",
            "rhs_norm": float(np.linalg.norm(values)),
            "rhs_sha256": _array_sha256(values),
            "solution_sha256": _array_sha256(solution),
            "iterations": int(result["iterations"]),
            "converged_reason": int(result["converged_reason"]),
            "true_residual": true_residual,
            "true_residual_limit": _W14_TRUE_RESIDUAL_LIMIT,
            "operator_apply_count_delta": operator_delta,
            "pc_apply_count_delta": pc_delta,
            "wall_seconds": elapsed,
            "finite": finite,
            "gate_pass": gate_pass,
        }
        self._records.append(record)
        if not gate_pass:
            del solution
            raise RuntimeError("W14 B0 inner true-residual gate failed")
        returned = np.array(solution, dtype=np.complex128, copy=True)
        del solution
        return returned

    @property
    def audit(self) -> dict[str, Any]:
        """Application records keep no full-space vectors; the wrapper-owned reusable RHS Vec is counted separately."""

        rhs_vec_destroyed = self._rhs_vec is None
        rhs_vec_count = 0 if rhs_vec_destroyed else 1
        rhs_vec_bytes = (
            0 if rhs_vec_destroyed else self._rows * np.dtype(np.complex128).itemsize
        )
        return {
            "schema": _W14_SCHEMA,
            "algorithm": {
                "solver": "fgmres",
                "restart": _W14_RESTART,
                "max_it": _W14_MAX_IT,
                "zero_start": True,
                "rtol": 0.0,
                "atol": 0.0,
                "pc_side": "right",
                "mpi_size": 1,
            },
            "rows": self._rows,
            "rhs_vec_owned": not rhs_vec_destroyed,
            "rhs_vec_destroyed": rhs_vec_destroyed,
            "wrapper_owned_full_vector_count": rhs_vec_count,
            "wrapper_owned_full_vector_bytes": rhs_vec_bytes,
            "retained_full_vector_count": rhs_vec_count,
            "retained_full_vector_bytes": rhs_vec_bytes,
            "application_records_full_vector_count": 0,
            "application_records_full_vector_bytes": 0,
            "ownership": {
                "rhs_work_vec": "owned",
                "operator": "borrowed",
                "contexts": "borrowed",
                "factor_store": "borrowed",
            },
            "applications": [dict(record) for record in self._records],
            "underlying_operator": dict(self._operator_context.audit),
            "underlying_pc": dict(self._pc_context.audit),
            "architecture": {
                "fine_space": "uncondensed_fullspace",
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab": False,
                "slab_factors": 0,
            },
        }

    def destroy(self) -> None:
        """Destroy only the wrapper-owned RHS Vec; borrowed objects remain live."""

        if self._rhs_vec is not None:
            self._rhs_vec.destroy()
            self._rhs_vec = None
