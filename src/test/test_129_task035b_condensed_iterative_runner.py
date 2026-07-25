from __future__ import annotations

import unittest

from benchmarks.run_task035b_condensed_iterative import (
    _classify_screen,
    _dry_run_plan,
    _extract_solver_evidence,
    _iterative_config,
    _parse_args,
    _telemetry_summary,
)


def _passing_worker_result() -> dict:
    return {
        "status": "worker_completed_with_summary",
        "rank_failures": [],
        "summary": {
            "case_status": "completed",
            "official_result": True,
            "diagnostic_only": False,
            "postprocess_skipped": False,
            "linear_solve_method": "assembled_condensed_iterative",
            "stage4_condensed_iterative_profile": "gmres_jacobi",
            "stage4_condensed_iterative": {
                "configured_programmatically": True,
                "raw_petsc_options_used_for_iterative_configuration": False,
                "assembled_reduced_operator": True,
                "matrix_free": False,
                "residual_history": [1.0, 1.0e-4],
                "residual_history_initial_norm": 1.0,
                "residual_history_final_norm": 1.0e-4,
                "residual_history_final_to_initial": 1.0e-4,
                "terminal_explicit_reduced_residual_norm": 1.0e-5,
                "terminal_explicit_reduced_relative_residual": 1.0e-6,
                "global_direct_factor_nnz": 0,
                "mumps_symbolic_or_numeric_created": False,
            },
            "stage4_dtn_factor_inventory": {
                "global_direct_factor_nnz": 0,
                "local_subdomain_ilu_active": False,
                "matrix_stats": None,
            },
            "actual_ksp_type": "gmres",
            "actual_pc_type": "jacobi",
            "ksp_converged": True,
            "ksp_converged_reason": 2,
            "ksp_converged_reason_name": "CONVERGED_RTOL",
            "ksp_iterations": 42,
            "mpi_size": 8,
            "mesh_cell_type_actual": "hexahedron",
            "mesh_cells_resolved": [6, 2, 10],
            "num_mesh_cells": 120,
            "num_nedelec_dofs": 74890,
            "matrix_stats": {
                "matrix_rows": 16880,
                "matrix_nnz_used": 9195812,
            },
            "config": {
                "mesh_target_size": 15.0,
                "nedelec_trace_degree_resolved": 5,
                "nedelec_interior_degree_resolved": 6,
            },
            "cell_static_condensation": {
                "full_explicit_true_residual": {
                    "linear_system_relative_residual": 2.0e-10,
                }
            },
        },
    }


def _passing_telemetry() -> dict:
    return {
        "observed_worker_rank_count": 8,
        "max_process_tree_swap_mb": 0.0,
        "max_worker_rank_smaps_swap_sum_mb": 0.0,
    }


class Task035bCondensedIterativeRunnerTests(unittest.TestCase):
    def test_default_is_stdout_only_not_run_plan(self) -> None:
        args = _parse_args([])
        plan = _dry_run_plan(args)
        self.assertFalse(args.execute_pde)
        self.assertEqual(
            plan["status"], "not_run_requires_explicit_execute_pde"
        )
        self.assertFalse(plan["pde_started"])
        self.assertFalse(plan["raw_petsc_options_accepted"])

    def test_explicit_profile_is_required_for_pde(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(["--execute-pde"])
        args = _parse_args(
            ["--execute-pde", "--profile", "fgmres_asm_ilu"]
        )
        self.assertEqual(args.profile, "fgmres_asm_ilu")

    def test_research_config_is_explicit_and_has_no_raw_petsc_options(self) -> None:
        cfg = _iterative_config("gmres_jacobi", h_nm=15.0)
        self.assertEqual(cfg.stage4_condensed_iterative_profile, "gmres_jacobi")
        self.assertTrue(cfg.stage4_assembly_time_cell_static_condensation)
        self.assertTrue(cfg.stage4_floquet_slave_elimination)
        self.assertEqual(cfg.nedelec_trace_degree_resolved, 5)
        self.assertEqual(cfg.nedelec_interior_degree_resolved, 6)
        self.assertTrue(cfg.stage4_fast_fixed_trace_setup)
        self.assertTrue(cfg.stage4_affine_isotropic_reference_tensor)
        self.assertFalse(cfg.stage4_condensed_bulk_cell_insertion)
        self.assertEqual(cfg.petsc_extra_options, {})
        self.assertFalse(cfg.matrix_diagnostics_assemble_only)

    def test_passing_screen_requires_factor_free_and_both_residuals(self) -> None:
        evidence = _extract_solver_evidence(_passing_worker_result())
        result = _classify_screen(
            evidence,
            _passing_telemetry(),
            expected_profile="gmres_jacobi",
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
        )
        self.assertTrue(result["formal_iterative_screen_pass"])
        self.assertEqual(
            result["status"], "actual_factor_free_iterative_screen_pass"
        )
        self.assertEqual(evidence["global_direct_factor_nnz"], 0)
        self.assertEqual(
            evidence["terminal_explicit_reduced_relative_residual"], 1.0e-6
        )
        self.assertEqual(evidence["full_recovered_true_residual"], 2.0e-10)

    def test_nonconvergence_is_a_preserved_controlled_negative(self) -> None:
        worker = _passing_worker_result()
        summary = worker["summary"]
        summary["official_result"] = False
        summary["diagnostic_only"] = True
        summary["ksp_converged"] = False
        summary["ksp_converged_reason"] = -3
        summary["stage4_condensed_iterative"][
            "residual_history_final_to_initial"
        ] = 0.2
        summary["stage4_condensed_iterative"][
            "terminal_explicit_reduced_relative_residual"
        ] = 0.2
        summary["cell_static_condensation"] = None
        evidence = _extract_solver_evidence(worker)
        result = _classify_screen(
            evidence,
            _passing_telemetry(),
            expected_profile="gmres_jacobi",
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
        )
        self.assertTrue(result["evidence_valid"])
        self.assertFalse(result["formal_iterative_screen_pass"])
        self.assertEqual(
            result["status"],
            "controlled_negative_iterative_nonconvergence",
        )
        self.assertEqual(result["classification"], "controlled_negative")

    def test_missing_worker_result_is_infrastructure_failure(self) -> None:
        evidence = _extract_solver_evidence(
            {"status": "worker_result_missing", "summary": None}
        )
        result = _classify_screen(
            evidence,
            _passing_telemetry(),
            expected_profile="gmres_jacobi",
            expected_mpi_size=8,
            return_code=3,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
        )
        self.assertFalse(result["evidence_valid"])
        self.assertEqual(
            result["status"], "iterative_watchdog_infrastructure_failure"
        )

    def test_telemetry_keeps_per_rank_pss_and_uss(self) -> None:
        rows = [
            {
                "stage": "solve",
                "worker_rank_rss_mb_json": (
                    '[{"rank":0,"rss_mb":10.0},{"rank":1,"rss_mb":11.0}]'
                ),
                "worker_rank_smaps_rollup_json": (
                    '[{"rank":0,"pss_mb":8.0,"uss_mb":7.0,'
                    '"rss_mb":10.0,"shared_mb":3.0,"anonymous_mb":6.0,'
                    '"swap_mb":0.0,"swap_pss_mb":0.0}]'
                ),
                "mpi_process_tree_rss_mb": 30.0,
                "mpi_process_tree_swap_mb": 0.0,
                "worker_rank_pss_sum_mb": 8.0,
                "worker_rank_uss_sum_mb": 7.0,
                "worker_rank_shared_sum_mb": 3.0,
                "worker_rank_smaps_swap_sum_mb": 0.0,
                "container_cgroup_current_mb": 35.0,
                "container_cgroup_peak_mb": 40.0,
                "worker_rank_rss_sum_mb": 21.0,
                "worker_rank_thread_count_sum": 2,
                "worker_rank_cpu_core_equivalents": 1.0,
            }
        ]
        summary = _telemetry_summary(rows)
        self.assertEqual(summary["observed_worker_ranks"], [0, 1])
        self.assertEqual(summary["max_worker_rank_pss_sum_mb"], 8.0)
        self.assertEqual(
            summary["per_rank_smaps_rollup_peaks_mb"]["0"]["uss_mb"],
            7.0,
        )


if __name__ == "__main__":
    unittest.main()
