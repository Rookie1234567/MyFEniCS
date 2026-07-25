from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from benchmarks.run_task035b_direct_setup_profile import (
    _cache_pairs,
    _classify_profile,
    _direct_config,
    _dry_run_plan,
    _extract_setup_evidence,
    _parse_args,
    _telemetry_summary,
    _validate_source_snapshot,
)


def _worker_result() -> dict:
    return {
        "status": "worker_completed_with_summary",
        "rank_failures": [],
        "worker_timings_seconds": {
            "solver_module_import_seconds": 1.25,
            "research_config_build_seconds": 0.02,
            "common_solver_call_seconds": 31.0,
        },
        "summary": {
            "case_status": "completed",
            "official_result": True,
            "diagnostic_only": False,
            "postprocess_skipped": False,
            "linear_solve_method": "direct_lu",
            "actual_ksp_type": "preonly",
            "actual_pc_type": "lu",
            "actual_pc_factor_solver_type": "mumps",
            "ksp_converged": True,
            "ksp_converged_reason": 4,
            "mpi_size": 8,
            "mesh_cell_type_actual": "hexahedron",
            "mesh_cells_resolved": [6, 2, 10],
            "num_mesh_cells": 120,
            "num_nedelec_dofs": 74890,
            "matrix_stats": {
                "matrix_rows": 16880,
                "matrix_nnz_used": 9195812,
                "matrix_nnz_allocated": 9200000,
            },
            "stage4_dtn_factor_inventory": {
                "factor_matrix_available": True,
                "factor_nnz": 123456,
            },
            "stage4_dtn_ksp_setup_seconds": 6.0,
            "stage4_dtn_ksp_solve_seconds": 0.5,
            "stage4_dtn_bilinear_form_compile_seconds": 0.0,
            "stage4_dtn_bilinear_form_compile_"
            "skipped_by_affine_backend": True,
            "stage4_dtn_incident_source_vector_seconds": 0.2,
            "stage4_dtn_surface_form_and_cache_setup_seconds": 0.3,
            "stage4_dtn_modal_loop_seconds": 2.0,
            "stage4_dtn_modal_vector_assembly_seconds": 1.7,
            "stage4_dtn_persistent_vector_restore_seconds": 0.05,
            "stage4_dtn_component_vector_assemblies": 0,
            "stage4_dtn_persistent_component_vector_restores": 160,
            "stage4_dtn_modal_block_insert_seconds": 0.1,
            "stage4_dtn_augmented_matrix_finalize_seconds": 0.3,
            "stage4_dtn_warm_persistent_cache_heap_trim_seconds": 0.07,
            "stage4_dtn_cell_static_condensation_recovery_seconds": 0.4,
            "stage4_dtn_solution_backsubstitution_seconds": 0.05,
            "R00_total": 0.72,
            "R_total": 0.8,
            "T_total": 0.19,
            "config": {
                "nedelec_trace_degree_resolved": 5,
                "nedelec_interior_degree_resolved": 6,
                "stage4_assembly_time_cell_static_condensation": True,
                "stage4_floquet_slave_elimination": True,
                "stage4_fast_fixed_trace_setup": True,
                "stage4_affine_isotropic_reference_tensor": True,
                "stage4_condensed_bulk_cell_insertion": False,
                "stage4_condensed_cache_directory": "/tmp/cache",
                "stage4_condensed_cache_source_sha": "a" * 40,
                "stage4_condensed_cache_mode": "read_only",
                "stage4_condensed_persistent_dtn_surface_cache": True,
            },
            "stage4_dtn_surface_vector_persistent_cache": {
                "enabled": True,
                "mode": "read_only",
                "source_commit_sha": "a" * 40,
                "hit_count_sum": 8,
                "miss_count_sum": 0,
                "hit_on_all_ranks": True,
                "collective_all_or_nothing": True,
                "restore_count_sum": 1280,
                "record_count_sum": 0,
                "write_count_sum": 0,
                "descriptor_count_per_rank": 160,
                "read_seconds_max": 0.15,
                "identity_and_key_seconds_max": 0.03,
                "write_seconds_max": 0.0,
            },
            "cell_static_condensation": {
                "full_explicit_true_residual": {
                    "linear_system_relative_residual": 2.0e-10,
                },
                "kernel_seconds_max": 0.08,
                "affine_reference_gram_seconds_max": 0.0,
                "affine_class_combination_seconds_max": 0.0,
                "orientation_seconds_max": 0.3,
                "aii_factor_seconds_max": 2.0,
                "aii_solve_seconds_max": 1.0,
                "schur_product_seconds_max": 0.8,
                "local_schur_seconds_max": 4.0,
                "constraint_projection_seconds_max": 0.2,
                "trace_preallocation_seconds": 0.06,
                "local_insert_seconds_max": 0.03,
                "pre_final_assembly_sync_seconds_max": 0.01,
                "final_assembly_seconds": 0.02,
                "raw_tensor_kernel_evaluation_count": 0,
                "raw_tensor_persistent_cache": {
                    "enabled": True,
                    "mode": "read_only",
                    "hit_count": 3,
                    "write_count": 0,
                    "read_seconds_max": 0.08,
                    "write_seconds_max": 0.0,
                },
                "persistent_condensed_class_cache": {
                    "enabled": True,
                    "mode": "read_only",
                    "hit_count_sum": 4,
                    "miss_count_sum": 0,
                    "construction_count_sum": 0,
                    "write_count_sum": 0,
                    "read_seconds_max": 0.04,
                    "identity_and_key_seconds_max": 0.01,
                    "write_seconds_max": 0.0,
                },
                "native_object_ledger": {
                    "python_visible_retained_bytes": 1000,
                },
            },
            "timings_seconds": {
                "mesh_build": 0.4,
                "function_space_setup": 2.0,
                "function_space_element_build_and_ufl_wrap": 0.03,
                "function_space_dolfinx_dofmap": 1.97,
                "stage4_dtn_port_assembly_and_solve": 20.0,
                "postprocess": 0.7,
                "diffraction_postprocess": 0.2,
                "volume_absorption_postprocess": 0.1,
            },
        },
    }


class Task035bDirectSetupProfileRunnerTests(unittest.TestCase):
    def test_cache_pair_inventory_distinguishes_raw_and_condensed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw_tensor_a.json").touch()
            (root / "raw_tensor_a.npy").touch()
            (root / "raw_tensor_incomplete.json").touch()
            (root / "condensed_class_b.json").touch()
            (root / "condensed_class_b.npz").touch()
            (root / "condensed_class_incomplete.npz").touch()
            (root / "dtn_surface_vectors_c.json").touch()
            (root / "dtn_surface_vectors_c.npz").touch()
            self.assertEqual(
                _cache_pairs(root, prefix="raw_tensor"),
                ["raw_tensor_a"],
            )
            self.assertEqual(
                _cache_pairs(root, prefix="condensed_class"),
                ["condensed_class_b"],
            )
            self.assertEqual(
                _cache_pairs(root, prefix="dtn_surface_vectors"),
                ["dtn_surface_vectors_c"],
            )

    def test_default_is_dry_run_and_describes_cold_warm_protocol(self) -> None:
        args = _parse_args([])
        plan = _dry_run_plan(args)
        self.assertFalse(args.execute_pde)
        self.assertFalse(plan["pde_started"])
        self.assertEqual(
            plan["status"],
            "not_run_requires_explicit_execute_pde",
        )
        self.assertEqual(plan["rank_study"], [1, 2, 4, 8])
        self.assertTrue(
            plan["explicit_opt_ins"][
                "persistent_sha_bound_raw_tensor_cache"
            ]
        )
        self.assertTrue(
            plan["explicit_opt_ins"][
                "persistent_sha_bound_condensed_class_cache"
            ]
        )
        self.assertTrue(
            plan["explicit_opt_ins"][
                "persistent_sha_mesh_mode_trace_bound_dtn_surface_cache"
            ]
        )

    def test_direct_config_is_explicit_and_ordinary_default_stays_off(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cfg = _direct_config(
                source_sha="a" * 40,
                cache_directory=Path(directory) / "cache",
                cache_state="warm",
                h_nm=15.0,
            )
        self.assertEqual(cfg.nedelec_trace_degree_resolved, 5)
        self.assertEqual(cfg.nedelec_interior_degree_resolved, 6)
        self.assertTrue(cfg.stage4_assembly_time_cell_static_condensation)
        self.assertTrue(cfg.stage4_floquet_slave_elimination)
        self.assertTrue(cfg.stage4_fast_fixed_trace_setup)
        self.assertTrue(cfg.stage4_affine_isotropic_reference_tensor)
        self.assertFalse(cfg.stage4_condensed_bulk_cell_insertion)
        self.assertTrue(
            cfg.stage4_condensed_persistent_dtn_surface_cache
        )
        self.assertEqual(cfg.stage4_condensed_cache_mode, "read_only")
        self.assertEqual(cfg.stage4_condensed_cache_source_sha, "a" * 40)
        self.assertIsNone(cfg.stage4_condensed_iterative_profile)
        self.assertFalse(cfg.matrix_diagnostics_assemble_only)
        self.assertEqual(
            cfg.petsc_extra_options["pc_factor_mat_solver_type"],
            "mumps",
        )

    def test_formal_source_gate_rejects_dirty_or_non_full_sha(self) -> None:
        with self.assertRaises(SystemExit):
            _validate_source_snapshot(
                commit_sha="a" * 40,
                branch=(
                    "codex/20260723-task35b-high-order-local-hp-"
                    "resource-envelope"
                ),
                porcelain_status=" M src/example.py",
            )
        with self.assertRaises(SystemExit):
            _validate_source_snapshot(
                commit_sha="abc123",
                branch=(
                    "codex/20260723-task35b-high-order-local-hp-"
                    "resource-envelope"
                ),
                porcelain_status="",
            )
        snapshot = _validate_source_snapshot(
            commit_sha="a" * 40,
            branch=(
                "codex/20260723-task35b-high-order-local-hp-"
                "resource-envelope"
            ),
            porcelain_status="",
        )
        self.assertTrue(snapshot["clean_full_sha_gate"])

    def test_record_extraction_keeps_all_requested_timing_groups(self) -> None:
        evidence = _extract_setup_evidence(_worker_result())
        timings = evidence["timings_seconds"]
        self.assertTrue(evidence["summary_available"])
        self.assertEqual(
            set(timings),
            {
                "import",
                "jit",
                "mesh",
                "function_space",
                "tensor",
                "aii_and_schur",
                "preallocation_and_insertion",
                "dtn",
                "mumps",
                "recovery",
                "postprocess",
                "outer_case",
                "common_solver_call",
            },
        )
        self.assertEqual(
            timings["mumps"]["symbolic_numeric_combined_ksp_setup"],
            6.0,
        )
        self.assertIsNone(timings["mumps"]["symbolic"])
        self.assertIsNone(timings["mumps"]["numeric"])
        self.assertEqual(timings["aii_and_schur"]["aii_factor"], 2.0)
        self.assertEqual(
            timings["aii_and_schur"]["persistent_class_read"],
            0.04,
        )
        self.assertEqual(
            timings["preallocation_and_insertion"][
                "trace_preallocation"
            ],
            0.06,
        )
        self.assertEqual(timings["dtn"]["non_ksp_derived"], 13.5)
        self.assertEqual(
            timings["dtn"]["persistent_surface_cache_read"],
            0.15,
        )
        self.assertEqual(
            timings["recovery"]["warm_persistent_cache_heap_trim"],
            0.07,
        )
        self.assertEqual(
            evidence["cell_static_raw_tensor_evaluations"],
            0,
        )
        self.assertEqual(evidence["full_true_residual"], 2.0e-10)
        self.assertEqual(
            evidence["cache_audit"]["condensed_class"][
                "construction_count_sum"
            ],
            0,
        )

    def test_warm_classification_requires_all_cache_layers(self) -> None:
        evidence = _extract_setup_evidence(_worker_result())
        telemetry = {
            "observed_worker_rank_count": 8,
            "max_process_tree_swap_mb": 0.0,
            "max_worker_rank_smaps_swap_sum_mb": 0.0,
        }
        result = _classify_profile(
            evidence,
            telemetry,
            cache_state="warm",
            source_sha="a" * 40,
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
            source_stable_and_clean_after=True,
        )
        self.assertTrue(result["formal_profile_pass"])

        evidence["cache_audit"]["condensed_class"][
            "construction_count_sum"
        ] = 1
        invalid = _classify_profile(
            evidence,
            telemetry,
            cache_state="warm",
            source_sha="a" * 40,
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
            source_stable_and_clean_after=True,
        )
        self.assertFalse(invalid["formal_profile_pass"])
        self.assertIn(
            "warm_condensed_class_cache_hit_without_recompute",
            invalid["failures"],
        )

        dtn_evidence = _extract_setup_evidence(_worker_result())
        dtn_evidence["cache_audit"]["dtn_surface_vector"][
            "hit_on_all_ranks"
        ] = False
        invalid_dtn = _classify_profile(
            dtn_evidence,
            telemetry,
            cache_state="warm",
            source_sha="a" * 40,
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
            source_stable_and_clean_after=True,
        )
        self.assertFalse(invalid_dtn["formal_profile_pass"])
        self.assertIn(
            "warm_dtn_surface_cache_hit_without_reassembly",
            invalid_dtn["failures"],
        )

    def test_watchdog_summary_preserves_pss_uss_and_cgroup(self) -> None:
        rows = [
            {
                "stage": "solve",
                "worker_rank_rss_mb_json": (
                    '[{"rank":0,"rss_mb":10.0},{"rank":1,"rss_mb":11.0}]'
                ),
                "worker_rank_smaps_rollup_json": (
                    '[{"rank":0,"rss_mb":10.0,"pss_mb":8.0,'
                    '"uss_mb":7.0,"shared_mb":3.0,"anonymous_mb":6.0,'
                    '"swap_mb":0.0,"swap_pss_mb":0.0},'
                    '{"rank":1,"rss_mb":11.0,"pss_mb":9.0,'
                    '"uss_mb":8.0,"shared_mb":3.0,"anonymous_mb":7.0,'
                    '"swap_mb":0.0,"swap_pss_mb":0.0}]'
                ),
                "worker_rank_smaps_readable_count": 2,
                "worker_rank_rss_sum_mb": 21.0,
                "worker_rank_pss_sum_mb": 17.0,
                "worker_rank_uss_sum_mb": 15.0,
                "worker_rank_shared_sum_mb": 6.0,
                "worker_rank_smaps_swap_sum_mb": 0.0,
                "worker_rank_thread_count_sum": 2,
                "worker_rank_thread_runtime_json": (
                    '[{"rank":1,"thread_count_observed":50,'
                    '"thread_name_counts":{"python":50},'
                    '"thread_wchan_counts":{"futex_wait_queue":49},'
                    '"loaded_parallel_runtime_libraries":["libblas.so"]}]'
                ),
                "worker_rank_cpu_core_equivalents": 1.0,
                "mpi_process_tree_rss_mb": 30.0,
                "mpi_process_tree_swap_mb": 0.0,
                "mpi_process_tree_thread_count": 3,
                "container_cgroup_current_mb": 35.0,
                "container_cgroup_peak_mb": 40.0,
                "container_swap_current_mb": 0.0,
            }
        ]
        summary = _telemetry_summary(rows)
        self.assertEqual(summary["observed_worker_ranks"], [0, 1])
        self.assertEqual(summary["max_worker_rank_pss_sum_mb"], 17.0)
        self.assertEqual(
            summary["per_rank_smaps_rollup_peaks_mb"]["1"]["uss_mb"],
            8.0,
        )
        self.assertEqual(summary["max_container_cgroup_peak_mb"], 40.0)
        self.assertEqual(
            summary["per_rank_peak_thread_runtime"]["1"][
                "thread_count_observed"
            ],
            50,
        )
        self.assertTrue(
            summary[
                "smaps_rollup_all_expected_ranks_readable_at_least_once"
            ]
        )


if __name__ == "__main__":
    unittest.main()
