"""Thin orchestration for the fixed restart-64 physical Krylov qualification.

The numerical work stays in the reusable physical bundle and fixed-restart
solver.  This module owns only the cold JIT children, one worker, markers,
resource samples, and raw scalar evidence.  The checkpoint at absolute
iteration 1000 is represented inside the solver as additional iteration zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from benchmarks import run_task038_full3d_physical_pcoarse_q1 as authority_runner
from benchmarks import run_task038_v17_oracles as v17


BRANCH = authority_runner.BRANCH
MODULE = "benchmarks.run_task038_v18_restart64"
PHASE = "restart64"
WORKFLOW = "task038-v18-restart64-physical-krylov"
JIT_GROUPS = tuple(authority_runner.JIT_GROUPS)

RESTART = 64
QUALIFIER_STEPS = 64
SCREEN_STEPS = 1024
TOTAL_STEPS = 10240
CHECKPOINT_INTERVAL = 256
CHECKPOINT_ABSOLUTE_ITERATION = 1000

RSS_WARNING = 1_800_000_000
RSS_HARD = 2_000_000_000
RSS_WATCHDOG = RSS_HARD
SWAP_HARD = 0

SCREEN_STEP512_LIMIT = 0.25
SCREEN_STEP1024_LIMIT = 0.10
SCREEN_RATIO_LIMIT = 0.85
LONG_RESIDUAL_LIMIT = 1.0e-6

EXPECTED_MPI_SIZES = (1,)
MARKER_SCHEMA = "task038.v18.restart64.marker.v1"
PARENT_SCHEMA = "task038.v18.restart64.parent.v1"
WORKER_SCHEMA = "task038.v18.restart64.worker.v1"
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "case_built",
    "checkpoint_restored",
    "qualifier_complete",
    "screen_complete",
    "continuation_complete",
    "record_written",
    "release_complete",
)

REPO_ROOT = authority_runner.REPO_ROOT
LEXICAL_PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _write_json(path: Path, value: Any) -> None:
    authority_runner._write_json(path, value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _array_sha(values: Any) -> str:
    import numpy as np

    array = np.asarray(values, dtype=np.complex128)
    return hashlib.sha256(
        memoryview(np.ascontiguousarray(array)).cast("B")
    ).hexdigest()


def _vec_relative(left: Any, right: Any) -> float:
    import numpy as np

    left_values = np.asarray(left.getArray(readonly=True), dtype=np.complex128)
    right_values = np.asarray(right.getArray(readonly=True), dtype=np.complex128)
    numerator = float(np.linalg.norm(left_values - right_values))
    denominator = max(float(np.linalg.norm(right_values)), np.finfo(float).tiny)
    return numerator / denominator


def _source_facts(source_sha: str, input_path: Path) -> dict[str, Any]:
    return {
        **v17._stage_source(REPO_ROOT, source_sha, input_path),
        "template_sha256": v17.INPUT_SHA256,
    }


def _worker_marker(
    comm: Any, marker_dir: Path, name: str, source_sha: str, **facts: Any
) -> None:
    if int(comm.rank) == 0:
        authority_runner.write_marker(
            marker_dir,
            name,
            {
                "phase": PHASE,
                "workflow": WORKFLOW,
                "source_sha": source_sha,
                "mpi_size": int(comm.size),
                **facts,
            },
            order=MARKER_ORDER,
            schema=MARKER_SCHEMA,
        )
    comm.barrier()


def _worker_command(
    root: Path,
    record: Path,
    source_sha: str,
    input_path: Path,
    size: int,
) -> list[str]:
    return [
        "mpiexec",
        "-n",
        str(size),
        LEXICAL_PYTHON,
        "-m",
        MODULE,
        "--phase",
        PHASE,
        "--mode",
        "worker",
        "--stage",
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
        str(size),
    ]


def _jit_child_command(
    group: str,
    cache: Path,
    record: Path,
    source_sha: str,
    input_path: Path,
) -> list[str]:
    return v17._jit_child_command(group, cache, record, source_sha, input_path)


def _stage_result(
    root: Path, result: dict[str, Any], record_path: Path, stage: str
) -> dict[str, Any]:
    result = dict(result)
    result.update(
        {
            "stage": stage,
            "record": str(record_path.relative_to(root)),
            "record_sha256": (
                _sha256(record_path) if record_path.is_file() else None
            ),
        }
    )
    return result


def _marker_manifest(root: Path) -> tuple[Path | None, list[dict[str, Any]]]:
    marker_dir = root / "markers"
    if not marker_dir.is_dir():
        return None, []
    rows = [
        {
            "name": path.stem.split("_", 1)[1],
            "relative_path": str(path.relative_to(root)),
            "sha256": authority_runner.sha256_file(path),
        }
        for path in authority_runner.marker_files(marker_dir, order=MARKER_ORDER)
    ]
    if not rows:
        return None, rows
    manifest_path = root / "marker_manifest.json"
    if not manifest_path.exists():
        _write_json(manifest_path, rows)
    return manifest_path, rows


def run_parent(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    mpi_size: int,
) -> int:
    root, cache = authority_runner._prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("parent record must be directly below the fresh root")
    children_dir = root / "children"
    children_dir.mkdir(exist_ok=False)
    process_path = root / "parent_process.jsonl"
    source = _source_facts(source_sha, input_path)
    disk_free = int(shutil.disk_usage(root).free)
    cache_initial = authority_runner._cache_snapshot(cache)
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
                _jit_child_command(
                    group, cache, child_record, source_sha, _absolute(input_path)
                ),
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
            ):
                raise RuntimeError(f"precompile lifecycle failed: {group}")
        cache_before = authority_runner._cache_snapshot(cache)
        worker_record = root / "raw" / "worker_record.json"
        worker_result = authority_runner._run_parent_child(
            _worker_command(
                root, worker_record, source_sha, _absolute(input_path), mpi_size
            ),
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
        ):
            raise RuntimeError("restart64 worker lifecycle failed")
        cache_after = authority_runner._cache_snapshot(cache)
        if cache_before != cache_after:
            raise RuntimeError("worker changed the parent-owned JIT cache")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    process = (
        authority_runner._process_summary(process_path)
        if process_path.is_file()
        else None
    )
    marker_manifest_path, marker_rows = _marker_manifest(root)
    parent_record = {
        "schema": PARENT_SCHEMA,
        "workflow": WORKFLOW,
        "phase": PHASE,
        "source": source,
        "expected_mpi_size": int(mpi_size),
        "disk_free_bytes": disk_free,
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
            "marker_manifest": (
                str(marker_manifest_path.relative_to(root))
                if marker_manifest_path is not None
                else None
            ),
        },
        "jit_groups": list(JIT_GROUPS),
        "stages": [*children, worker_result] if worker_result is not None else children,
        "cache": {
            "initial": cache_initial,
            "before_worker": cache_before,
            "after_worker": cache_after,
        },
        "children": children,
        "worker": worker_result,
        "process": process,
        "markers": {
            "rows": marker_rows,
            "sha256": (
                _sha256(marker_manifest_path)
                if marker_manifest_path is not None
                else None
            ),
        },
        "classification": "RAW_COMPLETE_PENDING_CHECKER" if error is None else None,
        "error": error,
    }
    _write_json(record_path, parent_record)
    return 0 if error is None else 1


def _cycle_facts(
    result: dict[str, Any], stage: str, base_offset: int
) -> dict[str, Any]:
    cycles = []
    for original in result["cycles"]:
        cycle = dict(original)
        additional_end = int(base_offset) + int(cycle["end_iteration"])
        cycle["additional_iteration"] = additional_end
        cycle["absolute_iteration"] = CHECKPOINT_ABSOLUTE_ITERATION + additional_end
        cycles.append(cycle)
    settings = dict(result["settings"])
    settings.update(
        {
            "restart": RESTART,
            "cycle_max_it": RESTART,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "additional_iteration_origin": 0,
            "absolute_iteration_origin": CHECKPOINT_ABSOLUTE_ITERATION,
        }
    )
    return {
        "stage": stage,
        "base_offset": int(base_offset),
        "settings": settings,
        "additional_iterations": int(result["iterations"]),
        "absolute_end_iteration": CHECKPOINT_ABSOLUTE_ITERATION
        + base_offset
        + int(result["iterations"]),
        "initial_true_residual": float(result["initial_true_residual"]),
        "final_true_residual": float(result["final_true_residual"]),
        "matvec_count": int(result["matvec_count"]),
        "pc_apply_count": int(result["pc_apply_count"]),
        "explicit_action_count": int(result["explicit_action_count"]),
        "ksp_destroy_count": int(result["ksp_destroy_count"]),
        "elapsed_seconds": float(result["elapsed_seconds"]),
        "cycles": cycles,
        "checkpoint_facts": list(result["checkpoint_facts"]),
    }


def _screen_gates(screen: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    rows = {int(row["additional_iteration"]): row for row in screen["cycles"]}
    values = {
        step: float(rows[step]["explicit_true_residual"])
        if step in rows
        else None
        for step in (512, 768, 1024)
    }
    failures: list[str] = []
    if values[512] is None or not np.isfinite(values[512]) or values[512] > SCREEN_STEP512_LIMIT:
        failures.append("step512")
    if values[1024] is None or not np.isfinite(values[1024]) or values[1024] > SCREEN_STEP1024_LIMIT:
        failures.append("step1024")
    ratio = None
    if values[768] is not None and values[1024] is not None:
        ratio = values[1024] / max(abs(values[768]), np.finfo(float).tiny)
    if ratio is None or not np.isfinite(ratio) or ratio > SCREEN_RATIO_LIMIT:
        failures.append("r1024_over_r768")
    if any(
        isinstance(row, dict)
        and isinstance(row.get("resource"), dict)
        and isinstance(row["resource"].get("process_tree"), dict)
        and isinstance(row["resource"]["process_tree"].get("rss_bytes"), int)
        and row["resource"]["process_tree"]["rss_bytes"] >= RSS_HARD
        for row in screen["cycles"]
    ):
        failures.append("resource_rss")
    if any(
        isinstance(row, dict)
        and isinstance(row.get("resource"), dict)
        and isinstance(row["resource"].get("process_tree"), dict)
        and isinstance(row["resource"]["process_tree"].get("swap_bytes"), int)
        and row["resource"]["process_tree"]["swap_bytes"] != SWAP_HARD
        for row in screen["cycles"]
    ):
        failures.append("resource_swap")
    return {
        "step512": {"value": values[512], "limit": SCREEN_STEP512_LIMIT},
        "step1024": {"value": values[1024], "limit": SCREEN_STEP1024_LIMIT},
        "r1024_over_r768": {"value": ratio, "limit": SCREEN_RATIO_LIMIT},
        "gate_failures": failures,
        "passed": not failures,
    }


def _qualifier_gate_failures(
    qualifier: dict[str, Any], action_probe: dict[str, Any], pc_probe: dict[str, Any]
) -> list[str]:
    import numpy as np

    failures: list[str] = []
    settings = qualifier.get("settings")
    expected_settings = {
        "ksp_type": "fgmres",
        "pc_side": "right",
        "restart": RESTART,
        "cycle_max_it": RESTART,
        "start_iteration": 0,
        "residual_replacement": True,
    }
    if not isinstance(settings, dict) or any(
        settings.get(key) != value for key, value in expected_settings.items()
    ):
        failures.append("qualifier.settings")
    if qualifier.get("additional_iterations") != QUALIFIER_STEPS:
        failures.append("qualifier.iterations")
    for index, cycle in enumerate(qualifier.get("cycles", ())):
        residual = (
            cycle.get("explicit_true_residual") if isinstance(cycle, dict) else None
        )
        if not isinstance(residual, (int, float)) or not np.isfinite(residual):
            failures.append(f"qualifier.cycle[{index}].finite")
        resource = cycle.get("resource") if isinstance(cycle, dict) else None
        process_tree = resource.get("process_tree") if isinstance(resource, dict) else None
        rss = process_tree.get("rss_bytes") if isinstance(process_tree, dict) else None
        swap = process_tree.get("swap_bytes") if isinstance(process_tree, dict) else None
        if not isinstance(rss, int) or rss < 0 or rss >= RSS_HARD:
            failures.append(f"qualifier.cycle[{index}].rss")
        if not isinstance(swap, int) or swap != SWAP_HARD:
            failures.append(f"qualifier.cycle[{index}].swap")
    for label, probe, fact_key in (
        ("action", action_probe, "dual_facts"),
        ("pc", pc_probe, "primal_facts"),
    ):
        facts = probe.get(fact_key) if isinstance(probe, dict) else None
        if not isinstance(facts, dict) or facts.get("finite") is not True:
            failures.append(f"{label}.finite")
        elif facts.get("owned_slave_max") != 0.0 or facts.get("owned_slave_count") != 0:
            failures.append(f"{label}.owned_slave")
        repeat = probe.get("repeat_relative") if isinstance(probe, dict) else None
        if not isinstance(repeat, (int, float)) or not np.isfinite(repeat) or repeat > 1.0e-12:
            failures.append(f"{label}.repeat")
        if not isinstance(probe, dict) or probe.get("input_before_sha256") != probe.get("input_after_sha256"):
            failures.append(f"{label}.input_unchanged")
        if label == "pc":
            input_facts = probe.get("input_facts") if isinstance(probe, dict) else None
            if not isinstance(input_facts, dict) or input_facts.get("finite") is not True:
                failures.append("pc.input_facts.finite")
            elif (
                input_facts.get("owned_slave_max") != 0.0
                or input_facts.get("owned_slave_count") != 0
            ):
                failures.append("pc.input_facts.owned_slave")
    return failures


def _checkpoint_writer(
    root: Path,
    raw_dir: Path,
    stage: str,
    base_offset: int,
    p6_vector: Any,
    comm: Any,
    source_sha: str,
    checkpoint_iteration: int,
    explicit_true_residual: float,
) -> dict[str, Any]:
    from src.solvers.fullspace_memory_first_krylov import write_solution_checkpoint

    absolute_iteration = (
        CHECKPOINT_ABSOLUTE_ITERATION + base_offset + int(checkpoint_iteration)
    )
    checkpoint_dir = (
        raw_dir / stage / "solution_checkpoints" / f"solution-{absolute_iteration}"
    )
    checkpoint_dir.parent.mkdir(parents=True, exist_ok=True)
    facts = write_solution_checkpoint(
        checkpoint_dir,
        p6_vector,
        iteration=absolute_iteration,
        explicit_true_residual=explicit_true_residual,
        input_identity_sha256=v17.CHECKPOINT_INPUT_IDENTITY_SHA256,
        operator_identity_sha256=v17.CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        physical_model_sha256=v17.CHECKPOINT_PHYSICAL_MODEL_SHA256,
        source_sha=source_sha,
        ownership=v17._ownership(p6_vector, comm),
        comm=comm,
    )
    facts = dict(facts)
    manifest_path = Path(str(facts.pop("manifest_path")))
    facts.update(
        {
            "relative_path": str(checkpoint_dir.relative_to(root)),
            "manifest_relative_path": str(manifest_path.relative_to(root)),
            "absolute_iteration": absolute_iteration,
            "additional_iteration": int(base_offset) + int(checkpoint_iteration),
            "local_iteration": int(checkpoint_iteration),
        }
    )
    return facts


def _run_stage(
    raw_dir: Path,
    stage: str,
    base_offset: int,
    max_steps: int,
    initial: Any,
    rhs: Any,
    action: Any,
    pc: Any,
    p6_vector: Any,
    comm: Any,
    source_sha: str,
    stop_on_true_residual: bool,
    residual_limit: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from src.solvers.fullspace_memory_first_krylov import run_fixed_restart_cycles

    checkpoint_facts: list[dict[str, Any]] = []

    def observer(
        _iteration: int, _solution: Any, cycle: dict[str, Any]
    ) -> None:
        cycle["additional_iteration"] = int(base_offset) + int(
            cycle["end_iteration"]
        )
        cycle["absolute_iteration"] = (
            CHECKPOINT_ABSOLUTE_ITERATION + cycle["additional_iteration"]
        )

    def checkpoint_writer(
        iteration: int, solution: Any, explicit_true_residual: float
    ) -> dict[str, Any]:
        facts = _checkpoint_writer(
            raw_dir.parent,
            raw_dir,
            stage,
            base_offset,
            solution,
            comm,
            source_sha,
            iteration,
            explicit_true_residual,
        )
        checkpoint_facts.append(facts)
        return facts

    result = run_fixed_restart_cycles(
        rhs,
        action,
        pc,
        max_it=max_steps,
        residual_limit=residual_limit,
        resource_sample=v17._solver_resource_sample,
        initial_solution=initial,
        start_iteration=0,
        checkpoint_writer=checkpoint_writer,
        first_checkpoint_iteration=None,
        checkpoint_interval=CHECKPOINT_INTERVAL,
        cycle_observer=observer,
        stop_on_true_residual=stop_on_true_residual,
        ksp_type="fgmres",
        restart=RESTART,
        cycle_max_it=RESTART,
    )
    facts = _cycle_facts(result, stage, base_offset)
    facts["checkpoint_facts"] = checkpoint_facts
    return result, facts


def _run_worker(
    root: Path,
    raw_dir: Path,
    marker_dir: Path,
    source_sha: str,
    input_path: Path,
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
        "template_sha256": v17.INPUT_SHA256,
        "mode_manifest_sha256": v17.MODE_MANIFEST_SHA256,
    }
    disk_free = int(shutil.disk_usage(root).free)

    bundle = None
    rhs = checkpoint_solution = pc_input = None
    qualifier_result = screen_result = continuation_result = None
    action_probe = pc_probe = None
    record_written = False
    try:
        bundle = build_p6_same_mesh_physical_bundle(cfg, comm)
        setup = bundle["setup"]
        p6_mpc = setup["floquets"][6].mpc
        p6_matrix = setup["p6_shell"].matrix
        _worker_marker(
            comm,
            marker_dir,
            "case_built",
            source_sha,
            profile="same_mesh_hcurl_pmg_v1_requalified",
            degree=6,
            levels=[6, 3, 1],
            mode_manifest_sha256=bundle["mode_sha256"],
        )

        checkpoint_solution = p6_matrix.createVecRight()
        checkpoint = read_solution_checkpoint(
            v17.CHECKPOINT_DIR,
            checkpoint_solution,
            expected=v17._checkpoint_expected(),
            ownership=v17._ownership(checkpoint_solution, comm),
            comm=comm,
        )
        rhs, rhs_facts = build_physical_rhs(bundle)
        initial_values = np.asarray(
            checkpoint_solution.getArray(readonly=True), dtype=np.complex128
        ).copy()
        rhs_values = np.asarray(
            rhs.getArray(readonly=True), dtype=np.complex128
        ).copy()
        initial_descriptor = v17._write_array(
            raw_dir, "same_start/initial_solution.npy", initial_values
        )
        rhs_descriptor = v17._write_array(raw_dir, "same_start/rhs.npy", rhs_values)
        rhs_facts = {
            **rhs_facts,
            **v17._owned_vector_facts(rhs, p6_mpc, comm),
            "descriptor": rhs_descriptor,
        }
        checkpoint_facts = {
            **checkpoint,
            **v17._checkpoint_expected(),
            "solution_sha256": v17.CHECKPOINT_SOLUTION_SHA256,
        }
        _worker_marker(
            comm,
            marker_dir,
            "checkpoint_restored",
            source_sha,
            iteration=CHECKPOINT_ABSOLUTE_ITERATION,
            solution_sha256=v17.CHECKPOINT_SOLUTION_SHA256,
        )

        p6_input_before = _array_sha(checkpoint_solution.array)
        action_first = p6_matrix.createVecLeft()
        action_second = p6_matrix.createVecLeft()
        try:
            bundle["physical_action"].apply(checkpoint_solution, action_first)
            bundle["physical_action"].apply(checkpoint_solution, action_second)
            action_facts = v17._owned_vector_facts(action_first, p6_mpc, comm)
            action_probe = {
                "repeat_relative": _vec_relative(action_first, action_second),
                "finite": bool(
                    np.all(np.isfinite(action_first.getArray(readonly=True)))
                    and np.all(np.isfinite(action_second.getArray(readonly=True)))
                ),
                "input_before_sha256": p6_input_before,
                "input_after_sha256": _array_sha(checkpoint_solution.array),
                "dual_facts": action_facts,
            }
            pc_input = rhs.copy()
            pc_input.axpy(-1.0, action_first)
            pc_input_facts = v17._owned_vector_facts(pc_input, p6_mpc, comm)
            pc_input_before_sha = _array_sha(pc_input.array)
        finally:
            action_first.destroy()
            action_second.destroy()

        pc_first = setup["upper_cycle"].apply(pc_input)
        pc_second = setup["upper_cycle"].apply(pc_input)
        try:
            pc_facts = v17._owned_vector_facts(pc_first, p6_mpc, comm)
            pc_probe = {
                "repeat_relative": _vec_relative(pc_first, pc_second),
                "finite": bool(
                    np.all(np.isfinite(pc_first.getArray(readonly=True)))
                    and np.all(np.isfinite(pc_second.getArray(readonly=True)))
                ),
                "input_role": "dual_residual",
                "input_facts": pc_input_facts,
                "input_before_sha256": pc_input_before_sha,
                "input_after_sha256": _array_sha(pc_input.array),
                "primal_facts": pc_facts,
            }
        finally:
            pc_first.destroy()
            pc_second.destroy()

        rhs_before_sha = _array_sha(rhs.array)
        initial_before_sha = _array_sha(checkpoint_solution.array)

        def apply_action(source: Any) -> Any:
            target = p6_matrix.createVecLeft()
            bundle["physical_action"].apply(source, target)
            return target

        def apply_pc(source: Any) -> Any:
            return setup["upper_cycle"].apply(source)

        def write_worker_record(
            qualifier_facts: dict[str, Any],
            qualifier_failures: list[str],
            screen_facts: dict[str, Any] | None,
            continuation_facts: dict[str, Any] | None,
        ) -> None:
            nonlocal record_written

            rhs_after_sha = _array_sha(rhs.array)
            initial_after_sha = _array_sha(checkpoint_solution.array)
            screen_gate = (
                screen_facts["gates"]
                if screen_facts is not None
                else {"status": "not_run_qualifier_gate_failed"}
            )
            long_gate = (
                continuation_facts["gate"]
                if continuation_facts is not None
                else {
                    "status": (
                        "not_run_qualifier_gate_failed"
                        if screen_facts is None
                        else "not_run_screen_gate_failed"
                    )
                }
            )
            record = {
                "schema": WORKER_SCHEMA,
                "workflow": WORKFLOW,
                "phase": PHASE,
                "stage": "worker",
                "source": _source_facts(source_sha, input_path),
                "input": input_facts,
                "disk_free_bytes": disk_free,
                "checkpoint": checkpoint_facts,
                "rhs": rhs_facts,
                "same_start": {
                    "rhs": {
                        "descriptor": rhs_descriptor,
                        "array_sha256": _array_sha(rhs_values),
                    },
                    "initial_solution": {
                        "descriptor": initial_descriptor,
                        "array_sha256": _array_sha(initial_values),
                    },
                    "rhs_before_sha256": rhs_before_sha,
                    "rhs_after_sha256": rhs_after_sha,
                    "initial_solution_before_sha256": initial_before_sha,
                    "initial_solution_after_sha256": initial_after_sha,
                    "input_unchanged": (
                        rhs_before_sha == rhs_after_sha
                        and initial_before_sha == initial_after_sha
                    ),
                    "finite": bool(
                        np.all(np.isfinite(rhs_values))
                        and np.all(np.isfinite(initial_values))
                    ),
                    "initial_true_residual": float(
                        qualifier_facts["initial_true_residual"]
                    ),
                    "screen_initial_true_residual": (
                        float(screen_facts["initial_true_residual"])
                        if screen_facts is not None
                        else None
                    ),
                },
                "probes": {"action": action_probe, "pc": pc_probe},
                "high_space_primal": {
                    **pc_facts,
                    "role": "upper_cycle_pc_correction",
                },
                "qualifier": qualifier_facts,
                "screen": screen_facts,
                "continuation": continuation_facts,
                "architecture": {
                    "physical_operator": "p6_matrix_free_split_volume_plus_streaming_dtn",
                    "p6_matrix_free": True,
                    "global_physical_aij": False,
                    "global_schur": False,
                    "dense_dtn": False,
                    "factor": False,
                    "numeric_allgather": False,
                    "phase_once": True,
                    "restart": RESTART,
                    "restart_basis_storage": "petsc_in_memory",
                    "restart_basis_bound": "fixed_restart_64",
                },
                "gates": {
                    "qualifier": {
                        "gate_failures": qualifier_failures,
                        "passed": not qualifier_failures,
                    },
                    "screen": screen_gate,
                    "long": long_gate,
                },
                "lifecycle": {"marker_order": list(MARKER_ORDER)},
            }
            _write_json(raw_dir / "worker_record.json", record)
            _worker_marker(comm, marker_dir, "record_written", source_sha)
            record_written = True

        qualifier_result, qualifier = _run_stage(
            raw_dir,
            "qualifier",
            0,
            QUALIFIER_STEPS,
            checkpoint_solution,
            rhs,
            apply_action,
            apply_pc,
            checkpoint_solution,
            comm,
            source_sha,
            False,
            0.0,
        )
        qualifier_gate_failures = _qualifier_gate_failures(
            qualifier, action_probe, pc_probe
        )
        if (
            _array_sha(rhs.array) != rhs_before_sha
            or _array_sha(checkpoint_solution.array) != initial_before_sha
        ):
            qualifier_gate_failures.append("qualifier.input_unchanged")
        _worker_marker(
            comm,
            marker_dir,
            "qualifier_complete",
            source_sha,
            iterations=qualifier["additional_iterations"],
            final_true_residual=qualifier["final_true_residual"],
            matvec_count=qualifier["matvec_count"],
            pc_apply_count=qualifier["pc_apply_count"],
            ksp_destroy_count=qualifier["ksp_destroy_count"],
            gate_failures=qualifier_gate_failures,
        )
        if qualifier_gate_failures:
            write_worker_record(qualifier, qualifier_gate_failures, None, None)
        else:
            destroy_krylov_result(qualifier_result)
            qualifier_result = None

            screen_result, screen = _run_stage(
                raw_dir,
                "screen",
                0,
                SCREEN_STEPS,
                checkpoint_solution,
                rhs,
                apply_action,
                apply_pc,
                checkpoint_solution,
                comm,
                source_sha,
                False,
                0.0,
            )
            screen["gates"] = _screen_gates(screen)
            _worker_marker(
                comm,
                marker_dir,
                "screen_complete",
                source_sha,
                iterations=screen["additional_iterations"],
                final_true_residual=screen["final_true_residual"],
                gate_failures=screen["gates"]["gate_failures"],
            )

            continuation = None
            if screen["gates"]["passed"]:
                continuation_result, continuation = _run_stage(
                    raw_dir,
                    "continuation",
                    SCREEN_STEPS,
                    TOTAL_STEPS - SCREEN_STEPS,
                    screen_result["final_solution"],
                    rhs,
                    apply_action,
                    apply_pc,
                    checkpoint_solution,
                    comm,
                    source_sha,
                    True,
                    LONG_RESIDUAL_LIMIT,
                )
                continuation["gate"] = {
                    "final_true_residual": continuation["final_true_residual"],
                    "limit": LONG_RESIDUAL_LIMIT,
                    "passed": (
                        np.isfinite(continuation["final_true_residual"])
                        and continuation["final_true_residual"] <= LONG_RESIDUAL_LIMIT
                    ),
                }
                _worker_marker(
                    comm,
                    marker_dir,
                    "continuation_complete",
                    source_sha,
                    iterations=continuation["additional_iterations"],
                    final_true_residual=continuation["final_true_residual"],
                    matvec_count=continuation["matvec_count"],
                    pc_apply_count=continuation["pc_apply_count"],
                    ksp_destroy_count=continuation["ksp_destroy_count"],
                )
            write_worker_record(qualifier, [], screen, continuation)
    finally:
        for result in (continuation_result, screen_result, qualifier_result):
            if result is not None:
                destroy_krylov_result(result)
        if pc_probe is not None:
            pc_probe = None
        if action_probe is not None:
            action_probe = None
        if rhs is not None:
            rhs.destroy()
        if pc_input is not None:
            pc_input.destroy()
        if checkpoint_solution is not None:
            checkpoint_solution.destroy()
        if bundle is not None:
            destroy_p6_same_mesh_physical_bundle(bundle)
    if record_written:
        _worker_marker(comm, marker_dir, "release_complete", source_sha)


def run_worker(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    mpi_size: int,
) -> None:
    root = _absolute(root)
    cache = (root / "jit_cache").resolve()
    os.environ["XDG_CACHE_HOME"] = str(cache)
    if not cache.is_dir():
        raise FileNotFoundError("parent-owned JIT cache is missing")
    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    if int(comm.size) != int(mpi_size):
        raise RuntimeError("worker MPI size mismatch")
    expected_record = root / "raw" / "worker_record.json"
    record_path = _absolute(record_path)
    if record_path != expected_record:
        raise ValueError("worker record must be raw/worker_record.json")
    raw_dir, marker_dir = authority_runner._prepare_worker_paths(root, comm)
    _worker_marker(comm, marker_dir, "paths_ready", source_sha, cache_dir="jit_cache")
    runtime = authority_runner._runtime_facts(comm, PETSc, mpi_size)
    _worker_marker(comm, marker_dir, "abi_ready", source_sha, runtime=runtime)
    _run_worker(root, raw_dir, marker_dir, source_sha, input_path, comm)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=(PHASE,), required=True)
    parser.add_argument("--mode", choices=("parent", "worker"), required=True)
    parser.add_argument("--stage", choices=("worker",))
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--mpi-size", choices=EXPECTED_MPI_SIZES, type=int, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = _absolute(args.artifact_root)
    record = _absolute(args.record)
    input_path = _absolute(args.input)
    if args.mode == "parent":
        return run_parent(root, record, args.source_sha, input_path, args.mpi_size)
    if args.stage != "worker":
        raise ValueError("worker mode requires --stage worker")
    run_worker(root, record, args.source_sha, input_path, args.mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
