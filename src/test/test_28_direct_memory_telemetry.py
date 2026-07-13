from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from petsc4py import PETSc

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
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
        self.assertIn("not inferred MUMPS", ratios["semantics"])

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
        args = _parse_args(["--h-nm", "5", "--profile", "mumps_ooc", "--mpi-size", "2"])
        self.assertEqual(args.h_nm, 5.0)
        self.assertEqual(args.profile, "mumps_ooc")
        self.assertEqual(args.mpi_size, 2)

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
