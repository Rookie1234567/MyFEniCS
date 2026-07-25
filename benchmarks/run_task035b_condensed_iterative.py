"""Formal watchdog for Task035b factor-free assembled condensed iteration.

The ordinary Stage-4 direct profile remains untouched.  This runner is a thin,
explicit opt-in around the existing fixed-p5-trace/p6-interior numerical core.
Without ``--execute-pde`` it only prints the reviewed execution plan.
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
    _source_provenance,
    _stage_peaks,
)
from benchmarks.task034_wsl_resources import effective_memory_limit


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
DEFAULT_ARTIFACT_ROOT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "task035b"
    / "condensed_iterative"
)
PHYSICS_AWARE_PROFILE = "fgmres_dtn_trace_deflation"
SUPPORTED_PROFILES = (
    "gmres_jacobi",
    "fgmres_asm_ilu",
    PHYSICS_AWARE_PROFILE,
)
EXPECTED_H15_TOPOLOGY = {
    "mesh_cells_resolved": [6, 2, 10],
    "num_mesh_cells": 120,
    "num_nedelec_dofs": 74890,
    "matrix_rows": 16880,
}


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


def _exclusive_output_path(path: Path) -> Path:
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    if resolved.exists():
        raise SystemExit(
            "output record already exists; historical evidence will not be "
            f"overwritten: {resolved}"
        )
    return resolved


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task035b opt-in factor-free assembled condensed iterative "
            "watchdog. The default action is a non-PDE execution plan."
        )
    )
    parser.add_argument(
        "--execute-pde",
        action="store_true",
        help="explicitly authorize the reviewed h15 iterative PDE screen",
    )
    parser.add_argument(
        "--profile",
        choices=SUPPORTED_PROFILES,
        help=(
            "programmatic iterative profile; no raw PETSc-option interface "
            "is exposed"
        ),
    )
    parser.add_argument(
        "--mpi-size",
        type=int,
        choices=(1, 2, 4, 8),
        default=8,
        help="Review-V2 h15 workstation-rank study point",
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
    parser.add_argument(
        "--verified-clean-sha",
        help=(
            "full clean-source SHA attested by the WSL host when local Git "
            "status cannot be trusted"
        ),
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source-sha", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if abs(float(args.h_nm) - 15.0) > 1.0e-12:
        parser.error(
            "Review V2 authorizes this rank-study runner only for frozen h15"
        )
    if args.warning_gib <= 0.0:
        parser.error("--warning-gib must be positive")
    if args.terminate_gib <= args.warning_gib:
        parser.error("--terminate-gib must exceed --warning-gib")
    if args.timeout_seconds <= 0.0 or args.poll_interval <= 0.0:
        parser.error("timeout and poll interval must be positive")
    if (args.execute_pde or args.worker) and args.profile is None:
        parser.error("--execute-pde requires an explicit --profile")
    if args.worker and (args.run_dir is None or args.source_sha is None):
        parser.error("--worker requires --run-dir and --source-sha")
    if args.worker and not args.execute_pde:
        parser.error("--worker requires --execute-pde")
    if not args.worker and not args.execute_pde and args.record is not None:
        parser.error(
            "the default plan is stdout-only; --record requires --execute-pde"
        )
    return args


def _dry_run_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "task035b.condensed-iterative-plan.v1",
        "status": "not_run_requires_explicit_execute_pde",
        "pde_started": False,
        "ordinary_default_changed": False,
        "geometry": "Task034 fixed rectangular block grating",
        "space": "fixed p5 trace plus p6 cell interior",
        "h_nm": 15.0,
        "mpi_size": int(args.mpi_size),
        "selected_profile": args.profile,
        "supported_programmatic_profiles": list(SUPPORTED_PROFILES),
        "profile_evidence_status": {
            "gmres_jacobi": "closed_controlled_negative",
            "fgmres_asm_ilu": "closed_controlled_negative",
            "fgmres_dtn_trace_deflation": (
                "not_run_requires_formal_discriminator"
            ),
        },
        "raw_petsc_options_accepted": False,
        "formal_first_screen": {
            "restart": 30,
            "maximum_iterations": 200,
            "minimum_unpreconditioned_residual_reduction_decades": 3.0,
            "terminal_explicit_reduced_relative_residual_max": 1.0e-3,
            "full_recovered_true_residual_required": True,
            "global_direct_factor_nnz_required": 0,
            "swap_allowed": False,
        },
        "physics_aware_discriminator": {
            "profile": "fgmres_dtn_trace_deflation",
            "coarse_basis": (
                "one normalized [-diag(A_tt)^-1 B_j; e_j] vector per "
                "physical DtN auxiliary mode"
            ),
            "fine_sparse_factor_nnz": 0,
            "small_dense_coarse_factor_reported_separately": True,
            "status": "not_run",
        },
        "next_action": (
            "rerun with --execute-pde and an explicit --profile after "
            "committing all source changes"
        ),
    }


def _environment_preflight() -> dict[str, Any]:
    from mpi4py import MPI
    import numpy as np
    from petsc4py import PETSc

    executable = Path(sys.executable).absolute()
    expected_python = (ROOT / ".venv" / "bin" / "python").absolute()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
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


def _iterative_config(profile: str, *, h_nm: float):
    """Build only the reviewed research configuration; numerical work is core-owned."""

    from src.common.config_3d import target_stage4_config

    base = target_stage4_config(degree=6, h_nm=float(h_nm))
    return replace(
        base,
        case_name=(
            f"task035b_fixed_p5trace_p6interior_h{h_nm:g}_{profile}"
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
        stage4_condensed_iterative_profile=profile,
        stage4_retain_dual_recovery_context=False,
        stage4_fast_fixed_trace_setup=True,
        stage4_affine_isotropic_reference_tensor=True,
        stage4_condensed_bulk_cell_insertion=False,
        petsc_extra_options={},
        unique_output=False,
    )


def _worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    solve_dir = args.run_dir / "solve"
    local_failure: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    try:
        from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
            run_stage4b_block_grating_3d_case,
        )

        cfg = _iterative_config(args.profile, h_nm=float(args.h_nm))
        summary = run_stage4b_block_grating_3d_case(cfg, solve_dir)
    except Exception as exc:  # evidence must survive a solver-side failure
        local_failure = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    failures = comm.allgather(local_failure)
    if comm.rank == 0:
        payload = {
            "schema_version": "task035b.condensed-iterative-worker.v1",
            "status": (
                "worker_completed_with_summary"
                if not any(failures)
                else "worker_exception_preserved"
            ),
            "profile": args.profile,
            "mpi_size": int(comm.size),
            "source_sha": args.source_sha,
            "summary": summary,
            "rank_failures": [
                failure for failure in failures if failure is not None
            ],
        }
        (args.run_dir / "worker_result.json").write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
            + "\n",
            encoding="utf-8",
        )
    comm.barrier()
    return 0 if not any(failures) else 3


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
    for row in rows:
        try:
            worker_rows = json.loads(
                str(row.get("worker_rank_rss_mb_json", "[]"))
            )
        except json.JSONDecodeError:
            worker_rows = []
        if isinstance(worker_rows, list):
            observed_ranks.update(
                int(entry["rank"])
                for entry in worker_rows
                if isinstance(entry, dict)
                and isinstance(entry.get("rank"), int)
            )
        try:
            smaps_rows = json.loads(
                str(row.get("worker_rank_smaps_rollup_json", "[]"))
            )
        except json.JSONDecodeError:
            smaps_rows = []
        if not isinstance(smaps_rows, list):
            smaps_rows = []
        for entry in smaps_rows:
            if not isinstance(entry, dict) or not isinstance(
                entry.get("rank"), int
            ):
                continue
            rank = int(entry["rank"])
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
                    value, bool
                ):
                    peaks[field] = max(
                        peaks.get(field, 0.0), float(value)
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
            rows, "mpi_process_tree_swap_mb"
        ),
        "max_worker_rank_pss_sum_mb": _numeric_max(
            rows, "worker_rank_pss_sum_mb"
        ),
        "max_worker_rank_uss_sum_mb": _numeric_max(
            rows, "worker_rank_uss_sum_mb"
        ),
        "max_worker_rank_shared_sum_mb": _numeric_max(
            rows, "worker_rank_shared_sum_mb"
        ),
        "max_worker_rank_smaps_swap_sum_mb": _numeric_max(
            rows, "worker_rank_smaps_swap_sum_mb"
        ),
        "max_container_cgroup_current_mb": _numeric_max(
            rows, "container_cgroup_current_mb"
        ),
        "max_container_cgroup_peak_mb": _numeric_max(
            rows, "container_cgroup_peak_mb"
        ),
        "per_rank_smaps_rollup_peaks_mb": {
            str(rank): fields for rank, fields in sorted(per_rank.items())
        },
        "per_rank_peak_thread_runtime": {
            str(rank): entry
            for rank, entry in sorted(per_rank_thread_runtime.items())
        },
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _full_true_residual(summary: dict[str, Any]) -> float | None:
    cell = summary.get("cell_static_condensation") or {}
    explicit = cell.get("full_explicit_true_residual")
    if isinstance(explicit, dict):
        explicit = explicit.get("linear_system_relative_residual")
    if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
        return float(explicit)
    fallback = summary.get("linear_system_relative_residual")
    if isinstance(fallback, (int, float)) and not isinstance(fallback, bool):
        return float(fallback)
    return None


def _extract_solver_evidence(
    worker_result: dict[str, Any],
) -> dict[str, Any]:
    summary = worker_result.get("summary")
    if not isinstance(summary, dict):
        return {
            "summary_available": False,
            "worker_status": worker_result.get("status"),
            "rank_failures": worker_result.get("rank_failures") or [],
        }
    iterative = summary.get("stage4_condensed_iterative") or {}
    factor_inventory = summary.get("stage4_dtn_factor_inventory") or {}
    matrix = summary.get("matrix_stats") or {}
    config = summary.get("config") or {}
    cell = summary.get("cell_static_condensation") or {}
    return {
        "summary_available": True,
        "worker_status": worker_result.get("status"),
        "rank_failures": worker_result.get("rank_failures") or [],
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "diagnostic_only": summary.get("diagnostic_only"),
        "postprocess_skipped": summary.get("postprocess_skipped"),
        "postprocess_skip_reason": summary.get("postprocess_skip_reason"),
        "linear_solve_method": summary.get("linear_solve_method"),
        "profile": summary.get("stage4_condensed_iterative_profile"),
        "ksp_type": summary.get("actual_ksp_type"),
        "pc_type": summary.get("actual_pc_type"),
        "ksp_converged": summary.get("ksp_converged"),
        "ksp_converged_reason": summary.get("ksp_converged_reason"),
        "ksp_converged_reason_name": summary.get(
            "ksp_converged_reason_name"
        ),
        "iterations": summary.get("ksp_iterations"),
        "residual_history": iterative.get("residual_history"),
        "residual_history_initial_norm": iterative.get(
            "residual_history_initial_norm"
        ),
        "residual_history_final_norm": iterative.get(
            "residual_history_final_norm"
        ),
        "residual_history_final_to_initial": iterative.get(
            "residual_history_final_to_initial"
        ),
        "terminal_explicit_reduced_residual_norm": iterative.get(
            "terminal_explicit_reduced_residual_norm"
        ),
        "terminal_explicit_reduced_relative_residual": iterative.get(
            "terminal_explicit_reduced_relative_residual"
        ),
        "full_recovered_true_residual": _full_true_residual(summary),
        "configured_programmatically": iterative.get(
            "configured_programmatically"
        ),
        "raw_petsc_options_used_for_iterative_configuration": iterative.get(
            "raw_petsc_options_used_for_iterative_configuration"
        ),
        "assembled_reduced_operator": iterative.get(
            "assembled_reduced_operator"
        ),
        "matrix_free": iterative.get("matrix_free"),
        "typed_profile_contract": iterative.get(
            "typed_profile_contract"
        ),
        "physics_aware_preconditioner": iterative.get(
            "physics_aware_preconditioner"
        ),
        "global_direct_factor_nnz": iterative.get(
            "global_direct_factor_nnz",
            factor_inventory.get("global_direct_factor_nnz"),
        ),
        "mumps_symbolic_or_numeric_created": iterative.get(
            "mumps_symbolic_or_numeric_created"
        ),
        "factor_inventory": factor_inventory,
        "native_object_ledger": cell.get("native_object_ledger"),
        "recovery_cache_lifecycle": cell.get(
            "recovery_cache_lifecycle"
        ),
        "local_subdomain_ilu_active": factor_inventory.get(
            "local_subdomain_ilu_active"
        ),
        "mpi_size": summary.get("mpi_size"),
        "h_nm": config.get("mesh_target_size"),
        "trace_degree": config.get("nedelec_trace_degree_resolved"),
        "interior_degree": config.get(
            "nedelec_interior_degree_resolved"
        ),
        "mesh_cell_type": summary.get("mesh_cell_type_actual"),
        "mesh_cells_resolved": summary.get("mesh_cells_resolved"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "full3d_equivalent_dofs": summary.get("num_nedelec_dofs"),
        "matrix_rows": matrix.get("matrix_rows"),
        "matrix_nnz_used": matrix.get("matrix_nnz_used"),
        "matrix_nnz_allocated": matrix.get("matrix_nnz_allocated"),
        "matrix_average_row_width": matrix.get(
            "matrix_average_row_width"
        ),
        "matrix_maximum_row_width": matrix.get(
            "matrix_maximum_row_width"
        ),
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
        "elapsed_seconds": summary.get("elapsed_seconds"),
        "timings_seconds": summary.get("timings_seconds"),
        "ordinary_default_changed": config.get(
            "ordinary_default_changed", False
        ),
    }


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _classify_screen(
    evidence: dict[str, Any],
    telemetry: dict[str, Any],
    *,
    expected_profile: str,
    expected_mpi_size: int,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    telemetry_readable: bool,
) -> dict[str, Any]:
    reduction = evidence.get("residual_history_final_to_initial")
    reduced = evidence.get(
        "terminal_explicit_reduced_relative_residual"
    )
    process_swap = telemetry.get("max_process_tree_swap_mb")
    smaps_swap = telemetry.get("max_worker_rank_smaps_swap_sum_mb")
    physics_aware_checks: dict[str, bool] = {}
    if expected_profile == PHYSICS_AWARE_PROFILE:
        contract = evidence.get("typed_profile_contract")
        physics = evidence.get("physics_aware_preconditioner")
        inventory = evidence.get("factor_inventory")
        contract = contract if isinstance(contract, dict) else {}
        physics = physics if isinstance(physics, dict) else {}
        inventory = inventory if isinstance(inventory, dict) else {}
        coarse_dimension = physics.get("coarse_dimension")
        coarse_rank = physics.get("coarse_rank")
        coarse_entries = physics.get("coarse_dense_matrix_entries")
        coarse_bytes = physics.get("coarse_dense_matrix_bytes")
        inventory_entries = inventory.get(
            "coarse_dense_matrix_entries"
        )
        inventory_bytes = inventory.get("coarse_dense_matrix_bytes")
        physics_aware_checks = {
            "typed_profile_contract_present": bool(contract),
            "typed_profile_contract_schema": (
                contract.get("schema_version")
                == "task035b.condensed-iterative-profile-contract.v2"
            ),
            "typed_profile_contract_name": (
                contract.get("name") == expected_profile
            ),
            "typed_profile_contract_programmatic": (
                contract.get("configured_programmatically") is True
            ),
            "typed_profile_contract_rejects_raw_options": (
                contract.get("raw_petsc_options_accepted") is False
            ),
            "typed_profile_contract_assembled_reduced_operator": (
                contract.get("assembled_reduced_operator") is True
            ),
            "typed_profile_contract_not_matrix_free": (
                contract.get("matrix_free") is False
            ),
            "typed_profile_contract_ordinary_default_unchanged": (
                contract.get("ordinary_default_changed") is False
            ),
            "physics_aware_preconditioner_present": bool(physics),
            "physics_aware_coarse_full_rank": (
                isinstance(coarse_dimension, int)
                and not isinstance(coarse_dimension, bool)
                and coarse_dimension > 0
                and coarse_rank == coarse_dimension
            ),
            "physics_aware_fine_operator_factor_free": (
                physics.get("fine_operator_factor_free") is True
            ),
            "physics_aware_global_fine_sparse_factor_absent": (
                physics.get("global_fine_sparse_factor_nnz") == 0
            ),
            "physics_aware_mumps_absent": (
                physics.get("mumps_symbolic_or_numeric_created") is False
            ),
            "physics_aware_dense_coarse_lu_disclosed": (
                physics.get("coarse_dense_lu_active") is True
            ),
            "physics_aware_not_strictly_factorless": (
                physics.get("strictly_factorless_preconditioner") is False
            ),
            "physics_aware_factor_disclosure_reason_recorded": (
                isinstance(
                    physics.get("strictly_factorless_reason"),
                    str,
                )
                and bool(
                    physics["strictly_factorless_reason"].strip()
                )
            ),
            "physics_aware_dense_coarse_entries_consistent": (
                isinstance(coarse_entries, int)
                and not isinstance(coarse_entries, bool)
                and isinstance(coarse_dimension, int)
                and not isinstance(coarse_dimension, bool)
                and coarse_entries == coarse_dimension * coarse_dimension
            ),
            "physics_aware_dense_coarse_bytes_consistent": (
                isinstance(coarse_bytes, int)
                and not isinstance(coarse_bytes, bool)
                and isinstance(coarse_entries, int)
                and not isinstance(coarse_entries, bool)
                and coarse_bytes == coarse_entries * 16
            ),
            "factor_inventory_dense_coarse_lu_disclosed": (
                inventory.get("coarse_dense_lu_active") is True
            ),
            "factor_inventory_fine_operator_factor_free": (
                inventory.get("fine_operator_factor_free") is True
            ),
            "factor_inventory_global_fine_sparse_factor_absent": (
                inventory.get("global_fine_sparse_factor_nnz") == 0
            ),
            "factor_inventory_mumps_absent": (
                inventory.get("mumps_symbolic_or_numeric_created")
                is False
            ),
            "factor_inventory_not_strictly_factorless": (
                inventory.get("strictly_factorless_preconditioner")
                is False
            ),
            "factor_inventory_dense_coarse_entries_match": (
                inventory_entries == coarse_entries
                and isinstance(inventory_entries, int)
                and not isinstance(inventory_entries, bool)
            ),
            "factor_inventory_dense_coarse_bytes_match": (
                inventory_bytes == coarse_bytes
                and isinstance(inventory_bytes, int)
                and not isinstance(inventory_bytes, bool)
            ),
            "factor_inventory_dense_coarse_semantics_recorded": (
                isinstance(
                    inventory.get("coarse_dense_lu_storage_semantics"),
                    str,
                )
                and bool(
                    inventory[
                        "coarse_dense_lu_storage_semantics"
                    ].strip()
                )
            ),
        }
    topology_checks = {
        "fixed_rectangular_hexa_h15": (
            evidence.get("mesh_cell_type") == "hexahedron"
            and abs(float(evidence.get("h_nm", -1.0)) - 15.0)
            <= 1.0e-12
        ),
        "fixed_p5_trace_p6_interior": (
            evidence.get("trace_degree") == 5
            and evidence.get("interior_degree") == 6
        ),
        "h15_mesh_axis_identity": (
            evidence.get("mesh_cells_resolved")
            == EXPECTED_H15_TOPOLOGY["mesh_cells_resolved"]
            and evidence.get("num_mesh_cells")
            == EXPECTED_H15_TOPOLOGY["num_mesh_cells"]
        ),
        "full3d_equivalent_dof_identity": (
            evidence.get("full3d_equivalent_dofs")
            == EXPECTED_H15_TOPOLOGY["num_nedelec_dofs"]
        ),
        "active_row_identity": (
            evidence.get("matrix_rows")
            == EXPECTED_H15_TOPOLOGY["matrix_rows"]
        ),
    }
    screen_checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "telemetry_readable": telemetry_readable,
        "all_expected_mpi_ranks_observed": (
            telemetry.get("observed_worker_rank_count")
            == int(expected_mpi_size)
        ),
        "profile_identity": evidence.get("profile") == expected_profile,
        "mpi_size_identity": evidence.get("mpi_size")
        == int(expected_mpi_size),
        "programmatic_configuration": (
            evidence.get("configured_programmatically") is True
        ),
        "raw_petsc_options_not_used": (
            evidence.get(
                "raw_petsc_options_used_for_iterative_configuration"
            )
            is False
        ),
        "assembled_reduced_operator": (
            evidence.get("assembled_reduced_operator") is True
            and evidence.get("matrix_free") is False
        ),
        "global_direct_factor_absent": (
            evidence.get("global_direct_factor_nnz") == 0
            and evidence.get("mumps_symbolic_or_numeric_created") is False
        ),
        "unpreconditioned_residual_reduction_ge_3_decades": (
            _finite_number(reduction) and float(reduction) <= 1.0e-3
        ),
        "terminal_explicit_reduced_residual_le_1e-3": (
            _finite_number(reduced) and float(reduced) <= 1.0e-3
        ),
        "full_recovered_true_residual_reported": _finite_number(
            evidence.get("full_recovered_true_residual")
        ),
        "no_process_tree_swap": (
            _finite_number(process_swap) and float(process_swap) == 0.0
        ),
        "no_worker_smaps_swap": (
            _finite_number(smaps_swap) and float(smaps_swap) == 0.0
        ),
        **physics_aware_checks,
        **topology_checks,
        "ordinary_default_unchanged": (
            evidence.get("ordinary_default_changed") is False
        ),
    }
    formal_pass = all(screen_checks.values())
    infrastructure_checks = {
        name: screen_checks[name]
        for name in (
            "process_completed",
            "not_terminated_for_memory",
            "not_terminated_for_timeout",
            "telemetry_readable",
            "all_expected_mpi_ranks_observed",
            "profile_identity",
            "mpi_size_identity",
        )
    }
    evidence_valid = all(infrastructure_checks.values()) and evidence.get(
        "summary_available"
    ) is True
    if formal_pass:
        status = "actual_factor_free_iterative_screen_pass"
        classification = "positive_factor_free_iterative_screen"
    elif terminated_for_memory:
        status = "controlled_stop_memory"
        classification = "resource_controlled_stop"
    elif terminated_for_timeout:
        status = "controlled_stop_timeout"
        classification = "resource_controlled_stop"
    elif evidence_valid and evidence.get("ksp_converged") is not True:
        status = "controlled_negative_iterative_nonconvergence"
        classification = "controlled_negative"
    elif evidence_valid:
        status = "controlled_negative_iterative_screen_failed"
        classification = "controlled_negative"
    else:
        status = "iterative_watchdog_infrastructure_failure"
        classification = "invalid_or_incomplete_evidence"
    full_residual = evidence.get("full_recovered_true_residual")
    return {
        "status": status,
        "classification": classification,
        "evidence_valid": evidence_valid,
        "formal_iterative_screen_pass": formal_pass,
        "official_physics_residual_pass": (
            _finite_number(full_residual)
            and float(full_residual) <= 1.0e-9
        ),
        "checks": screen_checks,
        "failures": [
            name for name, passed in screen_checks.items() if not passed
        ],
        "screen_thresholds": {
            "restart": 30,
            "maximum_iterations": 200,
            "minimum_unpreconditioned_residual_reduction_decades": 3.0,
            "terminal_explicit_reduced_relative_residual_max": 1.0e-3,
            "global_direct_factor_nnz_required": 0,
            "full_true_residual_official_gate": 1.0e-9,
            "swap_allowed": False,
        },
        "memory_research_targets_not_qualification_gates": {
            "minimum_useful_direct_gib": 5.0,
            "preferred_direct_gib": 4.5,
            "assembled_factor_free_research_target_gib": [4.0, 4.5],
        },
    }


def _resource_preflight(run_dir: Path) -> dict[str, Any]:
    effective = effective_memory_limit()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "effective_limit": effective,
        "artifact_filesystem_free_bytes": shutil.disk_usage(run_dir).free,
    }


def _run_parent(args: argparse.Namespace) -> int:
    source_before = _source_provenance(args)
    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise SystemExit(
            f"formal iterative screen requires {EXPECTED_BRANCH}; got {branch}"
        )
    source_before["branch"] = branch
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
        raise SystemExit("formal artifacts must stay on the WSL Linux filesystem")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir.resolve()
        if args.run_dir is not None
        else artifact_root
        / (
            f"h15_fixed_p5trace_p6interior_{args.profile}_"
            f"mpi{args.mpi_size}_{timestamp}"
        )
    )
    if str(run_dir).startswith("/mnt/"):
        raise SystemExit("formal run directories must stay on WSL Linux storage")
    run_dir.mkdir(parents=True, exist_ok=False)
    progress_path = run_dir / "solve" / "progress_3d.jsonl"
    stdout_path = run_dir / "worker_stdout.txt"
    worker_result_path = run_dir / "worker_result.json"
    timeline_path = run_dir / "memory_timeline.csv"
    record_path = (
        _exclusive_output_path(args.record)
        if args.record is not None
        else run_dir / "watchdog_summary.json"
    )

    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task035b_condensed_iterative",
        "--worker",
        "--execute-pde",
        "--profile",
        args.profile,
        "--mpi-size",
        str(args.mpi_size),
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
            readable = _finite_number(rss_mb) and _finite_number(swap_mb)
            telemetry_readable &= readable
            if readable:
                rss_gib = float(rss_mb) / 1024.0
                warning_triggered |= rss_gib >= float(args.warning_gib)
            else:
                rss_gib = None
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
            "schema_version": "task035b.condensed-iterative-worker.v1",
            "status": "worker_result_missing",
            "summary": None,
            "rank_failures": [],
        }
    )
    telemetry = _telemetry_summary(rows)
    evidence = _extract_solver_evidence(worker_result)
    screen = _classify_screen(
        evidence,
        telemetry,
        expected_profile=args.profile,
        expected_mpi_size=int(args.mpi_size),
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        telemetry_readable=telemetry_readable,
    )

    head_after = _git("rev-parse", "HEAD")
    branch_after = _git("branch", "--show-current")
    status_after = _git("status", "--porcelain", "--untracked-files=all")
    source_stable = (
        head_after == source_before["commit_sha"]
        and branch_after == branch
        and not status_after
    )
    source = {
        **source_before,
        "head_after_before_record_write": head_after,
        "branch_after_before_record_write": branch_after,
        "status_after_before_record_write": status_after,
        "stable_and_clean_after": source_stable,
    }
    screen["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        screen["formal_iterative_screen_pass"] = False
        screen["evidence_valid"] = False
        screen["status"] = "iterative_watchdog_infrastructure_failure"
        screen["classification"] = "invalid_or_incomplete_evidence"
        screen["failures"].append("source_stable_and_clean_after")

    record = {
        "schema_version": "task035b.condensed-iterative-watchdog.v1",
        "benchmark_id": "task035b_factor_free_assembled_condensed_iterative",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": screen["status"],
        "classification": screen["classification"],
        "ordinary_default_changed": False,
        "command": command,
        "request": {
            "geometry": "Task034 fixed rectangular block grating",
            "h_nm": 15.0,
            "trace_degree": 5,
            "interior_degree": 6,
            "profile": args.profile,
            "mpi_size": int(args.mpi_size),
            "programmatic_profile_only": True,
            "raw_petsc_options_accepted": False,
            "assembled_reduced_operator": True,
            "matrix_free": False,
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
        "solver_evidence": evidence,
        "iterative_screen": screen,
        "qualification": {
            "evidence_valid": screen["evidence_valid"],
            "formal_iterative_screen_pass": screen[
                "formal_iterative_screen_pass"
            ],
            "official_physics_residual_pass": screen[
                "official_physics_residual_pass"
            ],
            "controlled_negative_preserved": (
                screen["classification"] == "controlled_negative"
            ),
        },
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
                "status": screen["status"],
                "classification": screen["classification"],
                "formal_iterative_screen_pass": screen[
                    "formal_iterative_screen_pass"
                ],
                "record": _path_from_root(record_path),
                "failures": screen["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if screen["evidence_valid"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        return _worker(args)
    if not args.execute_pde:
        print(
            json.dumps(
                _dry_run_plan(args),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
