from __future__ import annotations

import copy
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from benchmarks import run_task033_case090_pde_core
from benchmarks import task033_case090_pde_core as core
from src.validation.task033_high_order_floquet_fixtures import (
    build_case090_record,
)


ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = ROOT / "benchmarks" / "cases" / core.CASE_ID


def _probe(degree: int, mpi_size: int) -> dict:
    return {
        "degree": degree,
        "mpi_size": mpi_size,
        "constraint_round_trip_relative_error": 1.0e-14,
        "bloch_trace_mismatch": 2.0e-13,
        "reduced_full_action_relative_error": 3.0e-13,
        "constraint_rows": 10 * degree,
        "constraint_nnz": 10 * degree,
        "phase_cache_probe": {
            "second_angle_deg_from_normal": 41.0,
            "topology_cache_hit": True,
            "topology_build_seconds_current": 0.0,
            "phase_update_seconds": 1.0e-4,
            "communication_bytes_sent_current": 0,
            "communication_bytes_received_current": 0,
            "global_constraint_rows": 10 * degree,
            "global_constraint_nnz": 10 * degree,
            "topology_rebuilt": False,
        },
        "full_operator": {
            "form": "inner(curl(u),curl(v)) + inner(u,v)",
            "matrix_type": "mpiaij" if mpi_size > 1 else "seqaij",
            "matrix_nnz": 100 * degree,
            "coercive": True,
        },
        "embedded_reduced_operator": {
            "matrix_type": "mpiaij" if mpi_size > 1 else "seqaij",
            "matrix_nnz": 120 * degree,
            "slave_input_entries_zero": True,
        },
        "constraint_prolongation": {
            "matrix_type": "mpiaij" if mpi_size > 1 else "seqaij",
            "matrix_nnz": 50 * degree,
            "representation": "sparse full-by-full embedding with zero slave columns",
        },
        "reduced_full_action_paths": {
            "assembled": "dolfinx_mpc assembled embedded reduced operator times q",
            "explicit": "C^H times assembled full H(curl) operator times C q",
            "random_vector": "deterministic nonzero free entries and zero slave entries",
        },
        "all_action_matrices_sparse": True,
        "sparse_distributed_constraints": True,
        "global_boundary_allgather_used": False,
        "dense_boundary_square_formed": False,
        "core_algebra_gates_passed": True,
        "method": "synthetic true matrix-action contract fixture",
    }


def _result(entry: dict, *, perturbation: float = 0.0) -> dict:
    fixture_a = entry["fixture"] == "fixture_a_air_box"
    field_error = 2.0e-3
    reflection_error = 3.0e-3
    transmission_error = 4.0e-3
    amplitude_evidence = None
    artifact_validation = None
    if not fixture_a:
        amplitude_evidence = {
            "status": "ok",
            "definition": "synthetic official zero-order DtN fixture",
            "source_files": ["port_power.json", "flat_layer_reference.json"],
            "reflection_top": {
                "analytic_interface_amplitude": [0.2, 0.1],
                "boundary_phase": [1.0, 0.0],
                "analytic_boundary_amplitude": [0.2, 0.1],
                "numerical_outgoing_amplitude_at_boundary": [0.203, 0.1],
                "absolute_error": reflection_error,
                "relative_error": 1.34e-2,
                "phase_error_rad": 1.0e-2,
            },
            "transmission_bottom": {
                "analytic_interface_amplitude": [0.8, -0.1],
                "boundary_phase": [1.0, 0.0],
                "analytic_boundary_amplitude": [0.8, -0.1],
                "numerical_outgoing_amplitude_at_boundary": [0.804, -0.1],
                "absolute_error": transmission_error,
                "relative_error": 4.96e-3,
                "phase_error_rad": 6.0e-4,
            },
        }
        artifact_validation = {
            "status": "completed",
            "method": core.NATIVE_VTU_ORACLE_METHOD,
            "field_errors": {
                "relative_max_abs_E_error": 1.0e-3,
                "relative_max_abs_H_error": field_error,
                "global_rank_local_points_compared": (
                    32 if entry["mesh_target_nm"] == 5.0 else 384
                ),
                "interface_points_excluded": True,
                "reduction": core.NATIVE_VTU_ORACLE_REDUCTION,
            },
            "zero_order_complex_amplitudes": amplitude_evidence,
            "failures": [],
        }
    return {
        **entry,
        "case_status": "completed",
        "official_result": True,
        "discretization": {
            "mesh_cells": 8,
            "full_nedelec_dofs": 100 * entry["degree"],
            "constrained_rows": 100 * entry["degree"],
            "matrix_nnz": 1000 * entry["degree"],
            "constraint_rows": 20 * entry["degree"],
            "constraint_nnz": 20 * entry["degree"],
            "constraint_mode": (
                "topological_edges_p1"
                if entry["degree"] == 1
                else f"topological_trace_p{entry['degree']}"
            ),
        },
        "algebra": {
            "full_true_residual": 1.0e-13,
            "bloch_mismatch": {
                "x_face": 1.0e-13,
                "y_face": 1.0e-13,
                "edge_corner": 0.0,
            },
            "bloch_trace_mismatch_max": 1.0e-13,
            "sparse_distributed_constraints": True,
            "global_boundary_allgather_used": False,
            "dense_boundary_square_formed": False,
        },
        "periodic_constraint": {
            "global_constraint_rows": 20 * entry["degree"],
            "global_constraint_nnz": 20 * entry["degree"],
            "max_masters_per_slave": entry["degree"],
            "rank0_local_slaves": 20 * entry["degree"],
            "rank0_local_slave_records_seen": 20 * entry["degree"],
            "rank0_local_ghost_slave_constraints": 0,
            "global_ghost_slave_constraints": 0,
            "rank0_local_ghost_slave_records_skipped": 0,
            "global_ghost_slave_records_skipped": 0,
            "slave_edges": 4,
            "matched_master_edges": 4,
            "slave_faces": 2 if entry["degree"] > 1 else 0,
            "matched_master_faces": 2 if entry["degree"] > 1 else 0,
            "edge_constraint_rows": 20 * entry["degree"],
            "face_constraint_rows": 0,
            "x_constraint_rows": 10 * entry["degree"],
            "y_constraint_rows": 8 * entry["degree"],
            "corner_constraint_rows": 2 * entry["degree"],
            "topology_cache_hit": False,
            "topology_cache_miss": True,
            "topology_build_seconds_current": 0.05,
            "phase_update_seconds": 0.01,
            "constraint_setup_outer_seconds": 0.1,
            "constraint_total_seconds": 0.08,
            "constraint_timings_seconds": {"floquet_total": 0.08},
            "communication_bytes_sent_current": 100 * entry["mpi_size"],
            "communication_bytes_received_current": 100 * entry["mpi_size"],
            "rank_local_semantics_note": "synthetic root/global semantics",
        },
        "fields": {
            "relative_max_abs_E_error": 1.0e-3,
            "relative_max_abs_H_error": field_error,
            "max_abs_E": None if fixture_a else 1.0,
            "max_abs_H": None if fixture_a else 0.9,
            "oracle_method": "synthetic oracle",
        },
        "zero_order_complex_amplitudes": amplitude_evidence,
        "artifact_validation": artifact_validation,
        "power": {
            "R_total": None if fixture_a else 0.2 + perturbation,
            "T_total": None if fixture_a else 0.7,
            "R_plus_T": None if fixture_a else 0.9,
            "A_volume_total": None if fixture_a else 0.1,
            "port_volume_closure_error": None if fixture_a else 0.0,
            "R_port_minus_R_ref": None if fixture_a else 1.0e-4,
            "T_port_minus_T_ref": None if fixture_a else -2.0e-4,
            "A_volume_minus_A_ref": None if fixture_a else 1.0e-4,
        },
        "resources": {
            "max_rank_historical_peak_rss_mb": 100.0,
            "sum_rank_historical_peaks_mb_upper_bound": 100.0 * entry["mpi_size"],
            "rss_semantics": "historical_rank_peaks_not_simultaneous_rss",
            "elapsed_seconds": 1.0,
            "timings_seconds": {"solve": 0.5},
            "floquet_timings_seconds": {"floquet_total": 0.1},
        },
        "physical_error_scalar": (
            field_error if fixture_a else max(field_error, reflection_error, transmission_error)
        ),
        "physical_qualification_passed": True,
        "numerical_gates_passed": True,
        "gate_failures": [],
    }


def _shard(mpi_size: int) -> dict:
    source = core.SourceIdentity("1" * 40, False)
    return core.build_shard_record(
        mpi_size=mpi_size,
        source_at_start=source,
        source_at_end=source,
        algebra_probes=[_probe(degree, mpi_size) for degree in core.DEGREES],
        results=[_result(entry) for entry in core.build_shard_plan(mpi_size)],
    )


def _memory_summary(mpi_size: int) -> dict:
    limit = 8_000_000_000
    warning_threshold = int(limit * (11.5 / 14.0))
    termination_threshold = int(limit * (13.0 / 14.0))
    return core.attach_evidence_sha256(
        {
            "schema_version": core.WATCHDOG_SCHEMA_VERSION,
            "record_type": "external_shard_memory_watchdog",
            "case_id": core.CASE_ID,
            "status": "passed",
            "identity": {
                "mpi_size": mpi_size,
                "source_commit_full_sha": "1" * 40,
                "source_commit_at_end_full_sha": "1" * 40,
                "tracked_source_dirty_at_start": False,
                "tracked_source_dirty_at_end": False,
                "source_worktree_dirty_at_start": False,
                "source_worktree_dirty_at_end": False,
                "nonignored_untracked_paths_at_start": [],
                "nonignored_untracked_paths_at_end": [],
                "source_cleanliness_semantics": (
                    "tracked changes plus all nonignored untracked paths"
                ),
                "source_clean_and_stable": True,
            },
            "worker": {
                "command": ["mpiexec", "-n", str(mpi_size)],
                "launched": True,
                "pid": 1234,
                "exit_code": 0,
            },
            "preflight": {
                "passed": True,
                "cgroup_memory_limit_state": "finite",
                "cgroup_memory_limit_bytes": limit,
                "cgroup_memory_current_bytes": 100_000_000,
                "host_available_memory_bytes": 16_000_000_000,
                "swap_current_bytes": 0,
                "effective_memory_bytes": limit,
                "effective_memory_definition": "synthetic authority",
                "warning_threshold_bytes": warning_threshold,
                "termination_threshold_bytes": termination_threshold,
                "warning_scale": 11.5 / 14.0,
                "termination_scale": 13.0 / 14.0,
                "failures": [],
            },
            "sampling": {
                "sample_interval_seconds": 1.0,
                "sample_count": 3,
                "worker_tree_rss_peak_bytes": 100_000_000,
                "cgroup_memory_current_peak_bytes": 120_000_000,
                "observed_memory_peak_bytes": 120_000_000,
                "observed_memory_definition": "max(worker RSS, cgroup current)",
                "cgroup_memory_limit_bytes": limit,
                "cgroup_memory_limit_state": "finite",
                "effective_memory_bytes": limit,
                "warning_threshold_bytes": warning_threshold,
                "termination_threshold_bytes": termination_threshold,
                "host_available_memory_min_bytes": 16_000_000_000,
                "swap_current_initial_bytes": 0,
                "swap_current_final_bytes": 0,
                "swap_current_peak_bytes": 0,
                "swap_current_delta_bytes": 0,
                "swap_current_net_delta_bytes": 0,
                "nonzero_swap_sample_count": 0,
                "authority_unreadable_sample_count": 0,
                "raw_output": "benchmarks/artifacts/case090/watchdog_raw.jsonl",
                "raw_output_ignored_by_git": True,
                "summary_output_ignored_by_git": True,
                "sources": {
                    "cgroup_memory_current": ["/sys/fs/cgroup/memory.current"],
                    "cgroup_memory_limit": ["/sys/fs/cgroup/memory.max"],
                    "swap_current": ["/sys/fs/cgroup/memory.swap.current"],
                },
            },
            "control": {
                "wall_timeout_seconds": 86400.0,
                "termination_grace_seconds": 5.0,
                "warning_triggered": False,
                "warning_first_observed_bytes": None,
                "termination_trigger": None,
                "termination_detail": None,
                "wall_timeout_triggered": False,
                "controlled_termination": False,
                "process_tree_cleanup": None,
                "threshold_rule": "synthetic scaled rule",
            },
            "qualification": {
                "memory_summary_qualified": True,
                "requires_zero_swap_every_sample": True,
                "requires_finite_container_limit": True,
                "warning_scale": 11.5 / 14.0,
                "termination_scale": 13.0 / 14.0,
            },
            "failures": [],
        }
    )


class Task033Case090PDECoreRecordTests(unittest.TestCase):
    def test_source_identity_rejects_nonignored_untracked_python_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args: str) -> None:
                subprocess.run(
                    ["git", *args],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            git("init")
            git("config", "user.email", "task033@example.invalid")
            git("config", "user.name", "Task033 Test")
            (root / ".gitignore").write_text("artifacts/\n", encoding="utf-8")
            (root / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
            git("add", ".gitignore", "tracked.py")
            git("commit", "-m", "clean source")
            clean = core.inspect_tracked_source(root)
            self.assertFalse(clean.tracked_source_dirty)

            ignored = root / "artifacts"
            ignored.mkdir()
            (ignored / "raw.jsonl").write_text("{}\n", encoding="utf-8")
            still_clean = core.inspect_tracked_source(root)
            self.assertFalse(still_clean.tracked_source_dirty)

            (root / "uncommitted_solver.py").write_text(
                "SHOULD_NOT_RUN = True\n", encoding="utf-8"
            )
            dirty = core.inspect_tracked_source(root)
            self.assertTrue(dirty.tracked_source_dirty)
            self.assertIn(
                "uncommitted_solver.py", dirty.nonignored_untracked_paths
            )

    @unittest.skipUnless(
        os.environ.get("RUN_TASK033_CORE_DOCKER_TESTS") == "1",
        "Set RUN_TASK033_CORE_DOCKER_TESTS=1 in the DOLFINx image.",
    )
    def test_real_sparse_hcurl_matrix_action_p1_to_p4(self) -> None:
        from mpi4py import MPI

        for degree in core.DEGREES:
            with self.subTest(degree=degree, mpi_size=MPI.COMM_WORLD.size):
                result = core.run_algebra_probe(
                    degree=degree,
                    mpi_size=MPI.COMM_WORLD.size,
                    out_dir=(
                        Path(tempfile.gettempdir())
                        / f"task033_test56_action_mpi{MPI.COMM_WORLD.size}"
                        / f"p{degree}"
                    ),
                )
                self.assertTrue(result["core_algebra_gates_passed"])
                self.assertTrue(result["all_action_matrices_sparse"])
                self.assertTrue(result["phase_cache_probe"]["topology_cache_hit"])
                self.assertFalse(result["phase_cache_probe"]["topology_rebuilt"])
                self.assertLessEqual(
                    result["reduced_full_action_relative_error"], 1.0e-11
                )
                self.assertEqual(
                    result["reduced_full_action_paths"]["explicit"],
                    "C^H times assembled full H(curl) operator times C q",
                )

    @unittest.skipUnless(
        os.environ.get("RUN_TASK033_CORE_DOCKER_TESTS") == "1",
        "Set RUN_TASK033_CORE_DOCKER_TESTS=1 in the DOLFINx image.",
    )
    def test_real_fixture_b_vtu_and_complex_amplitude_oracles(self) -> None:
        from mpi4py import MPI

        if MPI.COMM_WORLD.size != 1:
            self.skipTest("The artifact oracle integration case is exercised on MPI1.")
        entry = next(
            item
            for item in core.build_shard_plan(1)
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 10.0
            and item["polarization"] == "s"
            and item["degree"] == 1
            and item["mesh_target_nm"] == 5.0
        )
        out_dir = (
            Path(tempfile.gettempdir())
            / "task033_test56_fixture_b_artifact_oracle"
        )
        summary = core.run_pde_case(entry, out_dir)
        evidence = core.extract_case_artifact_validation(entry, out_dir)
        self.assertEqual(summary["case_status"], "completed")
        self.assertEqual(evidence["status"], "completed")
        self.assertIsNotNone(
            evidence["field_errors"]["relative_max_abs_E_error"]
        )
        self.assertIsNotNone(
            evidence["field_errors"]["relative_max_abs_H_error"]
        )
        amplitudes = evidence["zero_order_complex_amplitudes"]
        self.assertEqual(amplitudes["status"], "ok")
        self.assertEqual(
            len(
                amplitudes["reflection_top"][
                    "numerical_outgoing_amplitude_at_boundary"
                ]
            ),
            2,
        )
        row = core.extract_pde_result(
            entry, summary, artifact_validation=evidence
        )
        self.assertTrue(row["physical_qualification_passed"])
        self.assertIsNotNone(row["physical_error_scalar"])
        self.assertIsNotNone(
            row["periodic_constraint"]["constraint_setup_outer_seconds"]
        )
        self.assertTrue(row["numerical_gates_passed"], row["gate_failures"])

    @staticmethod
    def _solver_summary(entry: dict) -> dict:
        fixture_a = entry["fixture"] == "fixture_a_air_box"
        summary = {
            "case_status": "completed",
            "official_result": True,
            "num_mesh_cells": 8,
            "num_nedelec_dofs": 100,
            "constrained_linear_system_size": 80,
            "matrix_stats": {"matrix_rows": 80, "matrix_nnz_used": 800},
            "floquet_num_constraints": 20,
            "floquet_raw_map_nnz": 20,
            "floquet_max_masters_per_slave": entry["degree"],
            "floquet_num_local_slaves": 20,
            "floquet_num_local_slave_records_seen": 20,
            "floquet_num_local_ghost_slave_constraints": 0,
            "floquet_num_global_ghost_slave_constraints": 0,
            "floquet_num_local_ghost_slave_records_skipped": 0,
            "floquet_num_global_ghost_slave_records_skipped": 0,
            "floquet_num_slave_edges": 4,
            "floquet_num_matched_master_edges": 4,
            "floquet_num_slave_faces": 2 if entry["degree"] > 1 else 0,
            "floquet_num_matched_master_faces": 2 if entry["degree"] > 1 else 0,
            "floquet_num_edge_constraints": 20,
            "floquet_num_face_constraints": 0,
            "floquet_num_x_constraints": 10,
            "floquet_num_y_constraints": 8,
            "floquet_num_corner_constraints": 2,
            "floquet_topology_cache_hit": False,
            "floquet_topology_build_seconds_current": 0.05,
            "floquet_phase_update_seconds": 0.01,
            "floquet_communication_bytes_sent_current": 100,
            "floquet_communication_bytes_received_current": 100,
            "floquet_constraint_timings_seconds": {"floquet_total": 0.08},
            "floquet_constraint_mode_resolved": (
                "topological_edges_p1"
                if entry["degree"] == 1
                else f"topological_trace_p{entry['degree']}"
            ),
            "linear_system_relative_residual": 1.0e-13,
            "floquet_x_face_mismatch": 1.0e-13,
            "floquet_y_face_mismatch": 1.0e-13,
            "floquet_edge_corner_mismatch": 0.0,
            "floquet_used_full_boundary_gather": False,
            "floquet_created_dense_boundary_square": False,
            "relative_max_abs_E_error": 1.0e-3 if fixture_a else None,
            "relative_max_abs_H_error": 2.0e-3 if fixture_a else None,
            "max_abs_E": 1.0,
            "max_abs_H": 0.9,
            "elapsed_seconds": 1.0,
            "max_rss_mb": 100.0,
            "total_peak_rss_mb": 100.0 * entry["mpi_size"],
            "timings_seconds": {
                "solve": 0.5,
                "floquet_constraint_setup_outer": 0.1,
            },
        }
        if not fixture_a:
            summary.update(
                {
                    "R_total": 0.2,
                    "T_total": 0.7,
                    "R_plus_T": 0.9,
                    "A_volume_total": 0.1,
                    "energy_closure_error_port_volume": None,
                    "power_consistency": {
                        "closure_error_port_volume": 0.0,
                        "R_port_minus_R_ref": 1.0e-4,
                        "T_port_minus_T_ref": -2.0e-4,
                        "A_volume_minus_A_ref": 1.0e-4,
                    },
                }
            )
        return summary

    @staticmethod
    def _artifact_validation() -> dict:
        return {
            "status": "completed",
            "method": "synthetic distributed rank-local VTU oracle",
            "field_errors": {
                "relative_max_abs_E_error": 1.0e-3,
                "relative_max_abs_H_error": 2.0e-3,
            },
            "zero_order_complex_amplitudes": {
                "status": "ok",
                "definition": "synthetic official zero-order DtN fixture",
                "source_files": ["port_power.json", "flat_layer_reference.json"],
                "reflection_top": {
                    "analytic_interface_amplitude": [0.2, 0.1],
                    "boundary_phase": [1.0, 0.0],
                    "analytic_boundary_amplitude": [0.2, 0.1],
                    "numerical_outgoing_amplitude_at_boundary": [0.203, 0.1],
                    "absolute_error": 3.0e-3,
                    "relative_error": 1.34e-2,
                    "phase_error_rad": 1.0e-2,
                },
                "transmission_bottom": {
                    "analytic_interface_amplitude": [0.8, -0.1],
                    "boundary_phase": [1.0, 0.0],
                    "analytic_boundary_amplitude": [0.8, -0.1],
                    "numerical_outgoing_amplitude_at_boundary": [0.804, -0.1],
                    "absolute_error": 4.0e-3,
                    "relative_error": 4.96e-3,
                    "phase_error_rad": 6.0e-4,
                },
            },
            "failures": [],
        }

    def test_solver_summary_projection_records_all_required_evidence(self) -> None:
        plan = core.build_shard_plan(1)
        fixture_a = next(
            item for item in plan if item["fixture"] == "fixture_a_air_box"
        )
        fixture_b = next(
            item for item in plan if item["fixture"] == "fixture_b_flat_air_si"
        )
        a_result = core.extract_pde_result(
            fixture_a, self._solver_summary(fixture_a)
        )
        b_result = core.extract_pde_result(
            fixture_b,
            self._solver_summary(fixture_b),
            artifact_validation=self._artifact_validation(),
        )
        self.assertTrue(a_result["numerical_gates_passed"])
        self.assertTrue(b_result["numerical_gates_passed"])
        self.assertEqual(a_result["discretization"]["matrix_nnz"], 800)
        self.assertEqual(b_result["power"]["port_volume_closure_error"], 0.0)
        self.assertEqual(b_result["fields"]["relative_max_abs_E_error"], 1.0e-3)
        self.assertIn("reflection_top", b_result["zero_order_complex_amplitudes"])
        self.assertEqual(b_result["periodic_constraint"]["global_constraint_nnz"], 20)
        self.assertIn("sum_rank_historical_peaks_mb_upper_bound", b_result["resources"])

    def test_each_shard_plan_has_exact_real_fixture_coverage(self) -> None:
        for mpi_size in core.MPI_SIZES:
            with self.subTest(mpi_size=mpi_size):
                plan = core.build_shard_plan(mpi_size)
                self.assertEqual(len(plan), 48)
                self.assertEqual(len({item["matrix_id"] for item in plan}), 48)
                fixture_a = [
                    item for item in plan if item["fixture"] == "fixture_a_air_box"
                ]
                fixture_b_primary = [
                    item
                    for item in plan
                    if item["fixture"] == "fixture_b_flat_air_si"
                    and item["grazing_deg_from_surface"] == 10.0
                ]
                fixture_b_smoke = [
                    item
                    for item in plan
                    if item["fixture"] == "fixture_b_flat_air_si"
                    and item["grazing_deg_from_surface"] in (1.0, 5.0)
                ]
                self.assertEqual(len(fixture_a), 16)
                self.assertEqual(len(fixture_b_primary), 16)
                self.assertEqual(len(fixture_b_smoke), 16)
                self.assertEqual(
                    {item["degree"] for item in plan}, {1, 2, 3, 4}
                )
                self.assertEqual(
                    {item["polarization"] for item in plan}, {"s", "p"}
                )

    def test_clean_exact_shards_aggregate_to_planner_compatible_core_pass(self) -> None:
        shards = [_shard(size) for size in core.MPI_SIZES]
        for shard in shards:
            self.assertEqual(core.validate_shard_record(shard), [])
            self.assertTrue(core.evidence_sha256_is_valid(shard))
        memories = [_memory_summary(size) for size in core.MPI_SIZES]
        aggregate = core.aggregate_core_records(shards, memories)
        self.assertTrue(aggregate["all_core_gates_passed"])
        self.assertTrue(core.evidence_sha256_is_valid(aggregate))
        self.assertEqual(len(aggregate["coverage"]), 12)
        planner = build_case090_record(core_gate_payload=aggregate)
        self.assertEqual(planner["core_gate"]["status"], "passed")

        try:
            from jsonschema import Draft202012Validator
        except ModuleNotFoundError:
            return
        schema = json.loads(
            (CASE_ROOT / "pde_core_schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(shards[0])
        Draft202012Validator(schema).validate(memories[0])
        Draft202012Validator(schema).validate(aggregate)

    def test_missing_dirty_or_tampered_shards_fail_closed(self) -> None:
        source = core.SourceIdentity("1" * 40, False)
        missing = core.build_shard_record(
            mpi_size=1,
            source_at_start=source,
            source_at_end=source,
            algebra_probes=[_probe(degree, 1) for degree in core.DEGREES],
            results=[_result(entry) for entry in core.build_shard_plan(1)[:-1]],
        )
        self.assertEqual(missing["status"], "failed")

        dirty = core.build_shard_record(
            mpi_size=1,
            source_at_start=core.SourceIdentity("1" * 40, True),
            source_at_end=source,
            algebra_probes=[_probe(degree, 1) for degree in core.DEGREES],
            results=[_result(entry) for entry in core.build_shard_plan(1)],
        )
        self.assertEqual(dirty["status"], "failed")

        tampered = _shard(1)
        tampered["pde_results"][0]["fields"][
            "relative_max_abs_E_error"
        ] = 9.0
        self.assertFalse(core.evidence_sha256_is_valid(tampered))
        self.assertIn("invalid shard evidence_sha256", core.validate_shard_record(tampered))

    def test_mpi_numerical_difference_gate_cannot_be_bypassed(self) -> None:
        shards = [_shard(size) for size in core.MPI_SIZES]
        changed = copy.deepcopy(shards[1])
        fixture_b = next(
            item
            for item in changed["pde_results"]
            if item["fixture"] == "fixture_b_flat_air_si"
        )
        fixture_b["power"]["R_total"] += 1.0e-6
        changed = core.attach_evidence_sha256(changed)
        aggregate = core.aggregate_core_records(
            [shards[0], changed, shards[2]],
            [_memory_summary(size) for size in core.MPI_SIZES],
        )
        self.assertFalse(aggregate["all_core_gates_passed"])
        mpi_gate = next(
            gate
            for gate in aggregate["gates"]
            if gate["name"] == "mpi_result_difference"
        )
        self.assertFalse(mpi_gate["passed"])
        planner = build_case090_record(core_gate_payload=aggregate)
        self.assertEqual(planner["core_gate"]["status"], "failed")

    def test_partition_dependent_constraint_sparsity_uses_strict_bounds(self) -> None:
        shards = [_shard(size) for size in core.MPI_SIZES]
        changed = copy.deepcopy(shards[1])
        p4_rows = [
            item for item in changed["pde_results"] if item["degree"] == 4
        ]
        self.assertTrue(p4_rows)
        for item in p4_rows:
            periodic = item["periodic_constraint"]
            rows = periodic["global_constraint_rows"]
            periodic["global_constraint_nnz"] = rows * 3
            periodic["max_masters_per_slave"] = 3
        changed = core.attach_evidence_sha256(changed)
        self.assertEqual(core.validate_shard_record(changed), [])
        aggregate = core.aggregate_core_records(
            [shards[0], changed, shards[2]],
            [_memory_summary(size) for size in core.MPI_SIZES],
        )
        self.assertTrue(aggregate["all_core_gates_passed"])
        mpi_gate = next(
            gate
            for gate in aggregate["gates"]
            if gate["name"] == "mpi_result_difference"
        )
        self.assertTrue(mpi_gate["passed"])

        invalid = copy.deepcopy(changed)
        invalid["pde_results"][0]["periodic_constraint"][
            "max_masters_per_slave"
        ] = invalid["pde_results"][0]["degree"] + 1
        invalid = core.attach_evidence_sha256(invalid)
        self.assertIn(
            "one or more shard periodic max-master bounds failed",
            core.validate_shard_record(invalid),
        )

    def test_production_runner_does_not_import_test_helpers(self) -> None:
        source = inspect.getsource(core) + inspect.getsource(
            run_task033_case090_pde_core
        )
        self.assertNotIn("src.test", source)
        self.assertIn("run_stage2a_floquet_airbox_3d_case", source)
        self.assertIn("run_stage4a_flat_layer_sanity_3d_case", source)
        self.assertIn("fem_petsc.assemble_matrix", source)
        self.assertIn("dolfinx_mpc.assemble_matrix", source)
        self.assertIn("prolongation.multHermitian", source)
        self.assertIn("C^H A_full C q", source)

    def test_missing_or_unqualified_watchdog_fails_closed(self) -> None:
        shards = [_shard(size) for size in core.MPI_SIZES]
        missing = core.aggregate_core_records(shards)
        self.assertFalse(missing["all_core_gates_passed"])
        memories = [_memory_summary(size) for size in core.MPI_SIZES]
        bad = copy.deepcopy(memories[2])
        bad["sampling"]["swap_current_delta_bytes"] = 2 * 1024**2
        bad["qualification"]["memory_summary_qualified"] = False
        bad["status"] = "failed"
        bad["failures"] = ["synthetic swap growth"]
        bad = core.attach_evidence_sha256(bad)
        aggregate = core.aggregate_core_records(shards, [*memories[:2], bad])
        self.assertFalse(aggregate["all_core_gates_passed"])

    def test_trend_analysis_preserves_no_p4_benefit_and_scopes_h_regression(self) -> None:
        rows = [_result(entry) for entry in core.build_shard_plan(1)]
        analysis, problems = core.analyze_accuracy_trends(rows)
        self.assertEqual(problems, [])
        self.assertTrue(analysis["negative_classifications"])
        self.assertTrue(
            all(
                item["classification"] == "negative_no_clear_p4_benefit"
                for item in analysis["negative_classifications"]
            )
        )
        hard_rows = [_result(entry) for entry in core.build_shard_plan(1)]
        fine = next(
            item
            for item in hard_rows
            if item["fixture"] == "fixture_a_air_box"
            and item["degree"] == 1
            and item["mesh_target_nm"] == 2.5
            and item["polarization"] == "s"
        )
        fine["physical_error_scalar"] = 1.0
        analysis, problems = core.analyze_accuracy_trends(hard_rows)
        p1_h_regression = next(
            item
            for item in analysis["h_refinement"]
            if item["fixture"] == "fixture_a_air_box"
            and item["degree"] == 1
            and item["polarization"] == "s"
        )
        self.assertEqual(
            p1_h_regression["classification"],
            "negative_h_refinement_regression",
        )
        self.assertEqual(p1_h_regression["gate_scope"], "hard_qualification")
        self.assertFalse(p1_h_regression["passed"])
        self.assertTrue(any("h5->h2.5" in problem for problem in problems))

        diagnostic_rows = [_result(entry) for entry in core.build_shard_plan(1)]
        diagnostic_fine = next(
            item
            for item in diagnostic_rows
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 10.0
            and item["degree"] == 1
            and item["mesh_target_nm"] == 2.5
            and item["polarization"] == "p"
        )
        diagnostic_fine["fields"]["relative_max_abs_H_error"] = 1.0
        diagnostic_fine["physical_error_scalar"] = 1.0
        analysis, problems = core.analyze_accuracy_trends(diagnostic_rows)
        self.assertEqual(problems, [])
        diagnostic_h_regression = next(
            item
            for item in analysis["h_refinement"]
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 10.0
            and item["degree"] == 1
            and item["polarization"] == "p"
        )
        self.assertEqual(
            diagnostic_h_regression["classification"],
            "negative_diagnostic_mesh_native_H_linf_sampling_regression",
        )
        self.assertEqual(
            diagnostic_h_regression["gate_scope"],
            "diagnostic_mesh_native_vtu_linf",
        )
        self.assertFalse(diagnostic_h_regression["passed"])
        self.assertIn(
            diagnostic_h_regression,
            analysis["negative_classifications"],
        )
        self.assertTrue(
            any("sampling diagnostic only" in warning for warning in analysis["warnings"])
        )

        wrong_oracle_rows = copy.deepcopy(diagnostic_rows)
        wrong_oracle_fine = next(
            item
            for item in wrong_oracle_rows
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 10.0
            and item["degree"] == 1
            and item["mesh_target_nm"] == 2.5
            and item["polarization"] == "p"
        )
        wrong_oracle_fine["artifact_validation"]["method"] = "fixed common probe oracle"
        analysis, problems = core.analyze_accuracy_trends(wrong_oracle_rows)
        wrong_oracle_h_regression = next(
            item
            for item in analysis["h_refinement"]
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 10.0
            and item["degree"] == 1
            and item["polarization"] == "p"
        )
        self.assertEqual(
            wrong_oracle_h_regression["classification"],
            "negative_h_refinement_regression",
        )
        self.assertTrue(any("h5->h2.5" in problem for problem in problems))

        p3_rows = [_result(entry) for entry in core.build_shard_plan(1)]
        p3_fine = next(
            item
            for item in p3_rows
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 10.0
            and item["degree"] == 3
            and item["mesh_target_nm"] == 2.5
            and item["polarization"] == "p"
        )
        p3_fine["fields"]["relative_max_abs_H_error"] = 1.0
        p3_fine["physical_error_scalar"] = 1.0
        analysis, problems = core.analyze_accuracy_trends(p3_rows)
        p3_h_regression = next(
            item
            for item in analysis["h_refinement"]
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["degree"] == 3
            and item["polarization"] == "p"
            and item["grazing_deg_from_surface"] == 10.0
        )
        self.assertEqual(p3_h_regression["gate_scope"], "hard_qualification")
        self.assertTrue(any("h5->h2.5" in problem for problem in problems))

        p_trend_rows = [_result(entry) for entry in core.build_shard_plan(1)]
        p3_smoke = next(
            item
            for item in p_trend_rows
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 1.0
            and item["degree"] == 3
            and item["polarization"] == "s"
        )
        p3_smoke["physical_error_scalar"] = 1.0
        analysis, problems = core.analyze_accuracy_trends(p_trend_rows)
        self.assertTrue(
            any("p3 physical error regressed" in problem for problem in problems)
        )
        p_trend = next(
            item
            for item in analysis["p_refinement"]
            if item["fixture"] == "fixture_b_flat_air_si"
            and item["grazing_deg_from_surface"] == 1.0
            and item["polarization"] == "s"
        )
        self.assertFalse(p_trend["p3_nonregression_passed"])
        self.assertEqual(p_trend["p3_classification"], "negative_p3_regression")
        self.assertEqual(p_trend["classification"], "negative_p3_regression")
        self.assertEqual(p_trend["p4_classification"], "positive_p4_benefit")


if __name__ == "__main__":
    unittest.main()
