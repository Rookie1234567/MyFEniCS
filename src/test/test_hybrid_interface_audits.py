from __future__ import annotations

import unittest

import numpy as np

from src.coupling.hybrid_internal_modes import (
    _canonical_trace_consistency_audit,
)
from src.modes.mode_classification import (
    NearDegenerateBlockPartitionSplitError,
    _joint_near_degenerate_groups,
    _joint_subspace_inverse,
    _near_degenerate_partition_audit,
)


class HybridInterfaceAuditTests(unittest.TestCase):
    def test_canonical_trace_audit_checks_raw_and_represented_traces(self):
        gram = np.asarray(
            [[2.0 + 0.0j, 0.25j], [-0.25j, 1.5 + 0.0j]],
            dtype=np.complex128,
        )
        mapping = np.asarray(
            [[0.75 + 0.1j, -0.2j], [0.15, 0.9 - 0.05j]],
            dtype=np.complex128,
        )
        expected = gram @ mapping

        passing = _canonical_trace_consistency_audit(
            gram,
            expected,
            expected,
            mapping,
        )
        self.assertTrue(passing["pass"])
        self.assertEqual(passing["raw_consistency_error"], 0.0)
        self.assertEqual(passing["canonical_representation_error"], 0.0)

        perturbed_raw = expected.copy()
        perturbed_raw[0, 1] += 1.0e-8
        failing = _canonical_trace_consistency_audit(
            gram,
            perturbed_raw,
            expected,
            mapping,
        )
        self.assertFalse(failing["pass"])
        self.assertGreater(failing["raw_consistency_error"], 1.0e-12)
        self.assertEqual(failing["canonical_representation_error"], 0.0)

        nonfinite = expected.copy()
        nonfinite[0, 0] = np.nan
        nonfinite_audit = _canonical_trace_consistency_audit(
            gram,
            nonfinite,
            expected,
            mapping,
        )
        self.assertFalse(nonfinite_audit["pass"])
        self.assertEqual(nonfinite_audit["raw_consistency_error"], float("inf"))

    def test_partition_detector_rejects_cumulative_row_error(self):
        overlap = np.eye(5, dtype=np.complex128)
        overlap[0, 1:4] = 4.0e-7
        betas = tuple(0.5 + (0.1 + index * 1.0e-7) * 1j for index in range(5))
        groups = tuple((index,) for index in range(5))
        audit = _near_degenerate_partition_audit(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 5,
        )

        self.assertFalse(audit["pass"])
        self.assertEqual(
            audit["status"],
            "near_degenerate_block_partition_split",
        )
        self.assertAlmostEqual(
            audit["biorthogonality_identity_row_norm"],
            1.2e-6,
        )
        self.assertAlmostEqual(
            audit["biorthogonality_identity_max_entry"],
            4.0e-7,
        )
        self.assertTrue(audit["max_cross_block_overlap_within_tolerance"])
        self.assertFalse(audit["biorthogonality_identity_row_norm_within_tolerance"])
        self.assertEqual(audit["worst_cross_block_indices"], [0, 1])
        self.assertEqual(audit["worst_cross_block_group_ids"], [0, 1])
        self.assertEqual(audit["worst_cross_block_group_members"], [[0], [1]])
        self.assertGreater(
            audit["worst_cross_block_relative_beta_distance"],
            0.0,
        )

        with self.assertRaisesRegex(
            NearDegenerateBlockPartitionSplitError,
            r"identity_row_norm=.*cross_block_max=.*indices=\[0, 1\]",
        ) as caught:
            raise NearDegenerateBlockPartitionSplitError(audit)
        self.assertEqual(caught.exception.audit, audit)

    def test_joint_groups_rotate_coupled_near_degenerate_modes(self):
        betas = (1.0 + 0.0j, 1.0 + 1.580086e-6j, 2.0 + 0.0j)
        groups = ((0,), (1,), (2,))
        overlap = np.eye(3, dtype=np.complex128)
        overlap[0, 1] = 1.773428e-6
        overlap[1, 0] = 0.7e-6

        joint = _joint_near_degenerate_groups(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertEqual(joint, ((0, 1), (2,)))
        transform, condition = _joint_subspace_inverse(
            overlap[np.ix_((0, 1), (0, 1))],
            maximum_overlap_condition=1.0e12,
        )
        np.testing.assert_allclose(
            transform.conj().T @ overlap[np.ix_((0, 1), (0, 1))],
            np.eye(2),
            rtol=0.0,
            atol=1.0e-12,
        )
        self.assertTrue(np.isfinite(condition))

    def test_joint_groups_do_not_merge_outside_candidate_envelope(self):
        betas = (1.0 + 0.0j, 1.0 + 11.0e-6j)
        groups = ((0,), (1,))
        overlap = np.asarray(
            [[1.0 + 0.0j, 2.0e-6], [2.0e-6, 1.0 + 0.0j]],
            dtype=np.complex128,
        )
        joint = _joint_near_degenerate_groups(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertEqual(joint, ((0,), (1,)))
        audit = _near_degenerate_partition_audit(
            betas,
            joint,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward", "forward"),
        )
        self.assertFalse(audit["pass"])
        self.assertEqual(audit["status"], "cross_block_biorthogonality_failure")


if __name__ == "__main__":
    unittest.main()
