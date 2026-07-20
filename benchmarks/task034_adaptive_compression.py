"""Task034 fail-closed aggregation for measured graded-h compression shards."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


MODES = (80, 120, 160)
PROFILE_FACTORS = {"conservative": 1.5, "balanced": 2.0, "aggressive": 3.0}
TOTAL_TOLERANCE = 1.0e-5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sum_finite(values: Sequence[Any]) -> float | None:
    numbers = [_finite(value) for value in values]
    return None if any(value is None for value in numbers) else float(sum(numbers))


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _source_sha(payload: Mapping[str, Any]) -> str | None:
    source = _mapping(payload.get("source"))
    value = source.get("head_before_sha") or source.get("commit_sha")
    return value if isinstance(value, str) and len(value) == 40 else None


def _watchdog_contract(payload: Mapping[str, Any]) -> bool:
    resource = _mapping(_mapping(payload.get("resource_authority")).get("gate"))
    source = _mapping(payload.get("source_gate"))
    launch = _mapping(payload.get("launch_gate"))
    return bool(
        payload.get("target") == "hybrid"
        and payload.get("return_code") == 2
        and payload.get("memory_authority_pass") is True
        and payload.get("no_swap") is True
        and payload.get("terminated_for_memory") is False
        and payload.get("terminated_for_timeout") is False
        and resource.get("pass") is True
        and source.get("pass") is True
        and launch.get("pass") is True
    )


def _factor_nnz(ledger: Mapping[str, Any], side: str) -> float | None:
    inventory = _mapping(ledger.get("local_or_augmented_factor_inventory"))
    matrix = _mapping(_mapping(inventory.get(side)).get("matrix_stats"))
    return _finite(matrix.get("matrix_nnz_used"))


def _candidate(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    measurements = _mapping(payload.get("measurements"))
    case = _mapping(measurements.get("case"))
    system = _mapping(measurements.get("hybrid_system"))
    solve = _mapping(measurements.get("solve"))
    validation = _mapping(measurements.get("validation"))
    port = _mapping(validation.get("port_power"))
    fields = _mapping(measurements.get("physical_field_reconstruction"))
    interfaces = _mapping(fields.get("interface_continuity"))
    volume = _mapping(fields.get("volume_absorption"))
    planes = _mapping(fields.get("selected_plane_full3d_comparison"))
    comparison = _mapping(measurements.get("full3d_reference_comparison"))
    delta = _mapping(comparison.get("hybrid_minus_full3d"))
    ledger = _mapping(measurements.get("object_payload_ledger"))
    timing = _mapping(measurements.get("timing_seconds_max_rank"))
    gates = _mapping(measurements.get("gates"))
    bottom = _mapping(system.get("bottom_matrix_stats"))
    top = _mapping(system.get("top_matrix_stats"))

    interface_e = []
    interface_h = []
    for side in ("bottom", "top"):
        row = _mapping(interfaces.get(side))
        interface_e.append(_mapping(row.get("electric_tangential")).get("relative_l2"))
        interface_h.append(_mapping(row.get("magnetic_tangential")).get("relative_l2"))

    failed = sorted(name for name, passed in gates.items() if passed is False)
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "source_commit_full_sha": _source_sha(payload),
        "watchdog_contract_pass": _watchdog_contract(payload),
        "profile": case.get("graded_profile"),
        "coarse_factor": _finite(case.get("graded_coarse_factor")),
        "plan_hash": case.get("graded_plan_hash"),
        "mesh_cells": _mapping(case.get("graded_plan")).get("mesh_cells"),
        "mesh_elements": _mapping(case.get("graded_plan")).get("element_count"),
        "mode_count": payload.get("requested_modes"),
        "local_fe_dofs_bottom": system.get("bottom_local_fe_dofs"),
        "local_fe_dofs_top": system.get("top_local_fe_dofs"),
        "local_fe_dofs_sum": _sum_finite(
            [system.get("bottom_local_fe_dofs"), system.get("top_local_fe_dofs")]
        ),
        "local_rows_bottom": system.get("bottom_global_size"),
        "local_rows_top": system.get("top_global_size"),
        "local_rows_sum": _sum_finite(
            [system.get("bottom_global_size"), system.get("top_global_size")]
        ),
        "assembled_nnz_sum": _sum_finite(
            [bottom.get("matrix_nnz_used"), top.get("matrix_nnz_used")]
        ),
        "factor_nnz_sum": _sum_finite(
            [_factor_nnz(ledger, "bottom"), _factor_nnz(ledger, "top")]
        ),
        "peak_memory_gib": _finite(
            _mapping(payload.get("memory")).get("max_simultaneous_worker_rss_gib")
        ),
        "wall_time_seconds": _finite(timing.get("total")),
        "true_relative_residual": _finite(solve.get("true_relative_residual")),
        "R_total": _finite(port.get("R_total")),
        "T_total": _finite(port.get("T_total")),
        "A_balance": _finite(port.get("A_balance")),
        "A_volume": _finite(volume.get("A_volume_total")),
        "R_delta_full3d": _finite(delta.get("R_total")),
        "T_delta_full3d": _finite(delta.get("T_total")),
        "A_delta_full3d": _finite(delta.get("A_balance")),
        "A_volume_delta_full3d": _finite(
            volume.get("hybrid_minus_full3d_A_volume_total")
        ),
        "max_middle_E_relative_l2": _finite(
            planes.get("max_middle_plane_electric_relative_l2")
        ),
        "max_middle_H_relative_l2": _finite(
            planes.get("max_middle_plane_magnetic_relative_l2")
        ),
        "max_interface_E_relative_l2": max(
            (value for value in map(_finite, interface_e) if value is not None),
            default=None,
        ),
        "max_interface_H_relative_l2": max(
            (value for value in map(_finite, interface_h) if value is not None),
            default=None,
        ),
        "all_reported_physical_gates_pass": bool(gates) and all(gates.values()),
        "failed_gate_names": failed,
    }


def _modal_delta(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    deltas = {}
    for name in ("R_total", "T_total", "A_balance"):
        first = _finite(previous.get(name))
        second = _finite(current.get(name))
        deltas[name] = None if first is None or second is None else abs(second - first)
    finite = [value for value in deltas.values() if value is not None]
    maximum = max(finite) if len(finite) == len(deltas) else None
    return {
        "previous_mode_count": previous.get("mode_count"),
        "current_mode_count": current.get("mode_count"),
        "absolute_total_deltas": deltas,
        "max_absolute_total_delta": maximum,
        "mandatory_total_tolerance": TOTAL_TOLERANCE,
        "modal_totals_converged": maximum is not None and maximum <= TOTAL_TOLERANCE,
    }


def build_adaptive_compression_summary(
    *,
    baseline_path: Path,
    profile_paths: Mapping[str, Sequence[Path]],
    preserved_failures: Sequence[Path] = (),
) -> dict[str, Any]:
    baseline = _candidate(baseline_path, _load(baseline_path))
    profiles: dict[str, Any] = {}
    source_shas: set[str | None] = set()
    for profile, factor in PROFILE_FACTORS.items():
        paths = list(profile_paths.get(profile, ()))
        if len(paths) != 3:
            raise ValueError(f"{profile} requires exactly M80/M120/M160")
        rows = [_candidate(path, _load(path)) for path in paths]
        rows.sort(key=lambda row: int(row["mode_count"]))
        if [row["mode_count"] for row in rows] != list(MODES):
            raise ValueError(f"{profile} has an invalid M funnel")
        if any(row["profile"] != profile for row in rows):
            raise ValueError(f"{profile} payload identity mismatch")
        if any(row["coarse_factor"] != factor for row in rows):
            raise ValueError(f"{profile} coarse factor mismatch")
        source_shas.update(row["source_commit_full_sha"] for row in rows)
        comparisons = [_modal_delta(rows[0], rows[1]), _modal_delta(rows[1], rows[2])]
        selected = rows[-1]
        same_error = bool(selected["all_reported_physical_gates_pass"])
        modal_converged = bool(comparisons[-1]["modal_totals_converged"])
        baseline_dofs = _finite(baseline.get("local_fe_dofs_sum"))
        candidate_dofs = _finite(selected.get("local_fe_dofs_sum"))
        raw_dof_ratio = (
            None
            if baseline_dofs is None or candidate_dofs in (None, 0.0)
            else baseline_dofs / candidate_dofs
        )
        profiles[profile] = {
            "status": "same_error_qualified" if same_error and modal_converged else "not_qualified",
            "shards": rows,
            "modal_comparisons": comparisons,
            "modal_totals_converged": modal_converged,
            "same_error_physical_gates_pass": same_error,
            "raw_local_fe_dof_ratio_vs_uniform": raw_dof_ratio,
            "qualified_compression_ratio": raw_dof_ratio if same_error and modal_converged else None,
            "compression_classification": None,
            "stop_reason": (
                None
                if same_error and modal_converged
                else "critical_observable_exceeded_same_error_tolerance"
            ),
        }
    failure_records = []
    for path in preserved_failures:
        payload = _load(path)
        failure_records.append(
            {
                "path": str(path),
                "sha256": _sha256(path),
                "status": payload.get("status"),
                "return_code": payload.get("return_code"),
                "case_label": payload.get("case_label"),
                "preserved_as": "controlled_transient_launch_failure",
            }
        )
    any_qualified = any(
        row["status"] == "same_error_qualified" for row in profiles.values()
    )
    return {
        "schema_version": "task034.adaptive-compression.v1",
        "record_type": "task034_measured_graded_h_compression",
        "status": "qualified_profile_available" if any_qualified else "controlled_negative",
        "baseline": baseline,
        "profiles": profiles,
        "preserved_failures": failure_records,
        "source": {
            "candidate_source_commit_full_sha": next(iter(source_shas), None),
            "all_candidate_shards_same_source_sha": len(source_shas) == 1,
        },
        "decision": {
            "same_error_compression_demonstrated": any_qualified,
            "measured_adaptive_heavy_lane_unlocked": any_qualified,
            "common_mesh_heavy_lane_unlocked": any_qualified,
            "p3_adaptive_heavy_lane_unlocked": any_qualified,
            "ordinary_uniform_default_changed": False,
            "failure_thresholds_relaxed": False,
            "reason": (
                "At least one profile passed the fixed physical gates."
                if any_qualified
                else "All three graded profiles exceeded fixed same-error observables; stop conditions apply."
            ),
        },
        "limitations": [
            "The conforming mechanism is qualified independently of compression accuracy.",
            "Raw cost ratios are not compression success when same-error gates fail.",
            "No heavy common-mesh or p3 adaptive claim is made after the stop condition.",
        ],
    }


def write_adaptive_csv(summary: Mapping[str, Any], path: Path) -> None:
    fields = [
        "profile", "mode_count", "mesh_elements", "local_fe_dofs_sum",
        "local_rows_sum", "assembled_nnz_sum", "factor_nnz_sum",
        "peak_memory_gib", "wall_time_seconds", "true_relative_residual",
        "R_total", "T_total", "A_balance", "A_volume",
        "R_delta_full3d", "T_delta_full3d", "A_delta_full3d",
        "A_volume_delta_full3d", "max_middle_E_relative_l2",
        "max_middle_H_relative_l2", "max_interface_E_relative_l2",
        "max_interface_H_relative_l2", "all_reported_physical_gates_pass",
        "failed_gate_names",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for profile, record in _mapping(summary.get("profiles")).items():
            for shard in record["shards"]:
                row = {name: shard.get(name) for name in fields}
                row["profile"] = profile
                row["failed_gate_names"] = ";".join(shard["failed_gate_names"])
                writer.writerow(row)


def _parse_profile(value: str) -> tuple[str, list[Path]]:
    profile, raw_paths = value.split("=", 1)
    return profile, [Path(item) for item in raw_paths.split(",")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--preserved-failure", action="append", type=Path, default=[])
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    profiles = dict(_parse_profile(item) for item in args.profile)
    summary = build_adaptive_compression_summary(
        baseline_path=args.baseline,
        profile_paths=profiles,
        preserved_failures=args.preserved_failure,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_adaptive_csv(summary, args.csv_output)
    print(json.dumps(summary["decision"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
