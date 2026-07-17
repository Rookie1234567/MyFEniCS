from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host path
    resource = None

from src.common.config_3d import target_stage4_config
from src.coupling.hybrid_internal_modes import (
    build_hybrid_internal_mode_coupling,
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
    hybrid_volume_absorption,
    interface_field_continuity,
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
        tracked_status = _git("status", "--porcelain", "--untracked-files=no")
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

    end = _source_provenance(
        comm, verified_clean_sha, allow_dirty_research
    )
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
    """Count distributed matrix columns that contain at least one stored entry."""

    first, last = matrix.getOwnershipRange()
    local_columns: set[int] = set()
    for row in range(first, last):
        columns, _values = matrix.getRow(row)
        local_columns.update(int(column) for column in columns)
    gathered = matrix.getComm().tompi4py().allgather(tuple(sorted(local_columns)))
    return len({column for columns in gathered for column in columns})


def _basis_summary(basis) -> dict[str, Any]:
    return {
        "mode_count": len(basis.modes),
        "max_biorthogonality_identity_error": basis.max_identity_error,
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
        "passive_branch_valid": [
            mode.passive_branch_valid for mode in basis.modes
        ],
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


def _validate_case080_reference_identity(
    reference: dict[str, Any], *, degree: int, h_nm: float, path: Path
) -> None:
    try:
        physical_model = reference["physical_model"]
        qualification = reference["qualification"]
        metadata = reference["metadata"]
        commit_sha = str(metadata["commit_sha"]).lower()
        identity_valid = (
            physical_model["nedelec_degree"] == degree
            and abs(float(physical_model["mesh_h_nm"]) - h_nm) <= 1.0e-12
            and abs(float(physical_model["incident_grazing_deg"]) - 10.0)
            <= 1.0e-12
            and abs(float(physical_model["incident_theta_deg"]) - 80.0)
            <= 1.0e-12
            and abs(float(physical_model["incident_phi_deg"])) <= 1.0e-12
            and physical_model["polarization_kind"] == "s"
            and abs(float(physical_model["wavelength_nm"]) - 13.5)
            <= 1.0e-12
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
            f"pinned 10-degree s-polarized 13.5-nm model: {path}"
        )


def _load_case080_reference(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    reference_path = _case080_reference_path(
        degree, h_nm, reference_by_degree_and_h
    )
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
    _validate_case080_reference_identity(
        reference, degree=degree, h_nm=h_nm, path=reference_path
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
        "reference_grid_converged": reference["qualification"][
            "grid_converged"
        ],
        "hybrid_minus_full3d": {
            "R_total": float(port_power["R_total"] - results["R_total"]),
            "T_total": float(port_power["T_total"] - results["T_total"]),
            "A_balance": float(
                port_power["A_balance"] - results["A_balance"]
            ),
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase6 real-QEP hybrid augmented direct diagnostic"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--degree", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument(
        "--full3d-reference",
        type=Path,
        help=(
            "Optional explicit same-p/h full3D descriptor. This is required "
            "for review-v5 coarse p3 candidates that are not in the legacy "
            "reference registry."
        ),
    )
    parser.add_argument("--bottom-interface-nm", type=float, default=10.0)
    parser.add_argument("--top-interface-nm", type=float, default=110.0)
    parser.add_argument("--graded-reference-h", type=float, choices=(5.0, 3.0))
    parser.add_argument("--graded-coarse-factor", type=float, default=2.0)
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.h_nm <= 0.0:
        raise SystemExit("--h-nm must be positive.")
    if not (
        0.0 < args.bottom_interface_nm < args.top_interface_nm < 120.0
    ):
        raise SystemExit(
            "Task33 buffer interfaces must satisfy "
            "0 < bottom-interface-nm < top-interface-nm < 120."
        )
    if args.graded_reference_h is not None:
        if args.degree != 2:
            raise SystemExit("The Task033 graded feasibility path is fixed to p2.")
        if (
            args.bottom_interface_nm != 10.0
            or args.top_interface_nm != 110.0
        ):
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
    task33_variant = bool(
        args.degree != 2
        or args.bottom_interface_nm != 10.0
        or args.top_interface_nm != 110.0
        or args.graded_reference_h is not None
        or not np.isclose(args.incident_grazing_deg, 10.0)
        or args.polarization_kind != "s"
    )
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )

    if comm.rank == 0 and args.memory_stages is not None:
        args.memory_stages.parent.mkdir(parents=True, exist_ok=True)
        args.memory_stages.unlink(missing_ok=True)
    comm.barrier()

    def mark_stage(stage: str) -> None:
        if comm.rank == 0 and args.memory_stages is not None:
            with args.memory_stages.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "stage": stage,
                            "elapsed_seconds": time.perf_counter() - total_started,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def progress(message: str) -> None:
        if comm.rank == 0:
            print(message, flush=True)

    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    cfg.incident_theta_deg = 90.0 - float(args.incident_grazing_deg)
    cfg.polarization_kind = args.polarization_kind
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
            "finite_spectrum_abs_beta_h_cutoff": (
                NUMERICAL_INFINITY_BETA_H_CUTOFF
            ),
            "finite_spectrum_abs_beta_cutoff_per_nm": (
                selection.abs_beta_cutoff
            ),
            "first_rejected_numerical_infinity_beta_per_nm": (
                selection_record[
                    "first_rejected_numerical_infinity_beta_per_nm"
                ]
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
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
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
                f"{direction}_solver_converged_modes": (
                    solver_report.converged_modes
                ),
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
            from src.geometry.task033_periodic_graded_mesh import (
                Task033Stage4Geometry,
                build_physics_informed_graded_plan,
                build_task033_graded_local_mesh_pair,
            )

            graded_plan = build_physics_informed_graded_plan(
                reference_h_nm=args.graded_reference_h,
                geometry=Task033Stage4Geometry.from_config(cfg),
                coarse_factor=args.graded_coarse_factor,
            )
            graded_bottom_mesh, graded_top_mesh = (
                build_task033_graded_local_mesh_pair(cfg, graded_plan)
            )
            cross_section = build_matching_cross_section(
                cfg,
                "stage4_xy",
                x_values=graded_plan.x_values,
                y_values=graded_plan.y_values,
            )
        else:
            cross_section = build_matching_cross_section(cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=args.degree
        )
        operators = assemble_quadratic_beta_operators(
            cfg, cross_section, spaces
        )
        poynting_evaluator = PoyntingFluxEvaluator(
            cfg, cross_section, spaces
        )
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        timings["cross_section_and_qep_assembly"] = _max_elapsed(
            comm, started
        )
        progress("Task32 Phase6: cross-section QEP assembled")

        mark_stage("cross_section_eigen_solve")
        started = time.perf_counter()
        positive_right, positive_report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=candidate_modes,
        )
        progress("Task32 Phase6: positive right QEP modes complete")
        positive_right, positive_selection = select_passive_direction_modes(
            positive_right,
            desired_direction="forward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(
                NUMERICAL_INFINITY_BETA_H_CUTOFF / args.h_nm
            ),
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
            cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=candidate_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
        progress("Task32 Phase6: positive adjoint basis complete")
        negative_right, negative_report = solve_quadratic_beta_modes(
            operators,
            target=-target,
            requested_modes=candidate_modes,
        )
        progress("Task32 Phase6: negative right QEP modes complete")
        negative_right, negative_selection = select_passive_direction_modes(
            negative_right,
            desired_direction="backward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(
                NUMERICAL_INFINITY_BETA_H_CUTOFF / args.h_nm
            ),
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
        negative = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=candidate_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
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
            log=progress,
        )
        timings["internal_modal_coupling"] = _max_elapsed(comm, started)

        started = time.perf_counter()
        if args.solver_path == "augmented":
            mark_stage("augmented_matrix_and_factor")
            system = build_hybrid_augmented_direct_system(
                bottom, top, coupling
            )
            timings["primary_system_build"] = _max_elapsed(comm, started)
            timings["monolithic_assembly"] = timings["primary_system_build"]
            progress("Task32 Phase6: monolithic augmented AIJ complete")
            solution = solve_hybrid_augmented_direct(system, bottom, top)
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
                    schur_validation["port_power"][key]
                    - validation["port_power"][key]
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
                    _relative_vector_error(schur_solution.top, solution.top)
                    <= 1.0e-9
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
                "status": (
                    "pass" if all(comparison_gates.values()) else "failed"
                ),
                "comparison_solver_path": comparison_solver_path,
                "comparison_solver_path_argument": (
                    args.comparison_solver_path
                ),
                "comparison_lifecycle_strategy": (
                    schur_system.lifecycle_strategy
                ),
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
                "Task32 Phase7: "
                f"{comparison_solver_path} direct comparison complete"
            )
        pinned_reference_case = (
            abs(args.incident_grazing_deg - 10.0) <= 1.0e-12
            and args.polarization_kind == "s"
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
            sample_x = cfg.x_min + (
                np.arange(40, dtype=np.float64) + 0.5
            ) * cfg.period_x / 40.0
            sample_y = cfg.y_min + (
                np.arange(20, dtype=np.float64) + 0.5
            ) * cfg.period_y / 20.0
            sample_z = np.linspace(
                args.bottom_interface_nm,
                args.top_interface_nm,
                5,
                dtype=np.float64,
            )
        mark_stage("middle_plane_reconstruction")
        started = time.perf_counter()
        reconstructor = ModalFieldReconstructor(
            cfg,
            cross_section,
            spaces,
            positive,
            negative,
            bottom_z_nm=args.bottom_interface_nm,
            top_z_nm=args.top_interface_nm,
        )
        selected_planes = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            sample_z,
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
            solution.bottom,
            solution.top,
            interface_samples,
        )
        absorption = hybrid_volume_absorption(
            cfg,
            bottom,
            top,
            solution.bottom,
            solution.top,
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
                        expected_reference_npz_sha256
                        == observed_reference_npz_sha256
                    ),
                }
            )
        absorption["R_plus_T_plus_A_volume"] = float(
            port_power["R_total"]
            + port_power["T_total"]
            + absorption["A_volume_total"]
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
            "volume_absorption": absorption,
            "selected_plane_full3d_comparison": field_reference,
        }
        timings["physical_field_reconstruction"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: physical interface/absorption/selected-plane reconstruction complete")
        mark_stage("record_and_release")
        directions_valid = (
            all(mode.direction == "forward" for mode in positive.modes)
            and all(mode.direction == "backward" for mode in negative.modes)
            and all(mode.passive_branch_valid for mode in positive.modes)
            and all(mode.passive_branch_valid for mode in negative.modes)
        )
        reciprocal_valid = len(pairs) == args.requested_modes and all(
            pair.opposite_direction and pair.passive_branches_valid
            for pair in pairs
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
                max(positive.max_identity_error, negative.max_identity_error)
                <= 1.0e-6
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
                validation["interface_e_projection"][
                    "combined_relative_residual"
                ]
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
        if physical_fields is not None:
            interface_physical = physical_fields["interface_continuity"]
            absorption_physical = physical_fields["volume_absorption"]
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
                    "sampled_interface_h_t_relative_l2_le_1e-2": (
                        max(
                            interface_physical[side]["magnetic_tangential"][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 1.0e-2
                    ),
                    "volume_energy_closure_abs_le_1e-5": (
                        abs(absorption_physical["energy_closure_error"])
                        <= 1.0e-5
                    ),
                }
            )
            planes_physical = physical_fields[
                "selected_plane_full3d_comparison"
            ]
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
                            planes_physical[
                                "max_middle_plane_electric_relative_l2"
                            ]
                            <= 5.0e-3
                        ),
                        "middle_plane_h_relative_l2_le_5e-3": (
                            planes_physical[
                                "max_middle_plane_magnetic_relative_l2"
                            ]
                            <= 5.0e-3
                        ),
                    }
                )
        physical_gate_prefixes = ("sampled_interface_", "volume_", "middle_plane_")
        algebraic_chain_pass = all(
            value
            for key, value in gates.items()
            if not key.startswith(physical_gate_prefixes)
        )
        integration_pass = all(gates.values())
        task033_physical_truncation_allowed = bool(
            not task33_variant or args.requested_modes >= 80
        )
        projection_stats = {
            "bottom": _petsc_matrix_stats(
                coupling.bottom.projection, assemble=False
            ),
            "top": _petsc_matrix_stats(
                coupling.top.projection, assemble=False
            ),
        }
        factor_inventory = (
            {"augmented": _petsc_factor_inventory(solution.ksp)}
            if system is not None
            else primary_schur_system.factor_inventory
        )
        full_vector_size = int(positive.modes[0].right.right_full.getSize())
        reduced_vector_size = int(
            positive.modes[0].right.right_reduced.getSize()
        )
        eigenvector_bytes = int(
            2
            * args.requested_modes
            * 2
            * (full_vector_size + reduced_vector_size)
            * np.dtype(PETSc.ScalarType).itemsize
        )
        object_payload_ledger = {
            "scalar_bytes": int(np.dtype(PETSc.ScalarType).itemsize),
            "index_bytes": int(np.dtype(PETSc.IntType).itemsize),
            "interface_active_dofs": {
                "bottom": _global_active_column_count(
                    coupling.bottom.projection
                ),
                "top": _global_active_column_count(coupling.top.projection),
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
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
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
                "requested_modes_per_direction": args.requested_modes,
                "candidate_modes_per_target_branch": candidate_modes,
                "near_degenerate_tolerance": args.near_degenerate_tolerance,
                "block_rotation_tolerance": args.block_rotation_tolerance,
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "middle_length_nm": (
                    args.top_interface_nm - args.bottom_interface_nm
                ),
                "wavelength_nm": cfg.lambda0,
                "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
                "polarization_kind": cfg.polarization_kind,
                "mesh_policy": (
                    "task033_periodic_graded_conforming_p2"
                    if graded_plan is not None
                    else "reviewed_stage4_axis_plan"
                ),
                "graded_reference_h_nm": args.graded_reference_h,
                "graded_coarse_factor": (
                    args.graded_coarse_factor
                    if graded_plan is not None
                    else None
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
                "positive_solver_converged_modes": (
                    positive_report.converged_modes
                ),
                "negative_solver_converged_modes": (
                    negative_report.converged_modes
                ),
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
                        "passive_branches_valid": (
                            pair.passive_branches_valid
                        ),
                    }
                    for pair in pairs
                ],
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "matrix_size": (
                    list(system.A.getSize()) if system is not None else None
                ),
                "matrix_stats": (
                    system.matrix_stats if system is not None else None
                ),
                "block_shapes": (
                    system.block_shapes if system is not None else None
                ),
                "inserted_nnz_by_block": (
                    system.inserted_nnz_by_block if system is not None else None
                ),
                "bottom_global_size": bottom.global_size,
                "top_global_size": top.global_size,
                "bottom_local_fe_dofs": bottom.n_fe,
                "top_local_fe_dofs": top.n_fe,
                "bottom_local_mesh_cells": list(bottom.local_mesh.mesh_cells),
                "top_local_mesh_cells": list(top.local_mesh.mesh_cells),
                "bottom_local_thickness_nm": (
                    bottom.local_mesh.interface_z_nm
                    - bottom.local_mesh.external_z_nm
                ),
                "top_local_thickness_nm": (
                    top.local_mesh.external_z_nm - top.local_mesh.interface_z_nm
                ),
                "bottom_matrix_stats": bottom.augmented_matrix_stats,
                "top_matrix_stats": top.augmented_matrix_stats,
                "internal_unknown_count": coupling.internal_unknown_count,
                "qep_to_interface_quadrature_degree": (
                    coupling.interface_quadrature_degree
                ),
                "dense_interface_square_formed": (
                    system.dense_interface_square_formed
                    if system is not None
                    else primary_schur_system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (
                    coupling.full_field_or_mode_gathered
                ),
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
                        "lifecycle_strategy": (
                            primary_schur_system.lifecycle_strategy
                        ),
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
                "modal_solve_seconds": getattr(
                    solution, "modal_solve_seconds", None
                ),
                "recovery_seconds": getattr(solution, "recovery_seconds", None),
                "recovery_factor_setup_seconds": getattr(
                    solution, "recovery_factor_setup_seconds", {}
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
                        if key.startswith("sampled_interface_")
                        or key.startswith("volume_")
                        or key.startswith("middle_plane_")
                    )
                ),
                "pointwise_h_jump_checked": physical_fields is not None,
                "volume_absorption_reconstructed": physical_fields is not None,
                "selected_middle_planes_reconstructed": physical_fields is not None,
                "official_record": False,
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
                local_system.A.destroy()
                local_system.b.destroy()
        if positive is not None:
            positive.destroy()
        if negative is not None:
            negative.destroy()
        if operators is not None:
            operators.destroy()

    if comm.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        print(f"Task32 Phase6 record: {args.output}", flush=True)
        print(f"Task32 Phase6 status: {record['status']}", flush=True)
    comm.barrier()
    if not record["qualification"]["integration_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
