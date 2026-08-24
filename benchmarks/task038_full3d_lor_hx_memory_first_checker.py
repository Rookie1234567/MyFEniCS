"""Independent stdlib/NumPy checker for the V9 P1 memory-first facts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-native-complex-hx.memory-first-p1-record.v1"
CASES = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
}
SOURCES = ("random", "gradient", "curl", "checkerboard")
SOURCE_FORMULAS = {
    "random": "analytic deterministic pseudo-random edge field from fixed noninteger trigonometric frequencies and phases",
    "gradient": "grad(sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz))",
    "curl": "curl((0,0,sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz)))",
    "checkerboard": "R4 fixed 8-cycle field: (high_x*high_y*high_z, high_y*high_z, high_z*high_x)",
}
SUITE_ORDER = tuple(f"{case}/{source}" for case in CASES for source in SOURCES)
CHECKPOINT_POINTS = (20, 80, 200, 500, 1000, 2000)
CHECKPOINT_INTERVAL = 200
RESIDUAL_LIMIT = 1.0e-8
SMALL_PAIR_MARGIN = 1.0e-11
OLD_L2_RECORD_SHA = "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3"
OLD_L2_RHO = 1.7348663090876784
OLD_L2_CLASSIFICATION = "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        raise ValueError("relative operands have different shapes")
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny))


def _path_inside(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("artifact escapes raw_dir")
    return path


def _descriptor_array(root: Path, descriptor: dict[str, Any], label: str) -> np.ndarray:
    required = {"relative_path", "bytes", "sha256", "dtype", "shape"}
    if set(descriptor) != required:
        raise ValueError(f"{label} descriptor keys are incomplete")
    path = _path_inside(root, str(descriptor["relative_path"]))
    if not path.is_file():
        raise ValueError(f"{label} artifact is missing")
    if int(descriptor["bytes"]) != path.stat().st_size:
        raise ValueError(f"{label} byte count mismatch")
    if _sha256(path) != descriptor["sha256"]:
        raise ValueError(f"{label} SHA256 mismatch")
    values = np.asarray(np.load(path, allow_pickle=False))
    if str(values.dtype) != descriptor["dtype"] or list(values.shape) != list(descriptor["shape"]):
        raise ValueError(f"{label} dtype/shape mismatch")
    if values.ndim != 1:
        raise ValueError(f"{label} must be one-dimensional")
    return values


def _load_role(record: dict[str, Any], role: str, errors: list[str]) -> tuple[np.ndarray | None, np.ndarray | None]:
    artifacts = record.get("canonical_artifacts")
    if not isinstance(artifacts, dict) or role not in artifacts:
        errors.append(f"canonical role {role} is missing")
        return None, None
    section = artifacts[role]
    root = Path(str(record.get("raw_dir", ""))).resolve()
    if not root.is_absolute() or not root.is_dir():
        errors.append("raw_dir is missing or not a directory")
        return None, None
    expected_role = {"source": "primal", "rhs": "dual", "final_solution": "primal", "final_action": "dual", "final_true_residual": "dual"}[role]
    if not isinstance(section, dict) or section.get("role") != expected_role:
        errors.append(f"canonical role {role} has the wrong semantic role")
        return None, None
    shards = section.get("shards")
    mpi_size = int(record.get("mpi_size", -1))
    if not isinstance(shards, list) or len(shards) != mpi_size:
        errors.append(f"canonical role {role} does not have one shard per rank")
        return None, None
    key_parts: list[np.ndarray] = []
    value_parts: list[np.ndarray] = []
    ranks: list[int] = []
    for shard in shards:
        if not isinstance(shard, dict):
            errors.append(f"canonical role {role} has a malformed shard")
            continue
        rank = shard.get("rank")
        ranks.append(int(rank) if isinstance(rank, int) else -1)
        if shard.get("role") != expected_role:
            errors.append(f"canonical role {role} shard semantic role mismatch")
            continue
        try:
            keys = _descriptor_array(root, shard["keys"], f"{role}.rank{rank}.keys")
            values = _descriptor_array(root, shard["values"], f"{role}.rank{rank}.values")
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append(str(exc))
            continue
        if str(keys.dtype) != "<U64" or str(values.dtype) != "complex128":
            errors.append(f"canonical role {role} has an invalid dtype")
        if keys.size != values.size:
            errors.append(f"canonical role {role} keys and values do not align")
        if not np.all(np.isfinite(values)):
            errors.append(f"canonical role {role} contains non-finite values")
        key_parts.append(keys)
        value_parts.append(values)
    if sorted(ranks) != list(range(mpi_size)):
        errors.append(f"canonical role {role} rank shards are not a complete permutation")
    if not key_parts:
        return None, None
    keys = np.concatenate(key_parts)
    values = np.concatenate(value_parts)
    if len(set(keys.tolist())) != keys.size:
        errors.append(f"canonical role {role} has duplicate keys")
    return keys, values


def _load_pc_layout(
    record: dict[str, Any], name: str, errors: list[str]
) -> tuple[np.ndarray | None, list[dict[str, Any]]]:
    pc = record.get("pc_legality")
    artifacts = pc.get("pc_artifacts") if isinstance(pc, dict) else None
    section = artifacts.get(name) if isinstance(artifacts, dict) else None
    if not isinstance(section, dict):
        errors.append(f"P1 PC raw layout {name} is missing")
        return None, []
    expected_role = "dual" if name.startswith("pc_input") else "primal"
    if section.get("role") != expected_role:
        errors.append(f"P1 PC raw layout {name} has the wrong semantic role")
    mpi_size = int(record.get("mpi_size", -1))
    shards = section.get("shards")
    if not isinstance(shards, list) or len(shards) != mpi_size:
        errors.append(f"P1 PC raw layout {name} does not cover every rank")
        return None, []
    root = Path(str(record.get("raw_dir", ""))).resolve()
    ranges: list[tuple[int, int, int, np.ndarray]] = []
    ranks: list[int] = []
    global_sizes: set[int] = set()
    for shard in shards:
        if not isinstance(shard, dict):
            errors.append(f"P1 PC raw layout {name} has a malformed shard")
            continue
        rank = shard.get("rank")
        ownership = shard.get("ownership_range")
        try:
            rank = int(rank)
            start, stop = (int(ownership[0]), int(ownership[1]))
            values = _descriptor_array(root, shard["values"], f"{name}.rank{rank}")
        except (KeyError, TypeError, ValueError, OSError, IndexError) as exc:
            errors.append(str(exc))
            continue
        local_size = shard.get("local_size")
        global_size = shard.get("global_size")
        if not isinstance(local_size, int) or local_size != values.size or stop - start != values.size:
            errors.append(f"P1 PC raw layout {name} rank {rank} ownership/local size mismatch")
        if not isinstance(global_size, int) or global_size <= 0:
            errors.append(f"P1 PC raw layout {name} rank {rank} global size is invalid")
        else:
            global_sizes.add(global_size)
        if values.dtype != np.dtype("complex128") or not np.all(np.isfinite(values)):
            errors.append(f"P1 PC raw layout {name} rank {rank} is not finite complex128")
        ranks.append(rank)
        ranges.append((start, stop, rank, values))
    if sorted(ranks) != list(range(mpi_size)):
        errors.append(f"P1 PC raw layout {name} rank IDs are incomplete")
    if len(global_sizes) != 1:
        errors.append(f"P1 PC raw layout {name} global size is not rank-closed")
    ranges.sort(key=lambda item: item[0])
    expected_start = 0
    for start, stop, _rank, _values in ranges:
        if start != expected_start or stop < start:
            errors.append(f"P1 PC raw layout {name} ownership has a gap or overlap")
        expected_start = stop
    if global_sizes and expected_start != next(iter(global_sizes)):
        errors.append(f"P1 PC raw layout {name} ownership does not close globally")
    if not ranges:
        return None, []
    return np.concatenate([item[3] for item in ranges]), [
        {"start": start, "stop": stop, "rank": rank, "values": values}
        for start, stop, rank, values in ranges
    ]


def _align_to(
    target_keys: np.ndarray,
    keys: np.ndarray,
    values: np.ndarray,
    label: str,
    errors: list[str],
) -> np.ndarray | None:
    if len(set(target_keys.tolist())) != target_keys.size or len(set(keys.tolist())) != keys.size:
        errors.append(f"{label} contains duplicate canonical keys")
        return None
    if set(target_keys.tolist()) != set(keys.tolist()):
        errors.append(f"{label} canonical key set does not close")
        return None
    index = {key: position for position, key in enumerate(keys.tolist())}
    return np.asarray([values[index[key]] for key in target_keys.tolist()], dtype=np.complex128)


def _process_tree_facts(resource: dict[str, Any]) -> tuple[Any, Any, Any]:
    process_tree = resource.get("process_tree")
    if isinstance(process_tree, dict):
        return (
            process_tree.get("rss_bytes"),
            process_tree.get("swap_bytes"),
            process_tree.get("all_status_readable"),
        )
    return (
        resource.get("process_tree_rss_bytes"),
        resource.get("process_tree_swap_bytes"),
        resource.get("all_status_readable"),
    )


def _check_checkpoint(record: dict[str, Any], errors: list[str]) -> None:
    statuses = record.get("checkpoint_status")
    if not isinstance(statuses, dict) or set(statuses) != {str(point) for point in CHECKPOINT_POINTS}:
        errors.append("P1 checkpoint status points are incomplete")
        return
    facts = record.get("checkpoint_facts")
    if not isinstance(facts, list):
        errors.append("P1 checkpoint facts are missing")
        return
    measured_iterations = {int(fact.get("iteration", -1)) for fact in facts if isinstance(fact, dict)}
    for point in CHECKPOINT_POINTS:
        status = statuses[str(point)].get("status") if isinstance(statuses[str(point)], dict) else None
        if point % CHECKPOINT_INTERVAL == 0 and status == "measured" and point not in measured_iterations:
            errors.append(f"P1 measured checkpoint {point} has no raw fact")
        if point % CHECKPOINT_INTERVAL != 0 and status == "measured":
            errors.append(f"P1 non-cadence point {point} was marked as a checkpoint")
    raw_root = Path(str(record.get("raw_dir", ""))).resolve()
    cycles = record.get("cycles")
    for fact in facts:
        if not isinstance(fact, dict):
            errors.append("malformed checkpoint fact")
            continue
        iteration = int(fact.get("iteration", -1))
        if iteration <= 0 or iteration % CHECKPOINT_INTERVAL:
            errors.append("P1 checkpoint cadence is not every 200 iterations")
        boundary_values = [
            float(cycle.get("explicit_true_residual"))
            for cycle in cycles
            if isinstance(cycle, dict) and cycle.get("end_iteration") == iteration
        ] if isinstance(cycles, list) else []
        if len(boundary_values) != 1 or not np.isclose(
            float(fact.get("explicit_true_residual", float("nan"))),
            boundary_values[0] if boundary_values else float("nan"),
            rtol=1.0e-14,
            atol=1.0e-15,
        ):
            errors.append("P1 checkpoint residual does not match its cycle boundary")
        path = Path(str(fact.get("manifest_path", ""))).resolve()
        if raw_root not in path.parents or path.name != "manifest.json":
            errors.append("P1 checkpoint manifest is outside raw_dir")
            continue
        if not path.is_file() or _sha256(path) != fact.get("manifest_sha256"):
            errors.append("P1 checkpoint manifest hash is invalid")
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("P1 checkpoint manifest is unreadable")
            continue
        if manifest.get("iteration") != iteration or not np.isfinite(float(manifest.get("explicit_true_residual", float("nan")))):
            errors.append("P1 checkpoint explicit residual is missing or invalid")
        if not np.isclose(
            float(manifest.get("explicit_true_residual", float("nan"))),
            float(fact.get("explicit_true_residual", float("nan"))),
            rtol=1.0e-14,
            atol=1.0e-15,
        ):
            errors.append("P1 checkpoint fact and manifest residual do not close")
        provenance = record.get("provenance")
        source = record.get("source")
        if not isinstance(provenance, dict) or not isinstance(source, dict):
            errors.append("P1 checkpoint provenance cannot bind without record identity")
        else:
            for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
                if manifest.get(key) != provenance.get(key):
                    errors.append(f"P1 checkpoint {key} does not match record provenance")
            if manifest.get("source_sha") != source.get("expected_sha"):
                errors.append("P1 checkpoint source SHA does not match record source")
        if manifest.get("solution_only") is not True or manifest.get("vector_roles") != ["solution"]:
            errors.append("P1 checkpoint is not solution-only")
        if manifest.get("numeric_allgather") is not False:
            errors.append("P1 checkpoint numeric allgather contract failed")
        if set(manifest.get("forbidden_vector_roles", [])) != {"action", "residual", "krylov_basis"}:
            errors.append("P1 checkpoint forbidden vector roles changed")
        expected_files = {"manifest.json"}
        for rank in range(int(record["mpi_size"])):
            expected_files.add(f"solution_rank{rank}.npy")
        if {item.name for item in path.parent.iterdir()} != expected_files:
            errors.append("P1 checkpoint contains undeclared or missing numeric files")


def _check_identity(record: dict[str, Any], errors: list[str], gates: list[str]) -> None:
    if record.get("schema") != SCHEMA or record.get("stage") != "p1":
        errors.append("P1 schema/stage mismatch")
    case = record.get("case")
    source = record.get("source_name")
    if case not in CASES or source not in SOURCES:
        errors.append("P1 case/source is not frozen")
        return
    degree, mpi_size = CASES[case]
    if record.get("degree") != degree or record.get("mpi_size") != mpi_size:
        errors.append("P1 case degree/MPI identity mismatch")
    if record.get("variant") != "sequential-v1":
        errors.append("P1 production variant is not the frozen multiplicative sequential-v1")
    command = record.get("command")
    raw_dir = record.get("raw_dir")
    record_path = record.get("record_path")
    expected_sha = record.get("source", {}).get("expected_sha") if isinstance(record.get("source"), dict) else None
    expected_command = [
        "benchmarks.run_task038_full3d_lor_hx_memory_first",
        "--stage",
        "p1",
        "--case",
        case,
        "--source",
        source,
        "--raw-dir",
        raw_dir,
        "--record",
        record_path,
        "--expected-source-sha",
        expected_sha,
        "--expected-mpi-size",
        str(mpi_size),
    ]
    if (
        not isinstance(command, list)
        or len(command) != 2 + len(expected_command)
        or command[1:3] != ["-m", expected_command[0]]
        or command[3:] != expected_command[1:]
        or not isinstance(command[0], str)
        or not Path(command[0]).is_absolute()
    ):
        errors.append("P1 command provenance is missing or does not bind the record")
    identity = record.get("source")
    if not isinstance(identity, dict):
        errors.append("P1 source identity is missing")
    else:
        expected = identity.get("expected_sha")
        values = [identity.get(key) for key in ("expected_sha", "commit_sha_start", "commit_sha_end")]
        if not all(
            isinstance(value, str)
            and len(value) == 40
            and value == value.lower()
            and all(character in "0123456789abcdef" for character in value)
            for value in values
        ):
            errors.append("P1 source SHA fields are invalid")
        elif not (values[0] == values[1] == values[2]):
            errors.append("P1 source SHA fields do not close")
        if identity.get("branch") != BRANCH or identity.get("clean_start") is not True or identity.get("clean_end") is not True:
            errors.append("P1 source branch/clean identity does not close")
        if not isinstance(expected, str):
            errors.append("P1 expected source SHA is missing")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("P1 runtime identity is missing")
    else:
        for key, expected in (("qualified_activation", "1"), ("mpi_size", mpi_size), ("petsc_scalar_type", "complex128"), ("petsc_int_type", "int32")):
            if runtime.get(key) != expected:
                errors.append(f"P1 runtime.{key} is not qualified")
    settings = record.get("settings")
    exact = {
        "ksp_type": "gmres", "pc_side": "right", "norm_type": "unpreconditioned",
        "restart": 20, "max_it": 2000, "residual_limit": RESIDUAL_LIMIT,
        "residual_replacement": True, "checkpoint_interval": 200,
        "first_checkpoint_iteration": None, "additive_v2": False,
    }
    if not isinstance(settings, dict) or any(settings.get(key) != value for key, value in exact.items()):
        errors.append("P1 GMRES/checkpoint settings are not exact")
    old = record.get("old_authorities")
    if not isinstance(old, dict) or old.get("old_l2_record_sha256") != OLD_L2_RECORD_SHA or old.get("old_l2_one_apply_rho") != OLD_L2_RHO or old.get("old_l2_classification") != OLD_L2_CLASSIFICATION or old.get("old_k1_80_step") != "FAIL" or old.get("additive_v2") != "CLOSED":
        errors.append("old L2/K1/additive authority is not preserved")
    source_facts = record.get("source_facts")
    if not isinstance(source_facts, dict) or source_facts.get("name") != source or source_facts.get("formula") != SOURCE_FORMULAS[source]:
        errors.append("P1 source formula is not the frozen formula")
    provenance = record.get("provenance")
    for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
        value = provenance.get(key) if isinstance(provenance, dict) else None
        if not isinstance(value, str) or len(value) != 64 or value != value.lower() or any(character not in "0123456789abcdef" for character in value):
            errors.append(f"P1 provenance {key} is invalid")
    basis = record.get("provenance_basis")
    if not isinstance(basis, dict) or basis.get("partition_invariant") is not True:
        errors.append("P1 provenance is not explicitly partition-invariant")
    elif set(basis.get("excludes", [])) != {"case_mpi_label", "mpi_size", "owner_local_counts", "rank_local_audit"}:
        errors.append("P1 provenance exclusion basis is not exact")
    production = record.get("production")
    forbidden = record.get("forbidden")
    for section in (production, forbidden):
        if not isinstance(section, dict):
            errors.append("P1 forbidden/production audit is missing")
            continue
        for key in ("high_order_global_aij", "global_direct_coarse", "global_numeric_allgather", "global_dense_transfer"):
            if section.get(key) is not False:
                errors.append(f"P1 {key} must be false")
    fixture_audit = record.get("fixture_audit")
    hx_audit = record.get("hx_audit")
    if not isinstance(fixture_audit, dict) or not isinstance(hx_audit, dict):
        errors.append("P1 fixture/hx audit snapshot is missing")
    else:
        if fixture_audit.get("variant") != "sequential-v1" or hx_audit.get("variant") != "sequential-v1":
            errors.append("P1 fixture/hx audit variant is not sequential-v1")
        fixture_flags = {
            "high_order_global_aij": fixture_audit.get("high_order_global_aij"),
            "global_numeric_allgather": fixture_audit.get("global_numeric_allgather"),
            "global_dense_transfer": fixture_audit.get("global_transfer_matrix"),
        }
        hx_flags = {
            "high_order_global_aij": hx_audit.get("high_order_aij"),
            "global_numeric_allgather": hx_audit.get("global_numeric_allgather"),
            "global_dense_transfer": hx_audit.get("global_transfer_matrix"),
        }
        actual = {
            "high_order_global_aij": (
                fixture_flags["high_order_global_aij"]
                or hx_flags["high_order_global_aij"]
                if all(
                    isinstance(value, bool)
                    for value in (
                        fixture_flags["high_order_global_aij"],
                        hx_flags["high_order_global_aij"],
                    )
                )
                else None
            ),
            "global_direct_coarse": hx_audit.get("global_direct_coarse"),
            "global_numeric_allgather": (
                fixture_flags["global_numeric_allgather"]
                or hx_flags["global_numeric_allgather"]
                if all(
                    isinstance(value, bool)
                    for value in (
                        fixture_flags["global_numeric_allgather"],
                        hx_flags["global_numeric_allgather"],
                    )
                )
                else None
            ),
            "global_dense_transfer": (
                fixture_flags["global_dense_transfer"]
                or hx_flags["global_dense_transfer"]
                if all(
                    isinstance(value, bool)
                    for value in (
                        fixture_flags["global_dense_transfer"],
                        hx_flags["global_dense_transfer"],
                    )
                )
                else None
            ),
        }
        for key, value in actual.items():
            if not isinstance(value, bool):
                errors.append(f"P1 fixture/hx audit {key} is missing")
            if isinstance(production, dict) and production.get(key) != value:
                errors.append(f"P1 production {key} does not bind fixture/hx audit")
            if isinstance(forbidden, dict) and forbidden.get(key) != value:
                errors.append(f"P1 forbidden {key} does not bind fixture/hx audit")
        if actual["high_order_global_aij"] is not False or actual["global_direct_coarse"] is not False or actual["global_numeric_allgather"] is not False or actual["global_dense_transfer"] is not False:
            errors.append("P1 fixture/hx audit contains a forbidden production path")
        if fixture_audit.get("slave_master_complete") is not True or fixture_audit.get("phase_application") != "finalized_floquet_mpc_once":
            errors.append("P1 fixture MPC audit is incomplete")
    if not isinstance(production, dict) or production.get("metadata_allgather") is not True:
        errors.append("P1 metadata-only allgather scope is missing")
    _check_checkpoint(record, errors)


def _check_cycle_ledger(record: dict[str, Any], errors: list[str], gates: list[str]) -> None:
    cycles = record.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        errors.append("P1 cycle ledger is missing")
        return
    expected_start = 0
    for cycle in cycles:
        if not isinstance(cycle, dict):
            errors.append("malformed P1 cycle ledger row")
            continue
        for key in ("start_iteration", "end_iteration", "iterations", "matvec_count", "pc_apply_count"):
            if not isinstance(cycle.get(key), int) or cycle[key] < 0:
                errors.append(f"P1 cycle {key} is invalid")
        start = cycle.get("start_iteration")
        end = cycle.get("end_iteration")
        iterations = cycle.get("iterations")
        if isinstance(start, int) and isinstance(end, int) and isinstance(iterations, int):
            if start != expected_start:
                errors.append("P1 cycle ledger has a gap or overlap")
            if end < start or end - start != iterations or iterations > 20:
                errors.append("P1 cycle ledger segment is not a closed <=20-step interval")
            expected_start = end
        explicit = cycle.get("explicit_true_residual")
        if not isinstance(explicit, (int, float)) or not np.isfinite(float(explicit)) or float(explicit) < 0.0:
            errors.append("P1 cycle explicit residual is not finite and non-negative")
        if cycle.get("ksp_destroyed") is not True:
            errors.append("P1 cycle KSP was not destroyed")
        resource = cycle.get("resource")
        if not isinstance(resource, dict):
            errors.append("P1 cycle resource sample is missing")
            continue
        rss, swap, readable = _process_tree_facts(resource)
        if not isinstance(rss, int) or rss < 0 or readable is not True:
            errors.append("P1 cycle process-tree resource sample is not readable")
        if swap != 0:
            gates.append("P1 cycle process-tree/rank swap is non-zero")
        if resource.get("scope") != "rank_process_tree_diagnostic_excludes_launcher":
            errors.append("P1 cycle resource scope is not explicitly diagnostic")
    final = record.get("final")
    if not isinstance(final, dict):
        errors.append("P1 final residual fact is missing")
    elif cycles and isinstance(cycles[-1], dict):
        last = cycles[-1]
        if last.get("end_iteration") != final.get("iterations"):
            errors.append("P1 final iteration does not close the cycle ledger")
        try:
            if not np.isclose(
                float(last.get("explicit_true_residual")),
                float(final.get("explicit_true_residual")),
                rtol=1.0e-14,
                atol=1.0e-15,
            ):
                errors.append("P1 final explicit residual does not close the cycle ledger")
        except (TypeError, ValueError):
            errors.append("P1 final explicit residual is invalid")
    checkpoint_facts = record.get("checkpoint_facts")
    measured = {
        fact.get("iteration")
        for fact in checkpoint_facts
        if isinstance(fact, dict)
    } if isinstance(checkpoint_facts, list) else set()
    statuses = record.get("checkpoint_status")
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        end = cycle.get("end_iteration")
        if isinstance(end, int) and end > 0 and end % CHECKPOINT_INTERVAL == 0:
            if end not in measured:
                errors.append(f"P1 reached checkpoint boundary {end} has no measured raw checkpoint")
            elif str(end) in {str(point) for point in CHECKPOINT_POINTS}:
                status = statuses.get(str(end), {}).get("status") if isinstance(statuses, dict) else None
                if status != "measured":
                    errors.append(f"P1 reached checkpoint boundary {end} status is not measured")
    rank_facts = record.get("rank_facts")
    if isinstance(rank_facts, list):
        for fact in rank_facts:
            ledger = fact.get("cycle_ledger") if isinstance(fact, dict) else None
            if not isinstance(ledger, list) or len(ledger) != len(cycles):
                errors.append("P1 per-rank cycle ledger is incomplete")
                continue
            for cycle in ledger:
                resource = cycle.get("resource") if isinstance(cycle, dict) else None
                _rss, swap, _readable = _process_tree_facts(resource) if isinstance(resource, dict) else (None, None, None)
                if swap != 0:
                    gates.append("P1 per-rank process-tree/rank swap is non-zero")
                if not isinstance(cycle, dict) or cycle.get("ksp_destroyed") is not True:
                    errors.append("P1 per-rank cycle KSP was not destroyed")


def _check_record_arrays(record: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    loaded: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for role in ("source", "rhs", "final_solution", "final_action", "final_true_residual"):
        keys, values = _load_role(record, role, errors)
        if keys is not None and values is not None:
            loaded[role] = (keys, values)
    if set(loaded) != {"source", "rhs", "final_solution", "final_action", "final_true_residual"}:
        return loaded
    rhs_keys, rhs_values = loaded["rhs"]
    action_keys, action_values = loaded["final_action"]
    residual_keys, residual_values = loaded["final_true_residual"]
    action_aligned = _align_to(rhs_keys, action_keys, action_values, "rhs/final_action", errors)
    residual_aligned = _align_to(
        rhs_keys, residual_keys, residual_values, "rhs/final_true_residual", errors
    )
    if action_aligned is None or residual_aligned is None:
        return loaded
    expected_residual = rhs_values - action_aligned
    if not np.allclose(
        residual_aligned,
        expected_residual,
        rtol=1.0e-12,
        atol=1.0e-14,
    ):
        errors.append("final true residual raw values do not equal RHS minus final action")
    rho = float(np.linalg.norm(expected_residual) / max(np.linalg.norm(rhs_values), np.finfo(float).tiny))
    if rho > RESIDUAL_LIMIT:
        gates.append(f"final true residual rho {rho} > {RESIDUAL_LIMIT}")
    final = record.get("final")
    if not isinstance(final, dict) or not np.isfinite(float(final.get("explicit_true_residual", float("nan")))):
        errors.append("final explicit residual fact is missing")
    elif not np.isclose(float(final["explicit_true_residual"]), rho, rtol=1.0e-12, atol=1.0e-14):
        errors.append("final explicit residual does not match canonical raw values")
    return loaded


def _check_pc_legality(record: dict[str, Any], errors: list[str], gates: list[str]) -> None:
    pc = record.get("pc_legality")
    if not isinstance(pc, dict):
        errors.append("P1 PC legality facts are missing")
        return
    fixture_audit = record.get("fixture_audit")
    hx_audit = record.get("hx_audit")
    if isinstance(fixture_audit, dict) and isinstance(hx_audit, dict):
        fixture_high = fixture_audit.get("high_order_global_aij")
        hx_high = hx_audit.get("high_order_aij")
        fixture_numeric = fixture_audit.get("global_numeric_allgather")
        hx_numeric = hx_audit.get("global_numeric_allgather")
        fixture_transfer = fixture_audit.get("global_transfer_matrix")
        hx_transfer = hx_audit.get("global_transfer_matrix")
        expected_flags = {
            "high_order_global_aij": (
                fixture_high or hx_high
                if isinstance(fixture_high, bool) and isinstance(hx_high, bool)
                else None
            ),
            "global_direct_coarse": hx_audit.get("global_direct_coarse"),
            "global_numeric_allgather": (
                fixture_numeric or hx_numeric
                if isinstance(fixture_numeric, bool) and isinstance(hx_numeric, bool)
                else None
            ),
            "global_dense_transfer": (
                fixture_transfer or hx_transfer
                if isinstance(fixture_transfer, bool) and isinstance(hx_transfer, bool)
                else None
            ),
        }
        for key, expected in expected_flags.items():
            if not isinstance(expected, bool) or pc.get(key) is not expected:
                errors.append(f"P1 PC {key} does not bind fixture/hx audit")
    names = (
        "pc_input_residual_before",
        "pc_input_residual_after",
        "pc_input_first_before",
        "pc_input_first_after",
        "pc_input_second_before",
        "pc_input_second_after",
        "pc_input_combined_before",
        "pc_input_combined_after",
        "pc_output_first",
        "pc_output_second",
        "pc_output_combined",
        "pc_output_repeat",
    )
    artifacts = pc.get("pc_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(names):
        errors.append("P1 PC raw artifact role set is not exact")
    arrays: dict[str, np.ndarray] = {}
    shards: dict[str, list[dict[str, Any]]] = {}
    for name in names:
        values, layout = _load_pc_layout(record, name, errors)
        if values is not None:
            arrays[name] = values
            shards[name] = layout
    if set(arrays) != set(names):
        return
    alpha = pc.get("alpha")
    beta = pc.get("beta")
    try:
        alpha_value = complex(float(alpha[0]), float(alpha[1]))
        beta_value = complex(float(beta[0]), float(beta[1]))
    except (TypeError, ValueError, IndexError):
        errors.append("P1 PC alpha/beta binding is missing")
        return
    if alpha_value != complex(0.375, 0.25) or beta_value != complex(-0.625, 0.5):
        errors.append("P1 PC alpha/beta are not the frozen coefficients")
        return
    input_pairs = (
        ("pc_input_residual_before", "pc_input_residual_after"),
        ("pc_input_first_before", "pc_input_first_after"),
        ("pc_input_second_before", "pc_input_second_after"),
        ("pc_input_combined_before", "pc_input_combined_after"),
    )
    input_unchanged = all(np.array_equal(arrays[before], arrays[after]) for before, after in input_pairs)
    finite = all(np.all(np.isfinite(values)) for values in arrays.values())
    expected_combined = (
        alpha_value * arrays["pc_output_first"]
        + beta_value * arrays["pc_output_second"]
    )
    output_combined = arrays["pc_output_combined"]
    output_repeat = arrays["pc_output_repeat"]
    linearity = _relative(output_combined, expected_combined)
    repeat = _relative(output_repeat, output_combined)
    first_norm = float(np.linalg.norm(arrays["pc_input_first_before"]))
    second_norm = float(np.linalg.norm(arrays["pc_input_second_before"]))
    combined_norm = float(np.linalg.norm(arrays["pc_input_combined_before"]))
    stored = {
        "first_global_norm": pc.get("first_global_norm"),
        "second_global_norm": pc.get("second_global_norm"),
        "combined_global_norm": pc.get("combined_global_norm"),
        "linearity_relative": pc.get("linearity_relative"),
        "repeat_relative": pc.get("repeat_relative"),
        "slave_constraint_absolute": pc.get("slave_constraint_absolute"),
    }
    computed = {
        "first_global_norm": first_norm,
        "second_global_norm": second_norm,
        "combined_global_norm": combined_norm,
        "linearity_relative": linearity,
        "repeat_relative": repeat,
    }
    for key, value in computed.items():
        try:
            if not np.isclose(float(stored[key]), value, rtol=1.0e-12, atol=1.0e-14):
                errors.append(f"P1 stored PC fact {key} does not match raw shards")
        except (TypeError, ValueError):
            errors.append(f"P1 stored PC fact {key} is missing")
    if pc.get("finite") is not finite:
        errors.append("P1 stored PC finite fact does not match raw shards")
    if pc.get("input_unchanged") is not input_unchanged:
        errors.append("P1 stored PC input_unchanged fact does not match raw shards")
    if pc.get("direction_construction") != "PETSc_global_row_parity":
        errors.append("P1 PC direction construction is not frozen")
    if pc.get("slave_master_complete") is not True or pc.get("phase_application") != "finalized_floquet_mpc_once":
        errors.append("P1 PC MPC audit facts are incomplete")
    if linearity > 1.0e-12:
        gates.append("P1 raw PC linearity exceeded 1e-12")
    if repeat > 1.0e-13:
        gates.append("P1 raw PC repeat exceeded 1e-13")
    if not finite:
        gates.append("P1 raw PC produced a non-finite value")
    if not input_unchanged:
        gates.append("P1 raw PC modified an input")

    slave_by_rank = pc.get("slave_local_indices_by_rank")
    mpi_size = int(record.get("mpi_size", -1))
    if not isinstance(slave_by_rank, dict) or set(slave_by_rank) != {str(rank) for rank in range(mpi_size)}:
        errors.append("P1 PC slave local-index facts do not cover all ranks")
        return
    slave_max = 0.0
    for output_name in ("pc_output_first", "pc_output_second", "pc_output_combined", "pc_output_repeat"):
        output_shards = {int(item["rank"]): item for item in shards[output_name]}
        for rank in range(mpi_size):
            indices = slave_by_rank[str(rank)]
            shard = output_shards.get(rank)
            if not isinstance(indices, list) or shard is None:
                errors.append(f"P1 PC slave layout is missing rank {rank}")
                continue
            values = shard["values"]
            for index in indices:
                if not isinstance(index, int) or index < 0 or index >= values.size:
                    errors.append(f"P1 PC slave local index is invalid on rank {rank}")
                    continue
                slave_max = max(slave_max, float(abs(values[index])))
    try:
        stored_slave = float(stored["slave_constraint_absolute"])
        if not np.isclose(stored_slave, slave_max, rtol=1.0e-12, atol=1.0e-14):
            errors.append("P1 stored slave constraint does not match raw output shards")
    except (TypeError, ValueError):
        errors.append("P1 stored slave constraint is missing")
    if slave_max > 1.0e-12:
        gates.append("P1 raw PC slave/primal constraint exceeded 1e-12")


def check_record(record_path: str | Path) -> dict[str, Any]:
    path = Path(record_path).resolve()
    errors: list[str] = []
    gates: list[str] = []
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "contract_errors": [str(exc)], "gate_failures": []}
    if not isinstance(record, dict):
        return {"passed": False, "contract_errors": ["record root is not an object"], "gate_failures": []}
    _check_identity(record, errors, gates)
    _check_cycle_ledger(record, errors, gates)
    loaded = _check_record_arrays(record, errors, gates)
    _check_pc_legality(record, errors, gates)
    rank_facts = record.get("rank_facts")
    mpi_size = int(record.get("mpi_size", -1))
    if not isinstance(rank_facts, list) or len(rank_facts) != mpi_size:
        errors.append("P1 rank facts do not cover all ranks")
    else:
        ranks = [fact.get("rank") for fact in rank_facts if isinstance(fact, dict)]
        if sorted(ranks) != list(range(mpi_size)):
            errors.append("P1 rank IDs are incomplete")
        for fact in rank_facts:
            constraint = fact.get("constraint") if isinstance(fact, dict) else None
            if not isinstance(constraint, dict) or constraint.get("slave_master_complete") is not True:
                errors.append("P1 all-rank slave/master constraint fact is missing")
            elif not np.isfinite(float(constraint.get("slave_constraint_absolute", float("nan")))) or float(constraint["slave_constraint_absolute"]) > 1.0e-12:
                gates.append("P1 all-rank slave/primal constraint exceeded 1e-12")
        ranges = record.get("count_ranges")
        if not isinstance(ranges, dict):
            errors.append("P1 count ranges are missing")
        else:
            for key in ("matvec_count", "pc_apply_count", "explicit_action_count", "iterations"):
                values = [fact.get(key) for fact in rank_facts]
                if not all(isinstance(value, int) and value >= 0 for value in values):
                    errors.append(f"P1 rank count {key} is invalid")
                elif ranges.get(key) != {"min": min(values), "max": max(values)} or min(values) != max(values):
                    errors.append(f"P1 collective count {key} is not rank-closed")
    one_apply = record.get("one_apply")
    if not isinstance(one_apply, dict):
        errors.append("P1 one-apply facts are missing")
    else:
        if one_apply.get("rho_status") != "diagnostic_only_not_a_gate":
            errors.append("P1 one-apply status is not diagnostic-only")
        try:
            one_apply_rho = float(one_apply["rho"])
        except (KeyError, TypeError, ValueError):
            errors.append("P1 one-apply rho is missing")
        else:
            if not np.isfinite(one_apply_rho) or one_apply_rho < 0.0:
                errors.append("P1 one-apply rho is not finite and non-negative")
            if one_apply.get("finite") is not bool(np.isfinite(one_apply_rho)):
                errors.append("P1 one-apply finite fact does not match rho")
    rho = None
    if "rhs" in loaded and "final_action" in loaded:
        rhs_keys, rhs_values = loaded["rhs"]
        action_keys, action_values = loaded["final_action"]
        action_aligned = _align_to(rhs_keys, action_keys, action_values, "pair rho rhs/final_action", [])
        if action_aligned is not None:
            rho = float(
                np.linalg.norm(rhs_values - action_aligned)
                / max(np.linalg.norm(rhs_values), np.finfo(float).tiny)
            )
    result = {
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "case": record.get("case"),
        "source": record.get("source_name"),
        "degree": record.get("degree"),
        "mpi_size": record.get("mpi_size"),
        "rho": rho,
    }
    return result


def _pair_arrays(
    left: dict[str, tuple[np.ndarray, np.ndarray]],
    right: dict[str, tuple[np.ndarray, np.ndarray]],
    role: str,
    errors: list[str],
    denominator: np.ndarray | None = None,
) -> float | None:
    if role not in left or role not in right or left[role][0] is None or right[role][0] is None:
        errors.append(f"pair role {role} is missing")
        return None
    left_keys, left_values = left[role]
    right_keys, right_values = right[role]
    if set(left_keys.tolist()) != set(right_keys.tolist()) or len(set(left_keys.tolist())) != len(left_keys) or len(set(right_keys.tolist())) != len(right_keys):
        errors.append(f"pair role {role} key set mismatch")
        return None
    right_index = {key: index for index, key in enumerate(right_keys.tolist())}
    aligned = np.asarray([right_values[right_index[key]] for key in left_keys.tolist()], dtype=np.complex128)
    scale = aligned if denominator is None else denominator
    return float(np.linalg.norm(left_values - aligned) / max(np.linalg.norm(scale), np.finfo(float).tiny))


def check_pair(left_path: str | Path, right_path: str | Path) -> dict[str, Any]:
    left_result = check_record(left_path)
    right_result = check_record(right_path)
    errors = list(left_result["contract_errors"]) + list(right_result["contract_errors"])
    gates = list(left_result["gate_failures"]) + list(right_result["gate_failures"])
    left = json.loads(Path(left_path).read_text(encoding="utf-8"))
    right = json.loads(Path(right_path).read_text(encoding="utf-8"))
    if left.get("degree") != right.get("degree") or left.get("source_name") != right.get("source_name"):
        errors.append("pair degree/source identity mismatch")
    left_sha = left.get("source", {}).get("expected_sha") if isinstance(left.get("source"), dict) else None
    right_sha = right.get("source", {}).get("expected_sha") if isinstance(right.get("source"), dict) else None
    if left_sha != right_sha:
        errors.append("pair source SHA mismatch")
    left_provenance = left.get("provenance")
    right_provenance = right.get("provenance")
    for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
        if not isinstance(left_provenance, dict) or not isinstance(right_provenance, dict):
            errors.append(f"pair {key} provenance is missing")
        elif left_provenance.get(key) != right_provenance.get(key):
            errors.append(f"pair {key} identity mismatch")
    left_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    right_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for role in ("source", "rhs", "final_solution", "final_action", "final_true_residual"):
        left_arrays[role] = _load_role(left, role, errors)
        right_arrays[role] = _load_role(right, role, errors)
    metrics: dict[str, float | None] = {}
    for role in ("source", "rhs"):
        metrics[role] = _pair_arrays(left_arrays, right_arrays, role, errors)
    metrics["final_action"] = _pair_arrays(
        left_arrays,
        right_arrays,
        "final_action",
        errors,
        denominator=(
            _align_to(
                left_arrays["final_action"][0],
                left_arrays["rhs"][0],
                left_arrays["rhs"][1],
                "pair final_action/RHS",
                errors,
            )
            if left_arrays.get("final_action") and left_arrays.get("rhs")
            else None
        ),
    )
    rhs_identity = metrics.get("rhs")
    source_identity = metrics.get("source")
    action_identity = metrics.get("final_action")
    rho_one = left_result.get("rho")
    rho_two = right_result.get("rho")
    if source_identity is None:
        errors.append("pair source measurement is missing")
    elif source_identity > 1.0e-12:
        gates.append(f"pair source identity {source_identity} exceeds 1e-12")
    if rhs_identity is None:
        errors.append("pair RHS measurement is missing")
    elif rhs_identity > 1.0e-12:
        gates.append(f"pair RHS identity {rhs_identity} exceeds 1e-12")
    for label, rho in (("left", rho_one), ("right", rho_two)):
        if rho is None:
            errors.append(f"pair {label} rho measurement is missing")
        elif rho > RESIDUAL_LIMIT:
            gates.append(f"pair {label} rho {rho} exceeds {RESIDUAL_LIMIT}")
    if any(value is None for value in (rhs_identity, action_identity, rho_one, rho_two)):
        errors.append("pair measured facts are incomplete")
        bound = None
    else:
        bound = float(rho_one + rho_two + rhs_identity + SMALL_PAIR_MARGIN)
        if action_identity > bound:
            gates.append(f"pair final action {action_identity} exceeds dynamic bound {bound}")
    metrics["final_solution_diagnostic"] = _pair_arrays(left_arrays, right_arrays, "final_solution", errors)
    metrics["final_true_residual_diagnostic"] = _pair_arrays(left_arrays, right_arrays, "final_true_residual", errors)
    return {
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "metrics": metrics,
        "dynamic_action_bound": bound,
        "left": left_result,
        "right": right_result,
        "left_identity": left.get("provenance"),
        "right_identity": right.get("provenance"),
    }


def check_records(record_paths: list[str | Path]) -> dict[str, Any]:
    expected = list(SUITE_ORDER)
    observed: list[str] = []
    individual: dict[str, Any] = {}
    records: dict[str, Path] = {}
    errors: list[str] = []
    gates: list[str] = []
    pairs: dict[str, Any] = {}
    for record_path in record_paths:
        result = check_record(record_path)
        record = json.loads(Path(record_path).read_text(encoding="utf-8"))
        key = f"{record.get('case')}/{record.get('source_name')}"
        observed.append(key)
        if key in records:
            errors.append(f"duplicate P1 suite member {key}")
        records[key] = Path(record_path)
        individual[key] = result
        errors.extend(result["contract_errors"])
        gates.extend(result["gate_failures"])
    if observed != expected or set(observed) != set(expected):
        errors.append("P1 aggregate requires exactly the frozen 16-case order")
    if errors:
        return {
            "passed": False,
            "contract_errors": errors,
            "gate_failures": gates,
            "individual": individual,
            "pairs": pairs,
        }
    for degree in (2, 3):
        for source in SOURCES:
            left = records[f"p{degree}-mpi1/{source}"]
            right = records[f"p{degree}-mpi2/{source}"]
            pair = check_pair(left, right)
            pair_key = f"p{degree}-mpi1/{source}::p{degree}-mpi2/{source}"
            pairs[pair_key] = pair
            if pair["contract_errors"]:
                errors.extend(pair["contract_errors"])
            gates.extend(pair["gate_failures"])
    return {
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "individual": individual,
        "pairs": pairs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("p1",), required=True)
    parser.add_argument("--record", action="append")
    parser.add_argument("--records", nargs="*")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    paths = args.records or args.record or []
    result = check_records(paths) if len(paths) != 1 else check_record(paths[0])
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
