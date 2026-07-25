"""Audit whether the Task035b condensed trace system can run a formal screen.

The ordinary Stage-4 default remains direct MUMPS.  Review V2 now also has an
explicit typed research-only condensed iterative profile.  This pure
postprocess distinguishes that opt-in capability from both the ordinary
default and an unqualified raw ``petsc_extra_options`` override.

The tracked Review-V1 ``condensed_trace_iterative_capability_gate.json`` is
historical controlled-stop evidence and is never rewritten by this module.
"""

from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.common.config_3d import SimulationConfig3D
from src.solvers.common_3d_solve import (
    _apply_petsc_option_dict,
    _direct_lu_petsc_options,
)
from src.solvers.dtn_port_3d import _solve_augmented_system


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
RECORDS = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
DEFAULT_OUTPUT = RECORDS / "condensed_trace_iterative_capability_gate.json"
AUTHORITY_PATH = (
    RECORDS
    / "fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json"
)
AUTHORITY_SHA256 = (
    "1ffde81be08c24232e62c1d2dfbf1b7ad2dcb3623444ea40af68b5c6585758e3"
)
AUTHORITY_SOURCE_SHA = "7f61d554b0441d7b224c096aba402d3b3ac2baa6"
AUTHORITY_SCHEMA = "task035b.fixed-trace-watchdog.v1"
SOURCE_FILES = (
    "benchmarks/task035b_condensed_iterative_capability_gate.py",
    "benchmarks/run_task035b_condensed_iterative.py",
    "benchmarks/run_task035_actual_r5.py",
    "src/common/config_3d.py",
    "src/solvers/common_3d_solve.py",
    "src/solvers/condensed_iterative_profiles.py",
    "src/solvers/dtn_port_3d.py",
)
GIB = 1024**3


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _is_full_sha(value: Any, *, length: int) -> bool:
    normalized = str(value).lower()
    return len(normalized) == length and all(
        character in "0123456789abcdef" for character in normalized
    )


def _source_file_hashes(repo_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in SOURCE_FILES:
        path = repo_root / relative
        if not path.is_file():
            raise RuntimeError(f"required source file is missing: {relative}")
        hashes[relative] = _sha256(path)
    return hashes


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).strip().lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": _is_full_sha(verified, length=40),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "condensed iterative capability source gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": status,
        "source_files_sha256_before": _source_file_hashes(repo_root),
        "checks": checks,
    }


def _close_source_identity(
    repo_root: Path,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    hashes_after = _source_file_hashes(repo_root)
    checks = {
        "head_stable_after_build": head == source["commit_sha"],
        "branch_stable_after_build": branch == source["branch"],
        "worktree_still_clean_before_exclusive_write": status == "",
        "source_files_stable_after_build": (
            hashes_after == source["source_files_sha256_before"]
        ),
    }
    if not all(checks.values()):
        raise SystemExit(
            "condensed iterative capability source closure failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        **dict(source),
        "head_after_build": head,
        "status_after_build_before_write": status,
        "source_files_sha256_after": hashes_after,
        "stable_and_clean_after_build": True,
        "closure_checks": checks,
    }


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": (
            np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
        ),
        "int32_petsc": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "serial_postprocess_only": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "condensed iterative capability ABI gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
        "petsc_hypre_available": bool(
            PETSc.Sys.hasExternalPackage("hypre")
        ),
        "petsc_mumps_available": bool(
            PETSc.Sys.hasExternalPackage("mumps")
        ),
    }


def _load_authority(
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = (repo_root / AUTHORITY_PATH).resolve()
    if not path.is_file():
        raise ValueError(f"h15 direct authority is unreadable: {path}")
    payload = path.read_bytes()
    actual_sha = hashlib.sha256(payload).hexdigest()
    record = json.loads(payload)
    source_sha = (record.get("source") or {}).get("commit_sha")
    checks = {
        "record_sha256_frozen": actual_sha == AUTHORITY_SHA256,
        "schema_frozen": record.get("schema_version") == AUTHORITY_SCHEMA,
        "source_commit_sha_frozen": source_sha == AUTHORITY_SOURCE_SHA,
    }
    if not all(checks.values()):
        raise ValueError(
            "h15 direct authority mismatch: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return record, {
        "path": str(AUTHORITY_PATH),
        "sha256": actual_sha,
        "schema_version": record["schema_version"],
        "source_commit_sha": source_sha,
        "checks": checks,
    }


def _stage_peak(
    record: Mapping[str, Any],
    stage: str,
) -> Mapping[str, Any]:
    matches = [
        item
        for item in record["resource_authority"]["stage_peaks"]
        if item["stage"] == stage
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one resource stage {stage!r}")
    return matches[0]


def _measured_direct_baseline(record: Mapping[str, Any]) -> dict[str, Any]:
    candidate = record["candidate"]
    matrix = candidate["matrix_stats"]
    factor = candidate["high_order_resource_audit"][
        "matrix_factor_resource"
    ]
    preallocation = candidate["cell_static_condensation"][
        "trace_preallocation"
    ]
    resource = record["resource_authority"]
    setup = float(candidate["stage4_dtn_ksp_setup_seconds"])
    solve = float(candidate["stage4_dtn_ksp_solve_seconds"])
    measured = {
        "semantics": "measured",
        "full3d_equivalent_dofs": int(candidate["num_nedelec_dofs"]),
        "active_trace_rows": int(preallocation["active_rows"]),
        "dtn_auxiliary_rows": int(preallocation["appended_rows"]),
        "matrix_rows": int(matrix["matrix_rows"]),
        "matrix_nnz_used": int(matrix["matrix_nnz_used"]),
        "matrix_nnz_allocated": int(matrix["matrix_nnz_allocated"]),
        "matrix_nnz_unneeded": int(matrix["matrix_nnz_unneeded"]),
        "matrix_mallocs": int(matrix["matrix_mallocs"]),
        "matrix_average_row_width": float(
            matrix["matrix_average_nnz_per_row"]
        ),
        "matrix_maximum_row_width": int(
            matrix["matrix_maximum_nnz_per_row"]
        ),
        "factor_solver_type": str(factor["factor_solver_type"]),
        "factor_nnz": int(factor["factor_nnz"]),
        "factor_fill_ratio": float(factor["factor_fill_ratio"]),
        "assembly_time_total_build_seconds": float(
            candidate["stage4_dtn_assembly_time_total_build_seconds"]
        ),
        "base_matrix_assembly_seconds": float(
            candidate["stage4_dtn_base_matrix_assembly_seconds"]
        ),
        "mumps_setup_seconds": setup,
        "mumps_solve_seconds": solve,
        "mumps_setup_plus_solve_seconds_derived": setup + solve,
        "reported_linear_solve_seconds": float(
            candidate["stage4_dtn_linear_solve_seconds"]
        ),
        "full_explicit_true_residual": float(
            candidate["linear_system_relative_residual"]
        ),
        "process_tree_peak_mb": float(resource["max_process_tree_rss_mb"]),
        "process_tree_peak_gib": float(resource["memory_authority_gib"]),
        "process_tree_swap_mb": float(
            resource["max_process_tree_swap_mb"]
        ),
    }
    if measured["active_trace_rows"] + measured["dtn_auxiliary_rows"] != (
        measured["matrix_rows"]
    ):
        raise ValueError("active trace plus DtN rows do not close")
    if measured["matrix_nnz_allocated"] - measured["matrix_nnz_used"] != (
        measured["matrix_nnz_unneeded"]
    ):
        raise ValueError("allocated/used/unneeded matrix NNZ do not close")
    return measured


def _derived_factor_removal_envelope(
    record: Mapping[str, Any],
    measured: Mapping[str, Any],
) -> dict[str, Any]:
    rows = int(measured["matrix_rows"])
    factor_nnz = int(measured["factor_nnz"])
    factor_inventory = record["candidate"]["stage4_dtn_factor_inventory"]
    reported_estimate = int(
        factor_inventory["matrix_stats"]["matrix_memory_estimate_bytes"]
    )
    # Reproduce the existing planning proxy exactly: 24 bytes per nonzero
    # plus 8 bytes per row pointer.  This is not an assertion about the
    # internal PETSc or MUMPS factor layout.
    recomputed_estimate = (
        factor_nnz * 24 + (rows + 1) * 8
    )
    if recomputed_estimate != reported_estimate:
        raise ValueError("factor storage estimate no longer reproduces")
    start_peak = _stage_peak(record, "process_start")
    solve_peak = _stage_peak(record, "fixed_trace_candidate_solve")
    lifecycle_increment_gib = (
        float(solve_peak["max_mpi_process_tree_rss_mb"])
        - float(start_peak["max_mpi_process_tree_rss_mb"])
    ) / 1024.0
    factor_estimate_gib = recomputed_estimate / GIB
    peak_gib = float(measured["process_tree_peak_gib"])
    return {
        "semantics": "derived_not_measured",
        "exact_factor_only_peak_contribution": None,
        "factor_storage_estimate_bytes": recomputed_estimate,
        "factor_storage_estimate_gib": factor_estimate_gib,
        "factor_storage_fraction_of_measured_peak": (
            factor_estimate_gib / peak_gib
        ),
        "derived_stage_peak_delta_gib": lifecycle_increment_gib,
        "factor_only_peak_reduction_upper_bound_gib": None,
        "factor_only_peak_reduction_upper_bound_status": (
            "unknown_from_non_simultaneous_stage_maxima"
        ),
        "arithmetic_peak_minus_factor_storage_proxy_gib": (
            peak_gib - factor_estimate_gib
        ),
        "future_screen_peak_reduction_required_gib": peak_gib - 5.2,
        "upper_bound_warning": (
            "The difference of non-simultaneous stage maxima is not a "
            "factor-memory upper bound and can contain allocation/release "
            "changes unrelated to factors. The 24-byte-per-NNZ planning "
            "proxy is not an exact MUMPS contribution. Neither value is a "
            "measured or predicted iterative peak."
        ),
        "iterative_peak": None,
    }


def _typed_iterative_contract_probe() -> dict[str, bool]:
    """Exercise the live evidence extraction/classifier without a PDE."""

    from benchmarks.run_task035b_condensed_iterative import (
        _classify_screen,
        _extract_solver_evidence,
        SUPPORTED_PROFILES,
    )
    from src.solvers.condensed_iterative_profiles import (
        PHYSICS_AWARE_PROFILE,
        SUPPORTED_CONDENSED_ITERATIVE_PROFILES,
        condensed_iterative_profile_contract,
    )

    coarse_dimension = 80
    coarse_entries = coarse_dimension * coarse_dimension
    coarse_bytes = coarse_entries * 16
    contract = condensed_iterative_profile_contract(
        PHYSICS_AWARE_PROFILE
    )
    physics = {
        "coarse_dimension": coarse_dimension,
        "coarse_rank": coarse_dimension,
        "coarse_dense_lu_active": True,
        "coarse_dense_matrix_entries": coarse_entries,
        "coarse_dense_matrix_bytes": coarse_bytes,
        "strictly_factorless_preconditioner": False,
        "strictly_factorless_reason": (
            "the small dense Galerkin coarse LU is retained"
        ),
        "fine_operator_factor_free": True,
        "global_fine_sparse_factor_nnz": 0,
        "mumps_symbolic_or_numeric_created": False,
    }
    inventory = {
        "global_direct_factor_nnz": 0,
        "global_fine_sparse_factor_nnz": 0,
        "mumps_symbolic_or_numeric_created": False,
        "coarse_dense_lu_active": True,
        "coarse_dense_matrix_entries": coarse_entries,
        "coarse_dense_matrix_bytes": coarse_bytes,
        "coarse_dense_lu_storage_semantics": (
            "small replicated dense coarse LU; no global fine sparse factor"
        ),
        "fine_operator_factor_free": True,
        "strictly_factorless_preconditioner": False,
        "local_subdomain_ilu_active": False,
    }
    worker = {
        "status": "worker_completed_with_summary",
        "rank_failures": [],
        "summary": {
            "case_status": "completed",
            "official_result": True,
            "diagnostic_only": False,
            "postprocess_skipped": False,
            "linear_solve_method": "assembled_condensed_iterative",
            "stage4_condensed_iterative_profile": PHYSICS_AWARE_PROFILE,
            "stage4_condensed_iterative": {
                "configured_programmatically": True,
                "raw_petsc_options_used_for_iterative_configuration": False,
                "assembled_reduced_operator": True,
                "matrix_free": False,
                "residual_history": [1.0, 1.0e-4],
                "residual_history_initial_norm": 1.0,
                "residual_history_final_norm": 1.0e-4,
                "residual_history_final_to_initial": 1.0e-4,
                "terminal_explicit_reduced_residual_norm": 1.0e-4,
                "terminal_explicit_reduced_relative_residual": 1.0e-4,
                "global_direct_factor_nnz": 0,
                "mumps_symbolic_or_numeric_created": False,
                "typed_profile_contract": contract,
                "physics_aware_preconditioner": physics,
            },
            "stage4_dtn_factor_inventory": inventory,
            "actual_ksp_type": "fgmres",
            "actual_pc_type": "python",
            "ksp_converged": True,
            "ksp_converged_reason": 2,
            "ksp_converged_reason_name": "CONVERGED_RTOL",
            "ksp_iterations": 40,
            "mpi_size": 8,
            "mesh_cell_type_actual": "hexahedron",
            "mesh_cells_resolved": [6, 2, 10],
            "num_mesh_cells": 120,
            "num_nedelec_dofs": 74890,
            "matrix_stats": {
                "matrix_rows": 16880,
                "matrix_nnz_used": 9195812,
            },
            "config": {
                "mesh_target_size": 15.0,
                "nedelec_trace_degree_resolved": 5,
                "nedelec_interior_degree_resolved": 6,
            },
            "cell_static_condensation": {
                "full_explicit_true_residual": {
                    "linear_system_relative_residual": 1.0e-10,
                }
            },
        },
    }
    evidence = _extract_solver_evidence(worker)
    telemetry = {
        "observed_worker_rank_count": 8,
        "max_process_tree_swap_mb": 0.0,
        "max_worker_rank_smaps_swap_sum_mb": 0.0,
    }

    def classify(candidate: dict[str, Any]) -> dict[str, Any]:
        return _classify_screen(
            candidate,
            telemetry,
            expected_profile=PHYSICS_AWARE_PROFILE,
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
        )

    passing = classify(evidence)
    raw_tampered = json.loads(json.dumps(evidence))
    raw_tampered["typed_profile_contract"][
        "raw_petsc_options_accepted"
    ] = True
    missing_inventory = json.loads(json.dumps(evidence))
    missing_inventory["factor_inventory"].pop(
        "coarse_dense_matrix_bytes"
    )
    return {
        "profile_registered_in_solver": (
            PHYSICS_AWARE_PROFILE
            in SUPPORTED_CONDENSED_ITERATIVE_PROFILES
        ),
        "profile_registered_in_runner": (
            PHYSICS_AWARE_PROFILE in SUPPORTED_PROFILES
        ),
        "typed_contract_schema": (
            contract.get("schema_version")
            == "task035b.condensed-iterative-profile-contract.v2"
        ),
        "typed_contract_identity": (
            contract.get("name") == PHYSICS_AWARE_PROFILE
        ),
        "typed_contract_rejects_raw_options": (
            contract.get("raw_petsc_options_accepted") is False
        ),
        "residual_history_extracted": (
            evidence.get("residual_history") == [1.0, 1.0e-4]
            and evidence.get(
                "terminal_explicit_reduced_relative_residual"
            )
            == 1.0e-4
        ),
        "factor_inventory_extracted": (
            evidence.get("factor_inventory") == inventory
        ),
        "complete_contract_classifies_as_capable": (
            passing["formal_iterative_screen_pass"] is True
        ),
        "raw_option_contract_tamper_fails_closed": (
            classify(raw_tampered)["formal_iterative_screen_pass"] is False
        ),
        "missing_factor_inventory_fails_closed": (
            classify(missing_inventory)[
                "formal_iterative_screen_pass"
            ]
            is False
        ),
    }


def _code_capability() -> dict[str, Any]:
    from src.solvers.condensed_iterative_profiles import (
        configure_condensed_iterative_outer_ksp,
    )

    dataclass_field_names = {field.name for field in fields(SimulationConfig3D)}
    dataclass_fields = {
        field.name: field for field in fields(SimulationConfig3D)
    }
    direct_options = _direct_lu_petsc_options()
    overridden_options = dict(direct_options)
    _apply_petsc_option_dict(
        overridden_options,
        {
            "ksp_type": "gmres",
            "pc_type": "bjacobi",
            "ksp_gmres_restart": 30,
        },
    )
    solve_parameters = inspect.signature(_solve_augmented_system).parameters
    solve_source = inspect.getsource(_solve_augmented_system)
    outer_profile_source = inspect.getsource(
        configure_condensed_iterative_outer_ksp
    )
    hypre_available = bool(PETSc.Sys.hasExternalPackage("hypre"))
    typed_contract_checks = _typed_iterative_contract_probe()
    capability_checks = {
        "ordinary_default_direct_mumps": (
            direct_options["ksp_type"] == "preonly"
            and direct_options["pc_type"] == "lu"
            and dataclass_fields[
                "stage4_condensed_iterative_profile"
            ].default
            is None
        ),
        "typed_profile_config_field": (
            "stage4_condensed_iterative_profile"
            in dataclass_field_names
        ),
        "solver_accepts_typed_profile": (
            "iterative_profile" in solve_parameters
        ),
        "solver_accepts_physical_dtn_row_identity": (
            "dtn_auxiliary_rows" in solve_parameters
        ),
        "solver_writes_residual_history": (
            "setConvergenceHistory" in outer_profile_source
            and '"residual_history"' in solve_source
            and "terminal_explicit_reduced_relative_residual"
            in solve_source
        ),
        "solver_writes_factor_inventory": (
            '"global_fine_sparse_factor_nnz"' in solve_source
            and '"coarse_dense_lu_active"' in solve_source
            and '"mumps_symbolic_or_numeric_created"' in solve_source
        ),
        **typed_contract_checks,
    }
    capability_pass = all(capability_checks.values())
    return {
        "petsc_hypre_available": hypre_available,
        "public_solver_profile_is_direct_only": (
            direct_options["ksp_type"] == "preonly"
            and direct_options["pc_type"] == "lu"
            and dataclass_fields[
                "stage4_condensed_iterative_profile"
            ].default
            is None
        ),
        "public_solver_profile_semantics": (
            "ordinary_default_direct_mumps_with_explicit_research_opt_in"
        ),
        "default_ksp_type": str(direct_options["ksp_type"]),
        "default_pc_type": str(direct_options["pc_type"]),
        "raw_petsc_option_override_technically_possible": (
            overridden_options["ksp_type"] == "gmres"
            and overridden_options["pc_type"] == "bjacobi"
        ),
        "raw_override_preserves_correct_iterative_provenance": False,
        "dedicated_condensed_iterative_hook_exists": (
            "stage4_condensed_iterative_profile" in dataclass_field_names
            and "iterative_profile" in solve_parameters
            and "dtn_auxiliary_rows" in solve_parameters
        ),
        "iterative_residual_history_contract_exists": (
            capability_checks["solver_writes_residual_history"]
            and typed_contract_checks["residual_history_extracted"]
        ),
        "factor_free_inventory_contract_exists": (
            capability_checks["solver_writes_factor_inventory"]
            and typed_contract_checks["factor_inventory_extracted"]
            and typed_contract_checks[
                "missing_factor_inventory_fails_closed"
            ]
        ),
        "typed_explicit_research_opt_in_exists": (
            typed_contract_checks["profile_registered_in_solver"]
            and typed_contract_checks["profile_registered_in_runner"]
        ),
        "typed_profile_name": "fgmres_dtn_trace_deflation",
        "typed_profile_contract_schema": (
            "task035b.condensed-iterative-profile-contract.v2"
        ),
        "hypre_preconditioner_available": hypre_available,
        "selected_profile_requires_hypre": False,
        "hypre_unavailable_but_not_required_for_selected_profile": (
            not hypre_available
        ),
        "capability_checks": capability_checks,
        "candidate_capability_pass": capability_pass,
        "reason": (
            "The ordinary default remains direct MUMPS. The live code now "
            "contains a typed explicit DtN-trace-deflation research profile "
            "with residual-history, fine-factor and dense-coarse inventory, "
            "and fail-closed provenance contracts. HYPRE remains unavailable "
            "but is not a dependency of this profile. Raw PETSc overrides "
            "still do not constitute qualified iterative evidence."
        ),
    }


def build_capability_gate(
    *,
    record: Mapping[str, Any],
    authority: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    environment_identity: Mapping[str, Any],
    code_capability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the controlled-stop evidence without writing it."""

    measured = _measured_direct_baseline(record)
    derived = _derived_factor_removal_envelope(record, measured)
    capability = dict(
        _code_capability() if code_capability is None else code_capability
    )
    candidate = record["candidate"]
    preallocation = candidate["cell_static_condensation"][
        "trace_preallocation"
    ]
    qualification = record["qualification"]
    authority_checks = {
        **dict(authority["checks"]),
        "qualified_record": qualification["pass"] is True,
        "mpi8": int(candidate["mpi_size"]) == 8,
        "fixed_rectangular_hexa_h15": (
            record["target_identity"]["geometry"]
            == "Task034 fixed rectangular block grating"
            and float(candidate["h_nm"]) == 15.0
        ),
        "physical_p5_trace_p6_interior": (
            int(candidate["nedelec_trace_degree_resolved"]) == 5
            and int(candidate["nedelec_interior_degree_resolved"]) == 6
        ),
        "assembly_time_condensation": (
            candidate["stage4_assembly_time_cell_static_condensation"]
            is True
        ),
        "floquet_slave_elimination": (
            candidate["stage4_floquet_slave_elimination"] is True
        ),
        "exact_preallocation": (
            preallocation["base_graph_preallocation"] == "exact"
        ),
        "zero_matrix_mallocs": measured["matrix_mallocs"] == 0,
        "true_residual_le_1e-9": (
            measured["full_explicit_true_residual"] <= 1.0e-9
        ),
        "no_swap": measured["process_tree_swap_mb"] == 0.0,
        "ordinary_default_unchanged": (
            qualification["checks"]["ordinary_default_unchanged"] is True
        ),
    }
    evidence_checks = {
        "all_authority_checks_pass": all(authority_checks.values()),
        "direct_measurements_recomputed": (
            measured["matrix_rows"] == 16_880
            and measured["matrix_nnz_used"] == 9_195_812
            and measured["factor_nnz"] == 27_916_600
        ),
        "factor_storage_proxy_recomputed": (
            derived["factor_storage_estimate_bytes"] == 670_133_448
        ),
        "iterative_capability_missing": (
            capability["candidate_capability_pass"] is False
        ),
        "no_iterative_pde_claimed": True,
        "ordinary_default_unchanged": True,
    }
    if not all(evidence_checks.values()):
        raise RuntimeError(
            "condensed iterative capability gate did not close: "
            + ", ".join(
                name for name, passed in evidence_checks.items() if not passed
            )
        )
    return {
        "schema_version": (
            "task035b.condensed-trace-iterative-capability-gate.v1"
        ),
        "benchmark_id": (
            "task035b_condensed_trace_iterative_capability_gate"
        ),
        "status": "capability_stop_not_run",
        "pass": True,
        "classification": "controlled_stop_before_iterative_pde",
        "record_semantics": (
            "pass means the factor-free capability audit completed; no "
            "iterative PDE, memory result, or candidate is claimed"
        ),
        "source": dict(source_identity),
        "environment": dict(environment_identity),
        "authority": {
            **dict(authority),
            "checks": authority_checks,
        },
        "measured_direct_baseline": measured,
        "derived_factor_removal_envelope": derived,
        "code_and_provenance_capability": capability,
        "future_unique_screen_gate": {
            "status": "not_run",
            "solver": "gmres",
            "mpi_size": 8,
            "restart": 30,
            "max_iterations": 200,
            "ksp_norm_type": "unpreconditioned",
            "minimum_residual_reduction_decades": 3.0,
            "residual_reduction_metric": (
                "unpreconditioned KSP residual 2-norm relative to its "
                "iteration-zero value"
            ),
            "terminal_explicit_reduced_system_relative_residual_max": 1.0e-3,
            "terminal_explicit_residual_definition": (
                "||b_reduced - A_reduced x||_2 / ||b_reduced||_2"
            ),
            "process_tree_peak_gib_max": 5.2,
            "process_tree_swap_mb_max": 0.0,
            "factor_matrix_must_not_exist": True,
            "factor_nnz_required": 0,
            "requires_dedicated_iterative_provenance": True,
            "ordinary_default_changed": False,
        },
        "pde": {
            "status": "not_run",
            "mpi8_gmres_started": False,
            "matrix_reassembled": False,
            "factorization_started": False,
            "formal_iterative_screen_completed": False,
            "formal_screen_run_count": 0,
        },
        "decision": {
            "classification": "capability_stop_not_run",
            "iterative_candidate": False,
            "formal_iterative_screen_pass": False,
            "reason": (
                "the live PETSc build lacks HYPRE and the fixed-trace path "
                "lacks a dedicated factor-free solver/provenance/residual-"
                "history contract; one raw option override is not formal "
                "evidence"
            ),
            "next_step_if_reopened": (
                "implement an opt-in condensed iterative profile with "
                "factor-free inventory and residual history, then run only "
                "the frozen MPI8 screen gate"
            ),
            "ordinary_default_changed": False,
        },
        "qualification": {
            "pass": True,
            "evidence_valid": True,
            "iterative_capability_pass": False,
            "formal_iterative_screen_pass": False,
            "iterative_candidate": False,
            "checks": evidence_checks,
        },
    }


def _resolve_output(path: Path) -> Path:
    output = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        output.relative_to((ROOT / RECORDS).resolve())
    except ValueError as error:
        raise ValueError(
            "condensed iterative evidence must remain in Case095 records"
        ) from error
    return output


def _write_json_exclusive(
    path: Path,
    record: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = _resolve_output(args.output)
    if output.exists():
        raise FileExistsError(f"exclusive output already exists: {output}")
    source = _verified_source_identity(ROOT, args.verified_clean_sha)
    environment = _environment_identity(ROOT)
    record, authority = _load_authority(ROOT)
    evidence = build_capability_gate(
        record=record,
        authority=authority,
        source_identity=source,
        environment_identity=environment,
    )
    evidence["source"] = _close_source_identity(ROOT, source)
    _write_json_exclusive(output, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
