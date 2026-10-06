"""Recover official V10 outputs from the preserved B0 candidate full field."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


_ORIGINAL_RUN_RELATIVE = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_b0_p6_y_orbit_candidate_v10__full3d_iterative__mpi1__Mna/"
    "20261005T150855.959138Z"
)
_ORIGINAL_SOURCE_SHA = "c439ed40768de4745131b43fc0312bb8be8d9d50"
_INPUT_SHA256 = "2f7e9cf51a3d1ecc73e5cb6f670bac32f769584bda11d778dbeaee5be6562780"
_PHYSICAL_MODEL_SHA256 = "250c26f25d85c0ff68abb0454a6c7640bf8d3af3e6f96bbf599a8cf7c925ae73"
_MODE_SHA256 = "afc439d8969463d3c3d46076382ec30c7a8fe3c9b1150955dc2d228a483e7f6b"
_CARRIER_ASSEMBLY_SHA256 = "f8b26df8a36d3f3f705df2833d62cf12a230a43aff2b1e6bbf751a0687848f12"
_CARRIER_PAYLOAD_SHA256 = "adc74bfe12dadebd5272dab52e699111ae4c8e4b8817bd008227bf996e0e82b6"
_MPC_SHA256 = "e406b9b84209d8502cc063b73501140458d8ca3d87638c6233992c20121ed447"
_STORAGE_ROWS = 55_950
_MODE_COUNT = 532
_A6_LIMIT = 1.0e-6
_PORT_LIMIT = 1.0e-8
_IDENTITY_LIMIT = 1.0e-10
_ENERGY_LIMIT = 1.0e-5

_SAVED_ASSEMBLY_SOURCE_SHA256 = {
    "dtn_boundary_phase_gauge.py": (
        "5af5e37e1e55ba511e1b3cca2d000cc4ff93f866b52841e9dc24cb69d52c58f4"
    ),
    "dtn_port_3d.py": "0724e3f5c5fd71ac1aa87d2bc27e4761ea05eb1da09b9ee997e71d36182e98f6",
    "fullspace_dtn_action.py": "5e846956a89620d3dc67f6d934bdd44f60e01515589045d81f975246da970784",
    "fullspace_same_mesh_hcurl_pmg_physical.py": (
        "0160c220f294027baa66e485a2e6f40c8f693881db5b1b888244cdf1d5082aac"
    ),
    "dtn_boundary_plane_qualification.py": (
        "08adf9eb4061489337fd55709fbe4761f679b910dd96299b9ac17836c7dd5f42"
    ),
    "fresh_c1_manifest_identity.py": (
        "5186cc28176b6143c6c4c827a3015209cc18b6f096a3055ccb25750b2826e761"
    ),
    "modes_3d.py": "ba58ffd3ceccff21ddf968ad73573344b3856e1dbede78044bd9ba6921cc1383",
    "config_3d.py": "c4cf27346824767a1a5f6dbde396fd61391a29d6cdf66b66603fa369eefcc92e",
}
_FROZEN_CURRENT_ASSEMBLY_SOURCE_SHA256 = {
    "dtn_boundary_phase_gauge.py": (
        "5af5e37e1e55ba511e1b3cca2d000cc4ff93f866b52841e9dc24cb69d52c58f4"
    ),
    "dtn_port_3d.py": "db6b49b4d9eb850dc06f71c320c33c92876ccd5945d039723d30a27c3b873434",
    "fullspace_dtn_action.py": "5e846956a89620d3dc67f6d934bdd44f60e01515589045d81f975246da970784",
    "fullspace_same_mesh_hcurl_pmg_physical.py": (
        "0096aa1d7927802c19f460824ca3fee799a2c61e853699a3308a615676f4120f"
    ),
    "dtn_boundary_plane_qualification.py": (
        "08adf9eb4061489337fd55709fbe4761f679b910dd96299b9ac17836c7dd5f42"
    ),
    "fresh_c1_manifest_identity.py": (
        "5186cc28176b6143c6c4c827a3015209cc18b6f096a3055ccb25750b2826e761"
    ),
    "modes_3d.py": "ba58ffd3ceccff21ddf968ad73573344b3856e1dbede78044bd9ba6921cc1383",
    "config_3d.py": "c4cf27346824767a1a5f6dbde396fd61391a29d6cdf66b66603fa369eefcc92e",
}
_REVIEWED_CHANGED_ASSEMBLY_SOURCES = tuple(
    sorted(
        name
        for name, saved_sha in _SAVED_ASSEMBLY_SOURCE_SHA256.items()
        if _FROZEN_CURRENT_ASSEMBLY_SOURCE_SHA256.get(name) != saved_sha
    )
)


def _canonical_identity_bytes(value: Any) -> bytes:
    from src.solvers.fullspace_dtn_action import _canonical_json_bytes

    return _canonical_json_bytes(value)


def _saved_carrier_identity_recheck(
    *,
    assembly_context: Any,
    mode_manifest_bytes: bytes | str,
    carrier_context_sha256: str | None,
    carrier_manifest_sha256: str | None,
    ordered_mode_count: int,
    ordered_mode_sha256: str | None,
    bundle_mode_sha256: str | None,
    carrier_payload_sha256: str | None,
    mpc_sha256: str | None,
    saved_packet_mpc_sha256: str | None,
    expected_saved_assembly_sha256: str = _CARRIER_ASSEMBLY_SHA256,
) -> dict[str, Any]:
    """Rebind only the reviewed source hashes, then replay the saved manifest guard."""

    expected_changed = list(_REVIEWED_CHANGED_ASSEMBLY_SOURCES)
    if not isinstance(assembly_context, Mapping):
        raise ValueError("rebuilt carrier has no complete assembly context")
    source_sha256 = assembly_context.get("source_sha256")
    if not isinstance(source_sha256, Mapping):
        raise ValueError("rebuilt carrier assembly context has no source hash map")
    raw_manifest = (
        mode_manifest_bytes.encode("utf-8")
        if isinstance(mode_manifest_bytes, str)
        else bytes(mode_manifest_bytes)
    )
    manifest = json.loads(raw_manifest)
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("modes"), list):
        raise ValueError("rebuilt carrier mode manifest is not a complete JSON object")
    manifest_rows = manifest["modes"]
    if any(
        not isinstance(row, dict) or "assembly_context_sha256" not in row
        for row in manifest_rows
    ):
        raise ValueError("rebuilt carrier mode manifest has a missing assembly-context identity")

    current_context_bytes = _canonical_identity_bytes(assembly_context)
    current_context_sha = hashlib.sha256(current_context_bytes).hexdigest()
    current_manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
    replayed_context = json.loads(current_context_bytes)
    replayed_context["source_sha256"] = dict(_SAVED_ASSEMBLY_SOURCE_SHA256)
    replayed_context_sha = hashlib.sha256(
        _canonical_identity_bytes(replayed_context)
    ).hexdigest()
    modes_bind_current_context = all(
        row.get("assembly_context_sha256") == current_context_sha for row in manifest_rows
    )
    for row in manifest_rows:
        row["assembly_context_sha256"] = replayed_context_sha
    replayed_manifest_sha = hashlib.sha256(_canonical_identity_bytes(manifest)).hexdigest()

    expected = {
        "ordered_mode_count": _MODE_COUNT,
        "ordered_mode_sha256": _MODE_SHA256,
        "carrier_payload_sha256": _CARRIER_PAYLOAD_SHA256,
        "mpc_sha256": _MPC_SHA256,
        "saved_packet_mpc_sha256": _MPC_SHA256,
        "saved_carrier_assembly_sha256": expected_saved_assembly_sha256,
        "saved_source_sha256": dict(_SAVED_ASSEMBLY_SOURCE_SHA256),
        "frozen_current_source_sha256": dict(_FROZEN_CURRENT_ASSEMBLY_SOURCE_SHA256),
        "reviewed_changed_source_names": expected_changed,
    }
    actual = {
        "ordered_mode_count": int(ordered_mode_count),
        "ordered_mode_sha256": ordered_mode_sha256,
        "bundle_mode_sha256": bundle_mode_sha256,
        "carrier_payload_sha256": carrier_payload_sha256,
        "mpc_sha256": mpc_sha256,
        "saved_packet_mpc_sha256": saved_packet_mpc_sha256,
        "carrier_context_sha256": carrier_context_sha256,
        "current_context_sha256": current_context_sha,
        "carrier_manifest_sha256": carrier_manifest_sha256,
        "manifest_sha256_from_bytes": current_manifest_sha,
        "rebuilt_saved_context_sha256": replayed_context_sha,
        "rebuilt_saved_manifest_sha256": replayed_manifest_sha,
        "source_sha256": dict(source_sha256),
    }
    checks = {
        "reviewed_source_hash_delta_is_two_files": expected_changed == [
            "dtn_port_3d.py",
            "fullspace_same_mesh_hcurl_pmg_physical.py",
        ],
        "source_sha256_matches_frozen_review": dict(source_sha256)
        == _FROZEN_CURRENT_ASSEMBLY_SOURCE_SHA256,
        "carrier_context_sha_matches_current_context": carrier_context_sha256
        == current_context_sha,
        "carrier_manifest_sha_matches_manifest_bytes": carrier_manifest_sha256
        == current_manifest_sha,
        "manifest_schema_and_profile_valid": (
            manifest.get("schema") == "fullspace-dtn.mode-manifest.v1"
            and manifest.get("profile") == "full3d_scalable_v1"
        ),
        "manifest_mode_count_matches_frozen_count": (
            len(manifest_rows) == _MODE_COUNT and manifest.get("mode_count") == len(manifest_rows)
        ),
        "all_manifest_modes_bind_current_context": modes_bind_current_context,
        "rebuilt_saved_manifest_matches_frozen_sha": (
            replayed_manifest_sha == expected_saved_assembly_sha256
        ),
        "ordered_mode_count_matches_saved_packet": int(ordered_mode_count) == _MODE_COUNT,
        "ordered_mode_sha_matches_saved_packet": ordered_mode_sha256 == _MODE_SHA256,
        "bundle_mode_sha_matches_saved_packet": bundle_mode_sha256 == _MODE_SHA256,
        "carrier_payload_sha_matches_saved_packet": (
            carrier_payload_sha256 == _CARRIER_PAYLOAD_SHA256
        ),
        "rebuilt_mpc_sha_matches_frozen_and_saved": (
            mpc_sha256 == _MPC_SHA256 and saved_packet_mpc_sha256 == _MPC_SHA256
            and mpc_sha256 == saved_packet_mpc_sha256
        ),
    }
    return {
        "schema": "task40extra.v10.saved-carrier-source-rebind-check.v1",
        "passed": all(checks.values()),
        "expected": expected,
        "actual": actual,
        "checks": checks,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    from .physical_p4_schur_v14 import _write_json as audited_write_json

    audited_write_json(path, value)


def _finite_within(value: Any, limit: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0.0 <= number <= float(limit)


def _saved_scalar_gate_checks(packet: Mapping[str, Any]) -> dict[str, bool]:
    """Require finite saved residual/identity values before reusing the field."""

    return {
        "target_A6": _finite_within(packet.get("relative_residual"), _A6_LIMIT),
        "native_A6": _finite_within(packet.get("native_witness_relative_residual"), _A6_LIMIT),
        "port": _finite_within(packet.get("actual_port_residual_relative"), _PORT_LIMIT),
        "internal": _finite_within(packet.get("actual_internal_residual_relative"), _IDENTITY_LIMIT),
        "native_identity": _finite_within(packet.get("actual_native_identity_relative"), _IDENTITY_LIMIT),
        "schur_port_identity": _finite_within(packet.get("actual_schur_port_identity_relative"), _IDENTITY_LIMIT),
        "solver_true_residual": _finite_within(packet.get("solver_reported_true_residual"), _A6_LIMIT),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _load_packet_arrays(
    run_root: Path,
    packet_name: str,
    keys: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    from .task40_v10_output_checker import _array_ref

    packet_path = run_root / packet_name
    packet = _read_json(packet_path)
    manifest = packet.get("arrays")
    if not isinstance(manifest, Mapping):
        raise ValueError(f"saved V10 packet has no array manifest: {packet_path}")
    npz_path = Path(str(manifest.get("path", ""))).resolve()
    if npz_path.parent != run_root or not npz_path.is_file():
        raise ValueError(f"saved V10 NPZ is missing or outside its run root: {npz_path}")
    npz_sha = _sha256_file(npz_path)
    if npz_sha != manifest.get("sha256"):
        raise ValueError(f"saved V10 NPZ SHA mismatch: {npz_path.name}")
    with np.load(npz_path, allow_pickle=False) as arrays:
        loaded = {
            name: np.asarray(_array_ref(packet, name, arrays)).copy()
            for name in keys
        }
    packet["_packet_path"] = str(packet_path.resolve())
    packet["_npz_path"] = str(npz_path)
    packet["_npz_sha256"] = npz_sha
    return packet, loaded


def load_saved_candidate_packets(
    run_root: str | Path,
    *,
    expected_input_sha256: str = _INPUT_SHA256,
    expected_physical_model_sha256: str = _PHYSICAL_MODEL_SHA256,
) -> dict[str, Any]:
    """Validate and load the immutable full-storage vectors from the failed run."""

    repo_root = Path(__file__).resolve().parents[2]
    root = Path(run_root).resolve()
    expected_root = (repo_root / _ORIGINAL_RUN_RELATIVE).resolve()
    if root != expected_root:
        raise ValueError("V10 saved-output recovery is restricted to the reviewed B0 run")

    manifest = _read_json(root / "run_manifest.json")
    run_summary = _read_json(root / "run_summary.json")
    worker_summary = _read_json(root / "task40_v10_p6_candidate_summary.json")
    if manifest.get("run_id") != "task40extra_0p7nm_b0_p6_y_orbit_candidate_v10":
        raise ValueError("saved V10 run_id does not match the frozen B0 candidate")
    if manifest.get("source_sha") != _ORIGINAL_SOURCE_SHA:
        raise ValueError("saved V10 candidate source SHA differs from the reviewed run")
    if manifest.get("input_sha256") != expected_input_sha256 or expected_input_sha256 != _INPUT_SHA256:
        raise ValueError("saved V10 candidate input identity mismatch")
    if (
        manifest.get("physical_model_sha256") != expected_physical_model_sha256
        or expected_physical_model_sha256 != _PHYSICAL_MODEL_SHA256
    ):
        raise ValueError("saved V10 candidate physical-model identity mismatch")
    if (root / "source_sha.txt").read_text(encoding="ascii").strip() != _ORIGINAL_SOURCE_SHA:
        raise ValueError("saved V10 source receipt does not match its run manifest")
    if _sha256_file(root / "input_original.dat") != _INPUT_SHA256:
        raise ValueError("saved V10 original input bytes do not match the frozen input SHA")
    if (root / "physical_model_sha256.txt").read_text(encoding="ascii").strip() != _PHYSICAL_MODEL_SHA256:
        raise ValueError("saved V10 physical-model receipt does not match")
    if (
        run_summary.get("status") != "finished"
        or run_summary.get("result_classification") != "WORKER_FAILED"
        or run_summary.get("exit_status") != 4
        or not math.isclose(
            float(run_summary.get("full_workflow_monotonic_seconds", -1.0)),
            1051.6991222669603,
            rel_tol=0.0,
            abs_tol=1.0e-6,
        )
    ):
        raise ValueError("the original failed-run classification or charged cost changed")
    resource = run_summary.get("resource_authority", {})
    if (
        resource.get("descendants_cleared") is not True
        or resource.get("job_cgroup_swap", {}).get("peak_swap_current_bytes") != 0
    ):
        raise ValueError("the original run is missing its clean-stop/zero-swap evidence")
    if worker_summary.get("numeric_gates_passed") is not True:
        raise ValueError("the preserved candidate did not pass its numeric gates")

    packet_keys = (
        "full_physical_rhs_storage",
        "full_solution_storage",
        "target_backend_applied_storage",
        "target_backend_residual_storage",
        "native_witness_applied_storage",
        "native_witness_residual_storage",
    )
    pre, pre_arrays = _load_packet_arrays(
        root, "v10_candidate_final_A6_pre_release.json", packet_keys + ("actual_retained_alpha",)
    )
    post, post_arrays = _load_packet_arrays(
        root, "v10_candidate_final_A6_post_release.json", packet_keys
    )
    expected_identity = {
        "input_sha256": _INPUT_SHA256,
        "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
        "source_sha": _ORIGINAL_SOURCE_SHA,
    }
    saved_identity = pre.get("identity")
    if not isinstance(saved_identity, Mapping) or any(
        saved_identity.get(key) != value for key, value in expected_identity.items()
    ):
        raise ValueError("saved A6 packet scientific identity mismatch")
    mode_identity = saved_identity.get("mode_and_carrier_identity", {})
    if (
        mode_identity.get("ordered_physical_mode_count") != _MODE_COUNT
        or mode_identity.get("physical_mode_sha256") != _MODE_SHA256
        or mode_identity.get("target_carrier_assembly_manifest_sha256")
        != _CARRIER_ASSEMBLY_SHA256
        or mode_identity.get("target_carrier_payload_sha256") != _CARRIER_PAYLOAD_SHA256
        or mode_identity.get("target_mpc", {}).get("sha256") != _MPC_SHA256
    ):
        raise ValueError("saved A6 packet mode/carrier/MPC identity mismatch")
    if (
        pre.get("limit") != _A6_LIMIT
        or post.get("limit") != _A6_LIMIT
        or post.get("reference_factors_released") is not True
        or pre.get("all_36000_cell_interior_rows_evaluated") is not True
        or pre.get("independent_action_count") != 2
    ):
        raise ValueError("saved A6 packets do not satisfy the frozen recovery contract")

    for name in packet_keys:
        if pre_arrays[name].shape != (_STORAGE_ROWS,) or pre_arrays[name].dtype != np.dtype(np.complex128):
            raise ValueError(f"saved pre-release array has the wrong layout: {name}")
        if post_arrays[name].shape != (_STORAGE_ROWS,) or post_arrays[name].dtype != np.dtype(np.complex128):
            raise ValueError(f"saved post-release array has the wrong layout: {name}")
    if pre_arrays["actual_retained_alpha"].shape != (_MODE_COUNT,):
        raise ValueError("saved retained alpha does not contain all 532 physical modes")
    for name in ("full_physical_rhs_storage", "full_solution_storage"):
        if not np.array_equal(pre_arrays[name], post_arrays[name]):
            raise ValueError(f"pre/post-release saved storage differs: {name}")

    checks = []
    for packet, arrays in ((pre, pre_arrays), (post, post_arrays)):
        rhs = arrays["full_physical_rhs_storage"]
        scale = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        for label, applied_key, residual_key, stored in (
            ("target_backend", "target_backend_applied_storage", "target_backend_residual_storage", packet["relative_residual"]),
            ("native_A6", "native_witness_applied_storage", "native_witness_residual_storage", packet["native_witness_relative_residual"]),
        ):
            residual = rhs - arrays[applied_key]
            algebra = float(np.linalg.norm(residual - arrays[residual_key]) / scale)
            relative = float(np.linalg.norm(residual) / scale)
            checks.append({
                "release_packet": "pre" if packet is pre else "post",
                "backend": label,
                "relative_residual": relative,
                "stored_relative_residual": float(stored),
                "residual_algebra_defect_relative": algebra,
                "passed": bool(
                    np.isfinite(relative)
                    and relative <= _A6_LIMIT
                    and abs(relative - float(stored)) <= 1.0e-12
                    and algebra <= 1.0e-12
                ),
            })
    if not all(item["passed"] for item in checks):
        raise ValueError("saved pre/post-release A6 residual algebra failed recomputation")
    scalar_gates = _saved_scalar_gate_checks(pre)
    if not all(scalar_gates.values()):
        raise ValueError("saved original port/internal/identity gates do not pass")

    return {
        "root": root,
        "manifest": manifest,
        "run_summary": run_summary,
        "worker_summary": worker_summary,
        "pre_packet": pre,
        "post_packet": post,
        "pre_arrays": pre_arrays,
        "post_arrays": post_arrays,
        "saved_residual_checks": checks,
        "saved_scalar_gate_checks": scalar_gates,
        "mode_identity": dict(mode_identity),
    }


def recover_task40_v10_saved_output(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    saved_run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Reapply native A6 to the saved storage field and generate V10 outputs."""

    from mpi4py import MPI
    from petsc4py import PETSc

    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.postprocessing.task40_saved_field_h_comparison import restore_p6_total_field
    from src.runners.task40_v10_output_checker import (
        verify_v10_dtn_port_mode_table,
        verify_v10_output_bundle,
    )
    from src.runners.task40_v10_worker import (
        _candidate_contract,
        _disk_admit,
        _assign_vector_storage,
        _carrier_payload_identity,
        _file_manifest,
        _hash_arrays,
    )
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P6_REFERENCE_PROFILE,
        profile_facts,
    )
    from src.runners.physical_p4_schur_v14 import _V14Runtime, _repo_root
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.dtn_boundary_phase_gauge import BOUNDARY_PLANE
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
        recover_p0_outputs,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    if MPI.COMM_WORLD.Get_size() != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise ValueError("V10 saved-output recovery requires MPI1 complex128")
    if len(source_sha) != 40:
        raise ValueError("V10 saved-output recovery requires a complete source SHA")
    provenance = resolved_payload.get("provenance", {})
    if (
        provenance.get("input_sha256") != _INPUT_SHA256
        or provenance.get("physical_model_sha256") != _PHYSICAL_MODEL_SHA256
        or resolved_payload.get("run_id") != "task40extra_0p7nm_b0_p6_y_orbit_candidate_v10"
    ):
        raise ValueError("V10 saved-output recovery is restricted to the frozen B0 input")

    run_root = Path(run_directory).resolve()
    stage = str(resolved_payload.get("solver", {}).get("stage", ""))
    contract = profile_facts(TASK40_V10_P6_REFERENCE_PROFILE)
    runtime = _V14Runtime(
        run_root,
        stage,
        contract,
        root=_repo_root(),
        source_sha=source_sha,
        batch_identity="task40_review_v10_integrated_p6_engineering",
        evidence_prefix="v10_candidate",
        require_zero_swap=True,
    )
    campaign_authority = _candidate_contract(resolved_payload, contract, runtime)
    runtime.sample("v10_candidate_preflight")
    phase_timings: dict[str, dict[str, float]] = {}

    def phase_start(name: str, phase: str) -> float:
        runtime.set_phase(phase)
        started = time.monotonic()
        runtime.marker(
            f"v10_saved_output_{name}_started",
            {"monotonic_started": started},
        )
        return started

    def phase_end(name: str, started: float) -> None:
        ended = time.monotonic()
        facts = {
            "monotonic_started": started,
            "monotonic_ended": ended,
            "elapsed_monotonic_seconds": max(0.0, ended - started),
        }
        phase_timings[name] = facts
        runtime.marker(f"v10_saved_output_{name}_completed", facts)
        runtime.sample(f"v10_saved_output_{name}_complete")

    saved = load_saved_candidate_packets(
        saved_run_directory,
        expected_input_sha256=str(provenance["input_sha256"]),
        expected_physical_model_sha256=str(provenance["physical_model_sha256"]),
    )
    output_dir = Path(run_directory).resolve() / "numerical_output"
    if output_dir == saved["root"] / "numerical_output":
        raise ValueError("recovery output must not overwrite the original failed run")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("new V10 recovery output directory is not empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = simulation_config_3d_from_normalized(dict(resolved_payload))
    original_solution = saved["pre_arrays"]["full_solution_storage"]
    original_rhs = saved["pre_arrays"]["full_physical_rhs_storage"]
    old_pre = saved["pre_packet"]
    old_identity = saved["mode_identity"]

    restore_started = phase_start("restore", "assembly")
    restored = restore_p6_total_field("task40_v10_saved", cfg, original_solution)
    phase_end("restore", restore_started)
    levels = restored.levels
    bundle: dict[str, Any] | None = None
    storage_vec = None
    applied_vec = None
    try:
        operator_started = phase_start("operator_rebuild", "assembly")
        native_build_started = phase_start("native_build", "assembly")
        bundle = build_same_mesh_physical_action(
            levels,
            cfg,
            6,
            jit_options=SAME_MESH_JIT_OPTIONS,
            dtn_phase_gauge=BOUNDARY_PLANE,
            verify_dtn_quadrature=True,
        )
        phase_end("native_build", native_build_started)
        inventory = build_dynamic_mode_inventory(cfg)
        modes, mode_rows, mode_sha = inventory

        mapping = native_map_arrays(levels["spaces"][6], levels["floquets"][6])
        independent = np.asarray(mapping["independent_indices"], dtype=np.int64)
        slaves = np.asarray(mapping["slaves"], dtype=np.int64)
        all_rows = np.arange(_STORAGE_ROWS, dtype=np.int64)
        mpc_sha = _hash_arrays({
            "slaves": np.asarray(mapping["slaves"]),
            "masters": np.asarray(mapping["masters"]),
            "coefficients": np.asarray(mapping["coefficients"]),
            "offsets": np.asarray(mapping["offsets"]),
        })
        carrier = bundle["dtn_action"].carrier
        carrier_identity = _saved_carrier_identity_recheck(
            assembly_context=getattr(carrier, "assembly_context", None),
            mode_manifest_bytes=getattr(carrier, "mode_manifest_bytes", b""),
            carrier_context_sha256=getattr(carrier, "assembly_context_sha256", None),
            carrier_manifest_sha256=getattr(carrier, "mode_manifest_sha256", None),
            ordered_mode_count=len(modes),
            ordered_mode_sha256=mode_sha,
            bundle_mode_sha256=bundle.get("mode_sha256"),
            carrier_payload_sha256=_carrier_payload_identity(carrier),
            mpc_sha256=mpc_sha,
            saved_packet_mpc_sha256=old_identity["target_mpc"].get("sha256"),
        )
        carrier_identity_path = output_dir / "v10_saved_output_carrier_identity_recheck.json"
        _write_json(carrier_identity_path, carrier_identity)
        if not carrier_identity["passed"]:
            failed_checks = sorted(
                name for name, passed in carrier_identity["checks"].items() if not passed
            )
            raise ValueError(
                "rebuilt p6 mode/carrier identity differs from the saved B0 packet; "
                f"failed_checks={failed_checks}; receipt={carrier_identity_path.name}"
            )
        if (
            independent.size + slaves.size != _STORAGE_ROWS
            or np.intersect1d(independent, slaves).size
            or not np.array_equal(np.sort(np.r_[independent, slaves]), all_rows)
        ):
            raise ValueError("rebuilt native map does not cover all p6 storage rows")
        if not np.all(original_solution[slaves] == 0.0):
            raise ValueError("saved full solution is not strict slave-zero storage")

        restored_values = np.asarray(restored.electric.x.array, dtype=np.complex128)
        restoration_defect = float(
            np.linalg.norm(restored_values[independent] - original_solution[independent])
            / max(float(np.linalg.norm(original_solution[independent])), np.finfo(float).tiny)
        )
        if not np.isfinite(restoration_defect) or restoration_defect > _IDENTITY_LIMIT:
            raise ValueError("saved-field independent-row restoration identity failed")
        phase_end("operator_rebuild", operator_started)

        native_started = phase_start("native", "evaluation")
        storage_vec = PETSc.Vec().createSeq(_STORAGE_ROWS, comm=PETSc.COMM_SELF)
        _assign_vector_storage(storage_vec, original_solution)
        applied_vec = storage_vec.duplicate()
        bundle["physical_action"].apply(storage_vec, applied_vec)
        native_applied = np.asarray(applied_vec.array_r, dtype=np.complex128).copy()
        native_residual = original_rhs - native_applied
        rhs_norm = max(float(np.linalg.norm(original_rhs)), np.finfo(float).tiny)
        native_relative = float(np.linalg.norm(native_residual) / rhs_norm)
        saved_applied = saved["pre_arrays"]["native_witness_applied_storage"]
        saved_residual = saved["pre_arrays"]["native_witness_residual_storage"]
        operation_scale = max(
            float(np.linalg.norm(original_rhs)) + float(np.linalg.norm(native_applied)),
            np.finfo(float).tiny,
        )
        native_action_identity = float(np.linalg.norm(native_applied - saved_applied) / operation_scale)
        native_residual_identity = float(np.linalg.norm(native_residual - saved_residual) / operation_scale)
        if (
            not np.isfinite(native_relative)
            or native_relative > _A6_LIMIT
            or native_action_identity > _IDENTITY_LIMIT
            or native_residual_identity > _IDENTITY_LIMIT
            or abs(native_relative - float(old_pre["native_witness_relative_residual"])) > 1.0e-12
        ):
            raise ValueError("fresh native A6 reapplication did not reproduce the saved residual")
        phase_end("native", native_started)

        runtime.set_phase("evaluation")
        disk_admission_before_output = _disk_admit(
            runtime,
            additional_bytes=1 << 30,
            label="before_p6_saved_field_field_mode_diffraction_export",
        )
        output_started = phase_start("output", "evaluation")
        output = recover_p0_outputs(
            bundle,
            storage_vec,
            output_dir,
            export_all_port_modes=True,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        auxiliary = np.asarray(output["auxiliary"], dtype=np.complex128)
        saved_alpha = saved["pre_arrays"]["actual_retained_alpha"]
        alpha_identity = float(
            np.linalg.norm(auxiliary - saved_alpha)
            / max(float(np.linalg.norm(saved_alpha)), np.finfo(float).tiny)
        )
        port_closure = float(old_pre["actual_port_residual_relative"])
        port = output.get("port_metrics", {})
        volume = output.get("volume_metrics", {})
        power = {
            "R": float(port.get("R_total", np.nan)),
            "T": float(port.get("T_total", np.nan)),
            "A": float(port.get("A_balance", np.nan)),
            "A_volume": float(volume.get("A_volume_total", np.nan)),
        }
        energy_error = abs(power["R"] + power["T"] + power["A_volume"] - 1.0)
        absorption_error = abs(power["A"] - power["A_volume"])
        output_files = _file_manifest(output_dir)
        if not output_files:
            raise ValueError("V10 field/mode/diffraction export produced no files")
        port_mode_table_check = verify_v10_dtn_port_mode_table(
            output_dir / "dtn_port_diffraction_orders_3d.csv",
            expected_channel_count=_MODE_COUNT,
        )
        single_side_order_count_passed = (
            output.get("diffraction_channel_count") == _MODE_COUNT // 2
        )
        output_pass = bool(
            output.get("electric_finite") is True
            and output.get("auxiliary_finite") is True
            and single_side_order_count_passed
            and port_mode_table_check["passed"]
            and np.isfinite(list(power.values())).all()
            and alpha_identity <= _IDENTITY_LIMIT
            and port_closure <= _PORT_LIMIT
            and energy_error <= _ENERGY_LIMIT
            and absorption_error <= _ENERGY_LIMIT
        )
        disk_admission_after_output = _disk_admit(
            runtime,
            additional_bytes=0,
            label="after_p6_saved_field_field_mode_diffraction_export",
        )
        phase_end("output", output_started)

        packet_path = Path(run_directory).resolve() / "v10_candidate_official_output_recovered.json"
        scientific_identity = {
            "schema": "task40extra.review_v10_scientific_output_identity.v1",
            "source_sha": source_sha,
            "saved_field_source_sha": _ORIGINAL_SOURCE_SHA,
            "input_sha256": _INPUT_SHA256,
            "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
            "ordered_physical_mode_sha256": str(bundle["mode_sha256"]),
            "carrier_assembly_manifest_sha256": str(
                bundle["dtn_action"].carrier.mode_manifest_sha256
            ),
            "carrier_payload_rows_values_sha256": _carrier_payload_identity(
                bundle["dtn_action"].carrier
            ),
            "full_solution_storage_sha256": _hash_arrays(
                {"full_solution_storage": original_solution}
            ),
            "modal_amplitudes_sha256": _hash_arrays({"modal_amplitudes": auxiliary}),
            "full_solution_packet": old_pre["arrays"],
            "full_solution_packet_json": old_pre["_packet_path"],
            "field_mode_and_diffraction_files": output_files,
            "field_file_count": len(output_files),
            "independent_reevaluation": {
                "entrypoint": "src.runners.task40_v10_output_checker.verify_v10_output_bundle",
                "scope": (
                    "reopen output hashes, verify complete top/bottom port modes, "
                    "and recompute saved full-residual algebra"
                ),
            },
        }
        output_facts = {
            key: value for key, value in output.items() if key != "auxiliary"
        }
        output_facts["diffraction_channel_count_scope"] = (
            "single-face order count; complete top+bottom channels are independently checked"
        )
        packet = {
            "schema": "task40extra.review_v10_b0_candidate_output.v1",
            "recovery_kind": "saved_field_postprocess_only",
            "identity": {
                "run_id": resolved_payload.get("run_id"),
                "input_sha256": _INPUT_SHA256,
                "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
                "saved_field_source_sha": _ORIGINAL_SOURCE_SHA,
                "recovery_source_sha": source_sha,
            },
            "scientific_identity": scientific_identity,
            "output": output_facts,
            "full_dtn_port_mode_table_check": port_mode_table_check,
            "power": power,
            "R_plus_T_plus_A_volume_minus_one": energy_error,
            "A_minus_A_volume": absorption_error,
            "passed": output_pass,
        }
        _write_json(packet_path, packet)
        checker_started = phase_start("checker", "evaluation")
        checker = verify_v10_output_bundle(packet_path)
        phase_end("checker", checker_started)
        record = {
            "schema": "task40extra.review_v10_b0_saved_field_postprocess_recovery.v1",
            "status": "PASS" if output_pass and checker.get("status") == "PASS" else "FAIL",
            "official_result": bool(output_pass and checker.get("status") == "PASS"),
            "result_classification": (
                "B0_CANDIDATE_POSTPROCESS_RECOVERY_PASS"
                if output_pass and checker.get("status") == "PASS"
                else "B0_CANDIDATE_POSTPROCESS_RECOVERY_FAIL"
            ),
            "original_run_root": str(saved["root"]),
            "original_run_classification_preserved": saved["run_summary"]["result_classification"],
            "original_run_seconds_preserved": float(
                saved["run_summary"]["full_workflow_monotonic_seconds"]
            ),
            "original_run_source_sha": _ORIGINAL_SOURCE_SHA,
            "recovery_source_sha": source_sha,
            "campaign_authority": campaign_authority,
            "campaign_runtime": {
                "time_policy": runtime.time_policy,
                "workflow_clock_source": runtime.workflow_clock_source,
                "workflow_reserved_seconds": runtime.workflow_reserved_seconds,
                "shared_budget": runtime.shared_budget,
                "worker_campaign_access": "read_only_projection",
            },
            "input_sha256": _INPUT_SHA256,
            "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
            "storage_rows": _STORAGE_ROWS,
            "ordered_mode_count": len(modes),
            "ordered_mode_sha256": str(bundle["mode_sha256"]),
            "native_mpc_payload_sha256": mpc_sha,
            "previous_native_map_sha256": "not_persisted_in_original_packet",
            "recomputed_native_map_sha256": __import__(
                "src.runners.physical_macro_controls", fromlist=["_mapping_identity_sha256"]
            )._mapping_identity_sha256(mapping),
            "saved_numeric_gates": saved["saved_residual_checks"],
            "saved_scalar_gate_checks": saved["saved_scalar_gate_checks"],
            "phase_timings_monotonic_seconds": phase_timings,
            "disk_admission": {
                "before_output": disk_admission_before_output,
                "after_output": disk_admission_after_output,
            },
            "native_A6_reapplication": {
                "relative_residual": native_relative,
                "limit": _A6_LIMIT,
                "action_identity_relative": native_action_identity,
                "residual_identity_relative": native_residual_identity,
                "storage_representation": "strict_slave_zero_full_storage",
                "operator_reapplied": True,
            },
            "restoration_identity_relative": restoration_defect,
            "saved_alpha_recovery_identity_relative": alpha_identity,
            "port_closure_relative_from_preserved_packet": port_closure,
            "power": power,
            "full_dtn_port_mode_table_check": port_mode_table_check,
            "single_side_order_count_passed": single_side_order_count_passed,
            "energy_closure_absolute": energy_error,
            "absorption_consistency_absolute": absorption_error,
            "output_packet": str(packet_path),
            "output_packet_sha256": _sha256_file(packet_path),
            "output_files": output_files,
            "output_gates_passed": output_pass,
            "independent_reevaluation": checker,
            "execution_contract": {
                "reference_factors_built": False,
                "condensation_numeric_built": False,
                "ksp_solve_count": 0,
                "native_A6_matvec_count": 1,
            },
        }
        record_path = Path(run_directory).resolve() / "postprocess_recovery_record.json"
        runtime.marker(
            "v10_saved_output_recovery_completed",
            {"status": record["status"], "official_result": record["official_result"]},
        )
        runtime.sample("v10_saved_output_recovery_complete")
        _write_json(record_path, record)
        record["record_path"] = str(record_path)
        return {
            "passed": record["official_result"],
            "errors": [] if record["official_result"] else [record["result_classification"]],
            "summary": record,
            "numerical_output_directory": str(output_dir),
        }
    finally:
        if applied_vec is not None:
            applied_vec.destroy()
        if storage_vec is not None:
            storage_vec.destroy()
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)


__all__ = ["load_saved_candidate_packets", "recover_task40_v10_saved_output"]
