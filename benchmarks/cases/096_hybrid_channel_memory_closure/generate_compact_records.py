#!/usr/bin/env python3
"""Generate Task035c Case096 compact evidence from ignored raw authorities.

The generated JSON is deliberately small enough for Git while retaining the
per-channel values needed for a hermetic, independent recheck.  This tool is
not a PDE runner: it only reads already completed, hash-bound raw records.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "benchmarks/cases/096_hybrid_channel_memory_closure"
RECORDS = CASE / "records"
ARTIFACTS = ROOT / "benchmarks/artifacts/task035c_hybrid_channel_memory"
REFERENCE_PATH = (
    ROOT
    / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
    / "significant_channel_reference_v1.json"
)
REFERENCE_SHA256 = "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3"
P6_SOURCE_SHA = "244b62e1fb4f299a468363cf90a2dd548dc34ff6"
P2_SOURCE_SHA = "8a1e40c420e36407cd827e1fd7e8f11401a0d39b"
SIGNIFICANT_POWER_FLOOR = 1.0e-8
RELATIVE_TOLERANCE = 1.0e-3
AMPLITUDE_DENOMINATOR_FLOOR = 1.0e-15
BOUNDARY_AMPLITUDE_FIELD = "outgoing_amplitude_at_boundary"

P6_MPI8_AUTHORITIES = {
    "full_standard": (
        "p6_h10_full_standard_mpi8_244b62e.json",
        "0a0846cd5e7bdef1532fda0ee2540fe2af00f54a8e1cc7c963f53dbf019df246",
    ),
    "full_static": (
        "p6_h10_full_static_mpi8_244b62e.json",
        "b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3",
    ),
    "hybrid_standard_m120": (
        "p6_h10_hybrid_standard_m120_mpi8_244b62e.json",
        "563e4158955f251e067be6d40bb3ca0e34e1032c2b1ad1e265a3751d3889979b",
    ),
    "hybrid_standard_m160": (
        "p6_h10_hybrid_standard_m160_mpi8_244b62e.json",
        "724923b23976000d44640177d50fc4882628c957fdffaf4800aa28f4e22734b5",
    ),
    "hybrid_static_m120": (
        "p6_h10_hybrid_static_m120_mpi8_244b62e_retry1.json",
        "194a22ee2528a2536f794c0a0a8871671cb023a2f8dc029b31fae456694d5532",
    ),
    "hybrid_static_m160": (
        "p6_h10_hybrid_static_m160_mpi8_244b62e.json",
        "58281f5f0be5c9d30b441d9b573018070502734043a81cb8cd10ddd068f5c137",
    ),
}

# The Hybrid watchdog is itself the memory-sampler summary and binds the
# solver record, but its historical schema did not store the timeline digest.
# Review V2 therefore freezes the already completed raw timelines here before
# extracting PSS/USS; --check fails if any ignored raw timeline drifts.
P6_MPI8_HYBRID_TIMELINE_SHA256 = {
    "hybrid_standard_m120": (
        "76445bb6ecb186361a6881674d64b80d8315581d392a0ea437ec0aebead736ea"
    ),
    "hybrid_standard_m160": (
        "2c2153e0a31a1d1017a9d7a61e48809c12f74ef64f7abb64882d7be5d3e74eba"
    ),
    "hybrid_static_m120": (
        "8e0b652de1a4af2c3eced21ce9e053eb143739e37259b3c6479b3989e52af510"
    ),
    "hybrid_static_m160": (
        "24c9147ef4d33b37faae401f0ee05722f561742896478792639e732a1734636c"
    ),
}

P6_RANK_AUTHORITIES = {
    "full_static_mpi1": (
        "p6_h10_full_static_mpi1_244b62e.json",
        "36cde9b87732277d91d9f9924e7a9a91671bc98ec74d949c0c1d14adce11a894",
    ),
    "full_static_mpi2": (
        "p6_h10_full_static_mpi2_244b62e.json",
        "6b045a1475e1f9d4b9d6e7b2e3bd41c6501f7312879228df3fb5b4fdfdcd225c",
    ),
    "hybrid_static_m120_mpi1": (
        "p6_h10_hybrid_static_m120_mpi1_244b62e.json",
        "e99cda1de21e6bbe7a8787eda268d4498565420f8a32d662f6456a919d6ca27e",
    ),
    "hybrid_static_m120_mpi2": (
        "p6_h10_hybrid_static_m120_mpi2_244b62e.json",
        "5a0ef31775d307c09ccf6b7e3fcb5fc523c6b9cba0531f9b298a938901e2bf5b",
    ),
}

P2_AUTHORITIES = {
    "full_static": (
        "p2_h5_full_static_mpi8_8a1e40c.json",
        "228517adc2829ea5f026ce571f22041b872e504906699eb661abab13db56a2a2",
    ),
    "hybrid_static_m120": (
        "p2_h5_static_m120_scalar_cg_phase_traction_watchdog.json",
        "13632704da826c100e5d252cda50a33b8f9bb86ab38f9109f2f3ae69e798b2d5",
    ),
    "hybrid_static_m160": (
        "p2_h5_static_m160_scalar_cg_phase_traction_watchdog.json",
        "03afd5a2547c934cf51df273c5057275b98f5e0776a9ffb7588907140b362ce6",
    ),
}

P2_PHASE_ONLY_AUTHORITIES = {
    "full_static": (
        "p2_h5_full_static_mpi8_1d9a712.json",
        "3fce43601f97853d4c385f3e7dfdffb6b7823eb45fd54dccbd68779db7c045c1",
    ),
    "hybrid_static_m160_phase_only": (
        "p2_h5_static_m160_scalar_cg_phase_watchdog.json",
        "f286f6224bfba6ace5f0dd5049a3a4a26bf99f66b3919b3136b8fd4e513fae3f",
    ),
}

DEPENDENCY_FAILURES = {
    "p6_cross_section_p5p6_not_implemented": (
        "p6_h10_hybrid_standard_m120_mpi8_c30fad7.json",
        "f5d47a68429e269b7016f09365077f669b11ac6dbab2c0946804489561234e79",
        "ValueError: Task033 qualifies exact cross-section N1curl constraints for p=1..4.",
    ),
    "static_trace_projection_absolute_tolerance": (
        "p6_h10_hybrid_static_m120_mpi8_b40644b.json",
        "188f5447454442282161f510bdbff33af2ed3ccfbaf0ee6c64a27696598cecef",
        "ValueError: MPC vector has nonzero eliminated interior/slave entries: 1.187e-12",
    ),
    "mpi8_terminal_sampler_race_superseded_by_retry1": (
        "p6_h10_hybrid_static_m120_mpi8_244b62e.json",
        "4c0d0b22bce9750550b26863f22b43d4cc93128a33e3021feda656f7969ae41a",
        None,
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{rel(path)} is not a JSON object")
    return payload


def load_bound(path: Path, expected_sha: str) -> tuple[dict[str, Any], str]:
    observed = sha256(path)
    if observed != expected_sha:
        raise ValueError(
            f"{rel(path)} SHA-256 mismatch: expected {expected_sha}, got {observed}"
        )
    return load_json(path), observed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_sha(record: dict[str, Any]) -> str:
    source = record["source"]
    values = {
        source[name]
        for name in (
            "commit_sha",
            "verified_clean_sha",
            "head_before_sha",
            "head_after_sha",
        )
        if isinstance(source.get(name), str)
    }
    require(len(values) == 1, "source SHA fields disagree")
    return values.pop()


def option(command: list[str], name: str) -> str:
    index = command.index(name)
    return command[index + 1]


def channel_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(row["side"]),
        int(row["m"]),
        int(row["n"]),
        str(row["polarization"]),
    )


def channel_label(key: tuple[str, int, int, str]) -> str:
    side, m, n, polarization = key
    return f"{'R' if side == 'top' else 'T'}({m},{n})_{polarization}"


def order_map(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    require(len(rows) == 80, "DtN order payload must contain exactly 80 rows")
    mapped = {channel_key(row): row for row in rows}
    require(len(mapped) == 80, "DtN order payload contains duplicate keys")
    return mapped


def significant_reference() -> tuple[
    dict[tuple[str, int, int, str], dict[str, Any]], dict[str, Any]
]:
    record, observed = load_bound(REFERENCE_PATH, REFERENCE_SHA256)
    require(
        record["status"] == "significant_channel_reference_v1_frozen",
        "significant-channel reference is not frozen",
    )
    channels = {
        channel_key(row["channel"]): row for row in record["channels"]
    }
    require(len(channels) == 12, "significant-channel reference does not contain 12 rows")
    authority = {
        "path": rel(REFERENCE_PATH),
        "sha256": observed,
        "schema_version": record["schema_version"],
        "status": record["status"],
        "phase_convention": record["phase_convention"],
        "significant_power_floor": record["significant_channel_selection"][
            "significant_power_floor"
        ],
    }
    return channels, authority


def compact_channels(
    orders: dict[tuple[str, int, int, str], dict[str, Any]],
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    require(set(reference).issubset(orders), "raw orders miss a frozen channel")
    output = []
    for key in sorted(reference):
        row = orders[key]
        amplitude = row[BOUNDARY_AMPLITUDE_FIELD]
        output.append(
            {
                "label": channel_label(key),
                "key": list(key),
                "power": float(row["power_ratio"]),
                "boundary_complex_amplitude": [
                    float(amplitude[0]),
                    float(amplitude[1]),
                ],
            }
        )
    return output


def load_full(
    name: str,
    expected_sha: str,
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
    expected_source: str,
) -> dict[str, Any]:
    path = ARTIFACTS / name
    record, observed = load_bound(path, expected_sha)
    require(record["schema_version"] == "task033.full3d-watchdog.v1", "wrong Full schema")
    require(source_sha(record) == expected_source, "unexpected Full source SHA")
    raw_path = (ROOT / record["raw_evidence"]["solver_summary"]).resolve()
    raw, raw_sha = load_bound(raw_path, record["solver_summary_sha256"])
    require(raw == record["solver_summary"], "Full embedded and raw summaries differ")
    order_path = raw_path.parent / raw["dtn_port_orders_json"]
    order_payload = load_json(order_path)
    orders = order_map(order_payload["orders"])
    factor_nnz = int(
        raw["stage4_dtn_factor_inventory"]["matrix_stats"]["matrix_nnz_used"]
    )
    matrix_nnz = int(record["calibration"]["exact_assembled_nnz"])
    model = {
        "kind": "full3d",
        "assembly_backend": record["stage4_full3d_assembly_backend_actual"],
        "source_sha": source_sha(record),
        "degree": int(record["degree"]),
        "h_nm": float(record["h_nm"]),
        "mpi_size": int(record["mpi_size"]),
        "formal_pass": bool(record["qualification"]["pass"]),
        "no_swap": bool(record["no_swap"]),
        "active_rows": int(record["calibration"]["exact_rows"]),
        "matrix_nnz": matrix_nnz,
        "factor_nnz": factor_nnz,
        "factor_fill": factor_nnz / matrix_nnz,
        "peak_memory_gib": float(record["resource_authority"]["memory_authority_gib"]),
        "total_seconds": float(raw["elapsed_seconds"]),
        "assembly_and_solve_seconds": float(
            raw["timings_seconds"]["stage4_dtn_port_assembly_and_solve"]
        ),
        "factor_setup_seconds": float(raw["stage4_dtn_ksp_setup_seconds"]),
        "backsolve_seconds": float(raw["stage4_dtn_ksp_solve_seconds"]),
        "true_residual": float(raw["linear_system_relative_residual"]),
        "R00_total": float(raw["R00_total"]),
        "R_total": float(raw["R_total"]),
        "T_total": float(raw["T_total"]),
        "A_closure": float(raw["A_balance"]),
        "A_volume": float(raw["A_volume_total"]),
        "energy_closure_error": float(
            raw["energy_closure_error_dtn_port_modal_volume"]
        ),
        "channels": compact_channels(orders, reference),
        "raw_authority": {
            "watchdog_path": rel(path),
            "watchdog_sha256": observed,
            "solver_summary_path": rel(raw_path),
            "solver_summary_sha256": raw_sha,
            "dtn_order_path": rel(order_path),
            "dtn_order_sha256": sha256(order_path),
        },
    }
    require(model["formal_pass"] and model["no_swap"], f"{name} is not formal")
    return model


def hybrid_raw_path(path: Path, record: dict[str, Any]) -> Path:
    candidate = Path(record["solver_record_ignored_path"])
    return (candidate if candidate.is_absolute() else ROOT / candidate).resolve()


def modal_stage_peak_gib(record: dict[str, Any]) -> float:
    rows = [
        row
        for row in record["memory"]["stage_peaks"]
        if row["stage"] == "interface_projection_and_coupling"
    ]
    require(len(rows) == 1, "modal coupling stage is missing or duplicated")
    return float(rows[0]["max_worker_rank_rss_sum_mb"]) / 1024.0


def load_hybrid(
    name: str,
    expected_sha: str,
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
    expected_source: str,
    require_formal: bool = True,
) -> dict[str, Any]:
    path = ARTIFACTS / name
    record, observed = load_bound(path, expected_sha)
    require(record["schema_version"] == "task033.memory-watchdog.v2", "wrong Hybrid schema")
    require(source_sha(record) == expected_source, "unexpected Hybrid source SHA")
    raw_path = hybrid_raw_path(path, record)
    raw, raw_sha = load_bound(raw_path, record["solver_record_sha256"])
    require(
        raw["validation"]["external_diffraction_orders"]
        == record["measurements"]["validation"]["external_diffraction_orders"],
        "Hybrid copied channel payload differs from raw",
    )
    orders = order_map(raw["validation"]["external_diffraction_orders"])
    system = raw["hybrid_system"]
    bottom = system["bottom_matrix_stats"]
    top = system["top_matrix_stats"]
    factor = raw["object_payload_ledger"]["local_or_augmented_factor_inventory"]
    bottom_factor = int(factor["bottom"]["matrix_stats"]["matrix_nnz_used"])
    top_factor = int(factor["top"]["matrix_stats"]["matrix_nnz_used"])
    matrix_nnz = int(bottom["matrix_nnz_used"]) + int(top["matrix_nnz_used"])
    factor_nnz = bottom_factor + top_factor
    authority = record["resource_authority"]
    peak_bytes = max(
        int(authority["simultaneous_live_worker_rss_sum_bytes"]),
        int(authority["container_cgroup_current_bytes"]),
    )
    require(peak_bytes == int(authority["memory_authority_bytes"]), "peak was not recomputed max")
    timing = raw["timing_seconds_max_rank"]
    port = raw["validation"]["port_power"]
    volume = raw["physical_field_reconstruction"]["volume_absorption"]
    interface = raw["physical_field_reconstruction"]["interface_continuity"]
    planes = raw["physical_field_reconstruction"]["selected_plane_full3d_comparison"]
    command = list(record["command"])
    backend = option(command, "--stage4-full3d-assembly-backend")
    model = {
        "kind": "hybrid",
        "assembly_backend": backend,
        "source_sha": source_sha(record),
        "degree": int(raw["case"]["degree"]),
        "h_nm": float(raw["case"]["h_nm"]),
        "modal_degree": int(raw["case"]["modal_degree"]),
        "modal_h_nm": float(raw["case"]["modal_h_nm"]),
        "mpi_size": int(raw["metadata"]["mpi_size"]),
        "modes_per_direction": int(raw["case"]["requested_modes_per_direction"]),
        "formal_pass": bool(record["formal_pass"]),
        "numeric_pass": bool(record["numeric_pass"]),
        "memory_authority_pass": bool(record["memory_authority_pass"]),
        "no_swap": bool(record["no_swap"]),
        "active_rows": (
            int(system["bottom_global_size"])
            + int(system["top_global_size"])
            + int(system["internal_unknown_count"])
        ),
        "matrix_nnz": matrix_nnz,
        "factor_nnz": factor_nnz,
        "factor_fill": factor_nnz / matrix_nnz,
        "peak_memory_gib": peak_bytes / 1024**3,
        "modal_coupling_stage_peak_gib": modal_stage_peak_gib(record),
        "total_seconds": float(timing["total"]),
        "modal_coupling_seconds": float(timing["internal_modal_coupling"]),
        "true_residual": float(raw["solve"]["true_relative_residual"]),
        "R00_total": float(port["R00_total"]),
        "R_total": float(port["R_total"]),
        "T_total": float(port["T_total"]),
        "A_closure": float(port["A_balance"]),
        "A_volume": float(volume["A_volume_total"]),
        "energy_closure_error": float(volume["energy_closure_error"]),
        "interface_E_relative_l2_max": max(
            float(interface["bottom"]["electric_tangential"]["relative_l2"]),
            float(interface["top"]["electric_tangential"]["relative_l2"]),
        ),
        "interface_H_relative_l2_max": max(
            float(interface["bottom"]["magnetic_tangential"]["relative_l2"]),
            float(interface["top"]["magnetic_tangential"]["relative_l2"]),
        ),
        "selected_plane_E_relative_l2_max": float(
            planes["max_middle_plane_electric_relative_l2"]
        ),
        "selected_plane_H_relative_l2_max": float(
            planes["max_middle_plane_magnetic_relative_l2"]
        ),
        "retained_right_left_eigenvector_bytes": int(
            raw["object_payload_ledger"]["retained_right_left_eigenvector_bytes"]
        ),
        "modal_schur_bytes": int(raw["object_payload_ledger"]["modal_schur_bytes"]),
        "dense_interface_square_formed": bool(
            raw["object_payload_ledger"]["dense_interface_square_formed"]
        ),
        "channels": compact_channels(orders, reference),
        "raw_authority": {
            "watchdog_path": rel(path),
            "watchdog_sha256": observed,
            "solver_record_path": rel(raw_path),
            "solver_record_sha256": raw_sha,
        },
    }
    if require_formal:
        require(
            model["formal_pass"]
            and model["numeric_pass"]
            and model["memory_authority_pass"]
            and model["no_swap"],
            f"{name} is not a formal Hybrid authority",
        )
    return model


def _timeline_path_and_sha(
    role: str,
    record: dict[str, Any],
) -> tuple[Path, str]:
    if role.startswith("full_"):
        path = (ROOT / record["raw_evidence"]["timeline"]).resolve()
        expected_sha = str(record["timeline_sha256"])
    else:
        candidate = Path(record["timeline_ignored_path"])
        path = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
        expected_sha = P6_MPI8_HYBRID_TIMELINE_SHA256[role]
    observed_sha = sha256(path)
    require(
        observed_sha == expected_sha,
        f"{rel(path)} SHA-256 mismatch: expected {expected_sha}, got {observed_sha}",
    )
    return path, observed_sha


def _smaps_peak(
    rows: list[dict[str, Any]],
    metric: str,
) -> dict[str, Any]:
    row = max(rows, key=lambda item: float(item[metric]))
    per_rank = json.loads(row["worker_rank_smaps_rollup_json"])
    require(isinstance(per_rank, list), "smaps peak payload is not a list")
    return {
        "simultaneous_sum_mb": float(row[metric]),
        "simultaneous_sum_gib": float(row[metric]) / 1024.0,
        "timestamp_utc": row["timestamp_utc"],
        "elapsed_seconds": float(row["elapsed_seconds"]),
        "stage": row["stage"],
        "rank_count": len(per_rank),
        "per_rank": [
            {
                "rank": int(item["rank"]),
                "rss_mb": float(item["rss_mb"]),
                "pss_mb": float(item["pss_mb"]),
                "uss_mb": float(item["uss_mb"]),
                "shared_mb": float(item["shared_mb"]),
                "swap_mb": float(item["swap_mb"]),
            }
            for item in sorted(per_rank, key=lambda item: int(item["rank"]))
        ],
    }


def _load_pss_uss_timeline(role: str) -> dict[str, Any]:
    watchdog_name, watchdog_sha = P6_MPI8_AUTHORITIES[role]
    watchdog_path = ARTIFACTS / watchdog_name
    record, observed_watchdog_sha = load_bound(watchdog_path, watchdog_sha)
    require(source_sha(record) == P6_SOURCE_SHA, f"{role} source SHA drifted")
    if role.startswith("full_"):
        require(
            record["schema_version"] == "task033.full3d-watchdog.v1",
            f"{role} has the wrong watchdog schema",
        )
        require(
            bool(record["qualification"]["pass"]),
            f"{role} is not a formal Full3D authority",
        )
        mpi_size = int(record["mpi_size"])
    else:
        require(
            record["schema_version"] == "task033.memory-watchdog.v2",
            f"{role} has the wrong watchdog schema",
        )
        require(
            bool(record["formal_pass"])
            and bool(record["numeric_pass"])
            and bool(record["memory_authority_pass"]),
            f"{role} is not a formal Hybrid authority",
        )
        mpi_size = int(record["worker_source"]["mpi_size"])
    require(mpi_size == 8, f"{role} PSS/USS backfill requires MPI8")

    timeline_path, timeline_sha = _timeline_path_and_sha(role, record)
    with timeline_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required_columns = {
            "timestamp_utc",
            "elapsed_seconds",
            "stage",
            "worker_rank_rss_sum_mb",
            "worker_rank_pss_sum_mb",
            "worker_rank_uss_sum_mb",
            "worker_rank_shared_sum_mb",
            "worker_rank_smaps_swap_sum_mb",
            "worker_rank_smaps_rollup_json",
            "worker_rank_smaps_readable_count",
        }
        require(
            reader.fieldnames is not None
            and required_columns.issubset(reader.fieldnames),
            f"{rel(timeline_path)} lacks PSS/USS timeline columns",
        )
        all_rows = list(reader)

    expected_ranks = set(range(mpi_size))
    fully_readable: list[dict[str, Any]] = []
    partial_readable = 0
    no_smaps = 0
    for row in all_rows:
        payload = json.loads(row["worker_rank_smaps_rollup_json"] or "[]")
        require(isinstance(payload, list), "smaps timeline payload is not a list")
        ranks = {int(item["rank"]) for item in payload if "rank" in item}
        readable_count = int(float(row["worker_rank_smaps_readable_count"] or 0))
        if ranks == expected_ranks and readable_count == mpi_size:
            sums = {
                "worker_rank_pss_sum_mb": sum(float(item["pss_mb"]) for item in payload),
                "worker_rank_uss_sum_mb": sum(float(item["uss_mb"]) for item in payload),
                "worker_rank_shared_sum_mb": sum(
                    float(item["shared_mb"]) for item in payload
                ),
                "worker_rank_smaps_swap_sum_mb": sum(
                    float(item["swap_mb"]) for item in payload
                ),
            }
            for name, reconstructed in sums.items():
                require(
                    math.isclose(
                        float(row[name]),
                        reconstructed,
                        rel_tol=0.0,
                        abs_tol=1.0e-8,
                    ),
                    f"{role} {name} differs from per-rank smaps reconstruction",
                )
            require(
                float(row["worker_rank_uss_sum_mb"])
                <= float(row["worker_rank_pss_sum_mb"])
                <= float(row["worker_rank_rss_sum_mb"]),
                f"{role} has invalid USS/PSS/RSS ordering",
            )
            require(
                float(row["worker_rank_smaps_swap_sum_mb"]) == 0.0,
                f"{role} smaps timeline contains swap",
            )
            fully_readable.append(row)
        elif readable_count > 0:
            partial_readable += 1
        else:
            no_smaps += 1

    require(fully_readable, f"{role} has no fully readable MPI8 smaps samples")
    return {
        "source_sha": P6_SOURCE_SHA,
        "mpi_size": mpi_size,
        "watchdog_path": rel(watchdog_path),
        "watchdog_sha256": observed_watchdog_sha,
        "timeline_path": rel(timeline_path),
        "timeline_sha256": timeline_sha,
        "sample_count": len(all_rows),
        "fully_readable_mpi8_sample_count": len(fully_readable),
        "partial_terminal_or_startup_sample_count": partial_readable,
        "no_live_rank_smaps_sample_count": no_smaps,
        "all_qualified_samples_have_zero_smaps_swap": True,
        "qualification": (
            "qualified historical backfill from simultaneous per-rank "
            "/proc/<pid>/smaps_rollup samples; only samples with all eight "
            "rank snapshots readable are eligible"
        ),
        "worker_rank_rss_peak": _smaps_peak(
            fully_readable, "worker_rank_rss_sum_mb"
        ),
        "worker_rank_pss_peak": _smaps_peak(
            fully_readable, "worker_rank_pss_sum_mb"
        ),
        "worker_rank_uss_peak": _smaps_peak(
            fully_readable, "worker_rank_uss_sum_mb"
        ),
    }


def _smaps_pair(
    standard: dict[str, Any],
    static: dict[str, Any],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric in ("pss", "uss"):
        key = f"worker_rank_{metric}_peak"
        standard_gib = float(standard[key]["simultaneous_sum_gib"])
        static_gib = float(static[key]["simultaneous_sum_gib"])
        output[metric] = {
            "standard_gib": standard_gib,
            "static_gib": static_gib,
            "saving_fraction": (standard_gib - static_gib) / standard_gib,
        }
    return output


def p6_pss_uss_record() -> dict[str, Any]:
    models = {
        role: _load_pss_uss_timeline(role)
        for role in P6_MPI8_AUTHORITIES
    }
    comparisons = {
        "full_standard_vs_static": _smaps_pair(
            models["full_standard"], models["full_static"]
        ),
        "hybrid_m120_standard_vs_static": _smaps_pair(
            models["hybrid_standard_m120"], models["hybrid_static_m120"]
        ),
        "hybrid_m160_standard_vs_static": _smaps_pair(
            models["hybrid_standard_m160"], models["hybrid_static_m160"]
        ),
    }
    return {
        "schema_version": "task035c.case096-p6-mpi8-pss-uss-ledger.v1",
        "status": "p6_h10_mpi8_historical_pss_uss_backfill_qualified",
        "pass": True,
        "numerical_source_sha": P6_SOURCE_SHA,
        "is_pde_rerun": False,
        "formal_task035c_relative_memory_authority": (
            "simultaneous process-tree/live-worker RSS from the original campaign"
        ),
        "pss_uss_semantics": (
            "diagnostic memory decomposition reconstructed from the original "
            "simultaneous MPI8 smaps_rollup timeline; no RSS-to-PSS/USS inference"
        ),
        "models": models,
        "comparisons": comparisons,
    }


def channel_map(model: dict[str, Any]) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    return {
        tuple(row["key"]): row  # type: ignore[misc]
        for row in model["channels"]
    }


def compare_models(left_name: str, left: dict[str, Any], right_name: str, right: dict[str, Any]) -> dict[str, Any]:
    left_rows = channel_map(left)
    right_rows = channel_map(right)
    keys = [
        key
        for key in sorted(set(left_rows) | set(right_rows))
        if max(
            float(left_rows[key]["power"]),
            float(right_rows[key]["power"]),
        )
        >= SIGNIFICANT_POWER_FLOOR
    ]
    rows = []
    for key in keys:
        lrow = left_rows[key]
        rrow = right_rows[key]
        lp = float(lrow["power"])
        rp = float(rrow["power"])
        la = complex(*lrow["boundary_complex_amplitude"])
        ra = complex(*rrow["boundary_complex_amplitude"])
        power_error = abs(rp - lp) / max(abs(lp), abs(rp), SIGNIFICANT_POWER_FLOOR)
        amplitude_error = abs(ra - la) / max(
            abs(la), abs(ra), AMPLITUDE_DENOMINATOR_FLOOR
        )
        rows.append(
            {
                "label": channel_label(key),
                "power_relative_error": power_error,
                "power_pass": power_error <= RELATIVE_TOLERANCE,
                "complex_amplitude_relative_error": amplitude_error,
                "complex_amplitude_pass": amplitude_error <= RELATIVE_TOLERANCE,
            }
        )
    power_count = sum(row["power_pass"] for row in rows)
    amplitude_count = sum(row["complex_amplitude_pass"] for row in rows)
    return {
        "left": left_name,
        "right": right_name,
        "semantics": "boundary-plane amplitude; symmetric relative denominator",
        "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "channel_count": len(rows),
        "power_pass_count": power_count,
        "complex_amplitude_pass_count": amplitude_count,
        "max_power_relative_error": max(row["power_relative_error"] for row in rows),
        "max_complex_amplitude_relative_error": max(
            row["complex_amplitude_relative_error"] for row in rows
        ),
        "pass": len(rows) == power_count == amplitude_count == 12,
        "channels": rows,
    }


def frozen_reference_gate(
    model: dict[str, Any],
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
) -> dict[str, Any]:
    observed = channel_map(model)
    rows = []
    for key in sorted(reference):
        frozen = reference[key]
        center = frozen["reference_center"]
        gate = frozen["unchanged_v0_acceptance_gate"]
        row = observed[key]
        amplitude = complex(*row["boundary_complex_amplitude"])
        center_amplitude = complex(*center["complex_amplitude"])
        power_error = abs(float(row["power"]) - float(center["power"]))
        amplitude_error = abs(amplitude - center_amplitude)
        rows.append(
            {
                "label": channel_label(key),
                "power_absolute_error": power_error,
                "power_absolute_tolerance": float(gate["power_absolute_tolerance"]),
                "power_pass": power_error <= float(gate["power_absolute_tolerance"]),
                "complex_amplitude_absolute_error": amplitude_error,
                "complex_amplitude_absolute_tolerance": float(
                    gate["complex_amplitude_absolute_tolerance"]
                ),
                "complex_amplitude_pass": amplitude_error
                <= float(gate["complex_amplitude_absolute_tolerance"]),
            }
        )
    power_count = sum(row["power_pass"] for row in rows)
    amplitude_count = sum(row["complex_amplitude_pass"] for row in rows)
    return {
        "channel_count": len(rows),
        "power_pass_count": power_count,
        "complex_amplitude_pass_count": amplitude_count,
        "pass": len(rows) == power_count == amplitude_count == 12,
        "channels": rows,
    }


def resource_pair(standard: dict[str, Any], static: dict[str, Any]) -> dict[str, Any]:
    saving = (
        float(standard["peak_memory_gib"]) - float(static["peak_memory_gib"])
    ) / float(standard["peak_memory_gib"])
    total_ratio = float(static["total_seconds"]) / float(standard["total_seconds"])
    modal_ratio = float(static["modal_coupling_seconds"]) / float(
        standard["modal_coupling_seconds"]
    )
    modal_memory_saving = (
        float(standard["modal_coupling_stage_peak_gib"])
        - float(static["modal_coupling_stage_peak_gib"])
    ) / float(standard["modal_coupling_stage_peak_gib"])
    return {
        "memory_saving_fraction": saving,
        "mandatory_15_percent_pass": saving >= 0.15,
        "preferred_25_percent_pass": saving >= 0.25,
        "user_target_50_percent_pass": saving >= 0.50,
        "active_row_saving_fraction": (
            int(standard["active_rows"]) - int(static["active_rows"])
        )
        / int(standard["active_rows"]),
        "matrix_nnz_saving_fraction": (
            int(standard["matrix_nnz"]) - int(static["matrix_nnz"])
        )
        / int(standard["matrix_nnz"]),
        "factor_nnz_saving_fraction": (
            int(standard["factor_nnz"]) - int(static["factor_nnz"])
        )
        / int(standard["factor_nnz"]),
        "modal_coupling_stage_memory_saving_fraction": modal_memory_saving,
        "static_to_standard_total_time_ratio": total_ratio,
        "total_time_1p35_gate_pass": total_ratio <= 1.35,
        "static_to_standard_modal_coupling_time_ratio": modal_ratio,
        "modal_time_is_report_only_not_hard_gate_by_user": True,
        "pass": saving >= 0.15 and total_ratio <= 1.35,
    }


def p6_six_path_record(
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
    reference_authority: dict[str, Any],
) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    for role, (name, expected_sha) in P6_MPI8_AUTHORITIES.items():
        loader = load_full if role.startswith("full_") else load_hybrid
        models[role] = loader(name, expected_sha, reference, P6_SOURCE_SHA)
    pair_names = [
        ("full_standard", "full_static"),
        ("hybrid_standard_m120", "hybrid_static_m120"),
        ("hybrid_standard_m160", "hybrid_static_m160"),
        ("full_standard", "hybrid_standard_m120"),
        ("full_standard", "hybrid_standard_m160"),
        ("full_static", "hybrid_static_m120"),
        ("full_static", "hybrid_static_m160"),
        ("hybrid_standard_m120", "hybrid_standard_m160"),
        ("hybrid_static_m120", "hybrid_static_m160"),
    ]
    comparisons = {
        f"{left}__vs__{right}": compare_models(
            left, models[left], right, models[right]
        )
        for left, right in pair_names
    }
    frozen = {
        name: frozen_reference_gate(model, reference)
        for name, model in models.items()
    }
    resources = {
        "m120_standard_vs_static": resource_pair(
            models["hybrid_standard_m120"], models["hybrid_static_m120"]
        ),
        "m160_standard_vs_static": resource_pair(
            models["hybrid_standard_m160"], models["hybrid_static_m160"]
        ),
    }
    return {
        "schema_version": "task035c.case096-p6-six-path.v1",
        "status": "p6_h10_mpi8_channel_and_resource_authority_pass",
        "pass": (
            all(item["pass"] for item in comparisons.values())
            and all(item["pass"] for item in frozen.values())
            and all(item["pass"] for item in resources.values())
        ),
        "numerical_source_sha": P6_SOURCE_SHA,
        "ordinary_default_changed": False,
        "identity": {
            "geometry": "Task034 fixed rectangular block grating",
            "degree": 6,
            "h_nm": 10.0,
            "mpi_size": 8,
            "p3_h7p5": {
                "status": "out_of_scope_by_user",
                "execution": "not_run",
                "completion_gate": False,
            },
        },
        "channel_semantics": {
            "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
            "relative_tolerance": RELATIVE_TOLERANCE,
            "complex_amplitude_field": BOUNDARY_AMPLITUDE_FIELD,
        },
        "significant_channel_reference_v1": reference_authority,
        "models": models,
        "pairwise_channel_comparisons": comparisons,
        "frozen_reference_v1_gates": frozen,
        "resource_comparisons": resources,
        "classification": {
            "physics": "12_of_12_power_and_12_of_12_boundary_amplitude_pass",
            "mandatory_static_hybrid_memory": "pass",
            "preferred_25_percent_static_hybrid_memory": "pass",
            "user_target_50_percent_static_hybrid_memory": "not_met",
            "total_time_1p35": "pass",
            "modal_coupling_time": "measured_and_minimized_not_hard_gate_by_user",
        },
    }


def p2_record(
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
    reference_authority: dict[str, Any],
) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    for role, (name, expected_sha) in P2_AUTHORITIES.items():
        loader = load_full if role == "full_static" else load_hybrid
        models[role] = loader(name, expected_sha, reference, P2_SOURCE_SHA)
    comparisons = {
        "full_static__vs__hybrid_static_m120": compare_models(
            "full_static",
            models["full_static"],
            "hybrid_static_m120",
            models["hybrid_static_m120"],
        ),
        "full_static__vs__hybrid_static_m160": compare_models(
            "full_static",
            models["full_static"],
            "hybrid_static_m160",
            models["hybrid_static_m160"],
        ),
        "hybrid_static_m120__vs__hybrid_static_m160": compare_models(
            "hybrid_static_m120",
            models["hybrid_static_m120"],
            "hybrid_static_m160",
            models["hybrid_static_m160"],
        ),
    }
    phase_models: dict[str, dict[str, Any]] = {}
    phase_sha = "1d9a712d87831dfe2202cc395126f00ec1b76760"
    for role, (name, expected_sha) in P2_PHASE_ONLY_AUTHORITIES.items():
        loader = load_full if role == "full_static" else load_hybrid
        phase_models[role] = loader(name, expected_sha, reference, phase_sha)
    phase_negative = compare_models(
        "full_static",
        phase_models["full_static"],
        "hybrid_static_m160_phase_only",
        phase_models["hybrid_static_m160_phase_only"],
    )
    return {
        "schema_version": "task035c.case096-p2-root-cause.v1",
        "status": "p2_h5_channel_root_cause_closed",
        "pass": all(item["pass"] for item in comparisons.values()),
        "numerical_source_sha": P2_SOURCE_SHA,
        "ordinary_default_changed": False,
        "identity": {
            "geometry": "Task034 fixed rectangular block grating",
            "degree": 2,
            "h_nm": 5.0,
            "mpi_size": 8,
        },
        "root_cause": {
            "plain_language": (
                "Full3D advances the field through the uniform z chain with the "
                "finite-element discrete phase and endpoint derivative, while the "
                "old Hybrid path used the continuous beta phase and traction."
            ),
            "internal_propagation_model": "full3d_uniform_cg",
            "internal_traction_model": "scalar_cg_discrete_derivative",
            "ordinary_default_remains": [
                "continuous_beta",
                "continuous_qep_beta",
            ],
        },
        "significant_channel_reference_v1": reference_authority,
        "models": models,
        "comparisons": comparisons,
        "phase_only_controlled_negative": {
            "classification": "controlled_negative",
            "pass": False,
            "expected_pass_counts": {"power": 4, "complex_amplitude": 4},
            "comparison": phase_negative,
            "models": phase_models,
        },
    }


def rank_record(
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
) -> dict[str, Any]:
    full: dict[str, dict[str, Any]] = {}
    hybrid: dict[str, dict[str, Any]] = {}
    for role, (name, expected_sha) in P6_RANK_AUTHORITIES.items():
        if role.startswith("full_"):
            full[role] = load_full(
                name, expected_sha, reference, P6_SOURCE_SHA
            )
        else:
            hybrid[role] = load_hybrid(
                name,
                expected_sha,
                reference,
                P6_SOURCE_SHA,
                require_formal=False,
            )
    mpi1 = hybrid["hybrid_static_m120_mpi1"]
    mpi2 = hybrid["hybrid_static_m120_mpi2"]
    mpi1_raw = load_json(ROOT / mpi1["raw_authority"]["solver_record_path"])
    mpi1_error = float(
        mpi1_raw["qep"]["positive"]["max_biorthogonality_identity_error"]
    )
    require(
        math.isclose(
            mpi1_error,
            1.1975997613347697e-6,
            rel_tol=0.0,
            abs_tol=1.0e-20,
        ),
        "MPI1 biorthogonality negative changed",
    )
    require(not mpi1["numeric_pass"], "MPI1 Hybrid unexpectedly became a numeric pass")
    require(mpi2["numeric_pass"], "MPI2 Hybrid is not a numeric pass")
    require(
        not mpi2["memory_authority_pass"],
        "MPI2 resource record unexpectedly became formal",
    )
    mpi8 = load_hybrid(
        *P6_MPI8_AUTHORITIES["hybrid_static_m120"],
        reference,
        P6_SOURCE_SHA,
    )
    return {
        "schema_version": "task035c.case096-static-rank-study.v1",
        "status": "rank_study_complete_with_controlled_negatives",
        "pass": True,
        "numerical_source_sha": P6_SOURCE_SHA,
        "full_static": {
            "mpi1": full["full_static_mpi1"],
            "mpi2": full["full_static_mpi2"],
            "mpi8": load_full(
                *P6_MPI8_AUTHORITIES["full_static"],
                reference,
                P6_SOURCE_SHA,
            ),
        },
        "hybrid_static_m120": {
            "mpi1": mpi1,
            "mpi2": mpi2,
            "mpi8": mpi8,
        },
        "classification": {
            "mpi1": {
                "status": "failed_numerical_gate",
                "failed_quantity": "positive_QEP_max_biorthogonality_identity_error",
                "actual": mpi1_error,
                "limit": 1.0e-6,
                "reason": "numerical gate failure, not a resource authority",
            },
            "mpi2": {
                "status": "numeric_pass_resource_nonformal",
                "numeric_pass": True,
                "resource_authority_pass": False,
                "reason": (
                    "terminal worker-drain sampling race made live RSS/swap "
                    "readability incomplete; measured peak is diagnostic only"
                ),
                "failed_resource_checks": [
                    "container_current_swap_zero_unreadable",
                    "all_live_authority_samples_readable",
                    "all_live_swap_samples_readable",
                ],
            },
            "mpi8": {
                "status": "formal_pass",
                "numeric_pass": True,
                "resource_authority_pass": True,
            },
        },
        "authority_boundary": (
            "MPI8 is the formal Task035c comparison point. MPI1 and MPI2 remain "
            "preserved rank evidence and are not used to overwrite MPI8 authority."
        ),
    }


def dependency_record() -> dict[str, Any]:
    failures = []
    for failure_id, (name, expected_sha, expected_text) in DEPENDENCY_FAILURES.items():
        path = ARTIFACTS / name
        record, observed = load_bound(path, expected_sha)
        raw_path = hybrid_raw_path(path, record)
        stdout_path = Path(record["stdout_ignored_path"])
        stdout_path = (
            stdout_path if stdout_path.is_absolute() else ROOT / stdout_path
        ).resolve()
        if expected_text is not None:
            text = stdout_path.read_text(encoding="utf-8", errors="replace")
            require(expected_text in text, f"{failure_id} expected exception is missing")
        failures.append(
            {
                "failure_id": failure_id,
                "classification": (
                    "failed_dependency_exception"
                    if expected_text is not None
                    else "resource_telemetry_terminal_race_superseded"
                ),
                "status": record["status"],
                "return_code": int(record["return_code"]),
                "numeric_pass": bool(record["numeric_pass"]),
                "memory_authority_pass": bool(record["memory_authority_pass"]),
                "source_sha": source_sha(record),
                "expected_exception": expected_text,
                "watchdog_path": rel(path),
                "watchdog_sha256": observed,
                "raw_solver_record_path": rel(raw_path),
                "raw_solver_record_exists": raw_path.is_file(),
                "stdout_path": rel(stdout_path),
                "stdout_sha256": sha256(stdout_path),
                "later_success_does_not_delete_this_evidence": True,
            }
        )
    return {
        "schema_version": "task035c.case096-dependency-failures.v1",
        "status": "preserved_failed_and_superseded_evidence",
        "ordinary_default_changed": False,
        "failures": failures,
    }


def execution_ledger(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "task035c.case096-execution-ledger.v1",
        "status": "task035c_compact_execution_ledger",
        "ordinary_default": "standard_full",
        "ordinary_default_changed": False,
        "task_scope": "Hybrid 12-channel accuracy and static-Hybrid memory closure",
        "entries": [
            {
                "lane": "p2_h5_root_cause",
                "classification": "completed_positive",
                "record": "records/p2_h5_root_cause_v1.json",
                "status": records["p2_h5_root_cause_v1.json"]["status"],
            },
            {
                "lane": "p6_h10_six_path_mpi8",
                "classification": "completed_positive",
                "record": "records/p6_h10_mpi8_six_path_v1.json",
                "status": records["p6_h10_mpi8_six_path_v1.json"]["status"],
            },
            {
                "lane": "p6_h10_rank_lifecycle",
                "classification": "completed_with_controlled_negatives",
                "record": "records/p6_h10_static_rank_study_v1.json",
                "status": records["p6_h10_static_rank_study_v1.json"]["status"],
            },
            {
                "lane": "p6_h10_pss_uss_backfill",
                "classification": "completed_from_existing_raw_timeline_no_pde_rerun",
                "record": "records/p6_h10_mpi8_pss_uss_ledger_v1.json",
                "status": records["p6_h10_mpi8_pss_uss_ledger_v1.json"]["status"],
            },
            {
                "lane": "dependency_failures",
                "classification": "preserved_failed_evidence",
                "record": "records/dependency_failures_v1.json",
                "status": records["dependency_failures_v1.json"]["status"],
            },
            {
                "lane": "p3_h7p5",
                "classification": "out_of_scope_by_user",
                "execution": "not_run",
                "completion_gate": False,
            },
        ],
        "closed_scope_guards": {
            "irregular_geometry": "not_run",
            "h13_adaptive_hybrid": "not_run",
            "tetra_or_mixed_static_condensation": "not_run",
            "production_selective_trace": "not_promoted",
            "condensed_iterative": "not_researched",
        },
    }


def write_or_check(path: Path, payload: dict[str, Any], check: bool) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if check:
        require(path.is_file(), f"{rel(path)} does not exist")
        require(
            path.read_text(encoding="utf-8") == encoded,
            f"{rel(path)} differs from regenerated raw evidence",
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless tracked compact records exactly match raw regeneration",
    )
    args = parser.parse_args()
    reference, reference_authority = significant_reference()
    payloads = {
        "p2_h5_root_cause_v1.json": p2_record(
            reference, reference_authority
        ),
        "p6_h10_mpi8_six_path_v1.json": p6_six_path_record(
            reference, reference_authority
        ),
        "p6_h10_static_rank_study_v1.json": rank_record(reference),
        "p6_h10_mpi8_pss_uss_ledger_v1.json": p6_pss_uss_record(),
        "dependency_failures_v1.json": dependency_record(),
    }
    payloads["execution_ledger_v1.json"] = execution_ledger(payloads)
    for name, payload in payloads.items():
        write_or_check(RECORDS / name, payload, args.check)
    manifest_records = []
    for name in sorted(payloads):
        path = RECORDS / name
        manifest_records.append(
            {
                "name": name,
                "sha256": sha256(path),
                "schema_version": payloads[name]["schema_version"],
                "status": payloads[name]["status"],
            }
        )
    manifest = {
        "schema_version": "task035c.case096-compact-authority.v1",
        "status": "case096_compact_authority",
        "numerical_source_sha": P6_SOURCE_SHA,
        "p2_diagnostic_source_sha": P2_SOURCE_SHA,
        "ordinary_default_changed": False,
        "significant_channel_reference_v1": reference_authority,
        "generator": rel(Path(__file__)),
        "record_count": len(manifest_records),
        "records": manifest_records,
        "not_promoted": [
            "irregular_geometry",
            "p3_h7p5",
            "h13_adaptive_hybrid",
            "production_selective_trace",
            "tetra_or_mixed_static_condensation",
            "condensed_iterative",
        ],
    }
    write_or_check(RECORDS / "compact_authority_v1.json", manifest, args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
