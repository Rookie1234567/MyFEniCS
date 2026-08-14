from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
from petsc4py import PETSc

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
    M6B_W4_KSP_ITERATIONS,
    M6B_W4_PC_APPLY_BUDGETS,
    evaluate_m6b_numeric_screen_gate,
    run_m6b_right_fbcgs_screen,
)


def _fixture() -> tuple[PETSc.Mat, PETSc.Vec, np.ndarray]:
    rows = 256
    matrix_values = np.zeros((rows, rows), dtype=np.complex128)
    for row in range(rows):
        matrix_values[row, row] = 2.6 + 0.11j + 0.013 * row
        matrix_values[row, (row + 1) % rows] = 0.21 - 0.07j
        matrix_values[row, (row + 2) % rows] = -0.13 + 0.09j
        matrix_values[row, (row + 3) % rows] = 0.08 + 0.04j
        matrix_values[row, (row - 1) % rows] = -0.10 + 0.05j
    rhs_values = np.asarray(
        [
            (1.0 + 0.03 * row) + 1j * (-0.4 + 0.02 * row)
            for row in range(rows)
        ],
        dtype=np.complex128,
    )
    matrix = PETSc.Mat().createDense(
        [rows, rows], comm=PETSc.COMM_SELF
    )
    matrix.setUp()
    ids = np.arange(rows, dtype=PETSc.IntType)
    matrix.setValues(ids, ids, matrix_values)
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.getArray()[:] = rhs_values
    return matrix, rhs, matrix_values


class _StatelessPC:
    def __init__(self) -> None:
        self.apply_count = 0

    def apply(
        self,
        _pc: PETSc.PC,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        source_values = source.getArray(readonly=True)
        factor = 0.96 + 0.02 / (1.0 + np.linalg.norm(source_values))
        self.apply_count += 1
        target.getArray()[:] = factor * source_values


def test_m6b_w4_parser_scope_and_fixed_dispatch(tmp_path, monkeypatch):
    args = runner._parser().parse_args(
        [
            "m6b-w4-fbcgs-screen",
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
    assert args.command == "m6b-w4-fbcgs-screen"
    scope = runner._m6b_w4_scope()
    assert scope["solver"] == "fbcgs"
    assert scope["beta"] == 1.0
    assert scope["checkpoint_axis"] == "pc_apply_budget"
    assert scope["monitor_solution_source"] == "direct_ksp_solution_vec"
    assert scope["buildSolution"] is False
    assert scope["augmented_matrix"] is False
    assert scope["explicit_C_materialized_count"] == 0
    assert scope["explicit_D_materialized_count"] == 0
    assert scope["dtn_matrix_free"] is True
    assert scope["ksp_iteration_to_pc_apply_budget"] == {
        10: 20,
        50: 100,
        75: 150,
        100: 200,
    }
    assert scope["predicted_live_set"]["predicted_live_set_bytes"] == 1_723_301_083

    captured = {}

    def fake_worker(*args, **kwargs):
        captured.update(kwargs)
        return 23

    monkeypatch.setattr(runner, "_run_m6b_w2_diagnostic", fake_worker)
    assert runner._run_m6b_w4_fbcgs_screen(
        tmp_path / "run",
        tmp_path / "factor",
        tmp_path / "wave",
        tmp_path / "jit",
        "a" * 40,
        tmp_path / "w0.json",
    ) == 23
    assert captured == {
        "projected": True,
        "screen": True,
        "shifted_beta": 1.0,
        "solver": "fbcgs",
    }


def test_m6b_w4_direct_x_writer_and_apply_budget_contract(tmp_path):
    matrix, rhs, _matrix_values = _fixture()
    pc = _StatelessPC()
    try:
        result = run_m6b_right_fbcgs_screen(
            matrix,
            rhs,
            pc_context=pc,
            checkpoint_dir=Path(tmp_path),
        )
        assert result["schema"] == "task037.extra.h2b.m6b.fbcgs-screen.v1"
        assert result["ksp_type"] == "fbcgs"
        assert result["pc_side"] == "right"
        assert result["norm_type"] == "unpreconditioned"
        assert result["max_it"] == result["iterations"] == M6B_W4_KSP_ITERATIONS[-1]
        assert result["rtol"] == result["atol"] == 0.0
        assert result["checkpoint_axis"] == "pc_apply_budget"
        assert result["monitor_solution_source"] == "direct_ksp_solution_vec"
        assert result["buildSolution_called"] is False
        assert result["monitor_extra_pc_applies"] == 0
        assert result["pc_apply_count"] == result["pc_apply_count_expected"] == 200
        assert result["pc_apply_count_closed"] is True
        assert result["checkpoint_operator_apply_count"] == 4
        assert result["operator_apply_count"] is None
        assert result["breakdown"] is False
        assert set(result["samples"]) == {"20", "100", "150", "200"}
        for ksp_iteration, budget in zip(
            M6B_W4_KSP_ITERATIONS, M6B_W4_PC_APPLY_BUDGETS
        ):
            sample = result["samples"][str(budget)]
            assert sample["iteration"] == budget
            assert sample["ksp_iteration"] == ksp_iteration
            assert sample["pc_apply_budget"] == budget
            assert sample["iteration_label_is_pc_apply_budget"] is True
            assert sample["reported_residual_is_diagnostic_only"] is True
            assert sample["pc_apply_count"] == budget
            assert np.isfinite(sample["true_relative_residual"])
            for artifact in sample["artifacts"].values():
                values = np.load(
                    Path(tmp_path) / artifact["path"], allow_pickle=False
                )
                assert values.dtype == np.dtype(np.complex128)
                assert values.shape == (256,)
                assert np.all(np.isfinite(values))
            residual = np.load(
                Path(tmp_path) / sample["artifacts"]["residual"]["path"],
                allow_pickle=False,
            )
            rhs_values = np.load(
                Path(tmp_path) / sample["artifacts"]["rhs"]["path"],
                allow_pickle=False,
            )
            outer_values = np.load(
                Path(tmp_path) / sample["artifacts"]["outer_action"]["path"],
                allow_pickle=False,
            )
            assert np.array_equal(residual, rhs_values - outer_values)
        assert ".buildSolution" not in inspect.getsource(
            run_m6b_right_fbcgs_screen
        )
    finally:
        rhs.destroy()
        matrix.destroy()


def test_m6b_w4_metadata_and_numeric_gates_fail_closed():
    valid = {
        str(budget): {
            "iteration": budget,
            "ksp_iteration": ksp_iteration,
            "pc_apply_budget": budget,
            "checkpoint_axis": "pc_apply_budget",
            "iteration_label_is_pc_apply_budget": True,
            "true_relative_residual": 0.1,
            "reported_residual_is_diagnostic_only": True,
            "pc_apply_count": budget,
            "artifacts": {},
        }
        for ksp_iteration, budget in zip(
            M6B_W4_KSP_ITERATIONS, M6B_W4_PC_APPLY_BUDGETS
        )
    }
    screen = {
        "schema": "task037.extra.h2b.m6b.fbcgs-screen.v1",
        "rows": runner.M6B_GLOBAL_ROWS,
        "ksp_type": "fbcgs",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "max_it": M6B_W4_KSP_ITERATIONS[-1],
        "max_it_actual": M6B_W4_KSP_ITERATIONS[-1],
        "iterations": M6B_W4_KSP_ITERATIONS[-1],
        "rtol": 0.0,
        "atol": 0.0,
        "fixed_screen": True,
        "checkpoint_axis": "pc_apply_budget",
        "monitor_solution_source": "direct_ksp_solution_vec",
        "buildSolution_called": False,
        "monitor_extra_pc_applies": 0,
        "pc_apply_count": 200,
        "pc_apply_count_expected": 200,
        "pc_apply_count_closed": True,
        "breakdown": False,
        "converged_reason": -3,
        "converged_reason_names": ["DIVERGED_ITS"],
        "breakdown_reason_names": [],
        "checkpoint_operator_apply_count": 4,
        "operator_apply_count": None,
        "sample_action_count": 4,
        "samples": valid,
    }
    assert runner._m6b_w4_screen_metadata_valid(screen) is True
    missing = dict(screen, samples={key: value for key, value in valid.items() if key != "100"})
    assert runner._m6b_w4_screen_metadata_valid(missing) is False
    count_tampered = dict(screen, pc_apply_count=198)
    assert runner._m6b_w4_screen_metadata_valid(count_tampered) is False
    breakdown = dict(screen, breakdown=True)
    assert runner._m6b_w4_screen_metadata_valid(breakdown) is False

    numeric = {
        "20": {"true_relative_residual": 0.5, "reported_residual": 1.0},
        "100": {"true_relative_residual": 0.1, "reported_residual": 1.0},
        "150": {"true_relative_residual": 0.2, "reported_residual": 1.0},
        "200": {"true_relative_residual": 0.05, "reported_residual": 1.0},
    }
    assert evaluate_m6b_numeric_screen_gate(numeric)["pass"] is True
    numeric["200"]["reported_residual"] = 1.0e9
    assert evaluate_m6b_numeric_screen_gate(numeric)["pass"] is True
    del numeric["150"]
    assert evaluate_m6b_numeric_screen_gate(numeric)["pass"] is False
