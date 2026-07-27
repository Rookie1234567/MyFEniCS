from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.run_task033_full3d_watchdog import (
    _factorization_stage_seen,
    _full3d_config,
    _parse_args,
    _qualify,
    _solve_stage_seen,
    _validate_p4_gate,
)


class Task033Full3DWatchdogTests(unittest.TestCase):
    def _args(self, *extra: str) -> argparse.Namespace:
        return _parse_args(["--degree", "3", *extra])

    def test_assembly_only_requires_no_factorization_and_no_swap(self) -> None:
        args = self._args()
        summary = {
            "case_status": "diagnostic_assemble_only",
            "matrix_diagnostics_assemble_only": True,
            "matrix_stats": {"matrix_rows": 10, "matrix_nnz_used": 20},
            "ksp_iterations": 0,
            "polarization_kind": "s",
        }
        result = _qualify(
            args=args,
            solver_summary=summary,
            events=[{"stage": "stage4_dtn_augmented_matrix_finalized"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=4,
        )
        self.assertTrue(result["pass"])
        for events, no_swap in (
            ([{"stage": "after_ksp_setup_factorized"}], True),
            ([], False),
        ):
            with self.subTest(events=events, no_swap=no_swap):
                failed = _qualify(
                    args=args,
                    solver_summary=summary,
                    events=events,
                    return_code=0,
                    terminated_for_memory=False,
                    terminated_for_timeout=False,
                    terminated_for_authority_unreadable=False,
                    no_swap=no_swap,
                    observed_worker_rank_count=4,
                )
                self.assertFalse(failed["pass"])

    def test_full_solve_requires_residual_and_reference_export(self) -> None:
        args = self._args("--run-kind", "full-solve", "--allow-swap")
        summary = {
            "case_status": "completed",
            "official_result": True,
            "matrix_diagnostics_assemble_only": False,
            "matrix_diagnostics_factorization_only": False,
            "matrix_stats": {"matrix_rows": 10, "matrix_nnz_used": 20},
            "ksp_converged": True,
            "linear_system_relative_residual": 1.0e-12,
            "full3d_reference_exported": True,
            "polarization_kind": "s",
        }
        result = _qualify(
            args=args,
            solver_summary=summary,
            events=[{"stage": "after_kspsolve"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=False,
            observed_worker_rank_count=4,
        )
        self.assertTrue(result["pass"])
        for invalid_residual in (-1.0, float("-inf"), False):
            with self.subTest(invalid_residual=invalid_residual):
                summary["linear_system_relative_residual"] = invalid_residual
                rejected = _qualify(
                    args=args,
                    solver_summary=summary,
                    events=[{"stage": "after_kspsolve"}],
                    return_code=0,
                    terminated_for_memory=False,
                    terminated_for_timeout=False,
                    terminated_for_authority_unreadable=False,
                    no_swap=False,
                    observed_worker_rank_count=4,
                )
                self.assertFalse(rejected["pass"])
        summary["linear_system_relative_residual"] = 1.0e-12
        summary["full3d_reference_exported"] = False
        result = _qualify(
            args=args,
            solver_summary=summary,
            events=[],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=False,
            observed_worker_rank_count=4,
        )
        self.assertFalse(result["pass"])

    def test_factorization_only_requires_setup_but_no_solve(self) -> None:
        args = self._args("--run-kind", "factorization-only")
        summary = {
            "case_status": "diagnostic_factorization_only",
            "official_result": False,
            "matrix_diagnostics_assemble_only": False,
            "matrix_diagnostics_factorization_only": True,
            "matrix_stats": {"matrix_rows": 10, "matrix_nnz_used": 20},
            "ksp_iterations": 0,
            "stage4_dtn_factor_inventory": {"factor_solver_type": "mumps"},
            "polarization_kind": "s",
        }
        events = [
            {"stage": "before_ksp_setup"},
            {"stage": "after_ksp_setup_factorized"},
        ]
        result = _qualify(
            args=args,
            solver_summary=summary,
            events=events,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=4,
        )
        self.assertTrue(result["pass"])
        result = _qualify(
            args=args,
            solver_summary=summary,
            events=[*events, {"stage": "before_ksp_solve"}],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=4,
        )
        self.assertFalse(result["pass"])

    def test_p4_requires_p3_zero_swap_below_10_gib(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p3.json"
            trace_path = Path(directory) / "p4_trace.json"
            source_sha = "a" * 40
            record = {
                "degree": 3,
                "h_nm": 5.0,
                "run_kind": "full-solve",
                "status": "full3d_reference_pass",
                "no_swap": True,
                "resource_authority": {"memory_authority_gib": 9.9},
            }
            path.write_text(json.dumps(record), encoding="utf-8")
            trace_path.write_text(
                json.dumps(
                    {
                        "record_type": ("p4_four_mode_matched_trace_aggregate"),
                        "status": "p4_four_mode_matched_trace_pass",
                        "source_commit_sha": source_sha,
                        "gates": {
                            "p4_four_mode_matched_trace": True,
                            "mpi1_mpi4_compact_identity": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = _parse_args(
                [
                    "--degree",
                    "4",
                    "--p3-gate-record",
                    str(path),
                    "--p4-trace-record",
                    str(trace_path),
                    "--verified-clean-sha",
                    source_sha,
                ]
            )
            self.assertTrue(_validate_p4_gate(args)["pass"])
            record["resource_authority"]["memory_authority_gib"] = 10.0
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(SystemExit):
                _validate_p4_gate(args)

    def test_task034_p4_h3_uses_live_warning_without_relaxing_task033(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p3_h3.json"
            trace_path = Path(directory) / "p4_trace.json"
            source_sha = "b" * 40
            path.write_text(
                json.dumps(
                    {
                        "degree": 3,
                        "h_nm": 3.0,
                        "run_kind": "full-solve",
                        "status": "full3d_reference_pass",
                        "no_swap": True,
                        "resource_authority": {"memory_authority_gib": 44.0},
                    }
                ),
                encoding="utf-8",
            )
            trace_path.write_text(
                json.dumps(
                    {
                        "record_type": "p4_four_mode_matched_trace_aggregate",
                        "status": "p4_four_mode_matched_trace_pass",
                        "source_commit_sha": source_sha,
                        "gates": {
                            "p4_four_mode_matched_trace": True,
                            "mpi1_mpi4_compact_identity": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            legacy = _parse_args(
                [
                    "--degree",
                    "4",
                    "--h-nm",
                    "3",
                    "--p3-gate-record",
                    str(path),
                    "--p4-trace-record",
                    str(trace_path),
                    "--verified-clean-sha",
                    source_sha,
                    "--warning-gib",
                    "155",
                ]
            )
            with self.assertRaises(SystemExit):
                _validate_p4_gate(legacy)
            workstation = _parse_args(
                [
                    "--degree",
                    "4",
                    "--h-nm",
                    "3",
                    "--p3-gate-record",
                    str(path),
                    "--p4-trace-record",
                    str(trace_path),
                    "--verified-clean-sha",
                    source_sha,
                    "--warning-gib",
                    "155",
                    "--task034-p4-h3-added-point",
                ]
            )
            gate = _validate_p4_gate(workstation)
            self.assertTrue(gate["pass"])
            self.assertTrue(gate["task034_p4_h3_added_point"])
            self.assertEqual(gate["p3_memory_threshold_gib"], 155.0)
            with self.assertRaises(SystemExit):
                _parse_args(
                    ["--degree", "4", "--h-nm", "5", "--task034-p4-h3-added-point"]
                )

    def test_factorization_stage_detection_is_fail_closed(self) -> None:
        self.assertFalse(
            _factorization_stage_seen(
                [{"stage": "stage4_dtn_augmented_matrix_finalized"}]
            )
        )
        for stage in (
            "before_ksp_setup",
            "after_ksp_setup_factorized",
            "before_ksp_solve",
            "after_ksp_solve",
        ):
            with self.subTest(stage=stage):
                self.assertTrue(_factorization_stage_seen([{"stage": stage}]))

    def test_solve_stage_detection_is_fail_closed(self) -> None:
        self.assertFalse(_solve_stage_seen([{"stage": "after_ksp_setup_factorized"}]))
        for stage in (
            "stage4_dtn_augmented_solve",
            "before_ksp_solve",
            "during_ksp_solve_peak",
            "after_ksp_solve",
        ):
            with self.subTest(stage=stage):
                self.assertTrue(_solve_stage_seen([{"stage": stage}]))

    def test_review_v5_coarse_p3_meshes_are_parser_qualified(self) -> None:
        for h_nm in ("10", "7.5"):
            with self.subTest(h_nm=h_nm):
                args = self._args("--h-nm", h_nm)
                self.assertEqual(args.degree, 3)
                self.assertEqual(args.h_nm, float(h_nm))

    def test_task034_requested_finer_candidates_are_opt_in(self) -> None:
        args = self._args("--h-nm", "3")
        self.assertEqual(args.degree, 3)
        self.assertEqual(args.h_nm, 3.0)
        for degree, h_nm in ((2, "1"), (3, "2"), (4, "3")):
            with self.subTest(degree=degree, h_nm=h_nm):
                parsed = _parse_args(["--degree", str(degree), "--h-nm", h_nm])
                self.assertEqual(parsed.h_nm, float(h_nm))

    def test_explicit_p_polarization_reaches_full3d_config(self) -> None:
        args = self._args("--polarization-kind", "p")
        self.assertEqual(args.polarization_kind, "p")
        cfg = _full3d_config(args)
        self.assertEqual(cfg.polarization_kind, "p")
        self.assertIsNone(cfg.custom_polarization)

        summary = {
            "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": 1},
            "polarization_kind": "s",
        }
        result = _qualify(
            args=args,
            solver_summary=summary,
            events=[],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=4,
        )
        self.assertIn("polarization_identity", result["failures"])

    def test_task034_fixed_geometry_candidate_matrix(self) -> None:
        allowed = {
            2: ("5", "3", "2", "1"),
            3: ("10", "7.5", "5", "3", "2"),
            4: ("10", "7.5", "5", "3"),
        }
        for degree, h_values in allowed.items():
            for h_nm in h_values:
                with self.subTest(degree=degree, h_nm=h_nm):
                    args = _parse_args(["--degree", str(degree), "--h-nm", h_nm])
                    self.assertEqual(args.degree, degree)
                    self.assertEqual(args.h_nm, float(h_nm))
        for degree, h_nm in ((2, "10"), (3, "1"), (4, "2"), (4, "1")):
            with self.subTest(rejected_degree=degree, rejected_h_nm=h_nm):
                with self.assertRaises(SystemExit):
                    _parse_args(["--degree", str(degree), "--h-nm", h_nm])


if __name__ == "__main__":
    unittest.main()
