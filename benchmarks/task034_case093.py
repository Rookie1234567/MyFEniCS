"""Build and independently check the compact Task034 Case093 benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TRUE_RESIDUAL_MAX = 1.0e-9
SIGNIFICANT_ORDER_POWER = 1.0e-8
REQUIRED_MPI_SIZES = (1, 8, 16)
EXPLORATORY_MPI_SIZES = (32,)
PHYSICAL_KEYS = (
    "stage_case",
    "geometry_kind",
    "lambda0",
    "period_x",
    "period_y",
    "z_min",
    "z_max",
    "substrate_thickness",
    "grating_height",
    "grating_width_x",
    "grating_width_y",
    "n_substrate",
    "n_grating",
    "incident_theta_deg",
    "incident_phi_deg",
    "polarization_kind",
    "stage4_boundary_model",
    "stage4_dtn_order_policy",
    "stage4_dtn_assembly",
    "full3d_reference_plane_z",
    "full3d_reference_sample_count_x",
    "full3d_reference_sample_count_y",
)
VECTOR_KEYS = (
    "R_total_absolute_delta",
    "T_total_absolute_delta",
    "A_balance_absolute_delta",
    "A_volume_total_absolute_delta",
    "five_plane_E_max_relative_l2",
    "five_plane_H_max_relative_l2",
    "interface_E_t_max_relative_l2",
    "interface_H_t_max_relative_l2",
    "significant_order_power_relative_error_max",
    "significant_order_power_relative_error_rms",
    "significant_order_complex_amplitude_relative_error_max",
    "significant_order_complex_amplitude_relative_error_rms",
)


class Case093Error(ValueError):
    """Raised when Case093 evidence is incomplete or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Case093Error(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Case093Error(f"JSON root must be an object: {path}")
    return payload


def _finite(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise Case093Error(f"{label} must be finite")
    return float(value)


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _source(record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("source")
    if not isinstance(source, Mapping):
        raise Case093Error("source identity missing")
    sha = source.get("verified_clean_sha", source.get("commit_sha"))
    if not isinstance(sha, str) or len(sha) != 40:
        raise Case093Error("clean full source SHA missing")
    clean = source.get("source_clean_verified", True) is True
    stable = source.get("source_stable_during_run", True) is True
    return {"commit_sha": sha, "clean": clean, "stable": stable}


def _physical_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in PHYSICAL_KEYS if key not in config]
    if missing:
        raise Case093Error("physical identity fields missing: " + ",".join(missing))
    return {key: config[key] for key in PHYSICAL_KEYS}


def _order_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    try:
        return (
            str(row["side"]),
            int(row.get("order_m", row.get("m"))),
            int(row.get("order_n", row.get("n"))),
            str(row["polarization"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise Case093Error("invalid diffraction-order row") from exc


def _order_map(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for row in rows:
        key = _order_key(row)
        if key in result:
            raise Case093Error(f"duplicate diffraction order {key}")
        result[key] = row
    if not result:
        raise Case093Error("diffraction orders are empty")
    return result


def _complex_pair(value: Any, label: str) -> complex:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise Case093Error(f"{label} must be [real,imag]")
    return complex(_finite(value[0], label), _finite(value[1], label))


def _order_error(
    first: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    second: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
) -> dict[str, Any]:
    if set(first) != set(second):
        raise Case093Error("diffraction-order coverage differs")
    powers: list[float] = []
    amplitudes: list[float] = []
    for key in sorted(first):
        left = first[key]
        right = second[key]
        a = abs(_finite(left.get("power_ratio"), f"{key}.power"))
        b = abs(_finite(right.get("power_ratio"), f"{key}.power"))
        if max(a, b) < SIGNIFICANT_ORDER_POWER:
            continue
        powers.append(abs(b - a) / max(a, b, SIGNIFICANT_ORDER_POWER))
        ca = _complex_pair(left.get("outgoing_amplitude_at_boundary"), f"{key}.amplitude")
        cb = _complex_pair(right.get("outgoing_amplitude_at_boundary"), f"{key}.amplitude")
        amplitudes.append(abs(cb - ca) / max(abs(ca), abs(cb), 1.0e-15))
    if not powers:
        raise Case093Error("no significant diffraction order")
    return {
        "significant_order_count": len(powers),
        "power_relative_error_max": max(powers),
        "power_relative_error_rms": math.sqrt(sum(v * v for v in powers) / len(powers)),
        "complex_amplitude_relative_error_max": max(amplitudes),
        "complex_amplitude_relative_error_rms": math.sqrt(
            sum(v * v for v in amplitudes) / len(amplitudes)
        ),
    }


def _relative_l2(candidate: np.ndarray, reference: np.ndarray) -> float:
    scale = float(np.linalg.norm(reference.reshape(-1)))
    if not scale > 0.0:
        raise Case093Error("reference field norm is zero")
    return float(np.linalg.norm((candidate - reference).reshape(-1)) / scale)


def _load_full3d(path_value: str | Path) -> dict[str, Any]:
    path = _resolve(path_value)
    record = _read_json(path)
    summary = record.get("solver_summary")
    qualification = record.get("qualification")
    raw = record.get("raw_evidence")
    if not all(isinstance(v, Mapping) for v in (summary, qualification, raw)):
        raise Case093Error(f"incomplete Full3D record: {path}")
    config = summary.get("config")
    if not isinstance(config, Mapping):
        raise Case093Error(f"Full3D config missing: {path}")
    archive = _resolve(str(summary.get("full3d_reference_archive")))
    expected_archive_sha = summary.get("full3d_reference_archive_sha256")
    if not archive.is_file() or _sha256(archive) != expected_archive_sha:
        raise Case093Error(f"Full3D field archive hash mismatch: {path}")
    run_directory = _resolve(str(raw.get("run_directory")))
    orders_path = run_directory / str(summary.get("dtn_port_orders_json"))
    orders_payload = _read_json(orders_path)
    rows = orders_payload.get("orders")
    if not isinstance(rows, list):
        raise Case093Error(f"Full3D orders missing: {path}")
    arrays = np.load(archive)
    required_arrays = {
        "x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m",
        "interface_z_nm", "E_t_interface_V_per_m", "H_t_interface_A_per_m",
    }
    if set(arrays.files) != required_arrays:
        raise Case093Error(f"Full3D field vector incomplete: {path}")
    source = _source(record)
    residual = _finite(summary.get("linear_system_relative_residual"), "Full3D residual")
    values = {
        "R_total": _finite(summary.get("R_total"), "R_total"),
        "T_total": _finite(summary.get("T_total"), "T_total"),
        "A_volume_total": _finite(summary.get("A_volume_total"), "A_volume_total"),
    }
    values["A_balance"] = 1.0 - values["R_total"] - values["T_total"]
    passed = (
        record.get("status") == "full3d_reference_pass"
        and summary.get("official_result") is True
        and qualification.get("pass") is True
        and record.get("no_swap") is True
        and residual <= TRUE_RESIDUAL_MAX
        and source["clean"]
        and source["stable"]
    )
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, Mapping) else {}
    return {
        "path": _repo_path(path),
        "sha256": _sha256(path),
        "record": record,
        "summary": summary,
        "arrays": arrays,
        "orders": _order_map(rows),
        "degree": int(record.get("degree")),
        "h_nm": _finite(record.get("h_nm"), "h_nm"),
        "mpi_size": int(record.get("mpi_size")),
        "source": source,
        "physical_identity": _physical_identity(config),
        "values": values,
        "residual": residual,
        "qualified": passed,
        "resource": {
            "peak_memory_gib": (record.get("resource_authority") or {}).get("memory_authority_gib"),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "dofs": summary.get("num_nedelec_dofs"),
            "rows": matrix.get("matrix_rows"),
            "nnz": matrix.get("matrix_nnz_used"),
            "no_swap": record.get("no_swap"),
        },
    }


def _load_hybrid(path_value: str | Path) -> dict[str, Any]:
    path = _resolve(path_value)
    record = _read_json(path)
    measurements = record.get("measurements")
    if not isinstance(measurements, Mapping):
        raise Case093Error(f"Hybrid measurements missing: {path}")
    case = measurements.get("case")
    solve = measurements.get("solve")
    validation = measurements.get("validation")
    reconstruction = measurements.get("physical_field_reconstruction")
    gates = measurements.get("gates")
    if not all(isinstance(v, Mapping) for v in (case, solve, validation, reconstruction, gates)):
        raise Case093Error(f"Hybrid observable vector incomplete: {path}")
    port = validation.get("port_power")
    volume = reconstruction.get("volume_absorption")
    planes = reconstruction.get("selected_plane_full3d_comparison")
    if not all(isinstance(v, Mapping) for v in (port, volume, planes)):
        raise Case093Error(f"Hybrid physical reconstruction incomplete: {path}")
    plane_rows = planes.get("planes")
    orders = validation.get("external_diffraction_orders")
    if not isinstance(plane_rows, list) or len(plane_rows) != 5 or not isinstance(orders, list):
        raise Case093Error(f"Hybrid five-plane/order vector incomplete: {path}")
    source = _source(record)
    residual = _finite(solve.get("true_relative_residual"), "Hybrid residual")
    values = {
        "R_total": _finite(port.get("R_total"), "Hybrid R_total"),
        "T_total": _finite(port.get("T_total"), "Hybrid T_total"),
        "A_volume_total": _finite(volume.get("A_volume_total"), "Hybrid A_volume_total"),
    }
    values["A_balance"] = 1.0 - values["R_total"] - values["T_total"]
    all_gates = bool(gates) and all(value is True for value in gates.values())
    qualified = (
        record.get("status") == "measured_shard_pass"
        and record.get("formal_pass") is True
        and record.get("numeric_pass") is True
        and record.get("no_swap") is True
        and int(record.get("requested_modes")) == 160
        and residual <= TRUE_RESIDUAL_MAX
        and all_gates
        and source["clean"]
        and source["stable"]
    )
    return {
        "path": _repo_path(path),
        "sha256": _sha256(path),
        "record": record,
        "measurements": measurements,
        "planes": plane_rows,
        "orders": _order_map(orders),
        "degree": int(case.get("degree")),
        "h_nm": _finite(case.get("h_nm"), "Hybrid h_nm"),
        "mpi_size": int((record.get("worker_source") or {}).get("mpi_size")),
        "source": source,
        "values": values,
        "residual": residual,
        "qualified": qualified,
        "all_measurement_gates_pass": all_gates,
        "resource": {
            "peak_memory_gib": (record.get("resource_authority") or {}).get("memory_authority_gib"),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "requested_modes": record.get("requested_modes"),
            "no_swap": record.get("no_swap"),
        },
    }


def _pair_vector(coarse: Mapping[str, Any], fine: Mapping[str, Any]) -> dict[str, float]:
    a = coarse["arrays"]
    b = fine["arrays"]
    for coordinate in ("x_nm", "y_nm", "z_nm", "interface_z_nm"):
        if not np.array_equal(a[coordinate], b[coordinate]):
            raise Case093Error(f"sampling coordinate differs: {coordinate}")
    planes_e = [_relative_l2(a["E_V_per_m"][i], b["E_V_per_m"][i]) for i in range(5)]
    planes_h = [_relative_l2(a["H_A_per_m"][i], b["H_A_per_m"][i]) for i in range(5)]
    interface_e = [_relative_l2(a["E_t_interface_V_per_m"][i], b["E_t_interface_V_per_m"][i]) for i in range(2)]
    interface_h = [_relative_l2(a["H_t_interface_A_per_m"][i], b["H_t_interface_A_per_m"][i]) for i in range(2)]
    orders = _order_error(coarse["orders"], fine["orders"])
    return {
        "R_total_absolute_delta": abs(coarse["values"]["R_total"] - fine["values"]["R_total"]),
        "T_total_absolute_delta": abs(coarse["values"]["T_total"] - fine["values"]["T_total"]),
        "A_balance_absolute_delta": abs(coarse["values"]["A_balance"] - fine["values"]["A_balance"]),
        "A_volume_total_absolute_delta": abs(coarse["values"]["A_volume_total"] - fine["values"]["A_volume_total"]),
        "five_plane_E_max_relative_l2": max(planes_e),
        "five_plane_H_max_relative_l2": max(planes_h),
        "interface_E_t_max_relative_l2": max(interface_e),
        "interface_H_t_max_relative_l2": max(interface_h),
        "significant_order_power_relative_error_max": orders["power_relative_error_max"],
        "significant_order_power_relative_error_rms": orders["power_relative_error_rms"],
        "significant_order_complex_amplitude_relative_error_max": orders["complex_amplitude_relative_error_max"],
        "significant_order_complex_amplitude_relative_error_rms": orders["complex_amplitude_relative_error_rms"],
    }


def _funnel_qualified(path_value: str | Path | None) -> tuple[dict[str, Any], bool]:
    if path_value is None:
        return {
            "path": None,
            "sha256": None,
            "status": "not_available_preserved_negative",
            "selected_mode_count_per_direction": None,
        }, False
    path = _resolve(path_value)
    record = _read_json(path)
    qualification = record.get("qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    selected = qualification.get("selected_mode_count_per_direction")
    passed = (
        record.get("status") == "qualified"
        and qualification.get("mode_count_converged") is True
        and selected == 160
    )
    return {
        "path": _repo_path(path),
        "sha256": _sha256(path),
        "status": record.get("status"),
        "selected_mode_count_per_direction": selected,
    }, passed


def _closure(
    full: Mapping[str, Any],
    hybrid: Mapping[str, Any],
    funnel_path: str | Path | None,
) -> dict[str, Any]:
    funnel, funnel_pass = _funnel_qualified(funnel_path)
    planes = hybrid["planes"]
    reconstruction = hybrid["measurements"]["physical_field_reconstruction"]
    comparison = reconstruction["selected_plane_full3d_comparison"]
    binding_pass = (
        comparison.get("reference_binding_verified") is True
        and comparison.get("reference_record_sha256") == full["sha256"]
    )
    orders = _order_error(full["orders"], hybrid["orders"])
    vector = {
        "R_total_absolute_delta": abs(full["values"]["R_total"] - hybrid["values"]["R_total"]),
        "T_total_absolute_delta": abs(full["values"]["T_total"] - hybrid["values"]["T_total"]),
        "A_balance_absolute_delta": abs(full["values"]["A_balance"] - hybrid["values"]["A_balance"]),
        "A_volume_total_absolute_delta": abs(full["values"]["A_volume_total"] - hybrid["values"]["A_volume_total"]),
        "five_plane_E_max_relative_l2": max(_finite(row["electric"]["relative_l2"], "plane E") for row in planes),
        "five_plane_H_max_relative_l2": max(_finite(row["magnetic"]["relative_l2"], "plane H") for row in planes),
        "interface_E_t_max_relative_l2": max(_finite(row["electric_tangential"]["relative_l2"], "interface E") for row in (planes[0], planes[-1])),
        "interface_H_t_max_relative_l2": max(_finite(row["magnetic_tangential"]["relative_l2"], "interface H") for row in (planes[0], planes[-1])),
        "significant_order_power_relative_error_max": orders["power_relative_error_max"],
        "significant_order_power_relative_error_rms": orders["power_relative_error_rms"],
        "significant_order_complex_amplitude_relative_error_max": orders["complex_amplitude_relative_error_max"],
        "significant_order_complex_amplitude_relative_error_rms": orders["complex_amplitude_relative_error_rms"],
    }
    passed = (
        full["qualified"]
        and hybrid["qualified"]
        and funnel_pass
        and binding_pass
        and full["degree"] == hybrid["degree"]
        and math.isclose(full["h_nm"], hybrid["h_nm"], abs_tol=1.0e-12)
        and full["mpi_size"] == hybrid["mpi_size"] == 8
    )
    return {
        "status": "same_degree_closure_pass" if passed else "same_degree_closure_not_qualified",
        "pass": passed,
        "funnel": funnel,
        "full3d_reference_binding_verified": binding_pass,
        "observable_vector": vector,
    }


def _compact_point(item: Mapping[str, Any]) -> dict[str, Any]:
    if item["method"] == "full3d":
        polarization = item["physical_identity"]["polarization_kind"]
    else:
        polarization = item["measurements"]["case"]["polarization_kind"]
    return {
        "method": item["method"],
        "degree": item["degree"],
        "h_nm": item["h_nm"],
        "polarization_kind": polarization,
        "mpi_size": item["mpi_size"],
        "status": item["status"],
        "qualified": item["qualified"],
        "source": item["source"],
        "true_relative_residual": item["residual"],
        "official_values": item["values"],
        "resource": item["resource"],
        "evidence": {"path": item["path"], "sha256": item["sha256"]},
    }


def _degree_decision(degree: int, points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    successful = sorted(
        [
            p
            for p in points
            if p["full"]["degree"] == degree
            and p["full"]["qualified"]
            and p["closure"]["pass"]
        ],
        key=lambda p: p["full"]["h_nm"],
        reverse=True,
    )
    decision: dict[str, Any] = {
        "degree": degree,
        "successful_same_degree_points": [p["key"] for p in successful],
        "successful_count": len(successful),
        "measured_sequence_decision": len(successful) >= 3,
        "observed_convergence_order_status": "convergence_order_not_established",
        "grid_convergence_proven": False,
    }
    if len(successful) >= 3:
        triple = successful[-3:]
        coarse_mid = _pair_vector(triple[0]["full"], triple[1]["full"])
        mid_fine = _pair_vector(triple[1]["full"], triple[2]["full"])
        reductions = {
            key: mid_fine[key] < coarse_mid[key]
            for key in VECTOR_KEYS
        }
        decision["three_finest_points"] = [p["key"] for p in triple]
        decision["coarse_to_middle_delta"] = coarse_mid
        decision["middle_to_fine_delta"] = mid_fine
        decision["componentwise_delta_reduction"] = reductions
        decision["all_twelve_components_reduce"] = all(reductions.values())
        decision["order_not_reported_reason"] = (
            "best_available reference is still discrete and the full vector is not declared asymptotic"
        )
    return decision


def _validate_compact_convergence(record: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if record.get("schema_version") != "task034.case093.convergence.v1":
        failures.append("convergence_schema")
    identity = record.get("physical_identity")
    if not isinstance(identity, Mapping) or identity.get("polarization_kind") != "s":
        failures.append("physical_identity_s")
    points = record.get("points")
    if not isinstance(points, list) or not points:
        return [*failures, "points_missing"]
    keys = set()
    recomputed: dict[int, list[str]] = {2: [], 3: [], 4: []}
    for point in points:
        if not isinstance(point, Mapping):
            failures.append("point_not_object")
            continue
        key = point.get("key")
        if key in keys:
            failures.append("duplicate_point")
        keys.add(key)
        for method in ("full3d", "hybrid"):
            row = point.get(method)
            if not isinstance(row, Mapping):
                failures.append(f"{key}_{method}_missing")
                continue
            if row.get("method") != method:
                failures.append(f"{key}_{method}_identity")
            if row.get("polarization_kind") != identity.get("polarization_kind"):
                failures.append(f"{key}_{method}_polarization")
            residual = row.get("true_relative_residual")
            if row.get("qualified") is True and (
                not isinstance(residual, (int, float)) or residual > TRUE_RESIDUAL_MAX
            ):
                failures.append(f"{key}_{method}_residual")
        full = point.get("full3d")
        hybrid = point.get("hybrid")
        closure = point.get("same_degree_closure")
        if not isinstance(closure, Mapping):
            failures.append(f"{key}_closure_missing")
        elif closure.get("pass") is True:
            if not isinstance(full, Mapping) or not isinstance(hybrid, Mapping):
                failures.append(f"{key}_closure_methods")
            elif (
                full.get("degree") != hybrid.get("degree")
                or full.get("h_nm") != hybrid.get("h_nm")
                or full.get("mpi_size") != hybrid.get("mpi_size")
            ):
                failures.append(f"{key}_same_degree_identity")
            elif full.get("qualified") is True and hybrid.get("qualified") is True:
                degree = full.get("degree")
                if degree in recomputed:
                    recomputed[degree].append(str(key))
            vector = closure.get("observable_vector")
            if not isinstance(vector, Mapping) or set(vector) != set(VECTOR_KEYS):
                failures.append(f"{key}_closure_vector")
    decisions = record.get("degree_decisions")
    if not isinstance(decisions, list) or {row.get("degree") for row in decisions if isinstance(row, Mapping)} != {2, 3, 4}:
        failures.append("degree_decisions")
    else:
        for row in decisions:
            degree = row.get("degree")
            expected_keys = recomputed.get(degree, [])
            reported_keys = row.get("successful_same_degree_points")
            if not isinstance(reported_keys, list) or set(reported_keys) != set(expected_keys):
                failures.append(f"p{degree}_successful_points_recompute")
            if row.get("successful_count") != len(expected_keys):
                failures.append(f"p{degree}_successful_count_recompute")
            if row.get("measured_sequence_decision") is not (len(expected_keys) >= 3):
                failures.append(f"p{degree}_decision_recompute")
            if row.get("observed_convergence_order_status") != "convergence_order_not_established":
                failures.append(f"p{degree}_order_overclaim")
            reductions = row.get("componentwise_delta_reduction")
            coarse_middle = row.get("coarse_to_middle_delta")
            middle_fine = row.get("middle_to_fine_delta")
            if len(expected_keys) >= 3 and (
                not isinstance(reductions, Mapping)
                or set(reductions) != set(VECTOR_KEYS)
                or not isinstance(coarse_middle, Mapping)
                or set(coarse_middle) != set(VECTOR_KEYS)
                or not isinstance(middle_fine, Mapping)
                or set(middle_fine) != set(VECTOR_KEYS)
            ):
                failures.append(f"p{degree}_reduction_recompute")
            elif len(expected_keys) >= 3:
                expected_reductions = {
                    key: middle_fine[key] < coarse_middle[key]
                    for key in VECTOR_KEYS
                }
                if dict(reductions) != expected_reductions or (
                    row.get("all_twelve_components_reduce")
                    is not all(expected_reductions.values())
                ):
                    failures.append(f"p{degree}_reduction_recompute")
    reference = record.get("selected_discrete_reference")
    if not isinstance(reference, Mapping) or reference.get("key") != "p4_h5" or reference.get("continuum_reference") is not False:
        failures.append("reference_identity")
    return failures


def _validate_compact_mpi(record: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if record.get("schema_version") != "task034.case093.mpi-identity.v1":
        failures.append("mpi_schema")
    if record.get("required_mpi_sizes") != list(REQUIRED_MPI_SIZES):
        failures.append("required_mpi_sizes")
    if record.get("exploratory_mpi_sizes") != list(EXPLORATORY_MPI_SIZES):
        failures.append("exploratory_mpi_sizes")
    methods = record.get("methods")
    if not isinstance(methods, Mapping) or set(methods) != {"full3d", "hybrid"}:
        return [*failures, "mpi_methods"]
    for name, method in methods.items():
        if not isinstance(method, Mapping) or method.get("status") != "qualified":
            failures.append(f"{name}_not_qualified")
            continue
        method_checks = method.get("checks")
        if not isinstance(method_checks, Mapping) or not method_checks or not all(
            value is True for value in method_checks.values()
        ):
            failures.append(f"{name}_global_checks")
        rows = method.get("comparisons")
        by_size = {row.get("mpi_size"): row for row in rows if isinstance(row, Mapping)} if isinstance(rows, list) else {}
        if not all(size in by_size for size in (*REQUIRED_MPI_SIZES, *EXPLORATORY_MPI_SIZES)):
            failures.append(f"{name}_sizes")
        for size in REQUIRED_MPI_SIZES:
            checks = by_size.get(size, {}).get("checks")
            if not isinstance(checks, Mapping) or not checks or not all(value is True for value in checks.values()):
                failures.append(f"{name}_mpi{size}_identity")
    return failures


def build_case093(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_file = _resolve(config_path)
    config = _read_json(config_file)
    matrix = config.get("matrix")
    if not isinstance(matrix, list) or not matrix:
        raise Case093Error("Case093 matrix is empty")
    loaded: list[dict[str, Any]] = []
    physical_identity: dict[str, Any] | None = None
    for row in matrix:
        if not isinstance(row, Mapping):
            raise Case093Error("matrix row must be an object")
        full = _load_full3d(str(row["full3d_record"]))
        hybrid = _load_hybrid(str(row["hybrid_m160_record"]))
        if full["degree"] != int(row["degree"]) or not math.isclose(full["h_nm"], float(row["h_nm"]), abs_tol=1.0e-12):
            raise Case093Error(f"matrix identity mismatch: {row.get('key')}")
        if hybrid["degree"] != full["degree"] or not math.isclose(hybrid["h_nm"], full["h_nm"], abs_tol=1.0e-12):
            raise Case093Error(f"Hybrid identity mismatch: {row.get('key')}")
        if physical_identity is None:
            physical_identity = full["physical_identity"]
        elif full["physical_identity"] != physical_identity:
            raise Case093Error(f"mixed physical configuration: {row.get('key')}")
        funnel_value = row.get("funnel_record")
        closure = _closure(
            full,
            hybrid,
            None if funnel_value is None else str(funnel_value),
        )
        loaded.append({"key": row["key"], "full": full, "hybrid": hybrid, "closure": closure})
    assert physical_identity is not None
    decisions = [_degree_decision(p, loaded) for p in (2, 3, 4)]
    by_key = {row["key"]: row for row in loaded}
    anchors = {"p2": "p2_h2", "p3": "p3_h3", "p4": "p4_h5"}
    if any(key not in by_key or not by_key[key]["closure"]["pass"] for key in anchors.values()):
        raise Case093Error("canonical anchor closure missing")
    p_h5 = {
        f"p{p}_to_p4_h5": _pair_vector(by_key[f"p{p}_h5"]["full"], by_key["p4_h5"]["full"])
        for p in (2, 3)
    }
    evidence = []
    points = []
    for row in loaded:
        evidence.extend([
            {"role": f"{row['key']}_full3d", "path": row["full"]["path"], "sha256": row["full"]["sha256"]},
            {"role": f"{row['key']}_hybrid_m160", "path": row["hybrid"]["path"], "sha256": row["hybrid"]["sha256"]},
            {"role": f"{row['key']}_funnel", **row["closure"]["funnel"]},
        ])
        points.append({
            "key": row["key"],
            "full3d": _compact_point({**row["full"], "method": "full3d", "status": row["full"]["record"].get("status")}),
            "hybrid": _compact_point({**row["hybrid"], "method": "hybrid", "status": row["hybrid"]["record"].get("status")}),
            "same_degree_closure": row["closure"],
        })
    supplemental = []
    for path_value in config.get("supplemental_outcomes", []):
        path = _resolve(str(path_value))
        payload = _read_json(path)
        supplemental.append({
            "path": _repo_path(path), "sha256": _sha256(path),
            "matrix_key": payload.get("matrix_key"), "status": payload.get("status", payload.get("record_type")),
            "qualification": payload.get("qualification"),
        })
    convergence: dict[str, Any] = {
        "schema_version": "task034.case093.convergence.v1",
        "record_type": "fixed_geometry_ph_convergence_and_same_degree_closure",
        "status": "measured_decisions_complete",
        "physical_identity": physical_identity,
        "physical_identity_sha256": hashlib.sha256(json.dumps(physical_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "scope": {
            "primary_polarization": "s",
            "user_approved_reduced_scope": True,
            "p1_excluded": True,
            "p_capability_only": "p2/h5 MPI8 Full3D and Hybrid M160",
            "mpi_identity_representative_only": "p3/h5 S Full3D and Hybrid",
        },
        "points": points,
        "degree_decisions": decisions,
        "p_convergence_at_h5_against_p4_h5": p_h5,
        "selected_discrete_reference": {
            "key": "p4_h5",
            "identity": "best_available_discrete_reference_for_case093",
            "grid_convergence_proven": False,
            "continuum_reference": False,
        },
        "canonical_anchors": anchors,
        "supplemental_user_added_points": supplemental,
        "heavy_evidence": evidence,
        "ordinary_default_changed": False,
    }
    convergence_failures = _validate_compact_convergence(convergence)
    if convergence_failures:
        raise Case093Error("generated convergence record invalid: " + ",".join(convergence_failures))

    mpi_methods: dict[str, Any] = {}
    for method, path_value in config.get("mpi_identity_records", {}).items():
        path = _resolve(str(path_value))
        payload = _read_json(path)
        comparisons = payload.get("comparisons")
        if payload.get("status") != "qualified" or not isinstance(comparisons, list):
            raise Case093Error(f"MPI identity is not qualified: {method}")
        compact_rows = [
            {"mpi_size": row.get("mpi_size"), "checks": row.get("checks"), "resource": row.get("resource"),
             "true_relative_residual": row.get("true_relative_residual"), "rta_drift": row.get("rta_drift"),
             "field_relative_l2_drift": row.get("field_relative_l2_drift"), "order_identity": row.get("order_identity")}
            for row in comparisons
        ]
        mpi_methods[method] = {
            "status": payload.get("status"), "identity": payload.get("identity"),
            "checks": payload.get("checks"),
            "comparisons": compact_rows,
            "evidence": {"path": _repo_path(path), "sha256": _sha256(path)},
        }
    mpi_record: dict[str, Any] = {
        "schema_version": "task034.case093.mpi-identity.v1",
        "record_type": "representative_full3d_hybrid_mpi_identity",
        "status": "qualified_user_approved_representative_scope",
        "anchor": "p3_h5_s",
        "required_mpi_sizes": list(REQUIRED_MPI_SIZES),
        "exploratory_mpi_sizes": list(EXPLORATORY_MPI_SIZES),
        "physical_core_count": 48,
        "methods": mpi_methods,
        "scope_note": "User approved one representative case; this closes rank-count expansion but is not a per-degree MPI matrix.",
        "ordinary_default_changed": False,
    }
    mpi_failures = _validate_compact_mpi(mpi_record)
    if mpi_failures:
        raise Case093Error("generated MPI record invalid: " + ",".join(mpi_failures))

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    convergence_path = output / "convergence_summary.json"
    mpi_path = output / "mpi_identity_summary.json"
    convergence_path.write_text(json.dumps(convergence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mpi_path.write_text(json.dumps(mpi_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short", "--untracked-files=all"], cwd=ROOT, text=True).strip()
    manifest = {
        "schema_version": "task034.case093.canonical-manifest.v1",
        "record_type": "case093_canonical_benchmark_manifest",
        "status": "canonical_partial_with_user_approved_reduced_scope",
        "case_id": "093_fixed_geometry_ph_convergence_mpi",
        "aggregation_source": {"commit_sha": head, "worktree_status_before_record_write": status},
        "compact_records": {
            "convergence_summary.json": _sha256(convergence_path),
            "mpi_identity_summary.json": _sha256(mpi_path),
        },
        "canonical_anchors": anchors,
        "selected_discrete_reference": "p4_h5",
        "adaptive_unlock": {
            "p2_uniform_measured_decision": decisions[0]["measured_sequence_decision"],
            "p3_uniform_measured_decision": decisions[1]["measured_sequence_decision"],
            "p4_same_degree_closure_or_controlled_negative": decisions[2]["measured_sequence_decision"],
            "selected_discrete_reference_frozen": True,
            "case093_observable_and_checker_available": True,
            "mpi8_production_baseline_selected": True,
        },
        "claims": {
            "canonical_compact_benchmark_available": True,
            "grid_convergence_proven": False,
            "continuum_reference": False,
            "full_addendum_polarization_and_per_degree_mpi_scope_complete": False,
            "user_approved_reduced_scope_complete": True,
            "ordinary_default_changed": False,
        },
    }
    manifest_path = output / "canonical_benchmark_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"convergence": convergence, "mpi": mpi_record, "manifest": manifest}


def check_case093(case_dir: str | Path) -> dict[str, Any]:
    directory = _resolve(case_dir)
    convergence_path = directory / "records/convergence_summary.json"
    mpi_path = directory / "records/mpi_identity_summary.json"
    manifest_path = directory / "records/canonical_benchmark_manifest.json"
    expected_path = directory / "expected.json"
    convergence = _read_json(convergence_path)
    mpi = _read_json(mpi_path)
    manifest = _read_json(manifest_path)
    expected = _read_json(expected_path)
    failures = [*_validate_compact_convergence(convergence), *_validate_compact_mpi(mpi)]
    compact = manifest.get("compact_records")
    if not isinstance(compact, Mapping):
        failures.append("manifest_compact_records")
    else:
        if compact.get("convergence_summary.json") != _sha256(convergence_path):
            failures.append("convergence_hash_binding")
        if compact.get("mpi_identity_summary.json") != _sha256(mpi_path):
            failures.append("mpi_hash_binding")
    unlock = manifest.get("adaptive_unlock")
    decisions = convergence.get("degree_decisions")
    decisions_by_degree = {
        row.get("degree"): row
        for row in decisions
        if isinstance(row, Mapping)
    } if isinstance(decisions, list) else {}
    expected_unlock = {
        "p2_uniform_measured_decision": decisions_by_degree.get(2, {}).get("measured_sequence_decision") is True,
        "p3_uniform_measured_decision": decisions_by_degree.get(3, {}).get("measured_sequence_decision") is True,
        "p4_same_degree_closure_or_controlled_negative": decisions_by_degree.get(4, {}).get("measured_sequence_decision") is True,
        "selected_discrete_reference_frozen": convergence.get("selected_discrete_reference", {}).get("key") == "p4_h5",
        "case093_observable_and_checker_available": True,
        "mpi8_production_baseline_selected": 8 in mpi.get("required_mpi_sizes", []),
    }
    if not isinstance(unlock, Mapping) or dict(unlock) != expected_unlock or not all(expected_unlock.values()):
        failures.append("adaptive_unlock")
    claims = manifest.get("claims")
    if not isinstance(claims, Mapping):
        failures.append("manifest_claims")
    else:
        if claims.get("grid_convergence_proven") is not False or claims.get("continuum_reference") is not False:
            failures.append("continuum_overclaim")
        if claims.get("ordinary_default_changed") is not False:
            failures.append("ordinary_default_changed")
    if manifest.get("status") != expected.get("expected_manifest_status"):
        failures.append("expected_manifest_status")
    if expected.get("required_mpi_sizes") != list(REQUIRED_MPI_SIZES):
        failures.append("expected_required_mpi_sizes")
    return {
        "schema_version": "task034.case093.check.v1",
        "status": "pass" if not failures else "fail",
        "formal_pass": not failures,
        "failures": failures,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--config", required=True)
    build.add_argument("--output-dir", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--case-dir", default="benchmarks/cases/093_fixed_geometry_ph_convergence_mpi")
    args = parser.parse_args(argv)
    if args.command == "build":
        result = build_case093(args.config, args.output_dir)
        print(json.dumps({"status": result["manifest"]["status"]}, ensure_ascii=False))
        return 0
    result = check_case093(args.case_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["formal_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Case093Error", "build_case093", "check_case093"]
