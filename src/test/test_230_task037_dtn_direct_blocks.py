from unittest.mock import patch

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.condensed_dtn as condensed_dtn
from src.solvers.condensed_dtn import (
    DtnBlockAssembler,
    MatrixFreeDtnProbe,
    condensed_rhs,
    create_matrix_free_condensed_operator,
    extract_petsc_condensed_blocks,
    gather_small_petsc_matrix,
    recover_petsc_auxiliary,
    relative_action_error,
)
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.test.test_229_task037_action_only_condensation import _build_systems


def _fill_active(vector: PETSc.Vec, offset: float) -> None:
    start, end = vector.getOwnershipRange()
    values = np.arange(start, end, dtype=np.float64) + offset
    vector.getArray()[:] = values + 1j * (values + 0.5) / 17.0
    vector.assemble()


def _mode_stream(
    start: int,
    end: int,
    n_aux: int,
) -> tuple[dict[str, np.ndarray | complex], ...]:
    owned = np.arange(start, end, dtype=PETSc.IntType)
    stream = []
    for mode in range(n_aux):
        count = min(3, len(owned))
        if count:
            traction_rows = owned[(mode + 2 * np.arange(count)) % len(owned)]
            ell_cols = owned[(mode + 1 + 3 * np.arange(count)) % len(owned)]
        else:
            traction_rows = np.empty(0, dtype=PETSc.IntType)
            ell_cols = np.empty(0, dtype=PETSc.IntType)
        traction_values = np.asarray(
            [
                (mode + 1.0) * (row + 1.0) + 1j * (row + 2.0) / 11.0
                for row in traction_rows
            ],
            dtype=PETSc.ScalarType,
        )
        ell_values = np.asarray(
            [
                (0.2 + 0.1j * mode) * (col + 1.0) - 1j * (col + 1.0) / 19.0
                for col in ell_cols
            ],
            dtype=PETSc.ScalarType,
        )
        b_fe_values = np.asarray(
            [
                0.03 * (mode + 1.0) * (row + 1.0) + 1j * (row + 1.0) / 23.0
                for row in traction_rows
            ],
            dtype=PETSc.ScalarType,
        )
        stream.append(
            {
                "traction_rows": traction_rows,
                "traction_values": traction_values,
                "ell_cols": ell_cols,
                "ell_values": ell_values,
                "auxiliary_diagonal": 1.2 + 0.1j * (mode + 1),
                "b_fe_rows": traction_rows.copy(),
                "b_fe_values": b_fe_values,
                "b_aux_value": 0.4 - 0.05j * mode,
            }
        )
    return tuple(stream)


def _build_augmented_oracle(
    fine: PETSc.Mat,
    base_rhs: PETSc.Vec,
    stream: tuple[dict[str, np.ndarray | complex], ...],
) -> tuple[PETSc.Mat, PETSc.Vec]:
    comm = fine.getComm().tompi4py()
    n_fe = int(fine.getSize()[0])
    n_aux = len(stream)
    start, end = fine.getOwnershipRange()
    local_fe = end - start
    local_aug = local_fe + (n_aux if comm.rank == comm.size - 1 else 0)
    total = n_fe + n_aux
    matrix = PETSc.Mat().createAIJ(
        size=((local_aug, total), (local_aug, total)),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    for row in range(start, end):
        columns, values = fine.getRow(row)
        if len(columns):
            matrix.setValues(
                np.asarray([row], dtype=PETSc.IntType),
                columns,
                values.reshape((1, -1)),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
    rhs = PETSc.Vec().createMPI((local_aug, total), comm=comm)
    if end > start:
        rhs.setValues(
            np.arange(start, end, dtype=PETSc.IntType),
            base_rhs.getArray(readonly=True),
        )
    for mode, contribution in enumerate(stream):
        traction_rows = contribution["traction_rows"]
        traction_values = contribution["traction_values"]
        ell_cols = contribution["ell_cols"]
        ell_values = contribution["ell_values"]
        b_fe_rows = contribution["b_fe_rows"]
        b_fe_values = contribution["b_fe_values"]
        for repeat_scale in (1.0, 0.25) if mode == 0 else (1.0,):
            if len(traction_rows):
                matrix.setValues(
                    traction_rows,
                    np.asarray([n_fe + mode], dtype=PETSc.IntType),
                    (repeat_scale * traction_values).reshape((-1, 1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            if len(ell_cols):
                matrix.setValues(
                    np.asarray([n_fe + mode], dtype=PETSc.IntType),
                    ell_cols,
                    (repeat_scale * ell_values).reshape((1, -1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            if comm.rank == comm.size - 1:
                matrix.setValue(
                    n_fe + mode,
                    n_fe + mode,
                    repeat_scale * contribution["auxiliary_diagonal"],
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
                rhs.setValue(
                    n_fe + mode,
                    repeat_scale * contribution["b_aux_value"],
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            if len(b_fe_rows):
                rhs.setValues(
                    b_fe_rows,
                    repeat_scale * b_fe_values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
    matrix.assemble()
    rhs.assemble()
    return matrix, rhs


def _vector_error(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    value = float(difference.norm())
    difference.destroy()
    return value


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2, 4),
    reason="M1b direct DtN block fixture supports serial/MPI2/MPI4",
)
def test_direct_dtn_blocks_match_extracted_oracle_and_action_only_fine():
    V, _tags, _compiled, assembled, action_only = _build_systems(MPI.COMM_WORLD)
    fine_reference = assembled.matrix
    assert fine_reference is not None
    n_fe = int(fine_reference.getSize()[0])
    n_aux = 3
    start, end = fine_reference.getOwnershipRange()
    stream = _mode_stream(start, end, n_aux)
    rank_support_counts = MPI.COMM_WORLD.allgather(
        tuple(len(np.unique(contribution["ell_cols"])) for contribution in stream)
    )
    assert all(count > 0 for counts in rank_support_counts for count in counts)
    base_rhs = action_only.create_active_vector()
    _fill_active(base_rhs, 0.75)
    oracle_matrix, oracle_rhs_augmented = _build_augmented_oracle(
        fine_reference,
        base_rhs,
        stream,
    )
    oracle = extract_petsc_condensed_blocks(
        oracle_matrix,
        oracle_rhs_augmented,
        n_fe=n_fe,
        n_aux=n_aux,
    )
    assert oracle.F is not None

    assembler = DtnBlockAssembler(
        base_rhs,
        n_aux,
        traction_supports=tuple(
            contribution["traction_rows"] for contribution in stream
        ),
        ell_supports=tuple(contribution["ell_cols"] for contribution in stream),
    )
    matrix_free_assembler = DtnBlockAssembler(
        base_rhs,
        n_aux,
        traction_supports=tuple(
            contribution["traction_rows"] for contribution in stream
        ),
        ell_supports=tuple(contribution["ell_cols"] for contribution in stream),
        matrix_free_dtn=True,
    )
    for mode, contribution in enumerate(stream):
        repeats = (1.0, 0.25) if mode == 0 else (1.0,)
        for repeat_scale in repeats:
            values = dict(
                traction_rows=contribution["traction_rows"],
                traction_values=repeat_scale * contribution["traction_values"],
                ell_cols=contribution["ell_cols"],
                ell_values=repeat_scale * contribution["ell_values"],
                auxiliary_diagonal=repeat_scale * contribution["auxiliary_diagonal"],
                b_fe_rows=contribution["b_fe_rows"],
                b_fe_values=repeat_scale * contribution["b_fe_values"],
                b_aux_value=repeat_scale * contribution["b_aux_value"],
            )
            assembler.add_mode(mode, **values)
            matrix_free_assembler.add_mode(mode, **values)
    with patch.object(
        condensed_dtn,
        "extract_petsc_condensed_blocks",
        side_effect=AssertionError("direct DtN path extracted an augmented matrix"),
    ):
        direct = assembler.finish()
    matrix_free = matrix_free_assembler.finish()
    assert direct.F is None
    assert matrix_free.F is None
    assert matrix_free_assembler.preallocation_audit["matrix_free_dtn"] is True
    assert matrix_free_assembler.preallocation_audit["explicit_c_matrix_count"] == 0
    assert matrix_free_assembler.preallocation_audit["explicit_d_matrix_count"] == 0
    assert assembler.preallocation_audit["explicit_c_matrix_count"] == 1
    assert assembler.preallocation_audit["explicit_d_matrix_count"] == 1
    assert assembler.preallocation_audit["python_triplet_cache"] is False
    assert assembler.preallocation_audit["c_row_nnz_max_local"] <= n_aux
    assert assembler.preallocation_audit["c_row_nnz_local_sum"] == sum(
        len(np.unique(contribution["traction_rows"])) for contribution in stream
    )
    expected_diag = sum(rank_support_counts[-1])
    expected_offdiag = sum(
        sum(counts[mode] for counts in rank_support_counts[:-1])
        for mode in range(n_aux)
    )
    if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1:
        assert assembler.preallocation_audit["d_diag_nnz_local_sum"] == expected_diag
        assert (
            assembler.preallocation_audit["d_offdiag_nnz_local_sum"] == expected_offdiag
        )
    else:
        assert assembler.preallocation_audit["d_diag_nnz_local_sum"] == 0
        assert assembler.preallocation_audit["d_offdiag_nnz_local_sum"] == 0

    for oracle_matrix_block, direct_matrix_block in (
        (oracle.C, direct.C),
        (oracle.D, direct.D),
        (oracle.H, direct.H),
    ):
        assert oracle_matrix_block.getSize() == direct_matrix_block.getSize()
        assert (
            oracle_matrix_block.getOwnershipRange()
            == direct_matrix_block.getOwnershipRange()
        )
        assert (
            oracle_matrix_block.getOwnershipRangeColumn()
            == direct_matrix_block.getOwnershipRangeColumn()
        )
        oracle_dense = gather_small_petsc_matrix(oracle_matrix_block)
        direct_dense = gather_small_petsc_matrix(direct_matrix_block)
        np.testing.assert_allclose(oracle_dense, direct_dense, atol=1.0e-12, rtol=0.0)
    assert oracle.b_fe.getOwnershipRange() == direct.b_fe.getOwnershipRange()
    assert oracle.b_aux.getOwnershipRange() == direct.b_aux.getOwnershipRange()
    b_fe_error = _vector_error(oracle.b_fe, direct.b_fe)
    b_aux_error = _vector_error(oracle.b_aux, direct.b_aux)
    assert b_fe_error <= 1.0e-12
    assert b_aux_error <= 1.0e-12

    fine_action, _fine_context = create_static_local_schur_action(action_only)
    oracle_operator, _oracle_context = create_matrix_free_condensed_operator(
        oracle,
        fine_operator=fine_action,
    )
    direct_operator, _direct_context = create_matrix_free_condensed_operator(
        direct,
        fine_operator=fine_action,
    )
    matrix_free_operator, _matrix_free_context = create_matrix_free_condensed_operator(
        matrix_free,
        fine_operator=fine_action,
    )
    max_action_error = 0.0
    for offset in (0.25, 1.25, 2.25):
        source = action_only.create_active_vector()
        _fill_active(source, offset)
        max_action_error = max(
            max_action_error,
            relative_action_error(oracle_operator, direct_operator, source),
            relative_action_error(oracle_operator, matrix_free_operator, source),
        )
        source.destroy()
    rng = np.random.default_rng(230)
    source = action_only.create_active_vector()
    source.getArray()[:] = rng.standard_normal(
        source.getLocalSize()
    ) + 1j * rng.standard_normal(source.getLocalSize())
    source.assemble()
    max_action_error = max(
        max_action_error,
        relative_action_error(oracle_operator, matrix_free_operator, source),
        relative_action_error(oracle_operator, direct_operator, source),
    )
    source.destroy()
    assert max_action_error <= 1.0e-11
    matrix_free_rhs = condensed_rhs(matrix_free)
    direct_rhs = condensed_rhs(direct)
    assert _vector_error(matrix_free_rhs, direct_rhs) <= 1.0e-12
    source = action_only.create_active_vector()
    _fill_active(source, 1.75)
    direct_aux = recover_petsc_auxiliary(direct, source)
    matrix_free_aux = recover_petsc_auxiliary(matrix_free, source)
    assert _vector_error(matrix_free_aux, direct_aux) <= 1.0e-11
    matrix_free_aux.destroy()
    direct_aux.destroy()
    source.destroy()
    matrix_free_rhs.destroy()
    direct_rhs.destroy()
    oracle_condensed_rhs = condensed_rhs(oracle)
    direct_condensed_rhs = condensed_rhs(direct)
    condensed_rhs_error = _vector_error(oracle_condensed_rhs, direct_condensed_rhs)
    assert condensed_rhs_error <= 1.0e-12

    oracle_condensed_rhs.destroy()
    direct_condensed_rhs.destroy()
    direct_operator.destroy()
    matrix_free_operator.destroy()
    oracle_operator.destroy()
    fine_action.destroy()
    direct.destroy()
    matrix_free.destroy()
    oracle.destroy()
    oracle_rhs_augmented.destroy()
    oracle_matrix.destroy()
    base_rhs.destroy()
    action_only.destroy()
    assembled.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="E0 synthetic probe is a serial light Gate",
)
def test_e0_matrix_free_probe_uses_one_mode_stream_for_primary_and_oracle():
    _V, _tags, _compiled, assembled, action_only = _build_systems(MPI.COMM_SELF)
    base_rhs = action_only.create_active_vector()
    _fill_active(base_rhs, 0.125)
    start, end = base_rhs.getOwnershipRange()
    stream = _mode_stream(start, end, 3)
    identities = tuple(
        {
            "mode_key": ("synthetic", mode),
            "beta": 1.0 + 0.1j * mode,
            "polarization": "s" if mode % 2 == 0 else "p",
            "power_normalization": 1.0 + mode,
            "rayleigh_warning": False,
        }
        for mode in range(3)
    )
    probe = MatrixFreeDtnProbe(
        base_rhs,
        3,
        traction_supports=tuple(item["traction_rows"] for item in stream),
        ell_supports=tuple(item["ell_cols"] for item in stream),
        mode_identities=identities,
        expected_mode_count=3,
    )
    try:
        for mode, contribution in enumerate(stream):
            probe.add_mode(
                mode,
                traction_rows=contribution["traction_rows"],
                traction_values=contribution["traction_values"],
                ell_cols=contribution["ell_cols"],
                ell_values=contribution["ell_values"],
                auxiliary_diagonal=contribution["auxiliary_diagonal"],
                b_fe_rows=contribution["b_fe_rows"],
                b_fe_values=contribution["b_fe_values"],
                b_aux_value=contribution["b_aux_value"],
            )
        primary = probe.finish()
        audit = probe.audit()
        assert audit["gate_pass"] is True
        assert audit["forward_action_relative_error_max"] <= 1.0e-11
        assert audit["auxiliary_recovery_relative_error_max"] <= 1.0e-11
        assert audit["physical_rhs_identity_relative_error"] <= 1.0e-12
        assert audit["mode_identity"]["count"] == 3
        assert audit["mode_identity"]["primary_oracle_match"] is True
        assert audit["materialization"]["profiles_separate"] is True
        assert audit["materialization"]["primary"]["explicit_c_matrix_count"] == 0
        assert audit["materialization"]["primary"]["explicit_d_matrix_count"] == 0
        assert audit["materialization"]["oracle"]["explicit_c_matrix_count"] == 1
        assert audit["materialization"]["oracle"]["explicit_d_matrix_count"] == 1
        assert audit["adjoint"]["status"] == "optional_not_run_with_reason"
        assert primary.F is None
    finally:
        probe.destroy()
        base_rhs.destroy()
        action_only.destroy()
        assembled.destroy()
