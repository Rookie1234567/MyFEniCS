from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI

from src.constraints.high_order_floquet_trace import (
    FloquetTopologyCache,
    FloquetTopologyKey,
    FloquetTraceTopology,
    PhaseIndependentConstraintBlock,
    distributed_match_periodic_records,
    edge_coefficient_transform,
    face_basis_transform,
    face_coefficient_transform,
    high_order_trace_layout,
    quadrilateral_d4_vertex_permutations,
    quadrilateral_face_info,
    stable_pairing_rank,
)


class Task033HighOrderEntityTransformTests(unittest.TestCase):
    def test_p1_to_p4_layout_matches_3d_face_and_2d_cross_section(self) -> None:
        expected = {
            1: (12, 1, 0, 0, 4),
            2: (54, 2, 4, 6, 12),
            3: (144, 3, 12, 36, 24),
            4: (300, 4, 24, 108, 40),
        }
        for degree, values in expected.items():
            with self.subTest(degree=degree):
                layout = high_order_trace_layout(degree)
                self.assertEqual(
                    (
                        layout.hexahedron_dimension,
                        layout.edge_dofs,
                        layout.face_interior_dofs,
                        layout.cell_interior_dofs,
                        layout.face_trace_dofs,
                    ),
                    values,
                )
                self.assertEqual(
                    layout.face_trace_dofs,
                    layout.quadrilateral_n1curl_dimension,
                )

    def test_basix_d4_permutations_are_complete_and_invertible(self) -> None:
        mapping = quadrilateral_d4_vertex_permutations()
        self.assertEqual(len(mapping), 8)
        self.assertEqual(mapping[(0, 1, 2, 3)], 0)
        for permutation, face_info in mapping.items():
            self.assertEqual(quadrilateral_face_info(permutation), face_info)
            self.assertEqual(sorted(permutation), [0, 1, 2, 3])

    def test_edge_and_face_coefficient_transforms_round_trip(self) -> None:
        for degree in range(1, 5):
            with self.subTest(degree=degree, entity="edge"):
                edge = edge_coefficient_transform(degree, reversed_orientation=True)
                np.testing.assert_allclose(
                    edge.conj().T @ edge, np.eye(edge.shape[0]), atol=1.0e-12
                )
            for (
                permutation,
                face_info,
            ) in quadrilateral_d4_vertex_permutations().items():
                with self.subTest(degree=degree, face_info=face_info):
                    basis = face_basis_transform(degree, face_info)
                    coefficient = face_coefficient_transform(degree, permutation)
                    np.testing.assert_allclose(coefficient, basis.T, atol=1.0e-14)
                    np.testing.assert_allclose(
                        coefficient.conj().T @ coefficient,
                        np.eye(coefficient.shape[0]),
                        atol=1.0e-12,
                    )

    def test_topology_cache_is_phase_independent(self) -> None:
        key = FloquetTopologyKey(
            mesh_token="fixture-a-h5", element_family="N1curl", degree=3
        )
        block = PhaseIndependentConstraintBlock(
            kind="corner",
            slave_global_dofs=(10, 11),
            master_global_dofs=(2, 3),
            coefficient_transform=np.eye(2),
        )
        topology = FloquetTraceTopology(
            key=key,
            blocks=(block,),
            topology_build_seconds=0.01,
            bytes_sent=64,
            bytes_received=64,
        )
        cache = FloquetTopologyCache(max_entries=2)
        self.assertIsNone(cache.get(key))
        cache.put(topology)
        self.assertIs(cache.get(key), topology)
        first = topology.materialize(phase_x=1j, phase_y=-1.0)[0]
        second = topology.materialize(phase_x=-1j, phase_y=-1.0)[0]
        self.assertFalse(np.array_equal(first, second))
        np.testing.assert_array_equal(block.coefficient_transform, np.eye(2))
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 1)

    def test_distributed_pairing_routes_only_matching_records(self) -> None:
        comm = MPI.COMM_WORLD
        pair_key = [101, 202, 303, 2]
        records = []
        if comm.rank == 0:
            records.append(
                {
                    "pair_key": pair_key,
                    "role": "master",
                    "global_dofs": [11, 12, 13],
                    "owners": [0, 0, 0],
                    "owns_any": True,
                    "reply_rank": 0,
                    "token": "master-r0",
                }
            )
        if comm.rank == comm.size - 1:
            records.append(
                {
                    "pair_key": pair_key,
                    "role": "slave",
                    "global_dofs": [91, 92, 93],
                    "reply_rank": comm.rank,
                    "token": f"slave-r{comm.rank}",
                }
            )
        replies, metrics = distributed_match_periodic_records(comm, records)
        if comm.rank == comm.size - 1:
            self.assertEqual(len(replies), 1)
            self.assertEqual(replies[0]["master"]["global_dofs"], [11, 12, 13])
        else:
            self.assertEqual(replies, [])
        self.assertEqual(metrics.pair_count, 1)
        self.assertFalse(metrics.used_full_boundary_gather)
        self.assertGreater(metrics.bytes_sent + metrics.bytes_received, 0)
        self.assertLess(stable_pairing_rank(pair_key, comm.size), comm.size)


if __name__ == "__main__":
    unittest.main()
