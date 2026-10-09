"""Attempt-bound reuse of a previously passed Task40 V18 Ny8 operator audit."""
from __future__ import annotations

from collections.abc import Mapping
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
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
CERTIFICATE_SOURCE_DEPENDENCIES = (
    *OPERATOR_SOURCE_DEPENDENCIES,
    "src/runners/task40_v10_output_checker.py",
)


def _json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        .encode("utf-8")
    ).hexdigest()


def _git_source_blob(root: Path, revision: Any, relative_path: str) -> bytes:
    """Read one frozen source blob from local Git without a shell or network."""
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision)
        or relative_path != "src/runners/task40_v10_output_checker.py"
    ):
        raise ValueError("qualified checker source identity is not a frozen Git revision")
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{relative_path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("qualified V18 checker Git blob is unavailable")
    return result.stdout


def _operator_checker_ast(source: bytes) -> dict[str, str]:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise ValueError("qualified/current output checker source is not valid Python") from exc
    names = (
        "_verify_v18_ny8_operator_qualification",
        "_verify_v18_packet_operator_qualification_binding",
    )
    result = {}
    for name in names:
        functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        if len(functions) != 1:
            raise ValueError(f"output checker source does not define exactly one {name}")
        result[name] = ast.dump(functions[0], include_attributes=False)
    return result


def _checker_lifecycle_only_delta(base_source: bytes, current_source: bytes) -> bool:
    """Allow only the V19 factor-lifecycle route in the pre-V19 checker."""
    try:
        base_tree = ast.parse(base_source.decode("utf-8"))
        current_tree = ast.parse(current_source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False

    def named_nodes(tree):
        result = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[node.name] = ast.dump(node, include_attributes=False)
        return result

    base_nodes = named_nodes(base_tree)
    current_nodes = named_nodes(current_tree)
    allowed_added = {
        "_verify_v19_one_q_factor_lifecycle",
        "_verify_v19_run_lifecycle_binding",
    }
    if set(current_nodes) - set(base_nodes) != allowed_added:
        return False
    if set(base_nodes) - set(current_nodes):
        return False
    changed = {
        name for name in base_nodes
        if base_nodes[name] != current_nodes[name]
    }
    if changed != {"verify_v10_output_bundle"}:
        return False
    base_other_nodes = [
        ast.dump(node, include_attributes=False)
        for node in base_tree.body
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    current_other_nodes = [
        ast.dump(node, include_attributes=False)
        for node in current_tree.body
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return base_other_nodes == current_other_nodes


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


def _flatten_input(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            flattened.update(_flatten_input(item, path))
        else:
            flattened[path] = item
    return flattened


def reuse_ny8_operator_qualification_certificate(
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
    """Reuse a passed Ny8 operator audit across the reviewed V19 run-only changes.

    The prior run may have passed or failed overall.  Its operator qualification
    and all-q CSR identity are checked independently of its result classification
    and factor-residency snapshot.
    """

    from src.runners.task40_v10_output_checker import (
        _registered_v15_profile_inventory,
        _verify_v19_one_q_factor_lifecycle,
        _verify_v18_ny8_operator_qualification,
    )
    from src.solvers.task40_v10_p6_mumps import _sparse_content_sha256

    root = Path(repo_root).resolve()
    path = Path(receipt_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("V19 Ny8 reuse receipt must be inside the repository")
    try:
        receipt_bytes = path.read_bytes()
        receipt = json.loads(receipt_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V19 Ny8 operator-reuse receipt is unavailable or invalid") from exc
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if (
        not isinstance(expected_receipt_sha256, str)
        or len(expected_receipt_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_receipt_sha256)
        or receipt_sha256 != expected_receipt_sha256
    ):
        raise ValueError("V19 Ny8 operator-reuse receipt differs from its frozen expected SHA256")
    if receipt.get("schema") != "task40extra.review_v19_ny8_operator_reuse_receipt.v1":
        raise ValueError("V19 Ny8 operator-reuse receipt schema is not registered")
    if getattr(profile, "name", None) != V18_NY8_PROFILE:
        raise ValueError("operator qualification reuse is restricted to the registered Ny8 profile")
    inventory = _registered_v15_profile_inventory(V18_NY8_PROFILE)
    qualified = receipt.get("qualified_attempt")
    current = receipt.get("new_attempt")
    if not isinstance(qualified, Mapping) or not isinstance(current, Mapping):
        raise ValueError("V19 Ny8 reuse receipt omits qualified/current attempt identities")

    expected_current = {
        "source_sha": source_sha,
        "profile_identity": V18_NY8_PROFILE,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_model_sha256,
        "target_mode_sha256": target_mode_sha256,
        "abi_identity": dict(abi_identity),
    }
    if any(current.get(key) != value for key, value in expected_current.items()):
        raise ValueError("V19 Ny8 receipt differs from the frozen current run identity")
    qualified_identity = {
        "profile_identity": V18_NY8_PROFILE,
        "physical_model_sha256": physical_model_sha256,
        "target_mode_sha256": target_mode_sha256,
        "abi_identity": dict(abi_identity),
    }
    if any(qualified.get(key) != value for key, value in qualified_identity.items()):
        raise ValueError("prior Ny8 operator evidence has a different model, mode, profile, or ABI")

    source_receipt_path = _repo_file(
        root, qualified.get("operator_source_receipt_path"), "qualified V18 source receipt"
    )
    source_receipt_bytes = source_receipt_path.read_bytes()
    source_receipt_sha256 = hashlib.sha256(source_receipt_bytes).hexdigest()
    if source_receipt_sha256 != qualified.get("operator_source_receipt_sha256"):
        raise ValueError("qualified V18 source receipt SHA256 differs from the V19 receipt")
    try:
        source_receipt = json.loads(source_receipt_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("qualified V18 source receipt is not valid JSON") from exc
    if source_receipt.get("schema") != "task40extra.review_v18_ny8_operator_reuse_receipt.v1":
        raise ValueError("qualified V18 source receipt schema is not registered")
    source_proof = source_receipt.get("new_attempt")
    if not isinstance(source_proof, Mapping):
        raise ValueError("qualified V18 source receipt omits its passed attempt proof")
    if any(source_proof.get(key) != qualified.get(key) for key in (
        "source_sha", "profile_identity", "input_sha256", "physical_model_sha256",
        "target_mode_sha256", "abi_identity",
    )):
        raise ValueError("qualified V18 attempt identity differs from its source receipt")
    qualified_dependencies = qualified.get("source_dependency_sha256")
    if (
        not isinstance(qualified_dependencies, Mapping)
        or qualified_dependencies != source_proof.get("source_dependency_sha256")
        or set(qualified_dependencies) != set(OPERATOR_SOURCE_DEPENDENCIES)
    ):
        raise ValueError("qualified V18 source dependencies differ from their frozen receipt")

    summary_path, original_summary, summary_sha256 = _read_bound_json(
        root,
        qualified.get("candidate_summary_path"),
        qualified.get("candidate_summary_sha256"),
        "qualified Ny8 candidate summary",
    )
    manifest_path, original_manifest, manifest_sha256 = _read_bound_json(
        root,
        qualified.get("run_manifest_path"),
        qualified.get("run_manifest_sha256"),
        "qualified Ny8 run manifest",
    )
    summary_root = summary_path.parent
    if manifest_path.parent != summary_root:
        raise ValueError("qualified Ny8 summary and run manifest are from different attempts")
    result_status = original_summary.get("status")
    result_classification = original_summary.get("result_classification")
    if (
        result_status not in {"PASS", "FAILED"}
        or not isinstance(result_classification, str)
        or original_manifest.get("status") != "finished"
        or type(original_manifest.get("exit_status")) is not int
        or original_summary.get("source_sha") != qualified.get("source_sha")
        or original_summary.get("profile") != V18_NY8_PROFILE
        or original_summary.get("abi") != qualified.get("abi_identity")
        or original_manifest.get("source_sha") != qualified.get("source_sha")
        or original_manifest.get("input_sha256") != qualified.get("input_sha256")
        or original_manifest.get("physical_model_sha256") != physical_model_sha256
        or original_manifest.get("run_id") != "task40extra_0p7nm_b0_p6_reference_v18_ny8"
        or original_manifest.get("result_classification") is None
    ):
        raise ValueError("qualified Ny8 run result does not bind its recorded terminal identity")
    manifest_solver = original_manifest.get("solver")
    if (
        not isinstance(manifest_solver, Mapping)
        or manifest_solver.get("preconditioner") != V18_NY8_PROFILE
        or manifest_solver.get("stage") != "B0_CANDIDATE"
    ):
        raise ValueError("qualified Ny8 run manifest does not bind the registered profile")
    for filename, expected in (
        ("source_sha.txt", qualified.get("source_sha")),
        ("input_sha256.txt", qualified.get("input_sha256")),
        ("physical_model_sha256.txt", physical_model_sha256),
    ):
        text_path = _repo_file(root, str(summary_root / filename), filename)
        if text_path.read_text(encoding="utf-8").strip() != expected:
            raise ValueError(f"qualified Ny8 {filename} differs from its summary identity")

    input_equivalence = current.get("input_equivalence")
    if not isinstance(input_equivalence, Mapping):
        raise ValueError("V19 receipt omits its explicit input-equivalence record")
    baseline_path = _repo_file(
        root, input_equivalence.get("baseline_input_path"), "baseline Ny8 input"
    )
    current_input_path = _repo_file(
        root, input_equivalence.get("current_input_path"), "current V19 input"
    )
    baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    current_input_sha = hashlib.sha256(current_input_path.read_bytes()).hexdigest()
    if (
        baseline_sha != qualified.get("input_sha256")
        or baseline_sha != input_equivalence.get("baseline_input_sha256")
        or current_input_sha != input_sha256
        or current_input_sha != input_equivalence.get("current_input_sha256")
    ):
        raise ValueError("V19 baseline/current input bytes do not match their recorded identities")
    try:
        baseline_config = tomllib.loads(baseline_path.read_text(encoding="utf-8"))
        current_config = tomllib.loads(current_input_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("V19 baseline/current input is not valid TOML") from exc
    baseline_flat = _flatten_input(baseline_config)
    current_flat = _flatten_input(current_config)
    field_differences = sorted(
        key for key in set(baseline_flat) | set(current_flat)
        if baseline_flat.get(key) != current_flat.get(key)
    )
    expected_differences = ["run_id", "solver.task40_factor_lifecycle_strategy"]
    if (
        field_differences != expected_differences
        or input_equivalence.get("field_differences") != expected_differences
        or baseline_config.get("run_id") != "task40extra_0p7nm_b0_p6_reference_v18_ny8"
        or current_config.get("run_id") != "task40extra_0p7nm_b0_p6_reference_v19_ny8"
        or baseline_config.get("solver", {}).get("task40_factor_lifecycle_strategy") is not None
        or current_config.get("solver", {}).get("task40_factor_lifecycle_strategy")
        != "ONE_Q_REFACTOR_V19"
    ):
        raise ValueError("V19 input changes exceed run_id and factor-lifecycle identity")

    old_snapshot = original_summary.get("reference_audit_snapshot")
    if not isinstance(old_snapshot, Mapping):
        raise ValueError("qualified Ny8 summary omits its reference audit snapshot")
    operator = old_snapshot.get("complete_operator_qualification")
    factor_snapshot = old_snapshot.get("factor_audit_before_destroy")
    if not isinstance(operator, Mapping) or not isinstance(factor_snapshot, Mapping):
        raise ValueError("qualified Ny8 summary omits operator or all-q CSR evidence")
    original_profile = original_summary.get("periodic_inventory_expectations")
    if (
        not isinstance(original_profile, Mapping)
        or original_profile.get("name") != V18_NY8_PROFILE
        or original_profile.get("q_count") != inventory["q_count"]
        or original_profile.get("mode_count") != inventory["mode_count"]
        or original_profile.get("all_q_required") is not True
        or operator.get("mode_identities_covered_once") is not True
        or operator.get("original_H_mode_count") != inventory["mode_count"]
        or qualified.get("mode_count") != inventory["mode_count"]
        or qualified.get("complete_operator_qualification_sha256") != _json_sha256(operator)
    ):
        raise ValueError("qualified Ny8 operator evidence does not bind the registered mode inventory")
    checker_relative_path = "src/runners/task40_v10_output_checker.py"
    checker_path = _repo_file(root, qualified.get("operator_checker_path"), "independent operator checker")
    if checker_path.relative_to(root).as_posix() != checker_relative_path:
        raise ValueError("qualified Ny8 independent checker path is not registered")
    qualified_checker_source = _git_source_blob(
        root, qualified.get("operator_checker_source_sha"), checker_relative_path
    )
    qualified_checker_sha256 = hashlib.sha256(qualified_checker_source).hexdigest()
    if qualified_checker_sha256 != qualified.get("operator_checker_sha256"):
        raise ValueError("qualified Ny8 checker blob differs from its frozen source/hash")
    current_checker_source = checker_path.read_bytes()
    current_checker_sha256 = hashlib.sha256(current_checker_source).hexdigest()
    if _operator_checker_ast(qualified_checker_source) != _operator_checker_ast(current_checker_source):
        raise ValueError("V19 lifecycle checker changes modified the frozen V18 operator-checker functions")
    if not _checker_lifecycle_only_delta(qualified_checker_source, current_checker_source):
        raise ValueError("V19 output-checker source changes exceed the factor-lifecycle route")

    factor_inputs = factor_snapshot.get("factor_inputs")
    lifecycle_strategy = factor_snapshot.get("factor_lifecycle_strategy", "ALL_Q_RESIDENT")
    if lifecycle_strategy == "ONE_Q_REFACTOR_V19":
        lifecycle_facts = _verify_v19_one_q_factor_lifecycle(
            factor_snapshot, expected_q_count=int(inventory["q_count"])
        )
    elif lifecycle_strategy == "ALL_Q_RESIDENT":
        lifecycle_facts = None
        if (
            factor_snapshot.get("max_simultaneous_factors") != inventory["q_count"]
            or factor_snapshot.get("factors_live_count_current") != inventory["q_count"]
            or factor_snapshot.get("all_q_numeric_factors_strict_true_residual_passed") is not True
            or not isinstance(factor_inputs, list)
            or len(factor_inputs) != inventory["q_count"]
        ):
            raise ValueError("qualified V18 all-q factor snapshot is incomplete")
    else:
        raise ValueError("qualified Ny8 factor snapshot uses an unsupported lifecycle")
    if not isinstance(factor_inputs, list) or len(factor_inputs) < inventory["q_count"]:
        raise ValueError("qualified Ny8 record does not contain complete q-factor input identities")
    by_q: dict[int, Mapping[str, Any]] = {}
    identities_by_q: dict[int, tuple[Any, ...]] = {}
    for item in factor_inputs:
        if not isinstance(item, Mapping) or type(item.get("q")) is not int:
            raise ValueError("qualified Ny8 q-factor input identity is malformed")
        q = item["q"]
        if q not in range(inventory["q_count"]):
            raise ValueError("qualified Ny8 q-factor input identity has an out-of-range q")
        if (
            item.get("input_identity_unchanged") is not True
            or not item.get("caller_input_sha256_before")
            or item.get("caller_input_sha256_before") != item.get("caller_input_sha256_after")
            or item.get("caller_input_sha256_before") != item.get("factor_csr_sha256_before")
            or item.get("factor_csr_sha256_before") != item.get("factor_csr_sha256_after")
        ):
            raise ValueError(f"qualified Ny8 q={q} CSR identity did not remain unchanged")
        identity = (
            tuple(item.get("shape", ())),
            item.get("nnz"),
            item.get("caller_input_sha256_before"),
        )
        if q in identities_by_q and identities_by_q[q] != identity:
            raise ValueError(f"qualified Ny8 q={q} CSR identity differs between refactors")
        if lifecycle_strategy == "ALL_Q_RESIDENT" and q in by_q:
            raise ValueError("qualified V18 all-q factor inputs contain a duplicate q")
        identities_by_q[q] = identity
        by_q.setdefault(q, item)
    if set(by_q) != set(range(inventory["q_count"])):
        raise ValueError("qualified Ny8 q-factor inputs do not cover q=0..7")
    if set(candidate_q_matrices) != set(range(inventory["q_count"])):
        raise ValueError("fresh V19 Ny8 q matrices do not cover q=0..7")
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
            raise ValueError(f"fresh V19 Ny8 q={q} CSR differs from its passed operator input")
        q_hashes[str(q)] = actual_hash

    current_dependencies = current.get("source_dependency_sha256")
    assessments = current.get("dependency_change_assessment")
    if (
        not isinstance(current_dependencies, Mapping)
        or set(current_dependencies) != set(CERTIFICATE_SOURCE_DEPENDENCIES)
        or not isinstance(assessments, Mapping)
    ):
        raise ValueError("V19 receipt does not bind every current operator/checker dependency")
    changed_dependencies = []
    for relative_path in CERTIFICATE_SOURCE_DEPENDENCIES:
        dependency = root / relative_path
        try:
            actual = hashlib.sha256(dependency.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError(f"V19 operator source dependency is unavailable: {relative_path}") from exc
        if current_dependencies.get(relative_path) != actual:
            raise ValueError(f"V19 operator source dependency changed after receipt: {relative_path}")
        qualified_hash = (
            qualified_dependencies.get(relative_path)
            if relative_path in qualified_dependencies
            else qualified.get("operator_checker_sha256")
            if relative_path == "src/runners/task40_v10_output_checker.py"
            else None
        )
        if qualified_hash != actual:
            changed_dependencies.append(relative_path)
    if set(assessments) != set(changed_dependencies):
        raise ValueError("V19 dependency-change assessment does not match actual source differences")
    for relative_path in changed_dependencies:
        facts = assessments[relative_path]
        if (
            not isinstance(facts, Mapping)
            or facts.get("operator_semantics_unchanged") is not True
            or not isinstance(facts.get("classification"), str)
            or not facts.get("classification")
            or not isinstance(facts.get("reason"), str)
            or not facts.get("reason")
        ):
            raise ValueError(f"V19 dependency change lacks a scoped operator-equivalence review: {relative_path}")
        if relative_path == checker_relative_path and (
            facts.get("classification") != "v19_factor_lifecycle_checker_route_only"
            or facts.get("lifecycle_checker_change_only") is not True
            or facts.get("operator_checker_functions_unchanged") is not True
        ):
            raise ValueError("V19 output-checker change is not explicitly limited to lifecycle validation")

    operator_checker_facts = _verify_v18_ny8_operator_qualification(
        {
            "reference_audit_snapshot": {"complete_operator_qualification": operator},
            "complete_operator_qualification_sha256": _json_sha256(operator),
        },
        inventory,
    )
    if operator_checker_facts.get("passed") is not True:
        raise ValueError("prior Ny8 complete-operator checker did not independently pass")

    reuse_facts = {
        "schema": "task40extra.review_v19_ny8_operator_reuse_validation.v1",
        "status": "REUSED_AFTER_FRESH_Q_HASH_AND_INDEPENDENT_CHECKER_PASS",
        "receipt_path": str(path),
        "receipt_sha256": receipt_sha256,
        "expected_receipt_sha256": expected_receipt_sha256,
        "qualified_candidate_summary_path": str(summary_path),
        "qualified_candidate_summary_sha256": summary_sha256,
        "qualified_run_manifest_path": str(manifest_path),
        "qualified_run_manifest_sha256": manifest_sha256,
        "qualified_run_root": qualified.get("run_root"),
        "qualified_source_sha": qualified.get("source_sha"),
        "qualified_status": result_status,
        "qualified_result_classification": result_classification,
        "qualified_run_result_classification": original_manifest.get("result_classification"),
        "qualified_exit_status": original_manifest.get("exit_status"),
        "current_source_sha": source_sha,
        "profile_identity": V18_NY8_PROFILE,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_model_sha256,
        "target_mode_sha256": target_mode_sha256,
        "abi_receipt_sha256": abi_identity.get("receipt_sha256"),
        "input_field_differences": field_differences,
        "input_differences_are_run_id_and_factor_lifecycle_only": True,
        "fresh_q_matrix_sha256": q_hashes,
        "all_eight_fresh_q_hashes_match": True,
        "mode_identity_bound_by_original_factor_input_sha256": True,
        "changed_operator_dependency_assessments": dict(assessments),
        "qualified_operator_checker_source_sha": qualified.get("operator_checker_source_sha"),
        "qualified_operator_checker_blob_sha256": qualified_checker_sha256,
        "current_operator_checker_sha256": current_checker_sha256,
        "original_operator_checker_functions_unchanged": True,
        "qualified_factor_lifecycle_strategy": lifecycle_strategy,
        "qualified_factor_lifecycle_validation": lifecycle_facts,
        "independent_operator_checker": operator_checker_facts,
        "fresh_factorization_and_target_solve_required": True,
        "qualified_run_result_and_operator_qualification_are_separate": True,
    }
    return dict(operator), reuse_facts
