"""Attempt-bound reuse of a previously passed Task40 V18 Ny8 operator audit."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

V18_NY8_PROFILE = "task40extra_v18_p6_y_orbit_b0_y8_reference_v1"
OPERATOR_SOURCE_DEPENDENCIES = (
    "src/solvers/task40_v18_ny8_operator_qualification.py",
    "src/solvers/task40_v17_ny_orbit.py",
    "src/solvers/task40_v17_ny_orbit_fe_component.py",
    "src/solvers/task40_v10_p6_periodic_profile.py",
    "src/solvers/task40_v10_p6_mumps.py",
    "src/solvers/task40_v10_p6_yorbit.py",
    "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
    "src/solvers/hcurl_assembly_time_condensation.py",
    "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py",
    "src/solvers/p6_cell_condensed_action.py",
    "src/solvers/task40_v18_ny8_operator_reuse.py",
    "src/runners/task40_v10_worker.py",
)


def _json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        .encode("utf-8")
    ).hexdigest()


def _repo_file(root: Path, stored_path: Any, label: str) -> Path:
    if not isinstance(stored_path, str) or not stored_path:
        raise ValueError(f"V18 Ny8 receipt omits its {label} path")
    path = Path(stored_path)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"V18 Ny8 {label} is unavailable inside the repository")
    return resolved


def _read_bound_json(root: Path, stored_path: Any, expected_sha256: Any, label: str):
    path = _repo_file(root, stored_path, label)
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 != actual_sha256:
        raise ValueError(f"V18 Ny8 {label} SHA256 differs from the frozen receipt")
    try:
        record = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"V18 Ny8 {label} is not valid JSON") from exc
    if not isinstance(record, Mapping):
        raise ValueError(f"V18 Ny8 {label} root must be a JSON object")
    return path, record, actual_sha256


def reuse_v18_ny8_operator_qualification(
    *,
    repo_root: str | Path,
    receipt_path: str | Path,
    candidate_q_matrices: Mapping[int, Any],
    profile: Any,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    target_mode_sha256: str,
    abi_identity: Mapping[str, Any],
    expected_receipt_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Revalidate a frozen old audit and fresh q CSR before skipping only its oracle."""

    from src.runners.task40_v10_output_checker import (
        _registered_v15_profile_inventory,
        _verify_v18_ny8_operator_qualification,
    )
    from src.solvers.task40_v10_p6_mumps import _sparse_content_sha256

    root = Path(repo_root).resolve()
    path = Path(receipt_path).resolve()
    try:
        receipt_bytes = path.read_bytes()
        receipt = json.loads(receipt_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V18 Ny8 operator-reuse receipt is unavailable or invalid") from exc
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if (
        not isinstance(expected_receipt_sha256, str)
        or len(expected_receipt_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_receipt_sha256)
        or receipt_sha256 != expected_receipt_sha256
    ):
        raise ValueError("V18 Ny8 operator-reuse receipt differs from its frozen expected SHA256")
    if receipt.get("schema") != "task40extra.review_v18_ny8_operator_reuse_receipt.v1":
        raise ValueError("V18 Ny8 operator-reuse receipt schema is not registered")
    profile_identity = getattr(profile, "name", None)
    if profile_identity != V18_NY8_PROFILE:
        raise ValueError("operator qualification reuse is restricted to the registered Ny8 profile")
    inventory = _registered_v15_profile_inventory(profile_identity)
    new_attempt = receipt.get("new_attempt")
    old_attempt = receipt.get("original_attempt")
    if not isinstance(new_attempt, Mapping) or not isinstance(old_attempt, Mapping):
        raise ValueError("V18 Ny8 operator-reuse receipt omits attempt identities")
    expected_identity = {
        "source_sha": source_sha,
        "profile_identity": profile_identity,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_model_sha256,
        "target_mode_sha256": target_mode_sha256,
        "abi_identity": dict(abi_identity),
    }
    if any(new_attempt.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("V18 Ny8 operator-reuse receipt differs from the frozen current run identity")
    original_identity = {
        "profile_identity": profile_identity,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_model_sha256,
        "target_mode_sha256": target_mode_sha256,
        "abi_identity": dict(abi_identity),
    }
    if any(old_attempt.get(key) != value for key, value in original_identity.items()):
        raise ValueError("prior V18 Ny8 operator evidence has a different input, model, mode, or ABI")

    summary_path, original_summary, summary_sha256 = _read_bound_json(
        root,
        old_attempt.get("candidate_summary_path"),
        old_attempt.get("candidate_summary_sha256"),
        "original candidate summary",
    )
    run_manifest_path, original_manifest, run_manifest_sha256 = _read_bound_json(
        root,
        old_attempt.get("run_manifest_path"),
        old_attempt.get("run_manifest_sha256"),
        "original run manifest",
    )
    summary_root = summary_path.parent
    if run_manifest_path.parent != summary_root:
        raise ValueError("V18 Ny8 original summary and run manifest are from different attempts")
    if (
        original_summary.get("status") != "FAILED"
        or original_summary.get("result_classification") != "WORKER_FAILED"
        or original_summary.get("source_sha") != old_attempt.get("source_sha")
        or original_summary.get("profile") != profile_identity
        or original_summary.get("abi") != old_attempt.get("abi_identity")
        or original_summary.get("error") != old_attempt.get("error")
        or original_manifest.get("source_sha") != old_attempt.get("source_sha")
        or original_manifest.get("input_sha256") != input_sha256
        or original_manifest.get("physical_model_sha256") != physical_model_sha256
        or original_manifest.get("result_classification") != "WORKER_FAILED"
        or original_manifest.get("exit_status") != old_attempt.get("exit_status")
    ):
        raise ValueError("original V18 Ny8 summary does not match its source/input/ABI/failure identity")
    for filename, expected in (
        ("source_sha.txt", old_attempt.get("source_sha")),
        ("input_sha256.txt", input_sha256),
        ("physical_model_sha256.txt", physical_model_sha256),
    ):
        text_path = _repo_file(root, str(summary_root / filename), filename)
        if text_path.read_text(encoding="utf-8").strip() != expected:
            raise ValueError(f"original V18 Ny8 {filename} differs from its candidate summary identity")

    old_snapshot = original_summary.get("reference_audit_snapshot")
    if not isinstance(old_snapshot, Mapping):
        raise ValueError("original V18 Ny8 summary omits its reference audit snapshot")
    original_operator = old_snapshot.get("complete_operator_qualification")
    original_factor_snapshot = old_snapshot.get("factor_audit_before_destroy")
    if not isinstance(original_operator, Mapping):
        raise ValueError("original V18 Ny8 summary omits its complete operator qualification")
    if not isinstance(original_factor_snapshot, Mapping):
        raise ValueError("original V18 Ny8 summary omits its factor snapshot")
    if old_attempt.get("complete_operator_qualification") != original_operator:
        raise ValueError("receipt operator facts differ from the original Ny8 summary")
    if old_attempt.get("factor_audit_before_destroy") != original_factor_snapshot:
        raise ValueError("receipt factor snapshot differs from the original Ny8 summary")
    original_profile = original_summary.get("periodic_inventory_expectations")
    if (
        not isinstance(original_profile, Mapping)
        or original_profile.get("name") != profile_identity
        or original_profile.get("q_count") != inventory["q_count"]
        or original_profile.get("mode_count") != inventory["mode_count"]
        or original_profile.get("all_q_required") is not True
        or original_operator.get("mode_identities_covered_once") is not True
        or original_operator.get("original_H_mode_count") != inventory["mode_count"]
        or old_attempt.get("mode_count") != inventory["mode_count"]
    ):
        raise ValueError("original V18 Ny8 summary does not bind the registered mode inventory")
    manifest_solver = original_manifest.get("solver")
    if (
        not isinstance(manifest_solver, Mapping)
        or manifest_solver.get("preconditioner") != profile_identity
        or original_manifest.get("status") != "finished"
        or original_manifest.get("exit_status") != 4
    ):
        raise ValueError("original V18 Ny8 run manifest does not bind its failed profile attempt")

    dependency_hashes = new_attempt.get("source_dependency_sha256")
    if not isinstance(dependency_hashes, Mapping) or set(dependency_hashes) != set(
        OPERATOR_SOURCE_DEPENDENCIES
    ):
        raise ValueError("V18 Ny8 receipt does not bind the complete operator source dependency set")
    for relative_path in OPERATOR_SOURCE_DEPENDENCIES:
        dependency = root / relative_path
        try:
            actual = hashlib.sha256(dependency.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError(f"V18 Ny8 operator source dependency is unavailable: {relative_path}") from exc
        if dependency_hashes.get(relative_path) != actual:
            raise ValueError(f"V18 Ny8 operator source dependency changed: {relative_path}")

    factor_inputs = original_factor_snapshot.get("factor_inputs")
    if old_attempt.get("factor_inputs") != factor_inputs:
        raise ValueError("receipt q-factor inputs differ from the original Ny8 summary")
    if not isinstance(factor_inputs, list) or len(factor_inputs) != inventory["q_count"]:
        raise ValueError("prior V18 Ny8 record does not contain all eight q-factor inputs")
    by_q = {}
    for item in factor_inputs:
        if not isinstance(item, Mapping) or type(item.get("q")) is not int:
            raise ValueError("prior V18 Ny8 q-factor input identity is malformed")
        q = item["q"]
        if q in by_q:
            raise ValueError("prior V18 Ny8 q-factor inputs contain a duplicate q")
        if (
            item.get("input_identity_unchanged") is not True
            or not item.get("caller_input_sha256_before")
            or item.get("caller_input_sha256_before") != item.get("caller_input_sha256_after")
            or item.get("caller_input_sha256_before") != item.get("factor_csr_sha256_before")
            or item.get("factor_csr_sha256_before") != item.get("factor_csr_sha256_after")
        ):
            raise ValueError(f"prior V18 Ny8 q={q} factor input identity did not remain unchanged")
        by_q[q] = item
    if set(by_q) != set(range(inventory["q_count"])):
        raise ValueError("prior V18 Ny8 q-factor inputs do not cover q=0..7")
    if set(candidate_q_matrices) != set(range(inventory["q_count"])):
        raise ValueError("fresh V18 Ny8 q matrices do not cover q=0..7")
    q_hashes = {}
    for q in range(inventory["q_count"]):
        matrix = candidate_q_matrices[q]
        prior = by_q[q]
        actual_hash = _sparse_content_sha256(matrix)
        if (
            list(matrix.shape) != prior.get("shape")
            or int(matrix.nnz) != int(prior.get("nnz", -1))
            or actual_hash != prior.get("caller_input_sha256_before")
        ):
            raise ValueError(f"fresh V18 Ny8 q={q} CSR differs from its passed factor input")
        q_hashes[str(q)] = actual_hash

    factor_snapshot = original_factor_snapshot
    if (
        not isinstance(factor_snapshot, Mapping)
        or int(factor_snapshot.get("max_simultaneous_factors", -1)) != inventory["q_count"]
        or int(factor_snapshot.get("factors_live_count_current", -1)) != inventory["q_count"]
        or factor_snapshot.get("all_q_numeric_factors_strict_true_residual_passed") is not True
    ):
        raise ValueError("prior V18 Ny8 record lacks the full eight-factor live PASS snapshot")
    operator = original_operator
    operator_sha256 = old_attempt.get("complete_operator_qualification_sha256")
    if not isinstance(operator, Mapping) or operator_sha256 != _json_sha256(operator):
        raise ValueError("prior V18 Ny8 operator record differs from its receipt hash")
    checker_summary = {
        "reference_audit_snapshot": {"complete_operator_qualification": operator},
        "complete_operator_qualification_sha256": operator_sha256,
    }
    checker_facts = _verify_v18_ny8_operator_qualification(checker_summary, inventory)
    if checker_facts.get("passed") is not True:
        raise ValueError("prior V18 Ny8 operator record failed independent revalidation")

    reuse_facts = {
        "schema": "task40extra.review_v18_ny8_operator_reuse_validation.v1",
        "status": "REUSED_AFTER_FRESH_Q_HASH_AND_INDEPENDENT_CHECKER_PASS",
        "receipt_path": str(path),
        "receipt_sha256": receipt_sha256,
        "expected_receipt_sha256": expected_receipt_sha256,
        "original_candidate_summary_path": str(summary_path),
        "original_candidate_summary_sha256": summary_sha256,
        "original_run_manifest_path": str(run_manifest_path),
        "original_run_manifest_sha256": run_manifest_sha256,
        "original_run_root": old_attempt.get("run_root"),
        "original_source_sha": old_attempt.get("source_sha"),
        "original_status": original_summary.get("status"),
        "original_result_classification": original_summary.get("result_classification"),
        "original_error": original_summary.get("error"),
        "original_exit_status": original_manifest.get("exit_status"),
        "current_source_sha": source_sha,
        "profile_identity": profile_identity,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_model_sha256,
        "target_mode_sha256": target_mode_sha256,
        "abi_receipt_sha256": abi_identity.get("receipt_sha256"),
        "fresh_q_matrix_sha256": q_hashes,
        "all_eight_fresh_q_hashes_match": True,
        "mode_identity_bound_by_original_factor_input_sha256": True,
        "independent_operator_checker": checker_facts,
        "fresh_factorization_and_target_solve_required": True,
        "old_attempt_failure_preserved": True,
    }
    return dict(operator), reuse_facts
