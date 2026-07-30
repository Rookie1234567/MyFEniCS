from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _cpu_affinity_count,
    _directory_usage,
    _enrich_factor_inventory,
    _historical_peak_upper_bound,
    _latest_stage,
    _numeric_gate,
    _parse_args,
    _sample,
    _source_provenance,
    _task29_direct_config,
    _two_point_power_law_prediction,
    _validate_h2_gate,
)
from src.solvers.common_3d_solve import (
    DirectSolveFailure,
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)
from src.solvers.common_3d_utils import (
    _cgroup_memory_fields,
    _current_rss_mb,
)
from src.solvers.dtn_port_3d import _solve_augmented_system


class DirectMemoryTelemetryTests(unittest.TestCase):
    def test_historical_peak_upper_bound_uses_all_complete_checkpoints(self) -> None:
        events = [
            {"sum_rank_historical_peaks_mb_upper_bound": 10.0},
            {"sum_rank_historical_peaks_mb_upper_bound": 12.5},
        ]
        summary = {
            "sum_rank_historical_peaks_mb_upper_bound": 11.0,
            "total_peak_rss_mb": 9.0,
        }
        self.assertEqual(_historical_peak_upper_bound(events, summary), 12.5)

    def test_factor_inventory_records_only_algebraic_derived_ratios(self) -> None:
        inventory = {
            "matrix_stats": {
                "matrix_nnz_used": 60.0,
                "matrix_memory_estimate_mb": 24.0,
            }
        }
        augmented = {
            "matrix_nnz_used": 10.0,
            "matrix_memory_estimate_mb": 4.0,
        }
        enriched = _enrich_factor_inventory(inventory, augmented)
        self.assertIsNotNone(enriched)
        ratios = enriched["derived_ratios"]
        self.assertEqual(ratios["factor_to_augmented_nnz_ratio"], 6.0)
        self.assertEqual(ratios["factor_to_augmented_estimated_storage_ratio"], 6.0)
        self.assertEqual(
            ratios["factor_nnz_source"],
            "petsc_factor_matrix_nnz_used_raw",
        )
        self.assertEqual(
            ratios["factor_estimated_storage_source"],
            "petsc_factor_matrix_estimate_raw",
        )
        self.assertIn("otherwise PETSc-reported nnz", ratios["semantics"])

    def test_worker_forces_full_solve_not_assemble_only(self) -> None:
        args = _parse_args(["--h-nm", "5", "--profile", "default"])
        cfg = _task29_direct_config(args)
        self.assertFalse(cfg.matrix_diagnostics_assemble_only)
        self.assertEqual(cfg.stage_case, "stage4_block_grating")
        self.assertEqual(cfg.stage4_dtn_order_policy, "auto_propagating")

    def test_release_base_candidate_is_explicit_opt_in(self) -> None:
        ordinary = _task29_direct_config(_parse_args(["--h-nm", "5"]))
        candidate = _task29_direct_config(
            _parse_args(["--h-nm", "5", "--release-base-after-augmentation"])
        )
        self.assertFalse(ordinary.direct_release_base_after_augmentation)
        self.assertFalse(
            ordinary.stage4_assembly_time_cell_static_condensation
        )
        self.assertFalse(
            ordinary.direct_release_solver_before_postprocess
        )
        self.assertTrue(candidate.direct_release_base_after_augmentation)

    def test_ooc_scratch_usage_is_measured_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mumps_ooc_files"
            nested = root / "rank0"
            nested.mkdir(parents=True)
            (root / "a.bin").write_bytes(b"123")
            (nested / "b.bin").write_bytes(b"45678")
            self.assertEqual(_directory_usage(root), (2, 8))

    def test_direct_solve_failure_cleanup_is_idempotent(self) -> None:
        class FakePetscObject:
            def __init__(self) -> None:
                self.handle = 1
                self.destroy_count = 0

            def destroy(self) -> None:
                self.destroy_count += 1
                self.handle = 0

        objects = [FakePetscObject() for _ in range(4)]
        failure = DirectSolveFailure(
            "diagnostic",
            failure_stage="unit_test",
            petsc_error=RuntimeError("unit_test"),
            A=objects[0],
            b=objects[1],
            x=objects[2],
            ksp=objects[3],
        )
        failure.cleanup()
        failure.cleanup()
        self.assertEqual([obj.destroy_count for obj in objects], [1, 1, 1, 1])
        self.assertIsNone(failure.A)
        self.assertIsNone(failure.ksp)

    def test_memory_snapshot_schema(self) -> None:
        self.assertIsNotNone(_current_rss_mb())
        cgroup = _cgroup_memory_fields()
        self.assertIn("container_cgroup_current_mb", cgroup)
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "progress.jsonl"
            row = _sample(os.getpid(), progress, 0.0)
        self.assertEqual(set(TIMELINE_FIELDS), set(row))
        self.assertEqual(row["stage"], "process_start")
        self.assertGreaterEqual(float(row["container_process_rss_sum_mb"]), 0.0)

    def test_worker_memory_is_scoped_to_the_sampled_process_tree(self) -> None:
        def process(
            pid: int,
            ppid: int,
            *,
            rank: int | None,
            rss_mb: float,
        ) -> dict:
            return {
                "pid": pid,
                "ppid": ppid,
                "rss_mb": rss_mb,
                "swap_mb": 0.0,
                "cpu_affinity": "0",
                "thread_count": 1,
                "cpu_seconds": 0.0,
                "cmdline": "",
                "worker_rank": rank,
                "smaps_rollup": None
                if rank is None
                else {
                    "rss_mb": rss_mb,
                    "pss_mb": rss_mb - 1.0,
                    "uss_mb": rss_mb - 2.0,
                    "shared_mb": 2.0,
                    "anonymous_mb": rss_mb - 3.0,
                    "swap_mb": 0.0,
                    "swap_pss_mb": 0.0,
                },
                "thread_runtime": None,
                "read_bytes": 0,
                "write_bytes": 0,
                "blkio_delay_seconds": 0.0,
            }

        processes = {
            10: process(10, 0, rank=None, rss_mb=5.0),
            11: process(11, 10, rank=0, rss_mb=100.0),
            20: process(20, 0, rank=None, rss_mb=6.0),
            21: process(21, 20, rank=1, rss_mb=900.0),
        }
        with tempfile.TemporaryDirectory() as tmp, patch(
            "benchmarks.run_direct_memory_forensics._read_processes",
            return_value=processes,
        ), patch(
            "benchmarks.run_direct_memory_forensics._vmstat_swap_pages",
            return_value=(0, 0),
        ), patch(
            "benchmarks.run_direct_memory_forensics._cgroup_snapshot",
            return_value={
                "container_cgroup_current_mb": 111.0,
                "container_cgroup_peak_mb": 112.0,
                "container_swap_current_mb": 0.0,
                "job_cgroup_path": "/test",
                "job_cgroup_dedicated": True,
            },
        ):
            row = _sample(10, Path(tmp) / "progress.jsonl", 0.0)

        workers = json.loads(row["worker_rank_rss_mb_json"])
        self.assertEqual([worker["rank"] for worker in workers], [0])
        self.assertEqual(row["worker_rank_rss_sum_mb"], 100.0)
        self.assertEqual(row["worker_rank_pss_sum_mb"], 99.0)
        self.assertEqual(row["mpi_process_tree_rss_mb"], 105.0)
        self.assertEqual(row["container_process_rss_sum_mb"], 1011.0)

    def test_stage_marker_reads_last_complete_json_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.jsonl"
            path.write_text(
                '{"stage":"after_mesh","status":"end"}\n{"stage":"before_ksp_setup","status":"begin"}\n{partial',
                encoding="utf-8",
            )
            self.assertEqual(_latest_stage(path), ("before_ksp_setup", "begin"))

    def test_matrix_info_is_json_serializable(self) -> None:
        matrix = PETSc.Mat().createAIJ([3, 3], nnz=1, comm=PETSc.COMM_SELF)
        try:
            for index in range(3):
                matrix.setValue(index, index, 2.0)
            matrix.assemble()
            stats = _petsc_matrix_stats(matrix)
            json.dumps(stats)
            self.assertEqual(stats["matrix_rows"], 3)
            self.assertEqual(stats["matrix_cols"], 3)
            self.assertEqual(stats["matrix_row_ownership_range"], [0, 3])
            self.assertIn("matrix_nnz_unneeded", stats)
            self.assertIn("matrix_mallocs", stats)
            self.assertIn("matrix_petsc_info_global_sum", stats)
        finally:
            matrix.destroy()


    def test_factorization_only_stops_after_ksp_setup(self) -> None:
        matrix = PETSc.Mat().createAIJ([2, 2], nnz=1, comm=PETSc.COMM_SELF)
        diagonal = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
        rhs = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
        x = None
        ksp = None
        try:
            diagonal.set(2.0)
            rhs.set(1.0)
            matrix.setDiagonal(diagonal)
            matrix.assemble()
            with tempfile.TemporaryDirectory() as tmp:
                x, ksp, telemetry = _solve_augmented_system(
                    matrix,
                    rhs,
                    {"ksp_type": "preonly", "pc_type": "lu"},
                    "task034_factorization_gate_test_",
                    out_dir=Path(tmp),
                    comm=MPI.COMM_SELF,
                    dofs=2,
                    constraints=0,
                    factorization_only=True,
                )
                events = [
                    json.loads(line)
                    for line in (Path(tmp) / "progress_3d.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
            stages = {event["stage"] for event in events}
            self.assertTrue(telemetry["factorization_only"])
            self.assertIsInstance(telemetry["factor_inventory"], dict)
            self.assertEqual(x.norm(), 0.0)
            self.assertIn("after_ksp_setup_factorized", stages)
            self.assertFalse(
                stages
                & {
                    "stage4_dtn_augmented_solve",
                    "before_ksp_solve",
                    "during_ksp_solve_peak",
                    "after_ksp_solve",
                }
            )
        finally:
            if ksp is not None:
                ksp.destroy()
            if x is not None:
                x.destroy()
            rhs.destroy()
            diagonal.destroy()
            matrix.destroy()

    def test_factor_inventory_does_not_reassemble_factored_matrix(self) -> None:
        matrix = PETSc.Mat().createAIJ([3, 3], nnz=1, comm=PETSc.COMM_SELF)
        diagonal = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
        ksp = PETSc.KSP().create(PETSc.COMM_SELF)
        try:
            diagonal.set(1.0)
            matrix.setDiagonal(diagonal)
            matrix.assemble()
            ksp.setType("preonly")
            ksp.getPC().setType("lu")
            ksp.setOperators(matrix)
            ksp.setUp()
            inventory = _petsc_factor_inventory(ksp)
            self.assertTrue(inventory["available"])
            self.assertEqual(inventory["matrix_stats"]["matrix_rows"], 3)
            self.assertEqual(
                inventory["matrix_stats"]["matrix_petsc_info"]["fill_ratio_needed"],
                1.0,
            )
            self.assertFalse(inventory["mumps_api_available"])
        finally:
            ksp.destroy()
            diagonal.destroy()
            matrix.destroy()

    def test_candidate_profile_parser(self) -> None:
        args = _parse_args(
            [
                "--h-nm",
                "5",
                "--profile",
                "mumps_ooc",
                "--mpi-size",
                "2",
                "--threads-per-rank",
                "2",
                "--cpu-affinity",
                "0-3",
            ]
        )
        self.assertEqual(args.h_nm, 5.0)
        self.assertEqual(args.profile, "mumps_ooc")
        self.assertEqual(args.mpi_size, 2)
        self.assertEqual(args.threads_per_rank, 2)
        self.assertEqual(args.cpu_affinity, "0-3")

    def test_cpu_core_equivalents_use_cumulative_proc_cpu_time(self) -> None:
        previous = {
            "elapsed_seconds": 1.0,
            "worker_rank_cpu_seconds": 2.0,
            "mpi_process_tree_cpu_seconds": 2.5,
        }
        current = {
            "elapsed_seconds": 1.5,
            "worker_rank_cpu_seconds": 3.5,
            "mpi_process_tree_cpu_seconds": 4.5,
            "worker_rank_cpu_core_equivalents": 0.0,
            "mpi_process_tree_cpu_core_equivalents": 0.0,
        }
        _add_cpu_core_equivalents(current, previous)
        self.assertAlmostEqual(current["worker_rank_cpu_core_equivalents"], 3.0)
        self.assertAlmostEqual(current["mpi_process_tree_cpu_core_equivalents"], 4.0)

    def test_cpu_affinity_count_understands_ranges_and_lists(self) -> None:
        self.assertEqual(_cpu_affinity_count("0-3"), 4)
        self.assertEqual(_cpu_affinity_count("0-1,4,6-7"), 5)
        self.assertIsNone(_cpu_affinity_count("3-1"))
        self.assertIsNone(_cpu_affinity_count("not-a-cpu-list"))

    def test_selected_candidate_record_contract(self) -> None:
        records = (
            "h5_mpi2_candidate.json",
            "h3_mpi2_candidate.json",
        )
        root = (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "cases"
            / "050_stage4_direct_memory_forensics"
            / "records"
        )
        required = {
            "benchmark_id",
            "status",
            "metadata",
            "physical_model",
            "resolved_config",
            "dimensions",
            "matrix_inventory",
            "factor_inventory",
            "memory_checkpoints",
            "memory",
            "timings_seconds",
            "qualification",
            "limitations",
        }
        for name in records:
            with self.subTest(record=name):
                record = json.loads((root / name).read_text(encoding="utf-8"))
                self.assertTrue(required.issubset(record))
                self.assertEqual(record["status"], "pass")
                self.assertFalse(record["metadata"]["tracked_source_dirty"])
                self.assertTrue(record["qualification"]["full_solve"])
                self.assertEqual(record["qualification"]["numeric_gate"], "pass")
        h5 = json.loads((root / records[0]).read_text(encoding="utf-8"))
        h3 = json.loads((root / records[1]).read_text(encoding="utf-8"))
        self.assertEqual(
            h5["qualification"]["memory_reduction_20pct_gate"], "pass"
        )
        self.assertEqual(
            h3["qualification"]["memory_reduction_20pct_gate"], "failed"
        )

    def test_task29_required_outcomes_contract(self) -> None:
        root = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "task029_stage4_direct_memory_forensics"
            / "outcomes"
        )
        required = (
            "README.md",
            "summary.md",
            "parameters.json",
            "environment.json",
            "changed_files.md",
            "run_log.txt",
            "test_summary.md",
            "gate_decision.csv",
            "merge_recommendation.md",
            "next_decision.md",
            "baseline_memory_timeline.csv",
            "baseline_matrix_inventory.csv",
            "baseline_factorization_summary.csv",
            "rank_scaling.csv",
            "optimization_hypotheses.csv",
            "optimization_manifest.csv",
            "candidate_comparison.csv",
            "object_lifecycle.md",
            "h2_memory_prediction.md",
            "h2_launch_decision.md",
            "comsol_reference_comparability.md",
        )
        for name in required:
            with self.subTest(outcome=name):
                self.assertTrue((root / name).is_file())
        for name in ("parameters.json", "environment.json"):
            json.loads((root / name).read_text(encoding="utf-8"))
        for name in (
            "gate_decision.csv",
            "optimization_hypotheses.csv",
            "optimization_manifest.csv",
            "candidate_comparison.csv",
        ):
            with (root / name).open(encoding="utf-8", newline="") as stream:
                self.assertGreater(len(list(csv.DictReader(stream))), 0)

    def test_numeric_gate_uses_task28_reference(self) -> None:
        reference = {
            "R_total": 0.1,
            "T_total": 0.4,
            "A_volume_total": 0.5,
        }
        summary = {
            **reference,
            "linear_system_relative_residual": 1.0e-12,
            "energy_closure_error_port_volume": 2.0e-12,
        }
        gate = _numeric_gate(summary, reference, 0)
        self.assertEqual(gate["status"], "pass")
        summary["T_total"] = 0.4001
        self.assertEqual(_numeric_gate(summary, reference, 0)["status"], "failed")

    def test_host_clean_sha_attestation_must_match_mounted_head(self) -> None:
        sha = "a" * 40
        args = _parse_args(["--h-nm", "5", "--verified-clean-sha", sha])
        with patch("benchmarks.run_direct_memory_forensics._git", return_value=sha):
            provenance = _source_provenance(args)
        self.assertFalse(provenance["tracked_source_dirty"])
        self.assertEqual(
            provenance["tracked_source_verification"],
            "host_git_clean_attestation",
        )

        args.verified_clean_sha = "b" * 40
        with patch("benchmarks.run_direct_memory_forensics._git", return_value=sha):
            with self.assertRaises(SystemExit):
                _source_provenance(args)

    def test_h2_is_blocked_without_passing_gate_record(self) -> None:
        args = _parse_args(["--h-nm", "2"])
        with self.assertRaises(SystemExit):
            _validate_h2_gate(args)

    def test_h2_gate_requires_every_safety_field(self) -> None:
        required = {
            "h5_numeric_pass": True,
            "h3_numeric_pass": True,
            "h5_memory_reduction_20pct": True,
            "h3_memory_reduction_20pct": True,
            "h3_no_swap": True,
            "prediction_upper_le_13p5_gb": True,
            "current_memory_margin_pass": True,
            "single_qualified_profile": True,
            "watchdog_enabled": True,
            "task28_h2_record_untouched": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.json"
            path.write_text(json.dumps(required), encoding="utf-8")
            args = _parse_args(["--h-nm", "2", "--h2-gate-json", str(path)])
            _validate_h2_gate(args)
            required["h3_no_swap"] = False
            path.write_text(json.dumps(required), encoding="utf-8")
            with self.assertRaises(SystemExit):
                _validate_h2_gate(args)

    def test_two_point_power_law_memory_prediction(self) -> None:
        result = _two_point_power_law_prediction(1.0, 10.0, 2.0, 20.0, 4.0)
        self.assertAlmostEqual(result["exponent"], 1.0)
        self.assertAlmostEqual(result["prediction"], 40.0)
        with self.assertRaises(ValueError):
            _two_point_power_law_prediction(1.0, 10.0, 1.0, 20.0, 4.0)


if __name__ == "__main__":
    unittest.main()
