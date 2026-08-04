from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.analytic_fields_3d import electric_field_code_values
from src.constraints.floquet_3d_high_order import build_high_order_constraint_data
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_assembly_time_condensation import (
    _cell_trace_expansion,
    build_unconstrained_assembly_time_condensation,
)
import src.solvers.hcurl_canonical_vector_dolfinx as canonical_module
from src.geometry.tetra_mesh_audit import mesh_coordinate_tolerance
from src.solvers.hcurl_canonical_vector import canonical_key, compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
    extract_canonical_full_fe_packets,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture
from src.test.test_46_task033_high_order_floquet_topology import _fixed_target_fixture


def _set_global_vector_values(vector: PETSc.Vec) -> None:
    first, last = vector.getOwnershipRange()
    values = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = values + 1j * (values + 1.0) / 11.0
    vector.assemble()


def _physical_field(x):
    return np.vstack(
        (
            x[0] + 2.0 * x[1] + 3.0 * x[2] + 1j * (1.0 + x[0]),
            2.0 * x[0] - x[1] + 0.5 * x[2] + 1j * (2.0 + x[1]),
            -x[0] + 3.0 * x[1] - 2.0 * x[2] + 1j * (3.0 + x[2]),
        )
    )


def _active_from_field(V, condensed, field):
    active = condensed.matrix.createVecRight()
    original_to_active = condensed.trace_constraints.original_to_active
    index_map = V.dofmap.index_map
    local_global = index_map.local_to_global(
        np.arange(index_map.size_local, dtype=np.int32)
    )
    for local, original in enumerate(local_global):
        active_id = original_to_active.get(int(original))
        if active_id is not None:
            active.setValue(int(active_id), field.x.array[local])
    active.assemble()
    return active


def _static_fixture(comm):
    mesh_3d, cell_tags, V, compiled = _build_fixture(comm)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
    )
    return mesh_3d, V, condensed


class TestTask037CanonicalVectorDolfinx(unittest.TestCase):
    def test_active_expansion_matches_full_trace_and_entity_packets(self) -> None:
        mesh_3d, V, condensed = _static_fixture(MPI.COMM_SELF)
        active = condensed.matrix.createVecRight()
        _set_global_vector_values(active)
        field = fem.Function(V)
        constraints = condensed.trace_constraints
        global_to_active = constraints.original_to_active
        local_map = V.dofmap.index_map
        local_global = local_map.local_to_global(
            np.arange(local_map.size_local, dtype=np.int32)
        )
        for local, original in enumerate(local_global):
            if int(original) in global_to_active:
                field.x.array[local] = active.getValue(global_to_active[int(original)])
            else:
                field.x.array[local] = 0.25 + 0.5j
        field.x.scatter_forward()
        active_packets, active_audit = extract_canonical_active_trace_packets(
            condensed,
            V,
            None,
            active,
        )
        full_packets, full_audit = extract_canonical_full_fe_packets(
            V,
            field.x.petsc_vec,
            None,
        )
        full_trace = tuple(
            (("active_trace",) + key[1:], value)
            for key, value in full_packets
            if key[1] in (1, 2)
        )
        comparison = compare_canonical_packets(active_packets, full_trace)
        self.assertTrue(comparison["pass"], comparison)
        self.assertEqual(active_audit["local_duplicate_count"], 0)
        self.assertEqual(full_audit["local_duplicate_count"], 0)
        self.assertEqual(
            {key[1] for key, _value in full_packets},
            {1, 2, 3},
        )
        cell = condensed.cell_recovery_maps[0]
        active_ids, expansion, _identity = _cell_trace_expansion(
            cell.trace_original_dofs,
            constraints,
        )
        expected = expansion.dot(
            np.asarray([active.getValue(int(value)) for value in active_ids])
        )
        observed = np.asarray(
            [field.x.array[int(value)] for value in cell.trace_original_dofs]
        )
        np.testing.assert_allclose(observed, expected, atol=1.0e-13, rtol=0.0)
        active.destroy()
        condensed.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size in (2, 4),
        "MPI2/MPI4 owner-local packet qualification",
    )
    def test_mpi_owner_local_packets_have_no_duplicate_physical_keys(self) -> None:
        _mesh, V, condensed = _static_fixture(MPI.COMM_WORLD)
        field = fem.Function(V)
        field.interpolate(_physical_field)
        field.x.scatter_forward()
        active = _active_from_field(V, condensed, field)
        active_packets, active_audit = extract_canonical_active_trace_packets(
            condensed,
            V,
            None,
            active,
        )
        full_packets, full_audit = extract_canonical_full_fe_packets(
            V,
            field.x.petsc_vec,
            None,
        )
        gathered_active = MPI.COMM_WORLD.gather(active_packets, root=0)
        gathered_full = MPI.COMM_WORLD.gather(full_packets, root=0)
        if MPI.COMM_WORLD.rank == 0:
            all_active = tuple(packet for part in gathered_active for packet in part)
            all_full = tuple(packet for part in gathered_full for packet in part)
            self.assertEqual(len(all_active), len({key for key, _value in all_active}))
            self.assertEqual(len(all_full), len({key for key, _value in all_full}))
            self.assertEqual(
                full_audit["global_packet_count"],
                len(all_full),
            )
            self.assertEqual(active_audit["global_packet_count"], len(all_active))
            _ref_mesh, ref_V, ref_condensed = _static_fixture(MPI.COMM_SELF)
            ref_field = fem.Function(ref_V)
            ref_field.interpolate(_physical_field)
            ref_field.x.scatter_forward()
            ref_active = _active_from_field(ref_V, ref_condensed, ref_field)
            ref_active_packets, _ref_active_audit = (
                extract_canonical_active_trace_packets(
                    ref_condensed, ref_V, None, ref_active
                )
            )
            ref_full_packets, _ref_full_audit = extract_canonical_full_fe_packets(
                ref_V, ref_field.x.petsc_vec, None
            )
            self.assertTrue(
                compare_canonical_packets(all_active, ref_active_packets)["pass"]
            )
            self.assertTrue(
                compare_canonical_packets(all_full, ref_full_packets)["pass"]
            )
            ref_active.destroy()
            ref_condensed.destroy()
        self.assertEqual(active_audit["local_duplicate_count"], 0)
        self.assertEqual(full_audit["local_duplicate_count"], 0)
        active.destroy()
        condensed.destroy()

    def test_real_floquet_phases_and_physical_relation_keys(self) -> None:
        cfg, mesh_data, V = _fixed_target_fixture(2, h_nm=50.0)
        field = fem.Function(V)
        field.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
        field.x.scatter_forward()
        floquet = build_double_floquet_mpc(V, mesh_data, cfg)
        packets, audit = extract_canonical_full_fe_packets(
            V,
            field.x.petsc_vec,
            floquet,
        )
        blocks = floquet.phase_independent_topology.blocks
        slave_keys = {
            tuple(sorted(block.slave_entity_geometry_key)) for block in blocks
        }
        master_keys = {
            tuple(sorted(block.master_entity_geometry_key)) for block in blocks
        }
        phase_by_kind = {
            "x": complex(cfg.floquet_phase_x),
            "y": complex(cfg.floquet_phase_y),
            "corner": complex(cfg.floquet_phase_x) * complex(cfg.floquet_phase_y),
        }
        phase_values = {
            tuple(sorted(block.slave_entity_geometry_key)): phase_by_kind[block.kind]
            for block in blocks
        }
        self.assertTrue({block.kind for block in blocks} >= {"x", "y", "corner"})
        self.assertTrue(all(block.has_physical_entity_identity for block in blocks))
        self.assertEqual(audit["local_duplicate_count"], 0)
        phase_keys = [key for key, _value in packets if key[5] is not None]
        self.assertGreater(len(phase_keys), 0)
        self.assertTrue(
            all(
                key[2] in slave_keys
                and key[5] in master_keys
                and key[5] != key[2]
                and key[6]
                == (
                    phase_values[key[2]].real,
                    phase_values[key[2]].imag,
                )
                for key in phase_keys
            )
        )
        self.assertTrue(any(key[6] != (1.0, 0.0) for key in phase_keys))

    def test_nonzero_basix_cell_info_uses_transpose_inverse(self) -> None:
        _cfg, _mesh_data, V = _fixed_target_fixture(4, h_nm=50.0)
        nonzero = 134743045
        values = np.random.default_rng(4183).standard_normal(V.element.space_dimension)
        stored = values.copy()
        V.element.T_apply(stored, np.asarray([nonzero], dtype=np.uint32), 1)
        restored = stored.copy()
        V.element.Tt_apply(restored, np.asarray([nonzero], dtype=np.uint32), 1)
        wrong = stored.copy()
        V.element.Tt_inv_apply(wrong, np.asarray([nonzero], dtype=np.uint32), 1)
        self.assertLess(
            np.linalg.norm(restored - values) / np.linalg.norm(values), 1.0e-12
        )
        self.assertGreater(
            np.linalg.norm(wrong - values) / np.linalg.norm(values), 1.0e-2
        )
        interior = np.asarray(V.element.basix_element.entity_dofs[3][0], dtype=np.int32)
        transform = np.zeros(
            (V.element.space_dimension, V.element.space_dimension), dtype=np.float64
        )
        for column in range(V.element.space_dimension):
            basis = np.zeros(V.element.space_dimension, dtype=np.float64)
            basis[column] = 1.0
            V.element.T_apply(basis, np.asarray([nonzero], dtype=np.uint32), 1)
            transform[:, column] = basis
        self.assertLess(
            np.linalg.norm(
                transform[np.ix_(interior, interior)] - np.eye(len(interior))
            ),
            1.0e-12,
        )
        self.assertLess(
            np.linalg.norm(
                transform[
                    np.ix_(
                        interior, np.setdiff1d(np.arange(transform.shape[0]), interior)
                    )
                ]
            ),
            1.0e-12,
        )
        canonical_module._topology_data(V)
        tolerance = mesh_coordinate_tolerance(V.mesh)
        edge_coords = canonical_module._entity_coordinates(V, 1, 0)
        edge_canonical = np.arange(4, dtype=np.complex128) + 1j * np.arange(1, 5)
        edge_forward = canonical_module.edge_coefficient_transform(
            4, reversed_orientation=False, cell_type="hexahedron"
        )
        edge_reverse = canonical_module.edge_coefficient_transform(
            4, reversed_orientation=True, cell_type="hexahedron"
        )
        edge_a = canonical_module._canonical_entity_values(
            edge_forward @ edge_canonical,
            edge_coords,
            1,
            4,
            tolerance,
            {},
        )
        edge_b = canonical_module._canonical_entity_values(
            edge_reverse @ edge_canonical,
            edge_coords[::-1],
            1,
            4,
            tolerance,
            {},
        )
        self.assertEqual(edge_a[4], edge_b[4])
        np.testing.assert_allclose(edge_a[0], edge_b[0], atol=1.0e-12, rtol=0.0)
        self.assertEqual(
            canonical_key(
                role="full_fe",
                entity_dimension=1,
                physical_entity=edge_a[1],
                entity_local_basis_index=0,
                orientation_state=edge_a[4],
            ),
            canonical_key(
                role="full_fe",
                entity_dimension=1,
                physical_entity=edge_b[1],
                entity_local_basis_index=0,
                orientation_state=edge_b[4],
            ),
        )
        face_coords = canonical_module._entity_coordinates(V, 2, 0)
        face_canonical_coords, face_permutation = (
            canonical_module._entity_canonical_order(face_coords, 2, tolerance)
        )
        face_transform = canonical_module.face_coefficient_transform(
            4, face_permutation
        )
        face_canonical = np.arange(face_transform.shape[1], dtype=np.complex128) + 1j
        face_a = canonical_module._canonical_entity_values(
            face_transform @ face_canonical,
            face_coords,
            2,
            4,
            tolerance,
            {},
        )
        reordered_face = face_coords[[1, 3, 0, 2]]
        _reordered_canonical, reordered_permutation = (
            canonical_module._entity_canonical_order(reordered_face, 2, tolerance)
        )
        reordered_transform = canonical_module.face_coefficient_transform(
            4, reordered_permutation
        )
        face_b = canonical_module._canonical_entity_values(
            reordered_transform @ face_canonical,
            reordered_face,
            2,
            4,
            tolerance,
            {},
        )
        self.assertEqual(face_a[4], face_b[4])
        np.testing.assert_allclose(face_a[0], face_b[0], atol=1.0e-12, rtol=0.0)
        self.assertEqual(
            canonical_key(
                role="full_fe",
                entity_dimension=2,
                physical_entity=face_a[1],
                entity_local_basis_index=0,
                orientation_state=face_a[4],
            ),
            canonical_key(
                role="full_fe",
                entity_dimension=2,
                physical_entity=face_b[1],
                entity_local_basis_index=0,
                orientation_state=face_b[4],
            ),
        )

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 8,
        "the recorded p6/h10 multi-master topology is an MPI8 qualification",
    )
    def test_target_topology_multi_master_block_orientation(self) -> None:
        cfg, mesh_data, V = _fixed_target_fixture(6, h_nm=10.0)
        data = build_high_order_constraint_data(V, mesh_data, cfg)
        tolerance = mesh_coordinate_tolerance(V.mesh)
        topology = V.mesh.topology
        topology.create_entities(2)
        entity_map = topology.index_map(2)
        entity_globals = entity_map.local_to_global(
            np.arange(
                entity_map.size_local + entity_map.num_ghosts,
                dtype=np.int32,
            )
        )
        candidates = []
        for block in data.topology.blocks:
            transform = np.asarray(block.coefficient_transform, dtype=np.complex128)
            row_nnz = max(
                int(np.count_nonzero(np.abs(row) > 1.0e-14)) for row in transform
            )
            local_entities = np.flatnonzero(entity_globals == block.slave_entity_id)
            if row_nnz > 1 and len(local_entities):
                candidates.append((block, transform, row_nnz, int(local_entities[0])))
        global_candidate_count = V.mesh.comm.allreduce(len(candidates), op=MPI.SUM)
        self.assertGreater(data.max_masters_per_slave, 1)
        self.assertGreater(global_candidate_count, 0)
        local_pass = True
        if candidates:
            block, transform, row_nnz, local_entity = candidates[0]
            phase = {
                "x": complex(cfg.floquet_phase_x),
                "y": complex(cfg.floquet_phase_y),
                "corner": complex(cfg.floquet_phase_x) * complex(cfg.floquet_phase_y),
            }[block.kind]
            master = (
                np.arange(transform.shape[1], dtype=np.float64)
                + 1j * (np.arange(transform.shape[1], dtype=np.float64) + 1.0) / 7.0
            )
            slave = phase * transform @ master
            coords = canonical_module._entity_coordinates(V, 2, local_entity)
            floquet_data = SimpleNamespace(
                phase_independent_topology=data.topology,
                phase_x=complex(cfg.floquet_phase_x),
                phase_y=complex(cfg.floquet_phase_y),
                phase_corner=complex(cfg.floquet_phase_x)
                * complex(cfg.floquet_phase_y),
            )
            relations = canonical_module._floquet_relations(floquet_data)
            (
                canonical,
                physical_key,
                floquet_master,
                canonical_phase,
                _state,
            ) = canonical_module._canonical_entity_values(
                slave,
                coords,
                2,
                6,
                tolerance,
                relations,
            )
            local_pass = (
                physical_key == tuple(sorted(block.slave_entity_geometry_key))
                and floquet_master == tuple(sorted(block.master_entity_geometry_key))
                and abs(canonical_phase - phase) <= 1.0e-12
                and np.linalg.norm(canonical - master) / np.linalg.norm(master)
                <= 1.0e-12
                and np.linalg.norm(slave / phase - master) / np.linalg.norm(master)
                > 1.0e-2
                and row_nnz >= 2
            )
        self.assertEqual(
            V.mesh.comm.allreduce(int(local_pass), op=MPI.MIN),
            1,
        )


if __name__ == "__main__":
    unittest.main()
