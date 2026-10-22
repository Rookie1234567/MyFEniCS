"""Explicit first-stage Task43 research configuration."""

from __future__ import annotations

import hashlib
import json

from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    EUV_REFERENCE_WAVELENGTH_NM,
    SI_GRATING_INDEX_EUV_13P5_NM,
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    target_stage4_config,
)
from src.geometry.task43_hp_adaptivity_axis_plan import (
    TASK43_AXES_NM,
    TASK43_AXIS_CELL_COUNTS,
    TASK43_AXIS_PLAN_ID,
    TASK43_AXIS_PLAN_SHA256,
)

TASK43_R13_MAX_M = 4
TASK43_R13_MAX_N = 8
TASK43_MODE_COUNT = 612
TASK43_VOLUME_QUADRATURE_DEGREE = 15
TASK43_VOLUME_QUADRATURE_RULE = "default"
TASK43_PORT_QUADRATURE_DEGREE = 28
TASK43_SPARSE_CUTOFF_POLICY = "scale_homogeneous_relative_only_v1"
TASK43_SPARSE_CUTOFF_RELATIVE_TOLERANCE = 1.0e-13
TASK43_PORT_BOUNDARY_AMPLITUDE_SCALE_POLICY = (
    "boundary_magnitude_scaled_r5_v1"
)
TASK43_RAW_TENSOR_BACKEND = "blocked_gram_v1"


def task43_initial_profile(
    *,
    cell_degree_plan_path: str | None = None,
    case_name: str = "task43_initial_r13",
):
    """Build the frozen Task43 geometry/physics start on a p6 carrier.

    The caller may attach a geometry-bound variable-p plan after building the
    exact mesh.  The returned config is intentionally not launchable until
    one such plan is supplied.
    """

    cfg = target_stage4_config(degree=6, h_nm=30.0)
    cfg.case_name = str(case_name)
    cfg.period_x = 50.0
    cfg.period_y = 50.0
    cfg.grating_width_x = 17.0
    cfg.grating_width_y = 20.0
    cfg.grating_height = 120.0
    cfg.interface_z = 0.0
    cfg.z_min = -10.0
    cfg.z_max = 130.0
    cfg.incident_theta_deg = 89.0
    cfg.incident_phi_deg = 90.0
    cfg.polarization_kind = "s"
    cfg.custom_polarization = None
    cfg.use_floquet_xy = True
    cfg.use_pml = False
    cfg.mesh_cell_type = "hexahedron"
    cfg.mesh_spacing_mode = "boundary_fitted"
    cfg.mesh_axis_cell_counts = TASK43_AXIS_CELL_COUNTS
    cfg.mesh_axis_x_values = TASK43_AXES_NM["x"]
    cfg.mesh_axis_y_values = TASK43_AXES_NM["y"]
    cfg.mesh_axis_z_values = TASK43_AXES_NM["z"]
    cfg.mesh_plan_id = TASK43_AXIS_PLAN_ID
    cfg.mesh_plan_sha256 = TASK43_AXIS_PLAN_SHA256
    cfg.stage4_dtn_order_policy = "explicit_rectangle"
    cfg.stage4_dtn_rectangle_max_m = TASK43_R13_MAX_M
    cfg.stage4_dtn_rectangle_max_n = TASK43_R13_MAX_N
    cfg.stage4_dtn_quadrature_degree = TASK43_PORT_QUADRATURE_DEGREE
    cfg.stage4_incident_quadrature_degree = TASK43_PORT_QUADRATURE_DEGREE
    cfg.stage4_volume_quadrature_degree = TASK43_VOLUME_QUADRATURE_DEGREE
    cfg.stage4_volume_quadrature_rule = TASK43_VOLUME_QUADRATURE_RULE
    cfg.stage4_dtn_sparse_cutoff_policy = TASK43_SPARSE_CUTOFF_POLICY
    cfg.stage4_dtn_sparse_cutoff_relative_tolerance = (
        TASK43_SPARSE_CUTOFF_RELATIVE_TOLERANCE
    )
    cfg.stage4_port_boundary_amplitude_scale_policy = (
        TASK43_PORT_BOUNDARY_AMPLITUDE_SCALE_POLICY
    )
    cfg.stage4_variable_p_raw_tensor_backend = TASK43_RAW_TENSOR_BACKEND
    cfg.stage4_full3d_assembly_backend = (
        ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    cfg.stage4_variable_p_cell_degree_plan = cell_degree_plan_path
    cfg.stage4_local_h_refinement_plan = None
    cfg.nedelec_degree = 6
    cfg.matrix_diagnostics_assemble_only = False
    cfg.matrix_diagnostics_factorization_only = False
    cfg.unique_output = False
    cfg.diffraction_zero_order_only = False
    return cfg


def _complex_pair(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _mode_identity(mode) -> dict[str, object]:
    """Serialize the actual selected mode, including its resolved wave data."""

    return {
        "side": str(mode.side),
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization),
        "alpha": _complex_pair(mode.alpha),
        "gamma": _complex_pair(mode.gamma),
        "beta": _complex_pair(mode.beta),
        "refractive_index": _complex_pair(mode.refractive_index),
        "vertical_sign": int(mode.vertical_sign),
        "e_vector": [_complex_pair(value) for value in mode.e_vector],
        "k_vector": [_complex_pair(value) for value in mode.k_vector],
        "h_vector": [_complex_pair(value) for value in mode.h_vector],
        "propagating": bool(mode.propagating),
        "rayleigh_warning": bool(mode.rayleigh_warning),
        "boundary_amplitude_scale": float(mode.boundary_amplitude_scale),
        "boundary_amplitude_log_scale": float(mode.boundary_amplitude_log_scale),
    }


def task43_profile_identity(cfg, modes) -> dict[str, object]:
    """Bind a run record to resolved config and the modes actually selected.

    ``expected_contract`` captures the intended Task43 starting controls.
    ``resolved`` is read from the live config and parsed mode inventory so a
    changed wavelength, material, incidence, quadrature, cutoff or mode window
    cannot continue to carry the original profile label unnoticed.
    """

    # Preserve the actual solver iteration order: auxiliary amplitudes and
    # mode-indexed fields use this same ordering.
    mode_inventory = [_mode_identity(mode) for mode in modes]
    mode_inventory_payload = json.dumps(
        mode_inventory, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    mode_keys = [
        [mode["side"], mode["m"], mode["n"], mode["polarization"]]
        for mode in mode_inventory
    ]
    grating_bounds = [
        float(cfg.grating_x_min),
        float(cfg.grating_x_max),
        float(cfg.grating_y_min),
        float(cfg.grating_y_max),
        float(cfg.grating_z_min),
        float(cfg.grating_z_max),
    ]
    axes = {
        "x": [float(value) for value in cfg.mesh_axis_x_values],
        "y": [float(value) for value in cfg.mesh_axis_y_values],
        "z": [float(value) for value in cfg.mesh_axis_z_values],
    }
    cell_counts = [len(axes[axis]) - 1 for axis in ("x", "y", "z")]
    return {
        "profile_id": "task43_initial_r13_v1",
        "expected_contract": {
            "lambda0_nm": EUV_REFERENCE_WAVELENGTH_NM,
            "material_indices": {
                "substrate": _complex_pair(SI_SUBSTRATE_INDEX_EUV_13P5_NM),
                "grating": _complex_pair(SI_GRATING_INDEX_EUV_13P5_NM),
            },
            "period_nm": [50.0, 50.0],
            "grating_bounds_nm": [16.5, 33.5, 15.0, 35.0, 0.0, 120.0],
            "substrate_bounds_nm": [-10.0, 0.0],
            "incidence": {
                "theta_deg": 89.0,
                "phi_deg": 90.0,
                "polarization_kind": "s",
                "amplitude": [1.0, 0.0],
                "direction_vector": [
                    0.0,
                    0.9998476951563913,
                    -0.0174524064372836,
                ],
                "polarization_vector": [[-1.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
            },
            "mode_rectangle": {
                "m": [-TASK43_R13_MAX_M, TASK43_R13_MAX_M],
                "n": [-TASK43_R13_MAX_N, TASK43_R13_MAX_N],
                "mode_count": TASK43_MODE_COUNT,
            },
            "quadrature_degree": {
                "volume": TASK43_VOLUME_QUADRATURE_DEGREE,
                "incident_and_ports": TASK43_PORT_QUADRATURE_DEGREE,
            },
            "quadrature_rule": {"volume": TASK43_VOLUME_QUADRATURE_RULE},
            "sparse_cutoff": {
                "policy": TASK43_SPARSE_CUTOFF_POLICY,
                "relative_tolerance": TASK43_SPARSE_CUTOFF_RELATIVE_TOLERANCE,
            },
            "port_basis_scaling_policy": (
                TASK43_PORT_BOUNDARY_AMPLITUDE_SCALE_POLICY
            ),
            "raw_tensor_backend": TASK43_RAW_TENSOR_BACKEND,
            "axis_plan_id": TASK43_AXIS_PLAN_ID,
            "axis_plan_sha256": TASK43_AXIS_PLAN_SHA256,
            "axis_cell_counts_xyz": list(TASK43_AXIS_CELL_COUNTS),
        },
        "resolved": {
            "lambda0_nm": float(cfg.lambda0),
            "material_indices": {
                "air": _complex_pair(cfg.n_air),
                "substrate": _complex_pair(cfg.substrate_index),
                "grating": _complex_pair(cfg.grating_index),
                "mu_r": _complex_pair(cfg.mu_r),
            },
            "period_nm": [
                float(cfg.x_max - cfg.x_min),
                float(cfg.y_max - cfg.y_min),
            ],
            "grating_bounds_nm": grating_bounds,
            "substrate_bounds_nm": [float(cfg.z_min), float(cfg.interface_z)],
            "incidence": {
                "theta_deg": float(cfg.incident_theta_deg),
                "phi_deg": float(cfg.incident_phi_deg),
                "polarization_kind": str(cfg.polarization_kind),
                "amplitude": _complex_pair(cfg.incident_amplitude),
                "direction_vector": [
                    float(value) for value in cfg.direction_vector
                ],
                "polarization_vector": [
                    _complex_pair(value) for value in cfg.polarization_vector
                ],
                "wavevector": [_complex_pair(value) for value in cfg.wavevector],
            },
            "mode_selection": {
                "order_policy": str(cfg.stage4_dtn_order_policy),
                "rectangle_max_m": getattr(
                    cfg, "stage4_dtn_rectangle_max_m", None
                ),
                "rectangle_max_n": getattr(
                    cfg, "stage4_dtn_rectangle_max_n", None
                ),
                "mode_count": len(mode_inventory),
                "mode_keys": mode_keys,
                "mode_inventory_sha256": hashlib.sha256(
                    mode_inventory_payload
                ).hexdigest(),
                "mode_inventory": mode_inventory,
            },
            "quadrature_degree": {
                "volume": int(cfg.stage4_volume_quadrature_degree),
                "incident": int(cfg.stage4_incident_quadrature_degree),
                "ports": int(cfg.stage4_dtn_quadrature_degree),
            },
            "quadrature_rule": {
                "volume": str(
                    getattr(cfg, "stage4_volume_quadrature_rule", "default")
                ),
            },
            "sparse_cutoff": {
                "policy": str(cfg.stage4_dtn_sparse_cutoff_policy),
                "relative_tolerance": float(
                    cfg.stage4_dtn_sparse_cutoff_relative_tolerance
                ),
            },
            "port_basis_scaling": {
                "policy": getattr(
                    cfg,
                    "stage4_port_boundary_amplitude_scale_policy",
                    None,
                ),
                "conversion": (
                    "solver coefficient is in the boundary-normalized modal basis; "
                    "per-mode q=exp(Im(kz)*z_boundary) and boundary_phase are "
                    "recorded, and outgoing_amplitude_at_boundary applies that map"
                ),
            },
            "variable_p_raw_tensor_backend": getattr(
                cfg,
                "stage4_variable_p_raw_tensor_backend",
                "ffcx",
            ),
            "axis_plan": {
                "id": str(cfg.mesh_plan_id),
                "sha256": str(cfg.mesh_plan_sha256),
                "axes_nm": axes,
                "cell_counts_xyz": cell_counts,
                "global_cell_count": int(
                    cell_counts[0] * cell_counts[1] * cell_counts[2]
                ),
            },
        },
    }


__all__ = ["task43_initial_profile", "task43_profile_identity"]
