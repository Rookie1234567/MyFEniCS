"""Non-Hermitian complex two-level identities, ownership and fixed-rank rules."""

import numpy as np
import pytest

from src.solvers.learned_two_level import (
    BalancedTwoLevelPC,
    algebra_audit,
    build_schur_encoding,
    error_space,
    space_budget,
)


class Local:
    representation_bytes = 0
    factor_bytes = 0
    declarations = ()

    def __init__(self, matrix):
        self.matrix = matrix
        self.calls = 0

    def apply_array(self, source):
        self.calls += 1
        return self.matrix @ source


@pytest.fixture
def toy():
    rng = np.random.default_rng(42)
    s = (
        rng.standard_normal((19, 19))
        + 1j * rng.standard_normal((19, 19))
        + 11 * np.eye(19)
    )
    b = np.diag(1.0 / np.diag(s))
    q = np.linalg.qr(rng.standard_normal((19, 5)) + 1j * rng.standard_normal((19, 5)))[
        0
    ]
    calls = []

    def operator(x):
        calls.append(1)
        return s @ x

    z, u, r, report = build_schur_encoding(q, operator)
    pc = BalancedTwoLevelPC(Local(b), operator, z, u, r)
    return pc, s, b, report, calls


def test_nonhermitian_identities_and_explicit_pair(toy):
    pc, s, b, report, _ = toy
    assert not np.allclose(s, s.conj().T)
    assert report["effective_rank"] == 5
    assert algebra_audit(pc)["passed"]
    # Dense matrices are permitted only in this 19-row pure-array test.
    c = pc.z @ np.linalg.solve(pc.r, pc.u.conj().T)
    b2 = c + (np.eye(19) - c @ s) @ b @ (np.eye(19) - s @ c)
    rhs = np.arange(19, dtype=np.complex128) * (1.0 + 0.5j)
    np.testing.assert_allclose(pc.apply_array(rhs), b2 @ rhs, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        pc.coarse_array(rhs),
        pc.z @ np.linalg.lstsq(s @ pc.z, rhs, rcond=None)[0],
        rtol=1e-12,
        atol=1e-12,
    )


def test_linearity_phase_scale_zero_and_input_ownership(toy):
    pc, _, _, _, _ = toy
    rhs = np.arange(19, dtype=np.complex128) + 1j
    copy = rhs.copy()
    original = pc.apply_array(rhs)
    for scale in (1j, -1j, 1e-3, 1e3):
        np.testing.assert_allclose(
            pc.apply_array(scale * rhs), scale * original, rtol=2e-12, atol=1e-12
        )
    np.testing.assert_array_equal(
        pc.apply_array(np.zeros_like(rhs)), np.zeros_like(rhs)
    )
    np.testing.assert_array_equal(rhs, copy)
    assert not np.shares_memory(original, rhs)
    assert pc.z.flags.writeable is False


def test_exact_action_counts_and_borrowed_ownership(toy):
    pc, _, _, _, calls = toy
    before = len(calls)
    pc.apply_array(np.ones(19, dtype=np.complex128))
    assert len(calls) - before == 1
    assert (pc.calls, pc.coarse_calls, pc.local_calls, pc.operator_calls) == (
        1,
        2,
        1,
        1,
    )
    assert pc.local.calls == 1
    assert not hasattr(pc, "destroy")  # borrowed B/S must never be destroyed by PC


def test_rank_deficient_rejected_and_once_fixed_dependency_rotation(toy):
    pc, s, _, _, _ = toy
    broken = pc.r.copy(order="F")
    broken[-1] = 0.0
    with pytest.raises(ValueError, match="rank-deficient"):
        BalancedTwoLevelPC(pc.local, pc.operator, pc.z, pc.u, broken)
    redundant = np.asfortranarray(np.column_stack((pc.z, pc.z[:, 0])))
    z, u, r, report = build_schur_encoding(redundant, lambda x: s @ x)
    assert report["input_rank"] == 6 and report["effective_rank"] == 5
    assert report["dependency_rotation_once"]
    assert algebra_audit(BalancedTwoLevelPC(pc.local, lambda x: s @ x, z, u, r))[
        "passed"
    ]


def test_snapshot_rank_not_filled_and_capacity():
    rng = np.random.default_rng(4)
    x = rng.standard_normal((40, 3)) + 1j * rng.standard_normal((40, 3))
    z, values = error_space(np.column_stack((x, x[:, 0])))
    assert z.shape == (40, 3) and len(values) == 4
    budget = space_budget(21824, 128, 3010048, 302047392)
    assert budget["construction_representation_workspace_bound_bytes"] <= 512 * 2**20
    assert budget["all_factor_bound_bytes"] <= 512 * 2**20
    with pytest.raises(ValueError, match="capacity"):
        space_budget(100000, 128)
