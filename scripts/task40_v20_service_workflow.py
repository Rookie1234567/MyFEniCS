#!/usr/bin/env python3
"""Hash-bound V20 stage inputs and a thin, clocked user-service driver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, Mapping

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
) -> dict[str, Any]:
    """Resolve a historical window or an exact, scoped V22–V26 campaign."""

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
    else:
        raise ValueError("service campaign window is not a registered V19 or V22–V26 path")
    return {
        "path": window.path,
        "sha256": window.sha256,
        "stage_scope": stage_scope,
        "version": campaign_version,
    }


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
) -> None:
    """Validate the exact pre-run input variant accepted by ``run_service``."""

    execution = data.get("execution", {})
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
    repo_root: Path, runtime_prefix: Path, abi_receipt: Path, jit_cache: Path
) -> tuple[dict[str, str], str, int, str]:
    command = (
        'set -euo pipefail; cd -- "$1"; '
        'source scripts/task40_fresh_c1/activate_local_wsl_complex.sh "$2" "$3" "$4"; '
        'env -0'
    )
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
    return (
        environment,
        " ".join(argv),
        int(completed.returncode),
        completed.stderr.decode("utf-8", errors="replace"),
    )


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


def _parse_case_arguments(case_args: list[str]) -> tuple[Path, Path, str, dict[str, Any]]:
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
    if stop_stage not in supported_stages | {"preflight"} and not v25_q_stage:
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
    *, producer_root: Path, repo_root: Path = ROOT
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
    manifest_input_path = Path(str(run_manifest.get("input_path", ""))).resolve()
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
            or _sha256_file(path) != digest
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


def _run_case_output_checker(packet_path: Path, runtime_prefix: Path) -> list[str]:
    return [
        str(runtime_prefix / "bin/python"),
        "-m",
        "src.runners.task40_v10_output_checker",
        str(packet_path),
        "--expected-channel-count",
        "700",
    ]


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
    activation_marker = environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION")
    if request.get("activation_marker") != activation_marker:
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

    if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("required checker supervisor lacks qualified activation")
    if not os.path.samefile(sys.executable, runtime_prefix / "bin/python"):
        raise RuntimeError("required checker supervisor is not using the qualified interpreter")

    resources = profile_facts(profile)["resources"]
    if resources.get("watchdog_memory_policy") != PHYSICAL_MEMORY_PRESSURE_POLICY:
        raise ValueError("V20 checker watchdog policy differs from the qualified physical-pressure policy")
    workflow_limit_seconds = float(resources["workflow_seconds"])
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
                (repo_root / QUALIFIED_JIT_RELATIVE).resolve()
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
        tree_cap_bytes=int(resources["process_tree_rss_cap_bytes"]),
        allow_physical_pressure_tree_cap=True,
        require_job_cgroup_zero_swap=True,
        campaign_window_path=campaign_window,
        campaign_window_sha256=campaign_sha256,
        campaign_accounting_path=campaign_accounting,
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
        "supervision": {
            "profile_workflow_limit_seconds": workflow_limit_seconds,
            "campaign_closeout_reserve_seconds": int(
                resources["campaign_closeout_reserve_seconds"]
            ),
            "campaign_window_sha256": campaign_sha256,
            "campaign_accounting_path": str(campaign_accounting),
            "memory_policy": resources["watchdog_memory_policy"],
            "pss_sampling_policy": resources["pss_sampling_policy"],
            "process_tree_rss_cap_bytes": resources["process_tree_rss_cap_bytes"],
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

    if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("V20 user-service did not receive the qualified activation marker")
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
        "activation_marker": environment.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
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
        "source_state": source_state,
        "profile": profile,
        "response_path": str(response_path),
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
        "activation_marker": environment.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
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
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("required checker supervisor child lacks qualified activation")
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
        native_manifest_path = (native_root / "v26_native_action_manifest.json").resolve()
        try:
            native_manifest = json.loads(native_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            native_manifest = {}
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
        binding = operation.get("v26_artifact_binding", {})
        binding = binding if isinstance(binding, Mapping) else {}
        native_sha = _sha256_file(native_manifest_path) if native_manifest_path.is_file() else ""
        native_identity_ok = bool(
            native_root == expected_native_root
            and native_manifest_path.is_relative_to(expected_native_root)
            and native_status == "PASS_COMPLETE_Q0_NATIVE_CONSUMER"
            and native_manifest.get("producer_identity_sha256") == producer_identity_sha
            and native_manifest.get("saved_replay_manifest_sha256") == replay_sha
            and (not binding or binding.get("native_manifest_sha256") == native_sha)
            and type(native_manifest.get("native_volume_apply_count")) is int
            and native_manifest.get("native_volume_apply_count") == 6
            and type(native_manifest.get("provider_sweep_count")) is int
            and native_manifest.get("provider_sweep_count") == 9
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
                    scale_norm = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)))
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
            recorded = operation.get("complete_stream", {}).get("consumer_replay", {})
            recorded = recorded if isinstance(recorded, Mapping) else {}
            checks["v26_raw_native_comparisons_recomputed_at_scaled_1e_11"] = comparison_passed
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
            checks["v26_scaled_metrics_match_operation_record"] = False
        if expected_stop_stage == "selected_reference_q_csr" and status == "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT":
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
    expected_completed = STAGE_PREFIXES.get(expected_stop_stage)
    v2_receipt = partial.get("schema") == "task40extra.review_v20_partial_result.v2"
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
    case_args, q_only_scan_directory = _extract_v23_q_only_scan_arg(case_args)
    case_args, v24_cd_selector_path = _extract_v24_cd_selector_arg(case_args)
    case_args, v25_selector_path = _extract_v25_selected_operation_selector_arg(case_args)
    case_args, v26_selector_path = _extract_v26_selected_operation_selector_arg(case_args)
    input_path, campaign_path, stop_stage, data = _parse_case_arguments(case_args)
    canonical_relative, _supported = V20_INPUTS[data["solver"]["preconditioner"]]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    _validate_service_stage_input_variant(
        input_path,
        canonical_path,
        canonical_text,
        stop_stage,
        data,
        repo_root=repo_root,
    )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", unit):
        raise ValueError("invalid systemd user-service unit name")
    campaign_registration = _resolve_service_campaign(
        repo_root,
        campaign_path,
        profile=str(data["solver"]["preconditioner"]),
        stop_stage=stop_stage,
    )
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
    fixed_campaign = Path(campaign_registration["path"])
    campaign_sha256 = str(campaign_registration["sha256"])
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo_root, text=True).strip()
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo_root, text=True)
    if branch != "task40extra_0p7nm_engineering" or dirty.strip():
        raise RuntimeError("V20 user-service requires the frozen Task40 branch and clean source")

    if campaign_registration.get("version") == "V26":
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
    if q_only_binding is not None:
        record["old_v23_scan_artifact_binding"] = dict(q_only_binding)
    if v24_cd_binding is not None:
        record["v24_bounded_port_reuse_volume_selector_binding"] = dict(v24_cd_binding)
    if v25_binding is not None:
        record["v25_selected_operation_selector_binding"] = dict(v25_binding)
    if v26_binding is not None:
        record["v26_selected_operation_selector_binding"] = dict(v26_binding)
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
        )
    }
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
            repo_root, runtime_prefix, abi_receipt, jit_cache
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
        if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
            raise RuntimeError("V20 user-service did not receive the qualified activation marker")
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

        _append_clock_event(events, "run_case_started", event_log, event_identity)
        case_command = record["run_case_argv"]
        run_case_result = subprocess.run(
            case_command,
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
        )
        run_case_code = int(run_case_result.returncode)
        _append_clock_event(events, "run_case_finished", event_log, event_identity)
        (evidence_directory / "run_case_stdout.raw.txt").write_text(
            run_case_result.stdout, encoding="utf-8"
        )
        (evidence_directory / "run_case_stderr.raw.txt").write_text(
            run_case_result.stderr, encoding="utf-8"
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
        run_case_payload = _parse_run_case_result(run_case_result.stdout)
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
            checker_command = _run_case_output_checker(packet_path, runtime_prefix)
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
