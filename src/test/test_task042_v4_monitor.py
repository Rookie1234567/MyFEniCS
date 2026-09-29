"""Real complex PETSc Krylov test of low-frequency audit and state capture."""

from types import SimpleNamespace

import numpy as np
import pytest

from src.io import load_and_resolve
from src.io.task042_profile import TASK042_PROFILES
from src.solvers.coarse_inverse_protocol import CoarseRHS
from src.solvers.learned_coarse_inverse import IterativeCoarseBackend


def test_explicit_v4_inputs_keep_original_operator_and_defaults():
    original = load_and_resolve(
        "input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat"
    )
    for profile, stage in TASK042_PROFILES.items():
        if stage.startswith("V4-"):
            path = (
                "input/task042_neural_coarse_inverse/"
                + stage.lower().replace("-", "_")
                + "_shared.dat"
            )
            new = load_and_resolve(path)
            assert new.physical_model_sha256 == original.physical_model_sha256
            assert new.solver["preconditioner"] == profile
            assert new.execution["mpi_size"] == 1
    assert original.solver["preconditioner"] == "balanced_h6_p4_v5"


def test_capture_real_iterates_without_native_audit_every_step():
    PETSc = pytest.importorskip("petsc4py.PETSc")
    if PETSc.ScalarType is not np.complex128:
        pytest.skip("complex ABI required")
    n = 120
    matrix = PETSc.Mat().createAIJ((n, n), nnz=2, comm=PETSc.COMM_SELF)
    for j, diagonal in enumerate(np.logspace(-6, 1, n)):
        matrix.setValue(j, j, diagonal + 0.2j * diagonal)
        if j + 1 < n:
            matrix.setValue(j, j + 1, 0.02 * diagonal)
    matrix.assemble()

    class Action:
        condensed = SimpleNamespace(active_rows=n)

        def reduce_rhs(self, values, **_kwargs):
            return values.copy()

        def recover_storage(self, values, **_kwargs):
            return values.copy()

    class IdentityPC:
        declarations = ()

        def apply(self, _pc, source, target):
            source.copy(target)

    seen, states = [], {}
    rhs = CoarseRHS(np.ones(n, dtype=np.complex128), np.zeros(0, dtype=np.complex128))

    def audit(i, _reported, x, residual, raw):
        source = matrix.createVecRight()
        output = source.duplicate()
        try:
            source.array[:] = x
            matrix.mult(source, output)
            np.testing.assert_allclose(
                residual, raw - output.array, rtol=1e-12, atol=1e-12
            )
            seen.append(i)
        finally:
            source.destroy()
            output.destroy()

    backend = IterativeCoarseBackend(
        matrix,
        Action(),
        IdentityPC(),
        "a" * 64,
        (),
        diagnostic_observer=audit,
        observer_stride=32,
        state_capture=lambda i, x: states.update({i: x.copy()}),
        max_iterations=64,
    )
    try:
        _state, report = backend.solve(rhs)
        assert report.iterations == 64
        assert seen == [0, 32, 64]
        assert sorted(states) == list(range(8, 65, 8))
        assert len(backend.history) == 65
        assert np.any(states[8]) and not np.array_equal(states[8], states[64])
        assert backend.last_reason < 0  # valid bounded trajectory, not a solver bug
        np.testing.assert_array_equal(rhs.fe, np.ones(n))
    finally:
        matrix.destroy()
