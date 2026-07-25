"""Formal Task035b direct setup and resource profiler.

This is a thin, research-only wrapper around the existing fixed rectangular
Stage-4 solver.  The default action is a dry-run plan.  A PDE is started only
with ``--execute-pde`` and only from a clean full-SHA checkout on the reviewed
Task035b branch.

Cold and warm profiles deliberately share SHA-bound raw-tensor and
oriented-condensed-class caches:

* ``--cache-state cold`` requires a cache directory that does not yet exist
  and uses the core ``read_write`` mode;
* ``--cache-state warm`` requires that exact directory to contain complete
  cache pairs and uses the core ``read_only`` mode.

The runner does not duplicate any numerical kernel.  It only selects explicit
opt-ins, launches the common solver under the existing watchdog sampler, and
extracts a compact timing/resource record without overwriting prior evidence.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
from typing import Any

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
    _stage_peaks,
)
from benchmarks.task034_wsl_resources import effective_memory_limit


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
DEFAULT_ARTIFACT_ROOT = (
    ROOT / "benchmarks" / "artifacts" / "task035b" / "direct_setup_profile"
)
EXPECTED_H15_TOPOLOGY = {
    "mesh_cells_resolved": [6, 2, 10],
    "num_mesh_cells": 120,
    "full3d_equivalent_dofs": 74890,
    "active_rows_with_dtn": 16880,
}
CACHE_MODES = {"cold": "read_write", "warm": "read_only"}
DTN_REDUCED_MODAL_CACHE_SCHEMA = (
    "task035b.dtn-reduced-modal-persistent-cache.v2"
)


def _json_default(value: Any) -> Any:
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"cannot resolve Git provenance: git {' '.join(arguments)}"
        ) from exc


def _path_from_root(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _exclusive_path(path: Path) -> Path:
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    if resolved.exists():
        raise SystemExit(
            "output already exists; historical evidence will not be "
            f"overwritten: {resolved}"
        )
    return resolved


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task035b opt-in direct setup/resource profiler. The default "
            "action prints a non-PDE cold/warm execution plan."
        )
    )
    parser.add_argument(
        "--execute-pde",
        action="store_true",
        help="explicitly authorize one reviewed h15 direct PDE profile",
    )
    parser.add_argument(
        "--mpi-size",
        type=int,
        choices=(1, 2, 4, 8),
        default=8,
        help="Review-V2 h15 resource-comparison rank count",
    )
    parser.add_argument(
        "--cache-state",
        choices=tuple(CACHE_MODES),
        default="cold",
        help="cold creates a new cache; warm reuses it read-only",
    )
    parser.add_argument(
        "--cache-directory",
        type=Path,
        help=(
            "shared cold/warm raw-tensor cache; the default is SHA-bound "
            "under the artifact root"
        ),
    )
    parser.add_argument("--h-nm", type=float, default=15.0)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
    )
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--warning-gib", type=float, default=8.0)
    parser.add_argument("--terminate-gib", type=float, default=48.0)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source-sha", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if abs(float(args.h_nm) - 15.0) > 1.0e-12:
        parser.error(
            "Review V2 authorizes this direct rank-study runner only for h15"
        )
    if args.warning_gib <= 0.0:
        parser.error("--warning-gib must be positive")
    if args.terminate_gib <= args.warning_gib:
        parser.error("--terminate-gib must exceed --warning-gib")
    if args.timeout_seconds <= 0.0 or args.poll_interval <= 0.0:
        parser.error("timeout and poll interval must be positive")
    if args.worker and (
        not args.execute_pde
        or args.run_dir is None
        or args.cache_directory is None
        or args.source_sha is None
    ):
        parser.error(
            "--worker requires --execute-pde, --run-dir, "
            "--cache-directory, and --source-sha"
        )
    if not args.worker and not args.execute_pde and args.record is not None:
        parser.error(
            "the default plan is stdout-only; --record requires --execute-pde"
        )
    return args


def _dry_run_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "task035b.direct-setup-profile-plan.v1",
        "status": "not_run_requires_explicit_execute_pde",
        "pde_started": False,
        "ordinary_default_changed": False,
        "geometry": "Task034 fixed rectangular block grating",
        "space": "fixed p5 trace plus p6 cell interior",
        "h_nm": 15.0,
        "mpi_size": int(args.mpi_size),
        "cache_state": args.cache_state,
        "cache_core_mode": CACHE_MODES[args.cache_state],
        "cache_directory": (
            None
            if args.cache_directory is None
            else str(args.cache_directory)
        ),
        "explicit_opt_ins": {
            "assembly_time_cell_static_condensation": True,
            "floquet_slave_elimination": True,
            "fast_fixed_trace_setup": True,
            "affine_isotropic_reference_tensor": True,
            "persistent_sha_bound_raw_tensor_cache": True,
            "persistent_sha_bound_condensed_class_cache": True,
            "persistent_sha_mesh_mode_trace_bound_dtn_surface_cache": (
                True
            ),
            "direct_mumps": True,
            "solver_release_before_postprocess": True,
        },
        "rank_study": [1, 2, 4, 8],
        "cold_warm_protocol": [
            "commit all source changes and start from a clean full SHA",
            "run cold once against a cache directory that does not exist",
            "run warm against that same cache directory in read-only mode",
            "do not run more than one heavy case at a time",
        ],
        "next_action": (
            "rerun with --execute-pde after committing all source changes"
        ),
    }


def _validate_source_snapshot(
    *,
    commit_sha: str,
    branch: str,
    porcelain_status: str,
) -> dict[str, Any]:
    sha = commit_sha.strip().lower()
    if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise SystemExit("formal direct profile requires a full Git SHA")
    if branch != EXPECTED_BRANCH:
        raise SystemExit(
            f"formal direct profile requires {EXPECTED_BRANCH}; got {branch}"
        )
    if porcelain_status.strip():
        raise SystemExit(
            "formal direct profile requires a clean worktree; commit all "
            "tracked and nonignored untracked source before execution"
        )
    return {
        "commit_sha": sha,
        "branch": branch,
        "status_before": "",
        "clean_full_sha_gate": True,
    }


def _source_preflight() -> dict[str, Any]:
    return _validate_source_snapshot(
        commit_sha=_git("rev-parse", "HEAD"),
        branch=_git("branch", "--show-current"),
        porcelain_status=_git(
            "status", "--porcelain", "--untracked-files=all"
        ),
    )


def _environment_preflight() -> dict[str, Any]:
    from mpi4py import MPI
    import numpy as np
    from petsc4py import PETSc

    executable = Path(sys.executable).absolute()
    expected = (ROOT / ".venv" / "bin" / "python").absolute()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected,
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": PETSc.ScalarType == np.complex128,
        "int32_petsc": PETSc.IntType == np.int32,
        "same_shell_mpi_available": MPI.Get_library_version() != "",
        "temporary_directory_not_windows_mount": not any(
            str(os.environ.get(name, "")).startswith("/mnt/")
            for name in ("TMPDIR", "TMP", "TEMP")
        ),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "python_executable": str(executable),
        "python_executable_realpath": str(executable.resolve()),
        "python_version": sys.version.split()[0],
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_library": MPI.Get_library_version().strip(),
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "temporary_directory_environment": {
            name: os.environ.get(name) for name in ("TMPDIR", "TMP", "TEMP")
        },
    }


def _direct_config(
    *,
    source_sha: str,
    cache_directory: Path,
    cache_state: str,
    h_nm: float,
):
    """Select only Review-V2 direct setup opt-ins; the common solver owns PDE."""

    from src.common.config_3d import target_stage4_config

    if cache_state not in CACHE_MODES:
        raise ValueError(f"unsupported cache state: {cache_state}")
    base = target_stage4_config(degree=6, h_nm=float(h_nm))
    return replace(
        base,
        case_name=(
            f"task035b_direct_setup_fixed_p5trace_p6interior_"
            f"h{h_nm:g}_{cache_state}"
        ).replace(".", "p"),
        incident_theta_deg=80.0,
        incident_phi_deg=0.0,
        polarization_kind="s",
        custom_polarization=None,
        mesh_cell_type="hexahedron",
        nedelec_trace_degree=5,
        nedelec_interior_degree=6,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=False,
        direct_release_base_after_augmentation=True,
        direct_release_solver_before_postprocess=True,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
        stage4_condensed_iterative_profile=None,
        stage4_retain_dual_recovery_context=False,
        stage4_fast_fixed_trace_setup=True,
        stage4_affine_isotropic_reference_tensor=True,
        stage4_condensed_bulk_cell_insertion=False,
        stage4_condensed_cache_directory=str(cache_directory.resolve()),
        stage4_condensed_cache_source_sha=source_sha,
        stage4_condensed_cache_mode=CACHE_MODES[cache_state],
        stage4_condensed_persistent_dtn_surface_cache=True,
        petsc_direct_solver_profile="default",
        petsc_extra_options={
            "pc_factor_mat_solver_type": "mumps",
            "mat_mumps_icntl_14": 100,
        },
        unique_output=False,
    )


def _worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    failures: list[dict[str, Any]] = []
    local_failure: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    local_import_seconds = 0.0
    local_config_seconds = 0.0
    local_solver_seconds = 0.0
    try:
        if int(comm.size) != int(args.mpi_size):
            raise RuntimeError(
                f"worker MPI size {comm.size} differs from {args.mpi_size}"
            )
        import_started = time.perf_counter()
        from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
            run_stage4b_block_grating_3d_case,
        )

        local_import_seconds = time.perf_counter() - import_started
        config_started = time.perf_counter()
        cfg = _direct_config(
            source_sha=args.source_sha,
            cache_directory=args.cache_directory,
            cache_state=args.cache_state,
            h_nm=float(args.h_nm),
        )
        local_config_seconds = time.perf_counter() - config_started
        solver_started = time.perf_counter()
        summary = run_stage4b_block_grating_3d_case(
            cfg,
            args.run_dir / "solve",
        )
        local_solver_seconds = time.perf_counter() - solver_started
    except Exception as exc:  # preserve rank-local solver failures
        local_failure = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    failures = [
        failure
        for failure in comm.allgather(local_failure)
        if failure is not None
    ]
    timing_max = {
        "solver_module_import_seconds": float(
            comm.allreduce(local_import_seconds, op=MPI.MAX)
        ),
        "research_config_build_seconds": float(
            comm.allreduce(local_config_seconds, op=MPI.MAX)
        ),
        "common_solver_call_seconds": float(
            comm.allreduce(local_solver_seconds, op=MPI.MAX)
        ),
    }
    if comm.rank == 0:
        payload = {
            "schema_version": "task035b.direct-setup-profile-worker.v1",
            "status": (
                "worker_completed_with_summary"
                if not failures
                else "worker_exception_preserved"
            ),
            "cache_state": args.cache_state,
            "mpi_size": int(comm.size),
            "source_sha": args.source_sha,
            "worker_timings_seconds": timing_max,
            "summary": summary,
            "rank_failures": failures,
        }
        with (args.run_dir / "worker_result.json").open(
            "x",
            encoding="utf-8",
        ) as stream:
            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    default=_json_default,
                )
                + "\n"
            )
    comm.barrier()
    return 0 if not failures else 3


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=15)


def _numeric_max(
    rows: list[dict[str, Any]],
    field: str,
) -> float | None:
    values = [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), (int, float))
        and not isinstance(row.get(field), bool)
    ]
    return max(values) if values else None


def _telemetry_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed_ranks: set[int] = set()
    per_rank: dict[int, dict[str, float]] = {}
    per_rank_thread_runtime: dict[int, dict[str, Any]] = {}
    smaps_readable_counts: list[int] = []
    for row in rows:
        if isinstance(
            row.get("worker_rank_smaps_readable_count"),
            (int, float),
        ):
            smaps_readable_counts.append(
                int(row["worker_rank_smaps_readable_count"])
            )
        for json_field in (
            "worker_rank_rss_mb_json",
            "worker_rank_smaps_rollup_json",
        ):
            try:
                rank_rows = json.loads(str(row.get(json_field, "[]")))
            except json.JSONDecodeError:
                rank_rows = []
            if not isinstance(rank_rows, list):
                continue
            for entry in rank_rows:
                if not isinstance(entry, dict) or not isinstance(
                    entry.get("rank"),
                    int,
                ):
                    continue
                rank = int(entry["rank"])
                observed_ranks.add(rank)
                if json_field != "worker_rank_smaps_rollup_json":
                    continue
                peaks = per_rank.setdefault(rank, {})
                for field in (
                    "rss_mb",
                    "pss_mb",
                    "uss_mb",
                    "shared_mb",
                    "anonymous_mb",
                    "swap_mb",
                    "swap_pss_mb",
                ):
                    value = entry.get(field)
                    if isinstance(value, (int, float)) and not isinstance(
                        value,
                        bool,
                    ):
                        peaks[field] = max(
                            peaks.get(field, 0.0),
                            float(value),
                        )
        try:
            runtime_rows = json.loads(
                str(row.get("worker_rank_thread_runtime_json", "[]"))
            )
        except json.JSONDecodeError:
            runtime_rows = []
        if isinstance(runtime_rows, list):
            for entry in runtime_rows:
                if not isinstance(entry, dict) or not isinstance(
                    entry.get("rank"),
                    int,
                ):
                    continue
                rank = int(entry["rank"])
                previous = per_rank_thread_runtime.get(rank)
                if previous is None or int(
                    entry.get("thread_count_observed", 0)
                ) > int(previous.get("thread_count_observed", 0)):
                    per_rank_thread_runtime[rank] = entry
    process_tree_rss = _numeric_max(rows, "mpi_process_tree_rss_mb")
    return {
        "sample_count": len(rows),
        "observed_worker_ranks": sorted(observed_ranks),
        "observed_worker_rank_count": len(observed_ranks),
        "max_process_tree_rss_mb": process_tree_rss,
        "max_process_tree_rss_gib": (
            None if process_tree_rss is None else process_tree_rss / 1024.0
        ),
        "max_process_tree_swap_mb": _numeric_max(
            rows,
            "mpi_process_tree_swap_mb",
        ),
        "max_worker_rank_rss_sum_mb": _numeric_max(
            rows,
            "worker_rank_rss_sum_mb",
        ),
        "max_worker_rank_pss_sum_mb": _numeric_max(
            rows,
            "worker_rank_pss_sum_mb",
        ),
        "max_worker_rank_uss_sum_mb": _numeric_max(
            rows,
            "worker_rank_uss_sum_mb",
        ),
        "max_worker_rank_shared_sum_mb": _numeric_max(
            rows,
            "worker_rank_shared_sum_mb",
        ),
        "max_worker_rank_smaps_swap_sum_mb": _numeric_max(
            rows,
            "worker_rank_smaps_swap_sum_mb",
        ),
        "max_worker_rank_thread_count_sum": _numeric_max(
            rows,
            "worker_rank_thread_count_sum",
        ),
        "max_mpi_process_tree_thread_count": _numeric_max(
            rows,
            "mpi_process_tree_thread_count",
        ),
        "max_container_cgroup_current_mb": _numeric_max(
            rows,
            "container_cgroup_current_mb",
        ),
        "max_container_cgroup_peak_mb": _numeric_max(
            rows,
            "container_cgroup_peak_mb",
        ),
        "max_container_swap_current_mb": _numeric_max(
            rows,
            "container_swap_current_mb",
        ),
        "per_rank_smaps_rollup_peaks_mb": {
            str(rank): fields for rank, fields in sorted(per_rank.items())
        },
        "per_rank_peak_thread_runtime": {
            str(rank): entry
            for rank, entry in sorted(per_rank_thread_runtime.items())
        },
        "smaps_rollup_all_expected_ranks_readable_at_least_once": (
            bool(smaps_readable_counts)
            and max(smaps_readable_counts) == len(observed_ranks)
        ),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _number(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ):
        return float(value)
    return None


def _sum_available(*values: float | None) -> float | None:
    available = [float(value) for value in values if value is not None]
    return sum(available) if available else None


def _full_true_residual(summary: dict[str, Any]) -> float | None:
    cell = summary.get("cell_static_condensation") or {}
    residual = cell.get("full_explicit_true_residual")
    if isinstance(residual, dict):
        residual = residual.get("linear_system_relative_residual")
    if isinstance(residual, (int, float)) and not isinstance(residual, bool):
        return float(residual)
    fallback = summary.get("linear_system_relative_residual")
    if isinstance(fallback, (int, float)) and not isinstance(
        fallback,
        bool,
    ):
        return float(fallback)
    return None


def _extract_setup_evidence(
    worker_result: dict[str, Any],
) -> dict[str, Any]:
    """Extract nonoverlapping outer stages and overlapping granular audits."""

    summary = worker_result.get("summary")
    if not isinstance(summary, dict):
        return {
            "summary_available": False,
            "worker_status": worker_result.get("status"),
            "rank_failures": worker_result.get("rank_failures") or [],
        }
    worker_timings = worker_result.get("worker_timings_seconds") or {}
    outer = summary.get("timings_seconds") or {}
    cell = summary.get("cell_static_condensation") or {}
    raw_cache = cell.get("raw_tensor_persistent_cache") or {}
    condensed_cache = (
        cell.get("persistent_condensed_class_cache") or {}
    )
    dtn_surface_cache = (
        summary.get("stage4_dtn_surface_vector_persistent_cache")
        or {}
    )
    matrix = summary.get("matrix_stats") or {}
    config = summary.get("config") or {}
    factor = summary.get("stage4_dtn_factor_inventory") or {}

    ksp_setup = _number(summary, "stage4_dtn_ksp_setup_seconds")
    ksp_solve = _number(summary, "stage4_dtn_ksp_solve_seconds")
    dtn_outer = _number(outer, "stage4_dtn_port_assembly_and_solve")
    dtn_non_ksp = (
        None
        if dtn_outer is None or ksp_setup is None or ksp_solve is None
        else max(0.0, dtn_outer - ksp_setup - ksp_solve)
    )
    postprocess_total = _sum_available(
        _number(outer, "postprocess"),
        _number(outer, "diffraction_postprocess"),
        _number(outer, "volume_absorption_postprocess"),
    )
    return {
        "summary_available": True,
        "worker_status": worker_result.get("status"),
        "rank_failures": worker_result.get("rank_failures") or [],
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "diagnostic_only": summary.get("diagnostic_only"),
        "postprocess_skipped": summary.get("postprocess_skipped"),
        "linear_solve_method": summary.get("linear_solve_method"),
        "actual_ksp_type": summary.get("actual_ksp_type"),
        "actual_pc_type": summary.get("actual_pc_type"),
        "actual_pc_factor_solver_type": summary.get(
            "actual_pc_factor_solver_type"
        ),
        "ksp_converged": summary.get("ksp_converged"),
        "ksp_converged_reason": summary.get("ksp_converged_reason"),
        "mpi_size": summary.get("mpi_size"),
        "mesh_cell_type": summary.get("mesh_cell_type_actual"),
        "mesh_cells_resolved": summary.get("mesh_cells_resolved"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "full3d_equivalent_dofs": summary.get("num_nedelec_dofs"),
        "active_rows_with_dtn": matrix.get("matrix_rows"),
        "matrix_nnz_used": matrix.get("matrix_nnz_used"),
        "matrix_nnz_allocated": matrix.get("matrix_nnz_allocated"),
        "factor_inventory": factor,
        "stage4_dtn_component_vector_assemblies": summary.get(
            "stage4_dtn_component_vector_assemblies"
        ),
        "stage4_dtn_persistent_component_vector_restores": summary.get(
            "stage4_dtn_persistent_component_vector_restores"
        ),
        "stage4_dtn_persistent_reduced_modal_bundle_restores": (
            summary.get("stage4_dtn_persistent_reduced_modal_bundle_restores")
        ),
        "full_true_residual": _full_true_residual(summary),
        "R00_total": summary.get("R00_total"),
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_closure": (
            None
            if not isinstance(summary.get("R_total"), (int, float))
            or not isinstance(summary.get("T_total"), (int, float))
            else 1.0
            - float(summary["R_total"])
            - float(summary["T_total"])
        ),
        "configuration_identity": {
            "trace_degree": config.get("nedelec_trace_degree_resolved"),
            "interior_degree": config.get(
                "nedelec_interior_degree_resolved"
            ),
            "assembly_time_cell_static_condensation": config.get(
                "stage4_assembly_time_cell_static_condensation"
            ),
            "floquet_slave_elimination": config.get(
                "stage4_floquet_slave_elimination"
            ),
            "fast_fixed_trace_setup": config.get(
                "stage4_fast_fixed_trace_setup"
            ),
            "affine_isotropic_reference_tensor": config.get(
                "stage4_affine_isotropic_reference_tensor"
            ),
            "bulk_cell_insertion": config.get(
                "stage4_condensed_bulk_cell_insertion"
            ),
            "cache_directory": config.get(
                "stage4_condensed_cache_directory"
            ),
            "cache_source_sha": config.get(
                "stage4_condensed_cache_source_sha"
            ),
            "cache_mode": config.get("stage4_condensed_cache_mode"),
            "persistent_dtn_surface_cache": config.get(
                "stage4_condensed_persistent_dtn_surface_cache"
            ),
            "ordinary_default_changed": config.get(
                "ordinary_default_changed",
                False,
            ),
        },
        "cache_audit": {
            "raw_tensor": raw_cache,
            "condensed_class": condensed_cache,
            "dtn_surface_vector": dtn_surface_cache,
        },
        "cell_static_raw_tensor_evaluations": cell.get(
            "raw_tensor_kernel_evaluation_count"
        ),
        "native_object_ledger": cell.get("native_object_ledger"),
        "recovery_cache_lifecycle": cell.get(
            "recovery_cache_lifecycle"
        ),
        "timing_coverage": {
            "nonoverlapping_outer_stages": (
                "timings_seconds fields are mutually staged by the common "
                "case flow"
            ),
            "granular_condensation_fields": (
                "granular fields overlap the outer DtN stage and must not be "
                "summed with it"
            ),
            "mumps_symbolic_numeric": (
                "current common solver exposes their combined KSPSetUp time; "
                "separate symbolic and numeric values are unavailable"
            ),
            "deferred_surface_jit": (
                "surface form/JIT plus persistent-cache setup is measured "
                "separately from modal vector assembly"
            ),
        },
        "timings_seconds": {
            "import": {
                "solver_module_import": _number(
                    worker_timings,
                    "solver_module_import_seconds",
                ),
                "research_config_build": _number(
                    worker_timings,
                    "research_config_build_seconds",
                ),
            },
            "jit": {
                "bilinear_form_compile": _number(
                    summary,
                    "stage4_dtn_bilinear_form_compile_seconds",
                ),
                "bilinear_form_compile_skipped_by_affine_backend": (
                    summary.get(
                        "stage4_dtn_bilinear_form_compile_"
                        "skipped_by_affine_backend"
                    )
                ),
                "deferred_surface_jit_separate": None,
            },
            "mesh": {
                "mesh_build": _number(outer, "mesh_build"),
            },
            "function_space": {
                "total": _number(outer, "function_space_setup"),
                "element_build_and_ufl_wrap": _number(
                    outer,
                    "function_space_element_build_and_ufl_wrap",
                ),
                "dolfinx_functionspace_and_dofmap": _number(
                    outer,
                    "function_space_dolfinx_dofmap",
                ),
            },
            "tensor": {
                "kernel_or_analytic_total": _number(
                    cell,
                    "kernel_seconds_max",
                ),
                "affine_reference_gram": _number(
                    cell,
                    "affine_reference_gram_seconds_max",
                ),
                "affine_class_combination": _number(
                    cell,
                    "affine_class_combination_seconds_max",
                ),
                "persistent_cache_read": _number(
                    raw_cache,
                    "read_seconds_max",
                ),
                "persistent_cache_write": _number(
                    raw_cache,
                    "write_seconds_max",
                ),
            },
            "aii_and_schur": {
                "persistent_class_identity_and_key": _number(
                    condensed_cache,
                    "identity_and_key_seconds_max",
                ),
                "persistent_class_read": _number(
                    condensed_cache,
                    "read_seconds_max",
                ),
                "persistent_class_write": _number(
                    condensed_cache,
                    "write_seconds_max",
                ),
                "orientation": _number(
                    cell,
                    "orientation_seconds_max",
                ),
                "aii_factor": _number(
                    cell,
                    "aii_factor_seconds_max",
                ),
                "aii_solve": _number(
                    cell,
                    "aii_solve_seconds_max",
                ),
                "schur_product": _number(
                    cell,
                    "schur_product_seconds_max",
                ),
                "local_schur_total": _number(
                    cell,
                    "local_schur_seconds_max",
                ),
                "constraint_projection": _number(
                    cell,
                    "constraint_projection_seconds_max",
                ),
            },
            "preallocation_and_insertion": {
                "trace_preallocation": _number(
                    cell,
                    "trace_preallocation_seconds",
                ),
                "cell_block_insertion": _number(
                    cell,
                    "local_insert_seconds_max",
                ),
                "pre_final_assembly_sync": _number(
                    cell,
                    "pre_final_assembly_sync_seconds_max",
                ),
                "final_assembly": _number(
                    cell,
                    "final_assembly_seconds",
                ),
            },
            "dtn": {
                "outer_assembly_solve_recovery": dtn_outer,
                "non_ksp_derived": dtn_non_ksp,
                "surface_form_and_cache_setup": _number(
                    summary,
                    "stage4_dtn_surface_form_and_cache_setup_seconds",
                ),
                "persistent_surface_cache_identity_and_key": _number(
                    dtn_surface_cache,
                    "identity_and_key_seconds_max",
                ),
                "reduced_operator_identity": _number(
                    summary,
                    "stage4_dtn_reduced_operator_identity_seconds",
                ),
                "persistent_surface_cache_read": _number(
                    dtn_surface_cache,
                    "read_seconds_max",
                ),
                "persistent_surface_cache_write": _number(
                    dtn_surface_cache,
                    "write_seconds_max",
                ),
                "persistent_surface_vector_restore": _number(
                    summary,
                    "stage4_dtn_persistent_vector_restore_seconds",
                ),
                "persistent_reduced_modal_bundle_restore": _number(
                    summary,
                    "stage4_dtn_persistent_reduced_modal_bundle_restore_seconds",
                ),
                "incident_source_vector": _number(
                    summary,
                    "stage4_dtn_incident_source_vector_seconds",
                ),
                "modal_loop": _number(
                    summary,
                    "stage4_dtn_modal_loop_seconds",
                ),
                "modal_vector_assembly": _number(
                    summary,
                    "stage4_dtn_modal_vector_assembly_seconds",
                ),
                "modal_block_insertion": _number(
                    summary,
                    "stage4_dtn_modal_block_insert_seconds",
                ),
                "augmented_matrix_finalize": _number(
                    summary,
                    "stage4_dtn_augmented_matrix_finalize_seconds",
                ),
            },
            "mumps": {
                "symbolic": _number(
                    summary,
                    "stage4_dtn_mumps_symbolic_seconds",
                ),
                "numeric": _number(
                    summary,
                    "stage4_dtn_mumps_numeric_seconds",
                ),
                "symbolic_numeric_combined_ksp_setup": ksp_setup,
                "backsolve": ksp_solve,
            },
            "recovery": {
                "cell_interior_rhs_prepare_and_cache_release": _number(
                    summary,
                    "stage4_dtn_cell_interior_rhs_"
                    "prepare_and_cache_release_seconds",
                ),
                "warm_persistent_cache_heap_trim": _number(
                    summary,
                    "stage4_dtn_warm_persistent_cache_heap_trim_seconds",
                ),
                "cell_interior": _number(
                    summary,
                    "stage4_dtn_cell_static_condensation_recovery_seconds",
                ),
                "solution_backsubstitution": _number(
                    summary,
                    "stage4_dtn_solution_backsubstitution_seconds",
                ),
            },
            "postprocess": {
                "field": _number(outer, "postprocess"),
                "diffraction": _number(
                    outer,
                    "diffraction_postprocess",
                ),
                "volume_absorption": _number(
                    outer,
                    "volume_absorption_postprocess",
                ),
                "total_of_available_nonoverlapping_stages": (
                    postprocess_total
                ),
            },
            "outer_case": dict(outer),
            "common_solver_call": _number(
                worker_timings,
                "common_solver_call_seconds",
            ),
        },
    }


def _classify_profile(
    evidence: dict[str, Any],
    telemetry: dict[str, Any],
    *,
    cache_state: str,
    source_sha: str,
    expected_mpi_size: int,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    telemetry_readable: bool,
    source_stable_and_clean_after: bool,
) -> dict[str, Any]:
    config = evidence.get("configuration_identity") or {}
    cache = evidence.get("cache_audit") or {}
    raw_cache = cache.get("raw_tensor") or {}
    condensed_cache = cache.get("condensed_class") or {}
    dtn_surface_cache = cache.get("dtn_surface_vector") or {}
    topology = {
        "fixed_rectangular_hexa_h15": (
            evidence.get("mesh_cell_type") == "hexahedron"
            and evidence.get("mesh_cells_resolved")
            == EXPECTED_H15_TOPOLOGY["mesh_cells_resolved"]
            and evidence.get("num_mesh_cells")
            == EXPECTED_H15_TOPOLOGY["num_mesh_cells"]
        ),
        "fixed_p5_trace_p6_interior": (
            config.get("trace_degree") == 5
            and config.get("interior_degree") == 6
        ),
        "full3d_equivalent_dof_identity": (
            evidence.get("full3d_equivalent_dofs")
            == EXPECTED_H15_TOPOLOGY["full3d_equivalent_dofs"]
        ),
        "active_row_identity": (
            evidence.get("active_rows_with_dtn")
            == EXPECTED_H15_TOPOLOGY["active_rows_with_dtn"]
        ),
    }
    cache_checks = {
        "raw_tensor_cache_enabled": raw_cache.get("enabled") is True,
        "condensed_class_cache_enabled": (
            condensed_cache.get("enabled") is True
        ),
        "dtn_surface_vector_cache_enabled": (
            dtn_surface_cache.get("enabled") is True
        ),
        "dtn_surface_cache_collective_all_or_nothing": (
            dtn_surface_cache.get("collective_all_or_nothing") is True
        ),
        "dtn_reduced_modal_cache_v2_identity": (
            dtn_surface_cache.get("schema_version")
            == DTN_REDUCED_MODAL_CACHE_SCHEMA
            and dtn_surface_cache.get("source_commit_sha") == source_sha
            and dtn_surface_cache.get("payload_kind")
            == "full_surface_vectors_plus_reduced_modal_bundles"
            and dtn_surface_cache.get("legacy_v1_payload_compatible")
            is False
            and dtn_surface_cache.get(
                "material_and_tensor_identity_bound"
            )
            is True
            and dtn_surface_cache.get("content_checksum_verified") is True
            and dtn_surface_cache.get("pickle_used") is False
            and dtn_surface_cache.get(
                "identity_or_payload_mismatch_is_fail_closed"
            )
            is True
            and dtn_surface_cache.get("inactive_modes_stored") is False
            and dtn_surface_cache.get("ordinary_default_changed") is False
        ),
        "cache_mode_identity": (
            raw_cache.get("mode") == CACHE_MODES[cache_state]
            and condensed_cache.get("mode") == CACHE_MODES[cache_state]
            and dtn_surface_cache.get("mode")
            == CACHE_MODES[cache_state]
            and config.get("cache_mode") == CACHE_MODES[cache_state]
        ),
        "cache_source_sha_identity": config.get("cache_source_sha")
        == source_sha,
        "cold_raw_tensor_cache_wrote_entries": (
            cache_state != "cold"
            or (
                isinstance(raw_cache.get("write_count"), int)
                and raw_cache["write_count"] > 0
            )
        ),
        "cold_condensed_class_cache_wrote_entries": (
            cache_state != "cold"
            or (
                isinstance(
                    condensed_cache.get("write_count_sum"),
                    int,
                )
                and condensed_cache["write_count_sum"] > 0
            )
        ),
        "cold_dtn_surface_cache_wrote_complete_rank_bundles": (
            cache_state != "cold"
            or (
                isinstance(
                    dtn_surface_cache.get("write_count_sum"),
                    int,
                )
                and dtn_surface_cache["write_count_sum"]
                == int(expected_mpi_size)
                and dtn_surface_cache.get("record_count_sum")
                == int(expected_mpi_size)
                * int(
                    dtn_surface_cache.get(
                        "descriptor_count_per_rank",
                        -1,
                    )
                )
                and dtn_surface_cache.get("reduced_bundle_record_count_sum")
                == int(expected_mpi_size)
                * int(
                    dtn_surface_cache.get(
                        "surface_order_count_per_rank",
                        -1,
                    )
                )
            )
        ),
        "warm_raw_tensor_cache_hit_without_recompute": (
            cache_state != "warm"
            or (
                isinstance(raw_cache.get("hit_count"), int)
                and raw_cache["hit_count"] > 0
                and evidence.get("cell_static_raw_tensor_evaluations", 0)
                == 0
            )
        ),
        "warm_condensed_class_cache_hit_without_recompute": (
            cache_state != "warm"
            or (
                isinstance(
                    condensed_cache.get("hit_count_sum"),
                    int,
                )
                and condensed_cache["hit_count_sum"] > 0
                and condensed_cache.get("construction_count_sum") == 0
            )
        ),
        "warm_dtn_surface_cache_hit_without_reassembly": (
            cache_state != "warm"
            or (
                dtn_surface_cache.get("hit_on_all_ranks") is True
                and dtn_surface_cache.get("hit_count_sum")
                == int(expected_mpi_size)
                and evidence.get(
                    "stage4_dtn_component_vector_assemblies",
                    0,
                )
                == 0
                and evidence.get(
                    "stage4_dtn_persistent_reduced_modal_bundle_restores",
                    0,
                )
                == int(
                    dtn_surface_cache.get(
                        "surface_order_count_per_rank",
                        -1,
                    )
                )
                and dtn_surface_cache.get(
                    "reduced_bundle_restore_count_sum"
                )
                == int(expected_mpi_size)
                * int(
                    dtn_surface_cache.get(
                        "surface_order_count_per_rank",
                        -1,
                    )
                )
                and (
                    dtn_surface_cache.get("restore_count_sum", -1)
                    + dtn_surface_cache.get(
                        "unrestored_full_vector_array_count_sum",
                        -1,
                    )
                    == int(expected_mpi_size)
                    * int(
                        dtn_surface_cache.get(
                            "descriptor_count_per_rank",
                            -1,
                        )
                    )
                )
                and dtn_surface_cache.get("trace_projection_recomputed_after_restore")
                is False
                and dtn_surface_cache.get(
                    "cell_interior_bilinear_recomputed_after_restore"
                )
                is False
            )
        ),
    }
    residual = evidence.get("full_true_residual")
    process_swap = telemetry.get("max_process_tree_swap_mb")
    smaps_swap = telemetry.get("max_worker_rank_smaps_swap_sum_mb")
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "telemetry_readable_every_sample": telemetry_readable,
        "summary_available": evidence.get("summary_available") is True,
        "no_rank_failures": not evidence.get("rank_failures"),
        "all_expected_mpi_ranks_observed": (
            telemetry.get("observed_worker_rank_count")
            == int(expected_mpi_size)
        ),
        "source_stable_and_clean_after": source_stable_and_clean_after,
        "direct_mumps_identity": (
            evidence.get("linear_solve_method") == "direct_lu"
            and evidence.get("actual_pc_factor_solver_type") == "mumps"
        ),
        "solve_converged": evidence.get("ksp_converged") is True,
        "full_true_residual_le_1e-9": (
            isinstance(residual, (int, float))
            and not isinstance(residual, bool)
            and float(residual) <= 1.0e-9
        ),
        "fast_setup_opt_in": config.get("fast_fixed_trace_setup") is True,
        "affine_tensor_opt_in": (
            config.get("affine_isotropic_reference_tensor") is True
        ),
        "persistent_dtn_surface_cache_opt_in": (
            config.get("persistent_dtn_surface_cache") is True
        ),
        "assembly_time_condensation_opt_in": (
            config.get("assembly_time_cell_static_condensation") is True
        ),
        "floquet_elimination_opt_in": (
            config.get("floquet_slave_elimination") is True
        ),
        "ordinary_default_unchanged": (
            config.get("ordinary_default_changed") is False
        ),
        "no_process_tree_swap": (
            isinstance(process_swap, (int, float))
            and float(process_swap) == 0.0
        ),
        "no_worker_smaps_swap": (
            isinstance(smaps_swap, (int, float))
            and float(smaps_swap) == 0.0
        ),
        **topology,
        **cache_checks,
    }
    passed = all(checks.values())
    infrastructure_names = (
        "process_completed",
        "not_terminated_for_memory",
        "not_terminated_for_timeout",
        "telemetry_readable_every_sample",
        "summary_available",
        "no_rank_failures",
        "all_expected_mpi_ranks_observed",
        "source_stable_and_clean_after",
    )
    evidence_valid = all(checks[name] for name in infrastructure_names)
    if passed:
        status = "actual_direct_setup_resource_profile_pass"
        classification = "positive_direct_setup_resource_profile"
    elif terminated_for_memory:
        status = "controlled_stop_memory"
        classification = "resource_controlled_stop"
    elif terminated_for_timeout:
        status = "controlled_stop_timeout"
        classification = "resource_controlled_stop"
    elif evidence_valid:
        status = "controlled_negative_direct_setup_profile"
        classification = "controlled_negative"
    else:
        status = "direct_setup_watchdog_infrastructure_failure"
        classification = "invalid_or_incomplete_evidence"
    return {
        "status": status,
        "classification": classification,
        "evidence_valid": evidence_valid,
        "formal_profile_pass": passed,
        "checks": checks,
        "failures": [name for name, value in checks.items() if not value],
    }


def _cache_pairs(cache_directory: Path, *, prefix: str) -> list[str]:
    pairs: list[str] = []
    suffix = ".npy" if prefix == "raw_tensor" else ".npz"
    for manifest in sorted(cache_directory.glob(f"{prefix}_*.json")):
        array = manifest.with_suffix(suffix)
        if array.is_file():
            pairs.append(manifest.stem)
    return pairs


def _resolve_cache_directory(
    args: argparse.Namespace,
    source_sha: str,
) -> Path:
    path = (
        args.cache_directory
        if args.cache_directory is not None
        else args.artifact_root / "condensed_setup_cache" / source_sha
    )
    resolved = path.resolve()
    if str(resolved).startswith("/mnt/"):
        raise SystemExit("formal cache must stay on the WSL Linux filesystem")
    if args.cache_state == "cold":
        if resolved.exists():
            raise SystemExit(
                "cold cache directory must not exist; historical cache "
                f"contents will not be overwritten: {resolved}"
            )
    else:
        if not resolved.is_dir():
            raise SystemExit(
                f"warm cache directory does not exist: {resolved}"
            )
        if not _cache_pairs(resolved, prefix="raw_tensor"):
            raise SystemExit(
                "warm cache requires at least one complete SHA-bound raw "
                f"tensor manifest/array pair: {resolved}"
            )
        if not _cache_pairs(resolved, prefix="condensed_class"):
            raise SystemExit(
                "warm cache requires at least one complete SHA-bound "
                f"condensed-class manifest/array pair: {resolved}"
            )
        if not _cache_pairs(resolved, prefix="dtn_reduced_modal"):
            raise SystemExit(
                "warm cache requires at least one complete mesh/mode/trace-"
                f"bound DtN reduced-modal manifest/array pair: {resolved}"
            )
    return resolved


def _resource_preflight(run_dir: Path) -> dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "effective_limit": effective_memory_limit(),
        "artifact_filesystem_free_bytes": shutil.disk_usage(run_dir).free,
    }


def _run_parent(args: argparse.Namespace) -> int:
    source_before = _source_preflight()
    environment = _environment_preflight()
    if environment["pass"] is not True:
        failures = [
            name
            for name, passed in environment["checks"].items()
            if not passed
        ]
        raise SystemExit(
            f"qualified WSL/PETSc environment preflight failed: {failures}"
        )

    artifact_root = args.artifact_root.resolve()
    if str(artifact_root).startswith("/mnt/"):
        raise SystemExit(
            "formal artifacts must stay on the WSL Linux filesystem"
        )
    cache_directory = _resolve_cache_directory(
        args,
        source_before["commit_sha"],
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir.resolve()
        if args.run_dir is not None
        else artifact_root
        / (
            f"h15_fixed_p5trace_p6interior_direct_{args.cache_state}_"
            f"mpi{args.mpi_size}_{timestamp}"
        )
    )
    if str(run_dir).startswith("/mnt/"):
        raise SystemExit("formal run directory must stay on WSL Linux storage")
    run_dir.mkdir(parents=True, exist_ok=False)
    progress_path = run_dir / "solve" / "progress_3d.jsonl"
    stdout_path = run_dir / "worker_stdout.txt"
    worker_result_path = run_dir / "worker_result.json"
    timeline_path = run_dir / "memory_timeline.csv"
    record_path = (
        _exclusive_path(args.record)
        if args.record is not None
        else run_dir / "watchdog_summary.json"
    )

    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task035b_direct_setup_profile",
        "--worker",
        "--execute-pde",
        "--mpi-size",
        str(args.mpi_size),
        "--cache-state",
        args.cache_state,
        "--cache-directory",
        str(cache_directory),
        "--h-nm",
        str(args.h_nm),
        "--run-dir",
        str(run_dir),
        "--source-sha",
        source_before["commit_sha"],
    ]
    child_environment = os.environ.copy()
    child_environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "TMPDIR": "/tmp",
            "TMP": "/tmp",
            "TEMP": "/tmp",
        }
    )

    rows: list[dict[str, Any]] = []
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    telemetry_readable = True
    started = time.perf_counter()
    with stdout_path.open("x", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=child_environment,
            start_new_session=True,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            rss_mb = row.get("mpi_process_tree_rss_mb")
            swap_mb = row.get("mpi_process_tree_swap_mb")
            readable = (
                isinstance(rss_mb, (int, float))
                and not isinstance(rss_mb, bool)
                and isinstance(swap_mb, (int, float))
                and not isinstance(swap_mb, bool)
            )
            telemetry_readable &= readable
            rss_gib = float(rss_mb) / 1024.0 if readable else None
            if rss_gib is not None:
                warning_triggered |= rss_gib >= float(args.warning_gib)
            if process.poll() is not None:
                break
            if not readable:
                _terminate_process_group(process)
            elif rss_gib is not None and rss_gib >= args.terminate_gib:
                terminated_for_memory = True
                _terminate_process_group(process)
            elif elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                _terminate_process_group(process)
            else:
                time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    worker_result = (
        json.loads(worker_result_path.read_text(encoding="utf-8"))
        if worker_result_path.is_file()
        else {
            "schema_version": "task035b.direct-setup-profile-worker.v1",
            "status": "worker_result_missing",
            "summary": None,
            "rank_failures": [],
        }
    )
    telemetry = _telemetry_summary(rows)
    evidence = _extract_setup_evidence(worker_result)
    head_after = _git("rev-parse", "HEAD").lower()
    branch_after = _git("branch", "--show-current")
    status_after = _git(
        "status",
        "--porcelain",
        "--untracked-files=all",
    )
    source_stable = (
        head_after == source_before["commit_sha"]
        and branch_after == source_before["branch"]
        and not status_after
    )
    source = {
        **source_before,
        "head_after_before_record_write": head_after,
        "branch_after_before_record_write": branch_after,
        "status_after_before_record_write": status_after,
        "stable_and_clean_after": source_stable,
    }
    profile = _classify_profile(
        evidence,
        telemetry,
        cache_state=args.cache_state,
        source_sha=source_before["commit_sha"],
        expected_mpi_size=int(args.mpi_size),
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        telemetry_readable=telemetry_readable,
        source_stable_and_clean_after=source_stable,
    )

    record = {
        "schema_version": "task035b.direct-setup-resource-watchdog.v1",
        "benchmark_id": "task035b_direct_setup_resource_profile",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": profile["status"],
        "classification": profile["classification"],
        "ordinary_default_changed": False,
        "command": command,
        "request": {
            "geometry": "Task034 fixed rectangular block grating",
            "h_nm": 15.0,
            "trace_degree": 5,
            "interior_degree": 6,
            "mpi_size": int(args.mpi_size),
            "cache_state": args.cache_state,
            "cache_mode": CACHE_MODES[args.cache_state],
            "cache_directory": _path_from_root(cache_directory),
            "fast_fixed_trace_setup": True,
            "affine_isotropic_reference_tensor": True,
            "direct_solver": "MUMPS",
        },
        "source": source,
        "environment": environment,
        "resource_preflight": _resource_preflight(run_dir),
        "resource_policy": {
            "one_heavy_case_at_a_time": True,
            "warning_gib": float(args.warning_gib),
            "termination_gib": float(args.terminate_gib),
            "timeout_seconds": float(args.timeout_seconds),
            "swap_allowed": False,
            "termination_scope": "complete_process_group",
        },
        "resource_authority": telemetry,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "worker_return_code": return_code,
        "setup_and_solver_evidence": evidence,
        "profile_qualification": profile,
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "worker_result": _path_from_root(worker_result_path),
            "worker_result_sha256": _sha256(worker_result_path),
            "solve_summary": _path_from_root(
                run_dir / "solve" / "run_summary.json"
            ),
            "solve_summary_sha256": _sha256(
                run_dir / "solve" / "run_summary.json"
            ),
            "progress": _path_from_root(progress_path),
            "progress_sha256": _sha256(progress_path),
            "memory_timeline": _path_from_root(timeline_path),
            "memory_timeline_sha256": _sha256(timeline_path),
            "stdout": _path_from_root(stdout_path),
            "stdout_sha256": _sha256(stdout_path),
            "cache_pairs_after": {
                "raw_tensor": _cache_pairs(
                    cache_directory,
                    prefix="raw_tensor",
                ),
                "condensed_class": _cache_pairs(
                    cache_directory,
                    prefix="condensed_class",
                ),
                "dtn_reduced_modal": _cache_pairs(
                    cache_directory,
                    prefix="dtn_reduced_modal",
                ),
            },
        },
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
            + "\n"
        )
    print(
        json.dumps(
            {
                "status": profile["status"],
                "classification": profile["classification"],
                "formal_profile_pass": profile["formal_profile_pass"],
                "record": _path_from_root(record_path),
                "cache_directory": _path_from_root(cache_directory),
                "failures": profile["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if profile["evidence_valid"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        return _worker(args)
    if not args.execute_pde:
        print(json.dumps(_dry_run_plan(args), ensure_ascii=False, indent=2))
        return 0
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
