"""Residual schema/callback checks with fake PETSc; no mesh, FE or solve."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.solvers.physical_retained_fgmres import run_retained_fgmres


class _Vector:
    def __init__(self, values=(1.0, 1.0)):
        self.values = np.asarray(values, dtype=np.complex128)

    def getLocalSize(self):
        return self.values.size

    getSize = getLocalSize

    def getComm(self):
        return None

    def set(self, value):
        self.values.fill(value)

    def duplicate(self):
        return _Vector(np.zeros_like(self.values))

    def copy(self, target=None):
        if target is None:
            return _Vector(self.values.copy())
        target.values[:] = self.values

    def norm(self):
        return float(np.linalg.norm(self.values))

    def axpy(self, coefficient, other):
        self.values += coefficient * other.values

    def destroy(self):
        pass


def _fake_run(monkeypatch, key, *, value=1e-3, extra_facts=None):
    rhs = _Vector()
    operator = Mock()
    operator.createVecRight.side_effect = rhs.duplicate
    ksp = Mock()
    ksp.create.return_value = ksp
    matrix_factory = Mock()
    matrix_factory.createPython.return_value = operator
    reason = SimpleNamespace(
        DIVERGED_NANORINF=-9, DIVERGED_MAX_IT=-3,
        DIVERGED_BREAKDOWN=-5, CONVERGED_RTOL=2,
    )
    petsc = SimpleNamespace(
        Mat=Mock(return_value=matrix_factory),
        KSP=Mock(return_value=ksp),
        PC=SimpleNamespace(Side=SimpleNamespace(RIGHT="right"),
                           Type=SimpleNamespace(PYTHON="python")),
    )
    petsc.KSP.ConvergedReason = reason
    petsc.KSP.NormType = SimpleNamespace(UNPRECONDITIONED="unpreconditioned")
    monkeypatch.setitem(sys.modules, "petsc4py", SimpleNamespace(PETSc=petsc))
    monkeypatch.setitem(
        sys.modules, "src.solvers.fullspace_memory_first_krylov",
        SimpleNamespace(
            _ActionContext=lambda _: SimpleNamespace(matvec_count=0),
            _PCContext=lambda _: SimpleNamespace(apply_count=0),
        ),
    )
    state = {"iteration": 0, "reason": 0}

    def fake_solve(_rhs, solution):
        callback = ksp.setConvergenceTest.call_args.args[0]
        # Supply callback events only: no linear system or FE model is solved.
        for iteration in (0, 8, 16):
            state["iteration"] = iteration
            ksp.buildSolution.side_effect = lambda target: solution.copy(target)
            state["reason"] = callback(ksp, iteration, 1.0)
            if state["reason"]:
                break

    ksp.solve.side_effect = fake_solve
    ksp.getIterationNumber.side_effect = lambda: state["iteration"]
    ksp.getConvergedReason.side_effect = lambda: state["reason"]
    ksp.getResidualNorm.return_value = 1.0
    events, checkpoints = [], []

    def evaluate(_target, _residual):
        return {
            key: 1.0 if state["iteration"] == 0 else value,
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 0.0,
            "schur_port_identity_relative": 0.0,
            **(extra_facts or {}),
        }

    result = run_retained_fgmres(
        rhs, lambda vector: vector.duplicate(), lambda vector: vector.copy(),
        evaluate=evaluate,
        checkpoint=lambda iteration, _vector, row: checkpoints.append((iteration, row)),
        append=lambda filename, row: events.append((filename, row)),
        seconds=lambda: float(state["iteration"]),
        planned_stop_iteration=16,
        **({"physical_residual_key": key} if key != "original_A6_relative" else {}),
    )
    return result, events, checkpoints, ksp


@pytest.mark.parametrize("key", ["original_A6_relative", "A6_n0_relative"])
def test_pilot_callbacks_keep_the_equation_identity_and_original_contract(monkeypatch, key):
    result, events, checkpoints, ksp = _fake_run(monkeypatch, key)
    assert result["status"] == "PILOT_COMPLETED_NOT_SOLVER_QUALIFICATION"
    assert result["iterations"] == 16
    assert result["final_true_residual"] == 1e-3
    rows = [row for name, row in events if name == "monitor_residuals.jsonl"]
    assert [row["iteration"] for row in rows] == [0, 8, 16, 16]
    assert [iteration for iteration, _ in checkpoints] == [0, 16]
    for row in rows:
        assert row["explicit_true_residual"] == row[key]
        assert not row["physical_residual_pass"]
        if key == "A6_n0_relative":
            assert "original_A6_relative" not in row
            assert row["operator_scope"] == "n0_filtered_dtn_not_full_dtn"
            assert row["physical_residual_key"] == key
        else:
            assert "A6_n0_relative" not in row
            assert "operator_scope" not in row
    if key == "A6_n0_relative":
        assert result["operator_scope"] == "n0_filtered_dtn_not_full_dtn"
    ksp.setGMRESRestart.assert_called_once_with(32)
    ksp.setTolerances.assert_called_once_with(rtol=0.0, atol=0.0, max_it=2048)
    ksp.setInitialGuessNonzero.assert_called_once_with(False)
    ksp.solve.assert_called_once()
    ksp.destroy.assert_called_once()


def test_n0_threshold_pass_is_explicitly_scoped_to_n0(monkeypatch):
    result, _, _, _ = _fake_run(monkeypatch, "A6_n0_relative", value=5e-7)
    assert result["status"] == "TRUE_RESIDUAL_PASS"
    assert result["iterations"] == 8
    assert result["final_evaluation"]["physical_residual_pass"]
    assert result["physical_residual_key"] == "A6_n0_relative"
    assert result["operator_scope"] == "n0_filtered_dtn_not_full_dtn"
    assert "original_A6_relative" not in result["final_evaluation"]


def test_n0_rejects_ambiguous_original_residual_alias(monkeypatch):
    with pytest.raises(ValueError, match="ambiguous original_A6_relative"):
        _fake_run(monkeypatch, "A6_n0_relative", extra_facts={"original_A6_relative": 0.0})


def test_n0_nonfinite_residual_still_fails(monkeypatch):
    with pytest.raises(FloatingPointError, match="nonfinite"):
        _fake_run(monkeypatch, "A6_n0_relative", value=float("nan"))


def test_unsupported_equation_name_fails_before_petsc_setup():
    with pytest.raises(ValueError, match="unsupported physical residual equation key"):
        run_retained_fgmres(
            None, None, None, evaluate=None, checkpoint=None,
            append=None, seconds=None, physical_residual_key="A6_full_relative",
        )
