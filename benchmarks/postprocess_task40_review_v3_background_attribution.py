"""Bounded Review V3 dual-background analysis of four saved Task40 fields."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import resource
import time
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
    RunInput,
    _git_facts,
    _load_run,
    _physical_signature,
    _qualified_environment,
    _read_json,
    _sha256,
    _write_json,
)
from src.postprocessing.task40_saved_field_h_comparison import (
    compare_paired_background_attribution,
    restore_p6_total_field,
)


DEFAULT_G0_M0 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_iterative_review_v1__full3d_iterative__mpi1__Mna/"
    "20260930T102148.356966Z"
)
DEFAULT_G1_M0 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g1_iterative_review_v1__full3d_iterative__mpi1__Mna/"
    "20260930T105500.302324Z"
)
DEFAULT_G0_M2 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_manual_m2_f3_v1__full3d_iterative__mpi1__Mna/"
    "20261001T154625.204407Z"
)
DEFAULT_G1_M2 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1__full3d_iterative__mpi1__Mna/"
    "20261002T000242.608221Z"
)
DEFAULT_OUTPUT = Path(
    "docs/task40extra_0p7nm_engineering/outcomes/records/"
    "background_attribution_v1.json"
)


def _sample_coordinates(run: RunInput) -> tuple[np.ndarray, dict[str, str]]:
    arrays = run.samples
    x = np.asarray(arrays["x_nm"], dtype=np.float64)
    y = np.asarray(arrays["y_nm"], dtype=np.float64)
    z = np.asarray(arrays["z_nm"], dtype=np.float64)
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    coordinates = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    if coordinates.shape != (4000, 3) or not np.isfinite(coordinates).all():
        raise ValueError(f"{run.label}: expected exactly 4000 finite xyz-nm sample coordinates")
    hashes = {
        name: hashlib.sha256(np.ascontiguousarray(arrays[name]).tobytes()).hexdigest()
        for name in ("x_nm", "y_nm", "z_nm")
    }
    return coordinates, hashes


def _mode_file(run: RunInput) -> Path:
    directory = Path(run.manifest["numerical_output_directory"])
    if not directory.is_absolute():
        directory = (run.root / directory).resolve()
    return directory / "dtn_port_diffraction_orders_3d.json"


def _mode_values(run: RunInput) -> tuple[dict[str, Any], dict[str, complex]]:
    path = _mode_file(run)
    payload = _read_json(path)
    values: dict[str, complex] = {}
    for side, m, n, pol in (("top", 0, 0, "s"), ("bottom", -1, 0, "s")):
        matches = [
            item
            for item in payload["orders"]
            if item["side"] == side
            and int(item["m"]) == m
            and int(item["n"]) == n
            and item["polarization"] == pol
        ]
        if len(matches) != 1:
            raise ValueError(f"{run.label}: expected one mode {(side, m, n, pol)} in saved DtN orders")
        pair = matches[0]["outgoing_amplitude_at_boundary"]
        values[f"{side}({m},{n},{pol})"] = complex(float(pair[0]), float(pair[1]))
    return {"path": str(path), "sha256": _sha256(path)}, values


def _mode_pair(first: dict[str, complex], second: dict[str, complex]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in first:
        a0, a1 = first[key], second[key]
        delta_phase = float(np.angle(a1 * np.conjugate(a0)))
        result[key] = {
            "G0_complex": [float(a0.real), float(a0.imag)],
            "G1_complex": [float(a1.real), float(a1.imag)],
            "G0_magnitude": float(abs(a0)),
            "G1_magnitude": float(abs(a1)),
            "magnitude_relative_change_to_G0": float((abs(a1) - abs(a0)) / max(abs(a0), np.finfo(float).tiny)),
            "phase_change_G1_minus_G0_rad": delta_phase,
            "complex_relative_difference_to_G0": float(abs(a1 - a0) / max(abs(a0), np.finfo(float).tiny)),
            "absolute_complex_difference": float(abs(a1 - a0)),
            "denominator": "G0 outgoing complex amplitude",
        }
    return result


def _run_identity(run: RunInput, mode_facts: dict[str, Any]) -> dict[str, Any]:
    identity = run.packet.get("identity", {})
    ordered_mode_sha = identity.get("ordered_mode_sha256")
    if not ordered_mode_sha:
        raise ValueError(f"{run.label}: packet.identity.ordered_mode_sha256 is missing")
    return {
        "label": run.label,
        "run_id": run.manifest["run_id"],
        "source_sha": run.manifest["source_sha"],
        "input_sha256": run.manifest["input_sha256"],
        "physical_model_sha256": run.manifest["physical_model_sha256"],
        "native_ordered_mode_sha256": ordered_mode_sha,
        "native_ordered_mode_sha256_source": "packet.identity.ordered_mode_sha256",
        "retained_vector_sha256": run.vector_sha256,
        "retained_vector_archive_sha256": run.vector_archive_sha256,
        "retained_vector_archive": str(run.vector_archive),
        "reference_sample_archive_sha256": run.sample_archive_sha256,
        "reference_sample_archive": str(run.sample_archive),
        "reference_sample_shape_z_y_x_component": run.sample_metadata[
            "array_shape_z_y_x_component"
        ],
        "reference_sample_interface_trace_sides": run.sample_metadata.get(
            "interface_trace_sides"
        ),
        "sample_coordinate_array_sha256": mode_facts["sample_coordinate_sha256"],
        "mode_file": mode_facts["mode_file"],
    }


def _analyze_pair(label: str, first_root: Path, second_root: Path) -> dict[str, Any]:
    print(f"Loading saved {label} pair", flush=True)
    first = _load_run(f"{label}_G0", first_root)
    second = _load_run(f"{label}_G1", second_root)
    sig0 = _physical_signature(first.resolved, first.cfg)
    sig1 = _physical_signature(second.resolved, second.cfg)
    if sig0 != sig1:
        raise ValueError(f"{label}: G0/G1 physical signatures differ")
    mode_identity0 = first.packet.get("identity", {}).get("ordered_mode_sha256")
    mode_identity1 = second.packet.get("identity", {}).get("ordered_mode_sha256")
    if not mode_identity0 or mode_identity0 != mode_identity1:
        raise ValueError(f"{label}: G0/G1 native ordered mode identities differ or are missing")

    points0, hashes0 = _sample_coordinates(first)
    points1, hashes1 = _sample_coordinates(second)
    if not np.array_equal(points0, points1) or hashes0 != hashes1:
        raise ValueError(f"{label}: saved G0/G1 4000-point coordinates differ")

    mode_facts0, mode_values0 = _mode_values(first)
    mode_facts1, mode_values1 = _mode_values(second)
    t0 = time.monotonic()
    field0 = restore_p6_total_field(f"{label}_G0", first.cfg, first.vector)
    field1 = restore_p6_total_field(f"{label}_G1", second.cfg, second.vector)
    attribution = compare_paired_background_attribution(
        field0, field1, points0, first.sample_metadata
    )
    elapsed = time.monotonic() - t0
    print(f"Finished saved {label} pair in {elapsed:.1f} s", flush=True)
    pair = {
        "status": "derived_offline",
        "physical_signature": sig0,
        "G0": _run_identity(
            first,
            {"sample_coordinate_sha256": hashes0, "mode_file": mode_facts0},
        ),
        "G1": _run_identity(
            second,
            {"sample_coordinate_sha256": hashes1, "mode_file": mode_facts1},
        ),
        "fixed_sample_coordinate_count": int(len(points0)),
        "mode_amplitudes": _mode_pair(mode_values0, mode_values1),
        "attribution": attribution,
        "elapsed_s": float(elapsed),
    }
    del field0, field1, first, second
    gc.collect()
    return pair


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--g0-m0", type=Path, default=DEFAULT_G0_M0)
    parser.add_argument("--g1-m0", type=Path, default=DEFAULT_G1_M0)
    parser.add_argument("--g0-m2", type=Path, default=DEFAULT_G0_M2)
    parser.add_argument("--g1-m2", type=Path, default=DEFAULT_G1_M2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    environment = _qualified_environment()
    git = _git_facts(root)
    if git["status"] != []:
        raise RuntimeError("analysis code and inputs must be run from a clean tracked source SHA")

    pairs: dict[str, Any] = {}

    def save_progress(status: str) -> None:
        payload = {
            "schema": "task40extra.review-v3-background-attribution.v1",
            "status": status,
            "analysis_source_sha": git["head"],
            "analysis_git_status_at_start": git["status"],
            "analysis_entry_sha256": _sha256(Path(__file__).resolve()),
            "analysis_core_sha256": _sha256(
                root / "src/postprocessing/task40_saved_field_h_comparison.py"
            ),
            "environment": environment,
            "execution": {
                "wall_s": float(time.monotonic() - START_TIME),
                "process_ru_maxrss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
                "resource_scope": "single offline process maximum RSS from getrusage; no PDE/operator/factor/KSP",
                "pde_or_solve": False,
            },
            "legacy_generator": {
                "status": "generator_unknown",
                "basis": "Review V3 limited lookup found commit 4e7d6074 adding result JSON only; no associated generator source was bound",
            },
            "pairs": pairs,
            "gate_interpretation": {
                "official_gate_changed": False,
                "fresnel_background_remains_official_P1_P4_definition": True,
                "plane_wave_substrate_extension_is_legacy_metric_reproduction_only": True,
                "representation_attribution_is_explanatory_only": True,
            },
        }
        output = args.output if args.output.is_absolute() else root / args.output
        _write_json(output, payload)
        print(f"Saved {status}: {output}", flush=True)

    try:
        pairs["M0"] = _analyze_pair("M0", root / args.g0_m0, root / args.g1_m0)
    except NotImplementedError as exc:
        pairs["M0"] = {"status": "not_run", "reason": str(exc)}
    save_progress("M0_complete_M2_pending")
    try:
        pairs["M2"] = _analyze_pair("M2", root / args.g0_m2, root / args.g1_m2)
    except NotImplementedError as exc:
        pairs["M2"] = {"status": "not_run", "reason": str(exc)}
    final_status = (
        "complete_derived_offline"
        if all(pair.get("status") == "derived_offline" for pair in pairs.values())
        else "partial_with_not_run"
    )
    save_progress(final_status)
    return 0


START_TIME = time.monotonic()


if __name__ == "__main__":
    raise SystemExit(main())
