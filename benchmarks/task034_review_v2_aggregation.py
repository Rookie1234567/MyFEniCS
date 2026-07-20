"""Aggregate accepted Task034 evidence; never launches a PDE solve."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


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


def _first(value: Any, names: Iterable[str]) -> Any:
    wanted = set(names)
    if isinstance(value, Mapping):
        for name in wanted:
            if name in value and value[name] is not None:
                return value[name]
        for child in value.values():
            found = _first(child, wanted)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first(child, wanted)
            if found is not None:
                return found
    return None


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


def _orders(payload: Mapping[str, Any], evidence_path: Path) -> list[Mapping[str, Any]]:
    embedded = _first(payload, ("external_diffraction_orders", "orders"))
    if isinstance(embedded, list):
        return [row for row in embedded if isinstance(row, Mapping)]
    run_dir = None
    command = payload.get("command")
    if isinstance(command, list) and "--run-dir" in command:
        run_dir = Path(command[command.index("--run-dir") + 1])
    filename = _first(payload, ("dtn_port_orders_json", "diffraction_orders_json"))
    if run_dir is not None and isinstance(filename, str):
        path = run_dir / filename
        if path.exists():
            external = _load(path)
            rows = external.get("orders")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, Mapping)]
    return []


def _zero_orders(payload: Mapping[str, Any], evidence_path: Path) -> dict[str, float | None]:
    result: dict[str, float | None] = {
        "R00_s": None, "R00_p": None, "R00_total": None,
        "T00_s": None, "T00_p": None, "T00_total": None,
    }
    for order in _orders(payload, evidence_path):
        if int(order.get("m", order.get("order_m", 999))) != 0:
            continue
        if int(order.get("n", order.get("order_n", 999))) != 0:
            continue
        side = str(order.get("side", "")).lower()
        pol = str(order.get("polarization", order.get("polarization_kind", ""))).lower()
        power = _finite(order.get("power_ratio"))
        if power is None or pol not in {"s", "p"}:
            continue
        prefix = "R" if side == "top" else "T" if side == "bottom" else ""
        if prefix:
            result[f"{prefix}00_{pol}"] = power
    for prefix in ("R", "T"):
        values = [result[f"{prefix}00_s"], result[f"{prefix}00_p"]]
        if any(value is not None for value in values):
            result[f"{prefix}00_total"] = sum(value or 0.0 for value in values)
    return result


def _descriptor_details(root: Path, evidence: str | None) -> dict[str, Any]:
    if not evidence:
        return {}
    path = Path(evidence)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return {}
    payload = _load(path)
    calibration = _mapping(payload.get("calibration"))
    measurements = _mapping(payload.get("measurements"))
    system = _mapping(measurements.get("hybrid_system"))
    solver = _mapping(payload.get("solver_summary"))
    resource = _mapping(payload.get("resource_authority"))
    memory = _mapping(payload.get("memory"))
    local_fe = None
    if system:
        local_fe = sum(
            int(_finite(system.get(name)) or 0)
            for name in ("bottom_local_fe_dofs", "top_local_fe_dofs")
        )
    rows = _finite(calibration.get("exact_rows"))
    if rows is None and system:
        rows = sum(
            int(_finite(system.get(name)) or 0)
            for name in ("bottom_global_size", "top_global_size", "internal_unknown_count")
        )
    details = {
        "elements": _product(solver.get("num_mesh_cells")),
        "fe_dofs": int(_finite(calibration.get("num_nedelec_dofs")) or local_fe or 0) or None,
        "external_aux_dofs": int(_finite(calibration.get("num_auxiliary_dofs")) or 0) or None,
        "modal_unknowns": int(_finite(system.get("internal_unknown_count")) or 0) or None,
        "total_rows": int(rows) if rows is not None else None,
        "assembled_nnz": _finite(calibration.get("exact_assembled_nnz")),
        "factor_nnz": _finite(_first(payload, ("factor_nnz", "matrix_nnz_used"))),
        "assembly_seconds": _finite(_first(payload, ("base_matrix_assembly_seconds", "stage4_dtn_base_matrix_assembly_seconds"))),
        "factorization_seconds": _finite(_first(payload, ("ksp_setup_seconds",))),
        "solve_seconds": _finite(_first(payload, ("ksp_solve_seconds", "stage4_dtn_linear_solve_seconds"))),
        "total_seconds": _finite(_first(payload, ("elapsed_seconds", "wall_time_seconds"))),
        "peak_memory_gib": _finite(resource.get("memory_authority_gib"))
        or _finite(memory.get("max_simultaneous_worker_rss_gib")),
        "swap_bytes": 0 if payload.get("no_swap") is True else None,
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
                M_per_direction=resource.get("requested_modes") if method_name == "hybrid" else None,
                MPI=record.get("mpi_size"), polarization=record.get("polarization_kind"),
                status=record.get("status"), data_identity="measured_case093",
                source_sha=_mapping(record.get("source")).get("commit_sha"),
                total_rows=resource.get("rows"), assembled_nnz=resource.get("nnz"),
                fe_dofs=resource.get("dofs"), R_total=official.get("R_total"),
                T_total=official.get("T_total"), A_balance=official.get("A_balance"),
                A_volume=official.get("A_volume_total"),
                true_relative_residual=record.get("true_relative_residual"),
                total_seconds=resource.get("elapsed_seconds"),
                peak_memory_gib=resource.get("peak_memory_gib"),
                swap_bytes=0 if resource.get("no_swap") is True else None,
                full3d_hybrid_closure_status=closure, evidence_path=evidence,
            )
            row.update({key: value for key, value in _descriptor_details(root, evidence).items() if value is not None and row.get(key) is None})
            rows.append(row)
    return rows


def _mpi_rows(root: Path, summary: Mapping[str, Any], case093: Mapping[str, Any]) -> list[dict[str, Any]]:
    anchors = {point["key"]: point for point in case093.get("points", [])}
    anchor = _mapping(anchors["p3_h5"])
    rows = []
    for method_key, method in _mapping(summary.get("methods")).items():
        identity = _mapping(method.get("identity"))
        structure = _mapping(identity.get("structural"))
        official = _mapping(_mapping(anchor.get(method_key)).get("official_values"))
        for comparison in method.get("comparisons", []):
            mpi = comparison.get("mpi_size")
            resource = _mapping(comparison.get("resource"))
            timings = _mapping(resource.get("timings_seconds"))
            rows.append(_blank(
                case_key=f"mpi_p3_h5_{method_key}_mpi{mpi}", p=3, h_nm=5.0,
                method="Full3D" if method_key == "full3d" else "Hybrid",
                M_per_direction=structure.get("requested_modes") if method_key == "hybrid" else None,
                MPI=mpi, polarization="s", status="mpi_identity_pass",
                data_identity="measured_mpi_identity", source_sha=identity.get("source_sha"),
                elements=_product(structure.get("mesh_cells")),
                fe_dofs=structure.get("num_nedelec_dofs"),
                external_aux_dofs=structure.get("propagating_orders"),
                modal_unknowns=(2 * int(structure["requested_modes"])) if structure.get("requested_modes") else None,
                total_rows=structure.get("matrix_rows"), assembled_nnz=structure.get("matrix_nnz"),
                R_total=official.get("R_total"), T_total=official.get("T_total"),
                A_balance=official.get("A_balance"), A_volume=official.get("A_volume_total"),
                true_relative_residual=comparison.get("true_relative_residual"),
                total_seconds=timings.get("total") or timings.get("stage4_dtn_port_assembly_and_solve"),
                peak_memory_gib=resource.get("peak_memory_gib"), swap_bytes=0,
                full3d_hybrid_closure_status="representative_mpi_identity_pass",
                evidence_path=_mapping(method.get("evidence")).get("path"),
            ))
    return rows


def _m_rows(root: Path, p3: Mapping[str, Any], p4: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs = []
    funnel_path = _mapping(_mapping(p3.get("inputs")).get("p3_h3_hybrid_m160")).get("funnel_path")
    p3_funnel = _load(root / funnel_path)
    for source in p3_funnel.get("source_records", []):
        specs.append((3, 3.0, 4, source.get("mode_count_per_direction"), source.get("source_commit_full_sha"), source.get("path"), "p3_h3_m_funnel_pass"))
    hybrid_inputs = _mapping(_mapping(p4.get("input_evidence")).get("hybrid"))
    p4_source = _mapping(p4.get("source_compatibility")).get("audited_source_groups", [])[-1]["source_commit_full_sha"]
    for modes in (80, 120, 160):
        source = _mapping(hybrid_inputs.get(f"M{modes}"))
        specs.append((4, 5.0, 4, modes, p4_source, source.get("path"), "p4_h5_m_funnel_pass"))
    rows = []
    for degree, h_nm, mpi, modes, sha, evidence, status in specs:
        path = Path(evidence)
        if not path.is_absolute():
            path = root / path
        payload = _load(path)
        measurements = _mapping(payload.get("measurements"))
        solve = _mapping(measurements.get("solve"))
        timing = _mapping(measurements.get("timing_seconds_max_rank"))
        port_power = _mapping(_mapping(measurements.get("validation")).get("port_power"))
        official = {
            "R_total": port_power.get("R_total") or _first(payload, ("R_total", "R")),
            "T_total": port_power.get("T_total") or _first(payload, ("T_total", "T")),
            "A_balance": port_power.get("A_balance") or _first(payload, ("A_balance",)),
            "A_volume": _first(payload, ("A_volume_total", "A_volume")),
        }
        row = _blank(
            case_key=f"m_funnel_p{degree}_h{h_nm:g}_m{modes}", p=degree, h_nm=h_nm,
            method="Hybrid", M_per_direction=modes, MPI=mpi, polarization="s",
            status=status, data_identity="measured_mode_funnel", source_sha=sha,
            R_total=_finite(official["R_total"]), T_total=_finite(official["T_total"]),
            A_balance=_finite(official["A_balance"]), A_volume=_finite(official["A_volume"]),
            true_relative_residual=_finite(solve.get("true_relative_residual")),
            total_seconds=_finite(timing.get("total")),
            evidence_path=str(Path(evidence)), full3d_hybrid_closure_status="funnel_row",
        )
        row.update({key: value for key, value in _descriptor_details(root, str(Path(evidence))).items() if value is not None and row.get(key) is None})
        rows.append(row)
    return rows


def _supplemental_rows(root: Path) -> list[dict[str, Any]]:
    base = root / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records"
    rows = []
    for filename in ("p2_h1_execution_outcome.json", "p3_h2_execution_outcome.json", "p4_h3_execution_outcome.json"):
        payload = _load(base / filename)
        scope = _mapping(payload.get("case")) or _mapping(payload.get("scope"))
        degree, h_nm, mpi = scope.get("degree"), scope.get("h_nm"), scope.get("mpi_size")
        full = _mapping(payload.get("full3d"))
        full_evidence = full.get("assembly_watchdog_record_path") or full.get("assembly_record_path")
        rows.append(_blank(
            case_key=f"supplemental_p{degree}_h{h_nm:g}_full3d", p=degree, h_nm=h_nm,
            method="Full3D", MPI=mpi, polarization="s",
            status="not_run_by_conservative_resource_gate_after_assembly",
            data_identity="measured_assembly_and_predicted_factorization_upper_bound",
            source_sha=full.get("source_sha") or payload.get("source_sha"),
            total_rows=full.get("exact_rows"), assembled_nnz=full.get("exact_assembled_nnz"),
            assembly_seconds=full.get("assembly_elapsed_seconds"),
            peak_memory_gib=full.get("assembly_peak_memory_gib"), swap_bytes=0,
            full3d_hybrid_closure_status="not_available_factorization_launched_false_full_solve_launched_false",
            evidence_path=full_evidence,
        ))
        hybrid = _mapping(payload.get("hybrid_m160")) or _mapping(payload.get("hybrid"))
        if degree == 2:
            hybrid_status = "timeout_during_field_recovery_no_official_solution"
        else:
            hybrid_status = "measured_shard_pass_no_m_funnel_no_full3d_closure"
        rows.append(_blank(
            case_key=f"supplemental_p{degree}_h{h_nm:g}_hybrid_m160", p=degree, h_nm=h_nm,
            method="Hybrid", M_per_direction=160, MPI=mpi, polarization="s",
            status=hybrid_status, data_identity="measured_watchdog_outcome",
            source_sha=hybrid.get("source_sha") or payload.get("source_sha"),
            R_total=hybrid.get("R_total", hybrid.get("R")),
            T_total=hybrid.get("T_total", hybrid.get("T")),
            A_balance=hybrid.get("A_balance"),
            A_volume=hybrid.get("A_volume_total", hybrid.get("A_volume")),
            true_relative_residual=hybrid.get("true_relative_residual"),
            total_seconds=hybrid.get("elapsed_seconds") or hybrid.get("wall_time_limit_seconds"),
            peak_memory_gib=hybrid.get("peak_memory_gib"), swap_bytes=0,
            full3d_hybrid_closure_status="not_available",
            evidence_path=hybrid.get("summary_path") or hybrid.get("watchdog_record_path"),
        ))
    return rows


def build(root: Path) -> dict[str, Any]:
    case093_path = root / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json"
    mpi_path = root / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/mpi_identity_summary.json"
    p3_path = root / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p3_h3_reference_summary.json"
    p4_path = root / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p4_h5_workstation_summary.json"
    case093, mpi, p3, p4 = map(_load, (case093_path, mpi_path, p3_path, p4_path))
    rows = _case093_rows(root, case093)
    rows.extend(_m_rows(root, p3, p4))
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
