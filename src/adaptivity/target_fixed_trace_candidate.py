"""Formal Task035b fixed-trace / enriched-interior candidate execution."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

from .high_order_same_error import (
    compare_cross_mesh_fields,
    compare_diffraction_channels,
    compare_observables,
    compare_significant_channels_to_reference_v1,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _control_run_dir(record: dict[str, Any]) -> Path:
    path = Path(record["raw_evidence"]["run_directory"])
    return path if path.is_absolute() else _REPO_ROOT / path


def _load_control_summary(
    compact: dict[str, Any],
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = json.loads(path.read_text(encoding="utf-8"))
    for key in ("R00_total", "R_total", "T_total"):
        if key not in summary:
            raise ValueError(f"raw p-control summary is missing {key}")
        if key in compact and not math.isclose(
            float(compact[key]),
            float(summary[key]),
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ):
            raise ValueError(
                f"compact and raw p-control summaries disagree for {key}"
            )
    return summary, {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
    }


def _load_global_p6_baseline(
    path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    if _sha256(path) != str(expected_sha256):
        raise ValueError("Task035b h15 global-p6 baseline SHA256 mismatch")
    baseline = json.loads(path.read_text(encoding="utf-8"))
    enriched = baseline.get("enriched") or {}
    if (
        baseline.get("status") != "actual_global_r5_pass"
        or (baseline.get("qualification") or {}).get("pass") is not True
        or enriched.get("degree") != 6
        or abs(float(enriched.get("h_nm", -1.0)) - 15.0) > 1.0e-12
        or enriched.get("mesh_cell_type_actual") != "hexahedron"
        or enriched.get("num_mesh_cells") != 120
    ):
        raise ValueError("Task035b h15 global-p6 baseline is not qualified")
    mesh_identity = (
        (enriched.get("high_order_resource_audit") or {}).get("mesh_identity")
        or {}
    )
    if not all(
        mesh_identity.get(key)
        for key in (
            "partition_independent_mesh_sha256",
            "cell_tag_sha256",
            "facet_tag_sha256",
        )
    ):
        raise ValueError("Task035b h15 global-p6 mesh identity is incomplete")
    return baseline


def _load_significant_channel_reference(
    path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    if _sha256(path) != str(expected_sha256).lower():
        raise ValueError(
            "Task035b significant-channel reference v1 SHA256 mismatch"
        )
    reference = json.loads(path.read_text(encoding="utf-8"))
    selection = reference.get("significant_channel_selection") or {}
    convergence = reference.get("reference_convergence_summary") or {}
    if (
        reference.get("schema_version")
        != "task035b.significant-channel-reference.v1"
        or reference.get("status")
        != "significant_channel_reference_v1_frozen"
        or reference.get("pass") is not True
        or reference.get("mechanical_validation_pass") is not True
        or selection.get("channel_count") != 12
        or selection.get("expected_and_observed_identity_match") is not True
        or convergence.get("all_12_channels_converged") is not True
    ):
        raise ValueError(
            "Task035b significant-channel reference v1 is not qualified"
        )
    return reference


def _load_directional_parent(
    path: Path,
    expected_sha256: str,
    *,
    significant_reference_sha256: str,
) -> dict[str, Any]:
    if _sha256(path) != str(expected_sha256).lower():
        raise ValueError("Task035b h14 directional parent SHA256 mismatch")
    parent = json.loads(path.read_text(encoding="utf-8"))
    candidate = parent.get("candidate") or {}
    reference = (
        parent.get("significant_channel_reference_authority") or {}
    )
    signal = parent.get("directional_recovery_signal") or {}
    if (
        parent.get("schema_version")
        != "task035b.fixed-trace-watchdog.v1"
        or (parent.get("qualification") or {}).get("pass") is not True
        or parent.get("status")
        not in {
            "actual_fixed_trace_candidate_pass",
            "actual_fixed_trace_controlled_negative",
        }
        or abs(float(candidate.get("h_nm", -1.0)) - 14.0) > 1.0e-12
        or candidate.get("num_nedelec_dofs") != 82315
        or reference.get("sha256")
        != str(significant_reference_sha256).lower()
        or signal.get("positive_signal") is not True
        or signal.get("thresholds_relaxed") is not False
        or (parent.get("source") or {}).get("stable_and_clean_after")
        is not True
    ):
        raise ValueError(
            "Task035b h13 escalation requires a qualified positive h14 "
            "directional parent"
        )
    return parent


def _same_mesh_identity(
    candidate_audit: dict[str, Any],
    baseline_entry: dict[str, Any],
) -> dict[str, Any]:
    candidate = candidate_audit.get("mesh_identity") or {}
    baseline = (
        (baseline_entry.get("high_order_resource_audit") or {}).get(
            "mesh_identity"
        )
        or {}
    )
    keys = (
        "partition_independent_mesh_sha256",
        "cell_tag_sha256",
        "facet_tag_sha256",
    )
    checks = {
        key: bool(candidate.get(key) and candidate.get(key) == baseline.get(key))
        for key in keys
    }
    return {
        "schema_version": "task035b.fixed-trace-same-mesh-baseline.v1",
        "pass": all(checks.values()),
        "checks": checks,
        "candidate": {key: candidate.get(key) for key in keys},
        "global_p6_baseline": {key: baseline.get(key) for key in keys},
    }


def _positive_ratio(reference: Any, candidate: Any) -> float | None:
    if not isinstance(reference, (int, float)):
        return None
    if not isinstance(candidate, (int, float)) or float(candidate) <= 0.0:
        return None
    return float(reference) / float(candidate)


def _same_mesh_resource_comparison(
    summary: dict[str, Any],
    baseline_entry: dict[str, Any],
) -> dict[str, Any]:
    candidate_matrix = summary.get("matrix_stats") or {}
    baseline_matrix = baseline_entry.get("matrix_stats") or {}
    candidate_factor = (
        (summary.get("stage4_dtn_factor_inventory") or {}).get("matrix_stats")
        or {}
    )
    baseline_factor = (
        (baseline_entry.get("stage4_dtn_factor_inventory") or {}).get(
            "matrix_stats"
        )
        or {}
    )
    metrics = {
        "full3d_equivalent_dofs": (
            baseline_entry.get("num_nedelec_dofs"),
            summary.get("num_nedelec_dofs"),
        ),
        "active_rows": (
            baseline_matrix.get("matrix_rows"),
            candidate_matrix.get("matrix_rows"),
        ),
        "matrix_nnz": (
            baseline_matrix.get("matrix_nnz_used"),
            candidate_matrix.get("matrix_nnz_used"),
        ),
        "factor_nnz": (
            baseline_factor.get("matrix_nnz_used"),
            candidate_factor.get("matrix_nnz_used"),
        ),
    }
    return {
        "schema_version": "task035b.fixed-trace-resource-comparison.v1",
        "reference": "same-mesh h15 global p6",
        "metrics": {
            name: {
                "global_p6": reference,
                "candidate": candidate,
                "compression_ratio": _positive_ratio(reference, candidate),
            }
            for name, (reference, candidate) in metrics.items()
        },
    }


def _derived_standard_global_dofs(
    resource_audit: dict[str, Any],
    *,
    degree: int,
) -> int:
    """Count the same-topology standard tensor N1curl space exactly."""

    import basix.ufl

    inventory = resource_audit.get("entity_dof_inventory") or {}
    counts = inventory.get("global_entity_counts") or {}
    element = basix.ufl.element(
        "N1curl",
        "hexahedron",
        int(degree),
    ).basix_element
    edge_modes = len(element.entity_dofs[1][0])
    face_modes = len(element.entity_dofs[2][0])
    cell_modes = len(element.entity_dofs[3][0])
    if not all(
        isinstance(counts.get(name), int)
        for name in ("edges", "faces", "cells")
    ):
        raise RuntimeError("candidate entity inventory is incomplete")
    return int(
        counts["edges"] * edge_modes
        + counts["faces"] * face_modes
        + counts["cells"] * cell_modes
    )


def _compact_element_audit(audit: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version",
        "status",
        "pass",
        "cell_type",
        "trace_degree",
        "low_interior_degree",
        "interior_degree",
        "custom_dimension",
        "standard_low_dimension",
        "standard_high_dimension",
        "trace_dimension",
        "low_interior_dimension",
        "high_interior_dimension",
        "polynomial_subspace_rank",
        "coefficient_matrix_condition_number",
        "low_space_embedding_rank",
        "low_interior_embedding_rank",
        "low_trace_identity_error_max",
        "low_interior_trace_leakage_max",
        "both_high_and_low_exact_sequence_pass",
        "map_type",
        "sobolev_space",
        "continuity_policy",
        "ordinary_default_changed",
    )
    compact = {key: audit.get(key) for key in keys}
    compact["high_exact_sequence"] = audit.get("high_exact_sequence")
    compact["low_exact_sequence"] = audit.get("low_exact_sequence")
    return compact


def _candidate_recovery_signal(
    reference: dict[str, Any],
    comparison: dict[str, Any],
    *,
    decision_use: str = (
        "authorizes at most one h13 escalation when true; never changes "
        "the formal 12-channel acceptance Gate"
    ),
) -> dict[str, Any]:
    """Compare a directional candidate with the accepted h15 fixed seed."""

    candidate_by_key = {
        (
            row["side"],
            int(row["m"]),
            int(row["n"]),
            row["polarization"],
        ): row
        for row in comparison["channels"]
    }
    rows: list[dict[str, Any]] = []
    for reference_row in reference["channels"]:
        channel = reference_row["channel"]
        key = (
            channel["side"],
            int(channel["m"]),
            int(channel["n"]),
            channel["polarization"],
        )
        candidate = candidate_by_key[key]
        seed = reference_row[
            "underresolved_diagnostics_not_in_bands"
        ]["fixed_p5trace_p6interior_h15"]
        center = reference_row["reference_center"]
        gate = reference_row["unchanged_v0_acceptance_gate"]
        seed_power_error = abs(
            float(seed["power"]) - float(center["power"])
        )
        seed_amplitude = complex(*seed["complex_amplitude"])
        center_amplitude = complex(*center["complex_amplitude"])
        seed_amplitude_error = abs(
            seed_amplitude - center_amplitude
        )
        power_tolerance = float(gate["power_absolute_tolerance"])
        amplitude_tolerance = float(
            gate["complex_amplitude_absolute_tolerance"]
        )
        candidate_power_error = float(
            candidate[
                "candidate_vs_reference_power_absolute_error"
            ]
        )
        candidate_amplitude_error = float(
            candidate[
                "candidate_vs_reference_amplitude_absolute_error"
            ]
        )
        rows.append(
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "seed_power_error_normalized": (
                    seed_power_error / power_tolerance
                ),
                "candidate_power_error_normalized": (
                    candidate_power_error / power_tolerance
                ),
                "seed_amplitude_error_normalized": (
                    seed_amplitude_error / amplitude_tolerance
                ),
                "candidate_amplitude_error_normalized": (
                    candidate_amplitude_error / amplitude_tolerance
                ),
                "seed_power_pass": seed_power_error <= power_tolerance,
                "candidate_power_pass": candidate["power_pass"],
                "seed_complex_amplitude_pass": (
                    seed_amplitude_error <= amplitude_tolerance
                ),
                "candidate_complex_amplitude_pass": (
                    candidate["complex_amplitude_pass"]
                ),
            }
        )
    seed_failed_power = [
        row for row in rows if not row["seed_power_pass"]
    ]
    seed_failed_amplitude = [
        row for row in rows
        if not row["seed_complex_amplitude_pass"]
    ]

    def normalized_l2(
        selected: list[dict[str, Any]],
        key: str,
    ) -> float:
        return math.sqrt(
            sum(float(row[key]) ** 2 for row in selected)
        )

    seed_power_l2 = normalized_l2(
        seed_failed_power,
        "seed_power_error_normalized",
    )
    candidate_power_l2 = normalized_l2(
        seed_failed_power,
        "candidate_power_error_normalized",
    )
    seed_amplitude_l2 = normalized_l2(
        seed_failed_amplitude,
        "seed_amplitude_error_normalized",
    )
    candidate_amplitude_l2 = normalized_l2(
        seed_failed_amplitude,
        "candidate_amplitude_error_normalized",
    )
    seed_power_count = sum(row["seed_power_pass"] for row in rows)
    candidate_power_count = sum(
        row["candidate_power_pass"] for row in rows
    )
    seed_amplitude_count = sum(
        row["seed_complex_amplitude_pass"] for row in rows
    )
    candidate_amplitude_count = sum(
        row["candidate_complex_amplitude_pass"] for row in rows
    )
    power_relative_reduction = (
        (seed_power_l2 - candidate_power_l2)
        / max(seed_power_l2, 1.0e-30)
    )
    amplitude_relative_reduction = (
        (seed_amplitude_l2 - candidate_amplitude_l2)
        / max(seed_amplitude_l2, 1.0e-30)
    )
    count_improved = bool(
        candidate_power_count > seed_power_count
        or candidate_amplitude_count > seed_amplitude_count
    )
    no_count_regression = bool(
        candidate_power_count >= seed_power_count
        and candidate_amplitude_count >= seed_amplitude_count
    )
    material_error_reduction = bool(
        power_relative_reduction >= 5.0e-2
        or amplitude_relative_reduction >= 5.0e-2
    )
    power_improved_failed_count = sum(
        row["candidate_power_error_normalized"]
        < row["seed_power_error_normalized"]
        for row in seed_failed_power
    )
    amplitude_improved_failed_count = sum(
        row["candidate_amplitude_error_normalized"]
        < row["seed_amplitude_error_normalized"]
        for row in seed_failed_amplitude
    )
    majority_failed_channels_improved = bool(
        (
            power_relative_reduction >= 5.0e-2
            and power_improved_failed_count
            > len(seed_failed_power) / 2.0
        )
        or (
            amplitude_relative_reduction >= 5.0e-2
            and amplitude_improved_failed_count
            > len(seed_failed_amplitude) / 2.0
        )
    )
    no_material_l2_regression = bool(
        power_relative_reduction >= -1.0e-2
        and amplitude_relative_reduction >= -1.0e-2
    )
    positive = bool(
        no_count_regression
        and no_material_l2_regression
        and (
            count_improved
            or (
                material_error_reduction
                and majority_failed_channels_improved
            )
        )
    )
    return {
        "schema_version": "task035b.seed-recovery-signal.v1",
        "status": (
            "positive_seed_recovery_signal"
            if positive
            else "controlled_negative_seed_recovery_signal"
        ),
        "positive_signal": positive,
        "decision_use": decision_use,
        "seed": (
            "accepted fixed p5-trace/p6-interior h15 diagnostic embedded "
            "in significant-channel reference v1"
        ),
        "seed_power_pass_count": seed_power_count,
        "candidate_power_pass_count": candidate_power_count,
        "seed_complex_amplitude_pass_count": seed_amplitude_count,
        "candidate_complex_amplitude_pass_count": (
            candidate_amplitude_count
        ),
        "seed_failed_power_channel_count": len(seed_failed_power),
        "seed_failed_complex_amplitude_channel_count": len(
            seed_failed_amplitude
        ),
        "seed_failed_power_normalized_l2": seed_power_l2,
        "candidate_on_seed_failed_power_normalized_l2": (
            candidate_power_l2
        ),
        "seed_failed_amplitude_normalized_l2": seed_amplitude_l2,
        "candidate_on_seed_failed_amplitude_normalized_l2": (
            candidate_amplitude_l2
        ),
        "power_relative_error_reduction": power_relative_reduction,
        "amplitude_relative_error_reduction": (
            amplitude_relative_reduction
        ),
        "minimum_material_relative_reduction": 5.0e-2,
        "maximum_allowed_l2_regression": 1.0e-2,
        "power_improved_failed_channel_count": (
            power_improved_failed_count
        ),
        "amplitude_improved_failed_channel_count": (
            amplitude_improved_failed_count
        ),
        "majority_failed_channels_improved": (
            majority_failed_channels_improved
        ),
        "no_material_l2_regression": no_material_l2_regression,
        "count_improved": count_improved,
        "no_count_regression": no_count_regression,
        "material_error_reduction": material_error_reduction,
        "normalization": (
            "unchanged v0 per-channel h10 p5-to-p6 Gate tolerance"
        ),
        "thresholds_relaxed": False,
        "channels": rows,
    }


def _execution_integrity_pass(
    summary: dict[str, Any],
    resource_audit: dict[str, Any],
    *,
    trace_degree: int,
    interior_degree: int,
) -> bool:
    """Validate the physically reduced solve against the persisted schema."""

    cell_audit = summary.get("cell_static_condensation") or {}
    true_residual = cell_audit.get("full_explicit_true_residual") or {}
    entity_audit = resource_audit.get("entity_dof_inventory") or {}
    resolved_config = summary.get("config") or {}
    return bool(
        isinstance(
            true_residual.get("linear_system_relative_residual"),
            (int, float),
        )
        and float(true_residual["linear_system_relative_residual"]) <= 1.0e-9
        and entity_audit.get("pass") is True
        and summary.get("mesh_cell_type_actual") == "hexahedron"
        and resolved_config.get("nedelec_trace_degree_resolved")
        == int(trace_degree)
        and resolved_config.get("nedelec_interior_degree_resolved")
        == int(interior_degree)
        and cell_audit.get("full_global_matrix_allocated") is False
        and cell_audit.get("full_trace_matrix_allocated") is False
    )


def _dtn_auxiliary_scaling_contract(
    summary: dict[str, Any],
    *,
    evanescent_buffer: int,
) -> dict[str, Any]:
    """Fail closed on the actual auxiliary basis used by a port diagnostic."""

    evanescent_buffer = int(evanescent_buffer)
    scaling = summary.get("dtn_auxiliary_coordinate_scaling")
    if evanescent_buffer == 0:
        return {
            "status": "not_requested",
            "pass": scaling is None,
            "evanescent_buffer": 0,
            "actual_scaling": scaling,
            "ordinary_default_changed": False,
        }
    if not isinstance(scaling, dict):
        return {
            "status": "missing_boundary_referenced_scaling",
            "pass": False,
            "evanescent_buffer": evanescent_buffer,
            "actual_scaling": scaling,
            "ordinary_default_changed": False,
        }
    scaled_mode_count = scaling.get("scaled_mode_count")
    expected_mode_count = summary.get("dtn_port_evanescent_mode_count")
    minimum_scale = scaling.get("minimum_abs_coordinate_scale")
    minimum_denominator = scaling.get(
        "minimum_assembly_projection_denominator"
    )
    passed = bool(
        scaling.get("status")
        == "boundary_referenced_evanescent_buffer_active"
        and scaling.get("ordinary_default_changed") is False
        and scaling.get("solver_coordinate")
        == "a_solver=exp(i*kz*z_port)*a_global_z"
        and scaling.get("official_output_coordinate")
        == "historical_global_z"
        and isinstance(scaled_mode_count, int)
        and not isinstance(scaled_mode_count, bool)
        and scaled_mode_count > 0
        and scaled_mode_count == expected_mode_count
        and isinstance(minimum_scale, (int, float))
        and not isinstance(minimum_scale, bool)
        and math.isfinite(float(minimum_scale))
        and float(minimum_scale) > 0.0
        and isinstance(minimum_denominator, (int, float))
        and not isinstance(minimum_denominator, bool)
        and math.isfinite(float(minimum_denominator))
        and float(minimum_denominator) > 0.0
    )
    return {
        "status": (
            "actual_boundary_referenced_scaling_pass"
            if passed
            else "actual_boundary_referenced_scaling_fail"
        ),
        "pass": passed,
        "evanescent_buffer": evanescent_buffer,
        "expected_scaled_mode_count": expected_mode_count,
        "actual_scaling": scaling,
        "ordinary_default_changed": False,
    }


def run_target_fixed_trace_candidate(
    out_dir: Path,
    *,
    control_record: Path,
    control_sha256: str,
    significant_channel_reference_record: Path,
    significant_channel_reference_sha256: str,
    global_p6_baseline_record: Path | None = None,
    global_p6_baseline_sha256: str | None = None,
    directional_parent_record: Path | None = None,
    directional_parent_sha256: str | None = None,
    h_nm: float = 15.0,
    incident_theta_deg: float = 80.0,
    polarization_kind: str = "s",
    trace_degree: int = 5,
    interior_degree: int = 6,
    directional_recovery: bool = False,
    directional_axis: str | None = None,
    mesh_axis_cell_counts: tuple[int, int, int] | None = None,
    channel_adjoint_diagnostic: bool = False,
    dtn_quadrature_degree: int | None = None,
    dtn_evanescent_buffer: int = 0,
    progress_observer=None,
) -> dict[str, Any]:
    """Run an exact p5-trace/p6-interior candidate on one fitted topology.

    The accepted h15 seed may bind a same-mesh global-p6 resource baseline.
    Directional Review-V1 recovery topologies deliberately omit that optional
    authority so they do not require an otherwise unnecessary global-p6 solve.
    """

    from src.adaptivity.hcurl_regionwise_p import (
        create_reduced_trace_hcurl_element,
    )
    from src.adaptivity.high_order_resource_audit import (
        build_high_order_resource_audit,
    )
    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if (global_p6_baseline_record is None) != (
        global_p6_baseline_sha256 is None
    ):
        raise ValueError(
            "same-mesh global-p6 baseline path and SHA256 must be paired"
        )
    if (directional_parent_record is None) != (
        directional_parent_sha256 is None
    ):
        raise ValueError(
            "directional parent path and SHA256 must be paired"
        )
    dtn_evanescent_buffer = int(dtn_evanescent_buffer)
    port_diagnostic = bool(
        dtn_quadrature_degree is not None
        or dtn_evanescent_buffer > 0
    )
    if dtn_evanescent_buffer < 0:
        raise ValueError("DtN evanescent buffer must be nonnegative")
    if (
        dtn_quadrature_degree is not None
        and dtn_evanescent_buffer > 0
    ):
        raise ValueError(
            "change only one DtN/port diagnostic control per run"
        )
    if port_diagnostic and (
        directional_recovery or channel_adjoint_diagnostic
    ):
        raise ValueError(
            "DtN/port diagnostic, directional recovery, and channel-adjoint "
            "seed diagnostic are mutually exclusive"
        )
    if directional_axis is not None and not directional_recovery:
        raise ValueError(
            "directional_axis requires directional fixed-trace recovery"
        )
    resolved_directional_axis = (
        ("z" if directional_axis is None else str(directional_axis).lower())
        if directional_recovery
        else None
    )
    if mesh_axis_cell_counts is not None:
        if (
            not isinstance(mesh_axis_cell_counts, tuple)
            or len(mesh_axis_cell_counts) != 3
            or any(
                type(value) is not int
                for value in mesh_axis_cell_counts
            )
        ):
            raise ValueError(
                "mesh_axis_cell_counts must contain exactly three integers"
            )
        mesh_axis_cell_counts = tuple(mesh_axis_cell_counts)
    if directional_recovery:
        if channel_adjoint_diagnostic:
            raise ValueError(
                "channel-adjoint seed diagnostic and directional recovery "
                "are mutually exclusive"
            )
        if global_p6_baseline_record is not None:
            raise ValueError(
                "directional fixed-trace recovery must omit a same-mesh "
                "global-p6 baseline"
            )
        if resolved_directional_axis == "z":
            if (
                not any(
                    abs(float(h_nm) - allowed) <= 1.0e-12
                    for allowed in (14.0, 13.0)
                )
                or mesh_axis_cell_counts is not None
            ):
                raise ValueError(
                    "z-directional fixed-trace recovery requires legacy "
                    "h14 or h13 without an explicit axis override"
                )
            if abs(float(h_nm) - 13.0) <= 1.0e-12:
                if directional_parent_record is None:
                    raise ValueError(
                        "h13 directional escalation requires a positive "
                        "SHA-bound h14 parent"
                    )
            elif directional_parent_record is not None:
                raise ValueError(
                    "the primary h14 directional point must not provide a "
                    "parent record"
                )
        elif resolved_directional_axis == "x":
            if (
                abs(float(h_nm) - 15.0) > 1.0e-12
                or mesh_axis_cell_counts != (7, 2, 10)
                or directional_parent_record is not None
            ):
                raise ValueError(
                    "x-directional fixed-trace recovery requires nominal "
                    "h15, exact axis cells (7, 2, 10), and no parent"
                )
        else:
            raise ValueError(
                "directional_axis must be 'x' or legacy 'z'"
            )
    elif (
        abs(float(h_nm) - 15.0) > 1.0e-12
        or global_p6_baseline_record is None
        or mesh_axis_cell_counts is not None
    ):
        raise ValueError(
            "the accepted fixed-trace seed requires h15 and a qualified "
            "same-mesh global-p6 baseline without an axis override"
        )
    elif directional_parent_record is not None:
        raise ValueError(
            "the accepted h15 seed does not use a directional parent"
        )
    control_record = Path(control_record).resolve()
    if _sha256(control_record) != str(control_sha256):
        raise ValueError("Task035b p5/p6 control SHA256 authority mismatch")
    control = json.loads(control_record.read_text(encoding="utf-8"))
    if (
        control.get("status") != "actual_global_r5_pass"
        or (control.get("qualification") or {}).get("pass") is not True
        or (control.get("coarse") or {}).get("degree") != 5
        or (control.get("enriched") or {}).get("degree") != 6
    ):
        raise ValueError("Task035b p5/p6 control record is not qualified")
    control_dir = _control_run_dir(control)
    p5_path = control_dir / "coarse_p5" / "run_summary.json"
    p6_path = control_dir / "enriched_p6" / "run_summary.json"
    p5, p5_authority = _load_control_summary(control["coarse"], p5_path)
    p6, p6_authority = _load_control_summary(control["enriched"], p6_path)
    significant_channel_reference_record = Path(
        significant_channel_reference_record
    ).resolve()
    significant_channel_reference = _load_significant_channel_reference(
        significant_channel_reference_record,
        significant_channel_reference_sha256,
    )
    directional_parent = (
        None
        if directional_parent_record is None
        else _load_directional_parent(
            Path(directional_parent_record).resolve(),
            str(directional_parent_sha256),
            significant_reference_sha256=(
                significant_channel_reference_sha256
            ),
        )
    )
    global_p6_baseline = None
    global_p6_baseline_entry = None
    if global_p6_baseline_record is not None:
        global_p6_baseline_record = Path(
            global_p6_baseline_record
        ).resolve()
        global_p6_baseline = _load_global_p6_baseline(
            global_p6_baseline_record,
            str(global_p6_baseline_sha256),
        )
        global_p6_baseline_entry = global_p6_baseline["enriched"]
    required_paths = [
        control_dir / degree_dir / "dtn_port_diffraction_orders_3d.json"
        for degree_dir in ("coarse_p5", "enriched_p6")
    ]
    required_paths.extend(
        control_dir
        / degree_dir
        / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
        for degree_dir in ("coarse_p5", "enriched_p6")
        for rank in range(8)
    )
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise ValueError(
            "Task035b p5/p6 field/channel authorities are incomplete: "
            + ", ".join(missing)
        )
    reduced = create_reduced_trace_hcurl_element(
        int(trace_degree),
        int(interior_degree),
    )
    element_audit = _compact_element_audit(reduced.audit)
    if element_audit["both_high_and_low_exact_sequence_pass"] is not True:
        raise ValueError("fixed-trace candidate fails exact-sequence preflight")
    base = target_stage4_config(degree=int(interior_degree), h_nm=float(h_nm))
    effective_dtn_quadrature_degree = (
        25
        if dtn_evanescent_buffer > 0
        and dtn_quadrature_degree is None
        else dtn_quadrature_degree
    )
    cfg = replace(
        base,
        case_name=(
            f"task035b_fixed_p{trace_degree}trace_"
            f"p{interior_degree}interior_h{h_nm:g}"
            + (
                ""
                if mesh_axis_cell_counts is None
                else "_axis" + "x".join(
                    str(value) for value in mesh_axis_cell_counts
                )
            )
        ).replace(".", "p"),
        incident_theta_deg=float(incident_theta_deg),
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="hexahedron",
        mesh_axis_cell_counts=mesh_axis_cell_counts,
        nedelec_trace_degree=int(trace_degree),
        nedelec_interior_degree=int(interior_degree),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=False,
        direct_release_base_after_augmentation=True,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
        direct_release_solver_before_postprocess=(
            not channel_adjoint_diagnostic
        ),
        stage4_retain_dual_recovery_context=(
            channel_adjoint_diagnostic
        ),
        stage4_dtn_quadrature_degree=effective_dtn_quadrature_degree,
        stage4_dtn_evanescent_buffer=dtn_evanescent_buffer,
        petsc_extra_options={
            **base.petsc_extra_options,
            "mat_mumps_icntl_14": 100,
        },
        unique_output=False,
    )
    capture: dict[str, Any] = {}

    def observer(**state) -> None:
        capture.update(
            field=state["field"],
            mesh_data=state["mesh_data"],
        )
        if channel_adjoint_diagnostic:
            from .dtn_goal_adjoint import (
                evaluate_actual_dtn_channel_adjoints,
            )
            from .fixed_trace_goal_entity_localization import (
                localize_recovered_dual_sensitivity_proxy,
            )

            recovery_context = (
                state["dtn_result"]["goal_context"].get(
                    "assembly_time_dual_recovery"
                )
            )
            if (
                recovery_context is None
                or recovery_context.get(
                    "exact_augmented_interior_coupling"
                )
                is not True
            ):
                raise RuntimeError(
                    "channel adjoints require exact augmented dual recovery"
                )
            recovered: dict[str, Any] = {}

            def recover(goal, reduced_dual) -> None:
                full_dual = recovery_context[
                    "recover_full_fe_dual"
                ](reduced_dual)
                try:
                    localization = (
                        localize_recovered_dual_sensitivity_proxy(
                            state["field"].function_space,
                            full_dual,
                            goal=goal,
                            reference_v1=(
                                significant_channel_reference
                            ),
                            periodic_axes={
                                "x": (
                                    float(state["config"].x_min),
                                    float(state["config"].x_max),
                                ),
                                "y": (
                                    float(state["config"].y_min),
                                    float(state["config"].y_max),
                                ),
                            },
                        )
                    )
                    recovered[goal.label] = {
                        "full_fe_rows": int(full_dual.getSize()),
                        "full_fe_dual_norm": float(full_dual.norm()),
                        "recovery_schema_version": recovery_context[
                            "schema_version"
                        ],
                        "exact_augmented_dual_recovery": True,
                        "entity_sensitivity_proxy": localization,
                    }
                finally:
                    full_dual.destroy()

            progress("fixed_trace_channel_adjoints", "begin")
            adjoint_started = time.perf_counter()
            capture["channel_adjoints"] = (
                evaluate_actual_dtn_channel_adjoints(
                    linear_system=state["linear_system"],
                    dtn_result=state["dtn_result"],
                    config=state["config"],
                    communicator=(
                        state["field"].function_space.mesh.comm
                    ),
                    adjoint_observer=recover,
                )
            )
            capture["channel_adjoint_elapsed_seconds"] = float(
                time.perf_counter() - adjoint_started
            )
            capture["recovered_channel_duals"] = recovered
            capture["dual_recovery_context_audit"] = {
                key: value
                for key, value in recovery_context.items()
                if key != "recover_full_fe_dual"
            }
            progress("fixed_trace_channel_adjoints", "end")

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    progress("fixed_trace_candidate_solve", "begin")
    started = time.perf_counter()
    summary = run_stage4b_block_grating_3d_case(
        cfg,
        out_dir / "candidate",
        solution_observer=observer,
    )
    progress("fixed_trace_candidate_solve", "end")
    if summary.get("official_result") is not True:
        raise RuntimeError("fixed-trace candidate did not produce an official result")
    resource_audit = build_high_order_resource_audit(
        capture["field"],
        capture["mesh_data"],
        summary,
    )
    if global_p6_baseline_entry is None:
        same_mesh_baseline = {
            "schema_version": (
                "task035b.fixed-trace-same-mesh-baseline.v1"
            ),
            "status": "not_run_directional_recovery",
            "required": False,
            "pass": None,
            "reason": (
                "Review-V1 directional topology does not require a separate "
                "same-mesh global-p6 solve"
            ),
        }
        resource_comparison = {
            "schema_version": (
                "task035b.fixed-trace-resource-comparison.v1"
            ),
            "status": "derived_dof_only_directional_recovery",
            "same_mesh_global_p6_measured": False,
        }
    else:
        same_mesh_baseline = {
            **_same_mesh_identity(
                resource_audit,
                global_p6_baseline_entry,
            ),
            "required": True,
        }
        resource_comparison = _same_mesh_resource_comparison(
            summary,
            global_p6_baseline_entry,
        )
    observable_comparison = compare_observables(summary, p5, p6)
    all_channel_diagnostic = compare_diffraction_channels(
        global_p5_path=control_dir
        / "coarse_p5"
        / "dtn_port_diffraction_orders_3d.json",
        global_p6_path=control_dir
        / "enriched_p6"
        / "dtn_port_diffraction_orders_3d.json",
        candidate_p6_path=out_dir
        / "candidate"
        / "dtn_port_diffraction_orders_3d.json",
        allow_candidate_extra_modes=dtn_evanescent_buffer > 0,
        expected_candidate_ordered_identity_sha256=(
            "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629"
            if dtn_evanescent_buffer > 0
            else "f039dd14264f7bc2987e75e311ef338682388b1f17a4ea194702ff888f4c7a21"
        ),
    )
    channel_comparison = compare_significant_channels_to_reference_v1(
        candidate_path=out_dir
        / "candidate"
        / "dtn_port_diffraction_orders_3d.json",
        reference_record_path=significant_channel_reference_record,
        reference_record_sha256=significant_channel_reference_sha256,
    )
    channel_comparison["all_80_channel_diagnostic"] = (
        all_channel_diagnostic
    )
    channel_comparison[
        "all_80_dynamic_significance_diagnostic_pass"
    ] = (
        all_channel_diagnostic["pass"]
    )
    channel_comparison["formal_gate_definition"] = (
        "frozen reference-v1 12-channel power and complex-amplitude Gate; "
        "the broader dynamic comparison is diagnostic only"
    )
    progress("fixed_trace_field_interface_comparison", "begin")
    field_comparison = compare_cross_mesh_fields(
        global_p5_dir=control_dir / "coarse_p5",
        global_p6_dir=control_dir / "enriched_p6",
        candidate_p6_dir=out_dir / "candidate",
    )
    progress("fixed_trace_field_interface_comparison", "end")
    directional_signal = (
        _candidate_recovery_signal(
            significant_channel_reference,
            channel_comparison,
            decision_use=(
                "classifies the x-only recovery lane and never authorizes "
                "a z/h13 escalation or changes the formal 12-channel Gate"
                if resolved_directional_axis == "x"
                else (
                    "authorizes at most one z/h13 escalation when true; "
                    "never changes the formal 12-channel acceptance Gate"
                )
            ),
        )
        if directional_recovery
        else None
    )
    port_signal = (
        _candidate_recovery_signal(
            significant_channel_reference,
            channel_comparison,
            decision_use=(
                "classifies this isolated DtN/port diagnostic only; never "
                "authorizes h13 and never changes the formal 12-channel "
                "acceptance Gate"
            ),
        )
        if port_diagnostic
        else None
    )
    port_scaling_contract = _dtn_auxiliary_scaling_contract(
        summary,
        evanescent_buffer=dtn_evanescent_buffer,
    )
    actual_dofs = int(summary["num_nedelec_dofs"])
    execution_pass = _execution_integrity_pass(
        summary,
        resource_audit,
        trace_degree=trace_degree,
        interior_degree=interior_degree,
    ) and (
        same_mesh_baseline["pass"] is True
        if same_mesh_baseline["required"]
        else True
    )
    channel_adjoint_report = capture.get("channel_adjoints")
    channel_adjoint_pass = bool(
        isinstance(channel_adjoint_report, dict)
        and channel_adjoint_report.get("pass") is True
        and channel_adjoint_report.get("goal_count") == 16
        and len(capture.get("recovered_channel_duals") or {}) == 16
        and all(
            row.get("exact_augmented_dual_recovery") is True
            for row in (
                capture.get("recovered_channel_duals") or {}
            ).values()
        )
    )
    result_execution_pass = bool(
        execution_pass
        and port_scaling_contract["pass"]
        and (
            channel_adjoint_pass
            if channel_adjoint_diagnostic
            else True
        )
    )
    accuracy_pass = bool(
        observable_comparison["pass"]
        and channel_comparison["pass"]
        and field_comparison["pass"]
    )
    return {
        "schema_version": "task035b.fixed-trace-candidate.v1",
        "status": (
            "actual_fixed_trace_channel_adjoint_diagnostic_pass"
            if channel_adjoint_diagnostic and result_execution_pass
            else "actual_fixed_trace_channel_adjoint_diagnostic_fail"
            if channel_adjoint_diagnostic
            else "actual_fixed_trace_port_diagnostic_positive"
            if (
                port_diagnostic
                and result_execution_pass
                and port_signal["positive_signal"]
            )
            else "actual_fixed_trace_port_diagnostic_controlled_negative"
            if port_diagnostic and result_execution_pass
            else "actual_fixed_trace_port_diagnostic_fail"
            if port_diagnostic
            else "actual_fixed_trace_candidate_pass"
            if result_execution_pass and accuracy_pass
            else "actual_fixed_trace_controlled_negative"
            if result_execution_pass
            else "actual_fixed_trace_execution_fail"
        ),
        "pass": result_execution_pass,
        "candidate_accuracy_pass": accuracy_pass,
        "channel_adjoint_diagnostic_only": channel_adjoint_diagnostic,
        "port_diagnostic_only": port_diagnostic,
        "formal_candidate_eligible": bool(
            not channel_adjoint_diagnostic
            and result_execution_pass
            and accuracy_pass
        ),
        "ordinary_default_changed": False,
        "target_identity": {
            "geometry": "Task034 fixed rectangular block grating",
            "h_nm": float(h_nm),
            "directional_axis": resolved_directional_axis,
            "mesh_axis_cell_counts_requested": (
                None
                if mesh_axis_cell_counts is None
                else list(mesh_axis_cell_counts)
            ),
            "directional_mesh_change_semantics": (
                "exact_material_fitted_remeshing_not_nested_refinement"
                if directional_recovery
                else "not_applicable"
            ),
            "actual_mesh_cells_resolved": summary.get(
                "mesh_cells_resolved"
            ),
            "actual_mesh_cell_count": summary.get("num_mesh_cells"),
            "trace_degree": int(trace_degree),
            "interior_degree": int(interior_degree),
            "space": "global p5 trace plus p6 cell interior on every cell",
        },
        "element_audit": element_audit,
        "control_authority": {
            "path": str(control_record),
            "sha256": str(control_sha256),
            "raw_observable_summaries": {
                "p5": p5_authority,
                "p6": p6_authority,
            },
        },
        "significant_channel_reference_authority": {
            "path": str(significant_channel_reference_record),
            "sha256": str(significant_channel_reference_sha256).lower(),
            "reference_payload_sha256": (
                significant_channel_reference.get(
                    "reference_payload_sha256"
                )
            ),
            "frozen_channel_count": 12,
            "unchanged_v0_gate": True,
            "numerical_convergence_band_used_as_gate": False,
        },
        "directional_parent_authority": (
            {
                "status": (
                    "not_required_primary_x"
                    if resolved_directional_axis == "x"
                    else "not_required_primary_h14"
                ),
                "required": False,
            }
            if directional_recovery and directional_parent is None
            else {
                "status": "qualified_positive_h14_parent",
                "required": True,
                "path": str(Path(directional_parent_record).resolve()),
                "sha256": str(directional_parent_sha256).lower(),
                "source_sha": (
                    directional_parent.get("source") or {}
                ).get("commit_sha"),
            }
            if directional_parent is not None
            else {
                "status": "not_applicable_h15_seed",
                "required": False,
            }
        ),
        "global_p6_baseline_authority": (
            {
                "status": "not_run_directional_recovery",
                "required": False,
            }
            if global_p6_baseline is None
            else {
                "status": "qualified_same_mesh_baseline",
                "required": True,
                "path": str(global_p6_baseline_record),
                "sha256": str(global_p6_baseline_sha256),
                "source_sha": (
                    global_p6_baseline.get("source") or {}
                ).get("commit_sha"),
            }
        ),
        "same_mesh_global_p6_baseline": same_mesh_baseline,
        "same_mesh_resource_comparison": resource_comparison,
        "candidate": {
            "degree": int(interior_degree),
            "h_nm": float(h_nm),
            "summary": summary,
            "high_order_resource_audit": resource_audit,
        },
        "dof_target": {
            "active_full3d_equivalent_dofs": actual_dofs,
            "same_mesh_global_p6_dofs": (
                _derived_standard_global_dofs(
                    resource_audit,
                    degree=interior_degree,
                )
                if global_p6_baseline_entry is None
                else int(global_p6_baseline_entry["num_nedelec_dofs"])
            ),
            "same_mesh_global_p6_dof_authority": (
                "derived_exact_entity_count"
                if global_p6_baseline_entry is None
                else "measured_qualified_record"
            ),
            "minimum_le_90000": actual_dofs <= 90000,
            "preferred_65000_to_75000": 65000 <= actual_dofs <= 75000,
            "inactive_p6_trace_modes_physically_absent": (
                actual_dofs
                < _derived_standard_global_dofs(
                    resource_audit,
                    degree=interior_degree,
                )
                and element_audit["custom_dimension"]
                < element_audit["standard_high_dimension"]
            ),
        },
        "observable_comparison": observable_comparison,
        "diffraction_channel_comparison": channel_comparison,
        "directional_recovery_signal": directional_signal,
        "port_diagnostic": (
            {
                "status": (
                    "port_diagnostic_execution_fail"
                    if not result_execution_pass
                    else "positive_port_diagnostic"
                    if port_signal["positive_signal"]
                    else "controlled_negative_port_diagnostic"
                ),
                "pass": result_execution_pass,
                "classification_complete": result_execution_pass,
                "formal_candidate_eligible": bool(
                    result_execution_pass and accuracy_pass
                ),
                "operator_identity_with_frozen_reference": False,
                "requested_quadrature_degree": dtn_quadrature_degree,
                "effective_quadrature_degree": (
                    summary.get("stage4_dtn_surface_quadrature_degree")
                ),
                "evanescent_buffer": dtn_evanescent_buffer,
                "mode_count": (
                    summary.get("dtn_port_mode_count")
                ),
                "evanescent_mode_count": (
                    summary.get("dtn_port_evanescent_mode_count")
                ),
                "auxiliary_coordinate_scaling_contract": (
                    port_scaling_contract
                ),
                "seed_recovery_signal": port_signal,
                "thresholds_relaxed": False,
            }
            if port_diagnostic
            else None
        ),
        "channel_adjoint_diagnostic": (
            {
                "status": (
                    "actual_channel_adjoints_and_exact_recovery_pass"
                    if channel_adjoint_pass
                    else "actual_channel_adjoints_or_recovery_fail"
                ),
                "pass": channel_adjoint_pass,
                "resource_authority": (
                    "diagnostic_only_factor_and_recovery_cache_retained"
                ),
                "formal_candidate_resource_comparable": False,
                "adjoint_elapsed_seconds": capture.get(
                    "channel_adjoint_elapsed_seconds"
                ),
                "adjoints": channel_adjoint_report,
                "recovered_full_duals": capture.get(
                    "recovered_channel_duals"
                ),
                "dual_recovery_context_audit": capture.get(
                    "dual_recovery_context_audit"
                ),
            }
            if channel_adjoint_diagnostic
            else None
        ),
        "selected_field_interface_error_gate": field_comparison,
        "elapsed_seconds": float(time.perf_counter() - started),
    }


__all__ = ["run_target_fixed_trace_candidate"]
