from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

from benchmarks import run_task033_case090_watchdog as watchdog
from benchmarks import task033_case090_pde_core as core
from benchmarks import task034_wsl_resources as wsl_resources


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "task033_test57_watchdog"


def _summary() -> dict:
    limit = 1_000_000_000
    warning_threshold = int(limit * (11.5 / 14.0))
    termination_threshold = int(limit * (13.0 / 14.0))
    return core.attach_evidence_sha256(
        {
            "schema_version": core.WATCHDOG_SCHEMA_VERSION,
            "record_type": "external_shard_memory_watchdog",
            "case_id": core.CASE_ID,
            "status": "passed",
            "identity": {
                "mpi_size": 1,
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
                "command": ["mpiexec", "-n", "1"],
                "launched": True,
                "pid": 1234,
                "exit_code": 0,
            },
            "preflight": {
                "passed": True,
                "cgroup_memory_limit_state": "finite",
                "cgroup_memory_limit_bytes": limit,
                "cgroup_memory_current_bytes": 10_000_000,
                "host_available_memory_bytes": 2_000_000_000,
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
                "worker_tree_rss_peak_bytes": 10_000_000,
                "cgroup_memory_current_peak_bytes": 20_000_000,
                "observed_memory_peak_bytes": 20_000_000,
                "observed_memory_definition": "max(worker RSS, cgroup current)",
                "cgroup_memory_limit_bytes": limit,
                "cgroup_memory_limit_state": "finite",
                "effective_memory_bytes": limit,
                "warning_threshold_bytes": warning_threshold,
                "termination_threshold_bytes": termination_threshold,
                "host_available_memory_min_bytes": 2_000_000_000,
                "swap_current_initial_bytes": 0,
                "swap_current_final_bytes": 0,
                "swap_current_peak_bytes": 0,
                "swap_current_delta_bytes": 0,
                "swap_current_net_delta_bytes": 0,
                "nonzero_swap_sample_count": 0,
                "authority_unreadable_sample_count": 0,
                "raw_output": "benchmarks/artifacts/task033_test57_watchdog/raw.jsonl",
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


class Task033Case090WatchdogTests(unittest.TestCase):
    def test_summary_validator_recomputes_memory_qualification(self) -> None:
        summary = _summary()
        self.assertEqual(
            core.validate_watchdog_summary(
                summary,
                expected_mpi_size=1,
                expected_source_sha="1" * 40,
            ),
            [],
        )
        summary["sampling"]["observed_memory_peak_bytes"] = 960_000_000
        summary = core.attach_evidence_sha256(summary)
        problems = core.validate_watchdog_summary(summary)
        self.assertTrue(any("termination threshold" in problem for problem in problems))

    def test_observed_sample_uses_only_dedicated_cgroup_authority(self) -> None:
        sample = watchdog.sample_memory(os.getpid(), worker_alive=True)
        dedicated_current = (
            sample["cgroup_memory_current_bytes"]
            if sample["cgroup_memory_is_dedicated_job_authority"]
            else 0
        )
        self.assertEqual(
            sample["observed_memory_bytes"],
            max(sample["worker_tree_rss_sum_bytes"], dedicated_current or 0),
        )
        self.assertEqual(
            sample["resource_authority_mode"],
            "task034_wsl_effective_limit",
        )
        self.assertIn("process_tree_swap_bytes", sample)
        self.assertIn("swap_current_bytes", sample)
        self.assertIn("host_available_memory_bytes", sample)


    def test_non_wsl_runtime_preserves_legacy_finite_cgroup_sampling(self) -> None:
        with (
            patch.object(watchdog, "_is_wsl_runtime", return_value=False),
            patch.object(
                watchdog,
                "_portable_process_tree_rss",
                return_value=(10, 1),
            ),
            patch.object(
                watchdog,
                "_cgroup_value",
                side_effect=[(20, "memory.current"), (0, "memory.swap.current")],
            ),
            patch.object(
                watchdog,
                "_cgroup_limit",
                return_value=(1000, "memory.max", "finite"),
            ),
            patch.object(
                watchdog,
                "_proc_meminfo",
                return_value={"MemAvailable": 2000},
            ),
        ):
            sample = watchdog.sample_memory(os.getpid(), worker_alive=True)
        self.assertEqual(
            sample["resource_authority_mode"],
            "legacy_finite_cgroup_14g",
        )
        self.assertEqual(sample["observed_memory_bytes"], 20)
        preflight, failures = watchdog.build_preflight(sample)
        self.assertEqual(failures, [])
        self.assertEqual(
            preflight["resource_authority_mode"],
            "legacy_finite_cgroup_14g",
        )

    def test_native_wsl_preflight_uses_task034_effective_limit(self) -> None:
        sample = watchdog.sample_memory(os.getpid(), worker_alive=True)
        preflight, failures = watchdog.build_preflight(sample)
        self.assertEqual(failures, [])
        self.assertTrue(preflight["passed"])
        self.assertEqual(
            preflight["resource_authority_mode"],
            "task034_wsl_effective_limit",
        )
        self.assertEqual(
            preflight["warning_threshold_bytes"],
            int(0.80 * preflight["effective_memory_bytes"]),
        )
        self.assertEqual(
            preflight["termination_threshold_bytes"],
            int(0.95 * preflight["effective_memory_bytes"]),
        )
        sampling, sampling_failures = watchdog.summarize_samples(
            [sample, sample],
            raw_output=ARTIFACT_ROOT / "wsl_raw.jsonl",
            summary_output=ARTIFACT_ROOT / "wsl_summary.json",
            preflight=preflight,
        )
        self.assertEqual(sampling_failures, [])
        self.assertEqual(
            sampling["cgroup_memory_limit_state"],
            "not_dedicated_unbounded_or_unreadable_diagnostic_only",
        )

    def test_unbounded_or_unreadable_container_limit_fails_closed(self) -> None:
        samples = [
            {
                "worker_tree_rss_sum_bytes": 10,
                "cgroup_memory_current_bytes": 20,
                "observed_memory_bytes": 20,
                "cgroup_memory_limit_bytes": None,
                "cgroup_memory_limit_state": "unbounded",
                "host_available_memory_bytes": 2000,
                "swap_current_bytes": 0,
                "sources": {},
            }
            for _ in range(2)
        ]
        _, failures = watchdog.summarize_samples(
            samples,
            raw_output=ARTIFACT_ROOT / "unbounded_raw.jsonl",
            summary_output=ARTIFACT_ROOT / "unbounded_summary.json",
        )
        self.assertTrue(
            any("unbounded" in failure for failure in failures)
        )


    def test_wsl_summary_accepts_nondedicated_cgroup_diagnostic(self) -> None:
        summary = _summary()
        effective = 1_000_000_000
        summary["preflight"].update(
            {
                "resource_authority_mode": "task034_wsl_effective_limit",
                "cgroup_memory_limit_state": (
                    "not_dedicated_unbounded_or_unreadable_diagnostic_only"
                ),
                "cgroup_memory_limit_bytes": None,
                "cgroup_memory_is_dedicated_job_authority": False,
                "effective_memory_bytes": effective,
                "warning_threshold_bytes": int(0.80 * effective),
                "termination_threshold_bytes": int(0.95 * effective),
                "warning_scale": 0.80,
                "termination_scale": 0.95,
                "task034_effective_limit": {
                    "user_limit_bytes": effective,
                    "wsl_total_85_percent_bytes": 1_200_000_000,
                    "available_minus_reserve_bytes": 1_300_000_000,
                    "effective_limit_bytes": effective,
                    "warning_bytes": int(0.80 * effective),
                    "termination_bytes": int(0.95 * effective),
                },
            }
        )
        summary["sampling"].update(
            {
                "resource_authority_mode": "task034_wsl_effective_limit",
                "process_tree_swap_peak_bytes": 0,
                "dedicated_job_cgroup_observed": False,
                "cgroup_memory_limit_state": (
                    "not_dedicated_unbounded_or_unreadable_diagnostic_only"
                ),
                "cgroup_memory_limit_bytes": None,
                "effective_memory_bytes": effective,
                "warning_threshold_bytes": int(0.80 * effective),
                "termination_threshold_bytes": int(0.95 * effective),
            }
        )
        summary["qualification"].update(
            {
                "requires_finite_container_limit": False,
                "resource_authority_mode": "task034_wsl_effective_limit",
                "warning_scale": 0.80,
                "termination_scale": 0.95,
            }
        )
        summary = core.attach_evidence_sha256(summary)
        self.assertEqual(core.validate_watchdog_summary(summary), [])

    def test_control_decisions_cover_swap_authority_memory_and_timeout(self) -> None:
        sample = {
            "worker_tree_rss_sum_bytes": 10,
            "cgroup_memory_current_bytes": 20,
            "observed_memory_bytes": 20,
            "cgroup_memory_limit_bytes": 1000,
            "cgroup_memory_limit_state": "finite",
            "host_available_memory_bytes": 2000,
            "swap_current_bytes": 0,
        }
        preflight, failures = watchdog.build_preflight(sample)
        self.assertEqual(failures, [])

        nonzero_swap = {**sample, "swap_current_bytes": 1}
        _, preflight_failures = watchdog.build_preflight(nonzero_swap)
        self.assertTrue(any("nonzero" in failure for failure in preflight_failures))
        decision = watchdog.watchdog_decision(
            nonzero_swap,
            preflight=preflight,
            elapsed_seconds=0.0,
            wall_timeout_seconds=100.0,
        )
        self.assertEqual(decision["trigger"], "nonzero_swap")
        self.assertTrue(decision["terminate"])

        unreadable = {**sample, "host_available_memory_bytes": None}
        decision = watchdog.watchdog_decision(
            unreadable,
            preflight=preflight,
            elapsed_seconds=0.0,
            wall_timeout_seconds=100.0,
        )
        self.assertEqual(decision["trigger"], "authority_unreadable")

        memory = {
            **sample,
            "observed_memory_bytes": preflight["termination_threshold_bytes"],
        }
        decision = watchdog.watchdog_decision(
            memory,
            preflight=preflight,
            elapsed_seconds=0.0,
            wall_timeout_seconds=100.0,
        )
        self.assertEqual(decision["trigger"], "memory_termination_threshold")

        decision = watchdog.watchdog_decision(
            sample,
            preflight=preflight,
            elapsed_seconds=100.0,
            wall_timeout_seconds=100.0,
        )
        self.assertEqual(decision["trigger"], "wall_timeout")

    def test_terminated_process_status_has_zero_memory_authority(self) -> None:
        self.assertEqual(
            wsl_resources._status_memory_kib(
                {"State": "Z (zombie)", "PPid": "1"}
            ),
            (0, 0),
        )
        self.assertEqual(
            wsl_resources._status_memory_kib(
                {"State": "S (sleeping)", "VmRSS": "12 kB", "VmSwap": "3 kB"}
            ),
            (12, 3),
        )
        self.assertEqual(
            wsl_resources._status_memory_kib({"State": "R (running)"}),
            (None, None),
        )

    def test_process_tree_status_exit_race_requires_confirmed_natural_exit(self) -> None:
        decision = {
            "trigger": "authority_unreadable",
            "detail": "process_tree_status",
        }
        exited = Mock()
        exited.poll.return_value = 0
        self.assertEqual(
            watchdog._natural_exit_after_process_tree_sample(exited, decision),
            0,
        )
        running = Mock()
        running.poll.return_value = None
        self.assertIsNone(
            watchdog._natural_exit_after_process_tree_sample(running, decision)
        )
        self.assertIsNone(
            watchdog._natural_exit_after_process_tree_sample(
                exited,
                {"trigger": "nonzero_swap", "detail": "1"},
            )
        )

    def test_confirmed_exit_race_is_not_an_unreadable_live_sample(self) -> None:
        sample = watchdog.sample_memory(os.getpid(), worker_alive=True)
        preflight, failures = watchdog.build_preflight(sample)
        self.assertEqual(failures, [])
        readable = dict(sample)
        exit_race = {
            **sample,
            "process_tree_all_status_readable": False,
            "process_tree_exit_race_observed": True,
            "worker_exit_code_observed_after_sample": 0,
        }
        sampling, failures = watchdog.summarize_samples(
            [readable, exit_race, readable],
            raw_output=ARTIFACT_ROOT / "exit_race_raw.jsonl",
            summary_output=ARTIFACT_ROOT / "exit_race_summary.json",
            preflight=preflight,
        )
        self.assertEqual(failures, [])
        self.assertEqual(sampling["authority_unreadable_sample_count"], 0)

        live_unreadable = dict(exit_race)
        live_unreadable.pop("process_tree_exit_race_observed")
        live_unreadable.pop("worker_exit_code_observed_after_sample")
        sampling, _ = watchdog.summarize_samples(
            [readable, live_unreadable, readable],
            raw_output=ARTIFACT_ROOT / "live_unreadable_raw.jsonl",
            summary_output=ARTIFACT_ROOT / "live_unreadable_summary.json",
            preflight=preflight,
        )
        self.assertEqual(sampling["authority_unreadable_sample_count"], 1)

    def test_synthetic_continuous_samples_are_summarized_without_raw_embedding(self) -> None:
        samples = [
            {
                "worker_tree_rss_sum_bytes": 10 + index,
                "cgroup_memory_current_bytes": 20 + index,
                "observed_memory_bytes": 20 + index,
                "cgroup_memory_limit_bytes": 1000,
                "cgroup_memory_limit_state": "finite",
                "host_available_memory_bytes": 2000 - index,
                "swap_current_bytes": 0,
                "sources": {
                    "cgroup_memory_current": "/sys/fs/cgroup/memory.current",
                    "cgroup_memory_limit": "/sys/fs/cgroup/memory.max",
                    "swap_current": "/sys/fs/cgroup/memory.swap.current",
                },
            }
            for index in range(3)
        ]
        sampling, failures = watchdog.summarize_samples(
            samples,
            raw_output=ARTIFACT_ROOT / "raw.jsonl",
            summary_output=ARTIFACT_ROOT / "summary.json",
        )
        self.assertEqual(failures, [])
        self.assertEqual(sampling["sample_count"], 3)
        self.assertEqual(sampling["observed_memory_peak_bytes"], 22)
        self.assertNotIn("samples", sampling)

    @unittest.skipUnless(
        os.environ.get("RUN_TASK033_CORE_DOCKER_TESTS") == "1",
        "Set RUN_TASK033_CORE_DOCKER_TESTS=1 in the DOLFINx image.",
    )
    def test_docker_cgroup_sampling_tracks_live_worker(self) -> None:
        ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; payload=bytearray(8*1024*1024); time.sleep(0.35)",
            ],
            cwd=ROOT,
        )
        samples = []
        while process.poll() is None:
            samples.append(watchdog.sample_memory(process.pid, worker_alive=True))
            time.sleep(0.08)
        samples.append(watchdog.sample_memory(process.pid, worker_alive=False))
        raw = ARTIFACT_ROOT / "docker_raw.jsonl"
        raw.write_text(
            "".join(json.dumps(sample) + "\n" for sample in samples),
            encoding="utf-8",
        )
        sampling, failures = watchdog.summarize_samples(
            samples,
            raw_output=raw,
            summary_output=ARTIFACT_ROOT / "docker_summary.json",
        )
        self.assertEqual(process.returncode, 0)
        self.assertGreaterEqual(sampling["sample_count"], 2)
        self.assertGreater(sampling["worker_tree_rss_peak_bytes"], 0)
        self.assertGreater(sampling["cgroup_memory_current_peak_bytes"], 0)
        self.assertGreater(sampling["cgroup_memory_limit_bytes"], 0)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
