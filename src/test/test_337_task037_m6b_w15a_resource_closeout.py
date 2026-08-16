from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import run_task037_extra_h2b as h2b
from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w14_global_b0_inner_pc as w14


EXPECTED_SOURCE = "expected-source"
FROZEN_AUTHORITY = {"checkpoint": "frozen-w14b"}


def _patch_checker(monkeypatch: pytest.MonkeyPatch, *, worker_pass: bool):
    monkeypatch.setattr(
        runner,
        "_m6b_w15a_w14b_checkpoint1_authority",
        lambda compact, raw: {"authority": FROZEN_AUTHORITY},
    )
    monkeypatch.setattr(runner, "_m6b_w14a_jit_closeout_valid", lambda value, h: True)
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda value: True)
    monkeypatch.setattr(runner, "_m6b_expected_p6", lambda value: True)
    monkeypatch.setattr(
        runner,
        "_m6b_w14a_action_audit_closeout_valid",
        lambda value, expected_authority_roles=("target",): expected_authority_roles
        == ("w14b_checkpoint1_residual",),
    )
    monkeypatch.setattr(
        h2b,
        "_light_source",
        lambda: {"source_commit_full_sha": EXPECTED_SOURCE},
    )

    def fake_evaluator(**kwargs):
        return {
            "checks": {
                "base_contract": bool(worker_pass),
                "checkpoint_authority": bool(worker_pass),
                "local_rho": bool(worker_pass),
                "cumulative_rho": bool(worker_pass),
            }
        }

    monkeypatch.setattr(w14, "evaluate_w15a_restart1_gate", fake_evaluator)


def _fixture(tmp_path: Path, *, worker_pass: bool = True, peak: int = 128):
    raw_dir = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw_dir.mkdir(parents=True)
    watchdog_dir.mkdir(parents=True)
    authority = {
        "q": {"raw_path": str(tmp_path / "w5" / "m6b_iter200_residual.npy")},
        "target": {
            "raw_path": str(tmp_path / "w7" / "m6b_iter400_residual.npy")
        },
        "w14b_checkpoint1": FROZEN_AUTHORITY,
    }
    core = {
        "inner_audit": {},
        "z_identity": {},
        "p_identity": {},
        "measurement": {},
        "p2_measurement": {},
        "physical_action_count": 2,
        "cumulative_rho": 0.8,
        "checkpoint_authority": FROZEN_AUTHORITY,
    }
    summary = runner._attach_evidence(
        {
            "schema": runner.M6B_W15A_SCHEMA,
            "phase": runner.M6B_W15A_PHASE,
            "status": "restart1_gate_pass"
            if worker_pass
            else "gate_failed",
            "classification": (
                "W15A_RESTART1_RANK1_PASS"
                if worker_pass
                else "W15A_RESTART1_NUMERIC_FAIL"
            ),
            "w15a_pass": bool(worker_pass),
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
            "w15b_locked": True,
            "scope": runner._m6b_w15a_scope(),
            "predicted_live_set": runner._m6b_w15a_predicted_live_set(),
            "p6": {},
            "authority": authority,
            "source_at_start": {
                "source_commit_full_sha": EXPECTED_SOURCE
            },
            "source_at_end": {"source_commit_full_sha": EXPECTED_SOURCE},
            "jit_cache": {
                "physical_source": "physical-jit",
                "b0_source": "b0-jit",
            },
            "action_audit": {
                "lifecycle_events": [
                    "b0_constructed",
                    "physical_constructed",
                    "coexistence_ready",
                    "physical_released",
                    "b0_released",
                ]
            },
            "architecture": {},
            "core": core,
        }
    )
    (raw_dir / runner.M6B_W15A_SUMMARY_FILENAME).write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    progress = [
        {
            "schema": f"{runner.M6B_W15A_SCHEMA}.progress.v1",
            "phase": runner.M6B_W15A_PHASE,
            "event": event,
        }
        for event in runner.M6B_W15A_EVENTS
    ]
    (raw_dir / runner.M6B_W15A_PROGRESS_FILENAME).write_text(
        "".join(json.dumps(item) + "\n" for item in progress),
        encoding="utf-8",
    )
    timeline_path = watchdog_dir / f"{runner.M6B_W15A_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W15A_PHASE,
                "rss_bytes": peak,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stdout_path = watchdog_dir / f"{runner.M6B_W15A_PHASE}_stdout.txt"
    root_path = watchdog_dir / f"{runner.M6B_W15A_PHASE}_root_pid.json"
    stdout_path.write_text("worker\n", encoding="utf-8")
    root_path.write_text("{}\n", encoding="utf-8")
    timeline = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W15A_PHASE
    )
    command = runner._m6b_w15a_worker_command(
        raw_dir,
        runner.ROOT / runner.M6B_W6A_W5_COMPACT_RELATIVE_PATH,
        Path(authority["q"]["raw_path"]).parent,
        runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
        Path(authority["target"]["raw_path"]).parent,
        runner.ROOT / runner.M6B_W11A_M3Y_MANIFEST_RELATIVE_PATH,
        Path("physical-jit"),
        Path("b0-jit"),
        runner.ROOT / runner.M6B_W15A_W14B_COMPACT_RELATIVE_PATH,
        runner.ROOT / runner.M6B_W15A_W14B_RAW_RELATIVE_PATH,
        EXPECTED_SOURCE,
    )
    watchdog = runner._attach_evidence(
        {
            "schema": runner.M6B_W15A_WATCHDOG_SCHEMA,
            "phase": runner.M6B_W15A_PHASE,
            "status": "measurement_complete"
            if worker_pass
            else "gate_failed",
            "process": {
                "return_code": 0 if worker_pass else 1,
                "termination": None,
                "peak_rss_bytes": peak,
                "swap_bytes": 0,
            },
            "drain": {"gone": True},
            "source_at_start": {"source_commit_full_sha": EXPECTED_SOURCE},
            "source_at_end": {"source_commit_full_sha": EXPECTED_SOURCE},
            "source_end_clean": True,
            "resource_limits": {
                "timeout_seconds": runner.M6B_W15A_TIMEOUT_SECONDS,
                "watchdog_rss_bytes": runner.M6B_W15A_WATCHDOG_RSS_LIMIT_BYTES,
                "completion_peak_rss_bytes": runner.M6B_W15A_FORMAL_RSS_LIMIT_BYTES,
                "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
            },
            "raw_dir": str(raw_dir),
            "watchdog_dir": str(watchdog_dir),
            "command": command,
            "w14b_checkpoint_authority": FROZEN_AUTHORITY,
            "artifact_inventory": {
                "raw": runner._m6b_w15a_raw_artifacts(raw_dir),
                "watchdog": runner._m6b_w15a_watchdog_artifacts(watchdog_dir),
            },
            "worker_summary": runner._artifact(
                raw_dir, runner.M6B_W15A_SUMMARY_FILENAME
            ),
            "timeline": timeline,
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
            "w15b_unlocked": False,
        }
    )
    watchdog_path = watchdog_dir / runner.M6B_W15A_WATCHDOG_SUMMARY_FILENAME
    watchdog_path.write_text(
        json.dumps(watchdog, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return raw_dir, watchdog_path


def test_w15a_check_pass_and_compact_is_scalar_only(tmp_path, monkeypatch):
    _patch_checker(monkeypatch, worker_pass=True)
    raw_dir, watchdog_path = _fixture(tmp_path)
    output = tmp_path / "formal.json"
    assert runner._run_m6b_w15a_check(
        raw_dir, watchdog_path, output, EXPECTED_SOURCE
    ) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["classification"] == "W15A_FORMAL_RESOURCE_CLOSEOUT_PASS"
    assert result["w15b_unlocked"] is True
    assert "records" not in result["timeline"]
    assert runner._evidence_valid(result)


def test_w15a_honest_numeric_fail_is_not_execution_fail(tmp_path, monkeypatch):
    _patch_checker(monkeypatch, worker_pass=False)
    raw_dir, watchdog_path = _fixture(tmp_path, worker_pass=False)
    gate = runner._m6b_w15a_formal_gate(raw_dir, watchdog_path, EXPECTED_SOURCE)
    assert gate["classification"] == "W15A_RESTART1_NUMERIC_FAIL"
    assert gate["checks"]["execution_semantics"] is True
    assert gate["checks"]["resource"] is True


def test_w15a_resource_and_missing_key_fail_closed(tmp_path, monkeypatch):
    _patch_checker(monkeypatch, worker_pass=True)
    raw_dir, watchdog_path = _fixture(
        tmp_path / "resource", peak=runner.M6B_W15A_FORMAL_RSS_LIMIT_BYTES
    )
    gate = runner._m6b_w15a_formal_gate(raw_dir, watchdog_path, EXPECTED_SOURCE)
    assert gate["classification"] == "W15A_RESOURCE_FAIL"

    missing = json.loads(watchdog_path.read_text(encoding="utf-8"))
    missing.pop("process")
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(missing)) + "\n", encoding="utf-8"
    )
    gate = runner._m6b_w15a_formal_gate(raw_dir, watchdog_path, EXPECTED_SOURCE)
    assert gate["classification"] == "W15A_EXECUTION_OR_EVIDENCE_FAIL"


def test_w15a_cli_command_and_marker_contract():
    expected_events = (
        "authority_validated",
        "w14b_checkpoint1_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "b0_ready",
        "inner_pc_ready",
        "physical_action_ready",
        "coexistence_ready",
        "inner_apply_1_ready",
        "inner_apply_2_ready",
        "physical_apply_1_ready",
        "physical_apply_2_ready",
        "measurement_ready",
        "summary_ready",
    )
    assert runner.M6B_W15A_EVENTS == expected_events
    args = runner._parser().parse_args(
        [
            "m6b-w15a-watchdog",
            "--run-dir", "run",
            "--watchdog-dir", "watchdog",
            "--w5-compact", "w5",
            "--w5-raw-dir", "w5raw",
            "--w7-compact", "w7",
            "--w7-raw-dir", "w7raw",
            "--m3y-manifest", "m3y",
            "--jit-cache-source", "physical",
            "--b0-jit-cache-source", "b0",
            "--w14b-compact", "w14b",
            "--w14b-raw-dir", "w14braw",
            "--expected-source-sha", "b" * 40,
        ]
    )
    assert args.command == "m6b-w15a-watchdog"
    check_args = runner._parser().parse_args(
        [
            "m6b-w15a-check",
            "--raw-dir", "raw",
            "--watchdog-summary", "watchdog.json",
            "--output", "out.json",
            "--expected-source-sha", "b" * 40,
        ]
    )
    assert check_args.command == "m6b-w15a-check"
    command = runner._m6b_w15a_worker_command(
        Path("run"), Path("w5"), Path("w5raw"), Path("w7"), Path("w7raw"),
        Path("m3y"), Path("physical"), Path("b0"), Path("w14b"),
        Path("w14braw"), "source",
    )
    assert command[3] == "m6b-w15a-restarted-rank1-diagnostic"
    assert "--w14b-raw-dir" in command
