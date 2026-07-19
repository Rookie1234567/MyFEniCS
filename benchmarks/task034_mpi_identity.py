from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MPI_SIZES = (1, 8, 16)
RTA_ABSOLUTE_TOLERANCE = 1.0e-8
ORDER_POWER_ABSOLUTE_TOLERANCE = 1.0e-8
AMPLITUDE_RELATIVE_TOLERANCE = 1.0e-7
AMPLITUDE_PHASE_TOLERANCE_RAD = 1.0e-7
FIELD_RELATIVE_L2_TOLERANCE = 1.0e-6
BETA_RELATIVE_TOLERANCE = 1.0e-7
TRUE_RESIDUAL_TOLERANCE = 1.0e-9
SIGNIFICANT_ORDER_POWER = 1.0e-8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _complex(value: Any) -> complex | None:
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 2
    ):
        real = _finite(value[0])
        imag = _finite(value[1])
        if real is not None and imag is not None:
            return complex(real, imag)
    return None


def _source_sha(record: Mapping[str, Any]) -> str | None:
    source = record.get("source")
    source = source if isinstance(source, Mapping) else {}
    value = source.get("verified_clean_sha")
    return value if isinstance(value, str) and len(value) == 40 else None


def _load_orders(record: Mapping[str, Any], method: str) -> list[dict[str, Any]]:
    if method == "hybrid":
        measurements = record.get("measurements")
        measurements = measurements if isinstance(measurements, Mapping) else {}
        validation = measurements.get("validation")
        validation = validation if isinstance(validation, Mapping) else {}
        orders = validation.get("external_diffraction_orders")
    else:
        summary = record.get("solver_summary")
        summary = summary if isinstance(summary, Mapping) else {}
        raw = record.get("raw_evidence")
        raw = raw if isinstance(raw, Mapping) else {}
        run_dir = raw.get("run_directory")
        order_name = summary.get("dtn_port_orders_json")
        if not isinstance(run_dir, str) or not isinstance(order_name, str):
            return []
        path = Path(run_dir)
        if not path.is_absolute():
            path = ROOT / path
        path = path / order_name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        orders = payload.get("orders") if isinstance(payload, Mapping) else None
    return [dict(row) for row in orders] if isinstance(orders, list) else []


def _order_key(row: Mapping[str, Any]) -> tuple[str, int, int, str] | None:
    try:
        return (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _order_map(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for row in rows:
        key = _order_key(row)
        if key is not None:
            result[key] = row
    return result


def _phase_delta(first: complex, second: complex) -> float:
    return abs(
        math.atan2(
            math.sin(np.angle(second) - np.angle(first)),
            math.cos(np.angle(second) - np.angle(first)),
        )
    )


def _compare_orders(
    baseline: Sequence[Mapping[str, Any]], current: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    first = _order_map(baseline)
    second = _order_map(current)
    keys_equal = set(first) == set(second) and bool(first)
    max_power = 0.0
    max_amplitude_relative = 0.0
    max_phase = 0.0
    max_beta_relative = 0.0
    significant_count = 0
    for key in sorted(set(first) & set(second)):
        a = first[key]
        b = second[key]
        power_a = _finite(a.get("power_ratio"))
        power_b = _finite(b.get("power_ratio"))
        amp_a = _complex(a.get("outgoing_amplitude_at_boundary"))
        amp_b = _complex(b.get("outgoing_amplitude_at_boundary"))
        beta_a = _complex(a.get("beta_per_nm"))
        beta_b = _complex(b.get("beta_per_nm"))
        if None in (power_a, power_b, amp_a, amp_b, beta_a, beta_b):
            keys_equal = False
            continue
        max_power = max(max_power, abs(power_b - power_a))
        power_scale = max(abs(power_a), abs(power_b))
        if power_scale >= SIGNIFICANT_ORDER_POWER:
            significant_count += 1
            amplitude_scale = max(abs(amp_a), abs(amp_b), 1.0e-30)
            max_amplitude_relative = max(
                max_amplitude_relative, abs(amp_b - amp_a) / amplitude_scale
            )
            max_phase = max(max_phase, _phase_delta(amp_a, amp_b))
            beta_scale = max(abs(beta_a), abs(beta_b), 1.0e-30)
            max_beta_relative = max(
                max_beta_relative, abs(beta_b - beta_a) / beta_scale
            )
    checks = {
        "order_keys_identical": keys_equal,
        "significant_order_count_positive": significant_count > 0,
        "order_power_absolute_drift_le_1e-8": max_power
        <= ORDER_POWER_ABSOLUTE_TOLERANCE,
        "complex_amplitude_relative_drift_le_1e-7": max_amplitude_relative
        <= AMPLITUDE_RELATIVE_TOLERANCE,
        "complex_amplitude_phase_drift_le_1e-7_rad": max_phase
        <= AMPLITUDE_PHASE_TOLERANCE_RAD,
        "qep_beta_relative_drift_le_1e-7": max_beta_relative <= BETA_RELATIVE_TOLERANCE,
    }
    return {
        "checks": checks,
        "significant_order_power_threshold": SIGNIFICANT_ORDER_POWER,
        "significant_order_count": significant_count,
        "max_power_absolute_drift": max_power,
        "max_complex_amplitude_relative_drift": max_amplitude_relative,
        "max_complex_amplitude_phase_drift_rad": max_phase,
        "max_qep_beta_relative_drift": max_beta_relative,
    }


def _relative_l2(first: np.ndarray, second: np.ndarray) -> float:
    scale = max(
        float(np.linalg.norm(first.ravel())),
        float(np.linalg.norm(second.ravel())),
        1.0e-30,
    )
    return float(np.linalg.norm((second - first).ravel())) / scale


def _full3d_arrays(
    record: Mapping[str, Any],
) -> tuple[dict[str, np.ndarray], list[str]]:
    summary = record.get("solver_summary")
    summary = summary if isinstance(summary, Mapping) else {}
    path_value = summary.get("full3d_reference_archive")
    expected_sha = summary.get("full3d_reference_archive_sha256")
    failures: list[str] = []
    if not isinstance(path_value, str):
        return {}, ["full3d_reference_archive_path_missing"]
    path = Path(path_value)
    if not path.is_file():
        return {}, ["full3d_reference_archive_missing"]
    if not isinstance(expected_sha, str) or _sha256(path) != expected_sha:
        failures.append("full3d_reference_archive_sha256_mismatch")
    required = (
        "E_V_per_m",
        "H_A_per_m",
        "E_t_interface_V_per_m",
        "H_t_interface_A_per_m",
    )
    try:
        with np.load(path) as payload:
            arrays = {name: np.asarray(payload[name]) for name in required}
    except (OSError, KeyError, ValueError):
        return {}, [*failures, "full3d_reference_archive_unreadable"]
    return arrays, failures


def _hybrid_field_scalars(record: Mapping[str, Any]) -> dict[str, float]:
    measurements = record.get("measurements")
    measurements = measurements if isinstance(measurements, Mapping) else {}
    physical = measurements.get("physical_field_reconstruction")
    physical = physical if isinstance(physical, Mapping) else {}
    selected = physical.get("selected_plane_full3d_comparison")
    selected = selected if isinstance(selected, Mapping) else {}
    rows: dict[str, float] = {}
    planes = selected.get("planes")
    if isinstance(planes, list):
        for plane in planes:
            if not isinstance(plane, Mapping):
                continue
            z_nm = _finite(plane.get("z_nm"))
            for field in ("electric", "magnetic"):
                metric = plane.get(field)
                metric = metric if isinstance(metric, Mapping) else {}
                value = _finite(metric.get("relative_l2"))
                if z_nm is not None and value is not None:
                    rows[f"plane_{z_nm:g}_{field}"] = value
    interface = physical.get("interface_continuity")
    interface = interface if isinstance(interface, Mapping) else {}
    for side in ("bottom", "top"):
        side_payload = interface.get(side)
        side_payload = side_payload if isinstance(side_payload, Mapping) else {}
        for field in ("electric_tangential", "magnetic_tangential"):
            metric = side_payload.get(field)
            metric = metric if isinstance(metric, Mapping) else {}
            value = _finite(metric.get("relative_l2"))
            if value is not None:
                rows[f"interface_{side}_{field}"] = value
    return rows


def _identity(record: Mapping[str, Any], method: str) -> dict[str, Any]:
    if method == "full3d":
        summary = record.get("solver_summary")
        summary = summary if isinstance(summary, Mapping) else {}
        config = summary.get("config")
        config = config if isinstance(config, Mapping) else {}
        structural = {
            "num_nedelec_dofs": summary.get("num_nedelec_dofs"),
            "matrix_rows": (summary.get("matrix_stats") or {}).get("matrix_rows"),
            "matrix_nnz": (summary.get("matrix_stats") or {}).get("matrix_nnz_used"),
            "floquet_constraints": summary.get("floquet_num_constraints"),
            "floquet_constraint_nnz": summary.get("floquet_raw_map_nnz"),
            "propagating_orders": summary.get("stage4_dtn_num_auxiliary_dofs"),
            "mesh_cells": summary.get("mesh_cells_resolved"),
        }
        polarization = record.get("polarization_kind")
        config_hash = hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    else:
        measurements = record.get("measurements")
        measurements = measurements if isinstance(measurements, Mapping) else {}
        case = measurements.get("case")
        case = case if isinstance(case, Mapping) else {}
        system = measurements.get("hybrid_system")
        system = system if isinstance(system, Mapping) else {}
        ledger = measurements.get("object_payload_ledger")
        ledger = ledger if isinstance(ledger, Mapping) else {}
        structural = {
            "bottom_local_fe_dofs": system.get("bottom_local_fe_dofs"),
            "top_local_fe_dofs": system.get("top_local_fe_dofs"),
            "bottom_local_mesh_cells": system.get("bottom_local_mesh_cells"),
            "top_local_mesh_cells": system.get("top_local_mesh_cells"),
            "interface_active_dofs": ledger.get("interface_active_dofs"),
            "requested_modes": record.get(
                "requested_modes", case.get("requested_modes_per_direction")
            ),
        }
        polarization = case.get("polarization_kind")
        config_hash = hashlib.sha256(
            json.dumps(case, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    return {
        "degree": record.get("degree")
        if method == "full3d"
        else (record.get("measurements") or {}).get("case", {}).get("degree"),
        "h_nm": record.get("h_nm")
        if method == "full3d"
        else (record.get("measurements") or {}).get("case", {}).get("h_nm"),
        "polarization_kind": polarization,
        "source_sha": _source_sha(record),
        "config_hash": config_hash,
        "structural": structural,
    }


def build_mpi_identity(
    records: Sequence[Mapping[str, Any]],
    *,
    method: str,
    required_sizes: Sequence[int] = REQUIRED_MPI_SIZES,
    physical_core_count: int,
    funnel: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    by_size: dict[int, Mapping[str, Any]] = {}
    duplicate_sizes: list[int] = []
    for record in records:
        size = record.get("mpi_size")
        if not isinstance(size, int):
            size = (record.get("worker_source") or {}).get("mpi_size")
        if not isinstance(size, int):
            size = (record.get("measurements") or {}).get("mpi_size")
        if isinstance(size, int):
            if size in by_size:
                duplicate_sizes.append(size)
            by_size[size] = record
    required = tuple(int(value) for value in required_sizes)
    identities = {size: _identity(record, method) for size, record in by_size.items()}
    baseline_size = min(required) if required else None
    baseline = by_size.get(baseline_size) if baseline_size is not None else None
    baseline_identity = (
        identities.get(baseline_size) if baseline_size is not None else None
    )
    checks: dict[str, bool] = {
        "method_supported": method in ("full3d", "hybrid"),
        "required_mpi_sizes_present_once": all(size in by_size for size in required)
        and not duplicate_sizes,
        "no_oversubscription": physical_core_count > 0
        and all(size <= physical_core_count for size in by_size),
        "same_case_source_config_and_structure": bool(baseline_identity)
        and all(identity == baseline_identity for identity in identities.values()),
        "all_no_swap": bool(by_size)
        and all(record.get("no_swap") is True for record in by_size.values()),
    }
    comparisons: list[dict[str, Any]] = []
    if baseline is not None:
        base_orders = _load_orders(baseline, method)
        if method == "full3d":
            base_summary = baseline.get("solver_summary") or {}
            base_values = {
                "R_total": _finite(base_summary.get("R_total")),
                "T_total": _finite(base_summary.get("T_total")),
                "A_volume_total": _finite(base_summary.get("A_volume_total")),
            }
            base_values["A_balance"] = (
                None
                if None in (base_values["R_total"], base_values["T_total"])
                else 1.0 - base_values["R_total"] - base_values["T_total"]
            )
            base_arrays, array_failures = _full3d_arrays(baseline)
            checks["baseline_field_archive_valid"] = not array_failures
        else:
            base_measurements = baseline.get("measurements") or {}
            port = (base_measurements.get("validation") or {}).get("port_power") or {}
            volume = (base_measurements.get("physical_field_reconstruction") or {}).get(
                "volume_absorption"
            ) or {}
            base_values = {
                "R_total": _finite(port.get("R_total")),
                "T_total": _finite(port.get("T_total")),
                "A_balance": None,
                "A_volume_total": _finite(volume.get("A_volume_total")),
            }
            base_values["A_balance"] = (
                None
                if None in (base_values["R_total"], base_values["T_total"])
                else 1.0 - base_values["R_total"] - base_values["T_total"]
            )
            base_fields = _hybrid_field_scalars(baseline)
        for size in sorted(by_size):
            record = by_size[size]
            order_report = _compare_orders(base_orders, _load_orders(record, method))
            if method == "full3d":
                summary = record.get("solver_summary") or {}
                values = {
                    "R_total": _finite(summary.get("R_total")),
                    "T_total": _finite(summary.get("T_total")),
                    "A_volume_total": _finite(summary.get("A_volume_total")),
                }
                values["A_balance"] = (
                    None
                    if None in (values["R_total"], values["T_total"])
                    else 1.0 - values["R_total"] - values["T_total"]
                )
                residual = _finite(summary.get("linear_system_relative_residual"))
                official = (
                    record.get("status") == "full3d_reference_pass"
                    and summary.get("official_result") is True
                    and (record.get("qualification") or {}).get("pass") is True
                )
                arrays, failures = _full3d_arrays(record)
                field_drift = {
                    name: _relative_l2(base_arrays[name], arrays[name])
                    for name in base_arrays.keys() & arrays.keys()
                }
                field_complete = not failures and set(field_drift) == set(base_arrays)
            else:
                measurements = record.get("measurements") or {}
                port = (measurements.get("validation") or {}).get("port_power") or {}
                volume = (measurements.get("physical_field_reconstruction") or {}).get(
                    "volume_absorption"
                ) or {}
                values = {
                    "R_total": _finite(port.get("R_total")),
                    "T_total": _finite(port.get("T_total")),
                    "A_volume_total": _finite(volume.get("A_volume_total")),
                }
                values["A_balance"] = (
                    None
                    if None in (values["R_total"], values["T_total"])
                    else 1.0 - values["R_total"] - values["T_total"]
                )
                residual = _finite(
                    (measurements.get("solve") or {}).get("true_relative_residual")
                )
                gates = measurements.get("gates") or {}
                official = (
                    record.get("status") == "measured_shard_pass"
                    and record.get("formal_pass") is True
                    and record.get("numeric_pass") is True
                    and gates.get("biorthogonality_identity_error_le_1e-6") is True
                    and gates.get("right_and_left_qep_residuals_le_1e-8") is True
                )
                fields = _hybrid_field_scalars(record)
                field_drift = {
                    name: abs(value - base_fields[name])
                    for name, value in fields.items()
                    if name in base_fields
                }
                field_complete = bool(base_fields) and set(fields) == set(base_fields)
            rta_drift = {
                name: math.inf
                if base_values[name] is None or values[name] is None
                else abs(values[name] - base_values[name])
                for name in base_values
            }
            row_checks = {
                "official_result_identity": official,
                "true_residual_le_1e-9": residual is not None
                and residual <= TRUE_RESIDUAL_TOLERANCE,
                "rta_and_a_volume_absolute_drift_le_1e-8": max(rta_drift.values())
                <= RTA_ABSOLUTE_TOLERANCE,
                "field_and_interface_relative_l2_drift_le_1e-6": field_complete
                and max(field_drift.values(), default=math.inf)
                <= FIELD_RELATIVE_L2_TOLERANCE,
                **order_report["checks"],
            }
            comparisons.append(
                {
                    "mpi_size": size,
                    "checks": row_checks,
                    "true_relative_residual": residual,
                    "rta_drift": rta_drift,
                    "field_relative_l2_drift": field_drift,
                    "order_identity": order_report,
                    "resource": {
                        "elapsed_seconds": record.get("elapsed_seconds"),
                        "peak_memory_gib": (record.get("resource_authority") or {}).get(
                            "memory_authority_gib"
                        ),
                        "timings_seconds": record.get("timings_seconds")
                        if method == "full3d"
                        else (record.get("measurements") or {}).get(
                            "timing_seconds_max_rank"
                        ),
                        "no_swap": record.get("no_swap"),
                    },
                }
            )
    all_rows_pass = bool(comparisons) and all(
        all(row["checks"].values()) for row in comparisons
    )
    checks["all_numerical_identity_rows_pass"] = all_rows_pass
    if method == "hybrid":
        payload = funnel if isinstance(funnel, Mapping) else {}
        qualification = payload.get("qualification")
        qualification = qualification if isinstance(qualification, Mapping) else {}
        selected = qualification.get("selected_mode_count_per_direction")
        requested = (
            None
            if baseline_identity is None
            else baseline_identity["structural"].get("requested_modes")
        )
        checks["qualified_selected_mode_funnel"] = (
            payload.get("status") == "qualified"
            and qualification.get("mode_count_converged") is True
            and selected == requested
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task034.phase_f3.mpi-identity.v1",
        "record_type": "task034_mpi_identity_and_scalability",
        "status": "qualified" if not failures else "not_qualified",
        "method": method,
        "required_mpi_sizes": list(required),
        "observed_mpi_sizes": sorted(by_size),
        "physical_core_count": physical_core_count,
        "identity": baseline_identity,
        "tolerances": {
            "rta_and_a_volume_absolute": RTA_ABSOLUTE_TOLERANCE,
            "significant_order_power": SIGNIFICANT_ORDER_POWER,
            "order_power_absolute": ORDER_POWER_ABSOLUTE_TOLERANCE,
            "complex_amplitude_relative": AMPLITUDE_RELATIVE_TOLERANCE,
            "complex_amplitude_phase_rad": AMPLITUDE_PHASE_TOLERANCE_RAD,
            "field_and_interface_relative_l2": FIELD_RELATIVE_L2_TOLERANCE,
            "qep_beta_relative": BETA_RELATIVE_TOLERANCE,
            "true_residual": TRUE_RESIDUAL_TOLERANCE,
        },
        "checks": checks,
        "comparisons": comparisons,
        "failures": failures,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=("full3d", "hybrid"), required=True)
    parser.add_argument("--physical-core-count", type=int, required=True)
    parser.add_argument(
        "--required-sizes", nargs="+", type=int, default=list(REQUIRED_MPI_SIZES)
    )
    parser.add_argument("--funnel", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("records", nargs="+", type=Path)
    args = parser.parse_args(argv)
    records = [json.loads(path.read_text(encoding="utf-8")) for path in args.records]
    funnel = (
        None
        if args.funnel is None
        else json.loads(args.funnel.read_text(encoding="utf-8"))
    )
    result = build_mpi_identity(
        records,
        method=args.method,
        required_sizes=args.required_sizes,
        physical_core_count=args.physical_core_count,
        funnel=funnel,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "failures": result["failures"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "qualified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
