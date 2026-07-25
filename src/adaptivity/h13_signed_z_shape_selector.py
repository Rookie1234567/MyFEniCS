"""Fail-closed signed shape-sensitivity selector for the Task035b h13 lane.

This module is deliberately a pure algorithm.  It consumes two independently
measured signed central-difference sensitivity matrices and never evaluates a
PDE, invents a sensitivity, or accepts a caller-selected plane.  The only
physical target contract is the six independent real h13 failure quantities:

* bottom ``T(-4,0)_s`` power;
* top ``R(-4,0)_s`` power;
* real and imaginary parts of top ``r(-4,0)_s``;
* real and imaginary parts of top ``r(-5,0)_s``.

The two complex-amplitude Gates are validated only through the L2 norm of
their paired real/imaginary errors.  No per-component pass signature is
invented.  Already-passing observables, when available, enter an explicitly
separate optional protection contract and never alter the six failure rows.

Only the nine interior planes in the fixed ``0..120 nm`` material slab may
move.  Every one-plane and two-plane support is optimized deterministically by
a small linear program.  A selected displacement remains a prediction-only
research proposal until a separate clean-SHA MPI8 PDE clears the complete
Task035b Gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import combinations
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import linprog


H13_REAL_GOAL_LABELS = (
    "T_bottom(-4,0)_s.power",
    "R_top(-4,0)_s.power",
    "Re[r_top(-4,0)_s]",
    "Im[r_top(-4,0)_s]",
    "Re[r_top(-5,0)_s]",
    "Im[r_top(-5,0)_s]",
)

H13_POWER_FAILURE_INDICES = (0, 1)
H13_COMPLEX_FAILURE_PAIRS = (
    ("r_top(-4,0)_s", 2, 3),
    ("r_top(-5,0)_s", 4, 5),
)

H13_BASE_INTERIOR_Z_PLANES_NM = (
    12.0,
    24.0,
    36.0,
    48.0,
    60.0,
    72.0,
    84.0,
    96.0,
    108.0,
)

_REQUIRED_SOURCE_HASH_KEYS = (
    "h13_base",
    "plus_epsilon_bundle",
    "minus_epsilon_bundle",
    "plus_2epsilon_bundle",
    "minus_2epsilon_bundle",
)


@dataclass(frozen=True)
class H13RealGoal:
    """One SHA-bound real observable in the frozen h13 target contract."""

    label: str
    base_observable: float
    reference: float
    tolerance: float


@dataclass(frozen=True)
class H13ProtectedRealGoal:
    """One separate already-passing scalar guard observable.

    This guard is not one of the six failed targets and never claims to
    replace the complete formal 12-channel PDE Gate.
    """

    label: str
    base_observable: float
    reference: float
    tolerance: float


@dataclass(frozen=True)
class _SelectorProfile:
    schema_version: str = "task035b.h13-signed-z-shape-selector.v1"
    baseline_identity: str = "fixed_p5trace_p6interior_h13_directional_z"
    full3d_equivalent_dofs: int = 89_740
    active_rows_with_dtn: int = 20_120
    cell_count: int = 144
    fixed_domain_z_min_nm: float = -10.0
    fixed_material_z_min_nm: float = 0.0
    fixed_material_z_max_nm: float = 120.0
    fixed_domain_z_max_nm: float = 130.0
    movable_plane_count: int = 9
    maximum_moved_planes: int = 2
    maximum_absolute_displacement_nm: float = 0.6
    minimum_material_slab_width_nm: float = 10.8
    maximum_material_slab_width_nm: float = 13.2
    minimum_predicted_benefit_fraction: float = 0.05
    step_relative_disagreement_limit: float = 0.25
    normalized_sensitivity_zero_floor_per_nm: float = 1.0e-8
    rank_relative_tolerance: float = 1.0e-10
    rank_absolute_tolerance: float = 1.0e-12
    optimization_method: str = "scipy.optimize.linprog.highs"
    selection_sensitivity: str = "epsilon_signed_central_difference"
    passed_goal_guard: str = "absolute_normalized_error_le_1"
    ordinary_default_changed: bool = False


_PROFILE = _SelectorProfile()


def _finite_float(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _canonical_sha256(payload: Mapping[str, Any] | Sequence[Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype="<f8")
    digest = hashlib.sha256()
    digest.update(b"task035b.canonical-float64-array.v1")
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _profile_payload() -> dict[str, Any]:
    return {
        "schema_version": _PROFILE.schema_version,
        "baseline_identity": _PROFILE.baseline_identity,
        "failed_physical_target_labels": list(H13_REAL_GOAL_LABELS),
        "failed_gate_contract": {
            "power_failure_indices": list(H13_POWER_FAILURE_INDICES),
            "complex_vector_failure_pairs": [
                {
                    "channel": channel,
                    "real_index": real_index,
                    "imaginary_index": imaginary_index,
                    "gate": "L2_norm_of_normalized_Re_Im_error_gt_1",
                }
                for channel, real_index, imaginary_index
                in H13_COMPLEX_FAILURE_PAIRS
            ],
            "per_component_amplitude_pass_signature": "not_defined",
        },
        "base_interior_z_planes_nm": list(H13_BASE_INTERIOR_Z_PLANES_NM),
        "fixed_planes_nm": {
            "domain_z_min": _PROFILE.fixed_domain_z_min_nm,
            "material_z_min": _PROFILE.fixed_material_z_min_nm,
            "material_z_max": _PROFILE.fixed_material_z_max_nm,
            "domain_z_max": _PROFILE.fixed_domain_z_max_nm,
        },
        "resource_identity": {
            "full3d_equivalent_dofs": _PROFILE.full3d_equivalent_dofs,
            "active_rows_with_dtn": _PROFILE.active_rows_with_dtn,
            "cell_count": _PROFILE.cell_count,
            "topology_and_dofs_unchanged": True,
        },
        "candidate_contract": {
            "movable_plane_count": _PROFILE.movable_plane_count,
            "maximum_moved_planes": _PROFILE.maximum_moved_planes,
            "single_support_count": 9,
            "pair_support_count": 36,
            "total_support_count": 45,
            "maximum_absolute_displacement_nm": (
                _PROFILE.maximum_absolute_displacement_nm
            ),
            "material_slab_width_range_nm": [
                _PROFILE.minimum_material_slab_width_nm,
                _PROFILE.maximum_material_slab_width_nm,
            ],
            "minimum_predicted_benefit_fraction": (
                _PROFILE.minimum_predicted_benefit_fraction
            ),
        },
        "sensitivity_contract": {
            "fine_step": "signed central difference at +/-epsilon",
            "coarse_step": "signed central difference at +/-2epsilon",
            "selection_sensitivity": _PROFILE.selection_sensitivity,
            "step_relative_disagreement_limit": (
                _PROFILE.step_relative_disagreement_limit
            ),
            "normalized_sensitivity_zero_floor_per_nm": (
                _PROFILE.normalized_sensitivity_zero_floor_per_nm
            ),
            "full_row_rank_required": False,
            "rank_role": "SVD_diagnostic_only_unless_matrix_is_zero",
            "rank_relative_tolerance": _PROFILE.rank_relative_tolerance,
            "rank_absolute_tolerance": _PROFILE.rank_absolute_tolerance,
        },
        "optimization_contract": {
            "method": _PROFILE.optimization_method,
            "objective": "deterministic_minimax_absolute_normalized_error",
            "passed_goal_guard": _PROFILE.passed_goal_guard,
            "tie_break": (
                "minimax_then_support_size_then_plane_indices_then_delta"
            ),
            "manual_plane_override_allowed": False,
        },
        "optional_protection_contract": {
            "separate_from_six_failed_targets": True,
            "requires_base_absolute_normalized_error_le_1": True,
            "scope": "caller_supplied_partial_prediction_screen_only",
            "formal_12_channel_PDE_gate_still_required": True,
        },
        "ordinary_default_changed": _PROFILE.ordinary_default_changed,
    }


def _validate_source_hashes(
    source_hashes: Mapping[str, str],
) -> dict[str, str]:
    if set(source_hashes) != set(_REQUIRED_SOURCE_HASH_KEYS):
        raise ValueError(
            "source_hashes must contain exactly "
            + ", ".join(_REQUIRED_SOURCE_HASH_KEYS)
        )
    result: dict[str, str] = {}
    for key in _REQUIRED_SOURCE_HASH_KEYS:
        value = str(source_hashes[key]).lower()
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"source_hashes[{key!r}] must be a SHA-256")
        result[key] = value
    if len(set(result.values())) != len(result):
        raise ValueError("each signed perturbation authority needs a unique hash")
    return result


def _validate_goals(
    goals: Sequence[H13RealGoal],
) -> tuple[
    list[dict[str, Any]],
    np.ndarray,
    np.ndarray,
    dict[str, Any],
]:
    if len(goals) != len(H13_REAL_GOAL_LABELS):
        raise ValueError("the h13 selector requires exactly six real goals")
    by_label: dict[str, H13RealGoal] = {}
    for goal in goals:
        if not isinstance(goal, H13RealGoal):
            raise TypeError("goals must contain H13RealGoal objects")
        if goal.label in by_label:
            raise ValueError(f"duplicate h13 goal {goal.label!r}")
        by_label[goal.label] = goal
    if set(by_label) != set(H13_REAL_GOAL_LABELS):
        raise ValueError("goals do not match the frozen h13 target labels")

    rows: list[dict[str, Any]] = []
    tolerances: list[float] = []
    normalized: list[float] = []
    for goal_index, label in enumerate(H13_REAL_GOAL_LABELS):
        goal = by_label[label]
        base = _finite_float(
            goal.base_observable,
            label=f"{label}.base_observable",
        )
        reference = _finite_float(goal.reference, label=f"{label}.reference")
        tolerance = _finite_float(
            goal.tolerance,
            label=f"{label}.tolerance",
        )
        if tolerance <= 0.0:
            raise ValueError(f"{label}.tolerance must be positive")
        error = (base - reference) / tolerance
        if not math.isfinite(error):
            raise ValueError(f"{label} normalized error is nonfinite")
        rows.append(
            {
                "label": label,
                "base_observable": base,
                "reference": reference,
                "tolerance": tolerance,
                "base_normalized_error_signed": error,
                "gate_role": (
                    "failed_power_goal"
                    if goal_index in H13_POWER_FAILURE_INDICES
                    else "failed_complex_amplitude_component"
                ),
                "individual_component_gate": (
                    "not_applicable"
                    if goal_index in H13_POWER_FAILURE_INDICES
                    else "not_defined_use_paired_complex_L2_gate"
                ),
            }
        )
        tolerances.append(tolerance)
        normalized.append(error)

    normalized_array = np.asarray(normalized, dtype=np.float64)
    power_gates = [
        {
            "label": H13_REAL_GOAL_LABELS[index],
            "absolute_normalized_error": abs(float(normalized_array[index])),
            "gate_pass": abs(float(normalized_array[index])) <= 1.0,
            "expected_h13_failure": True,
        }
        for index in H13_POWER_FAILURE_INDICES
    ]
    complex_gates: list[dict[str, Any]] = []
    for channel, real_index, imaginary_index in H13_COMPLEX_FAILURE_PAIRS:
        if tolerances[real_index] != tolerances[imaginary_index]:
            raise ValueError(
                f"{channel} Re/Im must share one complex-amplitude tolerance"
            )
        l2_error = float(
            np.hypot(
                normalized_array[real_index],
                normalized_array[imaginary_index],
            )
        )
        complex_gates.append(
            {
                "channel": channel,
                "component_labels": [
                    H13_REAL_GOAL_LABELS[real_index],
                    H13_REAL_GOAL_LABELS[imaginary_index],
                ],
                "normalized_component_errors_signed": [
                    float(normalized_array[real_index]),
                    float(normalized_array[imaginary_index]),
                ],
                "normalized_complex_vector_L2_error": l2_error,
                "gate_pass": l2_error <= 1.0,
                "expected_h13_failure": True,
                "individual_component_pass_signature": "not_defined",
            }
        )
    gate_audit = {
        "pass": all(not row["gate_pass"] for row in power_gates)
        and all(not row["gate_pass"] for row in complex_gates),
        "power_gates": power_gates,
        "complex_vector_L2_gates": complex_gates,
        "expected_failure_count": 4,
        "observed_failure_count": sum(
            not row["gate_pass"] for row in (*power_gates, *complex_gates)
        ),
        "componentwise_amplitude_passes_inferred": False,
    }
    if not gate_audit["pass"]:
        raise ValueError(
            "base observables do not reproduce two failed power Gates and "
            "two failed complex-vector L2 Gates from the h13 authority"
        )
    return (
        rows,
        np.asarray(tolerances, dtype=np.float64),
        normalized_array,
        gate_audit,
    )


def _validate_protected_goals(
    goals: Sequence[H13ProtectedRealGoal],
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
    rows: list[dict[str, Any]] = []
    tolerances: list[float] = []
    normalized: list[float] = []
    seen: set[str] = set()
    for goal in goals:
        if not isinstance(goal, H13ProtectedRealGoal):
            raise TypeError(
                "protected_goals must contain H13ProtectedRealGoal objects"
            )
        label = str(goal.label)
        if not label:
            raise ValueError("protected goal labels must be nonempty")
        if label in H13_REAL_GOAL_LABELS:
            raise ValueError(
                "a failed h13 target cannot be mixed into protected_goals"
            )
        if label in seen:
            raise ValueError(f"duplicate protected goal {label!r}")
        seen.add(label)
        base = _finite_float(
            goal.base_observable,
            label=f"{label}.base_observable",
        )
        reference = _finite_float(goal.reference, label=f"{label}.reference")
        tolerance = _finite_float(
            goal.tolerance,
            label=f"{label}.tolerance",
        )
        if tolerance <= 0.0:
            raise ValueError(f"{label}.tolerance must be positive")
        error = (base - reference) / tolerance
        if abs(error) > 1.0:
            raise ValueError(
                f"protected goal {label!r} does not pass its base Gate"
            )
        rows.append(
            {
                "label": label,
                "base_observable": base,
                "reference": reference,
                "tolerance": tolerance,
                "base_normalized_error_signed": error,
                "base_gate_pass": True,
                "contract_role": "separate_partial_prediction_guard",
            }
        )
        tolerances.append(tolerance)
        normalized.append(error)
    return (
        rows,
        np.asarray(tolerances, dtype=np.float64),
        np.asarray(normalized, dtype=np.float64),
    )


def _validate_sensitivity_matrix(
    values: Any,
    *,
    label: str,
    row_count: int = len(H13_REAL_GOAL_LABELS),
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    expected = (
        row_count,
        len(H13_BASE_INTERIOR_Z_PLANES_NM),
    )
    if array.shape != expected:
        raise ValueError(f"{label} must have shape {expected}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} contains NaN or Inf")
    return np.array(array, dtype=np.float64, order="C", copy=True)


def _step_consistency(
    fine_normalized: np.ndarray,
    coarse_normalized: np.ndarray,
    *,
    labels: Sequence[str],
) -> dict[str, Any]:
    floor = _PROFILE.normalized_sensitivity_zero_floor_per_nm
    scale = np.maximum.reduce(
        (
            np.abs(fine_normalized),
            np.abs(coarse_normalized),
            np.full(fine_normalized.shape, floor),
        )
    )
    disagreement = np.abs(fine_normalized - coarse_normalized) / scale
    influential = np.maximum(
        np.abs(fine_normalized),
        np.abs(coarse_normalized),
    ) > floor
    sign_agrees = (
        np.signbit(fine_normalized) == np.signbit(coarse_normalized)
    ) & (fine_normalized != 0.0) & (coarse_normalized != 0.0)
    entry_pass = (~influential) | (
        sign_agrees
        & (disagreement <= _PROFILE.step_relative_disagreement_limit)
    )
    failures = [
        {
            "goal": labels[int(goal_index)],
            "plane_index": int(plane_index),
            "plane_z_nm": H13_BASE_INTERIOR_Z_PLANES_NM[int(plane_index)],
            "fine_normalized_sensitivity_per_nm": float(
                fine_normalized[goal_index, plane_index]
            ),
            "coarse_normalized_sensitivity_per_nm": float(
                coarse_normalized[goal_index, plane_index]
            ),
            "relative_disagreement": float(
                disagreement[goal_index, plane_index]
            ),
            "sign_consistent": bool(
                sign_agrees[goal_index, plane_index]
            ),
        }
        for goal_index, plane_index in np.argwhere(~entry_pass)
    ]
    influential_disagreement = disagreement[influential]
    return {
        "pass": bool(np.all(entry_pass)),
        "fine_step": "plus_epsilon_minus_minus_epsilon_over_2epsilon",
        "coarse_step": "plus_2epsilon_minus_minus_2epsilon_over_4epsilon",
        "influential_entry_count": int(np.count_nonzero(influential)),
        "consistent_entry_count": int(np.count_nonzero(entry_pass)),
        "total_entry_count": int(entry_pass.size),
        "maximum_influential_relative_disagreement": (
            float(np.max(influential_disagreement))
            if influential_disagreement.size
            else 0.0
        ),
        "failure_count": len(failures),
        "failures": failures,
    }


def _rank_audit(normalized_sensitivity: np.ndarray) -> dict[str, Any]:
    singular_values = np.linalg.svd(
        normalized_sensitivity,
        compute_uv=False,
    )
    leading = float(singular_values[0]) if singular_values.size else 0.0
    tolerance = max(
        _PROFILE.rank_absolute_tolerance,
        _PROFILE.rank_relative_tolerance * leading,
    )
    rank = int(np.count_nonzero(singular_values > tolerance))
    row_norms = np.linalg.norm(normalized_sensitivity, axis=1)
    unusable_rows = [
        H13_REAL_GOAL_LABELS[index]
        for index, norm in enumerate(row_norms)
        if float(norm) <= _PROFILE.normalized_sensitivity_zero_floor_per_nm
    ]
    usable = not unusable_rows and leading > tolerance
    condition = (
        float(singular_values[0] / singular_values[-1])
        if rank == len(H13_REAL_GOAL_LABELS)
        and singular_values.size
        and float(singular_values[-1]) > tolerance
        else None
    )
    return {
        "pass": usable,
        "hard_gate": "each_failed_goal_row_must_have_nonzero_sensitivity",
        "full_row_rank_required": False,
        "rank_is_diagnostic": True,
        "normalized_row_rank": rank,
        "maximum_possible_row_rank": len(H13_REAL_GOAL_LABELS),
        "rank_tolerance": tolerance,
        "normalized_row_L2_norms_per_nm": [
            float(value) for value in row_norms
        ],
        "unusable_failed_goal_rows": unusable_rows,
        "singular_values": [float(value) for value in singular_values],
        "full_row_rank_condition_number": condition,
    }


def _support_geometry_constraints(
    support: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    variable_count = len(support)
    column = {plane_index: index for index, plane_index in enumerate(support)}
    base = np.asarray(
        (
            _PROFILE.fixed_material_z_min_nm,
            *H13_BASE_INTERIOR_Z_PLANES_NM,
            _PROFILE.fixed_material_z_max_nm,
        ),
        dtype=np.float64,
    )
    rows: list[np.ndarray] = []
    bounds: list[float] = []
    for interval in range(len(base) - 1):
        coefficient = np.zeros(variable_count, dtype=np.float64)
        left_plane_index = interval - 1
        right_plane_index = interval
        if left_plane_index in column:
            coefficient[column[left_plane_index]] -= 1.0
        if right_plane_index in column:
            coefficient[column[right_plane_index]] += 1.0
        base_width = float(base[interval + 1] - base[interval])
        rows.append(coefficient)
        bounds.append(
            _PROFILE.maximum_material_slab_width_nm - base_width
        )
        rows.append(-coefficient)
        bounds.append(
            base_width - _PROFILE.minimum_material_slab_width_nm
        )
    return np.asarray(rows), np.asarray(bounds)


def _solve_support(
    support: tuple[int, ...],
    base_error: np.ndarray,
    sensitivity: np.ndarray,
    protection_error: np.ndarray,
    protection_sensitivity: np.ndarray,
    *,
    enforce_protection: bool,
) -> dict[str, Any]:
    variable_count = len(support)
    selected = sensitivity[:, support]
    rows: list[np.ndarray] = []
    bounds: list[float] = []

    # |e + S dz| <= t
    for goal_index in range(len(base_error)):
        positive = np.zeros(variable_count + 1, dtype=np.float64)
        positive[:variable_count] = selected[goal_index]
        positive[-1] = -1.0
        rows.append(positive)
        bounds.append(-float(base_error[goal_index]))

        negative = np.zeros(variable_count + 1, dtype=np.float64)
        negative[:variable_count] = -selected[goal_index]
        negative[-1] = -1.0
        rows.append(negative)
        bounds.append(float(base_error[goal_index]))

    if enforce_protection:
        for goal_index in range(len(protection_error)):
            positive = np.zeros(variable_count + 1, dtype=np.float64)
            positive[:variable_count] = protection_sensitivity[
                goal_index, support
            ]
            rows.append(positive)
            bounds.append(1.0 - float(protection_error[goal_index]))

            negative = np.zeros(variable_count + 1, dtype=np.float64)
            negative[:variable_count] = -protection_sensitivity[
                goal_index, support
            ]
            rows.append(negative)
            bounds.append(1.0 + float(protection_error[goal_index]))

    geometry_rows, geometry_bounds = _support_geometry_constraints(support)
    for row, bound in zip(geometry_rows, geometry_bounds, strict=True):
        expanded = np.zeros(variable_count + 1, dtype=np.float64)
        expanded[:variable_count] = row
        rows.append(expanded)
        bounds.append(float(bound))

    objective = np.zeros(variable_count + 1, dtype=np.float64)
    objective[-1] = 1.0
    bounds_by_variable = [
        (
            -_PROFILE.maximum_absolute_displacement_nm,
            _PROFILE.maximum_absolute_displacement_nm,
        )
        for _ in support
    ]
    bounds_by_variable.append((0.0, None))
    result = linprog(
        objective,
        A_ub=np.asarray(rows, dtype=np.float64),
        b_ub=np.asarray(bounds, dtype=np.float64),
        bounds=bounds_by_variable,
        method="highs",
    )
    if not result.success:
        return {
            "feasible": False,
            "optimizer_status": int(result.status),
            "optimizer_message": str(result.message),
        }

    support_delta = np.asarray(result.x[:variable_count], dtype=np.float64)
    support_delta[np.abs(support_delta) < 1.0e-12] = 0.0
    full_delta = np.zeros(len(H13_BASE_INTERIOR_Z_PLANES_NM))
    full_delta[list(support)] = support_delta
    predicted = base_error + sensitivity @ full_delta
    protected_predicted = (
        protection_error + protection_sensitivity @ full_delta
    )
    minimax = float(np.max(np.abs(predicted)))
    base_minimax = float(np.max(np.abs(base_error)))
    benefit = (base_minimax - minimax) / base_minimax
    protected_pass = bool(
        np.all(np.abs(protected_predicted) <= 1.0 + 1.0e-10)
    )
    interior = (
        np.asarray(H13_BASE_INTERIOR_Z_PLANES_NM, dtype=np.float64)
        + full_delta
    )
    full_material_axis = np.concatenate(
        (
            np.asarray([_PROFILE.fixed_material_z_min_nm]),
            interior,
            np.asarray([_PROFILE.fixed_material_z_max_nm]),
        )
    )
    widths = np.diff(full_material_axis)
    geometry_pass = bool(
        np.all(
            widths
            >= _PROFILE.minimum_material_slab_width_nm - 1.0e-10
        )
        and np.all(
            widths
            <= _PROFILE.maximum_material_slab_width_nm + 1.0e-10
        )
        and np.max(np.abs(full_delta))
        <= _PROFILE.maximum_absolute_displacement_nm + 1.0e-10
    )
    return {
        "feasible": True,
        "optimizer_status": int(result.status),
        "optimizer_message": str(result.message),
        "support_delta_nm": [float(value) for value in support_delta],
        "full_delta_nm": [float(value) for value in full_delta],
        "predicted_normalized_errors": [
            float(value) for value in predicted
        ],
        "predicted_minimax_normalized_error": minimax,
        "predicted_benefit_fraction": benefit,
        "separate_protected_goals_preserved": protected_pass,
        "predicted_protected_normalized_errors": [
            float(value) for value in protected_predicted
        ],
        "geometry_pass": geometry_pass,
        "material_slab_widths_nm": [float(value) for value in widths],
        "candidate_full_z_axis_nm": [
            _PROFILE.fixed_domain_z_min_nm,
            _PROFILE.fixed_material_z_min_nm,
            *[float(value) for value in interior],
            _PROFILE.fixed_material_z_max_nm,
            _PROFILE.fixed_domain_z_max_nm,
        ],
    }


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        float(candidate["predicted_minimax_normalized_error"]),
        int(candidate["support_size"]),
        tuple(int(value) for value in candidate["support_plane_indices"]),
        tuple(round(float(value), 14) for value in candidate["support_delta_nm"]),
    )


def _not_run_pde_gate(*, candidate_selected: bool) -> dict[str, Any]:
    reason = (
        "prediction selected; a separate clean-SHA MPI8 unchanged-topology "
        "control and candidate PDE are required"
        if candidate_selected
        else "no prediction qualified for a formal PDE"
    )
    return {
        "status": "not_run",
        "reason": reason,
        "prediction_grants_accuracy_credit": False,
        "all_12_significant_channels_reserved_for_formal_PDE": True,
        "clean_sha_mpi8_execution": "not_run",
        "unchanged_topology_control": "not_run",
        "full_explicit_true_residual_le_1e-9": "not_run",
        "R00_R_T_Aclosure": "not_run",
        "normalized_vector": "not_run",
        "significant_power_12_of_12": "not_run",
        "significant_complex_amplitude_12_of_12": "not_run",
        "selected_volume_and_interface_fields": "not_run",
        "geometry_tag_floquet_orientation": "not_run",
        "exact_sequence": "not_run",
        "no_swap": "not_run",
    }


def select_h13_signed_z_shape_candidate(
    *,
    goals: Sequence[H13RealGoal],
    sensitivity_at_epsilon: Any,
    sensitivity_at_2epsilon: Any,
    epsilon_nm: float,
    source_hashes: Mapping[str, str],
    protected_goals: Sequence[H13ProtectedRealGoal] = (),
    protected_sensitivity_at_epsilon: Any | None = None,
    protected_sensitivity_at_2epsilon: Any | None = None,
) -> dict[str, Any]:
    """Select at most one prediction-only h13 one/two-plane candidate.

    ``sensitivity_at_epsilon`` and ``sensitivity_at_2epsilon`` are signed
    central-difference derivatives in observable units per nanometre.  They
    must have shape ``(6, 9)`` and be backed by the five unique source hashes
    required by the frozen profile.  Any already-passing scalar screens must
    be supplied through the separate ``protected_*`` arguments.  They do not
    replace the formal 12-channel PDE Gate.
    """

    epsilon = _finite_float(epsilon_nm, label="epsilon_nm")
    if epsilon <= 0.0:
        raise ValueError("epsilon_nm must be positive")
    if 2.0 * epsilon > _PROFILE.maximum_absolute_displacement_nm + 1.0e-12:
        raise ValueError(
            "the +/-2epsilon audit must remain inside the 0.6 nm trust region"
        )
    verified_hashes = _validate_source_hashes(source_hashes)
    goal_rows, tolerances, base_error, failed_gate_audit = _validate_goals(
        goals
    )
    (
        protected_rows,
        protected_tolerances,
        protection_error,
    ) = _validate_protected_goals(protected_goals)
    fine = _validate_sensitivity_matrix(
        sensitivity_at_epsilon,
        label="sensitivity_at_epsilon",
    )
    coarse = _validate_sensitivity_matrix(
        sensitivity_at_2epsilon,
        label="sensitivity_at_2epsilon",
    )
    protected_row_count = len(protected_rows)
    if protected_row_count:
        if (
            protected_sensitivity_at_epsilon is None
            or protected_sensitivity_at_2epsilon is None
        ):
            raise ValueError(
                "protected goals require separate epsilon and 2epsilon "
                "sensitivity matrices"
            )
        protected_fine = _validate_sensitivity_matrix(
            protected_sensitivity_at_epsilon,
            label="protected_sensitivity_at_epsilon",
            row_count=protected_row_count,
        )
        protected_coarse = _validate_sensitivity_matrix(
            protected_sensitivity_at_2epsilon,
            label="protected_sensitivity_at_2epsilon",
            row_count=protected_row_count,
        )
    else:
        if (
            protected_sensitivity_at_epsilon is not None
            or protected_sensitivity_at_2epsilon is not None
        ):
            raise ValueError(
                "protected sensitivity matrices require protected_goals"
            )
        protected_fine = np.zeros(
            (0, len(H13_BASE_INTERIOR_Z_PLANES_NM)),
            dtype=np.float64,
        )
        protected_coarse = protected_fine.copy()
    fine_normalized = fine / tolerances[:, None]
    coarse_normalized = coarse / tolerances[:, None]
    protected_fine_normalized = (
        protected_fine / protected_tolerances[:, None]
        if protected_row_count
        else protected_fine
    )
    protected_coarse_normalized = (
        protected_coarse / protected_tolerances[:, None]
        if protected_row_count
        else protected_coarse
    )

    profile = _profile_payload()
    profile_hash = _canonical_sha256(profile)
    goal_contract_hash = _canonical_sha256(goal_rows)
    geometry_hash = _canonical_sha256(
        {
            "base_full_z_axis_nm": [
                _PROFILE.fixed_domain_z_min_nm,
                _PROFILE.fixed_material_z_min_nm,
                *H13_BASE_INTERIOR_Z_PLANES_NM,
                _PROFILE.fixed_material_z_max_nm,
                _PROFILE.fixed_domain_z_max_nm,
            ],
            "fixed_material_interfaces_nm": [
                _PROFILE.fixed_material_z_min_nm,
                _PROFILE.fixed_material_z_max_nm,
            ],
        }
    )
    fine_hash = _array_sha256(fine)
    coarse_hash = _array_sha256(coarse)
    protected_contract_hash = _canonical_sha256(protected_rows)
    protected_fine_hash = _array_sha256(protected_fine)
    protected_coarse_hash = _array_sha256(protected_coarse)
    input_hashes = {
        "profile_sha256": profile_hash,
        "h13_failed_goal_contract_sha256": goal_contract_hash,
        "separate_protected_goal_contract_sha256": protected_contract_hash,
        "h13_geometry_sha256": geometry_hash,
        "signed_sensitivity_epsilon_sha256": fine_hash,
        "signed_sensitivity_2epsilon_sha256": coarse_hash,
        "protected_signed_sensitivity_epsilon_sha256": (
            protected_fine_hash
        ),
        "protected_signed_sensitivity_2epsilon_sha256": (
            protected_coarse_hash
        ),
        "source_evidence_sha256": verified_hashes,
    }
    input_hashes["complete_selector_input_sha256"] = _canonical_sha256(
        {
            "profile_sha256": profile_hash,
            "goal_contract_sha256": goal_contract_hash,
            "geometry_sha256": geometry_hash,
            "fine_sensitivity_sha256": fine_hash,
            "coarse_sensitivity_sha256": coarse_hash,
            "protected_goal_contract_sha256": protected_contract_hash,
            "protected_fine_sensitivity_sha256": protected_fine_hash,
            "protected_coarse_sensitivity_sha256": protected_coarse_hash,
            "epsilon_nm": epsilon,
            "source_evidence_sha256": verified_hashes,
        }
    )

    consistency = _step_consistency(
        fine_normalized,
        coarse_normalized,
        labels=H13_REAL_GOAL_LABELS,
    )
    protected_consistency = _step_consistency(
        protected_fine_normalized,
        protected_coarse_normalized,
        labels=[row["label"] for row in protected_rows],
    )
    rank = _rank_audit(fine_normalized)
    base_minimax = float(np.max(np.abs(base_error)))
    base_summary = {
        "six_independent_failed_real_goals": goal_rows,
        "failed_gate_validation": failed_gate_audit,
        "base_minimax_normalized_error": base_minimax,
        "individual_complex_component_pass_signature": "not_defined",
    }
    protection_summary = {
        "scope": "separate_partial_prediction_screen_only",
        "formal_12_channel_PDE_gate_still_required": True,
        "protected_goal_count": protected_row_count,
        "goals": protected_rows,
    }

    common: dict[str, Any] = {
        "schema_version": _PROFILE.schema_version,
        "frozen_profile": profile,
        "frozen_profile_sha256": profile_hash,
        "input_hashes": input_hashes,
        "source_contract": {
            "caller_supplied_measured_sensitivities_only": True,
            "synthetic_sensitivity_generation": False,
            "manual_plane_override": False,
            "source_hashes_unique_and_complete": True,
            "perturbation_hashes_are_nine_plane_bundle_manifests": True,
            "six_failed_targets_and_protected_goals_are_separate": True,
        },
        "epsilon_nm": epsilon,
        "two_epsilon_nm": 2.0 * epsilon,
        "base": base_summary,
        "separate_protection_contract": protection_summary,
        "preflight": {
            "failed_goal_step_consistency": consistency,
            "protected_goal_step_consistency": protected_consistency,
            "failed_goal_sensitivity_rank_diagnostic": rank,
        },
        "resource_identity": profile["resource_identity"],
        "ordinary_default_changed": False,
    }

    if not consistency["pass"] or not protected_consistency["pass"]:
        return {
            **common,
            "status": "controlled_negative_step_inconsistent",
            "classification": "controlled_negative",
            "decision": "no_candidate",
            "enumeration": {
                "single_support_count_expected": 9,
                "pair_support_count_expected": 36,
                "support_count_evaluated": 0,
                "candidates": [],
            },
            "selected_candidate": None,
            "pde_gate": _not_run_pde_gate(candidate_selected=False),
        }
    if not rank["pass"]:
        return {
            **common,
            "status": "controlled_negative_unusable_sensitivity",
            "classification": "controlled_negative",
            "decision": "no_candidate",
            "enumeration": {
                "single_support_count_expected": 9,
                "pair_support_count_expected": 36,
                "support_count_evaluated": 0,
                "candidates": [],
            },
            "selected_candidate": None,
            "pde_gate": _not_run_pde_gate(candidate_selected=False),
        }

    supports = [
        *((index,) for index in range(len(H13_BASE_INTERIOR_Z_PLANES_NM))),
        *combinations(range(len(H13_BASE_INTERIOR_Z_PLANES_NM)), 2),
    ]
    candidates: list[dict[str, Any]] = []
    protected_blocked_positive_count = 0
    for support in supports:
        protected = _solve_support(
            support,
            base_error,
            fine_normalized,
            protection_error,
            protected_fine_normalized,
            enforce_protection=True,
        )
        counterfactual = _solve_support(
            support,
            base_error,
            fine_normalized,
            protection_error,
            protected_fine_normalized,
            enforce_protection=False,
        )
        candidate: dict[str, Any] = {
            "support_plane_indices": [int(value) for value in support],
            "support_base_z_nm": [
                H13_BASE_INTERIOR_Z_PLANES_NM[index] for index in support
            ],
            "support_size": len(support),
            **protected,
        }
        if protected["feasible"]:
            candidate["eligible_for_selection"] = bool(
                protected["geometry_pass"]
                and protected["separate_protected_goals_preserved"]
                and protected["predicted_benefit_fraction"]
                >= _PROFILE.minimum_predicted_benefit_fraction - 1.0e-12
            )
        else:
            candidate["eligible_for_selection"] = False

        counterfactual_summary: dict[str, Any] = {
            "feasible": bool(counterfactual["feasible"]),
        }
        if counterfactual["feasible"]:
            counterfactual_summary.update(
                {
                    "predicted_benefit_fraction": counterfactual[
                        "predicted_benefit_fraction"
                    ],
                    "separate_protected_goals_preserved": counterfactual[
                        "separate_protected_goals_preserved"
                    ],
                }
            )
            if (
                counterfactual["predicted_benefit_fraction"]
                >= _PROFILE.minimum_predicted_benefit_fraction - 1.0e-12
                and not counterfactual[
                    "separate_protected_goals_preserved"
                ]
            ):
                protected_blocked_positive_count += 1
        candidate["unprotected_counterfactual"] = counterfactual_summary
        candidates.append(candidate)

    eligible = [
        candidate
        for candidate in candidates
        if candidate["eligible_for_selection"]
    ]
    eligible.sort(key=_candidate_sort_key)
    selected = eligible[0] if eligible else None
    enumeration = {
        "single_support_count_expected": 9,
        "pair_support_count_expected": 36,
        "support_count_evaluated": len(candidates),
        "eligible_support_count": len(eligible),
        "protected_blocked_positive_support_count": (
            protected_blocked_positive_count
        ),
        "candidates": candidates,
    }

    if selected is None:
        passed_guard_blocked = protected_blocked_positive_count > 0
        status = (
            "controlled_negative_passed_channel_degradation"
            if passed_guard_blocked
            else "controlled_negative_no_signal"
        )
        return {
            **common,
            "status": status,
            "classification": "controlled_negative",
            "decision": "no_candidate",
            "no_candidate_reason": (
                "all >=5% unprotected predictions degrade an already-passing "
                "h13 target"
                if passed_guard_blocked
                else "no protected one/two-plane support predicts >=5% benefit"
            ),
            "enumeration": enumeration,
            "selected_candidate": None,
            "pde_gate": _not_run_pde_gate(candidate_selected=False),
        }

    # Return a copy without the diagnostic counterfactual as the one formal
    # proposal.  The complete 45-support audit remains in ``enumeration``.
    selected_candidate = {
        key: value
        for key, value in selected.items()
        if key != "unprotected_counterfactual"
    }
    selected_candidate["selection_origin"] = (
        "deterministic_45_support_minimax_enumeration"
    )
    selected_candidate["prediction_only"] = True
    return {
        **common,
        "status": "prediction_candidate_selected",
        "classification": "positive_prediction_not_pde_qualified",
        "decision": "run_one_formal_unchanged_topology_control_and_candidate",
        "enumeration": enumeration,
        "selected_candidate": selected_candidate,
        "pde_gate": _not_run_pde_gate(candidate_selected=True),
    }


__all__ = [
    "H13_BASE_INTERIOR_Z_PLANES_NM",
    "H13_COMPLEX_FAILURE_PAIRS",
    "H13_POWER_FAILURE_INDICES",
    "H13_REAL_GOAL_LABELS",
    "H13ProtectedRealGoal",
    "H13RealGoal",
    "select_h13_signed_z_shape_candidate",
]
