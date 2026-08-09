from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance
from src.solvers.hcurl_canonical_vector_dolfinx import (
    _entity_coordinates,
    _owned_entity_incidents,
    _physical_entity_transform,
)
from src.geometry.tetra_mesh_audit import canonical_entity_key
from src.solvers.fullspace_matrix_free_hcurl import (
    build_task037_extra_candidate_h_fullspace_action,
)


def _physical_cell_tags(mesh_3d, cfg) -> tuple[object, np.ndarray]:
    tdim = mesh_3d.topology.dim
    owned_cells = int(mesh_3d.topology.index_map(tdim).size_local)
    coordinates = np.asarray(mesh_3d.geometry.x, dtype=np.float64)
    x_mid = 0.5 * (float(cfg.x_min) + float(cfg.x_max))
    tags = np.empty(owned_cells, dtype=np.int32)
    for cell in range(owned_cells):
        points = np.asarray(mesh_3d.geometry.dofmap[cell], dtype=np.int32)
        center = np.mean(coordinates[points], axis=0)
        tags[cell] = 1 if float(center[0]) < x_mid else 2
    cell_tags = mesh.meshtags(
        mesh_3d,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        tags,
    )
    return cell_tags, tags


def _build_case(degree: int, comm):
    cfg = target_stage4_config(degree=degree, h_nm=1000.0)
    cfg = replace(cfg, incident_theta_deg=37.0, incident_phi_deg=23.0)
    points = (
        np.asarray(
            (cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64
        ),
        np.asarray(
            (cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64
        ),
    )
    mesh_3d = mesh.create_box(
        comm,
        points,
        (2, 2, 2),
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    fdim = mesh_3d.topology.dim - 1
    boundary_specs = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
    )
    facet_indices = []
    facet_values = []
    for tag, marker in boundary_specs:
        facets = mesh.locate_entities_boundary(mesh_3d, fdim, marker)
        facet_indices.append(facets)
        facet_values.append(np.full(len(facets), tag, dtype=np.int32))
    facet_index = np.concatenate(facet_indices).astype(np.int32)
    facet_value = np.concatenate(facet_values).astype(np.int32)
    order = np.argsort(facet_index)
    mesh_data = SimpleNamespace(
        mesh=mesh_3d,
        facet_tags=mesh.meshtags(
            mesh_3d, fdim, facet_index[order], facet_value[order]
        ),
    )
    cell_tags, tags = _physical_cell_tags(mesh_3d, cfg)
    function_space = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    terms = []
    coefficients = {
        1: (PETSc.ScalarType(1.0 + 0.17j), PETSc.ScalarType(2.1 - 0.3j)),
        2: (PETSc.ScalarType(1.6 - 0.21j), PETSc.ScalarType(0.7 + 0.41j)),
    }
    for tag, (curl_coefficient, mass_coefficient) in coefficients.items():
        terms.append(
            (
                curl_coefficient * ufl.inner(ufl.curl(u), ufl.curl(v))
                + mass_coefficient * ufl.inner(u, v)
            )
            * dx(tag)
        )
    form = fem.form(sum(terms))
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    return cfg, mesh_data, function_space, cell_tags, tags, floquet, form


def _physical_source(function_space, mpc) -> PETSc.Vec:
    field = fem.Function(function_space)
    field.interpolate(
        lambda x: np.vstack(
            (
                1.0 + 0.2 * x[0] - 0.11 * x[2],
                -0.4 + 0.13 * x[1] + 0.07 * x[2],
                0.25 + 0.09 * x[0] - 0.17 * x[1],
            )
        ).astype(np.complex128)
    )
    field.x.scatter_forward()
    source = create_vector(
        [(mpc.function_space.dofmap.index_map, mpc.function_space.dofmap.index_map_bs)]
    )
    owned = int(mpc.function_space.dofmap.index_map.size_local)
    with source.localForm() as local:
        local.set(0.0)
        local.array_w[:owned] = field.x.array[:owned]
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    mpc.backsubstitution(source)
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return source


def _dual_packet(function_space, mpc, vector, tolerance: float):
    mesh_3d = function_space.mesh
    topology = mesh_3d.topology
    topology.create_entity_permutations()
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, topology.dim)
        topology.create_connectivity(topology.dim, dimension)
    layout = function_space.dofmap.dof_layout
    element_data = function_space.element
    degree = int(element_data.basix_element.degree)
    cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    owned_size = int(function_space.dofmap.index_map.size_local)
    extended = create_vector(
        [(mpc.function_space.dofmap.index_map, mpc.function_space.dofmap.index_map_bs)]
    )
    try:
        with extended.localForm() as local:
            local.set(0.0)
            local.array_w[:owned_size] = vector.getArray(readonly=True)
        extended.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        with extended.localForm() as local:
            local_values = np.asarray(local.array_r, dtype=np.complex128).copy()
    finally:
        extended.destroy()

    is_slave = np.asarray(mpc.is_slave, dtype=bool)
    packets: dict[tuple[object, ...], complex] = {}

    def add_packet(key, value):
        if key in packets:
            raise AssertionError(f"duplicate dual packet key: {key!r}")
        packets[key] = complex(value)

    for dimension in (1, 2):
        for entity, cell in _owned_entity_incidents(function_space, dimension):
            local_entities = np.asarray(
                topology.connectivity(topology.dim, dimension).links(cell),
                dtype=np.int32,
            )
            local_entity_matches = np.flatnonzero(local_entities == int(entity))
            if local_entity_matches.size != 1:
                raise RuntimeError("entity incidence is not unique")
            local_entity = int(local_entity_matches[0])
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            local_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int32
            )[positions]
            slave_mask = np.asarray(
                [bool(is_slave[int(dof)]) for dof in local_dofs], dtype=bool
            )
            if np.any(slave_mask) and not np.all(slave_mask):
                raise AssertionError("Floquet entity block is partly constrained")
            if np.all(slave_mask):
                continue
            coordinates = _entity_coordinates(function_space, dimension, entity)
            transform, state = _physical_entity_transform(
                coordinates, dimension, degree, tolerance
            )
            canonical_dual = transform.conj().T @ local_values[local_dofs]
            physical_key = canonical_entity_key(coordinates, tolerance)
            for basis, value in enumerate(canonical_dual):
                add_packet((dimension, physical_key, state, basis), value)

    interior_positions = np.asarray(
        element_data.basix_element.entity_dofs[3][0], dtype=np.int32
    )
    owned_cells = int(topology.index_map(topology.dim).size_local)
    dimension = int(element_data.space_dimension)
    for cell in range(owned_cells):
        local_dofs = np.asarray(
            function_space.dofmap.cell_dofs(cell), dtype=np.int32
        )
        stored = local_values[local_dofs].copy()
        for position, local_dof in enumerate(local_dofs):
            if is_slave[int(local_dof)]:
                stored[position] = 0.0
        orientation = np.zeros((dimension, dimension), dtype=np.complex128)
        info = np.asarray([cell_info[cell]], dtype=np.uint32)
        for column in range(dimension):
            basis = np.zeros(dimension, dtype=np.complex128)
            basis[column] = 1.0
            element_data.T_apply(basis, info, 1)
            orientation[:, column] = basis
        canonical_dual = orientation.conj().T @ stored
        physical_key = canonical_entity_key(
            _entity_coordinates(function_space, 3, cell), tolerance
        )
        for basis, position in enumerate(interior_positions):
            local_dof = int(local_dofs[int(position)])
            if local_dof < owned_size and not is_slave[local_dof]:
                add_packet((3, physical_key, basis), canonical_dual[int(position)])
    return packets


def _merge_packets(comm, local_packets):
    merged = {}
    duplicate_count = 0
    for packet in comm.allgather(local_packets):
        for key, value in packet.items():
            if key in merged:
                duplicate_count += 1
            merged[key] = value
    return merged, duplicate_count


@pytest.mark.parametrize("degree", [2, 3])
def test_fullspace_mpc_action_and_dual_packets_are_partition_invariant(degree: int):
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("test272 is qualified only for COMM_WORLD size 1 or 2")
    (
        cfg,
        mesh_data,
        function_space,
        cell_tags,
        tags,
        floquet,
        form,
    ) = _build_case(degree, comm)
    assembled = dolfinx_mpc.assemble_matrix(
        form, floquet.mpc, diagval=PETSc.ScalarType(1.0)
    )
    assembled.assemble()
    action = build_task037_extra_candidate_h_fullspace_action(
        form,
        function_space,
        cell_tags,
        mpc=floquet.mpc,
        task037_extra_candidate_h=True,
        geometry_tolerance=floquet_geometry_tolerance(cfg),
    )
    source = _physical_source(function_space, floquet.mpc)
    expected = assembled.createVecLeft()
    observed = assembled.createVecLeft()
    repeated = assembled.createVecLeft()
    difference = assembled.createVecLeft()
    serial_assembled = None
    serial_action = None
    serial_source = None
    serial_observed = None
    try:
        assembled.mult(source, expected)
        action.matrix.mult(source, observed)
        action.matrix.mult(source, repeated)
        observed.copy(result=difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        relative_error = difference.norm() / max(expected.norm(), 1.0e-30)
        assert relative_error <= 1.0e-11
        assert np.array_equal(
            observed.getArray(readonly=True), repeated.getArray(readonly=True)
        )
        assert np.all(np.isfinite(observed.getArray(readonly=True)))
        owned_size = int(function_space.dofmap.index_map.size_local)
        slave_indices = np.asarray(floquet.mpc.slaves, dtype=np.int32)
        owned_slaves = slave_indices[slave_indices < owned_size]
        np.testing.assert_array_equal(
            observed.getArray(readonly=True)[owned_slaves],
            source.getArray(readonly=True)[owned_slaves],
        )

        topology = floquet.phase_independent_topology
        assert topology is not None
        assert {block.kind for block in topology.blocks} >= {"x", "y", "corner"}
        assert {block.entity_kind for block in topology.blocks} >= {"edge", "face"}
        assert floquet.num_edge_constraints > 0
        assert floquet.num_face_constraints > 0
        assert abs(complex(floquet.phase_x) - 1.0) > 1.0e-12
        assert abs(complex(floquet.phase_y) - 1.0) > 1.0e-12
        cell_infos = np.asarray(
            mesh_data.mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        local_any_nonzero = bool(
            np.any(cell_infos[: mesh_data.mesh.topology.index_map(3).size_local] != 0)
        )
        assert comm.allreduce(local_any_nonzero, op=MPI.LOR)
        global_tags = set().union(*comm.allgather(set(int(tag) for tag in tags)))
        assert global_tags == {1, 2}
        assert action.audit["mpc_enabled"] is True
        assert action.audit["mpc_metadata_cached"] is True
        assert action.audit["mpc_per_apply_collective"] is False
        assert action.audit["global_constraint_matrix_materialized"] is False

        tolerance = floquet_geometry_tolerance(cfg)
        local_packets = _dual_packet(
            function_space, floquet.mpc, observed, tolerance
        )
        world_packets, duplicate_count = _merge_packets(comm, local_packets)
        if comm.size == 1:
            serial_packet = world_packets
        else:
            serial_cfg, _, serial_space, serial_tags, _, serial_floquet, serial_form = (
                _build_case(degree, MPI.COMM_SELF)
            )
            serial_assembled = dolfinx_mpc.assemble_matrix(
                serial_form,
                serial_floquet.mpc,
                diagval=PETSc.ScalarType(1.0),
            )
            serial_assembled.assemble()
            serial_action = build_task037_extra_candidate_h_fullspace_action(
                serial_form,
                serial_space,
                serial_tags,
                mpc=serial_floquet.mpc,
                task037_extra_candidate_h=True,
                geometry_tolerance=floquet_geometry_tolerance(serial_cfg),
            )
            serial_source = _physical_source(serial_space, serial_floquet.mpc)
            serial_observed = serial_assembled.createVecLeft()
            serial_action.matrix.mult(serial_source, serial_observed)
            serial_packets = _dual_packet(
                serial_space,
                serial_floquet.mpc,
                serial_observed,
                floquet_geometry_tolerance(serial_cfg),
            )
            serial_packet = serial_packets
        missing = set(serial_packet).difference(world_packets)
        extra = set(world_packets).difference(serial_packet)
        assert not missing
        assert not extra
        assert duplicate_count == 0
        expected_reduced_dual_rows = (
            int(action.audit["global_rows"]) - int(floquet.num_constraints)
        )
        assert len(world_packets) == expected_reduced_dual_rows
        assert len(serial_packet) == expected_reduced_dual_rows
        values_world = np.asarray(
            [world_packets[key] for key in sorted(world_packets, key=repr)],
            dtype=np.complex128,
        )
        values_serial = np.asarray(
            [serial_packet[key] for key in sorted(serial_packet, key=repr)],
            dtype=np.complex128,
        )
        packet_error = np.linalg.norm(values_world - values_serial) / max(
            np.linalg.norm(values_serial), 1.0e-30
        )
        assert packet_error <= 1.0e-11
        assert len(world_packets) == len(serial_packet)
        global_permutation_values = sorted(
            {
                int(value)
                for packet in comm.allgather(
                    [
                        int(value)
                        for value in cell_infos[
                            : int(
                                mesh_data.mesh.topology.index_map(3).size_local
                            )
                        ]
                    ]
                )
                for value in packet
            }
        )
        if comm.rank == 0:
            print(
                {
                    "degree": degree,
                    "assembled_vs_mf_relative_error": relative_error,
                    "finite": True,
                    "repeated_bitwise_equal": True,
                    "world_dual_packet_relative_error": packet_error,
                    "world_dual_packet_count": len(world_packets),
                    "serial_dual_packet_count": len(serial_packet),
                    "missing": len(missing),
                    "extra": len(extra),
                    "duplicate": duplicate_count,
                    "phase_x": complex(floquet.phase_x),
                    "phase_y": complex(floquet.phase_y),
                    "global_material_tags": sorted(global_tags),
                    "global_permutation_unique_values": global_permutation_values,
                    "edge_constraints": int(floquet.num_edge_constraints),
                    "face_constraints": int(floquet.num_face_constraints),
                    "global_constraints": int(floquet.num_constraints),
                    "local_constraints": len(floquet.mpc.slaves),
                    "owned_constraints": int(floquet.mpc.num_local_slaves),
                    "audit": {
                        key: action.audit[key]
                        for key in (
                            "global_rows",
                            "local_owned_rows",
                            "local_cell_count",
                            "cell_dof_count",
                            "mpc_local_slave_count",
                            "mpc_owned_slave_count",
                            "mpc_constraint_nnz",
                            "global_matrix_materialized",
                            "retained_cell_dense_matrix_count",
                            "cell_tensor_scratch_count",
                            "cell_tensor_scratch_reused",
                            "global_constraint_matrix_materialized",
                        )
                    },
                }
            )
    finally:
        if serial_observed is not None:
            serial_observed.destroy()
        if serial_source is not None:
            serial_source.destroy()
        if serial_action is not None:
            serial_action.destroy()
        if serial_assembled is not None:
            serial_assembled.destroy()
        difference.destroy()
        repeated.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        assembled.destroy()
