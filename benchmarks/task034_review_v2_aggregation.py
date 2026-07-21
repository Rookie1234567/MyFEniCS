"""Aggregate accepted Task034 evidence; never launches a PDE solve."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping


COLUMNS = [
    "case_key", "p", "h_nm", "method", "M_per_direction", "MPI",
    "polarization", "status", "data_identity", "source_sha", "elements",
    "fe_dofs", "external_aux_dofs", "modal_unknowns", "total_rows",
    "assembled_nnz", "factor_nnz", "R_total", "T_total", "A_balance",
    "A_volume", "R00_s", "R00_p", "R00_total", "T00_s", "T00_p",
    "T00_total", "true_relative_residual", "assembly_seconds",
    "factorization_seconds", "solve_seconds", "total_seconds",
    "peak_memory_gib", "swap_bytes", "full3d_hybrid_closure_status",
    "evidence_path",
]


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _blank(**values: Any) -> dict[str, Any]:
    row = {name: None for name in COLUMNS}
    row.update(values)
    return row


def _product(value: Any) -> int | None:
    if isinstance(value, list) and value and all(isinstance(item, int) for item in value):
        result = 1
        for item in value:
            result *= item
        return result
    number = _finite(value)
    return int(number) if number is not None else None



_SCHEMA_EXACT_FIELDS = {
    "fe_dofs", "external_aux_dofs", "modal_unknowns", "total_rows",
    "assembled_nnz", "factor_nnz", "assembly_seconds",
    "factorization_seconds", "solve_seconds", "total_seconds",
}


def _resolve_evidence_path(root: Path, evidence: str | None) -> Path | None:
    if not evidence:
        return None
    path = Path(evidence)
    return path if path.is_absolute() else root / path


def _normalize_evidence_path(root: Path, evidence: str | None) -> str | None:
    path = _resolve_evidence_path(root, evidence)
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return f"external_absolute:{path}"


def _apply_descriptor(row: dict[str, Any], details: Mapping[str, Any]) -> None:
    for key, value in details.items():
        if key in _SCHEMA_EXACT_FIELDS or value is not None:
            row[key] = value


def _orders(payload: Mapping[str, Any], evidence_path: Path) -> list[Mapping[str, Any]]:
    validation = _mapping(_mapping(payload.get("measurements")).get("validation"))
    embedded = validation.get("external_diffraction_orders")
    if isinstance(embedded, list):
        return [row for row in embedded if isinstance(row, Mapping)]
    solver = _mapping(payload.get("solver_summary"))
    filename = solver.get("dtn_port_orders_json")
    run_dir = _mapping(payload.get("raw_evidence")).get("run_directory")
    command = payload.get("command")
    if not isinstance(run_dir, str) and isinstance(command, list) and "--run-dir" in command:
        run_dir = command[command.index("--run-dir") + 1]
    if not isinstance(filename, str) or not isinstance(run_dir, str):
        return []
    path = Path(filename)
    path = path if path.is_absolute() else Path(run_dir) / path
    if not path.exists():
        return []
    rows = _load(path).get("orders")
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _zero_orders(payload: Mapping[str, Any], evidence_path: Path) -> dict[str, float | None]:
    result = {
        f"{side}00_{pol}": None
        for side in ("R", "T")
        for pol in ("s", "p", "total")
    }
    for order in _orders(payload, evidence_path):
        m = int(order.get("m", order.get("order_m", 999)))
        n = int(order.get("n", order.get("order_n", 999)))
        if m != 0 or n != 0:
            continue
        side = str(order.get("side", "")).lower()
        pol = str(order.get("polarization", order.get("polarization_kind", ""))).lower()
        power = _finite(order.get("power_ratio"))
        prefix = "R" if side == "top" else "T" if side == "bottom" else ""
        if prefix and pol in {"s", "p"} and power is not None:
            result[f"{prefix}00_{pol}"] = power
    for prefix in ("R", "T"):
        values = [result[f"{prefix}00_s"], result[f"{prefix}00_p"]]
        if any(value is not None for value in values):
            result[f"{prefix}00_total"] = sum(value or 0.0 for value in values)
    return result


def _descriptor_details(root: Path, evidence: str | None) -> dict[str, Any]:
    path = _resolve_evidence_path(root, evidence)
    if path is None or not path.exists():
        return {}
    payload = _load(path)
    measurements = _mapping(payload.get("measurements"))
    system = _mapping(measurements.get("hybrid_system"))
    resource = _mapping(payload.get("resource_authority"))
    memory = _mapping(payload.get("memory"))

    if system:
        bottom_fe = int(_finite(system.get("bottom_local_fe_dofs")) or 0)
        top_fe = int(_finite(system.get("top_local_fe_dofs")) or 0)
        bottom_rows = int(_finite(system.get("bottom_global_size")) or 0)
        top_rows = int(_finite(system.get("top_global_size")) or 0)
        modal = int(_finite(system.get("internal_unknown_count")) or 0)
        fe_dofs = bottom_fe + top_fe
        external_aux_dofs = (bottom_rows - bottom_fe) + (top_rows - top_fe)
        total_rows = bottom_rows + top_rows + modal
        if min(fe_dofs, external_aux_dofs, modal, total_rows) < 0:
            raise ValueError(f"negative Hybrid structure field in {path}")
        if total_rows != fe_dofs + external_aux_dofs + modal:
            raise ValueError(f"Hybrid row decomposition mismatch in {path}")
        parts = [
            _finite(_mapping(system.get(f"{side}_matrix_stats")).get("matrix_nnz_used"))
            for side in ("bottom", "top")
        ]
        timing = _mapping(measurements.get("timing_seconds_max_rank"))
        solve = _mapping(measurements.get("solve"))
        details = {
            "elements": sum(
                int(_finite(system.get(f"{side}_local_mesh_cells")) or 0)
                for side in ("bottom", "top")
            ),
            "fe_dofs": fe_dofs,
            "external_aux_dofs": external_aux_dofs,
            "modal_unknowns": modal,
            "total_rows": total_rows,
            "assembled_nnz": (
                sum(parts) if all(value is not None for value in parts) else None
            ),
            "factor_nnz": None,
            "assembly_seconds": None,
            "factorization_seconds": None,
            "solve_seconds": _finite(solve.get("solve_seconds")),
            "total_seconds": _finite(timing.get("total")),
            "peak_memory_gib": (
                _finite(resource.get("memory_authority_gib"))
                or _finite(memory.get("max_simultaneous_worker_rss_gib"))
            ),
            "swap_bytes": 0 if (
                payload.get("no_swap") is True
                or resource.get("job_process_tree_swap_bytes") == 0
                or resource.get("container_swap_current_bytes") == 0
            ) else None,
        }
        details.update(_zero_orders(payload, path))
        return details

    calibration = _mapping(payload.get("calibration"))
    solver = _mapping(payload.get("solver_summary"))
    inventory = _mapping(solver.get("stage4_dtn_factor_inventory"))
    factor_stats = _mapping(inventory.get("matrix_stats"))
    exact_rows = _finite(calibration.get("exact_rows"))
    details = {
        "elements": _product(solver.get("num_mesh_cells")),
        "fe_dofs": int(_finite(calibration.get("num_nedelec_dofs")) or 0) or None,
        "external_aux_dofs": (
            int(_finite(calibration.get("num_auxiliary_dofs")) or 0) or None
        ),
        "modal_unknowns": None,
        "total_rows": int(exact_rows) if exact_rows is not None else None,
        "assembled_nnz": _finite(calibration.get("exact_assembled_nnz")),
        "factor_nnz": (
            _finite(factor_stats.get("matrix_nnz_used"))
            if inventory.get("available") is True else None
        ),
        "assembly_seconds": _finite(
            solver.get("stage4_dtn_base_matrix_assembly_seconds")
        ),
        "factorization_seconds": None,
        "solve_seconds": _finite(solver.get("stage4_dtn_linear_solve_seconds")),
        "total_seconds": _finite(solver.get("elapsed_seconds")),
        "peak_memory_gib": _finite(resource.get("memory_authority_gib")),
        "swap_bytes": 0 if (
            payload.get("no_swap") is True
            or resource.get("max_process_tree_swap_mb") == 0
        ) else None,
    }
    details.update(_zero_orders(payload, path))
    return details


def _case093_rows(root: Path, summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for point in summary.get("points", []):
        closure = _mapping(point.get("same_degree_closure")).get("status")
        for method_name in ("full3d", "hybrid"):
            record = _mapping(point.get(method_name))
            official = _mapping(record.get("official_values"))
            resource = _mapping(record.get("resource"))
            evidence = _mapping(record.get("evidence")).get("path")
            row = _blank(
                case_key=f"case093_{point['key']}_{method_name}",
                p=record.get("degree"), h_nm=record.get("h_nm"),
                method="Full3D" if method_name == "full3d" else "Hybrid",
                M_per_direction=(
                    resource.get("requested_modes")
                    if method_name == "hybrid" else None
                ),
                MPI=record.get("mpi_size"),
                polarization=record.get("polarization_kind"),
                status=record.get("status"),
                data_identity="measured_case093",
                source_sha=_mapping(record.get("source")).get("commit_sha"),
                R_total=official.get("R_total"),
                T_total=official.get("T_total"),
                A_balance=official.get("A_balance"),
                A_volume=official.get("A_volume_total"),
                true_relative_residual=record.get("true_relative_residual"),
                peak_memory_gib=resource.get("peak_memory_gib"),
                swap_bytes=0 if resource.get("no_swap") is True else None,
                full3d_hybrid_closure_status=closure,
                evidence_path=_normalize_evidence_path(root, evidence),
            )
            _apply_descriptor(row, _descriptor_details(root, evidence))
            rows.append(row)
    return rows


def _mpi_rows(
    root: Path,
    summary: Mapping[str, Any],
    case093: Mapping[str, Any],
) -> list[dict[str, Any]]:
    anchors = {point["key"]: point for point in case093.get("points", [])}
    anchor = _mapping(anchors["p3_h5"])
    rows = []
    for method_key, method in _mapping(summary.get("methods")).items():
        identity = _mapping(method.get("identity"))
        structure = _mapping(identity.get("structural"))
        anchor_record = _mapping(anchor.get(method_key))
        official = _mapping(anchor_record.get("official_values"))
        anchor_evidence = _mapping(anchor_record.get("evidence")).get("path")
        anchor_details = _descriptor_details(root, anchor_evidence)
        evidence = _mapping(method.get("evidence")).get("path")
        for comparison in method.get("comparisons", []):
            mpi = comparison.get("mpi_size")
            resource = _mapping(comparison.get("resource"))
            timings = _mapping(resource.get("timings_seconds"))
            rows.append(_blank(
                case_key=f"mpi_p3_h5_{method_key}_mpi{mpi}",
                p=3, h_nm=5.0,
                method="Full3D" if method_key == "full3d" else "Hybrid",
                M_per_direction=(
                    structure.get("requested_modes")
                    if method_key == "hybrid" else None
                ),
                MPI=mpi, polarization="s",
                status="mpi_identity_pass",
                data_identity=(
                    "measured_mpi_identity_with_selected_baseline_physics"
                ),
                source_sha=identity.get("source_sha"),
                elements=(
                    anchor_details.get("elements")
                    or _product(structure.get("mesh_cells"))
                ),
                fe_dofs=anchor_details.get("fe_dofs"),
                external_aux_dofs=anchor_details.get("external_aux_dofs"),
                modal_unknowns=anchor_details.get("modal_unknowns"),
                total_rows=anchor_details.get("total_rows"),
                assembled_nnz=(
                    anchor_details.get("assembled_nnz")
                    or structure.get("matrix_nnz")
                ),
                R_total=official.get("R_total"),
                T_total=official.get("T_total"),
                A_balance=official.get("A_balance"),
                A_volume=official.get("A_volume_total"),
                true_relative_residual=comparison.get("true_relative_residual"),
                total_seconds=timings.get("total"),
                peak_memory_gib=resource.get("peak_memory_gib"),
                swap_bytes=0,
                full3d_hybrid_closure_status=(
                    "representative_mpi_identity_pass"
                ),
                evidence_path=_normalize_evidence_path(root, evidence),
            ))
    return rows


def _m_rows(
    root: Path,
    case093: Mapping[str, Any],
    p4: Mapping[str, Any],
) -> list[dict[str, Any]]:
    specs = []
    points = {point["key"]: point for point in case093.get("points", [])}
    closure = _mapping(points["p3_h3"]).get("same_degree_closure")
    p3_path = _mapping(_mapping(closure).get("funnel")).get("path")
    p3_funnel = _load(_resolve_evidence_path(root, p3_path))
    for source in p3_funnel.get("source_records", []):
        specs.append((
            3, 3.0, 8,
            source.get("mode_count_per_direction"),
            source.get("source_commit_full_sha"),
            source.get("path"),
            "p3_h3_m_funnel_pass",
        ))
    hybrid_inputs = _mapping(_mapping(p4.get("input_evidence")).get("hybrid"))
    groups = _mapping(p4.get("source_compatibility")).get(
        "audited_source_groups", []
    )
    p4_source = groups[-1]["source_commit_full_sha"]
    for modes in (80, 120, 160):
        source = _mapping(hybrid_inputs.get(f"M{modes}"))
        specs.append((
            4, 5.0, 4, modes, p4_source, source.get("path"),
            "p4_h5_m_funnel_pass",
        ))

    rows = []
    for degree, h_nm, mpi, modes, sha, evidence, status in specs:
        path = _resolve_evidence_path(root, evidence)
        if path is None:
            raise ValueError("missing M-funnel evidence path")
        payload = _load(path)
        measurements = _mapping(payload.get("measurements"))
        solve = _mapping(measurements.get("solve"))
        validation = _mapping(measurements.get("validation"))
        port_power = _mapping(validation.get("port_power"))
        reconstruction = _mapping(measurements.get("physical_field_reconstruction"))
        absorption = _mapping(reconstruction.get("volume_absorption"))
        row = _blank(
            case_key=f"m_funnel_p{degree}_h{h_nm:g}_m{modes}",
            p=degree, h_nm=h_nm, method="Hybrid",
            M_per_direction=modes, MPI=mpi, polarization="s",
            status=status, data_identity="measured_mode_funnel",
            source_sha=sha,
            R_total=_finite(port_power.get("R_total")),
            T_total=_finite(port_power.get("T_total")),
            A_balance=_finite(port_power.get("A_balance")),
            A_volume=_finite(absorption.get("A_volume_total")),
            true_relative_residual=_finite(
                solve.get("true_relative_residual")
            ),
            evidence_path=_normalize_evidence_path(root, evidence),
            full3d_hybrid_closure_status="funnel_row",
        )
        _apply_descriptor(row, _descriptor_details(root, evidence))
        rows.append(row)
    return rows


def _supplemental_rows(root: Path) -> list[dict[str, Any]]:
    base = root / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records"
    rows = []
    filenames = (
        "p2_h1_execution_outcome.json",
        "p3_h2_execution_outcome.json",
        "p4_h3_execution_outcome.json",
    )
    for filename in filenames:
        payload = _load(base / filename)
        scope = _mapping(payload.get("case")) or _mapping(payload.get("scope"))
        degree = scope.get("degree")
        h_nm = scope.get("h_nm")
        mpi = scope.get("mpi_size")
        full = _mapping(payload.get("full3d"))
        full_evidence = (
            full.get("assembly_watchdog_record_path")
            or full.get("assembly_record_path")
        )
        full_row = _blank(
            case_key=f"supplemental_p{degree}_h{h_nm:g}_full3d",
            p=degree, h_nm=h_nm, method="Full3D",
            MPI=mpi, polarization="s",
            status="not_run_by_conservative_resource_gate_after_assembly",
            data_identity=(
                "measured_assembly_and_predicted_factorization_upper_bound"
            ),
            source_sha=full.get("source_sha") or payload.get("source_sha"),
            total_rows=full.get("exact_rows"),
            assembled_nnz=full.get("exact_assembled_nnz"),
            assembly_seconds=full.get("assembly_elapsed_seconds"),
            peak_memory_gib=full.get("assembly_peak_memory_gib"),
            swap_bytes=0,
            full3d_hybrid_closure_status=(
                "not_available_factorization_launched_false_"
                "full_solve_launched_false"
            ),
            evidence_path=_normalize_evidence_path(root, full_evidence),
        )
        _apply_descriptor(
            full_row,
            _descriptor_details(root, full_evidence),
        )
        rows.append(full_row)

        hybrid = (
            _mapping(payload.get("hybrid_m160"))
            or _mapping(payload.get("hybrid"))
        )
        hybrid_status = (
            "timeout_during_field_recovery_no_official_solution"
            if degree == 2
            else "measured_shard_pass_no_m_funnel_no_full3d_closure"
        )
        hybrid_evidence = (
            hybrid.get("summary_path")
            or hybrid.get("watchdog_record_path")
        )
        hybrid_row = _blank(
            case_key=f"supplemental_p{degree}_h{h_nm:g}_hybrid_m160",
            p=degree, h_nm=h_nm, method="Hybrid",
            M_per_direction=160, MPI=mpi, polarization="s",
            status=hybrid_status,
            data_identity="measured_watchdog_outcome",
            source_sha=hybrid.get("source_sha") or payload.get("source_sha"),
            R_total=hybrid.get("R_total", hybrid.get("R")),
            T_total=hybrid.get("T_total", hybrid.get("T")),
            A_balance=hybrid.get("A_balance"),
            A_volume=hybrid.get("A_volume_total", hybrid.get("A_volume")),
            true_relative_residual=hybrid.get("true_relative_residual"),
            total_seconds=(
                hybrid.get("elapsed_seconds")
                or hybrid.get("wall_time_limit_seconds")
            ),
            peak_memory_gib=hybrid.get("peak_memory_gib"),
            swap_bytes=0,
            full3d_hybrid_closure_status="not_available",
            evidence_path=_normalize_evidence_path(root, hybrid_evidence),
        )
        if degree != 2:
            _apply_descriptor(
                hybrid_row,
                _descriptor_details(root, hybrid_evidence),
            )
        rows.append(hybrid_row)
    return rows


def build(root: Path) -> dict[str, Any]:
    case093_path = root / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json"
    mpi_path = root / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/mpi_identity_summary.json"
    p4_path = root / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p4_h5_workstation_summary.json"
    case093, mpi, p4 = map(_load, (case093_path, mpi_path, p4_path))
    rows = _case093_rows(root, case093)
    rows.extend(_m_rows(root, case093, p4))
    rows.extend(_mpi_rows(root, mpi, case093))
    rows.extend(_supplemental_rows(root))
    if any(set(row) != set(COLUMNS) for row in rows):
        raise ValueError("row schema mismatch")
    return {
        "schema_version": "task034.all-model-results.v1",
        "record_type": "accepted_measured_and_formal_not_run_fact_table",
        "identity": {
            "is_pde_run": False,
            "polarization_mainline": "s",
            "R00_p_semantics": "cross-polarized p output under S incidence",
            "p_incidence_rerun_required": False,
            "null_means": "not available in accepted evidence; never imputed",
        },
        "columns": COLUMNS,
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.root.resolve())
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with args.csv_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["rows"])
    print(json.dumps({"row_count": result["row_count"]}, indent=2))


if __name__ == "__main__":
    main()
