from __future__ import annotations

import unittest

import numpy as np

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)


class Task43PrimalVariablePTransferTests(unittest.TestCase):
    def test_oriented_p4_to_p5_primal_extraction_roundtrips_nonzero_cell_info(
        self,
    ):
        parent = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(4)
        )
        candidate = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(5)
        )
        cell_info = 0b011  # face-0 reflection and one quarter-turn
        self.assertNotEqual(cell_info, 0)
        rng = np.random.default_rng(4305)
        parent_active = (
            rng.standard_normal(parent.hcurl_dimension)
            + 1j * rng.standard_normal(parent.hcurl_dimension)
        )
        parent_p6 = parent.active_to_p6_oriented(
            parent_active,
            cell_info=cell_info,
        )
        candidate_active, audit = candidate.extract_hcurl_coefficients_from_p6(
            parent_p6,
            cell_info=cell_info,
        )
        reconstructed_p6 = candidate.active_to_p6_oriented(
            candidate_active,
            cell_info=cell_info,
        )
        self.assertFalse(audit["transpose_dual_projection_used"])
        self.assertEqual(audit["cell_info"], cell_info)
        self.assertLessEqual(audit["p6_to_active_identity_error_max"], 5.0e-10)
        np.testing.assert_allclose(
            reconstructed_p6,
            parent_p6,
            rtol=5.0e-12,
            atol=5.0e-12,
        )

    def test_custom_mixed_entity_primal_extraction_roundtrips_orientation(self):
        parent = build_variable_p_reference_space(
            HexaEntityDegreeMap.dimension_uniform(
                edge_degree=3,
                face_degree=3,
                cell_degree=4,
            )
        )
        candidate = build_variable_p_reference_space(
            HexaEntityDegreeMap.dimension_uniform(
                edge_degree=3,
                face_degree=4,
                cell_degree=5,
            )
        )
        cell_info = 0b011
        rng = np.random.default_rng(4315)
        parent_active = (
            rng.standard_normal(parent.hcurl_dimension)
            + 1j * rng.standard_normal(parent.hcurl_dimension)
        )
        parent_p6 = parent.active_to_p6_oriented(
            parent_active,
            cell_info=cell_info,
        )
        candidate_active, audit = candidate.extract_hcurl_coefficients_from_p6(
            parent_p6,
            cell_info=cell_info,
        )
        reconstructed_p6 = candidate.active_to_p6_oriented(
            candidate_active,
            cell_info=cell_info,
        )
        self.assertLessEqual(audit["p6_to_active_identity_error_max"], 5.0e-10)
        np.testing.assert_allclose(
            reconstructed_p6,
            parent_p6,
            rtol=5.0e-12,
            atol=5.0e-12,
        )


if __name__ == "__main__":
    unittest.main()
