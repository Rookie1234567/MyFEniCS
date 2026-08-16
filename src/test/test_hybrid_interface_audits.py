from __future__ import annotations

import unittest
from types import SimpleNamespace
import inspect

import numpy as np
from petsc4py import PETSc

from src.coupling.hybrid_internal_modes import (
    _canonical_trace_consistency_audit,
)
from src.modes.mode_classification import (
    NearDegenerateBlockPartitionSplitError,
    _joint_near_degenerate_groups,
    _joint_subspace_inverse,
    _near_degenerate_partition_audit,
    _retained_subspace_dual_rotation,
    _retained_subspace_dual_rotation_eligible,
    build_biorthogonal_mode_basis,
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
        joint = _joint_near_degenerate_groups(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertEqual(joint, ((0, 1), (2,), (3,), (4,)))
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
        self.assertFalse(_retained_subspace_dual_rotation_eligible(audit, enabled=True))

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

    def test_joint_groups_close_cumulative_near_degenerate_blocks(self):
        betas = tuple(0.5 + (0.1 + index * 1.0e-7) * 1j for index in range(4))
        groups = tuple((index,) for index in range(4))
        overlap = np.eye(4, dtype=np.complex128)
        overlap[0, 1:] = 0.6e-6

        one_merge_values = overlap.copy()
        one_merge_values[np.ix_((0, 1), (0, 1))] = np.eye(2, dtype=np.complex128)
        one_merge_audit = _near_degenerate_partition_audit(
            betas,
            ((0, 1), (2,), (3,)),
            one_merge_values,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertGreater(one_merge_audit["biorthogonality_identity_row_norm"], 1.0e-6)

        joint = _joint_near_degenerate_groups(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertEqual(joint, ((0, 1, 2), (3,)))
        closed_values = overlap.copy()
        closed_values[np.ix_((0, 1, 2), (0, 1, 2))] = np.eye(3, dtype=np.complex128)
        closed_audit = _near_degenerate_partition_audit(
            betas,
            joint,
            closed_values,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertLessEqual(closed_audit["biorthogonality_identity_row_norm"], 1.0e-6)

    @staticmethod
    def _identity_matrix(size: int) -> PETSc.Mat:
        matrix = PETSc.Mat().createAIJ(size=(size, size), comm=PETSc.COMM_SELF)
        matrix.setUp()
        for row in range(size):
            matrix.setValue(row, row, 1.0)
        matrix.assemble()
        return matrix

    @staticmethod
    def _zero_matrix(size: int) -> PETSc.Mat:
        matrix = PETSc.Mat().createAIJ(size=(size, size), comm=PETSc.COMM_SELF)
        matrix.setUp()
        matrix.assemble()
        return matrix

    @staticmethod
    def _vector(values: np.ndarray) -> PETSc.Vec:
        vector = PETSc.Vec().createMPI(len(values), comm=PETSc.COMM_SELF)
        vector.setArray(np.asarray(values, dtype=np.complex128))
        return vector

    def test_retained_dual_rotation_repairs_accumulated_row_and_transforms_both_spaces(
        self,
    ):
        size = 4
        overlap = np.eye(size, dtype=np.complex128)
        overlap[0, 1:] = 3.5e-7
        betas = tuple(float(index + 1) + 0.0j for index in range(size))
        groups = tuple((index,) for index in range(size))
        pre_audit = _near_degenerate_partition_audit(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * size,
        )
        self.assertTrue(
            _retained_subspace_dual_rotation_eligible(pre_audit, enabled=True)
        )
        self.assertFalse(
            _retained_subspace_dual_rotation_eligible(pre_audit, enabled=False)
        )
        self.assertIs(
            inspect.signature(build_biorthogonal_mode_basis)
            .parameters["retained_subspace_dual_rotation"]
            .default,
            False,
        )

        right_reduced = [
            self._vector(np.eye(size, dtype=np.complex128)[:, index])
            for index in range(size)
        ]
        left_reduced = [self._vector(overlap[index, :]) for index in range(size)]
        left_full = [self._vector(overlap[index, :]) for index in range(size)]
        candidates = [
            SimpleNamespace(right_reduced=reduced, right_full=full)
            for reduced, full in zip(left_reduced, left_full)
        ]
        k1 = self._identity_matrix(size)
        k2 = self._zero_matrix(size)
        adjoint_k0 = self._zero_matrix(size)
        adjoint_k1 = self._zero_matrix(size)
        adjoint_k2 = self._zero_matrix(size)
        operators = SimpleNamespace(K1=k1, K2=k2)
        adjoints = (adjoint_k0, adjoint_k1, adjoint_k2)
        rotated = False
        try:
            (
                new_reduced,
                new_full,
                post_values,
                post_audit,
                report,
                residuals,
            ) = _retained_subspace_dual_rotation(
                overlap,
                left_reduced,
                left_full,
                betas,
                betas,
                right_reduced,
                groups,
                operators=operators,
                adjoints=adjoints,
                pre_audit=pre_audit,
                near_degenerate_tolerance=1.0e-6,
                block_rotation_tolerance=1.0e-6,
                maximum_overlap_condition=1.0e12,
                directions=("forward",) * size,
                left_candidates=candidates,
            )
            rotated = True
            np.testing.assert_allclose(
                post_values, np.eye(size), rtol=0.0, atol=1.0e-12
            )
            self.assertTrue(post_audit["pass"])
            self.assertEqual(report["left_span_dimension"], size)
            self.assertTrue(report["right_vectors_unchanged"])
            self.assertTrue(report["betas_unchanged"])
            self.assertTrue(report["partition_pass"])
            self.assertTrue(report["left_residual_pass"])
            self.assertTrue(report["overall_pass"])
            self.assertEqual(len(new_reduced), size)
            self.assertEqual(len(new_full), size)
            self.assertEqual(len(residuals), size)
            for candidate, reduced, full in zip(candidates, new_reduced, new_full):
                self.assertIs(candidate.right_reduced, reduced)
                self.assertIs(candidate.right_full, full)
            self.assertTrue(
                np.isfinite(report["post_max_left_polynomial_relative_residual"])
            )
        finally:
            if rotated:
                for vector in [*new_reduced, *new_full]:
                    vector.destroy()
            else:
                for vector in [*left_reduced, *left_full]:
                    vector.destroy()
            for vector in right_reduced:
                vector.destroy()
            for matrix in [k1, k2, adjoint_k0, adjoint_k1, adjoint_k2]:
                matrix.destroy()

    def test_retained_dual_rotation_rejects_bad_condition_and_cross_failure(self):
        size = 2
        reduced = [self._vector(np.eye(size)[:, index]) for index in range(size)]
        full = [self._vector(np.eye(size)[:, index]) for index in range(size)]
        right = [self._vector(np.eye(size)[:, index]) for index in range(size)]
        try:
            with self.assertRaisesRegex(RuntimeError, "ill-conditioned"):
                _retained_subspace_dual_rotation(
                    np.diag([1.0, 1.0e-8]),
                    reduced,
                    full,
                    (1.0 + 0.0j, 2.0 + 0.0j),
                    (1.0 + 0.0j, 2.0 + 0.0j),
                    right,
                    ((0,), (1,)),
                    operators=SimpleNamespace(),
                    adjoints=(),
                    pre_audit={},
                    near_degenerate_tolerance=1.0e-6,
                    block_rotation_tolerance=1.0e-6,
                    maximum_overlap_condition=1.0e4,
                )
        finally:
            for vector in [*reduced, *full, *right]:
                vector.destroy()

        cross_failure = np.eye(2, dtype=np.complex128)
        cross_failure[0, 1] = 2.0e-6
        audit = _near_degenerate_partition_audit(
            (1.0 + 0.0j, 2.0 + 0.0j),
            ((0,), (1,)),
            cross_failure,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
        )
        self.assertEqual(audit["status"], "cross_block_biorthogonality_failure")
        self.assertTrue(_retained_subspace_dual_rotation_eligible(audit, enabled=True))


if __name__ == "__main__":
    unittest.main()
