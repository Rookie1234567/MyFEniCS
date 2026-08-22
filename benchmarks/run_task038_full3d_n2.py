"""Thin N2 local-spectral setup worker and process-tree watchdog.

The worker records one source-independent p6/h10 setup.  It reuses the
qualified N1 cell-patch and regional builders, then applies the current
volume-plus-dynamic-DtN action only to build ``AZ32`` and ``E32``.  No source,
residual, contraction solve, global matrix, or direct coarse solve is created.
Large numeric objects are written as owner-local ignored artifacts; the
independent checker owns all conclusions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping

import numpy as np


N2_SCHEMA = "task038.full3d.local-spectral.n2-record.v1"
N2_WATCHDOG_RAW_SCHEMA = "task038.full3d.local-spectral.n2-watchdog-raw.v1"
N2_WATCHDOG_COMPACT_SCHEMA = "task038.full3d.local-spectral.n2-watchdog-compact.v1"
N2_PROFILE = "full3d_scalable_v1"
N2_DEGREE = 6
N2_MESH_TARGET_NM = 10.0
N2_RANK = 32
N2_REGIONAL_RANK = 16
N2_MODE_CAP = 8
N2_MAX_CLASSES = 32
N2_FACTOR_BYTES_LIMIT = 6_230_448
N2_WARN_BYTES = 1_800_000_000
N2_HARD_BYTES = 2_000_000_000
N2_RETAINED_HARD_BYTES = 1_798_919_864
N2_MODE_SHARD_HARD_BYTES = 252 * 882 * 8 * 16
N2_POST_SETUP_DWELL_SECONDS = 2.2
N2_CASES = {"p6-h10-mpi1": 1, "p6-h10-mpi2": 2}
N2_MARKERS = (
    "preflight",
    "mesh_space_mpc",
    "JIT",
    "subdomain_inventory",
    "local_factor_build",
    "local_mode_build",
    "regional_coarse_build",
    "top_level_build",
    "identity_apply",
    "post_setup_release",
    "canonical_evidence",
    "cleanup",
    "failure",
)
N2_DIAGNOSTIC_MARKERS = ("linear_algebra_diagnostic",)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return str(value)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_probe(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Git probe failed")
    return result.stdout.strip()


def _source_identity(root: Path, expected_sha: str) -> dict[str, Any]:
    actual = _git_probe(root, "rev-parse", "HEAD")
    tracked_status = _git_probe(
        root, "status", "--short", "--untracked-files=all"
    )
    if actual != expected_sha:
        raise RuntimeError(
            f"source SHA mismatch: actual={actual}, expected={expected_sha}"
        )
    if tracked_status:
        raise RuntimeError(
            "formal source is not clean: " + tracked_status.replace("\n", "; ")
        )
    return {
        "expected_sha": expected_sha,
        "source_git_sha": actual,
        "tracked_status": tracked_status,
    }


def _runtime_preflight(
    root: Path, expected_sha: str, expected_mpi: int, actual_mpi: int
) -> dict[str, Any]:
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation marker is not 1")
    identity = _source_identity(root, expected_sha)
    executable = Path(sys.executable).absolute()
    qualified_bin = (root / ".venv" / "bin").resolve()
    if executable.parent.resolve() != qualified_bin:
        raise RuntimeError(f"unqualified executable: {executable}")
    threads = {
        name: os.environ.get(name)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if any(value not in (None, "1") for value in threads.values()):
        raise RuntimeError(f"threads are not fixed to one: {threads}")
    from mpi4py import MPI
    from petsc4py import PETSc

    import basix
    import dolfinx
    import mpi4py
    import petsc4py
    import slepc4py

    scalar = np.dtype(PETSc.ScalarType)
    integer = np.dtype(PETSc.IntType)
    if scalar != np.dtype(np.complex128) or integer != np.dtype(np.int32):
        raise RuntimeError(f"ABI dtype mismatch: scalar={scalar}, int={integer}")
    if int(actual_mpi) != int(expected_mpi):
        raise RuntimeError(
            f"MPI size mismatch: actual={actual_mpi}, expected={expected_mpi}"
        )
    return {
        "qualified_activation": "1",
        "sys_executable": str(executable),
        "qualified_venv_bin_resolved": str(qualified_bin),
        "python": sys.version,
        "mpi_size": int(actual_mpi),
        "mpi_library": str(MPI.Get_library_version()).splitlines()[0],
        "petsc4py": str(petsc4py.__file__),
        "slepc4py": str(slepc4py.__file__),
        "dolfinx": str(dolfinx.__file__),
        "basix": str(basix.__file__),
        "mpi4py": str(mpi4py.__file__),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "scalar_dtype": str(scalar),
        "int_dtype": str(integer),
        "threads": threads,
        "source_identity": identity,
    }


def _rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("VmRSS is unavailable")


def _swap_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmSwap:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("VmSwap is unavailable")


def _rank_resource(comm: Any) -> dict[str, int]:
    from mpi4py import MPI

    return {
        "rank_max_current_rss_bytes": int(comm.allreduce(_rss_bytes(), op=MPI.MAX)),
        "rank_max_current_swap_bytes": int(comm.allreduce(_swap_bytes(), op=MPI.MAX)),
    }


def _prepare_paths(raw_dir: Path, record: Path, marker_dir: Path, comm: Any) -> None:
    failure = None
    if comm.rank == 0:
        try:
            if raw_dir.exists() or record.exists() or marker_dir.exists():
                raise FileExistsError("N2 raw, record, or marker path already exists")
            raw_dir.mkdir(parents=True)
            marker_dir.mkdir(parents=True)
            record.parent.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, OSError) as exc:
            failure = (type(exc).__name__, str(exc))
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        if failure[0] == "FileExistsError":
            raise FileExistsError(failure[1])
        raise OSError(failure[1])
    comm.barrier()


def _write_marker(marker_dir: Path, name: str, source_sha: str, comm: Any, **details: Any) -> None:
    if name not in N2_MARKERS and name not in N2_DIAGNOSTIC_MARKERS:
        raise ValueError(f"unknown N2 marker: {name}")
    payload = {
        "schema": "task038.full3d.local-spectral.n2-marker.v1",
        "marker": name,
        "monotonic_ns": time.monotonic_ns(),
        "wall_time_ns": time.time_ns(),
        "source_git_sha": source_sha,
        "details": _jsonable(details),
    }
    if comm.rank == 0:
        path = marker_dir / f"{name}.json"
        if path.exists():
            raise FileExistsError(f"N2 marker already exists: {path}")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=marker_dir, delete=False
        ) as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            temporary = Path(stream.name)
        os.replace(temporary, path)
        print(json.dumps(payload, sort_keys=True), flush=True)
    comm.barrier()


def _marker_ledger(marker_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads((marker_dir / f"{name}.json").read_text(encoding="utf-8"))
        for name in N2_MARKERS
        if (marker_dir / f"{name}.json").is_file()
    ]


def _last_marker(marker_dir: Path) -> str | None:
    ledger = _marker_ledger(marker_dir)
    return None if not ledger else str(ledger[-1]["marker"])


def _collective_stage(comm: Any, label: str, action: Callable[[], Any]) -> Any:
    value = None
    error = None
    try:
        value = action()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    errors = comm.gather(error, root=0)
    failure = None
    if comm.rank == 0:
        failures = [item for item in errors if item is not None]
        if failures:
            failure = f"{label} failed: {failures[0]}"
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        raise RuntimeError(failure)
    return value


def _new_full_vector(space: Any):
    from dolfinx.la.petsc import create_vector

    index_map = space.dofmap.index_map
    return create_vector([(index_map, space.dofmap.index_map_bs)])


def _set_vector_owned(vector: Any, values: np.ndarray) -> None:
    from petsc4py import PETSc

    with vector.localForm() as local:
        local.set(0.0)
        local.array_w[: values.size] = np.asarray(values, dtype=np.complex128)
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )


def _write_owner_array(path: Path, values: np.ndarray) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"N2 array already exists: {path}")
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 2 or not np.all(np.isfinite(array)):
        raise ValueError("N2 owner array must be finite two-dimensional complex128")
    output = np.lib.format.open_memmap(
        path, mode="w+", dtype=np.complex128, shape=array.shape
    )
    try:
        for column in range(array.shape[1]):
            output[:, column] = array[:, column]
        output.flush()
    finally:
        output.flush()
        del output
    return {
        "path": str(path),
        "sha256": _sha256_path(path),
        "bytes": int(path.stat().st_size),
        "shape": list(array.shape),
        "dtype": "complex128",
    }


def _write_small_array(path: Path, values: np.ndarray) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"N2 array already exists: {path}")
    array = np.asarray(values, dtype=np.complex128)
    np.save(path, array, allow_pickle=False)
    return {
        "path": str(path),
        "sha256": _sha256_path(path),
        "bytes": int(path.stat().st_size),
        "shape": list(array.shape),
        "dtype": "complex128",
    }


def _augment_process_tree_memory(authority: Mapping[str, Any]) -> dict[str, Any]:
    """Add PSS/USS facts to the shared RSS/swap process-tree sample."""

    result = dict(authority)
    tree = dict(result["process_tree"])
    pids = tuple(int(pid) for pid in tree.get("pids", ()))
    pss_total = 0
    uss_total = 0
    readable = True
    for pid in pids:
        try:
            fields = {}
            for line in Path(f"/proc/{pid}/smaps_rollup").read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key] = int(value.split()[0]) * 1024
            pss_total += int(fields["Pss"])
            uss_total += int(fields.get("Private_Clean", 0))
            uss_total += int(fields.get("Private_Dirty", 0))
            uss_total += int(fields.get("Private_Hugetlb", 0))
        except (OSError, KeyError, ValueError):
            readable = False
    tree["pss_bytes"] = int(pss_total)
    tree["uss_bytes"] = int(uss_total)
    tree["pss_uss_readable"] = bool(readable)
    result["process_tree"] = tree
    cgroup = result.get("job_cgroup")
    if isinstance(cgroup, Mapping):
        result["dedicated_cgroup_swap_bytes"] = (
            None
            if not cgroup.get("dedicated_job_cgroup")
            else cgroup.get("swap_current_bytes")
        )
    return result


def _write_canonical_matrix(
    root: Path,
    role: str,
    space: Any,
    mpc: Any,
    floquet_data: Any,
    basis: Any,
    coarse: Any,
    comm: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_matrix_artifacts import write_canonical_matrix_shard
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    work = _new_full_vector(space)

    def column(index: int):
        if role == "full_fe":
            _set_vector_owned(work, basis.columns[:, index])
            packets, _audit = extract_canonical_full_fe_packets(
                space, work, floquet_data
            )
        else:
            _set_vector_owned(work, coarse.az[:, index])
            packets, _audit = extract_canonical_full_fe_dual_packets(
                space, mpc, work
            )
        return packets

    try:
        result = write_canonical_matrix_shard(
            root,
            role=role,
            column_count=N2_RANK,
            columns=column,
            extractor_audit={
                "role": role,
                "owner_local_streaming": True,
                "numeric_allgather": False,
                "physical_owned_row_order": True,
            },
            comm=comm,
        )
    finally:
        work.destroy()
    descriptor = None
    if comm.rank == 0:
        descriptor = {
            "role": role,
            "manifest_path": str(result["manifest_path"]),
            "manifest_sha256": result["manifest_sha256"],
            "global_packet_count": int(result["manifest"]["global_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _build_case(root: Path, args: argparse.Namespace, comm: Any) -> dict[str, Any]:
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_ordered_mode_manifest,
    )
    from src.solvers.fullspace_slab_interface import build_fullspace_slab_interface

    _specification, cfg, resolved = _resolve_case(
        root, args.input, N2_DEGREE, N2_MESH_TARGET_NM
    )
    modes, _rows, dynamic_sha = build_dynamic_mode_inventory(cfg)
    _, mode_bytes, mode_sha = build_ordered_mode_manifest(modes, cfg)
    mesh_data = build_airbox_mesh_3d(cfg, args.raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    _topology = build_fullspace_slab_interface(space, mesh_data, floquet_data, cfg)
    return {
        "cfg": cfg,
        "resolved": resolved,
        "modes": modes,
        "mode_bytes": mode_bytes,
        "mode_sha": mode_sha,
        "dynamic_mode_sha": dynamic_sha,
        "mesh_data": mesh_data,
        "raw_space": raw_space,
        "floquet_data": floquet_data,
        "space": space,
        "comm": comm,
    }


def _build_local_patches(case: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    from src.solvers.fullspace_local_spectral_dolfinx import (
        build_real_local_spectral_patches,
    )

    patches, audit = build_real_local_spectral_patches(
        case["space"],
        case["mesh_data"],
        case["floquet_data"],
        case["cfg"],
        reuse_class_templates=True,
        certification_v2=True,
    )
    return patches, audit


def _build_regional(case: dict[str, Any], patches: tuple[Any, ...]):
    from src.solvers.fullspace_local_spectral_dolfinx import (
        build_real_local_regional_rayleigh_ritz,
    )

    return build_real_local_regional_rayleigh_ritz(
        patches,
        case["space"],
        case["mesh_data"],
        case["floquet_data"],
        case["cfg"],
        return_multilevel=True,
    )


def _build_physical_action(case: Mapping[str, Any], comm: Any):
    from benchmarks.run_task038_full3d_r4 import _make_surface_assemblers
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from src.solvers.fullspace_dtn_action import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction

    cfg = case["cfg"]
    modes = case["modes"]
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = _make_surface_assemblers(
        case["raw_space"], case["mesh_data"], cfg, qdegree
    )
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, case["floquet_data"].mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    bilinear, _rhs = _build_variational_forms(
        case["mesh_data"].mesh,
        case["mesh_data"],
        cfg,
        case["raw_space"],
        field_formulation="total_field",
    )
    volume_action = build_fullspace_mpc_form_action(
        bilinear, case["raw_space"], mpc=case["floquet_data"].mpc
    )
    return FullspacePhysicalAction(volume_action, dtn_action)


def _zero_identity_apply(
    case: Mapping[str, Any], physical_action: Any, comm: Any
) -> dict[str, Any]:
    """Measure one zero-input physical action without retaining its work Vecs."""

    from mpi4py import MPI

    index_map = case["space"].dofmap.index_map
    local_rows = int(index_map.local_range[1] - index_map.local_range[0])
    source = _new_full_vector(case["space"])
    target = _new_full_vector(case["space"])
    try:
        _set_vector_owned(source, np.zeros(local_rows, dtype=np.complex128))
        started = time.perf_counter()
        physical_action.apply(source, target)
        elapsed = time.perf_counter() - started
        with target.localForm() as local:
            values = np.asarray(local.array_r)
            finite = bool(np.all(np.isfinite(values)))
            local_max_abs = float(np.max(np.abs(values))) if values.size else 0.0
        finite_global = bool(comm.allreduce(finite, op=MPI.LAND))
        max_abs = float(comm.allreduce(local_max_abs, op=MPI.MAX))
        output_norm = float(target.norm())
        elapsed_max = float(comm.allreduce(elapsed, op=MPI.MAX))
        if not finite_global or not np.isfinite(output_norm) or max_abs != 0.0:
            raise RuntimeError(
                "N2 zero identity apply failed: "
                f"finite={finite_global}, output_norm={output_norm:.17g}, "
                f"max_abs={max_abs:.17g}"
            )
        return {
            "kind": "setup_zero_identity_apply",
            "input_norm": 0.0,
            "output_norm": output_norm,
            "output_max_abs": max_abs,
            "finite": finite_global,
            "zero_output": max_abs == 0.0,
            "wall_seconds_rank_max": elapsed_max,
            "physical_action_apply_count": int(
                physical_action.audit["apply_count"]
            ),
            "rho_run": False,
            "ksp_created": False,
            "source_independent": True,
        }
    finally:
        target.destroy()
        source.destroy()


def _retained_components(
    basis: Any,
    coarse: Any,
    patch_audit: Mapping[str, Any],
    physical_action: Any,
    comm: Any,
) -> dict[str, Any]:
    from mpi4py import MPI

    z16 = int(basis.regional_columns.nbytes)
    z32 = int(basis.columns.nbytes)
    az32 = int(coarse.az.nbytes)
    e32 = int(coarse.e.nbytes)
    positions = int(basis.active_row_positions.nbytes)
    factor_local = int(patch_audit["owner_factor_bytes"])
    factor_global = int(patch_audit["global_owner_factor_bytes"])
    factor_count_global = int(patch_audit["global_owner_factor_count"])
    mode_global = int(patch_audit["mode_shard_bytes_retained_global"])
    action_audit = dict(getattr(physical_action, "audit", {}))
    volume_audit = action_audit["volume_action"]
    dtn_audit = action_audit["dtn_action"]
    volume_bytes = int(volume_audit["retained_numeric_payload_global_sum_bytes"])
    dtn_numeric_bytes = int(dtn_audit["retained_numeric_bytes_global_sum"])
    dtn_identity_bytes = int(
        comm.allreduce(int(dtn_audit["retained_identity_bytes"]), op=MPI.SUM)
    )
    dtn_work_bytes = int(dtn_audit["bounded_work_bytes_global_sum"])
    dtn_recovery_bytes = int(
        comm.allreduce(int(dtn_audit["recovery_output_bytes"]), op=MPI.SUM)
    )
    action_bytes = (
        volume_bytes
        + dtn_numeric_bytes
        + dtn_identity_bytes
        + dtn_work_bytes
        + dtn_recovery_bytes
    )
    work_bytes = int(
        coarse.audit["resident_work_vector_bytes"]["global_sum"]
    )
    metadata_budget = 64_000_000
    numeric_global = int(
        comm.allreduce(z16 + z32 + az32 + e32 + positions, op=MPI.SUM)
    )
    total = (
        factor_global
        + mode_global
        + numeric_global
        + action_bytes
        + work_bytes
        + metadata_budget
    )
    return {
        "factor_bytes_global": factor_global,
        "factor_bytes_local": factor_local,
        "factor_count_global": factor_count_global,
        "patch_mode_shard_bytes_global": mode_global,
        "patch_mode_shard_bytes_limit": N2_MODE_SHARD_HARD_BYTES,
        "regional_z16_bytes_global": int(comm.allreduce(z16, op=MPI.SUM)),
        "top_z32_bytes_global": int(comm.allreduce(z32, op=MPI.SUM)),
        "az32_bytes_global": int(comm.allreduce(az32, op=MPI.SUM)),
        "e32_bytes_global": int(comm.allreduce(e32, op=MPI.SUM)),
        "active_positions_bytes_global": int(comm.allreduce(positions, op=MPI.SUM)),
        "physical_action_volume_bytes_global": volume_bytes,
        "physical_action_dtn_numeric_bytes_global": dtn_numeric_bytes,
        "physical_action_dtn_identity_bytes_global": dtn_identity_bytes,
        "physical_action_dtn_work_bytes_global": dtn_work_bytes,
        "physical_action_dtn_recovery_bytes_global": dtn_recovery_bytes,
        "physical_action_bytes_global": action_bytes,
        "coarse_work_vector_bytes_global": work_bytes,
        "canonical_metadata_budget_bytes": metadata_budget,
        "canonical_metadata_budget_included": True,
        "numeric_component_bytes_global": numeric_global,
        "retained_closure_bytes_global": total,
        "retained_closure_limit_bytes": N2_RETAINED_HARD_BYTES,
        "provenance": "exact ndarray/audit nbytes plus bounded N0 metadata envelope",
        "unbudgeted_unknown": 0,
    }


def _record(
    args: argparse.Namespace,
    case: Mapping[str, Any],
    runtime: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    patches: tuple[Any, ...],
    patch_audit: Mapping[str, Any],
    regional_audit: Mapping[str, Any],
    basis: Any,
    physical_action: Any,
    coarse: Any,
    identity_audit: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    stage_resources: Mapping[str, Any],
    retained: Mapping[str, Any],
) -> dict[str, Any]:
    input_path = args.input.resolve()
    return {
        "schema": N2_SCHEMA,
        "classification": "worker_facts_pending_independent_checker",
        "stage": "n2_setup",
        "case": args.case,
        "command": list(sys.argv),
        "degree": N2_DEGREE,
        "mesh_target_nm": N2_MESH_TARGET_NM,
        "profile": N2_PROFILE,
        "mpi": {"size": int(args.expected_mpi_size)},
        "regional_rank": N2_REGIONAL_RANK,
        "top_rank": N2_RANK,
        "mode_cap": N2_MODE_CAP,
        "levels": 2,
        "input": {
            "path": str(input_path),
            "file_sha256": _sha256_path(input_path),
            "resolved_config_sha256": hashlib.sha256(case["resolved"]).hexdigest(),
            "resolved_config_bytes": len(case["resolved"]),
        },
        "source_identity": dict(source_identity),
        "runtime": _jsonable(dict(runtime)),
        "model": {
            "profile": N2_PROFILE,
            "degree": N2_DEGREE,
            "mesh_target_nm": N2_MESH_TARGET_NM,
            "fixed_patch_rule": "one_owned_hexa_cell_plus_shared_entity_overlap",
            "reuse_class_templates": True,
            "max_exact_classes": N2_MAX_CLASSES,
            "max_patch_rows": 882,
            "factor_storage": "one_hash_owner_lower_packed_complex128_cholesky",
            "local_factor_certification_v2": patch_audit.get(
                "certification_v2_enabled", False
            ),
            "local_factor_certification_schema": patch_audit.get(
                "certification_v2_schema"
            ),
            "factor_bytes_limit": N2_FACTOR_BYTES_LIMIT,
            "gradient_count": 3,
            "positive_mode_count": 5,
            "mode_cap": N2_MODE_CAP,
            "regional_rank": N2_REGIONAL_RANK,
            "top_rank": N2_RANK,
            "levels": 2,
            "source_independent": True,
        },
        "markers": {
            "directory": str(args.marker_dir.resolve()),
            "ledger": _marker_ledger(args.marker_dir),
        },
        "mode_manifest": {
            "relative_path": "mode_manifest.json",
            "sha256": case["mode_sha"],
            "bytes": len(case["mode_bytes"]),
            "dynamic_inventory_sha256": case["dynamic_mode_sha"],
        },
        "inventory": {
            "patch_count_local": len(patches),
            "patch_audit": _jsonable(dict(patch_audit)),
            "regional_audit": _jsonable(dict(regional_audit)),
        },
        "basis": {
            "audit": _jsonable(dict(basis.audit)),
            "top_mixing_identity": {
                "schema": basis.audit["top_mixing_schema"],
                "seed": basis.audit["top_mixing_seed"],
                "rank": N2_RANK,
                "levels": 2,
            },
            "class_template_identity": {
                "class_digests": patch_audit["class_digests"],
                "class_owners": patch_audit["class_owners"],
                "class_representatives": patch_audit["class_representatives"],
                "mode_digest": patch_audit["mode_digest"],
                "mode_template_count": patch_audit["mode_template_count"],
                "class_template_mode_digests": patch_audit[
                    "class_template_mode_digests"
                ],
            },
        },
        "operator": {
            "audit": _jsonable(dict(physical_action.audit)),
            "t4_transmission_included": False,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "factor_materialized": False,
            "numeric_allgather": False,
            "outer_contraction_run": False,
            "global_direct_coarse_solve": False,
        },
        "identity_apply": _jsonable(dict(identity_audit)),
        "coarse": {"audit": _jsonable(dict(coarse.audit))},
        "artifacts": _jsonable(dict(artifacts)),
        "retained_components": _jsonable(dict(retained)),
        "resource": {
            "rank_max_current_phase": "all_setup_objects_alive_before_cleanup",
            "stage_rank_max_current": _jsonable(dict(stage_resources)),
            "process_tree_watchdog_required": True,
            "warning_bytes": N2_WARN_BYTES,
            "hard_stop_bytes": N2_HARD_BYTES,
        },
        "resource_contract": {"status": "pending_external_watchdog"},
        "no_rho": True,
        "not_n3": True,
    }


def _write_record(path: Path, record: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"N2 record already exists: {path}")
    path.write_text(
        json.dumps(_jsonable(record), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _failure_record(args: argparse.Namespace, exc: BaseException, runtime: Mapping[str, Any], comm: Any) -> None:
    if comm.rank != 0 or args.record.exists():
        return
    runtime_identity = runtime.get("source_identity")
    if not isinstance(runtime_identity, Mapping):
        runtime_identity = {
            "expected_sha": args.expected_sha,
            "source_git_sha": None,
            "tracked_status": "not_measured",
        }
    payload = {
        "schema": N2_SCHEMA,
        "classification": "controlled_negative",
        "stage": "n2_setup",
        "case": args.case,
        "source_identity": dict(runtime_identity),
        "raw_dir": str(args.raw_dir),
        "marker_dir": str(args.marker_dir),
        "failure": {"exception_type": type(exc).__name__, "message": str(exc)},
        "last_marker": _last_marker(args.marker_dir),
        "marker_ledger": _marker_ledger(args.marker_dir),
        "runtime": _jsonable(dict(runtime)),
        "planned": list(N2_MARKERS),
        "not_run": ["remaining N2 setup stages", "independent checker gates"],
    }
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _destroy(objects: Iterable[Any]) -> None:
    for obj in objects:
        if obj is None:
            continue
        try:
            obj.destroy()
        except Exception:
            pass


def _run_worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    root = Path.cwd().resolve()
    args.raw_dir = args.raw_dir.resolve()
    args.record = args.record.resolve()
    args.marker_dir = args.marker_dir.resolve()
    _prepare_paths(args.raw_dir, args.record, args.marker_dir, comm)
    runtime: dict[str, Any] = {}
    source_identity: dict[str, Any] = {"expected_sha": args.expected_sha, "source_git_sha": None, "tracked_status": "not_measured"}
    stage_resources: dict[str, Mapping[str, Any]] = {}
    case = None
    patches: tuple[Any, ...] = ()
    physical_action = None
    basis = None
    coarse = None
    identity_audit: dict[str, Any] = {}
    try:
        _write_marker(args.marker_dir, "preflight", args.expected_sha, comm, case=args.case)
        runtime = _collective_stage(
            comm, "preflight", lambda: _runtime_preflight(root, args.expected_sha, args.expected_mpi_size, comm.size)
        )
        source_identity = runtime["source_identity"]
        _write_marker(args.marker_dir, "mesh_space_mpc", args.expected_sha, comm, profile=N2_PROFILE)
        case = _collective_stage(comm, "mesh_space_mpc", lambda: _build_case(root, args, comm))
        _write_marker(
            args.marker_dir,
            "JIT",
            args.expected_sha,
            comm,
            api="volume_plus_dynamic_DtN_build",
            baseline_before_local_spectral_objects=True,
        )
        physical_action = _collective_stage(
            comm,
            "physical_action_build",
            lambda: _build_physical_action(case, comm),
        )
        stage_resources["JIT"] = _rank_resource(comm)
        _write_marker(args.marker_dir, "subdomain_inventory", args.expected_sha, comm, api="build_real_local_spectral_patches", coalesced_factor_and_mode_build=True)
        _write_marker(args.marker_dir, "local_factor_build", args.expected_sha, comm, api="build_real_local_spectral_patches", exact_class_reuse=True)
        patches, patch_audit = _collective_stage(comm, "local_factor_and_mode_build", lambda: _build_local_patches(case))
        _write_marker(args.marker_dir, "local_mode_build", args.expected_sha, comm, completed_by="build_real_local_spectral_patches", mode_cap=N2_MODE_CAP)
        _write_marker(args.marker_dir, "regional_coarse_build", args.expected_sha, comm, api="build_real_local_regional_rayleigh_ritz", rank=N2_REGIONAL_RANK)
        _, regional_audit, basis = _collective_stage(comm, "regional_coarse_build", lambda: _build_regional(case, patches))
        _write_marker(args.marker_dir, "top_level_build", args.expected_sha, comm, completed_by="build_real_local_regional_rayleigh_ritz", rank=N2_RANK)
        if basis.audit.get("construction_workspace_released") is not True:
            raise RuntimeError("N2 basis construction workspace was not released")
        _write_marker(args.marker_dir, "identity_apply", args.expected_sha, comm, purpose="setup_AZ_E_repeat_only", rho_not_run=True)
        identity_audit = _collective_stage(
            comm,
            "zero_identity_apply",
            lambda: _zero_identity_apply(case, physical_action, comm),
        )
        from src.solvers.fullspace_adaptive_coarse import FullspaceAdaptiveCoarse

        coarse = FullspaceAdaptiveCoarse(basis, physical_action, lambda: _new_full_vector(case["space"]))
        _collective_stage(comm, "identity_apply", coarse.build)
        _collective_stage(comm, "identity_apply_prefix", coarse.prefix_audit)
        stage_resources["identity_apply"] = _rank_resource(comm)
        _write_marker(
            args.marker_dir,
            "post_setup_release",
            args.expected_sha,
            comm,
            construction_workspace_released=True,
            retained_regional_and_top=True,
            all_az_e_objects_alive=True,
            measurement_dwell_seconds=N2_POST_SETUP_DWELL_SECONDS,
            measurement_dwell_scope="post_setup_retained_objects_only",
        )
        stage_resources["post_setup_release"] = _rank_resource(comm)
        time.sleep(N2_POST_SETUP_DWELL_SECONDS)
        _write_marker(args.marker_dir, "canonical_evidence", args.expected_sha, comm, roles=("full_fe", "full_fe_dual"), numeric_allgather=False)
        z_path = args.raw_dir / f"Z32.rank{comm.rank:04d}.npy"
        az_path = args.raw_dir / f"AZ32.rank{comm.rank:04d}.npy"
        regional_path = args.raw_dir / f"Z16.rank{comm.rank:04d}.npy"
        index_map = case["space"].dofmap.index_map
        ownership_range = tuple(int(value) for value in index_map.local_range)
        if ownership_range[1] - ownership_range[0] != basis.columns.shape[0]:
            raise RuntimeError(
                "PETSc ownership range does not match physical owned rows: "
                f"range={ownership_range}, rows={basis.columns.shape[0]}"
            )
        arrays = {
            "Z16": _write_owner_array(regional_path, basis.regional_columns),
            "Z32": _write_owner_array(z_path, basis.columns),
            "AZ32": _write_owner_array(az_path, coarse.az),
            "ownership_range": list(ownership_range),
            "owner_rank": int(comm.rank),
            "local_owned_rows": int(basis.columns.shape[0]),
        }
        array_parts = comm.gather(arrays, root=0)
        if comm.rank == 0:
            arrays = {
                "owner_shards": [
                    {"rank": int(rank), **dict(shard)}
                    for rank, shard in enumerate(array_parts)
                ],
                "global_owned_rows": int(
                    sum(int(shard["local_owned_rows"]) for shard in array_parts)
                ),
            }
        arrays = comm.bcast(arrays, root=0)
        e_descriptor = None
        if comm.rank == 0:
            e_descriptor = _write_small_array(args.raw_dir / "E32.npy", coarse.e)
        e_descriptor = comm.bcast(e_descriptor, root=0)
        canonical = {
            "Z32": _write_canonical_matrix(args.raw_dir / "canonical" / "Z32", "full_fe", case["space"], case["floquet_data"].mpc, case["floquet_data"], basis, coarse, comm),
            "AZ32": _write_canonical_matrix(args.raw_dir / "canonical" / "AZ32", "full_fe_dual", case["space"], case["floquet_data"].mpc, case["floquet_data"], basis, coarse, comm),
        }
        mode_path = args.raw_dir / "mode_manifest.json"
        if comm.rank == 0:
            mode_path.write_bytes(case["mode_bytes"])
        comm.barrier()
        artifacts = {"arrays": arrays, "E32": e_descriptor, "canonical_matrices": canonical, "mode_manifest": {"path": str(mode_path), "sha256": _sha256_path(mode_path), "bytes": int(mode_path.stat().st_size)}}
        retained = _retained_components(basis, coarse, patch_audit, physical_action, comm)
        if retained["retained_closure_bytes_global"] > N2_RETAINED_HARD_BYTES:
            raise RuntimeError(f"N2 retained closure {retained['retained_closure_bytes_global']} exceeds limit {N2_RETAINED_HARD_BYTES}")
        record = _record(args, case, runtime, source_identity, patches, patch_audit, regional_audit, basis, physical_action, coarse, identity_audit, artifacts, stage_resources, retained)
        _write_marker(args.marker_dir, "cleanup", args.expected_sha, comm, sample_before_destroy=True)
        _destroy((coarse, physical_action, basis))
        for patch in patches:
            patch.destroy()
        if patches:
            patches[0].class_plan.destroy()
        cleanup_resource = _rank_resource(comm)
        record["resource"]["cleanup_rank_max_current"] = cleanup_resource
        record["markers"]["ledger"] = _marker_ledger(args.marker_dir)
        if comm.rank == 0:
            _write_record(args.record, record)
        comm.barrier()
        return 0
    except Exception as exc:
        _destroy((coarse, physical_action, basis))
        for patch in patches:
            patch.destroy()
        try:
            if not (args.marker_dir / "failure.json").exists():
                _write_marker(args.marker_dir, "failure", args.expected_sha, comm, exception_type=type(exc).__name__, message=str(exc))
        finally:
            _failure_record(args, exc, runtime, comm)
        return 1


def _watchdog_stage(marker_dir: Path) -> str:
    return _last_marker(marker_dir) or "startup"


def _extract_worker_owned_paths(
    command: Iterable[str], cwd: Path
) -> tuple[Path, Path]:
    tokens = tuple(command)

    def extract(flag: str) -> Path:
        positions = tuple(index for index, token in enumerate(tokens) if token == flag)
        if len(positions) != 1 or positions[0] + 1 >= len(tokens):
            raise ValueError(f"watchdog command must contain one {flag} value")
        value = tokens[positions[0] + 1]
        if not value or value.startswith("-"):
            raise ValueError(f"watchdog command has an invalid {flag} value")
        path = Path(value)
        return (path if path.is_absolute() else cwd / path).resolve(strict=False)

    return extract("--raw-dir"), extract("--marker-dir")


def _validate_watchdog_ownership(
    command: Iterable[str], outputs: Iterable[Path], cwd: Path
) -> tuple[Path, Path]:
    worker_paths = _extract_worker_owned_paths(command, cwd)
    for path in worker_paths:
        if path.exists():
            raise FileExistsError(f"worker-owned path already exists: {path}")
    for output in outputs:
        resolved = (output if output.is_absolute() else cwd / output).resolve(
            strict=False
        )
        if any(
            resolved == owned
            or owned in resolved.parents
            or resolved in owned.parents
            for owned in worker_paths
        ):
            raise ValueError(
                f"watchdog output overlaps worker-owned path: {resolved}"
            )
    return worker_paths


def _watchdog_compact(raw_sha: str, command: Iterable[str], stop_reason: str, return_code: int, termination: Mapping[str, Any], samples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = tuple(samples)
    valid = [row for row in rows if isinstance(row.get("authority"), Mapping) and not row.get("authority_error")]
    peaks: dict[str, int] = {}
    rss_peaks: dict[str, int] = {}
    pss_peaks: dict[str, int] = {}
    uss_peaks: dict[str, int] = {}
    cgroup_swap_peaks: dict[str, int] = {}
    for row in valid:
        stage = str(row.get("stage", "unknown"))
        authority = row["authority"]
        tree = authority.get("process_tree", {})
        peaks[stage] = max(peaks.get(stage, 0), int(authority.get("memory_authority_bytes", 0)))
        rss_peaks[stage] = max(rss_peaks.get(stage, 0), int(tree.get("rss_bytes", 0)))
        pss_peaks[stage] = max(pss_peaks.get(stage, 0), int(tree.get("pss_bytes", 0)))
        uss_peaks[stage] = max(uss_peaks.get(stage, 0), int(tree.get("uss_bytes", 0)))
        cgroup_swap = authority.get("dedicated_cgroup_swap_bytes")
        if cgroup_swap is not None:
            cgroup_swap_peaks[stage] = max(cgroup_swap_peaks.get(stage, 0), int(cgroup_swap))
    authority_ok = bool(rows) and len(valid) == len(rows)
    swap_ok = authority_ok and all(
        isinstance(row["authority"].get("process_tree"), Mapping)
        and int(row["authority"]["process_tree"].get("swap_bytes", -1)) == 0
        for row in valid
    )
    peak = max(peaks.values(), default=0)
    post_setup_peak = peaks.get("post_setup_release", 0)
    post_setup_sample_count = sum(
        1 for row in valid if row.get("stage") == "post_setup_release"
    )
    return {
        "schema": N2_WATCHDOG_COMPACT_SCHEMA,
        "raw_sha256": raw_sha,
        "command": list(command),
        "stop_reason": stop_reason,
        "worker_returncode": int(return_code),
        "termination": _jsonable(dict(termination)),
        "authority_samples": len(rows),
        "authority_complete": authority_ok,
        "process_tree_swap_gate": bool(swap_ok),
        "process_tree_peak_memory_authority_bytes": peak,
        "warning_bytes": N2_WARN_BYTES,
        "hard_stop_bytes": N2_HARD_BYTES,
        "stage_peak_memory_authority_bytes": peaks,
        "stage_peak_process_tree_rss_bytes": rss_peaks,
        "stage_peak_process_tree_pss_bytes": pss_peaks,
        "stage_peak_process_tree_uss_bytes": uss_peaks,
        "stage_peak_dedicated_cgroup_swap_bytes": cgroup_swap_peaks,
        "warning_crossed": bool(peak >= N2_WARN_BYTES),
        "post_setup_peak_memory_authority_bytes": int(post_setup_peak),
        "post_setup_sample_count": int(post_setup_sample_count),
        "post_setup_warning_crossed": bool(post_setup_peak >= N2_WARN_BYTES),
        "natural_exit": stop_reason == "natural_exit" and return_code == 0,
        "no_orphan_claim": bool(
            dict(termination).get("process_group_exited") is True
            and stop_reason != "orphan_cleanup_required"
        ),
    }


def _backfill_watchdog(record_path: Path, raw_path: Path, compact_path: Path, compact: Mapping[str, Any], marker_dir: Path, return_code: int, stop_reason: str) -> None:
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
    else:
        record = {
            "schema": N2_SCHEMA,
            "classification": "controlled_negative",
            "case": None,
            "source_identity": {"expected_sha": None, "source_git_sha": None, "tracked_status": "not_measured"},
            "raw_dir": str(raw_path.parent),
            "marker_dir": str(marker_dir),
            "last_marker": _watchdog_stage(marker_dir),
            "marker_ledger": _marker_ledger(marker_dir),
            "failure": {"exception_type": "ExternalWatchdogStop", "message": stop_reason},
            "not_run": ["worker record", "remaining N2 stages"],
        }
    record["resource_contract"] = {
        "status": "measured" if record.get("classification") != "controlled_negative" else "measured_controlled_negative",
        "raw_path": str(raw_path),
        "raw_sha256": _sha256_path(raw_path),
        "compact_path": str(compact_path),
        "compact_sha256": _sha256_path(compact_path),
        "stop_reason": stop_reason,
        "worker_returncode": int(return_code),
        "process_tree_peak_memory_authority_bytes": int(compact.get("process_tree_peak_memory_authority_bytes", 0)),
        "post_setup_peak_memory_authority_bytes": int(compact.get("post_setup_peak_memory_authority_bytes", 0)),
        "post_setup_sample_count": int(compact.get("post_setup_sample_count", 0)),
        "warning_crossed": bool(compact.get("warning_crossed", False)),
        "post_setup_warning_crossed": bool(compact.get("post_setup_warning_crossed", False)),
        "stage_peak_process_tree_rss_bytes": dict(compact.get("stage_peak_process_tree_rss_bytes", {})),
        "stage_peak_process_tree_pss_bytes": dict(compact.get("stage_peak_process_tree_pss_bytes", {})),
        "stage_peak_process_tree_uss_bytes": dict(compact.get("stage_peak_process_tree_uss_bytes", {})),
        "stage_peak_dedicated_cgroup_swap_bytes": dict(compact.get("stage_peak_dedicated_cgroup_swap_bytes", {})),
        "process_tree_swap_gate": bool(compact.get("process_tree_swap_gate", False)),
        "authority_complete": bool(compact.get("authority_complete", False)),
        "natural_exit": bool(compact.get("natural_exit", False)),
        "no_orphan": bool(compact.get("no_orphan_claim", False)),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(_jsonable(record), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _watchdog_main(argv: list[str]) -> int:
    from benchmarks.task034_wsl_resources import resource_authority_sample
    from benchmarks.watchdog_process_control import terminate_process_tree, worker_process_group_popen_kwargs

    parser = argparse.ArgumentParser(description="N2 process-tree watchdog")
    parser.add_argument("--watchdog-record", type=Path, required=True)
    parser.add_argument("--watchdog-raw", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--watchdog-log", type=Path, required=True)
    parser.add_argument("--watchdog-marker-dir", type=Path, required=True)
    parser.add_argument("--watchdog-poll-seconds", type=float, default=1.0)
    parser.add_argument("--watchdog-timeout-seconds", type=float, default=0.0)
    parser.add_argument("--watchdog-command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args(argv)
    command = [item for item in args.watchdog_command if item != "--"]
    if not command or args.watchdog_timeout_seconds < 0.0:
        raise SystemExit("watchdog command/timeout is invalid")
    worker_paths = _validate_watchdog_ownership(
        command,
        (args.watchdog_record, args.watchdog_raw, args.watchdog_compact, args.watchdog_log),
        Path.cwd(),
    )
    for path in (args.watchdog_raw, args.watchdog_compact, args.watchdog_log):
        if path.exists():
            raise FileExistsError(f"watchdog artifact already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    for path in worker_paths:
        if path.exists():
            raise FileExistsError(f"watchdog created worker-owned path: {path}")
    with args.watchdog_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, **worker_process_group_popen_kwargs())
        samples: list[dict[str, Any]] = []
        started = time.monotonic()
        stop_reason = "natural_exit"
        termination: Mapping[str, Any] = {"requested": False, "method": "natural_exit", "process_group_exited": False}
        while process.poll() is None:
            try:
                authority = _augment_process_tree_memory(
                    resource_authority_sample(process.pid)
                )
                sample: dict[str, Any] = {"wall_time_ns": time.time_ns(), "elapsed_seconds": time.monotonic() - started, "stage": _watchdog_stage(args.watchdog_marker_dir), "authority": authority}
                samples.append(sample)
                tree = authority["process_tree"]
                memory = int(authority["memory_authority_bytes"])
                stop = None
                if not tree["all_status_readable"]:
                    stop = "authority_unreadable"
                elif not authority["job_no_swap"]:
                    stop = "swap_nonzero"
                elif memory >= N2_HARD_BYTES:
                    stop = "hard_stop_2gb"
                elif args.watchdog_timeout_seconds and time.monotonic() - started >= args.watchdog_timeout_seconds:
                    stop = "watchdog_timeout"
                if stop is not None:
                    stop_reason = stop
                    termination = terminate_process_tree(process)
                    break
            except Exception as exc:
                samples.append({"wall_time_ns": time.time_ns(), "elapsed_seconds": time.monotonic() - started, "stage": _watchdog_stage(args.watchdog_marker_dir), "authority_error": f"{type(exc).__name__}: {exc}"})
                stop_reason = "authority_unreadable"
                termination = terminate_process_tree(process)
                break
            time.sleep(max(float(args.watchdog_poll_seconds), 0.05))
        return_code = process.wait()
        if stop_reason == "natural_exit":
            try:
                verification = terminate_process_tree(process)
            except Exception as exc:
                verification = {
                    "requested": True,
                    "method": "cleanup_error",
                    "worker_exited": process.poll() is not None,
                    "process_group_exited": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            termination = verification
            if (
                verification.get("method") != "already_exited"
                or verification.get("process_group_exited") is not True
            ):
                stop_reason = "orphan_cleanup_required"
    raw = {"schema": N2_WATCHDOG_RAW_SCHEMA, "command": command, "samples": samples, "stop_reason": stop_reason, "termination": termination, "worker_returncode": return_code}
    args.watchdog_raw.write_text(json.dumps(_jsonable(raw), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    compact = _watchdog_compact(_sha256_path(args.watchdog_raw), command, stop_reason, return_code, termination, samples)
    args.watchdog_compact.write_text(json.dumps(_jsonable(compact), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _backfill_watchdog(args.watchdog_record, args.watchdog_raw, args.watchdog_compact, compact, args.watchdog_marker_dir, return_code, stop_reason)
    return int(return_code)


def _parse_worker(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="N2 local-spectral setup worker")
    parser.add_argument("--stage", choices=("n2",), required=True)
    parser.add_argument("--case", choices=tuple(N2_CASES), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--marker-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", dest="expected_sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    if args.expected_mpi_size != N2_CASES[args.case]:
        parser.error("expected MPI size does not match frozen N2 case")
    return args


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    if "--watchdog" in selected:
        return _watchdog_main([item for item in selected if item != "--watchdog"])
    return _run_worker(_parse_worker(selected))


if __name__ == "__main__":
    raise SystemExit(main())
