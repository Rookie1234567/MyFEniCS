"""Research-only g*Nedelec space with the full three-dimensional Maxwell curl.

Coefficients store the envelope, never pointwise-phased old FE coefficients.
Physical kx/ky, port polarizations and admittances are unchanged. No NN/Riesz.
"""

from dataclasses import replace
import copy

import numpy as np

from src.geometry.fixed_phase_plan import digest


def carrier(cfg, enabled):
    if not enabled:
        return np.zeros(3)
    k = np.asarray([cfg.kx, cfg.ky, 0.0], complex)
    if np.max(abs(k.imag)) > 1e-14:
        raise ValueError("REAL_TRANSVERSE_CARRIER_REQUIRED")
    return k.real


def background(space, cfg, kappa, q):
    import basix.ufl
    from dolfinx import fem
    from src.common.analytic_fields_3d import electric_field_code_values
    from src.solvers.feinn_interpolation import full_moment_element

    custom = full_moment_element(space.element.basix_element, q)
    witness = fem.functionspace(space.mesh, basix.ufl.wrap_element(custom))
    if not np.array_equal(witness.dofmap.list, space.dofmap.list):
        raise ValueError("BACKGROUND_FULL_MOMENT_ORDER_CHANGED")
    field = fem.Function(witness)
    field.interpolate(
        lambda x: (
            electric_field_code_values(cfg, x.T) * np.exp(-1j * (x.T @ kappa))[:, None]
        ).T
    )
    field.x.scatter_forward()
    out = fem.Function(space)
    out.x.array[:] = field.x.array
    return out


def physical_rhs(bundle):
    import ufl
    from petsc4py import PETSc
    from src.solvers.dtn_port_3d import _assemble_mpc_vector

    cfg, setup = bundle["cfg"], bundle["setup"]
    V = setup["spaces"][bundle["degree"]]
    k = np.asarray(cfg.wavevector, complex)
    kappa = np.asarray(bundle["phase_carrier"] or [0, 0, 0], float)
    e = cfg.incident_amplitude * np.asarray(cfg.polarization_vector, complex)
    traction = np.cross(1j * np.cross(k, e), [0, 0, 1])
    x, v = ufl.SpatialCoordinate(V.mesh), ufl.TestFunction(V)
    phase = ufl.exp(
        sum(PETSc.ScalarType(1j * (k[j] - kappa[j])) * x[j] for j in range(3))
    )
    ds = ufl.Measure(
        "ds",
        domain=V.mesh,
        subdomain_data=setup["mesh_data"].facet_tags,
        metadata={"quadrature_degree": bundle["dtn_quadrature_degree"]},
    )
    L = ufl.inner(
        ufl.as_vector(tuple(PETSc.ScalarType(t) for t in traction)) * phase, v
    ) * ds(cfg.tags.z_max)
    b = _assemble_mpc_vector(
        L,
        setup["floquets"][bundle["degree"]].mpc,
        quadrature_degree=bundle["dtn_quadrature_degree"],
    )
    rhs = b.duplicate()
    try:
        bundle["physical_action"].compose_physical_rhs(
            b, bundle["incident_projections"], rhs
        )
    finally:
        b.destroy()
    return rhs, dict(
        generation="original_total_Maxwell_incident_traction_plus_ports",
        phase_carrier=kappa.tolist(),
        physical_wavevector=[[z.real, z.imag] for z in k],
        channels=len(bundle["modes"]),
        phase_application="envelope_MPC_once",
    )


def build_model(
    design,
    degree,
    phase,
    *,
    q=None,
    fixture_zero_carrier=False,
    operators=True,
    topological_ports=False,
    marker=lambda *_: None,
):
    import basix.ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.common.config_3d import SimulationConfig3D
    from src.common.optical_material_table import load_si_optical_constants
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        AirBox3DMesh,
        _mark_boundary_facets,
        _structured_hexa_mesh,
    )
    from src.geometry.neural_micro_pilot import material_tags
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
    )
    from src.solvers.neural_fe_action_packet import array_hash

    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
    ):
        raise RuntimeError("MPI1_COMPLEX128_INT64_ABI_REQUIRED")
    g = design["geometry"]
    q = max(15, 2 * degree + 3) if q is None else int(q)
    mat = load_si_optical_constants(design["wavelength_nm"])
    if (
        mat.provenance["material_table_sha256"]
        != design["materials"]["legacy_table_sha256"]
    ):
        raise ValueError("MATERIAL_TABLE_CHANGED")
    from src.geometry.fixed_phase_plan import INTERFACE_SHA256

    if design["materials"]["interface_sha256"] != INTERFACE_SHA256 or design[
        "materials"
    ]["si_n"] != [0.99988517036884961, 4.3236152269189515e-6]:
        raise ValueError("FROZEN_INTERFACE_MATERIAL_CHANGED")
    silicon = complex(*design["materials"]["si_n"])
    cfg = SimulationConfig3D(
        case_name="fixed_phase_research",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=design["wavelength_nm"],
        period_x=g["bounds_nm"][0][1],
        period_y=g["bounds_nm"][1][1],
        z_min=g["bounds_nm"][2][0],
        z_max=g["bounds_nm"][2][1],
        air_height=g["bounds_nm"][2][1],
        substrate_thickness=-g["bounds_nm"][2][0],
        grating_width_x=g["block_bounds_nm"][0][1] - g["block_bounds_nm"][0][0],
        grating_width_y=g["bounds_nm"][1][1],
        grating_height=g["block_bounds_nm"][2][1],
        interface_z=0,
        n_air=1 + 0j,
        n_substrate=silicon,
        n_grating=silicon,
        mu_r=mat.mu,
        incident_theta_deg=90 - design["incidence"]["grazing_deg"],
        incident_phi_deg=design["incidence"]["azimuth_deg"],
        polarization_kind="s",
        nedelec_degree=degree,
        use_pml=False,
        use_floquet_xy=True,
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="manual",
        diffraction_order_max_m=design["boundary"]["max_m"],
        diffraction_order_max_n=design["boundary"]["max_n"],
        scattering_background="layered",
    )
    if design.get("fixture"):
        cfg = replace(cfg, n_substrate=1 + 0j, n_grating=1 + 0j, grating_height=0.0)
    # Existing solver deliberately uses this explicit opt-in dynamic field.
    cfg.stage4_dtn_quadrature_degree = q
    kappa = carrier(cfg, phase)
    if fixture_zero_carrier:
        if not design.get("fixture"):
            raise ValueError("ZERO_CARRIER_OVERRIDE_IS_FIXTURE_ONLY")
        kappa[:] = 0

    class EnvelopeConfig(SimulationConfig3D):
        @property
        def floquet_phase_x(self):
            return np.exp(1j * (self.kx - kappa[0]) * self.period_x)

        @property
        def floquet_phase_y(self):
            return np.exp(1j * (self.ky - kappa[1]) * self.period_y)

    envelope_cfg = copy.copy(cfg)
    envelope_cfg.__class__ = EnvelopeConfig
    axes = [np.asarray(a, float) for a in g["axis_coordinates_nm"]]
    msh = _structured_hexa_mesh(MPI.COMM_WORLD, *axes)
    cells = np.arange(msh.topology.index_map(3).size_local, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, 3, cells)
    tags, notch = material_tags(
        centers,
        substrate_z=g["substrate_z_nm"],
        block_bounds=g["block_bounds_nm"],
        notch_bounds=g["notch_bounds_nm"],
    )
    if design.get("fixture"):
        tags[:] = cfg.tags.air
    facets, boundary = _mark_boundary_facets(msh, cfg)
    data = AirBox3DMesh(
        msh,
        mesh.meshtags(msh, 3, cells, tags),
        facets,
        boundary,
        "hexahedron",
        tuple(g["cells"]),
        [],
        "frozen_axes",
        {},
        {},
        {},
    )
    space = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", degree))
    floquet = build_double_floquet_mpc(space, data, envelope_cfg)
    modes, rows, mode_hash = build_dynamic_mode_inventory(cfg)
    if len(modes) != design["boundary"]["channels"]:
        raise ValueError("COMPLETE_PHYSICAL_PORT_INVENTORY_REQUIRED")
    setup = dict(
        mesh=msh, mesh_data=data, spaces={degree: space}, floquets={degree: floquet}
    )
    if operators:
        bundle = build_same_mesh_physical_action(
            setup,
            cfg,
            degree,
            mode_inventory=(modes, rows, mode_hash),
            volume_quadrature_metadata=({"quadrature_degree": q},) * 2,
            phase_carrier=tuple(kappa) if phase else None,
            topological_ports=topological_ports,
        )
    else:
        from src.solvers.dtn_port_3d import _incident_projection_onto_top_mode

        bundle = dict(
            cfg=cfg,
            modes=modes,
            incident_projections=[
                _incident_projection_onto_top_mode(m, cfg) for m in modes
            ],
            phase_carrier=tuple(kappa) if phase else None,
            setup=setup,
            degree=degree,
        )
    physical_identity = {
        k: v for k, v in design.items() if k not in ("finite_element", "geometry")
    }
    physical_identity["geometry"] = {
        k: v
        for k, v in g.items()
        if k not in ("axis_coordinates_nm", "cells", "mesh_id")
    }
    provenance = dict(
        selection=design["materials"],
        actual_n=[silicon.real, silicon.imag],
        actual_epsilon=[(silicon**2).real, (silicon**2).imag],
        legacy_table_read_only=mat.provenance,
        legacy_0p7_entry_used=False,
    )
    record = dict(
        material=provenance,
        modes=rows,
        mode_manifest_sha256=mode_hash,
        channels=len(modes),
        degree=degree,
        phase_carrier=kappa.tolist(),
        field_space="g*periodic_N1curl" if phase else "ordinary_Floquet_N1curl",
        mesh_coordinates_sha256=array_hash(msh.geometry.x),
        geometry_cell_dofs_sha256=array_hash(msh.geometry.dofmap),
        cell_tags_sha256=array_hash(tags),
        centers_sha256=array_hash(centers),
        cells=len(cells),
        actual_material_cell_counts={
            str(int(t)): int(sum(tags == t)) for t in np.unique(tags)
        },
        actual_notch_cells=int(sum(notch)),
        nonseparable_y_z_witness=bool(
            len(np.unique(centers[notch, 1])) > 1
            and len(np.unique(centers[notch, 2])) > 1
        ),
        native_rows=space.dofmap.index_map.size_local,
        slaves=len(floquet.mpc.slaves),
        volume_quadrature_degree=q,
        dtn_quadrature_degree=q,
        physical_model_sha256=digest(physical_identity),
        discretization_sha256=digest(
            dict(design=design, degree=degree, kappa=kappa.tolist(), q=q)
        ),
    )
    marker("physical_model", record)
    return dict(
        cfg=cfg,
        data=data,
        space=space,
        floquet=floquet,
        bundle=bundle,
        centers=centers,
        tags=tags,
        axes=axes,
        record=record,
        kappa=kappa,
        design=design,
        rhs_factory=physical_rhs,
        tensor_class_key=lambda tag, coords, info: (
            tag,
            np.round(coords, 13).tobytes(),
            info,
        ),
        background_factory=lambda V, c: background(V, c, kappa, q),
    )


def physical_fields(model, envelope):
    """Return UFL E and physical curl(E); no curl(u)-only H path."""
    import ufl
    from petsc4py import PETSc

    x = ufl.SpatialCoordinate(model["data"].mesh)
    kappa = ufl.as_vector(tuple(PETSc.ScalarType(k) for k in model["kappa"]))
    g = ufl.exp(PETSc.ScalarType(1j) * ufl.dot(kappa, x))
    return g * envelope, g * (ufl.curl(envelope) + 1j * ufl.cross(kappa, envelope))
