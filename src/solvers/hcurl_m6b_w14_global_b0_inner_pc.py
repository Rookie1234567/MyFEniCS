"""Research-only fixed global B0 inner-PC wrapper for W14.

The wrapper owns one reusable RHS vector and borrows the existing M5
MatPython operator and right-PC context.  The fixed M5 solve remains the
single implementation of the 20-step FGMRES algorithm; this module only
records a scalar/hash audit and enforces its inner true-residual gate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import math
from pathlib import Path
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
from .disk_backed_flexible_gmres import (
    DiskBackedFlexibleGMRES,
    DiskBackedFlexibleGMRESResult,
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
    "W14B_CHECKPOINTS",
    "W14B_FIXED_MAX_STEPS",
    "W14B_PREDICTED_LIVE_SET_BYTES",
    "W14B_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W14B_RHO1_ANCHOR",
    "W14B_RHO4_LIMIT",
    "W14B_SCHEMA",
    "evaluate_w14b_fixed4_gate",
    "run_w14b_fixed4_cycle",
    "W15A_CUMULATIVE_RHO_LIMIT",
    "W15A_PREDICTED_LIVE_SET_BYTES",
    "W15A_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W15A_RESTART1_SCHEMA",
    "W15A_RHO1_AUTHORITY",
    "W15A_RHO_LIMIT",
    "evaluate_w15a_restart1_gate",
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
W14B_SCHEMA = "task037.extra.h2b.w14b.fixed4-physical-correction.v1"
W14B_FIXED_MAX_STEPS = 4
W14B_CHECKPOINTS = (1, 2, 4)
W14B_RHO1_ANCHOR = 0.8943645606070599
W14B_RHO1_LIMIT = 1.0e-12
W14B_RHO4_LIMIT = 0.75
W14B_MONOTONICITY_TOLERANCE = 1.0e-13
W14B_PREDICTED_LIVE_SET_BYTES = 1_348_166_150
W14B_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_500_000_000
W15A_RESTART1_SCHEMA = "task037.extra.h2b.w15a.restarted-rank1.v1"
W15A_RHO1_AUTHORITY = 0.8943645606070647
W15A_RHO_LIMIT = 0.90
W15A_CUMULATIVE_RHO_LIMIT = 0.81
W15A_PREDICTED_LIVE_SET_BYTES = W14A_PREDICTED_LIVE_SET_BYTES
W15A_PREDICTED_LIVE_SET_LIMIT_BYTES = W14A_PREDICTED_LIVE_SET_LIMIT_BYTES


def _finite_bounded(value: Any, limit: float | None = None) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0.0 and (limit is None or number <= limit)


def run_w14b_fixed4_cycle(
    rhs: np.ndarray,
    *,
    action: Callable[[np.ndarray], np.ndarray],
    pc: Callable[[np.ndarray], np.ndarray],
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> DiskBackedFlexibleGMRESResult:
    """Run the fixed four-step right flexible-GMRES correction cycle.

    The existing disk-backed solver owns the Arnoldi/MGS implementation.  No
    W14B caller can change its iteration, restart, initial-guess, or
    tolerance contract through this thin fixed configuration.
    """

    solver = DiskBackedFlexibleGMRES(
        action,
        pc,
        max_steps=W14B_FIXED_MAX_STEPS,
        checkpoints=W14B_CHECKPOINTS,
    )
    return solver.solve(rhs, scratch_dir=scratch_dir, observer=observer)


def evaluate_w14b_fixed4_gate(
    *,
    outer_audit: Mapping[str, Any],
    inner_audit: Mapping[str, Any],
    samples: Mapping[str, Mapping[str, Any]],
    action_audit: Mapping[str, Any],
    architecture: Mapping[str, Any],
    predicted_live_set: Mapping[str, Any],
    w14a_authority_ok: bool,
    source_ok: bool,
    cache_ok: bool,
) -> dict[str, Any]:
    """Recompute the fixed W14B Gate from scalar and checkpoint evidence."""

    checks = {
        "w14a_authority": bool(w14a_authority_ok is True),
        "outer": False,
        "checkpoints": False,
        "inner": False,
        "action_audit": False,
        "architecture": False,
        "lifecycle": False,
        "prediction": False,
        "rho1_anchor": False,
        "rho_monotone": False,
        "rho4": False,
        "source": bool(source_ok is True),
        "cache": bool(cache_ok is True),
    }
    rho_values: dict[str, float] = {}
    try:
        checks["outer"] = (
            outer_audit["algorithm"] == "right_flexible_gmres"
            and outer_audit["max_steps"] == W14B_FIXED_MAX_STEPS
            and outer_audit["iterations"] == W14B_FIXED_MAX_STEPS
            and outer_audit["checkpoint_iterations"] == list(W14B_CHECKPOINTS)
            and outer_audit["checkpoint_count"] == len(W14B_CHECKPOINTS)
            and outer_audit["checkpoint_set_complete"] is True
            and outer_audit["observer_count"] == 3
            and outer_audit["action_count"] == 7
            and outer_audit["pc_count"] == 4
            and outer_audit["initial_action_count"] == 0
            and outer_audit["orthogonalization_passes"] == 2
            and outer_audit["basis_in_memory"] is False
            and outer_audit["mmap"] is False
            and outer_audit["scratch_bytes"] == 25_027_488
            and outer_audit["scratch_mmap"] is False
            and outer_audit["scratch_basis_in_memory"] is False
            and outer_audit["bounded_full_vector_bytes"] <= 64 * 1024 * 1024
            and outer_audit["bounded_full_vector_gate"] is True
        )
        checks["checkpoints"] = (
            set(samples) == {str(value) for value in W14B_CHECKPOINTS}
            and all(
                isinstance(samples[str(iteration)]["iteration"], int)
                and samples[str(iteration)]["iteration"] == iteration
                and samples[str(iteration)]["finite"] is True
                and _finite_bounded(
                    samples[str(iteration)]["true_relative_residual"]
                )
                for iteration in W14B_CHECKPOINTS
            )
        )
        for iteration in W14B_CHECKPOINTS:
            rho_values[str(iteration)] = float(
                samples[str(iteration)]["true_relative_residual"]
            )
        algorithm = inner_audit["algorithm"]
        records = inner_audit["applications"]
        checks["inner"] = (
            algorithm["solver"] == "fgmres"
            and algorithm["restart"] == 20
            and algorithm["max_it"] == 20
            and algorithm["zero_start"] is True
            and algorithm["rtol"] == 0.0
            and algorithm["atol"] == 0.0
            and algorithm["pc_side"] == "right"
            and algorithm["mpi_size"] == 1
            and isinstance(records, Sequence)
            and not isinstance(records, (str, bytes))
            and len(records) == 4
            and all(
                record["algorithm"] == "fgmres_right_b0_fixed20"
                and record["iterations"] == 20
                and record["converged_reason"] == -3
                and record["pc_apply_count_delta"] == 20
                and record["finite"] is True
                and record["gate_pass"] is True
                and _finite_bounded(record["true_residual"], _W14_TRUE_RESIDUAL_LIMIT)
                for record in records
            )
            and inner_audit["underlying_pc"]["apply_count"] == 80
        )
        physical_instances = action_audit["physical_instances"]
        b0_instances = action_audit["b0_instances"]
        construction_outer = action_audit["outer"]
        construction_physical = action_audit["physical"]
        construction_dtn = action_audit["dtn"]
        construction_bridge = action_audit["bridge"]
        final_physical = physical_instances[0]
        b0 = b0_instances[0]
        final_outer = final_physical["outer"]
        final_physical_action = final_physical["physical"]
        final_dtn = final_physical["dtn"]
        final_bridge = final_physical["bridge"]
        checks["action_audit"] = (
            construction_outer["apply_count"] == 0
            and construction_physical["apply_count"] == 0
            and construction_dtn["apply_count"] == 0
            and construction_bridge["forward_apply_count"] == 0
            and len(physical_instances) == 1
            and len(b0_instances) == 1
            and b0["total_pc_apply_count"] == 80
            and b0["inner_pc"]["underlying_pc"]["apply_count"] == 80
            and final_physical["total_physical_action_count"] == 7
            and final_outer["apply_count"] == 7
            and final_outer["matrix_type"] == "python_action_only"
            and final_outer["global_matrix"] is False
            and final_outer["augmented_matrix"] is False
            and final_outer["static_condensation"] is False
            and final_outer["trace_slab"] is False
            and final_outer["explicit_C_materialized_count"] == 0
            and final_outer["explicit_D_materialized_count"] == 0
            and final_physical_action["apply_count"] == 7
            and final_physical_action["global_matrix_materialized"] is False
            and final_physical_action["global_constraint_matrix_materialized"] is False
            and final_physical_action["global_condensed_schur_materialized"] is False
            and final_physical_action["cell_schur_matrix_materialized"] is False
            and final_physical_action["slab_matrix_materialized"] is False
            and final_physical_action["retained_dense_cell_tensor_count"] == 0
            and final_physical_action["dense_cell_tensor_materialized_per_apply"] is False
            and final_physical_action["factor_count"] == 0
            and final_physical_action["ksp_created"] is False
            and final_physical_action["cell_schur_matrix_nnz"] == 0
            and final_physical_action["slab_matrix_nnz"] == 0
            and final_physical_action["explicit_C_materialized_count"] == 0
            and final_physical_action["explicit_D_materialized_count"] == 0
            and final_physical_action["ordinary_default_changed"] is False
            and final_dtn["apply_count"] == 7
            and final_dtn["mode_count"] == 80
            and final_dtn["fine_space"] == "uncondensed_fullspace"
            and final_dtn["condensation"] is False
            and final_dtn["static_condensed_operator_used"] is False
            and final_dtn["trace_slab_pc_used"] is False
            and final_dtn["global_matrix_materialized"] is False
            and final_dtn["augmented_matrix_materialized"] is False
            and final_dtn["explicit_C_materialized_count"] == 0
            and final_dtn["explicit_D_materialized_count"] == 0
            and final_dtn["fe_sized_allgather"] is False
            and final_dtn["modal_allreduce_count_per_apply"] == 1
            and final_dtn["modal_allreduce_count_per_hermitian_apply"] == 1
            and final_bridge["forward_apply_count"] == 7
            and final_bridge["vector_create_count"] == 2
            and final_bridge["fixed_work_vectors"] == 2
            and final_bridge["per_apply_vec_creation"] == 0
            and action_audit["authority_vector_retention"] == {
                "q_vector_retained": False,
                "retained_authority_vector_roles": ["target"],
            }
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
        checks["lifecycle"] = action_audit["lifecycle_events"] == [
            "b0_constructed",
            "physical_constructed",
            "coexistence_ready",
            "physical_released",
            "b0_released",
        ] and action_audit["coexistence"] == {
            "b0_live": True,
            "physical_live": True,
            "release_between_operations": False,
        }
        checks["prediction"] = (
            predicted_live_set["bytes"] == W14B_PREDICTED_LIVE_SET_BYTES
            and predicted_live_set["limit_bytes"] == W14B_PREDICTED_LIVE_SET_LIMIT_BYTES
            and predicted_live_set["gate"] is True
            and predicted_live_set["derived_not_measured"] is True
            and predicted_live_set["scratch_bytes"] == 25_027_488
        )
        checks["rho1_anchor"] = abs(
            rho_values["1"] - W14B_RHO1_ANCHOR
        ) <= W14B_RHO1_LIMIT
        checks["rho_monotone"] = (
            rho_values["1"] >= rho_values["2"] - W14B_MONOTONICITY_TOLERANCE
            and rho_values["2"] >= rho_values["4"] - W14B_MONOTONICITY_TOLERANCE
        )
        checks["rho4"] = rho_values["4"] <= W14B_RHO4_LIMIT
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(name for name, passed in checks.items() if not passed),
        "rho": rho_values,
    }


def evaluate_w15a_restart1_gate(
    *,
    inner_audit: Mapping[str, Any],
    z_identity: Mapping[str, Any],
    p_identity: Mapping[str, Any],
    measurement: Mapping[str, Any],
    p2_measurement: Mapping[str, Any],
    cumulative_rho: float,
    physical_action_count: int,
    architecture: Mapping[str, Any],
    lifecycle_events: Sequence[str],
    predicted_live_set: Mapping[str, Any],
    checkpoint_authority_ok: bool,
    source_ok: bool,
    cache_ok: bool,
) -> dict[str, Any]:
    """Recompute W14A's contract plus the fixed restart-1 rho gates."""

    base = evaluate_w14a_action_gate(
        inner_audit=inner_audit,
        z_identity=z_identity,
        p_identity=p_identity,
        measurement=measurement,
        p2_measurement=p2_measurement,
        physical_action_count=physical_action_count,
        architecture=architecture,
        lifecycle_events=lifecycle_events,
        predicted_live_set=predicted_live_set,
        source_ok=source_ok,
        cache_ok=cache_ok,
    )
    checks = dict(base)
    checks.update(
        {
            "checkpoint_authority": bool(checkpoint_authority_ok is True),
            "local_rho": False,
            "cumulative_rho": False,
        }
    )
    try:
        local_rho = float(measurement["rho"])
        expected_cumulative = W15A_RHO1_AUTHORITY * local_rho
        checks["local_rho"] = _finite_bounded(local_rho, W15A_RHO_LIMIT)
        checks["cumulative_rho"] = (
            _finite_bounded(cumulative_rho, W15A_CUMULATIVE_RHO_LIMIT)
            and abs(float(cumulative_rho) - expected_cumulative) <= 1.0e-12
        )
    except (KeyError, TypeError, ValueError):
        pass
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(name for name, passed in checks.items() if not passed),
        "cumulative_rho": float(cumulative_rho)
        if isinstance(cumulative_rho, (int, float))
        else None,
    }


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
        """Apply fixed B0 FGMRES and record, but do not enforce, qualification.

        A finite solution whose true residual exceeds the fixed qualification
        limit remains mathematically usable by the outer flexible-GMRES cycle;
        the W14 evaluator consumes ``gate_pass`` and fails qualification
        closed.  Non-finite output is still an immediate execution failure.
        """

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
        if not finite:
            del solution
            raise RuntimeError("W14 B0 inner solve produced non-finite output")
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
