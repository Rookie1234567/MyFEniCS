"""Non-Hermitian complex head LS and independently checked port signs."""

import numpy as np
import pytest

from src.solvers.neural_linear_head import (
    port_closure_checks,
    thin_capacity,
    thin_lstsq,
)


def test_complex_thin_rank_and_original_first_order():
    rng = np.random.default_rng(13)
    q = rng.normal(size=(47, 8)) + 1j * rng.normal(size=(47, 8))
    q[:, -1] = q[:, 0] + (2 - 3j) * q[:, 1]
    rhs = rng.normal(size=47) + 1j * rng.normal(size=47)
    gamma, record = thin_lstsq(q, rhs)
    assert record["effective_rank"] == 7
    assert not record["exact_full_space_optimum_claimed"]
    assert np.linalg.norm(q.conj().T @ (rhs - q @ gamma)) < 1e-11
    assert record["residual_correction_count"] == 0


def test_nonhermitian_port_closure_recovers_original_equation():
    rng = np.random.default_rng(29)
    n = 12
    S = rng.normal(size=(n + 40, n + 40)) + 1j * rng.normal(size=(n + 40, n + 40))
    S[n:, n:] += 50 * np.eye(40)
    b = rng.normal(size=n + 40) + 1j * rng.normal(size=n + 40)
    checks, columns = port_closure_checks(S[n:, n:], lambda x: S @ x, n, b)
    assert checks["status"] == "PASS"
    assert np.allclose(columns, S[:, n:])
    t = rng.normal(size=n) + 1j * rng.normal(size=n)
    alpha = np.linalg.solve(S[n:, n:], b[n:] - S[n:, :n] @ t)
    z = np.r_[t, alpha]
    assert np.linalg.norm((b - S @ z)[n:]) < 1e-13
    H = np.zeros((40, 40), complex)
    unsafe, _ = port_closure_checks(H, lambda x: S @ x, n, b)
    assert unsafe["status"] == "PORT_BLOCK_UNSAFE"


def test_capacity_and_nonfinite_inputs_are_real_gates():
    plan = thin_capacity(18184, 1600, 18144, 1560, 209239672, 512 * 2**20)
    assert plan["conservative_resident_plan_bytes"] < 8 * 2**30
    with pytest.raises(ValueError):
        thin_capacity(181840, 16000, 181440, 15600, 209239672, 512 * 2**20)
    with pytest.raises(ValueError):
        thin_lstsq(np.full((5, 2), np.nan + 0j), np.ones(5))
