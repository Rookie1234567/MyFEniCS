from __future__ import annotations

import unittest

import numpy as np

from src.adaptivity.exact_sequence_variable_p import (
    ExactSequenceDegreeError,
    HexaEntityDegreeMap,
    apply_active_dof_transformation,
    allowed_dimension_degree_triples,
    build_p4_p6_entity_dof_catalog,
    build_variable_p_reference_space,
)
from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.hcurl_variable_p_local import (
    condense_variable_p_local_tensor,
    project_p6_local_tensor,
)


class Task035dReferenceActiveSpaceTests(unittest.TestCase):
    @staticmethod
    def _tensor(element) -> np.ndarray:
        factory = AffineIsotropicMaxwellTensorFactory(
            element,
            AffineIsotropicMaxwellTensorSpec(
                curl_coefficient=1.25 + 0.0j,
                mass_coefficient_by_tag={1: 0.75 + 0.0j},
                quadrature_degree=12,
            ),
        )
        return factory.tensor(tag=1, widths=(0.8, 1.1, 1.4))

    def test_p4_p5_p6_catalog_uses_actual_interpolation(self) -> None:
        catalog = build_p4_p6_entity_dof_catalog()
        self.assertTrue(catalog["pass"])
        self.assertEqual(
            catalog["allowed_dimension_degree_triples"],
            [list(values) for values in allowed_dimension_degree_triples()],
        )
        self.assertEqual(len(allowed_dimension_degree_triples()), 10)
        by_degree = {entry["degree"]: entry for entry in catalog["degrees"]}
        self.assertEqual(
            [by_degree[p]["hcurl_dimension"] for p in (4, 5, 6)],
            [300, 540, 882],
        )
        self.assertEqual(
            [by_degree[p]["h1_dimension"] for p in (4, 5, 6)],
            [125, 216, 343],
        )
        for degree in (4, 5, 6):
            entry = by_degree[degree]
            self.assertTrue(entry["hcurl_orientation"]["pass"])
            self.assertTrue(entry["h1_orientation"]["pass"])
            self.assertEqual(
                entry["hcurl_to_p6"]["rank"],
                entry["hcurl_dimension"],
            )
            self.assertEqual(
                entry["h1_to_q6"]["rank"],
                entry["h1_dimension"],
            )
            self.assertFalse(
                entry["hcurl_to_p6"]["prefix_assumption_used"]
            )
        self.assertGreater(
            by_degree[4]["hcurl_to_p6"]["naive_prefix_error_max"],
            0.5,
        )
        self.assertGreater(
            by_degree[5]["hcurl_to_p6"]["naive_prefix_error_max"],
            0.5,
        )
        self.assertEqual(
            by_degree[6]["hcurl_to_p6"]["naive_prefix_error_max"],
            0.0,
        )

    def test_degree_map_fails_closed_before_element_construction(self) -> None:
        with self.assertRaisesRegex(
            ExactSequenceDegreeError,
            "incident edge",
        ):
            HexaEntityDegreeMap.dimension_uniform(
                edge_degree=5,
                face_degree=4,
                cell_degree=6,
            )
        with self.assertRaisesRegex(
            ExactSequenceDegreeError,
            "incident face",
        ):
            HexaEntityDegreeMap.dimension_uniform(
                edge_degree=4,
                face_degree=6,
                cell_degree=5,
            )
        with self.assertRaisesRegex(ValueError, "p4/p5/p6"):
            HexaEntityDegreeMap.uniform(3)

    def test_uniform_and_mixed_reference_spaces_close_exact_sequence(
        self,
    ) -> None:
        expectations = {
            (4, 4, 4): (300, 125, False),
            (4, 5, 6): (738, 265, True),
            (5, 5, 6): (750, 277, True),
            (6, 6, 6): (882, 343, False),
        }
        for degrees, expected in expectations.items():
            with self.subTest(degrees=degrees):
                degree_map = HexaEntityDegreeMap.dimension_uniform(
                    edge_degree=degrees[0],
                    face_degree=degrees[1],
                    cell_degree=degrees[2],
                )
                space = build_variable_p_reference_space(degree_map)
                self.assertTrue(space.audit["pass"])
                self.assertEqual(space.hcurl_dimension, expected[0])
                self.assertEqual(space.h1_dimension, expected[1])
                self.assertEqual(
                    space.audit["hcurl_construction"]["custom"],
                    expected[2],
                )
                self.assertEqual(
                    space.audit["gradient_rank"],
                    space.h1_dimension - 1,
                )
                self.assertEqual(
                    space.audit["sampled_curl_nullity"],
                    space.h1_dimension - 1,
                )
                self.assertLessEqual(
                    space.audit["gradient_embedding_error_max"],
                    5.0e-11,
                )
                self.assertLessEqual(
                    space.audit["curl_gradient_error_max"],
                    2.0e-10,
                )
                self.assertFalse(
                    space.audit["inactive_modes_globally_numbered"]
                )

    def test_one_edge_can_change_degree_without_allocating_p6_rows(
        self,
    ) -> None:
        degree_map = HexaEntityDegreeMap(
            edges=(5,) + (4,) * 11,
            faces=(5,) * 6,
            cell=6,
        )
        space = build_variable_p_reference_space(degree_map)
        self.assertEqual(space.hcurl_dimension, 739)
        self.assertEqual(space.h1_dimension, 266)
        self.assertEqual(space.audit["inactive_p6_local_modes"], 143)
        self.assertEqual(space.audit["gradient_rank"], 265)
        self.assertEqual(space.audit["sampled_curl_nullity"], 265)
        self.assertTrue(space.audit["hcurl_orientation"]["pass"])
        self.assertTrue(space.audit["h1_orientation"]["pass"])
        self.assertEqual(
            space.audit["h1_orientation"]["transformation_source"],
            "per_entity_standard_basix_degree",
        )
        self.assertFalse(
            space.audit["h1_orientation"][
                "heterogeneous_custom_basix_T_apply_used"
            ]
        )

        rng = np.random.default_rng(183)
        edge_reflection_info = (1 << 18) | (1 << 19)
        for family, dimension in (
            ("hcurl", space.hcurl_dimension),
            ("h1", space.h1_dimension),
        ):
            values = rng.standard_normal((dimension, 3))
            reflected = apply_active_dof_transformation(
                space,
                values,
                family=family,
                cell_info=edge_reflection_info,
            )
            restored = apply_active_dof_transformation(
                space,
                reflected,
                family=family,
                cell_info=edge_reflection_info,
            )
            np.testing.assert_allclose(
                restored,
                values,
                rtol=2.0e-12,
                atol=2.0e-12,
            )

    def test_uniform_explicit_transform_matches_basix_T_apply(self) -> None:
        space = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(4)
        )
        # Face 0: reflect and rotate twice; face 3: rotate once. Reverse
        # edges 1 and 9. This exercises both parts of Basix's cell-info bitmap.
        cell_info = (
            1
            | (2 << 1)
            | (1 << (3 * 3 + 1))
            | (1 << (18 + 1))
            | (1 << (18 + 9))
        )
        rng = np.random.default_rng(4183)
        for family, element in (
            ("hcurl", space.hcurl_element),
            ("h1", space.h1_element),
        ):
            values = np.ascontiguousarray(
                rng.standard_normal((int(element.dim), 3))
            )
            expected = values.copy()
            element.T_apply(expected.ravel(), 3, int(cell_info))
            actual = apply_active_dof_transformation(
                space,
                values,
                family=family,
                cell_info=cell_info,
            )
            np.testing.assert_allclose(
                actual,
                expected,
                rtol=2.0e-13,
                atol=2.0e-13,
            )

    def test_projected_tensor_matches_direct_active_element(self) -> None:
        p6_space = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(6)
        )
        p6_tensor = self._tensor(p6_space.hcurl_element)
        for degrees in ((4, 4, 4), (4, 5, 6)):
            with self.subTest(degrees=degrees):
                space = build_variable_p_reference_space(
                    HexaEntityDegreeMap.dimension_uniform(
                        edge_degree=degrees[0],
                        face_degree=degrees[1],
                        cell_degree=degrees[2],
                    )
                )
                projected = project_p6_local_tensor(space, p6_tensor)
                direct = self._tensor(space.hcurl_element)
                relative = np.linalg.norm(projected - direct) / np.linalg.norm(
                    direct
                )
                self.assertLessEqual(relative, 2.0e-12)

    def test_local_schur_recovers_active_and_p6_coefficients(self) -> None:
        degree_map = HexaEntityDegreeMap.dimension_uniform(
            edge_degree=4,
            face_degree=5,
            cell_degree=6,
        )
        space = build_variable_p_reference_space(degree_map)
        p6_space = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(6)
        )
        p6_tensor = self._tensor(p6_space.hcurl_element)
        rng = np.random.default_rng(35035)
        expected_active = (
            rng.standard_normal(space.hcurl_dimension)
            + 1j * rng.standard_normal(space.hcurl_dimension)
        )
        expected_p6 = space.expand_hcurl_coefficients(expected_active)
        p6_rhs = p6_tensor @ expected_p6
        condensed = condense_variable_p_local_tensor(
            space,
            p6_tensor,
            p6_rhs,
        )
        trace = expected_active[space.trace_dofs]
        recovered_active = condensed.recover_active_coefficients(trace)
        recovered_p6 = condensed.recover_p6_coefficients(trace)
        np.testing.assert_allclose(
            recovered_active,
            expected_active,
            rtol=2.0e-9,
            atol=1.0e-9,
        )
        np.testing.assert_allclose(
            recovered_p6,
            expected_p6,
            rtol=2.0e-9,
            atol=1.0e-9,
        )
        np.testing.assert_allclose(
            condensed.schur_tensor @ trace,
            condensed.schur_rhs,
            rtol=2.0e-11,
            atol=2.0e-9,
        )
        self.assertFalse(
            condensed.audit["full_p6_global_matrix_constructed"]
        )
        self.assertFalse(
            condensed.audit["inactive_p6_rows_globally_numbered"]
        )
        self.assertEqual(condensed.audit["active_local_rows"], 738)
        self.assertEqual(condensed.audit["schur_rows"], 288)


if __name__ == "__main__":
    unittest.main()
