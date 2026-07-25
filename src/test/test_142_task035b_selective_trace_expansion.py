from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    CallerTraceExpansion,
    build_unconstrained_assembly_time_condensation,
    project_mpc_vector_to_active_trace,
    recover_owned_cell_interiors,
    recover_owned_trace_values,
)


def _problem(comm: MPI.Intracomm, nx: int):
    msh = mesh.create_unit_cube(
        comm,
        nx,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = msh.topology.dim
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    tags = mesh.meshtags(
        msh,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    function_space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    trial = ufl.TrialFunction(function_space)
    test = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + PETSc.ScalarType(2.3 - 0.17j)
            * ufl.inner(trial, test)
        )
        * dx(1)
    )
    return tags, function_space, compiled


def _qualification() -> dict[str, object]:
    return {
        "schema_version": "task035b.test-selective-trace-expansion.v1",
        "pass": True,
        "owner_aware_contiguous_petsc_rows": True,
        "inactive_modes_have_no_petsc_rows": True,
        "full_trace_matrix_constructed": False,
        "ordinary_default_changed": False,
    }


def _dense_complex_expansion(
    legacy,
    active_rows: int,
) -> tuple[np.ndarray, dict[int, tuple[np.ndarray, np.ndarray]]]:
    trace_rows = int(legacy.trace_rows)
    row_ids = np.arange(active_rows, dtype=PETSc.IntType)
    trace_index = np.arange(trace_rows, dtype=np.float64)[:, None]
    active_index = np.arange(active_rows, dtype=np.float64)[None, :]
    dense = (
        0.7
        + 0.013 * (trace_index + 1.0) * (active_index + 1.0)
    ) * np.exp(
        1j
        * (
            0.031 * (trace_index + 1.0)
            + 0.17 * (active_index + 1.0)
        )
    )
    dense /= np.linalg.norm(dense, axis=0)[None, :]
    expansion = {
        int(original): (
            row_ids.copy(),
            np.asarray(
                dense[int(trace_row)],
                dtype=np.complex128,
            ).copy(),
        )
        for original, trace_row in legacy.original_to_trace.items()
    }
    return dense, expansion


def _dense_matrix(matrix: PETSc.Mat) -> np.ndarray:
    converted = matrix.copy().convert("dense")
    try:
        return np.asarray(
            converted.getDenseArray(),
            dtype=np.complex128,
        ).copy()
    finally:
        converted.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial algebra test",
)
def test_generalized_trace_expansion_matches_ch_s_c_and_recovers() -> None:
    tags, function_space, compiled = _problem(MPI.COMM_SELF, 1)
    legacy = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
    )
    active_rows = 4
    dense_c, expansion = _dense_complex_expansion(legacy, active_rows)
    caller = CallerTraceExpansion(
        owned_active_rows=np.arange(active_rows, dtype=PETSc.IntType),
        expansion_by_original=expansion,
        full_trace_rows=legacy.trace_rows,
        active_rows=active_rows,
        qualification_audit=_qualification(),
    )
    selected = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
        caller_trace_expansion=caller,
    )

    legacy_schur = _dense_matrix(legacy.matrix)
    expected = dense_c.conj().T @ legacy_schur @ dense_c
    np.testing.assert_allclose(
        _dense_matrix(selected.matrix),
        expected,
        rtol=3.0e-13,
        atol=3.0e-12,
    )
    assert selected.matrix.getSize() == (active_rows, active_rows)
    assert selected.active_rows == active_rows
    assert selected.trace_rows > selected.active_rows
    assert selected.build_audit["caller_supplied_trace_expansion"] is True
    assert (
        selected.build_audit["inactive_trace_modes_receive_petsc_rows"]
        is False
    )
    assert selected.build_audit["full_trace_matrix_allocated"] is False
    assert (
        selected.trace_constraints.owned_active_original_dofs.size == 0
    )
    np.testing.assert_array_equal(
        selected.trace_constraints.owned_active_rows,
        np.arange(active_rows, dtype=PETSc.IntType),
    )

    q = np.asarray(
        [0.3 + 0.2j, -0.7 + 0.1j, 0.4 - 0.8j, 1.1 + 0.05j],
        dtype=np.complex128,
    )
    owned_rows, owned_values = recover_owned_trace_values(selected, q)
    expected_owned = np.asarray(
        [
            dense_c[selected.original_to_trace[int(original)]] @ q
            for original in owned_rows
        ],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(
        owned_values,
        expected_owned,
        rtol=2.0e-14,
        atol=2.0e-14,
    )

    storage_trace = dense_c @ q
    selected_interiors = recover_owned_cell_interiors(selected, q)
    legacy_interiors = recover_owned_cell_interiors(legacy, storage_trace)
    assert len(selected_interiors) == len(legacy_interiors) == 1
    np.testing.assert_array_equal(
        selected_interiors[0][0],
        legacy_interiors[0][0],
    )
    np.testing.assert_allclose(
        selected_interiors[0][1],
        legacy_interiors[0][1],
        rtol=3.0e-13,
        atol=3.0e-12,
    )

    full_vector = PETSc.Vec().createSeq(selected.full_rows)
    full_vector.set(PETSc.ScalarType(0.0))
    full_vector.assemble()
    with pytest.raises(
        NotImplementedError,
        match="active coordinates are generalized",
    ):
        project_mpc_vector_to_active_trace(selected, full_vector)

    full_vector.destroy()
    selected.destroy()
    legacy.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial identity endpoint test",
)
def test_caller_identity_endpoint_is_bitwise_legacy_schur() -> None:
    tags, function_space, compiled = _problem(MPI.COMM_SELF, 1)
    legacy = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
    )
    expansion = {
        int(original): (
            np.asarray([trace_row], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=np.complex128),
        )
        for original, trace_row in legacy.original_to_trace.items()
    }
    identity = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
        caller_trace_expansion=CallerTraceExpansion(
            owned_active_rows=np.arange(
                legacy.trace_rows,
                dtype=PETSc.IntType,
            ),
            expansion_by_original=expansion,
            full_trace_rows=legacy.trace_rows,
            active_rows=legacy.trace_rows,
            qualification_audit=_qualification(),
        ),
    )

    np.testing.assert_array_equal(
        _dense_matrix(identity.matrix),
        _dense_matrix(legacy.matrix),
    )
    assert identity.build_audit["caller_supplied_trace_expansion"] is True
    assert legacy.build_audit["caller_supplied_trace_expansion"] is False

    identity.destroy()
    legacy.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial fail-closed validation test",
)
def test_caller_trace_expansion_dimensions_and_ownership_fail_closed() -> None:
    tags, function_space, compiled = _problem(MPI.COMM_SELF, 1)
    legacy = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
    )
    _dense_c, expansion = _dense_complex_expansion(legacy, 4)
    valid = CallerTraceExpansion(
        owned_active_rows=np.arange(4, dtype=PETSc.IntType),
        expansion_by_original=expansion,
        full_trace_rows=legacy.trace_rows,
        active_rows=4,
        qualification_audit=_qualification(),
    )

    with pytest.raises(ValueError, match="full_trace_rows differs"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            tags,
            caller_trace_expansion=replace(
                valid,
                full_trace_rows=legacy.trace_rows + 1,
            ),
        )
    with pytest.raises(ValueError, match="ownership validation failed"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            tags,
            caller_trace_expansion=replace(
                valid,
                owned_active_rows=np.asarray(
                    [0, 1, 3],
                    dtype=PETSc.IntType,
                ),
            ),
        )
    missing = dict(expansion)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="cover exactly every storage"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            tags,
            caller_trace_expansion=replace(
                valid,
                expansion_by_original=missing,
            ),
        )
    invalid_qualification = dict(_qualification())
    invalid_qualification["inactive_modes_have_no_petsc_rows"] = False
    with pytest.raises(ValueError, match="not qualified"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            tags,
            caller_trace_expansion=replace(
                valid,
                qualification_audit=invalid_qualification,
            ),
        )
    with pytest.raises(ValueError, match="cannot be combined with mpc"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            tags,
            mpc=object(),
            caller_trace_expansion=valid,
        )

    legacy.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 ownership and algebra test",
)
def test_mpi2_generalized_rows_follow_owner_plan_without_inactive_rows() -> None:
    comm = MPI.COMM_WORLD
    tags, function_space, compiled = _problem(comm, 2)
    legacy = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
    )
    active_rows = comm.size
    dense_c = np.zeros(
        (legacy.trace_rows, active_rows),
        dtype=np.complex128,
    )
    expansion: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for original, trace_row in legacy.original_to_trace.items():
        active = int(original) % active_rows
        coefficient = np.exp(1j * 0.019 * (int(original) + 1))
        dense_c[int(trace_row), active] = coefficient
        expansion[int(original)] = (
            np.asarray([active], dtype=PETSc.IntType),
            np.asarray([coefficient], dtype=np.complex128),
        )
    selected = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
        caller_trace_expansion=CallerTraceExpansion(
            owned_active_rows=np.asarray(
                [comm.rank],
                dtype=PETSc.IntType,
            ),
            expansion_by_original=expansion,
            full_trace_rows=legacy.trace_rows,
            active_rows=active_rows,
            qualification_audit=_qualification(),
        ),
    )

    assert selected.matrix.getSize() == (active_rows, active_rows)
    assert tuple(map(int, selected.matrix.getOwnershipRange())) == (
        comm.rank,
        comm.rank + 1,
    )
    assert (
        selected.trace_constraints.build_audit[
            "inactive_mode_rows_allocated"
        ]
        is False
    )

    expected = np.empty((active_rows, active_rows), dtype=np.complex128)
    trace_start, trace_stop = map(
        int,
        legacy.matrix.getOwnershipRange(),
    )
    for column in range(active_rows):
        full_x = legacy.matrix.createVecRight()
        full_x.getArray()[:] = np.asarray(
            dense_c[trace_start:trace_stop, column],
            dtype=PETSc.ScalarType,
        )
        full_x.assemble()
        full_y = legacy.matrix.createVecLeft()
        legacy.matrix.mult(full_x, full_y)
        local_y = np.asarray(
            full_y.getArray(readonly=True),
            dtype=np.complex128,
        )
        for row in range(active_rows):
            local = np.vdot(
                dense_c[trace_start:trace_stop, row],
                local_y,
            )
            expected[row, column] = comm.allreduce(local, op=MPI.SUM)
        full_y.destroy()
        full_x.destroy()

    local_row = np.asarray(
        selected.matrix.getValues(
            np.asarray([comm.rank], dtype=PETSc.IntType),
            np.arange(active_rows, dtype=PETSc.IntType),
        ),
        dtype=np.complex128,
    )[0]
    np.testing.assert_allclose(
        local_row,
        expected[comm.rank],
        rtol=3.0e-13,
        atol=4.0e-12,
    )

    q = np.asarray([0.4 - 0.3j, -0.2 + 0.7j], dtype=np.complex128)
    owned_original, owned_values = recover_owned_trace_values(selected, q)
    expected_values = np.asarray(
        [
            dense_c[selected.original_to_trace[int(original)]] @ q
            for original in owned_original
        ],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(
        owned_values,
        expected_values,
        rtol=2.0e-14,
        atol=2.0e-14,
    )

    selected.destroy()
    legacy.destroy()
