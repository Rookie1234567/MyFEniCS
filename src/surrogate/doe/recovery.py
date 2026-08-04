"""Local linear off-centre recovery diagnostics for Task005 M4."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .design import FORWARD_SOLVER_SHA, MODEL_ID, ROUTE_ID, canonical_hash
from .sensitivity import noise_sigma, record_observables


def _vector(record: dict[str, Any], contract: str, channels: list[Any] | None = None) -> tuple[np.ndarray, list[Any]]:
    values = record_observables(record)
    if contract == "M0_aggregate_RT":
        return values["aggregate_RT"], ["R_total", "T_total"]
    identity = values["order_identity"]
    if channels is None:
        raise ValueError("order recovery requires frozen channels")
    positions = {tuple(value): index for index, value in enumerate(identity)}
    indices = [positions[tuple(value)] for value in channels]
    return values["order_total"][indices], [identity[index] for index in indices]


def recover_geometry(*, dataset: dict[str, Any], test_records: dict[str, dict[str, Any]],
                     angle_ids: list[str], truth: tuple[float, float]) -> dict[str, Any]:
    """Recover physical (dh,dw) for each declared contract/noise scenario."""

    results: dict[str, Any] = {"truth_delta_h_nm": float(truth[0]), "truth_delta_w_nm": float(truth[1]),
                               "contracts": {}}
    nominal_rows = {row["angle_id"]: row for row in dataset["angles"]}
    for contract in ("M0_aggregate_RT", "M1_order_total_robust", "M2_order_total_extended"):
        channels_by_angle = {
            angle: nominal_rows[angle]["contracts"][contract].get("channels")
            for angle in angle_ids
        }
        J_blocks: list[np.ndarray] = []
        d_blocks: list[np.ndarray] = []
        sig_blocks: dict[str, list[np.ndarray]] = {"N1": [], "N2": []}
        for angle in angle_ids:
            payload = nominal_rows[angle]["contracts"][contract]
            J_blocks.append(np.column_stack((np.asarray(payload["derivatives"]["h"], dtype=np.float64),
                                              np.asarray(payload["derivatives"]["w"], dtype=np.float64))))
            test, _ = _vector(test_records[angle], contract, channels_by_angle[angle])
            d_blocks.append(test - np.asarray(payload["nominal"], dtype=np.float64))
            for noise in ("N1", "N2"):
                sig_blocks[noise].append(np.asarray(payload["noise_sigma"][noise], dtype=np.float64))
        J = np.vstack(J_blocks); delta = np.concatenate(d_blocks)
        for noise in ("N1", "N2"):
            sigma = np.concatenate(sig_blocks[noise])
            weighted = J / sigma[:, None]
            rhs = weighted.T @ (delta / sigma)
            fisher = weighted.T @ weighted
            eig = np.linalg.eigvalsh(0.5 * (fisher + fisher.T))
            full_rank = bool(np.all(eig > 1.0e-14))
            if full_rank:
                estimate = np.linalg.solve(fisher, rhs)
                reconstruction = J @ estimate
                covariance = np.linalg.inv(fisher)
            else:
                estimate = np.asarray([np.nan, np.nan]); reconstruction = np.full_like(delta, np.nan); covariance = None
            errors = estimate - np.asarray(truth, dtype=np.float64)
            results["contracts"].setdefault(contract, {})[noise] = {
                "angle_ids": list(angle_ids), "rank": int(np.count_nonzero(eig > 1.0e-14)),
                "eigenvalues": eig.tolist(), "fisher_matrix": fisher.tolist(),
                "estimate_delta_h_nm": float(estimate[0]), "estimate_delta_w_nm": float(estimate[1]),
                "height_error_nm": float(errors[0]), "width_error_nm": float(errors[1]),
                "absolute_height_error_nm": float(abs(errors[0])), "absolute_width_error_nm": float(abs(errors[1])),
                "reconstruction_residual_l2": float(np.linalg.norm(reconstruction - delta)) if full_rank else None,
                "whitened_reconstruction_residual_l2": float(np.linalg.norm((reconstruction - delta) / sigma)) if full_rank else None,
                "covariance_scaled": covariance.tolist() if covariance is not None else None,
                "full_rank": full_rank,
                "gate": bool(full_rank and abs(errors[0]) <= 0.5 and abs(errors[1]) <= 0.1),
            }
    m1n1 = results["contracts"]["M1_order_total_robust"]["N1"]
    results["primary_gate"] = bool(m1n1["gate"])
    results["primary_contract"] = "M1_order_total_robust"
    results["primary_noise"] = "N1"
    results["forward_solver_sha"] = FORWARD_SOLVER_SHA
    results["model_id"] = MODEL_ID; results["solver_route_id"] = ROUTE_ID
    return results


def write_recovery_design(path: Path, *, angle_ids: list[str], ranking_sha256: str,
                          dataset_manifest_sha256: str) -> dict[str, Any]:
    payload = {
        "schema_version": "task005.off-centre-recovery-design.v1",
        "status": "frozen", "selected_angle_ids": angle_ids,
        "selected_angle_tuple_sha256": canonical_hash(angle_ids),
        "ranking_sha256": ranking_sha256, "dataset_manifest_sha256": dataset_manifest_sha256,
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "test_geometries": {
            "G1": {"height_nm": 118.75, "width_nm": 16.75},
            "G2": {"height_nm": 121.25, "width_nm": 17.25},
            "G3": {"height_nm": 118.75, "width_nm": 17.25},
        },
        "max_new_fem": 9, "nominal_reuse": "train112", "formal_inversion": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload

