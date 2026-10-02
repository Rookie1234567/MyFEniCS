"""Small fixture for the bounded Task40 local-growth action diagnostic."""

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from benchmarks.diagnose_task40_p6_local_growth_v2 import _make_bank, _mode_stress


def test_streamed_local_mode_actions_use_fixed_square_scratch_and_close_rhs():
    rng = np.random.default_rng(7)
    ni, nt = 4, 3
    Aii = np.diag(np.array([2.0, 3.0, 4.0, 5.0], dtype=np.complex128))
    Ait = np.asarray(rng.normal(size=(ni, nt)) + 1j * rng.normal(size=(ni, nt)))
    Ati = np.asarray(rng.normal(size=(nt, ni)) + 1j * rng.normal(size=(nt, ni)))
    factor = lu_factor(Aii)
    Xit = lu_solve(factor, Ait)
    bank = _make_bank(np.random.default_rng(11), ni, nt, 4)

    records = _mode_stress(
        factor=factor,
        Aii=Aii,
        Ait=Ait,
        Ati=Ati,
        Xit=Xit,
        bank=bank,
        mode_sizes=[5, 9],
        batch_size=3,
        seed=13,
    )

    assert [record["processed_mode_columns"] for record in records] == [5, 9]
    assert [record["batch_count"] for record in records] == [2, 3]
    assert all(record["largest_square_scratch_shape"] == [3, 3] for record in records)
    assert all(record["no_mode_square_allocation"] for record in records)
    assert all(record["max_nonzero_rhs_local_recovery_relative_closure"] < 1e-12 for record in records)
