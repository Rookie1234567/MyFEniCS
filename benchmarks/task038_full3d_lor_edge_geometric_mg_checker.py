"""Independent NumPy checker for the S4-A3 LOR-edge worker evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-edge-geometric-mg.s4-a3-record.v1"
CASES = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
}
SOURCES = ("random", "gradient", "curl", "checkerboard")
MAX_IT = 10000
RESTART = 20
RESIDUAL_LIMIT = 1.0e-8
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
SLAVE_LIMIT = 1.0e-12
ACTION_MARGIN = 1.0e-11
RSS_LIMIT = 500_000_000
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
WATCHDOG_POLL_SECONDS = 0.25
PC_ALPHA = 0.375 + 0.25j
PC_BETA = -0.625 + 0.5j
CANONICAL_ROLES = {
    "source": "primal",
    "rhs": "dual",
    "rhs_repeat": "dual",
    "final_solution": "primal",
    "final_action": "dual",
    "final_true_residual": "dual",
}
PC_ROLES = {
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
}


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value}")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, parse_constant=_reject_constant)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _provenance_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_ids = left.get("provenance", {})
    right_ids = right.get("provenance", {})
    names = (
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
    )
    return all(left_ids.get(name) == right_ids.get(name) for name in names)


def _load_array(
    raw_dir: Path, descriptor: dict[str, Any], errors: list[str], label: str
) -> np.ndarray | None:
    if not isinstance(descriptor, dict):
        errors.append(f"{label}: descriptor is not an object")
        return None
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str):
        errors.append(f"{label}: missing relative_path")
        return None
    path = (raw_dir / relative).resolve()
    if not _within(path, raw_dir) or not path.is_file():
        errors.append(f"{label}: shard path is missing or escapes raw_dir")
        return None
    try:
        if descriptor.get("sha256") != _sha256(path):
            errors.append(f"{label}: sha256 mismatch")
        values = np.load(path, allow_pickle=False)
    except Exception as exc:
        errors.append(f"{label}: cannot load array: {type(exc).__name__}: {exc}")
        return None
    if str(values.dtype) != descriptor.get("dtype"):
        errors.append(f"{label}: dtype mismatch")
    if list(values.shape) != descriptor.get("shape"):
        errors.append(f"{label}: shape mismatch")
    if int(path.stat().st_size) != int(descriptor.get("bytes", -1)):
        errors.append(f"{label}: byte count mismatch")
    return values


def _merge_canonical(
    record: dict[str, Any], raw_dir: Path, role: str, errors: list[str]
) -> dict[str, complex]:
    result: dict[str, complex] = {}
    entry = record.get("canonical_artifacts", {}).get(role)
    if not isinstance(entry, dict):
        errors.append(f"canonical {role}: missing role descriptor")
        return result
    if entry.get("role") != CANONICAL_ROLES[role]:
        errors.append(f"canonical {role}: role mismatch")
    shards = entry.get("shards")
    if not isinstance(shards, list) or len(shards) != int(record.get("mpi_size", -1)):
        errors.append(f"canonical {role}: shard count mismatch")
        return result
    seen_ranks: set[int] = set()
    for shard in shards:
        rank = int(shard.get("rank", -1)) if isinstance(shard, dict) else -1
        if rank in seen_ranks or rank < 0:
            errors.append(f"canonical {role}: duplicate/invalid rank")
            continue
        seen_ranks.add(rank)
        keys = _load_array(raw_dir, shard.get("keys"), errors, f"{role}.rank{rank}.keys")
        values = _load_array(raw_dir, shard.get("values"), errors, f"{role}.rank{rank}.values")
        if keys is None or values is None:
            continue
        if keys.ndim != 1 or values.ndim != 1 or keys.size != values.size:
            errors.append(f"canonical {role}.rank{rank}: invalid one-dimensional pair")
            continue
        if keys.dtype.kind != "U" or values.dtype != np.dtype(np.complex128):
            errors.append(f"canonical {role}.rank{rank}: role dtype is invalid")
        if not np.all(np.isfinite(values)):
            errors.append(f"canonical {role}.rank{rank}: non-finite values")
        for key, value in zip(keys.tolist(), values.tolist(), strict=True):
            if key in result:
                errors.append(f"canonical {role}: duplicate key {key}")
            result[str(key)] = complex(value)
    if seen_ranks != set(range(int(record.get("mpi_size", -1)))):
        errors.append(f"canonical {role}: rank inventory is incomplete")
    return result


def _relative_maps(left: dict[str, complex], right: dict[str, complex], errors: list[str], label: str) -> float:
    if set(left) != set(right):
        errors.append(f"{label}: canonical key sets differ")
        return float("inf")
    left_values = np.asarray([left[key] for key in sorted(left)], dtype=np.complex128)
    right_values = np.asarray([right[key] for key in sorted(left)], dtype=np.complex128)
    if not np.all(np.isfinite(left_values)) or not np.all(np.isfinite(right_values)):
        errors.append(f"{label}: non-finite canonical values")
        return float("inf")
    return float(np.linalg.norm(left_values - right_values) / max(np.linalg.norm(right_values), np.finfo(float).tiny))


def _dynamic_action_bound(rho_left: float, rho_right: float, rhs_identity: float) -> float:
    return float(rho_left + rho_right + rhs_identity + ACTION_MARGIN)


def _within_dynamic_action_bound(
    action_relative: float, rho_left: float, rho_right: float, rhs_identity: float
) -> bool:
    bound = _dynamic_action_bound(rho_left, rho_right, rhs_identity)
    return bool(np.isfinite(bound) and np.isfinite(action_relative) and action_relative <= bound)


def _check_watchdog(record: dict[str, Any], record_path: Path, compact_path: Path, errors: list[str], gates: list[str]) -> dict[str, Any]:
    resource: dict[str, Any] = {}
    if not compact_path.is_file():
        errors.append("watchdog compact is missing")
        return resource
    try:
        compact = _read_json(compact_path)
    except Exception as exc:
        errors.append(f"watchdog compact cannot be read: {type(exc).__name__}: {exc}")
        return resource
    if compact.get("schema") != WATCHDOG_SCHEMA:
        errors.append("watchdog schema mismatch")
    if compact.get("watchdog_poll_seconds") != WATCHDOG_POLL_SECONDS:
        errors.append("watchdog poll interval mismatch")
    if compact.get("watchdog_rss_limit_bytes") != RSS_LIMIT:
        errors.append("watchdog RSS limit mismatch")
    raw_path = Path(str(compact.get("watchdog_raw", ""))).resolve()
    if not raw_path.is_file():
        errors.append("watchdog raw is missing")
        return resource
    try:
        raw_lines = [
            json.loads(line, parse_constant=_reject_constant)
            for line in raw_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception as exc:
        errors.append(f"watchdog raw cannot be read: {type(exc).__name__}: {exc}")
        return resource
    if len(raw_lines) != int(compact.get("sample_count", -1)):
        errors.append("watchdog sample_count does not match raw ledger")
    derived_readable = True
    rss_values: list[int] = []
    swap_values: list[int] = []
    for index, sample in enumerate(raw_lines):
        tree = sample.get("authority", {}).get("process_tree", {})
        readable = bool(tree.get("all_status_readable", False))
        derived_readable = derived_readable and readable
        if not readable:
            errors.append(f"watchdog sample {index}: process tree unreadable")
        try:
            rss_values.append(int(tree["rss_bytes"]))
            swap_values.append(int(tree["swap_bytes"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"watchdog sample {index}: rss/swap missing")
    peak = max(rss_values, default=-1)
    swap = max(swap_values, default=-1)
    if compact.get("raw_sha256") != _sha256(raw_path):
        errors.append("watchdog raw_sha256 mismatch")
    if int(compact.get("sample_count", -1)) != len(raw_lines):
        errors.append("watchdog compact sample count mismatch")
    if bool(compact.get("all_status_readable", False)) != derived_readable:
        errors.append("watchdog all_status_readable is not independently derived")
    if int(compact.get("peak_process_tree_rss_bytes", -1)) != peak:
        errors.append("watchdog compact peak RSS disagrees with raw ledger")
    if int(compact.get("max_process_tree_swap_bytes", -1)) != swap:
        errors.append("watchdog compact swap disagrees with raw ledger")
    if compact.get("source_sha") != record.get("source", {}).get("expected_sha"):
        errors.append("watchdog source SHA mismatch")
    if Path(str(compact.get("worker_record", ""))).resolve() != record_path.resolve():
        errors.append("watchdog worker_record does not match record")
    if Path(str(compact.get("worker_raw_dir", ""))).resolve() != Path(str(record.get("raw_dir", ""))).resolve():
        errors.append("watchdog worker_raw_dir does not match record")
    if compact.get("worker_command") != record.get("launch_command"):
        errors.append("watchdog worker command does not match record launch_command")
    if int(compact.get("returncode", -1)) != 0 or compact.get("natural_exit") is not True:
        gates.append("watchdog worker did not exit naturally with rc0")
    if compact.get("no_orphan") is not True or compact.get("stop_reason") != "natural_exit":
        gates.append("watchdog process closeout is not clean")
    if not derived_readable or peak < 0 or peak >= RSS_LIMIT or swap != 0:
        gates.append("watchdog process-tree RSS/swap authority failed")
    resource = {
        "source_sha": compact.get("source_sha"),
        "sample_count": len(raw_lines),
        "peak_process_tree_rss_bytes": peak,
        "max_process_tree_swap_bytes": swap,
        "natural_exit": compact.get("natural_exit"),
        "no_orphan": compact.get("no_orphan"),
        "all_status_readable": derived_readable,
        "stop_reason": compact.get("stop_reason"),
        "worker_launch_command": compact.get("worker_command"),
        "watchdog_raw": str(raw_path),
        "watchdog_raw_sha256": _sha256(raw_path),
        "watchdog_compact": str(compact_path.resolve()),
        "watchdog_compact_sha256": _sha256(compact_path),
    }
    return resource


def _check_pc(record: dict[str, Any], raw_dir: Path, errors: list[str], gates: list[str]) -> dict[str, float | bool]:
    pc = record.get("pc_legality")
    if not isinstance(pc, dict):
        errors.append("pc_legality is missing")
        return {}
    artifacts = pc.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != PC_ROLES:
        errors.append("pc legality artifact role set is incomplete")
        return {}
    rank_count = int(record.get("mpi_size", -1))
    expected_ranks = set(range(rank_count))
    shard_maps: dict[str, dict[int, dict[str, Any]]] = {}
    arrays: dict[str, list[np.ndarray]] = {role: [] for role in PC_ROLES}
    for role in sorted(PC_ROLES):
        shards = artifacts[role].get("shards") if isinstance(artifacts[role], dict) else None
        mapping: dict[int, dict[str, Any]] = {}
        if not isinstance(shards, list):
            errors.append(f"pc {role}: shard list is missing")
            shard_maps[role] = mapping
            continue
        for shard in shards:
            rank = int(shard.get("rank", -1)) if isinstance(shard, dict) else -1
            if rank in mapping or rank < 0:
                errors.append(f"pc {role}: duplicate/invalid rank")
            elif isinstance(shard, dict):
                mapping[rank] = shard
        if set(mapping) != expected_ranks:
            errors.append(f"pc {role}: rank inventory is not exactly 0..mpi-1")
        shard_maps[role] = mapping
        for rank in sorted(mapping):
            values = _load_array(
                raw_dir,
                mapping[rank].get("values"),
                errors,
                f"pc {role}.rank{rank}",
            )
            if values is not None:
                arrays[role].append(values)
    first_shards = shard_maps.get("pc_input_first_before", {})
    ranges: list[tuple[int, int, int]] = [
        (
            rank,
            int(shard.get("ownership_range", [-1, -1])[0]),
            int(shard.get("ownership_range", [-1, -1])[1]),
        )
        for rank, shard in sorted(first_shards.items())
    ]
    if ranges:
        ranges.sort()
        cursor = 0
        global_size = None
        for rank, start, stop in ranges:
            if start != cursor or stop <= start:
                errors.append("pc ownership ranges are not contiguous")
            cursor = stop
            global_size = int(first_shards[rank].get("global_size", -1))
        if global_size != cursor:
            errors.append("pc ownership does not close global size")
    def join(role: str) -> np.ndarray:
        return np.concatenate(arrays[role]) if len(arrays[role]) == rank_count else np.asarray([], dtype=np.complex128)
    joined = {role: join(role) for role in PC_ROLES}
    for role, values in joined.items():
        if values.size == 0 or not np.all(np.isfinite(values)):
            errors.append(f"pc {role}: missing or non-finite values")
    input_unchanged = all(
        np.array_equal(joined[f"pc_input_{name}_before"], joined[f"pc_input_{name}_after"])
        for name in ("first", "second", "combined")
    )
    expected = PC_ALPHA * joined["pc_output_first"] + PC_BETA * joined["pc_output_second"]
    linearity = float(np.linalg.norm(joined["pc_output_combined"] - expected) / max(np.linalg.norm(expected), np.finfo(float).tiny))
    repeat = float(np.linalg.norm(joined["pc_output_repeat"] - joined["pc_output_combined"]) / max(np.linalg.norm(joined["pc_output_combined"]), np.finfo(float).tiny))
    slave_by_rank = pc.get("slave_local_indices_by_rank")
    slave_max = 0.0
    if not isinstance(slave_by_rank, dict):
        errors.append("pc slave inventory is missing")
    else:
        for rank_value, shard in sorted(shard_maps["pc_output_first"].items()):
            rank = str(rank_value)
            indices = np.asarray(slave_by_rank.get(rank, []), dtype=np.int64)
            local_size = int(shard.get("local_size", -1))
            if np.any(indices < 0) or np.any(indices >= local_size):
                errors.append(f"pc slave inventory rank {rank} is out of range")
                continue
            local_indices = indices
            for role in ("pc_output_first", "pc_output_second", "pc_output_combined", "pc_output_repeat"):
                role_shard = shard_maps[role].get(int(rank))
                local = _load_array(
                    raw_dir,
                    role_shard.get("values") if role_shard else None,
                    errors,
                    f"pc {role}.rank{rank}.repeat",
                )
                if local is not None and local_indices.size:
                    slave_max = max(slave_max, float(np.max(np.abs(local[local_indices]))))
        if set(slave_by_rank) != {str(rank) for rank in expected_ranks}:
            errors.append("pc slave inventory rank keys are incomplete")
    finite = all(values.size > 0 and np.all(np.isfinite(values)) for values in joined.values())
    if not input_unchanged:
        gates.append("pc input was modified")
    if not np.isfinite(linearity) or linearity > LINEARITY_LIMIT:
        gates.append("pc linearity failed")
    if not np.isfinite(repeat) or repeat > REPEAT_LIMIT:
        gates.append("pc repeat failed")
    if not finite:
        gates.append("pc finite failed")
    if not np.isfinite(slave_max) or slave_max > SLAVE_LIMIT:
        gates.append("pc slave/primal constraint failed")
    stored = {
        "input_unchanged": bool(pc.get("input_unchanged")),
        "finite": bool(pc.get("finite")),
        "linearity_relative": float(pc.get("linearity_relative", np.nan)),
        "repeat_relative": float(pc.get("repeat_relative", np.nan)),
        "slave_constraint_absolute": float(pc.get("slave_constraint_absolute", np.nan)),
    }
    recomputed = {
        "input_unchanged": input_unchanged,
        "finite": finite,
        "linearity_relative": linearity,
        "repeat_relative": repeat,
        "slave_constraint_absolute": slave_max,
    }
    for name in stored:
        if name in ("input_unchanged", "finite") and stored[name] != recomputed[name]:
            errors.append(f"pc stored {name} disagrees with raw recomputation")
        if name not in ("input_unchanged", "finite") and not np.isclose(stored[name], recomputed[name], rtol=0.0, atol=1.0e-15):
            errors.append(f"pc stored {name} disagrees with raw recomputation")
    return recomputed


def check_record(record_path: Path, watchdog_compact: Path) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    try:
        record = _read_json(record_path)
    except Exception as exc:
        return {"passed": False, "contract_errors": [f"record read failed: {type(exc).__name__}: {exc}"], "gate_failures": []}
    if record.get("schema") != SCHEMA:
        errors.append("schema mismatch")
    case = record.get("case")
    degree, expected_mpi = CASES.get(case, (-1, -1))
    if int(record.get("degree", -1)) != degree or int(record.get("mpi_size", -1)) != expected_mpi:
        errors.append("case/degree/MPI identity mismatch")
    if record.get("source_name") not in SOURCES or record.get("h_nm") != 50.0:
        errors.append("source or h identity mismatch")
    if record.get("method") != "lor_edge_geometric_mg_v1" or record.get("variant") != "sequential-v1":
        errors.append("method/variant mismatch")
    settings = record.get("settings", {})
    expected_settings = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": RESTART,
        "cycle_max_it": RESTART,
        "max_it": MAX_IT,
        "zero_initial_guess": True,
        "residual_replacement": True,
        "residual_limit": RESIDUAL_LIMIT,
        "checkpoint_writer": None,
    }
    for name, expected in expected_settings.items():
        if settings.get(name) != expected:
            errors.append(f"settings.{name} mismatch")
    vcycle = record.get("vcycle_settings", {})
    for name, expected in {
        "chebyshev_degree": 3,
        "power_steps": 10,
        "lambda_hi_factor": 1.10,
        "lambda_lo_factor": 0.10,
        "pre": 1,
        "post": 1,
        "vcycle": 1,
        "coarse_backend": "petsc-preonly-lu-mumps",
        "coarse_scope": "p2_p3_small_oracle_only",
    }.items():
        if vcycle.get(name) != expected:
            errors.append(f"vcycle_settings.{name} mismatch")
    source = record.get("source", {})
    source_end = record.get("source_end", {})
    expected_sha = source.get("expected_sha")
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        errors.append("source SHA is malformed")
    for identity, label in ((source, "source"), (source_end, "source_end")):
        if identity.get("expected_sha") != expected_sha:
            errors.append(f"{label} expected SHA mismatch")
        if identity.get("branch") != BRANCH:
            errors.append(f"{label} branch mismatch")
        if identity.get("commit_sha_start", expected_sha) != expected_sha and label == "source":
            errors.append("source start SHA mismatch")
        if label == "source_end" and identity.get("commit_sha_end") != expected_sha:
            errors.append("source end SHA mismatch")
        if identity.get("clean_start" if label == "source" else "clean_end") is not True:
            errors.append(f"{label} clean identity is false")
    if re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit_sha_start", ""))) is None:
        errors.append("source commit_sha_start is not lowercase 40-hex")
    if re.fullmatch(r"[0-9a-f]{40}", str(source_end.get("commit_sha_end", ""))) is None:
        errors.append("source_end commit_sha_end is not lowercase 40-hex")
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    if not raw_dir.is_dir() or raw_dir == record_path.resolve():
        errors.append("raw_dir is missing or not distinct from record")
    command = record.get("command")
    launch_command = record.get("launch_command")
    runtime = record.get("runtime", {})
    if runtime.get("qualified_activation") != "1":
        errors.append("runtime is not qualified activation")
    if runtime.get("petsc_scalar_type") != "complex128" or runtime.get("petsc_int_type") != "int32":
        errors.append("runtime PETSc ABI is not complex128/int32")
    if int(runtime.get("mpi_size", -1)) != expected_mpi:
        errors.append("runtime MPI size mismatch")
    if not isinstance(command, list) or not command or not isinstance(command[0], str) or not Path(command[0]).is_absolute():
        errors.append("worker command is not an absolute qualified command")
    if isinstance(command, list) and command and runtime.get("sys_executable") != command[0]:
        errors.append("runtime sys_executable does not equal direct command argv[0]")
    expected_command = [
        command[0] if isinstance(command, list) and command else "",
        "-m",
        "benchmarks.run_task038_full3d_lor_edge_geometric_mg",
        "--stage",
        "s4-a3",
        "--case",
        str(case),
        "--source",
        str(record.get("source_name")),
        "--raw-dir",
        str(raw_dir),
        "--record",
        str(Path(str(record.get("record_path", ""))).resolve()),
        "--expected-source-sha",
        str(expected_sha),
        "--expected-mpi-size",
        str(expected_mpi),
    ]
    if command != expected_command:
        errors.append("direct worker command does not match frozen case arguments")
    if expected_mpi == 1:
        if launch_command != command:
            errors.append("MPI1 launch_command must equal direct command")
    elif isinstance(launch_command, list):
        if (
            len(launch_command) != len(expected_command) + 3
            or not launch_command
            or not isinstance(launch_command[0], str)
            or not Path(launch_command[0]).is_absolute()
            or Path(launch_command[0]).name != "mpiexec"
            or launch_command[1:3] != ["-n", str(expected_mpi)]
            or launch_command[3:] != command
        ):
            errors.append("MPI2 launch_command does not have exact mpiexec -n prefix")
    else:
        errors.append("MPI2 launch_command is missing")
    provenance = record.get("provenance", {})
    for name in (
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
    ):
        if re.fullmatch(r"[0-9a-f]{64}", str(provenance.get(name, ""))) is None:
            errors.append(f"provenance {name} is not lowercase 64-hex")
    canonical = {}
    if raw_dir.is_dir():
        for role in CANONICAL_ROLES:
            canonical[role] = _merge_canonical(record, raw_dir, role, errors)
    rhs = canonical.get("rhs", {})
    rhs_repeat = canonical.get("rhs_repeat", {})
    action = canonical.get("final_action", {})
    saved = canonical.get("final_true_residual", {})
    if set(rhs) != set(rhs_repeat):
        errors.append("rhs/rhs_repeat canonical key sets differ")
    if set(rhs) != set(action) or set(rhs) != set(saved):
        errors.append("dual canonical key sets are not aligned")
    if rhs:
        rhs_values = np.asarray([rhs[key] for key in sorted(rhs)], dtype=np.complex128)
        repeat_values = np.asarray([rhs_repeat[key] for key in sorted(rhs)], dtype=np.complex128)
        action_values = np.asarray([action[key] for key in sorted(rhs)], dtype=np.complex128)
        saved_values = np.asarray([saved[key] for key in sorted(rhs)], dtype=np.complex128)
        residual_values = rhs_values - action_values
        rhs_repeat_relative = float(np.linalg.norm(rhs_values - repeat_values) / max(np.linalg.norm(rhs_values), np.finfo(float).tiny))
        residual_identity = float(np.linalg.norm(residual_values - saved_values) / max(np.linalg.norm(rhs_values), np.finfo(float).tiny))
        rho = float(np.linalg.norm(saved_values) / max(np.linalg.norm(rhs_values), np.finfo(float).tiny))
        if rhs_repeat_relative > REPEAT_LIMIT:
            gates.append("rhs repeat identity failed")
        if residual_identity > 1.0e-12:
            gates.append("final true residual identity failed")
        if not np.isfinite(rho) or rho > RESIDUAL_LIMIT:
            gates.append("final explicit true residual failed")
    else:
        rhs_repeat_relative = float("inf")
        residual_identity = float("inf")
        rho = float("inf")
        gates.append("dual canonical evidence is empty")
    outer = record.get("outer", {})
    cycles = outer.get("cycles", []) if isinstance(outer, dict) else []
    if not isinstance(cycles, list) or not cycles:
        errors.append("outer cycle ledger is empty")
        cycles = []
    cursor = 0
    for index, cycle in enumerate(cycles):
        start = int(cycle.get("start_iteration", -1))
        end = int(cycle.get("end_iteration", -1))
        iterations = int(cycle.get("iterations", -1))
        if start != cursor or end - start != iterations or not 0 < iterations <= RESTART:
            errors.append(f"cycle {index} is not continuous or has invalid iteration count")
        if cycle.get("ksp_destroyed") is not True:
            errors.append(f"cycle {index} KSP was not destroyed")
        if "resource" in cycle:
            errors.append(f"cycle {index} contains non-scalar resource payload")
        if not np.isfinite(float(cycle.get("explicit_true_residual", np.nan))):
            errors.append(f"cycle {index} residual is not finite")
        cursor = end
    final_iterations = int(outer.get("iterations", -1))
    if cursor != final_iterations or final_iterations < 0 or final_iterations > MAX_IT:
        errors.append("outer iteration ledger does not close")
    if cycles and not np.isclose(float(cycles[-1].get("explicit_true_residual", np.nan)), float(outer.get("final_true_residual", np.nan)), rtol=0.0, atol=1.0e-13):
        errors.append("final cycle residual does not match outer final residual")
    if not np.isclose(float(outer.get("final_true_residual", np.nan)), rho, rtol=0.0, atol=1.0e-12):
        errors.append("stored and raw final residual differ")
    if int(outer.get("ksp_destroy_count", -1)) != len(cycles):
        errors.append("outer KSP destroy count does not equal cycle count")
    rank_facts = record.get("rank_facts")
    rank_fields = (
        "iterations",
        "matvec_count",
        "pc_apply_count",
        "explicit_action_count",
        "ksp_destroy_count",
        "final_true_residual",
    )
    if not isinstance(rank_facts, list) or len(rank_facts) != expected_mpi:
        errors.append("rank_facts inventory does not match MPI size")
        rank_facts = []
    rank_map: dict[int, dict[str, Any]] = {}
    for fact in rank_facts:
        if not isinstance(fact, dict):
            errors.append("rank fact is not an object")
            continue
        rank = int(fact.get("rank", -1))
        if rank in rank_map or rank < 0:
            errors.append("rank_facts contains duplicate/invalid rank")
        else:
            rank_map[rank] = fact
    if set(rank_map) != set(range(expected_mpi)):
        errors.append("rank_facts rank inventory is not exact")
    for rank, fact in sorted(rank_map.items()):
        if fact.get("source_unchanged") is not True:
            errors.append(f"rank {rank} source input changed")
        scalar = fact.get("outer_scalar")
        if not isinstance(scalar, dict):
            errors.append(f"rank {rank} outer scalar ledger is missing")
            continue
        for field in rank_fields:
            if scalar.get(field) != outer.get(field):
                errors.append(f"rank {rank} outer field {field} does not close")
        if scalar.get("ksp_destroy_count") != len(cycles):
            errors.append(f"rank {rank} KSP destroy count does not close")
    if record.get("source_unchanged") is not True:
        errors.append("top-level source_unchanged is false")
    pc_metrics = _check_pc(record, raw_dir, errors, gates) if raw_dir.is_dir() else {}
    forbidden = record.get("production", {})
    false_fields = (
        "build_hx", "scalar_node_matrix", "high_order_global_aij", "global_dense_transfer",
        "global_numeric_allgather", "global_direct_coarse", "pcgamg_hierarchy_built",
        "p6_exact_edge_factor_built", "numeric_allgather",
    )
    for field in false_fields:
        if forbidden.get(field) is not False:
            errors.append(f"forbidden production field {field} is not false")
    node_audit = record.get("rank_facts", [{}])[0].get("node_audit", {}) if record.get("rank_facts") else {}
    if node_audit.get("scalar_node_matrix") is not False or node_audit.get("global_numeric_allgather") is not False:
        errors.append("fixture node audit did not prove forbidden objects absent")
    fixture_audit = record.get("fixture_audit", {})
    hx_audit = fixture_audit.get("hx_audit", {}) if isinstance(fixture_audit, dict) else {}
    if fixture_audit.get("high_order_global_aij") is not False:
        errors.append("fixture audit field high_order_global_aij is not false")
    if hx_audit.get("high_order_aij") is not False:
        errors.append("HX audit field high_order_aij is not false")
    for field in ("global_transfer_matrix", "global_numeric_allgather"):
        if fixture_audit.get(field) is not False or hx_audit.get(field) is not False:
            errors.append(f"fixture/HX audit field {field} is not false")
    resource = _check_watchdog(record, record_path, watchdog_compact, errors, gates)
    return {
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "metrics": {
            "rho": rho,
            "rhs_repeat_relative": rhs_repeat_relative,
            "final_residual_identity_relative": residual_identity,
            "iterations": final_iterations,
            "cycles": len(cycles),
            "pc": pc_metrics,
        },
        "resource": resource,
        "case": case,
        "source_name": record.get("source_name"),
        "record_sha256": _sha256(record_path),
    }


def check_records(record_paths: list[Path], watchdog_paths: list[Path]) -> dict[str, Any]:
    expected_order = [f"{case}/{source}" for case in CASES for source in SOURCES]
    errors: list[str] = []
    gates: list[str] = []
    individual = []
    by_identity: dict[str, dict[str, Any]] = {}
    record_by_identity: dict[str, tuple[Path, dict[str, Any]]] = {}
    if len(record_paths) != 16 or len(watchdog_paths) != 16:
        errors.append("aggregate requires exactly 16 records and watchdog compacts")
    for record_path, watchdog_path in zip(record_paths, watchdog_paths, strict=False):
        result = check_record(record_path, watchdog_path)
        individual.append(result)
        identity = f"{result.get('case')}/{result.get('source_name')}"
        try:
            loaded_record = _read_json(record_path)
        except Exception:
            loaded_record = None
        if isinstance(loaded_record, dict):
            if identity in record_by_identity:
                errors.append(f"aggregate duplicate case/source {identity}")
            record_by_identity[identity] = (record_path, loaded_record)
        by_identity[identity] = result
        errors.extend(f"{identity}: {item}" for item in result.get("contract_errors", []))
        gates.extend(f"{identity}: {item}" for item in result.get("gate_failures", []))
    if list(record_by_identity) != expected_order:
        errors.append("aggregate case/source order is not the frozen 16-case order")
    pairs = []
    for degree in (2, 3):
        for source in SOURCES:
            identity = f"p{degree}-mpi1/{source}"
            other_identity = f"p{degree}-mpi2/{source}"
            left = by_identity.get(identity)
            right = by_identity.get(other_identity)
            left_record = record_by_identity.get(identity)
            right_record = record_by_identity.get(other_identity)
            if left is None or right is None or left_record is None or right_record is None:
                errors.append(f"missing pair p{degree}/{source}")
                continue
            left_path, left_data = left_record
            right_path, right_data = right_record
            pair_errors: list[str] = []
            left_raw = Path(str(left_data.get("raw_dir", ""))).resolve()
            right_raw = Path(str(right_data.get("raw_dir", ""))).resolve()
            source_left = _merge_canonical(left_data, left_raw, "source", pair_errors)
            source_right = _merge_canonical(right_data, right_raw, "source", pair_errors)
            rhs_left = _merge_canonical(left_data, left_raw, "rhs", pair_errors)
            rhs_right = _merge_canonical(right_data, right_raw, "rhs", pair_errors)
            action_left = _merge_canonical(left_data, left_raw, "final_action", pair_errors)
            action_right = _merge_canonical(right_data, right_raw, "final_action", pair_errors)
            source_identity = _relative_maps(source_left, source_right, pair_errors, f"{degree}/{source} source")
            rhs_identity = _relative_maps(rhs_left, rhs_right, pair_errors, f"{degree}/{source} rhs")
            provenance_match = _provenance_match(left_data, right_data)
            if set(action_left) != set(action_right):
                pair_errors.append(f"{degree}/{source} action canonical key sets differ")
                action_relative = float("inf")
            elif set(action_left) != set(rhs_left):
                pair_errors.append(f"{degree}/{source} action/rhs key sets differ")
                action_relative = float("inf")
            else:
                left_action = np.asarray([action_left[key] for key in sorted(action_left)], dtype=np.complex128)
                right_action = np.asarray([action_right[key] for key in sorted(action_left)], dtype=np.complex128)
                rhs_norm = np.linalg.norm(np.asarray([rhs_left[key] for key in sorted(rhs_left)], dtype=np.complex128))
                action_relative = float(np.linalg.norm(left_action - right_action) / max(rhs_norm, np.finfo(float).tiny))
            rho_left = float(left.get("metrics", {}).get("rho", np.inf))
            rho_right = float(right.get("metrics", {}).get("rho", np.inf))
            bound = _dynamic_action_bound(rho_left, rho_right, rhs_identity)
            within_bound = bool(
                source_identity <= 1.0e-12
                and rhs_identity <= 1.0e-12
                and provenance_match
                and _within_dynamic_action_bound(
                    action_relative, rho_left, rho_right, rhs_identity
                )
            )
            if source_identity > 1.0e-12:
                gates.append(f"p{degree}/{source}: source identity pair gate failed")
            if rhs_identity > 1.0e-12:
                gates.append(f"p{degree}/{source}: RHS identity pair gate failed")
            if not provenance_match:
                gates.append(f"p{degree}/{source}: provenance identities differ")
            if action_relative > bound:
                gates.append(f"p{degree}/{source}: dynamic action bound failed")
            errors.extend(pair_errors)
            pairs.append({
                "degree": degree,
                "source_name": source,
                "mpi1_record_sha256": _sha256(left_path),
                "mpi2_record_sha256": _sha256(right_path),
                "source_identity": source_identity,
                "rhs_identity": rhs_identity,
                "provenance_match": provenance_match,
                "final_action_pair_relative": action_relative,
                "dynamic_action_bound": bound,
                "rho_mpi1": rho_left,
                "rho_mpi2": rho_right,
                "within_bound": within_bound,
            })
    return {
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "individual": individual,
        "pairs": pairs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--watchdog-compact", type=Path)
    parser.add_argument("--records", nargs="+", type=Path)
    parser.add_argument("--watchdogs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    if args.record is not None:
        if args.watchdog_compact is None:
            parser.error("single-case mode requires --watchdog-compact")
        result = check_record(args.record, args.watchdog_compact)
    elif args.records is not None and args.watchdogs is not None:
        result = check_records(args.records, args.watchdogs)
    else:
        parser.error("use single-case or aggregate mode")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
