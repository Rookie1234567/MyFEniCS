from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from petsc4py import PETSc

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _latest_stage,
    _numeric_gate,
    _parse_args,
    _sample,
    _source_provenance,
    _task29_direct_config,
    _validate_h2_gate,
)
from src.solvers.common_3d_solve import _petsc_matrix_stats
from src.solvers.common_3d_utils import (
    _cgroup_memory_fields,
    _current_rss_mb,
)


class DirectMemoryTelemetryTests(unittest.TestCase):
    def test_worker_forces_full_solve_not_assemble_only(self) -> None:
        args = _parse_args(["--h-nm", "5", "--profile", "default"])
        cfg = _task29_direct_config(args)
        self.assertFalse(cfg.matrix_diagnostics_assemble_only)
        self.assertEqual(cfg.stage_case, "stage4_block_grating")
        self.assertEqual(cfg.stage4_dtn_order_policy, "auto_propagating")

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

    def test_candidate_profile_parser(self) -> None:
        args = _parse_args(["--h-nm", "5", "--profile", "mumps_ooc", "--mpi-size", "2"])
        self.assertEqual(args.h_nm, 5.0)
        self.assertEqual(args.profile, "mumps_ooc")
        self.assertEqual(args.mpi_size, 2)

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
            "watchdog_enabled": True,
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


if __name__ == "__main__":
    unittest.main()
