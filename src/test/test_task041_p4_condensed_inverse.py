from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    CellRecoveryMap,
    TraceConstraintMap,
    _distributed_trace_preallocation,
)
from src.solvers.p4_cell_condensed_inverse import (
    CellPortTerms,
    P4CellCondensedInverse,
    assemble_port_condensed_terms,
)


def _cell_blocks(
    rank: int,
    active_rows: int,
    n_ports: int = 1,
) -> SimpleNamespace:
    trace_rows = active_rows + 1
    index = np.arange(trace_rows, dtype=np.float64) + 1.0
    aii = np.asarray([[2.2 + 0.35j + 0.2 * rank]], dtype=np.complex128)
    interior_from_trace = np.asarray(
        [(0.031 + 0.009j) * value * (rank + 1) for value in index],
        dtype=np.complex128,
    ).reshape(1, trace_rows)
    trace_from_interior_rhs = np.asarray(
        [(0.047 - 0.011j) * value * (rank + 1) for value in index],
        dtype=np.complex128,
    ).reshape(trace_rows, 1)
    bi = np.asarray(
        [[
            0.31 + 0.12j + 0.05 * rank
            + (0.06 + 0.02j) * port
            for port in range(n_ports)
        ]],
        dtype=np.complex128,
    )
    di = np.asarray(
        [
            [
                1.07 - 0.23j + 0.11 * rank
                + (0.09 - 0.03j) * port,
            ]
            for port in range(n_ports)
        ],
        dtype=np.complex128,
    )
    bt = np.column_stack(
        [
            (
                (0.13 + 0.08j) * index
                + (0.02 + 0.01j) * rank
                + (0.03 + 0.015j) * port
            )
            for port in range(n_ports)
        ]
    )
    dt = np.vstack(
        [
            (
                (0.09 - 0.04j) * index
                + (0.015 - 0.006j) * rank
                + (0.02 - 0.01j) * port
            )
            for port in range(n_ports)
        ]
    )
    att = (
        (0.011 + 0.007j) * (index[:, None] + 2.0 * index[None, :])
        + (3.0 + 0.2j + 0.25 * rank) * np.eye(trace_rows)
    )
    h = np.empty((n_ports, n_ports), dtype=np.complex128)
    for row in range(n_ports):
        for column in range(n_ports):
            if row == column:
                h[row, column] = 1.8 + 0.17j + 0.1 * rank + 0.05 * row
            else:
                h[row, column] = (0.16 + 0.07j) * (row + 1) * (column + 2)

    phase = np.exp(0.17j * (rank + 1))
    return SimpleNamespace(
        aii=aii,
        interior_from_trace=interior_from_trace,
        trace_from_interior_rhs=trace_from_interior_rhs,
        bi=bi,
        di=di,
        bt=bt,
        dt=dt,
        att=att,
        h=h,
        phase=phase,
    )


class _ExactKSPFactor:
    def __init__(self, matrix: PETSc.Mat) -> None:
        self.ksp = PETSc.KSP().create(matrix.getComm())
        self.solve_count = 0
        self.destroyed = False
        try:
            self.ksp.setOperators(matrix)
            self.ksp.setType("preonly")
            self.ksp.getPC().setType("lu")
            if matrix.getComm().tompi4py().size > 1:
                self.ksp.getPC().setFactorSolverType("mumps")
            self.ksp.setUp()
        except BaseException:
            self.ksp.destroy()
            self.destroyed = True
            raise

    def solve_repeated(self, rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        self.ksp.solve(rhs, solution)
        reason = int(self.ksp.getConvergedReason())
        if reason <= 0:
            raise RuntimeError(f"PETSc exact KSP did not converge: {reason}")
        self.solve_count += 1

    def destroy(self) -> None:
        if not self.destroyed:
            self.ksp.destroy()
            self.destroyed = True


def _cell_trace_originals(rank: int, size: int, empty_owner: bool) -> list[int]:
    if size == 1:
        return [0, 1, 3]
    if empty_owner:
        return [0, 1, 3]
    other = 1 - rank
    return [4 * rank, 4 * rank + 1, 4 * other, 4 * other + 1, 4 * rank + 3]


def _make_fixture(
    *,
    empty_owner: bool = False,
    n_ports: int = 1,
    include_group_rows: bool | None = None,
) -> SimpleNamespace:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("the shared fixture is qualified only for MPI1/MPI2")
    size = comm.size
    if empty_owner and size != 2:
        pytest.skip("the empty-owner fixture is qualified only for MPI2")
    if n_ports not in (1, 2):
        raise ValueError("the tiny fixture supports one or two ports")
    if include_group_rows is None:
        include_group_rows = n_ports > 1

    if empty_owner:
        active_rows = 2
        active_originals = [0, 1]
        slave_originals = [3]
        include_ranks = [1]
        full_rows = 4
        owned_storage_originals = [] if comm.rank == 0 else list(range(4))
        owned_active_originals = [] if comm.rank == 0 else [0, 1]
        owned_trace_originals = [] if comm.rank == 0 else [0, 1, 3]
        active_map = {0: 1, 1: 0}
        cell_storage_originals = {1: 2}
    else:
        active_rows = 2 * size
        active_originals = [
            4 * rank + offset for rank in range(size) for offset in (0, 1)
        ]
        slave_originals = [4 * rank + 3 for rank in range(size)]
        include_ranks = list(range(size))
        full_rows = 4 * size
        owned_storage_originals = list(
            range(4 * comm.rank, 4 * comm.rank + 4)
        )
        owned_active_originals = [4 * comm.rank, 4 * comm.rank + 1]
        owned_trace_originals = [
            4 * comm.rank,
            4 * comm.rank + 1,
            4 * comm.rank + 3,
        ]
        active_map = {
            4 * rank: 2 * rank + 1
            for rank in range(size)
        }
        active_map.update(
            {
                4 * rank + 1: 2 * rank
                for rank in range(size)
            }
        )
        cell_storage_originals = {
            rank: 4 * rank + 2 for rank in include_ranks
        }

    trace_originals = active_originals + slave_originals
    expansion_by_original = {
        original: (
            np.asarray([active_map[original]], dtype=PETSc.IntType),
            np.asarray([1.0 + 0.0j], dtype=np.complex128),
        )
        for original in active_originals
    }
    for rank, original in enumerate(slave_originals):
        source_rank = 0 if empty_owner else rank
        expansion_by_original[original] = (
            np.asarray([2 * source_rank], dtype=PETSc.IntType),
            np.asarray(
                [_cell_blocks(source_rank, active_rows).phase],
                dtype=np.complex128,
            ),
        )

    cell_index = {rank: index for index, rank in enumerate(include_ranks)}
    n_cells = len(include_ranks)
    full_block_rows = n_cells + active_rows + n_ports
    retained_rows = active_rows + n_ports
    full_matrix = np.zeros(
        (full_block_rows, full_block_rows),
        dtype=np.complex128,
    )
    base_active = np.zeros((active_rows, active_rows), dtype=np.complex128)
    gi_a = {
        rank: 0.19 + 0.08j + 0.04 * rank
        for rank in include_ranks
    }
    gi_b = {
        rank: -0.12 + 0.17j + 0.03j * rank
        for rank in include_ranks
    }
    gt_a = np.asarray(
        [(0.21 + 0.13j) * (index + 1) for index in range(active_rows)],
        dtype=np.complex128,
    )
    gt_b = np.asarray(
        [(-0.07 + 0.19j) * (index + 2) for index in range(active_rows)],
        dtype=np.complex128,
    )
    gp_a = np.asarray(
        [0.37 - 0.19j + (0.05 + 0.03j) * port for port in range(n_ports)],
        dtype=np.complex128,
    )
    gp_b = np.asarray(
        [-0.22 + 0.41j + (0.07 - 0.02j) * port for port in range(n_ports)],
        dtype=np.complex128,
    )

    for rank in include_ranks:
        blocks = _cell_blocks(rank, active_rows, n_ports)
        trace_original = np.asarray(
            _cell_trace_originals(rank, size, empty_owner),
            dtype=PETSc.IntType,
        )
        expansion = np.zeros((len(trace_original), active_rows), dtype=np.complex128)
        for row, original in enumerate(trace_original):
            active = int(expansion_by_original[int(original)][0][0])
            coefficient = expansion_by_original[int(original)][1][0]
            expansion[row, active] = coefficient
        interior_row = cell_index[rank]
        trace_offset = n_cells
        port_start = trace_offset + active_rows
        aii = blocks.aii[0, 0]
        ait = -aii * blocks.interior_from_trace
        ati = -blocks.trace_from_interior_rhs * aii
        full_matrix[interior_row, interior_row] += aii
        full_matrix[
            interior_row,
            trace_offset : trace_offset + active_rows,
        ] += (ait @ expansion).ravel()
        full_matrix[interior_row, port_start : port_start + n_ports] += blocks.bi[0]
        full_matrix[
            trace_offset : trace_offset + active_rows,
            interior_row,
        ] += expansion.conj().T @ ati.ravel()
        full_matrix[
            trace_offset : trace_offset + active_rows,
            trace_offset : trace_offset + active_rows,
        ] += expansion.conj().T @ blocks.att @ expansion
        full_matrix[
            trace_offset : trace_offset + active_rows,
            port_start : port_start + n_ports,
        ] += expansion.conj().T @ blocks.bt
        full_matrix[
            port_start : port_start + n_ports,
            interior_row,
        ] -= blocks.di[:, 0]
        full_matrix[
            port_start : port_start + n_ports,
            trace_offset : trace_offset + active_rows,
        ] -= blocks.dt @ expansion
        full_matrix[
            port_start : port_start + n_ports,
            port_start : port_start + n_ports,
        ] += blocks.h
        base_active += expansion.conj().T @ (
            blocks.att + ati @ blocks.interior_from_trace
        ) @ expansion

    trace_constraints = TraceConstraintMap(
        owned_active_original_dofs=np.asarray(
            owned_active_originals,
            dtype=PETSc.IntType,
        ),
        original_to_active=active_map,
        expansion_by_original=expansion_by_original,
        full_trace_rows=len(trace_originals),
        active_rows=active_rows,
        slave_rows=len(slave_originals),
        build_audit={"fixture": "real-petsc-nonhermitian-port-rhs"},
    )
    local_interiors: dict[tuple[int, ...], tuple[np.ndarray, np.ndarray]] = {}
    local_recovery: dict[tuple[int, ...], np.ndarray] = {}
    local_rhs_projection: dict[tuple[int, ...], np.ndarray] = {}
    local_embedding: dict[tuple[int, ...], np.ndarray] = {}
    local_trace_rhs: dict[tuple[int, ...], np.ndarray] = {}
    local_residual: dict[tuple[int, ...], np.ndarray] = {}
    local_cells: tuple[CellRecoveryMap, ...]
    local_terms: dict[int, CellPortTerms]
    if comm.rank in include_ranks:
        blocks = _cell_blocks(comm.rank, active_rows, n_ports)
        class_key = (comm.rank,)
        cell = CellRecoveryMap(
            interior_original_dofs=np.asarray(
                [cell_storage_originals[comm.rank]],
                dtype=PETSc.IntType,
            ),
            trace_original_dofs=np.asarray(
                _cell_trace_originals(comm.rank, size, empty_owner),
                dtype=PETSc.IntType,
            ),
            class_key=class_key,
        )
        local_cells = (cell,)
        local_terms = {
            0: CellPortTerms(
                Bi=blocks.bi,
                Di=blocks.di,
                port_indices=np.arange(n_ports, dtype=PETSc.IntType),
                Bt=blocks.bt,
                Dt=blocks.dt,
                H=blocks.h,
            )
        }
        local_interiors[class_key] = (
            blocks.aii.copy(),
            np.asarray([0], dtype=np.int32),
        )
        local_recovery[class_key] = blocks.interior_from_trace.copy()
        local_rhs_projection[class_key] = np.eye(1, dtype=np.complex128)
        local_embedding[class_key] = np.eye(1, dtype=np.complex128)
        local_trace_rhs[class_key] = blocks.trace_from_interior_rhs.copy()
        local_residual[class_key] = np.eye(1, dtype=np.complex128)
    else:
        local_cells = ()
        local_terms = {}

    if local_cells:
        local_cell_active_ids = (
            np.unique(
                np.concatenate(
                    [
                        expansion_by_original[int(original)][0]
                        for original in local_cells[0].trace_original_dofs
                    ]
                )
            ).astype(PETSc.IntType, copy=False),
        )
    else:
        local_cell_active_ids = ()
    active_counts = tuple(
        int(value) for value in comm.allgather(len(owned_active_originals))
    )
    support_owned_cell_groups = (
        (
            np.arange(
                len(local_cell_active_ids),
                dtype=PETSc.IntType,
            ),
        )
    )
    support_group_by_row = tuple(0 for _ in range(n_ports))
    preallocation_d_nnz, preallocation_o_nnz, preallocation_audit = (
        _distributed_trace_preallocation(
            comm,
            local_cell_active_ids,
            active_counts=active_counts,
            appended_global_rows=n_ports,
            appended_support_owned_cell_groups=support_owned_cell_groups,
            appended_support_group_by_row=support_group_by_row,
            appended_support_include_group_rows=bool(include_group_rows),
        )
    )
    if n_ports == 2 and include_group_rows:
        (
            control_preallocation_d_nnz,
            control_preallocation_o_nnz,
            control_preallocation_audit,
        ) = _distributed_trace_preallocation(
            comm,
            local_cell_active_ids,
            active_counts=active_counts,
            appended_global_rows=n_ports,
            appended_support_owned_cell_groups=support_owned_cell_groups,
            appended_support_group_by_row=support_group_by_row,
            appended_support_include_group_rows=False,
        )
    else:
        control_preallocation_d_nnz = np.array(
            preallocation_d_nnz,
            dtype=PETSc.IntType,
            copy=True,
        )
        control_preallocation_o_nnz = np.array(
            preallocation_o_nnz,
            dtype=PETSc.IntType,
            copy=True,
        )
        control_preallocation_audit = dict(preallocation_audit)

    local_matrix_rows = (
        0
        if empty_owner and comm.rank == 0
        else (
            len(owned_active_originals)
            + (n_ports if comm.rank == size - 1 else 0)
        )
    )
    matrix = PETSc.Mat().createAIJ(
        size=((local_matrix_rows, retained_rows), (local_matrix_rows, retained_rows)),
        nnz=(
            preallocation_d_nnz
            if size == 1
            else (preallocation_d_nnz, preallocation_o_nnz)
        ),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        values = np.zeros(retained_rows, dtype=np.complex128)
        if row < active_rows:
            values[:active_rows] = base_active[row]
        matrix.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            np.arange(retained_rows, dtype=PETSc.IntType),
            values.reshape(1, -1),
        )
    matrix.assemble()

    system = None
    factor = None
    try:
        system = AssemblyTimeCondensedSystem(
            matrix=matrix,
            owned_trace_original_dofs=np.asarray(
                owned_trace_originals,
                dtype=PETSc.IntType,
            ),
            original_to_trace={
                original: index
                for index, original in enumerate(trace_originals)
            },
            trace_constraints=trace_constraints,
            cell_recovery_maps=local_cells,
            interior_from_trace_by_class=local_recovery,
            interior_lu_by_class=local_interiors,
            interior_rhs_projection_by_class=local_rhs_projection,
            interior_solution_embedding_by_class=local_embedding,
            trace_from_interior_rhs_by_class=local_trace_rhs,
            interior_residual_projection_by_class=local_residual,
            full_rows=full_rows,
            trace_rows=len(trace_originals),
            active_rows=active_rows,
            appended_rows=n_ports,
            interior_rows=n_cells,
            active_interior_rows=n_cells,
            build_audit={
                "fixture": "real-petsc-cell-condensation",
                "preallocation": preallocation_audit,
            },
            comm=comm,
            owned_active_rows=len(owned_active_originals),
            owned_appended_rows=(
                n_ports if comm.rank == size - 1 else 0
            ),
            retained_local_schur_by_class=None,
        )
        assemble_port_condensed_terms(system, local_terms)
        factor = _ExactKSPFactor(matrix)
    except BaseException:
        if factor is not None:
            factor.destroy()
        if system is not None:
            system.destroy()
        else:
            matrix.destroy()
        raise

    return SimpleNamespace(
        comm=comm,
        size=size,
        system=system,
        factor=factor,
        port_terms=local_terms,
        full_matrix=full_matrix,
        full_block_rows=full_block_rows,
        retained_rows=retained_rows,
        full_rows=full_rows,
        active_rows=active_rows,
        n_ports=n_ports,
        include_group_rows=bool(include_group_rows),
        preallocation_d_nnz=np.asarray(preallocation_d_nnz, dtype=np.int64),
        preallocation_o_nnz=np.asarray(preallocation_o_nnz, dtype=np.int64),
        preallocation_audit=preallocation_audit,
        control_preallocation_d_nnz=np.asarray(
            control_preallocation_d_nnz,
            dtype=np.int64,
        ),
        control_preallocation_o_nnz=np.asarray(
            control_preallocation_o_nnz,
            dtype=np.int64,
        ),
        control_preallocation_audit=control_preallocation_audit,
        n_cells=n_cells,
        empty_owner=empty_owner,
        include_ranks=include_ranks,
        cell_index=cell_index,
        cell_storage_originals=cell_storage_originals,
        active_map=active_map,
        owned_storage_originals=np.asarray(
            owned_storage_originals,
            dtype=PETSc.IntType,
        ),
        owned_active_originals=np.asarray(
            owned_active_originals,
            dtype=PETSc.IntType,
        ),
        gi_a=gi_a,
        gi_b=gi_b,
        gt_a=gt_a,
        gt_b=gt_b,
        gp_a=gp_a,
        gp_b=gp_b,
    )


def _inverse_for(fixture: SimpleNamespace) -> P4CellCondensedInverse:
    try:
        return P4CellCondensedInverse(
            fixture.system,
            fixture.factor,
            port_terms=fixture.port_terms,
            owns_condensed=True,
            owns_factor=True,
        )
    except BaseException:
        fixture.factor.destroy()
        fixture.system.destroy()
        raise


def _payload(
    *,
    gi_by_rank: dict[int, complex],
    gt: np.ndarray,
    gp: np.ndarray,
) -> SimpleNamespace:
    return SimpleNamespace(
        gi_by_rank=gi_by_rank,
        gt=np.asarray(gt, dtype=np.complex128),
        gp=np.asarray(gp, dtype=np.complex128),
    )


def _scaled_payload(payload: SimpleNamespace, scale: complex) -> SimpleNamespace:
    return SimpleNamespace(
        gi_by_rank={
            rank: value * scale
            for rank, value in payload.gi_by_rank.items()
        },
        gt=payload.gt * scale,
        gp=payload.gp * scale,
    )


def _combined_payload(
    alpha: complex,
    first: SimpleNamespace,
    beta: complex,
    second: SimpleNamespace,
) -> SimpleNamespace:
    ranks = set(first.gi_by_rank) | set(second.gi_by_rank)
    return SimpleNamespace(
        gi_by_rank={
            rank: alpha * first.gi_by_rank.get(rank, 0.0)
            + beta * second.gi_by_rank.get(rank, 0.0)
            for rank in ranks
        },
        gt=alpha * first.gt + beta * second.gt,
        gp=alpha * first.gp + beta * second.gp,
    )


def _rhs_for(
    fixture: SimpleNamespace,
    payload: SimpleNamespace,
    *,
    zero_fe: bool = False,
) -> PETSc.Vec:
    rhs = PETSc.Vec().createMPI(
        (len(fixture.owned_storage_originals), fixture.full_rows),
        comm=fixture.comm,
    )
    try:
        values = rhs.getArray()
        values[:] = 0.0
        if not zero_fe:
            local_positions = {
                int(original): index
                for index, original in enumerate(fixture.owned_storage_originals)
            }
            for original in fixture.owned_active_originals:
                original = int(original)
                values[local_positions[original]] = (
                    payload.gt[fixture.active_map[original]]
                )
            if fixture.comm.rank in fixture.include_ranks:
                interior = fixture.cell_storage_originals[fixture.comm.rank]
                values[local_positions[interior]] = payload.gi_by_rank[
                    fixture.comm.rank
                ]
        rhs.assemble()
        return rhs
    except BaseException:
        rhs.destroy()
        raise


def _expected(
    fixture: SimpleNamespace,
    payload: SimpleNamespace,
    *,
    zero_fe: bool = False,
) -> SimpleNamespace:
    full_rhs = np.zeros(
        fixture.full_block_rows,
        dtype=np.complex128,
    )
    if not zero_fe:
        for rank in fixture.include_ranks:
            full_rhs[fixture.cell_index[rank]] = payload.gi_by_rank[rank]
        full_rhs[
            fixture.n_cells : fixture.n_cells + fixture.active_rows
        ] = payload.gt
    full_rhs[-fixture.n_ports :] = payload.gp
    direct = np.linalg.solve(fixture.full_matrix, full_rhs)
    storage = np.zeros(fixture.full_rows, dtype=np.complex128)
    for rank in fixture.include_ranks:
        storage[fixture.cell_storage_originals[rank]] = direct[
            fixture.cell_index[rank]
        ]
    active_offset = fixture.n_cells
    for original, active in fixture.active_map.items():
        storage[original] = direct[active_offset + active]
    direct_residual = _relative_difference(
        fixture.full_matrix @ direct,
        full_rhs,
    )
    return SimpleNamespace(
        full_rhs=full_rhs,
        direct=direct,
        storage=storage,
        relative_residual=float(direct_residual),
    )


def _gather_storage(fixture: SimpleNamespace, local_values: np.ndarray) -> np.ndarray:
    packets = fixture.comm.allgather(
        (
            fixture.owned_storage_originals.tolist(),
            np.asarray(local_values, dtype=np.complex128).tolist(),
        )
    )
    gathered = np.zeros(fixture.full_rows, dtype=np.complex128)
    for originals, values in packets:
        for original, value in zip(originals, values, strict=True):
            gathered[int(original)] = complex(value)
    return gathered


def _assert_global_relative(
    comm,
    value: float,
    label: str,
    *,
    limit: float = 1.0e-11,
) -> None:
    maximum = float(comm.allreduce(float(value), op=MPI.MAX))
    assert maximum <= limit, f"{label}={maximum:.16e} > {limit:.3e}"


def _assert_collective_condition(comm, condition: bool, label: str) -> None:
    """Make fixture-structure failures converge before later collectives."""

    passed = bool(comm.allreduce(bool(condition), op=MPI.LAND))
    assert passed, label


def _relative_difference(
    actual: np.ndarray,
    expected: np.ndarray,
) -> float:
    error = float(np.linalg.norm(actual - expected))
    scale = float(np.linalg.norm(expected))
    if scale == 0.0:
        return 0.0 if error == 0.0 else float("inf")
    return error / scale


def _emit_qualification(
    fixture: SimpleNamespace,
    case_name: str,
    diagnostics: dict[str, float],
) -> None:
    if fixture.comm.rank != 0:
        return
    print(
        json.dumps(
            {
                "case": case_name,
                "empty_owner": bool(fixture.empty_owner),
                "mpi_size": fixture.size,
                "n_ports": fixture.n_ports,
                "rhs_norm": diagnostics["rhs_norm"],
                "full_relative_residual": diagnostics[
                    "full_relative_residual"
                ],
                "fe_response_relative_error": diagnostics[
                    "fe_response_relative_error"
                ],
                "port_response_relative_error": diagnostics[
                    "port_response_relative_error"
                ],
                "factor_solve_count": diagnostics["factor_solve_count"],
                "preallocation_d_nnz_rank0_local": [
                    int(value) for value in fixture.preallocation_d_nnz
                ],
                "preallocation_o_nnz_rank0_local": [
                    int(value) for value in fixture.preallocation_o_nnz
                ],
                "preallocation_structural_nnz_global": int(
                    fixture.preallocation_audit["preallocated_structural_nnz"]
                ),
                "preallocation_control_structural_nnz_global": int(
                    fixture.control_preallocation_audit[
                        "preallocated_structural_nnz"
                    ]
                ),
                "preallocation_mode": fixture.preallocation_audit[
                    "appended_graph_preallocation"
                ],
                "preallocation_control_mode": fixture.control_preallocation_audit[
                    "appended_graph_preallocation"
                ],
                "zero_owner_assertion": (
                    True if fixture.empty_owner else None
                ),
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _apply_case(
    fixture: SimpleNamespace,
    inverse: P4CellCondensedInverse,
    payload: SimpleNamespace,
    *,
    case_name: str,
    zero_fe: bool = False,
) -> SimpleNamespace:
    rhs = _rhs_for(fixture, payload, zero_fe=zero_fe)
    before = np.array(rhs.getArray(readonly=True), copy=True)
    port_rhs = np.array(payload.gp, copy=True)
    port_before = np.array(port_rhs, copy=True)
    result = None
    try:
        result = inverse.apply(rhs, port_rhs=port_rhs)
        expected = _expected(fixture, payload, zero_fe=zero_fe)
        _assert_global_relative(
            fixture.comm,
            expected.relative_residual,
            "independent full oracle residual",
        )
        local_actual = np.asarray(
            result.getArray(readonly=True),
            dtype=np.complex128,
        )
        actual_storage = _gather_storage(fixture, local_actual)
        actual_port = np.array(inverse.last_port_solution, copy=True)
        actual_full = np.zeros_like(expected.direct)
        for rank in fixture.include_ranks:
            actual_full[fixture.cell_index[rank]] = actual_storage[
                fixture.cell_storage_originals[rank]
            ]
        for original, active in fixture.active_map.items():
            actual_full[fixture.n_cells + active] = actual_storage[original]
        actual_full[-fixture.n_ports :] = actual_port
        full_residual = _relative_difference(
            fixture.full_matrix @ actual_full,
            expected.full_rhs,
        )
        _assert_global_relative(
            fixture.comm,
            full_residual,
            "production full residual",
        )
        fe_error = _relative_difference(actual_storage, expected.storage)
        port_error = _relative_difference(
            actual_port,
            expected.direct[-fixture.n_ports :],
        )
        _assert_global_relative(
            fixture.comm,
            fe_error,
            "production FE response",
        )
        _assert_global_relative(
            fixture.comm,
            port_error,
            "production port response",
        )
        unchanged = np.array_equal(rhs.getArray(readonly=True), before)
        unchanged = fixture.comm.allreduce(bool(unchanged), op=MPI.LAND)
        assert unchanged
        assert np.array_equal(port_rhs, port_before)
        if zero_fe and not np.any(payload.gp):
            assert np.array_equal(actual_storage, np.zeros_like(actual_storage))
            assert np.array_equal(actual_port, np.zeros_like(actual_port))
        diagnostics = {
            "rhs_norm": float(np.linalg.norm(expected.full_rhs)),
            "full_relative_residual": full_residual,
            "fe_response_relative_error": fe_error,
            "port_response_relative_error": port_error,
            "factor_solve_count": float(inverse.solve_count),
        }
        _emit_qualification(fixture, case_name, diagnostics)
        return SimpleNamespace(
            storage=actual_storage,
            port=actual_port,
            full=actual_full,
            diagnostics=diagnostics,
        )
    finally:
        if result is not None:
            result.destroy()
        rhs.destroy()


@pytest.mark.parametrize("n_ports", [1, 2])
def test_production_apply_shared_fixture_covers_rhs_and_recovery_contract(
    n_ports: int,
) -> None:
    fixture = _make_fixture(n_ports=n_ports)
    active_rows = fixture.active_rows
    expected_default_structural_nnz = (
        active_rows * (active_rows + n_ports)
        + n_ports * (active_rows + 1)
    )
    expected_group_structural_nnz = (active_rows + n_ports) ** 2
    actual_structural_nnz = int(
        fixture.preallocation_audit["preallocated_structural_nnz"]
    )
    control_structural_nnz = int(
        fixture.control_preallocation_audit["preallocated_structural_nnz"]
    )
    _assert_collective_condition(
        fixture.comm,
        actual_structural_nnz
        == (
            expected_group_structural_nnz
            if fixture.include_group_rows
            else expected_default_structural_nnz
        ),
        "unexpected opt-in preallocation structural total",
    )
    _assert_collective_condition(
        fixture.comm,
        control_structural_nnz == expected_default_structural_nnz,
        "unexpected default preallocation structural total",
    )
    _assert_collective_condition(
        fixture.comm,
        actual_structural_nnz - control_structural_nnz == n_ports * (n_ports - 1),
        "unexpected opt-in structural increment",
    )
    active_local_rows = int(fixture.system.owned_active_rows)
    active_rows_unchanged = (
        fixture.preallocation_audit["active_rows"]
        == fixture.control_preallocation_audit["active_rows"]
        == active_rows
    )
    _assert_collective_condition(
        fixture.comm,
        active_rows_unchanged,
        "preallocation active row count changed",
    )
    active_d_unchanged = np.array_equal(
        fixture.preallocation_d_nnz[:active_local_rows],
        fixture.control_preallocation_d_nnz[:active_local_rows],
    )
    active_o_unchanged = np.array_equal(
        fixture.preallocation_o_nnz[:active_local_rows],
        fixture.control_preallocation_o_nnz[:active_local_rows],
    )
    _assert_collective_condition(
        fixture.comm,
        active_d_unchanged and active_o_unchanged,
        "opt-in changed active-row preallocation",
    )
    appended_d_ok = True
    appended_o_ok = True
    if fixture.comm.rank == fixture.size - 1:
        appended_d_ok = np.array_equal(
            fixture.preallocation_d_nnz[active_local_rows:],
            fixture.control_preallocation_d_nnz[active_local_rows:]
            + (n_ports - 1),
        )
        appended_o_ok = np.array_equal(
            fixture.preallocation_o_nnz[active_local_rows:],
            fixture.control_preallocation_o_nnz[active_local_rows:],
        )
    _assert_collective_condition(
        fixture.comm,
        appended_d_ok,
        "opt-in did not add one local slot per appended port row",
    )
    _assert_collective_condition(
        fixture.comm,
        appended_o_ok,
        "opt-in changed appended off-diagonal preallocation",
    )
    inverse = _inverse_for(fixture)
    payload_a = _payload(
        gi_by_rank=fixture.gi_a,
        gt=fixture.gt_a,
        gp=fixture.gp_a,
    )
    payload_b = _payload(
        gi_by_rank=fixture.gi_b,
        gt=fixture.gt_b,
        gp=fixture.gp_b,
    )
    alpha = 0.37 + 0.19j
    beta = -0.21 + 0.11j
    try:
        first = _apply_case(
            fixture,
            inverse,
            payload_a,
            case_name="normal_A",
        )
        second = _apply_case(
            fixture,
            inverse,
            payload_b,
            case_name="normal_B",
        )
        repeated = _apply_case(
            fixture,
            inverse,
            payload_a,
            case_name="normal_repeat_A",
        )
        repeat_fe_error = _relative_difference(repeated.storage, first.storage)
        repeat_port_error = _relative_difference(repeated.port, first.port)
        _assert_global_relative(
            fixture.comm,
            repeat_fe_error,
            "A-to-B-to-A FE repeat",
        )
        _assert_global_relative(
            fixture.comm,
            repeat_port_error,
            "A-to-B-to-A port repeat",
        )
        combined = _apply_case(
            fixture,
            inverse,
            _combined_payload(alpha, payload_a, beta, payload_b),
            case_name="normal_complex_linear_combo",
        )
        linearity_fe_error = _relative_difference(
            combined.storage,
            alpha * first.storage + beta * second.storage,
        )
        linearity_port_error = _relative_difference(
            combined.port,
            alpha * first.port + beta * second.port,
        )
        _assert_global_relative(
            fixture.comm,
            linearity_fe_error,
            "complex linearity FE",
        )
        _assert_global_relative(
            fixture.comm,
            linearity_port_error,
            "complex linearity port",
        )
        _apply_case(
            fixture,
            inverse,
            _scaled_payload(payload_a, 1.0e-14),
            case_name="normal_near_zero",
        )
        _apply_case(
            fixture,
            inverse,
            payload_a,
            case_name="normal_port_only",
            zero_fe=True,
        )
        factor_count_before_zero = int(inverse.solve_count)
        zero = _apply_case(
            fixture,
            inverse,
            _payload(
                gi_by_rank={rank: 0.0 for rank in fixture.include_ranks},
                gt=np.zeros(fixture.active_rows, dtype=np.complex128),
                gp=np.zeros(fixture.n_ports, dtype=np.complex128),
            ),
            case_name="normal_zero",
            zero_fe=True,
        )
        assert np.array_equal(zero.storage, np.zeros_like(zero.storage))
        assert np.array_equal(zero.port, np.zeros_like(zero.port))
        assert inverse.solve_count == factor_count_before_zero
        assert fixture.factor.solve_count == inverse.solve_count
        assert inverse.solve_count == 6
        assert fixture.preallocation_audit["new_nonzero_allocation_error_enabled"]
        assert (
            fixture.preallocation_audit["appended_support_include_group_rows"]
            == (n_ports > 1)
        )
        if n_ports == 2:
            assert (
                fixture.preallocation_audit["appended_graph_preallocation"]
                == "support_safe_upper_bound_with_group_rows"
            )
        else:
            assert (
                fixture.preallocation_audit["appended_graph_preallocation"]
                == "support_safe_upper_bound"
            )
        if fixture.comm.rank == 0:
            print(
                json.dumps(
                    {
                        "case": "normal_comparison_summary",
                        "empty_owner": False,
                        "mpi_size": fixture.size,
                        "n_ports": fixture.n_ports,
                        "rhs_norm": None,
                        "full_relative_residual": None,
                        "fe_response_relative_error": None,
                        "port_response_relative_error": None,
                        "repeat_fe_relative_error": repeat_fe_error,
                        "repeat_port_relative_error": repeat_port_error,
                        "complex_linearity_fe_error": linearity_fe_error,
                        "complex_linearity_port_error": linearity_port_error,
                        "factor_solve_count": inverse.solve_count,
                        "preallocation_structural_nnz_global": int(
                            fixture.preallocation_audit[
                                "preallocated_structural_nnz"
                            ]
                        ),
                        "preallocation_control_structural_nnz_global": int(
                            fixture.control_preallocation_audit[
                                "preallocated_structural_nnz"
                            ]
                        ),
                        "preallocation_d_nnz_rank0_local": [
                            int(value)
                            for value in fixture.preallocation_d_nnz
                        ],
                        "preallocation_o_nnz_rank0_local": [
                            int(value)
                            for value in fixture.preallocation_o_nnz
                        ],
                        "zero_owner_assertion": None,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        inverse.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="requires MPI2")
@pytest.mark.parametrize("n_ports", [1, 2])
def test_production_apply_empty_owner_uses_same_fixture(n_ports: int) -> None:
    fixture = _make_fixture(empty_owner=True, n_ports=n_ports)
    layout = fixture.comm.allgather(
        (
            len(fixture.owned_storage_originals),
            int(fixture.system.owned_active_rows),
            len(fixture.system.cell_recovery_maps),
            int(fixture.system.owned_appended_rows),
        )
    )
    assert layout[0] == (0, 0, 0, 0)
    assert layout[1][0] > 0
    assert layout[1][1] > 0
    assert layout[1][2] > 0
    assert layout[1][3] == n_ports
    assert fixture.preallocation_audit["new_nonzero_allocation_error_enabled"]
    inverse = _inverse_for(fixture)
    payload = _payload(
        gi_by_rank=fixture.gi_a,
        gt=fixture.gt_a,
        gp=fixture.gp_a,
    )
    try:
        _apply_case(
            fixture,
            inverse,
            payload,
            case_name="empty_owner_A",
        )
    finally:
        inverse.destroy()


@pytest.mark.parametrize(
    "bad_port_rhs",
    [
        np.asarray([np.nan + 0.0j]),
        np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
    ],
)
def test_port_rhs_collective_validation_rejects_bad_input(
    bad_port_rhs: np.ndarray,
) -> None:
    fixture = _make_fixture()
    inverse = _inverse_for(fixture)
    rhs = _rhs_for(
        fixture,
        _payload(
            gi_by_rank=fixture.gi_a,
            gt=fixture.gt_a,
            gp=fixture.gp_a,
        ),
    )
    try:
        with pytest.raises(ValueError, match="port RHS validation"):
            inverse.apply(rhs, port_rhs=bad_port_rhs)
    finally:
        rhs.destroy()
        inverse.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="requires MPI2")
def test_one_rank_port_rhs_mismatch_fails_collectively() -> None:
    fixture = _make_fixture()
    inverse = _inverse_for(fixture)
    rhs = _rhs_for(
        fixture,
        _payload(
            gi_by_rank=fixture.gi_a,
            gt=fixture.gt_a,
            gp=fixture.gp_a,
        ),
    )
    local_port_rhs = fixture.gp_a + fixture.comm.rank
    try:
        with pytest.raises(ValueError, match="port RHS validation"):
            inverse.apply(rhs, port_rhs=local_port_rhs)
    finally:
        rhs.destroy()
        inverse.destroy()


def test_borrowed_factor_and_condensed_are_not_destroyed() -> None:
    fixture = _make_fixture()
    borrowed = _inverse_for(fixture)
    borrowed.owns_condensed = False
    borrowed.owns_factor = False
    try:
        borrowed.destroy()
        borrowed.destroy()
        assert not fixture.factor.destroyed
        assert fixture.system.matrix.getSize() == (
            fixture.active_rows + 1,
            fixture.active_rows + 1,
        )
    finally:
        fixture.factor.destroy()
        fixture.system.destroy()
