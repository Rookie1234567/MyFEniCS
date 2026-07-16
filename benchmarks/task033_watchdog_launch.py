"""Fail-closed Task033 Hybrid launch authorization for the external watchdog.

The checked Case091 resource matrix is a planning artifact.  This module reads
one matching p/h entry, re-evaluates its two centers and conservative upper
against the *live* memory ceiling, and layers the runtime-only evidence that
the planning record deliberately leaves unknown.  It never launches a PDE.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
from typing import Any

from benchmarks.task033_case090_pde_core import evidence_sha256_is_valid
from benchmarks.task033_resource_gates import matrix_key, scaled_gate_limits


DEFAULT_RESOURCE_MATRIX = (
    Path(__file__).resolve().parent
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "resource_matrix.json"
)
FORMAL_FUNNEL_MODES = (80, 120, 160)
CONDITIONAL_FUNNEL_MODE = 240
_EXPECTED_M160_NONCONVERGENCE_FAILURE = (
    "M120->M160 did not converge and no qualifying M160->M240 result exists"
)

# These ratios/deltas are derived from the two clean Task032 M160 records for
# each path.  Center A is a path-RSS ratio; center B independently adds the
# measured augmented-minus-minimal increment as a function of assembled NNZ.
_AUGMENTED_TO_MINIMAL_RSS_RATIO = max(
    1.8653526306152344 / 1.6977119445800781,
    3.8526077270507812 / 3.224353790283203,
)
_FAST_TO_MINIMAL_RSS_RATIO = max(
    1.7551193237304688 / 1.6977119445800781,
    3.9983062744140625 / 3.224353790283203,
)
_H5_ASSEMBLED_NNZ = 2_000_624
_H3_ASSEMBLED_NNZ = 8_594_673
_H5_AUGMENTED_INCREMENT_GIB = 1.8653526306152344 - 1.6977119445800781
_H3_AUGMENTED_INCREMENT_GIB = 3.8526077270507812 - 3.224353790283203


def _positive_finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def _nonnegative_finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def high_order_core_evidence_gate(
    degree: int,
    evidence: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    current_source_sha: str | None,
) -> dict[str, Any]:
    """Verify real Case090 aggregate evidence for a p3/p4 launch.

    A caller-supplied 64-character string is not evidence.  The aggregate JSON
    must carry a valid canonical payload digest, clean real-PDE identity, the
    complete p3/p4 x MPI1/2/4 coverage, and the same source SHA as the launch.
    """

    if degree < 3:
        return {
            "pass": True,
            "applicable": False,
            "evidence_sha256": None,
            "checks": {},
            "failures": [],
        }

    payload = evidence if isinstance(evidence, Mapping) else {}
    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    coverage = payload.get("coverage")
    coverage = coverage if isinstance(coverage, list) else []
    covered_pairs = {
        (item.get("degree"), item.get("mpi_size"))
        for item in coverage
        if isinstance(item, Mapping)
    }
    required_pairs = {
        (candidate_degree, mpi_size)
        for candidate_degree in (3, 4)
        for mpi_size in (1, 2, 4)
    }
    observed_digest = payload.get("evidence_sha256")
    expected_digest_valid = (
        expected_sha256 is None or _valid_hex(expected_sha256, 64)
    )
    checks = {
        "evidence_object_present": bool(payload),
        "record_type_is_case090_core_gate": (
            payload.get("record_type") == "high_order_floquet_core_gate_result"
        ),
        "canonical_evidence_sha256_valid": evidence_sha256_is_valid(payload),
        "expected_sha256_valid_if_supplied": expected_digest_valid,
        "expected_sha256_matches": bool(
            expected_digest_valid
            and (expected_sha256 is None or observed_digest == expected_sha256)
        ),
        "all_core_gates_passed": payload.get("all_core_gates_passed") is True,
        "real_pde_solver_pass": bool(
            identity.get("is_pde_run") is True
            and identity.get("is_solver_pass") is True
        ),
        "tracked_source_clean": identity.get("tracked_source_dirty") is False,
        "same_full_source_sha": bool(
            _valid_hex(current_source_sha, 40)
            and identity.get("source_commit_full_sha") == current_source_sha
        ),
        "p3_p4_mpi_coverage_complete": required_pairs.issubset(covered_pairs),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "applicable": True,
        "evidence_sha256": observed_digest,
        "checks": checks,
        "failures": failures,
    }


def conditional_m240_evidence_gate(
    evidence: Mapping[str, Any] | None,
    *,
    expected_file_sha256: str | None,
    observed_file_sha256: str | None,
    current_source_sha: str | None,
    degree: int,
    h_nm: float,
    incident_grazing_deg: float,
    polarization_kind: str,
    bottom_interface_nm: float,
    top_interface_nm: float,
    graded_reference_h: float | None,
    solver_path: str,
    required: bool,
) -> dict[str, Any]:
    """Authorize M240 only from a complete, same-case M80/120/160 failure.

    The evidence is the existing Hybrid funnel aggregate.  This consumer does
    not reproduce its convergence algorithm; it verifies that the aggregate
    failed *only* because measured M120->M160 convergence was not reached.
    """

    if not required:
        return {
            "pass": True,
            "applicable": False,
            "evidence_file_sha256": None,
            "checks": {},
            "failures": [],
        }

    payload = evidence if isinstance(evidence, Mapping) else {}
    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    case = payload.get("case")
    case = case if isinstance(case, Mapping) else {}
    qualification = payload.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    individual = payload.get("individual_gates")
    individual = individual if isinstance(individual, Mapping) else {}
    comparisons = payload.get("comparisons")
    comparisons = comparisons if isinstance(comparisons, list) else []
    source_records = payload.get("source_records")
    source_records = source_records if isinstance(source_records, list) else []

    required_individual_flags = (
        "integration_pass",
        "algebraic_chain_pass",
        "physical_field_gates_pass",
        "task033_physical_truncation_allowed",
        "true_relative_residual_le_1e-9",
        "all_reported_gates_pass",
    )

    def individual_pass(value: object) -> bool:
        return bool(
            isinstance(value, Mapping)
            and all(value.get(name) is True for name in required_individual_flags)
            and _positive_finite(value.get("true_relative_residual")) is not None
        )

    pair_keys = {
        (item.get("previous_mode_count"), item.get("current_mode_count"))
        for item in comparisons
        if isinstance(item, Mapping)
    }
    pair_120_160 = next(
        (
            item
            for item in comparisons
            if isinstance(item, Mapping)
            and item.get("previous_mode_count") == 120
            and item.get("current_mode_count") == 160
        ),
        {},
    )
    totals = pair_120_160.get("absolute_total_deltas")
    totals = totals if isinstance(totals, Mapping) else {}
    diffraction = pair_120_160.get("diffraction_orders")
    diffraction = diffraction if isinstance(diffraction, Mapping) else {}
    rows = diffraction.get("rows")
    rows = rows if isinstance(rows, list) else []
    current_gates = pair_120_160.get("current_individual_gates")
    expected_sha_valid = _valid_hex(expected_file_sha256, 64)
    observed_sha_valid = _valid_hex(observed_file_sha256, 64)
    source_descriptors_valid = bool(
        len(source_records) == 3
        and {
            item.get("mode_count_per_direction")
            for item in source_records
            if isinstance(item, Mapping)
        }
        == set(FORMAL_FUNNEL_MODES)
        and all(
            isinstance(item, Mapping)
            and _valid_hex(item.get("sha256"), 64)
            and item.get("source_commit_full_sha") == current_source_sha
            and item.get("data_identity")
            == "measured_external_watchdog_summary"
            for item in source_records
        )
    )
    graded_identity_valid = (
        case.get("graded_reference_h_nm") is None
        and case.get("graded_plan_hash") is None
        if graded_reference_h is None
        else bool(
            _positive_finite(case.get("graded_reference_h_nm")) is not None
            and math.isclose(
                float(case["graded_reference_h_nm"]),
                float(graded_reference_h),
            )
            and isinstance(case.get("graded_plan_hash"), str)
            and bool(case.get("graded_plan_hash"))
        )
    )
    checks = {
        "evidence_object_present": bool(payload),
        "evidence_file_sha256_valid": expected_sha_valid and observed_sha_valid,
        "evidence_file_sha256_matches": bool(
            expected_sha_valid
            and observed_sha_valid
            and expected_file_sha256 == observed_file_sha256
        ),
        "funnel_record_identity": bool(
            payload.get("schema_version")
            == "task033.case091.hybrid-funnel.v1"
            and payload.get("record_type")
            == "task033_hybrid_mode_truncation_funnel"
            and payload.get("case_id")
            == "091_hybrid_hp_adaptivity_feasibility"
            and payload.get("status") == "not_qualified"
        ),
        "same_clean_source_identity": bool(
            _valid_hex(current_source_sha, 40)
            and identity.get("source_commit_full_sha") == current_source_sha
            and identity.get("tracked_source_clean") is True
            and identity.get("is_pde_run") is True
            and identity.get("is_solver_pass") is False
            and identity.get("is_mode_convergence_measurement") is True
        ),
        "same_physical_case": bool(
            case.get("degree") == degree
            and _positive_finite(case.get("h_nm")) is not None
            and math.isclose(float(case["h_nm"]), float(h_nm))
            and _positive_finite(case.get("wavelength_nm")) is not None
            and math.isclose(float(case["wavelength_nm"]), 13.5)
            and _positive_finite(case.get("incident_grazing_deg")) is not None
            and math.isclose(
                float(case["incident_grazing_deg"]),
                float(incident_grazing_deg),
            )
            and case.get("polarization_kind") == polarization_kind
            and _positive_finite(case.get("bottom_interface_nm")) is not None
            and math.isclose(
                float(case["bottom_interface_nm"]),
                float(bottom_interface_nm),
            )
            and _positive_finite(case.get("top_interface_nm")) is not None
            and math.isclose(
                float(case["top_interface_nm"]), float(top_interface_nm)
            )
            and graded_identity_valid
            and case.get("primary_solver_path") == solver_path
        ),
        "exact_executed_m80_m120_m160_funnel": (
            case.get("mode_counts") == list(FORMAL_FUNNEL_MODES)
        ),
        "all_three_individual_gates_pass": bool(
            set(individual) == {str(value) for value in FORMAL_FUNNEL_MODES}
            and all(
                individual_pass(individual.get(str(value)))
                for value in FORMAL_FUNNEL_MODES
            )
        ),
        "complete_pair_coverage": pair_keys == {(80, 120), (120, 160)},
        "m120_m160_comparison_evidence_complete": bool(
            all(_nonnegative_finite(totals.get(name)) is not None for name in (
                "R_total",
                "T_total",
                "A_balance",
            ))
            and _nonnegative_finite(
                pair_120_160.get("max_absolute_total_delta")
            )
            is not None
            and diffraction.get("available") is True
            and diffraction.get("coverage_equal") is True
            and rows
            and all(
                isinstance(row, Mapping) and row.get("complete") is True
                for row in rows
            )
            and individual_pass(current_gates)
        ),
        "m120_m160_measured_nonconvergence": (
            pair_120_160.get("mandatory_convergence_pass") is False
        ),
        "aggregate_failed_only_for_m160_nonconvergence": bool(
            payload.get("failures") == [_EXPECTED_M160_NONCONVERGENCE_FAILURE]
            and qualification.get("mode_count_converged") is False
            and qualification.get("selected_mode_count_per_direction") is None
            and qualification.get("all_sources_same_clean_sha") is True
            and qualification.get("all_external_watchdogs_pass") is True
        ),
        "three_bound_source_records": source_descriptors_valid,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "applicable": True,
        "evidence_file_sha256": observed_file_sha256,
        "checks": checks,
        "failures": failures,
    }


def _entry_centers(entry: Mapping[str, Any]) -> dict[str, float] | None:
    predictions = entry.get("predictions")
    if not isinstance(predictions, Mapping) or len(predictions) != 2:
        return None
    centers: dict[str, float] = {}
    for name, prediction in predictions.items():
        if not isinstance(prediction, Mapping):
            return None
        center = _positive_finite(prediction.get("center_gib"))
        if center is None:
            return None
        centers[str(name)] = center
    return centers


def _augmented_increment_gib(assembled_nnz: int) -> float:
    slope = (
        _H3_AUGMENTED_INCREMENT_GIB - _H5_AUGMENTED_INCREMENT_GIB
    ) / (_H3_ASSEMBLED_NNZ - _H5_ASSEMBLED_NNZ)
    intercept = _H5_AUGMENTED_INCREMENT_GIB - slope * _H5_ASSEMBLED_NNZ
    return max(_H5_AUGMENTED_INCREMENT_GIB, intercept + slope * assembled_nnz)


def independent_variant_prediction(
    entry: Mapping[str, Any],
    *,
    solver_path: str,
    compare_modal_schur: bool,
    bottom_interface_nm: float,
    top_interface_nm: float,
    graded_reference_h: float | None,
    incident_grazing_deg: float = 10.0,
    polarization_kind: str = "s",
    requested_modes: int = 160,
) -> dict[str, Any]:
    """Build separate two-center predictions for uncalibrated Hybrid variants.

    The checked uniform matrix is calibrated to Modal-Schur-memory-minimal at
    10/110 nm.  Augmented, fast-Schur, graded, and altered-buffer launches are
    therefore not allowed to inherit that prediction silently.
    """

    centers = _entry_centers(entry)
    if centers is None:
        return {
            "pass": False,
            "required": True,
            "failures": ["resource_matrix_two_centers_missing_or_invalid"],
        }
    ordered = list(centers.values())
    resolution_center = ordered[0]
    factor_center = ordered[1]
    # Prefer the named identities, but retain fail-closed numeric operation if
    # JSON object ordering is normalized by another writer.
    resolution_center = centers.get(
        "effective_resolution_rss_power_law", resolution_center
    )
    factor_center = centers.get("factor_nnz_fill_payload_affine", factor_center)
    assembled_nnz = entry.get("projected_assembled_nnz")
    try:
        assembled_nnz = int(assembled_nnz)
    except (TypeError, ValueError):
        assembled_nnz = 0

    if solver_path == "augmented":
        independent_centers = {
            "measured_path_ratio_center_gib": (
                resolution_center * _AUGMENTED_TO_MINIMAL_RSS_RATIO
            ),
            "assembled_nnz_increment_center_gib": (
                factor_center + _augmented_increment_gib(assembled_nnz)
            ),
        }
        prediction_identity = "task032_augmented_anchor_independent_two_center"
    elif solver_path == "modal-schur-fast":
        independent_centers = {
            "measured_path_ratio_center_gib": (
                resolution_center * _FAST_TO_MINIMAL_RSS_RATIO
            ),
            "factor_workspace_margin_center_gib": factor_center * 1.25,
        }
        prediction_identity = "task032_fast_schur_independent_two_center"
    else:
        independent_centers = {
            "uniform_center_a_with_variant_margin_gib": resolution_center,
            "uniform_center_b_with_variant_margin_gib": factor_center,
        }
        prediction_identity = "uncalibrated_geometry_variant_two_center"

    default_buffer_total_nm = 20.0
    candidate_buffer_total_nm = max(
        0.0, float(bottom_interface_nm)
    ) + max(0.0, 120.0 - float(top_interface_nm))
    buffer_volume_factor = max(1.0, candidate_buffer_total_nm / default_buffer_total_nm)
    uncalibrated_geometry = bool(
        graded_reference_h is not None
        or not math.isclose(float(bottom_interface_nm), 10.0)
        or not math.isclose(float(top_interface_nm), 110.0)
    )
    geometry_contingency = 1.25 if uncalibrated_geometry else 1.0
    physics_variant = bool(
        not math.isclose(float(incident_grazing_deg), 10.0)
        or polarization_kind != "s"
    )
    physics_contingency = 1.25 if physics_variant else 1.0
    # The checked planning matrix is an M160 ceiling.  A conditional M240
    # recovery launch receives a quadratic modal-workspace contingency and is
    # then re-evaluated against the live scaled limits.
    mode_workspace_contingency = max(
        1.0, (float(requested_modes) / 160.0) ** 2
    )
    comparison_contingency = 1.35 if compare_modal_schur else 1.0
    total_multiplier = (
        buffer_volume_factor
        * geometry_contingency
        * physics_contingency
        * mode_workspace_contingency
        * comparison_contingency
    )
    independent_centers = {
        name: value * total_multiplier
        for name, value in independent_centers.items()
    }
    higher = max(independent_centers.values())
    upper = higher + max(0.25, 0.20 * higher)
    return {
        "pass": True,
        "required": True,
        "prediction_identity": prediction_identity,
        "centers_gib": independent_centers,
        "conservative_upper_gib": upper,
        "projected_assembled_nnz": assembled_nnz,
        "buffer_volume_factor_no_discount": buffer_volume_factor,
        "uncalibrated_geometry_contingency": geometry_contingency,
        "uncalibrated_incidence_polarization_contingency": (
            physics_contingency
        ),
        "conditional_mode_workspace_contingency": mode_workspace_contingency,
        "comparison_workspace_contingency": comparison_contingency,
        "limitations": [
            "Prediction authorizes only a guarded launch, not a physical result.",
            "Graded meshes and thinner buffers receive no memory discount.",
            "Nondefault incidence/polarization and M240 receive explicit contingencies.",
            "The live watchdog remains the final memory authority.",
        ],
        "failures": [],
    }


def hybrid_launch_gate(
    resource_matrix: Mapping[str, Any] | None,
    *,
    degree: int,
    h_nm: float,
    requested_modes: int,
    candidate_modes: int,
    solver_path: str,
    compare_modal_schur: bool,
    bottom_interface_nm: float,
    top_interface_nm: float,
    graded_reference_h: float | None,
    container_limit_bytes: int | None,
    host_available_memory_bytes: int | None,
    warning_gib: float,
    terminate_gib: float,
    core_evidence: Mapping[str, Any] | None,
    expected_core_sha256: str | None,
    current_source_sha: str | None,
    incident_grazing_deg: float = 10.0,
    polarization_kind: str = "s",
    comparison_solver_path: str = "fast",
    m160_funnel_evidence: Mapping[str, Any] | None = None,
    expected_m160_funnel_sha256: str | None = None,
    observed_m160_funnel_sha256: str | None = None,
    task033_same_sha_anchor_requalification: bool = False,
    source_clean_verified: bool = False,
    resource_matrix_is_canonical: bool = False,
    resource_matrix_is_tracked: bool = False,
    external_watchdog_active: bool = False,
) -> dict[str, Any]:
    """Return a complete pre-launch authorization record for one Hybrid shard."""

    matrix = resource_matrix if isinstance(resource_matrix, Mapping) else {}
    entries = matrix.get("entries")
    entries = entries if isinstance(entries, list) else []
    key = matrix_key(degree, float(h_nm))
    matches = [
        entry
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("matrix_key") == key
    ]
    entry = matches[0] if len(matches) == 1 else {}
    centers = _entry_centers(entry)
    upper = _positive_finite(entry.get("conservative_upper_gib"))
    container_gib = (
        None
        if container_limit_bytes is None
        else _positive_finite(container_limit_bytes / 1024**3)
    )
    host_available_gib = (
        None
        if host_available_memory_bytes is None
        else _positive_finite(host_available_memory_bytes / 1024**3)
    )
    effective_live_ceiling = (
        None
        if container_gib is None or host_available_gib is None
        else min(container_gib, host_available_gib)
    )
    limits = (
        None
        if effective_live_ceiling is None
        else scaled_gate_limits(effective_live_ceiling)
    )
    core_gate = high_order_core_evidence_gate(
        degree,
        core_evidence,
        expected_sha256=expected_core_sha256,
        current_source_sha=current_source_sha,
    )
    m240_requested = requested_modes == CONDITIONAL_FUNNEL_MODE
    m240_gate = conditional_m240_evidence_gate(
        m160_funnel_evidence,
        expected_file_sha256=expected_m160_funnel_sha256,
        observed_file_sha256=observed_m160_funnel_sha256,
        current_source_sha=current_source_sha,
        degree=degree,
        h_nm=h_nm,
        incident_grazing_deg=incident_grazing_deg,
        polarization_kind=polarization_kind,
        bottom_interface_nm=bottom_interface_nm,
        top_interface_nm=top_interface_nm,
        graded_reference_h=graded_reference_h,
        solver_path=solver_path,
        required=m240_requested,
    )
    geometry_variant = bool(
        graded_reference_h is not None
        or not math.isclose(float(bottom_interface_nm), 10.0)
        or not math.isclose(float(top_interface_nm), 110.0)
    )
    physics_variant = bool(
        not math.isclose(float(incident_grazing_deg), 10.0)
        or polarization_kind != "s"
    )
    independent_required = bool(
        solver_path != "modal-schur-memory-minimal"
        or compare_modal_schur
        or geometry_variant
        or physics_variant
        or m240_requested
    )
    independent = (
        independent_variant_prediction(
            entry,
            solver_path=solver_path,
            compare_modal_schur=compare_modal_schur,
            bottom_interface_nm=bottom_interface_nm,
            top_interface_nm=top_interface_nm,
            graded_reference_h=graded_reference_h,
            incident_grazing_deg=incident_grazing_deg,
            polarization_kind=polarization_kind,
            requested_modes=requested_modes,
        )
        if independent_required and entry
        else {
            "pass": True,
            "required": False,
            "prediction_identity": "uniform_resource_matrix_prediction",
            "centers_gib": centers,
            "conservative_upper_gib": upper,
            "failures": [],
        }
    )
    uniform_centers_live_pass = bool(
        centers
        and limits
        and all(
            value <= float(limits["two_center_limit_gib"])
            for value in centers.values()
        )
    )
    uniform_upper_live_pass = bool(
        upper is not None
        and limits
        and upper <= float(limits["conservative_upper_limit_gib"])
    )
    independent_centers = independent.get("centers_gib")
    independent_upper = _positive_finite(independent.get("conservative_upper_gib"))
    independent_centers_live_pass = bool(
        isinstance(independent_centers, Mapping)
        and independent_centers
        and limits
        and all(
            _positive_finite(value) is not None
            and float(value) <= float(limits["two_center_limit_gib"])
            for value in independent_centers.values()
        )
    )
    independent_upper_live_pass = bool(
        independent_upper is not None
        and limits
        and independent_upper <= float(limits["conservative_upper_limit_gib"])
    )
    anchor_reuse = entry.get("planning_decision") == "reuse_task032_clean_anchor"
    variant_can_replace_anchor = bool(anchor_reuse and independent_required)
    requalification_requested = bool(task033_same_sha_anchor_requalification)
    candidate_pool_is_twice_requested_modes = bool(
        type(requested_modes) is int
        and type(candidate_modes) is int
        and requested_modes > 0
        and candidate_modes == 2 * requested_modes
    )
    canonical_anchor_case_identity = (
        "p2_h3_10_110_primary_modal_schur_memory_minimal"
    )
    requalification_checks = {
        "explicit_task033_requalification_flag": requalification_requested,
        "task032_reuse_anchor_is_the_selected_entry": anchor_reuse,
        "exact_p2_h3_anchor": bool(
            degree == 2 and math.isclose(float(h_nm), 3.0)
        ),
        "primary_uniform_10_110_minimal_path": bool(
            solver_path == "modal-schur-memory-minimal"
            and not compare_modal_schur
            and graded_reference_h is None
            and math.isclose(float(bottom_interface_nm), 10.0)
            and math.isclose(float(top_interface_nm), 110.0)
            and math.isclose(float(incident_grazing_deg), 10.0)
            and polarization_kind == "s"
        ),
        "current_full_source_sha_valid": _valid_hex(current_source_sha, 40),
        "complete_nonignored_worktree_clean": bool(source_clean_verified),
        "canonical_resource_matrix": bool(resource_matrix_is_canonical),
        "canonical_resource_matrix_tracked": bool(resource_matrix_is_tracked),
        "external_watchdog_is_launch_authority": bool(external_watchdog_active),
        "one_required_funnel_mode_selected": requested_modes in FORMAL_FUNNEL_MODES,
        "candidate_pool_is_twice_requested_modes": (
            candidate_pool_is_twice_requested_modes
        ),
    }
    requalification_allowed = bool(
        requalification_requested and all(requalification_checks.values())
    )
    requalification = {
        "requested": requalification_requested,
        "allowed": requalification_allowed,
        "reason": (
            "Task033 same-SHA formal requalification"
            if requalification_allowed
            else None
        ),
        "case_identity": canonical_anchor_case_identity,
        "source_commit_full_sha": current_source_sha,
        "current_requested_mode": requested_modes,
        "required_complete_mode_funnel": list(FORMAL_FUNNEL_MODES),
        "requires_same_case_and_source_sha_across_funnel": True,
        "does_not_replace_task032_anchor": True,
        "checks": requalification_checks,
        "failures": [
            name for name, passed in requalification_checks.items() if not passed
        ]
        if requalification_requested
        else [],
    }
    stored_launch_resolvable = bool(
        entry.get("launch_eligible") is True
        or entry.get("launch_decision")
        in {
            "not_launch_eligible_runtime_contract",
            "not_run_pending_high_order_qualification",
            "reuse_task032_clean_anchor",
        }
    )
    checks = {
        "resource_matrix_object_present": bool(matrix),
        "resource_matrix_identity_valid": bool(
            matrix.get("schema_version") == 2
            and matrix.get("benchmark_id") == "task033_case091_resource_matrix"
            and matrix.get("record_type")
            == "task033_resource_prediction_and_launch_decision"
            and matrix.get("solver_path") == "modal-schur-memory-minimal"
        ),
        "exactly_one_matching_p_h_entry": len(matches) == 1,
        "stored_two_center_gate_pass": entry.get("two_center_gate_pass") is True,
        "stored_conservative_upper_gate_pass": (
            entry.get("conservative_upper_gate_pass") is True
        ),
        "stored_prediction_gate_pass": entry.get("prediction_gate_pass") is True,
        "stored_policy_gate_pass": entry.get("policy_gate_pass") is True,
        "stored_planning_eligible": entry.get("planning_eligible") is True,
        "stored_launch_decision_is_runtime_resolvable": stored_launch_resolvable,
        "existing_uniform_anchor_not_relaunched_without_variant": (
            not anchor_reuse
            or variant_can_replace_anchor
            or requalification_allowed
        ),
        "task033_anchor_requalification_request_is_scoped": (
            not requalification_requested or requalification_allowed
        ),
        "live_container_and_host_ceiling_readable": limits is not None,
        "incident_angle_supported": bool(
            math.isfinite(float(incident_grazing_deg))
            and 0.0 < float(incident_grazing_deg) < 90.0
        ),
        "polarization_supported": polarization_kind in {"s", "p"},
        "comparison_solver_path_supported": (
            comparison_solver_path in {"fast", "minimal"}
        ),
        "task033_augmented_comparison_uses_memory_minimal": bool(
            not compare_modal_schur
            or (
                solver_path == "augmented"
                and comparison_solver_path == "minimal"
            )
        ),
        "uniform_two_centers_within_live_scaled_limit": uniform_centers_live_pass,
        "uniform_upper_within_live_scaled_limit": uniform_upper_live_pass,
        "formal_funnel_mode_count": bool(
            requested_modes in FORMAL_FUNNEL_MODES
            or (m240_requested and m240_gate["pass"])
        ),
        "conditional_m240_prior_nonconvergence_evidence": m240_gate["pass"],
        "candidate_pool_is_twice_requested_modes": (
            candidate_pool_is_twice_requested_modes
        ),
        "warning_threshold_not_wider_than_scaled_gate": bool(
            limits and warning_gib <= float(limits["warning_gib"])
        ),
        "termination_threshold_not_wider_than_scaled_gate": bool(
            limits and terminate_gib <= float(limits["controlled_termination_gib"])
        ),
        "high_order_core_evidence": core_gate["pass"],
        "independent_prediction_constructed": independent.get("pass") is True,
        "independent_two_centers_within_live_scaled_limit": (
            independent_centers_live_pass
        ),
        "independent_upper_within_live_scaled_limit": independent_upper_live_pass,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "launch_eligible_recomputed": not failures,
        "matrix_key": key,
        "resource_matrix_stored_launch_eligible": entry.get("launch_eligible"),
        "resource_matrix_stored_launch_decision": entry.get("launch_decision"),
        "resource_matrix_stored_launch_reasons": entry.get("launch_reasons"),
        "live_scaled_limits": limits,
        "uniform_prediction": {
            "centers_gib": centers,
            "conservative_upper_gib": upper,
        },
        "independent_prediction": independent,
        "conditional_m240_evidence": m240_gate,
        "physical_case": {
            "incident_grazing_deg": float(incident_grazing_deg),
            "polarization_kind": polarization_kind,
            "comparison_solver_path": comparison_solver_path,
        },
        "high_order_core_evidence": core_gate,
        "task033_anchor_requalification": requalification,
        "checks": checks,
        "failures": failures,
        "semantics": (
            "The Case091 planning entry is re-evaluated with the live container/"
            "host ceiling. Runtime attestations may resolve its documented unknowns;"
            " memory/policy vetoes may not be overridden by CLI input."
        ),
    }
