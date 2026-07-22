from __future__ import annotations

import json
import math
import unittest

import numpy as np

from benchmarks.task035_estimator_fixtures import build_record
from src.validation.task035_hcurl_estimator_fixtures import (
    CANDIDATE_METHODS,
    RESIDUAL_COMPONENTS,
    build_fixture_summary,
    canonical_partition_sum,
    combine_goal_estimates,
    dwr_error_estimate,
    flat_lossy_layer_fixture,
    frequency_scaled_indicator,
    homogeneous_periodic_fixture,
    hybrid_interface_fixture,
    local_energy_correction,
    material_interface_fixture,
    standard_residual_indicator,
    truncation_error_split,
)


class Task035EstimatorFixtureTests(unittest.TestCase):
    def test_candidate_inventory_is_complete_and_fixture_only(self) -> None:
        summary = build_fixture_summary()
        self.assertEqual(set(summary["method_status"]), set(CANDIDATE_METHODS))
        self.assertEqual(
            summary["method_status"]["R4_equilibrated_patch"], "formula_defined"
        )
        self.assertEqual(
            summary["method_status"]["R2_frequency_scaled_residual"],
            "resolution_diagnostic_pass",
        )
        algebraic = set(summary["method_status"]) - {
            "R2_frequency_scaled_residual",
            "R4_equilibrated_patch",
        }
        self.assertTrue(all(
            summary["method_status"][name] == "algebraic_precursor_pass"
            for name in algebraic
        ))
        self.assertFalse(summary["canonical"])
        self.assertFalse(summary["production_qualified"])
        self.assertFalse(summary["pde_run"])
        self.assertFalse(summary["target_grating_run"])
        json.dumps(summary)

    def test_residual_inventory_and_hermitian_nonnegativity(self) -> None:
        self.assertEqual(len(RESIDUAL_COMPONENTS), 8)
        result = standard_residual_indicator(
            {
                "volume_curl_residual": [1.0 + 2.0j, -0.5j],
                "curl_flux_jump": [0.25 - 0.75j],
            }
        )
        self.assertGreaterEqual(result["total"], 0.0)
        self.assertTrue(math.isfinite(result["total"]))
        self.assertAlmostEqual(result["total"] ** 2, result["total_squared"])

    def test_homogeneous_fixture_detects_orientation_and_phase(self) -> None:
        fixture = homogeneous_periodic_fixture()
        self.assertLess(fixture["exact_indicator"], 1.0e-13)
        self.assertGreater(fixture["broken_orientation_indicator"], 1.0e-2)
        self.assertGreater(fixture["broken_phase_indicator"], 1.0e-3)
        sums = [
            row["global_sum"] for row in fixture["mpi_partitions"].values()
        ]
        np.testing.assert_allclose(sums, sums[0], rtol=0.0, atol=1.0e-15)

    def test_cell_ids_are_canonical_and_duplicate_ids_fail(self) -> None:
        result = canonical_partition_sum([8, 2, 5], [0.3, 0.1, 0.2], 4)
        self.assertEqual(result["canonical_cell_ids"], [2, 5, 8])
        self.assertAlmostEqual(result["global_sum"], 0.6)
        with self.assertRaisesRegex(ValueError, "unique"):
            canonical_partition_sum([2, 2], [0.1, 0.2], 2)

    def test_frequency_screen_is_diagnostic_only_and_never_rescales(self) -> None:
        resolved = frequency_scaled_indicator(
            2.0, wave_number=3.0, cell_size=0.1, degree=4
        )
        unresolved = frequency_scaled_indicator(
            2.0, wave_number=30.0, cell_size=1.0, degree=1
        )
        self.assertEqual(resolved["unscaled_indicator"], 2.0)
        self.assertEqual(unresolved["unscaled_indicator"], 2.0)
        self.assertGreater(unresolved["chi"], resolved["chi"])
        self.assertNotIn("scale", resolved)
        self.assertNotIn("indicator", resolved)

    def test_flat_lossy_fixture_derivatives_and_refinement(self) -> None:
        fixture = flat_lossy_layer_fixture()
        for result in fixture["goal_derivative_checks"].values():
            self.assertLess(result["absolute_error"], 1.0e-9)
        trend = fixture["uniform_refinement_indicators"]
        self.assertTrue(all(right < left for left, right in zip(trend, trend[1:])))
        self.assertEqual(fixture["dtn_exact_indicator"], 0.0)
        self.assertGreater(fixture["dtn_broken_indicator"], 1.0e-3)

    def test_material_fixture_detects_tag_and_preserves_jump_weighting(self) -> None:
        fixture = material_interface_fixture()
        self.assertEqual(fixture["exact_interface_indicator"], 0.0)
        self.assertGreater(fixture["corrupted_material_tag_indicator"], 0.1)
        self.assertEqual(fixture["coefficient_aware_recovery_indicator"], 0.0)
        self.assertGreater(fixture["naive_recovery_jump_indicator"], 0.1)
        self.assertLess(fixture["equilibrium_residual"], 1.0e-13)
        marking = fixture["anisotropic_marking"]
        self.assertEqual(marking[0]["preferred_axis"], "x")

    def test_local_patch_and_two_level_energy_are_well_defined(self) -> None:
        result = local_energy_correction(
            [[3.0, 0.2j], [-0.2j, 2.0]], [0.4 + 0.1j, -0.2]
        )
        self.assertGreater(result["indicator"], 0.0)
        self.assertLess(result["equilibrium_residual"], 1.0e-13)

    def test_dwr_uses_complex_conjugation_and_multi_goal_weights(self) -> None:
        residual = np.array([1.0 + 2.0j, -0.3 + 0.5j])
        adjoint = np.array([0.2 - 0.4j, 0.7 + 0.1j])
        expected = abs(np.vdot(adjoint, residual))
        self.assertAlmostEqual(dwr_error_estimate(residual, adjoint), expected)
        combined = combine_goal_estimates(
            {"R": expected, "T": 0.2, "A": -0.1},
            {"R": 1.0, "T": 2.0, "A": 0.5},
        )
        self.assertAlmostEqual(combined, expected + 0.45)

    def test_hybrid_fixture_separates_spatial_modal_and_qep_terms(self) -> None:
        fixture = hybrid_interface_fixture()
        self.assertEqual(fixture["exact_et_indicator"], 0.0)
        self.assertEqual(fixture["exact_ht_indicator"], 0.0)
        self.assertGreater(fixture["broken_et_indicator"], 0.0)
        self.assertGreater(fixture["broken_ht_indicator"], 0.0)
        split = fixture["error_split"]
        self.assertAlmostEqual(split["estimator_total"], 0.12)
        self.assertFalse(fixture["qep_counted_as_spatial"])
        self.assertNotEqual(
            split["qep_eigen_residual_diagnostic"], split["estimator_total"]
        )

    def test_truncation_split_rejects_negative_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            truncation_error_split(0.1, -0.01, 0.02, 0.0)

    def test_serial_runner_uses_scalar_allreduce_and_is_hermetic(self) -> None:
        record = build_record()
        self.assertEqual(record["status"], "algebraic_precursor_pass")
        self.assertTrue(record["mpi_identity"]["pass"])
        self.assertEqual(
            record["mpi_identity"]["reduction"],
            "scalar_allreduce_no_full_vector_gather",
        )


if __name__ == "__main__":
    unittest.main()
