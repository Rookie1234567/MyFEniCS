#!/usr/bin/env python3
"""Compare saved Task40 B0 Ny4/Ny8 modal arrays without rerunning a field solve."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/task40extra_nonseparable_0p7nm"
ARTIFACTS = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl"
NY4_SOLVER = RESULTS / (
    "task40extra_0p7nm_b0_p6_reference_v15__full3d_iterative__mpi1__Mna/"
    "20261007T103141.187971Z"
)
NY4_RECOVERED = RESULTS / (
    "task40extra_0p7nm_b0_p6_reference_v15__full3d_iterative__mpi1__Mna/"
    "20261007T112650.870129Z"
)
NY8_ROOT = RESULTS / (
    "task40extra_0p7nm_b0_p6_reference_v18_ny8__full3d_iterative__mpi1__Mna/"
    "20261008T201318.267171Z"
)
PREVIOUS_OUTPUT = ARTIFACTS / "v18_ny4_ny8_saved_field_common_subcells.json"
DEFAULT_OUTPUT = ARTIFACTS / "v18_ny4_ny8_saved_field_modes_supplement_v4.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_modes(run_root: Path) -> tuple[list[tuple[str, int, int, str]], np.ndarray, np.ndarray, str, Path]:
    archive = run_root / "numerical_output/dtn_port_modal_amplitudes_3d.npz"
    with np.load(archive, allow_pickle=False) as arrays:
        keys = list(zip(
            arrays["side"].astype(str).tolist(),
            arrays["m"].astype(int).tolist(),
            arrays["n"].astype(int).tolist(),
            arrays["polarization"].astype(str).tolist(),
            strict=True,
        ))
        outgoing = np.asarray(
            arrays["physical_boundary_outgoing_amplitude"], dtype=np.complex128
        ).copy()
        incident = np.asarray(
            arrays["physical_boundary_incident_amplitude"], dtype=np.complex128
        ).copy()
        gauge = str(arrays["dtn_phase_gauge"].item())
    if (
        len(keys) != 532
        or len(set(keys)) != len(keys)
        or outgoing.shape != (len(keys),)
        or incident.shape != (len(keys),)
        or not np.isfinite(outgoing).all()
        or not np.isfinite(incident).all()
    ):
        raise ValueError(f"{run_root.name}: invalid saved 532-mode arrays")
    return keys, outgoing, incident, gauge, archive


def compare_saved_modal_arrays(output_path: Path) -> int:
    started = time.monotonic()
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite saved comparison: {output_path}")
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified WSL activation is required")
    if sys.platform != "linux" or MPI.COMM_WORLD.size != 1:
        raise RuntimeError("comparison requires qualified Linux serial execution")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("comparison requires complex128 PETSc")

    manifest4 = read_json(NY4_SOLVER / "run_manifest.json")
    manifest4r = read_json(NY4_RECOVERED / "run_manifest.json")
    recovery4 = read_json(NY4_RECOVERED / "postprocess_recovery_record.json")
    packet4_path = NY4_RECOVERED / "v15_b0_official_output_recovered.json"
    packet4 = read_json(packet4_path)
    manifest8 = read_json(NY8_ROOT / "run_manifest.json")
    prior = read_json(PREVIOUS_OUTPUT)
    prior_identity = prior.get("identity", {})
    if (
        prior_identity.get("physical_sections_identical") is not True
        or prior_identity.get("derived_physical_values_identical") is not True
        or prior_identity.get("complex_diffraction_mode_identity_and_order_match") is not True
    ):
        raise ValueError("prior comparison did not establish matching B0 physics/modes")
    if (
        manifest4["input_sha256"] != manifest4r["input_sha256"]
        or manifest4["physical_model_sha256"] != manifest4r["physical_model_sha256"]
        or packet4["identity"]["saved_field_source_sha"] != manifest4["source_sha"]
        or recovery4["original_run_classification_preserved"] != "WORKER_FAILED"
        or recovery4.get("official_result") is not True
        or recovery4.get("status") != "PASS"
    ):
        raise ValueError("Ny4 saved output does not preserve original/recovery identity")
    if manifest8["source_sha"] != "3b9457e57ceb15f21306a35baac07f42036840b1":
        raise ValueError("Ny8 source SHA differs from the frozen saved-field run")

    keys4, outgoing4, incident4, gauge4, archive4 = read_modes(NY4_RECOVERED)
    keys8, outgoing8, incident8, gauge8, archive8 = read_modes(NY8_ROOT)
    if keys4 != keys8 or gauge4 != gauge8:
        raise ValueError("Ny4/Ny8 ordered channel identities or phase gauges differ")

    mode_digest = hashlib.sha256(
        json.dumps(keys4, separators=(",", ":")).encode()
    ).hexdigest()
    incident_delta = incident8 - incident4
    incident_norm4 = float(np.linalg.norm(incident4))
    incident_abs_l2 = float(np.linalg.norm(incident_delta))
    incident_max = float(np.max(np.abs(incident_delta)))
    incident_max_index = int(np.argmax(np.abs(incident_delta)))
    incident_equal = bool(np.array_equal(incident4, incident8))
    incident_comparison = {
        "classification": "measured_saved_physical_boundary_incident_amplitude_array_comparison",
        "channel_count_each": len(keys4),
        "bitwise_equal": incident_equal,
        "maximum_absolute_difference": incident_max,
        "maximum_difference_channel": list(keys4[incident_max_index]) if incident_max else None,
        "all_channels_exactly_equal": incident_equal,
        "absolute_difference_l2": incident_abs_l2,
        "relative_l2_to_ny4_incident": (
            float(incident_abs_l2 / incident_norm4) if incident_norm4 > 0.0 else None
        ),
        "normalization_identity": (
            "Ny4 physical_boundary_incident_amplitude vector L2 norm; "
            "identity check only, not a precision gate"
        ),
        "normalizer_l2": incident_norm4,
        "ordered_channel_identity_sha256": mode_digest,
    }

    delta = outgoing8 - outgoing4
    norm4, norm8 = float(np.linalg.norm(outgoing4)), float(np.linalg.norm(outgoing8))
    shared_scale = max(norm4, norm8, np.finfo(float).tiny)
    shared_normalized = np.abs(delta) / shared_scale
    has_ny4_denominator = np.abs(outgoing4) > 0.0
    rows = []
    for i, key in enumerate(keys4):
        ratio = complex(delta[i] / outgoing4[i]) if has_ny4_denominator[i] else None
        rows.append({
            "side": key[0], "m": key[1], "n": key[2], "polarization": key[3],
            "Ny4_outgoing_physical_boundary": [float(outgoing4[i].real), float(outgoing4[i].imag)],
            "Ny8_outgoing_physical_boundary": [float(outgoing8[i].real), float(outgoing8[i].imag)],
            "Ny4_outgoing_magnitude": float(abs(outgoing4[i])),
            "Ny8_outgoing_magnitude": float(abs(outgoing8[i])),
            "absolute_difference_relative_to_incident_vector_l2": float(abs(delta[i]) / incident_norm4) if incident_norm4 > 0.0 else None,
            "absolute_difference": float(abs(delta[i])),
            "difference_scaled_by_larger_outgoing_vector_l2": float(shared_normalized[i]),
            "complex_relative_difference_to_ny4": (
                [float(ratio.real), float(ratio.imag)] if ratio is not None else None
            ),
            "relative_difference_magnitude_to_ny4": float(abs(ratio)) if ratio is not None else None,
            "ny4_normalized_status": (
                "MEASURED_DIAGNOSTIC" if ratio is not None
                else "NULL_ZERO_NY4_DENOMINATOR_NOT_JUDGED"
            ),
        })
    nonzero = np.flatnonzero(has_ny4_denominator)
    max_shared = int(np.argmax(shared_normalized))
    max_ny4 = (
        int(nonzero[np.argmax(np.abs(delta[nonzero] / outgoing4[nonzero]))])
        if len(nonzero) else None
    )
    significant_mode_gate = {
        "status": "NOT_EVALUATED_NO_FROZEN_B0_SIGNIFICANT_MODE_SET",
        "contractual_engineering_limit": 0.01,
        "frozen_b0_mode_keys": None,
        "frozen_b0_selection_rule": None,
        "evaluated_mode_count": 0,
        "per_channel_ny4_normalized_values_are_diagnostic_only": True,
        "reason": (
            "The B0 task/review does not freeze a B0 key list or selection rule. "
            "The V17 11-key set belongs to Gx560 and is not transferred; no threshold "
            "is selected after observing this result."
        ),
    }
    result = {
        "schema": "task40extra.review_v18.ny4_ny8_saved_mode_supplement.v1",
        "status": "SAVED_ARRAY_DIAGNOSTIC_COMPLETE",
        "classification": "small_model_y_refinement_observation_not_continuum_convergence",
        "execution": {
            "mode": "saved_modal_npz_readback_only",
            "pde_started": False,
            "field_integral_recomputed": False,
            "physical_operator_built": False,
            "factor_started": False,
            "ksp_started": False,
            "activation": os.environ["_MYFENICS_WSL_QUALIFIED_ACTIVATION"],
            "python": sys.executable,
            "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
            "petsc_int_type": np.dtype(PETSc.IntType).name,
            "mpi_size": int(MPI.COMM_WORLD.size),
            "duration_seconds": time.monotonic() - started,
            "runner_path": str(Path(__file__).resolve().relative_to(ROOT)),
            "runner_sha256": sha256(Path(__file__).resolve()),
        },
        "prior_comparison": {
            "path": str(PREVIOUS_OUTPUT.relative_to(ROOT)),
            "sha256": sha256(PREVIOUS_OUTPUT),
            "preserved_without_overwrite": True,
        },
        "identity": {
            "Ny4_original_run_id": manifest4["run_id"],
            "Ny4_original_source_sha": manifest4["source_sha"],
            "Ny4_input_sha256": manifest4["input_sha256"],
            "Ny4_physical_model_sha256": manifest4["physical_model_sha256"],
            "Ny4_original_classification_preserved": "WORKER_FAILED",
            "Ny4_recovery_source_sha": manifest4r["source_sha"],
            "Ny4_recovery_status": recovery4["status"],
            "Ny4_recovered_packet_sha256": sha256(packet4_path),
            "Ny4_saved_field_source_sha": packet4["identity"]["saved_field_source_sha"],
            "Ny8_run_id": manifest8["run_id"],
            "Ny8_source_sha": manifest8["source_sha"],
            "Ny8_input_sha256": manifest8["input_sha256"],
            "Ny8_physical_model_sha256": manifest8["physical_model_sha256"],
            "input_sha_equal": manifest4["input_sha256"] == manifest8["input_sha256"],
            "input_sha_difference_semantics": "expected because the y discretization differs",
            "physical_sections_identical_from_preserved_comparison": True,
            "derived_physical_values_identical_from_preserved_comparison": True,
            "ordered_mode_count": len(keys4),
        },
        "complete_complex_diffraction": {
            "channel_count_each": len(keys4),
            "ordered_channel_identity_sha256": mode_digest,
            "phase_gauge": gauge4,
            "global_phase_fit_applied": False,
            "input_archives": {
                "Ny4": {"path": str(archive4.relative_to(ROOT)), "sha256": sha256(archive4)},
                "Ny8": {"path": str(archive8.relative_to(ROOT)), "sha256": sha256(archive8)},
            },
            "physical_boundary_incident_amplitude": incident_comparison,
            "legacy_vector_scale_diagnostic": {
                "normalization": (
                    "absolute channel difference divided by the larger complete outgoing "
                    "vector L2 norm; diagnostic only, not the significant-mode gate"
                ),
                "relative_l2_to_ny4_outgoing": float(
                    np.linalg.norm(delta) / max(norm4, np.finfo(float).tiny)
                ),
                "relative_l2_to_ny8_outgoing": float(
                    np.linalg.norm(delta) / max(norm8, np.finfo(float).tiny)
                ),
                "maximum_channel_scaled_difference": float(shared_normalized[max_shared]),
                "maximum_channel": list(keys4[max_shared]),
            },
            "per_channel_ny4_amplitude_relative_diagnostic": {
                "normalization_identity": (
                    "(Ny8 - Ny4) complex outgoing amplitude divided by that channel's "
                    "Ny4 physical_boundary_outgoing_amplitude"
                ),
                "zero_denominator_semantics": (
                    "null; retain absolute difference and do not judge a relative gate"
                ),
                "nonzero_ny4_denominator_count": int(np.count_nonzero(has_ny4_denominator)),
                "zero_ny4_denominator_count": int(len(keys4) - np.count_nonzero(has_ny4_denominator)),
                "maximum_relative_magnitude_over_nonzero_denominators": (
                    float(abs(delta[max_ny4] / outgoing4[max_ny4]))
                    if max_ny4 is not None else None
                ),
                "maximum_relative_magnitude_channel": list(keys4[max_ny4]) if max_ny4 is not None else None,
                "significant_mode_gate": significant_mode_gate,
            },
            "channels": rows,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "status": result["status"],
        "output": str(output_path),
        "channel_count": len(keys4),
        "incident_bitwise_equal": incident_equal,
        "significant_mode_gate": significant_mode_gate["status"],
    }, ensure_ascii=False), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--modes-only",
        action="store_true",
        help="accepted for compatibility; this runner only reads saved modal arrays",
    )
    args = parser.parse_args(argv)
    return compare_saved_modal_arrays(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
