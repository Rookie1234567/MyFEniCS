"""Thin M6A stage/worker/watchdog/checker route for the matrix-free DtN core.

The controller imports only the standard library.  DOLFINx, PETSc, MPI, and
the surface-form code are imported inside the stage/worker paths so that
source, command, and raw-evidence checks remain usable without constructing a
finite-element object.  The worker writes owner-local arrays and canonical
shards; the checker is the only code here that assembles full offline
comparison arrays from those shards.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
M6A_SCHEMA = "task037.extra.m6a.v1"
M6A_STAGE_SCHEMA = f"{M6A_SCHEMA}.stage"
M6A_WORKER_SCHEMA = f"{M6A_SCHEMA}.worker"
M6A_WATCHDOG_SCHEMA = f"{M6A_SCHEMA}.watchdog"
M6A_CHECK_SCHEMA = f"{M6A_SCHEMA}.check"

M6A_DEGREE = 6
M6A_H_NM = 10.0
M6A_GLOBAL_CELLS = 252
M6A_LOCAL_NLOC = 882
M6A_GLOBAL_ROWS = 173_802
M6A_CONSTRAINTS = 9_210
M6A_MODE_COUNT = 80
M6A_TIMEOUT_SECONDS = 1_800.0
M6A_RSS_LIMIT_BYTES = 1_950_000_000
M6A_SWAP_LIMIT_BYTES = 0
M6A_RETAINED_WORK_LIMIT_BYTES = 150_000_000
M6A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6A_PREDICTED_LIVE_SET_BYTES = 636_989_440 + 150_000_000 + 32_000_000 + 64_000_000

M6A_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "modes_ready",
    "surface_cache_ready",
    "carrier_ready",
    "source_ready",
    "candidate_ready",
    "direct_ready",
    "rhs_ready",
    "canonical_ready",
    "summary_ready",
)
M6A_STAGE_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "modes_ready",
    "surface_cache_ready",
    "summary_ready",
)
M6A_MODE_IDENTITY_FIELDS = (
    "schema",
    "mode_index",
    "side",
    "m",
    "n",
    "polarization",
    "alpha",
    "gamma",
    "beta",
    "k_vector",
    "e_vector",
    "power_per_unit_amplitude",
    "rayleigh_warning",
    "projection_denominator",
    "traction_vector",
    "refractive_index",
    "vertical_sign",
    "h_vector",
    "electric_tangential_norm_sq",
    "propagating",
)

_HEX = frozenset("0123456789abcdef")
_ARRAY_RECORD_KEYS = frozenset(
    {
        "path",
        "present",
        "bytes",
        "sha256",
        "array_sha256",
        "shape",
        "dtype",
        "rank",
        "ownership_range",
    }
)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _attach_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("evidence_sha256", None)
    result["evidence_sha256"] = hashlib.sha256(_canonical_json(result)).hexdigest()
    return result


def _evidence_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    observed = value.get("evidence_sha256")
    return (
        isinstance(observed, str)
        and len(observed) == 64
        and observed == observed.lower()
        and set(observed) <= _HEX
        and observed == _attach_evidence(value).get("evidence_sha256")
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _artifact(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {"path": relative, "present": False}
    return {
        "path": relative,
        "present": True,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
    }


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _source_valid(value: Any) -> bool:
    required = {
        "source_commit_full_sha",
        "tracked_source_dirty",
        "source_worktree_dirty",
        "nonignored_untracked_paths",
        "worktree_status_porcelain",
        "git_error",
    }
    return bool(
        isinstance(value, Mapping)
        and required <= set(value)
        and isinstance(value["source_commit_full_sha"], str)
        and len(value["source_commit_full_sha"]) == 40
        and set(value["source_commit_full_sha"]) <= _HEX
        and value["tracked_source_dirty"] is False
        and value["source_worktree_dirty"] is False
        and value["nonignored_untracked_paths"] == []
        and value["worktree_status_porcelain"] == []
        and value["git_error"] is None
    )


def _source_pair_valid(start: Any, end: Any) -> bool:
    return bool(
        _source_valid(start)
        and _source_valid(end)
        and start["source_commit_full_sha"] == end["source_commit_full_sha"]
    )


def _m6a_scope(expected_mpi_size: int | None = None, phase: str | None = None) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "degree": M6A_DEGREE,
        "h_nm": M6A_H_NM,
        "global_cells": M6A_GLOBAL_CELLS,
        "local_nloc": M6A_LOCAL_NLOC,
        "global_rows": M6A_GLOBAL_ROWS,
        "constraint_count": M6A_CONSTRAINTS,
        "mode_count": M6A_MODE_COUNT,
        "fine_space": "uncondensed_fullspace",
        "condensation": False,
        "static_condensed_operator": False,
        "trace_slab_pc": False,
        "global_matrix": False,
        "augmented_matrix": False,
        "ordinary_default": False,
        "timeout_seconds": M6A_TIMEOUT_SECONDS,
        "rss_limit_bytes": M6A_RSS_LIMIT_BYTES,
        "swap_limit_bytes": M6A_SWAP_LIMIT_BYTES,
        "retained_work_limit_bytes": M6A_RETAINED_WORK_LIMIT_BYTES,
        "predicted_live_set_bytes": M6A_PREDICTED_LIVE_SET_BYTES,
        "predicted_live_set_limit_bytes": M6A_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "predicted_live_set_is_measurement": False,
        "source_fixture": "floquet_compatible_degree5_dual_v1_as_primal",
        "output_role": "dual_load_owner_local",
        "source_role": "primal_owner_local",
    }
    if expected_mpi_size is not None:
        scope["expected_mpi_size"] = int(expected_mpi_size)
    if phase is not None:
        scope["phase"] = str(phase)
    return scope


def _mark(stream: Any, phase: str, event: str, started: float, **extra: Any) -> None:
    if stream is None:
        return
    if event not in M6A_EVENTS:
        raise ValueError(f"unknown M6A progress event: {event}")
    item = {
        "schema": f"{M6A_SCHEMA}.progress.v1",
        "phase": phase,
        "event": event,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
        **extra,
    }
    stream.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()
    print(json.dumps(item, sort_keys=True), flush=True)


def _event_order_valid(events: Sequence[str]) -> bool:
    return tuple(events) == M6A_EVENTS


def _progress_valid(path: Path, phase: str, expected: Sequence[str]) -> bool:
    """Validate the flushed JSONL markers, not a summary's copied event list."""

    observed: list[str] = []
    previous_elapsed = 0.0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            elapsed = item.get("elapsed_wall_seconds") if isinstance(item, Mapping) else None
            if (
                not isinstance(item, Mapping)
                or item.get("schema") != f"{M6A_SCHEMA}.progress.v1"
                or item.get("phase") != phase
                or not isinstance(item.get("event"), str)
                or item["event"] in observed
                or item["event"] not in expected
                or type(elapsed) not in (int, float)
                or not math.isfinite(float(elapsed))
                or float(elapsed) < 0.0
                or float(elapsed) < previous_elapsed
            ):
                return False
            observed.append(item["event"])
            previous_elapsed = float(elapsed)
        return tuple(observed) == tuple(expected)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _m6a_runtime_valid(value: Any, expected_mpi_size: int, executable: str | None = None) -> bool:
    if not isinstance(value, Mapping):
        return False
    executable_value = value.get("sys_executable")
    if not isinstance(executable_value, str) or not Path(executable_value).is_absolute():
        return False
    repo_venv = (ROOT / ".venv").resolve()
    executable_venv = Path(executable_value).parent.parent.resolve()
    paths = value.get("package_paths")
    threads = value.get("threads")
    compiler = value.get("compiler")
    required_threads = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    return bool(
        value.get("qualified_activation") == "1"
        and executable_venv == repo_venv
        and (executable is None or executable_value == str(executable))
        and value.get("petsc_scalar_type") == "complex128"
        and value.get("petsc_int_type") == "int32"
        and value.get("mpi_size") == int(expected_mpi_size)
        and value.get("linux_abi") is True
        and isinstance(compiler, Mapping)
        and isinstance(paths, Mapping)
        and all(
            isinstance(paths.get(name), str)
            and Path(paths[name]).is_absolute()
            and "/mnt/c" not in paths[name]
            and "\\\\" not in paths[name]
            for name in ("petsc4py", "slepc4py", "dolfinx", "mpi4py")
        )
        and isinstance(threads, Mapping)
        and all(threads.get(name) == "1" for name in required_threads)
    )


def _runtime_identity_by_rank_valid(
    value: Any, expected_mpi_size: int, executable: str | None = None
) -> bool:
    if not isinstance(value, list) or len(value) != int(expected_mpi_size):
        return False
    if not all(_m6a_runtime_valid(item, expected_mpi_size, executable) for item in value):
        return False
    return all(item == value[0] for item in value[1:])


def _mode_manifest_valid(run_dir: Path, record: Mapping[str, Any]) -> bool:
    if set(record) != {"path", "present", "bytes", "sha256"} or record["present"] is not True:
        return False
    relative = record["path"]
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return False
    actual = _artifact(run_dir, relative)
    if actual != dict(record) or not _valid_sha(record["sha256"]):
        return False
    try:
        payload = json.loads((run_dir / relative).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    modes = payload.get("modes") if isinstance(payload, Mapping) else None
    if not isinstance(payload, Mapping) or payload.get("schema") != "m6-fullspace-dtn-mode-manifest-v1":
        return False
    if payload.get("mode_count") != M6A_MODE_COUNT or not isinstance(modes, list) or len(modes) != M6A_MODE_COUNT:
        return False
    for index, mode in enumerate(modes):
        if not isinstance(mode, Mapping) or any(field not in mode for field in M6A_MODE_IDENTITY_FIELDS):
            return False
        if mode.get("mode_index") != index:
            return False
    return True


def _canonical_packet_role(packets: Sequence[Any], expected_packet_role: str) -> bool:
    return all(
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], tuple)
        and item[0]
        and item[0][0] == expected_packet_role
        for item in packets
    )


def _stage_allows_online(stage_process: Mapping[str, Any], stage: Mapping[str, Any], gone: bool) -> bool:
    required = ("return_code", "termination", "processes_gone", "status", "scope", "source_at_start", "source_at_end")
    if not isinstance(stage_process, Mapping) or not isinstance(stage, Mapping):
        return False
    if any(key not in stage_process for key in required[:3]) or any(key not in stage for key in required[3:]):
        return False
    return bool(
        type(stage_process["return_code"]) is int
        and stage_process["return_code"] == 0
        and stage_process["termination"] is None
        and stage_process["processes_gone"] is True
        and gone is True
        and stage["status"] == "measurement_complete"
        and _evidence_valid(stage)
        and stage["scope"] == _m6a_scope()
        and _source_pair_valid(stage["source_at_start"], stage["source_at_end"])
    )


def _worker_command(executable: str, run_dir: Path, phase: str, mpi_size: int) -> list[str]:
    if phase not in {"mpi1", "mpi2"} or int(mpi_size) not in {1, 2}:
        raise ValueError("M6A has only mpi1/mpi2 worker phases")
    return [
        "mpiexec",
        "-n",
        str(int(mpi_size)),
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_m6",
        "m6a-worker",
        "--run-dir",
        str(run_dir.resolve()),
        "--phase",
        phase,
        "--expected-mpi-size",
        str(int(mpi_size)),
    ]


def _stage_command(executable: str, run_dir: Path) -> list[str]:
    return [
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_m6",
        "m6a-stage-worker",
        "--run-dir",
        str(run_dir.resolve()),
    ]


def _h2b_module() -> Any:
    import benchmarks.run_task037_extra_h2b as h2b

    return h2b


def _worker_runtime_identity(
    comm: Any,
    h2b: Any,
    *,
    compiler_probe: bool,
    compiler: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    import dolfinx
    import mpi4py
    import petsc4py
    import slepc4py

    identity = dict(
        h2b._runtime_identity(
            h2b._lazy_h2a(), compiler_probe=compiler_probe, compiler=compiler
        )
    )
    identity.update(
        {
            "mpi_size": int(comm.size),
            "linux_abi": bool(os.name == "posix"),
            "package_paths": {
                "petsc4py": str(petsc4py.__file__),
                "slepc4py": str(slepc4py.__file__),
                "dolfinx": str(dolfinx.__file__),
                "mpi4py": str(mpi4py.__file__),
            },
        }
    )
    return identity


def _save_owned_array(
    run_dir: Path,
    name: str,
    values: Any,
    *,
    rank: int,
    ownership_range: tuple[int, int],
) -> dict[str, Any]:
    import numpy as np

    array = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ValueError(f"M6A artifact {name} must be finite complex128 1-D")
    relative = f"{name}_rank{int(rank)}.npy"
    path = run_dir / relative
    np.save(path, array, allow_pickle=False)
    contiguous = np.ascontiguousarray(array)
    return {
        **_artifact(run_dir, relative),
        "array_sha256": hashlib.sha256(memoryview(contiguous).cast("B")).hexdigest(),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "rank": int(rank),
        "ownership_range": [int(ownership_range[0]), int(ownership_range[1])],
    }


def _save_global_small_array(run_dir: Path, name: str, values: Any) -> dict[str, Any]:
    return _save_owned_array(run_dir, name, values, rank=0, ownership_range=(0, 80))


def _save_bytes_artifact(run_dir: Path, relative: str, payload: bytes) -> dict[str, Any]:
    path = run_dir / relative
    path.write_bytes(bytes(payload))
    return _artifact(run_dir, relative)


def _write_canonical_role(
    run_dir: Path,
    phase: str,
    role: str,
    packets: Iterable[Any],
    *,
    rank: int,
    mpi_size: int,
    ownership_range: tuple[int, int],
    comm: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    shard_relative = f"{phase}_{role}_rank{int(rank)}.jsonl"
    shard_metadata = write_canonical_packet_shard(run_dir / shard_relative, packets)
    shard_metadata.update(
        {
            "rank": int(rank),
            "ownership_range": [int(ownership_range[0]), int(ownership_range[1])],
        }
    )
    metadata = comm.allgather(shard_metadata)
    if rank == 0:
        manifest = canonical_shard_manifest(
            role=role,
            mpi_size=mpi_size,
            shard_metadata=metadata,
            extractor_audit={
                "source_role": "primal_owner_local" if role == "source_primal" else "dual_load_owner_local",
                "ownership_identity": "rank_shard_metadata_only",
            },
            duplicate_detection="checker_recomputed_from_shards",
        )
        manifest_relative = f"{phase}_{role}_manifest.json"
        manifest_sha = write_canonical_manifest(run_dir / manifest_relative, manifest)
        result = {"path": manifest_relative, "sha256": manifest_sha, "role": role}
    else:
        result = None
    result = comm.bcast(result, root=0)
    comm.Barrier()
    return dict(result)


def _surface_assemblers(function_space: Any, mesh_data: Any, cfg: Any, modes: Sequence[Any], cache_dir: Path) -> dict[tuple[str, int], Any]:
    from src.solvers.dtn_port_3d import (
        _ReusableSurfaceComponentAssembler,
        _dtn_surface_quadrature_degree,
    )

    degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    tags = {"top": cfg.tags.z_max, "bottom": cfg.tags.z_min}
    jit_options = _h2b_module()._expected_jit_options(cache_dir)
    return {
        (side, component): _ReusableSurfaceComponentAssembler(
            function_space,
            mesh_data,
            tags[side],
            component,
            quadrature_degree=degree,
            jit_options=jit_options,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }


def _production_objects(run_dir: Path, *, mesh_name: str) -> tuple[Any, Any, Any, Any, list[Any]]:
    from src.common.config_3d import target_stage4_config
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space

    cfg = target_stage4_config(degree=M6A_DEGREE, h_nm=M6A_H_NM)
    mesh_data = build_airbox_mesh_3d(cfg, run_dir / mesh_name)
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    modes = outgoing_port_modes_3d(cfg)
    if len(modes) != M6A_MODE_COUNT:
        raise ValueError(f"M6A requires exactly 80 outgoing modes, got {len(modes)}")
    return cfg, mesh_data, function_space, floquet, modes


def _p6_identity(mesh_data: Any, function_space: Any, floquet: Any) -> dict[str, int]:
    index_map = function_space.dofmap.index_map
    return {
        "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
        "local_cells": int(mesh_data.mesh.topology.index_map(3).size_local),
        "local_nloc": int(function_space.element.space_dimension),
        "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
        "constraint_count": int(floquet.num_constraints),
    }


def _surface_identity(cache_dir: Path, modes: Sequence[Any]) -> dict[str, Any]:
    h2b = _h2b_module()
    return {
        "component_count": 4,
        "incident_form_count": 1,
        "components": [
            {"side": side, "component": component}
            for side in ("top", "bottom")
            for component in (0, 1)
        ],
        "mode_count": len(modes),
        "jit_options": h2b._expected_jit_options(cache_dir),
        "cache_inventory": h2b._cache_snapshot(cache_dir),
    }


def _stage_worker(run_dir: Path) -> int:
    import gc
    import time as _time

    from mpi4py import MPI

    h2b = _h2b_module()
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6A stage worker must run with MPI size 1")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "m6a_stage_summary.json"
    progress_path = run_dir / "m6a_stage_progress.jsonl"
    started = _time.perf_counter()
    source_start = h2b._light_source()
    runtime = None
    runtime_identity_by_rank = None
    identity = None
    local_cells_by_rank: list[int] | None = None
    surface_identity = None
    error = None
    try:
        with (
            progress_path.open("w", encoding="utf-8")
            if comm.rank == 0
            else nullcontext()
        ) as markers:
            _mark(markers, "stage", "authority_validated", started, source_sha=source_start["source_commit_full_sha"])
            cfg, mesh_data, function_space, floquet, modes = _production_objects(run_dir, mesh_name="m6a_stage_mesh")
            _mark(markers, "stage", "mesh_ready", started)
            _mark(markers, "stage", "space_ready", started)
            _mark(markers, "stage", "floquet_mpc_ready", started)
            _mark(markers, "stage", "modes_ready", started)
            cache_dir = run_dir / "jit_cache"
            assemblers = _surface_assemblers(function_space, mesh_data, cfg, modes, cache_dir)
            from dolfinx import fem
            from src.solvers.dtn_port_3d import _incident_top_traction_form

            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=h2b._expected_jit_options(cache_dir),
            )
            del incident_form
            surface_identity = _surface_identity(cache_dir, modes)
            _mark(markers, "stage", "surface_cache_ready", started, cache_files=len(surface_identity["cache_inventory"]))
            identity = _p6_identity(mesh_data, function_space, floquet)
            expected = {
                "global_cells": M6A_GLOBAL_CELLS,
                "local_cells": M6A_GLOBAL_CELLS,
                "local_nloc": M6A_LOCAL_NLOC,
                "global_rows": M6A_GLOBAL_ROWS,
                "constraint_count": M6A_CONSTRAINTS,
            }
            if identity != expected:
                raise ValueError(f"M6A p6 identity mismatch: {identity}")
            local_cells_by_rank = [int(value) for value in comm.allgather(identity["local_cells"])]
            runtime = _worker_runtime_identity(comm, h2b, compiler_probe=True)
            runtime_identity_by_rank = comm.allgather(runtime)
            _mark(markers, "stage", "summary_ready", started)
            del assemblers, function_space, floquet, mesh_data, cfg, modes
            gc.collect()
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_end = h2b._light_source()
    status = "measurement_complete" if error is None and identity is not None else "gate_failed"
    summary = _attach_evidence(
        {
            "schema": M6A_STAGE_SCHEMA,
            "status": status,
            "scope": _m6a_scope(),
            "events": list(M6A_STAGE_EVENTS),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "runtime_identity": runtime,
            "runtime_identity_by_rank": runtime_identity_by_rank,
            "p6": identity,
            "local_cells_by_rank": local_cells_by_rank,
            "surface_forms": surface_identity,
            "error": error,
            "elapsed_wall_seconds": float(_time.perf_counter() - started),
        }
    )
    if comm.rank == 0:
        _write_json(summary_path, summary)
    comm.Barrier()
    return 0 if status == "measurement_complete" else 1


def _component_owned_values(assembler: Any, mode: Any, mpc: Any) -> Any:
    import numpy as np
    from src.solvers.dtn_port_3d import _assemble_mpc_form_vector, _set_scalar_constant

    _set_scalar_constant(assembler.alpha, mode.alpha)
    _set_scalar_constant(assembler.gamma, mode.gamma)
    _set_scalar_constant(assembler.kz, mode.k_vector[2])
    vector = _assemble_mpc_form_vector(assembler.form, mpc)
    try:
        return np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    finally:
        vector.destroy()


def _mode_phase_groups(modes: Sequence[Any]) -> tuple[tuple[tuple[Any, ...], tuple[int, ...]], ...]:
    groups: list[tuple[tuple[Any, ...], list[int]]] = []
    positions: dict[tuple[Any, ...], int] = {}
    for index, mode in enumerate(modes):
        key = (
            str(mode.side),
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.k_vector[2]),
        )
        position = positions.get(key)
        if position is None:
            positions[key] = len(groups)
            groups.append((key, [index]))
        else:
            groups[position][1].append(index)
    return tuple((key, tuple(indices)) for key, indices in groups)


def _fresh_phase_components(
    assemblers: Mapping[tuple[str, int], Any],
    modes: Sequence[Any],
    indices: Sequence[int],
    mpc: Any,
) -> tuple[Any, Any]:
    mode = modes[indices[0]]
    return (
        _component_owned_values(assemblers[(mode.side, 0)], mode, mpc),
        _component_owned_values(assemblers[(mode.side, 1)], mode, mpc),
    )


def _direct_surface_pass(
    modes: Sequence[Any],
    mpc: Any,
    cfg: Any,
    source: Any,
    projections: Sequence[complex],
    assemblers: Mapping[tuple[str, int], Any],
    incident_form: Any,
) -> tuple[Any, Any, Any, Any]:
    import numpy as np
    from mpi4py import MPI
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_form_vector,
        _mode_projection_denominator,
        _traction_vector,
    )

    source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
    comm = source.getComm().tompi4py()
    local_modal = np.zeros(len(modes), dtype=np.complex128)
    phase_groups = _mode_phase_groups(modes)
    for _key, indices in phase_groups:
        first, second = _fresh_phase_components(assemblers, modes, indices, mpc)
        try:
            for index in indices:
                mode = modes[index]
                ell = mode.e_vector[0] * first + mode.e_vector[1] * second
                denominator = _mode_projection_denominator(mode, cfg)
                local_modal[index] = np.dot(-np.conjugate(ell) / denominator, source_values)
                del ell
        finally:
            del first, second
    modal = np.empty_like(local_modal)
    comm.Allreduce(local_modal, modal, op=MPI.SUM)
    direct_action = np.zeros_like(source_values)
    direct_rhs_correction = np.zeros_like(source_values)
    for _key, indices in phase_groups:
        first, second = _fresh_phase_components(assemblers, modes, indices, mpc)
        try:
            for index in indices:
                mode = modes[index]
                traction = _traction_vector(mode, cfg)
                traction_values = traction[0] * first + traction[1] * second
                direct_action += modal[index] * traction_values
                direct_rhs_correction -= projections[index] * traction_values
                del traction_values
        finally:
            del first, second
    base_vector = _assemble_mpc_form_vector(incident_form, mpc)
    try:
        base = np.asarray(base_vector.getArray(readonly=True), dtype=np.complex128).copy()
    finally:
        base_vector.destroy()
    return direct_action, base + direct_rhs_correction, -modal, modal


def _relative_local(left: Any, right: Any, comm: Any) -> float:
    import numpy as np

    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    numerator = float(comm.allreduce(float(np.vdot(left_array - right_array, left_array - right_array).real)))
    denominator = float(comm.allreduce(float(np.vdot(right_array, right_array).real)))
    return float(math.sqrt(max(numerator, 0.0)) / max(math.sqrt(max(denominator, 0.0)), 1.0e-300))


def _online_worker(run_dir: Path, phase: str, expected_mpi_size: int) -> int:
    import gc
    import time as _time

    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc

    h2b = _h2b_module()
    comm = MPI.COMM_WORLD
    if phase not in {"mpi1", "mpi2"} or comm.size != int(expected_mpi_size):
        raise RuntimeError("M6A worker MPI identity mismatch")
    run_dir = run_dir.resolve()
    progress_path = run_dir / f"{phase}_progress.jsonl"
    summary_path = run_dir / f"{phase}_worker_summary.json"
    started = _time.perf_counter()
    source_start = h2b._light_source()
    runtime = None
    runtime_identity_by_rank = None
    measurement = None
    form_identity = None
    error = None
    action = None
    source = None
    target = None
    repeat = None
    base = None
    candidate_rhs = None
    assemblers = None
    incident_form = None
    cache_final = None
    try:
        with (
            progress_path.open("w", encoding="utf-8")
            if comm.rank == 0
            else nullcontext()
        ) as markers:
            stage = _read_json(run_dir / "m6a_stage_summary.json")
            if not _stage_allows_online(
                {"return_code": 0, "termination": None, "processes_gone": True},
                stage,
                True,
            ):
                raise ValueError("M6A stage authority is incomplete")
            _mark(markers, phase, "authority_validated", started, stage_manifest_sha256=_sha256_file(run_dir / "m6a_stage_summary.json"))
            cfg, mesh_data, function_space, floquet, modes = _production_objects(run_dir, mesh_name=f"m6a_{phase}_mesh")
            runtime = _worker_runtime_identity(
                comm,
                h2b,
                compiler_probe=False,
                compiler=stage["runtime_identity"]["compiler"],
            )
            runtime_identity_by_rank = comm.allgather(runtime)
            _mark(markers, phase, "mesh_ready", started)
            _mark(markers, phase, "space_ready", started)
            _mark(markers, phase, "floquet_mpc_ready", started)
            _mark(markers, phase, "modes_ready", started)
            cache_dir = run_dir / "jit_cache"
            cache_before = h2b._cache_snapshot(cache_dir)
            assemblers = _surface_assemblers(function_space, mesh_data, cfg, modes, cache_dir)
            from dolfinx import fem
            from src.solvers.dtn_port_3d import (
                _assemble_mpc_form_vector,
                _incident_top_traction_form,
            )

            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=h2b._expected_jit_options(cache_dir),
            )
            form_identity = _surface_identity(cache_dir, modes)
            cache_after = h2b._cache_snapshot(cache_dir)
            if (
                cache_before != stage["surface_forms"]["cache_inventory"]
                or cache_after != stage["surface_forms"]["cache_inventory"]
                or form_identity != stage["surface_forms"]
            ):
                raise ValueError("M6A online surface forms changed staged cache")
            _mark(markers, phase, "surface_cache_ready", started)
            from src.solvers.hcurl_fullspace_dtn import (
                build_fullspace_dtn_action,
                build_fullspace_dtn_carrier_from_surface,
            )
            carrier = build_fullspace_dtn_carrier_from_surface(
                modes,
                assemblers,
                floquet.mpc,
                cfg,
                expected_mode_count=M6A_MODE_COUNT,
            )
            action = build_fullspace_dtn_action(carrier, comm=comm)
            _mark(markers, phase, "carrier_ready", started, mode_manifest_sha256=action.audit["mode_manifest_sha256"])
            from benchmarks.run_task037_extra_m import _floquet_compatible_p6_dual, _function_to_mpc_vector
            from dolfinx import fem

            primal_function = fem.Function(function_space)
            primal_function.interpolate(_floquet_compatible_p6_dual(cfg))
            source = _function_to_mpc_vector(primal_function, floquet.mpc)
            index_map = function_space.dofmap.index_map
            ownership = tuple(int(value) for value in index_map.local_range)
            source_manifest = _write_canonical_role(
                run_dir,
                phase,
                "source_primal",
                __import__("src.solvers.hcurl_canonical_vector_dolfinx", fromlist=["iter_canonical_full_fe_owner_packets"]).iter_canonical_full_fe_owner_packets(
                    function_space, floquet.mpc, source, floquet
                ),
                rank=comm.rank,
                mpi_size=comm.size,
                ownership_range=ownership,
                comm=comm,
            )
            _mark(markers, phase, "source_ready", started, canonical_manifest=source_manifest)
            target = source.duplicate()
            repeat = source.duplicate()
            base = source.duplicate()
            candidate_rhs = source.duplicate()
            action.apply(source, target)
            action.apply(source, repeat)
            recovery = action.recover_auxiliary(source)
            repeat_recovery = action.recover_auxiliary(source)
            mode_manifest_record = None
            if comm.rank == 0:
                mode_manifest_record = _save_bytes_artifact(
                    run_dir,
                    f"{phase}_mode_manifest.json",
                    action.carrier.mode_manifest_bytes,
                )
            mode_manifest_record = comm.bcast(mode_manifest_record, root=0)
            mode_manifest_sha_by_rank = comm.allgather(
                hashlib.sha256(action.carrier.mode_manifest_bytes).hexdigest()
            )
            _mark(markers, phase, "candidate_ready", started)
            projections = tuple(
                __import__("src.solvers.dtn_port_3d", fromlist=["_incident_projection_onto_top_mode"])._incident_projection_onto_top_mode(mode, cfg)
                for mode in modes
            )
            base_vec = _assemble_mpc_form_vector(incident_form, floquet.mpc)
            try:
                base_values = np.asarray(base_vec.getArray(readonly=True), dtype=np.complex128).copy()
            finally:
                base_vec.destroy()
            with base.localForm() as local:
                local.set(0.0)
                local.array_w[: base_values.size] = base_values
            base.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            action.compose_physical_rhs(base, projections, candidate_rhs)
            direct_action, direct_rhs, direct_recovery, _modal = _direct_surface_pass(
                modes,
                floquet.mpc,
                cfg,
                source,
                projections,
                assemblers,
                incident_form,
            )
            _mark(markers, phase, "direct_ready", started)
            candidate_action = np.asarray(target.getArray(readonly=True), dtype=np.complex128).copy()
            repeat_action = np.asarray(repeat.getArray(readonly=True), dtype=np.complex128).copy()
            candidate_rhs_values = np.asarray(candidate_rhs.getArray(readonly=True), dtype=np.complex128).copy()
            recovery = np.asarray(recovery, dtype=np.complex128).copy()
            repeat_recovery = np.asarray(repeat_recovery, dtype=np.complex128).copy()
            _mark(markers, phase, "rhs_ready", started)
            dual_iterator = __import__("src.solvers.hcurl_canonical_vector_dolfinx", fromlist=["iter_canonical_full_fe_dual_packets"]).iter_canonical_full_fe_dual_packets
            action_manifest = _write_canonical_role(
                run_dir, phase, "candidate_action_dual", dual_iterator(function_space, floquet.mpc, target), rank=comm.rank, mpi_size=comm.size, ownership_range=ownership, comm=comm
            )
            rhs_manifest = _write_canonical_role(
                run_dir, phase, "candidate_physical_rhs_dual", dual_iterator(function_space, floquet.mpc, candidate_rhs), rank=comm.rank, mpi_size=comm.size, ownership_range=ownership, comm=comm
            )
            _mark(markers, phase, "canonical_ready", started, action_manifest=action_manifest, rhs_manifest=rhs_manifest)
            local_arrays = {
                "candidate_action": _save_owned_array(run_dir, f"{phase}_candidate_action", candidate_action, rank=comm.rank, ownership_range=ownership),
                "direct_action": _save_owned_array(run_dir, f"{phase}_direct_action", direct_action, rank=comm.rank, ownership_range=ownership),
                "repeat_action": _save_owned_array(run_dir, f"{phase}_repeat_action", repeat_action, rank=comm.rank, ownership_range=ownership),
                "candidate_physical_rhs": _save_owned_array(run_dir, f"{phase}_candidate_physical_rhs", candidate_rhs_values, rank=comm.rank, ownership_range=ownership),
                "direct_physical_rhs": _save_owned_array(run_dir, f"{phase}_direct_physical_rhs", direct_rhs, rank=comm.rank, ownership_range=ownership),
            }
            arrays = {
                name: comm.allgather(record) for name, record in local_arrays.items()
            }
            if comm.rank == 0:
                arrays["candidate_recovery"] = [_save_global_small_array(run_dir, f"{phase}_candidate_recovery", recovery)]
                arrays["direct_recovery"] = [_save_global_small_array(run_dir, f"{phase}_direct_recovery", direct_recovery)]
                arrays["repeat_recovery"] = [_save_global_small_array(run_dir, f"{phase}_repeat_recovery", repeat_recovery)]
            arrays = comm.bcast(arrays if comm.rank == 0 else None, root=0)
            cache_final = h2b._cache_snapshot(cache_dir)
            action_error = _relative_local(candidate_action, direct_action, comm)
            rhs_error = _relative_local(candidate_rhs_values, direct_rhs, comm)
            recovery_error = float(np.linalg.norm(recovery - direct_recovery) / max(np.linalg.norm(direct_recovery), 1.0e-300))
            repeat_error = _relative_local(candidate_action, repeat_action, comm)
            repeat_recovery_error = float(np.linalg.norm(recovery - repeat_recovery) / max(np.linalg.norm(recovery), 1.0e-300))
            measurement = {
                "scope": _m6a_scope(comm.size, phase),
                "p6": _p6_identity(mesh_data, function_space, floquet),
                "events": list(M6A_EVENTS),
                "source": {"role": "source_primal", "canonical": source_manifest},
                "canonical": {"candidate_action_dual": action_manifest, "candidate_physical_rhs_dual": rhs_manifest},
                "local_cells_by_rank": [int(value) for value in comm.allgather(_p6_identity(mesh_data, function_space, floquet)["local_cells"])],
                "arrays": arrays,
                "metrics": {
                    "candidate_direct_action_relative_error": action_error,
                    "candidate_direct_physical_rhs_relative_error": rhs_error,
                    "candidate_direct_recovery_relative_error": recovery_error,
                    "candidate_repeat_action_relative_error": repeat_error,
                    "candidate_repeat_recovery_relative_error": repeat_recovery_error,
                    "finite": bool(np.isfinite(candidate_action).all() and np.isfinite(direct_action).all() and np.isfinite(candidate_rhs_values).all() and np.isfinite(direct_rhs).all() and np.isfinite(recovery).all() and np.isfinite(direct_recovery).all()),
                },
                "action_audit": {
                    **dict(action.audit),
                },
                "form": form_identity,
                "cache": {
                    "stage": stage["surface_forms"]["cache_inventory"],
                    "before": cache_before,
                    "after": cache_after,
                    "final": cache_final,
                    "unchanged": cache_before == cache_after == cache_final,
                },
                "mode_manifest_sha256": action.audit["mode_manifest_sha256"],
                "mode_manifest_sha_by_rank": mode_manifest_sha_by_rank,
                "mode_manifest": mode_manifest_record,
                "recovery_definition": "direct modal sum -D u with fixed H=I",
                "physical_rhs_definition": "fresh base incident top traction plus C times fixed incident projections",
                "metadata_only_collective": "canonical rank metadata allgather; no FE-sized numeric allgather",
                "direct_oracle": {
                    "explicit_C_materialized_count": 0,
                    "explicit_D_materialized_count": 0,
                    "global_matrix_materialized": False,
                    "augmented_matrix_materialized": False,
                    "schur_or_trace_operator_materialized": False,
                    "streaming_passes": 2,
                },
            }
            _mark(markers, phase, "summary_ready", started)
            del primal_function, carrier
            gc.collect()
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for item in (candidate_rhs, base, repeat, target, source):
            if item is not None:
                item.destroy()
        if action is not None:
            action.destroy()
        del assemblers, incident_form
        gc.collect()
    source_end = h2b._light_source()
    status = "measurement_complete" if error is None and measurement is not None else "gate_failed"
    summary = _attach_evidence(
        {
            "schema": M6A_WORKER_SCHEMA,
            "status": status,
            "route": "M6A",
            "phase": phase,
            "scope": _m6a_scope(expected_mpi_size, phase),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "runtime_identity": runtime,
            "runtime_identity_by_rank": runtime_identity_by_rank,
            "measurement": measurement,
            "error": error,
            "elapsed_wall_seconds": float(_time.perf_counter() - started),
        }
    )
    if comm.rank == 0:
        _write_json(summary_path, summary)
    comm.Barrier()
    return 0 if status == "measurement_complete" else 1


def _process_gate(h2b: Any, run_dir: Path, phase: str, process: Mapping[str, Any], *, require_no_compiler: bool) -> tuple[bool, dict[str, Any]]:
    drain = h2b._bounded_process_drain(process)
    timeline_path = run_dir / f"{phase}_timeline.jsonl"
    metrics = h2b._timeline_metrics(timeline_path, phase)
    observed = {
        "peak_rss_bytes": int(process.get("peak_rss_bytes", -1)),
        "swap_bytes": int(process.get("swap_bytes", -1)),
        "timeline_peak_rss_bytes": int(metrics["peak_rss_bytes"]),
        "timeline_swap_bytes": int(metrics["swap_bytes"]),
        "compiler_descendant_pids": list(metrics["compiler_descendant_pids"]),
        "processes_gone": bool(drain["gone"]),
        "drain": drain,
    }
    passed = bool(
        type(process.get("return_code")) is int
        and process["return_code"] == 0
        and process.get("termination") is None
        and drain["gone"] is True
        and process.get("peak_rss_bytes") == metrics["peak_rss_bytes"]
        and process.get("swap_bytes") == metrics["swap_bytes"]
        and int(metrics["peak_rss_bytes"]) < M6A_RSS_LIMIT_BYTES
        and int(metrics["swap_bytes"]) == M6A_SWAP_LIMIT_BYTES
        and (not require_no_compiler or metrics["compiler_descendant_pids"] == [])
    )
    return passed, observed


def _stage_summary_valid(run_dir: Path, stage: Mapping[str, Any]) -> bool:
    try:
        p6 = stage["p6"]
        local_cells = stage["local_cells_by_rank"]
        surface_forms = stage["surface_forms"]
        return bool(
            stage["schema"] == M6A_STAGE_SCHEMA
            and stage["status"] == "measurement_complete"
            and _evidence_valid(stage)
            and stage["scope"] == _m6a_scope()
            and _source_pair_valid(stage["source_at_start"], stage["source_at_end"])
            and _m6a_runtime_valid(stage["runtime_identity"], 1)
            and _runtime_identity_by_rank_valid(
                stage["runtime_identity_by_rank"],
                1,
                stage["runtime_identity"]["sys_executable"],
            )
            and p6 == {
                "global_cells": M6A_GLOBAL_CELLS,
                "local_cells": M6A_GLOBAL_CELLS,
                "local_nloc": M6A_LOCAL_NLOC,
                "global_rows": M6A_GLOBAL_ROWS,
                "constraint_count": M6A_CONSTRAINTS,
            }
            and local_cells == [M6A_GLOBAL_CELLS]
            and stage["events"] == list(M6A_STAGE_EVENTS)
            and surface_forms["component_count"] == 4
            and surface_forms["incident_form_count"] == 1
            and surface_forms["mode_count"] == M6A_MODE_COUNT
            and isinstance(surface_forms["cache_inventory"], list)
            and surface_forms["cache_inventory"]
            == _h2b_module()._cache_snapshot(run_dir / "jit_cache")
            and _progress_valid(
                run_dir / "m6a_stage_progress.jsonl", "stage", M6A_STAGE_EVENTS
            )
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return False


def _phase_worker_gate(
    run_dir: Path, phase: str, expected_mpi_size: int
) -> tuple[bool, dict[str, Any]]:
    try:
        summary = _read_json(run_dir / f"{phase}_worker_summary.json")
        checks, details = _phase_check(
            run_dir, summary, phase=phase, expected_mpi_size=expected_mpi_size
        )
        return all(checks.values()), {"checks": checks, "details": details}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return False, {"checks": {}, "error": f"{type(exc).__name__}: {exc}"}


def _raw_artifacts(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Build the explicit evidence inventory; the watchdog file is excluded."""

    paths = {
        "m6a_stage_summary.json",
        "m6a_stage_progress.jsonl",
        "stage_timeline.jsonl",
        "stage_stdout.txt",
        "stage_root_pid.json",
    }
    for phase in ("mpi1", "mpi2"):
        paths.update(
            {
                f"{phase}_worker_summary.json",
                f"{phase}_progress.jsonl",
                f"{phase}_timeline.jsonl",
                f"{phase}_stdout.txt",
                f"{phase}_root_pid.json",
            }
        )
        summary_path = run_dir / f"{phase}_worker_summary.json"
        if not summary_path.is_file():
            continue
        try:
            measurement = _read_json(summary_path)["measurement"]
            records = [measurement["mode_manifest"], measurement["source"]["canonical"]]
            records.extend(measurement["canonical"].values())
            for array_records in measurement["arrays"].values():
                records.extend(array_records if isinstance(array_records, list) else [array_records])
            for record in records:
                if isinstance(record, Mapping) and isinstance(record.get("path"), str):
                    paths.add(record["path"])
                    if record["path"].endswith("_manifest.json"):
                        manifest_path = run_dir / record["path"]
                        if manifest_path.is_file():
                            manifest = _read_json(manifest_path)
                            for shard in manifest.get("per_rank_shards", []):
                                if isinstance(shard, Mapping) and isinstance(shard.get("filename"), str):
                                    paths.add(shard["filename"])
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            continue
    return {relative: _artifact(run_dir, relative) for relative in sorted(paths)}


def _watchdog(run_dir: Path) -> int:
    h2b = _h2b_module()
    run_dir = run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(f"M6A run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    executable = h2b._worker_executable()
    started = time.perf_counter()
    source_start = h2b._light_source()
    stage = h2b._monitor_phase(run_dir, "stage", _stage_command(executable, run_dir), M6A_TIMEOUT_SECONDS, M6A_RSS_LIMIT_BYTES)
    stage_ok, stage_resource = _process_gate(h2b, run_dir, "stage", stage, require_no_compiler=False)
    stage["processes_gone"] = stage_resource["processes_gone"]
    try:
        stage_summary = _read_json(run_dir / "m6a_stage_summary.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        stage_summary = {"status": "missing", "error": f"{type(exc).__name__}: {exc}"}
    stage_ok = bool(
        stage_ok
        and _stage_allows_online(stage, stage_summary, bool(stage["processes_gone"]))
        and _stage_summary_valid(run_dir, stage_summary)
    )
    phases: dict[str, Any] = {}
    phase_resource: dict[str, Any] = {}
    if stage_ok:
        mpi1 = h2b._monitor_phase(run_dir, "mpi1", _worker_command(executable, run_dir, "mpi1", 1), M6A_TIMEOUT_SECONDS, M6A_RSS_LIMIT_BYTES)
        ok1, phase_resource["mpi1"] = _process_gate(h2b, run_dir, "mpi1", mpi1, require_no_compiler=True)
        mpi1["processes_gone"] = phase_resource["mpi1"]["processes_gone"]
        phases["mpi1"] = mpi1
        worker_ok1, worker_gate1 = _phase_worker_gate(run_dir, "mpi1", 1) if ok1 else (False, {"checks": {}})
        mpi1["worker_gate"] = worker_gate1
        if ok1 and worker_ok1:
            mpi2 = h2b._monitor_phase(run_dir, "mpi2", _worker_command(executable, run_dir, "mpi2", 2), M6A_TIMEOUT_SECONDS, M6A_RSS_LIMIT_BYTES)
            ok2, phase_resource["mpi2"] = _process_gate(h2b, run_dir, "mpi2", mpi2, require_no_compiler=True)
            mpi2["processes_gone"] = phase_resource["mpi2"]["processes_gone"]
            worker_ok2, worker_gate2 = _phase_worker_gate(run_dir, "mpi2", 2) if ok2 else (False, {"checks": {}})
            mpi2["worker_gate"] = worker_gate2
            phases["mpi2"] = mpi2
        else:
            phases["mpi2"] = {
                "status": "not_run_by_gate",
                "reason": "mpi1_gate_failed",
            }
            worker_ok2 = False
            ok2 = False
    else:
        phases["mpi1"] = {"status": "not_run_by_gate", "reason": "stage_gate_failed"}
        phases["mpi2"] = {"status": "not_run_by_gate", "reason": "stage_gate_failed"}
        worker_ok1 = False
        worker_ok2 = False
        ok2 = False
    source_end = h2b._light_source()
    status = (
        "measurement_complete"
        if stage_ok and worker_ok1 and ok2 and worker_ok2
        else "controlled_stop"
    )
    raw_artifacts = _raw_artifacts(run_dir)
    payload = _attach_evidence(
        {
            "schema": M6A_WATCHDOG_SCHEMA,
            "status": status,
            "route": "M6A",
            "scope": _m6a_scope(),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "prediction": {
                "predicted_live_set_bytes": M6A_PREDICTED_LIVE_SET_BYTES,
                "limit_bytes": M6A_PREDICTED_LIVE_SET_LIMIT_BYTES,
                "is_measurement": False,
            },
            "commands": {
                "stage": _stage_command(executable, run_dir),
                "mpi1": _worker_command(executable, run_dir, "mpi1", 1),
                "mpi2": _worker_command(executable, run_dir, "mpi2", 2),
            },
            "stage": stage,
            "stage_summary": _artifact(run_dir, "m6a_stage_summary.json"),
            "stage_resource": stage_resource,
            "phases": phases,
            "phase_resource": phase_resource,
            "raw_artifacts": raw_artifacts,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(run_dir / "m6a_watchdog_summary.json", payload)
    return 0 if status == "measurement_complete" else 1


def _load_owned_vector(
    run_dir: Path,
    records: Any,
    global_rows: int,
    *,
    expected_ranks: Sequence[int] | None = None,
) -> Any:
    import numpy as np

    if not isinstance(records, list) or not records:
        raise ValueError("owner-local array records are missing")
    pieces = []
    seen_ranks: set[int] = set()
    for record in records:
        if not isinstance(record, Mapping) or set(record) != _ARRAY_RECORD_KEYS:
            raise ValueError("owner-local array record keys are incomplete")
        if record["present"] is not True or not isinstance(record["rank"], int) or record["rank"] in seen_ranks:
            raise ValueError("owner-local array rank identity is invalid")
        seen_ranks.add(record["rank"])
        relative = record["path"]
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("owner-local array path is not relative")
        actual = _artifact(run_dir, relative)
        if actual != {key: record[key] for key in ("path", "present", "bytes", "sha256")}:
            raise ValueError("owner-local array file binding mismatch")
        value = np.load(run_dir / relative, mmap_mode="r", allow_pickle=False)
        start, end = record["ownership_range"]
        if (
            value.dtype != np.dtype(np.complex128)
            or value.ndim != 1
            or list(value.shape) != record["shape"]
            or record["dtype"] != str(value.dtype)
            or value.shape[0] != int(end) - int(start)
            or int(start) < 0
            or int(end) > int(global_rows)
            or record["array_sha256"] != hashlib.sha256(memoryview(np.ascontiguousarray(value)).cast("B")).hexdigest()
            or not np.all(np.isfinite(value))
        ):
            raise ValueError("owner-local array payload is invalid")
        pieces.append((int(start), int(end), np.asarray(value, dtype=np.complex128).copy()))
    if expected_ranks is not None and seen_ranks != {int(rank) for rank in expected_ranks}:
        raise ValueError("owner-local array rank set is incomplete")
    pieces.sort(key=lambda item: item[0])
    result = np.empty(int(global_rows), dtype=np.complex128)
    cursor = 0
    for start, end, value in pieces:
        if start != cursor:
            raise ValueError("owner-local array ownership has a gap or overlap")
        result[start:end] = value
        cursor = end
    if cursor != int(global_rows):
        raise ValueError("owner-local array ownership does not cover global rows")
    return result


def _canonical_record(
    run_dir: Path,
    record: Any,
    expected_role: str,
    *,
    expected_mpi_size: int,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    if not isinstance(record, Mapping) or set(record) != {"path", "sha256", "role"} or record["role"] != expected_role:
        raise ValueError("canonical manifest binding is invalid")
    relative = record["path"]
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("canonical manifest path is invalid")
    from benchmarks.canonical_vector_artifacts import read_canonical_manifest, read_canonical_packet_shards

    manifest = read_canonical_manifest(run_dir / relative, record["sha256"])
    if (
        manifest.get("role") != expected_role
        or manifest.get("mpi_size") != int(expected_mpi_size)
        or manifest.get("duplicate_detection") != "checker_recomputed_from_shards"
    ):
        raise ValueError("canonical manifest role or duplicate mode is invalid")
    shards = manifest.get("per_rank_shards")
    if (
        not isinstance(shards, list)
        or len(shards) != int(expected_mpi_size)
        or {item.get("rank") for item in shards} != set(range(int(expected_mpi_size)))
    ):
        raise ValueError("canonical shard rank set is invalid")
    ordered = sorted(shards, key=lambda item: int(item["ownership_range"][0]))
    cursor = 0
    for item in ordered:
        filename = item.get("filename")
        ownership = item.get("ownership_range")
        if (
            not isinstance(filename, str)
            or Path(filename).is_absolute()
            or ".." in Path(filename).parts
            or not isinstance(ownership, list)
            or len(ownership) != 2
            or int(ownership[0]) != cursor
            or int(ownership[1]) < int(ownership[0])
        ):
            raise ValueError("canonical shard ownership or path is invalid")
        cursor = int(ownership[1])
    if cursor != M6A_GLOBAL_ROWS:
        raise ValueError("canonical shard ownership does not cover global rows")
    paths = tuple(run_dir / item["filename"] for item in shards)
    packets = read_canonical_packet_shards(paths, tuple(item["file_sha256"] for item in shards))
    keys = tuple(key for key, _value in packets)
    packet_role = "full_fe" if expected_role == "source_primal" else "full_fe_dual"
    if (
        len(keys) != len(set(keys))
        or int(manifest["global_summed_packet_count"]) != len(packets)
        or not _canonical_packet_role(packets, packet_role)
    ):
        raise ValueError("canonical checker found duplicate or packet-count mismatch")
    return manifest, packets


def _phase_check(
    run_dir: Path,
    summary: Mapping[str, Any],
    *,
    phase: str,
    expected_mpi_size: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np

    checks = {
        "schema": False,
        "source": False,
        "runtime": False,
        "scope": False,
        "p6": False,
        "events": False,
        "cache": False,
        "audit": False,
        "arrays": False,
        "canonical": False,
        "mode_manifest": False,
        "numeric": False,
    }
    details: dict[str, Any] = {}
    if not isinstance(summary, Mapping):
        return checks, {"problems": ["summary_missing"]}
    try:
        checks["schema"] = (
            summary["schema"] == M6A_WORKER_SCHEMA
            and summary["status"] == "measurement_complete"
            and _evidence_valid(summary)
        )
        checks["source"] = _source_pair_valid(
            summary["source_at_start"], summary["source_at_end"]
        )
        checks["runtime"] = _m6a_runtime_valid(
            summary["runtime_identity"], expected_mpi_size
        )
        checks["scope"] = summary["scope"] == _m6a_scope(expected_mpi_size, phase)
        measurement = summary["measurement"]
        p6 = measurement["p6"]
        local_cells_by_rank = measurement["local_cells_by_rank"]
        checks["p6"] = bool(
            p6["global_cells"] == M6A_GLOBAL_CELLS
            and p6["local_nloc"] == M6A_LOCAL_NLOC
            and p6["global_rows"] == M6A_GLOBAL_ROWS
            and p6["constraint_count"] == M6A_CONSTRAINTS
            and isinstance(local_cells_by_rank, list)
            and len(local_cells_by_rank) == expected_mpi_size
            and all(type(value) is int and value > 0 for value in local_cells_by_rank)
            and sum(local_cells_by_rank) == M6A_GLOBAL_CELLS
            and p6["local_cells"] == local_cells_by_rank[0]
        )
        checks["events"] = bool(
            summary["measurement"]["events"] == list(M6A_EVENTS)
            and _progress_valid(
                run_dir / f"{phase}_progress.jsonl", phase, M6A_EVENTS
            )
        )
        cache = measurement["cache"]
        h2b = _h2b_module()
        checks["cache"] = bool(
            cache["stage"] == _read_json(run_dir / "m6a_stage_summary.json")["surface_forms"]["cache_inventory"]
            and cache["before"] == cache["after"] == cache["final"] == cache["stage"]
            and cache["unchanged"] is True
            and cache["final"] == h2b._cache_snapshot(run_dir / "jit_cache")
        )
        audit = measurement["action_audit"]
        required_audit = {
            "fine_space": "uncondensed_fullspace",
            "condensation": False,
            "static_condensed_operator_used": False,
            "trace_slab_pc_used": False,
            "global_matrix_materialized": False,
            "augmented_matrix_materialized": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "mode_count": M6A_MODE_COUNT,
            "global_rows": M6A_GLOBAL_ROWS,
            "fixed_H": "identity",
            "fe_sized_allgather": False,
            "ordinary_default": False,
            "modal_allreduce_count_per_apply": 1,
            "apply_count": 2,
            "retained_payload_scope": "numpy arrays + retained canonical manifest bytes",
            "python_object_overhead_included": False,
            "petsc_object_overhead_included": False,
            "matrix_type": "python_action_only",
            "retained_plus_work_limit_bytes": M6A_RETAINED_WORK_LIMIT_BYTES,
        }
        checks["audit"] = bool(
            all(key in audit and audit[key] == value for key, value in required_audit.items())
            and type(audit["retained_plus_work_global_sum_bytes"]) is int
            and audit["retained_plus_work_global_sum_bytes"] >= 0
            and audit["retained_plus_work_global_sum_bytes"] <= M6A_RETAINED_WORK_LIMIT_BYTES
            and audit["retained_plus_work_gate"] is True
        )
        checks["runtime"] = bool(
            checks["runtime"]
            and _runtime_identity_by_rank_valid(
                summary["runtime_identity_by_rank"],
                expected_mpi_size,
                summary["runtime_identity"]["sys_executable"],
            )
        )
        checks["source"] = bool(
            checks["source"] and measurement["source"]["role"] == "source_primal"
        )
        arrays = measurement["arrays"]
        expected_ranks = tuple(range(expected_mpi_size))

        def relative_from_records(left_name: str, right_name: str, size: int) -> float:
            left = _load_owned_vector(
                run_dir, arrays[left_name], size, expected_ranks=expected_ranks
            )
            right = _load_owned_vector(
                run_dir, arrays[right_name], size, expected_ranks=expected_ranks
            )
            result = float(
                np.linalg.norm(left - right)
                / max(np.linalg.norm(right), 1.0e-300)
            )
            del left, right
            return result

        action_error = relative_from_records(
            "candidate_action", "direct_action", M6A_GLOBAL_ROWS
        )
        rhs_error = relative_from_records(
            "candidate_physical_rhs", "direct_physical_rhs", M6A_GLOBAL_ROWS
        )
        repeat_error = relative_from_records(
            "candidate_action", "repeat_action", M6A_GLOBAL_ROWS
        )
        candidate_recovery = _load_owned_vector(
            run_dir,
            arrays["candidate_recovery"],
            M6A_MODE_COUNT,
            expected_ranks=(0,),
        )
        direct_recovery = _load_owned_vector(
            run_dir,
            arrays["direct_recovery"],
            M6A_MODE_COUNT,
            expected_ranks=(0,),
        )
        repeat_recovery = _load_owned_vector(
            run_dir,
            arrays["repeat_recovery"],
            M6A_MODE_COUNT,
            expected_ranks=(0,),
        )
        recovery_error = float(
            np.linalg.norm(candidate_recovery - direct_recovery)
            / max(np.linalg.norm(direct_recovery), 1.0e-300)
        )
        recovery_repeat_error = float(
            np.linalg.norm(candidate_recovery - repeat_recovery)
            / max(np.linalg.norm(candidate_recovery), 1.0e-300)
        )
        checks["arrays"] = True
        recorded = measurement["metrics"]
        recorded_values = {
            "candidate_direct_action_relative_error": action_error,
            "candidate_direct_physical_rhs_relative_error": rhs_error,
            "candidate_direct_recovery_relative_error": recovery_error,
            "candidate_repeat_action_relative_error": repeat_error,
            "candidate_repeat_recovery_relative_error": recovery_repeat_error,
        }
        if any(
            key not in recorded
            or abs(float(recorded[key]) - value) > 1.0e-14
            for key, value in recorded_values.items()
        ):
            raise ValueError("worker numeric scalars do not match checker recomputation")
        checks["numeric"] = bool(
            all(value <= 1.0e-11 for value in recorded_values.values())
            and recorded["finite"] is True
        )
        _canonical_record(
            run_dir,
            measurement["source"]["canonical"],
            "source_primal",
            expected_mpi_size=expected_mpi_size,
        )
        _canonical_record(
            run_dir,
            measurement["canonical"]["candidate_action_dual"],
            "candidate_action_dual",
            expected_mpi_size=expected_mpi_size,
        )
        _canonical_record(
            run_dir,
            measurement["canonical"]["candidate_physical_rhs_dual"],
            "candidate_physical_rhs_dual",
            expected_mpi_size=expected_mpi_size,
        )
        mode_manifest = measurement["mode_manifest"]
        checks["mode_manifest"] = bool(
            _mode_manifest_valid(run_dir, mode_manifest)
            and mode_manifest["sha256"] == measurement["mode_manifest_sha256"]
            and mode_manifest["sha256"] == audit["mode_manifest_sha256"]
            and measurement["mode_manifest_sha256"] == audit["mode_manifest_sha256"]
            and measurement["mode_manifest_sha_by_rank"]
            == [audit["mode_manifest_sha256"]] * expected_mpi_size
        )
        direct_oracle = measurement["direct_oracle"]
        checks["canonical"] = bool(
            direct_oracle["explicit_C_materialized_count"] == 0
            and direct_oracle["explicit_D_materialized_count"] == 0
            and direct_oracle["global_matrix_materialized"] is False
            and direct_oracle["augmented_matrix_materialized"] is False
            and direct_oracle["schur_or_trace_operator_materialized"] is False
            and direct_oracle["streaming_passes"] == 2
        )
        details.update(
            {
                "metrics": recorded_values,
                "candidate_recovery": candidate_recovery.tolist(),
            }
        )
    except (AttributeError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError, AssertionError) as exc:
        details["problems"] = [f"{type(exc).__name__}:{exc}"]
    return checks, details


def _check_raw(run_dir: Path) -> dict[str, Any]:
    checks = {
        "watchdog": False,
        "stage": False,
        "commands": False,
        "prediction": False,
        "mpi1": False,
        "mpi2": False,
        "cross_mpi_source": False,
        "cross_mpi_action": False,
        "cross_mpi_rhs": False,
        "cross_mpi_recovery": False,
        "mode_manifest": False,
        "source_stability": False,
        "lifecycle": False,
        "progress": False,
        "raw_artifacts": False,
    }
    problems: list[str] = []
    phase_checks: dict[str, dict[str, bool]] = {}
    phase_details: dict[str, dict[str, Any]] = {}
    recovery_error: float | None = None
    try:
        watchdog = _read_json(run_dir / "m6a_watchdog_summary.json")
        checks["watchdog"] = bool(
            watchdog["schema"] == M6A_WATCHDOG_SCHEMA
            and watchdog["status"] == "measurement_complete"
            and watchdog["route"] == "M6A"
            and _evidence_valid(watchdog)
            and watchdog["scope"] == _m6a_scope()
        )
        stage = _read_json(run_dir / "m6a_stage_summary.json")
        checks["stage"] = _stage_summary_valid(run_dir, stage)
        checks["stage"] = bool(
            checks["stage"]
            and watchdog["stage_summary"] == _artifact(run_dir, "m6a_stage_summary.json")
        )
        executable = stage["runtime_identity"]["sys_executable"]
        checks["commands"] = watchdog["commands"] == {
            "stage": _stage_command(executable, run_dir),
            "mpi1": _worker_command(executable, run_dir, "mpi1", 1),
            "mpi2": _worker_command(executable, run_dir, "mpi2", 2),
        }
        prediction = watchdog["prediction"]
        checks["prediction"] = bool(
            prediction["is_measurement"] is False
            and prediction["predicted_live_set_bytes"] == M6A_PREDICTED_LIVE_SET_BYTES
            and prediction["limit_bytes"] == M6A_PREDICTED_LIVE_SET_LIMIT_BYTES
            and prediction["predicted_live_set_bytes"] <= M6A_PREDICTED_LIVE_SET_LIMIT_BYTES
        )
        phases = watchdog.get("phases", {})
        phase_resources = watchdog.get("phase_resource", {})
        lifecycle_records = [
            ("stage", watchdog.get("stage"), watchdog.get("stage_resource")),
            ("mpi1", phases.get("mpi1"), phase_resources.get("mpi1")),
            ("mpi2", phases.get("mpi2"), phase_resources.get("mpi2")),
        ]
        lifecycle_ok = True
        h2b = _h2b_module()
        for name, process, resource in lifecycle_records:
            if not isinstance(process, Mapping) or not isinstance(resource, Mapping):
                lifecycle_ok = False
                if name == "mpi2":
                    problems.append("mpi2_not_run_by_gate")
                continue
            if name in {"mpi1", "mpi2"} and process.get("status") == "not_run_by_gate":
                lifecycle_ok = False
                problems.append(f"{name}_not_run_by_gate")
                continue
            try:
                timeline = h2b._timeline_metrics(run_dir / f"{name}_timeline.jsonl", name)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                lifecycle_ok = False
                problems.append(f"{name}_timeline:{type(exc).__name__}:{exc}")
                continue
            lifecycle_ok = lifecycle_ok and (
                process.get("return_code") == 0
                and process.get("termination") is None
                and process.get("processes_gone") is True
                and resource.get("processes_gone") is True
                and process.get("peak_rss_bytes") == timeline["peak_rss_bytes"]
                and process.get("swap_bytes") == timeline["swap_bytes"]
                and int(timeline["peak_rss_bytes"]) < M6A_RSS_LIMIT_BYTES
                and int(timeline["swap_bytes"]) == M6A_SWAP_LIMIT_BYTES
            )
            if name in {"mpi1", "mpi2"}:
                if timeline["compiler_descendant_pids"]:
                    lifecycle_ok = False
                    problems.append(f"{name}_compiler_descendants")
                lifecycle_ok = lifecycle_ok and timeline["compiler_descendant_pids"] == []
        checks["lifecycle"] = lifecycle_ok
        phase_summaries: dict[str, dict[str, Any] | None] = {}
        for phase in ("mpi1", "mpi2"):
            summary_path = run_dir / f"{phase}_worker_summary.json"
            if summary_path.is_file():
                try:
                    phase_summaries[phase] = _read_json(summary_path)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    phase_summaries[phase] = None
                    problems.append(f"{phase}_summary:{type(exc).__name__}:{exc}")
            else:
                phase_summaries[phase] = None
                problems.append(f"{phase}_not_run_by_gate")
        stage_source_sha = stage["source_at_start"]["source_commit_full_sha"]
        watchdog_source_sha = watchdog["source_at_start"]["source_commit_full_sha"]
        checks["source_stability"] = (
            _source_pair_valid(watchdog["source_at_start"], watchdog["source_at_end"])
            and _source_pair_valid(stage["source_at_start"], stage["source_at_end"])
            and stage_source_sha == watchdog_source_sha
            and all(phase_summaries[phase] is not None for phase in ("mpi1", "mpi2"))
            and all(
                _source_pair_valid(item["source_at_start"], item["source_at_end"])
                and item["source_at_start"]["source_commit_full_sha"] == watchdog_source_sha
                for item in phase_summaries.values()
                if item is not None
            )
        )
        for phase, item in phase_summaries.items():
            if item is None:
                continue
            measurement = item.get("measurement")
            if not isinstance(measurement, Mapping) or measurement.get("form") != stage.get("surface_forms"):
                raise ValueError("online surface form/cache identity differs from stage")
        checks["progress"] = bool(
            _progress_valid(run_dir / "m6a_stage_progress.jsonl", "stage", M6A_STAGE_EVENTS)
            and all(
                phase_summaries[phase] is not None
                and _progress_valid(run_dir / f"{phase}_progress.jsonl", phase, M6A_EVENTS)
                for phase in ("mpi1", "mpi2")
            )
        )
        for phase, size in (("mpi1", 1), ("mpi2", 2)):
            if phase_summaries[phase] is None:
                phase_checks[phase] = {
                    key: False
                    for key in (
                        "schema", "source", "runtime", "scope", "p6", "events",
                        "cache", "audit", "arrays", "canonical", "mode_manifest", "numeric",
                    )
                }
                phase_details[phase] = {"status": "not_run_by_gate", "problems": ["summary_missing"]}
            else:
                phase_checks[phase], phase_details[phase] = _phase_check(
                    run_dir, phase_summaries[phase], phase=phase, expected_mpi_size=size
                )
            checks[phase] = all(phase_checks[phase].values())
        if phase_summaries["mpi1"] is not None and phase_summaries["mpi2"] is not None:
            from src.solvers.hcurl_canonical_vector import compare_canonical_packets

            for key, path in (
                ("cross_mpi_source", ("source", "source_primal")),
                ("cross_mpi_action", ("canonical", "candidate_action_dual")),
                ("cross_mpi_rhs", ("canonical", "candidate_physical_rhs_dual")),
            ):
                left_measurement = phase_summaries["mpi1"]["measurement"]
                right_measurement = phase_summaries["mpi2"]["measurement"]
                left_record = left_measurement[path[0]]["canonical"] if path[0] == "source" else left_measurement[path[0]][path[1]]
                right_record = right_measurement[path[0]]["canonical"] if path[0] == "source" else right_measurement[path[0]][path[1]]
                _left_manifest, left_packets = _canonical_record(
                    run_dir, left_record, path[1], expected_mpi_size=1
                )
                _right_manifest, right_packets = _canonical_record(
                    run_dir, right_record, path[1], expected_mpi_size=2
                )
                comparison = compare_canonical_packets(
                    left_packets, right_packets, relative_tolerance=1.0e-12
                )
                checks[key] = comparison["pass"]
                del left_packets, right_packets
            import numpy as np

            left_recovery = np.asarray(phase_details["mpi1"]["candidate_recovery"], dtype=np.complex128)
            right_recovery = np.asarray(phase_details["mpi2"]["candidate_recovery"], dtype=np.complex128)
            recovery_error = float(np.linalg.norm(left_recovery - right_recovery) / max(np.linalg.norm(right_recovery), 1.0e-300))
            checks["cross_mpi_recovery"] = recovery_error <= 1.0e-12
            checks["mode_manifest"] = bool(
                phase_summaries["mpi1"]["measurement"]["mode_manifest_sha256"]
                == phase_summaries["mpi2"]["measurement"]["mode_manifest_sha256"]
                and phase_summaries["mpi1"]["measurement"]["mode_manifest_sha_by_rank"]
                == [phase_summaries["mpi1"]["measurement"]["mode_manifest_sha256"]]
                and phase_summaries["mpi2"]["measurement"]["mode_manifest_sha_by_rank"]
                == [phase_summaries["mpi2"]["measurement"]["mode_manifest_sha256"]] * 2
            )
        else:
            problems.append("cross_mpi_not_run_by_gate")
        expected_artifacts = _raw_artifacts(run_dir)
        expected_direct = {
            name for name, record in expected_artifacts.items() if record["present"]
        } | {"m6a_watchdog_summary.json"}
        actual_direct = {path.name for path in run_dir.iterdir() if path.is_file()}
        checks["raw_artifacts"] = bool(
            watchdog["raw_artifacts"] == expected_artifacts
            and actual_direct == expected_direct
            and all(
                record["present"] is True
                and (run_dir / name).is_file()
                or record["present"] is False
                and not (run_dir / name).exists()
                for name, record in expected_artifacts.items()
            )
        )
        if not all(checks.values()):
            problems.append("one_or_more_m6a_checks_failed")
        return {
            "schema": M6A_CHECK_SCHEMA,
            "status": "pass" if all(checks.values()) else "gate_failed",
            "pass": bool(all(checks.values())),
            "route": "M6A",
            "checks": checks,
            "problems": problems,
            "phase_checks": phase_checks,
            "phase_measurements": {
                phase: {"metrics": phase_details[phase].get("metrics"), "status": phase_details[phase].get("status")}
                for phase in ("mpi1", "mpi2")
            },
            "cross_mpi_recovery_relative_error": recovery_error,
            "source_sha256": watchdog["source_at_start"]["source_commit_full_sha"],
        }
    except (AttributeError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError, ImportError) as exc:
        problems.append(f"{type(exc).__name__}:{exc}")
        return {
            "schema": M6A_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "route": "M6A-review-only",
            "checks": checks,
            "problems": problems,
        }


def _check_command(args: argparse.Namespace) -> int:
    result = _check_raw(Path(args.run_dir).resolve())
    payload = _attach_evidence(result)
    _write_json(Path(args.output).resolve(), payload)
    print(json.dumps(payload, sort_keys=True), flush=True)
    return 0 if payload["pass"] is True else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("m6a-stage-worker", "m6a-watchdog"):
        item = sub.add_parser(name)
        item.add_argument("--run-dir", required=True)
    worker = sub.add_parser("m6a-worker")
    worker.add_argument("--run-dir", required=True)
    worker.add_argument("--phase", choices=("mpi1", "mpi2"), required=True)
    worker.add_argument("--expected-mpi-size", type=int, choices=(1, 2), required=True)
    checker = sub.add_parser("m6a-check")
    checker.add_argument("--run-dir", required=True)
    checker.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "m6a-stage-worker":
        return _stage_worker(Path(args.run_dir))
    if args.command == "m6a-worker":
        return _online_worker(Path(args.run_dir), args.phase, args.expected_mpi_size)
    if args.command == "m6a-watchdog":
        return _watchdog(Path(args.run_dir))
    if args.command == "m6a-check":
        return _check_command(args)
    raise RuntimeError(f"unsupported M6A command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
