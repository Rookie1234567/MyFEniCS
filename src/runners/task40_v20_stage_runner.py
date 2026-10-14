"""Task40 V20 case routing and bounded original-size preflight stages."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tomllib
from typing import Any

import numpy as np


V20_STAGE_NAMES = (
    "preflight",
    "geometry_inventory",
    "target_operator_probe",
    "local_port_components",
    "build_and_symbolic",
    "one_q_numeric",
    "full",
)
V20_TARGET_Q0 = 0
V20_TARGET_FULL_FIELD_QUALIFIED = False
_V20_TARGET_RUN_ID = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
_V20_TARGET_PROFILE = "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
_V22_TARGET_OPERATOR_PROFILE = "task40extra_v22_p6_y_orbit_target_original_ny8_operator_probe_v1"
_V20_COMPLETED_PREFIX_SCOPE = (
    "reuse the separately verified original c00 packet and all c01-c59 packets from the hash-bound "
    "failed original-size TARGET_ORIGINAL_NY8 local/port run; replay every saved local packet, "
    "then measure only the top/bottom port witnesses"
)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"V20 stage evidence cannot encode {type(value).__name__}")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = json.dumps(
        value, sort_keys=True, indent=2, allow_nan=False, default=_json_default
    ).encode("utf-8") + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_v26_minus_d_failed_attempt(
    run_family: Path,
    *,
    source_sha: str,
    run_id: str,
    input_sha256: str,
    physical_model_sha256: str,
) -> Path:
    matches: list[Path] = []
    for operation_path in run_family.glob("*/v26_selected_q_stage.json"):
        attempt = operation_path.parent
        try:
            run_manifest = json.loads((attempt / "run_manifest.json").read_text(encoding="utf-8"))
            run_summary = json.loads((attempt / "run_summary.json").read_text(encoding="utf-8"))
            operation = json.loads(operation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        resource = run_summary.get("resource_authority", {})
        if (
            run_manifest.get("source_sha") == source_sha
            and run_manifest.get("run_id") == run_id
            and run_manifest.get("input_sha256") == input_sha256
            and run_manifest.get("physical_model_sha256") == physical_model_sha256
            and run_summary.get("result_classification") == "WORKER_FAILED"
            and resource.get("classification") == "WORKER_FAILED"
            and operation.get("status") == "FAILED_V26_SELECTED_Q_GATES"
            and operation.get("failure_type") == "KeyError"
            and operation.get("failure_message") == "'minus_D'"
            and operation.get("resource_blocker") is None
            and operation.get("official_result") is False
        ):
            matches.append(attempt.resolve())
    if len(matches) != 1:
        raise RuntimeError(
            f"V26 native recovery requires one exact prior minus_D leaf failure; found {len(matches)}"
        )
    return matches[0]


def _retain_v26_footer_bindings(
    operation: dict[str, Any],
    *,
    artifact_binding: Mapping[str, Any] | None,
    recovery_binding: Mapping[str, Any] | None,
    current_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep completed V26 evidence identities when a later stage stops or fails."""
    existing_artifact = operation.get("v26_artifact_binding")
    if isinstance(artifact_binding, Mapping):
        operation["v26_artifact_binding"] = {
            **dict(artifact_binding),
            **(dict(existing_artifact) if isinstance(existing_artifact, Mapping) else {}),
        }
    existing_recovery = operation.get("v26_native_recovery")
    if isinstance(recovery_binding, Mapping):
        operation["v26_native_recovery"] = {
            **dict(recovery_binding),
            **(dict(existing_recovery) if isinstance(existing_recovery, Mapping) else {}),
        }
    if isinstance(current_identity, Mapping):
        operation["v26_current_identity"] = dict(current_identity)
    return operation


def _repo_path(root: Path, value: Any, label: str) -> Path:
    candidate = Path(str(value))
    if candidate.is_absolute():
        candidate = candidate.resolve()
    else:
        candidate = (root / candidate).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"V20 component resume {label} escapes the repository") from error
    return candidate


def _saved_q0_resource_gate_key(stage: str) -> str:
    """Bound repeated cell/port/projection gate records to semantic groups."""
    for prefix, key in (
        ("task40_v27_saved_q0/volume/cell/", "saved_q0/volume/cell"),
        ("task40_v27_saved_q0/direct/C/provider/", "saved_q0/surface/C"),
        ("task40_v27_saved_q0/direct/-D/provider/", "saved_q0/surface/minus_D"),
        ("task40_v28_q_projection_support_discovery/", "q0_projection/support_discovery"),
        ("task40_v28_q_projection_support/", "q0_projection/support"),
        ("task40_v28_q_hhat_sparse_scatter/", "q0_H/sparse_scatter"),
    ):
        if stage.startswith(prefix):
            return key
    return stage


def _make_saved_q0_allocation_gate(
    *,
    output_directory: Path,
    disk_reserve_bytes: int,
    resource_admission: Callable[..., Mapping[str, Any]],
    resource_sample: Callable[[], Mapping[str, Any]],
    cgroup_snapshot: Callable[[], Mapping[str, Any]],
    blocked_exception: type[Exception],
    disk_usage: Callable[[Path], Any],
) -> tuple[
    Callable[[str, Mapping[str, Any]], dict[str, Any]],
    dict[str, dict[str, Any]],
    Callable[[], list[dict[str, Any]]],
    dict[str, Any],
]:
    """Create the exact saved-q0 admission callback and its bounded evidence store."""
    records: dict[str, dict[str, Any]] = {}
    timing = {"calls": 0, "seconds": 0.0}

    def remember(stage: str, record: dict[str, Any], *, failed: bool) -> None:
        key = _saved_q0_resource_gate_key(stage)
        record["stage"] = key
        record.setdefault("first_original_stage_label", stage)
        record["last_original_stage_label"] = stage
        if failed:
            record.setdefault("original_failure_stage_label", stage)
        previous = records.get(key)
        if previous is None:
            records[key] = record
            return
        previous["observation_count"] = int(previous.get("observation_count", 1)) + 1
        previous["passed"] = bool(previous.get("passed", True) and record.get("passed", False))
        previous["maximum_additional_object_upper_bound_bytes"] = max(
            int(previous.get("maximum_additional_object_upper_bound_bytes", 0)),
            int(record.get("maximum_additional_object_upper_bound_bytes", 0)),
        )
        previous["maximum_disk_payload_bytes"] = max(
            int(previous.get("maximum_disk_payload_bytes", 0)),
            int(record.get("maximum_disk_payload_bytes", 0)),
        )
        previous["last_request_facts"] = record.get("request_facts")
        previous["last_host_effective_available_bytes"] = record.get(
            "host_effective_available_bytes",
            record.get("memory_admission", {}).get("host_effective_available_bytes"),
        )
        previous["last_original_stage_label"] = stage
        minimum_available = record.get(
            "host_effective_available_bytes",
            record.get("memory_admission", {}).get("host_effective_available_bytes"),
        )
        if type(minimum_available) is int:
            previous["minimum_host_effective_available_bytes"] = min(
                int(previous.get("minimum_host_effective_available_bytes", minimum_available)),
                minimum_available,
            )
        previous["maximum_task_cgroup_memory_current_bytes"] = max(
            int(previous.get("maximum_task_cgroup_memory_current_bytes", 0)),
            int(record.get("maximum_task_cgroup_memory_current_bytes", 0)),
        )
        if failed:
            previous.setdefault("original_failure_stage_label", stage)
            previous["last_failure_facts"] = record.get(
                "failure_facts", record.get("memory_admission")
            )

    def allocation_gate(stage: str, facts: Mapping[str, Any]) -> dict[str, Any]:
        import time

        started = time.perf_counter()
        timing["calls"] = int(timing["calls"]) + 1
        requested = sum(
            int(facts.get(key, 0))
            for key in (
                "additional_payload_bytes",
                "matrix_payload_bytes",
                "workspace_bytes",
                "future_co_resident_reserve_bytes",
            )
        )
        before = dict(cgroup_snapshot())
        try:
            memory = dict(resource_admission(
                stage,
                requested,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            ))
        except blocked_exception as error:
            after = dict(cgroup_snapshot())
            failure_facts = dict(getattr(error, "facts", {}))
            failure_memory = failure_facts.get("memory_envelope", {})
            failure_memory = failure_memory if isinstance(failure_memory, Mapping) else {}
            record = {
                "passed": False,
                "observation_count": 1,
                "request_facts": dict(facts),
                "memory_admission": failure_facts,
                "failure_facts": failure_facts,
                "maximum_additional_object_upper_bound_bytes": requested,
                "maximum_disk_payload_bytes": int(facts.get("disk_payload_bytes", 0)),
                "task_cgroup_memory_before": before,
                "task_cgroup_memory_after": after,
                "maximum_task_cgroup_memory_current_bytes": max(
                    int(before.get("memory_current_bytes", 0) or 0),
                    int(after.get("memory_current_bytes", 0) or 0),
                ),
                "minimum_host_effective_available_bytes": failure_facts.get(
                    "host_effective_available_bytes",
                    failure_memory.get("host_effective_available_bytes"),
                ),
            }
            remember(stage, record, failed=True)
            timing["seconds"] = float(
                timing["seconds"] + time.perf_counter() - started
            )
            raise
        disk_required = int(facts.get("disk_payload_bytes", 0))
        disk_free = int(disk_usage(output_directory).free)
        disk_passed = disk_free >= disk_required + int(disk_reserve_bytes)
        after = dict(cgroup_snapshot())
        record = {
            **memory,
            "passed": disk_passed,
            "observation_count": 1,
            "maximum_additional_object_upper_bound_bytes": requested,
            "maximum_disk_payload_bytes": disk_required,
            "disk_payload_bytes": disk_required,
            "disk_free_bytes": disk_free,
            "disk_reserve_bytes": int(disk_reserve_bytes),
            "disk_gate_passed": disk_passed,
            "request_facts": dict(facts),
            "task_cgroup_memory_before": before,
            "task_cgroup_memory_after": after,
            "minimum_host_effective_available_bytes": memory.get(
                "host_effective_available_bytes"
            ),
            "maximum_task_cgroup_memory_current_bytes": max(
                int(before.get("memory_current_bytes", 0) or 0),
                int(after.get("memory_current_bytes", 0) or 0),
            ),
        }
        if not disk_passed:
            record["failure_facts"] = {
                "stage": stage,
                "additional_object_upper_bound_bytes": requested,
                "disk_payload_bytes": disk_required,
                "disk_free_bytes": disk_free,
                "disk_reserve_bytes": int(disk_reserve_bytes),
                "disk_gate_passed": False,
                "passed": False,
            }
        remember(stage, record, failed=not disk_passed)
        timing["seconds"] = float(
            timing["seconds"] + time.perf_counter() - started
        )
        if not disk_passed:
            raise blocked_exception(
                stage,
                {
                    "stage": stage,
                    "additional_object_upper_bound_bytes": requested,
                    "disk_payload_bytes": disk_required,
                    "disk_free_bytes": disk_free,
                    "disk_reserve_bytes": int(disk_reserve_bytes),
                    "disk_gate_passed": False,
                    "passed": False,
                },
            )
        return record

    def record_list() -> list[dict[str, Any]]:
        return list(records.values())

    return allocation_gate, records, record_list, timing


def _v28_continuation_action(status: str, native_qualification_matches: bool) -> str:
    if status in {"STRUCTURE_COMPLETE_VALUES_PENDING", "NUMERIC_FILL_INCOMPLETE"}:
        return "fill_and_readback"
    if status == "COMPLETE_CSR":
        return "factor_only" if native_qualification_matches else "readback_and_factor"
    raise ValueError(f"unsupported V28 continuation manifest state: {status}")


def _v28_readback_receipt_passes(readback: Mapping[str, Any]) -> bool:
    if readback.get("all_gates_passed") is not True:
        return False
    try:
        limit = float(readback["relative_error_limit"])
        if not 0.0 < limit <= 1.0e-11:
            return False
        errors = [
            float(readback[name]["relative"])
            for name in (
                "q0_case_1_full_csr_vs_native_total",
                "q0_case_2_full_csr_vs_native_total",
                "q0_case_1_trace_plus_port_vs_full_csr",
            )
        ]
        components = readback["q0_case_1_csr_trace_port_masked_components_vs_native"]
        if not isinstance(components, Mapping) or set(components) != {
            "volume", "minus_D", "C", "Hhat"
        }:
            return False
        for item in components.values():
            if not isinstance(item, Mapping):
                return False
            errors.append(float(item["active_block"]["relative"]))
            errors.append(float(item["native_off_block_relative"]))
        return all(np.isfinite(value) and 0.0 <= value <= limit for value in errors)
    except (KeyError, TypeError, ValueError):
        return False


def _load_matching_v28_native_qualification(
    *,
    repo_root: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    expected_pattern_path: Path,
    expected_pattern_sha256: str,
    donor_identity_sha256: str,
    input_sha256: str,
    physical_model_sha256: str,
    run_id: str,
    campaign_window_sha256: str,
    mode_manifest_sha256: str,
    ordered_mode_key_sha256: str,
    sha256_file: Callable[[Path], str],
    path_resolver: Callable[[str | Path], Path] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    """Return only a hash-bound, same-donor native PASS usable for factor-only continuation."""
    artifact_roots = (
        (repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl").resolve(),
        (repo_root / "results/task40extra_nonseparable_0p7nm").resolve(),
    )
    record = manifest.get("native_qualification")
    if not isinstance(record, Mapping):
        return None
    raw_qualification_path = Path(str(record.get("path", "")))
    path = (
        path_resolver(raw_qualification_path)
        if path_resolver is not None
        else raw_qualification_path.resolve()
    )
    if (
        not any(path.is_relative_to(root) for root in artifact_roots)
        or not path.is_file()
        or record.get("status") != "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
        or record.get("sha256") != sha256_file(path)
    ):
        return None
    try:
        qualification = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    artifacts = manifest.get("csr_artifacts", {})
    if not isinstance(artifacts, Mapping):
        return None
    expected_hashes = {
        name: item.get("sha256")
        for name, item in artifacts.items()
        if name in {"indptr", "indices", "data"} and isinstance(item, Mapping)
    }
    identity = qualification.get("source_identity", {})
    identity = identity if isinstance(identity, Mapping) else {}
    pattern = qualification.get("original_pattern_manifest", {})
    pattern = pattern if isinstance(pattern, Mapping) else {}
    readback = qualification.get("readback", {})
    readback = readback if isinstance(readback, Mapping) else {}
    readback_record = qualification.get("readback_artifact", {})
    readback_record = readback_record if isinstance(readback_record, Mapping) else {}
    readback_path_value = Path(str(readback_record.get("path", "")))
    if readback_path_value.is_absolute():
        readback_path = (
            path_resolver(readback_path_value)
            if path_resolver is not None
            else readback_path_value.resolve()
        )
    else:
        readback_path = (path.parent / readback_path_value).resolve()
    raw_pattern_path = Path(str(pattern.get("path", "")))
    mapped_pattern_path = (
        path_resolver(raw_pattern_path)
        if path_resolver is not None
        else raw_pattern_path.resolve()
    )
    raw_csr_manifest_path = Path(str(qualification.get("csr_manifest_path", "")))
    mapped_csr_manifest_path = (
        path_resolver(raw_csr_manifest_path)
        if path_resolver is not None
        else raw_csr_manifest_path.resolve()
    )
    if (
        qualification.get("schema") != "task40extra.review_v28_q0_native_qualification.v1"
        or qualification.get("status") != "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
        or qualification.get("donor_identity_sha256") != donor_identity_sha256
        or identity.get("input_sha256") != input_sha256
        or identity.get("physical_model_sha256") != physical_model_sha256
        or identity.get("run_id") != run_id
        or not isinstance(identity.get("campaign_window_sha256"), str)
        or len(str(identity.get("campaign_window_sha256"))) != 64
        or identity.get("mode_manifest_sha256") != mode_manifest_sha256
        or identity.get("ordered_mode_key_sha256") != ordered_mode_key_sha256
        or qualification.get("campaign_window_sha256")
        != identity.get("campaign_window_sha256")
        or not isinstance(qualification.get("campaign_window_sha256"), str)
        or len(str(qualification.get("campaign_window_sha256"))) != 64
        or mapped_csr_manifest_path != manifest_path.resolve()
        or set(expected_hashes) != {"indptr", "indices", "data"}
        or any(not isinstance(value, str) or len(value) != 64 for value in expected_hashes.values())
        or qualification.get("csr_artifact_hashes") != expected_hashes
        or qualification.get("csr_shape") != manifest.get("shape")
        or qualification.get("stored_structural_slots") != manifest.get("stored_structural_slots")
        or mapped_pattern_path != expected_pattern_path.resolve()
        or pattern.get("sha256") != expected_pattern_sha256
        or not _v28_readback_receipt_passes(readback)
        or readback_record.get("sha256") is None
        or not any(readback_path.is_relative_to(root) for root in artifact_roots)
        or not readback_path.is_file()
        or readback_path.stat().st_size != readback_record.get("bytes")
        or sha256_file(readback_path) != readback_record.get("sha256")
        or readback.get("csr_readback_artifact") != dict(readback_record)
    ):
        return None
    return path, dict(qualification)


def _write_v28_continuation_footer(
    *,
    output_directory: Path,
    operation_path: Path,
    manifest_path: Path,
    progress_path: Path,
    operation: dict[str, Any],
    stop_stage: str,
    profile: str,
    source_sha: str,
    preflight: Mapping[str, Any],
    selector_path: Path,
    selector_sha: str,
    donor_identity_sha256: str,
    resource_gate_records: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Persist a V28 continuation result, including a partial/factor-only attempt."""
    operation["resource_gates"] = resource_gate_records()
    operation["saved_only_no_fe_or_native_rebuild"] = True
    _write_json(operation_path, operation)
    operation_sha = _sha256_file(operation_path)
    status_code = str(operation.get("status", "FAILED_V28_Q0_CONTINUATION"))
    complete_csr = operation.get("complete_numeric_csr") is True
    factor_built = operation.get("factor_or_solve_built") is True
    factor_report = operation.get("factor_lifecycle", {})
    factor_report = factor_report if isinstance(factor_report, Mapping) else {}
    controlled = status_code.startswith(
        ("RESOURCE_CONTROLLED_STOP", "PERFORMANCE_CONTROLLED_STOP")
    )
    passed = status_code in {
        "PASS_COMPLETE_Q0_CSR",
        "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
    }
    if passed:
        partial_status, outcome = "stage_completed", "STAGE_COMPLETED"
        completed = ["preflight", stop_stage]
    elif controlled:
        partial_status, outcome = "controlled_stop", "RESOURCE_CONTROLLED_STOP"
        completed = ["preflight", stop_stage] if complete_csr else ["preflight"]
    elif status_code.endswith("_IN_PROGRESS"):
        partial_status, outcome = "in_progress", "IN_PROGRESS"
        completed = ["preflight", stop_stage] if complete_csr else ["preflight"]
    else:
        partial_status, outcome = "failed", "STAGE_FAILED"
        completed = ["preflight", stop_stage] if complete_csr else ["preflight"]
    manifest_value: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest_value = {}
    artifact_hashes: dict[str, Any] = {}
    preflight_path = output_directory / "v20_stage_preflight.json"
    if preflight_path.is_file():
        artifact_hashes[preflight_path.name] = {
            "path": preflight_path.name,
            "sha256": _sha256_file(preflight_path),
        }
    artifact_hashes[operation_path.name] = {
        "path": operation_path.name,
        "sha256": operation_sha,
    }
    for label, path in ((manifest_path.name, manifest_path), (progress_path.name, progress_path)):
        if path.is_file():
            artifact_hashes[label] = {
                "path": (
                    str(path.relative_to(output_directory))
                    if path.is_relative_to(output_directory)
                    else str(path)
                ),
                "sha256": _sha256_file(path),
            }
    qualification_record = operation.get("native_qualification_receipt", {})
    qualification_record = (
        qualification_record if isinstance(qualification_record, Mapping) else {}
    )
    for label, record in (
        ("native_qualification", qualification_record),
        ("readback", operation.get("csr_readback_artifact", {})),
    ):
        if not isinstance(record, Mapping) or not record.get("path"):
            continue
        candidate = Path(str(record["path"]))
        if candidate.is_absolute():
            path = candidate.resolve()
        elif label == "readback" and qualification_record.get("path"):
            path = (Path(str(qualification_record["path"])).resolve().parent / candidate).resolve()
        else:
            path = (output_directory / candidate).resolve()
        if path.is_file():
            artifact_hashes[label] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": partial_status,
        "outcome": outcome,
        "classification": "SELECTED_REFERENCE_Q_V28_EXISTING_MANIFEST_CONTINUATION",
        "run_id": preflight.get("run_id"),
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": stop_stage,
        "attempted_stages": ["preflight", stop_stage],
        "completed_stages": completed,
        "failed_stage": operation.get("failed_stage") if not passed else None,
        "stage_result": {
            "completed_stage": stop_stage if passed else None,
            "probe_status": status_code,
        },
        "v28_q0_continuation": {
            "operation_path": operation_path.name,
            "operation_sha256": operation_sha,
            "operation_status": status_code,
            "operation": operation,
            "selector_path": str(selector_path),
            "selector_sha256": selector_sha,
            "donor_import_identity_sha256": donor_identity_sha256,
            "resource_gates": resource_gate_records(),
        },
        "q_coverage": {
            "status": "KNOWN" if complete_csr else "IN_PROGRESS" if partial_status == "in_progress" else "KNOWN",
            "expected_q_count": 8,
            "built_q_count": int(complete_csr),
            "full_q_matrix_coverage": "1/8" if complete_csr else "0/8",
            "selected_q": 0,
            "paired_action_q": 4,
            "csr_status": manifest_value.get("status", "NOT_CREATED"),
            "factor_count": int(factor_built),
            "factor_attempt_status": factor_report.get("status", "NOT_RUN"),
            "factor_evicted_after_probe_and_rhs_solve": bool(
                factor_report.get("cleanup", {}).get("destroy_succeeded") is True
            ),
            "max_simultaneous_factors": int(
                factor_report.get("max_simultaneous_native_objects", {}).get("factors", 0)
            ),
            "ksp_created": False,
            "pde_solved": False,
            "reason": (
                "V28 reuses the frozen V27 pattern and data backing; it fills/qualifies q0 only and does not create a KSP or produce official R/T/A."
            ),
        },
        "resource_gate": operation.get("resource_blocker") if controlled else None,
        "cleanup": {
            "status": "OPERATION_RETURNED",
            "owner_cleanup": "V28 existing-manifest continuation",
        },
        "artifact_hashes": artifact_hashes,
        "official_result": False,
        "not_run": ["all other q CSR", "KSP", "target PDE", "official R/T/A"],
        "not_completed": [] if factor_report.get("status") == "PASS_Q0_FACTOR_PROBE_AND_RHS_SOLVE" else ["q0 factor lifecycle"],
        "full_field_release_allowed": False,
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": passed or controlled,
        "errors": [] if passed or controlled else [
            str(operation.get("failure_message", status_code))
        ],
        "official_result": False,
        "status": partial_status,
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def _validate_component_resume_input_identity(
    original_input_path: Path,
    continuation_input_path: Path,
    *,
    resume_manifest_path: str,
    resume_manifest_sha256: str,
) -> None:
    """Require the resume input to differ only by its two manifest bindings."""

    original = tomllib.loads(original_input_path.read_text(encoding="utf-8"))
    continuation = tomllib.loads(continuation_input_path.read_text(encoding="utf-8"))
    original_execution = original.get("execution")
    continuation_execution = continuation.get("execution")
    if not isinstance(original_execution, Mapping) or not isinstance(
        continuation_execution, Mapping
    ):
        raise ValueError("V20 component resume inputs must both contain an execution table")
    resume_fields = (
        "task40_component_resume_manifest_path",
        "task40_component_resume_manifest_sha256",
    )
    if any(key in original_execution for key in resume_fields):
        raise ValueError("V20 original input unexpectedly already contains resume manifest fields")
    if (
        continuation_execution.get(resume_fields[0]) != resume_manifest_path
        or continuation_execution.get(resume_fields[1]) != resume_manifest_sha256
        or original_execution.get("task40_execution_stop_stage") != "local_port_components"
        or continuation_execution.get("task40_execution_stop_stage")
        != "local_port_components"
    ):
        raise ValueError("V20 component resume input has unexpected resume bindings or stop stage")
    comparable_continuation = dict(continuation)
    comparable_execution = dict(continuation_execution)
    for key in resume_fields:
        comparable_execution.pop(key)
    comparable_continuation["execution"] = comparable_execution
    if original != comparable_continuation:
        raise ValueError(
            "V20 continuation input differs from the original beyond the two resume manifest fields"
        )


def _load_completed_local_prefix(
    root: Path,
    spec: Mapping[str, Any],
    classes: list[dict[str, Any]],
    c00_row: dict[str, Any],
    *,
    base_run_directory: Path,
    base_geometry_sha256: str,
    original_campaign_sha256: str,
    expected_campaign_window_path: Path,
    expected_physical_model_sha256: str,
    mode_manifest_sha256: str,
    ordered_mode_key_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verify the exact saved all-class prefix without rebuilding its local tensors."""

    if (
        spec.get("schema") != "task40extra.review_v20_completed_local_prefix.v1"
        or spec.get("scope") != _V20_COMPLETED_PREFIX_SCOPE
        or len(classes) != 60
        or spec.get("run_id") != _V20_TARGET_RUN_ID
        or spec.get("profile") != _V20_TARGET_PROFILE
        or spec.get("physical_model_sha256") == ""
        or spec.get("physical_model_sha256") != expected_physical_model_sha256
        or spec.get("campaign_window_sha256") != original_campaign_sha256
        or spec.get("exit_status") != 4
        or spec.get("result_classification") != "WORKER_FAILED"
    ):
        raise ValueError("V20 completed prefix is outside the reviewed failed target run")
    prefix_run = _repo_path(root, spec.get("run_directory"), "completed-prefix run")
    if prefix_run == base_run_directory or prefix_run.parent != base_run_directory.parent:
        raise ValueError("V20 completed prefix must be the paired target run in the same case directory")
    artifact_specs = spec.get("artifacts")
    required_artifacts = (
        "run_manifest",
        "run_summary",
        "input_original",
        "source_sha_file",
        "physical_model_sha_file",
        "geometry_inventory",
        "service_record",
        "component_summary",
        "partial_result",
        "partial_checker_result",
    )
    if not isinstance(artifact_specs, Mapping) or set(artifact_specs) != set(required_artifacts):
        raise ValueError("V20 completed prefix omitted a required run or failure-footer hash")
    artifact_paths: dict[str, Path] = {}
    for name in required_artifacts:
        item = artifact_specs.get(name)
        if not isinstance(item, Mapping) or not isinstance(item.get("sha256"), str):
            raise ValueError(f"V20 completed prefix omitted the {name} artifact hash")
        path = _repo_path(root, item.get("path"), f"completed-prefix {name}")
        if not path.is_file() or _sha256_file(path) != item["sha256"]:
            raise ValueError(f"V20 completed-prefix {name} artifact hash differs")
        artifact_paths[name] = path
    expected_run_files = {
        "run_manifest": prefix_run / "run_manifest.json",
        "run_summary": prefix_run / "run_summary.json",
        "input_original": prefix_run / "input_original.dat",
        "source_sha_file": prefix_run / "source_sha.txt",
        "physical_model_sha_file": prefix_run / "physical_model_sha256.txt",
        "geometry_inventory": prefix_run / "v20_geometry_inventory.json",
        "component_summary": prefix_run / "v20_local_port_components.json",
        "partial_result": prefix_run / "v20_partial_result.json",
    }
    if any(artifact_paths[name] != path.resolve() for name, path in expected_run_files.items()):
        raise ValueError("V20 completed-prefix run artifact paths do not match its run directory")
    if _sha256_file(artifact_paths["geometry_inventory"]) != base_geometry_sha256:
        raise ValueError("V20 completed-prefix geometry differs from the c00 source geometry")

    prefix_manifest = json.loads(artifact_paths["run_manifest"].read_text(encoding="utf-8"))
    prefix_summary = json.loads(artifact_paths["run_summary"].read_text(encoding="utf-8"))
    service_record = json.loads(artifact_paths["service_record"].read_text(encoding="utf-8"))
    checker = json.loads(artifact_paths["partial_checker_result"].read_text(encoding="utf-8"))
    input_path = _repo_path(root, spec.get("input_path"), "completed-prefix input")
    stage_input_root = (
        root
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs"
    ).resolve()
    if (
        not input_path.is_relative_to(stage_input_root)
        or input_path.name != "target_original_ny8_resource_pilot_v20.dat"
    ):
        raise ValueError("V20 completed-prefix input is outside the exact ignored stage-input tree")
    prefix_campaign = prefix_manifest.get("task40_v20_campaign", {})
    prefix_service_checker = _repo_path(
        root, service_record.get("partial_checker_result_path"), "completed-prefix partial checker"
    )
    input_sha256 = spec.get("input_sha256")
    source_sha = spec.get("source_sha")
    physical_sha256 = spec.get("physical_model_sha256")
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or not isinstance(input_sha256, str)
        or len(input_sha256) != 64
        or not isinstance(physical_sha256, str)
        or len(physical_sha256) != 64
        or _sha256_file(input_path) != input_sha256
        or _sha256_file(artifact_paths["input_original"]) != input_sha256
        or artifact_paths["source_sha_file"].read_text(encoding="utf-8").strip() != source_sha
        or artifact_paths["physical_model_sha_file"].read_text(encoding="utf-8").strip()
        != physical_sha256
        or prefix_manifest.get("run_id") != _V20_TARGET_RUN_ID
        or prefix_manifest.get("source_sha") != source_sha
        or prefix_manifest.get("input_path") != str(input_path)
        or prefix_manifest.get("input_sha256") != input_sha256
        or prefix_manifest.get("physical_model_sha256") != physical_sha256
        or physical_sha256 != expected_physical_model_sha256
        or prefix_manifest.get("task40_v20_campaign", {}).get("window_sha256")
        != original_campaign_sha256
        or prefix_campaign.get("window_path")
        != str(expected_campaign_window_path)
        or prefix_summary.get("run_id") != _V20_TARGET_RUN_ID
        or prefix_summary.get("exit_status") != 4
        or prefix_summary.get("result_classification") != "WORKER_FAILED"
        or prefix_summary.get("task40_v20_campaign", {}).get("window_sha256")
        != original_campaign_sha256
        or prefix_summary.get("task40_v20_campaign", {}).get("window_path")
        != str(expected_campaign_window_path)
        or prefix_service_checker != artifact_paths["partial_checker_result"]
        or artifact_paths["service_record"].parent
        != artifact_paths["partial_checker_result"].parent
        or service_record.get("run_directory") != str(prefix_run)
        or service_record.get("run_manifest_path") != str(artifact_paths["run_manifest"])
        or service_record.get("input_path") != str(input_path)
        or service_record.get("input_sha256") != input_sha256
        or service_record.get("source_sha") != source_sha
        or service_record.get("physical_model_sha256") != physical_sha256
        or service_record.get("campaign_window_sha256") != original_campaign_sha256
        or service_record.get("campaign_window_path")
        != str(expected_campaign_window_path)
        or service_record.get("run_case_result_classification") != "WORKER_FAILED"
        or service_record.get("run_case_returncode") != 3
        or service_record.get("required_checker_passed") is not True
        or service_record.get("partial_footer_cannot_promote_to_full_pass") is not True
        or service_record.get("reported_partial_stage_status") != "failed"
        or service_record.get("workflow_classification") != "PARTIAL_RECEIPT_RECHECKED"
        or service_record.get("workflow_complete") is not False
        or checker.get("status") != "PARTIAL_RECEIPT_CHECKED"
        or checker.get("checker_passed") is not True
        or checker.get("scientific_partial_status") != "failed"
        or checker.get("official_result") is not False
        or checker.get("partial_result_sha256") != artifact_specs["partial_result"]["sha256"]
    ):
        raise ValueError("V20 completed-prefix source, input, service, or failed-footer identity differs")

    component_summary = json.loads(artifact_paths["component_summary"].read_text(encoding="utf-8"))
    class_rows = component_summary.get("local_cell_classes")
    if (
        component_summary.get("schema")
        != "task40extra.review_v20_original_local_port_components.v1"
        or component_summary.get("status") != "PARTIAL_OR_FAILED"
        or component_summary.get("local_cell_class_count") != len(classes)
        or not isinstance(class_rows, list)
        or len(class_rows) != len(classes)
        or [row.get("class_id") for row in class_rows]
        != [row.get("class_id") for row in classes]
        or component_summary.get("mode_count_full_ordered") != 32060
        or component_summary.get("mode_manifest_sha256") != mode_manifest_sha256
        or component_summary.get("ordered_mode_key_sha256") != ordered_mode_key_sha256
        or component_summary.get("all_q_csr_created") is not False
        or component_summary.get("global_p6_space_created") is not False
        or component_summary.get("global_MPC_created") is not False
        or component_summary.get("global_mumps_factor_created") is not False
        or component_summary.get("directional_mpc_qualification", {}).get("status")
        != "PARTIAL_CANONICAL_LOCAL_COMPONENTS"
        or not all(
            row.get("status") == "PASS"
            and row.get("passed") is True
            and isinstance(row.get("gates"), Mapping)
            and all(row["gates"].values())
            for row in class_rows
        )
    ):
        raise ValueError("V20 completed-prefix class or mode inventory is incomplete")
    partial_rows = json.loads(
        artifact_paths["partial_result"].read_text(encoding="utf-8")
    )
    boundary_rows = component_summary.get("boundary_components")
    if (
        partial_rows.get("classification") != "LOCAL_COMPONENT_GATE_FAILED"
        or partial_rows.get("status") != "failed"
        or partial_rows.get("completed_stages")
        != ["preflight", "geometry_inventory", "local_port_components"]
        or not isinstance(boundary_rows, list)
        or {row.get("side") for row in boundary_rows} != {"top", "bottom"}
        or len(boundary_rows) != 2
        or any(
            row.get("status") != "FAILED_LOCAL_PORT_GATE"
            or row.get("error", {}).get("message")
            != "known local trace/interior solution shapes differ"
            for row in boundary_rows
        )
    ):
        raise ValueError("V20 completed-prefix footer is not the reviewed port-shape failure")

    if (
        not isinstance(class_rows[0].get("raw_packet"), Mapping)
        or class_rows[0].get("raw_packet") != c00_row.get("raw_packet")
    ):
        raise ValueError("V20 completed-prefix c00 row omitted its saved packet reference")
    c00_checks = (
        "class_id", "metric_identity", "material_tag", "target_cell_count",
        "filled_reference_cell_count", "interior_rows", "trace_rows", "status", "passed", "gates",
    )
    if any(class_rows[0].get(key) != c00_row.get(key) for key in c00_checks):
        raise ValueError("V20 completed-prefix c00 differs from its separately verified source packet")

    packet_specs = spec.get("class_packets")
    expected_class_ids = [row["class_id"] for row in classes[1:]]
    if (
        not isinstance(packet_specs, list)
        or [row.get("class_id") for row in packet_specs] != expected_class_ids
    ):
        raise ValueError("V20 completed-prefix packet inventory is not the c01-c59 class prefix")
    from src.solvers.task40_v20_local_components import (
        _validate_reused_local_prefix,
        verify_v20_saved_local_component_packet,
    )

    completed_rows = [c00_row]
    for expected_row, packet_spec in zip(class_rows[1:], packet_specs, strict=True):
        class_id = expected_row["class_id"]
        packet_json = _repo_path(root, packet_spec.get("json_path"), f"{class_id} JSON")
        packet_npz = _repo_path(root, packet_spec.get("npz_path"), f"{class_id} NPZ")
        if (
            packet_json != (prefix_run / f"v20_local_{class_id}.json").resolve()
            or packet_npz != (prefix_run / f"v20_local_{class_id}.npz").resolve()
        ):
            raise ValueError(f"V20 completed-prefix {class_id} packet path differs from its run")
        row, _validation = verify_v20_saved_local_component_packet(
            prefix_run,
            expected_row,
            expected_json_sha256=str(packet_spec.get("json_sha256", "")),
            expected_npz_sha256=str(packet_spec.get("npz_sha256", "")),
        )
        completed_rows.append(row)
    _validate_reused_local_prefix(classes, completed_rows)
    validation = {
        "schema": "task40extra.review_v20_completed_local_prefix_readback.v1",
        "status": "PASS",
        "source_run_directory": str(prefix_run),
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_sha256,
        "campaign_window_sha256": original_campaign_sha256,
        "class_count": len(completed_rows),
        "new_packet_count": len(packet_specs),
        "new_local_class_measurement_count": 0,
        "reused_local_class_count": len(completed_rows),
        "class_ids": [row["class_id"] for row in completed_rows],
        "all_packet_matrix_schur_recovery_replays_passed": True,
        "component_summary_sha256": artifact_specs["component_summary"]["sha256"],
        "partial_result_sha256": artifact_specs["partial_result"]["sha256"],
        "service_record_sha256": artifact_specs["service_record"]["sha256"],
        "partial_checker_result_sha256": artifact_specs["partial_checker_result"]["sha256"],
        "scope": (
            _V20_COMPLETED_PREFIX_SCOPE
            + "; c00 used its existing independent verifier; c01-c59 were read back one packet at a "
            "time and their original matrix, Schur, reduced recovery, and full recovery equations "
            "were independently replayed"
        ),
    }
    return completed_rows, validation


def _load_target_component_resume(
    resolved: Mapping[str, Any],
    output_directory: Path,
    *,
    source_sha: str,
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], Any, list[dict[str, Any]], tuple[np.ndarray, ...], list[dict[str, Any]], dict[str, Any]]:
    """Load the bound V20 inventory, mesh axes, and verified saved local prefix."""

    execution = resolved.get("execution", {})
    root = Path(__file__).resolve().parents[2]
    manifest_relative = execution.get("task40_component_resume_manifest_path")
    manifest_sha256 = execution.get("task40_component_resume_manifest_sha256")
    if not isinstance(manifest_relative, str) or not isinstance(manifest_sha256, str):
        raise ValueError("V20 component resume requires a manifest path and SHA-256")
    manifest_path = _repo_path(root, manifest_relative, "manifest path")
    if not manifest_path.is_file() or _sha256_file(manifest_path) != manifest_sha256:
        raise ValueError("V20 component resume manifest hash differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_schema = manifest.get("schema")
    if manifest_schema not in {
        "task40extra.review_v20_target_local_component_resume_manifest.v1",
        "task40extra.review_v20_target_local_component_resume_manifest.v2",
    }:
        raise ValueError("V20 component resume manifest schema is not recognized")
    completed_prefix_spec = manifest.get("completed_prefix")
    if (manifest_schema.endswith(".v1") and completed_prefix_spec is not None) or (
        manifest_schema.endswith(".v2") and not isinstance(completed_prefix_spec, Mapping)
    ):
        raise ValueError("V20 component resume manifest schema and saved prefix do not match")
    if (
        resolved.get("run_id") != _V20_TARGET_RUN_ID
        or resolved.get("solver", {}).get("preconditioner") != _V20_TARGET_PROFILE
        or execution.get("task40_execution_stop_stage") != "local_port_components"
        or preflight.get("mesh_id") != "TARGET_ORIGINAL_NY8"
        or preflight.get("source_sha") != source_sha
    ):
        raise ValueError("V20 component resume is restricted to the exact target local/port case")

    original = manifest.get("original_run", {})
    artifacts = manifest.get("artifacts", {})
    if not isinstance(original, Mapping) or not isinstance(artifacts, Mapping):
        raise ValueError("V20 component resume manifest omitted original identity or artifact hashes")
    original_run = _repo_path(root, original.get("run_directory"), "original run directory")
    current_manifest_path = output_directory / "run_manifest.json"
    if not current_manifest_path.is_file():
        raise ValueError("V20 component resume requires the run_case-created current manifest")
    current_manifest = json.loads(current_manifest_path.read_text(encoding="utf-8"))
    current_campaign = current_manifest.get("task40_v20_campaign", {})
    original_campaign_sha = str(original.get("campaign_window_sha256", ""))
    current_input_path = _repo_path(root, current_manifest.get("input_path"), "current input")
    continuation_input_path = _repo_path(root, preflight.get("input_path"), "continuation input")
    current_window_path = _repo_path(
        root, current_campaign.get("window_path"), "current campaign window"
    )
    if (
        original.get("run_id") != _V20_TARGET_RUN_ID
        or original.get("profile") != _V20_TARGET_PROFILE
        or current_manifest.get("run_id") != _V20_TARGET_RUN_ID
        or current_manifest.get("source_sha") != source_sha
        or current_input_path != continuation_input_path
        or current_manifest.get("input_sha256") != preflight.get("input_sha256")
        or current_manifest.get("physical_model_sha256")
        != preflight.get("physical_model_sha256")
        or preflight.get("physical_model_sha256")
        != original.get("physical_model_sha256")
        or current_campaign.get("window_sha256") != original_campaign_sha
        or not current_window_path.is_file()
        or _sha256_file(current_window_path) != original_campaign_sha
        or len(str(original.get("source_sha", ""))) != 40
        or len(str(original.get("input_sha256", ""))) != 64
        or len(str(original.get("physical_model_sha256", ""))) != 64
        or len(original_campaign_sha) != 64
    ):
        raise ValueError("V20 component resume identities differ from the new run or fixed window")

    original_manifest_path = original_run / "run_manifest.json"
    original_summary_path = original_run / "run_summary.json"
    original_input_path = original_run / "input_original.dat"
    original_source_path = original_run / "source_sha.txt"
    original_physical_path = original_run / "physical_model_sha256.txt"
    service_record_path = _repo_path(root, original.get("service_record_path"), "service record")
    geometry_path = _repo_path(root, artifacts.get("geometry_inventory_path"), "geometry inventory")
    mesh_xdmf_path = _repo_path(root, artifacts.get("mesh_xdmf_path"), "mesh XDMF")
    mesh_h5_path = _repo_path(root, artifacts.get("mesh_h5_path"), "mesh HDF5")
    c00_json_path = _repo_path(root, artifacts.get("c00_json_path"), "c00 JSON")
    c00_npz_path = _repo_path(root, artifacts.get("c00_npz_path"), "c00 NPZ")
    c00_receipt_path = _repo_path(root, artifacts.get("c00_readback_receipt_path"), "c00 readback receipt")
    expected_files = (
        (original_manifest_path, "original_run_manifest_sha256"),
        (original_summary_path, "original_run_summary_sha256"),
        (original_input_path, "original_input_copy_sha256"),
        (original_source_path, "original_source_sha_file_sha256"),
        (original_physical_path, "original_physical_sha_file_sha256"),
        (service_record_path, "original_service_record_sha256"),
        (geometry_path, "geometry_inventory_sha256"),
        (mesh_xdmf_path, "mesh_xdmf_sha256"),
        (mesh_h5_path, "mesh_h5_sha256"),
        (c00_json_path, "c00_json_sha256"),
        (c00_npz_path, "c00_npz_sha256"),
        (c00_receipt_path, "c00_readback_receipt_sha256"),
    )
    for path, key in expected_files:
        expected_hash = artifacts.get(key)
        if not isinstance(expected_hash, str) or not path.is_file() or _sha256_file(path) != expected_hash:
            raise ValueError(f"V20 component resume artifact hash differs: {key}")

    old_manifest = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    old_summary = json.loads(original_summary_path.read_text(encoding="utf-8"))
    old_service = json.loads(service_record_path.read_text(encoding="utf-8"))
    recorded_input_path = _repo_path(root, old_manifest.get("input_path"), "original input")
    service_run_directory = _repo_path(
        root, old_service.get("run_directory"), "service run directory"
    )
    service_manifest_path = _repo_path(
        root, old_service.get("run_manifest_path"), "service run manifest"
    )
    service_input_path = _repo_path(root, old_service.get("input_path"), "service input")
    old_campaign = old_manifest.get("task40_v20_campaign", {})
    summary_campaign = old_summary.get("task40_v20_campaign", {})
    if (
        old_manifest.get("run_id") != original.get("run_id")
        or old_summary.get("run_id") != original.get("run_id")
        or old_manifest.get("run_id") != _V20_TARGET_RUN_ID
        or old_manifest.get("source_sha") != original.get("source_sha")
        or old_manifest.get("input_sha256") != original.get("input_sha256")
        or old_manifest.get("physical_model_sha256") != original.get("physical_model_sha256")
        or _sha256_file(original_input_path) != original.get("input_sha256")
        or _sha256_file(recorded_input_path) != original.get("input_sha256")
        or _sha256_file(continuation_input_path) != preflight.get("input_sha256")
        or original_input_path.read_bytes() != recorded_input_path.read_bytes()
        or service_run_directory != original_run
        or service_manifest_path != original_manifest_path
        or service_input_path != recorded_input_path
        or original_source_path.read_text(encoding="utf-8").strip() != original.get("source_sha")
        or original_physical_path.read_text(encoding="utf-8").strip()
        != original.get("physical_model_sha256")
        or _sha256_file(original_source_path) != artifacts.get("original_source_sha_file_sha256")
        or _sha256_file(original_physical_path)
        != artifacts.get("original_physical_sha_file_sha256")
        or old_summary.get("result_classification") != "WORKER_FAILED"
        or old_summary.get("exit_status") != 4
        or old_service.get("source_sha") != original.get("source_sha")
        or old_service.get("input_sha256") != original.get("input_sha256")
        or old_service.get("physical_model_sha256") != original.get("physical_model_sha256")
        or old_service.get("campaign_window_sha256") != original_campaign_sha
        or old_campaign.get("window_sha256") != original_campaign_sha
        or summary_campaign.get("window_sha256") != original_campaign_sha
    ):
        raise ValueError("V20 original failed run/service identities do not match the resume manifest")
    _validate_component_resume_input_identity(
        recorded_input_path,
        continuation_input_path,
        resume_manifest_path=manifest_relative,
        resume_manifest_sha256=manifest_sha256,
    )
    if (original_run / "v20_local_port_components.json").exists() or (
        original_run / "v20_partial_result.json"
    ).exists():
        raise ValueError("V20 original attempt already has a continuation footer; refusing reuse")

    geometry_facts = json.loads(geometry_path.read_text(encoding="utf-8"))
    classes = geometry_facts.get("cell_classes")
    if (
        geometry_facts.get("schema") != "task40extra.review_v20_original_geometry_inventory.v1"
        or geometry_facts.get("status") != "PASS"
        or geometry_facts.get("mesh_id") != "TARGET_ORIGINAL_NY8"
        or not isinstance(classes, list)
        or len(classes) != int(geometry_facts.get("cell_class_count", -1))
        or [item.get("class_id") for item in classes]
        != [f"c{index:02d}" for index in range(len(classes))]
    ):
        raise ValueError("V20 saved geometry inventory is incomplete or has an unexpected identity")
    if not all(
        geometry_facts.get("periodic_face_inventory", {}).get(key) is True
        for key in (
            "x_periodic_coordinate_pairing_pass",
            "y_periodic_coordinate_pairing_pass",
            "top_bottom_port_coordinate_pairing_pass",
        )
    ):
        raise ValueError("V20 saved geometry inventory periodic/port pairing gates are incomplete")

    from mpi4py import MPI
    from dolfinx.io import XDMFFile
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.task40_v20_local_components import verify_v20_saved_c00_packet

    cfg = simulation_config_3d_from_normalized(resolved)
    with XDMFFile(MPI.COMM_SELF, str(mesh_xdmf_path), "r") as xdmf:
        msh = xdmf.read_mesh(name=cfg.case_name)
    axis_coordinates = tuple(
        np.unique(np.asarray(msh.geometry.x[:, axis], dtype=np.float64))
        for axis in range(3)
    )
    axis_hashes = [
        hashlib.sha256(np.ascontiguousarray(axis).tobytes()).hexdigest()
        for axis in axis_coordinates
    ]
    actual_axes = [int(len(axis) - 1) for axis in axis_coordinates]
    if (
        actual_axes != geometry_facts.get("actual_axes")
        or [int(len(axis)) for axis in axis_coordinates]
        != geometry_facts.get("vertex_axis_coordinate_counts")
        or axis_hashes != geometry_facts.get("axis_coordinate_sha256")
        or int(msh.topology.index_map(3).size_local)
        != int(geometry_facts.get("actual_cell_count", -1))
    ):
        raise ValueError("V20 restored XDMF axes/cell count differ from the saved geometry inventory")

    c00_row, c00_validation = verify_v20_saved_c00_packet(
        original_run,
        c00_receipt_path,
        expected_json_sha256=str(artifacts["c00_json_sha256"]),
        expected_npz_sha256=str(artifacts["c00_npz_sha256"]),
        expected_readback_receipt_sha256=str(artifacts["c00_readback_receipt_sha256"]),
    )
    c00_receipt_facts = json.loads(c00_receipt_path.read_text(encoding="utf-8"))
    if (
        c00_receipt_facts.get("run_directory") != str(original_run)
        or c00_receipt_facts.get("current_source_head") != original.get("source_sha")
    ):
        raise ValueError("V20 c00 readback receipt does not identify the original run/source")
    from src.solvers.task40_v20_local_components import _validate_reused_local_prefix

    completed_local_rows = [c00_row]
    prefix_validation = None
    if completed_prefix_spec is not None:
        mode_identity = preflight.get("target_mode_inventory")
        if not isinstance(mode_identity, Mapping):
            raise ValueError("V20 completed prefix requires the frozen target mode inventory")
        completed_local_rows, prefix_validation = _load_completed_local_prefix(
            root,
            completed_prefix_spec,
            classes,
            c00_row,
            base_run_directory=original_run,
            base_geometry_sha256=str(artifacts["geometry_inventory_sha256"]),
            original_campaign_sha256=original_campaign_sha,
            expected_campaign_window_path=current_window_path,
            expected_physical_model_sha256=str(preflight["physical_model_sha256"]),
            mode_manifest_sha256=str(mode_identity["mode_manifest_sha256"]),
            ordered_mode_key_sha256=str(mode_identity["ordered_mode_key_sha256"]),
        )
    _validate_reused_local_prefix(classes, completed_local_rows)
    receipt = {
        "schema": (
            "task40extra.review_v20_target_component_resume_receipt.v2"
            if prefix_validation is not None
            else "task40extra.review_v20_target_component_resume_receipt.v1"
        ),
        "status": "BOUND_AND_VERIFIED",
        "resume_manifest_path": str(manifest_path.relative_to(root)),
        "resume_manifest_sha256": manifest_sha256,
        "original_run": dict(original),
        "new_run": {
            "run_id": resolved.get("run_id"),
            "source_sha": source_sha,
            "input_sha256": preflight.get("input_sha256"),
            "physical_model_sha256": preflight.get("physical_model_sha256"),
            "campaign_window_sha256": current_campaign.get("window_sha256"),
        },
        "artifact_hashes": dict(artifacts),
        "restored_axis_coordinate_sha256": axis_hashes,
        "c00_independent_readback": c00_validation,
        "completed_prefix_independent_readback": prefix_validation,
        "completed_local_class_ids": [row["class_id"] for row in completed_local_rows],
        "original_attempt_preserved": True,
        "global_fe_mpc_q_csr_factor_or_pde_created": False,
    }
    output_geometry = output_directory / "v20_geometry_inventory.json"
    if output_geometry.exists():
        raise FileExistsError("V20 continuation output already contains a geometry inventory")
    output_geometry.write_bytes(geometry_path.read_bytes())
    return geometry_facts, cfg, classes, axis_coordinates, completed_local_rows, receipt


def _resource_snapshot() -> dict[str, Any]:
    available = None
    total = None
    swap_total = None
    swap_free = None
    try:
        facts = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, raw = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                facts[key] = int(raw.split()[0]) * 1024
        total = facts.get("MemTotal")
        available = facts.get("MemAvailable")
        swap_total = facts.get("SwapTotal")
        swap_free = facts.get("SwapFree")
    except (OSError, ValueError):
        pass
    try:
        from benchmarks.task034_wsl_resources import cgroup_snapshot

        cgroup = cgroup_snapshot("self")
        cgroup["sample_scope"] = (
            "current process cgroup; task-specific only when dedicated_job_cgroup is true"
        )
    except (ImportError, OSError, ValueError) as error:
        cgroup = {
            "path": None,
            "readable": False,
            "dedicated_job_cgroup": False,
            "memory_current_bytes": None,
            "memory_peak_bytes": None,
            "memory_limit_bytes": None,
            "swap_current_bytes": None,
            "sample_scope": "UNKNOWN: current process cgroup provider failed",
            "error": {"type": type(error).__name__, "message": str(error)},
        }
    return {
        "host_memory_total_bytes": total,
        "host_memory_available_bytes": available,
        "host_swap_total_bytes": swap_total,
        "host_swap_free_bytes": swap_free,
        "process_max_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        "current_process_cgroup": cgroup,
        "scope": (
            "instant host sample plus current-process cgroup sample and process historical max RSS; "
            "cgroup values are task-specific only for a dedicated job cgroup and are not a "
            "simultaneous process-tree peak"
        ),
    }


def _exact_case(resolved: Mapping[str, Any]) -> tuple[str, str]:
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_V15_REFERENCE_PC_STRATEGY,
        TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
    )
    from src.solvers.task40_v20_registry import task40_v20_case

    solver = resolved.get("solver", {})
    execution = resolved.get("execution", {})
    profile = solver.get("preconditioner")
    run_id = resolved.get("run_id")
    v30_requested = (
        "task40_v30_q_csr_binding" in execution
        or "task40_v30_factor_bank_config" in execution
    )
    v31_requested = (
        "task40_v31_q_csr_binding" in execution
        or "task40_v31_factor_bank_config" in execution
    )
    if v30_requested and v31_requested:
        raise ValueError("V20 stage adapter cannot mix V30 and V31 execution metadata")
    expected_factor_lifecycle = (
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
        if v30_requested or v31_requested
        else TASK40_V19_FACTOR_LIFECYCLE_STRATEGY
    )
    try:
        case = task40_v20_case(profile=str(profile))
    except ValueError:
        case = None
    if (
        case is None
        or run_id != case.run_id
        or resolved.get("comparison_group") != TASK40_COMPARISON_GROUP
        or resolved.get("method", {}).get("kind") != "full3d_iterative"
        or solver.get("task40_reference_pc_strategy") != TASK40_V15_REFERENCE_PC_STRATEGY
        or solver.get("task40_q_assembly_strategy") != TASK40_Q_ASSEMBLY_ROW_TILE_V17
        or solver.get("task40_factor_lifecycle_strategy") != expected_factor_lifecycle
        or (
            v30_requested
            and (
                case.mesh_id != "TARGET_ORIGINAL_NY8"
                or execution.get("task40_execution_stop_stage") != "full"
                or not execution.get("task40_target_heavy_authorized")
                or not isinstance(execution.get("task40_v30_q_csr_binding"), Mapping)
                or not isinstance(execution.get("task40_v30_factor_bank_config"), Mapping)
            )
        )
        or (
            v31_requested
            and (
                case.mesh_id != "TARGET_ORIGINAL_NY8"
                or execution.get("task40_execution_stop_stage") != "full"
                or not execution.get("task40_target_heavy_authorized")
                or not isinstance(execution.get("task40_v31_q_csr_binding"), Mapping)
                or not isinstance(execution.get("task40_v31_factor_bank_config"), Mapping)
            )
        )
        or execution.get("task40_execution_stop_stage") not in case.allowed_stop_stages
        or resolved.get("derived", {}).get("physical_intermediate_profile", {}).get(
            "identity"
        )
        != profile
    ):
        raise ValueError("Task40 V20 stage adapter requires an exact reviewed case/profile route")
    return str(profile), str(case.mesh_id)


def _preflight(
    resolved: Mapping[str, Any], *, source_sha: str, profile: str, mesh_id: str
) -> tuple[dict[str, Any], tuple[Any, ...] | None, tuple[Mapping[str, Any], ...] | None]:
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.io.physical_intermediate_profile import profile_facts
    from src.solvers.task40_v20_mode_inventory import load_v20_target_mode_inventory

    provenance = resolved.get("provenance", {})
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(char not in "0123456789abcdef" for char in source_sha.lower())
        or not isinstance(provenance, Mapping)
        or len(str(provenance.get("input_sha256", ""))) != 64
        or len(str(provenance.get("physical_model_sha256", ""))) != 64
    ):
        raise ValueError("V20 preflight requires complete source/input/physical-model identities")
    if os.environ.get("TASK40_V30_STRICT_EXECUTION") == "1":
        from src.runners.task40_v30_contract import (
            qualified_activation_identity,
            require_authorized_contract,
        )

        activation_identity = qualified_activation_identity(os.environ)
        require_authorized_contract(
            os.environ.get("TASK40_V30_CONTRACT_PATH", ""),
            expected_sha256=os.environ.get("TASK40_V30_CONTRACT_SHA256"),
            current_root=Path(__file__).resolve().parents[2],
        )
        expected_profile = "native_linux"
    elif os.environ.get("TASK40_V31_STRICT_EXECUTION") == "1":
        from src.runners.task40_v31_contract import (
            qualified_activation_identity,
            require_v31_execution_contract,
        )

        activation_identity = qualified_activation_identity(os.environ)
        require_v31_execution_contract(
            os.environ.get("TASK40_V31_CONTRACT_PATH", ""),
            expected_sha256=os.environ.get("TASK40_V31_CONTRACT_SHA256"),
            current_root=Path(__file__).resolve().parents[2],
        )
        expected_profile = "native_linux"
    elif os.environ.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1":
        from src.runners.task40_v29_contract import qualified_activation_identity

        activation_identity = qualified_activation_identity(os.environ)
        expected_profile = "native_linux"
    else:
        activation_identity = os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION")
        expected_profile = "local_wsl2_authorized"
    if (
        activation_identity is None
        or (expected_profile == "local_wsl2_authorized" and activation_identity != "1")
        or MPI.COMM_WORLD.size != 1
        or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
        or np.dtype(PETSc.IntType) != np.dtype(np.int32)
    ):
        raise RuntimeError(
            f"V20 preflight requires qualified {expected_profile} MPI1 complex128/int32 ABI"
        )
    inventory = profile_facts(profile)
    if (
        inventory.get("run_id") != resolved.get("run_id")
        or inventory.get("gates", {}).get("task40_mesh_id") != mesh_id
        or inventory.get("periodic_inventory", {}).get("global_cell_axes")
        != resolved.get("discretization", {}).get("mesh_axis_cell_counts")
    ):
        raise ValueError("V20 profile inventory differs from the resolved target geometry/case")
    mode_facts = None
    modes = rows = None
    if mesh_id == "TARGET_ORIGINAL_NY8":
        modes, rows, _mode_sha, mode_facts = load_v20_target_mode_inventory(resolved)
    environment = {
        "qualified_activation": activation_identity,
        "runtime_profile": expected_profile,
        "python_executable": sys.executable,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "mpi_library": MPI.Get_library_version().splitlines()[0],
        "mpi_size": MPI.COMM_WORLD.size,
    }
    return (
        {
            "schema": "task40extra.review_v20_stage_preflight.v1",
            "source_sha": source_sha,
            "input_path": provenance.get("source_path"),
            "input_sha256": provenance.get("input_sha256"),
            "physical_model_sha256": provenance.get("physical_model_sha256"),
            "case_profile": profile,
            "run_id": resolved.get("run_id"),
            "mesh_id": mesh_id,
            "solver_stage": resolved.get("solver", {}).get("stage"),
            "stop_stage": resolved.get("execution", {}).get(
                "task40_execution_stop_stage"
            ),
            "abi": environment,
            "resources": _resource_snapshot(),
            "profile_inventory": inventory,
            "target_mode_inventory": mode_facts,
            "passed": True,
        },
        modes,
        rows,
    )


def _controlled_stop(
    output_directory: Path,
    *,
    preflight: Mapping[str, Any],
    requested_stage: str,
    completed_stages: list[str],
    reason: str,
    outcome: str | None = None,
    attempted_stages: list[str] | None = None,
    additional: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = {
        "schema": (
            "task40extra.review_v20_partial_result.v2"
            if outcome is not None
            else "task40extra.review_v20_partial_result.v1"
        ),
        "status": "controlled_stop",
        "classification": "CONTROLLED_STOP",
        "run_id": preflight.get("run_id"),
        "profile": preflight.get("case_profile"),
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": requested_stage,
        "completed_stages": completed_stages,
        "official_result": False,
        "not_run": [
            "target global p6 FE/MPC",
            "all-q CSR and symbolic/numeric factors",
            "target PDE/full field",
            "R/T/A precision qualification",
        ],
        "reason": reason,
        "outer_budget": "not charged by this adapter; the launcher/watchdog owns campaign accounting",
        **dict(additional or {}),
    }
    if outcome is not None:
        receipt["outcome"] = outcome
        receipt["attempted_stages"] = list(
            completed_stages if attempted_stages is None else attempted_stages
        )
        receipt["q_coverage"] = {
            "status": "NOT_RUN",
            "reason": "the stop occurred before target q assembly",
        }
        receipt["cleanup"] = {
            "status": "NOT_RUN",
            "reason": "no heavy worker owner was created by this stop path",
        }
        receipt["artifact_hashes"] = {
            name: {"path": name, "sha256": _sha256_file(output_directory / name)}
            for name in ("v20_stage_preflight.json", "v20_geometry_inventory.json", "v20_local_port_components.json")
            if (output_directory / name).is_file()
        }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": True,
        "errors": [],
        "official_result": False,
        "status": "controlled_stop",
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def _worker_stage_receipt(
    output_directory: Path,
    *,
    preflight: Mapping[str, Any],
    requested_stage: str,
    completed_prefix: list[str],
    target_heavy_authorized: bool,
    worker_result: Mapping[str, Any] | None,
    failure: BaseException | None = None,
) -> dict[str, Any]:
    """Record what the worker actually attempted and completed, never a full result."""

    summary = worker_result.get("summary", {}) if worker_result is not None else {}
    if not isinstance(summary, Mapping):
        summary = {}
    stage_result = summary.get("v20_stage_result")
    if not isinstance(stage_result, Mapping):
        stage_result = None
    worker_classification = summary.get("result_classification")
    stage_completed = bool(
        failure is None
        and worker_result is not None
        and worker_result.get("passed") is True
        and stage_result is not None
        and stage_result.get("completed_stage") == requested_stage
    )
    if stage_completed:
        outcome = "STAGE_COMPLETED"
        completed_stages = [*completed_prefix, requested_stage]
    elif failure is None and worker_classification == "RESOURCE_CONTROLLED_STOP":
        outcome = "RESOURCE_CONTROLLED_STOP"
        completed_stages = list(completed_prefix)
    else:
        outcome = "STAGE_FAILED"
        completed_stages = list(completed_prefix)

    worker_error = (
        {"type": type(failure).__name__, "message": str(failure)}
        if failure is not None
        else summary.get("error")
    )
    artifact_hashes: dict[str, dict[str, str]] = {}
    for name in (
        "v20_stage_preflight.json",
        "v20_geometry_inventory.json",
        "v20_local_port_components.json",
        "task40_v10_p6_candidate_summary.json",
    ):
        path = output_directory / name
        if path.is_file():
            artifact_hashes[name] = {
                "path": name,
                "sha256": _sha256_file(path),
            }

    q_csr_inventory = stage_result.get("q_csr_inventory") if stage_result else None
    if isinstance(q_csr_inventory, Mapping):
        q_coverage = {
            "status": "KNOWN",
            "all_q_symbolic_covered": stage_result.get("all_q_symbolic_covered"),
            "q_count": len(q_csr_inventory),
            "q_csr_inventory": dict(q_csr_inventory),
            "source": "worker v20_stage_result; hash-bound by candidate summary artifact",
        }
    elif outcome == "AUTH_NOT_GRANTED":
        q_coverage = {
            "status": "NOT_RUN",
            "reason": "authorization gate stopped before target q assembly",
        }
    else:
        q_coverage = {
            "status": "UNKNOWN",
            "reason": "worker result did not expose completed-q inventory and hashes",
        }
    cleanup = summary.get("cleanup")
    if isinstance(cleanup, Mapping):
        cleanup_facts = {
            key: cleanup.get(key)
            for key in (
                "native_owners_released",
                "process_descendants_cleared",
                "temporary_stage_objects_released",
            )
        }
        cleanup_facts["status"] = (
            "PASS"
            if all(cleanup_facts[key] is True for key in cleanup_facts)
            else "UNKNOWN"
        )
    else:
        cleanup_facts = {
            "status": "UNKNOWN",
            "reason": "worker result did not expose a unified owner/descendant cleanup receipt",
        }

    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": {
            "AUTH_NOT_GRANTED": "controlled_stop",
            "RESOURCE_CONTROLLED_STOP": "controlled_stop",
            "STAGE_COMPLETED": "stage_completed",
            "STAGE_FAILED": "failed",
        }[outcome],
        "outcome": outcome,
        "classification": worker_classification or outcome,
        "run_id": preflight.get("run_id"),
        "profile": preflight.get("case_profile"),
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": requested_stage,
        "attempted_stages": [*completed_prefix, requested_stage],
        "completed_stages": completed_stages,
        "failed_stage": requested_stage if outcome == "STAGE_FAILED" else None,
        "target_heavy_authorized": target_heavy_authorized,
        "worker_status": worker_result.get("status") if worker_result is not None else None,
        "worker_result_classification": worker_classification,
        "stage_result": dict(stage_result) if stage_result is not None else None,
        "q_coverage": q_coverage,
        "cleanup": cleanup_facts,
        "resource_gate": worker_error if outcome == "RESOURCE_CONTROLLED_STOP" else None,
        "error": worker_error if outcome == "STAGE_FAILED" else None,
        "artifact_hashes": artifact_hashes,
        "not_run": [name for name in V20_STAGE_NAMES if name not in completed_stages],
        "official_result": False,
        "full_field_release_allowed": False,
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return receipt


def _run_v25_selected_q0_stage(
    resolved_payload: Mapping[str, Any],
    output_directory: Path,
    *,
    source_sha: str,
    profile: str,
    preflight: Mapping[str, Any],
    modes: tuple[Any, ...] | None,
    mode_rows: tuple[Mapping[str, Any], ...] | None,
    stop_stage: str,
) -> dict[str, Any]:
    """Run one registered V25 selected-reference-q0 build-only operation."""
    import shutil

    from src.solvers.task40_v22_operator_probe import (
        _ProbeResourceBlocked,
        _resource_admission,
        _v23_actual_axis_values,
    )
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.task40_v25_selected_q0 import run_task40_v25_selected_q0_consumer

    if modes is None or mode_rows is None:
        raise RuntimeError("V25 q0 route requires the frozen complete preflight mode inventory")
    identity = preflight.get("target_mode_inventory")
    if not isinstance(identity, Mapping):
        raise RuntimeError("V25 q0 route has no frozen mode-manifest/key identity")
    mode_sha = identity.get("mode_manifest_sha256")
    key_sha = identity.get("ordered_mode_key_sha256")
    if not isinstance(mode_sha, str) or len(mode_sha) != 64 or not isinstance(key_sha, str) or len(key_sha) != 64:
        raise RuntimeError("V25 q0 route mode identity is incomplete")

    resource_gates: list[dict[str, Any]] = []
    disk_reserve_bytes = 1024**3

    def allocation_gate(stage: str, facts: Mapping[str, Any]) -> dict[str, Any]:
        requested = int(facts.get("additional_payload_bytes", 0))
        requested += int(facts.get("matrix_payload_bytes", 0))
        requested += int(facts.get("workspace_bytes", 0))
        requested += int(facts.get("future_co_resident_reserve_bytes", 0))
        memory = _resource_admission(
            stage,
            requested,
            resource_sample=_resource_snapshot,
            require_task_cgroup=True,
        )
        disk_required = int(facts.get("disk_payload_bytes", 0))
        disk_free = int(shutil.disk_usage(output_directory).free)
        disk_passed = disk_free >= disk_required + disk_reserve_bytes
        record = {
            **memory,
            "disk_payload_bytes": disk_required,
            "disk_free_bytes": disk_free,
            "disk_reserve_bytes": disk_reserve_bytes,
            "disk_gate_passed": disk_passed,
            "request_facts": dict(facts),
        }
        resource_gates.append(record)
        if not disk_passed:
            blocker = {
                "stage": stage,
                "additional_object_upper_bound_bytes": requested,
                "disk_payload_bytes": disk_required,
                "disk_free_bytes": disk_free,
                "disk_reserve_bytes": disk_reserve_bytes,
                "disk_gate_passed": False,
                "passed": False,
            }
            raise _ProbeResourceBlocked(stage, blocker)
        return record

    def resident_csr_admission(stage: str, payload_bytes: int) -> Mapping[str, Any]:
        return allocation_gate(stage, {"additional_payload_bytes": int(payload_bytes)})

    operation_path = output_directory / "v25_selected_q0_consumer.json"
    try:
        operation = run_task40_v25_selected_q0_consumer(
            simulation_config_3d_from_normalized(resolved_payload),
            _v23_actual_axis_values(resolved_payload),
            output_directory=output_directory,
            allocation_gate=allocation_gate,
            resident_csr_admission=resident_csr_admission,
            frozen_modes=modes,
            frozen_mode_rows=mode_rows,
            frozen_mode_manifest_sha256=mode_sha,
            expected_ordered_mode_key_sha256=key_sha,
            physical_model_sha256=str(preflight.get("physical_model_sha256")),
            build_csr=stop_stage != "selected_reference_q_consumer",
        )
    except _ProbeResourceBlocked as error:
        resource_gates.append(dict(error.facts))
        operation = {
            "schema": "task40extra.review_v25_selected_reference_q0_consumer.v1",
            "status": "RESOURCE_CONTROLLED_STOP",
            "classification": "PRE_FE_OR_PHASE_RESOURCE_GATE_BLOCKED",
            "selected_q": 0,
            "paired_q": 4,
            "preflight_mode_manifest_sha256": mode_sha,
            "ordered_mode_key_sha256": key_sha,
            "failed_stage": error.stage,
            "resource_blocker": dict(error.facts),
            "official_result": False,
            "factor_or_solve_built": False,
        }
        _write_json(output_directory / "v25_selected_q0_consumer.json", operation)
    except Exception as error:
        operation = {
            "schema": "task40extra.review_v25_selected_reference_q0_consumer.v1",
            "status": "FAILED_SELECTED_Q0_GATES",
            "classification": "SELECTED_REFERENCE_Q0_OPERATION_FAILED",
            "selected_q": 0,
            "paired_q": 4,
            "preflight_mode_manifest_sha256": mode_sha,
            "ordered_mode_key_sha256": key_sha,
            "failure_type": type(error).__name__,
            "failure_message": str(error),
            "official_result": False,
            "factor_or_solve_built": False,
        }
        if not operation_path.exists():
            _write_json(operation_path, operation)

    op_status = str(operation.get("status", "FAILED_SELECTED_Q0_GATES"))
    is_pass = op_status in {
        "PASS_COMPLETE_Q0_STREAM",
        "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT",
        "PASS_COMPLETE_Q0_CSR",
    }
    controlled = op_status == "RESOURCE_CONTROLLED_STOP"
    csr_built = op_status == "PASS_COMPLETE_Q0_CSR"
    completed = ["preflight", stop_stage] if is_pass else ["preflight"]
    if is_pass:
        outcome, status = "STAGE_COMPLETED", "stage_completed"
        classification = (
            "SELECTED_REFERENCE_Q0_COMPLETE_DISK_BACKED_CSR"
            if csr_built else "SELECTED_REFERENCE_Q0_COMPLETE_STREAM_CSR_NOT_BUILT"
            if op_status == "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT"
            else "SELECTED_REFERENCE_Q0_COMPLETE_STREAM"
        )
    elif controlled:
        outcome, status = "RESOURCE_CONTROLLED_STOP", "controlled_stop"
        classification = "SELECTED_REFERENCE_Q0_RESOURCE_CONTROLLED_STOP"
    else:
        outcome, status = "STAGE_FAILED", "failed"
        classification = str(operation.get("classification", "SELECTED_REFERENCE_Q0_FAILED"))

    artifact_hashes: dict[str, dict[str, str]] = {}
    artifact_hashes["v20_stage_preflight.json"] = {
        "path": "v20_stage_preflight.json",
        "sha256": _sha256_file(output_directory / "v20_stage_preflight.json"),
    }
    artifact_hashes["v25_selected_q0_consumer.json"] = {
        "path": "v25_selected_q0_consumer.json",
        "sha256": _sha256_file(operation_path),
    }
    saved = operation.get("saved_artifacts", {})
    if isinstance(saved, Mapping):
        for key, value in saved.items():
            if not isinstance(value, Mapping):
                continue
            relative = Path(str(value.get("path", "")))
            target = (output_directory / relative).resolve()
            if target.is_relative_to(output_directory) and target.is_file():
                artifact_hashes[f"v25:{key}"] = {
                    "path": str(relative),
                    "sha256": _sha256_file(target),
                }

    complete_stream = operation.get("complete_stream", {})
    complete_stream = complete_stream if isinstance(complete_stream, Mapping) else {}
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": status,
        "outcome": outcome,
        "classification": classification,
        "run_id": preflight.get("run_id"),
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": stop_stage,
        "attempted_stages": ["preflight", stop_stage],
        "completed_stages": completed,
        "failed_stage": operation.get("failed_stage") if not is_pass else None,
        "stage_result": {
            "completed_stage": stop_stage if is_pass else None,
            "probe_status": op_status,
        },
        "selected_reference_q0_consumer": {
            "operation_path": "v25_selected_q0_consumer.json",
            "operation_sha256": artifact_hashes["v25_selected_q0_consumer.json"]["sha256"],
            "operation_status": op_status,
            "operation": dict(operation),
            "resource_gates": resource_gates,
        },
        "q_coverage": {
            "status": "KNOWN",
            "expected_q_count": 8,
            "built_q_count": 1 if csr_built else 0,
            "full_q_matrix_coverage": "1/8" if csr_built else "0/8",
            "complete_streamed_consumer_count": 1 if is_pass else 0,
            "selected_q": 0,
            "paired_action_q": 4,
            "csr_status": "BUILT" if csr_built else "NOT_BUILT",
            "factor_count": 0,
            "ksp_created": False,
            "pde_solved": False,
            "reason": "One q0 CSR is a build-only artifact; q4 is paired action-only. No factor, KSP, PDE, or official R/T/A is built.",
            "consumer_manifest": complete_stream.get("schema"),
        },
        "resource_gate": operation.get("resource_blocker") if controlled else None,
        "cleanup": {"status": "OPERATION_RETURNED", "owner_cleanup": "operation finally block"},
        "artifact_hashes": artifact_hashes,
        "official_result": False,
        "not_run": ["all other q CSR", "factor", "KSP", "PDE", "official R/T/A"],
        "full_field_release_allowed": False,
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": is_pass or controlled,
        "errors": [] if is_pass or controlled else [str(operation.get("failure_message", op_status))],
        "official_result": False,
        "status": status,
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def _run_v27_saved_q0_stage(
    resolved_payload: Mapping[str, Any],
    output_directory: Path,
    *,
    source_sha: str,
    profile: str,
    preflight: Mapping[str, Any],
    modes: tuple[Any, ...] | None,
    mode_rows: tuple[Mapping[str, Any], ...] | None,
    stop_stage: str,
    v28_continuation: bool = False,
    v29_strict_factor_only: bool = False,
) -> dict[str, Any]:
    """Build/read back only the frozen saved q0 CSR; no FE or native rebuild."""
    import gc
    import shutil
    import time
    import zipfile

    from scipy import sparse

    from src.solvers.task40_v22_operator_probe import (
        _ProbeResourceBlocked,
        _resource_admission,
    )
    from src.solvers.task40_v25_selected_q0 import (
        _advise_file_drop,
        _drop_mmap_pages,
        _file_sha256,
        _task_cgroup_memory_snapshot,
    )
    from src.solvers.task40_v27_saved_q0 import (
        SavedQ0ContributionAdapter,
        _sha256_file as _saved_q_sha256,
        build_saved_q0_csr_structure,
        create_v28_saved_q0_csr_continuation_manifest,
        fill_saved_q0_csr_values,
        open_saved_q0_csr_from_manifest,
        preflight_saved_q0_csr,
    )

    v29_contract = None
    v29_selector = None
    v29_resolve_path = None
    v29_contract_sha256 = None
    v29_selector_sha256 = None
    if v29_strict_factor_only:
        from src.runners.task40_v29_contract import (
            approved_path_resolver,
            require_authorized_contract,
            require_authorized_selector,
            require_strict_factor_only_status,
        )

        contract_path = Path(os.environ.get("TASK40_V29_CONTRACT_PATH", ""))
        strict_selector_path = Path(os.environ.get("TASK40_V29_SELECTOR_PATH", ""))
        v29_contract, v29_contract_sha256 = require_authorized_contract(
            contract_path,
            expected_sha256=os.environ.get("TASK40_V29_CONTRACT_SHA256"),
            current_root=Path(__file__).resolve().parents[2],
        )
        v29_selector, v29_selector_sha256 = require_authorized_selector(
            strict_selector_path,
            expected_sha256=os.environ.get("TASK40_V29_SELECTOR_SHA256"),
            contract_path=contract_path,
            contract_sha256=v29_contract_sha256,
            contract=v29_contract,
        )
        v29_resolve_path = approved_path_resolver(v29_contract)

    if stop_stage != "selected_reference_q_csr" or modes is None or mode_rows is None:
        raise RuntimeError("V27 route only accepts the registered q0 CSR stop with frozen mode inventory")
    selector_prefix = "TASK40_V28" if v28_continuation else "TASK40_V27"
    selector_path = Path(os.environ.get(f"{selector_prefix}_SELECTOR_PATH", "")).resolve()
    selector_sha = os.environ.get(f"{selector_prefix}_SELECTOR_SHA256", "")
    raw_operation = os.environ.get(f"{selector_prefix}_OPERATION", "")
    expected_operation = (
        "V28_EXISTING_MANIFEST_Q0_CONTINUATION"
        if v28_continuation
        else "V27_SAVED_ONLY_COMPLETE_Q0_CSR"
    )
    if (
        raw_operation != expected_operation
        or not selector_path.is_file()
        or len(selector_sha) != 64
        or _sha256_file(selector_path) != selector_sha
    ):
        raise RuntimeError("saved q0 route lacks its service-bound selector and operation identity")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    expected_selector_schema = (
        "task40extra.review_v28_q0_continuation_operation.v1"
        if v28_continuation
        else "task40extra.review_v27_saved_q0_operation.v1"
    )
    donor_import = selector.get("donor_import")
    producer_identity = (
        donor_import.get("producer_identity") if isinstance(donor_import, Mapping) else None
    )
    inventory = preflight.get("target_mode_inventory")
    if (
        selector.get("schema") != expected_selector_schema
        or selector.get("operation") != expected_operation
        or selector.get("stop_stage") != stop_stage
        or selector.get("model_profile") != profile
        or selector.get("input_sha256") != preflight.get("input_sha256")
        or not isinstance(donor_import, Mapping)
        or not isinstance(producer_identity, Mapping)
        or not isinstance(inventory, Mapping)
        or selector.get("campaign_window_sha256") is None
    ):
        raise RuntimeError("saved q0 selector or preflight omits its fixed donor/window/mode identity")
    if v28_continuation:
        pattern_manifest_path = Path(
            os.environ.get("TASK40_V28_PATTERN_MANIFEST_PATH", "")
        ).resolve()
        continuation_manifest_path = Path(
            os.environ.get("TASK40_V28_CONTINUATION_MANIFEST_PATH", "")
        ).resolve()
        if v29_strict_factor_only:
            strict_pattern = v29_resolve_path(v29_selector.get("pattern_manifest_path", ""))
            strict_manifest = v29_resolve_path(v29_selector.get("manifest_path", ""))
            strict_qualification = v29_resolve_path(v29_selector.get("qualification_path", ""))
            if (
                strict_pattern != pattern_manifest_path
                or strict_manifest != continuation_manifest_path
                or strict_qualification
                != Path(os.environ.get("TASK40_V29_QUALIFICATION_PATH", "")).resolve()
                or v29_selector.get("manifest_sha256")
                != os.environ.get("TASK40_V29_COMPLETE_MANIFEST_SHA256")
                or v29_selector.get("qualification_sha256")
                != os.environ.get("TASK40_V29_NATIVE_PASS_SHA256")
            ):
                raise RuntimeError("V29 worker strict selector path/hash binding differs from its service envelope")
            selector_pattern_path = v29_resolve_path(selector.get("pattern_manifest_path", ""))
            selector_continuation_path = v29_resolve_path(
                selector.get("continuation_manifest_path", "")
            )
        else:
            selector_pattern_path = Path(
                str(selector.get("pattern_manifest_path", ""))
            ).resolve()
            selector_continuation_path = Path(
                str(selector.get("continuation_manifest_path", ""))
            ).resolve()
        if (
            selector_pattern_path != pattern_manifest_path
            or selector.get("pattern_manifest_sha256")
            != os.environ.get("TASK40_V28_PATTERN_MANIFEST_SHA256")
            or selector_continuation_path != continuation_manifest_path
            or selector.get("campaign_window_sha256")
            != os.environ.get("TASK40_V28_CAMPAIGN_WINDOW_SHA256")
        ):
            raise RuntimeError("V28 worker pattern, continuation, or campaign binding changed")
    mode_sha = inventory.get("mode_manifest_sha256")
    key_sha = inventory.get("ordered_mode_key_sha256")
    if not isinstance(mode_sha, str) or len(mode_sha) != 64 or not isinstance(key_sha, str) or len(key_sha) != 64:
        raise RuntimeError("saved q0 route has no complete frozen mode-manifest/key identity")

    repo_root = Path(__file__).resolve().parents[2]
    producer_root = Path(os.environ.get(f"{selector_prefix}_PRODUCER_ROOT", "")).resolve()
    expected_producer_root = (
        repo_root / str(producer_identity.get("producer_run_directory", ""))
    ).resolve()
    if not producer_root.is_dir() or producer_root != expected_producer_root:
        raise RuntimeError("saved q0 producer root differs from its service-bound read-only donor identity")
    replay_root = (
        repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl/saved_replay"
    ).resolve()
    native_root = (
        repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl/native_consumer"
    ).resolve()
    disk_reserve_bytes = 1024**3
    resource_admission_for_gate = _resource_admission
    if v29_strict_factor_only:
        def resource_admission_for_gate(stage, additional_bytes, **kwargs):
            resources = v29_contract["execution"]["resources"]
            return _resource_admission(
                stage,
                additional_bytes,
                explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
                host_reserve_bytes=int(resources["host_reserve_bytes"]),
                task_cgroup_reserve_bytes=0,
                **kwargs,
            )

    allocation_gate, resource_gates_by_stage, resource_gate_records, resource_gate_timing = (
        _make_saved_q0_allocation_gate(
            output_directory=output_directory,
            disk_reserve_bytes=disk_reserve_bytes,
            resource_admission=resource_admission_for_gate,
            resource_sample=_resource_snapshot,
            cgroup_snapshot=_task_cgroup_memory_snapshot,
            blocked_exception=_ProbeResourceBlocked,
            disk_usage=shutil.disk_usage,
        )
    )
    if v29_strict_factor_only:
        from src.runners.task40_v29_contract import (
            V29ContractError,
            validate_live_resource_contract,
        )

        base_allocation_gate = allocation_gate

        def allocation_gate(stage: str, facts: Mapping[str, Any]) -> dict[str, Any]:
            result = base_allocation_gate(stage, facts)
            cgroup = result.get("current_process_cgroup", {})
            cgroup = cgroup if isinstance(cgroup, Mapping) else {}
            requested = sum(
                int(facts.get(name, 0))
                for name in (
                    "additional_payload_bytes",
                    "matrix_payload_bytes",
                    "workspace_bytes",
                    "future_co_resident_reserve_bytes",
                )
            )
            try:
                if cgroup.get("dedicated_job_cgroup") is not True or cgroup.get("swap_current_bytes") != 0:
                    raise V29ContractError("V29 requires a dedicated zero-swap task cgroup")
                validate_live_resource_contract(
                    v29_contract,
                    cgroup_limit_bytes=int(cgroup["memory_limit_bytes"]),
                    cgroup_current_bytes=int(cgroup["memory_current_bytes"]),
                    host_effective_available_bytes=int(result["host_effective_available_bytes"]),
                    additional_request_bytes=requested,
                )
            except (V29ContractError, KeyError, TypeError, ValueError) as error:
                raise _ProbeResourceBlocked(
                    stage,
                    {
                        "stage": stage,
                        "v29_contract_resource_gate": False,
                        "task_memory_max_bytes": v29_contract["execution"]["resources"]["task_memory_max_bytes"],
                        "host_reserve_bytes": v29_contract["execution"]["resources"]["host_reserve_bytes"],
                        "requested_additional_bytes": requested,
                        "cgroup_snapshot": dict(cgroup),
                        "host_effective_available_bytes": result.get("host_effective_available_bytes"),
                        "reason": str(error),
                        "passed": False,
                    },
                ) from error
            result["v29_contract_resource_gate"] = {
                "passed": True,
                "task_memory_max_bytes": v29_contract["execution"]["resources"]["task_memory_max_bytes"],
                "host_reserve_bytes": v29_contract["execution"]["resources"]["host_reserve_bytes"],
                "requested_additional_bytes": requested,
                "cgroup_limit_bytes": cgroup["memory_limit_bytes"],
                "cgroup_current_bytes": cgroup["memory_current_bytes"],
                "host_effective_available_bytes": result["host_effective_available_bytes"],
            }
            return result

    current_identity = {
        "source_sha": source_sha,
        "run_id": preflight.get("run_id"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "campaign_window_sha256": selector["campaign_window_sha256"],
        "mode_manifest_sha256": mode_sha,
        "ordered_mode_key_sha256": key_sha,
    }
    if v29_strict_factor_only:
        current_identity["execution_campaign_window_sha256"] = str(
            os.environ.get("TASK40_V29_EXECUTION_WINDOW_SHA256", "")
        )
        current_identity["execution_contract_sha256"] = str(v29_contract_sha256)
        current_identity["execution_selector_sha256"] = str(v29_selector_sha256)
    donor_identity_sha = hashlib.sha256(
        json.dumps(donor_import, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    source_identity = {
        "donor_identity": dict(donor_import),
        "execution_identity": dict(current_identity),
        "donor_identity_sha256": donor_identity_sha,
    }
    partial_path = output_directory / "v20_partial_result.json"
    if v28_continuation:
        operation_path = output_directory / "v28_q0_continuation_stage.json"
        csr_root = pattern_manifest_path.parent
        manifest_path = continuation_manifest_path
    else:
        operation_path = output_directory / "v27_saved_q0_stage.json"
        csr_root = output_directory / "v27_q0_csr"
        manifest_path = csr_root / "task40_v27_q0_csr_manifest.json"
    if operation_path.exists() or partial_path.exists():
        raise FileExistsError("refusing to replace an existing saved q0 operation or partial receipt")

    operation: dict[str, Any] = {
        "schema": (
            "task40extra.review_v28_q0_continuation_stage.v1"
            if v28_continuation
            else "task40extra.review_v27_saved_q0_stage.v1"
        ),
        "status": "V28_CONTINUATION_STARTED" if v28_continuation else "FAILED_V27_SAVED_Q0",
        "classification": (
            "V28_EXISTING_MANIFEST_Q0_CONTINUATION"
            if v28_continuation
            else "V27_SAVED_ONLY_Q0_CSR"
        ),
        "official_result": False,
        "stop_stage": stop_stage,
        "selector_path": str(selector_path),
        "selector_sha256": selector_sha,
        "operation": expected_operation,
        "current_execution_identity": dict(current_identity),
        "donor_import_identity_sha256": donor_identity_sha,
        "donor_import_identity": dict(donor_import),
        "source_identity": source_identity,
        "saved_only_no_fe_or_native_rebuild": True,
        "q_map_count": 1,
        "q_map_branch": 0,
        "factor_or_solve_built": False,
        "ksp_created": False,
        "pde_solved": False,
    }
    if v28_continuation:
        operation.update(
            {
                "pattern_manifest_path": str(pattern_manifest_path),
                "pattern_manifest_sha256": str(
                    os.environ.get("TASK40_V28_PATTERN_MANIFEST_SHA256", "")
                ),
                "continuation_manifest_path": str(manifest_path),
                "source_pattern_reused": True,
                "formal_numeric_fill_started": False,
            }
        )
        _write_json(operation_path, operation)

    def continue_v28_factor_only_if_qualified() -> dict[str, Any] | None:
        if not v28_continuation:
            return None
        v29_factor_only_prepare_started = (
            time.perf_counter() if v29_strict_factor_only else None
        )
        if not manifest_path.is_file():
            if v29_strict_factor_only:
                raise RuntimeError(
                    "V29 strict factor-only refused before adapter/fill/readback: "
                    f"COMPLETE_CSR manifest is missing at {manifest_path}"
                )
            return None
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") != "COMPLETE_CSR":
            if v29_strict_factor_only:
                raise RuntimeError(
                    "V29 strict factor-only refused before adapter/fill/readback: "
                    f"manifest.status expected COMPLETE_CSR, got {existing.get('status')!r} "
                    f"at {manifest_path}"
                )
            operation["continuation_action"] = _v28_continuation_action(
                str(existing.get("status", "")), False
            )
            return None
        if v29_strict_factor_only and (
            _sha256_file(manifest_path) != v29_selector.get("manifest_sha256")
            or manifest_path.resolve()
            != v29_resolve_path(v29_selector.get("manifest_path", ""))
        ):
            raise RuntimeError(
                "V29 strict factor-only refused before adapter/fill/readback: "
                f"COMPLETE_CSR manifest path/hash differs at {manifest_path}"
            )
        qualification_match_started = time.perf_counter()
        qualification_binding = _load_matching_v28_native_qualification(
            repo_root=repo_root,
            manifest_path=manifest_path,
            manifest=existing,
            expected_pattern_path=pattern_manifest_path,
            expected_pattern_sha256=os.environ["TASK40_V28_PATTERN_MANIFEST_SHA256"],
            donor_identity_sha256=donor_identity_sha,
            input_sha256=str(preflight.get("input_sha256", "")),
            physical_model_sha256=str(preflight.get("physical_model_sha256", "")),
            run_id=str(preflight.get("run_id", "")),
            campaign_window_sha256=str(selector["campaign_window_sha256"]),
            mode_manifest_sha256=mode_sha,
            ordered_mode_key_sha256=key_sha,
            sha256_file=_sha256_file,
            path_resolver=v29_resolve_path if v29_strict_factor_only else None,
        )
        qualification_match_seconds = float(time.perf_counter() - qualification_match_started)
        action = _v28_continuation_action(
            "COMPLETE_CSR", qualification_binding is not None
        )
        operation["continuation_action"] = action
        if qualification_binding is None:
            operation["existing_native_qualification_rejected_or_missing"] = True
            if v29_strict_factor_only:
                native_record = existing.get("native_qualification", {})
                native_record = native_record if isinstance(native_record, Mapping) else {}
                raise RuntimeError(
                    "V29 strict factor-only refused before adapter/fill/readback: "
                    "matching native PASS is missing or failed identity checks; "
                    f"manifest={manifest_path}; qualification={native_record.get('path')!r}; "
                    f"qualification_sha256={native_record.get('sha256')!r}"
                )
            return None

        qualification_path, qualification = qualification_binding
        if v29_strict_factor_only:
            require_strict_factor_only_status(existing, qualification)
        if v29_strict_factor_only and (
            qualification_path.resolve()
            != v29_resolve_path(v29_selector.get("qualification_path", ""))
            or _sha256_file(qualification_path)
            != v29_selector.get("qualification_sha256")
        ):
            raise RuntimeError(
                "V29 strict factor-only refused before adapter/fill/readback: "
                "matching native PASS differs from the approved selector"
            )
        artifact_records = existing.get("csr_artifacts", {})
        artifact_records = artifact_records if isinstance(artifact_records, Mapping) else {}
        csr_payload_bytes = sum(
            int(item.get("bytes", 0))
            for item in artifact_records.values()
            if isinstance(item, Mapping)
        )
        allocation_gate(
            "task40_v28_q0_existing_qualified_csr_factor_input",
            {
                "additional_payload_bytes": csr_payload_bytes,
                "matrix_payload_bytes": 0,
                "workspace_bytes": 8 * 1024 * 1024,
                "future_co_resident_reserve_bytes": 0,
                "disk_payload_bytes": 0,
                "complete_csr_payload_bytes": csr_payload_bytes,
                "read_only_memory_map": True,
                "qualification_sha256": _sha256_file(qualification_path),
                "all_three_csr_array_hashes_bound": True,
            },
        )
        saved_csr_open_started = time.perf_counter()
        q0_csr, completed_manifest = open_saved_q0_csr_from_manifest(
            manifest_path,
            path_resolver=v29_resolve_path if v29_strict_factor_only else None,
        )
        saved_csr_open_seconds = float(time.perf_counter() - saved_csr_open_started)
        if v29_strict_factor_only:
            operation["timings_v29"] = {
                "qualification_match_full_identity_parent_seconds": qualification_match_seconds,
                "saved_csr_open_and_full_hash_parent_seconds": saved_csr_open_seconds,
                "csr_arrays_are_read_only_mmap": True,
                "csr_payload_bytes_hashed": csr_payload_bytes,
            }
        qualification_sha = _sha256_file(qualification_path)
        current_identity["native_qualification_sha256"] = qualification_sha
        operation["current_execution_identity"] = dict(current_identity)
        operation.update(
            {
                "continuation_action": "factor_only",
                "numeric_fill_skipped": True,
                "native_readback_skipped": True,
                "factor_only_continuation": True,
                "csr_manifest_path": str(manifest_path),
                "csr_manifest_sha256": _sha256_file(manifest_path),
                "csr_status": "COMPLETE_CSR",
                "complete_numeric_csr": True,
                "csr_artifacts": dict(completed_manifest["csr_artifacts"]),
                "stored_structural_slots": int(completed_manifest["stored_structural_slots"]),
                "numeric_facts": dict(completed_manifest["numeric_pass"]["numeric_facts"]),
                "csr_readback": dict(qualification["readback"]),
                "csr_readback_artifact": dict(qualification["readback_artifact"]),
                "native_qualification_receipt": {
                    "path": str(qualification_path),
                    "sha256": qualification_sha,
                    "status": qualification["status"],
                },
                "native_qualification_original_source_identity": dict(
                    qualification["source_identity"]
                ),
                "factor_execution_identity": dict(current_identity),
            }
        )
        if v29_strict_factor_only:
            operation["v29_strict_factor_only_binding"] = {
                "contract_sha256": v29_contract_sha256,
                "selector_sha256": v29_selector_sha256,
                "execution_window_sha256": os.environ.get(
                    "TASK40_V29_EXECUTION_WINDOW_SHA256"
                ),
                "strict_policy": "COMPLETE_AND_MATCHING_V28_NATIVE_PASS_REQUIRED",
                "fallback_disabled": True,
            }
        v29_initial_loader_parent_seconds = (
            float(time.perf_counter() - v29_factor_only_prepare_started)
            if v29_factor_only_prepare_started is not None
            else None
        )
        factor_root = output_directory / "v28_q0_factor"
        factor_checkpoint_path = factor_root / "v26_q0_factor_checkpoints.json"
        try:
            from src.solvers.task40_v10_p6_mumps import (
                run_task40_v26_selected_q0_factor_lifecycle,
            )

            factor_report = run_task40_v26_selected_q0_factor_lifecycle(
                q0_csr,
                allocation_gate=allocation_gate,
                checkpoint_directory=factor_root,
                current_identity=current_identity,
            )
        except _ProbeResourceBlocked as error:
            factor_report = {
                "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                "status": "RESOURCE_CONTROLLED_STOP",
                "selected_q": 0,
                "failed_stage": error.stage,
                "resource_blocker": {"stage": error.stage, **dict(error.facts), "passed": False},
                "checkpoint_path": str(factor_checkpoint_path),
                "checkpoint_sha256": _sha256_file(factor_checkpoint_path)
                if factor_checkpoint_path.is_file() else None,
            }
        except Exception as error:
            factor_report = {
                "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                "status": "FAILED_Q0_FACTOR_LIFECYCLE",
                "selected_q": 0,
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "checkpoint_path": str(factor_checkpoint_path),
                "checkpoint_sha256": _sha256_file(factor_checkpoint_path)
                if factor_checkpoint_path.is_file() else None,
            }
        factor_built = bool(
            factor_report.get("q_coverage", {}).get("numeric_factor_built") is True
        )
        if v29_strict_factor_only:
            lifecycle_timings = factor_report.get("timings_v29", {})
            lifecycle_timings = lifecycle_timings if isinstance(lifecycle_timings, Mapping) else {}
            lifecycle_fq = lifecycle_timings.get("F_q", {})
            lifecycle_fq = lifecycle_fq if isinstance(lifecycle_fq, Mapping) else {}
            initial_loader_timings = operation.get("timings_v29", {})
            initial_loader_timings = (
                initial_loader_timings if isinstance(initial_loader_timings, Mapping) else {}
            )
            lifecycle_fq_seconds = lifecycle_fq.get("parent_seconds")
            loader_seconds = v29_initial_loader_parent_seconds
            operation["timings_v29"]["F_q"] = {
                "status": lifecycle_fq.get("status", "NOT_RECORDED"),
                "parent_seconds": (
                    float(loader_seconds) + float(lifecycle_fq_seconds)
                    if isinstance(loader_seconds, (int, float))
                    and isinstance(lifecycle_fq_seconds, (int, float))
                    else None
                ),
                "includes_initial_loader": True,
                "initial_loader_parent_seconds": loader_seconds,
                "initial_loader_subphases": {
                    "qualification_match_full_identity_parent_seconds": initial_loader_timings.get(
                        "qualification_match_full_identity_parent_seconds"
                    ),
                    "saved_csr_open_and_full_hash_parent_seconds": initial_loader_timings.get(
                        "saved_csr_open_and_full_hash_parent_seconds"
                    ),
                    "initial_loader_total_boundary": "from strict COMPLETE/PASS manifest entry through read-only mmap and full CSR file hash; includes intervening identity checks and resource admission",
                },
                "factor_lifecycle_through_fresh_qualification_parent_seconds": lifecycle_fq_seconds,
                "boundary": "cold q0 factor-cache miss starts at strict saved-manifest/qualification validation; includes initial CSR loader, conversion, symbolic, numeric, first MatSolve, full explicit true residual and fresh raw readback; ends before second RHS and eviction",
                "second_rhs_and_eviction_included": False,
            }
            operation["timings_v29"]["S_q"] = lifecycle_timings.get("S_q", {
                "status": "NOT_RECORDED",
                "parent_seconds": None,
            })
            operation["timings_v29"]["eviction"] = lifecycle_timings.get("eviction", {
                "parent_seconds": None,
                "status": "NOT_RECORDED",
            })
        operation["factor_lifecycle"] = factor_report
        operation["factor_or_solve_built"] = factor_built
        operation["factor_checkpoint"] = {
            "path": str(factor_checkpoint_path),
            "sha256": _sha256_file(factor_checkpoint_path)
            if factor_checkpoint_path.is_file() else None,
        }
        if factor_report.get("status") == "PASS_Q0_FACTOR_PROBE_AND_RHS_SOLVE":
            operation["status"] = "PASS_COMPLETE_Q0_CSR_AND_FACTOR"
        elif factor_report.get("status") == "RESOURCE_CONTROLLED_STOP":
            operation["status"] = "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
            operation["failed_stage"] = factor_report.get("failed_stage")
            operation["resource_blocker"] = factor_report.get("resource_blocker")
        else:
            operation["status"] = "FAILED_Q0_FACTOR_LIFECYCLE"
            operation["failed_stage"] = "q0_factor_lifecycle"
            operation["failure_type"] = factor_report.get("failure_type")
            operation["failure_message"] = factor_report.get("failure_message")
        operation["factor_lifecycle_executed_without_adapter_or_native_readback"] = True
        return _write_v28_continuation_footer(
            output_directory=output_directory,
            operation_path=operation_path,
            manifest_path=manifest_path,
            progress_path=output_directory / "v28_q0_numeric_progress.json",
            operation=operation,
            stop_stage=stop_stage,
            profile=profile,
            source_sha=source_sha,
            preflight=preflight,
            selector_path=selector_path,
            selector_sha=selector_sha,
            donor_identity_sha256=donor_identity_sha,
            resource_gate_records=resource_gate_records,
        )

    try:
        factor_only_result = continue_v28_factor_only_if_qualified()
        if factor_only_result is not None:
            return factor_only_result
        if v29_strict_factor_only:
            raise RuntimeError(
                "V29 strict factor-only refused before adapter/fill/readback: no qualified continuation returned"
            )
        payloads = {
            str(item.get("path")): item
            for item in producer_identity.get("payloads", [])
            if isinstance(item, Mapping)
        }
        q0_map_path = (producer_root / "v25_selected_q0_map.npz").resolve()
        lookup_path = (producer_root / "v25_selected_q0_original_to_active_int32.npy").resolve()
        h_path = (producer_root / "v25_selected_q0_local_H_p.npy").resolve()
        volume_path = (producer_root / "v25_selected_q0_volume_classes.bin").resolve()
        surface_path = (producer_root / "v25_selected_q0_surface_functionals.bin").resolve()
        for name, path in (
            ("v25_selected_q0_map.npz", q0_map_path),
            ("v25_selected_q0_original_to_active_int32.npy", lookup_path),
            ("v25_selected_q0_local_H_p.npy", h_path),
            ("v25_selected_q0_volume_classes.bin", volume_path),
            ("v25_selected_q0_surface_functionals.bin", surface_path),
        ):
            item = payloads.get(name)
            if (
                not isinstance(item, Mapping)
                or not path.is_relative_to(producer_root)
                or not path.is_file()
                or path.stat().st_size != item.get("bytes")
                or not isinstance(item.get("sha256"), str)
                or len(item["sha256"]) != 64
            ):
                raise ValueError(f"V27 donor payload path/size/hash identity is invalid: {name}")
        q0_map_uncompressed_bytes = 0
        with zipfile.ZipFile(q0_map_path) as archive:
            members = {item.filename: int(item.file_size) for item in archive.infolist()}
        if not {"data.npy", "indices.npy", "indptr.npy", "shape.npy", "format.npy"} <= set(members):
            raise ValueError("V27 q0 map NPZ has an unexpected sparse-array inventory")
        q0_map_uncompressed_bytes = sum(members.values())
        lookup_bytes = int(payloads[lookup_path.name]["bytes"])
        h_bytes = int(payloads[h_path.name]["bytes"])
        witness = donor_import.get("row_structure_witness", {})
        witness = witness if isinstance(witness, Mapping) else {}
        witness_path = Path(str(witness.get("path", ""))).resolve()
        witness_bytes = int(witness.get("bytes", 0))
        if (
            not witness_path.is_file()
            or not witness_path.is_relative_to(repo_root)
            or witness_path.stat().st_size != witness_bytes
            or len(str(witness.get("sha256", ""))) != 64
            or _saved_q_sha256(witness_path) != witness.get("sha256")
        ):
            raise ValueError("V27 frozen complete-row witness is missing or changed")
        from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES
        from src.solvers.task40_v27_saved_q0 import inspect_saved_q0_input_headers

        periodic = TASK40_P6_PERIODIC_PROFILES[profile]
        header_inventory = inspect_saved_q0_input_headers(
            q0_map_path=q0_map_path,
            active_lookup_path=lookup_path,
            local_h_path=h_path,
            row_witness_path=witness_path,
            profile=periodic,
            q_index=int(operation["q_map_branch"]),
        )
        operation["saved_input_header_inventory"] = header_inventory
        map_load_bytes = (
            q0_map_uncompressed_bytes + lookup_bytes + h_bytes + witness_bytes
        )
        allocation_gate(
            "task40_v27_saved_q0_readonly_inputs_load",
            {
                "additional_payload_bytes": int(map_load_bytes),
                "workspace_bytes": 8 * 1024 * 1024,
                "future_co_resident_reserve_bytes": 0,
                "q0_map_uncompressed_payload_bytes": int(q0_map_uncompressed_bytes),
                "active_lookup_payload_bytes": lookup_bytes,
                "local_h_payload_bytes": h_bytes,
                "complete_row_witness_payload_bytes": witness_bytes,
                "q_map_count": 1,
                "q_index": int(header_inventory["q_index"]),
                "sector_index": int(header_inventory["sector_index"]),
                "sector_local_alias_count": int(header_inventory["sector_local_alias_count"]),
                "full_profile_mode_count": int(header_inventory["full_profile_mode_count"]),
                "q4_map_loaded": False,
                "mmap_or_file_cache_counted_as_memory": True,
            },
        )

        with np.load(witness_path, allow_pickle=False) as archive:
            if set(archive.files) != {"row_counts_int64", "wide_offsets_int64"}:
                raise ValueError("V27 row witness has an unexpected field inventory")
            row_counts = np.asarray(archive["row_counts_int64"], dtype=np.int64)
            offsets = np.asarray(archive["wide_offsets_int64"], dtype=np.int64)
        expected_q0_columns = int(header_inventory["expected_shapes"]["q0_map"][1])
        if row_counts.shape != (expected_q0_columns,) or offsets.shape != (expected_q0_columns + 1,):
            raise ValueError("V27 frozen full q0 row witness has the wrong vector dimensions")
        if _file_sha256(q0_map_path) != payloads[q0_map_path.name]["sha256"]:
            raise ValueError("V27 q0 map changed after the service donor binding")
        q0_map = sparse.load_npz(q0_map_path)
        if not sparse.isspmatrix_csr(q0_map):
            raise ValueError("V27 saved q0 map is not CSR")
        active_lookup = np.load(lookup_path, mmap_mode="r", allow_pickle=False)
        local_h = np.load(h_path, mmap_mode="r", allow_pickle=False)
        expected_shapes = header_inventory["expected_shapes"]
        if (
            tuple(q0_map.shape) != tuple(expected_shapes["q0_map"])
            or q0_map.shape[0] != periodic.local_trace_rows + int(local_h.size)
            or tuple(active_lookup.shape) != tuple(expected_shapes["active_lookup"])
            or tuple(local_h.shape) != tuple(expected_shapes["local_H"])
        ):
            raise ValueError("V27 saved q0-only map/lookup/H dimensions differ from the frozen profile")
        with q0_map_path.open("rb") as stream:
            _advise_file_drop(stream, 0, q0_map_path.stat().st_size)
        reader_telemetry: dict[str, Any] = {"advice_calls": 0, "advised_bytes": 0}
        adapter = SavedQ0ContributionAdapter(
            volume_stream_path=volume_path,
            surface_stream_path=surface_path,
            active_lookup=active_lookup,
            local_h=local_h,
            q0_map=q0_map,
            active_rows=int(periodic.local_trace_rows),
            q0_trace_rows=int(periodic.trace_rows_per_q),
            q0_port_rows=int(header_inventory["expected_shapes"]["q0_map"][1]
                             - periodic.trace_rows_per_q),
            allocation_gate=allocation_gate,
            expected_cell_count=int(periodic.local_cell_count),
            expected_class_count=45,
            reader_telemetry=reader_telemetry,
        )
        csr_preflight = preflight_saved_q0_csr(
            adapter,
            expected_row_counts=row_counts,
            expected_offsets=offsets,
            allocation_gate=allocation_gate,
        )
        operation["saved_only_preflight"] = {
            **dict(csr_preflight),
            "live_resource_gates": resource_gate_records(),
            "source_map_identity": {
                "path": str(q0_map_path),
                "bytes": int(q0_map_path.stat().st_size),
                "sha256": payloads[q0_map_path.name]["sha256"],
                "loaded_q_maps": ["q0"],
            },
        }
        progress_path = output_directory / "v28_q0_numeric_progress.json"
        progress_state: dict[str, Any] | None = None
        progress_last_write = 0.0
        progress_last_component: str | None = None
        if v28_continuation:
            progress_state = {
                "schema": "task40extra.review_v28_q0_numeric_progress.v1",
                "status": "IN_PROGRESS",
                "source_identity": current_identity,
                "continuation_manifest_path": str(manifest_path),
                "restart_policy": "clear_all_values_before_each_numeric_pass; progress_is_not_a_cursor",
                "completed_work_items_by_component": {"Hhat": 0, "volume": 0, "surface": 0},
                "expected_work_items_by_component": {
                    "Hhat": 1,
                    "volume": int(adapter.volume_layout["cell_count"]),
                    "surface": int(
                        adapter.surface_nonempty_b_count
                        + adapter.surface_nonempty_d_count
                    ),
                },
                "component_parent_wall_seconds": {"Hhat": 0.0, "volume": 0.0, "surface": 0.0},
                "component_child_seconds": {"Hhat": 0.0, "volume": 0.0, "surface": 0.0},
                "contribution_generation_seconds": 0.0,
                "projection_seconds": 0.0,
                "scatter_seconds": 0.0,
                "resource_gate_calls": 0,
                "resource_gate_seconds": 0.0,
                "read_and_constraint_split": "not separately instrumented; combined contribution_generation_seconds is measured",
                "data_zero_and_flush_seconds": None,
                "data_hash_seconds": None,
                "contribution_value_bytes_completed": 0,
                "completed_contribution_count": 0,
                "last_completed_label": None,
            }

            component_started_at: dict[str, float] = {}

            def persist_v28_progress(
                rows: np.ndarray | None,
                columns: np.ndarray | None,
                values: np.ndarray | None,
                label: str,
                timings: Mapping[str, float],
            ) -> None:
                nonlocal progress_last_write, progress_last_component
                if progress_state is None:
                    return
                if label.startswith("ports/Hhat/"):
                    component = "Hhat"
                elif label.startswith("volume/cell/"):
                    component = "volume"
                else:
                    component = "surface"
                counts = progress_state["completed_work_items_by_component"]
                counts[component] = int(counts[component]) + 1
                progress_state["completed_contribution_count"] = int(
                    progress_state["completed_contribution_count"]
                ) + 1
                progress_state["last_completed_label"] = label
                progress_state["contribution_value_bytes_completed"] = int(
                    progress_state["contribution_value_bytes_completed"]
                ) + (int(values.nbytes) if values is not None else 0)
                component_child = progress_state["component_child_seconds"]
                component_child[component] = float(
                    component_child[component]
                    + sum(float(value) for value in timings.values())
                )
                generation_seconds = float(timings.get("generation_seconds", 0.0))
                progress_state["contribution_generation_seconds"] = float(
                    progress_state["contribution_generation_seconds"]
                    + generation_seconds
                )
                progress_state["projection_seconds"] = float(
                    progress_state["projection_seconds"]
                    + float(timings.get("projection_seconds", 0.0))
                )
                progress_state["scatter_seconds"] = float(
                    progress_state["scatter_seconds"]
                    + float(timings.get("accumulation_seconds", 0.0))
                )
                now = time.monotonic()
                component_started_at.setdefault(
                    component,
                    now - sum(float(value) for value in timings.values()),
                )
                progress_state["component_parent_wall_seconds"][component] = float(
                    now - component_started_at[component]
                )
                boundary = progress_last_component != component
                if boundary or now - progress_last_write >= 60.0:
                    memory = _resource_snapshot()
                    cgroup = memory.get("current_process_cgroup", {})
                    try:
                        resident_pages = int(
                            Path("/proc/self/statm")
                            .read_text(encoding="ascii")
                            .split()[1]
                        )
                        rss_bytes = resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
                    except (OSError, ValueError, IndexError):
                        rss_bytes = None
                    expected = progress_state["expected_work_items_by_component"]
                    eta: dict[str, float | None] = {}
                    remaining: dict[str, int] = {}
                    for key, total in expected.items():
                        done = int(counts[key])
                        remaining[key] = max(0, int(total) - done)
                        seconds = float(
                            progress_state["component_parent_wall_seconds"][key]
                        )
                        eta[key] = remaining[key] * seconds / done if done > 0 else None
                    cgroup_stat = cgroup.get("memory_stat_bytes", {}) if isinstance(cgroup, Mapping) else {}
                    progress_state.update(
                        {
                            "current_component": component,
                            "component_boundary_transition": (
                                None
                                if progress_last_component is None
                                else {"from": progress_last_component, "to": component}
                            ),
                            "remaining_work_items_by_component": remaining,
                            "linear_component_eta_seconds": eta,
                            "eta_uncertainty": (
                                "per-component mean only; excludes hashing, readback, factor, and service closeout"
                            ),
                            "current_process_rss_bytes": rss_bytes,
                            "current_process_cgroup": cgroup,
                            "task_swap_current_bytes": (
                                cgroup.get("swap_current_bytes")
                                if isinstance(cgroup, Mapping)
                                else None
                            ),
                            "host_memory_available_bytes": memory.get(
                                "host_memory_available_bytes"
                            ),
                            "task_cgroup_anon_bytes": cgroup_stat.get("anon") if isinstance(cgroup_stat, Mapping) else None,
                            "task_cgroup_file_bytes": cgroup_stat.get("file") if isinstance(cgroup_stat, Mapping) else None,
                            "task_cgroup_file_dirty_bytes": cgroup_stat.get("file_dirty") if isinstance(cgroup_stat, Mapping) else None,
                            "saved_reader_advice_calls": int(reader_telemetry.get("advice_calls", 0)),
                            "saved_reader_advised_bytes": int(reader_telemetry.get("advised_bytes", 0)),
                            "resource_gate_records": resource_gate_records(),
                            "resource_gate_calls": int(resource_gate_timing["calls"]),
                            "resource_gate_seconds": float(resource_gate_timing["seconds"]),
                            "progress_is_not_a_restart_cursor": True,
                            "resource_gate_count": len(resource_gates_by_stage),
                        }
                    )
                    _write_json(progress_path, progress_state)
                    persist_v28_checkpoint()
                    progress_last_write = now
                    progress_last_component = component

            def persist_v28_checkpoint() -> None:
                if not v28_continuation or progress_state is None:
                    return
                if not str(operation.get("status", "")).endswith("_IN_PROGRESS"):
                    operation["status"] = "V28_NUMERIC_FILL_IN_PROGRESS"
                _write_json(progress_path, progress_state)
                operation["numeric_progress"] = dict(progress_state)
                operation["resource_gates"] = resource_gate_records()
                operation["resource_gate_timing"] = dict(resource_gate_timing)
                operation["progress_is_not_restart_cursor"] = True
                _write_v28_continuation_footer(
                    output_directory=output_directory,
                    operation_path=operation_path,
                    manifest_path=manifest_path,
                    progress_path=progress_path,
                    operation=operation,
                    stop_stage=stop_stage,
                    profile=profile,
                    source_sha=source_sha,
                    preflight=preflight,
                    selector_path=selector_path,
                    selector_sha=selector_sha,
                    donor_identity_sha256=donor_identity_sha,
                    resource_gate_records=resource_gate_records,
                )

            def persist_v28_fill_phase(phase: str, facts: Mapping[str, Any]) -> None:
                if progress_state is None:
                    return
                progress_state["last_fill_phase"] = phase
                progress_state["last_fill_phase_facts"] = dict(facts)
                if phase == "data_zeroed_and_flushed":
                    progress_state["data_zero_and_flush_seconds"] = facts.get("elapsed_seconds")
                    progress_state["data_zeroed_bytes"] = facts.get("bytes")
                elif phase == "data_hash_progress":
                    progress_state["data_hash_bytes_processed"] = facts.get("bytes_processed")
                    progress_state["data_hash_elapsed_seconds"] = facts.get("elapsed_seconds")
                elif phase == "data_sha256_complete":
                    progress_state["data_hash_seconds"] = facts.get("elapsed_seconds")
                    progress_state["data_hash_bytes"] = facts.get("bytes")
                    progress_state["data_sha256"] = facts.get("sha256")
                progress_state["resource_gate_records"] = resource_gate_records()
                progress_state["resource_gate_calls"] = int(resource_gate_timing["calls"])
                progress_state["resource_gate_seconds"] = float(resource_gate_timing["seconds"])
                cgroup = _task_cgroup_memory_snapshot()
                stat = cgroup.get("memory_stat_bytes", {}) if isinstance(cgroup, Mapping) else {}
                progress_state["task_cgroup_anon_bytes"] = stat.get("anon") if isinstance(stat, Mapping) else None
                progress_state["task_cgroup_file_bytes"] = stat.get("file") if isinstance(stat, Mapping) else None
                progress_state["task_cgroup_file_dirty_bytes"] = stat.get("file_dirty") if isinstance(stat, Mapping) else None
                _write_json(progress_path, progress_state)
                persist_v28_checkpoint()

        if v28_continuation:
            if (
                not pattern_manifest_path.is_file()
                or _saved_q_sha256(pattern_manifest_path)
                != os.environ.get("TASK40_V28_PATTERN_MANIFEST_SHA256")
            ):
                raise ValueError("V28 source V27 pattern manifest changed before continuation")
            if manifest_path.exists():
                continuation_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                if (
                    continuation_manifest.get("schema")
                    != "task40extra.review_v28_saved_q0_csr.v1"
                    or continuation_manifest.get("original_pattern_manifest", {}).get(
                        "sha256"
                    )
                    != os.environ.get("TASK40_V28_PATTERN_MANIFEST_SHA256")
                    or continuation_manifest.get("source_identity", {}).get(
                        "donor_identity"
                    )
                    != donor_import
                ):
                    raise ValueError("existing V28 continuation manifest identity changed")
            else:
                continuation_manifest, _ = create_v28_saved_q0_csr_continuation_manifest(
                    pattern_manifest_path=pattern_manifest_path,
                    continuation_manifest_path=manifest_path,
                    expected_pattern_manifest_sha256=os.environ[
                        "TASK40_V28_PATTERN_MANIFEST_SHA256"
                    ],
                    current_execution_identity=current_identity,
                    donor_identity=donor_import,
                )
            structure_manifest = json.loads(
                pattern_manifest_path.read_text(encoding="utf-8")
            )
            operation["continuation_manifest_status_at_entry"] = continuation_manifest.get(
                "status"
            )
            operation["continuation_action"] = _v28_continuation_action(
                str(continuation_manifest.get("status", "")),
                operation.get("continuation_action") == "factor_only",
            )
            operation["original_pattern_manifest_sha256_verified"] = True
            operation["data_reuse_event"] = dict(
                continuation_manifest.get("continuation_event", {})
            )
            operation["formal_numeric_fill_started"] = False
            _write_json(operation_path, operation)
            if continuation_manifest.get("status") == "COMPLETE_CSR":
                operation["status"] = "V28_NATIVE_READBACK_IN_PROGRESS"
                progress_state["status"] = "READBACK_IN_PROGRESS"
                operation["continuation_action"] = "readback_and_factor"
                _write_json(progress_path, progress_state)
                persist_v28_checkpoint()
                q0_csr, completed_manifest = open_saved_q0_csr_from_manifest(
                    manifest_path
                )
                operation["numeric_fill_skipped"] = True
            else:
                progress_state["status"] = "READY_TO_CLEAR_AND_FILL"
                progress_state["resource_gate_records"] = resource_gate_records()
                progress_state["resource_gate_calls"] = int(resource_gate_timing["calls"])
                progress_state["resource_gate_seconds"] = float(resource_gate_timing["seconds"])
                cgroup = _task_cgroup_memory_snapshot()
                cgroup_stat = cgroup.get("memory_stat_bytes", {}) if isinstance(cgroup, Mapping) else {}
                progress_state["task_cgroup_anon_bytes"] = cgroup_stat.get("anon") if isinstance(cgroup_stat, Mapping) else None
                progress_state["task_cgroup_file_bytes"] = cgroup_stat.get("file") if isinstance(cgroup_stat, Mapping) else None
                progress_state["task_cgroup_file_dirty_bytes"] = cgroup_stat.get("file_dirty") if isinstance(cgroup_stat, Mapping) else None
                _write_json(progress_path, progress_state)
                operation["status"] = "V28_NUMERIC_FILL_IN_PROGRESS"
                operation["formal_numeric_fill_started"] = False
                persist_v28_checkpoint()
                operation["formal_numeric_fill_started"] = True
                _write_json(operation_path, operation)
                progress_state["status"] = "CLEARING_AND_FILLING"
                persist_v28_checkpoint()
                q0_csr, completed_manifest = fill_saved_q0_csr_values(
                    adapter,
                    manifest_path=manifest_path,
                    allocation_gate=allocation_gate,
                    source_identity=source_identity,
                    projection_method="sparse_local",
                    direct_hhat=True,
                    contribution_completed_observer=persist_v28_progress,
                    phase_observer=persist_v28_fill_phase,
                )
                if progress_state is not None:
                    progress_state["status"] = "NUMERIC_FILL_COMPLETED"
                    progress_state["continuation_manifest_sha256"] = _sha256_file(
                        manifest_path
                    )
                    _write_json(progress_path, progress_state)
                    persist_v28_checkpoint()
        else:
            blocks, structure_manifest, manifest_path = build_saved_q0_csr_structure(
                adapter,
                output_directory=csr_root,
                expected_row_counts=row_counts,
                expected_offsets=offsets,
                allocation_gate=allocation_gate,
                source_identity=source_identity,
            )
            del blocks
            q0_csr, completed_manifest = fill_saved_q0_csr_values(
                adapter,
                manifest_path=manifest_path,
                allocation_gate=allocation_gate,
                source_identity=source_identity,
            )
        del q0_csr
        gc.collect()
        csr_artifacts = completed_manifest.get("csr_artifacts", {})
        csr_artifacts = csr_artifacts if isinstance(csr_artifacts, Mapping) else {}
        allocation_gate(
            "task40_v28_q0_csr_manifest_readback"
            if v28_continuation
            else "task40_v27_q0_csr_manifest_readback",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": 8 * 1024 * 1024,
                "disk_payload_bytes": 0,
                "read_only_memory_map": True,
                "manifest_payload_hash_read_bytes": sum(
                    int(item.get("bytes", 0))
                    for item in csr_artifacts.values()
                    if isinstance(item, Mapping)
                ),
                "filled_csr_object_released_before_reopen": True,
            },
        )
        q0_csr, completed_manifest = open_saved_q0_csr_from_manifest(manifest_path)
        operation["csr_manifest_path"] = str(manifest_path)
        operation["csr_manifest_sha256"] = _sha256_file(manifest_path)
        operation["csr_status"] = completed_manifest["status"]
        operation["csr_structure_status"] = structure_manifest["status"]
        if completed_manifest.get("status") == "COMPLETE_CSR":
            operation["complete_numeric_csr"] = True
            operation["csr_artifacts"] = dict(completed_manifest["csr_artifacts"])
            operation["stored_structural_slots"] = int(
                completed_manifest["stored_structural_slots"]
            )
            operation["numeric_facts"] = dict(
                completed_manifest["numeric_pass"]["numeric_facts"]
            )
            operation["numeric_fill_skipped"] = bool(
                operation.get("numeric_fill_skipped")
            )
            if v28_continuation and progress_state is not None:
                progress_state["status"] = "READBACK_IN_PROGRESS"
                persist_v28_checkpoint()

        readback_started = time.perf_counter()
        if v28_continuation and progress_state is not None:
            progress_state["readback_started"] = True
            progress_state["readback_matvec_seconds"] = {}
            persist_v28_checkpoint()
        replay_artifacts = donor_import.get("saved_replay_manifest", {}).get("artifacts", {})
        input_record = replay_artifacts.get("inputs") if isinstance(replay_artifacts, Mapping) else None
        input_path = Path(str(input_record.get("path", ""))).resolve() if isinstance(input_record, Mapping) else Path()
        if (
            not isinstance(input_record, Mapping)
            or not input_path.is_relative_to(replay_root)
            or not input_path.is_file()
            or input_path.stat().st_size != input_record.get("bytes")
            or _file_sha256(input_path) != input_record.get("sha256")
        ):
            raise ValueError("V27 saved q0 replay inputs are not bound to the accepted V26 donor")
        q0_size = int(q0_map.shape[1])
        readback_reserve = adapter.owner_reserve_facts()
        vector_bytes = q0_size * np.dtype(np.complex128).itemsize
        allocation_gate(
            "task40_v27_q0_csr_native_readback_vectors",
            {
                "additional_payload_bytes": int(8 * vector_bytes),
                "workspace_bytes": int(
                    9 * vector_bytes
                    + readback_reserve["maximum_cell_contribution_payload_bytes"]
                    + readback_reserve["maximum_cell_expansion_dense_workspace_bytes"]
                    + readback_reserve["maximum_surface_frame_working_bytes"]
                    + 4 * 1024 * 1024
                ),
                "future_co_resident_reserve_bytes": 0,
                "q0_inputs_to_load": 2,
                "native_q0_outputs_to_load": 6,
                "additional_trace_port_masked_inputs": 2,
                "full_csr_outputs": 4,
                "component_validation_outputs": 5,
                "csr_rows_all_columns_validation": True,
            },
        )
        with np.load(input_path, allow_pickle=False) as archive:
            if not {"q0_case_1", "q0_case_2"} <= set(archive.files):
                raise ValueError("V27 saved q0 input archive omits either nonzero validation vector")
            x1 = np.asarray(archive["q0_case_1"])
            x2 = np.asarray(archive["q0_case_2"])
        native_cases = donor_import.get("native_cases", {})
        case1_record = native_cases.get("q0_case_1") if isinstance(native_cases, Mapping) else None
        case2_record = native_cases.get("q0_case_2") if isinstance(native_cases, Mapping) else None
        if not isinstance(case1_record, Mapping) or not isinstance(case2_record, Mapping):
            raise ValueError("V27 donor import lacks both native q0 comparison cases")
        native1_path = Path(str(case1_record.get("path", ""))).resolve()
        native2_path = Path(str(case2_record.get("path", ""))).resolve()
        for path, record in ((native1_path, case1_record), (native2_path, case2_record)):
            if (
                not path.is_relative_to(native_root)
                or not path.is_file()
                or path.stat().st_size != record.get("bytes")
                or _file_sha256(path) != record.get("sha256")
            ):
                raise ValueError("V27 native q0 case changed after its service donor binding")
        with np.load(native1_path, allow_pickle=False) as archive:
            required_native1 = {
                "native_q0_total",
                "native_q0_volume",
                "native_q0_C",
                "native_q0_minus_D",
                "native_q0_Hhat",
            }
            if not required_native1 <= set(archive.files):
                raise ValueError("V27 q0 native case 1 omits a required component output")
            native1 = {name: np.asarray(archive[name]) for name in required_native1}
        with np.load(native2_path, allow_pickle=False) as archive:
            if "native_q0_total" not in archive.files:
                raise ValueError("V27 q0 native case 2 omits the total output")
            native2 = {"native_q0_total": np.asarray(archive["native_q0_total"])}
        for path in (input_path, native1_path, native2_path):
            with path.open("rb") as stream:
                _advise_file_drop(stream, 0, path.stat().st_size)
        if any(
            vector.shape != (q0_size,)
            or vector.dtype != np.dtype(np.complex128)
            or not np.isfinite(vector).all()
            for vector in (x1, x2)
        ) or not np.any(x1 != 0.0) or not np.any(x2 != 0.0) or np.array_equal(x1, x2):
            raise ValueError("V27 saved q0 readback inputs must be distinct finite nonzero complex128 vectors")
        native_component_names = {
            "volume": "native_q0_volume",
            "C": "native_q0_C",
            "minus_D": "native_q0_minus_D",
            "Hhat": "native_q0_Hhat",
        }
        if not {"native_q0_total", *native_component_names.values()} <= set(native1) or "native_q0_total" not in native2:
            raise ValueError("V27 saved native cases omit q0 total or component outputs")
        trace_rows = int(periodic.trace_rows_per_q)
        if q0_size - trace_rows != 4_076:
            raise ValueError("V27 q0 trace/port split differs from the frozen q0 map")

        def relative_error(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
            if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
                raise ValueError("V27 q0 readback vectors have invalid shape or non-finite entries")
            absolute = float(np.linalg.norm(left - right))
            scale = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), np.finfo(float).tiny)
            return {"absolute": absolute, "scale": scale, "relative": absolute / scale}

        matvec_started = time.perf_counter()
        full1 = np.asarray(q0_csr @ x1)
        if v28_continuation and progress_state is not None:
            progress_state["readback_matvec_seconds"]["case_1_full"] = float(
                time.perf_counter() - matvec_started
            )
            persist_v28_checkpoint()
        _drop_mmap_pages(q0_csr.data, 0, q0_csr.data.nbytes)
        _drop_mmap_pages(q0_csr.indices, 0, q0_csr.indices.nbytes)
        _drop_mmap_pages(q0_csr.indptr, 0, q0_csr.indptr.nbytes)
        matvec_started = time.perf_counter()
        full2 = np.asarray(q0_csr @ x2)
        if v28_continuation and progress_state is not None:
            progress_state["readback_matvec_seconds"]["case_2_full"] = float(
                time.perf_counter() - matvec_started
            )
            persist_v28_checkpoint()
        _drop_mmap_pages(q0_csr.data, 0, q0_csr.data.nbytes)
        _drop_mmap_pages(q0_csr.indices, 0, q0_csr.indices.nbytes)
        _drop_mmap_pages(q0_csr.indptr, 0, q0_csr.indptr.nbytes)
        x1_trace = x1.copy()
        x1_trace[trace_rows:] = 0.0
        x1_port = x1.copy()
        x1_port[:trace_rows] = 0.0
        matvec_started = time.perf_counter()
        trace_only = np.asarray(q0_csr @ x1_trace)
        if v28_continuation and progress_state is not None:
            progress_state["readback_matvec_seconds"]["case_1_trace_only"] = float(
                time.perf_counter() - matvec_started
            )
            persist_v28_checkpoint()
        _drop_mmap_pages(q0_csr.data, 0, q0_csr.data.nbytes)
        _drop_mmap_pages(q0_csr.indices, 0, q0_csr.indices.nbytes)
        _drop_mmap_pages(q0_csr.indptr, 0, q0_csr.indptr.nbytes)
        matvec_started = time.perf_counter()
        port_only = np.asarray(q0_csr @ x1_port)
        if v28_continuation and progress_state is not None:
            progress_state["readback_matvec_seconds"]["case_1_port_only"] = float(
                time.perf_counter() - matvec_started
            )
            persist_v28_checkpoint()
        _drop_mmap_pages(q0_csr.data, 0, q0_csr.data.nbytes)
        _drop_mmap_pages(q0_csr.indices, 0, q0_csr.indices.nbytes)
        _drop_mmap_pages(q0_csr.indptr, 0, q0_csr.indptr.nbytes)
        component_slices = {
            "volume": (trace_only[:trace_rows], native1["native_q0_volume"][:trace_rows], native1["native_q0_volume"][trace_rows:]),
            "minus_D": (trace_only[trace_rows:], native1["native_q0_minus_D"][trace_rows:], native1["native_q0_minus_D"][:trace_rows]),
            "C": (port_only[:trace_rows], native1["native_q0_C"][:trace_rows], native1["native_q0_C"][trace_rows:]),
            "Hhat": (port_only[trace_rows:], native1["native_q0_Hhat"][trace_rows:], native1["native_q0_Hhat"][:trace_rows]),
        }
        component_errors = {}
        for component, (actual_block, expected_block, expected_off_block) in component_slices.items():
            component_errors[component] = {
                "active_block": relative_error(actual_block, expected_block),
                "native_off_block_relative": float(
                    np.linalg.norm(expected_off_block)
                    / max(float(np.linalg.norm(native1[native_component_names[component]])), np.finfo(float).tiny)
                ),
            }
        component_sum = trace_only + port_only
        full_error_1 = relative_error(full1, native1["native_q0_total"])
        full_error_2 = relative_error(full2, native2["native_q0_total"])
        split_sum_error = relative_error(component_sum, full1)
        all_component_errors = [
            error["active_block"]["relative"]
            for error in component_errors.values()
        ] + [error["native_off_block_relative"] for error in component_errors.values()]
        readback_stem = "v28_q0_csr_readback" if v28_continuation else "v27_q0_csr_readback"
        readback_path = output_directory / f"{readback_stem}.npz"
        if readback_path.exists():
            raise FileExistsError("refusing to overwrite saved q0 CSR readback outputs")
        allocation_gate(
            "task40_v28_q0_csr_readback_persistence"
            if v28_continuation
            else "task40_v27_q0_csr_readback_persistence",
            {
                "disk_payload_bytes": int(4 * vector_bytes),
                "additional_payload_bytes": 0,
                "workspace_bytes": 4 * 1024 * 1024,
                "raw_output_vectors": ["q0_case_1_full", "q0_case_2_full", "q0_case_1_trace_only", "q0_case_1_port_only"],
                "atomic_write": True,
            },
        )
        temporary_readback = output_directory / f".{readback_stem}.tmp"
        with temporary_readback.open("xb") as stream:
            np.savez(
                stream,
                q0_case_1_full=full1,
                q0_case_2_full=full2,
                q0_case_1_trace_only=trace_only,
                q0_case_1_port_only=port_only,
            )
            stream.flush()
            os.fsync(stream.fileno())
        temporary_readback.replace(readback_path)
        readback_artifact = {
            "path": readback_path.name,
            "bytes": int(readback_path.stat().st_size),
            "sha256": _file_sha256(readback_path),
            "array_names": ["q0_case_1_full", "q0_case_2_full", "q0_case_1_trace_only", "q0_case_1_port_only"],
        }
        readback = {
            "q0_case_1_full_csr_vs_native_total": full_error_1,
            "q0_case_2_full_csr_vs_native_total": full_error_2,
            "q0_case_1_csr_trace_port_masked_components_vs_native": component_errors,
            "q0_case_1_trace_plus_port_vs_full_csr": split_sum_error,
            "relative_error_limit": 1.0e-11,
            "all_gates_passed": bool(
                max(
                    [full_error_1["relative"], full_error_2["relative"], split_sum_error["relative"], *all_component_errors],
                    default=0.0,
                ) <= 1.0e-11
            ),
            "full_csr_multiply_count": 4,
            "matvecs": [
                {"input": "q0_case_1", "kind": "full"},
                {"input": "q0_case_2", "kind": "full"},
                {"input": "q0_case_1_trace_only", "kind": "masked_trace"},
                {"input": "q0_case_1_port_only", "kind": "masked_port"},
            ],
            "csr_readback_artifact": readback_artifact,
            "component_method": "four complete q0 CSR matvecs; trace/port-only q0 case 1 inputs separate volume/-D and C/Hhat output blocks",
            "no_csr_submatrix_copies": True,
            "no_second_adapter_contribution_pass": True,
        }
        if readback["all_gates_passed"] is not True:
            raise ValueError("complete q0 CSR or component native readback exceeded 1e-11")
        operation["csr_readback"] = readback
        operation["csr_readback_artifact"] = readback_artifact
        if v28_continuation and progress_state is not None:
            progress_state["readback_parent_wall_seconds"] = float(
                time.perf_counter() - readback_started
            )
            progress_state["readback_completed"] = True
            persist_v28_checkpoint()
        operation["status"] = "PASS_COMPLETE_Q0_CSR"
        operation["classification"] = (
            "V28_COMPLETE_Q0_CSR_NATIVE_READBACK"
            if v28_continuation
            else "V27_COMPLETE_Q0_CSR_NATIVE_READBACK"
        )
        operation["csr_artifacts"] = dict(completed_manifest["csr_artifacts"])
        operation["stored_structural_slots"] = int(completed_manifest["stored_structural_slots"])
        operation["numeric_facts"] = dict(completed_manifest["numeric_pass"]["numeric_facts"])
        operation["complete_numeric_csr"] = True
        operation["factor_or_solve_built"] = False
        if v28_continuation:
            qualification_path = output_directory / "v28_q0_native_qualification.json"
            qualification = {
                "schema": "task40extra.review_v28_q0_native_qualification.v1",
                "status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK",
                "source_identity": current_identity,
                "donor_identity_sha256": donor_identity_sha,
                "campaign_window_sha256": selector["campaign_window_sha256"],
                "original_pattern_manifest": {
                    "path": str(pattern_manifest_path),
                    "sha256": os.environ["TASK40_V28_PATTERN_MANIFEST_SHA256"],
                },
                "csr_manifest_path": str(manifest_path),
                "csr_artifact_hashes": {
                    name: item.get("sha256")
                    for name, item in completed_manifest["csr_artifacts"].items()
                },
                "csr_shape": list(q0_csr.shape),
                "stored_structural_slots": int(q0_csr.nnz),
                "readback": readback,
                "readback_artifact": readback_artifact,
                "qualification_gates_passed_at": _resource_snapshot(),
            }
            if qualification_path.exists():
                raise FileExistsError("refusing to overwrite a prior V28 native qualification receipt")
            _write_json(qualification_path, qualification)
            qualification_sha = _sha256_file(qualification_path)
            completed_manifest["native_qualification"] = {
                "path": str(qualification_path),
                "sha256": qualification_sha,
                "status": qualification["status"],
                "csr_artifact_hashes": dict(qualification["csr_artifact_hashes"]),
            }
            _write_json(manifest_path, completed_manifest)
            operation["native_qualification_receipt"] = {
                "path": str(qualification_path),
                "sha256": qualification_sha,
                "status": qualification["status"],
            }
            operation["csr_manifest_sha256"] = _sha256_file(manifest_path)
            current_identity["native_qualification_sha256"] = qualification_sha
            _write_json(operation_path, operation)
        del native1, native2, component_sum, full1, full2, trace_only, port_only
        del x1, x2, x1_trace, x1_port
        del adapter, q0_map, active_lookup, local_h, row_counts, offsets
        owner_release_collected = gc.collect()
        try:
            resident_pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
            current_rss_bytes = resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            current_rss_bytes = None
        operation["saved_q0_contribution_owner_release"] = {
            "released": ["adapter", "q0_map", "active_lookup", "local_h", "row_counts", "offsets"],
            "garbage_collected_objects": int(owner_release_collected),
            "current_process_rss_bytes": current_rss_bytes,
            "task_cgroup_after_release": _task_cgroup_memory_snapshot(),
            "allocator_or_file_cache_remains_counted": True,
        }

        factor_root = output_directory / (
            "v28_q0_factor" if v28_continuation else "v27_q0_factor"
        )
        factor_checkpoint_path = factor_root / "v26_q0_factor_checkpoints.json"
        try:
            from src.solvers.task40_v10_p6_mumps import run_task40_v26_selected_q0_factor_lifecycle

            if v28_continuation:
                qualification_record = operation.get("native_qualification_receipt", {})
                qualification_record = (
                    qualification_record
                    if isinstance(qualification_record, Mapping)
                    else {}
                )
                qualification_path = Path(
                    str(qualification_record.get("path", ""))
                ).resolve()
                if (
                    not qualification_path.is_relative_to(output_directory)
                    or not qualification_path.is_file()
                    or _sha256_file(qualification_path)
                    != qualification_record.get("sha256")
                ):
                    raise ValueError("V28 factor continuation requires a matching native PASS receipt")
                qualification = json.loads(
                    qualification_path.read_text(encoding="utf-8")
                )
                if (
                    qualification.get("status")
                    != "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
                    or qualification.get("csr_artifact_hashes")
                    != {
                        name: item.get("sha256")
                        for name, item in completed_manifest["csr_artifacts"].items()
                    }
                    or qualification.get("campaign_window_sha256")
                    != selector["campaign_window_sha256"]
                ):
                    raise ValueError("V28 native PASS receipt does not qualify this CSR and window")
                current_identity["native_qualification_sha256"] = str(
                    qualification_record["sha256"]
                )

            factor_report = run_task40_v26_selected_q0_factor_lifecycle(
                q0_csr,
                allocation_gate=allocation_gate,
                checkpoint_directory=factor_root,
                current_identity=current_identity,
            )
        except _ProbeResourceBlocked as error:
            factor_report = {
                "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                "status": "RESOURCE_CONTROLLED_STOP",
                "selected_q": 0,
                "failed_stage": error.stage,
                "resource_blocker": {"stage": error.stage, **dict(error.facts), "passed": False},
                "checkpoint_path": str(factor_checkpoint_path),
                "checkpoint_sha256": _sha256_file(factor_checkpoint_path)
                if factor_checkpoint_path.is_file() else None,
            }
        except Exception as error:
            factor_report = {
                "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                "status": "FAILED_Q0_FACTOR_LIFECYCLE",
                "selected_q": 0,
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "checkpoint_path": str(factor_checkpoint_path),
                "checkpoint_sha256": _sha256_file(factor_checkpoint_path)
                if factor_checkpoint_path.is_file() else None,
            }
        operation["factor_lifecycle"] = factor_report
        operation["factor_or_solve_built"] = bool(
            factor_report.get("q_coverage", {}).get("numeric_factor_built") is True
        )
        operation["factor_checkpoint"] = {
            "path": str(factor_checkpoint_path),
            "sha256": _sha256_file(factor_checkpoint_path)
            if factor_checkpoint_path.is_file() else None,
        }
        if factor_report.get("status") == "PASS_Q0_FACTOR_PROBE_AND_RHS_SOLVE":
            operation["status"] = "PASS_COMPLETE_Q0_CSR_AND_FACTOR"
        elif factor_report.get("status") == "RESOURCE_CONTROLLED_STOP":
            operation["status"] = "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
            operation["failed_stage"] = factor_report.get("failed_stage")
            operation["resource_blocker"] = factor_report.get("resource_blocker")
        else:
            operation["status"] = "FAILED_Q0_FACTOR_LIFECYCLE"
            operation["failed_stage"] = "q0_factor_lifecycle"
            operation["failure_type"] = factor_report.get("failure_type")
            operation["failure_message"] = factor_report.get("failure_message")
    except _ProbeResourceBlocked as error:
        existing_manifest = {}
        if manifest_path.is_file():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        operation.update(
            {
                "status": (
                    "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
                    if existing_manifest.get("status") == "COMPLETE_CSR"
                    else "RESOURCE_CONTROLLED_STOP_DURING_CSR"
                    if existing_manifest
                    else "RESOURCE_CONTROLLED_STOP_BEFORE_CSR"
                ),
                "classification": (
                    "V28_LIVE_RESOURCE_ADMISSION_BLOCKED"
                    if v28_continuation
                    else "V27_LIVE_RESOURCE_ADMISSION_BLOCKED"
                ),
                "failed_stage": error.stage,
                "resource_blocker": {"stage": error.stage, **dict(error.facts), "passed": False},
                "csr_manifest_path": str(manifest_path) if manifest_path.is_file() else None,
                "csr_status": existing_manifest.get("status", "NOT_CREATED"),
                "csr_manifest_sha256": _sha256_file(manifest_path) if manifest_path.is_file() else None,
                "complete_numeric_csr": existing_manifest.get("status") == "COMPLETE_CSR",
            }
        )
    except Exception as error:
        existing_manifest = {}
        if manifest_path.is_file():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        operation.update(
            {
                "status": "FAILED_V28_Q0_CONTINUATION" if v28_continuation else "FAILED_V27_SAVED_Q0",
                "classification": (
                    "V28_EXISTING_MANIFEST_Q0_CSR_FAILED"
                    if v28_continuation
                    else "V27_SAVED_ONLY_Q0_CSR_FAILED"
                ),
                "failed_stage": operation.get("failed_stage", "saved_only_q0_csr"),
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "csr_manifest_path": str(manifest_path) if manifest_path.is_file() else None,
                "csr_status": existing_manifest.get("status", "NOT_CREATED"),
                "csr_manifest_sha256": _sha256_file(manifest_path) if manifest_path.is_file() else None,
                "complete_numeric_csr": existing_manifest.get("status") == "COMPLETE_CSR",
            }
        )

    operation["resource_gates"] = resource_gate_records()
    operation["saved_only_no_fe_or_native_rebuild"] = True
    _write_json(operation_path, operation)
    status_code = str(operation.get("status"))
    csr_built = bool(operation.get("complete_numeric_csr"))
    factor_built = bool(operation.get("factor_or_solve_built"))
    controlled = status_code.startswith(
        ("RESOURCE_CONTROLLED_STOP", "PERFORMANCE_CONTROLLED_STOP")
    )
    passed = status_code in {"PASS_COMPLETE_Q0_CSR", "PASS_COMPLETE_Q0_CSR_AND_FACTOR"}
    if passed:
        partial_status, outcome = "stage_completed", "STAGE_COMPLETED"
        completed = ["preflight", "selected_reference_q_csr"]
    elif controlled:
        partial_status = "controlled_stop"
        outcome = (
            "PERFORMANCE_CONTROLLED_STOP"
            if status_code.startswith("PERFORMANCE_CONTROLLED_STOP")
            else "RESOURCE_CONTROLLED_STOP"
        )
        completed = ["preflight", "selected_reference_q_csr"] if csr_built else ["preflight"]
    else:
        partial_status, outcome = "failed", "STAGE_FAILED"
        completed = ["preflight", "selected_reference_q_csr"] if csr_built else ["preflight"]
    operation_sha = _sha256_file(operation_path)
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": partial_status,
        "outcome": outcome,
        "classification": (
            "SELECTED_REFERENCE_Q_V28_EXISTING_MANIFEST_CONTINUATION"
            if v28_continuation
            else "SELECTED_REFERENCE_Q_V27_SAVED_ONLY_COMPLETE_CSR"
        ),
        "run_id": preflight.get("run_id"),
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": stop_stage,
        "attempted_stages": ["preflight", stop_stage],
        "completed_stages": completed,
        "failed_stage": operation.get("failed_stage") if not passed else None,
        "stage_result": {"completed_stage": stop_stage if passed else None, "probe_status": status_code},
        ("v28_q0_continuation" if v28_continuation else "v27_saved_q0_stage"): {
            "operation_path": operation_path.name,
            "operation_sha256": operation_sha,
            "operation_status": status_code,
            "operation": operation,
            "selector_path": str(selector_path),
            "selector_sha256": selector_sha,
            "donor_import_identity_sha256": donor_identity_sha,
            "resource_gates": resource_gate_records(),
        },
        "q_coverage": {
            "status": "KNOWN",
            "expected_q_count": 8,
            "built_q_count": 1 if csr_built else 0,
            "full_q_matrix_coverage": "1/8" if csr_built else "0/8",
            "selected_q": 0,
            "paired_action_q": 4,
            "csr_status": "COMPLETE_CSR" if csr_built else operation.get("csr_status", "NOT_CREATED"),
            "factor_count": int(factor_built),
            "factor_evicted_after_probe_and_rhs_solve": bool(
                operation.get("factor_lifecycle", {}).get("cleanup", {}).get("destroy_succeeded") is True
            ),
            "max_simultaneous_factors": int(
                operation.get("factor_lifecycle", {}).get("max_simultaneous_native_objects", {}).get("factors", 0)
            ),
            "ksp_created": False,
            "pde_solved": False,
            "reason": (
                "V28 imports the frozen V26 donor read-only, reuses the V27 q0 pattern and data backing, "
                "fills and qualifies only q0, and does not create a KSP, solve the target PDE, or produce official R/T/A."
                if v28_continuation
                else "V27 imports the frozen V26 donor read-only, constructs only the q0 saved-data CSR, and stops at the first live resource gate; it does not create a KSP, solve the target PDE, or produce official R/T/A."
            ),
        },
        "resource_gate": operation.get("resource_blocker") if controlled else None,
        "cleanup": {
            "status": "OPERATION_RETURNED",
            "owner_cleanup": "V28 existing-manifest continuation" if v28_continuation else "V27 saved-only stage operation",
        },
        "artifact_hashes": {
            "v20_stage_preflight.json": {
                "path": "v20_stage_preflight.json",
                "sha256": _sha256_file(output_directory / "v20_stage_preflight.json"),
            },
            operation_path.name: {"path": operation_path.name, "sha256": operation_sha},
            **(
                {
                    manifest_path.name: {
                        "path": (
                            str(manifest_path.relative_to(output_directory))
                            if manifest_path.is_relative_to(output_directory)
                            else str(manifest_path)
                        ),
                        "sha256": _sha256_file(manifest_path),
                    }
                }
                if manifest_path.is_file()
                else {}
            ),
            **(
                {
                    progress_path.name: {
                        "path": progress_path.name,
                        "sha256": _sha256_file(progress_path),
                    }
                }
                if v28_continuation and progress_path.is_file()
                else {}
            ),
            **(
                {
                    str(operation["csr_readback_artifact"]["path"]): {
                        "path": str(operation["csr_readback_artifact"]["path"]),
                        "sha256": str(operation["csr_readback_artifact"]["sha256"]),
                    }
                }
                if isinstance(operation.get("csr_readback_artifact"), Mapping)
                else {}
            ),
        },
        "official_result": False,
        "not_run": ["all other q CSR", *( [] if factor_built else ["q0 factor"] ), "KSP", "PDE", "official R/T/A"],
        "full_field_release_allowed": False,
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": passed or controlled,
        "errors": [] if passed or controlled else [str(operation.get("failure_message", status_code))],
        "official_result": False,
        "status": partial_status,
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def _run_v26_selected_q0_stage(
    resolved_payload: Mapping[str, Any],
    output_directory: Path,
    *,
    source_sha: str,
    profile: str,
    preflight: Mapping[str, Any],
    modes: tuple[Any, ...] | None,
    mode_rows: tuple[Mapping[str, Any], ...] | None,
    stop_stage: str,
) -> dict[str, Any]:
    """Execute the V26 selector's saved replay, native consumer, or CSR stage."""
    import shutil

    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.task40_v22_operator_probe import (
        _ProbeResourceBlocked,
        _resource_admission,
        _v23_actual_axis_values,
    )
    from src.solvers.task40_v25_selected_q0 import (
        _task_cgroup_memory_snapshot,
        run_task40_v25_selected_q0_consumer,
        run_task40_v26_saved_stream_replay,
    )

    if modes is None or mode_rows is None:
        raise RuntimeError("V26 route requires the complete frozen preflight mode inventory")
    expected_operation = {
        "selected_reference_q_build_only": "V26_SAVED_STREAM_REPLAY",
        "selected_reference_q_consumer": "V26_SAVED_STREAM_NATIVE_CONSUMER",
        "selected_reference_q_csr": "V26_COMPLETE_Q0_CSR_AND_CONDITIONAL_FACTOR",
    }.get(stop_stage)
    selector_path = Path(os.environ.get("TASK40_V26_SELECTOR_PATH", "")).resolve()
    selector_sha = os.environ.get("TASK40_V26_SELECTOR_SHA256", "")
    producer_root = Path(os.environ.get("TASK40_V26_PRODUCER_ROOT", "")).resolve()
    raw_operation = os.environ.get("TASK40_V26_OPERATION", "")
    if (
        expected_operation is None
        or not selector_path.is_file()
        or len(selector_sha) != 64
        or _sha256_file(selector_path) != selector_sha
        or raw_operation != expected_operation
    ):
        raise RuntimeError("V26 stage lacks its exact service-bound selector operation")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    producer_identity = selector.get("producer_identity")
    inventory = preflight.get("target_mode_inventory")
    if not isinstance(producer_identity, Mapping) or not isinstance(inventory, Mapping):
        raise RuntimeError("V26 selector or preflight omits its frozen producer/mode identity")
    if (
        selector.get("schema") != "task40extra.review_v26_selected_operation.v1"
        or selector.get("operation") != expected_operation
        or selector.get("stop_stage") != stop_stage
        or selector.get("model_profile") != profile
        or selector.get("input_sha256") != preflight.get("input_sha256")
        or producer_identity.get("producer_run_directory") is None
    ):
        raise RuntimeError("V26 selector identity differs from the service-verified stage input")
    mode_sha = inventory.get("mode_manifest_sha256")
    key_sha = inventory.get("ordered_mode_key_sha256")
    if not isinstance(mode_sha, str) or len(mode_sha) != 64 or not isinstance(key_sha, str) or len(key_sha) != 64:
        raise RuntimeError("V26 route has no complete frozen mode-manifest/key identity")

    repo_root = Path(__file__).resolve().parents[2]
    artifact_root = (repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl").resolve()
    replay_root = artifact_root / "saved_replay"
    native_root = artifact_root / "native_consumer"
    replay_root.mkdir(parents=True, exist_ok=True)
    native_root.mkdir(parents=True, exist_ok=True)
    if producer_root != (repo_root / str(producer_identity.get("producer_run_directory"))).resolve():
        raise RuntimeError("V26 producer root differs from its service-bound producer identity")

    resource_gates: list[dict[str, Any]] = []
    disk_reserve_bytes = 1024**3
    disk_root = replay_root if stop_stage == "selected_reference_q_build_only" else output_directory

    def allocation_gate(stage: str, facts: Mapping[str, Any]) -> dict[str, Any]:
        requested = sum(
            int(facts.get(key, 0))
            for key in (
                "additional_payload_bytes",
                "matrix_payload_bytes",
                "workspace_bytes",
                "future_co_resident_reserve_bytes",
            )
        )
        sample_task_memory = stage == "task40_v25_selected_q0_pre_fe_and_surface_phase"
        task_memory_before = _task_cgroup_memory_snapshot() if sample_task_memory else None
        try:
            memory = _resource_admission(
                stage,
                requested,
                resource_sample=_resource_snapshot,
                require_task_cgroup=True,
            )
        except _ProbeResourceBlocked as error:
            if sample_task_memory:
                error.facts["task_cgroup_memory_samples"] = {
                    "phase": stage,
                    "before": task_memory_before,
                    "after": _task_cgroup_memory_snapshot(),
                }
            raise
        disk_required = int(facts.get("disk_payload_bytes", 0))
        disk_free = int(shutil.disk_usage(disk_root).free)
        disk_passed = disk_free >= disk_required + disk_reserve_bytes
        record = {
            **memory,
            "disk_payload_bytes": disk_required,
            "disk_free_bytes": disk_free,
            "disk_reserve_bytes": disk_reserve_bytes,
            "disk_gate_passed": disk_passed,
            "request_facts": dict(facts),
        }
        if sample_task_memory:
            record["task_cgroup_memory_samples"] = {
                "phase": stage,
                "before": task_memory_before,
                "after": _task_cgroup_memory_snapshot(),
            }
        resource_gates.append(record)
        if not disk_passed:
            blocker = {
                "stage": stage,
                "additional_object_upper_bound_bytes": requested,
                "disk_payload_bytes": disk_required,
                "disk_free_bytes": disk_free,
                "disk_reserve_bytes": disk_reserve_bytes,
                "disk_gate_passed": False,
                "passed": False,
            }
            raise _ProbeResourceBlocked(stage, blocker)
        return record

    def resident_csr_admission(stage: str, payload_bytes: int) -> Mapping[str, Any]:
        return allocation_gate(stage, {"additional_payload_bytes": int(payload_bytes)})

    current_identity = {
        "source_sha": source_sha,
        "run_id": preflight.get("run_id"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "campaign_window_sha256": selector.get("campaign_window_sha256"),
        "producer_identity_sha256": hashlib.sha256(
            json.dumps(
                producer_identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "mode_manifest_sha256": mode_sha,
        "ordered_mode_key_sha256": key_sha,
    }
    operation_path = output_directory / "v26_selected_q_stage.json"
    operation: dict[str, Any]
    replay_manifest: Mapping[str, Any] | None = None
    try:
        if stop_stage == "selected_reference_q_build_only":
            replay_manifest = run_task40_v26_saved_stream_replay(
                simulation_config_3d_from_normalized(resolved_payload),
                _v23_actual_axis_values(resolved_payload),
                producer_root=producer_root,
                producer_identity=producer_identity,
                output_directory=replay_root,
                allocation_gate=allocation_gate,
                frozen_modes=modes,
                frozen_mode_rows=mode_rows,
                frozen_mode_manifest_sha256=mode_sha,
                expected_ordered_mode_key_sha256=key_sha,
                current_identity=current_identity,
            )
            operation = {
                "schema": "task40extra.review_v26_selected_q_stage.v1",
                "status": str(replay_manifest.get("status", "FAILED")),
                "classification": str(replay_manifest.get("classification", "V26_SAVED_STREAM_REPLAY")),
                "official_result": False,
                "stop_stage": stop_stage,
                "selector_sha256": selector_sha,
                "current_identity": current_identity,
                "mode_inventory": {
                    "mode_count_full_reference": replay_manifest.get("mode_count_full_reference"),
                    "q0_alias_count": replay_manifest.get("q0_alias_count"),
                    "q4_alias_count": replay_manifest.get("q4_alias_count"),
                    "selected_twist_alias_count": replay_manifest.get("selected_twist_alias_count"),
                },
                "saved_replay_root": str(replay_root),
                "saved_replay_manifest_path": str(replay_root / "v26_saved_q_replay_manifest.json"),
                "saved_replay_manifest_sha256": replay_manifest.get("manifest_sha256"),
                "saved_replay": dict(replay_manifest),
                "factor_or_solve_built": False,
            }
        else:
            replay_manifest_path = replay_root / "v26_saved_q_replay_manifest.json"
            if not replay_manifest_path.is_file():
                replay_manifest = run_task40_v26_saved_stream_replay(
                    simulation_config_3d_from_normalized(resolved_payload),
                    _v23_actual_axis_values(resolved_payload),
                    producer_root=producer_root,
                    producer_identity=producer_identity,
                    output_directory=replay_root,
                    allocation_gate=allocation_gate,
                    frozen_modes=modes,
                    frozen_mode_rows=mode_rows,
                    frozen_mode_manifest_sha256=mode_sha,
                    expected_ordered_mode_key_sha256=key_sha,
                    current_identity=current_identity,
                )
            replay_sha = _sha256_file(replay_manifest_path)
            replay_binding = {
                "producer_identity": dict(producer_identity),
                "producer_identity_sha256": current_identity["producer_identity_sha256"],
                "saved_replay_root": str(replay_root),
                "saved_replay_manifest_path": str(replay_manifest_path),
                "saved_replay_manifest_sha256": replay_sha,
            }
            native_manifest_path = native_root / "v26_native_action_manifest.json"
            native_manifest: Mapping[str, Any] = {}
            try:
                native_manifest = json.loads(native_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            reuse_native = bool(
                native_manifest.get("schema") == "task40extra.review_v26_native_action.v1"
                and native_manifest.get("status") == "PASS_COMPLETE_Q0_NATIVE_CONSUMER"
                and native_manifest.get("current_identity") == current_identity
                and native_manifest.get("saved_replay_manifest_sha256") == replay_sha
                and native_manifest.get("native_volume_apply_count") == 6
                and native_manifest.get("provider_sweep_count") == 9
            )
            native_recovery_binding: dict[str, Any] | None = None
            if (
                not reuse_native
                and not native_manifest_path.exists()
                and stop_stage == "selected_reference_q_csr"
                and all((native_root / f"v26_native_{name}.npz").is_file()
                        and (native_root / f"v26_native_{name}.json").is_file()
                        for name in ("q0_case_1", "q0_case_2", "q4_pair"))
            ):
                freeze_path = artifact_root / "main_source_freeze_receipt_v26_reader_fix.json"
                freeze_receipt = json.loads(freeze_path.read_text(encoding="utf-8"))
                prior_attempt = _find_v26_minus_d_failed_attempt(
                    output_directory.parent,
                    source_sha=str(freeze_receipt.get("source_sha", "")),
                    run_id=str(preflight.get("run_id", "")),
                    input_sha256=str(preflight.get("input_sha256", "")),
                    physical_model_sha256=str(preflight.get("physical_model_sha256", "")),
                )
                from scripts.task40_v20_service_workflow import _v26_native_case_recovery_readback

                checker_receipt = _v26_native_case_recovery_readback(
                    repo_root=repo_root,
                    native_root=native_root,
                    replay_root=replay_root,
                    prior_attempt_root=prior_attempt,
                    recovery_identity=current_identity,
                    expected_run_id=str(preflight.get("run_id", "")),
                    expected_input_sha256=str(preflight.get("input_sha256", "")),
                    expected_physical_model_sha256=str(preflight.get("physical_model_sha256", "")),
                )
                source_tag = str(source_sha)
                checker_receipt_path = native_root / f"v26_native_action_recovery_check_{source_tag}.json"
                recovery_manifest_path = native_root / f"v26_native_action_recovery_{source_tag}.json"
                if checker_receipt_path.exists() or recovery_manifest_path.exists():
                    raise FileExistsError("refusing to overwrite V26 native recovery evidence")
                _write_json(checker_receipt_path, checker_receipt)
                checker_sha = _sha256_file(checker_receipt_path)
                recovery_manifest = {
                    "schema": "task40extra.review_v26_native_action_recovery.v1",
                    "status": "PASS_RECOVERED_THREE_NATIVE_CASES",
                    "official_result": False,
                    "producer_identity_sha256": current_identity["producer_identity_sha256"],
                    "saved_replay_manifest_sha256": replay_sha,
                    "native_current_identity": checker_receipt["original_native_current_identity"],
                    "recovery_current_identity": dict(current_identity),
                    "cases": checker_receipt["native_cases"],
                    "native_volume_apply_count": None,
                    "provider_sweep_count": None,
                    "count_provenance": {
                        "native_volume_apply_count": "SOURCE_DERIVED",
                        "provider_sweep_count": "SOURCE_DERIVED",
                    },
                    "source_derived_counts": checker_receipt["historical_native_counts"],
                    "elapsed_seconds": None,
                    "elapsed_seconds_status": "UNKNOWN_NOT_PERSISTED_BEFORE_KEYERROR",
                    "recomputed_comparisons": checker_receipt["recomputed_comparisons"],
                    "recomputed_scaled_leakage": checker_receipt["recomputed_scaled_leakage"],
                    "recovery_checker_receipt_path": str(checker_receipt_path),
                    "recovery_checker_receipt_sha256": checker_sha,
                    "prior_failed_attempt": checker_receipt["prior_failed_attempt"],
                    "fresh_surface_integration": checker_receipt["fresh_surface_integration"],
                }
                _write_json(recovery_manifest_path, recovery_manifest)
                native_manifest_path = recovery_manifest_path
                native_manifest = recovery_manifest
                reuse_native = True
                native_recovery_binding = {
                    "status": checker_receipt["status"],
                    "manifest_path": str(recovery_manifest_path),
                    "manifest_sha256": _sha256_file(recovery_manifest_path),
                    "checker_receipt_path": str(checker_receipt_path),
                    "checker_receipt_sha256": checker_sha,
                    "native_evidence_source_sha": checker_receipt["source_sha_split"]["native_evidence_source_sha"],
                    "recovery_source_sha": source_sha,
                }
            native_artifact_binding: dict[str, Any] | None = None
            if reuse_native:
                native_artifact_binding = {
                    **replay_binding,
                    "native_root": str(native_root),
                    "native_manifest_path": str(native_manifest_path),
                    "native_manifest_sha256": _sha256_file(native_manifest_path),
                    "native_volume_apply_count": native_manifest.get("native_volume_apply_count"),
                    "provider_sweep_count": native_manifest.get("provider_sweep_count"),
                    "native_count_provenance": native_manifest.get("count_provenance", {}),
                    "source_derived_counts": native_manifest.get("source_derived_counts", {}),
                    "native_action_elapsed_seconds": native_manifest.get("elapsed_seconds"),
                    "native_action_elapsed_seconds_status": native_manifest.get(
                        "elapsed_seconds_status",
                        "MEASURED" if native_manifest.get("elapsed_seconds") is not None else "UNKNOWN",
                    ),
                }
            operation = run_task40_v25_selected_q0_consumer(
                simulation_config_3d_from_normalized(resolved_payload),
                _v23_actual_axis_values(resolved_payload),
                output_directory=output_directory,
                allocation_gate=allocation_gate,
                resident_csr_admission=None,
                frozen_modes=modes,
                frozen_mode_rows=mode_rows,
                frozen_mode_manifest_sha256=mode_sha,
                expected_ordered_mode_key_sha256=key_sha,
                physical_model_sha256=str(preflight.get("physical_model_sha256")),
                build_csr=stop_stage == "selected_reference_q_csr",
                structure_checkpoint_path=(
                    output_directory / "v26_q0_preallocation_row_structure.npz"
                    if stop_stage == "selected_reference_q_csr"
                    else None
                ),
                structure_checkpoint_identity=current_identity,
                saved_producer_root=producer_root,
                saved_producer_identity=producer_identity,
                saved_replay_root=replay_root,
                native_output_root=native_root,
                saved_native_root=native_root if reuse_native else None,
                saved_native_manifest_path=native_manifest_path if reuse_native else None,
                current_identity=current_identity,
                perform_native_validation=not reuse_native,
            )
            existing_binding = operation.get("v26_artifact_binding")
            if not isinstance(existing_binding, Mapping):
                if native_artifact_binding is not None:
                    existing_binding = native_artifact_binding
                else:
                    try:
                        native_facts = json.loads(native_manifest_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        native_facts = {}
                    existing_binding = {
                        **replay_binding,
                        "native_root": str(native_root),
                        "native_manifest_path": str(native_manifest_path),
                        "native_manifest_sha256": (
                            _sha256_file(native_manifest_path) if native_manifest_path.is_file() else ""
                        ),
                        "native_volume_apply_count": native_facts.get("native_volume_apply_count"),
                        "provider_sweep_count": native_facts.get("provider_sweep_count"),
                        "native_count_provenance": native_facts.get("count_provenance", {}),
                        "source_derived_counts": native_facts.get("source_derived_counts", {}),
                        "native_action_elapsed_seconds": native_facts.get("elapsed_seconds"),
                        "native_action_elapsed_seconds_status": native_facts.get(
                            "elapsed_seconds_status",
                            "MEASURED" if native_facts.get("elapsed_seconds") is not None else "UNKNOWN",
                        ),
                    }
            elif native_artifact_binding is not None:
                existing_binding = {**native_artifact_binding, **dict(existing_binding)}
            operation = {
                **dict(operation),
                "v26_artifact_binding": dict(existing_binding),
                "stop_stage": stop_stage,
                "v26_selector_sha256": selector_sha,
                "v26_operation": expected_operation,
                "v26_current_identity": current_identity,
                "v26_replay_created_in_this_operation": replay_manifest is not None,
                "v26_native_reused_from_prior_operation": reuse_native,
                **({"v26_native_recovery": native_recovery_binding} if native_recovery_binding else {}),
            }
            if stop_stage == "selected_reference_q_csr" and operation.get("status") == "PASS_COMPLETE_Q0_CSR":
                import numpy as np
                from scipy import sparse

                from src.solvers.task40_v10_p6_mumps import (
                    run_task40_v26_selected_q0_factor_lifecycle,
                )

                tile_store = operation.get("row_tile_store", {})
                tile_store = tile_store if isinstance(tile_store, Mapping) else {}
                matrix_identity = operation.get("matrix_identity", {})
                matrix_identity = matrix_identity if isinstance(matrix_identity, Mapping) else {}
                files = tile_store.get("files", {})
                files = files if isinstance(files, Mapping) else {}
                shape = tuple(map(int, tile_store.get("shape", ())))
                nnz = int(tile_store.get("nnz", -1))
                payload_bytes = int(matrix_identity.get("csr_payload_bytes", -1))
                if (
                    len(shape) != 2
                    or shape[0] <= 0
                    or shape[0] != shape[1]
                    or nnz < 0
                    or payload_bytes <= 0
                    or set(("data", "indices", "indptr")) - set(files)
                ):
                    raise RuntimeError("V26 completed q0 CSR omits its complete row-tile identity")
                structure_path = output_directory / "v26_q0_preallocation_row_structure.npz"
                structure_manifest_path = structure_path.with_suffix(".json")
                structure_record = operation.get("preallocation_row_structure", {})
                structure_record = structure_record if isinstance(structure_record, Mapping) else {}
                structure_artifact = structure_record.get("array_artifact", {})
                structure_artifact = structure_artifact if isinstance(structure_artifact, Mapping) else {}
                if (
                    not structure_path.is_file()
                    or not structure_manifest_path.is_file()
                    or structure_artifact.get("sha256") != _sha256_file(structure_path)
                    or structure_artifact.get("path") != structure_path.name
                ):
                    raise RuntimeError("V26 pre-CSR int64 row-count/offset checkpoint failed identity readback")
                with np.load(structure_path, allow_pickle=False) as structure_archive:
                    if set(structure_archive.files) != {"row_counts_int64", "wide_offsets_int64"}:
                        raise RuntimeError("V26 pre-CSR structure checkpoint lacks both int64 arrays")
                    row_counts_wide = np.asarray(structure_archive["row_counts_int64"])
                    wide_offsets = np.asarray(structure_archive["wide_offsets_int64"])
                    if (
                        row_counts_wide.dtype != np.dtype(np.int64)
                        or wide_offsets.dtype != np.dtype(np.int64)
                        or row_counts_wide.shape != (shape[0],)
                        or wide_offsets.shape != (shape[0] + 1,)
                        or int(wide_offsets[0]) != 0
                        or int(wide_offsets[-1]) != nnz
                        or np.any(row_counts_wide < 0)
                        or np.any(wide_offsets[1:] < wide_offsets[:-1])
                        or int(max(shape[0], nnz, int(np.max(wide_offsets, initial=0)))) > np.iinfo(np.int32).max
                    ):
                        raise RuntimeError("V26 q0 pre-CSR wide structure failed int32-capacity verification")
                allocation_gate("task40_v26_q0_factor_csr_input_retention", {
                    "additional_payload_bytes": payload_bytes,
                    "matrix_payload_bytes": 0,
                    "workspace_bytes": 0,
                    "future_co_resident_reserve_bytes": 0,
                    "disk_payload_bytes": 0,
                    "selected_q": 0,
                    "source_csr_payload_bytes_to_retain": payload_bytes,
                    "row_count": shape[0],
                    "nnz": nnz,
                    "wide_int64_structure_checkpoint_sha256": _sha256_file(structure_path),
                    "wide_structure_checked_before_int32_csr_readback": True,
                })
                loaded_arrays: dict[str, np.ndarray] = {}
                for name in ("indptr", "indices", "data"):
                    item = files[name]
                    if not isinstance(item, Mapping):
                        raise RuntimeError(f"V26 q0 CSR file record is malformed: {name}")
                    path = (output_directory / str(item.get("path", ""))).resolve()
                    if (
                        not path.is_relative_to(output_directory.resolve())
                        or not path.is_file()
                        or path.stat().st_size != item.get("bytes")
                        or _sha256_file(path) != item.get("sha256")
                    ):
                        raise RuntimeError(f"V26 q0 CSR file hash failed readback: {name}")
                    loaded_arrays[name] = np.load(path, allow_pickle=False)
                indptr = loaded_arrays["indptr"]
                indices = loaded_arrays["indices"]
                data = loaded_arrays["data"]
                if (
                    indptr.dtype != np.dtype(np.int32)
                    or indices.dtype != np.dtype(np.int32)
                    or data.dtype != np.dtype(np.complex128)
                    or indptr.shape != (shape[0] + 1,)
                    or indices.shape != (nnz,)
                    or data.shape != (nnz,)
                    or int(indptr[0]) != 0
                    or int(indptr[-1]) != nnz
                    or not np.array_equal(np.diff(indptr).astype(np.int64), row_counts_wide)
                    or not np.array_equal(indptr.astype(np.int64), wide_offsets)
                ):
                    raise RuntimeError("V26 q0 CSR arrays differ from the full wide pre-CSR row structure")
                q0_csr = sparse.csr_matrix((data, indices, indptr), shape=shape, copy=False)
                if not q0_csr.has_canonical_format or not q0_csr.has_sorted_indices:
                    raise RuntimeError("V26 q0 saved CSR is not canonical sorted CSR")
                factor_checkpoint_root = output_directory / "v26_q0_factor"
                factor_checkpoint_root.mkdir(parents=True, exist_ok=True)
                factor_checkpoint_path = factor_checkpoint_root / "v26_q0_factor_checkpoints.json"
                try:
                    factor_report = run_task40_v26_selected_q0_factor_lifecycle(
                        q0_csr,
                        allocation_gate=allocation_gate,
                        checkpoint_directory=factor_checkpoint_root,
                        current_identity=current_identity,
                    )
                except _ProbeResourceBlocked as error:
                    factor_report = {
                        "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                        "status": "RESOURCE_CONTROLLED_STOP",
                        "selected_q": 0,
                        "failed_stage": error.stage,
                        "resource_blocker": {"stage": error.stage, **dict(error.facts), "passed": False},
                        "checkpoint_path": str(factor_checkpoint_path),
                        "checkpoint_sha256": _sha256_file(factor_checkpoint_path)
                        if factor_checkpoint_path.is_file() else None,
                    }
                except Exception as error:
                    factor_report = {
                        "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                        "status": "FAILED_Q0_FACTOR_LIFECYCLE",
                        "selected_q": 0,
                        "failure_type": type(error).__name__,
                        "failure_message": str(error),
                        "checkpoint_path": str(factor_checkpoint_path),
                        "checkpoint_sha256": _sha256_file(factor_checkpoint_path)
                        if factor_checkpoint_path.is_file() else None,
                    }
                finally:
                    del q0_csr, loaded_arrays, indptr, indices, data, row_counts_wide, wide_offsets
                factor_report = dict(factor_report)
                operation["factor_lifecycle"] = factor_report
                operation["factor_or_solve_built"] = bool(
                    factor_report.get("q_coverage", {}).get("numeric_factor_built") is True
                )
                operation["ksp_created"] = False
                operation["pde_solved"] = False
                operation["factor_checkpoint"] = {
                    "path": str(factor_checkpoint_path),
                    "sha256": _sha256_file(factor_checkpoint_path)
                    if factor_checkpoint_path.is_file() else None,
                }
                if factor_report.get("status") == "PASS_Q0_FACTOR_PROBE_AND_RHS_SOLVE":
                    operation["status"] = "PASS_COMPLETE_Q0_CSR_AND_FACTOR"
                elif factor_report.get("status") == "RESOURCE_CONTROLLED_STOP":
                    operation["status"] = "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
                    operation["failed_stage"] = factor_report.get("failed_stage")
                    operation["resource_blocker"] = factor_report.get("resource_blocker")
                else:
                    operation["status"] = "FAILED_Q0_FACTOR_LIFECYCLE"
                    operation["failed_stage"] = "q0_factor_lifecycle"
                    operation["failure_type"] = factor_report.get("failure_type", "RuntimeError")
                    operation["failure_message"] = factor_report.get("failure_message", "q0 factor lifecycle failed")
                operation["csr_structure_checkpoint"] = {
                    "path": structure_path.name,
                    "sha256": _sha256_file(structure_path),
                    "manifest_path": structure_manifest_path.name,
                    "manifest_sha256": _sha256_file(structure_manifest_path),
                    "wide_int64_rows_and_offsets_preserved": True,
                }
    except _ProbeResourceBlocked as error:
        previous = locals().get("operation")
        if stop_stage == "selected_reference_q_csr" and isinstance(previous, Mapping) and previous.get("status") == "PASS_COMPLETE_Q0_CSR":
            factor_checkpoint_root = output_directory / "v26_q0_factor"
            factor_checkpoint_root.mkdir(parents=True, exist_ok=True)
            factor_checkpoint_path = factor_checkpoint_root / "v26_q0_factor_checkpoints.json"
            if not factor_checkpoint_path.is_file():
                _write_json(factor_checkpoint_path, {
                    "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                    "status": "RESOURCE_CONTROLLED_STOP",
                    "current_identity": current_identity,
                    "selected_q": 0,
                    "factor_route": "V26_SELECTED_Q0_ONLY; no fabricated q_count=1 profile",
                    "q_coverage": {"numeric_factor_attempted": False, "numeric_factor_built": False},
                    "resource_gates": [{"stage": error.stage, "request_facts": {}, "admission": None}],
                    "cleanup": {
                        "status": "NOT_STARTED",
                        "destroy_succeeded": True,
                        "native_object_counts_after_destroy": {
                            "matrices_current": 0, "factors_current": 0, "vectors_current": 0,
                        },
                    },
                    "failure": {"type": type(error).__name__, "message": str(error)},
                })
            operation = {
                **dict(previous),
                "status": "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR",
                "failed_stage": error.stage,
                "resource_blocker": {"stage": error.stage, **dict(error.facts), "passed": False},
                "factor_lifecycle": {
                    "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                    "status": "RESOURCE_CONTROLLED_STOP",
                    "selected_q": 0,
                    "resource_blocker": {"stage": error.stage, **dict(error.facts), "passed": False},
                    "checkpoint_path": str(factor_checkpoint_path.resolve()),
                    "checkpoint_sha256": _sha256_file(factor_checkpoint_path),
                },
                "factor_checkpoint": {
                    "path": str(factor_checkpoint_path.resolve()),
                    "sha256": _sha256_file(factor_checkpoint_path),
                },
                "csr_structure_checkpoint": {
                    "path": "v26_q0_preallocation_row_structure.npz",
                    "sha256": _sha256_file(output_directory / "v26_q0_preallocation_row_structure.npz"),
                    "manifest_path": "v26_q0_preallocation_row_structure.json",
                    "manifest_sha256": _sha256_file(output_directory / "v26_q0_preallocation_row_structure.json"),
                    "wide_int64_rows_and_offsets_preserved": True,
                },
                "factor_or_solve_built": False,
                "ksp_created": False,
                "pde_solved": False,
            }
        else:
            operation = {
                "schema": "task40extra.review_v26_selected_q_stage.v1",
                "status": "RESOURCE_CONTROLLED_STOP",
                "classification": "V26_LIVE_RESOURCE_ADMISSION_BLOCKED",
                "official_result": False,
                "stop_stage": stop_stage,
                "selector_sha256": selector_sha,
                "failed_stage": error.stage,
                "resource_blocker": {**dict(error.facts), "passed": False},
                "factor_or_solve_built": False,
            }
        replay_binding = locals().get("replay_binding")
        native_artifact_binding = locals().get("native_artifact_binding")
        operation = _retain_v26_footer_bindings(
            operation,
            artifact_binding=(
                native_artifact_binding
                if isinstance(native_artifact_binding, Mapping)
                else replay_binding if isinstance(replay_binding, Mapping) else None
            ),
            recovery_binding=locals().get("native_recovery_binding"),
            current_identity=locals().get("current_identity"),
        )
    except Exception as error:
        previous = locals().get("operation")
        if stop_stage == "selected_reference_q_csr" and isinstance(previous, Mapping) and previous.get("status") == "PASS_COMPLETE_Q0_CSR":
            factor_checkpoint_root = output_directory / "v26_q0_factor"
            factor_checkpoint_root.mkdir(parents=True, exist_ok=True)
            factor_checkpoint_path = factor_checkpoint_root / "v26_q0_factor_checkpoints.json"
            if not factor_checkpoint_path.is_file():
                _write_json(factor_checkpoint_path, {
                    "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                    "status": "FAILED_Q0_FACTOR_LIFECYCLE",
                    "current_identity": current_identity,
                    "selected_q": 0,
                    "factor_route": "V26_SELECTED_Q0_ONLY; no fabricated q_count=1 profile",
                    "q_coverage": {"numeric_factor_attempted": False, "numeric_factor_built": False},
                    "cleanup": {
                        "status": "NOT_STARTED",
                        "destroy_succeeded": True,
                        "native_object_counts_after_destroy": {
                            "matrices_current": 0, "factors_current": 0, "vectors_current": 0,
                        },
                    },
                    "failure": {"type": type(error).__name__, "message": str(error)},
                })
            factor_report = {
                "schema": "task40extra.review_v26_selected_q0_factor_lifecycle.v1",
                "status": "FAILED_Q0_FACTOR_LIFECYCLE",
                "selected_q": 0,
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "checkpoint_path": str(factor_checkpoint_path.resolve()),
                "checkpoint_sha256": _sha256_file(factor_checkpoint_path),
            }
            operation = {
                **dict(previous),
                "status": "FAILED_Q0_FACTOR_LIFECYCLE",
                "failed_stage": "q0_factor_lifecycle",
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "factor_lifecycle": factor_report,
                "factor_checkpoint": {
                    "path": str(factor_checkpoint_path.resolve()),
                    "sha256": _sha256_file(factor_checkpoint_path),
                },
                "csr_structure_checkpoint": {
                    "path": "v26_q0_preallocation_row_structure.npz",
                    "sha256": _sha256_file(output_directory / "v26_q0_preallocation_row_structure.npz"),
                    "manifest_path": "v26_q0_preallocation_row_structure.json",
                    "manifest_sha256": _sha256_file(output_directory / "v26_q0_preallocation_row_structure.json"),
                    "wide_int64_rows_and_offsets_preserved": True,
                },
                "factor_or_solve_built": False,
                "ksp_created": False,
                "pde_solved": False,
            }
        else:
            operation = {
                "schema": "task40extra.review_v26_selected_q_stage.v1",
                "status": "FAILED_V26_SELECTED_Q_GATES",
                "classification": "V26_SELECTED_Q_OPERATION_FAILED",
                "official_result": False,
                "stop_stage": stop_stage,
                "selector_sha256": selector_sha,
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "factor_or_solve_built": False,
            }
        replay_binding = locals().get("replay_binding")
        native_artifact_binding = locals().get("native_artifact_binding")
        operation = _retain_v26_footer_bindings(
            operation,
            artifact_binding=(
                native_artifact_binding
                if isinstance(native_artifact_binding, Mapping)
                else replay_binding if isinstance(replay_binding, Mapping) else None
            ),
            recovery_binding=locals().get("native_recovery_binding"),
            current_identity=locals().get("current_identity"),
        )
    _write_json(operation_path, operation)

    op_status = str(operation.get("status", "FAILED_V26_SELECTED_Q_GATES"))
    controlled = op_status == "RESOURCE_CONTROLLED_STOP" or (
        stop_stage == "selected_reference_q_csr"
        and op_status == "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT"
    )
    passed = (
        op_status == "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        if stop_stage == "selected_reference_q_build_only"
        else op_status in {"PASS_COMPLETE_Q0_STREAM", "PASS_COMPLETE_Q0_CSR", "PASS_COMPLETE_Q0_CSR_AND_FACTOR"}
        if stop_stage == "selected_reference_q_csr"
        else op_status == "PASS_COMPLETE_Q0_STREAM"
    )
    factor_status = operation.get("factor_lifecycle", {})
    factor_status = factor_status if isinstance(factor_status, Mapping) else {}
    csr_built = op_status in {
        "PASS_COMPLETE_Q0_CSR",
        "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
        "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR",
        "FAILED_Q0_FACTOR_LIFECYCLE",
    }
    csr_retained_controlled = (
        stop_stage == "selected_reference_q_csr"
        and op_status == "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
    )
    if passed:
        status, outcome = "stage_completed", "STAGE_COMPLETED"
        completed = ["preflight", stop_stage]
    elif controlled or csr_retained_controlled:
        status, outcome = "controlled_stop", "RESOURCE_CONTROLLED_STOP"
        completed = (
            ["preflight", "selected_reference_q_consumer", "selected_reference_q_csr"]
            if csr_retained_controlled
            else ["preflight", "selected_reference_q_consumer"]
            if stop_stage == "selected_reference_q_csr" and op_status != "RESOURCE_CONTROLLED_STOP"
            else ["preflight"]
        )
    elif csr_built:
        status, outcome = "failed", "STAGE_FAILED"
        completed = ["preflight", "selected_reference_q_consumer", "selected_reference_q_csr"]
    else:
        status, outcome = "failed", "STAGE_FAILED"
        completed = ["preflight"]

    operation_sha = _sha256_file(operation_path)
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": status,
        "outcome": outcome,
        "classification": (
            "SELECTED_REFERENCE_Q_V26_SAVED_STREAM_REPLAY"
            if stop_stage == "selected_reference_q_build_only"
            else "SELECTED_REFERENCE_Q_V26_NATIVE_CONSUMER"
            if stop_stage == "selected_reference_q_consumer"
            else "SELECTED_REFERENCE_Q_V26_COMPLETE_CSR"
        ),
        "run_id": preflight.get("run_id"),
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": stop_stage,
        "attempted_stages": ["preflight", stop_stage],
        "completed_stages": completed,
        "failed_stage": operation.get("failed_stage") if status == "failed" else None,
        "stage_result": {"completed_stage": stop_stage if passed else None, "probe_status": op_status},
        "v26_selected_q_stage": {
            "operation_path": operation_path.name,
            "operation_sha256": operation_sha,
            "operation_status": op_status,
            "operation": operation,
            "selector_path": str(selector_path),
            "selector_sha256": selector_sha,
            "producer_root": str(producer_root),
            "saved_replay_root": str(replay_root),
            "native_root": str(native_root),
            "resource_gates": resource_gates,
        },
        "q_coverage": {
            "status": "KNOWN",
            "expected_q_count": 8,
            "built_q_count": 1 if csr_built else 0,
            "full_q_matrix_coverage": "1/8" if csr_built else "0/8",
            "complete_streamed_consumer_count": int(
                stop_stage != "selected_reference_q_build_only"
                and isinstance(operation.get("complete_stream"), Mapping)
            ),
            "selected_q": 0,
            "paired_action_q": 4,
            "csr_status": "BUILT" if csr_built else "NOT_BUILT",
            "factor_count": int(factor_status.get("q_coverage", {}).get("numeric_factor_built") is True),
            "factor_evicted_after_probe_and_rhs_solve": bool(
                factor_status.get("cleanup", {}).get("destroy_succeeded") is True
            ),
            "max_simultaneous_factors": int(
                factor_status.get("max_simultaneous_native_objects", {}).get("factors", 0)
            ),
            "ksp_created": False,
            "pde_solved": False,
            "reason": "V26 replays saved q0/q4 streams, validates native q0/q4 actions, builds only q0 CSR, and runs a fresh-probe plus one nonzero-RHS factor lifecycle only when all resource gates admit it; no KSP, PDE, or official R/T/A is produced.",
        },
        "resource_gate": operation.get("resource_blocker") if controlled else None,
        "cleanup": {"status": "OPERATION_RETURNED", "owner_cleanup": "V26 stage operation finally block"},
        "artifact_hashes": {
            "v20_stage_preflight.json": {
                "path": "v20_stage_preflight.json",
                "sha256": _sha256_file(output_directory / "v20_stage_preflight.json"),
            },
            "v26_selected_q_stage.json": {
                "path": operation_path.name,
                "sha256": operation_sha,
            },
        },
        "official_result": False,
        "not_run": [
            "all other q CSR",
            *( [] if factor_status.get("q_coverage", {}).get("numeric_factor_built") is True else ["q0 factor"] ),
            "KSP", "PDE", "official R/T/A",
        ],
        "full_field_release_allowed": False,
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": passed or controlled,
        "errors": [] if passed or controlled else [str(operation.get("failure_message", op_status))],
        "official_result": False,
        "status": status,
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def run_task40_v20_stage(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    v30_requested_factor_lifecycle_strategy: str | None = None,
    v30_effective_factor_lifecycle_strategy: str | None = None,
    v31_requested_factor_lifecycle_strategy: str | None = None,
    v31_effective_factor_lifecycle_strategy: str | None = None,
) -> dict[str, Any]:
    """Run only the explicitly selected V20 stage, failing closed at each gate."""

    execution = resolved_payload.get("execution", {})
    v30_requested = isinstance(execution, Mapping) and (
        "task40_v30_q_csr_binding" in execution
        or "task40_v30_factor_bank_config" in execution
    )
    v31_requested = isinstance(execution, Mapping) and (
        "task40_v31_q_csr_binding" in execution
        or "task40_v31_factor_bank_config" in execution
    )
    if v30_requested and v31_requested:
        raise ValueError("V20 stage cannot mix V30 and V31 lifecycle authorizations")
    if v30_requested:
        if (
            v30_requested_factor_lifecycle_strategy != "ONE_Q_REFACTOR_V19"
            or v30_effective_factor_lifecycle_strategy != "ALL_Q_RESIDENT"
            or resolved_payload.get("solver", {}).get("task40_factor_lifecycle_strategy")
            != v30_effective_factor_lifecycle_strategy
        ):
            raise ValueError("V30 stage requires the dispatcher-authorized V19-to-AllQ strategy binding")
        route_requested_strategy = v30_requested_factor_lifecycle_strategy
        route_effective_strategy = v30_effective_factor_lifecycle_strategy
    elif v31_requested:
        if (
            v31_requested_factor_lifecycle_strategy != "ONE_Q_REFACTOR_V19"
            or v31_effective_factor_lifecycle_strategy != "ALL_Q_RESIDENT"
            or resolved_payload.get("solver", {}).get("task40_factor_lifecycle_strategy")
            != v31_effective_factor_lifecycle_strategy
        ):
            raise ValueError("V31 stage requires the dispatcher-authorized V19-to-AllQ strategy binding")
        route_requested_strategy = v31_requested_factor_lifecycle_strategy
        route_effective_strategy = v31_effective_factor_lifecycle_strategy
    elif (
        v30_requested_factor_lifecycle_strategy is not None
        or v30_effective_factor_lifecycle_strategy is not None
        or v31_requested_factor_lifecycle_strategy is not None
        or v31_effective_factor_lifecycle_strategy is not None
    ):
        raise ValueError("V30/V31 factor-lifecycle binding is forbidden outside its route")

    profile, mesh_id = _exact_case(resolved_payload)
    stop_stage = str(resolved_payload["execution"]["task40_execution_stop_stage"])
    output_directory = Path(run_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    preflight, modes, mode_rows = _preflight(
        resolved_payload, source_sha=source_sha, profile=profile, mesh_id=mesh_id
    )
    if v30_requested or v31_requested:
        preflight[
            "v31_factor_lifecycle_authority" if v31_requested else "v30_factor_lifecycle_authority"
        ] = {
            "requested": route_requested_strategy,
            "effective": route_effective_strategy,
        }
    _write_json(output_directory / "v20_stage_preflight.json", preflight)
    completed = ["preflight"]

    if (
        profile == _V22_TARGET_OPERATOR_PROFILE
        and stop_stage == "selected_reference_q_csr"
        and os.environ.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1"
    ):
        return _run_v27_saved_q0_stage(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile=profile,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            stop_stage=stop_stage,
            v28_continuation=True,
            v29_strict_factor_only=True,
        )

    if (
        profile == _V22_TARGET_OPERATOR_PROFILE
        and stop_stage == "selected_reference_q_csr"
        and os.environ.get("TASK40_V28_OPERATION")
    ):
        return _run_v27_saved_q0_stage(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile=profile,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            stop_stage=stop_stage,
            v28_continuation=True,
        )

    if (
        profile == _V22_TARGET_OPERATOR_PROFILE
        and stop_stage == "selected_reference_q_csr"
        and os.environ.get("TASK40_V27_OPERATION")
    ):
        return _run_v27_saved_q0_stage(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile=profile,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            stop_stage=stop_stage,
        )

    if (
        profile == _V22_TARGET_OPERATOR_PROFILE
        and stop_stage in {
            "selected_reference_q_build_only",
            "selected_reference_q_consumer",
            "selected_reference_q_csr",
        }
        and os.environ.get("TASK40_V26_OPERATION")
    ):
        return _run_v26_selected_q0_stage(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile=profile,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            stop_stage=stop_stage,
        )

    if profile == _V22_TARGET_OPERATOR_PROFILE and stop_stage in {
        "selected_reference_q_consumer",
        "selected_reference_q_build_only",
        "selected_reference_q_csr",
    }:
        return _run_v25_selected_q0_stage(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile=profile,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            stop_stage=stop_stage,
        )

    execution_bindings = resolved_payload["execution"]
    v30_q_csr_binding = execution_bindings.get("task40_v30_q_csr_binding")
    v30_factor_config = execution_bindings.get("task40_v30_factor_bank_config")
    v31_q_csr_binding = execution_bindings.get("task40_v31_q_csr_binding")
    v31_factor_config = execution_bindings.get("task40_v31_factor_bank_config")
    v31_route = os.environ.get("TASK40_V31_STRICT_EXECUTION") == "1"
    v30_metadata = v30_q_csr_binding is not None or v30_factor_config is not None
    v31_metadata = v31_q_csr_binding is not None or v31_factor_config is not None
    if v30_metadata and v31_metadata:
        raise ValueError("Task40 service route cannot mix V30 and V31 execution bindings")
    if v30_metadata or v31_metadata:
        selected_q_csr_binding = v31_q_csr_binding if v31_route else v30_q_csr_binding
        selected_factor_config = v31_factor_config if v31_route else v30_factor_config
        if (
            mesh_id != "TARGET_ORIGINAL_NY8"
            or stop_stage != "full"
            or not resolved_payload["execution"].get("task40_target_heavy_authorized")
            or not isinstance(selected_q_csr_binding, Mapping)
            or not isinstance(selected_factor_config, Mapping)
        ):
            raise ValueError("Task40 V30/V31 service route requires the exact authorized target full-stage package")
        repo_root = Path(__file__).resolve().parents[2]
        if v31_route:
            if os.environ.get("TASK40_V30_STRICT_EXECUTION") == "1":
                raise RuntimeError("V31 worker route cannot inherit V30 strict authorization")
            from src.runners.task40_v31_contract import (
                V31_Q_CSR_BINDING_SCHEMA,
                V31_FACTOR_BANK_SCHEMA,
                V31_WORKER_BINDING_SCHEMA,
                require_v31_execution_contract,
                v31_source_artifact_relative,
            )

            v31_contract_path = Path(os.environ.get("TASK40_V31_CONTRACT_PATH", ""))
            v31_contract, v31_contract_sha = require_v31_execution_contract(
                v31_contract_path,
                expected_sha256=os.environ.get("TASK40_V31_CONTRACT_SHA256"),
                current_root=repo_root,
            )
            v31_execution = v31_contract["execution"]
            v31_window = v31_execution["window"]
            v31_resources = v31_execution["resources"]
            staged_q_csr_import_authorizations = dict(
                resolved_payload["execution"].get(
                    "task40_v31_q_csr_import_authorizations", {}
                )
            )
            v32_route = (
                isinstance(v31_contract.get("review"), Mapping)
                and v31_contract["review"].get("path")
                == "docs/task40extra_0p7nm_engineering/review_report_v32.md"
            )
            if v32_route:
                v32_template = v31_contract.get("preparation", {}).get(
                    "q4_numeric_pending_import"
                )
                v32_complete_template = v31_contract.get("preparation", {}).get(
                    "q4_complete_import"
                )
                v31_q_csr_import_authorizations = v31_execution.get(
                    "q_csr_import_authorizations"
                )
                if (
                    not isinstance(v32_template, Mapping)
                    or not isinstance(v32_complete_template, Mapping)
                    or staged_q_csr_import_authorizations
                    != {
                        "complete": {"4": dict(v32_complete_template)},
                        "numeric_pending": {"4": dict(v32_template)},
                    }
                    or not isinstance(v31_q_csr_import_authorizations, Mapping)
                ):
                    raise RuntimeError(
                        "V32 staged DAT import template differs from the approved q4 contract"
                    )
                v31_q_csr_import_authorizations = dict(v31_q_csr_import_authorizations)
            else:
                v31_q_csr_import_authorizations = staged_q_csr_import_authorizations
            if (
                v31_contract_sha != os.environ.get("TASK40_V31_CONTRACT_SHA256")
                or Path(str(v31_window["window_path"])).resolve()
                != Path(os.environ.get("TASK40_V31_EXECUTION_WINDOW_PATH", "")).resolve()
                or v31_window["window_sha256"]
                != os.environ.get("TASK40_V31_EXECUTION_WINDOW_SHA256")
                or str(v31_resources["task_memory_max_bytes"])
                != os.environ.get("TASK40_V31_TASK_MEMORY_MAX_BYTES")
                or str(v31_resources["host_reserve_bytes"])
                != os.environ.get("TASK40_V31_HOST_RESERVE_BYTES")
                or str(v31_resources["memory_swap_max_bytes"])
                != os.environ.get("TASK40_V31_MEMORY_SWAP_MAX_BYTES")
                or not isinstance(v31_q_csr_binding, Mapping)
                or not isinstance(v31_factor_config, Mapping)
                or Path(str(v31_execution["selector_path"])).resolve()
                != Path(str(v31_q_csr_binding.get("selector_path", ""))).resolve()
                or v31_execution["selector_sha256"]
                != v31_q_csr_binding.get("selector_sha256")
                or v31_q_csr_binding.get("schema") != V31_Q_CSR_BINDING_SCHEMA
                or v31_factor_config.get("schema") != V31_FACTOR_BANK_SCHEMA
            ):
                raise RuntimeError("V31 worker contract, selector, fixed window, or resource environment differs")
            source_root = (
                repo_root
                / v31_source_artifact_relative(str(v31_execution["run_source_sha"]))
            ).resolve()
            expected_v31_factor_config = {
                "schema": V31_FACTOR_BANK_SCHEMA,
                "output_directory": (
                    v31_source_artifact_relative(str(v31_execution["run_source_sha"]))
                    / "factor_bank"
                ).as_posix(),
                "require_two_strict_rhs": True,
                "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
            }
            if dict(v31_factor_config) != expected_v31_factor_config:
                raise RuntimeError("V31 stage DAT factor-bank binding differs from its source-qualified contract")
            v31_binding = {
                "schema": V31_WORKER_BINDING_SCHEMA,
                "contract_path": str(v31_contract_path.resolve()),
                "contract_sha256": v31_contract_sha,
                "execution_window_path": str(Path(str(v31_window["window_path"])).resolve()),
                "execution_window_sha256": str(v31_window["window_sha256"]),
                "source_at_entry": str(v31_window["source_at_entry"]),
                "run_source_sha": str(v31_execution["run_source_sha"]),
                "q_csr_selector_binding": {
                    "schema": V31_Q_CSR_BINDING_SCHEMA,
                    "selector_path": str(Path(str(v31_execution["selector_path"])).resolve()),
                    "selector_sha256": str(v31_execution["selector_sha256"]),
                },
                "factor_bank_config": {
                    "schema": V31_FACTOR_BANK_SCHEMA,
                    "output_directory": str(source_root / "factor_bank"),
                    "require_two_strict_rhs": True,
                    "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
                },
                "accepted_q0_donor": dict(v31_contract["preparation"]["accepted_q0_donor"]),
                "q_csr_worklist": list(v31_contract["preparation"]["q_csr_worklist"]),
                "q_csr_import_authorizations": v31_q_csr_import_authorizations,
                "target_admission_policy": dict(
                    resolved_payload["execution"].get(
                        "task40_v31_target_admission_policy",
                        {
                            "schema": "task40extra.review_v31_target_admission.v1",
                            "phase": "REFERENCE_ONLY",
                        },
                    )
                ),
            }
            v30_contract = None
            v30_contract_sha = None
            v30_input_identity = None
        else:
            if v31_q_csr_binding is not None or v31_factor_config is not None:
                raise RuntimeError("V30 worker route cannot inherit V31 execution bindings")
            if os.environ.get("TASK40_V30_STRICT_EXECUTION") != "1":
                raise RuntimeError("V30 worker route requires the approved V30 service contract")
            from src.runners.task40_v30_contract import require_authorized_contract

            v30_contract_path = Path(os.environ.get("TASK40_V30_CONTRACT_PATH", ""))
            v30_contract, v30_contract_sha = require_authorized_contract(
                v30_contract_path,
                expected_sha256=os.environ.get("TASK40_V30_CONTRACT_SHA256"),
                current_root=repo_root,
            )
            if (
                v30_contract_sha != os.environ.get("TASK40_V30_CONTRACT_SHA256")
                or os.environ.get("TASK40_V30_EXECUTION_WINDOW_SHA256")
                != v30_contract["execution"]["campaign_window_sha256"]
            ):
                raise RuntimeError("V30 worker contract/window environment differs from the validated contract")
            v31_binding = None
        provenance = resolved_payload.get("provenance", {})
        if not isinstance(provenance, Mapping) or not provenance.get("source_path"):
            raise ValueError("V30/V31 stage runner lacks the staged input provenance")
        if v31_route:
            from src.runners.task40_v31_contract import require_v31_input_identity
            from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_RELATIVE

            v31_input_identity = require_v31_input_identity(
                repo_root / V30_CANONICAL_INPUT_RELATIVE,
                str(provenance["source_path"]),
                repo_root=repo_root,
                source_sha=str(v31_contract["source_freeze"]["source_sha"]),
                selector_sha256=str(v31_q_csr_binding["selector_sha256"]),
                q4_numeric_pending_import=(
                    v31_contract.get("preparation", {}).get("q4_numeric_pending_import")
                    if v32_route
                    else None
                ),
            )
            if v31_input_identity["staged_input_sha256"] != provenance.get("input_sha256"):
                raise ValueError("V31 stage runner raw stage SHA differs from its provenance")
            stage_input_identity = v31_input_identity
        else:
            from src.runners.task40_v30_contract import (
                V30_CANONICAL_INPUT_RELATIVE,
                require_v30_input_identity,
            )

            v30_input_identity = require_v30_input_identity(
                repo_root / V30_CANONICAL_INPUT_RELATIVE,
                str(provenance["source_path"]),
                repo_root=repo_root,
            )
            if v30_input_identity["staged_input_sha256"] != provenance.get("input_sha256"):
                raise ValueError("V30 stage runner raw stage SHA differs from its provenance")
            stage_input_identity = v30_input_identity
        from src.runners.task40_v10_worker import run_task40_v10_p6_reference_worker

        try:
            worker_result = run_task40_v10_p6_reference_worker(
                resolved_payload,
                output_directory,
                source_sha=source_sha,
                profile_identity=profile,
                share_transform_bank=True,
                v30_q_csr_binding=(v30_q_csr_binding if not v31_route else None),
                v30_factor_config=(v30_factor_config if not v31_route else None),
                v30_requested_factor_lifecycle_strategy=(
                    route_requested_strategy
                ),
                v30_effective_factor_lifecycle_strategy=(
                    route_effective_strategy
                ),
                v31_target_admission_policy=(
                    resolved_payload["execution"].get(
                        "task40_v31_target_admission_policy"
                    )
                ),
                v31_q_csr_import_authorizations=(
                    v31_binding["q_csr_import_authorizations"]
                    if v31_route
                    else None
                ),
                v31_q_csr_binding=(
                    v31_binding["q_csr_selector_binding"] if v31_route else None
                ),
                v31_factor_config=(
                    v31_binding["factor_bank_config"] if v31_route else None
                ),
                v31_execution_binding=v31_binding,
            )
            receipt = {
                "schema": (
                    "task40extra.review_v31_worker_service_receipt.v1"
                    if v31_route
                    else "task40extra.review_v30_worker_service_receipt.v1"
                ),
                "status": str(worker_result.get("status", "completed")),
                "requested_stage": stop_stage,
                "profile": profile,
                "run_id": preflight["run_id"],
                "source_sha": source_sha,
                "input_sha256": preflight["input_sha256"],
                "scientific_input_sha256": stage_input_identity["scientific_input_sha256"],
                "staged_input_sha256": stage_input_identity["staged_input_sha256"],
                **(
                    {
                        "v31_input_identity": dict(stage_input_identity),
                        "v31_worker_binding": {
                            key: value
                            for key, value in v31_binding.items()
                            if key not in {"accepted_q0_donor", "q_csr_import_authorizations"}
                        },
                        "accepted_q0_donor_identity_sha256": str(
                            v31_binding["accepted_q0_donor"].get("identity_sha256", "")
                        ),
                        "q_worklist": list(v31_binding["q_csr_worklist"]),
                        "factor_bank_schema": v31_binding["factor_bank_config"]["schema"],
                    }
                    if v31_route
                    else {
                        "v30_input_identity": dict(stage_input_identity),
                        "q_csr_selector": dict(v30_q_csr_binding),
                        "factor_bank_schema": v30_factor_config.get("schema"),
                    }
                ),
                "factor_lifecycle_strategy": {
                    "requested": route_requested_strategy,
                    "effective": route_effective_strategy,
                },
                **(
                    {
                        "execution_contract_path": str(v31_contract_path.resolve()),
                        "execution_contract_sha256": v31_contract_sha,
                        "execution_window_sha256": v31_binding["execution_window_sha256"],
                        "source_at_entry": v31_binding["source_at_entry"],
                        "run_source_sha": v31_binding["run_source_sha"],
                        "official_result": False,
                    }
                    if v31_route
                    else {
                        "execution_contract_path": str(v30_contract_path.resolve()),
                        "execution_contract_sha256": v30_contract_sha,
                        "execution_window_sha256": str(
                            v30_contract["execution"]["campaign_window_sha256"]
                        ),
                        "accepted_q0_donor_identity_sha256": str(
                            v30_contract["preparation"]["accepted_q0_donor"]["identity_sha256"]
                        ),
                        "pending_q_csr_worklist": list(
                            v30_contract["preparation"]["q_csr_worklist"]
                        ),
                        "final_all_q_selector_required_at": str(
                            v30_contract["preparation"]["final_all_q_selector_required_at"]
                        ),
                    }
                ),
                "worker_status": worker_result.get("status"),
                "official_result": bool(worker_result.get("official_result", False)),
            }
        except BaseException as error:
            receipt = {
                "schema": (
                    "task40extra.review_v31_worker_service_receipt.v1"
                    if v31_route
                    else "task40extra.review_v30_worker_service_receipt.v1"
                ),
                "status": "failed",
                "requested_stage": stop_stage,
                "profile": profile,
                "run_id": preflight["run_id"],
                "source_sha": source_sha,
                "input_sha256": preflight["input_sha256"],
                "scientific_input_sha256": stage_input_identity["scientific_input_sha256"],
                "staged_input_sha256": stage_input_identity["staged_input_sha256"],
                **(
                    {"v31_input_identity": dict(stage_input_identity)}
                    if v31_route
                    else {
                        "v30_input_identity": dict(stage_input_identity),
                        "q_csr_selector": dict(v30_q_csr_binding),
                    }
                ),
                "factor_lifecycle_strategy": {
                    "requested": route_requested_strategy,
                    "effective": route_effective_strategy,
                },
                "failure_type": type(error).__name__,
                "failure_message": str(error),
                "official_result": False,
            }
            _write_json(
                output_directory
                / ("v31_worker_service_receipt.json" if v31_route else "v30_worker_service_receipt.json"),
                receipt,
            )
            raise
        _write_json(
            output_directory
            / ("v31_worker_service_receipt.json" if v31_route else "v30_worker_service_receipt.json"),
            receipt,
        )
        return {
            **dict(worker_result),
            ("v31_service_receipt" if v31_route else "v30_service_receipt"): receipt,
        }

    if profile == _V22_TARGET_OPERATOR_PROFILE and stop_stage == "target_operator_probe":
        from src.solvers.task40_v22_operator_probe import (
            run_v22_target_operator_probe,
        )

        probe = run_v22_target_operator_probe(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            resource_sample=_resource_snapshot,
        )
        probe_status = str(probe.get("status", "FAILED"))
        attempted = list(probe.get("attempted_stages", []))
        completed = ["preflight", *probe.get("completed_stages", [])]
        failed_stage = probe.get("failed_stage")
        if probe_status == "RESOURCE_CONTROLLED_STOP":
            outcome = "RESOURCE_CONTROLLED_STOP"
            status = "controlled_stop"
            classification = "RESOURCE_CONTROLLED_STOP"
        elif probe_status == "PASS_ALL_MODE_B_D_STREAM_WITH_Q_UNBUILT":
            outcome = "STAGE_COMPLETED"
            status = "stage_completed"
            classification = "TARGET_OPERATOR_PROBE_B_D_STREAM_COMPLETE_Q_NOT_BUILT"
        elif probe_status == "PASS_ALL_MODE_B_D_STREAM_WITH_PARTIAL_Q_PORT_TILE":
            outcome = "STAGE_COMPLETED"
            status = "stage_completed"
            classification = "TARGET_OPERATOR_PROBE_COMPLETE_WITH_PARTIAL_Q_PORT_TILE"
        elif probe_status == "PASS_V23_Q_ONLY_SUPPLEMENT":
            outcome = "STAGE_COMPLETED"
            status = "stage_completed"
            classification = "TARGET_OPERATOR_PROBE_Q_ONLY_SUPPLEMENT"
        elif probe_status == "PASS_V24_BOUNDED_PORT_REUSE_VOLUME_SAMPLE":
            outcome = "STAGE_COMPLETED"
            status = "stage_completed"
            classification = "TARGET_OPERATOR_PROBE_V24_BOUNDED_PORT_REUSE_VOLUME_SAMPLE"
        elif probe_status == "PASS_V24_REAL_EDGE_VOLUME_PANEL":
            outcome = "STAGE_COMPLETED"
            status = "stage_completed"
            classification = "TARGET_OPERATOR_PROBE_V24_REAL_EDGE_VOLUME_PANEL"
        elif probe_status == "PASS_COMPLETE_TARGET_VOLUME_ACTION":
            outcome = "STAGE_COMPLETED"
            status = "stage_completed"
            classification = "TARGET_OPERATOR_PROBE_V25_COMPLETE_TARGET_VOLUME_ACTION"
        elif probe_status == "FAILED_COMPLETE_TARGET_VOLUME_ACTION":
            outcome = "STAGE_FAILED"
            status = "failed"
            classification = "TARGET_OPERATOR_PROBE_V25_COMPLETE_TARGET_VOLUME_ACTION_FAILED"
        elif probe_status == "PLANNED_SCAN_HANDOFF_WITH_PARTIAL_Q_PORT_TILE":
            outcome = "PLANNED_HANDOFF"
            status = "planned_handoff"
            classification = "TARGET_OPERATOR_PROBE_PLANNED_SCAN_HANDOFF_Q_PORT_TILE_COMPLETE"
        else:
            outcome = "STAGE_FAILED"
            status = "failed"
            classification = "TARGET_OPERATOR_PROBE_FAILED"
        receipt = {
            "schema": "task40extra.review_v20_partial_result.v2",
            "status": status,
            "outcome": outcome,
            "classification": classification,
            "run_id": preflight["run_id"],
            "profile": profile,
            "source_sha": source_sha,
            "input_sha256": preflight["input_sha256"],
            "physical_model_sha256": preflight["physical_model_sha256"],
            "requested_stop_stage": stop_stage,
            "attempted_stages": ["preflight", *attempted],
            "completed_stages": completed,
            "partial_stages": list(probe.get("partial_stages", [])),
            "failed_stage": failed_stage,
            "blocked_task_stage": probe.get("blocked_task_stage"),
            "q_coverage": probe.get(
                "q_coverage",
                {
                    "status": "NOT_RUN",
                    "expected_q_count": 8,
                    "built_q_count": 0,
                    "reason": "target operator probe did not build any q CSR or factor",
                },
            ),
            "expected_q_count": 8,
            "built_q_count": 0,
            "cleanup": probe.get(
                "cleanup",
                {"status": "UNKNOWN", "reason": "operator probe cleanup receipt unavailable"},
            ),
            "failure_type": probe.get("failure_type"),
            "failure_message": probe.get("failure_message"),
            "resource_gate": probe.get("resource_blocker")
            if outcome == "RESOURCE_CONTROLLED_STOP"
            else None,
            "stage_result": (
                {
                    "completed_stage": "target_operator_probe",
                    "probe_status": probe_status,
                }
                if outcome == "STAGE_COMPLETED"
                else None
            ),
            "planned_handoff": probe.get("planned_handoff")
            if outcome == "PLANNED_HANDOFF"
            else None,
            "artifact_hashes": {
                name: {"path": name, "sha256": _sha256_file(output_directory / name)}
                for name in (
                    "v20_stage_preflight.json",
                    "v20_geometry_inventory.json",
                    "v22_target_operator_probe.json",
                    "v23_reference_q_port_tile.json",
                    "v23_q_only_supplement.json",
                    "v23_selected_mode_production_B_D_H.npz",
                    "v23_selected_q_projection_readback.npz",
                    "v24_bounded_port_reuse_volume_sample.json",
                    "v24_bounded_32_mode_B_D_H_cache.npz",
                    "v24_bounded_32_mode_provider_replay.npz",
                    "v24_real_edge_volume_panel.json",
                    "v24_real_edge_volume_panel.npz",
                    "v25_complete_target_volume_action.json",
                    "v25_cell_class_coverage.json",
                    "v25_volume_witness_case_0.json",
                    "v25_volume_witness_case_1.json",
                )
                if (output_directory / name).is_file()
            },
            "official_result": False,
            "not_run": [name for name in V20_STAGE_NAMES if name not in completed],
            "geometry_inventory": probe.get("geometry_inventory"),
            "target_operator_probe": probe,
            "q_only_supplement": probe.get("q_only_supplement"),
            "full_field_release_allowed": False,
        }
        _write_json(output_directory / "v20_partial_result.json", receipt)
        return {
            "passed": outcome != "STAGE_FAILED",
            "errors": [receipt["failure_message"]] if status == "failed" else [],
            "official_result": False,
            "status": status,
            "summary": receipt,
            "numerical_output_directory": str(output_directory),
        }

    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage == "full":
        return _controlled_stop(
            output_directory,
            preflight=preflight,
            requested_stage=stop_stage,
            completed_stages=completed,
            reason="TARGET_SOLVER_NOT_QUALIFIED: original-size mapping, all-q/operator, recovery, and full-field gates remain open",
            additional={
                "full_field_release_allowed": False,
                "qualification_blockers": [
                    "actual target primal/dual mapping",
                    "all-q coverage and native operator witnesses",
                    "target recovery and original A6 residual",
                    "physical output and independent checker",
                ],
            },
        )

    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage in {
        "build_and_symbolic",
        "one_q_numeric",
    } and not bool(resolved_payload["execution"].get("task40_target_heavy_authorized")):
        return _controlled_stop(
            output_directory,
            preflight=preflight,
            requested_stage=stop_stage,
            completed_stages=completed,
            reason="TARGET_HEAVY_NOT_AUTHORIZED_IN_THIS_NOTEBOOK_EXECUTION; stage is registered and its worker route is available after explicit resource authorization",
            outcome="AUTH_NOT_GRANTED",
            attempted_stages=completed,
            additional={
                "production_worker_route": "src.runners.task40_v10_worker.run_task40_v10_p6_reference_worker",
                "target_heavy_authorized": False,
                "full_field_release_allowed": False,
                "resource_sample": preflight["resources"],
            },
        )

    geometry_facts = None
    mesh_data = cfg = classes = None
    axis_coordinates = None
    reused_local_rows: list[Mapping[str, Any]] = []
    reused_packet_validation = None
    resume_receipt = None
    resume_manifest_path = resolved_payload["execution"].get(
        "task40_component_resume_manifest_path"
    )
    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage in {
        "geometry_inventory",
        "local_port_components",
        "build_and_symbolic",
        "one_q_numeric",
    }:
        if resume_manifest_path is not None:
            if stop_stage != "local_port_components":
                raise ValueError("V20 component resume is allowed only at local_port_components")
            (
                geometry_facts,
                cfg,
                classes,
                axis_coordinates,
                completed_local_rows,
                resume_receipt,
            ) = _load_target_component_resume(
                resolved_payload,
                output_directory,
                source_sha=source_sha,
                preflight=preflight,
            )
            reused_local_rows = completed_local_rows
            reused_packet_validation = (
                resume_receipt.get("completed_prefix_independent_readback")
                or completed_local_rows[0]["saved_packet_independent_readback"]
            )
            _write_json(output_directory / "v20_component_resume_receipt.json", resume_receipt)
        else:
            from src.geometry.task40_v20_geometry import build_v20_geometry_inventory

            geometry_facts, mesh_data, cfg, classes = build_v20_geometry_inventory(
                resolved_payload, output_directory
            )
            axis_coordinates = tuple(
                np.unique(np.asarray(mesh_data.mesh.geometry.x[:, axis], dtype=np.float64))
                for axis in range(3)
            )
            _write_json(output_directory / "v20_geometry_inventory.json", geometry_facts)
        completed.append("geometry_inventory")

    local_facts = None
    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage in {
        "local_port_components",
        "build_and_symbolic",
        "one_q_numeric",
    }:
        if modes is None or mode_rows is None:
            raise RuntimeError("target V20 local/port stage requires the frozen AUTO mode table")
        from src.solvers.task40_v20_local_components import run_v20_local_port_components

        local_facts = run_v20_local_port_components(
            resolved_payload,
            output_directory,
            axis_coordinates=axis_coordinates,
            cfg=cfg,
            geometry_facts=geometry_facts,
            classes=classes,
            mode_rows=mode_rows,
            resource_sample=_resource_snapshot,
            completed_local_rows=reused_local_rows,
            reused_packet_validation=reused_packet_validation,
        )
        if resume_receipt is not None:
            local_facts["component_resume_receipt"] = resume_receipt
        _write_json(output_directory / "v20_local_port_components.json", local_facts)
        completed.append("local_port_components")
        if local_facts.get("status") != "PASS":
            attempted = list(completed)
            receipt = {
                "schema": "task40extra.review_v20_partial_result.v2",
                "status": "failed",
                "outcome": "STAGE_FAILED",
                "classification": "LOCAL_COMPONENT_GATE_FAILED",
                "run_id": preflight["run_id"],
                "profile": profile,
                "source_sha": source_sha,
                "input_sha256": preflight["input_sha256"],
                "physical_model_sha256": preflight["physical_model_sha256"],
                "requested_stop_stage": stop_stage,
                "attempted_stages": attempted,
                "completed_stages": completed[:-1],
                "failed_stage": "local_port_components",
                "q_coverage": {
                    "status": "NOT_RUN",
                    "reason": "local component gate failed before target q assembly",
                },
                "cleanup": {
                    "status": "UNKNOWN",
                    "reason": "local component runner did not provide a unified cleanup receipt",
                },
                "failure_message": "V20 original-size local/port component gate failed",
                "artifact_hashes": {
                    name: {"path": name, "sha256": _sha256_file(output_directory / name)}
                    for name in ("v20_stage_preflight.json", "v20_geometry_inventory.json", "v20_local_port_components.json")
                    if (output_directory / name).is_file()
                },
                "official_result": False,
                "not_run": ["all-q CSR/symbolic", "one-q numeric", "full field"],
                "local_port_components": local_facts,
            }
            _write_json(output_directory / "v20_partial_result.json", receipt)
            return {
                "passed": False,
                "errors": ["V20 original-size local/port component gate failed"],
                "official_result": False,
                "status": "failed",
                "summary": receipt,
                "numerical_output_directory": str(output_directory),
            }

    if stop_stage in {"build_and_symbolic", "one_q_numeric"}:
        from src.runners.task40_v10_worker import run_task40_v10_p6_reference_worker

        worker_result = None
        worker_failure: BaseException | None = None
        try:
            worker_result = run_task40_v10_p6_reference_worker(
                resolved_payload,
                output_directory,
                source_sha=source_sha,
                profile_identity=profile,
                share_transform_bank=True,
                stop_after_stage=stop_stage,
            )
        except BaseException as error:
            worker_failure = error
        receipt = _worker_stage_receipt(
            output_directory,
            preflight=preflight,
            requested_stage=stop_stage,
            completed_prefix=completed,
            target_heavy_authorized=bool(
                resolved_payload["execution"].get("task40_target_heavy_authorized")
            ),
            worker_result=worker_result,
            failure=worker_failure,
        )
        if worker_failure is not None:
            raise worker_failure
        if worker_result is None:
            raise RuntimeError("V20 stage worker returned no result")
        return {**dict(worker_result), "v20_partial_result": receipt}

    if profile.endswith("_e2_reference_v1") and stop_stage == "full":
        from src.runners.task40_v10_worker import run_task40_v10_p6_reference_worker

        return run_task40_v10_p6_reference_worker(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile_identity=profile,
            share_transform_bank=True,
        )

    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": "controlled_stop",
        "outcome": "STAGE_COMPLETED",
        "classification": "CONTROLLED_STOP_AT_REQUESTED_STAGE",
        "run_id": preflight["run_id"],
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight["input_sha256"],
        "physical_model_sha256": preflight["physical_model_sha256"],
        "requested_stop_stage": stop_stage,
        "attempted_stages": completed,
        "completed_stages": completed,
        "q_coverage": {
            "status": "NOT_RUN",
            "reason": "requested pre-q stage completed without target q assembly",
        },
        "cleanup": {
            "status": "UNKNOWN",
            "reason": "stage result did not provide a unified owner/descendant cleanup receipt",
        },
        "stage_result": {"completed_stage": stop_stage},
        "artifact_hashes": {
            name: {"path": name, "sha256": _sha256_file(output_directory / name)}
            for name in ("v20_stage_preflight.json", "v20_geometry_inventory.json", "v20_local_port_components.json")
            if (output_directory / name).is_file()
        },
        "official_result": False,
        "not_run": [
            name for name in V20_STAGE_NAMES if name not in completed
        ],
        "geometry_inventory": geometry_facts,
        "local_port_components": local_facts,
        "full_field_release_allowed": False,
        "resources": _resource_snapshot(),
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": True,
        "errors": [],
        "official_result": False,
        "status": "controlled_stop",
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


__all__ = ["run_task40_v20_stage", "V20_STAGE_NAMES", "V20_TARGET_Q0"]
