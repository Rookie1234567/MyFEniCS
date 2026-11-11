"""Frozen 120-cell 0.7 nm PSTDDM pilot model. No solver runs at import.

Units: nm. Scattered field against the analytic flat air/Si interface.
PML is outside the identical physical 120-cell region. This is a NEW source,
not the lost Oct23 source identity or a continuation of its numerical proof.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np

X = (0., .8555555555555555, 1.737037037037037, 2.5925925925925926)
Y = (0.0, 0.25925925925925924, 0.5185185185185185, 0.7777777777777778, 1.037037037037037, 1.2962962962962963, 1.5555555555555554, 1.8148148148148147, 2.074074074074074, 2.333333333333333, 2.5925925925925926)
Z = (-.5185185185185185, 0., 3.111111111111111, 6.222222222222222,
     6.7407407407407405)
SI = complex(.9998851703688496, 4.3236152269189515e-6)

def graded_pml_axis(layers=4, length=10., ratio=1.25):
    if layers < 1 or length <= 0 or ratio < 1: raise ValueError('Invalid PML grading')
    widths = ratio**np.arange(layers, dtype=float)
    depths = length*np.cumsum(widths)/np.sum(widths)
    depths[-1] = length
    return tuple(Z[0]-depths[::-1]) + Z + tuple(Z[-1]+depths)

def make_cfg(boundary, degree=6, *, layers=4):
    from src.common.config_3d import SimulationConfig3D
    if boundary not in ('pml','dtn'): raise ValueError('boundary must be pml or dtn')
    if not 1 <= degree <= 6: raise ValueError('Qualified Floquet degrees are 1..6')
    pml = boundary == 'pml'
    z = graded_pml_axis(layers) if pml else Z
    cfg=SimulationConfig3D(case_name=f'rebuild120_p{degree}_{boundary}',
        stage_case='stage4_block_grating',geometry_kind='rectangular_block_grating',
        lambda0=.7,n_air=1+0j,mu_r=1+0j,period_x=X[-1],period_y=Y[-1],
        z_min=Z[0],z_max=Z[-1],air_height=Z[-1],substrate_thickness=-Z[0],
        interface_z=0.,grating_height=Z[-2],grating_width_x=.8814814814814814,
        grating_width_y=1.037037037037037,n_substrate=SI,n_grating=SI,
        geometry_identity='scaled07_centered17x20_physical120_rebuilt_20261025',
        use_floquet_xy=True,incident_theta_deg=89.,incident_phi_deg=90.,
        polarization_kind='s',custom_polarization=None,incident_amplitude=1+0j,
        nedelec_degree=degree,visualization_degree=degree,
        mesh_cell_type='hexahedron',mesh_spacing_mode='boundary_fitted',
        mesh_target_size=.7,mesh_axis_cell_counts=(3,10,len(z)-1),
        mesh_axis_x_values=X,mesh_axis_y_values=Y,mesh_axis_z_values=z,
        mesh_axis_z_profile='physical120_pml_graded4_rebuilt' if pml else 'physical120_rebuilt',
        stage4_boundary_model='pml' if pml else 'dtn_port',
        stage4_dtn_order_policy='manual',diffraction_order_max_m=5,diffraction_order_max_n=9,
        reporting_diffraction_order_max_m=3,reporting_diffraction_order_max_n=7,
        use_pml=pml,pml_top_thickness=10. if pml else 0.,
        pml_bottom_thickness=10. if pml else 0.,pml_alpha=800.,
        stage4_pml_outer_bc='zero_tangential',divergence_penalty=0.)
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

def build_problem(boundary, output_dir, degree=6, *, layers=4, log=print):
    import ufl
    from dolfinx import fem
    from petsc4py import PETSc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.common_3d_forms import _build_variational_forms
    cfg=make_cfg(boundary,degree,layers=layers)
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
    expected={1:82,2:30,3:8}
    if boundary=='pml':expected.update({4:30*layers,5:30*layers})
    actual={int(t):int(np.sum(tags==t)) for t in np.unique(tags)}
    if actual!=expected:raise ValueError(f'Unexpected mesh material counts: {actual} != {expected}')
    return Problem(cfg,mesh_data,V,floquet,a,L,bg)
