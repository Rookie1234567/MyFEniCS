"""Frozen 120-cell 0.7 nm PSTDDM pilot model. No solver runs at import.

Units: nm. Scattered field against the analytic flat air/Si interface.
PML is outside the identical physical 120-cell region. This is a NEW source,
not the lost Oct23 source identity or a continuation of its numerical proof.
"""
from dataclasses import dataclass
from math import floor, pi
from pathlib import Path
import numpy as np

X = (0., .8555555555555555, 1.737037037037037, 2.5925925925925926)
Y = (0.0, 0.25925925925925924, 0.5185185185185185, 0.7777777777777778, 1.037037037037037, 1.2962962962962963, 1.5555555555555554, 1.8148148148148147, 2.074074074074074, 2.333333333333333, 2.5925925925925926)
Z = (-.5185185185185185, 0., 3.111111111111111, 6.222222222222222,
     6.7407407407407405)
SI = complex(.9998851703688496, 4.3236152269189515e-6)


@dataclass(frozen=True)
class PSTDDMModelSpec:
    """Explicit geometry/material/wavelength identity for one PSTDDM case."""

    case_name: str
    wavelength_nm: float
    period_x_nm: float
    period_y_nm: float
    x_axis_nm: tuple[float, ...]
    y_axis_nm: tuple[float, ...]
    z_axis_nm: tuple[float, ...]
    interface_z_nm: float
    grating_height_nm: float
    grating_width_x_nm: float
    grating_width_y_nm: float
    n_substrate: complex
    n_grating: complex
    geometry_identity: str
    expected_material_cells: tuple[tuple[int, int], ...]
    mesh_target_size_nm: float
    incident_theta_deg: float = 89.0
    incident_phi_deg: float = 90.0
    polarization_kind: str = "s"
    material_identity_sha256: str | None = None
    dtn_order_padding: int | None = None
    diffraction_order_max_m: int | None = None
    diffraction_order_max_n: int | None = None
    reporting_order_max_m: int | None = None
    reporting_order_max_n: int | None = None
    mesh_axis_z_profile: str = "explicit_pstddm_model_spec"

    def __post_init__(self) -> None:
        if not np.isfinite(self.wavelength_nm) or self.wavelength_nm <= 0.0:
            raise ValueError("model wavelength must be finite and positive")
        for name, value in (("x period", self.period_x_nm), ("y period", self.period_y_nm),
                            ("grating height", self.grating_height_nm),
                            ("grating x width", self.grating_width_x_nm),
                            ("grating y width", self.grating_width_y_nm),
                            ("mesh target size", self.mesh_target_size_nm)):
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not self.geometry_identity or not self.case_name:
            raise ValueError("case and geometry identities must be nonempty")
        if self.polarization_kind not in {"s", "p"}:
            raise ValueError("polarization_kind must be s or p")
        for name, index in (("substrate", self.n_substrate), ("grating", self.n_grating)):
            if not np.isfinite(complex(index)) or complex(index).imag < 0.0:
                raise ValueError(f"{name} index must be finite and passive for exp(-i omega t)")
        for name, axis in (("x", self.x_axis_nm), ("y", self.y_axis_nm),
                           ("z", self.z_axis_nm)):
            values = np.asarray(axis, dtype=np.float64)
            if values.ndim != 1 or values.size < 2 or np.any(~np.isfinite(values)):
                raise ValueError(f"{name} axis must contain finite mesh planes")
            if np.any(np.diff(values) <= 0.0):
                raise ValueError(f"{name} axis must be strictly increasing")
        if (not np.isclose(self.x_axis_nm[0], 0.0)
                or not np.isclose(self.x_axis_nm[-1] - self.x_axis_nm[0], self.period_x_nm)):
            raise ValueError("x mesh planes must span the x Floquet period")
        if (not np.isclose(self.y_axis_nm[0], 0.0)
                or not np.isclose(self.y_axis_nm[-1] - self.y_axis_nm[0], self.period_y_nm)):
            raise ValueError("y mesh planes must span the y Floquet period")
        boundaries = (
            (self.interface_z_nm, self.z_axis_nm),
            (self.interface_z_nm + self.grating_height_nm, self.z_axis_nm),
            (0.5 * (self.period_x_nm - self.grating_width_x_nm), self.x_axis_nm),
            (0.5 * (self.period_x_nm + self.grating_width_x_nm), self.x_axis_nm),
            (0.5 * (self.period_y_nm - self.grating_width_y_nm), self.y_axis_nm),
            (0.5 * (self.period_y_nm + self.grating_width_y_nm), self.y_axis_nm),
        )
        for coordinate, axis in boundaries:
            if not np.any(np.isclose(np.asarray(axis), coordinate, rtol=0.0, atol=1e-12)):
                raise ValueError(f"material boundary {coordinate} nm is not a mesh plane")
        if self.dtn_order_padding is not None and self.dtn_order_padding < 0:
            raise ValueError("DtN order padding must be non-negative")
        if any(int(tag) < 1 or int(count) < 0 for tag, count in self.expected_material_cells):
            raise ValueError("expected material cell tags/counts must be non-negative")


def stationary_grating_p2_spec(
    wavelength_nm: float,
    si_index: complex,
    *,
    material_identity_sha256: str | None = None,
) -> PSTDDMModelSpec:
    """Fixed finite-width 50x50x140 nm grating, with material-aligned p2 axes."""
    x_axis = (0.0, 16.5, 25.0, 33.5, 50.0)
    y_axis = (0.0, 15.0, 25.0, 35.0, 50.0)
    z_axis = (-10.0, *tuple(120.0 * index / 14.0 for index in range(15)), 130.0)
    return PSTDDMModelSpec(
        case_name=f"stationary_50x50x140_p2_{str(wavelength_nm).replace('.', 'p')}nm",
        wavelength_nm=float(wavelength_nm), period_x_nm=50.0, period_y_nm=50.0,
        x_axis_nm=x_axis, y_axis_nm=y_axis, z_axis_nm=z_axis,
        interface_z_nm=0.0, grating_height_nm=120.0,
        grating_width_x_nm=17.0, grating_width_y_nm=20.0,
        n_substrate=complex(si_index), n_grating=complex(si_index),
        geometry_identity="stationary_centered_17x20x120_period50x50_zm10_130_v1",
        expected_material_cells=((1, 184), (2, 16), (3, 56)),
        mesh_target_size_nm=16.5, incident_theta_deg=89.0,
        incident_phi_deg=90.0, polarization_kind="s",
        material_identity_sha256=material_identity_sha256,
        dtn_order_padding=1, mesh_axis_z_profile="stationary_z16_material_fitted_v1",
    )


def workstation_spec_from_material_identity(identity: dict[str, object]) -> PSTDDMModelSpec:
    """Bind the stationary geometry to one source-derived wavelength identity."""
    if identity.get("schema") != "pstddm.si_optical_identity.v1":
        raise ValueError("unsupported PSTDDM optical material identity")
    wavelength = float(identity["wavelength_nm"])
    pair = identity.get("n")
    if not isinstance(pair, list) or len(pair) != 2:
        raise ValueError("material identity must contain n as [real, imaginary]")
    index = complex(float(pair[0]), float(pair[1]))
    identity_sha = identity.get("identity_sha256")
    if not isinstance(identity_sha, str) or len(identity_sha) != 64:
        raise ValueError("material identity is missing its canonical SHA256")
    return stationary_grating_p2_spec(
        wavelength, index,
        material_identity_sha256=identity_sha,
    )


def _legacy_model_spec() -> PSTDDMModelSpec:
    return PSTDDMModelSpec(
        case_name="rebuild120", wavelength_nm=0.7,
        period_x_nm=X[-1], period_y_nm=Y[-1], x_axis_nm=X, y_axis_nm=Y, z_axis_nm=Z,
        interface_z_nm=0.0, grating_height_nm=Z[-2],
        grating_width_x_nm=.8814814814814814, grating_width_y_nm=1.037037037037037,
        n_substrate=SI, n_grating=SI,
        geometry_identity="scaled07_centered17x20_physical120_rebuilt_20261025",
        expected_material_cells=((1, 82), (2, 30), (3, 8)), mesh_target_size_nm=.7,
        dtn_order_padding=None, diffraction_order_max_m=5, diffraction_order_max_n=9,
        reporting_order_max_m=3, reporting_order_max_n=7,
        mesh_axis_z_profile="physical120_rebuilt",
    )


def structured_hcurl_dof_counts(nx: int, ny: int, nz: int, degree: int) -> dict[str, int]:
    """Count tensor-hexa Nedelec rows before and after x/y periodic tying."""
    nx, ny, nz, degree = (int(nx), int(ny), int(nz), int(degree))
    if min(nx, ny, nz, degree) < 1:
        raise ValueError("cell counts and Nedelec degree must be positive")
    px, py, pz = degree * nx, degree * ny, degree * nz
    raw = px * (py + 1) * (pz + 1) + (px + 1) * py * (pz + 1) + (px + 1) * (py + 1) * pz
    independent = 2 * px * py * (pz + 1) + px * py * pz
    return {"raw_fe_rows": int(raw), "independent_fe_rows": int(independent)}


def model_preflight(spec: PSTDDMModelSpec, degree: int = 2) -> dict[str, object]:
    """Count DoFs, modes and conservative factor allowances without FE assembly."""
    cfg = make_cfg("dtn", degree, model_spec=spec)
    from src.common.modes_3d import outgoing_port_modes_3d

    nx, ny, nz = len(spec.x_axis_nm) - 1, len(spec.y_axis_nm) - 1, len(spec.z_axis_nm) - 1
    dofs = structured_hcurl_dof_counts(nx, ny, nz, degree)
    modes = outgoing_port_modes_3d(cfg)
    n_max = max(abs(complex(cfg.n_air)), abs(complex(cfg.substrate_index)))
    auto_max_m = floor((n_max*cfg.k0+abs(cfg.kx))*cfg.period_x/(2*pi)+1e-12)
    auto_max_n = floor((n_max*cfg.k0+abs(cfg.ky))*cfg.period_y/(2*pi)+1e-12)
    selected_m = max(abs(mode.m) for mode in modes)
    selected_n = max(abs(mode.n) for mode in modes)
    if spec.dtn_order_padding is not None and (selected_m != auto_max_m+spec.dtn_order_padding
                                               or selected_n != auto_max_n+spec.dtn_order_padding):
        raise ValueError("generated DtN inventory does not match the wavelength-specific padded rectangle")
    rows = dofs["independent_fe_rows"] + len(modes)
    factor_allowance = 4 * rows * rows * 16
    element_dofs = 3 * degree * (degree + 1) ** 2
    trace_rows = degree * nx * (degree * ny + 1) + (degree * nx + 1) * degree * ny
    partitions = {}
    for count in (2, 4, 8):
        if nz % count:
            partitions[str(count)] = {"legal": False}
            continue
        layers = nz // count
        local_rows = []
        for pair in range(count - 1):
            lo, hi = pair * layers, (pair + 2) * layers
            local_nz = hi - lo + (2 if lo > 0 else 0) + (2 if hi < nz else 0)
            local_rows.append(structured_hcurl_dof_counts(nx, ny, local_nz, degree)["independent_fe_rows"])
        local_factors = sum(4 * value * value * 16 for value in local_rows)
        mass_factor = 4 * dofs["independent_fe_rows"] ** 2 * 16
        partitions[str(count)] = {
            "legal": True, "physical_layers_per_partition": layers,
            "pair_local_independent_rows_upper": local_rows,
            "maximum_pair_local_independent_rows_upper": max(local_rows),
            "all_local_factors_plus_global_mass_factor_allowance_bytes": local_factors + mass_factor,
        }
    return {
        "wavelength_nm": float(spec.wavelength_nm), "geometry_identity": spec.geometry_identity,
        "cells": nx * ny * nz, "axis_cell_counts": [nx, ny, nz], **dofs,
        "mode_count": len(modes),
        "propagating_mode_count": sum(bool(mode.propagating) for mode in modes),
        "evanescent_mode_count": sum(not bool(mode.propagating) for mode in modes),
        "rayleigh_warning_mode_count": sum(bool(mode.rayleigh_warning) for mode in modes),
        "auto_max_m": auto_max_m, "auto_max_n": auto_max_n,
        "selected_m_max": selected_m, "selected_n_max": selected_n,
        "dtn_order_padding": spec.dtn_order_padding,
        "mode_window_policy": ("all_propagating_plus_rectangular_one_order_padding"
                               if spec.dtn_order_padding == 1 else "legacy_manual"),
        "full_augmented_rows": rows, "direct_factor_planning_allowance_bytes": factor_allowance,
        "element_dofs": element_dofs,
        "volume_element_entry_contribution_upper": nx * ny * nz * element_dofs**2,
        "boundary_tangential_rows_per_side_upper": trace_rows,
        "legal_partition_plans": partitions,
        "factor_allowance_definition": "4*n^2*16 B planning estimate; not measured RSS or sparse factor size",
    }

def graded_pml_axis(layers=4, length=10., ratio=1.25):
    if layers < 1 or length <= 0 or ratio < 1: raise ValueError('Invalid PML grading')
    widths = ratio**np.arange(layers, dtype=float)
    depths = length*np.cumsum(widths)/np.sum(widths)
    depths[-1] = length
    return tuple(Z[0]-depths[::-1]) + Z + tuple(Z[-1]+depths)

def make_cfg(boundary, degree=6, *, layers=4, model_spec=None):
    from src.common.config_3d import SimulationConfig3D
    if boundary not in ('pml','dtn'): raise ValueError('boundary must be pml or dtn')
    if not 1 <= degree <= 6: raise ValueError('Qualified Floquet degrees are 1..6')
    legacy = model_spec is None
    model = _legacy_model_spec() if legacy else model_spec
    if not isinstance(model, PSTDDMModelSpec): raise TypeError('model_spec must be a PSTDDMModelSpec')
    if boundary == 'pml' and not legacy:
        raise ValueError('the stationary wavelength profile keeps PML local to PSTDDM partitions')
    pml = boundary == 'pml'
    x_axis, y_axis = model.x_axis_nm, model.y_axis_nm
    z = graded_pml_axis(layers) if pml else model.z_axis_nm
    cfg=SimulationConfig3D(case_name=f'{model.case_name}_p{degree}_{boundary}',
        stage_case='stage4_block_grating',geometry_kind='rectangular_block_grating',
        lambda0=model.wavelength_nm,n_air=1+0j,mu_r=1+0j,
        period_x=model.period_x_nm,period_y=model.period_y_nm,
        z_min=model.z_axis_nm[0],z_max=model.z_axis_nm[-1],air_height=model.z_axis_nm[-1],
        substrate_thickness=model.interface_z_nm-model.z_axis_nm[0],
        interface_z=model.interface_z_nm,grating_height=model.grating_height_nm,
        grating_width_x=model.grating_width_x_nm,grating_width_y=model.grating_width_y_nm,
        n_substrate=model.n_substrate,n_grating=model.n_grating,
        geometry_identity=model.geometry_identity,
        material_identity_sha256=model.material_identity_sha256,
        use_floquet_xy=True,incident_theta_deg=model.incident_theta_deg,
        incident_phi_deg=model.incident_phi_deg,
        polarization_kind=model.polarization_kind,custom_polarization=None,incident_amplitude=1+0j,
        nedelec_degree=degree,visualization_degree=degree,
        mesh_cell_type='hexahedron',mesh_spacing_mode='boundary_fitted',
        mesh_target_size=model.mesh_target_size_nm,
        mesh_axis_cell_counts=(len(x_axis)-1,len(y_axis)-1,len(z)-1),
        mesh_axis_x_values=x_axis,mesh_axis_y_values=y_axis,mesh_axis_z_values=z,
        mesh_axis_z_profile='physical120_pml_graded4_rebuilt' if pml else model.mesh_axis_z_profile,
        stage4_boundary_model='pml' if pml else 'dtn_port',
        stage4_dtn_order_policy='manual',
        diffraction_order_max_m=model.diffraction_order_max_m,
        diffraction_order_max_n=model.diffraction_order_max_n,
        reporting_diffraction_order_max_m=model.reporting_order_max_m,
        reporting_diffraction_order_max_n=model.reporting_order_max_n,
        use_pml=pml,pml_top_thickness=10. if pml else 0.,
        pml_bottom_thickness=10. if pml else 0.,pml_alpha=800.,
        stage4_pml_outer_bc='zero_tangential',divergence_penalty=0.)
    if model.dtn_order_padding is not None:
        n_max=max(abs(complex(cfg.n_air)),abs(complex(cfg.substrate_index)))
        auto_m=floor((n_max*cfg.k0+abs(cfg.kx))*cfg.period_x/(2*pi)+1e-12)
        auto_n=floor((n_max*cfg.k0+abs(cfg.ky))*cfg.period_y/(2*pi)+1e-12)
        cfg.diffraction_order_max_m=auto_m+model.dtn_order_padding
        cfg.diffraction_order_max_n=auto_n+model.dtn_order_padding
    cfg.stage4_dtn_quadrature_degree=28
    cfg.dtn_phase_gauge='boundary_plane'
    from src.common.config_3d import STANDARD_FULL_ASSEMBLY_BACKEND, resolve_stage4_full3d_assembly_backend
    cfg.stage4_full3d_assembly_backend=STANDARD_FULL_ASSEMBLY_BACKEND
    cfg.stage4_cell_static_condensation=False
    cfg.stage4_assembly_time_cell_static_condensation=False
    cfg.stage4_floquet_slave_elimination=False
    resolve_stage4_full3d_assembly_backend(cfg,apply=True)
    return cfg

def analytic_background(msh,cfg):
    """UFL flat-interface E; no FE interpolation in the forcing.

    No PML stretching needed here: RHS is supported only on physical grating.
    Total-field postprocessing uses this only on the physical region.
    """
    import ufl
    from petsc4py import PETSc
    from src.common.analytic_fields_3d import _fresnel_components
    x=ufl.SpatialCoordinate(msh)
    ki,kr,kt,ei,er,et=_fresnel_components(cfg)
    def wave(k,e):
        phase=ufl.exp(sum(PETSc.ScalarType(1j*k[j])*x[j] for j in range(3)))
        return ufl.as_vector([PETSc.ScalarType(v)*phase for v in e])
    return ufl.conditional(ufl.ge(x[2],cfg.interface_z),wave(ki,ei)+wave(kr,er),wave(kt,et))

@dataclass
class Problem:
    cfg: object
    mesh_data: object
    V: object
    floquet: object
    a: object
    L: object
    analytic_Ebg: object
    model_spec: object

def build_problem(boundary, output_dir, degree=6, *, layers=4, log=print, model_spec=None):
    import ufl
    from dolfinx import fem
    from petsc4py import PETSc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.common_3d_forms import _build_variational_forms
    model = _legacy_model_spec() if model_spec is None else model_spec
    # Preserve None so legacy PML calls retain their original global-PML path.
    cfg=make_cfg(boundary,degree,layers=layers,model_spec=model_spec)
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    mesh_data=build_airbox_mesh_3d(cfg,output_dir)
    if mesh_data.mesh.comm.size != 1: raise ValueError('This rebuilt direct adapter is MPI1 only')
    V=_create_nedelec_space(mesh_data.mesh,cfg)
    floquet=build_double_floquet_mpc(V,mesh_data,cfg,log)
    bg=analytic_background(mesh_data.mesh,cfg)
    a,L=_build_variational_forms(mesh_data.mesh,mesh_data,cfg,V,
        field_formulation='layered_scattered',incident_field=bg)
    if boundary=='pml':
        a=ufl.Form([i.reconstruct(metadata={**i.metadata(),'quadrature_degree':18})
                    if i.subdomain_id() in (cfg.tags.top_pml,cfg.tags.bottom_pml) else i
                    for i in a.integrals()])
    tags=np.asarray(mesh_data.cell_tags.values)
    expected=dict(model.expected_material_cells)
    if boundary=='pml':
        cross_section=(len(model.x_axis_nm)-1)*(len(model.y_axis_nm)-1)
        expected.update({4:cross_section*layers,5:cross_section*layers})
    actual={int(t):int(np.sum(tags==t)) for t in np.unique(tags)}
    if actual!=expected:raise ValueError(f'Unexpected mesh material counts: {actual} != {expected}')
    return Problem(cfg,mesh_data,V,floquet,a,L,bg,model)
