from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.condensed_dtn import (
    DtnBlockAssembler,
    PetscCondensedBlocks,
    create_matrix_free_condensed_operator,
    project_condensed_blocks_to_coarse,
)
from src.solvers.hcurl_assembly_time_condensation import (
    CellRecoveryMap,
    _cell_trace_expansion,
    _distributed_trace_preallocation,
)
from src.solvers.static_trace_auxiliary import (
    build_p2_galerkin_fine_matrix,
    build_p2_to_p6_active_trace_transfer,
    _global_cell_dofs,
    _trace_and_interior_positions,
)
from src.test.test_234_task037_p2_trace_transfer import _constraint_map, _spaces


def _aij(values: np.ndarray) -> PETSc.Mat:
    values = np.asarray(values, dtype=PETSc.ScalarType)
    matrix = PETSc.Mat().createAIJ(
        size=values.shape,
        nnz=max(int(values.shape[1]), 1),
        comm=PETSc.COMM_SELF,
    )
    matrix.setValues(
        np.arange(values.shape[0], dtype=PETSc.IntType),
        np.arange(values.shape[1], dtype=PETSc.IntType),
        values,
    )
    matrix.assemble()
    return matrix


def _vector(layout: PETSc.Vec, seed: int) -> PETSc.Vec:
    result = layout.copy()
    start, end = map(int, result.getOwnershipRange())
    ids = np.arange(start, end, dtype=np.float64)
    if seed == 235:
        generator = np.random.default_rng(seed)
        values = generator.standard_normal(
            end - start
        ) + 1j * generator.standard_normal(end - start)
        values /= max(float(np.max(np.abs(values), initial=0.0)), 1.0)
    else:
        values = np.sin(0.13 * ids + 0.17 * (seed + 1)) + 1j * np.cos(
            0.09 * ids - 0.11 * (seed + 2)
        )
    result.getArray()[:] = values
    result.assemble()
    return result


def _max_relative(left: PETSc.Vec, right: PETSc.Vec) -> tuple[float, float]:
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    comm = difference.getComm().tompi4py()
    local_absolute = float(
        np.max(np.abs(difference.getArray(readonly=True)), initial=0.0)
    )
    local_reference = float(np.max(np.abs(right.getArray(readonly=True)), initial=0.0))
    absolute = float(comm.allreduce(local_absolute, op=MPI.MAX))
    reference = float(comm.allreduce(local_reference, op=MPI.MAX))
    difference.destroy()
    return absolute, absolute / max(reference, 1.0e-30)


def _retained_p6_fixture(V6, C6):
    _trace, fine_trace = _trace_and_interior_positions(V6)
    owned_cells = int(V6.mesh.topology.index_map(V6.mesh.topology.dim).size_local)
    recovery_maps = []
    schurs = {}
    for cell in range(owned_cells):
        fine_global = _global_cell_dofs(V6, cell)
        trace_global = fine_global[_trace]
        class_key = ("synthetic_raw_p6", cell)
        recovery_maps.append(
            CellRecoveryMap(
                interior_original_dofs=fine_global[fine_trace],
                trace_original_dofs=trace_global,
                class_key=class_key,
            )
        )
        generator = np.random.default_rng(2350 + cell)
        raw = generator.standard_normal(
            (len(_trace), len(_trace))
        ) + 1j * generator.standard_normal((len(_trace), len(_trace)))
        raw /= np.sqrt(len(_trace))
        schurs[class_key] = np.asarray(
            raw.conjugate().T @ raw + 0.25 * np.eye(len(_trace)),
            dtype=np.complex128,
        )
    return SimpleNamespace(
        matrix=None,
        active_rows=int(C6.active_rows),
        cell_recovery_maps=tuple(recovery_maps),
        retained_local_schur_by_class=MappingProxyType(schurs),
    ), schurs


def _assemble_fine_reference(V6, C6, schurs) -> PETSc.Mat:
    fine_trace, _interior = _trace_and_interior_positions(V6)
    comm = V6.mesh.comm
    active_counts = tuple(
        int(value) for value in comm.allgather(len(C6.owned_active_original_dofs))
    )
    active_rows = int(C6.active_rows)
    active_cells = []
    for cell, schur in enumerate(schurs.values()):
        fine_global = _global_cell_dofs(V6, cell)
        trace_global = fine_global[fine_trace]
        active_ids, expansion, identity = _cell_trace_expansion(
            trace_global,
            C6,
        )
        active_schur = (
            schur if identity else expansion.conjugate().T @ schur @ expansion
        )
        active_cells.append((active_ids, np.asarray(active_schur)))
    diagonal_nnz, off_diagonal_nnz, _audit = _distributed_trace_preallocation(
        comm,
        tuple(active_ids for active_ids, _active_schur in active_cells),
        active_counts=active_counts,
        appended_global_rows=0,
        appended_support_owned_cell_groups=(),
        appended_support_group_by_row=(),
    )
    matrix = PETSc.Mat().createAIJ(
        size=(
            (active_counts[comm.rank], active_rows),
            (active_counts[comm.rank], active_rows),
        ),
        nnz=(diagonal_nnz, off_diagonal_nnz),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
    for active_ids, active_schur in active_cells:
        matrix.setValues(
            active_ids,
            active_ids,
            np.ascontiguousarray(np.asarray(active_schur, dtype=PETSc.ScalarType)),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    matrix.assemble()
    return matrix


def _explicit_transfer_matrix(transfer) -> PETSc.Mat:
    rows = int(transfer.fine_constraints.active_rows)
    cols = int(transfer.coarse_constraints.active_rows)
    row_nnz = np.diff(transfer.row_offsets).astype(PETSc.IntType)
    matrix = PETSc.Mat().createAIJ(
        size=((rows, rows), (cols, cols)),
        nnz=(row_nnz, np.zeros(rows, dtype=PETSc.IntType)),
        comm=PETSc.COMM_SELF,
    )
    for local, row in enumerate(transfer.row_global_ids):
        start = int(transfer.row_offsets[local])
        end = int(transfer.row_offsets[local + 1])
        if end > start:
            matrix.setValues(
                np.asarray([row], dtype=PETSc.IntType),
                transfer.column_ids[start:end],
                transfer.values[start:end].reshape((1, -1)),
            )
    matrix.assemble()
    return matrix


def _dense_values(matrix: PETSc.Mat) -> np.ndarray:
    rows, cols = map(int, matrix.getSize())
    return np.asarray(
        matrix.getValues(
            np.arange(rows, dtype=PETSc.IntType),
            np.arange(cols, dtype=PETSc.IntType),
        ),
        dtype=PETSc.ScalarType,
    )


def _array_error(
    left: np.ndarray,
    right: np.ndarray,
    comm=MPI.COMM_SELF,
) -> tuple[float, float]:
    difference = np.asarray(left) - np.asarray(right)
    local_absolute = float(np.max(np.abs(difference), initial=0.0))
    local_reference = float(np.max(np.abs(right), initial=0.0))
    absolute = float(comm.allreduce(local_absolute, op=MPI.MAX))
    reference = float(comm.allreduce(local_reference, op=MPI.MAX))
    return absolute, absolute / max(reference, 1.0e-30)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial-only fixture")
def test_serial_p2_galerkin_projection_and_dtn_identity():
    mesh_3d, (V2, V6), (C2, C6) = _spaces(MPI.COMM_SELF)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    fine_condensed, schurs = _retained_p6_fixture(V6, C6)
    F2, f2_audit = build_p2_galerkin_fine_matrix(
        fine_condensed,
        V2,
        V6,
        C2,
    )
    assert f2_audit["global_p6_matrix_materialized"] is False
    assert f2_audit["global_p6_transfer_materialized"] is False
    assert f2_audit["global_basis_sweep"] is False
    assert f2_audit["trace_interior_dependency_max"] <= 1.0e-12
    assert f2_audit["max_cell_temporary_bytes"] > 0

    F6 = _assemble_fine_reference(V6, C6, schurs)
    P = _explicit_transfer_matrix(transfer)
    n6 = int(C6.active_rows)
    n_aux = 2
    C6_values = np.zeros((n6, n_aux), dtype=np.complex128)
    C6_values[[0, n6 // 3, n6 // 2], 0] = (0.3 - 0.2j, 0.1 + 0.04j, -0.07j)
    C6_values[[1, n6 // 4, n6 - 1], 1] = (-0.2 + 0.1j, 0.06j, 0.08 - 0.03j)
    D6_values = np.zeros((n_aux, n6), dtype=np.complex128)
    D6_values[0, [0, n6 // 3, n6 // 2]] = (0.11 + 0.02j, -0.04j, 0.05 - 0.01j)
    D6_values[1, [1, n6 // 4, n6 - 1]] = (-0.08j, 0.03 + 0.02j, 0.09)
    H_values = np.asarray(
        [[1.4 + 0.1j, 0.12 - 0.03j], [-0.02j, 0.85 - 0.08j]],
        dtype=np.complex128,
    )
    C6_mat = _aij(C6_values)
    D6_mat = _aij(D6_values)
    H6_mat = _aij(H_values)
    b6 = F6.createVecLeft()
    b6.getArray()[:] = 0.2 + 0.03j * np.arange(n6)
    b6.assemble()
    b_aux = H6_mat.createVecLeft()
    b_aux.getArray()[:] = (0.4 - 0.1j, -0.2 + 0.05j)
    b_aux.assemble()
    fine_blocks = PetscCondensedBlocks(
        None,
        C6_mat,
        D6_mat,
        H6_mat,
        b6,
        b_aux,
        n6,
        n_aux,
    )
    coarse_blocks, block_audit = project_condensed_blocks_to_coarse(
        fine_blocks,
        transfer,
        F2,
    )
    assert block_audit["global_p6_matrix_materialized"] is False
    assert block_audit["global_p6_transfer_materialized"] is False
    assert block_audit["projection_mode_count"] == n_aux
    assert block_audit["structural_zero_tolerance"] == 1.0e-14
    assert not np.allclose(H_values, np.eye(n_aux))

    fine_blocks.F = F6
    fine_shell, fine_context = create_matrix_free_condensed_operator(fine_blocks)
    coarse_shell, coarse_context = create_matrix_free_condensed_operator(coarse_blocks)
    max_f2_error = 0.0
    max_f2_absolute = 0.0
    max_a2_error = 0.0
    max_a2_absolute = 0.0
    for seed in (0, 1, 2, 235):
        q2 = _vector(coarse_blocks.F.createVecRight(), seed)
        p6 = F6.createVecRight()
        f6_result = F6.createVecLeft()
        f2_result = F2.createVecLeft()
        projected_f6 = coarse_blocks.F.createVecLeft()
        P.mult(q2, p6)
        F6.mult(p6, f6_result)
        P.multHermitian(f6_result, projected_f6)
        F2.mult(q2, f2_result)
        f2_absolute, f2_relative = _max_relative(f2_result, projected_f6)
        max_f2_error = max(max_f2_error, f2_relative)
        max_f2_absolute = max(max_f2_absolute, f2_absolute)
        fine_shell.mult(p6, f6_result)
        P.multHermitian(f6_result, projected_f6)
        coarse_shell.mult(q2, f2_result)
        a2_absolute, a2_relative = _max_relative(f2_result, projected_f6)
        max_a2_error = max(max_a2_error, a2_relative)
        max_a2_absolute = max(max_a2_absolute, a2_absolute)
        assert f2_absolute <= 1.0e-11
        assert a2_relative <= 1.0e-11
        assert a2_absolute <= 1.0e-11
        assert f2_relative <= 1.0e-11
        for vector in (projected_f6, f2_result, f6_result, p6, q2):
            vector.destroy()
    assert max_f2_error <= 1.0e-11
    assert max_f2_absolute <= 1.0e-11
    assert max_a2_error <= 1.0e-11
    assert max_a2_absolute <= 1.0e-11

    transfer_values = _dense_values(P)
    fine_c_values = _dense_values(fine_blocks.C)
    fine_d_values = _dense_values(fine_blocks.D)
    coarse_c_values = _dense_values(coarse_blocks.C)
    coarse_d_values = _dense_values(coarse_blocks.D)
    coarse_h_values = _dense_values(coarse_blocks.H)
    expected_c_values = transfer_values.conjugate().T @ fine_c_values
    expected_d_values = fine_d_values @ transfer_values
    c2_absolute, c2_relative = _array_error(coarse_c_values, expected_c_values)
    d2_absolute, d2_relative = _array_error(coarse_d_values, expected_d_values)
    h2_absolute, h2_relative = _array_error(coarse_h_values, H_values)
    assert c2_absolute <= 1.0e-11
    assert c2_relative <= 1.0e-11
    assert d2_absolute <= 1.0e-11
    assert d2_relative <= 1.0e-11
    assert h2_absolute <= 1.0e-11
    assert h2_relative <= 1.0e-11

    fine_b_values = np.asarray(
        fine_blocks.b_fe.getArray(readonly=True), dtype=PETSc.ScalarType
    ).copy()
    coarse_b_values = np.asarray(
        coarse_blocks.b_fe.getArray(readonly=True), dtype=PETSc.ScalarType
    ).copy()
    expected_b_values = transfer_values.conjugate().T @ fine_b_values
    b_fe_absolute, b_fe_relative = _array_error(coarse_b_values, expected_b_values)
    coarse_aux_values = np.asarray(
        coarse_blocks.b_aux.getArray(readonly=True), dtype=PETSc.ScalarType
    )
    expected_aux_values = np.asarray(
        b_aux.getArray(readonly=True), dtype=PETSc.ScalarType
    )
    b_aux_absolute, b_aux_relative = _array_error(
        coarse_aux_values, expected_aux_values
    )
    assert b_fe_absolute <= 1.0e-11
    assert b_fe_relative <= 1.0e-11
    assert b_aux_absolute <= 1.0e-11
    assert b_aux_relative <= 1.0e-11

    from src.solvers.hcurl_multilevel import ModalWoodburyPc

    class TinyF2Solver:
        def __init__(self, matrix):
            self.ksp = PETSc.KSP().create(matrix.getComm())
            self.ksp.setOperators(matrix)
            self.ksp.setType("preonly")
            self.ksp.getPC().setType("lu")
            self.ksp.setUp()

        def solve(self, source, target):
            self.ksp.solve(source, target)

        def destroy(self):
            self.ksp.destroy()

    base_solver = TinyF2Solver(coarse_blocks.F)
    woodbury = ModalWoodburyPc(
        base_solver=base_solver,
        C=coarse_blocks.C,
        D=coarse_blocks.D,
        H=coarse_blocks.H,
    )
    source = coarse_blocks.C.createVecLeft()
    target = coarse_blocks.C.createVecLeft()
    source.getArray()[:] = 0.17 + 0.03j * np.arange(source.getLocalSize())
    source.assemble()
    woodbury.solve(source, target)
    a2_values = _dense_values(coarse_blocks.F)
    projected_a2 = a2_values - coarse_c_values @ np.linalg.solve(
        coarse_h_values, coarse_d_values
    )
    expected_solution = np.linalg.solve(
        projected_a2,
        np.asarray(source.getArray(readonly=True), dtype=PETSc.ScalarType),
    )
    modal_absolute, modal_relative = _array_error(
        np.asarray(target.getArray(readonly=True), dtype=PETSc.ScalarType),
        expected_solution,
    )
    assert modal_absolute <= 1.0e-11
    assert modal_relative <= 1.0e-11
    source.destroy()
    target.destroy()
    woodbury.destroy()
    base_solver.destroy()

    fine_context.destroy(fine_shell)
    coarse_context.destroy(coarse_shell)
    fine_shell.destroy()
    coarse_shell.destroy()
    coarse_blocks.destroy()
    fine_blocks.destroy()
    P.destroy()
    transfer.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial-only fixture")
def test_p2_galerkin_rejects_missing_retained_schur():
    _mesh_3d, (V2, V6), (C2, C6) = _spaces(MPI.COMM_SELF)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    fine_condensed, _schurs = _retained_p6_fixture(V6, C6)
    fine_condensed.retained_local_schur_by_class = None
    with pytest.raises(ValueError, match="requires retained local Schur"):
        build_p2_galerkin_fine_matrix(fine_condensed, V2, V6, C2)
    transfer.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial-only fixture")
def test_serial_floquet_p2_galerkin_action():
    from dataclasses import replace

    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.test.test_46_task033_high_order_floquet_topology import (
        _fixed_target_fixture,
    )

    cfg, mesh_data, V2 = _fixed_target_fixture(2, h_nm=50.0)
    cfg = replace(cfg, incident_phi_deg=37.0)
    V6 = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    cfg6 = replace(cfg, nedelec_degree=6)
    mpc2_data = build_double_floquet_mpc(V2, mesh_data, cfg)
    mpc6_data = build_double_floquet_mpc(V6, mesh_data, cfg6)
    assert mpc2_data.num_x_constraints > 0
    assert mpc2_data.num_y_constraints > 0
    assert mpc2_data.num_corner_constraints > 0
    assert mpc6_data.num_x_constraints > 0
    assert mpc6_data.num_y_constraints > 0
    assert mpc6_data.num_corner_constraints > 0
    assert abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_y) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_x * cfg.floquet_phase_y) - 1.0) > 1.0e-8

    C2 = _constraint_map(V2, mpc2_data.mpc)
    C6 = _constraint_map(V6, mpc6_data.mpc)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    assert transfer.audit["cell_info_nonzero_count"] > 0
    fine_condensed, schurs = _retained_p6_fixture(V6, C6)
    F2, f2_audit = build_p2_galerkin_fine_matrix(
        fine_condensed,
        V2,
        V6,
        C2,
    )
    F6 = _assemble_fine_reference(V6, C6, schurs)
    P = _explicit_transfer_matrix(transfer)
    for seed in (0, 235):
        q2 = _vector(F2.createVecRight(), seed)
        q6 = F6.createVecRight()
        fine_result = F6.createVecLeft()
        projected = F2.createVecLeft()
        coarse_result = F2.createVecLeft()
        P.mult(q2, q6)
        F6.mult(q6, fine_result)
        P.multHermitian(fine_result, projected)
        F2.mult(q2, coarse_result)
        absolute, relative = _max_relative(coarse_result, projected)
        assert absolute <= 1.0e-11
        assert relative <= 1.0e-11
        for vector in (coarse_result, projected, fine_result, q6, q2):
            vector.destroy()
    assert f2_audit["projected_cells_global"] > 0
    F6.destroy()
    P.destroy()
    F2.destroy()
    transfer.destroy()


def _distributed_dtn_blocks(active_layout, n_aux=2, matrix_free_dtn=False):
    base_rhs = active_layout.copy()
    start, end = map(int, base_rhs.getOwnershipRange())
    ids = np.arange(start, end, dtype=PETSc.IntType)
    scale = float(max(int(base_rhs.getSize()), 1))
    base_rhs.getArray()[:] = (0.11 + 0.013j * (ids + 1)) / scale
    base_rhs.assemble()
    supports = tuple(ids.copy() for _mode in range(n_aux))
    assembler = DtnBlockAssembler(
        base_rhs,
        n_aux,
        traction_supports=supports,
        ell_supports=supports,
        matrix_free_dtn=matrix_free_dtn,
    )
    for mode in range(n_aux):
        assembler.add_mode(
            mode,
            traction_rows=ids,
            traction_values=(0.07 + 0.01j * (mode + 1)) * (ids + 1) / scale,
            ell_cols=ids,
            ell_values=(0.03 - 0.02j * (mode + 1)) * (ids + 1) / scale,
            auxiliary_diagonal=1.2 + 0.2j * (mode + 1),
            b_fe_rows=ids,
            b_fe_values=(0.019 + 0.007j * (mode + 1)) * (ids + 1) / scale,
            b_aux_value=0.12 + 0.04j * (mode + 1),
        )
    blocks = assembler.finish()
    audit = dict(assembler.preallocation_audit)
    base_rhs.destroy()
    return blocks, audit


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (2, 4), reason="requires MPI2 or MPI4")
def test_mpi_projected_p2_galerkin_action():
    comm = MPI.COMM_WORLD
    _mesh_3d, (V2, V6), (C2, C6) = _spaces(comm)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    fine_condensed, schurs = _retained_p6_fixture(V6, C6)
    F2, f2_audit = build_p2_galerkin_fine_matrix(
        fine_condensed,
        V2,
        V6,
        C2,
    )
    F6 = _assemble_fine_reference(V6, C6, schurs)
    fine_layout = F6.createVecLeft()
    fine_blocks, dtn_audit = _distributed_dtn_blocks(fine_layout)
    fine_layout.destroy()
    coarse_blocks, block_audit = project_condensed_blocks_to_coarse(
        fine_blocks,
        transfer,
        F2,
    )
    fine_blocks.F = F6
    assert f2_audit["global_p6_matrix_materialized"] is False
    assert f2_audit["projected_cells_global"] == 8
    assert block_audit["global_p6_matrix_materialized"] is False
    local_owned = len(C6.owned_active_original_dofs)
    assert comm.allreduce(local_owned, op=MPI.MIN) > 0
    owner_remote_nnz = (
        int(dtn_audit["d_offdiag_nnz_local_sum"]) if comm.rank == comm.size - 1 else 0
    )
    remote_d_offdiag_nnz = comm.allreduce(owner_remote_nnz, op=MPI.MAX)
    assert remote_d_offdiag_nnz > 0

    fine_shell, fine_context = create_matrix_free_condensed_operator(fine_blocks)
    coarse_shell, coarse_context = create_matrix_free_condensed_operator(coarse_blocks)
    max_action_absolute = 0.0
    max_action_relative = 0.0
    for seed in (0, 235):
        q2 = _vector(coarse_blocks.F.createVecRight(), seed)
        q6 = F6.createVecRight()
        fine_result = F6.createVecLeft()
        projected = coarse_blocks.F.createVecLeft()
        coarse_result = coarse_blocks.F.createVecLeft()
        transfer.apply(q2, q6)
        fine_shell.mult(q6, fine_result)
        transfer.apply_adjoint(fine_result, projected)
        coarse_shell.mult(q2, coarse_result)
        absolute, relative = _max_relative(coarse_result, projected)
        max_action_absolute = max(max_action_absolute, absolute)
        max_action_relative = max(max_action_relative, relative)
        assert absolute <= 1.0e-11
        assert relative <= 1.0e-11
        for vector in (coarse_result, projected, fine_result, q6, q2):
            vector.destroy()

    expected_rhs = coarse_blocks.F.createVecLeft()
    transfer.apply_adjoint(fine_blocks.b_fe, expected_rhs)
    rhs_absolute, rhs_relative = _max_relative(coarse_blocks.b_fe, expected_rhs)
    assert rhs_absolute <= 1.0e-11
    assert rhs_relative <= 1.0e-11
    if comm.rank == 0:
        print(
            "M4B_MPI_AUDIT",
            {
                "size": comm.size,
                "max_action_absolute": max_action_absolute,
                "max_action_relative": max_action_relative,
                "rhs_absolute": rhs_absolute,
                "rhs_relative": rhs_relative,
                "remote_d_offdiag_nnz": remote_d_offdiag_nnz,
                "p2_active_rows": C2.active_rows,
                "p6_active_rows": C6.active_rows,
                "projected_cells_global": f2_audit["projected_cells_global"],
                "f2_nnz_used": f2_audit["matrix_nnz_used"],
                "f2_nnz_allocated": f2_audit["matrix_nnz_allocated"],
                "projected_payload_lower_bound_bytes_global": block_audit[
                    "projected_payload_lower_bound_bytes_global"
                ],
            },
        )
    expected_rhs.destroy()
    fine_context.destroy(fine_shell)
    coarse_context.destroy(coarse_shell)
    fine_shell.destroy()
    coarse_shell.destroy()
    coarse_blocks.destroy()
    fine_blocks.destroy()
    transfer.destroy()
