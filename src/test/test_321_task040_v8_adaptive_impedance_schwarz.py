"""Focused bounded-patch contracts for the Task040 adaptive pilot."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.hybrid_adaptive_impedance_schwarz as adaptive_schwarz
from src.solvers.hybrid_adaptive_impedance_schwarz import (
    MAX_LOCAL_ACTIVE_ROWS,
    _fixed_shift_values,
    build_adaptive_impedance_schwarz_action,
    reduce_cell_tangential_face_mass,
)


def _fake_condensed(comm: MPI.Comm, *, empty_local: bool = False, rows: int = 6):
    first, last = (rows * comm.rank) // comm.size, (rows * (comm.rank + 1)) // comm.size
    if empty_local and comm.rank != 0:
        cell_rows: list[tuple[int, ...]] = []
    elif empty_local:
        cell_rows = [tuple(range(rows))]
    elif comm.size == 1:
        cell_rows = [
            tuple(sorted((index, (index + 1) % rows))) for index in range(rows)
        ]
    else:
        cell_rows = [
            tuple(sorted((index, (index + 1) % rows)))
            for index in range(first, last)
        ]
    expansions = {
        index: (
            np.asarray([index], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=PETSc.ScalarType),
        )
        for index in range(rows)
    }
    recoveries = []
    schurs = {}
    for cell_index, cell_rows_values in enumerate(cell_rows):
        key = ("same_cell_class", len(cell_rows_values))
        recoveries.append(
            SimpleNamespace(
                trace_original_dofs=np.asarray(cell_rows_values, dtype=PETSc.IntType),
                class_key=key,
            )
        )
        schurs[key] = np.asarray(
            2.0 * np.eye(len(cell_rows_values))
            - 0.1 * (np.ones((len(cell_rows_values), len(cell_rows_values))) - np.eye(len(cell_rows_values))),
            dtype=PETSc.ScalarType,
        )
    return SimpleNamespace(
        comm=comm,
        active_rows=rows,
        cell_recovery_maps=tuple(recoveries),
        retained_local_schur_by_class=schurs,
        trace_constraints=SimpleNamespace(expansion_by_original=expansions),
    ), cell_rows


def _bare(comm: MPI.Comm, rows: int = 6) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, rows), (PETSc.DECIDE, rows)),
        nnz=3,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(3.0))
        if row + 1 < rows:
            matrix.setValue(row, row + 1, PETSc.ScalarType(-0.2 + 0.03j))
    matrix.assemble()
    return matrix


def _face_masses(cell_rows: list[tuple[int, ...]]):
    return {
        index: np.asarray(
            0.4 * np.eye(len(cell_rows_values))
            + 0.05 * (
                np.ones((len(cell_rows_values), len(cell_rows_values)))
                - np.eye(len(cell_rows_values))
            ),
            dtype=PETSc.ScalarType,
        )
        for index, cell_rows_values in enumerate(cell_rows)
    }


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="bounded adaptive pilot is focused on serial and MPI2",
)
def test_task040_adaptive_patch_is_bounded_owner_routed_and_reused() -> None:
    comm = MPI.COMM_WORLD
    condensed, cells = _fake_condensed(comm)
    bare = _bare(comm)
    action = None
    source = None
    target = None
    try:
        action = build_adaptive_impedance_schwarz_action(
            condensed,
            bare,
            raw_tangential_face_mass_by_cell=_face_masses(cells),
            beta=0.7 + 0.2j,
        )
        source = bare.createVecRight()
        target = bare.createVecLeft()
        first, last = map(int, source.getOwnershipRange())
        source.array[:] = np.asarray(
            [0.4 + 0.02j * row for row in range(first, last)],
            dtype=PETSc.ScalarType,
        )
        source.assemble()
        action.apply(source, target)
        diagnostics = action.diagnostics
        assert diagnostics["overlap_semantics"] == "one_shared_entity_support"
        assert diagnostics["rows_max"] <= MAX_LOCAL_ACTIVE_ROWS
        assert diagnostics["row_count_histogram"] == {"2": 6}
        assert diagnostics["class_count"] == 1
        assert diagnostics["patch_count"] == 6
        assert diagnostics["class_reuse_saved_count"] == 5
        assert sum(diagnostics["owner_loads"]) == diagnostics["class_count"]
        mass_audits = diagnostics["mass_audits_local"]
        assert diagnostics["raw_mass_audit_cache_size_local"] == 1
        assert len(mass_audits) == 1
        assert diagnostics["factor_class_reuse_enabled"] is True
        assert diagnostics["factor_class_reuse_observed"] is True
        assert diagnostics["factor_only_storage"] is True
        assert diagnostics["pou_error"] <= 1.0e-12
        assert diagnostics["covered_active_rows"] == diagnostics["active_rows"]
        assert diagnostics["full_vector_numeric_allgather"] is False
        assert diagnostics["full_numeric_replica"] is False
        assert diagnostics["numeric_collective_type"] == "bounded_object_alltoall"
        assert diagnostics["numeric_object_alltoall_count"] == 5
        assert diagnostics["numeric_object_alltoall_count_per_apply"] == 5
        assert diagnostics["diagnostic_scalar_gather"] is True
        assert diagnostics["numeric_target_write_type"] == "PETSc_local_array"
        assert diagnostics["target_assembly_collective"] is False
        assert (
            diagnostics["max_sender_payload_bytes"]
            >= diagnostics["max_single_patch_payload_bytes"]
        )
        assert diagnostics["max_owner_payload_bytes"] > 0
        assert np.all(np.isfinite(target.array))
        assert all(
            audit["reduction"] == "C^H_M_t_C"
            and audit["raw_hermitian_psd"]
            and audit["principal_submatrix_used"] is False
            and audit["patch_operator_differs_from_bare_principal"] == "not_evaluated"
            and audit["source"] == "caller_declared_real_hcurl_tangential_trace_mass"
            and audit["actual_hcurl_facet_form_assembler"] == "not_implemented_by_component"
            and audit["usage_count_local"] == len(cells)
            for audit in mass_audits.values()
        )
        assert diagnostics["factor_lifecycle"]["factor_count_ready"] == 1
        assert diagnostics["factor_lifecycle"]["diagnostic_matrices_released"] is False
        ratio_summary = diagnostics["last_real_apply_patch_residual_summary"]
        assert ratio_summary["count"] == 6
        assert np.isfinite(ratio_summary["min"])
        assert np.isfinite(ratio_summary["median"])
        assert np.isfinite(ratio_summary["p90"])
        assert np.isfinite(ratio_summary["max"])
        all_cells = comm.allgather(
            tuple(tuple(int(row) for row in rows) for rows in cells)
        )
        global_cells = [rows for packet in all_cells for rows in packet]
        multiplicity = np.bincount(
            np.asarray(global_cells, dtype=np.int64).reshape(-1), minlength=6
        )
        volume = 2.0 * np.eye(2) - 0.1 * (np.ones((2, 2)) - np.eye(2))
        mass = 0.4 * np.eye(2) + 0.05 * (np.ones((2, 2)) - np.eye(2))
        patch_matrix = volume - 1j * (0.7 + 0.2j) * mass - 0.3j * np.eye(2)
        expected = np.zeros(6, dtype=PETSc.ScalarType)
        for rows in global_cells:
            row_array = np.asarray(rows, dtype=np.int64)
            rhs = np.asarray(
                [0.4 + 0.02j * row for row in row_array], dtype=PETSc.ScalarType
            )
            expected[row_array] += np.linalg.solve(patch_matrix, rhs) / multiplicity[
                row_array
            ]
        first, last = map(int, target.getOwnershipRange())
        assert np.allclose(target.array, expected[first:last])
        assert np.allclose(
            _fixed_shift_values(np.asarray([3.0, 0.0]), 3.0),
            np.asarray([-0.3j, -3.0e-13j]),
        )
        action.release_diagnostic_matrices()
        assert action.diagnostics["factor_lifecycle"]["diagnostic_matrices_released"] is True
        assert action.diagnostics["diagnostic_unavailable_after_release"] is True
        action.destroy()
        assert action.diagnostics["factor_lifecycle"]["factor_count_ready"] == 0
        assert action.diagnostics["bare_f_borrowed"] is True
    finally:
        if action is not None:
            action.destroy()
        if target is not None:
            target.destroy()
        if source is not None:
            source.destroy()
        bare.destroy()


def test_task040_adaptive_face_mass_rejects_invalid_contracts() -> None:
    condensed, cells = _fake_condensed(MPI.COMM_SELF)
    size = len(cells[0])
    good = _face_masses(cells)[0]
    reduce_cell_tangential_face_mass(condensed, 0, good)
    with pytest.raises(ValueError, match="square raw local block"):
        reduce_cell_tangential_face_mass(condensed, 0, np.eye(size - 1))
    nonhermitian = np.eye(size, dtype=PETSc.ScalarType)
    nonhermitian[0, 1] = 1.0
    with pytest.raises(ValueError, match="not Hermitian"):
        reduce_cell_tangential_face_mass(condensed, 0, nonhermitian)
    with pytest.raises(ValueError, match="non-finite"):
        reduce_cell_tangential_face_mass(
            condensed, 0, np.full((size, size), np.nan, dtype=PETSc.ScalarType)
        )
    with pytest.raises(ValueError, match="positive semidefinite"):
        reduce_cell_tangential_face_mass(
            condensed, 0, -np.eye(size, dtype=PETSc.ScalarType)
        )
    with pytest.raises(ValueError, match="empty or non-finite"):
        reduce_cell_tangential_face_mass(
            condensed, 0, np.zeros((size, size), dtype=PETSc.ScalarType)
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="bounded adaptive pilot is focused on serial and MPI2",
)
def test_task040_adaptive_support_preflight_is_collective_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comm = MPI.COMM_WORLD
    condensed, cells = _fake_condensed(comm)
    rectangular = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 6), (PETSc.DECIDE, 5)), nnz=1, comm=comm
    )
    rectangular.assemble()
    try:
        with pytest.raises(RuntimeError, match="not square"):
            build_adaptive_impedance_schwarz_action(
                condensed,
                rectangular,
                raw_tangential_face_mass_by_cell=_face_masses(cells),
                beta=0.7,
            )
    finally:
        rectangular.destroy()

    condensed.active_rows = 5
    bare = _bare(comm)
    try:
        with pytest.raises(RuntimeError, match="active row count mismatch"):
            build_adaptive_impedance_schwarz_action(
                condensed,
                bare,
                raw_tangential_face_mass_by_cell=_face_masses(cells),
                beta=0.7,
            )
    finally:
        bare.destroy()

    condensed.active_rows = 6
    for bad_rows, message in (
        ((1, 0), "strictly sorted"),
        ((0, 6), "outside"),
    ):
        def bad_contributions(_condensed, rows=bad_rows):
            local_rows = rows if comm.rank == 0 else (0, 1)
            yield 0, np.asarray(local_rows, dtype=PETSc.IntType), np.eye(2)

        monkeypatch.setattr(
            adaptive_schwarz,
            "iter_owned_constrained_schur_contributions",
            bad_contributions,
        )
        bare = _bare(comm)
        try:
            with pytest.raises(RuntimeError, match=message):
                build_adaptive_impedance_schwarz_action(
                    condensed,
                    bare,
                    raw_tangential_face_mass_by_cell=_face_masses(cells),
                    beta=0.7,
                )
        finally:
            bare.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="bounded adaptive pilot is focused on serial and MPI2",
)
def test_task040_adaptive_patch_row_cap_fails_before_factor() -> None:
    comm = MPI.COMM_WORLD
    rows = MAX_LOCAL_ACTIVE_ROWS + 1
    condensed, cells = _fake_condensed(comm, empty_local=True, rows=rows)
    bare = _bare(comm, rows=rows)
    try:
        with pytest.raises(RuntimeError, match="fixed active-row cap"):
            build_adaptive_impedance_schwarz_action(
                condensed,
                bare,
                raw_tangential_face_mass_by_cell=_face_masses(cells),
                beta=0.7,
            )
    finally:
        bare.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="empty-local ownership regression is MPI2-only",
)
def test_task040_adaptive_patch_accepts_empty_local_owner_rank() -> None:
    comm = MPI.COMM_WORLD
    condensed, cells = _fake_condensed(comm, empty_local=True, rows=4)
    bare = _bare(comm, rows=4)
    action = None
    source = None
    target = None
    try:
        action = build_adaptive_impedance_schwarz_action(
            condensed,
            bare,
            raw_tangential_face_mass_by_cell=_face_masses(cells),
            beta=0.7,
        )
        source = bare.createVecRight()
        target = bare.createVecLeft()
        source.set(PETSc.ScalarType(1.0))
        source.assemble()
        action.apply(source, target)
        diagnostics = action.diagnostics
        assert diagnostics["row_count_histogram"] == {"4": 1}
        assert diagnostics["numeric_object_alltoall_count"] == 5
        assert diagnostics["full_numeric_replica"] is False
        action.release_diagnostic_matrices()
        assert np.all(np.isfinite(target.array))
    finally:
        if action is not None:
            action.destroy()
        if target is not None:
            target.destroy()
        if source is not None:
            source.destroy()
        bare.destroy()
