from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w14_global_b0_inner_pc as w14_core


SOURCE_SHA = "a" * 40


def _source() -> dict[str, object]:
    return {
        "source_commit_full_sha": SOURCE_SHA,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _write_array(path: Path, values: np.ndarray) -> dict[str, object]:
    np.save(path, values, allow_pickle=False)
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(values),
        "shape": list(values.shape),
        "dtype": str(values.dtype),
    }


def _jit_fixture(tmp_path: Path) -> dict[str, object]:
    physical = tmp_path / "physical-jit"
    b0 = tmp_path / "b0-jit"
    target = tmp_path / "union-jit"
    return {
        "physical_source": str(physical),
        "b0_source": str(b0),
        "union_target": str(target),
        "physical_source_before": {"inventory_sha256": "physical", "entries": []},
        "b0_source_before": {"inventory_sha256": "b0", "entries": []},
        "physical_source_final": {"inventory_sha256": "physical", "entries": []},
        "b0_source_final": {"inventory_sha256": "b0", "entries": []},
        "union_target_final": {"inventory_sha256": "union", "entries": []},
        "physical_file_count": runner.M6B_W11A_PHYSICAL_JIT_FILE_COUNT,
        "b0_file_count": runner.M6B_W11A_B0_JIT_FILE_COUNT,
        "union_file_count": runner.M6B_W11A_UNION_JIT_FILE_COUNT,
        "warm_precompiled": True,
        "runtime_compile_allowed": False,
        "source_unchanged": True,
        "target_frozen_unchanged": True,
        "verification_error": None,
        "verification_stages": [],
    }


def _make_fixture(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 2)
    monkeypatch.setattr(runner, "M6B_W14B_SCRATCH_BYTES", 288)
    raw = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw.mkdir()
    watchdog_dir.mkdir()
    (raw / "outer_checkpoints").mkdir()
    (raw / "outer_scratch").mkdir()
    (watchdog_dir / f"{runner.M6B_W14B_PHASE}_stdout.txt").write_text("ok")
    (watchdog_dir / f"{runner.M6B_W14B_PHASE}_root_pid.json").write_text("{}")
    timeline_path = watchdog_dir / f"{runner.M6B_W14B_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W14B_PHASE,
                "rss_bytes": 100,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n"
    )
    progress = []
    for index, event in enumerate(runner.M6B_W14B_EVENTS):
        progress.append(
            {
                "schema": f"{runner.M6B_W14B_SCHEMA}.progress.v1",
                "phase": runner.M6B_W14B_PHASE,
                "event": event,
                "elapsed_wall_seconds": float(index),
            }
        )
    (raw / runner.M6B_W14B_PROGRESS_FILENAME).write_text(
        "".join(json.dumps(item) + "\n" for item in progress)
    )

    samples = {}
    for iteration, rho in ((1, 0.8943645606070599), (2, 0.8), (4, 0.7)):
        rhs = np.array([1.0 + 0.0j, 0.0j], dtype=np.complex128)
        outer_action = np.array([1.0 - rho + 0.0j, 0.0j], dtype=np.complex128)
        residual = rhs - outer_action
        solution = np.array([0.0j, 0.0j], dtype=np.complex128)
        values = {
            "solution": solution,
            "outer_action": outer_action,
            "residual": residual,
            "rhs": rhs,
        }
        artifacts = {
            name: _write_array(
                raw / "outer_checkpoints" / f"m6b_iter{iteration}_{name}.npy",
                value,
            )
            for name, value in values.items()
        }
        samples[str(iteration)] = {
            "iteration": iteration,
            "true_relative_residual": rho,
            "estimated_relative_residual": rho,
            "finite": True,
            "estimated_diagnostic": True,
            "artifacts": artifacts,
        }

    for name, size in (
        ("v_basis.bin", 2 * 5 * 16),
        ("z_basis.bin", 2 * 4 * 16),
    ):
        path = raw / "outer_scratch" / name
        path.touch()
        with path.open("r+b") as stream:
            stream.truncate(size)

    authority = {
        "path": str(
            (runner.ROOT / runner.M6B_W14B_W14A_COMPACT_RELATIVE_PATH).resolve()
        ),
        "file_sha256": runner.M6B_W14B_W14A_COMPACT_FILE_SHA256,
        "evidence_sha256": runner.M6B_W14B_W14A_COMPACT_EVIDENCE_SHA256,
        "producer_source_sha": runner.M6B_W14B_W14A_PRODUCER_SHA,
        "anchor_rho": 0.8943645606070599,
        "measured_peak_rss_bytes": 1_158_553_600,
        "measured_swap_bytes": 0,
        "inner_pc_apply_count": 40,
        "physical_action_count": 2,
        "formal_pass": True,
        "pde_pass": False,
        "official_rta": False,
        "w14_2_unlocked": True,
    }
    jit = _jit_fixture(tmp_path)
    raw_path = str((tmp_path / "w5raw").resolve())
    target_path = str((tmp_path / "w7raw").resolve() / "m6b_iter200_residual.npy")
    summary = {
        "schema": runner.M6B_W14B_SCHEMA,
        "phase": runner.M6B_W14B_PHASE,
        "status": "correction_gate_pass",
        "classification": "W14B_FIXED4_CORRECTION_PASS",
        "w14b_pass": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "formal_resource_closeout_pending": True,
        "w14c_locked": True,
        "scope": runner._m6b_w14b_scope(),
        "authority": {
            "w14a_compact": authority,
            "q": {"raw_path": raw_path + "/m6b_iter200_residual.npy"},
            "target": {"raw_path": target_path},
        },
        "p6": {
            "global_cells": runner.M6B_GLOBAL_CELLS,
            "local_cells": runner.M6B_GLOBAL_CELLS,
            "local_nloc": runner.M6B_LOCAL_NLOC,
            "global_rows": runner.M6B_GLOBAL_ROWS,
            "constraint_count": runner.M6B_CONSTRAINTS,
        },
        "predicted_live_set": runner._m6b_w14b_predicted_live_set(),
        "architecture": {},
        "action_audit": {},
        "core": {
            "outer_audit": {
                "scratch_bytes": runner.M6B_W14B_SCRATCH_BYTES,
                "scratch_mmap": False,
                "scratch_basis_in_memory": False,
                "basis_in_memory": False,
                "mmap": False,
                "scratch_paths": {
                    "v_basis": str((raw / "outer_scratch/v_basis.bin").resolve()),
                    "z_basis": str((raw / "outer_scratch/z_basis.bin").resolve()),
                },
                "v_basis": {
                    "path": str((raw / "outer_scratch/v_basis.bin").resolve()),
                    "rows": 2,
                    "dtype": "complex128",
                    "capacity": 5,
                    "written_count": 5,
                    "read_count": 20,
                    "write_count": 5,
                    "allocated_bytes": 2 * 5 * 16,
                    "bytes_read": 2 * 20 * 16,
                    "bytes_written": 2 * 5 * 16,
                    "mmap": False,
                },
                "z_basis": {
                    "path": str((raw / "outer_scratch/z_basis.bin").resolve()),
                    "rows": 2,
                    "dtype": "complex128",
                    "capacity": 4,
                    "written_count": 4,
                    "read_count": 7,
                    "write_count": 4,
                    "allocated_bytes": 2 * 4 * 16,
                    "bytes_read": 2 * 7 * 16,
                    "bytes_written": 2 * 4 * 16,
                    "mmap": False,
                },
            },
            "inner_audit": {},
            "samples": samples,
            "physical_action_count": 7,
        },
        "jit_cache": jit,
        "source_at_start": _source(),
        "source_at_end": _source(),
    }
    (raw / runner.M6B_W14B_SUMMARY_FILENAME).write_text(
        json.dumps(runner._attach_evidence(summary), allow_nan=False)
    )
    import benchmarks.run_task037_extra_h2b as h2b

    timeline = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W14B_PHASE
    )
    expected_command = runner._m6b_w14b_worker_command(
        raw,
        runner.ROOT / runner.M6B_W6A_W5_COMPACT_RELATIVE_PATH,
        Path(raw_path),
        runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
        Path(target_path).parent,
        runner.ROOT / runner.M6B_W11A_M3Y_MANIFEST_RELATIVE_PATH,
        Path(jit["physical_source"]),
        Path(jit["b0_source"]),
        Path(authority["path"]),
        SOURCE_SHA,
    )
    watchdog = {
        "schema": runner.M6B_W14B_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W14B_PHASE,
        "status": "measurement_complete",
        "process": {
            "return_code": 0,
            "termination": None,
            "peak_rss_bytes": 100,
            "swap_bytes": 0,
        },
        "drain": {"gone": True},
        "source_at_start": _source(),
        "source_at_end": _source(),
        "source_end_clean": True,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W14B_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W14B_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W14B_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
        },
        "raw_dir": str(raw.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "command": expected_command,
        "w14a_compact_authority": authority,
        "artifact_inventory": {
            "raw": runner._m6b_w14b_raw_artifacts(raw),
            "watchdog": runner._m6b_w14b_watchdog_artifacts(watchdog_dir),
        },
        "worker_summary": runner._artifact(
            raw, runner.M6B_W14B_SUMMARY_FILENAME
        ),
        "timeline": timeline,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w14c_unlocked": False,
    }
    watchdog_path = watchdog_dir / runner.M6B_W14B_WATCHDOG_SUMMARY_FILENAME
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), allow_nan=False)
    )
    monkeypatch.setattr(runner, "_m6b_w14b_w14a_compact_authority", lambda _path: authority)
    monkeypatch.setattr(runner, "_m6b_w14a_jit_closeout_valid", lambda _value, _h2b: True)
    monkeypatch.setattr(h2b, "_light_source", lambda: _source())

    def fake_gate(**kwargs):
        rho4 = kwargs["samples"]["4"]["true_relative_residual"]
        checks = {
            name: True
            for name in (
                "w14a_authority", "outer", "checkpoints", "inner",
                "action_audit", "architecture", "lifecycle", "prediction",
                "rho1_anchor", "rho_monotone", "rho4", "source", "cache",
            )
        }
        checks["rho4"] = rho4 <= 0.75
        return {"pass": all(checks.values()), "checks": checks, "problems": [], "rho": {}}

    monkeypatch.setattr(w14_core, "evaluate_w14b_fixed4_gate", fake_gate)
    return raw, watchdog_dir, watchdog_path, summary, watchdog


def _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog):
    summary_path = raw / runner.M6B_W14B_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), allow_nan=False)
    )
    watchdog["worker_summary"] = runner._artifact(
        raw, runner.M6B_W14B_SUMMARY_FILENAME
    )
    watchdog["artifact_inventory"]["raw"] = runner._m6b_w14b_raw_artifacts(raw)
    watchdog["artifact_inventory"]["watchdog"] = (
        runner._m6b_w14b_watchdog_artifacts(watchdog_dir)
    )
    watchdog["timeline"] = runner._m6b_w8a_timeline_valid(
        watchdog_dir / f"{runner.M6B_W14B_PHASE}_timeline.jsonl",
        phase=runner.M6B_W14B_PHASE,
    )
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), allow_nan=False)
    )


def _synthetic_gate_report(rho4_pass):
    checks = {
        name: True
        for name in (
            "w14a_authority", "outer", "checkpoints", "inner",
            "action_audit", "architecture", "lifecycle", "prediction",
            "rho1_anchor", "rho_monotone", "rho4", "source", "cache",
        )
    }
    checks["rho4"] = bool(rho4_pass)
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": [] if rho4_pass else ["rho4"],
        "rho": {},
    }


def test_w14b_parser_command_and_marker_contract():
    args = [
        "m6b-w14b-watchdog", "--run-dir", "run", "--watchdog-dir", "watchdog",
        "--w5-compact", "w5", "--w5-raw-dir", "w5raw", "--w7-compact", "w7",
        "--w7-raw-dir", "w7raw", "--m3y-manifest", "m3y", "--jit-cache-source", "jit",
        "--b0-jit-cache-source", "b0", "--w14a-compact", "w14a", "--expected-source-sha", SOURCE_SHA,
    ]
    parsed = runner._parser().parse_args(args)
    assert parsed.command == "m6b-w14b-watchdog"
    assert parsed.w14a_compact == "w14a"
    assert runner.M6B_W14B_EVENTS[0] == "authority_validated"
    assert runner.M6B_W14B_EVENTS[-1] == "summary_ready"
    assert len(runner.M6B_W14B_EVENTS) == 15


def test_w14b_main_dispatches_watchdog_and_check_without_running_worker(
    monkeypatch,
):
    calls = []
    watchdog_args = [
        "m6b-w14b-watchdog", "--run-dir", "run", "--watchdog-dir", "watchdog",
        "--w5-compact", "w5", "--w5-raw-dir", "w5raw", "--w7-compact", "w7",
        "--w7-raw-dir", "w7raw", "--m3y-manifest", "m3y", "--jit-cache-source", "jit",
        "--b0-jit-cache-source", "b0", "--w14a-compact", "w14a",
        "--expected-source-sha", SOURCE_SHA,
    ]
    monkeypatch.setattr(
        runner,
        "_run_m6b_w14b_watchdog",
        lambda *args: calls.append(("watchdog", args)) or 17,
    )
    assert runner.main(watchdog_args) == 17
    check_args = [
        "m6b-w14b-check", "--raw-dir", "raw", "--watchdog-summary", "watchdog.json",
        "--output", "formal.json", "--expected-source-sha", SOURCE_SHA,
    ]
    monkeypatch.setattr(
        runner,
        "_run_m6b_w14b_check",
        lambda *args: calls.append(("check", args)) or 18,
    )
    assert runner.main(check_args) == 18
    assert [name for name, _args in calls] == ["watchdog", "check"]


def test_w14b_progress_malformed_record_fails_closed(tmp_path):
    path = tmp_path / "progress.jsonl"
    path.write_text("null\n")
    result = runner._m6b_w14b_progress_valid(path)
    assert result["pass"] is False


def test_w14b_formal_pass_compact_is_scalar_hash_only(tmp_path, monkeypatch):
    raw, watchdog_dir, watchdog_path, _summary, _watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    output = tmp_path / "formal.json"
    assert runner._run_m6b_w14b_check(raw, watchdog_path, output, SOURCE_SHA) == 0
    result = json.loads(output.read_text())
    assert result["classification"] == "W14B_FORMAL_RESOURCE_CLOSEOUT_PASS"
    assert result["formal_pass"] is True
    assert result["w14c_unlocked"] is True
    assert result["pde_pass"] is False
    assert "records" not in result["timeline"]
    assert all("values" not in item for item in result["checkpoint_artifacts"])
    assert watchdog_dir.is_dir()


def test_w14b_checkpoint_tamper_and_resource_fail_closed(tmp_path, monkeypatch):
    raw, _watchdog_dir, watchdog_path, _summary, _watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    checkpoint = raw / "outer_checkpoints/m6b_iter4_residual.npy"
    values = np.load(checkpoint, allow_pickle=False)
    values[0] = 0.6 + 0.0j
    np.save(checkpoint, values, allow_pickle=False)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    assert gate["checks"]["checkpoint_artifacts"] is False


def test_w14b_resource_peak_and_compiler_fail_closed(tmp_path, monkeypatch):
    raw, watchdog_dir, watchdog_path, _summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    watchdog["process"]["peak_rss_bytes"] = runner.M6B_W14B_FORMAL_RSS_LIMIT_BYTES
    timeline = watchdog_dir / f"{runner.M6B_W14B_PHASE}_timeline.jsonl"
    timeline.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W14B_PHASE,
                "rss_bytes": runner.M6B_W14B_FORMAL_RSS_LIMIT_BYTES,
                "swap_bytes": 0,
                "compiler_descendant_pids": [123],
            }
        )
        + "\n"
    )
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, _summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    assert gate["checks"]["resource"] is False
    assert gate["classification"] == "W14B_RESOURCE_FAIL"


def test_w14b_worker_status_does_not_override_independent_gate(tmp_path, monkeypatch):
    raw, _watchdog_dir, watchdog_path, summary, _watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    summary["status"] = "gate_failed"
    summary["w14b_pass"] = False
    (raw / runner.M6B_W14B_SUMMARY_FILENAME).write_text(
        json.dumps(runner._attach_evidence(summary), allow_nan=False)
    )
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    assert gate["checks"]["worker_semantics"] is False


@pytest.mark.parametrize("tamper", ("scratch_path", "v_count", "z_count"))
def test_w14b_scratch_audit_contract_tamper_fails(
    tmp_path, monkeypatch, tamper
):
    raw, watchdog_dir, watchdog_path, summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    outer = summary["core"]["outer_audit"]
    if tamper == "scratch_path":
        outer["scratch_paths"]["v_basis"] = "wrong/v_basis.bin"
    elif tamper == "v_count":
        outer["v_basis"]["read_count"] = 19
    else:
        outer["z_basis"]["write_count"] = 3
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    assert gate["checks"]["scratch"] is False


@pytest.mark.parametrize("name", ("v_basis.bin", "z_basis.bin"))
def test_w14b_scratch_file_size_or_hash_tamper_fails(
    tmp_path, monkeypatch, name
):
    raw, _watchdog_dir, watchdog_path, _summary, _watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    path = raw / "outer_scratch" / name
    if name == "v_basis.bin":
        path.write_bytes(b"x" * (path.stat().st_size - 1))
    else:
        values = bytearray(path.read_bytes())
        values[0] ^= 1
        path.write_bytes(values)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    assert gate["checks"]["artifacts"] is False


@pytest.mark.parametrize(
    "tamper,expected_classification",
    (
        ("swap", "W14B_RESOURCE_FAIL"),
        ("source", "W14B_EXECUTION_OR_EVIDENCE_FAIL"),
        ("return_code_bool", "W14B_EXECUTION_OR_EVIDENCE_FAIL"),
        ("swap_float", "W14B_EXECUTION_OR_EVIDENCE_FAIL"),
    ),
)
def test_w14b_swap_or_source_failure_is_bound_separately(
    tmp_path, monkeypatch, tamper, expected_classification
):
    raw, watchdog_dir, watchdog_path, summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    if tamper == "swap":
        watchdog["process"]["swap_bytes"] = 1
    elif tamper == "source":
        watchdog["source_at_end"]["source_commit_full_sha"] = "b" * 40
    elif tamper == "return_code_bool":
        watchdog["process"]["return_code"] = False
    else:
        watchdog["process"]["swap_bytes"] = 0.0
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    if tamper == "swap":
        assert gate["checks"]["resource"] is False
    elif tamper == "source":
        assert gate["checks"]["watchdog_evidence"] is False
    elif tamper == "return_code_bool":
        assert gate["checks"]["execution_semantics"] is False
    else:
        assert gate["checks"]["resource"] is False
    assert gate["classification"] == expected_classification


def test_w14b_watchdog_w14a_authority_tamper_is_evidence_failure(
    tmp_path, monkeypatch
):
    raw, watchdog_dir, watchdog_path, summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    watchdog["w14a_compact_authority"] = {"tampered": True}
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["pass"] is False
    assert gate["checks"]["watchdog_evidence"] is False
    assert gate["classification"] == "W14B_EXECUTION_OR_EVIDENCE_FAIL"


def test_w14b_honest_numeric_fail_has_rc1_and_numeric_classification(
    tmp_path, monkeypatch
):
    raw, watchdog_dir, watchdog_path, summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        w14_core,
        "evaluate_w14b_fixed4_gate",
        lambda **_kwargs: _synthetic_gate_report(False),
    )
    summary.update(
        {
            "status": "gate_failed",
            "classification": "W14B_FIXED4_CORRECTION_FAIL",
            "w14b_pass": False,
            "formal_resource_closeout_pending": False,
            "w14c_locked": True,
        }
    )
    watchdog["process"]["return_code"] = 1
    watchdog["status"] = "gate_failed"
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["checks"]["worker_action_gate"] is False
    assert gate["checks"]["worker_semantics"] is True
    assert gate["checks"]["execution_semantics"] is True
    assert gate["checks"]["resource"] is True
    assert gate["classification"] == "W14B_FIXED4_CORRECTION_FAIL"


@pytest.mark.parametrize("independent_pass,self_report_fail", ((False, False), (True, True)))
def test_w14b_self_report_mismatch_is_evidence_failure(
    tmp_path, monkeypatch, independent_pass, self_report_fail
):
    raw, watchdog_dir, watchdog_path, summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        w14_core,
        "evaluate_w14b_fixed4_gate",
        lambda **_kwargs: _synthetic_gate_report(independent_pass),
    )
    if self_report_fail:
        summary.update(
            {
                "status": "gate_failed",
                "classification": "W14B_FIXED4_CORRECTION_FAIL",
                "w14b_pass": False,
                "formal_resource_closeout_pending": False,
                "w14c_locked": True,
            }
        )
        watchdog["process"]["return_code"] = 0
        watchdog["status"] = "measurement_complete"
    else:
        watchdog["process"]["return_code"] = 1
        watchdog["status"] = "gate_failed"
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["checks"]["worker_semantics"] is False
    assert gate["classification"] == "W14B_EXECUTION_OR_EVIDENCE_FAIL"


def test_w14b_missing_process_measurement_is_not_resource_failure(
    tmp_path, monkeypatch
):
    raw, watchdog_dir, watchdog_path, summary, watchdog = _make_fixture(
        tmp_path, monkeypatch
    )
    del watchdog["process"]["peak_rss_bytes"]
    _refresh_fixture_evidence(raw, watchdog_dir, watchdog_path, summary, watchdog)
    gate = runner._m6b_w14b_formal_gate(raw, watchdog_path, SOURCE_SHA)
    assert gate["checks"]["resource"] is False
    assert gate["classification"] == "W14B_EXECUTION_OR_EVIDENCE_FAIL"
