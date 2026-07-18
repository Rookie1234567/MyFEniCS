from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import scipy.sparse as sp

from benchmarks.neural_pc.data_contract import load_operator
from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap
from src.solvers.local_slab_solver import ScipyCsrAction
from src.solvers.low_storage_audit_proxy import (
    LowStorageProxyCertificate,
    certificate_content_hash,
    procedural_count_sketch,
)


TINY = np.finfo(float).tiny
Q_VALUES = (64, 128, 256, 512, 1024, 2048)
SEED_BASES = (0x51A7, 0xC3D9)


def _scores(
    rhs: np.ndarray,
    correction: np.ndarray,
    model: FrozenLinearReducedMap,
    reduced_operator: np.ndarray,
    sketch_products: tuple[np.ndarray, ...],
    seeds: tuple[int, ...],
    q: int,
) -> np.ndarray:
    input_coordinates = rhs @ model.input_basis.conj()
    output_coordinates = correction @ model.output_basis.conj()
    reduced_residual = input_coordinates - output_coordinates @ reduced_operator.T
    components = [
        np.linalg.norm(reduced_residual, axis=1)
        / np.maximum(np.linalg.norm(input_coordinates, axis=1), TINY)
    ]
    for seed, product in zip(seeds, sketch_products, strict=True):
        sketched_rhs = procedural_count_sketch(rhs, q=q, seed=seed)
        residual = sketched_rhs - output_coordinates @ product.T
        components.append(
            np.linalg.norm(residual, axis=1)
            / np.maximum(np.linalg.norm(sketched_rhs, axis=1), TINY)
        )
    return np.stack(components, axis=1)


def _expanded_range(values: np.ndarray) -> tuple[float, float]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        raise ValueError("cannot calibrate an empty norm range")
    low = max(0.0, 0.5 * float(np.min(finite)))
    high = max(float(np.max(finite)) * 2.0, low + TINY)
    return low, high


def _strict_threshold(values: np.ndarray, harmful: np.ndarray, fallback: float) -> float:
    selected = np.asarray(values, dtype=np.float64)[harmful]
    if not selected.size:
        return float(fallback)
    return float(np.nextafter(float(np.min(selected)), -np.inf))


def _calibrate_slab(
    *,
    slab: int,
    dataset_root: Path,
    model_root: Path,
    ilu_root: Path,
    q: int,
    seed_count: int,
) -> tuple[dict[str, Any], LowStorageProxyCertificate]:
    directory = dataset_root / f"slab_{slab:03d}"
    operator = load_operator(directory)
    model = FrozenLinearReducedMap.load(
        model_root / f"slab_{slab:03d}",
        expected_operator_fingerprint=operator.fingerprint,
    )
    with np.load(directory / "samples.npz", allow_pickle=False) as payload:
        split = payload["split"].astype(str)
        if set(np.unique(split)) != {"train", "validation", "holdout"}:
            raise ValueError("unexpected Task005 split identities")
        rhs = np.asarray(payload["rhs"][split == "validation"], dtype=np.complex128)
    with np.load(
        ilu_root / f"slab_{slab:03d}" / "reference.npz",
        allow_pickle=False,
    ) as payload:
        ilu_rho = np.asarray(payload["rho"], dtype=np.float64)
        ilu_correction = np.asarray(payload["correction"], dtype=np.complex128)
    if rhs.shape[0] != 256 or ilu_correction.shape != rhs.shape:
        raise ValueError("Q0 requires 256 aligned V/ILU samples per slab")

    action = ScipyCsrAction(operator)
    learned_correction = model.predict_many(rhs)
    learned_residual = rhs - action.action_many(learned_correction)
    learned_rho = np.linalg.norm(learned_residual, axis=1) / np.maximum(
        np.linalg.norm(rhs, axis=1), TINY
    )
    harmful = (learned_rho >= 1.0) | (learned_rho > 1.05 * ilu_rho)

    reference_matrix = sp.csr_matrix(
        (operator.values, operator.indices, operator.indptr),
        shape=operator.shape,
        copy=False,
    )
    action_output_basis = np.asarray(
        reference_matrix @ model.output_basis, dtype=np.complex128
    )
    reduced_operator = model.input_basis.conj().T @ action_output_basis
    seeds = tuple(SEED_BASES[index] + 1009 * slab + 17 * q for index in range(seed_count))
    sketch_products = tuple(
        procedural_count_sketch(
            action_output_basis.T, q=q, seed=seed
        ).T
        for seed in seeds
    )
    learned_components = _scores(
        rhs,
        learned_correction,
        model,
        reduced_operator,
        sketch_products,
        seeds,
        q,
    )
    ilu_components = _scores(
        rhs,
        ilu_correction,
        model,
        reduced_operator,
        sketch_products,
        seeds,
        q,
    )
    combined_components = np.vstack((learned_components, ilu_components))
    combined_exact = np.concatenate((learned_rho, ilu_rho))
    scales = []
    for column in range(combined_components.shape[1]):
        component = combined_components[:, column]
        valid = (component > 1.0e-14) & np.isfinite(component)
        ratios = combined_exact[valid] / component[valid]
        scales.append(
            max(float(np.quantile(ratios, 0.995)), np.finfo(float).eps)
        )
    scale_array = np.asarray(scales, dtype=np.float64)
    learned_score = np.max(learned_components * scale_array[None, :], axis=1)
    ilu_score = np.max(ilu_components * scale_array[None, :], axis=1)
    score_ratio = learned_score / np.maximum(ilu_score, TINY)

    absolute_harmful = learned_rho >= 1.0
    absolute_threshold = _strict_threshold(
        learned_score, absolute_harmful, fallback=1.0
    )
    relative_harmful = learned_rho > 1.05 * ilu_rho
    ratio_threshold = _strict_threshold(
        score_ratio, relative_harmful, fallback=1.05
    )
    accepted = (learned_score <= absolute_threshold) & (
        score_ratio <= ratio_threshold
    )
    false_accept = accepted & harmful
    false_reject = (~accepted) & (~harmful)
    nonharmful_count = int(np.count_nonzero(~harmful))
    nonharmful_accept_fraction = float(
        np.count_nonzero(accepted & ~harmful) / max(nonharmful_count, 1)
    )

    input_norm = np.linalg.norm(rhs, axis=1)
    output_norm = np.linalg.norm(learned_correction, axis=1)
    ratio = output_norm / np.maximum(input_norm, TINY)
    certificate = LowStorageProxyCertificate(
        slab_id=slab,
        operator_fingerprint=operator.fingerprint,
        checkpoint_sha256=model.checkpoint_sha256,
        reduced_operator=reduced_operator,
        sketch_products=sketch_products,
        sketch_q=q,
        sketch_seeds=seeds,
        score_scales=tuple(float(value) for value in scales),
        acceptance_threshold=absolute_threshold,
        nondegradation_ratio_threshold=ratio_threshold,
        input_norm_range=_expanded_range(input_norm),
        output_norm_range=_expanded_range(output_norm),
        correction_input_ratio_range=_expanded_range(ratio),
    )
    row = {
        "slab": slab,
        "q": q,
        "seed_count": seed_count,
        "q0_samples": int(rhs.shape[0]),
        "harmful_count": int(np.count_nonzero(harmful)),
        "false_accept_count": int(np.count_nonzero(false_accept)),
        "false_reject_count": int(np.count_nonzero(false_reject)),
        "nonharmful_accept_fraction": nonharmful_accept_fraction,
        "overall_accept_fraction": float(np.mean(accepted)),
        "absolute_threshold": absolute_threshold,
        "ratio_threshold": ratio_threshold,
        "score_scales": scales,
        "proxy_storage_bytes": certificate.storage_bytes,
        "certificate_hash": certificate_content_hash(certificate),
        "learned_rho_median": float(np.median(learned_rho)),
        "learned_rho_p95": float(np.quantile(learned_rho, 0.95)),
        "ilu_rho_median": float(np.median(ilu_rho)),
        "ilu_rho_p95": float(np.quantile(ilu_rho, 0.95)),
    }
    return row, certificate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--ilu-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--slabs", default="0,5,9,15")
    parser.add_argument("--phase", choices=("Q0",), required=True)
    args = parser.parse_args()
    slabs = tuple(int(value) for value in args.slabs.split(","))
    started = time.perf_counter()
    family_rows = []
    family_certificates: dict[tuple[int, int], dict[int, LowStorageProxyCertificate]] = {}
    for q in Q_VALUES:
        for seed_count in (1, 2):
            rows = []
            certificates = {}
            for slab in slabs:
                row, certificate = _calibrate_slab(
                    slab=slab,
                    dataset_root=args.dataset_root,
                    model_root=args.model_root,
                    ilu_root=args.ilu_root,
                    q=q,
                    seed_count=seed_count,
                )
                rows.append(row)
                certificates[slab] = certificate
            false_accepts = sum(row["false_accept_count"] for row in rows)
            false_rejects = sum(row["false_reject_count"] for row in rows)
            nonharmful = sum(
                row["q0_samples"] - row["harmful_count"] for row in rows
            )
            acceptance = 1.0 - false_rejects / max(nonharmful, 1)
            maximum_slab_false_reject = max(
                1.0 - row["nonharmful_accept_fraction"] for row in rows
            )
            family = {
                "q": q,
                "seed_count": seed_count,
                "false_accept_count": false_accepts,
                "false_reject_count": false_rejects,
                "nonharmful_accept_fraction": acceptance,
                "maximum_slab_false_reject_fraction": (
                    maximum_slab_false_reject
                ),
                "proxy_storage_bytes_R4": sum(
                    row["proxy_storage_bytes"] for row in rows
                ),
                "usable": bool(
                    false_accepts == 0
                    and acceptance >= 0.99
                    and maximum_slab_false_reject <= 0.10
                ),
                "rows": rows,
            }
            family_rows.append(family)
            family_certificates[(q, seed_count)] = certificates

    usable = [
        family
        for family in family_rows
        if family["usable"] and family["seed_count"] == 2
    ]
    selected = (
        min(
            usable,
            key=lambda family: (
                family["proxy_storage_bytes_R4"],
                -family["nonharmful_accept_fraction"],
                family["q"],
                family["seed_count"],
            ),
        )
        if usable
        else None
    )
    if selected is not None:
        certificate_root = args.output_root / "locked_certificates"
        for slab, certificate in family_certificates[
            (selected["q"], selected["seed_count"])
        ].items():
            certificate.save(certificate_root / f"slab_{slab:03d}")
    summary = {
        "schema": "myfenics.task006.proxy_q0_calibration.v1",
        "phase": args.phase,
        "corpora_accessed": ["Q0_Task005_V_validation"],
        "forbidden_corpora_accessed": [],
        "thresholds_locked_before_Q1_Q5": selected is not None,
        "slabs": list(slabs),
        "family_count": len(family_rows),
        "selected_family": (
            None
            if selected is None
            else {
                key: value
                for key, value in selected.items()
                if key != "rows"
            }
        ),
        "families": family_rows,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "calibration.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if selected is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
