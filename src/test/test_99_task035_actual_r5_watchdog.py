from __future__ import annotations

from argparse import Namespace
import unittest

from benchmarks.run_task035_actual_r5 import (
    _compact_solve,
    _parse_args,
    _qualify,
    _qualify_common_mesh_sweep,
    _qualify_goal_dwr,
    _qualify_regionwise_p,
)


class Task035ActualR5WatchdogTests(unittest.TestCase):
    def test_compact_solve_preserves_solver_lifecycle_audit(self) -> None:
        release_audit = {
            "petsc_garbage_cleanup_called": True,
            "process_heap_trim": {
                "succeeded_on_all_ranks": True,
                "sum_rss_before_mb": 16000.0,
                "sum_rss_after_mb": 11000.0,
            },
        }
        compact = _compact_solve(
            {
                "degree": 6,
                "h_nm": 10.0,
                "summary": {
                    "stage4_dtn_ksp_setup_seconds": 120.0,
                    "stage4_dtn_ksp_solve_seconds": 0.2,
                    "solver_objects_released_before_postprocess": True,
                    "solver_release_audit": release_audit,
                },
            }
        )
        self.assertEqual(compact["stage4_dtn_ksp_setup_seconds"], 120.0)
        self.assertEqual(compact["stage4_dtn_ksp_solve_seconds"], 0.2)
        self.assertTrue(
            compact["solver_objects_released_before_postprocess"]
        )
        self.assertEqual(compact["solver_release_audit"], release_audit)

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

    def test_static_condensation_is_explicit_fixed_hexa_pair_opt_in(self) -> None:
        args = _parse_args(
            [
                "--coarse-degree",
                "3",
                "--enriched-degree",
                "4",
                "--mesh-cell-type",
                "hexahedron",
                "--static-condensation-degree",
                "4",
                "--floquet-slave-elimination-degree",
                "4",
            ]
        )
        self.assertEqual(args.static_condensation_degree, [4])
        self.assertEqual(args.floquet_slave_elimination_degree, [4])
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "3",
                    "--enriched-degree",
                    "4",
                    "--static-condensation-degree",
                    "5",
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "3",
                    "--enriched-degree",
                    "4",
                    "--mesh-cell-type",
                    "tetrahedron",
                    "--static-condensation-degree",
                    "4",
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "3",
                    "--enriched-degree",
                    "4",
                    "--mesh-cell-type",
                    "hexahedron",
                    "--floquet-slave-elimination-degree",
                    "4",
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

    def test_argument_contract_accepts_formal_hexa_goal_dwr_only(self) -> None:
        args = _parse_args(
            [
                "--coarse-degree",
                "4",
                "--enriched-degree",
                "5",
                "--mesh-cell-type",
                "hexahedron",
                "--mpi-size",
                "8",
                "--h-nm",
                "10",
                "--goal-dwr-only",
            ]
        )
        self.assertTrue(args.goal_dwr_only)
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "5",
                    "--enriched-degree",
                    "6",
                    "--mesh-cell-type",
                    "hexahedron",
                    "--goal-dwr-only",
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "4",
                    "--enriched-degree",
                    "5",
                    "--mesh-cell-type",
                    "hexahedron",
                    "--goal-dwr-only",
                    "--dwr-adaptive-cycles",
                    "1",
                ]
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

    def test_regionwise_p_mode_requires_four_bound_authorities(self) -> None:
        args = _parse_args(
            [
                "--coarse-degree",
                "5",
                "--enriched-degree",
                "6",
                "--regionwise-p-classifier-record",
                "classifier.json",
                "--regionwise-p-classifier-sha256",
                "a" * 64,
                "--regionwise-p-control-record",
                "control.json",
                "--regionwise-p-control-sha256",
                "b" * 64,
            ]
        )
        self.assertEqual(
            args.regionwise_p_classifier_record.name, "classifier.json"
        )
        self.assertEqual(args.regionwise_p_control_sha256, "b" * 64)
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "5",
                    "--enriched-degree",
                    "6",
                    "--regionwise-p-classifier-record",
                    "classifier.json",
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "5",
                    "--enriched-degree",
                    "6",
                    "--regionwise-p-classifier-record",
                    "classifier.json",
                    "--regionwise-p-classifier-sha256",
                    "a" * 64,
                    "--regionwise-p-control-record",
                    "control.json",
                    "--regionwise-p-control-sha256",
                    "b" * 64,
                    "--single-mesh-pair",
                ]
            )

        mixed = _parse_args(
            [
                "--coarse-degree",
                "5",
                "--enriched-degree",
                "6",
                "--regionwise-p-classifier-record",
                "classifier.json",
                "--regionwise-p-classifier-sha256",
                "a" * 64,
                "--regionwise-p-control-record",
                "control.json",
                "--regionwise-p-control-sha256",
                "b" * 64,
                "--regionwise-p-trace-degree",
                "5",
                "--regionwise-p-low-interior-degree",
                "4",
                "--regionwise-p-high-cell-count",
                "62",
            ]
        )
        self.assertEqual(mixed.regionwise_p_trace_degree, 5)
        self.assertEqual(mixed.regionwise_p_low_interior_degree, 4)
        self.assertEqual(mixed.regionwise_p_high_cell_count, 62)
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--coarse-degree",
                    "5",
                    "--enriched-degree",
                    "6",
                    "--regionwise-p-classifier-record",
                    "classifier.json",
                    "--regionwise-p-classifier-sha256",
                    "a" * 64,
                    "--regionwise-p-control-record",
                    "control.json",
                    "--regionwise-p-control-sha256",
                    "b" * 64,
                    "--regionwise-p-trace-degree",
                    "5",
                    "--regionwise-p-low-interior-degree",
                    "4",
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
            "R00_total": 0.01,
            "R_total": 0.02,
            "T_total": 0.6,
            "A_volume_total": 0.38,
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
            "R00_total": 0.01,
            "R_total": 0.02,
            "T_total": 0.6,
            "A_volume_total": 0.38,
        }
        result = {
            "status": "actual_global_r5_pass",
            "ordinary_default_changed": False,
            "same_mesh_hashes": True,
            "coarse": {
                "summary": solve_summary,
                "high_order_resource_audit": {
                    "entity_dof_inventory": {"pass": True}
                },
            },
            "enriched": {
                "summary": solve_summary,
                "high_order_resource_audit": {
                    "entity_dof_inventory": {"pass": True}
                },
            },
            "R5": {
                "formal_hierarchical_fe_r5": True,
                "finite_cell_contributions": True,
                "nonnegative_cell_contributions": True,
                "correction_energy_norm": 1.0,
                "correction_energy": {"relative_closure_error": 1.0e-14},
                "marking": {"captured_fraction": 0.51},
                "canonical_marking": {"captured_fraction": 0.51},
                "owned_cell_contribution_count": 2,
                "mesh_geometry_sha256": "a" * 64,
                "cell_indicator_snapshot": {
                    "storage": "inline_complete_vector",
                    "cell_count": 2,
                    "canonical_cell_ids": [0, 1],
                    "indicator_values": [0.6, 0.4],
                    "mesh_geometry_sha256": "a" * 64,
                    "canonical_ids_and_values_sha256": "b" * 64,
                },
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

    def test_assembly_time_record_requires_effective_heap_trim(self) -> None:
        args = Namespace(
            mpi_size=8,
            theta=0.5,
            mesh_cell_type="hexahedron",
            assembly_time_condensation_degree=[6],
        )
        base_summary = {
            "official_result": True,
            "linear_system_relative_residual": 1.0e-12,
            "mesh_cell_type_actual": "hexahedron",
            "R00_total": 0.01,
            "R_total": 0.02,
            "T_total": 0.6,
            "A_volume_total": 0.38,
        }
        enriched_summary = {
            **base_summary,
            "stage4_assembly_time_cell_static_condensation": True,
            "cell_static_condensation": {
                "full_global_matrix_allocated": False,
                "full_trace_matrix_allocated": False,
                "full_explicit_true_residual": {
                    "eliminated_cell_interior_residual_norm": 1.0e-12,
                },
            },
            "config": {
                "petsc_extra_options": {"mat_mumps_icntl_14": 100},
            },
            "solver_objects_released_before_postprocess": True,
            "solver_release_audit": {
                "process_heap_trim": {
                    "succeeded_on_all_ranks": True,
                    "sum_rss_before_mb": 16000.0,
                    "sum_rss_after_mb": 11000.0,
                },
            },
        }
        result = {
            "status": "actual_global_r5_pass",
            "ordinary_default_changed": False,
            "same_mesh_hashes": True,
            "coarse": {
                "degree": 1,
                "summary": base_summary,
                "high_order_resource_audit": {
                    "entity_dof_inventory": {"pass": True},
                },
            },
            "enriched": {
                "degree": 6,
                "summary": enriched_summary,
                "high_order_resource_audit": {
                    "entity_dof_inventory": {"pass": True},
                },
            },
            "R5": {
                "formal_hierarchical_fe_r5": True,
                "finite_cell_contributions": True,
                "nonnegative_cell_contributions": True,
                "correction_energy_norm": 1.0,
                "correction_energy": {"relative_closure_error": 1.0e-14},
                "marking": {"captured_fraction": 0.51},
                "canonical_marking": {"captured_fraction": 0.51},
                "owned_cell_contribution_count": 2,
                "mesh_geometry_sha256": "a" * 64,
                "cell_indicator_snapshot": {
                    "storage": "inline_complete_vector",
                    "cell_count": 2,
                    "canonical_cell_ids": [0, 1],
                    "indicator_values": [0.6, 0.4],
                    "mesh_geometry_sha256": "a" * 64,
                    "canonical_ids_and_values_sha256": "b" * 64,
                },
            },
        }
        sampler = {
            "max_observed_worker_rank_count": 8,
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
        self.assertTrue(qualification["pass"], qualification)

        enriched_summary["solver_release_audit"]["process_heap_trim"][
            "sum_rss_after_mb"
        ] = 16000.0
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
        self.assertIn("requested_heap_trim_reduced_rss", failed["failures"])

    def test_regionwise_controlled_negative_preserves_valid_execution(self) -> None:
        classifier_sha = "a" * 64
        control_sha = "b" * 64
        geometry_sha = "c" * 64
        args = Namespace(
            mpi_size=8,
            regionwise_p_classifier_sha256=classifier_sha,
            regionwise_p_control_sha256=control_sha,
            regionwise_p_trace_degree=4,
            regionwise_p_low_interior_degree=4,
            regionwise_p_high_cell_count=None,
        )
        summary = {
            "official_result": True,
            "num_mesh_cells": 252,
            "mesh_cell_type_actual": "hexahedron",
            "linear_system_relative_residual": 1.0e-12,
            "matrix_stats": {
                "matrix_rows": 21824,
                "matrix_nnz_used": 8_000_000.0,
                "matrix_average_nnz_per_row": 366.0,
                "matrix_maximum_nnz_per_row": 700,
            },
            "stage4_dtn_factor_inventory": {"available": True},
            "cell_static_condensation": {
                "matrix_rows": 21824,
                "regionwise_mesh_geometry_sha256": geometry_sha,
                "regionwise_interior_p_active": True,
                "regionwise_high_cell_count": 105,
                "regionwise_low_cell_count": 147,
                "active_full3d_equivalent_dofs": 88994,
                "inactive_max_p_rows_retained_in_matrix": False,
                "full_global_matrix_allocated": False,
                "full_trace_matrix_allocated": False,
                "regionwise_low_cell_kernel_compiled_directly": True,
                "full_explicit_true_residual": {
                    "linear_system_relative_residual": 1.0e-12,
                },
            },
            "floquet_num_constraints": 6000,
            "floquet_x_face_mismatch": 0.0,
            "floquet_y_face_mismatch": 0.0,
            "floquet_edge_corner_mismatch": 0.0,
            "max_face_pairing_coordinate_error": 0.0,
            "nedelec_orientation_factor_stats": {
                "uses_exact_basix_entity_transforms": True,
                "uses_local_moment_fit": False,
            },
            "mesh_material_plane_alignment": {"all_aligned": True},
            "domain_tag_volumes": {
                "air": 1.0,
                "substrate": 1.0,
                "grating": 1.0,
            },
        }
        result = {
            "status": "actual_regionwise_p_controlled_negative",
            "pass": True,
            "candidate_accuracy_pass": False,
            "ordinary_default_changed": False,
            "target_identity": {
                "geometry": "Task034 fixed rectangular block grating",
                "mesh_geometry_sha256": geometry_sha,
                "trace_degree": 4,
                "low_interior_degree": 4,
                "high_interior_degree": 6,
            },
            "classifier_authority": {
                "sha256": classifier_sha,
                "high_canonical_cell_count": 105,
                "active_full3d_equivalent_dofs": 88994,
            },
            "control_authority": {"sha256": control_sha},
            "candidate": {
                "degree": 6,
                "h_nm": 10.0,
                "summary": summary,
                "high_order_resource_audit": {
                    "entity_dof_inventory": {"pass": True}
                },
            },
            "observable_comparison": {
                "schema_version": (
                    "task035b.regionwise-p-observable-comparison.v1"
                ),
                "all_scalar_same_code_bands_pass": False,
                "normalized_R_T_Aclosure_vector_pass": False,
            },
            "diffraction_channel_comparison": {
                "channel_count": 80,
                "pass": False,
            },
            "selected_field_interface_error_gate": {
                "status": "measured_common_native_visualization_points",
                "no_threshold_relaxation": True,
                "pass": False,
            },
        }
        sampler = {
            "max_observed_worker_rank_count": 8,
            "max_process_tree_swap_mb": 0.0,
        }
        qualification = _qualify_regionwise_p(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertTrue(qualification["pass"], qualification)

        summary["cell_static_condensation"][
            "inactive_max_p_rows_retained_in_matrix"
        ] = True
        failed = _qualify_regionwise_p(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertFalse(failed["pass"])
        self.assertIn("inactive_p6_rows_not_retained", failed["failures"])

    def test_goal_dwr_only_qualification_requires_all_three_goals(self) -> None:
        summary = {
            "official_result": True,
            "linear_system_relative_residual": 1.0e-12,
            "mesh_cell_type_actual": "hexahedron",
            "num_mesh_cells": 252,
        }
        goal = {
            "finite_nonnegative_cell_contributions": True,
            "marking": {"captured_fraction": 0.6},
            "absolute_effectivity": 1.0,
            "signed_goal_change_closure": 0.0,
            "mesh_geometry_sha256": "a" * 64,
            "marked_geometry_sha256": "b" * 64,
        }
        marker = {
            "finite_nonnegative_cell_contributions": True,
            "marking": {"captured_fraction": 0.6},
            "mesh_geometry_sha256": "a" * 64,
            "marked_geometry_sha256": "c" * 64,
        }
        result = {
            "status": "target_goal_weighted_two_level_pass",
            "pass": True,
            "ordinary_default_changed": False,
            "target_identity": {
                "geometry": "Task034 fixed rectangular block grating",
                "mesh_backend": "boundary-fitted conforming hexahedron",
                "h_nm": 10.0,
            },
            "coarse": {"degree": 4, "summary": dict(summary)},
            "enriched": {"degree": 5, "summary": dict(summary)},
            "DWR": {
                "residual": {
                    "enriched_solution_relative_residual_recomputed": 1.0e-12
                },
                "adjoint_qualification": {"pass": True},
                "goals": {
                    "R00_total": dict(goal),
                    "R_total": dict(goal),
                    "T_total": dict(goal),
                },
                "combined_relative_R_T": dict(marker),
                "tolerance_normalized_R_T": {
                    **marker,
                    "normalization_authority": {
                        "independent_adjoint_goals": ["R_total", "T_total"]
                    },
                },
                "rejected_localization": {
                    "decision": "controlled_negative_partition_dependent"
                },
            },
            "R5_control": {
                "correction_energy": {"relative_closure_error": 1.0e-12}
            },
        }
        args = Namespace(mpi_size=8, theta=0.5)
        sampler = {
            "max_observed_worker_rank_count": 8,
            "max_process_tree_swap_mb": 0.0,
        }
        qualification = _qualify_goal_dwr(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertTrue(qualification["pass"], qualification)

        del result["DWR"]["goals"]["R00_total"]
        failed = _qualify_goal_dwr(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertFalse(failed["pass"])
        self.assertIn(
            "all_R00_R_T_goal_reports_qualified",
            failed["failures"],
        )


if __name__ == "__main__":
    unittest.main()
