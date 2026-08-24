"""Independent checker for the thin V9 P0 memory-first record.

This module deliberately uses only the standard library and NumPy.  It reads
raw JSON/NPY facts, verifies their hashes and provenance, and recomputes the
checkpoint and residual-bound decisions without importing the worker, solver,
PETSc, or MPI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.lor-native-complex-hx.memory-first-p0-record.v1"
CHECKPOINT_SCHEMA = "fixed-memory-krylov.solution-checkpoint.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA_LENGTH = 40
SMALL_PAIR_MARGIN = 1.0e-11
PHYSICAL_PAIR_MARGIN = 1.0e-9
ROUNDTRIP_LIMIT = 1.0e-13
BOUNDARY_LIMIT = 1.0e-12
NEXT_CYCLE_LIMIT = 1.0e-11


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and np.isfinite(float(value))


def _valid_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        character in "0123456789abcdef" for character in value
    )


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    numerator = float(np.linalg.norm(np.asarray(left) - np.asarray(right)))
    denominator = max(float(np.linalg.norm(np.asarray(right))), np.finfo(float).tiny)
    return numerator / denominator


def residual_pair_bound(
    rho_one: float,
    rho_two: float,
    rhs_identity: float,
    *,
    physical: bool,
) -> float:
    values = (float(rho_one), float(rho_two), float(rhs_identity))
    if not all(np.isfinite(value) and value >= 0.0 for value in values):
        raise ValueError("pair-bound facts must be finite and non-negative")
    margin = PHYSICAL_PAIR_MARGIN if physical else SMALL_PAIR_MARGIN
    return float(sum(values) + margin)


def _require(mapping: dict[str, Any], key: str, errors: list[str], path: str) -> Any:
    if key not in mapping:
        errors.append(f"missing {path}.{key}")
        return None
    return mapping[key]


def _check_shard(
    root: Path,
    descriptor: dict[str, Any],
    errors: list[str],
    *,
    forbidden_name_tokens: tuple[str, ...] = (),
) -> None:
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str):
        errors.append("shard relative_path is missing or not a string")
        return
    if any(token in relative.lower() for token in forbidden_name_tokens):
        errors.append(f"forbidden vector shard name: {relative}")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        errors.append(f"shard escapes raw root: {relative}")
        return
    if not path.is_file():
        errors.append(f"missing shard: {path}")
        return
    if int(descriptor.get("bytes", -1)) != path.stat().st_size:
        errors.append(f"shard byte mismatch: {relative}")
    if str(descriptor.get("sha256", "")) != _sha256(path):
        errors.append(f"shard SHA mismatch: {relative}")
    try:
        values = np.asarray(np.load(path, allow_pickle=False))
    except Exception as exc:
        errors.append(f"shard cannot be loaded: {relative}: {exc}")
        return
    if str(descriptor.get("dtype")) != str(values.dtype):
        errors.append(f"shard dtype mismatch: {relative}")
    if list(descriptor.get("shape", ())) != list(values.shape):
        errors.append(f"shard shape mismatch: {relative}")
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        errors.append(f"shard is not a finite one-dimensional vector: {relative}")


def _load_artifact(
    artifact: dict[str, Any], errors: list[str], *, expected_root: Path
) -> np.ndarray | None:
    root_value = artifact.get("root")
    if not isinstance(root_value, str):
        errors.append("artifact root is missing")
        return None
    root = Path(root_value).resolve()
    if root != expected_root:
        errors.append(f"artifact root mismatch: {root} != {expected_root}")
        return None
    shards = artifact.get("shards")
    if not isinstance(shards, list) or not shards:
        errors.append(f"artifact {artifact.get('name', '<unnamed>')} has no shards")
        return None
    arrays: list[np.ndarray] = []
    for shard in shards:
        if not isinstance(shard, dict):
            errors.append("artifact contains a malformed shard descriptor")
            continue
        _check_shard(root, shard, errors)
        path_value = shard.get("relative_path")
        if isinstance(path_value, str):
            path = (root / path_value).resolve()
            if root not in path.parents:
                continue
            try:
                arrays.append(np.asarray(np.load(path, allow_pickle=False)))
            except Exception:
                pass
    if not arrays:
        return None
    return np.concatenate(arrays)


def _check_metric(
    stored: Any, actual: float, errors: list[str], name: str
) -> None:
    if not _finite_number(stored):
        errors.append(f"{name} is missing or non-finite")
        return
    tolerance = 1.0e-14 * max(1.0, abs(float(actual)))
    if abs(float(stored) - float(actual)) > tolerance:
        errors.append(f"{name} does not match raw artifact recomputation")


def _check_pc_legality(
    record: dict[str, Any],
    artifacts: dict[str, Any],
    raw_root: Path,
    errors: list[str],
    gates: list[str],
) -> None:
    pc = record.get("pc_legality")
    fixture_audit = record.get("fixture_audit")
    if not isinstance(pc, dict) or not isinstance(fixture_audit, dict):
        errors.append("pc_legality and fixture_audit are required")
        return
    if pc.get("direction_construction") != "PETSc_global_row_parity":
        errors.append("PC direction construction is not PETSc_global_row_parity")
    expected_names = {
        "input_first_before",
        "input_first_after",
        "input_second_before",
        "input_second_after",
        "input_combined_before",
        "input_combined_after",
        "output_first",
        "output_second",
        "output_combined",
        "output_repeat",
    }
    if set(pc.get("artifact_names", ())) != expected_names:
        errors.append("PC artifact_names do not match the fixed legality probe")
    arrays: dict[str, np.ndarray] = {}
    for name in sorted(expected_names):
        artifact = artifacts.get(name)
        if not isinstance(artifact, dict):
            errors.append(f"missing PC artifact: {name}")
            continue
        values = _load_artifact(artifact, errors, expected_root=raw_root)
        if values is not None:
            arrays[name] = values
    if len(arrays) != len(expected_names):
        return
    shapes = {values.shape for values in arrays.values()}
    if len(shapes) != 1:
        errors.append("PC legality artifacts do not have one vector shape")
        return
    if not all(np.all(np.isfinite(values)) for values in arrays.values()):
        gates.append("PC legality contains a non-finite vector")

    input_pairs = (
        ("first", "input_first_before", "input_first_after"),
        ("second", "input_second_before", "input_second_after"),
        ("combined", "input_combined_before", "input_combined_after"),
    )
    input_unchanged = 0.0
    for label, before_name, after_name in input_pairs:
        before = arrays[before_name]
        after = arrays[after_name]
        if not np.array_equal(before, after):
            gates.append(f"PC input {label} changed during apply")
        input_unchanged = max(input_unchanged, _relative(after, before))
    first = arrays["output_first"]
    second = arrays["output_second"]
    combined = arrays["output_combined"]
    repeat = arrays["output_repeat"]
    alpha_pair = pc.get("alpha")
    beta_pair = pc.get("beta")
    if (
        not isinstance(alpha_pair, list)
        or len(alpha_pair) != 2
        or not isinstance(beta_pair, list)
        or len(beta_pair) != 2
    ):
        errors.append("PC complex linearity coefficients are missing")
        return
    alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
    beta = complex(float(beta_pair[0]), float(beta_pair[1]))
    expected = alpha * first + beta * second
    linearity = _relative(combined, expected)
    repeat_relative = _relative(repeat, combined)
    finite = all(np.all(np.isfinite(values)) for values in arrays.values())
    slave_indices = pc.get("slave_local_indices")
    if not isinstance(slave_indices, list) or not slave_indices:
        errors.append("PC slave_local_indices are missing")
        slave_constraint = float("nan")
    else:
        if any(
            not isinstance(value, int) or value < 0 or value >= combined.size
            for value in slave_indices
        ):
            errors.append("PC slave_local_indices are out of bounds")
            slave_constraint = float("nan")
        else:
            slave_constraint = float(np.max(np.abs(combined[slave_indices])))
    first_norm = float(np.linalg.norm(arrays["input_first_before"]))
    second_norm = float(np.linalg.norm(arrays["input_second_before"]))
    combined_norm = float(np.linalg.norm(arrays["input_combined_before"]))
    for name, actual in (
        ("first_global_norm", first_norm),
        ("second_global_norm", second_norm),
        ("combined_global_norm", combined_norm),
        ("linearity_relative", linearity),
        ("repeat_relative", repeat_relative),
        ("input_unchanged_relative", input_unchanged),
        ("slave_constraint_absolute", slave_constraint),
    ):
        _check_metric(pc.get(name), actual, errors, f"pc_legality.{name}")
    if not all(value > 0.0 for value in (first_norm, second_norm, combined_norm)):
        gates.append("PC legality directions must have nonzero global norms")
    if not finite:
        gates.append("PC legality finite gate failed")
    if linearity > 1.0e-12:
        gates.append("PC legality linearity exceeds 1e-12")
    if repeat_relative > 1.0e-13:
        gates.append("PC legality repeat exceeds 1e-13")
    if input_unchanged > 0.0:
        gates.append("PC legality input unchanged gate failed")
    if np.isfinite(slave_constraint) and slave_constraint > 1.0e-12:
        gates.append("PC legality slave constraint exceeds 1e-12")

    if pc.get("finite") is not finite:
        errors.append("pc_legality.finite disagrees with raw artifacts")
    if pc.get("slave_master_complete") is not fixture_audit.get("slave_master_complete"):
        errors.append("PC slave_master_complete is not bound to fixture audit")
    if pc.get("slave_master_complete") is not True:
        errors.append("PC slave_master_complete is not true")
    if pc.get("phase_application") != fixture_audit.get("phase_application"):
        errors.append("PC phase_application is not bound to fixture audit")
    if pc.get("phase_application") != "finalized_floquet_mpc_once":
        errors.append("PC phase_application is not the frozen finalized MPC contract")
    hx_audit = fixture_audit.get("hx_audit")
    if not isinstance(hx_audit, dict):
        errors.append("fixture_audit.hx_audit is missing")
        hx_audit = {}
    expected_high_aij = bool(
        fixture_audit.get("high_order_global_aij") or hx_audit.get("high_order_aij")
    )
    expected_direct = bool(hx_audit.get("global_direct_coarse"))
    expected_allgather = bool(
        fixture_audit.get("global_numeric_allgather")
        or hx_audit.get("global_numeric_allgather")
    )
    for name, actual in (
        ("high_order_global_aij", expected_high_aij),
        ("global_direct_coarse", expected_direct),
        ("numeric_allgather", expected_allgather),
    ):
        if pc.get(name) is not actual:
            errors.append(f"pc_legality.{name} is not bound to fixture audit")
        if actual:
            errors.append(f"forbidden PC audit is true: {name}")


def _check_checkpoint(
    checkpoint: dict[str, Any],
    provenance: dict[str, Any],
    raw_root: Path,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    manifest_path_value = checkpoint.get("manifest_path")
    if not isinstance(manifest_path_value, str):
        errors.append("checkpoint.manifest_path is missing")
        return {}
    manifest_path = Path(manifest_path_value).resolve()
    checkpoint_root = (raw_root / "checkpoint-20").resolve()
    if not Path(manifest_path_value).is_absolute() or manifest_path != checkpoint_root / "manifest.json":
        errors.append("checkpoint manifest is not raw_dir/checkpoint-20/manifest.json")
        return {}
    if not manifest_path.is_file():
        errors.append(f"missing checkpoint manifest: {manifest_path}")
        return {}
    actual_manifest_sha = _sha256(manifest_path)
    if checkpoint.get("manifest_sha256") != actual_manifest_sha:
        errors.append("record checkpoint manifest SHA mismatch")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"checkpoint manifest JSON is invalid: {exc}")
        return {}
    if manifest.get("schema") != CHECKPOINT_SCHEMA:
        errors.append("checkpoint schema mismatch")
    if manifest.get("iteration") != 20 or checkpoint.get("iteration") != 20:
        errors.append("P0 checkpoint must be the global iteration-20 checkpoint")
    manifest_residual = manifest.get("explicit_true_residual")
    checkpoint_residual = checkpoint.get("explicit_true_residual")
    if not _finite_number(manifest_residual) or float(manifest_residual) < 0.0:
        errors.append("checkpoint manifest explicit_true_residual is invalid")
    if not _finite_number(checkpoint_residual) or float(checkpoint_residual) < 0.0:
        errors.append("checkpoint explicit_true_residual is missing or invalid")
    if _finite_number(manifest_residual) and _finite_number(checkpoint_residual) and not np.isclose(
        float(manifest_residual),
        float(checkpoint_residual),
        rtol=1.0e-14,
        atol=1.0e-15,
    ):
        errors.append("checkpoint explicit_true_residual manifest/record mismatch")
    for key in (
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
        "source_sha",
    ):
        if manifest.get(key) != provenance.get(key):
            errors.append(f"checkpoint provenance mismatch: {key}")
    for key in (
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
    ):
        if not _valid_hex(manifest.get(key), 64):
            errors.append(f"checkpoint manifest {key} is not a 64-character lowercase SHA256")
    if not _valid_hex(manifest.get("source_sha"), 40):
        errors.append("checkpoint manifest source_sha is not a 40-character lowercase Git SHA")
    if manifest.get("mpi_size") != 1 or checkpoint.get("mpi_size") != 1:
        errors.append("P0 checkpoint MPI size must be one")
    if manifest.get("solution_only") is not True:
        errors.append("checkpoint is not marked solution_only")
    if manifest.get("numeric_allgather") is not False:
        errors.append("checkpoint numeric_allgather must be false")
    if manifest.get("vector_roles") != ["solution"]:
        errors.append("checkpoint must contain only the solution role")
    if set(manifest.get("forbidden_vector_roles", ())) != {
        "action",
        "residual",
        "krylov_basis",
    }:
        errors.append("checkpoint forbidden vector role contract mismatch")
    ranks = manifest.get("ranks")
    if not isinstance(ranks, list) or len(ranks) != 1:
        errors.append("checkpoint rank metadata is incomplete")
        return manifest
    fact = ranks[0]
    if fact.get("rank") != 0:
        errors.append("checkpoint rank metadata is not rank zero")
    if set(fact) != {"rank", "ownership", "solution"}:
        errors.append("checkpoint contains a second vector descriptor")
    solution_descriptor = fact.get("solution")
    if not isinstance(solution_descriptor, dict):
        errors.append("checkpoint solution descriptor is missing")
    else:
        _check_shard(
            checkpoint_root,
            solution_descriptor,
            errors,
            forbidden_name_tokens=("action", "residual", "basis", "before", "reference"),
        )
    declared = {"manifest.json"}
    if isinstance(solution_descriptor, dict) and isinstance(
        solution_descriptor.get("relative_path"), str
    ):
        declared.add(str(solution_descriptor["relative_path"]))
    actual = {path.name for path in checkpoint_root.iterdir()}
    if actual != declared:
        errors.append(
            "checkpoint directory contents do not exactly match manifest: "
            f"declared={sorted(declared)}, actual={sorted(actual)}"
        )
    roundtrip = checkpoint.get("roundtrip_relative")
    if not _finite_number(roundtrip):
        errors.append("checkpoint roundtrip_relative is missing or non-finite")
    elif float(roundtrip) > ROUNDTRIP_LIMIT:
        gates.append(f"checkpoint roundtrip {float(roundtrip):.17g} > {ROUNDTRIP_LIMIT:.17g}")
    return manifest


def _check_cycle(
    cycle: dict[str, Any], index: int, errors: list[str], gates: list[str]
) -> None:
    required = {
        "cycle_index",
        "start_iteration",
        "end_iteration",
        "iterations",
        "reason",
        "initial_guess_nonzero",
        "reported_final_residual",
        "explicit_true_residual",
        "matvec_count",
        "pc_apply_count",
        "wall_seconds",
        "resource",
        "ksp_destroyed",
    }
    missing = sorted(required.difference(cycle))
    if missing:
        errors.append(f"cycle {index} missing fields: {','.join(missing)}")
        return
    if int(cycle["end_iteration"]) - int(cycle["start_iteration"]) != int(cycle["iterations"]):
        errors.append(f"cycle {index} iteration boundary mismatch")
    if int(cycle["iterations"]) < 0 or int(cycle["iterations"]) > 20:
        errors.append(f"cycle {index} exceeds restart-20 limit")
    if cycle["ksp_destroyed"] is not True:
        errors.append(f"cycle {index} KSP was not destroyed before the next boundary")
    for key in ("reported_final_residual", "explicit_true_residual", "wall_seconds"):
        if not _finite_number(cycle[key]) or float(cycle[key]) < 0.0:
            errors.append(f"cycle {index} has invalid {key}")
    for key in ("matvec_count", "pc_apply_count"):
        if not isinstance(cycle[key], int) or int(cycle[key]) < 0:
            errors.append(f"cycle {index} has invalid {key}")
    resource = cycle["resource"]
    if not isinstance(resource, dict):
        errors.append(f"cycle {index} resource facts are missing")
    else:
        for key in (
            "process_tree_rss_bytes",
            "process_tree_swap_bytes",
            "memory_authority_bytes",
        ):
            if not isinstance(resource.get(key), int) or int(resource[key]) < 0:
                errors.append(f"cycle {index} resource.{key} is missing or invalid")
        if resource.get("all_status_readable") is not True:
            errors.append(f"cycle {index} process-tree status was not readable")
        if resource.get("process_tree_swap_bytes") != 0:
            gates.append(f"cycle {index} process-tree swap is nonzero")
        dedicated_swap = resource.get("dedicated_cgroup_swap_bytes")
        if dedicated_swap is not None and (
            not isinstance(dedicated_swap, int) or dedicated_swap != 0
        ):
            gates.append(f"cycle {index} dedicated cgroup swap is nonzero")
        if resource.get("job_no_swap") is not True:
            gates.append(f"cycle {index} resource authority reports swap")


def check_record(record_path: Path) -> dict[str, Any]:
    """Check one record and return separate contract and gate failures."""

    record_path = Path(record_path).resolve()
    errors: list[str] = []
    gates: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"passed": False, "contract_errors": [f"invalid record JSON: {exc}"], "gate_failures": []}
    if not isinstance(record, dict):
        return {"passed": False, "contract_errors": ["record must be a JSON object"], "gate_failures": []}
    if record.get("schema") != SCHEMA:
        errors.append("record schema mismatch")
    if record.get("stage") != "p0" or record.get("case") != "p2-mpi1":
        errors.append("record case/stage is not the frozen P0 p2-mpi1 case")
    if record.get("degree") != 2 or record.get("h_nm") != 50.0 or record.get("source_name") != "random":
        errors.append("record fixture identity mismatch")

    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source identity is missing")
        source = {}
    source_sha = source.get("expected_sha")
    if not _valid_hex(source_sha, SOURCE_SHA_LENGTH):
        errors.append("source.expected_sha is not a 40-character lowercase Git SHA")
    if source.get("branch") != BRANCH:
        errors.append("source branch mismatch")
    if source.get("commit_sha_start") != source_sha or source.get("commit_sha_end") != source_sha:
        errors.append("source commit SHA is not bound to expected_sha")
    if source.get("clean_start") is not True or source.get("clean_end") is not True:
        errors.append("source clean identity is not true")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime identity is missing")
    else:
        for key, expected in (("qualified_activation", "1"), ("petsc_scalar_type", "complex128"), ("petsc_int_type", "int32")):
            if runtime.get(key) != expected:
                errors.append(f"runtime.{key} mismatch")
        if runtime.get("mpi_size") != 1:
            errors.append("runtime MPI size mismatch")

    settings = record.get("settings")
    if not isinstance(settings, dict):
        errors.append("settings are missing")
        settings = {}
    exact_settings = {
        "variant": "sequential-v1",
        "restart": 20,
        "cycle_max_it": 20,
        "max_it": 40,
        "right_preconditioned": True,
        "norm_type": "unpreconditioned",
        "residual_replacement": True,
        "additive_v2": False,
    }
    for key, expected in exact_settings.items():
        if settings.get(key) != expected:
            errors.append(f"settings.{key} mismatch")

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance is missing")
        provenance = {}
    for key in (
        "source_sha",
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
    ):
        value = provenance.get(key)
        expected_length = SOURCE_SHA_LENGTH if key == "source_sha" else 64
        if not _valid_hex(value, expected_length):
            errors.append(f"provenance.{key} is not a {expected_length}-character lowercase hex SHA")
    if provenance.get("source_sha") != source_sha:
        errors.append("provenance.source_sha differs from source identity")

    raw_dir_value = record.get("raw_dir")
    if not isinstance(raw_dir_value, str) or not raw_dir_value:
        errors.append("record.raw_dir is missing")
        raw_root = record_path.parent
    else:
        raw_root = Path(raw_dir_value).resolve()
        if not raw_root.is_dir():
            errors.append(f"record.raw_dir is not an existing directory: {raw_root}")
        if record_path == raw_root or raw_root in record_path.parents:
            errors.append("record path must remain outside raw_dir")

    authorities = record.get("old_authorities")
    if not isinstance(authorities, dict):
        errors.append("old immutable authority facts are missing")
    else:
        if authorities.get("old_l2_one_apply_rho") != 1.7348663090876784:
            errors.append("old L2 rho authority changed")
        if authorities.get("old_l2_classification") != "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE":
            errors.append("old L2 classification changed")
        if authorities.get("old_k1_v1_80_step") != "FAIL" or authorities.get("additive_v2") != "CLOSED":
            errors.append("old K1/additive authority changed")

    outer = record.get("outer")
    if not isinstance(outer, dict):
        errors.append("outer cycle facts are missing")
        outer = {}
    for key in (
        "production_first_cycle",
        "restart",
        "continuous_reference",
        "checkpoint",
        "boundary_true_residual",
        "restart_boundary_true_residual_relative",
        "post_rebuild_solution_roundtrip_relative",
        "rebuilt_provenance",
        "next_cycle_first_true_residual_relative",
    ):
        if key not in outer:
            errors.append(f"outer.{key} is missing")
    for label in ("production_first_cycle", "restart", "continuous_reference"):
        value = outer.get(label)
        if not isinstance(value, dict):
            errors.append(f"outer.{label} is not an object")
            continue
        cycles = value.get("cycles")
        if not isinstance(cycles, list) or not cycles:
            errors.append(f"outer.{label}.cycles is missing")
            continue
        for count_name, expected_count in (
            ("explicit_action_count", len(cycles) + 1),
            ("ksp_destroy_count", len(cycles)),
        ):
            count = value.get(count_name)
            if not isinstance(count, int) or count != expected_count:
                errors.append(
                    f"outer.{label}.{count_name} must equal {expected_count}"
                )
        for index, cycle in enumerate(cycles):
            if isinstance(cycle, dict):
                _check_cycle(cycle, index, errors, gates)
            else:
                errors.append(f"outer.{label}.cycle {index} is not an object")
    first_cycles = outer.get("production_first_cycle", {}).get("cycles", [])
    restart_cycles = outer.get("restart", {}).get("cycles", [])
    continuous_cycles = outer.get("continuous_reference", {}).get("cycles", [])
    if len(first_cycles) != 1 or first_cycles[0].get("start_iteration") != 0 or first_cycles[0].get("end_iteration") != 20:
        errors.append("first production cycle is not the required 0-to-20 segment")
    if not restart_cycles or restart_cycles[0].get("start_iteration") != 20:
        errors.append("resumed cycle does not start at global iteration 20")
    if len(continuous_cycles) < 2:
        errors.append("continuous reference did not retain two scalar cycle boundaries")
    checkpoint = outer.get("checkpoint")
    if isinstance(checkpoint, dict):
        _check_checkpoint(checkpoint, provenance, raw_root, errors, gates)
        boundary_value = outer.get("boundary_true_residual")
        checkpoint_value = checkpoint.get("explicit_true_residual")
        if not _finite_number(boundary_value) or float(boundary_value) < 0.0:
            errors.append("outer boundary_true_residual is missing or invalid")
        elif _finite_number(checkpoint_value) and not np.isclose(
            float(boundary_value),
            float(checkpoint_value),
            rtol=1.0e-14,
            atol=1.0e-15,
        ):
            errors.append("checkpoint explicit residual differs from iteration-20 boundary")
        if first_cycles and isinstance(first_cycles[0], dict) and _finite_number(checkpoint_value) and not np.isclose(
            float(first_cycles[0].get("explicit_true_residual", float("nan"))),
            float(checkpoint_value),
            rtol=1.0e-14,
            atol=1.0e-15,
        ):
            errors.append("checkpoint explicit residual differs from first cycle ledger")
    if _finite_number(outer.get("restart_boundary_true_residual_relative")):
        if float(outer["restart_boundary_true_residual_relative"]) > BOUNDARY_LIMIT:
            gates.append("restart boundary true residual exceeds 1e-12")
    else:
        errors.append("restart boundary true residual fact is missing")
    if _finite_number(outer.get("post_rebuild_solution_roundtrip_relative")):
        if float(outer["post_rebuild_solution_roundtrip_relative"]) > ROUNDTRIP_LIMIT:
            gates.append("post-rebuild solution roundtrip exceeds 1e-13")
    else:
        errors.append("post-rebuild solution roundtrip fact is missing")
    rebuilt = outer.get("rebuilt_provenance")
    if not isinstance(rebuilt, dict):
        errors.append("outer.rebuilt_provenance is missing")
    else:
        expected_identity_keys = {
            "source_sha",
            "input_identity_sha256",
            "operator_identity_sha256",
            "physical_model_sha256",
        }
        if set(rebuilt) != expected_identity_keys:
            errors.append("outer.rebuilt_provenance fields are incomplete")
        for key in expected_identity_keys:
            expected_length = SOURCE_SHA_LENGTH if key == "source_sha" else 64
            if not _valid_hex(rebuilt.get(key), expected_length):
                errors.append(f"outer.rebuilt_provenance.{key} has invalid SHA")
            elif rebuilt.get(key) != provenance.get(key):
                errors.append(f"outer.rebuilt_provenance.{key} differs from initial provenance")
    if _finite_number(outer.get("next_cycle_first_true_residual_relative")):
        if float(outer["next_cycle_first_true_residual_relative"]) > NEXT_CYCLE_LIMIT:
            gates.append("next-cycle first true residual exceeds 1e-11")
    else:
        errors.append("next-cycle first true residual fact is missing")

    artifacts = record.get("artifacts")
    pc = record.get("pc_legality")
    expected_pc_names = {
        "input_first_before",
        "input_first_after",
        "input_second_before",
        "input_second_after",
        "input_combined_before",
        "input_combined_after",
        "output_first",
        "output_second",
        "output_combined",
        "output_repeat",
    }
    expected_artifact_names = {"source", "residual"} | expected_pc_names
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifact_names:
        errors.append("record artifacts do not match the source/residual/PC contract")
    else:
        for name, artifact in artifacts.items():
            if not isinstance(artifact, dict) or not isinstance(artifact.get("shards"), list):
                errors.append(f"artifact {name} shard manifest is missing")
                continue
            if artifact.get("name") != name or artifact.get("role") != name:
                errors.append(f"artifact {name} name/role identity mismatch")
            _load_artifact(artifact, errors, expected_root=raw_root)
        _check_pc_legality(record, artifacts, raw_root, errors, gates)

    passed = not errors and not gates
    return {
        "passed": passed,
        "contract_errors": errors,
        "gate_failures": gates,
        "facts": {
            "source_sha": source_sha,
            "checkpoint_manifest_sha256": record.get("outer", {}).get("checkpoint", {}).get("manifest_sha256"),
            "final_true_residual": record.get("outer", {}).get("restart", {}).get("final_true_residual"),
        },
    }


def check_pair(record_one_path: Path, record_two_path: Path, *, physical: bool) -> dict[str, Any]:
    """Check two records and a measured cross-MPI action metric."""

    one = check_record(record_one_path)
    two = check_record(record_two_path)
    contract_errors = list(one["contract_errors"]) + list(two["contract_errors"])
    gate_failures = list(one["gate_failures"]) + list(two["gate_failures"])
    first = json.loads(Path(record_one_path).read_text(encoding="utf-8"))
    second = json.loads(Path(record_two_path).read_text(encoding="utf-8"))
    first_sha = first.get("source", {}).get("expected_sha")
    second_sha = second.get("source", {}).get("expected_sha")
    if first_sha != second_sha:
        contract_errors.append("pair source SHA mismatch")
    pair_metrics = first.get("pair_metrics")
    if not isinstance(pair_metrics, dict):
        contract_errors.append("pair_metrics are required measured raw facts")
        pair_metrics = {}
    rhs_identity = pair_metrics.get("rhs_identity_relative")
    action_relative = pair_metrics.get("action_relative")
    if not _finite_number(rhs_identity) or not _finite_number(action_relative):
        contract_errors.append("pair_metrics RHS/action facts are missing or non-finite")
    else:
        try:
            bound = residual_pair_bound(
                float(first["outer"]["restart"]["final_true_residual"]),
                float(second["outer"]["restart"]["final_true_residual"]),
                float(rhs_identity),
                physical=physical,
            )
            if float(action_relative) > bound:
                gate_failures.append(
                    f"cross-MPI action {float(action_relative):.17g} > residual bound {bound:.17g}"
                )
        except (KeyError, TypeError, ValueError) as exc:
            contract_errors.append(f"pair residual facts are invalid: {exc}")
            bound = None
    return {
        "passed": not contract_errors and not gate_failures,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "pair_bound": bound if "bound" in locals() else None,
        "rhs_identity_relative": rhs_identity,
        "action_relative": action_relative,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--physical", action="store_true")
    args = parser.parse_args(argv)
    if len(args.record) == 1:
        result = check_record(args.record[0])
    elif len(args.record) == 2:
        result = check_pair(args.record[0], args.record[1], physical=args.physical)
    else:
        result = {
            "passed": False,
            "contract_errors": ["checker accepts one record or one pair"],
            "gate_failures": [],
        }
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
