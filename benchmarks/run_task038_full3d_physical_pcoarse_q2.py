"""Run the V16 Q2 checkpoint-reference correction lane."""

from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import sys
from typing import Any

from benchmarks import run_task038_full3d_physical_pcoarse_q1 as authority_runner


BRANCH = authority_runner.BRANCH
MODULE = "benchmarks.run_task038_full3d_physical_pcoarse_q2"
PHASE = "q2-reference-correction"
WORKFLOW = "q2-reference-checkpoint-correction"
PARENT_SCHEMA = "task038.v16.q2.parent.v1"
WORKER_SCHEMA = "task038.v16.q2.worker.v1"
PROCESS_SCHEMA = authority_runner.PROCESS_SCHEMA
MARKER_SCHEMA = "task038.v16.q2.marker.v1"
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "case_built",
    "checkpoint_restored",
    "residual_reproduced",
    "inner_complete",
    "correction_measured",
    "release_complete",
    "record_written",
)
JIT_GROUPS = authority_runner.JIT_GROUPS
EXPECTED_MPI_SIZES = (1,)
REPO_ROOT = authority_runner.REPO_ROOT
INPUT_SHA256 = authority_runner.INPUT_SHA256
MODE_MANIFEST_SHA256 = authority_runner.MODE_MANIFEST_SHA256
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
RESOLVED_CONFIG_SHA256 = (
    "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
)
CHECKPOINT_RELATIVE = Path(
    "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/"
    "j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d/"
    "checkpoints/checkpoint-1000"
)
CHECKPOINT_EXPECTED = {
    "iteration": 1000,
    "explicit_true_residual": 0.4837947981092168,
    "input_identity_sha256": "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f",
    "operator_identity_sha256": "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3",
    "physical_model_sha256": PHYSICAL_MODEL_SHA256,
    "source_sha": "ee5920b9fa977a39fea7bc09cfbe155303acdb2d",
    "mpi_size": 1,
    "manifest_sha256": "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139",
}
CHECKPOINT_SOLUTION_SHA256 = (
    "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b"
)
RSS_STAGING_WATCHDOG = 1_950_000_000
RSS_SOLVER_WATCHDOG = 1_950_000_000
INNER_MAX_IT = 10_000
INNER_RESIDUAL_LIMIT = 1.0e-6
RESTART = 20


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _write_json(path: Path, value: Any) -> None:
    authority_runner._write_json(path, _jsonable(value))


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
                **_jsonable(facts),
            },
            order=MARKER_ORDER,
            schema=MARKER_SCHEMA,
        )
    comm.barrier()


def _worker_command(
    root: Path, record: Path, source_sha: str, input_path: Path
) -> list[str]:
    return [
        "mpiexec",
        "-n",
        "1",
        str(Path(sys.executable)),
        "-m",
        MODULE,
        "--phase",
        PHASE,
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


def _solver_resource_sample() -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import resource_authority_sample

    sample = resource_authority_sample(os.getpid())
    process_tree = sample["process_tree"]
    if hasattr(process_tree, "to_dict"):
        sample["process_tree"] = process_tree.to_dict()
    return _jsonable(sample)


def _marker_callback(comm: Any, marker_dir: Path, source_sha: str):
    def callback(name: str, facts: Any) -> None:
        if name == "inner_complete":
            facts = {
                "iterations": int(facts["iterations"]),
                "final_true_residual": float(facts["final_true_residual"]),
                "matvec_count": int(facts["matvec_count"]),
                "pc_apply_count": int(facts["pc_apply_count"]),
                "ksp_destroy_count": int(facts["ksp_destroy_count"]),
                "restart_workspace_destroyed": all(
                    cycle["ksp_destroyed"] is True for cycle in facts["cycles"]
                ),
            }
        elif name == "checkpoint_restored":
            facts = {"iteration": int(facts["iteration"])}
        elif name == "residual_reproduced":
            facts = {
                "reproduction_relative": float(facts["reproduction_relative"])
            }
        _worker_marker(comm, marker_dir, name, source_sha, **dict(facts))

    return callback


def _action_audit(action: Any) -> dict[str, Any]:
    audit = dict(action.audit)
    return {
        key: _jsonable(audit[key])
        for key in (
            "schema",
            "global_aij_materialized",
            "global_schur_materialized",
            "ksp_created",
            "numeric_allgather",
            "t4_transmission_included",
            "apply_count",
        )
        if key in audit
    }


def run_worker(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> None:
    if int(expected_size) != 1:
        raise ValueError("Q2 reference lane is fixed to MPI1")
    root = _absolute(root)
    cache_dir = (root / "jit_cache").resolve()
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    if not cache_dir.is_dir():
        raise FileNotFoundError("parent-owned Q2 jit_cache is missing")

    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    source = authority_runner._source_facts(REPO_ROOT, source_sha, input_path)
    raw_dir, marker_dir = authority_runner._prepare_worker_paths(root, comm)
    record_path = _absolute(record_path)
    if record_path != raw_dir / "worker_record.json":
        raise ValueError("Q2 worker record must be raw/worker_record.json")
    cache = {
        "path": "jit_cache",
        "xdg_cache_home": str(Path(os.environ["XDG_CACHE_HOME"]).resolve()),
        "binding": Path(os.environ["XDG_CACHE_HOME"]).resolve() == cache_dir,
        "snapshot": authority_runner._cache_snapshot(cache_dir),
    }
    _worker_marker(comm, marker_dir, "paths_ready", source_sha, cache=cache)
    runtime = authority_runner._runtime_facts(comm, PETSc, expected_size)
    _worker_marker(comm, marker_dir, "abi_ready", source_sha, runtime=runtime)

    p6_bundle = None
    p3_bundle = None
    setup = None
    try:
        from benchmarks.run_task038_full3d_r3 import _current_input
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_p6_same_mesh_physical_bundle,
            build_same_mesh_physical_action,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            destroy_same_mesh_physical_action,
        )
        from src.solvers.fullspace_same_mesh_physical_pcoarse import (
            solve_reference_checkpoint_correction,
        )

        _specification, cfg10, _resolved, input_facts = _current_input(
            REPO_ROOT, _absolute(input_path)
        )
        p6_bundle = build_p6_same_mesh_physical_bundle(cfg10, comm)
        setup = p6_bundle["setup"]
        mode_inventory = (
            p6_bundle["modes"],
            p6_bundle["mode_rows"],
            p6_bundle["mode_sha256"],
        )
        p3_bundle = build_same_mesh_physical_action(
            setup, cfg10, 3, mode_inventory=mode_inventory
        )
        _worker_marker(
            comm,
            marker_dir,
            "case_built",
            source_sha,
            levels=[6, 3, 1],
            p6_setup=True,
            p6_pre_post_smoother_applied=False,
            p3_positive_pc="setup_owned_lower_cycle",
        )
        q2_facts = solve_reference_checkpoint_correction(
            p6_bundle,
            p3_bundle,
            REPO_ROOT / CHECKPOINT_RELATIVE,
            CHECKPOINT_EXPECTED,
            resource_sample=_solver_resource_sample,
            stage_callback=_marker_callback(comm, marker_dir, source_sha),
        )
        q2_facts["input_facts"] = input_facts
        q2_facts["checkpoint_authority"] = {
            "directory": CHECKPOINT_RELATIVE.as_posix(),
            "manifest_sha256": CHECKPOINT_EXPECTED["manifest_sha256"],
            "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
            "source_sha": CHECKPOINT_EXPECTED["source_sha"],
        }
        q2_facts["actions"] = {
            "p6": _action_audit(p6_bundle["physical_action"]),
            "p3": _action_audit(p3_bundle["action"]),
        }
        transfer_audit = p6_bundle["setup"]["p63_owner_transfer"].audit
        q2_facts["p63_transfer"] = {
            key: _jsonable(transfer_audit[key])
            for key in (
                "pair_fine_to_coarse",
                "global_transfer_matrix",
                "numeric_allgather",
                "static_condensation",
            )
        }
        q2_facts["provenance"] = {
            "input_sha256": INPUT_SHA256,
            "resolved_config_sha256": RESOLVED_CONFIG_SHA256,
            "physical_model_sha256": PHYSICAL_MODEL_SHA256,
            "mode_manifest_sha256": MODE_MANIFEST_SHA256,
        }
    finally:
        if p3_bundle is not None:
            destroy_same_mesh_physical_action(p3_bundle)
        if p6_bundle is not None:
            physical_action = p6_bundle.pop("physical_action", None)
            if physical_action is not None:
                physical_action.destroy()
            p6_bundle.clear()
        if setup is not None:
            destroy_p6_same_mesh_setup_bundle(setup)
        gc.collect()

    _worker_marker(comm, marker_dir, "release_complete", source_sha)
    if int(comm.rank) == 0:
        worker_record = {
            "schema": WORKER_SCHEMA,
            "raw_facts_only": True,
            "source": source,
            "runtime": runtime,
            "facts": _jsonable(q2_facts),
            "cache": cache,
            "paths": {
                "cache_dir": "jit_cache",
                "record": "raw/worker_record.json",
                "checkpoint": CHECKPOINT_RELATIVE.as_posix(),
            },
        }
        _write_json(record_path, worker_record)
    comm.barrier()
    _worker_marker(comm, marker_dir, "record_written", source_sha)


def run_parent(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> int:
    if int(expected_size) != 1:
        raise ValueError("Q2 reference lane is fixed to MPI1")
    root, cache = authority_runner._prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("Q2 parent record must be directly below root")
    children_dir = root / "children"
    children_dir.mkdir(exist_ok=False)
    process_path = root / "parent_process.jsonl"
    source = authority_runner._source_facts(REPO_ROOT, source_sha, input_path)
    cache_initial = authority_runner._cache_snapshot(cache)
    children: list[dict[str, Any]] = []
    worker_result = None
    cache_before = None
    cache_after = None
    error = None
    try:
        for index, group in enumerate(JIT_GROUPS):
            stem = f"{index:02d}_{group.replace('-', '_')}"
            child_record = children_dir / f"{stem}.json"
            child = authority_runner._run_parent_child(
                authority_runner._child_command(
                    group, cache, child_record, source_sha, _absolute(input_path)
                ),
                process_path,
                f"precompile:{group}",
                children_dir / f"{stem}.stdout.log",
                children_dir / f"{stem}.stderr.log",
                rss_watchdog_bytes=RSS_STAGING_WATCHDOG,
            )
            child.update({"group": group, "record": str(child_record.relative_to(root))})
            children.append(child)
            if (
                child["returncode"] != 0
                or child["stop_reason"] is not None
                or not child["process_group_gone"]
            ):
                raise RuntimeError(f"Q2 precompile lifecycle failed: {group}")
        cache_before = authority_runner._cache_snapshot(cache)
        worker_record = root / "raw" / "worker_record.json"
        worker_result = authority_runner._run_parent_child(
            _worker_command(root, worker_record, source_sha, _absolute(input_path)),
            process_path,
            "worker",
            root / "worker.stdout.log",
            root / "worker.stderr.log",
            rss_watchdog_bytes=RSS_SOLVER_WATCHDOG,
        )
        cache_after = authority_runner._cache_snapshot(cache)
        if (
            worker_result["returncode"] != 0
            or worker_result["stop_reason"] is not None
            or not worker_result["process_group_gone"]
        ):
            raise RuntimeError("Q2 worker lifecycle failed")
        if cache_before != cache_after:
            raise RuntimeError("Q2 worker changed the parent-owned JIT cache")
    except Exception as exc:
        error = str(exc)

    process = (
        authority_runner._process_summary(process_path)
        if process_path.is_file()
        else None
    )
    marker_dir = root / "markers"
    marker_manifest_path = root / "marker_manifest.json"
    marker_rows = []
    if marker_dir.is_dir():
        for path in authority_runner.marker_files(marker_dir, order=MARKER_ORDER):
            marker_rows.append(
                {"name": path.stem.split("_", 1)[1], "sha256": authority_runner.sha256_file(path)}
            )
    if marker_rows and not marker_manifest_path.exists():
        _write_json(marker_manifest_path, marker_rows)
    worker_record = root / "raw" / "worker_record.json"
    parent_record = {
        "schema": PARENT_SCHEMA,
        "source": source,
        "workflow": WORKFLOW,
        "phase": PHASE,
        "expected_mpi_size": 1,
        "rss_watchdog_bytes": RSS_SOLVER_WATCHDOG,
        "staging_rss_watchdog_bytes": RSS_STAGING_WATCHDOG,
        "command": {
            "argv": [str(value) for value in sys.argv],
            "worker_argv": [] if worker_result is None else worker_result["argv"],
            "cwd": str(REPO_ROOT),
        },
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "worker_record": "raw/worker_record.json",
            "marker_manifest": "marker_manifest.json",
            "checkpoint": CHECKPOINT_RELATIVE.as_posix(),
        },
        "checkpoint_authority": {
            "manifest_sha256": CHECKPOINT_EXPECTED["manifest_sha256"],
            "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
            "source_sha": CHECKPOINT_EXPECTED["source_sha"],
        },
        "jit_groups": list(JIT_GROUPS),
        "cache": {
            "initial": cache_initial,
            "before_worker": cache_before,
            "after_worker": cache_after,
        },
        "children": children,
        "process": process,
        "worker": (
            None
            if worker_result is None
            else {
                **worker_result,
                "record_present": worker_record.is_file(),
                "record_sha256": (
                    authority_runner.sha256_file(worker_record)
                    if worker_record.is_file()
                    else None
                ),
                "stdout_sha256": authority_runner.sha256_file(root / "worker.stdout.log"),
                "stderr_sha256": authority_runner.sha256_file(root / "worker.stderr.log"),
            }
        ),
        "markers": (
            None
            if not marker_manifest_path.is_file()
            else {
                "manifest_relative_path": "marker_manifest.json",
                "manifest_sha256": authority_runner.sha256_file(marker_manifest_path),
                "names": [row["name"] for row in marker_rows],
            }
        ),
        "error": error,
    }
    if not record_path.exists():
        _write_json(record_path, parent_record)
    return 0 if error is None else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=(PHASE,), required=True)
    parser.add_argument("--mode", choices=("parent", "worker"), required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--mpi-size", type=int, choices=EXPECTED_MPI_SIZES, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.mode == "parent":
            return run_parent(
                _absolute(args.artifact_root),
                _absolute(args.record),
                args.source_sha,
                _absolute(args.input),
                args.mpi_size,
            )
        run_worker(
            _absolute(args.artifact_root),
            _absolute(args.record),
            args.source_sha,
            _absolute(args.input),
            args.mpi_size,
        )
        return 0
    except Exception as error:
        print(f"Q2 reference execution failed: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
