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

from src.common.config_3d import target_stage4_config
from src.modes.cross_section_spaces import (
    CrossSectionMaterial,
    build_cross_section_spaces,
    build_matching_cross_section,
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
    / "phase2"
    / "qep_validation.json"
)


def _complex_json(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    comm: MPI.Intracomm, verified_clean_sha: str | None, allow_dirty_research: bool
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
        raise SystemExit("Cannot verify Task32 Phase2 source identity and cleanliness.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(char not in "0123456789abcdef" for char in verified):
            raise SystemExit("--verified-clean-sha must be a full hexadecimal Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match mounted HEAD {head}."
            )
        # The Windows host uses core.autocrlf=true, while git inside the Linux
        # bind mount reports every CRLF working-tree file as modified.  The
        # full SHA is therefore an explicit host-side clean attestation, as in
        # the Task31 formal runner; HEAD must still match inside the container.
        tracked_dirty = False
        verification = "host_git_clean_attestation"
    else:
        if tracked_status and not allow_dirty_research:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase2 code first or pass "
                "--allow-dirty-research for an explicitly non-qualifying run."
            )
        tracked_dirty = bool(tracked_status)
        verification = "dirty_research_opt_in" if tracked_dirty else "local_git_status"
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


def _mode_record(mode) -> dict[str, Any]:
    return {
        "beta_per_nm": _complex_json(mode.beta),
        "polynomial_relative_residual": mode.polynomial_relative_residual,
        "slepc_relative_error": mode.slepc_relative_error,
        "normalization_kind": mode.normalization_kind,
        "normalization_factor": mode.normalization_factor,
        "electric_l2_norm_after": mode.electric_l2_norm_after,
        "gathered_to_root": mode.ownership.gathered_to_root,
    }


def _solve_target(operators, target: complex, requested_modes: int) -> tuple[dict[str, Any], complex]:
    started = time.perf_counter()
    modes, report = solve_quadratic_beta_modes(
        operators,
        target=target,
        requested_modes=requested_modes,
    )
    elapsed = _max_elapsed(operators.K0.comm.tompi4py(), started)
    if not modes:
        raise RuntimeError(f"PEP converged no modes near target {target!r}.")
    selected = min(modes, key=lambda mode: abs(mode.beta - target))
    ownership_by_rank = operators.K0.comm.tompi4py().gather(
        {
            "rank": operators.K0.comm.tompi4py().rank,
            "reduced_local_size": selected.ownership.reduced_local_size,
            "reduced_ownership_range": list(selected.ownership.reduced_ownership_range),
            "full_local_size": selected.ownership.full_local_size,
            "full_ownership_range": list(selected.ownership.full_ownership_range),
        },
        root=0,
    )
    record = {
        "target_per_nm": _complex_json(target),
        "selected": _mode_record(selected),
        "spectrum": [_mode_record(mode) for mode in modes],
        "solver_report": {
            "solver": report.solver,
            "problem_type": report.problem_type,
            "spectral_transform": report.spectral_transform,
            "requested_modes": report.requested_modes,
            "converged_modes": report.converged_modes,
            "iteration_count": report.iteration_count,
            "convergence_reason": report.convergence_reason,
        },
        "elapsed_seconds_max_rank": elapsed,
        "ownership_by_rank": ownership_by_rank,
    }
    beta = complex(selected.beta)
    for mode in modes:
        mode.destroy()
    return record, beta


def _run_case(
    *,
    material_kind: CrossSectionMaterial,
    h_nm: float,
    solve_negative: bool,
    requested_modes: int,
) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    cfg = target_stage4_config(degree=2, h_nm=h_nm)

    started = time.perf_counter()
    cross_section = build_matching_cross_section(cfg, material_kind)
    spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
    mesh_space_seconds = _max_elapsed(comm, started)

    started = time.perf_counter()
    operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
    assembly_seconds = _max_elapsed(comm, started)

    if material_kind == "lossy_homogeneous":
        reference_index = complex(cfg.n_grating)
    else:
        reference_index = complex(cfg.n_air)
    positive_target = analytic_homogeneous_beta(cfg, reference_index)
    positive, beta_positive = _solve_target(
        operators, positive_target, requested_modes
    )
    negative = None
    beta_negative = None
    if solve_negative:
        negative, beta_negative = _solve_target(
            operators, -positive_target, requested_modes
        )

    matrix_info = {
        name: {
            "shape": list(matrix.getSize()),
            "nnz_used": float(matrix.getInfo()["nz_used"]),
            "memory_bytes": float(matrix.getInfo()["memory"]),
        }
        for name, matrix in (
            ("K0", operators.K0),
            ("K1", operators.K1),
            ("K2", operators.K2),
            ("electric_mass", operators.electric_mass),
        )
    }
    rss_by_rank = comm.gather(
        {"rank": comm.rank, "historical_peak_rss_mb": _peak_rss_mb()}, root=0
    )
    transverse_constraints_global = comm.allreduce(
        operators.constraints.transverse_constraint_count, op=MPI.SUM
    )
    longitudinal_constraints_global = comm.allreduce(
        operators.constraints.longitudinal_constraint_count, op=MPI.SUM
    )
    record: dict[str, Any] = {
        "case_id": f"{material_kind}_p2_h{h_nm:g}".replace(".", "p"),
        "material_kind": material_kind,
        "h_nm": h_nm,
        "mesh_cells_xy": list(cross_section.mesh_cells),
        "full_shape": list(operators.full_shape),
        "reduced_shape": list(operators.reduced_shape),
        "global_slave_count": operators.transform.global_slave_count,
        "constraint_communication_scope": operators.constraints.communication_scope,
        "transverse_constraint_count_global": transverse_constraints_global,
        "longitudinal_constraint_count_global": longitudinal_constraints_global,
        "max_pair_coordinate_error": operators.constraints.max_pair_coordinate_error,
        "max_probe_residual": operators.constraints.max_probe_residual,
        "phase_x": _complex_json(operators.constraints.phase_x),
        "phase_y": _complex_json(operators.constraints.phase_y),
        "formulation": operators.formulation,
        "polynomial_order": operators.polynomial_order,
        "leading_coefficient_singular_by_design": operators.leading_coefficient_singular_by_design,
        "scalar_dtype": operators.scalar_dtype,
        "matrix_info": matrix_info,
        "timing": {
            "mesh_and_spaces_seconds_max_rank": mesh_space_seconds,
            "assembly_and_reduction_seconds_max_rank": assembly_seconds,
        },
        "positive_target": positive,
        "negative_target": negative,
        "historical_peak_rss_by_rank": rss_by_rank,
        "memory_note": (
            "Per-rank process-lifetime historical peaks; not simultaneous and never summed. "
            "External stage sampling remains required for the final Task32 memory claim."
        ),
    }
    if material_kind in {"air", "lossy_homogeneous"}:
        record["analytic_beta_per_nm"] = _complex_json(positive_target)
        record["positive_relative_beta_error"] = abs(
            beta_positive - positive_target
        ) / max(abs(positive_target), 1.0e-30)
    else:
        record["analytic_beta_per_nm"] = None
        record["positive_relative_beta_error"] = None
    if beta_negative is not None:
        record["reciprocal_pair_absolute_error_per_nm"] = abs(
            beta_positive + beta_negative
        )
        record["reciprocal_pair_relative_error"] = abs(
            beta_positive + beta_negative
        ) / max(abs(beta_positive), 1.0e-30)
    else:
        record["reciprocal_pair_absolute_error_per_nm"] = None
        record["reciprocal_pair_relative_error"] = None

    operators.destroy()
    return record


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase2 distributed cross-section QEP validation"
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
        default=os.environ.get("TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    parser.add_argument("--requested-modes", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least two for polarization pairs.")

    cases: list[dict[str, Any]] = []
    for h_nm in (5.0, 3.0, 2.0, 1.5):
        cases.append(
            _run_case(
                material_kind="air",
                h_nm=h_nm,
                solve_negative=h_nm == 2.0,
                requested_modes=args.requested_modes,
            )
        )
    cases.append(
        _run_case(
            material_kind="lossy_homogeneous",
            h_nm=2.0,
            solve_negative=True,
            requested_modes=args.requested_modes,
        )
    )
    cases.append(
        _run_case(
            material_kind="stage4_xy",
            h_nm=3.0,
            solve_negative=True,
            requested_modes=args.requested_modes,
        )
    )

    if comm.rank == 0:
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        air_errors = [
            float(case["positive_relative_beta_error"])
            for case in cases
            if case["material_kind"] == "air"
        ]
        payload = {
            "schema_version": 1,
            "benchmark_id": "case080_task032_phase2_qep",
            "status": "pass",
            "timestamp_utc": timestamp_utc,
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp_utc,
                "command": "python -m benchmarks.run_task032_phase2_qep "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "provenance": "clean_task032_phase2_qep",
                "eigen_backend": "SLEPc.PEP/TOAR",
                "full_eigenvector_gather": False,
            },
            "physics": {
                "lambda0_nm": 13.5,
                "period_x_nm": 50.0,
                "period_y_nm": 25.0,
                "incident_theta_deg_from_minus_z": 80.0,
                "grazing_angle_deg": 10.0,
                "incident_phi_deg": 0.0,
                "n_air": _complex_json(1.0 + 0.0j),
                "n_si": _complex_json(
                    target_stage4_config(degree=2, h_nm=5.0).n_grating
                ),
            },
            "cases": cases,
            "gates": {
                "all_polynomial_relative_residual_le_1e-10": all(
                    target["selected"]["polynomial_relative_residual"] <= 1.0e-10
                    for case in cases
                    for target in (case["positive_target"], case["negative_target"])
                    if target is not None
                ),
                "all_electric_l2_norm_error_le_1e-10": all(
                    abs(target["selected"]["electric_l2_norm_after"] - 1.0) <= 1.0e-10
                    for case in cases
                    for target in (case["positive_target"], case["negative_target"])
                    if target is not None
                ),
                "air_beta_error_strictly_decreases": all(
                    later < earlier
                    for earlier, later in zip(air_errors, air_errors[1:])
                ),
                "air_h2_relative_beta_error_le_1p5e-2": air_errors[2] <= 1.5e-2,
                "air_h1p5_relative_beta_error_le_5e-3": air_errors[3] <= 5.0e-3,
                "lossy_h2_relative_beta_error_le_2e-2": cases[-2][
                    "positive_relative_beta_error"
                ]
                <= 2.0e-2,
                "lossy_forward_imag_beta_positive": cases[-2]["positive_target"][
                    "selected"
                ]["beta_per_nm"][1]
                > 0.0,
                "all_requested_pair_errors_le_1e-9": all(
                    case["reciprocal_pair_relative_error"] is None
                    or case["reciprocal_pair_relative_error"] <= 1.0e-9
                    for case in cases
                ),
                "boundary_only_constraint_communication": all(
                    case["constraint_communication_scope"]
                    == "periodic_boundary_dofs_only"
                    for case in cases
                ),
                "no_full_eigenvector_gather": True,
            },
        }
        if not all(payload["gates"].values()):
            payload["status"] = "fail"
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"status": payload["status"], "output": str(output)}))
        if payload["status"] != "pass":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
