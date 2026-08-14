from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
    M6B_W5_SCHEMA as M6B_W5_CORE_SCHEMA,
    run_m6b_disk_backed_right_fgmres_screen,
)


def _fixture() -> tuple[np.ndarray, np.ndarray]:
    rows = 220
    matrix = np.diag(
        np.asarray(
            [1.2 + 0.009 * index + 1j * (0.17 + 0.003 * index) for index in range(rows)],
            dtype=np.complex128,
        )
    )
    matrix += np.diag(
        np.full(rows - 1, 0.07 - 0.02j, dtype=np.complex128), k=1
    )
    matrix += np.diag(
        np.full(rows - 2, -0.04 + 0.03j, dtype=np.complex128), k=2
    )
    rhs = np.asarray(
        [1.0 + 0.011 * index + 1j * (-0.2 + 0.007 * index) for index in range(rows)],
        dtype=np.complex128,
    )
    return matrix, rhs


def _run(root: Path, matrix: np.ndarray, rhs: np.ndarray) -> dict:
    root.mkdir()
    return run_m6b_disk_backed_right_fgmres_screen(
        lambda values: matrix @ values,
        lambda values: ((0.83 + 0.04j) + (0.12 - 0.03j) / (1.0 + np.linalg.norm(values)))
        * values,
        rhs,
        checkpoint_dir=root / "checkpoints",
        scratch_dir=root / "scratch",
    )


def test_w5_disk_screen_writes_true_residuals_and_repeats(tmp_path):
    matrix, rhs = _fixture()
    first = _run(tmp_path / "first", matrix, rhs)
    second = _run(tmp_path / "second", matrix, rhs)

    assert first["schema"] == second["schema"] == M6B_W5_CORE_SCHEMA
    assert runner.M6B_W5_SCHEMA != runner.M6B_W5_CORE_SCHEMA
    assert first["iterations"] == second["iterations"] == 200
    assert first["happy_breakdown"] is second["happy_breakdown"] is False
    assert first["action_count"] == second["action_count"] == 204
    assert first["pc_count"] == second["pc_count"] == 200
    assert first["core_audit"]["v_basis"]["read_count"] == 40200
    assert first["core_audit"]["z_basis"]["read_count"] == 470
    assert first["core_audit"]["mmap"] is False
    assert first["core_audit"]["basis_in_memory"] is False
    assert first["core_audit"]["bounded_full_vector_bytes"] <= 64 * 1024 * 1024
    assert first["scratch"]["bytes"] == (201 + 200) * rhs.size * 16
    assert set(first["samples"]) == {"20", "100", "150", "200"}
    assert set(first["samples"]) == set(second["samples"])
    for key in first["samples"]:
        first_sample = first["samples"][key]
        second_sample = second["samples"][key]
        assert first_sample["true_relative_residual"] == second_sample[
            "true_relative_residual"
        ]
        for name, artifact in first_sample["artifacts"].items():
            first_values = np.load(
                tmp_path / "first" / "checkpoints" / artifact["path"],
                allow_pickle=False,
            )
            second_values = np.load(
                tmp_path / "second" / "checkpoints" / second_sample["artifacts"][name]["path"],
                allow_pickle=False,
            )
            assert np.array_equal(first_values, second_values)
            assert first_values.dtype == np.dtype(np.complex128)
        artifacts = first_sample["artifacts"]
        rhs_values = np.load(
            tmp_path / "first" / "checkpoints" / artifacts["rhs"]["path"],
            allow_pickle=False,
        )
        outer_values = np.load(
            tmp_path / "first" / "checkpoints" / artifacts["outer_action"]["path"],
            allow_pickle=False,
        )
        residual_values = np.load(
            tmp_path / "first" / "checkpoints" / artifacts["residual"]["path"],
            allow_pickle=False,
        )
        assert np.array_equal(residual_values, rhs_values - outer_values)
        assert first_sample["true_relative_residual"] == (
            np.linalg.norm(residual_values)
            / max(np.linalg.norm(rhs_values), np.finfo(float).tiny)
        )
        assert first_sample["estimated_residual_is_diagnostic_only"] is True


def test_w5_parser_scope_and_fixed_dispatch(tmp_path, monkeypatch):
    args = runner._parser().parse_args(
        [
            "m6b-w5-disk-fgmres-screen",
            "--run-dir",
            str(tmp_path / "run"),
            "--factor-authority-dir",
            str(tmp_path / "factor"),
            "--wave-authority-dir",
            str(tmp_path / "wave"),
            "--jit-cache-source",
            str(tmp_path / "jit"),
            "--expected-source-sha",
            "a" * 40,
            "--w0-authority-file",
            str(tmp_path / "w0.json"),
        ]
    )
    assert args.command == "m6b-w5-disk-fgmres-screen"
    scope = runner._m6b_w5_scope()
    assert scope["solver"] == "disk_fgmres"
    assert scope["beta"] == 1.0
    assert scope["petsc_ksp_used"] is False
    assert scope["checkpoint_axis"] == "krylov_iteration"
    assert scope["augmented_matrix"] is False
    assert scope["factor_count"] == runner.M6B_FACTOR_COUNT
    assert scope["factor_reuse_count"] == runner.M6B_FACTOR_REUSE
    assert runner._m6b_w5_predicted_live_set()["predicted_live_set_bytes"] == 1_666_871_296

    captured = {}

    def fake_worker(*args, **kwargs):
        captured.update(kwargs)
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w2_diagnostic", fake_worker)
    assert runner._run_m6b_w5_disk_fgmres_screen(
        tmp_path / "run",
        tmp_path / "factor",
        tmp_path / "wave",
        tmp_path / "jit",
        "a" * 40,
        tmp_path / "w0.json",
    ) == 17
    assert captured == {
        "projected": True,
        "screen": True,
        "shifted_beta": 1.0,
        "solver": "disk_fgmres",
    }


def _production_metadata() -> dict:
    artifact = {
        "path": "m6b_iter20_solution.npy",
        "bytes": 1,
        "sha256": "a" * 64,
        "array_sha256": "b" * 64,
    }
    samples = {
        str(iteration): {
            "iteration": iteration,
            "true_relative_residual": 0.1,
            "estimated_residual_norm": 0.2,
            "estimated_residual_is_diagnostic_only": True,
            "artifacts": {
                name: dict(artifact, path=f"m6b_iter{iteration}_{name}.npy")
                for name in ("solution", "outer_action", "residual", "rhs")
            },
        }
        for iteration in (20, 100, 150, 200)
    }
    core = {
        "algorithm": "right_flexible_gmres",
        "rows": runner.M6B_GLOBAL_ROWS,
        "dtype": "complex128",
        "action_count": 204,
        "pc_count": 200,
        "initial_action_count": 0,
        "orthogonalization_passes": 2,
        "happy_breakdown": False,
        "retained_full_vector_count": 1,
        "iterations": 200,
        "checkpoint_set_complete": True,
        "checkpoint_count": 4,
        "bounded_full_vector_bytes": 33_000_000,
        "bounded_full_vector_gate": True,
        "mmap": False,
        "basis_in_memory": False,
        "scratch_bytes": runner.M6B_W5_SCRATCH_BYTES,
        "v_basis": {
            "rows": runner.M6B_GLOBAL_ROWS,
            "dtype": "complex128",
            "capacity": 201,
            "written_count": 201,
            "read_count": 40200,
            "write_count": 201,
            "allocated_bytes": 558_947_232,
            "mmap": False,
        },
        "z_basis": {
            "rows": runner.M6B_GLOBAL_ROWS,
            "dtype": "complex128",
            "capacity": 200,
            "written_count": 200,
            "read_count": 470,
            "write_count": 200,
            "allocated_bytes": 556_166_400,
            "mmap": False,
        },
    }
    return {
        "schema": runner.M6B_W5_CORE_SCHEMA,
        "rows": runner.M6B_GLOBAL_ROWS,
        "solver": "disk_backed_flexible_gmres",
        "petsc_ksp_used": False,
        "side": "right",
        "two_pass_mgs": True,
        "cycle": "fixed_one_200_step_cycle",
        "max_steps": 200,
        "iterations": 200,
        "checkpoint_iterations": [20, 100, 150, 200],
        "true_residual_authority": "rhs-outer_action",
        "estimated_residual_is_diagnostic_only": True,
        "happy_breakdown": False,
        "samples": samples,
        "numeric_gate": {"pass": False, "problems": []},
        "core_audit": core,
        "scratch": {
            "bytes": runner.M6B_W5_SCRATCH_BYTES,
            "mmap": False,
            "basis_in_memory": False,
        },
        "action_count": 204,
        "pc_count": 200,
        "read_write_counts": {
            "v_basis": {"read_count": 40200, "write_count": 201},
            "z_basis": {"read_count": 470, "write_count": 200},
        },
    }


def test_w5_metadata_validator_requires_fixed_production_shape():
    valid = _production_metadata()
    assert runner._m6b_w5_screen_metadata_valid(valid) is True
    missing = deepcopy(valid)
    del missing["core_audit"]["v_basis"]["read_count"]
    assert runner._m6b_w5_screen_metadata_valid(missing) is False
