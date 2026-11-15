from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.pstddm_condensed_adapter import (
    balanced_partition_bounds,
    expand_trace_primal,
    inject_trace_dual,
    restrict_trace_dual,
    restrict_trace_primal,
)


def _complex_mpc_map(owned=(10, 20)):
    phase = np.exp(0.37j)
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray(owned, dtype=np.int64),
        original_to_active={10: 0, 20: 1},
        # Rows 30 and 40 are distinct slaves sharing masters 10 and 20.
        # Rows 50/60 are storage/interior entries and intentionally absent.
        expansion_by_original={
            10: (np.asarray([0]), np.asarray([1.0 + 0.0j])),
            20: (np.asarray([1]), np.asarray([1.0 + 0.0j])),
            30: (np.asarray([0, 1]), np.asarray([phase, -0.25 + 0.5j])),
            40: (np.asarray([0]), np.asarray([-0.3j])),
        },
        full_trace_rows=4,
        active_rows=2,
    )
    return constraints, phase


def test_h10_n4_uses_existing_nonuniform_integer_planes():
    assert balanced_partition_bounds(14, 4) == (0, 3, 7, 10, 14)
    bounds = np.asarray(balanced_partition_bounds(14, 4))
    assert np.array_equal(np.diff(bounds), [3, 4, 3, 4])
    assert max(np.diff(bounds)) - min(np.diff(bounds)) == 1


@pytest.mark.parametrize(
    "layers,partitions",
    [(0, 1), (4, 0), (4, 5), (True, 1), (4, False)],
)
def test_partition_bounds_reject_invalid_counts(layers, partitions):
    with pytest.raises(ValueError):
        balanced_partition_bounds(layers, partitions)


def test_dual_injection_is_master_only_and_restricts_to_original_active_residual():
    constraints, _phase = _complex_mpc_map()
    residual = np.asarray([1.25 - 0.75j, -2.0 + 0.125j])
    rows, values = inject_trace_dual(constraints, residual, full_rows=64)
    lifted = np.zeros(64, dtype=np.complex128)
    lifted[rows] = values

    assert rows.tolist() == [10, 20]
    assert np.array_equal(values, residual)
    assert not np.any(lifted[[30, 40, 50, 60]])
    assert np.array_equal(restrict_trace_dual(constraints, lifted, 64), residual)


def test_dual_restriction_uses_conjugate_complex_mpc_coefficients_and_sums_shared_masters():
    constraints, phase = _complex_mpc_map()
    full_dual = np.zeros(64, dtype=np.complex128)
    full_dual[[10, 20, 30, 40]] = [0.5 + 0.25j, -1.0j, 2.0 - 0.5j, -0.75 + 0.125j]
    full_dual[[50, 60]] = [1.0e8j, -3.0e8]

    reduced = restrict_trace_dual(constraints, full_dual, 64)
    expected = np.asarray([
        full_dual[10] + np.conjugate(phase) * full_dual[30]
        + np.conjugate(-0.3j) * full_dual[40],
        full_dual[20] + np.conjugate(-0.25 + 0.5j) * full_dual[30],
    ])
    assert np.allclose(reduced, expected, rtol=0.0, atol=1e-14)
    assert np.array_equal(reduced, restrict_trace_dual(constraints, full_dual, 64))


def test_primal_expand_then_master_restriction_recovers_active_coefficients():
    constraints, _phase = _complex_mpc_map()
    active = np.asarray([0.3 + 0.7j, -0.2 + 1.1j])
    full = expand_trace_primal(constraints, active, full_rows=64)
    assert np.allclose(restrict_trace_primal(constraints, full, 64), active,
                       rtol=0.0, atol=1e-14)
    assert np.allclose(full[30], np.exp(0.37j) * active[0]
                       + (-0.25 + 0.5j) * active[1])
    assert full[50] == 0.0 and full[60] == 0.0


def test_owned_rank_injection_returns_only_its_master_rows():
    rank0, _phase = _complex_mpc_map(owned=(10,))
    rank1, _phase = _complex_mpc_map(owned=(20,))
    residual = np.asarray([3.0 + 2.0j, -1.0 + 4.0j])
    rows0, values0 = inject_trace_dual(rank0, residual, 64, owned_only=True)
    rows1, values1 = inject_trace_dual(rank1, residual, 64, owned_only=True)
    assembled = np.zeros(64, dtype=np.complex128)
    assembled[rows0] += values0
    assembled[rows1] += values1
    assert np.array_equal(restrict_trace_dual(rank0, assembled, 64), residual)
