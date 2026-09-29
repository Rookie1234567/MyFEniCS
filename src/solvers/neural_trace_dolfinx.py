"""Affine N1curl moment packets, independent DOLFINx interpolation witness.

No material functions, Maxwell forms, Schur matrix, inverse or factor is built.
This material-independent interface is not a substitute for a real S/S^H Gate.
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


def extended_moment_element(element, degree):
    """Reintegrate the SAME polynomial moment functionals at higher quadrature.

    Recover their low-degree test polynomials from Basix's own x/M tensors.
    This changes interpolation quadrature, not the N1curl space or FE operator
    quadrature. Interior x/M are kept unchanged; only trace moments are used.
    """
    xs = [[np.array(x, copy=True) for x in dim] for dim in element.x]
    ms = [[np.array(m, copy=True) for m in dim] for dim in element.M]
    geometry = basix.cell.geometry(element.cell_type)
    topology = basix.cell.topology(element.cell_type)
    for dimension in (1, 2):
        for entity, old in enumerate(element.x[dimension]):
            vertices = geometry[topology[dimension][entity]]
            axes = np.flatnonzero(np.ptp(vertices, axis=0) > 0.5)
            count = len(np.unique(np.round(old[:, axes[0]], 12)))
            nodes, weights = np.polynomial.legendre.leggauss(count)
            nodes, weights = (nodes + 1) / 2, weights / 2
            old_weights = np.ones(len(old))
            for axis in axes:
                nearest = np.argmin(abs(old[:, axis, None] - nodes[None, :]), axis=1)
                if np.max(abs(old[:, axis] - nodes[nearest])) > 1e-12:
                    raise ValueError("Basix moment rule is not qualified tensor Gauss")
                old_weights *= weights[nearest]
            powers = list(product(range(count), repeat=dimension))

            def vandermonde(points, axes=axes, powers=powers):
                return np.column_stack(
                    [
                        np.prod(points[:, axes] ** np.asarray(power), axis=1)
                        for power in powers
                    ]
                )

            old_matrix = element.M[dimension][entity][..., 0]
            density = old_matrix / old_weights[None, None, :]
            # A small <=9 square interpolation, never a target operator inverse.
            coefficients = np.linalg.solve(
                vandermonde(old), density.reshape(-1, len(old)).T
            )
            cell = (
                basix.CellType.interval
                if dimension == 1
                else basix.CellType.quadrilateral
            )
            new, new_weights = basix.make_quadrature(cell, degree)
            points = np.tile(vertices.min(axis=0), (len(new), 1))
            points[:, axes] = new
            values = (vandermonde(points) @ coefficients).T.reshape(
                *old_matrix.shape[:2], len(new)
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


def pilot_space(design):
    cfg = geometry_config(design)
    axes = [
        np.linspace(*bounds, count + 1)
        for bounds, count in zip(
            design["geometry"]["bounds_nm"], design["geometry"]["cells"], strict=True
        )
    ]
    msh = _structured_hexa_mesh(MPI.COMM_WORLD, *axes)
    cell_ids = np.arange(msh.topology.index_map(3).size_local, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, 3, cell_ids)
    tags, notch = material_tags(
        centers,
        substrate_z=design["geometry"]["substrate_z_nm"],
        block_bounds=design["geometry"]["block_bounds_nm"],
        notch_bounds=design["geometry"]["notch_bounds_nm"],
    )
    facets, boundary = _mark_boundary_facets(msh, cfg)
    data = AirBox3DMesh(
        msh,
        mesh.meshtags(msh, 3, cell_ids, tags),
        facets,
        boundary,
        "hexahedron",
        (8, 6, 8),
        [],
        "uniform",
        {},
        {},
        {},
    )
    space = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 3))
    return cfg, data, space, centers, tags, notch, axes


def build_packet(space, mpc, quadrature):
    original = space.element.basix_element
    custom = extended_moment_element(original, quadrature)
    witness_space = fem.functionspace(space.mesh, basix.ufl.wrap_element(custom))
    if not np.array_equal(space.dofmap.list, witness_space.dofmap.list):
        raise ValueError("extended quadrature changed native numbering")
    probe = np.asarray([[0.11, 0.23, 0.37], [0.79, 0.61, 0.47]])
    basis_defect = np.linalg.norm(
        original.tabulate(0, probe) - custom.tabulate(0, probe)
    ) / np.linalg.norm(original.tabulate(0, probe))
    if basis_defect > 1e-10:
        raise ValueError("extended moments changed the N1curl basis")
    msh = space.mesh
    msh.topology.create_entity_permutations()
    info = msh.topology.get_cell_permutation_info()
    dimension = original.dim
    interior = np.asarray(original.entity_dofs[3][0], dtype=np.int32)
    trace = np.setdiff1d(np.arange(dimension), interior)
    dofs = np.array([space.dofmap.cell_dofs(i) for i in range(len(info))])
    full_trace = np.unique(dofs[:, trace])
    masters = np.setdiff1d(full_trace, mpc.slaves)
    predicted = hexa_inventory((8, 6, 8), 3)
    if (
        len(masters) != predicted["independent_trace_rows"]
        or len(full_trace) != predicted["full_trace_rows"]
    ):
        raise ValueError("actual trace/MPC counts disagree with geometric inventory")
    master_index = {int(row): index for index, row in enumerate(masters)}
    owner_rows = np.full(dofs.shape, -1, dtype=np.int64)
    assigned = set()
    for cell in range(len(dofs)):
        for position in trace:
            row = int(dofs[cell, position])
            if row in master_index and row not in assigned:
                assigned.add(row)
                owner_rows[cell, position] = master_index[row]
    if len(assigned) != len(masters):
        raise ValueError("unique master owner coverage failed")
    transforms, orientations = [], {}
    for value in np.unique(info):
        transform = np.eye(dimension).reshape(-1)
        witness_space.element.Tt_inv_apply(
            transform, np.asarray([value], dtype=np.uint32), dimension
        )
        orientations[int(value)] = len(transforms)
        transforms.append(transform.reshape(dimension, dimension))
    reference_vertices = basix.cell.geometry(basix.CellType.hexahedron)
    origins, jacobians = [], []
    for cell in range(len(dofs)):
        vertices = msh.geometry.x[msh.geometry.dofmap[cell]]
        # Geometry is affine: fit the coordinate element's reference vertices.
        fitted = np.linalg.lstsq(
            np.column_stack((np.ones(8), reference_vertices)), vertices, rcond=None
        )[0]
        jacobian = fitted[1:].T
        if (
            np.linalg.norm(
                np.column_stack((np.ones(8), reference_vertices)) @ fitted - vertices
            )
            > 1e-12
            or np.linalg.det(jacobian) <= 0
        ):
            raise ValueError("mesh is not the qualified positive affine hexahedron")
        origins.append(fitted[0])
        jacobians.append(jacobian)
    packet = dict(
        reference_points=np.array(custom.points),
        interpolation=np.array(custom.interpolation_matrix),
        transforms=np.array(transforms),
        orientation_ids=np.asarray([orientations[int(i)] for i in info]),
        origins=np.array(origins),
        jacobians=np.array(jacobians),
        owner_rows=owner_rows,
        active_rows=np.asarray(len(masters)),
        master_native_rows=masters,
        native_cell_dofs=dofs,
        quadrature_degree=np.asarray(quadrature),
        basis_defect=np.asarray(basis_defect),
    )
    return packet, witness_space


def interpolation_checks(packet, witness_space, mpc):
    def field(points):
        x, y, z = np.asarray(points).T
        return np.column_stack(
            (
                1 + x * y + 0.2j * z**2,
                0.7 + y * z + 0.4j * x**2,
                0.3 + x * z + 0.6j * y**2,
            )
        )

    reference = fem.Function(witness_space)
    reference.interpolate(lambda x: field(x.T).T)
    mapped = moment_packet_values(packet, field)
    native = reference.x.array[packet["master_native_rows"]]
    interpolation_defect = float(
        np.linalg.norm(mapped - native) / np.linalg.norm(native)
    )
    active = fem.Function(mpc.function_space)
    active.x.array[:] = 0
    active.x.array[packet["master_native_rows"]] = mapped
    slave_zero_before = float(np.linalg.norm(active.x.array[mpc.slaves]))
    mpc.backsubstitution(active)
    coefficients, offsets = mpc.coefficients()
    defects = []
    for slave in mpc.slaves:
        masters = mpc.masters.links(int(slave))
        values = coefficients[offsets[slave] : offsets[slave + 1]]
        expected = np.dot(values, active.x.array[masters])
        defects.append(active.x.array[slave] - expected)
    constraint_defect = float(np.linalg.norm(defects) / np.linalg.norm(active.x.array))
    cell_infos = witness_space.mesh.topology.get_cell_permutation_info()
    if not np.any(cell_infos):
        raise ValueError("orientation witness contains no nontrivial cells")
    passed = (
        interpolation_defect <= 1e-10
        and constraint_defect <= 1e-10
        and slave_zero_before == 0
    )
    return dict(
        status="PASS" if passed else "FAIL",
        interpolation_relative=interpolation_defect,
        mpc_expansion_relative=constraint_defect,
        slave_zero_before_expansion=slave_zero_before,
        nonzero_master_norm=float(np.linalg.norm(mapped)),
        nontrivial_orientation_cells=int(np.count_nonzero(cell_infos)),
        orientation_classes=len(np.unique(cell_infos)),
        interpolation_basis_relative=float(packet["basis_defect"]),
        test_field="nonzero complex polynomial, not the target solution",
        true_S_gate="NOT_RUN_MATERIAL_BLOCKED",
        local_recovery_gate="NOT_RUN_MATERIAL_BLOCKED",
    )
