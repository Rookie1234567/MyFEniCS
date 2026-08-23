"""Focused contracts for the reusable L2 source and shell helpers."""

from __future__ import annotations

import ast
import inspect

import numpy as np
import pytest

from src.solvers.fullspace_lor_native_hx_fixture import (
    L2_CG_MAX_IT,
    L2_CG_RTOL,
    L2_RHO_LIMITS,
    L2_SOURCE_NAMES,
    L2HXPCContext,
    L2HighActionShellContext,
    _l2_analytic_values,
    l2_one_apply,
    l2_source_formula,
)


class _FakeVector:
    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.complex128).copy()
        self.destroy_calls = 0

    def copy(self, target: "_FakeVector | None" = None):
        if target is None:
            return _FakeVector(self.values)
        target.values[:] = self.values
        return None

    def getArray(self, readonly: bool = False) -> np.ndarray:
        return self.values

    def norm(self) -> float:
        return float(np.linalg.norm(self.values))

    def axpy(self, coefficient: complex, other: "_FakeVector") -> None:
        self.values[:] += coefficient * other.values

    def destroy(self) -> None:
        self.destroy_calls += 1


class _FakeFixture:
    def __init__(self) -> None:
        self.action_calls = 0
        self.pc_calls = 0

    def apply_high_action_copy(self, source: _FakeVector) -> _FakeVector:
        self.action_calls += 1
        return _FakeVector(2.0 * source.values)

    def apply_high_preconditioner(self, source: _FakeVector) -> _FakeVector:
        self.pc_calls += 1
        return _FakeVector(0.5 * source.values)


def test_l2_source_formulas_and_fixed_limits_are_closed() -> None:
    assert L2_SOURCE_NAMES == ("random", "gradient", "curl", "checkerboard")
    assert L2_RHO_LIMITS == {
        "random": 0.45,
        "gradient": 0.25,
        "curl": 0.45,
        "checkerboard": 0.60,
    }
    assert L2_CG_RTOL == 1.0e-8
    assert L2_CG_MAX_IT == 40
    assert "pseudo-random" in l2_source_formula("random")
    assert "grad(" in l2_source_formula("gradient")
    assert "curl(" in l2_source_formula("curl")
    assert "8-cycle" in l2_source_formula("checkerboard")
    with pytest.raises(ValueError):
        l2_source_formula("rhs-driven")


def test_l2_shell_contexts_copy_outputs_and_keep_input() -> None:
    fixture = _FakeFixture()
    source = _FakeVector(np.asarray([1.0 + 2.0j, -3.0 + 1.0j]))
    target = _FakeVector(np.zeros(2, dtype=np.complex128))
    before = source.values.copy()
    action_context = L2HighActionShellContext(fixture)
    action_context.mult(None, source, target)
    assert np.array_equal(source.values, before)
    assert np.array_equal(target.values, 2.0 * before)

    pc_target = _FakeVector(np.zeros(2, dtype=np.complex128))
    pc_context = L2HXPCContext(fixture)
    pc_context.apply(None, source, pc_target)
    assert np.array_equal(source.values, before)
    assert np.array_equal(pc_target.values, 0.5 * before)
    assert pc_context.apply_count == 1


def test_l2_one_apply_fake_ownership_and_repeat_contract() -> None:
    fixture = _FakeFixture()
    source = _FakeVector(np.asarray([1.0 + 0.5j, -2.0 + 1.0j]))
    before = source.values.copy()
    first = l2_one_apply(fixture, source)
    second = l2_one_apply(fixture, source)
    try:
        assert first["input_unchanged"] is True
        assert second["input_unchanged"] is True
        assert first["rho"] == 0.0
        assert second["rho"] == 0.0
        assert np.array_equal(source.values, before)
        assert np.array_equal(first["output"].values, second["output"].values)
    finally:
        for result in (first, second):
            for name in ("true_residual", "applied_output", "output", "residual"):
                result[name].destroy()


def test_l2_source_formula_has_no_result_scan_or_rng() -> None:
    tree = ast.parse(inspect.getsource(_l2_analytic_values))
    assert not any(
        isinstance(node, (ast.For, ast.While, ast.comprehension))
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in {"random", "default_rng"}
        for node in ast.walk(tree)
    )
