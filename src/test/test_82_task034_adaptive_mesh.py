from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.geometry.task034_adaptive_mesh import (
    Task034Stage4Geometry,
    assert_periodic_mate_trace,
    build_task034_conforming_graded_plan,
    build_task034_graded_local_mesh_pair,
    canonical_indicator_table,
    combine_maxwell_indicator,
    dorfler_marked_cells,
    global_indicator_scales,
    indicator_digest,
    material_planes_are_exact,
    matching_planes_are_exact,
    refine_plan_from_indicator,
    robust_common_indicator,
)


class TestTask034AdaptiveMesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = target_stage4_config(degree=2, h_nm=5.0)
        cls.geometry = Task034Stage4Geometry.from_config(cls.cfg)

    def _plan(self, profile: str = "mechanism"):
        return build_task034_conforming_graded_plan(
            reference_h_nm=5.0,
            geometry=self.geometry,
            profile=profile,
            comm_size=MPI.COMM_WORLD.size,
        )

    def test_plan_is_deterministic_exact_and_opt_in(self) -> None:
        first = self._plan()
        second = self._plan()
        self.assertEqual(first.plan_hash, second.plan_hash)
        self.assertTrue(material_planes_are_exact(first))
        self.assertTrue(matching_planes_are_exact(first))
        self.assertFalse(first.to_record()["ordinary_uniform_default_changed"])
        self.assertFalse(first.to_record()["quality"]["hanging_nodes_present"])
        self.assertTrue(first.to_record()["periodic_pairing"]["x_trace_synchronized"])

    def test_profiles_form_three_distinct_compression_levels(self) -> None:
        conservative = self._plan("conservative")
        balanced = self._plan("balanced")
        aggressive = self._plan("aggressive")
        self.assertGreaterEqual(conservative.element_count, balanced.element_count)
        self.assertGreaterEqual(balanced.element_count, aggressive.element_count)
        self.assertEqual(
            len({conservative.plan_hash, balanced.plan_hash, aggressive.plan_hash}),
            3,
        )

    def test_broken_periodic_mate_trace_fails(self) -> None:
        plan = self._plan()
        first = (plan.y_values.copy(), plan.z_values.copy())
        broken_y = plan.y_values.copy()
        broken_y[1] += 0.125
        with self.assertRaisesRegex(ValueError, "Broken x-periodic"):
            assert_periodic_mate_trace(
                plan,
                "x",
                mate_first_trace_axes=first,
                mate_second_trace_axes=(broken_y, plan.z_values.copy()),
            )

    def test_local_pair_has_identical_matching_trace(self) -> None:
        plan = self._plan()
        bottom, top = build_task034_graded_local_mesh_pair(self.cfg, plan)
        self.assertEqual(bottom.mesh_cells[:2], top.mesh_cells[:2])
        expected = bottom.mesh_cells[0] * bottom.mesh_cells[1]
        self.assertEqual(bottom.global_interface_facet_count, expected)
        self.assertEqual(top.global_interface_facet_count, expected)
        self.assertEqual(bottom.interface_z_nm, 10.0)
        self.assertEqual(top.interface_z_nm, 110.0)

    def test_indicator_is_finite_nonnegative_and_partition_canonical(self) -> None:
        components = {
            "volume_residual": np.asarray([1.0 + 2.0j, 0.5, 0.25]),
            "curl_jump": np.asarray([0.2, 0.4j, 0.1]),
            "material_interface": np.asarray([0.0, 0.3, 0.7]),
            "goal_proxy": np.asarray([0.1, 0.2, 0.3]),
        }
        scales = global_indicator_scales(components, comm=MPI.COMM_SELF)
        values = combine_maxwell_indicator(components, scales=scales)
        self.assertTrue(np.all(np.isfinite(values)))
        self.assertTrue(np.all(values >= 0.0))
        ids = np.asarray([2, 0, 1])
        canonical_ids, canonical_values = canonical_indicator_table(ids, values)
        self.assertEqual(canonical_ids.tolist(), [0, 1, 2])
        self.assertEqual(
            indicator_digest(ids, values),
            indicator_digest(canonical_ids, canonical_values),
        )

    def test_invalid_indicator_fails_closed(self) -> None:
        components = {
            "volume_residual": np.asarray([1.0, np.nan]),
            "curl_jump": np.asarray([0.1, 0.2]),
            "material_interface": np.asarray([0.2, 0.3]),
        }
        with self.assertRaisesRegex(ValueError, "finite"):
            global_indicator_scales(components, comm=MPI.COMM_SELF)

    def test_robust_common_mesh_indicator_is_order_independent(self) -> None:
        ids = np.arange(4, dtype=np.int64)
        s10 = np.asarray([1.0, 2.0, 0.0, 4.0])
        p1 = np.asarray([3.0, 1.0, 5.0, 0.0])
        first_ids, first = robust_common_indicator(
            {"10deg_s": (ids, s10), "1deg_p": (ids, p1)}
        )
        second_ids, second = robust_common_indicator(
            {"1deg_p": (ids, p1), "10deg_s": (ids, s10)}
        )
        np.testing.assert_array_equal(first_ids, second_ids)
        np.testing.assert_allclose(first, np.maximum(s10, p1))
        np.testing.assert_array_equal(first, second)

    def test_dorfler_refinement_is_field_driven_and_periodic_synced(self) -> None:
        plan = self._plan()
        ids = np.arange(plan.element_count, dtype=np.int64)
        indicator = np.zeros(plan.element_count)
        indicator[0] = 10.0
        marked = dorfler_marked_cells(ids, indicator, theta=0.5)
        np.testing.assert_array_equal(marked, np.asarray([0]))
        refined = refine_plan_from_indicator(plan, ids, indicator, theta=0.5)
        self.assertEqual(refined.parent_plan_hash, plan.plan_hash)
        self.assertEqual(refined.adaptive_iteration, 1)
        self.assertEqual(len(refined.x_values), len(plan.x_values) + 2)
        self.assertEqual(len(refined.y_values), len(plan.y_values) + 2)
        self.assertEqual(len(refined.z_values), len(plan.z_values) + 1)
        self.assertTrue(material_planes_are_exact(refined))
        self.assertTrue(matching_planes_are_exact(refined))

    def test_robust_indicator_rejects_nonidentical_cell_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "share global cell ids"):
            robust_common_indicator(
                {
                    "s": (np.asarray([0, 1]), np.asarray([1.0, 2.0])),
                    "p": (np.asarray([0, 2]), np.asarray([1.0, 2.0])),
                }
            )


if __name__ == "__main__":
    unittest.main()
