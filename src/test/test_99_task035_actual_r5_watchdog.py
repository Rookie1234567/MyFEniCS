from __future__ import annotations

from argparse import Namespace
import unittest

from benchmarks.run_task035_actual_r5 import _parse_args, _qualify


class Task035ActualR5WatchdogTests(unittest.TestCase):
    def test_argument_contract_rejects_non_enriched_degree(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "2",
                    "--enriched-degree",
                    "2",
                ]
            )
    def test_argument_contract_accepts_one_dwr_adaptive_mode(self) -> None:
        args = _parse_args(
            [
                "--mesh-cell-type",
                "tetrahedron",
                "--dwr-adaptive-cycles",
                "1",
                "--dwr-marker-policy",
                "R_total",
                "--minimal-periodic-edge-closure",
            ]
        )
        self.assertEqual(args.dwr_adaptive_cycles, 1)
        self.assertEqual(args.dwr_marker_policy, "R_total")
        self.assertTrue(args.minimal_periodic_edge_closure)

    def test_argument_contract_rejects_multiple_cycle_modes(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--mesh-cell-type",
                    "tetrahedron",
                    "--adaptive-marked-cycles",
                    "1",
                    "--dwr-adaptive-cycles",
                    "1",
                ]
            )

    def test_minimal_periodic_closure_requires_dwr_mode(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--minimal-periodic-edge-closure",
                ]
            )


    def test_positive_record_requires_all_numerical_and_resource_gates(self) -> None:
        args = Namespace(mpi_size=2, theta=0.5, mesh_cell_type="tetrahedron")
        solve_summary = {
            "official_result": True,
            "linear_system_relative_residual": 1.0e-12,
            "mesh_cell_type_actual": "tetrahedron",
        }
        result = {
            "status": "actual_global_r5_pass",
            "ordinary_default_changed": False,
            "coarse": {"summary": solve_summary},
            "enriched": {"summary": solve_summary},
            "R5": {
                "formal_hierarchical_fe_r5": True,
                "finite_cell_contributions": True,
                "nonnegative_cell_contributions": True,
                "correction_energy_norm": 1.0,
                "correction_energy": {"relative_closure_error": 1.0e-14},
                "marking": {"captured_fraction": 0.51},
            },
        }
        sampler = {
            "max_observed_worker_rank_count": 2,
            "max_process_tree_swap_mb": 0.0,
        }
        qualification = _qualify(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertTrue(qualification["pass"])
        self.assertEqual(qualification["failures"], [])

        result["R5"]["correction_energy"]["relative_closure_error"] = 1.0e-5
        failed = _qualify(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertFalse(failed["pass"])
        self.assertIn("cell_energy_closure_le_1e-10", failed["failures"])


if __name__ == "__main__":
    unittest.main()
