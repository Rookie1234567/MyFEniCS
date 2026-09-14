"""Executable, opt-in V16 p4 BLR control worker.

This worker intentionally reuses the reviewed V14 mesh, map, RHS and metric
builders.  It owns only the V16 stage ledger and the one global BLR factor;
the historical V14 ledger is never opened for writing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import signal
import time
from typing import Any, Mapping

import numpy as np

from src.io.input_validation import simulation_config_3d_from_normalized
from src.io.physical_intermediate_profile import (
    P4_BLR_PROFILE,
    P4_BLR_TRADEOFF_PROFILE,
    profile_facts,
    p4_blr_tradeoff_threshold,
)
from src.solvers.fullspace_p4_blr import augmented_residual_identity
from src.solvers.fullspace_v17_p3_oracle import configured_mumps_blr_factor
from src.solvers.physical_interface_schur import _prepare_factor

from .physical_p4_schur_v14 import (
    V14ResourceStop,
    _Q1_Q2_RHS,
    _V14Runtime,
    _abi_facts,
    _build_common,
    _destroy_common,
    _field_metrics,
    _jsonable,
    _load_rhs_and_reference,
    _matrix_residual_vector,
    _prepare_reviewed_rhs,
    _repo_root,
    _save_packet,
    _sha256_bytes,
    _factor_gates,
    _q1_residual_arrays,
    _sparse_payload_bytes,
    _v14_known_preallocation_gate,
    _write_json,
)


Q1_BRIDGE_PATH = Path(
    "benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/q1_baseline_live_scope.json"
)
Q1_BRIDGE_ARTIFACT_NAMES = (
    "v14_events.jsonl",
    "watchdog/resources.jsonl",
    "physical_p4_schur_v14_summary.json",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def bridge_q1_baseline(root: Path, runtime: _V14Runtime) -> dict[str, Any]:
    """Admit the existing Q1 live-factor scope record without rerunning it."""

    path = root / Q1_BRIDGE_PATH
    checks: dict[str, Any] = {}
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        data = {}
        errors.append(f"bridge record unreadable: {type(exc).__name__}: {exc}")
    checks["bridge_record_exists"] = path.is_file()
    # These fields are retained as provenance about the root-engineering
    # handoff, but they are not admission inputs.  The raw event/resource
    # files below are re-parsed and re-measured independently.
    checks["engineering_claims"] = {
        key: data.get(key)
        for key in (
            "factor_and_matrix_retained",
            "all_samples_readable",
            "R_live_denominator_rss_bytes",
            "R_peak_denominator_rss_bytes",
            "full_pss_peak_bytes",
            "live_pss_peak_bytes",
            "readable_live_sample_count",
        )
    }
    checks["interval_events"] = (
        data.get("interval_start_event") == "schur_factor_numeric_complete"
        and data.get("interval_end_event") == "v14_field_metrics_complete"
    )
    if not checks["interval_events"]:
        errors.append("Q1 interval does not cover post-numeric through field metrics")

    baseline_value = data.get("baseline_dir")
    baseline = root / str(baseline_value) if baseline_value else Path("/")
    baseline = baseline.resolve()
    checks["baseline_directory_exists"] = baseline.is_dir()
    if not checks["baseline_directory_exists"]:
        errors.append(f"Q1 baseline directory is missing: {baseline}")

    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("JSONL row is not an object")
                rows.append(value)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"raw record unreadable: {path.name}: {exc}")
        return rows

    raw_events = read_jsonl(baseline / "v14_events.jsonl")
    # The parent watchdog's process-tree stream is the authoritative resource
    # scope.  The worker stream is retained only as auxiliary evidence; it is
    # not interchangeable with the parent R_live/R_peak measurement.
    raw_resources = read_jsonl(baseline / "watchdog" / "resources.jsonl")
    worker_resources = read_jsonl(baseline / "v14_worker_resources.jsonl")
    numeric_events = [
        item for item in raw_events if item.get("event") == "schur_factor_numeric_complete"
    ]
    field_events = [
        item for item in raw_events if item.get("event") == "v14_field_metrics_complete"
    ]
    rhs_load_events = [
        item for item in raw_events if item.get("event") == "v14_reviewed_rhs_loading_complete"
    ]
    augmentation_events = [
        item for item in raw_events if item.get("event") == "reference_augmentation_complete"
    ]
    checks["raw_event_cardinality"] = (
        len(numeric_events) == 1
        and len(field_events) == 1
        and len(rhs_load_events) == 1
        and len(augmentation_events) == 1
    )
    if not checks["raw_event_cardinality"]:
        errors.append("raw Q1 event cardinality is not exactly one for each required scope event")
    if numeric_events and field_events:
        start_ns = int(numeric_events[0].get("timestamp_ns", -1))
        end_ns = int(field_events[0].get("timestamp_ns", -1))
    else:
        start_ns = end_ns = -1
    def resource_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "sample_count": len(rows),
            "rss_peak_bytes": max(
                (int(item.get("rss_bytes", 0)) for item in rows), default=0
            ),
            "pss_peak_bytes": max(
                (int(item.get("pss_bytes", 0)) for item in rows), default=0
            ),
            "swap_peak_bytes": max(
                (int(item.get("swap_bytes", 0)) for item in rows), default=0
            ),
            "all_status_readable": bool(
                rows and all(item.get("all_status_readable") is True for item in rows)
            ),
            "all_pss_readable": bool(
                rows and all(item.get("pss_all_readable") is True for item in rows)
            ),
        }

    window_resources = [
        item
        for item in raw_resources
        if start_ns <= int(item.get("timestamp_ns", -2)) <= end_ns
    ]
    full_stats = resource_stats(raw_resources)
    window_stats = resource_stats(window_resources)
    tree_caps = [
        int(item.get("watchdog_tree_cap_bytes", item.get("launch_cap_bytes", 0)))
        for item in raw_resources
    ]
    tree_cap = min((value for value in tree_caps if value > 0), default=0)
    dynamic_cap_checks = bool(
        raw_resources
        and all(
            int(item.get("rss_bytes", 0)) < int(item.get("launch_cap_bytes", 0))
            and int(item.get("pss_bytes", 0)) < int(item.get("launch_cap_bytes", 0))
            for item in raw_resources
        )
    )
    checks["raw_window"] = bool(
        start_ns >= 0
        and end_ns >= start_ns
        and window_resources
        and full_stats["all_status_readable"]
        and full_stats["all_pss_readable"]
        and window_stats["all_status_readable"]
        and window_stats["all_pss_readable"]
        and full_stats["swap_peak_bytes"] == 0
        and window_stats["swap_peak_bytes"] == 0
        and tree_cap > 0
        and dynamic_cap_checks
        and full_stats["rss_peak_bytes"] <= tree_cap
        and full_stats["pss_peak_bytes"] <= tree_cap
        and window_stats["rss_peak_bytes"] <= tree_cap
        and window_stats["pss_peak_bytes"] <= tree_cap
    )
    if not checks["raw_window"]:
        errors.append("raw Q1 watchdog resource stream does not satisfy the live scope")
    checks["raw_resource_window"] = {
        "start_timestamp_ns": start_ns,
        "end_timestamp_ns": end_ns,
        "scope": "parent_watchdog_process_tree",
        "tree_cap_bytes": tree_cap,
        "dynamic_launch_caps_satisfied": dynamic_cap_checks,
        "full": full_stats,
        "window": window_stats,
        "rss_ratio_to_tree_cap": window_stats["rss_peak_bytes"] / float(tree_cap)
        if window_stats["rss_peak_bytes"]
        else None,
        "pss_ratio_to_tree_cap": window_stats["pss_peak_bytes"] / float(tree_cap)
        if window_stats["pss_peak_bytes"]
        else None,
        "worker_stream_auxiliary": resource_stats(worker_resources),
    }

    raw_numeric = numeric_events[0].get("facts", {}) if numeric_events else {}
    raw_controls_before = raw_numeric.get("symbolic_memory_settings", {})
    raw_controls_after = raw_numeric.get("symbolic_memory_settings_after_memory_limit", {})
    checks["raw_icntl10_zero"] = (
        raw_controls_before.get("icntl", {}).get("10") == 0
        and raw_controls_after.get("icntl", {}).get("10") == 0
    )
    if not checks["raw_icntl10_zero"]:
        errors.append("raw Q1 MUMPS control readback does not prove ICNTL(10)=0")
    raw_matrix = augmentation_events[0].get("facts", {}) if augmentation_events else {}
    checks["raw_matrix_identity"] = all(
        raw_matrix.get(key) == expected
        for key, expected in {
            "fe_rows": 53084,
            "port_rows": 80,
            "augmented_rows": 53164,
            "allocated_nnz": 24730144,
            "preallocated_nnz": 24730144,
        }.items()
    )
    if not checks["raw_matrix_identity"]:
        errors.append("raw Q1 augmentation rows/NNZ do not match the reviewed matrix")

    summary: dict[str, Any] = {}
    summary_path = baseline / "physical_p4_schur_v14_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"Q1 worker summary is unreadable: {exc}")
    summary_rhs = summary.get("rhs", [])
    summary_solves = summary.get("solve_records", [])
    expected_stems = [item["stem"] for item in _Q1_Q2_RHS]
    summary_rhs_by_stem = {
        item.get("stem"): item for item in summary_rhs if isinstance(item, dict)
    }
    summary_solves_by_stem = {
        item.get("stem"): item for item in summary_solves if isinstance(item, dict)
    }
    checks["summary_rhs_order"] = (
        isinstance(summary_rhs, list)
        and [item.get("stem") for item in summary_rhs] == expected_stems
        and isinstance(summary_solves, list)
        and [item.get("stem") for item in summary_solves] == expected_stems
    )
    if not checks["summary_rhs_order"]:
        errors.append("Q1 summary RHS/solve records do not bind the reviewed stem order")

    def resolve_root_path(value: Any) -> Path:
        candidate = Path(str(value))
        return candidate if candidate.is_absolute() else root / candidate

    def hash_identity_path(
        value: Any, expected: Any, label: str
    ) -> dict[str, Any]:
        target = resolve_root_path(value)
        actual = _sha256_file(target) if target.is_file() else None
        passed = isinstance(expected, str) and actual == expected
        if not passed:
            errors.append(f"Q1 {label} hash mismatch or missing: {target}")
        return {
            "path": str(target),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "passed": passed,
        }

    packet_checks: dict[str, Any] = {}
    for item in _Q1_Q2_RHS:
        packet_path = baseline / "q1_rhs_packets" / f"{item['stem']}.json"
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            array_path = resolve_root_path(packet["arrays"]["path"])
            array_sha = _sha256_file(array_path)
            solve = packet["solve"]
            identity = packet["identity"]
            calibration = identity["calibration_identity"]
            summary_rhs_record = summary_rhs_by_stem.get(item["stem"], {})
            summary_solve = summary_solves_by_stem.get(item["stem"], {})
            summary_packet = summary_solve.get("packet", {})
            summary_field = summary_solve.get("field_metrics", {})
            input_identity = {
                "input_json": hash_identity_path(
                    item["input_json"], item["input_sha256"], f"{item['stem']} input metadata"
                ),
                "input_npz": hash_identity_path(
                    str(Path(item["input_json"]).with_suffix(".npz")),
                    item["input_npz_sha256"],
                    f"{item['stem']} input array",
                ),
                "reference_json": hash_identity_path(
                    item["reference_json"],
                    item["reference_json_sha256"],
                    f"{item['stem']} reference metadata",
                ),
                "reference_npz": hash_identity_path(
                    str(
                        Path(
                            json.loads(
                                resolve_root_path(item["reference_json"])
                                .read_text(encoding="utf-8")
                            )["arrays"]["path"]
                        )
                    ),
                    item["reference_npz_sha256"],
                    f"{item['stem']} reference array",
                ),
            }
            summary_identity = (
                summary_rhs_record.get("input_sha256") == item["input_sha256"]
                and summary_rhs_record.get("input_npz_sha256") == item["input_npz_sha256"]
                and summary_rhs_record.get("reference_json_sha256")
                == item["reference_json_sha256"]
                and summary_rhs_record.get("reference_npz_sha256")
                == item["reference_npz_sha256"]
                and summary_rhs_record.get("g_sha256") == item["g_sha256"]
                and summary_rhs_record.get("logical_rhs") == item["logical_rhs"]
            )
            packet_identity = (
                calibration.get("input_sha256") == item["input_sha256"]
                and identity.get("g_sha256") == item["g_sha256"]
                and identity.get("logical_rhs") == item["logical_rhs"]
                and identity.get("stem") == item["stem"]
            )
            passed = (
                array_sha == packet["arrays"]["sha256"]
                and array_sha == summary_packet.get("arrays", {}).get("sha256")
                and summary_identity
                and packet_identity
                and all(value["passed"] for value in input_identity.values())
                and solve.get("factor_solve_call_delta") == 1
                and float(solve.get("native_A4_relative_residual")) <= 1.0e-10
                and float(solve.get("matrix_relative_residual")) <= 1.0e-8
                and float(solve.get("augmented_total_relative_residual")) <= 1.0e-8
                and float(summary_field.get("field_l2_relative")) <= 1.0e-8
                and float(summary_field.get("scaled_curl_relative")) <= 1.0e-8
            )
            packet_checks[item["stem"]] = {
                "packet_path": str(packet_path),
                "array_path": str(array_path),
                "packet_json_sha256": _sha256_file(packet_path),
                "array_sha256": array_sha,
                "input_identity": input_identity,
                "summary_identity": summary_identity,
                "packet_identity": packet_identity,
                "native_A4_relative_residual": solve.get("native_A4_relative_residual"),
                "matrix_relative_residual": solve.get("matrix_relative_residual"),
                "augmented_total_relative_residual": solve.get("augmented_total_relative_residual"),
                "field_l2_relative": summary_field.get("field_l2_relative"),
                "scaled_curl_relative": summary_field.get("scaled_curl_relative"),
                "passed": passed,
            }
            if not passed:
                errors.append(
                    "raw Q1 RHS packet/summary/hash checks failed: "
                    f"{item['stem']}"
                )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            packet_checks[item["stem"]] = {"passed": False, "error": str(exc)}
            errors.append(f"raw Q1 RHS packet is unreadable: {item['stem']}: {exc}")
    checks["raw_rhs_packets"] = all(item.get("passed") is True for item in packet_checks.values())
    if rhs_load_events:
        facts = rhs_load_events[0].get("facts", {})
        checks["raw_rhs_order"] = facts.get("count") == 3 and facts.get(
            "ordered_stems"
        ) == [item["stem"] for item in _Q1_Q2_RHS]
    else:
        checks["raw_rhs_order"] = False
    if not checks["raw_rhs_order"]:
        errors.append("raw Q1 reviewed RHS loader did not prove the three ordered inputs")
    artifact_checks: dict[str, Any] = {}
    expected_hashes = data.get("artifact_hashes", {})
    for name in Q1_BRIDGE_ARTIFACT_NAMES:
        artifact = baseline / name
        expected = expected_hashes.get(name)
        actual = _sha256_file(artifact) if artifact.is_file() else None
        passed = isinstance(expected, str) and actual == expected
        artifact_checks[name] = {
            "path": str(artifact),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "passed": passed,
        }
        if not passed:
            errors.append(f"Q1 artifact hash mismatch or missing: {name}")
    checks["artifact_hashes"] = all(item["passed"] for item in artifact_checks.values())

    checks["summary_scope"] = all(
        summary.get(key) == expected
        for key, expected in {
            "profile": "physical_p4_schur_v14",
            "stage": "Q1_FULL_DIRECT",
        }.items()
    )
    if not checks["summary_scope"]:
        errors.append("Q1 worker summary is not the Q1 full-direct scope")
    checks["summary_claims"] = {
        key: summary.get(key) for key in ("official_result", "stage_pass", "status")
    }
    source_sha = data.get("source_sha")
    checks["source_sha_valid"] = (
        isinstance(source_sha, str)
        and len(source_sha) == 40
        and source_sha == summary.get("source_sha")
    )
    if not checks["source_sha_valid"]:
        errors.append("Q1 bridge source SHA does not bind the worker summary")
    record = {
        "schema": "task039extra.v16.s1-q1-bridge.v1",
        "stage": "S1_CONTROL",
        "status": "S1_Q1_BRIDGE_PASS" if not errors else "S1_Q1_BRIDGE_REJECTED",
        "official_result": False,
        "bridge_only": True,
        "historical_baseline_not_rerun": True,
        "source_sha": runtime.source_sha,
        "historical_source_sha": source_sha,
        "record_path": str(path),
        "record_sha256": _sha256_file(path) if path.is_file() else None,
        "checks": checks,
        "artifact_checks": artifact_checks,
        "packet_checks": packet_checks,
        "errors": errors,
        "passed": not errors,
    }
    runtime.marker("v16_s1_q1_bridge_complete", record)
    _save_packet(runtime.directory, "s1_q1_bridge", record, runtime=runtime)
    return record


def _s2_preallocation_callback(runtime: _V14Runtime):
    def callback(facts: Mapping[str, Any]) -> None:
        matrix_payload = int(facts["matrix_payload_bytes"])
        volume_rows = int(facts["volume_rows"])
        volume_nnz = int(facts["volume_nnz"])
        volume_payload = _sparse_payload_bytes(
            {"nz_allocated": volume_nnz}, volume_rows
        )
        workspace = min(
            int(runtime.workspace_cap),
            16 * (volume_rows + int(facts["port_rows"])) * 16,
        )
        runtime.check_inventory_projected(
            "s2_augmented_matrix",
            volume_payload + matrix_payload,
        )
        runtime.check_projected(
            "s2_augmented_matrix",
            matrix_payload,
            workspace_bytes=workspace,
        )
        runtime.reserve_workspace("s2_augmented_matrix_workspace", workspace)

    return callback


def _s2_blr_control(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
    *,
    profile: str = P4_BLR_PROFILE,
    threshold: float = 1.0e-5,
    evidence_prefix: str = "v16",
    control_stage: str = "S2_BLR_CONTROL",
    packet_directory: str = "s2_rhs_packets",
    enable_coverage_statistics: bool = False,
) -> dict[str, Any]:
    from src.solvers.fullspace_p4_reference import build_reference_matrix

    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"{profile} p4 carrier storage rows changed: {storage_rows}")
    matrix = None
    factor = None
    factor_facts: dict[str, Any] | None = None
    solve_records: list[dict[str, Any]] = []
    workspace_label = "s2_augmented_matrix_workspace"
    factor_label = (
        "s2_p4_blr_global"
        if evidence_prefix == "v16"
        else f"{control_stage.lower()}_p4_blr_global"
    )
    packet_schema = (
        "task039extra.v16.s2-blr-rhs-packet.v1"
        if evidence_prefix == "v16"
        else f"task039extra.{evidence_prefix}.{control_stage.lower()}.rhs-packet.v1"
    )
    record_schema = (
        "task039extra.v16.s2-blr-control.v1"
        if evidence_prefix == "v16"
        else f"task039extra.{evidence_prefix}.{control_stage.lower()}.v1"
    )
    record_stem = (
        "s2_blr_control"
        if evidence_prefix == "v16"
        else f"{evidence_prefix}_{control_stage.lower()}"
    )
    runtime.set_phase("assembly")
    try:
        matrix, matrix_facts = build_reference_matrix(
            common["levels"],
            common["cfg"],
            common["p4"],
            common["quadrature"],
            marker=runtime.marker,
            sample=lambda: runtime.sample("s2_assembly"),
            degree=4,
            allocation_callback=_s2_preallocation_callback(runtime),
        )
        runtime.release_workspace(workspace_label)
        if int(matrix.getSize()[0]) != storage_rows + len(common["p4"]["dtn_action"].carrier.entries):
            raise ValueError(f"{profile} augmented matrix row count changed")
        before, after = _factor_gates(runtime)
        runtime.set_phase("factor")
        factor_factory = (
            configured_mumps_blr_factor
            if evidence_prefix == "v16"
            else lambda value: configured_mumps_blr_factor(
                value,
                profile=profile,
                threshold=threshold,
                enable_coverage_statistics=enable_coverage_statistics,
            )
        )
        factor, factor_facts = _prepare_factor(
            matrix,
            factor_factory,
            label=factor_label,
            resource_sample=lambda: runtime.sample("s2_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
        )
        runtime.sample("s2_post_numeric_factor_live")
        for reviewed in rhs_records:
            if runtime.stop_requested:
                raise V14ResourceStop(
                    f"{profile} stop requested before the next RHS"
                )
            runtime.set_phase("solve")
            started = time.perf_counter()
            rhs = matrix.createVecRight()
            solution = matrix.createVecRight()
            residual = None
            try:
                rhs.set(0)
                rhs.array[:storage_rows] = reviewed["rhs"]
                rhs_before = np.asarray(rhs.array).copy()
                mat_solve_started = time.perf_counter()
                solve_facts = factor.solve_once(rhs, solution)
                mat_solve_seconds = time.perf_counter() - mat_solve_started
                np.testing.assert_array_equal(rhs.array, rhs_before)

                native_started = time.perf_counter()
                residual = _matrix_residual_vector(matrix, rhs, solution)
                matrix_relative_residual = float(residual.norm()) / max(
                    float(rhs.norm()), np.finfo(float).tiny
                )
                facts, raw_native_a4, raw_native_volume, raw_augmented_top, raw_port = _q1_residual_arrays(
                    common, reviewed, solution, storage_rows
                )
                # _q1_residual_arrays is a historical V14 helper whose raw
                # orientation is A4*c-g, V*c-g, V*c-g+B*alpha and
                # -D*c+H*alpha.  V16 packets use the contract orientation
                # g-A4*c, g-V*c, g-V*c-B*alpha and D*c-H*alpha.
                native_a4 = -np.asarray(raw_native_a4, dtype=np.complex128)
                native_volume = -np.asarray(raw_native_volume, dtype=np.complex128)
                augmented_top = -np.asarray(raw_augmented_top, dtype=np.complex128)
                port = -np.asarray(raw_port, dtype=np.complex128)
                facts = dict(facts)
                facts["raw_residual_orientation"] = {
                    "native_A4": "A4*c-g",
                    "native_volume_top": "V*c-g",
                    "augmented_top": "V*c-g+B*alpha",
                    "port": "-D*c+H*alpha",
                }
                facts["reported_residual_orientation"] = {
                    "native_A4": "g-A4*c",
                    "native_volume_top": "g-V*c",
                    "augmented_top": "g-V*c-B*alpha",
                    "port": "D*c-H*alpha",
                }
                native_action = np.asarray(
                    reviewed["rhs"] - native_a4, dtype=np.complex128
                )
                identity = augmented_residual_identity(
                    native_a4,
                    augmented_top,
                    port,
                    common["p4"]["dtn_action"].carrier,
                    rhs_norm=float(facts["rhs_norm"]),
                    native_action_norm=float(np.linalg.norm(native_action)),
                )
                solution_array = np.asarray(solution.array[:storage_rows]).copy()
                native_evaluation_seconds = time.perf_counter() - native_started

                field_started = time.perf_counter()
                field = _field_metrics(
                    runtime,
                    common,
                    [solution_array],
                    [reviewed["reference_solution"]],
                )[0]
                field_metric_seconds = time.perf_counter() - field_started
                solve_after = int(getattr(factor, "solve_calls", 0))
                solve_record = {
                    "stem": reviewed["stem"],
                    "logical_rhs": int(reviewed["logical_rhs"]),
                    "elapsed_seconds": None,
                    "elapsed_seconds_semantics": (
                        "full_rhs_mat_solve_plus_native_evaluation_plus_field_metric_plus_packet_save"
                    ),
                    "mat_solve_seconds": mat_solve_seconds,
                    "native_evaluation_seconds": native_evaluation_seconds,
                    "field_metric_seconds": field_metric_seconds,
                    "packet_save_seconds": None,
                    "matrix_relative_residual": matrix_relative_residual,
                    "native_A4_relative_residual": float(facts["native_A4_relative"]),
                    "augmented_residual": facts,
                    "native_residual_identity": identity,
                    "field_metrics": field,
                    "factor_solve_calls_before": int(solve_facts["factor_solve_calls_before"]),
                    "factor_solve_calls_after": solve_after,
                    "factor_solve_call_delta": int(solve_facts["factor_solve_call_delta"]),
                    "controls_after_solve": solve_facts["controls_after_solve"],
                    "rhs_input_unchanged": bool(np.array_equal(rhs.array, rhs_before)),
                    "solution_sha256": _sha256_bytes(
                        np.ascontiguousarray(solution.array).tobytes()
                    ),
                }
                if evidence_prefix != "v16":
                    solve_record["hidden_refinement"] = bool(
                        solve_facts.get("hidden_refinement", False)
                    )
                packet_save_started = time.perf_counter()
                packet_facts = {
                    "schema": packet_schema,
                    "identity": {
                        key: value
                        for key, value in reviewed.items()
                        if key
                        not in {"rhs", "reference_solution", "reference_A4y", "reference_map"}
                    },
                    "solve": solve_record,
                    "x_augmented": np.asarray(solution.array).copy(),
                    "x_storage": solution_array,
                    "native_A4_residual": native_a4,
                    "native_volume_top_residual": native_volume,
                    "augmented_top_residual": augmented_top,
                    "port_residual": port,
                    "raw_native_A4_residual": raw_native_a4,
                    "raw_native_volume_top_residual": raw_native_volume,
                    "raw_augmented_top_residual": raw_augmented_top,
                    "raw_port_residual": raw_port,
                }
                if evidence_prefix != "v16":
                    # These are already-live vectors used for the native
                    # residual and identity norm.  Keep the exact objects in
                    # the V17 packet; V16's packet lifecycle is unchanged.
                    packet_facts.update(
                        {
                            "g": reviewed["rhs"],
                            "native_action": native_action,
                        }
                    )
                packet = _save_packet(
                    runtime.directory / packet_directory,
                    reviewed["stem"],
                    packet_facts,
                    runtime=runtime,
                )
                solve_record["packet_save_seconds"] = (
                    time.perf_counter() - packet_save_started
                )
                solve_record["elapsed_seconds"] = time.perf_counter() - started
                # The first packet write necessarily precedes the final timing
                # values.  Refresh the compact JSON atomically so the packet
                # itself carries the same complete per-RHS control/timing
                # record as the in-memory engineering record.
                packet["solve"] = dict(solve_record)
                _write_json(
                    runtime.directory / packet_directory / f"{reviewed['stem']}.json",
                    packet,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
            finally:
                if residual is not None:
                    residual.destroy()
                rhs.destroy()
                solution.destroy()
            runtime.sample(f"s2_rhs_{reviewed['stem']}_complete")
        runtime.sample("s2_third_evaluation_complete_factor_matrix_live")
        factor_live_window = {
            "start": "post_numeric_factor_live",
            "end": "third_evaluation_complete_factor_matrix_live",
            "factor_live_through_all_three": True,
            "matrix_live_through_all_three": True,
            "rhs_count": len(solve_records),
        }
        gates = {
            "one_factor": bool(factor_facts and factor_facts.get("factor_solve_calls_at_factorization") == 0),
            "rhs_count": len(solve_records) == 3,
            "sequential_rhs": [item["stem"] for item in solve_records]
            == [item["stem"] for item in rhs_records],
            "one_mat_solve_per_rhs": all(
                item["factor_solve_call_delta"] == 1 for item in solve_records
            ),
            "rhs_inputs_unchanged": all(
                item["rhs_input_unchanged"] for item in solve_records
            ),
            "solve_control_readback": all(
                item.get("controls_after_solve", {})
                .get("icntl", {})
                .get("10", {})
                .get("value")
                == 0
                and item.get("controls_after_solve", {})
                .get("icntl", {})
                .get("35", {})
                .get("value")
                == 2
                and item.get("controls_after_solve", {})
                .get("cntl", {})
                .get("7", {})
                .get("value")
                == float(threshold)
                for item in solve_records
            ),
            "timing_fields": all(
                all(
                    np.isfinite(float(item.get(key)))
                    and float(item.get(key)) >= 0.0
                    for key in (
                        "elapsed_seconds",
                        "mat_solve_seconds",
                        "native_evaluation_seconds",
                        "field_metric_seconds",
                        "packet_save_seconds",
                    )
                )
                for item in solve_records
            ),
            "native_identity": all(
                item["native_residual_identity"]["passed"] for item in solve_records
            ),
            "finite_quality_values": all(
                np.isfinite([
                    item["native_A4_relative_residual"],
                    item["field_metrics"]["field_l2_relative"],
                    item["field_metrics"]["scaled_curl_relative"],
                ]).all() for item in solve_records
            ),
            "native_A4_relative_residual": max(
                (item["native_A4_relative_residual"] for item in solve_records),
                default=float("inf"),
            ) <= 0.5,
            "field_l2_and_scaled_curl": max(
                max(
                    item["field_metrics"]["field_l2_relative"],
                    item["field_metrics"]["scaled_curl_relative"],
                )
                for item in solve_records
            ) <= 0.25
            if solve_records
            else False,
        }
        record = {
            "schema": record_schema,
            "stage": control_stage,
            "status": f"{control_stage}_PASS" if all(gates.values()) else f"{control_stage}_REJECTED",
            "official_result": False,
            "stage_pass": bool(all(gates.values())),
            "result_classification": "DISCRETE_SOLVER_OUTPUT_PASS"
            if all(gates.values())
            else "NUMERICAL_GATE_REJECTED",
            "matrix": matrix_facts,
            "factor": factor_facts,
            "solve_records": solve_records,
            "factor_live_window": factor_live_window,
            "gates": gates,
            "memory_policy": "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
            "evidence_paths": {
                "events": str(runtime.events_path),
                "resources": str(runtime.resources_path),
                "parent_resources": str(runtime.directory / "watchdog" / "resources.jsonl"),
                "inventory": str(runtime.inventory_path),
                "rhs_packets": str(runtime.directory / packet_directory),
            },
            "inventory_cap_bytes": int(runtime.inventory_cap),
            "shared_temp_workspace_cap_bytes": int(runtime.workspace_cap),
        }
        if evidence_prefix != "v16":
            record.update(
                {
                    "blr_threshold": float(threshold),
                    "coverage_statistics_requested": bool(enable_coverage_statistics),
                }
            )
            runtime.marker(f"{evidence_prefix}_{control_stage.lower()}_complete", record)
        else:
            runtime.marker("v16_s2_blr_control_complete", record)
        _save_packet(runtime.directory, record_stem, record, runtime=runtime)
        return record
    finally:
        try:
            if factor is not None:
                factor.destroy()
        finally:
            if matrix is not None:
                matrix.destroy()
        # This entry covers BOTH the factor and the matrix. An exception in
        # either destroy must not falsely clear its inventory observation.
        runtime.release_inventory(factor_label)
        runtime.release_workspace(workspace_label)


def _not_run_stage(stage: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "task039extra.v16.stage-record.v1",
        "stage": str(stage),
        "status": "NOT_RUN",
        "official_result": False,
        "stage_pass": False,
        "result_classification": "NOT_RUN",
        "reason": str(reason),
    }


def _run_physical_p4_blr(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    profile: str,
    batch_identity: str,
    evidence_prefix: str,
    control_stages: tuple[str, ...],
    fixed_threshold: float | None = None,
    enable_coverage_statistics: bool = False,
) -> dict[str, Any]:
    """Run the shared p4 BLR control wiring for one reviewed profile."""

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    contract = profile_facts(profile)
    stage = str(resolved_payload.get("solver", {}).get("stage"))
    summary: dict[str, Any] = {
        "schema": f"task039extra.{evidence_prefix}.worker-summary.v1",
        "profile": profile,
        "stage": stage,
        "source_sha": source_sha,
        "status": "STARTED",
        "official_result": False,
    }
    runtime = None
    common = None
    rhs_records: list[dict[str, Any]] | None = None
    handlers: dict[int, Any] = {}
    try:
        if resolved_payload.get("dimension") != 3:
            raise ValueError(f"{profile} requires dimension=3")
        if resolved_payload.get("method", {}).get("kind") != "full3d_iterative":
            raise ValueError(f"{profile} requires method.kind=full3d_iterative")
        if resolved_payload.get("solver", {}).get("preconditioner") != profile:
            raise ValueError(f"BLR worker received a different preconditioner than {profile}")
        if resolved_payload.get("derived", {}).get("physical_intermediate_profile") != contract:
            raise ValueError(f"{profile} resolved profile differs from the frozen contract")
        if not isinstance(source_sha, str) or len(source_sha) != 40:
            raise ValueError(f"{profile} requires the complete launch source SHA")
        summary["abi"] = _abi_facts()
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        root = _repo_root()
        runtime = _V14Runtime(
            directory,
            stage,
            contract,
            root=root,
            source_sha=source_sha,
            batch_identity=batch_identity,
            evidence_prefix=evidence_prefix,
        )
        summary["shared_budget"] = runtime.shared_budget
        summary["shared_attempt"] = {
            "attempt_index": runtime._stage_attempt_index,
            "reserved_seconds": runtime.workflow_reserved_seconds,
            **runtime.time_policy_facts,
        }
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum,
                lambda _value, _frame: setattr(runtime, "stop_requested", True),
            )
        runtime.sample("s0_preflight")
        if stage == "S0_PREFLIGHT":
            record = {
                "schema": (
                    "task039extra.v16.s0-preflight.v1"
                    if evidence_prefix == "v16"
                    else f"task039extra.{evidence_prefix}.s0-preflight.v1"
                ),
                "stage": stage,
                "status": "S0_PREFLIGHT_PASS",
                "official_result": False,
                "stage_pass": True,
                "abi": summary["abi"],
                "formal_pde_started": False,
                "old_v14_ledger_written": False,
            }
        elif stage == "S1_CONTROL":
            record = bridge_q1_baseline(root, runtime)
            record["stage_pass"] = bool(record["passed"])
        elif stage in control_stages:
            s1_bridge = bridge_q1_baseline(root, runtime)
            summary["s1_bridge"] = s1_bridge
            if not s1_bridge.get("passed"):
                raise ValueError(
                    f"{stage} requires the qualified S1 Q1 bridge: "
                    f"{s1_bridge.get('errors', [])}"
                )
            _v14_known_preallocation_gate(
                runtime,
                stage,
                include_common=True,
                include_matrices=False,
            )
            common = _build_common(runtime, cfg)
            try:
                rhs_records = _prepare_reviewed_rhs(
                    runtime, common, resolved_payload, root, 53084
                )
                _v14_known_preallocation_gate(
                    runtime,
                    stage,
                    include_common=False,
                    include_matrices=True,
                )
                threshold = (
                    float(fixed_threshold)
                    if fixed_threshold is not None
                    else p4_blr_tradeoff_threshold(stage)
                )
                record = _s2_blr_control(
                    runtime,
                    common,
                    rhs_records,
                    profile=profile,
                    threshold=threshold,
                    evidence_prefix=evidence_prefix,
                    control_stage=stage,
                    packet_directory=(
                        "s2_rhs_packets"
                        if evidence_prefix == "v16"
                        else f"{stage.lower()}_rhs_packets"
                    ),
                    enable_coverage_statistics=enable_coverage_statistics,
                )
            finally:
                if rhs_records is not None:
                    for item in rhs_records:
                        for key in ("rhs", "reference_solution", "reference_A4y", "reference_map"):
                            item.pop(key, None)
                    rhs_records.clear()
                runtime.set_phase("cleanup")
                _destroy_common(common, runtime)
                common = None
                runtime.sample("post_common_cleanup")
        else:
            record = _not_run_stage(
                stage,
                (
                    "S3/S4 conditional physical runs are not connected in this wiring turn"
                    if evidence_prefix == "v16"
                    else "conditional physical runs are not connected in this wiring turn"
                ),
            )
        summary.update(record)
        summary["status"] = record["status"]
        summary["stage_pass"] = bool(record.get("stage_pass", False))
        summary["result_classification"] = record.get("result_classification", record["status"])
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            stage_pass=False,
            result_classification=exc.classification,
            error=str(exc),
        )
    except Exception as exc:
        summary.update(
            status="FAILED",
            stage_pass=False,
            result_classification="WORKER_FAILED",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        if common is not None:
            _destroy_common(common, runtime)
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        _write_json(directory / f"physical_p4_blr_{evidence_prefix}_summary.json", summary)
        if runtime is not None:
            runtime.marker(f"{evidence_prefix}_worker_complete", summary)
    return {
        "passed": bool(summary.get("stage_pass", False)),
        "errors": [] if summary.get("stage_pass", False) else [str(summary.get("error", summary.get("status", f"{profile} stage did not pass")))],
        "summary": summary,
        "numerical_output_directory": str(directory / "numerical_output"),
    }


def run_physical_p4_blr_v16(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run the unchanged V16 S0/S1/S2 control wiring."""

    return _run_physical_p4_blr(
        resolved_payload,
        run_directory,
        source_sha=source_sha,
        profile=P4_BLR_PROFILE,
        batch_identity="review_v16_p4_blr",
        evidence_prefix="v16",
        control_stages=("S2_BLR_CONTROL",),
        fixed_threshold=1.0e-5,
    )


def run_physical_p4_blr_tradeoff_v17(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run one explicit V17 T1/T2 threshold control."""

    return _run_physical_p4_blr(
        resolved_payload,
        run_directory,
        source_sha=source_sha,
        profile=P4_BLR_TRADEOFF_PROFILE,
        batch_identity="review_v17_p4_blr_tradeoff",
        evidence_prefix="v17",
        control_stages=("T1_BLR_CONTROL", "T2_BLR_CONTROL"),
        enable_coverage_statistics=True,
    )


__all__ = [
    "Q1_BRIDGE_PATH",
    "bridge_q1_baseline",
    "run_physical_p4_blr_tradeoff_v17",
    "run_physical_p4_blr_v16",
]
