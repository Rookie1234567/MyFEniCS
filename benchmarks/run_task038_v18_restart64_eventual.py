"""Thin E1/E2 orchestration for the V18 eventual-correctness lane.

The fixed-restart numerical work remains in
``fullspace_memory_first_krylov.run_fixed_restart_cycles``.  This module only
binds the immutable V18 checkpoint, cold-cache parent/worker lifecycle, the
4096-step stagnation stop, and the E1/E2 gate ordering.  E3 is represented by
the pure unlock facts; official recovery is intentionally not implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from benchmarks import run_task038_full3d_physical_pcoarse_q1 as authority_runner
from benchmarks import run_task038_v17_oracles as v17
from benchmarks import run_task038_v18_restart64 as v18


BRANCH = authority_runner.BRANCH
MODULE = "benchmarks.run_task038_v18_restart64_eventual"
WORKFLOW = "task038-v18-restart64-eventual-physical"
PHASES = ("e1", "e2")
JIT_GROUPS = tuple(authority_runner.JIT_GROUPS)

RESTART = 64
ABSOLUTE_ORIGIN = 1000
E1_BASE_OFFSET = 1024
E1_MAX_TOTAL_ADDITIONAL = 32768
E1_MAX_STEPS = E1_MAX_TOTAL_ADDITIONAL - E1_BASE_OFFSET
E2_MAX_STEPS = E1_MAX_TOTAL_ADDITIONAL
CHECKPOINT_INTERVAL = 1024
STAGNATION_BLOCK_SIZE = 4096
STAGNATION_RATIO_LIMIT = 0.95
RESIDUAL_LIMIT = 1.0e-6
DIVERGED_ITS = -3

RSS_WARNING = 1_800_000_000
RSS_HARD = 2_000_000_000
RSS_WATCHDOG = RSS_HARD
SWAP_HARD = 0

INPUT_SHA256 = v17.INPUT_SHA256
PHYSICAL_MODEL_SHA256 = v17.PHYSICAL_MODEL_SHA256
MODE_MANIFEST_SHA256 = v17.MODE_MANIFEST_SHA256
CHECKPOINT_INPUT_IDENTITY_SHA256 = v17.CHECKPOINT_INPUT_IDENTITY_SHA256
CHECKPOINT_OPERATOR_IDENTITY_SHA256 = v17.CHECKPOINT_OPERATOR_IDENTITY_SHA256
CHECKPOINT_SOLUTION_SHA256 = (
    "5ab1ec46b588e1a1c38945ceaf5d41b61f066785ff08ccdd493735a01b45ee79"
)
CHECKPOINT_MANIFEST_SHA256 = (
    "267a933e1f85cd8685efcfc14a2fc8a50b352d6573a19e9781655c19d3f0be31"
)
CHECKPOINT_SOURCE_SHA = "a20008734c8bf0df03890bf35576c697eb0967f0"
CHECKPOINT_EXPLICIT_RESIDUAL = 0.27299642739429014
CHECKPOINT_DIR = (
    authority_runner.REPO_ROOT
    / "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm"
    / "v18_restart64_physical_v1"
    / "a20008734c8bf0df03890bf35576c697eb0967f0"
    / "mpi1/raw/screen/solution_checkpoints/solution-2024"
)

MARKER_SCHEMA = "task038.v18.restart64.eventual.marker.v1"
PARENT_SCHEMA = "task038.v18.restart64.eventual.parent.v1"
WORKER_SCHEMA = "task038.v18.restart64.eventual.worker.v1"
CHECKER_SCHEMA = "task038.v18.restart64.eventual.checker.v1"
COMPLETION_SCHEMA = "task038.v18.restart64.eventual.completion.v1"
CHECKER_MODULE = "benchmarks.task038_v18_restart64_eventual_checker"
E1_PASS_CLASSIFICATION = "E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS"
MARKER_ORDER = {
    "e1": (
        "paths_ready",
        "abi_ready",
        "case_built",
        "checkpoint_restored",
        "e1_complete",
        "record_written",
        "release_complete",
    ),
    "e2": (
        "paths_ready",
        "abi_ready",
        "case_built",
        "e2_complete",
        "record_written",
        "release_complete",
    ),
}

REPO_ROOT = authority_runner.REPO_ROOT
LEXICAL_PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")
CHECKPOINT_RELATIVE = str(CHECKPOINT_DIR.relative_to(REPO_ROOT))


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _write_json(path: Path, value: Any) -> None:
    v18._write_json(path, value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _array_sha(values: Any) -> str:
    return v18._array_sha(values)


def _vec_relative(left: Any, right: Any) -> float:
    return v18._vec_relative(left, right)


def _source_facts(source_sha: str, input_path: Path) -> dict[str, Any]:
    return {
        **v18._source_facts(source_sha, input_path),
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
    }


def _checkpoint_preflight() -> dict[str, Any]:
    """Read and bind the immutable E0 checkpoint before any JIT or case build."""

    import numpy as np

    manifest_path = CHECKPOINT_DIR / "manifest.json"
    facts: dict[str, Any] = {
        "relative_path": CHECKPOINT_RELATIVE,
        "manifest_relative_path": str(manifest_path.relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else None,
        "solution_relative_path": None,
        "solution_sha256": None,
        "solution_bytes": None,
        "dtype": None,
        "shape": None,
        "finite": False,
        "ownership": None,
        "valid": False,
        "errors": [],
    }
    errors = facts["errors"]
    if not manifest_path.is_file():
        errors.append("manifest missing")
        return facts
    if facts["manifest_sha256"] != CHECKPOINT_MANIFEST_SHA256:
        errors.append("manifest SHA mismatch")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        errors.append(f"manifest unreadable: {exc}")
        return facts
    expected = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 2024,
        "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
    }
    if not isinstance(manifest, dict):
        errors.append("manifest is not an object")
        return facts
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} mismatch")
    ranks = manifest.get("ranks")
    rank = ranks[0] if isinstance(ranks, list) and len(ranks) == 1 else None
    descriptor = rank.get("solution") if isinstance(rank, dict) else None
    ownership = rank.get("ownership") if isinstance(rank, dict) else None
    facts["ownership"] = ownership
    expected_ownership = {
        "rank": 0,
        "ownership_range": [0, 173802],
        "local_size": 173802,
        "global_size": 173802,
    }
    if ownership != expected_ownership:
        errors.append("ownership mismatch")
    relative = descriptor.get("relative_path") if isinstance(descriptor, dict) else None
    facts["solution_relative_path"] = relative
    if not isinstance(relative, str):
        errors.append("solution descriptor missing")
        return facts
    solution_path = (CHECKPOINT_DIR / relative).resolve()
    try:
        solution_path.relative_to(CHECKPOINT_DIR.resolve())
    except ValueError:
        errors.append("solution path escapes checkpoint")
        return facts
    if not solution_path.is_file():
        errors.append("solution shard missing")
        return facts
    facts["solution_sha256"] = _sha256(solution_path)
    facts["solution_bytes"] = int(solution_path.stat().st_size)
    if facts["solution_sha256"] != CHECKPOINT_SOLUTION_SHA256:
        errors.append("solution SHA mismatch")
    if not isinstance(descriptor, dict):
        errors.append("solution descriptor missing")
        return facts
    if descriptor.get("bytes") != facts["solution_bytes"] or descriptor.get("sha256") != facts["solution_sha256"]:
        errors.append("solution descriptor hash or bytes mismatch")
    try:
        values = np.asarray(np.load(solution_path, allow_pickle=False))
    except (OSError, TypeError, ValueError) as exc:
        errors.append(f"solution unreadable: {exc}")
        return facts
    facts["dtype"] = str(values.dtype)
    facts["shape"] = list(values.shape)
    facts["finite"] = bool(np.all(np.isfinite(values)))
    if values.dtype != np.dtype(np.complex128) or values.ndim != 1 or values.shape != (173802,):
        errors.append("solution dtype or shape mismatch")
    if descriptor.get("dtype") != "complex128" or descriptor.get("shape") != [173802]:
        errors.append("solution descriptor dtype or shape mismatch")
    if not facts["finite"]:
        errors.append("solution is nonfinite")
    facts["valid"] = not errors
    return facts


def checkpoint_expected() -> dict[str, Any]:
    """Return the exact immutable V18 solution-2024 manifest contract."""

    return {
        "iteration": 2024,
        "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
    }


def iteration_identity(local_iteration: int, base_offset: int) -> dict[str, int]:
    """Map a solver-local counter to the original additional/absolute counters."""

    local_iteration = int(local_iteration)
    base_offset = int(base_offset)
    if local_iteration < 0 or base_offset < 0:
        raise ValueError("iteration counters must be non-negative")
    additional = base_offset + local_iteration
    return {
        "local_iteration": local_iteration,
        "additional_iteration": additional,
        "absolute_iteration": ABSOLUTE_ORIGIN + additional,
    }


def _marker(comm: Any, marker_dir: Path, phase: str, name: str, source_sha: str, **facts: Any) -> None:
    if int(comm.rank) == 0:
        authority_runner.write_marker(
            marker_dir,
            name,
            {
                "phase": phase,
                "workflow": WORKFLOW,
                "source_sha": source_sha,
                "mpi_size": int(comm.size),
                **facts,
            },
            order=MARKER_ORDER[phase],
            schema=MARKER_SCHEMA,
        )
    comm.barrier()


def _worker_command(root: Path, record: Path, source_sha: str, input_path: Path, phase: str) -> list[str]:
    return [
        "mpiexec",
        "-n",
        "1",
        LEXICAL_PYTHON,
        "-m",
        MODULE,
        "--phase",
        phase,
        "--mode",
        "worker",
        "--artifact-root",
        str(root),
        "--record",
        str(record),
        "--source-sha",
        source_sha,
        "--input",
        str(input_path),
        "--mpi-size",
        "1",
    ]


def _jit_child_command(group: str, cache: Path, record: Path, source_sha: str, input_path: Path) -> list[str]:
    return v18._jit_child_command(group, cache, record, source_sha, input_path)


def _stage_result(root: Path, result: dict[str, Any], record_path: Path, stage: str) -> dict[str, Any]:
    return {
        **result,
        "stage": stage,
        "record": str(record_path.relative_to(root)),
        "record_sha256": _sha256(record_path) if record_path.is_file() else None,
    }


def _marker_manifest(root: Path, phase: str) -> tuple[Path | None, list[dict[str, Any]]]:
    marker_dir = root / "markers"
    if not marker_dir.is_dir():
        return None, []
    rows = []
    for path in authority_runner.marker_files(marker_dir, order=MARKER_ORDER[phase]):
        rows.append(
            {
                "name": path.stem.split("_", 1)[1],
                "relative_path": str(path.relative_to(root)),
                "sha256": _sha256(path),
            }
        )
    if not rows:
        return None, rows
    manifest_path = root / "marker_manifest.json"
    if not manifest_path.exists():
        _write_json(manifest_path, rows)
    return manifest_path, rows


def _checkpoint_writer(
    root: Path,
    raw_dir: Path,
    stage: str,
    base_offset: int,
    vector: Any,
    comm: Any,
    source_sha: str,
    local_iteration: int,
    explicit_true_residual: float,
) -> dict[str, Any]:
    from src.solvers.fullspace_memory_first_krylov import write_solution_checkpoint

    identity = iteration_identity(local_iteration, base_offset)
    checkpoint_dir = (
        raw_dir / stage / "solution_checkpoints"
        / f"solution-{identity['absolute_iteration']}"
    )
    checkpoint_dir.parent.mkdir(parents=True, exist_ok=True)
    facts = dict(
        write_solution_checkpoint(
            checkpoint_dir,
            vector,
            iteration=identity["absolute_iteration"],
            explicit_true_residual=explicit_true_residual,
            input_identity_sha256=CHECKPOINT_INPUT_IDENTITY_SHA256,
            operator_identity_sha256=CHECKPOINT_OPERATOR_IDENTITY_SHA256,
            physical_model_sha256=PHYSICAL_MODEL_SHA256,
            source_sha=source_sha,
            ownership=v17._ownership(vector, comm),
            comm=comm,
        )
    )
    manifest_path = Path(str(facts.pop("manifest_path")))
    facts.update(
        {
            "relative_path": str(checkpoint_dir.relative_to(root)),
            "manifest_relative_path": str(manifest_path.relative_to(root)),
            **identity,
        }
    )
    return facts


def _stage_cycles(
    raw_dir: Path,
    phase: str,
    stage: str,
    base_offset: int,
    max_steps: int,
    initial: Any,
    rhs: Any,
    action: Any,
    pc: Any,
    comm: Any,
    source_sha: str,
    initial_true_residual: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from src.solvers.fullspace_memory_first_krylov import run_fixed_restart_cycles

    checkpoint_facts: list[dict[str, Any]] = []

    def observer(_iteration: int, _solution: Any, cycle: dict[str, Any]) -> None:
        cycle.update(iteration_identity(cycle["end_iteration"], base_offset))

    def checkpoint_writer(local_iteration: int, solution: Any, residual: float) -> dict[str, Any]:
        facts = _checkpoint_writer(
            raw_dir.parent,
            raw_dir,
            stage,
            base_offset,
            solution,
            comm,
            source_sha,
            local_iteration,
            residual,
        )
        checkpoint_facts.append(facts)
        return facts

    def stop_after_cycle(_cycle: Any, cycles: Any) -> bool:
        facts = _stagnation_facts(initial_true_residual, cycles, base_offset)
        return bool(facts["triggered"])

    result = run_fixed_restart_cycles(
        rhs,
        action,
        pc,
        max_it=max_steps,
        residual_limit=RESIDUAL_LIMIT,
        resource_sample=v17._solver_resource_sample,
        initial_solution=initial,
        start_iteration=0,
        checkpoint_writer=checkpoint_writer,
        first_checkpoint_iteration=None,
        checkpoint_interval=CHECKPOINT_INTERVAL,
        cycle_observer=observer,
        stop_on_true_residual=True,
        ksp_type="fgmres",
        restart=RESTART,
        cycle_max_it=RESTART,
        stop_after_cycle=stop_after_cycle,
    )
    facts = {
        "stage": stage,
        "phase": phase,
        "base_offset": int(base_offset),
        "local_iterations": int(result["iterations"]),
        "additional_iterations": int(base_offset) + int(result["iterations"]),
        "absolute_end_iteration": ABSOLUTE_ORIGIN + int(base_offset) + int(result["iterations"]),
        "initial_true_residual": float(initial_true_residual),
        "final_true_residual": float(result["final_true_residual"]),
        "matvec_count": int(result["matvec_count"]),
        "pc_apply_count": int(result["pc_apply_count"]),
        "explicit_action_count": int(result["explicit_action_count"]),
        "ksp_destroy_count": int(result["ksp_destroy_count"]),
        "elapsed_seconds": float(result["elapsed_seconds"]),
        "settings": {
            **result["settings"],
            "restart": RESTART,
            "cycle_max_it": RESTART,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "additional_iteration_origin": 0,
            "absolute_iteration_origin": ABSOLUTE_ORIGIN,
            "stage_base_offset": int(base_offset),
        },
        "cycles": [dict(cycle) for cycle in result["cycles"]],
        "checkpoint_facts": checkpoint_facts,
    }
    facts["stagnation"] = _stagnation_facts(
        initial_true_residual, facts["cycles"], base_offset
    )
    return result, facts


def _stagnation_facts(
    initial_true_residual: float,
    cycles: Any,
    base_offset: int,
) -> dict[str, Any]:
    """Return local block facts plus the E1/E2 evidence coordinates."""

    from src.solvers.fullspace_memory_first_krylov import restart_stagnation_facts

    facts = restart_stagnation_facts(
        float(initial_true_residual),
        cycles,
        block_size=STAGNATION_BLOCK_SIZE,
        ratio_limit=STAGNATION_RATIO_LIMIT,
    )
    mapped_blocks = []
    for block in facts["blocks"]:
        start = iteration_identity(int(block["start_iteration"]), base_offset)
        end = iteration_identity(int(block["end_iteration"]), base_offset)
        mapped_blocks.append(
            {
                **block,
                "start_additional_iteration": start["additional_iteration"],
                "end_additional_iteration": end["additional_iteration"],
                "start_absolute_iteration": start["absolute_iteration"],
                "end_absolute_iteration": end["absolute_iteration"],
            }
        )
    return {
        **facts,
        "base_offset": int(base_offset),
        "absolute_origin": ABSOLUTE_ORIGIN,
        "blocks": mapped_blocks,
    }


def _probe_action_and_pc(bundle: Any, setup: Any, p6_matrix: Any, initial: Any, rhs: Any, p6_mpc: Any, comm: Any, raw_dir: Path) -> tuple[dict[str, Any], dict[str, Any], Any]:
    import numpy as np

    action_first = p6_matrix.createVecLeft()
    action_second = p6_matrix.createVecLeft()
    pc_input = None
    pc_first = pc_second = None
    try:
        input_before = _array_sha(initial.array)
        bundle["physical_action"].apply(initial, action_first)
        bundle["physical_action"].apply(initial, action_second)
        action_first_descriptor = v17._write_array(raw_dir, "probes/action_first.npy", action_first.array)
        action_second_descriptor = v17._write_array(raw_dir, "probes/action_second.npy", action_second.array)
        action_facts = v17._owned_vector_facts(action_first, p6_mpc, comm)
        action_probe = {
            "input_before_sha256": input_before,
            "input_after_sha256": _array_sha(initial.array),
            "repeat_relative": _vec_relative(action_first, action_second),
            "first": action_first_descriptor,
            "second": action_second_descriptor,
            "dual_facts": action_facts,
        }

        pc_input = rhs.copy()
        pc_input.axpy(-1.0, action_first)
        pc_input_before = _array_sha(pc_input.array)
        pc_first = setup["upper_cycle"].apply(pc_input)
        pc_second = setup["upper_cycle"].apply(pc_input)
        pc_first_descriptor = v17._write_array(raw_dir, "probes/pc_first.npy", pc_first.array)
        pc_second_descriptor = v17._write_array(raw_dir, "probes/pc_second.npy", pc_second.array)
        pc_probe = {
            "input_role": "dual_residual",
            "input_before_sha256": pc_input_before,
            "input_after_sha256": _array_sha(pc_input.array),
            "repeat_relative": _vec_relative(pc_first, pc_second),
            "input_facts": v17._owned_vector_facts(pc_input, p6_mpc, comm),
            "first": pc_first_descriptor,
            "second": pc_second_descriptor,
            "primal_facts": v17._owned_vector_facts(pc_first, p6_mpc, comm),
        }
        return action_probe, pc_probe, pc_input
    finally:
        action_first.destroy()
        action_second.destroy()
        if pc_first is not None:
            pc_first.destroy()
        if pc_second is not None:
            pc_second.destroy()


def _stage_classification(stage: dict[str, Any] | None, gate_failures: list[str], phase: str) -> str:
    if gate_failures:
        return f"{phase.upper()}_NUMERICAL_GATE_FAIL"
    if stage is None:
        return f"{phase.upper()}_NOT_RUN"
    cycles = stage.get("cycles")
    last_reason = cycles[-1].get("reason") if isinstance(cycles, list) and cycles else None
    if isinstance(last_reason, int) and last_reason < 0 and last_reason != DIVERGED_ITS:
        return f"{phase.upper()}_PHYSICAL_BREAKDOWN"
    if float(stage["final_true_residual"]) <= RESIDUAL_LIMIT:
        return (
            "E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS"
            if phase == "e1"
            else "E2_FRESH_PHYSICAL_NUMERICAL_PASS"
        )
    if stage["stagnation"]["triggered"]:
        return "E1_PHYSICAL_STAGNATION" if phase == "e1" else "E2_FRESH_PHYSICAL_STAGNATION"
    if int(stage["local_iterations"]) >= (E1_MAX_STEPS if phase == "e1" else E2_MAX_STEPS):
        return "E1_PHYSICAL_MAXIT_FAIL" if phase == "e1" else "E2_FRESH_PHYSICAL_MAXIT_FAIL"
    return f"{phase.upper()}_PHYSICAL_BREAKDOWN"


def stage_unlocks(e1_classification: str, e2_classification: str | None = None) -> dict[str, bool]:
    e1_pass = e1_classification == "E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS"
    e2_pass = e2_classification == "E2_FRESH_PHYSICAL_NUMERICAL_PASS"
    return {"e2": e1_pass, "e3": e1_pass and e2_pass}


def _checker_command(record: Path, output: Path, source_sha: str) -> list[str]:
    return [
        LEXICAL_PYTHON,
        "-m",
        CHECKER_MODULE,
        "--record",
        str(record),
        "--expected-source-sha",
        source_sha,
        "--output",
        str(output),
    ]


def _e1_checker_authority(checker_path: Path, expected_source_sha: str) -> bool:
    """Accept only an independent, hash-bound E1 checker result."""

    try:
        checker = json.loads(checker_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    if (
        checker.get("schema") != CHECKER_SCHEMA
        or checker.get("status") != "PASS"
        or checker.get("evidence_valid") is not True
        or checker.get("classification") != E1_PASS_CLASSIFICATION
        or checker.get("errors") != []
        or checker.get("expected_source_sha") != expected_source_sha
    ):
        return False
    record_value = checker.get("record")
    if not isinstance(record_value, str):
        return False
    record_path = _absolute(record_value)
    if not record_path.is_file() or checker.get("record_sha256") != _sha256(record_path):
        return False
    try:
        parent = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    source = parent.get("source") if isinstance(parent, dict) else None
    if (
        parent.get("schema") != PARENT_SCHEMA
        or parent.get("workflow") != WORKFLOW
        or parent.get("phase") != "e1"
        or parent.get("classification") != "RAW_COMPLETE_PENDING_CHECKER"
        or not isinstance(source, dict)
        or source.get("commit_sha") != expected_source_sha
        or source.get("upstream_sha") != expected_source_sha
        or source.get("branch") != BRANCH
        or source.get("upstream") != f"origin/{BRANCH}"
        or source.get("ahead") != 0
        or source.get("behind") != 0
        or source.get("tracked_worktree_clean") is not True
    ):
        return False
    paths = parent.get("paths")
    completion_value = paths.get("completion") if isinstance(paths, dict) else None
    if not isinstance(completion_value, str):
        return False
    completion_path = (record_path.parent / completion_value).resolve()
    if not completion_path.is_file():
        return False
    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    checker_sha = _sha256(checker_path)
    checker_process = completion.get("checker_process")
    return bool(
        completion.get("schema") == COMPLETION_SCHEMA
        and completion.get("parent_record") == record_path.name
        and completion.get("parent_record_sha256") == _sha256(record_path)
        and completion.get("checker") == checker_path.name
        and completion.get("checker_sha256") == checker_sha
        and completion.get("status") == "PASS"
        and isinstance(checker_process, dict)
        and checker_process.get("returncode") == 0
        and checker_process.get("stop_reason") is None
        and checker_process.get("process_group_gone") is True
        and checker_process.get("lifecycle_failure") is False
        and checker_process.get("all_status_readable") is True
        and checker_process.get("max_swap_bytes") == 0
        and isinstance(checker_process.get("peak_rss_bytes"), int)
        and not isinstance(checker_process.get("peak_rss_bytes"), bool)
        and checker_process["peak_rss_bytes"] < RSS_HARD
        and checker_process.get("rss_watchdog_bytes") == RSS_HARD
    )


def _run_worker(
    root: Path,
    raw_dir: Path,
    marker_dir: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    phase: str,
    comm: Any,
) -> None:
    import numpy as np

    from benchmarks.run_task038_full3d_r3 import _current_input
    from src.solvers.fullspace_memory_first_krylov import (
        destroy_krylov_result,
        read_solution_checkpoint,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_p6_same_mesh_physical_bundle,
        build_physical_rhs,
        destroy_p6_same_mesh_physical_bundle,
    )

    _spec, cfg, _resolved, input_facts = _current_input(REPO_ROOT, input_path)
    input_facts = {
        **input_facts,
        "template_sha256": INPUT_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
    }
    bundle = None
    rhs = initial = pc_input = None
    stage_result = None
    stage_facts = None
    record_written = False
    try:
        bundle = build_p6_same_mesh_physical_bundle(cfg, comm)
        setup = bundle["setup"]
        p6_matrix = setup["p6_shell"].matrix
        p6_mpc = setup["floquets"][6].mpc
        _marker(comm, marker_dir, phase, "case_built", source_sha, degree=6, levels=[6, 3, 1], mode_manifest_sha256=bundle["mode_sha256"])

        checkpoint_facts = None
        if phase == "e1":
            initial = p6_matrix.createVecRight()
            checkpoint = read_solution_checkpoint(
                CHECKPOINT_DIR,
                initial,
                expected=checkpoint_expected(),
                ownership=v17._ownership(initial, comm),
                comm=comm,
            )
            checkpoint_facts = {
                **checkpoint,
                **checkpoint_expected(),
                "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
                "relative_path": str(CHECKPOINT_DIR.relative_to(REPO_ROOT)),
            }
            _marker(comm, marker_dir, phase, "checkpoint_restored", source_sha, iteration=2024, manifest_sha256=CHECKPOINT_MANIFEST_SHA256, solution_sha256=CHECKPOINT_SOLUTION_SHA256)
        else:
            initial = p6_matrix.createVecRight()
            initial.set(0.0 + 0.0j)

        rhs, rhs_facts = build_physical_rhs(bundle)
        initial_descriptor = v17._write_array(raw_dir, "same_start/initial_solution.npy", initial.array)
        rhs_descriptor = v17._write_array(raw_dir, "same_start/rhs.npy", rhs.array)
        rhs_facts = {**rhs_facts, **v17._owned_vector_facts(rhs, p6_mpc, comm), "descriptor": rhs_descriptor}
        initial_before = _array_sha(initial.array)
        rhs_before = _array_sha(rhs.array)
        action_probe, pc_probe, pc_input = _probe_action_and_pc(bundle, setup, p6_matrix, initial, rhs, p6_mpc, comm, raw_dir)
        action_values = np.asarray(np.load(raw_dir / "probes/action_first.npy", allow_pickle=False), dtype=np.complex128)
        residual_values = np.asarray(rhs.array, dtype=np.complex128) - action_values
        residual_descriptor = v17._write_array(raw_dir, "restore/residual.npy", residual_values)
        action_descriptor = v17._write_array(raw_dir, "restore/action.npy", action_values)
        restore_actual = float(np.linalg.norm(residual_values)) / max(float(np.linalg.norm(rhs.array)), np.finfo(float).tiny)
        restore_relative = abs(restore_actual - CHECKPOINT_EXPLICIT_RESIDUAL) / max(abs(CHECKPOINT_EXPLICIT_RESIDUAL), np.finfo(float).tiny)
        restore = {
            "expected": CHECKPOINT_EXPLICIT_RESIDUAL if phase == "e1" else None,
            "actual": restore_actual,
            "relative_difference": restore_relative if phase == "e1" else None,
            "relative_limit": 1.0e-11 if phase == "e1" else None,
            "rhs_descriptor": rhs_descriptor,
            "action_descriptor": action_descriptor,
            "residual_descriptor": residual_descriptor,
            "finite": bool(np.all(np.isfinite(residual_values))),
        }
        pre_failures: list[str] = []
        if phase == "e1" and (not np.isfinite(restore_relative) or restore_relative > 1.0e-11):
            pre_failures.append("checkpoint_reproduction")
        for label, probe, facts_key in (("action", action_probe, "dual_facts"), ("pc", pc_probe, "primal_facts")):
            facts = probe[facts_key]
            if facts["finite"] is not True or facts["owned_slave_max"] != 0.0 or facts["owned_slave_count"] != 0:
                pre_failures.append(f"{label}.facts")
            if not np.isfinite(probe["repeat_relative"]) or probe["repeat_relative"] > 1.0e-12:
                pre_failures.append(f"{label}.repeat")
            if probe["input_before_sha256"] != probe["input_after_sha256"]:
                pre_failures.append(f"{label}.input_unchanged")
        pc_input_facts = pc_probe["input_facts"]
        if pc_input_facts["finite"] is not True:
            pre_failures.append("pc.input_finite")
        if pc_probe["input_facts"]["owned_slave_max"] != 0.0 or pc_probe["input_facts"]["owned_slave_count"] != 0:
            pre_failures.append("pc.input_slave")
        if rhs_facts["finite"] is not True:
            pre_failures.append("rhs.finite")
        if not np.all(np.isfinite(initial.array)):
            pre_failures.append("initial_solution.finite")
        input_after = {
            "rhs": _array_sha(rhs.array),
            "initial_solution": _array_sha(initial.array),
        }
        if input_after["rhs"] != rhs_before or input_after["initial_solution"] != initial_before:
            pre_failures.append("same_start.input_unchanged")

        if not pre_failures:
            base_offset = E1_BASE_OFFSET if phase == "e1" else 0
            max_steps = E1_MAX_STEPS if phase == "e1" else E2_MAX_STEPS
            stage_result, stage_facts = _stage_cycles(
                raw_dir,
                phase,
                phase,
                base_offset,
                max_steps,
                initial,
                rhs,
                lambda source: _apply_action(bundle, p6_matrix, source),
                lambda source: setup["upper_cycle"].apply(source),
                comm,
                source_sha,
                restore_actual,
            )

        classification = _stage_classification(stage_facts, pre_failures, phase)
        initial_after = _array_sha(initial.array)
        rhs_after = _array_sha(rhs.array)
        record = {
            "schema": WORKER_SCHEMA,
            "workflow": WORKFLOW,
            "phase": phase,
            "worker_stage": "worker",
            "source": _source_facts(source_sha, input_path),
            "input": input_facts,
            "checkpoint": checkpoint_facts,
            "rhs": rhs_facts,
            "same_start": {
                "rhs": rhs_descriptor,
                "initial_solution": initial_descriptor,
                "rhs_before_sha256": rhs_before,
                "rhs_after_sha256": rhs_after,
                "initial_solution_before_sha256": initial_before,
                "initial_solution_after_sha256": initial_after,
                "input_unchanged": rhs_before == rhs_after and initial_before == initial_after,
                "finite": bool(rhs_facts["finite"] and np.all(np.isfinite(initial.array))),
                "initial_true_residual": float(stage_facts["initial_true_residual"] if stage_facts is not None else restore_actual),
            },
            "probes": {"action": action_probe, "pc": pc_probe},
            "restore": restore,
            "stage": stage_facts,
            "gates": {"pre_stage": pre_failures, "classification": classification},
            "architecture": {
                "physical_operator": "p6_matrix_free_split_volume_plus_streaming_dtn",
                "global_physical_aij": False,
                "global_schur": False,
                "dense_dtn": False,
                "factor": False,
                "numeric_allgather": False,
                "phase_once": True,
                "restart_basis_storage": "petsc_in_memory",
                "restart": RESTART,
            },
            "lifecycle": {"marker_order": list(MARKER_ORDER[phase])},
        }
        _write_json(record_path, record)
        _marker(comm, marker_dir, phase, f"{phase}_complete", source_sha, classification=classification, final_true_residual=stage_facts["final_true_residual"] if stage_facts else None, gate_failures=pre_failures)
        _marker(comm, marker_dir, phase, "record_written", source_sha, classification=classification)
        record_written = True
    finally:
        if stage_result is not None:
            destroy_krylov_result(stage_result)
        if rhs is not None:
            rhs.destroy()
        if pc_input is not None:
            pc_input.destroy()
        if initial is not None:
            initial.destroy()
        if bundle is not None:
            destroy_p6_same_mesh_physical_bundle(bundle)
    if record_written:
        _marker(comm, marker_dir, phase, "release_complete", source_sha)


def _apply_action(bundle: Any, p6_matrix: Any, source: Any) -> Any:
    target = p6_matrix.createVecLeft()
    bundle["physical_action"].apply(source, target)
    return target


def _run_parent(root: Path, record_path: Path, source_sha: str, input_path: Path, phase: str) -> int:
    root, cache = authority_runner._prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("parent record must be directly below the fresh root")
    source = _source_facts(source_sha, input_path)
    cache_initial = authority_runner._cache_snapshot(cache)
    e0_facts: dict[str, Any] | None = None
    e0_path: Path | None = None

    if phase == "e1":
        e0_facts = _checkpoint_preflight()
        e0_path = root / "e0_checkpoint_preflight.json"
        _write_json(e0_path, e0_facts)
        if not e0_facts["valid"]:
            parent_record = {
                "schema": PARENT_SCHEMA,
                "workflow": WORKFLOW,
                "phase": phase,
                "source": source,
                "expected_mpi_size": 1,
                "resource_contract": {
                    "warning_bytes": RSS_WARNING,
                    "rss_watchdog_bytes": RSS_WATCHDOG,
                    "rss_hard_gate_bytes": RSS_HARD,
                    "swap_hard_gate_bytes": SWAP_HARD,
                },
                "paths": {
                    "jit_cache": "jit_cache",
                    "children": "children",
                    "process_samples": None,
                    "marker_manifest": None,
                    "e0_checkpoint_preflight": str(e0_path.relative_to(root)),
                    "e0_checkpoint_preflight_sha256": _sha256(e0_path),
                    "checker_output": None,
                    "completion": None,
                },
                "jit_groups": [],
                "children": [],
                "worker": None,
                "stages": [],
                "cache": {
                    "initial": cache_initial,
                    "before_worker": cache_initial,
                    "after_worker": cache_initial,
                },
                "process": None,
                "markers": {"rows": [], "sha256": None},
                "e0": e0_facts,
                "classification": "E0_BLOCKED_BY_CHECKPOINT_AUTHORITY",
                "error": None,
            }
            _write_json(record_path, parent_record)
            return 0

    children_dir = root / "children"
    children_dir.mkdir(exist_ok=False)
    process_path = root / "parent_process.jsonl"
    children: list[dict[str, Any]] = []
    worker_result: dict[str, Any] | None = None
    error: str | None = None
    cache_before: dict[str, Any] | None = None
    cache_after: dict[str, Any] | None = None
    try:
        for index, group in enumerate(JIT_GROUPS):
            stem = f"{index:02d}_{group.replace('-', '_')}"
            child_record = children_dir / f"{stem}.json"
            result = authority_runner._run_parent_child(
                _jit_child_command(group, cache, child_record, source_sha, _absolute(input_path)),
                process_path,
                f"precompile:{group}",
                children_dir / f"{stem}.stdout.log",
                children_dir / f"{stem}.stderr.log",
                rss_watchdog_bytes=RSS_WATCHDOG,
                rss_warning_bytes=RSS_WARNING,
            )
            child = _stage_result(root, result, child_record, f"precompile:{group}")
            child["group"] = group
            children.append(child)
            if (
                result["returncode"] != 0
                or result["stop_reason"] is not None
                or not result["process_group_gone"]
                or not child_record.is_file()
            ):
                if result["stop_reason"] in {"process_tree_rss_watchdog", "process_tree_swap"}:
                    break
                raise RuntimeError(f"precompile lifecycle failed: {group}")
        else:
            cache_before = authority_runner._cache_snapshot(cache)
            worker_record = root / "raw" / "worker_record.json"
            worker_result = authority_runner._run_parent_child(
                _worker_command(root, worker_record, source_sha, _absolute(input_path), phase),
                process_path,
                "worker",
                root / "worker.stdout.log",
                root / "worker.stderr.log",
                rss_watchdog_bytes=RSS_WATCHDOG,
                rss_warning_bytes=RSS_WARNING,
            )
            worker_result = _stage_result(root, worker_result, worker_record, "worker")
            if (
                worker_result["returncode"] != 0
                or worker_result["stop_reason"] is not None
                or not worker_result["process_group_gone"]
                or not worker_record.is_file()
            ):
                if worker_result["stop_reason"] not in {"process_tree_rss_watchdog", "process_tree_swap"}:
                    raise RuntimeError("eventual worker lifecycle failed")
            else:
                cache_after = authority_runner._cache_snapshot(cache)
                if cache_before != cache_after:
                    raise RuntimeError("worker changed the parent-owned JIT cache")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    process = authority_runner._process_summary(process_path) if process_path.is_file() else None
    marker_manifest_path, marker_rows = _marker_manifest(root, phase)
    checker_output = root / "checker.json"
    completion_path = root / "completion.json"
    checker_process_path = root / "checker_process.jsonl"
    parent_record = {
        "schema": PARENT_SCHEMA,
        "workflow": WORKFLOW,
        "phase": phase,
        "source": source,
        "expected_mpi_size": 1,
        "resource_contract": {
            "warning_bytes": RSS_WARNING,
            "rss_watchdog_bytes": RSS_WATCHDOG,
            "rss_hard_gate_bytes": RSS_HARD,
            "swap_hard_gate_bytes": SWAP_HARD,
        },
        "command": {"argv": [str(value) for value in os.sys.argv], "cwd": str(REPO_ROOT)},
        "paths": {
            "jit_cache": "jit_cache",
            "children": "children",
            "process_samples": "parent_process.jsonl",
            "marker_manifest": str(marker_manifest_path.relative_to(root)) if marker_manifest_path else None,
            "e0_checkpoint_preflight": (
                str(e0_path.relative_to(root)) if e0_path is not None else None
            ),
            "e0_checkpoint_preflight_sha256": (
                _sha256(e0_path) if e0_path is not None else None
            ),
            "checker_output": str(checker_output.relative_to(root)),
            "completion": str(completion_path.relative_to(root)),
            "checker_process_samples": str(checker_process_path.relative_to(root)),
        },
        "jit_groups": list(JIT_GROUPS),
        "children": children,
        "worker": worker_result,
        "stages": [*children, worker_result] if worker_result is not None else children,
        "cache": {"initial": cache_initial, "before_worker": cache_before, "after_worker": cache_after},
        "process": process,
        "markers": {"rows": marker_rows, "sha256": _sha256(marker_manifest_path) if marker_manifest_path else None},
        "e0": e0_facts,
        "classification": "RAW_COMPLETE_PENDING_CHECKER" if error is None else None,
        "error": error,
    }
    _write_json(record_path, parent_record)
    checker_result = authority_runner._run_parent_child(
        _checker_command(record_path, checker_output, source_sha),
        checker_process_path,
        "checker",
        root / "checker.stdout.log",
        root / "checker.stderr.log",
        rss_watchdog_bytes=RSS_WATCHDOG,
        rss_warning_bytes=RSS_WARNING,
    )
    checker_result = _stage_result(root, checker_result, checker_output, "checker")
    checker_sha = _sha256(checker_output) if checker_output.is_file() else None
    checker_complete = (
        checker_output.is_file()
        and checker_sha is not None
        and checker_result.get("returncode") == 0
        and checker_result.get("stop_reason") is None
        and checker_result.get("process_group_gone") is True
        and checker_result.get("lifecycle_failure") is False
        and checker_result.get("all_status_readable") is True
        and checker_result.get("max_swap_bytes") == 0
        and isinstance(checker_result.get("peak_rss_bytes"), int)
        and not isinstance(checker_result.get("peak_rss_bytes"), bool)
        and checker_result["peak_rss_bytes"] < RSS_HARD
        and checker_result.get("rss_watchdog_bytes") == RSS_HARD
    )
    completion = {
        "schema": COMPLETION_SCHEMA,
        "workflow": WORKFLOW,
        "phase": phase,
        "parent_record": record_path.name,
        "parent_record_sha256": _sha256(record_path),
        "checker": checker_output.name,
        "checker_sha256": checker_sha,
        "checker_process": checker_result,
        "status": "PASS" if checker_complete else "FAIL",
    }
    _write_json(completion_path, completion)
    return 0 if completion["status"] == "PASS" else 1


def run_worker(root: Path, record_path: Path, source_sha: str, input_path: Path, phase: str, mpi_size: int) -> None:
    root = _absolute(root)
    cache = root / "jit_cache"
    os.environ["XDG_CACHE_HOME"] = str(cache)
    if not cache.is_dir():
        raise FileNotFoundError(f"parent-owned cache is missing: {cache}")
    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    if int(comm.size) != int(mpi_size):
        raise RuntimeError("worker MPI size mismatch")
    raw_dir, marker_dir = authority_runner._prepare_worker_paths(root, comm)
    _marker(comm, marker_dir, phase, "paths_ready", source_sha, cache_dir="jit_cache")
    _marker(comm, marker_dir, phase, "abi_ready", source_sha, runtime=authority_runner._runtime_facts(comm, PETSc, mpi_size))
    _run_worker(root, raw_dir, marker_dir, record_path, source_sha, input_path, phase, comm)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--mode", choices=("parent", "worker"), required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--mpi-size", choices=(1,), type=int, required=True)
    parser.add_argument("--e1-checker")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = _absolute(args.artifact_root)
    record = _absolute(args.record)
    input_path = _absolute(args.input)
    if args.phase == "e2" and args.mode == "parent":
        if not args.e1_checker or not _e1_checker_authority(
            _absolute(args.e1_checker), args.source_sha
        ):
            raise RuntimeError("E2 requires a hash-bound independent E1 checker PASS")
    if args.mode == "parent":
        return _run_parent(root, record, args.source_sha, input_path, args.phase)
    run_worker(root, record, args.source_sha, input_path, args.phase, args.mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
