"""Focused L2 native-complex LOR-HX algebra and MPI identity tests."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.fullspace_lor_native_hx import (
    LOR_HX_EDGE_JACOBI_OMEGA,
    LOR_HX_FORBIDDEN_PC_TYPES,
    LOR_HX_GAMG_MAX_LEVELS,
    NativeComplexLORHX,
)
from src.solvers.fullspace_lor_transfer import (
    _edge_endpoints,
    build_local_lor_transfer,
)
from src.solvers.fullspace_lor_topology import _pack_canonical_edges


def _node_id(index: tuple[int, int, int], degree: int) -> int:
    width = degree + 1
    i, j, k = (int(value) for value in index)
    return int(i + width * (j + width * k))


def _aij_from_block(
    block: np.ndarray,
    global_rows: int,
    global_cols: int,
    row_offset: int,
    col_offset: int,
    comm: MPI.Comm,
) -> PETSc.Mat:
    block = np.asarray(block, dtype=np.complex128)
    matrix = PETSc.Mat().createAIJ(
        [int(global_rows), int(global_cols)],
        nnz=max(1, min(int(global_cols), int(np.count_nonzero(block, axis=1).max()))),
        comm=comm,
    )
    matrix.setUp()
    start, stop = matrix.getOwnershipRange()
    if (int(start), int(stop)) != (
        int(row_offset),
        int(row_offset + block.shape[0]),
    ):
        matrix.destroy()
        raise RuntimeError("test block does not match PETSc owned row range")
    for local_row in range(block.shape[0]):
        nonzero = np.flatnonzero(np.abs(block[local_row]) > 0.0)
        for local_col in nonzero:
            matrix.setValue(
                int(row_offset + local_row),
                int(col_offset + local_col),
                complex(block[local_row, local_col]),
            )
    matrix.assemble()
    return matrix


def _pi_block(local, axis: int) -> np.ndarray:
    degree = int(local.nodes.size - 1)
    edge_count = 3 * degree * (degree + 1) ** 2
    node_count = (degree + 1) ** 3
    starts, ends = _edge_endpoints(degree)
    block = np.zeros((edge_count, node_count), dtype=np.complex128)
    axis_count = degree * (degree + 1) ** 2
    for edge in range(axis * axis_count, (axis + 1) * axis_count):
        start = tuple(starts[edge])
        end = tuple(ends[edge])
        edge_length = float(
            local.widths[axis] * (local.nodes[end[axis]] - local.nodes[start[axis]])
        )
        edge_weight = 0.5 * edge_length
        block[edge, _node_id(start, degree)] = edge_weight
        block[edge, _node_id(end, degree)] = edge_weight
    return block


def _build_case(degree: int, comm: MPI.Comm):
    local = build_local_lor_transfer(degree)
    edge_count = int(local.lor_matrix.shape[0])
    node_count = int(local.lor_gradient.shape[1])
    size = int(comm.size)
    rank = int(comm.rank)
    edge_matrix = _aij_from_block(
        local.lor_matrix,
        size * edge_count,
        size * edge_count,
        rank * edge_count,
        rank * edge_count,
        comm,
    )
    gradient_block = np.asarray(local.lor_gradient, dtype=np.complex128)
    gradient_adjoint_block = gradient_block.conj().T
    nodal_block = gradient_adjoint_block @ gradient_block + np.eye(
        node_count, dtype=np.complex128
    )
    nodal_matrix = _aij_from_block(
        nodal_block,
        size * node_count,
        size * node_count,
        rank * node_count,
        rank * node_count,
        comm,
    )
    gradient = _aij_from_block(
        gradient_block,
        size * edge_count,
        size * node_count,
        rank * edge_count,
        rank * node_count,
        comm,
    )
    gradient_adjoint = _aij_from_block(
        gradient_adjoint_block,
        size * node_count,
        size * edge_count,
        rank * node_count,
        rank * edge_count,
        comm,
    )
    prolongations = []
    restrictions = []
    for axis in range(3):
        prolongation_block = _pi_block(local, axis)
        restriction_block = prolongation_block.conj().T
        prolongations.append(
            _aij_from_block(
                prolongation_block,
                size * edge_count,
                size * node_count,
                rank * edge_count,
                rank * node_count,
                comm,
            )
        )
        restrictions.append(
            _aij_from_block(
                restriction_block,
                size * node_count,
                size * edge_count,
                rank * node_count,
                rank * edge_count,
                comm,
            )
        )
    hx = NativeComplexLORHX(
        edge_matrix,
        nodal_matrix,
        gradient,
        gradient_adjoint,
        prolongations,
        restrictions,
    )
    return local, hx, (
        edge_matrix,
        nodal_matrix,
        gradient,
        gradient_adjoint,
        *prolongations,
        *restrictions,
    )


def test_l2_vector_nodal_interpolation_adjoint_and_edge_length() -> None:
    local = build_local_lor_transfer(3)
    starts, ends = _edge_endpoints(3)
    node_count = (local.nodes.size) ** 3
    edge_count = int(local.audit["lor_edge_dofs"])
    x = np.arange(node_count, dtype=np.float64) + (0.25 + 0.5j)
    y = np.arange(edge_count, dtype=np.float64) + (0.75 - 0.125j)
    ones = np.ones(node_count, dtype=np.complex128)
    degree = 3
    axis_count = degree * (degree + 1) ** 2
    for axis in range(3):
        interpolation = _pi_block(local, axis)
        adjoint = interpolation.conj().T
        left = np.vdot(interpolation @ x, y)
        right = np.vdot(x, adjoint @ y)
        relative = abs(left - right) / max(abs(left), abs(right), 1.0)
        assert relative <= 1.0e-12

        edge = axis * axis_count
        start = tuple(starts[edge])
        end = tuple(ends[edge])
        assert np.count_nonzero(np.abs(interpolation[edge]) > 0.0) == 2
        assert np.count_nonzero(
            np.abs(
                interpolation[axis * axis_count : (axis + 1) * axis_count, :]
            )
            > 0.0
        ) == 2 * axis_count
        assert np.count_nonzero(
            np.abs(interpolation[: axis * axis_count, :]) > 0.0
        ) == 0
        assert np.count_nonzero(
            np.abs(interpolation[(axis + 1) * axis_count :, :]) > 0.0
        ) == 0
        expected_length = local.widths[axis] * (
            local.nodes[end[axis]] - local.nodes[start[axis]]
        )
        assert expected_length > 0.0
        assert abs(np.sum(interpolation[edge] @ ones) - expected_length) <= 1.0e-14


def _destroy_case(hx: NativeComplexLORHX, matrices: tuple[PETSc.Mat, ...]) -> None:
    hx.destroy()
    for matrix in matrices:
        matrix.destroy()


def _source_vectors(local, edge_matrix: PETSc.Mat, gradient: PETSc.Mat, nodal_matrix: PETSc.Mat):
    edge = edge_matrix.createVecRight()
    values = np.arange(edge.getLocalSize(), dtype=np.float64)
    edge.array[:] = np.sin(values + 0.25) + 1j * np.cos(0.5 * values + 0.75)
    checkerboard = edge.duplicate()
    checkerboard.array[:] = np.where(np.arange(edge.getLocalSize()) % 2, -1.0, 1.0)
    node = nodal_matrix.createVecRight()
    node.array[:] = np.cos(np.arange(node.getLocalSize()) + 0.5)
    gradient_field = edge.duplicate()
    gradient.mult(node, gradient_field)
    curl_field = edge.duplicate()
    curl_field.array[:] = np.cos(1.7 * values) + 1j * np.sin(2.3 * values)
    node.destroy()
    return (edge, gradient_field, curl_field, checkerboard)


def _rho(hx: NativeComplexLORHX, edge_matrix: PETSc.Mat, source: PETSc.Vec) -> float:
    output = hx.apply(source)
    action = edge_matrix.createVecLeft()
    residual = source.duplicate()
    edge_matrix.mult(output, action)
    source.copy(residual)
    residual.axpy(-1.0 + 0.0j, action)
    value = float(residual.norm() / max(source.norm(), np.finfo(float).tiny))
    output.destroy()
    action.destroy()
    residual.destroy()
    return value


@pytest.mark.parametrize("degree", [2, 3])
def test_l2_serial_positive_hx_contract(degree: int) -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial algebra case")
    local, hx, matrices = _build_case(degree, MPI.COMM_SELF)
    edge_matrix, nodal_matrix, gradient, gradient_adjoint = matrices[:4]
    try:
        edge_count = 3 * degree * (degree + 1) ** 2
        assert local.nodes.size == degree + 1
        assert edge_count == local.audit["lor_edge_dofs"]
        assert local.lor_matrix.shape == (edge_count, edge_count)
        assert np.min(np.linalg.eigvalsh(local.lor_matrix)) > 0.0
        nodal_reference = local.lor_gradient.conj().T @ local.lor_gradient + np.eye(
            (degree + 1) ** 3
        )
        assert np.min(np.linalg.eigvalsh(nodal_reference)) > 0.0
        assert np.linalg.norm(local.lor_curl_incidence @ local.lor_gradient) <= 1.0e-12
        audit = hx.audit
        assert audit["edge_jacobi_omega"] == LOR_HX_EDGE_JACOBI_OMEGA
        assert audit["maximum_levels"] == LOR_HX_GAMG_MAX_LEVELS == 8
        assert 1 <= audit["observed_levels"] <= 8
        assert audit["pc_type"] == "gamg"
        assert audit["pc_gamg_type"] == "agg"
        assert audit["coarse_ksp_type"] == "preonly"
        assert audit["coarse_pc_type"] == "jacobi"
        assert not set(audit["smoother_pc_types"]) & LOR_HX_FORBIDDEN_PC_TYPES
        assert audit["one_shared_scalar_hierarchy"]
        assert audit["hierarchy_object_count"] == 1
        sources = _source_vectors(local, edge_matrix, gradient, nodal_matrix)
        for source in sources:
            before = source.array.copy()
            before_sha = hashlib.sha256(before.tobytes()).hexdigest()
            pre_jacobi = source.duplicate()
            hx._edge_jacobi(source, pre_jacobi)
            assert np.linalg.norm(pre_jacobi.array) > 0.0
            pre_jacobi.destroy()
            first = hx.apply(source)
            second = hx.apply(source)
            assert np.array_equal(source.array, before)
            assert hashlib.sha256(source.array.tobytes()).hexdigest() == before_sha
            assert np.all(np.isfinite(first.array))
            assert np.all(np.isfinite(second.array))
            assert np.linalg.norm(first.array - second.array) / max(
                np.linalg.norm(first.array), 1.0
            ) <= 1.0e-13
            assert np.isfinite(_rho(hx, edge_matrix, source))
            first.destroy()
            second.destroy()
            source.destroy()
        assert hx.audit["apply_count"] == 12
        assert hx.audit["last_nodal_correction_count"] == 4
    finally:
        _destroy_case(hx, matrices)


def test_l2_p2_mpi2_block_ownership_smoke() -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("run this focused ownership smoke with mpiexec -n 2")
    comm = MPI.COMM_WORLD
    local, distributed_hx, distributed_matrices = _build_case(2, comm)
    distributed_edge = distributed_matrices[0]
    try:
        start, stop = distributed_edge.getOwnershipRange()
        source = distributed_edge.createVecRight()
        source.array[:] = np.arange(start, stop, dtype=np.float64) + (0.125 + 0.25j)
        before = source.array.copy()
        first = distributed_hx.apply(source)
        second = distributed_hx.apply(source)
        repeat = float(
            np.sqrt(comm.allreduce(float(np.vdot(first.array - second.array, first.array - second.array).real), op=MPI.SUM))
            / max(
                np.sqrt(comm.allreduce(float(np.vdot(first.array, first.array).real), op=MPI.SUM)),
                np.finfo(float).tiny,
            )
        )
        assert np.array_equal(source.array, before)
        assert np.all(np.isfinite(first.array))
        assert np.all(np.isfinite(second.array))
        assert repeat <= 1.0e-13
        audit = distributed_hx.audit
        assert audit["maximum_levels"] == 8
        assert 1 <= audit["observed_levels"] <= 8
        assert audit["hierarchy_object_count"] == 1
        assert audit["global_numeric_allgather"] is False
        first.destroy()
        second.destroy()
        source.destroy()
    finally:
        _destroy_case(distributed_hx, distributed_matrices)


def test_l2_periodic_edge_phase_is_once_and_whole_edge_only() -> None:
    lower_start = np.asarray([[0, 1, 3]], dtype=np.int32)
    lower_end = np.asarray([[0, 2, 3]], dtype=np.int32)
    upper_start = np.asarray([[5, 1, 3]], dtype=np.int32)
    upper_end = np.asarray([[5, 2, 3]], dtype=np.int32)
    normal_start = np.asarray([[4, 1, 3]], dtype=np.int32)
    normal_end = np.asarray([[5, 1, 3]], dtype=np.int32)
    lower_ids, _, lower_phase = _pack_canonical_edges(
        lower_start, lower_end, np.asarray([5, 5, 5], dtype=np.int32)
    )
    upper_ids, _, upper_phase = _pack_canonical_edges(
        upper_start, upper_end, np.asarray([5, 5, 5], dtype=np.int32)
    )
    normal_ids, _, normal_phase = _pack_canonical_edges(
        normal_start, normal_end, np.asarray([5, 5, 5], dtype=np.int32)
    )
    assert int(lower_ids[0]) == int(upper_ids[0])
    assert int(lower_phase[0]) == 0
    assert int(upper_phase[0]) == 1
    assert int(normal_phase[0]) == 0
    assert int(normal_ids[0]) != int(lower_ids[0])
