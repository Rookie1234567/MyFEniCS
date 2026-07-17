from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from benchmarks import run_task033_case090_watchdog as watchdog
from benchmarks import task033_case090_pde_core as core


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

    def test_observed_sample_is_max_of_worker_tree_and_cgroup(self) -> None:
        sample = watchdog.sample_memory(os.getpid(), worker_alive=True)
        self.assertEqual(
            sample["observed_memory_bytes"],
            max(
                sample["worker_tree_rss_sum_bytes"],
                sample["cgroup_memory_current_bytes"] or 0,
            ),
        )
        self.assertIn("swap_current_bytes", sample)
        self.assertIn("host_available_memory_bytes", sample)

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
