"""One bounded W1 q30/q60 boundary and local-correction probe.

This runner consumes the frozen AUTO mode manifest without invoking its
generator.  The 272x4 surface partition is derived from the review's cell
count candidate and exact periodic/material planes; it is not an assembled
or qualified original-size volume mesh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.solvers.directional_boundary import (
    BoundaryLayout,
    DirectionalBoundaryAction,
    FacetPolynomial,
    zvalue,
)
from src.solvers.task40_w1_local_probe import stream_boundary_correction
from src.solvers.task40_w1_local_probe import direct_single_face_projection
from src.solvers.task40_w1_moment_reference import (
    AnalyticMomentBoundaryReference,
    legendre_exponential_moment_table,
    quadrature_legendre_exponential_moments,
    segmented_legendre_exponential_moments,
)
from src.common.config_3d import SimulationConfig3D


MODE_PATH = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json"
W1_ROOT = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w1_wsl"
V10_LOCAL_W10_ROOT = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl"
SAVED_W1_RAW = W1_ROOT / "w1_probe_c354afa_retry1_20261004T1654Z/probe/w1_boundary_probe_arrays.npz"
SAVED_W9_REFERENCE = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/w1_reference_completion_raw_v2.npz"
SAVED_W1_RAW_SHA256 = "a475bba1618abd74981622a66e127b2fd88b43f52a2339f5087115ed9b1a82f8"
SAVED_W9_REFERENCE_SHA256 = "d83151f8db3b186e9dc5366c56b052243b01d690fe58a83d66208e7bf37b4289"
SAVED_Q60_APPLY_SHA256 = "af07712b8525df426f223d3a3669c2861d4861657e71e088bf4077660566a7de"
SAVED_Q60_COMPONENTS_SHA256 = "4975bae7c26ccc8806b14dc59a271af1a586e9407cdc9dd1229aa0105c58e208"
EXPECTED_MODE_SHA256 = "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d"
EXPECTED_KEYS_SHA256 = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"
EXPECTED_PHYSICAL_IDENTITY_SHA256 = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"
EXPECTED_INVENTORY_IDENTITY_SHA256 = "39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12"
PERIOD_X_NM = 50.0
PERIOD_Y_NM = 25.0
BOUNDARY_Z_NM = {"bottom": -10.0, "top": 130.0}
SILICON_INDEX = 0.9998851703688496 + 4.3236152269189515e-06j


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _numeric_hashes(arrays: dict[str, np.ndarray]) -> dict[str, str]:
    return {
        key: _sha256_bytes(np.ascontiguousarray(value).tobytes(order="C"))
        for key, value in sorted(arrays.items())
    }


def _atomic_npz(path: Path, arrays: dict[str, np.ndarray]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    with np.load(path, allow_pickle=False) as reopened:
        copied = {key: reopened[key] for key in reopened.files}
    return {
        "path": str(path.relative_to(ROOT)),
        "file_sha256": _file_sha256(path),
        "file_bytes": path.stat().st_size,
        "member_numeric_sha256": _numeric_hashes(copied),
        "member_count": len(copied),
        "reopened_after_fsync": True,
    }


def _source_file_hashes() -> dict[str, str]:
    paths = (
        ROOT / "src/solvers/directional_boundary.py",
        ROOT / "src/solvers/native_boundary_adapter.py",
        ROOT / "src/solvers/task40_w1_local_probe.py",
        ROOT / "src/solvers/task40_w1_moment_reference.py",
        ROOT / "benchmarks/run_task40_w1_boundary_probe.py",
        ROOT / "benchmarks/check_task40_w1_boundary_probe.py",
        ROOT / "src/test/test_task40_w1_boundary_adapter.py",
    )
    return {str(path.relative_to(ROOT)): _file_sha256(path) for path in paths if path.is_file()}


def _load_modes(path: Path) -> tuple[list[dict], dict]:
    digest = _file_sha256(path)
    if digest != EXPECTED_MODE_SHA256:
        raise ValueError(f"frozen mode file SHA mismatch: {digest}")
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("modes")
    if not isinstance(rows, list) or len(rows) != 32060:
        raise ValueError("frozen ordered AUTO mode inventory must contain 32060 rows")
    keys = [[r["side"], r["m"], r["n"], r["polarization"]] for r in rows]
    key_sha = _sha256_bytes(
        json.dumps(keys, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    if key_sha != EXPECTED_KEYS_SHA256:
        raise ValueError(f"frozen ordered mode keys SHA mismatch: {key_sha}")
    sides = {s: sum(r["side"] == s for r in rows) for s in ("top", "bottom")}
    polarizations = {p: sum(r["polarization"] == p for r in rows) for p in ("s", "p")}
    if sides != {"top": 16030, "bottom": 16030} or polarizations != {"s": 16030, "p": 16030}:
        raise ValueError("frozen side/polarization coverage differs")
    ledger = json.loads((ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/target_ledger.json").read_text())
    if (
        ledger.get("target_mode_physical_identity_sha256") != EXPECTED_PHYSICAL_IDENTITY_SHA256
        or ledger.get("original_size_ordered_mode_inventory_identity_sha256")
        != EXPECTED_INVENTORY_IDENTITY_SHA256
    ):
        raise ValueError("frozen target physical or ordered inventory identity digest differs")
    modes = []
    for row in rows:
        modes.append({
            "side": row["side"],
            "k_vector": row["k_vector"],
            "e_vector": row["e_vector"],
            "traction_vector": row["traction_vector"],
            "reference_plane_nm": BOUNDARY_Z_NM[row["side"]],
            "projection_denominator": row["projection_denominator"],
            "mode_index": row["mode_index"],
            "m": row["m"],
            "n": row["n"],
            "polarization": row["polarization"],
        })
    return modes, {
        "mode_manifest_path": str(path.relative_to(ROOT)),
        "mode_manifest_bytes": path.stat().st_size,
        "mode_manifest_sha256": digest,
        "ordered_key_count": len(keys),
        "ordered_key_sha256": key_sha,
        "target_physical_inventory_identity_sha256": EXPECTED_PHYSICAL_IDENTITY_SHA256,
        "side_counts": sides,
        "polarization_counts": polarizations,
    }


def _proportional_axis(bounds: list[float], intervals: int) -> np.ndarray:
    lengths = np.diff(np.asarray(bounds, dtype=np.float64))
    quota = intervals * lengths / lengths.sum()
    counts = np.floor(quota).astype(int)
    remainder = intervals - int(counts.sum())
    order = sorted(range(len(counts)), key=lambda i: (-(quota[i] - counts[i]), i))
    for i in order[:remainder]:
        counts[i] += 1
    values = [float(bounds[0])]
    for i, count in enumerate(counts):
        values.extend(np.linspace(bounds[i], bounds[i + 1], int(count) + 1)[1:].tolist())
    result = np.asarray(values, dtype=np.float64)
    if len(result) != intervals + 1 or np.any(np.diff(result) <= 0):
        raise ValueError("derived candidate surface axes are not a complete partition")
    return result


def _floquet_phases(modes: list[dict]) -> tuple[complex, complex, dict]:
    estimates = [[], []]
    for row in modes:
        k = [zvalue(v) for v in row["k_vector"]]
        estimates[0].append(k[0] - 2 * math.pi * row["m"] / PERIOD_X_NM)
        estimates[1].append(k[1] - 2 * math.pi * row["n"] / PERIOD_Y_NM)
    references = [estimates[i][0] for i in range(2)]
    spreads = [max(abs(v - references[i]) for v in estimates[i]) for i in range(2)]
    scales = [max(1.0, max(abs(v) for v in values)) for values in estimates]
    relative_spreads = [spreads[i] / scales[i] for i in range(2)]
    if max(relative_spreads) > 2e-11:
        raise ValueError(f"mode wavenumbers do not share a consistent Bloch vector: {relative_spreads}")
    phases = tuple(complex(np.exp(1j * references[i] * (PERIOD_X_NM if i == 0 else PERIOD_Y_NM))) for i in range(2))
    return phases[0], phases[1], {
        "bloch_kx_nm_inverse": [references[0].real, references[0].imag],
        "bloch_ky_nm_inverse": [references[1].real, references[1].imag],
        "relative_consistency_spread": relative_spreads,
        "floquet_phases": [[p.real, p.imag] for p in phases],
    }


def _direct_single_face_projection(layout, mode: dict, trace: np.ndarray, q: int, i: int, j: int) -> np.ndarray:
    return direct_single_face_projection(layout, mode, trace, q, i, j)


def run(output: Path, mode_path: Path = MODE_PATH) -> dict:
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    arrays_path = output / "w1_boundary_probe_arrays.npz"
    progress_path = output / "w1_boundary_probe_progress.json"
    base_arrays: dict[str, np.ndarray] = {}
    local_arrays: dict[str, np.ndarray] = {}
    local_correction_cases: list[dict] = []
    raw_info: dict | None = None

    def checkpoint(stage: str, inventory: dict, boundary: dict | None = None) -> None:
        nonlocal raw_info
        raw_info = _atomic_npz(arrays_path, {**base_arrays, **local_arrays})
        _atomic_json(progress_path, {
            "schema": "task40extra.review_v8_w1_boundary_probe_progress.v1",
            "status": "IN_PROGRESS",
            "stage": stage,
            "started_monotonic": started,
            "checkpoint_monotonic": time.monotonic(),
            "source_files_sha256": _source_file_hashes(),
            "input_inventory": inventory,
            "q30_q60": boundary,
            "completed_local_cases": local_correction_cases,
            "raw": raw_info,
        })

    modes, inventory = _load_modes(mode_path)
    phase_x, phase_y, bloch = _floquet_phases(modes)
    x = _proportional_axis([-25.0, -8.5, 0.0, 8.5, 25.0], 272)
    y = np.asarray([-12.5, -6.25, 0.0, 6.25, 12.5], dtype=np.float64)
    representative_i, representative_j = 100, 1
    selected_faces = [
        ("top", representative_i, representative_j),
        ("bottom", representative_i, representative_j),
    ]
    polynomial = FacetPolynomial(_make_element(6))
    layout = BoundaryLayout(x, y, polynomial, (phase_x, phase_y))
    if (layout.nx, layout.ny) != (272, 4):
        raise ValueError("candidate face partition must be 272 by 4")
    ntrace, nmode = layout.rows, len(modes)
    trace = np.ones(ntrace, dtype=np.complex128)
    dual = np.exp(2j * np.pi * np.arange(ntrace, dtype=np.float64) / max(ntrace, 1)).astype(np.complex128)
    alpha = np.full(nmode, 1.0 / math.sqrt(nmode), dtype=np.complex128)
    physical_config = SimulationConfig3D(
        case_name="task40_w1_local_representative",
        geometry_kind="rectangular_block_grating",
        lambda0=0.7,
        n_air=1.0 + 0.0j,
        mu_r=1.0 + 0.0j,
        n_substrate=SILICON_INDEX,
        n_grating=SILICON_INDEX,
        stage4_boundary_model="dtn_port",
    )

    q30 = DirectionalBoundaryAction(
        layout, modes, 30, face_inventory=selected_faces
    )
    q30_components = q30.project_components(trace)
    q30_recover = q30.recover(trace)
    q30_apply = q30.apply(trace)
    q30_adjoint = q30.apply(dual, adjoint=True)
    q30_rhs = q30.modal_rhs(alpha)
    dot_left = np.vdot(dual, q30_apply)
    dot_right = np.vdot(q30_adjoint, trace)
    adjoint_rel = abs(dot_left - dot_right) / max(abs(dot_left), abs(dot_right), np.finfo(float).tiny)
    adjoint_gate = bool(adjoint_rel <= 1e-10)
    modal_rhs_gate = bool(np.linalg.norm(q30_rhs) > 0)
    q30_stats = dict(q30.stats)
    q30_cache = int(q30.cache_bytes)
    del q30

    mode_identity_arrays = {
        "trace": trace,
        "dual": dual,
        "alpha": alpha,
        "mode_index": np.asarray([m["mode_index"] for m in modes], np.int32),
        "m": np.asarray([m["m"] for m in modes], np.int32),
        "n": np.asarray([m["n"] for m in modes], np.int32),
        "side": np.asarray([m["side"] for m in modes], dtype="U6"),
        "polarization": np.asarray([m["polarization"] for m in modes], dtype="U1"),
        "surface_x_axis_nm": x,
        "surface_y_axis_nm": y,
        "floquet_phases": np.asarray([phase_x, phase_y], dtype=np.complex128),
        "representative_face_indices": np.asarray(
            [[representative_i, representative_j]], dtype=np.int32
        ),
        "mode_manifest_sha256_ascii": np.frombuffer(
            inventory["mode_manifest_sha256"].encode("ascii"), dtype=np.uint8
        ),
        "ordered_key_sha256_ascii": np.frombuffer(
            inventory["ordered_key_sha256"].encode("ascii"), dtype=np.uint8
        ),
    }
    base_arrays = {
        **mode_identity_arrays,
        "q30_components": q30_components,
        "q30_recover": q30_recover,
        "q30_apply": q30_apply,
        "q30_adjoint": q30_adjoint,
        "q30_modal_rhs": q30_rhs,
    }
    checkpoint("Q30_BOUNDARY_EVIDENCE_SAVED_Q60_PENDING", inventory, {
        "q_degrees": [30],
        "mode_count": len(modes),
        "q30_adjoint_bilinear_relative": float(adjoint_rel),
        "q30_adjoint_gate_pass": adjoint_gate,
        "q30_modal_rhs_norm": float(np.linalg.norm(q30_rhs)),
        "q30_modal_rhs_nonzero_gate_pass": modal_rhs_gate,
    })

    q60 = DirectionalBoundaryAction(
        layout, modes, 60, face_inventory=selected_faces
    )
    q60_components = q60.project_components(trace)
    q60_recover = q60.recover(trace)
    q60_apply = q60.apply(trace)
    denominators = q60.H.copy()
    component_delta = np.linalg.norm(q30_components - q60_components, axis=1) / np.abs(denominators)
    q60_scale = np.maximum(np.linalg.norm(q60_components, axis=1) / np.abs(denominators), np.finfo(float).tiny)
    per_mode_relative = np.abs(q30_recover - q60_recover) / q60_scale
    worst = int(np.argmax(per_mode_relative))
    action_delta = np.linalg.norm(q30_apply - q60_apply) / max(
        np.linalg.norm(q60_apply), np.finfo(float).tiny
    )
    q60_stats = dict(q60.stats)
    q60_cache = int(q60.cache_bytes)
    del q60
    boundary_gate = bool(
        float(per_mode_relative[worst]) <= 1e-10
        and adjoint_gate
        and modal_rhs_gate
    )
    base_arrays.update({
        "q60_components": q60_components,
        "q60_recover": q60_recover,
        "q60_apply": q60_apply,
        "denominators": denominators,
    })
    boundary_checkpoint = {
        "q_degrees": [30, 60],
        "mode_count": len(modes),
        "maximum_relative_error": float(per_mode_relative[worst]),
        "maximum_component_delta_over_original_denominator": float(np.max(component_delta)),
        "worst_mode_index": int(worst),
        "worst_key": [modes[worst]["side"], modes[worst]["m"], modes[worst]["n"], modes[worst]["polarization"]],
        "worst_original_projection_denominator": float(denominators[worst]),
        "boundary_limit": 1e-10,
        "boundary_gate_pass": boundary_gate,
        "full_action_relative_difference": float(action_delta),
        "q30_adjoint_bilinear_relative": float(adjoint_rel),
        "q30_adjoint_gate_pass": adjoint_gate,
        "q30_modal_rhs_norm": float(np.linalg.norm(q30_rhs)),
        "q30_modal_rhs_nonzero_gate_pass": modal_rhs_gate,
    }
    checkpoint("Q30_Q60_BOUNDARY_EVIDENCE_SAVED_LOCAL_CASES_PENDING", inventory, boundary_checkpoint)

    selected = [next(m for m in modes if m["side"] == side) for side in ("top", "bottom")]
    witness = DirectionalBoundaryAction(
        layout, selected, 30,
        face_inventory=selected_faces,
    )
    witness_trace = np.ones(ntrace, dtype=np.complex128)
    witness_values = witness.project_components(witness_trace)
    old_values = np.vstack([
        _direct_single_face_projection(
            layout, mode, witness_trace, 30, representative_i, representative_j
        )
        for mode in selected
    ])
    old_witness_rel = float(
        np.linalg.norm(witness_values - old_values)
        / max(np.linalg.norm(old_values), np.finfo(float).tiny)
    )
    old_witness_gate = bool(old_witness_rel <= 1e-10)
    boundary_checkpoint.update({
        "explicit_old_representation_relative": old_witness_rel,
        "explicit_old_representation_gate_pass": old_witness_gate,
    })
    base_arrays.update({
        "old_representation_witness_trace": witness_trace,
        "old_representation_witness_values": witness_values,
        "old_representation_direct_values": old_values,
    })
    checkpoint("BOUNDARY_AND_SMALL_KEY_EVIDENCE_SAVED_LOCAL_CASES_PENDING", inventory, boundary_checkpoint)
    del witness, layout, polynomial

    local_layouts = {
        degree: BoundaryLayout(
            x, y, FacetPolynomial(_make_element(degree)), (phase_x, phase_y)
        )
        for degree in (4, 6)
    }
    for degree in (4, 6):
        element = local_layouts[degree].polynomial.element
        interior_positions = np.asarray(element.entity_dofs[3][0], dtype=np.int64)
        local_trace_count = int(element.dim - len(interior_positions))
        for side in ("top", "bottom"):
            z_bounds = (120.0, 130.0) if side == "top" else (-10.0, 0.0)
            bounds = (
                (float(x[representative_i]), float(x[representative_i + 1])),
                (float(y[representative_j]), float(y[representative_j + 1])),
                z_bounds,
            )
            material_tag = (
                physical_config.tags.air
                if side == "top"
                else physical_config.tags.substrate
            )
            local_ni = len(interior_positions)
            alpha_local = (
                1.0 + np.arange(nmode, dtype=np.float64) * 1e-4
                + 1j * (1.0 + np.arange(nmode, dtype=np.float64)[::-1] * 1e-5)
            ) / math.sqrt(nmode)
            known_interior_solution_local = (
                1.0 + np.arange(local_ni, dtype=np.float64) * 1e-3
                + 1j * (1.0 + np.arange(local_ni, dtype=np.float64)[::-1] * 5e-4)
            ) / math.sqrt(max(local_ni, 1))
            trace_values_local = (
                1.0 + np.arange(local_trace_count, dtype=np.float64) * 1e-4
                - 0.2j * (1.0 + np.arange(local_trace_count, dtype=np.float64)[::-1] * 2e-4)
            ) / math.sqrt(max(local_trace_count, 1))
            try:
                result = stream_boundary_correction(
                    modes=modes,
                    side=side,
                    degree=degree,
                    bounds=bounds,
                    config=physical_config,
                    material_tag=material_tag,
                    mode_alpha=alpha_local,
                    trace_values=trace_values_local,
                    known_interior_solution=known_interior_solution_local,
                    boundary_layout=local_layouts[degree],
                    face_i=representative_i,
                    face_j=representative_j,
                    boundary_quadrature_degree=30,
                    batch_modes=64,
                )
                arrays = result.pop("arrays")
                for name, array in arrays.items():
                    local_arrays[f"p{degree}_{side}_{name}"] = array
                result["case_status"] = "PASS" if (
                    result["local_recovery_equation_relative"] <= 1e-11
                    and result["known_interior_solution_relative"] <= 1e-11
                    and result["local_original_trace_equation_relative"] <= 1e-10
                    and result["local_reduced_trace_equation_relative"] <= 1e-10
                    and result["local_trace_elimination_identity_relative"] <= 1e-10
                    and result["local_port_equation_relative"] <= 1e-10
                    and result["local_reduced_port_equation_relative"] <= 1e-10
                    and result["local_port_elimination_identity_relative"] <= 1e-10
                    and result["nonzero_internal_rhs_norm"] > 0
                    and result["nonzero_full_port_rhs_norm"] > 0
                    and result["nonzero_trace_rhs_norm"] > 0
                    and result["small_key_native_carrier_witness"][
                        "full_dof_direct_q30_gate_pass"
                    ]
                ) else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"
                local_correction_cases.append(result)
            except Exception as exc:  # preserve a negative case in the atomic report
                local_correction_cases.append({
                    "degree": degree,
                    "side": side,
                    "case_bounds_nm": [[float(a), float(b)] for a, b in bounds],
                    "case_status": "FAILED_LOCAL_PROBE",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
            checkpoint(f"P{degree}_{side}_CASE_SAVED", inventory, boundary_checkpoint)
    checkpoint("ALL_LOCAL_CASES_SAVED_CHECKER_PENDING", inventory, boundary_checkpoint)
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    local_gates_pass = bool(local_correction_cases) and all(
        case.get("case_status") == "PASS" for case in local_correction_cases
    )
    full_target_mpc_qualified = False
    if not boundary_gate or not old_witness_gate or not local_gates_pass:
        status = "CONTROLLED_NEGATIVE_REQUIRED_GATE_FAILED"
    elif not full_target_mpc_qualified:
        status = "PARTIAL_PASS_COMPONENTS_FULL_TARGET_MPC_NOT_RUN"
    else:
        status = "PASS_W1_BOUNDED_PROBE_NOT_FULLSIZE_FE"
    source_files_sha256 = _source_file_hashes()
    report = {
        "schema": "task40extra.review_v8_w1_boundary_probe.v1",
        "status": status,
        "w1_required_gates_pass": bool(
            boundary_gate and old_witness_gate and local_gates_pass and full_target_mpc_qualified
        ),
        "started_monotonic": started,
        "elapsed_monotonic_seconds": time.monotonic() - started,
        "source_head_at_probe": source_sha,
        "input_inventory": inventory,
        "physical_surface": {
            "period_x_nm": PERIOD_X_NM,
            "period_y_nm": PERIOD_Y_NM,
            "bottom_z_nm": BOUNDARY_Z_NM["bottom"],
            "top_z_nm": BOUNDARY_Z_NM["top"],
            "x_plane_bounds_nm": [-25.0, -8.5, 0.0, 8.5, 25.0],
            "x_intervals_by_zone": [90, 46, 46, 90],
            "y_plane_bounds_nm": [-12.5, -6.25, 0.0, 6.25, 12.5],
            "facet_count_each_surface": len(selected_faces) // 2,
            "surface_axis_identity_sha256": _sha256_bytes(x.tobytes() + y.tobytes()),
            "partition_classification": "derived exact-plane 272x4 boundary candidate; no 3D mesh constructed",
            "representative_face_inventory": [list(face) for face in selected_faces],
            "basis": "Basix N1curl hexahedron degree 6",
            "floquet": bloch,
        },
        "q30_q60": {
            "q_degrees": [30, 60],
            "mode_count": nmode,
            "all_keys_compared": True,
            "relative_error_definition": "abs(recover_q30-recover_q60) / max(norm(project_q60_components)/original_projection_denominator, tiny)",
            "maximum_relative_error": float(per_mode_relative[worst]),
            "maximum_component_delta_over_original_denominator": float(np.max(component_delta)),
            "worst_mode_index": int(worst),
            "worst_key": [modes[worst]["side"], modes[worst]["m"], modes[worst]["n"], modes[worst]["polarization"]],
            "worst_original_projection_denominator": float(denominators[worst]),
            "boundary_limit": 1e-10,
            "boundary_gate_pass": boundary_gate,
            "all_keys_on_selected_faces_only": True,
            "full_action_relative_difference": float(action_delta),
            "q30_adjoint_bilinear_relative": float(adjoint_rel),
            "q30_adjoint_gate_pass": adjoint_gate,
            "q30_modal_rhs_norm": float(np.linalg.norm(q30_rhs)),
            "q30_modal_rhs_nonzero_gate_pass": modal_rhs_gate,
            "q30_cache_bytes": q30_cache,
            "q60_cache_bytes": q60_cache,
            "q30_action_stats": q30_stats,
            "q60_action_stats": q60_stats,
        },
        "explicit_old_representation": {
            "scope": "one real top and one real bottom candidate panel; first frozen AUTO key on each side; q30 direct facet sum",
            "relative_difference": old_witness_rel,
            "limit": 1e-10,
            "passed": old_witness_gate,
        },
        "original_size_local_internal_correction": {
            "classification": "one-cell Maxwell form on target-coordinate top-air/bottom-Si representatives; not an assembled target volume mesh",
            "volume_form_source": "common_3d_forms._build_physical_volume_terms; compiled by the same fem.form(a) default path as common_3d_case_flow",
            "volume_quadrature_policy": "FFCx/DOLFINx original default; no explicit degree override or scan",
            "boundary_quadrature_degree": 30,
            "batch_modes": 64,
            "all_32060_ordered_keys_present_in_vectors": True,
            "cases": local_correction_cases,
            "all_local_equation_gates_pass": local_gates_pass,
            "full_target_mpc_master_slave_mapping": "NOT_RUN; global original-size MPC row IDs require the unconstructed target volume mesh",
        },
        "raw": {
            **(raw_info or {}),
        },
        "source_files_sha256": source_files_sha256,
        "formal_scope": {
            "one_cell_local_FE_kernel_and_factor": True,
            "global_volume_matrix_or_factor": False,
            "official_results": False,
            "source_of_local_cells": "target ledger outer-plane coordinates and air/Si material; one-cell representative only; no W0 raw internal carriers",
            "original_size_full_volume_or_target_mpc_mapping_qualified": False,
        },
    }
    _atomic_json(output / "w1_boundary_probe_report.json", report)
    _atomic_json(progress_path, {
        "schema": "task40extra.review_v8_w1_boundary_probe_progress.v1",
        "status": "RUNNER_COMPLETE_CHECKER_PENDING",
        "stage": "RUNNER_COMPLETE_CHECKER_PENDING",
        "started_monotonic": started,
        "checkpoint_monotonic": time.monotonic(),
        "source_files_sha256": source_files_sha256,
        "input_inventory": inventory,
        "q30_q60": boundary_checkpoint,
        "completed_local_cases": local_correction_cases,
        "raw": raw_info,
    })
    return report


def _v10_local_case_pass(case: dict) -> bool:
    return bool(
        case["local_recovery_equation_relative"] <= 1e-11
        and case["known_interior_solution_relative"] <= 1e-11
        and case["local_original_trace_equation_relative"] <= 1e-10
        and case["local_reduced_trace_equation_relative"] <= 1e-10
        and case["local_trace_elimination_identity_relative"] <= 1e-10
        and case["local_port_equation_relative"] <= 1e-10
        and case["local_reduced_port_equation_relative"] <= 1e-10
        and case["local_port_elimination_identity_relative"] <= 1e-10
        and case["nonzero_internal_rhs_norm"] > 0
        and case["nonzero_full_port_rhs_norm"] > 0
        and case["nonzero_trace_rhs_norm"] > 0
        and case["analytic_full_row_crosscheck"]["status"] == "PASS"
        and case["small_key_native_carrier_witness"]["full_dof_direct_q30_gate_pass"]
    )


def run_v10_saved_array_extension(
    output: Path,
    mode_path: Path = MODE_PATH,
    raw_path: Path = SAVED_W1_RAW,
    reference_path: Path = SAVED_W9_REFERENCE,
) -> dict:
    """Extend W1 from its frozen arrays; do not rerun q30 or rebuild p4 volume."""
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    if _file_sha256(raw_path) != SAVED_W1_RAW_SHA256:
        raise ValueError("saved W1 raw archive SHA mismatch")
    if _file_sha256(reference_path) != SAVED_W9_REFERENCE_SHA256:
        raise ValueError("saved V9 reference archive SHA mismatch")
    modes, inventory = _load_modes(mode_path)
    with np.load(raw_path, allow_pickle=False) as loaded:
        saved = {key: loaded[key] for key in loaded.files}
    with np.load(reference_path, allow_pickle=False) as loaded:
        reference = {key: loaded[key] for key in loaded.files}
    if len(reference) != 10:
        raise ValueError("frozen V9 reference archive must retain its ten registered members")
    if (
        _sha256_bytes(np.ascontiguousarray(saved["q60_apply"]).tobytes())
        != SAVED_Q60_APPLY_SHA256
        or _sha256_bytes(np.ascontiguousarray(saved["q60_components"]).tobytes())
        != SAVED_Q60_COMPONENTS_SHA256
    ):
        raise ValueError("saved q60 action/component identity differs from the V10 recheck")
    if not np.array_equal(saved["q60_apply"], reference["q60_apply_saved"]):
        raise ValueError("saved q60 action differs from the V9 raw reference array")
    if not np.array_equal(saved["q60_components"], reference["q60_components_saved"]):
        raise ValueError("saved q60 components differ from the V9 raw reference array")
    if saved["trace"].shape != (156672,) or saved["q60_apply"].shape != (156672,):
        raise ValueError("frozen W1 boundary vector shape changed")
    if saved["q60_components"].shape != (32060, 2) or len(modes) != 32060:
        raise ValueError("frozen W1 q60 full ordered mode shape changed")
    expected_identity = {
        "mode_index": np.asarray([mode["mode_index"] for mode in modes], dtype=np.int32),
        "m": np.asarray([mode["m"] for mode in modes], dtype=np.int32),
        "n": np.asarray([mode["n"] for mode in modes], dtype=np.int32),
        "side": np.asarray([mode["side"] for mode in modes], dtype="U6"),
        "polarization": np.asarray(
            [mode["polarization"] for mode in modes], dtype="U1"
        ),
    }
    if any(not np.array_equal(saved[key], value) for key, value in expected_identity.items()):
        raise ValueError("saved W1 ordered mode identities differ from the frozen manifest")

    x = np.asarray(saved["surface_x_axis_nm"], dtype=np.float64)
    y = np.asarray(saved["surface_y_axis_nm"], dtype=np.float64)
    phases = tuple(complex(value) for value in saved["floquet_phases"])
    phase_x, phase_y, floquet = _floquet_phases(modes)
    if max(abs(phases[0] - phase_x), abs(phases[1] - phase_y)) > 2e-11:
        raise ValueError("saved W1 Floquet phase bridge differs from the frozen manifest")
    selected_face = tuple(int(v) for v in saved["representative_face_indices"][0])
    if selected_face != (100, 1) or (len(x) - 1, len(y) - 1) != (272, 4):
        raise ValueError("saved W1 representative panel or axes identity changed")
    face_inventory = [("top", *selected_face), ("bottom", *selected_face)]
    polynomial = FacetPolynomial(_make_element(6))
    layout = BoundaryLayout(x, y, polynomial, phases)
    ntrace, nmode = layout.rows, len(modes)
    mode_indices = {tuple((m["side"], m["m"], m["n"], m["polarization"])): i for i, m in enumerate(modes)}
    max_kx_index = max(
        range(nmode),
        key=lambda i: abs(zvalue(modes[i]["k_vector"][0])),
    )
    max_ky_index = max(
        range(nmode),
        key=lambda i: abs(zvalue(modes[i]["k_vector"][1])),
    )
    registered_indices = {
        "historical_q30_worst": mode_indices[("top", -67, -34, "s")],
        "saved_q60_worst": mode_indices[("top", -71, 35, "s")],
        "actual_n0": mode_indices[("top", -142, 0, "s")],
        "maximum_abs_kx": max_kx_index,
        "maximum_abs_ky": max_ky_index,
    }

    row = np.arange(ntrace, dtype=np.float64)
    generic_trace = np.asarray(
        (
            np.sin(0.00037 * (row + 1)) + 0.17 * np.cos(0.0019 * row)
            + 1j * (np.cos(0.00053 * (row + 1)) - 0.23 * np.sin(0.0013 * row))
        ) / math.sqrt(ntrace),
        dtype=np.complex128,
    )
    modal_index = np.arange(nmode, dtype=np.float64)
    generic_alpha = np.asarray(
        (
            np.sin(0.013 * (modal_index + 1))
            + 1j * np.cos(0.017 * (modal_index + 1))
        ) / math.sqrt(nmode),
        dtype=np.complex128,
    )
    frozen_e = np.asarray(
        [[zvalue(value) for value in mode["e_vector"][:2]] for mode in modes],
        dtype=np.complex128,
    )
    frozen_h = np.asarray(saved["denominators"], dtype=np.float64)
    frozen_scale = np.linalg.norm(saved["q60_components"], axis=1) / np.abs(frozen_h)
    if np.any(frozen_scale == 0):
        raise ValueError("frozen q60 per-mode scale contains an exact zero; original absolute rule required")
    frozen_reference_recover = np.sum(
        frozen_e.conj() * reference["reference_components_80"], axis=1
    ) / frozen_h
    frozen_per_mode = np.abs(saved["q60_recover"] - frozen_reference_recover) / frozen_scale
    frozen_full_action_error = float(
        np.linalg.norm(saved["q60_apply"] - reference["reference_action_80"])
        / np.linalg.norm(saved["q60_apply"])
    )
    q60 = DirectionalBoundaryAction(layout, modes, 60, face_inventory=face_inventory)
    analytic_reference = AnalyticMomentBoundaryReference(
        layout, modes, face_inventory=face_inventory
    )
    generic_components = q60.project_components(generic_trace)
    generic_apply = q60.apply(generic_trace)
    generic_port_rhs = q60.modal_rhs(generic_alpha)
    generic_scatter = q60.scatter_components(generic_components)
    reference_components = analytic_reference.project_components(generic_trace)
    reference_apply = analytic_reference.apply(generic_trace)
    reference_port_rhs = analytic_reference.modal_rhs(generic_alpha)
    reference_scatter = analytic_reference.scatter_components(generic_components)
    saved_action_norm = float(np.linalg.norm(saved["q60_apply"]))
    frozen_mode_scale = (
        np.linalg.norm(saved["q60_components"], axis=1)
        / np.abs(np.asarray(saved["denominators"], dtype=np.float64))
    )
    if saved_action_norm == 0 or np.any(frozen_mode_scale == 0):
        raise ValueError("frozen W1 per-mode/action scale is zero; original absolute rule required")
    generic_mode_error = (
        np.linalg.norm(generic_components - reference_components, axis=1)
        / np.abs(np.asarray(saved["denominators"], dtype=np.float64))
        / frozen_mode_scale
    )
    generic_full_action_error = float(
        np.linalg.norm(generic_apply - reference_apply) / saved_action_norm
    )
    reference_port_norm = float(np.linalg.norm(reference_port_rhs))
    reference_scatter_norm = float(np.linalg.norm(reference_scatter))
    generic_port_error = (
        float(np.linalg.norm(generic_port_rhs - reference_port_rhs) / reference_port_norm)
        if reference_port_norm > 0 else float("inf")
    )
    generic_scatter_error = (
        float(np.linalg.norm(generic_scatter - reference_scatter) / reference_scatter_norm)
        if reference_scatter_norm > 0 else float("inf")
    )

    direct_panel_witnesses = []
    moment_witnesses = []
    for label, index in registered_indices.items():
        mode = modes[index]
        direct = direct_single_face_projection(
            layout, mode, generic_trace, 60, *selected_face
        )
        candidate = generic_components[index]
        panel_scale = float(np.linalg.norm(direct))
        panel_relative = (
            float(np.linalg.norm(candidate - direct) / panel_scale)
            if panel_scale > 0 else float("inf")
        )
        direct_panel_witnesses.append({
            "witness": label,
            "mode_index": int(index),
            "key": [mode["side"], mode["m"], mode["n"], mode["polarization"]],
            "q60_direct_panel_relative": panel_relative,
        })
        axis_moments = {}
        for axis_index, axis_label, coords in ((0, "x", x), (1, "y", y)):
            k = -np.conj(zvalue(mode["k_vector"][axis_index]))
            origin = float(coords[selected_face[0 if axis_index == 0 else 1]])
            length = float(np.diff(coords)[selected_face[0 if axis_index == 0 else 1]])
            q_rule = np.asarray(
                quadrature_legendre_exponential_moments(
                    k, origin, length, 6, quadrature_degree=60
                ), dtype=np.complex128,
            )
            direct_mp = np.asarray(
                segmented_legendre_exponential_moments(
                    k, origin, length, 6, dps=100, segments=5
                ), dtype=np.complex128,
            )
            analytic_table = legendre_exponential_moment_table(
                k, np.asarray([origin]), np.asarray([length]), 6
            )[0]
            scale = float(np.linalg.norm(direct_mp))
            q_relative = float(np.linalg.norm(q_rule - direct_mp) / scale)
            analytic_relative = float(np.linalg.norm(analytic_table - direct_mp) / scale)
            axis_moments[axis_label] = {
                "candidate_q60_vs_segmented_direct_relative": q_relative,
                "independent_analytic_vs_segmented_direct_relative": analytic_relative,
                "q60_degree": 60,
                "direct_precision_dps": 100,
            }
        moment_witnesses.append({
            "witness": label,
            "mode_index": int(index),
            "key": [mode["side"], mode["m"], mode["n"], mode["polarization"]],
            "axes": axis_moments,
        })

    candidate_limit = 1e-10
    independent_reference_limit = 1e-12
    max_panel_relative = max(item["q60_direct_panel_relative"] for item in direct_panel_witnesses)
    max_candidate_moment_relative = max(
        entry["candidate_q60_vs_segmented_direct_relative"]
        for witness in moment_witnesses
        for entry in witness["axes"].values()
    )
    max_independent_reference_relative = max(
        entry["independent_analytic_vs_segmented_direct_relative"]
        for witness in moment_witnesses
        for entry in witness["axes"].values()
    )
    q60_finite_pass = bool(
        np.isfinite(generic_components).all()
        and np.isfinite(generic_apply).all()
        and np.isfinite(generic_port_rhs).all()
        and np.linalg.norm(generic_trace) > 0
        and np.linalg.norm(generic_alpha) > 0
        and np.linalg.norm(generic_port_rhs) > 0
        and np.isfinite(generic_mode_error).all()
        and float(np.max(generic_mode_error)) <= candidate_limit
        and generic_full_action_error <= candidate_limit
        and float(np.max(frozen_per_mode)) <= candidate_limit
        and frozen_full_action_error <= candidate_limit
        and generic_port_error <= candidate_limit
        and generic_scatter_error <= candidate_limit
        and max_panel_relative <= candidate_limit
        and max_candidate_moment_relative <= candidate_limit
        and max_independent_reference_relative <= independent_reference_limit
    )
    q60_witness = {
        "status": "PASS_FINITE_WITNESSES" if q60_finite_pass else "CONTROLLED_NEGATIVE_Q60_WITNESS",
        "generic_trace_nonzero": bool(np.linalg.norm(generic_trace) > 0),
        "generic_port_amplitudes_nonzero": bool(np.linalg.norm(generic_alpha) > 0),
        "generic_full_mode_port_rhs_norm": float(np.linalg.norm(generic_port_rhs)),
        "generic_full_mode_apply_norm": float(np.linalg.norm(generic_apply)),
        "generic_full_mode_scatter_norm": float(np.linalg.norm(generic_scatter)),
        "generic_mode_max_relative_over_frozen_scale": float(np.max(generic_mode_error)),
        "generic_full_action_relative_over_saved_q60_apply_norm": generic_full_action_error,
        "generic_port_rhs_relative_to_analytic_reference": generic_port_error,
        "generic_scatter_relative_to_analytic_reference": generic_scatter_error,
        "candidate_q60_limit": candidate_limit,
        "independent_reference_cross_limit": independent_reference_limit,
        "frozen_saved_q60_max_per_mode_relative_over_original_scale": float(np.max(frozen_per_mode)),
        "frozen_saved_q60_full_action_relative_over_saved_norm": frozen_full_action_error,
        "max_q60_direct_panel_relative": max_panel_relative,
        "max_candidate_q60_segmented_moment_relative": max_candidate_moment_relative,
        "max_independent_analytic_segmented_moment_relative": max_independent_reference_relative,
        "direct_panel_witnesses": direct_panel_witnesses,
        "moment_witnesses": moment_witnesses,
        "registered_mode_indices": registered_indices,
    }
    witness_arrays = {
        "generic_trace": generic_trace,
        "generic_alpha": generic_alpha,
        "generic_q60_components": generic_components,
        "generic_q60_apply": generic_apply,
        "generic_q60_port_rhs": generic_port_rhs,
        "generic_q60_scatter": generic_scatter,
        "generic_analytic_reference_components": reference_components,
        "generic_analytic_reference_apply": reference_apply,
        "generic_analytic_reference_port_rhs": reference_port_rhs,
        "generic_analytic_reference_scatter": reference_scatter,
    }
    arrays_info = _atomic_npz(output / "w1_v10_a_extension_arrays.npz", witness_arrays)

    def write_checkpoint(status: str, cases: list[dict], *, p6_started: bool) -> dict:
        nonlocal arrays_info
        arrays_info = _atomic_npz(
            output / "w1_v10_a_extension_arrays.npz", witness_arrays
        )
        checkpoint = {
            "schema": "task40extra.review_v10_w1_a_saved_array_extension.v1",
            "status": status,
            "started_monotonic": started,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "saved_w1_raw": {"path": str(raw_path.relative_to(ROOT)), "sha256": SAVED_W1_RAW_SHA256},
            "saved_v9_reference": {"path": str(reference_path.relative_to(ROOT)), "sha256": SAVED_W9_REFERENCE_SHA256},
            "input_inventory": inventory,
            "floquet_bridge": floquet,
            "q60_finite_witness": q60_witness,
            "local_cases": cases,
            "completed_local_objects": [
                f"p{case['degree']}_{case['side']}" for case in cases
                if case.get("case_status") != "FAILED_LOCAL_PROBE"
            ],
            "arrays": arrays_info,
            "source_files_sha256": _source_file_hashes(),
            "p4_volume_reused": True,
            "p6_volume_build_count": sum(int(case.get("degree") == 6) for case in cases),
            "p6_started": p6_started,
            "dense_mode_square_materialized": False,
        }
        _atomic_json(output / "w1_v10_a_extension_report.json", checkpoint)
        return checkpoint

    if not q60_finite_pass:
        return write_checkpoint("CONTROLLED_NEGATIVE_Q60_WITNESS", [], p6_started=False)

    write_checkpoint("Q60_GATE_PASSED_LOCAL_OBJECTS_PENDING", [], p6_started=False)

    config = SimulationConfig3D(
        case_name="task40_v10_w1_saved_array_extension",
        geometry_kind="rectangular_block_grating",
        lambda0=0.7,
        n_air=1.0 + 0.0j,
        mu_r=1.0 + 0.0j,
        n_substrate=SILICON_INDEX,
        n_grating=SILICON_INDEX,
        stage4_boundary_model="dtn_port",
    )
    local_layouts = {
        degree: BoundaryLayout(
            x, y, FacetPolynomial(_make_element(degree)), phases
        )
        for degree in (4, 6)
    }
    i, j = selected_face
    local_cases = []

    for side in ("top", "bottom"):
        z_bounds = (120.0, 130.0) if side == "top" else (-10.0, 0.0)
        bounds = (
            (float(x[i]), float(x[i + 1])),
            (float(y[j]), float(y[j + 1])),
            z_bounds,
        )
        tag = config.tags.air if side == "top" else config.tags.substrate
        p4_saved_volume = {
            "tensor": saved[f"p4_{side}_local_native_tensor"],
            "coordinates": saved[f"p4_{side}_local_cell_coordinates"],
            "cell_info": saved[f"p4_{side}_local_cell_orientation"],
            "interior_positions": saved[f"p4_{side}_interior_positions"],
            "trace_positions": saved[f"p4_{side}_trace_positions"],
        }
        try:
            p4_result = stream_boundary_correction(
                modes=modes,
                side=side,
                degree=4,
                bounds=bounds,
                config=config,
                material_tag=tag,
                mode_alpha=saved[f"p4_{side}_mode_alpha"],
                trace_values=saved[f"p4_{side}_trace_values"],
                known_interior_solution=saved[f"p4_{side}_known_interior_solution"],
                boundary_layout=local_layouts[4],
                face_i=i,
                face_j=j,
                boundary_quadrature_degree=60,
                batch_modes=64,
                saved_local_volume=p4_saved_volume,
                verify_analytic_full_rows=True,
            )
        except Exception as exc:
            local_cases.append({
                "degree": 4, "side": side, "case_status": "FAILED_LOCAL_PROBE",
                "error_type": type(exc).__name__, "error": str(exc),
                "volume_source": "saved W1 raw p4 tensor; no volume reassembly",
                "boundary_quadrature_degree": 60,
                "mode_count_full_ordered": nmode,
            })
            return write_checkpoint("CONTROLLED_NEGATIVE_LOCAL_OBJECT", local_cases, p6_started=False)
        for key, value in p4_result.pop("arrays").items():
            witness_arrays[f"p4_q60_{side}_{key}"] = value
        p4_result.update({
            "degree": 4,
            "side": side,
            "case_status": "PASS" if _v10_local_case_pass(p4_result) else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
            "volume_source": "saved W1 raw p4 tensor; no volume reassembly",
            "boundary_quadrature_degree": 60,
        })
        local_cases.append(p4_result)
        write_checkpoint(
            "LOCAL_OBJECT_CHECKPOINTED" if p4_result["case_status"] == "PASS"
            else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
            local_cases,
            p6_started=False,
        )
        if p4_result["case_status"] != "PASS":
            return write_checkpoint("CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE", local_cases, p6_started=False)

        n_i, n_t = 450, 432
        local_row_i = np.arange(n_i, dtype=np.float64)
        local_row_t = np.arange(n_t, dtype=np.float64)
        try:
            p6_result = stream_boundary_correction(
                modes=modes,
                side=side,
                degree=6,
                bounds=bounds,
                config=config,
                material_tag=tag,
                mode_alpha=generic_alpha,
                trace_values=np.asarray(
                    (1.0 + 1e-4 * local_row_t)
                    + 1j * (0.25 + 2e-4 * local_row_t[::-1]),
                    dtype=np.complex128,
                ) / math.sqrt(n_t),
                known_interior_solution=np.asarray(
                    (1.0 + 1e-3 * local_row_i)
                    + 1j * (0.5 + 5e-4 * local_row_i[::-1]),
                    dtype=np.complex128,
                ) / math.sqrt(n_i),
                boundary_layout=local_layouts[6],
                face_i=i,
                face_j=j,
                boundary_quadrature_degree=60,
                batch_modes=64,
                verify_analytic_full_rows=True,
            )
        except Exception as exc:
            local_cases.append({
                "degree": 6, "side": side, "case_status": "FAILED_LOCAL_PROBE",
                "error_type": type(exc).__name__, "error": str(exc),
                "volume_source": "new one-cell p6 physical volume tensor, assembled once",
                "boundary_quadrature_degree": 60,
                "mode_count_full_ordered": nmode,
            })
            return write_checkpoint("CONTROLLED_NEGATIVE_LOCAL_OBJECT", local_cases, p6_started=True)
        for key, value in p6_result.pop("arrays").items():
            witness_arrays[f"p6_q60_{side}_{key}"] = value
        p6_result.update({
            "degree": 6,
            "side": side,
            "case_status": "PASS" if _v10_local_case_pass(p6_result) else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
            "volume_source": "new one-cell p6 physical volume tensor, assembled once",
            "boundary_quadrature_degree": 60,
        })
        local_cases.append(p6_result)
        write_checkpoint(
            "LOCAL_OBJECT_CHECKPOINTED" if p6_result["case_status"] == "PASS"
            else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
            local_cases,
            p6_started=True,
        )
        if p6_result["case_status"] != "PASS":
            return write_checkpoint("CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE", local_cases, p6_started=True)

    local_equation_gates = [
        case["local_recovery_equation_relative"] <= 1e-11
        and case["known_interior_solution_relative"] <= 1e-11
        and case["local_original_trace_equation_relative"] <= 1e-10
        and case["local_reduced_trace_equation_relative"] <= 1e-10
        and case["local_trace_elimination_identity_relative"] <= 1e-10
        and case["local_port_equation_relative"] <= 1e-10
        and case["local_reduced_port_equation_relative"] <= 1e-10
        and case["local_port_elimination_identity_relative"] <= 1e-10
        and case["nonzero_internal_rhs_norm"] > 0
        and case["nonzero_full_port_rhs_norm"] > 0
        and case["nonzero_trace_rhs_norm"] > 0
        and case["analytic_full_row_crosscheck"]["status"] == "PASS"
        for case in local_cases
    ]
    report = {
        "schema": "task40extra.review_v10_w1_a_saved_array_extension.v1",
        "status": "PASS_FINITE_A_COMPONENTS" if q60_finite_pass and all(local_equation_gates) else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
        "started_monotonic": started,
        "elapsed_monotonic_seconds": time.monotonic() - started,
        "saved_w1_raw": {"path": str(raw_path.relative_to(ROOT)), "sha256": SAVED_W1_RAW_SHA256},
        "saved_v9_reference": {"path": str(reference_path.relative_to(ROOT)), "sha256": SAVED_W9_REFERENCE_SHA256},
        "input_inventory": inventory,
        "floquet_bridge": floquet,
        "q60_finite_witness": q60_witness,
        "local_cases": local_cases,
        "all_local_equation_gates_pass": bool(all(local_equation_gates)),
        "p4_volume_reused": True,
        "p6_volume_build_count": 2,
        "p6_side_inventory": ["top/air", "bottom/Si"],
        "p6_boundary_quadrature_degree": 60,
        "mode_batch": 64,
        "dense_mode_square_materialized": False,
        "arrays": arrays_info,
        "source_files_sha256": _source_file_hashes(),
        "official_results": False,
        "global_target_mpc_mapping": "NOT_RUN",
    }
    _atomic_json(output / "w1_v10_a_extension_report.json", report)
    return report


def _v10_verify_parent_producer_snapshot(parent_report: dict, parent_output: Path) -> dict:
    watchdog_path = parent_output / "watchdog" / "summary.json"
    if not watchdog_path.is_file():
        raise ValueError("bottom continuation requires the parent watchdog source receipt")
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    source = watchdog.get("source_state", {})
    producer_sha = str(source.get("source_sha", ""))
    if (
        source.get("branch") != "task40extra_0p7nm_engineering"
        or source.get("clean") is not True
        or len(producer_sha) != 40
    ):
        raise ValueError("parent producer source identity is incomplete or unclean")
    checks = {}
    for relative, expected in parent_report.get("source_files_sha256", {}).items():
        try:
            blob = subprocess.run(
                ["git", "show", f"{producer_sha}:{relative}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            actual = _sha256_bytes(blob)
        except subprocess.CalledProcessError:
            actual = None
        checks[relative] = {
            "report_sha256": expected,
            "producer_git_snapshot_sha256": actual,
            "pass": actual == expected,
        }
    if not checks or not all(item["pass"] for item in checks.values()):
        raise ValueError("parent report source hashes do not match its frozen Git snapshot")
    return {"source_sha": producer_sha, "source_hash_checks": checks}


def run_v10_bottom_continuation(
    output: Path,
    parent_output: Path,
    mode_path: Path = MODE_PATH,
    raw_path: Path = SAVED_W1_RAW,
    reference_path: Path = SAVED_W9_REFERENCE,
) -> dict:
    """Resume only bottom p4/p6 from a hash-bound V10 parent checkpoint."""
    started = time.monotonic()
    output = Path(output).resolve()
    parent_output = Path(parent_output).resolve()
    if not output.is_relative_to(ROOT) or not parent_output.is_relative_to(ROOT):
        raise ValueError("V10 continuation input and output must remain inside the repository")
    if output == parent_output:
        raise ValueError("bottom continuation output must be distinct from its parent checkpoint")
    if output.exists() and any(output.iterdir()):
        raise ValueError("bottom continuation output directory must be new and empty")
    if _file_sha256(raw_path) != SAVED_W1_RAW_SHA256:
        raise ValueError("saved W1 raw archive SHA mismatch")
    if _file_sha256(reference_path) != SAVED_W9_REFERENCE_SHA256:
        raise ValueError("saved V9 reference archive SHA mismatch")

    parent_report_path = parent_output / "w1_v10_a_extension_report.json"
    if not parent_report_path.is_file():
        raise ValueError("parent V10 extension report is missing")
    parent_report_sha = _file_sha256(parent_report_path)
    parent_report = json.loads(parent_report_path.read_text(encoding="utf-8"))
    if parent_report.get("schema") != "task40extra.review_v10_w1_a_saved_array_extension.v1":
        raise ValueError("unsupported parent V10 extension report schema")
    parent_source = _v10_verify_parent_producer_snapshot(parent_report, parent_output)
    if parent_report.get("q60_finite_witness", {}).get("status") != "PASS_FINITE_WITNESSES":
        raise ValueError("bottom continuation requires the parent finite q60 witness gate")
    parent_cases = list(parent_report.get("local_cases", []))
    parent_case_by_key = {
        (int(case.get("degree", -1)), str(case.get("side", ""))): case
        for case in parent_cases
    }
    if (
        parent_report.get("completed_local_objects") != ["p4_top", "p6_top"]
        or parent_case_by_key.get((4, "top"), {}).get("case_status") != "PASS"
        or parent_case_by_key.get((6, "top"), {}).get("case_status")
        != "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"
        or float(parent_case_by_key[(6, "top")]["known_interior_solution_relative"]) <= 1e-11
    ):
        raise ValueError("parent checkpoint is not the reviewed top-p6 controlled-negative case")

    arrays_meta = parent_report.get("arrays", {})
    parent_arrays_path = (ROOT / arrays_meta.get("path", "")).resolve()
    if (
        not parent_arrays_path.is_file()
        or _file_sha256(parent_arrays_path) != arrays_meta.get("file_sha256")
        or parent_arrays_path.stat().st_size != arrays_meta.get("file_bytes")
    ):
        raise ValueError("parent V10 array archive identity mismatch")
    with np.load(parent_arrays_path, allow_pickle=False) as archive:
        witness_arrays = {key: archive[key] for key in archive.files}
    if _numeric_hashes(witness_arrays) != arrays_meta.get("member_numeric_sha256"):
        raise ValueError("parent V10 numeric array member hashes mismatch")

    modes, inventory = _load_modes(mode_path)
    if len(modes) != 32060 or inventory != parent_report.get("input_inventory"):
        raise ValueError("parent frozen full mode inventory identity differs")
    with np.load(raw_path, allow_pickle=False) as archive:
        saved = {key: archive[key] for key in archive.files}
    with np.load(reference_path, allow_pickle=False) as archive:
        reference = {key: archive[key] for key in archive.files}
    if (
        _sha256_bytes(np.ascontiguousarray(saved["q60_apply"]).tobytes())
        != SAVED_Q60_APPLY_SHA256
        or _sha256_bytes(np.ascontiguousarray(saved["q60_components"]).tobytes())
        != SAVED_Q60_COMPONENTS_SHA256
        or not np.array_equal(saved["q60_apply"], reference["q60_apply_saved"])
        or not np.array_equal(saved["q60_components"], reference["q60_components_saved"])
    ):
        raise ValueError("saved W1/V9 q60 frozen reference identity changed")
    if (
        witness_arrays.get("generic_alpha", np.empty(0)).shape != (32060,)
        or witness_arrays.get("generic_trace", np.empty(0)).shape != (156672,)
    ):
        raise ValueError("parent saved q60 witness arrays have unexpected shapes")
    required_parent_arrays = (
        "generic_alpha", "generic_trace", "generic_q60_apply",
        "p4_q60_top_local_native_tensor", "p6_q60_top_local_native_tensor",
    )
    if any(name not in witness_arrays for name in required_parent_arrays):
        raise ValueError("parent top/q60 checkpoint is missing required saved arrays")

    x = np.asarray(saved["surface_x_axis_nm"], dtype=np.float64)
    y = np.asarray(saved["surface_y_axis_nm"], dtype=np.float64)
    phases = tuple(complex(value) for value in saved["floquet_phases"])
    selected_face = tuple(int(value) for value in saved["representative_face_indices"][0])
    if selected_face != (100, 1) or (len(x) - 1, len(y) - 1) != (272, 4):
        raise ValueError("parent representative panel or frozen axes changed")
    face_i, face_j = selected_face
    bounds = (
        (float(x[face_i]), float(x[face_i + 1])),
        (float(y[face_j]), float(y[face_j + 1])),
        (-10.0, 0.0),
    )
    faces = [("top", *selected_face), ("bottom", *selected_face)]
    config = SimulationConfig3D(
        case_name="task40_v10_w1_saved_array_extension",
        geometry_kind="rectangular_block_grating",
        lambda0=0.7,
        n_air=1.0 + 0.0j,
        mu_r=1.0 + 0.0j,
        n_substrate=SILICON_INDEX,
        n_grating=SILICON_INDEX,
        stage4_boundary_model="dtn_port",
    )
    local_layouts = {
        degree: BoundaryLayout(x, y, FacetPolynomial(_make_element(degree)), phases)
        for degree in (4, 6)
    }
    local_cases = json.loads(json.dumps(parent_cases))
    parent_lineage = {
        "parent_output_directory": str(parent_output.relative_to(ROOT)),
        "parent_report_path": str(parent_report_path.relative_to(ROOT)),
        "parent_report_sha256": parent_report_sha,
        "parent_arrays_path": str(parent_arrays_path.relative_to(ROOT)),
        "parent_arrays_sha256": arrays_meta["file_sha256"],
        "parent_arrays_member_count": arrays_meta["member_count"],
        "parent_producer_source_sha": parent_source["source_sha"],
        "parent_source_hash_checks": parent_source["source_hash_checks"],
        "reused_q60_finite_witness": True,
        "reused_parent_arrays_without_numeric_recomputation": True,
        "reused_top_local_objects": ["p4_top", "p6_top"],
        "objects_to_compute": ["p4_bottom", "p6_bottom"],
    }

    output.mkdir(parents=True, exist_ok=True)

    def write_checkpoint(stage: str, *, p6_started: bool) -> dict:
        arrays_info = _atomic_npz(output / "w1_v10_a_extension_arrays.npz", witness_arrays)
        non_failed = [case for case in local_cases if case.get("case_status") != "FAILED_LOCAL_PROBE"]
        all_local_pass = bool(
            len(non_failed) == 4
            and all(case.get("case_status") == "PASS" and _v10_local_case_pass(case)
                    for case in non_failed)
        )
        report = {
            "schema": "task40extra.review_v10_w1_a_saved_array_extension.v1",
            "status": "PASS_FINITE_A_COMPONENTS" if all_local_pass else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
            "checkpoint_stage": stage,
            "started_monotonic": started,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "saved_w1_raw": parent_report["saved_w1_raw"],
            "saved_v9_reference": parent_report["saved_v9_reference"],
            "input_inventory": parent_report["input_inventory"],
            "floquet_bridge": parent_report["floquet_bridge"],
            "q60_finite_witness": parent_report["q60_finite_witness"],
            "local_cases": local_cases,
            "completed_local_objects": [
                f"p{case['degree']}_{case['side']}" for case in local_cases
                if case.get("case_status") != "FAILED_LOCAL_PROBE"
            ],
            "all_local_equation_gates_pass": all_local_pass,
            "p4_volume_reused": True,
            "p6_volume_build_count": sum(
                int(case.get("degree") == 6) for case in local_cases
                if case.get("case_status") != "FAILED_LOCAL_PROBE"
            ),
            "p6_side_inventory": [
                f"{case['side']}/{'air' if case['side'] == 'top' else 'Si'}"
                for case in local_cases if int(case.get("degree", -1)) == 6
            ],
            "p6_boundary_quadrature_degree": 60,
            "mode_batch": 64,
            "dense_mode_square_materialized": False,
            "arrays": arrays_info,
            "source_files_sha256": _source_file_hashes(),
            "official_results": False,
            "global_target_mpc_mapping": "NOT_RUN",
            "parent_lineage": parent_lineage,
            "continuation": {
                "kind": "bottom_only_from_hash_bound_parent",
                "q60_finite_witness_recomputed": False,
                "top_local_objects_recomputed": False,
                "bottom_p4_checkpointed": any(
                    int(c.get("degree", -1)) == 4 and c.get("side") == "bottom"
                    for c in local_cases
                ),
                "bottom_p6_started": p6_started,
                "numeric_negative_does_not_skip_independent_bottom_object": True,
            },
        }
        _atomic_json(output / "w1_v10_a_extension_report.json", report)
        return report

    write_checkpoint("BOTTOM_CONTINUATION_STARTED", p6_started=False)
    bottom_saved_volume = {
        "tensor": saved["p4_bottom_local_native_tensor"],
        "coordinates": saved["p4_bottom_local_cell_coordinates"],
        "cell_info": saved["p4_bottom_local_cell_orientation"],
        "interior_positions": saved["p4_bottom_interior_positions"],
        "trace_positions": saved["p4_bottom_trace_positions"],
    }
    try:
        p4_result = stream_boundary_correction(
            modes=modes,
            side="bottom",
            degree=4,
            bounds=bounds,
            config=config,
            material_tag=config.tags.substrate,
            mode_alpha=saved["p4_bottom_mode_alpha"],
            trace_values=saved["p4_bottom_trace_values"],
            known_interior_solution=saved["p4_bottom_known_interior_solution"],
            boundary_layout=local_layouts[4],
            face_i=face_i,
            face_j=face_j,
            boundary_quadrature_degree=60,
            batch_modes=64,
            saved_local_volume=bottom_saved_volume,
            verify_analytic_full_rows=True,
        )
    except Exception as exc:
        local_cases.append({
            "degree": 4, "side": "bottom", "case_status": "FAILED_LOCAL_PROBE",
            "error_type": type(exc).__name__, "error": str(exc),
            "volume_source": "saved W1 raw p4 tensor; no volume reassembly",
            "boundary_quadrature_degree": 60,
            "mode_count_full_ordered": len(modes),
        })
        return write_checkpoint("CONTROLLED_NEGATIVE_BOTTOM_P4_OBJECT", p6_started=False)
    for key, value in p4_result.pop("arrays").items():
        witness_arrays[f"p4_q60_bottom_{key}"] = value
    p4_result.update({
        "degree": 4,
        "side": "bottom",
        "case_status": "PASS" if _v10_local_case_pass(p4_result) else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
        "volume_source": "saved W1 raw p4 tensor; no volume reassembly",
        "boundary_quadrature_degree": 60,
    })
    local_cases.append(p4_result)
    write_checkpoint("BOTTOM_P4_CHECKPOINTED", p6_started=False)

    n_i, n_t = 450, 432
    local_row_i = np.arange(n_i, dtype=np.float64)
    local_row_t = np.arange(n_t, dtype=np.float64)
    try:
        p6_result = stream_boundary_correction(
            modes=modes,
            side="bottom",
            degree=6,
            bounds=bounds,
            config=config,
            material_tag=config.tags.substrate,
            mode_alpha=witness_arrays["generic_alpha"],
            trace_values=np.asarray(
                (1.0 + 1e-4 * local_row_t)
                + 1j * (0.25 + 2e-4 * local_row_t[::-1]),
                dtype=np.complex128,
            ) / math.sqrt(n_t),
            known_interior_solution=np.asarray(
                (1.0 + 1e-3 * local_row_i)
                + 1j * (0.5 + 5e-4 * local_row_i[::-1]),
                dtype=np.complex128,
            ) / math.sqrt(n_i),
            boundary_layout=local_layouts[6],
            face_i=face_i,
            face_j=face_j,
            boundary_quadrature_degree=60,
            batch_modes=64,
            verify_analytic_full_rows=True,
        )
    except Exception as exc:
        local_cases.append({
            "degree": 6, "side": "bottom", "case_status": "FAILED_LOCAL_PROBE",
            "error_type": type(exc).__name__, "error": str(exc),
            "volume_source": "new one-cell p6 physical volume tensor, assembled once",
            "boundary_quadrature_degree": 60,
            "mode_count_full_ordered": len(modes),
        })
        return write_checkpoint("CONTROLLED_NEGATIVE_BOTTOM_P6_OBJECT", p6_started=True)
    for key, value in p6_result.pop("arrays").items():
        witness_arrays[f"p6_q60_bottom_{key}"] = value
    p6_result.update({
        "degree": 6,
        "side": "bottom",
        "case_status": "PASS" if _v10_local_case_pass(p6_result) else "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
        "volume_source": "new one-cell p6 physical volume tensor, assembled once",
        "boundary_quadrature_degree": 60,
    })
    local_cases.append(p6_result)
    # A numerical gate failure on top/p4-bottom must not suppress independent p6-bottom.
    return write_checkpoint("BOTTOM_CONTINUATION_COMPLETE", p6_started=True)


def _make_element(degree: int = 6):
    import basix.ufl

    return basix.ufl.element("N1curl", "hexahedron", degree).basix_element


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", type=Path, default=MODE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--v10-a-saved-array-extension",
        action="store_true",
        help="reuse the hash-bound W1/V9 arrays, qualify q60, then run p4-reuse and p6 top/bottom",
    )
    parser.add_argument(
        "--v10-a-resume-bottom-from",
        type=Path,
        help="reuse a hash-bound V10 parent checkpoint and compute only bottom p4/p6 objects",
    )
    parser.add_argument("--saved-w1-raw", type=Path, default=SAVED_W1_RAW)
    parser.add_argument("--saved-w9-reference", type=Path, default=SAVED_W9_REFERENCE)
    args = parser.parse_args()
    if args.v10_a_resume_bottom_from is not None:
        if args.v10_a_saved_array_extension:
            parser.error("choose either a fresh V10 extension or a bottom-only checkpoint continuation")
        report = run_v10_bottom_continuation(
            args.output,
            args.v10_a_resume_bottom_from,
            args.modes,
            args.saved_w1_raw,
            args.saved_w9_reference,
        )
        print(json.dumps({
            "status": report["status"],
            "checkpoint_stage": report["checkpoint_stage"],
            "completed_local_objects": report["completed_local_objects"],
            "all_local_equation_gates_pass": report["all_local_equation_gates_pass"],
            "elapsed_monotonic_seconds": report["elapsed_monotonic_seconds"],
            "report": str(args.output / "w1_v10_a_extension_report.json"),
        }, indent=2))
        return 0
    if args.v10_a_saved_array_extension:
        report = run_v10_saved_array_extension(
            args.output, args.modes, args.saved_w1_raw, args.saved_w9_reference
        )
        print(json.dumps({
            "status": report["status"],
            "q60_finite_witness_status": report["q60_finite_witness"]["status"],
            "all_local_equation_gates_pass": report.get("all_local_equation_gates_pass"),
            "elapsed_monotonic_seconds": report["elapsed_monotonic_seconds"],
            "report": str(args.output / "w1_v10_a_extension_report.json"),
        }, indent=2))
        return 0
    report = run(args.output, args.modes)
    print(json.dumps({
        "status": report["status"],
        "maximum_relative_error": report["q30_q60"]["maximum_relative_error"],
        "boundary_gate_pass": report["q30_q60"]["boundary_gate_pass"],
        "elapsed_monotonic_seconds": report["elapsed_monotonic_seconds"],
        "report": str(args.output / "w1_boundary_probe_report.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
