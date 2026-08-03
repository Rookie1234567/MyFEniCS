from __future__ import annotations

import unittest
from unittest.mock import patch

from benchmarks.run_direct_memory_forensics import (
    _enrich_factor_inventory,
)
from src.adaptivity.high_order_resource_audit import (
    matrix_factor_resource_audit,
)
from src.adaptivity.high_order_same_error import _resource_metrics
from src.solvers.common_3d_solve import (
    _corrected_mumps_factor_nnz,
    _petsc_factor_inventory,
)


class _FakeFactor:
    def __init__(self, infog_9: int) -> None:
        self.infog_9 = infog_9

    def getMumpsInfog(self, index: int) -> int:
        return self.infog_9 if index == 9 else 0

    def getMumpsRinfog(self, index: int) -> float:
        return 0.0


class _FakePC:
    def __init__(self, solver_type: str, factor: _FakeFactor) -> None:
        self.solver_type = solver_type
        self.factor = factor

    def getFactorSolverType(self) -> str:
        return self.solver_type

    def getFactorMatrix(self) -> _FakeFactor:
        return self.factor


class _FakeKSP:
    def __init__(self, solver_type: str, infog_9: int) -> None:
        self.pc = _FakePC(solver_type, _FakeFactor(infog_9))

    def getPC(self) -> _FakePC:
        return self.pc


def _factor_inventory(
    *,
    solver_type: str,
    infog_9: int,
    petsc_factor_nnz: float,
) -> dict:
    matrix_stats = {
        "matrix_rows": 10,
        "matrix_nnz_used": petsc_factor_nnz,
        "matrix_average_nnz_per_row": petsc_factor_nnz / 10.0,
        "matrix_maximum_nnz_per_row": 7,
    }
    with patch(
        "src.solvers.common_3d_solve._petsc_matrix_stats",
        return_value=matrix_stats,
    ):
        return _petsc_factor_inventory(_FakeKSP(solver_type, infog_9))


class Task036MumpsFactorNnzTests(unittest.TestCase):
    def test_negative_infog_9_decodes_to_python_int_above_int32(self) -> None:
        corrected = _corrected_mumps_factor_nnz("mumps", -2277)
        self.assertEqual(corrected, 2_277_000_000)
        self.assertIs(type(corrected), int)
        self.assertGreater(corrected, 2**31)

    def test_inventory_preserves_raw_values_and_adds_correction(self) -> None:
        inventory = _factor_inventory(
            solver_type="mumps",
            infog_9=-2277,
            petsc_factor_nnz=-2_017_967_296.0,
        )
        self.assertEqual(
            inventory["matrix_stats"]["matrix_nnz_used"],
            -2_017_967_296.0,
        )
        self.assertEqual(inventory["mumps_raw_infog"]["9"], -2277)
        self.assertEqual(inventory["factor_nnz_corrected"], 2_277_000_000)
        self.assertEqual(
            inventory["factor_nnz_corrected_source"],
            "mumps_infog_9_negative_millions",
        )

    def test_positive_mumps_and_non_mumps_values_are_not_reinterpreted(
        self,
    ) -> None:
        positive = _factor_inventory(
            solver_type="mumps",
            infog_9=123,
            petsc_factor_nnz=123.0,
        )
        other_solver = _factor_inventory(
            solver_type="superlu_dist",
            infog_9=-2277,
            petsc_factor_nnz=456.0,
        )
        self.assertIsNone(positive["factor_nnz_corrected"])
        self.assertIsNone(positive["factor_nnz_corrected_source"])
        self.assertEqual(positive["mumps_raw_infog"]["9"], 123)
        self.assertIsNone(other_solver["factor_nnz_corrected"])
        self.assertIsNone(other_solver["factor_nnz_corrected_source"])
        self.assertEqual(
            other_solver["matrix_stats"]["matrix_nnz_used"],
            456.0,
        )
        self.assertEqual(other_solver["mumps_raw_infog"], {})

    def test_resource_fill_consumers_prefer_corrected_count(self) -> None:
        inventory = _factor_inventory(
            solver_type="mumps",
            infog_9=-2277,
            petsc_factor_nnz=-2_017_967_296.0,
        )
        summary = {
            "matrix_stats": {
                "matrix_rows": 10,
                "matrix_nnz_used": 1_000_000_000.0,
                "matrix_average_nnz_per_row": 100_000_000.0,
                "matrix_maximum_nnz_per_row": 8,
            },
            "stage4_dtn_factor_inventory": inventory,
        }
        audit = matrix_factor_resource_audit(summary)
        self.assertEqual(audit["factor_nnz"], 2_277_000_000)
        self.assertEqual(audit["factor_fill_ratio"], 2.277)
        self.assertGreater(audit["factor_average_row_width"], 0.0)
        self.assertEqual(
            audit["factor_average_row_width_source"],
            "corrected_factor_nnz_over_factor_rows",
        )
        self.assertEqual(
            audit["factor_nnz_source"],
            "mumps_infog_9_negative_millions",
        )

        same_error_summary = {
            **summary,
            "stage4_dtn_floquet_independent_matrix_stats": summary["matrix_stats"],
            "num_nedelec_dofs": 20,
            "stage4_dtn_base_matrix_assembly_seconds": 1.0,
            "stage4_dtn_assembly_time_total_build_seconds": 2.0,
            "stage4_dtn_ksp_setup_seconds": 3.0,
            "stage4_dtn_ksp_solve_seconds": 4.0,
            "stage4_dtn_linear_solve_seconds": 5.0,
            "stage4_dtn_cell_static_condensation_recovery_seconds": 6.0,
            "elapsed_seconds": 7.0,
        }
        record = {
            "resource_authority": {
                "memory_authority_gib": 8.0,
                "stage_peaks": [
                    {
                        "stage": "actual_r5_enriched_solve",
                        "max_mpi_process_tree_rss_mb": 1024.0,
                    }
                ],
            }
        }
        metrics = _resource_metrics(record, same_error_summary)
        self.assertEqual(metrics["factor_nnz"], 2_277_000_000)
        self.assertEqual(metrics["factor_fill"], 2.277)
        self.assertEqual(
            metrics["factor_nnz_source"],
            "mumps_infog_9_negative_millions",
        )

    def test_memory_forensics_ratios_never_use_negative_overflow(self) -> None:
        inventory = _factor_inventory(
            solver_type="mumps",
            infog_9=-2277,
            petsc_factor_nnz=-2_017_967_296.0,
        )
        inventory["matrix_stats"]["matrix_memory_estimate_mb"] = -123.0
        enriched = _enrich_factor_inventory(
            inventory,
            {
                "matrix_nnz_used": 100_000_000.0,
                "matrix_memory_estimate_mb": 2500.0,
            },
        )
        self.assertIsNotNone(enriched)
        ratios = enriched["derived_ratios"]
        self.assertEqual(
            ratios["factor_to_augmented_nnz_ratio"],
            22.77,
        )
        self.assertGreater(
            ratios["factor_to_augmented_estimated_storage_ratio"],
            0.0,
        )
        self.assertEqual(
            ratios["factor_estimated_storage_source"],
            "corrected_factor_nnz_complex128_int64_csr_estimate",
        )


if __name__ == "__main__":
    unittest.main()
