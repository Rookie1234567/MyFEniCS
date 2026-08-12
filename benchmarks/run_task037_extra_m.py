"""Thin M1/M2 opt-in evidence routes.

M1 records the reviewed owner-local p4/p6 transfer.  M2 adds one bounded
high-complement patch oracle.  Neither route is imported by the production
default.
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
    _bounded_process_drain as _h2b_bounded_process_drain,
    _build_b0_form as _h2b_build_b0_form,
    _cache_snapshot as _h2b_cache_snapshot,
    _expected_jit_options as _h2b_expected_jit_options,
    _form_record as _h2b_form_record,
    _forms_match as _h2b_forms_match,
    _monitor_phase as _h2b_monitor_phase,
    _p1_authority as _h2b_p1_authority,
    _phase_identity as _h2b_phase_identity,
    _stage_gate_allows_online as _h2b_stage_gate_allows_online,
    _timeline_metrics as _h2b_timeline_metrics,
    _worker_error_types as _h2b_worker_error_types,
    H2B_R2_MANIFEST,
    _lazy_h2a,
    _light_source as _clean_source,
    _read_json,
    _residual_source_arrays as _h2b_residual_source_arrays,
    _sha256_file,
    _source_arrays as _h2b_source_arrays,
    _worker_command as _h2b_worker_command,
    _write_json,
)
from src.solvers.hcurl_h2b_block_smoother import _p0_numeric_sha
from src.solvers.hcurl_h2b_m2_complement import (
    M2_Q_ORTHOGONALITY_LIMIT,
    M2_SPLIT_RECONSTRUCTION_LIMIT,
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
M2_SCHEMA = "task037.extra.m2.high-complement-patch-oracle"
M2_WORKER_SCHEMA = f"{M2_SCHEMA}.worker.v1"
M2_WATCHDOG_SCHEMA = f"{M2_SCHEMA}.watchdog.v1"
M2_CHECK_SCHEMA = f"{M2_SCHEMA}.check.v1"
M2_TIMEOUT_SECONDS = 1_800.0
M2_RSS_LIMIT_BYTES = 1_300_000_000
M2_SWAP_LIMIT_BYTES = 0
M2_FACTOR_BYTES_LIMIT = 5_500_000
M2_TRANSFORM_BYTES_LIMIT = 32_000_000
M2_ACTION_CLOSURE_LIMIT = 1.0e-11
M2_FACTOR_RESIDUAL_LIMIT = 1.0e-10
M2_CHECKERBOARD_RHO_LIMIT = 0.70
M2_MIXED_RHO_LIMIT = 0.90
M2_OTHER_RHO_LIMIT = 0.98
M2_SOURCE_LABELS = (
    "gradient-dominated",
    "curl-dominated",
    "mixed",
    "checkerboard/high-frequency",
    "physical-RHS-like",
)
M2_FORM_REUSE_ARTIFACT = "m2_form_reuse.json"
M2_FORM_REUSE_SCHEMA = f"{M2_SCHEMA}.form-reuse.v1"
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


def _m2_scope() -> dict[str, Any]:
    return {
        "mode": "isolated_jit_stage_then_warm_online",
        "numerical_route": "m2_high_complement_patch_oracle",
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "global_cells": 252,
        "global_rows": 173802,
        "constraint_count": 9210,
        "central_cell_ordinal": 3,
        "central_class_id": 3,
        "touching_cell_count": 19,
        "patch_row_count": 882,
        "low_rank": 300,
        "high_rank": 582,
        "timeout_seconds": M2_TIMEOUT_SECONDS,
        "rss_limit_bytes": M2_RSS_LIMIT_BYTES,
        "stage_rss_limit_bytes": M2_RSS_LIMIT_BYTES,
        "online_rss_limit_bytes": M2_RSS_LIMIT_BYTES,
        "swap_limit_bytes": M2_SWAP_LIMIT_BYTES,
        "factor_values_pivots_limit_bytes": M2_FACTOR_BYTES_LIMIT,
        "retained_transform_limit_bytes": M2_TRANSFORM_BYTES_LIMIT,
        "operator": "K_curl+k0^2*M_abs_epsilon; code uses (1/mu_r) with mu_r=1",
        "patch_definition": "restricted-global row-complete B_P from the qualified P0 stream",
        "construction": "one central constrained/oriented I_c and one high-complement factor",
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "ordinary_default_changed": False,
    }


def _m2_identity() -> dict[str, Any]:
    return {
        "fine_space": "uncondensed_fullspace",
        "condensation": False,
        "static_condensed_operator_used": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "schur_or_slab_materialized": False,
        "per_neighborhood_qh_retained": False,
        "global_numeric_allgather": False,
        "local_krylov_or_ksp_called": False,
        "pde_called": False,
        "ordinary_default_changed": False,
    }


def _m2_phase_identity() -> dict[str, Any]:
    return {
        "phase": "online",
        "form_jit_used": True,
        "compile_called": False,
        "compiler_probe_called": False,
        "tensor_tabulation_called": True,
        "factorization_called": True,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "ordinary_default_changed": False,
    }


def _m2_stage_summary_valid(stage_summary: Any, run_dir: Path) -> bool:
    """Validate the existing H2B cold JIT authority before M2 starts."""

    if not isinstance(stage_summary, Mapping):
        return False
    try:
        return bool(
            _h2b_stage_gate_allows_online(
                {"return_code": 0, "termination": None},
                stage_summary,
                True,
                run_dir,
            )
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _m2_stage_gate_valid(
    stage_process: Any,
    stage_summary: Any,
    run_dir: Path,
    processes_gone: bool,
) -> bool:
    """Apply the existing stage contract plus the stricter M2 RSS limit."""

    if not isinstance(stage_process, Mapping):
        return False
    if not _m2_stage_summary_valid(stage_summary, run_dir):
        return False
    if not (
        type(stage_process.get("return_code")) is int
        and stage_process["return_code"] == 0
        and stage_process.get("termination") is None
        and processes_gone is True
        and type(stage_process.get("peak_rss_bytes")) is int
        and stage_process["peak_rss_bytes"] < M2_RSS_LIMIT_BYTES
        and stage_process.get("swap_bytes") == M2_SWAP_LIMIT_BYTES
    ):
        return False
    return _m2_timeline_resource_valid(
        run_dir / "stage_timeline.jsonl",
        stage_process,
        "stage",
        require_no_compiler=False,
    )


def _m2_timeline_resource_valid(
    path: Path,
    process: Mapping[str, Any],
    phase: str,
    *,
    require_no_compiler: bool,
) -> bool:
    try:
        metrics = _h2b_timeline_metrics(path, phase)
    except _h2b_worker_error_types():
        return False
    return bool(
        type(process.get("peak_rss_bytes")) is int
        and process["peak_rss_bytes"] == metrics["peak_rss_bytes"]
        and process["peak_rss_bytes"] < M2_RSS_LIMIT_BYTES
        and type(process.get("swap_bytes")) is int
        and process["swap_bytes"] == metrics["swap_bytes"] == M2_SWAP_LIMIT_BYTES
        and (not require_no_compiler or metrics["compiler_descendant_pids"] == [])
    )


def _m2_online_cache_valid(
    measurement: Any,
    form: Any,
    stage_form: Any,
    run_dir: Path,
) -> bool:
    if not isinstance(measurement, Mapping) or not isinstance(measurement.get("cache"), Mapping):
        return False
    cache = measurement["cache"]
    try:
        snapshot = _h2b_cache_snapshot(run_dir / "jit_cache")
    except (OSError, ValueError):
        return False
    return bool(
        cache.get("before") == cache.get("after") == snapshot
        and cache.get("unchanged") is True
        and cache.get("form_jit_cache_hit") is True
        and cache.get("c_source_regeneration") is False
        and cache.get("compiler_descendant_pids") == []
        and measurement.get("stage_manifest_sha256") == _sha256_file(run_dir / "stage_summary.json")
        and _h2b_forms_match(stage_form, form, run_dir)
    )


def _m2_mark(run_dir: Path, event: str, started: float, **fields: Any) -> None:
    path = run_dir / "m2_progress.jsonl"
    item = {
        "schema": f"{M2_SCHEMA}.progress.v1",
        "phase": "m2",
        "event": event,
        "event_index": sum(1 for _line in path.open("r", encoding="utf-8")) if path.exists() else 0,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
        **fields,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()


def _m2_worker_command(executable: str, run_dir: Path) -> list[str]:
    return [
        "mpiexec",
        "-n",
        "1",
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_m",
        "m2-worker",
        "--run-dir",
        str(run_dir.resolve()),
    ]


def _m2_save_array(run_dir: Path, name: str, value: Any) -> None:
    import numpy as np

    np.save(run_dir / name, np.asarray(value), allow_pickle=False)


def _m2_recorded_artifacts(run_dir: Path) -> dict[str, dict[str, Any]]:
    names = [
        "stage_progress.jsonl",
        "stage_stdout.txt",
        "stage_summary.json",
        "stage_timeline.jsonl",
        "stage_root_pid.json",
        "m2_progress.jsonl",
        "m2_stdout.txt",
        M2_FORM_REUSE_ARTIFACT,
        "m2_worker_summary.json",
        "m2_timeline.jsonl",
        "m2_root_pid.json",
        "m2_injection.npy",
        "m2_patch.npy",
        "m2_patch_rows.npy",
        "m2_q_high.npy",
        "m2_factor_values.npy",
        "m2_factor_pivots.npy",
        "m2_source_rhs.npy",
        "m2_source_corrections.npy",
        "m2_source_actions.npy",
    ]
    return {name: _artifact(run_dir, name) for name in names}


def _m2_write_form_reuse(
    run_dir: Path,
    source: Mapping[str, Any],
    stage_summary: Mapping[str, Any],
    form_record: Mapping[str, Any],
    cache_before: list[dict[str, Any]],
    cache_after: list[dict[str, Any]],
) -> dict[str, Any]:
    checks = {
        "code_state_hit": form_record.get("code_state") == "hit_no_new_decl_impl",
        "cache_unchanged": cache_before == cache_after,
        "forms_match": bool(_h2b_forms_match(stage_summary.get("form"), form_record, run_dir)),
    }
    payload = _attach_evidence(
        {
            "schema": M2_FORM_REUSE_SCHEMA,
            "phase": "online",
            "source": _plain(source),
            "stage_manifest_sha256": _sha256_file(run_dir / "stage_summary.json"),
            "online_form": _plain(form_record),
            "cache": {
                "before": _plain(cache_before),
                "after": _plain(cache_after),
            },
            "checks": checks,
            "all_pass": all(value is True for value in checks.values()),
        }
    )
    _write_json(run_dir / M2_FORM_REUSE_ARTIFACT, payload)
    return payload


def _m2_prepare_p0_patch(h2a: Any, function_space: Any, mesh_data: Any, cfg: Any, floquet: Any, run_dir: Path) -> dict[str, Any]:
    """Reuse the P0 discovery/stream authority without factoring its matrix."""

    import numpy as np

    from src.solvers.hcurl_h2b_block_smoother import (
        discover_h2b_p0_touching_cells,
        group_h2b_p0_touching_cells_by_class,
        select_h2b_p0_class,
        stream_h2b_p0_patch,
    )
    from src.solvers.hcurl_r2_constrained_local_block import (
        H2AR2CellExpansion,
        build_h2a_r2_cell_expansion,
    )
    from src.solvers.hcurl_r2_factor_store import (
        H2AR2CellReference,
        load_h2a_r2_factor_store,
    )

    index_map = function_space.dofmap.index_map
    discovery = h2a._discover_cell_references(
        function_space,
        mesh_data,
        cfg,
        floquet,
        geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
    )
    authority = _h2b_p1_authority()
    inventory = authority["r0"]["class_inventory"]
    key_to_id = {str(item["class_key_sha256"]): int(item["class_id"]) for item in inventory}
    blocks = tuple(floquet.phase_independent_topology.blocks)
    expansions: dict[int, Any] = {}
    cell_refs: list[Any] = []
    for reference in discovery["references"]:
        cell_dofs = np.asarray(reference.local_dofs, dtype=np.int64)
        class_id = key_to_id.get(h2a._r0_digest(reference.class_key))
        if class_id is None:
            raise ValueError("M2 discovery class is not in frozen R0 authority")
        expansion = build_h2a_r2_cell_expansion(
            h2a._blocks_for_cell(blocks, cell_dofs),
            cell_dofs,
            index_map,
            index_map_bs=int(function_space.dofmap.index_map_bs),
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        )
        previous = expansions.get(class_id)
        if previous is not None and previous.pattern_sha256 != expansion.pattern_sha256:
            raise ValueError("M2 expansion pattern differs within an exact class")
        expansions.setdefault(class_id, expansion)
        cell_refs.append(H2AR2CellReference(class_id, expansion.independent_global_rows))
    if len(cell_refs) != 252:
        raise ValueError("M2 discovery did not produce 252 cell references")
    r2_store = load_h2a_r2_factor_store(H2B_R2_MANIFEST, task037_extra_h2a_r2=True)
    if r2_store.audit.get("factor_plus_metadata_bytes") != 201_933_812:
        raise ValueError("M2 R2 factor authority payload changed")
    if len(r2_store.cells) != len(cell_refs) or any(
        int(left.class_id) != int(right.class_id)
        or not np.array_equal(left.independent_global_rows, right.independent_global_rows)
        for left, right in zip(r2_store.cells, cell_refs, strict=True)
    ):
        raise ValueError("M2 R2 cell authority does not match fresh discovery")
    selection = select_h2b_p0_class(inventory, task037_extra_h2b=True)
    central = min(
        (ordinal for ordinal, reference in enumerate(cell_refs) if int(reference.class_id) == int(selection["class_id"])),
        default=-1,
    )
    patch_rows = np.ascontiguousarray(cell_refs[central].independent_global_rows, dtype=np.int64)
    touching = discover_h2b_p0_touching_cells(cell_refs, patch_rows, task037_extra_h2b=True)
    groups = group_h2b_p0_touching_cells_by_class(cell_refs, touching, task037_extra_h2b=True)
    if (central, int(cell_refs[central].class_id), len(touching), len(groups)) != (3, 3, 19, 11):
        raise ValueError("M2 P0 representative topology does not close")
    tolerance = h2a.floquet_geometry_tolerance(cfg)
    proxy_forms = h2a._proxy_forms(
        function_space,
        mesh_data,
        cfg,
        cache_dir=h2a.R2_R1_JIT_CACHE_DIR,
    )
    tags = discovery["tags"]

    def tensor_stream():
        for class_id, class_cells in groups:
            representative = int(class_cells[0])
            template = expansions[class_id]
            curl_tensor, _widths, _info = h2a.tabulate_task037_extra_h2a_cell_tensor(
                proxy_forms[0], function_space, mesh_data.cell_tags, representative, geometry_tolerance=tolerance
            )
            mass_tensor, _widths, _info = h2a.tabulate_task037_extra_h2a_cell_tensor(
                proxy_forms[1], function_space, mesh_data.cell_tags, representative, geometry_tolerance=tolerance
            )
            proxy = np.ascontiguousarray(
                h2a.build_b0_proxy_tensor(
                    curl_tensor,
                    mass_tensor,
                    k0=float(cfg.k0),
                    abs_epsilon=float(abs(h2a._material_epsilon(cfg, int(tags[representative])))),
                ),
                dtype=np.complex128,
            )
            for cell in class_cells:
                yield int(cell), proxy, H2AR2CellExpansion(
                    offsets=template.offsets,
                    column_indices=template.column_indices,
                    coefficients=template.coefficients,
                    independent_global_rows=cell_refs[cell].independent_global_rows,
                    pattern_identity=template.pattern_identity,
                    pattern_sha256=template.pattern_sha256,
                )
            del curl_tensor, mass_tensor, proxy

    patch = stream_h2b_p0_patch(
        cell_refs,
        patch_rows,
        tensor_stream(),
        task037_extra_h2b=True,
    )
    patch_matrix = np.ascontiguousarray(patch.pop("matrix"), dtype=np.complex128)
    patch["matrix_sha256"] = _p0_numeric_sha(patch_matrix)
    patch["central_cell_ordinal"] = central
    patch["central_class_id"] = int(cell_refs[central].class_id)
    patch["patch_row_count"] = int(patch_rows.size)
    patch["patch_definition"] = "restricted-global row-complete B_P"
    patch["p0_authority_record_sha256"] = authority["p0"]["record_sha256"]
    patch["p0_authority_evidence_sha256"] = authority["p0"]["evidence_sha256"]
    patch["touching_class_ids"] = [int(class_id) for class_id, _cells in groups]
    patch["touching_class_count"] = len(groups)
    patch["tensor_tabulation_cell_count"] = len(groups)
    patch["tensor_reuse_cell_count"] = len(touching) - len(groups)
    patch["max_live_dense_proxy_count"] = 1
    patch["cell_dense_tensors_retained"] = False
    return {
        "authority": authority,
        "cell_refs": tuple(cell_refs),
        "expansions": expansions,
        "central_cell_ordinal": central,
        "patch_rows": patch_rows,
        "patch_matrix": patch_matrix,
        "patch_audit": patch,
    }


def _run_m2_worker(run_dir: Path) -> int:
    import numpy as np
    from petsc4py import PETSc
    from mpi4py import MPI
    from dolfinx import default_real_type, fem
    from basix.ufl import element
    from dataclasses import replace

    from src.common.config_3d import target_stage4_config
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.hcurl_h2b_block_smoother import factorize_h2b_p0_patch
    from src.solvers.hcurl_h2b_m2_complement import (
        build_h2b_m2_cell_injection,
        build_h2b_m2_complement,
        measure_h2b_m2_source,
    )
    from src.solvers.hcurl_p_split_owner_transfer import build_owner_local_p4_p6_transfer
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise ValueError("M2 formal worker is fixed to MPI1")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_start = _clean_source()
    if not _source_valid(source_start):
        raise RuntimeError("M2 worker requires a clean source")
    action = source_vec = transfer = factor = None
    stage_path = run_dir / "stage_summary.json"
    cache_dir = run_dir / "jit_cache"
    stage_summary: Mapping[str, Any] | None = None
    cache_before: list[dict[str, Any]] | None = None
    cache_after: list[dict[str, Any]] | None = None
    form_reuse: dict[str, Any] | None = None
    try:
        _m2_mark(run_dir, "authority_validated", started)
        stage_summary = _read_json(stage_path)
        if not _m2_stage_summary_valid(stage_summary, run_dir):
            raise ValueError("M2 isolated JIT stage authority is invalid")
        _m2_mark(
            run_dir,
            "stage_summary_validated",
            started,
            stage_manifest_sha256=_sha256_file(stage_path),
        )
        cfg = target_stage4_config(degree=6, h_nm=10.0)
        mesh_data = build_airbox_mesh_3d(cfg, run_dir / "m2_mesh")
        _m2_mark(run_dir, "mesh_ready", started)
        p4_space = fem.functionspace(mesh_data.mesh, element("N1curl", mesh_data.mesh.basix_cell(), 4, dtype=default_real_type))
        p6_space = fem.functionspace(mesh_data.mesh, element("N1curl", mesh_data.mesh.basix_cell(), 6, dtype=default_real_type))
        _m2_mark(run_dir, "space_ready", started)
        p4_cfg = replace(cfg, nedelec_degree=4)
        floquet4 = build_double_floquet_mpc(p4_space, mesh_data, p4_cfg)
        floquet6 = build_double_floquet_mpc(p6_space, mesh_data, cfg)
        _m2_mark(run_dir, "floquet_mpc_ready", started)
        transfer = build_owner_local_p4_p6_transfer(p4_space, p6_space, p4_mpc=floquet4.mpc, p6_mpc=floquet6.mpc)
        cache_before = _h2b_cache_snapshot(cache_dir)
        b0, _epsilon = _h2b_build_b0_form(p6_space, mesh_data, cfg)
        action = build_task037_extra_h1r2_mpc_action(
            b0,
            floquet6.mpc,
            task037_extra_h1r2=True,
            jit_options=_h2b_expected_jit_options(cache_dir),
        )
        form_record = _h2b_form_record(
            action._action_form,
            action._action_ufl,
            cache_dir,
            cfg,
            p6_space,
            "b0",
        )
        cache_after = _h2b_cache_snapshot(cache_dir)
        form_reuse = _m2_write_form_reuse(
            run_dir,
            _clean_source(),
            stage_summary,
            form_record,
            cache_before,
            cache_after,
        )
        if form_reuse["all_pass"] is not True:
            checks = form_reuse["checks"]
            raise ValueError(
                "M2 online B0 form reuse failed: "
                f"code_state_hit={checks['code_state_hit']}, "
                f"cache_unchanged={checks['cache_unchanged']}, "
                f"forms_match={checks['forms_match']}"
            )
        _m2_mark(run_dir, "b0_action_ready", started)
        prepared = _m2_prepare_p0_patch(_lazy_h2a(), p6_space, mesh_data, cfg, floquet6, run_dir)
        _m2_mark(run_dir, "p0_authority_ready", started, touching_cell_count=19)
        central_cell = int(prepared["central_cell_ordinal"])
        central_stencil = next(cell for cell in transfer._cells if int(cell.global_cell) == central_cell)
        p4_dofs = np.asarray(central_stencil.p4_local_dofs, dtype=np.int32)
        p6_dofs = np.asarray(central_stencil.p6_local_dofs, dtype=np.int32)
        p4_global = np.asarray(p4_space.dofmap.index_map.local_to_global(p4_dofs), dtype=np.int64)
        p6_global = np.asarray(p6_space.dofmap.index_map.local_to_global(p6_dofs), dtype=np.int64)
        injection = build_h2b_m2_cell_injection(
            patch_rows=prepared["patch_rows"],
            p4_global_rows=p4_global,
            p4_cell_dofs=p4_dofs,
            p6_global_rows=p6_global,
            p6_cell_dofs=p6_dofs,
            p4_local_rows=transfer.p4_constraints.local_rows,
            p6_local_rows=transfer.p6_constraints.local_rows,
            cell_info=int(central_stencil.cell_info),
            local_apply=transfer.apply_reference,
            p4_lift=transfer.p4_constraints.lift_in_place,
            p6_lift=transfer.p6_constraints.lift_in_place,
        )
        carrier = build_h2b_m2_complement(injection)
        _m2_mark(run_dir, "complement_ready", started, rank=300, high_rank=582)
        high_matrix = np.ascontiguousarray(carrier.q_high.conj().T @ prepared["patch_matrix"] @ carrier.q_high, dtype=np.complex128)
        factor = factorize_h2b_p0_patch(high_matrix, task037_extra_h2b=True)
        high_repeat = np.ascontiguousarray(carrier.q_high.conj().T @ prepared["patch_matrix"] @ carrier.q_high, dtype=np.complex128)
        if _p0_numeric_sha(high_matrix) != _p0_numeric_sha(high_repeat):
            raise ValueError("M2 projected high patch is not deterministic")
        _m2_mark(run_dir, "factor_ready", started, factor_bytes=int(factor.factor_bytes))
        slaves = np.asarray(floquet6.mpc.slaves, dtype=np.int64)
        source_vec = action.output_vector.duplicate()

        def exact_action(source: np.ndarray) -> np.ndarray:
            if np.any(source[slaves] != 0.0):
                raise ValueError("M2 B0 source has nonzero identity rows")
            with source_vec.localForm() as local:
                local.set(0.0)
                local.array_w[: source.size] = source
            source_vec.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
            result = action.mult(source_vec)
            return np.array(result.getArray(readonly=True), dtype=np.complex128, copy=True, order="C")

        primal = _h2b_source_arrays(p6_space, cfg, slaves, floquet6.mpc)
        sources = _h2b_residual_source_arrays(primal, exact_action, slaves)
        source_metrics: list[dict[str, Any]] = []
        rhs_values: list[np.ndarray] = []
        correction_values: list[np.ndarray] = []
        action_values: list[np.ndarray] = []
        for label in M2_SOURCE_LABELS:
            first = measure_h2b_m2_source(
                sources[label],
                prepared["patch_rows"],
                carrier,
                factor,
                exact_action,
                patch_matrix=prepared["patch_matrix"],
                high_patch_matrix=high_matrix,
            )
            second = measure_h2b_m2_source(
                sources[label],
                prepared["patch_rows"],
                carrier,
                factor,
                exact_action,
                patch_matrix=prepared["patch_matrix"],
                high_patch_matrix=high_matrix,
            )
            if first["correction_sha256"] != second["correction_sha256"] or first["action_sha256"] != second["action_sha256"]:
                raise ValueError(f"M2 source {label} is nondeterministic")
            rhs_values.append(np.asarray(sources[label], dtype=np.complex128))
            correction_values.append(first.pop("correction"))
            action_values.append(first.pop("action"))
            first.update({
                "label": label,
                "repeat_correction_sha256": second["correction_sha256"],
                "repeat_action_sha256": second["action_sha256"],
            })
            source_metrics.append(first)
        _m2_mark(run_dir, "measurement_ready", started)
        _m2_save_array(run_dir, "m2_injection.npy", injection)
        _m2_save_array(run_dir, "m2_patch.npy", prepared["patch_matrix"])
        _m2_save_array(run_dir, "m2_patch_rows.npy", prepared["patch_rows"])
        _m2_save_array(run_dir, "m2_q_high.npy", carrier.q_high)
        _m2_save_array(run_dir, "m2_factor_values.npy", factor.values)
        _m2_save_array(run_dir, "m2_factor_pivots.npy", factor.pivots)
        _m2_save_array(run_dir, "m2_source_rhs.npy", np.stack(rhs_values))
        _m2_save_array(run_dir, "m2_source_corrections.npy", np.stack(correction_values))
        _m2_save_array(run_dir, "m2_source_actions.npy", np.stack(action_values))
        source_end = _clean_source()
        form_reuse_artifact = _artifact(run_dir, M2_FORM_REUSE_ARTIFACT)
        payload = _attach_evidence({
            "schema": M2_WORKER_SCHEMA,
            "status": "measurement_complete",
            "pass": True,
            "route": "M2",
            "run_dir": str(run_dir),
            "scope": _m2_scope(),
            "identity": _m2_identity(),
            "phase_identity": _m2_phase_identity(),
            "phase": "online",
            "source_at_start": source_start,
            "source_at_end": source_end,
            "form": form_record,
            "measurement": {
                "authority": {
                    "p0_record_sha256": prepared["authority"]["p0"]["record_sha256"],
                    "p0_evidence_sha256": prepared["authority"]["p0"]["evidence_sha256"],
                },
                "topology": {
                    "central_cell_ordinal": central_cell,
                    "central_class_id": 3,
                    "touching_cell_count": 19,
                    "patch_row_count": 882,
                },
                "injection": _plain(carrier.audit),
                "patch": _plain(prepared["patch_audit"]),
                "high_matrix_sha256": _p0_numeric_sha(high_matrix),
                "factor": {
                    "factor_values_sha256": factor.factor_values_sha256,
                    "pivot_sha256": factor.pivot_sha256,
                    "factorization_residual": float(factor.factorization_residual),
                    "solve_residual": float(factor.solve_residual),
                    "factor_bytes": int(factor.factor_bytes),
                    "factor_values_bytes": int(factor.values.nbytes),
                    "pivot_bytes": int(factor.pivots.nbytes),
                    "factor_values_pivots_bytes": int(
                        factor.values.nbytes + factor.pivots.nbytes
                    ),
                    "finite": bool(factor.finite),
                    "deterministic": bool(factor.deterministic),
                },
                "sources": source_metrics,
                "cache": {
                    "before": cache_before,
                    "after": cache_after,
                    "unchanged": cache_before == cache_after,
                    "form_jit_cache_hit": True,
                    "c_source_regeneration": False,
                    "compiler_descendant_pids": [],
                },
                "form_reuse": {
                    "artifact_sha256": form_reuse_artifact.get("sha256"),
                    "checks": form_reuse["checks"] if form_reuse is not None else None,
                    "all_pass": form_reuse["all_pass"] if form_reuse is not None else None,
                },
                "stage_manifest_sha256": _sha256_file(stage_path),
                "materialization": _m2_identity(),
                "raw_array_names": list(_m2_recorded_artifacts(run_dir)),
            },
            "error": None,
            "controlled_stop": None,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        })
        _m2_mark(run_dir, "summary_ready", started)
        _write_json(run_dir / "m2_worker_summary.json", payload)
        return 0
    finally:
        if source_vec is not None:
            source_vec.destroy()
        if action is not None:
            action.destroy()
        if transfer is not None:
            transfer.destroy()


def _run_m2_watchdog(run_dir: Path) -> int:
    run_dir = run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(f"M2 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    source_start = _clean_source()
    started = time.perf_counter()
    executable = os.path.abspath(sys.executable)
    stage: dict[str, Any] | None = None
    online: dict[str, Any] | None = None
    stage_summary: dict[str, Any] | None = None
    error: str | None = None
    try:
        stage = _h2b_monitor_phase(
            run_dir,
            "stage",
            _h2b_worker_command(executable, "jit-worker", run_dir),
            M2_TIMEOUT_SECONDS,
            M2_RSS_LIMIT_BYTES,
        )
        stage["drain"] = _h2b_bounded_process_drain(stage)
        stage["processes_gone"] = bool(_process_gone(stage))
        stage_summary = _read_json(run_dir / "stage_summary.json")
        if not _m2_stage_gate_valid(
            stage,
            stage_summary,
            run_dir,
            bool(stage["processes_gone"]),
        ):
            error = "m2_stage_gate_failed_before_online"
        else:
            online = _h2b_monitor_phase(
                run_dir,
                "m2",
                _m2_worker_command(executable, run_dir),
                M2_TIMEOUT_SECONDS,
                M2_RSS_LIMIT_BYTES,
            )
            online["drain"] = _h2b_bounded_process_drain(online)
            online["processes_gone"] = bool(_process_gone(online))
            if not (
                online.get("return_code") == 0
                and online.get("termination") is None
                and online.get("processes_gone") is True
                and online.get("peak_rss_bytes", M2_RSS_LIMIT_BYTES) < M2_RSS_LIMIT_BYTES
                and online.get("swap_bytes") == M2_SWAP_LIMIT_BYTES
                and _artifact(run_dir, "m2_worker_summary.json").get("present") is True
                and _m2_timeline_resource_valid(
                    run_dir / "m2_timeline.jsonl",
                    online,
                    "m2",
                    require_no_compiler=True,
                )
            ):
                error = "m2_online_resource_or_worker_gate_failed"
    except _h2b_worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_end = _clean_source()
    worker_ref = _artifact(run_dir, "m2_worker_summary.json")
    passed = bool(
        error is None
        and stage is not None
        and online is not None
        and stage.get("return_code") == 0
        and online.get("return_code") == 0
    )
    payload = _attach_evidence({
        "schema": M2_WATCHDOG_SCHEMA,
        "status": "pass" if passed else "gate_failed",
        "pass": passed,
        "route": "M2" if passed else "M2-review-only",
        "run_dir": str(run_dir),
        "scope": _m2_scope(),
        "identity": _m2_identity(),
        "phase_identity": {
            "lifecycle": "isolated_jit_stage_then_warm_online",
            "stage": _h2b_phase_identity(jit_api=True, compile_called=True, compiler_probe=True),
            "online": _m2_phase_identity(),
        },
        "source_at_start": source_start,
        "source_at_end": source_end,
        "command_identity": {
            "python": executable,
            "launch_mode": "direct_singleton_stage_then_mpi1_online",
            "stage_command": _h2b_worker_command(executable, "jit-worker", run_dir),
            "m2_command": _m2_worker_command(executable, run_dir),
        },
        "stage": stage,
        "online": online,
        "stage_summary": _artifact(run_dir, "stage_summary.json"),
        "worker_summary": worker_ref,
        "raw_artifacts": _m2_recorded_artifacts(run_dir),
        "error": error,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    })
    _write_json(run_dir / "m2_watchdog_summary.json", payload)
    print(f"M2 watchdog status={payload['status']} run_dir={run_dir}", flush=True)
    return 0 if error is None else 1


def _m2_source_gate_valid(result: Mapping[str, Any], rho_limit: float) -> bool:
    return bool(
        result.get("finite") is True
        and result.get("rho_scope") == "complete_882_patch_rows"
        and result.get("global_rho_scope") == "full_global_rows_diagnostic_only"
        and all(
            type(result.get(key)) in (int, float)
            and math.isfinite(float(result[key]))
            for key in (
                "projected_high_closure_relative",
                "action_closure_relative",
                "full_space_rho_star",
                "full_space_rho_unit",
            )
        )
        and result["action_closure_relative"] <= M2_ACTION_CLOSURE_LIMIT
        and result["full_space_rho_star"] <= rho_limit
    )


def _m2_check_raw(run_dir: Path, checker_source: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    from src.solvers.hcurl_h2b_block_smoother import factorize_h2b_p0_patch
    from src.solvers.hcurl_h2b_m2_complement import (
        _array_sha256,
        build_h2b_m2_complement,
        measure_h2b_m2_source,
    )

    checks: dict[str, bool] = {}
    problems: list[str] = []
    try:
        watchdog = _read_json(run_dir / "m2_watchdog_summary.json")
        stage = _read_json(run_dir / "stage_summary.json")
        worker = _read_json(run_dir / "m2_worker_summary.json")
        form_reuse = _read_json(run_dir / M2_FORM_REUSE_ARTIFACT)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "schema": M2_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "route": "M2-review-only",
            "checks": {"raw_readable": False},
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
            "measurements": None,
            "checker_source": _plain(checker_source),
        }
    checks["watchdog_schema"] = bool(
        watchdog.get("schema") == M2_WATCHDOG_SCHEMA
        and watchdog.get("status") == "pass"
        and watchdog.get("pass") is True
        and _evidence_valid(watchdog)
    )
    checks["source_authority"] = bool(
        _source_pair_valid(watchdog.get("source_at_start"), watchdog.get("source_at_end"))
        and _source_pair_valid(stage.get("source_at_start"), stage.get("source_at_end"))
        and watchdog.get("source_at_start") == worker.get("source_at_start")
        and watchdog.get("source_at_start") == stage.get("source_at_start")
        and _source_pair_valid(worker.get("source_at_start"), worker.get("source_at_end"))
        and _source_valid(checker_source)
        and checker_source == watchdog.get("source_at_start")
    )
    checks["scope_identity"] = watchdog.get("scope") == _m2_scope() and worker.get("scope") == _m2_scope()
    checks["identity"] = watchdog.get("identity") == _m2_identity() and worker.get("identity") == _m2_identity()
    stage_process = watchdog.get("stage")
    online_process = watchdog.get("online")
    checks["command_identity"] = bool(
        isinstance(watchdog.get("command_identity"), Mapping)
        and watchdog["command_identity"].get("launch_mode")
        == "direct_singleton_stage_then_mpi1_online"
        and watchdog["command_identity"].get("python")
        == stage.get("runtime_identity", {}).get("sys_executable")
        and watchdog["command_identity"].get("stage_command")
        == _h2b_worker_command(
            watchdog["command_identity"].get("python"), "jit-worker", run_dir
        )
        and watchdog["command_identity"].get("m2_command")
        == _m2_worker_command(
            watchdog["command_identity"].get("python"), run_dir
        )
    ) if isinstance(watchdog.get("command_identity"), Mapping) and isinstance(
        watchdog["command_identity"].get("python"), str
    ) else False
    checks["stage_resource"] = bool(
        _m2_stage_gate_valid(
            stage_process,
            stage,
            run_dir,
            isinstance(stage_process, Mapping)
            and stage_process.get("processes_gone") is True,
        )
    )
    checks["online_resource"] = bool(
        isinstance(online_process, Mapping)
        and type(online_process.get("return_code")) is int
        and online_process.get("return_code") == 0
        and online_process.get("termination") is None
        and online_process.get("processes_gone") is True
        and type(online_process.get("peak_rss_bytes")) is int
        and online_process["peak_rss_bytes"] < M2_RSS_LIMIT_BYTES
        and online_process.get("swap_bytes") == M2_SWAP_LIMIT_BYTES
        and _m2_timeline_resource_valid(
            run_dir / "m2_timeline.jsonl",
            online_process,
            "m2",
            require_no_compiler=True,
        )
    )
    checks["stage_online_lifecycle"] = bool(
        isinstance(stage_process, Mapping)
        and isinstance(online_process, Mapping)
        and stage_process.get("processes_gone") is True
        and watchdog.get("phase_identity") == {
            "lifecycle": "isolated_jit_stage_then_warm_online",
            "stage": _h2b_phase_identity(jit_api=True, compile_called=True, compiler_probe=True),
            "online": _m2_phase_identity(),
        }
    )
    if not checks["stage_resource"]:
        problems.append("stage_resource")
    if not checks["online_resource"]:
        problems.append("online_resource")
    checks["worker_schema"] = bool(
        worker.get("schema") == M2_WORKER_SCHEMA
        and worker.get("phase") == "online"
        and worker.get("status") == "measurement_complete"
        and worker.get("error") is None
        and worker.get("controlled_stop") is None
        and worker.get("phase_identity") == _m2_phase_identity()
        and _evidence_valid(worker)
    )
    measurement = worker.get("measurement")
    checks["form_identity"] = bool(
        _m2_stage_summary_valid(stage, run_dir)
        and isinstance(stage.get("form"), Mapping)
        and isinstance(worker.get("form"), Mapping)
        and _h2b_forms_match(stage["form"], worker["form"], run_dir)
    )
    checks["online_cache"] = _m2_online_cache_valid(
        measurement,
        worker.get("form"),
        stage.get("form"),
        run_dir,
    )
    expected_form_reuse = {
        "code_state_hit": (
            isinstance(worker.get("form"), Mapping)
            and worker["form"].get("code_state") == "hit_no_new_decl_impl"
        ),
        "cache_unchanged": (
            isinstance(measurement, Mapping)
            and isinstance(measurement.get("cache"), Mapping)
            and measurement["cache"].get("before") == measurement["cache"].get("after")
        ),
        "forms_match": (
            isinstance(stage.get("form"), Mapping)
            and isinstance(form_reuse, Mapping)
            and isinstance(form_reuse.get("online_form"), Mapping)
            and _h2b_forms_match(stage["form"], form_reuse["online_form"], run_dir)
        ),
    }
    form_artifact = _artifact(run_dir, M2_FORM_REUSE_ARTIFACT)
    sidecar_cache = form_reuse.get("cache") if isinstance(form_reuse, Mapping) else None
    worker_cache = measurement.get("cache") if isinstance(measurement, Mapping) else None
    worker_binding = measurement.get("form_reuse") if isinstance(measurement, Mapping) else None
    raw_artifacts = watchdog.get("raw_artifacts")
    checks["form_reuse"] = bool(
        isinstance(form_reuse, Mapping)
        and form_reuse.get("schema") == M2_FORM_REUSE_SCHEMA
        and form_reuse.get("phase") == "online"
        and _evidence_valid(form_reuse)
        and _source_valid(form_reuse.get("source"))
        and form_reuse.get("source") == worker.get("source_at_start")
        and form_reuse.get("source") == worker.get("source_at_end")
        and form_reuse.get("stage_manifest_sha256") == _sha256_file(run_dir / "stage_summary.json")
        and form_reuse.get("stage_manifest_sha256") == measurement.get("stage_manifest_sha256")
        if isinstance(measurement, Mapping)
        else False
    )
    checks["form_reuse"] = bool(
        checks["form_reuse"]
        and form_reuse.get("online_form") == worker.get("form")
        and isinstance(sidecar_cache, Mapping)
        and isinstance(worker_cache, Mapping)
        and sidecar_cache.get("before") == worker_cache.get("before")
        and sidecar_cache.get("after") == worker_cache.get("after")
        and form_reuse.get("checks") == expected_form_reuse
        and form_reuse.get("all_pass") is True
        and isinstance(worker_binding, Mapping)
        and worker_binding.get("artifact_sha256") == form_artifact.get("sha256")
        and worker_binding.get("checks") == expected_form_reuse
        and worker_binding.get("all_pass") is True
        and form_artifact.get("present") is True
        and isinstance(form_artifact.get("sha256"), str)
        and isinstance(raw_artifacts, Mapping)
        and raw_artifacts.get(M2_FORM_REUSE_ARTIFACT) == form_artifact
        and all(value is True for value in expected_form_reuse.values())
    )
    if not checks["form_identity"]:
        problems.append("form_identity")
    if not checks["online_cache"]:
        problems.append("online_cache")
    if not checks["form_reuse"]:
        problems.append("form_reuse")
    current_authority = None
    try:
        current_authority = _h2b_p1_authority()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        problems.append(f"p0_authority:{type(exc).__name__}")
    current_p0 = (
        current_authority.get("p0")
        if isinstance(current_authority, Mapping)
        else None
    )
    topology = measurement.get("topology") if isinstance(measurement, Mapping) else None
    measurement_authority = (
        measurement.get("authority") if isinstance(measurement, Mapping) else None
    )
    patch_audit = measurement.get("patch") if isinstance(measurement, Mapping) else None
    checks["authority_topology"] = bool(
        isinstance(current_p0, Mapping)
        and isinstance(measurement_authority, Mapping)
        and measurement_authority.get("p0_record_sha256") == current_p0.get("record_sha256")
        and measurement_authority.get("p0_evidence_sha256") == current_p0.get("evidence_sha256")
        and topology == {
            "central_cell_ordinal": 3,
            "central_class_id": 3,
            "touching_cell_count": 19,
            "patch_row_count": 882,
        }
        and isinstance(patch_audit, Mapping)
        and patch_audit.get("patch_definition") == "restricted-global row-complete B_P"
        and patch_audit.get("central_cell_ordinal") == 3
        and patch_audit.get("central_class_id") == 3
        and patch_audit.get("patch_row_count") == 882
        and patch_audit.get("p0_authority_record_sha256") == current_p0.get("record_sha256")
        and patch_audit.get("p0_authority_evidence_sha256") == current_p0.get("evidence_sha256")
    )
    if not checks["authority_topology"]:
        problems.append("authority_topology_gate")
    patch_rows = np.empty(0, dtype=np.int64)
    injection = np.empty((0, 0), dtype=np.complex128)
    patch = np.empty((0, 0), dtype=np.complex128)
    q_high_raw = np.empty((0, 0), dtype=np.complex128)
    factor_values_raw = np.empty((0, 0), dtype=np.complex128)
    pivots_raw = np.empty(0, dtype=np.int32)
    rhs = np.empty((0, 0), dtype=np.complex128)
    corrections = np.empty((0, 0), dtype=np.complex128)
    actions = np.empty((0, 0), dtype=np.complex128)
    try:
        injection = np.load(run_dir / "m2_injection.npy", allow_pickle=False)
        patch = np.load(run_dir / "m2_patch.npy", allow_pickle=False)
        patch_rows = np.load(run_dir / "m2_patch_rows.npy", allow_pickle=False)
        q_high_raw = np.load(run_dir / "m2_q_high.npy", allow_pickle=False)
        factor_values_raw = np.load(run_dir / "m2_factor_values.npy", allow_pickle=False)
        pivots_raw = np.load(run_dir / "m2_factor_pivots.npy", allow_pickle=False)
        rhs = np.load(run_dir / "m2_source_rhs.npy", allow_pickle=False)
        corrections = np.load(run_dir / "m2_source_corrections.npy", allow_pickle=False)
        actions = np.load(run_dir / "m2_source_actions.npy", allow_pickle=False)
        carrier = build_h2b_m2_complement(injection)
        q_high_equal = np.array_equal(carrier.q_high, q_high_raw)
        high_matrix = np.ascontiguousarray(carrier.q_high.conj().T @ patch @ carrier.q_high, dtype=np.complex128)
        factor = factorize_h2b_p0_patch(high_matrix, task037_extra_h2b=True)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        q_high_equal = False
        carrier = None
        factor = None
        high_matrix = None
        problems.append(f"numeric_recompute:{type(exc).__name__}")
    checks["complement"] = bool(
        carrier is not None
        and q_high_equal
        and patch_rows.dtype == np.dtype(np.int64)
        and patch_rows.shape == (882,)
        and np.unique(patch_rows).size == patch_rows.size
        and carrier.audit["rank"] == 300
        and carrier.audit["q_high_dimension"] == 582
        and carrier.audit["q_orthogonality_error"] <= M2_Q_ORTHOGONALITY_LIMIT
        and carrier.audit["split_reconstruction_error"] <= M2_SPLIT_RECONSTRUCTION_LIMIT
        and carrier.audit["retained_transform_bytes"] <= M2_TRANSFORM_BYTES_LIMIT
        and carrier.audit["dense_qh_retained"] is True
        and carrier.audit["dense_qh_count"] == 1
    )
    if not checks["complement"]:
        problems.append("complement_gate")
    factor_measurement = (
        measurement.get("factor")
        if isinstance(measurement, Mapping)
        and isinstance(measurement.get("factor"), Mapping)
        else None
    )
    factor_arrays_match = bool(
        factor is not None
        and factor_values_raw.dtype == factor.values.dtype
        and factor_values_raw.shape == factor.values.shape
        and pivots_raw.dtype == factor.pivots.dtype
        and pivots_raw.shape == factor.pivots.shape
        and np.array_equal(factor_values_raw, factor.values)
        and np.array_equal(pivots_raw, factor.pivots)
    )
    checks["factor"] = bool(
        factor is not None
        and factor_arrays_match
        and factor.factor_bytes <= M2_FACTOR_BYTES_LIMIT
        and factor.factorization_residual <= M2_FACTOR_RESIDUAL_LIMIT
        and factor.solve_residual <= M2_FACTOR_RESIDUAL_LIMIT
        and factor.finite is True
        and factor.deterministic is True
        and isinstance(factor_measurement, Mapping)
        and factor_measurement.get("factor_values_sha256") == factor.factor_values_sha256
        and factor_measurement.get("pivot_sha256") == factor.pivot_sha256
        and factor_measurement.get("factorization_residual") == factor.factorization_residual
        and factor_measurement.get("solve_residual") == factor.solve_residual
        and factor_measurement.get("factor_bytes") == factor.factor_bytes
        and factor_measurement.get("factor_values_bytes") == factor.values.nbytes
        and factor_measurement.get("pivot_bytes") == factor.pivots.nbytes
        and factor_measurement.get("factor_values_pivots_bytes") == factor.factor_bytes
    )
    if not checks["factor"]:
        problems.append("factor_gate")
    source_results: list[dict[str, Any]] = []
    worker_sources = measurement.get("sources") if isinstance(measurement, Mapping) else None
    source_binding_ok = isinstance(worker_sources, list) and len(worker_sources) == len(M2_SOURCE_LABELS)
    if (
        carrier is not None
        and factor is not None
        and patch_rows.shape == (882,)
        and rhs.shape == (len(M2_SOURCE_LABELS), 173802)
        and corrections.shape == rhs.shape
        and actions.shape == rhs.shape
    ):
        for index, label in enumerate(M2_SOURCE_LABELS):
            result = measure_h2b_m2_source(
                rhs[index],
                patch_rows,
                carrier,
                factor,
                lambda _values, expected=actions[index]: expected,
                patch_matrix=patch,
                high_patch_matrix=high_matrix,
            )
            result["label"] = label
            if result["correction_sha256"] != _array_sha256(corrections[index]):
                problems.append(f"source_correction_sha:{label}")
            if result["action_sha256"] != _array_sha256(actions[index]):
                problems.append(f"source_action_sha:{label}")
            worker_item = (
                worker_sources[index]
                if isinstance(worker_sources, list) and index < len(worker_sources)
                else None
            )
            if not (
                isinstance(worker_item, Mapping)
                and worker_item.get("label") == label
                and worker_item.get("correction_sha256") == result["correction_sha256"]
                and worker_item.get("action_sha256") == result["action_sha256"]
                and worker_item.get("repeat_correction_sha256") == result["correction_sha256"]
                and worker_item.get("repeat_action_sha256") == result["action_sha256"]
            ):
                source_binding_ok = False
                problems.append(f"source_worker_binding:{label}")
            result["repeat_correction_sha256"] = result["correction_sha256"]
            result["repeat_action_sha256"] = result["action_sha256"]
            result.pop("correction")
            result.pop("action")
            source_results.append(result)
    checks["sources"] = bool(
        len(source_results) == len(M2_SOURCE_LABELS)
        and all(
            _m2_source_gate_valid(
                result,
                M2_CHECKERBOARD_RHO_LIMIT
                if result["label"] == "checkerboard/high-frequency"
                else M2_MIXED_RHO_LIMIT
                if result["label"] == "mixed"
                else M2_OTHER_RHO_LIMIT,
            )
            for result in source_results
        )
    )
    if not checks["sources"]:
        problems.append("source_gate")
    checks["source_binding"] = source_binding_ok
    if not checks["source_binding"]:
        problems.append("source_binding_gate")
    checks["materialization"] = bool(
        worker.get("identity") == _m2_identity()
        and isinstance(worker.get("measurement"), Mapping)
        and worker["measurement"].get("materialization") == _m2_identity()
    )
    checks["raw_artifacts"] = watchdog.get("raw_artifacts") == _m2_recorded_artifacts(run_dir)
    passed = bool(all(checks.values()) and not problems)
    return {
        "schema": M2_CHECK_SCHEMA,
        "status": "pass" if passed else "gate_failed",
        "pass": passed,
        "route": "M2" if passed else "M2-review-only",
        "checks": checks,
        "problems": list(dict.fromkeys(problems)),
        "measurements": {
            "topology": _plain(topology),
            "authority": _plain(measurement_authority),
            "patch": _plain(measurement.get("patch")) if isinstance(measurement, Mapping) else None,
            "carrier": _plain(carrier.audit) if carrier is not None else None,
            "factor": {
                "factorization_residual": float(factor.factorization_residual),
                "solve_residual": float(factor.solve_residual),
                "factor_bytes": int(factor.factor_bytes),
                "factor_values_bytes": int(factor.values.nbytes),
                "pivot_bytes": int(factor.pivots.nbytes),
                "factor_values_pivots_bytes": int(factor.factor_bytes),
            } if factor is not None else None,
            "source_count": len(source_results),
            "sources": _plain(source_results),
            "stage_resource": _plain(stage_process),
            "online_resource": _plain(online_process),
            "resource_peak_rss_bytes": max(
                int(stage_process["peak_rss_bytes"]),
                int(online_process["peak_rss_bytes"]),
            ) if isinstance(stage_process, Mapping) and isinstance(online_process, Mapping) else None,
        },
        "checker_source": _plain(checker_source),
        "raw_artifacts": _plain(watchdog.get("raw_artifacts")),
    }


def _run_m2_check(run_dir: Path, output: Path) -> int:
    checker_source = _clean_source()
    result = _m2_check_raw(run_dir.resolve(), checker_source)
    _write_json(output.resolve(), _attach_evidence(result))
    print(f"M2 check status={result['status']} output={output.resolve()}", flush=True)
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
    m2_worker = sub.add_parser("m2-worker")
    m2_worker.add_argument("--run-dir", required=True)
    m2_watchdog = sub.add_parser("m2-watchdog")
    m2_watchdog.add_argument("--run-dir", required=True)
    m2_checker = sub.add_parser("m2-check")
    m2_checker.add_argument("--run-dir", required=True)
    m2_checker.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "m1-worker":
        return _run_m1_worker(Path(args.run_dir), args.phase, args.expected_mpi_size)
    if args.command == "m1-watchdog":
        return _run_m1_watchdog(Path(args.run_dir))
    if args.command == "m1-check":
        return _run_m1_check(Path(args.run_dir), Path(args.output))
    if args.command == "m2-worker":
        return _run_m2_worker(Path(args.run_dir))
    if args.command == "m2-watchdog":
        return _run_m2_watchdog(Path(args.run_dir))
    return _run_m2_check(Path(args.run_dir), Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
