"""Independent checker for the final E-only LOR-foundation record.

This module reads JSON and NumPy evidence only.  It does not import the
worker, solver, PETSc, DOLFINx, or MPI, and it never trusts a worker status as
the numerical decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.lor-native-complex-hx.foundation-e-record.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
CASE = "p3-mpi1"
SOURCE_NAME = "random"
VARIANT = "sequential-v1"
DEGREE = 3
H_NM = 50.0
RESTART = 20
MAX_IT = 10_000
CHECKPOINT_INTERVAL = 500
RESIDUAL_LIMIT = 1.0e-8
DIRECT_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
INPUT_LIMIT = 1.0e-12
PRIMAL_LIMIT = 1.0e-12
WATCHDOG_RSS_LIMIT = 500_000_000
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
WATCHDOG_POLL_SECONDS = 0.25
PRIOR_Q0 = {
    "source_sha": "47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f",
    "record_path": "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json",
    "record_sha256": "2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82",
    "checker_path": "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1_checker.json",
    "checker_sha256": "be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea",
    "rho": 4.203423379090078e-4,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_sha(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    return hashlib.sha256(payload).hexdigest()


def _finite_sha(value: Any, length: int) -> bool:
    text = str(value)
    return len(text) == length and all(char in "0123456789abcdef" for char in text)


def _owner_key_identity(left: Any, right: Any) -> bool:
    left_keys = [str(key) for key in np.asarray(left).tolist()]
    right_keys = [str(key) for key in np.asarray(right).tolist()]
    return (
        len(left_keys) == len(set(left_keys))
        and len(right_keys) == len(set(right_keys))
        and len(left_keys) == len(right_keys)
        and set(left_keys) == set(right_keys)
    )


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny))


def _load_array(raw_dir: Path, descriptor: dict[str, Any]) -> np.ndarray:
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("artifact path is not a relative filename")
    path = (raw_dir / relative).resolve()
    if raw_dir.resolve() not in path.parents:
        raise ValueError("artifact path escapes raw_dir")
    if not path.is_file():
        raise FileNotFoundError(f"missing artifact {path}")
    if int(descriptor.get("bytes", -1)) != path.stat().st_size:
        raise ValueError(f"artifact byte count mismatch: {path.name}")
    if str(descriptor.get("sha256")) != _sha256(path):
        raise ValueError(f"artifact SHA256 mismatch: {path.name}")
    values = np.asarray(np.load(path, allow_pickle=False))
    if str(values.dtype) != str(descriptor.get("dtype")):
        raise ValueError(f"artifact dtype mismatch: {path.name}")
    if list(values.shape) != list(descriptor.get("shape", [])):
        raise ValueError(f"artifact shape mismatch: {path.name}")
    if values.dtype.kind not in "OUS" and not np.all(np.isfinite(values)):
        raise ValueError(f"artifact is non-finite: {path.name}")
    return values


def _load_role(raw_dir: Path, name: str, descriptor: dict[str, Any]) -> tuple[str, np.ndarray, np.ndarray]:
    role = descriptor.get("role")
    keys = _load_array(raw_dir, descriptor["keys"])
    values = _load_array(raw_dir, descriptor["values"])
    if keys.ndim != 1 or values.ndim != 1 or keys.size != values.size:
        raise ValueError(f"invalid paired role {name}")
    keys = np.asarray(keys, dtype=str)
    if np.unique(keys).size != keys.size:
        raise ValueError(f"duplicate keys in role {name}")
    return str(role), keys, np.asarray(values, dtype=np.complex128)


def _align(
    left_keys: np.ndarray,
    left_values: np.ndarray,
    right_keys: np.ndarray,
    right_values: np.ndarray,
    name: str,
) -> tuple[np.ndarray, np.ndarray]:
    if set(left_keys.tolist()) != set(right_keys.tolist()):
        raise ValueError(f"key set mismatch for {name}")
    positions = {key: index for index, key in enumerate(right_keys.tolist())}
    return left_values, np.asarray([right_values[positions[key]] for key in left_keys], dtype=np.complex128)


def _check_settings(record: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": RESTART,
        "max_it": MAX_IT,
        "residual_replacement": True,
        "zero_initial_guess": True,
        "residual_limit": RESIDUAL_LIMIT,
        "checkpoint_interval": CHECKPOINT_INTERVAL,
        "first_checkpoint_iteration": None,
    }
    settings = record.get("settings")
    if not isinstance(settings, dict):
        errors.append("missing settings")
        return
    for key, value in expected.items():
        if settings.get(key) != value:
            errors.append(f"settings.{key} mismatch")
    if settings.get("direct_backend") != "petsc-preonly-lu-mumps":
        errors.append("direct backend mismatch")


def _check_stage_markers(raw_dir: Path, reached: int, errors: list[str]) -> None:
    marker_path = raw_dir / "stage-rank0.jsonl"
    if not marker_path.is_file():
        errors.append("rank-0 stage marker ledger is missing")
        return
    try:
        rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines() if line]
        stages = {str(row["stage"]) for row in rows}
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"stage marker ledger is invalid: {exc}")
        return
    required = {"setup", "source_identity_closed", "runtime_identity", "single_apply_legality", "outer_start", "final", "record_closeout", "record_written"}
    required.update(f"checkpoint-{iteration}" for iteration in range(CHECKPOINT_INTERVAL, reached + 1, CHECKPOINT_INTERVAL))
    missing = sorted(required - stages)
    if missing:
        errors.append(f"stage marker ledger missing {missing}")


def _check_checkpoint(
    raw_dir: Path,
    fact: dict[str, Any],
    record: dict[str, Any],
    errors: list[str],
) -> None:
    iteration = int(fact.get("iteration", -1))
    expected_dir = (raw_dir / f"checkpoint-{iteration}").resolve()
    manifest_path = Path(str(fact.get("manifest_path", ""))).resolve()
    if manifest_path != expected_dir / "manifest.json" or raw_dir.resolve() not in manifest_path.parents:
        errors.append(f"checkpoint-{iteration} path is not bound to raw_dir")
        return
    if not manifest_path.is_file():
        errors.append(f"checkpoint-{iteration} manifest missing")
        return
    if str(fact.get("manifest_sha256")) != _sha256(manifest_path):
        errors.append(f"checkpoint-{iteration} manifest SHA mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("iteration") != iteration:
        errors.append(f"checkpoint-{iteration} iteration mismatch")
    if not np.isfinite(float(manifest.get("explicit_true_residual", np.nan))) or float(manifest["explicit_true_residual"]) < 0.0:
        errors.append(f"checkpoint-{iteration} explicit residual invalid")
    if not np.isclose(
        float(manifest.get("explicit_true_residual", np.nan)),
        float(fact.get("explicit_true_residual", np.nan)),
        rtol=1.0e-14,
        atol=1.0e-15,
    ):
        errors.append(f"checkpoint-{iteration} residual fact mismatch")
    if manifest.get("schema") != "fixed-memory-krylov.solution-checkpoint.v1":
        errors.append(f"checkpoint-{iteration} schema mismatch")
    if manifest.get("solution_only") is not True or manifest.get("vector_roles") != ["solution"]:
        errors.append(f"checkpoint-{iteration} is not solution-only")
    if manifest.get("numeric_allgather") is not False:
        errors.append(f"checkpoint-{iteration} numeric allgather contract failed")
    if manifest.get("source_sha") != record["source"]["expected_sha"]:
        errors.append(f"checkpoint-{iteration} source SHA mismatch")
    for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
        if manifest.get(key) != record["provenance"].get(key):
            errors.append(f"checkpoint-{iteration} {key} mismatch")
    actual_files = {path.name for path in expected_dir.iterdir()}
    if actual_files != {"manifest.json", "solution_rank0.npy"}:
        errors.append(f"checkpoint-{iteration} contains undeclared files")
    ranks = manifest.get("ranks")
    if not isinstance(ranks, list) or len(ranks) != 1 or int(ranks[0].get("rank", -1)) != 0:
        errors.append(f"checkpoint-{iteration} rank manifest incomplete")
        return
    descriptor = ranks[0].get("solution", {})
    try:
        values = _load_array(expected_dir, descriptor)
        if values.ndim != 1 or values.size != int(descriptor.get("shape", [-1])[0]):
            errors.append(f"checkpoint-{iteration} solution shard shape invalid")
    except (KeyError, OSError, ValueError) as exc:
        errors.append(f"checkpoint-{iteration} shard invalid: {exc}")


def _check_boundary_facts(
    cycles: list[dict[str, Any]],
    boundary_facts: Any,
    reached: int,
    errors: list[str],
    gates: list[str],
) -> None:
    expected_iterations = list(range(CHECKPOINT_INTERVAL, reached + 1, CHECKPOINT_INTERVAL))
    if not isinstance(boundary_facts, list):
        errors.append("boundary facts do not enumerate exactly the reached 500-step boundaries")
        return
    try:
        actual_iterations = [int(item.get("iteration", -1)) for item in boundary_facts]
    except (AttributeError, TypeError, ValueError):
        errors.append("boundary facts do not enumerate exactly the reached 500-step boundaries")
        return
    if actual_iterations != expected_iterations:
        errors.append("boundary facts do not enumerate exactly the reached 500-step boundaries")
        return
    cycle_by_end = {int(cycle.get("end_iteration", -1)): cycle for cycle in cycles}
    cumulative_matvec = 0
    cumulative_pc = 0
    cumulative_explicit = 1
    cumulative_wall = 0.0
    next_boundary = 0
    facts_by_iteration = {int(item.get("iteration", -1)): item for item in boundary_facts}
    for cycle in cycles:
        end = int(cycle.get("end_iteration", -1))
        cumulative_matvec += int(cycle.get("matvec_count", -1))
        cumulative_pc += int(cycle.get("pc_apply_count", -1))
        cumulative_explicit += 1
        cumulative_wall += float(cycle.get("wall_seconds", np.nan))
        if end in facts_by_iteration:
            fact = facts_by_iteration[end]
            next_boundary += 1
            if int(fact.get("matvec_count", -1)) != cumulative_matvec:
                errors.append(f"boundary {end} matvec count is not cumulative")
            if int(fact.get("pc_apply_count", -1)) != cumulative_pc:
                errors.append(f"boundary {end} PC count is not cumulative")
            if int(fact.get("cumulative_explicit_true_residual_action_count", -1)) != cumulative_explicit:
                errors.append(f"boundary {end} explicit residual-action count is not cumulative")
            if int(fact.get("cumulative_high_action_count", -1)) != cumulative_matvec + cumulative_explicit:
                errors.append(f"boundary {end} total high-action count is not cumulative")
            if fact.get("wall_semantics") != "cumulative_cycle_wall_seconds_excludes_setup":
                errors.append(f"boundary {end} wall semantics are not explicit")
            try:
                fact_wall = float(fact.get("wall_seconds", np.nan))
                fact_residual = float(fact.get("explicit_true_residual", np.nan))
            except (TypeError, ValueError):
                errors.append(f"boundary {end} scalar facts are invalid")
                continue
            if not np.isfinite(fact_wall) or not np.isfinite(fact_residual):
                errors.append(f"boundary {end} scalar facts are non-finite")
            if not np.isclose(fact_wall, cumulative_wall, rtol=1.0e-12, atol=1.0e-12):
                errors.append(f"boundary {end} wall time is not cumulative")
            if not np.isclose(
                fact_residual,
                float(cycle.get("explicit_true_residual", np.nan)),
                rtol=1.0e-12,
                atol=1.0e-15,
            ):
                errors.append(f"boundary {end} residual does not match its cycle")
            resource = fact.get("resource")
            if resource != cycle.get("resource"):
                errors.append(f"boundary {end} resource does not match its cycle")
            if not isinstance(resource, dict):
                gates.append(f"boundary {end} resource is missing")
            else:
                tree = resource.get("process_tree", {})
                try:
                    rss = int(tree.get("rss_bytes", -1))
                    swap = int(tree.get("swap_bytes", -1))
                except (TypeError, ValueError):
                    rss = -1
                    swap = -1
                if tree.get("all_status_readable") is not True or rss < 0 or rss >= WATCHDOG_RSS_LIMIT or swap != 0:
                    gates.append(f"boundary {end} process-tree resource failed")
                cgroup = resource.get("job_cgroup", {})
                if cgroup.get("dedicated_job_cgroup") is True:
                    try:
                        dedicated_swap = int(cgroup.get("swap_current_bytes", -1))
                    except (TypeError, ValueError):
                        dedicated_swap = -1
                    if dedicated_swap != 0:
                        gates.append(f"boundary {end} dedicated cgroup swap failed")
            if next_boundary > 1:
                previous = facts_by_iteration[expected_iterations[next_boundary - 2]]
                if fact_wall < float(previous.get("wall_seconds", np.nan)) or int(fact.get("matvec_count", -1)) < int(previous.get("matvec_count", -1)) or int(fact.get("pc_apply_count", -1)) < int(previous.get("pc_apply_count", -1)):
                    errors.append(f"boundary {end} cumulative facts are not monotone")
    if set(cycle_by_end) & set(expected_iterations) != set(expected_iterations):
        errors.append("boundary facts have no corresponding cycle boundary")


def _check_watchdog(
    record: dict[str, Any], record_path: Path, watchdog_path: Path, errors: list[str], gates: list[str]
) -> dict[str, Any]:
    if not watchdog_path.is_file():
        errors.append("missing external watchdog compact")
        return {}
    compact = json.loads(watchdog_path.read_text(encoding="utf-8"))
    if compact.get("schema") != WATCHDOG_SCHEMA:
        errors.append("watchdog schema mismatch")
    if compact.get("worker_record") != str(record_path.resolve()):
        errors.append("watchdog worker_record binding mismatch")
    if compact.get("worker_raw_dir") != str(Path(record["raw_dir"]).resolve()):
        errors.append("watchdog worker_raw_dir binding mismatch")
    if compact.get("source_sha") != record.get("source", {}).get("expected_sha"):
        errors.append("watchdog source SHA binding mismatch")
    raw_path = Path(str(compact.get("watchdog_raw", ""))).resolve()
    try:
        if str(compact.get("raw_sha256")) != _sha256(raw_path):
            errors.append("watchdog raw SHA mismatch")
        samples = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"watchdog raw unreadable: {exc}")
        return compact
    if compact.get("sample_count") != len(samples):
        errors.append("watchdog compact sample_count does not match raw sample count")
    raw_status = bool(samples) and all(
        sample.get("authority", {}).get("process_tree", {}).get("all_status_readable") is True
        for sample in samples
    )
    if compact.get("all_status_readable") is not raw_status:
        errors.append("watchdog compact all_status_readable does not match raw")
    if compact.get("watchdog_poll_seconds") != WATCHDOG_POLL_SECONDS:
        errors.append("watchdog poll interval is not the fixed 0.25 seconds")
    if compact.get("watchdog_rss_limit_bytes") != WATCHDOG_RSS_LIMIT:
        errors.append("watchdog RSS limit is not the fixed 500000000 bytes")
    if compact.get("worker_command") != record.get("command"):
        errors.append("watchdog worker_command does not exactly match worker record command")
    rss_values: list[int] = []
    for sample in samples:
        tree = sample.get("authority", {}).get("process_tree", {})
        if tree.get("all_status_readable") is not True or int(tree.get("swap_bytes", -1)) != 0:
            gates.append("external watchdog status unreadable or swap nonzero")
        rss = int(tree.get("rss_bytes", -1))
        if rss < 0:
            errors.append("external watchdog RSS missing")
        else:
            rss_values.append(rss)
        cgroup = sample.get("authority", {}).get("job_cgroup", {})
        if cgroup.get("dedicated_job_cgroup") is True and int(cgroup.get("swap_current_bytes", -1)) != 0:
            gates.append("external watchdog dedicated cgroup swap nonzero")
    peak = max(rss_values, default=-1)
    if peak < 0:
        errors.append("external watchdog has no readable RSS sample")
    elif peak >= WATCHDOG_RSS_LIMIT:
        gates.append(f"external watchdog process-tree RSS {peak} >= {WATCHDOG_RSS_LIMIT}")
    try:
        compact_peak = int(compact.get("peak_process_tree_rss_bytes", -1))
    except (TypeError, ValueError):
        compact_peak = -1
    if compact_peak != peak:
        errors.append("watchdog compact peak RSS does not match raw")
    raw_swap = max(
        (
            int(sample.get("authority", {}).get("process_tree", {}).get("swap_bytes", -1))
            for sample in samples
        ),
        default=-1,
    )
    try:
        compact_swap = int(compact.get("max_process_tree_swap_bytes", -1))
    except (TypeError, ValueError):
        compact_swap = -1
    if compact_swap != raw_swap:
        errors.append("watchdog compact swap does not match raw")
    if compact.get("no_orphan") is not True:
        errors.append("watchdog no_orphan is not explicitly true")
    if compact.get("returncode") != 0 or compact.get("natural_exit") is not True:
        gates.append("worker did not have natural rc0/natural-exit watchdog closeout")
    if compact.get("stop_reason") != "natural_exit":
        gates.append(f"watchdog stop reason is {compact.get('stop_reason')!r}")
    return compact


def check_record(
    record_path: Path,
    watchdog_path: Path,
    expected_source_sha: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record_path = Path(record_path).resolve()
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "contract_errors": [f"record unreadable: {exc}"], "gate_failures": []}

    if record.get("schema") != SCHEMA:
        errors.append("schema mismatch")
    if record.get("stage") != "foundation-e" or record.get("case") != CASE:
        errors.append("stage/case mismatch")
    if record.get("degree") != DEGREE or float(record.get("h_nm", np.nan)) != H_NM:
        errors.append("degree/h_nm mismatch")
    if record.get("source_name") != SOURCE_NAME or record.get("variant") != VARIANT or record.get("mpi_size") != 1:
        errors.append("source/variant/MPI identity mismatch")
    if record.get("record_path") != str(record_path):
        errors.append("record_path provenance mismatch")
    _check_settings(record, errors)
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    if not raw_dir.is_absolute() or not raw_dir.is_dir() or record_path == raw_dir:
        errors.append("record raw_dir is missing or malformed")
    _check_stage_markers(raw_dir, int(record.get("outer", {}).get("iterations", -1)), errors)
    source = record.get("source", {})
    source_sha = str(source.get("expected_sha", ""))
    if not _finite_sha(source_sha, 40):
        errors.append("source expected_sha is not a lowercase 40-hex SHA")
    if expected_source_sha is not None and source_sha != str(expected_source_sha):
        errors.append("source expected SHA differs from CLI")
    if source.get("branch") != BRANCH or source.get("clean_start") is not True or source.get("clean_end") is not True:
        errors.append("source branch/clean provenance mismatch")
    if source.get("commit_sha_start") != source_sha or source.get("commit_sha_end") != source_sha:
        errors.append("source start/end commit SHA mismatch")
    command = record.get("command")
    expected_command_tail = [
        "-m", "benchmarks.run_task038_full3d_lor_hx_foundation", "--stage", "foundation-e",
        "--case", CASE, "--raw-dir", str(raw_dir), "--record", str(record_path),
        "--expected-source-sha", source_sha, "--expected-mpi-size", "1",
    ]
    if (
        not isinstance(command, list)
        or len(command) != len(expected_command_tail) + 1
        or command[1:] != expected_command_tail
        or not isinstance(command[0], str)
        or not command[0]
        or not Path(command[0]).is_absolute()
    ):
        errors.append("worker command provenance is not the fixed ordered invocation")
    runtime = record.get("runtime", {})
    if not isinstance(runtime, dict):
        errors.append("runtime identity is missing")
    else:
        for key, expected in (
            ("qualified_activation", "1"),
            ("mpi_size", 1),
            ("petsc_scalar_type", "complex128"),
            ("petsc_int_type", "int32"),
        ):
            if runtime.get(key) != expected:
                errors.append(f"runtime.{key} mismatch")
        threads = runtime.get("threads")
        if not isinstance(threads, dict) or any(threads.get(name) != "1" for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")):
            errors.append("runtime thread contract is not one thread")
    provenance = record.get("provenance", {})
    for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
        if not _finite_sha(provenance.get(key), 64):
            errors.append(f"invalid {key}")
    if record.get("prior_q0_reference") != PRIOR_Q0:
        errors.append("immutable prior Q0 reference does not match")
    _check_watchdog(record, record_path, Path(watchdog_path).resolve(), errors, gates)

    artifacts = record.get("canonical_artifacts", {})
    expected_roles = {
        "source_before", "source_after", "high_rhs", "high_rhs_repeat",
        "e_input_before", "e_input_after", "e_output", "e_repeat",
        "e_final_solution", "e_final_action", "e_final_true_residual",
        "e_output_constraint", "e_repeat_constraint", "e_final_constraint",
    }
    if set(artifacts) != expected_roles:
        errors.append("canonical artifact role set mismatch")
    loaded: dict[str, tuple[str, np.ndarray, np.ndarray]] = {}
    try:
        for name in expected_roles:
            loaded[name] = _load_role(raw_dir, name, artifacts[name])
    except (KeyError, OSError, ValueError) as exc:
        errors.append(f"canonical artifact invalid: {exc}")

    owners = record.get("owner_artifacts", {})
    try:
        owner_input = _load_role(raw_dir, "e_low_input_owner", owners["e_low_input_owner"])
        owner_solution = _load_role(raw_dir, "e_low_solution_owner", owners["e_low_solution_owner"])
        if owner_input[0] != "dual" or owner_solution[0] != "primal":
            errors.append("low owner role metadata mismatch")
        if not _owner_key_identity(owner_input[1], owner_solution[1]):
            errors.append("low owner input/solution key identity mismatch")
        owner_count = record.get("route_audit", {}).get("owner_count")
        if owner_count != owner_input[1].size or owner_count != owner_solution[1].size:
            errors.append("low owner count does not match both raw inventories")
        for key in np.concatenate((owner_input[1], owner_solution[1])):
            prefix, _, numeric = str(key).partition(":")
            if prefix != "owner" or not numeric.isdigit():
                errors.append("low owner key is not a deterministic numeric owner key")
                break
    except (KeyError, OSError, ValueError) as exc:
        errors.append(f"owner artifact invalid: {exc}")

    component_hashes = record.get("component_hashes", {})
    for name, descriptor in {**artifacts, **owners}.items():
        try:
            expected_hash = _identity_sha(
                {
                    "keys_sha256": descriptor["keys"]["sha256"],
                    "values_sha256": descriptor["values"]["sha256"],
                }
            )
            if component_hashes.get(name) != expected_hash:
                errors.append(f"component hash mismatch: {name}")
        except (KeyError, TypeError):
            errors.append(f"component hash missing: {name}")

    route = record.get("route_audit", {})
    for key in ("owner_inventory_equal", "high_to_lor_owner_route", "lor_to_high_owner_route", "orientation_consistent", "slave_master_complete"):
        if route.get(key) is not True:
            errors.append(f"route audit fact is not closed: {key}")
    if route.get("phase_application") != "finalized_floquet_mpc_once":
        errors.append("route phase-once fact mismatch")

    if loaded:
        try:
            if loaded["source_before"][0] != "primal" or loaded["e_output"][0] != "primal":
                errors.append("primal role metadata mismatch")
            for name in ("high_rhs", "e_input_before", "e_final_action", "e_final_true_residual"):
                if loaded[name][0] != "dual":
                    errors.append(f"dual role metadata mismatch: {name}")
            source_before = loaded["source_before"][2]
            source_after = _align(*loaded["source_before"][1:], *loaded["source_after"][1:], "source")[1]
            rhs = loaded["high_rhs"][2]
            rhs_repeat = _align(*loaded["high_rhs"][1:], *loaded["high_rhs_repeat"][1:], "rhs repeat")[1]
            input_before = loaded["e_input_before"][2]
            input_after = _align(*loaded["e_input_before"][1:], *loaded["e_input_after"][1:], "input")[1]
            output = loaded["e_output"][2]
            repeat = _align(*loaded["e_output"][1:], *loaded["e_repeat"][1:], "repeat")[1]
            final_action = loaded["e_final_action"][2]
            final_residual = _align(*loaded["e_final_action"][1:], *loaded["e_final_true_residual"][1:], "final residual")[1]
            final_rhs = _align(*loaded["e_final_action"][1:], *loaded["high_rhs"][1:], "final RHS")[1]
            recomputed_true = final_rhs - final_action
            residual_identity = float(
                np.linalg.norm(final_residual - recomputed_true)
                / max(np.linalg.norm(final_rhs), np.finfo(float).tiny)
            )
            rho = float(np.linalg.norm(final_residual) / max(np.linalg.norm(final_rhs), np.finfo(float).tiny))
            source_unchanged = _relative(source_after, source_before)
            rhs_repeat_relative = _relative(rhs_repeat, rhs)
            input_unchanged = _relative(input_after, input_before)
            repeat_relative = _relative(repeat, output)
            for name, value, limit in (
                ("source unchanged", source_unchanged, INPUT_LIMIT),
                ("RHS repeat", rhs_repeat_relative, REPEAT_LIMIT),
                ("PC input unchanged", input_unchanged, INPUT_LIMIT),
                ("PC repeat", repeat_relative, REPEAT_LIMIT),
            ):
                if not np.isfinite(value) or value > limit:
                    gates.append(f"{name} {value} > {limit}")
            if not np.isfinite(residual_identity) or residual_identity > INPUT_LIMIT:
                gates.append(f"final residual identity {residual_identity} > {INPUT_LIMIT}")
            if not np.isfinite(rho) or rho > RESIDUAL_LIMIT:
                gates.append(f"final explicit rho {rho} > {RESIDUAL_LIMIT}")
            stored_outer_residual = float(record.get("outer", {}).get("final_true_residual", np.nan))
            if not np.isclose(rho, stored_outer_residual, rtol=1.0e-12, atol=1.0e-15):
                errors.append("raw final rho does not match outer final_true_residual")
            cycles_for_rho = record.get("cycles", [])
            if isinstance(cycles_for_rho, list) and cycles_for_rho:
                last_cycle_residual = float(cycles_for_rho[-1].get("explicit_true_residual", np.nan))
                if not np.isclose(rho, last_cycle_residual, rtol=1.0e-12, atol=1.0e-15):
                    errors.append("raw final rho does not match last cycle residual")
            single_apply = record.get("single_apply", {})
            if single_apply.get("direct_finite") is not True:
                gates.append("single-apply direct solve is not finite")
            if float(single_apply.get("direct_residual_relative", np.inf)) > DIRECT_LIMIT:
                gates.append("stored single-apply direct residual exceeds limit")
            if float(single_apply.get("repeat_relative", np.inf)) > REPEAT_LIMIT:
                gates.append("stored single-apply repeat exceeds limit")
            if float(single_apply.get("input_unchanged_relative", np.inf)) > INPUT_LIMIT:
                gates.append("stored single-apply input changed")
            constraint_vectors = {
                "e_output_constraint": "e_output",
                "e_repeat_constraint": "e_repeat",
                "e_final_constraint": "e_final_solution",
            }
            constraint_relatives: dict[str, float] = {}
            for name, vector_name in constraint_vectors.items():
                values = loaded[name][2]
                denominator = max(float(np.linalg.norm(loaded[vector_name][2])), np.finfo(float).tiny)
                constraint_relative = float(np.max(np.abs(values), initial=0.0)) / denominator
                constraint_relatives[name] = constraint_relative
                if not np.isfinite(constraint_relative) or constraint_relative > PRIMAL_LIMIT:
                    gates.append(f"{name} relative {constraint_relative} > {PRIMAL_LIMIT}")
            if not np.isclose(float(single_apply.get("primal_constraint_relative", np.nan)), constraint_relatives["e_output_constraint"], rtol=1.0e-12, atol=1.0e-15):
                errors.append("stored single-apply primal constraint does not match e_output raw norm")
            pc_legality = record.get("pc_legality", {})
            for key, expected_value in (
                ("reference_repeat_relative", repeat_relative),
                ("reference_input_unchanged_relative", input_unchanged),
                ("reference_primal_constraint_relative", constraint_relatives["e_output_constraint"]),
            ):
                if not np.isclose(float(pc_legality.get(key, np.nan)), expected_value, rtol=1.0e-12, atol=1.0e-15):
                    errors.append(f"stored PC legality {key} does not match raw")
        except (KeyError, ValueError) as exc:
            errors.append(f"canonical identity recomputation failed: {exc}")

    matrix = record.get("matrix_artifacts", {})
    try:
        edge = matrix["edge"]
        indptr = _load_array(raw_dir, edge["indptr"]).astype(np.int64)
        indices = _load_array(raw_dir, edge["indices"]).astype(np.int64)
        values = _load_array(raw_dir, edge["values"]).astype(np.complex128)
        row_keys = _load_array(raw_dir, edge["row_keys"]).astype(str)
        low_input = _load_role(raw_dir, "e_low_input_matrix", matrix["e_low_input_matrix"])
        low_solution = _load_role(raw_dir, "e_low_solution_matrix", matrix["e_low_solution_matrix"])
        if row_keys.size != int(edge["rows"]) or indptr.size != row_keys.size + 1:
            raise ValueError("edge CSR row layout mismatch")
        edge_rows = int(edge["rows"])
        fixture_audit = record.get("fixture_audit", {})
        full_edge_rows = fixture_audit.get("lor_full_edge_rows")
        slave_rows = fixture_audit.get("lor_edge_slave_rows")
        owner_count = record.get("route_audit", {}).get("owner_count")
        if full_edge_rows != edge_rows:
            errors.append("fixture full LOR edge rows do not match edge CSR rows")
        if not isinstance(slave_rows, int) or slave_rows < 0:
            errors.append("fixture LOR edge slave row count is invalid")
        elif not isinstance(owner_count, int) or owner_count < 0 or owner_count + slave_rows != edge_rows:
            errors.append("owner and fixture slave row counts do not close with edge CSR rows")
        x = _align(row_keys, np.zeros(row_keys.size, dtype=np.complex128), *low_solution[1:], "edge solution")[1]
        b = _align(row_keys, np.zeros(row_keys.size, dtype=np.complex128), *low_input[1:], "edge input")[1]
        action = np.zeros(row_keys.size, dtype=np.complex128)
        for row in range(row_keys.size):
            action[row] = np.dot(values[indptr[row] : indptr[row + 1]], x[indices[indptr[row] : indptr[row + 1]]])
        direct_relative = float(np.linalg.norm(action - b) / max(np.linalg.norm(b), np.finfo(float).tiny))
        if not np.isfinite(direct_relative) or direct_relative > DIRECT_LIMIT:
            gates.append(f"exact edge direct residual {direct_relative} > {DIRECT_LIMIT}")
        stored_direct = float(record.get("single_apply", {}).get("direct_residual_relative", np.inf))
        if not np.isclose(stored_direct, direct_relative, rtol=1.0e-12, atol=1.0e-15):
            errors.append("stored single-apply direct residual does not match raw edge CSR")
    except (KeyError, OSError, ValueError, IndexError) as exc:
        errors.append(f"edge direct artifact invalid: {exc}")

    cycles = record.get("cycles")
    outer = record.get("outer", {})
    if not isinstance(cycles, list) or not cycles:
        errors.append("cycle ledger is missing")
    else:
        previous = 0
        for cycle in cycles:
            start = int(cycle.get("start_iteration", -1))
            end = int(cycle.get("end_iteration", -1))
            iterations = int(cycle.get("iterations", -1))
            residual = float(cycle.get("explicit_true_residual", np.nan))
            if start != previous or end != start + iterations or iterations <= 0 or iterations > RESTART:
                errors.append("cycle iteration ledger is not continuous")
            if cycle.get("ksp_destroyed") is not True:
                errors.append(f"cycle {end} KSP was not destroyed")
            if not np.isfinite(residual) or residual < 0.0:
                errors.append(f"cycle {end} residual invalid")
            previous = end
        if previous != int(outer.get("iterations", -1)):
            errors.append("cycle/final iteration mismatch")
        if float(cycles[-1].get("explicit_true_residual", np.nan)) != float(outer.get("final_true_residual", np.nan)):
            errors.append("cycle/final residual mismatch")
    reached = int(outer.get("iterations", -1))
    if reached < 0 or reached > MAX_IT or reached % RESTART != 0:
        errors.append("outer iteration count is outside the fixed cap")
    if not np.isfinite(float(outer.get("final_true_residual", np.nan))):
        errors.append("outer final residual is non-finite")
    if isinstance(cycles, list):
        if int(outer.get("ksp_destroy_count", -1)) != len(cycles):
            errors.append("KSP destroy count does not equal cycle count")
        if int(outer.get("matvec_count", -1)) < 0 or int(outer.get("pc_apply_count", -1)) < 0:
            errors.append("outer operation counts are invalid")
        if int(outer.get("matvec_count", -1)) != sum(int(cycle.get("matvec_count", -1)) for cycle in cycles):
            errors.append("outer matvec count does not equal cycle sum")
        if int(outer.get("pc_apply_count", -1)) != sum(int(cycle.get("pc_apply_count", -1)) for cycle in cycles):
            errors.append("outer PC count does not equal cycle sum")
        if int(outer.get("explicit_action_count", -1)) != 1 + len(cycles):
            errors.append("outer explicit residual-action count does not close from initial action plus cycles")
        if int(outer.get("total_high_action_count", -1)) != int(outer.get("matvec_count", -1)) + int(outer.get("explicit_action_count", -1)):
            errors.append("outer total high-action count does not close")
        _check_boundary_facts(cycles, record.get("boundary_facts"), reached, errors, gates)
    checkpoint_facts = record.get("checkpoint_facts")
    if not isinstance(checkpoint_facts, list):
        errors.append("checkpoint facts are missing")
    else:
        checkpoint_iterations = [int(item.get("iteration", -1)) for item in checkpoint_facts]
        expected_iterations = list(range(CHECKPOINT_INTERVAL, reached + 1, CHECKPOINT_INTERVAL))
        if checkpoint_iterations != expected_iterations:
            errors.append("checkpoint cadence does not match reached 500-step boundaries")
        for fact in checkpoint_facts:
            _check_checkpoint(raw_dir, fact, record, errors)
            if isinstance(cycles, list):
                matching_cycles = [cycle for cycle in cycles if int(cycle.get("end_iteration", -1)) == int(fact.get("iteration", -1))]
                if len(matching_cycles) != 1:
                    errors.append(f"checkpoint {fact.get('iteration')} has no unique cycle boundary")
                elif not np.isclose(
                    float(fact.get("explicit_true_residual", np.nan)),
                    float(matching_cycles[0].get("explicit_true_residual", np.nan)),
                    rtol=1.0e-12,
                    atol=1.0e-15,
                ):
                    errors.append(f"checkpoint {fact.get('iteration')} residual does not match its cycle")

    pc = record.get("pc_legality", {})
    if pc.get("finite") is not True:
        gates.append("production PC output is not finite")
    if float(pc.get("max_input_unchanged_relative", np.inf)) > INPUT_LIMIT:
        gates.append("production PC input changed")
    if float(pc.get("max_primal_constraint_relative", np.inf)) > PRIMAL_LIMIT:
        gates.append("production PC primal constraint failed")
    if int(pc.get("apply_count", -1)) != int(outer.get("pc_apply_count", -2)):
        errors.append("production PC apply count does not close with outer ledger")
    direct_factor_total = int(pc.get("direct_factor_solve_count_total", -1))
    expected_direct_factor_total = 2 + int(outer.get("pc_apply_count", -1))
    if direct_factor_total != expected_direct_factor_total:
        errors.append("direct factor solve total does not equal two reference solves plus outer PC applies")
    rank_facts = record.get("rank_facts")
    if not isinstance(rank_facts, list) or len(rank_facts) != 1:
        errors.append("MPI1 rank facts are missing or not singleton")
    else:
        rank_fact = rank_facts[0]
        if int(rank_fact.get("rank", -1)) != 0:
            errors.append("MPI1 rank fact has wrong rank")
        if int(rank_fact.get("direct_factor_solve_count", -1)) != direct_factor_total:
            errors.append("rank direct factor solve count does not match total")
        if int(rank_fact.get("outer_iterations", -1)) != int(outer.get("iterations", -2)):
            errors.append("rank outer iteration count mismatch")
        if int(rank_fact.get("outer_matvec_count", -1)) != int(outer.get("matvec_count", -2)):
            errors.append("rank outer matvec count mismatch")
        if int(rank_fact.get("outer_pc_apply_count", -1)) != int(outer.get("pc_apply_count", -2)):
            errors.append("rank outer PC count mismatch")
        rank_runtime = rank_fact.get("runtime")
        if rank_runtime != record.get("runtime"):
            errors.append("rank runtime identity mismatch")
        rank_pc = rank_fact.get("pc_legality")
        if not isinstance(rank_pc, dict) or any(
            rank_pc.get(key) != pc.get(key)
            for key in ("apply_count", "finite", "max_input_unchanged_relative", "max_primal_constraint_relative")
        ):
            errors.append("rank PC legality facts mismatch")
    forbidden = record.get("production_forbidden", {})
    fixture_audit = record.get("fixture_audit", {})
    hx_audit = fixture_audit.get("hx_audit", {}) if isinstance(fixture_audit, dict) else {}
    derived_forbidden = {
        "high_order_global_aij": bool(fixture_audit.get("high_order_global_aij", False) or hx_audit.get("high_order_global_aij", hx_audit.get("high_order_aij", False))),
        "global_dense_transfer": bool(fixture_audit.get("global_transfer_matrix", False) or hx_audit.get("global_transfer_matrix", False)),
        "global_direct_coarse": bool(fixture_audit.get("global_direct_coarse", False) or hx_audit.get("global_direct_coarse", False)),
        "global_numeric_allgather": bool(fixture_audit.get("global_numeric_allgather", False) or hx_audit.get("global_numeric_allgather", False)),
    }
    for key, value in derived_forbidden.items():
        if forbidden.get(key) != value:
            errors.append(f"forbidden audit is not bound to fixture audit: {key}")
        if value:
            errors.append(f"forbidden production path was enabled: {key}")

    result = {
        "schema": "task038.lor-native-complex-hx.foundation-e-check.v1",
        "record": str(record_path),
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "metrics": {
            "iterations": int(outer.get("iterations", -1)),
            "final_true_residual": float(outer.get("final_true_residual", np.nan)),
            "checkpoint_count": len(checkpoint_facts) if isinstance(checkpoint_facts, list) else 0,
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args(argv)
    result = check_record(args.record, args.watchdog_compact, args.expected_source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json.dumps(result, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
