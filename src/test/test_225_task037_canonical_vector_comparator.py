import unittest

import numpy as np
from mpi4py import MPI

from src.solvers.hcurl_canonical_vector import (
    canonical_key,
    canonical_packet,
    canonicalize_coefficients,
    compare_canonical_packets,
)


def _packets() -> tuple[tuple[tuple, complex], ...]:
    edge = canonical_key(
        role="active_trace",
        entity_dimension=1,
        physical_entity=((0, 0, 0), (100, 0, 0)),
        entity_local_basis_index=0,
        orientation_state=("edge", 0),
        floquet_master=("edge", 0),
        floquet_coefficient=1.0 + 0.0j,
    )
    face = canonical_key(
        role="active_trace",
        entity_dimension=2,
        physical_entity=((0, 0, 0), (0, 100, 0), (100, 0, 0), (100, 100, 0)),
        entity_local_basis_index=1,
        orientation_state=("face", 2),
        floquet_master=("face", 1),
        floquet_coefficient=0.5 + 0.25j,
    )
    interior = canonical_key(
        role="full_fe",
        entity_dimension=3,
        physical_entity=(
            (0, 0, 0),
            (0, 0, 100),
            (0, 100, 0),
            (0, 100, 100),
            (100, 0, 0),
            (100, 0, 100),
            (100, 100, 0),
            (100, 100, 100),
        ),
        entity_local_basis_index=7,
        orientation_state=("cell", 0),
    )
    return (
        canonical_packet(edge, 1.25 - 0.5j),
        canonical_packet(face, -0.75 + 0.125j),
        canonical_packet(interior, 2.0 + 0.25j),
    )


class TestTask037CanonicalVectorComparator(unittest.TestCase):
    @unittest.skipUnless(
        MPI.COMM_WORLD.size in (1, 2, 4),
        "serial/MPI2/MPI4 canonical fixture",
    )
    def test_repartition_and_orientation_canonicalize(self) -> None:
        comm = MPI.COMM_WORLD
        packets = _packets()
        raw = np.asarray([1.0 + 2.0j, -0.5 + 0.25j])
        transform = np.asarray([[0.0, -1.0], [1.0, 0.0]])
        np.testing.assert_allclose(
            canonicalize_coefficients(raw, transform),
            (-raw[1], raw[0]),
        )
        left_owned = [
            packet
            for index, packet in enumerate(packets)
            if index % comm.size == comm.rank
        ]
        right_owned = [
            packet
            for index, packet in enumerate(reversed(packets))
            if index % comm.size == comm.rank
        ]
        left_groups = comm.gather(left_owned, root=0)
        right_groups = comm.gather(right_owned, root=0)
        audit = None
        if comm.rank == 0:
            left = tuple(packet for group in left_groups for packet in group)
            right = tuple(packet for group in right_groups for packet in group)
            audit = compare_canonical_packets(left, right)
        audit = comm.bcast(audit, root=0)
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["common_key_count"], 3)
        self.assertEqual(audit["duplicate_left_count"], 0)
        self.assertEqual(audit["trace_mass_norm"], "not_qualified")
        self.assertEqual(audit["hcurl_norm"], "not_qualified")

    def test_orientation_and_floquet_identity_errors_fail(self) -> None:
        packets = _packets()
        changed_value = list(packets)
        changed_value[1] = (changed_value[1][0], changed_value[1][1] + 0.01j)
        self.assertFalse(compare_canonical_packets(packets, changed_value)["pass"])
        orientation_key = list(packets)
        key = orientation_key[1][0]
        orientation_key[1] = (
            canonical_key(
                role=key[0],
                entity_dimension=key[1],
                physical_entity=key[2],
                entity_local_basis_index=key[3],
                orientation_state=("face", 3),
                floquet_master=key[5],
                floquet_coefficient=complex(*key[6]),
            ),
            orientation_key[1][1],
        )
        orientation_failed = compare_canonical_packets(packets, orientation_key)
        self.assertFalse(orientation_failed["pass"])
        self.assertEqual(orientation_failed["missing_key_count"], 1)
        self.assertEqual(orientation_failed["extra_key_count"], 1)
        changed_key = list(packets)
        key = changed_key[1][0]
        changed_key[1] = (
            canonical_key(
                role=key[0],
                entity_dimension=key[1],
                physical_entity=key[2],
                entity_local_basis_index=key[3],
                orientation_state=key[4],
                floquet_master=key[5],
                floquet_coefficient=0.5 + 0.5j,
            ),
            changed_key[1][1],
        )
        failed = compare_canonical_packets(packets, changed_key)
        self.assertFalse(failed["pass"])
        self.assertEqual(failed["missing_key_count"], 1)
        self.assertEqual(failed["extra_key_count"], 1)

    def test_duplicate_and_missing_keys_are_reported(self) -> None:
        packets = _packets()
        audit = compare_canonical_packets(packets + packets[:1], packets)
        self.assertFalse(audit["pass"])
        self.assertEqual(audit["duplicate_left_count"], 1)
        self.assertEqual(audit["left_shape"], [4])


if __name__ == "__main__":
    unittest.main()
