"""Research-only fixed global B0 inner-PC wrapper for W14.

The wrapper owns one reusable RHS vector and borrows the existing M5
MatPython operator and right-PC context.  The fixed M5 solve remains the
single implementation of the 20-step FGMRES algorithm; this module only
records a scalar/hash audit and enforces its inner true-residual gate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
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


__all__ = (
    "W14A_ACTION_SCHEMA",
    "W14A_CLOSURE_LIMIT",
    "W14A_PREDICTED_LIVE_SET_BYTES",
    "W14A_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W14A_RELATIVE_IDENTITY_LIMIT",
    "W14A_RHO_LIMIT",
    "W14GlobalB0InnerPC",
    "evaluate_w14a_action_gate",
)


_W14_SCHEMA = "task037.extra.h2b.w14.global-b0-inner-pc.v1"
_W14_MAX_IT = 20
_W14_RESTART = 20
_W14_TRUE_RESIDUAL_LIMIT = 1.0e-2
W14A_ACTION_SCHEMA = "task037.extra.h2b.w14a.action-only.global-b0.v1"
W14A_RHO_LIMIT = 0.95
W14A_CLOSURE_LIMIT = 1.0e-11
W14A_RELATIVE_IDENTITY_LIMIT = 1.0e-13
W14A_PREDICTED_LIVE_SET_BYTES = 1_281_057_286
W14A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_500_000_000


def _finite_bounded(value: Any, limit: float | None = None) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0.0 and (limit is None or number <= limit)


def evaluate_w14a_action_gate(
    *,
    inner_audit: Mapping[str, Any],
    z_identity: Mapping[str, Any],
    p_identity: Mapping[str, Any],
    measurement: Mapping[str, Any],
    p2_measurement: Mapping[str, Any],
    physical_action_count: int,
    architecture: Mapping[str, Any],
    lifecycle_events: Sequence[str],
    predicted_live_set: Mapping[str, Any],
    source_ok: bool,
    cache_ok: bool,
) -> dict[str, bool]:
    """Evaluate the fixed W14.1 action-only Gate from scalar evidence.

    This intentionally accepts only already-recorded scalar/hash audits.  A
    missing field makes the corresponding check false; no numeric fallback or
    alternate action path is introduced.
    """

    checks = {
        "inner_records": False,
        "inner_algorithm": False,
        "inner_residual": False,
        "inner_work_vector": False,
        "z_identity": False,
        "p_identity": False,
        "physical_action_count": False,
        "measurement": False,
        "measurement_repeat": False,
        "p2_measurement": False,
        "architecture": False,
        "coexistence_lifecycle": False,
        "prediction": False,
        "source": bool(source_ok is True),
        "cache": bool(cache_ok is True),
    }
    if not all(
        isinstance(value, Mapping)
        for value in (
            inner_audit,
            z_identity,
            p_identity,
            measurement,
            p2_measurement,
            architecture,
            predicted_live_set,
        )
    ):
        return checks
    try:
        algorithm = inner_audit["algorithm"]
        checks["inner_algorithm"] = (
            isinstance(algorithm, Mapping)
            and algorithm["solver"] == "fgmres"
            and algorithm["restart"] == 20
            and algorithm["max_it"] == 20
            and algorithm["zero_start"] is True
            and algorithm["rtol"] == 0.0
            and algorithm["atol"] == 0.0
            and algorithm["pc_side"] == "right"
            and algorithm["mpi_size"] == 1
        )
        records = inner_audit["applications"]
        if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
            checks["inner_records"] = len(records) == 2
            checks["inner_algorithm"] = checks["inner_algorithm"] and all(
                record["algorithm"] == "fgmres_right_b0_fixed20"
                and record["iterations"] == 20
                and record["converged_reason"] == -3
                and record["pc_apply_count_delta"] == record["iterations"]
                and record["operator_apply_count_delta"] > 0
                for record in records
            )
            checks["inner_algorithm"] = checks["inner_algorithm"] and (
                isinstance(inner_audit["underlying_pc"], Mapping)
                and inner_audit["underlying_pc"]["apply_count"]
                == sum(record["pc_apply_count_delta"] for record in records)
            )
            checks["inner_residual"] = all(
                record["finite"] is True
                and record["gate_pass"] is True
                and _finite_bounded(record["true_residual"], _W14_TRUE_RESIDUAL_LIMIT)
                for record in records
            )
            checks["inner_records"] = checks["inner_records"] and all(
                record["rhs_sha256"] == records[0]["rhs_sha256"] for record in records
            )
        checks["inner_work_vector"] = (
            inner_audit["rhs_vec_owned"] is True
            and inner_audit["rhs_vec_destroyed"] is False
            and inner_audit["rows"] > 0
            and inner_audit["retained_full_vector_count"] == 1
            and inner_audit["retained_full_vector_bytes"]
            == inner_audit["rows"] * np.dtype(np.complex128).itemsize
            and inner_audit["wrapper_owned_full_vector_count"] == 1
            and inner_audit["wrapper_owned_full_vector_bytes"]
            == inner_audit["rows"] * np.dtype(np.complex128).itemsize
            and inner_audit["application_records_full_vector_count"] == 0
            and inner_audit["application_records_full_vector_bytes"] == 0
        )
        checks["z_identity"] = (
            z_identity["finite"] is True
            and z_identity["dtype"] == "complex128"
            and z_identity["shape_equal"] is True
            and z_identity["sha256_equal"] is True
            and _finite_bounded(
                z_identity["relative_difference"], W14A_RELATIVE_IDENTITY_LIMIT
            )
        )
        checks["p_identity"] = (
            p_identity["finite"] is True
            and p_identity["dtype"] == "complex128"
            and p_identity["shape_equal"] is True
            and p_identity["sha256_equal"] is True
            and _finite_bounded(
                p_identity["relative_difference"], W14A_RELATIVE_IDENTITY_LIMIT
            )
        )
        checks["physical_action_count"] = physical_action_count == 2
        checks["measurement"] = (
            measurement["schema"] == W14A_ACTION_SCHEMA
            and measurement["finite"] is True
            and _finite_bounded(measurement["rho"], W14A_RHO_LIMIT)
            and _finite_bounded(measurement["normal_closure"], W14A_CLOSURE_LIMIT)
            and _finite_bounded(
                measurement["projection_orthogonality"], W14A_CLOSURE_LIMIT
            )
        )
        checks["measurement_repeat"] = (
            measurement["repeat_exact"] is True
            and measurement["repeat"]["repeat_exact"] is True
            and measurement["repeat"]["passes"] == 2
        )
        checks["p2_measurement"] = (
            p2_measurement["schema"] == W14A_ACTION_SCHEMA
            and p2_measurement["finite"] is True
            and _finite_bounded(p2_measurement["rho"], W14A_RHO_LIMIT)
            and _finite_bounded(p2_measurement["normal_closure"], W14A_CLOSURE_LIMIT)
            and _finite_bounded(
                p2_measurement["projection_orthogonality"], W14A_CLOSURE_LIMIT
            )
        )
        checks["architecture"] = (
            architecture["fine_space"] == "uncondensed_fullspace"
            and architecture["global_matrix_materialized"] is False
            and architecture["augmented_matrix_materialized"] is False
            and architecture["condensation"] is False
            and architecture["static_condensed_operator_used"] is False
            and architecture["trace_slab_pc_used"] is False
            and architecture["slab_factors"] == 0
            and architecture["shifted_pc_used"] is False
            and architecture["physical_ksp_used"] is False
            and architecture["pde_used"] is False
            and architecture["official_rta"] is False
        )
        checks["coexistence_lifecycle"] = list(lifecycle_events) == [
            "b0_constructed",
            "physical_constructed",
            "coexistence_ready",
            "physical_released",
            "b0_released",
        ]
        checks["prediction"] = (
            predicted_live_set["bytes"] == W14A_PREDICTED_LIVE_SET_BYTES
            and predicted_live_set["limit_bytes"] == W14A_PREDICTED_LIVE_SET_LIMIT_BYTES
            and predicted_live_set["gate"] is True
            and predicted_live_set["derived_not_measured"] is True
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return checks
    return checks


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
