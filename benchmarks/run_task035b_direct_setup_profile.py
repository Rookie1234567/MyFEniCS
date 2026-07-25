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
DIRECT_SETUP_TYPED_PETSC_OPTIONS = {
    "pc_factor_mat_solver_type": "mumps",
    "mat_mumps_icntl_14": 100,
}


def _raw_petsc_option_provenance() -> dict[str, Any]:
    """Audit PETSc's live raw option sources before typed solver setup."""

    from petsc4py import PETSc

    environment_value = os.environ.get("PETSC_OPTIONS")
    options = {
        str(key): str(value)
        for key, value in PETSc.Options().getAll().items()
    }
    canonical_options = json.dumps(
        options,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    possible_rc_files = tuple(
        dict.fromkeys(
            (
                str((ROOT / ".petscrc").resolve()),
                str((Path.cwd() / ".petscrc").resolve()),
                str((Path.home() / ".petscrc").resolve()),
            )
        )
    )
    environment_nonempty = bool(
        environment_value is not None and environment_value.strip()
    )
    return {
        "schema_version": "task035b.raw-petsc-option-provenance.v1",
        "checked_before_typed_solver_configuration": True,
        "PETSC_OPTIONS_present": environment_value is not None,
        "PETSC_OPTIONS_nonempty": environment_nonempty,
        "PETSC_OPTIONS_sha256": (
            None
            if environment_value is None
            else hashlib.sha256(
                environment_value.encode("utf-8")
            ).hexdigest()
        ),
        "live_options_database_entry_count": len(options),
        "live_options_database_keys": sorted(options),
        "live_options_database_sha256": hashlib.sha256(
            canonical_options
        ).hexdigest(),
        "possible_petscrc_sources": [
            {
                "path": path,
                "exists": Path(path).is_file(),
            }
            for path in possible_rc_files
        ],
        "raw_options_absent": not environment_nonempty and not options,
        "raw_option_values_recorded": False,
    }


def _typed_direct_petsc_option_audit(
    cfg,
) -> dict[str, Any]:
    """Require the research runner's exact direct-MUMPS allowlist."""

    configured = dict(cfg.petsc_extra_options)
    expected = dict(DIRECT_SETUP_TYPED_PETSC_OPTIONS)
    return {
        "schema_version": "task035b.typed-direct-petsc-options.v1",
        "provenance": "runner_constant_allowlist_not_raw_environment_or_cli",
        "configured_options": configured,
        "allowed_options": expected,
        "exact_allowlist_match": configured == expected,
        "direct_solver_profile": cfg.petsc_direct_solver_profile,
        "condensed_iterative_profile": (
            cfg.stage4_condensed_iterative_profile
        ),
        "direct_profile_is_default": (
            cfg.petsc_direct_solver_profile == "default"
        ),
        "iterative_profile_absent": (
            cfg.stage4_condensed_iterative_profile is None
        ),
        "pass": (
            configured == expected
            and cfg.petsc_direct_solver_profile == "default"
            and cfg.stage4_condensed_iterative_profile is None
        ),
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
        "--canonical-orientation-class-reuse",
        action="store_true",
        help=(
            "explicitly reuse canonical high-interior condensed classes "
            "and derive qualified oriented trace classes"
        ),
    )
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
            "persistent_fixed_trace_element_cache": True,
            "affine_isotropic_reference_tensor": True,
            "canonical_orientation_class_reuse": bool(
                args.canonical_orientation_class_reuse
            ),
            "petsc_direct_factor_event_timing": True,
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

    raw_petsc_options = _raw_petsc_option_provenance()
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
        "raw_petsc_options_absent_before_worker": (
            raw_petsc_options["raw_options_absent"] is True
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
        "raw_petsc_option_provenance": raw_petsc_options,
    }


def _direct_config(
    *,
    source_sha: str,
    cache_directory: Path,
    cache_state: str,
    h_nm: float,
    canonical_orientation_class_reuse: bool = False,
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
        stage4_petsc_factor_event_timing=True,
        stage4_fast_fixed_trace_setup=True,
        stage4_persistent_fixed_trace_element_cache=True,
        stage4_affine_isotropic_reference_tensor=True,
        stage4_canonical_orientation_class_reuse=bool(
            canonical_orientation_class_reuse
        ),
        stage4_condensed_bulk_cell_insertion=False,
        stage4_condensed_cache_directory=str(cache_directory.resolve()),
        stage4_condensed_cache_source_sha=source_sha,
        stage4_condensed_cache_mode=CACHE_MODES[cache_state],
        stage4_condensed_persistent_dtn_surface_cache=True,
        stage4_preserve_structured_input_partition=True,
        petsc_direct_solver_profile="default",
        petsc_extra_options=dict(DIRECT_SETUP_TYPED_PETSC_OPTIONS),
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
    local_raw_petsc_options: dict[str, Any] | None = None
    local_typed_petsc_options: dict[str, Any] | None = None
    try:
        if int(comm.size) != int(args.mpi_size):
            raise RuntimeError(
                f"worker MPI size {comm.size} differs from {args.mpi_size}"
            )
        local_raw_petsc_options = _raw_petsc_option_provenance()
        preliminary_raw_audits = comm.allgather(
            local_raw_petsc_options
        )
        if (
            not all(
                audit.get("raw_options_absent") is True
                for audit in preliminary_raw_audits
            )
            or not all(
                audit == preliminary_raw_audits[0]
                for audit in preliminary_raw_audits[1:]
            )
        ):
            raise RuntimeError(
                "raw PETSc options are present or differ across ranks "
                "before typed direct setup"
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
            canonical_orientation_class_reuse=(
                args.canonical_orientation_class_reuse
            ),
        )
        local_typed_petsc_options = _typed_direct_petsc_option_audit(cfg)
        preliminary_typed_audits = comm.allgather(
            local_typed_petsc_options
        )
        if (
            not all(
                audit.get("pass") is True
                for audit in preliminary_typed_audits
            )
            or not all(
                audit == preliminary_typed_audits[0]
                for audit in preliminary_typed_audits[1:]
            )
        ):
            raise RuntimeError(
                "typed direct PETSc configuration differs from the "
                "runner allowlist or across ranks"
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
    raw_petsc_rank_audits = comm.allgather(local_raw_petsc_options)
    typed_petsc_rank_audits = comm.allgather(local_typed_petsc_options)
    petsc_option_provenance = {
        "schema_version": (
            "task035b.collective-petsc-option-provenance.v1"
        ),
        "rank_count": int(comm.size),
        "raw_rank_audits": raw_petsc_rank_audits,
        "typed_rank_audits": typed_petsc_rank_audits,
        "raw_audit_present_on_all_ranks": all(
            isinstance(audit, dict)
            for audit in raw_petsc_rank_audits
        ),
        "typed_audit_present_on_all_ranks": all(
            isinstance(audit, dict)
            for audit in typed_petsc_rank_audits
        ),
        "raw_options_absent_on_all_ranks": all(
            isinstance(audit, dict)
            and audit.get("raw_options_absent") is True
            for audit in raw_petsc_rank_audits
        ),
        "typed_allowlist_pass_on_all_ranks": all(
            isinstance(audit, dict)
            and audit.get("pass") is True
            for audit in typed_petsc_rank_audits
        ),
        "rank_audits_identical": (
            all(
                audit == raw_petsc_rank_audits[0]
                for audit in raw_petsc_rank_audits[1:]
            )
            and all(
                audit == typed_petsc_rank_audits[0]
                for audit in typed_petsc_rank_audits[1:]
            )
        ),
    }
    petsc_option_provenance["pass"] = bool(
        petsc_option_provenance["raw_audit_present_on_all_ranks"]
        and petsc_option_provenance["typed_audit_present_on_all_ranks"]
        and petsc_option_provenance["raw_options_absent_on_all_ranks"]
        and petsc_option_provenance[
            "typed_allowlist_pass_on_all_ranks"
        ]
        and petsc_option_provenance["rank_audits_identical"]
    )
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
            "canonical_orientation_class_reuse_requested": bool(
                args.canonical_orientation_class_reuse
            ),
            "petsc_option_provenance": petsc_option_provenance,
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


DTN_NONOVERLAPPING_TIMING_COMPONENTS = (
    (
        "base_condensed_matrix_assembly",
        "stage4_dtn_base_matrix_assembly_seconds",
    ),
    ("base_rhs_assembly", "stage4_dtn_base_rhs_assembly_seconds"),
    ("augmented_block_copy", "stage4_dtn_augmented_block_copy_seconds"),
    (
        "incident_source_vector",
        "stage4_dtn_incident_source_vector_seconds",
    ),
    (
        "surface_form_and_cache_setup",
        "stage4_dtn_surface_form_and_cache_setup_seconds",
    ),
    ("modal_loop", "stage4_dtn_modal_loop_seconds"),
    (
        "augmented_matrix_finalize",
        "stage4_dtn_augmented_matrix_finalize_seconds",
    ),
    (
        "cell_interior_rhs_prepare_and_cache_release",
        "stage4_dtn_cell_interior_rhs_prepare_and_cache_release_seconds",
    ),
    (
        "warm_persistent_cache_heap_trim",
        "stage4_dtn_warm_persistent_cache_heap_trim_seconds",
    ),
    ("linear_solve_wrapper", "stage4_dtn_linear_solve_seconds"),
    (
        "cell_static_condensation_recovery",
        "stage4_dtn_cell_static_condensation_recovery_seconds",
    ),
    (
        "matrix_free_full_explicit_residual",
        "stage4_dtn_matrix_free_full_residual_seconds",
    ),
    (
        "solution_backsubstitution",
        "stage4_dtn_solution_backsubstitution_seconds",
    ),
)


def _dtn_nonoverlapping_timing_ledger(
    summary: dict[str, Any],
    outer: dict[str, Any],
) -> dict[str, Any]:
    """Derive a nonoverlapping DtN wall-time ledger.

    The solver exposes both sequential top-level regions and useful nested
    details.  The latter must not be added to the former.  This profiler-owned
    ledger names the sequential regions explicitly, retains the nested values
    as diagnostics, and leaves the small uninstrumented tail visible instead
    of silently assigning it to setup or MUMPS.
    """

    outer_seconds = _number(
        outer,
        "stage4_dtn_port_assembly_and_solve",
    )
    components = {
        name: _number(summary, source_key)
        for name, source_key in DTN_NONOVERLAPPING_TIMING_COMPONENTS
    }
    missing = [
        name for name, value in components.items() if value is None
    ]
    component_sum = (
        None
        if missing
        else float(sum(float(value) for value in components.values()))
    )
    unattributed = (
        None
        if outer_seconds is None or component_sum is None
        else float(outer_seconds - component_sum)
    )
    ksp_setup = _number(summary, "stage4_dtn_ksp_setup_seconds")
    ksp_solve = _number(summary, "stage4_dtn_ksp_solve_seconds")
    linear_wrapper = components["linear_solve_wrapper"]
    linear_wrapper_overhead = (
        None
        if (
            linear_wrapper is None
            or ksp_setup is None
            or ksp_solve is None
        )
        else float(linear_wrapper - ksp_setup - ksp_solve)
    )
    non_ksp_outer = (
        None
        if (
            outer_seconds is None
            or ksp_setup is None
            or ksp_solve is None
        )
        else float(outer_seconds - ksp_setup - ksp_solve)
    )
    non_ksp_attributed = (
        None
        if (
            component_sum is None
            or linear_wrapper is None
            or linear_wrapper_overhead is None
        )
        else float(
            component_sum
            - linear_wrapper
            + linear_wrapper_overhead
        )
    )
    non_ksp_unattributed = (
        None
        if non_ksp_outer is None or non_ksp_attributed is None
        else float(non_ksp_outer - non_ksp_attributed)
    )
    return {
        "schema_version": "task035b.dtn-nonoverlapping-timing-ledger.v1",
        "provenance": (
            "derived only by the explicit Task035b direct setup profiler "
            "from sequential core wall timers"
        ),
        "outer_seconds": outer_seconds,
        "component_order": [
            name for name, _ in DTN_NONOVERLAPPING_TIMING_COMPONENTS
        ],
        "components_seconds": components,
        "missing_components": missing,
        "all_required_components_present": not missing,
        "attributed_component_sum_seconds": component_sum,
        "unattributed_remainder_seconds": unattributed,
        "unattributed_fraction_of_outer": (
            None
            if (
                unattributed is None
                or outer_seconds is None
                or outer_seconds <= 0.0
            )
            else float(unattributed / outer_seconds)
        ),
        "non_ksp_seconds": {
            "outer_minus_ksp_setup_and_backsolve": non_ksp_outer,
            "attributed_components_including_linear_wrapper_overhead": (
                non_ksp_attributed
            ),
            "unattributed_remainder": non_ksp_unattributed,
        },
        "linear_solve_nested_seconds": {
            "ksp_setup": ksp_setup,
            "ksp_backsolve": ksp_solve,
            "wrapper_overhead": linear_wrapper_overhead,
            "parent_component": "linear_solve_wrapper",
        },
        "surface_setup_nested_seconds": {
            "reduced_operator_identity": _number(
                summary,
                "stage4_dtn_reduced_operator_identity_seconds",
            ),
            "parent_component": "surface_form_and_cache_setup",
        },
        "modal_loop_nested_seconds": {
            "modal_vector_assembly": _number(
                summary,
                "stage4_dtn_modal_vector_assembly_seconds",
            ),
            "persistent_reduced_modal_bundle_restore": _number(
                summary,
                "stage4_dtn_persistent_reduced_modal_bundle_restore_seconds",
            ),
            "persistent_reduced_modal_bundle_restore_is_subset_of_"
            "modal_vector_assembly": True,
            "persistent_full_vector_restore": _number(
                summary,
                "stage4_dtn_persistent_vector_restore_seconds",
            ),
            "modal_block_insertion": _number(
                summary,
                "stage4_dtn_modal_block_insert_seconds",
            ),
            "parent_component": "modal_loop",
        },
        "nested_values_must_not_be_added_to_top_level_components": True,
        "ordinary_default_changed": False,
    }


def _dtn_nonoverlapping_timing_ledger_checks(
    ledger: dict[str, Any],
) -> dict[str, bool]:
    """Independently recompute the profiler-owned ledger closure."""

    expected_order = [
        name for name, _ in DTN_NONOVERLAPPING_TIMING_COMPONENTS
    ]
    components = ledger.get("components_seconds")
    components = components if isinstance(components, dict) else {}

    def _finite(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )

    component_inventory = (
        ledger.get("component_order") == expected_order
        and list(components) == expected_order
    )
    component_values = (
        component_inventory
        and all(
            _finite(components.get(name))
            and float(components[name]) >= 0.0
            for name in expected_order
        )
    )
    recomputed_sum = (
        sum(float(components[name]) for name in expected_order)
        if component_values
        else None
    )
    declared_sum = ledger.get("attributed_component_sum_seconds")
    outer_seconds = ledger.get("outer_seconds")
    remainder = ledger.get("unattributed_remainder_seconds")
    closure_tolerance = (
        None
        if not _finite(outer_seconds)
        else max(0.1, 0.01 * float(outer_seconds))
    )
    sum_matches = bool(
        recomputed_sum is not None
        and _finite(declared_sum)
        and math.isclose(
            float(declared_sum),
            recomputed_sum,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )
    remainder_matches = bool(
        sum_matches
        and _finite(outer_seconds)
        and _finite(remainder)
        and math.isclose(
            float(remainder),
            float(outer_seconds) - recomputed_sum,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )
    remainder_is_small = bool(
        remainder_matches
        and closure_tolerance is not None
        and abs(float(remainder)) <= closure_tolerance
    )

    linear = ledger.get("linear_solve_nested_seconds")
    linear = linear if isinstance(linear, dict) else {}
    non_ksp = ledger.get("non_ksp_seconds")
    non_ksp = non_ksp if isinstance(non_ksp, dict) else {}
    linear_nested_values = [
        linear.get("ksp_setup"),
        linear.get("ksp_backsolve"),
        linear.get("wrapper_overhead"),
    ]
    linear_nested_closes = bool(
        all(_finite(value) for value in linear_nested_values)
        and _finite(components.get("linear_solve_wrapper"))
        and math.isclose(
            sum(float(value) for value in linear_nested_values),
            float(components["linear_solve_wrapper"]),
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )
    non_ksp_values = [
        non_ksp.get("outer_minus_ksp_setup_and_backsolve"),
        non_ksp.get(
            "attributed_components_including_linear_wrapper_overhead"
        ),
        non_ksp.get("unattributed_remainder"),
    ]
    non_ksp_closes = bool(
        all(_finite(value) for value in non_ksp_values)
        and math.isclose(
            float(non_ksp_values[0]),
            float(non_ksp_values[1]) + float(non_ksp_values[2]),
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )

    surface = ledger.get("surface_setup_nested_seconds")
    surface = surface if isinstance(surface, dict) else {}
    surface_nested_within_parent = bool(
        _finite(surface.get("reduced_operator_identity"))
        and _finite(components.get("surface_form_and_cache_setup"))
        and 0.0
        <= float(surface["reduced_operator_identity"])
        <= float(components["surface_form_and_cache_setup"]) + 1.0e-12
    )
    modal = ledger.get("modal_loop_nested_seconds")
    modal = modal if isinstance(modal, dict) else {}
    modal_nonoverlapping_children = [
        modal.get("modal_vector_assembly"),
        modal.get("persistent_full_vector_restore"),
        modal.get("modal_block_insertion"),
    ]
    modal_nested_within_parent = bool(
        all(_finite(value) for value in modal_nonoverlapping_children)
        and _finite(components.get("modal_loop"))
        and sum(float(value) for value in modal_nonoverlapping_children)
        <= float(components["modal_loop"]) + 1.0e-12
        and modal.get(
            "persistent_reduced_modal_bundle_restore_is_subset_of_"
            "modal_vector_assembly"
        )
        is True
    )
    return {
        "dtn_timing_ledger_schema": (
            ledger.get("schema_version")
            == "task035b.dtn-nonoverlapping-timing-ledger.v1"
            and ledger.get("ordinary_default_changed") is False
        ),
        "dtn_timing_component_inventory_exact": component_inventory,
        "dtn_timing_all_required_components_present": (
            ledger.get("all_required_components_present") is True
            and ledger.get("missing_components") == []
        ),
        "dtn_timing_component_values_finite_nonnegative": component_values,
        "dtn_timing_component_sum_independently_verified": sum_matches,
        "dtn_timing_unattributed_remainder_independently_verified": (
            remainder_matches
        ),
        "dtn_timing_unattributed_remainder_within_one_percent_or_0p1s": (
            remainder_is_small
        ),
        "dtn_timing_linear_nested_closure": linear_nested_closes,
        "dtn_timing_non_ksp_closure": non_ksp_closes,
        "dtn_timing_surface_nested_within_parent": (
            surface_nested_within_parent
        ),
        "dtn_timing_modal_nested_within_parent": (
            modal_nested_within_parent
        ),
        "dtn_timing_nested_overlap_disclosed": (
            ledger.get(
                "nested_values_must_not_be_added_to_top_level_components"
            )
            is True
        ),
    }


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
    petsc_option_provenance = (
        worker_result.get("petsc_option_provenance") or {}
    )
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
    canonical_orientation_request = (
        summary.get(
            "stage4_canonical_orientation_class_reuse_request"
        )
        or {}
    )
    petsc_factor_event_timing = (
        summary.get("stage4_dtn_petsc_factor_event_timing") or {}
    )
    matrix = summary.get("matrix_stats") or {}
    config = summary.get("config") or {}
    factor = summary.get("stage4_dtn_factor_inventory") or {}
    function_space_audit = summary.get("function_space_setup_audit") or {}
    fixed_trace_element_cache = (
        function_space_audit.get(
            "persistent_fixed_trace_element_cache"
        )
        or {}
    )

    ksp_setup = _number(summary, "stage4_dtn_ksp_setup_seconds")
    ksp_solve = _number(summary, "stage4_dtn_ksp_solve_seconds")
    dtn_outer = _number(outer, "stage4_dtn_port_assembly_and_solve")
    dtn_timing_ledger = _dtn_nonoverlapping_timing_ledger(
        summary,
        outer,
    )
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
            "persistent_fixed_trace_element_cache": config.get(
                "stage4_persistent_fixed_trace_element_cache"
            ),
            "affine_isotropic_reference_tensor": config.get(
                "stage4_affine_isotropic_reference_tensor"
            ),
            "canonical_orientation_class_reuse": config.get(
                "stage4_canonical_orientation_class_reuse",
                False,
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
            "preserve_structured_input_partition": config.get(
                "stage4_preserve_structured_input_partition"
            ),
            "direct_solver_profile": config.get(
                "petsc_direct_solver_profile"
            ),
            "condensed_iterative_profile": config.get(
                "stage4_condensed_iterative_profile"
            ),
            "petsc_factor_event_timing": config.get(
                "stage4_petsc_factor_event_timing"
            ),
            "typed_direct_petsc_options": config.get(
                "petsc_extra_options"
            ),
            "ordinary_default_changed": config.get(
                "ordinary_default_changed",
                False,
            ),
        },
        "petsc_option_provenance": petsc_option_provenance,
        "cache_audit": {
            "fixed_trace_element": fixed_trace_element_cache,
            "raw_tensor": raw_cache,
            "condensed_class": condensed_cache,
            "dtn_surface_vector": dtn_surface_cache,
        },
        "canonical_orientation_class_reuse": {
            "request": canonical_orientation_request,
            "core": cell.get(
                "canonical_orientation_class_reuse",
                {},
            ),
        },
        "petsc_factor_event_timing": petsc_factor_event_timing,
        "cell_static_raw_tensor_evaluations": cell.get(
            "raw_tensor_kernel_evaluation_count"
        ),
        "native_object_ledger": cell.get("native_object_ledger"),
        "recovery_cache_lifecycle": cell.get(
            "recovery_cache_lifecycle"
        ),
        "dtn_nonoverlapping_timing_ledger": dtn_timing_ledger,
        "dtn_nonoverlapping_timing_ledger_checks": (
            _dtn_nonoverlapping_timing_ledger_checks(
                dtn_timing_ledger
            )
        ),
        "timing_coverage": {
            "nonoverlapping_outer_stages": (
                "timings_seconds fields are mutually staged by the common "
                "case flow"
            ),
            "nonoverlapping_dtn_ledger": (
                "dtn_nonoverlapping_timing_ledger names every sequential "
                "top-level region, keeps an explicit uninstrumented "
                "remainder, and independently checks closure"
            ),
            "granular_condensation_fields": (
                "granular fields overlap the outer DtN stage and must not be "
                "summed with it"
            ),
            "mumps_symbolic_numeric": (
                "explicit direct-profile PETSc built-in event deltas; "
                "missing or inconsistent MatLUFactorSym/MatLUFactorNum "
                "events fail the formal profile instead of being inferred"
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
                "persistent_element_cache_read": _number(
                    fixed_trace_element_cache,
                    "read_seconds_max",
                ),
                "persistent_element_reconstruct": _number(
                    fixed_trace_element_cache,
                    "reconstruct_seconds_max",
                ),
                "persistent_element_cold_build": _number(
                    fixed_trace_element_cache,
                    "build_seconds_max",
                ),
                "persistent_element_cache_write": _number(
                    fixed_trace_element_cache,
                    "write_seconds_max",
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
                "nonoverlapping_ledger": dtn_timing_ledger,
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


def _petsc_factor_event_timing_formal_checks(
    evidence: dict[str, Any],
    *,
    expected_mpi_size: int,
) -> dict[str, bool]:
    """Independently validate the PETSc symbolic/numeric split.

    The profiler does not trust the core's ``split_available`` flag alone.
    It rechecks every rank packet, the collective content hash, event counts,
    finite time bounds, and the extracted common-summary maxima.
    """

    config = evidence.get("configuration_identity") or {}
    audit = evidence.get("petsc_factor_event_timing") or {}
    timings = evidence.get("timings_seconds") or {}
    mumps = timings.get("mumps") or {}
    event_names = {
        "symbolic": "MatLUFactorSym",
        "numeric": "MatLUFactorNum",
        "pc_setup": "PCSetUp",
    }
    packets = audit.get("per_rank")
    packets = packets if isinstance(packets, list) else []

    def _finite_nonnegative(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0.0
        )

    def _close(left: Any, right: Any) -> bool:
        if not _finite_nonnegative(left) or not _finite_nonnegative(
            right
        ):
            return False
        return math.isclose(
            float(left),
            float(right),
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        )

    packet_structure_valid = (
        len(packets) == int(expected_mpi_size)
        and [
            packet.get("comm_rank")
            if isinstance(packet, dict)
            else None
            for packet in packets
        ]
        == list(range(int(expected_mpi_size)))
        and all(
            isinstance(packet, dict)
            and packet.get("comm_size") == int(expected_mpi_size)
            and packet.get("world_rank") == index
            and packet.get("factor_solver_type") == "mumps"
            and packet.get("logging_active_after_begin") is True
            and not packet.get("errors")
            and _finite_nonnegative(packet.get("setup_wall_seconds"))
            for index, packet in enumerate(packets)
        )
    )
    counts_by_event: dict[str, list[int]] = {
        role: [] for role in event_names
    }
    seconds_by_event: dict[str, list[float]] = {
        role: [] for role in event_names
    }
    event_values_valid = packet_structure_valid
    nested_time_bounds_valid = packet_structure_valid
    for packet in packets:
        if not isinstance(packet, dict):
            event_values_valid = False
            nested_time_bounds_valid = False
            continue
        packet_events = packet.get("events")
        if not isinstance(packet_events, dict):
            event_values_valid = False
            nested_time_bounds_valid = False
            continue
        local_seconds: dict[str, float] = {}
        for role, event_name in event_names.items():
            event = packet_events.get(role)
            if not isinstance(event, dict):
                event_values_valid = False
                continue
            count = event.get("count")
            seconds = event.get("seconds")
            if (
                event.get("event_name") != event_name
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count <= 0
                or not _finite_nonnegative(seconds)
            ):
                event_values_valid = False
                continue
            counts_by_event[role].append(int(count))
            seconds_by_event[role].append(float(seconds))
            local_seconds[role] = float(seconds)
        if set(local_seconds) != set(event_names):
            nested_time_bounds_valid = False
            continue
        symbolic_numeric = (
            local_seconds["symbolic"] + local_seconds["numeric"]
        )
        pc_setup = local_seconds["pc_setup"]
        wall = float(packet["setup_wall_seconds"])
        tolerance = max(
            1.0e-12,
            1.0e-8 * max(1.0, symbolic_numeric, pc_setup, wall),
        )
        nested_time_bounds_valid &= (
            symbolic_numeric <= pc_setup + tolerance
            and pc_setup <= wall + tolerance
        )

    counts_positive_consistent = (
        event_values_valid
        and all(
            len(counts) == int(expected_mpi_size)
            and len(set(counts)) == 1
            for counts in counts_by_event.values()
        )
        and counts_by_event["symbolic"]
        == counts_by_event["numeric"]
    )
    expected_hash = None
    if packets:
        try:
            expected_hash = hashlib.sha256(
                json.dumps(
                    packets,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        except (TypeError, ValueError):
            expected_hash = None
    collective_hash_valid = (
        isinstance(expected_hash, str)
        and audit.get("collective_rank_payload_sha256")
        == expected_hash
    )
    ordered_world_ranks = [
        packet.get("world_rank") if isinstance(packet, dict) else None
        for packet in packets
    ]
    rank_identity_valid = (
        packet_structure_valid
        and audit.get("rank_count") == int(expected_mpi_size)
        and audit.get("ordered_world_ranks")
        == ordered_world_ranks
    )

    event_summary_valid = event_values_valid
    audit_event_summaries = audit.get("events")
    if not isinstance(audit_event_summaries, dict):
        event_summary_valid = False
    else:
        for role, event_name in event_names.items():
            summary = audit_event_summaries.get(role)
            counts = counts_by_event[role]
            seconds = seconds_by_event[role]
            if (
                not isinstance(summary, dict)
                or summary.get("event_name") != event_name
                or summary.get("count_per_rank") != counts
                or summary.get("seconds_per_rank") != seconds
                or summary.get("count_min")
                != (min(counts) if counts else None)
                or summary.get("count_max")
                != (max(counts) if counts else None)
                or summary.get("count_sum")
                != (sum(counts) if counts else None)
                or summary.get("count_consistent_across_ranks")
                is not True
                or summary.get("count_positive_on_all_ranks") is not True
                or summary.get(
                    "seconds_finite_nonnegative_on_all_ranks"
                )
                is not True
                or (
                    seconds
                    and not _close(
                        summary.get("seconds_min"),
                        min(seconds),
                    )
                )
                or (
                    seconds
                    and not _close(
                        summary.get("seconds_max"),
                        max(seconds),
                    )
                )
                or (
                    seconds
                    and not _close(
                        summary.get("seconds_sum"),
                        sum(seconds),
                    )
                )
            ):
                event_summary_valid = False

    symbolic_max = (
        max(seconds_by_event["symbolic"])
        if seconds_by_event["symbolic"]
        else None
    )
    numeric_max = (
        max(seconds_by_event["numeric"])
        if seconds_by_event["numeric"]
        else None
    )
    pc_setup_max = (
        max(seconds_by_event["pc_setup"])
        if seconds_by_event["pc_setup"]
        else None
    )
    summary_maxima_valid = (
        _close(audit.get("symbolic_seconds_max"), symbolic_max)
        and _close(audit.get("numeric_seconds_max"), numeric_max)
        and _close(audit.get("pc_setup_seconds_max"), pc_setup_max)
        and _close(mumps.get("symbolic"), symbolic_max)
        and _close(mumps.get("numeric"), numeric_max)
    )
    combined_setup = mumps.get(
        "symbolic_numeric_combined_ksp_setup"
    )
    combined_bounds_valid = (
        _finite_nonnegative(combined_setup)
        and _finite_nonnegative(pc_setup_max)
        and float(pc_setup_max)
        <= float(combined_setup)
        + max(1.0e-12, 1.0e-8 * max(1.0, float(combined_setup)))
    )

    expected_core_checks = {
        "requested_direct_only",
        "logging_active_after_begin_on_all_ranks",
        "no_snapshot_errors_on_any_rank",
        "communicator_rank_identity_valid",
        "event_values_finite_nonnegative_on_all_ranks",
        "event_counts_consistent_across_ranks",
        "event_counts_positive_on_all_ranks",
        "symbolic_numeric_counts_match",
        "symbolic_plus_numeric_within_pc_setup_on_all_ranks",
        "pc_setup_within_setup_wall_on_all_ranks",
    }
    core_checks = audit.get("checks")
    core_checks_valid = (
        isinstance(core_checks, dict)
        and expected_core_checks.issubset(core_checks)
        and all(value is True for value in core_checks.values())
    )
    return {
        "petsc_factor_event_timing_opt_in": (
            config.get("petsc_factor_event_timing") is True
        ),
        "petsc_factor_event_timing_schema_and_status": (
            audit.get("schema_version")
            == "task035b.petsc-direct-factor-event-timing.v1"
            and audit.get("requested") is True
            and audit.get("enabled") is True
            and audit.get("direct_only") is True
            and audit.get("iterative_profile") is None
            and audit.get("factor_solver_type") == "mumps"
            and audit.get("status")
            == "measured_symbolic_numeric_split"
            and audit.get("split_available") is True
            and audit.get("event_names") == event_names
            and audit.get("ordinary_default_changed") is False
        ),
        "petsc_factor_event_rank_identity": rank_identity_valid,
        "petsc_factor_event_collective_hash": collective_hash_valid,
        "petsc_factor_event_values_finite_nonnegative": (
            event_values_valid
        ),
        "petsc_factor_event_counts_positive_consistent": (
            counts_positive_consistent
        ),
        "petsc_factor_event_nested_time_bounds": (
            nested_time_bounds_valid
        ),
        "petsc_factor_event_summary_matches_rank_packets": (
            event_summary_valid and summary_maxima_valid
        ),
        "petsc_factor_event_within_combined_ksp_setup": (
            combined_bounds_valid
        ),
        "petsc_factor_event_core_checks_all_true": core_checks_valid,
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
    expected_canonical_orientation_class_reuse: bool = False,
) -> dict[str, Any]:
    config = evidence.get("configuration_identity") or {}
    cache = evidence.get("cache_audit") or {}
    fixed_trace_element_cache = cache.get("fixed_trace_element") or {}
    raw_cache = cache.get("raw_tensor") or {}
    condensed_cache = cache.get("condensed_class") or {}
    dtn_surface_cache = cache.get("dtn_surface_vector") or {}
    canonical_orientation = (
        evidence.get("canonical_orientation_class_reuse") or {}
    )
    petsc_option_provenance = (
        evidence.get("petsc_option_provenance") or {}
    )
    canonical_request = canonical_orientation.get("request") or {}
    canonical_core = canonical_orientation.get("core") or {}
    expected_canonical_orientation_class_reuse = bool(
        expected_canonical_orientation_class_reuse
    )
    factor_event_checks = _petsc_factor_event_timing_formal_checks(
        evidence,
        expected_mpi_size=int(expected_mpi_size),
    )
    dtn_timing_ledger_checks = (
        _dtn_nonoverlapping_timing_ledger_checks(
            evidence.get("dtn_nonoverlapping_timing_ledger") or {}
        )
    )
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
        "fixed_trace_element_cache_enabled": (
            fixed_trace_element_cache.get("schema_version")
            == "task035b.fixed-trace-custom-element-cache.v1"
            and fixed_trace_element_cache.get("ordinary_default_changed")
            is False
            and fixed_trace_element_cache.get("serialization")
            == "json_plus_npz_allow_pickle_false"
            and fixed_trace_element_cache.get("identity", {}).get(
                "source_sha"
            )
            == source_sha
        ),
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
            fixed_trace_element_cache.get("mode")
            == CACHE_MODES[cache_state]
            and raw_cache.get("mode") == CACHE_MODES[cache_state]
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
        "cold_fixed_trace_element_cache_wrote_entry": (
            cache_state != "cold"
            or (
                fixed_trace_element_cache.get("status")
                == "persistent_fixed_trace_element_cache_cold_write"
                and fixed_trace_element_cache.get(
                    "cache_miss_on_all_ranks"
                )
                is True
                and isinstance(
                    fixed_trace_element_cache.get("payload_sha256"),
                    str,
                )
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
        "warm_fixed_trace_element_cache_hit_without_rederivation": (
            cache_state != "warm"
            or (
                fixed_trace_element_cache.get("status")
                == "persistent_fixed_trace_element_cache_hit"
                and fixed_trace_element_cache.get(
                    "cache_hit_on_all_ranks"
                )
                is True
                and fixed_trace_element_cache.get("build_seconds_max")
                == 0.0
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
    physical_observables = {
        name: evidence.get(name)
        for name in (
            "R00_total",
            "R_total",
            "T_total",
            "A_closure",
        )
    }
    physical_observables_finite = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in physical_observables.values()
    )
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
        "summary_mpi_size_identity": (
            evidence.get("mpi_size") == int(expected_mpi_size)
        ),
        "source_stable_and_clean_after": source_stable_and_clean_after,
        "physical_full_run_completed": (
            evidence.get("case_status") == "completed"
            and evidence.get("official_result") is True
            and evidence.get("diagnostic_only") is False
            and evidence.get("postprocess_skipped") is False
        ),
        "physical_R00_R_T_Aclosure_finite": (
            physical_observables_finite
        ),
        "direct_mumps_identity": (
            evidence.get("linear_solve_method") == "direct_lu"
            and evidence.get("actual_pc_factor_solver_type") == "mumps"
        ),
        "raw_petsc_options_absent_on_all_worker_ranks": (
            petsc_option_provenance.get("schema_version")
            == "task035b.collective-petsc-option-provenance.v1"
            and petsc_option_provenance.get("rank_count")
            == int(expected_mpi_size)
            and petsc_option_provenance.get(
                "raw_audit_present_on_all_ranks"
            )
            is True
            and petsc_option_provenance.get(
                "raw_options_absent_on_all_ranks"
            )
            is True
            and petsc_option_provenance.get(
                "rank_audits_identical"
            )
            is True
        ),
        "typed_direct_petsc_options_exact_allowlist": (
            petsc_option_provenance.get(
                "typed_audit_present_on_all_ranks"
            )
            is True
            and petsc_option_provenance.get(
                "typed_allowlist_pass_on_all_ranks"
            )
            is True
            and petsc_option_provenance.get("pass") is True
            and config.get("direct_solver_profile") == "default"
            and config.get("condensed_iterative_profile") is None
            and config.get("typed_direct_petsc_options")
            == DIRECT_SETUP_TYPED_PETSC_OPTIONS
        ),
        "solve_converged": evidence.get("ksp_converged") is True,
        "full_true_residual_le_1e-9": (
            isinstance(residual, (int, float))
            and not isinstance(residual, bool)
            and float(residual) <= 1.0e-9
        ),
        "fast_setup_opt_in": config.get("fast_fixed_trace_setup") is True,
        "persistent_fixed_trace_element_cache_opt_in": (
            config.get("persistent_fixed_trace_element_cache") is True
        ),
        "affine_tensor_opt_in": (
            config.get("affine_isotropic_reference_tensor") is True
        ),
        "persistent_dtn_surface_cache_opt_in": (
            config.get("persistent_dtn_surface_cache") is True
        ),
        "deterministic_structured_partition_opt_in": (
            config.get("preserve_structured_input_partition") is True
        ),
        "assembly_time_condensation_opt_in": (
            config.get("assembly_time_cell_static_condensation") is True
        ),
        "floquet_elimination_opt_in": (
            config.get("floquet_slave_elimination") is True
        ),
        "canonical_orientation_request_identity": (
            bool(
                config.get(
                    "canonical_orientation_class_reuse",
                    False,
                )
            )
            == expected_canonical_orientation_class_reuse
        ),
        "canonical_orientation_request_provenance": (
            (
                not expected_canonical_orientation_class_reuse
                and not canonical_request
            )
            or (
                canonical_request.get("schema_version")
                == "task035b.canonical-orientation-reuse-request.v1"
                and canonical_request.get("requested")
                is expected_canonical_orientation_class_reuse
                and canonical_request.get("eligible") is True
                and canonical_request.get("accepted")
                is expected_canonical_orientation_class_reuse
                and canonical_request.get("rejection_reasons") == []
                and canonical_request.get("ordinary_default_changed")
                is False
            )
        ),
        "canonical_orientation_core_audit": (
            (
                not expected_canonical_orientation_class_reuse
                and not canonical_core
            )
            or (
                canonical_core.get("schema_version")
                == "task035b.canonical-orientation-condensation.v1"
                and canonical_core.get("enabled")
                is expected_canonical_orientation_class_reuse
                and canonical_core.get("ordinary_default_changed")
                is False
                and (
                    not expected_canonical_orientation_class_reuse
                    or (
                        canonical_core.get(
                            "trace_interior_block_diagonal_proven_"
                            "for_every_used_permutation"
                        )
                        is True
                        and canonical_core.get(
                            "used_set_equals_qualified_set"
                        )
                        is True
                        and canonical_core.get(
                            "inactive_or_postzero_rows_created"
                        )
                        is False
                    )
                )
            )
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
        **dtn_timing_ledger_checks,
        **factor_event_checks,
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
        "summary_mpi_size_identity",
        "source_stable_and_clean_after",
        "raw_petsc_options_absent_on_all_worker_ranks",
        "typed_direct_petsc_options_exact_allowlist",
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
        if not _cache_pairs(resolved, prefix="fixed_trace_element"):
            raise SystemExit(
                "warm cache requires one complete SHA-bound fixed-trace "
                f"custom-element manifest/array pair: {resolved}"
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
    if args.canonical_orientation_class_reuse:
        command.append("--canonical-orientation-class-reuse")
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
        expected_canonical_orientation_class_reuse=(
            args.canonical_orientation_class_reuse
        ),
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
            "canonical_orientation_class_reuse": bool(
                args.canonical_orientation_class_reuse
            ),
            "preserve_structured_input_partition": True,
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
                "fixed_trace_element": _cache_pairs(
                    cache_directory,
                    prefix="fixed_trace_element",
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
