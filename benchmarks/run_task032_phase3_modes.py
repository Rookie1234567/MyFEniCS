from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import resource
import shlex
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI
import numpy as np

from src.common.config_3d import target_stage4_config
from src.modes.cross_section_spaces import (
    CrossSectionMaterial,
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    BiorthogonalModeBasis,
    build_biorthogonal_mode_basis,
    pair_reciprocal_mode_bases,
    track_mode_bases,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "080"
    / "phase3"
    / "mode_classification.json"
)


def _complex_json(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _complex_matrix_json(matrix: np.ndarray) -> list[list[list[float]]]:
    return [
        [_complex_json(value) for value in row]
        for row in np.asarray(matrix, dtype=np.complex128)
    ]


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
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
        tracked_status = (
            None
            if verified_clean_sha is not None
            else _git("status", "--porcelain", "--untracked-files=no")
        )
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or (verified_clean_sha is None and tracked_status is None):
        raise SystemExit("Cannot verify Task32 Phase3 source identity and cleanliness.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            character not in "0123456789abcdef" for character in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full hexadecimal Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match mounted HEAD {head}."
            )
        tracked_dirty = False
        verification = "host_git_clean_attestation"
    else:
        if tracked_status and not allow_dirty_research:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase3 code first or pass "
                "--allow-dirty-research for an explicitly non-qualifying run."
            )
        tracked_dirty = bool(tracked_status)
        verification = (
            "dirty_research_opt_in" if tracked_dirty else "local_git_status"
        )
    return {
        "commit_sha": head,
        "branch": branch,
        "git_dirty": tracked_dirty,
        "tracked_source_dirty": tracked_dirty,
        "verification": verification,
        "verified_clean_sha": verified_clean_sha,
    }


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _peak_rss_mb() -> float:
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _basis_record(
    basis: BiorthogonalModeBasis,
    *,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    mode_records: list[dict[str, Any]] = []
    for index, mode in enumerate(basis.modes):
        left_ownership = comm.gather(
            {
                "rank": comm.rank,
                "reduced_local_size": mode.left_ownership.reduced_local_size,
                "reduced_ownership_range": list(
                    mode.left_ownership.reduced_ownership_range
                ),
                "full_local_size": mode.left_ownership.full_local_size,
                "full_ownership_range": list(
                    mode.left_ownership.full_ownership_range
                ),
            },
            root=0,
        )
        mode_records.append(
            {
                "index": index,
                "beta_per_nm": _complex_json(mode.beta),
                "left_adjoint_beta_per_nm": _complex_json(
                    mode.left_adjoint_beta
                ),
                "left_pair_relative_error": basis.left_pair_relative_errors[
                    index
                ],
                "right_polynomial_relative_residual": (
                    mode.right.polynomial_relative_residual
                ),
                "left_polynomial_relative_residual": (
                    mode.left_polynomial_relative_residual
                ),
                "poynting_z_before_normalization": (
                    mode.poynting_z_before_normalization
                ),
                "poynting_z_after_normalization": (
                    mode.poynting_z_after_normalization
                ),
                "flux_tolerance": mode.flux_tolerance,
                "kind": mode.kind,
                "direction": mode.direction,
                "classification_basis": mode.classification_basis,
                "passive_branch_valid": mode.passive_branch_valid,
                "right_normalization_kind": mode.right.normalization_kind,
                "right_scale": mode.right_scale,
                "qprime_overlap_after": _complex_json(
                    mode.qprime_overlap_after
                ),
                "left_ownership_by_rank": left_ownership,
                "full_vector_gathered": False,
            }
        )
    return {
        "mode_count": len(basis.modes),
        "modes": mode_records,
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
        "biorthogonality_matrix": _complex_matrix_json(
            basis.biorthogonality_matrix
        ),
        "max_biorthogonality_identity_error": basis.max_identity_error,
        "adjoint_solver": {
            "solver": basis.adjoint_solver_report.solver,
            "problem_type": basis.adjoint_solver_report.problem_type,
            "spectral_transform": basis.adjoint_solver_report.spectral_transform,
            "requested_modes": basis.adjoint_solver_report.requested_modes,
            "converged_modes": basis.adjoint_solver_report.converged_modes,
            "iteration_count": basis.adjoint_solver_report.iteration_count,
            "convergence_reason": basis.adjoint_solver_report.convergence_reason,
        },
        "full_vector_gathered": basis.full_vector_gathered,
    }


def _run_material_case(
    material_kind: CrossSectionMaterial,
    *,
    h_nm: float,
    requested_modes: int,
    include_negative: bool,
) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    cfg = target_stage4_config(degree=2, h_nm=h_nm)
    cross_section = build_matching_cross_section(cfg, material_kind)
    spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
    operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
    reference_index = (
        cfg.n_grating if material_kind == "lossy_homogeneous" else cfg.n_air
    )
    target = analytic_homogeneous_beta(cfg, reference_index)
    started = time.perf_counter()
    positive_right, _ = solve_quadratic_beta_modes(
        operators, target=target, requested_modes=requested_modes
    )
    positive = build_biorthogonal_mode_basis(
        cfg,
        cross_section,
        spaces,
        operators,
        positive_right,
        adjoint_target=np.conj(target),
        requested_left_modes=requested_modes,
    )
    positive_seconds = _max_elapsed(comm, started)

    negative = None
    negative_seconds = None
    pairs = ()
    if include_negative:
        started = time.perf_counter()
        negative_right, _ = solve_quadratic_beta_modes(
            operators, target=-target, requested_modes=requested_modes
        )
        negative = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=requested_modes,
        )
        negative_seconds = _max_elapsed(comm, started)
        pairs = pair_reciprocal_mode_bases(operators, positive, negative)

    try:
        record = {
            "case_id": f"{material_kind}_p2_h{h_nm:g}".replace(".", "p"),
            "material_kind": material_kind,
            "h_nm": h_nm,
            "mesh_cells_xy": list(cross_section.mesh_cells),
            "full_shape": list(operators.full_shape),
            "reduced_shape": list(operators.reduced_shape),
            "target_beta_per_nm": _complex_json(target),
            "positive": _basis_record(positive, comm=comm),
            "negative": (
                None if negative is None else _basis_record(negative, comm=comm)
            ),
            "reciprocal_pairs": [
                {
                    "positive_index": pair.positive_index,
                    "negative_index": pair.negative_index,
                    "relative_beta_error": pair.relative_beta_error,
                    "electric_mass_overlap": pair.electric_mass_overlap,
                    "opposite_direction": pair.opposite_direction,
                    "passive_branches_valid": pair.passive_branches_valid,
                }
                for pair in pairs
            ],
            "timing_seconds_max_rank": {
                "positive_right_and_adjoint": positive_seconds,
                "negative_right_and_adjoint": negative_seconds,
            },
            "constraint_communication_scope": (
                operators.constraints.communication_scope
            ),
        }
    finally:
        positive.destroy()
        if negative is not None:
            negative.destroy()
        operators.destroy()
    return record


def _run_angle_tracking(*, h_nm: float, requested_modes: int) -> dict[str, Any]:
    bases = []
    for theta in (80.0, 79.8):
        cfg = target_stage4_config(degree=2, h_nm=h_nm)
        cfg.incident_theta_deg = theta
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(
            cfg, cross_section, spaces
        )
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        right_modes, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=requested_modes
        )
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=requested_modes,
        )
        bases.append((theta, operators, basis))
    theta_previous, operators_previous, previous = bases[0]
    theta_current, operators_current, current = bases[1]
    try:
        tracking = track_mode_bases(operators_current, previous, current)
        return {
            "h_nm": h_nm,
            "theta_previous_deg": theta_previous,
            "theta_current_deg": theta_current,
            "previous_mode_count": len(previous.modes),
            "current_mode_count": len(current.modes),
            "matches": [
                {
                    "previous_index": match.previous_index,
                    "current_index": match.current_index,
                    "overlap": match.overlap,
                    "relative_beta_change": match.relative_beta_change,
                }
                for match in tracking.matches
            ],
            "unmatched_previous": list(tracking.unmatched_previous),
            "unmatched_current": list(tracking.unmatched_current),
            "subspaces": [
                {
                    "previous_indices": list(report.previous_indices),
                    "current_indices": list(report.current_indices),
                    "singular_values": list(report.singular_values),
                    "max_principal_angle_rad": report.max_principal_angle_rad,
                }
                for report in tracking.subspaces
            ],
            "overlap_matrix": tracking.overlap_matrix.tolist(),
        }
    finally:
        previous.destroy()
        current.destroy()
        operators_previous.destroy()
        operators_current.destroy()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase3 mode classification and biorthogonality validation"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default="sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d",
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get(
            "TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"
        ),
    )
    parser.add_argument("--basis-h-nm", type=float, default=10.0)
    parser.add_argument("--tracking-h-nm", type=float, default=10.0)
    parser.add_argument("--requested-modes", type=int, default=2)
    parser.add_argument("--skip-tracking", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least two.")
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    started = time.perf_counter()
    cases = [
        _run_material_case(
            "air",
            h_nm=args.basis_h_nm,
            requested_modes=args.requested_modes,
            include_negative=True,
        ),
        _run_material_case(
            "lossy_homogeneous",
            h_nm=args.basis_h_nm,
            requested_modes=args.requested_modes,
            include_negative=False,
        ),
        _run_material_case(
            "stage4_xy",
            h_nm=args.basis_h_nm,
            requested_modes=args.requested_modes,
            include_negative=False,
        ),
    ]
    tracking = (
        None
        if args.skip_tracking
        else _run_angle_tracking(
            h_nm=args.tracking_h_nm,
            requested_modes=args.requested_modes,
        )
    )
    elapsed = _max_elapsed(comm, started)
    rss_by_rank = comm.gather(
        {"rank": comm.rank, "historical_peak_rss_mb": _peak_rss_mb()},
        root=0,
    )

    all_bases = [
        case[key]
        for case in cases
        for key in ("positive", "negative")
        if case[key] is not None
    ]
    all_modes = [mode for basis in all_bases for mode in basis["modes"]]
    reciprocal_pairs = cases[0]["reciprocal_pairs"]
    tracking_matches = [] if tracking is None else tracking["matches"]
    tracking_subspaces = [] if tracking is None else tracking["subspaces"]
    gates = {
        "all_right_residuals_le_1e-8": all(
            mode["right_polynomial_relative_residual"] <= 1.0e-8
            for mode in all_modes
        ),
        "all_left_residuals_le_1e-8": all(
            mode["left_polynomial_relative_residual"] <= 1.0e-8
            for mode in all_modes
        ),
        "all_left_pairs_le_1e-7": all(
            mode["left_pair_relative_error"] <= 1.0e-7 for mode in all_modes
        ),
        "all_biorthogonality_identity_errors_le_1e-7": all(
            basis["max_biorthogonality_identity_error"] <= 1.0e-7
            for basis in all_bases
        ),
        "all_flux_normalized_or_near_zero": all(
            abs(abs(mode["poynting_z_after_normalization"]) - 1.0)
            <= 1.0e-7
            or abs(mode["poynting_z_after_normalization"])
            <= mode["flux_tolerance"]
            for mode in all_modes
        ),
        "all_passive_branches_valid": all(
            mode["passive_branch_valid"] for mode in all_modes
        ),
        "air_reciprocal_pairs_complete": (
            len(reciprocal_pairs) >= 2
            and all(
                pair["relative_beta_error"] <= 1.0e-7
                and pair["opposite_direction"]
                and pair["passive_branches_valid"]
                for pair in reciprocal_pairs
            )
        ),
        "angle_tracking_complete": (
            args.skip_tracking
            or (
                len(tracking_matches) >= 2
                and not tracking["unmatched_previous"]
                and all(match["overlap"] >= 0.5 for match in tracking_matches)
                and all(
                    report["max_principal_angle_rad"] <= 0.2
                    for report in tracking_subspaces
                )
            )
        ),
        "no_full_vector_gather": all(
            mode["full_vector_gathered"] is False for mode in all_modes
        ),
    }
    status = "pass" if all(gates.values()) else "fail"
    if comm.rank == 0:
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        record = {
            "schema_version": 1,
            "benchmark_id": "case080_task032_phase3_modes",
            "status": status,
            "timestamp_utc": timestamp_utc,
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp_utc,
                "command": "python -m benchmarks.run_task032_phase3_modes "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "eigen_backend": "SLEPc.PEP/TOAR + explicit adjoint QEP",
                "full_eigenvector_gather": False,
                "provenance": (
                    "clean_task032_phase3_modes"
                    if not provenance["tracked_source_dirty"]
                    else "dirty_task032_phase3_modes_research"
                ),
            },
            "cases": cases,
            "angle_tracking": tracking,
            "gates": gates,
            "elapsed_seconds_max_rank": elapsed,
            "historical_peak_rss_by_rank": rss_by_rank,
            "memory_note": (
                "Per-rank process-lifetime historical peaks; not simultaneous and "
                "never summed. Full eigenvectors remain distributed."
            ),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": status, "gates": gates}, indent=2))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
