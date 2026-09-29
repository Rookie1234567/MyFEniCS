"""Complete edge, face AND interior Nedelec moments on affine hexes.

Extends the frozen trace adapter's Basix moment-density reconstruction to
dimension three. Unique native owners cover every independent FE unknown.
"""

from itertools import product

import basix
import basix.ufl
import numpy as np
from dolfinx import fem, mesh
from mpi4py import MPI

from src.geometry.mesh_builder_3d import (
    AirBox3DMesh,
    _mark_boundary_facets,
    _structured_hexa_mesh,
)
from src.geometry.neural_micro_pilot import (
    geometry_config,
    hexa_inventory,
    material_tags,
)
from src.solvers.neural_trace import moment_packet_values


def full_moment_element(element, degree):
    xs = [[np.array(x, copy=True) for x in dim] for dim in element.x]
    ms = [[np.array(m, copy=True) for m in dim] for dim in element.M]
    geometry, topology = (
        basix.cell.geometry(element.cell_type),
        basix.cell.topology(element.cell_type),
    )
    for dimension in (1, 2, 3):
        for entity, old in enumerate(element.x[dimension]):
            if not len(old):
                continue
            vertices = geometry[topology[dimension][entity]]
            axes = np.flatnonzero(np.ptp(vertices, axis=0) > 0.5)
            count = len(np.unique(np.round(old[:, axes[0]], 12)))
            nodes, weights = np.polynomial.legendre.leggauss(count)
            nodes, weights = (nodes + 1) / 2, weights / 2
            old_weights = np.ones(len(old))
            for axis in axes:
                nearest = np.argmin(abs(old[:, axis, None] - nodes[None, :]), axis=1)
                if np.max(abs(old[:, axis] - nodes[nearest])) > 1e-12:
                    raise ValueError(
                        "Basix complete moments require qualified tensor Gauss rule"
                    )
                old_weights *= weights[nearest]
            powers = list(product(range(count), repeat=dimension))

            def vandermonde(points):
                return np.column_stack(
                    [
                        np.prod(points[:, axes] ** np.asarray(power), axis=1)
                        for power in powers
                    ]
                )

            original = element.M[dimension][entity][..., 0]
            density = original / old_weights[None, None, :]
            coefficients = np.linalg.solve(
                vandermonde(old), density.reshape(-1, len(old)).T
            )
            cell_type = (
                basix.CellType.interval,
                basix.CellType.quadrilateral,
                basix.CellType.hexahedron,
            )[dimension - 1]
            new, new_weights = basix.make_quadrature(cell_type, degree)
            points = np.tile(vertices.min(axis=0), (len(new), 1))
            points[:, axes] = new
            values = (vandermonde(points) @ coefficients).T.reshape(
                *original.shape[:2], len(new)
            )
            xs[dimension][entity] = np.ascontiguousarray(points)
            ms[dimension][entity] = np.ascontiguousarray(
                (values * new_weights[None, None, :])[..., None]
            )
    return basix.create_custom_element(
        element.cell_type,
        element.value_shape,
        element.wcoeffs,
        xs,
        ms,
        element.interpolation_nderivs,
        element.map_type,
        element.sobolev_space,
        False,
        element.embedded_subdegree,
        element.embedded_superdegree,
        element.polyset_type,
    )


def full_space(design, degree=None):
    degree = design["finite_element"]["degree"] if degree is None else degree
    cfg = geometry_config(design)
    g = design["geometry"]
    axes = [
        np.linspace(*bounds, count + 1)
        for bounds, count in zip(g["bounds_nm"], g["cells"], strict=True)
    ]
    msh = _structured_hexa_mesh(MPI.COMM_WORLD, *axes)
    cells = np.arange(msh.topology.index_map(3).size_local, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, 3, cells)
    tags, notch = material_tags(
        centers,
        substrate_z=g["substrate_z_nm"],
        block_bounds=g["block_bounds_nm"],
        notch_bounds=g["notch_bounds_nm"],
    )
    facets, boundary = _mark_boundary_facets(msh, cfg)
    data = AirBox3DMesh(
        msh,
        mesh.meshtags(msh, 3, cells, tags),
        facets,
        boundary,
        "hexahedron",
        tuple(g["cells"]),
        [],
        "uniform",
        {},
        {},
        {},
    )
    space = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", degree))
    return cfg, data, space, centers, tags, notch, axes


def build_full_moments(space, mpc, quadrature, counts):
    original = space.element.basix_element
    custom = full_moment_element(original, quadrature)
    witness = fem.functionspace(space.mesh, basix.ufl.wrap_element(custom))
    if not np.array_equal(space.dofmap.list, witness.dofmap.list):
        raise ValueError("complete moment quadrature changed native numbering")
    probes = np.asarray([[0.11, 0.23, 0.37], [0.79, 0.61, 0.47]])
    defect = np.linalg.norm(
        original.tabulate(0, probes) - custom.tabulate(0, probes)
    ) / np.linalg.norm(original.tabulate(0, probes))
    if defect > 1e-10:
        raise ValueError("complete moments changed the original FE basis")
    msh = space.mesh
    msh.topology.create_entity_permutations()
    info = msh.topology.get_cell_permutation_info()
    dofs = np.array(space.dofmap.list, dtype=np.int64)
    native_rows = space.dofmap.index_map.size_local
    masters = np.setdiff1d(np.arange(native_rows), mpc.slaves)
    predicted = hexa_inventory(counts, original.degree)
    if (
        native_rows != predicted["full_fe_rows"]
        or len(masters) != native_rows - predicted["periodic_slaves"]
    ):
        raise ValueError("full independent FE count disagrees with topology")
    lookup = {int(row): i for i, row in enumerate(masters)}
    owner_rows = np.full(dofs.shape, -1, dtype=np.int64)
    assigned = set()
    for cell, rows in enumerate(dofs):
        for position, row in enumerate(rows):
            if int(row) in lookup and int(row) not in assigned:
                owner_rows[cell, position] = lookup[int(row)]
                assigned.add(int(row))
    if len(assigned) != len(masters):
        raise ValueError("unique owner misses independent edge/face/interior DOFs")
    transforms, orientations = [], {}
    for value in np.unique(info):
        matrix = np.eye(original.dim).ravel()
        witness.element.Tt_inv_apply(
            matrix, np.asarray([value], dtype=np.uint32), original.dim
        )
        orientations[int(value)] = len(transforms)
        transforms.append(matrix.reshape(original.dim, original.dim))
    reference_vertices = basix.cell.geometry(basix.CellType.hexahedron)
    fit_matrix = np.column_stack((np.ones(8), reference_vertices))
    origins, jacobians = [], []
    for cell in range(len(dofs)):
        vertices = msh.geometry.x[msh.geometry.dofmap[cell]]
        fitted = np.linalg.lstsq(fit_matrix, vertices, rcond=None)[0]
        jacobian = fitted[1:].T
        if (
            np.linalg.norm(fit_matrix @ fitted - vertices) > 1e-11
            or np.linalg.det(jacobian) <= 0
        ):
            raise ValueError("positive affine mapping required")
        origins.append(fitted[0])
        jacobians.append(jacobian)
    packet = dict(
        reference_points=np.array(custom.points),
        interpolation=np.array(custom.interpolation_matrix),
        transforms=np.array(transforms),
        orientation_ids=np.asarray([orientations[int(v)] for v in info]),
        origins=np.array(origins),
        jacobians=np.array(jacobians),
        owner_rows=owner_rows,
        active_rows=np.asarray(len(masters)),
        master_native_rows=masters,
        native_cell_dofs=dofs,
        quadrature_degree=np.asarray(quadrature),
        basis_defect=np.asarray(defect),
        interior_positions=np.asarray(original.entity_dofs[3][0]),
        edge_positions=np.concatenate([np.asarray(x) for x in original.entity_dofs[1]]),
        face_positions=np.concatenate([np.asarray(x) for x in original.entity_dofs[2]]),
    )
    return packet, witness


def complete_interpolation_check(packet, space, witness, mpc):
    def field(points):
        x, y, z = points.T
        return np.column_stack(
            (
                1 + x * y + 0.2j * z * z,
                0.7 + y * z + 0.4j * x * x,
                0.3 + x * z + 0.6j * y * y,
            )
        )

    expected = fem.Function(space)
    expected.interpolate(lambda x: field(x.T).T)
    higher = fem.Function(witness)
    higher.interpolate(lambda x: field(x.T).T)
    mapped = moment_packet_values(packet, field)
    masters = packet["master_native_rows"]
    paired = float(
        np.linalg.norm(mapped - expected.x.array[masters])
        / np.linalg.norm(expected.x.array[masters])
    )
    high_pair = float(
        np.linalg.norm(mapped - higher.x.array[masters])
        / np.linalg.norm(higher.x.array[masters])
    )
    component_checks = {}
    for name in ("edge", "face", "interior"):
        indices = packet["owner_rows"][:, packet[name + "_positions"]].ravel()
        indices = indices[indices >= 0]
        native = expected.x.array[masters[indices]]
        component_checks[name] = dict(
            count=len(indices),
            nonzero_norm=float(np.linalg.norm(native)),
            relative=float(
                np.linalg.norm(mapped[indices] - native) / np.linalg.norm(native)
            ),
        )
    values = fem.Function(mpc.function_space)
    values.x.array[:] = 0
    values.x.array[masters] = mapped
    mpc.backsubstitution(values)
    coefficients, offsets = mpc.coefficients()
    defects = []
    for slave in mpc.slaves:
        links = mpc.masters.links(int(slave))
        phase = coefficients[offsets[slave] : offsets[slave + 1]]
        defects.append(values.x.array[slave] - np.dot(phase, values.x.array[links]))
    shared = []
    # Test shared native moments with all cells, including non-owner entities.
    for cell, dofs in enumerate(packet["native_cell_dofs"]):
        j = packet["jacobians"][cell]
        physical = packet["origins"][cell] + packet["reference_points"] @ j.T
        moments = packet["interpolation"] @ (field(physical) @ j).T.reshape(-1)
        oriented = packet["transforms"][packet["orientation_ids"][cell]] @ moments
        shared.append(np.linalg.norm(oriented - expected.x.array[dofs]) ** 2)
    shared_relative = float(
        np.sqrt(sum(shared))
        / np.linalg.norm(expected.x.array[packet["native_cell_dofs"]])
    )
    constraint = float(np.linalg.norm(defects) / np.linalg.norm(values.x.array))
    nonzero_phase = bool(np.any(np.abs(coefficients.imag) > 1e-8))
    passed = (
        max(paired, high_pair, shared_relative, constraint) <= 1e-10 and nonzero_phase
    )
    return dict(
        status="PASS" if passed else "FULL_INTERPOLATION_FAILED",
        interpolation_relative=paired,
        independent_custom_relative=high_pair,
        shared_entity_relative=shared_relative,
        component_checks=component_checks,
        mpc_expansion_relative=constraint,
        nonzero_slave_phase=nonzero_phase,
        orientation_classes=len(packet["transforms"]),
        basis_relative=float(packet["basis_defect"]),
        full_independent_rows=len(masters),
        reference_loaded=False,
    )
