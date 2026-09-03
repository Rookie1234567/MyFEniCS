"""Run the small V16 Q1.2 p3 physical inner-solve evidence lane.

The parent reuses the reviewed cold JIT staging and process sampler.  The
worker builds only the p3/h50 physical action and the existing p3-to-p1
positive cycle, then records raw facts for the two fixed right-FGMRES sources.
"""

from __future__ import annotations

import argparse
import copy
import gc
import json
import os
from pathlib import Path
import sys
from typing import Any

from benchmarks import run_task038_full3d_physical_pcoarse_q1 as authority_runner


BRANCH = authority_runner.BRANCH
MODULE = "benchmarks.run_task038_full3d_physical_pcoarse_q1_inner"
PHASE = "inner-solve"
WORKFLOW = "q1-physical-pcoarse-inner"
PARENT_SCHEMA = "task038.v16.q1.inner.parent.v1"
WORKER_SCHEMA = "task038.v16.q1.inner.worker.v1"
PROCESS_SCHEMA = authority_runner.PROCESS_SCHEMA
MARKER_SCHEMA = "task038.v16.q1.inner.marker.v1"
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "case_built",
    "source_physical_rhs_complete",
    "source_random_complete",
    "release_complete",
    "record_written",
)
JIT_GROUPS = authority_runner.JIT_GROUPS
EXPECTED_MPI_SIZES = (1, 2)
INPUT_SHA256 = authority_runner.INPUT_SHA256
MODE_MANIFEST_SHA256 = authority_runner.MODE_MANIFEST_SHA256
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
MODE_COUNT = 80
INNER_MAX_IT = 5000
INNER_RESIDUAL_LIMIT = 1.0e-6
INNER_RESTART = 20
MPI1_SOLVER_RSS_LIMIT = 500_000_000
REPEAT_LIMIT = 1.0e-12
REPO_ROOT = authority_runner.REPO_ROOT
SOURCE_NAMES = ("physical_rhs", "random")


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


def _rss_watchdog_bytes(mpi_size: int) -> int | None:
    return MPI1_SOLVER_RSS_LIMIT if int(mpi_size) == 1 else None


def _worker_command(
    root: Path, record: Path, source_sha: str, input_path: Path, mpi_size: int
) -> list[str]:
    return [
        "mpiexec",
        "-n",
        str(int(mpi_size)),
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
        str(int(mpi_size)),
    ]


def _packet_manifest(
    raw_dir: Path, source_name: str, packets: Any, audit: Any, comm: Any
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    canonical_dir = raw_dir / "canonical"
    if int(comm.rank) == 0:
        canonical_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = canonical_dir / f"{source_name}.rank{int(comm.rank):04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shard["rank"] = int(comm.rank)
    rows = comm.gather(shard, root=0)
    descriptor = None
    if int(comm.rank) == 0:
        manifest = canonical_shard_manifest(
            role="full_fe_dual",
            mpi_size=int(comm.size),
            shard_metadata=rows,
            extractor_audit={
                **_jsonable(dict(audit)),
                "source": source_name,
                "role": "full_fe_dual",
            },
        )
        manifest_path = canonical_dir / f"{source_name}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "manifest_relative_path": str(
                manifest_path.relative_to(raw_dir.parent)
            ),
            "manifest_sha256": manifest_sha,
            "role": "full_fe_dual",
            "packet_count": int(manifest["global_summed_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _compact_physical_audit(action: Any) -> dict[str, Any]:
    from benchmarks.run_task038_full3d_physical_pcoarse_q1_action import (
        _compact_action_audit,
    )

    return _compact_action_audit(action)


def _solver_resource_sample() -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import resource_authority_sample

    sample = resource_authority_sample(os.getpid())
    process_tree = sample["process_tree"]
    if hasattr(process_tree, "to_dict"):
        sample["process_tree"] = process_tree.to_dict()
    return _jsonable(sample)


def _solver_resource_summary(cycles: list[dict[str, Any]]) -> dict[str, Any]:
    samples = [cycle["resource"] for cycle in cycles]
    return {
        "sample_count": len(samples),
        "peak_memory_authority_bytes": max(
            int(sample["memory_authority_bytes"]) for sample in samples
        ),
        "max_swap_bytes": max(
            int(sample["process_tree"]["swap_bytes"]) for sample in samples
        ),
        "all_status_readable": all(
            sample["process_tree"]["all_status_readable"] is True
            for sample in samples
        ),
    }


def run_worker(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> None:
    root = _absolute(root)
    cache_dir = (root / "jit_cache").resolve()
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    if (
        not cache_dir.is_dir()
        or Path(os.environ["XDG_CACHE_HOME"]).resolve() != cache_dir
    ):
        raise FileNotFoundError("worker parent-owned jit_cache is not bound")

    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    source = authority_runner._source_facts(REPO_ROOT, source_sha, input_path)
    raw_dir, marker_dir = authority_runner._prepare_worker_paths(root, comm)
    record_path = _absolute(record_path)
    if record_path != raw_dir / "worker_record.json":
        raise ValueError("inner worker record must be raw/worker_record.json")
    cache_facts = {
        "path": "jit_cache",
        "xdg_cache_home": str(Path(os.environ["XDG_CACHE_HOME"]).resolve()),
        "binding": Path(os.environ["XDG_CACHE_HOME"]).resolve() == cache_dir,
        "snapshot": authority_runner._cache_snapshot(cache_dir),
    }
    _worker_marker(comm, marker_dir, "paths_ready", source_sha, cache=cache_facts)
    runtime = authority_runner._runtime_facts(comm, PETSc, expected_size)
    _worker_marker(comm, marker_dir, "abi_ready", source_sha, runtime=runtime)

    case = None
    try:
        from benchmarks.run_task038_full3d_r3 import _current_input
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        from src.solvers.fullspace_memory_first_krylov import destroy_krylov_result
        from src.solvers.fullspace_same_mesh_physical_pcoarse import (
            build_small_same_mesh_physical_inner_case,
            build_small_same_mesh_physical_inner_rhs,
            destroy_small_same_mesh_physical_inner_case,
            measure_small_same_mesh_physical_inner_pc,
            solve_small_same_mesh_physical_inner,
        )
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            extract_canonical_full_fe_dual_packets,
        )

        _specification, cfg10, _resolved, input_facts = _current_input(
            REPO_ROOT, _absolute(input_path)
        )
        cfg3 = copy.deepcopy(cfg10)
        cfg3.nedelec_degree = 3
        cfg3.mesh_target_size = 50.0
        modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg3)
        if len(modes) != MODE_COUNT or str(mode_sha) != MODE_MANIFEST_SHA256:
            raise RuntimeError("p3/h50 mode inventory identity changed")
        mode_facts = {
            "mode_count": MODE_COUNT,
            "mode_manifest_sha256": str(mode_sha),
            "degree": 3,
            "mesh_target_size_nm": 50.0,
        }
        mode_inventory = (modes, mode_rows, mode_sha)
        case = build_small_same_mesh_physical_inner_case(
            cfg3, comm, mode_inventory=mode_inventory
        )
        _worker_marker(comm, marker_dir, "case_built", source_sha, mode=mode_facts)

        p3_space = case["fine_space"]
        p3_floquet = case["fine_floquet"]
        physical_audit = _compact_physical_audit(case["physical_action"]["action"])
        pmg_audit = dict(case["pmg"].audit)
        architecture = {
            "levels": [3, 1],
            "p3_only": True,
            "p6_shell": False,
            "p6_action": False,
            "global_physical_aij": False,
            "global_dense_dtn": False,
            "physical_factor": False,
            "numeric_allgather": False,
            "phase_once": "finalized_floquet_mpc_once_no_wrapper_reapply",
            "physical_action": physical_audit,
            "positive_pmg": pmg_audit,
        }
        source_records: list[dict[str, Any]] = []
        for source_name in SOURCE_NAMES:
            rhs = None
            result = None
            try:
                rhs, source_generation = build_small_same_mesh_physical_inner_rhs(
                    case, source_name
                )
                rhs_before = authority_runner._owned_slave_facts(
                    rhs, p3_floquet.mpc, comm
                )
                pc_facts = measure_small_same_mesh_physical_inner_pc(case, rhs)
                result = solve_small_same_mesh_physical_inner(
                    case, rhs, resource_sample=_solver_resource_sample
                )
                solver_facts = {
                    key: value
                    for key, value in result.items()
                    if key != "final_solution"
                }
                solver_facts["resource_summary"] = _solver_resource_summary(
                    solver_facts["cycles"]
                )
                destroy_krylov_result(result)
                result = None
                rhs_after = authority_runner._owned_slave_facts(
                    rhs, p3_floquet.mpc, comm
                )
                packets, extractor_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, rhs
                )
                descriptor = _packet_manifest(
                    raw_dir, source_name, packets, extractor_audit, comm
                )
                rank_facts = comm.gather(
                    {
                        "rank": int(comm.rank),
                        "before_sha256": rhs_before["array_sha256"],
                        "after_sha256": rhs_after["array_sha256"],
                    },
                    root=0,
                )
                if int(comm.rank) == 0:
                    source_records.append(
                        {
                            "name": source_name,
                            "generation": _jsonable(source_generation),
                            "rhs_before": rhs_before,
                            "rhs_after": rhs_after,
                            "rank_input_facts": rank_facts,
                            "pc": _jsonable(pc_facts),
                            "solver": _jsonable(solver_facts),
                            "canonical": descriptor,
                        }
                    )
                del packets, extractor_audit
                _worker_marker(
                    comm,
                    marker_dir,
                    f"source_{source_name}_complete",
                    source_sha,
                    source=source_name,
                    final_true_residual=float(solver_facts["final_true_residual"]),
                )
            finally:
                if result is not None:
                    destroy_krylov_result(result)
                if rhs is not None:
                    rhs.destroy()

        del modes, mode_rows, mode_inventory, cfg3, cfg10, _specification, _resolved
        destroy_small_same_mesh_physical_inner_case(case)
        case = None
        gc.collect()
        _worker_marker(comm, marker_dir, "release_complete", source_sha)
        if int(comm.rank) == 0:
            worker_record = {
                "schema": WORKER_SCHEMA,
                "raw_facts_only": True,
                "source": source,
                "runtime": runtime,
                "input": input_facts,
                "mode_inventory": mode_facts,
                "cache": cache_facts,
                "paths": {
                    "cache_dir": "jit_cache",
                    "record": "raw/worker_record.json",
                    "canonical_dir": "raw/canonical",
                },
                "architecture": architecture,
                "sources": source_records,
            }
            _write_json(record_path, worker_record)
        comm.barrier()
        _worker_marker(comm, marker_dir, "record_written", source_sha)
    finally:
        if case is not None:
            destroy_small_same_mesh_physical_inner_case(case)
        gc.collect()


def run_parent(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> int:
    root, cache = authority_runner._prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("inner parent record must be directly below root")
    children_dir = root / "children"
    children_dir.mkdir(exist_ok=False)
    process_path = root / "parent_process.jsonl"
    source = authority_runner._source_facts(REPO_ROOT, source_sha, input_path)
    cache_initial = authority_runner._cache_snapshot(cache)
    children: list[dict[str, Any]] = []
    worker_result = None
    error = None
    cache_before = None
    cache_after = None
    watchdog = _rss_watchdog_bytes(expected_size)
    staging_watchdog = authority_runner.RSS_WATCHDOG
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
                rss_watchdog_bytes=staging_watchdog,
            )
            child.update({"group": group, "record": str(child_record.relative_to(root))})
            children.append(child)
            if (
                child["returncode"] != 0
                or child["stop_reason"] is not None
                or not child["process_group_gone"]
            ):
                raise RuntimeError(f"precompile lifecycle failed: {group}")
        cache_before = authority_runner._cache_snapshot(cache)
        worker_record = root / "raw" / "worker_record.json"
        worker_result = authority_runner._run_parent_child(
            _worker_command(
                root, worker_record, source_sha, _absolute(input_path), expected_size
            ),
            process_path,
            "worker",
            root / "worker.stdout.log",
            root / "worker.stderr.log",
            rss_watchdog_bytes=watchdog,
        )
        cache_after = authority_runner._cache_snapshot(cache)
        if (
            worker_result["returncode"] != 0
            or worker_result["stop_reason"] is not None
            or not worker_result["process_group_gone"]
        ):
            raise RuntimeError("inner worker lifecycle failed")
        if cache_before != cache_after:
            raise RuntimeError("inner worker changed the parent-owned JIT cache")
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
                {
                    "name": path.stem.split("_", 1)[1],
                    "sha256": authority_runner.sha256_file(path),
                }
            )
    if marker_rows and not marker_manifest_path.exists():
        _write_json(marker_manifest_path, marker_rows)
    worker_record = root / "raw" / "worker_record.json"
    parent_record = {
        "schema": PARENT_SCHEMA,
        "source": source,
        "workflow": WORKFLOW,
        "phase": PHASE,
        "expected_mpi_size": int(expected_size),
        "rss_watchdog_bytes": watchdog,
        "staging_rss_watchdog_bytes": staging_watchdog,
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
    parser.add_argument(
        "--mpi-size",
        "--expected-mpi-size",
        dest="mpi_size",
        type=int,
        choices=EXPECTED_MPI_SIZES,
        required=True,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = _absolute(args.artifact_root)
    record = _absolute(args.record)
    input_path = _absolute(args.input)
    if args.mode == "parent":
        return run_parent(root, record, args.source_sha, input_path, args.mpi_size)
    run_worker(root, record, args.source_sha, input_path, args.mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
