"""Run the V16 source-authority staging and h10-to-h50 R3 bridge.

The parent owns the fresh cache and the process-tree resource authority.  The
worker is the only process that creates ``raw`` and ``markers`` and performs
the already-reviewed source reconstruction and nonmatching bridge.  This
module deliberately keeps all PETSc/DOLFINx/MPI imports inside ``run_worker``.
"""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from benchmarks.task038_full3d_jit_staging import (
    append_jsonl,
    cache_manifest,
    marker_files,
    process_tree_snapshot,
    sha256_file,
    write_marker,
)

BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_physical_pcoarse_q1"
PHASE = "source-authority"
WORKFLOW = "q1-physical-pcoarse-source-authority"
WORKER_SCHEMA = "task038.v16.q1.source-authority.worker.v1"
PARENT_SCHEMA = "task038.v16.q1.source-authority.parent.v1"
PROCESS_SCHEMA = "task038.v16.q1.source-authority.process-sample.v1"
MARKER_SCHEMA = "task038.v16.q1.source-authority.marker.v1"
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "old_authority_streamed",
    "h10_reconstructed",
    "h50_bridged",
    "h10_released",
    "r3_ready",
    "record_written",
)
JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)
EXPECTED_MPI_SIZES = (1, 2)
RSS_WARNING = 1_800_000_000
RSS_WATCHDOG = 1_950_000_000
POLL_SECONDS = 0.05
TERMINATION_GRACE_SECONDS = 0.5
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
OLD_SOURCE_SHA = "2c8fca90c7300b85b30021081868b699c0b306d2"
OLD_MANIFEST_SHA256 = "0bf0588f888aba14177b19cf7f410d8dfb3edabcbd018a1c1b76f99df016c8fd"
OLD_SHARD_SHA256 = "a544b8a27d901bb4466f0e88e80c0ec64824caec295749d9c941f41015a23204"
OLD_PACKET_COUNT = 173802
OLD_MANIFEST = Path(
    "benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v2/"
    "r3_2c8fca90/mpi1/raw/canonical/mapped_solution.manifest.json"
)
OLD_SHARD_FILENAME = "mapped_solution.rank0000.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _write_json(path: Path, value: Any) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _source_facts(root: Path, source_sha: str, input_path: Path) -> dict[str, Any]:
    if len(source_sha) != 40 or any(char not in "0123456789abcdef" for char in source_sha):
        raise ValueError("source SHA must be a complete lowercase Git SHA")
    input_path = _absolute(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"input file does not exist: {input_path}")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream_sha = _git(root, "rev-parse", "@{upstream}")
    counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    expected_upstream = f"origin/{BRANCH}"
    if (
        branch != BRANCH
        or head != source_sha
        or upstream != expected_upstream
        or upstream_sha != source_sha
        or counts != ["0", "0"]
        or status
    ):
        raise RuntimeError(
            "source identity is not the clean reviewed checkout: "
            f"branch={branch!r}, head={head!r}, upstream={upstream!r}, "
            f"upstream_sha={upstream_sha!r}, counts={counts!r}, status={status!r}"
        )
    executable = Path(sys.executable)
    prefix = Path(sys.prefix)
    expected_executable = root / ".venv" / "bin" / "python"
    if (
        os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1"
        or executable.resolve() != expected_executable.resolve()
        or prefix.resolve() != (root / ".venv").resolve()
    ):
        raise RuntimeError("qualified lexical checkout Python is required")
    input_sha = sha256_file(input_path)
    if input_sha != INPUT_SHA256:
        raise RuntimeError("input identity is not the frozen Task038 template")
    return {
        "commit_sha": head,
        "branch": branch,
        "upstream": upstream,
        "upstream_sha": upstream_sha,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
        "python_executable": str(executable),
        "python_prefix": str(prefix),
        "input_path": str(input_path),
        "input_sha256": input_sha,
    }


def _runtime_facts(comm: Any, petsc: Any, expected_size: int) -> dict[str, Any]:
    import importlib
    import numpy as np
    if int(comm.size) != int(expected_size):
        raise RuntimeError(f"MPI size mismatch: {comm.size} != {expected_size}")
    if np.dtype(petsc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("PETSc ScalarType must be complex128")
    if np.dtype(petsc.IntType) != np.dtype(np.int32):
        raise RuntimeError("PETSc IntType must be int32")
    threads = {
        name: os.environ.get(name, "1")
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if any(value != "1" for value in threads.values()):
        raise RuntimeError("all BLAS/OpenMP thread settings must be one")
    modules = {}
    for name in ("mpi4py", "petsc4py", "slepc4py", "dolfinx", "basix"):
        module = importlib.import_module(name)
        modules[name] = str(Path(module.__file__).resolve())
    return {
        "mpi_size": int(comm.size),
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": threads,
        "abi_modules": modules,
    }


def _prepare_parent_root(root: Path) -> tuple[Path, Path]:
    root = _absolute(root)
    if root.exists() or (root / "jit_cache").exists():
        raise FileExistsError(f"fresh artifact root already exists: {root}")
    if not root.parent.is_dir():
        raise FileNotFoundError(f"artifact root parent is missing: {root.parent}")
    root.mkdir(exist_ok=False)
    cache = root / "jit_cache"
    cache.mkdir(exist_ok=False)
    return root, cache


def _prepare_worker_paths(root: Path, comm: Any) -> tuple[Path, Path]:
    root = _absolute(root)
    error = None
    if int(comm.rank) == 0:
        try:
            if not root.is_dir():
                raise FileNotFoundError(f"parent root is missing: {root}")
            raw = root / "raw"
            markers = root / "markers"
            if raw.exists() or markers.exists():
                raise FileExistsError("worker raw/markers path already exists")
            raw.mkdir(exist_ok=False)
            markers.mkdir(exist_ok=False)
        except (FileExistsError, FileNotFoundError, OSError) as exc:
            error = str(exc)
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(error)
    comm.barrier()
    return root / "raw", root / "markers"


def _cache_snapshot(cache: Path) -> dict[str, Any]:
    manifest = cache_manifest(cache)
    return {
        "artifact_count": int(manifest["artifact_count"]),
        "manifest_sha256": hashlib.sha256(
            json.dumps(
                manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest(),
    }


def _sample_parent(stage: str, exit_code: int | None = None) -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import cgroup_snapshot, vmstat_swap_pages

    snapshot = process_tree_snapshot(os.getpid(), stage, exit_code=exit_code)
    cgroup = cgroup_snapshot(os.getpid())
    snapshot_rss = snapshot["rss_bytes"]
    dedicated_current = (
        cgroup["memory_current_bytes"]
        if cgroup["dedicated_job_cgroup"]
        else None
    )
    if snapshot_rss is None and dedicated_current is None:
        memory_authority = None
    elif snapshot_rss is None:
        memory_authority = int(dedicated_current)
    elif dedicated_current is None:
        memory_authority = int(snapshot_rss)
    else:
        memory_authority = max(int(snapshot_rss), int(dedicated_current))
    dedicated_swap = (
        cgroup["swap_current_bytes"]
        if cgroup["dedicated_job_cgroup"]
        else None
    )
    job_no_swap = bool(
        snapshot["all_status_readable"]
        and snapshot["swap_bytes"] == 0
        and (dedicated_swap is None or dedicated_swap == 0)
    )
    authority = {
        "process_tree": snapshot,
        "job_cgroup": cgroup,
        "wsl_vm_global_swap_diagnostic": vmstat_swap_pages(),
        "memory_authority_bytes": memory_authority,
        "memory_authority_semantics": (
            "max(process-tree RSS, dedicated job cgroup memory.current when present)"
        ),
        "job_no_swap": job_no_swap,
        "formal_swap_semantics": (
            "process-tree VmSwap plus dedicated job cgroup swap; WSL-global pswp is diagnostic only"
        ),
        "mumps_ooc_is_swap": False,
        "windows_pagefile_is_linux_swap": False,
    }
    sample = {
        "schema": PROCESS_SCHEMA,
        "root_pid": os.getpid(),
        "stage": stage,
        "timestamp_ns": time.time_ns(),
        "exit_code": exit_code,
        "rss_bytes": authority["memory_authority_bytes"],
        "swap_bytes": snapshot["swap_bytes"],
        "all_status_readable": bool(snapshot["all_status_readable"]),
        "job_no_swap": bool(authority["job_no_swap"]),
        "compiler_descendant_count": int(snapshot["compiler_descendant_count"]),
        "members": snapshot["members"],
        "authority": authority,
    }
    return sample


def _sample_effectively_readable(sample: dict[str, Any]) -> bool:
    observed_code = sample.get("worker_exit_code_observed_after_sample")
    return sample.get("all_status_readable") is True or (
        sample.get("all_status_readable") is False
        and sample.get("process_tree_exit_race_observed") is True
        and type(observed_code) is int
        and observed_code == 0
    )


def _process_group_gone(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _run_parent_child(
    command: list[str],
    sample_path: Path,
    stage: str,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    peak = 0
    max_swap = 0
    sample_count = 0
    all_readable = True
    warning_crossed = False
    stop_reason = None
    signals: list[str] = []
    term_sent = False
    kill_sent = False
    process_group_gone = False
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        while True:
            sample = _sample_parent(stage)
            sample_count += 1
            observed_exit_code = process.poll()
            if (
                sample["all_status_readable"] is False
                and type(observed_exit_code) is int
                and observed_exit_code == 0
            ):
                sample["process_tree_exit_race_observed"] = True
                sample["worker_exit_code_observed_after_sample"] = 0
            append_jsonl(sample_path, sample)
            if sample["rss_bytes"] is not None:
                peak = max(peak, int(sample["rss_bytes"]))
            if sample["swap_bytes"] is not None:
                max_swap = max(max_swap, int(sample["swap_bytes"]))
            all_readable = all_readable and _sample_effectively_readable(sample)
            warning_crossed = warning_crossed or peak >= RSS_WARNING
            if not all_readable:
                stop_reason = "authority_unreadable"
            elif max_swap:
                stop_reason = "process_tree_swap"
            elif peak >= RSS_WATCHDOG:
                stop_reason = "process_tree_rss_watchdog"
            if stop_reason is not None and process.poll() is None and not term_sent:
                os.killpg(process.pid, signal.SIGTERM)
                signals.append("SIGTERM")
                term_sent = True
            if stop_reason is not None and term_sent:
                try:
                    returncode = process.wait(timeout=TERMINATION_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    signals.append("SIGKILL")
                    kill_sent = True
                    returncode = process.wait()
                break
            if process.poll() is not None:
                break
            time.sleep(POLL_SECONDS)
        returncode = int(process.wait()) if process.poll() is None else int(process.returncode)
        append_jsonl(
            sample_path,
            _sample_parent(stage, exit_code=int(returncode)),
        )
        deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
        while not process_group_gone and time.monotonic() < deadline:
            process_group_gone = _process_group_gone(process.pid)
            if not process_group_gone:
                time.sleep(POLL_SECONDS)
        if not process_group_gone and not kill_sent:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                signals.append("SIGKILL")
                kill_sent = True
            except ProcessLookupError:
                process_group_gone = True
            else:
                process.wait()
                process_group_gone = _process_group_gone(process.pid)
                deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
                while not process_group_gone and time.monotonic() < deadline:
                    process_group_gone = _process_group_gone(process.pid)
                    if not process_group_gone:
                        time.sleep(POLL_SECONDS)
    return {
        "stage": stage,
        "argv": [str(value) for value in command],
        "returncode": int(returncode),
        "stop_reason": stop_reason,
        "signals": signals,
        "sample_count": sample_count,
        "peak_rss_bytes": peak,
        "max_swap_bytes": max_swap,
        "all_status_readable": all_readable,
        "process_group_gone": process_group_gone,
        "lifecycle_failure": not process_group_gone,
        "warning_crossed": warning_crossed,
    }


def _worker_marker(
    comm: Any, marker_dir: Path, name: str, source_sha: str, **facts: Any
) -> None:
    if int(comm.rank) == 0:
        write_marker(
            marker_dir,
            name,
            {
                "phase": PHASE,
                "workflow": WORKFLOW,
                "source_sha": source_sha,
                "mpi_size": facts.pop("mpi_size", None),
                **facts,
            },
            order=MARKER_ORDER,
            schema=MARKER_SCHEMA,
        )
    comm.barrier()


def _array_sha(values: Any) -> str:
    import numpy as np
    array = np.asarray(values, dtype=np.complex128)
    if not array.flags.c_contiguous:
        array = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _update_packet_digest(digest: Any, key: Any, value: Any) -> None:
    from benchmarks.canonical_vector_artifacts import canonical_key_json_bytes
    digest.update(canonical_key_json_bytes(key))
    coefficient = complex(value)
    digest.update(
        json.dumps(
            [float(coefficient.real), float(coefficient.imag)],
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    )


def _packet_digest(packets: Any) -> str:
    digest = hashlib.sha256()
    for key, value in packets:
        _update_packet_digest(digest, key, value)
    return digest.hexdigest()


def _owned_slave_facts(vector: Any, mpc: Any, comm: Any) -> dict[str, Any]:
    from mpi4py import MPI
    import numpy as np
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    index_map = mpc.function_space.dofmap.index_map
    local_size = int(index_map.size_local) * int(mpc.function_space.dofmap.index_map_bs)
    slaves = np.asarray(mpc.slaves, dtype=np.int64).reshape(-1)
    owned = slaves[(slaves >= 0) & (slaves < local_size)]
    local_max = float(np.max(np.abs(values[owned]))) if owned.size else 0.0
    local_count = int(np.count_nonzero(np.abs(values[owned]) != 0.0)) if owned.size else 0
    return {
        "owned_slave_max": float(comm.allreduce(local_max, op=MPI.MAX)),
        "owned_slave_count": int(comm.allreduce(local_count, op=MPI.SUM)),
        "finite": bool(
            comm.allreduce(bool(np.all(np.isfinite(values))), op=MPI.LAND)
        ),
        "norm": float(vector.norm()),
        "array_sha256": _array_sha(values),
    }


def _packet_relative(left: Any, right: Any, comm: Any) -> float:
    left_map: dict[Any, complex] = {}
    right_map: dict[Any, complex] = {}
    for key, value in left:
        if key in left_map:
            raise RuntimeError("duplicate canonical packet key")
        left_map[key] = complex(value)
    for key, value in right:
        if key in right_map:
            raise RuntimeError("duplicate canonical packet key")
        right_map[key] = complex(value)
    if set(left_map) != set(right_map):
        raise RuntimeError("canonical packet key closure failed")
    local_num = sum(abs(left_map[key] - right_map[key]) ** 2 for key in left_map)
    local_den = sum(abs(right_map[key]) ** 2 for key in right_map)
    numerator = comm.allreduce(float(local_num))
    denominator = comm.allreduce(float(local_den))
    return float((numerator / max(denominator, 1.0e-300)) ** 0.5)


def _write_r3_manifest(
    raw_dir: Path, packets: Any, audit: dict[str, Any], comm: Any
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    canonical_dir = raw_dir / "canonical"
    canonical_dir.mkdir(exist_ok=True)
    shard_path = canonical_dir / f"r3.rank{int(comm.rank):04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shard["rank"] = int(comm.rank)
    shard_rows = comm.gather(shard, root=0)
    manifest_path = canonical_dir / "r3.manifest.json"
    descriptor = None
    if int(comm.rank) == 0:
        manifest = canonical_shard_manifest(
            role="full_fe_dual",
            mpi_size=int(comm.size),
            shard_metadata=shard_rows,
            extractor_audit={
                **audit,
                "source": "build_r3_long_tail_derived_probe",
            },
        )
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "manifest_relative_path": manifest_path.relative_to(raw_dir.parent).as_posix(),
            "manifest_sha256": manifest_sha,
            "role": "full_fe_dual",
            "packet_count": int(manifest["global_summed_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def run_worker(
    root: Path, record_path: Path, source_sha: str, input_path: Path, expected_size: int
) -> None:
    root = _absolute(root)
    cache_dir = root / "jit_cache"
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"parent-created cache is missing: {cache_dir}")
    cache_facts = {
        "xdg_cache_home": str(Path(os.environ["XDG_CACHE_HOME"]).resolve()),
    }
    cache_facts["binding"] = cache_facts["xdg_cache_home"] == str(cache_dir.resolve())
    if not cache_facts["binding"]:
        raise RuntimeError("worker XDG_CACHE_HOME is not the parent-owned jit_cache")
    from mpi4py import MPI
    from petsc4py import PETSc
    comm = MPI.COMM_WORLD
    source = _source_facts(REPO_ROOT, source_sha, input_path)
    raw_dir, marker_dir = _prepare_worker_paths(root, comm)
    record_path = _absolute(record_path)
    if record_path != raw_dir / "worker_record.json":
        raise ValueError("worker record must be raw/worker_record.json")
    _worker_marker(
        comm,
        marker_dir,
        "paths_ready",
        source_sha,
        mpi_size=int(comm.size),
        cache=cache_facts,
    )
    runtime = _runtime_facts(comm, PETSc, expected_size)
    _worker_marker(
        comm, marker_dir, "abi_ready", source_sha, mpi_size=int(comm.size), runtime=runtime
    )
    h10_mesh_data = None
    h10_raw_space = None
    h10_floquet = None
    historical_field = None
    case = None
    bridge = None
    probe_first = None
    probe_second = None
    try:
        from benchmarks.canonical_vector_artifacts import (
            read_canonical_manifest_metadata,
            read_selected_canonical_packet_shard,
        )
        from benchmarks.run_task038_full3d_r3 import _current_input
        from src.constraints.floquet_3d import build_double_floquet_mpc
        from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
        from src.solvers.common_3d_solve import _create_nedelec_space
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        from src.solvers.fullspace_same_mesh_physical_pcoarse import (
            build_r3_long_tail_derived_probe,
            build_small_same_mesh_physical_pcoarse_case,
            destroy_small_same_mesh_physical_pcoarse_case,
        )
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            build_nonmatching_hcurl_primal_bridge,
            destroy_nonmatching_hcurl_primal_bridge,
            extract_canonical_full_fe_packets,
            extract_canonical_full_fe_dual_packets,
            iter_canonical_full_fe_packets,
            reconstruct_canonical_full_fe_function,
        )
        from dolfinx import fem
        import numpy as np
        _specification, cfg10, _resolved, input_facts = _current_input(
            REPO_ROOT, _absolute(input_path)
        )
        modes10, _rows10, mode_sha10 = build_dynamic_mode_inventory(cfg10)
        if len(modes10) != 80 or str(mode_sha10) != MODE_MANIFEST_SHA256:
            raise RuntimeError("old authority mode inventory identity changed")
        del modes10, _rows10
        manifest_path = REPO_ROOT / OLD_MANIFEST
        manifest = read_canonical_manifest_metadata(manifest_path, OLD_MANIFEST_SHA256)
        if (
            manifest["role"] != "full_fe"
            or int(manifest["mpi_size"]) != 1
            or int(manifest["global_summed_packet_count"]) != OLD_PACKET_COUNT
            or len(manifest["per_rank_shards"]) != 1
            or manifest["per_rank_shards"][0]["filename"] != OLD_SHARD_FILENAME
            or manifest["per_rank_shards"][0]["file_sha256"] != OLD_SHARD_SHA256
        ):
            raise RuntimeError("old full-FE authority manifest does not match the frozen contract")
        h10_mesh_data = build_airbox_mesh_3d(cfg10, raw_dir / "h10_mesh")
        h10_raw_space = _create_nedelec_space(h10_mesh_data.mesh, cfg10)
        h10_floquet = build_double_floquet_mpc(h10_raw_space, h10_mesh_data, cfg10)
        h10_space = h10_floquet.mpc.function_space
        zero = fem.Function(h10_space)
        zero.x.array[:] = 0.0 + 0.0j
        zero.x.scatter_forward()
        wanted_keys = tuple(
            key for key, _ in iter_canonical_full_fe_packets(
                h10_space, zero.x.petsc_vec, h10_floquet
            )
        )
        expected_key_count = len(wanted_keys)
        del zero
        shard_path = manifest_path.parent / OLD_SHARD_FILENAME
        selected_packets, selected_facts = read_selected_canonical_packet_shard(
            shard_path, wanted_keys, OLD_SHARD_SHA256
        )
        del wanted_keys
        if (
            int(selected_facts["selected_packet_count"]) != expected_key_count
            or not selected_facts["finite"]
        ):
            raise RuntimeError("old authority selected packet closure failed")
        selected_before_digest = _packet_digest(selected_packets)
        _worker_marker(
            comm,
            marker_dir,
            "old_authority_streamed",
            source_sha,
            mpi_size=int(comm.size),
            manifest_sha256=OLD_MANIFEST_SHA256,
            shard_sha256=OLD_SHARD_SHA256,
        )
        historical_field = reconstruct_canonical_full_fe_function(
            h10_space, selected_packets, h10_floquet
        )
        reference = {key: complex(value) for key, value in selected_packets}
        first_digest = hashlib.sha256()
        first_count = 0
        first_finite = True
        local_difference = 0.0
        local_reference_norm = 0.0
        for key, value in iter_canonical_full_fe_packets(
            h10_space, historical_field.x.petsc_vec, h10_floquet
        ):
            if key not in reference:
                raise RuntimeError("h10 canonical key closure failed")
            coefficient = complex(value)
            first_finite = first_finite and np.isfinite(
                coefficient.real
            ) and np.isfinite(coefficient.imag)
            _update_packet_digest(first_digest, key, coefficient)
            reference_value = reference.pop(key)
            local_difference += abs(coefficient - reference_value) ** 2
            local_reference_norm += abs(reference_value) ** 2
            first_count += 1
        if reference:
            raise RuntimeError("h10 reconstructed canonical keys are incomplete")
        first_digest_value = first_digest.hexdigest()
        second_digest = hashlib.sha256()
        second_count = 0
        second_finite = True
        for key, value in iter_canonical_full_fe_packets(
            h10_space, historical_field.x.petsc_vec, h10_floquet
        ):
            coefficient = complex(value)
            second_finite = second_finite and np.isfinite(
                coefficient.real
            ) and np.isfinite(coefficient.imag)
            _update_packet_digest(second_digest, key, coefficient)
            second_count += 1
        second_digest_value = second_digest.hexdigest()
        if first_digest_value != second_digest_value or first_count != second_count:
            raise RuntimeError("h10 repeated canonical extraction differs")
        difference = comm.allreduce(float(local_difference), op=MPI.SUM)
        reference_norm = comm.allreduce(float(local_reference_norm), op=MPI.SUM)
        reconstruction_relative = float(
            (difference / max(reference_norm, np.finfo(np.float64).tiny)) ** 0.5
        )
        extracted_finite = bool(comm.allreduce(bool(first_finite), op=MPI.LAND))
        selected_after_digest = _packet_digest(selected_packets)
        selected_key_count_global = int(
            comm.allreduce(len(selected_packets), op=MPI.SUM)
        )
        extracted_key_count_global = int(comm.allreduce(first_count, op=MPI.SUM))
        extraction_repeat_finite = bool(comm.allreduce(bool(second_finite), op=MPI.LAND))
        h10_input_unchanged = bool(
            comm.allreduce(selected_before_digest == selected_after_digest, op=MPI.LAND)
        )
        if not extracted_finite or not extraction_repeat_finite or not h10_input_unchanged:
            raise RuntimeError("h10 extraction finite/input closure failed")
        h10_facts = {
            "selected_key_count": selected_key_count_global,
            "extracted_key_count": extracted_key_count_global,
            "selected_finite": bool(selected_facts["finite"]),
            "extracted_finite": extracted_finite,
            "extraction_repeat_finite": extraction_repeat_finite,
            "reconstruction_relative_l2": reconstruction_relative,
            "extraction_repeat_relative_l2": 0.0,
            "input_before_digest": selected_before_digest,
            "input_after_digest": selected_after_digest,
            "input_unchanged": h10_input_unchanged,
            "extraction_digest": first_digest_value,
            "extraction_repeat_digest": second_digest_value,
            "source_role": "full_fe",
            "canonical_role": "full_fe",
        }
        del (
            reference,
            first_digest,
            second_digest,
            selected_facts,
        )
        _worker_marker(
            comm,
            marker_dir,
            "h10_reconstructed",
            source_sha,
            mpi_size=int(comm.size),
            reconstruction_relative_l2=reconstruction_relative,
            extraction_repeat_relative_l2=h10_facts["extraction_repeat_relative_l2"],
        )
        cfg50 = copy.deepcopy(cfg10)
        cfg50.mesh_target_size = 50.0
        modes50, _rows50, mode_sha50 = build_dynamic_mode_inventory(cfg50)
        if len(modes50) != 80 or str(mode_sha50) != MODE_MANIFEST_SHA256:
            raise RuntimeError("target h50 mode inventory identity changed")
        target_mode_facts = {
            "mode_count": len(modes50),
            "mode_manifest_sha256": str(mode_sha50),
        }
        del modes50, _rows50
        del _specification, _resolved, cfg10
        case = build_small_same_mesh_physical_pcoarse_case(cfg50, comm)
        target_space = case["setup"]["spaces"][6]
        target_floquet = case["setup"]["floquets"][6]
        source_before_sha = _array_sha(historical_field.x.array)
        bridge = build_nonmatching_hcurl_primal_bridge(
            historical_field, target_space, target_floquet, padding=1.0e-10
        )
        source_after_sha = _array_sha(historical_field.x.array)
        action_facts = _owned_slave_facts(
            bridge["action_vector"], target_floquet.mpc, comm
        )
        canonical_packets, canonical_audit = extract_canonical_full_fe_packets(
            target_space,
            bridge["canonical_field"].x.petsc_vec,
            target_floquet,
        )
        canonical_local_finite = all(
            np.isfinite(complex(value).real) and np.isfinite(complex(value).imag)
            for _key, value in canonical_packets
        )
        canonical_field_facts = {
            "finite": bool(comm.allreduce(bool(canonical_local_finite), op=MPI.LAND)),
            "norm": float(bridge["canonical_field"].x.petsc_vec.norm()),
            "packet_count": len(canonical_packets),
            "canonical_role": str(canonical_audit["role"]),
            "array_sha256": _array_sha(bridge["canonical_field"].x.array),
        }
        _worker_marker(
            comm,
            marker_dir,
            "h50_bridged",
            source_sha,
            mpi_size=int(comm.size),
            bridge_audit=bridge["audit"],
            source_before_sha256=source_before_sha,
            source_after_sha256=source_after_sha,
        )
        source_input_unchanged = bool(
            comm.allreduce(source_before_sha == source_after_sha, op=MPI.LAND)
        )
        del canonical_packets, selected_packets
        del historical_field, h10_floquet, h10_raw_space, h10_mesh_data
        historical_field = None
        h10_floquet = None
        h10_raw_space = None
        h10_mesh_data = None
        gc.collect()
        _worker_marker(comm, marker_dir, "h10_released", source_sha, mpi_size=int(comm.size))
        action_before_sha = action_facts["array_sha256"]
        probe_first, r3_facts = build_r3_long_tail_derived_probe(case, bridge["action_vector"])
        action_after_first_sha = _array_sha(bridge["action_vector"].getArray(readonly=True))
        probe_second, _r3_repeat_facts = build_r3_long_tail_derived_probe(
            case, bridge["action_vector"]
        )
        action_after_second_sha = _array_sha(bridge["action_vector"].getArray(readonly=True))
        packets_first, dual_audit = extract_canonical_full_fe_dual_packets(
            case["setup"]["spaces"][3], case["setup"]["floquets"][3].mpc, probe_first
        )
        packets_second, _ = extract_canonical_full_fe_dual_packets(
            case["setup"]["spaces"][3], case["setup"]["floquets"][3].mpc, probe_second
        )
        r3_repeat_relative = _packet_relative(packets_first, packets_second, comm)
        r3_norm = float(probe_first.norm())
        r3_slave = _owned_slave_facts(probe_first, case["setup"]["floquets"][3].mpc, comm)
        r3_packets_finite_local = all(
            np.isfinite(complex(value).real) and np.isfinite(complex(value).imag)
            for packets in (packets_first, packets_second)
            for _key, value in packets
        )
        r3_packet_finite = bool(
            comm.allreduce(
                r3_packets_finite_local and bool(r3_slave["finite"]),
                op=MPI.LAND,
            )
        )
        r3_input_unchanged = bool(
            comm.allreduce(
                action_before_sha == action_after_first_sha == action_after_second_sha,
                op=MPI.LAND,
            )
        )
        r3_manifest = _write_r3_manifest(raw_dir, packets_first, dual_audit, comm)
        del packets_first, packets_second
        r3_record_facts = {
            "schema": str(r3_facts["schema"]),
            "name": str(r3_facts["name"]),
            "formula": str(r3_facts["formula"]),
            "mapped_primal_authority_role": str(r3_facts["mapped_primal_authority_role"]),
            "mapped_primal_action_storage": str(r3_facts["mapped_primal_action_storage"]),
            "residual_role": str(r3_facts["residual_role"]),
            "probe_role": str(r3_facts["probe_role"]),
            "apply_count": 2,
            "repeat_relative_l2": r3_repeat_relative,
            "input_unchanged": r3_input_unchanged,
            "finite": r3_packet_finite,
            "owned_slave_max": float(r3_slave["owned_slave_max"]),
            "norm": r3_norm,
            "physical_rhs_facts": dict(r3_facts["physical_rhs_facts"]),
            "action_input_before_sha256": action_before_sha,
            "action_input_after_first_sha256": action_after_first_sha,
            "action_input_after_second_sha256": action_after_second_sha,
            "manifest": r3_manifest,
        }
        _worker_marker(
            comm,
            marker_dir,
            "r3_ready",
            source_sha,
            mpi_size=int(comm.size),
            packet_count=int(r3_manifest["packet_count"]),
            repeat_relative_l2=r3_repeat_relative,
        )
        if comm.rank == 0:
            worker_record = {
                "schema": WORKER_SCHEMA,
                "raw_facts_only": True,
                "source": source,
                "runtime": runtime,
                "input": input_facts,
                "cache": cache_facts,
                "target_mode": target_mode_facts,
                "paths": {
                    "cache_dir": "jit_cache",
                    "record": "raw/worker_record.json",
                },
                "old_authority": {
                    "source_sha": OLD_SOURCE_SHA,
                    "manifest_relative_path": OLD_MANIFEST.as_posix(),
                    "manifest_sha256": OLD_MANIFEST_SHA256,
                    "shard_filename": OLD_SHARD_FILENAME,
                    "shard_sha256": OLD_SHARD_SHA256,
                    "packet_count": OLD_PACKET_COUNT,
                    "h10": h10_facts,
                },
                "h50_bridge": {
                    "source_input_unchanged": source_input_unchanged,
                    "source_before_sha256": source_before_sha,
                    "source_after_sha256": source_after_sha,
                    "action_vector": {
                        "role": "fullspace_slave_zero",
                        **action_facts,
                    },
                    "canonical_field": canonical_field_facts,
                    "bridge_audit": bridge["audit"],
                },
                "r3": r3_record_facts,
            }
            _write_json(record_path, worker_record)
        _worker_marker(comm, marker_dir, "record_written", source_sha, mpi_size=int(comm.size))
    finally:
        if probe_second is not None:
            probe_second.destroy()
        if probe_first is not None:
            probe_first.destroy()
        if bridge is not None:
            destroy_nonmatching_hcurl_primal_bridge(bridge)
        if case is not None:
            destroy_small_same_mesh_physical_pcoarse_case(case)
        gc.collect()


def _child_command(
    group: str, cache: Path, record: Path, source_sha: str, input_path: Path
) -> list[str]:
    return [
        str(Path(sys.executable)),
        "-m",
        "benchmarks.run_task038_full3d_jit_precompile",
        "--group",
        group,
        "--cache-dir",
        str(cache),
        "--record",
        str(record),
        "--expected-source-sha",
        source_sha,
        "--input",
        str(input_path),
    ]


def _worker_command(
    root: Path, record: Path, source_sha: str, input_path: Path, size: int
) -> list[str]:
    return [
        "mpiexec",
        "-n",
        str(size),
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
        str(size),
    ]


def _process_summary(path: Path) -> dict[str, Any]:
    count = 0
    peak = 0
    swap = 0
    readable = True
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            sample = json.loads(line)
            count += 1
            if sample["rss_bytes"] is not None:
                peak = max(peak, int(sample["rss_bytes"]))
            if sample["swap_bytes"] is not None:
                swap = max(swap, int(sample["swap_bytes"]))
            readable = readable and _sample_effectively_readable(sample)
    return {
        "sample_count": count,
        "peak_rss_bytes": peak,
        "max_swap_bytes": swap,
        "all_status_readable": readable,
    }


def run_parent(
    root: Path, record_path: Path, source_sha: str, input_path: Path, expected_size: int
) -> int:
    root, cache = _prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("parent record must be directly below artifact root")
    children_dir = root / "children"
    children_dir.mkdir(exist_ok=False)
    sample_path = root / "parent_process.jsonl"
    source = _source_facts(REPO_ROOT, source_sha, input_path)
    children: list[dict[str, Any]] = []
    worker_result = None
    error = None
    cache_initial = _cache_snapshot(cache)
    cache_before_worker = None
    cache_after_worker = None
    try:
        for index, group in enumerate(JIT_GROUPS):
            child_record = children_dir / f"{index:02d}_{group.replace('-', '_')}.json"
            result = _run_parent_child(
                _child_command(group, cache, child_record, source_sha, _absolute(input_path)),
                sample_path,
                f"precompile:{group}",
                children_dir / f"{index:02d}_{group.replace('-', '_')}.stdout.log",
                children_dir / f"{index:02d}_{group.replace('-', '_')}.stderr.log",
            )
            result.update(
                {
                    "group": group,
                }
            )
            children.append(result)
            if (
                result["returncode"] != 0
                or result["stop_reason"] is not None
                or not result["process_group_gone"]
            ):
                raise RuntimeError(f"precompile child lifecycle failed: {group}")
        cache_before_worker = _cache_snapshot(cache)
        worker_record = root / "raw" / "worker_record.json"
        worker_result = _run_parent_child(
            _worker_command(root, worker_record, source_sha, _absolute(input_path), expected_size),
            sample_path,
            "worker",
            root / "worker.stdout.log",
            root / "worker.stderr.log",
        )
        cache_after_worker = _cache_snapshot(cache)
        if (
            worker_result["returncode"] != 0
            or worker_result["stop_reason"] is not None
            or not worker_result["process_group_gone"]
        ):
            raise RuntimeError("source-authority worker failed")
        if cache_before_worker != cache_after_worker:
            raise RuntimeError("worker changed the parent-owned JIT cache")
    except Exception as exc:
        error = str(exc)
    process = _process_summary(sample_path) if sample_path.is_file() else None
    worker_record = root / "raw" / "worker_record.json"
    marker_dir = root / "markers"
    marker_manifest_path = root / "marker_manifest.json"
    marker_rows = []
    if marker_dir.is_dir():
        for path in marker_files(marker_dir, order=MARKER_ORDER):
            marker_rows.append({"name": path.stem.split("_", 1)[1], "sha256": sha256_file(path)})
    if marker_rows and not marker_manifest_path.exists():
        _write_json(marker_manifest_path, marker_rows)
    worker_cache = (
        json.loads(worker_record.read_text(encoding="utf-8")).get("cache")
        if worker_record.is_file()
        else None
    )
    parent_record = {
        "schema": PARENT_SCHEMA,
        "source": source,
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
        "children": children,
        "cache": {
            "initial": cache_initial,
            "before_worker": cache_before_worker,
            "after_worker": cache_after_worker,
            "worker_binding": worker_cache,
        },
        "process": process,
        "worker": (
            None
            if worker_result is None
            else {
                **worker_result,
                "record_present": worker_record.is_file(),
                "record_sha256": (
                    sha256_file(worker_record) if worker_record.is_file() else None
                ),
                "stdout_sha256": (
                    sha256_file(root / "worker.stdout.log")
                    if (root / "worker.stdout.log").is_file()
                    else None
                ),
                "stderr_sha256": (
                    sha256_file(root / "worker.stderr.log")
                    if (root / "worker.stderr.log").is_file()
                    else None
                ),
            }
        ),
        "markers": (
            None
            if not marker_manifest_path.is_file()
            else {
                "manifest_relative_path": "marker_manifest.json",
                "manifest_sha256": sha256_file(marker_manifest_path),
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
    try:
        if args.mode == "parent":
            return run_parent(root, record, args.source_sha, input_path, args.mpi_size)
        run_worker(root, record, args.source_sha, input_path, args.mpi_size)
        return 0
    except Exception as error:
        print(f"Q1 source-authority execution failed: {error}", file=sys.stderr, flush=True)
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
