#!/usr/bin/env python3
"""Prepare the held V29 q0 factor-only package without starting a service."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runners.task40_v29_contract import (
    V29_SELECTOR_SCHEMA,
    V29_STRICT_POLICY,
    V29ContractError,
    read_json_object,
    sha256_file,
)


TASK = Path("docs/task40extra_0p7nm_engineering")
ARTIFACT_REL = Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_preparation")
TARGET_ROOT = Path("/home/fenics/Projects/laptop_share")
TARGET_ROOT_RECEIPT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/main_workstation_readonly_receipt_v29.json"
)
TARGET_ROOT_RECEIPT_SHA256 = "5bddd5d774ace598751449d41e3df160a4a833e2aa7ab68985e399273040f4ff"
TARGET_RUNTIME_INVENTORY = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/main_target_system_runtime_inventory_v29.json"
)
TARGET_RUNTIME_INVENTORY_SHA256 = "0665dc67a5e39bdeec94a8feb099a1dbd4185fd3f19a12cdc06ec44b37939bef"
EXPECTED_REVIEW_SHA256 = "7a535053474bf864ed77dbf13f66aba1baf2172ff568738e10e2bc3d2266d51e"
EXPECTED_BRANCH = "task40extra_0p7nm_engineering"
INPUT_SHA256 = "134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b"
V28_WINDOW = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/campaign_window_v28.json"
)
V28_RECEIPT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/registration_receipt_v28.json"
)


def _relative_path(value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve(strict=False).relative_to(ROOT).as_posix()


def _file_record(
    *,
    label: str,
    path: str | Path,
    purpose: str,
    required: bool,
    historical_sha256: str | None = None,
    historical_hash_scope: str | None = None,
    expected_bytes: int | None = None,
    progress_path: Path | None = None,
) -> dict[str, Any]:
    source = Path(path)
    if not source.is_absolute():
        source = ROOT / source
    source = source.resolve(strict=False)
    exists = source.is_file()
    source_relative = _relative_path(source) if source.is_relative_to(ROOT) else None
    destination = TARGET_ROOT / source_relative if source_relative is not None else None
    record: dict[str, Any] = {
        "id": label,
        "source_path": str(source),
        "source_relative_path": source_relative,
        "approved_destination_path": None,
        "proposed_destination_path": str(destination) if destination is not None else None,
        "proposed_destination_relative_path": source_relative,
        "bytes": source.stat().st_size if exists else None,
        "expected_bytes": expected_bytes,
        "historical_sha256": historical_sha256,
        "historical_hash_scope": historical_hash_scope,
        "actual_sha256": None,
        "actual_hash_scope": "full file SHA-256 computed by this local prepare run" if exists else None,
        "purpose": purpose,
        "local_status": "PRESENT" if exists else "MISSING",
        "target_status": (
            "NEEDS_COPY_EMPTY_ROOT_SNAPSHOT"
            if required and destination is not None
            else "NOT_REQUIRED_BY_SELECTED_ROUTE"
            if not required
            else "DESTINATION_NOT_MAPPED"
        ),
        "copy_scope": (
            "whole file only, after explicit source/destination authorization"
            if required else "not required by the selected factor-only route"
        ),
        "required_by_factor_only_loader": bool(required),
    }
    if expected_bytes is not None and exists and source.stat().st_size != expected_bytes:
        record["local_status"] = "SIZE_MISMATCH"
    if exists:
        digest = hashlib.sha256()
        read_bytes = 0
        last_reported = 0
        with source.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
                read_bytes += len(chunk)
                if progress_path is not None and read_bytes - last_reported >= 1 << 30:
                    progress = {
                        "event": "hash_progress",
                        "utc": datetime.now(timezone.utc).isoformat(),
                        "id": label,
                        "path": str(source),
                        "read_bytes": read_bytes,
                        "file_bytes": record["bytes"],
                    }
                    with progress_path.open("a", encoding="utf-8") as stream_out:
                        stream_out.write(json.dumps(progress, ensure_ascii=False) + "\n")
                        stream_out.flush()
                        os.fsync(stream_out.fileno())
                    print(json.dumps(progress, ensure_ascii=False), flush=True)
                    last_reported = read_bytes
        record["actual_sha256"] = digest.hexdigest()
        if historical_sha256 is not None and record["actual_sha256"] != historical_sha256:
            record["local_status"] = "HASH_MISMATCH"
    return record


def _require_identity(actual: str | None, expected: str, label: str) -> None:
    if actual != expected:
        raise V29ContractError(f"V29 prepare refused: {label} expected {expected}, got {actual}")


def prepare(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    if root != ROOT:
        raise V29ContractError("V29 preparation is restricted to this canonical Task40 checkout")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip()
    if branch != EXPECTED_BRANCH:
        raise V29ContractError(f"V29 prepare requires {EXPECTED_BRANCH}; found {branch}")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    review_path = root / TASK / "review_report_v29.md"
    review_sha = sha256_file(review_path)
    _require_identity(review_sha, EXPECTED_REVIEW_SHA256, "Review V29 SHA-256")

    operator_path = root / TASK / "outcomes/records/target_operator_probe_v28.json"
    operator = read_json_object(operator_path)
    resource = read_json_object(root / TASK / "outcomes/records/time_resource_accounting_v28.json")
    raw = operator["raw_evidence"]
    donor = operator["donor_identity"]
    producer = donor["producer_identity"]
    identity = operator["identity"]
    artifact_dir = root / ARTIFACT_REL
    artifact_dir.mkdir(parents=True, exist_ok=True)
    progress_path = artifact_dir / "preparation_progress.jsonl"
    progress_path.write_text("", encoding="utf-8")
    with progress_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "event": "prepare_started",
            "utc": datetime.now(timezone.utc).isoformat(),
            "head": head,
            "dependency_hashing": "full_file_sha256_streaming",
        }, ensure_ascii=False) + "\n")
    _require_identity(
        raw["original_v27_manifest"]["sha256"],
        "1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de",
        "V27 source manifest historical identity",
    )
    _require_identity(
        raw["continuation_manifest"]["sha256"],
        "ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290",
        "V28 complete manifest historical identity",
    )
    _require_identity(
        raw["native_qualification"]["sha256"],
        "63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81",
        "V28 qualification historical identity",
    )

    specs: list[dict[str, Any]] = []

    def add(label, path, purpose, required=True, expected=None, scope=None, size=None):
        progress = {
            "event": "dependency_hash_started",
            "utc": datetime.now(timezone.utc).isoformat(),
            "id": label,
            "path": str(path),
        }
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(progress, ensure_ascii=False) + "\n")
            stream.flush()
        specs.append(_file_record(
            label=label,
            path=path,
            purpose=purpose,
            required=required,
            historical_sha256=expected,
            historical_hash_scope=scope,
            expected_bytes=size,
            progress_path=progress_path,
        ))
        record = specs[-1]
        progress = {
            "event": "dependency_hash_finished",
            "utc": datetime.now(timezone.utc).isoformat(),
            "id": label,
            "local_status": record["local_status"],
            "bytes": record["bytes"],
            "actual_sha256": record["actual_sha256"],
        }
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(progress, ensure_ascii=False) + "\n")
            stream.flush()
        print(json.dumps(progress, ensure_ascii=False), flush=True)

    producer_root = root / producer["producer_run_directory"]
    producer_index_path = root / producer["failure_index_path"]
    producer_index = read_json_object(producer_index_path)
    producer_support = {
        str(item.get("path")): item
        for item in producer_index.get("supporting_records", [])
        if isinstance(item, Mapping)
    }
    for payload in producer["payloads"]:
        add(
            f"producer_{Path(payload['path']).stem}",
            producer_root / payload["path"],
            "V25 donor payload verified by the current V27/V28 q0 service route; six payloads are required even though AUTO fill is disabled",
            expected=payload["sha256"],
            scope="historical V25 producer identity embedded in the accepted V28 donor compact",
            size=payload["bytes"],
        )
    add(
        "producer_failure_artifact_index",
        producer_index_path,
        "producer identity and six-payload inventory read by the saved donor verifier",
        expected=producer["failure_index_sha256"],
        scope="historical V25 donor identity embedded in the accepted V28 donor compact",
    )
    for name, expected in (("run_manifest.json", producer["run_manifest_sha256"]),
                           ("resolved_config.json", producer["resolved_config_sha256"])):
        add(
            f"producer_{name.removesuffix('.json')}",
            producer_root / name,
            "producer run/config identity referenced by the accepted donor record",
            expected=expected,
            scope="historical V25 donor identity embedded in the accepted V28 donor compact",
        )
    for name in (
        "input_sha256.txt",
        "physical_model_sha256.txt",
        "source_sha.txt",
        "run_summary.json",
    ):
        item = producer_support[name]
        add(
            f"producer_support_{name.removesuffix('.txt').removesuffix('.json')}",
            producer_root / name,
            "supporting producer record opened by the strict V25 metadata verifier",
            expected=item["sha256"],
            scope="supporting_records entry in the frozen V25 failure artifact index",
            size=item["bytes"],
        )
    add(
        "producer_input_original_dat",
        producer_root / "input_original.dat",
        "original producer DAT read and identity-checked by the strict V25 metadata verifier",
        expected=producer["verified_input_sha256"],
        scope="accepted V26 donor identity cross-check",
    )
    producer_run_manifest = read_json_object(producer_root / "run_manifest.json")
    executed_dat_path = Path(str(producer_run_manifest.get("input_path", "")))
    if not executed_dat_path.is_absolute():
        executed_dat_path = root / executed_dat_path
    add(
        "producer_executed_stage_dat",
        executed_dat_path,
        "actual selected-reference-q stage input named by the frozen producer run manifest",
        expected=producer["actual_v25_dat_sha256"],
        scope="accepted V26 donor identity cross-check",
    )

    replay = donor["saved_replay_manifest"]
    add(
        "v26_saved_replay_manifest",
        replay["path"],
        "replay donor manifest checked by service and donor verifier",
        expected=replay["sha256"],
        scope="historical V26 replay identity embedded in the accepted V28 donor compact",
    )
    for name, item in replay["artifacts"].items():
        add(
            f"v26_replay_{name}", item["path"],
            "saved V26 replay payload checked by the donor verifier",
            expected=item["sha256"],
            scope="historical V26 replay identity embedded in the accepted V28 donor compact",
            size=item["bytes"],
        )
    for name, item in donor["native_cases"].items():
        add(
            f"v26_native_{name}", item["path"],
            "native q0/q4 witness checked by the V26 donor import validator",
            expected=item["sha256"],
            scope="historical V26 native identity embedded in the accepted V28 donor compact",
            size=item["bytes"],
        )
    for name in ("native_recovery_manifest", "native_recovery_checker"):
        item = donor[name]
        add(
            f"v26_{name}", item["path"],
            "native recovery/witness metadata checked by the V26 donor import validator",
            expected=item["sha256"],
            scope="historical V26 native identity embedded in the accepted V28 donor compact",
        )
    witness = donor["row_structure_witness"]
    add(
        "v26_row_structure_witness_npz", witness["path"],
        "V26 complete q0 row-count witness consumed by the selected-q0 continuation",
        expected=witness["sha256"], scope="historical V26 witness identity in accepted V28 donor compact",
        size=witness["bytes"],
    )
    add(
        "v26_row_structure_witness_manifest", witness["manifest_path"],
        "metadata for the V26 row-count witness",
        expected=witness["manifest_sha256"], scope="historical V26 witness identity in accepted V28 donor compact",
    )

    for key in ("original_v27_manifest", "continuation_manifest", "native_qualification"):
        item = raw[key]
        add(
            key, root / item["path"],
            "immutable V27 pattern / V28 complete CSR / native PASS binding",
            expected=item["sha256"], scope="reviewed V28 raw-evidence hash; current file is re-read here",
            size=item["bytes"],
        )
    for name, item in operator["csr"]["artifacts"].items():
        add(
            f"v28_csr_{name}", item["path"],
            "read-only q0 CSR array opened by the factor-only route",
            expected=item["sha256"], scope="accepted V28 manifest/checker hash; this prepare independently re-reads current bytes",
            size=item["bytes"],
        )
    readback = operator["native_qualification"]["saved_outputs"]
    readback_path = Path(operator["native_qualification"]["receipt"]["path"]).parent / readback["path"]
    add(
        "v28_native_readback_outputs", readback_path,
        "saved native vectors verified by the qualification loader and final checker",
        expected=readback["sha256"], scope="accepted V28 qualification and independent audit; current file is re-read here",
        size=readback["bytes"],
    )

    selector_path = root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/q0_continuation.json"
    selector_sha = sha256_file(selector_path) if selector_path.is_file() else None
    prior_selector_ref = raw.get("selector") or resource.get("raw", {}).get("selector")
    if isinstance(prior_selector_ref, Mapping) and selector_sha is not None:
        _require_identity(selector_sha, prior_selector_ref["sha256"], "V28 selector hash")
    add(
        "v28_q0_continuation_selector", selector_path,
        "existing V28 donor/pattern selector reused as the immutable science binding",
        expected=prior_selector_ref.get("sha256") if isinstance(prior_selector_ref, Mapping) else None,
        scope="accepted V28 selector registration hash",
        size=prior_selector_ref.get("bytes") if isinstance(prior_selector_ref, Mapping) else None,
    )
    input_record = identity["actual_numeric_fill_identity"]
    input_path = root / (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/"
        "stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat"
    )
    add(
        "science_input_dat", input_path,
        "unchanged scientific input; resource/execution authorization stays in the separate V29 contract",
        expected=INPUT_SHA256,
        scope="accepted V28 input identity",
    )
    add(
        "canonical_template_dat",
        root / "input/task40extra_0p7nm_engineering/target_original_ny8_operator_probe_v22.dat",
        "canonical template read by the existing service to validate the unchanged V28 stage input",
        scope="current canonical template bytes independently hashed by this V29 prepare run",
    )
    add(
        "immutable_v28_campaign_window",
        root / V28_WINDOW,
        "preserved V28 source window bound by the existing native qualification",
        expected=identity["actual_numeric_fill_identity"]["campaign_window_sha256"],
        scope="accepted V28 numeric-fill source identity",
    )
    add(
        "immutable_v28_registration_receipt",
        root / V28_RECEIPT,
        "read-only V28 campaign registration binding required by the existing selector route",
        expected="e2f4b5673918c3c94981b0596359fd46406a78fd48e2743ee72375a42093a58e",
        scope="registered V28 campaign receipt identity",
    )

    failed = [item for item in specs if item["local_status"] not in {"PRESENT"}]
    total_bytes = sum(int(item["bytes"] or 0) for item in specs)
    manifest = {
        "schema": "task40extra.review_v29_local_dependency_manifest.v1",
        "status": "PASS_LOCAL_IDENTITIES" if not failed else "FAILED_LOCAL_IDENTITIES",
        "authorization_status": "PENDING_USER_AUTHORIZATION",
        "target_host": {
            "alias": "fenics-ws",
            "address": "10.14.35.46",
            "remote_user": "fenics",
            "observed_hostname": "fenics-ws01",
            "status": "VERIFIED_HOST_AND_EMPTY_ROOT_BY_USER_AUTHORIZED_READ_ONLY_PROBE",
            "authorization_scope": "user-approved empty destination root verification only",
        },
        "target_root": str(TARGET_ROOT),
        "target_root_status": "VERIFIED_EMPTY",
        "target_runtime": None,
        "target_abi": None,
        "target_window": None,
        "transfer_authorized": False,
        "heavy_factor_authorized": False,
        "target_resource_observation": {
            "MemTotal_bytes": 2163100385280,
            "MemAvailable_bytes": 1413713145856,
            "SwapTotal_bytes": 8589930496,
            "SwapFree_bytes": 8569143296,
            "disk_free_bytes": 2681846722560,
            "scope": "main controller read-only snapshot; host swap exists, and no task cgroup cap is set",
        },
        "execution_target_evidence": {
            "path": str(root / TARGET_ROOT_RECEIPT),
            "sha256": TARGET_ROOT_RECEIPT_SHA256,
            "classification": "read-only host and empty-root verification; not transfer or runtime authorization",
        },
        "target_runtime_inventory_evidence": {
            "path": str(root / TARGET_RUNTIME_INVENTORY),
            "sha256": TARGET_RUNTIME_INVENTORY_SHA256,
            "classification": "read-only discovery only; ABI is not qualified and no runtime was created",
        },
        "source_head_at_prepare": head,
        "source_worktree_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip(),
        "source_transfer_status": "HELD_UNTIL_MAIN_FREEZES_EXACT_COMMIT_SNAPSHOT",
        "review_sha256": review_sha,
        "input_sha256": INPUT_SHA256,
        "input_identity_source_sha": input_record["source_sha"],
        "donor_identity_sha256": operator["donor_identity_sha256"],
        "scope": "Only files referenced by the accepted q0 factor-only service loader; no other tasks or historical run trees copied.",
        "hash_semantics": "historical_sha256 records the previously accepted hash source; actual_sha256 is a new full read of current local file bytes during this prepare. They are reported separately.",
        "dependencies": specs,
        "dependency_count": len(specs),
        "total_required_bytes_if_transferred": total_bytes,
        "missing_or_changed_ids": [item["id"] for item in failed],
        "copy_policy": "No copy is performed. The host/root are the user-approved verification target; file transfer remains unauthorized until the V29 package and exact dependency set are approved.",
        "path_mapping": {
            "source_root": str(root),
            "destination_root": str(TARGET_ROOT),
            "strategy": "explicit path-resolver sidecar; old manifests/selectors/qualification JSON remain byte-identical",
            "root_status": "ROOT_VERIFIED_EMPTY",
            "root_verification_receipt": str(root / TARGET_ROOT_RECEIPT),
            "root_verification_receipt_sha256": TARGET_ROOT_RECEIPT_SHA256,
            "transfer_status": "PENDING_AUTHORIZATION",
            "runtime_status": "PENDING_QUALIFICATION",
            "heavy_status": "PENDING_RESOURCE_AND_WINDOW_AUTHORIZATION",
        },
        "large_surface_stream": next((item for item in specs if item["id"] == "producer_v25_selected_q0_surface_functionals"), None),
    }
    contract_template = read_json_object(root / TASK / "outcomes/records/v29_execution_contract.json")
    contract_path = artifact_dir / "execution_contract_v29.json"
    if contract_path.exists():
        prior_contract = read_json_object(contract_path)
        if prior_contract.get("authorization_status") == "USER_APPROVED":
            contract_template = prior_contract
    contract_payload = json.dumps(contract_template, ensure_ascii=False, indent=2) + "\n"
    if not contract_path.exists() or contract_template.get("authorization_status") != "USER_APPROVED":
        contract_path.write_text(contract_payload, encoding="utf-8")

    contract_sha = sha256_file(contract_path)
    v28_selector = read_json_object(selector_path)
    strict_selector = {
        "schema": V29_SELECTOR_SCHEMA,
        "policy": V29_STRICT_POLICY,
        "operation": "EXISTING_COMPLETE_Q0_CSR_FACTOR_ONLY",
        "authorization_status": "PENDING_USER_AUTHORIZATION",
        "execution_contract_path": str(contract_path),
        "execution_contract_sha256": contract_sha,
        "immutable_v28_selector_path": str(selector_path),
        "immutable_v28_selector_sha256": selector_sha,
        "manifest_path": str(root / raw["continuation_manifest"]["path"]),
        "manifest_sha256": raw["continuation_manifest"]["sha256"],
        "qualification_path": str(root / raw["native_qualification"]["path"]),
        "qualification_sha256": raw["native_qualification"]["sha256"],
        "pattern_manifest_path": str(root / raw["original_v27_manifest"]["path"]),
        "pattern_manifest_sha256": raw["original_v27_manifest"]["sha256"],
        "continuation_manifest_path": str(root / raw["continuation_manifest"]["path"]),
        "input_path": str(input_path),
        "input_sha256": INPUT_SHA256,
        "physical_model_sha256": input_record["physical_model_sha256"],
        "run_id": input_record["run_id"],
        "qualified_numeric_source_sha": input_record["source_sha"],
        "qualified_window_sha256": input_record["campaign_window_sha256"],
        "qualified_mode_manifest_sha256": input_record["mode_manifest_sha256"],
        "qualified_ordered_mode_key_sha256": input_record["ordered_mode_key_sha256"],
        "qualified_donor_identity_sha256": operator["donor_identity_sha256"],
        "path_mapping_sidecar": str(artifact_dir / "path_mapping_v29.json"),
        "fill_fallback": False,
        "readback_fallback": False,
        "status": "HELD_PENDING_USER_AUTHORIZATION",
    }
    strict_selector_path = artifact_dir / "factor_only_selector_v29.json"
    strict_selector_path.write_text(json.dumps(strict_selector, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    path_mapping = {
        "schema": "task40extra.review_v29_path_mapping.v1",
        "source_root": str(root),
        "execution_root": str(TARGET_ROOT),
        "root_status": "ROOT_VERIFIED_EMPTY",
        "root_verification_receipt": str(root / TARGET_ROOT_RECEIPT),
        "root_verification_receipt_sha256": TARGET_ROOT_RECEIPT_SHA256,
        "transfer_status": "PENDING_AUTHORIZATION",
        "runtime_status": "PENDING_QUALIFICATION",
        "heavy_status": "PENDING_RESOURCE_AND_WINDOW_AUTHORIZATION",
        "rules": {
            "source_paths_must_resolve_under_source_root": True,
            "destination_paths_must_resolve_under_execution_root": True,
            "relative_layout_preserved": True,
            "rewrite_immutable_v28_json": False,
            "rewrite_method": "resolve_paths_in_memory_or_through_this_sidecar_only",
        },
    }
    path_mapping_path = artifact_dir / "path_mapping_v29.json"
    path_mapping_path.write_text(json.dumps(path_mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    command = [
        "bash", "scripts/run_case_in_user_service.sh", input_path.relative_to(root).as_posix(),
        "--task40-v29-execution-contract", contract_path.relative_to(root).as_posix(),
        "--task40-v29-factor-only-selector", strict_selector_path.relative_to(root).as_posix(),
    ]
    command_text = (
        "# HELD: do not run before package/resource approval, target runtime qualification, and main source freeze.\n"
        "cd " + shlex.quote(str(TARGET_ROOT)) + "\n"
        + " ".join(shlex.quote(part) for part in command) + "\n"
    )
    (artifact_dir / "factor_only_command_v29.sh.txt").write_text(command_text, encoding="utf-8")
    local_verify_command = (
        "# Local dependency verification only; this never launches a service or factor.\n"
        "cd " + shlex.quote(str(root)) + "\n"
        "source scripts/activate_myfenics_wsl.sh\n"
        "python scripts/task40_v29_prepare.py --verify-only\n"
    )
    (artifact_dir / "prepare_verify_only_v29.sh.txt").write_text(
        local_verify_command,
        encoding="utf-8",
    )
    manifest["command_path"] = str(artifact_dir / "factor_only_command_v29.sh.txt")
    manifest["contract_path"] = str(contract_path)
    manifest["contract_sha256"] = contract_sha
    manifest["selector_path"] = str(strict_selector_path)
    manifest["selector_sha256"] = sha256_file(strict_selector_path)
    manifest["path_mapping_sidecar"] = str(path_mapping_path)
    manifest["path_mapping_sha256"] = sha256_file(path_mapping_path)
    manifest["launch_command"] = command_text.strip()
    manifest["local_verify_only_command_path"] = str(
        artifact_dir / "prepare_verify_only_v29.sh.txt"
    )
    out = root / TASK / "outcomes/records/v29_dependency_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    start_path = artifact_dir / "preparation_start.json"
    if start_path.is_file():
        start = read_json_object(start_path)
        finish = {
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "ended_unix_ns": time.time_ns(),
            "ended_monotonic_ns": time.monotonic_ns(),
            "ended_boottime_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
        }
        finish["elapsed_monotonic_seconds"] = (
            finish["ended_monotonic_ns"] - int(start["started_monotonic_ns"])
        ) / 1e9
        finish["elapsed_boottime_seconds"] = (
            finish["ended_boottime_ns"] - int(start["started_boottime_ns"])
        ) / 1e9
        finish["elapsed_utc_seconds"] = (
            finish["ended_unix_ns"] - int(start["started_unix_ns"])
        ) / 1e9
        finish["start"] = start
        finish["scope"] = "measured from recorded local V29 preparation clock start; review/source inspection before that anchor remains UNKNOWN"
        (artifact_dir / "preparation_finish.json").write_text(json.dumps(finish, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["preparation_time"] = finish
        out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="verify and write the local dependency package; never launch")
    args = parser.parse_args(argv)
    try:
        result = prepare()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAILED_LOCAL_PREPARE", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "status": result["status"],
        "dependency_count": result["dependency_count"],
        "total_required_bytes_if_transferred": result["total_required_bytes_if_transferred"],
        "missing_or_changed_ids": result["missing_or_changed_ids"],
        "contract_status": "PENDING_USER_AUTHORIZATION",
        "launch_command": result["launch_command"],
        "dependency_manifest": "docs/task40extra_0p7nm_engineering/outcomes/records/v29_dependency_manifest.json",
    }, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS_LOCAL_IDENTITIES" else 2


if __name__ == "__main__":
    raise SystemExit(main())
