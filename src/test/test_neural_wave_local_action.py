"""Small independent non-Hermitian MPC/DtN support and adjoint fixtures."""

import numpy as np
import pytest
from scipy.linalg import block_diag

from src.solvers.feinn_native import FullNativePacket
from src.solvers.neural_wave_local_action import LocalWaveAction


def toy_packet():
    rng = np.random.default_rng(4213008)
    n, nc, dim, ports = 9, 5, 3, 4
    erows = np.r_[np.arange(nc * dim), 1, 4, 12]
    eids = np.r_[rng.integers(0, n, nc * dim), 6, 0, 2]
    evals = np.exp(1j * rng.uniform(-2, 2, len(erows)))
    tensors = rng.normal(size=(2, dim, dim)) + 1j * rng.normal(size=(2, dim, dim))
    classes = np.array([0, 1, 1, 0, 1])
    br, bp = np.meshgrid(np.arange(n), np.arange(ports), indexing="ij")
    bv = rng.normal(size=br.size) + 1j * rng.normal(size=br.size)
    dv = rng.normal(size=br.size) + 1j * rng.normal(size=br.size)
    arrays = dict(
        masters=np.arange(n), full_rows=np.array(n),
        cell_dofs=np.arange(nc * dim).reshape(nc, dim),
        erows=erows, eids=eids, evals=evals, F=tensors, classes=classes,
        H=np.arange(1, ports + 1, dtype=float),
        br=br.ravel(), bp=bp.ravel(), bv=bv,
        dr=br.ravel(), dp=bp.ravel(), dv=dv,
        g=rng.normal(size=n) + 1j * rng.normal(size=n),
        gp=rng.normal(size=ports) + 1j * rng.normal(size=ports),
    )
    expansion = np.zeros((nc * dim, n), complex)
    np.add.at(expansion, (erows, eids), evals)
    B = np.zeros((n, ports), complex)
    D = np.zeros((ports, n), complex)
    np.add.at(B, (br.ravel(), bp.ravel()), bv)
    np.add.at(D, (bp.ravel(), br.ravel()), dv)
    independent = (
        expansion.conj().T @ block_diag(*(tensors[j] for j in classes)) @ expansion
        + B @ np.diag(1 / arrays["H"]) @ D
    )
    return rng, FullNativePacket(arrays), independent


@pytest.mark.parametrize("support", [[0], [0, 3, 7], list(range(9))])
def test_original_nonhermitian_mpc_ports_and_real_adjoint(support):
    rng, action, independent = toy_packet()
    local = LocalWaveAction(action, support)
    columns = np.zeros((action.size, 6), complex)
    columns[support] = rng.normal(size=(len(support), 6)) + 1j * rng.normal(
        size=(len(support), 6)
    )
    actual = local.columns(columns)
    np.testing.assert_allclose(actual, independent @ columns, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        actual, np.column_stack([action.apply(c) for c in columns.T]),
        rtol=1e-12, atol=1e-12,
    )
    g = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
    adjoint = local.adjoint(g)
    np.testing.assert_allclose(
        adjoint[support], (independent.conj().T @ g)[support],
        rtol=1e-12, atol=1e-12,
    )
    assert np.count_nonzero(adjoint[~local.mask]) == 0
    for j in range(6):
        assert abs(np.vdot(g, actual[:, j]).real - np.vdot(adjoint, columns[:, j]).real) < 1e-10
    assert action.counts["A"] == 12
    assert action.counts["AH"] == 1
    assert local.counts == dict(columns=6, adjoint=1)


def test_support_validation_no_amplitude_threshold_or_truncated_output():
    _, action, _ = toy_packet()
    with pytest.raises(ValueError, match="INPUT_SUPPORT_INVALID"):
        LocalWaveAction(action, [])
    with pytest.raises(ValueError, match="INPUT_SUPPORT_INVALID"):
        LocalWaveAction(action, [action.size])
    local = LocalWaveAction(action, [0])
    columns = np.zeros((action.size, 1), complex)
    columns[0] = 1
    # A local input has a complete, nonlocal output through native DtN.
    assert np.count_nonzero(local.columns(columns)[~local.mask]) > 0
    columns[1] = 1e-200
    with pytest.raises(ValueError, match="OUTSIDE_PROVEN_SUPPORT"):
        local.columns(columns)
    with pytest.raises(ValueError, match="OUTSIDE_PROVEN_SUPPORT"):
        local.columns(np.zeros((action.size, 25), complex))
