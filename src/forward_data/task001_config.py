"""Thin Task001 configuration overlay on the tracked Stage-4 authority."""

from __future__ import annotations

from typing import Any

from src.common.config_3d import SimulationConfig3D, target_stage4_config

from .schema import TASK001_FIDELITIES, Task001ForwardParameters


def task001_stage4_config(parameters: Task001ForwardParameters) -> SimulationConfig3D:
    """Build one Task001 config without copying any physical constants."""

    parameters.validate()
    fidelity = TASK001_FIDELITIES[parameters.model_id]
    cfg = target_stage4_config(
        degree=int(fidelity["degree"]), h_nm=float(fidelity["h_nm"])
    )
    cfg.grating_height = float(parameters.height_nm)
    cfg.grating_width_x = float(parameters.width_x_nm)
    cfg.incident_theta_deg = float(parameters.theta_deg)
    cfg.incident_phi_deg = float(parameters.phi_deg)
    cfg.polarization_kind = parameters.incident_polarization.lower()
    cfg.mesh_axis_cell_counts = tuple(int(v) for v in fidelity["axis_counts"])
    cfg.mesh_spacing_mode = "boundary_fitted"
    substrate_cells, grating_cells, air_cells = (
        (1, 12, 1) if parameters.model_id in {"HF10", "LF4", "LF5"} else (2, 17, 1)
    )
    substrate_axis = [
        cfg.domain_z_min
        + index * (cfg.interface_z - cfg.domain_z_min) / substrate_cells
        for index in range(substrate_cells + 1)
    ]
    grating_axis = [
        cfg.interface_z
        + index * (cfg.grating_z_max - cfg.interface_z) / grating_cells
        for index in range(1, grating_cells + 1)
    ]
    air_axis = [
        cfg.grating_z_max
        + index * (cfg.domain_z_max - cfg.grating_z_max) / air_cells
        for index in range(1, air_cells + 1)
    ]
    cfg.mesh_axis_z_values = tuple(substrate_axis + grating_axis + air_axis)
    cfg.mesh_axis_z_profile = (
        f"task001-fixed-material-layers-{substrate_cells}-{grating_cells}-{air_cells}"
    )
    cfg.case_name = (
        f"task001_{parameters.model_id.lower()}_hgt{parameters.height_nm:g}_"
        f"wid{parameters.width_x_nm:g}_theta{parameters.theta_deg:g}_"
        f"phi{parameters.phi_deg:g}_{parameters.incident_polarization.lower()}"
    ).replace(".", "p")
    return cfg


def task001_config_identity(parameters: Task001ForwardParameters) -> dict[str, Any]:
    cfg = task001_stage4_config(parameters)
    return {
        "case_name": cfg.case_name,
        "degree": int(cfg.nedelec_degree),
        "h_nm": float(cfg.mesh_target_size),
        "modes": int(parameters.fidelity["modes"]),
        "axis_cell_counts": list(cfg.mesh_axis_cell_counts_requested or ()),
        "height_nm": float(cfg.grating_height),
        "width_x_nm": float(cfg.grating_width_x),
        "theta_deg": float(cfg.incident_theta_deg),
        "phi_deg": float(cfg.incident_phi_deg),
        "grazing_deg": float(parameters.grazing_deg),
        "azimuth_deg": float(parameters.azimuth_deg),
        "angle_convention": "theta_from_downward_normal_deg = 90 - grazing_deg",
        "polarization": cfg.polarization_kind.upper(),
        "wavelength_nm": float(cfg.lambda0),
        "assembly_backend": "assembly_time_static_condensed",
        "solver_path": "modal-schur-memory-minimal",
        "internal_propagation_model": "full3d_uniform_cg",
        "internal_traction_model": "scalar_cg_discrete_derivative",
    }
