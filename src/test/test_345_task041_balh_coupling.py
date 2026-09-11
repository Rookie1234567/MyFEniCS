"""Focused complex-algebra contract for the Task041 BAL_H core."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.physical_balanced_coupling import (
    BALANCE_LIMIT,
    BalancedConstraintRejected,
    PhysicalBalancedCoupling,
)


class _TrackedVector:
    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.complex128).copy()
        self.destroyed = False

    def duplicate(self) -> "_TrackedVector":
        return _TrackedVector(self.values)

    def copy(self, target: "_TrackedVector") -> None:
        target.values[:] = self.values

    def norm(self) -> float:
        return float(np.linalg.norm(self.values))

    def axpy(self, alpha: complex, source: "_TrackedVector") -> None:
        self.values[:] += alpha * source.values

    def destroy(self) -> None:
        self.destroyed = True


def _operator_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(37)
    a = rng.normal(size=(9, 9)) + 1j * rng.normal(size=(9, 9))
    a += 3.0 * np.eye(9)
    p = rng.normal(size=(9, 2)) + 1j * rng.normal(size=(9, 2))
    coarse = p @ np.linalg.solve(p.conj().T @ a @ p, p.conj().T)
    smoother = np.diag(np.linspace(0.2, 0.8, 9))
    return a, p, coarse, smoother


def test_bal_h_preserves_complex_formula_and_audit_counts() -> None:
    a, p, coarse, smoother = _operator_fixture()
    source = np.arange(9, dtype=np.complex128) + 1j
    original = source.copy()

    coupling = PhysicalBalancedCoupling(
        lambda value: a @ value,
        lambda value: coarse @ value,
        lambda value: smoother @ value,
        lambda value: p.conj().T @ value,
    )

    result = coupling.apply(source)
    identity = np.eye(a.shape[0], dtype=np.complex128)
    expected_operator = (
        coarse + (identity - coarse @ a) @ smoother @ (identity - a @ coarse)
    )
    expected = expected_operator @ source
    final_residual = source - a @ result

    np.testing.assert_allclose(result, expected, rtol=1.0e-12, atol=1.0e-12)
    np.testing.assert_array_equal(source, original)
    np.testing.assert_allclose(p.conj().T @ final_residual, 0.0, atol=1.0e-10)
    facts = coupling.last_apply_facts
    assert facts["route"] == "BAL_H"
    assert facts["counts"] == {"Q": 2, "H6": 1, "A6": 2, "PH_audit": 2}
    assert facts["initial"]["balance"]["relative"] <= BALANCE_LIMIT
    assert facts["peak_new_vectors"] <= 6
    assert facts["live_after_cleanup"] == 0
    assert facts["status"] == "BALANCED_ACTION_COMPLETED"


def test_bal_h_repeated_rhs_is_state_free_and_rejects_borrowed_output() -> None:
    a, p, coarse, smoother = _operator_fixture()
    q1 = np.arange(9, dtype=np.complex128) - 0.3j
    q2 = np.linspace(-0.7, 0.9, 9) + 0.4j
    coupling = PhysicalBalancedCoupling(
        lambda value: a @ value,
        lambda value: coarse @ value,
        lambda value: smoother @ value,
        lambda value: p.conj().T @ value,
    )

    identity = np.eye(a.shape[0], dtype=np.complex128)
    expected_operator = (
        coarse + (identity - coarse @ a) @ smoother @ (identity - a @ coarse)
    )
    first = coupling.apply(q1)
    first_peak = coupling.last_apply_facts["peak_new_vectors"]
    middle = coupling.apply(q2)
    middle_peak = coupling.last_apply_facts["peak_new_vectors"]
    third = coupling.apply(q1)
    third_peak = coupling.last_apply_facts["peak_new_vectors"]
    np.testing.assert_allclose(first, expected_operator @ q1)
    np.testing.assert_allclose(middle, expected_operator @ q2)
    np.testing.assert_allclose(third, expected_operator @ q1)
    assert coupling.apply_count == 3
    assert max(first_peak, middle_peak, third_peak) <= 6
    assert coupling.last_apply_facts["live_after_cleanup"] == 0

    source = q1.copy()
    borrowed = PhysicalBalancedCoupling(
        lambda value: value,
        lambda value: value,
        lambda value: value,
        lambda value: value.copy(),
    )
    with pytest.raises(TypeError, match="fresh owned"):
        borrowed.apply(source)
    assert borrowed.apply_count == 0
    assert borrowed.last_apply_facts["live_after_cleanup"] == 0


def test_bal_h_balance_gate_rejects_a_bad_dual_residual() -> None:
    source = np.asarray([1.0 + 2.0j, 2.0 - 1.0j])
    coupling = PhysicalBalancedCoupling(
        lambda value: np.zeros_like(value),
        lambda value: np.zeros_like(value),
        lambda value: np.zeros_like(value),
        lambda value: np.asarray([value[0] + 1.0]),
    )

    with pytest.raises(BalancedConstraintRejected):
        coupling.apply(source)
    assert coupling.last_apply_facts["live_after_cleanup"] == 0


def test_bal_h_releases_first_dual_when_second_ph_raises() -> None:
    source = _TrackedVector(np.asarray([1.0 + 2.0j, 2.0 - 1.0j]))
    original = source.values.copy()
    dual_outputs: list[_TrackedVector] = []

    def restriction(_value: _TrackedVector) -> _TrackedVector:
        if not dual_outputs:
            dual = _TrackedVector(np.zeros(2, dtype=np.complex128))
            dual_outputs.append(dual)
            return dual
        raise RuntimeError("injected second PH failure")

    coupling = PhysicalBalancedCoupling(
        lambda value: _TrackedVector(np.zeros_like(value.values)),
        lambda value: _TrackedVector(np.zeros_like(value.values)),
        lambda value: _TrackedVector(np.zeros_like(value.values)),
        restriction,
    )

    with pytest.raises(RuntimeError, match="second PH failure"):
        coupling.apply(source)
    assert dual_outputs[0].destroyed is True
    assert source.destroyed is False
    np.testing.assert_array_equal(source.values, original)
    assert coupling.last_apply_facts["live_after_cleanup"] == 0
