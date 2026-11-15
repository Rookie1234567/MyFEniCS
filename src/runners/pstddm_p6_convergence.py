"""Bounded p6 direct reference cases for the workstation convergence pilot."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import time
from typing import Any, Mapping

MODEL_NAME = "pstddm_p6_convergence_workstation"
TASK_CAP_BYTES = 64 << 30
HOST_RESERVE_BYTES = 380 << 30
DISK_RESERVE_BYTES = 380_000_000_000
STAGING_RESERVE_BYTES = 512 << 20
CASE_SECONDS = 7200
FULL_RESIDUAL_TOLERANCE = 1.0e-10
ITERATIVE_FULL_RESIDUAL_TOLERANCE = 1.0e-8
ENERGY_CLOSURE_TOLERANCE = 1.0e-5
EXPECTED_MODE_COUNT = 612
ITERATIVE_MODE = "pstddm_iterative_diagnostic"
ITERATIVE_CASE_ID = "p6_h10_pstddm_diagnostic_13p5"
DIRECT_RETRY5_CASE_ID = "p6_h10_direct_13p5_retry5"
DIRECT_RETRY5_EVIDENCE_SHA256 = "2ae270fc08e27e8999d99678cf76163b92d87cd691781f4de668232dfefee9df"
DIRECT_RETRY5_REFERENCE = {
    "source_sha": "2d28a7e4bcde4e4aadd621f0e02deceaa6c50ed7",
    "input_sha256": "5ce0d20a2f79093859e45d25176b9b4671216f01cbefd2faeb87e768f9d08de3",
    "evidence": "docs/task40extra_dot_parallel_cloud/pstddm_partition_pilot/workstation_wavelength_pilot/outcomes/records/p6_h10_retry5.json",
}
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
AXIS_BREAKPOINTS_NM = {
    "x": (0.0, 16.5, 33.5, 50.0),
    "y": (0.0, 15.0, 35.0, 50.0),
    "z": (-10.0, 0.0, 120.0, 130.0),
}
CASE_IDS = {10.0: "p6_h10_direct_13p5", 7.5: "p6_h7p5_direct_13p5"}
_INPUT_KEYS = {
    "model", "case_id", "mode", "wavelength_nm", "degree", "h_nm",
    "geometry_identity", "period_x_nm", "period_y_nm", "z_min_nm", "z_max_nm",
    "substrate_thickness_nm", "grating_width_x_nm", "grating_width_y_nm",
    "grating_height_nm", "theta_deg", "phi_deg", "polarization",
    "expected_dtn_mode_count", "full_residual_tolerance", "energy_closure_tolerance",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_case(document: Mapping[str, Any]) -> dict[str, Any]:
    if set(document) != _INPUT_KEYS:
        raise ValueError(f"p6 convergence input keys differ: {sorted(set(document) ^ _INPUT_KEYS)}")
    case = dict(document)
    h_nm = float(case["h_nm"])
    if case["model"] != MODEL_NAME or case["mode"] != "direct":
        raise ValueError("p6 convergence profile accepts direct cases with its exact model marker")
    if h_nm not in CASE_IDS or not re.fullmatch(re.escape(CASE_IDS[h_nm])+r'(?:_retry[1-9][0-9]*)?', str(case['case_id'])):
        raise ValueError("case_id/h_nm is outside the frozen h10/h7.5 direct pair")
    fixed = {
        "wavelength_nm": 13.5, "degree": 6, "geometry_identity": "stationary_centered_17x20x120_period50x50_zm10_130_v1",
        "period_x_nm": 50.0, "period_y_nm": 50.0, "z_min_nm": -10.0, "z_max_nm": 130.0,
        "substrate_thickness_nm": 10.0, "grating_width_x_nm": 17.0,
        "grating_width_y_nm": 20.0, "grating_height_nm": 120.0,
        "theta_deg": 89.0, "phi_deg": 90.0, "polarization": "s",
        "expected_dtn_mode_count": EXPECTED_MODE_COUNT,
        "full_residual_tolerance": FULL_RESIDUAL_TOLERANCE,
        "energy_closure_tolerance": ENERGY_CLOSURE_TOLERANCE,
    }
    for key, expected in fixed.items():
        actual = case[key]
        if isinstance(expected, float):
            try:
                valid = math.isfinite(float(actual)) and math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1.0e-13)
            except (TypeError, ValueError):
                valid = False
        else:
            valid = actual == expected
        if not valid:
            raise ValueError(f"p6 convergence input {key} differs from the frozen identity")
    return case


def _validate_iterative_case(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the one explicitly diagnostic h10 case without widening direct IDs."""
    if set(document) != _INPUT_KEYS:
        raise ValueError(f"p6 iterative input keys differ: {sorted(set(document) ^ _INPUT_KEYS)}")
    case = dict(document)
    if case["mode"] != ITERATIVE_MODE or case["case_id"] != ITERATIVE_CASE_ID:
        raise ValueError("the p6 PSTDDM diagnostic accepts only its exact case ID and mode")
    if float(case["h_nm"]) != 10.0:
        raise ValueError("the p6 PSTDDM diagnostic is frozen to h=10 nm")
    try:
        iterative_tolerance = float(case["full_residual_tolerance"])
    except (TypeError, ValueError) as error:
        raise ValueError("the p6 PSTDDM diagnostic requires its 1e-8 residual tolerance") from error
    if not math.isfinite(iterative_tolerance) or not math.isclose(
        iterative_tolerance, ITERATIVE_FULL_RESIDUAL_TOLERANCE, rel_tol=0.0, abs_tol=1.0e-20
    ):
        raise ValueError("the p6 PSTDDM diagnostic full residual tolerance must be exactly 1e-8")
    direct_identity = dict(case)
    direct_identity["mode"] = "direct"
    direct_identity["case_id"] = CASE_IDS[10.0]
    direct_identity["full_residual_tolerance"] = FULL_RESIDUAL_TOLERANCE
    validated = _validate_case(direct_identity)
    return {
        **validated,
        "case_id": ITERATIVE_CASE_ID,
        "mode": ITERATIVE_MODE,
        "full_residual_tolerance": ITERATIVE_FULL_RESIDUAL_TOLERANCE,
    }


def axis_values_for_h(h_nm: float) -> dict[str, tuple[float, ...]]:
    """Piecewise-ceil axes; h is the maximum coordinate-direction edge length."""
    h_nm = float(h_nm)
    if h_nm not in CASE_IDS:
        raise ValueError("only h=10 nm and h=7.5 nm are qualified")
    result: dict[str, tuple[float, ...]] = {}
    for name, breaks in AXIS_BREAKPOINTS_NM.items():
        values = [float(breaks[0])]
        for low, high in zip(breaks[:-1], breaks[1:]):
            count = max(1, math.ceil((high - low) / h_nm))
            values.extend(
                float(high) if index == count else float(low + (high - low) * index / count)
                for index in range(1, count + 1)
            )
        result[name] = tuple(values)
    return result


def mesh_plan(h_nm: float) -> dict[str, Any]:
    axes = axis_values_for_h(h_nm)
    counts = {name: len(values) - 1 for name, values in axes.items()}
    intervals = {
        name: [max(1, math.ceil((high - low) / float(h_nm))) for low, high in zip(breaks[:-1], breaks[1:])]
        for name, breaks in AXIS_BREAKPOINTS_NM.items()
    }
    return {
        "axis_breakpoints_nm": {name: list(values) for name, values in AXIS_BREAKPOINTS_NM.items()},
        "axis_segment_cell_counts": intervals,
        "axis_cell_counts": [counts["x"], counts["y"], counts["z"]],
        "cells": math.prod(counts.values()),
        "max_axis_edge_nm": max(
            max(high - low for low, high in zip(axes[name][:-1], axes[name][1:]))
            for name in axes
        ),
        "axes_nm": {name: list(values) for name, values in axes.items()},
        "mesh_rule": "boundary_fitted; ceil(each material-aligned interval length / h)",
    }


def build_p6_config(case: Mapping[str, Any], material: Mapping[str, Any]):
    from dataclasses import replace
    from src.common.config_3d import (
        ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        resolve_stage4_full3d_assembly_backend,
    )
    from src.solvers.pstddm_model import make_cfg, workstation_spec_from_material_identity

    spec = workstation_spec_from_material_identity(dict(material))
    cfg = make_cfg("dtn", 6, model_spec=spec)
    axes = axis_values_for_h(float(case["h_nm"]))
    cfg = replace(
        cfg,
        case_name=str(case["case_id"]),
        mesh_target_size=float(case["h_nm"]),
        mesh_spacing_mode="boundary_fitted",
        mesh_axis_cell_counts=tuple(len(axes[name]) - 1 for name in ("x", "y", "z")),
        mesh_axis_x_values=axes["x"],
        mesh_axis_y_values=axes["y"],
        mesh_axis_z_values=axes["z"],
        mesh_axis_z_profile=f"p6_piecewise_ceil_h{str(case['h_nm']).replace('.', 'p')}_v1",
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        stage4_preserve_exact_geometry=True,
        require_full_explicit_residual=True,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        petsc_direct_solver_profile="default",
        petsc_extra_options={**cfg.petsc_extra_options, "pc_factor_mat_solver_type": "mumps"},
        full3d_reference_export=False,
        write_visualization_files=False,
        unique_output=False,
    )
    backend = resolve_stage4_full3d_assembly_backend(cfg, apply=True)
    if backend["actual"] != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND:
        raise RuntimeError("p6 profile did not resolve to assembly-time static condensation")
    if not cfg.stage4_assembly_time_cell_static_condensation:
        raise RuntimeError("p6 static-condensation backend failed to activate its assembly path")
    return cfg


def _mode_record(mode: Any) -> dict[str, Any]:
    def pair(value: complex) -> list[float]:
        z = complex(value)
        return [float(z.real), float(z.imag)]

    def vector(values: Any) -> list[list[float]]:
        return [pair(value) for value in values]

    return {
        "side": str(mode.side), "m": int(mode.m), "n": int(mode.n),
        "polarization": str(mode.polarization), "alpha": pair(mode.alpha),
        "gamma": pair(mode.gamma), "beta": pair(mode.beta),
        "refractive_index": pair(mode.refractive_index),
        "vertical_sign": int(mode.vertical_sign), "e_vector": vector(mode.e_vector),
        "k_vector": vector(mode.k_vector), "h_vector": vector(mode.h_vector),
        "electric_tangential_norm_sq": float(mode.electric_tangential_norm_sq),
        "power_per_unit_amplitude": float(mode.power_per_unit_amplitude),
        "propagating": bool(mode.propagating), "rayleigh_warning": bool(mode.rayleigh_warning),
    }


def _mode_inventory(cfg) -> dict[str, Any]:
    from src.common.modes_3d import outgoing_port_modes_3d

    records = [_mode_record(mode) for mode in outgoing_port_modes_3d(cfg)]
    if len(records) != EXPECTED_MODE_COUNT:
        raise ValueError(f"generated DtN mode count {len(records)} differs from frozen 612")
    return {
        "count": len(records),
        "propagating": sum(record["propagating"] for record in records),
        "evanescent": sum(not record["propagating"] for record in records),
        "ordered_modes_sha256": _sha256_bytes(_canonical(records)),
        "records": records,
    }


def _physical_identity(cfg, material: Mapping[str, Any], modes: Mapping[str, Any]) -> dict[str, Any]:
    def pair(value: complex) -> list[float]:
        value = complex(value)
        return [float(value.real), float(value.imag)]

    return {
        "wavelength_nm": float(cfg.lambda0),
        "geometry": {
            "period_x_nm": float(cfg.period_x), "period_y_nm": float(cfg.period_y),
            "z_min_nm": float(cfg.domain_z_min), "z_max_nm": float(cfg.domain_z_max),
            "interface_z_nm": float(cfg.interface_z),
            "substrate_thickness_nm": float(cfg.substrate_thickness),
            "grating_width_x_nm": float(cfg.grating_width_x),
            "grating_width_y_nm": float(cfg.grating_width_y),
            "grating_height_nm": float(cfg.grating_height),
        },
        "materials": {
            "source_identity_sha256": material["identity_sha256"],
            "n_air": pair(cfg.n_air), "n_substrate": pair(cfg.n_substrate),
            "n_grating": pair(cfg.n_grating), "mu_r": pair(cfg.mu_r),
            "epsilon_substrate": pair(cfg.eps_substrate),
            "epsilon_grating": pair(cfg.eps_grating),
        },
        "incidence": {
            "theta_deg": float(cfg.incident_theta_deg), "phi_deg": float(cfg.incident_phi_deg),
            "polarization": str(cfg.polarization_kind), "amplitude": pair(cfg.incident_amplitude),
        },
        "ports": {
            "boundary_model": str(cfg.stage4_boundary_model),
            "order_policy": str(cfg.stage4_dtn_order_policy),
            "mode_count": int(modes["count"]),
            "ordered_modes_sha256": str(modes["ordered_modes_sha256"]),
        },
    }


def _assembly_future_bytes(
    plan: Mapping[str, Any], n_aux: int, *, pstddm_iterative: bool = False
) -> tuple[int, dict[str, Any]]:
    nx, ny, nz = (int(value) for value in plan["axis_cell_counts"])
    cells = nx * ny * nz
    degree = 6
    interior = 3 * degree * (degree - 1) ** 2
    trace = 12 * degree**2
    local = interior + trace
    px, py, pz = degree * nx, degree * ny, degree * nz
    independent_rows = 2 * px * py * (pz + 1) + px * py * pz
    boundary_cells = nx * ny
    # Upper estimate for per-cell dense kernel/LU/Schur work plus sparse insertion.
    # The global trace matrix/factor is admitted later from its actual sparse MUMPS symbolic result.
    local_payload = cells * ((local**2 + interior**2 + trace**2) * 16 + trace**2 * 20)
    port_payload = 2 * int(n_aux) * boundary_cells * trace * 20
    vector_payload = 4 * independent_rows * 16
    jit_reserve = 2560 << 20
    estimate = {
        "kind": "local_cell_kernel_payload_and_sparse_insertion_upper_bound",
        "cells": cells, "degree": degree, "local_full_dofs": local,
        "cell_interior_dofs": interior, "cell_trace_dofs": trace,
        "expected_independent_fe_rows": independent_rows,
        "port_modes": int(n_aux), "boundary_cells_per_port": boundary_cells,
        "local_cell_payload_bytes": local_payload,
        "port_support_insertion_bytes": port_payload,
        "full_field_vector_slots_bytes": vector_payload,
        "native_jit_reserve_bytes": jit_reserve,
        "global_sparse_factor_estimate": "not estimated here; requires actual MUMPS symbolic INFOG",
    }
    direct_peak = local_payload + port_payload + vector_payload + jit_reserve
    estimate["future_bytes"] = direct_peak
    if pstddm_iterative:
        # Keep the original direct Stage-4 pre-assembly gate. Subsequent
        # allocations are gated at their actual lifetime boundaries by the
        # native callback, using the live cgroup baseline and only incremental
        # bytes. The old dense local^2/interior^2/trace^2 term described
        # cell-local condensation objects that this uncondensed route never
        # constructs.
        estimate.update(
            {
                "direct_assembly_peak_estimate_bytes": direct_peak,
                "pstddm_diagnostic_initial_stage_future_bytes": direct_peak,
                "pstddm_diagnostic_resource_gate_lifecycle": [
                    {
                        "stage": "Stage4_base_FE_assembly",
                        "admission": "existing direct_peak pre-assembly bound",
                        "future_bytes": direct_peak,
                        "already_resident_objects_recounted": False,
                    },
                    {
                        "stage": "full_FE_mass_PETSc_assembly",
                        "admission": "native structural-support PETSc bound before matrix assembly",
                        "future_bytes": "incremental PETSc matrix and assembly workspace only",
                    },
                    {
                        "stage": "full_FE_mass_CSR_copy",
                        "admission": "actual PETSc nz_used before CSR copy",
                        "future_bytes": "new CSR copy only; PETSc matrix is live baseline",
                    },
                    {
                        "stage": "full_FE_mass_Floquet_transform",
                        "admission": "actual CSR nnz and Floquet expansion bound",
                        "future_bytes": "transform intermediate, result, and workspace; raw CSR is live baseline",
                    },
                    {
                        "stage": "four_layer_mass_and_beta_matrices",
                        "admission": "per-layer cell-support bounds before retaining eight CSR matrices",
                        "future_bytes": "new layer matrices and one assembly workspace",
                    },
                    {
                        "stage": "each_N4_local_pair_assembly_and_factor",
                        "admission": "local mesh support before L assembly, actual S C D S^H rank-support before terminal update, then actual free-matrix nnz and MUMPS symbolic bounds",
                        "future_bytes": "new pair matrix or factor phase only; resident earlier factors are cgroup baseline",
                        "dense_local_square_bound_used": False,
                    },
                    {
                        "stage": "condensed_Stage4_operator_CSR_copy",
                        "admission": "actual PETSc nz_used before conversion",
                        "future_bytes": "new CSR copy and conversion workspace only",
                    },
                ],
                "n4_dense_cell_condensation_payload_included": False,
                "pstddm_diagnostic_peak_estimate_bytes": "phase-gated; no fictitious all-phase sum",
                "future_bytes": direct_peak,
            }
        )
    return estimate["future_bytes"], estimate


def _original_residual_record(summary: Mapping[str, Any]) -> Mapping[str, Any] | None:
    audit = summary.get("cell_static_condensation")
    if not isinstance(audit, Mapping):
        return None
    full = audit.get("full_explicit_true_residual")
    if not isinstance(full, Mapping):
        return None
    original = full.get("original_full_augmented_residual")
    return original if isinstance(original, Mapping) else None


def _direct_gates(summary: Mapping[str, Any]) -> dict[str, Any]:
    original = _original_residual_record(summary)
    residual = None
    if original is not None:
        try:
            value = float(original["relative_residual"])
            residual = value if math.isfinite(value) else None
        except (KeyError, TypeError, ValueError):
            residual = None
    mumps = str(summary.get("actual_pc_factor_solver_type", "")).lower() == "mumps"
    converged = summary.get("ksp_converged") is True
    numerical_pass = bool(mumps and converged and residual is not None and residual <= FULL_RESIDUAL_TOLERANCE)
    rta = {}
    for name in ("R_total", "T_total", "A_volume_total"):
        try:
            value = float(summary[name])
            rta[name] = value if math.isfinite(value) else None
        except (KeyError, TypeError, ValueError):
            rta[name] = None
    computed_closure = None
    reported_closure = None
    if all(value is not None for value in rta.values()):
        computed_closure = rta["R_total"] + rta["T_total"] + rta["A_volume_total"] - 1.0
    try:
        value = float(summary["energy_closure_error_port_volume"])
        reported_closure = value if math.isfinite(value) else None
    except (KeyError, TypeError, ValueError):
        pass
    physical_pass = bool(
        computed_closure is not None and reported_closure is not None
        and abs(computed_closure) <= ENERGY_CLOSURE_TOLERANCE
        and math.isclose(computed_closure, reported_closure, rel_tol=0.0, abs_tol=1.0e-12)
    )
    return {
        "numerical_pass": numerical_pass,
        "mumps_factor_solver": mumps,
        "ksp_converged": converged,
        "original_full_augmented_residual_relative": residual,
        "original_residual_record_passed_field_not_used_as_threshold": (
            None if original is None else original.get("passed")
        ),
        "required_full_residual_tolerance": FULL_RESIDUAL_TOLERANCE,
        "physical_pass": physical_pass,
        **rta,
        "computed_energy_closure": computed_closure,
        "reported_energy_closure_port_volume": reported_closure,
        "required_energy_closure_tolerance": ENERGY_CLOSURE_TOLERANCE,
        "solver_lossless_energy_boolean_used": False,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_direct_retry5_reference(repository_root: Path) -> dict[str, Any]:
    """Load the tracked compact retry5 record and bind its identity by SHA256."""
    path = Path(repository_root) / DIRECT_RETRY5_REFERENCE["evidence"]
    if not path.is_file():
        raise FileNotFoundError(f"tracked direct retry5 evidence is missing: {path}")
    actual_hash = _sha256_file(path)
    if actual_hash != DIRECT_RETRY5_EVIDENCE_SHA256:
        raise RuntimeError("tracked direct retry5 compact evidence hash does not match the frozen receipt")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    expected_identity = {
        "schema": "pstddm.p6.retry5.independent_receipt_audit.v1",
        "run_id": DIRECT_RETRY5_CASE_ID,
        "classification": "DIRECT_NUMERICAL_FAIL",
        "source_sha": DIRECT_RETRY5_REFERENCE["source_sha"],
        "input_sha256": DIRECT_RETRY5_REFERENCE["input_sha256"],
    }
    if any(evidence.get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError("tracked direct retry5 compact evidence identity differs from its frozen receipt")
    threshold = float(evidence["threshold"])
    residual = float(evidence["full_residual"])
    if not (math.isfinite(threshold) and threshold == FULL_RESIDUAL_TOLERANCE
            and math.isfinite(residual) and residual > threshold):
        raise RuntimeError("direct retry5 evidence no longer records its failed 1e-10 residual gate")
    physical = evidence.get("diagnostic_physical")
    if not isinstance(physical, Mapping):
        raise RuntimeError("direct retry5 evidence has no diagnostic physical record")
    result = {key: float(physical[key]) for key in (
        "R_total", "T_total", "A_volume_total", "energy_closure_error_port_volume"
    )}
    if not all(math.isfinite(value) for value in result.values()):
        raise RuntimeError("direct retry5 physical record contains non-finite values")
    closure = result["R_total"] + result["T_total"] + result["A_volume_total"] - 1.0
    if not math.isclose(closure, result["energy_closure_error_port_volume"], rel_tol=0.0, abs_tol=1.0e-12):
        raise RuntimeError("direct retry5 physical power and volume closure do not agree")
    receipt = evidence.get("receipt_hashes", {}).get("run_summary.json", {})
    run_summary_hash = receipt.get("sha256")
    if (not isinstance(run_summary_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", run_summary_hash)
            or receipt.get("matches_supervisor_inventory") is not True):
        raise RuntimeError("direct retry5 evidence lacks a verified run_summary.json receipt")
    return {
        **result,
        "source_sha": evidence["source_sha"],
        "input_sha256": evidence["input_sha256"],
        "full_residual": residual,
        "evidence": str(path),
        "evidence_sha256": actual_hash,
        "run_summary_sha256": run_summary_hash,
        "run_summary_bytes": int(receipt["bytes"]),
    }


def _verified_local_reference_run(reference_run: Path, baseline: Mapping[str, Any]) -> tuple[Path | None, dict[str, Any]]:
    summary_path = Path(reference_run) / "run_summary.json"
    if not summary_path.is_file():
        return None, {"status": "not_available", "reason": "local direct run_summary.json is absent"}
    actual_hash = _sha256_file(summary_path)
    if actual_hash != baseline["run_summary_sha256"]:
        return None, {
            "status": "identity_mismatch",
            "reason": "local direct run_summary.json does not match the hash-bound retry5 receipt",
            "actual_run_summary_sha256": actual_hash,
            "required_run_summary_sha256": baseline["run_summary_sha256"],
        }
    return Path(reference_run), {
        "status": "verified",
        "run_summary_sha256": actual_hash,
        "run_summary_bytes": summary_path.stat().st_size,
    }


def _compare_same_discrete_fields(candidate_run: Path, reference_run: Path) -> dict[str, Any]:
    """Stream fixed common-sample arrays and apply the frozen p6 E/H limits."""
    import numpy as np

    roots = [Path(candidate_run) / "common_field_samples", Path(reference_run) / "common_field_samples"]
    if not all(root.is_dir() and (root / "manifest.json").is_file() for root in roots):
        return {
            "status": "not_available",
            "reason": "same-discrete common_field_samples are absent in one or both local run directories",
            "remote_access_attempted": False,
            "field_errors": None,
        }
    manifests = [json.loads((root / "manifest.json").read_text(encoding="utf-8")) for root in roots]
    keys = ("count", "order", "axes", "H_definition")
    if any(manifests[0][key] != manifests[1][key] for key in keys):
        return {"status": "identity_mismatch", "same_discrete_samples": False, "field_errors": None}
    for root, manifest in zip(roots, manifests, strict=True):
        for name, item in manifest.get("files", {}).items():
            path = root / name
            if not path.is_file() or _sha256_file(path) != item.get("sha256"):
                return {
                    "status": "hash_mismatch",
                    "same_discrete_samples": True,
                    "bad_file": str(path),
                    "field_errors": None,
                }
    count = int(manifests[0]["count"])
    data = [
        {
            name: np.load(root / f"{name}.npy", mmap_mode="r")
            for name in ("E", "H", "E_scattered", "H_scattered", "points", "weights")
        }
        for root in roots
    ]
    accumulators = {name: [0.0, 0.0] for name in ("E", "H", "E_scattered", "H_scattered")}
    for start in range(0, count, 8192):
        block = slice(start, min(start + 8192, count))
        if not np.array_equal(data[0]["points"][block], data[1]["points"][block]):
            return {"status": "point_mismatch", "same_discrete_samples": True, "field_errors": None}
        if not np.array_equal(data[0]["weights"][block], data[1]["weights"][block]):
            return {"status": "weight_mismatch", "same_discrete_samples": True, "field_errors": None}
        weights = data[1]["weights"][block, None]
        for name, (difference_sum, reference_sum) in accumulators.items():
            candidate = data[0][name][block]
            reference = data[1][name][block]
            difference_sum += float(np.sum(weights * np.abs(candidate - reference) ** 2))
            reference_sum += float(np.sum(weights * np.abs(reference) ** 2))
            accumulators[name] = [difference_sum, reference_sum]
    limits = {"E": 1.0e-4, "E_scattered": 1.0e-4, "H": 1.0e-3, "H_scattered": 1.0e-3}
    fields = {}
    for name, (difference_sum, reference_sum) in accumulators.items():
        relative = float(np.sqrt(difference_sum / reference_sum)) if reference_sum > 0.0 else None
        fields[name] = {
            "relative_l2": relative,
            "limit": limits[name],
            "passed": relative is not None and relative <= limits[name],
            "difference_squared": difference_sum,
            "reference_squared": reference_sum,
        }
    return {
        "status": "compared",
        "same_discrete_samples": True,
        "count": count,
        "chunk_size": 8192,
        "fields": fields,
        "passed": all(value["passed"] for value in fields.values()),
        "reference_run": str(reference_run),
    }


def _iterative_gates(
    summary: Mapping[str, Any], output: Path, repository_root: Path | None = None
) -> dict[str, Any]:
    """Recompute the diagnostic residual and same-discrete physical comparison gates."""
    original = _original_residual_record(summary)
    residual = None
    if original is not None:
        try:
            value = float(original["relative_residual"])
            residual = value if math.isfinite(value) and value >= 0.0 else None
        except (KeyError, TypeError, ValueError):
            residual = None
    residual_pass = residual is not None and residual <= ITERATIVE_FULL_RESIDUAL_TOLERANCE

    metrics: dict[str, float | None] = {}
    for name in ("R_total", "T_total", "A_volume_total"):
        try:
            value = float(summary[name])
            metrics[name] = value if math.isfinite(value) else None
        except (KeyError, TypeError, ValueError):
            metrics[name] = None
    computed_closure = (
        metrics["R_total"] + metrics["T_total"] + metrics["A_volume_total"] - 1.0
        if all(metrics[name] is not None for name in metrics)
        else None
    )
    try:
        reported_closure_value = float(summary["energy_closure_error_port_volume"])
        reported_closure = reported_closure_value if math.isfinite(reported_closure_value) else None
    except (KeyError, TypeError, ValueError):
        reported_closure = None
    physical_pass = bool(
        computed_closure is not None and reported_closure is not None
        and abs(computed_closure) <= ENERGY_CLOSURE_TOLERANCE
        and math.isclose(computed_closure, reported_closure, rel_tol=0.0, abs_tol=1.0e-12)
    )
    root = Path(repository_root) if repository_root is not None else Path(__file__).resolve().parents[2]
    direct = _load_direct_retry5_reference(root)
    power_differences = {
        name: (None if metrics[name] is None else abs(metrics[name] - float(direct[name])))
        for name in ("R_total", "T_total", "A_volume_total")
    }
    power_pass = all(value is not None and value <= 1.0e-4 for value in power_differences.values())
    reference_run = output.parent / DIRECT_RETRY5_CASE_ID
    verified_reference, reference_identity = _verified_local_reference_run(reference_run, direct)
    if reference_identity["status"] == "identity_mismatch":
        field_comparison = {
            "status": "identity_mismatch",
            "reason": reference_identity["reason"],
            "reference_run_identity": reference_identity,
            "field_errors": None,
        }
    elif verified_reference is None:
        field_comparison = {
            "status": "not_available",
            "reason": reference_identity["reason"],
            "remote_access_attempted": False,
            "field_errors": None,
        }
    else:
        field_comparison = _compare_same_discrete_fields(output, verified_reference)
    field_status = field_comparison.get("status")
    if field_status == "compared":
        comparison_pass: bool | None = bool(field_comparison["passed"])
    elif field_status in {"not_available"}:
        comparison_pass = None
    else:
        comparison_pass = False
    core_pass = bool(residual_pass and physical_pass and power_pass)
    gate_pass = (
        False if not core_pass else
        (bool(comparison_pass) if comparison_pass is not None else None)
    )
    return {
        "diagnostic_only": True,
        "official_result": False,
        "original_full_augmented_residual_relative": residual,
        "required_iterative_full_residual_tolerance": ITERATIVE_FULL_RESIDUAL_TOLERANCE,
        "baseline_direct_residual_relative": direct["full_residual"],
        "baseline_direct_residual_passed_direct_1e10": False,
        "residual_gate_pass": bool(residual_pass),
        "original_residual_record_passed_field_not_used_as_threshold": (
            None if original is None else original.get("passed")
        ),
        "physical_gate_pass": physical_pass,
        **metrics,
        "computed_energy_closure": computed_closure,
        "reported_energy_closure_port_volume": reported_closure,
        "required_energy_closure_tolerance": ENERGY_CLOSURE_TOLERANCE,
        "same_discrete_direct_power_absolute_differences": power_differences,
        "same_discrete_direct_power_difference_limit": 1.0e-4,
        "same_discrete_power_gate_pass": bool(power_pass),
        "same_discrete_mesh": True,
        "same_discrete_field_comparison": field_comparison,
        "field_comparison_gate_pass": comparison_pass,
        "diagnostic_gate_pass": gate_pass,
        "comparison_incomplete_reason": (
            field_comparison.get("reason") if comparison_pass is None else None
        ),
        "baseline_identity": {
            "case_id": DIRECT_RETRY5_CASE_ID,
            "source_sha": direct["source_sha"],
            "input_sha256": direct["input_sha256"],
            "evidence": direct["evidence"],
            "evidence_sha256": direct["evidence_sha256"],
            "run_summary_sha256": direct["run_summary_sha256"],
            "local_reference_run_summary": reference_identity,
        },
    }


def _bind_iterative_full_residual_audit(summary: Mapping[str, Any], output: Path) -> dict[str, Any]:
    """Attach the post-Stage4 native full residual to the callback audit record."""
    from src.common.strict_json import atomic_json

    original = _original_residual_record(summary)
    residual = None
    if original is not None:
        try:
            value = float(original["relative_residual"])
            residual = value if math.isfinite(value) and value >= 0.0 else None
        except (KeyError, TypeError, ValueError):
            residual = None
    audit_path = Path(output) / "pstddm_stage4_diagnostic.json"
    if not audit_path.is_file():
        raise FileNotFoundError("Stage-4 diagnostic callback did not write its audit record")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    gate_pass = residual is not None and residual <= ITERATIVE_FULL_RESIDUAL_TOLERANCE
    audit["post_stage4_native_original_full_augmented_residual"] = {
        "relative_residual": residual,
        "required_tolerance": ITERATIVE_FULL_RESIDUAL_TOLERANCE,
        "passed": bool(gate_pass),
        "source": "solver_summary.cell_static_condensation.full_explicit_true_residual.original_full_augmented_residual",
        "original_record_passed_field_used_as_gate": False,
    }
    audit["official_result"] = False
    audit["diagnostic_only"] = True
    atomic_json(audit_path, audit)
    return audit["post_stage4_native_original_full_augmented_residual"]


def _actual_mesh_axes(mesh_data) -> dict[str, tuple[float, ...]]:
    import numpy as np

    coordinates = np.asarray(mesh_data.mesh.geometry.x, dtype=np.float64)
    result = {}
    for name, column in zip(("x", "y", "z"), range(3), strict=True):
        ordered = np.sort(coordinates[:, column])
        values = [float(ordered[0])]
        for value in ordered[1:]:
            if float(value) - values[-1] > 1.0e-10:
                values.append(float(value))
        result[name] = tuple(values)
    return result


def _axes_match(actual: Mapping[str, tuple[float, ...]], expected: Mapping[str, tuple[float, ...]]) -> bool:
    import numpy as np

    return all(
        len(actual[name]) == len(expected[name])
        and np.allclose(actual[name], expected[name], rtol=0.0, atol=1.0e-10)
        for name in ("x", "y", "z")
    )


def _mem_available_bytes() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is not readable")


def qualified_mumps_compiler_command():
    """Select only the current qualified prefix compiler; leave FFCx/sysconfig untouched."""
    import sys
    if os.environ.get('_MYFENICS_CLOUD_QUALIFIED_ACTIVATION') != '1':
        raise RuntimeError('qualified native activation required for MUMPS compiler')
    prefix = Path(sys.prefix).resolve(strict=True)
    compiler = prefix/'bin/x86_64-conda-linux-gnu-cc'
    sysroot = prefix/'x86_64-conda-linux-gnu/sysroot'
    if (not compiler.is_file() or not os.access(compiler, os.X_OK)
            or not compiler.resolve().is_relative_to(prefix/'bin')
            or not sysroot.is_dir() or not sysroot.resolve().is_relative_to(prefix)):
        raise RuntimeError('qualified prefix compiler/sysroot missing or escaped')
    return (str(compiler), '--sysroot='+str(sysroot), '-pthread')


def _admission_callback(output: Path, scope_root: Path, preparation_cgroup: str, started: float):
    from src.common.strict_json import atomic_json
    from src.runners.pstddm_workstation_case import validate_workstation_cgroup
    from benchmarks.pstddm_partition_pilot.supervise import _workstation_cgroup

    events: list[dict[str, Any]] = []
    def admit(stage: str, future_bytes: int, *, estimate_basis: Any) -> dict[str, Any]:
        elapsed = time.monotonic() - started
        if elapsed >= CASE_SECONDS:
            raise TimeoutError("p6 direct case reached its 7200 s wall limit")
        active_path, facts = _workstation_cgroup()
        available = _mem_available_bytes()
        disk_free = shutil.disk_usage(scope_root).free
        observation = {
            "stage": stage, "elapsed_seconds": elapsed,
            "active_cgroup_path": str(active_path),
            "effective_cap_bytes": int(facts["memory_max_bytes"]),
            "live_tree_and_supervisor_bytes": int(facts["memory_current_bytes"]),
            "task_swap_current_bytes": int(facts["swap_current_bytes"]),
            "task_swap_max_bytes": int(facts["swap_max_bytes"]),
            "ancestors": facts.get("ancestors", []),
            "future_bytes": int(future_bytes),
            "margin_bytes": STAGING_RESERVE_BYTES,
            "system": {"available": int(available)},
            "available_floor_bytes": HOST_RESERVE_BYTES,
            "mumps_task_limit_bytes": TASK_CAP_BYTES,
            "future_co_resident_reserve_bytes": 4 << 30,
            "disk_free_bytes": int(disk_free),
            "disk_reserve_bytes": DISK_RESERVE_BYTES,
            "estimate_basis": estimate_basis,
        }
        events.append(observation)
        atomic_json(output / "resource_admission.json", events)
        print(json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
        validate_workstation_cgroup(
            str(active_path), facts, preparation_cgroup,
            reserve_bytes=STAGING_RESERVE_BYTES, future_bytes=int(future_bytes),
            tree_limit_bytes=TASK_CAP_BYTES,
        )
        if available - int(future_bytes) - STAGING_RESERVE_BYTES < HOST_RESERVE_BYTES:
            raise MemoryError("future allocation would cross the 380 GiB host reserve")
        if disk_free < DISK_RESERVE_BYTES:
            raise OSError("p6 direct case would cross the 380 GB disk reserve")
        return observation
    return admit


def _run_p6_stage4_solver(cfg, output: Path, observer, *, linear_solver_port=None):
    """Call Stage 4 with the p6 incident-RHS quadrature used by its residual gate."""
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    return run_stage4b_block_grating_3d_case(
        cfg,
        output,
        solution_observer=observer,
        diagnostic_reference_incident_quadrature=True,
        linear_solver_port=linear_solver_port,
    )


def run_p6_convergence_case(input_path: str | Path, dry_run: bool = False) -> dict[str, Any]:
    try:
        return _run_p6_convergence_case(input_path, dry_run)
    except BaseException as exc:
        output_text = os.environ.get("PSTDDM_WORKSTATION_OUTPUT")
        if not dry_run and output_text:
            path = Path(output_text) / "run_manifest.json"
            if path.is_file():
                from src.common.strict_json import atomic_json
                record = json.loads(path.read_text())
                record.update(status="FAILED", error_type=type(exc).__name__, error=str(exc))
                atomic_json(path, record)
        raise


def _run_p6_convergence_case(input_path: str | Path, dry_run: bool = False) -> dict[str, Any]:
    """Run a p6 direct reference or the one explicit source-transfer diagnostic."""
    from src.io.input_loader import load_dat_input
    from src.solvers.pstddm_material import derive_si_optical_identity
    from src.common.config_3d import resolve_stage4_full3d_assembly_backend

    loaded = load_dat_input(input_path)
    iterative = loaded.document.get("mode") == ITERATIVE_MODE
    case = _validate_iterative_case(loaded.document) if iterative else _validate_case(loaded.document)
    material = derive_si_optical_identity(float(case["wavelength_nm"]))
    cfg = build_p6_config(case, material)
    modes = _mode_inventory(cfg)
    plan = mesh_plan(float(case["h_nm"]))
    if dry_run:
        initial_stage_future, resource_estimate = _assembly_future_bytes(
            plan, modes["count"], pstddm_iterative=iterative
        )
        return {
            "status": "VALID_CONFIGURATION_NOT_RUN", "model": MODEL_NAME,
            "case": case, "material_identity": material, "mode_inventory": modes,
            "mesh_plan": plan, "assembly_backend": resolve_stage4_full3d_assembly_backend(cfg),
            "config": cfg.as_jsonable(),
            "initial_stage_future_bytes": int(initial_stage_future),
            "resource_estimate": resource_estimate,
            "execution_command": (
                "python scripts/run_case.py <p6-h10-pstddm-diagnostic-input.dat>"
                if iterative else "python scripts/run_case.py <p6-direct-input.dat>"
            ),
            "diagnostic_only": bool(iterative),
            "official_result": False if iterative else None,
        }
    if not __debug__ or os.environ.get("PYTHONOPTIMIZE"):
        raise RuntimeError("optimization mode is forbidden for resource-admitted p6 direct runs")
    if os.environ.get("PSTDDM_WORKSTATION_SUPERVISOR_PID") != str(os.getppid()):
        raise RuntimeError("p6 direct cases require supervise.py --profile workstation-p6")
    scope_root = Path(os.environ["PSTDDM_WORKSTATION_SCOPE_ROOT"]).resolve(strict=True)
    output = Path(os.environ["PSTDDM_WORKSTATION_OUTPUT"]).resolve(strict=True)
    from src.runners.pstddm_workstation_case import (
        THREAD_VARIABLES as _OLD_THREADS,
        qualified_native_runtime_receipt,
        validate_supervisor_handoff,
    )
    validate_supervisor_handoff(
        loaded.source_path, str(case["case_id"]), loaded.input_sha256,
        scope_root, output, parent_pid=os.getppid(),
    )
    runtime = qualified_native_runtime_receipt(scope_root)
    if any(os.environ.get(name) != "1" for name in (*THREAD_VARIABLES, *_OLD_THREADS)):
        raise RuntimeError("all mathematics thread variables must equal one")
    from benchmarks.pstddm_partition_pilot.supervise import _workstation_cgroup
    active_path, facts = _workstation_cgroup()
    if str(active_path) != runtime["active_cgroup_path"]:
        raise RuntimeError("active cgroup differs from the qualified runtime receipt")
    if int(facts["memory_max_bytes"]) != TASK_CAP_BYTES or int(facts["swap_max_bytes"]) != 0:
        raise RuntimeError("workstation-p6 cgroup must be 64 GiB with swap disabled")
    if shutil.disk_usage(scope_root).free < DISK_RESERVE_BYTES:
        raise OSError("less than 380 GB remains before p6 case start")

    from src.common.strict_json import atomic_json, snapshot
    from src.common.runtime_resource_policy import resource_policy
    from src.geometry.mesh_builder_3d import stage4_axis_plan

    axes_by_h = {}
    for h in CASE_IDS:
        sibling = build_p6_config({**case, "h_nm": h, "case_id": CASE_IDS[h]}, material)
        axis_plan = stage4_axis_plan(sibling, comm_size=1)
        axes_by_h[h] = {
            "x": tuple(float(value) for value in axis_plan.x_values),
            "y": tuple(float(value) for value in axis_plan.y_values),
            "z": tuple(float(value) for value in axis_plan.z_values),
        }
        if not _axes_match(axes_by_h[h], {name: tuple(plan_values) for name, plan_values in axis_values_for_h(h).items()}):
            raise RuntimeError(f"Stage-4 mesh planner differs from the frozen h={h:g} interval plan")
    mode_path = output / "mode_inventory.json"
    atomic_json(mode_path, modes)
    config_payload = cfg.as_jsonable()
    atomic_json(output / "resolved_config.json", config_payload)
    atomic_json(output / "material_identity.json", material)
    physical = _physical_identity(cfg, material, modes)
    manifest = {
        "schema": (
            "pstddm.p6.iterative_diagnostic.run.v1"
            if iterative else "pstddm.p6.direct.run.v1"
        ), "model": MODEL_NAME,
        "case_id": case["case_id"], "status": "running",
        "source_sha": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip(),
        "input_path": str(loaded.source_path), "input_sha256": loaded.input_sha256,
        "config_sha256": _sha256_bytes(_canonical(config_payload)),
        "physical_identity": physical, "physical_identity_sha256": _sha256_bytes(_canonical(physical)),
        "material_identity_sha256": material["identity_sha256"],
        "mode_inventory_sha256": modes["ordered_modes_sha256"],
        "mesh_plan": plan, "assembly_backend": "assembly_time_static_condensed",
        "solver": (
            "full-FE PureSourceTransfer initial sweep and right FGMRES; one bounded global mass factor plus three bounded local pair factors"
            if iterative else "PETSc LU with explicitly selected MUMPS; bounded exact symbolic preflight"
        ),
        "solver_profile": ITERATIVE_MODE if iterative else "direct",
        "diagnostic_only": bool(iterative),
        "official_result": False if iterative else None,
        "full_explicit_residual_required": True,
        "full_residual_tolerance": (
            ITERATIVE_FULL_RESIDUAL_TOLERANCE if iterative else FULL_RESIDUAL_TOLERANCE
        ),
        "energy_closure_tolerance": ENERGY_CLOSURE_TOLERANCE,
        "resource_limits": {
            "task_cap_bytes": TASK_CAP_BYTES, "host_reserve_bytes": HOST_RESERVE_BYTES,
            "disk_reserve_bytes": DISK_RESERVE_BYTES, "staging_reserve_bytes": STAGING_RESERVE_BYTES,
            "case_wall_seconds": CASE_SECONDS,
        },
        "global_full_FE_matrix_exported": False,
        "condensed_matrix_checkpoint_enabled": False,
        "visualization_files_enabled": False,
        "solution_observer": "common p6 physical quadrature samples; no VTU interpolation",
        "jit_cache_donor": None if iterative else "not_applicable",
        "jit_cache_reused": False if iterative else None,
    }
    quadrature_receipt_path = output / "incident_traction_quadrature_receipt.json"
    quadrature_receipt = {
        "schema": "pstddm.p6.incident_traction_quadrature_request.v1",
        "status": "request_frozen_before_solver_invocation",
        "diagnostic_reference_incident_quadrature": True,
        "quadrature_degree": int(cfg.stage4_dtn_quadrature_degree),
        "quadrature_rule": "explicit_degree",
        "reason": "match the incident RHS quadrature used by the full augmented residual check",
        "old_default_preserved_for_other_callers": True,
    }
    atomic_json(quadrature_receipt_path, quadrature_receipt)
    manifest["incident_traction_quadrature_receipt"] = {
        "relative_path": quadrature_receipt_path.name,
        "sha256": hashlib.sha256(quadrature_receipt_path.read_bytes()).hexdigest(),
        "diagnostic_reference_incident_quadrature": True,
        "quadrature_degree": int(cfg.stage4_dtn_quadrature_degree),
    }
    atomic_json(output / "run_manifest.json", manifest)
    started = time.monotonic()
    admit = _admission_callback(output, scope_root, runtime["preparation_cgroup"]["path"], started)
    future, estimate = _assembly_future_bytes(
        plan, modes["count"], pstddm_iterative=iterative
    )
    compiler = qualified_mumps_compiler_command()
    with resource_policy(admit, disk_reserve_bytes=DISK_RESERVE_BYTES, factor_checkpoint=False,
                         mumps_compiler_command=compiler):
        admit('public_mumps_bridge_before_FE', 256 << 20,
              estimate_basis='small compiled public PETSc API bridge, before mesh/form/assembly')
        from src.solvers.bounded_mumps import load_public_shim
        import sysconfig
        original_cc = sysconfig.get_config_var('CC')
        shim_started = time.monotonic()
        _api, shim_identity = load_public_shim(output/'mumps_symbolic', compiler_command=compiler)
        if sysconfig.get_config_var('CC') != original_cc:
            raise RuntimeError('MUMPS bridge unexpectedly changed FFCx compiler policy')
        atomic_json(output/'mumps_compiler_preflight.json', {
            'status':'PUBLIC_API_ABI_PASS_BEFORE_FE_NOT_FACTOR_QUALIFICATION',
            'elapsed_seconds':time.monotonic()-shim_started,
            'compiler':list(compiler), 'original_sysconfig_CC':original_cc,
            'sysconfig_unchanged':True, 'identity':shim_identity,
        })
        manifest['mumps_compiler_preflight'] = {
            'path':str(output/'mumps_compiler_preflight.json'),
            'sha256':hashlib.sha256((output/'mumps_compiler_preflight.json').read_bytes()).hexdigest(),
            'status':'PUBLIC_API_ABI_PASS_BEFORE_FE_NOT_FACTOR_QUALIFICATION',
        }
        atomic_json(output/'run_manifest.json', manifest)
        admit("before_local_static_condensation_assembly", future, estimate_basis=estimate)

        linear_solver_port = None
        if iterative:
            from src.solvers.pstddm_stage4_hook import make_p6_h10_source_transfer_port

            def observe(stage):
                return admit(
                    str(stage), 0,
                    estimate_basis={"kind": "live MUMPS phase resource observation"},
                )

            linear_solver_port = make_p6_h10_source_transfer_port(
                output_directory=str(output),
                admit=admit,
                observe=observe,
                available_floor_bytes=HOST_RESERVE_BYTES,
                task_limit_bytes=TASK_CAP_BYTES,
                compiler_command=compiler,
            )

        def observer(*, field, mesh_data, config, **_kwargs):
            actual = _actual_mesh_axes(mesh_data)
            expected = {name: tuple(values) for name, values in axis_values_for_h(float(case["h_nm"])).items()}
            if not _axes_match(actual, expected):
                raise RuntimeError("actual solved mesh axes differ from the frozen piecewise h plan")
            axis_pair = [
                (actual["x"], actual["y"], actual["z"])
                if float(case["h_nm"]) == h
                else (axes_by_h[h]["x"], axes_by_h[h]["y"], axes_by_h[h]["z"])
                for h in (10.0, 7.5)
            ]
            from src.postprocessing.pstddm_p6_convergence import save_common_field_samples
            record = save_common_field_samples(field, config, output, axis_pair)
            atomic_json(output / "common_field_sampling_receipt.json", record)

        result = _run_p6_stage4_solver(
            cfg, output, observer, linear_solver_port=linear_solver_port
        )
    summary = snapshot(result)
    atomic_json(output / "solver_summary.json", summary)
    if iterative:
        _bind_iterative_full_residual_audit(summary, output)
        gates = _iterative_gates(summary, output)
        if gates["diagnostic_gate_pass"] is True:
            status = "PSTDDM_DIAGNOSTIC_GATE_PASS"
        elif gates["diagnostic_gate_pass"] is False:
            status = "PSTDDM_DIAGNOSTIC_GATE_FAIL"
        else:
            status = "PSTDDM_DIAGNOSTIC_COMPLETED_COMPARISON_UNAVAILABLE"
    else:
        gates = _direct_gates(summary)
        numerical = bool(gates["numerical_pass"])
        physical_ok = bool(gates["physical_pass"])
        status = "DIRECT_NUMERICAL_AND_PHYSICAL_PASS" if numerical and physical_ok else (
            "DIRECT_NUMERICAL_PASS_PHYSICAL_FAIL" if numerical else "DIRECT_NUMERICAL_FAIL"
        )
    checkpoint_manifest = output / "pre_factor_checkpoint" / "manifest.json"
    if checkpoint_manifest.is_file():
        checkpoint = json.loads(checkpoint_manifest.read_text(encoding="utf-8"))
        manifest["condensed_sparse_checkpoint"] = {
            "actual_bytes": checkpoint.get("actual_bytes"),
            "matrix": checkpoint.get("matrix"),
            "manifest_sha256": hashlib.sha256(checkpoint_manifest.read_bytes()).hexdigest(),
            "scope": "condensed trace-plus-DtN sparse operator; not the uncondensed global FE matrix",
        }
    manifest.update(
        status=status, completed_wall_seconds=time.monotonic() - started,
        numerical_gate=gates, solver_case_status=summary.get("case_status"),
        solver_official_result=summary.get("official_result"),
        task40_physical_gate_uses_independent_volume_closure=True,
        diagnostic_only=bool(iterative),
        official_result=False if iterative else summary.get("official_result"),
    )
    atomic_json(output / "run_manifest.json", manifest)
    return {"status": status, "case_id": case["case_id"], "numerical_gate": gates,
            "run_manifest": str(output / "run_manifest.json"), "solver_summary": str(output / "solver_summary.json")}
