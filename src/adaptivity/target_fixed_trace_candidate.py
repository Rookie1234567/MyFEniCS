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


def run_target_fixed_trace_candidate(
    out_dir: Path,
    *,
    control_record: Path,
    control_sha256: str,
    global_p6_baseline_record: Path,
    global_p6_baseline_sha256: str,
    h_nm: float = 15.0,
    incident_theta_deg: float = 80.0,
    polarization_kind: str = "s",
    trace_degree: int = 5,
    interior_degree: int = 6,
    progress_observer=None,
) -> dict[str, Any]:
    """Run the strongest exact p5-trace/p6-interior candidate at h15."""

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
    global_p6_baseline_record = Path(global_p6_baseline_record).resolve()
    global_p6_baseline = _load_global_p6_baseline(
        global_p6_baseline_record,
        global_p6_baseline_sha256,
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
    cfg = replace(
        base,
        case_name=(
            f"task035b_fixed_p{trace_degree}trace_"
            f"p{interior_degree}interior_h{h_nm:g}"
        ).replace(".", "p"),
        incident_theta_deg=float(incident_theta_deg),
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="hexahedron",
        nedelec_trace_degree=int(trace_degree),
        nedelec_interior_degree=int(interior_degree),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=False,
        direct_release_base_after_augmentation=True,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
        direct_release_solver_before_postprocess=True,
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
    same_mesh_baseline = _same_mesh_identity(
        resource_audit,
        global_p6_baseline_entry,
    )
    resource_comparison = _same_mesh_resource_comparison(
        summary,
        global_p6_baseline_entry,
    )
    observable_comparison = compare_observables(summary, p5, p6)
    channel_comparison = compare_diffraction_channels(
        global_p5_path=control_dir
        / "coarse_p5"
        / "dtn_port_diffraction_orders_3d.json",
        global_p6_path=control_dir
        / "enriched_p6"
        / "dtn_port_diffraction_orders_3d.json",
        candidate_p6_path=out_dir
        / "candidate"
        / "dtn_port_diffraction_orders_3d.json",
    )
    progress("fixed_trace_field_interface_comparison", "begin")
    field_comparison = compare_cross_mesh_fields(
        global_p5_dir=control_dir / "coarse_p5",
        global_p6_dir=control_dir / "enriched_p6",
        candidate_p6_dir=out_dir / "candidate",
    )
    progress("fixed_trace_field_interface_comparison", "end")
    actual_dofs = int(summary["num_nedelec_dofs"])
    execution_pass = _execution_integrity_pass(
        summary,
        resource_audit,
        trace_degree=trace_degree,
        interior_degree=interior_degree,
    ) and same_mesh_baseline["pass"]
    accuracy_pass = bool(
        observable_comparison["pass"]
        and channel_comparison["pass"]
        and field_comparison["pass"]
    )
    return {
        "schema_version": "task035b.fixed-trace-candidate.v1",
        "status": (
            "actual_fixed_trace_candidate_pass"
            if execution_pass and accuracy_pass
            else "actual_fixed_trace_controlled_negative"
            if execution_pass
            else "actual_fixed_trace_execution_fail"
        ),
        "pass": execution_pass,
        "candidate_accuracy_pass": accuracy_pass,
        "ordinary_default_changed": False,
        "target_identity": {
            "geometry": "Task034 fixed rectangular block grating",
            "h_nm": float(h_nm),
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
        "global_p6_baseline_authority": {
            "path": str(global_p6_baseline_record),
            "sha256": str(global_p6_baseline_sha256),
            "source_sha": (global_p6_baseline.get("source") or {}).get(
                "commit_sha"
            ),
        },
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
            "same_mesh_global_p6_dofs": int(
                global_p6_baseline_entry["num_nedelec_dofs"]
            ),
            "minimum_le_90000": actual_dofs <= 90000,
            "preferred_65000_to_75000": 65000 <= actual_dofs <= 75000,
            "inactive_p6_trace_modes_physically_absent": (
                actual_dofs
                < int(global_p6_baseline_entry["num_nedelec_dofs"])
                and element_audit["custom_dimension"]
                < element_audit["standard_high_dimension"]
            ),
        },
        "observable_comparison": observable_comparison,
        "diffraction_channel_comparison": channel_comparison,
        "selected_field_interface_error_gate": field_comparison,
        "elapsed_seconds": float(time.perf_counter() - started),
    }


__all__ = ["run_target_fixed_trace_candidate"]
