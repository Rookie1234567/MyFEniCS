from __future__ import annotations

from argparse import Namespace
import unittest

from benchmarks.run_task035_actual_r5 import (
    _parse_args,
    _qualify,
    _qualify_common_mesh_sweep,
)


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

    def test_argument_contract_accepts_tolerance_normalized_multi_goal(self) -> None:
        args = _parse_args(
            [
                "--mesh-cell-type",
                "tetrahedron",
                "--dwr-adaptive-cycles",
                "1",
                "--dwr-marker-policy",
                "tolerance_normalized_R_T",
            ]
        )
        self.assertEqual(
            args.dwr_marker_policy,
            "tolerance_normalized_R_T",
        )

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

    def test_argument_contract_accepts_sha_bound_common_mesh_mode(self) -> None:
        args = _parse_args(
            [
                "--mesh-cell-type",
                "tetrahedron",
                "--common-mesh-replay-record",
                "authority.json",
                "--common-mesh-replay-sha256",
                "a" * 64,
                "--common-mesh-grazing-angles",
                "1,5,10",
            ]
        )
        self.assertEqual(args.common_mesh_replay_record.name, "authority.json")
        self.assertEqual(args.common_mesh_replay_sha256, "a" * 64)
        self.assertEqual(args.common_mesh_grazing_angles, (1.0, 5.0, 10.0))

    def test_argument_contract_accepts_sha_bound_hp_budget_mode(self) -> None:
        args = _parse_args(
            [
                "--mesh-cell-type",
                "tetrahedron",
                "--coarse-degree",
                "5",
                "--enriched-degree",
                "6",
                "--common-mesh-replay-record",
                "authority.json",
                "--common-mesh-replay-sha256",
                "a" * 64,
                "--common-mesh-replay-theta",
                "0.3",
                "--common-mesh-replay-expected-final-cells",
                "1200",
                "--common-mesh-grazing-angles",
                "10",
                "--hp-dof-ceiling",
                "169946",
                "--hp-accuracy-control-key",
                "p4_h7p5",
            ]
        )
        self.assertEqual(args.common_mesh_replay_theta, 0.3)
        self.assertEqual(args.common_mesh_replay_expected_final_cells, 1200)
        self.assertEqual(args.common_mesh_grazing_angles, (10.0,))
        self.assertEqual(args.hp_dof_ceiling, 169946)
        self.assertEqual(args.hp_accuracy_control_key, "p4_h7p5")

    def test_hp_budget_mode_requires_paired_control_and_ten_degrees(self) -> None:
        common = [
            "--mesh-cell-type",
            "tetrahedron",
            "--common-mesh-replay-record",
            "authority.json",
            "--common-mesh-replay-sha256",
            "a" * 64,
        ]
        with self.assertRaises(SystemExit):
            _parse_args([*common, "--hp-dof-ceiling", "169946"])
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    *common,
                    "--hp-dof-ceiling",
                    "169946",
                    "--hp-accuracy-control-key",
                    "p4_h7p5",
                    "--common-mesh-grazing-angles",
                    "1,5,10",
                ]
            )

    def test_common_mesh_record_requires_sha_authority(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--mesh-cell-type",
                    "tetrahedron",
                    "--common-mesh-replay-record",
                    "authority.json",
                ]
            )

    def test_common_mesh_mode_rejects_adaptive_cycle_mode(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--mesh-cell-type",
                    "tetrahedron",
                    "--common-mesh-replay-record",
                    "authority.json",
                    "--common-mesh-replay-sha256",
                    "a" * 64,
                    "--dwr-adaptive-cycles",
                    "1",
                ]
            )

    def test_common_mesh_angles_are_unique_and_physical(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--common-mesh-grazing-angles",
                    "1,1,10",
                ]
            )

    def test_common_mesh_positive_record_requires_every_angle_gate(self) -> None:
        authority_sha = "a" * 64
        args = Namespace(
            mpi_size=8,
            common_mesh_grazing_angles=(1.0, 5.0, 10.0),
            common_mesh_replay_sha256=authority_sha,
        )
        solve_summary = {
            "official_result": True,
            "linear_system_relative_residual": 1.0e-12,
            "mesh_cell_type_actual": "tetrahedron",
        }
        angles = []
        for grazing_angle in args.common_mesh_grazing_angles:
            incident_theta = 90.0 - grazing_angle
            angles.append(
                {
                    "grazing_angle_deg": grazing_angle,
                    "incident_theta_deg": incident_theta,
                    "actual_r5_pair": {
                        "status": "actual_global_r5_pass",
                        "target_identity": {
                            "grazing_angle_deg": grazing_angle,
                            "incidence_theta_deg": incident_theta,
                        },
                        "coarse": {"summary": dict(solve_summary)},
                        "enriched": {"summary": dict(solve_summary)},
                        "R5": {
                            "correction_energy": {
                                "relative_closure_error": 1.0e-14,
                            }
                        },
                        "ordinary_default_changed": False,
                    },
                }
            )
        result = {
            "status": "actual_common_mesh_angle_sweep_pass",
            "pass": True,
            "mesh_replay": {
                "pass": True,
                "single_in_memory_mesh_instance": True,
                "contract": {
                    "record_sha256": authority_sha,
                    "theta": 0.7,
                    "final_mesh_identity": {
                        "global_cell_count": 1316,
                    },
                },
            },
            "single_in_memory_mesh_instance": True,
            "angle_results": angles,
            "ordinary_default_changed": False,
        }
        sampler = {
            "max_observed_worker_rank_count": 8,
            "max_process_tree_swap_mb": 0.0,
        }
        qualification = _qualify_common_mesh_sweep(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertTrue(qualification["pass"])

        result["angle_results"][1]["actual_r5_pair"]["target_identity"][
            "incidence_theta_deg"
        ] = 80.0
        failed = _qualify_common_mesh_sweep(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertFalse(failed["pass"])
        self.assertIn("angle_identities_exact", failed["failures"])


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
