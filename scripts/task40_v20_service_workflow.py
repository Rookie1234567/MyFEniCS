#!/usr/bin/env python3
"""Hash-bound V20 stage inputs and a thin, clocked user-service driver."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tomllib
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runners.workflow_timebase import (  # noqa: E402
    CONSERVATIVE_REALTIME,
    checked_interval,
    clock_sample,
)
from src.runners.task40_v10_campaign import (  # noqa: E402
    TASK40_V22_CAMPAIGN_SHA256,
    TASK40_V22_CAMPAIGN_WINDOW,
    TASK40_V22_STAGE_SCOPE,
    TASK40_V23_CAMPAIGN_SHA256,
    TASK40_V23_CAMPAIGN_WINDOW,
    TASK40_V23_STAGE_SCOPE,
    TASK40_V24_CAMPAIGN_RECEIPT,
    TASK40_V24_CAMPAIGN_RECEIPT_SHA256,
    TASK40_V24_CAMPAIGN_SHA256,
    TASK40_V24_CAMPAIGN_WINDOW,
    TASK40_V24_REVIEW_COMMIT,
    TASK40_V24_REVIEW_PATH,
    TASK40_V24_REVIEW_SHA256,
    TASK40_V24_STAGE_SCOPE,
    TASK40_V24_PARENT_LEDGER,
    TASK40_V25_CAMPAIGN_RECEIPT,
    TASK40_V25_CAMPAIGN_RECEIPT_SHA256,
    TASK40_V25_CAMPAIGN_SHA256,
    TASK40_V25_CAMPAIGN_WINDOW,
    TASK40_V25_REVIEW_COMMIT,
    TASK40_V25_REVIEW_PATH,
    TASK40_V25_REVIEW_SHA256,
    TASK40_V25_STAGE_SCOPE,
    TASK40_V26_CAMPAIGN_RECEIPT,
    TASK40_V26_CAMPAIGN_RECEIPT_SHA256,
    TASK40_V26_CAMPAIGN_SHA256,
    TASK40_V26_CAMPAIGN_WINDOW,
    TASK40_V26_REVIEW_COMMIT,
    TASK40_V26_REVIEW_PATH,
    TASK40_V26_REVIEW_SHA256,
    TASK40_V26_STAGE_SCOPE,
    TASK40_V27_CAMPAIGN_RECEIPT,
    TASK40_V27_CAMPAIGN_RECEIPT_SHA256,
    TASK40_V27_CAMPAIGN_SHA256,
    TASK40_V27_CAMPAIGN_WINDOW,
    TASK40_V27_REVIEW_COMMIT,
    TASK40_V27_REVIEW_PATH,
    TASK40_V27_REVIEW_SHA256,
    TASK40_V27_STAGE_SCOPE,
    TASK40_V28_CAMPAIGN_RECEIPT,
    TASK40_V28_CAMPAIGN_RECEIPT_SHA256,
    TASK40_V28_CAMPAIGN_SHA256,
    TASK40_V28_CAMPAIGN_WINDOW,
    TASK40_V28_FORBIDDEN_SCOPE,
    TASK40_V28_PARENT_LEDGER,
    TASK40_V28_PARENT_WINDOW,
    TASK40_V28_REVIEW_COMMIT,
    TASK40_V28_REVIEW_PATH,
    TASK40_V28_REVIEW_SHA256,
    TASK40_V28_SOURCE_AT_ENTRY,
    TASK40_V28_STAGE_SCOPE,
    TASK40_V29_CAMPAIGN_WINDOW,
    TASK40_V30_TARGET_CAMPAIGN_SHA256,
    TASK40_V30_TARGET_CAMPAIGN_WINDOW,
    TASK40_V31_CAMPAIGN_WINDOW,
    TASK40_V30_STAGE_SCOPE,
    load_fixed_campaign_window,
)


ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl"
)
CAMPAIGN_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
    "campaign_window_v19.json"
)
CAMPAIGN_SHA256 = "b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0"
V22_TARGET_PROFILE = "task40extra_v22_p6_y_orbit_target_original_ny8_operator_probe_v1"
V22_STOP_STAGE_SCOPE = {
    "preflight": "implementation",
    "geometry_inventory": "geometry_descriptor",
    "local_port_components": "local_port_components",
    "target_operator_probe": "target_operator_probe",
}
# V23 keeps the hash-bound V22 physical profile but has a separate campaign
# identity, immutable window, and explicit scope. It cannot authorize V22 work.
V23_TARGET_PROFILE = V22_TARGET_PROFILE
V23_STOP_STAGE_SCOPE = {
    "preflight": "implementation",
    "geometry_inventory": "geometry_descriptor",
    "target_operator_probe": "target_operator_probe",
}
V23_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl"
)
V24_TARGET_PROFILE = V22_TARGET_PROFILE
V24_STOP_STAGE_SCOPE = {
    "preflight": "implementation",
    "target_operator_probe": "target_operator_probe",
}
V24_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v24_wsl"
)
V25_TARGET_PROFILE = V22_TARGET_PROFILE
V25_STOP_STAGE_SCOPE = {
    "preflight": "implementation",
    "target_operator_probe": "target_operator_probe",
    "selected_reference_q_consumer": "selected_reference_q_consumer",
    "selected_reference_q_build_only": "selected_reference_q_build_only",
    "selected_reference_q_csr": "selected_reference_q_csr",
}
V25_SELECTED_Q_STAGES = frozenset(
    {
        "selected_reference_q_consumer",
        "selected_reference_q_build_only",
        "selected_reference_q_csr",
    }
)
V25_SELECTED_OPERATION_BY_STAGE = {
    "target_operator_probe": "COMPLETE_TARGET_VOLUME_ACTION",
    "selected_reference_q_consumer": "SELECTED_REFERENCE_Q_CONSUMER",
    "selected_reference_q_build_only": "SELECTED_REFERENCE_Q_BUILD_ONLY",
    "selected_reference_q_csr": "SELECTED_REFERENCE_Q_CSR",
}
V25_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl"
)
V26_TARGET_PROFILE = V25_TARGET_PROFILE
V26_STOP_STAGE_SCOPE = {
    "selected_reference_q_build_only": "saved_stream_replay",
    "selected_reference_q_consumer": "native_reference_consumer",
    "selected_reference_q_csr": "complete_q0_csr",
}
V26_SELECTED_Q_STAGES = frozenset(V26_STOP_STAGE_SCOPE)
V26_SELECTED_OPERATION_BY_STAGE = {
    "selected_reference_q_build_only": "V26_SAVED_STREAM_REPLAY",
    "selected_reference_q_consumer": "V26_SAVED_STREAM_NATIVE_CONSUMER",
    "selected_reference_q_csr": "V26_COMPLETE_Q0_CSR_AND_CONDITIONAL_FACTOR",
}
V26_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl"
)
V27_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v27_wsl"
)
V27_TARGET_PROFILE = V26_TARGET_PROFILE
V27_STOP_STAGE_SCOPE = {
    "selected_reference_q_csr": "complete_q0_numeric_csr",
}
V27_SELECTED_Q_STAGES = frozenset(V27_STOP_STAGE_SCOPE)
V27_SELECTED_OPERATION_BY_STAGE = {
    "selected_reference_q_csr": "V27_SAVED_ONLY_COMPLETE_Q0_CSR",
}
V27_REPLAY_ROOT = V26_ARTIFACT_ROOT / "saved_replay"
V27_NATIVE_ROOT = V26_ARTIFACT_ROOT / "native_consumer"
V28_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl"
)
V29_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl"
)
V29_PREPARATION_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_preparation"
)
V30_ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_wsl"
)
V30_TARGET_PROFILE = "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
V28_TARGET_PROFILE = V27_TARGET_PROFILE
V28_STOP_STAGE_SCOPE = {
    "selected_reference_q_csr": "existing_manifest_continuation",
}
V28_SELECTED_Q_STAGES = frozenset(V28_STOP_STAGE_SCOPE)
V28_CONTINUATION_OPERATION = "V28_EXISTING_MANIFEST_Q0_CONTINUATION"
V28_CONTINUATION_POLICY = (
    "auto_manifest_state: pending_or_incomplete=fill_then_native_readback_then_factor_preflight; "
    "complete_without_matching_native_pass=readback_then_factor_preflight; "
    "complete_with_matching_native_pass=factor_preflight_only"
)
V28_PATTERN_MANIFEST_RELATIVE = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/"
    "20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_csr_manifest.json"
)
V28_PATTERN_MANIFEST_SHA256 = "1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de"
V28_CONTINUATION_MANIFEST_NAME = "task40_v28_q0_csr_continuation_manifest.json"
V27_REPLAY_MANIFEST_SHA256 = "6e16ab0f0bae09e472d2806a71bdf28325f3ce768b089fe4a6521099e68b100f"
V27_NATIVE_RECOVERY_TAG = "f9093c87f81d52b75fbc156e562b3745df45ccf4"
V27_NATIVE_RECOVERY_SHA256 = "6a558896fc0e83826081d9b418a89d4cd76d45207bf7dd4cd086c68df7c12265"
V27_NATIVE_CHECKER_SHA256 = "e6b88c9eeb5e2314cdf427f4db76f67ca73aac162307d005d2ac22f455ce4ce2"
V27_ROW_STRUCTURE_RELATIVE = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/"
    "20261011T111053.208174Z/v26_q0_preallocation_row_structure.npz"
)
V27_ROW_STRUCTURE_SHA256 = "b8241f8bf6e6d40c4238a0a01da90cc6e58e06a92b179d524a243fbe65deab69"
V27_ROW_STRUCTURE_MANIFEST_SHA256 = "f42ab160f8fc3d5ad04026b8c9d13491d2685205d149a9e395fdd2be7e8bb64b"
V26_PRODUCER_RUN_RELATIVE = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/"
    "20261011T053811.673002Z"
)
V26_FAILURE_INDEX_SHA256 = "c7f687e6054e0506d03d4443bfaede58bfa46d76476b5270844d3d792cb3f026"
V26_PRODUCER_SOURCE_SHA = "9d0f4dbfc730dd620b709d048e33e9da6c77520c"
V26_PRODUCER_RUN_ID = "task40extra_0p7nm_target_original_ny8_operator_probe_v22"
V26_LEGACY_BAD_INPUT_SHA256 = "7c7fcc172968bb291d6834bac6f2d3b71b3f1a1efb836129f5dfb872082407"
V26_VERIFIED_INPUT_SHA256 = "7c7fcc172968bb291d6834bac6c4f2d3b71b3f1a1efb836129f5dfb872082407"
V26_PRODUCER_FILE_HASHES = {
    "v25_selected_q0_surface_functionals.bin": (11230840064, "92fb011dc9bc551728079d10f8cd26e8810668b0ab5df78189c3466e2cbd4613"),
    "v25_selected_q0_volume_classes.bin": (226645122, "f76b1dad7b863c0e4fc32ca7cdbd793436a22cc2386a59b79e6297eac94e390b"),
    "v25_selected_q0_local_H_p.npy": (127040, "f79de1ec28568f9a1d05f4bd6743a497d9dcc729654cf0a04e56d92d912c5a21"),
    "v25_selected_q0_original_to_active_int32.npy": (21009152, "f473037848f72d886ddb0a421d6240fe77788f799740168c234c9340ba1a963d"),
    "v25_selected_q0_map.npz": (348496973, "cad0ea1d34c26cea53b07965d80b952733944a8003ee9aa09cf922e08bc71e20"),
    "v25_selected_q4_map.npz": (348492573, "871e1a86715588fb6157fe5bbc96bf545d207629e4ad480eafd7ee4cd383a2f4"),
}
RUNTIME_PREFIX_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
)
ABI_RECEIPT_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/"
    "continuation_attempt4/abi_receipt.json"
)
QUALIFIED_JIT_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/"
    "window_qualification_jit"
)
V20_INPUTS = {
    "task40extra_v20_p6_y_orbit_e2_reference_v1": (
        Path("input/task40extra_0p7nm_engineering/nonseparable_e2_p6_reference_v20.dat"),
        {"full"},
    ),
    "task40extra_v20_p6_y_orbit_target_original_ny8_v1": (
        Path(
            "input/task40extra_0p7nm_engineering/"
            "target_original_ny8_resource_pilot_v20.dat"
        ),
        {
            "geometry_inventory",
            "local_port_components",
            "build_and_symbolic",
            "one_q_numeric",
        },
    ),
    "task40extra_v22_p6_y_orbit_target_original_ny8_operator_probe_v1": (
        Path("input/task40extra_0p7nm_engineering/target_original_ny8_operator_probe_v22.dat"),
        {"target_operator_probe"},
    ),
}
STAGE_PREFIXES = {
    "preflight": ["preflight"],
    "selected_reference_q_consumer": ["preflight", "selected_reference_q_consumer"],
    "selected_reference_q_build_only": ["preflight", "selected_reference_q_build_only"],
    "selected_reference_q_csr": ["preflight", "selected_reference_q_csr"],
    "geometry_inventory": ["preflight", "geometry_inventory"],
    "target_operator_probe": [
        "preflight",
        "geometry_inventory",
        "target_operator_probe",
    ],
    "local_port_components": [
        "preflight",
        "geometry_inventory",
        "local_port_components",
    ],
    "build_and_symbolic": ["preflight"],
    "one_q_numeric": ["preflight"],
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_owned_payload(path: Path) -> str:
    """Hash donor data in bounded stdlib chunks and drop consumed file pages."""
    digest = hashlib.sha256()
    position = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
            if hasattr(os, "posix_fadvise"):
                advice = getattr(os, "POSIX_FADV_DONTNEED", None)
                if advice is not None:
                    try:
                        page_size = os.sysconf("SC_PAGE_SIZE")
                        begin = position - position % page_size
                        end = ((position + len(block) + page_size - 1) // page_size) * page_size
                        os.posix_fadvise(stream.fileno(), begin, end - begin, advice)
                    except (OSError, ValueError, TypeError):
                        pass
            position += len(block)
    return digest.hexdigest()


def _profile_q_count(profile_identity: str) -> int:
    """Return the periodic q count from the registered, hash-bound profile."""

    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    try:
        profile = TASK40_P6_PERIODIC_PROFILES[profile_identity]
    except KeyError as error:
        raise ValueError(
            f"partial receipt profile is not registered for q-count validation: {profile_identity!r}"
        ) from error
    count = int(profile.q_count)
    if count <= 0:
        raise ValueError("registered periodic profile q_count must be positive")
    return count


def _resolve_service_campaign(
    repo_root: Path,
    campaign_path: Path,
    *,
    profile: str,
    stop_stage: str,
    v31_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a historical window or an exact, scoped Task40 campaign."""

    supplied = campaign_path if campaign_path.is_absolute() else repo_root / campaign_path
    supplied = supplied.resolve()
    v19_path = (repo_root / CAMPAIGN_RELATIVE).resolve()
    if supplied == v19_path:
        if _sha256_file(v19_path) != CAMPAIGN_SHA256:
            raise ValueError("the existing V19 fixed campaign window SHA changed")
        return {
            "path": v19_path,
            "sha256": CAMPAIGN_SHA256,
            "stage_scope": None,
            "version": "V19",
        }

    v22_path = (repo_root / TASK40_V22_CAMPAIGN_WINDOW).resolve()
    v23_path = (repo_root / TASK40_V23_CAMPAIGN_WINDOW).resolve()
    v24_path = (repo_root / TASK40_V24_CAMPAIGN_WINDOW).resolve()
    v25_path = (repo_root / TASK40_V25_CAMPAIGN_WINDOW).resolve()
    v26_path = (repo_root / TASK40_V26_CAMPAIGN_WINDOW).resolve()
    v27_path = (repo_root / TASK40_V27_CAMPAIGN_WINDOW).resolve()
    v28_path = (repo_root / TASK40_V28_CAMPAIGN_WINDOW).resolve()
    v29_path = (repo_root / TASK40_V29_CAMPAIGN_WINDOW).resolve()
    v30_path = (repo_root / TASK40_V30_TARGET_CAMPAIGN_WINDOW).resolve()
    if v31_contract is None:
        v31_path = (repo_root / TASK40_V31_CAMPAIGN_WINDOW).resolve()
    else:
        from src.runners.task40_v31_contract import v31_source_artifact_relative

        v31_window = v31_contract.get("execution", {}).get("window", {})
        v31_entry_source = str(v31_window.get("source_at_entry", ""))
        v31_path = (
            repo_root
            / v31_source_artifact_relative(v31_entry_source)
            / "campaign_window_v31.json"
        ).resolve()
    if supplied == v22_path:
        if profile != V22_TARGET_PROFILE:
            raise ValueError("the V22 campaign route is restricted to the registered Ny8 target")
        stage_scope = V22_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V22_STAGE_SCOPE:
            raise ValueError("the V22 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v22_path) != TASK40_V22_CAMPAIGN_SHA256:
            raise ValueError("the registered V22 campaign window SHA changed")
        window = load_fixed_campaign_window(v22_path, require_current_boot=True)
        campaign_version = "V22"
    elif supplied == v23_path:
        if profile != V23_TARGET_PROFILE:
            raise ValueError("the V23 campaign route is restricted to the registered Ny8 target")
        stage_scope = V23_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V23_STAGE_SCOPE:
            raise ValueError("the V23 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v23_path) != TASK40_V23_CAMPAIGN_SHA256:
            raise ValueError("the registered V23 campaign window SHA changed")
        window = load_fixed_campaign_window(v23_path, require_current_boot=True)
        campaign_version = "V23"
    elif supplied == v24_path:
        if profile != V24_TARGET_PROFILE:
            raise ValueError("the V24 campaign route is restricted to the registered Ny8 target")
        stage_scope = V24_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V24_STAGE_SCOPE:
            raise ValueError("the V24 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v24_path) != TASK40_V24_CAMPAIGN_SHA256:
            raise ValueError("the registered V24 campaign window SHA changed")
        receipt_path = (repo_root / TASK40_V24_CAMPAIGN_RECEIPT).resolve()
        if (
            not receipt_path.is_file()
            or _sha256_file(receipt_path) != TASK40_V24_CAMPAIGN_RECEIPT_SHA256
        ):
            raise ValueError("the V24 campaign registration receipt is missing or changed")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("schema") != "task40extra.review_v24_campaign_registration.v1"
            or receipt.get("manifest_path") != str(TASK40_V24_CAMPAIGN_WINDOW)
            or receipt.get("manifest_sha256") != TASK40_V24_CAMPAIGN_SHA256
            or receipt.get("review_sha") != TASK40_V24_REVIEW_COMMIT
            or receipt.get("review_path") != TASK40_V24_REVIEW_PATH
            or receipt.get("review_sha256") != TASK40_V24_REVIEW_SHA256
            or receipt.get("stage_scope") != list(TASK40_V24_STAGE_SCOPE)
            or receipt.get("registration_state") != "REGISTERED_FOR_DEVELOPMENT; service/probe/checkpoint-loader/watchdog qualification required before FE"
        ):
            raise ValueError("the V24 campaign registration receipt identity or scope changed")
        window = load_fixed_campaign_window(v24_path, require_current_boot=True)
        campaign_version = "V24"
    elif supplied == v25_path:
        if profile != V25_TARGET_PROFILE:
            raise ValueError("the V25 campaign route is restricted to the registered Ny8 target")
        stage_scope = V25_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V25_STAGE_SCOPE:
            raise ValueError("the V25 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v25_path) != TASK40_V25_CAMPAIGN_SHA256:
            raise ValueError("the registered V25 campaign window SHA changed")
        receipt_path = (repo_root / TASK40_V25_CAMPAIGN_RECEIPT).resolve()
        if (
            not receipt_path.is_file()
            or _sha256_file(receipt_path) != TASK40_V25_CAMPAIGN_RECEIPT_SHA256
        ):
            raise ValueError("the V25 campaign registration receipt is missing or changed")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("schema") != "task40extra.review_v25_campaign_registration.v1"
            or receipt.get("manifest_path") != str(TASK40_V25_CAMPAIGN_WINDOW)
            or receipt.get("manifest_sha256") != TASK40_V25_CAMPAIGN_SHA256
            or receipt.get("review_sha") != TASK40_V25_REVIEW_COMMIT
            or receipt.get("review_path") != TASK40_V25_REVIEW_PATH
            or receipt.get("review_sha256") != TASK40_V25_REVIEW_SHA256
            or receipt.get("stage_scope") != list(TASK40_V25_STAGE_SCOPE)
            or receipt.get("registration_state")
            != "REGISTERED_FOR_DEVELOPMENT; campaign/service/worker/checker routing qualification required before FE"
        ):
            raise ValueError("the V25 campaign registration receipt identity or scope changed")
        window = load_fixed_campaign_window(v25_path, require_current_boot=True)
        campaign_version = "V25"
    elif supplied == v26_path:
        if profile != V26_TARGET_PROFILE:
            raise ValueError("the V26 campaign route is restricted to the registered Ny8 target")
        stage_scope = V26_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V26_STAGE_SCOPE:
            raise ValueError("the V26 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v26_path) != TASK40_V26_CAMPAIGN_SHA256:
            raise ValueError("the registered V26 campaign window SHA changed")
        receipt_path = (repo_root / TASK40_V26_CAMPAIGN_RECEIPT).resolve()
        if (
            not receipt_path.is_file()
            or _sha256_file(receipt_path) != TASK40_V26_CAMPAIGN_RECEIPT_SHA256
        ):
            raise ValueError("the V26 campaign registration receipt is missing or changed")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("schema") != "task40extra.review_v26_campaign_registration.v1"
            or receipt.get("manifest_path") != str(TASK40_V26_CAMPAIGN_WINDOW)
            or receipt.get("manifest_sha256") != TASK40_V26_CAMPAIGN_SHA256
            or receipt.get("review_sha") != TASK40_V26_REVIEW_COMMIT
            or receipt.get("review_path") != TASK40_V26_REVIEW_PATH
            or receipt.get("review_sha256") != TASK40_V26_REVIEW_SHA256
            or receipt.get("stage_scope")
            != [
                "implementation", "targeted_tests", "saved_stream_replay",
                "native_reference_consumer", "complete_q0_row_counts",
                "complete_q0_csr", "selected_q0_factor_lifecycle", "checker",
                "persistence_readback", "closeout",
            ]
            or receipt.get("registration_state")
            != "REGISTERED_FOR_DEVELOPMENT; service/selector/stage/watchdog/required-checker qualification required before saved replay"
        ):
            raise ValueError("the V26 campaign registration receipt identity or scope changed")
        window = load_fixed_campaign_window(v26_path, require_current_boot=True)
        campaign_version = "V26"
    elif supplied == v27_path:
        if profile != V27_TARGET_PROFILE:
            raise ValueError("the V27 campaign route is restricted to the registered Ny8 target")
        stage_scope = V27_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V27_STAGE_SCOPE:
            raise ValueError("the V27 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v27_path) != TASK40_V27_CAMPAIGN_SHA256:
            raise ValueError("the registered V27 campaign window SHA changed")
        receipt_path = (repo_root / TASK40_V27_CAMPAIGN_RECEIPT).resolve()
        if (
            not receipt_path.is_file()
            or _sha256_file(receipt_path) != TASK40_V27_CAMPAIGN_RECEIPT_SHA256
        ):
            raise ValueError("the V27 campaign registration receipt is missing or changed")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("schema") != "task40extra.review_v27_campaign_registration.v1"
            or receipt.get("manifest_path") != str(TASK40_V27_CAMPAIGN_WINDOW)
            or receipt.get("manifest_sha256") != TASK40_V27_CAMPAIGN_SHA256
            or receipt.get("review_sha") != TASK40_V27_REVIEW_COMMIT
            or receipt.get("review_path") != TASK40_V27_REVIEW_PATH
            or receipt.get("review_sha256") != TASK40_V27_REVIEW_SHA256
            or receipt.get("source_at_entry")
            != "399787abc991e0e30975bc694bd18a9a30c5470e"
            or receipt.get("stage_scope") != list(TASK40_V27_STAGE_SCOPE)
            or receipt.get("registration_state")
            != "REGISTERED_FOR_DEVELOPMENT; require source route/service/checker registration before formal worker"
        ):
            raise ValueError("the V27 campaign registration receipt identity or scope changed")
        window = load_fixed_campaign_window(v27_path, require_current_boot=True)
        campaign_version = "V27"
    elif supplied == v28_path:
        if profile != V28_TARGET_PROFILE:
            raise ValueError("the V28 continuation route is restricted to the registered Ny8 target")
        stage_scope = V28_STOP_STAGE_SCOPE.get(stop_stage)
        if stage_scope is None or stage_scope not in TASK40_V28_STAGE_SCOPE:
            raise ValueError("the V28 service stop stage is outside its explicit campaign scope")
        if _sha256_file(v28_path) != TASK40_V28_CAMPAIGN_SHA256:
            raise ValueError("the registered V28 campaign window SHA changed")
        receipt_path = (repo_root / TASK40_V28_CAMPAIGN_RECEIPT).resolve()
        if (
            not receipt_path.is_file()
            or _sha256_file(receipt_path) != TASK40_V28_CAMPAIGN_RECEIPT_SHA256
        ):
            raise ValueError("the V28 campaign registration receipt is missing or changed")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("schema") != "task40extra.review_v28_campaign_registration.v1"
            or receipt.get("manifest_path") != str(TASK40_V28_CAMPAIGN_WINDOW)
            or receipt.get("manifest_sha256") != TASK40_V28_CAMPAIGN_SHA256
            or receipt.get("review_sha") != TASK40_V28_REVIEW_COMMIT
            or receipt.get("review_path") != TASK40_V28_REVIEW_PATH
            or receipt.get("review_sha256") != TASK40_V28_REVIEW_SHA256
            or receipt.get("source_at_entry") != TASK40_V28_SOURCE_AT_ENTRY
            or receipt.get("stage_scope") != list(TASK40_V28_STAGE_SCOPE)
            or receipt.get("forbidden_scope") != list(TASK40_V28_FORBIDDEN_SCOPE)
            or receipt.get("parent_window") != TASK40_V28_PARENT_WINDOW
            or receipt.get("parent_ledger") != TASK40_V28_PARENT_LEDGER
            or receipt.get("registration_state")
            != "REGISTERED_FOR_DEVELOPMENT; service/selector/worker/watchdog/checker route qualification required before formal worker"
        ):
            raise ValueError("the V28 campaign registration receipt identity or scope changed")
        window = load_fixed_campaign_window(v28_path, require_current_boot=True)
        campaign_version = "V28"
    elif supplied == v29_path:
        if profile != V28_TARGET_PROFILE or stop_stage not in V28_SELECTED_Q_STAGES:
            raise ValueError("the V29 campaign route is restricted to existing q0 factor-only continuation")
        window = load_fixed_campaign_window(v29_path, require_current_boot=True)
        stage_scope = "existing_manifest_continuation_factor_only"
        campaign_version = "V29"
    elif supplied == v30_path:
        if profile != V30_TARGET_PROFILE or stop_stage != "full":
            raise ValueError("the V30 service route is restricted to the reviewed full reference worker")
        if _sha256_file(v30_path) != TASK40_V30_TARGET_CAMPAIGN_SHA256:
            raise ValueError("the registered target-native V30 campaign window SHA changed")
        window = load_fixed_campaign_window(v30_path, require_current_boot=True)
        stage_scope = list(TASK40_V30_STAGE_SCOPE)
        campaign_version = "V30"
    elif supplied == v31_path:
        if profile != "task40extra_v20_p6_y_orbit_target_original_ny8_v1" or stop_stage != "full":
            raise ValueError("the V31 service route is restricted to the reviewed full Ny8 worker")
        if v31_contract is None:
            raise ValueError("the V31 campaign window requires its user-approved execution contract")
        from src.runners.task40_v10_campaign import _validate_v31_campaign_registration

        window = load_fixed_campaign_window(
            v31_path, require_current_boot=True, v31_contract=v31_contract
        )
        _validate_v31_campaign_registration(
            v31_path,
            window.sha256,
            window.payload,
            v31_contract,
        )
        from src.runners.task40_v31_contract import V31_STAGE_SCOPE

        stage_scope = list(V31_STAGE_SCOPE)
        campaign_version = "V31"
    else:
        raise ValueError("service campaign window is not a registered V19 or V22–V31 path")
    return {
        "path": window.path,
        "sha256": window.sha256,
        "stage_scope": stage_scope,
        "version": campaign_version,
    }


def _v30_environment_window_path(campaign_registration: Mapping[str, Any]) -> str:
    """Export the validated service campaign path in its absolute form."""
    return str(Path(campaign_registration["path"]).resolve())


def _unified_cgroup_membership(pid: int | str = "self") -> str | None:
    try:
        lines = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            return fields[2]
    return None


def _read_case(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    return raw, tomllib.loads(raw)


def render_stage_input(
    canonical_text: str,
    stop_stage: str,
    *,
    component_resume_manifest_path: str | None = None,
    component_resume_manifest_sha256: str | None = None,
) -> str:
    """Render a V20 stage input, optionally binding one target component resume manifest."""

    matches = list(
        re.finditer(
            r'(?m)^task40_execution_stop_stage = "([a-z_]+)"\s*$',
            canonical_text,
        )
    )
    if len(matches) != 1 or matches[0].group(1) != "preflight":
        raise ValueError("canonical V20 input must contain exactly one preflight stop-stage line")
    replaced = canonical_text[: matches[0].start(1)] + stop_stage + canonical_text[matches[0].end(1) :]
    original_data = tomllib.loads(canonical_text)
    changed_data = tomllib.loads(replaced)
    original_data["execution"]["task40_execution_stop_stage"] = stop_stage
    profile = str(original_data.get("solver", {}).get("preconditioner", ""))
    v22_profile = "task40extra_v22_p6_y_orbit_target_original_ny8_operator_probe_v1"
    if stop_stage == "target_operator_probe":
        if profile != v22_profile:
            raise ValueError("target_operator_probe requires the dedicated V22 profile/input")
        original_data["execution"]["task40_v22_operator_probe_authorized"] = True
        replaced, count = re.subn(
            r'(?m)^task40_v22_operator_probe_authorized = false\s*$',
            "task40_v22_operator_probe_authorized = true",
            replaced,
            count=1,
        )
        if count != 1:
            raise ValueError("V22 canonical input must carry the explicit false authorization field")
        changed_data = tomllib.loads(replaced)
    elif profile == v22_profile:
        original_data["execution"]["task40_v22_operator_probe_authorized"] = False
    if (component_resume_manifest_path is None) != (
        component_resume_manifest_sha256 is None
    ):
        raise ValueError("component resume manifest path and SHA-256 must be supplied together")
    if component_resume_manifest_path is not None:
        if (
            stop_stage != "local_port_components"
            or Path(component_resume_manifest_path).is_absolute()
            or ".." in Path(component_resume_manifest_path).parts
            or not re.fullmatch(r"[0-9a-f]{64}", str(component_resume_manifest_sha256))
        ):
            raise ValueError("component resume input is restricted to a hash-bound target local-port stage")
        replacement_line = (
            f'task40_execution_stop_stage = "{stop_stage}"\n'
            f'task40_component_resume_manifest_path = "{component_resume_manifest_path}"\n'
            f'task40_component_resume_manifest_sha256 = "{component_resume_manifest_sha256}"'
        )
        replaced, count = re.subn(
            r'(?m)^task40_execution_stop_stage = "[a-z_]+"\s*$',
            replacement_line,
            replaced,
            count=1,
        )
        if count != 1:
            raise ValueError("cannot insert the V20 component resume manifest into the execution block")
        original_data["execution"]["task40_component_resume_manifest_path"] = (
            component_resume_manifest_path
        )
        original_data["execution"]["task40_component_resume_manifest_sha256"] = (
            component_resume_manifest_sha256
        )
        changed_data = tomllib.loads(replaced)
    if original_data != changed_data:
        raise ValueError("stage input changes fields beyond the explicit V20 stop/resume execution fields")
    return replaced


def prepare_component_resume_input(
    manifest_path: str,
    manifest_sha256: str,
    *,
    repo_root: Path = ROOT,
) -> dict[str, str]:
    """Create one ignored local-port input bound to a prepared resume manifest."""

    relative_manifest = Path(manifest_path)
    if relative_manifest.is_absolute() or ".." in relative_manifest.parts:
        raise ValueError("V20 component resume manifest path must be repo-relative")
    manifest = repo_root / relative_manifest
    if not manifest.is_file() or _sha256_file(manifest) != manifest_sha256:
        raise ValueError("V20 component resume manifest is missing or has the wrong hash")
    canonical = repo_root / V20_INPUTS[
        "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
    ][0]
    canonical_text = canonical.read_text(encoding="utf-8")
    staged_text = render_stage_input(
        canonical_text,
        "local_port_components",
        component_resume_manifest_path=manifest_path,
        component_resume_manifest_sha256=manifest_sha256,
    )
    destination = (
        repo_root
        / ARTIFACT_ROOT
        / "stage_inputs/local_port_components_resume/target_original_ny8_resource_pilot_v20.dat"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    relative_destination = destination.relative_to(repo_root)
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(relative_destination)],
        cwd=repo_root,
        check=False,
    )
    if ignored.returncode != 0:
        raise RuntimeError(f"component resume input is not git-ignored: {relative_destination}")
    if destination.exists():
        if destination.read_text(encoding="utf-8") != staged_text:
            raise FileExistsError(f"refusing to replace a different component resume input: {destination}")
    else:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(staged_text)
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "input_path": str(relative_destination),
        "input_sha256": _sha256_bytes(staged_text.encode("utf-8")),
        "resume_manifest_path": manifest_path,
        "resume_manifest_sha256": manifest_sha256,
    }


def _validate_service_stage_input_variant(
    input_path: Path,
    canonical_path: Path,
    canonical_text: str,
    stop_stage: str,
    data: dict[str, Any],
    *,
    repo_root: Path,
    v30_contract: bool = False,
    v31_contract: Mapping[str, Any] | None = None,
) -> None:
    """Validate the exact pre-run input variant accepted by ``run_service``."""

    execution = data.get("execution", {})
    if v30_contract:
        if (
            data.get("run_id") != "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
            or data.get("solver", {}).get("preconditioner") != V30_TARGET_PROFILE
            or stop_stage != "full"
            or execution.get("task40_target_heavy_authorized") is not True
        ):
            raise ValueError("V30 execution contract is restricted to the exact full target reference case")
        selector_binding = execution.get("task40_v30_q_csr_binding")
        factor_config = execution.get("task40_v30_factor_bank_config")
        if (
            not isinstance(selector_binding, Mapping)
            or set(selector_binding) != {"schema", "selector_path", "selector_sha256"}
            or selector_binding.get("schema") != "task40extra.review_v30_q_csr_worker_binding.v1"
            or not re.fullmatch(r"[0-9a-f]{64}", str(selector_binding.get("selector_sha256", "")))
            or not isinstance(factor_config, Mapping)
            or factor_config.get("schema") != "task40extra.review_v30_all_q_factor_bank.v1"
            or factor_config.get("require_two_strict_rhs") is not True
        ):
            raise ValueError("V30 input needs its bound partial q selector and all-q factor-bank policy")
        selector_path = Path(str(selector_binding["selector_path"]))
        selector_path = (selector_path if selector_path.is_absolute() else repo_root / selector_path).resolve()
        v30_roots = (
            (repo_root / V30_ARTIFACT_ROOT).resolve(),
            (repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_preparation").resolve(),
        )
        if not any(selector_path.is_relative_to(root) for root in v30_roots):
            raise ValueError("V30 q selector must remain in the registered V30 artifact roots")
        if not selector_path.is_file() or _sha256_file(selector_path) != selector_binding["selector_sha256"]:
            raise ValueError("V30 q selector is missing or changed")
        output_directory = Path(str(factor_config.get("output_directory", "")))
        output_directory = (output_directory if output_directory.is_absolute() else repo_root / output_directory).resolve()
        if not any(output_directory.is_relative_to(root) for root in v30_roots):
            raise ValueError("V30 factor-bank output directory must remain in the V30 artifact roots")
        expected_data = tomllib.loads(render_stage_input(canonical_text, stop_stage))
        actual_base = json.loads(json.dumps(data))
        for name in (
            "task40_target_heavy_authorized",
            "task40_v30_q_csr_binding",
            "task40_v30_factor_bank_config",
        ):
            actual_base["execution"].pop(name, None)
            expected_data["execution"].pop(name, None)
        if actual_base != expected_data:
            raise ValueError("V30 stage input changes fields outside its exact target-operation bindings")
        if input_path.name != canonical_path.name:
            raise ValueError("V30 full input must retain the canonical DAT basename")
        from src.runners.task40_v30_contract import require_v30_input_identity

        expected_source_sha = None
        if (repo_root / ".git").exists():
            expected_source_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
            ).strip()
        require_v30_input_identity(
            canonical_path,
            input_path,
            repo_root=repo_root,
            expected_source_sha=expected_source_sha,
        )
        return
    if v31_contract is not None:
        from src.runners.task40_v31_contract import (
            V31_FACTOR_BANK_SCHEMA,
            V31_PROFILE,
            V31_Q_CSR_BINDING_SCHEMA,
            require_v31_input_identity,
        )

        contract_execution = v31_contract.get("execution")
        source_freeze = v31_contract.get("source_freeze")
        selector = execution.get("task40_v31_q_csr_binding")
        factor = execution.get("task40_v31_factor_bank_config")
        if (
            data.get("run_id") != "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
            or data.get("solver", {}).get("preconditioner") != V31_PROFILE
            or stop_stage != "full"
            or execution.get("task40_target_heavy_authorized") is not True
            or not isinstance(contract_execution, Mapping)
            or not isinstance(source_freeze, Mapping)
            or not isinstance(selector, Mapping)
            or selector.get("schema") != V31_Q_CSR_BINDING_SCHEMA
            or not isinstance(factor, Mapping)
            or factor.get("schema") != V31_FACTOR_BANK_SCHEMA
        ):
            raise ValueError("V31 execution contract is restricted to its exact full target case")
        selector_path = Path(str(selector.get("selector_path", "")))
        selector_path = (
            selector_path if selector_path.is_absolute() else repo_root / selector_path
        ).resolve()
        contract_selector = Path(str(contract_execution.get("selector_path", "")))
        contract_selector = (
            contract_selector
            if contract_selector.is_absolute()
            else repo_root / contract_selector
        ).resolve()
        if (
            selector_path != contract_selector
            or selector.get("selector_sha256") != contract_execution.get("selector_sha256")
        ):
            raise ValueError("V31 stage selector differs from its approved execution contract")
        expected_data = tomllib.loads(render_stage_input(canonical_text, stop_stage))
        expected_execution = expected_data["execution"]
        expected_execution["task40_target_heavy_authorized"] = True
        expected_execution["task40_v31_q_csr_binding"] = dict(selector)
        expected_execution["task40_v31_factor_bank_config"] = dict(factor)
        if data != expected_data:
            raise ValueError("V31 stage input changes fields outside its registered route")
        if input_path.name != canonical_path.name:
            raise ValueError("V31 full input must retain the canonical DAT basename")
        require_v31_input_identity(
            canonical_path,
            input_path,
            repo_root=repo_root,
            source_sha=str(source_freeze.get("source_sha", "")),
            selector_sha256=str(contract_execution.get("selector_sha256", "")),
        )
        return
    resume_path = execution.get("task40_component_resume_manifest_path")
    resume_sha256 = execution.get("task40_component_resume_manifest_sha256")
    if (resume_path is None) != (resume_sha256 is None):
        raise ValueError("component resume manifest path and SHA-256 must be supplied together")
    if resume_path is None and resume_sha256 is None:
        expected_text = render_stage_input(canonical_text, stop_stage)
    else:
        if (
            data.get("run_id")
            != "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
            or data.get("solver", {}).get("preconditioner")
            != "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
            or stop_stage != "local_port_components"
        ):
            raise ValueError(
                "component resume input is restricted to the exact target local_port_components case"
            )
        expected_text = render_stage_input(
            canonical_text,
            stop_stage,
            component_resume_manifest_path=resume_path,
            component_resume_manifest_sha256=resume_sha256,
        )

    if input_path == canonical_path:
        if stop_stage != "preflight":
            raise ValueError("canonical V20 inputs are immutable preflight inputs")
        return
    if input_path.name != canonical_path.name or input_path.read_text(encoding="utf-8") != expected_text:
        raise ValueError(
            "stage input is not an exact same-basename variant of the canonical input"
        )
    allowed_stage_roots = [(repo_root / ARTIFACT_ROOT / "stage_inputs").resolve()]
    if stop_stage in V25_SELECTED_Q_STAGES:
        allowed_stage_roots.append(
            (repo_root / V25_ARTIFACT_ROOT / "stage_inputs").resolve()
        )
    if stop_stage in V26_SELECTED_Q_STAGES:
        allowed_stage_roots.append(
            (repo_root / V26_ARTIFACT_ROOT / "stage_inputs").resolve()
        )
    if stop_stage in V27_SELECTED_Q_STAGES:
        allowed_stage_roots.append(
            (repo_root / V27_ARTIFACT_ROOT / "stage_inputs").resolve()
        )
    if stop_stage in V28_SELECTED_Q_STAGES:
        allowed_stage_roots.append(
            (repo_root / V28_ARTIFACT_ROOT / "stage_inputs").resolve()
        )
    if not any(input_path.is_relative_to(path) for path in allowed_stage_roots):
        raise ValueError("noncanonical V20/V25/V26 stage input must live in its ignored stage_inputs artifact")



def prepare_v25_selected_q_input(
    stop_stage: str = "selected_reference_q_build_only",
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Create the ignored, input/window-bound stage input and operation selector."""
    if stop_stage not in V25_SELECTED_Q_STAGES:
        raise ValueError("V25 selected-q preparation requires one of the registered q0 stages")
    canonical_relative, _ = V20_INPUTS[V25_TARGET_PROFILE]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    canonical_data = tomllib.loads(canonical_text)
    if canonical_data.get("solver", {}).get("preconditioner") != V25_TARGET_PROFILE:
        raise ValueError("V25 selected-q canonical input/profile identity changed")
    campaign_path = (repo_root / TASK40_V25_CAMPAIGN_WINDOW).resolve()
    if not campaign_path.is_file() or _sha256_file(campaign_path) != TASK40_V25_CAMPAIGN_SHA256:
        raise ValueError("V25 selected-q preparation requires the frozen campaign window")
    rendered = render_stage_input(canonical_text, stop_stage).encode("utf-8")
    stage_directory = (repo_root / V25_ARTIFACT_ROOT / "stage_inputs" / stop_stage).resolve()
    stage_directory.mkdir(parents=True, exist_ok=True)
    input_path = stage_directory / canonical_path.name
    selector_path = stage_directory / "selected_operation.json"
    for destination, payload in (
        (input_path, rendered),
        (
            selector_path,
            (
                json.dumps(
                    {
                        "schema": "task40extra.review_v25_selected_operation.v1",
                        "operation": V25_SELECTED_OPERATION_BY_STAGE[stop_stage],
                        "campaign_window_sha256": TASK40_V25_CAMPAIGN_SHA256,
                        "input_sha256": _sha256_bytes(rendered),
                        "model_profile": V25_TARGET_PROFILE,
                        "stop_stage": stop_stage,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
        ),
    ):
        relative = destination.relative_to(repo_root.resolve())
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(relative)],
            cwd=repo_root,
            check=False,
        )
        if ignored.returncode != 0:
            raise RuntimeError(f"V25 selected-q artifact is not git-ignored: {relative}")
        if destination.exists():
            if destination.read_bytes() != payload:
                raise FileExistsError(f"refusing to replace different V25 selected-q artifact: {destination}")
        else:
            with destination.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    return {
        "schema": "task40extra.review_v25_selected_q_stage_input.v1",
        "stop_stage": stop_stage,
        "operation": V25_SELECTED_OPERATION_BY_STAGE[stop_stage],
        "canonical_input_sha256": _sha256_file(canonical_path),
        "stage_input_path": str(input_path),
        "stage_input_sha256": _sha256_file(input_path),
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_file(selector_path),
        "campaign_window_path": str(campaign_path),
        "campaign_window_sha256": TASK40_V25_CAMPAIGN_SHA256,
        "launch_command": (
            "bash scripts/run_case_in_user_service.sh "
            f"{input_path} --task40-v10-campaign-window {TASK40_V25_CAMPAIGN_WINDOW} "
            f"--v25-selected-operation-selector {selector_path}"
        ),
    }


def prepare_v26_selected_q_input(
    stop_stage: str = "selected_reference_q_build_only",
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Create an ignored V26 stage/selector bound to the prior raw producer and this window."""
    if stop_stage not in V26_SELECTED_Q_STAGES:
        raise ValueError("V26 selected-q preparation requires a registered saved-consumer stage")
    canonical_relative, _ = V20_INPUTS[V26_TARGET_PROFILE]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    canonical_data = tomllib.loads(canonical_text)
    if canonical_data.get("solver", {}).get("preconditioner") != V26_TARGET_PROFILE:
        raise ValueError("V26 selected-q canonical input/profile identity changed")
    campaign_path = (repo_root / TASK40_V26_CAMPAIGN_WINDOW).resolve()
    if not campaign_path.is_file() or _sha256_file(campaign_path) != TASK40_V26_CAMPAIGN_SHA256:
        raise ValueError("V26 selected-q preparation requires the frozen campaign window")
    load_fixed_campaign_window(campaign_path, require_current_boot=True)
    rendered = render_stage_input(canonical_text, stop_stage).encode("utf-8")
    stage_directory = (repo_root / V26_ARTIFACT_ROOT / "stage_inputs" / stop_stage).resolve()
    stage_directory.mkdir(parents=True, exist_ok=True)
    input_path = stage_directory / canonical_path.name
    selector_path = stage_directory / "selected_operation.json"
    if input_path.exists():
        if input_path.read_bytes() != rendered:
            raise FileExistsError(f"refusing to replace different V26 stage input: {input_path}")
    else:
        with input_path.open("xb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
    producer_identity = verify_v26_saved_producer_metadata(
        producer_root=repo_root / V26_PRODUCER_RUN_RELATIVE,
        repo_root=repo_root,
    )
    selector = {
        "schema": "task40extra.review_v26_selected_operation.v1",
        "operation": V26_SELECTED_OPERATION_BY_STAGE[stop_stage],
        "campaign_window_sha256": TASK40_V26_CAMPAIGN_SHA256,
        "input_sha256": _sha256_bytes(rendered),
        "model_profile": V26_TARGET_PROFILE,
        "stop_stage": stop_stage,
        "producer_identity": producer_identity,
    }
    selector_payload = (
        json.dumps(selector, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if selector_path.exists():
        if selector_path.read_bytes() != selector_payload:
            raise FileExistsError(f"refusing to replace different V26 selector: {selector_path}")
    else:
        with selector_path.open("xb") as stream:
            stream.write(selector_payload)
            stream.flush()
            os.fsync(stream.fileno())
    for destination in (input_path, selector_path):
        relative = destination.relative_to(repo_root.resolve())
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(relative)], cwd=repo_root, check=False
        )
        if ignored.returncode != 0:
            raise RuntimeError(f"V26 selected-q artifact is not git-ignored: {relative}")
    return {
        "schema": "task40extra.review_v26_selected_q_stage_input.v1",
        "stop_stage": stop_stage,
        "operation": V26_SELECTED_OPERATION_BY_STAGE[stop_stage],
        "canonical_input_sha256": _sha256_file(canonical_path),
        "stage_input_path": str(input_path),
        "stage_input_sha256": _sha256_file(input_path),
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_file(selector_path),
        "producer_identity": producer_identity,
        "campaign_window_path": str(campaign_path),
        "campaign_window_sha256": TASK40_V26_CAMPAIGN_SHA256,
        "launch_command": (
            "bash scripts/run_case_in_user_service.sh "
            f"{input_path} --task40-v10-campaign-window {TASK40_V26_CAMPAIGN_WINDOW} "
            f"--v26-selected-operation-selector {selector_path}"
        ),
    }


def prepare_v27_saved_q0_input(
    stop_stage: str = "selected_reference_q_csr",
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Create a V27 selector bound to the immutable V26 donor and fixed V27 window."""
    if stop_stage not in V27_SELECTED_Q_STAGES:
        raise ValueError("V27 preparation only supports the reviewed saved-only q0 CSR stage")
    canonical_relative, _ = V20_INPUTS[V27_TARGET_PROFILE]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    canonical_data = tomllib.loads(canonical_text)
    if canonical_data.get("solver", {}).get("preconditioner") != V27_TARGET_PROFILE:
        raise ValueError("V27 selected-q canonical input/profile identity changed")
    campaign_path = (repo_root / TASK40_V27_CAMPAIGN_WINDOW).resolve()
    if not campaign_path.is_file() or _sha256_file(campaign_path) != TASK40_V27_CAMPAIGN_SHA256:
        raise ValueError("V27 preparation requires the existing fixed campaign window")
    if _sha256_file(repo_root / TASK40_V27_CAMPAIGN_RECEIPT) != TASK40_V27_CAMPAIGN_RECEIPT_SHA256:
        raise ValueError("V27 preparation requires the fixed registration receipt")
    load_fixed_campaign_window(campaign_path, require_current_boot=True)
    donor_import = verify_v27_v26_donor_import(repo_root=repo_root)
    rendered = render_stage_input(canonical_text, stop_stage).encode("utf-8")
    stage_directory = (
        repo_root / V27_ARTIFACT_ROOT / "stage_inputs" / stop_stage
    ).resolve()
    stage_directory.mkdir(parents=True, exist_ok=True)
    input_path = stage_directory / canonical_path.name
    selector_path = stage_directory / "selected_operation.json"
    selector = {
        "schema": "task40extra.review_v27_saved_q0_operation.v1",
        "operation": V27_SELECTED_OPERATION_BY_STAGE[stop_stage],
        "campaign_window_sha256": TASK40_V27_CAMPAIGN_SHA256,
        "input_sha256": _sha256_bytes(rendered),
        "model_profile": V27_TARGET_PROFILE,
        "stop_stage": stop_stage,
        "donor_import": donor_import,
    }
    selector_payload = (
        json.dumps(selector, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    for destination, payload in ((input_path, rendered), (selector_path, selector_payload)):
        relative = destination.relative_to(repo_root.resolve())
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(relative)], cwd=repo_root, check=False
        )
        if ignored.returncode != 0:
            raise RuntimeError(f"V27 selected-q artifact is not git-ignored: {relative}")
        if destination.exists():
            if destination.read_bytes() != payload:
                raise FileExistsError(f"refusing to replace different V27 artifact: {destination}")
        else:
            with destination.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    return {
        "schema": "task40extra.review_v27_saved_q0_stage_input.v1",
        "stop_stage": stop_stage,
        "operation": V27_SELECTED_OPERATION_BY_STAGE[stop_stage],
        "canonical_input_sha256": _sha256_file(canonical_path),
        "stage_input_path": str(input_path),
        "stage_input_sha256": _sha256_file(input_path),
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_file(selector_path),
        "donor_import": donor_import,
        "campaign_window_path": str(campaign_path),
        "campaign_window_sha256": TASK40_V27_CAMPAIGN_SHA256,
        "launch_command": (
            "bash scripts/run_case_in_user_service.sh "
            f"{input_path} --task40-v10-campaign-window {TASK40_V27_CAMPAIGN_WINDOW} "
            f"--v27-saved-q0-selector {selector_path}"
        ),
    }


def prepare_v28_q0_continuation_input(
    stop_stage: str = "selected_reference_q_csr",
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Bind the V28 service input to the immutable V27 pattern and V26 donor."""
    if stop_stage not in V28_SELECTED_Q_STAGES:
        raise ValueError("V28 preparation only supports the existing-manifest q0 continuation")
    campaign_path = (repo_root / TASK40_V28_CAMPAIGN_WINDOW).resolve()
    receipt_path = (repo_root / TASK40_V28_CAMPAIGN_RECEIPT).resolve()
    if (
        not campaign_path.is_file()
        or _sha256_file(campaign_path) != TASK40_V28_CAMPAIGN_SHA256
        or not receipt_path.is_file()
        or _sha256_file(receipt_path) != TASK40_V28_CAMPAIGN_RECEIPT_SHA256
    ):
        raise ValueError("V28 preparation requires its immutable window and registration receipt")
    load_fixed_campaign_window(campaign_path, require_current_boot=True)
    pattern_path = (repo_root / V28_PATTERN_MANIFEST_RELATIVE).resolve()
    if (
        not pattern_path.is_file()
        or _sha256_file(pattern_path) != V28_PATTERN_MANIFEST_SHA256
    ):
        raise ValueError("V28 preparation requires the exact incomplete V27 q0 pattern")
    pattern = json.loads(pattern_path.read_text(encoding="utf-8"))
    if (
        pattern.get("schema") != "task40extra.review_v27_saved_q0_csr.v1"
        or pattern.get("status") != "NUMERIC_FILL_INCOMPLETE"
        or pattern.get("shape") != [777_644, 777_644]
        or pattern.get("stored_structural_slots") != 577_061_168
        or pattern.get("csr_artifacts", {}).get("data", {}).get("sha256") is not None
    ):
        raise ValueError("V27 pattern is not the reviewed incomplete numeric continuation input")
    canonical_relative, _ = V20_INPUTS[V28_TARGET_PROFILE]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    canonical_data = tomllib.loads(canonical_text)
    if canonical_data.get("solver", {}).get("preconditioner") != V28_TARGET_PROFILE:
        raise ValueError("V28 continuation canonical input/profile identity changed")
    donor_import = verify_v27_v26_donor_import(repo_root=repo_root)
    rendered = render_stage_input(canonical_text, stop_stage).encode("utf-8")
    stage_directory = (
        repo_root / V28_ARTIFACT_ROOT / "stage_inputs" / stop_stage
    ).resolve()
    stage_directory.mkdir(parents=True, exist_ok=True)
    input_path = stage_directory / canonical_path.name
    selector_path = stage_directory / "q0_continuation.json"
    continuation_path = pattern_path.with_name(V28_CONTINUATION_MANIFEST_NAME)
    selector = {
        "schema": "task40extra.review_v28_q0_continuation_operation.v1",
        "operation": V28_CONTINUATION_OPERATION,
        "campaign_window_sha256": TASK40_V28_CAMPAIGN_SHA256,
        "input_sha256": _sha256_bytes(rendered),
        "model_profile": V28_TARGET_PROFILE,
        "stop_stage": stop_stage,
        "donor_import": donor_import,
        "pattern_manifest_path": str(pattern_path),
        "pattern_manifest_sha256": V28_PATTERN_MANIFEST_SHA256,
        "continuation_manifest_path": str(continuation_path),
        "continuation_policy": V28_CONTINUATION_POLICY,
    }
    selector_payload = (
        json.dumps(selector, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    for destination, payload in ((input_path, rendered), (selector_path, selector_payload)):
        relative = destination.relative_to(repo_root.resolve())
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(relative)], cwd=repo_root, check=False
        )
        if ignored.returncode != 0:
            raise RuntimeError(f"V28 selected-q artifact is not git-ignored: {relative}")
        if destination.exists():
            if destination.read_bytes() != payload:
                raise FileExistsError(f"refusing to replace different V28 artifact: {destination}")
        else:
            with destination.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    return {
        "schema": "task40extra.review_v28_q0_continuation_stage_input.v1",
        "stop_stage": stop_stage,
        "operation": V28_CONTINUATION_OPERATION,
        "canonical_input_sha256": _sha256_file(canonical_path),
        "stage_input_path": str(input_path),
        "stage_input_sha256": _sha256_file(input_path),
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_file(selector_path),
        "donor_import": donor_import,
        "pattern_manifest_path": str(pattern_path),
        "pattern_manifest_sha256": V28_PATTERN_MANIFEST_SHA256,
        "continuation_manifest_path": str(continuation_path),
        "campaign_window_path": str(campaign_path),
        "campaign_window_sha256": TASK40_V28_CAMPAIGN_SHA256,
        "launch_command": (
            "bash scripts/run_case_in_user_service.sh "
            f"{input_path} --task40-v10-campaign-window {TASK40_V28_CAMPAIGN_WINDOW} "
            f"--v28-q0-continuation-selector {selector_path}"
        ),
    }


def _v30_q0_csr_shape(donor_shape: Any, q0_map_shape: Any) -> list[int]:
    """Use the donor CSR shape, not the rectangular local-to-q map shape."""
    if (
        not isinstance(donor_shape, list)
        or len(donor_shape) != 2
        or any(type(value) is not int or value <= 0 for value in donor_shape)
        or not isinstance(q0_map_shape, tuple)
        or len(q0_map_shape) != 2
        or type(q0_map_shape[1]) is not int
        or donor_shape != [q0_map_shape[1], q0_map_shape[1]]
    ):
        raise ValueError("V30 q0 CSR shape must be square and match the saved q-map column count")
    return list(donor_shape)


def prepare_v30_full_input(repo_root: Path = ROOT) -> dict[str, Any]:
    """Prepare the hash-bound q0 import, corrected paths, and V30 full-stage DAT."""
    import numpy as np
    from scipy import sparse

    from src.io.input_validation import load_and_resolve
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES
    from src.runners.task40_v30_contract import (
        V30_ABI_RECEIPT_RELATIVE,
        V30_ARTIFACT_ROOT_RELATIVE,
        V30_CANONICAL_INPUT_RELATIVE,
        V30_CANONICAL_INPUT_SHA256,
        V30_JIT_CACHE_RELATIVE,
        V30_OLD_EXECUTION_CONTRACT_SHA256,
        V30_Q0_DONOR,
        V30_RUNTIME_RELATIVE,
        V30ContractError,
        require_authorized_contract,
        require_v30_input_identity,
    )
    from src.solvers.task40_v20_mode_inventory import load_v20_target_mode_inventory
    from src.solvers.task40_v30_qualified_q_csr import (
        V28_Q0_CSR_MANIFEST_SHA256,
        V28_Q0_DONOR_INPUT_SHA256,
        V28_Q0_NATIVE_QUALIFICATION_SHA256,
        V30_Q0_LEGACY_IMPORT_SCHEMA,
        V30_Q_CSR_SELECTOR_SCHEMA,
    )
    from src.solvers.task40_v30_selected_q_csr import selected_q_operator_identity

    root = Path(repo_root).resolve()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if branch != "task40extra_0p7nm_engineering" or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    ).strip():
        raise RuntimeError("V30 prepare requires the frozen clean Task40 execution branch")

    artifact_root = (root / V30_ARTIFACT_ROOT_RELATIVE).resolve()
    attempt_root = artifact_root / "attempts" / source_sha
    old_contract_path = artifact_root / "execution_contract_v30.json"
    contract_path = artifact_root / "execution_contract_v30_fix01.json"
    if (
        not old_contract_path.is_file()
        or _sha256_file(old_contract_path) != V30_OLD_EXECUTION_CONTRACT_SHA256
    ):
        raise ValueError("V30 prepare requires the preserved hash-pinned original contract")
    contract = json.loads(old_contract_path.read_text(encoding="utf-8"))
    execution = contract.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("V30 original execution contract omits execution fields")
    supplied_runtime = Path(str(execution.get("runtime_prefix", "")))
    supplied_runtime = (supplied_runtime if supplied_runtime.is_absolute() else root / supplied_runtime).resolve()
    if supplied_runtime != (root / V30_RUNTIME_RELATIVE).resolve():
        raise ValueError("V30 fix01 may only correct the approved ABI/JIT paths")
    execution["abi_receipt_path"] = str((root / V30_ABI_RECEIPT_RELATIVE).resolve())
    execution["jit_cache"] = str((root / V30_JIT_CACHE_RELATIVE).resolve())
    contract_bytes = (json.dumps(contract, ensure_ascii=False, indent=2) + "\n").encode()

    def write_ignored_immutable(path: Path, payload: bytes) -> None:
        relative = path.resolve().relative_to(root).as_posix()
        if subprocess.run(["git", "check-ignore", "-q", relative], cwd=root, check=False).returncode != 0:
            raise RuntimeError(f"V30 preparation output is not git-ignored: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise FileExistsError(f"refusing to replace different V30 artifact: {path}")
            return
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    write_ignored_immutable(contract_path, contract_bytes)
    fixed_contract, contract_sha = require_authorized_contract(
        contract_path, current_root=root, current_hostname=socket.gethostname()
    )
    canonical_path = (root / V30_CANONICAL_INPUT_RELATIVE).resolve()
    canonical_text = canonical_path.read_text(encoding="utf-8")
    canonical_sha = _sha256_file(canonical_path)
    if canonical_sha != V30_CANONICAL_INPUT_SHA256:
        raise ValueError("V30 canonical scientific DAT SHA changed")

    donor = V30_Q0_DONOR
    donor_manifest_path = (root / donor["manifest_relative_path"]).resolve()
    native_path = (root / donor["native_qualification_relative_path"]).resolve()
    if (
        _sha256_file(donor_manifest_path) != V28_Q0_CSR_MANIFEST_SHA256
        or _sha256_file(native_path) != V28_Q0_NATIVE_QUALIFICATION_SHA256
    ):
        raise ValueError("V30 pinned V28 q0 manifest/native qualification changed")
    donor_manifest = json.loads(donor_manifest_path.read_text(encoding="utf-8"))
    native_qualification = json.loads(native_path.read_text(encoding="utf-8"))
    fill = donor_manifest.get("numeric_fill_identity", {})
    old_fill_identity = fill.get("execution_identity", {})
    producer = fill.get("donor_identity", {}).get("producer_identity", {})
    if (
        donor_manifest.get("status") != "COMPLETE_CSR"
        or donor_manifest.get("donor_identity_sha256") != donor["identity_sha256"]
        or native_qualification.get("status") != donor["native_qualification_status"]
        or old_fill_identity.get("input_sha256") != V28_Q0_DONOR_INPUT_SHA256
        or not isinstance(producer, Mapping)
        or not isinstance(old_fill_identity, Mapping)
    ):
        raise ValueError("V30 pinned V28 donor is not COMPLETE/PASS with the accepted old identity")
    pattern_path = (root / V28_PATTERN_MANIFEST_RELATIVE).resolve()
    pattern_sha = _sha256_file(pattern_path)
    if (
        pattern_sha != V28_PATTERN_MANIFEST_SHA256
        or native_qualification.get("original_pattern_manifest", {}).get("sha256") != pattern_sha
    ):
        raise ValueError("V30 original q0 pattern manifest differs from the pinned V28 donor")

    producer_run = (root / str(producer.get("producer_run_directory", ""))).resolve()
    if not producer_run.is_relative_to(root):
        raise ValueError("V30 q0 map/H producer escaped the approved repository root")
    payloads = producer.get("payloads", [])
    payload_by_name = {
        Path(str(record.get("path", ""))).name: record
        for record in payloads
        if isinstance(record, Mapping)
    }

    def verified_payload(name: str) -> Path:
        record = payload_by_name.get(name)
        if not isinstance(record, Mapping):
            raise ValueError(f"V30 q0 donor omits saved payload {name}")
        path = (producer_run / str(record.get("path", ""))).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != record.get("bytes")
            or _sha256_file(path) != record.get("sha256")
        ):
            raise ValueError(f"V30 saved q0 payload is missing or changed: {name}")
        return path

    q0_map = sparse.load_npz(verified_payload("v25_selected_q0_map.npz")).tocsr()
    q0_csr_shape = _v30_q0_csr_shape(donor_manifest.get("shape"), q0_map.shape)
    local_h = np.load(
        verified_payload("v25_selected_q0_local_H_p.npy"), allow_pickle=False, mmap_mode="r"
    )
    verified_payload("v25_selected_q0_original_to_active_int32.npy")
    resolved = load_and_resolve(canonical_path).as_jsonable()
    modes, _rows, _mode_sha, _mode_facts = load_v20_target_mode_inventory(resolved)
    profile = TASK40_P6_PERIODIC_PROFILES[V30_TARGET_PROFILE]
    operator_identity = selected_q_operator_identity(
        scientific_input_sha256=canonical_sha,
        profile_identity=profile.identity(),
        ordered_modes=modes,
        q_map=q0_map,
        original_h=local_h,
    )
    matrix_source = {
        "source_sha": str(old_fill_identity.get("source_sha", "")),
        "window_sha256": str(old_fill_identity.get("campaign_window_sha256", "")),
    }
    execution_identity = {
        "source_sha": source_sha,
        "window_sha256": str(fixed_contract["execution"]["campaign_window_sha256"]),
    }
    legacy_identity = {
        "input_sha256": str(old_fill_identity["input_sha256"]),
        "physical_model_sha256": str(old_fill_identity["physical_model_sha256"]),
        "mode_manifest_sha256": str(old_fill_identity["mode_manifest_sha256"]),
        "manifest_sha256": V28_Q0_CSR_MANIFEST_SHA256,
        "native_qualification_sha256": V28_Q0_NATIVE_QUALIFICATION_SHA256,
    }
    selector_path = attempt_root / "q0_selector_v30_partial.json"
    selector_relative = selector_path.relative_to(root).as_posix()
    selector = {
        "schema": V30_Q_CSR_SELECTOR_SCHEMA,
        "profile": V30_TARGET_PROFILE,
        "q_csr_entries": [
            {
                "q_index": 0,
                "twist_index": 0,
                "shape": q0_csr_shape,
                "operator_identity": operator_identity,
                "matrix_source_identity": matrix_source,
                "execution_identity": execution_identity,
                "csr_manifest": {
                    "path": donor_manifest_path.relative_to(root).as_posix(),
                    "sha256": V28_Q0_CSR_MANIFEST_SHA256,
                },
                "native_qualification": {
                    "path": native_path.relative_to(root).as_posix(),
                    "sha256": V28_Q0_NATIVE_QUALIFICATION_SHA256,
                    "status": donor["native_qualification_status"],
                },
                "legacy_q0_import": {
                    "schema": V30_Q0_LEGACY_IMPORT_SCHEMA,
                    "v28_identity": legacy_identity,
                    "original_pattern_manifest": {
                        "path": pattern_path.relative_to(root).as_posix(),
                        "sha256": pattern_sha,
                    },
                },
            }
        ],
    }
    selector_bytes = (json.dumps(selector, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    selector_sha = hashlib.sha256(selector_bytes).hexdigest()
    input_path = attempt_root / "stage_inputs" / "full" / canonical_path.name
    factor_directory = attempt_root / "factor_bank"
    rendered = render_stage_input(canonical_text, "full")
    overrides = (
        "task40_target_heavy_authorized = true\n"
        "task40_v30_q_csr_binding = { schema = \"task40extra.review_v30_q_csr_worker_binding.v1\", "
        f"selector_path = \"{selector_relative}\", selector_sha256 = \"{selector_sha}\" }}\n"
        "task40_v30_factor_bank_config = { schema = \"task40extra.review_v30_all_q_factor_bank.v1\", "
        f"output_directory = \"{factor_directory.relative_to(root).as_posix()}\", require_two_strict_rhs = true }}\n"
    )
    authorization_line = "task40_target_heavy_authorized = false\n"
    if rendered.count(authorization_line) != 1:
        raise ValueError("V30 canonical DAT must contain one false heavy-run authorization line")
    staged_bytes = rendered.replace(authorization_line, overrides, 1).encode("utf-8")
    write_ignored_immutable(selector_path, selector_bytes)
    write_ignored_immutable(input_path, staged_bytes)
    identity = require_v30_input_identity(
        canonical_path,
        input_path,
        repo_root=root,
        expected_source_sha=source_sha,
    )
    if identity["staged_input_sha256"] != hashlib.sha256(staged_bytes).hexdigest():
        raise V30ContractError("V30 staged DAT changed while preparing the input")

    checker_command = [
        str((root / V30_RUNTIME_RELATIVE) / "bin/python"),
        "scripts/task40_v20_service_workflow.py",
        "check-partial",
        "--input",
        str(input_path),
        "--summary",
        "<RUN_DIR>/run_summary.json",
        "--manifest",
        "<RUN_DIR>/run_manifest.json",
        "--numerical-output",
        "<RUN_DIR>",
        "--stop-stage",
        "full",
        "--output",
        "<RUN_DIR>/partial_checker_result.json",
    ]
    return {
        "schema": "task40extra.review_v30_full_input_preparation.v1",
        "status": "READY_FOR_APPROVED_V30_SERVICE",
        "source_sha": source_sha,
        **identity,
        "q0_map_sha256": operator_identity["q_map_sha256"],
        "q0_original_h_sha256": operator_identity["original_h_sha256"],
        "execution_contract_path": str(contract_path),
        "execution_contract_sha256": contract_sha,
        "campaign_window_path": str(fixed_contract["execution"]["campaign_window_path"]),
        "campaign_window_sha256": str(fixed_contract["execution"]["campaign_window_sha256"]),
        "campaign_window": dict(fixed_contract["execution"]["window"]),
        "q0_donor_manifest_sha256": V28_Q0_CSR_MANIFEST_SHA256,
        "q0_native_qualification_sha256": V28_Q0_NATIVE_QUALIFICATION_SHA256,
        "service_command": (
            "bash scripts/run_case_in_user_service.sh "
            f"{input_path} --task40-v30-execution-contract {contract_path}"
        ),
        "checker_command_template": checker_command,
    }


def prepare_stage_inputs(repo_root: Path = ROOT) -> dict[str, Any]:
    artifact_root = repo_root / ARTIFACT_ROOT
    stage_root = artifact_root / "stage_inputs"
    stage_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    for profile, (canonical_relative, stages) in V20_INPUTS.items():
        canonical = repo_root / canonical_relative
        canonical_bytes = canonical.read_bytes()
        canonical_text = canonical_bytes.decode("utf-8")
        canonical_data = tomllib.loads(canonical_text)
        if canonical_data.get("solver", {}).get("preconditioner") != profile:
            raise ValueError(f"canonical input/profile mismatch: {canonical_relative}")
        if canonical_data.get("execution", {}).get("task40_execution_stop_stage") != "preflight":
            raise ValueError(f"canonical input is no longer the preflight authority: {canonical_relative}")
        for stop_stage in ("preflight", *sorted(stages)):
            if stop_stage == "preflight":
                staged_bytes = canonical_bytes
                destination = canonical
            else:
                staged_bytes = render_stage_input(canonical_text, stop_stage).encode("utf-8")
                destination = stage_root / stop_stage / canonical.name
                destination.parent.mkdir(parents=True, exist_ok=True)
            relative_destination = destination.relative_to(repo_root)
            if stop_stage != "preflight":
                ignored = subprocess.run(
                    ["git", "check-ignore", "-q", str(relative_destination)],
                    cwd=repo_root,
                    check=False,
                )
                if ignored.returncode != 0:
                    raise RuntimeError(f"stage input destination is not git-ignored: {relative_destination}")
                if destination.exists():
                    if destination.read_bytes() != staged_bytes:
                        raise FileExistsError(f"refusing to replace different stage input: {destination}")
                else:
                    with destination.open("xb") as stream:
                        stream.write(staged_bytes)
                        stream.flush()
                        os.fsync(stream.fileno())
            records.append(
                {
                    "profile": profile,
                    "stop_stage": stop_stage,
                    "canonical_path": str(canonical_relative),
                    "canonical_sha256": _sha256_bytes(canonical_bytes),
                    "stage_input_path": str(relative_destination),
                    "stage_input_sha256": _sha256_bytes(staged_bytes),
                }
            )

    campaign = repo_root / CAMPAIGN_RELATIVE
    if _sha256_file(campaign) != CAMPAIGN_SHA256:
        raise ValueError("the existing V19 fixed campaign window SHA differs from V20 authority")
    manifest = {
        "schema": "task40extra.review_v20_stage_input_manifest.v1",
        "canonical_inputs_unchanged": True,
        "campaign_window_path": str(CAMPAIGN_RELATIVE),
        "campaign_window_sha256": CAMPAIGN_SHA256,
        "stage_inputs": records,
        "launch_command": (
            "bash scripts/run_case_in_user_service.sh <stage_input.dat> "
            "--task40-v10-campaign-window "
            "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
            "campaign_window_v19.json"
        ),
    }
    manifest_path = stage_root / "stage_input_manifest.json"
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    if manifest_path.exists() and manifest_path.read_bytes() != encoded:
        raise FileExistsError(f"refusing to replace a different stage input manifest: {manifest_path}")
    if not manifest_path.exists():
        with manifest_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    command_lines = [
        "# Task40 V20 staged-input commands; run only after source freeze",
        "",
        "Each input keeps the canonical basename and changes only `execution.task40_execution_stop_stage`;",
        "the canonical input remains at its original path. Hashes are in `stage_input_manifest.json`.",
        "The local-port command completes preflight, geometry inventory, then local/port components in one run.",
        "The E2 full command is registered but remains conditional on the existing campaign deadline and resource gates.",
        "build_and_symbolic and one_q_numeric target inputs are registered but remain refused: the canonical authorization flag is false, so both stop after preflight.",
        "",
        "",
    ]
    for row in records:
        command_lines.append(
            "bash scripts/run_case_in_user_service.sh "
            f"{row['stage_input_path']} --task40-v10-campaign-window "
            f"{CAMPAIGN_RELATIVE}"
        )
    commands_path = stage_root / "stage_commands.md"
    commands_text = "\n".join(command_lines) + "\n"
    if commands_path.exists() and commands_path.read_text(encoding="utf-8") != commands_text:
        raise FileExistsError(f"refusing to replace a different stage command package: {commands_path}")
    if not commands_path.exists():
        with commands_path.open("x", encoding="utf-8") as stream:
            stream.write(commands_text)
            stream.flush()
            os.fsync(stream.fileno())
    manifest["manifest_path"] = str(manifest_path.relative_to(repo_root))
    manifest["commands_path"] = str(commands_path.relative_to(repo_root))
    return manifest


def _append_clock_event(
    events: list[dict[str, Any]],
    label: str,
    event_log: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "label": label,
        "sample": clock_sample(include_boot_id=True),
        "identity": identity,
    }
    events.append(event)
    with event_log.open("ab") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return event["sample"]


def _write_json_fsync(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    with path.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _set_first_failure(
    record: dict[str, Any], kind: str, message: str, returncode: int | None = None
) -> None:
    if "first_failure" not in record:
        record["first_failure"] = {
            "kind": kind,
            "message": message,
            "returncode": returncode,
        }


def _parse_run_case_result(stdout: str) -> dict[str, Any]:
    """Find the launcher-result object emitted by run_case, ignoring other lines."""

    required = {"run_directory", "manifest", "summary", "result_classification"}
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    for start, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(stdout[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and required.issubset(payload):
            found = payload
    if found is None:
        raise ValueError("run_case stdout contains no launcher result object")
    return found


def _intervals(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    intervals: list[dict[str, Any]] = []
    errors: list[str] = []
    boot_ids = {event["sample"].get("boot_id") for event in events}
    if len(boot_ids) != 1 or None in boot_ids:
        errors.append("clock samples have missing or mixed boot_id values")
    for left, right in zip(events, events[1:]):
        try:
            interval = checked_interval(
                left["sample"],
                right["sample"],
                policy=CONSERVATIVE_REALTIME,
            )
            intervals.append(
                {
                    "from": left["label"],
                    "to": right["label"],
                    **interval,
                }
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            errors.append(f"{left['label']}->{right['label']}: {type(exc).__name__}: {exc}")
    return intervals, errors


def _activation_environment(
    repo_root: Path,
    runtime_prefix: Path,
    abi_receipt: Path,
    jit_cache: Path,
    *,
    runtime_profile: str | None = None,
) -> tuple[dict[str, str], str, int, str]:
    if runtime_profile == "native_linux":
        command = (
            'set -euo pipefail; cd -- "$1"; '
            'unset _MYFENICS_WSL_QUALIFIED_ACTIVATION; '
            'source scripts/task40_fresh_c1/activate_native_complex.sh '
            '"$2" "$3" "$4" native_linux; '
            'env -0'
        )
    elif runtime_profile is None:
        command = (
            'set -euo pipefail; cd -- "$1"; '
            'source scripts/task40_fresh_c1/activate_local_wsl_complex.sh "$2" "$3" "$4"; '
            'env -0'
        )
    else:
        raise ValueError(f"unsupported Task40 V29 runtime profile: {runtime_profile}")
    argv = [
        "/usr/bin/bash",
        "-lc",
        command,
        "task40-v20-activation",
        str(repo_root),
        str(runtime_prefix),
        str(abi_receipt),
        str(jit_cache),
    ]
    completed = subprocess.run(argv, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    environment: dict[str, str] = {}
    for item in completed.stdout.split(b"\0"):
        if item and b"=" in item:
            key, value = item.split(b"=", 1)
            environment[key.decode()] = value.decode(errors="surrogateescape")
    if runtime_profile == "native_linux" and completed.returncode == 0:
        environment["TASK40_V29_STRICT_FACTOR_ONLY"] = "1"
    return (
        environment,
        " ".join(argv),
        int(completed.returncode),
        completed.stderr.decode("utf-8", errors="replace"),
    )


def _qualified_activation_identity(environment: Mapping[str, str]) -> str | None:
    if environment.get("TASK40_V31_STRICT_EXECUTION") == "1":
        digest = environment.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256", "")
        if (
            environment.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") == "1"
            and environment.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") == "native_linux"
            and environment.get("_MYFENICS_CLOUD_QUALIFICATION_SCOPE")
            == "imports_only_C1_FE_JIT_NOT_RUN"
            and re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            return f"native_linux_imports_only:{digest}"
        return None
    if environment.get("TASK40_V30_STRICT_EXECUTION") == "1":
        from src.runners.task40_v30_contract import qualified_activation_identity

        return qualified_activation_identity(environment)
    from src.runners.task40_v29_contract import qualified_activation_identity

    return qualified_activation_identity(environment)


def _abi_preflight(
    runtime_prefix: Path, environment: dict[str, str], repo_root: Path
) -> tuple[list[str], int, str, str]:
    snippet = r'''
import json, pathlib, sys
import numpy as np
from petsc4py import PETSc
from mpi4py import MPI
import petsc4py, slepc4py, dolfinx, mpi4py
prefix = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(sys.executable).resolve().is_relative_to(prefix)
assert np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
assert np.dtype(PETSc.IntType) == np.dtype(np.int32)
assert MPI.COMM_WORLD.Get_size() == 1
modules = (petsc4py, slepc4py, dolfinx, mpi4py)
for module in modules:
    assert pathlib.Path(module.__file__).resolve().is_relative_to(prefix)
print(json.dumps({
    "python": sys.executable,
    "scalar_type": str(np.dtype(PETSc.ScalarType)),
    "int_type": str(np.dtype(PETSc.IntType)),
    "mpi_size": MPI.COMM_WORLD.Get_size(),
    "abi_module_paths": {m.__name__: m.__file__ for m in modules},
}))
'''
    argv = [str(runtime_prefix / "bin/python"), "-c", snippet, str(runtime_prefix)]
    completed = subprocess.run(
        argv,
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    return argv, int(completed.returncode), completed.stdout, completed.stderr


def _parse_case_arguments(
    case_args: list[str], *, v30_contract: bool = False, v31_contract: bool = False
) -> tuple[Path, Path, str, dict[str, Any]]:
    if not case_args:
        raise ValueError("V20 service requires a .dat input")
    input_path = Path(case_args[0]).resolve()
    text, data = _read_case(input_path)
    del text
    profile = str(data.get("solver", {}).get("preconditioner", ""))
    case = V20_INPUTS.get(profile)
    if case is None:
        raise ValueError("service V20 branch received a non-V20 profile")
    canonical_relative, supported_stages = case
    stop_stage = str(data.get("execution", {}).get("task40_execution_stop_stage", ""))
    v25_q_stage = profile == V25_TARGET_PROFILE and stop_stage in V25_SELECTED_Q_STAGES
    v30_full_case = (
        v30_contract
        and profile == V30_TARGET_PROFILE
        and stop_stage == "full"
        and data.get("execution", {}).get("task40_target_heavy_authorized") is True
        and isinstance(data.get("execution", {}).get("task40_v30_q_csr_binding"), Mapping)
        and isinstance(data.get("execution", {}).get("task40_v30_factor_bank_config"), Mapping)
    )
    v31_full_case = (
        v31_contract
        and profile == "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
        and stop_stage == "full"
        and data.get("execution", {}).get("task40_target_heavy_authorized") is True
        and isinstance(data.get("execution", {}).get("task40_v31_q_csr_binding"), Mapping)
        and isinstance(data.get("execution", {}).get("task40_v31_factor_bank_config"), Mapping)
        and not isinstance(data.get("execution", {}).get("task40_v30_q_csr_binding"), Mapping)
        and not isinstance(data.get("execution", {}).get("task40_v30_factor_bank_config"), Mapping)
    )
    if stop_stage not in supported_stages | {"preflight"} and not v25_q_stage and not v30_full_case and not v31_full_case:
        raise ValueError(f"unsupported user-service stop stage for {profile}: {stop_stage}")
    campaign: Path | None = None
    for index, arg in enumerate(case_args):
        if arg == "--task40-v10-campaign-window" and index + 1 < len(case_args):
            campaign = Path(case_args[index + 1])
        elif arg.startswith("--task40-v10-campaign-window="):
            campaign = Path(arg.split("=", 1)[1])
    if campaign is None:
        raise ValueError("V20 service route requires the existing fixed campaign window")
    return input_path, campaign, stop_stage, data


def _extract_v23_q_only_scan_arg(case_args: list[str]) -> tuple[list[str], Path | None]:
    """Remove the one-off q-only selector before forwarding arguments to run_case."""

    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    while index < len(case_args):
        value = case_args[index]
        if value == "--v23-q-only-scan-checkpoint":
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError("V23 q-only selector must appear once with a scan run directory")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith("--v23-q-only-scan-checkpoint="):
            if selected is not None:
                raise ValueError("V23 q-only selector must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _extract_v24_cd_selector_arg(case_args: list[str]) -> tuple[list[str], Path | None]:
    """Remove the explicit V24 bounded port/volume sample selector."""

    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    flag = "--v24-bounded-port-reuse-volume-selector"
    while index < len(case_args):
        value = case_args[index]
        if value == flag:
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError("V24 C/D selector must appear once with a selector JSON path")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith(flag + "="):
            if selected is not None:
                raise ValueError("V24 C/D selector must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _extract_v25_selected_operation_selector_arg(
    case_args: list[str],
) -> tuple[list[str], Path | None]:
    """Remove the explicit V25 operation selector before forwarding to run_case."""
    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    flag = "--v25-selected-operation-selector"
    while index < len(case_args):
        value = case_args[index]
        if value == flag:
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError("V25 selected-operation selector must appear once with a JSON path")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith(flag + "="):
            if selected is not None:
                raise ValueError("V25 selected-operation selector must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _extract_v26_selected_operation_selector_arg(
    case_args: list[str],
) -> tuple[list[str], Path | None]:
    """Remove the V26 selector before forwarding only the reviewed case args."""
    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    flag = "--v26-selected-operation-selector"
    while index < len(case_args):
        value = case_args[index]
        if value == flag:
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError("V26 selected-operation selector must appear once with a JSON path")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith(flag + "="):
            if selected is not None:
                raise ValueError("V26 selected-operation selector must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _extract_v27_saved_q0_selector_arg(
    case_args: list[str],
) -> tuple[list[str], Path | None]:
    """Remove the single V27 saved-only q0 selector from forwarded case args."""
    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    flag = "--v27-saved-q0-selector"
    while index < len(case_args):
        value = case_args[index]
        if value == flag:
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError("V27 saved-q0 selector must appear once with a JSON path")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith(flag + "="):
            if selected is not None:
                raise ValueError("V27 saved-q0 selector must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _extract_v28_q0_continuation_selector_arg(
    case_args: list[str],
) -> tuple[list[str], Path | None]:
    """Remove the one V28 existing-manifest continuation selector."""
    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    flag = "--v28-q0-continuation-selector"
    while index < len(case_args):
        value = case_args[index]
        if value == flag:
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError("V28 q0 continuation selector must appear once with a JSON path")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith(flag + "="):
            if selected is not None:
                raise ValueError("V28 q0 continuation selector must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _extract_v29_path_arg(case_args: list[str], flag: str) -> tuple[list[str], Path | None]:
    """Remove one V29 path argument before forwarding case args to run_case."""
    cleaned: list[str] = []
    selected: Path | None = None
    index = 0
    while index < len(case_args):
        value = case_args[index]
        if value == flag:
            if selected is not None or index + 1 >= len(case_args):
                raise ValueError(f"{flag} must appear once with a path")
            selected = Path(case_args[index + 1]).resolve()
            index += 2
            continue
        if value.startswith(flag + "="):
            if selected is not None:
                raise ValueError(f"{flag} must appear only once")
            selected = Path(value.split("=", 1)[1]).resolve()
            index += 1
            continue
        cleaned.append(value)
        index += 1
    return cleaned, selected


def _map_v29_paths_in_value(value: Any, resolver: Callable[[str | Path], Path]) -> Any:
    """Map only absolute paths rooted in the canonical source tree, in-memory."""
    if isinstance(value, Mapping):
        return {key: _map_v29_paths_in_value(item, resolver) for key, item in value.items()}
    if isinstance(value, list):
        return [_map_v29_paths_in_value(item, resolver) for item in value]
    if isinstance(value, str) and Path(value).is_absolute():
        try:
            return str(resolver(value))
        except ValueError:
            return value
    return value


def _resolve_v29_checker_path(
    value: str | Path,
    *,
    resolver: Callable[[str | Path], Path],
    execution_root: Path,
) -> Path:
    """Resolve a saved V28 path into the approved V29 tree, rejecting every other root."""
    supplied = Path(value)
    if supplied.is_absolute():
        mapped = Path(_map_v29_paths_in_value(str(supplied), resolver))
    else:
        mapped = resolver(supplied)
    if not mapped.is_absolute():
        mapped = execution_root / mapped
    resolved = mapped.resolve()
    if not resolved.is_relative_to(execution_root):
        raise ValueError(f"V29 checker path escapes its approved execution root: {value}")
    return resolved


def _v29_partial_checker_context(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_output: Path,
    manifest: Mapping[str, Any],
    run_summary: Mapping[str, Any],
    partial: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the V29 checker caller, its source, and the two campaign windows."""
    from src.runners.task40_v29_contract import (
        approved_path_resolver,
        require_authorized_contract,
        require_authorized_selector,
    )

    env = os.environ
    root = ROOT.resolve()
    contract_path = Path(env["TASK40_V29_CONTRACT_PATH"]).resolve()
    selector_path = Path(env["TASK40_V29_SELECTOR_PATH"]).resolve()
    if not contract_path.is_relative_to(root) or not selector_path.is_relative_to(root):
        raise ValueError("V29 contract and selector must remain under the execution root")
    contract, contract_sha = require_authorized_contract(
        contract_path, expected_sha256=env["TASK40_V29_CONTRACT_SHA256"], current_root=root
    )
    selector, selector_sha = require_authorized_selector(
        selector_path,
        expected_sha256=env["TASK40_V29_SELECTOR_SHA256"],
        contract_path=contract_path,
        contract_sha256=contract_sha,
        contract=contract,
    )
    execution, science = contract["execution"], contract["scientific_identity"]
    source_root = Path(str(execution["approved_path_mapping"]["source_root"])).resolve()
    resolver = approved_path_resolver(contract)
    resolve = lambda value: _resolve_v29_checker_path(
        value, resolver=resolver, execution_root=root
    )
    callers = [input_path.resolve(), summary_path.resolve(), manifest_path.resolve(), numerical_output.resolve()]
    if any(not path.is_relative_to(root) for path in callers):
        raise ValueError("V29 checker caller path escapes the execution root")

    paths = {
        "input": resolve(selector.get("input_path", "")),
        "manifest": resolve(selector.get("manifest_path", "")),
        "qualification": resolve(selector.get("qualification_path", "")),
        "pattern": resolve(selector.get("pattern_manifest_path", "")),
        "immutable_selector": resolve(selector.get("immutable_v28_selector_path", "")),
        "old_window": resolve(source_root / TASK40_V28_CAMPAIGN_WINDOW),
        "sidecar": resolve(selector.get("path_mapping_sidecar", "")),
    }
    for label, field, digest in (
        ("input", "input_sha256", science["input_sha256"]),
        ("manifest", "manifest_sha256", science["v28_complete_manifest_sha256"]),
    ):
        target = paths[label]
        if selector.get(field) != digest or not target.is_file() or _sha256_file(target) != digest:
            raise ValueError(f"V29 checker {label} differs from its frozen hash")
    if (
        selector.get("qualification_sha256") != science["v28_native_qualification_sha256"]
        or selector.get("pattern_manifest_sha256") != science["v27_manifest_sha256"]
        or selector.get("qualified_window_sha256") != science["v28_window_sha256"]
        or paths["input"] != callers[0]
        or paths["manifest"] != resolve(selector.get("continuation_manifest_path", ""))
        or not paths["old_window"].is_file()
        or _sha256_file(paths["old_window"]) != science["v28_window_sha256"]
    ):
        raise ValueError("V29 caller or immutable V28 evidence differs from its approved identity")

    sidecar = json.loads(paths["sidecar"].read_text(encoding="utf-8"))
    if (
        sidecar.get("source_root") != str(source_root)
        or sidecar.get("execution_root") != str(root)
        or sidecar.get("execution_contract_sha256") != contract_sha
        or sidecar.get("rules", {}).get("rewrite_immutable_v28_json") is not False
    ):
        raise ValueError("V29 path-mapping sidecar differs from its approved path contract")

    stage = partial.get("v28_q0_continuation", {})
    stage = stage if isinstance(stage, Mapping) else {}
    partial_path = callers[3] / "v20_partial_result.json"
    operation_path = (callers[3] / str(stage.get("operation_path", ""))).resolve()
    if (
        not operation_path.is_relative_to(callers[3])
        or not operation_path.is_file()
        or stage.get("operation_sha256") != _sha256_file(operation_path)
    ):
        raise ValueError("V29 factor operation path or hash differs from the partial footer")
    operation = json.loads(operation_path.read_text(encoding="utf-8"))
    if (
        resolve(stage.get("selector_path", "")) != paths["immutable_selector"]
        or stage.get("selector_sha256") != selector.get("immutable_v28_selector_sha256")
        or resolve(operation.get("csr_manifest_path", operation.get("continuation_manifest_path", "")))
        != paths["manifest"]
    ):
        raise ValueError("V29 factor operation differs from the frozen V28 selector or manifest")
    factor = operation.get("factor_execution_identity", {})
    factor = factor if isinstance(factor, Mapping) else {}
    current = operation.get("current_execution_identity", {})
    current = current if isinstance(current, Mapping) else {}
    binding = operation.get("v29_strict_factor_only_binding", {})
    binding = binding if isinstance(binding, Mapping) else {}
    run_id, run_source = manifest.get("run_id"), str(manifest.get("source_sha", ""))
    source_ok = bool(
        re.fullmatch(r"[0-9a-f]{40,64}", run_source)
        and partial.get("source_sha") == factor.get("source_sha") == current.get("source_sha") == run_source
        and partial.get("run_id") == operation.get("run_id", run_id) == run_id
        and factor.get("run_id", run_id) == current.get("run_id", run_id) == run_id
        and partial.get("input_sha256") == manifest.get("input_sha256")
        == factor.get("input_sha256") == current.get("input_sha256") == selector.get("input_sha256")
        and resolve(manifest.get("input_path", "")) == paths["input"]
        and partial.get("physical_model_sha256") == manifest.get("physical_model_sha256")
        == factor.get("physical_model_sha256") == current.get("physical_model_sha256")
        == selector.get("physical_model_sha256")
        and factor.get("execution_contract_sha256") == current.get("execution_contract_sha256")
        == binding.get("contract_sha256") == contract_sha
        and factor.get("execution_selector_sha256") == current.get("execution_selector_sha256")
        == binding.get("selector_sha256") == selector_sha
        and run_summary.get("run_id") in (None, run_id)
        and run_summary.get("source_sha") in (None, run_source)
    )
    window = Path(str(execution["campaign_window_path"])).resolve()
    accounting = window.with_name("campaign_accounting_v10.jsonl")
    campaign = manifest.get("task40_v20_campaign", {})
    campaign = campaign if isinstance(campaign, Mapping) else {}
    execution_window_ok = bool(
        window.is_relative_to(root)
        and window.is_file()
        and _sha256_file(window) == execution["campaign_window_sha256"]
        and campaign.get("window_path") == str(window)
        and campaign.get("window_sha256") == execution["campaign_window_sha256"]
        and Path(str(campaign.get("accounting_path", ""))).resolve() == accounting
        and accounting.is_file()
        and binding.get("execution_window_sha256") == factor.get("execution_campaign_window_sha256")
        == current.get("execution_campaign_window_sha256") == execution["campaign_window_sha256"]
    )
    science_window_ok = bool(
        factor.get("campaign_window_sha256") == current.get("campaign_window_sha256")
        == science["v28_window_sha256"]
    )
    hashes = {
        "v29_contract": contract_sha,
        "v29_selector": selector_sha,
        "v29_path_mapping_sidecar": _sha256_file(paths["sidecar"]),
        "v29_execution_window": _sha256_file(window),
        "v28_input": _sha256_file(callers[0]),
        "v28_manifest": _sha256_file(paths["manifest"]),
        "v28_old_window": science["v28_window_sha256"],
        "partial_result": _sha256_file(partial_path),
        "factor_operation": _sha256_file(operation_path),
        "run_summary": _sha256_file(callers[1]),
        "run_manifest": _sha256_file(callers[2]),
    }
    checker_source_sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    checker_file_sha = _sha256_file(Path(__file__))
    hashes["checker_service_source"] = checker_file_sha
    return {
        "selector": selector,
        "contract_sha256": contract_sha,
        "selector_sha256": selector_sha,
        "path_resolver": resolve,
        "pattern_path": paths["pattern"],
        "qualification_path": paths["qualification"],
        "operation": operation,
        "run_source_sha": run_source,
        "checker_source_sha": checker_source_sha,
        "checker_source_file_sha256": checker_file_sha,
        "raw_file_hashes": hashes,
        "identity_checks": {
            "v29_caller_source_and_root_bound": source_ok,
            "v29_old_v28_science_window_preserved": science_window_ok,
            "v29_execution_manifest_window_accounting_and_registration_bind": execution_window_ok,
        },
    }


def _bind_v29_factor_only_selector(
    selector_path: Path,
    contract_path: Path,
    *,
    input_path: Path,
    campaign_registration: Mapping[str, Any],
    profile: str,
    stop_stage: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Bind the exact V29 contract and immutable V28 factor-only science input."""
    from src.runners.task40_v29_contract import (
        V29_STRICT_POLICY,
        approved_path_resolver,
        require_authorized_contract,
        require_authorized_selector,
        require_strict_factor_only_status,
    )
    from src.runners.task40_v20_stage_runner import _load_matching_v28_native_qualification

    contract, contract_sha = require_authorized_contract(
        contract_path,
        current_root=repo_root,
    )
    selector, selector_sha = require_authorized_selector(
        selector_path,
        expected_sha256=None,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        contract=contract,
    )
    resolver = approved_path_resolver(contract)
    if (
        selector.get("policy") != V29_STRICT_POLICY
        or campaign_registration.get("version") != "V29"
        or campaign_registration.get("sha256") != contract["execution"]["campaign_window_sha256"]
        or profile != V28_TARGET_PROFILE
        or stop_stage not in V28_SELECTED_Q_STAGES
    ):
        raise ValueError("V29 strict selector requires its exact approved factor-only profile/window/stage")
    mapped_input_path = resolver(selector.get("input_path", ""))
    if mapped_input_path != input_path.resolve() or selector.get("input_sha256") != _sha256_file(input_path):
        raise ValueError("V29 stage DAT differs from the frozen V28 scientific input identity")
    science = contract.get("scientific_identity", {})
    if (
        not isinstance(science, Mapping)
        or science.get("input_sha256") != selector.get("input_sha256")
        or science.get("v28_complete_manifest_sha256") != selector.get("manifest_sha256")
        or science.get("v28_native_qualification_sha256") != selector.get("qualification_sha256")
        or science.get("v28_window_sha256") != selector.get("qualified_window_sha256")
    ):
        raise ValueError("V29 execution contract and factor-only selector disagree on immutable science identity")

    old_selector_path = resolver(selector.get("immutable_v28_selector_path", ""))
    old_selector_sha = selector.get("immutable_v28_selector_sha256")
    if not old_selector_path.is_file() or _sha256_file(old_selector_path) != old_selector_sha:
        raise ValueError("V29 immutable V28 selector is missing or changed")
    old_selector = json.loads(old_selector_path.read_text(encoding="utf-8"))
    donor_import = verify_v27_v26_donor_import(
        repo_root=repo_root,
        path_resolver=resolver,
    )
    stored_donor = old_selector.get("donor_import")
    mapped_donor = _map_v29_paths_in_value(stored_donor, resolver)
    donor_sha = hashlib.sha256(
        json.dumps(stored_donor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    pattern_path = (repo_root / V28_PATTERN_MANIFEST_RELATIVE).resolve()
    continuation_path = pattern_path.with_name(V28_CONTINUATION_MANIFEST_NAME)
    if (
        old_selector.get("schema") != "task40extra.review_v28_q0_continuation_operation.v1"
        or old_selector.get("campaign_window_sha256") != TASK40_V28_CAMPAIGN_SHA256
        or old_selector.get("input_sha256") != _sha256_file(input_path)
        or old_selector.get("model_profile") != V28_TARGET_PROFILE
        or old_selector.get("stop_stage") != stop_stage
        or mapped_donor != donor_import
        or donor_sha != selector.get("qualified_donor_identity_sha256")
        or resolver(old_selector.get("pattern_manifest_path", "")) != pattern_path
        or old_selector.get("pattern_manifest_sha256") != V28_PATTERN_MANIFEST_SHA256
        or resolver(old_selector.get("continuation_manifest_path", "")) != continuation_path
        or old_selector.get("continuation_policy") != V28_CONTINUATION_POLICY
    ):
        raise ValueError("V29 old V28 donor/pattern selector no longer matches its read-only dependencies")

    manifest_path = resolver(selector.get("manifest_path", ""))
    qualification_path = resolver(selector.get("qualification_path", ""))
    if (
        manifest_path != continuation_path
        or not manifest_path.is_file()
        or _sha256_file(manifest_path) != selector.get("manifest_sha256")
        or not qualification_path.is_file()
        or _sha256_file(qualification_path) != selector.get("qualification_sha256")
    ):
        raise ValueError("V29 COMPLETE CSR or native PASS is missing or differs from the frozen hash")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    require_strict_factor_only_status(manifest, qualification)
    qualified = _load_matching_v28_native_qualification(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        expected_pattern_path=pattern_path,
        expected_pattern_sha256=V28_PATTERN_MANIFEST_SHA256,
        donor_identity_sha256=donor_sha,
        input_sha256=str(selector["input_sha256"]),
        physical_model_sha256=str(selector["physical_model_sha256"]),
        run_id=str(selector["run_id"]),
        campaign_window_sha256=str(selector["qualified_window_sha256"]),
        mode_manifest_sha256=str(selector.get("qualified_mode_manifest_sha256", "")),
        ordered_mode_key_sha256=str(selector.get("qualified_ordered_mode_key_sha256", "")),
        sha256_file=_sha256_file,
        path_resolver=resolver,
    )
    if qualified is None or qualified[0] != qualification_path:
        raise ValueError("V29 native PASS failed the existing complete q0 qualification matcher")
    return {
        "selector_path": str(selector_path.resolve()),
        "selector_sha256": selector_sha,
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": contract_sha,
        "immutable_v28_selector_path": str(old_selector_path),
        "immutable_v28_selector_sha256": str(old_selector_sha),
        "operation": V28_CONTINUATION_OPERATION,
        "stop_stage": stop_stage,
        "campaign_window_sha256": str(campaign_registration["sha256"]),
        "qualified_window_sha256": str(selector["qualified_window_sha256"]),
        "input_sha256": str(selector["input_sha256"]),
        "donor_identity_sha256": donor_sha,
        "producer_root": str((repo_root / V26_PRODUCER_RUN_RELATIVE).resolve()),
        "pattern_manifest_path": str(pattern_path),
        "pattern_manifest_sha256": V28_PATTERN_MANIFEST_SHA256,
        "continuation_manifest_path": str(continuation_path),
        "manifest_sha256": str(selector["manifest_sha256"]),
        "qualification_path": str(qualification_path),
        "qualification_sha256": str(selector["qualification_sha256"]),
        "execution_window_path": str(contract["execution"]["campaign_window_path"]),
        "execution_window_sha256": str(contract["execution"]["campaign_window_sha256"]),
        "contract": contract,
    }


def _v29_live_resource_gate(contract: Mapping[str, Any], *, stage: str) -> dict[str, Any]:
    """Require the live task cgroup and host reserve to match V29 authorization."""
    from src.runners.task40_v29_contract import (
        V29ContractError,
        validate_live_resource_contract,
    )
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.runners.task40_v20_stage_runner import _resource_snapshot

    admission = _resource_admission(
        stage,
        0,
        resource_sample=_resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(
            contract["execution"]["resources"]["task_memory_max_bytes"]
        ),
        host_reserve_bytes=int(contract["execution"]["resources"]["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=0,
    )
    cgroup = admission.get("current_process_cgroup", {})
    if not isinstance(cgroup, Mapping) or (
        cgroup.get("dedicated_job_cgroup") is not True
        or cgroup.get("swap_current_bytes") != 0
    ):
        raise V29ContractError(f"{stage}: dedicated zero-swap systemd task cgroup is unavailable")
    validate_live_resource_contract(
        contract,
        cgroup_limit_bytes=int(cgroup["memory_limit_bytes"]),
        cgroup_current_bytes=int(cgroup["memory_current_bytes"]),
        host_effective_available_bytes=int(admission["host_effective_available_bytes"]),
        additional_request_bytes=0,
    )
    return {
        "stage": stage,
        "passed": True,
        "task_memory_max_bytes": int(contract["execution"]["resources"]["task_memory_max_bytes"]),
        "host_reserve_bytes": int(contract["execution"]["resources"]["host_reserve_bytes"]),
        "memory_swap_max_bytes": int(contract["execution"]["resources"]["memory_swap_max_bytes"]),
        "cgroup_limit_bytes": int(cgroup["memory_limit_bytes"]),
        "cgroup_current_bytes": int(cgroup["memory_current_bytes"]),
        "host_effective_available_bytes": int(admission["host_effective_available_bytes"]),
        "resource_admission": admission,
    }


def _v30_live_resource_gate(contract: Mapping[str, Any], *, stage: str) -> dict[str, Any]:
    """Require the V30 systemd cgroup and 64 GiB host reserve at each gate."""
    from src.runners.task40_v30_contract import (
        V30ContractError,
        validate_live_resource_contract,
    )
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.runners.task40_v20_stage_runner import _resource_snapshot

    resources = contract["execution"]["resources"]
    admission = _resource_admission(
        stage,
        0,
        resource_sample=_resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
        host_reserve_bytes=int(resources["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=0,
    )
    cgroup = admission.get("current_process_cgroup", {})
    if not isinstance(cgroup, Mapping) or cgroup.get("dedicated_job_cgroup") is not True:
        raise V30ContractError(f"{stage}: dedicated V30 systemd task cgroup is unavailable")
    result = validate_live_resource_contract(
        contract,
        cgroup_limit_bytes=int(cgroup["memory_limit_bytes"]),
        cgroup_current_bytes=int(cgroup["memory_current_bytes"]),
        cgroup_swap_current_bytes=int(cgroup.get("swap_current_bytes", -1)),
        host_effective_available_bytes=int(admission["host_effective_available_bytes"]),
        additional_request_bytes=0,
    )
    return {
        "stage": stage,
        **result,
        "cgroup_limit_bytes": int(cgroup["memory_limit_bytes"]),
        "cgroup_swap_current_bytes": int(cgroup["swap_current_bytes"]),
        "resource_admission": admission,
    }


def _v31_live_resource_gate(contract: Mapping[str, Any], *, stage: str) -> dict[str, Any]:
    """Enforce V31's own fixed cgroup and host reserve contract."""
    from src.runners.task40_v31_contract import V31ContractError, V31_RESOURCES
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.runners.task40_v20_stage_runner import _resource_snapshot

    execution = contract.get("execution")
    resources = execution.get("resources") if isinstance(execution, Mapping) else None
    if not isinstance(resources, Mapping) or dict(resources) != V31_RESOURCES:
        raise V31ContractError("V31 live resource gate has no exact approved limits")
    admission = _resource_admission(
        stage,
        0,
        resource_sample=_resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
        host_reserve_bytes=int(resources["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=0,
    )
    cgroup = admission.get("current_process_cgroup", {})
    if not isinstance(cgroup, Mapping) or cgroup.get("dedicated_job_cgroup") is not True:
        raise V31ContractError(f"{stage}: dedicated V31 systemd task cgroup is unavailable")
    if (
        int(cgroup.get("memory_limit_bytes", -1)) != int(resources["task_memory_max_bytes"])
        or int(cgroup.get("swap_current_bytes", -1)) != 0
        or int(cgroup.get("memory_current_bytes", -1)) > int(resources["task_memory_max_bytes"])
        or int(admission.get("host_effective_available_bytes", -1))
        < int(resources["host_reserve_bytes"])
    ):
        raise V31ContractError(f"{stage}: V31 cgroup, zero-swap, or host-reserve gate failed")
    return {
        "stage": stage,
        "passed": True,
        "task_memory_max_bytes": int(resources["task_memory_max_bytes"]),
        "host_reserve_bytes": int(resources["host_reserve_bytes"]),
        "memory_swap_max_bytes": 0,
        "cgroup_limit_bytes": int(cgroup["memory_limit_bytes"]),
        "cgroup_current_bytes": int(cgroup["memory_current_bytes"]),
        "cgroup_swap_current_bytes": int(cgroup["swap_current_bytes"]),
        "host_effective_available_bytes": int(admission["host_effective_available_bytes"]),
        "resource_admission": admission,
    }


def _bind_v25_selected_operation_selector(
    selector_path: Path,
    *,
    input_path: Path,
    campaign_registration: dict[str, Any],
    profile: str,
    stop_stage: str,
    repo_root: Path,
) -> dict[str, str]:
    """Bind the V25 target-volume action selector to its exact input/window."""
    selector_path = selector_path.resolve()
    allowed_root = (repo_root / V25_ARTIFACT_ROOT).resolve()
    if not selector_path.is_relative_to(allowed_root) or not selector_path.is_file():
        raise ValueError("V25 selected-operation selector must be under its registered artifact directory")
    expected_operation = V25_SELECTED_OPERATION_BY_STAGE.get(stop_stage)
    if (
        campaign_registration.get("version") != "V25"
        or campaign_registration.get("sha256") != TASK40_V25_CAMPAIGN_SHA256
        or profile != V25_TARGET_PROFILE
        or expected_operation is None
    ):
        raise ValueError("V25 operation selector requires an explicitly scoped stage/window")
    raw = selector_path.read_bytes()
    selector = json.loads(raw)
    if not isinstance(selector, dict) or (
        selector.get("schema") != "task40extra.review_v25_selected_operation.v1"
        or selector.get("operation") != expected_operation
        or selector.get("campaign_window_sha256") != TASK40_V25_CAMPAIGN_SHA256
        or selector.get("input_sha256") != _sha256_file(input_path)
        or selector.get("model_profile") != V25_TARGET_PROFILE
        or selector.get("stop_stage") != stop_stage
    ):
        raise ValueError("V25 selected-operation selector differs from the frozen target contract (stage/input/window)")
    return {
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_bytes(raw),
        "operation": str(selector["operation"]),
        "stop_stage": stop_stage,
        "campaign_window_sha256": TASK40_V25_CAMPAIGN_SHA256,
        "input_sha256": _sha256_file(input_path),
    }


def verify_v26_saved_producer_metadata(
    *,
    producer_root: Path,
    repo_root: Path = ROOT,
    path_resolver: Callable[[str | Path], Path] | None = None,
) -> dict[str, Any]:
    """Rebind the malformed legacy field only after strict V25 producer cross-checks."""
    producer_root = producer_root.resolve()
    expected_root = (repo_root / V26_PRODUCER_RUN_RELATIVE).resolve()
    if producer_root != expected_root or not producer_root.is_dir():
        raise ValueError("V26 saved producer is not the exact registered V25 run directory")
    index_path = producer_root / "v25_q0_failure_artifact_index.json"
    if not index_path.is_file() or _sha256_file(index_path) != V26_FAILURE_INDEX_SHA256:
        raise ValueError("V26 saved producer failure index identity changed")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    run = index.get("run")
    if not isinstance(run, Mapping):
        raise ValueError("V26 saved producer index has no run identity")
    malformed = run.get("input_sha256")
    if malformed != V26_LEGACY_BAD_INPUT_SHA256 or len(str(malformed)) != 62:
        raise ValueError("V26 legacy malformed input field differs from the preserved index record")
    if (
        run.get("run_id") != V26_PRODUCER_RUN_ID
        or run.get("source_sha") != V26_PRODUCER_SOURCE_SHA
        or run.get("relative_run_directory") != str(V26_PRODUCER_RUN_RELATIVE)
    ):
        raise ValueError("V26 saved producer source/run identity differs from the frozen V25 review")
    support = {
        str(item.get("path")): item
        for item in index.get("supporting_records", [])
        if isinstance(item, Mapping)
    }
    for name in ("input_sha256.txt", "physical_model_sha256.txt", "source_sha.txt", "run_manifest.json", "run_summary.json"):
        item = support.get(name)
        path = producer_root / name
        if (
            not isinstance(item, Mapping)
            or not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or _sha256_file(path) != item.get("sha256")
        ):
            raise ValueError(f"V26 saved producer metadata record failed its frozen hash: {name}")
    run_manifest = json.loads((producer_root / "run_manifest.json").read_text(encoding="utf-8"))
    resolved_path = producer_root / "resolved_config.json"
    if (
        not resolved_path.is_file()
        or _sha256_file(resolved_path) != run.get("resolved_config_sha256")
        or run_manifest.get("resolved_config_sha256") != run.get("resolved_config_sha256")
        or run_manifest.get("input_sha256") != V26_VERIFIED_INPUT_SHA256
        or run_manifest.get("source_sha") != V26_PRODUCER_SOURCE_SHA
        or run_manifest.get("run_id") != V26_PRODUCER_RUN_ID
        or run_manifest.get("physical_model_sha256") != run.get("physical_model_sha256")
    ):
        raise ValueError("V26 saved producer run manifest/resolved config cross-check failed")
    resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    resolved_provenance = resolved.get("provenance", {})
    resolved_config_identity = run_manifest.get("resolved_config_sha256")
    if (
        _sha256_file(producer_root / "input_original.dat") != V26_VERIFIED_INPUT_SHA256
        or (producer_root / "input_sha256.txt").read_text(encoding="ascii").strip()
        != V26_VERIFIED_INPUT_SHA256
        or (producer_root / "physical_model_sha256.txt").read_text(encoding="ascii").strip()
        != run.get("physical_model_sha256")
        or (producer_root / "source_sha.txt").read_text(encoding="ascii").strip()
        != V26_PRODUCER_SOURCE_SHA
        or resolved_provenance.get("input_sha256") != V26_VERIFIED_INPUT_SHA256
        or resolved_provenance.get("physical_model_sha256") != run.get("physical_model_sha256")
    ):
        raise ValueError("V26 verified producer input identity differs across dat/support/resolved config")
    raw_manifest_input_path = Path(str(run_manifest.get("input_path", "")))
    manifest_input_path = (
        path_resolver(raw_manifest_input_path)
        if path_resolver is not None
        else raw_manifest_input_path.resolve()
    )
    expected_v25_input = (
        repo_root / V25_ARTIFACT_ROOT / "stage_inputs" / "selected_reference_q_build_only"
        / "target_original_ny8_operator_probe_v22.dat"
    ).resolve()
    if (
        manifest_input_path != expected_v25_input
        or not manifest_input_path.is_file()
        or _sha256_file(manifest_input_path) != V26_VERIFIED_INPUT_SHA256
    ):
        raise ValueError("V26 actual executed V25 dat path/hash is not the exact frozen producer input")
    if resolved_config_identity != _sha256_file(resolved_path):
        raise ValueError("V26 resolved configuration identity is inconsistent")
    payloads = []
    artifact_records = {str(item.get("path")): item for item in index.get("data_artifacts", []) if isinstance(item, Mapping)}
    for name, (size, digest) in V26_PRODUCER_FILE_HASHES.items():
        item = artifact_records.get(name)
        path = producer_root / name
        if (
            not isinstance(item, Mapping)
            or item.get("bytes") != size
            or item.get("sha256") != digest
            or not path.is_file()
            or path.stat().st_size != size
            or _sha256_owned_payload(path) != digest
        ):
            raise ValueError(f"V26 saved producer payload metadata mismatch: {name}")
        payloads.append({"path": name, "bytes": size, "sha256": digest})
    return {
        "producer_run_id": V26_PRODUCER_RUN_ID,
        "producer_source_sha": V26_PRODUCER_SOURCE_SHA,
        "producer_run_directory": str(V26_PRODUCER_RUN_RELATIVE),
        "failure_index_path": str(V26_PRODUCER_RUN_RELATIVE / index_path.name),
        "failure_index_sha256": V26_FAILURE_INDEX_SHA256,
        "legacy_index_input_sha256": str(malformed),
        "legacy_index_input_sha256_length": len(str(malformed)),
        "verified_input_sha256": V26_VERIFIED_INPUT_SHA256,
        "actual_v25_dat_sha256": _sha256_file(manifest_input_path),
        "input_sha256_record_sha256": support["input_sha256.txt"]["sha256"],
        "run_manifest_sha256": support["run_manifest.json"]["sha256"],
        "resolved_config_sha256": resolved_config_identity,
        "physical_model_sha256": run.get("physical_model_sha256"),
        "metadata_repair_applied": "strict_cross_check_rebind_only; old failure index unchanged",
        "payloads": payloads,
    }


def verify_v27_v26_donor_import(
    *,
    repo_root: Path = ROOT,
    path_resolver: Callable[[str | Path], Path] | None = None,
) -> dict[str, Any]:
    """Bind V27 to the already-passed V26 saved replay/native recovery evidence."""
    producer_root = (repo_root / V26_PRODUCER_RUN_RELATIVE).resolve()
    producer_identity = verify_v26_saved_producer_metadata(
        producer_root=producer_root,
        repo_root=repo_root,
        path_resolver=path_resolver,
    )
    replay_root = (repo_root / V27_REPLAY_ROOT).resolve()
    replay_path = replay_root / "v26_saved_q_replay_manifest.json"
    if (
        not replay_path.is_file()
        or _sha256_file(replay_path) != V27_REPLAY_MANIFEST_SHA256
    ):
        raise ValueError("V27 donor saved-replay manifest identity changed")
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    producer_identity_sha = hashlib.sha256(
        json.dumps(
            producer_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if (
        replay.get("schema") != "task40extra.review_v26_saved_q_replay.v1"
        or replay.get("status") != "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        or replay.get("producer_identity") != producer_identity
        or replay.get("producer_identity_sha256") != producer_identity_sha
        or replay.get("official_result") is not False
        or replay.get("csr_built") is not False
    ):
        raise ValueError("V27 donor saved replay is not the accepted V26 replay record")
    replay_artifacts: dict[str, Any] = {}
    for name, item in replay.get("artifacts", {}).items():
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise ValueError(f"V27 donor replay artifact record is malformed: {name}")
        artifact_path = (replay_root / item["path"]).resolve()
        if (
            not artifact_path.is_relative_to(replay_root)
            or not artifact_path.is_file()
            or artifact_path.stat().st_size != item.get("bytes")
            or _sha256_owned_payload(artifact_path) != item.get("sha256")
        ):
            raise ValueError(f"V27 donor replay artifact changed: {name}")
        replay_artifacts[name] = {
            "path": str(artifact_path),
            "bytes": int(item["bytes"]),
            "sha256": str(item["sha256"]),
        }

    native_root = (repo_root / V27_NATIVE_ROOT).resolve()
    recovery_path = native_root / (
        f"v26_native_action_recovery_{V27_NATIVE_RECOVERY_TAG}.json"
    )
    checker_path = native_root / (
        f"v26_native_action_recovery_check_{V27_NATIVE_RECOVERY_TAG}.json"
    )
    if (
        not recovery_path.is_file()
        or _sha256_file(recovery_path) != V27_NATIVE_RECOVERY_SHA256
        or not checker_path.is_file()
        or _sha256_file(checker_path) != V27_NATIVE_CHECKER_SHA256
    ):
        raise ValueError("V27 donor native recovery/checker hashes changed")
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    checker = json.loads(checker_path.read_text(encoding="utf-8"))
    if (
        recovery.get("schema") != "task40extra.review_v26_native_action_recovery.v1"
        or recovery.get("status") != "PASS_RECOVERED_THREE_NATIVE_CASES"
        or recovery.get("saved_replay_manifest_sha256") != V27_REPLAY_MANIFEST_SHA256
        or recovery.get("recovery_checker_receipt_sha256") != V27_NATIVE_CHECKER_SHA256
        or checker.get("schema") != "task40extra.review_v26_native_case_recovery_check.v1"
        or checker.get("status") != "PASS_READONLY_THREE_CASE_RECOVERY"
        or checker.get("native_cases") != recovery.get("cases")
    ):
        raise ValueError("V27 donor native recovery and independent checker disagree")
    native_cases: dict[str, Any] = {}
    for case_name, item in recovery.get("cases", {}).items():
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise ValueError(f"V27 donor native case record is malformed: {case_name}")
        case_path = (native_root / item["path"]).resolve()
        if (
            not case_path.is_relative_to(native_root)
            or not case_path.is_file()
            or case_path.stat().st_size != item.get("bytes")
            or _sha256_owned_payload(case_path) != item.get("sha256")
        ):
            raise ValueError(f"V27 donor native case payload changed: {case_name}")
        native_cases[str(case_name)] = {
            "path": str(case_path),
            "bytes": int(item["bytes"]),
            "sha256": str(item["sha256"]),
            "array_sha256": dict(item.get("array_sha256", {})),
            "array_shapes": dict(item.get("array_shapes", {})),
        }
    if set(native_cases) != {"q0_case_1", "q0_case_2", "q4_pair"}:
        raise ValueError("V27 donor native recovery lacks one of the three accepted cases")
    structure_path = (repo_root / V27_ROW_STRUCTURE_RELATIVE).resolve()
    structure_manifest_path = structure_path.with_suffix(".json")
    if (
        not structure_path.is_file()
        or _sha256_owned_payload(structure_path) != V27_ROW_STRUCTURE_SHA256
        or not structure_manifest_path.is_file()
        or _sha256_file(structure_manifest_path) != V27_ROW_STRUCTURE_MANIFEST_SHA256
    ):
        raise ValueError("V27 donor full-row structure witness hashes changed")
    structure_manifest = json.loads(structure_manifest_path.read_text(encoding="utf-8"))
    if (
        structure_manifest.get("schema")
        != "task40extra.review_v26_selected_q0_row_structure_checkpoint.v1"
        or structure_manifest.get("shape") != [777_644, 777_644]
        or structure_manifest.get("nnz") != 577_061_168
        or structure_manifest.get("required_csr_payload_bytes") != 11_544_333_940
        or structure_manifest.get("array_artifact", {}).get("sha256")
        != V27_ROW_STRUCTURE_SHA256
    ):
        raise ValueError("V27 donor full-row structure witness facts changed")
    return {
        "producer_identity": producer_identity,
        "producer_identity_sha256": producer_identity_sha,
        "saved_replay_manifest": {
            "path": str(replay_path),
            "sha256": V27_REPLAY_MANIFEST_SHA256,
            "status": str(replay["status"]),
            "artifacts": replay_artifacts,
        },
        "native_recovery_manifest": {
            "path": str(recovery_path),
            "sha256": V27_NATIVE_RECOVERY_SHA256,
            "status": str(recovery["status"]),
        },
        "native_recovery_checker": {
            "path": str(checker_path),
            "sha256": V27_NATIVE_CHECKER_SHA256,
            "status": str(checker["status"]),
        },
        "native_cases": native_cases,
        "row_structure_witness": {
            "path": str(structure_path),
            "bytes": int(structure_path.stat().st_size),
            "sha256": V27_ROW_STRUCTURE_SHA256,
            "manifest_path": str(structure_manifest_path),
            "manifest_sha256": V27_ROW_STRUCTURE_MANIFEST_SHA256,
            "shape": [777_644, 777_644],
            "stored_structural_slots": 577_061_168,
            "csr_payload_bytes": 11_544_333_940,
        },
    }


def _bind_v26_selected_operation_selector(
    selector_path: Path,
    *,
    input_path: Path,
    campaign_registration: dict[str, Any],
    profile: str,
    stop_stage: str,
    repo_root: Path,
) -> dict[str, Any]:
    selector_path = selector_path.resolve()
    allowed_root = (repo_root / V26_ARTIFACT_ROOT).resolve()
    if not selector_path.is_relative_to(allowed_root) or not selector_path.is_file():
        raise ValueError("V26 selected-operation selector must be under its registered artifact directory")
    expected_operation = V26_SELECTED_OPERATION_BY_STAGE.get(stop_stage)
    if (
        campaign_registration.get("version") != "V26"
        or campaign_registration.get("sha256") != TASK40_V26_CAMPAIGN_SHA256
        or profile != V26_TARGET_PROFILE
        or expected_operation is None
    ):
        raise ValueError("V26 operation selector requires its exact registered stage/window")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    metadata = verify_v26_saved_producer_metadata(
        producer_root=repo_root / V26_PRODUCER_RUN_RELATIVE,
        repo_root=repo_root,
    )
    if (
        not isinstance(selector, dict)
        or selector.get("schema") != "task40extra.review_v26_selected_operation.v1"
        or selector.get("operation") != expected_operation
        or selector.get("campaign_window_sha256") != TASK40_V26_CAMPAIGN_SHA256
        or selector.get("input_sha256") != _sha256_file(input_path)
        or selector.get("model_profile") != V26_TARGET_PROFILE
        or selector.get("stop_stage") != stop_stage
        or selector.get("producer_identity") != metadata
    ):
        raise ValueError("V26 selector or verified saved-producer identity differs from the frozen contract")
    raw = selector_path.read_bytes()
    return {
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_bytes(raw),
        "operation": str(selector["operation"]),
        "stop_stage": stop_stage,
        "campaign_window_sha256": TASK40_V26_CAMPAIGN_SHA256,
        "input_sha256": _sha256_file(input_path),
        "producer_identity": metadata,
    }


def _bind_v27_saved_q0_selector(
    selector_path: Path,
    *,
    input_path: Path,
    campaign_registration: dict[str, Any],
    profile: str,
    stop_stage: str,
    repo_root: Path,
) -> dict[str, Any]:
    selector_path = selector_path.resolve()
    allowed_root = (repo_root / V27_ARTIFACT_ROOT).resolve()
    if not selector_path.is_relative_to(allowed_root) or not selector_path.is_file():
        raise ValueError("V27 saved-q0 selector must be under its registered artifact directory")
    expected_operation = V27_SELECTED_OPERATION_BY_STAGE.get(stop_stage)
    if (
        campaign_registration.get("version") != "V27"
        or campaign_registration.get("sha256") != TASK40_V27_CAMPAIGN_SHA256
        or profile != V27_TARGET_PROFILE
        or expected_operation is None
    ):
        raise ValueError("V27 selector requires its exact registered stage/window")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    donor_import = verify_v27_v26_donor_import(repo_root=repo_root)
    if (
        not isinstance(selector, dict)
        or selector.get("schema") != "task40extra.review_v27_saved_q0_operation.v1"
        or selector.get("operation") != expected_operation
        or selector.get("campaign_window_sha256") != TASK40_V27_CAMPAIGN_SHA256
        or selector.get("input_sha256") != _sha256_file(input_path)
        or selector.get("model_profile") != V27_TARGET_PROFILE
        or selector.get("stop_stage") != stop_stage
        or selector.get("donor_import") != donor_import
    ):
        raise ValueError("V27 selector or V26 donor import differs from its frozen identity")
    raw = selector_path.read_bytes()
    return {
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_bytes(raw),
        "operation": expected_operation,
        "stop_stage": stop_stage,
        "campaign_window_sha256": TASK40_V27_CAMPAIGN_SHA256,
        "input_sha256": _sha256_file(input_path),
        "donor_import": donor_import,
        "producer_root": str((repo_root / V26_PRODUCER_RUN_RELATIVE).resolve()),
    }


def _bind_v28_q0_continuation_selector(
    selector_path: Path,
    *,
    input_path: Path,
    campaign_registration: dict[str, Any],
    profile: str,
    stop_stage: str,
    repo_root: Path,
) -> dict[str, Any]:
    selector_path = selector_path.resolve()
    allowed_root = (repo_root / V28_ARTIFACT_ROOT).resolve()
    pattern_path = (repo_root / V28_PATTERN_MANIFEST_RELATIVE).resolve()
    continuation_path = pattern_path.with_name(V28_CONTINUATION_MANIFEST_NAME)
    if not selector_path.is_relative_to(allowed_root) or not selector_path.is_file():
        raise ValueError("V28 q0 continuation selector must be under its registered artifact directory")
    if (
        campaign_registration.get("version") != "V28"
        or campaign_registration.get("sha256") != TASK40_V28_CAMPAIGN_SHA256
        or profile != V28_TARGET_PROFILE
        or stop_stage not in V28_SELECTED_Q_STAGES
    ):
        raise ValueError("V28 selector requires its exact registered stage and window")
    if (
        not pattern_path.is_file()
        or _sha256_file(pattern_path) != V28_PATTERN_MANIFEST_SHA256
    ):
        raise ValueError("V28 continuation requires the unchanged V27 pattern manifest")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    donor_import = verify_v27_v26_donor_import(repo_root=repo_root)
    if (
        not isinstance(selector, dict)
        or selector.get("schema") != "task40extra.review_v28_q0_continuation_operation.v1"
        or selector.get("operation") != V28_CONTINUATION_OPERATION
        or selector.get("campaign_window_sha256") != TASK40_V28_CAMPAIGN_SHA256
        or selector.get("input_sha256") != _sha256_file(input_path)
        or selector.get("model_profile") != V28_TARGET_PROFILE
        or selector.get("stop_stage") != stop_stage
        or selector.get("donor_import") != donor_import
        or Path(str(selector.get("pattern_manifest_path", ""))).resolve() != pattern_path
        or selector.get("pattern_manifest_sha256") != V28_PATTERN_MANIFEST_SHA256
        or Path(str(selector.get("continuation_manifest_path", ""))).resolve()
        != continuation_path
        or selector.get("continuation_policy") != V28_CONTINUATION_POLICY
    ):
        raise ValueError("V28 selector or V27 donor/pattern identity differs from its frozen contract")
    raw = selector_path.read_bytes()
    return {
        "selector_path": str(selector_path),
        "selector_sha256": _sha256_bytes(raw),
        "operation": V28_CONTINUATION_OPERATION,
        "stop_stage": stop_stage,
        "campaign_window_sha256": TASK40_V28_CAMPAIGN_SHA256,
        "input_sha256": _sha256_file(input_path),
        "donor_import": donor_import,
        "producer_root": str((repo_root / V26_PRODUCER_RUN_RELATIVE).resolve()),
        "pattern_manifest_path": str(pattern_path),
        "pattern_manifest_sha256": V28_PATTERN_MANIFEST_SHA256,
        "continuation_manifest_path": str(continuation_path),
    }


def _bind_v24_cd_selector(
    selector_path: Path,
    *,
    input_path: Path,
    campaign_registration: dict[str, Any],
    profile: str,
    stop_stage: str,
    q_only_binding: dict[str, str | int] | None,
    repo_root: Path,
) -> dict[str, str | int]:
    """Bind the bounded C/D sample to V24 and the existing q-only checkpoint."""

    selector_path = selector_path.resolve()
    allowed_root = (repo_root / V24_ARTIFACT_ROOT).resolve()
    if not selector_path.is_relative_to(allowed_root) or not selector_path.is_file():
        raise ValueError("V24 C/D selector must be a file under the registered V24 artifact directory")
    if (
        campaign_registration.get("version") != "V24"
        or campaign_registration.get("sha256") != TASK40_V24_CAMPAIGN_SHA256
        or profile != V23_TARGET_PROFILE
        or stop_stage != "target_operator_probe"
        or q_only_binding is None
    ):
        raise ValueError("V24 C/D selector requires the registered Ny8 V24 probe and full q-only checkpoint")
    selector_raw = selector_path.read_bytes()
    selector = json.loads(selector_raw)
    if not isinstance(selector, dict):
        raise ValueError("V24 C/D selector must contain a JSON object")
    if (
        selector.get("schema") != "task40extra.review_v24_bounded_port_reuse_volume_selector.v1"
        or selector.get("campaign_window_sha256") != TASK40_V24_CAMPAIGN_SHA256
        or selector.get("input_sha256") != _sha256_file(input_path)
        or selector.get("q_only_scan_manifest_sha256")
        != q_only_binding.get("scan_manifest_sha256")
        or selector.get("q_only_checkpoint_metadata_sha256")
        != q_only_binding.get("checkpoint_metadata_sha256")
        or selector.get("q_only_checkpoint_payload_sha256")
        != q_only_binding.get("checkpoint_payload_sha256")
        or selector.get("mode_count") != 32
        or selector.get("selection")
        != "first valid actual mode for every side x global-q x s/polarization group"
        or selector.get("max_cache_bytes") != 536_870_912
        or selector.get("volume_trace_dimension") != 432
        or selector.get("face_panel_rows") != 60
        or selector.get("y_orbit_count") != 8
        or selector.get("sum_duplicate_cell_integrals") is not True
    ):
        raise ValueError("V24 C/D selector differs from the frozen bounded sample contract")
    operation = selector.get("operation", "C_PORT_REUSE_VOLUME_CENSUS")
    if operation not in {"C_PORT_REUSE_VOLUME_CENSUS", "D_REAL_EDGE_PANEL"}:
        raise ValueError("V24 selector names an unsupported C/D operation")
    c_artifact_binding: dict[str, str] = {}
    if operation == "D_REAL_EDGE_PANEL":
        results_root = (repo_root / "results").resolve()
        for path_key, hash_key in (
            ("c_sample_path", "c_sample_sha256"),
            ("c_cache_path", "c_cache_sha256"),
            ("c_replay_path", "c_replay_sha256"),
        ):
            artifact_path = (repo_root / str(selector.get(path_key, ""))).resolve()
            artifact_hash = selector.get(hash_key)
            if (
                not artifact_path.is_relative_to(results_root)
                or not artifact_path.is_file()
                or not isinstance(artifact_hash, str)
                or _sha256_file(artifact_path) != artifact_hash
            ):
                raise ValueError(f"V24 D selector has an invalid hash-bound C artifact: {path_key}")
            c_artifact_binding[path_key] = str(artifact_path)
            c_artifact_binding[hash_key] = artifact_hash
        if not isinstance(selector.get("c_source_sha"), str):
            raise ValueError("V24 D selector must bind the completed C source SHA")
        c_artifact_binding["c_source_sha"] = str(selector["c_source_sha"])
    q0_path = (repo_root / str(selector.get("q0_partial_checker_path", ""))).resolve()
    if not q0_path.is_relative_to(allowed_root) or not q0_path.is_file():
        raise ValueError("V24 C/D selector is missing its bound q0 partial checker receipt")
    q0_sha = _sha256_file(q0_path)
    if selector.get("q0_partial_checker_sha256") != q0_sha:
        raise ValueError("V24 C/D selector q0 checker receipt hash differs")
    q0_receipt = json.loads(q0_path.read_text(encoding="utf-8"))
    q0_checks = q0_receipt.get("checks")
    if (
        q0_receipt.get("status") != "PARTIAL_RECEIPT_CHECKED"
        or q0_receipt.get("checker_passed") is not True
        or q0_receipt.get("official_result") is not False
        or q0_receipt.get("full_pass") is not False
        or not isinstance(q0_checks, dict)
        or not q0_checks
        or not all(value is True for value in q0_checks.values())
    ):
        raise ValueError("V24 C/D selector q0 partial receipt is not a qualified checker pass")
    return {
        "operation": str(operation),
        "selector_path": str(selector_path),
        "selector_sha256": hashlib.sha256(selector_raw).hexdigest(),
        "schema": str(selector["schema"]),
        "q0_partial_checker_path": str(q0_path),
        "q0_partial_checker_sha256": q0_sha,
        "q_only_scan_manifest_sha256": str(q_only_binding["scan_manifest_sha256"]),
        "q_only_checkpoint_metadata_sha256": str(q_only_binding["checkpoint_metadata_sha256"]),
        "q_only_checkpoint_payload_sha256": str(q_only_binding["checkpoint_payload_sha256"]),
        "mode_count": 32,
        "max_cache_bytes": 536_870_912,
        **c_artifact_binding,
    }


def _bind_v23_q_only_scan_checkpoint(
    scan_directory: Path,
    *,
    input_path: Path,
    campaign_registration: dict[str, Any],
    profile: str,
    stop_stage: str,
    repo_root: Path,
) -> dict[str, str | int]:
    """Bind the immutable V23 scan artifact to the current V23 or V24 execution."""

    expected_old_source = "1291aeef089e6c02c4b9e28125f60072aa769340"
    scan_directory = scan_directory.resolve()
    if not scan_directory.is_relative_to((repo_root / "results").resolve()):
        raise ValueError("V23 q-only selector must name a prior run under this repository's results")
    if (
        profile != V23_TARGET_PROFILE
        or stop_stage != "target_operator_probe"
        or campaign_registration.get("sha256")
        not in {TASK40_V23_CAMPAIGN_SHA256, TASK40_V24_CAMPAIGN_SHA256}
    ):
        raise ValueError("V23 q-only selector is restricted to the registered Ny8 V23/V24 probe")
    manifest_path = scan_directory / "run_manifest.json"
    summary_path = scan_directory / "run_summary.json"
    if not manifest_path.is_file() or not summary_path.is_file():
        raise ValueError("selected old V23 scan is missing its run manifest or summary")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    current_input_sha = _sha256_file(input_path)
    campaign = manifest.get("task40_v20_campaign", {})
    old_window_path = (repo_root / TASK40_V23_CAMPAIGN_WINDOW).resolve()
    old_accounting_path = old_window_path.with_name("campaign_accounting_v10.jsonl")
    if (
        manifest.get("source_sha") != expected_old_source
        or manifest.get("input_sha256") != current_input_sha
        or summary.get("status") != "finished"
        or summary.get("result_classification") != "WORKER_FAILED"
        or campaign.get("window_sha256") != TASK40_V23_CAMPAIGN_SHA256
        or Path(str(campaign.get("window_path", ""))).resolve() != old_window_path
        or Path(str(campaign.get("accounting_path", ""))).resolve()
        != old_accounting_path
        or not old_window_path.is_file()
        or _sha256_file(old_window_path) != TASK40_V23_CAMPAIGN_SHA256
        or not old_accounting_path.is_file()
        or _sha256_file(old_accounting_path)
        != TASK40_V24_PARENT_LEDGER["sha256"]
    ):
        raise ValueError("selected old scan source/input/window or terminal classification differs")
    numerical_output = _checker_numerical_output_directory(
        scan_directory,
        Path(str(summary.get("numerical_output_directory", ""))),
    )
    probe_path = numerical_output / "v22_target_operator_probe.json"
    q_failure_path = numerical_output / "v23_reference_q_port_tile.json"
    witness_path = numerical_output / "v22_pre_sweep_witness.json"
    preflight_path = numerical_output / "v20_stage_preflight.json"
    required = (probe_path, q_failure_path, witness_path, preflight_path)
    if any(not path.is_file() for path in required):
        raise ValueError("selected old V23 scan is missing its probe, q failure, witness, or preflight")
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    q_failure = json.loads(q_failure_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    checkpoint = probe.get("latest_mode_checkpoint")
    mode_inventory = preflight.get("target_mode_inventory", {})
    if (
        probe.get("status") != "FAILED_SELECTED_Q_PORT_TILE"
        or q_failure.get("status") != "FAILED"
        or q_failure.get("failure_type") != "TypeError"
        or "list indices" not in str(q_failure.get("failure_message", ""))
        or not isinstance(checkpoint, dict)
        or checkpoint.get("completed_mode_count") != 32_060
        or preflight.get("source_sha") != expected_old_source
    ):
        raise ValueError("selected old V23 scan does not contain the preserved full-prefix q-tile failure")
    identity = {
        "source_sha": expected_old_source,
        "input_sha256": manifest.get("input_sha256"),
        "physical_model_sha256": manifest.get("physical_model_sha256"),
        "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256"),
        "ordered_mode_key_sha256": mode_inventory.get("ordered_mode_key_sha256"),
        "campaign_window_sha256": TASK40_V23_CAMPAIGN_SHA256,
    }
    checkpoint_key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    checkpoint_directory = (
        repo_root
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/operator_checkpoints"
        / checkpoint_key
    ).resolve()
    checkpoint_path = Path(str(checkpoint.get("checkpoint_json_path", "")))
    if not checkpoint_path.is_absolute():
        checkpoint_path = (numerical_output / checkpoint_path).resolve()
    else:
        checkpoint_path = checkpoint_path.resolve()
    if not checkpoint_path.is_file() or checkpoint_path.parent != checkpoint_directory:
        raise ValueError("old V23 terminal checkpoint path does not match its source-bound identity")
    checkpoint_data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint_data != checkpoint:
        raise ValueError("old V23 terminal checkpoint metadata differs from the scan's embedded receipt")
    payload = checkpoint_data.get("actual_action_payload", {})
    payload_path = (checkpoint_path.parent / str(payload.get("path", ""))).resolve()
    if (
        not payload_path.is_file()
        or payload_path.parent != checkpoint_path.parent
        or _sha256_file(payload_path) != payload.get("sha256")
    ):
        raise ValueError("old V23 terminal checkpoint payload is missing or hash-mismatched")
    return {
        "execution_campaign_window_path": str(campaign_registration["path"]),
        "execution_campaign_window_sha256": str(campaign_registration["sha256"]),
        "artifact_campaign_window_path": str(old_window_path),
        "artifact_campaign_window_sha256": TASK40_V23_CAMPAIGN_SHA256,
        "artifact_campaign_accounting_path": str(old_accounting_path),
        "scan_run_directory": str(scan_directory),
        "scan_manifest_path": str(manifest_path),
        "scan_manifest_sha256": _sha256_file(manifest_path),
        "scan_numerical_output": str(numerical_output),
        "scan_preflight_path": str(preflight_path),
        "scan_witness_path": str(witness_path),
        "old_q_failure_path": str(q_failure_path),
        "old_q_failure_sha256": _sha256_file(q_failure_path),
        "old_source_sha": expected_old_source,
        "checkpoint_metadata_path": str(checkpoint_path),
        "checkpoint_metadata_sha256": _sha256_file(checkpoint_path),
        "checkpoint_payload_path": str(payload_path),
        "checkpoint_payload_sha256": str(payload["sha256"]),
        "completed_mode_count": 32_060,
    }


def _validate_v24_q_only_selector(
    campaign_registration: dict[str, Any],
    *,
    stop_stage: str,
    scan_directory: Path | None,
    cd_selector_path: Path | None = None,
) -> None:
    if (
        campaign_registration.get("version") == "V24"
        and stop_stage == "target_operator_probe"
        and scan_directory is None
    ):
        raise ValueError("V24 target_operator_probe requires the registered V23 q-only scan selector")
    if cd_selector_path is not None and (
        campaign_registration.get("version") != "V24"
        or stop_stage != "target_operator_probe"
        or scan_directory is None
    ):
        raise ValueError("V24 C/D selector requires V24 target_operator_probe and its q-only scan checkpoint")


def _run_case_output_checker(
    packet_path: Path,
    runtime_prefix: Path,
    *,
    expected_channel_count: int = 700,
) -> list[str]:
    if type(expected_channel_count) is not int or expected_channel_count < 1:
        raise ValueError("official checker requires the registered positive channel count")
    return [
        str(runtime_prefix / "bin/python"),
        "-m",
        "src.runners.task40_v10_output_checker",
        str(packet_path),
        "--expected-channel-count",
        str(expected_channel_count),
    ]


def _v31_missing_numerical_output_is_bound_worker_failure(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_path: Path,
    repo_root: Path,
    source_sha: str,
    campaign_sha256: str,
    campaign_window_path: Path,
) -> bool:
    """Bind absent V31 output to its exact worker failure or enforced cutoff."""
    root = repo_root.resolve()
    window_path = (
        campaign_window_path
        if campaign_window_path.is_absolute()
        else root / campaign_window_path
    ).resolve()

    def resolve_repo_path(path: Path) -> Path:
        return (path if path.is_absolute() else root / path).resolve()

    if (
        numerical_path.exists()
        or any(
            not resolve_repo_path(path).is_relative_to(root)
            for path in (input_path, summary_path, manifest_path, numerical_path)
        )
        or not input_path.is_file()
        or not summary_path.is_file()
        or not manifest_path.is_file()
        or not window_path.is_relative_to(root)
        or not window_path.is_file()
        or _sha256_file(window_path) != campaign_sha256
    ):
        return False
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        window_payload = json.loads(window_path.read_text(encoding="utf-8"))
        _raw, input_payload = _read_case(input_path)
        expected_run_id = input_payload.get("run_id")
    except Exception:
        return False
    try:
        expected_campaign_seconds = float(window_payload["campaign_seconds"])
        expected_numeric_seconds = float(window_payload["numeric_cutoff_seconds"])
        expected_closeout_seconds = float(window_payload["closeout_reserve_seconds"])
    except (KeyError, TypeError, ValueError):
        return False
    if (
        expected_campaign_seconds <= 0.0
        or expected_numeric_seconds <= 0.0
        or expected_closeout_seconds <= 0.0
        or expected_numeric_seconds + expected_closeout_seconds != expected_campaign_seconds
    ):
        return False
    if not isinstance(summary, Mapping) or not isinstance(manifest, Mapping):
        return False
    manifest_campaign = manifest.get("task40_v20_campaign")
    manifest_campaign = manifest_campaign if isinstance(manifest_campaign, Mapping) else {}
    summary_campaign = summary.get("task40_v20_campaign")
    summary_campaign = summary_campaign if isinstance(summary_campaign, Mapping) else {}
    from src.runners.task40_v31_contract import V31_PROFILE

    summary_numerical_path = resolve_repo_path(
        Path(str(summary.get("numerical_output_directory", "")))
    )
    manifest_numerical_path = resolve_repo_path(
        Path(str(manifest.get("numerical_output_directory", "")))
    )
    recorded_input_path = resolve_repo_path(Path(str(manifest.get("input_path", ""))))
    recorded_window_path = resolve_repo_path(
        Path(str(manifest_campaign.get("window_path", "")))
    )
    summary_window_path = resolve_repo_path(
        Path(str(summary_campaign.get("path", summary_campaign.get("window_path", ""))))
    )
    run_directory = summary_path.resolve().parent
    output_directory = resolve_repo_path(Path(str(summary.get("output_directory", ""))))
    manifest_output_directory = resolve_repo_path(
        Path(str(manifest.get("output_directory", "")))
    )
    input_sha256 = _sha256_file(input_path)
    manifest_source_sha = manifest.get("source_sha")
    manifest_input_sha256 = manifest.get("input_sha256")
    solver = input_payload.get("solver", {}) if isinstance(input_payload, Mapping) else {}
    identity_bound = bool(
        expected_run_id == "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
        and summary.get("run_id") == manifest.get("run_id") == expected_run_id
        and manifest_source_sha == source_sha
        and manifest_input_sha256 == input_sha256
        and ("source_sha" not in summary or summary.get("source_sha") == manifest_source_sha)
        and (
            "input_sha256" not in summary
            or summary.get("input_sha256") == manifest_input_sha256
        )
        and summary_path.resolve().parent == manifest_path.resolve().parent == run_directory
        and output_directory == run_directory
        and manifest_output_directory == run_directory
        and recorded_input_path == input_path.resolve()
        and summary_numerical_path == numerical_path.resolve()
        and manifest_numerical_path == numerical_path.resolve()
        and summary_numerical_path.parent == run_directory
        and solver.get("preconditioner") == V31_PROFILE
        and recorded_window_path == window_path
        and summary_window_path == window_path
        and manifest_campaign.get("window_sha256") == campaign_sha256
        and summary_campaign.get(
            "sha256", summary_campaign.get("window_sha256")
        ) == campaign_sha256
    )
    if not identity_bound:
        return False

    # Preserve the original V31 worker-failure acceptance rule unchanged.
    if (
        summary.get("status") == "finished"
        and summary.get("result_classification") == "WORKER_FAILED"
        and summary.get("exit_status") == 4
    ):
        return True

    watchdog_path = run_directory / "watchdog" / "summary.json"
    if not watchdog_path.is_relative_to(root) or not watchdog_path.is_file():
        return False
    try:
        watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(watchdog, Mapping):
        return False

    watchdog_campaign = watchdog.get("task40_v10_campaign")
    watchdog_campaign = watchdog_campaign if isinstance(watchdog_campaign, Mapping) else {}
    watchdog_source = watchdog.get("source_state")
    watchdog_source = watchdog_source if isinstance(watchdog_source, Mapping) else {}
    authority = summary.get("resource_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    time_exceeded = watchdog.get("time_exceeded")
    time_exceeded = time_exceeded if isinstance(time_exceeded, Mapping) else {}
    time_end = watchdog.get("time_end_observation")
    time_end = time_end if isinstance(time_end, Mapping) else {}
    stop_event = watchdog.get("stop_event")
    stop_event = stop_event if isinstance(stop_event, Mapping) else {}
    first_sigterm = watchdog.get("first_SIGTERM")
    first_sigkill = watchdog.get("first_SIGKILL")
    leader_exit_code = watchdog.get("leader_exit_code")

    def valid_tree_signal(value: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and value.get("scope") == "whole child tree"
            and type(value.get("timestamp_ns")) is int
            and value.get("timestamp_ns") > 0
            and type(value.get("monotonic")) in (int, float)
            and math.isfinite(float(value.get("monotonic")))
            and value.get("monotonic") >= 0.0
        )

    stop_monotonic = stop_event.get("monotonic")
    stop_timestamp_ns = stop_event.get("timestamp_ns")
    stop_record_bound = bool(
        stop_event.get("reason") == "PERFORMANCE_CONTROLLED_STOP"
        and stop_event.get("grace_seconds") == 30
        and type(stop_timestamp_ns) is int
        and stop_timestamp_ns > 0
        and type(stop_monotonic) in (int, float)
        and math.isfinite(float(stop_monotonic))
        and stop_monotonic >= 0.0
    )
    term_after_stop = bool(
        stop_record_bound
        and valid_tree_signal(first_sigterm)
        and first_sigterm["monotonic"] >= stop_monotonic
        and first_sigterm["timestamp_ns"] >= stop_timestamp_ns
    )
    if type(leader_exit_code) is not int:
        signal_outcome_bound = False
    elif leader_exit_code == -9:
        signal_outcome_bound = bool(
            term_after_stop
            and valid_tree_signal(first_sigkill)
            and first_sigkill["monotonic"] >= first_sigterm["monotonic"]
            and first_sigkill["timestamp_ns"] >= first_sigterm["timestamp_ns"]
        )
    elif leader_exit_code in (0, -15):
        signal_outcome_bound = term_after_stop and first_sigkill is None
    else:
        signal_outcome_bound = False
    cutoff_accounting = watchdog_campaign.get("watchdog_end_accounting")
    cutoff_accounting = cutoff_accounting if isinstance(cutoff_accounting, Mapping) else {}
    phase_sub_budget_seconds = watchdog_campaign.get("phase_sub_budget_seconds")
    job_swap = watchdog.get("job_cgroup_swap")
    job_swap = job_swap if isinstance(job_swap, Mapping) else {}
    job_swap_end = job_swap.get("end")
    job_swap_end = job_swap_end if isinstance(job_swap_end, Mapping) else {}
    authority_keys = (
        "classification",
        "leader_exit_code",
        "descendants_cleared",
        "remaining_child_pids",
        "time_gate_action",
        "time_gate_evaluated",
        "time_exceeded",
        "stop_event",
        "task40_v10_campaign",
    )
    return bool(
        summary.get("status") == manifest.get("status") == "finished"
        and summary.get("result_classification")
        == manifest.get("result_classification")
        == watchdog.get("classification")
        == "PERFORMANCE_CONTROLLED_STOP"
        and signal_outcome_bound
        and summary.get("exit_status")
        == manifest.get("exit_status")
        == leader_exit_code
        and summary.get("full_workflow_time_exceeded") is True
        and watchdog_source.get("source_sha") == source_sha
        and watchdog_source.get("tracked_and_nonignored_untracked_clean") is True
        and watchdog_campaign.get("window_sha256") == campaign_sha256
        and watchdog_campaign.get("phase") == "numeric"
        and watchdog_campaign.get("campaign_seconds") == expected_campaign_seconds
        and watchdog_campaign.get("numerical_cutoff_seconds") == expected_numeric_seconds
        and cutoff_accounting.get("label") == "watchdog_end"
        and cutoff_accounting.get("phase") == "numeric"
        and cutoff_accounting.get("campaign_window_sha256") == campaign_sha256
        and cutoff_accounting.get("t0_utc_ns") == watchdog_campaign.get("t0_utc_ns")
        and cutoff_accounting.get("deadline_utc_ns") == watchdog_campaign.get("deadline_utc_ns")
        and cutoff_accounting.get("cutoff_seconds") == expected_numeric_seconds
        and isinstance(cutoff_accounting.get("cumulative_charged_seconds"), (int, float))
        and cutoff_accounting.get("cumulative_charged_seconds") >= expected_numeric_seconds
        and watchdog.get("time_gate_action") == "enforce"
        and watchdog.get("time_gate_evaluated") is True
        and time_exceeded.get("workflow") is True
        and time_exceeded.get("solve") is False
        and time_exceeded.get("active_pc") is False
        and time_end.get("time_policy") == "enforce"
        and time_end.get("time_gate_action") == "enforce"
        and time_end.get("time_gate_evaluated") is True
        and time_end.get("exceeded") is True
        and time_end.get("passed") is False
        and isinstance(time_end.get("observed_seconds"), (int, float))
        and isinstance(time_end.get("limit_seconds"), (int, float))
        and type(phase_sub_budget_seconds) in (int, float)
        and 0.0 < float(phase_sub_budget_seconds) <= expected_numeric_seconds
        and float(time_end.get("limit_seconds")) == float(phase_sub_budget_seconds)
        and time_end.get("observed_seconds") > time_end.get("limit_seconds")
        and stop_event.get("reason") == "PERFORMANCE_CONTROLLED_STOP"
        and stop_event.get("grace_seconds") == 30
        and watchdog.get("descendants_cleared") is True
        and watchdog.get("remaining_child_pids") == []
        and watchdog.get("process_tree_all_status_readable") is True
        and watchdog.get("process_tree_all_identity_complete") is True
        and watchdog.get("process_tree_identity_coverage") == "complete"
        and watchdog.get("job_cgroup_swap_gate_enforced") is True
        and watchdog.get("job_cgroup_swap_start_bytes") == 0
        and watchdog.get("sampled_process_tree_swap_peak_bytes") == 0
        and job_swap.get("gate_enforced") is True
        and job_swap.get("passed") is True
        and job_swap.get("peak_swap_current_bytes") == 0
        and job_swap_end.get("swap_current_bytes") == 0
        and all(authority.get(key) == watchdog.get(key) for key in authority_keys)
    )


def _task40_v30_closeout_checker_authorization(
    *,
    command: list[str],
    checker_kind: str,
    runtime_prefix: Path,
    repo_root: Path,
    evidence_directory: Path,
    campaign_sha256: str,
    contract_sha256: str,
    source_state: Mapping[str, Any],
    profile: str,
    allow_missing_numerical_output_for_v31_worker_failure: bool = False,
    expected_campaign_window_path: Path | None = None,
) -> dict[str, Any]:
    """Bind only the two registered read-only checker commands to closeout time."""
    runtime = runtime_prefix.resolve() / "bin" / "python"
    root = repo_root.resolve()
    evidence = evidence_directory.resolve()
    argv = [str(value) for value in command]
    if not argv or Path(argv[0]).resolve() != runtime.resolve():
        raise ValueError("V30 closeout checker must use the qualified Python executable")
    if source_state.get("clean") is not True or not source_state.get("source_sha"):
        raise ValueError("V30 closeout checker requires a clean, source-bound service state")

    def resolve_run_path(raw: str) -> Path:
        supplied = Path(raw)
        return (root / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()

    from src.io.physical_intermediate_profile import profile_facts

    profile_gates = profile_facts(profile).get("gates", {})
    expected_channel_count = profile_gates.get("all_original_modes_retained")
    if type(expected_channel_count) is not int or expected_channel_count < 1:
        raise ValueError("V30 profile has no frozen output channel count")
    inputs: list[Path] = []
    if checker_kind == "task40_v10_independent_output_checker":
        if (
            len(argv) != 6
            or argv[1:3] != ["-m", "src.runners.task40_v10_output_checker"]
            or argv[4:] != ["--expected-channel-count", str(expected_channel_count)]
        ):
            raise ValueError("V30 closeout command is not the registered official output checker")
        packet = resolve_run_path(argv[3])
        if (
            packet.name != "v10_candidate_official_output.json"
            or not packet.is_file()
            or not packet.is_relative_to(root)
        ):
            raise ValueError("V30 output checker packet is outside the current repository evidence")
        inputs.append(packet)
    elif checker_kind == "task40_v20_partial_receipt_checker":
        script = (root / "scripts" / "task40_v20_service_workflow.py").resolve()
        if (
            len(argv) != 15
            or resolve_run_path(argv[1]) != script
            or argv[2] != "check-partial"
            or argv[3::2]
            != [
                "--input",
                "--summary",
                "--manifest",
                "--numerical-output",
                "--stop-stage",
                "--output",
            ]
        ):
            raise ValueError("V30 closeout command is not the registered partial-receipt checker")
        values = argv[4::2]
        if len(values) != 6 or values[4] != "full":
            raise ValueError("V30 partial checker arguments are incomplete")
        input_path, summary_path, manifest_path, numerical_path, output_path = (
            resolve_run_path(values[index]) for index in (0, 1, 2, 3, 5)
        )
        numerical_output_is_bound = numerical_path.is_dir()
        if (
            not numerical_output_is_bound
            and allow_missing_numerical_output_for_v31_worker_failure
            and expected_campaign_window_path is not None
        ):
            numerical_output_is_bound = _v31_missing_numerical_output_is_bound_worker_failure(
                input_path=input_path,
                summary_path=summary_path,
                manifest_path=manifest_path,
                numerical_path=numerical_path,
                repo_root=root,
                source_sha=str(source_state.get("source_sha", "")),
                campaign_sha256=campaign_sha256,
                campaign_window_path=expected_campaign_window_path,
            )
        if (
            not input_path.is_file()
            or not summary_path.is_file()
            or not manifest_path.is_file()
            or not numerical_output_is_bound
            or any(not path.is_relative_to(root) for path in (
                input_path, summary_path, manifest_path, numerical_path
            ))
            or not output_path.is_relative_to(evidence)
        ):
            raise ValueError("V30 partial checker paths are not bound to current run evidence")
        inputs.extend((input_path, summary_path, manifest_path))
    else:
        raise ValueError("checker kind is not eligible for the V30 closeout reserve")

    command_sha256 = hashlib.sha256(
        json.dumps(argv, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    input_sha256s = [_sha256_file(path) for path in inputs]
    return {
        "schema": "task40extra.review_v31_closeout_checker_authorization.v1",
        "phase": "closeout",
        "purpose": "registered_read_only_required_checker",
        "checker_kind": checker_kind,
        "command_sha256": command_sha256,
        "input_paths": [str(path) for path in inputs],
        "input_sha256s": input_sha256s,
        "expected_channel_count": expected_channel_count,
        "campaign_window_sha256": campaign_sha256,
        "v30_contract_sha256": contract_sha256,
        "source_sha": str(source_state["source_sha"]),
        "source_branch": str(source_state.get("branch", "")),
        "source_clean": True,
    }


def _task40_v31_closeout_checker_authorization(
    *,
    command: list[str],
    checker_kind: str,
    runtime_prefix: Path,
    repo_root: Path,
    evidence_directory: Path,
    campaign_sha256: str,
    contract_path: Path,
    source_state: Mapping[str, Any],
    profile: str,
) -> dict[str, Any]:
    """Bind the read-only checker to a user-approved V31 contract and window."""
    from src.runners.task40_v31_contract import require_v31_execution_contract

    contract, contract_sha = require_v31_execution_contract(
        contract_path, current_root=repo_root
    )
    window = contract["execution"]["window"]
    if window.get("window_sha256") != campaign_sha256:
        raise ValueError("V31 closeout checker window differs from its approved contract")
    common = _task40_v30_closeout_checker_authorization(
        command=command,
        checker_kind=checker_kind,
        runtime_prefix=runtime_prefix,
        repo_root=repo_root,
        evidence_directory=evidence_directory,
        campaign_sha256=campaign_sha256,
        contract_sha256=contract_sha,
        source_state=source_state,
        profile=profile,
        allow_missing_numerical_output_for_v31_worker_failure=True,
        expected_campaign_window_path=Path(str(window["window_path"])),
    )
    common["schema"] = "task40extra.review_v31_closeout_checker_authorization.v2"
    common["v31_contract_sha256"] = common.pop("v30_contract_sha256")
    return common


def _run_required_checker_supervision(request: dict[str, Any]) -> dict[str, Any]:
    """Run the checker under the fixed Task40 watchdog gates in a qualified child."""

    from benchmarks.subreaper_watchdog import PHYSICAL_MEMORY_PRESSURE_POLICY, supervise
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    command = [str(value) for value in request["command"]]
    checker_kind = str(request["checker_kind"])
    evidence_directory = Path(request["evidence_directory"])
    runtime_prefix = Path(request["runtime_prefix"])
    environment = dict(os.environ)
    activation_marker = _qualified_activation_identity(environment)
    if activation_marker is None or request.get("activation_marker") != activation_marker:
        raise RuntimeError("required checker supervisor activation identity differs")
    numeric_environment = request.get("numeric_environment", {})
    if not isinstance(numeric_environment, dict):
        raise RuntimeError("required checker supervisor numeric environment is malformed")
    allowed_numeric_settings = {
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    }
    if not set(numeric_environment) <= allowed_numeric_settings:
        raise RuntimeError("required checker supervisor request has unsupported environment fields")
    for key, value in numeric_environment.items():
        if environment.get(key) != value:
            raise RuntimeError(f"required checker supervisor setting differs: {key}")
    tree_accounting_root_pid = int(request["service_parent_pid"])
    service_cgroup_membership = str(request["service_cgroup_membership"])
    repo_root = Path(request["repo_root"])
    campaign_window = Path(request["campaign_window"])
    campaign_sha256 = str(request["campaign_sha256"])
    campaign_accounting = Path(request["campaign_accounting"])
    source_state = dict(request["source_state"])
    profile = str(request["profile"])
    v29_watchdog_gate = None
    v29_contract = None
    v30_watchdog_gate = None
    v30_contract = None
    v30_contract_sha = None
    v31_watchdog_gate = None
    v31_contract = None
    v31_contract_sha = None
    if environment.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1":
        from src.runners.task40_v29_contract import (
            require_authorized_contract,
            require_authorized_selector,
        )

        contract, contract_sha = require_authorized_contract(
            environment["TASK40_V29_CONTRACT_PATH"],
            expected_sha256=environment["TASK40_V29_CONTRACT_SHA256"],
            current_root=repo_root,
        )
        require_authorized_selector(
            environment["TASK40_V29_SELECTOR_PATH"],
            expected_sha256=environment["TASK40_V29_SELECTOR_SHA256"],
            contract_path=environment["TASK40_V29_CONTRACT_PATH"],
            contract_sha256=contract_sha,
            contract=contract,
        )
        if (
            Path(str(contract["execution"]["campaign_window_path"])).resolve()
            != campaign_window.resolve()
            or contract["execution"]["campaign_window_sha256"] != campaign_sha256
        ):
            raise RuntimeError("V29 watchdog campaign binding differs from the approved execution window")
        if request.get("v29_resource_gate", {}).get("passed") is not True:
            raise RuntimeError("V29 watchdog request lacks a passing parent resource-contract check")
        v29_watchdog_gate = _v29_live_resource_gate(
            contract,
            stage="v29_checker_watchdog_child_entry",
        )
    elif request.get("v29_resource_gate") is not None:
        raise RuntimeError("V29 watchdog resource receipt was supplied without strict V29 mode")
    if environment.get("TASK40_V30_STRICT_EXECUTION") == "1":
        from src.runners.task40_v30_contract import require_authorized_contract

        v30_contract, v30_contract_sha = require_authorized_contract(
            environment["TASK40_V30_CONTRACT_PATH"],
            expected_sha256=environment["TASK40_V30_CONTRACT_SHA256"],
            current_root=repo_root,
        )
        if (
            Path(str(v30_contract["execution"]["campaign_window_path"])).resolve()
            != campaign_window.resolve()
            or v30_contract["execution"]["campaign_window_sha256"] != campaign_sha256
            or v30_contract_sha != environment["TASK40_V30_CONTRACT_SHA256"]
        ):
            raise RuntimeError("V30 watchdog campaign binding differs from the approved window")
        if request.get("v30_resource_gate", {}).get("passed") is not True:
            raise RuntimeError("V30 watchdog request lacks a passing parent resource-contract check")
        v30_watchdog_gate = _v30_live_resource_gate(
            v30_contract,
            stage="v30_checker_watchdog_child_entry",
        )
    elif request.get("v30_resource_gate") is not None:
        raise RuntimeError("V30 watchdog resource receipt was supplied without strict V30 mode")

    if environment.get("TASK40_V31_STRICT_EXECUTION") == "1":
        if environment.get("TASK40_V30_STRICT_EXECUTION") == "1":
            raise RuntimeError("V31 checker supervision cannot inherit V30 strict authorization")
        from src.runners.task40_v31_contract import require_v31_execution_contract

        v31_contract, v31_contract_sha = require_v31_execution_contract(
            environment["TASK40_V31_CONTRACT_PATH"],
            expected_sha256=environment["TASK40_V31_CONTRACT_SHA256"],
            current_root=repo_root,
        )
        window = v31_contract["execution"]["window"]
        if (
            Path(str(window["window_path"])).resolve() != campaign_window.resolve()
            or window["window_sha256"] != campaign_sha256
            or v31_contract_sha != environment["TASK40_V31_CONTRACT_SHA256"]
        ):
            raise RuntimeError("V31 watchdog campaign binding differs from the approved window")
        if request.get("v31_resource_gate", {}).get("passed") is not True:
            raise RuntimeError("V31 watchdog request lacks a passing parent resource-contract check")
        v31_watchdog_gate = _v31_live_resource_gate(
            v31_contract, stage="v31_checker_watchdog_child_entry"
        )
    elif request.get("v31_resource_gate") is not None:
        raise RuntimeError("V31 watchdog resource receipt was supplied without strict V31 mode")

    campaign_phase = str(request.get("campaign_phase", "numeric"))
    closeout_authorization = request.get("closeout_authorization")
    if v31_contract is not None:
        expected_closeout_authorization = _task40_v31_closeout_checker_authorization(
            command=command,
            checker_kind=checker_kind,
            runtime_prefix=runtime_prefix,
            repo_root=repo_root,
            evidence_directory=evidence_directory,
            campaign_sha256=campaign_sha256,
            contract_path=Path(environment["TASK40_V31_CONTRACT_PATH"]),
            source_state=source_state,
            profile=profile,
        )
        if campaign_phase != "closeout" or closeout_authorization != expected_closeout_authorization:
            raise RuntimeError("V31 checker closeout phase is not bound to its exact command and identities")
    elif v30_contract is not None:
        expected_closeout_authorization = _task40_v30_closeout_checker_authorization(
            command=command,
            checker_kind=checker_kind,
            runtime_prefix=runtime_prefix,
            repo_root=repo_root,
            evidence_directory=evidence_directory,
            campaign_sha256=campaign_sha256,
            contract_sha256=str(v30_contract_sha),
            source_state=source_state,
            profile=profile,
        )
        if (
            campaign_phase != "closeout"
            or closeout_authorization != expected_closeout_authorization
        ):
            raise RuntimeError("V30 checker closeout phase is not bound to its exact command and identities")
    elif campaign_phase != "numeric" or closeout_authorization is not None:
        raise RuntimeError("closeout phase is unavailable without the authorized V30 checker contract")

    if _qualified_activation_identity(environment) is None:
        raise RuntimeError("required checker supervisor lacks a qualified runtime profile")
    if not os.path.samefile(sys.executable, runtime_prefix / "bin/python"):
        raise RuntimeError("required checker supervisor is not using the qualified interpreter")

    resources = profile_facts(profile)["resources"]
    if resources.get("watchdog_memory_policy") != PHYSICAL_MEMORY_PRESSURE_POLICY:
        raise ValueError("V20 checker watchdog policy differs from the qualified physical-pressure policy")
    watchdog_tree_cap_bytes = int(resources["process_tree_rss_cap_bytes"])
    watchdog_host_reserve_bytes = None
    if v29_contract is not None:
        approved_resources = v29_contract["execution"]["resources"]
        watchdog_tree_cap_bytes = int(approved_resources["task_memory_max_bytes"])
        watchdog_host_reserve_bytes = int(approved_resources["host_reserve_bytes"])
    if v30_contract is not None:
        approved_resources = v30_contract["execution"]["resources"]
        watchdog_tree_cap_bytes = int(approved_resources["task_memory_max_bytes"])
        watchdog_host_reserve_bytes = int(approved_resources["host_reserve_bytes"])
    if v31_contract is not None:
        approved_resources = v31_contract["execution"]["resources"]
        watchdog_tree_cap_bytes = int(approved_resources["task_memory_max_bytes"])
        watchdog_host_reserve_bytes = int(approved_resources["host_reserve_bytes"])
    workflow_limit_seconds = (
        float(v31_contract["execution"]["window"]["closeout_seconds"])
        if v31_contract is not None
        else float(v30_contract["execution"]["window"]["closeout_reserve_seconds"])
        if v30_contract is not None
        else float(resources["workflow_seconds"])
    )
    watchdog_directory = evidence_directory / "required_checker_watchdog"
    worker_environment = dict(environment)
    worker_environment.update(
        {
            "TASK40_V10_CAMPAIGN_WINDOW": str(campaign_window),
            "TASK40_V10_CAMPAIGN_WINDOW_SHA256": campaign_sha256,
            "TASK40_V10_CAMPAIGN_ACCOUNTING": str(campaign_accounting),
            "PHYSICAL_WATCHDOG_MEMORY_POLICY": str(
                resources["watchdog_memory_policy"]
            ),
            "PHYSICAL_WATCHDOG_PSS_POLICY": str(resources["pss_sampling_policy"]),
            "XDG_CACHE_HOME": str(
                Path(str(v29_contract["execution"]["jit_cache"])).resolve()
                if v29_contract is not None
                else Path(str(v30_contract["execution"]["jit_cache"])).resolve()
                if v30_contract is not None
                else Path(str(v31_contract["execution"]["jit_cache"])).resolve()
                if v31_contract is not None
                else (repo_root / QUALIFIED_JIT_RELATIVE).resolve()
            ),
        }
    )
    watchdog_summary = supervise(
        command,
        watchdog_directory,
        wall_seconds=workflow_limit_seconds,
        grace_seconds=30.0,
        hard_stop_immediate=True,
        timebase_guard=True,
        timebase_policy=CONSERVATIVE_REALTIME,
        time_policy=V14_TIME_POLICY_ENFORCE,
        memory_policy=str(resources["watchdog_memory_policy"]),
        pss_sampling_policy=str(resources["pss_sampling_policy"]),
        tree_cap_bytes=watchdog_tree_cap_bytes,
        host_reserve_bytes=watchdog_host_reserve_bytes,
        task_cgroup_reserve_bytes=(
            0 if v29_contract is not None or v30_contract is not None or v31_contract is not None else None
        ),
        allow_physical_pressure_tree_cap=True,
        require_job_cgroup_zero_swap=True,
        campaign_window_path=campaign_window,
        campaign_window_sha256=campaign_sha256,
        campaign_accounting_path=campaign_accounting,
        campaign_phase=campaign_phase,
        campaign_phase_authorization=closeout_authorization,
        worker_environment=worker_environment,
        source_state=source_state,
        tree_accounting_root_pid=tree_accounting_root_pid,
    )
    summary_path = evidence_directory / "required_checker_watchdog_summary.json"
    _write_json_fsync(summary_path, watchdog_summary)
    raw_output = watchdog_directory / "worker.log"
    if raw_output.is_file():
        raw_path = evidence_directory / "required_checker_output.raw.txt"
        with raw_path.open("xb") as stream:
            stream.write(raw_output.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw_path = None
        raw_text = ""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None
    complete = bool(
        watchdog_summary.get("classification") == "COMPLETED"
        and watchdog_summary.get("leader_exit_code") == 0
        and watchdog_summary.get("descendants_cleared") is True
    )
    exit_code = watchdog_summary.get("leader_exit_code")
    return_code = 0 if complete else (
        int(exit_code) if type(exit_code) is int and exit_code != 0 else 2
    )
    details = {
        "kind": checker_kind,
        "command": command,
        "watchdog_directory": str(watchdog_directory),
        "watchdog_summary_path": str(summary_path),
        "raw_output_path": None if raw_path is None else str(raw_path),
        "raw_output_sha256": None if raw_path is None else _sha256_file(raw_path),
        "watchdog_classification": watchdog_summary.get("classification"),
        "leader_exit_code": exit_code,
        "returncode": return_code,
        "payload": payload if isinstance(payload, dict) else None,
        "v29_contract_resource_gate": v29_watchdog_gate,
        "v30_contract_resource_gate": v30_watchdog_gate,
        "v31_contract_resource_gate": v31_watchdog_gate,
        "supervision": {
            "campaign_phase": campaign_phase,
            "closeout_authorization": closeout_authorization,
            "profile_workflow_limit_seconds": workflow_limit_seconds,
            "campaign_closeout_reserve_seconds": int(
                v31_contract["execution"]["window"]["closeout_seconds"]
                if v31_contract is not None
                else v30_contract["execution"]["window"]["closeout_reserve_seconds"]
                if v30_contract is not None
                else resources["campaign_closeout_reserve_seconds"]
            ),
            "campaign_window_sha256": campaign_sha256,
            "campaign_accounting_path": str(campaign_accounting),
            "memory_policy": resources["watchdog_memory_policy"],
            "pss_sampling_policy": resources["pss_sampling_policy"],
            "process_tree_rss_cap_bytes": watchdog_tree_cap_bytes,
            "host_reserve_bytes": watchdog_host_reserve_bytes,
            "zero_swap_required": True,
            "service_cgroup_membership": service_cgroup_membership,
            "process_tree_root_pid": tree_accounting_root_pid,
            "process_tree_scope_includes_user_service_parent": True,
            "process_tree_cleanup_required": True,
        },
    }
    return {
        "return_code": return_code,
        "payload": details["payload"],
        "details": details,
    }


def _supervise_required_checker(
    *,
    command: list[str],
    checker_kind: str,
    evidence_directory: Path,
    runtime_prefix: Path,
    environment: dict[str, str],
    repo_root: Path,
    campaign_window: Path,
    campaign_sha256: str,
    campaign_accounting: Path,
    source_state: dict[str, Any],
    profile: str,
    events: list[dict[str, Any]],
    event_log: Path,
    event_identity: dict[str, Any],
) -> tuple[int, dict[str, Any] | None, dict[str, Any]]:
    """Launch the watchdog from the qualified interpreter, away from the -S parent."""

    if _qualified_activation_identity(environment) is None:
        raise RuntimeError("V20 user-service did not receive a qualified runtime profile")
    v29_resource_gate = None
    v30_contract_sha = None
    v31_resource_gate = None
    v31_contract_sha = None
    if environment.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1":
        from src.runners.task40_v29_contract import (
            require_authorized_contract,
            require_authorized_selector,
        )

        contract, contract_sha = require_authorized_contract(
            environment["TASK40_V29_CONTRACT_PATH"],
            expected_sha256=environment["TASK40_V29_CONTRACT_SHA256"],
            current_root=repo_root,
        )
        require_authorized_selector(
            environment["TASK40_V29_SELECTOR_PATH"],
            expected_sha256=environment["TASK40_V29_SELECTOR_SHA256"],
            contract_path=environment["TASK40_V29_CONTRACT_PATH"],
            contract_sha256=contract_sha,
            contract=contract,
        )
        if (
            Path(str(contract["execution"]["campaign_window_path"])).resolve()
            != campaign_window.resolve()
            or contract["execution"]["campaign_window_sha256"] != campaign_sha256
        ):
            raise RuntimeError("V29 checker watchdog campaign window differs from its approved contract")
        v29_resource_gate = _v29_live_resource_gate(
            contract,
            stage="v29_before_required_checker_watchdog",
        )
    v30_resource_gate = None
    if environment.get("TASK40_V30_STRICT_EXECUTION") == "1":
        from src.runners.task40_v30_contract import require_authorized_contract

        contract, contract_sha = require_authorized_contract(
            environment["TASK40_V30_CONTRACT_PATH"],
            expected_sha256=environment["TASK40_V30_CONTRACT_SHA256"],
            current_root=repo_root,
        )
        if (
            Path(str(contract["execution"]["campaign_window_path"])).resolve()
            != campaign_window.resolve()
            or contract["execution"]["campaign_window_sha256"] != campaign_sha256
            or contract_sha != environment["TASK40_V30_CONTRACT_SHA256"]
        ):
            raise RuntimeError("V30 checker watchdog campaign binding differs from its contract")
        v30_resource_gate = _v30_live_resource_gate(
            contract,
            stage="v30_before_required_checker_watchdog",
        )
        v30_contract_sha = contract_sha
    if environment.get("TASK40_V31_STRICT_EXECUTION") == "1":
        if environment.get("TASK40_V30_STRICT_EXECUTION") == "1":
            raise RuntimeError("V31 checker watchdog cannot inherit V30 strict authorization")
        from src.runners.task40_v31_contract import require_v31_execution_contract

        contract, contract_sha = require_v31_execution_contract(
            environment["TASK40_V31_CONTRACT_PATH"],
            expected_sha256=environment["TASK40_V31_CONTRACT_SHA256"],
            current_root=repo_root,
        )
        window = contract["execution"]["window"]
        if (
            Path(str(window["window_path"])).resolve() != campaign_window.resolve()
            or window["window_sha256"] != campaign_sha256
            or contract_sha != environment["TASK40_V31_CONTRACT_SHA256"]
        ):
            raise RuntimeError("V31 checker watchdog campaign window differs from its contract")
        v31_resource_gate = _v31_live_resource_gate(
            contract, stage="v31_before_required_checker_watchdog"
        )
        v31_contract_sha = contract_sha
    campaign_phase = "numeric"
    closeout_authorization = None
    if v30_resource_gate is not None:
        campaign_phase = "closeout"
        closeout_authorization = _task40_v30_closeout_checker_authorization(
            command=command,
            checker_kind=checker_kind,
            runtime_prefix=runtime_prefix,
            repo_root=repo_root,
            evidence_directory=evidence_directory,
            campaign_sha256=campaign_sha256,
            contract_sha256=str(v30_contract_sha),
            source_state=source_state,
            profile=profile,
        )
    elif v31_resource_gate is not None:
        campaign_phase = "closeout"
        closeout_authorization = _task40_v31_closeout_checker_authorization(
            command=command,
            checker_kind=checker_kind,
            runtime_prefix=runtime_prefix,
            repo_root=repo_root,
            evidence_directory=evidence_directory,
            campaign_sha256=campaign_sha256,
            contract_path=Path(environment["TASK40_V31_CONTRACT_PATH"]),
            source_state=source_state,
            profile=profile,
        )
    request_path = evidence_directory / "required_checker_supervision_request.json"
    response_path = evidence_directory / "required_checker_supervision_response.json"
    stdout_path = evidence_directory / "required_checker_supervisor_stdout.raw.txt"
    stderr_path = evidence_directory / "required_checker_supervisor_stderr.raw.txt"
    service_parent_pid = os.getpid()
    service_cgroup_membership = _unified_cgroup_membership(service_parent_pid)
    if service_cgroup_membership is None:
        raise RuntimeError("V20 service parent has no readable unified-cgroup identity")
    numeric_setting_names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    request = {
        "command": command,
        "checker_kind": checker_kind,
        "evidence_directory": str(evidence_directory),
        "runtime_prefix": str(runtime_prefix),
        "activation_marker": _qualified_activation_identity(environment),
        "numeric_environment": {
            key: environment[key]
            for key in numeric_setting_names
            if key in environment
        },
        "service_parent_pid": service_parent_pid,
        "service_cgroup_membership": service_cgroup_membership,
        "repo_root": str(repo_root),
        "campaign_window": str(campaign_window),
        "campaign_sha256": campaign_sha256,
        "campaign_accounting": str(campaign_accounting),
        "campaign_phase": campaign_phase,
        "closeout_authorization": closeout_authorization,
        "source_state": source_state,
        "profile": profile,
        "response_path": str(response_path),
        "v29_resource_gate": v29_resource_gate,
        "v30_resource_gate": v30_resource_gate,
        "v31_resource_gate": v31_resource_gate,
    }
    _write_json_fsync(request_path, request)
    supervisor_command = [
        str(runtime_prefix / "bin/python"),
        str(Path(__file__).resolve()),
        "supervise-required-checker",
        "--request",
        str(request_path),
    ]
    child = subprocess.run(
        supervisor_command,
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    for path, content in ((stdout_path, child.stdout), (stderr_path, child.stderr)):
        with path.open("xb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    if child.returncode != 0 or not response_path.is_file():
        raise RuntimeError(
            "qualified required-checker supervisor failed "
            f"(returncode={child.returncode}): "
            f"{child.stderr[-4000:] or child.stdout[-4000:]}"
        )
    response = json.loads(response_path.read_text(encoding="utf-8"))
    if not isinstance(response, dict) or not isinstance(response.get("details"), dict):
        raise RuntimeError("qualified required-checker supervisor returned an invalid receipt")
    _append_clock_event(
        events, "required_checker_finished", event_log, event_identity
    )
    details = dict(response["details"])
    details["qualified_supervisor"] = {
        "command": supervisor_command,
        "returncode": int(child.returncode),
        "activation_marker": _qualified_activation_identity(environment),
        "request_path": str(request_path),
        "request_sha256": _sha256_file(request_path),
        "response_path": str(response_path),
        "response_sha256": _sha256_file(response_path),
        "stdout_path": str(stdout_path),
        "stdout_sha256": _sha256_file(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_sha256": _sha256_file(stderr_path),
    }
    payload = response.get("payload")
    return int(response["return_code"]), (
        payload if isinstance(payload, dict) else None
    ), details


def _run_required_checker_supervision_request(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    runtime_prefix = Path(request["runtime_prefix"])
    if _qualified_activation_identity(os.environ) is None:
        raise RuntimeError("required checker supervisor child lacks a qualified runtime profile")
    if request.get("activation_marker") != _qualified_activation_identity(os.environ):
        raise RuntimeError("required checker supervisor child runtime profile differs from request")
    if not os.path.samefile(sys.executable, runtime_prefix / "bin/python"):
        raise RuntimeError("required checker supervisor child interpreter identity differs")
    if int(request["service_parent_pid"]) != os.getppid():
        raise RuntimeError("required checker supervisor lost its user-service parent identity")
    if request["service_cgroup_membership"] != _unified_cgroup_membership():
        raise RuntimeError("required checker supervisor moved out of the user-service cgroup")
    response = _run_required_checker_supervision(request)
    _write_json_fsync(Path(request["response_path"]), response)
    return 0


def _campaign_accounting_path_from_manifest(
    run_manifest: dict[str, Any],
    *,
    expected_window_sha256: str,
    expected_accounting_path: Path,
    expected_run_id: str,
    expected_profile: str,
) -> Path:
    """Validate this V20 case's identity and its fixed campaign ledger."""

    campaign_evidence = run_manifest.get("task40_v20_campaign")
    if not isinstance(campaign_evidence, dict):
        raise ValueError("run manifest has no Task40 V20 campaign accounting identity")
    solver = run_manifest.get("solver")
    if (
        run_manifest.get("run_id") != expected_run_id
        or not isinstance(solver, dict)
        or solver.get("preconditioner") != expected_profile
    ):
        raise ValueError("run manifest does not match the requested Task40 V20 case/profile")
    accounting_path = Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
    if (
        campaign_evidence.get("window_sha256") != expected_window_sha256
        or accounting_path != expected_accounting_path.resolve()
        or not accounting_path.is_file()
    ):
        raise ValueError(
            "run manifest Task40 V20 campaign window/accounting identity is invalid"
        )
    return accounting_path


def _checker_numerical_output_directory(
    run_directory: Path, declared_numerical_output: Path
) -> Path:
    """Locate the actual packet/footer root emitted for this run."""

    candidates = (declared_numerical_output.resolve(), run_directory.resolve())
    for candidate in candidates:
        if (candidate / "v10_candidate_official_output.json").is_file():
            return candidate
    for candidate in candidates:
        if (candidate / "v20_partial_result.json").is_file():
            return candidate
    return candidates[0]


def _official_checker_passed(returncode: int, payload: Any) -> bool:
    """The checker CLI's authoritative success marker is status=PASS."""

    return bool(
        returncode == 0 and isinstance(payload, dict) and payload.get("status") == "PASS"
    )


def _q_only_execution_artifact_campaigns_valid(
    supplement: dict[str, Any],
    *,
    manifest_execution_sha256: str | None,
    v23_window: Path,
    v23_accounting: Path,
) -> bool:
    execution_sha256 = str(manifest_execution_sha256 or "")
    old_sha256 = supplement.get("old_scan_campaign_window_sha256")
    old_window_path = supplement.get("old_scan_campaign_window_path")
    old_accounting_path = supplement.get("old_scan_campaign_accounting_path")
    if execution_sha256 == TASK40_V24_CAMPAIGN_SHA256:
        return bool(
            supplement.get("execution_campaign_window_sha256")
            == TASK40_V24_CAMPAIGN_SHA256
            and old_sha256 == TASK40_V23_CAMPAIGN_SHA256
            and Path(str(old_window_path or "")).resolve() == v23_window
            and Path(str(old_accounting_path or "")).resolve() == v23_accounting
            and v23_window.is_file()
            and _sha256_file(v23_window) == TASK40_V23_CAMPAIGN_SHA256
            and v23_accounting.is_file()
            and _sha256_file(v23_accounting) == TASK40_V24_PARENT_LEDGER["sha256"]
        )
    if execution_sha256 == TASK40_V23_CAMPAIGN_SHA256:
        return bool(
            supplement.get("execution_campaign_window_sha256")
            in (None, TASK40_V23_CAMPAIGN_SHA256)
            and old_sha256 in (None, TASK40_V23_CAMPAIGN_SHA256)
            and old_window_path in (None, str(v23_window))
            and old_accounting_path in (None, str(v23_accounting))
        )
    return False


def _v24_bounded_sample_readback_checks(
    *, output_directory: Path, probe: dict[str, Any]
) -> dict[str, bool]:
    """Independently replay bounded V24 Bα, -Dx, and original-H actions."""
    import numpy as np

    sample = probe.get("v24_bounded_port_reuse_volume_sample")
    sample = sample if isinstance(sample, dict) else {}
    port = sample.get("port_reuse")
    port = port if isinstance(port, dict) else {}
    volume = sample.get("volume_census")
    volume = volume if isinstance(volume, dict) else {}
    regenerated_record = port.get("regenerated_apply")
    regenerated_record = regenerated_record if isinstance(regenerated_record, dict) else {}
    selected_h_action = port.get("selected_H_p_action")
    selected_h_action = selected_h_action if isinstance(selected_h_action, dict) else {}
    cache_release = port.get("cache_release")
    cache_release = cache_release if isinstance(cache_release, dict) else {}
    selection = sample.get("mode_selection")
    selection = selection if isinstance(selection, dict) else {}
    q0_anchor = sample.get("q0_anchor")
    q0_anchor = q0_anchor if isinstance(q0_anchor, dict) else {}
    resource_samples = sample.get("resource_samples")
    resource_samples = resource_samples if isinstance(resource_samples, list) else []
    cache_name = "v24_bounded_32_mode_B_D_H_cache.npz"
    replay_name = "v24_bounded_32_mode_provider_replay.npz"
    cache_path = output_directory / cache_name
    replay_path = output_directory / replay_name
    sample_path = output_directory / "v24_bounded_port_reuse_volume_sample.json"
    q0_checker_path = Path(str(q0_anchor.get("checker_path", ""))).resolve()
    q0_root = (ROOT / V24_ARTIFACT_ROOT).resolve()
    q0_checker_valid = False
    if q0_checker_path.is_relative_to(q0_root) and q0_checker_path.is_file():
        try:
            q0_checker = json.loads(q0_checker_path.read_text(encoding="utf-8"))
            q0_checker_valid = bool(
                _sha256_file(q0_checker_path) == q0_anchor.get("checker_sha256")
                and q0_checker.get("status") == "PARTIAL_RECEIPT_CHECKED"
                and q0_checker.get("checker_passed") is True
                and q0_checker.get("official_result") is False
                and q0_checker.get("full_pass") is False
                and isinstance(q0_checker.get("checks"), dict)
                and bool(q0_checker["checks"])
                and all(value is True for value in q0_checker["checks"].values())
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            q0_checker_valid = False
    selected_groups = selection.get("groups")
    expected_groups = {
        (side, q, polarization)
        for side in ("bottom", "top")
        for q in range(8)
        for polarization in ("s", "p")
    }
    actual_groups: set[tuple[str, int, str]] = set()
    selected_mode_indices: list[int] = []
    groups_valid = isinstance(selected_groups, list)
    if groups_valid:
        try:
            for group in selected_groups:
                actual_groups.add(
                    (
                        str(group["side"]),
                        int(group["global_q"]),
                        str(group["polarization"]),
                    )
                )
                selected_mode_indices.append(int(group["original_mode_index"]))
            groups_valid = (
                actual_groups == expected_groups
                and len(actual_groups) == 32
                and len(set(selected_mode_indices)) == 32
            )
        except (KeyError, TypeError, ValueError):
            groups_valid = False
    sample_file_valid = False
    if sample_path.is_file():
        try:
            sample_file_valid = json.loads(sample_path.read_text(encoding="utf-8")) == {
                key: value
                for key, value in sample.items()
                if key not in {"artifact_path", "artifact_sha256"}
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            sample_file_valid = False
    checks: dict[str, bool] = {
        "v24_sample_scope_is_bounded_and_nonofficial": (
            sample.get("status") == "PASS_V24_PORT_REUSE_C_AND_VOLUME_CENSUS"
            and sample.get("official_result") is False
            and sample.get("full_q_matrix") is False
            and sample.get("factor_created") is False
            and sample.get("ksp_created") is False
            and sample.get("pde_solved") is False
        ),
        "v24_mode_sample_has_32_actual_groups": (
            selection.get("selected_mode_count") == 32
            and groups_valid
        ),
        "v24_cache_and_replay_files_are_hash_bound": (
            port.get("cache_payload_path") == cache_name
            and port.get("replay_payload_path") == replay_name
            and cache_path.is_file()
            and replay_path.is_file()
            and port.get("cache_payload_sha256") == _sha256_file(cache_path)
            and port.get("replay_payload_sha256") == _sha256_file(replay_path)
        ),
        "v24_sample_json_is_hash_bound_to_probe": (
            sample_path.is_file()
            and sample.get("artifact_path") == sample_path.name
            and sample.get("artifact_sha256") == _sha256_file(sample_path)
            and sample_file_valid
        ),
        "v24_cache_identity_recomputed": False,
        "v24_actions_recomputed_from_raw_B_D_H": False,
        "v24_cold_warm_regenerate_lifecycle_is_recorded": False,
        "v24_volume_capacity_scope_not_overclaimed": (
            volume.get("full_volume_action_admitted") is False
            and "excludes global trace-constraint maps" in str(
                volume.get("full_volume_class_cache_estimate_scope", "")
            )
        ),
        "v24_q0_anchor_is_bound_and_not_rerun": (
            q0_anchor.get("status") == "PREVIOUS_PARTIAL_Q0_CHECKER_PASS_BOUND"
            and q0_anchor.get("rerun") is False
            and q0_checker_valid
        ),
    }
    if not (cache_path.is_file() and replay_path.is_file()):
        return checks

    def array_sha256(value: Any) -> str:
        array = np.ascontiguousarray(value)
        digest = hashlib.sha256()
        digest.update(repr((array.shape, str(array.dtype))).encode("ascii"))
        digest.update(memoryview(array).cast("B"))
        return digest.hexdigest()

    def relative_l2(candidate: np.ndarray, oracle: np.ndarray) -> float:
        denominator = float(np.linalg.norm(oracle))
        delta = float(np.linalg.norm(candidate - oracle))
        if denominator == 0.0:
            return 0.0 if delta == 0.0 else float("inf")
        return delta / denominator

    warm_records = port.get("warm_actions", [])
    warm_records = warm_records if isinstance(warm_records, list) else []
    action_records = [
        port.get("cold_apply"),
        *warm_records,
        port.get("regenerated_apply"),
    ]
    action_records = [record for record in action_records if isinstance(record, dict)]
    expected_action_ids = {
        "cold_apply", "warm_apply_1", "warm_apply_2", "regenerated_apply"
    }
    cache_digest = hashlib.sha256()
    raw_identity_valid = True
    replay_valid = len(action_records) == 4 and {
        str(record.get("action_id")) for record in action_records
    } == expected_action_ids
    action_hashes_valid = replay_valid
    action_limits_valid = replay_valid
    action_inputs_by_id: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    actions_by_id: dict[str, dict[str, Any]] = {}
    try:
        with np.load(cache_path, allow_pickle=False) as cache, np.load(
            replay_path, allow_pickle=False
        ) as replay:
            indices = np.asarray(cache["mode_indices"])
            mode_keys = json.loads(str(cache["mode_keys_json"].item()))
            active_rows = np.asarray(replay["active_original_rows"])
            selected_indices = port.get("selected_original_mode_indices")
            selected_groups = selection.get("groups")
            selected_keys = {
                int(group["original_mode_index"]): list(group["mode_key"])
                for group in selected_groups
                if isinstance(group, dict)
                and isinstance(group.get("original_mode_index"), int)
                and isinstance(group.get("mode_key"), list)
            } if isinstance(selected_groups, list) else {}
            raw_identity_valid = bool(
                indices.shape == (32,)
                and indices.dtype.kind in "iu"
                and (len(indices) < 2 or np.all(indices[1:] > indices[:-1]))
                and indices.tolist() == selected_indices
                and len(mode_keys) == 32
                and len(selected_keys) == 32
                and all(
                    selected_keys.get(int(index)) == mode_key
                    for index, mode_key in zip(indices, mode_keys, strict=True)
                )
                and active_rows.ndim == 1
                and active_rows.dtype.kind in "iu"
                and active_rows.dtype.kind != "b"
                and (len(active_rows) < 2 or np.all(active_rows[1:] > active_rows[:-1]))
                and array_sha256(active_rows)
                == sample.get("active_original_rows_sha256")
            )
            for mode_index in range(32):
                prefix = f"mode_{mode_index:02d}"
                b_rows = np.asarray(cache[f"{prefix}_B_rows"])
                b_values = np.asarray(cache[f"{prefix}_B_values"])
                d_rows = np.asarray(cache[f"{prefix}_D_rows"])
                d_values = np.asarray(cache[f"{prefix}_D_values"])
                h_value = np.asarray(cache[f"{prefix}_H_p"])
                mode_identity = json.dumps(
                    mode_keys[mode_index], ensure_ascii=False, separators=(",", ":")
                )
                cache_digest.update(mode_identity.encode())
                cache_digest.update(np.asarray(h_value, dtype="<f8").tobytes())
                for name, array in (
                    ("B_rows", b_rows),
                    ("B_values", b_values),
                    ("D_rows", d_rows),
                    ("D_values", d_values),
                ):
                    cache_digest.update(name.encode())
                    cache_digest.update(array.dtype.str.encode())
                    cache_digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
                    cache_digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
                raw_identity_valid = raw_identity_valid and bool(
                    b_rows.ndim == d_rows.ndim == b_values.ndim == d_values.ndim == 1
                    and b_rows.dtype.kind in "iu"
                    and d_rows.dtype.kind in "iu"
                    and b_values.dtype == np.dtype(np.complex128)
                    and d_values.dtype == np.dtype(np.complex128)
                    and len(b_rows) == len(b_values)
                    and len(d_rows) == len(d_values)
                    and len(h_value) == 1
                    and np.isfinite(b_values).all()
                    and np.isfinite(d_values).all()
                    and np.isfinite(h_value).all()
                    and float(h_value[0]) > 0.0
                    and (len(b_rows) < 2 or np.all(b_rows[1:] > b_rows[:-1]))
                    and (len(d_rows) < 2 or np.all(d_rows[1:] > d_rows[:-1]))
                )
            raw_identity_valid = raw_identity_valid and (
                cache_digest.hexdigest() == port.get("cache_sha256")
            )
            actions_by_id = {str(record["action_id"]): record for record in action_records}
            output_by_id: dict[str, np.ndarray] = {}
            for action_id in sorted(expected_action_ids):
                record = actions_by_id[action_id]
                alpha = np.asarray(replay[f"{action_id}_alpha"], dtype=np.complex128)
                trace = np.asarray(replay[f"{action_id}_active_trace"], dtype=np.complex128)
                output = np.asarray(replay[f"{action_id}_provider_output"], dtype=np.complex128)
                h_output = np.asarray(replay[f"{action_id}_H_p_alpha_output"], dtype=np.complex128)
                if (
                    alpha.shape != (32,)
                    or trace.shape != active_rows.shape
                    or output.shape != (len(active_rows) + 32,)
                    or h_output.shape != (32,)
                    or not np.any(alpha)
                    or not np.any(trace)
                ):
                    replay_valid = False
                    continue
                expected_b = np.zeros(len(active_rows), dtype=np.complex128)
                expected_minus_d = np.zeros(32, dtype=np.complex128)
                expected_h = np.empty(32, dtype=np.complex128)
                for mode_index in range(32):
                    prefix = f"mode_{mode_index:02d}"
                    b_rows = np.asarray(cache[f"{prefix}_B_rows"])
                    b_values = np.asarray(cache[f"{prefix}_B_values"], dtype=np.complex128)
                    d_rows = np.asarray(cache[f"{prefix}_D_rows"])
                    d_values = np.asarray(cache[f"{prefix}_D_values"], dtype=np.complex128)
                    b_positions = np.searchsorted(active_rows, b_rows)
                    d_positions = np.searchsorted(active_rows, d_rows)
                    b_found = b_positions < len(active_rows)
                    d_found = d_positions < len(active_rows)
                    if np.any(b_found):
                        loc = np.flatnonzero(b_found)
                        b_found[loc] = active_rows[b_positions[loc]] == b_rows[loc]
                    if np.any(d_found):
                        loc = np.flatnonzero(d_found)
                        d_found[loc] = active_rows[d_positions[loc]] == d_rows[loc]
                    if not np.all(b_found) or not np.all(d_found):
                        raw_identity_valid = False
                        continue
                    np.add.at(expected_b, b_positions, b_values * alpha[mode_index])
                    expected_minus_d[mode_index] = -np.dot(
                        d_values, trace[d_positions]
                    )
                    expected_h[mode_index] = (
                        complex(cache[f"{prefix}_H_p"][0]) * alpha[mode_index]
                    )
                b_relative = relative_l2(output[:len(active_rows)], expected_b)
                d_relative = relative_l2(output[len(active_rows):], expected_minus_d)
                h_relative = relative_l2(h_output, expected_h)
                expected_errors = {
                    "B_alpha": b_relative,
                    "minus_Dx": d_relative,
                    "H_p_alpha": h_relative,
                }
                recorded_errors = record.get("oracle_relative_errors", {})
                limits = record.get("relative_error_limits", {})
                action_limits_valid = action_limits_valid and all(
                    np.isfinite(expected_errors[name])
                    and expected_errors[name] <= float(limits.get(name, 0.0)) <= 1.0e-11
                    for name in expected_errors
                )
                action_hashes_valid = action_hashes_valid and (
                    array_sha256(alpha) == record.get("input_alpha_sha256")
                    and array_sha256(trace) == record.get("input_active_trace_sha256")
                    and array_sha256(output) == record.get("provider_output_sha256")
                    and array_sha256(h_output) == record.get("H_p_alpha_output_sha256")
                    and array_sha256(active_rows) == record.get("active_original_rows_sha256")
                    and all(
                        np.isclose(
                            float(recorded_errors.get(name, float("inf"))),
                            expected_errors[name],
                            rtol=1.0e-6,
                            atol=1.0e-14,
                        )
                        for name in expected_errors
                    )
                )
                replay_valid = replay_valid and bool(np.isfinite(output).all() and np.isfinite(h_output).all())
                action_inputs_by_id[action_id] = (alpha, trace)
                output_by_id[action_id] = output
            if "cold_apply" in output_by_id and "regenerated_apply" in output_by_id:
                regen_delta = relative_l2(output_by_id["regenerated_apply"], output_by_id["cold_apply"])
                action_limits_valid = action_limits_valid and regen_delta <= 1.0e-11
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raw_identity_valid = replay_valid = action_hashes_valid = action_limits_valid = False

    checks["v24_cache_identity_recomputed"] = bool(raw_identity_valid)
    checks["v24_actions_recomputed_from_raw_B_D_H"] = bool(
        replay_valid and action_hashes_valid and action_limits_valid
    )
    distinct_action_inputs = bool(
        len(action_inputs_by_id) == 4
        and set(actions_by_id) == expected_action_ids
        and len(
            {
                actions_by_id[action_id]["input_alpha_sha256"]
                for action_id in ("cold_apply", "warm_apply_1", "warm_apply_2")
            }
        ) == 3
        and len(
            {
                actions_by_id[action_id]["input_active_trace_sha256"]
                for action_id in ("cold_apply", "warm_apply_1", "warm_apply_2")
            }
        ) == 3
        and np.array_equal(
            action_inputs_by_id["cold_apply"][0],
            action_inputs_by_id["regenerated_apply"][0],
        )
        and np.array_equal(
            action_inputs_by_id["cold_apply"][1],
            action_inputs_by_id["regenerated_apply"][1],
        )
    )
    try:
        regeneration_error = float(
            regenerated_record.get("same_input_relative_error_vs_cold", float("inf"))
        )
        regeneration_error_limit = float(
            regenerated_record.get("relative_error_limit", 0.0)
        )
    except (TypeError, ValueError):
        regeneration_error, regeneration_error_limit = float("inf"), 0.0
    checks["v24_cold_warm_regenerate_lifecycle_is_recorded"] = bool(
        port.get("status") == "PASS_COLD_WARM_RELEASE_REGENERATE_APPLY"
        and port.get("functional_generation_count_cold") == 32
        and port.get("functional_generation_count_warm") == 0
        and port.get("functional_generation_count_regenerate") == 32
        and port.get("provider_cold_apply_sweep_count") == 1
        and port.get("provider_warm_apply_sweep_count") == 2
        and port.get("provider_total_sweep_count") == 3
        and port.get("provider_total_mode_entries_processed") == 96
        and distinct_action_inputs
        and port.get("cache_bytes", 0) > 0
        and port.get("cache_bytes", 0) <= port.get("cache_byte_limit", 0)
        and port.get("cache_sha256") == port.get("regenerated_cache_sha256")
        and port.get("cache_bytes") == port.get("regenerated_cache_bytes")
        and regeneration_error <= regeneration_error_limit <= 1.0e-11
        and selected_h_action.get("representation") == "diagonal_original_H"
        and selected_h_action.get("mode_count") == 32
        and selected_h_action.get("apply_count") == 4
        and selected_h_action.get("no_Hhat_materialized") is True
        and len(resource_samples) == 15
        and cache_release.get("status")
        == "PASS_ALL_ARRAY_BACKINGS_RELEASED_BEFORE_REGENERATE_AND_AFTER"
    )
    return checks


def _v24_real_edge_panel_readback_checks(
    *, output_directory: Path, probe: dict[str, Any]
) -> dict[str, bool]:
    """Independently replay the saved V24 edge row block and local witnesses."""
    import math

    import numpy as np
    from scipy import sparse

    checks = {
        "v24_real_edge_panel_json_and_payload_hashes": False,
        "v24_real_edge_panel_json_matches_probe_receipt": False,
        "v24_real_edge_panel_48_by_all_active_columns": False,
        "v24_real_edge_panel_q_row_and_edge_self_recomputed": False,
        "v24_real_edge_panel_v17_csr_relative_oracles_recomputed": False,
        "v24_real_edge_panel_full_trace_and_incident_cell_inventory": False,
        "v24_real_edge_panel_cell_projection_maps_hash_bound": False,
        "v24_real_edge_panel_native_block_reaccumulated_from_cells": False,
        "v24_real_edge_panel_local_witness_blocks_independently_verified": False,
        "v24_real_edge_panel_local_witness_residuals_recomputed": False,
        "v24_real_edge_panel_q_scope_is_partial_and_explicit": False,
    }

    def array_sha256(value: Any) -> str:
        array = np.ascontiguousarray(value)
        digest = hashlib.sha256()
        digest.update(repr((array.shape, str(array.dtype))).encode("ascii"))
        digest.update(memoryview(array).cast("B"))
        return digest.hexdigest()

    def relative_error(actual: Any, expected: Any) -> tuple[float, float, float]:
        left = np.asarray(actual, dtype=np.complex128)
        right = np.asarray(expected, dtype=np.complex128)
        if left.shape != right.shape:
            return float("inf"), float("inf"), float(np.linalg.norm(right))
        error_norm = float(np.linalg.norm(left - right))
        oracle_norm = float(np.linalg.norm(right))
        if oracle_norm == 0.0:
            return (
                0.0 if error_norm == 0.0 else float("inf"),
                error_norm,
                oracle_norm,
            )
        return error_norm / oracle_norm, error_norm, oracle_norm

    def pass_metrics(
        A_ii: np.ndarray,
        A_it: np.ndarray,
        A_ti: np.ndarray,
        A_tt: np.ndarray,
        schur: np.ndarray,
        xi_true: np.ndarray,
        xt_true: np.ndarray,
        b_i: np.ndarray,
        b_t: np.ndarray,
        xi: np.ndarray,
        solve_b: np.ndarray,
    ) -> tuple[dict[str, float], np.ndarray]:
        interior_residual = A_ii @ xi + A_it @ xt_true - b_i
        trace_residual = A_ti @ xi + A_tt @ xt_true - b_t
        full_rhs_norm = float(np.hypot(np.linalg.norm(b_i), np.linalg.norm(b_t)))
        equation_relative = float(
            np.hypot(np.linalg.norm(interior_residual), np.linalg.norm(trace_residual))
            / max(full_rhs_norm, np.finfo(np.float64).tiny)
        )
        forward_relative = float(
            np.linalg.norm(xi - xi_true)
            / max(float(np.linalg.norm(xi_true)), np.finfo(np.float64).tiny)
        )
        rhs_condensed = b_t - A_ti @ solve_b
        condensed_relative = float(
            np.linalg.norm(schur @ xt_true - rhs_condensed)
            / max(float(np.linalg.norm(rhs_condensed)), np.finfo(np.float64).tiny)
        )
        return (
            {
                "equation": equation_relative,
                "forward": forward_relative,
                "condensed": condensed_relative,
            },
            rhs_condensed,
        )

    try:
        panel = probe.get("v24_real_edge_volume_panel")
        if not isinstance(panel, dict):
            return checks
        json_path = output_directory / "v24_real_edge_volume_panel.json"
        payload_path = output_directory / "v24_real_edge_volume_panel.npz"
        if not json_path.is_file() or not payload_path.is_file():
            return checks
        disk_panel = json.loads(json_path.read_text(encoding="utf-8"))
        payload_hash = _sha256_file(payload_path)
        partial_path = output_directory / "v20_partial_result.json"
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        artifact_records = partial.get("artifact_hashes", {})
        json_artifact = artifact_records.get(json_path.name, {})
        npz_artifact = artifact_records.get(payload_path.name, {})
        hashes = panel.get("payload_hashes", {})
        checks["v24_real_edge_panel_json_and_payload_hashes"] = bool(
            panel.get("status") == "PASS_V24_REAL_EDGE_ORBIT_Q_PANEL"
            and panel.get("payload_file") == payload_path.name
            and panel.get("payload_sha256") == payload_hash
            and hashes.get("payload_file_sha256") == payload_hash
            and json_artifact.get("sha256") == _sha256_file(json_path)
            and npz_artifact.get("sha256") == payload_hash
        )
        checks["v24_real_edge_panel_json_matches_probe_receipt"] = (
            disk_panel == panel
        )

        with np.load(payload_path, allow_pickle=False) as archive:
            payload = {name: archive[name] for name in archive.files}
        native = np.asarray(payload["native_panel"], dtype=np.complex128)
        canonical = np.asarray(payload["canonical_row_panel"], dtype=np.complex128)
        q_row_saved = np.asarray(payload["q_row_panel"], dtype=np.complex128)
        edge_native_saved = np.asarray(
            payload["edge_self_native_panel"], dtype=np.complex128
        )
        edge_canonical_saved = np.asarray(
            payload["edge_self_canonical_panel"], dtype=np.complex128
        )
        edge_q_saved = np.asarray(payload["edge_self_q_panel"], dtype=np.complex128)
        entity_map = np.asarray(payload["entity_map"], dtype=np.complex128)
        dft = np.asarray(payload["dft"], dtype=np.complex128)
        dft_edge = np.asarray(payload["dft_edge"], dtype=np.complex128)
        column_rows = np.asarray(payload["column_global_rows"], dtype=np.int64)
        for hash_name, array_name in (
            ("native_panel_sha256", "native_panel"),
            ("canonical_row_panel_sha256", "canonical_row_panel"),
            ("q_row_panel_sha256", "q_row_panel"),
            ("edge_self_q_panel_sha256", "edge_self_q_panel"),
            ("entity_map_sha256", "entity_map"),
            ("dft_sha256", "dft"),
            ("column_global_rows_sha256", "column_global_rows"),
        ):
            checks.setdefault("v24_real_edge_panel_array_hashes_recomputed", True)
            if hashes.get(hash_name) != array_sha256(payload[array_name]):
                checks["v24_real_edge_panel_array_hashes_recomputed"] = False
        witness_hashes = hashes.get(
            "local_equation_witness_payloads_sha256", {}
        )
        projection_hashes = hashes.get(
            "cell_mpc_projection_payloads_sha256", {}
        )
        if not isinstance(witness_hashes, dict) or any(
            name not in payload or witness_hashes.get(name) != array_sha256(payload[name])
            for name in witness_hashes
        ):
            checks["v24_real_edge_panel_array_hashes_recomputed"] = False
        checks["v24_real_edge_panel_cell_projection_maps_hash_bound"] = bool(
            isinstance(projection_hashes, dict)
            and bool(projection_hashes)
            and all(
                name in payload and digest == array_sha256(payload[name])
                for name, digest in projection_hashes.items()
            )
        )

        column_count = len(column_rows)
        checks["v24_real_edge_panel_48_by_all_active_columns"] = bool(
            native.shape == (48, column_count)
            and canonical.shape == (48, column_count)
            and q_row_saved.shape == (48, column_count)
            and column_count == panel.get("incident_cells", {}).get(
                "active_trace_column_count"
            )
            and len(np.unique(column_rows)) == column_count
            and np.all(np.diff(column_rows) > 0)
        )

        direct_canonical = entity_map.conjugate().T @ native
        direct_q_row = dft_edge.conjugate().T @ direct_canonical
        entity_canonical_error = relative_error(canonical, direct_canonical)[0]
        q_row_payload_error = relative_error(q_row_saved, direct_q_row)[0]
        selected = panel.get("selected_entity", {})
        orbit_rows = np.asarray(
            selected.get("global_rows_by_orbit", []), dtype=np.int64
        )
        expected_rows = orbit_rows.reshape(-1)
        edge_positions = np.searchsorted(column_rows, expected_rows)
        edge_positions_valid = bool(
            orbit_rows.shape == (8, 6)
            and len(np.unique(expected_rows)) == 48
            and np.all(edge_positions < column_count)
            and np.array_equal(column_rows[edge_positions], expected_rows)
        )
        edge_native = native[:, edge_positions] if edge_positions_valid else np.empty((48, 0))
        direct_edge_canonical = entity_map.conjugate().T @ edge_native
        direct_edge_q = dft_edge.conjugate().T @ direct_edge_canonical @ dft_edge
        edge_native_error = relative_error(edge_native_saved, edge_native)[0]
        edge_canonical_error = relative_error(edge_canonical_saved, direct_edge_canonical)[0]
        edge_q_error = relative_error(edge_q_saved, direct_edge_q)[0]

        q_row_csr = sparse.csr_matrix(
            (
                payload["q_row_csr_data"],
                payload["q_row_csr_indices"],
                payload["q_row_csr_indptr"],
            ),
            shape=(48, column_count),
        )
        q_edge_csr = sparse.csr_matrix(
            (
                payload["q_edge_csr_data"],
                payload["q_edge_csr_indices"],
                payload["q_edge_csr_indptr"],
            ),
            shape=(48, 48),
        )
        q_row_csr_error = relative_error(q_row_csr.toarray(), direct_q_row)[0]
        q_edge_csr_error = relative_error(q_edge_csr.toarray(), direct_edge_q)[0]
        v17 = panel.get("v17_row_tile_csr", {})
        checks["v24_real_edge_panel_q_row_and_edge_self_recomputed"] = bool(
            dft_edge.shape == (48, 48)
            and np.allclose(dft_edge, np.kron(dft, np.eye(6)), rtol=0.0, atol=0.0)
            and edge_positions_valid
            and max(
                entity_canonical_error,
                q_row_payload_error,
                edge_native_error,
                edge_canonical_error,
                edge_q_error,
            ) <= 1e-11
        )
        checks["v24_real_edge_panel_v17_csr_relative_oracles_recomputed"] = bool(
            v17.get("consumer") == "_assemble_bounded_v17_row_tile_q_patterns"
            and v17.get("index_dtype")
            == np.dtype(payload["q_row_csr_indices"].dtype).str
            and q_row_csr.shape == tuple(v17.get("q_row_native_column_block_shape", ()))
            and q_edge_csr.shape == tuple(v17.get("q_edge_self_block_shape", ()))
            and q_row_csr_error <= 1e-11
            and q_edge_csr_error <= 1e-11
            and float(v17.get("q_row_relative_frobenius_error", float("inf"))) <= 1e-11
            and float(
                v17.get("q_edge_self_relative_frobenius_error", float("inf"))
            ) <= 1e-11
            and v17.get("relative_error_limit") == 1e-11
            and int(v17.get("q_row_native_column_block_nnz", -1)) == q_row_csr.nnz
            and int(v17.get("q_edge_self_block_nnz", -1)) == q_edge_csr.nnz
            and int(v17.get("staging_peak_bytes", -1)) >= 0
            and int(v17.get("support_route_spool_peak_file_bytes", -1)) >= 0
        )

        incident = panel.get("incident_cells", {})
        selected_edges = panel.get("selected_entity", {})
        checks["v24_real_edge_panel_full_trace_and_incident_cell_inventory"] = bool(
            incident.get("cell_dofs_per_cell") == 882
            and incident.get("interior_rows_per_cell") == 450
            and incident.get("trace_rows_per_cell") == 432
            and incident.get("complete_432_trace_rows_retained_before_projection") is True
            and incident.get("complete_active_trace_columns_accumulated") is True
            and incident.get("all_incident_cells_included_exactly_once") is True
            and len(selected_edges.get("global_edge_ids_by_orbit", [])) == 8
            and len(selected_edges.get("global_rows_by_orbit", [])) == 8
            and all(len(rows) == 6 for rows in selected_edges.get("global_rows_by_orbit", []))
            and sum(incident.get("projected_cell_count_by_orbit", []))
            == incident.get("cell_count")
        )

        witness_audits = panel.get("local_equation_condense_recover_witnesses", {})
        witness_ok = bool(witness_audits) and set(witness_audits) == set(
            panel.get("local_lu", {}).get("oriented_classes", {})
        )
        witness_residuals_ok = witness_ok
        for class_key, audit in witness_audits.items():
            prefix = str(audit.get("payload_prefix", ""))
            names = {
                name: f"{prefix}_{name}"
                for name in (
                    "A_ii",
                    "A_it",
                    "A_ti",
                    "A_tt",
                    "schur",
                    "x_i_true",
                    "x_t_true",
                    "b_i",
                    "b_t",
                    "x_i_recovered_initial",
                    "solve_b_initial",
                    "x_i_recovered",
                    "solve_b_selected",
                    "rhs_condensed",
                )
            }
            if any(name not in payload for name in names.values()):
                witness_ok = False
                witness_residuals_ok = False
                continue
            A_ii, A_it, A_ti, A_tt = (
                np.asarray(payload[names[name]], dtype=np.complex128)
                for name in ("A_ii", "A_it", "A_ti", "A_tt")
            )
            schur = np.asarray(payload[names["schur"]], dtype=np.complex128)
            xi_true = np.asarray(payload[names["x_i_true"]], dtype=np.complex128)
            xt_true = np.asarray(payload[names["x_t_true"]], dtype=np.complex128)
            b_i = np.asarray(payload[names["b_i"]], dtype=np.complex128)
            b_t = np.asarray(payload[names["b_t"]], dtype=np.complex128)
            xi_initial = np.asarray(
                payload[names["x_i_recovered_initial"]], dtype=np.complex128
            )
            solve_b_initial = np.asarray(
                payload[names["solve_b_initial"]], dtype=np.complex128
            )
            xi_final = np.asarray(payload[names["x_i_recovered"]], dtype=np.complex128)
            solve_b_final = np.asarray(
                payload[names["solve_b_selected"]], dtype=np.complex128
            )
            rhs_condensed_saved = np.asarray(
                payload[names["rhs_condensed"]], dtype=np.complex128
            )
            expected_shapes = (
                A_ii.shape == (450, 450)
                and A_it.shape == (450, 432)
                and A_ti.shape == (432, 450)
                and A_tt.shape == (432, 432)
                and schur.shape == (432, 432)
                and xi_true.shape == (450,)
                and xt_true.shape == (432,)
                and b_i.shape == (450,)
                and b_t.shape == (432,)
            )
            arrays = (
                A_ii,
                A_it,
                A_ti,
                A_tt,
                schur,
                xi_true,
                xt_true,
                b_i,
                b_t,
                xi_initial,
                solve_b_initial,
                xi_final,
                solve_b_final,
                rhs_condensed_saved,
            )
            witness_ok = witness_ok and expected_shapes and all(
                np.isfinite(array).all() for array in arrays
            )
            initial_metrics, _ = pass_metrics(
                A_ii,
                A_it,
                A_ti,
                A_tt,
                schur,
                xi_true,
                xt_true,
                b_i,
                b_t,
                xi_initial,
                solve_b_initial,
            )
            final_metrics, rhs_condensed_recomputed = pass_metrics(
                A_ii,
                A_it,
                A_ti,
                A_tt,
                schur,
                xi_true,
                xt_true,
                b_i,
                b_t,
                xi_final,
                solve_b_final,
            )
            rhs_condensed_error = relative_error(
                rhs_condensed_saved, rhs_condensed_recomputed
            )[0]
            corrections = int(audit.get("refinement_correction_count", -1))
            history = audit.get("refinement_history", [])
            current_lu = panel.get("local_lu", {}).get("oriented_classes", {}).get(
                class_key, {}
            )
            witness_ok = witness_ok and bool(
                audit.get("status") == "PASS_LOCAL_EQUATION_CONDENSE_RECOVER_WITNESS"
                and float(np.linalg.norm(b_i)) > 0.0
                and corrections <= 3
                and len(history) == corrections + 1
                and int(current_lu.get("fresh_factorizations", 0)) == 1
                and int(current_lu.get("iterative_refinement_corrections", -1))
                == corrections
                and int(current_lu.get("maximum_iterative_refinement_corrections_allowed", 0))
                == 3
                and float(audit.get("same_lu_fresh_factorizations", 0)) == 1.0
                and float(audit.get("same_lu_refinement_corrections", -1))
                == corrections
                and float(audit.get("same_lu_max_refinement_corrections", 0)) == 3.0
                and (not bool(audit.get("initial_state_passed")) or corrections == 0)
                and bool(audit.get("initial_state_passed"))
                == (
                    initial_metrics["equation"] <= 1e-10
                    and initial_metrics["forward"] <= 1e-11
                    and initial_metrics["condensed"] <= 1e-10
                )
            )
            witness_residuals_ok = witness_residuals_ok and bool(
                final_metrics["equation"] <= 1e-10
                and final_metrics["forward"] <= 1e-11
                and final_metrics["condensed"] <= 1e-10
                and rhs_condensed_error <= 1e-11
                and float(audit.get("full_equation_residual_relative", float("inf")))
                <= 1e-10
                and float(
                    audit.get("recovered_interior_forward_relative", float("inf"))
                )
                <= 1e-11
                and float(
                    audit.get("condensed_trace_residual_relative", float("inf"))
                )
                <= 1e-10
            )
            for correction in range(1, corrections + 1):
                state = f"refinement_{correction:03d}"
                if (
                    f"{prefix}_{state}_x_i_recovered" not in payload
                    or f"{prefix}_{state}_solve_b" not in payload
                ):
                    witness_ok = False
                    witness_residuals_ok = False
            if corrections:
                last_state = f"refinement_{corrections:03d}"
                witness_ok = witness_ok and np.array_equal(
                    payload[f"{prefix}_{last_state}_x_i_recovered"], xi_final
                ) and np.array_equal(
                    payload[f"{prefix}_{last_state}_solve_b"], solve_b_final
                )
            if not math.isfinite(final_metrics["equation"]):
                witness_residuals_ok = False

        cell_records = panel.get("cell_mpc_projection_records", [])
        reconstructed_panel = np.zeros_like(native)
        seen_cell_ids: set[int] = set()
        active_global_union: set[int] = set()
        orbit_counts = [0] * 8
        cell_reaccumulation_ok = bool(
            isinstance(cell_records, list)
            and len(cell_records) == panel.get("incident_cells", {}).get("cell_count")
        )
        expected_orbit_rows = np.asarray(
            panel.get("selected_entity", {}).get("global_rows_by_orbit", []),
            dtype=np.int64,
        )
        expected_cells_by_orbit = panel.get("incident_cells", {}).get(
            "cells_by_orbit", {}
        )
        for record in cell_records if isinstance(cell_records, list) else []:
            try:
                cell_id = int(record["cell_id"])
                orbit = int(record["orbit_index"])
                class_key = str(record["oriented_class_key"])
                prefix = str(
                    witness_audits[class_key]["payload_prefix"]
                )
                schur_key = str(record["schur_payload_key"])
                trace_rows = np.asarray(
                    payload[record["trace_global_rows_payload_key"]],
                    dtype=np.int64,
                )
                active_rows = np.asarray(
                    payload[record["active_global_rows_payload_key"]],
                    dtype=np.int64,
                )
                expansion_data = np.asarray(
                    payload[record["expansion_data_payload_key"]],
                    dtype=np.complex128,
                )
                expansion_indices = np.asarray(
                    payload[record["expansion_indices_payload_key"]]
                )
                expansion_indptr = np.asarray(
                    payload[record["expansion_indptr_payload_key"]]
                )
                expansion_shape = tuple(record["expansion_shape"])
                expansion = sparse.csr_matrix(
                    (expansion_data, expansion_indices, expansion_indptr),
                    shape=expansion_shape,
                )
                selected_edge_rows = np.asarray(
                    record["selected_edge_global_rows"], dtype=np.int64
                )
                selected_columns = np.asarray(
                    record["selected_edge_expansion_columns"], dtype=np.int64
                )
                panel_row_positions = np.asarray(
                    record["panel_row_positions"], dtype=np.int64
                )
                panel_column_positions = np.asarray(
                    record["panel_column_positions"], dtype=np.int64
                )
                expected_active_positions = np.searchsorted(
                    active_rows, selected_edge_rows
                )
                expected_column_positions = np.searchsorted(
                    column_rows, active_rows
                )
                expected_row_positions = orbit * 6 + np.arange(6)
                expected_schur_key = f"{prefix}_schur"
                expected_cells = expected_cells_by_orbit.get(str(orbit), [])
                schur = np.asarray(payload[schur_key], dtype=np.complex128)
                trace_and_map_valid = bool(
                    0 <= orbit < 8
                    and trace_rows.shape == (432,)
                    and len(np.unique(trace_rows)) == 432
                    and active_rows.ndim == 1
                    and len(active_rows) > 0
                    and len(np.unique(active_rows)) == len(active_rows)
                    and np.all(np.diff(active_rows) > 0)
                    and expansion.shape == (432, len(active_rows))
                    and expansion.nnz == int(record["expansion_nnz"])
                    and np.array_equal(expansion.indptr, expansion_indptr)
                    and np.all(np.diff(expansion.indptr) >= 1)
                    and np.isfinite(expansion.data).all()
                    and np.all(expansion.indices >= 0)
                    and np.all(expansion.indices < len(active_rows))
                    and selected_edge_rows.shape == (6,)
                    and expected_orbit_rows.shape == (8, 6)
                    and np.array_equal(
                        selected_edge_rows, expected_orbit_rows[orbit]
                    )
                    and np.array_equal(selected_columns, expected_active_positions)
                    and np.all(selected_columns < len(active_rows))
                    and np.array_equal(panel_row_positions, expected_row_positions)
                    and np.array_equal(
                        panel_column_positions, expected_column_positions
                    )
                    and np.all(panel_column_positions < column_count)
                    and schur_key == expected_schur_key
                    and schur.shape == (432, 432)
                    and cell_id not in seen_cell_ids
                    and cell_id in set(map(int, expected_cells))
                )
                cell_reaccumulation_ok = cell_reaccumulation_ok and trace_and_map_valid
                if not trace_and_map_valid:
                    continue
                expansion_dense = expansion.toarray()
                selected_expansion = expansion_dense[:, selected_columns]
                projected = selected_expansion.conjugate().T @ schur @ expansion_dense
                if projected.shape != (6, len(active_rows)):
                    cell_reaccumulation_ok = False
                    continue
                reconstructed_panel[np.ix_(panel_row_positions, panel_column_positions)] += (
                    projected
                )
                seen_cell_ids.add(cell_id)
                active_global_union.update(map(int, active_rows))
                orbit_counts[orbit] += 1
            except (KeyError, TypeError, ValueError, IndexError, OverflowError):
                cell_reaccumulation_ok = False
        reconstructed_relative_error = relative_error(
            reconstructed_panel, native
        )[0]
        cell_reaccumulation_ok = bool(
            cell_reaccumulation_ok
            and len(seen_cell_ids) == len(cell_records)
            and active_global_union == set(map(int, column_rows))
            and orbit_counts
            == panel.get("incident_cells", {}).get("projected_cell_count_by_orbit")
            and reconstructed_relative_error <= 1e-11
        )
        checks["v24_real_edge_panel_native_block_reaccumulated_from_cells"] = (
            cell_reaccumulation_ok
        )

        checks["v24_real_edge_panel_local_witness_blocks_independently_verified"] = bool(
            witness_ok
            and panel.get("local_lu", {}).get(
                "maximum_fresh_factorizations_per_class"
            ) == 1
            and panel.get("local_lu", {}).get(
                "maximum_iterative_refinement_corrections_per_class", 4
            ) <= 3
        )
        checks["v24_real_edge_panel_local_witness_residuals_recomputed"] = bool(
            witness_residuals_ok
        )
        q_coverage = probe.get("q_coverage", {})
        checks["v24_real_edge_panel_q_scope_is_partial_and_explicit"] = bool(
            panel.get("full_q_matrix") is False
            and panel.get("full_volume_action") is False
            and panel.get("pde_solved") is False
            and q_coverage.get("built_q_count") == 0
            and q_coverage.get("full_q_matrix_coverage") == "0/8"
            and q_coverage.get("volume_qualification")
            == "PARTIAL_REAL_EDGE_ORBIT_Q_PANEL"
            and "non-edge q-column projection not run"
            in str(q_coverage.get("reason", ""))
            and panel.get("q_projection", {}).get("full_q_column_projection")
            == "NOT_RUN_FOR_NON_EDGE_COLUMNS"
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError, ArithmeticError):
        return checks
    return checks


def _v25_operation_status_matches_case_evidence(
    *, status: str, witnesses: list[Any], recovery_identity_valid: bool = False
) -> bool:
    statuses = [
        row.get("status") if isinstance(row, Mapping) else None for row in witnesses
    ]
    if status == "PASS_COMPLETE_TARGET_VOLUME_ACTION":
        return len(statuses) == 2 and all(value == "PASS" for value in statuses)
    if status == "FAILED_COMPLETE_TARGET_VOLUME_ACTION":
        return any(value == "FAILED_NUMERICAL_GATE" for value in statuses)
    if status == "RECOVERED_SAVED_WITNESS_PASS":
        return (
            recovery_identity_valid
            and len(statuses) == 2
            and all(value == "PASS" for value in statuses)
        )
    return False


def _v25_complete_volume_readback_checks(
    *, output_directory: Path, probe: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, bool]:
    """Verify V25 witness files and recompute every reported numerical gate."""
    import numpy as np
    identity = probe.get("v25_complete_target_volume_action")
    identity = identity if isinstance(identity, Mapping) else {}
    campaign = manifest.get("task40_v20_campaign")
    campaign = campaign if isinstance(campaign, Mapping) else {}
    operation_path = output_directory / "v25_complete_target_volume_action.json"
    if not operation_path.is_file():
        return {"v25_complete_volume_operation_file_present": False}
    operation = json.loads(operation_path.read_text(encoding="utf-8"))
    recovery_identity = operation.get("saved_witness_recovery")
    recovery_identity = recovery_identity if isinstance(recovery_identity, Mapping) else {}
    is_recovery = operation.get("status") == "RECOVERED_SAVED_WITNESS_PASS"
    recovery_original_directory = Path(
        str(recovery_identity.get("original_output_directory", ""))
    ).resolve()
    original_partial_path = recovery_original_directory / "v20_partial_result.json"
    partial_copy_path = output_directory / "v20_partial_result.json"
    original_partial: Mapping[str, Any] = {}
    if is_recovery and partial_copy_path.is_file():
        try:
            loaded_partial = json.loads(partial_copy_path.read_text(encoding="utf-8"))
            original_partial = loaded_partial if isinstance(loaded_partial, Mapping) else {}
        except (OSError, json.JSONDecodeError):
            original_partial = {}
    partial_sha256 = (
        _sha256_file(partial_copy_path) if partial_copy_path.is_file() else None
    )
    try:
        partial_is_original_hardlink = (
            partial_copy_path.is_file()
            and original_partial_path.is_file()
            and partial_copy_path.samefile(original_partial_path)
        )
    except OSError:
        partial_is_original_hardlink = False
    recovery_source_sha = str(recovery_identity.get("recovery_source_sha", ""))
    recovery_diff_sha = str(recovery_identity.get("recovery_source_diff_sha256", ""))
    recovery_identity_valid = bool(
        is_recovery
        and recovery_identity.get("schema")
        == "task40extra.review_v25_saved_witness_recovery.v1"
        and recovery_identity.get("recovery_kind") == "saved_raw_postprocess_only"
        and recovery_identity.get("original_run_id") == manifest.get("run_id")
        and recovery_identity.get("original_source_sha") == manifest.get("source_sha")
        and recovery_identity.get("original_source_sha") == operation.get("source_sha")
        and len(recovery_source_sha) == 40
        and all(char in "0123456789abcdef" for char in recovery_source_sha)
        and len(recovery_diff_sha) == 64
        and all(char in "0123456789abcdef" for char in recovery_diff_sha)
        and recovery_identity.get("original_worker_classification") == "WORKER_FAILED"
        and recovery_identity.get("original_worker_failure_type") == "TypeError"
        and "mappingproxy"
        in str(recovery_identity.get("original_worker_failure_message", ""))
        and recovery_identity.get("original_worker_completion_claimed_pass") is False
        and recovery_identity.get("fe_rerun") is False
        and recovery_identity.get("original_partial_sha256") == partial_sha256
        and partial_is_original_hardlink
        and original_partial.get("status") == "failed"
        and original_partial.get("classification") == "TARGET_OPERATOR_PROBE_FAILED"
        and original_partial.get("failure_type") == "TypeError"
        and "mappingproxy" in str(original_partial.get("failure_message", ""))
        and original_partial.get("official_result") is False
        and recovery_original_directory != output_directory.resolve()
    )
    hardlink_checks: list[bool] = []
    checks: dict[str, bool] = {
        "v25_operation_path_and_hash_match_probe": (
            identity.get("path") == operation_path.name
            and identity.get("sha256") == _sha256_file(operation_path)
        ),
        "v25_operation_identity_matches_run": (
            operation.get("run_id") == manifest.get("run_id")
            and operation.get("source_sha") == manifest.get("source_sha")
            and operation.get("input_sha256") == manifest.get("input_sha256")
            and operation.get("physical_model_sha256") == manifest.get("physical_model_sha256")
            and operation.get("campaign_window_sha256") == campaign.get("window_sha256")
        ),
        "v25_no_full_q_factor_ksp_or_pde": (
            operation.get("official_result") is False
            and operation.get("full_q_matrix") is False
            and operation.get("q_csr_created") is False
            and operation.get("factor_created") is False
            and operation.get("ksp_created") is False
            and operation.get("pde_solved") is False
            and operation.get("official_R_T_A_created") is False
        ),
    }
    witnesses = operation.get("witnesses")
    if operation.get("status") != "PASS_COMPLETE_TARGET_VOLUME_ACTION" and not witnesses:
        raw_facts = operation.get("partial_raw_evidence", [])
        raw_ok = isinstance(raw_facts, list)
        for fact in raw_facts if isinstance(raw_facts, list) else []:
            if not isinstance(fact, Mapping):
                raw_ok = False
                continue
            path = (output_directory / str(fact.get("path", ""))).resolve()
            raw_ok = bool(
                raw_ok
                and path.parent == output_directory.resolve()
                and path.is_file()
                and path.stat().st_size == fact.get("bytes")
                and _sha256_file(path) == fact.get("sha256")
            )
        checks["v25_failure_cause_and_partial_raw_evidence_preserved"] = bool(
            operation.get("status") == "FAILED_COMPLETE_TARGET_VOLUME_ACTION"
            and isinstance(operation.get("failure_type"), str)
            and isinstance(operation.get("failure_message"), str)
            and raw_ok
        )
        return checks

    target = operation.get("target_model", {})
    target = target if isinstance(target, Mapping) else {}
    checks["v25_exact_complete_target_inventory"] = (
        target.get("cell_count") == 30_464
        and target.get("p6_local_cell_dofs") == 882
        and target.get("full_storage_rows") == 20_181_348
        and target.get("independent_rows") == 19_897_344
        and target.get("trace_rows") == 6_472_548
        and target.get("active_trace_rows") == 6_188_544
        and target.get("mpc_slave_rows") == 284_004
        and operation.get("condensation", {}).get("global_matrix_materialized") is False
    )
    if not isinstance(witnesses, list) or len(witnesses) != 2:
        checks["v25_two_complete_witnesses"] = False
        return checks
    checks["v25_two_complete_witnesses"] = True
    cases_valid: list[bool] = []
    for case, witness in enumerate(witnesses):
        if not isinstance(witness, Mapping):
            cases_valid.append(False)
            continue
        manifest_name = witness.get("case_manifest_path")
        case_path = (output_directory / str(manifest_name or "")).resolve()
        case_is_hardlink = True
        if is_recovery:
            try:
                case_is_hardlink = (
                    (recovery_original_directory / case_path.name).is_file()
                    and case_path.samefile(recovery_original_directory / case_path.name)
                )
            except OSError:
                case_is_hardlink = False
            hardlink_checks.append(case_is_hardlink)
        case_ok = bool(
            case_path.parent == output_directory.resolve()
            and case_path.is_file()
            and _sha256_file(case_path) == witness.get("case_manifest_sha256")
            and case_is_hardlink
        )
        case_doc = (
            json.loads(case_path.read_text(encoding="utf-8")) if case_ok else {}
        )
        records = case_doc.get("raw_arrays", []) if isinstance(case_doc, Mapping) else []
        arrays: dict[str, Any] = {}
        if not isinstance(records, list):
            case_ok = False
            records = []

        def array_hash(value: Any) -> str:
            array = np.ascontiguousarray(np.asarray(value))
            digest = hashlib.sha256()
            digest.update(repr((array.shape, str(array.dtype))).encode("ascii"))
            digest.update(memoryview(array).cast("B"))
            return digest.hexdigest()

        for record in records:
            if not isinstance(record, Mapping):
                case_ok = False
                continue
            raw_path = (output_directory / str(record.get("path", ""))).resolve()
            raw_is_hardlink = True
            if is_recovery:
                try:
                    original_raw_path = recovery_original_directory / raw_path.name
                    raw_is_hardlink = (
                        original_raw_path.is_file()
                        and raw_path.samefile(original_raw_path)
                    )
                except OSError:
                    raw_is_hardlink = False
                hardlink_checks.append(raw_is_hardlink)
            if (
                raw_path.parent != output_directory.resolve()
                or not raw_path.is_file()
                or raw_path.stat().st_size != record.get("bytes")
                or _sha256_file(raw_path) != record.get("file_sha256")
                or not raw_is_hardlink
            ):
                case_ok = False
                continue
            try:
                array = np.load(raw_path, mmap_mode="r", allow_pickle=False)
            except (OSError, ValueError):
                case_ok = False
                continue
            label = raw_path.stem.removeprefix(f"v25_volume_case_{case}_")
            if (
                list(array.shape) != record.get("shape")
                or str(array.dtype) != record.get("dtype")
                or array_hash(array) != record.get("array_sha256")
                or record.get("readback_verified") is not True
            ):
                case_ok = False
            arrays[label] = array
        expected_arrays = {
            "trace_input", "storage_state", "native_rhs", "reduced_rhs",
            "reduced_action", "recovered_storage", "native_recovered_action",
            "native_residual", "slave_global_rows",
            "internal_state_nonzero_counts_by_cell",
            "internal_rhs_nonzero_counts_by_cell", "internal_rhs_norms_by_cell",
        }
        case_ok = case_ok and set(arrays) == expected_arrays
        try:
            trace = arrays["trace_input"]
            state = arrays["storage_state"]
            rhs = arrays["native_rhs"]
            reduced_rhs = arrays["reduced_rhs"]
            reduced_action = arrays["reduced_action"]
            recovered = arrays["recovered_storage"]
            native_applied = arrays["native_recovered_action"]
            residual = arrays["native_residual"]
            slaves = np.asarray(arrays["slave_global_rows"], dtype=np.int64)
            state_cell_counts = np.asarray(
                arrays["internal_state_nonzero_counts_by_cell"], dtype=np.int64
            )
            rhs_cell_counts = np.asarray(
                arrays["internal_rhs_nonzero_counts_by_cell"], dtype=np.int64
            )
            rhs_cell_norms = np.asarray(arrays["internal_rhs_norms_by_cell"], dtype=np.float64)
            cell_coverage = (
                state_cell_counts.shape == (30_464,)
                and rhs_cell_counts.shape == (30_464,)
                and rhs_cell_norms.shape == (30_464,)
                and int(np.count_nonzero(state_cell_counts))
                == witness.get("nonzero_internal_cell_count")
                and int(np.count_nonzero(rhs_cell_counts))
                == witness.get("native_rhs_nonzero_internal_cell_count")
                and array_hash(state_cell_counts)
                == witness.get("internal_state_nonzero_counts_by_cell_sha256")
                and array_hash(rhs_cell_counts)
                == witness.get("native_rhs_nonzero_counts_by_cell_sha256")
                and array_hash(rhs_cell_norms)
                == witness.get("native_rhs_norms_by_cell_sha256")
            )
            if case == 1:
                cell_coverage = bool(
                    cell_coverage
                    and np.all(state_cell_counts > 0)
                    and np.all(rhs_cell_counts > 0)
                    and np.all(rhs_cell_norms > 0.0)
                )
            slave_zero = bool(
                slaves.ndim == 1
                and len(slaves) == 284_004
                and (not len(slaves) or np.all(slaves[1:] > slaves[:-1]))
                and (not len(slaves)
                     or (np.all(state[slaves] == 0.0)
                         and np.all(rhs[slaves] == 0.0)
                         and np.all(recovered[slaves] == 0.0)))
            )

            def norm_chunks(value: Any) -> float:
                total = 0.0
                flat = np.asarray(value).reshape(-1)
                for start in range(0, len(flat), 1_000_000):
                    part = flat[start : start + 1_000_000]
                    total += float(np.vdot(part, part).real)
                return float(np.sqrt(total))

            def finite_chunks(value: Any) -> bool:
                flat = np.asarray(value).reshape(-1)
                return all(
                    bool(np.all(np.isfinite(flat[start : start + 1_000_000])))
                    for start in range(0, len(flat), 1_000_000)
                )

            def difference_relative(left: Any, right: Any) -> float:
                error_square = 0.0
                reference_square = 0.0
                lhs = np.asarray(left).reshape(-1)
                rhs_value = np.asarray(right).reshape(-1)
                if lhs.shape != rhs_value.shape:
                    return float("inf")
                for start in range(0, len(lhs), 1_000_000):
                    stop = min(start + 1_000_000, len(lhs))
                    difference = lhs[start:stop] - rhs_value[start:stop]
                    error_square += float(np.vdot(difference, difference).real)
                    reference = rhs_value[start:stop]
                    reference_square += float(np.vdot(reference, reference).real)
                reference_norm = float(np.sqrt(reference_square))
                return float(np.sqrt(error_square)) / reference_norm if reference_norm else float("inf")

            action_relative = difference_relative(reduced_action, reduced_rhs)
            forward_relative = difference_relative(recovered, state)
            native_rhs_norm = norm_chunks(rhs)
            native_relative = norm_chunks(residual) / native_rhs_norm if native_rhs_norm else float("inf")
            numerical_pass = bool(
                action_relative <= 1.0e-10
                and native_relative <= 1.0e-10
                and forward_relative <= 1.0e-11
                and witness.get("native_packed_coefficients_within_bound") is True
                and (case != 1 or cell_coverage)
            )
            expected_case_status = "PASS" if numerical_pass else "FAILED_NUMERICAL_GATE"
            residual_equal = True
            for start in range(0, len(rhs), 1_000_000):
                stop = min(start + 1_000_000, len(rhs))
                if not np.array_equal(
                    rhs[start:stop] - native_applied[start:stop], residual[start:stop]
                ):
                    residual_equal = False
                    break
            case_ok = bool(
                case_ok
                and case_doc.get("case") == case
                and case_doc.get("status") == expected_case_status
                and witness.get("status") == expected_case_status
                and trace.shape == (6_188_544,)
                and state.shape == rhs.shape == recovered.shape == native_applied.shape == residual.shape == (20_181_348,)
                and reduced_rhs.shape == reduced_action.shape == trace.shape
                and finite_chunks(trace)
                and finite_chunks(state)
                and finite_chunks(rhs)
                and finite_chunks(recovered)
                and finite_chunks(residual)
                and np.count_nonzero(trace) == 6_188_544
                and array_hash(trace) == witness.get("active_trace_input_sha256")
                and array_hash(state) == witness.get("full_storage_input_sha256")
                and array_hash(rhs) == witness.get("native_rhs_sha256")
                and case_doc.get("raw_arrays") == witness.get("raw_arrays")
                and slaves.shape == (284_004,)
                and (not len(slaves) or (int(slaves.min()) >= 0 and int(slaves.max()) < 20_181_348))
                and array_hash(np.asarray(slaves, dtype="<i8"))
                == target.get("mpc_slave_rows_sha256")
                and cell_coverage
                and slave_zero
                and residual_equal
                and ((action_relative <= 1.0e-10) == (case_doc.get("status") == "PASS"))
                and ((native_relative <= 1.0e-10) or (case_doc.get("status") == "FAILED_NUMERICAL_GATE"))
                and ((forward_relative <= 1.0e-11) or (case_doc.get("status") == "FAILED_NUMERICAL_GATE"))
                and np.isclose(action_relative, witness.get("condensed_action_rhs_relative_error"), rtol=1e-12, atol=1e-15)
                and np.isclose(native_relative, witness.get("native_volume_residual_relative"), rtol=1e-12, atol=1e-15)
                and np.isclose(forward_relative, witness.get("recovery_forward_relative_error"), rtol=1e-12, atol=1e-15)
                and np.isclose(native_rhs_norm, witness.get("native_rhs_norm"), rtol=1e-12, atol=1e-15)
                and np.isclose(norm_chunks(residual), witness.get("native_volume_residual_norm"), rtol=1e-12, atol=1e-15)
            )
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            case_ok = False
        finally:
            for array in arrays.values():
                mmap = getattr(array, "_mmap", None)
                if mmap is not None:
                    mmap.close()
        cases_valid.append(bool(case_ok))
    checks["v25_raw_array_hashes_and_readback_verified"] = all(cases_valid)
    checks["v25_action_residual_and_forward_gates_recomputed"] = all(cases_valid)
    checks["v25_second_case_covers_every_cell_state_and_native_rhs"] = (
        bool(witnesses[1].get("all_cell_internal_nonzero_witness"))
        and bool(witnesses[1].get("all_cell_internal_native_rhs_witness"))
        and cases_valid[1]
    )
    if is_recovery:
        checks["v25_recovery_identity_and_original_failure_preserved"] = (
            recovery_identity_valid
        )
        checks["v25_recovery_raw_case_manifests_and_arrays_are_hardlinked"] = (
            len(hardlink_checks) == 26 and all(hardlink_checks)
        )
    checks["v25_operation_status_matches_case_evidence"] = (
        _v25_operation_status_matches_case_evidence(
            status=str(operation.get("status", "")),
            witnesses=witnesses,
            recovery_identity_valid=(
                recovery_identity_valid
                and len(hardlink_checks) == 26
                and all(hardlink_checks)
            ),
        )
    )
    return checks



def _v25_selected_q0_readback_checks(
    *, output_directory: Path, partial: Mapping[str, Any]
) -> dict[str, bool]:
    """Recompute selected-q errors from saved vectors and verify their identities."""
    import math
    import numpy as np
    import zipfile

    root = output_directory.resolve()
    nested = partial.get("selected_reference_q0_consumer", {})
    nested = nested if isinstance(nested, Mapping) else {}
    operation_path = (root / "v25_selected_q0_consumer.json").resolve()
    try:
        operation = json.loads(operation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        operation = {}
    status = str(operation.get("status", ""))
    checks: dict[str, bool] = {
        "q0_operation_identity_and_status_hash": (
            operation_path.is_relative_to(root)
            and operation_path.is_file()
            and nested.get("operation_path") == operation_path.name
            and nested.get("operation_sha256") == _sha256_file(operation_path)
            and nested.get("operation_status") == status
            and operation.get("schema") == "task40extra.review_v25_selected_reference_q0_consumer.v1"
            and operation.get("selected_q") == 0
            and operation.get("paired_q") == 4
            and operation.get("official_result") is False
        ),
        "q0_no_factor_ksp_pde_or_official_result": (
            operation.get("factor_or_solve_built") is not True
            and operation.get("ksp_created") is not True
            and operation.get("pde_solved") is not True
            and partial.get("official_result") is False
        ),
    }
    try:
        preflight = json.loads((root / "v20_stage_preflight.json").read_text(encoding="utf-8"))
        preflight_modes = preflight.get("target_mode_inventory", {})
        preflight_modes = preflight_modes if isinstance(preflight_modes, Mapping) else {}
    except (OSError, json.JSONDecodeError):
        preflight_modes = {}
    inventory = operation.get("mode_inventory", {})
    inventory = inventory if isinstance(inventory, Mapping) else {}
    identity_valid = (
        operation.get("preflight_mode_manifest_sha256", inventory.get("mode_manifest_sha256"))
        == preflight_modes.get("mode_manifest_sha256")
        and operation.get("ordered_mode_key_sha256", inventory.get("ordered_mode_key_sha256"))
        == preflight_modes.get("ordered_mode_key_sha256")
    )
    if status in {
        "PASS_COMPLETE_Q0_STREAM",
        "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT",
        "PASS_COMPLETE_Q0_CSR",
        "PARTIAL_REFERENCE_NONZERO_INTERNAL_DTN_SUPPORT",
    }:
        identity_valid = identity_valid and (
            type(inventory.get("q0_alias_count_actual")) is int
            and inventory["q0_alias_count_actual"] > 0
            and type(inventory.get("q4_alias_count_actual")) is int
            and inventory["q4_alias_count_actual"] > 0
            and inventory.get("selected_twist_alias_count_actual")
            == inventory.get("q0_alias_count_actual", -1)
            + inventory.get("q4_alias_count_actual", -1)
        )
    checks["q0_frozen_preflight_mode_identity"] = bool(
        (root / "v20_stage_preflight.json").is_file() and identity_valid
    )

    saved = operation.get("saved_artifacts", {})
    saved = saved if isinstance(saved, Mapping) else {}
    artifacts_valid = bool(saved)
    for item in saved.values():
        if not isinstance(item, Mapping):
            artifacts_valid = False
            break
        artifact = (root / str(item.get("path", ""))).resolve()
        if (
            not artifact.is_relative_to(root)
            or not artifact.is_file()
            or type(item.get("bytes")) is not int
            or artifact.stat().st_size != item.get("bytes")
            or not isinstance(item.get("sha256"), str)
            or _sha256_file(artifact) != item.get("sha256")
        ):
            artifacts_valid = False
            break

    def vector_metrics(archive: Any, left_key: str, right_key: str) -> dict[str, float]:
        left = np.asarray(archive[left_key], dtype=np.complex128).reshape(-1)
        right = np.asarray(archive[right_key], dtype=np.complex128).reshape(-1)
        if left.shape != right.shape:
            raise ValueError(f"raw replay vectors have different shapes: {left_key}, {right_key}")
        difference_sq = left_sq = right_sq = 0.0
        step = 1_000_000
        for start in range(0, left.size, step):
            stop = min(start + step, left.size)
            a, b = left[start:stop], right[start:stop]
            if not np.isfinite(a).all() or not np.isfinite(b).all():
                raise ValueError("raw replay vector contains non-finite values")
            difference_sq += float(np.vdot(a - b, a - b).real)
            left_sq += float(np.vdot(a, a).real)
            right_sq += float(np.vdot(b, b).real)
        absolute = math.sqrt(max(difference_sq, 0.0))
        scale = max(math.sqrt(max(left_sq, 0.0)), math.sqrt(max(right_sq, 0.0)), np.finfo(float).tiny)
        return {"absolute": absolute, "relative_to_component": absolute / scale}

    def vector_norm(archive: Any, key: str) -> float:
        values = np.asarray(archive[key], dtype=np.complex128).reshape(-1)
        total = 0.0
        for start in range(0, values.size, 1_000_000):
            chunk = values[start : start + 1_000_000]
            if not np.isfinite(chunk).all():
                raise ValueError(f"raw replay vector is non-finite: {key}")
            total += float(np.vdot(chunk, chunk).real)
        return math.sqrt(max(total, 0.0))

    def metrics_match(recorded: Any, calculated: Mapping[str, float]) -> bool:
        if not isinstance(recorded, Mapping):
            return False
        try:
            absolute = float(recorded["absolute"])
            relative = float(recorded["relative_to_component"])
            return (
                math.isfinite(absolute)
                and math.isfinite(relative)
                and math.isclose(
                    absolute,
                    calculated["absolute"],
                    rel_tol=1.0e-6,
                    abs_tol=1.0e-14,
                )
                and math.isclose(
                    relative,
                    calculated["relative_to_component"],
                    rel_tol=1.0e-6,
                    abs_tol=1.0e-14,
                )
                and relative <= 1.0e-11
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return False

    pass_statuses = {
        "PASS_COMPLETE_Q0_STREAM",
        "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT",
        "PASS_COMPLETE_Q0_CSR",
    }
    if status in pass_statuses:
        stream = operation.get("complete_stream", {})
        stream = stream if isinstance(stream, Mapping) else {}
        replay = stream.get("consumer_replay", {})
        replay = replay if isinstance(replay, Mapping) else {}
        replay_facts = replay.get("replay_artifact", {})
        replay_facts = replay_facts if isinstance(replay_facts, Mapping) else {}
        replay_path = (root / str(replay_facts.get("path", ""))).resolve()
        if (
            replay_path.is_relative_to(root)
            and replay_path.is_file()
            and replay_facts.get("sha256") == _sha256_file(replay_path)
            and saved.get("complete_consumer_replay", {}).get("sha256") == replay_facts.get("sha256")
        ):
            try:
                recomputed: dict[str, dict[str, float]] = {}
                with np.load(replay_path, allow_pickle=False) as archive:
                    required = {
                        "input_q0_case_1", "input_q0_case_2", "input_q4_pair",
                        "stream_q0_output_case_1", "stream_q0_output_case_2",
                        "native_q0_output_case_1", "native_q0_output_case_2",
                        "stream_q4_output_from_q0_case_1", "native_q4_output_from_q0_case_1",
                        "stream_q0_output_from_q4", "native_q0_output_from_q4",
                        "stream_q4_output_case_pair", "native_q4_output_case_pair",
                        "component_volume_stream", "component_volume_native",
                        "component_C_stream", "component_C_native",
                        "component_minus_D_stream", "component_minus_D_native",
                        "component_Hhat_stream", "component_Hhat_native",
                    }
                    if not required.issubset(set(archive.files)):
                        raise ValueError("complete q0 replay archive is missing required raw vectors")
                    if any(vector_norm(archive, key) == 0.0 for key in ("input_q0_case_1", "input_q0_case_2", "input_q4_pair")):
                        raise ValueError("q0/q4 replay inputs must all be nonzero")
                    q0_input_distinct = bool(
                        np.asarray(archive["input_q0_case_1"]).shape != np.asarray(archive["input_q0_case_2"]).shape
                        or not np.array_equal(archive["input_q0_case_1"], archive["input_q0_case_2"])
                    )
                    if not q0_input_distinct:
                        raise ValueError("the two q0 replay inputs are not distinct")
                    pairs = {
                        "q0_case_1": ("stream_q0_output_case_1", "native_q0_output_case_1"),
                        "q0_case_2": ("stream_q0_output_case_2", "native_q0_output_case_2"),
                        "q0_to_q4": ("stream_q4_output_from_q0_case_1", "native_q4_output_from_q0_case_1"),
                        "q4_to_q0": ("stream_q0_output_from_q4", "native_q0_output_from_q4"),
                        "q4_case": ("stream_q4_output_case_pair", "native_q4_output_case_pair"),
                        "volume": ("component_volume_stream", "component_volume_native"),
                        "C": ("component_C_stream", "component_C_native"),
                        "-D": ("component_minus_D_stream", "component_minus_D_native"),
                        "Hhat": ("component_Hhat_stream", "component_Hhat_native"),
                    }
                    for name, (left, right) in pairs.items():
                        recomputed[name] = vector_metrics(archive, left, right)
                    leakage_04 = vector_norm(archive, "stream_q4_output_from_q0_case_1") / max(
                        vector_norm(archive, "stream_q0_output_case_1"), np.finfo(float).tiny
                    )
                    leakage_40 = vector_norm(archive, "stream_q0_output_from_q4") / max(
                        vector_norm(archive, "stream_q4_output_case_pair"), np.finfo(float).tiny
                    )
                reported_q0 = replay.get("q0_replay_relative_errors", [])
                reported_components = replay.get("q0_component_relative_errors", {})
                reported_components = reported_components if isinstance(reported_components, Mapping) else {}
                checks["q0_raw_stream_and_native_errors_recomputed"] = (
                    len(reported_q0) == 2
                    and metrics_match(reported_q0[0], recomputed["q0_case_1"])
                    and metrics_match(reported_q0[1], recomputed["q0_case_2"])
                    and set(reported_components) == {"volume", "C", "-D", "Hhat"}
                    and all(metrics_match(reported_components[name], recomputed[name]) for name in reported_components)
                    and all(metrics_match(replay.get(key), recomputed[name]) for name, key in (
                        ("q0_to_q4", "q0_to_q4_relative_error"),
                        ("q4_to_q0", "q4_to_q0_relative_error"),
                        ("q4_case", "q4_to_q4_relative_error"),
                    ))
                    and math.isclose(float(replay.get("q0_to_q4_leakage_ratio", math.inf)), leakage_04, rel_tol=1.0e-6, abs_tol=1.0e-14)
                    and math.isclose(float(replay.get("q4_to_q0_leakage_ratio", math.inf)), leakage_40, rel_tol=1.0e-6, abs_tol=1.0e-14)
                    and leakage_04 <= 1.0e-11
                    and leakage_40 <= 1.0e-11
                )
                pre_gate = operation.get("pre_fe_resource_gate", {})
                checks["q0_pre_fe_memory_cgroup_and_swap_admission"] = bool(
                    isinstance(pre_gate, Mapping)
                    and pre_gate.get("task_cgroup_gate_passed") is True
                    and pre_gate.get("swap_gate_status") == "PASS_ZERO_TASK_CGROUP_SWAP"
                    and pre_gate.get("explicit_process_tree_cap_bytes") == 16 * 1024**3
                    and pre_gate.get("disk_gate_passed") is True
                )
                direct = operation.get("direct_only_support", {})
                direct = direct if isinstance(direct, Mapping) else {}
                hp = operation.get("original_H_p", {})
                hp = hp if isinstance(hp, Mapping) else {}
                checks["q0_internal_support_and_Hp_identity_gates"] = bool(
                    direct.get("passed") is True
                    and direct.get("internal_B_nonzero_count") == 0
                    and direct.get("internal_D_nonzero_count", direct.get("internal_minus_D_nonzero_count")) == 0
                    and float(hp.get("local_global_scaling_error", {}).get("relative_to_component", math.inf)) <= 1.0e-12
                    and float(hp.get("q0_normalized_H_p_identity_max_abs", math.inf)) <= 1.0e-12
                    and hp.get("q0_q4_H_p_alias_overlap") == 0
                )
            except (OSError, ValueError, TypeError, KeyError, OverflowError, zipfile.BadZipFile):
                checks["q0_raw_stream_and_native_errors_recomputed"] = False
        else:
            checks["q0_raw_stream_and_native_errors_recomputed"] = False
        checks["q0_saved_artifact_hash_readback"] = artifacts_valid
        q0_pass = bool(checks.get("q0_raw_stream_and_native_errors_recomputed"))
        checks["q0_stage_status_matches_recomputed_consumer"] = (
            q0_pass
            and partial.get("status") == "stage_completed"
            and partial.get("outcome") == "STAGE_COMPLETED"
            and partial.get("q_coverage", {}).get("built_q_count")
            == (1 if status == "PASS_COMPLETE_Q0_CSR" else 0)
        )
        if status == "PASS_COMPLETE_Q0_CSR":
            tiles = operation.get("row_tile_store", {})
            tiles = tiles if isinstance(tiles, Mapping) else {}
            csr_replay = operation.get("replay", {})
            csr_replay = csr_replay if isinstance(csr_replay, Mapping) else {}
            csr_path = (root / "v25_selected_q0_replay.npz").resolve()
            try:
                with np.load(csr_path, allow_pickle=False) as archive:
                    csr_errors = (
                        vector_metrics(archive, "q0_replay_output_case_1", "native_q0_output_case_1"),
                        vector_metrics(archive, "q0_replay_output_case_2", "native_q0_output_case_2"),
                    )
                csr_values_valid = all(item["relative_to_component"] <= 1.0e-11 for item in csr_errors)
            except (OSError, ValueError, TypeError, KeyError, OverflowError, zipfile.BadZipFile):
                csr_values_valid = False
            checks["q0_complete_disk_csr_readback_recomputed"] = bool(
                csr_values_valid
                and csr_path.is_file()
                and _sha256_file(csr_path) == csr_replay.get("csr_replay_file_sha256")
                and tiles.get("complete_row_domain") is True
                and tiles.get("complete_column_domain") is True
                and tiles.get("row_count") == tiles.get("shape", [None])[0]
                and operation.get("solve_ready") is False
            )
        else:
            checks["q0_csr_not_built_is_explicit"] = (
                partial.get("q_coverage", {}).get("csr_status") == "NOT_BUILT"
            )
    elif status == "PARTIAL_REFERENCE_NONZERO_INTERNAL_DTN_SUPPORT":
        raw = operation.get("raw_surface_stream", {})
        raw = raw if isinstance(raw, Mapping) else {}
        raw_path = (root / str(raw.get("path", ""))).resolve()
        counts = raw.get("internal_nonzero_entry_count", {})
        counts = counts if isinstance(counts, Mapping) else {}
        artifacts_valid = bool(
            raw_path.is_relative_to(root)
            and raw_path.is_file()
            and raw.get("sha256") == _sha256_file(raw_path)
        )
        checks["q0_saved_artifact_hash_readback"] = artifacts_valid
        checks["q0_nonzero_internal_support_preserved"] = bool(
            partial.get("status") == "failed"
            and (counts.get("B", 0) > 0 or counts.get("D", 0) > 0)
            and "no values were dropped or zeroed" in str(operation.get("reason", ""))
        )
    elif status == "RESOURCE_CONTROLLED_STOP":
        blocker = operation.get("resource_blocker", {})
        blocker = blocker if isinstance(blocker, Mapping) else {}
        checks["q0_resource_stop_before_fe"] = (
            partial.get("status") == "controlled_stop"
            and isinstance(operation.get("resource_blocker"), Mapping)
            and isinstance(blocker.get("stage"), str)
        )
        checks["q0_saved_artifact_hash_readback"] = not any(
            (root / name).exists()
            for name in (
                "v25_selected_q0_surface_functionals.bin",
                "v25_selected_q0_complete_stream.json",
            )
        )
    else:
        checks["q0_failure_is_retained"] = (
            partial.get("status") == "failed"
            and isinstance(operation.get("failure_type"), str)
        )
        checks["q0_saved_artifact_hash_readback"] = artifacts_valid
    return checks


def _v26_array_sha256(array: Any) -> str:
    import numpy as np

    value = np.asarray(array)
    return hashlib.sha256(memoryview(value).cast("B")).hexdigest()


def _v26_native_case_recovery_readback(
    *,
    repo_root: Path,
    native_root: Path,
    replay_root: Path,
    prior_attempt_root: Path,
    recovery_identity: Mapping[str, Any],
    expected_run_id: str,
    expected_input_sha256: str,
    expected_physical_model_sha256: str,
) -> dict[str, Any]:
    """Independently qualify the one complete three-case V26 KeyError recovery."""
    import math
    import numpy as np
    import zipfile

    root = repo_root.resolve()
    artifact_root = (root / V26_ARTIFACT_ROOT).resolve()
    native_root = native_root.resolve()
    replay_root = replay_root.resolve()
    prior_attempt_root = prior_attempt_root.resolve()
    if native_root != (artifact_root / "native_consumer").resolve():
        raise ValueError("V26 recovery native root differs from the registered artifact root")
    if replay_root != (artifact_root / "saved_replay").resolve():
        raise ValueError("V26 recovery replay root differs from the registered artifact root")
    if not prior_attempt_root.is_relative_to((root / "results").resolve()):
        raise ValueError("V26 recovery failure attempt is outside results/")

    def read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"V26 recovery JSON is not an object: {path.name}")
        return value

    freeze_path = artifact_root / "main_source_freeze_receipt_v26_reader_fix.json"
    freeze = read_json(freeze_path)
    old_source_sha = str(freeze.get("source_sha", ""))
    if (
        freeze.get("schema") != "task40extra.review_v26_main_source_freeze.v1"
        or freeze.get("worktree_clean_at_freeze") is not True
        or len(old_source_sha) != 40
        or recovery_identity.get("source_sha") == old_source_sha
        or len(str(recovery_identity.get("source_sha", ""))) != 40
        or recovery_identity.get("run_id") != expected_run_id
        or recovery_identity.get("physical_model_sha256") != expected_physical_model_sha256
    ):
        raise ValueError("V26 recovery source split is not bound to the clean original native freeze")

    failed_manifest_path = prior_attempt_root / "run_manifest.json"
    failed_summary_path = prior_attempt_root / "run_summary.json"
    failed_operation_path = prior_attempt_root / "v26_selected_q_stage.json"
    failed_manifest = read_json(failed_manifest_path)
    failed_summary = read_json(failed_summary_path)
    failed_operation = read_json(failed_operation_path)
    failed_resource = failed_summary.get("resource_authority", {})
    if not isinstance(failed_resource, Mapping):
        failed_resource = {}
    if (
        failed_manifest.get("source_sha") != old_source_sha
        or failed_manifest.get("run_id") != expected_run_id
        or failed_manifest.get("input_sha256") != expected_input_sha256
        or failed_manifest.get("physical_model_sha256") != expected_physical_model_sha256
        or failed_summary.get("status") != "finished"
        or failed_summary.get("result_classification") != "WORKER_FAILED"
        or failed_summary.get("exit_status") != 4
        or failed_resource.get("classification") != "WORKER_FAILED"
        or failed_operation.get("status") != "FAILED_V26_SELECTED_Q_GATES"
        or failed_operation.get("failure_type") != "KeyError"
        or failed_operation.get("failure_message") != "'minus_D'"
        or failed_operation.get("official_result") is not False
        or failed_operation.get("resource_blocker") is not None
        or failed_operation.get("stop_stage") != "selected_reference_q_csr"
    ):
        raise ValueError("V26 recovery prior attempt is not the exact non-resource minus_D leaf failure")
    if (native_root / "v26_native_action_manifest.json").exists():
        raise FileExistsError("V26 recovery refuses to replace an existing native action manifest")

    def identity_without_source(identity: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in identity.items() if key != "source_sha"}

    recovery_identity = dict(recovery_identity)
    shared_identity = identity_without_source(recovery_identity)
    identity_keys = (
        "run_id", "physical_model_sha256", "campaign_window_sha256",
        "producer_identity_sha256", "mode_manifest_sha256", "ordered_mode_key_sha256",
    )
    selector_path = artifact_root / "stage_inputs/selected_reference_q_csr/selected_operation.json"
    selector = read_json(selector_path)
    producer_identity = selector.get("producer_identity", {})
    if not isinstance(producer_identity, Mapping):
        raise ValueError("V26 recovery selector omits the producer identity")
    producer_sha = hashlib.sha256(
        json.dumps(producer_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    replay_path = replay_root / "v26_saved_q_replay_manifest.json"
    replay = read_json(replay_path)
    replay_sha = _sha256_file(replay_path)
    replay_identity = replay.get("current_identity", {})
    if not isinstance(replay_identity, Mapping):
        replay_identity = {}
    if (
        selector.get("schema") != "task40extra.review_v26_selected_operation.v1"
        or selector.get("operation") != "V26_COMPLETE_Q0_CSR_AND_CONDITIONAL_FACTOR"
        or selector.get("stop_stage") != "selected_reference_q_csr"
        or selector.get("input_sha256") != expected_input_sha256
        or not isinstance(selector.get("producer_identity"), Mapping)
        or replay.get("schema") != "task40extra.review_v26_saved_q_replay.v1"
        or replay.get("status") != "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        or replay.get("producer_identity") != producer_identity
        or replay.get("producer_identity_sha256") != producer_sha
        or replay.get("official_result") is not False
        or replay.get("csr_built") is not False
        or replay.get("factor_or_solve_built") is not False
        or any(replay_identity.get(key) != recovery_identity.get(key) for key in identity_keys)
        or replay.get("ordered_mode_key_sha256") != recovery_identity.get("ordered_mode_key_sha256")
        or replay.get("mode_count_full_reference") != 32_060
        or replay.get("q0_alias_count") != 4_076
        or replay.get("q4_alias_count") != 3_856
        or replay.get("selected_twist_alias_count") != 7_932
    ):
        raise ValueError("V26 recovery saved replay identity or scope is not compatible")

    def load_archive(
        path: Path,
        *,
        expected_bytes: Any,
        expected_sha: Any,
        array_hashes: Mapping[str, Any],
        array_shapes: Mapping[str, Any],
    ) -> dict[str, np.ndarray]:
        if (
            not path.is_relative_to(native_root if path.is_relative_to(native_root) else replay_root)
            or not path.is_file()
            or type(expected_bytes) is not int
            or path.stat().st_size != expected_bytes
            or _sha256_file(path) != expected_sha
        ):
            raise ValueError(f"V26 recovery archive identity failed: {path.name}")
        arrays: dict[str, np.ndarray] = {}
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != set(array_hashes) or (
                array_shapes and set(archive.files) != set(array_shapes)
            ):
                raise ValueError(f"V26 recovery array inventory differs: {path.name}")
            for name in archive.files:
                value = np.asarray(archive[name]).copy()
                if (
                    value.ndim != 1
                    or value.dtype != np.dtype(np.complex128)
                    or (array_shapes and list(value.shape) != array_shapes.get(name))
                    or not np.isfinite(value).all()
                    or _v26_array_sha256(value) != array_hashes.get(name)
                ):
                    raise ValueError(f"V26 recovery array failed raw hash/shape validation: {path.name}/{name}")
                arrays[name] = value
        return arrays

    artifacts = replay.get("artifacts", {})
    input_item = artifacts.get("inputs", {}) if isinstance(artifacts, Mapping) else {}
    input_path = (replay_root / str(input_item.get("path", ""))).resolve()
    input_sidecar = read_json(replay_root / "v26_saved_q_replay_inputs.json")
    if (
        input_sidecar.get("sha256") != input_item.get("sha256")
        or input_sidecar.get("array_sha256") != input_item.get("array_sha256")
        or input_sidecar.get("producer_identity_sha256") != producer_sha
    ):
        raise ValueError("V26 recovery saved input sidecar identity differs")
    inputs = load_archive(
        input_path,
        expected_bytes=input_item.get("bytes"),
        expected_sha=input_item.get("sha256"),
        array_hashes=input_item.get("array_sha256", {}),
        array_shapes=input_item.get("array_shapes", {}),
    )
    if (
        set(inputs) != {"q0_case_1", "q0_case_2", "q4_pair"}
        or any(not np.all(value != 0.0) for value in inputs.values())
        or np.array_equal(inputs["q0_case_1"], inputs["q0_case_2"])
    ):
        raise ValueError("V26 recovery saved replay inputs are not complete, nonzero, distinct witnesses")

    replay_cases: dict[str, dict[str, np.ndarray]] = {}
    replay_case_records = replay.get("cases", {})
    for case_name in ("q0_case_1", "q0_case_2", "q4_pair"):
        item = artifacts.get(case_name, {})
        record = replay_case_records.get(case_name, {})
        case_path = (replay_root / str(item.get("path", ""))).resolve()
        sidecar_path = (replay_root / str(item.get("manifest_path", ""))).resolve()
        sidecar = read_json(sidecar_path)
        if (
            not sidecar_path.is_relative_to(replay_root)
            or sidecar.get("sha256") != item.get("sha256")
            or sidecar.get("array_sha256") != record.get("array_sha256")
            or record.get("sha256") != item.get("sha256")
            or record.get("producer_identity_sha256") != producer_sha
        ):
            raise ValueError(f"V26 recovery saved replay case sidecar differs: {case_name}")
        replay_cases[case_name] = load_archive(
            case_path,
            expected_bytes=item.get("bytes"),
            expected_sha=item.get("sha256"),
            array_hashes=record.get("array_sha256", {}),
            array_shapes=record.get("array_shapes", {}),
        )

    native_cases: dict[str, dict[str, np.ndarray]] = {}
    native_records: dict[str, Any] = {}
    native_identity: dict[str, Any] | None = None
    for case_name in ("q0_case_1", "q0_case_2", "q4_pair"):
        case_path = native_root / f"v26_native_{case_name}.npz"
        sidecar_path = case_path.with_suffix(".json")
        sidecar = read_json(sidecar_path)
        current = sidecar.get("current_identity", {})
        if not isinstance(current, Mapping):
            raise ValueError(f"V26 recovery native case omits its original current identity: {case_name}")
        if native_identity is None:
            native_identity = dict(current)
        if (
            sidecar.get("schema") != "task40extra.review_v26_native_action_case.v1"
            or sidecar.get("case") != case_name
            or sidecar.get("path") != case_path.name
            or sidecar.get("producer_identity_sha256") != producer_sha
            or sidecar.get("saved_replay_manifest_sha256") != replay_sha
            or dict(current) != native_identity
            or current.get("source_sha") != old_source_sha
            or any(current.get(key) != shared_identity.get(key) for key in identity_keys)
        ):
            raise ValueError(f"V26 recovery native case identity differs: {case_name}")
        arrays = load_archive(
            case_path,
            expected_bytes=sidecar.get("bytes"),
            expected_sha=sidecar.get("sha256"),
            array_hashes=sidecar.get("array_sha256", {}),
            array_shapes=sidecar.get("array_shapes", {}),
        )
        native_cases[case_name] = arrays
        native_records[case_name] = sidecar
    if native_identity is None:
        raise ValueError("V26 recovery has no native case identities")

    def relative_error(actual: np.ndarray, expected: np.ndarray, scale: np.ndarray | None = None) -> dict[str, float]:
        if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
            raise ValueError("V26 recovery comparison arrays differ in shape or finiteness")
        absolute = float(np.linalg.norm(actual - expected))
        denominator = (
            float(np.linalg.norm(scale))
            if scale is not None
            else max(
                float(np.linalg.norm(actual)),
                float(np.linalg.norm(expected)),
                np.finfo(float).tiny,
            )
        )
        if not math.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("V26 recovery comparison scale is not finite and positive")
        return {"absolute": absolute, "scale": denominator, "relative_to_component": absolute / denominator}

    q0_1, q0_2, q4 = replay_cases["q0_case_1"], replay_cases["q0_case_2"], replay_cases["q4_pair"]
    n0_1, n0_2, n4 = native_cases["q0_case_1"], native_cases["q0_case_2"], native_cases["q4_pair"]
    comparisons = {
        "q0_case_1": relative_error(q0_1["q0_total"], n0_1["native_q0_total"]),
        "q0_case_2": relative_error(q0_2["q0_total"], n0_2["native_q0_total"]),
        "q4_pair": relative_error(q4["q4_total"], n4["native_q4_total"]),
        "volume": relative_error(q0_1["q0_volume"], n0_1["native_q0_volume"]),
        "C": relative_error(q0_1["q0_C"], n0_1["native_q0_C"]),
        "-D": relative_error(q0_1["q0_minus_D"], n0_1["native_q0_minus_D"]),
        "Hhat": relative_error(q0_1["q0_Hhat"], n0_1["native_q0_Hhat"]),
        "q0_to_q4_scaled": relative_error(
            q0_1["q4_total_from_q0"], n0_1["native_q4_from_q0"], n0_1["native_q0_total"]
        ),
        "q4_to_q0_scaled": relative_error(
            q4["q0_total_from_q4"], n4["native_q0_from_q4"], n4["native_q4_total"]
        ),
    }
    norm_q0 = float(np.linalg.norm(n0_1["native_q0_total"]))
    norm_q4 = float(np.linalg.norm(n4["native_q4_total"]))
    if not math.isfinite(norm_q0) or not math.isfinite(norm_q4) or min(norm_q0, norm_q4) <= 0.0:
        raise ValueError("V26 recovery native diagonal scales are not finite and positive")
    leakage = {
        "q0_to_q4": float(np.linalg.norm(q0_1["q4_total_from_q0"])) / norm_q0,
        "q4_to_q0": float(np.linalg.norm(q4["q0_total_from_q4"])) / norm_q4,
    }
    limit = 1.0e-11
    if (
        any(row["relative_to_component"] > limit for row in comparisons.values())
        or any(value > limit for value in leakage.values())
    ):
        raise ValueError("V26 recovery saved native cases fail the original 1e-11 comparison/leakage gates")

    return {
        "schema": "task40extra.review_v26_native_case_recovery_check.v1",
        "status": "PASS_READONLY_THREE_CASE_RECOVERY",
        "checker_passed": True,
        "official_result": False,
        "source_sha_split": {
            "native_evidence_source_sha": old_source_sha,
            "recovery_source_sha": str(recovery_identity.get("source_sha", "")),
            "shared_mathematical_identity_keys": list(identity_keys),
        },
        "original_native_current_identity": dict(native_identity),
        "recovery_current_identity": recovery_identity,
        "producer_identity_sha256": producer_sha,
        "saved_replay_manifest_path": str(replay_path),
        "saved_replay_manifest_sha256": replay_sha,
        "prior_failed_attempt": {
            "path": str(prior_attempt_root),
            "run_manifest_sha256": _sha256_file(failed_manifest_path),
            "run_summary_sha256": _sha256_file(failed_summary_path),
            "operation_sha256": _sha256_file(failed_operation_path),
            "status": "WORKER_FAILED",
            "failure_type": "KeyError",
            "failure_message": "'minus_D'",
        },
        "native_cases": native_records,
        "recomputed_comparisons": comparisons,
        "recomputed_scaled_leakage": leakage,
        "comparison_limit": limit,
        "fresh_surface_integration": "NOT_RUN; reused hash-bound producer surface functionals",
        "historical_native_counts": {
            "native_volume_apply_count": {
                "measured": None,
                "source_derived": 6,
                "classification": "SOURCE_DERIVED",
                "source_sha": old_source_sha,
            },
            "provider_sweep_count": {
                "measured": None,
                "source_derived": 9,
                "classification": "SOURCE_DERIVED",
                "source_sha": old_source_sha,
            },
            "native_action_elapsed_seconds": {
                "measured": None,
                "classification": "UNKNOWN_NOT_PERSISTED_BEFORE_KEYERROR",
            },
        },
    }


def _v26_selected_q_readback_checks(
    *, output_directory: Path, partial: Mapping[str, Any], expected_stop_stage: str
) -> dict[str, bool]:
    """Independently bind V26 saved arrays and recompute scaled native comparisons."""
    import math
    import numpy as np
    from scipy import sparse
    import zipfile

    root = output_directory.resolve()
    stage_receipt = partial.get("v26_selected_q_stage", {})
    stage_receipt = stage_receipt if isinstance(stage_receipt, Mapping) else {}
    operation_path = (root / "v26_selected_q_stage.json").resolve()
    try:
        operation = json.loads(operation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        operation = {}
    status = str(operation.get("status", ""))
    expected_operation = {
        "selected_reference_q_build_only": "V26_SAVED_STREAM_REPLAY",
        "selected_reference_q_consumer": "V26_SAVED_STREAM_NATIVE_CONSUMER",
        "selected_reference_q_csr": "V26_COMPLETE_Q0_CSR_AND_CONDITIONAL_FACTOR",
    }.get(expected_stop_stage)
    checks: dict[str, bool] = {
        "v26_stage_operation_identity_and_hash": bool(
            operation_path.is_relative_to(root)
            and operation_path.is_file()
            and stage_receipt.get("operation_path") == operation_path.name
            and stage_receipt.get("operation_sha256") == _sha256_file(operation_path)
            and stage_receipt.get("operation_status") == status
            and stage_receipt.get("selector_sha256") == operation.get("selector_sha256", operation.get("v26_selector_sha256"))
            and operation.get("official_result") is False
            and operation.get("stop_stage") == expected_stop_stage
        ),
        "v26_factor_scope_has_no_ksp_pde_or_official_result": bool(
            operation.get("ksp_created") is not True
            and operation.get("pde_solved") is not True
            and partial.get("official_result") is False
            and partial.get("q_coverage", {}).get("ksp_created") is False
            and partial.get("q_coverage", {}).get("pde_solved") is False
        ),
    }
    try:
        preflight = json.loads((root / "v20_stage_preflight.json").read_text(encoding="utf-8"))
        frozen_modes = preflight.get("target_mode_inventory", {})
        frozen_modes = frozen_modes if isinstance(frozen_modes, Mapping) else {}
    except (OSError, json.JSONDecodeError):
        frozen_modes = {}

    artifact_root = (ROOT / V26_ARTIFACT_ROOT).resolve()
    replay_root = Path(str(stage_receipt.get("saved_replay_root", ""))).resolve()
    native_root = Path(str(stage_receipt.get("native_root", ""))).resolve()
    selector_path = Path(str(stage_receipt.get("selector_path", ""))).resolve()
    selector_sha = str(stage_receipt.get("selector_sha256", ""))
    try:
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        selector = {}
    producer_identity = selector.get("producer_identity", {})
    producer_identity = producer_identity if isinstance(producer_identity, Mapping) else {}
    producer_identity_sha = hashlib.sha256(
        json.dumps(
            producer_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    selector_ok = bool(
        selector_path.is_relative_to(artifact_root)
        and selector_path.is_file()
        and _sha256_file(selector_path) == selector_sha
        and selector.get("schema") == "task40extra.review_v26_selected_operation.v1"
        and selector.get("operation") == expected_operation
        and selector.get("stop_stage") == expected_stop_stage
        and selector.get("input_sha256") == partial.get("input_sha256")
        and selector.get("model_profile") == partial.get("profile")
        and isinstance(producer_identity.get("payloads"), list)
        and producer_identity.get("failure_index_sha256") == V26_FAILURE_INDEX_SHA256
        and producer_identity.get("verified_input_sha256") == V26_VERIFIED_INPUT_SHA256
    )
    checks["v26_selector_and_producer_identity_bound"] = selector_ok
    checks["v26_preflight_inventory_is_complete"] = bool(
        (root / "v20_stage_preflight.json").is_file()
        and frozen_modes.get("mode_count") == 32_060
        and len(str(frozen_modes.get("mode_manifest_sha256", ""))) == 64
        and len(str(frozen_modes.get("ordered_mode_key_sha256", ""))) == 64
    )

    expected_replay_root = (artifact_root / "saved_replay").resolve()
    expected_native_root = (artifact_root / "native_consumer").resolve()
    replay_manifest_path = (replay_root / "v26_saved_q_replay_manifest.json").resolve()
    try:
        replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        replay_manifest = {}
    if (
        expected_stop_stage == "selected_reference_q_build_only"
        and not replay_manifest
        and status == "RESOURCE_CONTROLLED_STOP"
    ):
        blocker = operation.get("resource_blocker", {})
        blocker = blocker if isinstance(blocker, Mapping) else {}
        no_outputs = not any(replay_root.glob("v26_saved_q_replay_*.npz")) and not replay_manifest_path.exists()
        controlled_valid = bool(
            partial.get("status") == "controlled_stop"
            and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
            and isinstance(blocker.get("stage"), str)
            and blocker.get("passed") is False
            and replay_root == expected_replay_root
            and no_outputs
        )
        checks["v26_saved_replay_manifest_identity_and_inventory"] = controlled_valid
        checks["v26_saved_inputs_and_all_replay_arrays_hash_bound"] = controlled_valid
        checks["v26_saved_replay_completed_before_fe"] = controlled_valid
        checks["v26_replay_controlled_stop_has_no_science_outputs"] = controlled_valid
        return checks
    replay_sha = _sha256_file(replay_manifest_path) if replay_manifest_path.is_file() else ""
    operation_replay_sha = (
        operation.get("saved_replay_manifest_sha256")
        if expected_stop_stage == "selected_reference_q_build_only"
        else operation.get("v26_artifact_binding", {}).get("saved_replay_manifest_sha256")
        if isinstance(operation.get("v26_artifact_binding"), Mapping)
        else None
    )
    replay_identity_ok = bool(
        replay_root == expected_replay_root
        and replay_manifest_path.is_relative_to(expected_replay_root)
        and replay_manifest.get("schema") == "task40extra.review_v26_saved_q_replay.v1"
        and replay_manifest.get("status") == "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        and replay_manifest.get("producer_identity") == producer_identity
        and replay_manifest.get("producer_identity_sha256") == producer_identity_sha
        and operation_replay_sha == replay_sha
        and replay_manifest.get("preflight_mode_manifest_sha256") == frozen_modes.get("mode_manifest_sha256")
        and replay_manifest.get("ordered_mode_key_sha256") == frozen_modes.get("ordered_mode_key_sha256")
        and replay_manifest.get("mode_count_full_reference") == 32_060
        and replay_manifest.get("q0_alias_count") == 4_076
        and replay_manifest.get("q4_alias_count") == 3_856
        and replay_manifest.get("selected_twist_alias_count") == 7_932
        and replay_manifest.get("official_result") is False
        and replay_manifest.get("csr_built") is False
        and replay_manifest.get("factor_or_solve_built") is False
    )
    checks["v26_saved_replay_manifest_identity_and_inventory"] = replay_identity_ok

    arrays_by_case: dict[str, dict[str, np.ndarray]] = {}
    try:
        artifacts = replay_manifest.get("artifacts", {})
        input_item = artifacts.get("inputs", {})
        input_path = (replay_root / str(input_item.get("path", ""))).resolve()
        input_sidecar_path = replay_root / "v26_saved_q_replay_inputs.json"
        input_sidecar = json.loads(input_sidecar_path.read_text(encoding="utf-8"))
        replay_artifacts_ok = bool(
            input_path.is_relative_to(replay_root)
            and input_path.is_file()
            and type(input_item.get("bytes")) is int
            and input_path.stat().st_size == input_item.get("bytes")
            and _sha256_file(input_path) == input_item.get("sha256")
            and input_sidecar.get("sha256") == input_item.get("sha256")
            and input_sidecar.get("array_sha256") == input_item.get("array_sha256")
        )
        inputs: dict[str, np.ndarray] = {}
        with np.load(input_path, allow_pickle=False) as archive:
            required_inputs = {"q0_case_1", "q0_case_2", "q4_pair"}
            if set(archive.files) != required_inputs:
                raise ValueError("V26 input checkpoint case inventory differs")
            for name in required_inputs:
                value = np.asarray(archive[name]).copy()
                if (
                    value.ndim != 1
                    or value.dtype != np.dtype(np.complex128)
                    or not np.isfinite(value).all()
                    or not np.all(value != 0.0)
                    or _v26_array_sha256(value) != input_item.get("array_sha256", {}).get(name)
                ):
                    raise ValueError(f"V26 raw input array failed validation: {name}")
                inputs[name] = value
        if np.array_equal(inputs["q0_case_1"], inputs["q0_case_2"]):
            raise ValueError("V26 q0 replay input vectors are not distinct")
        for case_name in ("q0_case_1", "q0_case_2", "q4_pair"):
            item = artifacts.get(case_name, {})
            path = (replay_root / str(item.get("path", ""))).resolve()
            sidecar_path = (replay_root / str(item.get("manifest_path", ""))).resolve()
            case_doc = replay_manifest.get("cases", {}).get(case_name, {})
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            replay_artifacts_ok = replay_artifacts_ok and bool(
                path.is_relative_to(replay_root)
                and sidecar_path.is_relative_to(replay_root)
                and path.is_file()
                and sidecar_path.is_file()
                and type(item.get("bytes")) is int
                and path.stat().st_size == item.get("bytes")
                and _sha256_file(path) == item.get("sha256")
                and sidecar.get("sha256") == item.get("sha256")
                and case_doc.get("sha256") == item.get("sha256")
                and case_doc.get("producer_identity_sha256") == producer_identity_sha
            )
            loaded: dict[str, np.ndarray] = {}
            with np.load(path, allow_pickle=False) as archive:
                hashes = case_doc.get("array_sha256", {})
                shapes = case_doc.get("array_shapes", {})
                if set(archive.files) != set(hashes) or set(archive.files) != set(shapes):
                    raise ValueError(f"V26 replay case array inventory differs: {case_name}")
                for name in archive.files:
                    value = np.asarray(archive[name]).copy()
                    if (
                        value.ndim != 1
                        or value.dtype != np.dtype(np.complex128)
                        or list(value.shape) != shapes.get(name)
                        or not np.isfinite(value).all()
                        or _v26_array_sha256(value) != hashes.get(name)
                    ):
                        raise ValueError(f"V26 raw replay output failed validation: {case_name}/{name}")
                    loaded[name] = value
            arrays_by_case[case_name] = loaded
        checks["v26_saved_inputs_and_all_replay_arrays_hash_bound"] = bool(replay_artifacts_ok)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, zipfile.BadZipFile):
        inputs = {}
        arrays_by_case = {}
        checks["v26_saved_inputs_and_all_replay_arrays_hash_bound"] = False

    checks["v26_saved_replay_completed_before_fe"] = bool(
        replay_manifest.get("native_volume_apply_count") == 0
        and replay_manifest.get("provider_sweep_count") == 0
        and replay_manifest.get("inputs_saved_before_replay") is True
        and replay_manifest.get("each_case_output_saved_atomically_before_next_case") is True
        and replay_manifest.get("all_saved_inputs_nonzero") is True
        and replay_manifest.get("q0_inputs_distinct") is True
    )

    native_status = "NOT_RUN"
    if expected_stop_stage in {"selected_reference_q_consumer", "selected_reference_q_csr"}:
        binding = operation.get("v26_artifact_binding", {})
        binding = binding if isinstance(binding, Mapping) else {}
        native_manifest_path = Path(
            str(binding.get("native_manifest_path", native_root / "v26_native_action_manifest.json"))
        ).resolve()
        try:
            native_manifest = json.loads(native_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            native_manifest = {}
        native_recovery = operation.get("v26_native_recovery", {})
        native_recovery = native_recovery if isinstance(native_recovery, Mapping) else {}
        recovered_native = native_manifest.get("schema") == "task40extra.review_v26_native_action_recovery.v1"
        native_status = str(native_manifest.get("status", "MISSING"))
        if not native_manifest and status == "RESOURCE_CONTROLLED_STOP":
            blocker = operation.get("resource_blocker", {})
            blocker = blocker if isinstance(blocker, Mapping) else {}
            controlled_valid = bool(
                partial.get("status") == "controlled_stop"
                and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
                and isinstance(blocker.get("stage"), str)
                and blocker.get("passed") is False
                and partial.get("official_result") is False
            )
            checks["v26_native_not_started_under_explicit_resource_gate"] = controlled_valid
            checks["v26_native_stage_status_matches_raw_comparisons"] = controlled_valid
            return checks
        if (
            not native_manifest
            and status == "PARTIAL_REFERENCE_NONZERO_INTERNAL_DTN_SUPPORT"
        ):
            raw = operation.get("raw_surface_stream", {})
            raw = raw if isinstance(raw, Mapping) else {}
            producer_root = Path(str(stage_receipt.get("producer_root", ""))).resolve()
            surface_path = Path(str(raw.get("path", ""))).resolve()
            payload = next(
                (
                    item
                    for item in producer_identity.get("payloads", [])
                    if isinstance(item, Mapping)
                    and Path(str(item.get("path", ""))).name == surface_path.name
                ),
                {},
            )
            negative_valid = bool(
                partial.get("status") == "failed"
                and partial.get("outcome") == "STAGE_FAILED"
                and operation.get("classification") == "RAW_PRODUCTION_SUPPORT_PRESERVED; DIRECT_ONLY_Q0_NOT_QUALIFIED"
                and surface_path.is_relative_to(producer_root)
                and surface_path.is_file()
                and surface_path.stat().st_size == raw.get("bytes") == payload.get("bytes")
                and raw.get("sha256") == payload.get("sha256")
                and sum(raw.get("internal_nonzero_entry_count", {}).values()) > 0
                and not any(native_root.glob("v26_native_*.npz"))
            )
            checks["v26_native_not_started_after_preserved_support_negative"] = negative_valid
            checks["v26_native_stage_status_matches_raw_comparisons"] = negative_valid
            return checks
        native_sha = _sha256_file(native_manifest_path) if native_manifest_path.is_file() else ""
        native_identity = native_manifest.get(
            "native_current_identity" if recovered_native else "current_identity", {}
        )
        recovery_identity = native_manifest.get("recovery_current_identity", {})
        operation_identity = operation.get("v26_current_identity", {})
        shared_identity_keys = (
            "run_id", "physical_model_sha256", "campaign_window_sha256",
            "producer_identity_sha256", "mode_manifest_sha256", "ordered_mode_key_sha256",
        )
        recovery_receipt_path = Path(str(native_recovery.get("checker_receipt_path", ""))).resolve()
        try:
            recovery_receipt = json.loads(recovery_receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            recovery_receipt = {}
        recovery_receipt_sha = (
            _sha256_file(recovery_receipt_path) if recovery_receipt_path.is_file() else ""
        )
        recovery_receipt_ok = bool(
            recovered_native
            and recovery_receipt_path.is_relative_to(expected_native_root)
            and recovery_receipt.get("schema") == "task40extra.review_v26_native_case_recovery_check.v1"
            and recovery_receipt.get("status") == "PASS_READONLY_THREE_CASE_RECOVERY"
            and recovery_receipt.get("checker_passed") is True
            and recovery_receipt_sha == native_recovery.get("checker_receipt_sha256")
            and recovery_receipt_sha == native_manifest.get("recovery_checker_receipt_sha256")
            and recovery_receipt.get("original_native_current_identity") == native_identity
            and recovery_receipt.get("recovery_current_identity") == operation_identity == recovery_identity
            and recovery_identity.get("source_sha") != native_identity.get("source_sha")
            and all(native_identity.get(key) == recovery_identity.get(key) for key in shared_identity_keys)
        )
        complete_stream = operation.get("complete_stream", {})
        complete_stream = complete_stream if isinstance(complete_stream, Mapping) else {}
        recorded = complete_stream.get("consumer_replay", {})
        recorded = recorded if isinstance(recorded, Mapping) else {}
        recovery_only_footer = bool(
            recovered_native
            and not recorded
            and status in {"RESOURCE_CONTROLLED_STOP", "FAILED_V26_SELECTED_Q_GATES"}
        )
        if recovered_native and not recorded:
            checks["v26_recovery_footer_has_identity_without_consumer_claim"] = bool(
                recovery_only_footer
                and operation.get("official_result") is False
                and operation.get("v26_current_identity") == recovery_identity
                and "complete_stream" not in operation
                and operation.get("factor_or_solve_built") is False
            )
        native_identity_ok = bool(
            native_root == expected_native_root
            and native_manifest_path.is_relative_to(expected_native_root)
            and (
                (
                    not recovered_native
                    and native_status == "PASS_COMPLETE_Q0_NATIVE_CONSUMER"
                    and native_identity == operation_identity
                )
                or (recovered_native and native_status == "PASS_RECOVERED_THREE_NATIVE_CASES" and recovery_receipt_ok)
            )
            and native_manifest.get("producer_identity_sha256") == producer_identity_sha
            and native_manifest.get("saved_replay_manifest_sha256") == replay_sha
            and (not binding or binding.get("native_manifest_sha256") == native_sha)
            and (
                (
                    not recovered_native
                    and type(native_manifest.get("native_volume_apply_count")) is int
                    and native_manifest.get("native_volume_apply_count") == 6
                    and type(native_manifest.get("provider_sweep_count")) is int
                    and native_manifest.get("provider_sweep_count") == 9
                )
                or (
                    recovered_native
                    and native_manifest.get("native_volume_apply_count") is None
                    and native_manifest.get("provider_sweep_count") is None
                    and native_manifest.get("elapsed_seconds") is None
                    and native_manifest.get("elapsed_seconds_status") == "UNKNOWN_NOT_PERSISTED_BEFORE_KEYERROR"
                    and native_manifest.get("count_provenance") == {
                        "native_volume_apply_count": "SOURCE_DERIVED",
                        "provider_sweep_count": "SOURCE_DERIVED",
                    }
                )
            )
        )
        checks["v26_native_recovery_checker_receipt_bound"] = bool(
            not recovered_native or recovery_receipt_ok
        )
        try:
            native_cases: dict[str, dict[str, np.ndarray]] = {}
            native_case_records = native_manifest.get("cases", {})
            for case_name in ("q0_case_1", "q0_case_2", "q4_pair"):
                item = native_case_records.get(case_name, {})
                path = (native_root / str(item.get("path", ""))).resolve()
                sidecar_path = path.with_suffix(".json")
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if (
                    not path.is_relative_to(native_root)
                    or not path.is_file()
                    or path.stat().st_size != item.get("bytes")
                    or _sha256_file(path) != item.get("sha256")
                    or sidecar.get("sha256") != item.get("sha256")
                    or sidecar.get("array_sha256") != item.get("array_sha256")
                    or sidecar.get("producer_identity_sha256") != producer_identity_sha
                    or sidecar.get("saved_replay_manifest_sha256") != replay_sha
                    or sidecar.get("current_identity") != native_identity
                ):
                    raise ValueError(f"V26 native case identity failed: {case_name}")
                current: dict[str, np.ndarray] = {}
                with np.load(path, allow_pickle=False) as archive:
                    hashes = item.get("array_sha256", {})
                    shapes = item.get("array_shapes", {})
                    if set(archive.files) != set(hashes) or set(archive.files) != set(shapes):
                        raise ValueError(f"V26 native case array inventory differs: {case_name}")
                    for name in archive.files:
                        value = np.asarray(archive[name]).copy()
                        if (
                            value.ndim != 1
                            or value.dtype != np.dtype(np.complex128)
                            or list(value.shape) != shapes.get(name)
                            or not np.isfinite(value).all()
                            or _v26_array_sha256(value) != hashes.get(name)
                        ):
                            raise ValueError(f"V26 native raw array failed validation: {case_name}/{name}")
                        current[name] = value
                native_cases[case_name] = current
            checks["v26_native_manifest_and_case_arrays_hash_bound"] = native_identity_ok

            def relative_error(left: np.ndarray, right: np.ndarray, scale: np.ndarray | None = None) -> dict[str, float]:
                if left.shape != right.shape:
                    raise ValueError("V26 comparison arrays have different shapes")
                if not np.isfinite(left).all() or not np.isfinite(right).all():
                    raise ValueError("V26 comparison arrays contain non-finite values")
                absolute = float(np.linalg.norm(left - right))
                if scale is not None:
                    if not np.isfinite(scale).all():
                        raise ValueError("V26 native diagonal scale contains non-finite values")
                    scale_norm = float(np.linalg.norm(scale))
                else:
                    scale_norm = max(
                        float(np.linalg.norm(left)),
                        float(np.linalg.norm(right)),
                        np.finfo(float).tiny,
                    )
                if not math.isfinite(scale_norm) or scale_norm <= 0.0:
                    raise ValueError("V26 comparison scale must be finite and strictly positive")
                return {
                    "absolute": absolute,
                    "scale": scale_norm,
                    "relative_to_component": absolute / scale_norm,
                }

            q0_saved_1 = arrays_by_case["q0_case_1"]
            q0_saved_2 = arrays_by_case["q0_case_2"]
            q4_saved = arrays_by_case["q4_pair"]
            q0_native_1 = native_cases["q0_case_1"]
            q0_native_2 = native_cases["q0_case_2"]
            q4_native = native_cases["q4_pair"]
            recomputed = {
                "q0_case_1": relative_error(q0_saved_1["q0_total"], q0_native_1["native_q0_total"]),
                "q0_case_2": relative_error(q0_saved_2["q0_total"], q0_native_2["native_q0_total"]),
                "q4_case": relative_error(q4_saved["q4_total"], q4_native["native_q4_total"]),
                "volume": relative_error(q0_saved_1["q0_volume"], q0_native_1["native_q0_volume"]),
                "C": relative_error(q0_saved_1["q0_C"], q0_native_1["native_q0_C"]),
                "-D": relative_error(q0_saved_1["q0_minus_D"], q0_native_1["native_q0_minus_D"]),
                "Hhat": relative_error(q0_saved_1["q0_Hhat"], q0_native_1["native_q0_Hhat"]),
                "q0_to_q4_scaled": relative_error(
                    q0_saved_1["q4_total_from_q0"],
                    q0_native_1["native_q4_from_q0"],
                    q0_native_1["native_q0_total"],
                ),
                "q4_to_q0_scaled": relative_error(
                    q4_saved["q0_total_from_q4"],
                    q4_native["native_q0_from_q4"],
                    q4_native["native_q4_total"],
                ),
            }
            native_q0_diagonal_norm = float(np.linalg.norm(q0_native_1["native_q0_total"]))
            native_q4_diagonal_norm = float(np.linalg.norm(q4_native["native_q4_total"]))
            if (
                not math.isfinite(native_q0_diagonal_norm)
                or native_q0_diagonal_norm <= 0.0
                or not math.isfinite(native_q4_diagonal_norm)
                or native_q4_diagonal_norm <= 0.0
            ):
                raise ValueError("V26 native q0/q4 diagonal scales must be finite and strictly positive")
            leakage_04 = float(np.linalg.norm(q0_saved_1["q4_total_from_q0"])) / native_q0_diagonal_norm
            leakage_40 = float(np.linalg.norm(q4_saved["q0_total_from_q4"])) / native_q4_diagonal_norm
            comparison_passed = bool(
                all(value["relative_to_component"] <= 1.0e-11 for value in recomputed.values())
                and leakage_04 <= 1.0e-11
                and leakage_40 <= 1.0e-11
            )
            checks["v26_raw_native_comparisons_recomputed_at_scaled_1e_11"] = comparison_passed
            recovery_comparison_map = {
                "q0_case_1": "q0_case_1",
                "q0_case_2": "q0_case_2",
                "q4_case": "q4_pair",
                "volume": "volume",
                "C": "C",
                "-D": "-D",
                "Hhat": "Hhat",
                "q0_to_q4_scaled": "q0_to_q4_scaled",
                "q4_to_q0_scaled": "q4_to_q0_scaled",
            }

            def metric_matches_record(record: Any, calculated: Mapping[str, float]) -> bool:
                if not isinstance(record, Mapping):
                    return False
                try:
                    return all(
                        math.isfinite(float(record[name]))
                        and math.isclose(
                            float(record[name]),
                            float(calculated[name]),
                            rel_tol=1.0e-6,
                            abs_tol=1.0e-14,
                        )
                        for name in ("absolute", "scale", "relative_to_component")
                    )
                except (KeyError, TypeError, ValueError, OverflowError):
                    return False

            recovery_comparisons = recovery_receipt.get("recomputed_comparisons", {})
            recovery_comparisons = recovery_comparisons if isinstance(recovery_comparisons, Mapping) else {}
            recovery_leakage = recovery_receipt.get("recomputed_scaled_leakage", {})
            recovery_leakage = recovery_leakage if isinstance(recovery_leakage, Mapping) else {}
            recovery_metrics_match = bool(
                recovered_native
                and recovery_receipt_ok
                and recovery_receipt.get("comparison_limit") == 1.0e-11
                and set(recovery_comparisons) == set(recovery_comparison_map.values())
                and all(
                    metric_matches_record(
                        recovery_comparisons[receipt_key],
                        recomputed[calculated_key],
                    )
                    for calculated_key, receipt_key in recovery_comparison_map.items()
                )
                and math.isclose(
                    float(recovery_leakage.get("q0_to_q4", math.inf)), leakage_04,
                    rel_tol=1.0e-6, abs_tol=1.0e-14,
                )
                and math.isclose(
                    float(recovery_leakage.get("q4_to_q0", math.inf)), leakage_40,
                    rel_tol=1.0e-6, abs_tol=1.0e-14,
                )
                and native_manifest.get("recomputed_comparisons") == recovery_comparisons
                and native_manifest.get("recomputed_scaled_leakage") == recovery_leakage
            )
            if recovered_native:
                checks["v26_native_recovery_checker_receipt_bound"] = bool(
                    recovery_receipt_ok and recovery_metrics_match
                )
                checks["v26_native_manifest_and_case_arrays_hash_bound"] = bool(
                    native_identity_ok and recovery_metrics_match
                )
            if recovered_native:
                derived = native_manifest.get("source_derived_counts", {})
                replay_counts = recorded.get("source_derived_counts")
                if not isinstance(replay_counts, Mapping):
                    replay_counts = recovery_receipt.get("historical_native_counts", {})
                checks["v26_native_apply_and_provider_sweep_counts_recorded"] = bool(
                    native_manifest.get("native_volume_apply_count") is None
                    and native_manifest.get("provider_sweep_count") is None
                    and binding.get("native_volume_apply_count") is None
                    and binding.get("provider_sweep_count") is None
                    and derived == replay_counts
                    and derived == recovery_receipt.get("historical_native_counts")
                    and derived.get("native_volume_apply_count", {}).get("measured") is None
                    and derived.get("native_volume_apply_count", {}).get("source_derived") == 6
                    and derived.get("provider_sweep_count", {}).get("measured") is None
                    and derived.get("provider_sweep_count", {}).get("source_derived") == 9
                    and derived.get("native_action_elapsed_seconds", {}).get("measured") is None
                    and derived.get("native_action_elapsed_seconds", {}).get("classification")
                    == "UNKNOWN_NOT_PERSISTED_BEFORE_KEYERROR"
                    and (
                        (
                            recovery_only_footer
                            and not recorded
                            and "complete_stream" not in operation
                        )
                        or (
                            bool(recorded)
                            and recorded.get("native_volume_apply_count") is None
                            and recorded.get("provider_sweep_count") is None
                            and recorded.get("native_action_elapsed_seconds") is None
                            and recorded.get("native_action_elapsed_seconds_status")
                            == "UNKNOWN_NOT_PERSISTED_BEFORE_KEYERROR"
                        )
                    )
                )
            else:
                checks["v26_native_apply_and_provider_sweep_counts_recorded"] = bool(
                    binding.get("native_volume_apply_count", native_manifest.get("native_volume_apply_count")) == 6
                    and binding.get("provider_sweep_count", native_manifest.get("provider_sweep_count")) == 9
                    and math.isclose(
                        float(binding.get("native_action_elapsed_seconds", native_manifest.get("elapsed_seconds", -1.0))),
                        float(native_manifest.get("elapsed_seconds", -2.0)),
                        rel_tol=1.0e-9,
                        abs_tol=1.0e-12,
                    )
                )
            if recovery_only_footer:
                checks["v26_scaled_metrics_match_recovery_checker_receipt"] = recovery_metrics_match
            else:
                checks["v26_scaled_metrics_match_operation_record"] = bool(
                    math.isclose(
                        float(recorded.get("q0_to_q4_scaled_error", {}).get("relative_to_component", math.inf)),
                        recomputed["q0_to_q4_scaled"]["relative_to_component"],
                        rel_tol=1.0e-6,
                        abs_tol=1.0e-14,
                    )
                    and math.isclose(
                        float(recorded.get("q4_to_q0_scaled_error", {}).get("relative_to_component", math.inf)),
                        recomputed["q4_to_q0_scaled"]["relative_to_component"],
                        rel_tol=1.0e-6,
                        abs_tol=1.0e-14,
                    )
                    and math.isclose(float(recorded.get("q0_to_q4_leakage_ratio", math.inf)), leakage_04, rel_tol=1.0e-6, abs_tol=1.0e-14)
                    and math.isclose(float(recorded.get("q4_to_q0_leakage_ratio", math.inf)), leakage_40, rel_tol=1.0e-6, abs_tol=1.0e-14)
                    and recorded.get("cross_q_scale_q0_to_q4") == "native q0 diagonal output norm"
                    and recorded.get("cross_q_scale_q4_to_q0") == "native q4 diagonal output norm"
                )
        except (OSError, ValueError, TypeError, KeyError, OverflowError, zipfile.BadZipFile):
            checks["v26_native_manifest_and_case_arrays_hash_bound"] = False
            checks["v26_raw_native_comparisons_recomputed_at_scaled_1e_11"] = False
            checks["v26_native_apply_and_provider_sweep_counts_recorded"] = False
            checks["v26_native_recovery_checker_receipt_bound"] = False
            checks["v26_scaled_metrics_match_operation_record"] = False
        if recovery_only_footer and status == "RESOURCE_CONTROLLED_STOP":
            checks["v26_native_stage_status_matches_raw_comparisons"] = bool(
                partial.get("status") == "controlled_stop"
                and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
                and partial.get("q_coverage", {}).get("csr_status") == "NOT_BUILT"
                and partial.get("q_coverage", {}).get("complete_streamed_consumer_count") == 0
                and "complete_stream" not in operation
                and checks.get("v26_raw_native_comparisons_recomputed_at_scaled_1e_11") is True
                and checks.get("v26_native_recovery_checker_receipt_bound") is True
            )
        elif recovery_only_footer and status == "FAILED_V26_SELECTED_Q_GATES":
            checks["v26_native_stage_status_matches_raw_comparisons"] = bool(
                partial.get("status") == "failed"
                and partial.get("outcome") == "STAGE_FAILED"
                and partial.get("q_coverage", {}).get("csr_status") == "NOT_BUILT"
                and partial.get("q_coverage", {}).get("complete_streamed_consumer_count") == 0
                and "complete_stream" not in operation
                and checks.get("v26_raw_native_comparisons_recomputed_at_scaled_1e_11") is True
                and checks.get("v26_native_recovery_checker_receipt_bound") is True
            )
        elif expected_stop_stage == "selected_reference_q_csr" and status == "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT":
            checks["v26_native_stage_status_matches_raw_comparisons"] = bool(
                partial.get("status") == "controlled_stop"
                and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
                and checks.get("v26_raw_native_comparisons_recomputed_at_scaled_1e_11") is True
            )
        elif expected_stop_stage == "selected_reference_q_csr" and status == "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR":
            checks["v26_native_stage_status_matches_raw_comparisons"] = bool(
                partial.get("status") == "controlled_stop"
                and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
                and partial.get("q_coverage", {}).get("csr_status") == "BUILT"
                and checks.get("v26_raw_native_comparisons_recomputed_at_scaled_1e_11") is True
            )
        elif expected_stop_stage == "selected_reference_q_csr" and status == "FAILED_Q0_FACTOR_LIFECYCLE":
            checks["v26_native_stage_status_matches_raw_comparisons"] = bool(
                partial.get("status") == "failed"
                and partial.get("outcome") == "STAGE_FAILED"
                and partial.get("failed_stage") == "q0_factor_lifecycle"
                and partial.get("q_coverage", {}).get("csr_status") == "BUILT"
                and checks.get("v26_raw_native_comparisons_recomputed_at_scaled_1e_11") is True
            )
        else:
            checks["v26_native_stage_status_matches_raw_comparisons"] = bool(
                partial.get("status") == "stage_completed"
                and partial.get("outcome") == "STAGE_COMPLETED"
                and status in ({"PASS_COMPLETE_Q0_CSR", "PASS_COMPLETE_Q0_CSR_AND_FACTOR"} if expected_stop_stage == "selected_reference_q_csr" else {"PASS_COMPLETE_Q0_STREAM"})
                and checks.get("v26_raw_native_comparisons_recomputed_at_scaled_1e_11") is True
            )
        csr_complete_statuses = {
            "PASS_COMPLETE_Q0_CSR",
            "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
            "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR",
            "FAILED_Q0_FACTOR_LIFECYCLE",
        }
        if expected_stop_stage == "selected_reference_q_csr" and status in csr_complete_statuses:
            tiles = operation.get("row_tile_store", {})
            tiles = tiles if isinstance(tiles, Mapping) else {}
            saved = operation.get("saved_artifacts", {})
            saved = saved if isinstance(saved, Mapping) else {}
            all_csr_files_valid = True
            for item in saved.values():
                if not isinstance(item, Mapping):
                    all_csr_files_valid = False
                    break
                path = (root / str(item.get("path", ""))).resolve()
                if not path.is_relative_to(root) or not path.is_file() or _sha256_file(path) != item.get("sha256"):
                    all_csr_files_valid = False
                    break
            checks["v26_complete_q0_csr_artifacts_hash_bound"] = bool(
                all_csr_files_valid
                and tiles.get("complete_row_domain") is True
                and tiles.get("complete_column_domain") is True
                and tiles.get("row_count") == tiles.get("shape", [None])[0]
                and operation.get("solve_ready") is False
            )
            checks["v26_wide_pre_csr_structure_checkpoint_preserved"] = bool(
                (root / "v26_q0_preallocation_row_structure.npz").is_file()
                and operation.get("csr_structure_checkpoint", {}).get("wide_int64_rows_and_offsets_preserved") is True
                and operation.get("csr_structure_checkpoint", {}).get("sha256")
                == _sha256_file(root / "v26_q0_preallocation_row_structure.npz")
            )
            csr_input_gate = next(
                (
                    row for row in stage_receipt.get("resource_gates", [])
                    if isinstance(row, Mapping)
                    and row.get("request_facts", {}).get("source_csr_payload_bytes_to_retain")
                    == operation.get("matrix_identity", {}).get("csr_payload_bytes")
                ),
                {},
            )
            csr_input_admission = csr_input_gate.get("admission", {}) if isinstance(csr_input_gate, Mapping) else {}
            resource_blocker = operation.get("resource_blocker", {})
            resource_blocker = resource_blocker if isinstance(resource_blocker, Mapping) else {}
            checks["v26_q0_csr_retention_resource_gate_passed"] = bool(
                (
                    csr_input_gate
                    and csr_input_admission.get("task_cgroup_gate_passed") is True
                    and csr_input_admission.get("process_tree_gate_passed") is True
                    and csr_input_admission.get("disk_gate_passed") is True
                )
                or (
                    status == "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
                    and operation.get("failed_stage") == "task40_v26_q0_factor_csr_input_retention"
                    and resource_blocker.get("passed") is False
                    and resource_blocker.get("additional_object_upper_bound_bytes")
                    == operation.get("matrix_identity", {}).get("csr_payload_bytes")
                )
            )
            factor_report = operation.get("factor_lifecycle", {})
            factor_report = factor_report if isinstance(factor_report, Mapping) else {}
            factor_path = Path(str(operation.get("factor_checkpoint", {}).get("path", ""))).resolve()
            factor_hash = str(operation.get("factor_checkpoint", {}).get("sha256", ""))
            try:
                factor_checkpoint = json.loads(factor_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                factor_checkpoint = {}
            factor_checkpoint_identity = bool(
                factor_path.is_relative_to(root)
                and factor_path.is_file()
                and factor_hash
                and _sha256_file(factor_path) == factor_hash
                and factor_report.get("checkpoint_path") == str(factor_path)
                and factor_report.get("checkpoint_sha256") == factor_hash
                and factor_checkpoint.get("schema") == "task40extra.review_v26_selected_q0_factor_lifecycle.v1"
                and factor_checkpoint.get("current_identity") == operation.get("v26_current_identity")
                and factor_checkpoint.get("selected_q") == 0
                and factor_checkpoint.get("factor_route") == "V26_SELECTED_Q0_ONLY; no fabricated q_count=1 profile"
            )
            factor_pass = status == "PASS_COMPLETE_Q0_CSR_AND_FACTOR"
            factor_controlled = status == "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR"
            factor_failed = status == "FAILED_Q0_FACTOR_LIFECYCLE"
            factor_phases = [row.get("phase") for row in factor_checkpoint.get("phases", []) if isinstance(row, Mapping)]
            factor_gates = factor_checkpoint.get("resource_gates", [])
            gate_by_stage = {
                str(row.get("stage")): row
                for row in factor_gates
                if isinstance(row, Mapping)
            }
            conversion_facts = gate_by_stage.get("task40_v26_q0_factor_petsc_conversion", {}).get("request_facts", {})
            symbolic_facts = gate_by_stage.get("task40_v26_q0_factor_symbolic", {}).get("request_facts", {})
            numeric_facts = gate_by_stage.get("task40_v26_q0_factor_numeric", {}).get("request_facts", {})
            conversion_seen = "task40_v26_q0_factor_petsc_conversion" in gate_by_stage
            symbolic_seen = "task40_v26_q0_factor_symbolic" in gate_by_stage
            numeric_seen = "task40_v26_q0_factor_numeric" in gate_by_stage
            conversion_facts_ok = bool(
                not conversion_seen
                or (
                    conversion_facts.get("symbolic_guard_bytes") == max(
                        128 << 20,
                        4 * int(conversion_facts.get("source_csr_payload_bytes_already_resident", -1)),
                    )
                    and conversion_facts.get("csr_to_petsc_conversion_workspace_bytes")
                    == conversion_facts.get("source_csr_payload_bytes_already_resident")
                    and conversion_facts.get("future_factor_vector_and_checker_reserve_bytes")
                    == int(tiles.get("shape", [0])[0]) * 6 * np.dtype(np.complex128).itemsize
                )
            )
            symbolic_facts_ok = bool(
                not symbolic_seen
                or (
                    conversion_seen
                    and symbolic_facts.get("symbolic_factorization_guard_bytes")
                    == conversion_facts.get("symbolic_guard_bytes")
                    and symbolic_facts.get("future_co_resident_reserve_bytes")
                    == symbolic_facts.get("symbolic_factorization_guard_bytes")
                    + symbolic_facts.get("vector_and_checker_reserve_bytes", 0)
                    and symbolic_facts.get("vector_and_checker_reserve_bytes")
                    == int(tiles.get("shape", [0])[0]) * 6 * np.dtype(np.complex128).itemsize
                )
            )
            numeric_facts_ok = bool(
                not numeric_seen
                or (
                    symbolic_seen
                    and numeric_facts.get("numeric_factor_reserve_bytes_from_INFOG_16_17")
                    == factor_checkpoint.get("symbolic_factor_reserve_bytes")
                    and numeric_facts.get("future_co_resident_reserve_bytes")
                    == factor_checkpoint.get("symbolic_factor_reserve_bytes")
                    and type(numeric_facts.get("vector_and_checker_reserve_bytes")) is int
                    and numeric_facts.get("vector_and_checker_reserve_bytes") > 0
                    and numeric_facts.get("vector_and_checker_reserve_bytes")
                    == int(tiles.get("shape", [0])[0]) * 6 * np.dtype(np.complex128).itemsize
                    and numeric_facts.get("workspace_bytes")
                    == numeric_facts.get("vector_and_checker_reserve_bytes")
                )
            )
            resource_facts_ok = bool(
                conversion_facts_ok
                and symbolic_facts_ok
                and numeric_facts_ok
                and (not factor_pass or conversion_seen and symbolic_seen and numeric_seen)
            )
            probe = factor_checkpoint.get("fresh_factor_probe", {})
            probe = probe if isinstance(probe, Mapping) else {}
            rhs_solve = factor_checkpoint.get("separate_nonzero_q0_rhs_solve", {})
            rhs_solve = rhs_solve if isinstance(rhs_solve, Mapping) else {}
            cleanup = factor_checkpoint.get("cleanup", {})
            cleanup = cleanup if isinstance(cleanup, Mapping) else {}
            symbolic_info = factor_checkpoint.get("symbolic_mumps_evidence", {}).get("raw_infog", {})
            numeric_info = factor_checkpoint.get("numeric_mumps_evidence", {}).get("raw_infog", {})
            lifecycle_pass = bool(
                factor_pass
                and factor_checkpoint.get("status") == "PASS_Q0_FACTOR_PROBE_AND_RHS_SOLVE"
                and factor_checkpoint_identity
                and factor_checkpoint.get("petsc_scalar_type") == np.dtype(np.complex128).str
                and factor_checkpoint.get("petsc_int_type") == np.dtype(np.int32).str
                and factor_checkpoint.get("petsc_comm_size") == 1
                and factor_checkpoint.get("mumps_controls_readback_before_symbolic")
                == {"35": 0, "10": 0, "2": 0, "3": 6, "4": 2}
                and type(symbolic_info.get("16")) is int
                and symbolic_info.get("16") == symbolic_info.get("17")
                and type(numeric_info.get("9")) is int
                and type(numeric_info.get("19")) is int
                and type(numeric_info.get("22")) is int
                and probe.get("input_nonzero") is True
                and probe.get("passed") is True
                and type(probe.get("relative_full_true_residual")) in (float, int)
                and probe.get("relative_full_true_residual") <= 1.0e-10
                and rhs_solve.get("rhs_nonzero") is True
                and rhs_solve.get("passed") is True
                and type(rhs_solve.get("relative_full_true_residual")) in (float, int)
                and rhs_solve.get("relative_full_true_residual") <= 1.0e-10
                and cleanup.get("destroy_succeeded") is True
                and cleanup.get("native_object_counts_after_destroy")
                == {"matrices_current": 0, "factors_current": 0, "vectors_current": 0}
                and factor_checkpoint.get("max_simultaneous_native_objects", {}).get("matrices") == 1
                and factor_checkpoint.get("max_simultaneous_native_objects", {}).get("factors") == 1
                and "cleanup_complete" in factor_phases
                and resource_facts_ok
            )
            checks["v26_q0_exact_factor_checkpoint_hash_bound"] = factor_checkpoint_identity
            checks["v26_q0_factor_resource_reserves_explicit"] = resource_facts_ok
            checks["v26_q0_factor_probe_rhs_and_cleanup_verified"] = (lifecycle_pass and raw_vectors_ok) if factor_pass else bool(
                factor_controlled
                and factor_checkpoint_identity
                and isinstance(operation.get("resource_blocker"), Mapping)
                and operation.get("resource_blocker", {}).get("passed") is False
                and cleanup.get("destroy_succeeded") is True
                and factor_checkpoint.get("q_coverage", {}).get("numeric_factor_built") is not True
            ) if factor_controlled else bool(
                factor_failed
                and factor_checkpoint_identity
                and factor_checkpoint.get("status") in {
                    "FAILED_Q0_FACTOR_LIFECYCLE",
                    "FAILED_Q0_FACTOR_CLEANUP",
                    "FAILED_Q0_FACTOR_CHECKPOINT",
                }
                and isinstance(factor_checkpoint.get("failure"), Mapping)
            )
            try:
                csr_sha = hashlib.sha256()
                csr_sha.update(b"csr")
                csr_sha.update(np.asarray(tiles.get("shape"), dtype=np.int64).tobytes())
                csr_sha.update(np.dtype(np.complex128).str.encode("ascii"))
                arrays: dict[str, Any] = {}
                for name in ("indptr", "indices", "data"):
                    item = tiles.get("files", {}).get(name, {})
                    path = (root / str(item.get("path", ""))).resolve()
                    array = np.load(path, mmap_mode="r", allow_pickle=False)
                    arrays[name] = array
                    if _v26_array_sha256(array) != operation.get("matrix_identity", {}).get("csr_array_sha256", {}).get(name):
                        raise ValueError(f"V26 factor input array hash differs: {name}")
                    csr_sha.update(name.encode("ascii"))
                    csr_sha.update(array.dtype.str.encode("ascii"))
                    csr_sha.update(np.asarray(array.shape, dtype=np.int64).tobytes())
                    csr_sha.update(memoryview(np.ascontiguousarray(array)).cast("B"))
                source_csr_hash = csr_sha.hexdigest()
                offsets = arrays["indptr"]
                indices = arrays["indices"]
                data = arrays["data"]
                wide_structure = root / "v26_q0_preallocation_row_structure.npz"
                with np.load(wide_structure, allow_pickle=False) as saved_structure:
                    wide_counts = saved_structure["row_counts_int64"]
                    wide_offsets = saved_structure["wide_offsets_int64"]
                    structure_matches = bool(
                        wide_counts.dtype == np.dtype(np.int64)
                        and wide_offsets.dtype == np.dtype(np.int64)
                        and wide_counts.shape == (int(tiles["shape"][0]),)
                        and wide_offsets.shape == (int(tiles["shape"][0]) + 1,)
                        and np.array_equal(np.diff(offsets).astype(np.int64), wide_counts)
                        and np.array_equal(offsets.astype(np.int64), wide_offsets)
                    )
                source_hash_matches = bool(
                    indices.dtype == np.dtype(np.int32)
                    and offsets.dtype == np.dtype(np.int32)
                    and data.dtype == np.dtype(np.complex128)
                    and source_csr_hash == factor_checkpoint.get("source_csr_sha256")
                    and structure_matches
                )

                def verify_factor_vectors(label: str, record: Mapping[str, Any]) -> bool:
                    raw = record.get("raw_artifact", {})
                    raw = raw if isinstance(raw, Mapping) else {}
                    raw_path = (factor_path.parent / str(raw.get("path", ""))).resolve()
                    raw_arrays: dict[str, np.ndarray] = {}
                    if (
                        not raw_path.is_relative_to(factor_path.parent)
                        or not raw_path.is_file()
                        or raw.get("bytes") != raw_path.stat().st_size
                        or raw.get("sha256") != _sha256_file(raw_path)
                        or raw.get("array_names") != ["input_x", "residual", "rhs", "solution"]
                        or raw.get("native_vectors_destroyed_before_serialization") is not True
                        or raw.get("native_vector_count_before_serialization") != 0
                    ):
                        return False
                    with np.load(raw_path, allow_pickle=False) as archive:
                        if set(archive.files) != {"input_x", "rhs", "solution", "residual"}:
                            return False
                        for name in archive.files:
                            value = np.asarray(archive[name]).copy()
                            if (
                                value.ndim != 1
                                or value.dtype != np.dtype(np.complex128)
                                or value.shape != (int(tiles["shape"][0]),)
                                or not np.isfinite(value).all()
                                or _v26_array_sha256(value) != raw.get("array_sha256", {}).get(name)
                            ):
                                return False
                            raw_arrays[name] = value
                    if (
                        not np.any(raw_arrays["input_x"] != 0.0)
                        or not np.any(raw_arrays["rhs"] != 0.0)
                    ):
                        return False
                    matrix = sparse.csr_matrix(
                        (data, indices, offsets),
                        shape=tuple(map(int, tiles["shape"])),
                        copy=False,
                    )
                    rebuilt_rhs = np.asarray(matrix @ raw_arrays["input_x"], dtype=np.complex128)
                    rebuilt_residual = np.asarray(matrix @ raw_arrays["solution"], dtype=np.complex128)
                    rebuilt_residual -= raw_arrays["rhs"]
                    if (
                        not np.array_equal(rebuilt_rhs, raw_arrays["rhs"])
                        or not np.array_equal(rebuilt_residual, raw_arrays["residual"])
                    ):
                        return False
                    relative = float(
                        np.linalg.norm(rebuilt_residual) / np.linalg.norm(raw_arrays["rhs"])
                    )
                    return bool(
                        math.isfinite(relative)
                        and relative <= 1.0e-10
                        and math.isclose(
                            relative,
                            float(record.get("relative_full_true_residual", math.inf)),
                            rel_tol=1.0e-8,
                            abs_tol=1.0e-15,
                        )
                        and record.get("passed") is True
                    )

                solve_accounting = factor_checkpoint.get("solve_accounting", {})
                solve_accounting = solve_accounting if isinstance(solve_accounting, Mapping) else {}
                raw_case_records = {
                    "fresh_factor_probe": probe,
                    "separate_nonzero_q0_rhs_solve": rhs_solve,
                }
                raw_case_present = {
                    label: isinstance(record.get("raw_artifact"), Mapping)
                    for label, record in raw_case_records.items()
                }
                raw_case_checks = {
                    label: verify_factor_vectors(label, record)
                    for label, record in raw_case_records.items()
                    if raw_case_present[label]
                }
                raw_vectors_ok = bool(
                    all(raw_case_checks.values())
                    and (
                        (factor_pass and all(raw_case_present.values())
                         and all(
                             solve_accounting.get(label, {}).get("mat_solve_invoked") == 1
                             and solve_accounting.get(label, {}).get("mat_solve_completed") == 1
                             and solve_accounting.get(label, {}).get("mat_solve_failed") == 0
                             for label in raw_case_records
                         ))
                        or (factor_controlled and not any(raw_case_present.values()))
                        or factor_failed
                    )
                )
                del arrays
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                source_hash_matches = False
                raw_vectors_ok = False
            checks["v26_q0_factor_input_hash_and_wide_structure_verified"] = source_hash_matches
            checks["v26_q0_factor_raw_vectors_recomputed"] = raw_vectors_ok
            if factor_pass:
                checks["v26_factor_lifecycle_pass_matches_stage_status"] = bool(
                    lifecycle_pass
                    and partial.get("status") == "stage_completed"
                    and partial.get("q_coverage", {}).get("factor_count") == 1
                    and operation.get("factor_or_solve_built") is True
                )
            elif factor_controlled:
                checks["v26_factor_lifecycle_pass_matches_stage_status"] = bool(
                    checks["v26_q0_factor_probe_rhs_and_cleanup_verified"]
                    and partial.get("status") == "controlled_stop"
                    and partial.get("q_coverage", {}).get("factor_count") == 0
                    and operation.get("factor_or_solve_built") is False
                )
            else:
                checks["v26_factor_lifecycle_pass_matches_stage_status"] = bool(
                    factor_failed
                    and partial.get("status") == "failed"
                    and partial.get("q_coverage", {}).get("factor_count")
                    == int(factor_checkpoint.get("q_coverage", {}).get("numeric_factor_built") is True)
                    and operation.get("factor_or_solve_built")
                    == factor_checkpoint.get("q_coverage", {}).get("numeric_factor_built")
                )
        elif expected_stop_stage == "selected_reference_q_csr" and recovery_only_footer and status == "RESOURCE_CONTROLLED_STOP":
            checks["v26_native_recovery_csr_controlled_stop_is_explicit"] = bool(
                partial.get("status") == "controlled_stop"
                and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
                and partial.get("q_coverage", {}).get("csr_status") == "NOT_BUILT"
                and partial.get("q_coverage", {}).get("complete_streamed_consumer_count") == 0
                and "complete_stream" not in operation
                and checks.get("v26_native_recovery_checker_receipt_bound") is True
            )
        elif expected_stop_stage == "selected_reference_q_csr" and recovery_only_footer and status == "FAILED_V26_SELECTED_Q_GATES":
            checks["v26_native_recovery_csr_failure_is_explicit"] = bool(
                partial.get("status") == "failed"
                and partial.get("outcome") == "STAGE_FAILED"
                and partial.get("q_coverage", {}).get("csr_status") == "NOT_BUILT"
                and partial.get("q_coverage", {}).get("complete_streamed_consumer_count") == 0
                and "complete_stream" not in operation
                and checks.get("v26_native_recovery_checker_receipt_bound") is True
            )
        elif expected_stop_stage == "selected_reference_q_csr":
            checks["v26_csr_controlled_stop_is_explicit"] = bool(
                status == "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT"
                and partial.get("status") == "controlled_stop"
                and partial.get("q_coverage", {}).get("csr_status") == "NOT_BUILT"
            )
    else:
        checks["v26_native_stage_explicitly_not_run"] = bool(
            expected_stop_stage == "selected_reference_q_build_only"
            and replay_manifest.get("native_comparison") == "NOT_RUN_IN_THIS_STAGE"
            and replay_manifest.get("native_volume_apply_count") == 0
            and replay_manifest.get("provider_sweep_count") == 0
        )
        checks["v26_build_only_stage_status_matches_replay"] = bool(
            status == "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
            and partial.get("status") == "stage_completed"
            and partial.get("outcome") == "STAGE_COMPLETED"
            and partial.get("q_coverage", {}).get("built_q_count") == 0
        )
    return checks


def _v27_saved_q0_readback_checks(
    *,
    output_directory: Path,
    partial: Mapping[str, Any],
    expected_stop_stage: str,
) -> dict[str, bool]:
    """Independently verify V27's controlled stop or saved q0 CSR readback."""
    checks: dict[str, bool] = {}
    stage = partial.get("v27_saved_q0_stage", {})
    stage = stage if isinstance(stage, Mapping) else {}
    operation = stage.get("operation", {})
    operation = operation if isinstance(operation, Mapping) else {}
    status = str(operation.get("status", ""))
    try:
        donor = operation.get("donor_import_identity", {})
        donor = donor if isinstance(donor, Mapping) else {}
        source_identity = operation.get("source_identity", {})
        source_identity = source_identity if isinstance(source_identity, Mapping) else {}
        execution = operation.get("current_execution_identity", {})
        execution = execution if isinstance(execution, Mapping) else {}
        producer = donor.get("producer_identity", {})
        producer = producer if isinstance(producer, Mapping) else {}
        selector_path = Path(str(stage.get("selector_path", ""))).resolve()
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
        selector_sha = _sha256_file(selector_path)
        donor_sha = hashlib.sha256(
            json.dumps(donor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        checks["v27_selector_donor_window_and_execution_identity_bound"] = bool(
            expected_stop_stage == "selected_reference_q_csr"
            and operation.get("schema") == "task40extra.review_v27_saved_q0_stage.v1"
            and operation.get("stop_stage") == expected_stop_stage
            and operation.get("operation") == "V27_SAVED_ONLY_COMPLETE_Q0_CSR"
            and operation.get("selector_sha256") == stage.get("selector_sha256") == selector_sha
            and selector.get("schema") == "task40extra.review_v27_saved_q0_operation.v1"
            and selector.get("operation") == operation.get("operation")
            and selector.get("donor_import") == donor
            and operation.get("donor_import_identity_sha256") == donor_sha
            and source_identity.get("donor_identity") == donor
            and source_identity.get("execution_identity") == execution
            and execution.get("source_sha") == partial.get("source_sha")
            and execution.get("run_id") == partial.get("run_id")
            and execution.get("input_sha256") == partial.get("input_sha256")
            and execution.get("physical_model_sha256") == partial.get("physical_model_sha256")
            and execution.get("campaign_window_sha256") == TASK40_V27_CAMPAIGN_SHA256
            and operation.get("saved_only_no_fe_or_native_rebuild") is True
            and operation.get("official_result") is False
            and operation.get("pde_solved") is False
            and operation.get("ksp_created") is False
        )
        replay = donor.get("saved_replay_manifest", {})
        replay = replay if isinstance(replay, Mapping) else {}
        recovery = donor.get("native_recovery_manifest", {})
        recovery = recovery if isinstance(recovery, Mapping) else {}
        recovery_checker = donor.get("native_recovery_checker", {})
        recovery_checker = recovery_checker if isinstance(recovery_checker, Mapping) else {}
        witness = donor.get("row_structure_witness", {})
        witness = witness if isinstance(witness, Mapping) else {}
        checks["v27_three_donor_identities_remain_separate_and_fixed"] = bool(
            producer.get("producer_source_sha") == V26_PRODUCER_SOURCE_SHA
            and producer.get("producer_run_id") == V26_PRODUCER_RUN_ID
            and producer.get("producer_run_directory") == str(V26_PRODUCER_RUN_RELATIVE)
            and replay.get("sha256") == V27_REPLAY_MANIFEST_SHA256
            and replay.get("status") == "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
            and recovery.get("sha256") == V27_NATIVE_RECOVERY_SHA256
            and recovery.get("status") == "PASS_RECOVERED_THREE_NATIVE_CASES"
            and recovery_checker.get("sha256") == V27_NATIVE_CHECKER_SHA256
            and recovery_checker.get("status") == "PASS_READONLY_THREE_CASE_RECOVERY"
            and witness.get("sha256") == V27_ROW_STRUCTURE_SHA256
            and witness.get("shape") == [777_644, 777_644]
            and witness.get("stored_structural_slots") == 577_061_168
            and source_identity.get("donor_identity_sha256") == donor_sha
        )
        operation_receipt_matches = bool(
            stage.get("operation_status") == status
            and stage.get("operation_sha256") == _sha256_file(
                output_directory / str(stage.get("operation_path", ""))
            )
            and partial.get("status") in {"controlled_stop", "stage_completed", "failed"}
            and partial.get("official_result") is False
            and partial.get("q_coverage", {}).get("expected_q_count") == 8
        )
        checks["v27_partial_receipt_binds_raw_operation"] = operation_receipt_matches

        manifest_path = output_directory / "v27_q0_csr" / "task40_v27_q0_csr_manifest.json"
        readback_path = output_directory / "v27_q0_csr_readback.npz"
        if status in {"RESOURCE_CONTROLLED_STOP_BEFORE_CSR", "RESOURCE_CONTROLLED_STOP_DURING_CSR"}:
            blocker = operation.get("resource_blocker", {})
            blocker = blocker if isinstance(blocker, Mapping) else {}
            manifest = {}
            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    manifest = {}
            no_completed_csr = manifest.get("status") != "COMPLETE_CSR"
            checks["v27_resource_gate_stop_is_explicit_and_csr_state_is_accurate"] = bool(
                partial.get("status") == "controlled_stop"
                and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
                and blocker.get("passed") is False
                and isinstance(blocker.get("stage"), str)
                and no_completed_csr
                and partial.get("q_coverage", {}).get("built_q_count") == 0
                and partial.get("q_coverage", {}).get("full_q_matrix_coverage") == "0/8"
                and partial.get("q_coverage", {}).get("factor_count") == 0
                and operation.get("factor_or_solve_built") is False
            )
            checks["v27_no_csr_readback_or_factor_claim_after_gate_stop"] = bool(
                not readback_path.exists()
                and operation.get("csr_readback") is None
                and operation.get("factor_or_solve_built") is False
            )
            if manifest:
                checks["v27_partial_structure_manifest_state_matches_operation"] = bool(
                    operation.get("csr_status") == manifest.get("status")
                    and manifest.get("status") in {
                        "ROW_STRUCTURE_CHECKPOINTED",
                        "STRUCTURE_COMPLETE_VALUES_PENDING",
                        "NUMERIC_FILL_INCOMPLETE",
                    }
                    and manifest.get("q_map_count") == 1
                    and manifest.get("q_map_branch") == 0
                )
            return checks

        if status == "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR" and not readback_path.exists():
            checks["v27_complete_csr_preserved_for_readback_continuation"] = bool(
                partial.get("status") == "controlled_stop"
                and operation.get("complete_numeric_csr") is True
                and operation.get("csr_status") == "COMPLETE_CSR"
                and partial.get("q_coverage", {}).get("built_q_count") == 1
            )
            checks["v27_readback_remains_unclaimed"] = operation.get("csr_readback") is None
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                artifact_records = manifest.get("csr_artifacts", {})
                artifact_records = artifact_records if isinstance(artifact_records, Mapping) else {}
                csr_artifacts_ok = True
                for name in ("indptr", "indices", "data"):
                    item = artifact_records.get(name, {})
                    item = item if isinstance(item, Mapping) else {}
                    artifact_path = Path(str(item.get("path", ""))).resolve()
                    if (
                        not artifact_path.is_relative_to(manifest_path.parent.resolve())
                        or not artifact_path.is_file()
                        or artifact_path.stat().st_size != item.get("bytes")
                        or _sha256_owned_payload(artifact_path) != item.get("sha256")
                    ):
                        csr_artifacts_ok = False
                        break
                checks["v27_complete_csr_manifest_and_payload_hashes_verified"] = bool(
                    csr_artifacts_ok
                    and manifest.get("schema") == "task40extra.review_v27_saved_q0_csr.v1"
                    and manifest.get("status") == "COMPLETE_CSR"
                    and manifest.get("shape") == [777_644, 777_644]
                    and manifest.get("stored_structural_slots") == 577_061_168
                    and manifest.get("csr_index_dtype") == np.dtype(np.int32).str
                    and manifest.get("csr_data_dtype") == np.dtype(np.complex128).str
                    and operation.get("csr_manifest_sha256") == _sha256_file(manifest_path)
                )
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                checks["v27_complete_csr_manifest_and_payload_hashes_verified"] = False
            return checks

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_records = manifest.get("csr_artifacts", {})
        artifact_records = artifact_records if isinstance(artifact_records, Mapping) else {}
        csr_root = manifest_path.parent.resolve()
        csr_artifacts_ok = True
        for name in ("indptr", "indices", "data"):
            item = artifact_records.get(name, {})
            item = item if isinstance(item, Mapping) else {}
            path = Path(str(item.get("path", ""))).resolve()
            if (
                not path.is_relative_to(csr_root)
                or not path.is_file()
                or path.stat().st_size != item.get("bytes")
                or _sha256_owned_payload(path) != item.get("sha256")
            ):
                csr_artifacts_ok = False
                break
        csr_metadata_ok = bool(
            manifest.get("schema") == "task40extra.review_v27_saved_q0_csr.v1"
            and manifest.get("status") == "COMPLETE_CSR"
            and manifest.get("shape") == [777_644, 777_644]
            and manifest.get("stored_structural_slots") == 577_061_168
            and manifest.get("q_map_count") == 1
            and manifest.get("q_map_branch") == 0
            and manifest.get("csr_index_dtype") == np.dtype(np.int32).str
            and manifest.get("csr_data_dtype") == np.dtype(np.complex128).str
            and manifest.get("saved_only_no_fe_or_native_rebuild") is True
            and manifest.get("row_count_witness_matches") is True
            and operation.get("csr_status") == "COMPLETE_CSR"
            and operation.get("complete_numeric_csr") is True
            and operation.get("stored_structural_slots") == 577_061_168
            and operation.get("csr_manifest_sha256") == _sha256_file(manifest_path)
            and operation.get("csr_manifest_path") == str(manifest_path)
        )
        checks["v27_complete_csr_identity_shape_and_payload_hashes"] = bool(
            csr_artifacts_ok and csr_metadata_ok
        )

        artifact = operation.get("csr_readback_artifact", {})
        artifact = artifact if isinstance(artifact, Mapping) else {}
        readback_ok = bool(
            artifact.get("path") == readback_path.name
            and readback_path.is_file()
            and readback_path.stat().st_size == artifact.get("bytes")
            and _sha256_owned_payload(readback_path) == artifact.get("sha256")
        )
        donor_artifacts = replay.get("artifacts", {})
        donor_artifacts = donor_artifacts if isinstance(donor_artifacts, Mapping) else {}
        input_record = donor_artifacts.get("inputs", {})
        input_record = input_record if isinstance(input_record, Mapping) else {}
        input_path = Path(str(input_record.get("path", ""))).resolve()
        case_records = donor.get("native_cases", {})
        case_records = case_records if isinstance(case_records, Mapping) else {}
        native1_record = case_records.get("q0_case_1", {})
        native2_record = case_records.get("q0_case_2", {})
        native1_record = native1_record if isinstance(native1_record, Mapping) else {}
        native2_record = native2_record if isinstance(native2_record, Mapping) else {}
        native1_path = Path(str(native1_record.get("path", ""))).resolve()
        native2_path = Path(str(native2_record.get("path", ""))).resolve()
        donor_inputs_ok = bool(
            input_path.is_file()
            and input_path.stat().st_size == input_record.get("bytes")
            and _sha256_owned_payload(input_path) == input_record.get("sha256")
            and native1_path.is_file()
            and native1_path.stat().st_size == native1_record.get("bytes")
            and _sha256_owned_payload(native1_path) == native1_record.get("sha256")
            and native2_path.is_file()
            and native2_path.stat().st_size == native2_record.get("bytes")
            and _sha256_owned_payload(native2_path) == native2_record.get("sha256")
        )
        if not (readback_ok and donor_inputs_ok):
            checks["v27_readback_raw_outputs_and_donor_cases_hash_bound"] = False
            checks["v27_four_csr_matvecs_recompute_native_total_and_components"] = False
            return checks
        with np.load(readback_path, allow_pickle=False) as archive:
            expected_output_names = {
                "q0_case_1_full",
                "q0_case_2_full",
                "q0_case_1_trace_only",
                "q0_case_1_port_only",
            }
            output_names_ok = set(archive.files) == expected_output_names
            outputs = {name: np.asarray(archive[name]) for name in expected_output_names}
        with np.load(input_path, allow_pickle=False) as archive:
            x1 = np.asarray(archive["q0_case_1"])
            x2 = np.asarray(archive["q0_case_2"])
        with np.load(native1_path, allow_pickle=False) as archive:
            component_names = {
                "native_q0_total", "native_q0_volume", "native_q0_C",
                "native_q0_minus_D", "native_q0_Hhat",
            }
            native1 = {name: np.asarray(archive[name]) for name in component_names}
        with np.load(native2_path, allow_pickle=False) as archive:
            native2_total = np.asarray(archive["native_q0_total"])
        q0_size = 777_644
        trace_rows = 773_568
        vectors_valid = bool(
            output_names_ok
            and all(
                value.shape == (q0_size,)
                and value.dtype == np.dtype(np.complex128)
                and np.isfinite(value).all()
                for value in (*outputs.values(), x1, x2, *native1.values(), native2_total)
            )
            and np.any(x1 != 0.0)
            and np.any(x2 != 0.0)
            and not np.array_equal(x1, x2)
        )

        def relative_error(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
            absolute = float(np.linalg.norm(left - right))
            scale = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), np.finfo(float).tiny)
            return {"absolute": absolute, "scale": scale, "relative": absolute / scale}

        total1 = relative_error(outputs["q0_case_1_full"], native1["native_q0_total"])
        total2 = relative_error(outputs["q0_case_2_full"], native2_total)
        split = relative_error(
            outputs["q0_case_1_trace_only"] + outputs["q0_case_1_port_only"],
            outputs["q0_case_1_full"],
        )
        native_components = {
            "volume": (outputs["q0_case_1_trace_only"][:trace_rows], native1["native_q0_volume"][:trace_rows], native1["native_q0_volume"][trace_rows:]),
            "minus_D": (outputs["q0_case_1_trace_only"][trace_rows:], native1["native_q0_minus_D"][trace_rows:], native1["native_q0_minus_D"][:trace_rows]),
            "C": (outputs["q0_case_1_port_only"][:trace_rows], native1["native_q0_C"][:trace_rows], native1["native_q0_C"][trace_rows:]),
            "Hhat": (outputs["q0_case_1_port_only"][trace_rows:], native1["native_q0_Hhat"][trace_rows:], native1["native_q0_Hhat"][:trace_rows]),
        }
        component_ok = all(
            relative_error(actual, expected)["relative"] <= 1.0e-11
            and float(np.linalg.norm(off_block))
            / max(float(np.linalg.norm(native1[f"native_q0_{'minus_D' if name == 'minus_D' else name}"])), np.finfo(float).tiny)
            <= 1.0e-11
            for name, (actual, expected, off_block) in native_components.items()
        )
        recorded = operation.get("csr_readback", {})
        recorded = recorded if isinstance(recorded, Mapping) else {}
        checks["v27_readback_raw_outputs_and_donor_cases_hash_bound"] = bool(readback_ok and donor_inputs_ok)
        checks["v27_four_csr_matvecs_recompute_native_total_and_components"] = bool(
            vectors_valid
            and total1["relative"] <= 1.0e-11
            and total2["relative"] <= 1.0e-11
            and split["relative"] <= 1.0e-11
            and component_ok
            and recorded.get("all_gates_passed") is True
            and recorded.get("full_csr_multiply_count") == 4
            and recorded.get("no_second_adapter_contribution_pass") is True
        )
        checks["v27_factor_status_does_not_erase_complete_csr"] = bool(
            status in {
                "PASS_COMPLETE_Q0_CSR",
                "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
                "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR",
                "FAILED_Q0_FACTOR_LIFECYCLE",
            }
            and partial.get("q_coverage", {}).get("built_q_count") == 1
            and partial.get("q_coverage", {}).get("full_q_matrix_coverage") == "1/8"
        )
    except Exception:
        checks["v27_readback_raw_outputs_and_donor_cases_hash_bound"] = False
        checks["v27_four_csr_matvecs_recompute_native_total_and_components"] = False
    return checks


def _v28_saved_q0_continuation_checks(
    *,
    output_directory: Path,
    partial: Mapping[str, Any],
    expected_stop_stage: str,
    path_resolver: Callable[[str | Path], Path] | None = None,
    expected_pattern_path: Path | None = None,
    expected_qualification_path: Path | None = None,
    artifact_hashes: dict[str, str] | None = None,
) -> dict[str, bool]:
    """Classify V28 in-progress cutoffs and verify reused/complete CSR identities."""
    checks: dict[str, bool] = {}
    stage = partial.get("v28_q0_continuation", {})
    stage = stage if isinstance(stage, Mapping) else {}
    operation = stage.get("operation", {})
    operation = operation if isinstance(operation, Mapping) else {}
    status = str(operation.get("status", ""))
    operation_path = output_directory / str(stage.get("operation_path", ""))
    selector_path = (
        path_resolver(stage.get("selector_path", ""))
        if path_resolver is not None
        else Path(str(stage.get("selector_path", ""))).resolve()
    )
    raw_manifest_path = operation.get(
        "csr_manifest_path", operation.get("continuation_manifest_path", "")
    )
    manifest_path = (
        path_resolver(raw_manifest_path)
        if path_resolver is not None
        else Path(str(raw_manifest_path)).resolve()
    )
    pattern_path = (
        expected_pattern_path.resolve()
        if expected_pattern_path is not None
        else (ROOT / V28_PATTERN_MANIFEST_RELATIVE).resolve()
    )
    try:
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
        pattern = json.loads(pattern_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        selector_sha = _sha256_file(selector_path)
        if artifact_hashes is not None:
            artifact_hashes.update(
                {
                    "v28_selector": selector_sha,
                    "v28_pattern_manifest": _sha256_file(pattern_path),
                }
            )
        donor = operation.get("donor_import_identity", {})
        donor = donor if isinstance(donor, Mapping) else {}
        inventory = operation.get("saved_only_preflight", {})
        inventory = inventory if isinstance(inventory, Mapping) else {}
        execution = operation.get("current_execution_identity", {})
        execution = execution if isinstance(execution, Mapping) else {}
        donor_sha = hashlib.sha256(
            json.dumps(donor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        checks["v28_selector_current_window_and_donor_bind"] = bool(
            selector.get("schema") == "task40extra.review_v28_q0_continuation_operation.v1"
            and selector.get("operation") == V28_CONTINUATION_OPERATION
            and selector.get("stop_stage") == expected_stop_stage
            and selector.get("campaign_window_sha256") == TASK40_V28_CAMPAIGN_SHA256
            and selector.get("donor_import") == donor
            and stage.get("selector_sha256") == operation.get("selector_sha256") == selector_sha
            and stage.get("donor_import_identity_sha256") == operation.get("donor_import_identity_sha256") == donor_sha
            and execution.get("campaign_window_sha256") == TASK40_V28_CAMPAIGN_SHA256
        )
        checks["v28_selector_manifest_state_dispatch_policy_bound"] = bool(
            selector.get("continuation_policy") == V28_CONTINUATION_POLICY
        )
        checks["v28_operation_receipt_hash_bound"] = bool(
            operation.get("schema") == "task40extra.review_v28_q0_continuation_stage.v1"
            and operation.get("operation") == V28_CONTINUATION_OPERATION
            and operation.get("stop_stage") == expected_stop_stage
            and operation_path.is_file()
            and operation_path.resolve().is_relative_to(output_directory.resolve())
            and stage.get("operation_sha256") == _sha256_file(operation_path)
            and operation.get("official_result") is False
            and operation.get("saved_only_no_fe_or_native_rebuild") is True
        )
        checks["v28_campaign_window_registration_and_pattern_freeze_bind"] = bool(
            (
                path_resolver(selector.get("pattern_manifest_path", ""))
                if path_resolver is not None
                else Path(str(selector.get("pattern_manifest_path", ""))).resolve()
            ) == pattern_path
            and selector.get("pattern_manifest_sha256") == V28_PATTERN_MANIFEST_SHA256
            and pattern_path.is_file()
            and _sha256_file(pattern_path) == V28_PATTERN_MANIFEST_SHA256
            and pattern.get("status") == "NUMERIC_FILL_INCOMPLETE"
            and partial.get("official_result") is False
        )
        checks["v28_original_v27_manifest_unchanged_and_pattern_reused"] = bool(
            pattern_path == (ROOT / V28_PATTERN_MANIFEST_RELATIVE).resolve()
            and pattern.get("schema") == "task40extra.review_v27_saved_q0_csr.v1"
            and operation.get("source_pattern_reused") is True
            and operation.get("pattern_manifest_sha256") == V28_PATTERN_MANIFEST_SHA256
            and manifest.get("schema") == "task40extra.review_v28_saved_q0_csr.v1"
            and manifest.get("original_pattern_manifest", {}).get("sha256") == V28_PATTERN_MANIFEST_SHA256
            and manifest.get("continuation_event", {}).get("old_manifest_modified") is False
            and manifest.get("continuation_event", {}).get("full_csr_copy_created") is False
            and manifest.get("continuation_event", {}).get("data_restart_policy")
            == "clear_all_values_before_each_numeric_pass"
        )
        progress_path = output_directory / "v28_q0_numeric_progress.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {}
        count_map = progress.get("completed_work_items_by_component", {})
        expected_map = progress.get("expected_work_items_by_component", {})
        count_values = [int(count_map.get(name, -1)) for name in ("Hhat", "volume", "surface")]
        expected_values = [int(expected_map.get(name, -1)) for name in ("Hhat", "volume", "surface")]
        progress_ok = bool(
            progress.get("schema") == "task40extra.review_v28_q0_numeric_progress.v1"
            and progress.get("restart_policy") == "clear_all_values_before_each_numeric_pass; progress_is_not_a_cursor"
            and progress.get("progress_is_not_a_restart_cursor") is True
            and all(value >= 0 for value in count_values)
            and all(value >= count for value, count in zip(expected_values, count_values, strict=True))
            and progress.get("completed_contribution_count") == sum(count_values)
            and (sum(count_values) == 0 or isinstance(progress.get("last_completed_label"), str))
            and isinstance(progress.get("resource_gate_records"), list)
            and isinstance(progress.get("component_parent_wall_seconds"), Mapping)
            and isinstance(progress.get("component_child_seconds"), Mapping)
            and progress.get("read_and_constraint_split") is not None
            and "task_cgroup_anon_bytes" in progress
            and "task_cgroup_file_bytes" in progress
            and "task_cgroup_file_dirty_bytes" in progress
            and "data_zero_and_flush_seconds" in progress
            and "data_hash_seconds" in progress
        )
        manifest_status = manifest.get("status")
        if status.endswith("_IN_PROGRESS"):
            checks["v28_cutoff_partial_progress_is_classified_without_claiming_completion"] = bool(
                partial.get("status") == "in_progress"
                and partial.get("outcome") == "IN_PROGRESS"
                and partial.get("completed_stages")
                == (["preflight", expected_stop_stage] if manifest_status == "COMPLETE_CSR" else ["preflight"])
                and partial.get("q_coverage", {}).get("built_q_count")
                == int(manifest_status == "COMPLETE_CSR")
                and progress_ok
                and manifest_status in {
                    "STRUCTURE_COMPLETE_VALUES_PENDING",
                    "NUMERIC_FILL_INCOMPLETE",
                    "COMPLETE_CSR",
                }
                and operation.get("complete_numeric_csr") is (manifest_status == "COMPLETE_CSR")
            )
        else:
            checks["v28_progress_receipt_schema_and_success_only_counts"] = bool(
                progress_ok
                or progress.get("status") in {"NUMERIC_FILL_COMPLETED", "READBACK_IN_PROGRESS"}
                or not progress_path.exists() and status.startswith("PASS_COMPLETE_Q0_CSR")
            )
        csr_hashes_ok = False
        csr_artifacts = manifest.get("csr_artifacts", {})
        if isinstance(csr_artifacts, Mapping) and manifest_status == "COMPLETE_CSR":
            csr_hashes_ok = True
            for name in ("indptr", "indices", "data"):
                record = csr_artifacts.get(name, {})
                record = record if isinstance(record, Mapping) else {}
                path = (
                    path_resolver(record.get("path", ""))
                    if path_resolver is not None
                    else Path(str(record.get("path", ""))).resolve()
                )
                if (
                    not path.is_relative_to(manifest_path.parent.resolve())
                    or not path.is_file()
                    or path.stat().st_size != record.get("bytes")
                ):
                    csr_hashes_ok = False
                    break
                actual_hash = _sha256_owned_payload(path)
                if artifact_hashes is not None:
                    artifact_hashes[f"v28_csr_{name}"] = actual_hash
                if actual_hash != record.get("sha256"):
                    csr_hashes_ok = False
                    break
        checks["v28_complete_csr_requires_all_three_payload_hashes"] = bool(
            (manifest_status != "COMPLETE_CSR" and not operation.get("complete_numeric_csr"))
            or (
                csr_hashes_ok
                and operation.get("complete_numeric_csr") is True
                and operation.get("csr_status") == "COMPLETE_CSR"
                and operation.get("csr_manifest_sha256") == _sha256_file(manifest_path)
            )
        )
        qualification_binding = None
        if manifest_status == "COMPLETE_CSR" and manifest.get("native_qualification"):
            from src.runners.task40_v20_stage_runner import _load_matching_v28_native_qualification

            qualification_binding = _load_matching_v28_native_qualification(
                repo_root=ROOT,
                manifest_path=manifest_path,
                manifest=manifest,
                expected_pattern_path=pattern_path,
                expected_pattern_sha256=V28_PATTERN_MANIFEST_SHA256,
                donor_identity_sha256=donor_sha,
                input_sha256=str(partial.get("input_sha256", "")),
                physical_model_sha256=str(partial.get("physical_model_sha256", "")),
                run_id=str(partial.get("run_id", "")),
                campaign_window_sha256=TASK40_V28_CAMPAIGN_SHA256,
                mode_manifest_sha256=str(execution.get("mode_manifest_sha256", "")),
                ordered_mode_key_sha256=str(execution.get("ordered_mode_key_sha256", "")),
                sha256_file=_sha256_file,
                path_resolver=path_resolver,
            )
        checks["v28_native_qualification_remains_bound_to_complete_csr"] = bool(
            manifest_status != "COMPLETE_CSR"
            or not manifest.get("native_qualification")
            or (
                qualification_binding is not None
                and (
                    expected_qualification_path is None
                    or qualification_binding[0] == expected_qualification_path
                )
            )
        )
        if qualification_binding is not None:
            qpath, qualification = qualification_binding
            if artifact_hashes is not None:
                artifact_hashes["v28_native_qualification"] = _sha256_file(qpath)
            operation_qualification = operation.get("native_qualification_receipt", {})
            operation_qualification = operation_qualification if isinstance(operation_qualification, Mapping) else {}
            operation_qualification_path = (
                path_resolver(operation_qualification.get("path", ""))
                if path_resolver is not None
                else Path(str(operation_qualification.get("path", ""))).resolve()
            )
            checks["v28_native_pass_receipt_keeps_old_source_window_and_current_factor_identity"] = bool(
                operation.get("native_readback_skipped") is not True
                or (
                    operation_qualification_path == qpath
                    and operation_qualification.get("sha256") == _sha256_file(qpath)
                    and operation.get("native_qualification_original_source_identity")
                    == qualification.get("source_identity")
                    and operation.get("factor_execution_identity", {}).get("source_sha")
                    == operation.get("current_execution_identity", {}).get("source_sha")
                    and operation.get("factor_execution_identity", {}).get("campaign_window_sha256")
                    == TASK40_V28_CAMPAIGN_SHA256
                )
            )
    except Exception:
        return {**checks, "v28_continuation_evidence_readable": False}
    return checks


def _check_partial_result(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_output: Path,
    expected_stop_stage: str,
) -> dict[str, Any]:
    """Check a raw stage footer; explicitly never promote it to a full result."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _, input_data = _read_case(input_path)
    profile_identity = str(input_data.get("solver", {}).get("preconditioner", ""))
    expected_q_count = _profile_q_count(profile_identity)
    v31_binding = manifest.get("v31_execution_contract_binding")
    v31_binding = v31_binding if isinstance(v31_binding, Mapping) else None
    v31_input_identity = None
    v31_input_identity_error = None
    v30_input_identity = None
    v30_input_identity_error = None
    if profile_identity == V30_TARGET_PROFILE and v31_binding is not None:
        try:
            from src.runners.task40_v30_contract import (
                V30_CANONICAL_INPUT_RELATIVE,
            )
            from src.runners.task40_v31_contract import (
                bind_v32_q4_pending_import,
                require_v31_execution_contract,
                require_v31_input_identity,
                v32_q4_pending_import_template,
            )

            selector_sha = v31_binding.get("selector_sha256")
            selector_value = v31_binding.get("selector_path")
            if not isinstance(selector_value, str) or not isinstance(selector_sha, str):
                raise ValueError("V31 manifest binding omits its selector path or SHA")
            selector_path = Path(selector_value)
            if not selector_path.is_absolute():
                selector_path = ROOT / selector_path
            selector_path = selector_path.resolve(strict=True)
            if _sha256_file(selector_path) != selector_sha:
                raise ValueError("V31 selector bytes differ from the recorded selector SHA")
            q4_import_template = None
            if v31_binding.get("review_version") == "V32":
                contract_path_text = os.environ.get("TASK40_V31_CONTRACT_PATH", "")
                contract_sha256 = os.environ.get("TASK40_V31_CONTRACT_SHA256", "")
                if not contract_path_text or not contract_sha256:
                    raise ValueError("V32 partial checker requires the current approved execution contract")
                contract_path = Path(contract_path_text).resolve(strict=True)
                contract, contract_sha = require_v31_execution_contract(
                    contract_path,
                    expected_sha256=contract_sha256,
                    current_root=ROOT,
                )
                source_sha = str(manifest.get("source_sha", ""))
                window_sha256 = str(contract.get("execution", {}).get("window", {}).get("window_sha256", ""))
                expected_template = v32_q4_pending_import_template(
                    execution_root=ROOT,
                    consumer_source_sha=source_sha,
                )
                expected_authorization = bind_v32_q4_pending_import(
                    expected_template,
                    consumer_execution_identity={
                        "source_sha": source_sha,
                        "window_sha256": window_sha256,
                    },
                )
                execution = contract.get("execution", {})
                if (
                    v31_binding.get("contract_path") != str(contract_path)
                    or v31_binding.get("contract_sha256") != contract_sha
                    or v31_binding.get("run_source_sha") != source_sha
                    or v31_binding.get("execution_window_sha256") != window_sha256
                    or v31_binding.get("q4_numeric_pending_import_template") != expected_template
                    or v31_binding.get("q4_numeric_pending_import_authorization") != expected_authorization
                    or contract.get("preparation", {}).get("q4_numeric_pending_import") != expected_template
                    or execution.get("q_csr_import_authorizations")
                    != {"numeric_pending": {"4": expected_authorization}}
                ):
                    raise ValueError("V32 q4 import binding differs from the current approved contract or fixed old source")
                q4_import_template = expected_template
            elif (
                v31_binding.get("q4_numeric_pending_import_template") is not None
                or v31_binding.get("q4_numeric_pending_import_authorization") is not None
            ):
                raise ValueError("V31 worker manifest carries an unregistered V32 q4 import")
            v31_input_identity = require_v31_input_identity(
                ROOT / V30_CANONICAL_INPUT_RELATIVE,
                input_path,
                repo_root=ROOT,
                source_sha=str(manifest.get("source_sha", "")),
                selector_sha256=selector_sha,
                q4_numeric_pending_import=q4_import_template,
            )
        except Exception as error:
            v31_input_identity_error = f"{type(error).__name__}: {error}"
    elif profile_identity == V30_TARGET_PROFILE:
        try:
            from src.runners.task40_v30_contract import (
                V30_CANONICAL_INPUT_RELATIVE,
                require_v30_input_identity,
            )

            v30_input_identity = require_v30_input_identity(
                ROOT / V30_CANONICAL_INPUT_RELATIVE,
                input_path,
                repo_root=ROOT,
            )
        except Exception as error:
            v30_input_identity_error = f"{type(error).__name__}: {error}"
    partial_path = numerical_output / "v20_partial_result.json"
    if not partial_path.is_file():
        return {
            "schema": "task40extra.review_v20_partial_stage_checker.v1",
            "status": "NO_PARTIAL_FOOTER",
            "checker_passed": False,
            "official_result": False,
            "full_pass": False,
            "run_summary_result_classification": run_summary.get("result_classification"),
            "run_summary_path": str(summary_path),
            "raw_output_directory": str(numerical_output),
            "error": "no official packet or V20 partial footer exists; preserve run/watchdog raw evidence",
        }
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    v29_context = None
    v29_context_error = None
    if os.environ.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1":
        try:
            v29_context = _v29_partial_checker_context(
                input_path=input_path,
                summary_path=summary_path,
                manifest_path=manifest_path,
                numerical_output=numerical_output,
                manifest=manifest,
                run_summary=run_summary,
                partial=partial,
            )
        except Exception as error:
            v29_context_error = f"{type(error).__name__}: {error}"
    campaign_evidence = manifest.get("task40_v20_campaign")
    campaign_evidence = campaign_evidence if isinstance(campaign_evidence, dict) else {}
    probe_identity = partial.get("target_operator_probe")
    probe_identity = probe_identity if isinstance(probe_identity, dict) else {}
    v23_expected_window = (ROOT / TASK40_V23_CAMPAIGN_WINDOW).resolve()
    v23_expected_accounting = v23_expected_window.with_name("campaign_accounting_v10.jsonl")
    v24_expected_window = (ROOT / TASK40_V24_CAMPAIGN_WINDOW).resolve()
    v24_expected_accounting = v24_expected_window.with_name("campaign_accounting_v10.jsonl")
    v25_expected_window = (ROOT / TASK40_V25_CAMPAIGN_WINDOW).resolve()
    v25_expected_accounting = v25_expected_window.with_name("campaign_accounting_v10.jsonl")
    v26_expected_window = (ROOT / TASK40_V26_CAMPAIGN_WINDOW).resolve()
    v26_expected_accounting = v26_expected_window.with_name("campaign_accounting_v10.jsonl")
    v27_expected_window = (ROOT / TASK40_V27_CAMPAIGN_WINDOW).resolve()
    v27_expected_accounting = v27_expected_window.with_name("campaign_accounting_v10.jsonl")
    v28_expected_window = (ROOT / TASK40_V28_CAMPAIGN_WINDOW).resolve()
    v28_expected_accounting = v28_expected_window.with_name("campaign_accounting_v10.jsonl")
    q_only_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and partial.get("classification") == "TARGET_OPERATOR_PROBE_Q_ONLY_SUPPLEMENT"
    )
    v24_cd_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and partial.get("classification")
        in {
            "TARGET_OPERATOR_PROBE_V24_BOUNDED_PORT_REUSE_VOLUME_SAMPLE",
            "TARGET_OPERATOR_PROBE_V24_REAL_EDGE_VOLUME_PANEL",
        }
    )
    v25_volume_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and partial.get("classification")
        in {
            "TARGET_OPERATOR_PROBE_V25_COMPLETE_TARGET_VOLUME_ACTION",
            "TARGET_OPERATOR_PROBE_V25_COMPLETE_TARGET_VOLUME_ACTION_FAILED",
        }
    )
    v25_q0_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and expected_stop_stage in V25_SELECTED_Q_STAGES
        and isinstance(partial.get("selected_reference_q0_consumer"), Mapping)
    )
    v26_q_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and expected_stop_stage in V26_SELECTED_Q_STAGES
        and isinstance(partial.get("v26_selected_q_stage"), Mapping)
    )
    v27_q_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and expected_stop_stage in V27_SELECTED_Q_STAGES
        and isinstance(partial.get("v27_saved_q0_stage"), Mapping)
    )
    v28_q_receipt = (
        partial.get("schema") == "task40extra.review_v20_partial_result.v2"
        and expected_stop_stage in V28_SELECTED_Q_STAGES
        and isinstance(partial.get("v28_q0_continuation"), Mapping)
    )
    q_only_supplement_identity = partial.get("q_only_supplement")
    q_only_supplement_identity = (
        q_only_supplement_identity
        if isinstance(q_only_supplement_identity, dict)
        else {}
    )
    v23_identity_claimed = (
        probe_identity.get("schema")
        == "task40extra.review_v23_compact_boundary_operator_probe.v1"
        or campaign_evidence.get("window_sha256") == TASK40_V23_CAMPAIGN_SHA256
        or campaign_evidence.get("window_path") == str(v23_expected_window)
    )
    v23_campaign_identity_valid = (
        campaign_evidence.get("window_sha256") == TASK40_V23_CAMPAIGN_SHA256
        and Path(str(campaign_evidence.get("window_path", ""))).resolve()
        == v23_expected_window
        and Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
        == v23_expected_accounting
        and v23_expected_window.is_file()
        and _sha256_file(v23_expected_window) == TASK40_V23_CAMPAIGN_SHA256
        and v23_expected_accounting.is_file()
    )
    v24_identity_claimed = (
        probe_identity.get("schema")
        == "task40extra.review_v24_compact_boundary_operator_probe.v1"
        or campaign_evidence.get("window_sha256") == TASK40_V24_CAMPAIGN_SHA256
        or campaign_evidence.get("window_path") == str(v24_expected_window)
        or (
            q_only_receipt
            and q_only_supplement_identity.get("execution_campaign_window_sha256")
            == TASK40_V24_CAMPAIGN_SHA256
        )
        or v24_cd_receipt
    )
    v24_campaign_identity_valid = (
        campaign_evidence.get("window_sha256") == TASK40_V24_CAMPAIGN_SHA256
        and Path(str(campaign_evidence.get("window_path", ""))).resolve()
        == v24_expected_window
        and Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
        == v24_expected_accounting
        and v24_expected_window.is_file()
        and _sha256_file(v24_expected_window) == TASK40_V24_CAMPAIGN_SHA256
        and v24_expected_accounting.is_file()
        and (ROOT / TASK40_V24_CAMPAIGN_RECEIPT).is_file()
        and _sha256_file(ROOT / TASK40_V24_CAMPAIGN_RECEIPT)
        == TASK40_V24_CAMPAIGN_RECEIPT_SHA256
    )
    v25_identity_claimed = (
        probe_identity.get("schema") == "task40extra.review_v25_target_operator_probe.v1"
        or campaign_evidence.get("window_sha256") == TASK40_V25_CAMPAIGN_SHA256
        or campaign_evidence.get("window_path") == str(v25_expected_window)
        or v25_volume_receipt
    )
    v26_identity_claimed = (
        probe_identity.get("schema") == "task40extra.review_v26_selected_q_stage.v1"
        or campaign_evidence.get("window_sha256") == TASK40_V26_CAMPAIGN_SHA256
        or campaign_evidence.get("window_path") == str(v26_expected_window)
        or v26_q_receipt
    )
    v27_stage = partial.get("v27_saved_q0_stage", {})
    v27_stage = v27_stage if isinstance(v27_stage, Mapping) else {}
    v27_operation = v27_stage.get("operation", {})
    v27_operation = v27_operation if isinstance(v27_operation, Mapping) else {}
    v27_identity_claimed = (
        v27_operation.get("schema") == "task40extra.review_v27_saved_q0_stage.v1"
        or campaign_evidence.get("window_sha256") == TASK40_V27_CAMPAIGN_SHA256
        or campaign_evidence.get("window_path") == str(v27_expected_window)
        or v27_q_receipt
    )
    v28_stage = partial.get("v28_q0_continuation", {})
    v28_stage = v28_stage if isinstance(v28_stage, Mapping) else {}
    v28_operation = v28_stage.get("operation", {})
    v28_operation = v28_operation if isinstance(v28_operation, Mapping) else {}
    v28_identity_claimed = (
        v28_operation.get("schema") == "task40extra.review_v28_q0_continuation_stage.v1"
        or campaign_evidence.get("window_sha256") == TASK40_V28_CAMPAIGN_SHA256
        or campaign_evidence.get("window_path") == str(v28_expected_window)
        or v28_q_receipt
    )
    v25_controlled_stop_receipt = bool(
        v25_identity_claimed
        and partial.get("status") == "controlled_stop"
        and partial.get("outcome") == "RESOURCE_CONTROLLED_STOP"
        and expected_stop_stage == "target_operator_probe"
    )
    v25_campaign_identity_valid = (
        campaign_evidence.get("window_sha256") == TASK40_V25_CAMPAIGN_SHA256
        and Path(str(campaign_evidence.get("window_path", ""))).resolve()
        == v25_expected_window
        and Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
        == v25_expected_accounting
        and v25_expected_window.is_file()
        and _sha256_file(v25_expected_window) == TASK40_V25_CAMPAIGN_SHA256
        and v25_expected_accounting.is_file()
        and (ROOT / TASK40_V25_CAMPAIGN_RECEIPT).is_file()
        and _sha256_file(ROOT / TASK40_V25_CAMPAIGN_RECEIPT)
        == TASK40_V25_CAMPAIGN_RECEIPT_SHA256
    )
    v26_campaign_identity_valid = (
        campaign_evidence.get("window_sha256") == TASK40_V26_CAMPAIGN_SHA256
        and Path(str(campaign_evidence.get("window_path", ""))).resolve()
        == v26_expected_window
        and Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
        == v26_expected_accounting
        and v26_expected_window.is_file()
        and _sha256_file(v26_expected_window) == TASK40_V26_CAMPAIGN_SHA256
        and v26_expected_accounting.is_file()
        and (ROOT / TASK40_V26_CAMPAIGN_RECEIPT).is_file()
        and _sha256_file(ROOT / TASK40_V26_CAMPAIGN_RECEIPT)
        == TASK40_V26_CAMPAIGN_RECEIPT_SHA256
    )
    v27_campaign_identity_valid = (
        campaign_evidence.get("window_sha256") == TASK40_V27_CAMPAIGN_SHA256
        and Path(str(campaign_evidence.get("window_path", ""))).resolve()
        == v27_expected_window
        and Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
        == v27_expected_accounting
        and v27_expected_window.is_file()
        and _sha256_file(v27_expected_window) == TASK40_V27_CAMPAIGN_SHA256
        and v27_expected_accounting.is_file()
        and (ROOT / TASK40_V27_CAMPAIGN_RECEIPT).is_file()
        and _sha256_file(ROOT / TASK40_V27_CAMPAIGN_RECEIPT)
        == TASK40_V27_CAMPAIGN_RECEIPT_SHA256
    )
    v28_campaign_identity_valid = (
        campaign_evidence.get("window_sha256") == TASK40_V28_CAMPAIGN_SHA256
        and Path(str(campaign_evidence.get("window_path", ""))).resolve()
        == v28_expected_window
        and Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
        == v28_expected_accounting
        and v28_expected_window.is_file()
        and _sha256_file(v28_expected_window) == TASK40_V28_CAMPAIGN_SHA256
        and v28_expected_accounting.is_file()
        and (ROOT / TASK40_V28_CAMPAIGN_RECEIPT).is_file()
        and _sha256_file(ROOT / TASK40_V28_CAMPAIGN_RECEIPT)
        == TASK40_V28_CAMPAIGN_RECEIPT_SHA256
    )
    expected_completed = STAGE_PREFIXES.get(expected_stop_stage)
    v2_receipt = partial.get("schema") == "task40extra.review_v20_partial_result.v2"
    if v27_q_receipt or v28_q_receipt:
        expected_completed = None
    if v2_receipt and expected_stop_stage in {
        "target_operator_probe", "build_and_symbolic", "one_q_numeric"
    }:
        expected_completed = None
    if expected_stop_stage == "full" and manifest.get("mesh_id") == "TARGET_ORIGINAL_NY8":
        expected_completed = ["preflight"]
    actual_completed = partial.get("completed_stages")
    expected_completed_for_failure = None
    failed_stage = partial.get("failed_stage")
    if v26_q_receipt and partial.get("status") == "controlled_stop":
        v26_stage_receipt = partial.get("v26_selected_q_stage", {})
        v26_stage_receipt = v26_stage_receipt if isinstance(v26_stage_receipt, Mapping) else {}
        v26_operation_status = str(v26_stage_receipt.get("operation_status", ""))
        if (
            expected_stop_stage == "selected_reference_q_csr"
            and v26_operation_status == "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT"
        ):
            expected_completed = ["preflight", "selected_reference_q_consumer"]
        else:
            expected_completed = ["preflight"]
    elif v26_q_receipt and partial.get("status") == "failed":
        expected_completed = ["preflight"]
        expected_completed_for_failure = ["preflight"]
    if (
        partial.get("status") == "failed"
        and isinstance(expected_completed, list)
        and isinstance(failed_stage, str)
        and failed_stage in expected_completed
    ):
        failed_index = expected_completed.index(failed_stage)
        expected_completed_for_failure = expected_completed[:failed_index]
    checks = {
        "run_id_matches": partial.get("run_id") == manifest.get("run_id"),
        "source_sha_matches": partial.get("source_sha") == manifest.get("source_sha"),
        "input_sha_matches": partial.get("input_sha256") == manifest.get("input_sha256"),
        "physical_model_sha_matches": partial.get("physical_model_sha256")
        == manifest.get("physical_model_sha256"),
        "requested_stage_matches": partial.get("requested_stop_stage") == expected_stop_stage,
        "official_result_false": partial.get("official_result") is False,
        "completed_stages_expected": (
            expected_completed is None
            or actual_completed == expected_completed
            or (
                expected_completed_for_failure is not None
                and actual_completed == expected_completed_for_failure
            )
        ),
        "failure_stage_is_next_incomplete_stage": (
            expected_completed_for_failure is None
            or failed_stage
            == expected_completed[len(expected_completed_for_failure)]
        ),
    }
    if profile_identity == V30_TARGET_PROFILE and v31_binding is not None:
        recorded_identity = manifest.get("v31_input_identity")
        binding_identity = v31_binding.get("input_identity")
        selector_path = v31_binding.get("selector_path")
        selector_sha = v31_binding.get("selector_sha256")
        checks.update(
            {
                "v31_canonical_staged_input_revalidated": v31_input_identity is not None,
                "v31_raw_stage_and_scientific_identity_match": bool(
                    v31_input_identity is not None
                    and isinstance(recorded_identity, Mapping)
                    and isinstance(binding_identity, Mapping)
                    and recorded_identity == v31_input_identity
                    and binding_identity == v31_input_identity
                    and manifest.get("input_sha256")
                    == v31_input_identity["staged_input_sha256"]
                    and partial.get("input_sha256")
                    == v31_input_identity["staged_input_sha256"]
                    and manifest.get("scientific_input_sha256")
                    == v31_input_identity["scientific_input_sha256"]
                    and v31_binding.get("run_source_sha")
                    == manifest.get("source_sha")
                    and v31_input_identity.get("source_sha")
                    == manifest.get("source_sha")
                    and isinstance(selector_path, str)
                    and isinstance(selector_sha, str)
                ),
                "v31_input_identity_error_absent": v31_input_identity_error is None,
            }
        )
    elif profile_identity == V30_TARGET_PROFILE:
        recorded_identity = manifest.get("v30_input_identity")
        contract_binding = manifest.get("v30_execution_contract_binding", {})
        contract_identity = (
            contract_binding.get("input_identity", {})
            if isinstance(contract_binding, Mapping)
            else {}
        )
        checks.update(
            {
                "v30_canonical_input_revalidated": v30_input_identity is not None,
                "v30_raw_stage_sha_matches_manifest": bool(
                    v30_input_identity is not None
                    and manifest.get("input_sha256") == v30_input_identity["staged_input_sha256"]
                    and manifest.get("canonical_input_sha256") == v30_input_identity["canonical_input_sha256"]
                ),
                "v30_scientific_input_sha_matches_canonical": bool(
                    v30_input_identity is not None
                    and manifest.get("scientific_input_sha256")
                    == v30_input_identity["scientific_input_sha256"]
                ),
                "v30_service_identity_matches_checker": bool(
                    v30_input_identity is not None
                    and recorded_identity == v30_input_identity
                    and contract_identity == v30_input_identity
                ),
                "v30_identity_error_absent": v30_input_identity_error is None,
            }
        )
    if v23_identity_claimed:
        checks["v23_manifest_campaign_window_and_accounting_bind"] = (
            v23_campaign_identity_valid
        )
    if v24_identity_claimed:
        checks["v24_execution_manifest_window_and_accounting_bind"] = (
            v24_campaign_identity_valid
        )
    if v25_identity_claimed:
        checks["v25_execution_manifest_window_accounting_and_registration_bind"] = (
            v25_campaign_identity_valid
        )
    if v26_identity_claimed:
        checks["v26_execution_manifest_window_accounting_and_registration_bind"] = (
            v26_campaign_identity_valid
        )
    if v27_identity_claimed:
        checks["v27_execution_manifest_window_accounting_and_registration_bind"] = (
            v27_campaign_identity_valid
        )
    if v28_identity_claimed and os.environ.get("TASK40_V29_STRICT_FACTOR_ONLY") != "1":
        checks["v28_execution_manifest_window_accounting_and_registration_bind"] = (
            v28_campaign_identity_valid
        )
    if expected_stop_stage in {"build_and_symbolic", "one_q_numeric"} and not v2_receipt:
        checks["target_heavy_authorization_remains_false"] = (
            input_data.get("execution", {}).get("task40_target_heavy_authorized") is False
        )
    if (
        v2_receipt
        and not q_only_receipt
        and not v24_cd_receipt
        and not v25_volume_receipt
        and not v25_q0_receipt
        and not v26_q_receipt
        and not v27_q_receipt
        and not v28_q_receipt
        and not v25_controlled_stop_receipt
    ):
        from scripts.task40_v21_readonly_recheck import validate_stage_receipt_semantics

        semantic_checks = validate_stage_receipt_semantics(
            partial,
            expected_stage=expected_stop_stage,
            heavy_authorized=input_data.get("execution", {}).get(
                "task40_target_heavy_authorized"
            ),
            output_directory=numerical_output,
            operator_probe_authorized=input_data.get("execution", {}).get(
                "task40_v22_operator_probe_authorized"
            ),
            expected_q_count=expected_q_count,
            expected_campaign_window_sha256=(
                TASK40_V24_CAMPAIGN_SHA256
                if v24_identity_claimed
                else TASK40_V25_CAMPAIGN_SHA256
                if v25_identity_claimed
                else TASK40_V23_CAMPAIGN_SHA256
                if v23_identity_claimed
                else None
            ),
        )
        checks.update({f"stage_semantics_{name}": passed for name, passed in semantic_checks.items()})
    elif q_only_receipt:
        supplement = partial.get("q_only_supplement")
        supplement = supplement if isinstance(supplement, dict) else {}
        supplement_path = numerical_output / "v23_q_only_supplement.json"
        tile_path = numerical_output / "v23_reference_q_port_tile.json"
        supplement_disk = (
            json.loads(supplement_path.read_text(encoding="utf-8"))
            if supplement_path.is_file()
            else {}
        )
        tile = json.loads(tile_path.read_text(encoding="utf-8")) if tile_path.is_file() else {}
        tile_inner = tile.get("q_tile", {})
        tile_inner = tile_inner if isinstance(tile_inner, dict) else {}
        from scripts.task40_v21_readonly_recheck import (
            _v23_projection_readback_valid,
            _v23_q_contribution_checks,
        )

        raw_contribution_checks = _v23_q_contribution_checks(tile_inner)
        projection_readback_valid = _v23_projection_readback_valid(
            output_directory=numerical_output,
            receipt=partial,
            q_tile=tile,
            tile=tile_inner,
        )
        contributions = tile_inner.get("contributions", {})
        direct_checks: dict[str, bool] = {}
        for name in ("C_direct", "minus_D_direct", "H_original"):
            evidence = contributions.get(name, {}) if isinstance(contributions, dict) else {}
            try:
                relative_error = float(evidence.get("relative_error", float("inf")))
                limit = float(evidence.get("limit", 1.0e-11))
            except (TypeError, ValueError):
                relative_error, limit = float("inf"), 0.0
            direct_checks[name] = bool(
                evidence.get("status") == "MEASURED_AND_INDEPENDENTLY_CHECKED"
                and relative_error <= limit <= 1.0e-11
            )
        cleanup = partial.get("cleanup", {})
        cleared_aliases = cleanup.get("known_python_reference_aliases_cleared", [])
        checks.update(
            {
                "q_only_supplement_artifact_hash_matches": (
                    supplement_path.is_file()
                    and supplement.get("artifact_sha256") == _sha256_file(supplement_path)
                ),
                "q_only_supplement_disk_receipt_matches": (
                    supplement_disk.get("old_checkpoint_metadata_sha256")
                    == supplement.get("old_checkpoint_metadata_sha256")
                    and supplement_disk.get("old_q_failure_sha256")
                    == supplement.get("old_q_failure_sha256")
                    and supplement_disk.get("execution_campaign_window_sha256")
                    == supplement.get("execution_campaign_window_sha256")
                    and supplement_disk.get("old_scan_campaign_window_sha256")
                    == supplement.get("old_scan_campaign_window_sha256")
                ),
                "q_only_old_source_and_complete_prefix_bound": (
                    supplement.get("old_scan_source_sha")
                    == "1291aeef089e6c02c4b9e28125f60072aa769340"
                    and supplement.get("old_checkpoint_completed_mode_count") == 32_060
                ),
                "q_only_execution_and_artifact_campaigns_are_bound":
                _q_only_execution_artifact_campaigns_valid(
                    supplement,
                    manifest_execution_sha256=str(
                        campaign_evidence.get("window_sha256", "")
                    ),
                    v23_window=v23_expected_window,
                    v23_accounting=v23_expected_accounting,
                ),
                "q_only_old_failure_preserved_as_typeerror": (
                    supplement.get("old_q_failure_type") == "TypeError"
                    and "list indices" in str(supplement.get("old_q_failure_message", ""))
                    and isinstance(supplement.get("old_q_failure_sha256"), str)
                    and len(str(supplement.get("old_q_failure_sha256"))) == 64
                ),
                "q_only_checkpoint_hashes_bound": (
                    all(
                        isinstance(supplement.get(key), str)
                        and len(str(supplement.get(key))) == 64
                        for key in (
                            "old_checkpoint_metadata_sha256",
                            "old_checkpoint_payload_sha256",
                            "old_checkpoint_field_sha256",
                        )
                    )
                    and supplement.get("mesh_mpc_h_and_mode_identity_revalidated") is True
                ),
                "q_only_tile_passed_without_full_matrix_or_solver": (
                    tile.get("status") == "PASS_REAL_ORIGINAL_NY8_Q_PORT_TILE"
                    and tile.get("full_q_matrix_coverage") == "0/8"
                    and tile.get("factor_count") == 0
                    and tile.get("ksp_created") is False
                    and tile.get("pde_solved") is False
                    and supplement.get("mode_scan_repeated") is False
                ),
                "q_only_raw_C_minus_D_H_payload_recomputed": all(
                    raw_contribution_checks.values()
                ),
                "q_only_projection_npz_readback_recomputed": projection_readback_valid,
                "q_only_recorded_C_minus_D_H_within_limits": all(direct_checks.values()),
                "q_only_python_references_cleared_and_worker_finished": (
                    isinstance(cleared_aliases, list)
                    and {"space", "mpc", "mesh_object"}.issubset(cleared_aliases)
                    and run_summary.get("status") == "finished"
                    and run_summary.get("result_classification") == "worker_exit0"
                ),
            }
        )
    elif v24_cd_receipt:
        v24_stage_result = partial.get("stage_result")
        v24_stage_result = v24_stage_result if isinstance(v24_stage_result, dict) else {}
        v24_q_coverage = partial.get("q_coverage")
        v24_q_coverage = v24_q_coverage if isinstance(v24_q_coverage, dict) else {}
        real_edge_panel = (
            partial.get("classification")
            == "TARGET_OPERATOR_PROBE_V24_REAL_EDGE_VOLUME_PANEL"
        )
        expected_probe_status = (
            "PASS_V24_REAL_EDGE_VOLUME_PANEL"
            if real_edge_panel
            else "PASS_V24_BOUNDED_PORT_REUSE_VOLUME_SAMPLE"
        )
        q_volume_check = (
            v24_q_coverage.get("built_q_count") == 0
            and v24_q_coverage.get("full_q_matrix_coverage") == "0/8"
            and (
                (
                    v24_q_coverage.get("volume_qualification")
                    == "PARTIAL_REAL_EDGE_ORBIT_Q_PANEL"
                    and "non-edge q-column projection not run"
                    in str(v24_q_coverage.get("reason", ""))
                )
                if real_edge_panel
                else (
                    v24_q_coverage.get("volume_qualification") == "NOT_RUN"
                    and "real face panel remains NOT_RUN"
                    in str(v24_q_coverage.get("reason", ""))
                )
            )
        )
        checks.update(
            {
                "v24_cd_receipt_classification_and_stage_status": (
                    partial.get("status") == "stage_completed"
                    and partial.get("outcome") == "STAGE_COMPLETED"
                    and v24_stage_result.get("probe_status")
                    == expected_probe_status
                    and probe_identity.get("status")
                    == expected_probe_status
                ),
                "v24_cd_q_and_volume_scope_is_accurate": q_volume_check,
                **{
                    f"{name}": passed
                    for name, passed in _v24_bounded_sample_readback_checks(
                        output_directory=numerical_output,
                        probe=probe_identity,
                    ).items()
                },
            }
        )
        if real_edge_panel:
            checks.update(
                {
                    f"{name}": passed
                    for name, passed in _v24_real_edge_panel_readback_checks(
                        output_directory=numerical_output,
                        probe=probe_identity,
                    ).items()
                }
            )
    elif v25_volume_receipt:
        v25_stage_result = partial.get("stage_result")
        v25_stage_result = v25_stage_result if isinstance(v25_stage_result, dict) else {}
        v25_identity = probe_identity.get("v25_complete_target_volume_action")
        v25_identity = v25_identity if isinstance(v25_identity, dict) else {}
        v25_is_pass = partial.get("classification") == (
            "TARGET_OPERATOR_PROBE_V25_COMPLETE_TARGET_VOLUME_ACTION"
        )
        expected_volume_status = (
            "PASS_COMPLETE_TARGET_VOLUME_ACTION"
            if v25_is_pass
            else "FAILED_COMPLETE_TARGET_VOLUME_ACTION"
        )
        v25_q = partial.get("q_coverage", {})
        v25_q = v25_q if isinstance(v25_q, dict) else {}
        checks.update(
            {
                "v25_volume_receipt_classification_and_stage_status": (
                    partial.get("status") == ("stage_completed" if v25_is_pass else "failed")
                    and partial.get("outcome") == ("STAGE_COMPLETED" if v25_is_pass else "STAGE_FAILED")
                    and v25_stage_result.get("probe_status") == expected_volume_status
                    and probe_identity.get("status") == expected_volume_status
                    and v25_identity.get("status") == expected_volume_status
                ),
                "v25_q_factor_and_pde_scope_is_accurate": (
                    v25_q.get("built_q_count") == 0
                    and v25_q.get("full_q_matrix_coverage") == "0/8"
                    and v25_q.get("volume_qualification") == "NOT_RUN"
                    and isinstance(v25_q.get("reason"), str)
                    and "no q csr or factor was built"
                    in str(v25_q.get("reason", "")).lower()
                ),
                **{
                    name: passed
                    for name, passed in _v25_complete_volume_readback_checks(
                        output_directory=numerical_output,
                        probe=probe_identity,
                        manifest=manifest,
                    ).items()
                },
            }
        )
    elif v28_q_receipt:
        v28_result = partial.get("stage_result", {})
        v28_result = v28_result if isinstance(v28_result, Mapping) else {}
        v28_status = str(v28_stage.get("operation_status", ""))
        v28_complete_csr = v28_operation.get("complete_numeric_csr") is True
        v28_factor_built = v28_operation.get("factor_or_solve_built") is True
        v28_passed = v28_status in {
            "PASS_COMPLETE_Q0_CSR",
            "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
        }
        v28_controlled = v28_status.startswith(
            ("RESOURCE_CONTROLLED_STOP", "PERFORMANCE_CONTROLLED_STOP")
        )
        expected_partial_status = (
            "stage_completed"
            if v28_passed
            else "controlled_stop"
            if v28_controlled
            else "in_progress"
            if v28_status.endswith("_IN_PROGRESS")
            else "failed"
        )
        expected_completed_v28 = (
            ["preflight", expected_stop_stage]
            if v28_complete_csr
            else ["preflight"]
        )
        operation_path = numerical_output / str(v28_stage.get("operation_path", ""))
        checks.update(
            {
                "v28_stage_identity_and_cutoff_classification": bool(
                    partial.get("requested_stop_stage") == expected_stop_stage
                    and v28_operation.get("schema") == "task40extra.review_v28_q0_continuation_stage.v1"
                    and v28_operation.get("operation") == V28_CONTINUATION_OPERATION
                    and v28_operation.get("stop_stage") == expected_stop_stage
                    and v28_result.get("probe_status") == v28_status
                    and partial.get("status") == expected_partial_status
                    and partial.get("completed_stages") == expected_completed_v28
                    and partial.get("official_result") is False
                    and operation_path.is_file()
                    and operation_path.resolve().is_relative_to(numerical_output.resolve())
                    and _sha256_file(operation_path) == v28_stage.get("operation_sha256")
                    and v28_operation.get("selector_sha256") == v28_stage.get("selector_sha256")
                ),
                "v28_q_coverage_and_factor_scope_are_accurate": bool(
                    partial.get("q_coverage", {}).get("built_q_count")
                    == int(v28_complete_csr)
                    and partial.get("q_coverage", {}).get("full_q_matrix_coverage")
                    == ("1/8" if v28_complete_csr else "0/8")
                    and partial.get("q_coverage", {}).get("factor_count")
                    == int(v28_factor_built)
                    and partial.get("q_coverage", {}).get("pde_solved") is False
                    and v28_operation.get("ksp_created") is False
                    and v28_operation.get("pde_solved") is False
                ),
                **{
                    name: passed
                    for name, passed in _v28_saved_q0_continuation_checks(
                        output_directory=numerical_output,
                        partial=partial,
                        expected_stop_stage=expected_stop_stage,
                        path_resolver=(v29_context["path_resolver"] if v29_context else None),
                        expected_pattern_path=(v29_context["pattern_path"] if v29_context else None),
                        expected_qualification_path=(
                            v29_context["qualification_path"] if v29_context else None
                        ),
                        artifact_hashes=(v29_context["raw_file_hashes"] if v29_context else None),
                    ).items()
                },
            }
        )
    elif v27_q_receipt:
        v27_result = partial.get("stage_result", {})
        v27_result = v27_result if isinstance(v27_result, Mapping) else {}
        v27_status = str(v27_stage.get("operation_status", ""))
        v27_complete_csr = v27_operation.get("complete_numeric_csr") is True
        v27_factor_built = bool(v27_operation.get("factor_or_solve_built") is True)
        v27_passed = v27_status in {
            "PASS_COMPLETE_Q0_CSR",
            "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
        }
        v27_controlled = v27_status.startswith("RESOURCE_CONTROLLED_STOP")
        v27_expected_partial_status = (
            "stage_completed" if v27_passed else "controlled_stop" if v27_controlled else "failed"
        )
        v27_expected_completed = (
            ["preflight", expected_stop_stage] if v27_complete_csr else ["preflight"]
        )
        operation_path = numerical_output / str(v27_stage.get("operation_path", ""))
        checks.update(
            {
                "v27_saved_q0_stage_identity_and_status": (
                    partial.get("requested_stop_stage") == expected_stop_stage
                    and v27_operation.get("schema") == "task40extra.review_v27_saved_q0_stage.v1"
                    and v27_operation.get("operation") == "V27_SAVED_ONLY_COMPLETE_Q0_CSR"
                    and v27_operation.get("stop_stage") == expected_stop_stage
                    and v27_result.get("probe_status") == v27_status
                    and partial.get("status") == v27_expected_partial_status
                    and partial.get("completed_stages") == v27_expected_completed
                    and partial.get("official_result") is False
                    and operation_path.is_file()
                    and operation_path.resolve().is_relative_to(numerical_output.resolve())
                    and _sha256_file(operation_path) == v27_stage.get("operation_sha256")
                    and v27_operation.get("selector_sha256") == v27_stage.get("selector_sha256")
                ),
                "v27_q_coverage_and_factor_scope_are_accurate": (
                    partial.get("q_coverage", {}).get("built_q_count")
                    == (1 if v27_complete_csr else 0)
                    and partial.get("q_coverage", {}).get("full_q_matrix_coverage")
                    == ("1/8" if v27_complete_csr else "0/8")
                    and partial.get("q_coverage", {}).get("csr_status")
                    == ("COMPLETE_CSR" if v27_complete_csr else v27_operation.get("csr_status", "NOT_CREATED"))
                    and partial.get("q_coverage", {}).get("factor_count") == int(v27_factor_built)
                    and partial.get("q_coverage", {}).get("pde_solved") is False
                    and v27_operation.get("ksp_created") is False
                    and v27_operation.get("pde_solved") is False
                ),
                **{
                    name: passed
                    for name, passed in _v27_saved_q0_readback_checks(
                        output_directory=numerical_output,
                        partial=partial,
                        expected_stop_stage=expected_stop_stage,
                    ).items()
                },
            }
        )
    elif v26_q_receipt:
        v26_stage = partial.get("stage_result", {})
        v26_stage = v26_stage if isinstance(v26_stage, Mapping) else {}
        v26_nested = partial.get("v26_selected_q_stage", {})
        v26_nested = v26_nested if isinstance(v26_nested, Mapping) else {}
        v26_status = str(v26_nested.get("operation_status", ""))
        if expected_stop_stage == "selected_reference_q_build_only":
            expected_v26_status = "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        elif expected_stop_stage == "selected_reference_q_consumer":
            expected_v26_status = "PASS_COMPLETE_Q0_STREAM"
        else:
            expected_v26_status = "PASS_COMPLETE_Q0_CSR_AND_FACTOR"
        v26_success = v26_status == expected_v26_status
        v26_csr_built = v26_status in {
            "PASS_COMPLETE_Q0_CSR",
            "PASS_COMPLETE_Q0_CSR_AND_FACTOR",
            "RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR",
            "FAILED_Q0_FACTOR_LIFECYCLE",
        }
        v26_factor_built = bool(
            v26_nested.get("operation", {}).get("factor_lifecycle", {})
            .get("q_coverage", {}).get("numeric_factor_built") is True
        )
        v26_controlled = partial.get("status") == "controlled_stop"
        checks.update(
            {
                "v26_selected_q_stage_and_scope": (
                    partial.get("requested_stop_stage") == expected_stop_stage
                    and v26_stage.get("probe_status") == v26_status
                    and partial.get("status") == (
                        "stage_completed" if v26_success else "controlled_stop" if v26_controlled else "failed"
                    )
                    and partial.get("official_result") is False
                    and v26_nested.get("selector_sha256")
                    == v26_nested.get("operation", {}).get("selector_sha256", v26_nested.get("operation", {}).get("v26_selector_sha256"))
                ),
                "v26_q_coverage_and_no_solve_scope": (
                    partial.get("q_coverage", {}).get("built_q_count")
                    == (1 if expected_stop_stage == "selected_reference_q_csr" and v26_csr_built else 0)
                    and partial.get("q_coverage", {}).get("full_q_matrix_coverage")
                    == ("1/8" if expected_stop_stage == "selected_reference_q_csr" and v26_csr_built else "0/8")
                    and partial.get("q_coverage", {}).get("factor_count") == int(v26_factor_built)
                    and partial.get("q_coverage", {}).get("pde_solved") is False
                ),
                **{
                    name: passed
                    for name, passed in _v26_selected_q_readback_checks(
                        output_directory=numerical_output,
                        partial=partial,
                        expected_stop_stage=expected_stop_stage,
                    ).items()
                },
            }
        )
    elif v25_q0_receipt:
        q0_stage_result = partial.get("stage_result", {})
        q0_stage_result = q0_stage_result if isinstance(q0_stage_result, Mapping) else {}
        q0_status = str(
            (partial.get("selected_reference_q0_consumer", {}) or {}).get(
                "operation_status", ""
            )
        )
        q0_pass = q0_status in {
            "PASS_COMPLETE_Q0_STREAM",
            "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT",
            "PASS_COMPLETE_Q0_CSR",
        }
        checks.update(
            {
                "v25_q0_receipt_stage_and_scope": (
                    partial.get("requested_stop_stage") == expected_stop_stage
                    and q0_stage_result.get("probe_status") == q0_status
                    and partial.get("status") == (
                        "stage_completed" if q0_pass else "controlled_stop"
                        if q0_status == "RESOURCE_CONTROLLED_STOP" else "failed"
                    )
                    and partial.get("official_result") is False
                ),
                **{
                    name: passed
                    for name, passed in _v25_selected_q0_readback_checks(
                        output_directory=numerical_output,
                        partial=partial,
                    ).items()
                },
            }
        )
    elif v25_controlled_stop_receipt:
        blocker = partial.get("resource_gate")
        blocker = blocker if isinstance(blocker, Mapping) else {}
        probe_blocker = probe_identity.get("resource_blocker")
        probe_blocker = probe_blocker if isinstance(probe_blocker, Mapping) else {}
        checks.update(
            {
                "v25_disk_gate_is_a_controlled_stop": (
                    probe_identity.get("status") == "RESOURCE_CONTROLLED_STOP"
                    and probe_identity.get("failed_stage") is None
                    and probe_identity.get("blocked_task_stage") == "target_operator_probe"
                    and blocker == probe_blocker
                    and blocker.get("stage") == "v25_two_case_atomic_raw_witness_persistence"
                    and blocker.get("passed") is False
                    and type(blocker.get("required_bytes_upper")) is int
                    and type(blocker.get("available_bytes")) is int
                    and blocker["available_bytes"] < blocker["required_bytes_upper"]
                ),
                "v25_disk_controlled_stop_did_not_start_numerical_witness": (
                    not (numerical_output / "v25_complete_target_volume_action.json").exists()
                ),
                "v25_q_factor_and_pde_scope_is_accurate": (
                    partial.get("q_coverage", {}).get("built_q_count") == 0
                    and partial.get("q_coverage", {}).get("full_q_matrix_coverage") == "0/8"
                    and partial.get("q_coverage", {}).get("volume_qualification") == "NOT_RUN"
                ),
            }
        )
    if "geometry_inventory" in (partial.get("completed_stages") or []):
        checks["geometry_artifact_present"] = (
            numerical_output / "v20_geometry_inventory.json"
        ).is_file()
    if "local_port_components" in (partial.get("completed_stages") or []):
        checks["local_components_artifact_present"] = (
            numerical_output / "v20_local_port_components.json"
        ).is_file()
    if os.environ.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1":
        try:
            from src.runners.task40_v29_contract import (
                V29_STRICT_POLICY,
                require_strict_factor_only_status,
            )

            if v29_context is None:
                raise ValueError(v29_context_error or "V29 checker identity context is unavailable")
            selector = v29_context["selector"]
            contract_sha = v29_context["contract_sha256"]
            selector_sha = v29_context["selector_sha256"]
            operation_on_disk = v29_context["operation"]
            binding = operation_on_disk.get("v29_strict_factor_only_binding", {})
            binding = binding if isinstance(binding, Mapping) else {}
            native_receipt = operation_on_disk.get("native_qualification_receipt", {})
            native_receipt = native_receipt if isinstance(native_receipt, Mapping) else {}
            require_strict_factor_only_status(
                {"status": operation_on_disk.get("csr_status")},
                {"status": native_receipt.get("status")},
            )
            strict_action = (
                operation_on_disk.get("continuation_action") == "factor_only"
                and operation_on_disk.get("factor_only_continuation") is True
                and operation_on_disk.get("numeric_fill_skipped") is True
                and operation_on_disk.get("native_readback_skipped") is True
                and operation_on_disk.get("factor_lifecycle_executed_without_adapter_or_native_readback") is True
                and binding.get("fallback_disabled") is True
                and binding.get("strict_policy") == V29_STRICT_POLICY
                and operation_on_disk.get("adapter_created") is not True
                and operation_on_disk.get("numeric_fill_started") is not True
                and operation_on_disk.get("native_readback_started") is not True
            )
            checks.update(v29_context["identity_checks"])
            checks.update(
                {
                    "v29_contract_hash_matches_service_envelope": (
                        contract_sha == os.environ["TASK40_V29_CONTRACT_SHA256"]
                        and binding.get("contract_sha256") == contract_sha
                    ),
                    "v29_selector_hash_matches_service_envelope": (
                        selector_sha == os.environ["TASK40_V29_SELECTOR_SHA256"]
                        and binding.get("selector_sha256") == selector_sha
                    ),
                    "v29_complete_manifest_and_native_pass_preserved": (
                        operation_on_disk.get("csr_status") == "COMPLETE_CSR"
                        and native_receipt.get("status") == "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
                        and native_receipt.get("sha256") == selector.get("qualification_sha256")
                    ),
                    "v29_factor_only_route_has_no_auto_fallback": strict_action,
                    "v29_path_mapping_sidecar_hash_bound": all(
                        isinstance(value, str) and len(value) == 64
                        for value in (
                            v29_context["raw_file_hashes"].get("v29_contract"),
                            v29_context["raw_file_hashes"].get("v29_selector"),
                            v29_context["raw_file_hashes"].get("v29_path_mapping_sidecar"),
                            v29_context["raw_file_hashes"].get("v29_execution_window"),
                        )
                    ),
                }
            )
        except Exception as error:
            checks.update(
                {
                    "v29_contract_hash_matches_service_envelope": False,
                    "v29_selector_hash_matches_service_envelope": False,
                    "v29_complete_manifest_and_native_pass_preserved": False,
                    "v29_factor_only_route_has_no_auto_fallback": False,
                    "v29_caller_source_and_root_bound": False,
                    "v29_old_v28_science_window_preserved": False,
                    "v29_execution_manifest_window_accounting_and_registration_bind": False,
                    "v29_path_mapping_sidecar_hash_bound": False,
                    "v29_contract_check_error": f"{type(error).__name__}: {error}",
                }
            )
    v31_reference_product_recheck = None
    v31_reference_product_error = None
    v31_audit_status = "NOT_APPLICABLE"
    v31_worker_summary = None
    if v31_binding is not None:
        worker_summary_path = numerical_output / "task40_v10_p6_candidate_summary.json"
        if not worker_summary_path.is_file():
            v31_audit_status = "NOT_RUN_WORKER_SUMMARY_ABSENT"
        else:
            try:
                loaded_worker_summary = json.loads(
                    worker_summary_path.read_text(encoding="utf-8")
                )
                if not isinstance(loaded_worker_summary, Mapping):
                    raise ValueError("V31 worker summary root must be an object")
                v31_worker_summary = loaded_worker_summary
            except Exception as error:
                v31_audit_status = "FAILED_WORKER_SUMMARY_INVALID"
                v31_reference_product_error = f"{type(error).__name__}: {error}"
            if v31_worker_summary is not None:
                v31_snapshot = v31_worker_summary.get("reference_audit_snapshot")
                v31_regular_checks = v31_worker_summary.get("regular_inverse_checks")
                if v31_snapshot is None:
                    if v31_regular_checks is not None:
                        v31_audit_status = "FAILED_REFERENCE_PRODUCT_MISSING_AFTER_REFERENCE_CHECKS"
                        v31_reference_product_error = (
                            "regular inverse checks exist but the V31 reference snapshot is absent"
                        )
                    else:
                        v31_audit_status = "NOT_RUN_REFERENCE_NOT_COMPLETE"
                else:
                    try:
                        input_identity = v31_binding.get("input_identity")
                        if not isinstance(input_identity, Mapping):
                            raise ValueError("V31 manifest binding omits its input identity")
                        from src.runners.task40_v10_output_checker import (
                            _verify_v31_reference_inverse_product,
                        )

                        v31_reference_product_recheck = _verify_v31_reference_inverse_product(
                            numerical_output,
                            v31_worker_summary,
                            expected_q_count=expected_q_count,
                            expected_source_sha=str(manifest.get("source_sha", "")),
                            expected_run_id=str(partial.get("run_id", "")),
                            expected_input_sha256=str(
                                input_identity.get("scientific_input_sha256", "")
                            ),
                        )
                        v31_audit_status = "REFERENCE_PRODUCT_RECHECKED"
                    except Exception as error:
                        v31_audit_status = "FAILED_REFERENCE_PRODUCT_RECHECK"
                        v31_reference_product_error = f"{type(error).__name__}: {error}"
        checks["v31_partial_worker_never_claims_official_result"] = (
            partial.get("official_result") is False
            and (
                not worker_summary_path.is_file()
                or (
                    isinstance(v31_worker_summary, Mapping)
                    and v31_worker_summary.get("official_result") is False
                )
            )
        )
        checks["v31_reference_product_rechecked_or_truthfully_not_run"] = (
            v31_audit_status in {
                "NOT_RUN_WORKER_SUMMARY_ABSENT",
                "NOT_RUN_REFERENCE_NOT_COMPLETE",
                "REFERENCE_PRODUCT_RECHECKED",
            }
            and v31_reference_product_error is None
        )
    status = str(partial.get("status", ""))
    checks["partial_status_not_full_pass"] = status != "PASS" and partial.get("official_result") is not True
    checker_passed = all(checks.values())
    return {
        "schema": "task40extra.review_v20_partial_stage_checker.v1",
        "profile_q_count": expected_q_count,
        "status": "PARTIAL_RECEIPT_CHECKED" if checker_passed else "PARTIAL_RECEIPT_INVALID",
        "checker_passed": checker_passed,
        "official_result": False,
        "full_pass": False,
        "scientific_partial_status": status,
        "requested_stop_stage": expected_stop_stage,
        "partial_result_path": str(partial_path),
        "partial_result_sha256": _sha256_file(partial_path),
        "run_summary_result_classification": run_summary.get("result_classification"),
        "checks": checks,
        "errors": [key for key, passed in checks.items() if not passed],
        "raw_evidence_preserved": True,
        "v31_reference_audit_status": v31_audit_status,
        "v31_reference_product_recheck": v31_reference_product_recheck,
        "v31_reference_product_error": v31_reference_product_error,
        **(
            {
                "checker_source_sha": v29_context["checker_source_sha"],
                "original_run_source_sha": v29_context["run_source_sha"],
                "raw_file_hashes": v29_context["raw_file_hashes"],
            }
            if v29_context is not None
            else {}
        ),
    }


def _check_partial_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--numerical-output", type=Path, required=True)
    parser.add_argument("--stop-stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = _check_partial_result(
        input_path=args.input,
        summary_path=args.summary,
        manifest_path=args.manifest,
        numerical_output=args.numerical_output,
        expected_stop_stage=args.stop_stage,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["checker_passed"] else 2


def run_service(
    *,
    unit: str,
    runtime_prefix: Path,
    abi_receipt: Path,
    jit_cache: Path,
    case_args: list[str],
    repo_root: Path = ROOT,
) -> int:
    if case_args and case_args[0] == "--":
        case_args = case_args[1:]
    case_args, v29_contract_path = _extract_v29_path_arg(
        case_args, "--task40-v29-execution-contract"
    )
    case_args, v29_selector_path = _extract_v29_path_arg(
        case_args, "--task40-v29-factor-only-selector"
    )
    case_args, v30_contract_path = _extract_v29_path_arg(
        case_args, "--task40-v30-execution-contract"
    )
    case_args, v31_contract_path = _extract_v29_path_arg(
        case_args, "--task40-v31-execution-contract"
    )
    case_args, v32_contract_path = _extract_v29_path_arg(
        case_args, "--task40-v32-execution-contract"
    )
    if v31_contract_path is not None and v32_contract_path is not None:
        raise ValueError("supply only one Task40 V31/V32 execution contract")
    if v32_contract_path is not None:
        v31_contract_path = v32_contract_path
    v31_entry_sample = (
        clock_sample(include_boot_id=True) if v31_contract_path is not None else None
    )
    v31_contract: dict[str, Any] | None = None
    v31_contract_sha256: str | None = None
    if v31_contract_path is not None:
        if v29_contract_path is not None or v29_selector_path is not None or v30_contract_path is not None:
            raise ValueError("V31 execution contract cannot be combined with a V29 or V30 route")
        from src.runners.task40_v31_contract import (
            require_v31_execution_contract,
            v31_source_artifact_relative,
        )

        current_source_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
        if v31_contract_path.name not in {
            "execution_contract_v31.approved.json",
            "execution_contract_v32.approved.json",
        }:
            raise ValueError("Task40 approved contract filename is not registered")
        expected_contract_path = (
            repo_root / v31_source_artifact_relative(current_source_sha) / v31_contract_path.name
        ).resolve()
        if v31_contract_path.resolve() != expected_contract_path:
            raise ValueError("Task40 service requires the one registered native approved-contract path")
        if os.environ.get("TASK40_V31_CONTRACT_PATH") and Path(
            os.environ["TASK40_V31_CONTRACT_PATH"]
        ).resolve() != v31_contract_path.resolve():
            raise ValueError("V31 service flag differs from its registered contract environment path")
        v31_contract, v31_contract_sha256 = require_v31_execution_contract(
            v31_contract_path,
            expected_sha256=os.environ.get("TASK40_V31_CONTRACT_SHA256"),
            current_root=repo_root,
        )
        execution = v31_contract["execution"]

        def resolve_v31_path(key: str) -> Path:
            value = Path(str(execution[key]))
            return (value if value.is_absolute() else repo_root / value).resolve()

        if (
            resolve_v31_path("runtime_prefix") != runtime_prefix.resolve()
            or resolve_v31_path("abi_receipt_path") != abi_receipt.resolve()
            or resolve_v31_path("jit_cache") != jit_cache.resolve()
        ):
            raise ValueError("V31 launcher runtime paths differ from the approved execution contract")
        if any(
            value == "--task40-v10-campaign-window"
            or value.startswith("--task40-v10-campaign-window=")
            for value in case_args
        ):
            raise ValueError("V31 execution contract supplies its own fixed campaign window")
        case_args.extend(
            ["--task40-v10-campaign-window", str(execution["campaign_window_path"])]
        )
    if v30_contract_path is not None and (v29_contract_path is not None or v29_selector_path is not None):
        raise ValueError("V30 execution contract cannot be combined with the V29 factor-only route")
    v29_entry_sample = (
        clock_sample(include_boot_id=True)
        if v29_contract_path is not None and v29_selector_path is not None
        else None
    )
    v29_contract: dict[str, Any] | None = None
    v29_contract_sha256: str | None = None
    v30_entry_sample = (
        clock_sample(include_boot_id=True) if v30_contract_path is not None else None
    )
    v30_contract: dict[str, Any] | None = None
    v30_contract_sha256: str | None = None
    if (v29_contract_path is None) != (v29_selector_path is None):
        raise ValueError("V29 execution contract and factor-only selector must be supplied together")
    if v29_contract_path is not None:
        from src.runners.task40_v29_contract import require_authorized_contract

        v29_contract, v29_contract_sha256 = require_authorized_contract(
            v29_contract_path,
            current_root=repo_root,
        )
        if any(
            value == "--task40-v10-campaign-window"
            or value.startswith("--task40-v10-campaign-window=")
            for value in case_args
        ):
            raise ValueError("V29 execution contract supplies its own fixed campaign window")
        case_args.extend(
            ["--task40-v10-campaign-window", str(v29_contract["execution"]["campaign_window_path"])]
        )
    if v30_contract_path is not None:
        from src.runners.task40_v30_contract import require_authorized_contract

        if Path(os.environ.get("TASK40_V30_CONTRACT_PATH", "")).resolve() != v30_contract_path.resolve():
            raise ValueError("V30 service flag differs from the contract path received by the launcher")
        v30_contract, v30_contract_sha256 = require_authorized_contract(
            v30_contract_path,
            expected_sha256=os.environ.get("TASK40_V30_CONTRACT_SHA256"),
            current_root=repo_root,
            current_hostname=socket.gethostname(),
        )
        execution = v30_contract["execution"]
        if (
            Path(str(execution["runtime_prefix"])).resolve() != runtime_prefix.resolve()
            or Path(str(execution["abi_receipt_path"])).resolve() != abi_receipt.resolve()
            or Path(str(execution["jit_cache"])).resolve() != jit_cache.resolve()
        ):
            raise ValueError("V30 launcher runtime paths differ from the approved execution contract")
        if any(
            value == "--task40-v10-campaign-window"
            or value.startswith("--task40-v10-campaign-window=")
            for value in case_args
        ):
            raise ValueError("V30 execution contract supplies its own target-native campaign window")
        case_args.extend(
            ["--task40-v10-campaign-window", str(execution["campaign_window_path"])]
        )
    case_args, q_only_scan_directory = _extract_v23_q_only_scan_arg(case_args)
    case_args, v24_cd_selector_path = _extract_v24_cd_selector_arg(case_args)
    case_args, v25_selector_path = _extract_v25_selected_operation_selector_arg(case_args)
    case_args, v26_selector_path = _extract_v26_selected_operation_selector_arg(case_args)
    case_args, v27_selector_path = _extract_v27_saved_q0_selector_arg(case_args)
    case_args, v28_selector_path = _extract_v28_q0_continuation_selector_arg(case_args)
    input_path, campaign_path, stop_stage, data = _parse_case_arguments(
        case_args,
        v30_contract=v30_contract is not None,
        v31_contract=v31_contract is not None,
    )
    canonical_relative, _supported = V20_INPUTS[data["solver"]["preconditioner"]]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    v30_input_identity = None
    v31_input_identity = None
    if v31_contract is not None:
        execution = v31_contract["execution"]
        expected_input_path = Path(str(execution["input_path"]))
        expected_input_path = (
            expected_input_path
            if expected_input_path.is_absolute()
            else repo_root / expected_input_path
        )
        if (
            input_path.resolve() != expected_input_path.resolve()
            or _sha256_file(input_path) != execution["input_sha256"]
        ):
            raise ValueError("V31 DAT path/hash differs from the approved execution contract")
    _validate_service_stage_input_variant(
        input_path,
        canonical_path,
        canonical_text,
        stop_stage,
        data,
        repo_root=repo_root,
        v30_contract=v30_contract is not None,
        v31_contract=v31_contract,
    )
    if v30_contract is not None:
        from src.runners.task40_v30_contract import require_v30_input_identity

        v30_input_identity = require_v30_input_identity(
            canonical_path, input_path, repo_root=repo_root
        )
    if v31_contract is not None:
        from src.runners.task40_v31_contract import require_v31_input_identity

        selector = data["execution"]["task40_v31_q_csr_binding"]
        v31_input_identity = require_v31_input_identity(
            canonical_path,
            input_path,
            repo_root=repo_root,
            source_sha=str(v31_contract["source_freeze"]["source_sha"]),
            selector_sha256=str(selector["selector_sha256"]),
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", unit):
        raise ValueError("invalid systemd user-service unit name")
    campaign_registration = _resolve_service_campaign(
        repo_root,
        campaign_path,
        profile=str(data["solver"]["preconditioner"]),
        stop_stage=stop_stage,
        v31_contract=v31_contract,
    )
    if v29_contract_path is not None and (
        campaign_registration.get("version") != "V29"
        or Path(campaign_registration["path"]).resolve()
        != Path(str(v29_contract["execution"]["campaign_window_path"])).resolve()
    ):
        raise ValueError("V29 campaign window differs from the approved execution contract")
    if v30_contract_path is not None and (
        campaign_registration.get("version") != "V30"
        or Path(campaign_registration["path"]).resolve()
        != Path(str(v30_contract["execution"]["campaign_window_path"])).resolve()
        or campaign_registration.get("sha256")
        != v30_contract["execution"]["campaign_window_sha256"]
    ):
        raise ValueError("V30 campaign window differs from the approved target-native contract")
    if v31_contract_path is not None and (
        campaign_registration.get("version") != "V31"
        or Path(campaign_registration["path"]).resolve()
        != Path(str(v31_contract["execution"]["window"]["window_path"])).resolve()
        or campaign_registration.get("sha256")
        != v31_contract["execution"]["window"]["window_sha256"]
    ):
        raise ValueError("V31 campaign window differs from its separately approved fixed-window contract")
    _validate_v24_q_only_selector(
        campaign_registration,
        stop_stage=stop_stage,
        scan_directory=q_only_scan_directory,
        cd_selector_path=v24_cd_selector_path,
    )
    if v25_selector_path is not None and (
        campaign_registration.get("version") != "V25"
        or q_only_scan_directory is not None
        or v24_cd_selector_path is not None
        or v26_selector_path is not None
    ):
        raise ValueError("V25 selected-operation selector cannot be combined with V23/V24 selectors")
    if campaign_registration.get("version") == "V25" and v25_selector_path is None:
        raise ValueError("V25 operations require their explicit selected-operation selector")
    if v26_selector_path is not None and (
        campaign_registration.get("version") != "V26"
        or q_only_scan_directory is not None
        or v24_cd_selector_path is not None
        or v25_selector_path is not None
    ):
        raise ValueError("V26 selected-operation selector cannot be combined with V23/V24/V25 selectors")
    if campaign_registration.get("version") == "V26" and v26_selector_path is None:
        raise ValueError("V26 operations require their explicit selected-operation selector")
    if v27_selector_path is not None and (
        campaign_registration.get("version") != "V27"
        or q_only_scan_directory is not None
        or v24_cd_selector_path is not None
        or v25_selector_path is not None
        or v26_selector_path is not None
    ):
        raise ValueError("V27 saved-q0 selector cannot be combined with V23–V26 selectors")
    if campaign_registration.get("version") == "V27" and v27_selector_path is None:
        raise ValueError("V27 operations require their explicit saved-q0 selector")
    if v28_selector_path is not None and (
        campaign_registration.get("version") != "V28"
        or q_only_scan_directory is not None
        or v24_cd_selector_path is not None
        or v25_selector_path is not None
        or v26_selector_path is not None
        or v27_selector_path is not None
    ):
        raise ValueError("V28 continuation selector cannot be combined with V23–V27 selectors")
    if campaign_registration.get("version") == "V28" and v28_selector_path is None:
        raise ValueError("V28 operations require their explicit q0 continuation selector")
    v30_selector_conflicts = (
        q_only_scan_directory,
        v24_cd_selector_path,
        v25_selector_path,
        v26_selector_path,
        v27_selector_path,
        v28_selector_path,
        v29_selector_path,
    )
    if v30_contract_path is not None and any(item is not None for item in v30_selector_conflicts):
        raise ValueError("V30 execution contract cannot be combined with an older selector route")
    if campaign_registration.get("version") == "V30" and v30_contract_path is None:
        raise ValueError("V30 operations require the approved execution contract")
    if v31_contract_path is not None and any(item is not None for item in v30_selector_conflicts):
        raise ValueError("V31 execution contract cannot be combined with an older selector route")
    if campaign_registration.get("version") == "V31" and v31_contract_path is None:
        raise ValueError("V31 operations require the separately approved native execution contract")
    if campaign_registration.get("version") == "V29" and (
        v29_selector_path is None
        or v29_contract_path is None
        or any(
            item is not None
            for item in (
                q_only_scan_directory, v24_cd_selector_path, v25_selector_path,
                v26_selector_path, v27_selector_path, v28_selector_path,
            )
        )
    ):
        raise ValueError("V29 operations require only the approved contract and strict factor-only selector")
    q_only_binding = (
        _bind_v23_q_only_scan_checkpoint(
            q_only_scan_directory,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            repo_root=repo_root,
        )
        if q_only_scan_directory is not None
        else None
    )
    v24_cd_binding = (
        _bind_v24_cd_selector(
            v24_cd_selector_path,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            q_only_binding=q_only_binding,
            repo_root=repo_root,
        )
        if v24_cd_selector_path is not None
        else None
    )
    v25_binding = (
        _bind_v25_selected_operation_selector(
            v25_selector_path,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            repo_root=repo_root,
        )
        if v25_selector_path is not None
        else None
    )
    v26_binding = (
        _bind_v26_selected_operation_selector(
            v26_selector_path,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            repo_root=repo_root,
        )
        if v26_selector_path is not None
        else None
    )
    v27_binding = (
        _bind_v27_saved_q0_selector(
            v27_selector_path,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            repo_root=repo_root,
        )
        if v27_selector_path is not None
        else None
    )
    v28_binding = (
        _bind_v28_q0_continuation_selector(
            v28_selector_path,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            repo_root=repo_root,
        )
        if v28_selector_path is not None
        else None
    )
    v29_binding = (
        _bind_v29_factor_only_selector(
            v29_selector_path,
            v29_contract_path,
            input_path=input_path,
            campaign_registration=campaign_registration,
            profile=str(data["solver"]["preconditioner"]),
            stop_stage=stop_stage,
            repo_root=repo_root,
        )
        if v29_selector_path is not None and v29_contract_path is not None
        else None
    )
    v30_binding = (
        {
            "contract_path": str(v30_contract_path.resolve()),
            "contract_sha256": str(v30_contract_sha256),
            "contract": v30_contract,
            "execution_window_path": _v30_environment_window_path(campaign_registration),
            "execution_window_sha256": str(v30_contract["execution"]["campaign_window_sha256"]),
            "q0_donor": dict(v30_contract["preparation"]["accepted_q0_donor"]),
            "q_csr_worklist": list(v30_contract["preparation"]["q_csr_worklist"]),
            "final_all_q_selector_required_at": v30_contract["preparation"]["final_all_q_selector_required_at"],
            "input_identity": dict(v30_input_identity or {}),
        }
        if v30_contract_path is not None and v30_contract is not None
        else None
    )
    v31_binding = (
        {
            "contract_path": str(v31_contract_path.resolve()),
            "contract_sha256": str(v31_contract_sha256),
            "contract": v31_contract,
            "execution_window_path": str(
                Path(str(v31_contract["execution"]["window"]["window_path"])).resolve()
            ),
            "execution_window_sha256": str(
                v31_contract["execution"]["window"]["window_sha256"]
            ),
            "run_source_sha": str(v31_contract["execution"]["run_source_sha"]),
            "source_at_entry": str(
                v31_contract["execution"]["window"]["source_at_entry"]
            ),
            "q0_donor": dict(v31_contract["preparation"]["accepted_q0_donor"]),
            "q_csr_worklist": list(v31_contract["preparation"]["q_csr_worklist"]),
            "final_all_q_selector_required_at": v31_contract["preparation"]["final_all_q_selector_required_at"],
            "selector_path": str(v31_contract["execution"]["selector_path"]),
            "selector_sha256": str(v31_contract["execution"]["selector_sha256"]),
            "input_identity": dict(v31_input_identity or {}),
        }
        if v31_contract_path is not None and v31_contract is not None
        else None
    )
    if v29_binding is not None:
        v28_binding = {
            "selector_path": v29_binding["immutable_v28_selector_path"],
            "selector_sha256": v29_binding["immutable_v28_selector_sha256"],
            "operation": V28_CONTINUATION_OPERATION,
            "stop_stage": stop_stage,
            "campaign_window_sha256": TASK40_V28_CAMPAIGN_SHA256,
            "input_sha256": v29_binding["input_sha256"],
            "producer_root": v29_binding["producer_root"],
            "pattern_manifest_path": v29_binding["pattern_manifest_path"],
            "pattern_manifest_sha256": v29_binding["pattern_manifest_sha256"],
            "continuation_manifest_path": v29_binding["continuation_manifest_path"],
        }
    fixed_campaign = Path(campaign_registration["path"])
    campaign_sha256 = str(campaign_registration["sha256"])
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo_root, text=True).strip()
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo_root, text=True)
    if branch != "task40extra_0p7nm_engineering" or dirty.strip():
        raise RuntimeError("V20 user-service requires the frozen Task40 branch and clean source")

    if campaign_registration.get("version") == "V31":
        from src.runners.task40_v31_contract import v31_source_artifact_relative

        artifact_root = v31_source_artifact_relative(source_sha)
    elif campaign_registration.get("version") == "V30":
        artifact_root = V30_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V29":
        artifact_root = V29_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V28":
        artifact_root = V28_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V27":
        artifact_root = V27_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V26":
        artifact_root = V26_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V25":
        artifact_root = V25_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V24":
        artifact_root = V24_ARTIFACT_ROOT
    elif campaign_registration.get("version") == "V23":
        artifact_root = V23_ARTIFACT_ROOT
    else:
        artifact_root = ARTIFACT_ROOT
    evidence_directory = repo_root / artifact_root / "service_runs" / unit
    evidence_directory.mkdir(parents=True, exist_ok=False)
    events: list[dict[str, Any]] = []
    event_log = evidence_directory / "outer_clock_events.jsonl"
    if v29_entry_sample is not None:
        entry_event = {
            "label": "v29_true_service_entry_before_contract_input_selector_and_donor_hashes",
            "sample": v29_entry_sample,
            "identity": {
                "unit": unit,
                "contract_path": str(v29_contract_path),
                "selector_path": str(v29_selector_path),
                "scope": "clock starts before V29 contract/input/selector/donor validation",
            },
        }
        events.append(entry_event)
        with event_log.open("ab") as stream:
            stream.write(json.dumps(entry_event, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    if v30_entry_sample is not None:
        entry_event = {
            "label": "v30_true_service_entry_before_contract_and_input_validation",
            "sample": v30_entry_sample,
            "identity": {
                "unit": unit,
                "contract_path": str(v30_contract_path),
                "scope": "clock starts before V30 contract/input/selector validation",
            },
        }
        events.append(entry_event)
        with event_log.open("ab") as stream:
            stream.write(json.dumps(entry_event, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    if v31_entry_sample is not None:
        entry_event = {
            "label": "v31_true_service_entry_before_contract_input_selector_and_donor_validation",
            "sample": v31_entry_sample,
            "identity": {
                "unit": unit,
                "contract_path": str(v31_contract_path),
                "contract_sha256": str(v31_contract_sha256),
                "window_sha256": str(v31_binding["execution_window_sha256"]),
                "scope": "clock starts before V31 contract/input/selector/donor revalidation",
            },
        }
        events.append(entry_event)
        with event_log.open("ab") as stream:
            stream.write(json.dumps(entry_event, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    record: dict[str, Any] = {
        "schema": "task40extra.review_v20_user_service_workflow.v1",
        "unit": unit,
        "branch": branch,
        "source_sha": source_sha,
        "working_tree_clean": True,
        "input_path": str(input_path),
        "input_sha256": _sha256_file(input_path),
        "canonical_input_path": str(canonical_path),
        "canonical_input_sha256": _sha256_file(canonical_path),
        "physical_model_sha256": None,
        "stop_stage": stop_stage,
        "campaign_version": campaign_registration["version"],
        "campaign_window_path": str(fixed_campaign),
        "campaign_window_sha256": campaign_sha256,
        "campaign_stage_scope": campaign_registration["stage_scope"],
        "abi_receipt_path": str(abi_receipt),
        "abi_receipt_sha256": _sha256_file(abi_receipt),
        "qualified_jit_cache": str(jit_cache),
        "run_case_argv": [str(runtime_prefix / "bin/python"), "scripts/run_case.py", *case_args],
        "evidence_directory": str(evidence_directory),
    }
    if v30_input_identity is not None:
        record["scientific_input_sha256"] = v30_input_identity["scientific_input_sha256"]
        record["v30_input_identity"] = dict(v30_input_identity)
    if v31_input_identity is not None and v31_binding is not None:
        record["scientific_input_sha256"] = v31_input_identity["scientific_input_sha256"]
        record["v31_input_identity"] = dict(v31_input_identity)
        record["v31_execution_contract_binding"] = {
            key: value for key, value in v31_binding.items() if key != "contract"
        }
    if v29_entry_sample is not None:
        record["v29_true_service_entry_clock"] = v29_entry_sample
    if q_only_binding is not None:
        record["old_v23_scan_artifact_binding"] = dict(q_only_binding)
    if v24_cd_binding is not None:
        record["v24_bounded_port_reuse_volume_selector_binding"] = dict(v24_cd_binding)
    if v25_binding is not None:
        record["v25_selected_operation_selector_binding"] = dict(v25_binding)
    if v26_binding is not None:
        record["v26_selected_operation_selector_binding"] = dict(v26_binding)
    if v27_binding is not None:
        record["v27_saved_q0_selector_binding"] = dict(v27_binding)
    if v28_binding is not None:
        record["v28_q0_continuation_selector_binding"] = dict(v28_binding)
    if v29_binding is not None:
        record["v29_strict_factor_only_binding"] = {
            key: value for key, value in v29_binding.items() if key != "contract"
        }
        record["v29_contract_sha256"] = v29_binding["contract_sha256"]
        record["v29_selector_sha256"] = v29_binding["selector_sha256"]
    if v30_binding is not None:
        record["v30_execution_contract_binding"] = {
            key: value for key, value in v30_binding.items() if key != "contract"
        }
    event_identity = {
        key: record[key]
        for key in (
            "unit",
            "branch",
            "source_sha",
            "input_path",
            "input_sha256",
            "canonical_input_sha256",
            "campaign_window_sha256",
            "abi_receipt_sha256",
            "stop_stage",
            *( ["v29_contract_sha256", "v29_selector_sha256"] if v29_binding is not None else [] ),
            *( ["v30_execution_contract_binding"] if v30_binding is not None else [] ),
            *( ["v31_execution_contract_binding"] if v31_binding is not None else [] ),
        )
    }
    if v30_input_identity is not None:
        event_identity["scientific_input_sha256"] = v30_input_identity["scientific_input_sha256"]
    if v31_input_identity is not None:
        event_identity["scientific_input_sha256"] = v31_input_identity["scientific_input_sha256"]
    if v29_binding is not None:
        event_identity.update(
            v29_contract_sha256=v29_binding["contract_sha256"],
            v29_selector_sha256=v29_binding["selector_sha256"],
            v29_execution_window_sha256=v29_binding["execution_window_sha256"],
        )
    record["outer_clock_events_path"] = str(event_log)
    _append_clock_event(
        events, "user_service_parent_before_activation", event_log, event_identity
    )
    run_case_code: int | None = None
    checker_code: int | None = None
    checker_kind: str | None = None
    try:
        _append_clock_event(events, "activation_started", event_log, event_identity)
        environment, activation_command, activation_code, activation_stderr = _activation_environment(
            repo_root,
            runtime_prefix,
            abi_receipt,
            jit_cache,
            runtime_profile="native_linux"
            if v29_binding is not None or v30_binding is not None or v31_binding is not None
            else None,
        )
        _append_clock_event(events, "activation_finished", event_log, event_identity)
        record["activation_command"] = activation_command
        record["activation_returncode"] = activation_code
        if activation_stderr:
            activation_stderr_path = evidence_directory / "activation_stderr.raw.txt"
            activation_stderr_path.write_text(activation_stderr, encoding="utf-8")
            record["activation_stderr_path"] = str(activation_stderr_path)
            record["activation_stderr_sha256"] = _sha256_file(activation_stderr_path)
        if activation_code != 0:
            raise RuntimeError(
                "qualified activation failed: " + activation_stderr[-4000:]
            )
        if v30_binding is not None:
            environment.pop("TASK40_V29_STRICT_FACTOR_ONLY", None)
            environment.update(
                {
                    "TASK40_V30_STRICT_EXECUTION": "1",
                    "TASK40_V30_CONTRACT_PATH": v30_binding["contract_path"],
                    "TASK40_V30_CONTRACT_SHA256": v30_binding["contract_sha256"],
                    "TASK40_V30_EXECUTION_WINDOW_PATH": v30_binding["execution_window_path"],
                    "TASK40_V30_EXECUTION_WINDOW_SHA256": v30_binding["execution_window_sha256"],
                    "TASK40_V30_TASK_MEMORY_MAX_BYTES": str(
                        v30_binding["contract"]["execution"]["resources"]["task_memory_max_bytes"]
                    ),
                    "TASK40_V30_HOST_RESERVE_BYTES": str(
                        v30_binding["contract"]["execution"]["resources"]["host_reserve_bytes"]
                    ),
                    "TASK40_V30_MEMORY_SWAP_MAX_BYTES": str(
                        v30_binding["contract"]["execution"]["resources"]["memory_swap_max_bytes"]
                    ),
                }
            )
        if v31_binding is not None:
            environment.pop("TASK40_V29_STRICT_FACTOR_ONLY", None)
            environment.pop("TASK40_V30_STRICT_EXECUTION", None)
            environment.update(
                {
                    "TASK40_V31_STRICT_EXECUTION": "1",
                    "TASK40_V31_CONTRACT_PATH": v31_binding["contract_path"],
                    "TASK40_V31_CONTRACT_SHA256": v31_binding["contract_sha256"],
                    "TASK40_V31_EXECUTION_WINDOW_PATH": v31_binding["execution_window_path"],
                    "TASK40_V31_EXECUTION_WINDOW_SHA256": v31_binding["execution_window_sha256"],
                    "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(
                        v31_binding["contract"]["execution"]["resources"]["task_memory_max_bytes"]
                    ),
                    "TASK40_V31_HOST_RESERVE_BYTES": str(
                        v31_binding["contract"]["execution"]["resources"]["host_reserve_bytes"]
                    ),
                    "TASK40_V31_MEMORY_SWAP_MAX_BYTES": str(
                        v31_binding["contract"]["execution"]["resources"]["memory_swap_max_bytes"]
                    ),
                }
            )
        activation_identity = _qualified_activation_identity(environment)
        if activation_identity is None:
            raise RuntimeError("V20 user-service did not receive a qualified runtime profile")
        record["qualified_runtime_identity"] = activation_identity
        if q_only_binding is not None:
            environment.update(
                {
                    "TASK40_V23_Q_ONLY_SCAN_WINDOW_SHA256": str(
                        q_only_binding["artifact_campaign_window_sha256"]
                    ),
                    "TASK40_V23_Q_ONLY_SCAN_RUN_DIR": str(q_only_binding["scan_run_directory"]),
                    "TASK40_V23_Q_ONLY_SCAN_MANIFEST_SHA256": str(
                        q_only_binding["scan_manifest_sha256"]
                    ),
                    "TASK40_V23_Q_ONLY_SCAN_NUMERICAL_OUTPUT": str(
                        q_only_binding["scan_numerical_output"]
                    ),
                    "TASK40_V23_Q_ONLY_SCAN_PREFLIGHT": str(
                        q_only_binding["scan_preflight_path"]
                    ),
                    "TASK40_V23_Q_ONLY_SCAN_WITNESS": str(
                        q_only_binding["scan_witness_path"]
                    ),
                    "TASK40_V23_Q_ONLY_OLD_Q_FAILURE": str(
                        q_only_binding["old_q_failure_path"]
                    ),
                    "TASK40_V23_Q_ONLY_OLD_Q_FAILURE_SHA256": str(
                        q_only_binding["old_q_failure_sha256"]
                    ),
                    "TASK40_V23_Q_ONLY_CHECKPOINT_METADATA": str(
                        q_only_binding["checkpoint_metadata_path"]
                    ),
                    "TASK40_V23_Q_ONLY_CHECKPOINT_METADATA_SHA256": str(
                        q_only_binding["checkpoint_metadata_sha256"]
                    ),
                    "TASK40_V23_Q_ONLY_CHECKPOINT_PAYLOAD": str(
                        q_only_binding["checkpoint_payload_path"]
                    ),
                    "TASK40_V23_Q_ONLY_CHECKPOINT_PAYLOAD_SHA256": str(
                        q_only_binding["checkpoint_payload_sha256"]
                    ),
                }
            )
        if v24_cd_binding is not None:
            environment.update(
                {
                    "TASK40_V24_CD_SELECTOR_PATH": str(v24_cd_binding["selector_path"]),
                    "TASK40_V24_CD_SELECTOR_SHA256": str(v24_cd_binding["selector_sha256"]),
                    "TASK40_V24_CD_Q0_PARTIAL_CHECKER_PATH": str(
                        v24_cd_binding["q0_partial_checker_path"]
                    ),
                    "TASK40_V24_CD_Q0_PARTIAL_CHECKER_SHA256": str(
                        v24_cd_binding["q0_partial_checker_sha256"]
                    ),
                }
            )
        if v25_binding is not None:
            environment.update(
                {
                    "TASK40_V25_SELECTOR_PATH": str(v25_binding["selector_path"]),
                    "TASK40_V25_SELECTOR_SHA256": str(v25_binding["selector_sha256"]),
                }
            )
        if v26_binding is not None:
            environment.update(
                {
                    "TASK40_V26_SELECTOR_PATH": str(v26_binding["selector_path"]),
                    "TASK40_V26_SELECTOR_SHA256": str(v26_binding["selector_sha256"]),
                    "TASK40_V26_OPERATION": str(v26_binding["operation"]),
                    "TASK40_V26_PRODUCER_ROOT": str(
                        (repo_root / V26_PRODUCER_RUN_RELATIVE).resolve()
                    ),
                    "TASK40_V26_FAILURE_INDEX_SHA256": V26_FAILURE_INDEX_SHA256,
                    "TASK40_V26_VERIFIED_INPUT_SHA256": V26_VERIFIED_INPUT_SHA256,
                }
            )
        if v27_binding is not None:
            environment.update(
                {
                    "TASK40_V27_SELECTOR_PATH": str(v27_binding["selector_path"]),
                    "TASK40_V27_SELECTOR_SHA256": str(v27_binding["selector_sha256"]),
                    "TASK40_V27_OPERATION": str(v27_binding["operation"]),
                    "TASK40_V27_PRODUCER_ROOT": str(v27_binding["producer_root"]),
                }
            )
        if v28_binding is not None:
            environment.update(
                {
                    "TASK40_V28_SELECTOR_PATH": str(v28_binding["selector_path"]),
                    "TASK40_V28_SELECTOR_SHA256": str(v28_binding["selector_sha256"]),
                    "TASK40_V28_OPERATION": str(v28_binding["operation"]),
                    "TASK40_V28_CAMPAIGN_WINDOW_SHA256": TASK40_V28_CAMPAIGN_SHA256,
                    "TASK40_V28_PRODUCER_ROOT": str(v28_binding["producer_root"]),
                    "TASK40_V28_PATTERN_MANIFEST_PATH": str(
                        v28_binding["pattern_manifest_path"]
                    ),
                    "TASK40_V28_PATTERN_MANIFEST_SHA256": str(
                        v28_binding["pattern_manifest_sha256"]
                    ),
                    "TASK40_V28_CONTINUATION_MANIFEST_PATH": str(
                        v28_binding["continuation_manifest_path"]
                    ),
                }
            )
        if v29_binding is not None:
            environment.update(
                {
                    "TASK40_V29_STRICT_FACTOR_ONLY": "1",
                    "TASK40_V29_CONTRACT_PATH": v29_binding["contract_path"],
                    "TASK40_V29_CONTRACT_SHA256": v29_binding["contract_sha256"],
                    "TASK40_V29_SELECTOR_PATH": v29_binding["selector_path"],
                    "TASK40_V29_SELECTOR_SHA256": v29_binding["selector_sha256"],
                    "TASK40_V29_EXECUTION_WINDOW_PATH": v29_binding["execution_window_path"],
                    "TASK40_V29_EXECUTION_WINDOW_SHA256": v29_binding["execution_window_sha256"],
                    "TASK40_V29_QUALIFIED_DONOR_IDENTITY_SHA256": v29_binding["donor_identity_sha256"],
                    "TASK40_V29_QUALIFICATION_PATH": v29_binding["qualification_path"],
                    "TASK40_V29_COMPLETE_MANIFEST_SHA256": v29_binding["manifest_sha256"],
                    "TASK40_V29_NATIVE_PASS_SHA256": v29_binding["qualification_sha256"],
                    "TASK40_V29_TASK_MEMORY_MAX_BYTES": str(
                        v29_binding["contract"]["execution"]["resources"]["task_memory_max_bytes"]
                    ),
                    "TASK40_V29_HOST_RESERVE_BYTES": str(
                        v29_binding["contract"]["execution"]["resources"]["host_reserve_bytes"]
                    ),
                    "TASK40_V29_MEMORY_SWAP_MAX_BYTES": str(
                        v29_binding["contract"]["execution"]["resources"]["memory_swap_max_bytes"]
                    ),
                }
            )

        abi_command, abi_code, abi_stdout, abi_stderr = _abi_preflight(
            runtime_prefix, environment, repo_root
        )
        _append_clock_event(events, "abi_preflight_finished", event_log, event_identity)
        record["abi_preflight_command"] = abi_command
        record["abi_preflight_returncode"] = abi_code
        for label, value in (("stdout", abi_stdout), ("stderr", abi_stderr)):
            path = evidence_directory / f"abi_preflight_{label}.raw.txt"
            path.write_text(value, encoding="utf-8")
            record[f"abi_preflight_{label}_sha256"] = _sha256_file(path)
        if abi_code != 0:
            raise RuntimeError(
                "qualified ABI preflight failed: " + abi_stderr[-4000:]
            )
        abi = json.loads(abi_stdout)
        record["abi_preflight"] = abi

        if v29_binding is not None:
            _append_clock_event(events, "v29_live_resource_gate_started", event_log, event_identity)
            record["v29_live_resource_gate"] = _v29_live_resource_gate(
                v29_binding["contract"],
                stage="v29_service_before_worker_start",
            )
            _append_clock_event(events, "v29_live_resource_gate_finished", event_log, event_identity)
        if v30_binding is not None:
            _append_clock_event(events, "v30_live_resource_gate_started", event_log, event_identity)
            record["v30_live_resource_gate"] = _v30_live_resource_gate(
                v30_binding["contract"],
                stage="v30_service_before_worker_start",
            )
            _append_clock_event(events, "v30_live_resource_gate_finished", event_log, event_identity)
        if v31_binding is not None:
            _append_clock_event(events, "v31_live_resource_gate_started", event_log, event_identity)
            record["v31_live_resource_gate"] = _v31_live_resource_gate(
                v31_binding["contract"], stage="v31_service_before_worker_start"
            )
            _append_clock_event(events, "v31_live_resource_gate_finished", event_log, event_identity)

        _append_clock_event(events, "run_case_started", event_log, event_identity)
        case_command = record["run_case_argv"]
        if v29_binding is not None or v30_binding is not None or v31_binding is not None:
            run_case_process = subprocess.Popen(
                case_command,
                cwd=repo_root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            record["worker_pid"] = int(run_case_process.pid)
            run_case_stdout, run_case_stderr = run_case_process.communicate()
            run_case_code = int(run_case_process.returncode)
        else:
            run_case_result = subprocess.run(
                case_command,
                cwd=repo_root,
                env=environment,
                capture_output=True,
                text=True,
            )
            run_case_stdout = run_case_result.stdout
            run_case_stderr = run_case_result.stderr
            run_case_code = int(run_case_result.returncode)
        _append_clock_event(events, "run_case_finished", event_log, event_identity)
        (evidence_directory / "run_case_stdout.raw.txt").write_text(
            run_case_stdout, encoding="utf-8"
        )
        (evidence_directory / "run_case_stderr.raw.txt").write_text(
            run_case_stderr, encoding="utf-8"
        )
        record["run_case_stdout_path"] = str(evidence_directory / "run_case_stdout.raw.txt")
        record["run_case_stderr_path"] = str(evidence_directory / "run_case_stderr.raw.txt")
        record["run_case_returncode"] = run_case_code
        record["run_case_stdout_sha256"] = _sha256_file(evidence_directory / "run_case_stdout.raw.txt")
        record["run_case_stderr_sha256"] = _sha256_file(evidence_directory / "run_case_stderr.raw.txt")
        if run_case_code != 0:
            _set_first_failure(
                record,
                "run_case_failed",
                f"run_case returned {run_case_code}",
                run_case_code,
            )
        run_case_payload = _parse_run_case_result(run_case_stdout)
        summary_path = Path(str(run_case_payload["summary"])).resolve()
        manifest_path = Path(str(run_case_payload["manifest"])).resolve()
        run_directory = Path(str(run_case_payload["run_directory"])).resolve()
        run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        numerical_output = _checker_numerical_output_directory(
            run_directory,
            Path(str(run_summary["numerical_output_directory"])),
        )
        record.update(
            run_directory=str(run_directory),
            run_summary_path=str(summary_path),
            run_manifest_path=str(manifest_path),
            physical_model_sha256=run_manifest.get("physical_model_sha256"),
            input_sha256_from_manifest=run_manifest.get("input_sha256"),
            run_case_result_classification=run_case_payload.get("result_classification"),
        )

        _append_clock_event(events, "required_checker_started", event_log, event_identity)
        packet_path = numerical_output / "v10_candidate_official_output.json"
        if packet_path.is_file():
            checker_kind = "task40_v10_independent_output_checker"
            expected_channel_count = 700
            if campaign_registration.get("version") == "V30":
                from src.io.physical_intermediate_profile import profile_facts

                registered_count = profile_facts(
                    str(data["solver"]["preconditioner"])
                ).get("gates", {}).get("all_original_modes_retained")
                if type(registered_count) is not int or registered_count < 1:
                    raise ValueError("V30 registered profile has no frozen channel count")
                expected_channel_count = registered_count
            checker_command = _run_case_output_checker(
                packet_path,
                runtime_prefix,
                expected_channel_count=expected_channel_count,
            )
        else:
            checker_kind = "task40_v20_partial_receipt_checker"
            checker_output = evidence_directory / "partial_checker_result.json"
            checker_command = [
                str(runtime_prefix / "bin/python"),
                "scripts/task40_v20_service_workflow.py",
                "check-partial",
                "--input",
                str(input_path),
                "--summary",
                str(summary_path),
                "--manifest",
                str(manifest_path),
                "--numerical-output",
                str(numerical_output),
                "--stop-stage",
                stop_stage,
                "--output",
                str(checker_output),
            ]
            record["partial_checker_result_path"] = str(checker_output)
        campaign_accounting = _campaign_accounting_path_from_manifest(
            run_manifest,
            expected_window_sha256=campaign_sha256,
            expected_accounting_path=fixed_campaign.with_name(
                "campaign_accounting_v10.jsonl"
            ),
            expected_run_id=str(data["run_id"]),
            expected_profile=str(data["solver"]["preconditioner"]),
        )
        checker_code, checker_payload, checker_details = _supervise_required_checker(
            command=checker_command,
            checker_kind=checker_kind,
            evidence_directory=evidence_directory,
            runtime_prefix=runtime_prefix,
            environment=environment,
            repo_root=repo_root,
            campaign_window=fixed_campaign,
            campaign_sha256=campaign_sha256,
            campaign_accounting=campaign_accounting,
            source_state={"branch": branch, "source_sha": source_sha, "clean": True},
            profile=str(data["solver"]["preconditioner"]),
            events=events,
            event_log=event_log,
            event_identity=event_identity,
        )
        record["required_checker_command"] = checker_command
        record["required_checker"] = checker_details
        record["required_checker_returncode"] = checker_code
        record["required_checker_payload"] = checker_payload
        if checker_kind == "task40_v10_independent_output_checker":
            checker_passed = _official_checker_passed(checker_code, checker_payload)
        else:
            checker_passed = bool(
                checker_code == 0
                and isinstance(checker_payload, dict)
                and checker_payload.get("checker_passed") is True
                and checker_payload.get("full_pass") is False
            )
            partial_status = (
                checker_payload.get("scientific_partial_status")
                if isinstance(checker_payload, dict)
                else None
            )
            record["reported_partial_stage_status"] = partial_status
            if checker_passed and partial_status == "failed":
                _set_first_failure(
                    record,
                    "scientific_partial_stage_failed",
                    "partial receipt is identity-valid but its scientific stage status is failed",
                    checker_code,
                )
        record["required_checker_passed"] = checker_passed
        record["required_checker_kind"] = checker_kind
        record["official_result"] = bool(
            checker_kind == "task40_v10_independent_output_checker" and checker_passed
        )
        record["partial_footer_cannot_promote_to_full_pass"] = (
            checker_kind == "task40_v20_partial_receipt_checker"
            and isinstance(checker_payload, dict)
            and checker_payload.get("official_result") is False
            and checker_payload.get("full_pass") is False
        )
        if record.get("official_result"):
            record["workflow_classification"] = "OFFICIAL_PACKET_RECHECKED"
        elif record.get("required_checker_passed"):
            record["workflow_classification"] = "PARTIAL_RECEIPT_RECHECKED"
        else:
            record["workflow_classification"] = "CHECKER_FAILED_RAW_EVIDENCE_RETAINED"
            _set_first_failure(
                record,
                "required_checker_failed",
                "required checker did not complete with its exact passing receipt",
                checker_code,
            )
    except Exception as exc:  # retain a complete outer receipt for wrapper failures
        record["workflow_error"] = {"type": type(exc).__name__, "message": str(exc)}
        record["workflow_classification"] = "WORKFLOW_OR_CHECKER_FAILED_RAW_EVIDENCE_RETAINED"
        _set_first_failure(record, "workflow_exception", str(exc))
    finally:
        try:
            _append_clock_event(
                events, "user_service_parent_finished", event_log, event_identity
            )
        except Exception as exc:
            record["clock_persistence_error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            _set_first_failure(record, "clock_persistence_failed", str(exc))
        intervals, clock_errors = _intervals(events)
        record["clock_samples"] = events
        record["nonoverlapping_parent_intervals"] = intervals
        record["clock_errors"] = clock_errors
        if v29_entry_sample is not None and events:
            try:
                record["v29_true_entry_to_parent_closeout_interval"] = checked_interval(
                    v29_entry_sample,
                    events[-1]["sample"],
                    policy=CONSERVATIVE_REALTIME,
                )
                record["v29_parent_cost_includes_preflight_hashes"] = True
            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                record["v29_true_entry_to_parent_closeout_error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
                clock_errors.append(f"V29 true-entry parent interval: {type(error).__name__}: {error}")
        record["outer_clock_passed"] = bool(
            not clock_errors
            and not record.get("clock_persistence_error")
            and len(intervals) == len(events) - 1
        )
        if not record["outer_clock_passed"]:
            _set_first_failure(
                record,
                "outer_clock_failed",
                "; ".join(clock_errors) or "parent clock event persistence was incomplete",
            )
        record["workflow_complete"] = bool(
            not record.get("first_failure")
            and not record.get("workflow_error")
            and record.get("outer_clock_passed") is True
            and run_case_code == 0
            and checker_code == 0
            and record.get("required_checker_passed") is True
        )
        output_path = evidence_directory / "outer_workflow_record.json"
        _write_json_fsync(output_path, record)
    if record.get("workflow_complete") is True:
        return 0
    if checker_code not in (None, 0):
        return int(checker_code)
    if run_case_code not in (None, 0):
        return int(run_case_code)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-inputs")
    resume_input_parser = subparsers.add_parser("prepare-component-resume-input")
    resume_input_parser.add_argument("--manifest", required=True)
    resume_input_parser.add_argument("--sha256", required=True)
    service_parser = subparsers.add_parser("run-service")
    service_parser.add_argument("--unit", required=True)
    service_parser.add_argument("--runtime-prefix", type=Path, required=True)
    service_parser.add_argument("--abi-receipt", type=Path, required=True)
    service_parser.add_argument("--jit-cache", type=Path, required=True)
    service_parser.add_argument("case_args", nargs=argparse.REMAINDER)
    v25_prepare_parser = subparsers.add_parser("prepare-v25-selected-q-input")
    v25_prepare_parser.add_argument(
        "--stop-stage",
        choices=sorted(V25_SELECTED_Q_STAGES),
        default="selected_reference_q_build_only",
    )
    v26_prepare_parser = subparsers.add_parser("prepare-v26-selected-q-input")
    v26_prepare_parser.add_argument(
        "--stop-stage",
        choices=sorted(V26_SELECTED_Q_STAGES),
        default="selected_reference_q_build_only",
    )
    v27_prepare_parser = subparsers.add_parser("prepare-v27-saved-q0-input")
    v27_prepare_parser.add_argument(
        "--stop-stage",
        choices=sorted(V27_SELECTED_Q_STAGES),
        default="selected_reference_q_csr",
    )
    v28_prepare_parser = subparsers.add_parser("prepare-v28-q0-continuation-input")
    v28_prepare_parser.add_argument(
        "--stop-stage",
        choices=sorted(V28_SELECTED_Q_STAGES),
        default="selected_reference_q_csr",
    )
    subparsers.add_parser("prepare-v30-full-input")
    v31_prepare_parser = subparsers.add_parser("prepare-v31-p0")
    v31_prepare_parser.add_argument("--output-dir", type=Path)
    v31_prepare_parser.add_argument("--execution-root", type=Path)
    v32_prepare_parser = subparsers.add_parser("prepare-v32-p0")
    v32_prepare_parser.add_argument("--output-dir", type=Path)
    v32_prepare_parser.add_argument("--execution-root", type=Path)
    v31_approved_parser = subparsers.add_parser("prepare-v31-approved")
    v31_approved_parser.add_argument("--pending-dir", type=Path, required=True)
    v31_approval = v31_approved_parser.add_mutually_exclusive_group(required=True)
    v31_approval.add_argument("--approval-receipt", type=Path)
    v31_approval.add_argument("--reuse-approved-contract", type=Path)
    v32_approved_parser = subparsers.add_parser("prepare-v32-approved")
    v32_approved_parser.add_argument("--pending-dir", type=Path, required=True)
    v32_approval = v32_approved_parser.add_mutually_exclusive_group(required=True)
    v32_approval.add_argument("--approval-receipt", type=Path)
    v32_approval.add_argument("--reuse-approved-contract", type=Path)
    partial_parser = subparsers.add_parser("check-partial")
    partial_parser.add_argument("--input", type=Path, required=True)
    partial_parser.add_argument("--summary", type=Path, required=True)
    partial_parser.add_argument("--manifest", type=Path, required=True)
    partial_parser.add_argument("--numerical-output", type=Path, required=True)
    partial_parser.add_argument("--stop-stage", required=True)
    partial_parser.add_argument("--output", type=Path, required=True)
    supervisor_parser = subparsers.add_parser(
        "supervise-required-checker", help=argparse.SUPPRESS
    )
    supervisor_parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "supervise-required-checker":
        return _run_required_checker_supervision_request(args.request)
    if args.command == "prepare-inputs":
        print(json.dumps(prepare_stage_inputs(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare-v25-selected-q-input":
        print(
            json.dumps(
                prepare_v25_selected_q_input(args.stop_stage),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v26-selected-q-input":
        print(
            json.dumps(
                prepare_v26_selected_q_input(args.stop_stage),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v27-saved-q0-input":
        print(
            json.dumps(
                prepare_v27_saved_q0_input(args.stop_stage),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v28-q0-continuation-input":
        print(
            json.dumps(
                prepare_v28_q0_continuation_input(args.stop_stage),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v30-full-input":
        print(
            json.dumps(
                prepare_v30_full_input(),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v31-p0":
        from src.runners.task40_v31_contract import prepare_v31_pending_package

        print(
            json.dumps(
                prepare_v31_pending_package(
                    repo_root=ROOT,
                    output_directory=args.output_dir,
                    execution_root=args.execution_root,
                ),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v32-p0":
        from src.runners.task40_v31_contract import prepare_v32_pending_package

        print(
            json.dumps(
                prepare_v32_pending_package(
                    repo_root=ROOT,
                    output_directory=args.output_dir,
                    execution_root=args.execution_root,
                ),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v31-approved":
        from src.runners.task40_v31_contract import prepare_v31_approved_package

        print(
            json.dumps(
                prepare_v31_approved_package(
                    repo_root=ROOT,
                    pending_directory=args.pending_dir,
                    approval_receipt=args.approval_receipt,
                    reuse_approved_contract=args.reuse_approved_contract,
                ),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-v32-approved":
        from src.runners.task40_v31_contract import prepare_v32_approved_package

        print(
            json.dumps(
                prepare_v32_approved_package(
                    repo_root=ROOT,
                    pending_directory=args.pending_dir,
                    approval_receipt=args.approval_receipt,
                    reuse_approved_contract=args.reuse_approved_contract,
                ),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "prepare-component-resume-input":
        print(
            json.dumps(
                prepare_component_resume_input(args.manifest, args.sha256),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "check-partial":
        result = _check_partial_result(
            input_path=args.input,
            summary_path=args.summary,
            manifest_path=args.manifest,
            numerical_output=args.numerical_output,
            expected_stop_stage=args.stop_stage,
        )
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["checker_passed"] else 2
    return run_service(
        unit=args.unit,
        runtime_prefix=args.runtime_prefix.resolve(),
        abi_receipt=args.abi_receipt.resolve(),
        jit_cache=args.jit_cache.resolve(),
        case_args=list(args.case_args),
    )


if __name__ == "__main__":
    raise SystemExit(main())
