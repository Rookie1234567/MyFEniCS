"""Thin M1 owner-local transfer evidence route.

The M1 route is deliberately separate from the H2B factor runners.  Its worker
builds the already-reviewed full-space p4/p6 transfer and records bounded
owner-local evidence; the watchdog only sequences MPI1 and MPI2; the checker
recomputes the gates from the raw worker summaries and canonical manifests.
No production default imports this module.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

from benchmarks.run_task037_extra_h2b import (
    _artifact,
    _attach_evidence,
    _light_source as _clean_source,
    _read_json,
    _sha256_file,
    _write_json,
)


ROOT = Path(__file__).resolve().parents[1]
M1_SCHEMA = "task037.extra.m1.owner-local-transfer"
M1_WORKER_SCHEMA = f"{M1_SCHEMA}.worker.v1"
M1_WATCHDOG_SCHEMA = f"{M1_SCHEMA}.watchdog.v1"
M1_CHECK_SCHEMA = f"{M1_SCHEMA}.check.v1"
M1_SCOPE_SCHEMA = f"{M1_SCHEMA}.scope.v1"
M1_TIMEOUT_SECONDS = 1_800.0
M1_MPI1_RSS_LIMIT_BYTES = 900_000_000
M1_MPI2_RSS_LIMIT_BYTES = 1_300_000_000
M1_RETAINED_PAYLOAD_LIMIT_BYTES = 128_000_000
M1_WORKSPACE_LIMIT_BYTES = 64_000_000
M1_SWAP_LIMIT_BYTES = 0
M1_IMAGE_LIMIT = 1.0e-11
M1_ADJOINT_LIMIT = 1.0e-12
M1_CANONICAL_LIMIT = 1.0e-12
M1_MANUFACTURED_FIELD_ID = "floquet_compatible_bilinear_p4_v1"
M1_DUAL_FIELD_ID = "floquet_compatible_degree5_dual_v1"
M1_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "transfer_ready",
    "measurement_started",
    "measurement_ready",
    "canonical_ready",
    "summary_ready",
)
_HEX = frozenset("0123456789abcdef")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    item = getattr(value, "item", None)
    if callable(item):
        return _plain(item())
    raise TypeError(f"M1 evidence value is not JSONable: {type(value).__name__}")


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


def _valid_sha(value: Any, *, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and set(value) <= _HEX
    )


def _m1_scope(mpi_size: int | None = None) -> dict[str, Any]:
    return {
        "schema": M1_SCOPE_SCHEMA,
        "target_stage4_config": {"degree": 6, "h_nm": 10.0},
        "mesh_builder": "build_airbox_mesh_3d",
        "p4_space": "N1curl_degree4",
        "p6_space": "N1curl_degree6",
        "manufactured_field": M1_MANUFACTURED_FIELD_ID,
        "dual_field": M1_DUAL_FIELD_ID,
        "fine_space": "uncondensed_fullspace",
        "mpi_size": None if mpi_size is None else int(mpi_size),
        "timeout_seconds": M1_TIMEOUT_SECONDS,
        "rss_limits_bytes": {
            "mpi1": M1_MPI1_RSS_LIMIT_BYTES,
            "mpi2": M1_MPI2_RSS_LIMIT_BYTES,
        },
        "swap_limit_bytes": M1_SWAP_LIMIT_BYTES,
        "form_jit_used": False,
        "global_transfer_matrix_materialized": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "condensation": False,
        "pde_or_ksp_called": False,
    }


def _m1_identity() -> dict[str, Any]:
    return {
        "condensation": False,
        "static_condensed_operator_used": False,
        "trace_only_path": False,
        "global_transfer_matrix_materialized": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "numeric_allgather": False,
        "replicated_global_numeric_vector": False,
        "schur_or_slab_materialized": False,
        "local_krylov_or_ksp_called": False,
        "pde_called": False,
        "ordinary_default_changed": False,
    }


def _m1_phase_identity() -> dict[str, Any]:
    return {
        "form_jit_used": False,
        "compile_called": False,
        "compiler_probe_called": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "condensed_path": False,
        "trace_only_path": False,
        "ordinary_default_changed": False,
    }


def _m1_runtime_identity(comm: Any) -> dict[str, Any]:
    import dolfinx
    import mpi4py
    import numpy as np
    import petsc4py
    import slepc4py
    from petsc4py import PETSc

    return {
        "sys_executable": str(sys.executable),
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_size": int(comm.size),
        "linux_abi": bool(os.name == "posix"),
        "package_paths": {
            "petsc4py": str(petsc4py.__file__),
            "slepc4py": str(slepc4py.__file__),
            "dolfinx": str(dolfinx.__file__),
            "mpi4py": str(mpi4py.__file__),
        },
        "threads": {
            key: os.environ.get(key)
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }


def _m1_runtime_valid(value: Any, mpi_size: int, executable: str) -> bool:
    required = (
        "sys_executable",
        "petsc_scalar_type",
        "petsc_int_type",
        "mpi_size",
        "linux_abi",
        "package_paths",
        "threads",
    )
    if not _required_mapping(value, required):
        return False
    paths = value["package_paths"]
    threads = value["threads"]
    thread_names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    return bool(
        value["sys_executable"] == str(executable)
        and value["petsc_scalar_type"] == "complex128"
        and value["petsc_int_type"] == "int32"
        and type(value["mpi_size"]) is int
        and value["mpi_size"] == mpi_size
        and value["linux_abi"] is True
        and _required_mapping(paths, ("petsc4py", "slepc4py", "dolfinx", "mpi4py"))
        and all(
            isinstance(paths[name], str)
            and os.path.isabs(paths[name])
            and "/mnt/c" not in paths[name]
            for name in ("petsc4py", "slepc4py", "dolfinx", "mpi4py")
        )
        and _required_mapping(threads, thread_names)
        and all(threads[name] == "1" for name in thread_names)
    )


def _source_valid(value: Any) -> bool:
    required = (
        "source_commit_full_sha",
        "tracked_source_dirty",
        "source_worktree_dirty",
        "nonignored_untracked_paths",
        "worktree_status_porcelain",
        "git_error",
    )
    if not isinstance(value, Mapping) or any(key not in value for key in required):
        return False
    return bool(
        _valid_sha(value["source_commit_full_sha"], length=40)
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


def _mark(run_dir: Path, phase: str, event: str, *, rank: int) -> None:
    if rank != 0:
        return
    path = run_dir / f"{phase}_progress.jsonl"
    previous = 0
    if path.exists():
        previous = sum(1 for _line in path.open("r", encoding="utf-8"))
    item = {
        "schema": f"{M1_SCHEMA}.progress.v1",
        "phase": phase,
        "event": event,
        "event_index": int(previous),
        "elapsed_wall_seconds": time.monotonic(),
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()


def _m1_worker_command(executable: str, run_dir: Path, phase: str, mpi_size: int) -> list[str]:
    if phase not in {"mpi1", "mpi2"} or int(mpi_size) not in {1, 2}:
        raise ValueError("M1 has only MPI1 and MPI2 worker phases")
    return [
        "mpiexec",
        "-n",
        str(int(mpi_size)),
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_m",
        "m1-worker",
        "--run-dir",
        str(run_dir.resolve()),
        "--phase",
        phase,
        "--expected-mpi-size",
        str(int(mpi_size)),
    ]


def _mpi_relative_error(observed: Any, expected: Any, comm: Any) -> float:
    import numpy as np

    left = np.asarray(observed, dtype=np.complex128)
    right = np.asarray(expected, dtype=np.complex128)
    if left.shape != right.shape:
        raise ValueError("M1 comparison arrays have different local shapes")
    numerator = float(comm.allreduce(float(np.vdot(left - right, left - right).real)))
    denominator = float(comm.allreduce(float(np.vdot(right, right).real)))
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return math.inf
    return float(math.sqrt(max(numerator, 0.0)) / max(math.sqrt(max(denominator, 0.0)), np.finfo(float).tiny))


def _mpi_finite(values: Any, comm: Any) -> bool:
    import numpy as np

    local = bool(np.isfinite(np.asarray(values)).all())
    from mpi4py import MPI

    return bool(comm.allreduce(local, op=MPI.LAND))


def _mpi_array_equal(left: Any, right: Any, comm: Any) -> bool:
    import numpy as np

    from mpi4py import MPI

    return bool(comm.allreduce(bool(np.array_equal(left, right)), op=MPI.LAND))


def _new_mpc_vector(mpc: Any) -> Any:
    from dolfinx.la.petsc import create_vector

    index_map = mpc.function_space.dofmap.index_map
    return create_vector([(index_map, mpc.function_space.dofmap.index_map_bs)])


def _function_to_mpc_vector(function: Any, mpc: Any) -> Any:
    from petsc4py import PETSc

    vector = _new_mpc_vector(mpc)
    owned = int(mpc.function_space.dofmap.index_map.size_local)
    with vector.localForm() as local:
        local.set(0.0)
        local.array_w[:owned] = function.x.array[:owned]
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    mpc.backsubstitution(vector)
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return vector


def _floquet_compatible_hcurl(cfg: Any) -> Any:
    """Return the fixed cfg-bound p4-compatible Floquet polynomial field."""

    import numpy as np

    c = np.asarray(
        (1.0 + 0.2j, -0.3 + 0.4j, 0.7 - 0.1j),
        dtype=np.complex128,
    )
    x_min = float(cfg.x_min)
    x_max = float(cfg.x_max)
    y_min = float(cfg.y_min)
    y_max = float(cfg.y_max)
    phase_x = complex(cfg.floquet_phase_x)
    phase_y = complex(cfg.floquet_phase_y)

    def _field(x: Any) -> Any:
        points = np.asarray(x)
        sx = (points[0] - x_min) / (x_max - x_min)
        sy = (points[1] - y_min) / (y_max - y_min)
        qx = 1.0 + (phase_x - 1.0) * sx
        qy = 1.0 + (phase_y - 1.0) * sy
        return np.vstack(tuple(qx * qy * component for component in c))

    return _field


def _floquet_compatible_p6_dual(cfg: Any) -> Any:
    """Return the fixed degree-5 Floquet-compatible p6 dual field.

    The qx*qy factors enforce the two Floquet face relations.  The remaining
    factors have tensor degree at most five in x/y and four in z, so they are
    representable by the p6 N1curl reference space without a fitted dual.
    """

    import numpy as np

    c = np.asarray(
        (1.0 + 0.2j, -0.3 + 0.4j, 0.7 - 0.1j),
        dtype=np.complex128,
    )
    x_min = float(cfg.x_min)
    x_max = float(cfg.x_max)
    y_min = float(cfg.y_min)
    y_max = float(cfg.y_max)
    z_min = float(cfg.domain_z_min)
    z_max = float(cfg.domain_z_max)
    phase_x = complex(cfg.floquet_phase_x)
    phase_y = complex(cfg.floquet_phase_y)

    def _field(x: Any) -> Any:
        points = np.asarray(x, dtype=np.float64)
        sx = (points[0] - x_min) / (x_max - x_min)
        sy = (points[1] - y_min) / (y_max - y_min)
        sz = (points[2] - z_min) / (z_max - z_min)
        qx = 1.0 + (phase_x - 1.0) * sx
        qy = 1.0 + (phase_y - 1.0) * sy
        bx = sx * (1.0 - sx)
        by = sy * (1.0 - sy)
        q = qx * qy
        return np.vstack(
            (
                c[0]
                * q
                * (
                    1.0
                    + 0.13 * bx**2
                    + 0.07j * by
                    + 0.11 * sz
                    + 0.03j * sz**2
                ),
                c[1]
                * q
                * (
                    1.0
                    - 0.09 * bx
                    + 0.15j * by**2
                    + 0.12 * sz
                    + 0.04j * sz**3
                ),
                c[2]
                * q
                * (
                    1.0
                    + 0.11 * bx * by
                    + 0.08j * bx**2
                    + 0.09 * sz**2
                    + 0.02j * sz**4
                ),
            )
        ).astype(np.complex128)

    return _field


def _write_canonical_manifest(
    run_dir: Path,
    role: str,
    packets: Any,
    extractor_audit: Mapping[str, Any],
    comm: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    rank = int(comm.rank)
    shard_path = run_dir / f"{role}_rank{rank}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets)
    shard["rank"] = rank
    shard_metadata = comm.allgather(shard)
    audit = dict(_plain(extractor_audit))
    audit["packet_count_source"] = "write_canonical_packet_shard"
    audit["duplicate_detection"] = "checker_recomputed_from_shards"
    manifest = canonical_shard_manifest(
        role=role,
        mpi_size=int(comm.size),
        shard_metadata=shard_metadata,
        extractor_audit=audit,
        duplicate_detection="checker_recomputed_from_shards",
    )
    manifest_path = run_dir / f"{role}_manifest.json"
    manifest_sha = None
    if rank == 0:
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
    manifest_sha = comm.bcast(manifest_sha, root=0)
    comm.barrier()
    return {
        "path": manifest_path.name,
        "role": role,
        "sha256": str(manifest_sha),
        "packet_count": int(manifest["global_summed_packet_count"]),
        "duplicate_count": manifest["summed_local_duplicate_count"],
    }


def _worker_measurement(
    *,
    transfer: Any,
    image_error: float,
    adjoint_error: float,
    image_deterministic: bool,
    adjoint_deterministic: bool,
    finite: bool,
    canonical_manifests: Mapping[str, Any],
) -> dict[str, Any]:
    audit = _plain(transfer.audit)
    required_audit = {
        "p4_global_rows",
        "p4_owned_rows",
        "p4_ghost_rows",
        "p4_original_local_rows",
        "p4_original_ghost_rows",
        "p4_mpc_extended_local_rows",
        "p4_mpc_extended_ghost_rows",
        "p4_mpc_added_master_ghost_rows",
        "p6_global_rows",
        "p6_owned_rows",
        "p6_ghost_rows",
        "p6_original_local_rows",
        "p6_original_ghost_rows",
        "p6_mpc_extended_local_rows",
        "p6_mpc_extended_ghost_rows",
        "p6_mpc_added_master_ghost_rows",
        "p4_mpc_extended_local_work_bytes",
        "p6_mpc_extended_local_work_bytes",
        "p4_owned_constraint_count_global",
        "p6_owned_constraint_count_global",
        "missing_owned_p6_rows",
        "extra_owned_p6_rows",
        "duplicate_owned_p6_designations",
        "retained_numeric_payload_components",
        "retained_numeric_payload_bytes",
        "lazy_p6_work_vec_bytes",
        "retained_transfer_numeric_payload_bytes",
        "bounded_apply_workspace_components",
        "bounded_apply_workspace_bytes",
    }
    if not required_audit <= set(audit):
        raise ValueError("owner-local audit is missing M1 row/constraint fields")
    return {
        "p4_global_rows": int(audit["p4_global_rows"]),
        "p4_owned_rows": int(audit["p4_owned_rows"]),
        "p4_ghost_rows": int(audit["p4_ghost_rows"]),
        "p4_original_local_rows": int(audit["p4_original_local_rows"]),
        "p4_original_ghost_rows": int(audit["p4_original_ghost_rows"]),
        "p4_mpc_extended_local_rows": int(
            audit["p4_mpc_extended_local_rows"]
        ),
        "p4_mpc_extended_ghost_rows": int(
            audit["p4_mpc_extended_ghost_rows"]
        ),
        "p4_mpc_added_master_ghost_rows": int(
            audit["p4_mpc_added_master_ghost_rows"]
        ),
        "p6_global_rows": int(audit["p6_global_rows"]),
        "p6_owned_rows": int(audit["p6_owned_rows"]),
        "p6_ghost_rows": int(audit["p6_ghost_rows"]),
        "p6_original_local_rows": int(audit["p6_original_local_rows"]),
        "p6_original_ghost_rows": int(audit["p6_original_ghost_rows"]),
        "p6_mpc_extended_local_rows": int(
            audit["p6_mpc_extended_local_rows"]
        ),
        "p6_mpc_extended_ghost_rows": int(
            audit["p6_mpc_extended_ghost_rows"]
        ),
        "p6_mpc_added_master_ghost_rows": int(
            audit["p6_mpc_added_master_ghost_rows"]
        ),
        "p4_mpc_extended_local_work_bytes": int(
            audit["p4_mpc_extended_local_work_bytes"]
        ),
        "p6_mpc_extended_local_work_bytes": int(
            audit["p6_mpc_extended_local_work_bytes"]
        ),
        "p4_global_constraints": int(audit["p4_owned_constraint_count_global"]),
        "p6_global_constraints": int(audit["p6_owned_constraint_count_global"]),
        "missing_rows": int(audit["missing_owned_p6_rows"]),
        "extra_rows": int(audit["extra_owned_p6_rows"]),
        "duplicate_rows": int(audit["duplicate_owned_p6_designations"]),
        "image_relative_error": float(image_error),
        "adjoint_relative_error": float(adjoint_error),
        "image_deterministic": bool(image_deterministic),
        "adjoint_deterministic": bool(adjoint_deterministic),
        "finite": bool(finite),
        "phase_once": bool(
            audit["p4_mpc_phase_applied_once"]
            and audit["p6_mpc_phase_applied_once"]
        ),
        "orientation": {
            "cell_count_global": int(audit["orientation_cell_count_global"]),
            "nonzero_cell_count_global": int(
                audit["orientation_nonzero_cell_count_global"]
            ),
            "metadata_sha256": audit["orientation_metadata_sha256"],
            "reference_transform_sha256": audit["reference_transform_sha256"],
            "edge_reverse_face_d4_authority": "production Basix/VariablePReferenceSpace",
        },
        "payload_audit": {
            "retained_numeric_payload_components": _plain(
                audit["retained_numeric_payload_components"]
            ),
            "retained_numeric_payload_bytes": int(
                audit["retained_numeric_payload_bytes"]
            ),
            "lazy_p6_work_vec_bytes": int(audit["lazy_p6_work_vec_bytes"]),
            "retained_transfer_numeric_payload_bytes": int(
                audit["retained_transfer_numeric_payload_bytes"]
            ),
            "bounded_apply_workspace_bytes": int(
                audit["bounded_apply_workspace_bytes"]
            ),
            "bounded_apply_workspace_components": _plain(
                audit["bounded_apply_workspace_components"]
            ),
            "construction_transient_numeric_payload_bytes": audit[
                "construction_transient_numeric_payload_bytes"
            ],
            "measured_process_tree_rss_bytes": audit[
                "measured_process_tree_rss_bytes"
            ],
        },
        "canonical_manifests": _plain(canonical_manifests),
        "materialization_identity": {
            "global_transfer_matrix": False,
            "global_matrix": False,
            "global_constraint_matrix": False,
            "condensed": False,
            "trace_only": False,
            "ksp_or_pde": False,
            "numeric_allgather": False,
            "replicated_global_numeric_vector": False,
        },
    }


def _m1_numeric_failure_payload(
    *,
    run_dir: Path,
    phase: str,
    mpi_size: int,
    source_start: Mapping[str, Any],
    source_end: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
    transfer: Any,
    image_error: float,
    adjoint_error: float,
    image_deterministic: bool,
    adjoint_deterministic: bool,
    finite: bool,
    elapsed_wall_seconds: float,
) -> dict[str, Any]:
    """Persist measured M1 numerical failure before canonical extraction."""

    measurement = _worker_measurement(
        transfer=transfer,
        image_error=image_error,
        adjoint_error=adjoint_error,
        image_deterministic=image_deterministic,
        adjoint_deterministic=adjoint_deterministic,
        finite=finite,
        canonical_manifests={
            "p6_image": {"status": "not_run_by_gate"},
            "p4_adjoint": {"status": "not_run_by_gate"},
        },
    )
    return _attach_evidence(
        {
            "schema": M1_WORKER_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "route": "M1-review-only",
            "run_dir": str(run_dir),
            "phase": phase,
            "mpi_size": int(mpi_size),
            "scope": _m1_scope(mpi_size),
            "identity": _m1_identity(),
            "phase_identity": _m1_phase_identity(),
            "runtime_identity": _plain(runtime_identity),
            "source_at_start": _plain(source_start),
            "source_at_end": _plain(source_end),
            "measurement": measurement,
            "m1_build_audit": _plain(transfer.audit),
            "error": "m1_transfer_numeric_gate_failed",
            "controlled_stop": None,
            "elapsed_wall_seconds": float(elapsed_wall_seconds),
        }
    )


def _run_m1_worker(run_dir: Path, phase: str, expected_mpi_size: int) -> int:
    import numpy as np
    from dataclasses import replace
    from dolfinx import default_real_type, fem
    from basix.ufl import element
    from mpi4py import MPI
    from src.common.config_3d import target_stage4_config
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        iter_canonical_full_fe_owner_packets,
        iter_canonical_full_fe_dual_packets,
    )
    from src.solvers.hcurl_p_split_owner_transfer import (
        build_owner_local_p4_p6_transfer,
    )

    comm = MPI.COMM_WORLD
    if int(comm.size) != int(expected_mpi_size) or phase not in {"mpi1", "mpi2"}:
        raise ValueError("M1 worker MPI phase does not match its command")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    rank = int(comm.rank)
    started = time.perf_counter()
    source_start = comm.bcast(_clean_source() if rank == 0 else None, root=0)
    if not _source_valid(source_start):
        raise RuntimeError("M1 worker requires a clean source")
    source_function = None
    expected_function = None
    dual_function = None
    vectors: list[Any] = []
    transfer = None
    try:
        _mark(run_dir, phase, "authority_validated", rank=rank)
        cfg = target_stage4_config(degree=6, h_nm=10.0)
        mesh_data = build_airbox_mesh_3d(cfg, run_dir / f"{phase}_mesh")
        _mark(run_dir, phase, "mesh_ready", rank=rank)
        p4_space = fem.functionspace(
            mesh_data.mesh,
            element(
                "N1curl",
                mesh_data.mesh.basix_cell(),
                4,
                dtype=default_real_type,
            ),
        )
        p6_space = fem.functionspace(
            mesh_data.mesh,
            element(
                "N1curl",
                mesh_data.mesh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        _mark(run_dir, phase, "space_ready", rank=rank)
        p4_cfg = replace(cfg, nedelec_degree=4)
        floquet4 = build_double_floquet_mpc(p4_space, mesh_data, p4_cfg)
        floquet6 = build_double_floquet_mpc(p6_space, mesh_data, cfg)
        _mark(run_dir, phase, "floquet_mpc_ready", rank=rank)
        transfer = build_owner_local_p4_p6_transfer(
            p4_space,
            p6_space,
            p4_mpc=floquet4.mpc,
            p6_mpc=floquet6.mpc,
        )
        _mark(run_dir, phase, "transfer_ready", rank=rank)
        source_function = fem.Function(p4_space)
        expected_function = fem.Function(p6_space)
        dual_function = fem.Function(p6_space)
        manufactured_hcurl = _floquet_compatible_hcurl(cfg)
        dual_hcurl = _floquet_compatible_p6_dual(cfg)
        source_function.interpolate(manufactured_hcurl)
        source_function.x.scatter_forward()
        expected_function.interpolate(manufactured_hcurl)
        expected_function.x.scatter_forward()
        dual_function.interpolate(dual_hcurl)
        dual_function.x.scatter_forward()
        source = _function_to_mpc_vector(source_function, floquet4.mpc)
        expected = _function_to_mpc_vector(expected_function, floquet6.mpc)
        dual = _function_to_mpc_vector(dual_function, floquet6.mpc)
        image = _new_mpc_vector(floquet6.mpc)
        repeat_image = _new_mpc_vector(floquet6.mpc)
        adjoint = _new_mpc_vector(floquet4.mpc)
        repeat_adjoint = _new_mpc_vector(floquet4.mpc)
        vectors.extend((source, expected, dual, image, repeat_image, adjoint, repeat_adjoint))
        _mark(run_dir, phase, "measurement_started", rank=rank)
        transfer.apply(source, image)
        transfer.apply(source, repeat_image)
        transfer.apply_adjoint(dual, adjoint)
        transfer.apply_adjoint(dual, repeat_adjoint)
        with image.localForm() as image_local, expected.localForm() as expected_local:
            image_error = _mpi_relative_error(
                image_local.array_r[: transfer.p6_constraints.owned_rows],
                expected_local.array_r[: transfer.p6_constraints.owned_rows],
                comm,
            )
        with image.localForm() as image_local, repeat_image.localForm() as repeat_local:
            image_deterministic = _mpi_array_equal(
                image_local.array_r[: transfer.p6_constraints.owned_rows],
                repeat_local.array_r[: transfer.p6_constraints.owned_rows],
                comm,
            )
        with adjoint.localForm() as adjoint_local, repeat_adjoint.localForm() as repeat_local:
            adjoint_deterministic = _mpi_array_equal(
                adjoint_local.array_r[: transfer.p4_constraints.owned_rows],
                repeat_local.array_r[: transfer.p4_constraints.owned_rows],
                comm,
            )
        lhs = complex(image.dot(dual))
        rhs = complex(source.dot(adjoint))
        source_norm = float(source.norm())
        dual_norm = float(dual.norm())
        adjoint_error = abs(lhs - rhs) / max(source_norm * dual_norm, np.finfo(float).tiny)
        finite = _mpi_finite(
            np.concatenate(
                (
                    np.asarray(image.getArray(readonly=True)),
                    np.asarray(adjoint.getArray(readonly=True)),
                )
            ),
            comm,
        )
        if not (
            math.isfinite(image_error)
            and image_error <= M1_IMAGE_LIMIT
            and math.isfinite(float(adjoint_error))
            and float(adjoint_error) <= M1_ADJOINT_LIMIT
            and image_deterministic
            and adjoint_deterministic
            and finite
        ):
            source_end = comm.bcast(_clean_source() if rank == 0 else None, root=0)
            failure_payload = _m1_numeric_failure_payload(
                run_dir=run_dir,
                phase=phase,
                mpi_size=int(comm.size),
                source_start=source_start,
                source_end=source_end,
                runtime_identity=_m1_runtime_identity(comm),
                transfer=transfer,
                image_error=image_error,
                adjoint_error=float(adjoint_error),
                image_deterministic=image_deterministic,
                adjoint_deterministic=adjoint_deterministic,
                finite=finite,
                elapsed_wall_seconds=float(time.perf_counter() - started),
            )
            _mark(run_dir, phase, "summary_ready", rank=rank)
            comm.barrier()
            if rank == 0:
                _write_json(run_dir / f"{phase}_worker_summary.json", failure_payload)
            comm.barrier()
            return 1
        _mark(run_dir, phase, "measurement_ready", rank=rank)
        p6_extract_audit = {
            "role": "full_fe",
            "numeric_allgather": False,
        }
        canonical_manifests = {
            "p6_image": _write_canonical_manifest(
                run_dir,
                f"{phase}_p6_image",
                iter_canonical_full_fe_owner_packets(
                    p6_space, floquet6.mpc, image, floquet6
                ),
                p6_extract_audit,
                comm,
            ),
            "p4_adjoint": _write_canonical_manifest(
                run_dir,
                f"{phase}_p4_adjoint",
                iter_canonical_full_fe_dual_packets(
                    p4_space, floquet4.mpc, adjoint
                ),
                {"role": "full_fe_dual", "numeric_allgather": False},
                comm,
            ),
        }
        _mark(run_dir, phase, "canonical_ready", rank=rank)
        measurement = _worker_measurement(
            transfer=transfer,
            image_error=image_error,
            adjoint_error=float(adjoint_error),
            image_deterministic=image_deterministic,
            adjoint_deterministic=adjoint_deterministic,
            finite=finite,
            canonical_manifests=canonical_manifests,
        )
        source_end = comm.bcast(_clean_source() if rank == 0 else None, root=0)
        payload = _attach_evidence(
            {
                "schema": M1_WORKER_SCHEMA,
                "status": "measurement_complete",
                "run_dir": str(run_dir),
                "phase": phase,
                "mpi_size": int(comm.size),
                "scope": _m1_scope(comm.size),
                "identity": _m1_identity(),
                "phase_identity": _m1_phase_identity(),
                "runtime_identity": _m1_runtime_identity(comm),
                "source_at_start": source_start,
                "source_at_end": source_end,
                "measurement": measurement,
                "m1_build_audit": _plain(transfer.audit),
                "error": None,
                "controlled_stop": None,
                "elapsed_wall_seconds": float(time.perf_counter() - started),
            }
        )
        _mark(run_dir, phase, "summary_ready", rank=rank)
        comm.barrier()
        if rank == 0:
            _write_json(run_dir / f"{phase}_worker_summary.json", payload)
        comm.barrier()
        return 0
    finally:
        for vector in vectors:
            vector.destroy()
        if transfer is not None:
            transfer.destroy()


def _recorded_artifacts(run_dir: Path) -> dict[str, dict[str, Any]]:
    names = [
        "mpi1_worker_summary.json",
        "mpi1_progress.jsonl",
        "mpi1_stdout.txt",
        "mpi1_timeline.jsonl",
        "mpi1_root_pid.json",
        "mpi2_worker_summary.json",
        "mpi2_progress.jsonl",
        "mpi2_stdout.txt",
        "mpi2_timeline.jsonl",
        "mpi2_root_pid.json",
    ]
    names.extend(
        path.name
        for path in sorted(run_dir.glob("*_manifest.json"))
        if path.name != "m1_watchdog_summary.json"
    )
    names.extend(
        path.name
        for path in sorted(run_dir.glob("*_rank*.jsonl"))
    )
    return {name: _artifact(run_dir, name) for name in dict.fromkeys(names)}


def _process_gone(process: Mapping[str, Any]) -> bool:
    pids = [process.get("root_pid"), *process.get("observed_process_tree_pids", [])]
    return bool(pids) and all(
        type(pid) is int and not (Path("/proc") / str(pid)).exists() for pid in pids
    )


def _worker_dispatch_gate(
    run_dir: Path,
    phase: str,
    mpi_size: int,
    source: Mapping[str, Any],
    executable: str,
) -> bool:
    path = run_dir / f"{phase}_worker_summary.json"
    try:
        worker = _read_json(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    required = (
        "schema",
        "status",
        "run_dir",
        "phase",
        "mpi_size",
        "scope",
        "identity",
        "phase_identity",
        "runtime_identity",
        "source_at_start",
        "source_at_end",
        "measurement",
        "error",
        "controlled_stop",
        "evidence_sha256",
    )
    return bool(
        _required_mapping(worker, required)
        and _evidence_valid(worker)
        and worker["schema"] == M1_WORKER_SCHEMA
        and worker["status"] == "measurement_complete"
        and worker["run_dir"] == str(run_dir)
        and worker["phase"] == phase
        and worker["mpi_size"] == mpi_size
        and worker["scope"] == _m1_scope(mpi_size)
        and worker["identity"] == _m1_identity()
        and worker["phase_identity"] == _m1_phase_identity()
        and _m1_runtime_valid(worker["runtime_identity"], mpi_size, executable)
        and _source_pair_valid(worker["source_at_start"], worker["source_at_end"])
        and worker["source_at_start"] == source
        and worker["error"] is None
        and worker["controlled_stop"] is None
        and _progress_valid(run_dir / f"{phase}_progress.jsonl", phase)
    )


def _run_m1_watchdog(run_dir: Path) -> int:
    from benchmarks.run_task037_extra_h2b import _bounded_process_drain, _monitor_phase

    run_dir = run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(f"M1 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    source_start = _clean_source()
    started = time.perf_counter()
    phases: dict[str, Any] = {}
    error = None
    if not _source_valid(source_start):
        error = "source_not_clean"
    else:
        executable = os.path.abspath(sys.executable)
        for phase, mpi_size, limit in (
            ("mpi1", 1, M1_MPI1_RSS_LIMIT_BYTES),
            ("mpi2", 2, M1_MPI2_RSS_LIMIT_BYTES),
        ):
            if error is not None:
                phases[phase] = {"not_run_by_gate": True}
                continue
            process = _monitor_phase(
                run_dir,
                phase,
                _m1_worker_command(executable, run_dir, phase, mpi_size),
                M1_TIMEOUT_SECONDS,
                limit,
            )
            process["drain"] = _bounded_process_drain(process)
            process["processes_gone"] = bool(_process_gone(process))
            phases[phase] = process
            if not (
                process["return_code"] == 0
                and process["termination"] is None
                and process["processes_gone"]
                and process["peak_rss_bytes"] < limit
                and process["swap_bytes"] == M1_SWAP_LIMIT_BYTES
            ):
                error = f"{phase}_gate_failed"
            elif not _worker_dispatch_gate(
                run_dir, phase, mpi_size, source_start, executable
            ):
                error = f"{phase}_worker_gate_failed"
    source_end = _clean_source()
    worker_summaries = {
        phase: _artifact(run_dir, f"{phase}_worker_summary.json")
        for phase in ("mpi1", "mpi2")
    }
    payload = _attach_evidence(
        {
            "schema": M1_WATCHDOG_SCHEMA,
            "status": "pass" if error is None else "gate_failed",
            "pass": error is None,
            "route": "M1" if error is None else "M1-review-only",
            "run_dir": str(run_dir),
            "scope": _m1_scope(),
            "identity": _m1_identity(),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "command_identity": {
                "python": os.path.abspath(sys.executable),
                "mpi1_command": _m1_worker_command(
                    os.path.abspath(sys.executable), run_dir, "mpi1", 1
                ),
                "mpi2_command": _m1_worker_command(
                    os.path.abspath(sys.executable), run_dir, "mpi2", 2
                ),
            },
            "mpi1": phases.get("mpi1", {"not_run_by_gate": True}),
            "mpi2": phases.get("mpi2", {"not_run_by_gate": True}),
            "worker_summaries": worker_summaries,
            "raw_artifacts": _recorded_artifacts(run_dir),
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(run_dir / "m1_watchdog_summary.json", payload)
    print(
        f"M1 watchdog status={payload['status']} run_dir={run_dir}"
        f" elapsed={payload['elapsed_wall_seconds']:.3f}s",
        flush=True,
    )
    return 0 if payload["pass"] else 1


def _required_mapping(value: Any, keys: Sequence[str]) -> bool:
    return isinstance(value, Mapping) and all(key in value for key in keys)


def _safe_relative_path(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    path = (root / value).resolve()
    root = root.resolve()
    if path != root and root not in path.parents:
        return None
    return path


def _canonical_ref_valid(root: Path, value: Any, role: str) -> bool:
    from benchmarks.canonical_vector_artifacts import (
        read_canonical_manifest,
        read_canonical_packet_shard,
    )

    if not _required_mapping(value, ("path", "role", "sha256")):
        return False
    if value["role"] != role or not _valid_sha(value["sha256"]):
        return False
    path = _safe_relative_path(root, value["path"])
    if path is None or not path.is_file():
        return False
    if _sha256_file(path) != value["sha256"]:
        return False
    try:
        manifest = read_canonical_manifest(path, value["sha256"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if not (
        isinstance(manifest, Mapping)
        and manifest.get("role") == role
        and type(manifest.get("mpi_size")) is int
        and manifest["mpi_size"] in {1, 2}
        and manifest.get("dtype") == "complex128"
        and type(manifest.get("global_summed_packet_count")) is int
        and manifest["global_summed_packet_count"] > 0
        and isinstance(manifest.get("extractor_audit"), Mapping)
        and manifest["extractor_audit"].get("numeric_allgather") is False
        and isinstance(manifest.get("per_rank_shards"), list)
    ):
        return False
    checker_recomputed = (
        manifest.get("duplicate_detection") == "checker_recomputed_from_shards"
    )
    if checker_recomputed and manifest.get("summed_local_duplicate_count") is not None:
        return False
    if not checker_recomputed and manifest.get("summed_local_duplicate_count") != 0:
        return False
    all_keys: list[Any] = []
    packet_count = 0
    local_duplicate_count = 0
    try:
        for shard in manifest["per_rank_shards"]:
            if not _required_mapping(shard, ("filename", "packet_count", "file_sha256")):
                return False
            shard_path = _safe_relative_path(path.parent, shard["filename"])
            if (
                shard_path is None
                or type(shard["packet_count"]) is not int
                or shard["packet_count"] < 0
                or not _valid_sha(shard["file_sha256"])
            ):
                return False
            packets = read_canonical_packet_shard(
                shard_path,
                shard["file_sha256"],
            )
            if len(packets) != shard["packet_count"]:
                return False
            keys = [key for key, _value in packets]
            local_duplicate_count += len(keys) - len(set(keys))
            all_keys.extend(keys)
            packet_count += len(packets)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        packet_count == manifest["global_summed_packet_count"]
        and local_duplicate_count == 0
        and len(all_keys) == len(set(all_keys))
    )


def _progress_valid(path: Path, phase: str) -> bool:
    if not path.is_file():
        return False
    events: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                item = json.loads(raw_line)
                if not isinstance(item, Mapping):
                    return False
                if item.get("schema") != f"{M1_SCHEMA}.progress.v1":
                    return False
                if item.get("phase") != phase or not isinstance(item.get("event"), str):
                    return False
                events.append(item["event"])
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return events == list(M1_EVENTS)


def _worker_check(
    root: Path,
    worker: Any,
    process: Any,
    phase: str,
    mpi_size: int,
    rss_limit: int,
    source: Mapping[str, Any],
    executable: str,
) -> tuple[bool, str | None]:
    worker_keys = (
        "schema",
        "status",
        "run_dir",
        "phase",
        "mpi_size",
        "scope",
        "identity",
        "phase_identity",
        "runtime_identity",
        "source_at_start",
        "source_at_end",
        "measurement",
        "m1_build_audit",
        "error",
        "controlled_stop",
        "evidence_sha256",
    )
    process_keys = (
        "return_code",
        "termination",
        "peak_rss_bytes",
        "swap_bytes",
        "processes_gone",
        "drain",
    )
    if not _required_mapping(worker, worker_keys):
        return False, f"{phase}_worker_missing_key"
    if not _required_mapping(process, process_keys):
        return False, f"{phase}_process_missing_key"
    if not _evidence_valid(worker):
        return False, f"{phase}_worker_evidence"
    if not (
        worker["schema"] == M1_WORKER_SCHEMA
        and worker["status"] == "measurement_complete"
        and worker["run_dir"] == str(root)
        and worker["phase"] == phase
        and type(worker["mpi_size"]) is int
        and worker["mpi_size"] == mpi_size
        and worker["scope"] == _m1_scope(mpi_size)
        and worker["identity"] == _m1_identity()
        and worker["phase_identity"] == _m1_phase_identity()
        and _m1_runtime_valid(worker["runtime_identity"], mpi_size, executable)
        and _source_pair_valid(worker["source_at_start"], worker["source_at_end"])
        and worker["source_at_start"] == source
        and worker["error"] is None
        and worker["controlled_stop"] is None
    ):
        return False, f"{phase}_worker_identity"
    if not (
        type(process["return_code"]) is int
        and process["return_code"] == 0
        and process["termination"] is None
        and process["processes_gone"] is True
        and isinstance(process["drain"], Mapping)
        and process["drain"].get("gone") is True
        and type(process["peak_rss_bytes"]) is int
        and process["peak_rss_bytes"] >= 0
        and process["peak_rss_bytes"] < rss_limit
        and type(process["swap_bytes"]) is int
        and process["swap_bytes"] == M1_SWAP_LIMIT_BYTES
    ):
        return False, f"{phase}_resource_gate"
    measurement = worker["measurement"]
    measurement_keys = (
        "p4_global_rows",
        "p4_owned_rows",
        "p4_ghost_rows",
        "p6_global_rows",
        "p6_owned_rows",
        "p6_ghost_rows",
        "p4_global_constraints",
        "p6_global_constraints",
        "missing_rows",
        "extra_rows",
        "duplicate_rows",
        "image_relative_error",
        "adjoint_relative_error",
        "image_deterministic",
        "adjoint_deterministic",
        "finite",
        "phase_once",
        "orientation",
        "payload_audit",
        "canonical_manifests",
        "materialization_identity",
    )
    if not _required_mapping(measurement, measurement_keys):
        return False, f"{phase}_measurement_missing_key"
    integer_fields = measurement_keys[:11]
    if any(type(measurement[key]) is not int or measurement[key] < 0 for key in integer_fields):
        return False, f"{phase}_measurement_row_contract"
    if not (
        isinstance(measurement["image_relative_error"], (int, float))
        and not isinstance(measurement["image_relative_error"], bool)
        and isinstance(measurement["adjoint_relative_error"], (int, float))
        and not isinstance(measurement["adjoint_relative_error"], bool)
        and math.isfinite(float(measurement["image_relative_error"]))
        and measurement["image_relative_error"] <= M1_IMAGE_LIMIT
        and math.isfinite(float(measurement["adjoint_relative_error"]))
        and measurement["adjoint_relative_error"] <= M1_ADJOINT_LIMIT
        and measurement["image_deterministic"] is True
        and measurement["adjoint_deterministic"] is True
        and measurement["finite"] is True
        and measurement["phase_once"] is True
        and measurement["missing_rows"] == 0
        and measurement["extra_rows"] == 0
        and measurement["duplicate_rows"] == 0
    ):
        return False, f"{phase}_numeric_gate"
    audit = worker["m1_build_audit"]
    audit_keys = (
        "m1_gate_pass",
        "structural_build_pass",
        "global_transfer_matrix_materialized",
        "global_matrix_materialized",
        "global_constraint_matrix_materialized",
        "numeric_allgather",
        "replicated_global_numeric_vector",
        "retained_numeric_payload_components",
        "retained_numeric_payload_bytes",
        "lazy_p6_work_vec_bytes",
        "retained_transfer_numeric_payload_bytes",
        "retained_transfer_numeric_payload_gate",
        "bounded_apply_workspace_bytes",
        "bounded_apply_workspace_gate",
        "bounded_apply_workspace_components",
        "orientation_metadata_sha256",
        "reference_transform_sha256",
    )
    if not _required_mapping(audit, audit_keys):
        return False, f"{phase}_build_audit_missing_key"
    if (
        audit["m1_gate_pass"] is not False
        or audit["structural_build_pass"] is not True
        or any(audit[key] is not False for key in audit_keys[2:7])
        or not _valid_sha(audit["orientation_metadata_sha256"])
        or not _valid_sha(audit["reference_transform_sha256"])
        or type(audit["retained_transfer_numeric_payload_bytes"]) is not int
        or type(audit["bounded_apply_workspace_bytes"]) is not int
    ):
        return False, f"{phase}_build_audit_semantics"
    forbidden = measurement["materialization_identity"]
    forbidden_keys = (
        "global_transfer_matrix",
        "global_matrix",
        "global_constraint_matrix",
        "condensed",
        "trace_only",
        "ksp_or_pde",
        "numeric_allgather",
        "replicated_global_numeric_vector",
    )
    if not _required_mapping(forbidden, forbidden_keys) or any(
        forbidden[key] is not False for key in forbidden_keys
    ):
        return False, f"{phase}_forbidden_materialization"
    manifests = measurement["canonical_manifests"]
    if not _required_mapping(manifests, ("p6_image", "p4_adjoint")):
        return False, f"{phase}_canonical_missing_key"
    if not (
        _canonical_ref_valid(root, manifests["p6_image"], f"{phase}_p6_image")
        and _canonical_ref_valid(root, manifests["p4_adjoint"], f"{phase}_p4_adjoint")
    ):
        return False, f"{phase}_canonical_manifest"
    payload = measurement["payload_audit"]
    payload_keys = (
        "retained_numeric_payload_components",
        "retained_numeric_payload_bytes",
        "lazy_p6_work_vec_bytes",
        "retained_transfer_numeric_payload_bytes",
        "bounded_apply_workspace_bytes",
        "bounded_apply_workspace_components",
        "construction_transient_numeric_payload_bytes",
        "measured_process_tree_rss_bytes",
    )
    if not _required_mapping(payload, payload_keys):
        return False, f"{phase}_payload_missing_key"
    if not (
        payload["retained_numeric_payload_components"]
        == audit["retained_numeric_payload_components"]
        and payload["bounded_apply_workspace_components"]
        == audit["bounded_apply_workspace_components"]
        and payload["retained_numeric_payload_bytes"]
        == audit["retained_numeric_payload_bytes"]
        and payload["lazy_p6_work_vec_bytes"] == audit["lazy_p6_work_vec_bytes"]
        and payload["retained_transfer_numeric_payload_bytes"]
        == audit["retained_transfer_numeric_payload_bytes"]
        and payload["bounded_apply_workspace_bytes"]
        == audit["bounded_apply_workspace_bytes"]
    ):
        return False, f"{phase}_payload_binding"
    if not (
        type(payload["retained_transfer_numeric_payload_bytes"]) is int
        and payload["retained_transfer_numeric_payload_bytes"]
        <= M1_RETAINED_PAYLOAD_LIMIT_BYTES
        and type(payload["bounded_apply_workspace_bytes"]) is int
        and payload["bounded_apply_workspace_bytes"] <= M1_WORKSPACE_LIMIT_BYTES
        and audit["retained_transfer_numeric_payload_gate"] is True
        and audit["bounded_apply_workspace_gate"] is True
    ):
        return False, f"{phase}_payload_contract"
    if any(
        type(payload[key]) is not int or payload[key] < 0
        for key in (
            "retained_numeric_payload_bytes",
            "lazy_p6_work_vec_bytes",
            "retained_transfer_numeric_payload_bytes",
            "bounded_apply_workspace_bytes",
        )
    ):
        return False, f"{phase}_payload_contract"
    return True, None


def _m1_check_raw(run_dir: Path, checker_source: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    problems: list[str] = []
    canonical_results: dict[str, Any] = {}
    try:
        watchdog = _read_json(run_dir / "m1_watchdog_summary.json")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "schema": M1_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "route": "M1-review-only",
            "checks": {"watchdog_readable": False},
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
            "measurements": None,
            "checker_source": _plain(checker_source),
        }
    watchdog_keys = (
        "schema",
        "status",
        "pass",
        "route",
        "run_dir",
        "scope",
        "identity",
        "source_at_start",
        "source_at_end",
        "command_identity",
        "mpi1",
        "mpi2",
        "worker_summaries",
        "raw_artifacts",
        "evidence_sha256",
    )
    checks["watchdog_schema"] = _required_mapping(watchdog, watchdog_keys) and _evidence_valid(watchdog)
    if not checks["watchdog_schema"]:
        problems.append("watchdog_schema")
        watchdog = {key: None for key in watchdog_keys}
    source = watchdog["source_at_start"]
    checks["source_authority"] = bool(
        _source_pair_valid(watchdog["source_at_start"], watchdog["source_at_end"])
        and watchdog["source_at_start"] == watchdog["source_at_end"]
        and _source_valid(checker_source)
        and checker_source == watchdog["source_at_start"]
    )
    checks["scope_identity"] = bool(
        watchdog["scope"] == _m1_scope()
        and watchdog["identity"] == _m1_identity()
        and watchdog["run_dir"] == str(run_dir)
    )
    command = watchdog["command_identity"]
    checks["command_identity"] = bool(
        _required_mapping(command, ("python", "mpi1_command", "mpi2_command"))
        and isinstance(command["python"], str)
        and os.path.isabs(command["python"])
        and command["mpi1_command"] == _m1_worker_command(command["python"], run_dir, "mpi1", 1)
        and command["mpi2_command"] == _m1_worker_command(command["python"], run_dir, "mpi2", 2)
    )
    mpi1 = watchdog["mpi1"]
    mpi1_gate, mpi1_problem = _phase_process_shape(mpi1, 1, M1_MPI1_RSS_LIMIT_BYTES)
    checks["mpi1_process"] = mpi1_gate
    if mpi1_problem:
        problems.append(mpi1_problem)
    checks["mpi1_timeline"] = _timeline_resource_valid(
        run_dir / "mpi1_timeline.jsonl", mpi1, M1_MPI1_RSS_LIMIT_BYTES, "mpi1"
    )
    if not checks["mpi1_timeline"]:
        problems.append("mpi1_timeline")
    mpi1_summary_ref = watchdog["worker_summaries"]["mpi1"] if _required_mapping(watchdog["worker_summaries"], ("mpi1", "mpi2")) else None
    mpi1_worker = None
    if isinstance(mpi1_summary_ref, Mapping) and mpi1_summary_ref.get("present") is True:
        try:
            mpi1_worker = _read_json(run_dir / "mpi1_worker_summary.json")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            mpi1_worker = None
    worker_ok, worker_problem = _worker_check(
        run_dir,
        mpi1_worker,
        mpi1,
        "mpi1",
        1,
        M1_MPI1_RSS_LIMIT_BYTES,
        source,
        watchdog["command_identity"]["python"],
    )
    checks["mpi1_worker"] = worker_ok
    if worker_problem:
        problems.append(worker_problem)
    checks["mpi1_markers"] = _progress_valid(run_dir / "mpi1_progress.jsonl", "mpi1")
    if not checks["mpi1_markers"]:
        problems.append("mpi1_markers")
    mpi2 = watchdog["mpi2"]
    if not mpi1_gate or not worker_ok:
        checks["mpi2_not_run_by_gate"] = bool(
            _required_mapping(mpi2, ("not_run_by_gate",))
            and mpi2["not_run_by_gate"] is True
            and watchdog["status"] == "gate_failed"
        )
        checks["mpi2_process"] = True
        checks["mpi2_worker"] = True
        checks["mpi2_markers"] = True
        checks["mpi2_timeline"] = True
    else:
        mpi2_gate, mpi2_problem = _phase_process_shape(mpi2, 2, M1_MPI2_RSS_LIMIT_BYTES)
        checks["mpi2_process"] = mpi2_gate
        if mpi2_problem:
            problems.append(mpi2_problem)
        checks["mpi2_timeline"] = _timeline_resource_valid(
            run_dir / "mpi2_timeline.jsonl", mpi2, M1_MPI2_RSS_LIMIT_BYTES, "mpi2"
        )
        if not checks["mpi2_timeline"]:
            problems.append("mpi2_timeline")
        mpi2_summary_ref = watchdog["worker_summaries"]["mpi2"]
        mpi2_worker = None
        if isinstance(mpi2_summary_ref, Mapping) and mpi2_summary_ref.get("present") is True:
            try:
                mpi2_worker = _read_json(run_dir / "mpi2_worker_summary.json")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                mpi2_worker = None
        worker2_ok, worker2_problem = _worker_check(
            run_dir,
            mpi2_worker,
            mpi2,
            "mpi2",
            2,
            M1_MPI2_RSS_LIMIT_BYTES,
            source,
            watchdog["command_identity"]["python"],
        )
        checks["mpi2_worker"] = worker2_ok
        if worker2_problem:
            problems.append(worker2_problem)
        checks["mpi2_markers"] = _progress_valid(run_dir / "mpi2_progress.jsonl", "mpi2")
        if not checks["mpi2_markers"]:
            problems.append("mpi2_markers")
        if worker_ok and worker2_ok:
            for role in ("p6_image", "p4_adjoint"):
                left = mpi1_worker["measurement"]["canonical_manifests"][role]
                right = mpi2_worker["measurement"]["canonical_manifests"][role]
                left_path = _safe_relative_path(run_dir, left["path"])
                right_path = _safe_relative_path(run_dir, right["path"])
                if left_path is None or right_path is None:
                    checks[f"canonical_{role}"] = False
                    problems.append(f"canonical_{role}_path")
                    continue
                from benchmarks.canonical_vector_artifacts import compare_canonical_manifests

                try:
                    comparison = compare_canonical_manifests(
                        left_path,
                        right_path,
                        left_sha256=left["sha256"],
                        right_sha256=right["sha256"],
                        relative_tolerance=M1_CANONICAL_LIMIT,
                    )
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                    comparison = {"pass": False}
                canonical_results[role] = comparison
                checks[f"canonical_{role}"] = bool(comparison.get("pass") is True)
                if not checks[f"canonical_{role}"]:
                    problems.append(f"canonical_{role}")
    actual_artifacts = _recorded_artifacts(run_dir)
    recorded_artifacts = watchdog["raw_artifacts"]
    checks["raw_artifacts"] = bool(
        isinstance(recorded_artifacts, Mapping)
        and set(recorded_artifacts) == set(actual_artifacts)
        and all(recorded_artifacts[name] == actual_artifacts[name] for name in actual_artifacts)
    )
    if not checks["raw_artifacts"]:
        problems.append("raw_artifacts")
    passed = bool(all(checks.values()) and watchdog["status"] == "pass" and watchdog["pass"] is True)
    if not passed and not problems:
        problems.append("m1_gate_failed")
    return {
        "schema": M1_CHECK_SCHEMA,
        "status": "pass" if passed else "gate_failed",
        "pass": passed,
        "route": "M1" if passed else "M1-review-only",
        "checks": checks,
        "problems": list(dict.fromkeys(problems)),
        "measurements": {
            "mpi1": mpi1,
            "mpi2": mpi2,
            "canonical_comparisons": canonical_results,
        } if passed else None,
        "checker_source": _plain(checker_source),
        "raw_artifacts": _plain(recorded_artifacts),
    }


def _phase_process_shape(value: Any, mpi_size: int, limit: int) -> tuple[bool, str | None]:
    if not isinstance(value, Mapping):
        return False, f"mpi{mpi_size}_process_missing"
    required = ("return_code", "termination", "peak_rss_bytes", "swap_bytes", "processes_gone", "drain")
    if any(key not in value for key in required):
        return False, f"mpi{mpi_size}_process_missing_key"
    if not (
        type(value["return_code"]) is int
        and value["return_code"] == 0
        and value["termination"] is None
        and type(value["peak_rss_bytes"]) is int
        and value["peak_rss_bytes"] >= 0
        and value["peak_rss_bytes"] < limit
        and type(value["swap_bytes"]) is int
        and value["swap_bytes"] == 0
        and value["processes_gone"] is True
        and isinstance(value["drain"], Mapping)
        and value["drain"].get("gone") is True
    ):
        return False, f"mpi{mpi_size}_process_gate"
    return True, None


def _timeline_resource_valid(
    path: Path,
    process: Mapping[str, Any],
    limit: int,
    phase: str,
) -> bool:
    samples: list[Mapping[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                item = json.loads(raw_line)
                if not isinstance(item, Mapping):
                    return False
                if item.get("phase") != phase:
                    return False
                if item.get("sample_kind") == "worker":
                    samples.append(item)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    if not samples:
        return False
    rss = []
    swap = []
    for item in samples:
        if (
            type(item.get("rss_bytes")) is not int
            or type(item.get("swap_bytes")) is not int
            or item["rss_bytes"] < 0
            or item["rss_bytes"] >= limit
            or item["swap_bytes"] != M1_SWAP_LIMIT_BYTES
            or item.get("all_status_readable") is not True
        ):
            return False
        rss.append(item["rss_bytes"])
        swap.append(item["swap_bytes"])
    return bool(
        max(rss) == process["peak_rss_bytes"]
        and max(swap) == process["swap_bytes"]
    )


def _run_m1_check(run_dir: Path, output: Path) -> int:
    checker_source = _clean_source()
    result = _m1_check_raw(run_dir.resolve(), checker_source)
    _write_json(output.resolve(), _attach_evidence(result))
    print(f"M1 check status={result['status']} output={output.resolve()}", flush=True)
    return 0 if result["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_task037_extra_m")
    sub = parser.add_subparsers(dest="command", required=True)
    worker = sub.add_parser("m1-worker")
    worker.add_argument("--run-dir", required=True)
    worker.add_argument("--phase", choices=("mpi1", "mpi2"), required=True)
    worker.add_argument("--expected-mpi-size", type=int, required=True)
    watchdog = sub.add_parser("m1-watchdog")
    watchdog.add_argument("--run-dir", required=True)
    checker = sub.add_parser("m1-check")
    checker.add_argument("--run-dir", required=True)
    checker.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "m1-worker":
        return _run_m1_worker(Path(args.run_dir), args.phase, args.expected_mpi_size)
    if args.command == "m1-watchdog":
        return _run_m1_watchdog(Path(args.run_dir))
    return _run_m1_check(Path(args.run_dir), Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
