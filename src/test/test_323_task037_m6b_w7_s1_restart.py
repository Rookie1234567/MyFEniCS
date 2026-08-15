from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.disk_backed_flexible_gmres import DiskBackedFlexibleGMRES


def _fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = 8
    matrix = np.diag(
        np.asarray(
            [1.4 + 0.03 * i + 1j * (0.2 + 0.01 * i) for i in range(rows)],
            dtype=np.complex128,
        )
    )
    matrix += np.diag(
        np.full(rows - 1, 0.11 - 0.04j, dtype=np.complex128), k=1
    )
    rhs = np.asarray(
        [1.0 + 0.07 * i + 1j * (-0.2 + 0.03 * i) for i in range(rows)],
        dtype=np.complex128,
    )
    initial = np.asarray(
        [0.2 - 0.01j * i for i in range(rows)], dtype=np.complex128
    )
    return matrix, rhs, initial


def _run_core(root: Path, initial: np.ndarray | None):
    matrix, rhs, _ = _fixture()

    def action(values):
        return np.asarray(matrix @ values, dtype=np.complex128)

    def pc(values):
        scale = (0.86 + 0.03j) + (0.08 - 0.02j) / (
            1.0 + np.linalg.norm(values)
        )
        return np.asarray(scale * values, dtype=np.complex128)

    result = DiskBackedFlexibleGMRES(
        action, pc, max_steps=6, checkpoints=(1, 3, 6)
    ).solve(rhs, scratch_dir=root, initial_solution=initial)
    return result


def test_w7_restart_core_keeps_zero_start_and_initial_solution_paths(tmp_path):
    _matrix, _rhs, initial = _fixture()
    zero = _run_core(tmp_path / "zero", None)
    continued = _run_core(tmp_path / "continued", initial)

    assert zero.audit["initial_solution_provided"] is False
    assert zero.audit["initial_action_count"] == 0
    assert zero.audit["action_count"] == 9
    assert continued.audit["initial_solution_provided"] is True
    assert continued.audit["initial_action_count"] == 1
    assert continued.audit["action_count"] == 10
    assert continued.audit["checkpoint_set_complete"] is True
    assert set(continued.checkpoints) == {"1", "3", "6"}

    repeat = _run_core(tmp_path / "repeat", initial)
    assert np.array_equal(continued.solution, repeat.solution)
    assert np.array_equal(continued.hessenberg, repeat.hessenberg)
    first_audit = deepcopy(continued.audit)
    second_audit = deepcopy(repeat.audit)
    for audit in (first_audit, second_audit):
        audit.pop("scratch_paths")
        audit["v_basis"].pop("path")
        audit["z_basis"].pop("path")
    assert first_audit == second_audit


def _w7_samples(values: tuple[float, float, float, float]) -> dict:
    return {
        str(local): {
            "iteration": local,
            "local_iteration": local,
            "cumulative_iteration": cumulative,
            "true_relative_residual": value,
            "estimated_residual_norm": value,
            "estimated_residual_is_diagnostic_only": True,
            "artifacts": {},
        }
        for local, cumulative, value in zip(
            runner.M6B_W7_S1_LOCAL_ITERATIONS,
            runner.M6B_W7_S1_CUMULATIVE_ITERATIONS,
            values,
        )
    }


def test_w7_local_cumulative_gate_only_hard_gates_cumulative400():
    samples = _w7_samples((0.30, 0.20, 0.075, 0.070))
    gate = runner._m6b_w7_s1_numeric_gate(samples)
    assert gate["pass"] is True
    assert gate["cumulative_true_residuals"]["400"] == 0.070
    assert gate["checks"]["improvement_350_to_400_ge_0.15"] is False
    assert "improvement_350_to_400_ge_0.15" not in gate["problems"]

    bad = deepcopy(samples)
    bad["200"]["true_relative_residual"] = 0.081
    bad_gate = runner._m6b_w7_s1_numeric_gate(bad)
    assert bad_gate["pass"] is False
    assert "cumulative400_true_residual" in bad_gate["problems"]

    nonmonotone = runner._m6b_w7_s1_numeric_gate(
        _w7_samples((0.30, 0.40, 0.075, 0.070))
    )
    assert nonmonotone["checks"]["monotone_nonincreasing"] is False
    assert nonmonotone["pass"] is True
    assert "non_monotone_residuals" not in nonmonotone["problems"]


def test_w7_frozen_w5_iter200_authority_and_hash_fail_closed(monkeypatch):
    compact = (
        runner.ROOT / runner.M6B_W7_S1_W5_COMPACT_RELATIVE_PATH
    ).resolve()
    raw = (
        runner.ROOT
        / "benchmarks/artifacts/task037_extra_development/"
        "m6b_w5_disk_fgmres_41cbbd4_screen_run1"
    ).resolve()
    authority = runner._m6b_w7_s1_load_w5_authority(compact, raw)
    assert authority["frozen_iteration"] == 200
    assert authority["initial_solution"].shape == (runner.M6B_GLOBAL_ROWS,)
    assert authority["frozen_rhs"].shape == (runner.M6B_GLOBAL_ROWS,)
    assert authority["frozen_outer_action"].shape == (runner.M6B_GLOBAL_ROWS,)
    assert authority["frozen_residual"].shape == (runner.M6B_GLOBAL_ROWS,)
    del (
        authority["initial_solution"],
        authority["frozen_rhs"],
        authority["frozen_outer_action"],
        authority["frozen_residual"],
    )

    monkeypatch.setattr(runner, "M6B_W7_S1_W5_COMPACT_FILE_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="compact authority"):
        runner._m6b_w7_s1_load_w5_authority(compact, raw)


def test_w7_parser_and_fixed_dispatch(monkeypatch, tmp_path):
    args = runner._parser().parse_args(
        [
            "m6b-w7-s1-screen",
            "--run-dir", str(tmp_path / "run"),
            "--factor-authority-dir", str(tmp_path / "factor"),
            "--wave-authority-dir", str(tmp_path / "wave"),
            "--jit-cache-source", str(tmp_path / "jit"),
            "--expected-source-sha", "a" * 40,
            "--w0-authority-file", str(tmp_path / "w0.json"),
            "--w5-compact", str(tmp_path / "w5.json"),
            "--w5-raw-dir", str(tmp_path / "w5raw"),
        ]
    )
    assert args.command == "m6b-w7-s1-screen"
    assert runner._m6b_w7_s1_scope()["checkpoint_axis"] == "local_cycle_iteration"
    assert runner._m6b_w7_s1_scope()["cumulative_checkpoint_iterations"] == [
        220, 300, 350, 400
    ]
    assert runner._m6b_w7_s1_predicted_live_set()["predicted_live_set_bytes"] == (
        1_666_871_296
    )
    assert runner.M6B_W7_S1_TIMEOUT_SECONDS == 10_800.0

    captured = {}

    def fake_authority(_compact, _raw):
        return {
            "compact": {"path": "frozen", "file_sha256": "a" * 64},
            "samples": {"200": {}},
            "frozen_iteration": 200,
            "initial_solution": np.ones(3, dtype=np.complex128),
            "frozen_rhs": np.ones(3, dtype=np.complex128),
            "frozen_outer_action": np.ones(3, dtype=np.complex128),
            "frozen_residual": np.ones(3, dtype=np.complex128),
        }

    def fake_worker(*_args, **kwargs):
        captured.update(kwargs)
        payload = kwargs["continuation_authority"]
        for key in ("frozen_rhs", "frozen_outer_action", "frozen_residual"):
            payload.pop(key)
        captured["payload_after_precheck"] = payload
        return 19

    monkeypatch.setattr(runner, "_m6b_w7_s1_load_w5_authority", fake_authority)
    monkeypatch.setattr(runner, "_run_m6b_w2_diagnostic", fake_worker)
    assert runner._run_m6b_w7_s1_screen(
        tmp_path / "run",
        tmp_path / "factor",
        tmp_path / "wave",
        tmp_path / "jit",
        "a" * 40,
        tmp_path / "w0.json",
        tmp_path / "w5.json",
        tmp_path / "w5raw",
    ) == 19
    assert captured["solver"] == "disk_fgmres_restart"
    assert captured["initial_solution"].shape == (3,)
    assert captured["payload_after_precheck"]["frozen_iteration"] == 200
    assert "frozen_rhs" not in captured["payload_after_precheck"]
    assert "frozen_outer_action" not in captured["payload_after_precheck"]
    assert "frozen_residual" not in captured["payload_after_precheck"]
    assert captured["projected"] is True
    assert captured["screen"] is True


def test_w7_restart_entry_guard_reaches_existing_run_check(tmp_path):
    run_dir = tmp_path / "existing"
    run_dir.mkdir()
    with pytest.raises(FileExistsError, match="existing run directory"):
        runner._run_m6b_w2_diagnostic(
            run_dir,
            tmp_path / "factor",
            tmp_path / "wave",
            tmp_path / "jit",
            "a" * 40,
            tmp_path / "w0.json",
            projected=True,
            screen=True,
            shifted_beta=runner.M6B_W5_BETA,
            solver="disk_fgmres_restart",
            initial_solution=np.ones(3, dtype=np.complex128),
            continuation_authority={},
        )


def test_w7_checkpoint_checker_rejects_wrong_file_hash(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    screen = {}
    rows = runner.M6B_GLOBAL_ROWS
    for iteration in runner.M6B_W7_S1_LOCAL_ITERATIONS:
        rhs = np.ones(rows, dtype=np.complex128)
        outer = np.zeros(rows, dtype=np.complex128)
        residual = rhs.copy()
        solution = np.zeros(rows, dtype=np.complex128)
        arrays = {
            "solution": solution,
            "outer_action": outer,
            "residual": residual,
            "rhs": rhs,
        }
        artifacts = {}
        for name, values in arrays.items():
            path = raw / f"m6b_iter{iteration}_{name}.npy"
            np.save(path, values, allow_pickle=False)
            file_artifact = runner._artifact(raw, path.name)
            artifacts[name] = {
                "path": file_artifact["path"],
                "bytes": file_artifact["bytes"],
                "sha256": file_artifact["sha256"],
                "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(values),
                "shape": [rows],
                "dtype": "complex128",
            }
        screen[str(iteration)] = {
            "iteration": iteration,
            "true_relative_residual": 1.0,
            "artifacts": artifacts,
        }
    assert runner._m6b_checkpoint_recompute(raw, screen)["pass"] is True
    screen["200"]["artifacts"]["rhs"]["sha256"] = "0" * 64
    assert runner._m6b_checkpoint_recompute(raw, screen)["pass"] is False


def test_w5_and_w7_timeline_artifact_key_contracts(tmp_path):
    line = '{"rss_bytes": 1, "swap_bytes": 0, "compiler_descendant_pids": []}\n'
    w5_name = "w5_disk_fgmres_screen_timeline.jsonl"
    w5_path = tmp_path / w5_name
    w5_path.write_text(line, encoding="utf-8")
    assert runner._m6b_w5_timeline_valid(
        {"artifacts": {w5_name: {"path": str(w5_path)}}},
        tmp_path,
        timeline_name=w5_name,
        expected_peak=None,
    )["pass"] is True

    w7_name = "w7_s1_restart_disk_fgmres_screen_timeline.jsonl"
    w7_path = tmp_path / w7_name
    w7_path.write_text(line, encoding="utf-8")
    assert runner._m6b_w5_timeline_valid(
        {"artifacts": {"timeline": {"path": str(w7_path)}}},
        tmp_path,
        timeline_name=w7_name,
        expected_peak=None,
        artifact_key="timeline",
    )["pass"] is True


def test_w7_checker_passes_samples_to_all_recompute_paths(monkeypatch, tmp_path):
    samples = _w7_samples((0.30, 0.20, 0.10, 0.09))
    compact = {"path": "frozen", "file_sha256": "a" * 64}
    continuation_record = {
        "compact": compact,
        "frozen_iteration": 200,
        "initial_check": {
            "initial_solution_provided": True,
            "precheck_action_count": 2,
            "core_initial_action_count": 1,
            "rhs_equal_to_frozen_w5": True,
            "repeat_relative_error": 0.0,
            "frozen_action_relative_error": 0.0,
            "frozen_residual_relative_error": 0.0,
            "rho_absolute_error": 0.0,
        },
    }
    screen = {"samples": samples, "continuation_authority": continuation_record}
    worker = {
        "schema": runner.M6B_W7_S1_SCHEMA,
        "screen": screen,
        "scope": runner._m6b_w7_s1_scope(),
        "predicted_live_set": runner._m6b_w7_s1_predicted_live_set(),
        "source_at_start": {},
        "source_at_end": {},
        "diagnostic_numeric_pass": False,
        "w7_s1_pass": False,
        "formal_pass": False,
        "pde_pass": False,
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "dtn_matrix_free": True,
            "global_matrix": False,
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "schur": False,
        },
        "jit_cache": {
            "source_inventory_sha256": runner.M6B_W2_JIT_INVENTORY_SHA256,
            "source_before": "cache",
            "source_after": "cache",
            "source_final": "cache",
            "before": "cache",
            "after": "cache",
            "final": "cache",
            "unchanged": True,
        },
    }
    watchdog = {
        "artifacts": {},
        "schema": "task037.extra.m6b.w7-s1.watchdog.v1",
        "phase": runner.M6B_W7_S1_PHASE,
        "source_at_start": {},
        "source_at_end": {},
        "process": {
            "return_code": 1,
            "termination": None,
            "peak_rss_bytes": 1,
            "swap_bytes": 0,
        },
        "drain": {"gone": True},
        "resource_limits": {
            "timeout_seconds": runner.M6B_W7_S1_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
            "pde_strict_peak_bytes": 2_000_000_000,
        },
        "monitor_error": None,
        "formal_pass": False,
        "pde_pass": False,
    }
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for name in runner.M6B_W7_S1_RAW_ARTIFACT_NAMES:
        (raw_dir / name).write_bytes(b"")
    for name in runner.M6B_W7_S1_WATCHDOG_ARTIFACT_NAMES:
        (tmp_path / name).write_bytes(b"")

    def absolute_report(root, name):
        record = runner._artifact(root, name)
        record["path"] = str((root / name).resolve())
        return record

    watchdog["artifacts"] = {
        "worker_summary": absolute_report(raw_dir, "m6b_w7_s1_summary.json"),
        "progress": absolute_report(raw_dir, "m6b_w7_s1_progress.jsonl"),
        "root_pid": absolute_report(
            tmp_path, "w7_s1_restart_disk_fgmres_screen_root_pid.json"
        ),
        "stdout": absolute_report(
            tmp_path, "w7_s1_restart_disk_fgmres_screen_stdout.txt"
        ),
        "timeline": absolute_report(
            tmp_path, "w7_s1_restart_disk_fgmres_screen_timeline.jsonl"
        ),
    }
    continuation = {
        "compact": compact,
        "initial_solution": np.ones(1, dtype=np.complex128),
        "frozen_rhs": np.ones(1, dtype=np.complex128),
        "frozen_outer_action": np.ones(1, dtype=np.complex128),
        "frozen_residual": np.ones(1, dtype=np.complex128),
    }
    seen = {}
    monkeypatch.setattr(
        runner,
        "_read_json",
        lambda path: worker if path.name == "m6b_w7_s1_summary.json" else watchdog,
    )
    monkeypatch.setattr(runner, "_m6b_w7_s1_load_w5_authority", lambda *_: continuation)
    monkeypatch.setattr(runner, "_evidence_valid", lambda *_: True)
    monkeypatch.setattr(runner, "_m6b_w2_source_identity_valid", lambda *_: True)
    monkeypatch.setattr(runner, "_m6b_w7_s1_screen_metadata_valid", lambda *_: True)
    monkeypatch.setattr(runner, "_m6b_w2_cache_record", lambda *_: "cache")

    def capture_recompute(_path, value):
        seen["recompute"] = value
        return {
            "pass": True,
            "residuals": {str(i): 0.1 for i in runner.M6B_SCREEN_ITERATIONS},
        }

    def capture_numeric(value, **_):
        seen["numeric"] = value
        return {"pass": True, "problems": []}

    def capture_progress(_path, value):
        seen["progress"] = value
        return {"pass": True}

    monkeypatch.setattr(runner, "_m6b_checkpoint_recompute", capture_recompute)
    monkeypatch.setattr(runner, "_m6b_w7_s1_numeric_gate", capture_numeric)
    monkeypatch.setattr(runner, "_m6b_w7_s1_progress_valid", capture_progress)
    monkeypatch.setattr(runner, "_m6b_w5_timeline_valid", lambda *_args, **_kwargs: {"pass": True, "peak_rss_bytes": 1, "swap_bytes": 0, "compiler_descendant_pids": [], "records": 1})
    monkeypatch.setattr(runner, "_m6b_w7_s1_artifact_inventory_valid", lambda *_: True)
    monkeypatch.setattr(runner, "_attach_evidence", lambda value: value)
    monkeypatch.setattr(runner, "_write_json", lambda _path, value: seen.setdefault("result", value))
    result_code = runner._m6b_w7_s1_check_command(
        tmp_path / "raw",
        tmp_path / "watchdog.json",
        tmp_path / "w5.json",
        tmp_path / "w5raw",
        tmp_path / "jit",
        tmp_path / "check.json",
        "a" * 40,
    )
    assert result_code in (0, 1)
    assert seen["recompute"] is samples
    assert seen["numeric"] is samples
    assert seen["progress"] is screen
    assert seen["result"]["artifact_inventory"]["watchdog"][
        "w7_s1_restart_disk_fgmres_screen_timeline.jsonl"
    ]["path"] == "w7_s1_restart_disk_fgmres_screen_timeline.jsonl"
