from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.physical_intermediate_checker import main
from scripts.task39extra_event_observer import Observer, _proc_identity
from src.runners.physical_balanced_output import (
    _observer_pair_receipt,
    _r13_pair_binding_errors,
    _r13_mode_identity,
    _r13_source_identity_errors,
)


def _identity_facts(q: int) -> dict:
    """Small binding unit facts; producer schemas are covered below from live producers."""
    return {
        "profile_identity": f"dual_condensed_balh_native_13p5_q{q}_v5",
        "coarse_degree": q,
        "run_directory": f"/tmp/r13-formal-{q}",
        # The data model run_id can be equal between distinct timestamped runs.
        "run_id": "original_13p5nm_v5",
        "source_sha": "a" * 40,
        "input_sha256": str(q) * 64,
        "physical_model_sha256": "b" * 64,
        "mode_sha256": "c" * 64,
        "native_solution_identity": {
            "residual_arrays_sha256": "d" * 64,
            "final_solution_sha256": "e" * 64,
            "operator_identity_sha256": "f" * 64,
        },
        "runtime_fingerprint": {"libraries": {"integer": "int64", "scalar": "complex128"}},
        "supervision": {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "resource_stop_policy": "measured_tree_rss_only_v3",
            "rss_hard_limit_bytes": 1_300_000_000_000,
            "sampled_process_tree_rss_peak_bytes": 4_000_000_000,
            "parent_identity": {"pid": 100 + q, "start_ticks": 1000 + q},
            "worker_identity": {"pid": 200 + q, "start_ticks": 2000 + q},
        },
    }


class Task39ExtraV5R13PairReleaseTests(unittest.TestCase):
    def test_actual_watchdog_and_observer_producers_match_pair_identity_schema(self):
        with tempfile.TemporaryDirectory(prefix="task39extra-r13-schema-") as temp:
            root = Path(temp)
            run = root / "formal_run"
            run.mkdir()
            watchdog_dir = run / "watchdog"
            script = (
                "import json,sys,time; "
                "from pathlib import Path; "
                "from benchmarks.subreaper_watchdog import supervise; "
                "r=supervise([sys.executable,'-c','import time;time.sleep(.15)'], "
                "Path(sys.argv[1]), wall_seconds=5.0, solve_seconds=5.0, "
                "interval=.05, grace_seconds=.5); "
                "print(json.dumps(r,allow_nan=False))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script, str(watchdog_dir)],
                cwd=Path(__file__).resolve().parents[2],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            watchdog = json.loads(completed.stdout.splitlines()[-1])
            self.assertEqual(watchdog["classification"], "COMPLETED")
            self.assertIsInstance(watchdog["samples"], int)
            self.assertGreater(watchdog["samples"], 0)
            self.assertTrue((watchdog_dir / "resources.jsonl").is_file())

            child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(.4)"])
            try:
                for _ in range(100):
                    worker_identity = _proc_identity(child.pid)
                    if worker_identity.get("state") == "present":
                        break
                    time.sleep(.005)
                root_identity = _proc_identity(os.getpid())
                self.assertEqual(root_identity.get("state"), "present")
                self.assertEqual(worker_identity.get("state"), "present")
                observer_log = root / "observer.jsonl"
                observer = Observer(
                    run_dir=run,
                    log_path=observer_log,
                    thread="schema-test-only",
                    root_pid=os.getpid(),
                    root_start_ticks=root_identity["start_ticks"],
                    worker_pid=child.pid,
                    worker_start_ticks=worker_identity["start_ticks"],
                    helper="unused-in-test",
                    interval=15.0,
                )
                observer._log({
                    "kind": "observer_started",
                    "run_dir": str(run),
                    "identities": observer.identities,
                    "interval_seconds": observer.interval,
                })
                receipt = _observer_pair_receipt(observer_log, run)
                self.assertEqual(receipt["root"]["pid"], os.getpid())
                self.assertEqual(receipt["worker"]["pid"], child.pid)
                # Missing notification completion is diagnostic, not a pair Gate.
                self.assertFalse(receipt["terminal_notification_acknowledged"])
                self.assertFalse(receipt["observer_finished"])
            finally:
                child.wait(timeout=3)

    def test_pair_binding_uses_distinct_run_directories_not_model_run_id(self):
        q4, q3 = _identity_facts(4), _identity_facts(3)
        self.assertEqual(q4["run_id"], q3["run_id"])
        self.assertEqual(_r13_pair_binding_errors(q4, q3), [])

        changed_source = dict(q3, source_sha="d" * 40)
        self.assertTrue(any("source_sha mismatch" in error
                            for error in _r13_pair_binding_errors(q4, changed_source)))

        changed_runtime = dict(q3, runtime_fingerprint={"libraries": {"integer": "int32"}})
        self.assertTrue(any("runtime or ABI" in error
                            for error in _r13_pair_binding_errors(q4, changed_runtime)))

        incomplete_supervision = dict(q3, supervision={
            **q3["supervision"], "worker_identity": {"pid": 1}
        })
        self.assertTrue(any("worker PID/start_ticks" in error
                            for error in _r13_pair_binding_errors(q4, incomplete_supervision)))

    def test_pair_source_gate_matches_successful_launcher_and_watchdog_schema(self):
        source_sha = "a" * 40
        source_state = {
            "source_sha": source_sha,
            "tracked_and_nonignored_untracked_clean": True,
            "actual_git_directory": "/repo/.git/worktrees/task",
        }
        manifest = {"source_sha": source_sha, "source_after": source_state}
        watchdog = {"source_state": source_state}
        self.assertEqual(_r13_source_identity_errors(manifest, watchdog), [])

        dirty_manifest = {
            "source_sha": source_sha,
            "source_after": {**source_state, "tracked_and_nonignored_untracked_clean": False},
        }
        self.assertTrue(any("launcher source_after is not recorded clean" in error
                            for error in _r13_source_identity_errors(dirty_manifest, watchdog)))

        mismatched_watchdog = {
            "source_state": {**source_state, "source_sha": "b" * 40},
        }
        self.assertTrue(any("watchdog source_state SHA differs" in error
                            for error in _r13_source_identity_errors(manifest, mismatched_watchdog)))

        failed_source = {"source_sha": source_sha,
                         "source_after": {"provenance_passed": False, "error": "dirty"}}
        self.assertTrue(any("launcher source_after is not recorded clean" in error
                            for error in _r13_source_identity_errors(failed_source, watchdog)))

    def test_pair_mode_identity_reads_actual_retained_summary_schema(self):
        mode_sha = "c" * 64
        summary = {
            "retained_runtime": {
                "mode_sha256": mode_sha,
                "space_identity": {
                    "fine_mode_sha256": mode_sha,
                    "fine_global_rows": 667152,
                },
            },
        }
        self.assertEqual(_r13_mode_identity(summary, 667152),
                         (mode_sha, summary["retained_runtime"]["space_identity"]))

        changed_space = {
            "retained_runtime": {
                **summary["retained_runtime"],
                "space_identity": {
                    **summary["retained_runtime"]["space_identity"],
                    "fine_mode_sha256": "d" * 64,
                },
            },
        }
        with self.assertRaisesRegex(ValueError, "p6 space/mode identity mismatch"):
            _r13_mode_identity(changed_space, 667152)

        changed_summary = {**summary, "mode_sha256": "e" * 64}
        with self.assertRaisesRegex(ValueError, "p6 space/mode identity mismatch"):
            _r13_mode_identity(changed_summary, 667152)

        with self.assertRaisesRegex(ValueError, "saved solution rows"):
            _r13_mode_identity(summary, 1)

    def test_checker_cli_writes_nonoverwriting_numerical_pair_record(self):
        with tempfile.TemporaryDirectory(prefix="task39extra-r13-pair-entry-") as temp:
            root = Path(temp)
            q4, q3 = root / "q4", root / "q3"
            q4.mkdir()
            q3.mkdir()
            q4_observer, q3_observer = root / "q4-observer.jsonl", root / "q3-observer.jsonl"
            q4_observer.write_text("observer diagnostics are supplied explicitly\n")
            q3_observer.write_text("observer diagnostics are supplied explicitly\n")
            numerical_pass = {
                "status": "NUMERICAL_PAIR_PASS",
                "release_status": "PENDING_COMMON_PATH_AND_SUSTAINED_HARDWARE_REVIEW",
                "automatic_r13_release": False,
                "gate_failures": [],
            }
            with patch("src.runners.physical_balanced_output.compare_r13_pair",
                       return_value=numerical_pass):
                status = main([
                    "--r13-pair", str(q4), str(q3),
                    "--q4-observer-log", str(q4_observer),
                    "--q3-observer-log", str(q3_observer),
                ])
            self.assertEqual(status, 0)
            record = json.loads((q3 / "r13_pair_numerical_comparison.json").read_text())
            self.assertEqual(record["status"], "NUMERICAL_PAIR_PASS")
            self.assertEqual(record["release_status"],
                             "PENDING_COMMON_PATH_AND_SUSTAINED_HARDWARE_REVIEW")
            self.assertFalse(record["automatic_r13_release"])
            self.assertEqual(record["entry"],
                             "benchmarks.physical_intermediate_checker --r13-pair")
            with patch("src.runners.physical_balanced_output.compare_r13_pair",
                       return_value=numerical_pass):
                self.assertEqual(main([
                    "--r13-pair", str(q4), str(q3),
                    "--q4-observer-log", str(q4_observer),
                    "--q3-observer-log", str(q3_observer),
                ]), 2)


if __name__ == "__main__":
    unittest.main()
