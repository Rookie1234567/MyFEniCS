"""Action-only Hybrid block-LDU preconditioner and tight iterative solve."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve, solve_triangular
from scipy.linalg import qr as pivoted_qr

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from .hybrid_fem_modal_schur_direct import modal_coupling_action
from .task041_modal_policy import (
    _TASK041_V12_MODAL_BACKUP_POLICY,
    _TASK041_V12_MODAL_SOLVER_POLICY,  # noqa: F401 - compatibility re-export
    _TASK041_V13_CONSISTENT_MODAL_POLICY,
    TASK041_V12_MODAL_BACKUP_POLICY_ID,
    TASK041_V12_MODAL_BACKUP_QUALIFICATION_METHOD,  # noqa: F401 - compatibility re-export
    TASK041_V12_MODAL_SOLVER_POLICY_ID,  # noqa: F401 - compatibility re-export
    TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
    resolve_task041_modal_solver_policy,
)

__all__ = (
    "HybridActionModalSchurApply",
    "HybridActionModalSchurSystem",
    "HybridBlockLduIterativeConfig",
    "HybridBlockLduIterativeResult",
    "HybridBlockLduPreconditioner",
    "Task041V13ConsistentModalSurrogateSystem",
    "build_hybrid_action_modal_schur",
    "build_task041_v13_consistent_modal_surrogate",
    "create_action_block_ldu_preconditioner",
    "create_research_exact_side_lu_block_ldu_preconditioner",
    "create_side_balh_block_ldu_preconditioner",
    "multimetric_true_residual_decision",
    "solve_action_modal_schur_anderson",
    "solve_hybrid_block_ldu_iterative",
)

_TINY = np.finfo(float).tiny
_RESIDUAL_KEYS = (
    "reported_relative_residual",
    "global_true_relative_residual",
    "bottom_true_relative_residual",
    "top_true_relative_residual",
    "modal_true_relative_residual",
)
_MODAL_ANDERSON_S_EVALUATION_LIMIT = 16
_MODAL_SOLVE_TRACE_SOLVE_LIMIT = 2
_MODAL_SOLVE_TRACE_EVALUATION_LIMIT = 16
_MODAL_SOLVE_TRACE_HISTORY_LIMIT = 4
_MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES = 640 * 1024


def _v13_complex_magnitudes(values: np.ndarray) -> np.ndarray:
    """Return complex moduli using hypot, avoiding square/sum overflow."""

    array = np.asarray(values, dtype=np.complex128)
    return np.hypot(array.real, array.imag)


def _v13_log_l2_from_magnitudes(values: np.ndarray) -> float:
    magnitudes = np.asarray(values, dtype=np.float64)
    if magnitudes.size == 0:
        return float("-inf")
    if not np.isfinite(magnitudes).all():
        return float("inf")
    maximum = float(np.max(magnitudes))
    if maximum == 0.0:
        return float("-inf")
    scaled = magnitudes / maximum
    return math.log(maximum) + 0.5 * math.log(
        math.fsum(float(value) * float(value) for value in scaled)
    )


def _v13_log_l2_from_logs(log_magnitudes: Sequence[float]) -> float:
    finite = [float(value) for value in log_magnitudes if value != float("-inf")]
    if not finite:
        return float("-inf")
    if any(not math.isfinite(value) for value in finite):
        return float("inf")
    maximum = max(finite)
    return maximum + 0.5 * math.log(
        math.fsum(math.exp(2.0 * (value - maximum)) for value in finite)
    )


def _v13_log_sum(log_values: Sequence[float]) -> float:
    finite = [float(value) for value in log_values if value != float("-inf")]
    if not finite:
        return float("-inf")
    if any(not math.isfinite(value) for value in finite):
        return float("inf")
    maximum = max(finite)
    return maximum + math.log(
        math.fsum(math.exp(value - maximum) for value in finite)
    )


def _v13_float_norm_from_log(log_norm: float) -> float | None:
    """Return an absolute norm when representable; retain the log otherwise."""

    value = float(log_norm)
    if value == float("-inf"):
        return 0.0
    if not math.isfinite(value):
        return None
    if value > math.log(np.finfo(np.float64).max):
        return None
    if value < math.log(float(np.nextafter(0.0, 1.0))):
        return None
    return math.exp(value)


def _v13_ratio_from_logs(numerator_log: float, denominator_log: float) -> float:
    if numerator_log == float("-inf"):
        return 0.0
    if denominator_log == float("-inf"):
        return float("inf")
    if not math.isfinite(numerator_log) or not math.isfinite(denominator_log):
        return float("inf")
    difference = numerator_log - denominator_log
    if difference > math.log(np.finfo(np.float64).max):
        return float("inf")
    if difference < math.log(float(np.nextafter(0.0, 1.0))):
        return 0.0
    return math.exp(difference)


_V15_ORIGINAL_MODAL_ROW_CONTRACT = "task041.v15.original_modal_row.terms_backward.v1"
_V13_ORIGINAL_MODAL_ROW_LEGACY_SCHEMA = "task041.v13.original_modal_row_capture.v1"


def _v13_original_modal_row_metrics(
    r_modal: np.ndarray,
    w_modal: np.ndarray,
    t_bottom: np.ndarray,
    t_top: np.ndarray,
    t_constraint: np.ndarray,
    *,
    tolerance: float = 1.0e-10,
) -> tuple[dict[str, Any], np.ndarray]:
    """Evaluate the V15 componentwise modal-row backward error.

    The stored residual is computed first as the actual binary64 complex
    subtraction ``w_modal - r_modal``.  Each row is then scaled independently
    only for evaluating its ratio; the captured residual itself is never
    replaced by a scaled surrogate.
    """

    names = ("r_modal", "w_modal", "t_bottom", "t_top", "t_constraint")
    arrays = {
        name: np.asarray(value, dtype=np.complex128)
        for name, value in zip(
            names,
            (r_modal, w_modal, t_bottom, t_top, t_constraint),
            strict=True,
        )
    }
    shape = arrays["r_modal"].shape
    shape_ok = (
        len(shape) == 1
        and shape[0] > 0
        and all(value.shape == shape for value in arrays.values())
    )
    if not shape_ok:
        return (
            {
                "contract_id": _V15_ORIGINAL_MODAL_ROW_CONTRACT,
                "legacy_schema": _V13_ORIGINAL_MODAL_ROW_LEGACY_SCHEMA,
                "status": "rejected",
                "valid": False,
                "reason": "shape_mismatch",
                "shape_by_field": {name: list(value.shape) for name, value in arrays.items()},
                "tolerance": float(tolerance),
            },
            np.empty((0,), dtype=np.complex128),
        )

    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        residual = np.subtract(arrays["w_modal"], arrays["r_modal"])
    finite_inputs = all(np.isfinite(value).all() for value in arrays.values())
    residual_representable = bool(np.isfinite(residual).all())
    exact_zero_rhs = bool(np.all(arrays["r_modal"] == 0.0))
    base: dict[str, Any] = {
        "contract_id": _V15_ORIGINAL_MODAL_ROW_CONTRACT,
        "legacy_schema": _V13_ORIGINAL_MODAL_ROW_LEGACY_SCHEMA,
        "equation": "w_modal - r_modal = t_bottom + t_top + t_constraint - r_modal",
        "tolerance": float(tolerance),
        "rhs_exact_zero": exact_zero_rhs,
        "finite_inputs": bool(finite_inputs),
        "residual_representable": residual_representable,
        "residual": residual.copy(),
        "absolute_l2_norms": None,
        "absolute_l2_log_norms": None,
        "absolute_l2_norms_scope": (
            "unavailable until all captured binary64 components are finite"
        ),
    }
    if not finite_inputs or not residual_representable:
        base.update(
            {
                "status": "rejected",
                "valid": False,
                "reason": (
                    "non_finite_component"
                    if not finite_inputs
                    else "unrepresentable_binary64_residual"
                ),
                "eta_terms_inf": None,
                "eta_terms_2": None,
                "eta_terms_2_denominator_log_norms": None,
                "legacy_rhs_relative_error": None,
                "legacy_rhs_relative_status": (
                    "not_defined" if exact_zero_rhs else "unavailable"
                ),
                "decomposition_eta_terms_inf": None,
                "decomposition_passed": False,
                "decomposition_metrics_valid": False,
                "decomposition_exact": None,
            }
        )
        return base, residual.copy()

    magnitudes = {
        name: _v13_complex_magnitudes(value)
        for name, value in arrays.items()
    }
    residual_magnitudes = _v13_complex_magnitudes(residual)
    if not all(np.isfinite(value).all() for value in magnitudes.values()) or not np.isfinite(
        residual_magnitudes
    ).all():
        base.update(
            {
                "status": "rejected",
                "valid": False,
                "reason": "non_finite_complex_modulus",
                "eta_terms_inf": None,
                "eta_terms_2": None,
                "eta_terms_2_denominator_log_norms": None,
                "legacy_rhs_relative_error": None,
                "legacy_rhs_relative_status": (
                    "not_defined" if exact_zero_rhs else "unavailable"
                ),
                "decomposition_eta_terms_inf": None,
                "decomposition_passed": False,
                "decomposition_metrics_valid": False,
                "decomposition_exact": None,
            }
        )
        return base, residual.copy()

    row_scale = np.maximum.reduce(
        [
            residual_magnitudes,
            magnitudes["t_bottom"],
            magnitudes["t_top"],
            magnitudes["t_constraint"],
            magnitudes["r_modal"],
        ]
    )
    denominator_scaled = np.zeros(shape, dtype=np.float64)
    row_relative = np.zeros(shape, dtype=np.float64)
    row_relative_log = np.full(shape, float("-inf"), dtype=np.float64)
    row_denominator_log = np.full(shape, float("-inf"), dtype=np.float64)
    invalid_rows: list[int] = []
    for index, scale in enumerate(row_scale):
        scale_value = float(scale)
        numerator = float(residual_magnitudes[index])
        if scale_value == 0.0:
            if numerator != 0.0:
                invalid_rows.append(index)
                row_relative[index] = float("inf")
            else:
                row_relative[index] = 0.0
            continue
        scaled_sum = math.fsum(
            float(magnitudes[name][index] / scale_value)
            for name in ("t_bottom", "t_top", "t_constraint", "r_modal")
        )
        denominator_scaled[index] = scaled_sum
        if scaled_sum == 0.0:
            if numerator != 0.0:
                invalid_rows.append(index)
                row_relative[index] = float("inf")
            else:
                row_relative[index] = 0.0
            continue
        row_denominator_log[index] = math.log(scale_value) + math.log(scaled_sum)
        if numerator > 0.0:
            row_relative_log[index] = (
                math.log(numerator) - row_denominator_log[index]
            )
        row_relative[index] = _v13_ratio_from_logs(
            float(row_relative_log[index]), 0.0
        )

    maximum_row = (
        int(np.argmax(row_relative)) if row_relative.size else None
    )
    eta_terms_inf = (
        float(row_relative[maximum_row]) if maximum_row is not None else 0.0
    )

    residual_log_norm = _v13_log_l2_from_magnitudes(residual_magnitudes)
    absolute_l2_log_norms = {
        "r_modal": _v13_log_l2_from_magnitudes(magnitudes["r_modal"]),
        "w_modal": _v13_log_l2_from_magnitudes(magnitudes["w_modal"]),
        "d_w_minus_r": residual_log_norm,
        "t_bottom": _v13_log_l2_from_magnitudes(magnitudes["t_bottom"]),
        "t_top": _v13_log_l2_from_magnitudes(magnitudes["t_top"]),
        "t_constraint": _v13_log_l2_from_magnitudes(
            magnitudes["t_constraint"]
        ),
    }
    absolute_l2_norms = {
        name: _v13_float_norm_from_log(log_norm)
        for name, log_norm in absolute_l2_log_norms.items()
    }
    # The contract denominator is the sum of each component vector's L2 norm.
    # This is intentionally not the L2 norm of the rowwise component magnitudes
    # added together; the Decimal oracle test distinguishes the two.
    eta_terms_2_denominator_log_norms = {
        name: _v13_log_l2_from_magnitudes(magnitudes[name])
        for name in ("t_bottom", "t_top", "t_constraint", "r_modal")
    }
    eta_terms_2_denominator_log = _v13_log_sum(
        list(eta_terms_2_denominator_log_norms.values())
    )
    eta_terms_2 = _v13_ratio_from_logs(
        residual_log_norm, eta_terms_2_denominator_log
    )
    rhs_log_norm = _v13_log_l2_from_magnitudes(magnitudes["r_modal"])
    legacy_rhs_relative_error = (
        None
        if exact_zero_rhs
        else _v13_ratio_from_logs(residual_log_norm, rhs_log_norm)
    )
    legacy_side_norm_log = _v13_log_l2_from_logs(
        [
            _v13_log_l2_from_magnitudes(magnitudes[name])
            for name in ("t_bottom", "t_top")
        ]
    )
    legacy_zero_terms_norm_log = _v13_log_sum(
        [
            legacy_side_norm_log,
            _v13_log_l2_from_magnitudes(magnitudes["t_constraint"]),
        ]
    )
    legacy_rhs_relative_status = (
        "not_defined"
        if exact_zero_rhs
        else (
            "passed"
            if legacy_rhs_relative_error is not None
            and legacy_rhs_relative_error <= tolerance
            else "rejected"
        )
    )
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        decomposition = arrays["t_constraint"].copy()
        decomposition += arrays["t_bottom"]
        decomposition += arrays["t_top"]
        decomposition_difference = np.subtract(arrays["w_modal"], decomposition)
    decomposition_magnitudes = _v13_complex_magnitudes(decomposition_difference)
    decomposition_finite = bool(
        np.isfinite(decomposition_difference).all()
        and np.isfinite(decomposition_magnitudes).all()
    )
    decomposition_exact = bool(
        decomposition_finite
        and np.array_equal(
            decomposition_difference, np.zeros_like(decomposition_difference)
        )
    )
    decomposition_row_relative = np.zeros(shape, dtype=np.float64)
    decomposition_row_relative_log = np.full(shape, float("-inf"), dtype=np.float64)
    decomposition_invalid_rows: list[int] = []
    if decomposition_finite:
        for index, difference_magnitude in enumerate(decomposition_magnitudes):
            denominator_log = float(row_denominator_log[index])
            numerator = float(difference_magnitude)
            if denominator_log == float("-inf"):
                if numerator != 0.0:
                    decomposition_invalid_rows.append(index)
                    decomposition_row_relative[index] = float("inf")
                else:
                    decomposition_row_relative[index] = 0.0
                continue
            if numerator > 0.0:
                decomposition_row_relative_log[index] = (
                    math.log(numerator) - denominator_log
                )
            decomposition_row_relative[index] = _v13_ratio_from_logs(
                float(decomposition_row_relative_log[index]), 0.0
            )
    decomposition_eta_terms_inf = (
        float(np.max(decomposition_row_relative))
        if decomposition_row_relative.size and decomposition_finite
        else None
    )
    decomposition_metrics_valid = bool(
        decomposition_finite
        and not decomposition_invalid_rows
        and decomposition_eta_terms_inf is not None
        and math.isfinite(decomposition_eta_terms_inf)
    )
    decomposition_passed = bool(
        decomposition_metrics_valid
        and decomposition_eta_terms_inf is not None
        and decomposition_eta_terms_inf <= tolerance
    )
    decomposition_max = (
        float(np.max(decomposition_magnitudes))
        if decomposition_difference.size and decomposition_finite
        else (0.0 if decomposition_finite else None)
    )
    valid = bool(
        finite_inputs
        and residual_representable
        and not invalid_rows
        and np.isfinite(eta_terms_inf)
        and np.isfinite(eta_terms_2)
    )
    passed = bool(valid and eta_terms_inf <= tolerance)
    denominator_at_max = None
    if maximum_row is not None and row_scale[maximum_row] > 0.0:
        denominator_at_max = {
            "scale": float(row_scale[maximum_row]),
            "scaled_sum": float(denominator_scaled[maximum_row]),
            "reconstructs_as": "scale * scaled_sum",
        }
    base.update(
        {
            "status": "passed" if passed else "rejected",
            "valid": valid,
            "reason": (
                None
                if valid
                else (
                    "zero_denominator_with_nonzero_residual"
                    if invalid_rows
                    else "non_finite_metric_or_decomposition"
                )
            ),
            "eta_terms_inf": eta_terms_inf,
            "eta_terms_2": eta_terms_2,
            "absolute_l2_norms": absolute_l2_norms,
            "absolute_l2_log_norms": absolute_l2_log_norms,
            "absolute_l2_norms_scope": (
                "binary64 captured arrays; null absolute value means outside "
                "binary64 range; stable natural-log norm remains available"
            ),
            "legacy_rhs_relative_error": legacy_rhs_relative_error,
            "legacy_rhs_relative_status": legacy_rhs_relative_status,
            "eta_terms_2_denominator_formula": (
                "||t_bottom||_2 + ||t_top||_2 + ||t_constraint||_2 + ||r_modal||_2"
            ),
            "eta_terms_2_denominator_log_norms": eta_terms_2_denominator_log_norms,
            "eta_terms_2_denominator_log": eta_terms_2_denominator_log,
            "legacy_exact_zero_terms_relative": (
                _v13_ratio_from_logs(
                    residual_log_norm,
                    legacy_zero_terms_norm_log,
                )
                if exact_zero_rhs and legacy_zero_terms_norm_log != float("-inf")
                else None
            ),
            "max_row_index": maximum_row,
            "max_row_relative_error": eta_terms_inf,
            "max_row_numerator": (
                None
                if maximum_row is None
                else float(residual_magnitudes[maximum_row])
            ),
            "max_row_denominator": denominator_at_max,
            "row_scale": row_scale.copy(),
            "row_denominator_scaled": denominator_scaled.copy(),
            "row_relative_error": row_relative.copy(),
            "row_relative_log_error": row_relative_log.copy(),
            "zero_denominator_rows": invalid_rows,
            "decomposition_error": decomposition_difference.copy(),
            "decomposition_row_relative_error": decomposition_row_relative.copy(),
            "decomposition_row_relative_log_error": decomposition_row_relative_log.copy(),
            "decomposition_zero_denominator_rows": decomposition_invalid_rows,
            "decomposition_eta_terms_inf": decomposition_eta_terms_inf,
            "decomposition_passed": decomposition_passed,
            "decomposition_metrics_valid": decomposition_metrics_valid,
            "decomposition_max_abs_difference": decomposition_max,
            "decomposition_exact": decomposition_exact,
            "decomposition_exact_is_observation_only": True,
            "decomposition_finite": decomposition_finite,
            "decomposition_gate_tolerance": float(tolerance),
            "decomposition_gate_applies_to": "decomposition_eta_terms_inf",
            "decomposition_operation_order": "((t_constraint + t_bottom) + t_top)",
            "tolerance_applied_to": "eta_terms_inf",
        }
    )
    return base, residual.copy()


class _V13OriginalCaptureFailure(RuntimeError):
    """An original-A capture failure tagged with its collective safety point."""

    def __init__(self, message: str, *, safe_to_collective: bool):
        super().__init__(message)
        self.safe_to_collective = bool(safe_to_collective)


def _v13_json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _v13_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_v13_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return {"shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, np.generic):
        return _v13_json_safe(value.item())
    if isinstance(value, complex):
        return {"real": _v13_json_safe(float(value.real)), "imag": _v13_json_safe(float(value.imag))}
    if isinstance(value, float) and not math.isfinite(value):
        label = "NaN" if math.isnan(value) else ("+Inf" if value > 0 else "-Inf")
        return {"value": None, "nonfinite": label}
    return value


def _task041_v12_capacity_gate_has_byte_refusal(gate: Any) -> bool:
    """Accept only a fresh, complete, numerically evidenced W0.7 refusal."""

    if (
        not isinstance(gate, Mapping)
        or gate.get("schema") != "task041.v12.side_restart_memory_gate.v1"
        or gate.get("pass") is not False
        or gate.get("status") != "refused"
        or gate.get("phase")
        not in {
            "capture_restart32_rhs",
            "allocate_restart64",
            "restore_restart32",
        }
    ):
        return False
    fresh = gate.get("fresh_B_bytes")
    delta = gate.get("delta_bytes")
    reserve = gate.get("W_policy_reserve_bytes")
    cap = gate.get("cap_bytes")
    screened = gate.get("screened_B_plus_delta_plus_W_bytes")
    if any(
        type(value) is not int or value < 0
        for value in (fresh, delta, reserve, cap, screened)
    ):
        return False
    if (
        screened != fresh + delta + reserve
        or cap != 85_899_345_920
        or reserve != 8_589_934_592
        or type(gate.get("floor_bytes")) is not int
        or gate["floor_bytes"] != 412_316_860_416
        or delta <= 0
        or gate.get("side") not in {"bottom", "top"}
        or gate.get("restart")
        != (
            32
            if gate.get("phase")
            in {"capture_restart32_rhs", "restore_restart32"}
            else 64
        )
    ):
        return False
    resource = gate.get("resource")
    supervisor = gate.get("supervisor_sample")
    if not isinstance(resource, Mapping) or not isinstance(supervisor, Mapping):
        return False
    root_pid = resource.get("root_pid")
    tree_rss = resource.get("tree_rss_bytes")
    cgroup_current = resource.get("cgroup_current_bytes")
    source_sha = supervisor.get("source_sha")
    invocation_id = supervisor.get("invocation_id")
    unit = supervisor.get("unit")
    age = supervisor.get("file_age_seconds")
    if (
        type(root_pid) is not int
        or root_pid <= 0
        or type(tree_rss) is not int
        or tree_rss < 0
        or type(cgroup_current) is not int
        or cgroup_current < 0
        or resource.get("B_bytes") != max(tree_rss, cgroup_current)
        or fresh != max(tree_rss, cgroup_current)
        or not isinstance(resource.get("tree_pids"), list)
        or not isinstance(supervisor.get("process_tree_pids"), list)
        or supervisor.get("sample_root_pid") != root_pid
        or supervisor.get("sample_role") != "phase_running"
        or supervisor.get("phase") != "public_command"
        or not isinstance(invocation_id, str)
        or not invocation_id
        or not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(character not in "0123456789abcdef" for character in source_sha)
        or not isinstance(unit, str)
        or not unit.endswith(".service")
        or type(age) not in (int, float)
        or isinstance(age, bool)
        or not math.isfinite(float(age))
        or not 0.0 <= float(age) <= 2.0
        or gate.get("authority")
        != (
            "fresh max(process-tree RSS,cgroup memory.current) bound to the explicit per-rank "
            "phase object inventory; destroyed workspaces receive no credit except as reflected in this sample"
        )
    ):
        return False
    rank_rows = gate.get("rank_layout")
    if not isinstance(rank_rows, list) or len(rank_rows) != 8:
        return False
    rank_pids = []
    rank_cpus = []
    local_sizes = []
    operator_row_sizes = []
    operator_column_sizes = []
    ranges = []
    global_sizes = []
    for rank, row in enumerate(rank_rows):
        if not isinstance(row, Mapping) or row.get("rank") != rank:
            return False
        pid = row.get("pid")
        cpu = row.get("expected_cpu")
        affinity = row.get("affinity")
        local_size = row.get("local_vector_size")
        local_operator_rows = row.get("operator_local_rows")
        local_operator_columns = row.get("operator_local_columns")
        global_size = row.get("rhs_global_size")
        ownership = row.get("rhs_ownership_range")
        phase = gate.get("phase")
        lifecycle_by_phase = {
            "capture_restart32_rhs": "restart32_ksp_live_plus_source_rhs_before_candidate_copy",
            "allocate_restart64": "restart32_ksp_destroyed_plus_candidate_rhs_live_plus_full_new_restart64_workspace",
            "restore_restart32": "restart64_ksp_and_candidate_rhs_destroyed_plus_full_new_restart32_workspace",
        }
        expected_lifecycle = lifecycle_by_phase.get(phase)
        expected_restart32_live = phase == "capture_restart32_rhs"
        expected_candidate_live = phase == "allocate_restart64"
        local_sha = row.get("rhs_local_sha256")
        if (
            type(pid) is not int
            or pid <= 0
            or type(cpu) is not int
            or not isinstance(affinity, list)
            or affinity != [cpu]
            or type(local_size) is not int
            or local_size < 0
            or type(local_operator_rows) is not int
            or local_operator_rows < 0
            or type(local_operator_columns) is not int
            or local_operator_columns != local_size
            or type(global_size) is not int
            or global_size < 0
            or not isinstance(ownership, list)
            or len(ownership) != 2
            or any(type(value) is not int for value in ownership)
            or ownership[1] - ownership[0] != local_size
            or row.get("side") != gate.get("side")
            or row.get("phase") != gate.get("phase")
            or row.get("restart") != gate.get("restart")
            or row.get("workspace_lifecycle")
            != expected_lifecycle
            or row.get("existing_restart32_ksp_live")
            is not expected_restart32_live
            or row.get("restart64_trial_ksp_live") is not False
            or row.get("candidate_rhs_live") is not expected_candidate_live
            or row.get("existing_restart32_restart") != 32
            or not isinstance(local_sha, str)
            or len(local_sha) != 64
            or any(character not in "0123456789abcdef" for character in local_sha)
        ):
            return False
        rank_pids.append(pid)
        rank_cpus.append(cpu)
        local_sizes.append(local_size)
        operator_row_sizes.append(local_operator_rows)
        operator_column_sizes.append(local_operator_columns)
        global_sizes.append(global_size)
        ranges.append(ownership)
    if (
        len(set(rank_pids)) != len(rank_pids)
        or len(set(rank_cpus)) != len(rank_cpus)
        or len(set(global_sizes)) != 1
        or any(ranges[index][1] != ranges[index + 1][0] for index in range(len(ranges) - 1))
        or ranges[0][0] != 0
        or ranges[-1][1] != global_sizes[0]
        or sum(local_sizes) != global_sizes[0]
        or sum(operator_row_sizes) != global_sizes[0]
        or sum(operator_column_sizes) != global_sizes[0]
        or not set(rank_pids).issubset(set(resource["tree_pids"]))
        or not set(rank_pids).issubset(set(supervisor["process_tree_pids"]))
        or root_pid not in resource["tree_pids"]
        or root_pid not in supervisor["process_tree_pids"]
    ):
        return False

    required = delta + reserve
    evidence = gate.get("external_headroom_byte_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("required_bytes") != required:
        return False
    floor = gate.get("floor_bytes")
    pointer_bytes_each = gate.get("pointer_bytes_each")
    if type(pointer_bytes_each) is not int or pointer_bytes_each not in (4, 8, 16):
        return False
    node0_free = gate.get("node0_memfree_bytes")
    host_available = resource.get("host_available_bytes")
    cgroup_state = resource.get("cgroup_limit_state")
    cgroup_headroom = resource.get("cgroup_headroom_bytes")
    if (
        type(node0_free) is not int
        or node0_free < 0
        or type(host_available) is not int
        or host_available < 0
        or cgroup_state not in {"finite", "max_or_unlimited"}
        or (
            cgroup_state == "finite"
            and (type(cgroup_headroom) is not int or cgroup_headroom < 0)
        )
        or (
            cgroup_state == "max_or_unlimited"
            and cgroup_headroom is not None
        )
    ):
        return False
    node0_after_floor = node0_free - floor
    host_after_floor = host_available - floor
    external_available = [
        ("node0_MemFree_after_floor", node0_after_floor),
        ("host_MemAvailable_after_floor", host_after_floor),
    ]
    if cgroup_state == "finite":
        external_available.append(("ancestor_cgroup_headroom", cgroup_headroom))
    else:
        external_available.append(("ancestor_cgroup_headroom", required))
    expected_shortages = [
        {
            "authority": authority,
            "available_after_floor_bytes": available,
            "shortfall_bytes": required - available,
        }
        for authority, available in external_available
        if available < required
    ]
    observed_shortages = evidence.get("shortages")
    if observed_shortages != expected_shortages:
        return False
    m = gate.get("restart")
    total_local_entries = sum(local_sizes)
    if gate.get("phase") == "capture_restart32_rhs":
        if m != 32:
            return False
        expected_vectors = 1
        expected_breakdown = {
            "basis_vectors": 0,
            "preconditioned_vectors": 0,
            "auxiliary_vectors": 0,
            "trial_solution_vectors": 0,
            "future_apply_output_vectors": 0,
            "simultaneous_true_residual_vectors": 0,
            "captured_rhs_vectors": 1,
        }
        expected_vector_payload = total_local_entries * 16
        expected_vector_components = {"captured_rhs": expected_vector_payload}
        expected_scalars = 0
        expected_pointers = 0
    else:
        if m not in (32, 64) or pointer_bytes_each not in (4, 8, 16):
            return False
        expected_vectors = (m + 1) + m + 8 + 1 + 2
        expected_breakdown = {
            "basis_vectors": m + 1,
            "preconditioned_vectors": m,
            "auxiliary_vectors": 8,
            "trial_solution_vectors": 1 if m == 64 else 0,
            "future_apply_output_vectors": 1 if m == 32 else 0,
            "simultaneous_true_residual_vectors": 2,
            "captured_rhs_vectors": 0,
        }
        expected_vector_components = {
            "basis": (m + 1) * sum(operator_row_sizes) * 16,
            "preconditioned_basis": m * sum(operator_column_sizes) * 16,
            "auxiliary_vecs_max_layout": (
                8
                * sum(
                    max(rows, columns)
                    for rows, columns in zip(
                        operator_row_sizes,
                        operator_column_sizes,
                        strict=True,
                    )
                )
                * 16
            ),
            **(
                {"trial_solution": sum(operator_column_sizes) * 16}
                if m == 64
                else {
                    "future_apply_output": sum(operator_column_sizes) * 16
                }
            ),
            "explicit_residual_operator_output": sum(operator_row_sizes) * 16,
            "explicit_residual_rhs_copy": sum(operator_column_sizes) * 16,
        }
        expected_vector_payload = sum(expected_vector_components.values())
        expected_scalars = (
            (m + 2) * (m + 1)
            + (m + 1) * (m + 1)
            + (m + 2)
            + (m + 1)
            + (m + 1)
            + m
            + (m + 2)
            + (m + 2)
        )
        expected_pointers = (m + 4) + (m + 2)
    expected_scalar_bytes = expected_scalars * 16
    expected_pointer_bytes = expected_pointers * pointer_bytes_each
    expected_delta = expected_vector_payload + len(rank_rows) * (
        expected_scalar_bytes + expected_pointer_bytes
    )
    if (
        gate.get("vector_count") != expected_vectors
        or gate.get("vector_breakdown") != expected_breakdown
        or gate.get("local_vector_entries_sum") != total_local_entries
        or gate.get("local_operator_row_entries_sum")
        != sum(operator_row_sizes)
        or gate.get("local_operator_column_entries_sum")
        != sum(operator_column_sizes)
        or gate.get("vector_payload_bytes") != expected_vector_payload
        or gate.get("vector_payload_components_bytes")
        != expected_vector_components
        or gate.get("scalar_array_count_per_rank") != expected_scalars
        or gate.get("scalar_array_bytes_per_rank") != expected_scalar_bytes
        or gate.get("workspace_pointer_count_per_rank") != expected_pointers
        or gate.get("workspace_pointer_bytes_per_rank") != expected_pointer_bytes
        or gate.get("delta_bytes") != expected_delta
        or gate.get("required_bytes_including_W") != required
    ):
        return False
    expected_external_reasons = []
    if node0_after_floor < required or host_after_floor < required:
        expected_external_reasons.append("host/node0 reserve headroom is insufficient")
    if cgroup_state == "finite" and cgroup_headroom < required:
        expected_external_reasons.append("cgroup ancestor headroom is insufficient or unknown")
    expected_reasons = list(expected_external_reasons)
    if screened > cap:
        expected_reasons.append("fresh B + full new KSP workspace + W exceeds case cap")
    reasons = gate.get("reasons")
    if not expected_reasons or reasons != expected_reasons:
        return False
    byte_evidence_errors = evidence.get("insufficient_or_unknown_reasons")
    if byte_evidence_errors != expected_external_reasons:
        return False
    if any(
        not isinstance(item, Mapping)
        or type(item.get("available_after_floor_bytes")) is not int
        or type(item.get("shortfall_bytes")) is not int
        or item.get("shortfall_bytes") != required - item.get("available_after_floor_bytes")
        or item.get("shortfall_bytes") <= 0
        for item in observed_shortages
    ):
        return False
    return bool(screened > cap or expected_shortages)


def _task041_modal_policy_allows_backup(policy: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(policy, Mapping)
        and policy.get("policy_id") == TASK041_V12_MODAL_BACKUP_POLICY_ID
        and policy.get("primary_method") == "fixed_h6_modal_gmres_research"
        and policy.get("backup_method")
        == "fixed_physical_balh_once_modal_gmres_research"
        and policy.get("maximum_backup_switches") == 1
    )


class _ModalNormalReturnBackupEligible(RuntimeError):
    """A trusted completed primary modal solve declined by the sealed eta gate."""

    def __init__(self, record: Mapping[str, Any]) -> None:
        self.record = dict(record)
        super().__init__("primary modal result is not PC-usable; one backup may be tried")


_MODAL_BACKUP_RANK_LOCAL_SOLVE_FIELDS = (
    "local_constraint_lu_factorizations",
    "local_constraint_lu_solve_attempts",
    "local_constraint_lu_solve_successes",
    "cumulative_constraint_lu_solve_attempts",
    "cumulative_constraint_lu_solve_successes",
    "fixed_h6_side_action_apply_calls",
    "modal_feedback_side_action_apply_calls",
)


def _collective_modal_backup_primary_record(
    comm: Any,
    diagnostics: Mapping[str, Any],
    *,
    require_backup_eligible: bool = True,
) -> dict[str, Any]:
    """Bind common primary-return facts and retain rank-local work separately."""

    last_solve = diagnostics.get("last_solve")
    local_error = None
    common_json = None
    local_json = None
    try:
        if not isinstance(last_solve, Mapping):
            raise TypeError("primary modal diagnostics lack last_solve")
        required = (
            "status",
            "ksp_reason",
            "ksp_status",
            "iterations",
            "raw_residual_pass",
            "final_relative_residual",
            "final_residual_evaluated",
            "pc_usable",
        )
        if require_backup_eligible:
            required += (
                "trusted_iterate",
                "input_unchanged",
                "backup_eligibility",
                "normal_primary_return_completed",
            )
        missing = [key for key in required if key not in last_solve]
        if missing:
            raise ValueError(
                "primary modal record lacks " + ", ".join(missing)
            )
        if require_backup_eligible:
            if (
                last_solve.get("status")
                != "PRIMARY_MODAL_TARGET_NOT_MET_BACKUP_ELIGIBLE"
                or last_solve.get("normal_primary_return_completed") is not True
                or last_solve.get("pc_usable") is not False
                or last_solve.get("trusted_iterate") is not True
                or last_solve.get("input_unchanged") is not True
                or last_solve.get("raw_residual_pass") is not False
                or last_solve.get("final_residual_evaluated") is not True
            ):
                raise ValueError("primary modal record is not an eligible normal return")
            eligibility = last_solve.get("backup_eligibility")
            if not isinstance(eligibility, Mapping) or eligibility.get("eligible") is not True:
                raise ValueError("primary modal record lacks exact backup eligibility")
        local_values = {
            key: last_solve.get(key)
            for key in _MODAL_BACKUP_RANK_LOCAL_SOLVE_FIELDS
        }
        local_values.update(
            rank=int(comm.rank),
            local_solver_matmult_calls=int(diagnostics.get("solver_matmult_calls", -1)),
            local_total_matmult_calls=int(diagnostics.get("total_matmult_calls", -1)),
        )
        local_required = (
            "local_constraint_lu_factorizations",
            "local_constraint_lu_solve_attempts",
            "local_constraint_lu_solve_successes",
        )
        if any(local_values.get(key) is None for key in local_required):
            raise ValueError("primary modal rank-local LU work is incomplete")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for key, value in local_values.items()
            if key not in {"fixed_h6_side_action_apply_calls", "modal_feedback_side_action_apply_calls"}
            and value is not None
        ):
            raise ValueError("primary modal rank-local counters are invalid")
        if any(
            value is not None and not isinstance(value, Mapping)
            for key, value in local_values.items()
            if key in {"fixed_h6_side_action_apply_calls", "modal_feedback_side_action_apply_calls"}
        ):
            raise ValueError("primary modal side-action counts are malformed")
        local_values = {
            key: value
            for key, value in local_values.items()
            if value is not None
        }
        common_values = {
            key: value
            for key, value in last_solve.items()
            if key not in _MODAL_BACKUP_RANK_LOCAL_SOLVE_FIELDS
        }
        common_json = json.dumps(
            common_values, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        local_json = json.dumps(
            local_values, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except Exception as exc:  # noqa: BLE001 - collect before any backup transition
        local_error = f"{type(exc).__name__}: {exc}"
    gathered = comm.allgather((local_error, common_json, local_json))
    failures = [
        f"rank {rank}: {error}"
        for rank, (error, _common, _local) in enumerate(gathered)
        if error is not None
    ]
    if failures:
        raise RuntimeError(
            "primary modal backup record rejected collectively; "
            + "; ".join(failures)
        )
    common_rows = [common for _error, common, _local in gathered]
    if any(row != common_rows[0] for row in common_rows[1:]):
        raise RuntimeError("primary modal common return facts differ across ranks")
    rank_local_rows = []
    for expected_rank, (_error, _common, local) in enumerate(gathered):
        if local is None:
            raise RuntimeError("primary modal rank-local work record is missing")
        row = json.loads(local)
        if row.get("rank") != expected_rank:
            raise RuntimeError("primary modal rank-local work has a wrong rank id")
        rank_local_rows.append(row)
    result = json.loads(common_rows[0])
    result["rank_local_accounting"] = rank_local_rows
    result["rank_local_accounting_scope"] = (
        "one_record_per_rank; do_not_sum_replicated_owner_values"
    )
    return result


def _bounded_modal_backup_eligibility(
    *,
    policy: Mapping[str, Any],
    reason: int,
    iterations: int,
    raw_relative_residual: float | None,
    raw_residual_pass: bool,
    trusted_iterate: bool,
    input_unchanged: bool,
    budget_exhausted: bool,
    final_residual_evaluated: bool,
    mat_preflight_failure: str | None,
    modal_action_failure: str | None,
    pc_failure: str | None,
) -> dict[str, Any]:
    """Recognize only a completed, trusted primary return that exceeds eta."""

    reason_enum = PETSc.KSP.ConvergedReason
    diverged_its = getattr(reason_enum, "DIVERGED_ITS", None)
    if diverged_its is None:
        diverged_its = getattr(reason_enum, "DIVERGED_MAX_IT", None)
    maximum = int(policy["max_it"])
    iteration_ok = bool(0 <= int(iterations) <= maximum)
    allowed_reason = bool(
        int(reason) > 0
        or (
            diverged_its is not None
            and int(reason) == int(diverged_its)
            and int(iterations) == maximum
        )
    )
    reason_class = (
        "positive_reason"
        if int(reason) > 0
        else "runtime_DIVERGED_ITS_at_max_it"
        if diverged_its is not None
        and int(reason) == int(diverged_its)
        and int(iterations) == maximum
        else "not_backup_eligible"
    )
    eta = raw_relative_residual
    finite_eta = isinstance(eta, (int, float, np.floating)) and bool(
        np.isfinite(eta)
    )
    above_approximate_bound = bool(
        finite_eta and float(eta) > float(policy["approximate_return_eta_max"])
    )
    eligible = bool(
        iteration_ok
        and allowed_reason
        and final_residual_evaluated
        and finite_eta
        and above_approximate_bound
        and not raw_residual_pass
        and trusted_iterate
        and input_unchanged
        and not budget_exhausted
        and mat_preflight_failure is None
        and modal_action_failure is None
        and pc_failure is None
    )
    return {
        "eligible": eligible,
        "status": "normal_primary_eta_refusal_backup_eligible"
        if eligible
        else "rejected",
        "normal_ksp_reason_allowed": allowed_reason,
        "normal_ksp_reason_class": reason_class,
        "runtime_diverged_its_reason": (
            None if diverged_its is None else int(diverged_its)
        ),
        "iteration_count_within_limit": iteration_ok,
        "final_residual_evaluated": bool(final_residual_evaluated),
        "raw_residual_pass": bool(raw_residual_pass),
        "raw_relative_residual": None if not finite_eta else float(eta),
        "eta_above_approximate_bound": above_approximate_bound,
        "trusted_iterate": bool(trusted_iterate),
        "input_unchanged": bool(input_unchanged),
        "budget_exhausted": bool(budget_exhausted),
        "mat_preflight_failure": mat_preflight_failure,
        "modal_action_failure": modal_action_failure,
        "pc_failure": pc_failure,
    }


def _bounded_modal_return_eligibility(
    *,
    policy: Mapping[str, Any],
    reason: int,
    iterations: int,
    raw_relative_residual: float | None,
    raw_residual_pass: bool,
    trusted_iterate: bool,
    input_unchanged: bool,
    budget_exhausted: bool,
    mat_preflight_failure: str | None,
    modal_action_failure: str | None,
    pc_failure: str | None,
) -> dict[str, Any]:
    """Classify only a normal KSP return; never turns an exception into a result."""

    reason_enum = PETSc.KSP.ConvergedReason
    diverged_its = getattr(reason_enum, "DIVERGED_ITS", None)
    if diverged_its is None:
        diverged_its = getattr(reason_enum, "DIVERGED_MAX_IT", None)
    max_it = int(policy["max_it"])
    iteration_count_within_limit = bool(0 <= iterations <= max_it)
    its_at_limit = bool(
        diverged_its is not None
        and reason == int(diverged_its)
        and iterations == max_it
    )
    eta = raw_relative_residual
    finite_eta = isinstance(eta, (int, float, np.floating)) and bool(
        np.isfinite(eta)
    )
    raw_target_missed = bool(
        finite_eta
        and float(eta) > float(policy["target_rtol"])
        and not raw_residual_pass
    )
    positive_reason_raw_miss = bool(reason > 0 and raw_target_missed)
    allowed_eta = bool(
        finite_eta and float(eta) <= float(policy["approximate_return_eta_max"])
    )
    usable = bool(
        iteration_count_within_limit
        and raw_target_missed
        and (its_at_limit or positive_reason_raw_miss)
        and allowed_eta
        and trusted_iterate
        and input_unchanged
        and not budget_exhausted
        and mat_preflight_failure is None
        and modal_action_failure is None
        and pc_failure is None
    )
    return {
        "pc_usable": usable,
        "status": (
            "INNER_TARGET_NOT_MET_APPROX_RETURN" if usable else "rejected"
        ),
        "runtime_diverged_its_at_max_it": its_at_limit,
        "iteration_count_within_limit": iteration_count_within_limit,
        "raw_target_missed": raw_target_missed,
        "positive_reason_with_raw_target_miss": positive_reason_raw_miss,
        "eta_within_pc_usable_bound": allowed_eta,
        "trusted_iterate": bool(trusted_iterate),
        "input_unchanged": bool(input_unchanged),
        "budget_exhausted": bool(budget_exhausted),
        "mat_preflight_failure": mat_preflight_failure,
        "modal_action_failure": modal_action_failure,
        "pc_failure": pc_failure,
    }


def _modal_trace_array_limit_bytes(modal_count: int) -> int:
    values_per_solve = (
        (1 + 3 * _MODAL_SOLVE_TRACE_EVALUATION_LIMIT) * modal_count
        + 14 * _MODAL_SOLVE_TRACE_HISTORY_LIMIT
    )
    return int(
        _MODAL_SOLVE_TRACE_SOLVE_LIMIT
        * values_per_solve
        * np.dtype(np.complex128).itemsize
    )


def _capture_modal_array(
    record: dict[str, Any],
    key: str,
    values: np.ndarray,
) -> dict[str, Any] | None:
    array = np.asarray(values)
    current = int(record.get("captured_array_bytes", 0))
    modal_count = int(record.get("modal_count", array.size))
    if (
        key not in {"g", "m", "raw", "scaled", "gamma"}
        or array.dtype != np.dtype(np.complex128)
        or array.ndim != 1
        or array.size > (
            _MODAL_SOLVE_TRACE_HISTORY_LIMIT if key == "gamma" else modal_count
        )
        or (key != "gamma" and array.size != modal_count)
    ):
        record["capture_complete"] = False
        record["capture_incomplete_reason"] = "unexpected_array_shape_or_dtype"
        return None
    if current + int(array.nbytes) > _modal_trace_array_limit_bytes(modal_count) // 2:
        record["capture_complete"] = False
        record["capture_incomplete_reason"] = "array_payload_limit_exceeded"
        return None
    raw = np.ascontiguousarray(array).tobytes(order="C")
    record["captured_array_bytes"] = current + int(array.nbytes)
    return {
        "dtype": "complex128",
        "shape": list(array.shape),
        "order": "C",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "encoding": "base64",
        "data": base64.b64encode(raw).decode("ascii"),
    }


def _modal_trace_side_apply_record(action: Any) -> dict[str, Any]:
    source = getattr(action, "_last_apply", None)
    source = source if isinstance(source, Mapping) else {}
    last_apply = {}
    for key in (
        "status",
        "reason",
        "iterations",
        "elapsed_seconds",
        "rhs_norm",
        "residual_norm",
        "relative_residual",
    ):
        if key not in source:
            continue
        value = source[key]
        if isinstance(value, np.generic):
            value = value.item()
        if value is None or isinstance(value, (str, int, float, bool)):
            last_apply[key] = value
    counts = source.get("counts", {})
    delta = counts.get("delta") if isinstance(counts, Mapping) else None
    if isinstance(delta, Mapping):
        last_apply["count_delta"] = {
            key: int(delta[key])
            for key in (
                "Q", "H6", "A6", "p4_backsolve", "p4_refinement", "P", "PH_total"
            )
            if isinstance(delta.get(key), (int, np.integer))
        }
    apply_count = getattr(action, "_apply_count", None)
    return {
        "apply_count": int(apply_count)
        if isinstance(apply_count, (int, np.integer))
        else None,
        "apply_count_source": "action_apply_count",
        "audit_index": "unknown",
        "last_apply": last_apply,
    }


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


def _replicated_modal_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    owner = comm.size - 1
    local = None
    if comm.rank == owner:
        local = np.asarray(
            vector.getValues(np.arange(vector.getSize(), dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)


def _encode_modal_real_coordinates(values: np.ndarray) -> np.ndarray:
    """Store complex modal values as real-valued ``[Re, Im]`` coordinates."""

    modal_values = np.asarray(values, dtype=np.complex128)
    if modal_values.ndim != 1:
        raise ValueError("Modal values must be a one-dimensional vector.")
    coordinates = np.empty(2 * modal_values.size, dtype=np.complex128)
    coordinates[: modal_values.size] = modal_values.real
    coordinates[modal_values.size :] = modal_values.imag
    return coordinates


def _decode_modal_real_coordinates(
    coordinates: np.ndarray, modal_count: int
) -> np.ndarray:
    """Restore real-valued ``[Re, Im]`` coordinates to complex modal values."""

    values = np.asarray(coordinates, dtype=np.complex128)
    if values.shape != (2 * modal_count,):
        raise ValueError("Real modal coordinates have the wrong shape.")
    return np.asarray(
        values[:modal_count].real + 1j * values[modal_count:].real,
        dtype=np.complex128,
    )


def _action_diagnostics(action: Any) -> dict[str, Any]:
    diagnostics = getattr(action, "diagnostics", None)
    if callable(diagnostics):
        diagnostics = diagnostics()
    if diagnostics is None:
        diagnostics = getattr(action, "audit", None)
        if callable(diagnostics):
            diagnostics = diagnostics()
    if not isinstance(diagnostics, Mapping):
        raise TypeError("Borrowed action must expose diagnostics or audit.")
    return dict(diagnostics)


_V13_SHARED_ACTION_COUNTERS = (
    "pc",
    "Q",
    "p4_backsolve",
    "p4_refinement",
    "H6",
    "A6",
    "J",
    "JH",
    "P",
    "PH_audit",
    "PH_total",
)
_V13_FIXED_Q_ACTION_COUNTERS = (
    "mathematical_correction_steps_requested",
    "mathematical_correction_steps_completed_with_valid_q_audit",
    "successful_q_audit_count",
    "q_attempts_missing_complete_audit",
    "successful_factor_solve_delta_total",
    "failed_q_attempt_count",
    "failed_live_factor_backsolve_delta_total",
    "failed_live_factor_backsolve_delta_unknown_count",
)


def _v13_action_work_snapshot(action: Any) -> dict[str, Any]:
    """Capture only rank-local cumulative action/callback counters."""

    diagnostics = _action_diagnostics(action)
    shared = diagnostics.get("shared_side_inverse_callback_counts")
    if isinstance(shared, Mapping):
        shared_counts = {
            key: shared.get(key)
            for key in _V13_SHARED_ACTION_COUNTERS
            if key in shared
        }
    else:
        shared_counts = None
    fixed_q = diagnostics.get("fixed_q_actual_work_cumulative")
    if isinstance(fixed_q, Mapping):
        fixed_q_counts = {
            key: fixed_q.get(key)
            for key in _V13_FIXED_Q_ACTION_COUNTERS
            if key in fixed_q
        }
        step_counts = fixed_q.get("factor_solve_deltas_by_step")
        if isinstance(step_counts, Mapping):
            fixed_q_counts["factor_solve_deltas_by_step"] = {
                step: {
                    key: value
                    for key, value in fields.items()
                    if key
                    in {
                        "audited_q_count",
                        "factor_solve_delta_total",
                        "direct_zero_status_audited_q_count",
                        "direct_zero_count",
                        "direct_zero_status_missing_q_count",
                    }
                }
                for step, fields in step_counts.items()
                if step in {"initial", "correction"}
                and isinstance(fields, Mapping)
            }
    else:
        fixed_q_counts = None
    return {
        "action_apply_count": diagnostics.get("apply_count"),
        "shared_side_inverse_callback_counts": shared_counts,
        "shared_counter_scope": diagnostics.get(
            "shared_side_inverse_callback_counter_scope"
        ),
        "fixed_q_actual_work_cumulative": fixed_q_counts,
    }


def _v13_numeric_counter_delta(before: Any, after: Any) -> Any:
    """Subtract comparable integer counters while leaving unknowns explicit."""

    if (
        isinstance(before, int)
        and not isinstance(before, bool)
        and isinstance(after, int)
        and not isinstance(after, bool)
    ):
        return int(after) - int(before)
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        delta = {
            key: _v13_numeric_counter_delta(value, after[key])
            for key, value in before.items()
            if key in after
        }
        return delta or None
    return None


def _v13_action_work_delta(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        key: _v13_numeric_counter_delta(before.get(key), after.get(key))
        for key in (
            "action_apply_count",
            "shared_side_inverse_callback_counts",
            "fixed_q_actual_work_cumulative",
        )
    }


def _action_apply_count(action: Any) -> int | None:
    try:
        value = _action_diagnostics(action).get("apply_count")
    except (TypeError, ValueError):
        return None
    if isinstance(value, (int, np.integer)) and int(value) >= 0:
        return int(value)
    return None


def _v13_local_petsc_vec_hash(vector: PETSc.Vec) -> dict[str, Any]:
    values = np.asarray(vector.getArray(readonly=True))
    if not values.flags.c_contiguous:
        raise ValueError("V13 evidence Vec array is not contiguous")
    digest = hashlib.sha256()
    view = memoryview(values).cast("B")
    chunk_bytes = 1 << 20
    for start in range(0, len(view), chunk_bytes):
        digest.update(view[start : start + chunk_bytes])
    return {
        "handle": int(vector.handle),
        "global_size": int(vector.getSize()),
        "local_size": int(vector.getLocalSize()),
        "ownership_range": [int(value) for value in vector.getOwnershipRange()],
        "dtype": str(values.dtype),
        "local_sha256": digest.hexdigest(),
    }


def _action_operator(action: Any) -> PETSc.Mat:
    operator = getattr(action, "operator", None)
    if operator is None:
        operator = getattr(action, "A", None)
    if operator is None:
        raise TypeError("Borrowed action must expose operator or A.")
    return operator


def _direct_factor_count(diagnostics: dict[str, Any]) -> int:
    return int(
        diagnostics.get(
            "direct_factor_count",
            diagnostics.get("local_direct_factor_count", 0),
        )
    )


def _factor_modal_constraint(
    constraint_values: np.ndarray, modal_count: int
) -> tuple[np.ndarray, np.ndarray, float]:
    constraint = np.asarray(constraint_values, dtype=np.complex128)
    if constraint.shape != (modal_count, modal_count):
        raise ValueError("C has the wrong modal shape")
    if not bool(np.all(np.isfinite(constraint))):
        raise ValueError("C contains non-finite values")
    condition = float(np.linalg.cond(constraint))
    if not np.isfinite(condition) or condition * np.finfo(float).eps >= 1.0:
        raise np.linalg.LinAlgError("C is singular at complex128 working precision")
    lu, pivots = lu_factor(constraint, check_finite=True)
    diagonal = np.diag(lu)
    if not bool(np.all(np.isfinite(diagonal))) or bool(np.any(diagonal == 0.0)):
        raise np.linalg.LinAlgError("C LU has a zero or non-finite pivot")
    return (
        np.asarray(lu, dtype=np.complex128),
        np.asarray(pivots),
        condition,
    )


def _complex_anderson_qr_coefficients(
    delta_f: np.ndarray, current_f: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve a small complex Anderson least-squares problem by pivoted QR.

    The returned coefficients are mapped back from the pivoted column order.
    Numerically dependent trailing columns are omitted using a scale-relative
    working-precision cutoff; no normal equations or pseudoinverse are used.
    """

    matrix = np.asarray(delta_f, dtype=np.complex128)
    vector = np.asarray(current_f, dtype=np.complex128)
    if matrix.ndim != 2 or vector.shape != (matrix.shape[0],):
        raise ValueError("Complex Anderson history has incompatible shapes.")
    if matrix.shape[1] < 1:
        raise ValueError("Complex Anderson QR requires at least one history column.")
    if not bool(np.all(np.isfinite(matrix))) or not bool(np.all(np.isfinite(vector))):
        raise FloatingPointError("Complex Anderson history is non-finite.")

    q_matrix, r_matrix, pivots = pivoted_qr(
        matrix,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(r_matrix))
    qr_scale = float(np.max(diagonal)) if diagonal.size else 0.0
    cutoff = (
        np.finfo(np.float64).eps * max(matrix.shape) * qr_scale
    )
    rank = 0
    for value in diagonal:
        if float(value) <= cutoff:
            break
        rank += 1

    coefficients = np.zeros(matrix.shape[1], dtype=np.complex128)
    if rank:
        projected = q_matrix[:, :rank].conj().T @ vector
        pivoted_coefficients = solve_triangular(
            r_matrix[:rank, :rank],
            projected,
            lower=False,
            check_finite=False,
        )
        coefficients[np.asarray(pivots[:rank], dtype=np.intp)] = (
            pivoted_coefficients
        )
    if not bool(np.all(np.isfinite(coefficients))):
        raise FloatingPointError("Complex Anderson QR coefficients are non-finite.")
    fit_residual = matrix @ coefficients - vector
    if not bool(np.all(np.isfinite(fit_residual))):
        raise FloatingPointError("Complex Anderson QR fit is non-finite.")
    fit_residual_norm = float(np.linalg.norm(fit_residual))
    if not np.isfinite(fit_residual_norm):
        raise FloatingPointError("Complex Anderson QR fit norm is non-finite.")
    return coefficients, {
        "effective_rank": int(rank),
        "history_column_count": int(matrix.shape[1]),
        "discarded_column_count": int(matrix.shape[1] - rank),
        "qr_scale": qr_scale,
        "rank_cutoff": float(cutoff),
        "fit_residual_norm": fit_residual_norm,
    }


def _complex_anderson_candidate_update(
    modal: np.ndarray,
    fixed_point_residual: np.ndarray,
    delta_m: np.ndarray | None,
    delta_f: np.ndarray | None,
    *,
    capture_coefficients: bool = False,
    mixing_metric: str = "C_scaled_residual",
    raw_residual: np.ndarray | None = None,
    delta_raw_residual: np.ndarray | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Make one beta=1 complex Type-II update or report rank zero."""

    current = np.asarray(modal, dtype=np.complex128)
    fixed_point = np.asarray(fixed_point_residual, dtype=np.complex128)
    if current.ndim != 1 or fixed_point.shape != current.shape:
        raise ValueError("Complex Anderson update vectors have incompatible shapes.")
    if not bool(np.all(np.isfinite(current))) or not bool(
        np.all(np.isfinite(fixed_point))
    ):
        raise FloatingPointError("Complex Anderson update vectors are non-finite.")
    if mixing_metric not in {"C_scaled_residual", "raw_residual"}:
        raise ValueError("Unknown complex Anderson least-squares metric.")
    if mixing_metric == "C_scaled_residual":
        if raw_residual is not None or delta_raw_residual is not None:
            raise ValueError("Raw residual data requires the raw mixing metric.")
        mixing_vector = fixed_point
    else:
        if raw_residual is None:
            raise ValueError("Raw Anderson mixing requires the current raw residual.")
        mixing_vector = np.asarray(raw_residual, dtype=np.complex128)
        if mixing_vector.shape != current.shape:
            raise ValueError("Raw Anderson residual has an incompatible shape.")
        if not bool(np.all(np.isfinite(mixing_vector))):
            raise FloatingPointError("Raw Anderson residual is non-finite.")
    delta_f_values = (
        None if delta_f is None else np.asarray(delta_f, dtype=np.complex128)
    )
    if delta_f_values is not None and delta_f_values.ndim != 2:
        raise ValueError("Complex Anderson residual history must be a matrix.")
    if (delta_m is None) != (delta_f_values is None):
        raise ValueError("Complex Anderson iterate and residual histories must match.")
    if delta_f_values is None or delta_f_values.shape[1] == 0:
        if delta_raw_residual is not None:
            raise ValueError("Raw Anderson differences require a history column.")
        candidate = current + fixed_point
        if not bool(np.all(np.isfinite(candidate))):
            raise FloatingPointError("Complex Anderson startup step is non-finite.")
        return candidate, {
            "update": "fixed_point_startup",
            "history_column_count": 0,
            "effective_rank": 0,
            "discarded_column_count": 0,
            "qr_scale": 0.0,
            "rank_cutoff": 0.0,
            "fit_residual_norm": None,
            "mixing_metric": mixing_metric,
        }
    delta_m_values = np.asarray(delta_m, dtype=np.complex128)
    delta_f_values = np.asarray(delta_f_values, dtype=np.complex128)
    if (
        delta_m_values.ndim != 2
        or delta_f_values.ndim != 2
        or delta_m_values.shape != delta_f_values.shape
        or delta_m_values.shape[0] != current.size
    ):
        raise ValueError("Complex Anderson difference histories have incompatible shapes.")
    if mixing_metric == "raw_residual":
        if delta_raw_residual is None:
            raise ValueError("Raw Anderson mixing requires raw residual history.")
        delta_mixing = np.asarray(delta_raw_residual, dtype=np.complex128)
        if delta_mixing.shape != delta_f_values.shape:
            raise ValueError("Raw and scaled Anderson histories must align.")
        coefficients, diagnostics = _complex_anderson_qr_coefficients(
            delta_mixing, mixing_vector
        )
    else:
        coefficients, diagnostics = _complex_anderson_qr_coefficients(
            delta_f_values, mixing_vector
        )
    diagnostics["mixing_metric"] = mixing_metric
    if capture_coefficients:
        diagnostics["_capture_gamma"] = coefficients
    if diagnostics["effective_rank"] == 0:
        return None, {"update": "rank_zero_history", **diagnostics}
    candidate = current + fixed_point - (delta_m_values + delta_f_values) @ coefficients
    if not bool(np.all(np.isfinite(candidate))):
        raise FloatingPointError("Complex Anderson candidate is non-finite.")
    return candidate, {"update": "complex_qr_type_ii", **diagnostics}


@dataclass
class HybridActionModalSchurSystem:
    """Small modal Schur system assembled from two borrowed actions."""

    modal_schur: np.ndarray
    modal_constraint: np.ndarray
    lu: np.ndarray
    pivots: np.ndarray
    rank: int
    condition: float
    matrix_repeat_error: float
    lu_repeat_solve_error: float
    build_apply_count: dict[str, int]
    repeat_diagnostics: dict[str, Any] = field(default_factory=dict)
    sampled_column_diagnostics: dict[str, Any] = field(default_factory=dict)
    batch_diagnostics: dict[str, Any] = field(default_factory=dict)
    _destroyed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._shape = tuple(self.modal_schur.shape)
        self._array_bytes = {
            "modal_schur_bytes": int(self.modal_schur.nbytes),
            "modal_constraint_bytes": int(self.modal_constraint.nbytes),
            "lu_bytes": int(self.lu.nbytes),
            "pivots_bytes": int(self.pivots.nbytes),
        }
        self._finite = bool(
            np.all(np.isfinite(self.modal_schur))
            and np.all(np.isfinite(self.lu))
            and np.all(np.isfinite(self.pivots))
        )

    @property
    def modal_count(self) -> int:
        return int(self._shape[0])

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("Action modal Schur has been destroyed")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self.modal_schur.shape[0],):
            raise ValueError("Action modal Schur RHS has the wrong shape.")
        return np.asarray(
            lu_solve((self.lu, self.pivots), values, check_finite=True),
            dtype=np.complex128,
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        finite = (
            self._finite
            if self._destroyed
            else bool(
                np.all(np.isfinite(self.modal_schur))
                and np.all(np.isfinite(self.lu))
                and np.all(np.isfinite(self.pivots))
            )
        )
        return {
            "shape": list(self._shape),
            "dtype": "complex128",
            "rank": int(self.rank),
            "condition": float(self.condition),
            "finite": finite,
            "normal_equations": False,
            "matrix_repeat_error": float(self.matrix_repeat_error),
            "lu_repeat_solve_error": float(self.lu_repeat_solve_error),
            "repeat_diagnostics": dict(self.repeat_diagnostics),
            "sampled_column_diagnostics": dict(self.sampled_column_diagnostics),
            "batch_diagnostics": dict(self.batch_diagnostics),
            "build_apply_count": dict(self.build_apply_count),
            **self._array_bytes,
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.modal_schur = None
        self.modal_constraint = None
        self.lu = None
        self.pivots = None
        self._destroyed = True


def _v13_modal_schur_diagnostic_fields(
    modal_count: int, build_audit: Mapping[str, Any]
) -> dict[str, Any]:
    if type(modal_count) is not int or modal_count <= 0:
        raise ValueError("V13 modal Schur diagnostics require a positive size")
    if not isinstance(build_audit, Mapping):
        raise TypeError("V13 modal Schur diagnostics require the builder audit")
    sample_columns = build_audit.get(
        "sample_columns_written_directly_to_final_matrix"
    )
    remaining_columns = build_audit.get("remaining_columns_applied_once")
    if not isinstance(sample_columns, list) or not isinstance(
        remaining_columns, list
    ):
        raise TypeError("V13 builder audit is missing its modal column lists")
    completed_columns = [*sample_columns, *remaining_columns]
    if (
        any(type(column) is not int for column in completed_columns)
        or len(completed_columns) != modal_count
        or len(set(completed_columns)) != modal_count
        or set(completed_columns) != set(range(modal_count))
    ):
        raise ValueError(
            "V13 builder audit must cover every modal Schur column exactly once"
        )
    return {
        "modal_count": modal_count,
        "modal_schur_materialized": (
            build_audit.get("full_owner_matrix_pages_materialized_before_sample_gate")
            is True
        ),
        "modal_schur_shape": [modal_count, modal_count],
        "modal_schur_column_count": len(completed_columns),
        "build_audit": dict(build_audit),
    }


def _task041_v13_outer_workspace_pass_resource_contract_valid(
    phase: str,
    report: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    rank_count: int,
) -> bool:
    """Recompute the frozen byte gate before accepting an outer-workspace pass."""

    expected_restart = 32 if phase == "outer_restart32_workspace" else 64
    expected_external_keys = {
        "bound_fresh_supervisor_sample",
        "tree_cgroup_and_all_mpi_ranks",
        "initial_aggregate_memfree_gate",
        "initial_node1_memfree_gate",
        "aggregate_floor_headroom",
        "node1_phase_headroom",
        "host_floor_headroom",
        "cgroup_ancestor_headroom",
        "case_cap_projection",
        "sample_cost_contract",
    }
    hard_cap = 85_899_345_920
    reserve = 8_589_934_592
    floor = 412_316_860_416

    def strict_integer_vector(value: Any) -> bool:
        return bool(
            isinstance(value, list)
            and len(value) == rank_count
            and all(type(item) is int and item >= 0 for item in value)
        )

    projection = report.get("phase_memory_projection")
    reports = projection.get("phase_reports") if isinstance(projection, Mapping) else None
    totals = projection.get("phase_total_bytes") if isinstance(projection, Mapping) else None
    if not isinstance(reports, Mapping) or not reports or not isinstance(totals, Mapping):
        return False
    if any(type(value) is not int or value < 0 for value in totals.values()):
        return False
    recomputed_totals: dict[str, int] = {}
    recomputed_by_phase: dict[str, list[int]] = {}
    for name, components in reports.items():
        if not isinstance(components, Mapping):
            return False
        fields = (
            "known_additional_bytes_by_rank",
            "additional_temporary_bytes_by_rank",
            "additional_replicated_bytes_by_rank",
        )
        arrays = [components.get(key) for key in fields]
        if any(
            not isinstance(values, list)
            or len(values) != rank_count
            or any(type(value) is not int or value < 0 for value in values)
            for values in arrays
        ):
            return False
        per_rank = [sum(values[rank] for values in arrays) for rank in range(rank_count)]
        if (
            not strict_integer_vector(components.get("additional_bytes_by_rank"))
            or components.get("additional_bytes_by_rank") != per_rank
        ):
            return False
        recomputed_by_phase[str(name)] = per_rank
        recomputed_totals[str(name)] = sum(per_rank)
    if dict(totals) != recomputed_totals:
        return False
    selected_phase = max(recomputed_totals, key=recomputed_totals.get)
    selected = reports[selected_phase]
    selected_additional = recomputed_by_phase[selected_phase]
    payload = response.get("authority_receipt_payload")
    external = response.get("external_resource_gates")
    if not isinstance(payload, Mapping) or not isinstance(external, Mapping):
        return False
    if not strict_integer_vector(response.get("additional_bytes_by_rank")):
        return False
    if not isinstance(payload.get("rank_pids"), list) or any(
        type(pid) is not int or pid <= 0 for pid in payload["rank_pids"]
    ):
        return False
    if (
        set(external) != expected_external_keys
        or any(value is not True for value in external.values())
        or report.get("phase") != phase
        or report.get("target_restart") != expected_restart
        or projection.get("selected_phase") != selected_phase
        or type(projection.get("selected_phase_payload_bytes")) is not int
        or projection.get("selected_phase_payload_bytes") != sum(selected_additional)
        or response.get("selected_memory_phase") != selected_phase
        or payload.get("selected_memory_phase") != selected_phase
        or report.get("known_additional_bytes_by_rank")
        != selected.get("known_additional_bytes_by_rank")
        or report.get("additional_temporary_bytes_by_rank")
        != selected.get("additional_temporary_bytes_by_rank")
        or report.get("additional_replicated_bytes_by_rank")
        != selected.get("additional_replicated_bytes_by_rank")
        or not strict_integer_vector(report.get("known_additional_bytes_by_rank"))
        or not strict_integer_vector(report.get("additional_temporary_bytes_by_rank"))
        or not strict_integer_vector(report.get("additional_replicated_bytes_by_rank"))
        or response.get("additional_bytes_by_rank") != selected_additional
        or not strict_integer_vector(response.get("additional_temporary_bytes_by_rank"))
        or not strict_integer_vector(response.get("additional_replicated_bytes_by_rank"))
        or response.get("selected_memory_phase_payload_bytes") != sum(selected_additional)
        or response.get("additional_temporary_bytes_by_rank")
        != selected.get("additional_temporary_bytes_by_rank")
        or response.get("additional_replicated_bytes_by_rank")
        != selected.get("additional_replicated_bytes_by_rank")
    ):
        return False
    fresh = response.get("fresh_job_authority_bytes")
    cap = response.get("cap_bytes")
    applied_reserve = response.get("W_policy_reserve_bytes")
    node0_free = response.get("node0_memfree_bytes")
    node1_free = response.get("node1_memfree_bytes")
    aggregate_free = response.get("aggregate_memfree_bytes")
    aggregate_reserve = response.get("aggregate_memfree_reserve_bytes")
    aggregate_headroom = response.get("aggregate_floor_headroom_bytes")
    node1_additional = response.get("node1_phase_additional_bytes")
    node1_headroom = response.get("node1_headroom_after_phase_additional_bytes")
    host_available = response.get("host_available_bytes")
    host_headroom = response.get("host_headroom_after_aggregate_reserve_bytes")
    cgroup_state = response.get("cgroup_limit_state")
    cgroup_headroom = response.get("cgroup_headroom_bytes")
    required = sum(selected_additional) + reserve
    projected = fresh + required if type(fresh) is int else None
    initial_gate = payload.get("initial_resource_gate")
    if (
        type(fresh) is not int
        or fresh <= 0
        or type(cap) is not int
        or cap != hard_cap
        or type(applied_reserve) is not int
        or applied_reserve != reserve
        or type(response.get("floor_bytes")) is not int
        or response.get("floor_bytes") != floor
        or type(payload.get("resource_B_bytes")) is not int
        or payload.get("resource_B_bytes") != fresh
        or type(payload.get("node0_memfree_bytes")) is not int
        or payload.get("node0_memfree_bytes") != node0_free
        or type(payload.get("node1_memfree_bytes")) is not int
        or payload.get("node1_memfree_bytes") != node1_free
        or type(payload.get("aggregate_memfree_bytes")) is not int
        or payload.get("aggregate_memfree_bytes") != aggregate_free
        or type(payload.get("aggregate_memfree_reserve_bytes")) is not int
        or payload.get("aggregate_memfree_reserve_bytes") != aggregate_reserve
        or type(payload.get("aggregate_floor_headroom_bytes")) is not int
        or payload.get("aggregate_floor_headroom_bytes") != aggregate_headroom
        or type(payload.get("node1_phase_additional_bytes")) is not int
        or payload.get("node1_phase_additional_bytes") != node1_additional
        or type(payload.get("node1_headroom_after_phase_additional_bytes")) is not int
        or payload.get("node1_headroom_after_phase_additional_bytes")
        != node1_headroom
        or type(payload.get("host_available_bytes")) is not int
        or payload.get("host_available_bytes") != host_available
        or type(payload.get("host_headroom_after_aggregate_reserve_bytes")) is not int
        or payload.get("host_headroom_after_aggregate_reserve_bytes") != host_headroom
        or type(payload.get("sample_root_pid")) is not int
        or payload.get("sample_root_pid") != response.get("root_pid")
        or payload.get("rank_pids") != response.get("rank_pids")
        or payload.get("sample_row_sha256") != response.get("sample_row_sha256")
        or payload.get("request_sha256") != response.get("request_sha256")
        or not isinstance(payload.get("invocation_id"), str)
        or not payload.get("invocation_id")
        or not isinstance(payload.get("source_sha"), str)
        or not payload.get("source_sha")
        or not isinstance(payload.get("unit"), str)
        or not payload.get("unit")
        or payload.get("phase") != phase
        or payload.get("cap_bytes") != cap
        or payload.get("W_policy_reserve_bytes") != applied_reserve
        or payload.get("floor_bytes") != floor
        or payload.get("cgroup_limit_state") != cgroup_state
        or (
            cgroup_state == "finite"
            and type(payload.get("cgroup_headroom_bytes")) is not int
        )
        or payload.get("cgroup_headroom_bytes") != cgroup_headroom
        or payload.get("selected_memory_phase") != selected_phase
        or type(payload.get("selected_memory_phase_payload_bytes")) is not int
        or payload.get("selected_memory_phase_payload_bytes")
        != sum(selected_additional)
        or not strict_integer_vector(payload.get("additional_bytes_by_rank"))
        or payload.get("additional_bytes_by_rank") != selected_additional
        or not isinstance(initial_gate, Mapping)
        or initial_gate.get("required") is not False
        or initial_gate.get("source") != "supervisor_resource_preflight"
        or initial_gate.get("initial_aggregate_memfree_minimum_bytes") != 464 * 2**30
        or initial_gate.get("initial_node1_memfree_minimum_bytes") != 80 * 2**30
        or payload.get("projected_B_plus_delta_plus_W_bytes") != projected
        or response.get("phase") != phase
        or type(response.get("root_pid")) is not int
        or not isinstance(response.get("rank_pids"), list)
        or len(response["rank_pids"]) != rank_count
        or any(type(pid) is not int or pid <= 0 for pid in response["rank_pids"])
        or len(set(response["rank_pids"])) != rank_count
        or not isinstance(response.get("sample_row_sha256"), str)
        or len(response["sample_row_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in response["sample_row_sha256"]
        )
        or not isinstance(response.get("sample_age_seconds"), (int, float))
        or isinstance(response.get("sample_age_seconds"), bool)
        or not math.isfinite(float(response["sample_age_seconds"]))
        or not 0.0 <= float(response["sample_age_seconds"]) <= 2.0
        or any(
            type(value) is not int
            for value in (
                node0_free,
                node1_free,
                aggregate_free,
                aggregate_reserve,
                aggregate_headroom,
                node1_additional,
                node1_headroom,
                host_available,
                host_headroom,
            )
        )
        or aggregate_reserve != floor
        or aggregate_free != node0_free + node1_free
        or aggregate_headroom != aggregate_free - floor
        or node1_additional != sum(selected_additional)
        or node1_headroom != node1_free - node1_additional
        or host_headroom != host_available - floor
        or response.get("projected_B_plus_delta_plus_W_bytes") != projected
        or projected is None
        or projected > cap
    ):
        return False
    if (
        aggregate_headroom < required
        or node1_headroom < 0
        or host_headroom < required
    ):
        return False
    if cgroup_state == "finite":
        if (
            type(cgroup_headroom) is not int
            or cgroup_headroom < required
            or type(payload.get("cgroup_headroom_bytes")) is not int
        ):
            return False
    elif cgroup_state == "max_or_unlimited":
        if cgroup_headroom is not None:
            return False
    else:
        return False
    cost = response.get("cost_assessment")
    return bool(
        isinstance(cost, Mapping)
        and cost.get("scope") == "outer_ksp_workspace_admission"
        and cost.get("status") == "workspace_model_valid"
        and cost.get("target_restart") == expected_restart
        and cost.get("W_policy_reserve_bytes") == reserve
        and cost.get("target_is_elapsed_stop") is False
        and response.get("projected_B_plus_delta_plus_W_bytes")
        == fresh + sum(selected_additional) + applied_reserve
    )


class Task041V13ConsistentModalSurrogateSystem:
    """Owner-LU solve for the V13 Schur built from the fixed approximate B.

    ``modal_constraint`` is replicated because it is also used to check the
    original modal row after each complete block-LDU application.  The Schur
    matrix and its LU are retained only by ``modal_owner``.  Side actions are
    borrowed and are never destroyed here.
    """

    method = TASK041_V13_CONSISTENT_MODAL_POLICY_ID
    requires_right_fgmres = True

    def __init__(
        self,
        *,
        modal_schur: np.ndarray | None,
        modal_constraint: np.ndarray,
        lu: np.ndarray | None,
        pivots: np.ndarray | None,
        modal_owner: int,
        comm: Any,
        condition: float | None,
        storage_plan: Mapping[str, Any],
        build_audit: Mapping[str, Any],
        bottom_action: Any,
        top_action: Any,
        side_operation_baseline: Mapping[str, Mapping[str, int]] | None,
        fresh_authority_callback: Callable[
            [str, Mapping[str, Any]], Mapping[str, Any]
        ] | None = None,
        marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
        snapshot_callback: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
        | None = None,
    ) -> None:
        self.modal_schur = modal_schur
        self.modal_constraint = np.asarray(modal_constraint, dtype=np.complex128)
        self.lu = lu
        self.pivots = pivots
        self.modal_owner = int(modal_owner)
        self.comm = comm
        self.rank = int(comm.rank)
        self.modal_count = int(self.modal_constraint.shape[0])
        self.condition = None if condition is None else float(condition)
        self.storage_plan = dict(storage_plan)
        self.build_audit = dict(build_audit)
        self._modal_schur_diagnostic_fields = _v13_modal_schur_diagnostic_fields(
            self.modal_count, self.build_audit
        )
        self.bottom_action = bottom_action
        self.top_action = top_action
        self.side_operation_baseline = (
            None
            if side_operation_baseline is None
            else {
                side: dict(counts)
                for side, counts in side_operation_baseline.items()
            }
        )
        self._fresh_authority_callback = fresh_authority_callback
        self._marker_callback = marker_callback
        self._snapshot_callback = snapshot_callback
        self._destroyed = False
        self._solve_count = 0
        self._owner_lu_solve_count = 0
        self._last_solve: dict[str, Any] | None = None
        self._last_original_modal_row: dict[str, Any] | None = None
        self._last_original_modal_row_arrays: dict[str, np.ndarray] | None = None
        self._last_original_modal_row_snapshot_receipt: dict[str, Any] | None = None
        self._last_pc_apply_attempt: dict[str, Any] | None = None
        self._last_pc_apply_success: dict[str, Any] | None = None
        self._last_s_b_ready_snapshot: dict[str, Any] | None = None
        self._original_modal_row_snapshot_slots: set[str] = set()
        self._side_operation_after = (
            None
            if self.side_operation_baseline is None
            else {
                side: dict(counts)
                for side, counts in self.side_operation_baseline.items()
            }
        )
        self._modal_ksp_handle = None
        self._modal_ksp_solve_call_count = 0
        self._outer_workspace_admissions: dict[str, dict[str, Any]] = {}
        self._array_bytes = {
            "modal_constraint_bytes": int(self.modal_constraint.nbytes),
            "modal_schur_bytes": (
                0 if self.modal_schur is None else int(self.modal_schur.nbytes)
            ),
            "lu_bytes": 0 if self.lu is None else int(self.lu.nbytes),
            "pivots_bytes": 0 if self.pivots is None else int(self.pivots.nbytes),
        }
        if self.modal_constraint.shape != (self.modal_count, self.modal_count):
            raise ValueError("V13 modal constraint has an invalid shape.")
        if (self.rank == self.modal_owner) != (self.modal_schur is not None):
            raise ValueError("V13 Schur storage must exist only on the modal owner.")
        if (self.rank == self.modal_owner) != (self.lu is not None):
            raise ValueError("V13 LU storage must exist only on the modal owner.")
        if (self.rank == self.modal_owner) != (self.pivots is not None):
            raise ValueError("V13 pivot storage must exist only on the modal owner.")

    def authorize_outer_workspace(
        self, phase: str, report: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Ask the bound authority before allocating an outer KSP workspace."""

        local_error = None
        response: dict[str, Any] | None = None
        request_sha256 = None
        request_json = None
        try:
            if self._destroyed:
                raise RuntimeError("V13 modal surrogate is destroyed")
            if phase not in {
                "outer_restart32_workspace",
                "outer_restart64_workspace",
            }:
                raise ValueError("V13 outer workspace phase is not registered")
            if not callable(self._fresh_authority_callback):
                raise TypeError("V13 outer workspace has no bound fresh authority callback")
            canonical = json.dumps(
                dict(report), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            request_json = canonical
            request_sha256 = hashlib.sha256(canonical.encode()).hexdigest()
        except Exception as exc:  # noqa: BLE001 - agree before the callback collective
            local_error = f"{type(exc).__name__}: {exc}"
        request_rows = self.comm.allgather(
            {
                "rank": int(self.comm.rank),
                "error": local_error,
                "request_sha256": request_sha256,
                "request_json": request_json,
                "marker_callback_available": callable(self._marker_callback),
            }
        )
        request_errors = []
        for rank, row in enumerate(request_rows):
            if not isinstance(row, Mapping):
                request_errors.append(f"rank {rank}: invalid preflight record")
            elif row.get("error") is not None:
                request_errors.append(f"rank {rank}: {row.get('error')}")
        marker_presence = [
            isinstance(row, Mapping)
            and row.get("marker_callback_available") is True
            for row in request_rows
        ]
        if any(marker_presence) and not all(marker_presence):
            request_errors.append(
                "outer authority marker callback availability differs across ranks"
            )
        request_digests = [
            row.get("request_sha256")
            for row in request_rows
            if isinstance(row, Mapping) and row.get("error") is None
        ]
        if len(request_digests) != int(self.comm.size):
            request_errors.append("request serialization missing on one or more ranks")
        if not request_errors and len(set(request_digests)) != 1:
            request_errors.append("outer restart report differs across ranks")
        request_validation_error = None
        if request_errors:
            request_validation_error = (
                "V13 outer restart report is unbindable: "
                + "; ".join(request_errors)
            )
            marker_error = None
            if all(marker_presence):
                try:
                    self._marker_callback(
                        "v13_outer_workspace_authority",
                        {
                            "phase": phase,
                            "request_sha256": request_sha256,
                            "request_json": request_json,
                            "request_preflight": request_rows,
                            "request_validation_error": request_validation_error,
                            "response": None,
                            "rank_validation": [],
                            "validation_error": request_validation_error,
                        },
                    )
                except Exception as exc:  # noqa: BLE001 - retain request failure
                    marker_error = f"{type(exc).__name__}: {exc}"
            elif any(marker_presence):
                marker_error = (
                    "marker callback availability differs across ranks; "
                    "collective marker was not attempted"
                )
            marker_errors = self.comm.allgather(marker_error)
            marker_failures = [
                f"rank {rank}: {error}"
                for rank, error in enumerate(marker_errors)
                if error is not None
            ]
            if marker_failures:
                request_validation_error += (
                    "; request marker persistence also failed: "
                    + "; ".join(marker_failures)
                )
            raise RuntimeError(request_validation_error)
        assert request_sha256 is not None

        raw_response_json = None
        raw_receipt_json = None
        raw_capture_error = None
        validated_response_json = None
        try:
            raw_response = self._fresh_authority_callback(phase, dict(report))
            try:
                raw_response_json = json.dumps(
                    raw_response,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except Exception as exc:  # noqa: BLE001 - keep capture failure diagnostic
                raw_capture_error = f"response {type(exc).__name__}: {exc}"
            if isinstance(raw_response, Mapping):
                raw_receipt = raw_response.get("authority_receipt_payload")
                if raw_receipt is not None:
                    try:
                        raw_receipt_json = json.dumps(
                            raw_receipt,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    except Exception as exc:  # noqa: BLE001 - keep capture failure diagnostic
                        receipt_error = f"receipt {type(exc).__name__}: {exc}"
                        raw_capture_error = "; ".join(
                            item for item in (raw_capture_error, receipt_error) if item
                        )
            if not isinstance(raw_response, Mapping):
                raise TypeError("V13 outer restart authority returned no record")
            response = dict(raw_response)
            payload = response.get("authority_receipt_payload")
            if not isinstance(payload, Mapping):
                raise TypeError("V13 outer restart authority receipt payload is absent")
            receipt_sha = hashlib.sha256(
                json.dumps(
                    dict(payload),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            if (
                response.get("schema") != "task041.v13.modal_builder_admission.v1"
                or response.get("phase") != phase
                or response.get("request_sha256") != request_sha256
                or response.get("authority_receipt_sha256") != receipt_sha
                or payload.get("phase") != phase
                or payload.get("request_sha256") != request_sha256
                or response.get("status") not in {"pass", "refused"}
                or response.get("decision") not in {"continue", "stop"}
                or response.get("decision")
                != ("continue" if response.get("status") == "pass" else "stop")
            ):
                raise ValueError("V13 outer restart authority receipt is not bound")
            if response.get("status") == "pass" and (
                response.get("decision") != "continue"
                or not _task041_v13_outer_workspace_pass_resource_contract_valid(
                    phase,
                    report,
                    response,
                    rank_count=int(self.comm.size),
                )
            ):
                raise ValueError(
                    "V13 outer restart pass fails recomputed fresh B/delta/W/floor evidence"
                )
            validated_response_json = json.dumps(
                response, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except Exception as exc:  # noqa: BLE001 - collective result checked below
            local_error = f"{type(exc).__name__}: {exc}"
        response_rows = self.comm.allgather(
            {
                "validation_error": local_error,
                "validated_response_json": validated_response_json,
                "raw_response_json": raw_response_json,
                "raw_receipt_json": raw_receipt_json,
                "raw_capture_error": raw_capture_error,
            }
        )
        response_errors = [
            f"rank {rank}: {row.get('validation_error')}"
            for rank, row in enumerate(response_rows)
            if isinstance(row, Mapping) and row.get("validation_error") is not None
        ]
        if any(not isinstance(row, Mapping) for row in response_rows):
            response_errors.append("one or more ranks returned an invalid response record")
        response_payloads = [
            row.get("validated_response_json")
            for row in response_rows
            if isinstance(row, Mapping) and row.get("validation_error") is None
        ]
        if any(
            isinstance(row, Mapping)
            and row.get("validation_error") is None
            and row.get("validated_response_json") is None
            for row in response_rows
        ):
            response_errors.append("one or more ranks omitted a validated response")
        validation_error = None
        if response_errors or len(response_payloads) != int(self.comm.size):
            validation_error = (
                "V13 outer restart authority validation failed: "
                + "; ".join(response_errors or ["response missing on one or more ranks"])
            )
        elif len(set(response_payloads)) != 1:
            validation_error = "V13 outer restart authority differs across ranks"

        marker_error = None
        if callable(self._marker_callback):
            try:
                self._marker_callback(
                    "v13_outer_workspace_authority",
                    {
                        "phase": phase,
                        "request_sha256": request_sha256,
                        "request": dict(report),
                        "response": None if response is None else dict(response),
                        "rank_validation": [
                            {
                                "rank": rank,
                                "error": row.get("validation_error"),
                                "validated_response": row.get(
                                    "validated_response_json"
                                ),
                                "raw_response": row.get("raw_response_json"),
                                "raw_receipt": row.get("raw_receipt_json"),
                                "raw_capture_error": row.get("raw_capture_error"),
                            }
                            for rank, row in enumerate(response_rows)
                        ],
                        "validation_error": validation_error,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - preserve the authority failure below
                marker_error = f"{type(exc).__name__}: {exc}"
        marker_errors = self.comm.allgather(marker_error)
        marker_failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(marker_errors)
            if error is not None
        ]

        if validation_error is not None:
            if marker_failures:
                validation_error += (
                    "; outer authority marker persistence also failed: "
                    + "; ".join(marker_failures)
                )
            raise RuntimeError(validation_error)
        if not isinstance(response, Mapping):
            detail = "V13 outer restart authority response is missing"
            if marker_failures:
                detail += "; marker persistence also failed: " + "; ".join(
                    marker_failures
                )
            raise TypeError(detail)
        if marker_failures:
            detail = (
                "V13 outer authority marker persistence failed after decision "
                f"{response.get('status')!r}"
            )
            reasons = response.get("reasons")
            if isinstance(reasons, list) and reasons:
                detail += ": " + "; ".join(map(str, reasons))
            detail += "; " + "; ".join(marker_failures)
            raise RuntimeError(detail)
        self._outer_workspace_admissions[phase] = dict(response)
        return dict(response)

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        local_error = None
        values = None
        digest = None
        try:
            if self._destroyed:
                raise RuntimeError("V13 modal surrogate has been destroyed")
            values = np.asarray(rhs, dtype=np.complex128)
            if values.shape != (self.modal_count,) or not np.all(np.isfinite(values)):
                raise ValueError("V13 modal Schur RHS has invalid shape or values")
            digest = hashlib.sha256(
                np.ascontiguousarray(values).tobytes()
            ).hexdigest()
        except Exception as exc:  # noqa: BLE001 - collect local error before the RHS collective
            local_error = f"{type(exc).__name__}: {exc}"
        preflight = self.comm.allgather(
            (local_error, digest, int(self.modal_owner))
        )
        errors = [
            f"rank {rank}: {error}"
            for rank, (error, _hash, _owner) in enumerate(preflight)
            if error is not None
        ]
        hashes = [value_hash for _error, value_hash, _owner in preflight]
        owners = [owner for _error, _hash, owner in preflight]
        if (
            errors
            or len(set(hashes)) != 1
            or hashes[0] is None
            or len(set(owners)) != 1
            or not 0 <= owners[0] < self.comm.size
        ):
            detail = "; ".join(errors) if errors else (
                "replicated g or owner identity differs by rank"
            )
            raise ValueError(f"V13 collective S_B RHS preflight rejected: {detail}")
        payload = None
        if self.rank == self.modal_owner:
            try:
                if self.modal_schur is None or self.lu is None or self.pivots is None:
                    raise RuntimeError("V13 owner Schur/LU storage is unavailable")
                solution = np.asarray(
                    lu_solve((self.lu, self.pivots), values, check_finite=True),
                    dtype=np.complex128,
                )
                residual = np.asarray(
                    self.modal_schur @ solution - values, dtype=np.complex128
                )
                matrix_norm = float(np.linalg.norm(self.modal_schur, ord="fro"))
                solution_norm = float(np.linalg.norm(solution))
                rhs_norm = float(np.linalg.norm(values))
                residual_norm = float(np.linalg.norm(residual))
                scale = rhs_norm if rhs_norm > 0.0 else matrix_norm * solution_norm
                relative = (
                    residual_norm / scale
                    if scale > 0.0
                    else (0.0 if residual_norm == 0.0 else float("inf"))
                )
                residual_passed = bool(
                    np.all(np.isfinite(solution))
                    and np.all(np.isfinite(residual))
                    and np.isfinite(relative)
                    and relative <= 1.0e-10
                )
                self._owner_lu_solve_count += 1
                input_unchanged = hashlib.sha256(
                    np.ascontiguousarray(values).tobytes()
                ).hexdigest() == digest
                trusted_iterate = bool(
                    input_unchanged
                    and np.all(np.isfinite(values))
                    and np.all(np.isfinite(solution))
                    and np.all(np.isfinite(residual))
                    and np.isfinite(relative)
                )
                passed = bool(residual_passed and trusted_iterate)
                record = {
                    "status": "passed" if passed else "rejected",
                    "equation": "S_B a - g",
                    "residual_norm": residual_norm,
                    "scale": scale,
                    "relative_backward_error": relative,
                    "tolerance": 1.0e-10,
                    "residual_passed": residual_passed,
                    "matrix_norm_frobenius": matrix_norm,
                    "rhs_norm": rhs_norm,
                    "solution_norm": solution_norm,
                    "owner_lu_solve_count": self._owner_lu_solve_count,
                    "owner_rank": self.modal_owner,
                    "trusted_iterate": trusted_iterate,
                    "input_unchanged": input_unchanged,
                }
                if not passed and trusted_iterate and self._snapshot_callback is not None:
                    try:
                        snapshot_record = self._snapshot_callback(
                            {
                                "snapshot_kind": "terminal_normal_reject",
                                "g": values.copy(),
                                "m": solution.copy(),
                                "raw_residual": residual * -1.0,
                                "trusted_iterate": True,
                                "scalar_history": [],
                                "policy_id": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                                "method": self.method,
                                "solve_record": dict(record),
                            }
                        )
                        record["snapshot_record"] = (
                            None
                            if snapshot_record is None
                            else dict(snapshot_record)
                        )
                    except Exception as exc:  # noqa: BLE001 - retain the numerical reject and writer error
                        record["snapshot_error"] = {
                            "type": type(exc).__name__,
                            "message": str(exc)[:240],
                        }
                payload = {
                    "solution": solution,
                    "record": record,
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - broadcast owner solve failure to every rank
                payload = {
                    "solution": None,
                    "record": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        payload = self.comm.bcast(payload, root=self.modal_owner)
        self._solve_count += 1
        if not isinstance(payload, Mapping) or payload.get("error") is not None:
            message = (
                "owner returned no solve record"
                if not isinstance(payload, Mapping)
                else str(payload.get("error"))
            )
            raise RuntimeError(f"V13 owner LU solve failed: {message}")
        solution = np.asarray(payload.get("solution"), dtype=np.complex128)
        record = payload.get("record")
        if not isinstance(record, Mapping):
            raise FloatingPointError("V13 S_B owner returned no numerical record")
        self._last_solve = dict(record)
        if solution.shape != (self.modal_count,) or not np.all(np.isfinite(solution)):
            raise FloatingPointError("V13 S_B owner returned an invalid iterate")
        if record.get("status") != "passed":
            snapshot_error = record.get("snapshot_error")
            suffix = (
                ""
                if not isinstance(snapshot_error, Mapping)
                else "; terminal snapshot failed: "
                + str(snapshot_error.get("message", "unknown writer error"))
            )
            raise FloatingPointError(
                "V13 S_B a-g residual gate rejected the solve" + suffix
            )
        return solution.copy()

    def record_pc_apply_attempt(self, record: Mapping[str, Any]) -> None:
        self._last_pc_apply_attempt = _v13_json_safe(dict(record))

    def record_pc_apply_success(self, record: Mapping[str, Any]) -> None:
        self._last_pc_apply_success = _v13_json_safe(dict(record))

    def record_original_modal_row(
        self,
        record: Mapping[str, Any],
        arrays: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        """Freeze row scalars and owned arrays before any cleanup begins."""

        self._last_original_modal_row = _v13_json_safe(dict(record))
        self._last_original_modal_row_arrays = (
            None
            if arrays is None
            else {
                str(name): np.asarray(value).copy()
                for name, value in arrays.items()
            }
        )

    def persist_v13_evidence_snapshot(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Owner writes a bounded V13 snapshot; all ranks receive the same result."""

        owner_result = None
        if self.rank == self.modal_owner:
            try:
                if not callable(self._snapshot_callback):
                    raise TypeError("V13 snapshot callback is not configured")
                slot = payload.get("snapshot_kind")
                if not isinstance(slot, str) or slot in self._original_modal_row_snapshot_slots:
                    raise RuntimeError(f"V15 snapshot slot is unavailable: {slot!r}")
                written = self._snapshot_callback(payload)
                if not isinstance(written, Mapping):
                    raise TypeError("V13 snapshot callback returned no receipt")
                owner_result = {"error": None, "receipt": dict(written)}
            except Exception as exc:  # noqa: BLE001 - report writer failure without replacing a row failure
                owner_result = {
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc)[:240],
                    },
                    "receipt": None,
                }
        result = self.comm.bcast(owner_result, root=self.modal_owner)
        if not isinstance(result, Mapping):
            return {
                "status": "failed",
                "error": {"type": "ProtocolError", "message": "invalid snapshot broadcast"},
                "receipt": None,
            }
        if result.get("error") is not None:
            return {
                "status": "failed",
                "error": dict(result["error"]),
                "receipt": None,
            }
        receipt = result.get("receipt")
        if isinstance(receipt, Mapping):
            slot = payload.get("snapshot_kind")
            if isinstance(slot, str):
                self._original_modal_row_snapshot_slots.add(slot)
        return {
            "status": "written" if isinstance(receipt, Mapping) else "failed",
            "error": None if isinstance(receipt, Mapping) else {
                "type": "ProtocolError",
                "message": "snapshot receipt is missing",
            },
            "receipt": None if not isinstance(receipt, Mapping) else dict(receipt),
        }

    def frozen_original_modal_row(self) -> dict[str, Any] | None:
        """Read only the pre-destroy scalar and array copies, never live getters."""

        if self._last_original_modal_row is None:
            return None
        return {
            "record": dict(self._last_original_modal_row),
            "arrays": (
                None
                if self._last_original_modal_row_arrays is None
                else {
                    name: value.copy()
                    for name, value in self._last_original_modal_row_arrays.items()
                }
            ),
            "snapshot_receipt": (
                None
                if self._last_original_modal_row_snapshot_receipt is None
                else dict(self._last_original_modal_row_snapshot_receipt)
            ),
        }

    def record_side_operation_counts(
        self, counts: Mapping[str, Mapping[str, int]]
    ) -> None:
        if set(counts) != {"bottom", "top"}:
            raise ValueError("V13 side-operation audit must contain both sides")
        self._side_operation_after = {
            side: {key: int(value) for key, value in counts[side].items()}
            for side in ("bottom", "top")
        }

    @staticmethod
    def _side_operation_deltas(
        baseline: Mapping[str, Mapping[str, int]] | None,
        after: Mapping[str, Mapping[str, int]] | None,
    ) -> dict[str, dict[str, int]] | None:
        if baseline is None or after is None:
            return None
        if set(baseline) != {"bottom", "top"} or set(after) != {"bottom", "top"}:
            return None
        result = {}
        for side in ("bottom", "top"):
            keys = ("apply_count", "total_iterations")
            if any(key not in baseline[side] or key not in after[side] for key in keys):
                return None
            result[side] = {
                key: int(after[side][key]) - int(baseline[side][key])
                for key in keys
            }
        return result

    def _actual_action_work_diagnostics(self) -> dict[str, Any]:
        """Expose rank-local cumulative counters at this outer/final read."""

        snapshots = self.build_audit.get("actual_work_phase_snapshots")
        before_phase = (
            snapshots.get("before_build") if isinstance(snapshots, Mapping) else None
        )
        setup_phase = (
            snapshots.get("after_independent_validation")
            if isinstance(snapshots, Mapping)
            else None
        )

        def side_snapshot(phase: Any, side: str) -> Mapping[str, Any] | None:
            if not isinstance(phase, Mapping):
                return None
            rows = phase.get("rank_rows")
            if not isinstance(rows, (list, tuple)) or self.rank >= len(rows):
                return None
            row = rows[self.rank]
            actions = row.get("actions") if isinstance(row, Mapping) else None
            value = actions.get(side) if isinstance(actions, Mapping) else None
            return value if isinstance(value, Mapping) else None

        current = {
            "bottom": _v13_action_work_snapshot(self.bottom_action),
            "top": _v13_action_work_snapshot(self.top_action),
        }
        since_builder = {}
        since_setup = {}
        for side in ("bottom", "top"):
            baseline = side_snapshot(before_phase, side)
            setup = side_snapshot(setup_phase, side)
            since_builder[side] = (
                None
                if baseline is None
                else _v13_action_work_delta(baseline, current[side])
            )
            since_setup[side] = (
                None
                if setup is None
                else _v13_action_work_delta(setup, current[side])
            )
        return {
            "scope": (
                "rank-local existing side callback counters plus fixed-Q audit; "
                "do not sum replicated/global counts across ranks or add fixed-Q "
                "factor deltas to the shared P4 backsolve counter"
            ),
            "observation_boundary": "this diagnostics/inventory read; finalizer must persist its final read",
            "current_by_side": current,
            "delta_since_builder_begin_by_side": since_builder,
            "delta_since_independent_validation_by_side": since_setup,
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        owner_bytes = (
            sum(
                int(self._array_bytes[key])
                for key in ("modal_schur_bytes", "lu_bytes", "pivots_bytes")
            )
            if self.rank == self.modal_owner
            else 0
        )
        side_operation_deltas = self._side_operation_deltas(
            self.side_operation_baseline, self._side_operation_after
        )
        side_operation_zero = bool(
            side_operation_deltas is not None
            and all(
                count == 0
                for side_counts in side_operation_deltas.values()
                for count in side_counts.values()
            )
        )
        return {
            "schema": "task041.v13.consistent_modal_surrogate.v1",
            "policy_id": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
            "method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
            "rank": self.rank,
            "modal_owner": self.modal_owner,
            **self._modal_schur_diagnostic_fields,
            "modal_schur_local_bytes": int(self._array_bytes["modal_schur_bytes"]),
            **self._array_bytes,
            "owner_factor_local_bytes": (
                int(self._array_bytes["lu_bytes"])
                + int(self._array_bytes["pivots_bytes"])
            ),
            "owner_retained_modal_bytes": owner_bytes,
            "owner_storage_plan": dict(self.storage_plan),
            "condition": self.condition,
            "modal_linear_solver": "owner_local_scipy_lu",
            "modal_ksp_handle_count": int(self._modal_ksp_handle is not None),
            "modal_ksp_solve_count": int(self._modal_ksp_solve_call_count),
            "owner_lu_factor_count_local": int(self.lu is not None),
            "modal_ksp_call_scope": "no_modal_ksp_object; owner_local_scipy_lu",
            "side_operation_baseline": (
                None
                if self.side_operation_baseline is None
                else {
                    side: dict(counts)
                    for side, counts in self.side_operation_baseline.items()
                }
            ),
            "side_operation_after": (
                None
                if self._side_operation_after is None
                else {
                    side: dict(counts)
                    for side, counts in self._side_operation_after.items()
                }
            ),
            "side_operation_deltas": side_operation_deltas,
            "side_solver_entry_zero_supported": side_operation_zero,
            "actual_action_work": self._actual_action_work_diagnostics(),
            "owner_lu_solve_count": self._owner_lu_solve_count,
            "solve_count": self._solve_count,
            "last_pc_apply_attempt": (
                None
                if self._last_pc_apply_attempt is None
                else dict(self._last_pc_apply_attempt)
            ),
            "last_pc_apply_success": (
                None
                if self._last_pc_apply_success is None
                else dict(self._last_pc_apply_success)
            ),
            "last_solve": (
                None if self._last_solve is None else dict(self._last_solve)
            ),
            "last_original_modal_row": (
                None
                if self._last_original_modal_row is None
                else dict(self._last_original_modal_row)
            ),
            "last_original_modal_row_snapshot_receipt": (
                None
                if self._last_original_modal_row_snapshot_receipt is None
                else dict(self._last_original_modal_row_snapshot_receipt)
            ),
            "borrowed_action_identity": {
                "bottom_id": id(self.bottom_action),
                "top_id": id(self.top_action),
                "not_owned": True,
            },
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.modal_schur = None
        self.modal_constraint = None
        self.lu = None
        self.pivots = None
        self._destroyed = True


def _v13_canonicalize_rank_elapsed(
    comm: MPI.Intracomm,
    report: Mapping[str, Any],
    *,
    metric: str,
    local_elapsed_seconds: float,
) -> dict[str, Any]:
    """Return one identical, hashable report containing every rank's timing."""

    local_row = {
        "rank": int(comm.rank),
        "elapsed_seconds": float(local_elapsed_seconds),
    }
    rank_rows = comm.allgather(local_row)
    if (
        len(rank_rows) != comm.size
        or [row.get("rank") for row in rank_rows] != list(range(comm.size))
        or any(
            not np.isfinite(row.get("elapsed_seconds", float("nan")))
            or row["elapsed_seconds"] < 0.0
            for row in rank_rows
        )
    ):
        raise ValueError(f"V13 {metric} elapsed-time rows are invalid")
    canonical = dict(report)
    canonical[f"{metric}_elapsed_seconds_max_rank"] = max(
        float(row["elapsed_seconds"]) for row in rank_rows
    )
    canonical[f"{metric}_elapsed_seconds_by_rank"] = [
        {
            "rank": int(row["rank"]),
            "elapsed_seconds": float(row["elapsed_seconds"]),
        }
        for row in rank_rows
    ]
    return canonical


def _v13_matrix_local_sizes(matrix: Any, name: str) -> tuple[int, int]:
    if not isinstance(matrix, PETSc.Mat):
        raise TypeError(f"V13 memory inventory requires PETSc Mat {name}")
    rows, columns = matrix.getLocalSize()
    values = (int(rows), int(columns))
    if any(value < 0 for value in values):
        raise ValueError(f"V13 memory inventory has negative local size for {name}")
    return values


def _v13_local_workspace_inventory(
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
    *,
    original_augmented_local_size: int,
    internal_count: int,
    owner: int,
    comm: MPI.Intracomm,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Count the V13 setup's actual local PETSc vector layouts without allocating Vecs.

    The returned peak is a source-derived slot count over the nested call graph:
    one modal-column action, its two traction products, the full-space BAL_H
    recurrence, its condensed P4 RHS/solve/result vectors, the later LDU work
    vectors, and the three retained original-A validation vectors.  Side KSPs
    have already run KSPSetUp in SideBalancedInverse.__init__; their work bases
    are resident in the fresh sample and are recorded separately, not charged
    again as transient Vecs.
    """

    scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
    if scalar_bytes != np.dtype(np.complex128).itemsize:
        raise ValueError("V13 local workspace model requires complex128 PETSc Vecs")
    if (
        isinstance(original_augmented_local_size, bool)
        or not isinstance(original_augmented_local_size, int)
        or original_augmented_local_size < 0
    ):
        raise ValueError("V13 original-A local Vec size is invalid")

    local_error = None
    local_row: dict[str, Any] = {"rank": int(comm.rank)}
    try:
        side_rows: dict[str, dict[str, Any]] = {}
        persistent_ldu_entries = 0
        action_workspace_entries: list[int] = []
        preexisting_h6_entries = 0
        for side, action in (("bottom", bottom_action), ("top", top_action)):
            inverse = getattr(action, "_side_inverse", None)
            if inverse is None or getattr(inverse, "_destroyed", True):
                raise RuntimeError(f"V13 {side} fixed-B action has no live side inverse")
            operator = _action_operator(action)
            operator_left, operator_right = _v13_matrix_local_sizes(
                operator, f"{side}.active_operator"
            )
            full_action = getattr(inverse, "_full_action", None)
            full_matrix = getattr(full_action, "matrix", None)
            full_left, full_right = _v13_matrix_local_sizes(
                full_matrix, f"{side}.full_P6_action"
            )
            p4_factor = getattr(inverse, "_p4_factor", None)
            p4_inverse = getattr(p4_factor, "inverse", None)
            condensed = getattr(p4_inverse, "condensed", None)
            condensed_matrix = getattr(condensed, "matrix", None)
            coarse_left, coarse_right = _v13_matrix_local_sizes(
                condensed_matrix, f"{side}.condensed_P4_matrix"
            )
            p4_physical_action = getattr(p4_factor, "physical_action", None)
            p4_physical_matrix = getattr(p4_physical_action, "matrix", None)
            p4_full_left, p4_full_right = _v13_matrix_local_sizes(
                p4_physical_matrix, f"{side}.P4_physical_action"
            )
            projection = (
                coupling.bottom.projection if side == "bottom" else coupling.top.projection
            )
            projection_left, projection_right = _v13_matrix_local_sizes(
                projection, f"{side}.projection"
            )
            block = coupling.bottom if side == "bottom" else coupling.top
            positive_left, positive_right = _v13_matrix_local_sizes(
                block.positive_traction, f"{side}.positive_traction"
            )
            negative_left, negative_right = _v13_matrix_local_sizes(
                block.negative_traction, f"{side}.negative_traction"
            )
            if (
                positive_left != negative_left
                or positive_right != negative_right
                or coarse_left != coarse_right
            ):
                raise ValueError(f"V13 {side} work-vector layouts are incompatible")

            # modal_coupling_action keeps both right inputs and both left
            # products until the sum is formed.  The nested peak then includes
            # its returned traction, the caller's response/projection Vecs,
            # full_source plus six simultaneously live recurrence Vecs, the
            # active extraction target, and the coarse RHS/reduced/solve/output
            # Vecs in P4CellCondensedInverse.apply.
            modal_coupling_peak = (
                positive_right + negative_right + positive_left + negative_left
            )
            # P4CellCondensedExactFactor.apply has two relevant live-vector
            # phases.  _residual_state holds its input RHS, current solution,
            # effective RHS, action output, residual, and augmented residual.
            # During the one correction solve it holds the original RHS,
            # current solution, residual input, correction output, plus the
            # condensed reduced RHS and factor solution.  These layouts come
            # from the actual P4 physical and condensed matrices respectively;
            # the P4 inverse itself creates no separate full-layout residual.
            p4_full_peak = max(p4_full_left, p4_full_right)
            p4_initial_inverse_peak = (
                2 * p4_full_peak + coarse_left + coarse_right
            )
            p4_residual_state_peak = 6 * p4_full_peak
            p4_correction_inverse_peak = (
                4 * p4_full_peak + coarse_left + coarse_right
            )
            p4_q_call_peak = max(
                p4_initial_inverse_peak,
                p4_residual_state_peak,
                p4_correction_inverse_peak,
            )
            nested_balh_peak = (
                positive_left
                + operator_left
                + projection_left
                + full_right
                + 6 * full_left
                + operator_left
                + p4_q_call_peak
            )
            action_workspace_entries.append(max(modal_coupling_peak, nested_balh_peak))

            # These two vectors are allocated by FixedH6ActiveTraceAction at
            # factory creation, before both fresh-authority checkpoints.
            preexisting_h6_entries += 2 * full_left

            # HybridBlockLduPreconditioner.__init__ retains, per side, RHS,
            # first, delta, coupling, projection, and positive/negative
            # traction source/target Vecs.  Count each actual layout once.
            persistent_ldu_entries += (
                operator_right
                + 3 * operator_left
                + projection_left
                + positive_right
                + negative_right
                + positive_left
                + negative_left
            )
            side_rows[side] = {
                "active_operator_local_left_entries": operator_left,
                "active_operator_local_right_entries": operator_right,
                "positive_traction_local_left_entries": positive_left,
                "positive_traction_local_right_entries": positive_right,
                "negative_traction_local_left_entries": negative_left,
                "negative_traction_local_right_entries": negative_right,
                "projection_local_left_entries": projection_left,
                "projection_local_right_entries": projection_right,
                "full_P6_action_local_left_entries": full_left,
                "full_P6_action_local_right_entries": full_right,
                "condensed_P4_local_left_entries": coarse_left,
                "condensed_P4_local_right_entries": coarse_right,
                "P4_physical_full_local_left_entries": p4_full_left,
                "P4_physical_full_local_right_entries": p4_full_right,
                "P4_Q_call_peak_vec_entries": p4_q_call_peak,
                "P4_Q_call_peak_components": {
                    "initial_inverse": p4_initial_inverse_peak,
                    "residual_state": p4_residual_state_peak,
                    "one_correction_inverse": p4_correction_inverse_peak,
                },
                "P4_Q_call_known_vector_roles": {
                    "initial_inverse": [
                        "P4 full RHS",
                        "condensed reduced RHS",
                        "condensed factor solution",
                        "P4 full returned solution",
                    ],
                    "residual_state": [
                        "P4 full RHS",
                        "P4 full current solution",
                        "P4 full effective RHS",
                        "P4 full action output",
                        "P4 full residual",
                        "P4 full augmented residual",
                    ],
                    "one_correction_inverse": [
                        "P4 full RHS",
                        "P4 full current solution",
                        "P4 full residual input",
                        "P4 full correction output",
                        "condensed reduced RHS",
                        "condensed factor solution",
                    ],
                    "inverse_internal_full_residual_vec": False,
                },
                "modal_coupling_peak_vec_entries": modal_coupling_peak,
                "nested_fixed_B_peak_vec_entries": nested_balh_peak,
                "preexisting_FixedH6_work_vec_entries": 2 * full_left,
            }

        # Each side recovers cells serially.  Record both layouts and take the
        # largest simultaneously live cell scratch across the two sides; an
        # owner with no cells is valid and contributes zero for that side.
        recovery_rows: dict[str, Any] = {}
        max_cell_scratch_entries = 0
        max_cell_shape = None
        max_cell_side = None
        for side, action in (("bottom", bottom_action), ("top", top_action)):
            inverse = getattr(action, "_side_inverse", None)
            p4_factor = getattr(inverse, "_p4_factor", None)
            p4_inverse = getattr(p4_factor, "inverse", None)
            recovery_system = getattr(p4_inverse, "condensed", None)
            cells = getattr(recovery_system, "cell_recovery_maps", None)
            if not isinstance(cells, (list, tuple)):
                raise TypeError(f"V13 {side} P4 recovery cell inventory is unavailable")
            side_max_entries = 0
            side_max_shape = None
            for cell in cells:
                interior_count = len(cell.interior_original_dofs)
                trace_count = len(cell.trace_original_dofs)
                entries = 3 * interior_count + 2 * trace_count
                if entries > side_max_entries:
                    side_max_entries = entries
                    side_max_shape = {
                        "interior_rows": int(interior_count),
                        "trace_rows": int(trace_count),
                    }
            recovery_rows[side] = {
                "local_cell_count": len(cells),
                "max_cell_scratch_numpy_entries": int(side_max_entries),
                "max_cell_shape": side_max_shape,
            }
            if side_max_entries > max_cell_scratch_entries:
                max_cell_scratch_entries = side_max_entries
                max_cell_shape = side_max_shape
                max_cell_side = side

        local_row.update(
            {
                "side_layouts": side_rows,
                "persistent_LDU_work_vec_entries": int(persistent_ldu_entries),
                "original_A_validation_vec_entries": int(
                    3 * original_augmented_local_size
                ),
                "persistent_modal_rhs_and_solution_numpy_entries": int(
                    2 * internal_count
                ),
                "B_action_peak_vec_entries": int(max(action_workspace_entries)),
                "preexisting_FixedH6_work_vec_entries": int(
                    preexisting_h6_entries
                ),
                "max_local_cell_recovery_numpy_entries": int(
                    max_cell_scratch_entries
                ),
                "max_local_cell_shape": max_cell_shape,
                "max_local_cell_recovery_side": max_cell_side,
                "local_cell_recovery_by_side": recovery_rows,
                "replicated_modal_numpy_peak_entries": int(8 * internal_count),
                "full_action_validation_numpy_peak_entries": int(
                    14 * internal_count
                ),
                "owner_modal_LU_solve_temporary_numpy_entries": int(
                    4 * internal_count if comm.rank == owner else 0
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001 - synchronize rank-local layout failures
        local_error = f"{type(exc).__name__}: {exc}"
    local_row["error"] = local_error
    rank_rows = comm.allgather(local_row)
    failures = [
        f"rank {row['rank']}: {row['error']}"
        for row in rank_rows
        if row.get("error") is not None
    ]
    if failures:
        raise ValueError("V13 local workspace inventory rejected: " + "; ".join(failures))

    temporary_bytes = [
        int(
            scalar_bytes
            * (
                row["B_action_peak_vec_entries"]
                + row["max_local_cell_recovery_numpy_entries"]
            )
        )
        for row in rank_rows
    ]
    replicated_column_bytes = [
        int(scalar_bytes * row["replicated_modal_numpy_peak_entries"])
        for row in rank_rows
    ]
    full_validation_bytes = [
        int(scalar_bytes * row["full_action_validation_numpy_peak_entries"])
        for row in rank_rows
    ]
    owner_lu_temporary_bytes = [
        int(scalar_bytes * row["owner_modal_LU_solve_temporary_numpy_entries"])
        for row in rank_rows
    ]
    new_persistent_bytes = [
        int(
            scalar_bytes
            * (
                row["persistent_LDU_work_vec_entries"]
                + row["original_A_validation_vec_entries"]
                + row["persistent_modal_rhs_and_solution_numpy_entries"]
            )
        )
        for row in rank_rows
    ]
    inventory = {
        "source": "PETSc Mat local sizes plus V13/P4/LDU allocation call graph",
        "scalar_bytes": scalar_bytes,
        "rank_rows": [
            {key: value for key, value in row.items() if key != "error"}
            for row in rank_rows
        ],
        "additional_temporary_petcs_and_cell_numpy_bytes_by_rank": temporary_bytes,
        "additional_replicated_modal_column_numpy_bytes_by_rank": replicated_column_bytes,
        "additional_full_action_validation_numpy_bytes_by_rank": full_validation_bytes,
        "additional_replicated_numpy_bytes_by_rank": [
            max(replicated_column_bytes[rank], full_validation_bytes[rank])
            for rank in range(comm.size)
        ],
        "additional_owner_modal_LU_solve_temporary_numpy_bytes_by_rank": owner_lu_temporary_bytes,
        "future_persistent_LDU_and_original_A_vec_bytes_by_rank": new_persistent_bytes,
        "preexisting_FixedH6_work_vecs_already_in_fresh_B": True,
        "side_KSP_SetUp_completed_before_V13_builder": True,
        "side_KSP_basis_bytes": "already present in fresh B; not charged again",
        "scope_limit": (
            "known PETSc Vec and bounded one-cell NumPy scratch; Python/MPI allocator headers "
            "remain policy uncertainty, not represented as zero"
        ),
    }
    return rank_rows, inventory


def build_task041_v13_consistent_modal_surrogate(
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
    *,
    modal_owner: int,
    sampled_columns: Sequence[int],
    sampled_column_roles: Mapping[str, Sequence[str]],
    sampled_column_contract_sha256: str,
    original_augmented_local_size: int,
    fresh_authority_callback: Callable[
        [str, Mapping[str, Any]], Mapping[str, Any]
    ] | None,
    snapshot_callback: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
    | None = None,
    owner_storage_limit_bytes: int = 268_435_456,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Task041V13ConsistentModalSurrogateSystem:
    """Build ``S_B=C-LBG`` once, retaining the eight registered columns.

    The default historical builder is deliberately untouched.  V13 applies
    each borrowed fixed approximate B side action once per matrix column; seven
    fixed full-complex action checks are a separately costed setup scope.
    """
    comm = _action_operator(bottom_action).getComm().tompi4py()
    modal_count = int(coupling.mode_count_per_direction)
    internal_count = 2 * modal_count
    contract = None
    owner = None
    local_error = None
    try:
        owner = int(modal_owner)
        top_comm = _action_operator(top_action).getComm().tompi4py()
        if MPI.Comm.Compare(comm, top_comm) not in (MPI.IDENT, MPI.CONGRUENT):
            raise ValueError("bottom/top V13 action communicators differ")
        if not 0 <= owner < comm.size:
            raise ValueError("V13 modal owner is outside the communicator")
        if type(owner_storage_limit_bytes) is not int or owner_storage_limit_bytes <= 0:
            raise ValueError("V13 owner storage limit must be a positive integer")
        if not callable(fresh_authority_callback):
            raise TypeError("V13 requires a sealed fresh-authority callback")
        contract = _sampled_modal_column_contract(
            sampled_columns,
            sampled_column_roles,
            sampled_column_contract_sha256,
            internal_count,
            modal_count,
        )
        if contract is None or len(contract["columns"]) != 8:
            raise ValueError("V13 requires exactly eight sealed Schur columns")
        offsets = (0, 1, modal_count // 2, modal_count - 1)
        expected_columns = [
            *offsets,
            *(modal_count + offset for offset in offsets),
        ]
        if contract["columns"] != expected_columns:
            raise ValueError(
                "V13 sample columns do not match the frozen positive/negative order"
            )
        role_rows = contract["roles"]
        bottom_columns = [
            column
            for column in contract["columns"]
            if "bottom_positive_unattenuated" in role_rows[str(column)]
        ]
        top_columns = [
            column
            for column in contract["columns"]
            if "top_negative_unattenuated" in role_rows[str(column)]
        ]
        if (
            bottom_columns != expected_columns[:4]
            or top_columns != expected_columns[4:]
        ):
            raise ValueError(
                "V13 requires four positive-bottom and four negative-top columns"
            )
    except Exception as exc:  # noqa: BLE001 - agree on local contract errors before allocation
        local_error = f"{type(exc).__name__}: {exc}"
    local_identity = {
        "error": local_error,
        "modal_owner": owner,
        "internal_count": internal_count,
        "sample_columns": None if contract is None else list(contract["columns"]),
        "sample_sha256": (
            None if contract is None else contract.get("sha256")
        ),
        "owner_storage_limit_bytes": owner_storage_limit_bytes,
    }
    identities = comm.allgather(local_identity)
    failures = [
        f"rank {rank}: {row['error']}"
        for rank, row in enumerate(identities)
        if row.get("error") is not None
    ]
    normalized = [
        {key: value for key, value in row.items() if key != "error"}
        for row in identities
    ]
    if failures or any(row != normalized[0] for row in normalized[1:]):
        reason = "; ".join(failures) if failures else "rank-local V13 inputs differ"
        raise ValueError(f"V13 collective construction preflight rejected: {reason}")
    assert contract is not None
    columns = list(contract["columns"])
    owner = int(identities[0]["modal_owner"])
    _workspace_rank_rows, workspace_inventory = _v13_local_workspace_inventory(
        coupling,
        bottom_action,
        top_action,
        original_augmented_local_size=original_augmented_local_size,
        internal_count=internal_count,
        owner=owner,
        comm=comm,
    )
    dense_bytes = int(np.dtype(np.complex128).itemsize * internal_count**2)
    pivot_bytes = int(np.dtype(np.int32).itemsize * internal_count)
    # These are simultaneous dense NumPy-array payloads by builder phase.  The
    # maximum covers the C construction copies, retained C/S_B, owner LU plus
    # its factorization copy and pivots. PETSc vectors and B-action temporaries
    # are counted separately from their actual local matrix layouts below.
    storage_phases = {
        "constraint_build_peak_bytes": 4 * dense_bytes,
        "lu_factorization_peak_bytes": 4 * dense_bytes + pivot_bytes,
        "final_modal_constraint_bytes": dense_bytes,
        "final_owner_schur_bytes": dense_bytes,
        "final_owner_lu_bytes": dense_bytes,
        "owner_pivots_bytes": pivot_bytes,
        "owner_storage_limit_bytes": owner_storage_limit_bytes,
    }
    estimated_owner_peak = max(
        int(storage_phases["constraint_build_peak_bytes"]),
        int(storage_phases["lu_factorization_peak_bytes"]),
    )
    storage_phases["estimated_owner_peak_bytes"] = estimated_owner_peak
    storage_phases["estimate_scope"] = "derived_dense_arrays_not_RSS_or_LU_peak"
    temporary_by_rank = list(
        workspace_inventory[
            "additional_temporary_petcs_and_cell_numpy_bytes_by_rank"
        ]
    )
    replicated_by_rank = list(
        workspace_inventory["additional_replicated_modal_column_numpy_bytes_by_rank"]
    )
    full_validation_replicated_by_rank = list(
        workspace_inventory["additional_full_action_validation_numpy_bytes_by_rank"]
    )
    owner_lu_temporary_by_rank = list(
        workspace_inventory[
            "additional_owner_modal_LU_solve_temporary_numpy_bytes_by_rank"
        ]
    )
    future_persistent_by_rank = list(
        workspace_inventory[
            "future_persistent_LDU_and_original_A_vec_bytes_by_rank"
        ]
    )

    def phase_memory_projection(*, after_eight_columns: bool) -> dict[str, Any]:
        phase_components: dict[str, dict[str, list[int]]] = {}
        zero = [0] * comm.size
        if after_eight_columns:
            phase_components["remaining_column_actions"] = {
                "known_additional_bytes_by_rank": zero.copy(),
                "additional_temporary_bytes_by_rank": temporary_by_rank,
                "additional_replicated_bytes_by_rank": replicated_by_rank,
            }
            phase_components["independent_full_complex_action_validation"] = {
                "known_additional_bytes_by_rank": zero.copy(),
                "additional_temporary_bytes_by_rank": temporary_by_rank,
                "additional_replicated_bytes_by_rank": full_validation_replicated_by_rank,
            }
            factor_known = [0] * comm.size
            factor_known[owner] = max(0, estimated_owner_peak - 2 * dense_bytes)
            phase_components["owner_factorization_after_sample"] = {
                "known_additional_bytes_by_rank": factor_known,
                "additional_temporary_bytes_by_rank": zero.copy(),
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            repeat_known = [0] * comm.size
            repeat_known[owner] = dense_bytes + pivot_bytes
            repeat_temporary = [0] * comm.size
            repeat_temporary[owner] = owner_lu_temporary_by_rank[owner]
            phase_components["owner_LU_repeat_after_sample"] = {
                "known_additional_bytes_by_rank": repeat_known,
                "additional_temporary_bytes_by_rank": repeat_temporary,
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            retained_known = [0] * comm.size
            retained_known[owner] = dense_bytes + pivot_bytes
            retained_known = [
                retained_known[rank] + future_persistent_by_rank[rank]
                for rank in range(comm.size)
            ]
            phase_components["retained_LDU_and_original_A_vectors"] = {
                "known_additional_bytes_by_rank": retained_known,
                "additional_temporary_bytes_by_rank": zero.copy(),
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            runtime_known = list(retained_known)
            runtime_temporary = list(temporary_by_rank)
            runtime_replicated = list(replicated_by_rank)
            phase_components["outer_PC_with_retained_workspaces"] = {
                "known_additional_bytes_by_rank": runtime_known,
                "additional_temporary_bytes_by_rank": runtime_temporary,
                "additional_replicated_bytes_by_rank": runtime_replicated,
            }
            modal_solve_temporary = list(owner_lu_temporary_by_rank)
            phase_components["outer_PC_modal_LU_with_retained_arrays"] = {
                "known_additional_bytes_by_rank": list(retained_known),
                "additional_temporary_bytes_by_rank": modal_solve_temporary,
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
        else:
            phase_components["constraint_construction"] = {
                "known_additional_bytes_by_rank": [4 * dense_bytes] * comm.size,
                "additional_temporary_bytes_by_rank": zero.copy(),
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            column_known = [dense_bytes] * comm.size
            column_known[owner] += dense_bytes
            phase_components["sample_and_remaining_columns"] = {
                "known_additional_bytes_by_rank": column_known,
                "additional_temporary_bytes_by_rank": temporary_by_rank,
                "additional_replicated_bytes_by_rank": replicated_by_rank,
            }
            validation_known = list(column_known)
            phase_components["independent_full_complex_action_validation"] = {
                "known_additional_bytes_by_rank": validation_known,
                "additional_temporary_bytes_by_rank": temporary_by_rank,
                "additional_replicated_bytes_by_rank": full_validation_replicated_by_rank,
            }
            factor_known = [dense_bytes] * comm.size
            factor_known[owner] = estimated_owner_peak
            phase_components["owner_factorization"] = {
                "known_additional_bytes_by_rank": factor_known,
                "additional_temporary_bytes_by_rank": zero.copy(),
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            repeat_known = [dense_bytes] * comm.size
            repeat_known[owner] = 3 * dense_bytes + pivot_bytes
            repeat_temporary = [0] * comm.size
            repeat_temporary[owner] = owner_lu_temporary_by_rank[owner]
            phase_components["owner_LU_repeat_solves"] = {
                "known_additional_bytes_by_rank": repeat_known,
                "additional_temporary_bytes_by_rank": repeat_temporary,
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            retained_known = [dense_bytes] * comm.size
            retained_known[owner] = 3 * dense_bytes + pivot_bytes
            retained_known = [
                retained_known[rank] + future_persistent_by_rank[rank]
                for rank in range(comm.size)
            ]
            phase_components["retained_LDU_and_original_A_vectors"] = {
                "known_additional_bytes_by_rank": retained_known,
                "additional_temporary_bytes_by_rank": zero.copy(),
                "additional_replicated_bytes_by_rank": zero.copy(),
            }
            runtime_known = list(retained_known)
            runtime_temporary = list(temporary_by_rank)
            runtime_replicated = list(replicated_by_rank)
            phase_components["outer_PC_with_retained_workspaces"] = {
                "known_additional_bytes_by_rank": runtime_known,
                "additional_temporary_bytes_by_rank": runtime_temporary,
                "additional_replicated_bytes_by_rank": runtime_replicated,
            }
            phase_components["outer_PC_modal_LU_with_retained_arrays"] = {
                "known_additional_bytes_by_rank": list(retained_known),
                "additional_temporary_bytes_by_rank": list(owner_lu_temporary_by_rank),
                "additional_replicated_bytes_by_rank": zero.copy(),
            }

        totals = {}
        for name, components in phase_components.items():
            total_by_rank = [
                components["known_additional_bytes_by_rank"][rank]
                + components["additional_temporary_bytes_by_rank"][rank]
                + components["additional_replicated_bytes_by_rank"][rank]
                for rank in range(comm.size)
            ]
            components["additional_bytes_by_rank"] = total_by_rank
            totals[name] = sum(total_by_rank)
        selected = max(phase_components, key=lambda name: totals[name])
        result = {
            "scope": "source_counted_simultaneous_array_payload_by_phase_not_RSS",
            "already_live_C_and_owner_S_after_sample_are_in_fresh_B": bool(
                after_eight_columns
            ),
            "phase_reports": phase_components,
            "phase_total_bytes": totals,
            "selected_phase": selected,
            **phase_components[selected],
        }
        return result

    before_memory_projection = phase_memory_projection(after_eight_columns=False)
    owner_storage_pass = estimated_owner_peak <= owner_storage_limit_bytes
    if not comm.allreduce(owner_storage_pass, op=MPI.LAND):
        raise MemoryError(
            "V13 owner-local 256MiB storage policy refused before dense allocation: "
            f"estimated_dense_array_payload={estimated_owner_peak}, "
            f"limit={owner_storage_limit_bytes}"
        )

    def collective_authority_gate(
        phase: str, report: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        local_report_error = None
        local_report_digest = None
        try:
            canonical_report = json.dumps(
                dict(report),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            local_report_digest = hashlib.sha256(
                canonical_report.encode()
            ).hexdigest()
        except Exception as exc:  # noqa: BLE001 - agree before callback/bcast
            local_report_error = f"{type(exc).__name__}: {exc}"
        report_identities = comm.allgather(
            (local_report_error, local_report_digest)
        )
        report_failures = [
            f"rank {rank}: {error}"
            for rank, (error, _digest) in enumerate(report_identities)
            if error is not None
        ]
        report_digests = [
            digest for error, digest in report_identities if error is None
        ]
        if report_failures or len(report_digests) != comm.size:
            raise MemoryError(
                f"V13 {phase} report is unbindable: "
                + "; ".join(report_failures)
            )
        if len(set(report_digests)) != 1:
            raise MemoryError(
                f"V13 {phase} report differs across ranks and is unbindable"
            )
        report_digest = report_digests[0]
        local_response = None
        callback_error = None
        try:
            assert callable(fresh_authority_callback)
            local_response = fresh_authority_callback(phase, dict(report))
            if not isinstance(local_response, Mapping):
                raise TypeError("fresh-authority callback must return a mapping")
            local_response = dict(local_response)
        except Exception as exc:  # noqa: BLE001 - callback errors must be rank-consistent
            callback_error = f"{type(exc).__name__}: {exc}"
        gathered = comm.allgather((callback_error, local_response))
        callback_failures = [
            f"rank {rank}: {error}"
            for rank, (error, _response) in enumerate(gathered)
            if error is not None
        ]
        responses = [response for _error, response in gathered]
        if callback_failures or any(not isinstance(row, Mapping) for row in responses):
            details = "; ".join(callback_failures) or "callback result missing on a rank"
            raise MemoryError(f"V13 {phase} collective authority callback failed: {details}")
        typed = [dict(row) for row in responses]
        def valid_receipt(row: Mapping[str, Any]) -> bool:
            payload = row.get("authority_receipt_payload")
            if not isinstance(payload, Mapping):
                return False
            try:
                digest = hashlib.sha256(
                    json.dumps(
                        dict(payload),
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode()
                ).hexdigest()
            except (TypeError, ValueError):
                return False
            return bool(
                digest == row.get("authority_receipt_sha256")
                and payload.get("phase") == phase
                and payload.get("request_sha256") == report_digest
            )

        receipt_ids = [row.get("authority_receipt_sha256") for row in typed]
        response_valid = not any(
            row.get("schema") != "task041.v13.modal_builder_admission.v1"
            or row.get("phase") != phase
            or row.get("status") not in {"pass", "refused"}
            or row.get("decision") not in {"continue", "stop"}
            or row.get("request_sha256") != report_digest
            or not isinstance(row.get("authority_receipt_sha256"), str)
            or len(row["authority_receipt_sha256"]) != 64
            or not valid_receipt(row)
            for row in typed
        ) and len(set(receipt_ids)) == 1
        if not response_valid:
            if marker_callback is not None:
                marker_callback(
                    "v13_modal_authority_refused",
                    {
                        "phase": phase,
                        "status": "refused",
                        "reason": "authority_receipt_missing_or_not_recomputable",
                        "report": dict(report),
                        "rank_admission_records": typed,
                    },
                )
            raise MemoryError(f"V13 {phase} authority/admission was not unanimous")
        statuses = {row.get("status") for row in typed}
        decisions = {row.get("decision") for row in typed}
        if statuses == {"refused"} and decisions == {"stop"}:
            reasons = typed[0].get("reasons")
            if marker_callback is not None:
                marker_callback(
                    "v13_modal_authority_refused",
                    {
                        "phase": phase,
                        "status": "refused",
                        "report": dict(report),
                        "rank_admission_records": typed,
                        "authority_receipt_payload": typed[0].get(
                            "authority_receipt_payload"
                        ),
                        "authority_receipt_sha256": typed[0].get(
                            "authority_receipt_sha256"
                        ),
                    },
                )
            raise MemoryError(
                f"V13 {phase} fresh authority refused: "
                + ("; ".join(map(str, reasons)) if isinstance(reasons, list) else "unknown reason")
            )
        if statuses != {"pass"} or decisions != {"continue"}:
            raise MemoryError(f"V13 {phase} authority decision differs across ranks")
        common_fields = (
            "fresh_job_authority_bytes",
            "cap_bytes",
            "W_policy_reserve_bytes",
            "additional_bytes_by_rank",
            "additional_temporary_bytes_by_rank",
            "additional_replicated_bytes_by_rank",
            "selected_memory_phase",
            "selected_memory_phase_payload_bytes",
            "cost_assessment",
            "external_resource_gates",
        )
        if any(
            any(row.get(key) != typed[0].get(key) for key in common_fields)
            for row in typed[1:]
        ):
            raise MemoryError("V13 fresh resource contract differs across ranks")
        gate = typed[0]
        fresh = gate.get("fresh_job_authority_bytes")
        cap = gate.get("cap_bytes")
        reserve = gate.get("W_policy_reserve_bytes")
        additional = gate.get("additional_bytes_by_rank")
        temporary = gate.get("additional_temporary_bytes_by_rank")
        replicated = gate.get("additional_replicated_bytes_by_rank")
        external = gate.get("external_resource_gates")
        known = report.get("known_additional_bytes_by_rank")
        projection = report.get("phase_memory_projection")
        if (
            any(type(value) is not int or value < 0 for value in (fresh, reserve))
            or type(cap) is not int
            or cap <= 0
            or not isinstance(additional, list)
            or len(additional) != comm.size
            or any(type(value) is not int or value < 0 for value in additional)
            or not isinstance(temporary, list)
            or len(temporary) != comm.size
            or any(type(value) is not int or value < 0 for value in temporary)
            or not isinstance(replicated, list)
            or len(replicated) != comm.size
            or any(type(value) is not int or value < 0 for value in replicated)
            or not isinstance(external, Mapping)
            or not external
            or any(value is not True for value in external.values())
            or not isinstance(known, list)
            or len(known) != comm.size
            or any(type(value) is not int or value < 0 for value in known)
            or not isinstance(projection, Mapping)
            or not isinstance(projection.get("phase_reports"), Mapping)
            or projection.get("selected_phase")
            not in projection.get("phase_reports", {})
            or any(
                additional[rank]
                != known[rank] + temporary[rank] + replicated[rank]
                for rank in range(comm.size)
            )
        ):
            raise MemoryError(
                f"V13 {phase} fresh authority is incomplete or omits known storage"
            )
        phase_reports = projection.get("phase_reports")
        phase_totals = projection.get("phase_total_bytes")
        if not isinstance(phase_reports, Mapping) or not isinstance(phase_totals, Mapping):
            raise TypeError(f"V13 {phase} phase memory projection is incomplete")
        recomputed_totals = {}
        for phase_name, components in phase_reports.items():
            if not isinstance(components, Mapping):
                raise TypeError(f"V13 {phase} has a malformed phase row")
            component_rows = [
                components.get("known_additional_bytes_by_rank"),
                components.get("additional_temporary_bytes_by_rank"),
                components.get("additional_replicated_bytes_by_rank"),
            ]
            if any(
                not isinstance(values, list)
                or len(values) != comm.size
                or any(type(value) is not int or value < 0 for value in values)
                for values in component_rows
            ):
                raise MemoryError(f"V13 {phase} phase component rows are invalid")
            phase_additional = [
                sum(values[rank] for values in component_rows)
                for rank in range(comm.size)
            ]
            if components.get("additional_bytes_by_rank") != phase_additional:
                raise MemoryError(f"V13 {phase} phase total does not match components")
            recomputed_totals[phase_name] = sum(phase_additional)
        selected_phase = max(recomputed_totals, key=recomputed_totals.get)
        selected = phase_reports[selected_phase]
        selected_additional = [
            sum(
                selected[key][rank]
                for key in (
                    "known_additional_bytes_by_rank",
                    "additional_temporary_bytes_by_rank",
                    "additional_replicated_bytes_by_rank",
                )
            )
            for rank in range(comm.size)
        ]
        if (
            projection.get("selected_phase") != selected_phase
            or dict(phase_totals) != recomputed_totals
            or any(
                report.get(key) != selected.get(key)
                for key in (
                    "known_additional_bytes_by_rank",
                    "additional_temporary_bytes_by_rank",
                    "additional_replicated_bytes_by_rank",
                )
            )
            or additional != selected_additional
            or gate.get("selected_memory_phase") != selected_phase
            or gate.get("selected_memory_phase_payload_bytes") != sum(selected_additional)
            or any(
                gate.get(response_key) != report.get(report_key)
                for response_key, report_key in (
                    ("additional_temporary_bytes_by_rank", "additional_temporary_bytes_by_rank"),
                    ("additional_replicated_bytes_by_rank", "additional_replicated_bytes_by_rank"),
                )
            )
        ):
            raise MemoryError(f"V13 {phase} selected phase is not the largest forecast")
        projected = fresh + sum(additional) + reserve
        if projected > cap:
            raise MemoryError(
                f"V13 {phase} full-job authority gate refused: "
                f"fresh+rank_delta+W={projected} > cap={cap}"
            )
        gate["recomputed_projected_authority_bytes"] = projected
        gate["known_modal_storage_bytes_by_rank"] = list(known)
        return gate, typed

    authority_record, _authority_rank_records = collective_authority_gate(
        "before_dense_allocation",
        {
            "owner": owner,
            "modal_count_per_direction": modal_count,
            "internal_modal_count": internal_count,
            "known_additional_bytes_by_rank": list(
                before_memory_projection["known_additional_bytes_by_rank"]
            ),
            "additional_temporary_bytes_by_rank": list(
                before_memory_projection["additional_temporary_bytes_by_rank"]
            ),
            "additional_replicated_bytes_by_rank": list(
                before_memory_projection["additional_replicated_bytes_by_rank"]
            ),
            "phase_memory_projection": before_memory_projection,
            "workspace_inventory": workspace_inventory,
            "owner_local_storage_limit_bytes": owner_storage_limit_bytes,
            "estimate_scope": (
                "max simultaneous source-counted array payload by phase; "
                "allocator/MPI uncertainty remains in W"
            ),
        },
    )
    build_started = time.perf_counter()

    side_operation_baseline = {
        "bottom": _v13_side_operation_counts(bottom_action),
        "top": _v13_side_operation_counts(top_action),
    }
    local_side_counters_valid = all(
        isinstance(value, Mapping)
        and set(value) == {"apply_count", "total_iterations"}
        for value in side_operation_baseline.values()
    )
    if not comm.allreduce(local_side_counters_valid, op=MPI.LAND):
        raise RuntimeError(
            "V13 requires real SideBalancedInverse apply/iteration counters before construction"
        )

    bottom_before = int(_action_diagnostics(bottom_action).get("apply_count", 0))
    top_before = int(_action_diagnostics(top_action).get("apply_count", 0))
    actual_work_phase_snapshots: dict[str, dict[str, Any]] = {}
    previous_work_rank_rows: list[dict[str, Any]] | None = None

    def remember_actual_work_phase(
        phase: str, rank_rows: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        nonlocal previous_work_rank_rows
        rows = [dict(row) for row in rank_rows]
        previous_by_rank = (
            {}
            if previous_work_rank_rows is None
            else {
                int(row["rank"]): row
                for row in previous_work_rank_rows
            }
        )
        for row in rows:
            rank = int(row["rank"])
            previous = previous_by_rank.get(rank)
            previous_actions = (
                previous.get("actions")
                if isinstance(previous, Mapping)
                else None
            )
            current_actions = row.get("actions")
            if not isinstance(previous_actions, Mapping) or not isinstance(
                current_actions, Mapping
            ):
                row["action_work_delta_since_previous_phase"] = None
                continue
            row["action_work_delta_since_previous_phase"] = {
                side: (
                    None
                    if not isinstance(previous_actions.get(side), Mapping)
                    or not isinstance(current_actions.get(side), Mapping)
                    else _v13_action_work_delta(
                        previous_actions[side], current_actions[side]
                    )
                )
                for side in ("bottom", "top")
            }
        phase_record = {
            "phase": phase,
            "rank_count": int(comm.size),
            "elapsed_seconds_scope": "rank-local interval since previous recorded phase",
            "max_rank_elapsed_seconds": max(
                (float(row.get("elapsed_seconds", 0.0)) for row in rows),
                default=0.0,
            ),
            "max_rank_builder_elapsed_seconds": max(
                (float(row.get("builder_elapsed_seconds", 0.0)) for row in rows),
                default=0.0,
            ),
            "rank_rows": rows,
            "counter_scope": (
                "rank-local action/callback snapshots and deltas; do not multiply "
                "or sum replicated/global values across ranks"
            ),
        }
        actual_work_phase_snapshots[phase] = phase_record
        previous_work_rank_rows = rows
        return phase_record

    def collect_actual_work_phase(
        phase: str,
        *,
        local_elapsed_seconds: float,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        local_row = {
            "rank": int(comm.rank),
            "elapsed_seconds": float(local_elapsed_seconds),
            "builder_elapsed_seconds": float(time.perf_counter() - build_started),
            "actions": {
                "bottom": _v13_action_work_snapshot(bottom_action),
                "top": _v13_action_work_snapshot(top_action),
            },
        }
        if extra:
            local_row.update(dict(extra))
        rows = comm.allgather(local_row)
        return remember_actual_work_phase(phase, rows)

    before_build_work_phase = collect_actual_work_phase(
        "before_build", local_elapsed_seconds=0.0
    )
    constraint = None
    local_constraint_error = None
    constraint_digest = None
    try:
        constraint = np.asarray(
            internal_modal_constraint_matrix(coupling), dtype=np.complex128
        )
        if (
            constraint.shape != (internal_count, internal_count)
            or not np.all(np.isfinite(constraint))
        ):
            raise ValueError("V13 modal constraint has invalid shape or values")
        constraint_digest = hashlib.sha256(
            np.ascontiguousarray(constraint).tobytes()
        ).hexdigest()
    except Exception as exc:  # noqa: BLE001 - synchronize constraint validation
        local_constraint_error = f"{type(exc).__name__}: {exc}"
    constraint_rows = comm.allgather((local_constraint_error, constraint_digest))
    constraint_failures = [
        f"rank {rank}: {error}"
        for rank, (error, _digest) in enumerate(constraint_rows)
        if error is not None
    ]
    constraint_hashes = [digest for _error, digest in constraint_rows]
    if (
        constraint_failures
        or any(value != constraint_hashes[0] for value in constraint_hashes[1:])
        or constraint_hashes[0] is None
    ):
        detail = "; ".join(constraint_failures) or "C differs by rank"
        raise ValueError(f"V13 collective modal-constraint preflight rejected: {detail}")
    assert constraint is not None
    schur = None
    local_schur_error = None
    try:
        if comm.rank == owner:
            schur = np.empty((internal_count, internal_count), dtype=np.complex128)
            # Fault every page before the after-eight fresh-RSS checkpoint;
            # np.empty alone does not make untouched columns resident.
            schur.fill(np.complex128(0.0))
    except Exception as exc:  # noqa: BLE001 - synchronize owner allocation failure
        local_schur_error = f"{type(exc).__name__}: {exc}"
    schur_errors = comm.allgather(local_schur_error)
    schur_failures = [
        f"rank {rank}: {error}"
        for rank, error in enumerate(schur_errors)
        if error is not None
    ]
    if schur_failures:
        raise MemoryError("V13 owner Schur allocation failed; " + "; ".join(schur_failures))
    remaining = [column for column in range(internal_count) if column not in columns]
    if marker_callback is not None:
        marker_callback(
            "v13_modal_schur_build_begin",
            {
                "method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                "owner": owner,
                "sample_columns_retained_in_final_matrix": list(columns),
                "remaining_columns_built_once": len(remaining),
                "owner_storage_plan": dict(storage_phases),
                "fresh_authority": authority_record,
                "actual_work_phase": before_build_work_phase,
            },
        )

    def assemble_column(column: int) -> None:
        bottom_column = _build_action_modal_contribution(
            "bottom", coupling, bottom_action, modal_count, columns=(column,)
        )[:, 0]
        top_column = _build_action_modal_contribution(
            "top", coupling, top_action, modal_count, columns=(column,)
        )[:, 0]
        assembled = np.asarray(
            constraint[:, column] - bottom_column - top_column,
            dtype=np.complex128,
        )
        local_finite = bool(np.all(np.isfinite(assembled)))
        if not comm.allreduce(local_finite, op=MPI.LAND):
            raise FloatingPointError(
                f"V13 S_B column {column} is non-finite on at least one rank"
            )
        if comm.rank == owner:
            assert schur is not None
            schur[:, column] = assembled

    sample_started = time.perf_counter()
    for column in columns:
        assemble_column(column)
    first_eight_local_seconds = float(time.perf_counter() - sample_started)
    sample_rank_rows = comm.allgather(
        {
            "rank": int(comm.rank),
            "elapsed_seconds": first_eight_local_seconds,
            "builder_elapsed_seconds": float(time.perf_counter() - build_started),
            "bottom_B_apply_count": int(
                _action_diagnostics(bottom_action).get("apply_count", 0)
            )
            - bottom_before,
            "top_B_apply_count": int(
                _action_diagnostics(top_action).get("apply_count", 0)
            )
            - top_before,
            "actions": {
                "bottom": _v13_action_work_snapshot(bottom_action),
                "top": _v13_action_work_snapshot(top_action),
            },
        }
    )
    after_eight_work_phase = remember_actual_work_phase(
        "after_eight_columns", sample_rank_rows
    )
    max_rank_sample_seconds = max(
        float(row["elapsed_seconds"]) for row in sample_rank_rows
    )
    remaining = [column for column in range(internal_count) if column not in columns]
    independent_action_count = 7
    projected_remaining_seconds = max_rank_sample_seconds * (
        len(remaining) + independent_action_count
    ) / len(columns)
    sample_cost_report = {
        "phase": "after_eight_columns",
        "method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
        "sample_columns_written_to_final_matrix": list(columns),
        "sample_column_count": len(columns),
        "max_rank_sample_seconds": max_rank_sample_seconds,
        "rank_local_sample_work": sample_rank_rows,
        "actual_work_phase": after_eight_work_phase,
        "remaining_column_count": len(remaining),
        "remaining_projected_B_apply_count_by_side": {
            "bottom": len(remaining) + independent_action_count,
            "top": len(remaining) + independent_action_count,
        },
        "remaining_projected_work_scopes": {
            "remaining_matrix_columns": len(remaining),
            "independent_full_complex_action_checks": independent_action_count,
        },
        "remaining_projected_seconds": projected_remaining_seconds,
        "estimated_builder_seconds_at_sample": None,
        "remaining_cost_model": (
            "linear_projection_from_measured_first_eight_for_remaining_columns_and_"
            "seven_full_complex_action_checks; owner_LU_and_outer_solve_not_measured"
        ),
        "full_run_cost_target_seconds": 172800,
        "full_run_cost_target_semantics": "planning_target_only_no_elapsed_stop",
    }
    sample_cost_report["estimated_builder_seconds_at_sample"] = (
        float(time.perf_counter() - build_started) + projected_remaining_seconds
    )
    after_memory_projection = phase_memory_projection(after_eight_columns=True)
    sample_cost_report["known_additional_bytes_by_rank"] = list(
        after_memory_projection["known_additional_bytes_by_rank"]
    )
    sample_cost_report["additional_temporary_bytes_by_rank"] = list(
        after_memory_projection["additional_temporary_bytes_by_rank"]
    )
    sample_cost_report["additional_replicated_bytes_by_rank"] = list(
        after_memory_projection["additional_replicated_bytes_by_rank"]
    )
    sample_cost_report["phase_memory_projection"] = after_memory_projection
    sample_cost_report["workspace_inventory"] = workspace_inventory
    sample_cost_report["additional_memory_basis"] = {
        "fresh_sample_includes": (
            "replicated C and the full allocated owner S_B; neither is charged again"
        ),
        "selected_phase": after_memory_projection["selected_phase"],
        "workspace_inventory_source": workspace_inventory["source"],
        "future_persistent_LDU_and_original_A_vec_bytes_by_rank": list(
            future_persistent_by_rank
        ),
        "unknown_allocator_MPI_headers_and_library_scratch": (
            "not set to zero; retained as policy uncertainty in W"
        ),
        "scope": "phase maximum of known simultaneous payload, not an RSS bound",
    }
    sample_cost_report = _v13_canonicalize_rank_elapsed(
        comm,
        sample_cost_report,
        metric="assembly",
        local_elapsed_seconds=float(time.perf_counter() - build_started),
    )
    sample_cost_report["estimated_builder_seconds_at_sample"] = (
        float(sample_cost_report["assembly_elapsed_seconds_max_rank"])
        + projected_remaining_seconds
    )
    if marker_callback is not None:
        marker_callback("v13_modal_sample8_complete", sample_cost_report)
    try:
        sample_admission, sample_admission_rank_rows = collective_authority_gate(
            "after_eight_columns", sample_cost_report
        )
    except Exception as exc:
        if marker_callback is not None:
            marker_callback(
                "v13_modal_sample8_refused",
                {
                    **sample_cost_report,
                    "status": "refused",
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        raise
    if marker_callback is not None:
        marker_callback(
            "v13_modal_sample8_admitted",
            {
                **sample_cost_report,
                "admission": sample_admission,
                "rank_admission_records": sample_admission_rank_rows,
            },
        )
    remaining_interval_started = time.perf_counter()
    remaining_completed = 0
    for column in remaining:
        assemble_column(column)
        remaining_completed += 1
        completed_columns = len(columns) + remaining_completed
        if completed_columns % 32 == 0 and completed_columns < internal_count:
            progress_phase = collect_actual_work_phase(
                f"after_column_{completed_columns}",
                local_elapsed_seconds=(
                    time.perf_counter() - remaining_interval_started
                ),
                extra={
                    "completed_column_count": completed_columns,
                    "remaining_column_count": internal_count - completed_columns,
                    "progress_interval": "every_32_total_columns_after_sample8",
                },
            )
            if marker_callback is not None:
                marker_callback("v13_modal_schur_columns_progress", progress_phase)
            remaining_interval_started = time.perf_counter()
    after_all_columns_work_phase = collect_actual_work_phase(
        "after_all_columns",
        local_elapsed_seconds=time.perf_counter() - remaining_interval_started,
        extra={
            "completed_column_count": len(columns) + remaining_completed,
            "remaining_column_count": 0,
        },
    )
    if marker_callback is not None:
        marker_callback(
            "v13_modal_schur_columns_complete",
            after_all_columns_work_phase,
        )
    bottom_after_assembly = int(
        _action_diagnostics(bottom_action).get("apply_count", 0)
    )
    top_after_assembly = int(_action_diagnostics(top_action).get("apply_count", 0))
    expected_columns = internal_count
    if (
        bottom_after_assembly - bottom_before != expected_columns
        or top_after_assembly - top_before != expected_columns
    ):
        raise RuntimeError("V13 must apply the same B once for each Schur column")

    action = HybridActionModalSchurApply(
        coupling,
        bottom_action,
        top_action,
        modal_constraint=constraint,
    )
    if action.modal_constraint is not constraint:
        action.destroy()
        raise RuntimeError("V13 independent action did not borrow the validated C block")
    validation_errors: list[float] = []
    validation_records: list[dict[str, Any]] = []
    validation_started = time.perf_counter()
    indices = np.arange(1, internal_count + 1, dtype=np.float64)
    x = np.asarray(indices + 1j * (indices[::-1] + 0.5), dtype=np.complex128)
    y = np.asarray(0.3 * indices[::-1] - 0.2 + 1j * (0.17 * indices + 0.1), dtype=np.complex128)
    alpha = np.complex128(0.37 - 0.21j)
    probes = [
        ("x", x),
        ("y", y),
        ("complex_homogeneity", alpha * x),
        ("additivity", x + y),
        ("repeat_x", x.copy()),
        ("zero", np.zeros(internal_count, dtype=np.complex128)),
        ("near_zero", 1.0e-12 * x),
    ]
    input_hashes = [
        hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
        for _name, values in probes
    ]
    if any(row != input_hashes for row in comm.allgather(input_hashes)):
        raise ValueError("V13 full-vector validation inputs differ across ranks")
    x_observed = None
    y_observed = None
    algebra_errors: dict[str, float] = {}
    try:
        for probe_index, (name, probe) in enumerate(probes):
            input_hash_before = hashlib.sha256(
                np.ascontiguousarray(probe).tobytes()
            ).hexdigest()
            observed = np.asarray(action.apply(probe), dtype=np.complex128)
            unchanged = (
                hashlib.sha256(np.ascontiguousarray(probe).tobytes()).hexdigest()
                == input_hash_before
            )
            owner_result = schur @ probe if comm.rank == owner else None
            reference = np.asarray(comm.bcast(owner_result, root=owner), dtype=np.complex128)
            difference = observed - reference
            denominator = float(np.linalg.norm(reference))
            error = float(np.linalg.norm(difference))
            relative = (
                error / denominator
                if denominator > 0.0
                else (0.0 if error == 0.0 else float("inf"))
            )
            relation_error = None
            relation_relative = None
            if name == "complex_homogeneity" and x_observed is not None:
                expected_relation = alpha * x_observed
            elif name == "additivity" and x_observed is not None and y_observed is not None:
                expected_relation = x_observed + y_observed
            elif name == "repeat_x" and x_observed is not None:
                expected_relation = x_observed
            elif name == "near_zero" and x_observed is not None:
                expected_relation = 1.0e-12 * x_observed
            elif name in {"zero", "x", "y"}:
                expected_relation = None
            else:
                raise RuntimeError(f"V13 full-vector relation input is out of order: {name}")
            if expected_relation is not None:
                relation_denominator = float(np.linalg.norm(expected_relation))
                relation_error = float(
                    np.linalg.norm(observed - expected_relation)
                )
                relation_relative = (
                    relation_error / relation_denominator
                    if relation_denominator > 0.0
                    else (
                        0.0 if relation_error == 0.0 else float("inf")
                    )
                )
                algebra_errors[name] = relation_relative
            else:
                if name == "zero":
                    expected_relation = np.zeros_like(observed)
                    relation_denominator = 0.0
                    relation_error = float(np.linalg.norm(observed))
                    relation_relative = (
                        0.0 if relation_error == 0.0 else float("inf")
                    )
                    algebra_errors["zero"] = relation_relative
            local_pass = bool(
                np.all(np.isfinite(observed))
                and np.all(np.isfinite(reference))
                and unchanged
                and np.isfinite(relative)
                and relative <= 1.0e-10
                and (
                    relation_relative is None
                    or (
                        np.isfinite(relation_relative)
                        and relation_relative <= 1.0e-10
                    )
                )
                and (name != "zero" or np.count_nonzero(observed) == 0)
            )
            if not comm.allreduce(local_pass, op=MPI.LAND):
                raise ValueError(
                    f"V13 independent full-complex action validation rejected {name}"
                )
            validation_errors.append(relative)
            validation_records.append(
                {
                    "input": name,
                    "input_sha256": input_hashes[probe_index],
                    "relative_error_vs_owner_S_B": relative,
                    "algebra_identity_absolute_error": relation_error,
                    "algebra_identity_relative_error": relation_relative,
                    "algebra_identity_applicable": relation_error is not None,
                    "input_unchanged": unchanged,
                    "finite": bool(
                        np.all(np.isfinite(observed))
                        and np.all(np.isfinite(reference))
                    ),
                }
            )
            if name == "x":
                x_observed = observed.copy()
            elif name == "y":
                y_observed = observed.copy()
            del owner_result, reference, difference, expected_relation, observed
    finally:
        action.destroy()
    after_independent_validation_work_phase = collect_actual_work_phase(
        "after_independent_validation",
        local_elapsed_seconds=time.perf_counter() - validation_started,
        extra={
            "validated_full_complex_input_count": len(probes),
            "scope": "independent_full_complex_action_setup; not outer application",
        },
    )
    if marker_callback is not None:
        marker_callback(
            "v13_modal_independent_validation_complete",
            after_independent_validation_work_phase,
        )
    bottom_after_validation = int(
        _action_diagnostics(bottom_action).get("apply_count", 0)
    )
    top_after_validation = int(
        _action_diagnostics(top_action).get("apply_count", 0)
    )
    expected_validation = len(probes)
    if (
        bottom_after_validation - bottom_after_assembly != expected_validation
        or top_after_validation - top_after_assembly != expected_validation
    ):
        raise RuntimeError("V13 independent validation action count is inconsistent")
    side_operation_after_setup = {
        "bottom": _v13_side_operation_counts(bottom_action),
        "top": _v13_side_operation_counts(top_action),
    }
    side_operation_deltas = {}
    for side in ("bottom", "top"):
        before = side_operation_baseline[side]
        after = side_operation_after_setup[side]
        if before is None or after is None:
            side_operation_deltas[side] = None
        else:
            side_operation_deltas[side] = {
                key: int(after[key]) - int(before[key])
                for key in ("apply_count", "total_iterations")
            }
    local_side_zero = bool(
        all(
            isinstance(counts, Mapping)
            and all(value == 0 for value in counts.values())
            for counts in side_operation_deltas.values()
        )
    )
    if not comm.allreduce(local_side_zero, op=MPI.LAND):
        raise RuntimeError(
            "V13 Schur assembly/validation entered a borrowed SideBalancedInverse"
        )

    owner_lu = None
    owner_pivots = None
    owner_payload = None
    owner_lu_factorization_attempts = 0
    owner_lu_repeat_solve_attempts = 0
    owner_lu_original_residual_checks = 0
    repeat_error = None
    first_residual_relative = None
    second_residual_relative = None
    first_input_unchanged = None
    second_input_unchanged = None
    lu_residual_pass = False
    if comm.rank == owner:
        try:
            if schur is None or not np.all(np.isfinite(schur)):
                raise ValueError("V13 owner Schur matrix is unavailable or non-finite")
            owner_lu_factorization_attempts += 1
            with warnings.catch_warnings():
                warnings.simplefilter("error", LinAlgWarning)
                owner_lu, owner_pivots = lu_factor(schur, check_finite=True)
            owner_lu = np.asarray(owner_lu, dtype=np.complex128)
            owner_pivots = np.asarray(owner_pivots, dtype=np.int32)
            diagonal = np.abs(np.diag(owner_lu))
            if (
                not np.all(np.isfinite(owner_lu))
                or not np.all(np.isfinite(owner_pivots))
                or diagonal.size != internal_count
                or np.any(diagonal == 0.0)
            ):
                raise ValueError("V13 owner Schur LU is singular or non-finite")
            rhs = np.arange(1, internal_count + 1, dtype=np.complex128)
            rhs_before = rhs.copy()
            owner_lu_repeat_solve_attempts += 1
            first_rhs = rhs.copy()
            first = lu_solve((owner_lu, owner_pivots), first_rhs, check_finite=True)
            first_input_unchanged = bool(np.array_equal(first_rhs, rhs_before))
            owner_lu_repeat_solve_attempts += 1
            second_rhs = rhs.copy()
            second = lu_solve((owner_lu, owner_pivots), second_rhs, check_finite=True)
            second_input_unchanged = bool(np.array_equal(second_rhs, rhs_before))
            repeat_error = float(
                np.linalg.norm(first - second) / max(float(np.linalg.norm(first)), _TINY)
            )
            rhs_norm = float(np.linalg.norm(rhs_before))
            if not np.isfinite(rhs_norm) or rhs_norm <= 0.0:
                raise ValueError("V13 owner LU validation RHS is invalid")
            first_residual = np.asarray(schur @ first - rhs_before)
            second_residual = np.asarray(schur @ second - rhs_before)
            first_residual_relative = float(np.linalg.norm(first_residual) / rhs_norm)
            second_residual_relative = float(np.linalg.norm(second_residual) / rhs_norm)
            owner_lu_original_residual_checks = 2
            lu_residual_pass = bool(
                np.isfinite(first).all()
                and np.isfinite(second).all()
                and np.isfinite(first_residual).all()
                and np.isfinite(second_residual).all()
                and first_input_unchanged
                and second_input_unchanged
                and np.isfinite(first_residual_relative)
                and np.isfinite(second_residual_relative)
                and first_residual_relative <= 1.0e-10
                and second_residual_relative <= 1.0e-10
                and np.array_equal(rhs, rhs_before)
            )
            if not np.isfinite(repeat_error) or repeat_error > 1.0e-13:
                raise ValueError("V13 owner LU repeat-solve gate failed")
            if not lu_residual_pass:
                raise ValueError(
                    "V13 owner LU original S_B a-g residual gate failed: "
                    f"first={first_residual_relative!r}, "
                    f"second={second_residual_relative!r}, "
                    f"first_input_unchanged={first_input_unchanged}, "
                    f"second_input_unchanged={second_input_unchanged}"
                )
            owner_payload = {
                "status": "ready",
                "condition": None,
                "repeat_error": repeat_error,
                "original_schur_rhs_relative_residuals": [
                    first_residual_relative,
                    second_residual_relative,
                ],
                "original_schur_rhs_residual_tolerance": 1.0e-10,
                "original_schur_rhs_residual_pass": True,
                "original_schur_rhs_input_unchanged": [
                    first_input_unchanged,
                    second_input_unchanged,
                ],
                "owner_lu_factorization_attempts": owner_lu_factorization_attempts,
                "owner_lu_repeat_solve_attempts": owner_lu_repeat_solve_attempts,
                "owner_lu_original_residual_checks": owner_lu_original_residual_checks,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - owner LU rejection is broadcast below
            owner_lu = None
            owner_pivots = None
            owner_payload = {
                "status": "rejected",
                "condition": None,
                "repeat_error": repeat_error,
                "original_schur_rhs_residual_tolerance": 1.0e-10,
                "original_schur_rhs_residual_pass": lu_residual_pass,
                "original_schur_rhs_input_unchanged": [
                    first_input_unchanged,
                    second_input_unchanged,
                ],
                "owner_lu_factorization_attempts": owner_lu_factorization_attempts,
                "owner_lu_repeat_solve_attempts": owner_lu_repeat_solve_attempts,
                "owner_lu_original_residual_checks": owner_lu_original_residual_checks,
                "original_schur_rhs_relative_residuals": [
                    first_residual_relative,
                    second_residual_relative,
                ],
                "error": f"{type(exc).__name__}: {exc}",
            }
    owner_payload = comm.bcast(owner_payload, root=owner)
    if (
        not isinstance(owner_payload, Mapping)
        or owner_payload.get("status") != "ready"
        or owner_payload.get("error") is not None
    ):
        error = "owner factorization returned no record"
        if isinstance(owner_payload, Mapping):
            error = str(owner_payload.get("error"))
            if marker_callback is not None:
                marker_callback(
                    "v13_modal_schur_lu_refused",
                    {
                        "method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                        "owner": owner,
                        "status": "refused",
                        "error": error,
                        "setup_work_counts": {
                            "scope": "owner_setup_not_outer_iterations",
                            "owner_rank": owner,
                            "owner_LU_factorization_attempts": owner_payload.get(
                                "owner_lu_factorization_attempts"
                            ),
                            "owner_repeat_lu_solve_attempts": owner_payload.get(
                                "owner_lu_repeat_solve_attempts"
                            ),
                            "owner_original_schur_rhs_residual_checks": owner_payload.get(
                                "owner_lu_original_residual_checks"
                            ),
                            "outer_PC_and_LDU_work": "not_run_during_builder_setup",
                        },
                        "lu_repeat_error": owner_payload.get("repeat_error"),
                        "original_schur_rhs_relative_residuals": owner_payload.get(
                            "original_schur_rhs_relative_residuals"
                        ),
                        "original_schur_rhs_residual_tolerance": 1.0e-10,
                        "original_schur_rhs_residual_pass": owner_payload.get(
                            "original_schur_rhs_residual_pass"
                        ),
                        "original_schur_rhs_input_unchanged": owner_payload.get(
                            "original_schur_rhs_input_unchanged"
                        ),
                    },
                )
        raise ValueError(f"V13 owner Schur factorization rejected: {error}")
    lu = owner_lu if comm.rank == owner else None
    pivots = owner_pivots if comm.rank == owner else None
    if marker_callback is not None:
        marker_callback(
            "v13_modal_schur_ready",
            {
                "method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                "owner": owner,
                "sample_columns_retained_in_final_matrix": list(columns),
                "remaining_columns_built_once": len(remaining),
                "assembly_B_apply_count_by_side": {
                    "bottom": bottom_after_assembly - bottom_before,
                    "top": top_after_assembly - top_before,
                },
                "independent_validation_B_apply_count_by_side": {
                    "bottom": bottom_after_validation - bottom_after_assembly,
                    "top": top_after_validation - top_after_assembly,
                },
                "actual_work_phase_snapshots": actual_work_phase_snapshots,
                "independent_validation_max_relative_error": max(
                    validation_errors, default=0.0
                ),
                "condition": owner_payload["condition"],
                "lu_repeat_error": float(owner_payload["repeat_error"]),
                "owner_original_schur_rhs_residuals": list(
                    owner_payload["original_schur_rhs_relative_residuals"]
                ),
                "owner_original_schur_rhs_residual_tolerance": 1.0e-10,
                "owner_original_schur_rhs_residual_pass": True,
                "owner_original_schur_rhs_input_unchanged": list(
                    owner_payload["original_schur_rhs_input_unchanged"]
                ),
                "setup_work_counts": {
                    "scope": "owner_setup_not_outer_iterations",
                    "owner_rank": owner,
                    "owner_LU_factorization_attempts": owner_payload[
                        "owner_lu_factorization_attempts"
                    ],
                    "owner_repeat_lu_solve_attempts": owner_payload[
                        "owner_lu_repeat_solve_attempts"
                    ],
                    "owner_original_schur_rhs_residual_checks": owner_payload[
                        "owner_lu_original_residual_checks"
                    ],
                    "independent_full_action_B_apply_count_by_side": {
                        "bottom": bottom_after_validation - bottom_after_assembly,
                        "top": top_after_validation - top_after_assembly,
                    },
                    "outer_PC_and_LDU_work": "not_run_during_builder_setup",
                },
                "owner_storage_plan": dict(storage_phases),
                "build_seconds": float(time.perf_counter() - build_started),
                "validation_seconds": float(
                    time.perf_counter() - validation_started
                ),
            },
        )
    build_audit = {
        "formula": "S_B=C-LBG",
        "B_definition": "fixed approximate physical BAL_H action; not D inverse",
        "sample_contract": dict(contract),
        "sample_columns_written_directly_to_final_matrix": list(columns),
        "full_owner_matrix_pages_materialized_before_sample_gate": True,
        "remaining_columns_applied_once": list(remaining),
        "assembly_B_apply_count_by_side": {
            "bottom": bottom_after_assembly - bottom_before,
            "top": top_after_assembly - top_before,
        },
        "independent_action_validation": {
            "scope": "separate_setup_scope",
            "uses_validated_constraint_storage": True,
            "inputs": [name for name, _values in probes],
            "covers_all_modal_components": True,
            "B_apply_count_by_side": {
                "bottom": bottom_after_validation - bottom_after_assembly,
                "top": top_after_validation - top_after_assembly,
            },
            "relative_errors": validation_errors,
            "input_records": validation_records,
            "complex_linearity_errors": algebra_errors,
            "tolerance": 1.0e-10,
            "pass": True,
        },
        "owner_storage_plan": dict(storage_phases),
        "workspace_inventory": workspace_inventory,
        "initial_phase_memory_projection": before_memory_projection,
        "side_operation_baseline": side_operation_baseline,
        "side_operation_after_setup": side_operation_after_setup,
        "side_operation_deltas": side_operation_deltas,
        "side_solver_entry_zero_supported": local_side_zero,
        "fresh_authority_gate": authority_record,
        "sample8_cost_report": sample_cost_report,
        "sample8_admission": sample_admission,
        "condition": (
            None
            if owner_payload["condition"] is None
            else float(owner_payload["condition"])
        ),
        "lu_repeat_error": float(owner_payload["repeat_error"]),
        "owner_original_schur_rhs_residuals": list(
            owner_payload["original_schur_rhs_relative_residuals"]
        ),
        "owner_original_schur_rhs_residual_tolerance": 1.0e-10,
        "owner_original_schur_rhs_residual_pass": True,
        "owner_original_schur_rhs_input_unchanged": list(
            owner_payload["original_schur_rhs_input_unchanged"]
        ),
        "setup_work_counts": {
            "scope": "builder_setup_only_not_outer_solve",
            "owner_rank": owner,
            "owner_lu_factorization_attempts": owner_payload[
                "owner_lu_factorization_attempts"
            ],
            "owner_lu_repeat_solve_attempts": owner_payload[
                "owner_lu_repeat_solve_attempts"
            ],
            "owner_original_schur_rhs_residual_checks": owner_payload[
                "owner_lu_original_residual_checks"
            ],
            "independent_full_action_validation_B_apply_count_by_side": {
                "bottom": bottom_after_validation - bottom_after_assembly,
                "top": top_after_validation - top_after_assembly,
            },
            "Schur_column_assembly_B_apply_count_by_side": {
                "bottom": bottom_after_assembly - bottom_before,
                "top": top_after_assembly - top_before,
            },
            "outer_PC_calls": 0,
            "modal_KSP_solves": 0,
        },
        "actual_work_phase_snapshots": actual_work_phase_snapshots,
        "actual_work_counter_semantics": {
            "side_callback_counts": (
                "rank-local SideBalancedInverse._count_snapshot deltas; "
                "p4_refinement retains sum(max(actual_backsolves-1,0)) per Q callback"
            ),
            "fixed_q_math_and_factor_counts": (
                "separate per-Q mathematical request/completion, initial/correction "
                "factor deltas, and exact-zero statuses from FixedPhysical action audits"
            ),
            "aggregation": (
                "phase rows preserve each rank; no rank multiplication or summing "
                "replicated counts"
            ),
            "cross_counter_rule": (
                "fixed-Q factor deltas are detail for shared p4_backsolve and must "
                "not be added to that callback counter"
            ),
        },
    }
    system = Task041V13ConsistentModalSurrogateSystem(
        modal_schur=schur,
        modal_constraint=constraint,
        lu=lu,
        pivots=pivots,
        modal_owner=owner,
        comm=comm,
        condition=(
            None
            if owner_payload["condition"] is None
            else float(owner_payload["condition"])
        ),
        storage_plan=storage_phases,
        build_audit=build_audit,
        bottom_action=bottom_action,
        top_action=top_action,
        side_operation_baseline=side_operation_baseline,
        fresh_authority_callback=fresh_authority_callback,
        marker_callback=marker_callback,
        snapshot_callback=snapshot_callback,
    )
    system.record_side_operation_counts(side_operation_after_setup)
    system_side_deltas = system._side_operation_deltas(
        system.side_operation_baseline, system._side_operation_after
    )
    if system_side_deltas != side_operation_deltas or not local_side_zero:
        system.destroy()
        raise RuntimeError(
            "V13 recorded side counters differ from the measured setup counters"
        )
    return system


@dataclass
class HybridActionModalSchurApply:
    """Apply one modal Schur action without assembling its columns.

    The side actions and coupling are borrowed.  A supplied modal constraint is
    borrowed as well; otherwise the historical path builds its own copy.  This
    object does not assert that the side actions define a fixed linear map:
    adaptive actions may make each call nonlinear or call-dependent, so this
    is not itself a PETSc Mat/KSP.
    """

    coupling: HybridInternalModeCoupling
    bottom_action: Any
    top_action: Any
    modal_constraint: np.ndarray | None = field(default=None, repr=False)
    _destroyed: bool = field(default=False, init=False, repr=False)
    _modal_constraint_matvec_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.mode_count = int(self.coupling.mode_count_per_direction)
        self.modal_count = 2 * self.mode_count
        if self.modal_constraint is None:
            self.modal_constraint = np.asarray(
                internal_modal_constraint_matrix(self.coupling), dtype=np.complex128
            )
        else:
            self.modal_constraint = np.asarray(
                self.modal_constraint, dtype=np.complex128
            )
        if self.modal_constraint.shape != (self.modal_count, self.modal_count):
            raise ValueError("Modal constraint has the wrong shape.")

    def _subtract_side_response(self, side: str, modal: np.ndarray, result: np.ndarray) -> None:
        action = self.bottom_action if side == "bottom" else self.top_action
        projection = (
            self.coupling.bottom.projection
            if side == "bottom"
            else self.coupling.top.projection
        )
        traction = modal_coupling_action(side, self.coupling, modal)
        response = projected = None
        try:
            response = _action_operator(action).createVecLeft()
            projected = projection.createVecLeft()
            action.apply(traction, response)
            projection.mult(response, projected)
            start = 0 if side == "bottom" else self.mode_count
            result[start : start + self.mode_count] -= _replicated_modal_values(
                projected
            )
        finally:
            if projected is not None:
                projected.destroy()
            if response is not None:
                response.destroy()
            traction.destroy()

    def apply(self, modal: np.ndarray) -> np.ndarray:
        """Return ``C modal - projected(bottom) - projected(top)``."""

        if self._destroyed:
            raise RuntimeError("On-demand modal Schur action has been destroyed.")
        values = np.asarray(modal, dtype=np.complex128)
        if values.shape != (self.modal_count,):
            raise ValueError("Modal Schur input has the wrong shape.")
        result = np.asarray(self.modal_constraint @ values, dtype=np.complex128)
        self._modal_constraint_matvec_count += 1
        self._subtract_side_response("bottom", values, result)
        self._subtract_side_response("top", values, result)
        return result

    def destroy(self) -> None:
        """Release owned modal data without destroying borrowed actions."""

        if self._destroyed:
            return
        self.modal_constraint = None
        self._destroyed = True


class _FixedH6ModalMatContext:
    def __init__(self, owner: _FixedH6ModalKrylovSystem) -> None:
        self.owner: _FixedH6ModalKrylovSystem | None = owner

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.owner is None:
            raise RuntimeError("Fixed-H6 modal Mat context was destroyed")
        self.owner._mat_mult(source, target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.owner = None


class _FixedH6ModalConstraintPcContext:
    def __init__(self, owner: _FixedH6ModalKrylovSystem) -> None:
        self.owner: _FixedH6ModalKrylovSystem | None = owner

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.owner is None:
            raise RuntimeError("Fixed-H6 modal C-PC context was destroyed")
        self.owner._apply_constraint_pc(_pc, source, target)

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.owner = None


class _FixedH6ModalKrylovSystem:
    """Bounded fixed-H6 modal solve used only by its explicit research branch."""

    rtol = 1.0e-3
    max_it = 8
    solver_matmult_limit = 9
    total_matmult_limit = 10
    modal_schur = None
    requires_right_fgmres = True

    def __init__(
        self,
        coupling: HybridInternalModeCoupling,
        bottom_action: Any,
        top_action: Any,
        *,
        modal_owner: int,
        feedback_method: str | None = None,
        modal_solver_policy: Mapping[str, Any] | None = None,
        snapshot_callback: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
        | None = None,
    ) -> None:
        from .physical_balanced_side_inverse import (
            FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
            FixedH6ActiveTraceAction,
            FixedPhysicalBalancedActiveTraceAction,
        )

        self._bottom_action = bottom_action
        self._top_action = top_action
        self._coupling = coupling
        self.feedback_method = feedback_method
        self.actual_feedback_method = feedback_method
        # Keep the historical instance contract until policy parsing has
        # participated in the existing all-rank setup validation below.
        self.modal_solver_policy = None
        self.rtol = float(type(self).rtol)
        self.max_it = int(type(self).max_it)
        self.solver_matmult_limit = int(type(self).solver_matmult_limit)
        self.total_matmult_limit = int(type(self).total_matmult_limit)
        self._snapshot_callback = snapshot_callback
        self._first_unmet_snapshot_saved = False
        self._success_control_snapshot_saved = False
        self._terminal_normal_reject_snapshot_saved = False
        self._outer_pc_apply_index: int | None = None
        self._iteration_scalar_history: list[dict[str, float | int]] = []
        self._rhs_input_sha256: str | None = None
        self._rhs_input_bytes: bytes | None = None
        self.method = (
            "fixed_h6_modal_gmres_research"
            if feedback_method is None
            else "fixed_physical_balh_once_modal_gmres_research"
        )
        self._method_history = [self.method]
        self._solve_in_progress = False
        self._action_operator = (
            "C-PbJbH6bJb^H Tb-PtJtH6tJt^H Tt"
            if feedback_method is None
            else (
                "C-PbJb[Qb+(I-QbA6b)H6b(I-A6bQb)]Jb^H Tb"
                "-PtJt[Qt+(I-QtA6t)H6t(I-A6tQt)]Jt^H Tt"
            )
        )
        self._modal_action: HybridActionModalSchurApply | None = None
        # The coupling projection is the shared communicator anchor.  No PETSc
        # solver object or modal action is allocated before the first collective
        # validation has rejected rank-local metadata errors.
        petsc_comm = coupling.bottom.projection.getComm()
        self._comm = petsc_comm.tompi4py()
        self._modal_owner = -1
        self.modal_count = 0
        self.mode_count = 0
        self._constraint_lu = self._constraint_pivots = None
        self._constraint_lu_solve_attempts = 0
        self._constraint_lu_solve_successes = 0
        self._constraint_lu_factorizations_local = 0
        self._constraint_lu_factorizations_owner = 0
        self._solver_matmult_calls = self._total_matmult_calls = 0
        self._modal_constraint_matvec_calls_at_destroy = 0
        self._blocked_matmult_attempts = 0
        self._budget_exhausted = False
        self._in_final_check = False
        self._pc_failure_error: str | None = None
        self._mat_preflight_failure: str | None = None
        self._modal_action_failure: str | None = None
        self._destroyed = False
        self._last_solve: dict[str, Any] | None = None
        self._backup_switches = 0
        self._backup_switch_audit: dict[str, Any] = {
            "requested": False,
            "allowed": False,
            "actual": False,
            "switch_count": 0,
            "trigger": None,
            "status": "not_requested",
        }
        self._backup_pending = False
        self._outer_window_points: list[dict[str, Any]] = []
        self._outer_completed_windows: list[dict[str, Any]] = []
        self._outer_metrics_passed_in_segment: set[str] = set()
        self._outer_observation_segment = "primary"
        self._outer_segment_history: list[dict[str, Any]] = []
        self._outer_last_observed_iteration: int | None = None
        self._post_backup_stop_pending: dict[str, Any] | None = None
        self._post_backup_capacity_stop_pending: dict[str, Any] | None = None
        self._post_backup_stop_record: dict[str, Any] | None = None
        self._side_restart64_trial_state: dict[str, Any] | None = None
        self._solve_count = 0
        self._not_converged_count = 0
        self._cumulative_solver_matmult_calls = 0
        self._cumulative_total_matmult_calls = 0
        self._cumulative_constraint_lu_solve_attempts = 0
        self._cumulative_constraint_lu_solve_successes = 0
        self._cumulative_owner_constraint_lu_solve_attempts = 0
        self._cumulative_owner_constraint_lu_solve_successes = 0
        self._cumulative_owner_constraint_lu_solve_counts_complete = True
        self._owner_constraint_lu_solve_counts_authoritative = False
        self._owner_constraint_lu_solve_attempts_this_solve: int | None = None
        self._owner_constraint_lu_solve_successes_this_solve: int | None = None
        self.modal_constraint_local_bytes = 0
        self._matrix = self._ksp = None
        self._rhs = self._solution = self._image = self._residual = None

        local_error = None
        local_signature = None
        requested_owner = -1
        mode_count = 0
        constraint = None
        resolved_modal_policy = None
        try:
            resolved_modal_policy = resolve_task041_modal_solver_policy(
                modal_solver_policy
            )
            if (resolved_modal_policy is None) != (snapshot_callback is None):
                raise ValueError(
                    "V12 modal policy and owner snapshot callback must be selected together"
                )
            if snapshot_callback is not None and not callable(snapshot_callback):
                raise TypeError("modal snapshot callback must be callable")
            if resolved_modal_policy is not None and feedback_method is not None:
                raise ValueError(
                    "V12 modal policy is restricted to the pure fixed-H6 route"
                )
            if feedback_method not in (
                None,
                FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
            ):
                raise ValueError("unsupported fixed modal feedback method")
            requested_owner = int(modal_owner)
            mode_count = int(coupling.mode_count_per_direction)
            modal_count = 2 * mode_count
            if requested_owner != self._comm.size - 1:
                raise ValueError("Modal ownership must be on the final MPI rank")
            if mode_count <= 0:
                raise ValueError("Fixed-H6 modal system requires nonempty modes")
            if feedback_method is None:
                actions_match_method = all(
                    isinstance(action, FixedH6ActiveTraceAction)
                    and not isinstance(
                        action, FixedPhysicalBalancedActiveTraceAction
                    )
                    and action.method == "fixed_h6_active_trace"
                    and action.operator_identity
                    == "borrowed_fixed_h6_active_trace_J_H6_JH"
                    for action in (bottom_action, top_action)
                )
            else:
                actions_match_method = all(
                    type(action) is FixedPhysicalBalancedActiveTraceAction
                    and action.method
                    == FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
                    and action.operator_identity
                    == "borrowed_fixed_physical_balh_active_trace"
                    for action in (bottom_action, top_action)
                )
            if not actions_match_method:
                raise TypeError(
                    "modal feedback actions do not match the explicitly selected method"
                )
            constraint = np.asarray(
                internal_modal_constraint_matrix(coupling), dtype=np.complex128
            )
            if constraint.shape != (modal_count, modal_count) or not np.all(
                np.isfinite(constraint)
            ):
                raise ValueError("S_H modal constraint is malformed or non-finite")
            side_shapes = []
            for side, action, interface in (
                ("bottom", bottom_action, coupling.bottom),
                ("top", top_action, coupling.top),
            ):
                if action._destroyed or action._condensed is None or action._h6 is None:
                    raise ValueError(f"{side} Fixed-H6 action is not live")
                operator = action.operator
                condensed = action._condensed
                h6_matrix = action._h6.matrix
                active_rows = int(condensed.active_rows)
                full_rows = int(condensed.full_rows)
                if operator.getSize() != (active_rows, active_rows):
                    raise ValueError(f"{side} active operator shape is inconsistent")
                if h6_matrix.getSize() != (full_rows, full_rows):
                    raise ValueError(f"{side} Fixed-H6 shape is inconsistent")
                if interface.projection.getSize() != (mode_count, active_rows):
                    raise ValueError(f"{side} modal projection shape is inconsistent")
                for matrix in (operator, h6_matrix, interface.projection):
                    relation = MPI.Comm.Compare(
                        self._comm, matrix.getComm().tompi4py()
                    )
                    if relation not in (MPI.IDENT, MPI.CONGRUENT):
                        raise ValueError(f"{side} action communicator differs")
                side_shapes.append((active_rows, full_rows))
            local_signature = (
                mode_count,
                modal_count,
                hashlib.sha256(np.ascontiguousarray(constraint).tobytes()).hexdigest(),
                tuple(side_shapes),
                feedback_method,
                (
                    None
                    if resolved_modal_policy is None
                    else json.dumps(
                        resolved_modal_policy,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                ),
                callable(self._snapshot_callback),
            )
        except Exception as exc:  # noqa: BLE001 - synchronize rank-local setup errors
            local_error = f"{type(exc).__name__}: {exc}"
        preflight = self._comm.allgather((local_error, local_signature))
        failures = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(preflight)
            if error is not None
        ]
        signatures = [signature for error, signature in preflight if error is None]
        if signatures and any(signature != signatures[0] for signature in signatures[1:]):
            failures.extend(
                f"rank {rank}: modal/action layout metadata differs"
                for rank, (error, signature) in enumerate(preflight)
                if error is None and signature != signatures[0]
            )
        if failures:
            raise RuntimeError("Fixed-H6 modal input preflight failed; " + "; ".join(failures))

        self._modal_owner = requested_owner
        self.mode_count = mode_count
        self.modal_count = 2 * mode_count
        self.modal_solver_policy = resolved_modal_policy
        if self.modal_solver_policy is not None:
            self.rtol = float(self.modal_solver_policy["target_rtol"])
            self.max_it = int(self.modal_solver_policy["max_it"])
            self.solver_matmult_limit = int(
                self.modal_solver_policy["solver_matmult_limit"]
            )
            self.total_matmult_limit = int(
                self.modal_solver_policy["total_matmult_limit_including_final"]
            )
        expected_constraint_sha = local_signature[2]

        construction_error = None
        try:
            self._modal_action = HybridActionModalSchurApply(
                coupling, bottom_action, top_action
            )
            constraint_sha = hashlib.sha256(
                np.ascontiguousarray(self._modal_action.modal_constraint).tobytes()
            ).hexdigest()
            if constraint_sha != expected_constraint_sha:
                raise ValueError("modal action constraint differs from validated input")
        except Exception as exc:  # noqa: BLE001 - synchronize local construction errors
            construction_error = f"{type(exc).__name__}: {exc}"
        constructions = self._comm.allgather(construction_error)
        construction_failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(constructions)
            if error is not None
        ]
        if construction_failures:
            if self._modal_action is not None:
                self._modal_action.destroy()
                self._modal_action = None
            raise RuntimeError(
                "Fixed-H6 modal action construction failed; "
                + "; ".join(construction_failures)
            )
        self.modal_constraint_local_bytes = int(
            self._modal_action.modal_constraint.nbytes
        )
        self._initial_modal_constraint_sha256 = hashlib.sha256(
            np.ascontiguousarray(
                self._modal_action.modal_constraint, dtype=np.complex128
            ).tobytes()
        ).hexdigest()

        factor_result = None
        if self._comm.rank == self._modal_owner:
            try:
                lu, pivots, condition = _factor_modal_constraint(constraint, self.modal_count)
                self._constraint_lu = lu
                self._constraint_pivots = pivots
                self._constraint_lu_factorizations_local += 1
                factor_result = (True, condition, None, 1)
            except Exception as exc:  # noqa: BLE001 - owner result is broadcast below
                factor_result = (False, None, f"{type(exc).__name__}: {exc}", 0)
        factor_ok, condition, factor_error, owner_factorizations = self._comm.bcast(
            factor_result, root=self._modal_owner
        )
        self._constraint_lu_factorizations_owner = int(owner_factorizations)
        if not factor_ok:
            self.destroy()
            raise RuntimeError(f"Fixed-H6 modal C factorization failed: {factor_error}")
        self.constraint_condition = float(condition)

        local_size = self.modal_count if self._comm.rank == self._modal_owner else 0
        try:
            self._matrix = PETSc.Mat().createPython(
                ((local_size, self.modal_count), (local_size, self.modal_count)),
                comm=petsc_comm,
            )
            self._matrix.setPythonContext(_FixedH6ModalMatContext(self))
            self._matrix.setUp()
            self._rhs = self._matrix.createVecRight()
            self._solution = self._matrix.createVecRight()
            self._image = self._matrix.createVecLeft()
            self._residual = self._matrix.createVecLeft()
            self._ksp = PETSc.KSP().create(petsc_comm)
            self._ksp.setOperators(self._matrix)
            self._ksp.setType(PETSc.KSP.Type.GMRES)
            self._ksp.setGMRESRestart(self.max_it)
            self._ksp.setPCSide(PETSc.PC.Side.RIGHT)
            self._ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            self._ksp.setInitialGuessNonzero(False)
            self._ksp.setTolerances(rtol=self.rtol, atol=0.0, max_it=self.max_it)
            pc = self._ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(_FixedH6ModalConstraintPcContext(self))
            self._ksp.setUp()
            if self.modal_solver_policy is not None:
                self._ksp.setMonitor(self._capture_policy_iteration_scalar)
            pc.setFailedReason(PETSc.PC.FailedReason.NOERROR)
        except BaseException:
            self.destroy()
            raise

    def set_outer_pc_apply_index(self, index: int) -> None:
        if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
            raise ValueError("outer PC apply index must be a positive integer")
        self._outer_pc_apply_index = int(index)

    def _capture_policy_iteration_scalar(
        self, _ksp: PETSc.KSP, iteration: int, residual_norm: float
    ) -> None:
        if int(iteration) not in (8, 16, 32):
            return
        value = float(residual_norm)
        if not np.isfinite(value):
            raise FloatingPointError(
                f"modal GMRES reported a non-finite scalar at iteration {iteration}"
            )
        self._iteration_scalar_history.append(
            {"iteration": int(iteration), "reported_residual_norm": value}
        )

    @property
    def modal_constraint(self) -> np.ndarray | None:
        if self._destroyed or self._modal_action is None:
            return None
        return self._modal_action.modal_constraint

    @property
    def constraint_lu_factorizations(self) -> int:
        return int(self._constraint_lu_factorizations_owner)

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("Fixed-H6 modal system has been destroyed")
        if self._solve_in_progress:
            raise RuntimeError("Fixed-H6 modal solve is not reentrant")
        actions = (("bottom", self._bottom_action), ("top", self._top_action))
        before = {
            side: int(action.audit["apply_count"])
            for side, action in actions
        }
        self._solve_in_progress = True
        try:
            return self._solve_once(rhs)
        except BaseException as exc:
            if (
                self.modal_solver_policy is not None
                and isinstance(self._last_solve, dict)
            ):
                self._last_solve["pc_usable"] = False
                if isinstance(exc, _ModalNormalReturnBackupEligible):
                    self._last_solve["backup_switch_requested"] = True
                    self._last_solve["backup_switch_actual"] = False
                else:
                    self._last_solve.setdefault(
                        "policy_exception_rejection_reason",
                        "exception_prevented_a_usable_V12_modal_return",
                    )
                    self._last_solve.setdefault(
                        "snapshot_record",
                        {
                            "status": "not_saved_exception_no_trusted_snapshot",
                            "reason": (
                                "exception_prevented_a_trusted_normal_return_snapshot"
                            ),
                            "exception_type": type(exc).__name__,
                            "exception_message": str(exc),
                        },
                    )
            raise
        finally:
            self._solve_count += 1
            self._cumulative_solver_matmult_calls += int(
                self._solver_matmult_calls
            )
            self._cumulative_total_matmult_calls += int(self._total_matmult_calls)
            self._cumulative_constraint_lu_solve_attempts += int(
                self._constraint_lu_solve_attempts
            )
            self._cumulative_constraint_lu_solve_successes += int(
                self._constraint_lu_solve_successes
            )
            owner_counts_authoritative = bool(
                self._owner_constraint_lu_solve_counts_authoritative
                and type(self._owner_constraint_lu_solve_attempts_this_solve) is int
                and self._owner_constraint_lu_solve_attempts_this_solve >= 0
                and type(self._owner_constraint_lu_solve_successes_this_solve) is int
                and self._owner_constraint_lu_solve_successes_this_solve >= 0
            )
            if owner_counts_authoritative:
                self._cumulative_owner_constraint_lu_solve_attempts += (
                    self._owner_constraint_lu_solve_attempts_this_solve
                )
                self._cumulative_owner_constraint_lu_solve_successes += (
                    self._owner_constraint_lu_solve_successes_this_solve
                )
            else:
                self._cumulative_owner_constraint_lu_solve_counts_complete = False
            zero_rhs_without_ksp = (
                self._last_solve is not None
                and self._last_solve.get("ksp_status") == "not_run_zero_rhs"
            )
            owner_solve_count_scope = (
                "owner_counts_unknown_without_post_KSP_broadcast"
            )
            if owner_counts_authoritative:
                owner_solve_count_scope = (
                    "zero_rhs_no_ksp_no_owner_lu_calls"
                    if zero_rhs_without_ksp
                    else "owner_authoritative_per_solve_broadcasts"
                )
            if self._last_solve is not None:
                side_action_count_key = (
                    "fixed_h6_side_action_apply_calls"
                    if self.method == "fixed_h6_modal_gmres_research"
                    else "modal_feedback_side_action_apply_calls"
                )
                self._last_solve[side_action_count_key] = {
                    side: int(action.audit["apply_count"]) - before[side]
                    for side, action in actions
                }
                side_action_scope_key = (
                    "fixed_h6_side_action_count_scope"
                    if self.method == "fixed_h6_modal_gmres_research"
                    else "modal_feedback_side_action_count_scope"
                )
                self._last_solve[side_action_scope_key] = (
                    "per_rank_replicated; do_not_sum_across_ranks"
                )
                self._last_solve["cumulative_solve_count"] = self._solve_count
                self._last_solve["cumulative_solver_matmult_calls"] = (
                    self._cumulative_solver_matmult_calls
                )
                self._last_solve["cumulative_total_matmult_calls"] = (
                    self._cumulative_total_matmult_calls
                )
                self._last_solve[
                    "owner_constraint_lu_solve_counts_authoritative"
                ] = owner_counts_authoritative
                self._last_solve[
                    "owner_constraint_lu_solve_counts_scope"
                ] = owner_solve_count_scope
                self._last_solve[
                    "cumulative_constraint_lu_solve_count_scope"
                ] = "rank_local_cumulative; do_not_sum_across_ranks"
                self._last_solve[
                    "cumulative_owner_constraint_lu_solve_attempts"
                ] = (
                    self._cumulative_owner_constraint_lu_solve_attempts
                    if self._cumulative_owner_constraint_lu_solve_counts_complete
                    else None
                )
                self._last_solve[
                    "cumulative_owner_constraint_lu_solve_successes"
                ] = (
                    self._cumulative_owner_constraint_lu_solve_successes
                    if self._cumulative_owner_constraint_lu_solve_counts_complete
                    else None
                )
                self._last_solve[
                    "cumulative_owner_constraint_lu_solve_status"
                ] = (
                    "complete"
                    if self._cumulative_owner_constraint_lu_solve_counts_complete
                    else "unknown_missing_per_solve_owner_broadcast"
                )
                if self._last_solve.get("status") not in {
                    "converged",
                    "zero_rhs_exact",
                }:
                    self._not_converged_count += 1
            self._solve_in_progress = False

    def install_feedback_candidate(
        self,
        candidate_action: HybridActionModalSchurApply,
        bottom_action: Any,
        top_action: Any,
    ) -> tuple[Any, Any, Any, str, str | None, str]:
        """Temporarily install a same-factor feedback candidate at a safe point."""

        from .physical_balanced_side_inverse import (
            FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
            FixedPhysicalBalancedActiveTraceAction,
        )

        local_error = None
        candidate_sha = None
        try:
            if self._destroyed or self._solve_in_progress:
                raise RuntimeError("modal feedback cannot change during an active solve")
            if not _task041_modal_policy_allows_backup(self.modal_solver_policy):
                raise ValueError("sealed modal policy does not authorize one backup")
            if self.method != "fixed_h6_modal_gmres_research":
                raise ValueError("the primary modal method is no longer fixed-H6")
            if not all(
                type(action) is FixedPhysicalBalancedActiveTraceAction
                and action.method == FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
                and action.operator_identity == "borrowed_fixed_physical_balh_active_trace"
                and not action.audit.get("destroyed")
                for action in (bottom_action, top_action)
            ):
                raise TypeError("backup actions do not match fixed physical BAL_H")
            if candidate_action.modal_constraint.shape != (
                self.modal_count,
                self.modal_count,
            ):
                raise ValueError("backup action changes the modal constraint shape")
            candidate_sha = hashlib.sha256(
                np.ascontiguousarray(
                    candidate_action.modal_constraint, dtype=np.complex128
                ).tobytes()
            ).hexdigest()
            if candidate_sha != self._initial_modal_constraint_sha256:
                raise ValueError("backup action changes the original modal operator C")
        except Exception as exc:  # noqa: BLE001 - collect before swapping on any rank
            local_error = f"{type(exc).__name__}: {exc}"
        records = self._comm.allgather((local_error, candidate_sha))
        errors = [
            f"rank {rank}: {error}"
            for rank, (error, _sha) in enumerate(records)
            if error is not None
        ]
        hashes = [sha for error, sha in records if error is None]
        if hashes and any(value != hashes[0] for value in hashes[1:]):
            errors.append("candidate modal constraint SHA differs across ranks")
        if errors:
            raise RuntimeError(
                "modal backup candidate rejected before switch; " + "; ".join(errors)
            )
        previous = (
            self._modal_action,
            self._bottom_action,
            self._top_action,
            self.method,
            self.actual_feedback_method,
            self._action_operator,
        )
        self._modal_action = candidate_action
        self._bottom_action = bottom_action
        self._top_action = top_action
        self.method = "fixed_physical_balh_once_modal_gmres_research"
        self.actual_feedback_method = FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
        self._action_operator = (
            "C-PbJb[Qb+(I-QbA6b)H6b(I-A6bQb)]Jb^H Tb-"
            "PtJt[Qt+(I-QtA6t)H6t(I-A6tQt)]Jt^H Tt"
        )
        return previous

    def commit_feedback_candidate(
        self,
        *,
        trigger: Mapping[str, Any],
        gate: Mapping[str, Any],
        primary_diagnostics: Mapping[str, Any],
        same_live_side_factor_handles_verified: bool,
    ) -> None:
        """Record the one all-rank-approved same-factor feedback switch."""

        local_error = None
        signature = None
        try:
            if self._solve_in_progress or self._destroyed:
                raise RuntimeError("feedback switch commit is not at a safe boundary")
            if not _task041_modal_policy_allows_backup(self.modal_solver_policy):
                raise ValueError("the sealed policy does not authorize a backup")
            if self._backup_switches != 0:
                raise RuntimeError("the one-time modal backup was already consumed")
            if self.method != "fixed_physical_balh_once_modal_gmres_research":
                raise RuntimeError("the candidate method was not installed")
            if same_live_side_factor_handles_verified is not True:
                raise ValueError(
                    "the backup did not verify reuse of both live side factor handles"
                )
            signature = json.dumps(
                {
                    "trigger": dict(trigger),
                    "gate_pass": gate.get("pass"),
                    "same_live_side_factor_handles_verified": True,
                    "primary_method": primary_diagnostics.get("method"),
                    "primary_diagnostics": dict(primary_diagnostics),
                    "candidate_method": self.method,
                    "backup_linearity_gate": dict(gate),
                    "candidate_constraint_sha256": hashlib.sha256(
                        np.ascontiguousarray(
                            self.modal_constraint, dtype=np.complex128
                        ).tobytes()
                    ).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            if gate.get("pass") is not True:
                raise ValueError("the physical feedback repeat gate did not pass")
        except Exception as exc:  # noqa: BLE001 - synchronize safe-point rejection
            local_error = f"{type(exc).__name__}: {exc}"
        records = self._comm.allgather((local_error, signature))
        errors = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(records)
            if error is not None
        ]
        signatures = [value for error, value in records if error is None]
        if signatures and any(value != signatures[0] for value in signatures[1:]):
            errors.append("backup switch audit differs across ranks")
        if errors:
            raise RuntimeError(
                "modal backup switch was rejected before commit; " + "; ".join(errors)
            )
        self._backup_switches = 1
        self._backup_pending = False
        self._method_history.append(self.method)
        self._start_outer_observation_segment(
            "post_backup",
            boundary_reason="backup_committed_after_completed_primary_modal_solve",
        )
        if self._side_restart64_trial_state is not None:
            self._side_restart64_trial_state["backup_method_active"] = True
            self._side_restart64_trial_state["backup_commit_count"] = 1
            self._side_restart64_trial_state["post_backup_side_solve_seen"] = {
                "bottom": False,
                "top": False,
            }
            self._side_restart64_trial_state["outer_stagnation_confirmed"] = False
            self._side_restart64_trial_state["capture_armed"] = False
            self._side_restart64_trial_state["resolved"] = False
            self._side_restart64_trial_state["pending"] = False
            self._side_restart64_trial_state.pop("candidate", None)
            self._side_restart64_trial_state.pop("result", None)
        self._backup_switch_audit = {
            "requested": True,
            "allowed": True,
            "actual": True,
            "switch_count": 1,
            "trigger": dict(trigger),
            "status": "switched_after_backup_linearity_gate",
            "same_live_side_factor_handles_verified": True,
            "primary_diagnostics": dict(primary_diagnostics),
            "backup_linearity_gate": dict(gate),
            "method_history": list(self._method_history),
            "collective_signature_sha256": hashlib.sha256(
                signatures[0].encode("utf-8")
            ).hexdigest(),
        }

    def _start_outer_observation_segment(
        self, name: str, *, boundary_reason: str
    ) -> None:
        """Start a new bounded residual window without clearing cumulative work."""

        if self._outer_window_points or self._outer_completed_windows:
            self._outer_segment_history.append(
                {
                    "segment": self._outer_observation_segment,
                    "boundary_reason": str(boundary_reason),
                    "last_iteration": self._outer_last_observed_iteration,
                    "completed_windows": [
                        dict(row) for row in self._outer_completed_windows
                    ],
                    "partial_window": [dict(row) for row in self._outer_window_points],
                }
            )
            self._outer_segment_history = self._outer_segment_history[-4:]
        self._outer_observation_segment = str(name)
        self._outer_window_points = []
        self._outer_completed_windows = []
        self._outer_metrics_passed_in_segment = set()
        self._outer_last_observed_iteration = None

    def resolve_side_restart64_trial(self, record: Mapping[str, Any]) -> None:
        """Collectively persist one trial result and begin a fresh outer window."""

        if self._side_restart64_trial_state is None:
            raise RuntimeError("the sealed modal policy has no side trial state")
        local_error = None
        payload = None
        try:
            if self._solve_in_progress or self._backup_switches != 1:
                raise RuntimeError("restart64 result arrived outside a post-backup safe point")
            status = record.get("status")
            if status not in {
                "trial_completed_selected_64",
                "trial_completed_retained_32",
                "capacity_gate_refused",
                "capacity_gate_refused_restart32_restore",
                "not_required_no_eligible_restart32_rhs",
            }:
                raise ValueError("restart64 result has an unsupported terminal status")
            if status == "capacity_gate_refused":
                refusal_gate = record.get("gate")
                phase = record.get("stage")
                if (
                    phase not in {"capture_restart32_rhs", "allocate_restart64"}
                    or not _task041_v12_capacity_gate_has_byte_refusal(refusal_gate)
                    or refusal_gate.get("phase") != phase
                ):
                    raise ValueError(
                        "restart64 capacity refusal lacks phase-bound fresh B/delta/W evidence"
                    )
                if phase == "allocate_restart64" and (
                    record.get("restart32_restored") is not True
                    or record.get("restart32_restore_required") is not False
                    or not _task041_v12_capacity_gate_has_byte_admission(
                        record.get("restart32_restore_gate"),
                        phase="restore_restart32",
                        restart=32,
                    )
                ):
                    raise ValueError(
                        "restart64 refusal cannot continue without a fresh admitted restart32 restore"
                    )
            if status == "capacity_gate_refused_restart32_restore":
                refusal_gate = record.get("gate")
                if (
                    record.get("stage") != "restore_restart32"
                    or not _task041_v12_capacity_gate_has_byte_refusal(refusal_gate)
                    or refusal_gate.get("phase") != "restore_restart32"
                    or record.get("restart32_restore_required") is not True
                    or record.get("restart32_restored") is not False
                    or record.get("restore_capacity_stop_required") is not True
                ):
                    raise ValueError(
                        "restart32 restore refusal lacks the fresh byte gate or live-state record"
                    )
                restart64_gate = record.get("restart64_gate")
                if "restart64_rank_records" in record:
                    if (
                        not _task041_v12_capacity_gate_has_byte_admission(
                            restart64_gate,
                            phase="allocate_restart64",
                            restart=64,
                        )
                        or not _task041_v12_nonselected_restart64_trial_matches(
                            record, rank_count=self._comm.size
                        )
                    ):
                        raise ValueError(
                            "completed non-selected restart64 trial lacks same-RHS residual or per-rank evidence"
                        )
                elif (
                    not _task041_v12_capacity_gate_has_byte_refusal(restart64_gate)
                    or restart64_gate.get("phase") != "allocate_restart64"
                    or record.get("restart64_trial_selected_restart") is not None
                ):
                    raise ValueError("restart32 restore refusal has no prior restart64 gate evidence")
            if status in {
                "trial_completed_selected_64",
                "trial_completed_retained_32",
            }:
                eta32 = record.get("restart32_relative_residual")
                eta64 = record.get("restart64_relative_residual")
                selection = record.get("selection_evidence")
                selection_matches = _task041_v12_restart64_selection_matches(
                    record, rank_count=self._comm.size
                )
                rank_records = record.get("restart64_rank_records")
                gate = record.get("restart64_gate")
                residual = record.get("restart64_original_D_residual")
                rhs_binding = record.get("candidate_rhs_binding")
                residual_keys = {
                    "rhs_norm",
                    "solution_norm",
                    "residual_norm",
                    "relative_residual",
                }
                residual_values = (
                    [residual.get(key) for key in residual_keys]
                    if isinstance(residual, Mapping)
                    else []
                )
                residual_is_valid = bool(
                    isinstance(residual, Mapping)
                    and set(residual) == residual_keys
                    and all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and np.isfinite(float(value))
                        and float(value) >= 0.0
                        for value in residual_values
                    )
                    and isinstance(rhs_binding, Mapping)
                    and isinstance(
                        rhs_binding.get("original_D_rhs_norm"), (int, float)
                    )
                    and not isinstance(rhs_binding.get("original_D_rhs_norm"), bool)
                    and np.isfinite(float(rhs_binding["original_D_rhs_norm"]))
                    and float(rhs_binding["original_D_rhs_norm"]) > 0.0
                    and isinstance(rhs_binding.get("global_size"), int)
                    and not isinstance(rhs_binding.get("global_size"), bool)
                    and rhs_binding["global_size"] > 0
                    and residual["rhs_norm"]
                    == rhs_binding["original_D_rhs_norm"]
                    and float(residual["relative_residual"])
                    == float(eta64)
                    and np.isclose(
                        float(residual["relative_residual"]),
                        float(residual["residual_norm"])
                        / float(residual["rhs_norm"]),
                        rtol=1.0e-12,
                        atol=1.0e-15,
                    )
                )
                if (
                    record.get("same_p4_factor_handle_all_ranks") is not True
                    or record.get("selection_rule")
                    != _TASK041_V12_MODAL_BACKUP_POLICY["side_restart64_trial"][
                        "selection_rule"
                    ]
                    or type(eta32) not in (int, float)
                    or type(eta64) not in (int, float)
                    or isinstance(eta32, bool)
                    or isinstance(eta64, bool)
                    or not np.isfinite(float(eta32))
                    or not np.isfinite(float(eta64))
                    or eta32 < 0.0
                    or eta64 < 0.0
                    or not isinstance(selection, Mapping)
                    or not selection_matches
                    or not residual_is_valid
                    or len(
                        rank_records
                        if isinstance(rank_records, list)
                        else ()
                    )
                    != self._comm.size
                    or not isinstance(gate, Mapping)
                    or not _task041_v12_capacity_gate_has_byte_admission(
                        gate, phase="allocate_restart64", restart=64
                    )
                    or record.get("selected_restart")
                    != (64 if selection.get("eligible_for_64") is True else 32)
                    or status
                    != (
                        "trial_completed_selected_64"
                        if selection.get("eligible_for_64") is True
                        else "trial_completed_retained_32"
                    )
                    or any(
                        not isinstance(row, Mapping)
                        or row.get("rank") != rank
                        or row.get("ksp_reason") != record.get("restart64_reason")
                        or row.get("iterations")
                        != record.get("restart64_iterations")
                        or row.get("same_p4_factor_handle_local") is not True
                        or row.get("candidate_rhs_unchanged_local") is not True
                        or not isinstance(row.get("original_D_residual"), Mapping)
                        or dict(row.get("original_D_residual", {})) != dict(residual)
                        for rank, row in enumerate(rank_records or ())
                    )
                ):
                    raise ValueError(
                        "side restart64 terminal lacks same-factor, same-RHS, residual, or selection evidence"
                    )
                if status == "trial_completed_selected_64":
                    if (
                        record.get("restart32_original_handle_destroyed") is not True
                        or record.get("restart64_handle_retained") is not True
                        or record.get("restart32_restore_required") is not False
                        or record.get("restart32_restored") is not False
                        or self._side_restart64_trial_state is None
                    ):
                        raise ValueError(
                            "selected restart64 record has an invalid live-handle inventory"
                        )
                elif (
                    record.get("restart32_original_handle_destroyed") is not True
                    or record.get("restart32_restore_required") is not False
                    or record.get("restart32_restored") is not True
                    or not _task041_v12_capacity_gate_has_byte_admission(
                        record.get("restart32_restore_gate"),
                        phase="restore_restart32",
                        restart=32,
                    )
                ):
                    raise ValueError(
                        "restart32 was not freshly admitted and restored after an unselected trial"
                    )
            if status == "not_required_no_eligible_restart32_rhs":
                side_seen = record.get("side_solve_seen")
                if not isinstance(side_seen, Mapping) or side_seen != {
                    "bottom": True,
                    "top": True,
                }:
                    raise ValueError(
                        "no-trial terminal requires post-stagnation applies on both sides"
                    )
            payload = json.dumps(
                dict(record), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except Exception as exc:  # noqa: BLE001 - synchronize safe-point state
            local_error = f"{type(exc).__name__}: {exc}"
        records = self._comm.allgather((local_error, payload))
        errors = [
            f"rank {rank}: {error}"
            for rank, (error, _payload) in enumerate(records)
            if error is not None
        ]
        payloads = [value for error, value in records if error is None]
        if payloads and any(value != payloads[0] for value in payloads[1:]):
            errors.append("restart64 trial result differs across ranks")
        if errors:
            raise RuntimeError("restart64 result was not agreed; " + "; ".join(errors))
        self._side_restart64_trial_state["status"] = record["status"]
        self._side_restart64_trial_state["result"] = dict(record)
        self._side_restart64_trial_state["trial_count"] = 1
        self._side_restart64_trial_state["resolved"] = True
        self._side_restart64_trial_state["pending"] = False
        self._start_outer_observation_segment(
            "post_side_restart64_trial",
            boundary_reason=str(record["status"]),
        )
        self._post_backup_stop_pending = None
        self._post_backup_capacity_stop_pending = None
        if record.get("status") == "capacity_gate_refused_restart32_restore":
            self._post_backup_capacity_stop_pending = {
                "schema": "task041.v12.post_backup_capacity_stop.v1",
                "status": "post_backup_restart32_restore_capacity_stop",
                "stop_reason": (
                    "task041_v12_restart32_restore_workspace_capacity_refused"
                ),
                "capacity_gate": dict(record["gate"]),
                "side_trial_record": dict(record),
                "side_restart64_trial_status": record["status"],
                "backup_switches": 1,
                "converged": False,
                "max_it_reached": False,
            }

    def reject_feedback_candidate(
        self, *, trigger: Mapping[str, Any], reason: str
    ) -> None:
        """Record a synchronized failed candidate gate without changing methods."""

        payload = {
            "trigger": dict(trigger),
            "reason": str(reason),
            "switch_count": int(self._backup_switches),
        }
        records = self._comm.allgather(payload)
        if any(record != records[0] for record in records[1:]):
            raise RuntimeError("backup rejection record differs across ranks")
        self._backup_pending = False
        self._backup_switch_audit = {
            "requested": True,
            "allowed": False,
            "actual": False,
            "switch_count": int(self._backup_switches),
            "trigger": dict(trigger),
            "status": "backup_candidate_rejected",
            "rejection_reason": str(reason),
            "method_history": list(self._method_history),
        }

    def observe_outer_true_residual(
        self,
        residual_row: Mapping[str, Any],
        *,
        gate_threshold: float | None = None,
    ) -> dict[str, Any] | None:
        """Track evidence-backed best residuals over bounded eight-step windows."""

        if not _task041_modal_policy_allows_backup(self.modal_solver_policy):
            return None
        if self._backup_pending:
            return None
        metrics = tuple(self.modal_solver_policy["outer_stagnation_metrics"])
        global_metric = "global_true_relative_residual"
        block_metrics = tuple(
            name for name in metrics if name != global_metric
        )
        window = int(self.modal_solver_policy["outer_stagnation_window_steps"])
        improvement_limit = float(
            self.modal_solver_policy["outer_stagnation_window_improvement_max"]
        )
        expected_threshold = float(
            self.modal_solver_policy[
                "outer_stagnation_residual_gate_threshold"
            ]
        )
        local_error = None
        local_signature = None
        try:
            raw_iteration = residual_row["iteration"]
            if type(raw_iteration) is not int or raw_iteration < 0:
                raise ValueError("outer residual row has an invalid iteration")
            iteration = raw_iteration
            actual_threshold = (
                expected_threshold
                if gate_threshold is None
                else float(gate_threshold)
            )
            if (
                not np.isfinite(actual_threshold)
                or actual_threshold <= 0.0
                or actual_threshold != expected_threshold
            ):
                raise ValueError(
                    "outer stagnation observer must use the sealed original residual gate"
                )
            residual_values = {
                name: float(residual_row[name]) for name in metrics
            }
            if any(
                not np.isfinite(value) or value < 0.0
                for value in residual_values.values()
            ):
                raise ValueError(
                    "outer residual row is non-finite or negative"
                )
            point = {
                "iteration": iteration,
                "residuals": residual_values,
            }
            local_signature = json.dumps(
                {"gate_threshold": actual_threshold, "point": point},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except Exception as exc:  # noqa: BLE001 - synchronize malformed local rows
            local_error = f"{type(exc).__name__}: {exc}"
        row_records = self._comm.allgather((local_error, local_signature))
        row_errors = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(row_records)
            if error is not None
        ]
        row_signatures = [
            signature for error, signature in row_records if error is None
        ]
        if row_errors:
            raise RuntimeError(
                "outer true-residual row validation failed; "
                + "; ".join(row_errors)
            )
        if row_signatures and any(
            signature != row_signatures[0] for signature in row_signatures[1:]
        ):
            raise RuntimeError(
                "outer true-residual row differs across ranks"
            )
        if not row_signatures:
            raise RuntimeError("outer true-residual row was not agreed across ranks")
        point = json.loads(row_signatures[0])["point"]
        iteration = int(point["iteration"])

        last_iteration = self._outer_last_observed_iteration
        if last_iteration is not None and iteration <= last_iteration:
            if (
                iteration == last_iteration
                and self._outer_window_points
                and point == self._outer_window_points[-1]
            ):
                return None
            self._outer_window_points = [point]
            self._outer_completed_windows = []
            self._outer_last_observed_iteration = iteration
            return {
                "status": "outer_window_evidence_reset",
                "reason": "non_monotone_or_conflicting_outer_iteration",
                "reset_iteration": iteration,
            }
        if last_iteration is not None and iteration != last_iteration + 1:
            self._outer_window_points = [point]
            self._outer_completed_windows = []
            self._outer_last_observed_iteration = iteration
            return {
                "status": "outer_window_evidence_reset",
                "reason": "nonconsecutive_outer_iteration",
                "reset_iteration": iteration,
            }
        if not self._outer_window_points:
            self._outer_window_points = [point]
            self._outer_last_observed_iteration = iteration
            return None
        self._outer_window_points.append(point)
        self._outer_last_observed_iteration = iteration
        start_iteration = int(self._outer_window_points[0]["iteration"])
        if iteration - start_iteration < window:
            return None
        if iteration - start_iteration != window:
            self._outer_window_points = [point]
            self._outer_completed_windows = []
            return {
                "status": "outer_window_evidence_reset",
                "reason": "outer_window_step_count_mismatch",
                "reset_iteration": iteration,
            }

        samples = [dict(sample) for sample in self._outer_window_points]
        residual_maps = [sample["residuals"] for sample in samples]
        best_sample_by_metric = {
            name: min(
                samples,
                key=lambda sample: (
                    float(sample["residuals"][name]),
                    int(sample["iteration"]),
                ),
            )
            for name in metrics
        }
        best_residual_by_metric = {
            name: float(best_sample_by_metric[name]["residuals"][name])
            for name in metrics
        }
        best_iteration_by_metric = {
            name: int(best_sample_by_metric[name]["iteration"])
            for name in metrics
        }
        end_residual_by_metric = {
            name: float(residual_maps[-1][name]) for name in metrics
        }
        if self._outer_completed_windows:
            previous_window = self._outer_completed_windows[-1]
            baseline_source = "previous_window_best"
            baseline_best_by_metric = dict(
                previous_window["best_residual_by_metric"]
            )
            baseline_best_iteration_by_metric = dict(
                previous_window["best_iteration_by_metric"]
            )
        else:
            baseline_source = "segment_start_sample"
            baseline_best_by_metric = {
                name: float(residual_maps[0][name]) for name in metrics
            }
            baseline_best_iteration_by_metric = {
                name: int(samples[0]["iteration"]) for name in metrics
            }
        improvement_by_metric: dict[str, float | None] = {}
        for name in metrics:
            baseline = float(baseline_best_by_metric[name])
            current_best = best_residual_by_metric[name]
            if baseline == 0.0:
                improvement_by_metric[name] = (
                    0.0 if current_best == 0.0 else None
                )
                continue
            with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                fraction = float((baseline - current_best) / baseline)
            improvement_by_metric[name] = (
                fraction if np.isfinite(fraction) else None
            )

        passed_metrics_at_window_end = [
            name
            for name in metrics
            if end_residual_by_metric[name] <= expected_threshold
        ]
        passed_metrics_in_window = [
            name
            for name in metrics
            if best_residual_by_metric[name] <= expected_threshold
        ]
        self._outer_metrics_passed_in_segment.update(passed_metrics_in_window)
        passed_metrics_in_segment = [
            name for name in metrics if name in self._outer_metrics_passed_in_segment
        ]
        required_metrics_in_window = [
            name for name in metrics if name not in passed_metrics_in_window
        ]
        # Stagnation is judged against blocks that still miss the gate at this
        # window's endpoint. A brief in-window crossing followed by regression
        # remains visible in ``passed_metrics_in_segment`` but must not mask a
        # currently failing block from the next stop decision.
        required_metrics_for_stagnation = [
            name for name in metrics if name not in passed_metrics_at_window_end
        ]
        required_improvements = [
            improvement_by_metric[name] for name in required_metrics_for_stagnation
        ]
        window_stalled = bool(
            required_metrics_for_stagnation
            and all(
                value is not None and value < improvement_limit
                for value in required_improvements
            )
        )
        window_record = {
            "start_iteration": start_iteration,
            "end_iteration": iteration,
            "gate_threshold": expected_threshold,
            "baseline_source": baseline_source,
            "baseline_best_by_metric": baseline_best_by_metric,
            "baseline_best_iteration_by_metric": (
                baseline_best_iteration_by_metric
            ),
            "best_residual_by_metric": best_residual_by_metric,
            "best_iteration_by_metric": best_iteration_by_metric,
            "end_residual_by_metric": end_residual_by_metric,
            "improvement_fraction_by_metric": improvement_by_metric,
            "passed_metrics_in_window": passed_metrics_in_window,
            "passed_metrics_in_segment": passed_metrics_in_segment,
            "required_metrics_in_window": required_metrics_in_window,
            "required_metrics_for_stagnation": required_metrics_for_stagnation,
            "passed_metrics_at_window_end": passed_metrics_at_window_end,
            "required_metrics_at_window_end": [
                name for name in metrics if name not in passed_metrics_at_window_end
            ],
            "global_metric_required": global_metric in required_metrics_for_stagnation,
            "unmet_block_metrics": [
                name
                for name in block_metrics
                if name in required_metrics_for_stagnation
            ],
            "stalled": window_stalled,
            "samples": samples,
        }
        window_signature = json.dumps(
            window_record,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        records = self._comm.allgather(window_signature)
        if any(value != records[0] for value in records[1:]):
            raise RuntimeError(
                "outer true-residual window evidence differs across ranks"
            )
        self._outer_completed_windows.append(window_record)
        self._outer_completed_windows = self._outer_completed_windows[-3:]
        # Adjacent windows share their boundary sample: [0..8], [8..16], ...
        # Keep that actual row as the next window's baseline rather than
        # restarting at the following iteration.
        self._outer_window_points = [point]
        stalled_windows = self._outer_completed_windows[-2:]
        stalled = bool(
            len(stalled_windows) == 2
            and all(bool(record["stalled"]) for record in stalled_windows)
        )
        observation = {
            "status": "two_consecutive_outer_windows_stalled"
            if stalled
            else "outer_progress_not_stalled",
            "observation_segment": self._outer_observation_segment,
            "observed_at_iteration": iteration,
            "windows": [dict(record) for record in self._outer_completed_windows],
            "stalled_window_end_iterations": (
                [int(record["end_iteration"]) for record in stalled_windows]
                if stalled
                else []
            ),
            "required_max_improvement_fraction": improvement_limit,
            "residual_gate_threshold": expected_threshold,
            "metrics": list(metrics),
            "global_metric": global_metric,
            "block_metrics": list(block_metrics),
            "next_safe_boundary": "next_outer_PC_modal_solve_before_KSP_entry",
        }
        restart_outer_observation = False
        if stalled and self._backup_switches == 0:
            self._backup_pending = True
            self._backup_switch_audit = {
                "requested": True,
                "allowed": False,
                "actual": False,
                "switch_count": int(self._backup_switches),
                "trigger": observation,
                "status": "backup_pending_next_safe_outer_PC_entry",
                "method_history": list(self._method_history),
            }
        elif stalled and self._backup_switches == 1:
            trial_state = self._side_restart64_trial_state
            trial_status = (
                trial_state.get("status")
                if isinstance(trial_state, dict)
                else "not_registered_for_this_caller"
            )
            if trial_status in {
                "trial_completed_selected_64",
                "trial_completed_retained_32",
                "capacity_gate_refused",
                "capacity_gate_refused_restart32_restore",
                "not_required_no_eligible_restart32_rhs",
            } and trial_state.get("resolved") is True:
                self._post_backup_stop_pending = {
                    "schema": "task041.v12.post_backup_finite_stop.v1",
                    "status": "post_backup_two_window_stagnation_after_trial_resolution",
                    "stop_reason": "task041_v12_post_backup_two_windows_stalled_after_side_trial_resolution",
                    "observation_segment": self._outer_observation_segment,
                    "observed_at_iteration": iteration,
                    "windows": [dict(row) for row in stalled_windows],
                    "side_restart64_trial_status": trial_status,
                    "backup_switches": 1,
                    "outer_observation": dict(observation),
                    "converged": False,
                    "max_it_reached": False,
                }
                observation["finite_stop_pending"] = dict(
                    self._post_backup_stop_pending
                )
            else:
                if not isinstance(trial_state, dict):
                    # Only the registered W0.7 construction provides the live
                    # side memory gate.  Other explicit V12 unit fixtures keep
                    # their prior behavior and cannot claim finite-stop closure.
                    observation["side_restart64_status"] = (
                        "not_registered_for_this_caller"
                    )
                else:
                    if trial_status == "candidate_captured":
                        trial_state["outer_stagnation_confirmed"] = True
                        trial_state["pending"] = True
                        observation["side_restart64_status"] = (
                            "trial_pending_next_safe_modal_entry"
                        )
                    elif trial_status in {"armed", "no_eligible_restart32_rhs"}:
                        # Side calls made before the first two stalled outer
                        # windows cannot satisfy the post-stagnation trial
                        # prerequisite.  Arm once, clear those observations,
                        # and start a fresh segment before watching side RHSs.
                        trial_state.update(
                            {
                                "status": "capture_armed",
                                "capture_armed": True,
                                "outer_stagnation_confirmed": True,
                                "post_backup_side_solve_seen": {
                                    "bottom": False,
                                    "top": False,
                                },
                                "capture_armed_after_iteration": iteration,
                            }
                        )
                        restart_outer_observation = True
                        observation["side_restart64_status"] = (
                            "capture_armed_after_outer_stagnation"
                        )
                    elif (
                        trial_status == "capture_armed"
                        and isinstance(
                            trial_state.get("post_backup_side_solve_seen"), Mapping
                        )
                        and trial_state["post_backup_side_solve_seen"].get(
                            "bottom"
                        ) is True
                        and trial_state["post_backup_side_solve_seen"].get(
                            "top"
                        ) is True
                    ):
                        seen = dict(trial_state["post_backup_side_solve_seen"])
                        trial_state.update(
                            {
                                "status": "not_required_no_eligible_restart32_rhs",
                                "resolved": True,
                                "pending": False,
                                "capture_armed": False,
                                "trial_count": 1,
                                "result": {
                                    "status": "not_required_no_eligible_restart32_rhs",
                                    "reason": (
                                        "both live sides completed post-stagnation applies "
                                        "without an eligible 128-step restart32 RHS"
                                    ),
                                    "side_solve_seen": seen,
                                },
                            }
                        )
                        restart_outer_observation = True
                        observation["side_restart64_status"] = (
                            "not_required_no_eligible_restart32_rhs"
                        )
                    elif trial_status == "capacity_gate_refused" and trial_state.get(
                        "resolved"
                    ) is True:
                        restart_outer_observation = True
                        observation["side_restart64_status"] = (
                            "capture_capacity_refused_trial_resolved"
                        )
                    elif trial_status == "capture_armed":
                        observation["side_restart64_status"] = trial_status
                    else:
                        observation["side_restart64_status"] = str(trial_status)
        if restart_outer_observation:
            self._start_outer_observation_segment(
                "post_backup_waiting_for_side_trial_resolution",
                boundary_reason="outer_stagnation_armed_one_side_trial",
            )
            self._outer_window_points = [point]
            self._outer_last_observed_iteration = iteration
        else:
            self._outer_window_points = [point]
        return observation

    def post_backup_stop_decision(self) -> dict[str, Any] | None:
        """Return a synchronized finite-stop request only after all V12 stages."""

        if not _task041_modal_policy_allows_backup(self.modal_solver_policy):
            return None
        capacity_stop = self._post_backup_capacity_stop_pending
        if capacity_stop is not None:
            trial_state = self._side_restart64_trial_state
            trial_result = (
                trial_state.get("result")
                if isinstance(trial_state, Mapping)
                else None
            )
            gate = capacity_stop.get("capacity_gate")
            if (
                self._backup_switches != 1
                or not isinstance(trial_state, Mapping)
                or trial_state.get("resolved") is not True
                or trial_state.get("pending") is not False
                or trial_state.get("trial_count") != 1
                or trial_state.get("status")
                != "capacity_gate_refused_restart32_restore"
                or not isinstance(trial_result, Mapping)
                or trial_result.get("status")
                != "capacity_gate_refused_restart32_restore"
                or trial_result.get("stage") != "restore_restart32"
                or trial_result.get("restart32_restore_required") is not True
                or trial_result.get("restart32_restored") is not False
                or trial_result.get("restart32_restored_handle_live") is not False
                or trial_result.get("restore_capacity_stop_required") is not True
                or trial_result.get("selected_restart") is not None
                or trial_result.get("same_p4_factor_handle_all_ranks") is not True
                or (
                    "restart64_rank_records" in trial_result
                    and not _task041_v12_nonselected_restart64_trial_matches(
                        trial_result, rank_count=self._comm.size
                    )
                )
                or (
                    "restart64_rank_records" not in trial_result
                    and (
                        not _task041_v12_capacity_gate_has_byte_refusal(
                            trial_result.get("restart64_gate")
                        )
                        or trial_result.get("restart64_trial_selected_restart")
                        is not None
                    )
                )
                or capacity_stop.get("schema")
                != "task041.v12.post_backup_capacity_stop.v1"
                or self._outer_observation_segment != "post_side_restart64_trial"
                or capacity_stop.get("status")
                != "post_backup_restart32_restore_capacity_stop"
                or capacity_stop.get("stop_reason")
                != "task041_v12_restart32_restore_workspace_capacity_refused"
                or capacity_stop.get("side_trial_record")
                != dict(trial_result)
                or not isinstance(gate, Mapping)
                or not _task041_v12_capacity_gate_has_byte_refusal(gate)
                or gate.get("phase") != "restore_restart32"
                or capacity_stop.get("side_restart64_trial_status")
                != trial_state.get("status")
                or type(self._outer_last_observed_iteration) is not int
                or self._outer_last_observed_iteration < 0
            ):
                return None
            stop = {
                **dict(capacity_stop),
                "observation_segment": self._outer_observation_segment,
                "observed_at_iteration": self._outer_last_observed_iteration,
                "current_ksp_iterate_available": True,
                "original_rhs_retained": True,
            }
            signature = json.dumps(
                stop, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            records = self._comm.allgather(signature)
            if any(value != records[0] for value in records[1:]):
                raise RuntimeError(
                    "post-backup capacity stop differs across ranks"
                )
            return stop

        stop = self._post_backup_stop_pending
        if stop is None:
            return None
        trial_state = self._side_restart64_trial_state
        trial_status = (
            trial_state.get("status") if isinstance(trial_state, Mapping) else None
        )
        trial_result = (
            trial_state.get("result") if isinstance(trial_state, Mapping) else None
        )
        if trial_status == "capacity_gate_refused":
            if (
                not isinstance(trial_result, Mapping)
                or not _task041_v12_capacity_gate_has_byte_refusal(
                    trial_result.get("gate")
                )
            ):
                return None
        elif trial_status == "not_required_no_eligible_restart32_rhs":
            side_seen = (
                trial_result.get("side_solve_seen")
                if isinstance(trial_result, Mapping)
                else None
            )
            if not isinstance(side_seen, Mapping) or side_seen != {
                "bottom": True,
                "top": True,
            }:
                return None
        elif trial_status in {
            "trial_completed_selected_64",
            "trial_completed_retained_32",
        }:
            if not isinstance(trial_result, Mapping):
                return None
            selection = trial_result.get("selection_evidence")
            selection_matches = _task041_v12_restart64_selection_matches(
                trial_result, rank_count=self._comm.size
            )
            expected_status = (
                "trial_completed_selected_64"
                if isinstance(selection, Mapping)
                and selection.get("eligible_for_64") is True
                else "trial_completed_retained_32"
            )
            if (
                trial_result.get("status") != trial_status
                or trial_status != expected_status
                or not selection_matches
                or trial_result.get("same_p4_factor_handle_all_ranks") is not True
                or trial_result.get("selected_restart")
                != (64 if trial_status == "trial_completed_selected_64" else 32)
                or not isinstance(trial_result.get("restart64_rank_records"), list)
                or len(trial_result["restart64_rank_records"]) != self._comm.size
            ):
                return None
        if (
            self._backup_switches != 1
            or not isinstance(trial_state, Mapping)
            or trial_state.get("resolved") is not True
            or trial_status
            not in {
                "trial_completed_selected_64",
                "trial_completed_retained_32",
                "capacity_gate_refused",
                "not_required_no_eligible_restart32_rhs",
            }
            or stop.get("observation_segment") != self._outer_observation_segment
            or stop.get("status")
            != "post_backup_two_window_stagnation_after_trial_resolution"
            or stop.get("stop_reason")
            != "task041_v12_post_backup_two_windows_stalled_after_side_trial_resolution"
            or not isinstance(stop.get("outer_observation"), Mapping)
            or stop["outer_observation"].get("status")
            != "two_consecutive_outer_windows_stalled"
            or len(stop.get("windows", ())) != 2
            or stop.get("windows")
            != stop["outer_observation"].get("windows", [])[-2:]
            or stop.get("observed_at_iteration")
            != stop["outer_observation"].get("observed_at_iteration")
            or stop.get("outer_observation", {}).get("observation_segment")
            != self._outer_observation_segment
            or stop.get("outer_observation", {}).get("stalled_window_end_iterations")
            != [window.get("end_iteration") for window in stop.get("windows", ())]
            or any(
                not isinstance(window, Mapping) or window.get("stalled") is not True
                for window in stop.get("windows", ())
            )
            or trial_state.get("trial_count") != 1
        ):
            return None
        signature = json.dumps(
            dict(stop), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        records = self._comm.allgather(signature)
        if any(value != records[0] for value in records[1:]):
            raise RuntimeError("post-backup finite-stop decision differs across ranks")
        return dict(stop)

    def record_post_backup_policy_stop(self, stop: Mapping[str, Any]) -> None:
        """Retain the finite stop decision without disguising it as KSP convergence."""

        local_error = None
        signature = None
        try:
            if self._solve_in_progress or self._backup_switches != 1:
                raise RuntimeError("post-backup stop is outside the outer solve callback")
            if stop.get("backup_switches") != 1:
                raise ValueError("policy stop must bind exactly one completed backup switch")
            if stop.get("converged") is not False or stop.get("max_it_reached") is not False:
                raise ValueError("policy stop cannot claim convergence or configured max-it")
            if stop.get("current_ksp_iterate_available") is not True or stop.get(
                "original_rhs_retained"
            ) is not True:
                raise ValueError("policy stop must retain the current iterate and original RHS")
            expected_reason = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
            expected_stop_reasons = {
                "post_backup_two_window_stagnation_after_trial_resolution": (
                    "task041_v12_post_backup_two_windows_stalled_after_side_trial_resolution"
                ),
                "post_backup_restart32_restore_capacity_stop": (
                    "task041_v12_restart32_restore_workspace_capacity_refused"
                ),
            }
            if (
                stop.get("status") not in expected_stop_reasons
                or stop.get("stop_reason")
                != expected_stop_reasons.get(stop.get("status"))
                or stop.get("reason_name") != "DIVERGED_MAX_IT"
                or stop.get("runtime_reason_source")
                != "petsc4py.PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT"
            ):
                raise ValueError("policy stop must preserve the runtime supported KSP reason identity")
            if stop.get("status") == "post_backup_restart32_restore_capacity_stop":
                gate = stop.get("capacity_gate")
                trial = stop.get("side_trial_record")
                if (
                    stop.get("schema")
                    != "task041.v12.post_backup_capacity_stop.v1"
                    or not isinstance(trial, Mapping)
                    or trial.get("status")
                    != "capacity_gate_refused_restart32_restore"
                    or trial.get("stage") != "restore_restart32"
                    or trial.get("gate") != gate
                    or not _task041_v12_capacity_gate_has_byte_refusal(gate)
                    or gate.get("phase") != "restore_restart32"
                    or stop.get("windows") not in (None, [])
                ):
                    raise ValueError(
                        "capacity stop requires the actual restart32 fresh byte refusal, not a stagnation label"
                    )
            elif (
                stop.get("status")
                == "post_backup_two_window_stagnation_after_trial_resolution"
                and (
                    stop.get("stop_reason")
                    != "task041_v12_post_backup_two_windows_stalled_after_side_trial_resolution"
                    or len(stop.get("windows", ())) != 2
                )
            ):
                raise ValueError(
                    "stagnation stop requires exactly two completed post-trial windows"
                )
            reason_code = stop.get("reason_code")
            if type(reason_code) is not int or reason_code != expected_reason or reason_code >= 0:
                raise ValueError("policy stop requires an actual non-success KSP reason")
            if type(stop.get("configured_max_it")) is not int or type(
                stop.get("iterations_at_stop")
            ) is not int or not 1 <= stop["iterations_at_stop"] < stop["configured_max_it"]:
                raise ValueError("finite policy stop must occur before configured max-it")
            signature = json.dumps(
                dict(stop), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except Exception as exc:  # noqa: BLE001 - all ranks agree before stop
            local_error = f"{type(exc).__name__}: {exc}"
        records = self._comm.allgather((local_error, signature))
        errors = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(records)
            if error is not None
        ]
        signatures = [value for error, value in records if error is None]
        if signatures and any(value != signatures[0] for value in signatures[1:]):
            errors.append("post-backup stop record differs across ranks")
        if errors:
            raise RuntimeError("post-backup finite stop was not agreed; " + "; ".join(errors))
        self._post_backup_stop_record = dict(stop)

    def finalize_post_backup_policy_stop(self, stop: Mapping[str, Any]) -> None:
        """Bind a requested policy stop to the returned finite x and unchanged f."""

        local_error = None
        signature = None
        try:
            if self._solve_in_progress or self._backup_switches != 1:
                raise RuntimeError("finite-stop solution finalization is not at solve return")
            if self._post_backup_stop_record is None:
                raise RuntimeError("finite-stop return has no previously agreed request")
            if any(
                stop.get(key) != value
                for key, value in self._post_backup_stop_record.items()
                if key != "current_trusted_solution_retained"
            ):
                raise ValueError("finite-stop return changed the agreed stop request")
            if (
                self._post_backup_stop_record.get("current_trusted_solution_retained")
                is not False
                or stop.get("current_trusted_solution_retained") is not True
            ):
                raise ValueError("finite-stop return did not promote the same iterate to retained x")
            if any(
                not isinstance(stop.get(key), Mapping)
                for key in (
                    "postsolve_true_residuals",
                    "rank_local_solution_rhs_binding",
                )
            ):
                raise ValueError("finite-stop return lacks true residual or sharded x/f evidence")
            if stop.get("current_trusted_solution_retained") is not True:
                raise ValueError("finite-stop return did not retain a trusted current solution")
            if stop.get("original_rhs_unchanged") is not True:
                raise ValueError("finite-stop return changed the original right-hand side")
            if stop.get("postsolve_all_finite_nonnegative") is not True:
                raise ValueError("finite-stop return lacks finite postsolve residuals")
            residuals = stop["postsolve_true_residuals"]
            if set(residuals) != set(_RESIDUAL_KEYS) or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not np.isfinite(float(value))
                or float(value) < 0.0
                for value in residuals.values()
            ):
                raise ValueError("finite-stop residual record is incomplete or non-finite")
            reason_code = stop.get("reason_code")
            if (
                type(reason_code) is not int
                or reason_code != int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
                or stop.get("reason_name") != "DIVERGED_MAX_IT"
                or stop.get("runtime_reason_source")
                != "petsc4py.PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT"
                or stop.get("converged") is not False
                or stop.get("max_it_reached") is not False
                or stop.get("current_ksp_iterate_available") is not True
                or stop.get("original_rhs_retained") is not True
            ):
                raise ValueError("finite-stop final record changed its actual reason or state")
            signature = json.dumps(
                dict(stop), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except Exception as exc:  # noqa: BLE001 - all ranks agree before checkpoint
            local_error = f"{type(exc).__name__}: {exc}"
        records = self._comm.allgather((local_error, signature))
        errors = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(records)
            if error is not None
        ]
        signatures = [value for error, value in records if error is None]
        if signatures and any(value != signatures[0] for value in signatures[1:]):
            errors.append("finite-stop x/f evidence differs across ranks")
        if errors:
            raise RuntimeError("finite-stop result was not finalized; " + "; ".join(errors))
        self._post_backup_stop_record = dict(stop)

    def record_outer_terminal(self, decision: Mapping[str, Any]) -> None:
        """Cancel a pending switch when no later outer-PC boundary can occur."""

        if not _task041_modal_policy_allows_backup(self.modal_solver_policy):
            return
        if self._backup_switches == 1:
            # The current outer iterate has reached its own terminal decision;
            # it takes precedence over a pending capacity-stop request because
            # no further preconditioner application will be required.
            self._post_backup_capacity_stop_pending = None
            return
        if not self._backup_pending or self._backup_switches:
            return
        safe_residuals = {}
        for name, value in dict(decision.get("residuals", {})).items():
            scalar = float(value)
            safe_residuals[str(name)] = (
                scalar if np.isfinite(scalar) else str(scalar)
            )
        terminal = {
            key: decision.get(key)
            for key in (
                "identity",
                "iteration",
                "threshold",
                "all_finite_nonnegative",
                "positive",
                "decision",
                "reason",
            )
        }
        terminal["residuals"] = safe_residuals
        local_record = json.dumps(
            terminal, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        records = self._comm.allgather(local_record)
        if any(record != records[0] for record in records[1:]):
            raise RuntimeError("outer terminal decision differs across ranks")
        solved = bool(
            terminal.get("positive") is True
            and terminal.get("decision")
            in {"CONVERGED_USER", "CONVERGED_RTOL"}
        )
        self._backup_pending = False
        if self._side_restart64_trial_state is not None:
            self._side_restart64_trial_state["outer_terminal_before_backup"] = True
        self._backup_switch_audit = {
            "requested": True,
            "allowed": False,
            "actual": False,
            "switch_count": 0,
            "trigger": dict(self._backup_switch_audit.get("trigger") or {}),
            "status": (
                "backup_not_needed_outer_converged_before_next_PC_boundary"
                if solved
                else "backup_not_run_outer_terminated_before_next_PC_boundary"
            ),
            "outer_terminal_decision": terminal,
            "method_history": list(self._method_history),
        }

    def rollback_feedback_candidate(
        self,
        previous: tuple[Any, Any, Any, str, str | None, str],
    ) -> None:
        if self._solve_in_progress:
            raise RuntimeError("cannot roll back modal feedback during a solve")
        (
            self._modal_action,
            self._bottom_action,
            self._top_action,
            self.method,
            self.actual_feedback_method,
            self._action_operator,
        ) = previous

    @staticmethod
    def destroy_previous_feedback_candidate(
        previous: tuple[Any, Any, Any, str, str | None, str],
    ) -> None:
        previous_action = previous[0]
        if previous_action is not None:
            previous_action.destroy()

    def _raise_collective_error(self, local_error: str | None, stage: str) -> None:
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            raise RuntimeError(f"Fixed-H6 modal {stage} failed; " + "; ".join(failures))

    def _mat_mult(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        local_error = None
        owner = self._modal_owner
        expected = self.modal_count if self._comm.rank == owner else 0
        try:
            if self._destroyed:
                raise RuntimeError("Fixed-H6 modal system was destroyed")
            if source.getLocalSize() != expected or target.getLocalSize() != expected:
                raise ValueError("S_H MatMult ownership differs from modal layout")
            if self._in_final_check:
                if self._total_matmult_calls >= self.total_matmult_limit:
                    self._budget_exhausted = True
                    raise RuntimeError("S_H total MatMult budget exhausted")
            elif self._solver_matmult_calls >= self.solver_matmult_limit:
                self._budget_exhausted = True
                raise RuntimeError("S_H solver MatMult budget exhausted")
        except Exception as exc:  # noqa: BLE001 - all ranks reject before action calls
            local_error = f"{type(exc).__name__}: {exc}"
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            detail = "; ".join(failures)
            if self._budget_exhausted:
                self._blocked_matmult_attempts += 1
                self._last_solve.update(
                    status="budget_exhausted",
                    final_residual_evaluated=False,
                    final_residual_status="not_evaluated",
                    final_residual_not_evaluated_reason=(
                        "solver_matmult_budget_exhausted_before_trusted_iterate"
                    ),
                    budget_used_solver_matmult_calls=self._solver_matmult_calls,
                    budget_used_total_matmult_calls=self._total_matmult_calls,
                    blocked_matmult_attempts=self._blocked_matmult_attempts,
                )
            else:
                self._mat_preflight_failure = detail
                self._last_solve.update(
                    status="mat_preflight_failed",
                    final_residual_evaluated=False,
                    final_residual_status="not_evaluated",
                    final_residual_not_evaluated_reason=(
                        "MatMult_vector_layout_rejected_before_S_H"
                    ),
                )
            raise RuntimeError(f"Fixed-H6 modal MatMult preflight failed; {detail}")

        self._total_matmult_calls += 1
        if not self._in_final_check:
            self._solver_matmult_calls += 1
        local_values = (
            np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
            if self._comm.rank == owner
            else None
        )
        values = np.asarray(self._comm.bcast(local_values, root=owner), dtype=np.complex128)
        # The action itself contains multiple PETSc collectives.  Do not wrap it
        # in a local try/allgather: an arbitrary rank-local callback exception
        # cannot safely be synchronized after those collectives have diverged.
        try:
            result = self._modal_action.apply(values)
        except BaseException as exc:
            self._modal_action_failure = f"{type(exc).__name__}: {exc}"
            raise
        local_error = None
        if result.shape != (self.modal_count,) or not np.all(np.isfinite(result)):
            local_error = "FloatingPointError: S_H returned a malformed or non-finite vector"
        try:
            self._raise_collective_error(local_error, "MatMult result")
        except BaseException as exc:
            self._modal_action_failure = f"{type(exc).__name__}: {exc}"
            raise
        if self._comm.rank == owner:
            target.getArray()[:] = result
        if self._in_final_check:
            self._last_solve["final_residual_evaluated"] = True

    def _apply_constraint_pc(
        self, pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self._pc_failure_error is not None:
            pc.setFailedReason(PETSc.PC.FailedReason.SUBPC_ERROR)
            target.set(PETSc.ScalarType(np.inf))
            return
        owner = self._modal_owner
        expected = self.modal_count if self._comm.rank == owner else 0
        local_error = None
        values = solved = None
        try:
            if source.getLocalSize() != expected or target.getLocalSize() != expected:
                raise ValueError("C-LU PC ownership differs from modal layout")
            if self._comm.rank == owner:
                values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
                if not np.all(np.isfinite(values)):
                    raise FloatingPointError("C-LU PC input is non-finite")
                self._constraint_lu_solve_attempts += 1
                solved = lu_solve(
                    (self._constraint_lu, self._constraint_pivots),
                    values,
                    check_finite=True,
                )
                if not np.all(np.isfinite(solved)):
                    raise FloatingPointError("C-LU PC result is non-finite")
                self._constraint_lu_solve_successes += 1
        except Exception as exc:  # noqa: BLE001 - synchronize owner solve failures
            local_error = f"{type(exc).__name__}: {exc}"
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            # Keep the local latch for result classification and also report
            # failure through PETSc's Python-PC channel.  The non-finite
            # output cannot be mistaken for a valid preconditioned vector.
            self._pc_failure_error = "; ".join(failures)
            pc.setFailedReason(PETSc.PC.FailedReason.SUBPC_ERROR)
            target.set(PETSc.ScalarType(np.inf))
            return
        if self._comm.rank == owner:
            target.getArray()[:] = solved

    def _reset_attempt(self) -> None:
        self._solver_matmult_calls = self._total_matmult_calls = 0
        self._blocked_matmult_attempts = 0
        self._constraint_lu_solve_attempts = 0
        self._constraint_lu_solve_successes = 0
        self._owner_constraint_lu_solve_attempts_this_solve = None
        self._owner_constraint_lu_solve_successes_this_solve = None
        self._owner_constraint_lu_solve_counts_authoritative = False
        self._budget_exhausted = False
        self._pc_failure_error = None
        self._mat_preflight_failure = None
        self._modal_action_failure = None
        self._iteration_scalar_history = []
        self._rhs_input_sha256 = None
        self._rhs_input_bytes = None
        self._last_solve = {
            "status": "running",
            "ksp_reason": None,
            "zero_initial_guess": True,
            "solver_matmult_calls": 0,
            "total_matmult_calls": 0,
            "final_residual_evaluated": False,
            "final_residual_status": "not_evaluated",
            "local_constraint_lu_solve_attempts": 0,
            "local_constraint_lu_solve_successes": 0,
            "owner_constraint_lu_solve_attempts": None,
            "owner_constraint_lu_solve_successes": None,
            "owner_constraint_lu_solve_counts_authoritative": False,
            "constraint_lu_solve_count_scope": (
                "not_yet_obtained_for_this_solve"
            ),
        }
        # Match the existing BAL_H KSP lifecycle: clear the prior callback
        # failure before each new solve, then latch SUBPC_ERROR on a new one.
        self._ksp.getPC().setFailedReason(PETSc.PC.FailedReason.NOERROR)

    def _persist_normal_return_snapshot(
        self,
        *,
        kind: str | None,
        reason: int,
        iterations: int,
        relative: float | None,
        raw_residual_pass: bool,
        rhs_norm: float,
    ) -> dict[str, Any] | None:
        if kind is None:
            return None
        owner_result: tuple[str | None, Mapping[str, Any] | None] | None = None
        if self._comm.rank == self._modal_owner:
            try:
                if self._snapshot_callback is None:
                    raise RuntimeError(
                        "V12 modal policy requires an owner snapshot callback"
                    )
                rhs = np.asarray(
                    self._rhs.getArray(readonly=True), dtype=np.complex128
                ).copy()
                iterate = np.asarray(
                    self._solution.getArray(readonly=True), dtype=np.complex128
                ).copy()
                raw_residual = np.asarray(
                    self._residual.getArray(readonly=True), dtype=np.complex128
                ).copy()
                payload = {
                    "snapshot_kind": kind,
                    "policy_id": self.modal_solver_policy["policy_id"],
                    "policy": dict(self.modal_solver_policy),
                    "method": self.method,
                    "status": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get("status")
                    ),
                    "modal_solve_ordinal": self._solve_count + 1,
                    "outer_pc_apply_index": self._outer_pc_apply_index,
                    "modal_owner": self._modal_owner,
                    "rank_count": int(self._comm.size),
                    "ksp_reason": int(reason),
                    "iterations": int(iterations),
                    "rhs_norm": float(rhs_norm),
                    "raw_relative_residual": relative,
                    "raw_residual_pass": bool(raw_residual_pass),
                    "trusted_iterate": bool(
                        self._last_solve is not None
                        and self._last_solve.get("trusted_iterate") is True
                    ),
                    "input_unchanged": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get("input_unchanged")
                    ),
                    "normal_return_rejection_reason": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get(
                            "normal_return_rejection_reason"
                        )
                    ),
                    "final_residual_norm": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get("final_residual_norm")
                    ),
                    "final_relative_residual": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get("final_relative_residual")
                    ),
                    "final_residual_evaluated": (
                        self._last_solve is not None
                        and self._last_solve.get("final_residual_evaluated") is True
                    ),
                    "approximate_return_decision": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get("approximate_return_decision")
                    ),
                    "backup_eligibility": (
                        None
                        if self._last_solve is None
                        else self._last_solve.get("backup_eligibility")
                    ),
                    "pc_usable": bool(
                        self._last_solve is not None
                        and self._last_solve.get("pc_usable") is True
                    ),
                    "solver_matmult_calls": int(self._solver_matmult_calls),
                    "total_matmult_calls": int(self._total_matmult_calls),
                    "scalar_history": list(self._iteration_scalar_history),
                    "g": rhs,
                    "m": iterate,
                    "raw_residual": raw_residual,
                }
                written = self._snapshot_callback(payload)
                if not isinstance(written, Mapping):
                    raise TypeError("modal snapshot callback returned no index record")
                owner_result = (None, dict(written))
            except Exception as exc:  # noqa: BLE001 - normal-return snapshot is required
                owner_result = (f"{type(exc).__name__}: {exc}", None)
        error, written = self._comm.bcast(owner_result, root=self._modal_owner)
        if error is not None:
            raise RuntimeError(f"V12 modal snapshot failed: {error}")
        return dict(written or {})

    def _final_residual(self, rhs_norm: float) -> tuple[float | None, bool]:
        if self._budget_exhausted or self._total_matmult_calls >= self.total_matmult_limit:
            self._budget_exhausted = True
            self._last_solve.update(
                status="budget_exhausted",
                final_residual_evaluated=False,
                final_residual_status="not_evaluated",
                final_residual_not_evaluated_reason="S_H_matmult_budget_reserved_or_exhausted",
                budget_used_solver_matmult_calls=self._solver_matmult_calls,
                budget_used_total_matmult_calls=self._total_matmult_calls,
                blocked_matmult_attempts=self._blocked_matmult_attempts,
            )
            return None, False
        self._in_final_check = True
        try:
            self._matrix.mult(self._solution, self._image)
        finally:
            self._in_final_check = False
        self._rhs.copy(self._residual)
        self._residual.axpy(PETSc.ScalarType(-1.0), self._image)
        residual_norm = float(self._residual.norm())
        finite = bool(np.isfinite(residual_norm) and np.isfinite(rhs_norm))
        relative = (
            residual_norm / rhs_norm if finite and rhs_norm > 0.0 else None
        )
        self._last_solve.update(
            final_residual_norm=residual_norm if finite else None,
            final_relative_residual=relative,
            final_residual_evaluated=True,
            final_residual_status="evaluated",
            final_residual_not_evaluated_reason=None,
        )
        return relative, finite and (residual_norm == 0.0 if rhs_norm == 0.0 else True)

    def _solve_once(self, rhs: np.ndarray) -> np.ndarray:
        self._reset_attempt()
        local_error = None
        values = None
        rhs_norm = float("nan")
        try:
            values = np.asarray(rhs, dtype=np.complex128)
            if values.shape != (self.modal_count,) or not np.all(np.isfinite(values)):
                raise ValueError("S_H RHS has the wrong shape or non-finite values")
            rhs_norm = float(np.linalg.norm(values))
            if not np.isfinite(rhs_norm):
                raise FloatingPointError("S_H RHS norm is non-finite")
            if self.modal_solver_policy is not None:
                self._rhs_input_bytes = values.tobytes()
                self._rhs_input_sha256 = hashlib.sha256(
                    self._rhs_input_bytes
                ).hexdigest()
        except Exception as exc:  # noqa: BLE001 - synchronize RHS rejection
            local_error = f"{type(exc).__name__}: {exc}"
        self._raise_collective_error(local_error, "RHS")
        digests = self._comm.allgather(hashlib.sha256(values.tobytes()).hexdigest())
        if len(set(digests)) != 1:
            self._raise_collective_error("modal RHS differs across ranks", "RHS")

        self._rhs.set(0.0)
        self._solution.set(0.0)
        if self._comm.rank == self._modal_owner:
            self._rhs.getArray()[:] = values
        self._rhs.assemble()
        self._solution.assemble()
        initial_solution_norm = float(self._solution.norm())
        self._last_solve["initial_solution_norm"] = initial_solution_norm
        if rhs_norm == 0.0:
            self._owner_constraint_lu_solve_attempts_this_solve = 0
            self._owner_constraint_lu_solve_successes_this_solve = 0
            self._owner_constraint_lu_solve_counts_authoritative = True
            self._last_solve.update(
                ksp_reason=None,
                ksp_status="not_run_zero_rhs",
                owner_constraint_lu_solve_attempts=0,
                owner_constraint_lu_solve_successes=0,
                owner_constraint_lu_solve_counts_authoritative=True,
                constraint_lu_solve_count_scope=(
                    "zero_rhs_no_ksp_no_owner_lu_calls"
                ),
            )
            relative, finite = self._final_residual(rhs_norm)
            zero_trusted_iterate = True
            zero_input_unchanged = True
            if self.modal_solver_policy is not None:
                zero_trusted_iterate = bool(
                    finite
                    and np.all(
                        np.isfinite(
                            np.asarray(
                                self._solution.getArray(readonly=True),
                                dtype=np.complex128,
                            )
                        )
                    )
                    and np.all(
                        np.isfinite(
                            np.asarray(
                                self._residual.getArray(readonly=True),
                                dtype=np.complex128,
                            )
                        )
                    )
                )
                try:
                    zero_input_unchanged = bool(
                        np.asarray(rhs, dtype=np.complex128).tobytes()
                        == self._rhs_input_bytes
                    )
                except Exception:  # noqa: BLE001 - V12 zero path fails closed
                    zero_input_unchanged = False
                zero_trust_records = self._comm.allgather(
                    (zero_trusted_iterate, zero_input_unchanged)
                )
                zero_trusted_iterate = all(
                    record[0] for record in zero_trust_records
                )
                zero_input_unchanged = all(
                    record[1] for record in zero_trust_records
                )
            passed = bool(
                finite
                and relative is None
                and not self._budget_exhausted
                and zero_trusted_iterate
                and zero_input_unchanged
            )
            status = (
                "budget_exhausted"
                if self._budget_exhausted
                else "zero_rhs_exact"
                if passed
                else "untrusted_iterate"
                if not zero_trusted_iterate
                else "modal_rhs_input_modified"
                if not zero_input_unchanged
                else "zero_rhs_failed"
            )
            self._last_solve.update(
                status=status,
                ksp_reason=None,
                ksp_status="not_run_zero_rhs",
                rhs_norm=0.0,
                s_h_rtol=self.rtol,
                solver_matmult_calls=self._solver_matmult_calls,
                total_matmult_calls=self._total_matmult_calls,
                local_constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_local
                ),
                constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_owner
                ),
                local_constraint_lu_solve_attempts=0,
                local_constraint_lu_solve_successes=0,
                owner_constraint_lu_solve_attempts=0,
                owner_constraint_lu_solve_successes=0,
                owner_constraint_lu_solve_counts_authoritative=True,
                constraint_lu_solve_count_scope=(
                    "zero_rhs_no_ksp_no_owner_lu_calls"
                ),
                **(
                    {
                        "trusted_iterate": zero_trusted_iterate,
                        "input_unchanged": zero_input_unchanged,
                        "pc_usable": passed,
                        **(
                            {
                                "normal_return_rejection_reason": (
                                    "V12 exact-zero return lacks a trusted residual/iterate"
                                )
                            }
                            if not zero_trusted_iterate
                            else {}
                        ),
                        **(
                            {
                                "normal_return_rejection_reason": (
                                    "V12 exact-zero return modified its caller RHS"
                                )
                            }
                            if zero_trusted_iterate and not zero_input_unchanged
                            else {}
                        ),
                    }
                    if self.modal_solver_policy is not None
                    else {}
                ),
            )
            if not passed:
                raise RuntimeError(f"Fixed-H6 modal zero-RHS solve failed: {status}")
            return np.zeros(self.modal_count, dtype=np.complex128)

        try:
            self._ksp.solve(self._rhs, self._solution)
        except Exception as exc:
            # Local petsc4py files identify PETSC_ERR_PYTHON but do not promise
            # cross-rank callback-exception synchronization.  Do not start a
            # new MPI collective here after an arbitrary callback exception.
            # Explicit preflight and owner-PC failures use separate protocols.
            try:
                reason = int(self._ksp.getConvergedReason())
            except PETSc.Error:
                reason = None
            try:
                iterations = int(self._ksp.getIterationNumber())
            except PETSc.Error:
                iterations = None
            if self._budget_exhausted:
                status = "budget_exhausted"
                not_evaluated_reason = (
                    "budget_exhausted_before_trusted_KSP_iterate"
                )
                ksp_status = "raised_after_budget_exhaustion"
            elif self._pc_failure_error is not None:
                status = "pc_apply_failed"
                not_evaluated_reason = "PC_failure_no_trusted_KSP_iterate"
                ksp_status = "raised_after_synchronized_pc_failure"
            elif self._mat_preflight_failure is not None:
                status = "mat_preflight_failed"
                not_evaluated_reason = "Mat_preflight_rejected_before_S_H"
                ksp_status = "raised_after_mat_preflight_failure"
            else:
                status = "ksp_callback_failed"
                not_evaluated_reason = "KSP_callback_exception_no_trusted_iterate"
                ksp_status = "raised_local_sync_unverified"
            self._last_solve.update(
                status=status,
                ksp_reason=reason,
                ksp_status=ksp_status,
                error=f"{type(exc).__name__}: {exc}",
                iterations=iterations,
                rhs_norm=rhs_norm,
                solver_matmult_calls=self._solver_matmult_calls,
                total_matmult_calls=self._total_matmult_calls,
                final_residual_evaluated=False,
                final_residual_status="not_evaluated",
                final_residual_not_evaluated_reason=not_evaluated_reason,
                pc_failure=self._pc_failure_error,
                budget_used_solver_matmult_calls=self._solver_matmult_calls,
                budget_used_total_matmult_calls=self._total_matmult_calls,
                local_constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_local
                ),
                constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_owner
                ),
                local_constraint_lu_solve_attempts=self._constraint_lu_solve_attempts,
                local_constraint_lu_solve_successes=self._constraint_lu_solve_successes,
                owner_constraint_lu_solve_attempts=(
                    self._constraint_lu_solve_attempts
                    if self._comm.rank == self._modal_owner
                    else None
                ),
                owner_constraint_lu_solve_successes=(
                    self._constraint_lu_solve_successes
                    if self._comm.rank == self._modal_owner
                    else None
                ),
                owner_constraint_lu_solve_counts_authoritative=False,
                constraint_lu_solve_count_scope=(
                    "owner_value_unavailable_without_post_callback_collective"
                ),
            )
            raise RuntimeError(
                f"Fixed-H6 modal KSP failed: {self._last_solve['error']}"
            ) from exc

        reason = int(self._ksp.getConvergedReason())
        iterations = int(self._ksp.getIterationNumber())
        if self.modal_solver_policy is None:
            states = self._comm.allgather(
                (reason, iterations, self._solver_matmult_calls)
            )
            if len(set(states)) != 1:
                raise RuntimeError("Fixed-H6 modal KSP state differs across ranks")
        else:
            states = self._comm.allgather(
                (
                    reason,
                    iterations,
                    self._solver_matmult_calls,
                    self._mat_preflight_failure is not None,
                    self._modal_action_failure is not None,
                )
            )
            solver_states = [row[:3] for row in states]
            if len(set(solver_states)) != 1:
                raise RuntimeError("Fixed-H6 modal KSP state differs across ranks")
            if any(row[3] or row[4] for row in states):
                self._last_solve.update(
                    status=(
                        "mat_preflight_failed"
                        if any(row[3] for row in states)
                        else "modal_action_failed"
                    ),
                    ksp_reason=reason,
                    ksp_status="returned_after_matmult_or_preflight_failure",
                    iterations=iterations,
                    rhs_norm=rhs_norm,
                    final_residual_evaluated=False,
                    final_residual_status="not_evaluated",
                    final_residual_not_evaluated_reason=(
                        "MatMult_or_preflight_failure_no_approximate_return"
                    ),
                    mat_preflight_failure=self._mat_preflight_failure,
                    modal_action_failure=self._modal_action_failure,
                    pc_usable=False,
                    snapshot_record={
                        "status": "not_saved_matmult_failure_no_trusted_iterate",
                        "reason": (
                            "normal KSP return followed an action/preflight failure"
                        ),
                    },
                )
                raise RuntimeError(
                    "Fixed-H6 modal KSP returned after a MatMult/action failure"
                )
        owner_lu_solve_attempts = int(
            self._comm.bcast(
                self._constraint_lu_solve_attempts
                if self._comm.rank == self._modal_owner
                else None,
                root=self._modal_owner,
            )
        )
        owner_lu_solve_successes = int(
            self._comm.bcast(
                self._constraint_lu_solve_successes
                if self._comm.rank == self._modal_owner
                else None,
                root=self._modal_owner,
            )
        )
        self._owner_constraint_lu_solve_attempts_this_solve = (
            owner_lu_solve_attempts
        )
        self._owner_constraint_lu_solve_successes_this_solve = (
            owner_lu_solve_successes
        )
        self._owner_constraint_lu_solve_counts_authoritative = True
        if self._pc_failure_error is not None:
            status = "budget_exhausted" if self._budget_exhausted else "pc_apply_failed"
            not_evaluated_reason = (
                "budget_exhausted_before_trusted_KSP_iterate"
                if self._budget_exhausted
                else "PC_failure_no_trusted_KSP_iterate"
            )
            self._last_solve.update(
                status=status,
                ksp_reason=reason,
                ksp_status="returned_after_marked_pc_failure",
                iterations=iterations,
                rhs_norm=rhs_norm,
                initial_solution_norm=initial_solution_norm,
                solver_matmult_calls=self._solver_matmult_calls,
                total_matmult_calls=self._total_matmult_calls,
                final_residual_evaluated=False,
                final_residual_status="not_evaluated",
                final_residual_not_evaluated_reason=not_evaluated_reason,
                pc_failure=self._pc_failure_error,
                local_constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_local
                ),
                constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_owner
                ),
                local_constraint_lu_solve_attempts=self._constraint_lu_solve_attempts,
                local_constraint_lu_solve_successes=self._constraint_lu_solve_successes,
                owner_constraint_lu_solve_attempts=owner_lu_solve_attempts,
                owner_constraint_lu_solve_successes=owner_lu_solve_successes,
                owner_constraint_lu_solve_counts_authoritative=True,
                constraint_lu_solve_count_scope=(
                    "owner_authoritative_replicated_report"
                ),
            )
            raise RuntimeError(f"Fixed-H6 modal solve failed: {status}")

        relative, finite = self._final_residual(rhs_norm)
        raw_pass = bool(relative is not None and finite and relative <= self.rtol)
        trusted_iterate = None
        input_unchanged = None
        if self.modal_solver_policy is not None:
            try:
                caller_values_after = np.asarray(rhs, dtype=np.complex128)
                caller_values_bytes_after = caller_values_after.tobytes()
                input_unchanged = bool(
                    self._rhs_input_sha256 is not None
                    and self._rhs_input_bytes is not None
                    and hashlib.sha256(self._rhs_input_bytes).hexdigest()
                    == self._rhs_input_sha256
                    and caller_values_bytes_after == self._rhs_input_bytes
                )
            except Exception:  # noqa: BLE001 - mutation check fails closed
                input_unchanged = False
            local_solution = np.asarray(
                self._solution.getArray(readonly=True), dtype=np.complex128
            )
            local_raw_residual = np.asarray(
                self._residual.getArray(readonly=True), dtype=np.complex128
            )
            local_trusted_iterate = bool(
                np.all(np.isfinite(local_solution))
                and np.all(np.isfinite(local_raw_residual))
                and finite
            )
            trust_records = self._comm.allgather(
                (local_trusted_iterate, input_unchanged)
            )
            trusted_iterate = all(record[0] for record in trust_records)
            input_unchanged = all(record[1] for record in trust_records)
        if self._budget_exhausted:
            status = "budget_exhausted"
        elif reason <= 0:
            status = "ksp_not_converged"
        elif not raw_pass:
            status = "final_residual_failed"
        else:
            status = "converged"
        solve_record = {
            "status": status,
            "ksp_reason": reason,
            "ksp_status": "returned",
            "iterations": iterations,
            "rhs_norm": rhs_norm,
            "initial_solution_norm": initial_solution_norm,
            "s_h_rtol": self.rtol,
            "raw_residual_pass": raw_pass,
            "solver_matmult_calls": self._solver_matmult_calls,
            "total_matmult_calls": self._total_matmult_calls,
            "constraint_lu_factorizations": self._constraint_lu_factorizations_owner,
            "local_constraint_lu_factorizations": self._constraint_lu_factorizations_local,
            "local_constraint_lu_solve_attempts": self._constraint_lu_solve_attempts,
            "local_constraint_lu_solve_successes": self._constraint_lu_solve_successes,
            "owner_constraint_lu_solve_attempts": owner_lu_solve_attempts,
            "owner_constraint_lu_solve_successes": owner_lu_solve_successes,
            "owner_constraint_lu_solve_counts_authoritative": True,
            "constraint_lu_solve_count_scope": "owner_authoritative_replicated_report",
            "budget_used_solver_matmult_calls": self._solver_matmult_calls,
            "budget_used_total_matmult_calls": self._total_matmult_calls,
        }
        if self.modal_solver_policy is not None:
            solve_record.update(
                trusted_iterate=bool(trusted_iterate),
                input_unchanged=bool(input_unchanged),
            )
            if not trusted_iterate:
                if status == "converged":
                    status = "untrusted_iterate"
                solve_record.update(
                    status=status,
                    normal_return_rejection_reason=(
                        "V12 requires a finite trusted iterate and raw residual"
                    ),
                )
            elif not input_unchanged:
                if status == "converged":
                    status = "modal_rhs_input_modified"
                solve_record.update(
                    status=status,
                    normal_return_rejection_reason=(
                        "V12 normal return modified its caller RHS"
                    ),
                )
        self._last_solve.update(solve_record)
        backup_decision = None
        if (
            self.modal_solver_policy is not None
            and _task041_modal_policy_allows_backup(self.modal_solver_policy)
            and self.method == "fixed_h6_modal_gmres_research"
            and status != "converged"
        ):
            backup_decision = _bounded_modal_backup_eligibility(
                policy=self.modal_solver_policy,
                reason=reason,
                iterations=iterations,
                raw_relative_residual=relative,
                raw_residual_pass=raw_pass,
                trusted_iterate=bool(trusted_iterate),
                input_unchanged=bool(input_unchanged),
                budget_exhausted=self._budget_exhausted,
                final_residual_evaluated=(
                    self._last_solve.get("final_residual_evaluated") is True
                ),
                mat_preflight_failure=self._mat_preflight_failure,
                modal_action_failure=self._modal_action_failure,
                pc_failure=self._pc_failure_error,
            )
            self._last_solve["backup_eligibility"] = backup_decision
            if backup_decision["eligible"]:
                status = "PRIMARY_MODAL_TARGET_NOT_MET_BACKUP_ELIGIBLE"
                self._last_solve.update(
                    status=status,
                    pc_usable=False,
                    backup_switch_requested=True,
                    backup_switch_actual=False,
                )
        approximate_decision = None
        if (
            self.modal_solver_policy is not None
            and status != "converged"
            and not (
                isinstance(backup_decision, Mapping)
                and backup_decision.get("eligible") is True
            )
        ):
            approximate_decision = _bounded_modal_return_eligibility(
                policy=self.modal_solver_policy,
                reason=reason,
                iterations=iterations,
                raw_relative_residual=relative,
                raw_residual_pass=raw_pass,
                trusted_iterate=trusted_iterate,
                input_unchanged=input_unchanged,
                budget_exhausted=self._budget_exhausted,
                mat_preflight_failure=self._mat_preflight_failure,
                modal_action_failure=self._modal_action_failure,
                pc_failure=self._pc_failure_error,
            )
            self._last_solve["approximate_return_decision"] = (
                approximate_decision
            )
            if approximate_decision["pc_usable"]:
                status = "INNER_TARGET_NOT_MET_APPROX_RETURN"
                self._last_solve.update(
                    status=status,
                    pc_usable=True,
                    approximate_return=True,
                    raw_residual_pass=False,
                )
        if self.modal_solver_policy is not None:
            self._last_solve["pc_usable"] = bool(
                status == "converged"
                and trusted_iterate is True
                and input_unchanged is True
                or (
                    isinstance(approximate_decision, Mapping)
                    and approximate_decision.get("pc_usable") is True
                )
            )
        snapshot_kinds: list[str] = []
        if self.modal_solver_policy is not None:
            if not raw_pass and not self._first_unmet_snapshot_saved:
                snapshot_kinds.append("first_unmet_target")
            elif (
                trusted_iterate
                and status == "converged"
                and raw_pass
                and rhs_norm > 0.0
                and not self._success_control_snapshot_saved
            ):
                snapshot_kinds.append("first_success_control")
            terminal_normal_reject = bool(
                status not in {
                    "converged",
                    "INNER_TARGET_NOT_MET_APPROX_RETURN",
                    "PRIMARY_MODAL_TARGET_NOT_MET_BACKUP_ELIGIBLE",
                }
                and trusted_iterate is True
                and input_unchanged is True
                and not self._terminal_normal_reject_snapshot_saved
            )
            if terminal_normal_reject:
                snapshot_kinds.append("terminal_normal_reject")
        if self.modal_solver_policy is not None:
            pc_usable = bool(self._last_solve.get("pc_usable") is True)
            normal_return_record = (
                int(reason),
                int(iterations),
                status,
                relative,
                bool(raw_pass),
                bool(trusted_iterate),
                bool(input_unchanged),
                pc_usable,
                tuple(snapshot_kinds),
                bool(
                    isinstance(backup_decision, Mapping)
                    and backup_decision.get("eligible") is True
                ),
            )
            normal_return_records = self._comm.allgather(normal_return_record)
            if any(
                record != normal_return_records[0]
                for record in normal_return_records[1:]
            ):
                raise RuntimeError(
                    "V12 modal normal-return decision differs across ranks"
                )
        if snapshot_kinds:
            snapshot_records = {}
            for snapshot_kind in snapshot_kinds:
                snapshot_record = self._persist_normal_return_snapshot(
                    kind=snapshot_kind,
                    reason=reason,
                    iterations=iterations,
                    relative=relative,
                    raw_residual_pass=raw_pass,
                    rhs_norm=rhs_norm,
                )
                snapshot_records[snapshot_kind] = snapshot_record
                if snapshot_kind == "first_unmet_target":
                    self._first_unmet_snapshot_saved = True
                elif snapshot_kind == "first_success_control":
                    self._success_control_snapshot_saved = True
                elif snapshot_kind == "terminal_normal_reject":
                    self._terminal_normal_reject_snapshot_saved = True
            preferred_snapshot_kind = (
                "terminal_normal_reject"
                if "terminal_normal_reject" in snapshot_records
                else next(iter(snapshot_records))
            )
            self._last_solve["snapshot_record"] = snapshot_records[
                preferred_snapshot_kind
            ]
            self._last_solve["snapshot_records"] = snapshot_records
        elif self.modal_solver_policy is not None and not trusted_iterate:
            self._last_solve["snapshot_record"] = {
                "status": "not_saved_untrusted_iterate_or_raw_residual"
            }
        if status != "converged":
            if (
                status == "PRIMARY_MODAL_TARGET_NOT_MET_BACKUP_ELIGIBLE"
                and isinstance(self._last_solve, dict)
            ):
                self._last_solve["normal_primary_return_completed"] = True
                self._last_solve["pc_usable"] = False
                raise _ModalNormalReturnBackupEligible(self._last_solve)
            if status == "INNER_TARGET_NOT_MET_APPROX_RETURN":
                local_solution = (
                    np.asarray(
                        self._solution.getArray(readonly=True),
                        dtype=np.complex128,
                    ).copy()
                    if self._comm.rank == self._modal_owner
                    else None
                )
                return np.asarray(
                    self._comm.bcast(local_solution, root=self._modal_owner),
                    dtype=np.complex128,
                )
            raise RuntimeError(f"Fixed-H6 modal solve did not converge: {status}")
        local_solution = (
            np.asarray(self._solution.getArray(readonly=True), dtype=np.complex128).copy()
            if self._comm.rank == self._modal_owner
            else None
        )
        result = np.asarray(
            self._comm.bcast(local_solution, root=self._modal_owner),
            dtype=np.complex128,
        )
        return result

    @property
    def diagnostics(self) -> dict[str, Any]:
        last_solve = self._last_solve
        modal_action = self._modal_action
        lu_solve_scope = (
            "rank_local_counter; owner aggregate unavailable before a completed solve"
            if last_solve is None
            else last_solve.get(
                "constraint_lu_solve_count_scope",
                "rank_local_attempt/success counters; no owner aggregate recorded",
            )
        )
        owner_lu_cumulative_complete = bool(
            self._cumulative_owner_constraint_lu_solve_counts_complete
        )
        result = {
            "method": self.method,
            "operator": self._action_operator,
            "operator_fixed_condition": (
                "side adapters, H6 runtime matrices, condensed maps, and modal "
                "coupling remain frozen for the modal solver lifetime"
            ),
            "rtol": self.rtol,
            "restart": self.max_it,
            "max_it": self.max_it,
            "modal_solver_policy": (
                None
                if self.modal_solver_policy is None
                else dict(self.modal_solver_policy)
            ),
            "solver_matmult_limit": self.solver_matmult_limit,
            "total_matmult_limit_including_final": self.total_matmult_limit,
            "modal_owner": self._modal_owner,
            "rank": int(self._comm.rank),
            "rank_count": int(self._comm.size),
            "solver_matmult_calls": self._solver_matmult_calls,
            "total_matmult_calls": self._total_matmult_calls,
            "solve_count": self._solve_count,
            "s_evaluation_count": self._cumulative_total_matmult_calls,
            "not_converged_count": self._not_converged_count,
            "cumulative_solver_matmult_calls": (
                self._cumulative_solver_matmult_calls
            ),
            "cumulative_total_matmult_calls": (
                self._cumulative_total_matmult_calls
            ),
            "cumulative_constraint_lu_solve_attempts": (
                self._cumulative_constraint_lu_solve_attempts
            ),
            "cumulative_constraint_lu_solve_successes": (
                self._cumulative_constraint_lu_solve_successes
            ),
            "cumulative_constraint_lu_solve_count_scope": (
                "rank_local_cumulative; do_not_sum_across_ranks"
            ),
            "cumulative_owner_constraint_lu_solve_attempts": (
                self._cumulative_owner_constraint_lu_solve_attempts
                if owner_lu_cumulative_complete
                else None
            ),
            "cumulative_owner_constraint_lu_solve_successes": (
                self._cumulative_owner_constraint_lu_solve_successes
                if owner_lu_cumulative_complete
                else None
            ),
            "cumulative_owner_constraint_lu_solve_status": (
                "complete"
                if owner_lu_cumulative_complete
                else "unknown_missing_per_solve_owner_broadcast"
            ),
            "cumulative_owner_constraint_lu_solve_count_scope": (
                "owner_authoritative_per_solve_broadcasts; replicated; do_not_sum_across_ranks"
            ),
            "modal_schur_materialized": False,
            "modal_schur_column_count": 0,
            "modal_schur_condition": "not_measured",
            "modal_constraint_local_bytes": self.modal_constraint_local_bytes,
            "modal_constraint_matvec_calls_total": (
                self._modal_constraint_matvec_calls_at_destroy
                if modal_action is None
                else int(modal_action._modal_constraint_matvec_count)
            ),
            "modal_constraint_matvec_count_scope": (
                "rank-local action counter; do_not_sum_across_ranks"
            ),
            "modal_constraint_condition": float(self.constraint_condition),
            "constraint_lu_factorizations": int(
                self._constraint_lu_factorizations_owner
            ),
            "constraint_lu_owner_rank": int(self._modal_owner),
            "blocked_matmult_attempts": self._blocked_matmult_attempts,
            "local_constraint_lu_factorizations": self._constraint_lu_factorizations_local,
            "owner_constraint_lu_factorizations": self._constraint_lu_factorizations_owner,
            "local_constraint_lu_solve_attempts": self._constraint_lu_solve_attempts,
            "local_constraint_lu_solve_successes": self._constraint_lu_solve_successes,
            "owner_constraint_lu_solve_attempts": (
                None
                if self._last_solve is None
                else self._last_solve.get("owner_constraint_lu_solve_attempts")
            ),
            "owner_constraint_lu_solve_successes": (
                None
                if self._last_solve is None
                else self._last_solve.get("owner_constraint_lu_solve_successes")
            ),
            "constraint_lu_solve_count_scope": lu_solve_scope,
            "constraint_lu_factorizations_scope": "rank_local_and_owner_authoritative",
            "pc_failure": self._pc_failure_error,
            "mat_preflight_failure": self._mat_preflight_failure,
            "budget_exhausted": self._budget_exhausted,
            "last_solve": None if last_solve is None else dict(last_solve),
            "first_unmet_snapshot_saved": self._first_unmet_snapshot_saved,
            "success_control_snapshot_saved": self._success_control_snapshot_saved,
            "terminal_normal_reject_snapshot_saved": (
                self._terminal_normal_reject_snapshot_saved
            ),
            "backup_switches": int(self._backup_switches),
            "backup_switch_audit": dict(self._backup_switch_audit),
            "post_backup_stop_record": (
                None
                if self._post_backup_stop_record is None
                else dict(self._post_backup_stop_record)
            ),
            "post_backup_capacity_stop_pending": (
                None
                if self._post_backup_capacity_stop_pending is None
                else dict(self._post_backup_capacity_stop_pending)
            ),
            "side_restart64_trial_state": (
                None
                if self._side_restart64_trial_state is None
                else dict(self._side_restart64_trial_state)
            ),
            "outer_stagnation_checkpoints": [
                dict(row) for row in self._outer_window_points
            ],
            "outer_stagnation_completed_windows": [
                dict(window) for window in self._outer_completed_windows
            ],
            "destroyed": self._destroyed,
        }
        if self.modal_solver_policy is not None:
            result["scalar_history"] = list(self._iteration_scalar_history)
        result["requested_feedback_method"] = self.feedback_method
        result["actual_feedback_method"] = self.actual_feedback_method
        result["method_history"] = list(self._method_history)
        if self.feedback_method is not None:
            result["feedback_method"] = self.feedback_method
            result["modal_feedback_method"] = self.feedback_method
        return result

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        ksp, self._ksp = self._ksp, None
        matrix, self._matrix = self._matrix, None
        for vector_name in ("_residual", "_image", "_solution", "_rhs"):
            vector = getattr(self, vector_name)
            if vector is not None:
                vector.destroy()
                setattr(self, vector_name, None)
        if ksp is not None:
            ksp.destroy()
        if matrix is not None:
            matrix.destroy()
        if self._modal_action is not None:
            self._modal_constraint_matvec_calls_at_destroy = int(
                self._modal_action._modal_constraint_matvec_count
            )
            self._modal_action.destroy()
            self._modal_action = None
        # Side adapters and their FixedH6/layout objects are borrowed.
        self._bottom_action = None
        self._top_action = None
        self._constraint_lu = self._constraint_pivots = None


class _FixedH6ModalGmresResearchBundle:
    """Own one fixed-H6 modal solver and its two borrowed-side adapters."""

    modal_schur = None
    requires_right_fgmres = True

    def __init__(
        self,
        solver: _FixedH6ModalKrylovSystem,
        bottom_action: Any,
        top_action: Any,
        *,
        coupling: HybridInternalModeCoupling | None = None,
        backup_side_inverses: tuple[Any, Any] | None = None,
        marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._solver: _FixedH6ModalKrylovSystem | None = solver
        self._side_actions: tuple[Any, Any] = (bottom_action, top_action)
        self._coupling = coupling
        self._backup_side_inverses = backup_side_inverses
        self._backup_p4_factor_handles: tuple[Any, ...] = (
            tuple(
                getattr(inverse, "_p4_factor", None)
                for inverse in backup_side_inverses
            )
            if isinstance(backup_side_inverses, tuple)
            else ()
        )
        self._marker_callback = marker_callback
        self.modal_count = int(solver.modal_count)
        self.mode_count = int(solver.mode_count)
        self.modal_constraint_local_bytes = int(solver.modal_constraint_local_bytes)
        self._destroyed = False
        self._backup_switch_in_progress = False
        if _task041_modal_policy_allows_backup(solver.modal_solver_policy) and (
            coupling is None
            or not isinstance(backup_side_inverses, tuple)
            or len(backup_side_inverses) != 2
            or solver.method != "fixed_h6_modal_gmres_research"
            or solver.feedback_method is not None
        ):
            raise ValueError(
                "the V12 one-time backup requires a pure H6 primary and both live side inverses"
            )
        if isinstance(backup_side_inverses, tuple) and len(backup_side_inverses) == 2:
            states = tuple(
                getattr(inverse, "_side_restart64_trial_state", None)
                for inverse in backup_side_inverses
            )
            gates = tuple(
                getattr(inverse, "_side_restart64_memory_gate", None)
                for inverse in backup_side_inverses
            )
            if any(state is not None for state in states):
                if (
                    states[0] is None
                    or states[0] is not states[1]
                    or not callable(gates[0])
                    or gates[0] is not gates[1]
                    or any(
                        getattr(inverse, "_side_system", None) is None
                        for inverse in backup_side_inverses
                    )
                    or tuple(
                        str(inverse._side_system.side)
                        for inverse in backup_side_inverses
                    )
                    != ("bottom", "top")
                ):
                    raise ValueError(
                        "the one-time side trial requires one shared state/gate and both live sides"
                    )
                solver._side_restart64_trial_state = states[0]

    @property
    def modal_constraint(self) -> np.ndarray | None:
        if self._destroyed or self._solver is None:
            return None
        return self._solver.modal_constraint

    @property
    def constraint_condition(self) -> float:
        if self._solver is None:
            return float("nan")
        return float(self._solver.constraint_condition)

    @property
    def diagnostics(self) -> dict[str, Any]:
        solver = {} if self._solver is None else self._solver.diagnostics
        actions = {
            side: dict(action.audit)
            for side, action in zip(
                ("bottom", "top"), self._side_actions, strict=True
            )
        }
        method = solver.get("method", "fixed_h6_modal_gmres_research")
        if method == "fixed_h6_modal_gmres_research":
            action_fields = {
                "fixed_h6_actions": actions,
                "fixed_h6_action_count_scope": (
                    "per-rank replicated; do_not_sum_across_ranks"
                ),
                "fixed_h6_modal_apply_calls": {
                    side: int(action["apply_count"])
                    for side, action in actions.items()
                },
                "fixed_h6_modal_matrix_mult_calls": {
                    side: int(action["matrix_mult_count"])
                    for side, action in actions.items()
                },
            }
        else:
            action_fields = {
                "fixed_physical_balh_actions": actions,
                "modal_feedback_action_count_scope": (
                    "per-rank replicated; do_not_sum_across_ranks"
                ),
                "modal_feedback_apply_calls": {
                    side: int(action["apply_count"])
                    for side, action in actions.items()
                },
                "modal_feedback_matrix_mult_calls": {
                    side: int(action["matrix_mult_count"])
                    for side, action in actions.items()
                },
            }
        return {
            **solver,
            "method": method,
            **action_fields,
            "modal_schur_materialized": False,
            "modal_schur_column_count": 0,
            "modal_schur_condition": "not_measured",
            "destroyed": self._destroyed,
        }

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed or self._solver is None:
            raise RuntimeError("Fixed-H6 modal research bundle was destroyed")
        solver = self._solver
        if self._backup_switch_in_progress:
            raise RuntimeError("modal backup transition is not reentrant")
        if solver._backup_pending:
            trigger = dict(solver._backup_switch_audit.get("trigger") or {})
            self._switch_to_fixed_physical_balh(trigger=trigger)
        try:
            result = solver.solve(rhs)
        except _ModalNormalReturnBackupEligible as exc:
            if not _task041_modal_policy_allows_backup(solver.modal_solver_policy):
                raise
            primary_normal_return = _collective_modal_backup_primary_record(
                solver._comm, solver.diagnostics
            )
            exception_eligibility = exc.record.get("backup_eligibility")
            if (
                not isinstance(exception_eligibility, Mapping)
                or exception_eligibility.get("eligible") is not True
                or dict(exception_eligibility)
                != dict(primary_normal_return["backup_eligibility"])
            ):
                raise RuntimeError(
                    "primary modal exception and finalized normal-return eligibility differ"
                ) from exc
            trigger = {
                "kind": "normal_trusted_primary_return_eta_above_0.1",
                "safe_boundary": (
                    "after_primary_modal_KSP_return_before_backup_modal_KSP_entry"
                ),
                "primary_normal_return": primary_normal_return,
            }
            solver._backup_switch_audit = {
                "requested": True,
                "allowed": False,
                "actual": False,
                "switch_count": int(solver._backup_switches),
                "trigger": trigger,
                "status": "backup_candidate_gate_pending",
                "method_history": list(solver._method_history),
            }
            self._switch_to_fixed_physical_balh(trigger=trigger)
            result = solver.solve(rhs)
        self._resolve_pending_side_restart_trial()
        return result

    def _resolve_pending_side_restart_trial(self) -> None:
        """Run the one side trial only after a complete modal call has returned."""

        solver = self._solver
        if solver is None or solver._solve_in_progress:
            raise RuntimeError("side restart trial reached an active modal KSP boundary")
        state = solver._side_restart64_trial_state
        if (
            not isinstance(state, dict)
            or state.get("resolved") is True
            or state.get("pending") is not True
        ):
            return
        status = state.get("status")
        if status == "candidate_captured":
            side = state.get("candidate_side")
            matches = [
                inverse
                for inverse in (self._backup_side_inverses or ())
                if str(getattr(getattr(inverse, "_side_system", None), "side", ""))
                == side
            ]
            if len(matches) != 1:
                raise RuntimeError("captured side RHS does not identify one live side inverse")
            record = matches[0].run_side_restart64_trial()
        elif status == "capacity_gate_refused":
            refusal = state.get("result")
            gate = refusal.get("gate") if isinstance(refusal, Mapping) else None
            if not isinstance(gate, Mapping) or gate.get("pass") is not False:
                raise RuntimeError("side RHS capacity refusal has no explicit failed gate")
            record = dict(refusal)
        else:
            return
        solver.resolve_side_restart64_trial(record)

    def observe_outer_true_residual(
        self,
        residual_row: Mapping[str, Any],
        *,
        gate_threshold: float | None = None,
    ) -> dict[str, Any] | None:
        if self._destroyed or self._solver is None:
            raise RuntimeError("Fixed-H6 modal research bundle was destroyed")
        observation = self._solver.observe_outer_true_residual(
            residual_row, gate_threshold=gate_threshold
        )
        if observation is not None and self._marker_callback is not None:
            self._marker_callback(
                "modal_backup_progress_checkpoint",
                {
                    "side": "both",
                    "stage": "outer_true_residual_stagnation_policy",
                    "observation": observation,
                    "backup_pending": bool(self._solver._backup_pending),
                    "switch_count": int(self._solver._backup_switches),
                },
            )
        return observation

    def record_outer_terminal(self, decision: Mapping[str, Any]) -> None:
        if self._destroyed or self._solver is None:
            raise RuntimeError("Fixed-H6 modal research bundle was destroyed")
        self._solver.record_outer_terminal(decision)

    def post_backup_stop_decision(self) -> dict[str, Any] | None:
        if self._destroyed or self._solver is None:
            raise RuntimeError("Fixed-H6 modal research bundle was destroyed")
        return self._solver.post_backup_stop_decision()

    def _switch_to_fixed_physical_balh(
        self, *, trigger: Mapping[str, Any]
    ) -> bool:
        """Install one borrowed physical action after a synchronized safety gate."""

        solver = self._solver
        if solver is None or self._destroyed:
            raise RuntimeError("cannot switch a destroyed modal bundle")
        if not _task041_modal_policy_allows_backup(solver.modal_solver_policy):
            raise RuntimeError("sealed policy does not allow the physical backup")
        if self._backup_switch_in_progress:
            raise RuntimeError("modal backup transition is not reentrant")
        if solver._backup_switches != 0 or solver.method != "fixed_h6_modal_gmres_research":
            raise RuntimeError("the one-time backup is already consumed or out of order")
        if solver._solve_in_progress:
            raise RuntimeError("cannot switch feedback while modal KSP is active")
        if self._coupling is None or self._backup_side_inverses is None:
            raise RuntimeError("the sealed backup lacks its original side factors")
        self._backup_switch_in_progress = True
        candidate_actions: list[Any] = []
        candidate_modal_action: HybridActionModalSchurApply | None = None
        previous = None
        committed = False
        primary_diagnostics = solver.diagnostics
        primary_normal_return = trigger.get("primary_normal_return")
        if not isinstance(primary_normal_return, Mapping):
            primary_normal_return = _collective_modal_backup_primary_record(
                solver._comm,
                primary_diagnostics,
                require_backup_eligible=False,
            )
        local_error = None
        try:
            audit_before_switch = solver._backup_switch_audit
            if not isinstance(trigger, Mapping):
                raise TypeError("modal backup trigger is not a mapping")
            trigger_kind = trigger.get("kind")
            if trigger_kind == "normal_trusted_primary_return_eta_above_0.1":
                if (
                    audit_before_switch.get("status")
                    != "backup_candidate_gate_pending"
                    or audit_before_switch.get("trigger") != dict(trigger)
                    or trigger.get("safe_boundary")
                    != "after_primary_modal_KSP_return_before_backup_modal_KSP_entry"
                    or not isinstance(primary_normal_return, Mapping)
                ):
                    raise ValueError(
                        "normal-return backup trigger differs from the completed primary record"
                    )
            elif trigger.get("status") == "two_consecutive_outer_windows_stalled":
                if (
                    not solver._backup_pending
                    or audit_before_switch.get("status")
                    != "backup_pending_next_safe_outer_PC_entry"
                    or audit_before_switch.get("trigger") != dict(trigger)
                    or trigger.get("next_safe_boundary")
                    != "next_outer_PC_modal_solve_before_KSP_entry"
                ):
                    raise ValueError(
                        "outer-stagnation switch is not at the sealed next-PC safe boundary"
                    )
            else:
                raise ValueError("modal backup trigger kind is not registered")

            from .physical_balanced_side_inverse import (
                FixedH6ActiveTraceAction,
                SideBalancedInverse,
            )

            if (
                len(self._side_actions) != 2
                or len(self._backup_side_inverses) != 2
                or len(self._backup_p4_factor_handles) != 2
            ):
                raise ValueError("both original side actions and factors must remain live")
            for side_index, (inverse, old_action) in enumerate(
                zip(self._backup_side_inverses, self._side_actions, strict=True)
            ):
                if (
                    not isinstance(inverse, SideBalancedInverse)
                    or inverse._destroyed
                    or inverse._p4_factor is None
                    or inverse._p4_factor
                    is not self._backup_p4_factor_handles[side_index]
                    or not isinstance(old_action, FixedH6ActiveTraceAction)
                    or old_action.method != "fixed_h6_active_trace"
                    or old_action._destroyed
                    or old_action._operator is not inverse._operator
                    or old_action._condensed is not inverse._condensed
                    or old_action._h6 is not inverse._h6
                ):
                    raise ValueError(
                        "the backup source is not the same live side inverse and P4 factor"
                    )

            transition_signature = json.dumps(
                {
                    "trigger": dict(trigger),
                    "policy_id": solver.modal_solver_policy.get("policy_id"),
                    "primary_method": solver.method,
                    "primary_method_history": list(solver._method_history),
                    "backup_switches": int(solver._backup_switches),
                    "backup_pending": bool(solver._backup_pending),
                    "primary_transition_status": audit_before_switch.get("status"),
                    "same_live_side_factor_handles_verified": True,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except Exception as exc:  # noqa: BLE001 - agree before any action creation
            local_error = f"{type(exc).__name__}: {exc}"
            transition_signature = None
        transition_records = solver._comm.allgather(
            (local_error, transition_signature)
        )
        transition_errors = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(transition_records)
            if error is not None
        ]
        transition_signatures = [
            signature
            for error, signature in transition_records
            if error is None
        ]
        if transition_signatures and any(
            signature != transition_signatures[0]
            for signature in transition_signatures[1:]
        ):
            transition_errors.append("modal backup transition differs across ranks")
        if transition_errors:
            reason = (
                "modal backup transition rejected before candidate construction; "
                + "; ".join(transition_errors)
            )
            self._backup_switch_in_progress = False
            solver.reject_feedback_candidate(trigger=trigger, reason=reason)
            raise RuntimeError(reason)

        local_error = None
        same_live_side_factor_handles_verified = True
        try:
            from .physical_balanced_side_inverse import SideBalancedInverse

            try:
                for inverse in self._backup_side_inverses:
                    if not isinstance(inverse, SideBalancedInverse):
                        raise TypeError("backup source is not the live SideBalancedInverse")
                    candidate_actions.append(
                        inverse.create_fixed_physical_balh_active_trace_action()
                    )
            except Exception as exc:  # noqa: BLE001 - agree before next collective
                local_error = f"{type(exc).__name__}: {exc}"
            action_records = solver._comm.allgather(local_error)
            action_errors = [
                f"rank {rank}: {error}"
                for rank, error in enumerate(action_records)
                if error is not None
            ]
            if action_errors:
                raise RuntimeError(
                    "physical backup adapter creation failed; "
                    + "; ".join(action_errors)
                )

            local_error = None
            try:
                candidate_modal_action = HybridActionModalSchurApply(
                    self._coupling, candidate_actions[0], candidate_actions[1]
                )
            except Exception as exc:  # noqa: BLE001 - agree before install collective
                local_error = f"{type(exc).__name__}: {exc}"
            modal_records = solver._comm.allgather(local_error)
            modal_errors = [
                f"rank {rank}: {error}"
                for rank, error in enumerate(modal_records)
                if error is not None
            ]
            if modal_errors:
                raise RuntimeError(
                    "physical backup modal action creation failed; "
                    + "; ".join(modal_errors)
                )

            previous = solver.install_feedback_candidate(
                candidate_modal_action, candidate_actions[0], candidate_actions[1]
            )
            gate = _check_fixed_h6_modal_feedback_repeat_linearity(
                solver,
                original_side_actions={
                    "bottom": self._backup_side_inverses[0],
                    "top": self._backup_side_inverses[1],
                },
                original_side_apply_counts_before={
                    "bottom": _action_diagnostics(self._backup_side_inverses[0]).get(
                        "apply_count"
                    ),
                    "top": _action_diagnostics(self._backup_side_inverses[1]).get(
                        "apply_count"
                    ),
                },
                marker_callback=self._marker_callback,
            )
            solver.commit_feedback_candidate(
                trigger=trigger,
                gate=gate,
                primary_diagnostics={
                    "method": primary_diagnostics.get("method"),
                    "solve_count": primary_diagnostics.get("solve_count"),
                    "cumulative_solver_matmult_calls": primary_diagnostics.get(
                        "cumulative_solver_matmult_calls"
                    ),
                    "cumulative_total_matmult_calls": primary_diagnostics.get(
                        "cumulative_total_matmult_calls"
                    ),
                    "scalar_history": list(
                        primary_diagnostics.get("scalar_history") or []
                    ),
                    "primary_solver_record": dict(primary_normal_return),
                },
                same_live_side_factor_handles_verified=(
                    same_live_side_factor_handles_verified
                ),
            )
            committed = True
            _old_modal_action, old_bottom_action, old_top_action = previous[:3]
            self._side_actions = (candidate_actions[0], candidate_actions[1])
            candidate_actions = []
            candidate_modal_action = None
            solver.destroy_previous_feedback_candidate(previous)
            old_cleanup_error = None
            for action in (old_top_action, old_bottom_action):
                try:
                    action.destroy()
                except Exception as exc:  # noqa: BLE001 - try to release both adapters
                    if old_cleanup_error is None:
                        old_cleanup_error = f"{type(exc).__name__}: {exc}"
            cleanup_errors = solver._comm.allgather(old_cleanup_error)
            failures = [
                f"rank {rank}: {error}"
                for rank, error in enumerate(cleanup_errors)
                if error is not None
            ]
            if failures:
                raise RuntimeError(
                    "primary modal adapter cleanup failed after backup commit; "
                    + "; ".join(failures)
                )
            if self._marker_callback is not None:
                self._marker_callback(
                    "modal_backup_switch_ready",
                    {
                        "side": "both",
                        "stage": "primary_to_fixed_physical_balh",
                        "trigger": dict(trigger),
                        "backup_switch_audit": dict(solver._backup_switch_audit),
                        "same_live_side_factors": True,
                    },
                )
            return True
        except BaseException as exc:
            cleanup_errors: list[str] = []
            if not committed and previous is not None and solver._backup_switches == 0:
                try:
                    solver.rollback_feedback_candidate(previous)
                except Exception as cleanup_exc:  # noqa: BLE001 - retain rollback failure
                    cleanup_errors.append(
                        f"rollback={type(cleanup_exc).__name__}: {cleanup_exc}"
                    )
            if not committed and candidate_modal_action is not None:
                try:
                    candidate_modal_action.destroy()
                except Exception as cleanup_exc:  # noqa: BLE001 - preserve transition cause
                    cleanup_errors.append(
                        f"candidate_modal_destroy={type(cleanup_exc).__name__}: "
                        f"{cleanup_exc}"
                    )
            for action in (reversed(candidate_actions) if not committed else ()):
                try:
                    action.destroy()
                except Exception as cleanup_exc:  # noqa: BLE001 - preserve transition cause
                    cleanup_errors.append(
                        f"candidate_action_destroy={type(cleanup_exc).__name__}: "
                        f"{cleanup_exc}"
                    )
            if not committed:
                reason = f"{type(exc).__name__}: {exc}"
                if cleanup_errors:
                    reason += "; " + "; ".join(cleanup_errors)
                solver.reject_feedback_candidate(trigger=trigger, reason=reason)
            raise
        finally:
            self._backup_switch_in_progress = False

    def set_outer_pc_apply_index(self, index: int) -> None:
        if self._destroyed or self._solver is None:
            raise RuntimeError("Fixed-H6 modal research bundle was destroyed")
        self._solver.set_outer_pc_apply_index(index)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        error: Exception | None = None
        # Keep the destroyed solver's bounded scalar diagnostics readable to
        # the caller's existing exception/failure-evidence boundary.
        solver = self._solver
        if solver is not None:
            try:
                solver.destroy()
            except Exception as exc:  # noqa: BLE001 - release owned adapters below
                error = exc
        for action in reversed(self._side_actions):
            try:
                action.destroy()
            except Exception as exc:  # noqa: BLE001 - try both owned adapters
                if error is None:
                    error = exc
        if error is not None:
            raise error


def _task041_v12_capacity_gate_has_byte_admission(
    gate: Any, *, phase: str, restart: int
) -> bool:
    """Check the compact fields needed to trust a fresh restart workspace pass."""

    if (
        not isinstance(gate, Mapping)
        or gate.get("schema") != "task041.v12.side_restart_memory_gate.v1"
        or gate.get("pass") is not True
        or gate.get("status") != "admitted"
        or gate.get("phase") != phase
        or gate.get("restart") != restart
        or phase not in {"allocate_restart64", "restore_restart32"}
    ):
        return False
    fresh = gate.get("fresh_B_bytes")
    delta = gate.get("delta_bytes")
    reserve = gate.get("W_policy_reserve_bytes")
    cap = gate.get("cap_bytes")
    screened = gate.get("screened_B_plus_delta_plus_W_bytes")
    floor = gate.get("floor_bytes")
    if (
        any(type(value) is not int or value < 0 for value in (fresh, delta, reserve, cap, screened, floor))
        or cap != 85_899_345_920
        or reserve != 8_589_934_592
        or floor != 412_316_860_416
        or delta <= 0
        or screened != fresh + delta + reserve
        or screened > cap
    ):
        return False
    authority = gate.get("authority")
    if authority != (
        "fresh max(process-tree RSS,cgroup memory.current) bound to the explicit per-rank "
        "phase object inventory; destroyed workspaces receive no credit except as reflected in this sample"
    ):
        return False
    resource = gate.get("resource")
    supervisor = gate.get("supervisor_sample")
    evidence = gate.get("external_headroom_byte_evidence")
    if not all(isinstance(value, Mapping) for value in (resource, supervisor, evidence)):
        return False
    if (
        resource.get("B_bytes") != fresh
        or evidence.get("required_bytes") != delta + reserve
        or evidence.get("shortages") != []
        or evidence.get("insufficient_or_unknown_reasons") != []
        or supervisor.get("sample_role") != "phase_running"
        or supervisor.get("phase") != "public_command"
        or type(supervisor.get("sample_root_pid")) is not int
        or not isinstance(supervisor.get("invocation_id"), str)
        or not isinstance(supervisor.get("source_sha"), str)
        or not isinstance(supervisor.get("unit"), str)
    ):
        return False
    expected_lifecycle = {
        "allocate_restart64": (
            "restart32_ksp_destroyed_plus_candidate_rhs_live_plus_full_new_restart64_workspace"
        ),
        "restore_restart32": (
            "restart64_ksp_and_candidate_rhs_destroyed_plus_full_new_restart32_workspace"
        ),
    }[phase]
    rows = gate.get("rank_layout")
    if not isinstance(rows, list) or len(rows) != 8:
        return False
    for rank, row in enumerate(rows):
        if (
            not isinstance(row, Mapping)
            or row.get("rank") != rank
            or row.get("phase") != phase
            or row.get("restart") != restart
            or row.get("workspace_lifecycle") != expected_lifecycle
            or row.get("existing_restart32_ksp_live") is not False
            or row.get("restart64_trial_ksp_live") is not False
            or row.get("candidate_rhs_live") is not (phase == "allocate_restart64")
            or not isinstance(row.get("rhs_local_sha256"), str)
            or len(row["rhs_local_sha256"]) != 64
        ):
            return False
    return True


def _task041_v12_nonselected_restart64_trial_matches(
    record: Any, *, rank_count: int
) -> bool:
    """Validate one same-RHS restart64 comparison before restore refusal."""

    residual = (
        record.get("restart64_original_D_residual")
        if isinstance(record, Mapping)
        else None
    )
    candidate = record.get("candidate_rhs_binding") if isinstance(record, Mapping) else None
    rank_rows = record.get("restart64_rank_records") if isinstance(record, Mapping) else None
    eta32 = record.get("restart32_relative_residual") if isinstance(record, Mapping) else None
    eta64 = record.get("restart64_relative_residual") if isinstance(record, Mapping) else None
    reason = record.get("restart64_reason") if isinstance(record, Mapping) else None
    iterations = record.get("restart64_iterations") if isinstance(record, Mapping) else None
    selection = (
        record.get("selection_evidence") if isinstance(record, Mapping) else None
    )
    if (
        not isinstance(record, Mapping)
        or record.get("status") != "capacity_gate_refused_restart32_restore"
        or record.get("restart64_trial_selected_restart") != 32
        or record.get("selected_restart") is not None
        or record.get("same_p4_factor_handle_all_ranks") is not True
        or not isinstance(selection, Mapping)
        or selection.get("eligible_for_64") is not False
        or not isinstance(eta32, (int, float))
        or isinstance(eta32, bool)
        or not math.isfinite(float(eta32))
        or float(eta32) < 0.0
        or not isinstance(eta64, (int, float))
        or isinstance(eta64, bool)
        or not math.isfinite(float(eta64))
        or float(eta64) < 0.0
        or type(reason) is not int
        or type(iterations) is not int
        or not 0 <= iterations <= 128
        or not isinstance(residual, Mapping)
        or set(residual)
        != {"rhs_norm", "solution_norm", "residual_norm", "relative_residual"}
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in residual.values()
        )
        or not isinstance(candidate, Mapping)
        or type(candidate.get("global_size")) is not int
        or candidate["global_size"] <= 0
        or not isinstance(candidate.get("original_D_rhs_norm"), (int, float))
        or isinstance(candidate.get("original_D_rhs_norm"), bool)
        or not math.isfinite(float(candidate["original_D_rhs_norm"]))
        or float(candidate["original_D_rhs_norm"]) <= 0.0
        or residual["rhs_norm"] != candidate["original_D_rhs_norm"]
        or residual["relative_residual"] != eta64
        or not math.isclose(
            float(residual["relative_residual"]),
            float(residual["residual_norm"]) / float(residual["rhs_norm"]),
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
        or not isinstance(rank_rows, list)
        or len(rank_rows) != rank_count
        or not _task041_v12_restart64_selection_matches(
            record, rank_count=rank_count
        )
    ):
        return False
    reason_enum = PETSc.KSP.ConvergedReason
    runtime_diverged_its = getattr(reason_enum, "DIVERGED_ITS", None)
    if runtime_diverged_its is None:
        runtime_diverged_its = getattr(reason_enum, "DIVERGED_MAX_IT", None)
    if not (
        reason > 0
        or (
            runtime_diverged_its is not None
            and reason == int(runtime_diverged_its)
        )
    ):
        return False
    return all(
        isinstance(row, Mapping)
        and row.get("rank") == rank
        and row.get("ksp_reason") == reason
        and row.get("iterations") == iterations
        and row.get("same_p4_factor_handle_local") is True
        and row.get("candidate_rhs_unchanged_local") is True
        and isinstance(row.get("original_D_residual"), Mapping)
        and dict(row["original_D_residual"]) == dict(residual)
        for rank, row in enumerate(rank_rows)
    )


def _task041_v12_restart64_selection_matches(
    record: Mapping[str, Any], *, rank_count: int
) -> bool:
    """Recompute the residual-and-max-rank-wall restart64 decision."""

    selection = record.get("selection_evidence")
    candidate = record.get("candidate_rhs_binding")
    baseline_rows = (
        candidate.get("restart32_reference_work_by_rank")
        if isinstance(candidate, Mapping)
        else None
    )
    trial_rows = record.get("restart64_rank_records")
    eta32 = record.get("restart32_relative_residual")
    eta64 = record.get("restart64_relative_residual")
    rule_id = (
        "same_rhs_eta64_at_most_0.9_eta32_and_max_rank_trial_wall_with_one_setup_not_higher"
        "_and_log_residual_reduction_per_wall_not_lower"
    )
    if (
        not isinstance(selection, Mapping)
        or selection.get("rule_id") != rule_id
        or not isinstance(baseline_rows, list)
        or len(baseline_rows) != rank_count
        or not isinstance(trial_rows, list)
        or len(trial_rows) != rank_count
    ):
        return False

    def finite(value: Any, *, positive: bool = False) -> float | None:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            return None
        result = float(value)
        return result if result >= 0.0 and (not positive or result > 0.0) else None

    eta32_value = finite(eta32, positive=True)
    eta64_value = finite(eta64, positive=True)
    if (
        eta32_value is None
        or eta64_value is None
        or eta32_value >= 1.0
        or eta64_value >= 1.0
    ):
        return _task041_v12_invalid_restart64_selection_is_retained(selection)

    baseline_local: list[float] = []
    baseline_reported_max: list[float] = []
    trial_local: list[float] = []
    setup_local: list[float] = []
    for rank, (baseline, trial) in enumerate(
        zip(baseline_rows, trial_rows, strict=True)
    ):
        if (
            not isinstance(baseline, Mapping)
            or baseline.get("rank") != rank
            or not isinstance(trial, Mapping)
            or trial.get("rank") != rank
        ):
            return _task041_v12_invalid_restart64_selection_is_retained(selection)
        values = (
            finite(baseline.get("rank_local_elapsed_seconds"), positive=True),
            finite(baseline.get("max_rank_elapsed_seconds"), positive=True),
            finite(trial.get("elapsed_local_seconds"), positive=True),
            finite(trial.get("ksp_setup_elapsed_local_seconds")),
        )
        if any(value is None for value in values):
            return _task041_v12_invalid_restart64_selection_is_retained(selection)
        baseline_local.append(float(values[0]))
        baseline_reported_max.append(float(values[1]))
        trial_local.append(float(values[2]))
        setup_local.append(float(values[3]))

    baseline_wall = max(baseline_local)
    trial_solve_wall = max(trial_local)
    setup_wall = max(setup_local)
    trial_wall_with_setup = max(
        solve + setup for solve, setup in zip(trial_local, setup_local, strict=True)
    )
    if (
        not all(
            math.isclose(value, baseline_wall, rel_tol=1.0e-12, abs_tol=1.0e-15)
            for value in baseline_reported_max
        )
        or not math.isclose(
            (
                finite(record.get("trial_elapsed_seconds_max_rank"), positive=True)
                if finite(
                    record.get("trial_elapsed_seconds_max_rank"), positive=True
                )
                is not None
                else -1.0
            ),
            trial_solve_wall,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
        or not math.isclose(
            (
                finite(record.get("trial_ksp_setup_elapsed_max_rank_seconds"))
                if finite(record.get("trial_ksp_setup_elapsed_max_rank_seconds"))
                is not None
                else -1.0
            ),
            setup_wall,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
        or not math.isclose(
            finite(
                record.get(
                    "trial_transition_wall_including_one_setup_max_rank_seconds"
                ),
                positive=True,
            )
            or -1.0,
            trial_wall_with_setup,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
    ):
        return _task041_v12_invalid_restart64_selection_is_retained(selection)

    try:
        baseline_rate = -math.log(eta32_value) / baseline_wall
        trial_rate = -math.log(eta64_value) / trial_wall_with_setup
    except (OverflowError, ZeroDivisionError):
        return _task041_v12_invalid_restart64_selection_is_retained(selection)
    if not math.isfinite(baseline_rate) or not math.isfinite(trial_rate):
        return _task041_v12_invalid_restart64_selection_is_retained(selection)
    residual_ok = eta64_value <= 0.9 * eta32_value
    wall_ok = trial_wall_with_setup <= baseline_wall
    rate_ok = trial_rate >= baseline_rate
    eligible = residual_ok and wall_ok and rate_ok
    expected_numbers = {
        "restart32_max_rank_side_wall_seconds": baseline_wall,
        "restart64_max_rank_side_solve_wall_seconds": trial_solve_wall,
        "restart64_max_rank_setup_wall_seconds": setup_wall,
        "restart64_max_rank_trial_wall_with_setup_seconds": trial_wall_with_setup,
        "restart32_log_residual_reduction_per_wall": baseline_rate,
        "restart64_log_residual_reduction_per_wall": trial_rate,
    }
    return bool(
        selection.get("residual_improved_by_at_least_10_percent") is residual_ok
        and selection.get("max_rank_trial_wall_with_one_setup_not_higher") is wall_ok
        and selection.get("log_residual_reduction_per_wall_not_lower") is rate_ok
        and selection.get("eligible_for_64") is eligible
        and selection.get("reason")
        == (
            "residual_and_cost_improved"
            if eligible
            else "restart64_did_not_improve_residual_and_cost_together"
        )
        and all(
            isinstance(selection.get(name), (int, float))
            and not isinstance(selection.get(name), bool)
            and math.isclose(
                float(selection[name]), expected, rel_tol=1.0e-12, abs_tol=1.0e-15
            )
            for name, expected in expected_numbers.items()
        )
    )


def _task041_v12_invalid_restart64_selection_is_retained(
    selection: Mapping[str, Any]
) -> bool:
    """A missing/non-finite cost may only retain restart32."""

    return bool(
        selection.get("eligible_for_64") is False
        and selection.get("residual_improved_by_at_least_10_percent") is False
        and selection.get("max_rank_trial_wall_with_one_setup_not_higher") is False
        and selection.get("log_residual_reduction_per_wall_not_lower") is False
        and all(
            selection.get(name) is None
            for name in (
                "restart32_max_rank_side_wall_seconds",
                "restart64_max_rank_side_solve_wall_seconds",
                "restart64_max_rank_setup_wall_seconds",
                "restart64_max_rank_trial_wall_with_setup_seconds",
                "restart32_log_residual_reduction_per_wall",
                "restart64_log_residual_reduction_per_wall",
            )
        )
    )
def solve_action_modal_schur_anderson(
    modal_action: HybridActionModalSchurApply,
    rhs: np.ndarray,
    *,
    scale_residual_by_constraint: bool = False,
    real_coordinate_embedding: bool = False,
    max_iterations: int = 8,
    _borrowed_constraint_factor: Any | None = None,
) -> dict[str, Any]:
    """Solve a bounded nonlinear modal equation with PETSc SNESANDERSON.

    The borrowed action is evaluated as ``S(m) - rhs`` on every SNES function
    call.  No fixed Schur Mat or side-action ownership is introduced.  The
    raw function norm is used directly by default: nonzero RHS uses a 1e-2
    relative target, while zero RHS uses a 1e-2 absolute target. The opt-in
    constraint scaling changes the Anderson residual, but convergence is
    still decided from the matching unscaled residual. A caller may lend an
    owner-only C LU; standalone calls continue to factor and release their
    own C LU. The optional real-coordinate embedding represents each complex
    modal value by two real-valued PETSc scalars; its Anderson trajectory is
    a real-coefficient candidate, not the complex-coefficient trajectory.
    """

    if modal_action._destroyed:
        raise RuntimeError("On-demand modal Schur action has been destroyed.")
    modal_count = int(modal_action.modal_count)
    operator = _action_operator(modal_action.bottom_action)
    petsc_comm = operator.getComm()
    comm = petsc_comm.tompi4py()
    root = comm.size - 1

    try:
        rhs_values = np.asarray(rhs, dtype=np.complex128)
        rhs_valid = (
            rhs_values.shape == (modal_count,)
            and bool(np.all(np.isfinite(rhs_values)))
        )
    except (TypeError, ValueError):
        rhs_values = np.empty(0, dtype=np.complex128)
        rhs_valid = False
    if not comm.allreduce(rhs_valid, op=MPI.LAND):
        raise ValueError("Modal Anderson RHS must be a finite modal vector.")
    rhs_hashes = comm.allgather(hashlib.sha256(rhs_values.tobytes()).hexdigest())
    if len(set(rhs_hashes)) != 1:
        raise ValueError("Modal Anderson RHS differs across MPI ranks.")
    rhs_values = rhs_values.copy()
    rhs_norm = float(np.linalg.norm(rhs_values))
    if not np.isfinite(rhs_norm):
        raise ValueError("Modal Anderson RHS norm is non-finite.")
    absolute_tolerance = 1.0e-2 * rhs_norm if rhs_norm != 0.0 else 1.0e-2
    if not isinstance(scale_residual_by_constraint, (bool, np.bool_)):
        raise TypeError("Constraint residual scaling must be an explicit boolean.")
    scale_residual_by_constraint = bool(scale_residual_by_constraint)
    if not isinstance(real_coordinate_embedding, (bool, np.bool_)):
        raise TypeError("Real modal coordinate embedding must be an explicit boolean.")
    real_coordinate_embedding = bool(real_coordinate_embedding)
    if isinstance(max_iterations, (bool, np.bool_)):
        raise TypeError("Modal Anderson max_iterations must be an integer.")
    max_iterations = int(max_iterations)
    if max_iterations < 1:
        raise ValueError("Modal Anderson max_iterations must be positive.")
    coordinate_count = 2 * modal_count if real_coordinate_embedding else modal_count
    coordinate_extra_bytes_per_vec = (
        modal_count * np.dtype(PETSc.ScalarType).itemsize
        if real_coordinate_embedding
        else 0
    )

    options = PETSc.Options()
    option_prefix = "task041_modal_inner_"
    history_option = f"{option_prefix}snes_anderson_m"
    try:
        previous_history_option = options.getString(history_option)
    except KeyError:
        previous_history_option = None

    local_modal_size = coordinate_count if comm.rank == root else 0
    solution = None
    function_value = None
    snes = None
    function_evaluations = 0
    function_callbacks = 0
    convergence_callbacks = 0
    budget_exhausted = False
    budget_callback_skipped = False
    nonfinite_evaluation = False
    raw_cache_iteration_mismatch = False
    real_coordinate_subspace_violation = False
    callback_target_reached = False
    callback_reason = int(PETSc.SNES.ConvergedReason.ITERATING)
    last_snes_function_norm = None
    final_evaluations = 0
    residual_history: list[dict[str, Any]] = []
    latest_raw_cache: dict[str, Any] = {
        "iterate": None,
        "residual": None,
        "raw_norm": None,
        "raw_metric": None,
        "scaled_norm": None,
        "finite": False,
    }
    constraint_lu = None
    constraint_pivots = None
    constraint_condition_number = None
    constraint_lu_factorizations = 0
    constraint_lu_solve_calls = 0
    actions = {
        "bottom": modal_action.bottom_action,
        "top": modal_action.top_action,
    }
    action_counts_before = {
        side: _action_apply_count(action) for side, action in actions.items()
    }

    def scale_raw_residual(raw_residual: np.ndarray) -> np.ndarray:
        nonlocal constraint_lu_solve_calls
        if not scale_residual_by_constraint:
            return np.asarray(raw_residual, dtype=np.complex128).copy()
        owner_result = None
        if comm.rank == root:
            try:
                scaled = lu_solve(
                    (constraint_lu, constraint_pivots),
                    np.asarray(raw_residual, dtype=np.complex128),
                    check_finite=True,
                )
                if not bool(np.all(np.isfinite(scaled))):
                    owner_result = (False, None, "C solve produced non-finite values")
                else:
                    owner_result = (
                        True,
                        np.asarray(scaled, dtype=np.complex128),
                        None,
                    )
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                owner_result = (
                    False,
                    None,
                    f"C solve failed: {type(exc).__name__}: {exc}",
                )
        success, scaled_values, error = comm.bcast(owner_result, root=root)
        if not success:
            if error == "C solve produced non-finite values":
                return np.full(modal_count, np.nan, dtype=np.complex128)
            raise RuntimeError(str(error))
        constraint_lu_solve_calls += 1
        return np.asarray(scaled_values, dtype=np.complex128)

    def decode_coordinates(coordinate_values: np.ndarray) -> np.ndarray:
        nonlocal real_coordinate_subspace_violation
        if not real_coordinate_embedding:
            return np.asarray(coordinate_values, dtype=np.complex128)
        # The coordinate vector is owner-read and broadcast by
        # _replicated_modal_values, so every rank checks the same values.
        if not bool(np.all(coordinate_values.imag == 0.0)):
            real_coordinate_subspace_violation = True
        return _decode_modal_real_coordinates(coordinate_values, modal_count)

    try:
        if scale_residual_by_constraint and _borrowed_constraint_factor is not None:
            factor = _borrowed_constraint_factor
            local_factor_valid = bool(
                getattr(factor, "modal_action", None) is modal_action
                and int(getattr(factor, "modal_count", -1)) == modal_count
                and int(getattr(factor, "constraint_lu_owner_rank", -1)) == root
                and np.isfinite(float(getattr(factor, "constraint_condition", np.nan)))
            )
            factor_lu = getattr(factor, "constraint_lu", None)
            factor_pivots = getattr(factor, "constraint_pivots", None)
            if comm.rank == root:
                local_factor_valid = bool(
                    local_factor_valid
                    and isinstance(factor_lu, np.ndarray)
                    and factor_lu.shape == (modal_count, modal_count)
                    and isinstance(factor_pivots, np.ndarray)
                    and factor_pivots.shape == (modal_count,)
                )
            else:
                local_factor_valid = bool(
                    local_factor_valid and factor_lu is None and factor_pivots is None
                )
            if not comm.allreduce(local_factor_valid, op=MPI.LAND):
                raise ValueError("Borrowed C LU must be valid only on the modal owner.")
            constraint_lu = factor_lu
            constraint_pivots = factor_pivots
            constraint_condition_number = float(factor.constraint_condition)
        elif scale_residual_by_constraint:
            owner_factor_result = None
            if comm.rank == root:
                try:
                    lu, pivots, condition = _factor_modal_constraint(
                        modal_action.modal_constraint, modal_count
                    )
                    constraint_lu = lu
                    constraint_pivots = pivots
                    constraint_condition_number = condition
                    owner_factor_result = (True, condition, None)
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    owner_factor_result = (
                        False,
                        None,
                        f"C factorization rejected: {type(exc).__name__}: {exc}",
                    )
            factor_ok, factor_condition, factor_error = comm.bcast(
                owner_factor_result, root=root
            )
            if not factor_ok:
                raise RuntimeError(str(factor_error))
            constraint_condition_number = float(factor_condition)
            constraint_lu_factorizations = 1
        elif _borrowed_constraint_factor is not None:
            raise ValueError("A borrowed C LU requires constraint residual scaling.")

        solution = PETSc.Vec().createMPI(
            (local_modal_size, coordinate_count), comm=petsc_comm
        )
        function_value = solution.duplicate()
        snes = PETSc.SNES().create(comm=petsc_comm)
        solution.set(PETSc.ScalarType(0.0))

        def function(_snes, modal_vector, residual_vector) -> None:
            nonlocal function_evaluations, function_callbacks
            nonlocal budget_callback_skipped
            nonlocal nonfinite_evaluation
            function_callbacks += 1
            if function_evaluations >= _MODAL_ANDERSON_S_EVALUATION_LIMIT - 1:
                budget_callback_skipped = True
                return
            coordinate_values = _replicated_modal_values(modal_vector)
            modal_values = decode_coordinates(coordinate_values)
            if real_coordinate_subspace_violation:
                latest_raw_cache.update(
                    iterate=coordinate_values.copy(),
                    residual=None,
                    raw_norm=None,
                    raw_metric=None,
                    scaled_norm=None,
                    finite=False,
                )
                residual_history.append(
                    {
                        "evaluation": function_evaluations,
                        "source": "real_coordinate_subspace_violation",
                        "raw_residual_norm": None,
                        "raw_target_metric": None,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )
                residual_vector.set(PETSc.ScalarType(np.nan))
                return
            raw_residual = np.asarray(
                modal_action.apply(modal_values) - rhs_values,
                dtype=np.complex128,
            )
            function_evaluations += 1
            local_finite = raw_residual.shape == (modal_count,) and bool(
                np.all(np.isfinite(raw_residual))
            )
            globally_finite = comm.allreduce(local_finite, op=MPI.LAND)
            if not globally_finite:
                nonfinite_evaluation = True
                latest_raw_cache.update(
                    iterate=coordinate_values.copy(),
                    residual=None,
                    raw_norm=None,
                    raw_metric=None,
                    scaled_norm=None,
                    finite=False,
                )
                residual_history.append(
                    {
                        "evaluation": function_evaluations,
                        "source": "snes_function",
                        "raw_residual_norm": None,
                        "raw_target_metric": None,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )
                residual_vector.set(PETSc.ScalarType(np.nan))
                return
            raw_norm = float(np.linalg.norm(raw_residual))
            raw_metric = raw_norm / rhs_norm if rhs_norm != 0.0 else raw_norm
            scaled_residual = scale_raw_residual(raw_residual)
            if not bool(np.all(np.isfinite(scaled_residual))):
                nonfinite_evaluation = True
                latest_raw_cache.update(
                    iterate=coordinate_values.copy(),
                    residual=raw_residual.copy(),
                    raw_norm=raw_norm,
                    raw_metric=raw_metric,
                    scaled_norm=None,
                    finite=False,
                )
                residual_history.append(
                    {
                        "evaluation": function_evaluations,
                        "source": "snes_function",
                        "raw_residual_norm": raw_norm,
                        "raw_target_metric": raw_metric,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )
                residual_vector.set(PETSc.ScalarType(np.nan))
                return
            scaled_norm = float(np.linalg.norm(scaled_residual))
            solver_residual = (
                _encode_modal_real_coordinates(scaled_residual)
                if real_coordinate_embedding
                else scaled_residual
            )
            latest_raw_cache.update(
                iterate=coordinate_values.copy(),
                residual=raw_residual.copy(),
                raw_norm=raw_norm,
                raw_metric=raw_metric,
                scaled_norm=scaled_norm,
                finite=True,
            )
            residual_history.append(
                {
                    "evaluation": function_evaluations,
                    "source": "snes_function",
                    "raw_residual_norm": raw_norm,
                    "raw_target_metric": raw_metric,
                    "scaled_residual_norm": scaled_norm,
                    "finite": True,
                }
            )
            _set_owned_values(residual_vector, solver_residual)

        def convergence_test(_snes, iteration, norms):
            nonlocal convergence_callbacks, callback_target_reached
            nonlocal callback_reason, last_snes_function_norm
            nonlocal raw_cache_iteration_mismatch, budget_exhausted
            convergence_callbacks += 1
            _xnorm, _ynorm, fnorm = norms
            last_snes_function_norm = float(fnorm)
            if nonfinite_evaluation:
                reason = PETSc.SNES.ConvergedReason.DIVERGED_FNORM_NAN
            elif real_coordinate_subspace_violation:
                reason = PETSc.SNES.ConvergedReason.DIVERGED_FUNCTION_DOMAIN
            elif budget_callback_skipped:
                reason = PETSc.SNES.ConvergedReason.DIVERGED_FUNCTION_COUNT
            elif not latest_raw_cache["finite"]:
                raw_cache_iteration_mismatch = True
                reason = PETSc.SNES.ConvergedReason.DIVERGED_INNER
            else:
                current_solution = _snes.getSolution()
                try:
                    current_values = _replicated_modal_values(current_solution)
                finally:
                    current_solution.destroy()
                cached_values = latest_raw_cache["iterate"]
                if not np.array_equal(current_values, cached_values):
                    raw_cache_iteration_mismatch = True
                    reason = PETSc.SNES.ConvergedReason.DIVERGED_INNER
                elif float(latest_raw_cache["raw_metric"]) <= 1.0e-2:
                    callback_target_reached = True
                    reason = PETSc.SNES.ConvergedReason.CONVERGED_FNORM_ABS
                elif (
                    function_evaluations
                    >= _MODAL_ANDERSON_S_EVALUATION_LIMIT - 1
                ):
                    budget_exhausted = True
                    reason = PETSc.SNES.ConvergedReason.DIVERGED_FUNCTION_COUNT
                elif int(iteration) >= max_iterations:
                    reason = PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT
                else:
                    reason = PETSc.SNES.ConvergedReason.ITERATING
            callback_reason = int(reason)
            return reason

        snes.setOptionsPrefix(option_prefix)
        snes.setType(PETSc.SNES.Type.ANDERSON)
        options.setValue(history_option, "4")
        snes.setFromOptions()
        if str(snes.getType()) != str(PETSc.SNES.Type.ANDERSON):
            raise RuntimeError("PETSc changed the requested SNESANDERSON type.")
        snes.setFunction(function, function_value)
        snes.setTolerances(
            rtol=0.0,
            atol=absolute_tolerance,
            stol=0.0,
            max_it=max_iterations,
        )
        snes.setConvergenceTest(convergence_test)
        # Reserve one of the sixteen allowed S evaluations for an independent
        # raw-residual check after SNES returns.
        snes.setMaxFunctionEvaluations(_MODAL_ANDERSON_S_EVALUATION_LIMIT)
        snes.solve(None, solution)

        iterations = int(snes.getIterationNumber())
        snes_reason = int(snes.getConvergedReason())
        coordinate_values = _replicated_modal_values(solution)
        modal_values = decode_coordinates(coordinate_values)
        residual_norm = float("inf")
        target_value = float("inf")
        final_target_reached = False
        final_scaled_norm = float("inf")
        if (
            not nonfinite_evaluation
            and not real_coordinate_subspace_violation
            and bool(np.all(np.isfinite(modal_values)))
        ):
            final_residual = np.asarray(
                modal_action.apply(modal_values) - rhs_values,
                dtype=np.complex128,
            )
            final_evaluations = 1
            local_finite = final_residual.shape == (modal_count,) and bool(
                np.all(np.isfinite(final_residual))
            )
            globally_finite = comm.allreduce(local_finite, op=MPI.LAND)
            if globally_finite:
                residual_norm = float(np.linalg.norm(final_residual))
                if np.isfinite(residual_norm):
                    target_value = (
                        residual_norm / rhs_norm
                        if rhs_norm != 0.0
                        else residual_norm
                    )
                    final_scaled_residual = scale_raw_residual(final_residual)
                    if bool(np.all(np.isfinite(final_scaled_residual))):
                        final_solver_residual = (
                            _encode_modal_real_coordinates(final_scaled_residual)
                            if real_coordinate_embedding
                            else final_scaled_residual
                        )
                        final_scaled_norm = float(
                            np.linalg.norm(final_solver_residual)
                        )
                        final_target_reached = target_value <= 1.0e-2
                        residual_history.append(
                            {
                                "evaluation": function_evaluations + final_evaluations,
                                "source": "final_validation",
                                "raw_residual_norm": residual_norm,
                                "raw_target_metric": target_value,
                                "scaled_residual_norm": final_scaled_norm,
                                "finite": True,
                            }
                        )
                    else:
                        nonfinite_evaluation = True
                        residual_history.append(
                            {
                                "evaluation": function_evaluations + final_evaluations,
                                "source": "final_validation",
                                "raw_residual_norm": residual_norm,
                                "raw_target_metric": target_value,
                                "scaled_residual_norm": None,
                                "finite": False,
                            }
                        )
                else:
                    nonfinite_evaluation = True
                    residual_history.append(
                        {
                            "evaluation": function_evaluations + final_evaluations,
                            "source": "final_validation",
                            "raw_residual_norm": None,
                            "raw_target_metric": None,
                            "scaled_residual_norm": None,
                            "finite": False,
                        }
                    )
            else:
                nonfinite_evaluation = True
                residual_history.append(
                    {
                        "evaluation": function_evaluations + final_evaluations,
                        "source": "final_validation",
                        "raw_residual_norm": None,
                        "raw_target_metric": None,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )

        total_evaluations = function_evaluations + final_evaluations
        if total_evaluations > _MODAL_ANDERSON_S_EVALUATION_LIMIT:
            raise RuntimeError("Modal Anderson exceeded its S-evaluation budget.")
        if (
            callback_target_reached
            and final_target_reached
            and not nonfinite_evaluation
            and not budget_exhausted
            and not budget_callback_skipped
            and not raw_cache_iteration_mismatch
            and not real_coordinate_subspace_violation
            and snes_reason > 0
        ):
            status = "converged"
            stop_reason = "unscaled_residual_target"
        else:
            status = "not_converged"
            if budget_exhausted or budget_callback_skipped:
                stop_reason = "budget_exhausted"
            elif nonfinite_evaluation:
                stop_reason = "nonfinite_residual"
            elif raw_cache_iteration_mismatch:
                stop_reason = "raw_cache_iteration_mismatch"
            elif real_coordinate_subspace_violation:
                stop_reason = "real_coordinate_subspace_violation"
            elif snes_reason == int(PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT):
                stop_reason = "max_iterations"
            elif function_evaluations >= _MODAL_ANDERSON_S_EVALUATION_LIMIT - 1:
                stop_reason = "function_evaluation_budget"
            else:
                stop_reason = "snes_nonconvergence"

        side_action_calls = {}
        for side, action in actions.items():
            before = action_counts_before[side]
            after = _action_apply_count(action)
            delta = None if before is None or after is None else after - before
            if delta is not None and delta < 0:
                delta = None
            rank_deltas = comm.allgather(delta)
            side_action_calls[side] = (
                int(delta)
                if delta is not None and all(value == delta for value in rank_deltas)
                else None
            )
        rank_state = (
            function_evaluations,
            function_callbacks,
            convergence_callbacks,
            final_evaluations,
            iterations,
            status,
            stop_reason,
            float(residual_norm),
            float(target_value),
            total_evaluations,
            constraint_lu_solve_calls,
            real_coordinate_embedding,
            real_coordinate_subspace_violation,
            tuple(sorted(side_action_calls.items())),
        )
        if any(value != rank_state for value in comm.allgather(rank_state)):
            raise RuntimeError("Modal Anderson control flow differs across MPI ranks.")
        return {
            "status": status,
            "stop_reason": stop_reason,
            "mixing_method": "petsc_snes_anderson_default",
            "solution": modal_values.copy(),
            "target_reached": bool(callback_target_reached and final_target_reached),
            "convergence_callback_target_reached": bool(callback_target_reached),
            "final_unscaled_target_reached": bool(final_target_reached),
            "unscaled_residual_norm": residual_norm,
            "rhs_norm": rhs_norm,
            "relative_residual": target_value,
            "scaled_residual_norm": final_scaled_norm,
            "last_snes_function_norm": last_snes_function_norm,
            "residual_evaluation_history": residual_history,
            "constraint_scale_enabled": scale_residual_by_constraint,
            "real_coordinate_embedding": real_coordinate_embedding,
            "modal_coordinate_representation": (
                "real_parts_then_imag_parts_in_complex128"
                if real_coordinate_embedding
                else "complex128_modal_values"
            ),
            "modal_coordinate_count": coordinate_count,
            "modal_coordinate_extra_bytes_per_explicit_vec": int(
                coordinate_extra_bytes_per_vec
            ),
            "modal_coordinate_extra_bytes_two_explicit_vecs": int(
                2 * coordinate_extra_bytes_per_vec
            ),
            "real_coordinate_subspace_violation": bool(
                real_coordinate_subspace_violation
            ),
            "constraint_condition_2": constraint_condition_number,
            "constraint_lu_owner_rank": root if scale_residual_by_constraint else None,
            "constraint_lu_factorizations": constraint_lu_factorizations,
            "constraint_lu_solve_calls": constraint_lu_solve_calls,
            "constraint_lu_borrowed": _borrowed_constraint_factor is not None,
            "zero_rhs_absolute_residual": rhs_norm == 0.0,
            "iterations": iterations,
            "function_evaluations": function_evaluations,
            "function_callbacks": function_callbacks,
            "convergence_callbacks": convergence_callbacks,
            "final_validation_evaluations": final_evaluations,
            "s_evaluation_count": total_evaluations,
            "s_evaluation_limit": _MODAL_ANDERSON_S_EVALUATION_LIMIT,
            "snes_function_evaluation_limit": _MODAL_ANDERSON_S_EVALUATION_LIMIT,
            "budget_callback_skipped": bool(budget_callback_skipped),
            "budget_callback_residual_state": (
                "not_evaluated" if budget_callback_skipped else None
            ),
            "budget_reason": (
                "DIVERGED_FUNCTION_COUNT"
                if budget_exhausted or budget_callback_skipped
                else None
            ),
            "budget_exhausted": bool(budget_exhausted),
            "anderson_history": 4,
            "max_iterations": max_iterations,
            "snes_converged_reason": snes_reason,
            "callback_converged_reason": callback_reason,
            "raw_cache_iteration_mismatch": bool(raw_cache_iteration_mismatch),
            "side_action_calls": side_action_calls,
        }
    finally:
        if snes is not None:
            snes.destroy()
        if function_value is not None:
            function_value.destroy()
        if solution is not None:
            solution.destroy()
        options.delValue(history_option)
        if previous_history_option is not None:
            options.setValue(history_option, previous_history_option)
        constraint_lu = None
        constraint_pivots = None


def solve_action_modal_schur_anderson_complex_qr_research(
    modal_action: HybridActionModalSchurApply,
    rhs: np.ndarray,
    *,
    _borrowed_constraint_factor: Any,
    raw_metric_mixing: bool = False,
    _capture_trace_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded full-S complex QR path with an optional raw gamma metric."""

    if modal_action._destroyed:
        raise RuntimeError("On-demand modal Schur action has been destroyed.")
    modal_count = int(modal_action.modal_count)
    comm = _action_operator(modal_action.bottom_action).getComm().tompi4py()
    root = comm.size - 1
    max_iterations, history_limit = 14, 4
    evaluation_limit = _MODAL_ANDERSON_S_EVALUATION_LIMIT
    beta = 1.0
    if not isinstance(raw_metric_mixing, (bool, np.bool_)):
        raise TypeError("Raw-metric Anderson selection must be an explicit boolean.")
    mixing_metric = "raw_residual" if raw_metric_mixing else "C_scaled_residual"
    rhs_values = np.asarray(rhs, dtype=np.complex128)
    rhs_valid = rhs_values.shape == (modal_count,) and bool(np.all(np.isfinite(rhs_values)))
    if not comm.allreduce(rhs_valid, op=MPI.LAND):
        raise ValueError("Modal Anderson RHS must be a finite modal vector.")
    rhs_hashes = comm.allgather(hashlib.sha256(rhs_values.tobytes()).hexdigest())
    if len(set(rhs_hashes)) != 1:
        raise ValueError("Modal Anderson RHS differs across MPI ranks.")
    rhs_values = rhs_values.copy()
    if _capture_trace_record is not None:
        _capture_trace_record["rhs_sha256"] = rhs_hashes[root]
        _capture_trace_record["g"] = _capture_modal_array(
            _capture_trace_record, "g", rhs_values
        )
    with np.errstate(over="ignore", invalid="ignore"):
        rhs_norm = float(np.linalg.norm(rhs_values))
    if not comm.allreduce(bool(np.isfinite(rhs_norm)), op=MPI.LAND):
        raise ValueError("Modal Anderson RHS norm is non-finite.")

    factor = _borrowed_constraint_factor
    factor_lu = getattr(factor, "constraint_lu", None)
    factor_pivots = getattr(factor, "constraint_pivots", None)
    factor_valid = bool(
        getattr(factor, "modal_action", None) is modal_action
        and int(getattr(factor, "modal_count", -1)) == modal_count
        and int(getattr(factor, "constraint_lu_owner_rank", -1)) == root
        and np.isfinite(float(getattr(factor, "constraint_condition", np.nan)))
    )
    if comm.rank == root:
        factor_valid = bool(
            factor_valid
            and isinstance(factor_lu, np.ndarray)
            and factor_lu.shape == (modal_count, modal_count)
            and isinstance(factor_pivots, np.ndarray)
            and factor_pivots.shape == (modal_count,)
        )
    else:
        factor_valid = bool(factor_valid and factor_lu is None and factor_pivots is None)
    if not comm.allreduce(factor_valid, op=MPI.LAND):
        raise ValueError("Borrowed C LU must be valid only on the modal owner.")

    actions = {"bottom": modal_action.bottom_action, "top": modal_action.top_action}
    counts_before = {side: _action_apply_count(action) for side, action in actions.items()}
    residual_history: list[dict[str, Any]] = []
    if _capture_trace_record is not None and comm.rank == root:
        _capture_trace_record["evaluations"] = residual_history
    mixing_history: list[dict[str, Any]] = []
    owner_states: list[tuple[np.ndarray, np.ndarray]] = []
    owner_raw_residuals: list[np.ndarray] = []
    modal_values = np.zeros(modal_count, dtype=np.complex128)
    function_evaluations = total_evaluations = c_solves = iterations = 0
    final_evaluations = 0
    callback_target = final_target = evaluation_failed = False
    budget_exhausted = False
    stop_reason = "max_iterations"
    last_raw_norm = last_raw_metric = last_scaled_norm = float("inf")

    def evaluate(current: np.ndarray, source: str):
        nonlocal function_evaluations, total_evaluations, c_solves
        capture_evaluation = None
        if _capture_trace_record is not None and comm.rank == root:
            capture_evaluation = {
                "evaluation": total_evaluations + 1,
                "source": source,
                "finite": False,
            }
            residual_history.append(capture_evaluation)
            if len(residual_history) <= evaluation_limit:
                capture_evaluation["m"] = _capture_modal_array(
                    _capture_trace_record, "m", current
                )
            else:
                _capture_trace_record["capture_incomplete_reason"] = (
                    "evaluation_count_exceeded_capture_limit"
                )
        action_values = modal_action.apply(current)
        raw = np.asarray(action_values - rhs_values, dtype=np.complex128)
        total_evaluations += 1
        if source == "complex_qr_iteration":
            function_evaluations += 1
        if capture_evaluation is not None and comm.rank == root:
            capture_evaluation["side_actions"] = {
                side: _modal_trace_side_apply_record(action)
                for side, action in actions.items()
            }
            capture_evaluation["raw"] = _capture_modal_array(
                _capture_trace_record, "raw", raw
            )
        finite = raw.shape == (modal_count,) and bool(np.all(np.isfinite(raw)))
        finite = bool(comm.allreduce(finite, op=MPI.LAND))
        payload = None
        if comm.rank == root:
            if not finite:
                payload = (False, None, "nonfinite_residual")
            else:
                try:
                    raw_norm = float(np.linalg.norm(raw))
                    raw_metric = raw_norm / rhs_norm if rhs_norm else raw_norm
                    scaled = lu_solve((factor_lu, factor_pivots), raw, check_finite=True)
                    if capture_evaluation is not None:
                        capture_evaluation["scaled"] = _capture_modal_array(
                            _capture_trace_record,
                            "scaled",
                            np.asarray(scaled, dtype=np.complex128),
                        )
                    fixed_point = -np.asarray(scaled, dtype=np.complex128)
                    scaled_norm = float(np.linalg.norm(scaled))
                    if (
                        not np.isfinite(raw_norm)
                        or not np.isfinite(raw_metric)
                        or not np.isfinite(scaled_norm)
                        or not np.all(np.isfinite(fixed_point))
                    ):
                        payload = (False, None, "nonfinite_residual")
                    else:
                        payload = (
                            True,
                            (raw_norm, raw_metric, scaled_norm, fixed_point),
                            None,
                        )
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    payload = (False, None, f"constraint_solve_failure: {exc}")
        success, values, error = comm.bcast(payload, root=root)
        if not success:
            if capture_evaluation is not None:
                row = capture_evaluation
                row.update(finite=False, capture_complete=False)
                _capture_trace_record["capture_incomplete_reason"] = (
                    "residual_evaluation_failed"
                )
            else:
                row = {
                    "evaluation": total_evaluations,
                    "source": source,
                    "raw_residual_norm": None,
                    "raw_target_metric": None,
                    "scaled_residual_norm": None,
                    "finite": False,
                }
                residual_history.append(row)
            return None, row, error, None
        c_solves += 1
        raw_norm, raw_metric, scaled_norm, fixed_point = values
        if capture_evaluation is None:
            row = {
                "evaluation": total_evaluations,
                "source": source,
                "raw_residual_norm": float(raw_norm),
                "raw_target_metric": float(raw_metric),
                "scaled_residual_norm": float(scaled_norm),
                "finite": True,
            }
            residual_history.append(row)
        else:
            row = capture_evaluation
            row.update(
                {
                    "raw_residual_norm": float(raw_norm),
                    "raw_target_metric": float(raw_metric),
                    "scaled_residual_norm": float(scaled_norm),
                    "finite": True,
                    "capture_complete": all(
                        row.get(key) is not None for key in ("m", "raw", "scaled")
                    ),
                }
            )
            if not row["capture_complete"]:
                _capture_trace_record["capture_incomplete_reason"] = (
                    "evaluation_vector_not_captured"
                )
        return (
            np.asarray(fixed_point, dtype=np.complex128),
            row,
            None,
            raw if raw_metric_mixing and comm.rank == root else None,
        )

    for _ in range(max_iterations + 1):
        if total_evaluations >= evaluation_limit - 1:
            budget_exhausted = True
            stop_reason = "budget_exhausted"
            break
        fixed_point, row, error, raw_residual = evaluate(
            modal_values, "complex_qr_iteration"
        )
        if error is not None:
            evaluation_failed = True
            stop_reason = error.split(":", 1)[0]
            break
        last_raw_norm = row["raw_residual_norm"]
        last_raw_metric = row["raw_target_metric"]
        last_scaled_norm = row["scaled_residual_norm"]
        if last_raw_metric <= 1.0e-2:
            callback_target = True
            stop_reason = "unscaled_residual_target"
            break
        if iterations == max_iterations:
            stop_reason = "max_iterations"
            break

        update_payload = None
        if comm.rank == root:
            owner_states.append((modal_values.copy(), fixed_point.copy()))
            if len(owner_states) > history_limit + 1:
                del owner_states[0]
            if raw_metric_mixing:
                if len(owner_raw_residuals) >= history_limit + 1:
                    del owner_raw_residuals[0]
                owner_raw_residuals.append(raw_residual)
            delta_m = delta_f = None
            delta_raw_residual = None
            if len(owner_states) > 1:
                delta_m = np.column_stack(
                    [owner_states[i + 1][0] - owner_states[i][0] for i in range(len(owner_states) - 1)]
                )
                delta_f = np.column_stack(
                    [owner_states[i + 1][1] - owner_states[i][1] for i in range(len(owner_states) - 1)]
                )
                if raw_metric_mixing:
                    delta_raw_residual = np.column_stack(
                        [
                            owner_raw_residuals[i + 1] - owner_raw_residuals[i]
                            for i in range(len(owner_raw_residuals) - 1)
                        ]
                    )
            try:
                candidate, mix = _complex_anderson_candidate_update(
                    modal_values,
                    fixed_point,
                    delta_m,
                    delta_f,
                    capture_coefficients=_capture_trace_record is not None,
                    mixing_metric=mixing_metric,
                    raw_residual=raw_residual if raw_metric_mixing else None,
                    delta_raw_residual=delta_raw_residual,
                )
                gamma = mix.pop("_capture_gamma", None)
                if _capture_trace_record is not None:
                    update_capture = {
                        "update_index": iterations + 1,
                        "source_evaluation_index": total_evaluations,
                        "candidate_accepted": candidate is not None,
                        "mixing_scalars": dict(mix),
                    }
                    if isinstance(gamma, np.ndarray):
                        update_capture["gamma"] = _capture_modal_array(
                            _capture_trace_record, "gamma", gamma
                        )
                    else:
                        update_capture["gamma"] = None
                        update_capture["gamma_status"] = "not_applicable_startup"
                    _capture_trace_record["updates"].append(update_capture)
                update_payload = (candidate is not None, candidate, mix, None)
            except (FloatingPointError, ValueError, np.linalg.LinAlgError) as exc:
                if _capture_trace_record is not None:
                    _capture_trace_record["updates"].append(
                        {
                            "update_index": iterations + 1,
                            "source_evaluation_index": total_evaluations,
                            "candidate_accepted": False,
                            "mixing_scalars": {},
                            "gamma": None,
                        }
                    )
                    _capture_trace_record["capture_incomplete_reason"] = (
                        "anderson_update_failed"
                    )
                update_payload = (False, None, {}, str(exc))
        update_ok, candidate, mix, update_error = comm.bcast(update_payload, root=root)
        mixing_history.append(dict(mix))
        if not update_ok:
            stop_reason = (
                "rank_zero_history"
                if mix.get("update") == "rank_zero_history"
                else "invalid_anderson_update"
            )
            if update_error:
                stop_reason = "nonfinite_or_invalid_anderson_update"
            break
        modal_values = np.asarray(candidate, dtype=np.complex128)
        iterations += 1

    if not evaluation_failed and bool(np.all(np.isfinite(modal_values))):
        _final_fixed_point, final_row, error, _final_raw_residual = evaluate(
            modal_values, "final_validation"
        )
        final_evaluations = 1
        if error is None:
            last_raw_norm = final_row["raw_residual_norm"]
            last_raw_metric = final_row["raw_target_metric"]
            last_scaled_norm = final_row["scaled_residual_norm"]
            final_target = last_raw_metric <= 1.0e-2
        else:
            evaluation_failed = True
            stop_reason = "final_validation_failure"

    if total_evaluations > evaluation_limit:
        raise RuntimeError("Complex modal Anderson exceeded its S-evaluation budget.")
    status = (
        "converged"
        if callback_target and final_target and not evaluation_failed
        and not budget_exhausted
        and stop_reason == "unscaled_residual_target"
        else "not_converged"
    )
    if status != "converged" and callback_target and final_evaluations:
        stop_reason = "final_validation_failed"

    side_calls = {}
    for side, action in actions.items():
        before, after = counts_before[side], _action_apply_count(action)
        delta = None if before is None or after is None else after - before
        rank_deltas = comm.allgather(delta if delta is not None and delta >= 0 else None)
        side_calls[side] = int(delta) if delta is not None and all(x == delta for x in rank_deltas) else None
    rank_state = (
        function_evaluations,
        total_evaluations,
        c_solves,
        iterations,
        status,
        stop_reason,
        budget_exhausted,
        last_raw_metric,
        tuple(sorted(side_calls.items())),
    )
    if any(item != rank_state for item in comm.allgather(rank_state)):
        raise RuntimeError("Complex modal Anderson control flow differs across MPI ranks.")

    if _capture_trace_record is not None and comm.rank == root:
        evaluations = _capture_trace_record.get("evaluations", [])
        capture_complete = bool(
            _capture_trace_record.get("g") is not None
            and len(evaluations) == total_evaluations
            and total_evaluations <= evaluation_limit
            and all(row.get("capture_complete") is True for row in evaluations)
            and not _capture_trace_record.get("capture_incomplete_reason")
        )
        _capture_trace_record.update(
            solver_status=status,
            solver_stop_reason=stop_reason,
            s_evaluation_count=total_evaluations,
            anderson_iterations=iterations,
            capture_complete=capture_complete,
        )
        if not capture_complete:
            _capture_trace_record.setdefault(
                "capture_incomplete_reason", "evaluation_trace_incomplete"
            )

    return {
        "status": status,
        "stop_reason": stop_reason,
        "solution": modal_values.copy(),
        "target_reached": bool(callback_target and final_target),
        "convergence_callback_target_reached": bool(callback_target),
        "final_unscaled_target_reached": bool(final_target),
        "invalid_failure": bool(evaluation_failed),
        "unscaled_residual_norm": last_raw_norm,
        "rhs_norm": rhs_norm,
        "relative_residual": last_raw_metric,
        "scaled_residual_norm": last_scaled_norm,
        "last_snes_function_norm": None,
        "residual_evaluation_history": residual_history,
        "complex_qr_mixing_history": mixing_history,
        "mixing_method": "complex_qr_type_ii_research",
        "mixing_metric": mixing_metric,
        "mixing_beta": beta,
        "constraint_scale_enabled": True,
        "real_coordinate_embedding": False,
        "modal_coordinate_representation": "complex128_modal_values",
        "modal_coordinate_count": modal_count,
        "modal_coordinate_extra_bytes_per_explicit_vec": 0,
        "modal_coordinate_extra_bytes_two_explicit_vecs": 0,
        "real_coordinate_subspace_violation": False,
        "constraint_condition_2": float(factor.constraint_condition),
        "constraint_lu_owner_rank": root,
        "constraint_lu_factorizations": 0,
        "constraint_lu_solve_calls": c_solves,
        "constraint_lu_borrowed": True,
        "zero_rhs_absolute_residual": rhs_norm == 0.0,
        "iterations": iterations,
        "max_iterations": max_iterations,
        "function_evaluations": function_evaluations,
        "s_evaluation_count": total_evaluations,
        "s_evaluation_limit": evaluation_limit,
        "final_validation_evaluations": final_evaluations,
        "budget_callback_skipped": False,
        "budget_callback_residual_state": None,
        "budget_reason": "S_EVALUATION_LIMIT" if budget_exhausted else None,
        "budget_exhausted": budget_exhausted,
        "anderson_history": history_limit,
        "snes_converged_reason": None,
        "callback_converged_reason": None,
        "raw_cache_iteration_mismatch": False,
        "side_action_calls": side_calls,
    }


class HybridActionModalSchurAndersonSystem:
    """Owner-factored C scaling for a borrowed nonlinear modal action."""

    def __init__(
        self,
        modal_action: HybridActionModalSchurApply,
        *,
        modal_owner: int,
        complex_qr_research: bool = False,
        raw_metric_mixing: bool = False,
        capture_modal_solve_trace: bool = False,
    ) -> None:
        if not isinstance(complex_qr_research, (bool, np.bool_)):
            raise TypeError("Complex QR research selection must be an explicit boolean.")
        if not isinstance(capture_modal_solve_trace, (bool, np.bool_)):
            raise TypeError("Modal solve trace capture must be an explicit boolean.")
        if not isinstance(raw_metric_mixing, (bool, np.bool_)):
            raise TypeError("Raw-metric Anderson selection must be an explicit boolean.")
        if raw_metric_mixing and not complex_qr_research:
            raise ValueError("Raw-metric mixing requires the complex QR research path.")
        if capture_modal_solve_trace and not complex_qr_research:
            raise ValueError(
                "Modal solve trace capture requires the complex QR research path."
            )
        self.modal_action = modal_action
        self.modal_count = int(modal_action.modal_count)
        self.complex_qr_research = bool(complex_qr_research)
        self.raw_metric_mixing = bool(raw_metric_mixing)
        self.capture_modal_solve_trace = bool(capture_modal_solve_trace)
        self.mixing_method = (
            "complex_qr_type_ii_research"
            if self.complex_qr_research
            else "petsc_snes_anderson_default"
        )
        self.mixing_metric = (
            "raw_residual" if self.raw_metric_mixing else "C_scaled_residual"
        )
        self.modal_schur = None
        self.constraint_lu_owner_rank = int(modal_owner)
        self.constraint_lu: np.ndarray | None = None
        self.constraint_pivots: np.ndarray | None = None
        self.constraint_condition = float("nan")
        self.modal_constraint_local_bytes = int(
            modal_action.modal_constraint.nbytes
        )
        self._destroyed = False
        self._solve_count = 0
        self._s_evaluation_count = 0
        self._anderson_iteration_count = 0
        self._constraint_lu_solve_calls = 0
        self._not_converged_count = 0
        self._side_action_call_count = {"bottom": 0, "top": 0}
        self._side_action_call_count_known = {"bottom": True, "top": True}
        self._last_solve: dict[str, Any] | None = None
        self._modal_solve_trace_records: list[dict[str, Any]] = []

        operator = _action_operator(modal_action.bottom_action)
        comm = operator.getComm().tompi4py()
        owner_valid = self.constraint_lu_owner_rank == comm.size - 1
        if not comm.allreduce(owner_valid, op=MPI.LAND):
            raise ValueError("The modal C LU must use the final-rank modal owner.")
        owner_result = None
        if comm.rank == self.constraint_lu_owner_rank:
            try:
                (
                    self.constraint_lu,
                    self.constraint_pivots,
                    condition,
                ) = _factor_modal_constraint(
                    modal_action.modal_constraint,
                    self.modal_count,
                )
                owner_result = (True, condition, None)
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                owner_result = (
                    False,
                    None,
                    f"C factorization rejected: {type(exc).__name__}: {exc}",
                )
        factor_ok, condition, error = comm.bcast(
            owner_result, root=self.constraint_lu_owner_rank
        )
        if not factor_ok:
            self.destroy()
            raise RuntimeError(str(error))
        self.constraint_condition = float(condition)

    @property
    def modal_constraint(self) -> np.ndarray | None:
        if self._destroyed:
            return None
        return self.modal_action.modal_constraint

    @property
    def requires_right_fgmres(self) -> bool:
        return True

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "method": (
                "bounded_C_scaled_complex_QR_Anderson_research"
                if self.complex_qr_research
                else "bounded_C_scaled_SNESANDERSON"
            ),
            "mixing_method": self.mixing_method,
            "mixing_metric": self.mixing_metric,
            "status": "destroyed" if self._destroyed else "ready",
            "modal_count": self.modal_count,
            "real_coordinate_embedding": not self.complex_qr_research,
            "modal_coordinate_representation": (
                "complex128_modal_values"
                if self.complex_qr_research
                else "real_parts_then_imag_parts_in_complex128"
            ),
            "modal_coordinate_count": (
                self.modal_count if self.complex_qr_research else 2 * self.modal_count
            ),
            "modal_coordinate_extra_bytes_per_explicit_vec": int(
                0
                if self.complex_qr_research
                else self.modal_count * np.dtype(PETSc.ScalarType).itemsize
            ),
            "modal_coordinate_extra_bytes_two_explicit_vecs": int(
                0
                if self.complex_qr_research
                else 2 * self.modal_count * np.dtype(PETSc.ScalarType).itemsize
            ),
            "modal_schur_materialized": False,
            "modal_schur_column_count": 0,
            "modal_constraint_local_bytes": self.modal_constraint_local_bytes,
            "modal_constraint_condition": float(self.constraint_condition),
            "constraint_lu_owner_rank": self.constraint_lu_owner_rank,
            "constraint_lu_factorizations": 1,
            "constraint_lu_local_bytes": int(
                0
                if self.constraint_lu is None
                else self.constraint_lu.nbytes + self.constraint_pivots.nbytes
            ),
            "constraint_lu_solve_calls": int(self._constraint_lu_solve_calls),
            "solve_count": int(self._solve_count),
            "anderson_iteration_count": int(self._anderson_iteration_count),
            "s_evaluation_count": int(self._s_evaluation_count),
            "not_converged_count": int(self._not_converged_count),
            "side_action_call_count": {
                side: (
                    int(self._side_action_call_count[side])
                    if self._side_action_call_count_known[side]
                    else None
                )
                for side in ("bottom", "top")
            },
            "last_solve": (
                None if self._last_solve is None else dict(self._last_solve)
            ),
            "destroyed": bool(self._destroyed),
        }

    def export_modal_solve_capture(
        self,
        comm: Any,
        *,
        writer_rank: int = 0,
        side_audit_path: str | None = None,
        trace_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Gather the bounded owner trace at an explicit all-rank boundary."""
        if not self.capture_modal_solve_trace:
            return None
        owner = self.constraint_lu_owner_rank
        payload = None
        traces = None
        if int(comm.rank) == owner:
            traces = (
                list(self._modal_solve_trace_records)
                if trace_records is None
                else trace_records
            )
            array_bytes = sum(trace["captured_array_bytes"] for trace in traces)
            complete = [trace["solve_id"] for trace in traces] == [1, 2] and all(
                trace["capture_complete"] for trace in traces
            )
            payload = {
                "schema": "task041.modal_inner.solve_trace_capture.v1",
                "capture_status": "complete" if complete else "incomplete",
                "capture_complete": complete,
                "capture_incomplete_reason": (
                    None
                    if complete
                    else next(
                        (
                            trace["capture_incomplete_reason"]
                            for trace in traces
                            if trace.get("capture_incomplete_reason")
                        ),
                        "two_complete_solve_traces_not_available",
                    )
                ),
                "owner_rank": int(owner),
                "writer_rank": int(writer_rank),
                "modal_count": self.modal_count,
                "array_payload_bytes": array_bytes,
                "array_payload_limit_bytes": _modal_trace_array_limit_bytes(
                    self.modal_count
                ),
                "serialized_payload_limit_bytes": _MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES,
                "serialized_payload_size_basis": "compact_utf8_json",
                "solve_count_observed": self._solve_count,
                "side_rhs_audit_path": side_audit_path,
                "traces": traces,
            }
            try:
                serialized_size = len(
                    json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                )
            except (TypeError, ValueError):
                serialized_size = _MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES + 1
                payload["capture_incomplete_reason"] = "trace_serialization_failed"
            if serialized_size > _MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES:
                payload.update(
                    capture_status="incomplete",
                    capture_complete=False,
                    capture_incomplete_reason=payload.get(
                        "capture_incomplete_reason"
                    )
                    or "serialized_payload_limit_exceeded",
                    traces=[],
                    trace_arrays_omitted=True,
                )
        try:
            gathered = comm.gather(payload, root=writer_rank)
        except BaseException:
            if int(comm.rank) == owner:
                self._modal_solve_trace_records.clear()
                if trace_records is not None:
                    trace_records.clear()
            raise
        if int(comm.rank) == writer_rank:
            result = gathered[owner] if owner < len(gathered) else None
            if result is None:
                result = {
                    "schema": "task041.modal_inner.solve_trace_capture.v1",
                    "capture_status": "incomplete",
                    "capture_complete": False,
                    "capture_incomplete_reason": "owner_payload_missing",
                    "owner_rank": int(owner),
                    "writer_rank": int(writer_rank),
                }
        else:
            result = None
        if int(comm.rank) == owner:
            self._modal_solve_trace_records.clear()
            if trace_records is not None and (
                int(comm.rank) != int(writer_rank)
                or payload is None
                or payload.get("traces") is not trace_records
            ):
                trace_records.clear()
        return result

    def take_modal_solve_trace_records(self) -> list[dict[str, Any]] | None:
        """Transfer the owner-only encoded trace list without copying it."""
        if not self.capture_modal_solve_trace:
            return None
        records = self._modal_solve_trace_records
        self._modal_solve_trace_records = []
        return records if records else None

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("On-demand modal Anderson system has been destroyed.")
        self._solve_count += 1
        trace_record = None
        if self.capture_modal_solve_trace and self._solve_count <= 2:
            comm = _action_operator(self.modal_action.bottom_action).getComm().tompi4py()
            if comm.rank == self.constraint_lu_owner_rank:
                trace_record = {
                    "solve_id": int(self._solve_count),
                    "modal_count": self.modal_count,
                    "captured_array_bytes": 0,
                    "capture_complete": True,
                    "capture_incomplete_reason": None,
                    "evaluations": [],
                    "updates": [],
                }
                self._modal_solve_trace_records.append(trace_record)
        try:
            if self.complex_qr_research:
                result = solve_action_modal_schur_anderson_complex_qr_research(
                    self.modal_action,
                    rhs,
                    _borrowed_constraint_factor=self,
                    raw_metric_mixing=self.raw_metric_mixing,
                    _capture_trace_record=trace_record,
                )
            else:
                result = solve_action_modal_schur_anderson(
                    self.modal_action,
                    rhs,
                    scale_residual_by_constraint=True,
                    real_coordinate_embedding=True,
                    max_iterations=14,
                    _borrowed_constraint_factor=self,
                )
        except BaseException:
            if trace_record is not None:
                trace_record.update(
                    capture_complete=False,
                    capture_incomplete_reason="solver_raised_before_trace_completion",
                )
                if trace_record["evaluations"]:
                    trace_record["evaluations"][-1]["side_actions"] = {
                        side: _modal_trace_side_apply_record(action)
                        for side, action in (
                            ("bottom", self.modal_action.bottom_action),
                            ("top", self.modal_action.top_action),
                        )
                    }
            raise
        side_calls = dict(result["side_action_calls"])
        for side in ("bottom", "top"):
            delta = side_calls.get(side)
            if delta is None:
                self._side_action_call_count_known[side] = False
            elif self._side_action_call_count_known[side]:
                self._side_action_call_count[side] += int(delta)
        self._s_evaluation_count += int(result["s_evaluation_count"])
        self._anderson_iteration_count += int(result["iterations"])
        self._constraint_lu_solve_calls += int(result["constraint_lu_solve_calls"])
        summary_keys = (
            "status",
            "stop_reason",
            "anderson_history",
            "unscaled_residual_norm",
            "rhs_norm",
            "relative_residual",
            "max_iterations",
            "iterations",
            "function_evaluations",
            "final_validation_evaluations",
            "s_evaluation_count",
            "constraint_lu_factorizations",
            "constraint_lu_solve_calls",
            "constraint_lu_borrowed",
            "zero_rhs_absolute_residual",
            "target_reached",
            "convergence_callback_target_reached",
            "final_unscaled_target_reached",
            "invalid_failure",
            "budget_reason",
            "budget_callback_skipped",
            "snes_converged_reason",
            "callback_converged_reason",
            "budget_exhausted",
            "side_action_calls",
            "residual_evaluation_history",
            "real_coordinate_embedding",
            "modal_coordinate_representation",
            "modal_coordinate_count",
            "modal_coordinate_extra_bytes_per_explicit_vec",
            "modal_coordinate_extra_bytes_two_explicit_vecs",
            "real_coordinate_subspace_violation",
            "mixing_method",
            "mixing_metric",
            "mixing_beta",
            "complex_qr_mixing_history",
        )
        self._last_solve = {
            key: result[key] for key in summary_keys if key in result
        }
        if self.capture_modal_solve_trace:
            self._last_solve["residual_evaluation_history"] = [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"m", "raw", "scaled", "side_actions", "capture_complete"}
                }
                for row in result["residual_evaluation_history"]
            ]
        solution = result.pop("solution")
        if result["status"] != "converged":
            self._not_converged_count += 1
            message = (
                "Modal Anderson inner solve did not converge: "
                f"stop_reason={result['stop_reason']}, "
                f"raw_residual_norm={result['unscaled_residual_norm']:.17g}, "
                f"relative_residual={result['relative_residual']:.17g}, "
                f"iterations={result['iterations']}, "
                f"S_evaluations={result['s_evaluation_count']}, "
                f"side_action_calls={side_calls}"
            )
            del solution
            raise RuntimeError(message)
        return np.asarray(solution, dtype=np.complex128)

    def destroy(self) -> None:
        self._modal_solve_trace_records.clear()
        if self._destroyed:
            return
        self.constraint_lu = None
        self.constraint_pivots = None
        modal_action = self.modal_action
        modal_action.destroy()
        self.modal_action = None
        self._destroyed = True


def _build_action_modal_contribution(
    side: str,
    coupling: HybridInternalModeCoupling,
    action: Any,
    modal_count: int,
    columns: Sequence[int] | None = None,
    *,
    batch_size: int | None = None,
    progress_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> np.ndarray:
    operator = _action_operator(action)
    projection = (
        coupling.bottom.projection if side == "bottom" else coupling.top.projection
    )
    selected_columns = (
        tuple(range(2 * modal_count))
        if columns is None
        else tuple(int(i) for i in columns)
    )
    contribution = np.zeros(
        (2 * modal_count, len(selected_columns)), dtype=np.complex128
    )
    row_slice = (
        slice(0, modal_count)
        if side == "bottom"
        else slice(modal_count, 2 * modal_count)
    )
    other_slice = (
        slice(modal_count, 2 * modal_count)
        if side == "bottom"
        else slice(0, modal_count)
    )
    if batch_size is not None:
        batch_size = int(batch_size)
        if batch_size != 32:
            raise ValueError("Modal batch size is fixed to 32")
        if not hasattr(action, "apply_many"):
            raise TypeError("Modal batching requires an action apply_many API")
        comm = operator.getComm().tompi4py()
        row_first, row_last = map(int, operator.getOwnershipRange())
        global_rows = int(operator.getSize()[0])
        batch_total = (len(selected_columns) + batch_size - 1) // batch_size
        started = time.perf_counter()
        batch_durations: list[tuple[float, int]] = []
        for batch_number, batch_start in enumerate(
            range(0, len(selected_columns), batch_size), start=1
        ):
            batch_columns = selected_columns[batch_start : batch_start + batch_size]
            batch_width = len(batch_columns)
            batch_started = time.perf_counter()
            before_diagnostics = _action_diagnostics(action)
            before_mat_solve_calls = int(
                before_diagnostics.get("mat_solve_call_count", 0)
            )
            if progress_callback is not None:
                progress_callback(
                    "modal_batch_begin",
                    {
                        "side": side,
                        "stage": "modal_action",
                        "index": batch_start,
                        "total": len(selected_columns),
                        "batch_total": batch_total,
                        "batch_index": batch_number,
                        "width": batch_width,
                        "logical_completed": batch_start,
                        "mat_solve_calls": before_mat_solve_calls,
                        "stage_wall_seconds": batch_started - started,
                    },
                )
            right_hand_sides = solved = None
            try:
                right_hand_sides = PETSc.Mat().createDense(
                    size=((row_last - row_first, global_rows), batch_width),
                    comm=comm,
                )
                right_hand_sides.setUp()
                local_rhs = right_hand_sides.getDenseArray()
                for offset, column in enumerate(batch_columns):
                    modal = np.zeros(2 * modal_count, dtype=np.complex128)
                    modal[column] = 1.0
                    traction = modal_coupling_action(side, coupling, modal)
                    try:
                        if tuple(map(int, traction.getOwnershipRange())) != (
                            row_first,
                            row_last,
                        ):
                            raise ValueError(
                                "Modal batch traction ownership does not match factor"
                            )
                        local_rhs[:, offset] = traction.getArray(readonly=True)
                    finally:
                        traction.destroy()
                right_hand_sides.assemble()
                solved = right_hand_sides.duplicate(copy=False)
                action.apply_many(right_hand_sides, solved)
                for offset in range(batch_width):
                    response = solved.getColumnVector(offset)
                    projected = projection.createVecLeft()
                    try:
                        projection.mult(response, projected)
                        values = _replicated_modal_values(projected)
                        contribution[row_slice, batch_start + offset] = values
                        contribution[other_slice, batch_start + offset] = 0.0
                    finally:
                        projected.destroy()
                        response.destroy()
            finally:
                if solved is not None:
                    solved.destroy()
                if right_hand_sides is not None:
                    right_hand_sides.destroy()
            batch_elapsed = float(
                comm.allreduce(time.perf_counter() - batch_started, op=MPI.MAX)
            )
            batch_durations.append((batch_elapsed, batch_width))
            after_diagnostics = _action_diagnostics(action)
            after_mat_solve_calls = int(
                after_diagnostics.get("mat_solve_call_count", 0)
            )
            detail: dict[str, Any] = {
                "side": side,
                "stage": "modal_action",
                "index": batch_start,
                "total": len(selected_columns),
                "batch_total": batch_total,
                "batch_index": batch_number,
                "width": batch_width,
                "logical_completed": batch_start + batch_width,
                "mat_solve_calls": after_mat_solve_calls,
                "mat_solve_calls_delta": after_mat_solve_calls
                - before_mat_solve_calls,
                "stage_wall_seconds": time.perf_counter() - started,
            }
            if len(batch_durations) == 2:
                observed = batch_durations[:2]
                completed = sum(width for _, width in observed)
                elapsed = sum(duration for duration, _ in observed)
                throughput = completed / max(elapsed, _TINY)
                remaining = len(selected_columns) - (batch_start + batch_width)
                upper_per_column = max(
                    duration / width for duration, width in observed
                )
                detail.update(
                    {
                        "throughput_logical_per_second": throughput,
                        "eta_seconds_central": remaining / max(throughput, _TINY),
                        "eta_seconds_upper": remaining * upper_per_column,
                        "eta_basis": "first_two_completed_batches",
                    }
                )
            if progress_callback is not None:
                progress_callback("modal_batch_end", detail)
        return contribution

    for local_column, column in enumerate(selected_columns):
        modal = np.zeros(2 * modal_count, dtype=np.complex128)
        modal[column] = 1.0
        traction = modal_coupling_action(side, coupling, modal)
        response = operator.createVecLeft()
        projected = projection.createVecLeft()
        try:
            action.apply(traction, response)
            projection.mult(response, projected)
            contribution[row_slice, local_column] = _replicated_modal_values(projected)
            contribution[other_slice, local_column] = 0.0
        finally:
            projected.destroy()
            response.destroy()
            traction.destroy()
    return contribution


def _sampled_modal_column_contract(
    sampled_columns: Sequence[int] | None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None,
    sampled_column_contract_sha256: str | None,
    internal_count: int,
    modal_count: int,
) -> dict[str, Any] | None:
    if sampled_columns is None:
        if (
            sampled_column_roles is not None
            or sampled_column_contract_sha256 is not None
        ):
            raise ValueError("Sampled modal roles/hash require sampled columns.")
        return None
    if sampled_column_roles is None or sampled_column_contract_sha256 is None:
        raise ValueError("Sampled modal columns require roles and a contract hash.")
    columns = [int(column) for column in sampled_columns]
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("Sampled modal columns must be non-empty and unique.")
    if any(column < 0 or column >= internal_count for column in columns):
        raise ValueError("Sampled modal column is outside the internal Schur range.")
    expected_role_keys = {str(column) for column in columns}
    if set(sampled_column_roles) != expected_role_keys:
        raise ValueError("Sampled modal roles must cover exactly the frozen columns.")
    roles = {
        str(column): [str(role) for role in sampled_column_roles[str(column)]]
        for column in columns
    }
    contract = {
        "columns": columns,
        "mode_count_per_direction": int(modal_count),
        "roles": roles,
    }
    actual_hash = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual_hash != str(sampled_column_contract_sha256):
        raise ValueError(
            "Sampled modal column contract hash does not match the frozen contract."
        )
    return {**contract, "sha256": actual_hash}


def _compare_modal_sample_repeat(
    first: np.ndarray,
    second: np.ndarray,
    *,
    finite_reducer: Callable[[bool], bool] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply the existing finite, aggregate, and per-column sample repeat gate."""

    difference = first - second
    finite = bool(
        np.all(np.isfinite(first))
        and np.all(np.isfinite(second))
        and np.all(np.isfinite(difference))
    )
    if finite_reducer is not None:
        finite = bool(finite_reducer(finite))
    reference_norm = float(np.linalg.norm(first))
    difference_norm = float(np.linalg.norm(difference))
    column_absolute = [
        float(np.linalg.norm(difference[:, index]))
        for index in range(first.shape[1])
    ]
    column_relative = [
        column_absolute[index]
        / max(float(np.linalg.norm(first[:, index])), _TINY)
        for index in range(first.shape[1])
    ]
    relative_error = difference_norm / max(reference_norm, _TINY)
    limit = 1.0e-10
    diagnostics = {
        "absolute_difference": difference_norm,
        "reference_norm": reference_norm,
        "difference_norm": difference_norm,
        "relative_error": relative_error,
        "max_abs": float(np.max(np.abs(difference))),
        "max_column_absolute_difference": max(column_absolute),
        "max_column_relative_error": max(column_relative),
        "finite": finite,
        "limit": limit,
        "pass": bool(
            finite
            and relative_error <= limit
            and max(column_relative) <= limit
        ),
    }
    return difference, diagnostics


def build_hybrid_action_modal_schur(
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
    *,
    matrix_repeat_tolerance: float = 1.0e-13,
    sampled_columns: Sequence[int] | None = None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None = None,
    sampled_column_contract_sha256: str | None = None,
    modal_batch_size: int | None = None,
    early_sample_first: bool = False,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> HybridActionModalSchurSystem:
    """Build the modal Schur, optionally with one frozen sampled reconstruction."""

    if (
        not np.isfinite(float(matrix_repeat_tolerance))
        or float(matrix_repeat_tolerance) <= 0.0
    ):
        raise ValueError("Modal-Schur repeat tolerance must be finite and positive.")
    if modal_batch_size is not None:
        modal_batch_size = int(modal_batch_size)
        if modal_batch_size != 32:
            raise ValueError("Modal batch size is fixed to 32")
    if early_sample_first:
        if sampled_columns is None or modal_batch_size != 32:
            raise ValueError(
                "Early modal sampling requires frozen columns and batch size 32"
            )
        if float(matrix_repeat_tolerance) != 1.0e-10:
            raise ValueError("Early modal sampling requires the fixed 1e-10 Gate")
    modal_count = int(coupling.mode_count_per_direction)
    internal_count = 2 * modal_count
    sampled_contract = _sampled_modal_column_contract(
        sampled_columns,
        sampled_column_roles,
        sampled_column_contract_sha256,
        internal_count,
        modal_count,
    )
    constraint = np.asarray(
        internal_modal_constraint_matrix(coupling), dtype=np.complex128
    )
    before = {
        "bottom": int(_action_diagnostics(bottom_action).get("apply_count", 0)),
        "top": int(_action_diagnostics(top_action).get("apply_count", 0)),
    }

    def total_mat_solve_calls() -> int:
        return sum(
            int(_action_diagnostics(action).get("mat_solve_call_count", 0))
            for action in (bottom_action, top_action)
        )

    def build_contribution(
        side: str,
        action: Any,
        columns: Sequence[int] | None = None,
    ) -> np.ndarray:
        if modal_batch_size is None:
            if columns is None:
                return _build_action_modal_contribution(
                    side, coupling, action, modal_count
                )
            return _build_action_modal_contribution(
                side, coupling, action, modal_count, columns=columns
            )
        return _build_action_modal_contribution(
            side,
            coupling,
            action,
            modal_count,
            columns=columns,
            batch_size=modal_batch_size,
            progress_callback=marker_callback,
        )

    sampled_column_errors: list[float] = []
    early_sample_diagnostics: dict[str, Any] | None = None
    full_sample_diagnostics: dict[str, Any] | None = None
    sampled_reconstruction = None
    if sampled_contract is None:
        first = constraint.copy()
        first -= build_contribution("bottom", bottom_action)
        first -= build_contribution("top", top_action)
        second = constraint.copy()
        second -= build_contribution("bottom", bottom_action)
        second -= build_contribution("top", top_action)
    elif early_sample_first:
        sampled = np.asarray(sampled_contract["columns"], dtype=np.int64)
        sample_started = time.perf_counter()
        if marker_callback is not None:
            marker_callback(
                "modal_sample_begin",
                {
                    "side": "both",
                    "stage": "modal_sample_repeat",
                    "index": 0,
                    "total": len(sampled),
                    "width": len(sampled),
                    "logical_completed": 0,
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": 0.0,
                },
            )
        sampled_first = constraint[:, sampled].copy()
        sampled_first -= build_contribution(
            "bottom", bottom_action, columns=sampled
        )
        sampled_first -= build_contribution("top", top_action, columns=sampled)
        sampled_second = constraint[:, sampled].copy()
        sampled_second -= build_contribution(
            "bottom", bottom_action, columns=sampled
        )
        sampled_second -= build_contribution("top", top_action, columns=sampled)
        early_difference, repeat_metrics = _compare_modal_sample_repeat(
            sampled_first, sampled_second
        )
        early_reference_norm = repeat_metrics["reference_norm"]
        early_difference_norm = repeat_metrics["difference_norm"]
        early_finite = repeat_metrics["finite"]
        early_sample_diagnostics = {
            **repeat_metrics,
            "mode": "two_batched_sample_builds_before_full_build",
        }
        if not early_sample_diagnostics["pass"]:
            raise ValueError(
                "Early sampled modal repeat Gate failed: "
                f"absolute={early_difference_norm:.6e}, "
                f"reference_norm={early_reference_norm:.6e}, "
                f"relative={early_sample_diagnostics['relative_error']:.6e}, "
                f"max_column={early_sample_diagnostics['max_column_relative_error']:.6e}, "
                f"finite={early_finite}, limit=1.000000e-10"
            )
        if marker_callback is not None:
            marker_callback(
                "modal_sample_ready",
                {
                    "side": "both",
                    "stage": "modal_sample_repeat",
                    "index": len(sampled),
                    "total": len(sampled),
                    "width": len(sampled),
                    "logical_completed": len(sampled),
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": time.perf_counter() - sample_started,
                    **early_sample_diagnostics,
                },
            )
        if marker_callback is not None:
            full_started = time.perf_counter()
            marker_callback(
                "modal_full_build_begin",
                {
                    "side": "both",
                    "stage": "modal_full_build",
                    "index": 0,
                    "total": internal_count,
                    "width": modal_batch_size,
                    "logical_completed": 0,
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": 0.0,
                },
            )
        first = constraint.copy()
        first -= build_contribution("bottom", bottom_action)
        first -= build_contribution("top", top_action)
        second = None
        sampled_reconstruction = sampled_first
        full_difference = first[:, sampled] - sampled_first
        full_reference_norm = float(np.linalg.norm(sampled_first))
        full_difference_norm = float(np.linalg.norm(full_difference))
        full_column_absolute = [
            float(np.linalg.norm(full_difference[:, index]))
            for index in range(len(sampled))
        ]
        sampled_column_errors = [
            float(
                full_column_absolute[index]
                / max(float(np.linalg.norm(sampled_first[:, index])), _TINY)
            )
            for index in range(len(sampled))
        ]
        full_sample_finite = bool(
            np.all(np.isfinite(first[:, sampled]))
            and np.all(np.isfinite(sampled_first))
            and np.all(np.isfinite(full_difference))
        )
        full_sample_diagnostics = {
            "absolute_difference": full_difference_norm,
            "reference_norm": full_reference_norm,
            "difference_norm": full_difference_norm,
            "relative_error": full_difference_norm
            / max(full_reference_norm, _TINY),
            "max_abs": float(np.max(np.abs(full_difference))),
            "max_column_absolute_difference": max(full_column_absolute),
            "max_column_relative_error": max(sampled_column_errors),
            "finite": full_sample_finite,
            "limit": 1.0e-10,
            "pass": bool(
                full_sample_finite
                and full_difference_norm / max(full_reference_norm, _TINY)
                <= 1.0e-10
                and max(sampled_column_errors) <= 1.0e-10
            ),
            "mode": "full_build_against_first_sample_without_third_action",
        }
        if not full_sample_diagnostics["pass"]:
            raise ValueError(
                "Full modal build differs from early sample: "
                f"absolute={full_difference_norm:.6e}, "
                f"reference_norm={full_reference_norm:.6e}, "
                f"relative={full_sample_diagnostics['relative_error']:.6e}, "
                f"max_column={full_sample_diagnostics['max_column_relative_error']:.6e}, "
                f"finite={full_sample_finite}, limit=1.000000e-10"
            )
        if marker_callback is not None:
            marker_callback(
                "modal_full_build_ready",
                {
                    "side": "both",
                    "stage": "modal_full_build",
                    "index": internal_count,
                    "total": internal_count,
                    "width": modal_batch_size,
                    "logical_completed": internal_count,
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": time.perf_counter() - full_started,
                },
            )
        matrix_difference = early_difference
        matrix_reference_norm = early_reference_norm
        matrix_difference_norm = early_difference_norm
    else:
        first = constraint.copy()
        first -= build_contribution("bottom", bottom_action)
        first -= build_contribution("top", top_action)
        second = None
        sampled = np.asarray(sampled_contract["columns"], dtype=np.int64)
        sampled_reconstruction = constraint[:, sampled].copy()
        sampled_reconstruction -= build_contribution(
            "bottom", bottom_action, columns=sampled
        )
        sampled_reconstruction -= build_contribution(
            "top", top_action, columns=sampled
        )
    after = {
        "bottom": int(_action_diagnostics(bottom_action).get("apply_count", 0)),
        "top": int(_action_diagnostics(top_action).get("apply_count", 0)),
    }
    build_apply_count = {side: after[side] - before[side] for side in ("bottom", "top")}
    expected = (
        internal_count + 2 * len(sampled_contract["columns"])
        if early_sample_first
        else (
            internal_count + len(sampled_contract["columns"])
            if sampled_contract is not None
            else 2 * internal_count
        )
    )
    if any(value != expected for value in build_apply_count.values()):
        raise RuntimeError(
            "Action modal Schur apply count does not match the selected build mode: "
            f"expected={expected}, actual={build_apply_count}."
        )
    expected_shape = (internal_count, internal_count)
    matrices = (constraint, first) if second is None else (constraint, first, second)
    for matrix in matrices:
        if matrix.shape != expected_shape or matrix.dtype != np.dtype(np.complex128):
            raise ValueError("Action modal Schur has an unexpected shape or dtype.")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Action modal Schur contains non-finite values.")
    if sampled_contract is None:
        matrix_difference = first - second
        matrix_reference_norm = float(np.linalg.norm(first))
        matrix_difference_norm = float(np.linalg.norm(matrix_difference))
        sampled_column_errors = []
    elif not early_sample_first:
        reference = first[:, np.asarray(sampled_contract["columns"], dtype=np.int64)]
        matrix_difference = reference - sampled_reconstruction
        matrix_reference_norm = float(np.linalg.norm(reference))
        matrix_difference_norm = float(np.linalg.norm(matrix_difference))
        sampled_column_errors = [
            float(
                np.linalg.norm(sampled_reconstruction[:, index] - reference[:, index])
                / max(float(np.linalg.norm(reference[:, index])), _TINY)
            )
            for index in range(len(sampled_contract["columns"]))
        ]
    max_column_relative_error = (
        float(early_sample_diagnostics["max_column_relative_error"])
        if early_sample_first
        else max(sampled_column_errors, default=0.0)
    )
    matrix_repeat_error = matrix_difference_norm / max(matrix_reference_norm, _TINY)
    matrix_repeat_finite = bool(np.all(np.isfinite(matrix_difference)))
    matrix_repeat_diagnostics = {
        "relative_error": float(matrix_repeat_error),
        "limit": float(matrix_repeat_tolerance),
        "reference_norm": matrix_reference_norm,
        "difference_norm": matrix_difference_norm,
        "absolute_difference": matrix_difference_norm,
        "max_abs": float(np.max(np.abs(matrix_difference))),
        "max_column_relative_error": float(max_column_relative_error),
        "finite": matrix_repeat_finite,
        "mode": (
            "double_full_build"
            if sampled_contract is None
            else (
                "early_sample_before_full_build"
                if early_sample_first
                else "single_full_build_sampled_reconstruction"
            )
        ),
        "pass": bool(
            matrix_repeat_finite
            and np.isfinite(matrix_repeat_error)
            and matrix_repeat_error <= float(matrix_repeat_tolerance)
            and max_column_relative_error <= float(matrix_repeat_tolerance)
        ),
    }
    if early_sample_first:
        matrix_repeat_diagnostics["early_sample"] = dict(early_sample_diagnostics)
        matrix_repeat_diagnostics["full_vs_first_sample"] = dict(
            full_sample_diagnostics
        )
    if not matrix_repeat_diagnostics["pass"]:
        raise ValueError(
            "Action modal Schur repeat error exceeds tolerance: "
            f"actual={matrix_repeat_error:.6e}, "
            f"limit={float(matrix_repeat_tolerance):.6e}, "
            f"reference_norm={matrix_reference_norm:.6e}, "
            f"difference_norm={matrix_difference_norm:.6e}, "
            f"max_abs={matrix_repeat_diagnostics['max_abs']:.6e}, "
            f"max_column={max_column_relative_error:.6e}."
        )
    singular_values = np.linalg.svd(first, compute_uv=False)
    rank_scale = (
        np.finfo(float).eps * max(first.shape) * float(singular_values[0])
        if singular_values.size
        else 0.0
    )
    rank = int(np.count_nonzero(singular_values > rank_scale))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if (
            singular_values.size
            and np.all(np.isfinite(singular_values))
            and singular_values[-1] > 0.0
        )
        else float("inf")
    )
    if (
        rank != internal_count
        or not np.isfinite(condition)
        or condition * np.finfo(np.float64).eps >= 1.0
    ):
        raise ValueError("Action modal Schur is not a finite full-rank system.")
    lu, pivots = lu_factor(first, check_finite=True)
    if not np.all(np.isfinite(lu)) or not np.all(np.isfinite(pivots)):
        raise ValueError("Action modal Schur LU contains non-finite values.")
    test_rhs = np.arange(1, internal_count + 1, dtype=np.complex128)
    first_solution = lu_solve((lu, pivots), test_rhs, check_finite=True)
    second_solution = lu_solve((lu, pivots), test_rhs, check_finite=True)
    lu_difference = first_solution - second_solution
    lu_reference_norm = float(np.linalg.norm(first_solution))
    lu_difference_norm = float(np.linalg.norm(lu_difference))
    lu_repeat_solve_error = lu_difference_norm / max(lu_reference_norm, _TINY)
    lu_repeat_diagnostics = {
        "relative_error": float(lu_repeat_solve_error),
        "limit": 1.0e-13,
        "reference_norm": lu_reference_norm,
        "difference_norm": lu_difference_norm,
        "max_abs": float(np.max(np.abs(lu_difference))),
        "pass": bool(
            np.isfinite(lu_repeat_solve_error) and lu_repeat_solve_error <= 1.0e-13
        ),
    }
    if not lu_repeat_diagnostics["pass"]:
        raise ValueError(
            "Action modal Schur LU repeat error exceeds tolerance: "
            f"actual={lu_repeat_solve_error:.6e}, "
            "limit=1.000000e-13, "
            f"reference_norm={lu_reference_norm:.6e}, "
            f"difference_norm={lu_difference_norm:.6e}, "
            f"max_abs={lu_repeat_diagnostics['max_abs']:.6e}."
        )
    return HybridActionModalSchurSystem(
        modal_schur=first,
        modal_constraint=constraint,
        lu=np.asarray(lu, dtype=np.complex128),
        pivots=np.asarray(pivots, dtype=np.int32),
        rank=rank,
        condition=condition,
        matrix_repeat_error=matrix_repeat_error,
        lu_repeat_solve_error=lu_repeat_solve_error,
        build_apply_count=build_apply_count,
        repeat_diagnostics={
            "matrix": matrix_repeat_diagnostics,
            "lu_solve": lu_repeat_diagnostics,
        },
        sampled_column_diagnostics={
            "single_build": sampled_contract is not None,
            "columns": []
            if sampled_contract is None
            else list(sampled_contract["columns"]),
            "roles": {}
            if sampled_contract is None
            else dict(sampled_contract["roles"]),
            "contract_sha256": None
            if sampled_contract is None
            else sampled_contract["sha256"],
            "early_sample_first": bool(early_sample_first),
            "modal_batch_size": modal_batch_size,
            "full_build_apply_count": {
                "bottom": internal_count,
                "top": internal_count,
            },
            "sample_build_apply_count": {
                "bottom": 0
                if sampled_contract is None
                else (
                    2 * len(sampled_contract["columns"])
                    if early_sample_first
                    else len(sampled_contract["columns"])
                ),
                "top": 0
                if sampled_contract is None
                else (
                    2 * len(sampled_contract["columns"])
                    if early_sample_first
                    else len(sampled_contract["columns"])
                ),
            },
            "column_relative_errors": sampled_column_errors,
        },
        batch_diagnostics={
            "enabled": modal_batch_size is not None,
            "batch_size": modal_batch_size,
            "early_sample_first": bool(early_sample_first),
            "early_sample": (
                None
                if early_sample_diagnostics is None
                else dict(early_sample_diagnostics)
            ),
            "full_vs_first_sample": (
                None
                if full_sample_diagnostics is None
                else dict(full_sample_diagnostics)
            ),
        },
    )


class HybridBlockLduPreconditioner:
    """Right block-LDU action with borrowed side actions and no owned factors."""

    def __init__(
        self,
        layout: HybridAugmentedLayout,
        bottom_system: Any,
        top_system: Any,
        coupling: HybridInternalModeCoupling,
        bottom_action: Any,
        top_action: Any,
        action_modal_schur_system: (
            HybridActionModalSchurSystem
            | HybridActionModalSchurAndersonSystem
            | _FixedH6ModalGmresResearchBundle
            | Task041V13ConsistentModalSurrogateSystem
        ),
        research_inventory: dict[str, Any] | None = None,
        dynamic_side_inventory: bool = False,
    ) -> None:
        self.layout = layout
        self.bottom_system = bottom_system
        self.top_system = top_system
        self.coupling = coupling
        self.bottom_action = bottom_action
        self.top_action = top_action
        self.action_modal_schur_system = action_modal_schur_system
        self._research_inventory = (
            None if research_inventory is None else dict(research_inventory)
        )
        self._dynamic_side_inventory = bool(dynamic_side_inventory)
        self._fixed_h6_pc_side_apply_counts = (
            {
                side: {"first": 0, "delta": 0}
                for side in ("bottom", "top")
            }
            if isinstance(
                action_modal_schur_system, _FixedH6ModalGmresResearchBundle
            )
            else None
        )
        self._v13_pc_side_apply_counts = (
            {
                side: {"first": 0, "delta": 0}
                for side in ("bottom", "top")
            }
            if isinstance(
                action_modal_schur_system,
                Task041V13ConsistentModalSurrogateSystem,
            )
            else None
        )
        self._v13_side_operation_baseline = None
        if self._v13_pc_side_apply_counts is not None:
            recorded_baseline = getattr(
                action_modal_schur_system,
                "side_operation_baseline",
                None,
            )
            self._v13_side_operation_baseline = (
                {
                    side: dict(counts)
                    for side, counts in recorded_baseline.items()
                }
                if isinstance(recorded_baseline, Mapping)
                else {
                    "bottom": _v13_side_operation_counts(bottom_action),
                    "top": _v13_side_operation_counts(top_action),
                }
            )
        self.modal_schur = getattr(action_modal_schur_system, "modal_schur", None)
        self.modal_count = int(action_modal_schur_system.modal_count)
        self.defer_action_modal_schur_release = False
        self._modal_solve_trace_handoff: list[dict[str, Any]] | None = None
        self._action_modal_schur_released = False
        self._destroyed = False
        self._v13_original_operator = None
        self._v13_original_operator_action = None
        self._v13_original_modal_row_callback = None
        self.mode_count = int(coupling.mode_count_per_direction)
        self._bottom_rhs = bottom_system.A.createVecRight()
        self._top_rhs = top_system.A.createVecRight()
        self._bottom_first = bottom_system.A.createVecLeft()
        self._top_first = top_system.A.createVecLeft()
        self._bottom_delta = bottom_system.A.createVecLeft()
        self._top_delta = top_system.A.createVecLeft()
        self._bottom_projection = coupling.bottom.projection.createVecLeft()
        self._top_projection = coupling.top.projection.createVecLeft()
        self._bottom_coupling = bottom_system.A.createVecLeft()
        self._top_coupling = top_system.A.createVecLeft()
        self._bottom_positive_source = (
            coupling.bottom.positive_traction.createVecRight()
        )
        self._bottom_negative_source = (
            coupling.bottom.negative_traction.createVecRight()
        )
        self._top_positive_source = coupling.top.positive_traction.createVecRight()
        self._top_negative_source = coupling.top.negative_traction.createVecRight()
        self._bottom_positive_target = coupling.bottom.positive_traction.createVecLeft()
        self._bottom_negative_target = coupling.bottom.negative_traction.createVecLeft()
        self._top_positive_target = coupling.top.positive_traction.createVecLeft()
        self._top_negative_target = coupling.top.negative_traction.createVecLeft()
        self._modal_rhs = np.empty(2 * self.mode_count, dtype=np.complex128)
        self._modal_solution = np.empty_like(self._modal_rhs)
        self._pc_apply_attempt_count = 0
        self._pc_apply_count = 0
        self._pc_apply_seconds = 0.0
        self._current_pc_apply_evidence: dict[str, Any] | None = None
        self._check_layouts()

    @property
    def modal_constraint(self) -> np.ndarray:
        constraint = self.action_modal_schur_system.modal_constraint
        if constraint is None:
            raise RuntimeError("Modal constraint was released before the LDU context.")
        return constraint

    @property
    def requires_right_fgmres(self) -> bool:
        return bool(
            getattr(self.action_modal_schur_system, "requires_right_fgmres", False)
        )

    @property
    def direct_factor_count(self) -> int:
        if isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        ):
            return sum(
                _direct_factor_count(
                    dict(action._side_inverse.diagnostics)
                )
                for action in (self.bottom_action, self.top_action)
            )
        return _direct_factor_count(
            _action_diagnostics(self.bottom_action)
        ) + _direct_factor_count(_action_diagnostics(self.top_action))

    @property
    def factors_released(self) -> bool:
        return False

    @property
    def inventory(self) -> dict[str, Any]:
        bottom = _action_diagnostics(self.bottom_action)
        top = _action_diagnostics(self.top_action)
        bottom_direct = _direct_factor_count(bottom)
        top_direct = _direct_factor_count(top)
        bottom_ilu = int(
            bottom.get(
                "base_factor_count",
                bottom.get("ilu_factor_count", bottom.get("factor_count", 0)),
            )
        )
        top_ilu = int(
            top.get(
                "base_factor_count",
                top.get("ilu_factor_count", top.get("factor_count", 0)),
            )
        )
        on_demand_modal = isinstance(
            self.action_modal_schur_system, HybridActionModalSchurAndersonSystem
        )
        fixed_h6_modal = isinstance(
            self.action_modal_schur_system, _FixedH6ModalGmresResearchBundle
        )
        v13_modal = isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        )
        nonmaterialized_modal = on_demand_modal or fixed_h6_modal
        v13_condition_unmeasured = (
            v13_modal and self.action_modal_schur_system.condition is None
        )
        system_diagnostics = self.action_modal_schur_system.diagnostics
        result = {
            "global_A_materialized": False,
            "direct_factor_count": bottom_direct + top_direct,
            "borrowed_direct_factor_count": bottom_direct + top_direct,
            "borrowed_ilu_factor_count": bottom_ilu + top_ilu,
            "pc_owned_local_factor_count": int(
                v13_modal
                and self.action_modal_schur_system.rank
                == self.action_modal_schur_system.modal_owner
                and self.action_modal_schur_system.lu is not None
            ),
            "bottom_direct_factor_count": bottom_direct,
            "top_direct_factor_count": top_direct,
            "bottom_ilu_factor_count": bottom_ilu,
            "top_ilu_factor_count": top_ilu,
            "bottom_action_apply_count": int(bottom.get("apply_count", 0)),
            "top_action_apply_count": int(top.get("apply_count", 0)),
            "pc_apply_count": int(self._pc_apply_count),
            "pc_apply_attempt_count": int(self._pc_apply_attempt_count),
            "pc_apply_seconds": float(self._pc_apply_seconds),
            "borrowed_side_actions": True,
            "modal_block_name": (
                "on_demand_nonlinear_modal_inner"
                if on_demand_modal
                else (
                    "fixed_h6_surrogate_on_demand_modal_gmres"
                    if system_diagnostics.get("method")
                    == "fixed_h6_modal_gmres_research"
                    else "fixed_physical_balh_once_on_demand_modal_gmres"
                )
                if fixed_h6_modal
                else TASK041_V13_CONSISTENT_MODAL_POLICY_ID
                if v13_modal
                else "approximate_action_schur"
            ),
            "modal_block_condition": (
                None
                if nonmaterialized_modal or v13_condition_unmeasured
                else float(self.action_modal_schur_system.condition)
            ),
            "modal_block_condition_status": (
                "not_measured"
                if fixed_h6_modal or v13_modal
                else "measured"
                if not on_demand_modal
                else None
            ),
            "modal_schur": None if nonmaterialized_modal else system_diagnostics,
            "action_modal_schur_released": bool(self._action_modal_schur_released),
            "destroyed": bool(self._destroyed),
        }
        if on_demand_modal:
            result.update(
                {
                    "modal_count": int(self.modal_count),
                    "modal_schur_materialized": False,
                    "modal_schur_storage_bytes": 0,
                    "modal_inner_solver": system_diagnostics,
                    "modal_constraint_condition": float(
                        self.action_modal_schur_system.constraint_condition
                    ),
                    "modal_constraint_local_bytes": int(
                        self.action_modal_schur_system.modal_constraint_local_bytes
                    ),
                }
            )
        if fixed_h6_modal:
            selected_method = system_diagnostics.get(
                "method", "fixed_h6_modal_gmres_research"
            )
            common_modal_fields = {
                "modal_count": int(self.modal_count),
                "modal_schur_scope": "not_materialized",
                "modal_schur_materialized": False,
                "modal_schur_column_count": 0,
                "modal_schur_storage_bytes": 0,
                "modal_schur_condition": "not_measured",
                "modal_inner_solver": system_diagnostics,
                "modal_constraint_condition": float(
                    self.action_modal_schur_system.constraint_condition
                ),
                "modal_constraint_local_bytes": int(
                    self.action_modal_schur_system.modal_constraint_local_bytes
                ),
            }
            side_apply_counts = {
                side: dict(counts)
                for side, counts in self._fixed_h6_pc_side_apply_counts.items()
            }
            if selected_method == "fixed_h6_modal_gmres_research":
                common_modal_fields.update(
                    {
                        "fixed_h6_modal_solver": system_diagnostics,
                        "fixed_h6_pc_side_apply_counts": side_apply_counts,
                        "fixed_h6_pc_side_apply_count_scope": (
                            "successful direct side apply calls; per-rank replicated"
                        ),
                        "side_h6_callback_counts": {
                            "bottom": int(bottom.get("counts", {}).get("H6", 0)),
                            "top": int(top.get("counts", {}).get("H6", 0)),
                        },
                    }
                )
                apply_call_key = "fixed_h6_modal_apply_calls"
                matrix_call_key = "fixed_h6_modal_matrix_mult_calls"
                setup_side_count_key = "fixed_h6_side_counts"
                whole_run_key = "fixed_h6_whole_run_work"
            else:
                common_modal_fields.update(
                    {
                        "fixed_physical_balh_modal_solver": system_diagnostics,
                        "modal_feedback_pc_side_apply_counts": side_apply_counts,
                        "modal_feedback_pc_side_apply_count_scope": (
                            "successful direct side apply calls; per-rank replicated"
                        ),
                    }
                )
                apply_call_key = "modal_feedback_apply_calls"
                matrix_call_key = "modal_feedback_matrix_mult_calls"
                setup_side_count_key = "modal_feedback_side_counts"
                whole_run_key = "modal_feedback_whole_run_work"
            result.update(common_modal_fields)
            local_rank = system_diagnostics.get("rank")
            if not isinstance(local_rank, int) or isinstance(local_rank, bool):
                local_rank = int(
                    _action_operator(self.bottom_action).getComm().tompi4py().rank
                )
            early_gate = (
                self._research_inventory.get("early_sample_gate", {})
                if self._research_inventory is not None
                else {}
            )
            gate_rows = early_gate.get("rank_results", [])
            gate_row = next(
                (
                    row
                    for row in gate_rows
                    if row.get("rank") == local_rank
                ),
                None,
            )
            setup_s_h = (
                None
                if gate_row is None
                else gate_row.get("operator_action_completions")
            )
            solver_s_h = system_diagnostics.get("cumulative_total_matmult_calls")

            def valid_counts(value: Any) -> int | None:
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
                return None

            setup_s_h = valid_counts(setup_s_h)
            solver_s_h = valid_counts(solver_s_h)
            total_s_h = (
                None
                if setup_s_h is None or solver_s_h is None
                else setup_s_h + solver_s_h
            )
            whole_run_work = {
                "rank": local_rank,
                "count_scope": "rank-local; do_not_sum_across_ranks",
                "setup_gate_s_h_actions": setup_s_h,
                "gmres_solver_and_final_check_s_h_actions": solver_s_h,
                "total_s_h_actions_including_setup_gate": total_s_h,
                "setup_gate_c_matvec_calls": (
                    None
                    if gate_row is None
                    else valid_counts(
                        gate_row.get("modal_constraint_matvec_calls")
                    )
                ),
                "total_c_matvec_calls_including_setup_gate": valid_counts(
                    system_diagnostics.get("modal_constraint_matvec_calls_total")
                ),
                "setup_gate_h6_calls_by_side": (
                    None
                    if gate_row is None
                    else gate_row.get(setup_side_count_key)
                ),
                "owner_c_lu_factorizations": system_diagnostics.get(
                    "constraint_lu_factorizations"
                ),
                "gmres_c_lu_solve_attempts": system_diagnostics.get(
                    "cumulative_constraint_lu_solve_attempts"
                ),
                "gmres_c_lu_solve_count_scope": system_diagnostics.get(
                    "cumulative_constraint_lu_solve_count_scope"
                ),
                "gmres_c_lu_owner_solve_attempts": system_diagnostics.get(
                    "cumulative_owner_constraint_lu_solve_attempts"
                ),
                "gmres_c_lu_owner_solve_successes": system_diagnostics.get(
                    "cumulative_owner_constraint_lu_solve_successes"
                ),
                "gmres_c_lu_owner_solve_status": system_diagnostics.get(
                    "cumulative_owner_constraint_lu_solve_status"
                ),
                "gmres_c_lu_owner_solve_count_scope": system_diagnostics.get(
                    "cumulative_owner_constraint_lu_solve_count_scope"
                ),
            }
            if selected_method == "fixed_h6_modal_gmres_research":
                whole_run_work.update(
                    {
                        "total_h6_apply_calls_by_side": system_diagnostics.get(
                            apply_call_key
                        ),
                        "total_h6_matrix_mult_calls_by_side": system_diagnostics.get(
                            matrix_call_key
                        ),
                    }
                )
            else:
                whole_run_work.update(
                    {
                        "total_side_feedback_apply_calls_by_side": (
                            system_diagnostics.get(apply_call_key)
                        ),
                        "total_side_feedback_matrix_mult_calls_by_side": (
                            system_diagnostics.get(matrix_call_key)
                        ),
                    }
                )
            result[whole_run_key] = whole_run_work
        if v13_modal:
            bottom_inverse = getattr(self.bottom_action, "_side_inverse", None)
            top_inverse = getattr(self.top_action, "_side_inverse", None)
            if bottom_inverse is None or top_inverse is None:
                raise RuntimeError("V13 LDU actions lost their borrowed side inverses")
            bottom_inverse_diagnostics = dict(bottom_inverse.diagnostics)
            top_inverse_diagnostics = dict(top_inverse.diagnostics)
            same_b = (
                self.action_modal_schur_system.bottom_action is self.bottom_action
                and self.action_modal_schur_system.top_action is self.top_action
            )
            if not same_b:
                raise RuntimeError(
                    "V13 modal Schur and LDU apply do not share the same B objects"
                )
            result.update(
                {
                    "modal_actual_method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                    "modal_solver_policy": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                    "task041_v13_consistent_modal_surrogate": system_diagnostics,
                    "bottom_direct_factor_count": int(
                        bottom_inverse_diagnostics.get("direct_factor_count", 0)
                    ),
                    "top_direct_factor_count": int(
                        top_inverse_diagnostics.get("direct_factor_count", 0)
                    ),
                    "direct_factor_count": int(
                        bottom_inverse_diagnostics.get("direct_factor_count", 0)
                    )
                    + int(top_inverse_diagnostics.get("direct_factor_count", 0)),
                    "borrowed_direct_factor_count": int(
                        bottom_inverse_diagnostics.get("direct_factor_count", 0)
                    )
                    + int(top_inverse_diagnostics.get("direct_factor_count", 0)),
                    "p4_factor_count": int(
                        bottom_inverse_diagnostics.get("p4_factor_count", 0)
                    )
                    + int(top_inverse_diagnostics.get("p4_factor_count", 0)),
                    "nested_iterative_ksp_count": int(
                        bottom_inverse_diagnostics.get("nested_iterative_ksp_count", 0)
                    )
                    + int(top_inverse_diagnostics.get("nested_iterative_ksp_count", 0)),
                    "borrowed_side_inverse_inventory_by_side": {
                        "bottom": bottom_inverse_diagnostics,
                        "top": top_inverse_diagnostics,
                    },
                    "v13_same_B_objects_for_schur_and_LDU": True,
                    "v13_pc_side_apply_counts": {
                        side: dict(values)
                        for side, values in self._v13_pc_side_apply_counts.items()
                    },
                    "v13_side_operation_baseline": {
                        side: dict(values)
                        for side, values in self._v13_side_operation_baseline.items()
                    },
                    "v13_modal_ksp_solve_count": system_diagnostics[
                        "modal_ksp_solve_count"
                    ],
                    "v13_side_solver_entry_zero_supported": system_diagnostics[
                        "side_solver_entry_zero_supported"
                    ],
                    "v13_side_operation_deltas": system_diagnostics[
                        "side_operation_deltas"
                    ],
                }
            )
        if self._research_inventory is not None:
            result.update(self._research_inventory)
        if (
            fixed_h6_modal
            and isinstance(system_diagnostics.get("modal_solver_policy"), Mapping)
            and system_diagnostics["modal_solver_policy"].get("policy_id")
            == TASK041_V12_MODAL_BACKUP_POLICY_ID
        ):
            result.update(
                {
                    "preconditioner_identity": (
                        "task041_v12_h6_primary_once_fixed_physical_balh_backup"
                    ),
                    "modal_primary_method": "fixed_h6_modal_gmres_research",
                    "modal_actual_method": system_diagnostics.get("method"),
                    "modal_method_history": list(
                        system_diagnostics.get("method_history", ())
                    ),
                    "modal_backup_switch_audit": dict(
                        system_diagnostics.get("backup_switch_audit", {})
                    ),
                }
            )
        if self._dynamic_side_inventory:
            nested_live = sum(
                int(diagnostics.get("nested_iterative_ksp_count", 0))
                for diagnostics in (bottom, top)
            )
            nested_created = sum(
                int(diagnostics.get("nested_ksp_created_count", 0))
                for diagnostics in (bottom, top)
            )
            nested_destroyed = sum(
                int(diagnostics.get("nested_ksp_destroy_count", 0))
                for diagnostics in (bottom, top)
            )
            p4_live = sum(
                int(diagnostics.get("p4_factor_count", 0))
                for diagnostics in (bottom, top)
            )
            p4_created = sum(
                int(diagnostics.get("p4_factor_created_count", 0))
                for diagnostics in (bottom, top)
            )
            p4_destroyed = sum(
                int(diagnostics.get("p4_factor_destroy_count", 0))
                for diagnostics in (bottom, top)
            )
            result.update(
                {
                    "p4_factor_count": p4_live,
                    "p4_factor_created_count": p4_created,
                    "p4_factor_destroy_count": p4_destroyed,
                    "p6_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "global_hybrid_direct_factor_count": 0,
                    "nested_iterative_ksp_count": nested_live,
                    "nested_iterative_ksp_created_count": nested_created,
                    "nested_iterative_ksp_destroy_count": nested_destroyed,
                }
            )
        return result

    def _check_layouts(self) -> None:
        expected_bottom = self.layout.bottom_local_sizes[self.layout.comm.rank]
        expected_top = self.layout.top_local_sizes[self.layout.comm.rank]
        if self._bottom_rhs.getLocalSize() != expected_bottom:
            raise ValueError("Bottom action ownership does not match layout.")
        if self._top_rhs.getLocalSize() != expected_top:
            raise ValueError("Top action ownership does not match layout.")
        if self.modal_schur is None:
            if self.modal_count != self.layout.modal_count:
                raise ValueError("Modal solver count does not match layout.")
            constraint = self.modal_constraint
            if constraint.shape != (
                self.layout.modal_count,
                self.layout.modal_count,
            ):
                raise ValueError("Modal constraint does not match layout.")
        elif self.modal_schur.shape != (
            self.layout.modal_count,
            self.layout.modal_count,
        ):
            raise ValueError("Action modal Schur does not match layout.")

    def _source_parts(self, source: PETSc.Vec) -> np.ndarray:
        local = np.asarray(source.getArray(readonly=True))
        self._bottom_rhs.getArray()[:] = local[self.layout.local_bottom_slice]
        self._top_rhs.getArray()[:] = local[self.layout.local_top_slice]
        modal = (
            np.asarray(local[self.layout.local_modal_slice], dtype=np.complex128).copy()
            if self.layout.comm.rank == self.layout.modal_owner
            else None
        )
        return np.asarray(
            self.layout.comm.bcast(modal, root=self.layout.modal_owner),
            dtype=np.complex128,
        )

    def _apply_modal_tractions(self, modal: np.ndarray) -> None:
        count = self.mode_count
        _set_owned_values(self._bottom_positive_source, modal[:count])
        _set_owned_values(
            self._bottom_negative_source,
            np.asarray(self.coupling.propagation.backward.factors) * modal[count:],
        )
        _set_owned_values(
            self._top_positive_source,
            np.asarray(self.coupling.propagation.forward.factors) * modal[:count],
        )
        _set_owned_values(self._top_negative_source, modal[count:])
        self.coupling.bottom.positive_traction.mult(
            self._bottom_positive_source, self._bottom_positive_target
        )
        self.coupling.bottom.negative_traction.mult(
            self._bottom_negative_source, self._bottom_negative_target
        )
        self._bottom_coupling.getArray()[:] = self._bottom_positive_target.getArray(
            readonly=True
        ) + self._bottom_negative_target.getArray(readonly=True)
        self.coupling.top.positive_traction.mult(
            self._top_positive_source, self._top_positive_target
        )
        self.coupling.top.negative_traction.mult(
            self._top_negative_source, self._top_negative_target
        )
        self._top_coupling.getArray()[:] = self._top_positive_target.getArray(
            readonly=True
        ) + self._top_negative_target.getArray(readonly=True)

    @staticmethod
    def _fixed_action_side_ksp_iterations(action: Any) -> int | None:
        inverse = getattr(action, "_side_inverse", None)
        if inverse is None:
            return None
        diagnostics = getattr(inverse, "diagnostics", None)
        if not isinstance(diagnostics, Mapping):
            return None
        value = diagnostics.get("total_iterations")
        return (
            int(value)
            if isinstance(value, (int, np.integer))
            and not isinstance(value, (bool, np.bool_))
            and int(value) >= 0
            else None
        )

    def set_v13_original_modal_row_callback(
        self,
        callback: Callable[[PETSc.Vec, PETSc.Vec, int], Mapping[str, Any]],
        *,
        operator_identity: str,
    ) -> None:
        if not isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        ):
            raise TypeError("Original modal-row callback is V13-only")
        if not callable(callback) or not operator_identity:
            raise TypeError("V13 requires an identified original-A modal-row callback")
        self._v13_original_modal_row_callback = callback
        self._v13_original_operator_identity = str(operator_identity)

    def bind_v13_original_global_operator(self, operator: PETSc.Mat) -> None:
        """Bind the original full operator used by the outer FGMRES solve."""

        if not isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        ):
            return
        comm = self.layout.comm
        local_error = None
        try:
            if not isinstance(operator, PETSc.Mat):
                raise TypeError("V13 original operator must be a PETSc Mat")
            rows, columns = (int(value) for value in operator.getSize())
            if rows != self.layout.global_size or columns != self.layout.global_size:
                raise ValueError("V13 original operator does not match the LDU layout")
            relation = MPI.Comm.Compare(comm, operator.getComm().tompi4py())
            if relation not in (MPI.IDENT, MPI.CONGRUENT):
                raise ValueError("V13 original operator communicator differs")
        except Exception as exc:  # noqa: BLE001 - synchronize binding validation errors
            local_error = f"{type(exc).__name__}: {exc}"
        errors = comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            raise ValueError(
                "V13 original global operator binding rejected; "
                + "; ".join(failures)
            )
        original_action = operator.createVecLeft()
        expected_range = (
            int(self.layout.combined_offsets[comm.rank]),
            int(self.layout.combined_offsets[comm.rank] + self.layout.local_size),
        )
        vector_errors = []
        actual_range = tuple(int(value) for value in original_action.getOwnershipRange())
        if (
            int(original_action.getSize()) != self.layout.global_size
            or actual_range != expected_range
        ):
            vector_errors.append(
                f"original action layout {actual_range}/{original_action.getSize()} "
                f"does not match {expected_range}/{self.layout.global_size}"
            )
        original_context = operator.getPythonContext()
        for method_name in (
            "arm_v13_modal_row_capture",
            "consume_v13_modal_row_capture",
            "clear_v13_modal_row_capture",
        ):
            if not callable(getattr(original_context, method_name, None)):
                vector_errors.append(
                    f"original A MatPython context lacks {method_name}"
                )
        layout_errors = comm.allgather(vector_errors)
        layout_failures = [
            f"rank {rank}: {error}"
            for rank, errors in enumerate(layout_errors)
            for error in errors
        ]
        if layout_failures:
            original_action.destroy()
            raise ValueError(
                "V13 original operator capture binding rejected; "
                + "; ".join(layout_failures)
            )
        self._v13_original_operator = operator
        self._v13_original_operator_action = original_action
        operator_identity = str(int(operator.handle))
        context_identity = id(original_context)
        local_sizes_by_rank = [
            int(self.layout.bottom_local_sizes[rank])
            + int(self.layout.top_local_sizes[rank])
            + (int(self.layout.modal_count) if rank == self.layout.modal_owner else 0)
            for rank in range(comm.size)
        ]
        layout_identity = {
            "global_size": int(self.layout.global_size),
            "local_size_by_rank": local_sizes_by_rank,
            "modal_global_indices": [
                int(value)
                for value in self.layout.map_modal(
                    np.arange(self.layout.modal_count, dtype=PETSc.IntType)
                )
            ],
            "combined_offsets": [int(value) for value in self.layout.combined_offsets],
            "modal_owner": int(self.layout.modal_owner),
            "modal_count": int(self.layout.modal_count),
            "local_modal_range_by_rank": [
                [
                    int(self.layout.bottom_local_sizes[rank])
                    + int(self.layout.top_local_sizes[rank]),
                    int(self.layout.bottom_local_sizes[rank])
                    + int(self.layout.top_local_sizes[rank])
                    + (int(self.layout.modal_count) if rank == self.layout.modal_owner else 0),
                ]
                for rank in range(comm.size)
            ],
        }
        layout_identity_sha256 = hashlib.sha256(
            json.dumps(
                layout_identity, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

        def original_modal_row(
            source: PETSc.Vec, target: PETSc.Vec, attempt_index: int
        ) -> Mapping[str, Any]:
            arm_error = None
            source_before = target_before = None
            try:
                source_before = _v13_local_petsc_vec_hash(source)
                target_before = _v13_local_petsc_vec_hash(target)
                if source is target or int(source.handle) == int(target.handle):
                    raise ValueError("V13 PC source and output Vecs alias")
                original_context.arm_v13_modal_row_capture(
                    int(attempt_index),
                    matrix_handle=int(operator.handle),
                    pc_source_handle=int(source.handle),
                    pc_target_handle=int(target.handle),
                    operator_input_handle=int(target.handle),
                    operator_output_handle=int(original_action.handle),
                )
            except Exception as exc:  # noqa: BLE001 - fail collectively before original-A MatMult
                arm_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            arm_errors = comm.allgather(arm_error)
            arm_failures = [
                f"rank {rank}: {error}"
                for rank, error in enumerate(arm_errors)
                if error is not None
            ]
            if arm_failures:
                original_context.clear_v13_modal_row_capture(int(attempt_index))
                raise _V13OriginalCaptureFailure(
                    "V13 original-A capture could not be armed; "
                    + "; ".join(arm_failures),
                    safe_to_collective=True,
                )
            local_capture = None
            try:
                operator.mult(target, original_action)
            except Exception as exc:
                original_context.clear_v13_modal_row_capture(int(attempt_index))
                raise _V13OriginalCaptureFailure(
                    "V13 original-A MatMult failed before a safe capture collective: "
                    f"{type(exc).__name__}: {str(exc)[:240]}",
                    safe_to_collective=False,
                ) from exc
            local_error = None
            try:
                local_capture = original_context.consume_v13_modal_row_capture(
                    int(attempt_index)
                )
            except Exception as exc:  # noqa: BLE001 - MatMult returned; this is the post-call safe point
                local_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            finally:
                original_context.clear_v13_modal_row_capture(int(attempt_index))
            capture_signature = None
            if local_capture is not None:
                try:
                    capture_signature = {
                        key: hashlib.sha256(
                            np.ascontiguousarray(local_capture[key]).view(np.uint8)
                        ).hexdigest()
                        for key in ("t_bottom", "t_top", "t_constraint")
                    }
                except Exception as exc:  # noqa: BLE001 - synchronize extraction after MatMult
                    local_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            source_after = target_after = None
            post_call_error = None
            try:
                source_after = _v13_local_petsc_vec_hash(source)
                target_after = _v13_local_petsc_vec_hash(target)
            except Exception as exc:  # noqa: BLE001 - report at the safe post-MatMult point
                post_call_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            if local_error is None:
                local_error = post_call_error
            local_after = {
                "error": local_error,
                "capture_signature": capture_signature,
                "token": None if local_capture is None else local_capture.get("token"),
                "matmult_call_id": (
                    None if local_capture is None else local_capture.get("matmult_call_id")
                ),
                "pc_source_handle": (
                    None if local_capture is None else local_capture.get("pc_source_handle")
                ),
                "pc_target_handle": (
                    None if local_capture is None else local_capture.get("pc_target_handle")
                ),
                "operator_input_handle": (
                    None if local_capture is None else local_capture.get("operator_input_handle")
                ),
                "operator_output_handle": (
                    None if local_capture is None else local_capture.get("operator_output_handle")
                ),
                "pc_source_range": [int(value) for value in source.getOwnershipRange()],
                "pc_target_range": [int(value) for value in target.getOwnershipRange()],
                "operator_input_range": (
                    None if local_capture is None else local_capture.get("operator_input_range")
                ),
                "operator_output_range": (
                    None if local_capture is None else local_capture.get("operator_output_range")
                ),
                "operator_input_unchanged": (
                    None if local_capture is None else local_capture.get("operator_input_unchanged")
                ),
                "operator_input_sha256_before": (
                    None if local_capture is None else local_capture.get("operator_input_sha256_before")
                ),
                "operator_input_sha256_after": (
                    None if local_capture is None else local_capture.get("operator_input_sha256_after")
                ),
                "operator_context_identity": int(context_identity),
                "pc_source_before": source_before,
                "pc_source_after": source_after,
                "pc_target_before": target_before,
                "pc_target_after": target_after,
            }
            rows = comm.allgather(local_after)
            errors = [
                f"rank {rank}: {row['error']}"
                for rank, row in enumerate(rows)
                if row.get("error") is not None
            ]
            signatures = [row.get("capture_signature") for row in rows]
            if (
                errors
                or any(row.get("token") != attempt_index for row in rows)
                or any(row.get("matmult_call_id") is None for row in rows)
                or len({row.get("matmult_call_id") for row in rows}) != 1
                or any(signature != signatures[0] for signature in signatures[1:])
            ):
                raise _V13OriginalCaptureFailure(
                    "V13 same-call original-A capture rejected: "
                    + (
                        "; ".join(errors)
                        if errors
                        else "rank capture identity/components differ"
                    ),
                    safe_to_collective=True,
                )
            owner_capture = local_capture if comm.rank == self.layout.modal_owner else None
            owner_capture = comm.bcast(owner_capture, root=self.layout.modal_owner)
            if not isinstance(owner_capture, Mapping):
                raise _V13OriginalCaptureFailure(
                    "V13 modal owner returned no same-call capture",
                    safe_to_collective=True,
                )
            r_modal = None
            r_modal_error = None
            try:
                if comm.rank == self.layout.modal_owner:
                    source_local = np.asarray(
                        source.getArray(readonly=True), dtype=np.complex128
                    )
                    r_modal = source_local[self.layout.local_modal_slice].copy()
            except Exception as exc:  # noqa: BLE001 - do not enter owner bcast on partial extraction
                r_modal_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            r_modal_errors = comm.allgather(r_modal_error)
            r_modal_failures = [
                f"rank {rank}: {error}"
                for rank, error in enumerate(r_modal_errors)
                if error is not None
            ]
            if r_modal_failures:
                raise _V13OriginalCaptureFailure(
                    "V13 PC RHS modal-row extraction failed: "
                    + "; ".join(r_modal_failures),
                    safe_to_collective=True,
                )
            r_modal = np.asarray(
                comm.bcast(r_modal, root=self.layout.modal_owner),
                dtype=np.complex128,
            )
            return {
                "r_modal": r_modal,
                "w_modal": np.asarray(owner_capture["w_modal"], dtype=np.complex128).copy(),
                "t_bottom": np.asarray(owner_capture["t_bottom"], dtype=np.complex128).copy(),
                "t_top": np.asarray(owner_capture["t_top"], dtype=np.complex128).copy(),
                "t_constraint": np.asarray(
                    owner_capture["t_constraint"], dtype=np.complex128
                ).copy(),
                "capture_identity": {
                    "attempt_index": int(attempt_index),
                    "matmult_call_id_by_rank": [
                        int(row["matmult_call_id"]) for row in rows
                    ],
                    "operator_handle": int(operator.handle),
                    "operator_context_identity_by_rank": [
                        row.get("operator_context_identity") for row in rows
                    ],
                    "pc_source_handle_by_rank": [
                        int(row["pc_source_handle"])
                        if isinstance(row.get("pc_source_handle"), int)
                        else None
                        for row in rows
                    ],
                    "pc_target_handle_by_rank": [
                        int(row["pc_target_handle"])
                        if isinstance(row.get("pc_target_handle"), int)
                        else None
                        for row in rows
                    ],
                    "operator_input_handle_by_rank": [
                        row.get("operator_input_handle") for row in rows
                    ],
                    "operator_output_handle_by_rank": [
                        row.get("operator_output_handle") for row in rows
                    ],
                    "pc_source_range_by_rank": [row.get("pc_source_range") for row in rows],
                    "pc_target_range_by_rank": [row.get("pc_target_range") for row in rows],
                    "pc_source_before_by_rank": [row.get("pc_source_before") for row in rows],
                    "pc_source_after_by_rank": [row.get("pc_source_after") for row in rows],
                    "pc_target_before_by_rank": [row.get("pc_target_before") for row in rows],
                    "pc_target_after_by_rank": [row.get("pc_target_after") for row in rows],
                    "pc_source_unchanged_by_rank": [
                        row.get("pc_source_before", {}).get("local_sha256")
                        == row.get("pc_source_after", {}).get("local_sha256")
                        for row in rows
                    ],
                    "pc_target_unchanged_by_original_A_by_rank": [
                        row.get("pc_target_before", {}).get("local_sha256")
                        == row.get("pc_target_after", {}).get("local_sha256")
                        for row in rows
                    ],
                    "pc_source_target_alias_by_rank": [
                        row.get("pc_source_before", {}).get("handle")
                        == row.get("pc_target_before", {}).get("handle")
                        for row in rows
                    ],
                    "operator_input_output_alias": (
                        int(target.handle) == int(original_action.handle)
                    ),
                    "layout_sha256": layout_identity_sha256,
                    "layout": layout_identity,
                    "operator_input_range_by_rank": [
                        list(row.get("operator_input_range", ())) for row in rows
                    ],
                    "operator_output_range_by_rank": [
                        list(row.get("operator_output_range", ())) for row in rows
                    ],
                    "operator_input_unchanged_by_rank": [
                        row.get("operator_input_unchanged") is True for row in rows
                    ],
                    "operator_input_sha256_before_by_rank": [
                        row.get("operator_input_sha256_before") for row in rows
                    ],
                    "operator_input_sha256_after_by_rank": [
                        row.get("operator_input_sha256_after") for row in rows
                    ],
                    "output_matches_components": owner_capture.get(
                        "output_matches_components"
                    ) is True,
                },
            }

        self.set_v13_original_modal_row_callback(
            original_modal_row,
            operator_identity=f"PETSc.Mat.handle:{operator_identity}",
        )

        system = self.action_modal_schur_system
        if callable(system._snapshot_callback):
            def make_owner_snapshot() -> Mapping[str, Any] | None:
                if comm.rank != self.layout.modal_owner:
                    return None
                schur = system.modal_schur
                if not isinstance(schur, np.ndarray):
                    raise TypeError("V13 owner S_B is unavailable at original-A binding")
                schur_copy = np.asarray(schur, dtype=np.complex128).copy()
                constraint_digest = hashlib.sha256(
                    np.ascontiguousarray(system.modal_constraint).view(np.uint8)
                ).hexdigest()
                schur_digest = hashlib.sha256(
                    np.ascontiguousarray(schur_copy).view(np.uint8)
                ).hexdigest()
                action_metadata = {}
                for side, action in (("bottom", self.bottom_action), ("top", self.top_action)):
                    inverse = getattr(action, "_side_inverse", None)
                    inverse_diagnostics = getattr(inverse, "diagnostics", {})
                    q_work = getattr(action, "audit", {}).get(
                        "fixed_q_actual_work_cumulative"
                    )
                    action_metadata[side] = {
                        "type": type(action).__name__,
                        "object_identity": id(action),
                        "operator_handle": (
                            int(_action_operator(action).handle)
                            if hasattr(action, "operator") or hasattr(action, "A")
                            else None
                        ),
                        "apply_count": _action_apply_count(action),
                        "borrowed_inverse_apply_count": (
                            inverse_diagnostics.get("apply_count")
                            if isinstance(inverse_diagnostics, Mapping)
                            else None
                        ),
                        "p4_factor_count": (
                            inverse_diagnostics.get("p4_factor_count")
                            if isinstance(inverse_diagnostics, Mapping)
                            else None
                        ),
                        "fixed_q_counter_snapshot": _v13_action_work_snapshot(action),
                        "fixed_q_actual_work_cumulative": q_work,
                    }
                payload = {
                    "snapshot_kind": "v15_s_b_ready",
                    "arrays": {
                        "s_b": schur_copy,
                        "C": np.asarray(system.modal_constraint, dtype=np.complex128).copy(),
                    },
                    "metadata": {
                        "formula": "S_B=C-LBG",
                        "status": "owner_matrix_ready_and_lu_factored",
                        "source": "current V13 builder output; no historical cache reuse",
                        "original_A": {
                            "handle": int(operator.handle),
                            "context_identity": int(context_identity),
                            "context_type": type(original_context).__name__,
                            "global_shape": [int(value) for value in operator.getSize()],
                            "layout_sha256": layout_identity_sha256,
                        },
                        "B_actions": action_metadata,
                        "modal": {
                            "owner_rank": int(system.modal_owner),
                            "mode_count_per_direction": int(self.mode_count),
                            "internal_mode_count": int(system.modal_count),
                            "dtype": str(schur_copy.dtype),
                            "shape": list(schur_copy.shape),
                            "s_b_sha256": schur_digest,
                            "constraint_sha256": constraint_digest,
                            "sample_contract": dict(system.build_audit.get("sample_contract", {})),
                            "owner_lu_factor_count": int(system.lu is not None),
                            "owner_lu_build_residuals": list(
                                system.build_audit.get("owner_original_schur_rhs_residuals", [])
                            ),
                            "owner_lu_build_residual_tolerance": system.build_audit.get(
                                "owner_original_schur_rhs_residual_tolerance"
                            ),
                        },
                        "component_binding": {
                            "source_and_producer_identity": "attached_by_workflow_snapshot_index",
                            "mesh_mpc_mode_and_packet_identity": "attached_by_workflow_consumer_binding",
                            "side_operator_and_constraint_hashes": {
                                "constraint_sha256": constraint_digest,
                                "S_B_sha256": schur_digest,
                            },
                        },
                    },
                }
                return payload

            snapshot_error = None
            owner_payload = None
            if comm.rank == self.layout.modal_owner:
                try:
                    owner_payload = make_owner_snapshot()
                except Exception as exc:  # noqa: BLE001 - synchronize before writer broadcast
                    snapshot_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            errors = comm.allgather(snapshot_error)
            failures = [f"rank {rank}: {error}" for rank, error in enumerate(errors) if error]
            if failures:
                raise RuntimeError("V13 S_B snapshot preparation failed: " + "; ".join(failures))
            receipt = system.persist_v13_evidence_snapshot(
                owner_payload if comm.rank == self.layout.modal_owner else {"snapshot_kind": "v15_s_b_ready"}
            )
            system._last_s_b_ready_snapshot = dict(receipt)
            if receipt.get("status") != "written":
                raise RuntimeError(
                    "V13 S_B ready evidence persistence failed: "
                    + str(receipt.get("error"))
                )
        else:
            system._last_s_b_ready_snapshot = {
                "status": "failed",
                "error": {
                    "type": "MissingWriter",
                    "message": "V15 S_B-ready evidence writer is required",
                },
            }
            raise TypeError(
                "V13 original-A binding requires the V15 S_B-ready evidence writer"
            )

    def _v13_pc_counter_snapshot(self) -> dict[str, Any]:
        system = self.action_modal_schur_system
        if not isinstance(system, Task041V13ConsistentModalSurrogateSystem):
            return {}
        sides = {}
        for side, action in (("bottom", self.bottom_action), ("top", self.top_action)):
            try:
                inverse = getattr(action, "_side_inverse", None)
                inverse_diagnostics = getattr(inverse, "diagnostics", {})
                sides[side] = {
                    "action_apply_count": _action_apply_count(action),
                    "action_work": _v13_action_work_snapshot(action),
                    "side_operation_counts": _v13_side_operation_counts(action),
                    "p4_factor_count": (
                        inverse_diagnostics.get("p4_factor_count")
                        if isinstance(inverse_diagnostics, Mapping)
                        else None
                    ),
                }
            except Exception as exc:  # noqa: BLE001 - preserve unavailable counter evidence
                sides[side] = {
                    "status": "unavailable",
                    "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                }
        return {
            "owner_lu_solve_count": int(system._owner_lu_solve_count),
            "solve_count": int(system._solve_count),
            "pc_success_count": int(self._pc_apply_count),
            "p4_and_B_by_side": sides,
            "fixed_h6_pc_side_apply_counts": (
                None
                if self._fixed_h6_pc_side_apply_counts is None
                else {
                    side: dict(values)
                    for side, values in self._fixed_h6_pc_side_apply_counts.items()
                }
            ),
        }

    def _check_v13_original_modal_row(
        self,
        source: PETSc.Vec,
        target: PETSc.Vec,
        attempt_index: int,
    ) -> None:
        system = self.action_modal_schur_system
        if not isinstance(system, Task041V13ConsistentModalSurrogateSystem):
            return
        callback = self._v13_original_modal_row_callback
        if not callable(callback):
            raise RuntimeError(  # noqa: TRY004 - the V13 action is missing from object state
                "V13 full-PC output has no independently bound original-A modal-row action"
            )

        def persist_rank_local_capture_failure(record: Mapping[str, Any]) -> dict[str, Any] | None:
            writer = system._snapshot_callback
            if not callable(writer):
                return None
            try:
                return dict(
                    writer(
                        {
                            "snapshot_kind": "v15_capture_failure_rank",
                            "rank": int(self.layout.comm.rank),
                            "attempt_index": int(attempt_index),
                            "record": dict(record),
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001 - keep capture failure primary
                return {
                    "status": "failed",
                    "error": {"type": type(exc).__name__, "message": str(exc)[:240]},
                }

        capture: Mapping[str, Any] | None = None
        capture_failure: BaseException | None = None
        comm = self.layout.comm
        try:
            capture = callback(source, target, int(attempt_index))
            if not isinstance(capture, Mapping):
                raise TypeError("original-A capture callback returned no mapping")
        except BaseException as exc:  # noqa: BLE001 - preserve evidence before PC cleanup
            capture_failure = exc

        if capture_failure is not None:
            safe = bool(
                isinstance(capture_failure, _V13OriginalCaptureFailure)
                and capture_failure.safe_to_collective
            )
            error_text = f"{type(capture_failure).__name__}: {str(capture_failure)[:320]}"
            row = {
                "status": "capture_failed",
                "failure_kind": "same_call_original_A_capture",
                "attempt_index": int(attempt_index),
                "operator_identity": self._v13_original_operator_identity,
                "safe_to_collective": safe,
                "error": error_text,
                "attempt": dict(self._current_pc_apply_evidence or {}),
            }
            if safe:
                errors = comm.allgather(error_text)
                row["rank_errors"] = [str(value) for value in errors]
            system.record_original_modal_row(row)
            write_receipt = persist_rank_local_capture_failure(row)
            if isinstance(write_receipt, Mapping):
                row["rank_local_write_receipt"] = dict(write_receipt)
                system.record_original_modal_row(row)
            system.record_pc_apply_attempt({**row, "status": "capture_failed"})
            raise FloatingPointError(
                "V13 original-A modal row capture failed before the row gate: "
                + error_text
            ) from capture_failure

        assert capture is not None
        fields = ("r_modal", "w_modal", "t_bottom", "t_top", "t_constraint")
        arrays: dict[str, np.ndarray] = {}
        array_errors: list[str] = []
        for name in fields:
            try:
                value = capture.get(name)
                if value is None:
                    raise ValueError("field is absent")
                arrays[name] = np.asarray(value, dtype=np.complex128).copy()
            except Exception as exc:  # noqa: BLE001 - keep individually credible terms
                array_errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
        metrics, residual = _v13_original_modal_row_metrics(
            *(arrays.get(name, np.empty(0, dtype=np.complex128)) for name in fields),
            tolerance=1.0e-10,
        )
        metric_inputs_available = bool(
            not array_errors and metrics.get("reason") != "shape_mismatch"
        )
        identity = capture.get("capture_identity")
        identity_errors: list[str] = []
        expected_modal_shape = (int(self.layout.modal_count),)
        for name in fields:
            if name in arrays and arrays[name].shape != expected_modal_shape:
                identity_errors.append(
                    f"{name} shape {arrays[name].shape} differs from "
                    f"the bound modal layout {expected_modal_shape}"
                )
        if not metric_inputs_available:
            identity_errors.append(
                "original modal-row metrics are unavailable from the captured array shapes"
            )
        if not isinstance(identity, Mapping):
            identity_errors.append("same-call capture identity is missing")
            identity = {}
        if identity.get("attempt_index") != attempt_index:
            identity_errors.append("capture attempt id differs from current PC attempt")
        if identity.get("operator_handle") != int(
            self._v13_original_operator.handle
            if self._v13_original_operator is not None
            else -1
        ):
            identity_errors.append("captured Mat handle differs from the bound original A")
        bound_context = (
            None
            if self._v13_original_operator is None
            else self._v13_original_operator.getPythonContext()
        )
        context_ids = identity.get("operator_context_identity_by_rank")
        if (
            not isinstance(context_ids, list)
            or len(context_ids) != comm.size
            or context_ids[comm.rank] != id(bound_context)
        ):
            identity_errors.append("captured MatPython context differs from the bound original A")
        if identity.get("output_matches_components") is not True:
            identity_errors.append("original-A output does not match captured component path")
        if metrics.get("decomposition_metrics_valid") is not True:
            identity_errors.append(
                "captured component decomposition error is unavailable, non-finite, "
                "or nonzero with a zero denominator"
            )
        elif metrics.get("decomposition_passed") is not True:
            identity_errors.append(
                "captured modal component decomposition exceeds the rowwise 1e-10 check"
            )
        if identity.get("pc_source_unchanged_by_rank") != [True] * comm.size:
            identity_errors.append("PC source changed during original-A row capture")
        if identity.get("pc_target_unchanged_by_original_A_by_rank") != [True] * comm.size:
            identity_errors.append("PC target changed during original-A MatMult")
        if identity.get("pc_source_target_alias_by_rank") != [False] * comm.size:
            identity_errors.append("PC source and target alias or alias evidence is missing")
        if identity.get("operator_input_unchanged_by_rank") != [True] * comm.size:
            identity_errors.append("original-A input changed during the captured MatMult")
        if identity.get("operator_input_output_alias") is not False:
            identity_errors.append("original-A input/output alias or alias evidence is invalid")
        call_ids = identity.get("matmult_call_id_by_rank")
        if (
            not isinstance(call_ids, list)
            or len(call_ids) != comm.size
            or any(type(value) is not int or value <= 0 for value in call_ids)
        ):
            identity_errors.append("original-A MatMult call ids are incomplete")
        entry = self._current_pc_apply_evidence or {}
        if entry.get("capture_prehash_error"):
            identity_errors.append(str(entry["capture_prehash_error"]))
        if entry.get("counter_snapshot_error"):
            identity_errors.append(str(entry["counter_snapshot_error"]))
        if not isinstance(entry.get("counters_before"), Mapping):
            identity_errors.append("pre-attempt B/P4 counter snapshot is missing")
        attempt_rows = comm.allgather(_v13_json_safe(dict(entry)))
        if any(row.get("attempt_index") != attempt_index for row in attempt_rows):
            identity_errors.append("PC attempt ordinal differs across ranks")
        if len({row.get("solve_count_before") for row in attempt_rows}) != 1:
            identity_errors.append("pre-attempt owner solve ordinal differs across ranks")
        if len({row.get("successful_pc_apply_count_before") for row in attempt_rows}) != 1:
            identity_errors.append("pre-attempt successful PC count differs across ranks")
        pc_source_handles = identity.get("pc_source_handle_by_rank")
        pc_target_handles = identity.get("pc_target_handle_by_rank")
        if not isinstance(pc_source_handles, list) or len(pc_source_handles) != comm.size:
            identity_errors.append("PC source handle identity is incomplete")
        elif any(
            pc_source_handles[rank] != attempt_rows[rank].get("source_handle")
            for rank in range(comm.size)
        ):
            identity_errors.append("captured PC source handle differs from the current attempt")
        if not isinstance(pc_target_handles, list) or len(pc_target_handles) != comm.size:
            identity_errors.append("PC target handle identity is incomplete")
        elif any(
            pc_target_handles[rank] != attempt_rows[rank].get("target_handle")
            for rank in range(comm.size)
        ):
            identity_errors.append("captured PC target handle differs from the current attempt")
        pc_source_after = identity.get("pc_source_after_by_rank")
        if not isinstance(pc_source_after, list) or len(pc_source_after) != comm.size:
            identity_errors.append("PC source after-hash identity is incomplete")
        else:
            for rank, attempt_row in enumerate(attempt_rows):
                before_hash = attempt_row.get("source_hash_before")
                after_hash = pc_source_after[rank]
                if (
                    not isinstance(before_hash, Mapping)
                    or not isinstance(after_hash, Mapping)
                    or before_hash.get("local_sha256") != after_hash.get("local_sha256")
                ):
                    identity_errors.append(
                        f"rank {rank}: PC source changed during the current attempt"
                    )
        operator_input_handles = identity.get("operator_input_handle_by_rank")
        if not isinstance(operator_input_handles, list) or len(operator_input_handles) != comm.size:
            identity_errors.append("original-A input handle identity is incomplete")
        elif any(
            operator_input_handles[rank] != attempt_rows[rank].get("target_handle")
            for rank in range(comm.size)
        ):
            identity_errors.append("original-A input is not the current PC target Vec")
        operator_output_handles = identity.get("operator_output_handle_by_rank")
        if not isinstance(operator_output_handles, list) or len(operator_output_handles) != comm.size:
            identity_errors.append("original-A output handle identity is incomplete")
        elif any(
            type(value) is not int for value in operator_output_handles
        ):
            identity_errors.append("original-A output handle identity is invalid")
        source_ranges = identity.get("pc_source_range_by_rank")
        target_ranges = identity.get("pc_target_range_by_rank")
        for range_name, range_rows, attempt_key in (
            ("source", source_ranges, "source_range"),
            ("target", target_ranges, "target_range"),
        ):
            if not isinstance(range_rows, list) or len(range_rows) != comm.size:
                identity_errors.append(f"PC {range_name} ownership ranges are incomplete")
            elif any(
                range_rows[rank] != attempt_rows[rank].get(attempt_key)
                for rank in range(comm.size)
            ):
                identity_errors.append(f"PC {range_name} ownership range changed during capture")
        operator_input_ranges = identity.get("operator_input_range_by_rank")
        if (
            not isinstance(operator_input_ranges, list)
            or len(operator_input_ranges) != comm.size
            or operator_input_ranges != target_ranges
        ):
            identity_errors.append("original-A input range differs from the current PC target")
        operator_output_ranges = identity.get("operator_output_range_by_rank")
        expected_local_sizes = [
            int(self.layout.bottom_local_sizes[rank])
            + int(self.layout.top_local_sizes[rank])
            + (
                int(self.layout.modal_count)
                if rank == self.layout.modal_owner
                else 0
            )
            for rank in range(comm.size)
        ]
        expected_operator_ranges = [
            [
                int(self.layout.combined_offsets[rank]),
                int(self.layout.combined_offsets[rank] + expected_local_sizes[rank]),
            ]
            for rank in range(comm.size)
        ]
        if operator_output_ranges != expected_operator_ranges:
            identity_errors.append("original-A output ranges differ from the bound layout")
        valid_pc_target_handles = (
            isinstance(pc_target_handles, list)
            and len(pc_target_handles) == comm.size
        )
        if (
            not isinstance(operator_output_handles, list)
            or len(operator_output_handles) != comm.size
            or any(type(value) is not int for value in operator_output_handles)
            or not valid_pc_target_handles
            or any(
                operator_output_handles[rank] == pc_target_handles[rank]
                for rank in range(comm.size)
            )
        ):
            identity_errors.append("original-A output aliases or lacks a per-rank handle")

        local_failure = {
            "metrics": {
                key: value
                for key, value in metrics.items()
                if not isinstance(value, np.ndarray)
            },
            "identity_errors": identity_errors,
            "array_errors": array_errors,
        }
        synchronized = comm.allgather(local_failure)
        collective_identity_errors = [
            f"rank {rank}: {error}"
            for rank, item in enumerate(synchronized)
            for error in [*item.get("identity_errors", []), *item.get("array_errors", [])]
        ]
        metric_rows = [item.get("metrics", {}) for item in synchronized]
        metrics_agree = all(
            row.get("eta_terms_inf") == metric_rows[0].get("eta_terms_inf")
            and row.get("status") == metric_rows[0].get("status")
            for row in metric_rows[1:]
        )
        if not metrics_agree:
            collective_identity_errors.append("replicated modal-row metric differs by rank")

        solve_before = entry.get("solve_count_before")
        solve_after = int(system._solve_count)
        owner_count_before = entry.get("owner_lu_solve_count_before")
        owner_count_after = int(system._owner_lu_solve_count)
        owner_solve_record = (
            None if system._last_solve is None else dict(system._last_solve)
        )
        owner_before_by_rank = [row.get("owner_lu_solve_count_before") for row in attempt_rows]
        owner_after_by_rank = comm.allgather(owner_count_after)
        expected_owner_count = None
        if (
            len(owner_before_by_rank) == comm.size
            and type(owner_before_by_rank[self.layout.modal_owner]) is int
        ):
            expected_owner_count = owner_before_by_rank[self.layout.modal_owner] + 1
        expected_owner_counts_by_rank = [
            int(owner_before_by_rank[rank]) + (1 if rank == self.layout.modal_owner else 0)
            if type(owner_before_by_rank[rank]) is int
            else None
            for rank in range(comm.size)
        ]
        same_attempt_solve = bool(
            type(solve_before) is int
            and solve_after == solve_before + 1
            and isinstance(owner_solve_record, Mapping)
            and owner_solve_record.get("owner_rank") == self.layout.modal_owner
            and owner_solve_record.get("owner_lu_solve_count") == expected_owner_count
            and owner_after_by_rank == expected_owner_counts_by_rank
            and owner_solve_record.get("status") == "passed"
            and owner_solve_record.get("input_unchanged") is True
            and owner_solve_record.get("trusted_iterate") is True
            and isinstance(
                owner_solve_record.get("relative_backward_error"), (int, float)
            )
            and math.isfinite(
                float(owner_solve_record.get("relative_backward_error", float("inf")))
            )
            and float(owner_solve_record.get("relative_backward_error", float("inf")))
            <= 1.0e-10
        )
        if not same_attempt_solve:
            solve_evidence_error = "owner LU solve record/count is not bound to this PC attempt"
            identity_errors.append(solve_evidence_error)
            collective_identity_errors.append(solve_evidence_error)
        counters_after = self._v13_pc_counter_snapshot()
        counters_after_by_rank = comm.allgather(counters_after)
        counter_delta_by_rank = [
            _v13_numeric_counter_delta(
                attempt_rows[rank].get("counters_before"),
                counters_after_by_rank[rank],
            )
            for rank in range(comm.size)
        ]
        counter_evidence_errors = []
        for rank in range(comm.size):
            before = attempt_rows[rank].get("counters_before")
            after = counters_after_by_rank[rank]
            if not isinstance(before, Mapping) or not isinstance(after, Mapping):
                counter_evidence_errors.append(
                    f"rank {rank}: same-attempt B/P4 counter snapshot is unavailable"
                )
                continue
            for side in ("bottom", "top"):
                before_side = before.get("p4_and_B_by_side", {}).get(side)
                after_side = after.get("p4_and_B_by_side", {}).get(side)
                if not isinstance(before_side, Mapping) or not isinstance(
                    after_side, Mapping
                ):
                    counter_evidence_errors.append(
                        f"rank {rank} {side}: B/P4 counter detail is unavailable"
                    )
                    continue
                before_apply = before_side.get("action_apply_count")
                after_apply = after_side.get("action_apply_count")
                before_p4 = before_side.get("p4_factor_count")
                after_p4 = after_side.get("p4_factor_count")
                if (
                    type(before_apply) is not int
                    or type(after_apply) is not int
                    or after_apply - before_apply != 2
                ):
                    counter_evidence_errors.append(
                        f"rank {rank} {side}: fixed B apply delta is not two"
                    )
                if (
                    type(before_p4) is not int
                    or type(after_p4) is not int
                    or after_p4 != before_p4
                ):
                    counter_evidence_errors.append(
                        f"rank {rank} {side}: P4 factor count changed or is missing"
                    )
        identity_errors.extend(counter_evidence_errors)
        collective_identity_errors.extend(counter_evidence_errors)
        eta_inf = metrics.get("eta_terms_inf")
        metrics_pass = bool(
            metric_inputs_available
            and metrics.get("valid") is True
            and isinstance(eta_inf, (int, float))
            and math.isfinite(float(eta_inf))
            and float(eta_inf) <= 1.0e-10
        )
        metrics_rejected = bool(metric_inputs_available and not metrics_pass)
        mandatory_evidence_failure = bool(
            collective_identity_errors or not same_attempt_solve
        )
        row_classification = (
            "numeric_gate_reject"
            if metrics_rejected
            else "evidence_failure"
            if not metrics_pass
            else "mandatory_evidence_failure_after_numeric_pass"
            if mandatory_evidence_failure
            else "numeric_gate_pass"
        )
        row_record = {
            "schema": _V15_ORIGINAL_MODAL_ROW_CONTRACT,
            "contract_id": _V15_ORIGINAL_MODAL_ROW_CONTRACT,
            "legacy_schema": _V13_ORIGINAL_MODAL_ROW_LEGACY_SCHEMA,
            "status": (
                "rejected"
                if metrics_rejected
                else "passed"
                if metrics_pass and not mandatory_evidence_failure
                else "evidence_failed"
            ),
            "classification": row_classification,
            "metric_inputs_available": metric_inputs_available,
            "equation": "d=w_modal-r_modal; w_modal=t_constraint+t_bottom+t_top in original A call order",
            "operator_identity": self._v13_original_operator_identity,
            "provenance_binding": {
                "source_sha256": "v15_modal_evidence_index.source_sha",
                "invocation_id": "v15_modal_evidence_index.identity.invocation_id",
                "outer_iteration": "not_available_inside_pc_apply",
            },
            "outer_iteration": {
                "status": "not_available_inside_pc_apply",
                "value": None,
            },
            "modal_layout_keys": {
                "modal_owner": int(self.layout.modal_owner),
                "modal_count": int(self.layout.modal_count),
                "modal_global_indices": list(
                    identity.get("layout", {}).get("modal_global_indices", [])
                ),
                "layout_sha256": identity.get("layout_sha256"),
            },
            "attempt_index": int(attempt_index),
            "successful_pc_apply_count_before": int(self._pc_apply_count),
            "attempted_pc_apply_count": int(self._pc_apply_attempt_count),
            "attempt_binding_by_rank": attempt_rows,
            "capture_identity": dict(identity),
            "same_attempt_owner_solve": same_attempt_solve,
            "owner_lu_solve_record": owner_solve_record,
            "owner_lu_solve_count_before": owner_count_before,
            "owner_lu_solve_count_after": owner_count_after,
            "solve_count_before": solve_before,
            "solve_count_after": solve_after,
            "B_P4_counters_before": entry.get("counters_before"),
            "B_P4_counters_after": counters_after,
            "B_P4_counters_after_by_rank": counters_after_by_rank,
            "B_P4_counter_delta": _v13_numeric_counter_delta(
                entry.get("counters_before"), counters_after
            ),
            "B_P4_counter_delta_by_rank": counter_delta_by_rank,
            "identity_or_evidence_errors": collective_identity_errors,
            "capture_array_errors": array_errors,
            "metrics": {
                key: value
                for key, value in metrics.items()
                if not isinstance(value, np.ndarray) and key != "residual"
            },
        }
        arrays.update(
            {
                "d": residual.copy(),
                "a": np.asarray(self._modal_solution, dtype=np.complex128).copy(),
                "g": np.asarray(self._modal_rhs, dtype=np.complex128).copy(),
            }
        )
        for name in (
            "row_scale",
            "row_denominator_scaled",
            "row_relative_error",
            "row_relative_log_error",
            "decomposition_error",
            "decomposition_row_relative_error",
            "decomposition_row_relative_log_error",
        ):
            value = metrics.get(name)
            if isinstance(value, np.ndarray):
                arrays[name] = value.copy()
        system.record_original_modal_row(row_record, arrays)
        system.record_pc_apply_attempt(row_record)

        # The numeric row gate has priority. Writer/evidence errors are retained
        # as secondary details and can never convert a rejection into a pass.
        writer_errors: list[str] = []
        if metrics_rejected:
            slot_kinds = ["v15_terminal_numeric_reject"]
        elif collective_identity_errors or not same_attempt_solve:
            slot_kinds = ["v15_evidence_failure"]
        else:
            slot_kinds = ["v15_first_success_control"]
            if metrics.get("legacy_rhs_relative_status") == "rejected":
                slot_kinds.append("v15_first_legacy_fail_new_pass")
        snapshot_receipts: dict[str, Any] = {}
        for current_slot in slot_kinds:
            if current_slot in system._original_modal_row_snapshot_slots:
                continue
            snapshot_payload = {
                "snapshot_kind": current_slot,
                "attempt_index": int(attempt_index),
                "record": row_record,
                "arrays": arrays,
            }
            receipt = system.persist_v13_evidence_snapshot(snapshot_payload)
            snapshot_receipts[current_slot] = receipt
            if receipt.get("status") != "written":
                writer_errors.append(
                    f"{current_slot}: {receipt.get('error')}"
                )
            else:
                system._last_original_modal_row_snapshot_receipt = dict(receipt)
        row_record["writer_errors"] = list(writer_errors)
        row_record["snapshot_receipts_by_slot"] = snapshot_receipts
        if (
            not metrics_rejected
            and writer_errors
            and "v15_evidence_failure" not in system._original_modal_row_snapshot_slots
        ):
            evidence_payload = {
                "snapshot_kind": "v15_evidence_failure",
                "attempt_index": int(attempt_index),
                "record": {
                    **row_record,
                    "status": "evidence_failed",
                    "classification": "mandatory_evidence_failure_after_numeric_pass",
                },
                "arrays": arrays,
            }
            evidence_receipt = system.persist_v13_evidence_snapshot(evidence_payload)
            row_record["snapshot_receipts_by_slot"]["v15_evidence_failure"] = evidence_receipt
            if evidence_receipt.get("status") != "written":
                writer_errors.append(f"v15_evidence_failure: {evidence_receipt.get('error')}")
            else:
                system._last_original_modal_row_snapshot_receipt = dict(evidence_receipt)
            row_record["writer_errors"] = list(writer_errors)
        if metrics_rejected:
            local_rank_receipt = None
            rank_write_error = None
            writer = system._snapshot_callback
            if callable(writer):
                try:
                    local_rank_receipt = dict(
                        writer(
                            {
                                "snapshot_kind": "v15_terminal_rank_vectors",
                                "attempt_index": int(attempt_index),
                                "rank": int(comm.rank),
                                "record": row_record,
                                "source": np.asarray(source.getArray(readonly=True)),
                                "target": np.asarray(target.getArray(readonly=True)),
                            }
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - keep numerical refusal primary
                    rank_write_error = {"type": type(exc).__name__, "message": str(exc)[:240]}
            else:
                rank_write_error = {"type": "WriterMissing", "message": "snapshot callback not configured"}
            rank_receipts = comm.allgather(
                {"receipt": local_rank_receipt, "error": rank_write_error}
            )
            rank_write_errors = [
                f"rank {rank}: {item['error']}"
                for rank, item in enumerate(rank_receipts)
                if item.get("error") is not None
            ]
            if not rank_write_errors:
                vector_index = system.persist_v13_evidence_snapshot(
                    {
                        "snapshot_kind": "v15_terminal_rank_vectors_index",
                        "attempt_index": int(attempt_index),
                        "rank_receipts": [item["receipt"] for item in rank_receipts],
                        "record": row_record,
                    }
                )
                if vector_index.get("status") != "written":
                    rank_write_errors.append(str(vector_index.get("error")))
                else:
                    row_record["terminal_rank_vector_index"] = vector_index
            writer_errors.extend(rank_write_errors)
            row_record["writer_errors"] = list(writer_errors)
        system.record_original_modal_row(row_record, arrays)
        if metrics_rejected:
            relative_text = (
                "unavailable"
                if eta_inf is None
                else f"{float(eta_inf):.6e}"
            )
            suffix = (
                ""
                if not writer_errors
                else "; secondary evidence writer error(s): " + "; ".join(writer_errors)
            )
            raise FloatingPointError(
                "V13 original global modal-row residual gate rejected: "
                f"eta_terms_inf={relative_text}, limit=1.000000e-10{suffix}"
            )
        if collective_identity_errors or writer_errors or not same_attempt_solve:
            row_record["status"] = "evidence_failed"
            row_record["classification"] = "mandatory_evidence_failure_after_numeric_pass"
            system.record_original_modal_row(row_record, arrays)
            raise RuntimeError(
                "V13 original modal-row numeric gate passed but mandatory attempt evidence failed: "
                + "; ".join(collective_identity_errors + writer_errors)
            )

    def apply(self, _pc: PETSc.PC | None, source: PETSc.Vec, target: PETSc.Vec) -> None:
        try:
            self._apply_unwrapped(_pc, source, target)
        except BaseException as exc:
            self._record_v13_apply_exception(exc)
            raise

    def _record_v13_apply_exception(self, original_error: BaseException) -> None:
        try:
            system = self.action_modal_schur_system
            if not isinstance(system, Task041V13ConsistentModalSurrogateSystem):
                return
            attempt_index = int(self._pc_apply_attempt_count)
            try:
                error_message = str(original_error)[:320]
            except BaseException as render_error:  # noqa: BLE001 - never replace the primary
                error_message = f"<message unavailable: {type(render_error).__name__}>"
            current = system._last_original_modal_row
            row = dict(current) if isinstance(current, Mapping) else {}
            same_attempt = row.get("attempt_index") == attempt_index
            if same_attempt and row.get("status") != "passed":
                # A terminal numeric/evidence/capture failure is the primary
                # result.  The wrapper exception is only its propagation path.
                system.record_pc_apply_attempt(row)
                return
            if same_attempt:
                row["post_row_apply_exception"] = {
                    "type": type(original_error).__name__,
                    "message": error_message,
                }
                system.record_original_modal_row(
                    row, system._last_original_modal_row_arrays
                )
            else:
                row = {
                    "schema": "task041.v15.pc_apply_attempt_failure.v1",
                    "status": "pc_apply_failed_before_original_row_gate",
                    "attempt_index": attempt_index,
                    "attempt": dict(self._current_pc_apply_evidence or {}),
                    "failure": {
                        "type": type(original_error).__name__,
                        "message": error_message,
                    },
                }
                system.record_original_modal_row(row)
            system.record_pc_apply_attempt(row)
            writer = system._snapshot_callback
            if callable(writer):
                try:
                    receipt = writer(
                        {
                            "snapshot_kind": "v15_capture_failure_rank",
                            "rank": int(self.layout.comm.rank),
                            "attempt_index": attempt_index,
                            "record": row,
                        }
                    )
                    row["rank_local_failure_receipt"] = (
                        dict(receipt) if isinstance(receipt, Mapping) else None
                    )
                except BaseException as writer_error:  # noqa: BLE001 - secondary only
                    try:
                        writer_message = str(writer_error)[:240]
                    except BaseException as render_error:  # noqa: BLE001
                        writer_message = (
                            f"<message unavailable: {type(render_error).__name__}>"
                        )
                    row["secondary_writer_error"] = {
                        "type": type(writer_error).__name__,
                        "message": writer_message,
                    }
                system.record_original_modal_row(
                    row, system._last_original_modal_row_arrays
                )
                system.record_pc_apply_attempt(row)
        except BaseException as evidence_error:  # noqa: BLE001 - primary exception wins
            try:
                original_error.add_note(
                    "V15 attempt evidence preservation failed without replacing the "
                    f"primary error: {type(evidence_error).__name__}"
                )
            except BaseException:  # noqa: BLE001, S110 - preserve the primary exception
                pass

    def _apply_unwrapped(
        self, _pc: PETSc.PC | None, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self._destroyed:
            raise RuntimeError("Block-LDU preconditioner has been destroyed")
        started = time.perf_counter()
        self._pc_apply_attempt_count += 1
        attempt_index = self._pc_apply_attempt_count
        if isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        ):
            record: dict[str, Any] = {
                "attempt_index": int(attempt_index),
                "successful_pc_apply_count_before": int(self._pc_apply_count),
                "source_handle": int(source.handle),
                "target_handle": int(target.handle),
                "source_target_alias": (
                    source is target or int(source.handle) == int(target.handle)
                ),
                "source_range": [int(value) for value in source.getOwnershipRange()],
                "target_range": [int(value) for value in target.getOwnershipRange()],
                "owner_lu_solve_count_before": int(
                    self.action_modal_schur_system._owner_lu_solve_count
                ),
                "solve_count_before": int(self.action_modal_schur_system._solve_count),
                "capture_prehash_error": None,
            }
            try:
                record["source_hash_before"] = _v13_local_petsc_vec_hash(source)
                record["target_hash_before"] = _v13_local_petsc_vec_hash(target)
            except Exception as exc:  # noqa: BLE001 - record missing evidence without changing PC arithmetic
                record["capture_prehash_error"] = (
                    f"{type(exc).__name__}: {str(exc)[:240]}"
                )
            try:
                record["counters_before"] = self._v13_pc_counter_snapshot()
            except Exception as exc:  # noqa: BLE001 - counter diagnostics cannot veto a numerical attempt
                record["counters_before"] = None
                record["counter_snapshot_error"] = (
                    f"{type(exc).__name__}: {str(exc)[:240]}"
                )
            self._current_pc_apply_evidence = record
            self.action_modal_schur_system.record_pc_apply_attempt(record)
        modal = self._source_parts(source)
        self.bottom_action.apply(self._bottom_rhs, self._bottom_first)
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["bottom"]["first"] += 1
        self.top_action.apply(self._top_rhs, self._top_first)
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["top"]["first"] += 1
        self.coupling.bottom.projection.mult(
            self._bottom_first, self._bottom_projection
        )
        self.coupling.top.projection.mult(self._top_first, self._top_projection)
        if self._v13_pc_side_apply_counts is not None:
            self._v13_pc_side_apply_counts["bottom"]["first"] += 1
            self._v13_pc_side_apply_counts["top"]["first"] += 1
        self._modal_rhs[:] = modal
        self._modal_rhs[: self.mode_count] -= _replicated_modal_values(
            self._bottom_projection
        )
        self._modal_rhs[self.mode_count :] -= _replicated_modal_values(
            self._top_projection
        )
        if isinstance(
            self.action_modal_schur_system, _FixedH6ModalGmresResearchBundle
        ):
            self.action_modal_schur_system.set_outer_pc_apply_index(
                self._pc_apply_count + 1
            )
        self._modal_solution[:] = self.action_modal_schur_system.solve(self._modal_rhs)
        self._apply_modal_tractions(self._modal_solution)
        self.bottom_action.apply(self._bottom_coupling, self._bottom_delta)
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["bottom"]["delta"] += 1
        self.top_action.apply(self._top_coupling, self._top_delta)
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["top"]["delta"] += 1
        self._bottom_first.axpy(PETSc.ScalarType(-1.0), self._bottom_delta)
        self._top_first.axpy(PETSc.ScalarType(-1.0), self._top_delta)
        if self._v13_pc_side_apply_counts is not None:
            self._v13_pc_side_apply_counts["bottom"]["delta"] += 1
            self._v13_pc_side_apply_counts["top"]["delta"] += 1
            current = {
                "bottom": _v13_side_operation_counts(self.bottom_action),
                "top": _v13_side_operation_counts(self.top_action),
            }
            if any(value is None for value in current.values()):
                raise RuntimeError("V13 could not read actual borrowed side counters")
            deltas = {}
            for side in ("bottom", "top"):
                baseline = self._v13_side_operation_baseline[side]
                observed = current[side]
                if baseline is None or observed is None:
                    raise RuntimeError("V13 side-operation baseline is unavailable")
                deltas[side] = {
                    key: int(observed[key]) - int(baseline[key])
                    for key in ("apply_count", "total_iterations")
                }
                if any(delta != 0 for delta in deltas[side].values()):
                    raise RuntimeError(
                        f"V13 fixed B unexpectedly entered the {side} side solver"
                    )
            self.action_modal_schur_system.record_side_operation_counts(current)
        target_local = target.getArray()
        target_local[self.layout.local_bottom_slice] = self._bottom_first.getArray(
            readonly=True
        )
        target_local[self.layout.local_top_slice] = self._top_first.getArray(
            readonly=True
        )
        if self.layout.comm.rank == self.layout.modal_owner:
            target_local[self.layout.local_modal_slice] = self._modal_solution
        self._check_v13_original_modal_row(source, target, attempt_index)
        self._pc_apply_count += 1
        self._pc_apply_seconds += time.perf_counter() - started
        self._current_pc_apply_evidence = None
        if isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        ):
            row = self.action_modal_schur_system._last_original_modal_row
            if (
                isinstance(row, Mapping)
                and row.get("attempt_index") == attempt_index
                and row.get("status") == "passed"
            ):
                metrics = row.get("metrics", {})
                self.action_modal_schur_system.record_pc_apply_success(
                    {
                        "attempt_index": int(attempt_index),
                        "status": "passed",
                        "successful_pc_apply_count": int(self._pc_apply_count),
                        "eta_terms_inf": metrics.get("eta_terms_inf"),
                        "eta_terms_2": metrics.get("eta_terms_2"),
                        "legacy_rhs_relative_error": metrics.get(
                            "legacy_rhs_relative_error"
                        ),
                        "same_attempt_owner_solve": True,
                        "attempt_binding": dict(
                            self.action_modal_schur_system._last_pc_apply_attempt
                            or {}
                        ),
                    }
                )

    def release_deferred_action_modal_schur(self) -> None:
        if self._action_modal_schur_released:
            return
        self.action_modal_schur_system.destroy()
        self.modal_schur = None
        self._action_modal_schur_released = True

    def release_modal_solve_trace_handoff(self) -> None:
        handoff = self._modal_solve_trace_handoff
        if isinstance(handoff, list):
            handoff.clear()
        self._modal_solve_trace_handoff = None

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        for vector in (
            self._top_negative_target,
            self._top_positive_target,
            self._bottom_negative_target,
            self._bottom_positive_target,
            self._top_negative_source,
            self._top_positive_source,
            self._bottom_negative_source,
            self._bottom_positive_source,
            self._top_projection,
            self._bottom_projection,
            self._top_coupling,
            self._bottom_coupling,
            self._top_delta,
            self._bottom_delta,
            self._top_first,
            self._bottom_first,
            self._top_rhs,
            self._bottom_rhs,
        ):
            vector.destroy()
        if isinstance(
            self.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        ):
            for action in (self.bottom_action, self.top_action):
                destroy = getattr(action, "destroy", None)
                if callable(destroy):
                    destroy()
        if not self.defer_action_modal_schur_release:
            self.release_deferred_action_modal_schur()
        if self._v13_original_operator_action is not None:
            self._v13_original_operator_action.destroy()
            self._v13_original_operator_action = None
        self._v13_original_operator = None
        self._v13_original_modal_row_callback = None
        self._destroyed = True


def create_action_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: Any,
    top_system: Any,
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
) -> HybridBlockLduPreconditioner:
    """Create a fixed action-backed block-LDU context."""

    if (
        _direct_factor_count(_action_diagnostics(bottom_action)) != 0
        or _direct_factor_count(_action_diagnostics(top_action)) != 0
    ):
        raise ValueError("Action block-LDU requires zero borrowed direct factors.")
    modal_schur = build_hybrid_action_modal_schur(coupling, bottom_action, top_action)
    try:
        return HybridBlockLduPreconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            bottom_action,
            top_action,
            modal_schur,
        )
    except Exception:
        modal_schur.destroy()
        raise


def _check_on_demand_modal_sample_repeat(
    modal_action: HybridActionModalSchurApply,
    *,
    sampled_columns: Sequence[int] | None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None,
    sampled_column_contract_sha256: str | None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Repeat the frozen sample basis through S without materializing S."""

    contract = _sampled_modal_column_contract(
        sampled_columns,
        sampled_column_roles,
        sampled_column_contract_sha256,
        modal_action.modal_count,
        modal_action.mode_count,
    )
    if contract is None:
        return {
            "status": "not_run",
            "pass": None,
            "reason": "sampled_column_contract_not_supplied",
            "full_vs_sample": "not_applicable_full_schur_not_materialized",
        }

    columns = list(contract["columns"])
    comm = _action_operator(modal_action.bottom_action).getComm().tompi4py()
    marker_detail = {
        "side": "both",
        "stage": "modal_sample_repeat",
        "columns": columns,
        "sample_count": len(columns),
        "contract_sha256": contract["sha256"],
    }
    if marker_callback is not None:
        marker_callback(
            "modal_sample_begin",
            {
                **marker_detail,
                "index": 0,
                "total": len(columns),
                "width": len(columns),
                "logical_completed": 0,
                "stage_wall_seconds": 0.0,
            },
        )

    sample_started = time.perf_counter()
    first = np.empty((modal_action.modal_count, len(columns)), dtype=np.complex128)
    second = np.empty_like(first)
    for target in (first, second):
        for index, column in enumerate(columns):
            basis = np.zeros(modal_action.modal_count, dtype=np.complex128)
            basis[column] = 1.0
            target[:, index] = modal_action.apply(basis)

    _, repeat_metrics = _compare_modal_sample_repeat(
        first,
        second,
        finite_reducer=lambda finite: bool(comm.allreduce(finite, op=MPI.LAND)),
    )
    passed = repeat_metrics["pass"]
    diagnostics = {
        **contract,
        "status": "passed" if passed else "failed",
        "pass": passed,
        "mode": "on_demand_modal_action_two_sample_basis_repeats",
        "early_sample_repeat": {
            **repeat_metrics,
        },
        "full_vs_sample": "not_applicable_full_schur_not_materialized",
    }
    if not passed:
        raise ValueError(
            "Early sampled modal repeat Gate failed: "
            f"relative={repeat_metrics['relative_error']:.6e}, "
            f"max_column={repeat_metrics['max_column_relative_error']:.6e}, "
            f"finite={repeat_metrics['finite']}, limit=1.000000e-10"
        )
    if marker_callback is not None:
        marker_callback(
            "modal_sample_ready",
            {
                **marker_detail,
                "index": len(columns),
                "total": len(columns),
                "width": len(columns),
                "logical_completed": len(columns),
                "stage_wall_seconds": time.perf_counter() - sample_started,
                **diagnostics["early_sample_repeat"],
            },
        )
    return diagnostics


def _v13_side_operation_counts(action: Any) -> dict[str, int] | None:
    """Read the borrowed side inverse's real apply/iteration counters."""

    inverse = getattr(action, "_side_inverse", None)
    diagnostics = getattr(inverse, "diagnostics", None)
    if not isinstance(diagnostics, Mapping):
        return None
    apply_count = diagnostics.get("apply_count")
    iterations = diagnostics.get("total_iterations")
    if any(
        type(value) is not int or value < 0
        for value in (apply_count, iterations)
    ):
        return None
    return {"apply_count": apply_count, "total_iterations": iterations}


_FIXED_H6_FEEDBACK_GATE_TOLERANCE = 1.0e-10
_FIXED_H6_FEEDBACK_GATE_ALPHA = 0.5 + 0.75j
_FIXED_H6_FEEDBACK_GATE_EPSILON = 1.0e-12


def _fixed_h6_gate_norm(
    values: np.ndarray | None, modal_count: int
) -> tuple[float | None, str | None]:
    if values is None:
        return None, "dependent_output_unavailable"
    vector = np.asarray(values, dtype=np.complex128)
    if vector.shape != (modal_count,):
        return None, "shape_mismatch"
    if not np.all(np.isfinite(vector)):
        return None, "nonfinite_vector"
    norm = float(np.linalg.norm(vector))
    return (norm, None) if np.isfinite(norm) else (None, "nonfinite_norm")


def _fixed_h6_gate_metric(
    actual: np.ndarray | None,
    reference: np.ndarray | None,
    modal_count: int,
    *,
    relative_denominator: str | None = None,
    reference_norm_scale: float | None = None,
    reference_norm_parts: tuple[float | None, ...] = (),
    absolute_branch: str | None = None,
    input_norm: float | None = None,
) -> dict[str, Any]:
    actual_norm, actual_error = _fixed_h6_gate_norm(actual, modal_count)
    reference_norm, reference_error = _fixed_h6_gate_norm(reference, modal_count)
    errors = [error for error in (actual_error, reference_error) if error is not None]
    numerator = None
    denominator = None
    measured: float | None = None
    branch = "not_evaluated"
    if not errors:
        difference = np.asarray(actual - reference, dtype=np.complex128)
        if np.all(np.isfinite(difference)):
            candidate_numerator = float(np.linalg.norm(difference))
            if np.isfinite(candidate_numerator):
                numerator = candidate_numerator
            else:
                errors.append("nonfinite_difference_norm")
        else:
            errors.append("nonfinite_difference_norm")
    if not errors and absolute_branch is not None:
        measured = float(numerator)
        branch = absolute_branch
    elif not errors:
        if relative_denominator == "pair":
            denominator = max(float(actual_norm), float(reference_norm))
        elif relative_denominator == "scaled_reference":
            if reference_norm_scale is None or not np.isfinite(reference_norm_scale):
                errors.append("nonfinite_scaled_reference_norm")
            else:
                denominator = max(float(actual_norm), float(reference_norm_scale))
        elif relative_denominator == "reference_sum":
            if len(reference_norm_parts) != 2 or not all(
                part is not None and np.isfinite(part) for part in reference_norm_parts
            ):
                errors.append("nonfinite_reference_norm_sum")
            else:
                denominator = max(
                    float(actual_norm), sum(float(part) for part in reference_norm_parts)
                )
        else:
            errors.append("unknown_relative_denominator")
        if not errors:
            if not np.isfinite(denominator):
                denominator = None
                errors.append("nonfinite_denominator")
            elif denominator > 0.0:
                candidate_measure = float(numerator / denominator)
                if np.isfinite(candidate_measure):
                    measured = candidate_measure
                    branch = "relative"
                else:
                    errors.append("nonfinite_error_metric")
            else:
                measured = float(numerator)
                branch = "absolute_zero_denominator"
    finite = bool(not errors and measured is not None and np.isfinite(measured))
    if not finite and not errors:
        errors.append("nonfinite_error_metric")
    if errors:
        branch = "not_evaluated_invalid_intermediate"
    metric_pass = bool(
        finite
        and measured is not None
        and measured <= _FIXED_H6_FEEDBACK_GATE_TOLERANCE
    )
    return {
        "status": "evaluated" if finite else "not_evaluated",
        "numerator": numerator,
        "denominator": denominator,
        "branch": branch if finite else (branch or "nonfinite_or_invalid_intermediate"),
        "relative_error": measured if finite and branch == "relative" else None,
        "absolute_error": numerator,
        "measured_error": measured if finite else None,
        "actual_norm": actual_norm,
        "reference_norm": reference_norm,
        "input_norm": input_norm,
        "finite": finite,
        "errors": errors,
        "limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
        "pass": metric_pass,
    }


def _check_fixed_h6_modal_feedback_repeat_linearity(
    modal_solver: _FixedH6ModalKrylovSystem,
    *,
    original_side_actions: Mapping[str, Any],
    original_side_apply_counts_before: Mapping[str, int | None],
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Check the same fixed H6 feedback on bounded complex mixed vectors."""

    physical_balh_method = (
        modal_solver.method == "fixed_physical_balh_once_modal_gmres_research"
    )
    gate_stage = (
        "fixed_physical_balh_modal_feedback_repeat_linearity"
        if physical_balh_method
        else "fixed_h6_modal_feedback_repeat_linearity"
    )
    gate_mode = (
        "fixed_physical_balh_modal_feedback_complex_repeat_linearity"
        if physical_balh_method
        else "fixed_h6_modal_feedback_complex_repeat_linearity"
    )
    side_counts_key = (
        "modal_feedback_side_counts"
        if physical_balh_method
        else "fixed_h6_side_counts"
    )
    modal_action = modal_solver._modal_action
    if modal_action is None:
        raise RuntimeError("Fixed-H6 modal action is unavailable for its gate")
    modal_count = int(modal_solver.modal_count)
    mode_count = int(modal_solver.mode_count)
    k = np.arange(1, modal_count + 1, dtype=np.float64)
    x_raw = k + 1j * k[::-1]
    x_norm = float(np.linalg.norm(x_raw))
    x = np.asarray(x_raw / x_norm, dtype=np.complex128)
    y_raw = k[::-1] + 1j * (k + 0.5)
    y_orthogonal = y_raw - np.vdot(x, y_raw) * x
    y_norm = float(np.linalg.norm(y_orthogonal))
    y = np.asarray(y_orthogonal / y_norm, dtype=np.complex128)
    alpha, epsilon = _FIXED_H6_FEEDBACK_GATE_ALPHA, _FIXED_H6_FEEDBACK_GATE_EPSILON
    inputs = {
        "zero": np.zeros(modal_count, dtype=np.complex128),
        "x": x,
        "x_repeat": x,
        "alpha_x": alpha * x,
        "y": y,
        "y_repeat": y,
        "x_plus_y": x + y,
        "near_zero_x": epsilon * x,
    }
    input_norms = {name: float(np.linalg.norm(value)) for name, value in inputs.items()}
    input_hashes = {
        name: hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
        for name, value in inputs.items()
    }
    block_support = {
        name: [
            bool(np.linalg.norm(value[:mode_count]) > 0.0),
            bool(np.linalg.norm(value[mode_count:]) > 0.0),
        ]
        for name, value in (("x", x), ("y", y))
    }
    xy_inner_product_abs = float(abs(np.vdot(x, y)))
    input_definition = {
        "formula": (
            "k=1..modal_count; x=normalize(k+i*reverse(k)); "
            "y=normalize(reverse(k)+i*(k+0.5)-vdot(x,y_raw)*x)"
        ),
        "modal_count": modal_count,
        "mode_count_per_direction": mode_count,
        "x_norm": input_norms["x"],
        "y_norm": input_norms["y"],
        "x_sha256": input_hashes["x"],
        "y_sha256": input_hashes["y"],
        "x_y_inner_product_abs": xy_inner_product_abs,
        "x_y_noncollinear": bool(np.isfinite(xy_inner_product_abs) and xy_inner_product_abs < 1.0e-12),
        "x_y_complex": bool(np.any(x.imag != 0.0) and np.any(y.imag != 0.0)),
        "positive_negative_block_support": block_support,
        "alpha": [float(alpha.real), float(alpha.imag)],
        "epsilon": epsilon,
        "epsilon_x_norm": input_norms["near_zero_x"],
    }
    local_input_error = None
    if (
        x_norm == 0.0
        or y_norm == 0.0
        or not all(np.all(np.isfinite(value)) for value in inputs.values())
        or not all(np.isfinite(value) for value in input_norms.values())
        or not all(all(support) for support in block_support.values())
        or not np.isfinite(xy_inner_product_abs)
        or xy_inner_product_abs >= 1.0e-12
        or not input_definition["x_y_complex"]
    ):
        local_input_error = "gate_inputs_are_nonfinite_or_not_mixed"
    started = time.perf_counter()
    if marker_callback is not None:
        marker_callback(
            "modal_sample_begin",
            {
                "side": "both",
                "stage": gate_stage,
                "mode": "complex_repeat_homogeneity_additivity_and_near_zero",
                "input_definition": input_definition,
                "maximum_s_h_actions": len(inputs),
                "limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
            },
        )

    comm = modal_solver._comm
    input_records = comm.allgather((local_input_error, input_hashes))
    input_errors = [
        f"rank {rank}: {error}"
        for rank, (error, _hashes) in enumerate(input_records)
        if error is not None
    ]
    hash_sets = [
        tuple(sorted(hashes.items()))
        for error, hashes in input_records
        if error is None
    ]
    if hash_sets and any(value != hash_sets[0] for value in hash_sets[1:]):
        input_errors.append("deterministic gate inputs differ across ranks")
    if input_errors:
        elapsed = float(time.perf_counter() - started)
        rank_results = [
            {
                "rank": rank,
                "pass": False,
                "input_hashes": hashes,
                "operator_action_attempts": 0,
                "operator_action_completions": 0,
                "modal_constraint_matvec_calls": 0,
                "constraint_lu_solve_attempts": 0,
                side_counts_key: None,
                "input_unchanged_by_action": {},
                "original_side_apply_count_delta": None,
                "setup_wall_seconds": elapsed,
                "errors": [error] if error is not None else input_errors,
            }
            for rank, (error, hashes) in enumerate(input_records)
        ]
        failed_gate = {
            "status": "failed",
            "pass": False,
            "mode": gate_mode,
            "requested_s_h_actions": len(inputs),
            "input_definition": input_definition,
            "rank_results": rank_results,
            "rank_count": int(comm.size),
            "rank_action_counts_scope": "per-rank local; do_not_sum_across_ranks",
            "input_preflight_allgathers": 1,
            "result_consensus_allgathers": 0,
            "full_schur_materialized": False,
            "fallback_used": False,
        }
        if physical_balh_method:
            failed_gate.update(
                {
                    "method": modal_solver.method,
                    "feedback_method": modal_solver.feedback_method,
                    "operator": modal_solver._action_operator,
                }
            )
        if marker_callback is not None:
            marker_callback(
                "modal_sample_ready",
                {
                    "side": "both",
                    "stage": gate_stage,
                    "status": "failed",
                    "pass": False,
                    "early_sample_gate": failed_gate,
                },
            )
        raise ValueError(
            "Fixed-H6 modal feedback gate input preflight failed; "
            + "; ".join(input_errors)
        )

    side_before = {
        side: dict(action.audit)
        for side, action in zip(
            ("bottom", "top"), (modal_solver._bottom_action, modal_solver._top_action), strict=True
        )
    }
    constraint_before = int(modal_action._modal_constraint_matvec_count)
    lu_attempts_before = int(modal_solver._constraint_lu_solve_attempts)
    outputs: dict[str, np.ndarray | None] = {}
    output_norms: dict[str, float | None] = {}
    output_errors: dict[str, str | None] = {}
    input_unchanged_by_action: dict[str, bool] = {}
    metrics: dict[str, dict[str, Any]] = {}
    attempts = completions = 0

    for name, values in inputs.items():
        attempts += 1
        result = np.asarray(modal_action.apply(values), dtype=np.complex128)
        completions += 1
        norm, error = _fixed_h6_gate_norm(result, modal_count)
        input_unchanged = (
            hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
            == input_hashes[name]
        )
        input_unchanged_by_action[name] = input_unchanged
        if error is None and not input_unchanged:
            error = "input_mutated_during_action"
        output_norms[name] = norm
        output_errors[name] = error
        outputs[name] = result if error is None else None
        if name == "zero":
            metrics["zero_absolute"] = _fixed_h6_gate_metric(
                outputs[name], np.zeros(modal_count, dtype=np.complex128), modal_count,
                absolute_branch="absolute_zero_input", input_norm=input_norms[name],
            )
        elif name == "x_repeat":
            metrics["repeat_x"] = _fixed_h6_gate_metric(
                outputs[name], outputs.get("x"), modal_count, relative_denominator="pair"
            )
        elif name == "alpha_x":
            fx_norm = output_norms.get("x")
            metrics["complex_homogeneity"] = _fixed_h6_gate_metric(
                outputs[name], None if outputs.get("x") is None else alpha * outputs["x"], modal_count,
                relative_denominator="scaled_reference",
                reference_norm_scale=None if fx_norm is None else abs(alpha) * fx_norm,
            )
        elif name == "y_repeat":
            metrics["repeat_y"] = _fixed_h6_gate_metric(
                outputs[name], outputs.get("y"), modal_count, relative_denominator="pair"
            )
        elif name == "x_plus_y":
            fx, fy = outputs.get("x"), outputs.get("y")
            metrics["additivity"] = _fixed_h6_gate_metric(
                outputs[name], None if fx is None or fy is None else fx + fy, modal_count,
                relative_denominator="reference_sum",
                reference_norm_parts=(output_norms.get("x"), output_norms.get("y")),
            )
        elif name == "near_zero_x":
            fx = outputs.get("x")
            metrics["near_zero_absolute"] = _fixed_h6_gate_metric(
                outputs[name], None if fx is None else epsilon * fx, modal_count,
                absolute_branch="absolute_near_zero_input",
                input_norm=input_norms[name],
            )
            metrics["near_zero_absolute"].update(
                {
                    "output_norm": output_norms.get(name),
                }
            )

    side_counts = {}
    for side, action in zip(
        ("bottom", "top"), (modal_solver._bottom_action, modal_solver._top_action), strict=True
    ):
        audit = action.audit
        apply_calls = int(audit["apply_count"]) - int(side_before[side]["apply_count"])
        matrix_mult_calls = int(audit["matrix_mult_count"]) - int(
            side_before[side]["matrix_mult_count"]
        )
        h6_degree = audit.get("h6_degree")
        degree_valid = (
            isinstance(h6_degree, int)
            and not isinstance(h6_degree, bool)
            and h6_degree > 1
        )
        expected_h6_matrix_mult_calls = (
            (h6_degree - 1) * apply_calls if degree_valid else None
        )
        if physical_balh_method:
            a6_apply_calls = int(audit["a6_apply_count"]) - int(
                side_before[side]["a6_apply_count"]
            )
            h6_apply_calls = int(audit["h6_apply_count"]) - int(
                side_before[side]["h6_apply_count"]
            )
            h6_matrix_mult_calls = int(audit["h6_matrix_mult_count"]) - int(
                side_before[side]["h6_matrix_mult_count"]
            )
            expected_total_matrix_mult_calls = (
                None
                if expected_h6_matrix_mult_calls is None
                else 2 * apply_calls + expected_h6_matrix_mult_calls
            )
            side_counts[side] = {
                "modal_feedback_apply_calls": apply_calls,
                "a6_apply_calls": a6_apply_calls,
                "expected_a6_apply_calls": 2 * apply_calls,
                "h6_apply_calls": h6_apply_calls,
                "expected_h6_apply_calls": apply_calls,
                "h6_degree": h6_degree if degree_valid else None,
                "h6_matrix_mult_calls": h6_matrix_mult_calls,
                "expected_h6_matrix_mult_calls": expected_h6_matrix_mult_calls,
                "total_matrix_mult_calls": matrix_mult_calls,
                "expected_total_matrix_mult_calls": expected_total_matrix_mult_calls,
                "operation_sequence_matches": bool(
                    a6_apply_calls == 2 * apply_calls
                    and h6_apply_calls == apply_calls
                    and expected_h6_matrix_mult_calls is not None
                    and h6_matrix_mult_calls == expected_h6_matrix_mult_calls
                    and expected_total_matrix_mult_calls is not None
                    and matrix_mult_calls == expected_total_matrix_mult_calls
                ),
            }
        else:
            side_counts[side] = {
                "fixed_h6_apply_calls": apply_calls,
                "fixed_h6_h6_degree": h6_degree if degree_valid else None,
                "fixed_h6_matrix_mult_calls": matrix_mult_calls,
                "expected_matrix_mult_calls_from_degree": expected_h6_matrix_mult_calls,
                "matrix_mult_matches_h6_degree": bool(
                    expected_h6_matrix_mult_calls is not None
                    and matrix_mult_calls == expected_h6_matrix_mult_calls
                ),
            }
    original_after = {
        side: _action_apply_count(action) for side, action in original_side_actions.items()
    }
    original_delta = {
        side: (
            None
            if original_side_apply_counts_before.get(side) is None
            or original_after[side] is None
            else int(original_after[side]) - int(original_side_apply_counts_before[side])
        )
        for side in ("bottom", "top")
    }
    c_matvecs = int(modal_action._modal_constraint_matvec_count) - constraint_before
    c_lu_attempts = int(modal_solver._constraint_lu_solve_attempts) - lu_attempts_before
    local_pass = bool(
        attempts == len(inputs)
        and completions == len(inputs)
        and len(metrics) == 6
        and all(error is None for error in output_errors.values())
        and all(input_unchanged_by_action.values())
        and all(metric["pass"] for metric in metrics.values())
        and all(value == 0 for value in original_delta.values())
        and c_matvecs == completions
        and c_lu_attempts == 0
        and all(
            (
                row.get("operation_sequence_matches") is True
                if physical_balh_method
                else (
                    row.get("fixed_h6_apply_calls") == completions
                    and row.get("matrix_mult_matches_h6_degree") is True
                )
            )
            for row in side_counts.values()
        )
    )
    local_count_key = (
        "modal_feedback_side_counts"
        if physical_balh_method
        else "fixed_h6_side_counts"
    )
    local_result = {
        "rank": int(comm.rank),
        "pass": local_pass,
        "input_hashes": input_hashes,
        "operator_action_attempts": attempts,
        "operator_action_completions": completions,
        "modal_constraint_matvec_calls": c_matvecs,
        "constraint_lu_solve_attempts": c_lu_attempts,
        local_count_key: side_counts,
        "input_unchanged_by_action": input_unchanged_by_action,
        "original_side_apply_count_delta": original_delta,
        "output_norms": output_norms,
        "output_errors": output_errors,
        "metrics": metrics,
        "setup_wall_seconds": float(time.perf_counter() - started),
    }
    rank_results = comm.allgather(local_result)
    gathered_input_hashes = [
        tuple(sorted(row["input_hashes"].items())) for row in rank_results
    ]
    global_pass = bool(
        [row.get("rank") for row in rank_results] == list(range(comm.size))
        and all(row.get("pass") is True for row in rank_results)
        and len(set(gathered_input_hashes)) == 1
    )
    metric_formulas = {
        "zero_absolute": "||F(0)||",
        "repeat_x": "||F(x)_1-F(x)_2||/max(||F(x)_1||,||F(x)_2||)",
        "complex_homogeneity": (
            "||F(alpha*x)-alpha*F(x)||/"
            "max(||F(alpha*x)||,|alpha|*||F(x)||)"
        ),
        "repeat_y": "||F(y)_1-F(y)_2||/max(||F(y)_1||,||F(y)_2||)",
        "additivity": (
            "||F(x+y)-F(x)-F(y)||/"
            "max(||F(x+y)||,||F(x)||+||F(y)||)"
        ),
        "near_zero_absolute": "||F(epsilon*x)-epsilon*F(x)||",
    }
    for row in rank_results:
        for name, formula in metric_formulas.items():
            if name in row["metrics"]:
                row["metrics"][name]["formula"] = formula
    wall_values = [float(row["setup_wall_seconds"]) for row in rank_results]
    diagnostics = {
        "status": "passed" if global_pass else "failed",
        "pass": global_pass,
        "mode": gate_mode,
        "operator": (
            modal_solver._action_operator
            if physical_balh_method
            else "S_H=C-PbJbH6bJb^H Tb-PtJtH6tJt^H Tt"
        ),
        "requested_s_h_actions": len(inputs),
        "operator_actions_maximum": len(inputs),
        "relative_limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
        "absolute_limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
        "input_definition": input_definition,
        "metric_formulas": metric_formulas,
        "metrics": rank_results[0]["metrics"],
        "rank_results": rank_results,
        "rank_count": int(comm.size),
        "rank_action_counts_scope": "per-rank local; do_not_sum_across_ranks",
        "input_preflight_allgathers": 1,
        "result_consensus_allgathers": 1,
        "max_rank_setup_wall_seconds": max(wall_values),
        "constraint_lu_factorizations_owner": int(
            modal_solver._constraint_lu_factorizations_owner
        ),
        "constraint_lu_solve_attempts_by_rank": {
            str(row["rank"]): row["constraint_lu_solve_attempts"] for row in rank_results
        },
        "constraint_lu_solve_attempts_at_owner_during_gate": next(
            row["constraint_lu_solve_attempts"]
            for row in rank_results
            if row["rank"] == modal_solver._modal_owner
        ),
        "gmres_solver_and_final_check_budget_unchanged": {
            "solver_matmult_limit": int(modal_solver.solver_matmult_limit),
            "total_matmult_limit_including_final": int(modal_solver.total_matmult_limit),
        },
        "original_side_apply_count_scope": (
            "per-side rank-local SideBalancedInverse; "
            + (
                "modal feedback gate must not call it"
                if physical_balh_method
                else "fixed-H6 gate must not call it"
            )
        ),
        "full_schur_materialized": False,
        "fallback_used": False,
    }
    if physical_balh_method:
        diagnostics.update(
            {
                "method": modal_solver.method,
                "feedback_method": modal_solver.feedback_method,
            }
        )
    if marker_callback is not None:
        marker_callback(
            "modal_sample_ready",
            {
                "side": "both",
                "stage": gate_stage,
                "status": diagnostics["status"],
                "pass": global_pass,
                "early_sample_gate": diagnostics,
            },
        )
    if not global_pass:
        failures = [
            f"rank {row.get('rank')}: pass={row.get('pass')} "
            f"attempts={row.get('operator_action_attempts')} "
            f"completions={row.get('operator_action_completions')}"
            for row in rank_results
            if row.get("pass") is not True
        ]
        label = (
            "fixed physical BAL_H modal feedback"
            if physical_balh_method
            else "Fixed-H6 modal feedback"
        )
        raise ValueError(
            f"{label} repeat/linearity Gate failed; " + "; ".join(failures)
        )
    return diagnostics

def create_side_balh_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: Any,
    top_system: Any,
    coupling: HybridInternalModeCoupling,
    bottom_side_inverse: Any,
    top_side_inverse: Any,
    *,
    sampled_columns: Sequence[int] | None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None,
    sampled_column_contract_sha256: str | None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    use_anderson_modal_inner: bool = False,
    complex_qr_research: bool = False,
    raw_metric_mixing: bool = False,
    capture_modal_solve_trace: bool = False,
    fixed_h6_modal_gmres_research: bool = False,
    fixed_h6_modal_feedback_method: str | None = None,
    modal_solver_policy: Mapping[str, Any] | None = None,
    modal_snapshot_callback: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
    | None = None,
    v13_fresh_authority_callback: Callable[
        [str, Mapping[str, Any]], Mapping[str, Any]
    ] | None = None,
) -> HybridBlockLduPreconditioner:
    """Build the sampled Schur or one explicitly selected BAL_H research path.

    The side inverses are nonlinear finite-response operators from the H1e
    candidate path.  The default sampled response columns define only an
    approximate preconditioner Schur. The Anderson and fixed-H6 research
    branches require right FGMRES and remain mutually exclusive. The caller
    owns both side inverses and all side systems.
    """

    from .physical_balanced_side_inverse import (
        FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
        SideBalancedInverse,
    )

    side_entries = (
        ("bottom", bottom_system, bottom_side_inverse),
        ("top", top_system, top_side_inverse),
    )
    for side, system, side_inverse in side_entries:
        if not isinstance(side_inverse, SideBalancedInverse):
            raise TypeError(
                f"BAL_H block factory requires a SideBalancedInverse for {side}"
            )
        system_operator = getattr(system, "A", None)
        if not isinstance(system_operator, PETSc.Mat):
            raise TypeError(f"BAL_H {side} system must expose PETSc A")
        if int(side_inverse.operator.handle) != int(system_operator.handle):
            raise ValueError(f"BAL_H {side} inverse operator is not side.A")
        diagnostics = dict(side_inverse.diagnostics)
        if diagnostics.get("p4_factor_count") != 1:
            raise ValueError(f"BAL_H {side} inverse p4 factor count is not one")
        if diagnostics.get("p6_factor_count") != 0:
            raise ValueError(f"BAL_H {side} inverse cannot own a p6 factor")
        if diagnostics.get("global_direct_factor_count") != 0:
            raise ValueError(f"BAL_H {side} inverse cannot own a global factor")
        if diagnostics.get("nested_iterative_ksp_count") != 1:
            raise ValueError(
                f"BAL_H {side} inverse must expose one live nested KSP"
            )

    if not isinstance(use_anderson_modal_inner, (bool, np.bool_)):
        raise TypeError("Anderson modal inner opt-in must be an explicit boolean.")
    use_anderson_modal_inner = bool(use_anderson_modal_inner)
    if not isinstance(complex_qr_research, (bool, np.bool_)):
        raise TypeError("Complex QR research selection must be an explicit boolean.")
    complex_qr_research = bool(complex_qr_research)
    if not isinstance(raw_metric_mixing, (bool, np.bool_)):
        raise TypeError("Raw-metric Anderson selection must be an explicit boolean.")
    raw_metric_mixing = bool(raw_metric_mixing)
    if not isinstance(capture_modal_solve_trace, (bool, np.bool_)):
        raise TypeError("Modal solve trace capture must be an explicit boolean.")
    capture_modal_solve_trace = bool(capture_modal_solve_trace)
    if not isinstance(fixed_h6_modal_gmres_research, (bool, np.bool_)):
        raise TypeError("Fixed-H6 modal GMRES research must be an explicit boolean.")
    fixed_h6_modal_gmres_research = bool(fixed_h6_modal_gmres_research)
    if modal_solver_policy is not None and (
        not fixed_h6_modal_gmres_research
        or fixed_h6_modal_feedback_method is not None
    ):
        raise ValueError(
            "V12 modal policy requires the pure fixed-H6 research route"
        )
    if fixed_h6_modal_feedback_method not in (
        None,
        FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
    ):
        raise ValueError("unsupported fixed modal feedback method")
    if (
        fixed_h6_modal_feedback_method is not None
        and not fixed_h6_modal_gmres_research
    ):
        raise ValueError(
            "fixed physical BAL_H feedback requires the fixed-H6 modal research binding"
        )
    if fixed_h6_modal_gmres_research and any(
        (
            use_anderson_modal_inner,
            complex_qr_research,
            raw_metric_mixing,
            capture_modal_solve_trace,
        )
    ):
        raise ValueError(
            "Fixed-H6 modal GMRES research is mutually exclusive with all "
            "Anderson modal-inner options."
        )
    v13_modal_policy = bool(
        isinstance(modal_solver_policy, Mapping)
        and modal_solver_policy.get("policy_id")
        == TASK041_V13_CONSISTENT_MODAL_POLICY_ID
    )
    if v13_modal_policy and (
        not fixed_h6_modal_gmres_research
        or fixed_h6_modal_feedback_method is not None
        or not sampled_columns
        or not isinstance(sampled_column_roles, Mapping)
        or not sampled_column_contract_sha256
        or not callable(v13_fresh_authority_callback)
    ):
        raise ValueError(
            "V13 requires explicit fixed-H6 research, no second feedback selector, "
            "its sealed eight-column contract and fresh-authority callback"
        )
    if complex_qr_research and not use_anderson_modal_inner:
        raise ValueError(
            "Complex QR research requires the on-demand Anderson modal inner."
        )
    if raw_metric_mixing and not complex_qr_research:
        raise ValueError("Raw-metric mixing requires the complex QR research path.")
    if capture_modal_solve_trace and not (
        use_anderson_modal_inner and complex_qr_research
    ):
        raise ValueError(
            "Modal solve trace capture requires complex QR modal inner research."
        )
    if not use_anderson_modal_inner and not fixed_h6_modal_gmres_research and not all(
        value is not None
        for value in (
            sampled_columns,
            sampled_column_roles,
            sampled_column_contract_sha256,
        )
    ):
        raise ValueError("Sampled Schur metadata is required by the default BAL_H path.")

    modal_schur = None
    modal_system = None
    modal_action = None
    fixed_h6_solver = None
    fixed_h6_adapters: list[Any] = []
    ldu_bottom_action = bottom_side_inverse
    ldu_top_action = top_side_inverse
    try:
        if use_anderson_modal_inner:
            modal_action = HybridActionModalSchurApply(
                coupling,
                bottom_side_inverse,
                top_side_inverse,
            )
            early_sample_gate = _check_on_demand_modal_sample_repeat(
                modal_action,
                sampled_columns=sampled_columns,
                sampled_column_roles=sampled_column_roles,
                sampled_column_contract_sha256=sampled_column_contract_sha256,
                marker_callback=marker_callback,
            )
            modal_system = HybridActionModalSchurAndersonSystem(
                modal_action,
                modal_owner=layout.modal_owner,
                complex_qr_research=complex_qr_research,
                raw_metric_mixing=raw_metric_mixing,
                capture_modal_solve_trace=capture_modal_solve_trace,
            )
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": "BAL_H_on_demand_modal_anderson",
                "modal_block_name": "on_demand_nonlinear_modal_inner",
                "modal_schur_scope": "not_materialized",
                "not_original_global_operator": True,
                "not_original_reduced_operator": True,
                "borrowed_side_actions": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
                "modal_schur_materialized": False,
                "modal_schur_column_count": 0,
                "full_vs_sample": {
                    "status": "not_applicable",
                    "reason": "full_modal_schur_not_materialized",
                },
                "schur_lu_repeat": {
                    "status": "not_applicable",
                    "reason": "modal_schur_lu_not_constructed",
                },
                "early_sample_gate": early_sample_gate,
            }
        elif fixed_h6_modal_gmres_research and v13_modal_policy:
            from .physical_balanced_side_inverse import (
                FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
                FixedPhysicalBalancedActiveTraceAction,
            )

            original_side_actions = {
                "bottom": bottom_side_inverse,
                "top": top_side_inverse,
            }
            bottom_v13_action = (
                bottom_side_inverse.create_fixed_physical_balh_active_trace_action()
            )
            fixed_h6_adapters.append(bottom_v13_action)
            top_v13_action = (
                top_side_inverse.create_fixed_physical_balh_active_trace_action()
            )
            fixed_h6_adapters.append(top_v13_action)
            if any(
                not isinstance(action, FixedPhysicalBalancedActiveTraceAction)
                or action.method != FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
                for action in (bottom_v13_action, top_v13_action)
            ):
                raise TypeError("V13 requires the registered fixed physical B actions")
            ldu_bottom_action = bottom_v13_action
            ldu_top_action = top_v13_action
            modal_system = build_task041_v13_consistent_modal_surrogate(
                coupling,
                bottom_v13_action,
                top_v13_action,
                modal_owner=layout.modal_owner,
                sampled_columns=sampled_columns,
                sampled_column_roles=sampled_column_roles,
                sampled_column_contract_sha256=sampled_column_contract_sha256,
                original_augmented_local_size=layout.local_size,
                fresh_authority_callback=v13_fresh_authority_callback,
                snapshot_callback=modal_snapshot_callback,
                marker_callback=marker_callback,
            )
            v13_diagnostics = modal_system.diagnostics
            v13_side_deltas = v13_diagnostics.get("side_operation_deltas")
            if v13_diagnostics.get("side_solver_entry_zero_supported") is not True:
                raise RuntimeError(
                    "V13 Schur setup did not preserve the borrowed side operation counters"
                )
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                "modal_actual_method": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                "modal_block_name": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
                "modal_solver_policy": dict(modal_solver_policy),
                "fixed_h6_modal_gmres_research": True,
                "fixed_physical_balh_once_requested": True,
                "modal_feedback_method": None,
                "borrowed_side_actions": True,
                "same_B_objects_for_all_LDU_terms_and_modal_Schur": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
                "modal_schur_materialized": True,
                "modal_schur_column_count": int(modal_system.modal_count),
                "modal_ksp_solve_count": v13_diagnostics[
                    "modal_ksp_solve_count"
                ],
                "modal_ksp_handle_count": v13_diagnostics[
                    "modal_ksp_handle_count"
                ],
                "side_inverse_apply_count_delta_by_side": {
                    side: counts["apply_count"]
                    for side, counts in v13_side_deltas.items()
                },
                "side_inverse_iteration_delta_by_side": {
                    side: counts["total_iterations"]
                    for side, counts in v13_side_deltas.items()
                },
                "side_solver_entry_zero_supported": v13_diagnostics[
                    "side_solver_entry_zero_supported"
                ],
                "early_sample_gate": dict(modal_system.build_audit),
                "side_operation_baseline": dict(
                    v13_diagnostics["side_operation_baseline"]
                ),
                "side_inverse_inventory_by_side": {
                    side: dict(inverse.diagnostics)
                    for side, inverse in original_side_actions.items()
                },
                "borrowed_direct_factor_count": sum(
                    int(inverse.diagnostics.get("direct_factor_count", 0))
                    for inverse in original_side_actions.values()
                ),
                "p4_factor_count": sum(
                    int(inverse.diagnostics.get("p4_factor_count", 0))
                    for inverse in original_side_actions.values()
                ),
                "fixed_physical_balh_action_identity": (
                    FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
                ),
            }
        elif fixed_h6_modal_gmres_research:
            original_side_actions = {
                "bottom": bottom_side_inverse,
                "top": top_side_inverse,
            }
            side_counts_before = {
                side: _action_diagnostics(action).get("apply_count")
                for side, action in original_side_actions.items()
            }
            make_action = (
                SideBalancedInverse.create_fixed_h6_active_trace_action
                if fixed_h6_modal_feedback_method is None
                else SideBalancedInverse.create_fixed_physical_balh_active_trace_action
            )
            fixed_h6_adapters.append(make_action(bottom_side_inverse))
            fixed_h6_adapters.append(make_action(top_side_inverse))
            fixed_h6_solver = _FixedH6ModalKrylovSystem(
                coupling,
                fixed_h6_adapters[0],
                fixed_h6_adapters[1],
                modal_owner=layout.modal_owner,
                feedback_method=fixed_h6_modal_feedback_method,
                modal_solver_policy=modal_solver_policy,
                snapshot_callback=modal_snapshot_callback,
            )
            early_sample_gate = _check_fixed_h6_modal_feedback_repeat_linearity(
                fixed_h6_solver,
                original_side_actions=original_side_actions,
                original_side_apply_counts_before=side_counts_before,
                marker_callback=marker_callback,
            )
            modal_system = _FixedH6ModalGmresResearchBundle(
                fixed_h6_solver,
                fixed_h6_adapters[0],
                fixed_h6_adapters[1],
                coupling=coupling,
                backup_side_inverses=(bottom_side_inverse, top_side_inverse)
                if _task041_modal_policy_allows_backup(
                    fixed_h6_solver.modal_solver_policy
                )
                else None,
                marker_callback=marker_callback,
            )
            fixed_balh_selected = (
                fixed_h6_modal_feedback_method
                == FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD
            )
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": (
                    "fixed_physical_balh_once_modal_gmres_research"
                    if fixed_balh_selected
                    else "fixed_h6_modal_gmres_research"
                ),
                **(
                    {
                        "modal_feedback_method": fixed_h6_modal_feedback_method,
                        "modal_feedback_selection_source": (
                            "registered_w0p7_fixed_h6_consumer_scope"
                        ),
                    }
                    if fixed_balh_selected
                    else {}
                ),
                "modal_block_name": (
                    "fixed_physical_balh_once_on_demand_modal_gmres"
                    if fixed_balh_selected
                    else "fixed_h6_surrogate_on_demand_modal_gmres"
                ),
                "modal_schur_scope": "not_materialized",
                "modal_block_condition_status": "not_measured",
                "not_original_global_operator": True,
                "not_original_reduced_operator": True,
                "borrowed_side_actions": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
                "modal_schur_materialized": False,
                "modal_schur_column_count": 0,
                "modal_schur_condition": "not_measured",
                "full_vs_sample": {
                    "status": "not_applicable",
                    "reason": "full_modal_schur_not_materialized",
                },
                "schur_lu_repeat": {
                    "status": "not_applicable",
                    "reason": "modal_schur_lu_not_constructed",
                },
                "early_sample_gate": early_sample_gate,
                "setup_gate_included_in_whole_run_work": True,
                "side_apply_counts_before_fixed_h6_branch": side_counts_before,
                "modal_solver_policy": (
                    None
                    if fixed_h6_solver.modal_solver_policy is None
                    else dict(fixed_h6_solver.modal_solver_policy)
                ),
                "modal_primary_method": fixed_h6_solver.method,
            }
        else:
            modal_schur = build_hybrid_action_modal_schur(
                coupling,
                bottom_side_inverse,
                top_side_inverse,
                matrix_repeat_tolerance=1.0e-10,
                sampled_columns=sampled_columns,
                sampled_column_roles=sampled_column_roles,
                sampled_column_contract_sha256=sampled_column_contract_sha256,
                modal_batch_size=32,
                early_sample_first=True,
                marker_callback=marker_callback,
            )
            modal_system = modal_schur
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": "BAL_H_side_inverse_response_schur",
                "modal_block_name": (
                    "finite_nonlinear_side_inverse_response_columns"
                ),
                "modal_schur_scope": "approximate_preconditioner_only",
                "not_original_global_operator": True,
                "not_original_reduced_operator": True,
                "borrowed_side_actions": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
            }
        return HybridBlockLduPreconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            ldu_bottom_action,
            ldu_top_action,
            modal_system,
            research_inventory=research_inventory,
            dynamic_side_inventory=not v13_modal_policy,
        )
    except BaseException:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_schur is not None:
            modal_schur.destroy()
        elif modal_action is not None:
            modal_action.destroy()
        elif fixed_h6_solver is not None:
            fixed_h6_solver.destroy()
        for action in reversed(fixed_h6_adapters):
            if not action.audit["destroyed"]:
                action.destroy()
        raise


def create_research_exact_side_lu_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: Any,
    top_system: Any,
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
    *,
    matrix_repeat_tolerance: float = 1.0e-13,
    qualification_scope: str | None = None,
    explicit_opt_in: bool = False,
    sampled_columns: Sequence[int] | None = None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None = None,
    sampled_column_contract_sha256: str | None = None,
    modal_batch_size: int | None = None,
    early_sample_first: bool = False,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> HybridBlockLduPreconditioner:
    """Build historical research LDU or an explicit case-qualified context.

    The default remains research-only; a fixed qualification scope and
    explicit opt-in are required for the case-qualified context.
    """

    actions = {"bottom": bottom_action, "top": top_action}
    for side, action in actions.items():
        diagnostics = _action_diagnostics(action)
        if diagnostics.get("research_only") is not True and not (
            explicit_opt_in and diagnostics.get("case_qualification_opt_in") is True
        ):
            raise ValueError(f"Research exact-side {side} action is not opted in")
        if _direct_factor_count(diagnostics) != 1:
            raise ValueError(
                f"Research exact-side {side} action needs one direct factor"
            )
        if diagnostics.get("global_hybrid_direct_factor_count") != 0:
            raise ValueError("Research exact-side action cannot own a global factor")
        if explicit_opt_in and (
            diagnostics.get("qualification_scope") != qualification_scope
            or diagnostics.get("explicit_opt_in") is not True
            or diagnostics.get("case_qualification_opt_in") is not True
            or diagnostics.get("general_production") is not False
            or diagnostics.get("ordinary_default") is not False
            or diagnostics.get("ordinary_default_changed") is not False
            or diagnostics.get("nested_iterative_ksp_count") != 0
            or diagnostics.get("local_direct_preonly_ksp_count") != 1
        ):
            raise ValueError("Case-qualified exact-side action diagnostics are invalid")
    if (
        (modal_batch_size is not None or early_sample_first)
        and not explicit_opt_in
    ):
        raise ValueError("Modal batching requires explicit case opt-in")
    modal_schur = build_hybrid_action_modal_schur(
        coupling,
        bottom_action,
        top_action,
        matrix_repeat_tolerance=matrix_repeat_tolerance,
        sampled_columns=sampled_columns,
        sampled_column_roles=sampled_column_roles,
        sampled_column_contract_sha256=sampled_column_contract_sha256,
        modal_batch_size=modal_batch_size,
        early_sample_first=early_sample_first,
        marker_callback=marker_callback,
    )
    research_inventory = {
        "global_hybrid_direct_factor_count": 0,
    }
    if not explicit_opt_in:
        research_inventory["research_only_exact_side_lu"] = True
    if explicit_opt_in:
        research_inventory.update(
            {
                "qualification_scope": qualification_scope,
                "explicit_opt_in": True,
                "case_qualification_opt_in": True,
                "ordinary_default": False,
                "ordinary_default_changed": False,
                "general_production": False,
                "nested_iterative_ksp_count": 0,
                "local_direct_preonly_ksp_count": 2,
            }
        )
    try:
        return HybridBlockLduPreconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            bottom_action,
            top_action,
            modal_schur,
            research_inventory=research_inventory,
        )
    except Exception:
        modal_schur.destroy()
        raise


@dataclass(frozen=True)
class HybridBlockLduIterativeConfig:
    """Frozen outer-KSP settings; default FGMRES, opt-in fixed GMRES10."""

    restart: int = 90
    max_it: int = 1000
    threshold: float = 5.0e-9
    initial_guess: str = "zero"
    ksp_type: str = "fgmres"
    fixed_preconditioner: bool = False

    def __post_init__(self) -> None:
        if int(self.restart) <= 0 or int(self.max_it) <= 0:
            raise ValueError("Iterative restart and max_it must be positive.")
        if not np.isfinite(float(self.threshold)) or float(self.threshold) <= 0.0:
            raise ValueError("Iterative threshold must be finite and positive.")
        if self.initial_guess != "zero":
            raise ValueError("Only the zero initial guess is supported.")
        if str(self.ksp_type).lower() not in {"fgmres", "gmres"}:
            raise ValueError("Only FGMRES and GMRES outer KSP types are supported.")
        if str(self.ksp_type).lower() == "gmres" and (
            not self.fixed_preconditioner or int(self.restart) != 10
        ):
            raise ValueError(
                "GMRES is reserved for the fixed-preconditioner restart-10 profile."
            )


@dataclass
class HybridBlockLduIterativeResult:
    """Retained solution and lifecycle evidence after the outer solve."""

    solution: PETSc.Vec
    history: list[dict[str, Any]]
    converged_reason: int
    iterations: int
    final_reported_relative_residual: float
    final_true_relative_residual: float
    block_relative_residuals: dict[str, float]
    postsolve_audit: dict[str, Any]
    release: dict[str, Any]
    inventory: dict[str, Any]
    timing: dict[str, Any]
    _preconditioner: HybridBlockLduPreconditioner | None = field(
        default=None, repr=False
    )
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def history_evaluation_count(self) -> int:
        return int(self.timing.get("history_evaluation_count", len(self.history)))

    @property
    def postsolve_evaluation_count(self) -> int:
        return int(self.timing.get("postsolve_evaluation_count", 1))

    def release_deferred_action_modal_schur(self) -> None:
        if self._preconditioner is None:
            return
        self._preconditioner.release_deferred_action_modal_schur()
        self.release["action_modal_schur_released"] = True

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.release_deferred_action_modal_schur()
        self.solution.destroy()
        self._destroyed = True


def multimetric_true_residual_decision(
    iteration: int,
    residuals: dict[str, Any],
    *,
    max_it: int = 1000,
    threshold: float = 5.0e-9,
    identity: str = "tight_multimetric_true_residual_gate",
) -> dict[str, Any]:
    """Apply the five-residual finite, nonnegative, tight convergence rule."""

    try:
        values = {key: float(residuals[key]) for key in _RESIDUAL_KEYS}
    except (KeyError, TypeError, ValueError):
        values = {key: float("nan") for key in _RESIDUAL_KEYS}
    finite_nonnegative = bool(
        all(np.isfinite(value) and value >= 0.0 for value in values.values())
    )
    positive = bool(
        int(iteration) > 0
        and finite_nonnegative
        and all(value <= float(threshold) for value in values.values())
    )
    if not finite_nonnegative:
        reason = int(PETSc.KSP.ConvergedReason.DIVERGED_NANORINF)
        decision = "DIVERGED_NANORINF"
    elif positive:
        user_reason = getattr(PETSc.KSP.ConvergedReason, "CONVERGED_USER", None)
        reason = int(
            PETSc.KSP.ConvergedReason.CONVERGED_RTOL
            if user_reason is None
            else user_reason
        )
        decision = "CONVERGED_USER" if user_reason is not None else "CONVERGED_RTOL"
    elif int(iteration) >= int(max_it):
        reason = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
        decision = "DIVERGED_MAX_IT"
    else:
        reason = int(PETSc.KSP.ConvergedReason.ITERATING)
        decision = "ITERATING"
    return {
        "identity": identity,
        "iteration": int(iteration),
        "threshold": float(threshold),
        "residuals": values,
        "max_true_residual": float(max(values.values(), default=float("nan"))),
        "all_finite_nonnegative": finite_nonnegative,
        "positive": positive,
        "decision": decision,
        "reason": reason,
    }


def _true_residual_metrics(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
    *,
    audit: dict[str, Any] | None = None,
) -> tuple[float, dict[str, float]]:
    residual = rhs.duplicate()
    operator.mult(solution, residual)
    residual.scale(PETSc.ScalarType(-1.0))
    residual.axpy(PETSc.ScalarType(1.0), rhs)
    rhs_bottom, rhs_top, rhs_modal = context.layout.split(
        rhs, context.bottom_system.b, context.top_system.b
    )
    residual_bottom, residual_top, residual_modal = context.layout.split(
        residual, context.bottom_system.b, context.top_system.b
    )
    solution_bottom, solution_top, solution_modal = context.layout.split(
        solution, context.bottom_system.b, context.top_system.b
    )
    bottom_value = context.bottom_system.A.createVecLeft()
    top_value = context.top_system.A.createVecLeft()
    try:
        context.bottom_system.A.mult(solution_bottom, bottom_value)
        context.top_system.A.mult(solution_top, top_value)
        context._apply_modal_tractions(solution_modal)
        context.coupling.bottom.projection.mult(
            solution_bottom, context._bottom_projection
        )
        context.coupling.top.projection.mult(solution_top, context._top_projection)
        bottom_rhs_norm = float(rhs_bottom.norm())
        bottom_action_norm = float(bottom_value.norm())
        bottom_coupling_norm = float(context._bottom_coupling.norm())
        bottom_scale = max(
            bottom_rhs_norm,
            bottom_action_norm,
            bottom_coupling_norm,
            1.0e-30,
        )
        top_rhs_norm = float(rhs_top.norm())
        top_action_norm = float(top_value.norm())
        top_coupling_norm = float(context._top_coupling.norm())
        top_scale = max(
            top_rhs_norm,
            top_action_norm,
            top_coupling_norm,
            1.0e-30,
        )
        modal_constraint = context.modal_constraint
        modal_rhs_norm = float(np.linalg.norm(rhs_modal))
        bottom_projection_norm = float(
            np.linalg.norm(_replicated_modal_values(context._bottom_projection))
        )
        top_projection_norm = float(
            np.linalg.norm(_replicated_modal_values(context._top_projection))
        )
        modal_constraint_action_norm = float(
            np.linalg.norm(modal_constraint @ solution_modal)
        )
        modal_scale = max(
            modal_rhs_norm,
            bottom_projection_norm,
            top_projection_norm,
            modal_constraint_action_norm,
            1.0e-30,
        )
        global_numerator = float(residual.norm())
        global_rhs_norm = float(rhs.norm())
        global_denominator = max(global_rhs_norm, _TINY)
        bottom_numerator = float(residual_bottom.norm())
        top_numerator = float(residual_top.norm())
        modal_numerator = float(np.linalg.norm(residual_modal))
        block = {
            "bottom": float(bottom_numerator / bottom_scale),
            "top": float(top_numerator / top_scale),
            "modal": float(modal_numerator / modal_scale),
        }
        global_relative = float(global_numerator / global_denominator)
        if audit is not None:
            audit.clear()
            audit.update(
                {
                    "scope": "one_true_residual_snapshot_row",
                    "global": {
                        "numerator_norm": global_numerator,
                        "denominator_norm": global_denominator,
                        "denominator_components": {
                            "original_rhs_norm": global_rhs_norm,
                            "floor": float(_TINY),
                        },
                        "formula": "||A*x-f||/max(||f||,_TINY)",
                        "denominator_scope": "original_rhs_norm_for_this_solve",
                    },
                    "bottom": {
                        "numerator_norm": bottom_numerator,
                        "denominator_norm": float(bottom_scale),
                        "denominator_components": {
                            "rhs_block_norm": bottom_rhs_norm,
                            "A_x_block_norm": bottom_action_norm,
                            "coupling_block_norm": bottom_coupling_norm,
                            "floor": 1.0e-30,
                        },
                        "formula": "||r_bottom||/max(||f_bottom||,||A_bottom*x_bottom||,||coupling_bottom||,1e-30)",
                        "denominator_scope": "recomputed_from_this_true_residual_row",
                    },
                    "top": {
                        "numerator_norm": top_numerator,
                        "denominator_norm": float(top_scale),
                        "denominator_components": {
                            "rhs_block_norm": top_rhs_norm,
                            "A_x_block_norm": top_action_norm,
                            "coupling_block_norm": top_coupling_norm,
                            "floor": 1.0e-30,
                        },
                        "formula": "||r_top||/max(||f_top||,||A_top*x_top||,||coupling_top||,1e-30)",
                        "denominator_scope": "recomputed_from_this_true_residual_row",
                    },
                    "modal": {
                        "numerator_norm": modal_numerator,
                        "denominator_norm": float(modal_scale),
                        "denominator_components": {
                            "rhs_modal_norm": modal_rhs_norm,
                            "bottom_projection_norm": bottom_projection_norm,
                            "top_projection_norm": top_projection_norm,
                            "modal_constraint_action_norm": modal_constraint_action_norm,
                            "floor": 1.0e-30,
                        },
                        "formula": "||r_modal||/max(||f_modal||,||P_bottom*x_bottom||,||P_top*x_top||,||C*x_modal||,1e-30)",
                        "denominator_scope": "recomputed_from_this_true_residual_row",
                    },
                }
            )
    finally:
        top_value.destroy()
        bottom_value.destroy()
        solution_top.destroy()
        solution_bottom.destroy()
        residual_modal = None
        residual_top.destroy()
        residual_bottom.destroy()
        rhs_top.destroy()
        rhs_bottom.destroy()
        residual.destroy()
    return global_relative, block


def _task041_v13_outer_restart_workspace_report(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
    comm: Any,
    *,
    phase: str,
) -> dict[str, Any]:
    """Compare simultaneous KSP+PC and KSP+true-residual payload phases.

    The initial report is made before the original-A validation Vecs and the
    outer KSP are set up, so both are charged as new.  At restart 64, those
    original-A Vecs and the V13 context are already resident in the fresh
    authority sample; only the new KSP workspace and concurrent scratch are
    added.  PC/B scratch is taken from the builder's existing
    ``outer_PC_with_retained_workspaces`` object inventory.  Its forecasted
    retained objects are not charged a second time because they are in the
    current fresh B; its per-apply scratch is included in the PC phase.
    """

    if phase not in {"outer_restart32_workspace", "outer_restart64_workspace"}:
        raise ValueError("V13 outer workspace phase is not registered")
    target_restart = 32 if phase == "outer_restart32_workspace" else 64
    restart32_already_in_fresh_b = phase == "outer_restart64_workspace"
    original_a_binding_already_in_fresh_b = restart32_already_in_fresh_b
    local_error = None
    local_row: dict[str, Any] | None = None
    try:
        if (
            np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
            or np.dtype(PETSc.IntType).itemsize != 4
        ):
            raise RuntimeError("V13 outer workspace model requires complex128/Int32")
        local_rows = int(rhs.getLocalSize())
        local_columns = int(solution.getLocalSize())
        if (
            local_rows < 0
            or local_columns < 0
            or int(rhs.getSize()) != int(operator.getSize()[0])
            or int(solution.getSize()) != int(operator.getSize()[1])
        ):
            raise ValueError("V13 outer Vec ownership does not match the operator")
        pointer_bytes = int(np.dtype(np.uintp).itemsize)
        integer_bytes = int(np.dtype(PETSc.IntType).itemsize)

        def workspace_components(restart: int) -> dict[str, int]:
            # PETSc 3.19.6 FGMRES setup allocates the GMRES row-vector table
            # (m+4 slots) and FGMRES preconditioned-vector table (m+2 slots).
            # The previous eight-slot lump mixed these KSP objects with
            # caller-owned PC and true-residual scratch; keep those separately
            # below so each simultaneous phase is counted once.
            gmres_vector_slots = restart + 4
            fgmres_preconditioned_slots = restart + 2
            vector_entries = (
                gmres_vector_slots * local_rows
                + fgmres_preconditioned_slots * local_columns
            )
            scalar_components = {
                "hh": (restart + 2) * (restart + 1),
                "hes": (restart + 1) * (restart + 1),
                "rs": restart + 2,
                "cc": restart + 1,
                "ss": restart + 1,
                "nrs": restart,
                # Retain the pre-existing conservative two auxiliary
                # (m+2)-scalar tables as explicit payload, not as Vec slots.
                "conservative_auxiliary": 2 * (restart + 2),
            }
            scalar_count = (
                sum(scalar_components.values())
            )
            pointer_count = gmres_vector_slots + fgmres_preconditioned_slots
            work_integer_slots = restart + 4
            return {
                "gmres_vector_slots": gmres_vector_slots,
                "fgmres_preconditioned_vector_slots": fgmres_preconditioned_slots,
                "vector_payload_bytes": (
                    vector_entries * np.dtype(PETSc.ScalarType).itemsize
                ),
                "scalar_array_slots": scalar_count,
                "scalar_payload_bytes": (
                    scalar_count * np.dtype(PETSc.ScalarType).itemsize
                ),
                "pointer_table_slots": pointer_count,
                "pointer_table_bytes": pointer_count * pointer_bytes,
                "PETSc_integer_workspace_slots": work_integer_slots,
                "PETSc_integer_workspace_bytes": work_integer_slots * integer_bytes,
                "workspace_bytes": (
                    vector_entries * np.dtype(PETSc.ScalarType).itemsize
                    + scalar_count * np.dtype(PETSc.ScalarType).itemsize
                    + pointer_count * pointer_bytes
                    + work_integer_slots * integer_bytes
                ),
            }

        restart32_components = workspace_components(32)
        restart64_components = workspace_components(64)
        restart32_bytes = int(restart32_components["workspace_bytes"])
        restart64_bytes = int(restart64_components["workspace_bytes"])

        system = getattr(context, "action_modal_schur_system", None)
        if not isinstance(system, Task041V13ConsistentModalSurrogateSystem):
            raise TypeError("V13 outer workspace requires its actual modal system")
        build_audit = system.build_audit
        workspace_inventory = build_audit.get("workspace_inventory")
        inventory_rows = (
            workspace_inventory.get("rank_rows")
            if isinstance(workspace_inventory, Mapping)
            else None
        )
        sample_cost = build_audit.get("sample8_cost_report")
        sample_projection = (
            sample_cost.get("phase_memory_projection")
            if isinstance(sample_cost, Mapping)
            else None
        )
        sample_phase_reports = (
            sample_projection.get("phase_reports")
            if isinstance(sample_projection, Mapping)
            else None
        )
        builder_pc_phase = (
            sample_phase_reports.get("outer_PC_with_retained_workspaces")
            if isinstance(sample_phase_reports, Mapping)
            else None
        )
        if (
            not isinstance(inventory_rows, list)
            or len(inventory_rows) != int(comm.size)
            or not isinstance(builder_pc_phase, Mapping)
        ):
            raise ValueError("V13 builder did not retain its outer-PC phase inventory")

        def rank_bytes(field: str) -> list[int]:
            values = builder_pc_phase.get(field)
            if (
                not isinstance(values, list)
                or len(values) != int(comm.size)
                or any(type(value) is not int or value < 0 for value in values)
            ):
                raise ValueError(f"V13 builder outer-PC inventory lacks {field}")
            return list(values)

        builder_pc_known = rank_bytes("known_additional_bytes_by_rank")
        builder_pc_temporary = rank_bytes("additional_temporary_bytes_by_rank")
        builder_pc_replicated = rank_bytes("additional_replicated_bytes_by_rank")
        rank_inventory = inventory_rows[int(comm.rank)]
        if (
            not isinstance(rank_inventory, Mapping)
            or int(rank_inventory.get("rank", -1)) != int(comm.rank)
        ):
            raise ValueError("V13 builder workspace inventory rank is incomplete")
        layout_rows = rank_inventory.get("side_layouts")
        if not isinstance(layout_rows, Mapping):
            raise TypeError("V13 builder side-layout inventory is absent")
        bottom_layout = layout_rows.get("bottom")
        top_layout = layout_rows.get("top")
        if not isinstance(bottom_layout, Mapping) or not isinstance(top_layout, Mapping):
            raise TypeError("V13 builder side layout rows are incomplete")
        bottom_rows = int(bottom_layout["active_operator_local_left_entries"])
        top_rows = int(top_layout["active_operator_local_left_entries"])
        modal_count = int(context.layout.modal_count)
        original_bind_entries = local_rows + 2 * local_columns
        if int(rank_inventory.get("original_A_validation_vec_entries", -1)) != (
            original_bind_entries
        ):
            raise ValueError(
                "V13 original-A Vec layouts differ from the builder's validated layout"
            )
        scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
        original_bind_bytes = original_bind_entries * scalar_bytes
        # _true_residual_metrics holds one full residual, the three rhs/residual/
        # solution bottom+top splits, and two side-A values concurrently.
        residual_petcs_entries = (
            local_rows + 4 * (bottom_rows + top_rows)
        )
        residual_petcs_bytes = residual_petcs_entries * scalar_bytes
        modal_owner = int(context.layout.modal_owner)
        # Three split() results remain live.  On the owner, each split also
        # makes a local modal copy before its replicated broadcast result.
        residual_modal_array_slots = 3 + (3 if int(comm.rank) == modal_owner else 0)
        # The denominator calculation additionally materializes one modal
        # projection/constraint product at a time while the split results live.
        residual_modal_array_slots += 1
        residual_modal_bytes = residual_modal_array_slots * modal_count * scalar_bytes
        # The exact-zero original-A modal-row check can hold rhs, two uncancelled
        # terms, their sum/residual, and owner-local copies.  Count the source-
        # visible worst branch separately from the builder's B-action inventory.
        modal_row_callback_slots = 5 + (3 if int(comm.rank) == modal_owner else 0)
        modal_row_callback_bytes = modal_row_callback_slots * modal_count * scalar_bytes

        workspace = restart32_components if target_restart == 32 else restart64_components
        ksp_bytes = int(workspace["workspace_bytes"])
        new_bind_bytes = (
            0 if original_a_binding_already_in_fresh_b else original_bind_bytes
        )
        known_common = ksp_bytes + new_bind_bytes
        pc_temporary = int(builder_pc_temporary[int(comm.rank)])
        pc_replicated = (
            int(builder_pc_replicated[int(comm.rank)]) + modal_row_callback_bytes
        )
        residual_temporary = residual_petcs_bytes
        residual_replicated = residual_modal_bytes
        pc_phase_rank_bytes = known_common + pc_temporary + pc_replicated
        residual_phase_rank_bytes = (
            known_common + residual_temporary + residual_replicated
        )
        local_row = {
            "rank": int(comm.rank),
            "operator_local_rows": local_rows,
            "operator_local_columns": local_columns,
            "complex_scalar_bytes": scalar_bytes,
            "pointer_bytes": pointer_bytes,
            "PETSc_integer_bytes": integer_bytes,
            "restart32_KSP_workspace_components": restart32_components,
            "restart64_KSP_workspace_components": restart64_components,
            "restart32_workspace_bytes": restart32_bytes,
            "restart64_workspace_bytes": restart64_bytes,
            "builder_outer_PC_phase_known_bytes_not_readded": int(
                builder_pc_known[int(comm.rank)]
            ),
            "builder_outer_PC_phase_temporary_bytes": pc_temporary,
            "builder_outer_PC_phase_replicated_bytes": int(
                builder_pc_replicated[int(comm.rank)]
            ),
            "original_A_binding_vec_entries": original_bind_entries,
            "original_A_binding_vec_bytes": original_bind_bytes,
            "original_A_binding_already_in_fresh_B": (
                original_a_binding_already_in_fresh_b
            ),
            "true_residual_bottom_local_rows": bottom_rows,
            "true_residual_top_local_rows": top_rows,
            "true_residual_PETSc_vec_entries": residual_petcs_entries,
            "true_residual_PETSc_vec_bytes": residual_petcs_bytes,
            "true_residual_modal_array_slots": residual_modal_array_slots,
            "true_residual_modal_array_bytes": residual_modal_bytes,
            "original_A_modal_row_callback_array_slots": modal_row_callback_slots,
            "original_A_modal_row_callback_array_bytes": modal_row_callback_bytes,
            "target_restart": target_restart,
            "modal_count": modal_count,
            "modal_owner": modal_owner,
            "PC_phase_additional_bytes": pc_phase_rank_bytes,
            "original_A_residual_phase_additional_bytes": residual_phase_rank_bytes,
            "selected_phase_additional_bytes": max(
                pc_phase_rank_bytes, residual_phase_rank_bytes
            ),
        }
    except Exception as exc:  # noqa: BLE001 - synchronize local Vec/model errors
        local_error = f"{type(exc).__name__}: {exc}"
    rows = comm.allgather((local_error, local_row))
    errors = [
        f"rank {rank}: {error}"
        for rank, (error, _row) in enumerate(rows)
        if error is not None
    ]
    rank_rows = [row for error, row in rows if error is None]
    if errors or len(rank_rows) != int(comm.size):
        raise RuntimeError(
            "V13 outer restart workspace model failed collectively: "
            + "; ".join(errors)
        )
    if [row.get("rank") for row in rank_rows] != list(range(int(comm.size))):
        raise RuntimeError("V13 outer restart workspace rank order is invalid")
    global_rows = sum(int(row["operator_local_rows"]) for row in rank_rows)
    global_columns = sum(int(row["operator_local_columns"]) for row in rank_rows)
    matrix_rows, matrix_columns = map(int, operator.getSize())
    if global_rows != matrix_rows or global_columns != matrix_columns:
        raise RuntimeError("V13 outer restart Vec ownership is incomplete")
    known = [
        int(row["restart32_workspace_bytes"] if target_restart == 32 else row["restart64_workspace_bytes"])
        + (
            0
            if original_a_binding_already_in_fresh_b
            else int(row["original_A_binding_vec_bytes"])
        )
        for row in rank_rows
    ]
    phase_reports = {
        "outer_PC_with_retained_workspaces": {
            "known_additional_bytes_by_rank": known,
            "additional_temporary_bytes_by_rank": [
                int(row["builder_outer_PC_phase_temporary_bytes"])
                for row in rank_rows
            ],
            "additional_replicated_bytes_by_rank": [
                int(row["builder_outer_PC_phase_replicated_bytes"])
                + int(row["original_A_modal_row_callback_array_bytes"])
                for row in rank_rows
            ],
        },
        "outer_original_A_true_residual": {
            "known_additional_bytes_by_rank": known,
            "additional_temporary_bytes_by_rank": [
                int(row["true_residual_PETSc_vec_bytes"]) for row in rank_rows
            ],
            "additional_replicated_bytes_by_rank": [
                int(row["true_residual_modal_array_bytes"]) for row in rank_rows
            ],
        },
    }
    for components in phase_reports.values():
        components["additional_bytes_by_rank"] = [
            components["known_additional_bytes_by_rank"][rank]
            + components["additional_temporary_bytes_by_rank"][rank]
            + components["additional_replicated_bytes_by_rank"][rank]
            for rank in range(int(comm.size))
        ]
    phase_totals = {
        name: sum(components["additional_bytes_by_rank"])
        for name, components in phase_reports.items()
    }
    selected_phase = max(phase_totals, key=phase_totals.get)
    selected = phase_reports[selected_phase]
    additional = list(selected["additional_bytes_by_rank"])
    selected_known = list(selected["known_additional_bytes_by_rank"])
    temporary = list(selected["additional_temporary_bytes_by_rank"])
    replicated = list(selected["additional_replicated_bytes_by_rank"])
    total = sum(additional)
    return {
        "phase": phase,
        "target_restart": target_restart,
        "workspace_model": (
            "petsc-3.19.6-fgmres-v-z-scalar-pointer-plus-live-phase-inventory-v1"
        ),
        "workspace_model_scope": (
            "source-derived countable slots plus exact builder PC/B inventory and "
            "V13 original-A temporary layouts; not an RSS upper bound"
        ),
        "restart32_workspace_is_already_in_fresh_B": (
            restart32_already_in_fresh_b
        ),
        "restart32_workspace_is_charged_as_new": not restart32_already_in_fresh_b,
        "original_A_binding_vecs_are_already_in_fresh_B": (
            original_a_binding_already_in_fresh_b
        ),
        "builder_outer_PC_phase_source": (
            "modal_system.build_audit.sample8_cost_report.phase_memory_projection."
            "phase_reports.outer_PC_with_retained_workspaces"
        ),
        "builder_outer_PC_known_additions_reused_as_delta": False,
        "builder_outer_PC_temporary_and_replicated_payload_reused": True,
        "outer_restart_workspace_by_rank": rank_rows,
        "existing_restart32_workspace_bytes_by_rank": [
            int(row["restart32_workspace_bytes"])
            if restart32_already_in_fresh_b
            else 0
            for row in rank_rows
        ],
        "restart64_workspace_bytes_by_rank": [
            int(row["restart64_workspace_bytes"]) for row in rank_rows
        ],
        "target_restart_workspace_bytes_by_rank": [
            int(row["restart32_workspace_bytes"] if target_restart == 32 else row["restart64_workspace_bytes"])
            for row in rank_rows
        ],
        "known_additional_bytes_by_rank": selected_known,
        "additional_bytes_by_rank": additional,
        "additional_temporary_bytes_by_rank": temporary,
        "additional_replicated_bytes_by_rank": replicated,
        "unitemized_allocator_and_MPI_scratch": (
            "unknown; W_policy_reserve_is_applied_separately"
        ),
        "original_A_binding_vec_bytes_by_rank": [
            int(row["original_A_binding_vec_bytes"]) for row in rank_rows
        ],
        "true_residual_PETSc_vec_bytes_by_rank": [
            int(row["true_residual_PETSc_vec_bytes"]) for row in rank_rows
        ],
        "true_residual_modal_array_bytes_by_rank": [
            int(row["true_residual_modal_array_bytes"]) for row in rank_rows
        ],
        "phase_memory_projection": {
            "scope": "max_simultaneous_KSP_plus_PC_or_original_A_residual_phase",
            "phase_reports": phase_reports,
            "phase_total_bytes": phase_totals,
            "selected_phase": selected_phase,
            "selected_phase_payload_bytes": total,
        },
    }


def _task041_v13_true_residual_operands_match(
    audit: Any, residual_values: Mapping[str, float]
) -> bool:
    """Check each recorded ratio against its existing row-local denominator."""

    if (
        not isinstance(audit, Mapping)
        or audit.get("scope") != "one_true_residual_snapshot_row"
    ):
        return False
    specifications = {
        "global": (
            "global_true_relative_residual",
            "original_rhs_norm_for_this_solve",
            {"original_rhs_norm", "floor"},
        ),
        "bottom": (
            "bottom_true_relative_residual",
            "recomputed_from_this_true_residual_row",
            {"rhs_block_norm", "A_x_block_norm", "coupling_block_norm", "floor"},
        ),
        "top": (
            "top_true_relative_residual",
            "recomputed_from_this_true_residual_row",
            {"rhs_block_norm", "A_x_block_norm", "coupling_block_norm", "floor"},
        ),
        "modal": (
            "modal_true_relative_residual",
            "recomputed_from_this_true_residual_row",
            {
                "rhs_modal_norm",
                "bottom_projection_norm",
                "top_projection_norm",
                "modal_constraint_action_norm",
                "floor",
            },
        ),
    }
    for section, (metric, expected_scope, expected_components) in specifications.items():
        record = audit.get(section)
        components = (
            record.get("denominator_components")
            if isinstance(record, Mapping)
            else None
        )
        if (
            not isinstance(record, Mapping)
            or record.get("denominator_scope") != expected_scope
            or not isinstance(components, Mapping)
            or not expected_components.issubset(components)
        ):
            return False
        try:
            numerator = float(record["numerator_norm"])
            denominator = float(record["denominator_norm"])
            component_values = [float(components[name]) for name in expected_components]
            recomputed_denominator = max(component_values)
            recomputed_ratio = numerator / denominator
            observed_ratio = float(residual_values[metric])
        except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
            return False
        if (
            not np.isfinite(numerator)
            or numerator < 0.0
            or not np.isfinite(denominator)
            or denominator <= 0.0
            or any(
                not np.isfinite(component) or component < 0.0
                for component in component_values
            )
            or not np.isclose(
                denominator, recomputed_denominator, rtol=1.0e-12, atol=0.0
            )
            or not np.isclose(
                observed_ratio, recomputed_ratio, rtol=1.0e-12, atol=0.0
            )
        ):
            return False
    return True


def _task041_v13_outer_restart_loss_evidence(
    history_by_iteration: Mapping[int, Mapping[str, Any]], *, threshold: float
) -> dict[str, Any]:
    """Compare equal 16-step true-residual windows before and after restart.

    This is a predeclared progress-loss heuristic, not a convergence theorem.
    Residuals use the existing full true-residual formulas: global residuals
    are divided by the original RHS norm, while each block denominator is
    recomputed from that row's existing RHS/action/coupling terms.  Those
    operands are retained with every sample.  A restart is only a candidate when
    the pre-window made material global progress and the post-window does not
    make material progress on the global residual or any still-unpassed block.
    """

    keys = (
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    pre_iterations = tuple(range(16, 33))
    post_iterations = tuple(range(32, 49))
    pre_rows = [history_by_iteration.get(index) for index in pre_iterations]
    post_rows = [history_by_iteration.get(index) for index in post_iterations]
    pre_baseline = history_by_iteration.get(16)
    boundary = history_by_iteration.get(32)
    minimum_progress = float(
        _TASK041_V13_CONSISTENT_MODAL_POLICY[
            "outer_restart_loss_minimum_progress_fraction"
        ]
    )
    threshold_value = float(threshold)

    def sample_rows(
        iterations: Sequence[int], rows: Sequence[Mapping[str, Any] | None]
    ) -> list[dict[str, Any]]:
        output = []
        for iteration, row in zip(iterations, rows, strict=True):
            if not isinstance(row, Mapping):
                continue
            values = {}
            for key in keys:
                try:
                    values[key] = float(row[key])
                except (KeyError, TypeError, ValueError, OverflowError):
                    values = {}
                    break
            row_audit = row.get("true_residual_operands")
            if values and _task041_v13_true_residual_operands_match(
                row_audit, values
            ):
                output.append(
                    {
                        "iteration": iteration,
                        "residuals": values,
                        "true_residual_operands": dict(row_audit),
                    }
                )
        return output

    pre_samples = sample_rows(pre_iterations, pre_rows)
    post_samples = sample_rows(post_iterations, post_rows)

    def incomplete(status: str) -> dict[str, Any]:
        return {
            "rule_id": _TASK041_V13_CONSISTENT_MODAL_POLICY[
                "outer_restart_loss_evidence_rule"
            ],
            "boundary_iteration": 32,
            "pre_window": [16, 32],
            "post_window": [32, 48],
            "steps_per_window": 16,
            "minimum_progress_fraction": minimum_progress,
            "denominator_basis": {
                "global": "original_rhs_norm_for_this_solve",
                "bottom_top_modal": (
                    "existing per-row component-max formula with operands retained per sample"
                ),
            },
            "pre_window_baseline_iteration": 16,
            "restart_boundary_baseline_iteration": 32,
            "pre_window_samples": pre_samples,
            "post_window_samples": post_samples,
            "clear_restart_loss": False,
            "evidence_status": status,
        }

    if (
        len(pre_samples) != len(pre_iterations)
        or len(post_samples) != len(post_iterations)
        or not isinstance(boundary, Mapping)
        or not isinstance(pre_baseline, Mapping)
    ):
        return incomplete("missing_complete_pre_or_post_true_residual_window")

    pre_values = [item["residuals"] for item in pre_samples]
    post_values = [item["residuals"] for item in post_samples]
    finite = all(
        np.isfinite(value) and value >= 0.0
        for values in (*pre_values, *post_values)
        for value in values.values()
    ) and np.isfinite(threshold_value) and threshold_value >= 0.0
    if not finite:
        return incomplete("nonfinite_or_negative_true_residual_or_threshold")

    pre_baseline_values = {
        key: float(pre_baseline[key]) for key in keys
    }
    boundary_values = {key: float(boundary[key]) for key in keys}
    required = [
        key
        for key in keys
        if key == "global_true_relative_residual"
        or boundary_values[key] > threshold_value
    ]

    pre_best = {key: min(row[key] for row in pre_values) for key in keys}
    post_best = {key: min(row[key] for row in post_values) for key in keys}

    def improvement_fraction(baseline: float, best: float) -> float | None:
        if baseline < 0.0 or best < 0.0 or best > baseline:
            return None
        if baseline == 0.0:
            return 0.0
        return float((baseline - best) / baseline)

    pre_improvement = {
        key: improvement_fraction(pre_baseline_values[key], pre_best[key])
        for key in keys
    }
    post_improvement = {
        key: improvement_fraction(boundary_values[key], post_best[key])
        for key in keys
    }
    if any(value is None for value in (*pre_improvement.values(), *post_improvement.values())):
        return incomplete("invalid_window_baseline_or_best_relationship")

    pre_global_improvement = pre_improvement["global_true_relative_residual"]
    pre_global_progress = bool(
        pre_global_improvement is not None
        and pre_global_improvement >= minimum_progress
    )
    post_unpassed_improvements = {
        key: post_improvement[key] for key in required
    }
    post_is_stalled = all(
        value is not None and value < minimum_progress
        for value in post_unpassed_improvements.values()
    )
    no_unpassed_block_effective_improvement = all(
        key == "global_true_relative_residual"
        or (
            post_improvement[key] is not None
            and post_improvement[key] < minimum_progress
        )
        for key in required
    )
    clear = bool(
        pre_global_progress
        and post_is_stalled
        and no_unpassed_block_effective_improvement
    )
    return {
        "rule_id": _TASK041_V13_CONSISTENT_MODAL_POLICY[
            "outer_restart_loss_evidence_rule"
        ],
        "boundary_iteration": 32,
        "pre_window": [16, 32],
        "post_window": [32, 48],
        "steps_per_window": 16,
        "minimum_progress_fraction": minimum_progress,
        "denominator_basis": {
            "global": "original_rhs_norm_for_this_solve",
            "bottom_top_modal": (
                "existing per-row component-max formula with operands retained per sample"
            ),
        },
        "pre_window_baseline_iteration": 16,
        "restart_boundary_baseline_iteration": 32,
        "required_unpassed_metrics_at_boundary": required,
        "pre_window_baseline_by_metric": pre_baseline_values,
        "pre_window_best_by_metric": pre_best,
        "pre_window_improvement_fraction_by_metric": pre_improvement,
        "restart_boundary_baseline_by_metric": boundary_values,
        "post_window_best_by_metric": post_best,
        "post_window_improvement_fraction_by_metric": post_improvement,
        "pre_restart_global_progress_at_least_10_percent": pre_global_progress,
        "post_restart_global_and_unpassed_blocks_below_10_percent": post_is_stalled,
        "unpassed_blocks_with_sustained_effective_progress": [
            key
            for key in required
            if key != "global_true_relative_residual"
            and post_improvement[key] is not None
            and post_improvement[key] >= minimum_progress
        ],
        "pre_window_samples": pre_samples,
        "post_window_samples": post_samples,
        "clear_restart_loss": clear,
        "evidence_status": "evaluated",
        "evidence_interpretation": (
            "heuristic_candidate_only; not_a_convergence_theorem"
        ),
    }


def _task041_v13_merge_running_best(
    previous: Mapping[str, float], current: Mapping[str, float]
) -> dict[str, float]:
    """Never raise a stalled-window baseline after a worse full window."""

    keys = (
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    return {
        key: min(float(previous[key]), float(current[key])) for key in keys
    }


def _task041_v13_outer_best_window(
    baseline: Mapping[str, float],
    samples: Sequence[Mapping[str, Any]],
    *,
    start_iteration: int,
    end_iteration: int,
    threshold: float,
) -> dict[str, Any]:
    """Summarize one exact 16-step window using its best true residuals."""

    keys = (
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    if (
        end_iteration - start_iteration != 16
        or len(samples) != 16
        or any(
            int(row.get("iteration", -1)) != start_iteration + offset + 1
            for offset, row in enumerate(samples)
        )
    ):
        return {
            "start_iteration": int(start_iteration),
            "end_iteration": int(end_iteration),
            "status": "incomplete_true_residual_window",
            "stalled": False,
        }
    values = [
        {key: float(row[key]) for key in keys} for row in samples
    ]
    denominator_records: list[dict[str, Any]] = []
    for row, residual_values in zip(samples, values, strict=True):
        row_audit = row.get("true_residual_operands")
        if not _task041_v13_true_residual_operands_match(
            row_audit, residual_values
        ):
            return {
                "start_iteration": int(start_iteration),
                "end_iteration": int(end_iteration),
                "status": "missing_or_inconsistent_true_residual_denominator_operands",
                "stalled": False,
            }
        denominator_records.append(dict(row_audit))
    if any(
        not np.isfinite(value) or value < 0.0
        for row in values
        for value in row.values()
    ):
        return {
            "start_iteration": int(start_iteration),
            "end_iteration": int(end_iteration),
            "status": "invalid_true_residual_window",
            "stalled": False,
        }
    best = {key: min(row[key] for row in values) for key in keys}
    end = dict(values[-1])
    improvement: dict[str, float | None] = {}
    for key in keys:
        base = float(baseline[key])
        if base <= 0.0:
            improvement[key] = 0.0 if best[key] == 0.0 else None
        else:
            fraction = (base - best[key]) / base
            improvement[key] = float(fraction) if np.isfinite(fraction) else None
    unmet = [key for key in keys if end[key] > float(threshold)]
    stalled = bool(
        unmet
        and all(
            improvement[key] is not None and float(improvement[key]) < 0.10
            for key in unmet
        )
    )
    return {
        "start_iteration": int(start_iteration),
        "end_iteration": int(end_iteration),
        "status": "complete",
        "baseline_best_by_metric": dict(baseline),
        "best_by_metric": best,
        "end_by_metric": end,
        "improvement_fraction_by_metric": improvement,
        "unmet_metrics_at_end": unmet,
        "stalled": stalled,
        "sample_count": 16,
        "interpretation": "predeclared_16_step_best_residual_stagnation_heuristic",
        "samples": [
            {
                "iteration": int(row["iteration"]),
                "residuals": values[index],
                "true_residual_operands": denominator_records[index],
            }
            for index, row in enumerate(samples)
        ],
    }


def solve_hybrid_block_ldu_iterative(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
    *,
    config: HybridBlockLduIterativeConfig | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> HybridBlockLduIterativeResult:
    """Run right FGMRES with one cached true-residual row per iteration."""

    config = HybridBlockLduIterativeConfig() if config is None else config
    if context._destroyed:
        raise RuntimeError("Cannot solve with a destroyed block-LDU context.")
    if context.requires_right_fgmres and str(config.ksp_type).lower() != "fgmres":
        raise ValueError(
            "The selected modal inner requires right-preconditioned FGMRES."
        )
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    retained_solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution.set(0.0)
    retained_solution.set(0.0)
    history: list[dict[str, Any]] = []
    history_cache: dict[int, dict[str, Any]] = {}
    history_evaluations = 0
    started = time.perf_counter()
    outer_comm = operator.getComm().tompi4py()
    rhs_norm = max(float(rhs.norm()), _TINY)
    v13_modal_system = (
        context.action_modal_schur_system
        if isinstance(
            context.action_modal_schur_system,
            Task041V13ConsistentModalSurrogateSystem,
        )
        else None
    )
    v13_outer_enabled = v13_modal_system is not None
    if v13_outer_enabled and (
        str(config.ksp_type).lower() != "fgmres"
        or float(config.threshold)
        != float(_TASK041_V13_CONSISTENT_MODAL_POLICY["outer_threshold"])
    ):
        raise ValueError(
            "V13 outer solve requires the original right-FGMRES and 5e-9 residual gate"
        )
    current_outer_restart = (
        int(_TASK041_V13_CONSISTENT_MODAL_POLICY["outer_restart_initial"])
        if v13_outer_enabled
        else int(config.restart)
    )
    outer_krylov_origin = 0
    outer_iteration_offset = 0
    v13_seen_iterations: set[int] = set()
    v13_window_records: list[dict[str, Any]] = []
    v13_window_baseline: dict[str, float] | None = None
    v13_window_segment_start = 32
    v13_consecutive_stalled_windows = 0
    v13_restart64_pending: dict[str, Any] | None = None
    v13_finite_stop_pending: dict[str, Any] | None = None
    v13_outer_control: dict[str, Any] = {
        "schema": "task041.v13.outer_control.v1",
        "policy_id": TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
        "enabled": bool(v13_outer_enabled),
        "initial_restart": int(current_outer_restart),
        "configured_max_it": int(config.max_it),
        "final_restart": int(current_outer_restart),
        "restart64_trial_count": 0,
        "restart_history": [
            {"iteration": 0, "restart": int(current_outer_restart), "reason": "initial"}
        ]
        if v13_outer_enabled
        else [],
        "restart64_evidence": None,
        "restart64_authority": None,
        "finite_stop_windows": v13_window_records,
        "finite_stop": None,
        "residual_samples": [],
        "workspace_unknowns": (
            "allocator/MPI scratch remain represented only by the independent policy W"
            if v13_outer_enabled
            else None
        ),
    }
    modal_bundle_for_stop = context.action_modal_schur_system
    backup_policy_for_stop = (
        isinstance(modal_bundle_for_stop, _FixedH6ModalGmresResearchBundle)
        and modal_bundle_for_stop._solver is not None
        and _task041_modal_policy_allows_backup(
            modal_bundle_for_stop._solver.modal_solver_policy
        )
    )
    rhs_local_sha256_at_entry = None
    if backup_policy_for_stop:
        rhs_local_sha256_at_entry = hashlib.sha256(
            np.ascontiguousarray(
                np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
            ).tobytes()
        ).hexdigest()
    v13_rhs_local_sha256_at_entry = None
    if v13_outer_enabled:
        v13_rhs_local_sha256_at_entry = hashlib.sha256(
            np.ascontiguousarray(
                np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
            ).tobytes()
        ).hexdigest()
    ksp = PETSc.KSP().create(operator.getComm())
    returned = False

    def snapshot(
        iteration: int,
        reported: float,
        current: PETSc.KSP | None,
    ) -> dict[str, Any]:
        nonlocal history_evaluations
        if int(iteration) in history_cache:
            return history_cache[int(iteration)]
        if current is None:
            solution.copy(monitor_solution)
            current_solution = monitor_solution
        else:
            current_solution = current.buildSolution(monitor_solution)
        residual_operand_audit: dict[str, Any] | None = (
            {} if v13_outer_enabled else None
        )
        global_true, block = _true_residual_metrics(
            operator,
            rhs,
            current_solution,
            context,
            audit=residual_operand_audit,
        )
        inventory = context.inventory
        row = {
            "iteration": int(iteration),
            "reported_relative_residual": float(reported),
            "global_true_relative_residual": float(global_true),
            "bottom_true_relative_residual": float(block["bottom"]),
            "top_true_relative_residual": float(block["top"]),
            "modal_true_relative_residual": float(block["modal"]),
            "pc_apply_count": int(inventory["pc_apply_count"]),
            "bottom_action_apply_count": int(
                inventory["bottom_action_apply_count"]
            ),
            "top_action_apply_count": int(inventory["top_action_apply_count"]),
            "elapsed_seconds": float(time.perf_counter() - started),
        }
        if v13_outer_enabled:
            row["true_residual_operands"] = residual_operand_audit
            relative_iteration = int(iteration) - int(outer_krylov_origin)
            is_registered_checkpoint = int(iteration) in {1, 4, 8, 16, 32}
            is_restart_boundary = bool(
                relative_iteration > 0
                and relative_iteration % int(current_outer_restart) == 0
            )
            row["task041_v13_outer_checkpoint"] = bool(
                is_registered_checkpoint or is_restart_boundary
            )
            row["task041_v13_restart_boundary"] = (
                bool(is_restart_boundary)
            )
            row["task041_v13_effective_restart"] = int(current_outer_restart)
            if is_registered_checkpoint or is_restart_boundary or int(iteration) == 48:
                local_solution = np.asarray(
                    current_solution.getArray(readonly=True), dtype=np.complex128
                )
                row["solution_local_sha256"] = hashlib.sha256(
                    np.ascontiguousarray(local_solution).tobytes()
                ).hexdigest()
                row["solution_ownership_range"] = [
                    int(value) for value in current_solution.getOwnershipRange()
                ]
                row["solution_finite_local"] = bool(
                    np.isfinite(local_solution).all()
                )
        modal_inner = inventory.get("modal_inner_solver")
        if isinstance(modal_inner, dict):
            last_inner = modal_inner.get("last_solve") or {}
            row.update(
                {
                    "modal_inner_solve_count": int(modal_inner["solve_count"]),
                    "modal_inner_s_evaluation_count": int(
                        modal_inner["s_evaluation_count"]
                    ),
                    "modal_inner_not_converged_count": int(
                        modal_inner["not_converged_count"]
                    ),
                    "modal_inner_last_stop_reason": last_inner.get("stop_reason"),
                    "modal_inner_last_raw_residual_norm": last_inner.get(
                        "unscaled_residual_norm"
                    ),
                }
            )
        decision = multimetric_true_residual_decision(
            int(iteration),
            row,
            max_it=config.max_it,
            threshold=config.threshold,
        )
        modal_bundle = context.action_modal_schur_system
        if (
            isinstance(modal_bundle, _FixedH6ModalGmresResearchBundle)
        ):
            if decision["decision"] == "ITERATING":
                backup_observation = modal_bundle.observe_outer_true_residual(
                    row, gate_threshold=float(decision["threshold"])
                )
                if backup_observation is not None:
                    row["modal_backup_stagnation_observation"] = (
                        backup_observation
                    )
            else:
                modal_bundle.record_outer_terminal(decision)
        row.update(
            {
                "multimetric_decision": decision["decision"],
                "multimetric_reason": decision["reason"],
                "multimetric_max_true_residual": decision["max_true_residual"],
            }
        )
        history.append(row)
        history_cache[int(iteration)] = row
        history_evaluations += 1
        if progress_callback is not None and (
            not v13_outer_enabled or current is None
        ):
            progress_callback(dict(row))
        return row

    def observe_v13_outer_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
        nonlocal v13_window_baseline, v13_consecutive_stalled_windows
        nonlocal v13_restart64_pending, v13_finite_stop_pending
        if not v13_outer_enabled:
            return None
        iteration = int(row["iteration"])
        if iteration in v13_seen_iterations:
            return None
        v13_seen_iterations.add(iteration)
        residual_fields = (
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        )
        residuals = {key: float(row[key]) for key in residual_fields}
        if any(not np.isfinite(value) or value < 0.0 for value in residuals.values()):
            return None
        if row.get("task041_v13_outer_checkpoint") is True:
            v13_outer_control["residual_samples"].append(
                {
                    "iteration": iteration,
                    "residuals": dict(residuals),
                    "true_residual_operands": dict(
                        row["true_residual_operands"]
                    ),
                    "elapsed_seconds": float(row["elapsed_seconds"]),
                    "pc_apply_count": int(row["pc_apply_count"]),
                    "bottom_action_apply_count": int(
                        row["bottom_action_apply_count"]
                    ),
                    "top_action_apply_count": int(row["top_action_apply_count"]),
                }
            )
        threshold = float(
            _TASK041_V13_CONSISTENT_MODAL_POLICY["outer_threshold"]
        )
        if iteration == 32:
            v13_window_baseline = dict(residuals)

        if (
            iteration == 48
            and v13_restart64_pending is None
            and v13_outer_control.get("restart64_decision_resolved") is not True
        ):
            evidence = _task041_v13_outer_restart_loss_evidence(
                history_cache, threshold=threshold
            )
            restart_loss = bool(evidence["clear_restart_loss"])
            signature = json.dumps(
                evidence, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            signatures = outer_comm.allgather(signature)
            if any(value != signatures[0] for value in signatures[1:]):
                raise RuntimeError(
                    "V13 outer restart-loss evidence differs across ranks"
                )
            v13_outer_control["restart64_evidence"] = evidence
            if restart_loss:
                v13_restart64_pending = {
                    "status": "restart64_candidate_at_safe_boundary",
                    "evidence": evidence,
                    "observed_at_iteration": iteration,
                }
                row["task041_v13_outer_checkpoint"] = True
                row["task041_v13_restart_transition_boundary"] = True
                if not any(
                    int(item.get("iteration", -1)) == iteration
                    for item in v13_outer_control["residual_samples"]
                ):
                    v13_outer_control["residual_samples"].append(
                        {
                            "iteration": iteration,
                            "residuals": dict(residuals),
                            "true_residual_operands": dict(
                                row["true_residual_operands"]
                            ),
                            "elapsed_seconds": float(row["elapsed_seconds"]),
                            "pc_apply_count": int(row["pc_apply_count"]),
                            "bottom_action_apply_count": int(
                                row["bottom_action_apply_count"]
                            ),
                            "top_action_apply_count": int(
                                row["top_action_apply_count"]
                            ),
                            "solution_local_sha256": row.get(
                                "solution_local_sha256"
                            ),
                        }
                    )
                return dict(v13_restart64_pending)
            v13_outer_control["restart64_decision_resolved"] = True
            v13_outer_control["restart64_decision"] = {
                "status": "retained_restart32_no_clear_restart_loss",
                "evidence": evidence,
            }

        if (
            iteration > v13_window_segment_start
            and (iteration - v13_window_segment_start) % 16 == 0
            and v13_window_baseline is not None
            and v13_outer_control.get("restart64_decision_resolved") is True
            and v13_restart64_pending is None
        ):
            start_iteration = iteration - 15
            boundary_iteration = iteration - 16
            boundary_row = history_cache.get(boundary_iteration)
            samples = [
                history_cache.get(index)
                for index in range(start_iteration, iteration + 1)
            ]
            if not isinstance(boundary_row, Mapping) or not all(
                isinstance(sample, Mapping) for sample in samples
            ):
                record = {
                    "start_iteration": boundary_iteration,
                    "end_iteration": iteration,
                    "status": "incomplete_true_residual_window",
                    "stalled": False,
                }
                v13_window_records.append(record)
                v13_consecutive_stalled_windows = 0
                return None
            record = _task041_v13_outer_best_window(
                v13_window_baseline,
                [sample for sample in samples if isinstance(sample, Mapping)],
                start_iteration=iteration - 16,
                end_iteration=iteration,
                threshold=threshold,
            )
            if record.get("status") != "complete":
                v13_window_records.append(record)
                v13_consecutive_stalled_windows = 0
                return None
            boundary_values = {
                key: float(boundary_row[key])
                for key in residual_fields
            }
            if any(
                not np.isfinite(value) or value < 0.0
                for value in boundary_values.values()
            ):
                record = {
                    "start_iteration": boundary_iteration,
                    "end_iteration": iteration,
                    "status": "invalid_shared_window_boundary",
                    "stalled": False,
                }
                v13_window_records.append(record)
                v13_consecutive_stalled_windows = 0
                return None
            record["start_boundary_iteration"] = boundary_iteration
            record["start_boundary_true_residuals"] = boundary_values
            best = dict(record["best_by_metric"])
            stalled = bool(record["stalled"])
            canonical = json.dumps(
                record, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            window_signatures = outer_comm.allgather(canonical)
            if any(value != window_signatures[0] for value in window_signatures[1:]):
                raise RuntimeError("V13 outer 16-step window differs across ranks")
            v13_window_records.append(record)
            v13_window_records[:] = v13_window_records[-4:]
            v13_consecutive_stalled_windows = (
                v13_consecutive_stalled_windows + 1 if stalled else 0
            )
            v13_window_baseline = _task041_v13_merge_running_best(
                v13_window_baseline, best
            )
            record["running_best_after_window"] = dict(v13_window_baseline)
            if v13_consecutive_stalled_windows >= 2:
                v13_finite_stop_pending = {
                    "schema": "task041.v13.outer_finite_stop.v1",
                    "status": "two_consecutive_complete_16_step_windows_stalled",
                    "stop_reason": "task041_v13_outer_best_residual_stagnation_after_restart_decision",
                    "reason_name": "DIVERGED_MAX_IT",
                    "reason_code": int(
                        PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT
                    ),
                    "runtime_reason_source": (
                        "petsc4py.PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT"
                    ),
                    "configured_max_it": int(config.max_it),
                    "iterations_at_stop": iteration,
                    "max_it_reached": False,
                    "converged": False,
                    "restart64_trial_count": int(
                        v13_outer_control["restart64_trial_count"]
                    ),
                    "windows": [dict(item) for item in v13_window_records[-2:]],
                    "original_rhs_norm_at_solve_entry": float(rhs_norm),
                    "current_ksp_iterate_available": True,
                    "retained_solution_checkpoint": (
                        "Task039 retained_solution_checkpoint -> owner-sharded packet"
                    ),
                }
                return dict(v13_finite_stop_pending)
        return None

    try:
        if v13_outer_enabled:
            initial_workspace_report = _task041_v13_outer_restart_workspace_report(
                operator,
                rhs,
                solution,
                context,
                outer_comm,
                phase="outer_restart32_workspace",
            )
            initial_workspace_authority = (
                v13_modal_system.authorize_outer_workspace(
                    "outer_restart32_workspace", initial_workspace_report
                )
            )
            v13_outer_control["initial_restart32_workspace_report"] = (
                initial_workspace_report
            )
            v13_outer_control["initial_restart32_authority"] = (
                initial_workspace_authority
            )
            if initial_workspace_authority.get("status") != "pass":
                raise MemoryError(
                    "V13 initial restart-32 workspace was refused by the fresh resource gate: "
                    + "; ".join(
                        map(
                            str,
                            initial_workspace_authority.get("reasons", []),
                        )
                    )
                )
        context.bind_v13_original_global_operator(operator)
        snapshot(0, 1.0 if rhs_norm > _TINY else 0.0, None)
        ksp.setOperators(operator)
        ksp.setType(
            PETSc.KSP.Type.GMRES
            if str(config.ksp_type).lower() == "gmres"
            else PETSc.KSP.Type.FGMRES
        )
        ksp.setGMRESRestart(int(current_outer_restart))
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(
            rtol=float(config.threshold), atol=0.0, max_it=int(config.max_it)
        )
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(context)
        ksp.setUp()
        actual_ksp_type = str(ksp.getType())

        def convergence_test(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            if v13_outer_enabled and outer_iteration_offset > 0 and int(iteration) == 0:
                # The resumed KSP starts from the retained nonzero x at the
                # prior global iteration.  Reusing that row as a new local
                # iteration-zero decision would replay the safe-stop reason.
                return int(PETSc.KSP.ConvergedReason.ITERATING)
            global_iteration = int(outer_iteration_offset) + int(iteration)
            row = snapshot(
                global_iteration, float(residual_norm) / rhs_norm, current
            )
            if row.get("multimetric_decision") == "ITERATING":
                modal_bundle = context.action_modal_schur_system
                if isinstance(
                    modal_bundle, _FixedH6ModalGmresResearchBundle
                ):
                    stop = modal_bundle.post_backup_stop_decision()
                    if stop is not None:
                        # PETSc 3.19 exposes the non-success DIVERGED_MAX_IT
                        # code (-3), historically named DIVERGED_ITS by the
                        # Task041 policy.  The separate record prevents this
                        # policy stop from being reported as configured max-it.
                        policy_stop = {
                            **dict(stop),
                            "reason_name": "DIVERGED_MAX_IT",
                            "runtime_reason_source": (
                                "petsc4py.PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT"
                            ),
                            "reason_code": int(
                                PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT
                            ),
                            "configured_max_it": int(config.max_it),
                            "iterations_at_stop": int(iteration),
                            "max_it_reached": False,
                            "converged": False,
                            "current_ksp_iterate_available": True,
                            "current_trusted_solution_retained": False,
                            "original_rhs_retained": True,
                            "original_rhs_norm_at_solve_entry": float(rhs_norm),
                        }
                        modal_bundle._solver.record_post_backup_policy_stop(
                            policy_stop
                        )
                        row["task041_v12_policy_stop"] = policy_stop
                        row["multimetric_reason"] = policy_stop["reason_code"]
                        row["multimetric_decision"] = (
                            "POLICY_CAPACITY_STOP"
                            if policy_stop.get("status")
                            == "post_backup_restart32_restore_capacity_stop"
                            else "POLICY_STAGNATION_STOP"
                        )
                        if history:
                            history[-1]["task041_v12_policy_stop"] = dict(
                                policy_stop
                            )
                            history[-1]["multimetric_reason"] = int(
                                policy_stop["reason_code"]
                            )
                            history[-1]["multimetric_decision"] = row[
                                "multimetric_decision"
                            ]
                        return int(policy_stop["reason_code"])
                if v13_outer_enabled:
                    observation = observe_v13_outer_row(row)
                    if isinstance(observation, Mapping):
                        if observation.get("status") == (
                            "restart64_candidate_at_safe_boundary"
                        ):
                            v13_outer_control["restart64_safe_boundary"] = dict(
                                observation
                            )
                            row["task041_v13_restart64_safe_boundary"] = dict(
                                observation
                            )
                            row["multimetric_decision"] = (
                                "V13_RESTART64_SAFE_BOUNDARY"
                            )
                            row["multimetric_reason"] = int(
                                PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT
                            )
                            if history:
                                history[-1].update(row)
                            if progress_callback is not None:
                                progress_callback(dict(row))
                            return int(
                                PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT
                            )
                        if observation.get("schema") == (
                            "task041.v13.outer_finite_stop.v1"
                        ):
                            v13_outer_control["finite_stop"] = dict(observation)
                            row["task041_v13_outer_finite_stop"] = dict(
                                observation
                            )
                            row["multimetric_decision"] = (
                                "V13_FINITE_STAGNATION_STOP"
                            )
                            row["multimetric_reason"] = int(
                                observation["reason_code"]
                            )
                            if history:
                                history[-1].update(row)
                            if progress_callback is not None:
                                progress_callback(dict(row))
                            return int(observation["reason_code"])
            if (
                v13_outer_enabled
                and int(iteration) > 0
                and progress_callback is not None
            ):
                progress_callback(dict(row))
            return int(row["multimetric_reason"])

        ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        if v13_restart64_pending is not None:
            safe_boundary = dict(v13_restart64_pending)
            evidence = safe_boundary.get("evidence")
            if not isinstance(evidence, Mapping):
                raise RuntimeError("V13 restart candidate is missing its window evidence")
            local_boundary_error = None
            local_boundary_row = None
            try:
                local_x = np.asarray(
                    solution.getArray(readonly=True), dtype=np.complex128
                )
                local_f = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
                if not np.isfinite(local_x).all() or not np.isfinite(local_f).all():
                    raise ValueError("outer restart safe-boundary x/f is non-finite")
                rhs_sha_after = hashlib.sha256(
                    np.ascontiguousarray(local_f).tobytes()
                ).hexdigest()
                if rhs_sha_after != v13_rhs_local_sha256_at_entry:
                    raise ValueError("original V13 outer RHS changed before restart")
                local_boundary_row = {
                    "rank": int(outer_comm.rank),
                    "x_range": [int(value) for value in solution.getOwnershipRange()],
                    "f_range": [int(value) for value in rhs.getOwnershipRange()],
                    "solution_global_size": int(solution.getSize()),
                    "rhs_global_size": int(rhs.getSize()),
                    "solution_local_sha256": hashlib.sha256(
                        np.ascontiguousarray(local_x).tobytes()
                    ).hexdigest(),
                    "solution_local_norm": float(np.linalg.norm(local_x)),
                    "rhs_local_sha256_before": v13_rhs_local_sha256_at_entry,
                    "rhs_local_sha256_after": rhs_sha_after,
                    "solution_finite": True,
                    "rhs_finite": True,
                    "runtime_ksp_object_id": id(ksp),
                    "runtime_pc_context_object_id": id(
                        ksp.getPC().getPythonContext()
                    ),
                    "elapsed_seconds_at_boundary": float(
                        time.perf_counter() - started
                    ),
                    "cumulative_pc_apply_count_at_boundary": int(
                        context.inventory.get("pc_apply_count", 0)
                    ),
                    "cumulative_bottom_action_apply_count_at_boundary": int(
                        context.inventory.get("bottom_action_apply_count", 0)
                    ),
                    "cumulative_top_action_apply_count_at_boundary": int(
                        context.inventory.get("top_action_apply_count", 0)
                    ),
                }
                checkpoint_row = history_cache.get(int(iterations))
                if (
                    not isinstance(checkpoint_row, Mapping)
                    or checkpoint_row.get("solution_finite_local") is not True
                    or local_boundary_row["solution_local_sha256"]
                    != checkpoint_row.get("solution_local_sha256")
                ):
                    raise ValueError(
                        "outer safe-boundary x differs from its true-residual sample"
                    )
            except Exception as exc:  # noqa: BLE001 - agree before fresh gate
                local_boundary_error = f"{type(exc).__name__}: {exc}"
            boundary_rows = outer_comm.allgather(
                (local_boundary_error, local_boundary_row)
            )
            boundary_errors = [
                f"rank {rank}: {error}"
                for rank, (error, _row) in enumerate(boundary_rows)
                if error is not None
            ]
            if boundary_errors:
                raise RuntimeError(
                    "V13 restart safe-boundary x/f validation failed: "
                    + "; ".join(boundary_errors)
                )
            retained_rank_rows = [row for _error, row in boundary_rows]
            if [row.get("rank") for row in retained_rank_rows] != list(
                range(int(outer_comm.size))
            ):
                raise RuntimeError("V13 restart safe-boundary rank records are incomplete")
            local_x_ranges = [row["x_range"] for row in retained_rank_rows]
            local_f_ranges = [row["f_range"] for row in retained_rank_rows]
            for ranges, global_size in (
                (local_x_ranges, int(solution.getSize())),
                (local_f_ranges, int(rhs.getSize())),
            ):
                if (
                    not ranges
                    or ranges[0][0] != 0
                    or ranges[-1][1] != global_size
                    or any(
                        ranges[index][1] != ranges[index + 1][0]
                        for index in range(len(ranges) - 1)
                    )
                ):
                    raise RuntimeError(
                        "V13 restart safe-boundary owner ranges are not contiguous"
                    )
            safe_boundary["trusted_x_f_owner_records"] = retained_rank_rows
            safe_boundary["original_rhs_norm"] = float(rhs_norm)
            safe_boundary["iterations_before_restart"] = int(iterations)
            fresh_report = _task041_v13_outer_restart_workspace_report(
                operator,
                rhs,
                solution,
                context,
                outer_comm,
                phase="outer_restart64_workspace",
            )
            authority = v13_modal_system.authorize_outer_workspace(
                "outer_restart64_workspace", fresh_report
            )
            v13_outer_control["restart64_authority"] = dict(authority)
            v13_outer_control["restart64_workspace_report"] = fresh_report
            candidate_selected = authority.get("status") == "pass"
            if authority.get("status") not in {"pass", "refused"}:
                raise RuntimeError("V13 restart authority returned an invalid status")
            decision_row = {
                "candidate": safe_boundary,
                "authority_status": authority.get("status"),
                "authority_receipt_sha256": authority.get(
                    "authority_receipt_sha256"
                ),
                "restart_selected": bool(candidate_selected),
                "restart_before": int(current_outer_restart),
            }
            decision_signature = json.dumps(
                decision_row,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            decision_signatures = outer_comm.allgather(decision_signature)
            if any(value != decision_signatures[0] for value in decision_signatures[1:]):
                raise RuntimeError("V13 restart64 decision differs across ranks")
            if candidate_selected:
                if int(current_outer_restart) != 32 or int(iterations) != 48:
                    raise RuntimeError("V13 restart64 trial is outside the first safe window")
                from .physical_balanced_side_inverse import (
                    _configure_gmres_restart_trial,
                    _live_gmres_restart,
                )

                pc_context_before = ksp.getPC().getPythonContext()
                if pc_context_before is not context or context._destroyed:
                    raise RuntimeError(
                        "V13 restart64 cannot preserve the live borrowed PC/factors"
                    )
                ksp.setGMRESRestart(64)
                mgs_setup = _configure_gmres_restart_trial(ksp)
                ksp.setUp()
                if (
                    _live_gmres_restart(ksp) != 64
                    or str(ksp.getType()).lower() != "fgmres"
                    or ksp.getPCSide() != PETSc.PC.Side.RIGHT
                    or ksp.getPC().getPythonContext() is not context
                    or context._destroyed
                ):
                    raise RuntimeError(
                        "V13 restart64 changed the KSP/PC identity or failed readback"
                    )
                current_outer_restart = 64
                v13_outer_control["restart64_trial_count"] = 1
                v13_outer_control["restart_history"].append(
                    {
                        "iteration": int(iterations),
                        "restart": 64,
                        "reason": (
                            "complete_16_to_32_global_progress_then_32_to_48_"
                            "global_and_unpassed_block_stagnation_with_fresh_gate_passed"
                        ),
                        "evidence_rule_id": evidence.get("rule_id"),
                        "orthogonalization": dict(mgs_setup),
                        "initial_guess_nonzero": True,
                        "restart_boundary_iteration": int(iterations),
                        "configured_total_max_it": int(config.max_it),
                        "remaining_total_iterations_before_resume": int(
                            config.max_it
                        )
                        - int(iterations),
                    }
                )
                v13_outer_control["restart64_decision"] = {
                    "status": "restart64_selected_once",
                    **decision_row,
                    "mgs_setup": dict(mgs_setup),
                }
            else:
                v13_outer_control["restart_history"].append(
                    {
                        "iteration": int(iterations),
                        "restart": 32,
                        "reason": "restart64_fresh_authority_refused_continue_same_ksp_at_48",
                        "evidence_rule_id": evidence.get("rule_id"),
                        "restart_boundary_iteration": int(iterations),
                        "configured_total_max_it": int(config.max_it),
                        "remaining_total_iterations_before_resume": int(
                            config.max_it
                        )
                        - int(iterations),
                        "authority_receipt_sha256": authority.get(
                            "authority_receipt_sha256"
                        ),
                    }
                )
                v13_outer_control["restart64_decision"] = {
                    "status": "restart64_refused_continue_restart32",
                    **decision_row,
                }
            resume_error = None
            resume_row = None
            try:
                ksp.setInitialGuessNonzero(True)
                initial_guess_nonzero_readback = bool(
                    ksp.getInitialGuessNonzero()
                )
                if not initial_guess_nonzero_readback:
                    raise RuntimeError(
                        "V13 same-KSP resume did not retain the nonzero initial guess"
                    )
                local_x = np.asarray(
                    solution.getArray(readonly=True), dtype=np.complex128
                )
                local_f = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
                expected_x_hash = retained_rank_rows[int(outer_comm.rank)][
                    "solution_local_sha256"
                ]
                actual_x_hash = hashlib.sha256(
                    np.ascontiguousarray(local_x).tobytes()
                ).hexdigest()
                actual_f_hash = hashlib.sha256(
                    np.ascontiguousarray(local_f).tobytes()
                ).hexdigest()
                if (
                    not np.isfinite(local_x).all()
                    or actual_x_hash != expected_x_hash
                    or actual_f_hash != v13_rhs_local_sha256_at_entry
                ):
                    raise ValueError(
                        "same-KSP resume changed the retained trusted x or original f"
                    )
                resume_row = {
                    "rank": int(outer_comm.rank),
                    "x_range": [int(value) for value in solution.getOwnershipRange()],
                    "f_range": [int(value) for value in rhs.getOwnershipRange()],
                    "solution_global_size": int(solution.getSize()),
                    "rhs_global_size": int(rhs.getSize()),
                    "solution_local_sha256_before": expected_x_hash,
                    "solution_local_sha256_after_setup": actual_x_hash,
                    "solution_local_norm_before_resume": float(
                        np.linalg.norm(local_x)
                    ),
                    "rhs_local_sha256_before": v13_rhs_local_sha256_at_entry,
                    "rhs_local_sha256_before_resume": actual_f_hash,
                    "solution_finite": True,
                    "rhs_finite": bool(np.isfinite(local_f).all()),
                    "runtime_ksp_object_id_before_restart": int(
                        retained_rank_rows[int(outer_comm.rank)][
                            "runtime_ksp_object_id"
                        ]
                    ),
                    "runtime_ksp_object_id_after_setup": id(ksp),
                    "runtime_pc_context_object_id_before_restart": int(
                        retained_rank_rows[int(outer_comm.rank)][
                            "runtime_pc_context_object_id"
                        ]
                    ),
                    "runtime_pc_context_object_id_after_setup": id(
                        ksp.getPC().getPythonContext()
                    ),
                    "same_ksp_object_retained": bool(
                        id(ksp)
                        == int(
                            retained_rank_rows[int(outer_comm.rank)][
                                "runtime_ksp_object_id"
                            ]
                        )
                    ),
                    "same_pc_context_retained": bool(
                        ksp.getPC().getPythonContext() is context
                        and id(ksp.getPC().getPythonContext())
                        == int(
                            retained_rank_rows[int(outer_comm.rank)][
                                "runtime_pc_context_object_id"
                            ]
                        )
                    ),
                    "initial_guess_nonzero_requested": True,
                    "initial_guess_nonzero_readback": initial_guess_nonzero_readback,
                    "cumulative_iteration_offset": int(iterations),
                    "local_iteration_count_before_resume": int(
                        ksp.getIterationNumber()
                    ),
                    "remaining_total_iterations_before_resume": int(
                        config.max_it
                    )
                    - int(iterations),
                    "elapsed_seconds_before_resume": float(
                        time.perf_counter() - started
                    ),
                    "cumulative_pc_apply_count_before_resume": int(
                        context.inventory.get("pc_apply_count", 0)
                    ),
                    "cumulative_bottom_action_apply_count_before_resume": int(
                        context.inventory.get("bottom_action_apply_count", 0)
                    ),
                    "cumulative_top_action_apply_count_before_resume": int(
                        context.inventory.get("top_action_apply_count", 0)
                    ),
                    "borrowed_actions_still_live": all(
                        not bool(_action_diagnostics(action).get("destroyed"))
                        for action in (context.bottom_action, context.top_action)
                    ),
                }
            except Exception as exc:  # noqa: BLE001 - agree before resumed solve
                resume_error = f"{type(exc).__name__}: {exc}"
            resume_rows = outer_comm.allgather((resume_error, resume_row))
            resume_errors = [
                f"rank {rank}: {error}"
                for rank, (error, _row) in enumerate(resume_rows)
                if error is not None
            ]
            if resume_errors:
                raise RuntimeError(
                    "V13 same-KSP resume lost trusted x/f: "
                    + "; ".join(resume_errors)
                )
            resume_facts = [row for _error, row in resume_rows]
            if [row.get("rank") for row in resume_facts] != list(
                range(int(outer_comm.size))
            ):
                raise RuntimeError("V13 same-KSP resume rank records are incomplete")
            v13_outer_control["restart64_decision"][
                "same_ksp_nonzero_x_resume"
            ] = resume_facts
            v13_outer_control["restart64_decision_resolved"] = True
            v13_restart64_pending = None
            outer_iteration_offset = int(iterations)
            outer_krylov_origin = int(iterations)
            v13_window_segment_start = int(iterations)
            boundary_row = history_cache.get(int(iterations))
            if not isinstance(boundary_row, Mapping):
                raise RuntimeError("V13 restart transition has no saved residual boundary")
            v13_window_baseline = {
                key: float(boundary_row[key])
                for key in (
                    "global_true_relative_residual",
                    "bottom_true_relative_residual",
                    "top_true_relative_residual",
                    "modal_true_relative_residual",
                )
            }
            v13_consecutive_stalled_windows = 0
            v13_outer_control.setdefault("observation_segments", []).append(
                {
                    "start_iteration": int(iterations),
                    "restart": int(current_outer_restart),
                    "baseline_true_residuals": dict(v13_window_baseline),
                    "reason": "restart64_gate_resolved_and_same_ksp_resumed",
                }
            )
            remaining = int(config.max_it) - int(iterations)
            if remaining <= 0:
                raise RuntimeError(
                    "V13 restart boundary has no remaining configured outer iterations"
                )
            ksp.setTolerances(
                rtol=float(config.threshold), atol=0.0, max_it=remaining
            )
            ksp.solve(rhs, solution)
            reason = int(ksp.getConvergedReason())
            iterations = int(outer_iteration_offset) + int(ksp.getIterationNumber())
            if iterations > int(config.max_it):
                raise RuntimeError("V13 segmented outer iterations exceeded total max_it")
            v13_outer_control["restart64_decision"][
                "same_ksp_nonzero_x_resume_work"
            ] = {
                "iterations_after_resume": int(iterations),
                "local_iteration_count_after_resume": int(
                    ksp.getIterationNumber()
                ),
                "max_it_remaining_after_resume": int(config.max_it) - int(iterations),
                "elapsed_seconds_after_resume": float(
                    time.perf_counter() - started
                ),
                "cumulative_pc_apply_count_after_resume": int(
                    context.inventory.get("pc_apply_count", 0)
                ),
                "cumulative_bottom_action_apply_count_after_resume": int(
                    context.inventory.get("bottom_action_apply_count", 0)
                ),
                "cumulative_top_action_apply_count_after_resume": int(
                    context.inventory.get("top_action_apply_count", 0)
                ),
            }
        if v13_finite_stop_pending is not None:
            if reason != int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT):
                raise RuntimeError("V13 finite stop returned an unexpected KSP reason")
            v13_finite_stop_pending["iterations_at_stop"] = int(iterations)
            v13_finite_stop_pending["max_it_reached"] = bool(
                int(iterations) >= int(config.max_it)
            )
            if v13_finite_stop_pending["max_it_reached"]:
                raise RuntimeError("V13 finite stop collided with the configured max_it")
        reported = float(ksp.getResidualNorm()) / rhs_norm
        if int(iterations) not in history_cache:
            snapshot(iterations, reported, None)
        solution.copy(retained_solution)
        if v13_finite_stop_pending is not None:
            local_x = np.asarray(
                retained_solution.getArray(readonly=True), dtype=np.complex128
            )
            local_f = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
            local_x_sha = hashlib.sha256(
                np.ascontiguousarray(local_x).tobytes()
            ).hexdigest()
            local_f_sha = hashlib.sha256(
                np.ascontiguousarray(local_f).tobytes()
            ).hexdigest()
            local_retention = {
                "rank": int(outer_comm.rank),
                "solution_range": [
                    int(value) for value in retained_solution.getOwnershipRange()
                ],
                "rhs_range": [int(value) for value in rhs.getOwnershipRange()],
                "solution_global_size": int(retained_solution.getSize()),
                "rhs_global_size": int(rhs.getSize()),
                "solution_local_sha256": local_x_sha,
                "solution_local_norm": float(np.linalg.norm(local_x)),
                "rhs_local_sha256_before": v13_rhs_local_sha256_at_entry,
                "rhs_local_sha256_after": local_f_sha,
                "solution_finite": bool(np.isfinite(local_x).all()),
                "rhs_unchanged": local_f_sha == v13_rhs_local_sha256_at_entry,
            }
            retained_rows = sorted(
                outer_comm.allgather(local_retention),
                key=lambda value: value.get("rank", -1),
            )
            retained_pass = bool(
                len(retained_rows) == int(outer_comm.size)
                and [row.get("rank") for row in retained_rows]
                == list(range(int(outer_comm.size)))
                and all(
                    row.get("solution_finite") is True
                    and row.get("rhs_unchanged") is True
                    and isinstance(row.get("solution_local_sha256"), str)
                    and len(row["solution_local_sha256"]) == 64
                    for row in retained_rows
                )
                and all(
                    retained_rows[index]["solution_range"][1]
                    == retained_rows[index + 1]["solution_range"][0]
                    and retained_rows[index]["rhs_range"][1]
                    == retained_rows[index + 1]["rhs_range"][0]
                    for index in range(len(retained_rows) - 1)
                )
                and retained_rows[0]["solution_range"][0] == 0
                and retained_rows[-1]["solution_range"][1]
                == int(retained_solution.getSize())
                and retained_rows[0]["rhs_range"][0] == 0
                and retained_rows[-1]["rhs_range"][1] == int(rhs.getSize())
            )
            retained_flags = outer_comm.allgather(retained_pass)
            if not retained_pass or any(
                value is not retained_flags[0] for value in retained_flags
            ):
                raise RuntimeError(
                    "V13 finite stop could not retain trusted owner-sharded x and original f"
                )
            v13_finite_stop_pending.update(
                {
                    "iterations_at_stop": int(iterations),
                    "current_trusted_solution_retained": True,
                    "original_rhs_unchanged": True,
                    "original_rhs_norm_at_solve_entry": float(rhs_norm),
                    "original_rhs_global_size": int(rhs.getSize()),
                    "rank_local_solution_rhs_binding": {
                        "scope": "owner-sharded hashes/ranges; vectors are not gathered",
                        "records": retained_rows,
                    },
                    "post_stop_true_residuals_pending": True,
                    "result_checkpoint_path": (
                        "Task039 retained_solution_checkpoint -> owner-sharded packet"
                    ),
                }
            )
            v13_outer_control["finite_stop"] = dict(v13_finite_stop_pending)
        elif v13_outer_enabled:
            local_f = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
            local_rhs_after = hashlib.sha256(
                np.ascontiguousarray(local_f).tobytes()
            ).hexdigest()
            local_facts = {
                "rank": int(outer_comm.rank),
                "rhs_sha256_before": v13_rhs_local_sha256_at_entry,
                "rhs_sha256_after": local_rhs_after,
                "rhs_finite": bool(np.isfinite(local_f).all()),
            }
            rhs_facts = sorted(
                outer_comm.allgather(local_facts), key=lambda value: value["rank"]
            )
            if any(
                row.get("rhs_finite") is not True
                or row.get("rhs_sha256_before") != row.get("rhs_sha256_after")
                for row in rhs_facts
            ):
                raise RuntimeError("V13 outer solve changed or invalidated the original RHS")
            v13_outer_control["original_rhs_unchanged"] = True
            v13_outer_control["original_rhs_rank_bindings"] = rhs_facts
        post_global, post_block = _true_residual_metrics(
            operator, rhs, retained_solution, context
        )
        post_values = {
            "reported_relative_residual": reported,
            "global_true_relative_residual": float(post_global),
            "bottom_true_relative_residual": float(post_block["bottom"]),
            "top_true_relative_residual": float(post_block["top"]),
            "modal_true_relative_residual": float(post_block["modal"]),
        }
        post_decision = multimetric_true_residual_decision(
            iterations,
            post_values,
            max_it=config.max_it,
            threshold=config.threshold,
        )
        if v13_finite_stop_pending is not None:
            v13_finite_stop_pending.update(
                {
                    "post_stop_true_residuals": dict(post_values),
                    "post_stop_original_residual_pass": bool(
                        post_decision["positive"]
                    ),
                    "post_stop_all_finite_nonnegative": bool(
                        post_decision["all_finite_nonnegative"]
                    ),
                }
            )
            v13_finite_stop_pending.pop("post_stop_true_residuals_pending", None)
            v13_outer_control["finite_stop"] = dict(v13_finite_stop_pending)
        if v13_outer_enabled:
            v13_outer_control.update(
                {
                    "final_restart": int(current_outer_restart),
                    "total_iterations": int(iterations),
                    "total_wall_seconds": float(time.perf_counter() - started),
                    "final_reason": int(reason),
                    "final_reason_name": str(post_decision["decision"]),
                    "all_residual_history_rows": len(history),
                    "cumulative_pc_apply_count": int(
                        context.inventory.get("pc_apply_count", 0)
                    ),
                    "cumulative_bottom_action_apply_count": int(
                        context.inventory.get("bottom_action_apply_count", 0)
                    ),
                    "cumulative_top_action_apply_count": int(
                        context.inventory.get("top_action_apply_count", 0)
                    ),
                }
            )
        post_pass = bool(reason > 0 and post_decision["positive"])
        policy_stop_record = next(
            (
                dict(row["task041_v12_policy_stop"])
                for row in reversed(history)
                if isinstance(row.get("task041_v12_policy_stop"), Mapping)
            ),
            None,
        )
        postsolve = {
            **post_values,
            "identity": post_decision["identity"],
            "ksp_type": actual_ksp_type,
            "threshold": float(config.threshold),
            "restart": int(
                current_outer_restart if v13_outer_enabled else config.restart
            ),
            "explicit_recomputed_residuals": dict(post_values),
            "decision": post_decision["decision"],
            "reason": reason,
            "all_finite_nonnegative": post_decision["all_finite_nonnegative"],
            "max_true_residual": post_decision["max_true_residual"],
            "pass": post_pass,
        }
        if v13_outer_enabled:
            postsolve["task041_v13_outer_control"] = dict(v13_outer_control)
        if policy_stop_record is not None:
            if (
                reason != policy_stop_record.get("reason_code")
                or iterations >= int(config.max_it)
                or policy_stop_record.get("max_it_reached") is not False
            ):
                raise RuntimeError(
                    "finite policy stop did not return its supported non-success reason before configured max_it"
                )
            if not backup_policy_for_stop or rhs_local_sha256_at_entry is None:
                raise RuntimeError(
                    "finite policy stop is outside the registered primary/backup route"
                )
            local_rhs_after_sha = hashlib.sha256(
                np.ascontiguousarray(
                    np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
                ).tobytes()
            ).hexdigest()
            local_solution_values = np.asarray(
                retained_solution.getArray(readonly=True), dtype=np.complex128
            )
            local_solution_sha = hashlib.sha256(
                np.ascontiguousarray(local_solution_values).tobytes()
            ).hexdigest()
            local_range = [int(value) for value in retained_solution.getOwnershipRange()]
            local_binding = {
                "rank": int(operator.getComm().tompi4py().rank),
                "range": local_range,
                "global_size": int(retained_solution.getSize()),
                "solution_local_sha256": local_solution_sha,
                "rhs_local_sha256_before": rhs_local_sha256_at_entry,
                "rhs_local_sha256_after": local_rhs_after_sha,
                "solution_finite_local": bool(np.isfinite(local_solution_values).all()),
                "rhs_unchanged_local": local_rhs_after_sha == rhs_local_sha256_at_entry,
            }
            retention_rows = sorted(
                operator.getComm().tompi4py().allgather(local_binding),
                key=lambda row: row.get("rank", -1),
            )
            retention_pass = bool(
                len(retention_rows) == operator.getComm().tompi4py().size
                and [row.get("rank") for row in retention_rows]
                == list(range(operator.getComm().tompi4py().size))
                and all(
                    row.get("solution_finite_local") is True
                    and row.get("rhs_unchanged_local") is True
                    and row.get("global_size") == int(retained_solution.getSize())
                    for row in retention_rows
                )
                and all(
                    retention_rows[index]["range"][1]
                    == retention_rows[index + 1]["range"][0]
                    for index in range(len(retention_rows) - 1)
                )
                and retention_rows[0]["range"][0] == 0
                and retention_rows[-1]["range"][1]
                == int(retained_solution.getSize())
            )
            retention_flags = operator.getComm().tompi4py().allgather(retention_pass)
            if not retention_pass or any(value is not retention_flags[0] for value in retention_flags):
                raise RuntimeError(
                    "finite policy stop did not retain the same trusted sharded x and original f"
                )
            if any(
                len(row["solution_local_sha256"]) != 64
                or len(row["rhs_local_sha256_before"]) != 64
                or row["rhs_local_sha256_before"] != row["rhs_local_sha256_after"]
                for row in retention_rows
            ):
                raise RuntimeError("finite policy stop returned malformed owner-local x/f hashes")
            finalized_policy_stop = {
                **policy_stop_record,
                "current_trusted_solution_retained": True,
                "original_rhs_unchanged": True,
                "original_rhs_norm_at_solve_entry": float(rhs_norm),
                "original_rhs_global_size": int(rhs.getSize()),
                "rank_local_solution_rhs_binding": {
                    "scope": "one owned record per MPI rank; no vector gather",
                    "records": retention_rows,
                },
                "postsolve_true_residuals": {
                    key: float(value) for key, value in post_values.items()
                },
                "postsolve_all_finite_nonnegative": bool(
                    post_decision["all_finite_nonnegative"]
                ),
                "postsolve_original_residual_pass": bool(post_decision["positive"]),
                "result_checkpoint_path": (
                    "HybridBlockLduIterativeResult.solution -> "
                    "Task039 retained_solution_checkpoint -> owner_sharded packet"
                ),
            }
            modal_bundle_for_stop._solver.finalize_post_backup_policy_stop(
                finalized_policy_stop
            )
            policy_stop_record = finalized_policy_stop
            if history and isinstance(history[-1], dict):
                history[-1]["task041_v12_policy_stop"] = dict(
                    finalized_policy_stop
                )
            postsolve.update(
                {
                    "decision": (
                        "POLICY_CAPACITY_STOP"
                        if policy_stop_record.get("status")
                        == "post_backup_restart32_restore_capacity_stop"
                        else "POLICY_STAGNATION_STOP"
                    ),
                    "policy_stop_reason": policy_stop_record["stop_reason"],
                    "policy_stop": policy_stop_record,
                    "configured_max_it": int(config.max_it),
                    "max_it_reached": False,
                    "converged": False,
                    "result_solution_retained": True,
                    "original_rhs_retained_for_result": True,
                }
            )
        inventory = dict(context.inventory)
        inventory.update(
            {
                "ksp_type": actual_ksp_type,
                "restart": int(
                    current_outer_restart if v13_outer_enabled else config.restart
                ),
            }
        )
        if v13_outer_enabled:
            inventory["task041_v13_outer_control"] = dict(v13_outer_control)
        if policy_stop_record is not None:
            inventory["task041_v12_policy_stop"] = dict(policy_stop_record)
        release = {
            "ksp_destroyed": False,
            "pc_context_destroyed": False,
            "action_modal_schur_retained_after_pc_destroyed": False,
            "action_modal_schur_released": False,
            "solution_snapshot_retained": True,
            "borrowed_side_actions_retained": False,
        }
        context.defer_action_modal_schur_release = bool(post_pass)
        ksp.destroy()
        ksp = None
        release["ksp_destroyed"] = True
        context.destroy()
        release["pc_context_destroyed"] = True
        release["action_modal_schur_retained_after_pc_destroyed"] = bool(
            not context.action_modal_schur_system.diagnostics["destroyed"]
        )
        release["borrowed_side_actions_retained"] = all(
            not bool(_action_diagnostics(action).get("destroyed"))
            for action in (context.bottom_action, context.top_action)
        )
        timing = {
            "total_seconds": float(time.perf_counter() - started),
            "ksp_type": actual_ksp_type,
            "restart": float(
                current_outer_restart if v13_outer_enabled else config.restart
            ),
            "max_it": float(config.max_it),
            "threshold": float(config.threshold),
            "history_evaluation_count": float(history_evaluations),
            "postsolve_evaluation_count": 1.0,
        }
        result = HybridBlockLduIterativeResult(
            solution=retained_solution,
            history=[dict(row) for row in history],
            converged_reason=reason,
            iterations=iterations,
            final_reported_relative_residual=reported,
            final_true_relative_residual=float(post_global),
            block_relative_residuals={
                key: float(value) for key, value in post_block.items()
            },
            postsolve_audit=postsolve,
            release=release,
            inventory=inventory,
            timing=timing,
            _preconditioner=context,
        )
        returned = True
        return result
    except BaseException:
        modal_system = context.action_modal_schur_system
        if getattr(modal_system, "capture_modal_solve_trace", False):
            context._modal_solve_trace_handoff = (
                modal_system.take_modal_solve_trace_records()
            )
        raise
    finally:
        if ksp is not None:
            ksp.destroy()
        if not context._destroyed:
            context.defer_action_modal_schur_release = False
            context.destroy()
        monitor_solution.destroy()
        solution.destroy()
        if not returned:
            retained_solution.destroy()
