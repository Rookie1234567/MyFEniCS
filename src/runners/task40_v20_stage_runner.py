"""Task40 V20 case routing and bounded original-size preflight stages."""

from __future__ import annotations

from collections.abc import Mapping
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
    "local_port_components",
    "build_and_symbolic",
    "one_q_numeric",
    "full",
)
V20_TARGET_Q0 = 0
V20_TARGET_FULL_FIELD_QUALIFIED = False
_V20_TARGET_RUN_ID = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
_V20_TARGET_PROFILE = "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
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
    from src.geometry.task40_nonseparable_plan import TASK40_COMPARISON_GROUP
    from src.solvers.task40_v20_registry import task40_v20_case

    solver = resolved.get("solver", {})
    execution = resolved.get("execution", {})
    profile = solver.get("preconditioner")
    run_id = resolved.get("run_id")
    try:
        case = task40_v20_case(profile=str(profile))
    except ValueError:
        case = None
    if (
        case is None
        or run_id != case.run_id
        or resolved.get("comparison_group") != TASK40_COMPARISON_GROUP
        or resolved.get("method", {}).get("kind") != "full3d_iterative"
        or solver.get("task40_reference_pc_strategy")
        != "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
        or solver.get("task40_q_assembly_strategy") != "ROW_TILE_BOUNDED_CSR_V17"
        or solver.get("task40_factor_lifecycle_strategy") != "ONE_Q_REFACTOR_V19"
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
    if (
        os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1"
        or MPI.COMM_WORLD.size != 1
        or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
        or np.dtype(PETSc.IntType) != np.dtype(np.int32)
    ):
        raise RuntimeError("V20 preflight requires qualified WSL MPI1 complex128/int32 ABI")
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
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
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
    additional: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v1",
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
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": True,
        "errors": [],
        "official_result": False,
        "status": "controlled_stop",
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def run_task40_v20_stage(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run only the explicitly selected V20 stage, failing closed at each gate."""

    profile, mesh_id = _exact_case(resolved_payload)
    stop_stage = str(resolved_payload["execution"]["task40_execution_stop_stage"])
    output_directory = Path(run_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    preflight, modes, mode_rows = _preflight(
        resolved_payload, source_sha=source_sha, profile=profile, mesh_id=mesh_id
    )
    _write_json(output_directory / "v20_stage_preflight.json", preflight)
    completed = ["preflight"]

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
            receipt = {
                "schema": "task40extra.review_v20_partial_result.v1",
                "status": "failed",
                "classification": "LOCAL_COMPONENT_GATE_FAILED",
                "run_id": preflight["run_id"],
                "profile": profile,
                "source_sha": source_sha,
                "input_sha256": preflight["input_sha256"],
                "physical_model_sha256": preflight["physical_model_sha256"],
                "requested_stop_stage": stop_stage,
                "completed_stages": completed,
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

        return run_task40_v10_p6_reference_worker(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile_identity=profile,
            share_transform_bank=True,
            stop_after_stage=stop_stage,
        )

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
        "schema": "task40extra.review_v20_partial_result.v1",
        "status": "controlled_stop",
        "classification": "CONTROLLED_STOP_AT_REQUESTED_STAGE",
        "run_id": preflight["run_id"],
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight["input_sha256"],
        "physical_model_sha256": preflight["physical_model_sha256"],
        "requested_stop_stage": stop_stage,
        "completed_stages": completed,
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
