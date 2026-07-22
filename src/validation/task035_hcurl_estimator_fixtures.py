from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


CANDIDATE_METHODS = (
    "R1_standard_residual_jump",
    "R2_frequency_scaled_residual",
    "R3_recovery_hcurl",
    "R4_equilibrated_patch",
    "R5_hierarchical_two_level",
    "G1_dwr_total_rta",
    "G2_dwr_r00_order_amplitudes",
    "B1_dtn_truncation_split",
    "M1_internal_mode_truncation_split",
)

RESIDUAL_COMPONENTS = (
    "volume_curl_residual",
    "scalar_divergence_residual",
    "curl_flux_jump",
    "material_interface_term",
    "external_dtn_boundary_term",
    "floquet_pair_residual",
    "hybrid_interface_et_residual",
    "hybrid_interface_ht_residual",
)


def _vector(values: ArrayLike) -> NDArray[np.complex128]:
    result = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not np.all(np.isfinite(result)):
        raise ValueError("values must be finite")
    return result


def hermitian_squared_norm(
    values: ArrayLike, weights: ArrayLike | None = None
) -> float:
    vector = _vector(values)
    if weights is None:
        value = np.vdot(vector, vector)
    else:
        weight = np.asarray(weights, dtype=float).reshape(-1)
        if weight.shape != vector.shape or np.any(weight < 0.0):
            raise ValueError("weights must be finite nonnegative and shape-compatible")
        if not np.all(np.isfinite(weight)):
            raise ValueError("weights must be finite nonnegative and shape-compatible")
        value = np.vdot(vector, weight * vector)
    if abs(value.imag) > 1.0e-12 * max(1.0, abs(value.real)):
        raise ValueError("Hermitian squared norm has a non-real value")
    return max(0.0, float(value.real))


def standard_residual_indicator(
    components: Mapping[str, ArrayLike],
) -> dict[str, Any]:
    unknown = set(components) - set(RESIDUAL_COMPONENTS)
    if unknown:
        raise ValueError(f"unknown residual components: {sorted(unknown)}")
    squared = {
        name: hermitian_squared_norm(values)
        for name, values in sorted(components.items())
    }
    total_squared = math.fsum(squared.values())
    return {
        "component_squared": squared,
        "total_squared": total_squared,
        "total": math.sqrt(total_squared),
    }


def frequency_scaled_indicator(
    indicator: float, *, wave_number: float, cell_size: float, degree: int
) -> dict[str, float | str]:
    eta = float(indicator)
    k_abs = abs(float(wave_number))
    h = float(cell_size)
    if not math.isfinite(eta) or eta < 0.0 or h <= 0.0 or degree < 1:
        raise ValueError("indicator, cell_size, and degree are outside their domain")
    chi = k_abs * h / degree
    return {
        "chi": chi,
        "unscaled_indicator": eta,
        "status": "resolution_diagnostic_pass",
    }


def trace_residual(
    master: ArrayLike,
    slave: ArrayLike,
    *,
    phase: complex = 1.0 + 0.0j,
    orientation: int = 1,
) -> float:
    if orientation not in (-1, 1):
        raise ValueError("orientation must be -1 or 1")
    left = _vector(master)
    right = _vector(slave)
    if left.shape != right.shape:
        raise ValueError("trace vectors must have identical shape")
    defect = right - orientation * complex(phase) * left
    return math.sqrt(hermitian_squared_norm(defect))


def recovery_indicator(field: ArrayLike, recovered_field: ArrayLike) -> float:
    field_vector = _vector(field)
    recovered = _vector(recovered_field)
    if field_vector.shape != recovered.shape:
        raise ValueError("field and recovered_field must have identical shape")
    return math.sqrt(hermitian_squared_norm(recovered - field_vector))


def local_energy_correction(
    matrix: ArrayLike, residual: ArrayLike
) -> dict[str, Any]:
    operator = np.asarray(matrix, dtype=np.complex128)
    right_hand_side = _vector(residual)
    if operator.shape != (right_hand_side.size, right_hand_side.size):
        raise ValueError("local matrix and residual dimensions do not match")
    if not np.allclose(operator, operator.conj().T, rtol=0.0, atol=1.0e-13):
        raise ValueError("local matrix must be Hermitian")
    correction = np.linalg.solve(operator, right_hand_side)
    energy_squared = np.vdot(correction, operator @ correction)
    algebraic_residual = operator @ correction - right_hand_side
    return {
        "indicator": math.sqrt(max(0.0, float(energy_squared.real))),
        "equilibrium_residual": math.sqrt(
            hermitian_squared_norm(algebraic_residual)
        ),
        "correction": correction,
    }


def dwr_error_estimate(residual: ArrayLike, adjoint_weight: ArrayLike) -> float:
    primal = _vector(residual)
    dual = _vector(adjoint_weight)
    if primal.shape != dual.shape:
        raise ValueError("residual and adjoint_weight must have identical shape")
    return abs(np.vdot(dual, primal))


def real_linear_goal(field: ArrayLike, goal_vector: ArrayLike) -> float:
    state = _vector(field)
    functional = _vector(goal_vector)
    if state.shape != functional.shape:
        raise ValueError("field and goal_vector must have identical shape")
    return float(np.vdot(functional, state).real)


def real_linear_goal_derivative(
    direction: ArrayLike, goal_vector: ArrayLike
) -> float:
    return real_linear_goal(direction, goal_vector)


def goal_derivative_check(
    field: ArrayLike,
    direction: ArrayLike,
    goal_vector: ArrayLike,
    *,
    step: float = 1.0e-7,
) -> dict[str, float]:
    state = _vector(field)
    perturbation = _vector(direction)
    if step <= 0.0:
        raise ValueError("step must be positive")
    finite_difference = (
        real_linear_goal(state + step * perturbation, goal_vector)
        - real_linear_goal(state - step * perturbation, goal_vector)
    ) / (2.0 * step)
    analytic = real_linear_goal_derivative(perturbation, goal_vector)
    return {
        "analytic": analytic,
        "finite_difference": finite_difference,
        "absolute_error": abs(finite_difference - analytic),
    }


def combine_goal_estimates(
    estimates: Mapping[str, float], weights: Mapping[str, float]
) -> float:
    if set(estimates) != set(weights):
        raise ValueError("goal estimates and weights must have the same keys")
    terms = []
    for name in sorted(estimates):
        estimate = float(estimates[name])
        weight = float(weights[name])
        if not math.isfinite(estimate) or not math.isfinite(weight):
            raise ValueError("goal estimates and weights must be finite")
        terms.append(abs(weight) * abs(estimate))
    return math.fsum(terms)


def truncation_error_split(
    spatial: float, dtn: float, internal_modes: float, qep_residual: float
) -> dict[str, float]:
    values = {
        "spatial": float(spatial),
        "dtn_truncation": float(dtn),
        "internal_mode_truncation": float(internal_modes),
        "qep_eigen_residual_diagnostic": float(qep_residual),
    }
    if any(not math.isfinite(value) or value < 0.0 for value in values.values()):
        raise ValueError("error split values must be finite and nonnegative")
    values["estimator_total"] = math.fsum(
        (values["spatial"], values["dtn_truncation"], values["internal_mode_truncation"])
    )
    return values


def canonical_partition_sum(
    cell_ids: Sequence[int], cell_squared: Sequence[float], mpi_size: int
) -> dict[str, Any]:
    ids = [int(value) for value in cell_ids]
    values = [float(value) for value in cell_squared]
    if len(ids) != len(values) or len(set(ids)) != len(ids):
        raise ValueError("cell global IDs must be unique and shape-compatible")
    if mpi_size < 1 or any(value < 0.0 for value in values):
        raise ValueError("mpi_size and cell contributions are outside their domain")
    canonical = sorted(zip(ids, values, strict=True))
    rank_sums = [0.0] * mpi_size
    for cell_id, value in canonical:
        rank_sums[cell_id % mpi_size] += value
    return {
        "canonical_cell_ids": [cell_id for cell_id, _ in canonical],
        "rank_sums": rank_sums,
        "global_sum": math.fsum(rank_sums),
    }


def homogeneous_periodic_fixture() -> dict[str, Any]:
    phase = np.exp(0.37j)
    master = np.array([1.0 + 0.2j, -0.3 + 0.4j, 0.15 - 0.1j])
    slave = -phase * master
    exact = trace_residual(master, slave, phase=phase, orientation=-1)
    broken_orientation = trace_residual(
        master, slave, phase=phase, orientation=1
    )
    broken_phase = trace_residual(
        master, slave, phase=np.exp(0.41j), orientation=-1
    )
    residual = standard_residual_indicator(
        {
            "volume_curl_residual": [1.0e-15 + 2.0e-15j],
            "curl_flux_jump": [2.0e-15 - 1.0e-15j],
            "floquet_pair_residual": [exact],
        }
    )
    partitions = {
        str(size): canonical_partition_sum(
            [41, 7, 19, 3], [0.04, 0.01, 0.03, 0.02], size
        )
        for size in (1, 2, 4)
    }
    return {
        "name": "homogeneous_periodic_analytic_field",
        "scope": "analytic_fixture_not_target_grating",
        "exact_indicator": residual["total"],
        "broken_orientation_indicator": broken_orientation,
        "broken_phase_indicator": broken_phase,
        "mpi_partitions": partitions,
    }


def flat_lossy_layer_fixture() -> dict[str, Any]:
    state = np.array([0.8 + 0.1j, 0.25 - 0.3j, -0.1 + 0.05j])
    direction = np.array([0.2 - 0.1j, -0.15 + 0.07j, 0.04 + 0.08j])
    goals = {
        "R": np.array([1.0 + 0.2j, 0.0, 0.0]),
        "T": np.array([0.0, 0.7 - 0.1j, 0.0]),
        "A": np.array([-0.4 + 0.3j, 0.2, 0.5 - 0.2j]),
    }
    checks = {
        name: goal_derivative_check(state, direction, vector)
        for name, vector in goals.items()
    }
    refinement = [0.2 * 0.5**level for level in range(5)]
    dtn_exact = trace_residual([0.4 + 0.2j], [0.4 + 0.2j])
    dtn_broken = trace_residual([0.4 + 0.2j], [0.46 + 0.16j])
    complex_weighted = hermitian_squared_norm(
        [0.2 + 0.4j, -0.3 + 0.1j], [1.7, 0.8]
    )
    return {
        "name": "flat_lossy_layer_known_modal_solution",
        "scope": "analytic_fixture_not_target_grating",
        "complex_material_weighted_squared": complex_weighted,
        "goal_derivative_checks": checks,
        "dtn_exact_indicator": dtn_exact,
        "dtn_broken_indicator": dtn_broken,
        "uniform_refinement_indicators": refinement,
    }


def material_interface_fixture() -> dict[str, Any]:
    tangential_field = np.array([0.6 + 0.2j, -0.25 + 0.1j])
    exact_interface = trace_residual(tangential_field, tangential_field)
    corrupted_tag = trace_residual(
        tangential_field, 1.35 * tangential_field
    )
    coefficient_aware_recovery = recovery_indicator(
        [1.0 + 0.2j, 1.0 + 0.2j], [1.0 + 0.2j, 1.0 + 0.2j]
    )
    naive_recovery = recovery_indicator(
        [1.0 + 0.2j, 2.0 + 0.4j], [1.5 + 0.3j, 1.5 + 0.3j]
    )
    patch = local_energy_correction(
        [[2.0, -0.25j], [0.25j, 1.5]], [0.3 + 0.1j, -0.2j]
    )
    directional_cells = [
        {"cell_id": 5, "indicator_squared": 0.64, "preferred_axis": "x"},
        {"cell_id": 9, "indicator_squared": 0.21, "preferred_axis": "z"},
        {"cell_id": 2, "indicator_squared": 0.04, "preferred_axis": "isotropic"},
    ]
    directional_cells.sort(key=lambda row: (-row["indicator_squared"], row["cell_id"]))
    return {
        "name": "material_interface_manufactured_corner",
        "scope": "manufactured_fixture_not_target_grating",
        "exact_interface_indicator": exact_interface,
        "corrupted_material_tag_indicator": corrupted_tag,
        "coefficient_aware_recovery_indicator": coefficient_aware_recovery,
        "naive_recovery_jump_indicator": naive_recovery,
        "equilibrated_patch_indicator": patch["indicator"],
        "equilibrium_residual": patch["equilibrium_residual"],
        "anisotropic_marking": directional_cells,
    }


def hybrid_interface_fixture() -> dict[str, Any]:
    electric = np.array([0.5 + 0.1j, -0.2 + 0.3j])
    magnetic = np.array([-0.15 + 0.05j, 0.4 - 0.2j])
    exact_et = trace_residual(electric, electric)
    exact_ht = trace_residual(magnetic, magnetic)
    broken_et = trace_residual(electric, electric + [0.03, -0.02j])
    broken_ht = trace_residual(magnetic, magnetic + [0.01j, 0.04])
    split = truncation_error_split(0.08, 0.015, 0.025, 2.0e-10)
    return {
        "name": "hybrid_analytic_mode_interface",
        "scope": "analytic_fixture_not_target_grating",
        "exact_et_indicator": exact_et,
        "exact_ht_indicator": exact_ht,
        "broken_et_indicator": broken_et,
        "broken_ht_indicator": broken_ht,
        "error_split": split,
        "qep_counted_as_spatial": False,
    }


def build_fixture_summary() -> dict[str, Any]:
    fixtures = [
        homogeneous_periodic_fixture(),
        flat_lossy_layer_fixture(),
        material_interface_fixture(),
        hybrid_interface_fixture(),
    ]
    method_status = {
        name: "algebraic_precursor_pass" for name in CANDIDATE_METHODS
    }
    method_status["R2_frequency_scaled_residual"] = "resolution_diagnostic_pass"
    method_status["R4_equilibrated_patch"] = "formula_defined"
    return {
        "schema_version": "task035.estimator-fixtures.v1",
        "status": "algebraic_precursor_pass",
        "canonical": False,
        "production_qualified": False,
        "pde_run": False,
        "target_grating_run": False,
        "method_status": method_status,
        "fixtures": fixtures,
        "limitations": [
            "NumPy/small-matrix algebraic precursor validation only",
            "R2 records chi=abs(k)h/p only and does not rescale an estimator",
            "R4 has only a local SPD precursor; constrained equilibration is pending",
            "no adaptive mesh backend or production runner is selected",
        ],
    }
