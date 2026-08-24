"""Tiny full-side V3-2 action against an independent block-Schur authority."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.hybrid_interface_coupled import (
    CoupledFullSidePetrovAction,
    CoupledInterfacePetrovAction,
)


def _block(rows: int, columns: int, seed: int, diagonal: float = 0.0) -> np.ndarray:
    row = np.arange(rows, dtype=float)[:, None]
    column = np.arange(columns, dtype=float)[None, :]
    value = (
        0.09 * (seed + 1.0) * (row + 1.0)
        + 0.031 * (column + 1.0)
        + 0.017j * (2.0 * row + column + seed + 1.0)
    ).astype(np.complex128)
    if rows == columns:
        value += (diagonal + 0.08j * (seed + 1.0)) * np.eye(rows, dtype=np.complex128)
    return value


def _fixture() -> dict[str, object]:
    lower = upper = 2
    interior = 2
    gamma = lower + upper

    e0 = _block(lower, lower, 1, 3.0)
    e2 = _block(upper, upper, 2, 3.2)
    e1 = np.block(
        [
            [_block(lower, lower, 3, 3.5), _block(lower, upper, 4)],
            [_block(upper, lower, 5), _block(upper, upper, 6, 3.7)],
        ]
    )
    b0 = _block(interior, interior, 7, 4.0)
    b1 = _block(interior, interior, 8, 4.3)
    b2 = _block(interior, interior, 9, 4.6)
    c0 = _block(lower, interior, 10)
    c1 = _block(gamma, interior, 11)
    c2 = _block(upper, interior, 12)
    d0 = _block(interior, lower, 13)
    d1 = _block(interior, gamma, 14)
    d2 = _block(interior, upper, 15)

    zero_gi = np.zeros((gamma, 3 * interior), dtype=np.complex128)
    c = zero_gi.copy()
    c[:lower, :interior] = c0
    c[:gamma, interior : 2 * interior] += c1
    c[lower:, 2 * interior :] = c2
    d = np.zeros((3 * interior, gamma), dtype=np.complex128)
    d[:interior, :lower] = d0
    d[interior : 2 * interior, :] = d1
    d[2 * interior :, lower:] = d2
    b = np.block(
        [
            [
                b0,
                np.zeros((interior, interior), dtype=np.complex128),
                np.zeros((interior, interior), dtype=np.complex128),
            ],
            [
                np.zeros((interior, interior), dtype=np.complex128),
                b1,
                np.zeros((interior, interior), dtype=np.complex128),
            ],
            [
                np.zeros((interior, interior), dtype=np.complex128),
                np.zeros((interior, interior), dtype=np.complex128),
                b2,
            ],
        ]
    )
    e = e1 + np.block(
        [
            [e0, np.zeros((lower, upper), dtype=np.complex128)],
            [np.zeros((upper, lower), dtype=np.complex128), e2],
        ]
    )
    schur = e - c @ np.linalg.solve(b, d)
    full = np.block([[e, c], [d, b]])

    z = np.eye(gamma, dtype=np.complex128) + _block(gamma, gamma, 16) * 0.01
    y = 1.3 * np.eye(gamma, dtype=np.complex128) + _block(gamma, gamma, 17) * 0.01
    joint = y.conj().T @ schur @ z

    def solve_group(group: int, rhs: np.ndarray) -> np.ndarray:
        return np.linalg.solve((b0, b1, b2)[group], rhs)

    def solve_interior(rhs: np.ndarray) -> np.ndarray:
        result = np.empty(3 * interior, dtype=np.complex128)
        for group in range(3):
            start = group * interior
            result[start : start + interior] = solve_group(
                group, rhs[start : start + interior]
            )
        return result

    def base_solve(rhs: np.ndarray) -> np.ndarray:
        result = np.zeros_like(rhs)
        result[gamma:] = solve_interior(rhs[gamma:])
        return result

    def restrict(residual: np.ndarray) -> np.ndarray:
        return residual[:gamma]

    def synthesize(coefficients: np.ndarray) -> np.ndarray:
        return z @ coefficients

    def back_sub(gamma_correction: np.ndarray) -> np.ndarray:
        result = np.empty(gamma + 3 * interior, dtype=np.complex128)
        result[:gamma] = gamma_correction
        result[gamma:] = -solve_interior(d @ gamma_correction)
        return result

    source = _block(gamma + 3 * interior, 1, 18).ravel()
    return {
        "gamma": gamma,
        "full": full,
        "schur": schur,
        "z": z,
        "y": y,
        "joint": joint,
        "base_solve": base_solve,
        "restrict": restrict,
        "synthesize": synthesize,
        "back_sub": back_sub,
        "source": source,
        "zero_source": np.zeros_like(source),
    }


def _action(data: dict[str, object], joint: np.ndarray) -> CoupledFullSidePetrovAction:
    full = data["full"]
    return CoupledFullSidePetrovAction(
        joint,
        data["y"],
        full_size=full.shape[0],
        base_solve=data["base_solve"],
        bare_apply=lambda value: full @ value,
        interface_restrict=data["restrict"],
        z_synthesize=data["synthesize"],
        harmonic_back_sub=data["back_sub"],
        group_factor_count=3,
    )


def test_full_side_action_matches_direct_block_schur_and_residual() -> None:
    data = _fixture()
    action = _action(data, data["joint"])
    source = data["source"]
    full = data["full"]
    direct = np.linalg.solve(full, source)
    result = action.apply(source)
    relative_solution = np.linalg.norm(result - direct) / np.linalg.norm(direct)
    relative_residual = np.linalg.norm(full @ result - source) / np.linalg.norm(source)
    assert relative_solution <= 1.0e-12
    assert relative_residual <= 1.0e-12
    assert action.diagnostics["cross_section_group_factor_count"] == 3
    assert action.diagnostics["exact_interface_schur_oracle_object_count"] == 0
    assert action.diagnostics["full_side_exact_factor_count"] == 0
    assert action.diagnostics["global_direct_factor_count"] == 0
    assert action.diagnostics["reduced_dense_factor_count"] == 1
    assert action.diagnostics["normal_equations"] is False
    assert action.diagnostics["packet_dependent"] is True
    assert action.diagnostics["apply_count"] == 1
    assert np.linalg.norm(action.apply(data["zero_source"])) == 0.0
    assert np.linalg.norm(data["y"].conj().T @ data["z"] - np.eye(4)) > 1.0e-3
    action.destroy()
    assert action.diagnostics["destroyed"] is True
    assert action.diagnostics["dense_factor_retained"] is False
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply(source)


def test_cross_block_omission_fails_full_side_residual() -> None:
    data = _fixture()
    omitted = data["schur"].copy()
    gamma = data["gamma"]
    lower = gamma // 2
    omitted[:lower, lower:] = 0.0
    omitted[lower:, :lower] = 0.0
    omitted_joint = data["y"].conj().T @ omitted @ data["z"]
    action = _action(data, omitted_joint)
    result = action.apply(data["source"])
    full = data["full"]
    relative_residual = np.linalg.norm(full @ result - data["source"]) / np.linalg.norm(
        data["source"]
    )
    assert relative_residual > 0.25


def test_full_side_action_repeat_and_linearity_are_deterministic() -> None:
    data = _fixture()
    action = _action(data, data["joint"])
    source = data["source"]
    other = np.roll(source, 1)
    first = action.apply(source)
    second = action.apply(source)
    combination = action.apply(1.7 * source - 0.4j * other)
    expected = 1.7 * first - 0.4j * action.apply(other)
    assert np.linalg.norm(first - second) / np.linalg.norm(first) <= 1.0e-12
    assert np.linalg.norm(combination - expected) / np.linalg.norm(expected) <= 1.0e-12


def test_full_side_rank_consistency_under_mpi() -> None:
    data = _fixture()
    action = _action(data, data["joint"])
    result = action.apply(data["source"])
    local_error = float(
        np.linalg.norm(data["full"] @ result - data["source"])
        / np.linalg.norm(data["source"])
    )
    errors = MPI.COMM_WORLD.allgather(local_error)
    assert max(errors) <= 1.0e-12
    action.destroy()


def test_distributed_gamma_petrov_uses_small_allreduce() -> None:
    data = _fixture()
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()
    gamma = int(data["gamma"])
    start = rank * gamma // size
    end = (rank + 1) * gamma // size
    rhs = _block(gamma, 1, 19).ravel()
    action = CoupledInterfacePetrovAction(
        data["joint"],
        data["z"][start:end, :],
        data["y"][start:end, :],
        comm=comm,
    )
    coefficients = np.linalg.solve(data["joint"], data["y"].conj().T @ rhs)
    expected = data["z"] @ coefficients
    actual = action.apply(rhs[start:end])
    local_relative_error = np.linalg.norm(actual - expected[start:end]) / max(
        np.linalg.norm(expected[start:end]), 1.0e-30
    )
    assert local_relative_error <= 1.0e-12
    assert action.diagnostics["owner_local_basis_contract"] is True
    assert action.diagnostics["basis_replication_verified"] is False
    assert action.diagnostics["fe_numeric_allgather"] is False
    assert action.diagnostics["apply_count"] == 1
    action.destroy()
    assert action.diagnostics["dense_factor_retained"] is False
