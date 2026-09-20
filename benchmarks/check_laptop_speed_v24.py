"""Independent, read-only audit for the saved Task39extra V24 B evidence.

This is deliberately a thin V24 entry point.  It reuses the established V19
array/residual conventions, the V21 channel/field checks, and the V12 saved
output comparison.  It does not create a solver or start a PDE.
The output is an audit of the already-written run root, not a replacement for
the worker's raw evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

import numpy as np


RAW_A4_LIMIT = 1.0e-10
TRUE_RESIDUAL_LIMIT = 1.0e-6
FIELD_LIMIT = 1.0e-4
OUTPUT_LIMIT = 1.0e-5
MODE_POWER_LIMIT = 1.0e-6
MODE_AMPLITUDE_LIMIT = 1.0e-4


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _complex(value: Any) -> complex:
    if isinstance(value, Mapping):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)):
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _mode_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _descriptor_array(packet: Mapping[str, Any], name: str, root: Path) -> np.ndarray:
    archive = Path(str(packet["arrays"]["path"]))
    if not archive.is_absolute():
        archive = root / archive
    expected_archive_sha = str(packet["arrays"]["sha256"])
    actual_archive_sha = sha256(archive)
    if actual_archive_sha != expected_archive_sha:
        raise ValueError(f"array archive hash mismatch: {archive}")
    descriptor = packet[name]
    with np.load(archive, allow_pickle=False) as data:
        array = np.asarray(data[descriptor["array_key"]]).copy()
    if list(array.shape) != list(descriptor["shape"]):
        raise ValueError(f"array shape mismatch for {name}")
    if str(array.dtype) != str(descriptor["dtype"]):
        raise ValueError(f"array dtype mismatch for {name}")
    if not np.isfinite(array).all():
        raise ValueError(f"nonfinite array for {name}")
    return array


def residual_packet_facts(packet_path: Path, root: Path) -> dict[str, Any]:
    """Recompute the full-space residual from the saved rhs/applied arrays."""

    packet = read_json(packet_path)
    rhs = _descriptor_array(packet, "rhs", root)
    applied = _descriptor_array(packet, "applied", root)
    residual = _descriptor_array(packet, "residual", root)
    solution = _descriptor_array(packet, "solution", root)
    if rhs.shape != applied.shape or rhs.shape != residual.shape:
        raise ValueError(f"residual packet shape mismatch: {packet_path}")
    rhs_norm = float(np.linalg.norm(rhs))
    if not _finite(packet.get("rhs_norm")) or not math.isclose(
        rhs_norm, float(packet["rhs_norm"]), rel_tol=1.0e-12, abs_tol=1.0e-15
    ):
        raise ValueError(f"rhs norm mismatch: {packet_path}")
    explicit_vector = rhs - applied
    explicit_ratio = float(np.linalg.norm(explicit_vector) / max(rhs_norm, np.finfo(float).tiny))
    saved_residual_ratio = float(np.linalg.norm(residual) / max(rhs_norm, np.finfo(float).tiny))
    residual_difference = float(np.linalg.norm(residual - explicit_vector))
    reported = float(packet["explicit_relative_residual"])
    return {
        "packet": str(packet_path),
        "packet_sha256": sha256(packet_path),
        "array_archive": str(Path(str(packet["arrays"]["path"])).resolve()),
        "array_archive_sha256": str(packet["arrays"]["sha256"]),
        "rhs_norm": rhs_norm,
        "explicit_ratio_from_rhs_minus_applied": explicit_ratio,
        "saved_residual_ratio": saved_residual_ratio,
        "reported_explicit_relative_residual": reported,
        "residual_vector_difference_norm": residual_difference,
        "solution_shape": list(solution.shape),
        "checks": {
            "rhs_norm": math.isclose(
                rhs_norm, float(packet["rhs_norm"]), rel_tol=1.0e-12, abs_tol=1.0e-15
            ),
            "residual_matches_rhs_minus_applied": residual_difference <= 1.0e-12,
            "reported_matches_recomputed": math.isclose(
                explicit_ratio, reported, rel_tol=1.0e-12, abs_tol=1.0e-15
            ),
            "gate": explicit_ratio <= TRUE_RESIDUAL_LIMIT,
        },
    }


def _saved_fe_metric_facts(current_dir: Path, reference_dir: Path) -> dict[str, Any]:
    """Validate the separate metric artifact against both saved field archives."""

    artifact_path = current_dir.parent / "engineering" / "v24_same_discrete_fe_metrics.json"
    watchdog_root = current_dir.parent / "engineering" / "fe_metric_watchdogs"
    completed_watchdog_path = watchdog_root / "completed" / "summary.json"
    first_stop_watchdog_path = watchdog_root / "first_timebase_inconsistency" / "summary.json"
    unknown = {
        "status": "UNKNOWN_MISSING_CELLWISE_INTEGRAL_OR_METRIC_DATA",
        "L2": None,
        "scaled_curl": None,
        "artifact_path": str(artifact_path),
        "reason": "No independently saved same-discrete FE metric artifact is available.",
    }
    if not artifact_path.is_file():
        return unknown
    try:
        artifact = read_json(artifact_path)
        current_facts = artifact["current"]
        reference_facts = artifact["reference"]
        current_archive = Path(current_facts["archive_path"]).resolve()
        reference_archive = Path(reference_facts["archive_path"]).resolve()
        expected_current_archive = (current_dir.parent / "x2_retained_final.npz").resolve()
        expected_reference_archive = (reference_dir.parent / "x2_retained_final.npz").resolve()
        with np.load(current_archive, allow_pickle=False) as current_arrays, np.load(
            reference_archive, allow_pickle=False
        ) as reference_arrays:
            current_vector = np.asarray(current_arrays[current_facts["array_key"]])
            reference_vector = np.asarray(reference_arrays[reference_facts["array_key"]])
        expected_map = "54647a99c97786af88364d6e3f8c6c1d3c7893bbf79afc2888a63cf47be6c06e"
        identity = artifact["frozen_identity"]
        metrics = artifact["comparison"]["metrics"]
        metric_facts: dict[str, dict[str, Any]] = {}
        metric_checks: dict[str, bool] = {}
        for name in ("L2", "scaled_curl"):
            item = metrics[name]
            absolute_error = float(item["absolute_error_norm"])
            reference_norm = float(item["reference_norm"])
            recorded_relative = float(item["relative"])
            recomputed_relative = (
                absolute_error / reference_norm
                if reference_norm > 0.0
                else math.inf
            )
            metric_checks[name] = (
                _finite(absolute_error)
                and _finite(reference_norm)
                and _finite(recorded_relative)
                and absolute_error >= 0.0
                and reference_norm > 0.0
                and recorded_relative >= 0.0
                and _finite(recomputed_relative)
                and math.isclose(
                    recomputed_relative,
                    recorded_relative,
                    rel_tol=1.0e-12,
                    abs_tol=1.0e-25,
                )
                and recomputed_relative <= FIELD_LIMIT
            )
            metric_facts[name] = {
                **item,
                "recomputed_relative": recomputed_relative,
                "relative_matches_recomputed": metric_checks[name],
            }
        completed_watchdog = read_json(completed_watchdog_path)
        first_stop_watchdog = read_json(first_stop_watchdog_path)
        zero_pages = {"pswpin_pages": 0, "pswpout_pages": 0}
        completed_watchdog_checks = {
            "classification_completed": completed_watchdog.get("classification") == "COMPLETED",
            "leader_exit_zero": completed_watchdog.get("leader_exit_code") == 0,
            "descendants_cleared": completed_watchdog.get("descendants_cleared") is True,
            "remaining_child_pids_empty": completed_watchdog.get("remaining_child_pids") == [],
            "process_tree_swap_zero": completed_watchdog.get("sampled_process_tree_swap_peak_bytes") == 0,
            "global_swap_delta_zero": completed_watchdog.get("global_swap_activity", {}).get("delta")
            == zero_pages,
        }
        first_stop_checks = {
            "classification_timebase_inconsistency": first_stop_watchdog.get("classification")
            == "TIMEBASE_INCONSISTENCY",
            "leader_exit_nonzero": first_stop_watchdog.get("leader_exit_code") == 1,
            "descendants_cleared": first_stop_watchdog.get("descendants_cleared") is True,
            "remaining_child_pids_empty": first_stop_watchdog.get("remaining_child_pids") == [],
            "process_tree_swap_zero": first_stop_watchdog.get("sampled_process_tree_swap_peak_bytes") == 0,
            "global_swap_delta_zero": first_stop_watchdog.get("global_swap_activity", {}).get("delta")
            == zero_pages,
            "stop_reason_timebase_inconsistency": first_stop_watchdog.get("stop_event", {}).get(
                "reason"
            )
            == "TIMEBASE_INCONSISTENCY",
        }
        checks = {
            "schema": artifact.get("schema") == "task039extra.v24.same-discrete-fe-metrics.v1",
            "offline_execution": artifact.get("execution", {}).get("status")
            == "OFFLINE_METRIC_ONLY"
            and not artifact["execution"].get("pde_started")
            and not artifact["execution"].get("physical_operator_built")
            and not artifact["execution"].get("factor_started")
            and not artifact["execution"].get("ksp_started"),
            "current_archive_path": current_archive == expected_current_archive,
            "reference_archive_path": reference_archive == expected_reference_archive,
            "current_archive_hash": sha256(current_archive) == current_facts["archive_sha256"],
            "reference_archive_hash": sha256(reference_archive) == reference_facts["archive_sha256"],
            "current_vector_hash": hashlib.sha256(current_vector.tobytes()).hexdigest()
            == current_facts["vector_sha256"],
            "reference_vector_hash": hashlib.sha256(reference_vector.tobytes()).hexdigest()
            == reference_facts["vector_sha256"],
            "postprocess_script_hash": artifact["source"]["checker_script_sha256"]
            == sha256(Path(__file__).resolve().with_name("postprocess_laptop_speed_v24_fe_metrics.py")),
            "map_hash": identity["p6_native_map_sha256_recomputed"] == expected_map
            and all(identity["identity_checks"].values()),
            "quadrature": identity["quadrature"] == [
                {"quadrature_degree": 15, "quadrature_rule": "default"},
                {"quadrature_degree": 15, "quadrature_rule": "default"},
            ],
            "metric_pass": set(metrics) == {"L2", "scaled_curl"} and all(metric_checks.values()),
            "cleanup": artifact.get("cleanup", {}).get("status") == "COMPLETED"
            and artifact["cleanup"].get("metric_destroyed") is True,
            "completed_watchdog": all(completed_watchdog_checks.values()),
            "first_timebase_stop_preserved": all(first_stop_checks.values()),
        }
        if not all(checks.values()):
            return {
                **unknown,
                "status": "INVALID_SAVED_FE_METRIC_ARTIFACT",
                "checks": checks,
                "artifact_sha256": sha256(artifact_path),
                "watchdog": {
                    "completed_summary_sha256": sha256(completed_watchdog_path),
                    "first_stop_summary_sha256": sha256(first_stop_watchdog_path),
                    "completed_checks": completed_watchdog_checks,
                    "first_stop_checks": first_stop_checks,
                },
            }
        return {
            "status": "AVAILABLE",
            "artifact_path": str(artifact_path),
            "artifact_sha256": sha256(artifact_path),
            "L2": metric_facts["L2"],
            "scaled_curl": metric_facts["scaled_curl"],
            "max_relative": max(item["recomputed_relative"] for item in metric_facts.values()),
            "limit": FIELD_LIMIT,
            "checks": checks,
            "watchdog": {
                "status": completed_watchdog["classification"],
                "completed_summary_path": str(completed_watchdog_path),
                "completed_summary_sha256": sha256(completed_watchdog_path),
                "completed": {
                    "classification": completed_watchdog["classification"],
                    "leader_exit_code": completed_watchdog["leader_exit_code"],
                    "descendants_cleared": completed_watchdog["descendants_cleared"],
                    "remaining_child_pids": completed_watchdog["remaining_child_pids"],
                    "samples": completed_watchdog["samples"],
                    "elapsed_seconds": completed_watchdog["elapsed_seconds"],
                    "rss_peak_bytes": completed_watchdog["sampled_process_tree_rss_peak_bytes"],
                    "swap_peak_bytes": completed_watchdog["sampled_process_tree_swap_peak_bytes"],
                    "global_swap_activity": completed_watchdog["global_swap_activity"],
                    "job_swap_activity": completed_watchdog["job_swap_activity"],
                    "memory_policy": completed_watchdog["memory_policy"],
                    "time_policy": completed_watchdog["time_policy"],
                    "timebase_guard": "not_enabled_or_not_recorded"
                    if completed_watchdog.get("clock_info") is None
                    else "recorded",
                    "checks": completed_watchdog_checks,
                },
                "first_timebase_stop": {
                    "summary_path": str(first_stop_watchdog_path),
                    "summary_sha256": sha256(first_stop_watchdog_path),
                    "classification": first_stop_watchdog["classification"],
                    "leader_exit_code": first_stop_watchdog["leader_exit_code"],
                    "elapsed_seconds": first_stop_watchdog["elapsed_seconds"],
                    "rss_peak_bytes": first_stop_watchdog[
                        "sampled_process_tree_rss_peak_bytes"
                    ],
                    "swap_peak_bytes": first_stop_watchdog[
                        "sampled_process_tree_swap_peak_bytes"
                    ],
                    "clock_error": first_stop_watchdog.get("clock_error"),
                    "checks": first_stop_checks,
                },
                "strategy_deviation": (
                    "The completed engineering metric wrapper used "
                    "LEGACY_STATIC_MEMORY_ENVELOPE with time_policy=enforce; "
                    "the successful record has no timebase-guard clock_info and "
                    "is not the formal physical resource authority."
                ),
                "artifact_scope": "independent engineering postprocess watchdog; not formal PDE resource authority",
            },
        }
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return {
            **unknown,
            "status": "INVALID_SAVED_FE_METRIC_ARTIFACT",
            "reason": str(exc),
            "artifact_sha256": sha256(artifact_path),
        }


def _matrix_identity_tuple(identity: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        identity.get("schema_version"),
        identity.get("shape"),
        identity.get("nnz"),
        identity.get("dtype"),
        identity.get("csr_sha256"),
        identity.get("mapping_sha256"),
        identity.get("values_sha256"),
    )


def _identity_projection(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the bounded operator/map identity fields used by the audit."""

    return {
        "input_sha256": identity.get("input_sha256"),
        "physical_model_sha256": identity.get("physical_model_sha256"),
        "p4_native_map_sha256": identity.get("p4_native_map_sha256"),
        "p6_native_map_sha256": identity.get("p6_native_map_sha256"),
        "ordered_mode_sha256": identity.get("ordered_mode_sha256"),
        "condensed_matrix_identity": list(
            _matrix_identity_tuple(identity.get("condensed_matrix_identity", {}))
        ),
    }


def _rhs_storage_facts(packet: Mapping[str, Any], root: Path) -> dict[str, Any]:
    archive = Path(str(packet["arrays"]["path"]))
    if not archive.is_absolute():
        archive = root / archive
    array_key = str(packet["rhs_storage"]["array_key"])
    with np.load(archive, allow_pickle=False) as arrays:
        vector = np.asarray(arrays[array_key]).copy()
    return {
        "archive_path": str(archive.resolve()),
        "archive_sha256_recorded": str(packet["arrays"]["sha256"]),
        "archive_sha256_actual": sha256(archive),
        "array_key": array_key,
        "shape": list(vector.shape),
        "dtype": str(vector.dtype),
        "vector_sha256": hashlib.sha256(vector.tobytes()).hexdigest(),
    }


def _saved_identity_facts(
    run_root: Path,
    old_root: Path,
    summary: Mapping[str, Any],
    old_summary: Mapping[str, Any],
    official_packet: Mapping[str, Any],
    old_packet: Mapping[str, Any],
    final_packet: Mapping[str, Any],
    post_packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind manifests, residual packets, RHS storage, and the old B operator."""

    run_manifest = read_json(run_root / "run_manifest.json")
    old_manifest = read_json(old_root / "run_manifest.json")
    current_summary_identity = _identity_projection(summary["operator_identity"])
    official_identity = _identity_projection(official_packet["identity"])
    current_packet_identities = {
        "official": official_identity,
        "final_residual": _identity_projection(final_packet["identity"]),
        "post_release_residual": _identity_projection(post_packet["identity"]),
    }
    old_identity = _identity_projection(old_packet["identity"])
    old_summary_identity = _identity_projection(old_summary["operator_identity"])
    current_rhs = _rhs_storage_facts(summary["rhs_packet"], run_root)
    old_rhs = _rhs_storage_facts(old_summary["rhs_packet"], old_root)
    current_input_path = run_root / "input_original.dat"
    old_input_path = old_root / "input_original.dat"
    current_input_sha = sha256(current_input_path)
    old_input_sha = sha256(old_input_path)
    current_resolved_path = run_root / "resolved_config.json"
    old_resolved_path = old_root / "resolved_config.json"
    current_orders = read_json(run_root / "numerical_output" / "dtn_port_diffraction_orders_3d.json")[
        "orders"
    ]
    old_orders = read_json(old_root / "numerical_output" / "dtn_port_diffraction_orders_3d.json")[
        "orders"
    ]
    current_keys = [_mode_key(row) for row in current_orders]
    old_keys = [_mode_key(row) for row in old_orders]
    common_operator_fields = (
        "physical_model_sha256",
        "p4_native_map_sha256",
        "p6_native_map_sha256",
        "ordered_mode_sha256",
        "condensed_matrix_identity",
    )
    common_operator_identity_matches = all(
        official_identity[field] == old_identity[field] for field in common_operator_fields
    )
    packet_identity_consistent = all(
        packet_identity == official_identity
        for packet_identity in current_packet_identities.values()
    )
    rhs_identity = _identity_projection(summary["rhs_packet"]["identity"])
    old_rhs_identity = _identity_projection(old_summary["rhs_packet"]["identity"])
    checks = {
        "source_matches_manifest": summary["source_sha"] == run_manifest["source_sha"],
        "current_manifest_input_matches_packets": run_manifest["input_sha256"]
        == official_identity["input_sha256"]
        == current_summary_identity["input_sha256"],
        "current_input_original_hash": current_input_sha == run_manifest["input_sha256"],
        "current_manifest_physical_matches_packets": run_manifest["physical_model_sha256"]
        == official_identity["physical_model_sha256"]
        == current_summary_identity["physical_model_sha256"],
        "old_input_original_hash": old_input_sha == old_manifest["input_sha256"]
        == old_identity["input_sha256"]
        == old_summary_identity["input_sha256"],
        "old_manifest_physical_matches_packets": old_manifest["physical_model_sha256"]
        == old_identity["physical_model_sha256"]
        == old_summary_identity["physical_model_sha256"],
        "current_resolved_config_hash": sha256(current_resolved_path)
        == run_manifest["resolved_config_sha256"],
        "old_resolved_config_hash": sha256(old_resolved_path)
        == old_manifest["resolved_config_sha256"],
        "current_residual_and_official_identity": packet_identity_consistent,
        "current_summary_and_official_identity": current_summary_identity == official_identity,
        "current_rhs_archive_hash": current_rhs["archive_sha256_actual"]
        == current_rhs["archive_sha256_recorded"],
        "old_rhs_archive_hash": old_rhs["archive_sha256_actual"]
        == old_rhs["archive_sha256_recorded"],
        "rhs_packet_operator_identity": rhs_identity == official_identity,
        "old_rhs_packet_operator_identity": old_rhs_identity == old_identity,
        "rhs_vectors_equal": current_rhs["vector_sha256"] == old_rhs["vector_sha256"],
        "rhs_vector_shape_and_dtype_equal": current_rhs["shape"] == old_rhs["shape"]
        and current_rhs["dtype"] == old_rhs["dtype"],
        "old_summary_and_official_identity": old_summary_identity == old_identity,
        "old_matrix_and_80_mode_identity": common_operator_identity_matches
        and len(current_orders) == len(old_orders) == 80
        and len(current_keys) == len(set(current_keys)) == 80
        and len(old_keys) == len(set(old_keys)) == 80
        and current_keys == old_keys,
    }
    return {
        "current_manifest": {
            "source_sha": run_manifest["source_sha"],
            "input_sha256": run_manifest["input_sha256"],
            "input_original_path": str(current_input_path),
            "input_original_sha256": current_input_sha,
            "resolved_config_sha256": run_manifest["resolved_config_sha256"],
            "physical_model_sha256": run_manifest["physical_model_sha256"],
            "resolved_config_file_sha256": sha256(current_resolved_path),
        },
        "old_manifest": {
            "source_sha": old_manifest["source_sha"],
            "input_sha256": old_manifest["input_sha256"],
            "input_original_path": str(old_input_path),
            "input_original_sha256": old_input_sha,
            "resolved_config_sha256": old_manifest["resolved_config_sha256"],
            "physical_model_sha256": old_manifest["physical_model_sha256"],
            "resolved_config_file_sha256": sha256(old_resolved_path),
        },
        "current_summary_identity": current_summary_identity,
        "official_packet_identity": official_identity,
        "current_packet_identities": current_packet_identities,
        "old_official_packet_identity": old_identity,
        "rhs": {
            "current": current_rhs,
            "old": old_rhs,
            "current_vector_equals_old": current_rhs["vector_sha256"] == old_rhs["vector_sha256"],
        },
        "mode_inventory": {
            "current_count": len(current_orders),
            "old_count": len(old_orders),
            "current_unique": len(current_keys) == len(set(current_keys)),
            "old_unique": len(old_keys) == len(set(old_keys)),
            "ordered_keys_equal": current_keys == old_keys,
        },
        "packet_identity_consistent": packet_identity_consistent,
        "old_matrix_and_mode_identity": common_operator_identity_matches,
        "checks": checks,
    }


def pc_boundary_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Check the saved PC contract and sampled closure formula only."""

    boundaries = summary["pc"]["boundary_records"]
    pc = summary["pc"]
    contract = summary["pc_boundary_contract"]
    expected_matrix = summary["interface_stack"]["matrix_identity_before_factor"]
    checks: dict[str, bool] = {
        "boundary_count_127": len(boundaries) == 127,
        "contract_route_BAL_H": contract.get("route") == "BAL_H",
        "contract_two_coarse_calls": contract.get("coarse_calls_per_apply") == 2,
        "contract_fint_direct": contract.get("fint_direct") is True,
        "contract_inner_ksp_false": contract.get("inner_ksp") is False,
        "contract_max_it_2048": contract.get("max_it") == 2048,
        "contract_restart_32": contract.get("restart") == 32,
        "contract_soft_pc_seconds_25": contract.get("soft_pc_seconds") == 25.0,
        "contract_hard_pc_seconds_30": contract.get("hard_pc_seconds") == 30.0,
        "contract_zero_start": contract.get("zero_start") is True,
        "pc_apply_count_127": pc.get("apply_count") == 127,
        "h6_apply_count_127": pc.get("h6_apply_count") == 127,
        "native_A4_actions_255": pc.get("native_A4_action_count") == 255,
        "physical_F4_calls_255": pc.get("p4_f4_apply_count") == 255,
        "logical_P4_calls_254": pc.get("p4_logical_apply_count") == 254,
        "logical_P4_attempts_254": pc.get("p4_logical_apply_attempt_count") == 254,
        "total_A_structure_254": pc.get("total_counts", {}).get("A_structure") == 254,
        "total_C_254": pc.get("total_counts", {}).get("C") == 254,
        "total_smoother_127": pc.get("total_counts", {}).get("smoother") == 127,
        "total_A_inner_true_zero": pc.get("total_counts", {}).get("A_inner_true") == 0,
        "total_PH_audit_zero": pc.get("total_counts", {}).get("PH_audit") == 0,
    }
    closure_samples: list[dict[str, Any]] = []
    physical_solve_count = 0
    logical_call_count = 0
    for number, boundary in enumerate(boundaries, start=1):
        balance = boundary["pc"]["inexact_balance"]
        calls = balance["calls"]
        checks[f"pc{number}.two_live_calls"] = len(calls) == 2 and balance.get("mode") == "BAL_H"
        checks[f"pc{number}.completed"] = boundary.get("completed") is True
        scale = sum(float(call["rhs_norm"]) + float(call["applied_norm"]) for call in calls)
        checks[f"pc{number}.operation_scale"] = math.isclose(
            scale, float(balance["operation_scale"]), rel_tol=1.0e-12, abs_tol=1.0e-30
        )
        for call_number, call in enumerate(calls, start=1):
            logical_call_count += 1
            inner = call["inner"]
            interface = inner["interface_facts"]
            repair = inner["repair"]
            physical_solve_count_before_call = physical_solve_count
            physical_solve_count += int(repair["actual_mat_solve_count"])
            prefix = f"pc{number}.call{call_number}"
            checks[f"{prefix}.one_factor_solve_delta"] = interface.get(
                "factor_solve_call_delta"
            ) == 1
            checks[f"{prefix}.cumulative_factor_solve_count"] = interface.get(
                "factor_solve_count"
            ) == physical_solve_count_before_call + 1
            checks[f"{prefix}.mpc_dual_input"] = interface.get("input_is_mpc_dual_storage") is True
            checks[f"{prefix}.no_duplicate_C_H"] = interface.get("duplicate_C_H_applied") is False
            checks[f"{prefix}.finite_input_output_solution"] = (
                interface.get("input_finite") is True
                and interface.get("output_finite") is True
                and interface.get("solution_finite") is True
            )
            checks[f"{prefix}.completed"] = interface.get("status") == "SOLVE_COMPLETED"
            checks[f"{prefix}.port_rhs_policy"] = interface.get("port_rhs_policy") == "zero_only"
            checks[f"{prefix}.slave_zero_policy"] = interface.get(
                "slave_zero_policy"
            ) == "zero_initialize_and_no_backsubstitution"
            checks[f"{prefix}.matrix_identity"] = _matrix_identity_tuple(
                interface.get("matrix_identity", {})
            ) == _matrix_identity_tuple(expected_matrix)
        if number == 1 or number % 32 == 0:
            audit = balance.get("audit", {})
            numerator = audit.get("closure_norm")
            relative = (
                float(numerator) / scale
                if _finite(numerator) and scale > 0.0
                else math.inf
            )
            closure_ok = math.isfinite(relative) and relative <= 1.0e-8
            checks[f"pc{number}.closure"] = closure_ok
            closure_samples.append(
                {
                    "pc": number,
                    "closure_norm": numerator,
                    "operation_scale": scale,
                    "relative": relative if math.isfinite(relative) else None,
                    "limit": 1.0e-8,
                    "pass": closure_ok,
                }
            )
    checks["summary_logical_call_count_254"] = logical_call_count == 254
    checks["summary_physical_factor_solve_count_255"] = physical_solve_count == 255
    return {
        "boundary_count": len(boundaries),
        "logical_call_count": logical_call_count,
        "physical_factor_solve_count": physical_solve_count,
        "closure_samples": closure_samples,
        "contract": contract,
        "checks": checks,
        "passed": all(checks.values()),
        "scope": "saved PC counters and sampled inexact-balance closure; no new vector solves",
    }


def _rho_from_denominator(residual_norm: float, denominator: float) -> float:
    """Use one explicit denominator rule for raw and repaired rho values."""

    return float(residual_norm / max(denominator, np.finfo(float).tiny))


def _correction_index(phase: Any) -> int | None:
    text = str(phase)
    prefix, separator, suffix = text.partition("_")
    if prefix != "correction" or not separator or not suffix.isdigit():
        return None
    index = int(suffix)
    return index if str(index) == suffix and index > 0 else None


def a4_raw_facts(summary: Mapping[str, Any], run_root: Path) -> dict[str, Any]:
    """Recompute all 254 logical rho values using each raw JSON g denominator."""

    balance_root = run_root / "inexact_balance"
    files = sorted(balance_root.glob("v24_p4_repair_*.json"))
    entries = [(path, read_json(path)) for path in files]
    records = [item for _, item in entries]
    raw_entries = [(path, item) for path, item in entries if item.get("phase") == "raw"]
    correction_entries = [
        (path, item)
        for path, item in entries
        if _correction_index(item.get("phase")) is not None
    ]
    unknown_phase_files = [
        str(path)
        for path, item in entries
        if item.get("phase") != "raw" and _correction_index(item.get("phase")) is None
    ]
    raw_by_sequence: dict[int, tuple[Path, Mapping[str, Any]]] = {}
    for path, item in raw_entries:
        sequence = int(item["logical_call_sequence"])
        if sequence in raw_by_sequence:
            raise ValueError(f"duplicate raw logical sequence {sequence}")
        raw_by_sequence[sequence] = (path, item)
    correction_by_sequence: dict[int, list[tuple[Path, Mapping[str, Any]]]] = {}
    for path, item in correction_entries:
        sequence = int(item["logical_call_sequence"])
        correction_by_sequence.setdefault(sequence, []).append((path, item))
    for sequence, correction_rows in correction_by_sequence.items():
        correction_rows.sort(key=lambda pair: int(_correction_index(pair[1]["phase"])))
        if sequence not in raw_by_sequence:
            raise ValueError(f"correction without raw logical sequence {sequence}")

    expected_matrix = summary["interface_stack"]["matrix_identity_before_factor"]
    boundary_calls = [
        call
        for boundary in summary["pc"]["boundary_records"]
        for call in boundary["pc"]["inexact_balance"]["calls"]
    ]
    repair_rows: list[dict[str, Any]] = []
    repair_raw_records: list[Mapping[str, Any]] = []
    repair_correction_records: list[Mapping[str, Any]] = []
    repair_actual_count = 0
    repair_extra_count = 0
    repair_record_count = 0
    repair_factor_delta = 0
    repair_phase_ok = True
    repair_sequence_ok = True
    for expected_sequence, call in enumerate(boundary_calls, start=1):
        repair = call["inner"]["repair"]
        actual = int(repair["actual_mat_solve_count"])
        extra = int(repair["extra_solve_count"])
        records_for_call = list(repair["records"])
        raw_for_call = [record for record in records_for_call if record.get("phase") == "raw"]
        correction_for_call = [
            record for record in records_for_call if record.get("phase") == "correction"
        ]
        correction_indices = sorted(int(record["index"]) for record in correction_for_call)
        record_delta = sum(int(record["factor_solve_call_delta"]) for record in records_for_call)
        call_checks = {
            "logical_sequence": int(repair["logical_call_sequence"]) == expected_sequence,
            "actual_is_raw_plus_extra": actual == 1 + extra,
            "record_count_matches_actual": len(records_for_call) == actual,
            "factor_solve_delta_matches_actual": record_delta == actual,
            "one_raw_record_index_zero": len(raw_for_call) == 1
            and int(raw_for_call[0]["index"]) == 0,
            "correction_record_phase_indices": correction_indices == list(range(1, extra + 1)),
        }
        repair_phase_ok = repair_phase_ok and all(call_checks.values())
        repair_sequence_ok = repair_sequence_ok and call_checks["logical_sequence"]
        repair_actual_count += actual
        repair_extra_count += extra
        repair_record_count += len(records_for_call)
        repair_factor_delta += record_delta
        repair_raw_records.extend(raw_for_call)
        repair_correction_records.extend(correction_for_call)
        repair_rows.append(
            {
                "logical_call_sequence": expected_sequence,
                "actual_mat_solve_count": actual,
                "extra_solve_count": extra,
                "record_count": len(records_for_call),
                "factor_solve_call_delta": record_delta,
                "correction_elapsed_seconds": [
                    record.get("elapsed_seconds") for record in correction_for_call
                ],
                "checks": call_checks,
            }
        )
    repair_summary_checks = {
        "summary_call_sequences_1_to_254": repair_sequence_ok
        and len(boundary_calls) == 254,
        "actual_mat_solve_count_255": repair_actual_count == 255,
        "extra_solve_count_1": repair_extra_count == 1,
        "repair_record_count_255": repair_record_count == 255,
        "factor_solve_delta_255": repair_factor_delta == 255,
        "packet_and_boundary_raw_counts_match": len(repair_raw_records) == len(raw_entries),
        "packet_and_boundary_correction_counts_match": len(repair_correction_records)
        == len(correction_entries),
        "pc_summary_counts_match": summary["pc"].get("p4_logical_apply_count") == 254
        and summary["pc"].get("p4_f4_apply_count") == 255
        and summary["pc"].get("p4_logical_apply_attempt_count") == 254,
    }
    rows: list[dict[str, Any]] = []
    identity_ok = True
    reported_ok = True
    finite_ok = True
    denominator_ok = True
    correction_denominator_ok = True
    correction_limit_ok = True
    epsilon_closure_ok = True
    boundary_rhs_norms = [
        float(call["rhs_norm"])
        for boundary in summary["pc"]["boundary_records"]
        for call in boundary["pc"]["inexact_balance"]["calls"]
    ]
    for sequence in sorted(raw_by_sequence):
        raw_path, raw_item = raw_by_sequence[sequence]
        raw_g = float(raw_item["g_norm"])
        raw_residual = float(raw_item["native_A4_residual_norm"])
        raw_rho = _rho_from_denominator(raw_residual, raw_g)
        expected_g = boundary_rhs_norms[sequence - 1] if 1 <= sequence <= len(boundary_rhs_norms) else math.nan
        row_denominator_ok = (
            _finite(raw_g)
            and raw_g > 0.0
            and math.isclose(raw_g, expected_g, rel_tol=1.0e-12, abs_tol=1.0e-15)
        )
        correction_rows = correction_by_sequence.get(sequence, [])
        correction_limit_ok = correction_limit_ok and len(correction_rows) <= 2
        final_path, final_item = raw_path, raw_item
        record_identity_ok = True
        record_reported_ok = math.isclose(
            raw_rho,
            float(raw_item["native_A4_relative_residual"]),
            rel_tol=1.0e-12,
            abs_tol=1.0e-25,
        )
        record_finite_ok = all(_finite(value) for value in (raw_g, raw_residual, raw_rho))
        correction_facts: list[dict[str, Any]] = []
        for correction_path, correction_item in correction_rows:
            correction_g = float(correction_item["g_norm"])
            correction_residual = float(correction_item["native_A4_residual_norm"])
            correction_rho = _rho_from_denominator(correction_residual, raw_g)
            correction_g_ok = math.isclose(
                correction_g, raw_g, rel_tol=1.0e-12, abs_tol=1.0e-15
            )
            correction_denominator_ok = correction_denominator_ok and correction_g_ok
            correction_interface = correction_item.get("interface_facts", {})
            correction_identity_ok = (
                _matrix_identity_tuple(correction_interface.get("matrix_identity", {}))
                == _matrix_identity_tuple(expected_matrix)
            )
            correction_reported_ok = math.isclose(
                correction_rho,
                float(correction_item["native_A4_relative_residual"]),
                rel_tol=1.0e-12,
                abs_tol=1.0e-25,
            )
            correction_finite_ok = all(
                _finite(value) for value in (correction_g, correction_residual, correction_rho)
            ) and bool(correction_interface.get("input_finite")) and bool(
                correction_interface.get("output_finite")
            )
            record_identity_ok = record_identity_ok and correction_identity_ok
            record_reported_ok = record_reported_ok and correction_reported_ok
            record_finite_ok = record_finite_ok and correction_finite_ok
            correction_facts.append(
                {
                    "path": str(correction_path),
                    "phase": correction_item.get("phase"),
                    "g_norm": correction_g,
                    "residual_norm": correction_residual,
                    "rho_from_raw_g": correction_rho,
                    "reported_rho": correction_item.get("native_A4_relative_residual"),
                    "g_matches_raw": correction_g_ok,
                    "reported_rho_ok": correction_reported_ok,
                    "matrix_identity_ok": correction_identity_ok,
                    "interface_elapsed_seconds": correction_interface.get("elapsed_seconds"),
                }
            )
            final_path, final_item = correction_path, correction_item
        final_residual = float(final_item["native_A4_residual_norm"])
        final_rho = _rho_from_denominator(final_residual, raw_g)
        final_reported_rho = float(final_item["native_A4_relative_residual"])
        row_epsilon_closure_ok = (
            _finite(final_reported_rho)
            and math.isclose(
                final_rho,
                final_reported_rho,
                rel_tol=1.0e-12,
                abs_tol=1.0e-25,
            )
        )
        final_interface = final_item.get("interface_facts", {})
        record_identity_ok = record_identity_ok and (
            _matrix_identity_tuple(final_interface.get("matrix_identity", {}))
            == _matrix_identity_tuple(expected_matrix)
        )
        row_finite_ok = record_finite_ok and _finite(final_rho)
        row_identity_ok = record_identity_ok
        row_reported_ok = record_reported_ok
        # A final correction is always judged with the original raw g
        # denominator.  Its own g_norm is only a consistency field.
        row = {
            "logical_call_sequence": sequence,
            "raw_path": str(raw_path),
            "raw_g_norm": raw_g,
            "raw_residual_norm": raw_residual,
            "raw_rho": raw_rho,
            "correction_count": len(correction_rows),
            "corrections": correction_facts,
            "final_phase": final_item.get("phase"),
            "final_path": str(final_path),
            "final_residual_norm": final_residual,
            "final_rho": final_rho,
            "final_reported_rho": final_reported_rho,
            "epsilon_closure_ok": row_epsilon_closure_ok,
            "matrix_identity_ok": row_identity_ok,
            "reported_rho_ok": row_reported_ok,
            "finite_ok": row_finite_ok,
            "raw_g_denominator_ok": row_denominator_ok,
        }
        rows.append(row)
        identity_ok = identity_ok and row_identity_ok
        reported_ok = reported_ok and row_reported_ok
        finite_ok = finite_ok and row_finite_ok
        denominator_ok = denominator_ok and row_denominator_ok
        epsilon_closure_ok = epsilon_closure_ok and row_epsilon_closure_ok

    raw_sequences = sorted(raw_by_sequence)
    final_rhos = [float(row["final_rho"]) for row in rows]
    raw_exceed = [row for row in rows if float(row["raw_rho"]) > RAW_A4_LIMIT]
    correction_count = sum(int(row["correction_count"]) for row in rows)
    all_interface_policies = []
    for item in records:
        interface = item.get("interface_facts", {})
        all_interface_policies.append(
            {
                "port_rhs_policy": interface.get("port_rhs_policy"),
                "slave_zero_policy": interface.get("slave_zero_policy"),
                "matrix_identity": _matrix_identity_tuple(interface.get("matrix_identity", {})),
            }
        )
    policy_ok = bool(all_interface_policies) and all(
        item["port_rhs_policy"] == "zero_only"
        and item["slave_zero_policy"] == "zero_initialize_and_no_backsubstitution"
        and item["matrix_identity"] == _matrix_identity_tuple(expected_matrix)
        for item in all_interface_policies
    )
    sequence_ok = raw_sequences == list(range(1, 255))
    # Bind the summary's 127 x 2 boundary layout to the file-level logical set.
    boundary_call_count = len(boundary_calls)
    return {
        "counts": {
            "boundary_records": len(summary["pc"]["boundary_records"]),
            "boundary_calls": boundary_call_count,
            "packet_files": len(entries),
            "raw_records": len(raw_entries),
            "correction_records": correction_count,
            "final_logical_calls": len(rows),
            "physical_mat_solve_records": len(raw_entries) + correction_count,
            "summary_actual_mat_solve_count": repair_actual_count,
            "summary_extra_solve_count": repair_extra_count,
        },
        "raw_rho_limit": RAW_A4_LIMIT,
        "final_rho_max": max(final_rhos, default=None),
        "final_rho_max_logical_call": (
            max(rows, key=lambda row: float(row["final_rho"]))["logical_call_sequence"]
            if rows
            else None
        ),
        "raw_limit_exceedances": raw_exceed,
        "correction_logical_calls": [row["logical_call_sequence"] for row in rows if row["correction_count"]],
        "identity": {
            "same_condensed_matrix": identity_ok,
            "port_and_slave_policies": policy_ok,
            "source_input_physical_identity": {
                "source_sha": summary.get("source_sha"),
                "input_sha256": summary["operator_identity"].get("input_sha256"),
                "physical_model_sha256": summary["operator_identity"].get("physical_model_sha256"),
            },
        },
        "boundary_repair": {
            "rows": repair_rows,
            "correction_elapsed_seconds": [
                record.get("elapsed_seconds") for record in repair_correction_records
            ],
            "checks": repair_summary_checks,
        },
        "checks": {
            "127_boundaries_x_2_calls": len(summary["pc"]["boundary_records"]) == 127
            and boundary_call_count == 254,
            "raw_254": len(raw_entries) == 254,
            "logical_sequences_1_to_254": sequence_ok,
            "final_254": len(rows) == 254,
            "physical_255": len(raw_entries) + correction_count == 255,
            "one_extra_repair": correction_count == 1,
            "at_most_two_extra_solves_per_logical_call": correction_limit_ok,
            "raw_g_denominator_matches_worker": denominator_ok,
            "correction_g_uses_raw_denominator": correction_denominator_ok,
            "raw_reported_rho_recomputed": reported_ok,
            "epsilon_closure": epsilon_closure_ok,
            "all_records_finite": finite_ok,
            "every_final_rho_le_1e-10": bool(rows) and max(final_rhos) <= RAW_A4_LIMIT,
            "matrix_and_port_identity": identity_ok and policy_ok and not unknown_phase_files,
            "correction_phase_ids_1_to_n": all(
                [
                    [
                        int(_correction_index(item["phase"]))
                        for _, item in correction_by_sequence.get(sequence, [])
                    ]
                    == list(range(1, len(correction_by_sequence.get(sequence, [])) + 1))
                    for sequence in raw_sequences
                ]
            ),
            "boundary_repair_deltas_and_cumulative": all(repair_summary_checks.values())
            and repair_phase_ok,
        },
        "unknown_phase_files": unknown_phase_files,
        "rows": rows,
    }


def _sample_archive_facts(current_dir: Path, reference_dir: Path) -> dict[str, Any]:
    current_path = current_dir / "full3d_reference_samples.npz"
    reference_path = reference_dir / "full3d_reference_samples.npz"
    coordinate_names = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    value_names = ("E_V_per_m", "H_A_per_m", "E_t_interface_V_per_m", "H_t_interface_A_per_m")
    result: dict[str, Any] = {
        "current_archive_sha256": sha256(current_path),
        "reference_archive_sha256": sha256(reference_path),
        "coordinates": {},
        "values": {},
        "full_fe_metrics": {},
    }
    with np.load(current_path, allow_pickle=False) as current, np.load(
        reference_path, allow_pickle=False
    ) as reference:
        coordinate_ok = True
        for name in coordinate_names:
            left, right = np.asarray(current[name]), np.asarray(reference[name])
            exact = bool(left.shape == right.shape and np.array_equal(left, right))
            coordinate_ok = coordinate_ok and exact
            result["coordinates"][name] = {"shape": list(left.shape), "exact": exact}
        for name in value_names:
            left, right = np.asarray(current[name]), np.asarray(reference[name])
            delta = left - right
            reference_norm = float(np.linalg.norm(right.ravel()))
            absolute = float(np.max(np.abs(delta), initial=0.0))
            relative = float(np.linalg.norm(delta.ravel()) / max(reference_norm, np.finfo(float).tiny))
            near_zero = reference_norm <= 1.0e-12 and absolute <= 1.0e-10
            result["values"][name] = {
                "shape": list(left.shape),
                "relative_l2_sample": relative,
                "max_absolute_sample": absolute,
                "reference_norm_sample": reference_norm,
                "near_zero_absolute_gate": near_zero,
                "pass": bool(coordinate_ok and (relative <= FIELD_LIMIT or near_zero)),
            }
        result["coordinate_gate"] = coordinate_ok
    result["sample_field_gate"] = bool(result["coordinate_gate"]) and all(
        item["pass"] for item in result["values"].values()
    )
    result["full_fe_metrics"] = _saved_fe_metric_facts(current_dir, reference_dir)
    return result


def old_b_regression(current_dir: Path, reference_dir: Path, current_output: Mapping[str, Any], reference_output: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the two saved B outputs without phase fitting or renormalization."""

    from src.runners.physical_macro_v12 import _compare_saved_output

    saved_output = _compare_saved_output(
        current_output,
        reference_output,
        current_dir=current_dir,
        reference_dir=reference_dir,
    )
    sample = _sample_archive_facts(current_dir, reference_dir)
    current_orders = read_json(current_dir / "dtn_port_diffraction_orders_3d.json")["orders"]
    reference_orders = read_json(reference_dir / "dtn_port_diffraction_orders_3d.json")["orders"]
    current_by_key = {_mode_key(row): row for row in current_orders}
    reference_by_key = {_mode_key(row): row for row in reference_orders}
    current_keys = [_mode_key(row) for row in current_orders]
    reference_keys = [_mode_key(row) for row in reference_orders]
    same_keys = (
        len(current_orders) == len(set(current_keys)) == 80
        and len(reference_orders) == len(set(reference_keys)) == 80
        and set(current_keys) == set(reference_keys)
    )
    power_files = {
        "R_total": "R_total",
        "T_total": "T_total",
        "A_balance": "A_balance",
    }
    current_power = current_output["port_metrics"]
    reference_power = reference_output["port_metrics"]
    current_volume = current_output["volume_metrics"]["A_volume_total"]
    reference_volume = reference_output["volume_metrics"]["A_volume_total"]
    total_diffs = {
        **{
            name: abs(float(current_power[key]) - float(reference_power[key]))
            for name, key in power_files.items()
        },
        "A_volume": abs(float(current_volume) - float(reference_volume)),
    }
    modal = saved_output.get("modal", {})
    modal_power_difference = float(modal.get("power_max_absolute_difference", math.inf))
    modal_amplitude_difference = float(modal.get("amplitude_relative_difference", math.inf))
    selected_field = saved_output.get("selected_field", {})
    full_fe_metrics = sample["full_fe_metrics"]
    full_fe_available = full_fe_metrics.get("status") == "AVAILABLE"
    regression_pass = bool(
        full_fe_available
        and selected_field.get("status") == "AVAILABLE"
        and modal_power_difference <= MODE_POWER_LIMIT
        and saved_output.get("power_max_absolute_difference", math.inf) <= OUTPUT_LIMIT
        and sample["sample_field_gate"]
        and same_keys
        and modal_amplitude_difference <= MODE_AMPLITUDE_LIMIT
        and max(total_diffs.values()) <= OUTPUT_LIMIT
    )
    status = (
        "PASS"
        if regression_pass
        else "FAIL"
        if full_fe_available
        else "PARTIAL_PASS_POINT_SAMPLES_AND_MODAL_ONLY"
    )
    return {
        "reused_saved_output_checker": saved_output,
        "coordinate_aligned_samples": sample,
        "mode_inventory": {
            "same_80_keys": same_keys,
            "current_count": len(current_orders),
            "reference_count": len(reference_orders),
            "phase_fitting": False,
        },
        "mode_power": {
            "max_absolute_difference": modal.get("power_max_absolute_difference"),
            "quantity": "normalized per-mode R/T from established saved-output checker",
            "limit": MODE_POWER_LIMIT,
            "pass": bool(same_keys) and modal_power_difference <= MODE_POWER_LIMIT,
        },
        "mode_amplitude": {
            "max_relative_difference": modal.get("amplitude_relative_difference"),
            "limit": MODE_AMPLITUDE_LIMIT,
            "pass": bool(same_keys) and modal_amplitude_difference <= MODE_AMPLITUDE_LIMIT,
        },
        "RTA_A_volume": {
            "absolute_differences": total_diffs,
            "limit": OUTPUT_LIMIT,
            "pass": bool(total_diffs) and max(total_diffs.values()) <= OUTPUT_LIMIT,
        },
        "full_fe_metrics": full_fe_metrics,
        "status": status,
        "pass": regression_pass,
    }


def _event_times(events: Iterable[Mapping[str, Any]], names: Iterable[str]) -> dict[str, int]:
    wanted = set(names)
    result: dict[str, int] = {}
    for event in events:
        name = str(event["event"])
        if name not in wanted:
            continue
        if name in result:
            raise ValueError(f"duplicate boundary event: {name}")
        result[name] = int(event["timestamp_ns"])
    return result


def _window_facts(resource_path: Path, start_ns: int, end_ns: int) -> dict[str, Any]:
    count = 0
    rss_peak: int | None = None
    pss_peak: int | None = None
    swap_peak: int | None = None
    compiler_samples = 0
    with resource_path.open(encoding="utf-8") as stream:
        for line in stream:
            sample = json.loads(line)
            timestamp = int(sample["timestamp_ns"])
            if start_ns <= timestamp <= end_ns:
                count += 1
                rss = int(sample["rss_bytes"])
                pss = int(sample["pss_bytes"])
                swap = int(sample["swap_bytes"])
                rss_peak = rss if rss_peak is None else max(rss_peak, rss)
                pss_peak = pss if pss_peak is None else max(pss_peak, pss)
                swap_peak = swap if swap_peak is None else max(swap_peak, swap)
                compiler_samples += int(sample.get("compiler_descendant_count", 0) > 0)
    return {
        "start_timestamp_ns": start_ns,
        "end_timestamp_ns": end_ns,
        "sample_count": count,
        "rss_peak_bytes": rss_peak,
        "pss_peak_bytes": pss_peak,
        "swap_peak_bytes": swap_peak,
        "compiler_descendant_samples": compiler_samples,
        "pss_peak_is_independent_of_rss_peak": True,
    }


def resource_and_cost_facts(
    run_root: Path,
    summary: Mapping[str, Any],
    repo_root: Path,
    a4_facts: Mapping[str, Any],
) -> dict[str, Any]:
    events = [json.loads(line) for line in (run_root / "v24_events.jsonl").open(encoding="utf-8")]
    boundary_names = {
        "v20_form_preparation_started",
        "v20_form_preparation_complete",
        "schur_factor_symbolic_started",
        "schur_factor_symbolic_complete",
        "schur_factor_numeric_started",
        "schur_factor_numeric_complete",
        "v20_outer_ksp_started",
        "z3_independent_final_residual_complete",
        "v24_formal_release_timing_before_release",
        "v20_post_release_final_residual_complete",
        "v24_worker_complete",
    }
    times = _event_times(events, boundary_names)
    resource_path = run_root / "watchdog" / "resources.jsonl"
    worker_resource_path = run_root / "v24_worker_resources.jsonl"
    watchdog_summary = read_json(run_root / "watchdog" / "summary.json")
    watchdog_samples = 0
    rss_peak = None
    pss_peak = None
    swap_peak = None
    all_status_readable = True
    all_pss_readable = True
    unreadable_pids: set[int] = set()
    vanished_pids: set[int] = set()
    memory_sample_count = 0
    min_mem_available = None
    min_effective_available = None
    reserve_values: set[int] = set()
    min_launch_cap = None
    global_swap_sample_max = {"pswpin_pages": 0, "pswpout_pages": 0}
    with resource_path.open(encoding="utf-8") as stream:
        for line in stream:
            sample = json.loads(line)
            watchdog_samples += 1
            rss = int(sample["rss_bytes"])
            pss = int(sample["pss_bytes"])
            swap = int(sample["swap_bytes"])
            rss_peak = rss if rss_peak is None else max(rss_peak, rss)
            pss_peak = pss if pss_peak is None else max(pss_peak, pss)
            swap_peak = swap if swap_peak is None else max(swap_peak, swap)
            all_status_readable = all_status_readable and bool(sample.get("all_status_readable"))
            all_pss_readable = all_pss_readable and bool(sample.get("pss_all_readable"))
            unreadable_pids.update(int(pid) for pid in sample.get("unreadable_pids", []))
            vanished_pids.update(int(pid) for pid in sample.get("vanished_pids", []))
            envelope = sample.get("memory_envelope", {})
            if envelope:
                memory_sample_count += 1
                mem_available = int(envelope["mem_available_bytes"])
                effective_available = int(envelope["effective_available_bytes"])
                reserve = int(envelope["reserve_bytes"])
                launch_cap = int(envelope["launch_cap_bytes"])
                min_mem_available = (
                    mem_available
                    if min_mem_available is None
                    else min(min_mem_available, mem_available)
                )
                min_effective_available = (
                    effective_available
                    if min_effective_available is None
                    else min(min_effective_available, effective_available)
                )
                reserve_values.add(reserve)
                min_launch_cap = (
                    launch_cap if min_launch_cap is None else min(min_launch_cap, launch_cap)
                )
            global_pages = sample.get("global_swap_pages", {})
            global_swap_sample_max["pswpin_pages"] = max(
                global_swap_sample_max["pswpin_pages"],
                int(global_pages.get("pswpin_pages", 0)),
            )
            global_swap_sample_max["pswpout_pages"] = max(
                global_swap_sample_max["pswpout_pages"],
                int(global_pages.get("pswpout_pages", 0)),
            )
    worker_samples = sum(1 for _ in worker_resource_path.open(encoding="utf-8"))
    windows = {
        "jit_form_preparation": (times["v20_form_preparation_started"], times["v20_form_preparation_complete"]),
        "symbolic_factor": (times["schur_factor_symbolic_started"], times["schur_factor_symbolic_complete"]),
        "numeric_factor": (times["schur_factor_numeric_started"], times["schur_factor_numeric_complete"]),
        "factor_total": (times["schur_factor_symbolic_started"], times["schur_factor_numeric_complete"]),
        "outer_solve_plus_final_native_check": (
            times["v20_outer_ksp_started"],
            times["z3_independent_final_residual_complete"],
        ),
        "release_and_post_release": (times["v24_formal_release_timing_before_release"], times["v20_post_release_final_residual_complete"]),
        "post_release_output": (times["v20_post_release_final_residual_complete"], times["v24_worker_complete"]),
    }
    phases = {name: _window_facts(resource_path, *bounds) for name, bounds in windows.items()}
    preparation = next(event["facts"] for event in events if event["event"] == "v20_form_preparation_complete")
    compiler_events = preparation["compiler_events"]
    numeric = next(event["facts"] for event in events if event["event"] == "schur_factor_numeric_complete")
    numeric_resource = numeric["numeric_resource"]
    numeric_envelope = numeric_resource.get("memory_envelope", {})
    snapshots = summary["solver"]["snapshots"]
    step_rows = []
    previous_seconds = 0.0
    for snapshot in snapshots:
        solve_seconds = float(snapshot["solve_seconds"])
        step_rows.append(
            {
                "iteration": int(snapshot["iteration"]),
                "solve_seconds_cumulative": solve_seconds,
                "solve_seconds_increment": solve_seconds - previous_seconds,
                "explicit_relative_residual": float(snapshot["explicit_true_residual"]),
            }
        )
        previous_seconds = solve_seconds
    correction_records = [
        correction
        for row in a4_facts["rows"]
        for correction in row.get("corrections", [])
    ]
    boundary_repair_records = [
        record
        for boundary in summary["pc"]["boundary_records"]
        for call in boundary["pc"]["inexact_balance"]["calls"]
        for record in call["inner"]["repair"]["records"]
        if record.get("phase") == "correction" and int(record.get("index", -1)) == 1
    ]

    formal_ledger_path = repo_root / "benchmarks/artifacts/task39extra/dual_condensed_laptop_speed_v24/review_v22_laptop_speed_after_a4_fix/shared_workflow_ledger.json"
    prefix_root = repo_root / "results/euv_grazing1_phi0/task39extra_v24_p4_prefix_original_h7p5__full3d_iterative__mpi1__Mna/20260920T081515.830696Z"
    prefix_watchdog_path = prefix_root / "watchdog" / "summary.json"
    prefix_ledger_path = repo_root / "benchmarks/artifacts/task39extra/dual_condensed_laptop_speed_v24_prefix/review_v22_laptop_speed_after_a4_fix_p4_prefix/shared_workflow_ledger.json"
    component_watchdog_path = repo_root / "benchmarks/artifacts/task39extra/b_capacity_v22/root_engineering/components/v24_full_pc_990_component_real_v2/watchdog/summary.json"
    old_ledger_path = repo_root / "benchmarks/artifacts/task39extra/dual_condensed_physical_memory_v23/review_v23_original_b_physical_memory_trial/shared_workflow_ledger.json"
    formal_ledger = read_json(formal_ledger_path)
    prefix_ledger = read_json(prefix_ledger_path)
    old_ledger = read_json(old_ledger_path)
    prefix_watchdog = read_json(prefix_watchdog_path)
    component_watchdog = read_json(component_watchdog_path)
    formal_run_summary_path = run_root / "run_summary.json"
    old_run_summary_path = repo_root / "results/euv_grazing1_phi0/task39extra_v23_b_physical_memory_original_h7p5__full3d_iterative__mpi1__Mna/20260920T004707.275665Z/run_summary.json"
    return {
        "formal_watchdog_authority": {
            "resource_path": str(resource_path),
            "resource_sha256": sha256(resource_path),
            "sample_count": watchdog_samples,
            "rss_peak_bytes": rss_peak,
            "pss_peak_bytes": pss_peak,
            "swap_peak_bytes": swap_peak,
            "summary_rss_peak_bytes": watchdog_summary["sampled_process_tree_rss_peak_bytes"],
            "summary_sample_count": watchdog_summary["samples"],
            "summary_classification": watchdog_summary["classification"],
            "summary_descendants_cleared": watchdog_summary["descendants_cleared"],
            "summary_zero_swap": watchdog_summary["sampled_process_tree_swap_peak_bytes"] == 0,
            "all_status_readable": all_status_readable,
            "all_pss_readable": all_pss_readable,
            "unreadable_pids": sorted(unreadable_pids),
            "vanished_pids": sorted(vanished_pids),
            "memory_envelope_samples": memory_sample_count,
            "memory_envelope": {
                "min_mem_available_bytes": min_mem_available,
                "min_effective_available_bytes": min_effective_available,
                "reserve_bytes": sorted(reserve_values),
                "min_launch_cap_bytes": min_launch_cap,
                "available_exceeds_reserve": bool(
                    min_effective_available is not None
                    and reserve_values
                    and min_effective_available >= max(reserve_values)
                ),
            },
            "global_swap_sample_max": global_swap_sample_max,
            "global_swap_activity": watchdog_summary.get("global_swap_activity"),
            "job_swap_activity": watchdog_summary.get("job_swap_activity"),
            "terminal_resource_identity_matches": (
                watchdog_samples == watchdog_summary["samples"]
                and rss_peak == watchdog_summary["sampled_process_tree_rss_peak_bytes"]
                and swap_peak == watchdog_summary["sampled_process_tree_swap_peak_bytes"]
            ),
        },
        "worker_sampled_resources_non_authority": {
            "path": str(worker_resource_path),
            "sha256": sha256(worker_resource_path),
            "sample_count": worker_samples,
            "scope": "worker snapshot; not the full watchdog process-tree authority",
        },
        "phase_windows": phases,
        "jit": {
            "compiler_event_count": len(compiler_events),
            "cache_hits": sum(bool(event["cache_hit"]) for event in compiler_events),
            "cache_misses": sum(not bool(event["cache_hit"]) for event in compiler_events),
            "compiler_elapsed_seconds": sum(float(event["elapsed_seconds"]) for event in compiler_events),
            "compiler_descendant_observed_in_window": phases["jit_form_preparation"]["compiler_descendant_samples"] > 0,
        },
        "factor": {
            "symbolic_seconds": float(numeric["symbolic_seconds"]),
            "numeric_seconds": float(numeric["numeric_seconds"]),
            "native_allocated_bytes_upper": numeric["mumps_memory_observation"]["infog19_allocated_bytes_upper"],
            "native_allocated_mb": numeric["mumps_memory_observation"]["infog19_allocated_mb"],
            "native_used_bytes_upper": numeric["mumps_memory_observation"]["infog22_used_bytes_upper"],
            "native_used_mb": numeric["mumps_memory_observation"]["infog22_used_mb"],
            "native_memory_observation_readable": bool(
                numeric["mumps_memory_observation"].get("allocation_is_not_inferred_from_icntl23")
            ),
            "matrix_nz_allocated": numeric["matrix_info_after_factor"].get("nz_allocated"),
            "matrix_nz_used": numeric["matrix_info_after_factor"].get("nz_used"),
            "numeric_resource": {
                "all_status_readable": numeric_resource.get("all_status_readable"),
                "pss_all_readable": numeric_resource.get("pss_all_readable"),
                "rss_bytes": numeric_resource.get("rss_bytes"),
                "pss_bytes": numeric_resource.get("pss_bytes"),
                "swap_bytes": numeric_resource.get("swap_bytes"),
                "unreadable_pids": numeric_resource.get("unreadable_pids"),
                "vanished_pids": numeric_resource.get("vanished_pids"),
                "memory_envelope": numeric_envelope,
            },
        },
        "ksp": {
            "actual_ksp_solve_monotonic_seconds": float(summary["solver"]["ksp_solve_monotonic_seconds"]),
            "solver_elapsed_seconds_not_used_as_ksp": float(summary["solver"]["elapsed_seconds"]),
            "iterations": int(summary["solver"]["iterations"]),
            "per_checkpoint_step_rows": step_rows,
        },
        "postprocess": {
            "outer_solve_plus_final_native_check_window": phases[
                "outer_solve_plus_final_native_check"
            ],
            "pure_ksp_window": None,
            "pure_ksp_window_note": "No exact KSP-end timestamp was saved; use solver.ksp_solve_monotonic_seconds for KSP duration, not a resource window.",
            "release_window": phases["release_and_post_release"],
            "output_window": phases["post_release_output"],
        },
        "affinity": {
            "status": "UNKNOWN_NOT_RECORDED",
            "requested_mpi_ranks": 1,
            "requested_thread_variables": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
            "actual_cpu_affinity": None,
            "reason": "The saved watchdog/member schema has no CPU-affinity field; the ended process cannot be queried retroactively.",
        },
        "refinement": {
            "logical_calls_with_correction": [
                row["logical_call_sequence"]
                for row in a4_facts["rows"]
                if row["correction_count"]
            ],
            "extra_solve_count": len(correction_records),
            "correction_boundary_record_elapsed_seconds": [
                record.get("elapsed_seconds") for record in boundary_repair_records
            ],
            "correction_interface_elapsed_seconds": [
                record.get("interface_elapsed_seconds") for record in correction_records
            ],
            "boundary_correction_record_count": len(boundary_repair_records),
            "boundary_correction_phase_indices": [
                int(record["index"]) for record in boundary_repair_records
            ],
            "boundary_repair_checks": {
                "one_correction_record": len(boundary_repair_records) == 1,
                "correction_index_one": [
                    int(record["index"]) for record in boundary_repair_records
                ] == [1],
                "elapsed_seconds_recorded": all(
                    _finite(record.get("elapsed_seconds"))
                    for record in boundary_repair_records
                ),
            },
            "timing_semantics": {
                "boundary_record_elapsed": "repair.records[].elapsed_seconds; includes the correction record's recorded repair interval",
                "interface_elapsed": "correction JSON interface_facts.elapsed_seconds; bare F4 interface timing only",
            },
        },
        "cost_accounting": {
            "prefix_watchdog_seconds": prefix_watchdog["elapsed_seconds"],
            "prefix_watchdog_summary_sha256": sha256(prefix_watchdog_path),
            "full_pc_component_watchdog_seconds": component_watchdog["elapsed_seconds"],
            "full_pc_component_watchdog_summary_sha256": sha256(component_watchdog_path),
            "formal_full_workflow_seconds": read_json(formal_run_summary_path)["full_workflow_monotonic_seconds"],
            "formal_run_summary_sha256": sha256(formal_run_summary_path),
            "engineering_preparation_and_review_seconds": None,
            "engineering_unknown_reason": "No stopwatch-bound engineering ledger for source editing/review was saved; it is not inferred.",
            "formal_ledger_seconds": formal_ledger["elapsed_seconds"],
            "formal_ledger_sha256": sha256(formal_ledger_path),
            "prefix_ledger_seconds": prefix_ledger["elapsed_seconds"],
            "prefix_ledger_sha256": sha256(prefix_ledger_path),
            "old_v23_full_workflow_seconds_preserved": read_json(old_run_summary_path)["full_workflow_monotonic_seconds"],
            "old_v23_run_summary_sha256": sha256(old_run_summary_path),
            "old_v23_ledger_seconds_preserved": old_ledger["elapsed_seconds"],
            "old_v23_ledger_sha256": sha256(old_ledger_path),
            "old_v23_ledger_semantics": "historical V23 batch ledger; not asserted to be the successful V23 scene runtime",
            "semantics": "watchdog/formal monotonic, component watchdog, and conservative ledger are reported separately and are not added.",
        },
    }


def audit_run(run_root: Path, old_root: Path, repo_root: Path) -> dict[str, Any]:
    summary_path = run_root / "physical_dual_condensed_laptop_speed_v24_summary.json"
    summary = read_json(summary_path)
    old_summary_path = old_root / "physical_dual_condensed_physical_memory_v23_summary.json"
    old_summary = read_json(old_summary_path)
    final_packet = read_json(run_root / "final_residual" / "z3_final.json")
    post_packet = read_json(run_root / "post_release_final_residual" / "z3_post_release_final.json")
    final = residual_packet_facts(run_root / "final_residual" / "z3_final.json", repo_root)
    post = residual_packet_facts(run_root / "post_release_final_residual" / "z3_post_release_final.json", repo_root)
    official_packet = read_json(run_root / "official_output" / "z3_output.json")
    old_packet = read_json(old_root / "official_output" / "z3_output.json")
    old_b = old_b_regression(
        run_root / "numerical_output",
        old_root / "numerical_output",
        official_packet["output"],
        old_packet["output"],
    )
    # Import these existing V21 checks only after all pure raw parsing has
    # succeeded.  They inspect saved files and do not instantiate a solver.
    from benchmarks.check_dual_condensed_robustness_v21 import (
        _check_channels,
        _field_output_facts_v21,
    )

    channel_checks, channel_facts = _check_channels(
        run_root / "numerical_output", official_packet["output"]
    )
    field_checks, field_facts = _field_output_facts_v21(
        run_root / "numerical_output", official_packet["output"]
    )
    a4 = a4_raw_facts(summary, run_root)
    pc_facts = pc_boundary_facts(summary)
    resources = resource_and_cost_facts(run_root, summary, repo_root, a4)
    saved_identity = _saved_identity_facts(
        run_root,
        old_root,
        summary,
        old_summary,
        official_packet,
        old_packet,
        final_packet,
        post_packet,
    )
    identity = {
        "summary_source_sha": summary["source_sha"],
        "run_manifest_source_sha": read_json(run_root / "run_manifest.json")["source_sha"],
        "summary_input_sha256": summary["operator_identity"]["input_sha256"],
        "summary_physical_model_sha256": summary["operator_identity"]["physical_model_sha256"],
        "operator_identity_sha256": summary["operator_identity_sha256"],
        "matrix_before_factor": summary["interface_stack"]["matrix_identity_before_factor"],
        "matrix_before_release": summary["interface_stack"]["matrix_identity_before_release"],
        "matrix_identity_unchanged": summary["interface_stack"]["matrix_identity_before_factor"]
        == summary["interface_stack"]["matrix_identity_before_release"],
        "official_output_identity": official_packet["identity"],
        "official_output_json_sha256": sha256(run_root / "official_output" / "z3_output.json"),
        "saved_identity": saved_identity,
    }
    checks = {
        "identity": all(saved_identity["checks"].values())
        and identity["summary_source_sha"] == identity["run_manifest_source_sha"]
        and identity["matrix_identity_unchanged"]
        and identity["matrix_before_factor"] == identity["matrix_before_release"],
        "final_residual": all(final["checks"].values()),
        "post_release_residual": all(post["checks"].values()),
        "same_final_post_release_residual": math.isclose(
            final["explicit_ratio_from_rhs_minus_applied"],
            post["explicit_ratio_from_rhs_minus_applied"],
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        ),
        "a4_raw_and_repaired": all(a4["checks"].values()),
        "pc_boundary_contract_and_closure": pc_facts["passed"],
        "channels_from_raw": all(channel_checks.values()),
        "field_archive_from_raw": all(field_checks.values()),
        "old_b_same_discrete_regression": old_b["pass"],
        "formal_watchdog_terminal": resources["formal_watchdog_authority"]["terminal_resource_identity_matches"]
        and resources["formal_watchdog_authority"]["summary_classification"] == "COMPLETED"
        and resources["formal_watchdog_authority"]["summary_descendants_cleared"]
        and resources["formal_watchdog_authority"]["summary_zero_swap"]
        and resources["formal_watchdog_authority"]["all_status_readable"]
        and resources["formal_watchdog_authority"]["all_pss_readable"]
        and not resources["formal_watchdog_authority"]["unreadable_pids"]
        and resources["formal_watchdog_authority"]["memory_envelope"]["available_exceeds_reserve"]
        and resources["formal_watchdog_authority"]["global_swap_activity"]["delta"] == {
            "pswpin_pages": 0,
            "pswpout_pages": 0,
        },
    }
    limitations = [
        "Old V23 remains a historical 58/59 negative checker result; passing same-discrete regression does not upgrade old B authority.",
        "Actual CPU affinity is unknown because the saved watchdog schema did not record it.",
        "Formal watchdog terminal samples are authoritative; the worker resource snapshot is reported separately and is not used as the formal peak.",
    ]
    if old_b["full_fe_metrics"].get("status") == "AVAILABLE":
        limitations.append(
            "The full FE L2/scaled-curl comparison is bound to the separate offline engineering metric artifact and its frozen V21 mesh/MPC identity; it is not a new PDE solve."
        )
    else:
        limitations.append(
            "Full FE L2/scaled-curl is unavailable or invalid; point-sample E/H differences are not substituted."
        )
    return {
        "schema": "task039extra.v24.independent-offline-audit.v2",
        "checker_type": "raw_fields_plus_saved_v23_regression",
        "execution": {
            "status": "OFFLINE_ONLY",
            "pde_started": False,
            "factor_started": False,
            "component_rerun": False,
        },
        "formal_run_root": str(run_root),
        "old_v23_run_root": str(old_root),
        "source_sha": summary["source_sha"],
        "input_sha256": summary["operator_identity"]["input_sha256"],
        "summary_sha256": sha256(summary_path),
        "identity": identity,
        "a4": a4,
        "pc_boundary": pc_facts,
        "a6_final": final,
        "a6_post_release": post,
        "channels": {"checks": channel_checks, "facts": channel_facts},
        "field_archive": {"checks": field_checks, "facts": field_facts},
        "old_b_regression": old_b,
        "resources_and_cost": resources,
        "checks": checks,
        "passed": all(checks.values()),
        "limitations": limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_run(args.run_root.resolve(), args.old_root.resolve(), args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "output": str(args.output), "schema": result["schema"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
