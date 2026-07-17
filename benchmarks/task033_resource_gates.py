from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from typing import Any


GIB = 1024**3
DEFAULT_DOCKER_LIMIT_GIB = 13.6485

DEGREES = (1, 2, 3, 4)
MESH_LEVELS_NM = (5.0, 3.0, 2.5, 2.0, 1.5)
REDUCED_EQUAL_ACCURACY_LEVELS_NM = (10.0, 7.5)

# Task033 task.md, Phase 4. ``policy_class`` has only the three operational
# classes used by the planner. The more specific task wording is retained
# separately so p1/h2 and p1/h1.5 are not mistaken for unconditional launches.
POLICY_MATRIX: dict[int, dict[float, tuple[str, str]]] = {
    1: {
        5.0: ("required", "required"),
        3.0: ("required", "required"),
        2.5: ("required", "required"),
        2.0: ("required", "required_if_gate"),
        1.5: ("required", "required_if_gate"),
    },
    2: {
        5.0: ("required", "required"),
        3.0: ("required", "required"),
        2.5: ("required", "required"),
        2.0: ("conditional", "conditional"),
        1.5: ("locked_by_default", "locked_by_default"),
    },
    3: {
        5.0: ("required", "required"),
        3.0: ("conditional", "conditional"),
        2.5: ("conditional", "conditional"),
        2.0: ("locked_by_default", "locked_by_default"),
        1.5: ("locked_by_default", "locked_by_default"),
    },
    4: {
        5.0: ("required", "required"),
        3.0: ("conditional", "conditional"),
        2.5: ("locked_by_default", "locked_by_default"),
        2.0: ("locked_by_default", "locked_by_default"),
        1.5: ("locked_by_default", "locked_by_default"),
    },
}

CONDITIONAL_PREDECESSOR = {
    "p2_h2": "p2_h2p5",
    "p3_h3": "p3_h5",
    "p3_h2p5": "p3_h3",
    "p4_h3": "p4_h5",
}

# Clean Task032 p2/M160 measurements. The factor NNZ inventories are the sums
# of the bottom/top MUMPS factor matrix inventories in the cited records. The
# payloads are likewise the summed PETSc matrix-memory estimates. These are
# measured calibration inputs, not Task033 runs.
TASK032_ANCHOR = {
    "solver_path": "modal-schur-memory-minimal",
    "degree": 2,
    "modes_per_direction": 160,
    "source_commit": "793354af0ac72cbfe1c6eb1030b2438afe10c101",
    "h5": {
        "h_nm": 5.0,
        "local_fe_rows": 13_652,
        "total_rows": 14_052,
        "assembled_nnz": 2_000_624,
        "factor_nnz": 6_438_552,
        "simultaneous_worker_rss_gib": 1.6977119445800781,
        "factor_payload_gib": 0.14401517808437347,
        "record": (
            "benchmarks/cases/080_hybrid_fem_modal_direct_baseline/"
            "records/memory_h5_schur_minimal.json"
        ),
        "data_identity": "measured",
    },
    "h3": {
        "h_nm": 3.0,
        "local_fe_rows": 68_396,
        "total_rows": 68_796,
        "assembled_nnz": 8_594_673,
        "factor_nnz": 60_672_040,
        "simultaneous_worker_rss_gib": 3.224353790283203,
        "factor_payload_gib": 1.3566359728574753,
        "record": (
            "benchmarks/cases/080_hybrid_fem_modal_direct_baseline/"
            "records/memory_h3_schur_minimal.json"
        ),
        "data_identity": "measured",
    },
}

BASE_GATE_GIB = {
    "host_hard_budget": 14.0,
    "two_center_limit": 11.5,
    "conservative_upper_limit": 12.8,
    "warning": 11.5,
    "controlled_termination": 13.0,
}


def _mesh_tag(h_nm: float) -> str:
    return f"{h_nm:g}".replace(".", "p")


def matrix_key(degree: int, h_nm: float) -> str:
    return f"p{degree}_h{_mesh_tag(h_nm)}"


def _positive_finite(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite.")
    return value


def scaled_gate_limits(container_limit_gib: float | None = None) -> dict[str, Any]:
    """Return Task033 limits scaled to the effective Docker/host ceiling.

    The default is the Phase-0 measured Docker Engine ``MemTotal`` rather than
    the nominal 14 GiB policy ceiling. A caller may inject a refreshed numeric
    limit. A larger value never widens the 14 GiB host envelope.
    """

    host_hard = BASE_GATE_GIB["host_hard_budget"]
    uses_phase0_default = container_limit_gib is None
    container = (
        DEFAULT_DOCKER_LIMIT_GIB
        if uses_phase0_default
        else _positive_finite("container_limit_gib", container_limit_gib)
    )
    effective = min(host_hard, container)
    scale = effective / host_hard
    return {
        "host_hard_budget_gib": host_hard,
        "container_limit_gib": container,
        "container_limit_identity": (
            "measured_phase0_docker_engine_memtotal"
            if uses_phase0_default
            else "caller_supplied_numeric_limit"
        ),
        "effective_hard_budget_gib": effective,
        "scale_from_14_gib": scale,
        "two_center_limit_gib": BASE_GATE_GIB["two_center_limit"] * scale,
        "conservative_upper_limit_gib": (
            BASE_GATE_GIB["conservative_upper_limit"] * scale
        ),
        "warning_gib": BASE_GATE_GIB["warning"] * scale,
        "controlled_termination_gib": (BASE_GATE_GIB["controlled_termination"] * scale),
    }


def nedelec_hex_local_dimension(degree: int) -> int:
    """Dimension of the tensor-product first-kind H(curl) cell space."""

    if degree not in DEGREES:
        raise ValueError(f"degree must be one of {DEGREES}.")
    return 3 * degree * (degree + 1) ** 2


def _power_exponent(y5: float, y3: float) -> float:
    return math.log(y3 / y5) / math.log(5.0 / 3.0)


def _power_exponent_from_x(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.log(y2 / y1) / math.log(x2 / x1)


def _ceil_stable(value: float) -> int:
    """Ceil a projection without a one-count drift at exact fit anchors."""

    nearest = round(value)
    if math.isclose(value, nearest, rel_tol=1.0e-12, abs_tol=1.0e-9):
        return int(nearest)
    return math.ceil(value)


def _factor_projection(assembled_nnz: int) -> dict[str, float | int | str]:
    """Project factor payload from this case's own assembled NNZ and fill.

    This center intentionally does not use the effective-p/h resolution scalar
    used by the first RSS center. Fill is extrapolated against assembled NNZ
    from the two measured Task032 factor inventories; payload then follows from
    projected factor NNZ and a conservative measured bytes-per-factor-NNZ.
    """

    h5 = TASK032_ANCHOR["h5"]
    h3 = TASK032_ANCHOR["h3"]
    h5_fill = float(h5["factor_nnz"]) / float(h5["assembled_nnz"])
    h3_fill = float(h3["factor_nnz"]) / float(h3["assembled_nnz"])
    fill_exponent = _power_exponent_from_x(
        float(h5["assembled_nnz"]),
        h5_fill,
        float(h3["assembled_nnz"]),
        h3_fill,
    )
    extrapolated_fill = (
        h3_fill * (float(assembled_nnz) / float(h3["assembled_nnz"])) ** fill_exponent
    )
    projected_fill = max(1.0, extrapolated_fill)
    projected_factor_nnz = _ceil_stable(float(assembled_nnz) * projected_fill)
    bytes_per_factor_nnz = max(
        float(item["factor_payload_gib"]) * GIB / float(item["factor_nnz"])
        for item in (h5, h3)
    )
    projected_payload = projected_factor_nnz * bytes_per_factor_nnz / GIB

    factor_slope = (
        float(h3["simultaneous_worker_rss_gib"])
        - float(h5["simultaneous_worker_rss_gib"])
    ) / (float(h3["factor_payload_gib"]) - float(h5["factor_payload_gib"]))
    factor_intercept = float(h3["simultaneous_worker_rss_gib"]) - (
        factor_slope * float(h3["factor_payload_gib"])
    )
    center = factor_intercept + factor_slope * projected_payload
    return {
        "center_gib": center,
        "projected_factor_payload_gib": projected_payload,
        "projected_factor_nnz": projected_factor_nnz,
        "projected_fill_ratio": projected_fill,
        "unclamped_projected_fill_ratio": extrapolated_fill,
        "minimum_fill_ratio": 1.0,
        "observed_fill_vs_assembled_nnz_exponent": fill_exponent,
        "conservative_bytes_per_factor_nnz": bytes_per_factor_nnz,
        "rss_per_factor_payload_slope": factor_slope,
        "rss_intercept_gib": factor_intercept,
        "independent_variable": "projected assembled NNZ and factor fill",
        "data_identity": "predicted_from_measured_task032_factor_inventories",
    }


def project_resources(degree: int, h_nm: float) -> dict[str, Any]:
    """Project p/h algebra and two memory centers without running a PDE."""

    if degree not in DEGREES:
        raise ValueError(f"degree must be one of {DEGREES}.")
    h_nm = _positive_finite("h_nm", h_nm)

    h5 = TASK032_ANCHOR["h5"]
    h3 = TASK032_ANCHOR["h3"]
    p2_dimension = nedelec_hex_local_dimension(2)
    degree_dimension = nedelec_hex_local_dimension(degree)
    degree_dimension_ratio = degree_dimension / p2_dimension

    row_h_exponent = _power_exponent(
        float(h5["local_fe_rows"]), float(h3["local_fe_rows"])
    )
    nnz_h_exponent = _power_exponent(
        float(h5["assembled_nnz"]), float(h3["assembled_nnz"])
    )
    local_fe_rows = _ceil_stable(
        float(h3["local_fe_rows"])
        * (3.0 / h_nm) ** row_h_exponent
        * degree_dimension_ratio
    )
    # Element tensors couple local high-order basis functions densely. Squared
    # cell-dimension scaling is conservative for pre-run NNZ inventory and is
    # not presented as a measured sparsity law.
    assembled_nnz = _ceil_stable(
        float(h3["assembled_nnz"])
        * (3.0 / h_nm) ** nnz_h_exponent
        * degree_dimension_ratio**2
    )
    # Reproduce the two fitted p2 calibration coordinates exactly. In
    # particular, this avoids the old p2/h5 2,000,624 -> 2,000,625 ceil drift.
    if degree == 2 and h_nm == 5.0:
        local_fe_rows = int(h5["local_fe_rows"])
        assembled_nnz = int(h5["assembled_nnz"])
    elif degree == 2 and h_nm == 3.0:
        local_fe_rows = int(h3["local_fe_rows"])
        assembled_nnz = int(h3["assembled_nnz"])

    external_auxiliary_rows = 80
    internal_modal_amplitudes = 2 * int(TASK032_ANCHOR["modes_per_direction"])
    total_rows = local_fe_rows + external_auxiliary_rows + internal_modal_amplitudes

    # Center A is an RSS power law in effective p/h resolution.
    effective_resolution_ratio = (degree / 2.0) * (3.0 / h_nm)
    rss_h_exponent = _power_exponent(
        float(h5["simultaneous_worker_rss_gib"]),
        float(h3["simultaneous_worker_rss_gib"]),
    )
    resolution_center = float(h3["simultaneous_worker_rss_gib"]) * (
        effective_resolution_ratio**rss_h_exponent
    )
    factor_prediction = _factor_projection(assembled_nnz)

    higher_center = max(resolution_center, float(factor_prediction["center_gib"]))
    conservative_upper = higher_center + max(0.10, 0.15 * higher_center)
    return {
        "degree": degree,
        "h_nm": h_nm,
        "modes_per_direction": int(TASK032_ANCHOR["modes_per_direction"]),
        "internal_modal_amplitudes_2m": internal_modal_amplitudes,
        "projected_local_fe_rows": local_fe_rows,
        "projected_external_auxiliary_rows": external_auxiliary_rows,
        "projected_total_rows": total_rows,
        "projected_assembled_nnz": assembled_nnz,
        "degree_cell_dimension": degree_dimension,
        "degree_cell_dimension_ratio_from_p2": degree_dimension_ratio,
        "predictions": {
            "effective_resolution_rss_power_law": {
                "center_gib": resolution_center,
                "observed_h_exponent": rss_h_exponent,
                "independent_variable": "effective p/h resolution",
                "data_identity": "predicted_from_measured_task032_rss",
            },
            "factor_nnz_fill_payload_affine": factor_prediction,
        },
        "conservative_upper_gib": conservative_upper,
        "data_identity": {
            "projected_rows_nnz": "predicted",
            "predicted_memory_centers": "predicted",
            "task032_calibration_inputs": "measured",
            "pde_execution": "not_run",
            "solver_result": "not_run",
        },
    }


def build_reduced_equal_accuracy_resource_matrix(
    *,
    container_limit_gib: float | None = None,
) -> dict[str, Any]:
    """Build the review-v5 p3/h10 then conditional p3/h7.5 planning matrix.

    This record is deliberately separate from the immutable original 20-case
    planning matrix. It predicts only the two candidates authorized by review
    v5, leaves runtime attestations unresolved, and never launches a PDE.
    """

    limits = scaled_gate_limits(container_limit_gib)
    entries: list[dict[str, Any]] = []
    for index, h_nm in enumerate(REDUCED_EQUAL_ACCURACY_LEVELS_NM):
        projection = project_resources(3, h_nm)
        centers = [
            float(item["center_gib"])
            for item in projection["predictions"].values()
        ]
        two_centers_pass = all(
            value <= limits["two_center_limit_gib"] for value in centers
        )
        upper_pass = bool(
            float(projection["conservative_upper_gib"])
            <= limits["conservative_upper_limit_gib"]
        )
        prediction_gate_pass = two_centers_pass and upper_pass
        key = matrix_key(3, h_nm)
        predecessor = None if index == 0 else matrix_key(3, 10.0)
        entries.append(
            {
                "matrix_key": key,
                "policy_class": "required" if index == 0 else "conditional",
                "task_matrix_label": (
                    "review_v5_required_candidate"
                    if index == 0
                    else "run_only_if_p3_h10_not_equal_accuracy"
                ),
                "conditional_predecessor": predecessor,
                "conditional_predecessor_clean": index == 0,
                "locked_override_present": False,
                "two_center_gate_pass": two_centers_pass,
                "conservative_upper_gate_pass": upper_pass,
                "prediction_gate_pass": prediction_gate_pass,
                "policy_gate_pass": True,
                "planning_eligible": prediction_gate_pass,
                "planning_decision": (
                    "planning_eligible_by_resource_prediction"
                    if prediction_gate_pass
                    else "not_run_by_memory_gate"
                ),
                "planning_reasons": (
                    []
                    if prediction_gate_pass
                    else [
                        *(
                            []
                            if two_centers_pass
                            else [
                                "one_or_both_center_predictions_exceed_limit"
                            ]
                        ),
                        *(
                            []
                            if upper_pass
                            else ["conservative_upper_exceeds_limit"]
                        ),
                    ]
                ),
                "qualification_state": "review_v5_p3_component_accepted",
                "qualification_gate_pass": True,
                "launch_eligible": False,
                "launch_decision": (
                    "not_launch_eligible_runtime_contract"
                    if prediction_gate_pass
                    else "not_run_by_memory_gate"
                ),
                "launch_reasons": (
                    [
                        "source_clean_unknown",
                        "swap_state_unknown",
                        "watchdog_state_unknown",
                        "one_large_case_contract_unknown",
                    ]
                    if prediction_gate_pass
                    else ["prediction_gate_failed"]
                ),
                "execution_identity": "prediction_only_no_pde_run",
                **projection,
            }
        )

    return {
        "schema_version": 2,
        "benchmark_id": "task033_case091_resource_matrix",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "task_id": "Task033",
        "record_type": "task033_resource_prediction_and_launch_decision",
        "status": "review_v5_reduced_equal_accuracy_planning_complete",
        "data_identity": (
            "prediction_with_measured_task032_calibration_reduced_review_v5"
        ),
        "identity": {
            "deterministic": True,
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_memory_measurement": False,
            "is_adaptive_compression_measurement": False,
            "ordinary_default_changed": False,
            "runtime_preflight_performed": False,
            "proves_0p7nm_feasible": False,
            "scope": "Task033 review-v5 p3 coarse equal-accuracy planning only",
        },
        "physical_model": {
            "wavelength_nm": 13.5,
            "solver_path": "modal-schur-memory-minimal",
            "modes_per_direction": int(
                TASK032_ANCHOR["modes_per_direction"]
            ),
        },
        "resolved_config": {
            "degrees": [3],
            "mesh_levels_nm": list(REDUCED_EQUAL_ACCURACY_LEVELS_NM),
            "execution_order": ["p3_h10", "p3_h7p5_if_needed"],
            "p3_h7p5_stop_gate": (
                "do_not_run_if_p3_h10_matches_or_beats_p2_h3_accuracy"
            ),
        },
        "solver_path": "modal-schur-memory-minimal",
        "gate_limits": limits,
        "runtime_launch_contract": {
            "source_clean": None,
            "swap_activity_detected": None,
            "watchdog_enabled": None,
            "one_large_case_at_a_time": None,
            "runtime_contract_verified": False,
            "contract_failures": [
                "source_clean_unknown",
                "swap_state_unknown",
                "watchdog_state_unknown",
                "one_large_case_contract_unknown",
            ],
        },
        "task032_measured_calibration": TASK032_ANCHOR,
        "entries": entries,
        "matrix_shape": {
            "degrees": 1,
            "mesh_levels": 2,
            "entries": 2,
        },
        "artifact_provenance": {
            "generator_module": "benchmarks.task033_resource_gates",
            "review_authority": (
                "docs/task033_high_order_floquet_hybrid_hp_adaptivity/"
                "review_report_v5.md"
            ),
        },
    }


def _contract_failures(runtime_contract: Mapping[str, bool | None]) -> list[str]:
    failures = []
    source_clean = runtime_contract["source_clean"]
    if source_clean is None:
        failures.append("tracked_source_clean_unknown")
    elif not source_clean:
        failures.append("tracked_source_not_clean")

    swap_detected = runtime_contract["swap_activity_detected"]
    if swap_detected is None:
        failures.append("swap_activity_state_unknown")
    elif swap_detected:
        failures.append("swap_activity_detected")

    watchdog_enabled = runtime_contract["watchdog_enabled"]
    if watchdog_enabled is None:
        failures.append("watchdog_state_unknown")
    elif not watchdog_enabled:
        failures.append("watchdog_not_enabled")

    one_large = runtime_contract["one_large_case_at_a_time"]
    if one_large is None:
        failures.append("one_large_case_contract_unknown")
    elif not one_large:
        failures.append("one_large_case_contract_not_met")
    return failures


def _count_decisions(entries: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        decision = str(entry[field])
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def build_resource_matrix(
    *,
    container_limit_gib: float | None = None,
    source_clean: bool | None = None,
    swap_activity_detected: bool | None = None,
    watchdog_enabled: bool | None = None,
    one_large_case_at_a_time: bool | None = None,
    qualified_high_order_degrees: Collection[int] = (),
    conditional_clean_records: Collection[str] = (),
    locked_overrides: Collection[str] = (),
) -> dict[str, Any]:
    """Build deterministic Task033 p1--4 by h planning/launch decisions.

    The default is deliberately fail-closed: clean source, no swap, watchdog,
    one-large-case serialization, and p3/p4 qualification are unknown until a
    caller explicitly supplies verified state. Passing this planner never runs
    a PDE; even ``launch_eligible`` only authorizes a later guarded launch.
    """

    limits = scaled_gate_limits(container_limit_gib)
    runtime_contract: dict[str, bool | None] = {
        "source_clean": source_clean,
        "swap_activity_detected": swap_activity_detected,
        "watchdog_enabled": watchdog_enabled,
        "one_large_case_at_a_time": one_large_case_at_a_time,
    }
    runtime_failures = _contract_failures(runtime_contract)
    clean_records = set(conditional_clean_records)
    overrides = set(locked_overrides)
    qualified = {int(degree) for degree in qualified_high_order_degrees}
    if not qualified.issubset({3, 4}):
        raise ValueError("qualified_high_order_degrees may contain only 3 and 4.")

    known_keys = {
        matrix_key(degree, h_nm) for degree in DEGREES for h_nm in MESH_LEVELS_NM
    }
    unknown = (clean_records | overrides) - known_keys
    if unknown:
        raise ValueError(f"Unknown p/h matrix keys: {sorted(unknown)}")

    entries = []
    for degree in DEGREES:
        for h_nm in MESH_LEVELS_NM:
            key = matrix_key(degree, h_nm)
            policy_class, task_label = POLICY_MATRIX[degree][h_nm]
            projection = project_resources(degree, h_nm)
            centers = [
                float(item["center_gib"]) for item in projection["predictions"].values()
            ]
            two_centers_pass = all(
                value <= limits["two_center_limit_gib"] for value in centers
            )
            upper_pass = (
                float(projection["conservative_upper_gib"])
                <= limits["conservative_upper_limit_gib"]
            )
            prediction_gate_pass = two_centers_pass and upper_pass
            predecessor = CONDITIONAL_PREDECESSOR.get(key)
            predecessor_clean = predecessor is None or predecessor in clean_records
            override_present = key in overrides

            planning_reasons = []
            if not two_centers_pass:
                planning_reasons.append("one_or_both_center_predictions_exceed_limit")
            if not upper_pass:
                planning_reasons.append("conservative_upper_exceeds_limit")
            if policy_class == "conditional" and not predecessor_clean:
                planning_reasons.append("conditional_predecessor_clean_record_missing")
            if policy_class == "locked_by_default" and not override_present:
                planning_reasons.append("locked_by_default_without_independent_unlock")

            is_task032_anchor = degree == 2 and h_nm == 3.0
            policy_gate_pass = not (
                (policy_class == "conditional" and not predecessor_clean)
                or (policy_class == "locked_by_default" and not override_present)
            )
            planning_eligible = prediction_gate_pass and policy_gate_pass
            if is_task032_anchor:
                planning_decision = "reuse_task032_clean_anchor"
                planning_reasons = []
            elif planning_eligible:
                planning_decision = "planning_eligible_by_resource_prediction"
            else:
                planning_decision = "not_run_by_memory_gate"

            if degree <= 2:
                qualification_state = "ordinary_degree_not_high_order_gated"
                qualification_gate_pass = True
                qualification_reasons: list[str] = []
            elif degree in qualified:
                qualification_state = "verified_qualified_by_caller"
                qualification_gate_pass = True
                qualification_reasons = []
            else:
                qualification_state = "unknown_fail_closed"
                qualification_gate_pass = False
                qualification_reasons = [f"p{degree}_qualification_unknown"]

            if is_task032_anchor:
                launch_eligible = False
                launch_decision = "reuse_task032_clean_anchor"
                launch_reasons: list[str] = []
            elif not planning_eligible:
                launch_eligible = False
                launch_decision = "not_run_by_memory_gate"
                launch_reasons = list(planning_reasons)
            elif not qualification_gate_pass:
                launch_eligible = False
                launch_decision = "not_run_pending_high_order_qualification"
                launch_reasons = list(qualification_reasons)
            elif runtime_failures:
                launch_eligible = False
                launch_decision = "not_launch_eligible_runtime_contract"
                launch_reasons = list(runtime_failures)
            else:
                launch_eligible = True
                launch_decision = "launch_eligible"
                launch_reasons = []

            entry: dict[str, Any] = {
                "matrix_key": key,
                "policy_class": policy_class,
                "task_matrix_label": task_label,
                "conditional_predecessor": predecessor,
                "conditional_predecessor_clean": predecessor_clean,
                "locked_override_present": override_present,
                "two_center_gate_pass": two_centers_pass,
                "conservative_upper_gate_pass": upper_pass,
                "prediction_gate_pass": prediction_gate_pass,
                "policy_gate_pass": policy_gate_pass,
                "planning_eligible": planning_eligible,
                "planning_decision": planning_decision,
                "planning_reasons": planning_reasons,
                "qualification_state": qualification_state,
                "qualification_gate_pass": qualification_gate_pass,
                "launch_eligible": launch_eligible,
                "launch_decision": launch_decision,
                "launch_reasons": launch_reasons,
                "execution_identity": (
                    "clean_measured_task032_anchor_reused"
                    if is_task032_anchor
                    else "prediction_only_no_pde_run"
                ),
                **projection,
            }
            if is_task032_anchor:
                entry["measured_anchor"] = {
                    **TASK032_ANCHOR["h3"],
                    "degree": 2,
                    "modes_per_direction": int(TASK032_ANCHOR["modes_per_direction"]),
                    "execution_identity": "clean_measured_task032_anchor_reused",
                }
            entries.append(entry)

    return {
        "schema_version": 2,
        "benchmark_id": "task033_case091_resource_matrix",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "task_id": "Task033",
        "record_type": "task033_resource_prediction_and_launch_decision",
        "status": "planning_complete_runtime_launch_fail_closed",
        "data_identity": "prediction_with_measured_task032_calibration_and_anchor",
        "identity": {
            "deterministic": True,
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_memory_measurement": False,
            "is_adaptive_compression_measurement": False,
            "ordinary_default_changed": False,
            "runtime_preflight_performed": False,
            "proves_0p7nm_feasible": False,
            "scope": "Task033 13.5 nm p/h launch planning only",
        },
        "physical_model": {
            "wavelength_nm": 13.5,
            "solver_path": "modal-schur-memory-minimal",
            "modes_per_direction": int(TASK032_ANCHOR["modes_per_direction"]),
        },
        "resolved_config": {
            "degrees": list(DEGREES),
            "mesh_levels_nm": list(MESH_LEVELS_NM),
            "qualified_high_order_degrees": sorted(qualified),
            "conditional_clean_records": sorted(clean_records),
            "locked_overrides": sorted(overrides),
        },
        "solver_path": "modal-schur-memory-minimal",
        "task032_measured_calibration": TASK032_ANCHOR,
        "task032_p2_h3_measured_anchor": {
            **TASK032_ANCHOR["h3"],
            "degree": 2,
            "modes_per_direction": int(TASK032_ANCHOR["modes_per_direction"]),
            "solver_path": str(TASK032_ANCHOR["solver_path"]),
            "source_commit": str(TASK032_ANCHOR["source_commit"]),
        },
        "artifact_provenance": {
            "generator_module": "benchmarks.task033_resource_gates",
            "runner_module": "benchmarks.run_task033_resource_matrix",
            "calibration_source_commit": str(TASK032_ANCHOR["source_commit"]),
            "default_container_limit_evidence": (
                "Task033 Phase-0 Docker Engine MemTotal snapshot"
            ),
        },
        "gate_limits": limits,
        "runtime_launch_contract": {
            **runtime_contract,
            "default_state": "unknown_fail_closed",
            "inputs_are_caller_attestations": True,
            "runtime_measurements_performed": False,
            "runtime_contract_verified": not runtime_failures,
            "swap_allowed": False,
            "memory_authority": (
                "max(simultaneous live MPI worker RSS sum, container cgroup current)"
            ),
            "contract_failures": runtime_failures,
        },
        "matrix_shape": {"degrees": 4, "mesh_levels": 5, "entries": 20},
        "decision_counts": {
            "planning": _count_decisions(entries, "planning_decision"),
            "launch": _count_decisions(entries, "launch_decision"),
        },
        "entries": entries,
        "limitations": [
            "This record plans launches; it does not execute a PDE.",
            "The two centers extrapolate only measured Task032 p2/h5-h3 data.",
            "Predicted rows and NNZ are not assembled Task033 measurements.",
            "Default runtime attestations and p3/p4 qualification are unknown.",
            "Launch eligibility still requires an external guarded runner.",
            "No Task033 result in this record proves 0.7 nm feasibility.",
        ],
    }
