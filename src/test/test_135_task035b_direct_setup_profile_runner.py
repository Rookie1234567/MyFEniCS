from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.run_task035b_direct_setup_profile import (
    DIRECT_SETUP_TYPED_PETSC_OPTIONS,
    _cache_pairs,
    _classify_profile,
    _direct_config,
    _dtn_nonoverlapping_timing_ledger_checks,
    _dry_run_plan,
    _extract_setup_evidence,
    _parse_args,
    _petsc_factor_event_timing_formal_checks,
    _telemetry_summary,
    _validate_source_snapshot,
)
from src.common.config_3d import target_stage4_config


def _factor_event_audit() -> dict:
    event_names = {
        "symbolic": "MatLUFactorSym",
        "numeric": "MatLUFactorNum",
        "pc_setup": "PCSetUp",
    }
    packets = []
    for rank in range(8):
        symbolic = 0.50 + 1.0e-3 * rank
        numeric = 0.70 + 1.0e-3 * rank
        pc_setup = 1.30 + 2.0e-3 * rank
        packets.append(
            {
                "comm_rank": rank,
                "comm_size": 8,
                "world_rank": rank,
                "logging_active_before": False,
                "logging_started_by_profile": True,
                "logging_active_after_begin": True,
                "setup_wall_seconds": 6.0,
                "factor_solver_type": "mumps",
                "events": {
                    "symbolic": {
                        "event_name": "MatLUFactorSym",
                        "count": 1,
                        "seconds": symbolic,
                    },
                    "numeric": {
                        "event_name": "MatLUFactorNum",
                        "count": 1,
                        "seconds": numeric,
                    },
                    "pc_setup": {
                        "event_name": "PCSetUp",
                        "count": 1,
                        "seconds": pc_setup,
                    },
                },
                "errors": [],
            }
        )
    events = {}
    for role, event_name in event_names.items():
        counts = [packet["events"][role]["count"] for packet in packets]
        seconds = [
            packet["events"][role]["seconds"] for packet in packets
        ]
        events[role] = {
            "event_name": event_name,
            "count_per_rank": counts,
            "count_min": min(counts),
            "count_max": max(counts),
            "count_sum": sum(counts),
            "count_consistent_across_ranks": True,
            "count_positive_on_all_ranks": True,
            "seconds_per_rank": seconds,
            "seconds_min": min(seconds),
            "seconds_max": max(seconds),
            "seconds_sum": sum(seconds),
            "seconds_finite_nonnegative_on_all_ranks": True,
        }
    packet_sha = hashlib.sha256(
        json.dumps(
            packets,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    checks = {
        "requested_direct_only": True,
        "logging_active_after_begin_on_all_ranks": True,
        "no_snapshot_errors_on_any_rank": True,
        "communicator_rank_identity_valid": True,
        "event_values_finite_nonnegative_on_all_ranks": True,
        "event_counts_consistent_across_ranks": True,
        "event_counts_positive_on_all_ranks": True,
        "symbolic_numeric_counts_match": True,
        "symbolic_plus_numeric_within_pc_setup_on_all_ranks": True,
        "pc_setup_within_setup_wall_on_all_ranks": True,
    }
    return {
        "schema_version": "task035b.petsc-direct-factor-event-timing.v1",
        "requested": True,
        "enabled": True,
        "direct_only": True,
        "iterative_profile": None,
        "factor_solver_type": "mumps",
        "status": "measured_symbolic_numeric_split",
        "split_available": True,
        "event_names": event_names,
        "rank_count": 8,
        "ordered_world_ranks": list(range(8)),
        "collective_rank_payload_sha256": packet_sha,
        "per_rank": packets,
        "events": events,
        "symbolic_seconds_max": events["symbolic"]["seconds_max"],
        "numeric_seconds_max": events["numeric"]["seconds_max"],
        "pc_setup_seconds_max": events["pc_setup"]["seconds_max"],
        "checks": checks,
        "ordinary_default_changed": False,
    }


def _worker_result() -> dict:
    factor_event_audit = _factor_event_audit()
    return {
        "status": "worker_completed_with_summary",
        "rank_failures": [],
        "petsc_option_provenance": {
            "schema_version": (
                "task035b.collective-petsc-option-provenance.v1"
            ),
            "rank_count": 8,
            "raw_audit_present_on_all_ranks": True,
            "typed_audit_present_on_all_ranks": True,
            "raw_options_absent_on_all_ranks": True,
            "typed_allowlist_pass_on_all_ranks": True,
            "rank_audits_identical": True,
            "pass": True,
        },
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
            "stage4_dtn_mumps_symbolic_seconds": (
                factor_event_audit["symbolic_seconds_max"]
            ),
            "stage4_dtn_mumps_numeric_seconds": (
                factor_event_audit["numeric_seconds_max"]
            ),
            "stage4_dtn_petsc_factor_event_timing": (
                factor_event_audit
            ),
            "stage4_dtn_ksp_solve_seconds": 0.5,
            "stage4_dtn_base_matrix_assembly_seconds": 7.0,
            "stage4_dtn_base_rhs_assembly_seconds": 0.1,
            "stage4_dtn_augmented_block_copy_seconds": 0.0,
            "stage4_dtn_bilinear_form_compile_seconds": 0.0,
            "stage4_dtn_bilinear_form_compile_"
            "skipped_by_affine_backend": True,
            "stage4_dtn_incident_source_vector_seconds": 0.2,
            "stage4_dtn_surface_form_and_cache_setup_seconds": 0.3,
            "stage4_dtn_reduced_operator_identity_seconds": 0.01,
            "stage4_dtn_modal_loop_seconds": 2.0,
            "stage4_dtn_modal_vector_assembly_seconds": 1.7,
            "stage4_dtn_persistent_vector_restore_seconds": 0.05,
            "stage4_dtn_persistent_reduced_modal_bundle_restore_seconds": 0.02,
            "stage4_dtn_component_vector_assemblies": 0,
            "stage4_dtn_persistent_component_vector_restores": 2,
            "stage4_dtn_persistent_reduced_modal_bundle_restores": 80,
            "stage4_dtn_modal_block_insert_seconds": 0.1,
            "stage4_dtn_augmented_matrix_finalize_seconds": 0.3,
            "stage4_dtn_cell_interior_rhs_prepare_and_"
            "cache_release_seconds": 0.1,
            "stage4_dtn_warm_persistent_cache_heap_trim_seconds": 0.07,
            "stage4_dtn_linear_solve_seconds": 6.55,
            "stage4_dtn_cell_static_condensation_recovery_seconds": 0.4,
            "stage4_dtn_matrix_free_full_residual_seconds": 2.88,
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
                "stage4_persistent_fixed_trace_element_cache": True,
                "stage4_affine_isotropic_reference_tensor": True,
                "stage4_condensed_bulk_cell_insertion": False,
                "stage4_condensed_cache_directory": "/tmp/cache",
                "stage4_condensed_cache_source_sha": "a" * 40,
                "stage4_condensed_cache_mode": "read_only",
                "stage4_condensed_persistent_dtn_surface_cache": True,
                "stage4_preserve_structured_input_partition": True,
                "petsc_direct_solver_profile": "default",
                "stage4_condensed_iterative_profile": None,
                "stage4_petsc_factor_event_timing": True,
                "petsc_extra_options": dict(
                    DIRECT_SETUP_TYPED_PETSC_OPTIONS
                ),
            },
            "function_space_setup_audit": {
                "persistent_fixed_trace_element_cache": {
                    "schema_version": (
                        "task035b.fixed-trace-custom-element-cache.v1"
                    ),
                    "status": "persistent_fixed_trace_element_cache_hit",
                    "mode": "read_only",
                    "cache_hit_on_all_ranks": True,
                    "cache_miss_on_all_ranks": False,
                    "identity": {"source_sha": "a" * 40},
                    "read_seconds_max": 0.02,
                    "reconstruct_seconds_max": 0.4,
                    "build_seconds_max": 0.0,
                    "write_seconds_max": 0.0,
                    "payload_sha256": "b" * 64,
                    "serialization": "json_plus_npz_allow_pickle_false",
                    "ordinary_default_changed": False,
                },
            },
            "stage4_dtn_surface_vector_persistent_cache": {
                "schema_version": (
                    "task035b.dtn-reduced-modal-persistent-cache.v2"
                ),
                "enabled": True,
                "mode": "read_only",
                "source_commit_sha": "a" * 40,
                "payload_kind": (
                    "full_surface_vectors_plus_reduced_modal_bundles"
                ),
                "legacy_v1_payload_compatible": False,
                "material_and_tensor_identity_bound": True,
                "content_checksum_verified": True,
                "pickle_used": False,
                "identity_or_payload_mismatch_is_fail_closed": True,
                "inactive_modes_stored": False,
                "ordinary_default_changed": False,
                "hit_count_sum": 8,
                "miss_count_sum": 0,
                "hit_on_all_ranks": True,
                "collective_all_or_nothing": True,
                "restore_count_sum": 16,
                "record_count_sum": 0,
                "reduced_bundle_restore_count_sum": 640,
                "reduced_bundle_record_count_sum": 0,
                "unrestored_full_vector_array_count_sum": 1264,
                "write_count_sum": 0,
                "descriptor_count_per_rank": 160,
                "surface_order_count_per_rank": 80,
                "trace_projection_recomputed_after_restore": False,
                "cell_interior_bilinear_recomputed_after_restore": False,
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
            (root / "dtn_reduced_modal_c.json").touch()
            (root / "dtn_reduced_modal_c.npz").touch()
            (root / "fixed_trace_element_d.json").touch()
            (root / "fixed_trace_element_d.npz").touch()
            self.assertEqual(
                _cache_pairs(root, prefix="raw_tensor"),
                ["raw_tensor_a"],
            )
            self.assertEqual(
                _cache_pairs(root, prefix="condensed_class"),
                ["condensed_class_b"],
            )
            self.assertEqual(
                _cache_pairs(root, prefix="fixed_trace_element"),
                ["fixed_trace_element_d"],
            )
            self.assertEqual(
                _cache_pairs(root, prefix="dtn_reduced_modal"),
                ["dtn_reduced_modal_c"],
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
        self.assertTrue(
            plan["explicit_opt_ins"][
                "petsc_direct_factor_event_timing"
            ]
        )

    def test_direct_config_is_explicit_and_ordinary_default_stays_off(
        self,
    ) -> None:
        self.assertFalse(
            target_stage4_config(
                degree=6,
                h_nm=15.0,
            ).stage4_preserve_structured_input_partition
        )
        self.assertFalse(
            target_stage4_config(
                degree=6,
                h_nm=15.0,
            ).stage4_petsc_factor_event_timing
        )
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
        self.assertTrue(cfg.stage4_persistent_fixed_trace_element_cache)
        self.assertTrue(cfg.stage4_affine_isotropic_reference_tensor)
        self.assertFalse(cfg.stage4_condensed_bulk_cell_insertion)
        self.assertTrue(
            cfg.stage4_condensed_persistent_dtn_surface_cache
        )
        self.assertTrue(cfg.stage4_preserve_structured_input_partition)
        self.assertEqual(cfg.stage4_condensed_cache_mode, "read_only")
        self.assertEqual(cfg.stage4_condensed_cache_source_sha, "a" * 40)
        self.assertIsNone(cfg.stage4_condensed_iterative_profile)
        self.assertTrue(cfg.stage4_petsc_factor_event_timing)
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
        self.assertEqual(
            timings["mumps"]["symbolic"],
            _factor_event_audit()["symbolic_seconds_max"],
        )
        self.assertEqual(
            timings["mumps"]["numeric"],
            _factor_event_audit()["numeric_seconds_max"],
        )
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
        ledger = timings["dtn"]["nonoverlapping_ledger"]
        self.assertEqual(
            ledger["schema_version"],
            "task035b.dtn-nonoverlapping-timing-ledger.v1",
        )
        self.assertEqual(
            ledger["attributed_component_sum_seconds"],
            19.95,
        )
        self.assertAlmostEqual(
            ledger["unattributed_remainder_seconds"],
            0.05,
        )
        self.assertAlmostEqual(
            ledger["non_ksp_seconds"][
                "outer_minus_ksp_setup_and_backsolve"
            ],
            13.5,
        )
        self.assertAlmostEqual(
            ledger["non_ksp_seconds"][
                "attributed_components_including_linear_wrapper_overhead"
            ],
            13.45,
        )
        self.assertTrue(
            ledger[
                "nested_values_must_not_be_added_to_top_level_components"
            ]
        )
        self.assertTrue(
            all(
                evidence[
                    "dtn_nonoverlapping_timing_ledger_checks"
                ].values()
            )
        )
        self.assertEqual(
            timings["dtn"]["persistent_surface_cache_read"],
            0.15,
        )
        self.assertEqual(
            timings["dtn"]["reduced_operator_identity"],
            0.01,
        )
        self.assertEqual(
            timings["dtn"]["persistent_reduced_modal_bundle_restore"],
            0.02,
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

    def test_dtn_timing_ledger_fails_closed_on_missing_component(self) -> None:
        worker = _worker_result()
        del worker["summary"][
            "stage4_dtn_matrix_free_full_residual_seconds"
        ]
        evidence = _extract_setup_evidence(worker)
        ledger = evidence["dtn_nonoverlapping_timing_ledger"]
        checks = evidence["dtn_nonoverlapping_timing_ledger_checks"]
        self.assertEqual(
            ledger["missing_components"],
            ["matrix_free_full_explicit_residual"],
        )
        self.assertIsNone(
            ledger["attributed_component_sum_seconds"]
        )
        self.assertFalse(
            checks["dtn_timing_all_required_components_present"]
        )
        self.assertFalse(
            checks["dtn_timing_component_sum_independently_verified"]
        )
        self.assertFalse(
            checks[
                "dtn_timing_unattributed_remainder_"
                "independently_verified"
            ]
        )

    def test_dtn_timing_ledger_independent_checks_reject_mutation(self) -> None:
        evidence = _extract_setup_evidence(_worker_result())
        ledger = copy.deepcopy(
            evidence["dtn_nonoverlapping_timing_ledger"]
        )
        ledger["attributed_component_sum_seconds"] += 1.0
        ledger["unattributed_remainder_seconds"] -= 1.0
        checks = _dtn_nonoverlapping_timing_ledger_checks(ledger)
        self.assertFalse(
            checks["dtn_timing_component_sum_independently_verified"]
        )
        self.assertFalse(
            checks[
                "dtn_timing_unattributed_remainder_"
                "independently_verified"
            ]
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

        identity_evidence = _extract_setup_evidence(_worker_result())
        identity_evidence["cache_audit"]["dtn_surface_vector"][
            "material_and_tensor_identity_bound"
        ] = False
        invalid_identity = _classify_profile(
            identity_evidence,
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
        self.assertFalse(invalid_identity["formal_profile_pass"])
        self.assertIn(
            "dtn_reduced_modal_cache_v2_identity",
            invalid_identity["failures"],
        )

    def test_factor_event_split_is_rechecked_from_rank_packets(self) -> None:
        evidence = _extract_setup_evidence(_worker_result())
        self.assertTrue(
            all(
                _petsc_factor_event_timing_formal_checks(
                    evidence,
                    expected_mpi_size=8,
                ).values()
            )
        )

        corrupted = copy.deepcopy(evidence)
        corrupted["petsc_factor_event_timing"]["per_rank"][3][
            "events"
        ]["numeric"]["count"] = 0
        result = _classify_profile(
            corrupted,
            {
                "observed_worker_rank_count": 8,
                "max_process_tree_swap_mb": 0.0,
                "max_worker_rank_smaps_swap_sum_mb": 0.0,
            },
            cache_state="warm",
            source_sha="a" * 40,
            expected_mpi_size=8,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            telemetry_readable=True,
            source_stable_and_clean_after=True,
        )
        self.assertFalse(result["formal_profile_pass"])
        self.assertIn(
            "petsc_factor_event_counts_positive_consistent",
            result["failures"],
        )
        self.assertIn(
            "petsc_factor_event_collective_hash",
            result["failures"],
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
