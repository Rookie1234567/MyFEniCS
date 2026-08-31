from __future__ import annotations

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_scalar_type, fem

from ..common.config_3d import SimulationConfig3D
from ..common.pml_3d import z_pml_tensors


def _validate_physical_split_profile(cfg: SimulationConfig3D) -> None:
    """Require the fixed no-PML, dtn-port split-volume profile."""

    if bool(cfg.use_pml) or float(cfg.pml_top_thickness) != 0.0 or float(
        cfg.pml_bottom_thickness
    ) != 0.0:
        raise ValueError("split physical volume requires the no-PML profile")
    if float(cfg.divergence_penalty) != 0.0:
        raise ValueError("split physical volume requires divergence_penalty=0")
    if str(cfg.stage4_boundary_model).lower() != "dtn_port":
        raise ValueError("split physical volume requires the dtn_port profile")


def _build_physical_volume_terms(
    cfg: SimulationConfig3D,
    u,
    v,
    dx,
):
    """Build the shared isotropic curl-curl and complex-mass forms.

    Optional divergence, PML, Robin, and right-hand-side terms remain in
    ``_build_variational_forms`` so its historical branches are unchanged.
    """
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    curl_curl = PETSc.ScalarType(0.0) * ufl.inner(curl_u, curl_v) * dx
    material_mass = PETSc.ScalarType(0.0) * ufl.inner(u, v) * dx
    for tag, eps_r in (
        (cfg.tags.air, cfg.eps_r),
        (cfg.tags.substrate, cfg.substrate_index**2),
        (cfg.tags.grating, cfg.grating_index**2),
    ):
        curl_curl += (
            PETSc.ScalarType(1.0 / cfg.mu_r)
            * ufl.inner(curl_u, curl_v)
            * dx(tag)
        )
        material_mass += (
            -cfg.k0**2
            * PETSc.ScalarType(eps_r)
            * ufl.inner(u, v)
            * dx(tag)
        )
    return curl_curl, material_mass


def _build_variational_forms(
    msh,
    mesh_data,
    cfg: SimulationConfig3D,
    V,
    *,
    field_formulation: str = "total_field",
    incident_field: fem.Function | None = None,
):
    """Assemble the shared Stage-1/Stage-2 curl-curl Maxwell weak form.

    Cell tags decide which material tensor is used.  The x/y periodicity is not
    part of this form; it is imposed later through ``dolfinx_mpc`` constraints.
    """
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mesh_data.facet_tags)
    zero = fem.Constant(msh, np.zeros(3, dtype=default_scalar_type))
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    curl_curl, material_mass = _build_physical_volume_terms(cfg, u, v, dx)
    a = curl_curl + material_mass
    if float(cfg.divergence_penalty) > 0.0:
        d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
        a += PETSc.ScalarType(cfg.divergence_penalty) * ufl.inner(ufl.div(u), ufl.div(v)) * d_physical

    # PML cells use the same unknown E, but with the z-stretched material
    # tensors.  Top and bottom are tagged separately so the sign convention is
    # testable and visible in ParaView through domain_tag.
    x = ufl.SpatialCoordinate(msh)
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        eps_top, mu_top = z_pml_tensors(x, cfg, "top", cfg.eps_r)
        a += ufl.inner(ufl.inv(mu_top) * curl_u, curl_v) * dx(cfg.tags.top_pml)
        a += -cfg.k0**2 * ufl.inner(eps_top * u, v) * dx(cfg.tags.top_pml)
    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        eps_bottom_background = (
            cfg.substrate_index**2
            if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}
            else cfg.eps_r
        )
        eps_bottom, mu_bottom = z_pml_tensors(x, cfg, "bottom", eps_bottom_background)
        a += ufl.inner(ufl.inv(mu_bottom) * curl_u, curl_v) * dx(cfg.tags.bottom_pml)
        a += -cfg.k0**2 * ufl.inner(eps_bottom * u, v) * dx(cfg.tags.bottom_pml)
    if (
        field_formulation == "layered_scattered"
        and cfg.stage4_boundary_model.lower() == "robin0"
    ):
        # Diagnostic truncation for Stage 4 only: no PML cells are present, so
        # a zero-order impedance term approximates outgoing waves at the top
        # and bottom planes.  The official Stage-4 path remains the 2D-like PML
        # weak form without this surface term.
        u_t = ufl.as_vector((u[0], u[1], 0.0))
        v_t = ufl.as_vector((v[0], v[1], 0.0))
        a += PETSc.ScalarType(1j * cfg.k0 * complex(cfg.n_air)) * ufl.inner(u_t, v_t) * ds(cfg.tags.z_max)
        a += PETSc.ScalarType(1j * cfg.k0 * complex(cfg.substrate_index)) * ufl.inner(u_t, v_t) * ds(cfg.tags.z_min)
    L = ufl.inner(zero, v) * dx
    if field_formulation == "incident_scattered":
        if incident_field is None:
            raise ValueError("incident_scattered formulation requires an incident_field.")
        contrast = PETSc.ScalarType(cfg.substrate_index**2 - cfg.eps_r)
        L += cfg.k0**2 * contrast * ufl.inner(incident_field, v) * dx(cfg.tags.substrate)
    elif field_formulation == "layered_scattered":
        if incident_field is None:
            raise ValueError("layered_scattered formulation requires a layered background field.")
        contrast = PETSc.ScalarType(cfg.eps_grating - cfg.grating_background_eps)
        L += cfg.k0**2 * contrast * ufl.inner(incident_field, v) * dx(cfg.tags.grating)
    return a, L

def _rhs_source_norm_for_tag(
    msh,
    mesh_data,
    cfg: SimulationConfig3D,
    source_field: fem.Function | None,
    tag: int,
    contrast: complex,
) -> float | None:
    if source_field is None:
        return None
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    energy_form = fem.form(ufl.inner(source_field, source_field) * dx(tag))
    local_energy = fem.assemble_scalar(energy_form)
    energy = msh.comm.allreduce(local_energy, op=MPI.SUM)
    scaled_contrast = cfg.k0**2 * complex(contrast)
    return float(abs(scaled_contrast) * np.sqrt(max(float(np.real(energy)), 0.0)))

def _incident_scattered_rhs_source_norm(
    msh, mesh_data, cfg: SimulationConfig3D, incident_field: fem.Function | None
) -> float | None:
    return _rhs_source_norm_for_tag(
        msh,
        mesh_data,
        cfg,
        incident_field,
        cfg.tags.substrate,
        cfg.substrate_index**2 - cfg.eps_r,
    )

def _layered_scattered_rhs_source_norm(
    msh, mesh_data, cfg: SimulationConfig3D, background_field: fem.Function | None
) -> float | None:
    return _rhs_source_norm_for_tag(
        msh,
        mesh_data,
        cfg,
        background_field,
        cfg.tags.grating,
        cfg.eps_grating - cfg.grating_background_eps,
    )

def _use_reference_correction_formulation(cfg: SimulationConfig3D) -> bool:
    """Use a correction unknown for analytic Stage-2 reference sanity cases.

    Solving homogeneous total-field problems with z-face Dirichlet data and
    x/y Floquet constraints creates a closed periodic cavity.  Near discrete
    cavity modes the total field can be badly amplified even when the boundary
    constraints are correct.  Keep this sanity path for 2A and 2B, but not for
    the 2C Fresnel physical benchmark.
    """

    return cfg.stage_case in {"floquet_airbox", "pml_airbox"}

def _use_incident_scattered_formulation(cfg: SimulationConfig3D) -> bool:
    return cfg.stage_case == "fresnel_interface" and cfg.geometry_kind == "fresnel_interface"

def _use_layered_scattered_formulation(cfg: SimulationConfig3D) -> bool:
    return (
        cfg.stage_case in {"stage4_block_grating", "stage4_flat_layer_sanity"}
        and cfg.geometry_kind == "rectangular_block_grating"
        and cfg.stage4_boundary_model.lower() != "dtn_port"
    )

def _use_stage4_dtn_port_formulation(cfg: SimulationConfig3D) -> bool:
    return (
        cfg.stage_case in {"stage4_block_grating", "stage4_flat_layer_sanity"}
        and cfg.geometry_kind == "rectangular_block_grating"
        and cfg.stage4_boundary_model.lower() == "dtn_port"
    )

def _field_formulation_label(
    cfg: SimulationConfig3D,
    use_reference_correction: bool,
    use_incident_scattered: bool,
) -> str:
    if use_incident_scattered:
        return "incident_scattered"
    if _use_stage4_dtn_port_formulation(cfg):
        return "total_field_dtn_port"
    if _use_layered_scattered_formulation(cfg):
        return "layered_scattered"
    if not use_reference_correction:
        return "total_field"
    if cfg.stage_case == "floquet_airbox":
        return "incident_correction"
    return "reference_correction"

def _z_boundary_facets(mesh_data, cfg: SimulationConfig3D) -> np.ndarray:
    return np.unique(
        np.concatenate(
            [
                np.asarray(mesh_data.facet_tags.find(cfg.tags.z_min), dtype=np.int32),
                np.asarray(mesh_data.facet_tags.find(cfg.tags.z_max), dtype=np.int32),
            ]
        )
    )
