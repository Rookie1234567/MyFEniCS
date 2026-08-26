"""Independent raw checker for the Task040 V5 Route-C watchdog closeout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


WORKER_SCHEMA = "task040.v5.route_c.online_long_fgmres.v1"
WATCHDOG_SCHEMA = "task040.level_a.watchdog.v1"
WORKER_METHOD = "task040_v5_route_c_online_long_fgmres"
HARD_STOP_BYTES = 45 * 2**30
SWAP_LIMIT_BYTES = 0
TERMINAL_CLEANUP_STAGES = frozenset(
    {"v5_route_c_cleanup"}
)
ROUTE_C_LABELS = ("external_dtn_coupling", "fixed_random_repeat_0")
REQUIRED_ROOT_FILES = {
    "watchdog_summary": "watchdog_summary.json",
    "process_tree_samples": "process_tree_samples.jsonl",
    "memory_stage_markers": "memory_stage_markers.raw.jsonl",
    "memory_stages": "memory_stages.jsonl",
    "worker_run_summary": "worker/run_summary.json",
    "worker_manifest": "worker/route_c_manifest.json",
    "worker_stdout": "worker_stdout.txt",
}

__all__ = ["check_route_c", "main"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_source_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        char in "0123456789abcdef" for char in value
    )


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row {line_number} is not an object: {path}")
        rows.append(value)
    return rows


def _argv_value(argv: Any, flag: str) -> str | None:
    if not isinstance(argv, list) or argv.count(flag) != 1:
        return None
    index = argv.index(flag)
    if index + 1 >= len(argv) or not isinstance(argv[index + 1], str):
        return None
    return argv[index + 1]


def _process_tree(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    authority = row.get("resource_authority")
    if not isinstance(authority, Mapping):
        return None
    tree = authority.get("process_tree")
    return tree if isinstance(tree, Mapping) else None


def _terminal_cleanup_row(row: Mapping[str, Any], run_summary: Path) -> bool:
    tree = _process_tree(row)
    return bool(
        row.get("post_sample_return_code") is None
        and run_summary.is_file()
        and row.get("stage") in TERMINAL_CLEANUP_STAGES
        and row.get("stage_status") == "complete"
        and isinstance(tree, Mapping)
        and tree.get("pids")
        and tree.get("all_status_readable") is False
    )


def _route_c_audit(manifest: Mapping[str, Any]) -> dict[str, Any]:
    route = manifest.get("route_c")
    records = route.get("records") if isinstance(route, Mapping) else None
    labels = route.get("labels") if isinstance(route, Mapping) else None
    per_label: dict[str, Any] = {}
    residual_values_pass = True
    no_signal = True
    final_iterations_pass = True
    conditional_256_pass = True
    if not isinstance(records, Mapping) or labels != list(ROUTE_C_LABELS):
        residual_values_pass = False
        final_iterations_pass = False
        conditional_256_pass = False
    else:
        for label in ROUTE_C_LABELS:
            record = records.get(label)
            checkpoints = record.get("checkpoints") if isinstance(record, Mapping) else None
            checkpoint_64 = checkpoints.get("64") if isinstance(checkpoints, Mapping) else None
            checkpoint_128 = checkpoints.get("128") if isinstance(checkpoints, Mapping) else None
            r64 = (
                checkpoint_64.get("true_residual_relative")
                if isinstance(checkpoint_64, Mapping)
                else None
            )
            r128 = (
                checkpoint_128.get("true_residual_relative")
                if isinstance(checkpoint_128, Mapping)
                else None
            )
            valid = (
                _finite(r64)
                and _finite(r128)
                and float(r64) > 0.0
                and float(r128) > 0.0
            )
            drop = math.log10(float(r64) / float(r128)) if valid else None
            final_iteration = record.get("final_iteration") if isinstance(record, Mapping) else None
            label_no_signal = bool(
                valid
                and float(r128) > 0.9
                and drop < 0.05
                and final_iteration == 128
            )
            label_conditional_256 = bool(
                isinstance(record, Mapping)
                and record.get("conditional_256_authorized") is False
                and record.get("conditional_256_completed") is False
            )
            per_label[label] = {
                "r64": r64,
                "r128": r128,
                "drop": drop,
                "no_signal": label_no_signal,
                "r128_above_0_9": bool(_finite(r128) and float(r128) > 0.9),
                "drop_below_0_05": bool(_finite(drop) and float(drop) < 0.05),
                "final_iteration": final_iteration,
                "conditional_256_authorized": (
                    record.get("conditional_256_authorized")
                    if isinstance(record, Mapping)
                    else None
                ),
                "conditional_256_completed": (
                    record.get("conditional_256_completed")
                    if isinstance(record, Mapping)
                    else None
                ),
            }
            residual_values_pass = residual_values_pass and valid
            no_signal = no_signal and label_no_signal
            final_iterations_pass = final_iterations_pass and final_iteration == 128
            conditional_256_pass = conditional_256_pass and label_conditional_256

    shared = route.get("shared_slow_directions") if isinstance(route, Mapping) else None
    matches = shared.get("matches") if isinstance(shared, Mapping) else None
    threshold = shared.get("threshold") if isinstance(shared, Mapping) else None
    stable_components: list[str] = []
    if isinstance(matches, list) and _finite(threshold):
        by_component: dict[str, list[Mapping[str, Any]]] = {}
        for match in matches:
            if not isinstance(match, Mapping) or not _finite(match.get("normalized_correlation")):
                continue
            if float(match["normalized_correlation"]) < float(threshold):
                continue
            component = match.get("component")
            if isinstance(component, str):
                by_component.setdefault(component, []).append(match)
        for component, component_matches in by_component.items():
            pairs = {
                (item.get("left_restart"), item.get("right_restart"))
                for item in component_matches
            }
            left_restarts = {pair[0] for pair in pairs}
            right_restarts = {pair[1] for pair in pairs}
            if len(pairs) >= 2 and len(left_restarts) >= 2 and len(right_restarts) >= 2:
                stable_components.append(component)
    stable_components.sort()
    stable_count = len(stable_components)
    shared_fields_pass = bool(
        isinstance(shared, Mapping)
        and isinstance(matches, list)
        and _finite(threshold)
        and shared.get("count") == stable_count
        and shared.get("stable_components") == stable_components
    )
    direction = route.get("direction_audit_gate") if isinstance(route, Mapping) else None
    group_pc = manifest.get("group_pc")
    factor_lifecycle = (
        group_pc.get("factor_lifecycle") if isinstance(group_pc, Mapping) else None
    )
    ready = factor_lifecycle.get("ready") if isinstance(factor_lifecycle, Mapping) else None
    after = factor_lifecycle.get("after") if isinstance(factor_lifecycle, Mapping) else None
    factor_pass = bool(
        isinstance(factor_lifecycle, Mapping)
        and factor_lifecycle.get("construction_count") == 3
        and factor_lifecycle.get("destruction_count") == 3
        and factor_lifecycle.get("simultaneous_factor_count_max") == 3
        and factor_lifecycle.get("pc_setup_count") == 1
        and factor_lifecycle.get("continuous_source_solve_count") == 2
        and isinstance(ready, Mapping)
        and ready.get("factor_count_ready") == 3
        and isinstance(after, Mapping)
        and after.get("factor_count_after_cleanup") == 0
        and after.get("destroyed") is True
        and after.get("action_destroyed") is True
        and after.get("parent_released") is True
    )
    direction_pass = bool(
        isinstance(direction, Mapping)
        and direction.get("basis_persistence_observed") is True
        and direction.get("basis_persistence_all_pass") is True
        and direction.get("canonical_interface_trace_observed") is True
        and direction.get("canonical_interface_trace_all_pass") is True
        and direction.get("interface_projection_observed") is True
        and direction.get("interface_projection_all_pass") is True
        and direction.get("pass") is True
        and direction.get("replicated") is False
    )
    conditional_gate = route.get("conditional_256_gate") if isinstance(route, Mapping) else None
    conditional_gate_pass = bool(
        isinstance(conditional_gate, Mapping)
        and conditional_gate.get("authorized_pass") is False
        and conditional_gate.get("aggregate_pass") is False
        and conditional_gate.get("aggregate_completed") is False
        and isinstance(conditional_gate.get("per_source"), Mapping)
        and set(conditional_gate["per_source"]) == set(ROUTE_C_LABELS)
        and all(
            isinstance(conditional_gate["per_source"].get(label), Mapping)
            and conditional_gate["per_source"][label].get("authorized") is False
            and conditional_gate["per_source"][label].get("completed") is False
            and conditional_gate["per_source"][label].get("final_iteration") == 128
            for label in ROUTE_C_LABELS
        )
    )
    external = manifest.get("external_dtn_coupling")
    external_observed = external.get("observed") if isinstance(external, Mapping) else None
    external_expected = {
        "matrix_objects": {"C": 0, "D": 0, "H": 0},
        "minimal_external_component_instances_total": 4,
        "minimal_external_coupling_construction_call_count": 2,
        "minimal_external_coupling_kind_count": 1,
        "minimal_external_coupling_objects_constructed": 1,
        "minimal_external_peak_live_components": 2,
        "minimal_external_surface_component_count": 2,
    }
    external_pass = bool(
        isinstance(external, Mapping)
        and external.get("path") == "minimal_surface_rhs_only"
        and external.get("physical_dtn_operator_constructed") is False
        and external.get("full_C_materialized") is False
        and external.get("D_materialized") is False
        and external.get("H_materialized") is False
        and external.get("woodbury_inverse_constructed") is False
        and external_observed == external_expected
    )
    numeric_inventory = route.get("numeric_collective_inventory") if isinstance(route, Mapping) else None
    numeric_inventory_pass = bool(
        isinstance(numeric_inventory, Mapping)
        and numeric_inventory.get("fe_sized_numeric_allgather_count") == 0
        and numeric_inventory.get("owner_row_basis_replicated") is False
    )
    rhs_two_exact_zero_system_created = bool(
        manifest.get("rhs_vectors_loaded") == 2
        and manifest.get("exact_output_vectors_loaded") == 0
        and manifest.get("exact_output_vectors_consumed") == 0
        and isinstance(route, Mapping)
        and route.get("exact_output_vectors_consumed") == 0
        and manifest.get("system_created") is True
        and manifest.get("qep_calls") == 0
        and manifest.get("full_side_exact_factor_count") == 0
        and manifest.get("pde_solve") == "not_run"
    )
    observed_signal = route.get("signal") if isinstance(route, Mapping) else None
    observed_signal_pass = bool(
        isinstance(observed_signal, Mapping)
        and observed_signal.get("classification") == "ROUTE_C_NO_SIGNAL"
        and observed_signal.get("no_signal") is True
    )
    return {
        "labels": list(ROUTE_C_LABELS),
        "per_label": per_label,
        "shared_stable_count": stable_count,
        "shared_stable_components": stable_components,
        "checks": {
            "labels": isinstance(records, Mapping) and labels == list(ROUTE_C_LABELS),
            "r64_r128_values_recomputed": residual_values_pass,
            "r128_above_0_9_and_drop_below_0_05": residual_values_pass and no_signal,
            "final_iteration_128": final_iterations_pass,
            "conditional_256_unauthorized": conditional_256_pass and conditional_gate_pass,
            "shared_stability_recomputed": shared_fields_pass,
            "route_c_no_signal_recomputed": (
                residual_values_pass
                and no_signal
                and stable_count == 0
                and shared_fields_pass
                and final_iterations_pass
            ),
            "observed_signal_cross_check": observed_signal_pass,
            "factor_three_to_zero": factor_pass,
            "qep_zero": manifest.get("qep_calls") == 0,
            "full_side_factor_zero": manifest.get("full_side_exact_factor_count") == 0,
            "rhs_two_exact_zero_system_created": rhs_two_exact_zero_system_created,
            "minimal_external_rhs_contract": external_pass,
            "direction_audit_pass": direction_pass,
            "numeric_collective_contract": numeric_inventory_pass,
            "observed_no_signal_classification": (
                manifest.get("classification") == "ROUTE_C_NO_SIGNAL"
                and manifest.get("status") == "completed_route_c_screen"
            ),
        },
    }


def _failure_result(
    *,
    formal_root: Path,
    formal_source_sha: str,
    checker_source_sha: str,
    failures: list[str],
    checks: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "task040.v5.route_c.teardown_adjudication.v2",
        "formal_root": str(formal_root),
        "formal_source_sha": formal_source_sha,
        "checker_source_sha": checker_source_sha,
        "evidence_valid": False,
        "checker_pass": False,
        "gate_pass": False,
        "classification": "IMPLEMENTATION_FAILURE",
        "failures": sorted(set(failures)),
        "gate_failures": [],
        "checks": dict(checks or {}),
        "read_files": [],
        "numeric_npy_read": False,
    }


def check_route_c(
    formal_root: str | Path,
    formal_source_sha: str,
    checker_source_sha: str,
    *,
    observed_outer_return_code: int = 2,
) -> dict[str, Any]:
    """Recompute raw Route-C teardown evidence without loading numerical arrays."""
    root = Path(formal_root).resolve()
    failures: list[str] = []
    checks: dict[str, bool] = {}
    if not _is_source_sha(formal_source_sha):
        failures.append("formal_source_sha")
    if not _is_source_sha(checker_source_sha):
        failures.append("checker_source_sha")
    paths = {name: root / relative for name, relative in REQUIRED_ROOT_FILES.items()}
    checks["required_files_present"] = all(path.is_file() for path in paths.values())
    if failures or not checks["required_files_present"]:
        if not checks["required_files_present"]:
            failures.append("required_files_present")
        return _failure_result(
            formal_root=root,
            formal_source_sha=formal_source_sha,
            checker_source_sha=checker_source_sha,
            failures=failures,
            checks=checks,
        )
    try:
        watchdog = _load_json(paths["watchdog_summary"])
        run_summary = _load_json(paths["worker_run_summary"])
        manifest = _load_json(paths["worker_manifest"])
        timeline_rows = _load_jsonl(paths["process_tree_samples"])
        marker_rows = _load_jsonl(paths["memory_stage_markers"])
        stage_rows = _load_jsonl(paths["memory_stages"])
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _failure_result(
            formal_root=root,
            formal_source_sha=formal_source_sha,
            checker_source_sha=checker_source_sha,
            failures=["raw_json_parse", type(exc).__name__],
            checks=checks,
        )

    argv = watchdog.get("command")
    input_name = _argv_value(argv, "--input")
    input_path = Path(input_name).resolve() if input_name is not None else None
    checks.update(
        {
            "formal_source_sha_format": _is_source_sha(formal_source_sha),
            "checker_source_sha_format": _is_source_sha(checker_source_sha),
            "watchdog_schema": watchdog.get("schema") == WATCHDOG_SCHEMA,
            "worker_schema": run_summary.get("schema") == WORKER_SCHEMA,
            "manifest_schema": manifest.get("schema") == WORKER_SCHEMA,
            "watchdog_method": watchdog.get("method") == WORKER_METHOD,
            "worker_manifest_bytes_equal": paths["worker_run_summary"].read_bytes()
            == paths["worker_manifest"].read_bytes(),
            "worker_source_identity": (
                watchdog.get("source_sha")
                == formal_source_sha
                == run_summary.get("source_sha")
                == manifest.get("source_sha")
            ),
            "input_path_present": input_path is not None and input_path.is_file(),
            "outer_return_code_observed": observed_outer_return_code == 2,
        }
    )
    raw_paths = dict(paths)
    if checks["input_path_present"]:
        input_sha = _sha256(input_path)
        checks["input_hash_bound"] = (
            run_summary.get("input_sha256")
            == manifest.get("input_sha256")
            == input_sha
        )
        raw_paths["official_input"] = input_path
    else:
        checks["input_hash_bound"] = False
        failures.append("input_path_present")

    artifact_paths = {
        "memory_stage_markers.raw.jsonl": paths["memory_stage_markers"],
        "memory_stages.jsonl": paths["memory_stages"],
        "process_tree_samples.jsonl": paths["process_tree_samples"],
        "worker_stdout.txt": paths["worker_stdout"],
    }
    artifact_hashes = watchdog.get("artifact_hashes")
    checks["watchdog_artifact_hashes"] = isinstance(artifact_hashes, Mapping) and all(
        _is_sha256(artifact_hashes.get(name))
        and artifact_hashes[name] == _sha256(path)
        for name, path in artifact_paths.items()
    )
    checks["watchdog_run_summary_hash"] = (
        watchdog.get("run_summary_sha256") == _sha256(paths["worker_run_summary"])
        and watchdog.get("run_summary_present") is True
    )
    checks["watchdog_command"] = bool(
        isinstance(argv, list)
        and argv[:3] == ["mpiexec", "-n", "8"]
        and "--v5-route-c" in argv
        and "--watchdog-enabled" in argv
        and "--bottom-route-only" in argv
        and argv.count("--input") == 1
        and argv.count("--exact-spool-root") == 1
        and argv.count("--run-directory") == 1
        and argv.count("--source-sha") == 1
        and _argv_value(argv, "--source-sha") == formal_source_sha
        and _argv_value(argv, "--run-directory") == str(root / "worker")
        and _argv_value(argv, "--memory-stages") == str(paths["memory_stages"])
        and _argv_value(argv, "--memory-markers") == str(paths["memory_stage_markers"])
    )
    checks["watchdog_process_control"] = bool(
        watchdog.get("return_code") == 0
        and watchdog.get("termination_reason") == "natural_exit"
        and isinstance(watchdog.get("process_control"), Mapping)
        and watchdog["process_control"].get("worker_exited") is True
        and watchdog["process_control"].get("process_group_exited") is True
        and watchdog["process_control"].get("sigkill_required") is False
    )
    checks["route_c_resource_contract"] = bool(
        watchdog.get("route_c_hard_stop_bytes") == HARD_STOP_BYTES
        and watchdog.get("route_c_swap_limit_bytes") == SWAP_LIMIT_BYTES
        and watchdog.get("route_c_timeout_seconds") == 21600
    )
    marker_stages = [row.get("stage") for row in marker_rows]
    stage_names = [row.get("stage") for row in stage_rows]
    checks["marker_stage_contract"] = bool(
        marker_rows
        and len(marker_rows) == len(stage_rows)
        and marker_stages == stage_names
        and marker_stages[0] == "construction_begin"
        and marker_stages[-1] in TERMINAL_CLEANUP_STAGES
        and stage_rows[0].get("status") == "running"
        and stage_rows[-1].get("status") == "complete"
    )

    timeline_shape = True
    rss_values: list[int] = []
    swap_values: list[int] = []
    readable_lines: list[int] = []
    unreadable_lines: list[int] = []
    terminal_candidate_lines: list[int] = []
    post_fix_authoritative_lines: list[int] = []
    terminal_details: list[dict[str, Any]] = []
    process_exit_lines: list[int] = []
    for line_number, row in enumerate(timeline_rows, 1):
        tree = _process_tree(row)
        rss = tree.get("rss_bytes") if isinstance(tree, Mapping) else None
        swap = tree.get("swap_bytes") if isinstance(tree, Mapping) else None
        valid_tree = bool(
            isinstance(tree, Mapping)
            and isinstance(tree.get("pids"), list)
            and tree.get("pids")
            and isinstance(tree.get("all_status_readable"), bool)
            and "post_sample_return_code" in row
        )
        valid_numbers = (
            isinstance(rss, int)
            and not isinstance(rss, bool)
            and rss >= 0
            and isinstance(swap, int)
            and not isinstance(swap, bool)
            and swap >= 0
        )
        timeline_shape = timeline_shape and valid_tree and valid_numbers
        if not valid_tree or not valid_numbers:
            continue
        rss_values.append(rss)
        swap_values.append(swap)
        if tree["all_status_readable"]:
            readable_lines.append(line_number)
        else:
            unreadable_lines.append(line_number)
        if row.get("post_sample_return_code") is not None:
            process_exit_lines.append(line_number)
        if _terminal_cleanup_row(row, paths["worker_run_summary"]):
            terminal_candidate_lines.append(line_number)
            terminal_details.append(
                {
                    "line_1_based": line_number,
                    "timestamp_utc": row.get("timestamp_utc"),
                    "elapsed_seconds": row.get("elapsed_seconds"),
                    "stage": row.get("stage"),
                    "stage_status": row.get("stage_status"),
                    "rss_bytes": rss,
                    "swap_bytes": swap,
                    "post_sample_return_code": row.get("post_sample_return_code"),
                }
            )

    candidate_set = set(terminal_candidate_lines)
    terminal_suffix_lines: list[int] = []
    for line_number in range(len(timeline_rows), 0, -1):
        if line_number not in candidate_set:
            break
        terminal_suffix_lines.insert(0, line_number)
    suffix_expected = (
        list(range(terminal_suffix_lines[0], len(timeline_rows) + 1))
        if terminal_suffix_lines
        else []
    )
    suffix_pass = bool(terminal_suffix_lines) and (
        terminal_candidate_lines == terminal_suffix_lines == suffix_expected
    )
    prefix_end = terminal_suffix_lines[0] - 1 if suffix_pass else len(timeline_rows)
    post_fix_authoritative_lines = list(range(1, prefix_end + 1))
    live_unreadable_lines = [
        line_number for line_number in unreadable_lines if line_number <= prefix_end
    ]
    max_rss = max(rss_values, default=-1)
    max_swap = max(swap_values, default=-1)
    derived_all_status_readable = bool(
        post_fix_authoritative_lines and not live_unreadable_lines
    )
    raw_observed_rss_below_hard_stop = bool(rss_values) and max_rss < HARD_STOP_BYTES
    raw_observed_swap_zero = bool(swap_values) and max_swap == SWAP_LIMIT_BYTES
    process_tree_authority_complete = derived_all_status_readable
    rss_authority_complete = bool(
        process_tree_authority_complete and raw_observed_rss_below_hard_stop
    )
    swap_authority_complete = bool(
        process_tree_authority_complete and raw_observed_swap_zero
    )
    checks["timeline_shape"] = bool(timeline_rows) and timeline_shape
    checks["recorded_peak_matches_raw"] = bool(
        watchdog.get("peak_rss_bytes") == max_rss
        and watchdog.get("peak_swap_bytes") == max_swap
    )
    raw_authoritative_true_count = sum(
        row.get("authoritative_sample") is True for row in timeline_rows
    )
    raw_terminal_excluded_true_count = sum(
        row.get("terminal_teardown_excluded") is True for row in timeline_rows
    )
    checks["original_summary_counts"] = bool(
        watchdog.get("sample_count")
        == watchdog.get("authoritative_sample_count")
        == raw_authoritative_true_count
        == len(timeline_rows)
    )
    checks["original_summary_flags"] = bool(
        watchdog.get("all_status_readable") is False
        and watchdog.get("swap_authority_readable") is False
        and watchdog.get("terminal_teardown_excluded_count") == 0
        and raw_terminal_excluded_true_count == 0
    )
    checks["raw_recorded_sample_flags"] = all(
        row.get("authoritative_sample") is True
        and row.get("terminal_teardown_excluded") is False
        for row in timeline_rows
    )
    checks["raw_resource_summary"] = bool(
        watchdog.get("hard_stop_bytes") == HARD_STOP_BYTES
        and watchdog.get("route_c_hard_stop_bytes") == HARD_STOP_BYTES
        and watchdog.get("route_c_peak_memory_bytes") == max_rss
        and watchdog.get("route_c_hard_stop_crossed") == (max_rss >= HARD_STOP_BYTES)
        and watchdog.get("peak_swap_bytes") == max_swap
    )
    route_audit = _route_c_audit(manifest)
    route_checks = route_audit["checks"]
    checks["formal_route_contract"] = all(route_checks.values())
    checks["formal_route_identity_cross_reference"] = bool(
        run_summary.get("classification") == manifest.get("classification")
        and run_summary.get("route_c", {}).get("labels") == list(ROUTE_C_LABELS)
    )
    evidence_valid = bool(all(checks.values()))
    teardown_adjudication_gate = bool(suffix_pass and not process_exit_lines)
    route_c_no_signal_stop_gate_triggered = route_checks[
        "route_c_no_signal_recomputed"
    ]
    route_c_positive_signal_gate_pass = not route_c_no_signal_stop_gate_triggered
    resource_authority_gate_pass = bool(
        raw_observed_rss_below_hard_stop
        and raw_observed_swap_zero
        and rss_authority_complete
        and swap_authority_complete
        and not process_exit_lines
    )
    gate_checks = {
        "worker_natural_exit": checks["watchdog_process_control"],
        "terminal_suffix_present": bool(terminal_suffix_lines),
        "teardown_adjudication": teardown_adjudication_gate,
        "all_prefix_rows_readable": derived_all_status_readable,
        "no_process_exit_during_sample": not process_exit_lines,
        "raw_unreadable_rows_are_terminal_suffix": bool(
            suffix_pass and unreadable_lines == terminal_suffix_lines
        ),
        "raw_observed_rss_below_hard_stop": raw_observed_rss_below_hard_stop,
        "raw_observed_swap_zero": raw_observed_swap_zero,
        "process_tree_authority_complete_after_terminal_exclusion": (
            process_tree_authority_complete
        ),
        "rss_authority_complete": rss_authority_complete,
        "swap_authority_complete": swap_authority_complete,
        "resource_authority_gate_pass": resource_authority_gate_pass,
        "route_c_no_signal_stop_gate_triggered": route_c_no_signal_stop_gate_triggered,
        "route_c_positive_signal_gate_pass": route_c_positive_signal_gate_pass,
    }
    overall_candidate_gate_pass = bool(
        evidence_valid
        and route_c_positive_signal_gate_pass
        and resource_authority_gate_pass
    )
    gate_pass = overall_candidate_gate_pass
    if not evidence_valid:
        classification = "IMPLEMENTATION_FAILURE"
        failures.extend(name for name, passed in checks.items() if not passed)
    elif route_c_no_signal_stop_gate_triggered and not resource_authority_gate_pass:
        classification = "VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP"
    elif route_c_no_signal_stop_gate_triggered and not teardown_adjudication_gate:
        classification = "VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_TEARDOWN_GAP"
    elif route_c_no_signal_stop_gate_triggered:
        classification = "VALID_NEGATIVE_ROUTE_C_NO_SIGNAL"
    else:
        classification = "VALID_NEGATIVE_ROUTE_C_GATE_NOT_SATISFIED"
    authority_gate_names = {
        "process_tree_authority_complete_after_terminal_exclusion",
        "rss_authority_complete",
        "swap_authority_complete",
        "resource_authority_gate_pass",
    }
    gate_failures = [
        name
        for name, passed in gate_checks.items()
        if not passed and name in authority_gate_names
    ]
    teardown_failures = [
        name
        for name, passed in gate_checks.items()
        if not passed and name in {"terminal_suffix_present", "teardown_adjudication"}
    ]
    stop_reasons = []
    if route_c_no_signal_stop_gate_triggered:
        stop_reasons.append("route_c_no_signal")
    stop_reasons.extend(teardown_failures)
    stop_reasons.extend(gate_failures)
    raw_file_sha256 = {name: _sha256(path) for name, path in raw_paths.items()}
    read_files = [
        {"role": name, "path": str(path), "sha256": raw_file_sha256[name]}
        for name, path in sorted(raw_paths.items())
    ]
    return {
        "schema": "task040.v5.route_c.teardown_adjudication.v2",
        "formal_root": str(root),
        "formal_source_sha": formal_source_sha,
        "checker_source_sha": checker_source_sha,
        "observed_outer_return_code": observed_outer_return_code,
        "evidence_valid": evidence_valid,
        "checker_pass": evidence_valid,
        "gate_pass": gate_pass,
        "teardown_adjudication_gate": teardown_adjudication_gate,
        "route_c_no_signal_stop_gate_triggered": route_c_no_signal_stop_gate_triggered,
        "route_c_positive_signal_gate_pass": route_c_positive_signal_gate_pass,
        "resource_authority_gate_pass": resource_authority_gate_pass,
        "overall_candidate_gate_pass": overall_candidate_gate_pass,
        "classification": classification,
        "formal_classification_observed": run_summary.get("classification"),
        "failures": sorted(set(failures)),
        "gate_failures": gate_failures,
        "stop_reasons": stop_reasons,
        "checks": checks,
        "route_c_audit": route_audit,
        "gate_checks": gate_checks,
        "numeric_npy_read": False,
        "read_files": read_files,
        "raw_file_sha256": raw_file_sha256,
        "original_watchdog_summary": {
            "return_code": watchdog.get("return_code"),
            "termination_reason": watchdog.get("termination_reason"),
            "all_status_readable": watchdog.get("all_status_readable"),
            "swap_authority_readable": watchdog.get("swap_authority_readable"),
            "sample_count": watchdog.get("sample_count"),
            "authoritative_sample_count": watchdog.get("authoritative_sample_count"),
            "terminal_teardown_excluded_count": watchdog.get(
                "terminal_teardown_excluded_count"
            ),
        },
        "derived_timeline": {
            "raw_row_count": len(timeline_rows),
            "raw_recorded_authoritative_true_count": sum(
                row.get("authoritative_sample") is True for row in timeline_rows
            ),
            "raw_recorded_terminal_excluded_true_count": sum(
                row.get("terminal_teardown_excluded") is True for row in timeline_rows
            ),
            "readable_process_tree_count": len(readable_lines),
            "unreadable_process_tree_count": len(unreadable_lines),
            "terminal_candidate_lines_1_based": terminal_candidate_lines,
            "terminal_teardown_excluded_count": len(terminal_suffix_lines),
            "terminal_teardown_excluded_lines_1_based": terminal_suffix_lines,
            "terminal_teardown_rows": terminal_details,
            "live_unreadable_lines_1_based": sorted(set(live_unreadable_lines)),
            "process_exit_lines_1_based": process_exit_lines,
            "suffix_pass": suffix_pass,
            "derived_authoritative_row_count": len(post_fix_authoritative_lines),
            "derived_readable_authoritative_row_count": len(post_fix_authoritative_lines)
            - len(set(live_unreadable_lines)),
            "derived_all_status_readable": derived_all_status_readable,
            "raw_observed_rss_below_hard_stop": raw_observed_rss_below_hard_stop,
            "raw_observed_swap_zero": raw_observed_swap_zero,
            "process_tree_authority_complete_after_terminal_exclusion": (
                process_tree_authority_complete
            ),
            "rss_authority_complete": rss_authority_complete,
            "swap_authority_complete": swap_authority_complete,
            "dedicated_cgroup_present": watchdog.get("dedicated_cgroup_present"),
            "dedicated_cgroup_swap_diagnostic": {
                "readable": watchdog.get("dedicated_cgroup_swap_readable"),
                "peak_swap_bytes": watchdog.get("peak_dedicated_cgroup_swap_bytes"),
                "zero_observed": (
                    watchdog.get("dedicated_cgroup_present") is True
                    and watchdog.get("dedicated_cgroup_swap_readable") is True
                    and watchdog.get("peak_dedicated_cgroup_swap_bytes") == 0
                ),
            },
            "max_rss_bytes": max_rss,
            "max_swap_bytes": max_swap,
        },
        "adjudication": {
            "terminal_teardown_bug_confirmed": bool(terminal_suffix_lines),
            "outer_watchdog_rc2_not_a_numerical_exception": bool(
                observed_outer_return_code == 2
                and watchdog.get("return_code") == 0
                and watchdog.get("termination_reason") == "natural_exit"
            ),
            "numerical_no_signal_stop_gate": route_c_no_signal_stop_gate_triggered,
        },
    }


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", required=True)
    parser.add_argument("--formal-source-sha", required=True)
    parser.add_argument("--checker-source-sha", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--observed-outer-return-code", type=int, default=2)
    args = parser.parse_args(argv)
    formal_root = Path(args.formal_root).resolve()
    output_path = Path(args.output).resolve()
    if output_path.is_relative_to(formal_root):
        result = _failure_result(
            formal_root=formal_root,
            formal_source_sha=args.formal_source_sha,
            checker_source_sha=args.checker_source_sha,
            failures=["output_inside_formal_root"],
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    try:
        result = check_route_c(
            formal_root,
            args.formal_source_sha,
            args.checker_source_sha,
            observed_outer_return_code=args.observed_outer_return_code,
        )
    except Exception as exc:  # keep evidence JSON-safe if the checker itself fails
        result = _failure_result(
            formal_root=formal_root,
            formal_source_sha=args.formal_source_sha,
            checker_source_sha=args.checker_source_sha,
            failures=["checker_exception", type(exc).__name__],
        )
        result["exception_message"] = str(exc)
    result["output_disjoint_from_formal_root"] = True
    _write_json_atomic(output_path, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["checker_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
