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
from src.common.config_3d import SimulationConfig3D


MODE_PATH = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json"
W1_ROOT = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w1_wsl"
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
    import basix

    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    side = mode["side"]
    zref = 0.0 if side == "bottom" else 1.0
    tab = layout.polynomial.element.tabulate(
        0, np.column_stack((rule, np.full(len(rule), zref)))
    )[0][:, layout.polynomial.active[side], :2]
    dx = float(layout.x[i + 1] - layout.x[i])
    dy = float(layout.y[j + 1] - layout.y[j])
    z = float(mode["reference_plane_nm"])
    pts = np.column_stack((
        layout.x[i] + dx * rule[:, 0],
        layout.y[j] + dy * rule[:, 1],
        np.full(len(rule), z),
    ))
    kv = np.asarray([zvalue(v) for v in mode["k_vector"]], dtype=np.complex128)
    basis_integral = np.einsum(
        "q,qjc->jc", weights * np.exp(-1j * np.conj(pts @ kv)), tab, optimize=True
    ) * np.asarray([dy, dx])
    local = trace[layout.maps[side][i, j]] * layout.weights[side][i, j]
    return local @ basis_integral


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


def _make_element(degree: int = 6):
    import basix.ufl

    return basix.ufl.element("N1curl", "hexahedron", degree).basix_element


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", type=Path, default=MODE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
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
