"""Research-only positive-branch QEP diagnostic for Task39 V3-7."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np

from benchmarks.task039_v3_7_watchdog import load_v3_7_official_payload
from src.common.config_3d import ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
from src.io.input_validation import simulation_config_3d_from_normalized
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    NearDegenerateBlockPartitionSplitError,
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)


QEP_ONLY_TOLERANCE = 1.0e-13
QEP_ONLY_DEGREE = 6
QEP_ONLY_REQUESTED_MODES = 480
QEP_ONLY_CANDIDATE_MODES = 960
QEP_ONLY_NEAR_TOLERANCE = 1.0e-6
QEP_ONLY_BLOCK_TOLERANCE = 1.0e-6
QEP_ONLY_CUTOFF_NUMERATOR = 1.0e4
QEP_ONLY_MPI_SIZE = 8


def qep_only_contract() -> dict[str, Any]:
    return {
        "mode": "positive_branch_qep_only",
        "physical": {
            "wavelength_nm": 5.0,
            "grazing_angle_deg": 1.0,
            "azimuth_deg": 0.0,
            "polarization": "s",
            "mesh_target_nm": 5.0,
            "degree": QEP_ONLY_DEGREE,
        },
        "selection": {
            "requested_modes": QEP_ONLY_REQUESTED_MODES,
            "candidate_modes": QEP_ONLY_CANDIDATE_MODES,
            "cutoff_numerator": QEP_ONLY_CUTOFF_NUMERATOR,
        },
        "provenance_fields": [
            "input_sha256",
            "resolved_config_sha256",
            "physical_model_sha256",
        ],
        "qep": {
            "tolerance": QEP_ONLY_TOLERANCE,
            "near_degenerate_tolerance": QEP_ONLY_NEAR_TOLERANCE,
            "block_rotation_tolerance": QEP_ONLY_BLOCK_TOLERANCE,
            "near_degenerate_candidate_envelope_factor": 10.0,
            "problem_type": "GENERAL",
            "type": "TOAR",
            "which": "TARGET_MAGNITUDE",
            "spectral_transform": "SINVERT",
            "ksp": "PREONLY",
            "pc": "LU",
            "factor_solver": "MUMPS",
            "runtime_readback": "not_available",
        },
        "forbidden_stages": [
            "endcap",
            "P/T coupling",
            "side factor",
            "modal Schur",
            "outer solve",
            "recovery",
        ],
    }


def _provenance(
    payload: Mapping[str, Any], output: Path, source_sha: str
) -> dict[str, Any]:
    source = payload.get("provenance", {})
    resolved = output.resolve().parents[1] / "resolved_config.json"
    return {
        "source_sha": source_sha,
        "input_sha256": source.get("input_sha256", "not_available"),
        "physical_model_sha256": source.get("physical_model_sha256", "not_available"),
        "resolved_config_sha256": (
            hashlib.sha256(resolved.read_bytes()).hexdigest()
            if resolved.is_file()
            else "not_available"
        ),
    }


def _write_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _solve_report(report: Any) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "solver": report.solver,
        "problem_type": report.problem_type,
        "spectral_transform": report.spectral_transform,
        "target_beta": [float(report.target.real), float(report.target.imag)],
        "requested_modes": report.requested_modes,
        "converged_modes": report.converged_modes,
        "iteration_count": report.iteration_count,
        "convergence_reason": report.convergence_reason,
    }


def _selection_record(selection: Any) -> dict[str, Any] | None:
    if selection is None:
        return None
    return {
        "requested_modes": selection.requested_modes,
        "candidate_modes": selection.candidate_modes,
        "selected_modes": selection.selected_modes,
        "desired_direction": selection.desired_direction,
        "selected_candidate_indices": list(selection.selected_candidate_indices),
        "direction_counts": selection.direction_counts,
        "flux_tolerance": selection.flux_tolerance,
        "passive_candidate_count": selection.passive_candidate_count,
        "finite_candidate_count": selection.finite_candidate_count,
        "numerically_infinite_candidate_count": (
            selection.numerically_infinite_candidate_count
        ),
        "abs_beta_cutoff": selection.abs_beta_cutoff,
        "first_rejected_numerical_infinity_beta": (
            None
            if selection.first_rejected_numerical_infinity_beta is None
            else [
                float(selection.first_rejected_numerical_infinity_beta.real),
                float(selection.first_rejected_numerical_infinity_beta.imag),
            ]
        ),
    }


def _right_mode_snapshots(
    right_modes: list[Any], selected: tuple[int, ...]
) -> list[dict[str, Any]]:
    return [
        {
            "basis_mode_index": basis_index,
            "selected_candidate_index": int(selected[basis_index]),
            "beta_per_nm": [
                float(right_modes[basis_index].beta.real),
                float(right_modes[basis_index].beta.imag),
            ],
            "right_polynomial_relative_residual": (
                right_modes[basis_index].polynomial_relative_residual
            ),
        }
        for basis_index in range(413, 418)
    ]


def _mode_rows(basis: Any, selected: tuple[int, ...]) -> list[dict[str, Any]]:
    groups = {
        int(position): {
            "basis": [int(index) for index in group.indices],
            "selected": [int(selected[index]) for index in group.indices],
        }
        for group in basis.groups
        for position in group.indices
    }
    rows = []
    for basis_index in range(413, 418):
        mode = basis.modes[basis_index]
        group = groups[basis_index]
        rows.append(
            {
                "basis_mode_index": basis_index,
                "selected_candidate_index": int(selected[basis_index]),
                "beta_per_nm": [float(mode.beta.real), float(mode.beta.imag)],
                "group_basis_mode_indices": group["basis"],
                "group_selected_candidate_indices": group["selected"],
                "right_polynomial_relative_residual": (
                    mode.right.polynomial_relative_residual
                ),
                "left_polynomial_relative_residual": mode.left_polynomial_relative_residual,
                "left_pair_relative_error": basis.left_pair_relative_errors[
                    basis_index
                ],
            }
        )
    return rows


def _failure_record(
    contract: Mapping[str, Any],
    provenance: Mapping[str, Any],
    report: Any,
    audit: Mapping[str, Any],
    exc: Exception,
    started: float,
    *,
    target: complex | None,
    operators: Any,
    selection: Any,
    right_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "fail",
        "mode": contract["mode"],
        "provenance": dict(provenance),
        "contract": dict(contract),
        "qep": {
            "solve_report": _solve_report(report),
            "target_beta_per_nm": (
                None if target is None else [float(target.real), float(target.imag)]
            ),
            "full_shape": None if operators is None else list(operators.full_shape),
            "reduced_shape": (
                None if operators is None else list(operators.reduced_shape)
            ),
            "selection": _selection_record(selection),
            "right_mode_snapshots": right_snapshots,
            "basis_left_polynomial_relative_residuals": (
                "not_available_basis_not_returned"
            ),
            "basis_group_indices": "not_available_basis_not_returned",
            "partition_audit": dict(audit),
        },
        "gate": {"overall_pass": False},
        "failure": {"type": type(exc).__name__, "message": str(exc)},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "resource_authority": _resource_authority(),
    }


def _resource_authority() -> dict[str, Any]:
    return {
        "process_tree_rss": "parent_run_summary.resource_authority",
        "swap": "parent_run_summary.resource_authority",
        "hard_stop_bytes": 224_000_000_000,
    }


def run_positive_qep_only(
    resolved_payload: Mapping[str, Any],
    output_path: str | Path,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    source_sha: str,
) -> dict[str, Any]:
    if comm.size != QEP_ONLY_MPI_SIZE:
        raise ValueError("Task39 QEP-only diagnostic requires MPI8.")
    output = Path(output_path)
    contract = qep_only_contract()
    provenance = _provenance(resolved_payload, output, source_sha)
    started = time.perf_counter()
    operators = None
    right_modes = None
    basis = None
    report = None
    target = None
    selection = None
    right_snapshots: list[dict[str, Any]] = []
    try:
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        modal_cfg = deepcopy(cfg)
        modal_cfg.stage4_full3d_assembly_backend = (
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        )
        modal_cfg.matrix_diagnostics_assemble_unconstrained = False
        modal_cfg.matrix_diagnostics_assemble_only = False
        modal_cfg.matrix_diagnostics_factorization_only = False
        cross_section = build_matching_cross_section(modal_cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=QEP_ONLY_DEGREE
        )
        operators = assemble_quadratic_beta_operators(modal_cfg, cross_section, spaces)
        evaluator = PoyntingFluxEvaluator(modal_cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(modal_cfg, modal_cfg.n_air)
        right_modes, report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=QEP_ONLY_CANDIDATE_MODES,
            tolerance=QEP_ONLY_TOLERANCE,
        )
        if report.converged_modes < QEP_ONLY_CANDIDATE_MODES:
            raise RuntimeError("positive QEP did not converge all 960 candidates")
        right_modes, selection = select_passive_direction_modes(
            right_modes,
            desired_direction="forward",
            requested_modes=QEP_ONLY_REQUESTED_MODES,
            poynting_evaluator=evaluator,
            maximum_abs_beta=QEP_ONLY_CUTOFF_NUMERATOR / 5.0,
        )
        if selection.selected_modes != QEP_ONLY_REQUESTED_MODES:
            raise RuntimeError("positive QEP did not select 480 forward modes")
        right_snapshots = _right_mode_snapshots(
            right_modes, selection.selected_candidate_indices
        )
        try:
            basis = build_biorthogonal_mode_basis(
                modal_cfg,
                cross_section,
                spaces,
                operators,
                right_modes,
                adjoint_target=np.conj(target),
                requested_left_modes=QEP_ONLY_CANDIDATE_MODES,
                qep_solver_tolerance=QEP_ONLY_TOLERANCE,
                near_degenerate_tolerance=QEP_ONLY_NEAR_TOLERANCE,
                block_rotation_tolerance=QEP_ONLY_BLOCK_TOLERANCE,
                poynting_evaluator=evaluator,
            )
        except Exception:
            right_modes = None
            raise
        right_modes = None
        audit = basis.near_degenerate_partition_audit
        if audit is None:
            raise RuntimeError("positive QEP partition audit was not emitted")
        passed = bool(audit.get("pass"))
        record = {
            "schema_version": 1,
            "status": "pass" if passed else "fail",
            "mode": contract["mode"],
            "provenance": provenance,
            "contract": contract,
            "qep": {
                "solve_report": _solve_report(report),
                "target_beta_per_nm": [float(target.real), float(target.imag)],
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "selection": _selection_record(selection),
                "right_mode_snapshots": right_snapshots,
                "indices_413_417": _mode_rows(
                    basis, selection.selected_candidate_indices
                ),
                "partition_audit": audit,
            },
            "gate": {
                "selected_480": selection.selected_modes == QEP_ONLY_REQUESTED_MODES,
                "partition_audit_pass": passed,
                "identity_row_norm_le_1e-6": audit["biorthogonality_identity_row_norm"]
                <= QEP_ONLY_BLOCK_TOLERANCE,
                "cross_block_max_le_1e-6": audit["max_cross_block_overlap"]
                <= QEP_ONLY_BLOCK_TOLERANCE,
                "overall_pass": passed,
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started,
            "resource_authority": _resource_authority(),
        }
    except NearDegenerateBlockPartitionSplitError as exc:
        record = _failure_record(
            contract,
            provenance,
            report,
            exc.audit,
            exc,
            started,
            target=target,
            operators=operators,
            selection=selection,
            right_snapshots=right_snapshots,
        )
    finally:
        if basis is not None:
            basis.destroy()
        elif right_modes is not None:
            for mode in right_modes:
                mode.destroy()
        if operators is not None:
            operators.destroy()
    if comm.rank == 0:
        _write_record(output, record)
    comm.barrier()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--launched-by-task038-watchdog", action="store_true")
    args = parser.parse_args(argv)
    if not args.worker or not args.launched_by_task038_watchdog:
        parser.error("QEP-only worker requires the authenticated Task38 watchdog")
    if len(args.source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in args.source_sha.lower()
    ):
        parser.error("--source-sha must be a full hexadecimal commit SHA")
    payload = load_v3_7_official_payload(args.input)
    output = (
        Path(args.run_directory).resolve()
        / "numerical_output"
        / "task039_qep_only_positive.json"
    )
    record = run_positive_qep_only(payload, output, source_sha=args.source_sha)
    if MPI.COMM_WORLD.rank == 0:
        print(json.dumps(record, sort_keys=True))
    return 0 if record.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "QEP_ONLY_BLOCK_TOLERANCE",
    "QEP_ONLY_CANDIDATE_MODES",
    "QEP_ONLY_CUTOFF_NUMERATOR",
    "QEP_ONLY_DEGREE",
    "QEP_ONLY_MPI_SIZE",
    "QEP_ONLY_NEAR_TOLERANCE",
    "QEP_ONLY_REQUESTED_MODES",
    "QEP_ONLY_TOLERANCE",
    "qep_only_contract",
    "run_positive_qep_only",
]
