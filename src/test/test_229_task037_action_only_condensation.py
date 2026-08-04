from unittest.mock import patch

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.hcurl_assembly_time_condensation as condensation_module
from src.solvers.hcurl_assembly_time_condensation import (
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
    project_mpc_vector_to_active_trace,
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.test.test_224_task037_static_local_schur_action import _build_fixture


def _fill_vector(vector: PETSc.Vec, offset: float = 0.0) -> None:
    start, end = vector.getOwnershipRange()
    values = np.arange(start, end, dtype=np.float64) + offset
    vector.getArray()[:] = values + 1j * (values + 1.0) / 13.0
    vector.assemble()


def _build_systems(comm, *, appended_rows: int = 0):
    _mesh, cell_tags, V, compiled = _build_fixture(comm)
    owned_cells = int(V.mesh.topology.index_map(V.mesh.topology.dim).size_local)
    support = (np.arange(owned_cells, dtype=np.int32),) if appended_rows else ()
    groups = (0,) * appended_rows
    kwargs = {
        "appended_global_rows": appended_rows,
        "appended_support_owned_cell_groups": support,
        "appended_support_group_by_row": groups,
        "retain_local_schur_for_matrix_free": True,
    }
    assembled = build_unconstrained_assembly_time_condensation(
        compiled, V, cell_tags, **kwargs
    )
    with patch.object(
        condensation_module,
        "_distributed_trace_preallocation",
        side_effect=AssertionError("action-only path called preallocation"),
    ):
        action_only = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            materialize_global_matrix=False,
            **kwargs,
        )
    return V, cell_tags, compiled, assembled, action_only


def test_serial_action_only_skips_global_matrix_and_preserves_layouts():
    V, cell_tags, compiled, assembled, action_only = _build_systems(
        MPI.COMM_SELF, appended_rows=2
    )
    assert assembled.matrix is not None
    assert action_only.matrix is None
    ordinary = build_unconstrained_assembly_time_condensation(compiled, V, cell_tags)
    assert ordinary.matrix is not None
    assert ordinary.retained_local_schur_by_class is None
    assert ordinary.build_audit["retained_local_schur_enabled"] is False
    assert ordinary.build_audit["retained_local_schur_class_count_sum"] == 0
    assert ordinary.build_audit["retained_local_schur_bytes_sum"] == 0
    assert action_only.build_audit["matrix_materialized"] is False
    assert action_only.build_audit["global_active_F_allocated"] is False
    assert action_only.build_audit["trace_preallocation_status"] == (
        "not_run_action_only"
    )
    assert action_only.build_audit["trace_insertion_status"] == ("not_run_action_only")
    assert action_only.build_audit["final_assembly_status"] == ("not_run_action_only")
    assert (
        action_only.build_audit["final_matrix_assembly_deferred_for_appended_rows"]
        is False
    )
    for system in (assembled, action_only):
        assert system.build_audit["retained_local_schur_enabled"] is True
        assert system.build_audit["retained_local_schur_class_count_local"] == len(
            system.retained_local_schur_by_class
        )
        assert system.build_audit["retained_local_schur_bytes_local"] == sum(
            int(schur.nbytes) for schur in system.retained_local_schur_by_class.values()
        )
    assert assembled.retained_local_schur_by_class is not None
    assert set(assembled.retained_local_schur_by_class) == set(
        action_only.retained_local_schur_by_class
    )

    with pytest.raises(ValueError, match="retained local Schur"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            materialize_global_matrix=False,
        )

    fine_assembled = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
    )
    fine_action, _context = create_static_local_schur_action(action_only)
    max_action_error = 0.0
    for offset in (0.5, 1.5, 2.5):
        source = fine_assembled.create_active_vector()
        _fill_vector(source, offset)
        expected = fine_assembled.matrix.createVecLeft()
        observed = fine_action.createVecLeft()
        fine_assembled.matrix.mult(source, expected)
        fine_action.mult(source, observed)
        difference = observed.copy()
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        max_action_error = max(
            max_action_error,
            difference.norm() / max(expected.norm(), 1.0e-30),
        )
        difference.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
    rng = np.random.default_rng(229)
    source = fine_assembled.create_active_vector()
    values = rng.standard_normal(source.getLocalSize())
    source.getArray()[:] = values + 1j * rng.standard_normal(len(values))
    source.assemble()
    expected = fine_assembled.matrix.createVecLeft()
    observed = fine_action.createVecLeft()
    fine_assembled.matrix.mult(source, expected)
    fine_action.mult(source, observed)
    difference = observed.copy()
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    max_action_error = max(
        max_action_error,
        difference.norm() / max(expected.norm(), 1.0e-30),
    )
    assert max_action_error <= 1.0e-11

    full = PETSc.Vec().createMPI(
        (int(V.dofmap.index_map.size_local), assembled.full_rows),
        comm=MPI.COMM_SELF,
    )
    _fill_vector(full, 1.5)
    condensed_rhs = condense_unconstrained_vector_to_active_trace(
        assembled, full, side="right"
    )
    action_rhs = condense_unconstrained_vector_to_active_trace(
        action_only, full, side="right"
    )
    assert condensed_rhs.getSize() == assembled.active_rows + 2
    assert action_rhs.getSize() == action_only.active_rows + 2
    np.testing.assert_allclose(
        condensed_rhs.getArray(readonly=True),
        action_rhs.getArray(readonly=True),
        atol=1.0e-12,
        rtol=0.0,
    )
    project_full = full.duplicate()
    project_full.set(0.0)
    start, _end = project_full.getOwnershipRange()
    owned_trace = assembled.owned_trace_original_dofs
    trace_local = np.asarray(owned_trace, dtype=np.int64) - start
    project_full.getArray()[trace_local] = full.getArray(readonly=True)[trace_local]
    project_full.assemble()
    projected = project_mpc_vector_to_active_trace(assembled, project_full)
    projected_action = project_mpc_vector_to_active_trace(action_only, project_full)
    assert projected.getSize() == assembled.active_rows + 2
    np.testing.assert_allclose(
        projected.getArray(readonly=True),
        projected_action.getArray(readonly=True),
        atol=1.0e-12,
        rtol=0.0,
    )
    left = full.duplicate()
    right = full.duplicate()
    _fill_vector(left, 2.0)
    _fill_vector(right, 3.0)
    assert (
        abs(
            cell_interior_schur_bilinear(assembled, left, right)
            - cell_interior_schur_bilinear(action_only, left, right)
        )
        <= 1.0e-12
    )

    for vector in (
        right,
        left,
        projected_action,
        projected,
        action_rhs,
        condensed_rhs,
        project_full,
        full,
        difference,
        observed,
        expected,
        source,
    ):
        vector.destroy()
    fine_action.destroy()
    fine_assembled.destroy()
    action_only.destroy()
    assembled.destroy()
    ordinary.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (2, 4), reason="MPI2/MPI4 action-only condensation"
)
def test_mpi2_action_only_matches_assembled_action_and_rhs():
    V, _tags, _compiled, assembled, action_only = _build_systems(MPI.COMM_WORLD)
    action, _context = create_static_local_schur_action(action_only)
    source = assembled.create_active_vector()
    _fill_vector(source, 0.25)
    expected = assembled.matrix.createVecLeft()
    observed = action.createVecLeft()
    assembled.matrix.mult(source, expected)
    action.mult(source, observed)
    difference = observed.copy()
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    assert difference.norm() / max(expected.norm(), 1.0e-30) <= 1.0e-11

    full = PETSc.Vec().createMPI(
        (int(V.dofmap.index_map.size_local), assembled.full_rows),
        comm=MPI.COMM_WORLD,
    )
    _fill_vector(full, 0.75)
    left_rhs = condense_unconstrained_vector_to_active_trace(
        assembled, full, side="right"
    )
    right_rhs = condense_unconstrained_vector_to_active_trace(
        action_only, full, side="right"
    )
    assert left_rhs.getSize() == right_rhs.getSize() == assembled.active_rows
    difference_rhs = left_rhs.copy()
    difference_rhs.axpy(PETSc.ScalarType(-1.0), right_rhs)
    assert difference_rhs.norm() <= 1.0e-12

    for vector in (
        difference_rhs,
        right_rhs,
        left_rhs,
        full,
        difference,
        observed,
        expected,
        source,
    ):
        vector.destroy()
    action.destroy()
    action_only.destroy()
    assembled.destroy()
