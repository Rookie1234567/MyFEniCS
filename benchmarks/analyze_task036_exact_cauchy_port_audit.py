"""Build the compact Task036 exact-Cauchy audit from frozen raw artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _selected_continuity(
    blocks_path: Path,
    coefficients_path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    with np.load(blocks_path) as archive:
        S_LL = np.asarray(archive["S_LL"], dtype=np.complex128)
        S_LR = np.asarray(archive["S_LR"], dtype=np.complex128)
        S_RL = np.asarray(archive["S_RL"], dtype=np.complex128)
        S_RR = np.asarray(archive["S_RR"], dtype=np.complex128)
    with np.load(coefficients_path) as archive:
        z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
        coefficients = np.asarray(
            archive["coefficients"], dtype=np.complex128
        )
    left = S_LL @ coefficients[:-1].T + S_LR @ coefficients[1:].T
    right = S_RL @ coefficients[:-1].T + S_RR @ coefficients[1:].T
    values = []
    for plane in range(1, len(z_nm) - 1):
        lower = right[:, plane - 1]
        upper = left[:, plane]
        values.append(
            np.linalg.norm(lower + upper)
            / max(np.linalg.norm(lower), np.linalg.norm(upper), 1.0e-30)
        )
    return z_nm[1:-1], np.asarray(values, dtype=np.float64)


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relative_path(path, root),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _recorded_artifact(record: dict[str, Any], root: Path) -> dict[str, Any]:
    """Verify a raw-record artifact and make its path repository-relative."""

    path = Path(record["path"])
    if not path.is_absolute():
        path = root / path
    actual_sha256 = _sha256(path)
    expected_sha256 = record.get("sha256")
    if expected_sha256 is not None and expected_sha256 != actual_sha256:
        raise ValueError(
            f"artifact hash mismatch for {path}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    normalized = dict(record)
    normalized.update(
        {
            "path": _relative_path(path, root),
            "sha256": actual_sha256,
            "size_bytes": path.stat().st_size,
        }
    )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--projected-blocks", type=Path, required=True)
    parser.add_argument("--exact-coefficients", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    raw = json.loads(args.audit.read_text(encoding="utf-8"))
    z_nm, continuity = _selected_continuity(
        args.projected_blocks, args.exact_coefficients
    )
    cauchy = raw["exact_cauchy"]
    port_lengths = raw["port_operator"]["lengths"]
    sensitivity = raw["persistent_failing_channel_sensitivity"]
    adjoint_residuals = [
        float(item["adjoint"]["adjoint_residual"]["relative_residual"])
        for item in sensitivity["channels"]
    ]
    selected_operator = {
        label: {
            "exact_fe_to_current_modal_frobenius_relative": value[
                "selected_operator"
            ]["exact_fe_to_current_modal_frobenius_relative"],
            "exact_projected_trace_to_modal_relative": value[
                "actual_full3d_trace"
            ]["exact_projected_to_modal_relative"],
            "actual_selected_to_modal_relative": value[
                "actual_full3d_trace"
            ]["actual_selected_to_modal_relative"],
            "actual_test_space_complement_relative_fixed_coordinate": value[
                "actual_full3d_trace"
            ]["actual_test_space_complement_relative"],
            "max_star_pivot_condition": value["stable_composition"][
                "max_pivot_condition"
            ],
            "max_star_solve_relative_residual": value[
                "stable_composition"
            ]["max_pivot_solve_relative_residual"],
        }
        for label, value in port_lengths.items()
    }
    payload = {
        "schema_version": "task036.exact-cauchy-port-audit-compact.v1",
        "status": "complete_no_actual_candidate_run",
        "numerical_source_sha": raw["metadata"]["source_sha"],
        "mpi_size": raw["metadata"]["mpi_size"],
        "abi": {
            "scalar_type": raw["metadata"]["scalar_type"],
            "int_type": raw["metadata"]["int_type"],
        },
        "command": raw["metadata"]["command"],
        "artifacts": {
            "raw_audit": _artifact(args.audit, args.repo_root),
            "frozen_projected_one_cell_blocks": _artifact(
                args.projected_blocks, args.repo_root
            ),
            "frozen_exact_petrov_plane_coefficients": _artifact(
                args.exact_coefficients, args.repo_root
            ),
            "exact_cauchy_npz": _recorded_artifact(
                raw["exact_cauchy"]["raw_archive"], args.repo_root
            ),
            "persistent_channel_adjoint_npz": _recorded_artifact(
                sensitivity["raw_archive"], args.repo_root
            ),
        },
        "withdrawn_raw_diagnostic": {
            "field": (
                "exact_cauchy.all_internal_conormal_cancellation_relative"
            ),
            "reason": (
                "left/right endpoint active rows have different numbering "
                "and orientation; raw 1200-vectors cannot be added directly"
            ),
            "replacement": (
                "selected Petrov conormals replayed from the coordinate-"
                "matched frozen one-cell blocks and exact coefficients"
            ),
        },
        "selected_petrov_internal_flux_continuity": {
            "z_nm": z_nm.tolist(),
            "relative": continuity.tolist(),
            "max_relative": float(np.max(continuity)),
            "minimum_relative": float(np.min(continuity)),
            "minimum_z_nm": float(z_nm[int(np.argmin(continuity))]),
        },
        "requested_exact_cauchy_planes": {
            label: {
                "z_nm": value["z_nm"],
                "electric_projection_relative": value[
                    "electric_projection_relative"
                ],
                "weak_conormal_sides": value["weak_conormal_sides"],
            }
            for label, value in cauchy["requested_planes"].items()
        },
        "one_cell_identity": raw["one_cell_identity"],
        "qep_coordinate_replay": raw["trace_basis"],
        "port_pair": raw["trace_basis"][
            "port_pair_gram_and_inf_sup"
        ],
        "cauchy_best_approximation": {
            "electric": cauchy["electric_best_approximation"],
            "magnetic_traction": cauchy[
                "magnetic_traction_best_approximation"
            ],
            "joint": cauchy["joint_cauchy_best_approximation"],
        },
        "port_operator_by_length": selected_operator,
        "test_space_complement_interpretation": (
            "The approximately 0.949 values use the fixed independent-row "
            "Euclidean coordinate norm. They are a diagnostic only and must "
            "not be reported as a physical-energy deficit."
        ),
        "persistent_16_channel_adjoint": {
            "count": len(sensitivity["channels"]),
            "max_adjoint_relative_residual": max(adjoint_residuals),
            "direction_svd": sensitivity["adjoint_trace_svd"],
            "local_prediction_vector_relative_error": sensitivity[
                "prediction_vector_relative_error"
            ],
            "local_prediction_actual_absolute_cosine": sensitivity[
                "prediction_actual_absolute_cosine"
            ],
            "quantitative_prediction_credit": "not_granted",
        },
        "decision": {
            "selected_core_operator": "qualified_inside_selected_M120_space",
            "endpoint_joint_cauchy": "incomplete",
            "few_common_failing_channel_directions": False,
            "frozen_single_enrichment_family": "transfer_optimal_port_modes",
            "implementation_status": "not_run_waiting_for_review",
            "rationale": (
                "The selected-space FE/modal operator agrees to about 2e-11, "
                "while endpoint traction/joint-Cauchy residuals are O(1e-5) "
                "and the 16 channel sensitivities require rank 16 for 95%. "
                "Transfer-optimal modes target the joint trace/traction "
                "complement without changing the M120 core or adding one "
                "ad-hoc mode per failed output."
            ),
        },
        "scope": {
            "full3d_or_hybrid_forward_pde_run": False,
            "actual_enriched_candidate_run": False,
            "ordinary_default_changed": False,
            "rcwa_development": False,
        },
        "timing_seconds": raw["timing_seconds"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
