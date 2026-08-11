from __future__ import annotations

import hashlib
import unittest

import numpy as np

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    apply_active_dof_transformation,
    build_p4_p6_entity_dof_catalog,
    build_variable_p_reference_space,
)
from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
    quadrilateral_d4_vertex_permutations,
)


def _relative_error(left: np.ndarray, right: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0)
    return float(np.linalg.norm(left - right) / denominator)


class Task037M0P4P6TransferFixtureTests(unittest.TestCase):
    @staticmethod
    def _spaces():
        p4 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(4))
        p6 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(6))
        return p4, p6

    def test_reference_embedding_metadata_and_entity_locality(self) -> None:
        p4, p6 = self._spaces()
        interpolation = p4.hcurl_to_p6

        self.assertEqual(interpolation.shape, (882, 300))
        self.assertEqual(interpolation.dtype, np.dtype(np.float64))
        self.assertTrue(interpolation.flags.c_contiguous)
        self.assertFalse(interpolation.flags.writeable)
        self.assertEqual(interpolation.nbytes, 2_116_800)
        self.assertTrue(np.isfinite(interpolation).all())

        digest = hashlib.sha256(interpolation.tobytes(order="C")).hexdigest()
        self.assertEqual(digest, p4.audit["hcurl_expansion_sha256"])
        p4_repeat, _p6_repeat = self._spaces()
        np.testing.assert_array_equal(p4_repeat.hcurl_to_p6, interpolation)
        self.assertEqual(
            hashlib.sha256(p4_repeat.hcurl_to_p6.tobytes(order="C")).hexdigest(),
            digest,
        )

        catalog = build_p4_p6_entity_dof_catalog()
        self.assertTrue(catalog["pass"])
        self.assertTrue(p4.audit["hcurl_orientation"]["pass"])
        self.assertTrue(p6.audit["hcurl_orientation"]["pass"])

        trace_from_p4_interior = interpolation[
            np.ix_(p6.trace_dofs, p4.interior_dofs)
        ]
        structural_roundoff_limit = 128 * np.finfo(np.float64).eps
        observed_structural_roundoff = float(
            np.max(np.abs(trace_from_p4_interior), initial=0.0)
        )
        self.assertLessEqual(
            observed_structural_roundoff,
            structural_roundoff_limit,
            msg=(
                "structural_roundoff_limit exceeded: "
                f"observed={observed_structural_roundoff:.17g}, "
                f"limit={structural_roundoff_limit:.17g}"
            ),
        )

    def test_full_space_oriented_transfer_and_complex_adjoint(self) -> None:
        p4, p6 = self._spaces()
        interpolation = p4.hcurl_to_p6
        x4 = (
            np.sin(np.arange(300, dtype=np.float64) + 0.17)
            + 1j * np.cos(np.arange(300, dtype=np.float64) - 0.23)
        ).astype(np.complex128)
        y6 = (
            np.cos(np.arange(882, dtype=np.float64) + 0.31)
            + 1j * np.sin(np.arange(882, dtype=np.float64) - 0.41)
        ).astype(np.complex128)

        cell_infos = [0]
        cell_infos.extend(1 << (18 + edge) for edge in range(12))
        cell_infos.extend(1 << (3 * face) for face in range(6))
        cell_infos.extend(1 << (3 * face + 1) for face in range(6))
        cell_infos.append(
            (1 << (18 + 2))
            | (1 << 0)
            | (2 << (3 * 2 + 1))
            | (1 << (3 * 5))
        )

        for cell_info in cell_infos:
            with self.subTest(cell_info=cell_info):
                active_reference = apply_active_dof_transformation(
                    p4,
                    x4,
                    family="hcurl",
                    cell_info=cell_info,
                    transpose=True,
                )
                p6_reference = interpolation @ active_reference
                expected = apply_active_dof_transformation(
                    p6,
                    p6_reference,
                    family="hcurl",
                    cell_info=cell_info,
                )
                actual = p4.active_to_p6_oriented(x4, cell_info=cell_info)
                self.assertLessEqual(_relative_error(actual, expected), 1.0e-13)
                self.assertEqual(actual.shape, (882,))
                self.assertTrue(np.isfinite(actual).all())

                p6_reference_dual = apply_active_dof_transformation(
                    p6,
                    y6,
                    family="hcurl",
                    cell_info=cell_info,
                    transpose=True,
                )
                active_reference_dual = interpolation.conj().T @ p6_reference_dual
                expected_adjoint = apply_active_dof_transformation(
                    p4,
                    active_reference_dual,
                    family="hcurl",
                    cell_info=cell_info,
                )
                actual_adjoint = p4.project_p6_oriented_dual(
                    y6,
                    cell_info=cell_info,
                )
                self.assertLessEqual(
                    _relative_error(actual_adjoint, expected_adjoint),
                    1.0e-13,
                )
                self.assertLessEqual(
                    abs(np.vdot(actual, y6) - np.vdot(x4, actual_adjoint))
                    / max(abs(np.vdot(actual, y6)), abs(np.vdot(x4, actual_adjoint)), 1.0),
                    1.0e-11,
                )
                repeated = p4.active_to_p6_oriented(x4, cell_info=cell_info)
                repeated_adjoint = p4.project_p6_oriented_dual(
                    y6,
                    cell_info=cell_info,
                )
                self.assertEqual(actual.tobytes(), repeated.tobytes())
                self.assertEqual(actual_adjoint.tobytes(), repeated_adjoint.tobytes())

    def test_floquet_entity_transforms_apply_one_common_phase(self) -> None:
        p4, p6 = self._spaces()
        interpolation = p4.hcurl_to_p6
        phase = np.exp(0.37j)

        p4_edge = np.asarray(p4.hcurl_element.entity_dofs[1][0], dtype=np.int32)
        p6_edge = np.asarray(p6.hcurl_element.entity_dofs[1][0], dtype=np.int32)
        edge_block = interpolation[np.ix_(p6_edge, p4_edge)]
        edge4 = edge_coefficient_transform(4, reversed_orientation=True)
        edge6 = edge_coefficient_transform(6, reversed_orientation=True)
        self._assert_phase_commutation(edge_block, edge4, edge6, phase)

        p4_face = np.asarray(p4.hcurl_element.entity_dofs[2][0], dtype=np.int32)
        p6_face = np.asarray(p6.hcurl_element.entity_dofs[2][0], dtype=np.int32)
        face_block = interpolation[np.ix_(p6_face, p4_face)]
        for permutation in sorted(quadrilateral_d4_vertex_permutations()):
            with self.subTest(permutation=permutation):
                face4 = face_coefficient_transform(4, permutation)
                face6 = face_coefficient_transform(6, permutation)
                self._assert_phase_commutation(face_block, face4, face6, phase)

    def _assert_phase_commutation(
        self,
        interpolation_block: np.ndarray,
        transform4: np.ndarray,
        transform6: np.ndarray,
        phase: complex,
    ) -> None:
        c4 = phase * transform4
        c6 = phase * transform6
        left = c6 @ interpolation_block
        right = interpolation_block @ c4
        adjoint_left = interpolation_block.conj().T @ c6.conj().T
        adjoint_right = c4.conj().T @ interpolation_block.conj().T
        np.testing.assert_allclose(left, right, rtol=0.0, atol=1.0e-11)
        np.testing.assert_allclose(
            adjoint_left,
            adjoint_right,
            rtol=0.0,
            atol=1.0e-11,
        )
        np.testing.assert_allclose(
            left,
            phase * (transform6 @ interpolation_block),
            rtol=0.0,
            atol=1.0e-11,
        )
        phase_twice = (phase**2) * (transform6 @ interpolation_block)
        self_norm = max(float(np.linalg.norm(left)), 1.0)
        relative_phase_twice_error = float(
            np.linalg.norm(left - phase_twice) / self_norm
        )
        self.assertGreater(relative_phase_twice_error, 1.0e-6)


if __name__ == "__main__":
    unittest.main()
