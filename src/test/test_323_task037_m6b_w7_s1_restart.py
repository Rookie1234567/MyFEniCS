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
    del authority["initial_solution"], authority["frozen_rhs"]

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

    captured = {}

    def fake_authority(_compact, _raw):
        return {
            "compact": {"path": "frozen", "file_sha256": "a" * 64},
            "samples": {"200": {}},
            "frozen_iteration": 200,
            "initial_solution": np.ones(3, dtype=np.complex128),
            "frozen_rhs": np.ones(3, dtype=np.complex128),
        }

    def fake_worker(*_args, **kwargs):
        captured.update(kwargs)
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
    assert captured["continuation_rhs"].shape == (3,)
    assert captured["projected"] is True
    assert captured["screen"] is True


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
