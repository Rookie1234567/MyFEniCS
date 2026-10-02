"""Small fixtures for Task40's bounded, streamed local-growth action."""

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from benchmarks.diagnose_task40_p6_local_growth_v2 import (
    _make_bank,
    _mode_stress,
    _streamed_modal_action,
)


def test_streamed_feedback_matches_dense_oracle_across_batch_boundary():
    rng = np.random.default_rng(7)
    ni, nt, modes, batch = 5, 4, 20, 16
    Aii = np.diag(np.array([2, 3, 4, 5, 6], dtype=np.complex128))
    Ait = rng.normal(size=(ni, nt)) + 1j * rng.normal(size=(ni, nt))
    Ati = rng.normal(size=(nt, ni)) + 1j * rng.normal(size=(nt, ni))
    factor = lu_factor(Aii)
    Xit = lu_solve(factor, Ait)
    bank = _make_bank(np.random.default_rng(11), ni, nt, modes)
    alpha = rng.normal(size=modes) + 1j * rng.normal(size=modes)
    trace = rng.normal(size=nt) + 1j * rng.normal(size=nt)

    streamed = _streamed_modal_action(
        factor=factor, Aii=Aii, Ait=Ait, Ati=Ati, Xit=Xit, bank=bank,
        alpha=alpha, trace_vector=trace, batch_size=batch,
    )
    Bi, Di, Bt, Dt = bank["Bi"], bank["Di"], bank["Bt"], bank["Dt"]
    XiB = lu_solve(factor, Bi)
    Bhat = Bt - Ati @ XiB
    Dhat = Dt - Di @ Xit
    dense_trace = Bhat @ alpha
    dense_port = Dhat @ trace + (Di @ XiB) @ alpha
    cross_batch_feedback = Di[:batch] @ (XiB[:, batch:] @ alpha[batch:])

    np.testing.assert_allclose(streamed["trace_from_port"], dense_trace, rtol=2e-13, atol=2e-13)
    np.testing.assert_allclose(streamed["port_total"], dense_port, rtol=2e-13, atol=2e-13)
    assert np.linalg.norm(cross_batch_feedback) > 0.0
    np.testing.assert_allclose(streamed["port_feedback"][:batch], (Di @ XiB @ alpha)[:batch], rtol=2e-13, atol=2e-13)
    assert streamed["max_nonzero_rhs_local_recovery_relative_closure"] < 1e-12
    assert streamed["all_outputs_finite"]


def test_streamed_modal_stress_keeps_fixed_batch_scratch():
    rng = np.random.default_rng(19)
    ni, nt = 4, 3
    Aii = np.diag(np.array([2.0, 3.0, 4.0, 5.0], dtype=np.complex128))
    Ait = rng.normal(size=(ni, nt)) + 1j * rng.normal(size=(ni, nt))
    Ati = rng.normal(size=(nt, ni)) + 1j * rng.normal(size=(nt, ni))
    factor = lu_factor(Aii)
    Xit = lu_solve(factor, Ait)
    bank = _make_bank(np.random.default_rng(23), ni, nt, 4)
    records = _mode_stress(
        factor=factor, Aii=Aii, Ait=Ait, Ati=Ati, Xit=Xit, bank=bank,
        mode_sizes=[5, 9], batch_size=3, seed=13,
    )
    assert [item["processed_mode_columns_first_pass"] for item in records] == [5, 9]
    assert [item["processed_mode_rows_second_pass"] for item in records] == [5, 9]
    assert all(item["two_pass_complete_cross_batch_feedback"] for item in records)
    assert all(item["no_mode_square_allocation"] for item in records)
    assert all(item["diagnostic_pass"] for item in records)
