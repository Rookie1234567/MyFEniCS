from __future__ import annotations

import numpy as np

from src.solvers.batched_reduced_smoother import (
    FrozenLinearReducedMap,
    FusedLinearReducedAction,
    IluLinearReducedCorrectionSlabSolver,
)
from src.solvers.local_slab_solver import CallableLocalSlabSolver, LocalCsrOperator, ScipyCsrAction


def _operator() -> LocalCsrOperator:
    return LocalCsrOperator(
        shape=(3, 3),
        indptr=np.array([0, 1, 2, 3]),
        indices=np.array([0, 1, 2]),
        values=np.array([2.0 + 1j, 3.0 - 1j, 4.0 + 2j]),
    )


def test_compiled_csr_matches_portable_action() -> None:
    operator = _operator()
    source = np.array([1 + 2j, -3 + .5j, .7 - .2j])
    assert np.allclose(ScipyCsrAction(operator).action(source), operator.action(source))


def test_linear_reduced_batch_checkpoint_and_shadow(tmp_path) -> None:
    operator = _operator()
    identity = np.eye(3, dtype=np.complex128)
    inverse = np.diag(1.0 / operator.values)
    model = FrozenLinearReducedMap(identity, inverse, identity, operator.fingerprint)
    source = np.array([[1 + 2j, 2 - 1j, 3 + .5j], [-2j, 1 + 0j, .3 - .7j]])
    assert np.allclose(model.predict_many(source), np.stack([model.predict(row) for row in source]))
    fused = FusedLinearReducedAction(operator, model)
    prediction, rho = fused.predict_and_audit_many(source)
    assert np.allclose(operator.values * prediction, source)
    assert np.max(rho) < 1e-14

    model.save(tmp_path, nonlinear_activation=False)
    loaded = FrozenLinearReducedMap.load(tmp_path, expected_operator_fingerprint=operator.fingerprint)
    assert np.allclose(loaded.predict_many(source), prediction)

    ilu = CallableLocalSlabSolver(3, lambda rhs: 0.5 * inverse @ rhs, identity="half_inverse")
    shadow = IluLinearReducedCorrectionSlabSolver(operator, model, ilu, shadow=True)
    output = np.empty(3, dtype=np.complex128)
    shadow.solve(source[0], output)
    assert np.allclose(output, 0.5 * inverse @ source[0])
    assert shadow.diagnostics["accept_count"] == 1
