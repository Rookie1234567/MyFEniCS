"""Nonzero complete-moment parameter JVP and independent analytic tangent."""

import numpy as np
import pytest
import torch
from src.solvers.feinn_phase import PhaseCoordinateField
from src.solvers.feinn_torch import CoordinateField, CompleteMomentMap
from src.solvers.feinn_parameter_jvp import MomentJacobian
from src.solvers.feinn_validation import parameters, assign
from src.solvers.damped_gauss_newton import DampedGNState
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    capture,
    load_checkpoint,
    restore,
)

if torch.get_num_interop_threads() != 1:
    torch.set_num_interop_threads(1)


def fixture():
    rng = np.random.default_rng(421909)
    nc, nq, dim = 9, 5, 4
    return CompleteMomentMap(
        dict(
            active_rows=np.asarray(nc * dim),
            reference_points=rng.uniform(size=(nq, 3)),
            interpolation=rng.normal(size=(dim, 3 * nq)),
            transforms=np.eye(dim)[None],
            jacobians=np.repeat(np.eye(3)[None], nc, axis=0),
            origins=rng.normal(size=(nc, 3)),
            orientation_ids=np.zeros(nc, dtype=int),
            owner_rows=np.arange(nc * dim).reshape(nc, dim),
        )
    )


@pytest.mark.parametrize("phase", [False, True])
@pytest.mark.parametrize("zero_output", [False, True])
def test_nonzero_directions_jvp_fd_real_adjoint_and_batch(phase, zero_output):
    torch.set_num_threads(1)
    kind = PhaseCoordinateField if phase else CoordinateField
    model = kind([[-5, 5], [-3.75, 3.75], [-1.25, 8.75]])
    rng = np.random.default_rng(421910)
    p = parameters(model)
    if not zero_output:
        p += 0.01 * rng.normal(size=p.size)
    assign(model, p)
    mapping = fixture()
    jac = MomentJacobian(mapping)
    v = rng.normal(size=p.size)
    v /= np.linalg.norm(v)
    j = jac.jvp(model, v)
    np.testing.assert_allclose(
        j, jac.jvp(model, v, analytic=True), rtol=1e-12, atol=1e-13
    )
    np.testing.assert_allclose(j, jac.jvp(model, v, 1), rtol=1e-12, atol=1e-13)
    for h in (1e-4, 1e-5, 1e-6):
        assign(model, p + h * v)
        plus = mapping.forward(model)
        assign(model, p - h * v)
        minus = mapping.forward(model)
        assert np.linalg.norm((plus - minus) / (2 * h) - j) / np.linalg.norm(j) < 1e-5
    assign(model, p)
    for pure_imag in (False, True):
        w = 1j * rng.normal(size=mapping.size)
        if not pure_imag:
            w += rng.normal(size=mapping.size)
        g = jac.vjp(model, w)
        np.testing.assert_allclose(np.vdot(w, j).real, v @ g, rtol=1e-11, atol=1e-12)
    np.testing.assert_array_equal(parameters(model), p)


def test_gn_atomic_save_load_and_matching_optimizer_restart(tmp_path):
    model = CoordinateField([[-5, 5], [-3.75, 3.75], [-1.25, 8.75]])
    state = DampedGNState(3.0)
    state.mu = 0.2
    state.accepted = 2
    state.V = np.eye(8966, 2)
    state.lam = np.array([0.3, 0.7])
    original = capture(model, state, dict(stage="GN", accepted=2))
    store = CheckpointStore(tmp_path)
    record = store.save(original, pin=True)
    loaded = load_checkpoint(tmp_path / record["name"], record["sha256"])
    other = CoordinateField([[-5, 5], [-3.75, 3.75], [-1.25, 8.75]])
    fresh = DampedGNState(1.0)
    restore(other, fresh, loaded)
    np.testing.assert_array_equal(parameters(other), parameters(model))
    np.testing.assert_array_equal(fresh.V, state.V)
    assert fresh.mu == state.mu and fresh.accepted == 2
