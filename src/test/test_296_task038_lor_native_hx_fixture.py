"""Focused real p-refined positive L2 fixture checks (not formal cases)."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.fullspace_lor_native_hx_fixture import (
    build_real_l2_positive_hx_fixture,
)


def _relative(left: complex, right: complex) -> float:
    return float(abs(left - right) / max(abs(left), abs(right), 1.0))


def _matrix_work_identity(matrix, rng: np.random.Generator) -> tuple[float, float]:
    source = matrix.createVecRight()
    other = matrix.createVecRight()
    action = matrix.createVecLeft()
    other_action = matrix.createVecLeft()
    source.array[:] = rng.standard_normal(source.getLocalSize()) + 1j * rng.standard_normal(
        source.getLocalSize()
    )
    other.array[:] = rng.standard_normal(other.getLocalSize()) + 1j * rng.standard_normal(
        other.getLocalSize()
    )
    matrix.mult(source, action)
    matrix.mult(other, other_action)
    hermitian = _relative(
        other.dot(action), np.conjugate(source.dot(other_action))
    )
    positive = float(np.real(source.dot(action)))
    source.destroy()
    other.destroy()
    action.destroy()
    other_action.destroy()
    return hermitian, positive


def _rectangular_adjoint_identity(forward, adjoint, rng: np.random.Generator) -> float:
    source = forward.createVecRight()
    other = forward.createVecLeft()
    mapped = forward.createVecLeft()
    pulled = adjoint.createVecLeft()
    source.array[:] = rng.standard_normal(source.getLocalSize()) + 1j * rng.standard_normal(
        source.getLocalSize()
    )
    other.array[:] = rng.standard_normal(other.getLocalSize()) + 1j * rng.standard_normal(
        other.getLocalSize()
    )
    forward.mult(source, mapped)
    adjoint.mult(other, pulled)
    relative = _relative(other.dot(mapped), np.conjugate(source.dot(pulled)))
    source.destroy()
    other.destroy()
    mapped.destroy()
    pulled.destroy()
    return relative


def _global_slave_ids(space, mpc) -> np.ndarray:
    index_map = space.dofmap.index_map
    local = np.asarray(
        index_map.local_to_global(np.asarray(mpc.slaves, dtype=np.int32)),
        dtype=np.int64,
    )
    parts = space.mesh.comm.allgather(local)
    if not parts:
        return np.empty(0, dtype=np.int64)
    return np.unique(np.concatenate(parts))


def _assert_zero_slave_rows_and_columns(matrix, row_slaves, column_slaves) -> None:
    row_slaves = {int(value) for value in row_slaves}
    column_slaves = {int(value) for value in column_slaves}
    start, stop = matrix.getOwnershipRange()
    for row in range(int(start), int(stop)):
        columns, values = matrix.getRow(row)
        if row in row_slaves:
            assert values.size == 0
        assert all(int(column) not in column_slaves for column in columns)


def _global_residual_transfer_work_identity(fixture) -> float:
    unique_ids = np.asarray(fixture.lor_topology.unique_edge_ids, dtype=np.uint32)
    low = np.sin(unique_ids.astype(np.float64) * 0.001) + 1j * np.cos(
        unique_ids.astype(np.float64) * 0.001
    )
    reconstructed = fixture._reconstruct_high_from_unique(low)
    source = fixture.high_action.apply(fixture.high_source).copy()
    owner_ids, owner_values = fixture._restrict_high_dual(source)
    high_owned = int(fixture.high_space.dofmap.index_map.size_local)
    lhs_local = np.vdot(
        np.asarray(reconstructed.array[:high_owned], dtype=np.complex128),
        np.asarray(source.array[:high_owned], dtype=np.complex128),
    )
    owner_ids = np.asarray(owner_ids, dtype=np.uint32)
    owner_values = np.asarray(owner_values, dtype=np.complex128)
    owner_source = np.sin(owner_ids.astype(np.float64) * 0.001) + 1j * np.cos(
        owner_ids.astype(np.float64) * 0.001
    )
    rhs_local = np.vdot(owner_source, owner_values)
    lhs = fixture.comm.allreduce(lhs_local, op=MPI.SUM)
    rhs = fixture.comm.allreduce(rhs_local, op=MPI.SUM)
    relative = _relative(lhs, rhs)
    slave_rows = _global_slave_ids(fixture.high_space, fixture.high_floquet.mpc)
    start, stop = reconstructed.getOwnershipRange()
    owned_slave_rows = slave_rows[(slave_rows >= start) & (slave_rows < stop)]
    if owned_slave_rows.size:
        assert np.max(
            np.abs(reconstructed.array[owned_slave_rows - int(start)])
        ) <= 1.0e-14
    reconstructed.destroy()
    source.destroy()
    return relative


def _assert_fixture(fixture) -> None:
    audit = fixture.audit
    assert audit["high_order_matrix_free"] is True
    assert audit["high_order_global_aij"] is False
    assert audit["global_transfer_matrix"] is False
    assert audit["global_numeric_allgather"] is False
    assert audit["metadata_allgather"] is False
    assert audit["de_rham_map_audit"]["production_metadata_replacement_required"] is False
    assert audit["canonical_only_reduction"] is False
    assert audit["full_space_slave_identity_rows"] is True
    assert audit["phase_application"] == "finalized_floquet_mpc_once"
    assert audit["slave_master_complete"] is True
    assert audit["lor_edge_slave_rows"] > 0
    assert audit["lor_node_slave_rows"] > 0
    assert audit["lor_full_edge_rows"] > audit["lor_edge_slave_rows"]
    assert audit["lor_full_node_rows"] > audit["lor_node_slave_rows"]
    assert audit["de_rham_map_audit"]["max_edge_relation_master_global"] < audit[
        "de_rham_map_audit"
    ]["edge_relation_global_rows"]
    assert audit["de_rham_map_audit"]["max_node_relation_master_global"] < audit[
        "de_rham_map_audit"
    ]["node_relation_global_rows"]
    assert np.array_equal(
        fixture.lor_topology.owned_edge_ids,
        fixture.lor_raw_topology.owned_edge_ids,
    )
    assert audit["single_cell_transfer_work_identity_relative"] <= 1.0e-12
    assert audit["transfer_roundtrip_relative"] <= 1.0e-12
    assert audit["transfer_nonzero_source"] is True
    assert audit["transfer_input_norm"] > 0.0
    assert audit["transfer_owner_packet_norm"] > 0.0
    for level_name, level_key, cell_key in (
        ("high", "high_cell_count", "high_cell_count"),
        ("lor", "lor_cell_count", "lor_cell_count"),
    ):
        coefficient_audit = audit["piecewise_coefficients"][level_name]
        counts = coefficient_audit["cell_counts"]
        assert sum(counts.values()) == audit[cell_key]
        assert set(counts) == {"air", "substrate", "grating"}
        assert all(value >= 0 for value in counts.values())
        assert all(
            coefficient_audit["positive_coefficients"][name]["mu_inverse"] > 0.0
            and coefficient_audit["positive_coefficients"][name][
                "k0_squared_abs_epsilon"
            ]
            > 0.0
            for name in counts
        )
    hx_audit = audit["hx_audit"]
    assert hx_audit["maximum_levels"] == 8
    assert 1 <= hx_audit["observed_levels"] <= 8
    assert hx_audit["coarse_ksp_type"] == "preonly"
    assert hx_audit["coarse_pc_type"] == "jacobi"
    assert hx_audit["one_shared_scalar_hierarchy"] is True
    assert hx_audit["global_transfer_matrix"] is False
    assert hx_audit["global_numeric_allgather"] is False


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial real fixture")
@pytest.mark.parametrize("degree", [2, 3])
def test_l2_real_positive_fullspace_fixture(degree: int) -> None:
    fixture = build_real_l2_positive_hx_fixture(degree, MPI.COMM_WORLD)
    try:
        _assert_fixture(fixture)
        rng = np.random.default_rng(20260823)
        edge_hermitian, edge_positive = _matrix_work_identity(
            fixture.edge_matrix, rng
        )
        node_hermitian, node_positive = _matrix_work_identity(
            fixture.node_matrix, rng
        )
        assert _rectangular_adjoint_identity(
            fixture.gradient, fixture.gradient_adjoint, rng
        ) <= 1.0e-12
        edge_slaves = _global_slave_ids(
            fixture.lor_edge_space, fixture.lor_edge_floquet.mpc
        )
        node_slaves = _global_slave_ids(
            fixture.lor_node_space, fixture.lor_node_floquet
        )
        for prolongation, restriction in zip(
            fixture.vector_prolongations,
            fixture.vector_restrictions,
            strict=True,
        ):
            assert _rectangular_adjoint_identity(prolongation, restriction, rng) <= 1.0e-12
            _assert_zero_slave_rows_and_columns(prolongation, edge_slaves, node_slaves)
        _assert_zero_slave_rows_and_columns(fixture.gradient, edge_slaves, node_slaves)
        assert _global_residual_transfer_work_identity(fixture) <= 1.0e-12
        assert edge_hermitian <= 1.0e-12
        assert node_hermitian <= 1.0e-12
        assert fixture.edge_matrix.isHermitian(tol=1.0e-12)
        assert fixture.node_matrix.isHermitian(tol=1.0e-12)
        assert edge_positive > 0.0
        assert node_positive > 0.0
        high_first, high_second = fixture.apply_high()
        lor_first, lor_second = fixture.apply_lor()
        try:
            assert np.all(np.isfinite(high_first.array))
            assert np.all(np.isfinite(lor_first.array))
            assert _relative(high_first.norm(), high_second.norm()) <= 1.0e-13
            assert _relative(lor_first.norm(), lor_second.norm()) <= 1.0e-13
        finally:
            high_first.destroy()
            high_second.destroy()
            lor_first.destroy()
            lor_second.destroy()
        residual_first = fixture.apply_residual_through_lor()
        residual_second = fixture.apply_residual_through_lor()
        try:
            assert np.all(np.isfinite(residual_first.array))
            assert residual_first.norm() > 0.0
            assert _relative(residual_first.norm(), residual_second.norm()) <= 1.0e-13
        finally:
            residual_first.destroy()
            residual_second.destroy()
    finally:
        fixture.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 real fixture")
def test_l2_real_p2_mpi2_full_row_ownership_full_chain() -> None:
    fixture = build_real_l2_positive_hx_fixture(2, MPI.COMM_WORLD)
    try:
        _assert_fixture(fixture)
        assert _global_residual_transfer_work_identity(fixture) <= 1.0e-12
        high_first, high_second = fixture.apply_high()
        lor_first, lor_second = fixture.apply_lor()
        try:
            assert np.all(np.isfinite(high_first.array))
            assert np.all(np.isfinite(lor_first.array))
            assert _relative(high_first.norm(), high_second.norm()) <= 1.0e-13
            assert _relative(lor_first.norm(), lor_second.norm()) <= 1.0e-13
        finally:
            high_first.destroy()
            high_second.destroy()
            lor_first.destroy()
            lor_second.destroy()
        first = fixture.apply_residual_through_lor()
        second = fixture.apply_residual_through_lor()
        try:
            assert np.all(np.isfinite(first.array))
            assert np.all(np.isfinite(second.array))
            assert _relative(first.norm(), second.norm()) <= 1.0e-13
        finally:
            first.destroy()
            second.destroy()
    finally:
        fixture.destroy()
