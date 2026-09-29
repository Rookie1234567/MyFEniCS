"""Review V3 micro geometry; material tags do not supply optical constants.

Research-only, parameterized box/substrate/block/notch tagging. Ordinary mesh
builders and the historical z40--80 notch recipe are deliberately untouched.
"""

import numpy as np


def box_mask(points, bounds):
    points = np.asarray(points, dtype=np.float64)
    bounds = np.asarray(bounds, dtype=np.float64)
    return np.all((points >= bounds[:, 0]) & (points <= bounds[:, 1]), axis=1)


def material_tags(points, *, substrate_z, block_bounds, notch_bounds):
    points = np.asarray(points, dtype=np.float64)
    tags = np.ones(len(points), dtype=np.int32)
    tags[points[:, 2] < float(substrate_z)] = 2
    block = box_mask(points, block_bounds)
    tags[block] = 3
    notch = block & box_mask(points, notch_bounds)
    tags[notch] = 1
    return tags, notch


def hexa_inventory(cells, degree):
    """Exact conforming N1curl counts, periodic in x/y and open in z."""
    nx, ny, nz = map(int, cells)
    p = int(degree)
    edges = (
        nx * (ny + 1) * (nz + 1) + ny * (nx + 1) * (nz + 1) + nz * (nx + 1) * (ny + 1)
    )
    faces = nx * ny * (nz + 1) + nx * nz * (ny + 1) + ny * nz * (nx + 1)
    periodic_edges = 2 * nx * ny * (nz + 1) + nx * ny * nz
    periodic_faces = nx * ny * (nz + 1) + 2 * nx * ny * nz
    interior = 3 * p * (p - 1) ** 2 * nx * ny * nz
    trace = edges * p + faces * 2 * p * (p - 1)
    active_trace = periodic_edges * p + periodic_faces * 2 * p * (p - 1)
    return dict(
        cells=nx * ny * nz,
        degree=p,
        cell_dimension=3 * p * (p + 1) ** 2,
        full_fe_rows=trace + interior,
        full_trace_rows=trace,
        independent_trace_rows=active_trace,
        interior_rows=interior,
        edges=edges,
        faces=faces,
        periodic_slaves=trace - active_trace,
    )


def geometry_config(design):
    """Geometry/phase carrier ONLY; never construct forms from this config.

    Unknown Si indices remain None. SimulationConfig3D has legacy air fallback
    properties, so this helper is restricted to mesh/space/Floquet extraction.
    """
    from src.common.config_3d import SimulationConfig3D

    g = design["geometry"]
    block = g["block_bounds_nm"]
    return SimulationConfig3D(
        case_name="task042_v6_geometry_only",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=design["wavelength_nm"],
        period_x=g["bounds_nm"][0][1] - g["bounds_nm"][0][0],
        period_y=g["bounds_nm"][1][1] - g["bounds_nm"][1][0],
        z_min=g["bounds_nm"][2][0],
        z_max=g["bounds_nm"][2][1],
        air_height=g["bounds_nm"][2][1],
        substrate_thickness=-g["bounds_nm"][2][0],
        grating_width_x=block[0][1] - block[0][0],
        grating_width_y=block[1][1] - block[1][0],
        grating_height=block[2][1],
        interface_z=g["substrate_z_nm"],
        n_air=1 + 0j,
        n_substrate=None,
        n_grating=None,
        mu_r=1 + 0j,
        incident_theta_deg=89.0,
        incident_phi_deg=0.0,
        polarization_kind="s",
        custom_polarization=None,
        use_floquet_xy=True,
        use_pml=False,
        nedelec_degree=3,
        diffraction_zero_order_only=False,
    )


def air_orders(design):
    """Known top-side inventory only. Do NOT evaluate missing substrate index."""
    from src.common.modes_3d import is_propagating, positive_sqrt

    cfg = geometry_config(design)
    k0, kx, ky = cfg.k0, cfg.kx, cfg.ky
    mx = int(np.floor((k0 + abs(kx)) * cfg.period_x / (2 * np.pi) + 1e-12))
    my = int(np.floor((k0 + abs(ky)) * cfg.period_y / (2 * np.pi) + 1e-12))
    orders = []
    for m in range(-mx, mx + 1):
        for n in range(-my, my + 1):
            value = (
                k0**2
                - (kx + 2 * np.pi * m / cfg.period_x) ** 2
                - (ky + 2 * np.pi * n / cfg.period_y) ** 2
            )
            if is_propagating(positive_sqrt(value), value) or (m, n) == (0, 0):
                orders.append([m, n])
    return dict(
        status="TOP_AIR_ONLY_DERIVED",
        orders=orders,
        top_channels=2 * len(orders),
        bottom_channels=None,
        total_channels=None,
        reason="Si0.7nm missing; complete original auto_propagating inventory is blocked",
    )
