"""Pure-array qualification checks for the V14 Q3 interface algebra."""

import numpy as np
import pytest

from src.runners.physical_p4_schur_v14 import (
    _q3_interface_operation_audit,
    _q3_local_setup_prediction,
)
from src.solvers.physical_interface_schur import (
    apply_interface_cycle,
    build_interface_coarse_pair,
    build_paired_patch_basis,
    orthonormalize_paired_directions,
)


def test_q3_maximal_counters_alone_do_not_prove_a_complete_route():
    facts = {
        "factor_solve_delta": [4] * 42,
        "local_patch_apply_count": 84,
        "local_smoother_apply_count": 2,
        "coarse_solve_count": 1,
    }
    audit = _q3_interface_operation_audit(facts, 42)
    assert audit["internal_factor_solve_total"] == 168
    assert audit["internal_factor_solve_max_per_block"] == 4
    assert audit["internal_factor_solve_limit_total"] == 168
    assert audit["passed"] is False

    malformed = dict(facts, factor_solve_delta={"internal_total": 42})
    assert _q3_interface_operation_audit(malformed, 42)["passed"] is False


def test_q3_local_setup_prediction_uses_remaining_structure_weight():
    rows = tuple(np.zeros(size, dtype=np.int64) for size in (2, 4, 1, 3))
    prediction = _q3_local_setup_prediction(
        rows,
        (0, 1, 2, 3),
        (0, 1),
        {0: 1.2, 1: 4.0},
    )
    assert prediction["remaining_patch_ids"] == [2, 3]
    assert prediction["representative_structure_weight"] == 26
    assert prediction["remaining_structure_weight"] == 14
    assert prediction["seconds_per_structure_unit_upper"] == pytest.approx(0.2)
    assert prediction["predicted_remaining_seconds"] == pytest.approx(2.8)
    assert prediction["predicted_local_setup_seconds"] == pytest.approx(8.0)


def test_paired_patch_basis_records_true_reconstruction_and_output_identity():
    local = np.array(
        [[2.0 + 1.0j, -0.2j, 0.1], [0.4, 1.5 - 0.3j, 0.2j], [0.0, 0.1, 0.8]],
        dtype=np.complex128,
    )
    basis = build_paired_patch_basis(
        local,
        np.array([2.0, 0.5, 1.25]),
        patch_id="representative",
        max_pairs=3,
    )

    assert basis.rank == 3
    assert basis.checks["svd_driver"] == "gesvd"
    assert basis.checks["full_reconstruction_relative"] < 1.0e-12
    assert basis.checks["reconstruction_workspace_bytes"] > 0
    assert len(basis.checks["p_sha256"]) == 64
    assert len(basis.checks["q_sha256"]) == 64
    assert basis.checks["right_delta_subspace_gram_relative"] < 1.0e-12
    assert basis.checks["left_delta_subspace_gram_relative"] < 1.0e-12
    np.testing.assert_allclose(
        basis.P.conj().T @ (np.array([2.0, 0.5, 1.25])[:, None] * basis.P),
        np.eye(3),
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        basis.Q.conj().T @ (np.array([2.0, 0.5, 1.25])[:, None] * basis.Q),
        np.eye(3),
        atol=1.0e-12,
    )


def test_paired_two_pass_gram_schmidt_rejects_one_sided_dependence():
    P = np.array(
        [[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
        dtype=np.complex128,
    )
    Q = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.complex128,
    )
    P_before = P.copy()
    Q_before = Q.copy()

    paired = orthonormalize_paired_directions(P, Q)

    np.testing.assert_array_equal(paired.accepted_indices, [0, 1])
    np.testing.assert_array_equal(paired.rejected_indices, [2])
    np.testing.assert_array_equal(P, P_before)
    np.testing.assert_array_equal(Q, Q_before)
    np.testing.assert_allclose(paired.P.conj().T @ paired.P, np.eye(2), atol=1.0e-12)
    np.testing.assert_allclose(paired.Q.conj().T @ paired.Q, np.eye(2), atol=1.0e-12)
    assert paired.checks["two_pass_gram_schmidt"] is True
    assert len(paired.checks["p_sha256"]) == 64
    assert len(paired.checks["q_sha256"]) == 64


def test_coarse_pair_uses_bounded_batches_and_checks_actual_zero_solve():
    n, rank = 35, 5
    P = np.eye(n, rank, dtype=np.complex128)
    Q = np.eye(n, rank, dtype=np.complex128)
    diagonal = np.arange(1, n + 1, dtype=np.float64).astype(np.complex128)
    widths = []

    def action(values):
        assert values.ndim == 2
        widths.append(values.shape[1])
        return diagonal[:, None] * values

    coarse = build_interface_coarse_pair(action, P, Q)
    try:
        assert widths == [5]
        assert coarse.facts["assembly_batch_columns"] == 32
        assert coarse.facts["full_S_P_retained"] is False
        assert coarse.facts["rcond_method"] == "scipy.linalg.lapack.gecon"
        assert coarse.facts["workspace_bytes"] <= coarse.facts["workspace_cap_bytes"]
        assert np.shares_memory(coarse.P, P)
        assert np.shares_memory(coarse.Q, Q)
        zero = np.zeros(rank, dtype=np.complex128)
        np.testing.assert_array_equal(coarse.solve(zero), zero)
        assert coarse.facts["last_solve_residual"] == 0.0
        assert coarse.facts["max_solve_residual"] == 0.0
    finally:
        coarse.destroy()


def test_coarse_workspace_gate_precedes_any_s_action():
    P = np.eye(4, dtype=np.complex128)
    calls = []

    def action(values):
        calls.append(values.shape)
        return values

    with pytest.raises(MemoryError, match="COARSE_PAIR_WORKSPACE_EXCEEDED"):
        build_interface_coarse_pair(action, P, P, max_workspace_bytes=1)
    assert calls == []


def test_coarse_pair_rejects_dense_global_schur_even_when_small():
    P = np.eye(2, dtype=np.complex128)
    with pytest.raises(ValueError, match="dense global S_gamma"):
        build_interface_coarse_pair(np.eye(2, dtype=np.complex128), P, P)


def test_fixed_cycle_is_one_j_c_j_application():
    A = np.array([[3.0 + 1.0j, 2.0 - 1.0j], [0.25j, 2.0]], dtype=np.complex128)
    P = np.array([[1.0], [0.3j]], dtype=np.complex128)
    Q = np.array([[0.5j], [1.0]], dtype=np.complex128)
    coarse = build_interface_coarse_pair(lambda values: A @ values, P, Q)
    calls = {"S": 0, "J": 0}
    J = np.diag([0.2, 0.3]).astype(np.complex128)
    rhs = np.array([1.0 + 2.0j, -0.5j], dtype=np.complex128)

    def action(values):
        calls["S"] += 1
        return A @ values

    def local(values):
        calls["J"] += 1
        return J @ values

    try:
        C = P @ np.linalg.solve(Q.conj().T @ A @ P, Q.conj().T)
        expected = J + C @ (np.eye(2) - A @ J)
        expected += J @ (np.eye(2) - A @ expected)
        result, facts = apply_interface_cycle(rhs, action, local, coarse)
        np.testing.assert_allclose(result, expected @ rhs, atol=1.0e-13)
        assert calls == {"S": 2, "J": 2}
        assert facts["coarse_apply_count"] == 1
        assert facts["cycle_count"] == 1
    finally:
        coarse.destroy()
