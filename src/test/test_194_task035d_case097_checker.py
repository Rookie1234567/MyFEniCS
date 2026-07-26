from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.run_direct_memory_forensics import TIMELINE_FIELDS
from benchmarks.task035d_case097_checker import (
    MANDATORY_PEAK_GIB,
    STATIC_P6_FACTOR_NNZ,
    STATIC_P6_MATRIX_NNZ,
    Task035dEvidenceError,
    _control_field_directories,
    _energy_comparison,
    _load_frozen_authorities,
    _resource_comparison,
    _timeline_resource_metrics,
    evaluate_task035d_case097_candidate,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_T30_ACTIVE_FE_DOFS,
    TASK035D_T30_SOLVE_ROWS,
)


def _timeline_row(*, process_rss_mb: float = 512.0) -> dict[str, object]:
    smaps = [
        {
            "rank": rank,
            "pid": 1000 + rank,
            "rss_mb": 40.0 + rank,
            "pss_mb": 35.0 + rank,
            "uss_mb": 30.0 + rank,
            "shared_mb": 10.0,
            "anonymous_mb": 25.0 + rank,
            "swap_mb": 0.0,
            "swap_pss_mb": 0.0,
        }
        for rank in range(8)
    ]
    workers = [
        {
            "rank": item["rank"],
            "pid": item["pid"],
            "rss_mb": item["rss_mb"],
        }
        for item in smaps
    ]
    return {
        "timestamp_utc": "2026-07-26T00:00:00+00:00",
        "elapsed_seconds": 1.0,
        "stage": "during_ksp_setup_peak",
        "stage_status": "running",
        "worker_rank_rss_sum_mb": sum(item["rss_mb"] for item in smaps),
        "worker_rank_pss_sum_mb": sum(item["pss_mb"] for item in smaps),
        "worker_rank_uss_sum_mb": sum(item["uss_mb"] for item in smaps),
        "worker_rank_shared_sum_mb": sum(
            item["shared_mb"] for item in smaps
        ),
        "worker_rank_smaps_swap_sum_mb": 0.0,
        "mpi_process_tree_rss_mb": process_rss_mb,
        "mpi_process_tree_swap_mb": 0.0,
        "container_process_rss_sum_mb": process_rss_mb,
        "worker_rank_rss_mb_json": json.dumps(workers),
        "worker_rank_smaps_rollup_json": json.dumps(smaps),
        "worker_rank_smaps_readable_count": 8,
        "worker_rank_cpu_affinity_json": "[]",
        "worker_rank_thread_count_sum": 8,
        "worker_rank_thread_runtime_json": "[]",
        "mpi_process_tree_thread_count": 9,
        "worker_rank_cpu_seconds": 8.0,
        "mpi_process_tree_cpu_seconds": 8.0,
        "worker_rank_cpu_core_equivalents": 8.0,
        "mpi_process_tree_cpu_core_equivalents": 8.0,
        "container_cgroup_current_mb": 1024.0,
        "container_cgroup_peak_mb": 2048.0,
        "container_swap_current_mb": 0.0,
        "job_cgroup_path": "/init.scope",
        "job_cgroup_dedicated": False,
        "wsl_pswpin_pages": 0,
        "wsl_pswpout_pages": 0,
        "ooc_scratch_file_count": 0,
        "ooc_scratch_bytes": 0,
        "mpi_process_tree_read_bytes": 0,
        "mpi_process_tree_write_bytes": 0,
        "mpi_process_tree_blkio_delay_seconds": 0.0,
    }


def _write_timeline(path: Path, row: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerow(row)


def _solver_summary() -> dict:
    return {
        "num_actual_conforming_active_fe_dofs": (
            TASK035D_T30_ACTIVE_FE_DOFS
        ),
        "matrix_stats": {
            "matrix_rows": TASK035D_T30_SOLVE_ROWS,
            "matrix_nnz_used": STATIC_P6_MATRIX_NNZ - 1,
        },
        "stage4_dtn_factor_inventory": {
            "matrix_stats": {
                "matrix_nnz_used": STATIC_P6_FACTOR_NNZ - 1,
            }
        },
    }


def _pass_payload() -> dict:
    return {"pass": True}


class Task035dCase097CheckerTests(unittest.TestCase):
    def test_frozen_control_field_shards_remain_hash_bound(self) -> None:
        authorities = _load_frozen_authorities()
        p5_dir, p6_dir, observed = _control_field_directories(authorities)
        self.assertTrue(p5_dir.is_dir())
        self.assertTrue(p6_dir.is_dir())
        self.assertEqual(len(observed["global_p5_control"]), 8)
        self.assertEqual(len(observed["global_p6_reference"]), 8)

    def test_timeline_recomputes_mpi8_pss_uss_and_cgroup_diagnostic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timeline.csv"
            row = _timeline_row()
            _write_timeline(path, row)
            metrics = _timeline_resource_metrics(path)
            self.assertEqual(metrics["max_observed_worker_rank_count"], 8)
            self.assertEqual(
                metrics["fully_readable_mpi8_smaps_sample_count"],
                1,
            )
            self.assertEqual(
                metrics["max_container_cgroup_current_observed_mb"],
                1024.0,
            )
            self.assertFalse(metrics["dedicated_job_cgroup_observed"])
            self.assertEqual(metrics["memory_authority_gib"], 0.5)
            self.assertTrue(metrics["zero_swap"])
            self.assertEqual(
                metrics["per_rank_smaps_rollup_peak_mb"]["7"]["uss_mb"],
                37.0,
            )

            tampered = dict(row)
            tampered["worker_rank_pss_sum_mb"] = 1.0
            _write_timeline(path, tampered)
            with self.assertRaises(Task035dEvidenceError):
                _timeline_resource_metrics(path)

    def test_energy_and_resource_gates_are_independently_recomputed(
        self,
    ) -> None:
        candidate = {
            "R00_s": 0.01,
            "R00_p": 0.0,
            "R00_total": 0.01,
            "R_total": 0.1,
            "T_total": 0.6,
            "A_volume_total": 0.3,
            "energy_closure_error_port_volume": 0.0,
        }
        coarse = {"A_volume_total": 0.29}
        enriched = {"A_volume_total": 0.3}
        energy = _energy_comparison(candidate, coarse, enriched)
        self.assertTrue(energy["pass"], energy["checks"])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timeline.csv"
            _write_timeline(path, _timeline_row())
            timeline = _timeline_resource_metrics(path)
        watchdog_resource = {
            key: value
            for key, value in timeline.items()
            if key
            in {
                "sample_count",
                "max_observed_worker_rank_count",
                "max_simultaneous_worker_rss_mb",
                "max_simultaneous_worker_pss_mb",
                "max_simultaneous_worker_uss_mb",
                "max_simultaneous_worker_smaps_swap_mb",
                "max_process_tree_rss_mb",
                "max_process_tree_swap_mb",
                "max_container_cgroup_current_observed_mb",
                "max_container_cgroup_peak_mb",
                "memory_authority_mb",
                "memory_authority_gib",
                "per_rank_smaps_rollup_peak_mb",
            }
        }
        resource = _resource_comparison(
            solver_summary=_solver_summary(),
            watchdog_resource=watchdog_resource,
            timeline=timeline,
        )
        self.assertTrue(resource["pass"], resource["checks"])
        self.assertLess(
            resource["candidate"]["peak_memory_gib"],
            MANDATORY_PEAK_GIB,
        )

        failed_timeline = dict(timeline)
        failed_timeline["memory_authority_gib"] = MANDATORY_PEAK_GIB + 0.1
        failed_timeline["memory_authority_mb"] = (
            failed_timeline["memory_authority_gib"] * 1024.0
        )
        failed_resource = _resource_comparison(
            solver_summary=_solver_summary(),
            watchdog_resource={
                **watchdog_resource,
                "memory_authority_gib": failed_timeline[
                    "memory_authority_gib"
                ],
                "memory_authority_mb": failed_timeline[
                    "memory_authority_mb"
                ],
            },
            timeline=failed_timeline,
        )
        self.assertFalse(failed_resource["pass"])
        self.assertFalse(
            failed_resource["checks"][
                "mandatory_peak_reduction_ge_20_percent"
            ]
        )

    def test_final_evaluator_requires_all_12_channels(self) -> None:
        watchdog = {
            "return_code": 0,
            "terminated_for_memory": False,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
            "qualification": {"pass": True},
        }
        solver_gate = {
            "pass": True,
            "checks": {"ordinary_default_unchanged": True},
        }
        channels = {
            "pass": True,
            "significant_power_pass_count": 12,
            "significant_complex_amplitude_pass_count": 12,
        }
        result = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=_pass_payload(),
            solver_gate=solver_gate,
            channel_comparison=channels,
            observable_comparison=_pass_payload(),
            energy_comparison=_pass_payload(),
            field_comparison=_pass_payload(),
            resource_comparison=_pass_payload(),
        )
        self.assertTrue(result["pass"])

        rejected = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=_pass_payload(),
            solver_gate=solver_gate,
            channel_comparison={
                **channels,
                "pass": False,
                "significant_power_pass_count": 11,
            },
            observable_comparison=_pass_payload(),
            energy_comparison=_pass_payload(),
            field_comparison=_pass_payload(),
            resource_comparison=_pass_payload(),
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "significant_12_power_and_12_amplitude",
            rejected["failures"],
        )


if __name__ == "__main__":
    unittest.main()
