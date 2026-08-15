from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host path
    resource = None

from benchmarks.task035c_p6_h10_gates import (
    TASK035C_P6_H10_BACKENDS,
    TASK035C_P6_H10_MODE_COUNTS,
    TASK035C_P6_H10_MPI_SIZES,
    task035c_p6_h10_full3d_reference_gate,
    task035c_p6_h10_preflight_authority_gate,
    valid_hex_digest,
)
from benchmarks.task039_memory_telemetry import (
    task039_e10_ledger,
    task039_e10_stage_event,
    task039_stage_target,
    task039_v2_h5_stage_event,
    task039_write_memory_object_ledger,
)
from benchmarks.task032_final_gates import (
    _all_formal_true,
    _exact_traction_gate,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    target_stage4_config,
)
from src.common.distributed_matrix_diagnostics import (
    distributed_active_column_count,
)
from src.coupling.hybrid_internal_modes import (
    build_hybrid_internal_mode_coupling,
    capture_hybrid_trace_audit,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    compare_selected_planes_to_reference,
    element_safe_middle_offsets,
    hybrid_volume_absorption,
    interface_field_continuity,
    sampled_plane_flux_and_vacuum_energy,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_schur_direct import (
    build_hybrid_modal_schur_direct_system,
    build_hybrid_modal_schur_memory_minimal_system,
    solve_hybrid_modal_schur_direct,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_status import hybrid_p_disposition
from src.solvers.common_3d_solve import (
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "080"
    / "phase6"
    / "hybrid_augmented_research.json"
)
REFERENCE_BY_DEGREE_AND_H = {
    (2, 5.0): ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h5_reference.json",
    (2, 3.0): ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h3_reference.json",
    (3, 5.0): ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "stage3_p3_h5"
    / "full3d_reference.json",
}


class _Task039TraceAuditStop(RuntimeError):
    """Internal controlled stop for the explicit research capture lane."""

    def __init__(self, record: dict[str, Any]):
        super().__init__("Task039 trace audit evidence captured.")
        self.record = record


def _discrete_axial_qualification_scope(
    propagation_model: str,
    traction_model: str,
) -> dict[str, Any]:
    """Expose the fail-closed scope of the Task035c discrete axial symbols."""

    selected = propagation_model == "full3d_uniform_cg" or traction_model in {
        "scalar_cg_discrete_derivative",
        "full3d_one_cell_exact_schur",
    }
    return {
        "selected": selected,
        "status": (
            "qualified_only_for_listed_scope"
            if selected
            else "not_selected_ordinary_continuous_symbols"
        ),
        "qualified": [
            "fixed rectangular block grating",
            "structured tensor-product mesh",
            "axis-aligned first-order affine hexahedra",
            "uniform z segmentation in the modal middle region",
            "one axial h for the scalar CG(p) chain",
            "supported axial degree p1-p6",
            "complex128",
            "Floquet periodicity",
            "sparse auxiliary DtN",
            "direct standard/static Full3D and Hybrid",
        ],
        "not_qualified": [
            "nonuniform z spacing",
            "locally refined or hanging-node hexa mesh",
            "curved or distorted hexahedra",
            "high-order curved geometry mapping",
            "tetrahedral static condensation",
            "hexa/tetra/prism/pyramid mixed meshes",
            "irregular geometry",
            "production automatic hp adaptivity",
        ],
        "failure_policy": (
            "unsupported meshes and inconsistent propagation/traction "
            "combinations fail closed; no fallback is permitted"
        ),
    }


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    comm: MPI.Intracomm,
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        tracked_status = _git("status", "--porcelain", "--untracked-files=all")
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or tracked_status is None:
        raise SystemExit("Cannot verify Task32 Phase6 source provenance.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            character not in "0123456789abcdef" for character in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match HEAD {head}."
            )
        if tracked_status:
            raise SystemExit(
                "Tracked source is dirty despite --verified-clean-sha. "
                "Commit the implementation before a qualifying run."
            )
        tracked_dirty = False
        verification = "local_full_sha_and_tracked_status"
    else:
        if allow_dirty_research:
            tracked_dirty = True
            verification = "dirty_research_opt_in_with_status_scan"
        elif tracked_status:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase6 code first or pass "
                "--allow-dirty-research for a non-qualifying diagnostic."
            )
        else:
            tracked_dirty = False
            verification = "local_git_status"
    return {
        "commit_sha": head,
        "branch": branch,
        "git_dirty": tracked_dirty,
        "tracked_source_dirty": tracked_dirty,
        "verification": verification,
        "verified_clean_sha": verified_clean_sha,
    }


def _verify_source_stable_at_end(
    comm: MPI.Intracomm,
    start: dict[str, Any],
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> None:
    """Require the same tracked-source state at the end of a formal shard."""

    end = _source_provenance(comm, verified_clean_sha, allow_dirty_research)
    if end["commit_sha"] != start["commit_sha"]:
        raise SystemExit("Tracked source HEAD changed during the Hybrid run.")
    if not allow_dirty_research and end["tracked_source_dirty"]:
        raise SystemExit("Tracked source became dirty during the Hybrid run.")
    start["source_commit_at_end_full_sha"] = end["commit_sha"]
    start["source_clean_and_stable"] = bool(
        not start["tracked_source_dirty"]
        and not end["tracked_source_dirty"]
        and end["commit_sha"] == start["commit_sha"]
    )


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _historical_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _complex_json(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _task039_canonical_trace_gate_record(
    coupling: Any, policy: str, family_sha: str | None
) -> dict[str, Any]:
    sides: dict[str, Any] = {}
    for side, block in (("bottom", coupling.bottom), ("top", coupling.top)):
        gate = block.canonical_trace_gate
        if gate is None:
            raise RuntimeError(f"Missing {side} Task039 canonical trace Gate audit.")
        sides[side] = {
            "raw_forward": float(gate["raw_consistency_error"]),
            "representation": float(gate["canonical_representation_error"]),
            "backward_eta": float(gate["backward_error_eta"]),
            "dynamic_limit": float(gate["dynamic_backward_error_limit"]),
            "finite": bool(gate["finite_all_trace_arrays"]),
            "policy": gate["policy"],
            "family_sha": gate["family_sha256"],
            "trace_gram_condition": float(block.trace_gram_condition),
        }
    return {"policy": policy, "family_sha": family_sha, "sides": sides}


def _json_default(value):
    if isinstance(value, complex):
        return _complex_json(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _relative_vector_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    try:
        actual.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        return float(
            difference.norm()
            / max(float(actual.norm()), float(expected.norm()), 1.0e-30)
        )
    finally:
        difference.destroy()


def _global_active_column_count(matrix: PETSc.Mat) -> int:
    """Count active columns without replicating their IDs on every rank."""

    return distributed_active_column_count(matrix).global_count


def _basis_summary(basis) -> dict[str, Any]:
    identity_difference = np.asarray(
        basis.biorthogonality_matrix, dtype=np.complex128
    ) - np.eye(len(basis.modes), dtype=np.complex128)
    absolute_difference = np.abs(identity_difference)
    row_sums = np.sum(absolute_difference, axis=1)
    worst_row = int(np.argmax(row_sums))
    worst_entry = tuple(
        int(index)
        for index in np.unravel_index(
            int(np.argmax(absolute_difference)),
            absolute_difference.shape,
        )
    )
    return {
        "mode_count": len(basis.modes),
        "max_biorthogonality_identity_error": basis.max_identity_error,
        "max_biorthogonality_entry_identity_error": (basis.max_entry_identity_error),
        "biorthogonality_identity_diagnostics": {
            "worst_row_index": worst_row,
            "worst_row_sum": float(row_sums[worst_row]),
            "worst_entry_row": worst_entry[0],
            "worst_entry_column": worst_entry[1],
            "worst_entry_abs": float(absolute_difference[worst_entry]),
        },
        "left_pair_relative_errors": list(basis.left_pair_relative_errors),
        "near_degenerate_groups": [
            {
                "indices": list(group.indices),
                "beta_center_per_nm": _complex_json(group.beta_center),
                "max_relative_beta_spread": group.max_relative_beta_spread,
                "overlap_condition": group.overlap_condition,
                "normalization_method": group.normalization_method,
                "post_normalization_identity_error": (
                    group.post_normalization_identity_error
                ),
            }
            for group in basis.groups
        ],
        "betas_per_nm": [_complex_json(mode.beta) for mode in basis.modes],
        "directions": [mode.direction for mode in basis.modes],
        "kinds": [mode.kind for mode in basis.modes],
        "passive_branch_valid": [mode.passive_branch_valid for mode in basis.modes],
        "polynomial_relative_residuals": [
            mode.right.polynomial_relative_residual for mode in basis.modes
        ],
        "left_polynomial_relative_residuals": [
            mode.left_polynomial_relative_residual for mode in basis.modes
        ],
        "full_vector_gathered": basis.full_vector_gathered,
    }


def _directional_selection_summary(report) -> dict[str, Any]:
    return {
        "requested_modes": report.requested_modes,
        "candidate_modes": report.candidate_modes,
        "selected_modes": report.selected_modes,
        "desired_direction": report.desired_direction,
        "direction_counts": report.direction_counts,
        "passive_candidate_count": report.passive_candidate_count,
        "selected_candidate_indices": list(report.selected_candidate_indices),
        "flux_tolerance": report.flux_tolerance,
        "finite_candidate_count": report.finite_candidate_count,
        "numerically_infinite_candidate_count": (
            report.numerically_infinite_candidate_count
        ),
        "finite_spectrum_abs_beta_cutoff_per_nm": report.abs_beta_cutoff,
        "first_rejected_numerical_infinity_beta_per_nm": (
            None
            if report.first_rejected_numerical_infinity_beta is None
            else _complex_json(report.first_rejected_numerical_infinity_beta)
        ),
    }


class _ModalBasisCapacityStop(RuntimeError):
    """Internal control flow after writing a structured finite-spectrum negative."""


NUMERICAL_INFINITY_BETA_H_CUTOFF = 1.0e4


def _case080_reference_path(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
) -> Path | None:
    references = (
        REFERENCE_BY_DEGREE_AND_H
        if reference_by_degree_and_h is None
        else reference_by_degree_and_h
    )
    matches = [
        path
        for (reference_degree, level), path in references.items()
        if degree == reference_degree and abs(h_nm - level) <= 1.0e-12
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple Case080 references match degree={degree}, h={h_nm} nm."
        )
    return matches[0] if matches else None


def _normalize_full3d_reference_record(
    reference: dict[str, Any],
    *,
    path: Path,
) -> dict[str, Any]:
    """Normalize a native watchdog record without writing a derived descriptor."""

    if reference.get("record_type") == "task034_full3d_reference":
        return reference
    if reference.get("schema_version") != "task033.full3d-watchdog.v1":
        return reference
    try:
        source = reference["source"]
        qualification = reference["qualification"]
        solver = reference["solver_summary"]
        resource_authority = reference["resource_authority"]
        archive = Path(str(solver["full3d_reference_archive"]))
        metadata = Path(str(solver["full3d_reference_metadata"]))
        if not archive.is_absolute():
            archive = ROOT / archive
        if not metadata.is_absolute():
            metadata = ROOT / metadata
        archive = archive.resolve()
        metadata = metadata.resolve()
        run_root = archive.parent.relative_to(ROOT)
        commit_sha = str(source["commit_sha"]).lower()
        polarization_kind = str(solver["polarization_kind"]).lower()
        archive_sha256 = str(solver["full3d_reference_archive_sha256"]).lower()
        finite_results = (
            solver["linear_system_relative_residual"],
            solver["R_total"],
            solver["T_total"],
            solver["A_balance"],
            solver["A_volume_total"],
            solver["energy_closure_error_port_volume"],
            resource_authority["memory_authority_gib"],
        )
        raw_valid = bool(
            reference["status"] == "full3d_reference_pass"
            and reference["run_kind"] == "full-solve"
            and qualification["pass"] is True
            and reference["no_swap"] is True
            and source["tracked_source_dirty"] is False
            and source["stable_and_clean_after"] is True
            and solver["case_status"] == "completed"
            and solver["official_result"] is True
            and solver["full3d_reference_exported"] is True
            and polarization_kind in {"s", "p"}
            and math.isclose(float(solver["incident_theta_deg"]), 80.0)
            and math.isclose(float(solver["incident_phi_deg"]), 0.0)
            and float(solver["linear_system_relative_residual"]) <= 1.0e-9
            and archive.name == "full3d_reference_samples.npz"
            and metadata.name == "full3d_reference_samples.json"
            and metadata.parent == archive.parent
            and len(commit_sha) == 40
            and all(character in "0123456789abcdef" for character in commit_sha)
            and len(archive_sha256) == 64
            and all(character in "0123456789abcdef" for character in archive_sha256)
            and all(np.isfinite(float(value)) for value in finite_results)
        )
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise RuntimeError(
            f"Native full3D watchdog reference is incomplete: {path}"
        ) from error
    if not raw_valid:
        raise RuntimeError(
            f"Native full3D watchdog reference failed its raw Gate: {path}"
        )
    return {
        "record_type": "task034_full3d_reference",
        "metadata": {
            "commit_sha": commit_sha,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "host_environment_id": "WSL2-Ubuntu-24.04",
            "provenance": (
                "in-memory normalization of native full3D watchdog evidence"
            ),
        },
        "physical_model": {
            "wavelength_nm": 13.5,
            "incident_theta_deg": 80.0,
            "incident_grazing_deg": 10.0,
            "incident_phi_deg": 0.0,
            "polarization_kind": polarization_kind,
            "nedelec_degree": int(reference["degree"]),
            "mesh_h_nm": float(reference["h_nm"]),
            "mpi_size": int(reference["mpi_size"]),
            "linear_solver": "direct_lu_mumps",
        },
        "results": {
            "case_status": solver["case_status"],
            "official_result": True,
            "linear_system_true_relative_residual": float(
                solver["linear_system_relative_residual"]
            ),
            "R_total": float(solver["R_total"]),
            "T_total": float(solver["T_total"]),
            "A_balance": float(solver["A_balance"]),
            "A_volume_total": float(solver["A_volume_total"]),
            "energy_closure_error_port_volume": float(
                solver["energy_closure_error_port_volume"]
            ),
            "external_memory_authority_gib": float(
                resource_authority["memory_authority_gib"]
            ),
        },
        "artifacts": {
            "ignored_run_root": run_root.as_posix(),
            "reference_npz_sha256": archive_sha256,
        },
        "qualification": {
            "phase1_reference_pass": True,
            "grid_converged": False,
            "no_swap": True,
            "watchdog_status": reference["status"],
            "heavy_artifacts_tracked": False,
        },
    }


def _validate_case080_reference_identity(
    reference: dict[str, Any],
    *,
    degree: int,
    h_nm: float,
    path: Path,
    polarization_kind: str = "s",
) -> None:
    try:
        physical_model = reference["physical_model"]
        qualification = reference["qualification"]
        metadata = reference["metadata"]
        commit_sha = str(metadata["commit_sha"]).lower()
        identity_valid = (
            physical_model["nedelec_degree"] == degree
            and abs(float(physical_model["mesh_h_nm"]) - h_nm) <= 1.0e-12
            and abs(float(physical_model["incident_grazing_deg"]) - 10.0) <= 1.0e-12
            and abs(float(physical_model["incident_theta_deg"]) - 80.0) <= 1.0e-12
            and abs(float(physical_model["incident_phi_deg"])) <= 1.0e-12
            and physical_model["polarization_kind"] == polarization_kind
            and abs(float(physical_model["wavelength_nm"]) - 13.5) <= 1.0e-12
            and qualification["phase1_reference_pass"] is True
            and metadata["git_dirty"] is False
            and metadata["tracked_source_dirty"] is False
            and len(commit_sha) == 40
            and all(character in "0123456789abcdef" for character in commit_sha)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Case080 reference identity is incomplete or invalid: {path}"
        ) from error
    if not identity_valid:
        raise RuntimeError(
            "Case080 reference identity does not match the requested p/h and "
            f"pinned 10-degree {polarization_kind}-polarized 13.5-nm model: {path}"
        )


def _load_case080_reference(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
    *,
    polarization_kind: str = "s",
) -> tuple[Path, dict[str, Any]] | None:
    reference_path = _case080_reference_path(degree, h_nm, reference_by_degree_and_h)
    if reference_path is None:
        return None
    if not reference_path.exists():
        raise FileNotFoundError(
            f"Pinned Case080 reference record is missing: {reference_path}"
        )
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Cannot load pinned Case080 reference record: {reference_path}"
        ) from error
    reference = _normalize_full3d_reference_record(reference, path=reference_path)
    _validate_case080_reference_identity(
        reference,
        degree=degree,
        h_nm=h_nm,
        path=reference_path,
        polarization_kind=polarization_kind,
    )
    return reference_path, reference


def _reference_comparison(
    loaded_reference: tuple[Path, dict[str, Any]] | None,
    port_power: dict[str, Any],
) -> dict[str, Any] | None:
    if loaded_reference is None:
        return None
    reference_path, reference = loaded_reference
    results = reference["results"]
    return {
        "reference_file": str(reference_path.relative_to(ROOT)),
        "reference_commit_sha": reference["metadata"]["commit_sha"],
        "reference_grid_converged": reference["qualification"]["grid_converged"],
        "hybrid_minus_full3d": {
            "R_total": float(port_power["R_total"] - results["R_total"]),
            "T_total": float(port_power["T_total"] - results["T_total"]),
            "A_balance": float(port_power["A_balance"] - results["A_balance"]),
        },
        "full3d": {
            "R_total": results["R_total"],
            "T_total": results["T_total"],
            "A_balance": results["A_balance"],
            "A_volume_total": results["A_volume_total"],
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_archive(
    loaded_reference: tuple[Path, dict[str, Any]] | None,
) -> tuple[Path, Path, dict[str, Any]] | None:
    if loaded_reference is None:
        return None
    record_path, record = loaded_reference
    run_root = ROOT / record["artifacts"]["ignored_run_root"]
    archive = run_root / "full3d_reference_samples.npz"
    if not archive.exists():
        raise FileNotFoundError(
            f"Pinned full-3D selected-plane archive is missing: {archive}"
        )
    expected_sha = str(record["artifacts"]["reference_npz_sha256"])
    actual_sha = _sha256(archive)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Full-3D selected-plane archive SHA256 {actual_sha} != {expected_sha}."
        )
    return archive, record_path, record


def _reference_sampling_grid(
    cfg: Any, bottom_interface_nm: float, top_interface_nm: float
):
    """Use requested reference sampling while preserving ordinary defaults."""

    sample_x = cfg.x_min + (
        np.arange(int(cfg.full3d_reference_sample_count_x), dtype=np.float64) + 0.5
    ) * cfg.period_x / int(cfg.full3d_reference_sample_count_x)
    sample_y = cfg.y_min + (
        np.arange(int(cfg.full3d_reference_sample_count_y), dtype=np.float64) + 0.5
    ) * cfg.period_y / int(cfg.full3d_reference_sample_count_y)
    if cfg.full3d_reference_plane_z:
        sample_z = np.asarray(cfg.full3d_reference_plane_z, dtype=np.float64)
    else:
        sample_z = np.linspace(
            bottom_interface_nm,
            top_interface_nm,
            5,
            dtype=np.float64,
        )
    return sample_x, sample_y, sample_z


def _direct_canonical_exports(
    *,
    solution: Any,
    systems: tuple[Any, Any],
    run_dir: Path,
    comm: MPI.Intracomm,
    prefix: str,
) -> dict[str, Any]:
    """Write the audited active/full packets for an explicit direct run."""

    from benchmarks.run_task037b_hybrid_iterative import (
        _write_canonical_manifest_exports,
        collective_heap_cleanup,
    )

    physical_solution = SimpleNamespace(
        bottom=solution.bottom,
        top=solution.top,
        bottom_recovered=solution.bottom_recovered,
        top_recovered=solution.top_recovered,
    )
    exports: dict[str, Any] = {}
    for side in ("bottom", "top"):
        exports[side] = _write_canonical_manifest_exports(
            side=side,
            systems={"bottom": systems[0], "top": systems[1]},
            physical_solution=physical_solution,
            run_dir=run_dir,
            comm=comm,
            prefix=prefix,
        )
        cleanup = collective_heap_cleanup(comm)
        exports[side]["cleanup"] = cleanup
        if not cleanup["collective_call_completed"]:
            raise RuntimeError(f"{prefix} {side} canonical cleanup failed.")
    return exports


_TASK039_DIRECT_PAYLOAD_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "modal_amplitudes",
    "bottom_q",
    "top_q",
)


def _task039_array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _task039_direct_payload(
    *,
    selected_planes: Any,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    sample_z: np.ndarray,
    modal_amplitudes: np.ndarray,
    external_auxiliary_amplitudes: Mapping[str, Any],
    run_dir: Path,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Persist the opt-in Task39 fields while their arrays are still alive."""

    descriptor = None
    if comm.rank == 0:
        arrays = {
            "x_nm": np.asarray(sample_x, dtype=np.float64),
            "y_nm": np.asarray(sample_y, dtype=np.float64),
            "z_nm": np.asarray(sample_z, dtype=np.float64),
            "E_V_per_m": np.asarray(
                selected_planes.electric_V_per_m, dtype=np.complex128
            ),
            "H_A_per_m": np.asarray(
                selected_planes.magnetic_A_per_m, dtype=np.complex128
            ),
            "modal_amplitudes": np.asarray(modal_amplitudes, dtype=np.complex128),
            "bottom_q": np.asarray(
                external_auxiliary_amplitudes["bottom"], dtype=np.complex128
            ),
            "top_q": np.asarray(
                external_auxiliary_amplitudes["top"], dtype=np.complex128
            ),
        }
        expected_shapes = {
            "x_nm": (40,),
            "y_nm": (20,),
            "z_nm": (5,),
            "E_V_per_m": (5, 20, 40, 3),
            "H_A_per_m": (5, 20, 40, 3),
        }
        for key, shape in expected_shapes.items():
            if arrays[key].shape != shape:
                raise RuntimeError(
                    f"Task39 direct payload {key} shape {arrays[key].shape} != {shape}."
                )
        if not np.array_equal(
            arrays["z_nm"], np.asarray([10, 30, 60, 90, 110], dtype=np.float64)
        ):
            raise RuntimeError("Task39 direct payload z planes are not frozen.")
        if any(not np.all(np.isfinite(value)) for value in arrays.values()):
            raise RuntimeError("Task39 direct payload contains a non-finite array.")
        if arrays["modal_amplitudes"].ndim != 1 or any(
            arrays[key].ndim != 1 for key in ("bottom_q", "top_q")
        ):
            raise RuntimeError("Task39 direct modal/q payload must be one-dimensional.")

        run_dir.mkdir(parents=True, exist_ok=True)
        payload_path = run_dir / "task039_direct_payload.npz"
        np.savez(payload_path, **arrays)
        descriptor = {
            "schema": "task039.hybrid-direct-payload.v1",
            "path": payload_path.name,
            "sha256": _sha256(payload_path),
            "bytes": payload_path.stat().st_size,
            "keys": list(_TASK039_DIRECT_PAYLOAD_KEYS),
            "arrays": {
                key: {
                    "shape": list(value.shape),
                    "dtype": str(value.dtype),
                    "bytes": int(value.nbytes),
                    "sha256": _task039_array_sha256(value),
                    "finite": True,
                }
                for key, value in arrays.items()
            },
        }
    return comm.bcast(descriptor, root=0)


def _task039_h_diagnostic_enabled(
    canonical_export_prefix: str | None, requested_modes: int
) -> bool:
    return canonical_export_prefix == "task039_direct" and requested_modes == 480


_TASK039_H_DIAGNOSTIC_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "native_E_V_per_m",
    "native_H_A_per_m",
    "curlE_E_V_per_m",
    "curlE_H_A_per_m",
    "native_flux",
    "curlE_flux",
    "native_energy",
    "curlE_energy",
)


def _task039_h_diagnostic_payload(
    *,
    native_planes: Any,
    curl_e_planes: Any,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    sample_z: np.ndarray,
    plane_roles: list[str],
    offset_provenance: Mapping[str, Any],
    run_dir: Path,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Persist the opt-in native/curl-E seven-plane diagnostic payload."""

    descriptor = None
    if comm.rank == 0:
        arrays = {
            "x_nm": np.asarray(sample_x, dtype=np.float64),
            "y_nm": np.asarray(sample_y, dtype=np.float64),
            "z_nm": np.asarray(sample_z, dtype=np.float64),
            "native_E_V_per_m": np.asarray(
                native_planes.electric_V_per_m, dtype=np.complex128
            ),
            "native_H_A_per_m": np.asarray(
                native_planes.magnetic_A_per_m, dtype=np.complex128
            ),
            "curlE_E_V_per_m": np.asarray(
                curl_e_planes.electric_V_per_m, dtype=np.complex128
            ),
            "curlE_H_A_per_m": np.asarray(
                curl_e_planes.magnetic_A_per_m, dtype=np.complex128
            ),
        }
        native_flux, native_energy = sampled_plane_flux_and_vacuum_energy(
            arrays["native_E_V_per_m"], arrays["native_H_A_per_m"]
        )
        curl_flux, curl_energy = sampled_plane_flux_and_vacuum_energy(
            arrays["curlE_E_V_per_m"], arrays["curlE_H_A_per_m"]
        )
        arrays.update(
            native_flux=native_flux,
            curlE_flux=curl_flux,
            native_energy=native_energy,
            curlE_energy=curl_energy,
        )
        field_shape = (7, 20, 40, 3)
        if any(
            arrays[key].shape != field_shape
            for key in (
                "native_E_V_per_m",
                "native_H_A_per_m",
                "curlE_E_V_per_m",
                "curlE_H_A_per_m",
            )
        ):
            raise RuntimeError("Task039 H diagnostic fields have an unexpected shape.")
        if (
            arrays["x_nm"].shape != (40,)
            or arrays["y_nm"].shape != (20,)
            or len(plane_roles) != 7
            or len(arrays["z_nm"]) != 7
        ):
            raise RuntimeError("Task039 H diagnostic requires seven ordered planes.")
        if (
            not np.isclose(arrays["z_nm"][0], 10.0)
            or not np.isclose(arrays["z_nm"][-1], 110.0)
            or not np.all(np.diff(arrays["z_nm"]) > 0.0)
        ):
            raise RuntimeError("Task039 H diagnostic z planes must be increasing.")
        if any(not np.all(np.isfinite(value)) for value in arrays.values()):
            raise RuntimeError("Task039 H diagnostic payload contains non-finite data.")
        if offset_provenance.get("source") != "mesh_element_interior":
            raise RuntimeError("Task039 H diagnostic offset provenance is invalid.")
        run_dir.mkdir(parents=True, exist_ok=True)
        payload_path = run_dir / "task039_h_diagnostic_payload.npz"
        metadata_path = run_dir / "task039_h_diagnostic_payload.json"
        np.savez(payload_path, **arrays)
        descriptor = {
            "schema": "task039.hybrid-h-diagnostic.v1",
            "path": payload_path.name,
            "metadata_path": metadata_path.name,
            "sha256": _sha256(payload_path),
            "bytes": payload_path.stat().st_size,
            "keys": list(_TASK039_H_DIAGNOSTIC_KEYS),
            "plane_roles": list(plane_roles),
            "offset_provenance": dict(offset_provenance),
            "curl_source": "complete_reconstructed_field_analytic_or_fe",
            "ordinary_path_changed": False,
            "solver_equation_unchanged": True,
            "flux": {
                "formula": "0.5*Re((E x conj(H))_z)",
                "units": "W_per_m2",
                "sampling": "mean over x/y samples per plane",
            },
            "energy": {
                "formula": "0.25*(epsilon0*|E|^2+mu0*|H|^2)",
                "units": "J_per_m3",
                "kind": "vacuum_weighted_field_energy_proxy",
                "volume_integral": False,
            },
            "arrays": {
                key: {
                    "shape": list(value.shape),
                    "dtype": str(value.dtype),
                    "bytes": int(value.nbytes),
                    "sha256": _task039_array_sha256(value),
                    "finite": True,
                }
                for key, value in arrays.items()
            },
        }
        metadata_path.write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        descriptor["metadata_sha256"] = _sha256(metadata_path)
        descriptor["metadata_bytes"] = metadata_path.stat().st_size
    return comm.bcast(descriptor, root=0)


def _parse_args(
    argv: list[str] | None = None,
    *,
    allow_task039: bool = False,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase6 real-QEP hybrid augmented direct diagnostic"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--degree", type=int, choices=(1, 2, 3, 4, 6), default=2)
    parser.add_argument(
        "--modal-h-nm",
        type=float,
        help=(
            "Optional independent cross-section QEP mesh size. The local 3D "
            "FEM mesh remains controlled by --h-nm."
        ),
    )
    parser.add_argument(
        "--modal-degree",
        type=int,
        choices=(1, 2, 3, 4, 6),
        help=(
            "Optional independent cross-section QEP polynomial degree. The "
            "local 3D FEM degree remains controlled by --degree."
        ),
    )
    parser.add_argument(
        "--internal-propagation-model",
        choices=("continuous_beta", "full3d_uniform_cg"),
        default="continuous_beta",
        help=(
            "Axial propagation used between the two Hybrid interfaces. "
            "full3d_uniform_cg is an explicit same-p/h Full3D closure audit "
            "qualified only for a fixed rectangular, axis-aligned affine "
            "tensor-hexa mesh with uniform middle-region z spacing, one "
            "axial h, p1-p6, complex128, Floquet and sparse auxiliary DtN; "
            "nonuniform/local-h/curved/mixed meshes fail closed. "
            "continuous_beta remains the ordinary default."
        ),
    )
    traction_choices = (
        "continuous_qep_beta",
        "scalar_cg_discrete_derivative",
    )
    if allow_task039:
        traction_choices += ("full3d_one_cell_exact_schur",)
    parser.add_argument(
        "--internal-traction-model",
        choices=traction_choices,
        default="continuous_qep_beta",
        help=(
            "Modal interface traction symbol. The scalar-CG derivative is an "
            "explicit diagnostic and requires full3d_uniform_cg propagation "
            "under the same uniform-z affine-hexa qualification scope; "
            "unsupported meshes fail closed without fallback. "
            "continuous_qep_beta remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=(
            STANDARD_FULL_ASSEMBLY_BACKEND,
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        ),
        default=STANDARD_FULL_ASSEMBLY_BACKEND,
        help=(
            "Single public local-FE assembly port. Static condensation is "
            "explicit opt-in; standard_full remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--full3d-reference",
        type=Path,
        help=(
            "Optional explicit same-p/h full3D descriptor. This is required "
            "for review-v5 coarse p3 candidates that are not in the legacy "
            "reference registry."
        ),
    )
    parser.add_argument("--full3d-reference-sha256")
    parser.add_argument(
        "--task035c-p6-h10-gate",
        action="store_true",
        help=(
            "Explicitly open only the fixed-rectangular Task035c p6/h10 "
            "M120/M160 Hybrid path. Ordinary defaults remain unchanged."
        ),
    )
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument("--bottom-interface-nm", type=float, default=10.0)
    parser.add_argument("--top-interface-nm", type=float, default=110.0)
    parser.add_argument("--graded-reference-h", type=float, choices=(5.0, 3.0))
    parser.add_argument("--graded-coarse-factor", type=float, default=2.0)
    parser.add_argument(
        "--graded-profile",
        choices=("mechanism", "conservative", "balanced", "aggressive"),
        default="mechanism",
    )
    parser.add_argument("--incident-grazing-deg", type=float, default=10.0)
    parser.add_argument(
        "--polarization-kind",
        choices=("s", "p"),
        default="s",
    )
    parser.add_argument("--requested-modes", type=int, default=2)
    parser.add_argument(
        "--candidate-modes",
        type=int,
        help=(
            "QEP candidate count per target branch before passive-direction filtering. "
            "Default keeps M for M<=6 and uses 2M for wider funnels."
        ),
    )
    parser.add_argument("--near-degenerate-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--block-rotation-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument(
        "--memory-stages",
        type=Path,
        help="Optional JSONL stage marker consumed by the external memory sampler.",
    )
    parser.add_argument(
        "--compare-modal-schur",
        action="store_true",
        help="Also build the Phase7 multi-RHS modal-Schur direct path and compare it with augmented.",
    )
    parser.add_argument(
        "--comparison-solver-path",
        choices=("fast", "minimal"),
        default="fast",
        help=(
            "Modal-Schur builder used by --compare-modal-schur. The fast default "
            "preserves Task32 behavior; Task33 formal comparisons use minimal."
        ),
    )
    parser.add_argument(
        "--solver-path",
        choices=("augmented", "modal-schur-fast", "modal-schur-memory-minimal"),
        default="augmented",
        help=(
            "Primary direct solve lifecycle. Non-augmented choices are standalone "
            "Phase10 memory paths and never retain the monolithic augmented factor."
        ),
    )
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default=(
            "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
        ),
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    args = parser.parse_args(argv)
    if (
        args.internal_traction_model == "full3d_one_cell_exact_schur"
        and not allow_task039
    ):
        parser.error(
            "full3d_one_cell_exact_schur is restricted to the Task39 Python opt-in."
        )
    if args.degree == 6 and not args.task035c_p6_h10_gate and not allow_task039:
        parser.error(
            "p6 is fail-closed; pass --task035c-p6-h10-gate for the fixed "
            "Task035c p6/h10 Hybrid authority only."
        )
    if allow_task039:
        scoped = bool(
            not args.task035c_p6_h10_gate
            and not args.allow_dirty_research
            and args.degree == 6
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and (
                (
                    np.isclose(args.h_nm, 10.0)
                    and np.isclose(args.modal_h_nm, 10.0)
                    and args.requested_modes in (120, 240, 480, 960)
                )
                or (
                    np.isclose(args.h_nm, 5.0)
                    and np.isclose(args.modal_h_nm, 5.0)
                    and args.requested_modes == 480
                )
            )
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "augmented"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend
            == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            and args.graded_reference_h is None
            and np.isclose(args.bottom_interface_nm, 10.0)
            and np.isclose(args.top_interface_nm, 110.0)
            and (
                np.isclose(args.incident_grazing_deg, 10.0)
                or (
                    np.isclose(args.h_nm, 5.0)
                    and np.isclose(args.modal_h_nm, 5.0)
                    and args.requested_modes == 480
                    and np.isclose(args.incident_grazing_deg, 1.0)
                )
            )
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "full3d_one_cell_exact_schur"
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.task035c_p6_preflight_authority is None
            and args.task035c_p6_preflight_sha256 is None
            and args.full3d_reference is None
            and args.full3d_reference_sha256 is None
        )
        if not scoped:
            parser.error(
                "Task39 Hybrid direct is restricted to historical p6/h10 with "
                "modal h10 and numeric M120/240/480/960, or formal p6/h5 with "
                "modal h5 and M480 at 10 or 1 degree; both require 2M "
                "candidates, static-condensed full3d_uniform_cg, exact one-cell "
                "traction, 10/110 interfaces, and a clean verified source."
            )
        return args
    if args.task035c_p6_h10_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes in TASK035C_P6_H10_MODE_COUNTS
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend in TASK035C_P6_H10_BACKENDS
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.allow_dirty_research
        )
        if not scoped:
            parser.error(
                "--task035c-p6-h10-gate is restricted to clean-source fixed "
                "rectangular p6/h10 S-polarized Hybrid M120/M160, explicit "
                "modal p6/h10, exact 2M pool, modal-schur-memory-minimal, "
                "the qualified discrete axial propagation/traction pair, "
                "10/110 nm interfaces, standard/static backend, and "
                "hash-bound historical and matching Full3D authorities."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
        or args.full3d_reference_sha256 is not None
    ):
        parser.error("Task035c authority SHA arguments require --task035c-p6-h10-gate.")
    return args


def _task035c_worker_authority_gate(
    args: argparse.Namespace,
    *,
    current_source_sha: str | None,
    mpi_size: int,
) -> dict[str, Any] | None:
    if not args.task035c_p6_h10_gate:
        return None

    authority_path = args.task035c_p6_preflight_authority
    reference_path = args.full3d_reference
    if authority_path is None or reference_path is None:
        raise SystemExit("Task035c p6/h10 authority paths are required.")
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    reference_path = (
        reference_path if reference_path.is_absolute() else ROOT / reference_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 historical authority is unreadable: {exc}"
        ) from exc
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 Full3D reference is unreadable: {exc}"
        ) from exc
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_is_tracked = bool(
        authority_relative is not None
        and _git("ls-files", "--error-unmatch", "--", authority_relative) is not None
    )
    preflight_gate = task035c_p6_h10_preflight_authority_gate(
        authority if isinstance(authority, dict) else None,
        expected_sha256=args.task035c_p6_preflight_sha256,
        observed_sha256=_sha256(authority_path),
        authority_is_tracked=authority_is_tracked,
    )
    reference_gate = task035c_p6_h10_full3d_reference_gate(
        reference if isinstance(reference, dict) else None,
        expected_sha256=args.full3d_reference_sha256,
        observed_sha256=_sha256(reference_path),
        current_source_sha=current_source_sha,
        assembly_backend=args.stage4_full3d_assembly_backend,
        mpi_size=mpi_size,
    )
    gate = {
        "schema_version": "task035c.p6-h10-worker-authority-gate.v1",
        "pass": bool(preflight_gate["pass"] and reference_gate["pass"]),
        "historical_preflight": {
            **preflight_gate,
            "path": str(authority_path),
        },
        "matching_full3d_reference": {
            **reference_gate,
            "path": str(reference_path),
        },
    }
    gate["failures"] = [
        *(
            []
            if preflight_gate["pass"]
            else [
                f"historical_preflight:{failure}"
                for failure in preflight_gate["failures"]
            ]
        ),
        *(
            []
            if reference_gate["pass"]
            else [
                f"matching_full3d_reference:{failure}"
                for failure in reference_gate["failures"]
            ]
        ),
    ]
    if not gate["pass"]:
        raise SystemExit(f"Task035c p6/h10 worker authority failed: {gate['failures']}")
    return gate


def _task039_write_trace_capture_mpi(
    comm: Any,
    capture: Mapping[str, Any],
    output_dir: str | Path,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Write the research capture on rank zero and broadcast one result."""

    result: dict[str, Any] | None = None
    if comm.rank == 0:
        from benchmarks.task039_trace_audit import write_trace_audit_capture

        try:
            result = {
                "ok": True,
                "descriptor": write_trace_audit_capture(
                    capture, output_dir, metadata=metadata
                ),
            }
        except Exception as error:
            result = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    result = comm.bcast(result, root=0)
    if not result["ok"]:
        raise RuntimeError(
            f"Task039 trace evidence writer failed on rank 0: {result['error']}"
        )
    return result["descriptor"]


def main(
    argv: list[str] | None = None,
    *,
    config_override: Any | None = None,
    use_case080_reference: bool = True,
    canonical_export_prefix: str | None = None,
    external_mode_inventory: Mapping[str, Any] | None = None,
    exact_one_cell_work_dir: str | Path | None = None,
    qep_solver_tolerance: float = 1.0e-10,
    trace_audit_capture_dir: str | Path | None = None,
    trace_audit_metadata: Mapping[str, Any] | None = None,
    canonical_trace_gate_policy: str | None = None,
    canonical_trace_family_sha256: str | None = None,
    task039_stage_marker_path: str | Path | None = None,
) -> dict[str, Any]:
    command_argv = list(sys.argv[1:] if argv is None else argv)
    allow_task039 = bool(
        config_override is not None
        and str(getattr(config_override, "case_name", "")).startswith("task039_5nm")
    )
    args = _parse_args(argv, allow_task039=allow_task039)
    if args.h_nm <= 0.0:
        raise SystemExit("--h-nm must be positive.")
    modal_h_nm = float(args.h_nm) if args.modal_h_nm is None else float(args.modal_h_nm)
    modal_degree = (
        int(args.degree) if args.modal_degree is None else int(args.modal_degree)
    )
    if modal_h_nm <= 0.0:
        raise SystemExit("--modal-h-nm must be positive.")
    if not (0.0 < args.bottom_interface_nm < args.top_interface_nm < 120.0):
        raise SystemExit(
            "Task33 buffer interfaces must satisfy "
            "0 < bottom-interface-nm < top-interface-nm < 120."
        )
    if args.graded_reference_h is not None:
        if args.modal_h_nm is not None or args.modal_degree is not None:
            raise SystemExit(
                "Independent modal h/p is not combined with the Task034 "
                "graded local-mesh research path."
            )
        if args.degree not in (2, 3):
            raise SystemExit("The Task034 fixed-p graded path is restricted to p2/p3.")
        if args.bottom_interface_nm != 10.0 or args.top_interface_nm != 110.0:
            raise SystemExit(
                "The first Task033 graded path is qualified only at the "
                "reviewed 10/110 nm matching interfaces."
            )
        if not np.isclose(args.h_nm, args.graded_reference_h):
            raise SystemExit("--h-nm must equal --graded-reference-h.")
        if args.graded_coarse_factor <= 1.0:
            raise SystemExit("--graded-coarse-factor must be greater than one.")
    if not 0.0 < args.incident_grazing_deg < 90.0:
        raise SystemExit("--incident-grazing-deg must lie strictly between 0 and 90.")
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least 2.")
    candidate_modes = (
        int(args.candidate_modes)
        if args.candidate_modes is not None
        else (
            int(args.requested_modes)
            if args.requested_modes <= 6
            else 2 * int(args.requested_modes)
        )
    )
    if candidate_modes < args.requested_modes:
        raise SystemExit("--candidate-modes must be at least --requested-modes.")
    if args.near_degenerate_tolerance <= 0.0:
        raise SystemExit("--near-degenerate-tolerance must be positive.")
    if args.block_rotation_tolerance <= 0.0:
        raise SystemExit("--block-rotation-tolerance must be positive.")
    if args.compare_modal_schur and args.solver_path != "augmented":
        raise SystemExit("--compare-modal-schur requires --solver-path augmented.")
    if (
        args.internal_traction_model == "scalar_cg_discrete_derivative"
        and args.internal_propagation_model != "full3d_uniform_cg"
    ):
        raise SystemExit(
            "scalar_cg_discrete_derivative traction requires "
            "--internal-propagation-model full3d_uniform_cg."
        )
    task33_variant = bool(
        args.degree != 2
        or modal_degree != args.degree
        or not np.isclose(modal_h_nm, args.h_nm)
        or args.bottom_interface_nm != 10.0
        or args.top_interface_nm != 110.0
        or args.graded_reference_h is not None
        or not np.isclose(args.incident_grazing_deg, 10.0)
        or args.polarization_kind != "s"
        or args.internal_propagation_model != "continuous_beta"
        or args.internal_traction_model != "continuous_qep_beta"
    )
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    if args.task035c_p6_h10_gate and comm.size not in TASK035C_P6_H10_MPI_SIZES:
        raise SystemExit("Task035c p6/h10 Hybrid is restricted to MPI1/2/4/8.")
    task035c_p6_gate = _task035c_worker_authority_gate(
        args,
        current_source_sha=provenance.get("commit_sha"),
        mpi_size=comm.size,
    )

    if comm.rank == 0 and args.memory_stages is not None:
        args.memory_stages.parent.mkdir(parents=True, exist_ok=True)
        args.memory_stages.unlink(missing_ok=True)
    formal_stage_marker_path = (
        None if task039_stage_marker_path is None else Path(task039_stage_marker_path)
    )
    detail_marker_path = (
        None
        if formal_stage_marker_path is None
        else formal_stage_marker_path.with_name("memory_detail_markers.raw.jsonl")
    )
    if comm.rank == 0 and formal_stage_marker_path is not None:
        formal_stage_marker_path.parent.mkdir(parents=True, exist_ok=True)
        formal_stage_marker_path.unlink(missing_ok=True)
        detail_marker_path.unlink(missing_ok=True)
    comm.barrier()

    def mark_stage(stage: str) -> None:
        if comm.rank == 0 and args.memory_stages is not None:
            elapsed = time.perf_counter() - total_started
            payload = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "elapsed_seconds": elapsed,
            }
            with args.memory_stages.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")

    task039_e10_events: list[dict[str, Any]] = []

    def task039_memory_detail_marker(name: str, detail: Mapping[str, Any]) -> None:
        if detail_marker_path is None or comm.rank != 0:
            return
        payload = {
            "schema": "task039.v3-memory-detail-marker.v2",
            "marker_type": "memory_detail",
            "name": name,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - total_started,
            "elapsed_origin": "worker_run_task032_total_started_perf_counter",
            "detail": dict(detail),
        }
        with detail_marker_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            stream.flush()

    def task039_post_destroy_cleanup() -> Mapping[str, Any]:
        from benchmarks.run_task037b_hybrid_iterative import collective_heap_cleanup

        return collective_heap_cleanup(comm)

    def task039_mark_stage(
        stage: str, *, detail: Mapping[str, Any] | None = None
    ) -> None:
        if canonical_export_prefix != "task039_direct" or comm.rank != 0:
            return
        elapsed = time.perf_counter() - total_started
        target_stage = task039_stage_target(
            stage, formal_v2_h5=formal_stage_marker_path is not None
        )
        if target_stage is None:
            return
        if formal_stage_marker_path is not None:
            formal_detail = dict(detail or {})
            if stage in {"positive_qep_solve_peak", "negative_qep_solve_peak"}:
                formal_detail.update(
                    {
                        "marker_is_interval_start": True,
                        "marker_semantics": (
                            "solve interval start; marker is not a peak value"
                        ),
                        "peak_source": "subsequent_0.25s_process_tree_samples",
                    }
                )
            event = task039_v2_h5_stage_event(
                target_stage,
                elapsed_seconds=elapsed,
                detail=formal_detail,
            )
            with formal_stage_marker_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                stream.flush()
            return
        if args.memory_stages is None:
            return
        event = task039_e10_stage_event(
            target_stage, elapsed_seconds=elapsed, detail=detail
        )
        task039_e10_events.append(event)
        with args.memory_stages.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
        event_path = args.memory_stages.with_name(
            args.memory_stages.stem + ".task039_e10.jsonl"
        )
        with event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()

    def progress(message: str) -> None:
        if comm.rank == 0:
            print(message, flush=True)

    total_started = time.perf_counter()
    task039_mark_stage(
        "baseline_before_mesh",
        detail={"marker_semantics": "formal lifecycle start; not a memory peak"},
    )
    timings: dict[str, float] = {}
    if config_override is None:
        cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
        cfg.stage4_full3d_assembly_backend = args.stage4_full3d_assembly_backend
        cfg.matrix_diagnostics_assemble_only = False
        cfg.matrix_diagnostics_factorization_only = False
        cfg.incident_theta_deg = 90.0 - float(args.incident_grazing_deg)
        cfg.polarization_kind = args.polarization_kind
        modal_cfg = target_stage4_config(
            degree=modal_degree,
            h_nm=modal_h_nm,
        )
        modal_cfg.incident_theta_deg = cfg.incident_theta_deg
        modal_cfg.incident_phi_deg = cfg.incident_phi_deg
        modal_cfg.polarization_kind = cfg.polarization_kind
    else:
        cfg = deepcopy(config_override)
        if (
            cfg.nedelec_degree != args.degree
            or not np.isclose(cfg.mesh_target_size, args.h_nm)
            or modal_degree != cfg.nedelec_degree
            or not np.isclose(modal_h_nm, cfg.mesh_target_size)
            or not np.isclose(cfg.incident_theta_deg, 90.0 - args.incident_grazing_deg)
            or cfg.polarization_kind != args.polarization_kind
            or cfg.stage4_full3d_assembly_backend != args.stage4_full3d_assembly_backend
        ):
            raise SystemExit(
                "Task38 config override does not match the explicit runner argv."
            )
        modal_cfg = deepcopy(cfg)
    operators = None
    positive = None
    negative = None
    bottom = None
    top = None
    coupling = None
    system = None
    solution = None
    schur_system = None
    schur_solution = None
    primary_schur_system = None
    record = None
    opt_in_canonical_exports = None
    graded_plan = None
    graded_bottom_mesh = None
    graded_top_mesh = None

    def finite_spectrum_capacity_record(
        *,
        direction: str,
        selection,
        solver_report,
    ) -> dict[str, Any]:
        """Preserve a clean measured negative when singular K2 yields infinity roots."""

        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        case = {
            "material_kind": "stage4_xy",
            "degree": args.degree,
            "h_nm": args.h_nm,
            "modal_degree": modal_degree,
            "modal_h_nm": modal_h_nm,
            "internal_propagation_model": (args.internal_propagation_model),
            "internal_traction_model": args.internal_traction_model,
            "discrete_axial_qualification_scope": (
                _discrete_axial_qualification_scope(
                    args.internal_propagation_model,
                    args.internal_traction_model,
                )
            ),
            "requested_modes_per_direction": args.requested_modes,
            "candidate_modes_per_target_branch": candidate_modes,
            "near_degenerate_tolerance": args.near_degenerate_tolerance,
            "block_rotation_tolerance": args.block_rotation_tolerance,
            "bottom_interface_nm": args.bottom_interface_nm,
            "top_interface_nm": args.top_interface_nm,
            "middle_length_nm": args.top_interface_nm - args.bottom_interface_nm,
            "wavelength_nm": cfg.lambda0,
            "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
            "polarization_kind": cfg.polarization_kind,
            "mesh_policy": "reviewed_stage4_axis_plan",
            "graded_reference_h_nm": args.graded_reference_h,
            "graded_coarse_factor": None,
            "graded_plan_hash": None,
            "graded_plan": None,
        }
        selection_record = _directional_selection_summary(selection)
        capacity = {
            "status": "insufficient_finite_admissible_modes",
            "direction": direction,
            "requested_modes_per_direction": args.requested_modes,
            "delivered_finite_admissible_modes": selection.selected_modes,
            "finite_candidate_count_both_directions": (
                selection.finite_candidate_count
            ),
            "numerically_infinite_candidate_count": (
                selection.numerically_infinite_candidate_count
            ),
            "finite_spectrum_abs_beta_h_cutoff": (NUMERICAL_INFINITY_BETA_H_CUTOFF),
            "finite_spectrum_abs_beta_cutoff_per_nm": (selection.abs_beta_cutoff),
            "first_rejected_numerical_infinity_beta_per_nm": (
                selection_record["first_rejected_numerical_infinity_beta_per_nm"]
            ),
            "leading_coefficient_singular_by_design": (
                operators.leading_coefficient_singular_by_design
            ),
            "pair_tolerance_relaxed": False,
            "left_pair_relative_error_tolerance": 1.0e-7,
        }
        return {
            "schema_version": 1,
            "benchmark_id": "task033_hybrid_modal_basis_capacity",
            "timestamp_utc": timestamp,
            "status": "insufficient_finite_admissible_modes",
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in command_argv),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
                "internal_propagation_model_requested": (
                    args.internal_propagation_model
                ),
                "internal_traction_model_requested": (args.internal_traction_model),
                "stage4_full3d_assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "task035c_p6_h10_authority_gate": task035c_p6_gate,
                "task33_variant": True,
                "provenance": (
                    "clean_task033_finite_spectrum_capacity_negative"
                    if not provenance["tracked_source_dirty"]
                    else "dirty_task033_finite_spectrum_capacity_research"
                ),
            },
            "case": case,
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "quadrature_policy": operators.quadrature_policy,
                f"{direction}_solver_converged_modes": (solver_report.converged_modes),
                f"{direction}_directional_selection": selection_record,
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "dense_interface_square_formed": False,
                "full_field_or_mode_gathered": False,
            },
            "solve": {"true_relative_residual": None},
            "validation": {
                "port_power": None,
                "external_diffraction_orders": None,
            },
            "physical_field_reconstruction": None,
            "modal_schur_comparison": None,
            "object_payload_ledger": {
                "mode_count_per_direction": selection.selected_modes,
                "storage_complexity_contract": "O(N_interface*M)+O(M^2)",
                "dense_interface_square_formed": False,
            },
            "full3d_reference_comparison": None,
            "gates": {"finite_admissible_mode_capacity": False},
            "qualification": {
                "integration_pass": False,
                "algebraic_chain_pass": False,
                "task033_physical_truncation_allowed": False,
                "clean_source_integration_record": False,
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "physical_field_gates_pass": False,
                "modal_basis_capacity_pass": False,
                "capacity_disposition": "insufficient_finite_admissible_modes",
                "official_record": False,
                "boundary": (
                    "Measured finite-spectrum capacity negative; numerical-infinity "
                    "roots from singular K2 are rejected before adjoint pairing."
                ),
            },
            "modal_basis_capacity": capacity,
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }

    try:
        mark_stage("cross_section_eigen_assembly")
        started = time.perf_counter()
        if args.graded_reference_h is not None:
            from src.geometry.task034_adaptive_mesh import (
                Task034Stage4Geometry,
                build_task034_conforming_graded_plan,
                build_task034_graded_local_mesh_pair,
            )

            graded_plan = build_task034_conforming_graded_plan(
                reference_h_nm=args.graded_reference_h,
                geometry=Task034Stage4Geometry.from_config(
                    cfg,
                    bottom_interface_z_nm=args.bottom_interface_nm,
                    top_interface_z_nm=args.top_interface_nm,
                ),
                profile=args.graded_profile,
                coarse_factor=args.graded_coarse_factor,
                comm_size=comm.size,
            )
            graded_bottom_mesh, graded_top_mesh = build_task034_graded_local_mesh_pair(
                cfg, graded_plan
            )
            cross_section = build_matching_cross_section(
                cfg,
                "stage4_xy",
                x_values=graded_plan.x_values,
                y_values=graded_plan.y_values,
            )
        else:
            cross_section = build_matching_cross_section(
                modal_cfg,
                "stage4_xy",
            )
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=modal_degree
        )
        operators = assemble_quadratic_beta_operators(modal_cfg, cross_section, spaces)
        task039_mark_stage("mesh_spaces_ready")
        task039_mark_stage("qep_matrices_ready")
        poynting_evaluator = PoyntingFluxEvaluator(modal_cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(modal_cfg, modal_cfg.n_air)
        timings["cross_section_and_qep_assembly"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: cross-section QEP assembled")

        mark_stage("cross_section_eigen_solve")
        started = time.perf_counter()
        task039_mark_stage(
            "positive_qep_solve_peak",
            detail={
                "marker_semantics": (
                    "solve interval boundary; peak is derived from subsequent "
                    "watchdog interval samples, not this marker"
                )
            },
        )
        positive_right, positive_report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=candidate_modes,
            tolerance=qep_solver_tolerance,
        )
        progress("Task32 Phase6: positive right QEP modes complete")
        positive_right, positive_selection = select_passive_direction_modes(
            positive_right,
            desired_direction="forward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(NUMERICAL_INFINITY_BETA_H_CUTOFF / modal_h_nm),
        )
        if len(positive_right) != args.requested_modes:
            for mode in positive_right:
                mode.destroy()
            if positive_selection.numerically_infinite_candidate_count:
                record = finite_spectrum_capacity_record(
                    direction="positive",
                    selection=positive_selection,
                    solver_report=positive_report,
                )
                raise _ModalBasisCapacityStop
            raise RuntimeError(
                "Positive finite candidate pool did not deliver enough passive "
                f"forward modes: {positive_selection.direction_counts}."
            )
        mark_stage("mode_classification")
        positive = build_biorthogonal_mode_basis(
            modal_cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=candidate_modes,
            qep_solver_tolerance=qep_solver_tolerance,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
        progress("Task32 Phase6: positive adjoint basis complete")
        task039_mark_stage(
            "negative_qep_solve_peak",
            detail={
                "marker_semantics": (
                    "solve interval boundary; peak is derived from subsequent "
                    "watchdog interval samples, not this marker"
                )
            },
        )
        negative_right, negative_report = solve_quadratic_beta_modes(
            operators,
            target=-target,
            requested_modes=candidate_modes,
            tolerance=qep_solver_tolerance,
        )
        progress("Task32 Phase6: negative right QEP modes complete")
        negative_right, negative_selection = select_passive_direction_modes(
            negative_right,
            desired_direction="backward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(NUMERICAL_INFINITY_BETA_H_CUTOFF / modal_h_nm),
        )
        if len(negative_right) != args.requested_modes:
            for mode in negative_right:
                mode.destroy()
            if negative_selection.numerically_infinite_candidate_count:
                record = finite_spectrum_capacity_record(
                    direction="negative",
                    selection=negative_selection,
                    solver_report=negative_report,
                )
                raise _ModalBasisCapacityStop
            raise RuntimeError(
                "Negative finite candidate pool did not deliver enough passive "
                f"backward modes: {negative_selection.direction_counts}."
            )
        task039_mark_stage("raw_candidate_eigenvectors_ready")
        negative = build_biorthogonal_mode_basis(
            modal_cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=candidate_modes,
            qep_solver_tolerance=qep_solver_tolerance,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
        task039_mark_stage("selected_biorthogonal_bases_ready")
        progress("Task32 Phase6: negative adjoint basis complete")
        progress(
            "Task32 Phase6: delivered basis counts "
            f"positive={len(positive.modes)}/{positive_report.converged_modes}, "
            f"negative={len(negative.modes)}/{negative_report.converged_modes}"
        )
        preview_count = min(len(positive.modes), 12)
        progress(
            "Task32 Phase6: positive beta preview "
            f"{[complex(mode.beta) for mode in positive.modes[:preview_count]]} "
            f"(showing {preview_count}/{len(positive.modes)})"
        )
        progress(
            "Task32 Phase6: positive near-degenerate group count "
            f"{len(positive.groups)}; first groups="
            f"{[group.indices for group in positive.groups[:8]]}"
        )
        pairs = pair_reciprocal_mode_bases(operators, positive, negative)
        timings["positive_and_negative_biorthogonal_bases"] = _max_elapsed(
            comm, started
        )
        progress("Task32 Phase6: real positive/negative QEP bases complete")

        mark_stage("local_fem_dtn_assembly")
        started = time.perf_counter()
        bottom = assemble_hybrid_local_dtn_system(
            cfg,
            "bottom",
            bottom_interface_z_nm=args.bottom_interface_nm,
            top_interface_z_nm=args.top_interface_nm,
            local_mesh_override=graded_bottom_mesh,
        )
        top = assemble_hybrid_local_dtn_system(
            cfg,
            "top",
            bottom_interface_z_nm=args.bottom_interface_nm,
            top_interface_z_nm=args.top_interface_nm,
            local_mesh_override=graded_top_mesh,
        )
        timings["two_local_fem_dtn_systems"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: bottom/top local FEM-DtN systems complete")

        if trace_audit_capture_dir is not None:
            if canonical_export_prefix != "task039_direct":
                raise ValueError(
                    "Trace audit capture requires the explicit Task039 direct opt-in."
                )
            if args.requested_modes not in (120, 240, 480, 960):
                raise ValueError("Trace audit capture supports only M=120/240/480/960.")
            capture = capture_hybrid_trace_audit(
                spaces,
                positive,
                negative,
                bottom,
                top,
                log=progress,
            )
            stage_event_path = args.memory_stages
            stage_ledger_path = (
                None
                if stage_event_path is None
                else stage_event_path.with_name(
                    stage_event_path.stem + ".task039_e10.json"
                )
            )
            descriptor = _task039_write_trace_capture_mpi(
                comm,
                capture,
                trace_audit_capture_dir,
                {
                    "requested_modes_per_direction": args.requested_modes,
                    "mesh_target_size_nm": float(args.h_nm),
                    "mpi_size": comm.size,
                    "trace_audit_stage_events": {
                        "event_path": (
                            None if stage_event_path is None else str(stage_event_path)
                        ),
                        "e10_ledger_path": (
                            None
                            if stage_ledger_path is None
                            else str(stage_ledger_path)
                        ),
                    },
                    **dict(trace_audit_metadata or {}),
                },
            )
            task039_mark_stage(
                "canonical_negative_traces_ready",
                detail={
                    "source": "research_trace_capture",
                    "marker_semantics": "captured audit arrays; not a solver-ready trace",
                },
            )
            task039_mark_stage(
                "projection_matrices_ready",
                detail={
                    "source": "research_trace_capture",
                    "marker_semantics": "captured Gram/raw/canonical arrays only",
                },
            )
            task039_mark_stage(
                "local_fe_dtn_systems_ready",
                detail={
                    "source": "systems_assembled_before_capture",
                    "marker_semantics": "ordered capture boundary; not a new build",
                },
            )
            record = {
                "schema": "task039.review-v1.m960-trace-controlled-stop.v1",
                "status": "controlled_stop",
                "trace_audit_capture": descriptor,
                "trace_audit_stage_events": {
                    "event_path": (
                        None if stage_event_path is None else str(stage_event_path)
                    ),
                    "e10_ledger_path": (
                        None if stage_ledger_path is None else str(stage_ledger_path)
                    ),
                },
                "provenance": provenance,
                "case": {
                    "requested_modes_per_direction": args.requested_modes,
                    "mesh_target_size_nm": float(args.h_nm),
                    "nedelec_degree": int(args.degree),
                },
                "qualification": {
                    "integration_pass": False,
                    "official_record": False,
                    "trace_capture_only": True,
                    "solve_entered": False,
                    "exact_traction_entered": False,
                },
            }
            raise _Task039TraceAuditStop(record)

        mark_stage("interface_projection_and_coupling")
        started = time.perf_counter()
        coupling = build_hybrid_internal_mode_coupling(
            cfg,
            spaces,
            positive,
            negative,
            bottom,
            top,
            length_nm=args.top_interface_nm - args.bottom_interface_nm,
            propagation_model=args.internal_propagation_model,
            modal_traction_model=args.internal_traction_model,
            exact_one_cell_work_dir=exact_one_cell_work_dir,
            canonical_trace_gate_policy=canonical_trace_gate_policy,
            canonical_trace_family_sha256=canonical_trace_family_sha256,
            stage_callback=(
                task039_memory_detail_marker if detail_marker_path is not None else None
            ),
            post_destroy_cleanup=(
                task039_post_destroy_cleanup if detail_marker_path is not None else None
            ),
            log=progress,
        )
        timings["internal_modal_coupling"] = _max_elapsed(comm, started)
        task039_mark_stage(
            "canonical_negative_traces_ready",
            detail={
                "source": "coupling_complete_boundary",
                "marker_semantics": "coupling-complete boundary; not an RSS/PSS/USS peak",
            },
        )
        task039_mark_stage(
            "projection_matrices_ready", detail={"source": "coupling_output"}
        )
        task039_mark_stage(
            "traction_matrices_ready", detail={"source": "coupling_output"}
        )
        task039_mark_stage(
            "local_fe_dtn_systems_ready",
            detail={
                "source": "local_systems_built_before_coupling",
                "marker_emitted_at_ordered_coupling_boundary": True,
            },
        )
        started = time.perf_counter()
        if args.solver_path == "augmented":
            mark_stage("augmented_matrix_and_factor")
            system = build_hybrid_augmented_direct_system(bottom, top, coupling)
            timings["primary_system_build"] = _max_elapsed(comm, started)
            timings["monolithic_assembly"] = timings["primary_system_build"]
            task039_mark_stage("hybrid_augmented_operator_ready")
            task039_mark_stage(
                "mumps_analysis_ready_when_available",
                detail={
                    "status": "not_available",
                    "classification": "not_available",
                    "reason": "runner exposes no separate analysis-only snapshot",
                },
            )
            progress("Task32 Phase6: monolithic augmented AIJ complete")
            solution = solve_hybrid_augmented_direct(
                system,
                bottom,
                top,
                coupling,
            )
            task039_mark_stage(
                "direct_factor_or_iterative_side_factors_ready",
                detail={"source": "solution_ksp_holds_factor"},
            )
            task039_mark_stage("solution_ready")
        else:
            builder = (
                build_hybrid_modal_schur_direct_system
                if args.solver_path == "modal-schur-fast"
                else build_hybrid_modal_schur_memory_minimal_system
            )
            primary_schur_system = builder(
                bottom, top, coupling, stage_callback=mark_stage
            )
            timings["primary_system_build"] = _max_elapsed(comm, started)
            task039_mark_stage("direct_factor_or_iterative_side_factors_ready")
            task039_mark_stage("modal_schur_ready")
            progress(
                "Task32 Phase10: standalone "
                f"{primary_schur_system.lifecycle_strategy} Schur system complete"
            )
            solution = solve_hybrid_modal_schur_direct(
                primary_schur_system,
                bottom,
                top,
                coupling,
                stage_callback=mark_stage,
            )
        mark_stage("official_rta")
        validation = evaluate_hybrid_augmented_solution(
            cfg, bottom, top, coupling, solution
        )
        port_power = validation["port_power"]
        modal_schur_comparison = None
        if args.compare_modal_schur:
            started = time.perf_counter()
            comparison_builder = (
                build_hybrid_modal_schur_direct_system
                if args.comparison_solver_path == "fast"
                else build_hybrid_modal_schur_memory_minimal_system
            )
            comparison_solver_path = (
                "modal-schur-fast"
                if args.comparison_solver_path == "fast"
                else "modal-schur-memory-minimal"
            )
            schur_system = comparison_builder(bottom, top, coupling)
            timings["modal_schur_build"] = _max_elapsed(comm, started)
            schur_solution = solve_hybrid_modal_schur_direct(
                schur_system, bottom, top, coupling
            )
            schur_validation = evaluate_hybrid_augmented_solution(
                cfg, bottom, top, coupling, schur_solution
            )
            modal_difference = np.asarray(
                schur_solution.modal_amplitudes - solution.modal_amplitudes,
                dtype=np.complex128,
            )
            modal_scale = max(
                float(np.linalg.norm(schur_solution.modal_amplitudes)),
                float(np.linalg.norm(solution.modal_amplitudes)),
                1.0e-30,
            )
            rta_delta = {
                key: float(
                    schur_validation["port_power"][key] - validation["port_power"][key]
                )
                for key in ("R_total", "T_total", "A_balance")
            }
            comparison_gates = {
                "modal_coefficients_relative_error_le_1e-9": (
                    float(np.linalg.norm(modal_difference) / modal_scale) <= 1.0e-9
                ),
                "bottom_solution_relative_error_le_1e-9": (
                    _relative_vector_error(schur_solution.bottom, solution.bottom)
                    <= 1.0e-9
                ),
                "top_solution_relative_error_le_1e-9": (
                    _relative_vector_error(schur_solution.top, solution.top) <= 1.0e-9
                ),
                "modal_schur_full_residual_le_1e-9": (
                    schur_solution.relative_residual <= 1.0e-9
                    and schur_solution.modal_relative_residual <= 1.0e-9
                ),
                "rta_absolute_delta_le_1e-10": max(
                    abs(value) for value in rta_delta.values()
                )
                <= 1.0e-10,
                "no_dense_interface_square": (
                    not schur_system.dense_interface_square_formed
                ),
                "multi_rhs_single_factor_context_per_local_block": (
                    schur_system.multi_rhs_count == 2 * args.requested_modes + 1
                ),
            }
            modal_schur_comparison = {
                "status": ("pass" if all(comparison_gates.values()) else "failed"),
                "comparison_solver_path": comparison_solver_path,
                "comparison_solver_path_argument": (args.comparison_solver_path),
                "comparison_lifecycle_strategy": (schur_system.lifecycle_strategy),
                "multi_rhs_count": schur_system.multi_rhs_count,
                "modal_schur_shape": list(schur_system.modal_schur.shape),
                "modal_schur_bytes": int(schur_system.modal_schur.nbytes),
                "modal_schur_condition": schur_system.modal_schur_condition,
                "dense_interface_square_formed": (
                    schur_system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (
                    schur_system.full_field_or_mode_gathered
                ),
                "transient_dense_rhs_solution_bytes": (
                    schur_system.transient_dense_rhs_solution_bytes
                ),
                "factor_setup_seconds": schur_system.factor_setup_seconds,
                "multi_rhs_solve_seconds": schur_system.multi_rhs_solve_seconds,
                "modal_solve_seconds": schur_solution.modal_solve_seconds,
                "recovery_seconds": schur_solution.recovery_seconds,
                "residuals": {
                    "combined_relative": schur_solution.relative_residual,
                    "bottom_relative": schur_solution.bottom_relative_residual,
                    "top_relative": schur_solution.top_relative_residual,
                    "modal_relative": schur_solution.modal_relative_residual,
                },
                "augmented_vs_schur": {
                    "modal_coefficients_relative_error": float(
                        np.linalg.norm(modal_difference) / modal_scale
                    ),
                    "bottom_solution_relative_error": _relative_vector_error(
                        schur_solution.bottom, solution.bottom
                    ),
                    "top_solution_relative_error": _relative_vector_error(
                        schur_solution.top, solution.top
                    ),
                    "interface_e_projection_combined_residual_delta": float(
                        schur_validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                        - validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                    ),
                    "RTA_delta": rta_delta,
                },
                "gates": comparison_gates,
                "memory_comparison_semantics": (
                    "Correctness runner retains augmented and Schur factors concurrently; "
                    "its process peak is not a standalone Schur memory measurement."
                ),
            }
            progress(
                f"Task32 Phase7: {comparison_solver_path} direct comparison complete"
            )
        pinned_reference_case = (
            use_case080_reference
            and abs(args.incident_grazing_deg - 10.0) <= 1.0e-12
            and (args.polarization_kind == "s" or args.full3d_reference is not None)
        )
        explicit_reference = args.full3d_reference
        if explicit_reference is not None and not explicit_reference.is_absolute():
            explicit_reference = ROOT / explicit_reference
        reference_registry = (
            None
            if explicit_reference is None
            else {(args.degree, float(args.h_nm)): explicit_reference}
        )
        loaded_reference = (
            _load_case080_reference(
                args.degree,
                args.h_nm,
                reference_by_degree_and_h=reference_registry,
                polarization_kind=args.polarization_kind,
            )
            if pinned_reference_case
            else None
        )
        reference = (
            _reference_comparison(loaded_reference, port_power)
            if pinned_reference_case
            else None
        )
        reference_archive = (
            _reference_archive(loaded_reference) if pinned_reference_case else None
        )
        if reference_archive is not None:
            archive_path, reference_record_path, reference_record = reference_archive
            with np.load(archive_path) as archive:
                sample_x = np.asarray(archive["x_nm"], dtype=np.float64)
                sample_y = np.asarray(archive["y_nm"], dtype=np.float64)
                sample_z = np.asarray(archive["z_nm"], dtype=np.float64)
        else:
            sample_x, sample_y, sample_z = _reference_sampling_grid(
                cfg,
                args.bottom_interface_nm,
                args.top_interface_nm,
            )
        mark_stage("middle_plane_reconstruction")
        task039_mark_stage(
            "field_reconstruction_start",
            detail={"marker_semantics": "lifecycle boundary, not an RSS/PSS/USS peak"},
        )
        started = time.perf_counter()
        reconstructor = ModalFieldReconstructor(
            cfg,
            cross_section,
            spaces,
            positive,
            negative,
            bottom_z_nm=args.bottom_interface_nm,
            top_z_nm=args.top_interface_nm,
            propagation=coupling.propagation,
            positive_traction_beta_per_nm=(coupling.positive_traction_beta_per_nm),
            negative_traction_beta_per_nm=(coupling.negative_traction_beta_per_nm),
        )
        reconstruction_traction_betas = reconstructor.traction_beta_per_nm
        trace_modal_oracle = None
        if reference_archive is not None:
            mark_stage("full3d_trace_modal_oracle")
            trace_modal_oracle = reconstructor.full3d_trace_modal_oracle(archive_path)
            mark_stage("middle_plane_reconstruction")
        selected_planes = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            sample_z,
        )
        task039_h_diagnostic_payload = None
        if _task039_h_diagnostic_enabled(canonical_export_prefix, args.requested_modes):
            bottom_offset, top_offset = element_safe_middle_offsets(
                cross_section.axis_plan,
                args.bottom_interface_nm,
                args.top_interface_nm,
            )
            diagnostic_z = np.asarray(
                [
                    args.bottom_interface_nm,
                    bottom_offset["z_nm"],
                    30.0,
                    60.0,
                    90.0,
                    top_offset["z_nm"],
                    args.top_interface_nm,
                ],
                dtype=np.float64,
            )
            diagnostic_roles = [
                "interface_bottom",
                "bottom_element_safe_offset",
                "lower_reference",
                "middle_reference",
                "upper_reference",
                "top_element_safe_offset",
                "interface_top",
            ]
            diagnostic_provenance = {
                "source": "mesh_element_interior",
                "bottom": bottom_offset,
                "top": top_offset,
            }
            native_diagnostic = reconstructor.selected_planes(
                solution.modal_amplitudes,
                sample_x,
                sample_y,
                diagnostic_z,
            )
            curl_e_diagnostic = reconstructor.selected_planes_from_curl_e(
                solution.modal_amplitudes,
                sample_x,
                sample_y,
                diagnostic_z,
            )
            task039_h_diagnostic_payload = _task039_h_diagnostic_payload(
                native_planes=native_diagnostic,
                curl_e_planes=curl_e_diagnostic,
                sample_x=sample_x,
                sample_y=sample_y,
                sample_z=diagnostic_z,
                plane_roles=diagnostic_roles,
                offset_provenance=diagnostic_provenance,
                run_dir=args.output.parent,
                comm=comm,
            )
        task039_mark_stage(
            "field_reconstruction_peak",
            detail={"marker_semantics": "lifecycle boundary, not an RSS/PSS/USS peak"},
        )
        interface_samples = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            np.asarray(
                [args.bottom_interface_nm, args.top_interface_nm],
                dtype=np.float64,
            ),
        )
        interface_continuity = interface_field_continuity(
            cfg,
            bottom,
            top,
            solution.bottom_physical,
            solution.top_physical,
            interface_samples,
        )
        for side in ("bottom", "top"):
            interface_continuity[side]["traction_hcurl_dual"] = validation[
                "fe_modal_traction_equilibrium"
            ][f"{side}_dual"]
        absorption = hybrid_volume_absorption(
            cfg,
            bottom,
            top,
            solution.bottom_physical,
            solution.top_physical,
            reconstructor,
            solution.modal_amplitudes,
            incident_power=float(port_power["incident_power_code_units"]),
        )
        field_reference = None
        if reference_archive is not None:
            field_reference = compare_selected_planes_to_reference(
                selected_planes, archive_path
            )
            expected_reference_npz_sha256 = str(
                reference_record["artifacts"]["reference_npz_sha256"]
            ).lower()
            observed_reference_npz_sha256 = _sha256(archive_path)
            field_reference.update(
                {
                    "reference_npz_sha256_expected": expected_reference_npz_sha256,
                    "reference_npz_sha256_observed": observed_reference_npz_sha256,
                    "reference_record": str(reference_record_path.relative_to(ROOT)),
                    "reference_record_sha256": _sha256(reference_record_path),
                    "reference_record_source_commit_full_sha": str(
                        reference_record["metadata"]["commit_sha"]
                    ).lower(),
                    "reference_binding_verified": (
                        expected_reference_npz_sha256 == observed_reference_npz_sha256
                    ),
                }
            )
        absorption["R_plus_T_plus_A_volume"] = float(
            port_power["R_total"] + port_power["T_total"] + absorption["A_volume_total"]
        )
        absorption["energy_closure_error"] = float(
            absorption["R_plus_T_plus_A_volume"] - 1.0
        )
        absorption["hybrid_A_balance_minus_A_volume_total"] = float(
            port_power["A_balance"] - absorption["A_volume_total"]
        )
        if reference_archive is not None:
            absorption["full3d_A_volume_total"] = float(
                reference_record["results"]["A_volume_total"]
            )
            absorption["hybrid_minus_full3d_A_volume_total"] = float(
                absorption["A_volume_total"]
                - reference_record["results"]["A_volume_total"]
            )
        task039_direct_payload = None
        if canonical_export_prefix == "task039_direct":
            task039_direct_payload = _task039_direct_payload(
                selected_planes=selected_planes,
                sample_x=sample_x,
                sample_y=sample_y,
                sample_z=sample_z,
                modal_amplitudes=solution.modal_amplitudes,
                external_auxiliary_amplitudes=validation[
                    "external_auxiliary_amplitudes"
                ],
                run_dir=args.output.parent,
                comm=comm,
            )
        physical_fields = {
            "sample_payload_bytes": int(
                selected_planes.electric_V_per_m.nbytes
                + selected_planes.magnetic_A_per_m.nbytes
            ),
            "sample_grid_shape_z_y_x_component": list(
                selected_planes.electric_V_per_m.shape
            ),
            "full_middle_volume_reconstructed": False,
            "interface_continuity": interface_continuity,
            "full3d_trace_modal_oracle": trace_modal_oracle,
            "volume_absorption": absorption,
            "selected_plane_full3d_comparison": field_reference,
        }
        if task039_direct_payload is not None:
            physical_fields["task039_direct_payload"] = task039_direct_payload
        if task039_h_diagnostic_payload is not None:
            physical_fields["task039_h_diagnostic_payload"] = (
                task039_h_diagnostic_payload
            )
        timings["physical_field_reconstruction"] = _max_elapsed(comm, started)
        progress(
            "Task32 Phase6: physical interface/absorption/selected-plane reconstruction complete"
        )
        if canonical_export_prefix is not None:
            if external_mode_inventory is None:
                raise RuntimeError(
                    "canonical export opt-in requires external mode inventory"
                )
            opt_in_canonical_exports = _direct_canonical_exports(
                solution=solution,
                systems=(bottom, top),
                run_dir=args.output.parent,
                comm=comm,
                prefix=canonical_export_prefix,
            )
        task039_mark_stage(
            "postprocess_peak",
            detail={
                "marker_semantics": (
                    "elapsed lifecycle boundary; not an RSS/PSS/USS peak"
                )
            },
        )
        mark_stage("record_and_release")
        directions_valid = (
            all(mode.direction == "forward" for mode in positive.modes)
            and all(mode.direction == "backward" for mode in negative.modes)
            and all(mode.passive_branch_valid for mode in positive.modes)
            and all(mode.passive_branch_valid for mode in negative.modes)
        )
        reciprocal_valid = len(pairs) == args.requested_modes and all(
            pair.opposite_direction and pair.passive_branches_valid for pair in pairs
        )
        forward_factors = np.asarray(
            coupling.propagation.forward.factors, dtype=np.complex128
        )
        backward_factors = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
        finite_rta = all(
            np.isfinite(port_power[key])
            for key in ("R_total", "T_total", "A_balance", "R_plus_T")
        )
        gates = {
            "exact_requested_mode_count_delivered": (
                len(positive.modes) == args.requested_modes
                and len(negative.modes) == args.requested_modes
            ),
            "requested_forward_and_backward_passive_bases": directions_valid,
            "reciprocal_pairing_complete": reciprocal_valid,
            "biorthogonality_identity_error_le_1e-6": (
                max(positive.max_identity_error, negative.max_identity_error) <= 1.0e-6
            ),
            "right_and_left_qep_residuals_le_1e-8": (
                max(
                    *(
                        mode.right.polynomial_relative_residual
                        for mode in positive.modes
                    ),
                    *(
                        mode.right.polynomial_relative_residual
                        for mode in negative.modes
                    ),
                    *(
                        mode.left_polynomial_relative_residual
                        for mode in positive.modes
                    ),
                    *(
                        mode.left_polynomial_relative_residual
                        for mode in negative.modes
                    ),
                )
                <= 1.0e-8
            ),
            "stable_propagation_no_growing_factor": bool(
                max(
                    np.max(np.abs(forward_factors), initial=0.0),
                    np.max(np.abs(backward_factors), initial=0.0),
                )
                <= 1.0 + 1.0e-12
            ),
            "monolithic_true_relative_residual_le_1e-9": (
                solution.relative_residual <= 1.0e-9
            ),
            "primary_direct_true_relative_residual_le_1e-9": (
                solution.relative_residual <= 1.0e-9
            ),
            "interface_e_projection_relative_residual_le_1e-8": (
                validation["interface_e_projection"]["combined_relative_residual"]
                <= 1.0e-8
            ),
            "fe_modal_traction_equilibrium_relative_residual_le_1e-8": (
                max(
                    validation["fe_modal_traction_equilibrium"][
                        "bottom_relative_residual"
                    ],
                    validation["fe_modal_traction_equilibrium"][
                        "top_relative_residual"
                    ],
                )
                <= 1.0e-8
            ),
            "external_port_rta_finite": finite_rta,
        }
        if solution.bottom_recovered is not None:
            if solution.top_recovered is None:
                raise RuntimeError(
                    "Hybrid static recovery completed on only one local side."
                )
            recovered_sides = (
                solution.bottom_recovered,
                solution.top_recovered,
            )
            gates.update(
                {
                    "condensed_full_operator_relative_residual_le_1e-9": (
                        max(
                            item.full_operator_residual[
                                "linear_system_relative_residual"
                            ]
                            for item in recovered_sides
                        )
                        <= 1.0e-9
                    ),
                    "condensed_eliminated_interior_max_residual_le_1e-9": (
                        max(
                            item.full_operator_residual[
                                "eliminated_cell_interior_max_abs_residual"
                            ]
                            for item in recovered_sides
                        )
                        <= 1.0e-9
                    ),
                    "condensed_full_surface_mode_matrix_not_retained": all(
                        not item.streaming_audit["full_surface_mode_matrix_retained"]
                        for item in recovered_sides
                    ),
                    "condensed_full_global_matrix_not_allocated": all(
                        not item.streaming_audit["full_global_matrix_allocated"]
                        for item in recovered_sides
                    ),
                }
            )
        if physical_fields is not None:
            interface_physical = physical_fields["interface_continuity"]
            absorption_physical = physical_fields["volume_absorption"]
            exact_traction_values = [
                interface_physical.get(side, {})
                .get("traction_hcurl_dual", {})
                .get("relative_dual")
                for side in ("bottom", "top")
            ]
            exact_traction_pass, _exact_traction_role = _exact_traction_gate(
                {}, exact_traction_values, 1.0e-8
            )
            gates.update(
                {
                    "sampled_interface_e_t_relative_l2_le_5e-3": (
                        max(
                            interface_physical[side]["electric_tangential"][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 5.0e-3
                    ),
                    "diagnostic_sampled_traction_density_l2_proxy_le_1e-2": (
                        max(
                            interface_physical[side]["traction_density_l2_proxy"][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 1.0e-2
                    ),
                    "assembled_interface_h_t_exact_dual_le_1e-8": (exact_traction_pass),
                    "volume_energy_closure_abs_le_1e-5": (
                        abs(absorption_physical["energy_closure_error"]) <= 1.0e-5
                    ),
                }
            )
            planes_physical = physical_fields["selected_plane_full3d_comparison"]
            if planes_physical is not None:
                gates.update(
                    {
                        "volume_absorption_full3d_abs_delta_le_1e-5": (
                            abs(
                                absorption_physical[
                                    "hybrid_minus_full3d_A_volume_total"
                                ]
                            )
                            <= 1.0e-5
                        ),
                        "middle_plane_e_relative_l2_le_5e-3": (
                            planes_physical["max_middle_plane_electric_relative_l2"]
                            <= 5.0e-3
                        ),
                        "middle_plane_h_relative_l2_le_5e-3": (
                            planes_physical["max_middle_plane_magnetic_relative_l2"]
                            <= 5.0e-3
                        ),
                    }
                )
        physical_gate_prefixes = (
            "sampled_interface_",
            "assembled_interface_",
            "volume_",
            "middle_plane_",
        )
        algebraic_chain_pass = all(
            value
            for key, value in gates.items()
            if not key.startswith(physical_gate_prefixes)
            and not key.startswith("diagnostic_")
        )
        integration_pass = _all_formal_true(gates)
        interface_closure_pass = bool(
            physical_fields is not None
            and gates.get(
                "interface_e_projection_relative_residual_le_1e-8",
                False,
            )
            and gates.get(
                "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
                False,
            )
            and gates.get(
                "sampled_interface_e_t_relative_l2_le_5e-3",
                False,
            )
            and gates.get(
                "assembled_interface_h_t_exact_dual_le_1e-8",
                False,
            )
        )
        hybrid_p_status = hybrid_p_disposition(
            cfg.polarization_kind,
            full3d_physical_solution_exists=loaded_reference is not None,
            modal_rank_sufficient=None,
            interface_closure_pass=interface_closure_pass,
            diagnostic_projection_bug=False,
        )
        task033_physical_truncation_allowed = bool(
            not task33_variant or args.requested_modes >= 80
        )
        projection_stats = {
            "bottom": _petsc_matrix_stats(coupling.bottom.projection, assemble=False),
            "top": _petsc_matrix_stats(coupling.top.projection, assemble=False),
        }
        factor_inventory = (
            {"augmented": _petsc_factor_inventory(solution.ksp)}
            if system is not None
            else primary_schur_system.factor_inventory
        )
        full_vector_size = int(positive.modes[0].right.right_full.getSize())
        reduced_vector_size = int(positive.modes[0].right.right_reduced.getSize())
        eigenvector_bytes = int(
            2
            * args.requested_modes
            * 2
            * (full_vector_size + reduced_vector_size)
            * np.dtype(PETSc.ScalarType).itemsize
        )
        active_column_counts = {
            "bottom": distributed_active_column_count(coupling.bottom.projection),
            "top": distributed_active_column_count(coupling.top.projection),
        }
        object_payload_ledger = {
            "scalar_bytes": int(np.dtype(PETSc.ScalarType).itemsize),
            "index_bytes": int(np.dtype(PETSc.IntType).itemsize),
            "interface_active_dofs": {
                side: result.global_count
                for side, result in active_column_counts.items()
            },
            "interface_active_column_count_diagnostics": {
                side: result.to_dict() for side, result in active_column_counts.items()
            },
            "mode_count_per_direction": args.requested_modes,
            "retained_right_left_eigenvector_bytes": eigenvector_bytes,
            "projection_matrix": projection_stats,
            "modal_schur_bytes": (
                0
                if primary_schur_system is None
                else int(primary_schur_system.modal_schur.nbytes)
            ),
            "local_or_augmented_factor_inventory": factor_inventory,
            "storage_complexity_contract": "O(N_interface*M)+O(M^2)",
            "dense_interface_square_formed": False,
        }
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "schema_version": 1,
            "benchmark_id": (
                "task032_phase6_hybrid_augmented_direct"
                if args.degree == 2
                and args.bottom_interface_nm == 10.0
                and args.top_interface_nm == 110.0
                and args.solver_path == "augmented"
                else (
                    "task032_phase10_hybrid_modal_schur_direct"
                    if args.degree == 2
                    and args.bottom_interface_nm == 10.0
                    and args.top_interface_nm == 110.0
                    else "task033_high_order_or_buffer_hybrid_direct"
                )
            ),
            "timestamp_utc": timestamp,
            "status": (
                "algebraic_smoke_pass_physical_truncation_not_qualified"
                if task33_variant
                and algebraic_chain_pass
                and not task033_physical_truncation_allowed
                else (
                    "physical_integration_pass_mode_convergence_pending"
                    if integration_pass
                    else "physical_integration_failed"
                )
            ),
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in command_argv),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
                "internal_propagation_model_requested": (
                    args.internal_propagation_model
                ),
                "internal_traction_model_requested": (args.internal_traction_model),
                "stage4_full3d_assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "task035c_p6_h10_authority_gate": task035c_p6_gate,
                "task33_variant": task33_variant,
                "provenance": (
                    (
                        "clean_task033_high_order_or_buffer_hybrid_integration"
                        if task33_variant
                        else "clean_task032_phase6_real_qep_hybrid_integration"
                    )
                    if not provenance["tracked_source_dirty"]
                    else (
                        "dirty_task033_high_order_or_buffer_hybrid_research"
                        if task33_variant
                        else "dirty_task032_phase6_real_qep_hybrid_research"
                    )
                ),
            },
            "case": {
                "material_kind": "stage4_xy",
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": modal_degree,
                "modal_h_nm": modal_h_nm,
                "internal_propagation_model": (args.internal_propagation_model),
                "internal_traction_model": args.internal_traction_model,
                "discrete_axial_qualification_scope": (
                    _discrete_axial_qualification_scope(
                        args.internal_propagation_model,
                        args.internal_traction_model,
                    )
                ),
                "requested_modes_per_direction": args.requested_modes,
                "candidate_modes_per_target_branch": candidate_modes,
                "near_degenerate_tolerance": args.near_degenerate_tolerance,
                "block_rotation_tolerance": args.block_rotation_tolerance,
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "middle_length_nm": (args.top_interface_nm - args.bottom_interface_nm),
                "wavelength_nm": cfg.lambda0,
                "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
                "polarization_kind": cfg.polarization_kind,
                "mesh_policy": (
                    "task034_periodic_conforming_fixed_p_graded_opt_in"
                    if graded_plan is not None
                    else "reviewed_stage4_axis_plan"
                ),
                "graded_reference_h_nm": args.graded_reference_h,
                "graded_profile": (
                    args.graded_profile if graded_plan is not None else None
                ),
                "graded_coarse_factor": (
                    args.graded_coarse_factor if graded_plan is not None else None
                ),
                "graded_plan_hash": (
                    graded_plan.plan_hash if graded_plan is not None else None
                ),
                "graded_plan": (
                    graded_plan.to_record() if graded_plan is not None else None
                ),
            },
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "quadrature_policy": operators.quadrature_policy,
                "positive_solver_converged_modes": (positive_report.converged_modes),
                "negative_solver_converged_modes": (negative_report.converged_modes),
                "positive_directional_selection": (
                    _directional_selection_summary(positive_selection)
                ),
                "negative_directional_selection": (
                    _directional_selection_summary(negative_selection)
                ),
                "positive": _basis_summary(positive),
                "negative": _basis_summary(negative),
                "reciprocal_pairs": [
                    {
                        "positive_index": pair.positive_index,
                        "negative_index": pair.negative_index,
                        "relative_beta_error": pair.relative_beta_error,
                        "electric_mass_overlap": pair.electric_mass_overlap,
                        "opposite_direction": pair.opposite_direction,
                        "passive_branches_valid": (pair.passive_branches_valid),
                    }
                    for pair in pairs
                ],
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "matrix_size": (
                    list(system.A.getSize()) if system is not None else None
                ),
                "matrix_stats": (system.matrix_stats if system is not None else None),
                "block_shapes": (system.block_shapes if system is not None else None),
                "inserted_nnz_by_block": (
                    system.inserted_nnz_by_block if system is not None else None
                ),
                "bottom_global_size": bottom.global_size,
                "top_global_size": top.global_size,
                "assembly_backend_requested": (args.stage4_full3d_assembly_backend),
                "bottom_assembly_backend_actual": (bottom.assembly_backend_actual),
                "top_assembly_backend_actual": top.assembly_backend_actual,
                "bottom_assembly_backend_qualification": (
                    bottom.assembly_backend_qualification
                ),
                "top_assembly_backend_qualification": (
                    top.assembly_backend_qualification
                ),
                "bottom_static_condensation": (
                    bottom.static_condensation.metadata.to_dict()
                    if bottom.static_condensation is not None
                    else None
                ),
                "top_static_condensation": (
                    top.static_condensation.metadata.to_dict()
                    if top.static_condensation is not None
                    else None
                ),
                "bottom_local_fe_dofs": bottom.n_fe,
                "top_local_fe_dofs": top.n_fe,
                "bottom_local_mesh_cells": list(bottom.local_mesh.mesh_cells),
                "top_local_mesh_cells": list(top.local_mesh.mesh_cells),
                "bottom_local_thickness_nm": (
                    bottom.local_mesh.interface_z_nm - bottom.local_mesh.external_z_nm
                ),
                "top_local_thickness_nm": (
                    top.local_mesh.external_z_nm - top.local_mesh.interface_z_nm
                ),
                "bottom_matrix_stats": bottom.augmented_matrix_stats,
                "top_matrix_stats": top.augmented_matrix_stats,
                "internal_unknown_count": coupling.internal_unknown_count,
                "internal_propagation": {
                    "model": coupling.propagation.propagation_model,
                    "authority_boundary": (
                        "scalar_CG_axial_phase_oracle; final authority remains "
                        "the measured 12-channel/field/residual closure"
                    ),
                    "modal_magnetic_and_traction_symbol": (
                        coupling.modal_traction_model
                    ),
                    "field_reconstruction_magnetic_beta_source": (
                        reconstructor.traction_model
                    ),
                    "field_reconstruction_positive_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in reconstruction_traction_betas[0]
                    ],
                    "field_reconstruction_negative_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in reconstruction_traction_betas[1]
                    ],
                    "positive_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.positive_traction_beta_per_nm
                    ],
                    "negative_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.negative_traction_beta_per_nm
                    ],
                    "axial_fem_degree": int(cfg.nedelec_degree),
                    "axial_h_nm": float(cfg.mesh_target_size),
                    "forward_original_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.propagation.forward.beta_per_nm
                    ],
                    "forward_effective_beta_per_nm": [
                        _complex_json(value)
                        for value in (
                            coupling.propagation.forward.effective_beta_per_nm
                        )
                    ],
                    "forward_phase_corrections_rad": list(
                        coupling.propagation.forward.phase_corrections_rad
                    ),
                    "forward_log_magnitude_corrections": list(
                        coupling.propagation.forward.log_magnitude_corrections
                    ),
                    "backward_original_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.propagation.backward.beta_per_nm
                    ],
                    "backward_effective_beta_per_nm": [
                        _complex_json(value)
                        for value in (
                            coupling.propagation.backward.effective_beta_per_nm
                        )
                    ],
                    "backward_phase_corrections_rad": list(
                        coupling.propagation.backward.phase_corrections_rad
                    ),
                    "backward_log_magnitude_corrections": list(
                        coupling.propagation.backward.log_magnitude_corrections
                    ),
                    "max_factor_magnitude": float(
                        coupling.propagation.max_factor_magnitude
                    ),
                    "passivity_valid": bool(coupling.propagation.passivity_valid),
                },
                "qep_to_interface_quadrature_degree": (
                    coupling.interface_quadrature_degree
                ),
                "cell_interior_modal_correction_norms": {
                    side: {
                        "positive_frobenius": float(
                            np.linalg.norm(block.positive_interior_correction)
                        ),
                        "negative_frobenius": float(
                            np.linalg.norm(block.negative_interior_correction)
                        ),
                        "modal_rhs_l2": float(
                            np.linalg.norm(block.modal_rhs_correction)
                        ),
                    }
                    for side, block in (
                        ("bottom", coupling.bottom),
                        ("top", coupling.top),
                    )
                },
                "tangential_surface_trace_only_audit": {
                    side: {
                        "verified": bool(block.tangential_surface_trace_only_verified),
                        "pairwise_interior_schur_evaluated": bool(
                            block.interior_modal_pairwise_schur_evaluated
                        ),
                        "mathematical_contract": (
                            "pure tangential ds coupling; H(curl) "
                            "cell-interior tangential trace is zero"
                        ),
                    }
                    for side, block in (
                        ("bottom", coupling.bottom),
                        ("top", coupling.top),
                    )
                },
                "full_surface_mode_vectors_retained": bool(
                    coupling.bottom.full_surface_mode_vectors_retained
                    or coupling.top.full_surface_mode_vectors_retained
                ),
                "dense_interface_square_formed": (
                    system.dense_interface_square_formed
                    if system is not None
                    else primary_schur_system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (coupling.full_field_or_mode_gathered),
                "modal_schur": (
                    None
                    if primary_schur_system is None
                    else {
                        "shape": list(primary_schur_system.modal_schur.shape),
                        "bytes": int(primary_schur_system.modal_schur.nbytes),
                        "condition": primary_schur_system.modal_schur_condition,
                        "multi_rhs_count": primary_schur_system.multi_rhs_count,
                        "transient_dense_rhs_solution_bytes": (
                            primary_schur_system.transient_dense_rhs_solution_bytes
                        ),
                        "factor_setup_seconds": (
                            primary_schur_system.factor_setup_seconds
                        ),
                        "multi_rhs_solve_seconds": (
                            primary_schur_system.multi_rhs_solve_seconds
                        ),
                        "lifecycle_strategy": (primary_schur_system.lifecycle_strategy),
                        "recovery_refactor_required": (
                            primary_schur_system.recovery_refactor_required
                        ),
                    }
                ),
            },
            "solve": {
                "factor_solver": solution.factor_solver,
                "converged_reason": solution.converged_reason,
                "true_relative_residual": solution.relative_residual,
                "setup_seconds": getattr(solution, "setup_seconds", None),
                "solve_seconds": getattr(solution, "solve_seconds", None),
                "modal_solve_seconds": getattr(solution, "modal_solve_seconds", None),
                "recovery_seconds": getattr(solution, "recovery_seconds", None),
                "recovery_factor_setup_seconds": getattr(
                    solution, "recovery_factor_setup_seconds", {}
                ),
                "bottom_static_recovery": (
                    None
                    if solution.bottom_recovered is None
                    else {
                        "recovery": (solution.bottom_recovered.recovery_audit),
                        "full_operator_residual": (
                            solution.bottom_recovered.full_operator_residual
                        ),
                        "streaming": (solution.bottom_recovered.streaming_audit),
                    }
                ),
                "top_static_recovery": (
                    None
                    if solution.top_recovered is None
                    else {
                        "recovery": solution.top_recovered.recovery_audit,
                        "full_operator_residual": (
                            solution.top_recovered.full_operator_residual
                        ),
                        "streaming": solution.top_recovered.streaming_audit,
                    }
                ),
            },
            "validation": validation,
            "physical_field_reconstruction": physical_fields,
            "modal_schur_comparison": modal_schur_comparison,
            "object_payload_ledger": object_payload_ledger,
            "full3d_reference_comparison": reference,
            "gates": gates,
            "qualification": {
                "integration_pass": integration_pass,
                "algebraic_chain_pass": algebraic_chain_pass,
                "task033_physical_truncation_allowed": (
                    task033_physical_truncation_allowed
                ),
                "task033_minimum_physical_modes_per_direction": (
                    80 if task33_variant else None
                ),
                "clean_source_integration_record": bool(
                    integration_pass
                    and task033_physical_truncation_allowed
                    and not provenance["tracked_source_dirty"]
                ),
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "physical_field_gates_pass": bool(
                    physical_fields is not None
                    and all(
                        value
                        for key, value in gates.items()
                        if (
                            key.startswith("sampled_interface_")
                            or key.startswith("assembled_interface_")
                            or key.startswith("volume_")
                            or key.startswith("middle_plane_")
                        )
                        and not key.startswith("diagnostic_")
                    )
                ),
                "pointwise_h_jump_checked": physical_fields is not None,
                "pointwise_h_jump_role": "diagnostic_sampled_proxy_only",
                "exact_variational_conormal_dual_checked": bool(
                    physical_fields is not None
                    and all(
                        "traction_hcurl_dual"
                        in physical_fields["interface_continuity"][side]
                        for side in ("bottom", "top")
                    )
                ),
                "volume_absorption_reconstructed": physical_fields is not None,
                "selected_middle_planes_reconstructed": physical_fields is not None,
                "official_record": False,
                "hybrid_p_disposition": hybrid_p_status,
                "boundary": (
                    (
                        "real_QEP_internal_physical_chain; no pinned "
                        "degree-compatible Case080 full3D reference is registered; "
                        "requires an M funnel and a separate equal-accuracy comparison"
                    )
                    if loaded_reference is None
                    else (
                        "real_QEP_physical_field_chain with a degree-compatible "
                        "full3D reference; requires a wider M funnel before "
                        "official qualification"
                    )
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }
        if canonical_trace_gate_policy is not None:
            record["canonical_trace_gate"] = _task039_canonical_trace_gate_record(
                coupling, canonical_trace_gate_policy, canonical_trace_family_sha256
            )
        if opt_in_canonical_exports is not None:
            record["canonical_exports"] = opt_in_canonical_exports
    except _Task039TraceAuditStop as stopped:
        record = stopped.record
    except _ModalBasisCapacityStop:
        pass
    finally:
        if schur_solution is not None:
            schur_solution.destroy()
        if schur_system is not None:
            schur_system.destroy()
        if solution is not None:
            solution.destroy()
        if primary_schur_system is not None:
            primary_schur_system.destroy()
        if system is not None:
            system.destroy()
        if coupling is not None:
            coupling.destroy()
        for local_system in (bottom, top):
            if local_system is not None:
                local_system.destroy()
        if positive is not None:
            positive.destroy()
        if negative is not None:
            negative.destroy()
        if operators is not None:
            operators.destroy()
        if record is not None and any(
            item is not None for item in (positive, negative, operators)
        ):
            task039_mark_stage(
                "all_modal_qep_temporaries_released",
                detail={"after_destroy": True},
            )
        if record is not None and any(
            item is not None
            for item in (
                schur_solution,
                schur_system,
                solution,
                primary_schur_system,
                system,
                coupling,
                bottom,
                top,
                positive,
                negative,
                operators,
            )
        ):
            task039_mark_stage("final_cleanup", detail={"after_destroy": True})

    if record is not None and external_mode_inventory is not None:
        record["external_mode_inventory"] = dict(external_mode_inventory)
    if record is not None and detail_marker_path is not None:
        record.setdefault("telemetry", {})["memory_detail_markers_path"] = str(
            detail_marker_path
        )
    if (
        canonical_export_prefix == "task039_direct"
        and comm.rank == 0
        and args.memory_stages is not None
    ):
        ledger_path = args.memory_stages.with_name(
            args.memory_stages.stem + ".task039_e10.json"
        )
        ledger_path.write_text(
            json.dumps(task039_e10_ledger(task039_e10_events), ensure_ascii=False),
            encoding="utf-8",
        )
    if comm.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        if formal_stage_marker_path is not None:
            task039_write_memory_object_ledger(
                args.output.parent / "memory_object_ledger.json", record
            )
        print(f"Task32 Phase6 record: {args.output}", flush=True)
        print(f"Task32 Phase6 status: {record['status']}", flush=True)
    comm.barrier()
    if record.get("status") == "controlled_stop":
        return record
    if not record["qualification"]["integration_pass"]:
        raise SystemExit(2)
    return record


if __name__ == "__main__":
    main()
