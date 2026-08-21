"""D2 owner-local adaptive-coarse worker and external resource wrapper.

The worker is intentionally a single p6/h10 rank-64 path.  It constructs the
trace-harmonic basis once, releases its construction workspace, builds the
online ``AZ/E`` data once, and writes only owner-local raw artifacts plus one
compact record.  Numerical conclusions belong to the later independent
checker; this module records facts and controlled failures.
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


D2_SCHEMA = "task038.full3d.adaptive-coarse.d2-record.v1"
D2_PROFILE = "full3d_scalable_v1"
D2_DEGREE = 6
D2_MESH_TARGET_NM = 10.0
D2_RANK = 64
D2_PREFIXES = (16, 32, 48, 64)
D2_CASES = {"p6-h10-mpi1": 1, "p6-h10-mpi2": 2}
D2_MARKERS = (
    "preflight",
    "mesh_mpc_topology",
    "trace_basis_build",
    "trace_workspace_release",
    "physical_action_build",
    "online_az_e",
    "canonical_evidence",
    "cleanup",
    "failure",
)
D2_MEMORY_HARD_STOP_BYTES = 12 * 1024**3


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
    root: Path,
    expected_sha: str,
    expected_mpi_size: int,
    actual_mpi_size: int,
) -> dict[str, Any]:
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation marker is not 1")
    source_identity = _source_identity(root, expected_sha)
    lexical_executable = Path(sys.executable).absolute()
    qualified_bin = (root / ".venv" / "bin").resolve()
    if lexical_executable.parent.resolve() != qualified_bin:
        raise RuntimeError(
            "sys.executable is outside the qualified repository venv: "
            f"{lexical_executable}"
        )
    thread_values = {
        name: os.environ.get(name)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if any(value not in (None, "1") for value in thread_values.values()):
        raise RuntimeError(f"thread count is not fixed to one: {thread_values}")
    from mpi4py import MPI
    from petsc4py import PETSc

    import basix
    import dolfinx
    import mpi4py
    import petsc4py
    import slepc4py

    scalar_dtype = np.dtype(PETSc.ScalarType)
    int_dtype = np.dtype(PETSc.IntType)
    if scalar_dtype != np.dtype(np.complex128):
        raise RuntimeError(f"PETSc scalar dtype is {scalar_dtype}")
    if int_dtype != np.dtype(np.int32):
        raise RuntimeError(f"PETSc integer dtype is {int_dtype}")
    if int(expected_mpi_size) != int(actual_mpi_size):
        raise RuntimeError(
            f"MPI size mismatch: actual={actual_mpi_size}, "
            f"expected={expected_mpi_size}"
        )
    return {
        "qualified_activation": "1",
        "sys_executable": str(lexical_executable),
        "qualified_venv_bin_resolved": str(qualified_bin),
        "python": sys.version,
        "mpi_size": int(actual_mpi_size),
        "mpi_library": str(MPI.Get_library_version()).splitlines()[0],
        "petsc4py": str(petsc4py.__file__),
        "slepc4py": str(slepc4py.__file__),
        "dolfinx": str(dolfinx.__file__),
        "basix": str(basix.__file__),
        "mpi4py": str(mpi4py.__file__),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "scalar_dtype": str(scalar_dtype),
        "int_dtype": str(int_dtype),
        "threads": thread_values,
        "source_identity": source_identity,
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

    rss = int(comm.allreduce(_rss_bytes(), op=MPI.MAX))
    swap = int(comm.allreduce(_swap_bytes(), op=MPI.MAX))
    return {"rank_max_current_rss_bytes": rss, "rank_max_current_swap_bytes": swap}


def _prepare_paths(
    raw_dir: Path, record_path: Path, marker_dir: Path, comm: Any
) -> None:
    failure: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            if raw_dir.exists() or record_path.exists() or marker_dir.exists():
                raise FileExistsError(
                    "D2 raw, record, or marker path already exists"
                )
            raw_dir.mkdir(parents=True)
            marker_dir.mkdir(parents=True)
            record_path.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError as exc:
            failure = ("FileExistsError", str(exc))
        except OSError as exc:
            failure = ("OSError", str(exc))
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        if failure[0] == "FileExistsError":
            raise FileExistsError(failure[1])
        raise OSError(failure[1])
    comm.barrier()


def _write_marker(
    marker_dir: Path,
    name: str,
    expected_sha: str,
    comm: Any,
    **details: Any,
) -> dict[str, Any] | None:
    if name not in D2_MARKERS:
        raise ValueError(f"unknown D2 marker: {name}")
    payload = {
        "schema": "task038.full3d.adaptive-coarse.d2-marker.v1",
        "marker": name,
        "monotonic_ns": time.monotonic_ns(),
        "wall_time_ns": time.time_ns(),
        "source_git_sha": expected_sha,
        "details": _jsonable(details),
    }
    if comm.rank == 0:
        path = marker_dir / f"{name}.json"
        if path.exists():
            raise FileExistsError(f"D2 marker already exists: {path}")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=marker_dir, delete=False
        ) as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            temporary = Path(stream.name)
        os.replace(temporary, path)
        print(json.dumps(payload, sort_keys=True), flush=True)
    comm.barrier()
    return payload if comm.rank == 0 else None


def _marker_ledger(marker_dir: Path) -> list[dict[str, Any]]:
    ledger = []
    for name in D2_MARKERS:
        path = marker_dir / f"{name}.json"
        if path.is_file():
            ledger.append(json.loads(path.read_text(encoding="utf-8")))
    return ledger


def _last_marker(marker_dir: Path) -> str | None:
    ledger = _marker_ledger(marker_dir)
    return None if not ledger else str(ledger[-1]["marker"])


def _write_failure_record(
    record_path: Path,
    raw_dir: Path,
    marker_dir: Path,
    expected_sha: str,
    failure: BaseException,
    planned: Iterable[str],
    not_run: Iterable[str],
    comm: Any,
    runtime: Mapping[str, Any] | None = None,
) -> None:
    if comm.rank != 0:
        return
    record = {
        "schema": D2_SCHEMA,
        "classification": "controlled_negative",
        "status": "controlled_negative",
        "raw_dir": str(raw_dir),
        "marker_dir": str(marker_dir),
        "source_identity": {
            "expected_sha": expected_sha,
            "source_git_sha": None,
            "tracked_status": "not_measured",
        },
        "failure": {
            "exception_type": type(failure).__name__,
            "message": str(failure),
        },
        "last_marker": _last_marker(marker_dir),
        "marker_ledger": _marker_ledger(marker_dir),
        "planned": list(planned),
        "not_run": list(not_run),
        "runtime": _jsonable(runtime or {}),
    }
    if record_path.exists():
        raise FileExistsError(f"D2 failure record already exists: {record_path}")
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _collective_stage(comm: Any, label: str, action: Callable[[], Any]) -> Any:
    local_error: str | None = None
    value = None
    try:
        value = action()
    except Exception as exc:  # the root records the first real stage failure
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.gather(local_error, root=0)
    failure = None
    if comm.rank == 0:
        failures = [item for item in errors if item is not None]
        if failures:
            failure = f"{label} failed: {failures[0]}"
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        raise RuntimeError(failure)
    return value


def _write_owner_matrix(
    path: Path,
    shape: tuple[int, int],
    column_values: Callable[[int], np.ndarray],
) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"D2 owner matrix already exists: {path}")
    matrix = np.lib.format.open_memmap(
        path, mode="w+", dtype=np.complex128, shape=shape
    )
    try:
        for index in range(shape[1]):
            values = np.asarray(column_values(index), dtype=np.complex128)
            if values.shape != (shape[0],):
                raise ValueError(
                    f"owner matrix column shape {values.shape} does not match "
                    f"{(shape[0],)}"
                )
            if not np.all(np.isfinite(values)):
                raise ValueError("owner matrix column is non-finite")
            matrix[:, index] = values
        matrix.flush()
    finally:
        matrix.flush()
        del matrix
    return {
        "path": str(path),
        "sha256": _sha256_path(path),
        "bytes": int(path.stat().st_size),
        "shape": list(shape),
        "dtype": "complex128",
    }


def _write_small_array(path: Path, values: np.ndarray) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"D2 small array already exists: {path}")
    np.save(path, np.asarray(values, dtype=np.complex128), allow_pickle=False)
    return {
        "path": str(path),
        "sha256": _sha256_path(path),
        "bytes": int(path.stat().st_size),
        "shape": list(np.asarray(values).shape),
        "dtype": "complex128",
    }


def _new_full_vector(space: Any):
    from dolfinx.la.petsc import create_vector

    index_map = space.dofmap.index_map
    return create_vector([(index_map, space.dofmap.index_map_bs)])


def _set_vector_owned(vector: Any, values: np.ndarray) -> None:
    from petsc4py import PETSc

    with vector.localForm() as local:
        local.set(0.0)
        local.array_w[: values.size] = values
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )


def _write_matrix_manifest(
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

    def columns(index: int):
        try:
            if role == "full_fe":
                basis.fill_column(index, work)
                packets, _audit = extract_canonical_full_fe_packets(
                    space, work, floquet_data
                )
            else:
                _set_vector_owned(work, coarse.az[:, index])
                packets, _audit = extract_canonical_full_fe_dual_packets(
                    space, mpc, work
                )
            return packets
        finally:
            work.set(0.0)

    try:
        result = write_canonical_matrix_shard(
            root,
            role=role,
            column_count=D2_RANK,
            columns=columns,
            extractor_audit={
                "role": role,
                "numeric_allgather": False,
                "owner_local_streaming": True,
            },
            comm=comm,
        )
    finally:
        work.destroy()
    descriptor = None
    if comm.rank == 0:
        manifest_path = Path(result["manifest_path"])
        descriptor = {
            "role": role,
            "manifest_relative_path": str(
                manifest_path.relative_to(root.parent.parent)
            ),
            "manifest_sha256": result["manifest_sha256"],
            "global_packet_count": int(result["manifest"]["global_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _setup_online_case(root: Path, args: argparse.Namespace, comm: Any):
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
        build_ordered_mode_manifest,
    )
    from src.solvers.fullspace_slab_interface import (
        build_fullspace_slab_interface,
    )

    _specification, cfg, resolved = _resolve_case(
        root, args.input, D2_DEGREE, D2_MESH_TARGET_NM
    )
    modes, _dynamic_rows, _dynamic_sha = build_dynamic_mode_inventory(cfg)
    mode_bytes = build_ordered_mode_manifest(modes, cfg)[1]
    mesh_data = build_airbox_mesh_3d(cfg, args.raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    topology = build_fullspace_slab_interface(
        space, mesh_data, floquet_data, cfg
    )
    return {
        "cfg": cfg,
        "resolved": resolved,
        "modes": modes,
        "mode_bytes": mode_bytes,
        "mesh_data": mesh_data,
        "raw_space": raw_space,
        "floquet_data": floquet_data,
        "space": space,
        "topology": topology,
    }


def _build_trace_basis(case: dict[str, Any]):
    from src.solvers.fullspace_trace_harmonic import TraceHarmonicDefinition
    from src.solvers.fullspace_trace_harmonic_distributed import (
        DistributedTraceHarmonicBasis,
    )

    definitions = tuple(
        TraceHarmonicDefinition(
            topology=case["topology"],
            mesh_data=case["mesh_data"],
            raw_function_space=case["raw_space"],
            mpc=case["floquet_data"].mpc,
            slab_id=slab_id,
        )
        for slab_id in (0, 1)
    )
    basis = DistributedTraceHarmonicBasis(definitions)
    basis.build(rank=D2_RANK, requested_eigenpairs=D2_RANK)
    case["basis"] = basis
    case["definitions"] = definitions
    return case


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
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = _make_surface_assemblers(
        case["raw_space"],
        case["mesh_data"],
        cfg,
        quadrature_degree,
    )
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, case["floquet_data"].mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    bilinear, _linear = _build_variational_forms(
        case["mesh_data"].mesh,
        case["mesh_data"],
        cfg,
        case["raw_space"],
        field_formulation="total_field",
    )
    volume_action = build_fullspace_mpc_form_action(
        bilinear,
        case["raw_space"],
        mpc=case["floquet_data"].mpc,
    )
    return FullspacePhysicalAction(volume_action, dtn_action)


def _runtime_record(
    args: argparse.Namespace,
    case: Mapping[str, Any],
    runtime: Mapping[str, Any],
    coarse: Any,
    artifacts: Mapping[str, Any],
    local_arrays: Mapping[str, Any],
    resource: Mapping[str, int],
    stage_resources: Mapping[str, Mapping[str, int]],
    marker_dir: Path,
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = case["resolved"]
    input_path = args.input.resolve()
    mode_path = args.raw_dir / "mode_manifest.json"
    if mode_path.exists():
        mode_descriptor = {
            "relative_path": str(mode_path.relative_to(args.raw_dir)),
            "bytes": int(mode_path.stat().st_size),
            "sha256": _sha256_path(mode_path),
        }
    else:
        mode_descriptor = None
    return {
        "schema": D2_SCHEMA,
        "classification": "worker_facts_pending_independent_checker",
        "stage": "d2",
        "case": args.case,
        "command": list(sys.argv),
        "degree": D2_DEGREE,
        "mesh_target_nm": D2_MESH_TARGET_NM,
        "profile": D2_PROFILE,
        "mpi": {"size": int(args.expected_mpi_size)},
        "rank": D2_RANK,
        "prefixes": list(D2_PREFIXES),
        "model": {
            "profile": D2_PROFILE,
            "degree": D2_DEGREE,
            "mesh_target_nm": D2_MESH_TARGET_NM,
            "input_resolved_from_file": True,
        },
        "input": {
            "path": str(input_path),
            "file_sha256": _sha256_path(input_path),
            "resolved_config_sha256": hashlib.sha256(resolved).hexdigest(),
            "resolved_config_bytes": len(resolved),
        },
        "source_identity": dict(source_identity),
        "runtime": _jsonable(dict(runtime)),
        "markers": {
            "directory": str(marker_dir),
            "ledger": _marker_ledger(marker_dir),
        },
        "mode_manifest": mode_descriptor,
        "basis": {
            "candidate_order": _jsonable(case["basis"].candidate_order),
            "audit": _jsonable(dict(case["basis"].audit)),
        },
        "coarse": {"audit": _jsonable(dict(coarse.audit))},
        "topology": {"audit": _jsonable(dict(case["topology"].audit))},
        "operator": {
            "audit": _jsonable(dict(case["physical_action"].audit)),
            "t4_transmission_included": False,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "factor_materialized": False,
            "numeric_allgather": False,
        },
        "artifacts": _jsonable(dict(artifacts)),
        "owner_local_arrays": _jsonable(dict(local_arrays)),
        "resource": {
            "rank_max_current_rss_bytes": int(
                resource["rank_max_current_rss_bytes"]
            ),
            "rank_max_current_swap_bytes": int(
                resource["rank_max_current_swap_bytes"]
            ),
            "stage_rank_max_current": _jsonable(dict(stage_resources)),
            "rank_max_current_phase": "before_cleanup_destroy",
            "process_tree": "external_watchdog_required",
        },
        "resource_contract": {"status": "pending_external_watchdog"},
    }


def _write_success_record(record_path: Path, record: Mapping[str, Any]) -> None:
    if record_path.exists():
        raise FileExistsError(f"D2 record already exists: {record_path}")
    record_path.write_text(
        json.dumps(_jsonable(record), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _destroy_and_measure(
    objects: Iterable[Any], measure: Callable[[], Mapping[str, int]]
) -> Mapping[str, int]:
    for obj in objects:
        if obj is not None:
            obj.destroy()
    return measure()


def _best_effort_destroy(objects: Iterable[Any]) -> None:
    for obj in objects:
        if obj is not None:
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
    stage_resources: dict[str, Mapping[str, int]] = {}
    source_identity = {
        "expected_sha": args.expected_sha,
        "source_git_sha": None,
        "tracked_status": "not_measured",
    }
    case: dict[str, Any] | None = None
    coarse = None
    try:
        _write_marker(
            args.marker_dir,
            "preflight",
            args.expected_sha,
            comm,
            case=args.case,
            stage="preflight",
        )
        runtime = _collective_stage(
            comm,
            "preflight",
            lambda: _runtime_preflight(
                root,
                args.expected_sha,
                args.expected_mpi_size,
                comm.size,
            ),
        )
        stage_resources["preflight"] = _rank_resource(comm)
        source_identity = runtime["source_identity"]
        _write_marker(
            args.marker_dir,
            "mesh_mpc_topology",
            args.expected_sha,
            comm,
        )
        case = _collective_stage(
            comm, "mesh_mpc_topology", lambda: _setup_online_case(root, args, comm)
        )
        stage_resources["mesh_mpc_topology"] = _rank_resource(comm)
        _write_marker(
            args.marker_dir,
            "trace_basis_build",
            args.expected_sha,
            comm,
            rank=D2_RANK,
            prefixes=D2_PREFIXES,
        )
        case = _collective_stage(
            comm, "trace_basis_build", lambda: _build_trace_basis(case)
        )
        stage_resources["trace_basis_build"] = _rank_resource(comm)
        _write_marker(
            args.marker_dir,
            "trace_workspace_release",
            args.expected_sha,
            comm,
        )
        case["basis"].release_construction_workspace()
        stage_resources["trace_workspace_release"] = _rank_resource(comm)
        if not case["basis"].audit["construction_workspace_released"]:
            raise RuntimeError("trace basis workspace release did not close")
        _write_marker(
            args.marker_dir,
            "physical_action_build",
            args.expected_sha,
            comm,
            released=True,
        )
        case["physical_action"] = _collective_stage(
            comm,
            "physical_action_build",
            lambda: _build_physical_action(case, comm),
        )
        stage_resources["physical_action_build"] = _rank_resource(comm)
        _write_marker(
            args.marker_dir,
            "online_az_e",
            args.expected_sha,
            comm,
            operator="volume_plus_dynamic_DtN",
        )
        coarse = _collective_stage(
            comm,
            "online_az_e",
            lambda: __import__(
                "src.solvers.fullspace_adaptive_coarse",
                fromlist=["FullspaceAdaptiveCoarse"],
            ).FullspaceAdaptiveCoarse(
                case["basis"],
                case["physical_action"],
                lambda: _new_full_vector(case["space"]),
            ),
        )
        _collective_stage(comm, "online_az_e_build", lambda: coarse.build())
        _collective_stage(
            comm, "online_az_e_prefix", lambda: coarse.prefix_audit()
        )
        stage_resources["online_az_e"] = _rank_resource(comm)
        _write_marker(
            args.marker_dir,
            "canonical_evidence",
            args.expected_sha,
            comm,
            rank=D2_RANK,
            prefixes=D2_PREFIXES,
        )
        local_z = case["basis"].columns
        local_az = coarse.az
        local_arrays = {
            "Z": _write_owner_matrix(
                args.raw_dir / f"Z.rank{comm.rank:04d}.npy",
                local_z.shape,
                lambda index: local_z[:, index],
            ),
            "AZ": _write_owner_matrix(
                args.raw_dir / f"AZ.rank{comm.rank:04d}.npy",
                local_az.shape,
                lambda index: local_az[:, index],
            ),
            "ownership_range": [
                int(comm.scan(local_z.shape[0], op=MPI.SUM) - local_z.shape[0]),
                int(comm.scan(local_z.shape[0], op=MPI.SUM)),
            ],
        }
        e_descriptor = None
        if comm.rank == 0:
            e_descriptor = _write_small_array(args.raw_dir / "E.npy", coarse.e)
        e_descriptor = comm.bcast(e_descriptor, root=0)
        canonical = {
            "Z": _write_matrix_manifest(
                args.raw_dir / "canonical" / "Z",
                "full_fe",
                case["space"],
                case["floquet_data"].mpc,
                case["floquet_data"],
                case["basis"],
                coarse,
                comm,
            ),
            "AZ": _write_matrix_manifest(
                args.raw_dir / "canonical" / "AZ",
                "full_fe_dual",
                case["space"],
                case["floquet_data"].mpc,
                case["floquet_data"],
                case["basis"],
                coarse,
                comm,
            ),
        }
        stage_resources["canonical_evidence"] = _rank_resource(comm)
        artifacts = {"canonical_matrices": canonical, "E": e_descriptor}
        resource = _rank_resource(comm)
        mode_path = args.raw_dir / "mode_manifest.json"
        if comm.rank == 0:
            if mode_path.exists():
                raise FileExistsError(f"mode manifest already exists: {mode_path}")
            mode_path.write_bytes(case["mode_bytes"])
        comm.barrier()
        mode_descriptor = {
            "relative_path": "mode_manifest.json",
            "sha256": _sha256_path(mode_path),
            "bytes": int(mode_path.stat().st_size),
        }
        record = _runtime_record(
            args,
            case,
            runtime,
            coarse,
            artifacts,
            local_arrays,
            resource,
            stage_resources,
            args.marker_dir,
            source_identity,
        )
        record["mode_manifest"] = dict(mode_descriptor)
        _write_marker(args.marker_dir, "cleanup", args.expected_sha, comm)
        cleanup_resource = _destroy_and_measure(
            (coarse, case["physical_action"], case["basis"]),
            lambda: _rank_resource(comm),
        )
        stage_resources["cleanup"] = cleanup_resource
        record["markers"]["ledger"] = _marker_ledger(args.marker_dir)
        record["resource"]["stage_rank_max_current"] = _jsonable(
            dict(stage_resources)
        )
        record["resource"]["cleanup_rank_max_current_rss_bytes"] = int(
            cleanup_resource["rank_max_current_rss_bytes"]
        )
        record["resource"]["cleanup_rank_max_current_swap_bytes"] = int(
            cleanup_resource["rank_max_current_swap_bytes"]
        )
        if comm.rank == 0:
            record["artifacts"]["mode_manifest"] = dict(mode_descriptor)
            record["artifacts"]["E"] = e_descriptor
            _write_success_record(args.record, record)
        comm.barrier()
        return 0
    except Exception as exc:
        _best_effort_destroy(
            (
                coarse,
                None if case is None else case.get("physical_action"),
                None if case is None else case.get("basis"),
            )
        )
        try:
            if not (args.marker_dir / "failure.json").exists():
                _write_marker(
                    args.marker_dir,
                    "failure",
                    args.expected_sha,
                    comm,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                )
        finally:
            _write_failure_record(
                args.record,
                args.raw_dir,
                args.marker_dir,
                args.expected_sha,
                exc,
                planned=("mesh_mpc_topology", "trace_basis_build", "online_az_e", "canonical_evidence"),
                not_run=("remaining stages after failure",),
                comm=comm,
                runtime=runtime,
            )
        return 1


def _marker_stage(marker_dir: Path) -> str:
    return _last_marker(marker_dir) or "startup"


def _stage_memory_peaks(samples: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    peaks: dict[str, int] = {}
    for sample in samples:
        authority = sample.get("authority")
        if not isinstance(authority, Mapping):
            continue
        stage = str(sample.get("stage", "unknown"))
        value = int(authority.get("memory_authority_bytes", 0))
        peaks[stage] = max(peaks.get(stage, 0), value)
    return peaks


def _watchdog_compact(
    raw_sha256: str,
    command: Iterable[str],
    stop_reason: str,
    return_code: int,
    termination: Mapping[str, Any],
    samples: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = tuple(samples)
    peaks = _stage_memory_peaks(rows)
    valid_authority = [
        sample
        for sample in rows
        if isinstance(sample.get("authority"), Mapping)
        and not sample.get("authority_error")
    ]
    authority_complete = bool(rows) and len(valid_authority) == len(rows)
    process_tree_swap_gate = authority_complete and all(
        int(
            sample["authority"]["process_tree"]["swap_bytes"]
        )
        == 0
        for sample in valid_authority
        if isinstance(sample["authority"].get("process_tree"), Mapping)
    )
    if authority_complete and any(
        not isinstance(sample["authority"].get("process_tree"), Mapping)
        for sample in valid_authority
    ):
        process_tree_swap_gate = False
    return {
        "schema": "task038.full3d.adaptive-coarse.d2-watchdog-compact.v1",
        "raw_sha256": raw_sha256,
        "command": list(command),
        "stop_reason": stop_reason,
        "worker_returncode": int(return_code),
        "termination": dict(termination),
        "stage_peak_memory_authority_bytes": peaks,
        "process_tree_peak_memory_authority_bytes": max(
            peaks.values(), default=0
        ),
        "process_tree_swap_gate": bool(process_tree_swap_gate),
    }


def _backfill_watchdog_record(
    record_path: Path,
    marker_dir: Path,
    raw_path: Path,
    compact_path: Path,
    compact: Mapping[str, Any],
    stop_reason: str,
    return_code: int,
    termination: Mapping[str, Any],
) -> None:
    existed = record_path.exists()
    if existed:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    else:
        record = {
            "schema": D2_SCHEMA,
            "classification": "controlled_negative",
            "status": "controlled_negative",
            "raw_dir": str(marker_dir.parent),
            "marker_dir": str(marker_dir),
            "source_identity": {
                "expected_sha": None,
                "source_git_sha": None,
                "tracked_status": "not_measured",
            },
            "failure": {
                "exception_type": "ExternalWatchdogStop",
                "message": stop_reason,
            },
            "last_marker": _marker_stage(marker_dir),
            "marker_ledger": _marker_ledger(marker_dir),
            "planned": [
                "mesh_mpc_topology",
                "trace_basis_build",
                "trace_workspace_release",
                "physical_action_build",
                "online_az_e",
                "canonical_evidence",
            ],
            "not_run": ["worker success record", "remaining D2 stages"],
        }
    record["resource_contract"] = {
        "status": (
            "measured_controlled_negative"
            if record.get("classification") == "controlled_negative"
            else "measured"
        ),
        "raw_path": str(raw_path),
        "raw_sha256": _sha256_path(raw_path),
        "compact_path": str(compact_path),
        "compact_sha256": _sha256_path(compact_path),
        "stop_reason": stop_reason,
        "worker_returncode": int(return_code),
        "termination": _jsonable(dict(termination)),
        "process_tree_peak_memory_authority_bytes": int(
            compact.get("process_tree_peak_memory_authority_bytes", 0)
        ),
        "process_tree_swap_gate": bool(
            compact.get("process_tree_swap_gate", False)
        ),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    if existed:
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
    else:
        with record_path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")


def _watchdog_main(argv: list[str]) -> int:
    from benchmarks.task034_wsl_resources import resource_authority_sample
    from benchmarks.watchdog_process_control import (
        terminate_process_tree,
        worker_process_group_popen_kwargs,
    )

    parser = argparse.ArgumentParser(description="D2 process-tree watchdog")
    parser.add_argument("--watchdog", action="store_true")
    parser.add_argument("--watchdog-record", type=Path, required=True)
    parser.add_argument("--watchdog-raw", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--watchdog-log", type=Path, required=True)
    parser.add_argument("--watchdog-marker-dir", type=Path, required=True)
    parser.add_argument("--watchdog-poll-seconds", type=float, default=1.0)
    parser.add_argument("--watchdog-timeout-seconds", type=float, default=0.0)
    parser.add_argument("--watchdog-command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args([item for item in argv if item != "--watchdog"])
    command = [item for item in args.watchdog_command if item != "--"]
    if not command or args.watchdog_poll_seconds < 0.05:
        raise SystemExit("watchdog command and poll interval are invalid")
    if args.watchdog_timeout_seconds < 0.0:
        raise SystemExit("watchdog timeout must be non-negative; zero disables it")
    for path in (args.watchdog_raw, args.watchdog_compact, args.watchdog_log):
        if path.exists():
            raise FileExistsError(f"watchdog artifact already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command,
        stdout=args.watchdog_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        **worker_process_group_popen_kwargs(),
    )
    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    stop_reason = "natural_exit"
    termination = None
    while True:
        try:
            authority = resource_authority_sample(process.pid)
            authority_error = None
        except Exception as exc:
            authority = None
            authority_error = f"{type(exc).__name__}: {exc}"
        if authority is not None:
            memory = int(authority["memory_authority_bytes"])
            process_tree = authority["process_tree"]
            sample = {
                "wall_time_ns": time.time_ns(),
                "elapsed_seconds": time.monotonic() - started,
                "stage": _marker_stage(args.watchdog_marker_dir),
                "authority": authority,
            }
            samples.append(sample)
            stop = None
            if not process_tree["all_status_readable"]:
                stop = "authority_unreadable"
            elif not bool(authority["job_no_swap"]):
                stop = "swap_nonzero"
            elif memory >= D2_MEMORY_HARD_STOP_BYTES:
                stop = "hard_stop_12_gib"
            elif (
                args.watchdog_timeout_seconds > 0.0
                and time.monotonic() - started >= args.watchdog_timeout_seconds
            ):
                stop = "watchdog_timeout"
            if stop is not None and process.poll() is None:
                stop_reason = stop
                termination = terminate_process_tree(process)
                break
        else:
            samples.append(
                {
                    "wall_time_ns": time.time_ns(),
                    "elapsed_seconds": time.monotonic() - started,
                    "stage": _marker_stage(args.watchdog_marker_dir),
                    "authority_error": authority_error,
                }
            )
            if process.poll() is None:
                stop_reason = "authority_unreadable"
                termination = terminate_process_tree(process)
                break
        if process.poll() is not None:
            break
        time.sleep(args.watchdog_poll_seconds)
    return_code = process.wait()
    if termination is None:
        termination = {
            "requested": False,
            "method": "natural_exit",
            "sigkill_required": False,
        }
    raw = {
        "schema": "task038.full3d.adaptive-coarse.d2-watchdog-raw.v1",
        "command": command,
        "samples": samples,
        "stop_reason": stop_reason,
        "termination": termination,
        "worker_returncode": return_code,
    }
    args.watchdog_raw.write_text(
        json.dumps(_jsonable(raw), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    compact = _watchdog_compact(
        _sha256_path(args.watchdog_raw),
        command,
        stop_reason,
        return_code,
        termination,
        samples,
    )
    args.watchdog_compact.write_text(
        json.dumps(_jsonable(compact), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    try:
        _backfill_watchdog_record(
            args.watchdog_record,
            args.watchdog_marker_dir,
            args.watchdog_raw,
            args.watchdog_compact,
            compact,
            stop_reason,
            return_code,
            termination,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(
            f"D2 watchdog record update failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return 1
    return int(return_code)


def _parse_worker_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="D2 adaptive coarse worker")
    parser.add_argument("--stage", choices=("d2",), required=True)
    parser.add_argument("--case", choices=tuple(D2_CASES), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--marker-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", dest="expected_sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    if args.expected_mpi_size != D2_CASES[args.case]:
        parser.error("expected MPI size does not match the frozen D2 case")
    return args


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    if "--watchdog" in selected:
        return _watchdog_main(selected)
    return _run_worker(_parse_worker_args(selected))


if __name__ == "__main__":
    raise SystemExit(main())
