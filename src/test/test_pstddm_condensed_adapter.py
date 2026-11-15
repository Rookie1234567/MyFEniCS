from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.pstddm_condensed_adapter import (
    apply_full_fe_port_bridge,
    balanced_partition_bounds,
    expand_trace_primal,
    inject_trace_dual,
    prepare_trace_master_adapter,
    restrict_trace_dual,
    restrict_trace_primal,
)
from src.runners.pstddm_p6_convergence import axis_values_for_h


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


def test_frozen_h10_entry_axes_are_exact_and_do_not_assume_ten_nm_edges():
    axes = axis_values_for_h(10.0)
    assert axes["x"] == (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0)
    assert axes["y"] == (0.0, 7.5, 15.0, 25.0, 35.0, 42.5, 50.0)
    assert axes["z"] == tuple([-10.0, *map(float, range(0, 121, 10)), 130.0])
    assert tuple(len(axes[name]) - 1 for name in ("x", "y", "z")) == (6, 6, 14)
    assert max(np.diff(axes["x"])) == 8.5


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


def test_full_fe_port_bridge_keeps_interior_c_d_and_complex_mpc_phase():
    from scipy import sparse

    phase = np.exp(0.37j)
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray([0, 1], dtype=np.int64),
        original_to_active={0: 0, 1: 1},
        expansion_by_original={
            0: (np.asarray([0]), np.asarray([1.0 + 0.0j])),
            1: (np.asarray([1]), np.asarray([1.0 + 0.0j])),
            2: (np.asarray([0]), np.asarray([phase])),
        },
        full_trace_rows=3,
        active_rows=2,
    )
    trace_adapter = prepare_trace_master_adapter(constraints, full_rows=4)
    transformation = sparse.csr_matrix(
        np.asarray(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [phase, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.complex128,
        )
    )
    raw_C = sparse.csr_matrix(
        np.asarray([[0.0], [0.0], [2.0 - 1.0j], [0.5 + 0.25j]], dtype=np.complex128)
    )
    raw_D = sparse.csr_matrix(
        np.asarray([[0.0, 0.0, -0.75 + 0.5j, 1.25 - 0.2j]], dtype=np.complex128)
    )
    full_C = transformation.getH() @ raw_C
    full_D = raw_D @ transformation
    assert full_C[2, 0] != 0.0 and full_D[0, 2] != 0.0

    def lift(trace_dual):
        rows, values = trace_adapter.lift_dual(trace_dual)
        raw = np.zeros(4, dtype=np.complex128)
        np.add.at(raw, rows, values)
        return np.asarray(transformation.getH() @ raw).reshape(-1)

    def restrict(full_primal):
        return trace_adapter.restrict_primal(transformation @ full_primal)

    full_core = np.asarray(
        [[1.0 + 0.1j, 0.2j, 0.35], [0.1, 1.2 - 0.2j, -0.4j], [0.5, 0.2j, 0.9]],
        dtype=np.complex128,
    )
    trace_dual = np.asarray([1.0 + 0.3j, -0.4 + 0.8j])
    auxiliary_dual = np.asarray([0.7 - 0.2j])
    trace_primal, auxiliary_result, full_primal = apply_full_fe_port_bridge(
        trace_dual,
        auxiliary_dual,
        full_C=full_C,
        full_D=full_D,
        lift_trace_dual=lift,
        source_transfer=lambda value: full_core @ value,
        restrict_trace_primal=restrict,
    )

    expected_rhs = lift(trace_dual) - full_C @ auxiliary_dual
    expected_full = full_core @ expected_rhs
    np.testing.assert_allclose(full_primal, expected_full, rtol=0.0, atol=1e-14)
    np.testing.assert_allclose(trace_primal, restrict(expected_full), rtol=0.0, atol=1e-14)
    np.testing.assert_allclose(
        auxiliary_result,
        auxiliary_dual - full_D @ expected_full,
        rtol=0.0,
        atol=1e-14,
    )

    # This is the rejected trace-only formula: its nonzero interior C/D rows
    # vanish, so the test must detect the resulting change in both outputs.
    trace_core = full_core[:2, :2]
    trace_C = full_C[:2, :]
    trace_D = full_D[:, :2]
    wrong_trace = trace_core @ (trace_dual - trace_C @ auxiliary_dual)
    wrong_auxiliary = auxiliary_dual - trace_D @ wrong_trace
    assert not np.allclose(trace_primal, wrong_trace, rtol=0.0, atol=1e-12)
    assert not np.allclose(auxiliary_result, wrong_auxiliary, rtol=0.0, atol=1e-12)


def test_full_fe_bridge_runs_real_n4_source_transfer_and_right_fgmres_call_chain():
    from scipy import sparse

    from src.solvers.pstddm_comparison import flexible_gmres
    from src.solvers.pstddm_source_transfer import PureSourceTransfer

    phase = np.exp(0.37j)
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray([0, 1], dtype=np.int64),
        original_to_active={0: 0, 1: 1},
        expansion_by_original={
            0: (np.asarray([0]), np.asarray([1.0 + 0.0j])),
            1: (np.asarray([1]), np.asarray([1.0 + 0.0j])),
            2: (np.asarray([0]), np.asarray([phase])),
        },
        full_trace_rows=3,
        active_rows=2,
    )
    trace_adapter = prepare_trace_master_adapter(constraints, full_rows=4)
    transformation = sparse.csr_matrix(
        np.asarray(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [phase, 0.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.complex128,
        )
    )
    raw_C = sparse.csr_matrix(
        np.asarray([[0.0], [0.0], [1.2 - 0.3j], [0.4 + 0.7j]], dtype=np.complex128)
    )
    raw_D = sparse.csr_matrix(
        np.asarray([[0.0, 0.0, -0.5 + 0.2j, 0.8 - 0.4j]], dtype=np.complex128)
    )
    full_C = transformation.getH() @ raw_C
    full_D = raw_D @ transformation
    assert full_C[2, 0] != 0.0 and full_D[0, 2] != 0.0

    def lift(trace_dual):
        rows, values = trace_adapter.lift_dual(trace_dual)
        raw = np.zeros(4, dtype=np.complex128)
        np.add.at(raw, rows, values)
        return np.asarray(transformation.getH() @ raw).reshape(-1)

    def restrict(full_primal):
        return trace_adapter.restrict_primal(transformation @ full_primal)

    masks = [sparse.eye(3, dtype=np.complex128, format="csr") * 0.25 for _ in range(4)]
    zero = sparse.csr_matrix((3, 3), dtype=np.complex128)
    pair_calls = []
    mass_solve_calls = []
    apply_statistics = []

    def solve_pair(pair, rhs):
        pair_calls.append((pair, np.asarray(rhs).copy()))
        return np.asarray(rhs, dtype=np.complex128).copy()

    def mass_solve(rhs):
        mass_solve_calls.append(np.asarray(rhs).copy())
        return np.asarray(rhs, dtype=np.complex128).copy()

    def reconstruct(layer, up, down):
        value = np.zeros(3, dtype=np.complex128)
        if up is not None:
            value += up
        if down is not None:
            value += down
        return masks[layer] @ value

    core = PureSourceTransfer(
        partition_mass=masks,
        forward_beta_mass=[0.5 * value for value in masks],
        mass_solve=mass_solve,
        solve_pair=solve_pair,
        forward_commutator=lambda _pair, _value: np.zeros(3, dtype=np.complex128),
        reverse_commutator=lambda _pair, _value: np.zeros(3, dtype=np.complex128),
        reconstruct_load=reconstruct,
    )

    def preconditioner(residual):
        trace, auxiliary, _full = apply_full_fe_port_bridge(
            residual[:2],
            residual[2:],
            full_C=full_C,
            full_D=full_D,
            lift_trace_dual=lift,
            source_transfer=core,
            restrict_trace_primal=restrict,
        )
        apply_statistics.append(core.last_statistics.copy())
        return np.concatenate((trace, auxiliary))

    # The condensed block keeps a non-identity H, while the PC uses only the
    # original raw-C/D full-FE bridge. The outer solver still sees this full A.
    C_trace = sparse.csr_matrix(np.asarray([[0.2 + 0.1j], [-0.3j]]))
    D_trace = sparse.csr_matrix(np.asarray([[0.1 - 0.2j, 0.25 + 0.1j]]))
    A = sparse.bmat(
        [[sparse.csr_matrix([[2.0, 0.1j], [0.2, 1.7]]), C_trace],
         [D_trace, sparse.csr_matrix([[1.3 + 0.05j]])]],
        format="csr",
        dtype=np.complex128,
    )
    rhs = np.asarray([0.5 + 0.2j, -0.3 + 0.1j, 0.7 - 0.4j])
    initial = preconditioner(rhs)
    solution, audit = flexible_gmres(
        A, rhs, preconditioner, initial, restart=3, max_iterations=5, tolerance=1.0e-8
    )
    from src.solvers.pstddm_comparison import true_residual

    final_original_residual = true_residual(A, solution, rhs)
    assert abs(A[-1, -1] - 1.0) > 1.0e-3
    assert core.apply_count == audit["iterations"] + 1
    assert len(apply_statistics) == core.apply_count
    assert len(pair_calls) == core.apply_count * 6
    assert len(mass_solve_calls) == core.apply_count * 2
    assert all(item["local_solve_count"] == 6 for item in apply_statistics)
    assert all(item["mass_solve_count"] == 2 for item in apply_statistics)
    assert final_original_residual <= 1.0e-8
    assert np.isclose(final_original_residual, audit["true_residual"], rtol=0.0, atol=1.0e-14)
    assert np.isfinite(solution).all()
    assert all(np.isfinite(item["true_residual"]) for item in audit["history"])
