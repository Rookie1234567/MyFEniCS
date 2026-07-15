from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI
import numpy as np

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
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system


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
REFERENCE_BY_H = {
    5.0: ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h5_reference.json",
    3.0: ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h3_reference.json",
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
        if verified_clean_sha is not None:
            tracked_status = None
        elif allow_dirty_research:
            tracked_status = "dirty_research_status_scan_skipped"
        else:
            tracked_status = _git(
                "status", "--porcelain", "--untracked-files=no"
            )
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or (
        verified_clean_sha is None and tracked_status is None
    ):
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
        tracked_dirty = False
        verification = "host_git_clean_attestation"
    else:
        if allow_dirty_research:
            tracked_dirty = True
            verification = "dirty_research_opt_in_status_scan_skipped"
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


def _reference_comparison(
    h_nm: float, port_power: dict[str, Any]
) -> dict[str, Any] | None:
    reference_path = next(
        (
            path
            for level, path in REFERENCE_BY_H.items()
            if abs(h_nm - level) <= 1.0e-12
        ),
        None,
    )
    if reference_path is None or not reference_path.exists():
        return None
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase6 real-QEP hybrid augmented direct diagnostic"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--requested-modes", type=int, default=2)
    parser.add_argument("--near-degenerate-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--block-rotation-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
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
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least 2.")
    if args.near_degenerate_tolerance <= 0.0:
        raise SystemExit("--near-degenerate-tolerance must be positive.")
    if args.block_rotation_tolerance <= 0.0:
        raise SystemExit("--block-rotation-tolerance must be positive.")
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )

    def progress(message: str) -> None:
        if comm.rank == 0:
            print(message, flush=True)

    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    cfg = target_stage4_config(degree=2, h_nm=args.h_nm)
    operators = None
    positive = None
    negative = None
    bottom = None
    top = None
    coupling = None
    system = None
    solution = None
    record = None
    try:
        started = time.perf_counter()
        cross_section = build_matching_cross_section(cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=2
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

        started = time.perf_counter()
        positive_right, positive_report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=args.requested_modes,
        )
        progress("Task32 Phase6: positive right QEP modes complete")
        positive = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=args.requested_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
        progress("Task32 Phase6: positive adjoint basis complete")
        negative_right, negative_report = solve_quadratic_beta_modes(
            operators,
            target=-target,
            requested_modes=args.requested_modes,
        )
        progress("Task32 Phase6: negative right QEP modes complete")
        negative = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=args.requested_modes,
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
        progress(
            "Task32 Phase6: positive betas "
            f"{[complex(mode.beta) for mode in positive.modes]}"
        )
        progress(
            "Task32 Phase6: positive near-degenerate groups "
            f"{[group.indices for group in positive.groups]}"
        )
        pairs = pair_reciprocal_mode_bases(operators, positive, negative)
        timings["positive_and_negative_biorthogonal_bases"] = _max_elapsed(
            comm, started
        )
        progress("Task32 Phase6: real positive/negative QEP bases complete")

        started = time.perf_counter()
        bottom = assemble_hybrid_local_dtn_system(cfg, "bottom")
        top = assemble_hybrid_local_dtn_system(cfg, "top")
        timings["two_local_fem_dtn_systems"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: bottom/top local FEM-DtN systems complete")

        started = time.perf_counter()
        coupling = build_hybrid_internal_mode_coupling(
            cfg,
            spaces,
            positive,
            negative,
            bottom,
            top,
            log=progress,
        )
        timings["internal_modal_coupling"] = _max_elapsed(comm, started)

        started = time.perf_counter()
        system = build_hybrid_augmented_direct_system(
            bottom, top, coupling
        )
        timings["monolithic_assembly"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: monolithic augmented AIJ complete")

        solution = solve_hybrid_augmented_direct(system, bottom, top)
        validation = evaluate_hybrid_augmented_solution(
            cfg, bottom, top, coupling, solution
        )
        port_power = validation["port_power"]
        reference = _reference_comparison(args.h_nm, port_power)
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
        integration_pass = all(gates.values())
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        record = {
            "schema_version": 1,
            "benchmark_id": "task032_phase6_hybrid_augmented_direct",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": (
                "physical_integration_pass_mode_convergence_pending"
                if integration_pass
                else "physical_integration_failed"
            ),
            "metadata": {
                **provenance,
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
            },
            "case": {
                "material_kind": "stage4_xy",
                "h_nm": args.h_nm,
                "requested_modes_per_direction": args.requested_modes,
                "near_degenerate_tolerance": args.near_degenerate_tolerance,
                "block_rotation_tolerance": args.block_rotation_tolerance,
                "middle_length_nm": 100.0,
                "wavelength_nm": cfg.lambda0,
                "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
                "polarization_kind": cfg.polarization_kind,
            },
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "positive_solver_converged_modes": (
                    positive_report.converged_modes
                ),
                "negative_solver_converged_modes": (
                    negative_report.converged_modes
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
                "matrix_size": list(system.A.getSize()),
                "matrix_stats": system.matrix_stats,
                "block_shapes": system.block_shapes,
                "inserted_nnz_by_block": system.inserted_nnz_by_block,
                "bottom_global_size": bottom.global_size,
                "top_global_size": top.global_size,
                "internal_unknown_count": coupling.internal_unknown_count,
                "dense_interface_square_formed": (
                    system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (
                    coupling.full_field_or_mode_gathered
                ),
            },
            "solve": {
                "factor_solver": solution.factor_solver,
                "converged_reason": solution.converged_reason,
                "true_relative_residual": solution.relative_residual,
                "setup_seconds": solution.setup_seconds,
                "solve_seconds": solution.solve_seconds,
            },
            "validation": validation,
            "full3d_reference_comparison": reference,
            "gates": gates,
            "qualification": {
                "integration_pass": integration_pass,
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "pointwise_h_jump_checked": False,
                "volume_absorption_reconstructed": False,
                "official_record": False,
                "boundary": (
                    "real_QEP_chain_diagnostic_only; requires M funnel, "
                    "pointwise H jump, volume absorption, and h5/h3 comparison"
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
    finally:
        if solution is not None:
            solution.destroy()
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
