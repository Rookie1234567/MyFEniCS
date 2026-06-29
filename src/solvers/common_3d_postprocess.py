from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_scalar_type, fem

from ..common.analytic_fields_3d import electric_field_code_values, fresnel_reference
from ..common.config_3d import SimulationConfig3D
from ..constraints.floquet_3d import DoubleFloquet3DData
from ..geometry.mesh_builder_3d import build_airbox_mesh_3d
from .common_3d_fields import (
    _function_coefficient_norm,
    _interpolated_mode_field,
    _mode_basis,
    _positive_sqrt,
    _sample_field_at_points,
    incident_air_plane_wave_field,
    plane_wave_electric_field,
)
from .solve_vector_maxwell import _json_default
from .common_3d_solve import _create_nedelec_space
from .common_3d_utils import _global_max_rss_mb, _summary_base_fields


def _relative_norm_error(actual: np.ndarray, expected: np.ndarray) -> float:
    diff = actual - expected
    denom = max(float(np.linalg.norm(actual)), float(np.linalg.norm(expected)), 1.0e-30)
    return float(np.linalg.norm(diff) / denom)

def _sample_grid_points(cfg: SimulationConfig3D, z_values: np.ndarray, nx: int = 4, ny: int = 4) -> np.ndarray:
    x_values = np.linspace(cfg.x_min + 0.2 * (cfg.x_max - cfg.x_min), cfg.x_min + 0.8 * (cfg.x_max - cfg.x_min), nx)
    y_values = np.linspace(cfg.y_min + 0.2 * (cfg.y_max - cfg.y_min), cfg.y_min + 0.8 * (cfg.y_max - cfg.y_min), ny)
    points = [[x, y, z] for z in z_values for x in x_values for y in y_values]
    return np.asarray(points, dtype=np.float64)

def _cell_tag_volumes(msh, mesh_data, cfg: SimulationConfig3D) -> dict[str, float]:
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    tag_items = {
        "air": cfg.tags.air,
        "substrate": cfg.tags.substrate,
        "grating": cfg.tags.grating,
        "top_pml": cfg.tags.top_pml,
        "bottom_pml": cfg.tags.bottom_pml,
    }
    volumes: dict[str, float] = {}
    for name, tag in tag_items.items():
        local = fem.assemble_scalar(fem.form(ufl.as_ufl(1.0) * dx(tag)))
        global_value = msh.comm.allreduce(local, op=MPI.SUM)
        volumes[name] = float(np.real(global_value))
    return volumes

def _fit_plane_wave_modes(
    E,
    cfg: SimulationConfig3D,
    points: np.ndarray,
    modes: list[tuple[str, np.ndarray, np.ndarray]],
    *,
    calibrate_fe_response: bool = True,
):
    values = _sample_field_at_points(E, points)
    rows = []
    rhs = []
    for point, value in zip(points, values):
        phase_xy = cfg.kx * point[0] + cfg.ky * point[1]
        for component in range(3):
            rows.append(
                [
                    mode_polarization[component] * np.exp(1j * (phase_xy + mode_k[2] * point[2]))
                    for _, mode_k, mode_polarization in modes
                ]
            )
            rhs.append(value[component])
    A = np.asarray(rows, dtype=np.complex128)
    b = np.asarray(rhs, dtype=np.complex128)
    amplitudes, *_ = np.linalg.lstsq(A, b, rcond=None)
    residual = float(np.linalg.norm(A @ amplitudes - b) / max(float(np.linalg.norm(b)), 1.0e-30))

    if calibrate_fe_response and modes:
        # Point-sampling a low-order Nedelec interpolation of a plane wave can
        # bias modal amplitudes by several percent even when the field itself is
        # the correct FE representation.  Calibrate the fit by measuring how
        # each unit-amplitude mode is seen after interpolation in this exact
        # function space, then invert that small response matrix.
        response_columns = []
        for _, mode_k, mode_polarization in modes:
            mode_field = _interpolated_mode_field(E.function_space, mode_k, mode_polarization)
            apparent, _ = _fit_plane_wave_modes(
                mode_field,
                cfg,
                points,
                modes,
                calibrate_fe_response=False,
            )
            response_columns.append([apparent[name] for name, _, _ in modes])
        response = np.asarray(response_columns, dtype=np.complex128).T
        if response.size:
            condition = np.linalg.cond(response)
            if np.isfinite(condition) and condition < 1.0e12:
                amplitudes = np.linalg.solve(response, amplitudes)
    return {name: complex(value) for value, (name, _, _) in zip(amplitudes, modes)}, residual

def _floquet_probe_metrics(floquet_data: DoubleFloquet3DData) -> dict[str, float]:
    # Stage 2 now uses explicit edge topology for Floquet constraints, so the
    # old probe-fit mismatch is replaced by the maximum edge midpoint pairing
    # error measured during dof matching.
    x_mismatch = float(floquet_data.max_edge_midpoint_pairing_error)
    y_mismatch = float(floquet_data.max_edge_midpoint_pairing_error)
    return {
        "floquet_x_face_mismatch": x_mismatch,
        "floquet_y_face_mismatch": y_mismatch,
        "floquet_edge_corner_mismatch": floquet_data.edge_corner_phase_mismatch,
    }

def _pml_probe_metrics(E, cfg: SimulationConfig3D) -> dict[str, float | None]:
    if not cfg.use_pml:
        return {
            "pml_reflection_proxy": None,
            "pml_decay_ratio_top": None,
            "pml_decay_ratio_bottom": None,
        }

    center_x = 0.5 * (cfg.x_min + cfg.x_max)
    center_y = 0.5 * (cfg.y_min + cfg.y_max)
    metrics: dict[str, float | None] = {}
    physical_z = np.linspace(cfg.physical_z_min + 0.15 * (cfg.physical_z_max - cfg.physical_z_min),
                             cfg.physical_z_max - 0.15 * (cfg.physical_z_max - cfg.physical_z_min), 6)
    physical_points = np.asarray([[center_x, center_y, z] for z in physical_z], dtype=np.float64)
    numerical = _sample_field_at_points(E, physical_points)
    exact = electric_field_code_values(cfg, physical_points)
    metrics["pml_reference_relative_error"] = _relative_norm_error(numerical, exact)

    # Fit the numerical physical-region field to downward/upward plane waves.
    # The ratio |A_up|/|A_down| is a more meaningful PML reflection proxy than
    # simply comparing against the manufactured field point by point.
    k_down, p_down = _mode_basis(cfg, cfg.n_air, vertical_sign=-1)
    k_up, p_up = _mode_basis(cfg, cfg.n_air, vertical_sign=1)
    fit_z = np.linspace(
        cfg.physical_z_min + 0.2 * (cfg.physical_z_max - cfg.physical_z_min),
        cfg.physical_z_max - 0.2 * (cfg.physical_z_max - cfg.physical_z_min),
        5,
    )
    amplitudes, fit_residual = _fit_plane_wave_modes(
        E,
        cfg,
        _sample_grid_points(cfg, fit_z, nx=3, ny=3),
        [("down", k_down, p_down), ("up", k_up, p_up)],
    )
    down_abs = abs(amplitudes["down"])
    up_abs = abs(amplitudes["up"])
    metrics["pml_reflection_proxy"] = float(up_abs / max(down_abs, 1.0e-30))
    metrics["pml_mode_fit_residual"] = fit_residual
    metrics["pml_downward_amplitude_abs"] = float(down_abs)
    metrics["pml_upward_amplitude_abs"] = float(up_abs)

    if cfg.pml_top_thickness > 0.0:
        top_inner = np.asarray([[center_x, center_y, cfg.physical_z_max + 0.05 * cfg.pml_top_thickness]])
        top_outer = np.asarray([[center_x, center_y, cfg.domain_z_max - 0.05 * cfg.pml_top_thickness]])
        metrics["pml_decay_ratio_top"] = float(
            np.linalg.norm(_sample_field_at_points(E, top_outer)) / max(np.linalg.norm(_sample_field_at_points(E, top_inner)), 1.0e-30)
        )
    else:
        metrics["pml_decay_ratio_top"] = None

    if cfg.pml_bottom_thickness > 0.0:
        bottom_inner = np.asarray([[center_x, center_y, cfg.physical_z_min - 0.05 * cfg.pml_bottom_thickness]])
        bottom_outer = np.asarray([[center_x, center_y, cfg.domain_z_min + 0.05 * cfg.pml_bottom_thickness]])
        metrics["pml_decay_ratio_bottom"] = float(
            np.linalg.norm(_sample_field_at_points(E, bottom_outer))
            / max(np.linalg.norm(_sample_field_at_points(E, bottom_inner)), 1.0e-30)
        )
    else:
        metrics["pml_decay_ratio_bottom"] = None
    return metrics

def _stage4_scattered_pml_metrics(E_sca, cfg: SimulationConfig3D) -> dict[str, float | None | str]:
    """Measure PML behavior from the scattered field, not the total field.

    In Stage 4, ``E_total = E_bg + E_scat``.  The PML is meant to absorb the
    outgoing scattered field.  The layered background field is analytically
    continued into the artificial PML and may have nonzero or even large
    magnitude there, so judging the PML from ``E_total`` is misleading.
    """

    metrics: dict[str, float | None | str] = {
        "pml_metric_field": "E_scat",
        "pml_metric_note": "Stage 4 PML diagnostics use E_scat; E_total/E_b in PML are artificial-coordinate fields.",
        "pml_reference_relative_error": None,
        "pml_reflection_proxy": None,
        "pml_decay_ratio_top": None,
        "pml_decay_ratio_bottom": None,
        "pml_scattered_decay_ratio_top": None,
        "pml_scattered_decay_ratio_bottom": None,
    }
    if E_sca is None or not cfg.use_pml:
        return metrics

    center_x = 0.5 * (cfg.x_min + cfg.x_max)
    center_y = 0.5 * (cfg.y_min + cfg.y_max)
    if cfg.pml_top_thickness > 0.0:
        top_inner = np.asarray([[center_x, center_y, cfg.physical_z_max + 0.05 * cfg.pml_top_thickness]])
        top_outer = np.asarray([[center_x, center_y, cfg.domain_z_max - 0.05 * cfg.pml_top_thickness]])
        top_inner_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, top_inner)))
        top_outer_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, top_outer)))
        metrics["pml_scattered_inner_norm_top"] = top_inner_norm
        metrics["pml_scattered_outer_norm_top"] = top_outer_norm
        metrics["pml_scattered_decay_ratio_top"] = top_outer_norm / max(top_inner_norm, 1.0e-30)
        metrics["pml_decay_ratio_top"] = metrics["pml_scattered_decay_ratio_top"]

    if cfg.pml_bottom_thickness > 0.0:
        bottom_inner = np.asarray([[center_x, center_y, cfg.physical_z_min - 0.05 * cfg.pml_bottom_thickness]])
        bottom_outer = np.asarray([[center_x, center_y, cfg.domain_z_min + 0.05 * cfg.pml_bottom_thickness]])
        bottom_inner_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, bottom_inner)))
        bottom_outer_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, bottom_outer)))
        metrics["pml_scattered_inner_norm_bottom"] = bottom_inner_norm
        metrics["pml_scattered_outer_norm_bottom"] = bottom_outer_norm
        metrics["pml_scattered_decay_ratio_bottom"] = bottom_outer_norm / max(bottom_inner_norm, 1.0e-30)
        metrics["pml_decay_ratio_bottom"] = metrics["pml_scattered_decay_ratio_bottom"]
    return metrics

def _fresnel_numerical_metrics(E, cfg: SimulationConfig3D) -> dict[str, Any]:
    """Extract Fresnel R/T from the solved 3D field by modal fitting."""
    ref = fresnel_reference(cfg)
    n1 = complex(cfg.n_air)
    n2 = complex(cfg.substrate_index)
    k_inc, p_inc = _mode_basis(cfg, n1, vertical_sign=-1)
    k_ref, p_ref = _mode_basis(cfg, n1, vertical_sign=1)
    k_trn, p_trn = _mode_basis(cfg, n2, vertical_sign=-1)

    top_height = cfg.physical_z_max - cfg.interface_z
    bottom_height = cfg.interface_z - cfg.physical_z_min
    top_z = np.linspace(cfg.interface_z + 0.25 * top_height, cfg.interface_z + 0.75 * top_height, 4)
    bottom_z = np.linspace(cfg.interface_z - 0.75 * bottom_height, cfg.interface_z - 0.25 * bottom_height, 4)
    top_points = _sample_grid_points(cfg, top_z, nx=4, ny=4)
    bottom_points = _sample_grid_points(cfg, bottom_z, nx=4, ny=4)
    top_amplitudes, top_fit_residual = _fit_plane_wave_modes(
        E,
        cfg,
        top_points,
        [("incident", k_inc, p_inc), ("reflected", k_ref, p_ref)],
    )
    bottom_amplitudes, bottom_fit_residual = _fit_plane_wave_modes(
        E,
        cfg,
        bottom_points,
        [("transmitted", k_trn, p_trn)],
    )

    incident = top_amplitudes["incident"]
    reflected = top_amplitudes["reflected"]
    transmitted = bottom_amplitudes["transmitted"]
    cos_i = max(float(np.cos(cfg.theta_rad)), 1.0e-30)
    sin_t = n1 / n2 * np.sin(cfg.theta_rad)
    cos_t = _positive_sqrt(1.0 - sin_t**2)
    admittance_ratio = float(np.real((n2 * cos_t) / (n1 * cos_i)))
    # These are numerical postprocess values.  The analytic Fresnel values are
    # only used below as the reference to compute errors.
    R_total = float(abs(reflected / incident) ** 2)
    T_total = float(admittance_ratio * abs(transmitted / incident) ** 2)
    return {
        "R_total": R_total,
        "T_total": T_total,
        "R_plus_T": R_total + T_total,
        "fresnel_R": ref["R"],
        "fresnel_T": ref["T"],
        "fresnel_R_error": abs(R_total - float(ref["R"])),
        "fresnel_T_error": abs(T_total - float(ref["T"])),
        "fresnel_R_plus_T_error": abs(R_total + T_total - float(ref["R_plus_T"])),
        "fresnel_reference": ref,
        "fresnel_incident_amplitude_abs": float(abs(incident)),
        "fresnel_reflected_amplitude_abs": float(abs(reflected)),
        "fresnel_transmitted_amplitude_abs": float(abs(transmitted)),
        "fresnel_top_mode_fit_residual": top_fit_residual,
        "fresnel_bottom_mode_fit_residual": bottom_fit_residual,
        "fresnel_top_sampling_z_min": float(np.min(top_z)),
        "fresnel_top_sampling_z_max": float(np.max(top_z)),
        "fresnel_bottom_sampling_z_min": float(np.min(bottom_z)),
        "fresnel_bottom_sampling_z_max": float(np.max(bottom_z)),
        "fresnel_top_sampling_point_count": int(len(top_points)),
        "fresnel_bottom_sampling_point_count": int(len(bottom_points)),
        "fresnel_top_sampling_margin_to_interface": float(np.min(top_z) - cfg.interface_z),
        "fresnel_top_sampling_margin_to_top_pml": float(cfg.physical_z_max - np.max(top_z)),
        "fresnel_bottom_sampling_margin_to_interface": float(cfg.interface_z - np.max(bottom_z)),
        "fresnel_bottom_sampling_margin_to_bottom_pml": float(np.min(bottom_z) - cfg.physical_z_min),
        "rt_metric_note": "R/T are fitted from the numerical 3D field in uniform layers and compared with Fresnel theory.",
    }

def _stage2_reference_metrics(E, cfg: SimulationConfig3D, field_metrics: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if cfg.geometry_kind == "fresnel_interface":
        metrics.update(_fresnel_numerical_metrics(E, cfg))
    elif cfg.use_pml:
        metrics.update(
            {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "fresnel_R": None,
                "fresnel_T": None,
                "fresnel_R_error": None,
                "fresnel_T_error": None,
            }
        )
    metrics["fresnel_field_relative_max_error"] = field_metrics.get("relative_max_abs_E_error")
    return metrics

def run_fresnel_analytic_postprocess_sanity(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, Any]:
    """Check Fresnel R/T fitting by interpolating the analytic total field only.

    This diagnostic intentionally does not assemble or solve Maxwell.  It uses
    the same mesh, Nedelec function space, and ``_fresnel_numerical_metrics``
    modal fitting path as the real 2C solve.  If this sanity check fails, the
    issue is in postprocessing, polarization basis, sampling, or T
    normalization rather than in the PDE solve.
    """

    if cfg.geometry_kind != "fresnel_interface":
        raise ValueError("Fresnel analytic postprocess sanity requires geometry_kind='fresnel_interface'.")
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    start = time.perf_counter()
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    msh = mesh_data.mesh
    V = _create_nedelec_space(msh, cfg)
    E_analytic = plane_wave_electric_field(V, cfg)
    metrics = _fresnel_numerical_metrics(E_analytic, cfg)
    field_norm = _function_coefficient_norm(E_analytic)
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
    summary: dict[str, Any] = {
        "case_name": cfg.case_name,
        "stage": "stage2_3d_fresnel_analytic_postprocess_sanity",
        **_summary_base_fields(cfg, comm),
        "config": cfg.as_jsonable(),
        "case_status": "completed",
        "official_result": False,
        "diagnostic_only": True,
        "postprocess_only": True,
        "postprocess_sanity_kind": "fresnel_analytic_total_field_interpolation",
        "num_mesh_cells": msh.topology.index_map(msh.topology.dim).size_global,
        "num_nedelec_dofs": V.dofmap.index_map.size_global * V.dofmap.index_map_bs,
        "mesh_cell_type_actual": mesh_data.mesh_cell_type_resolved,
        "mesh_cells_resolved": mesh_data.mesh_cells_resolved,
        "z_alignment_warnings": mesh_data.z_alignment_warnings,
        "domain_tag_volumes": _cell_tag_volumes(msh, mesh_data, cfg),
        "E_analytic_norm": field_norm,
        "elapsed_seconds": elapsed,
        "max_rss_mb": _global_max_rss_mb(comm),
        **metrics,
    }
    summary["fresnel_postprocess_sanity_thresholds"] = {
        "fresnel_R_error": 1.0e-8,
        "fresnel_T_error": 1.0e-8,
        "fresnel_top_mode_fit_residual": 1.0e-1,
        "fresnel_bottom_mode_fit_residual": 1.0e-1,
    }
    summary["fresnel_postprocess_sanity_pass"] = bool(
        summary["fresnel_R_error"] < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_R_error"]
        and summary["fresnel_T_error"] < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_T_error"]
        and summary["fresnel_top_mode_fit_residual"]
        < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_top_mode_fit_residual"]
        and summary["fresnel_bottom_mode_fit_residual"]
        < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_bottom_mode_fit_residual"]
    )
    if comm.rank == 0:
        (out_dir / "fresnel_analytic_postprocess_sanity.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    return summary

def _stage4_lossless_energy_balance_check(cfg: SimulationConfig3D, summary: dict[str, Any]) -> dict[str, Any]:
    """Return an explicit pass/fail flag for lossless Stage-4 R/T metrics."""

    if cfg.geometry_kind != "rectangular_block_grating" or summary.get("R_plus_T") is None:
        return {}
    lossless = all(
        abs(complex(index).imag) < 1.0e-12
        for index in (cfg.n_air, cfg.substrate_index, cfg.grating_index)
    )
    tolerance = 1.0e-8
    r_plus_t = float(summary["R_plus_T"])
    passed = (not lossless) or r_plus_t <= 1.0 + tolerance
    return {
        "stage4_lossless_energy_balance_checked": bool(lossless),
        "stage4_energy_balance_tolerance": tolerance,
        "stage4_energy_balance_pass": bool(passed),
        "stage4_energy_balance_excess": float(r_plus_t - 1.0) if lossless else None,
    }
