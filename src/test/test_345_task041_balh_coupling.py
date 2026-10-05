"""Focused complex-algebra contract for the Task041 BAL_H core."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.physical_balanced_coupling import (
    BALANCE_LIMIT,
    BalancedConstraintRejected,
    PhysicalBalancedCoupling,
)
from src.solvers.physical_balanced_side_inverse import SideBalancedInverse


class _TrackedVector:
    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.complex128).copy()
        self.destroyed = False

    def duplicate(self) -> _TrackedVector:
        return _TrackedVector(self.values)

    def copy(self, target: _TrackedVector) -> None:
        target.values[:] = self.values

    def norm(self) -> float:
        return float(np.linalg.norm(self.values))

    def axpy(self, alpha: complex, source: _TrackedVector) -> None:
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


def _tracked_balanced_callbacks(*, reuse: bool, fail: str | None = None):
    a, p, _coarse, smoother = _operator_fixture()
    ph_matrix = p.conj().T
    p4_map = p @ np.linalg.inv(ph_matrix @ a @ p)
    created: list[_TrackedVector] = []
    counts = {"Q_PH": 0, "audit_PH": 0}
    failure = {"kind": fail}

    def vector(values: np.ndarray) -> _TrackedVector:
        result = _TrackedVector(values)
        created.append(result)
        return result

    def action(value: _TrackedVector) -> _TrackedVector:
        if failure["kind"] == "A6":
            failure["kind"] = None
            raise RuntimeError("injected A6 failure after first Q")
        return vector(a @ value.values)

    def q(value: _TrackedVector, *, return_leading_dual: bool = False):
        counts["Q_PH"] += 1
        dual = ph_matrix @ value.values
        result = vector(p4_map @ dual)
        if return_leading_dual:
            return result, vector(dual)
        return result

    def smoother_action(value: _TrackedVector) -> _TrackedVector:
        return vector(smoother @ value.values)

    def restriction(value: _TrackedVector) -> _TrackedVector:
        counts["audit_PH"] += 1
        if failure["kind"] == "PH_residual":
            failure["kind"] = None
            raise RuntimeError("injected residual PH failure")
        return vector(ph_matrix @ value.values)

    checkpoint_count = {"value": 0}

    def checkpoint() -> None:
        checkpoint_count["value"] += 1
        if failure["kind"] == "checkpoint" and checkpoint_count["value"] == 2:
            failure["kind"] = None
            raise RuntimeError("injected checkpoint after first Q")

    return (
        PhysicalBalancedCoupling(
            action,
            q,
            smoother_action,
            restriction,
            checkpoint=checkpoint,
            reuse_leading_ph=reuse,
        ),
        counts,
        created,
    )


def test_bal_h_first_q_dual_reuse_matches_complex_ab_a_and_counts_ph() -> None:
    a, p, _coarse, smoother = _operator_fixture()
    ph = p.conj().T
    coarse = p @ np.linalg.inv(ph @ a @ p) @ ph
    inputs = (
        np.arange(9, dtype=np.complex128) + 0.25j,
        np.linspace(-0.8, 1.2, 9).astype(np.complex128) - 0.35j,
        np.arange(9, dtype=np.complex128) + 0.25j,
    )
    originals = tuple(value.copy() for value in inputs)
    call_shapes = {"legacy": [], "reuse": []}
    call_counts = {
        "legacy": {"Q_PH": 0, "audit_PH": 0},
        "reuse": {"Q_PH": 0, "audit_PH": 0},
    }

    def make_case(name: str, *, reuse: bool) -> PhysicalBalancedCoupling:
        def q(value: np.ndarray, *, return_leading_dual: bool = False):
            call_shapes[name].append(return_leading_dual)
            call_counts[name]["Q_PH"] += 1
            dual = ph @ value
            result = coarse @ value
            if return_leading_dual:
                return result.copy(), dual.copy()
            return result.copy()

        def restriction(value: np.ndarray) -> np.ndarray:
            call_counts[name]["audit_PH"] += 1
            return (ph @ value).copy()

        return PhysicalBalancedCoupling(
            lambda value: a @ value,
            q,
            lambda value: smoother @ value,
            restriction,
            reuse_leading_ph=reuse,
        )

    legacy = make_case("legacy", reuse=False)
    reused = make_case("reuse", reuse=True)
    identity = np.eye(a.shape[0], dtype=np.complex128)
    expected_operator = (
        coarse + (identity - coarse @ a) @ smoother @ (identity - a @ coarse)
    )
    for source, original in zip(inputs, originals, strict=True):
        legacy_output = legacy.apply(source)
        legacy_facts = legacy.last_apply_facts
        reused_output = reused.apply(source)
        reused_facts = reused.last_apply_facts
        np.testing.assert_allclose(legacy_output, expected_operator @ source)
        np.testing.assert_allclose(reused_output, legacy_output, rtol=1e-12, atol=1e-12)
        np.testing.assert_array_equal(source, original)
        assert legacy_facts["initial"]["balance"] == reused_facts["initial"]["balance"]
        assert legacy_facts["counts"] == {
            "Q": 2,
            "H6": 1,
            "A6": 2,
            "PH_audit": 2,
        }
        assert reused_facts["counts"] == {
            "Q": 2,
            "H6": 1,
            "A6": 2,
            "PH_audit": 2,
            "PH_audit_transfer": 1,
            "PH_audit_leading_reused": 1,
        }
        assert legacy_facts["live_after_cleanup"] == 0
        assert reused_facts["live_after_cleanup"] == 0

    assert call_shapes["legacy"] == [False] * 6
    assert call_shapes["reuse"] == [True, False] * 3
    assert [sum(call_counts[name].values()) for name in ("legacy", "reuse")] == [12, 9]


@pytest.mark.parametrize("failure_kind", ("A6", "checkpoint", "PH_residual"))
def test_bal_h_reused_first_dual_is_released_after_failure_and_retry(
    failure_kind: str,
) -> None:
    source = _TrackedVector(np.arange(9, dtype=np.complex128) + 0.4j)
    original = source.values.copy()
    coupling, _counts, created = _tracked_balanced_callbacks(
        reuse=True,
        fail=failure_kind,
    )
    with pytest.raises(RuntimeError, match="injected"):
        coupling.apply(source)
    failed_vectors = list(created)
    assert failed_vectors
    assert all(vector.destroyed for vector in failed_vectors)
    assert source.destroyed is False
    np.testing.assert_array_equal(source.values, original)
    assert coupling.last_apply_facts["live_after_cleanup"] == 0

    result = coupling.apply(source)
    assert coupling.last_apply_facts["status"] == "BALANCED_ACTION_COMPLETED"
    assert coupling.last_apply_facts["live_after_cleanup"] == 0
    assert all(vector.destroyed for vector in created if vector is not result)
    assert result.destroyed is False
    result.destroy()


def test_bal_h_q_handoff_wrapper_releases_pair_when_impl_raises() -> None:
    class _QOwner:
        _reuse_leading_ph_dual = True

        def __init__(self) -> None:
            self.fail = True
            self.created: list[_TrackedVector] = []

        def _apply_q_callback_impl(self, source, *, handoff_state):
            output = _TrackedVector(source.values + 1.0 + 0.5j)
            dual = _TrackedVector(source.values - 0.25j)
            self.created.extend((output, dual))
            handoff_state["coarse_output"] = output
            handoff_state["leading_dual"] = dual
            if self.fail:
                self.fail = False
                raise RuntimeError("injected Q tail diagnostic failure")
            return output

    owner = _QOwner()
    source = _TrackedVector(np.asarray([1.0 + 2.0j, -0.5 + 0.75j]))
    with pytest.raises(RuntimeError, match="Q tail diagnostic"):
        SideBalancedInverse._apply_q_callback(
            owner,
            source,
            return_leading_dual=True,
        )
    assert all(vector.destroyed for vector in owner.created)
    pair = SideBalancedInverse._apply_q_callback(
        owner,
        source,
        return_leading_dual=True,
    )
    assert isinstance(pair, tuple) and len(pair) == 2
    assert all(not vector.destroyed for vector in pair)
    assert owner.created[-2:] == list(pair)
    for vector in pair:
        vector.destroy()
