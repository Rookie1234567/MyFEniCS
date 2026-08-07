import numpy as np
import pytest
from types import SimpleNamespace
from mpi4py import MPI
from petsc4py import PETSc

import dolfinx_mpc
import src.solvers.physical_slab_two_level as slab_module
from src.geometry.tetra_mesh_audit import owned_cell_geometry
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_slab_two_level import (
    assemble_owner_local_slab_matrix,
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
    owner_local_slab_diagonal_shift,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture
from src.solvers.hcurl_cell_static_condensation import (
    owned_hcurl_cell_interior_dofs,
)


def _build_mpc(V):
    interiors = owned_hcurl_cell_interior_dofs(V)
    interior_set = {int(value) for values in interiors for value in values}
    trace = [
        value
        for value in range(V.dofmap.index_map.size_global)
        if value not in interior_set
    ]
    mpc = dolfinx_mpc.MultiPointConstraint(V)
    mpc.add_constraint(
        V,
        np.asarray([trace[-1]], dtype=np.int32),
        np.asarray([trace[0]], dtype=np.int64),
        np.asarray([0.5 + 0.25j], dtype=PETSc.ScalarType),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 1], dtype=np.int32),
    )
    mpc.finalize()
    return mpc


def _dense(matrix: PETSc.Mat) -> np.ndarray:
    size = int(matrix.getSize()[0])
    indptr, indices, values = matrix.getValuesCSR()
    dense = np.zeros((size, size), dtype=PETSc.ScalarType)
    for row in range(size):
        dense[row, indices[indptr[row] : indptr[row + 1]]] = values[
            indptr[row] : indptr[row + 1]
        ]
    return dense


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2, 4),
    reason="M2a owner-local slab oracle supports serial/MPI2/MPI4",
)
def test_owner_local_slab_matrix_and_diagonal_match_assembled():
    comm = MPI.COMM_WORLD
    mesh, cell_tags, V, compiled = _build_fixture(comm)
    mpc = _build_mpc(V) if comm.size == 1 else None
    kwargs = {
        "mpc": mpc,
        "retain_local_schur_for_matrix_free": True,
    }
    assembled = build_unconstrained_assembly_time_condensation(
        compiled, V, cell_tags, **kwargs
    )
    action_only = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        materialize_global_matrix=False,
        **kwargs,
    )
    assert action_only.matrix is None
    assert assembled.matrix is not None
    assert len(owned_cell_geometry(mesh)) == len(action_only.cell_recovery_maps)

    plan = build_owner_local_slab_plan(
        action_only,
        mesh,
        domain_z=(0.0, 1.0),
        num_slabs=3,
        overlap_fraction=0.0,
    )
    assert plan.coordinate_axis == 2
    assert len(plan.coordinate_intervals) == 3
    assert all(count > 0 for count in plan.slab_row_counts)
    if comm.size == 1:
        assert action_only.trace_constraints.slave_rows > 0
    assigned = {
        slab for slab, owner in enumerate(plan.slab_owners) if owner == comm.rank
    }
    assert all(
        plan.owner_rows[slab].size
        == (plan.slab_row_counts[slab] if slab in assigned else 0)
        for slab in range(3)
    )

    for slab, owner in enumerate(plan.slab_owners):
        matrix, audit = assemble_owner_local_slab_matrix(action_only, plan, slab)
        indices = (
            plan.owner_rows[slab]
            if comm.rank == owner
            else np.empty(0, dtype=PETSc.IntType)
        )
        index_set = PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
        reference = assembled.matrix.createSubMatrices([index_set])[0]
        index_set.destroy()
        assert audit["dynamic_allocation"] is True
        assert audit["max_sender_payload_bytes"] > 0
        assert audit["max_owner_payload_bytes"] >= audit["max_sender_payload_bytes"]
        assert audit["max_owner_payload_bytes"] <= (
            comm.size * audit["max_sender_payload_bytes"]
        )
        assert audit["matrix_allocation_ratio"] >= 1.0
        if comm.size > 1 and comm.rank != owner:
            assert plan.owner_rows[slab].size == 0
            assert matrix is None
        local_abs = 0.0
        local_rel = 0.0
        if comm.rank == owner:
            assert matrix is not None
            expected = _dense(reference)
            observed = _dense(matrix)
            difference = observed - expected
            local_abs = float(np.max(np.abs(difference))) if difference.size else 0.0
            local_rel = float(np.linalg.norm(difference)) / max(
                float(np.linalg.norm(expected)), 1.0e-30
            )
            assert matrix.getSize() == (indices.size, indices.size)
            assert matrix.getSize() == reference.getSize()
            assert len(audit["matrix_fingerprint"]) == 64
            assert set(audit["matrix_fingerprint"]) <= set("0123456789abcdef")
        assert comm.allreduce(local_abs, op=MPI.MAX) <= 1.0e-11
        assert comm.allreduce(local_rel, op=MPI.MAX) <= 1.0e-11
        reference.destroy()
        if matrix is not None:
            matrix.destroy()

    diagonal, diagonal_audit = build_owner_local_slab_diagonal(action_only)
    assembled_diagonal = assembled.create_active_vector()
    assembled.matrix.getDiagonal(assembled_diagonal)
    difference = diagonal.copy()
    difference.axpy(PETSc.ScalarType(-1.0), assembled_diagonal)
    local_max_error = difference.getArray(readonly=True)
    max_error = comm.allreduce(
        float(np.max(np.abs(local_max_error))) if local_max_error.size else 0.0,
        op=MPI.MAX,
    )
    relative_error = difference.norm() / max(assembled_diagonal.norm(), 1.0e-30)
    assert max_error <= 1.0e-11
    assert relative_error <= 1.0e-11
    global_scale = diagonal_audit["global_diagonal_max_abs"]
    assert global_scale > 0.0

    start, end = assembled_diagonal.getOwnershipRange()
    gathered = comm.gather(
        (int(start), int(end), assembled_diagonal.getArray(readonly=True).copy()),
        root=0,
    )
    full_diagonal = None
    if comm.rank == 0:
        full_diagonal = np.empty(assembled.active_rows, dtype=PETSc.ScalarType)
        for packet_start, packet_end, values in gathered:
            full_diagonal[packet_start:packet_end] = values
    full_diagonal = comm.bcast(full_diagonal, root=0)
    for slab, owner in enumerate(plan.slab_owners):
        shift, shift_audit = owner_local_slab_diagonal_shift(
            diagonal, plan, slab, global_scale
        )
        assert shift_audit["owner_local_row_count"] == plan.slab_row_counts[slab]
        if comm.rank == owner:
            expected_shift = (
                -1j
                * 0.1
                * np.maximum(
                    np.abs(full_diagonal[plan.owner_rows[slab]]),
                    1.0e-12 * global_scale,
                )
            )
            np.testing.assert_allclose(shift, expected_shift, atol=1.0e-11, rtol=0.0)
        else:
            assert shift is None

    for vector in (difference, assembled_diagonal, diagonal):
        vector.destroy()
    action_only.destroy()
    assembled.destroy()


def test_row_closure_routes_geometry_external_neighbor(monkeypatch):
    blocks = {
        0: np.asarray(
            [[2.0 + 0.1j, 0.3 - 0.2j], [0.4j, 3.0]],
            dtype=PETSc.ScalarType,
        ),
        1: np.asarray(
            [[5.0 - 0.3j, 0.2j], [0.1 - 0.1j, 7.0]],
            dtype=PETSc.ScalarType,
        ),
    }
    recovery_maps = (
        SimpleNamespace(trace_original_dofs=np.asarray([10, 11]), class_key=0),
        SimpleNamespace(trace_original_dofs=np.asarray([11, 12]), class_key=1),
    )
    condensed = SimpleNamespace(
        comm=MPI.COMM_SELF,
        matrix=None,
        active_rows=3,
        cell_recovery_maps=recovery_maps,
        trace_constraints=SimpleNamespace(
            expansion_by_original={
                10: (
                    np.asarray([0], dtype=PETSc.IntType),
                    np.ones(1, dtype=PETSc.ScalarType),
                ),
                11: (
                    np.asarray([1], dtype=PETSc.IntType),
                    np.ones(1, dtype=PETSc.ScalarType),
                ),
                12: (
                    np.asarray([2], dtype=PETSc.IntType),
                    np.ones(1, dtype=PETSc.ScalarType),
                ),
            }
        ),
        retained_local_schur_by_class=blocks,
    )

    def create_active_vector():
        return PETSc.Vec().createMPI((3, 3), comm=MPI.COMM_SELF)

    condensed.create_active_vector = create_active_vector
    records = [
        SimpleNamespace(coordinates=np.asarray([[0, 0, 0], [1, 1, 0.4]], dtype=float)),
        SimpleNamespace(
            coordinates=np.asarray([[0, 0, 0.6], [1, 1, 1.0]], dtype=float)
        ),
    ]
    monkeypatch.setattr(
        slab_module,
        "owned_cell_geometry",
        lambda _mesh: records,
    )
    plan = build_owner_local_slab_plan(
        condensed,
        SimpleNamespace(),
        domain_z=(0.0, 1.0),
        num_slabs=2,
        overlap_fraction=0.0,
    )
    assert plan.local_cell_indices_by_slab == ((0, 1), (0, 1))
    assembled = PETSc.Mat().createAIJ(size=(3, 3), comm=PETSc.COMM_SELF)
    assembled.setValues([0, 1], [0, 1], blocks[0], addv=PETSc.InsertMode.ADD_VALUES)
    assembled.setValues([1, 2], [1, 2], blocks[1], addv=PETSc.InsertMode.ADD_VALUES)
    assembled.assemble()
    for slab in range(2):
        observed, _audit = assemble_owner_local_slab_matrix(condensed, plan, slab)
        rows = plan.owner_rows[slab]
        index_set = PETSc.IS().createGeneral(rows, comm=PETSc.COMM_SELF)
        reference = assembled.createSubMatrices([index_set])[0]
        index_set.destroy()
        np.testing.assert_allclose(
            _dense(observed), _dense(reference), atol=1.0e-12, rtol=0.0
        )
        observed.destroy()
        reference.destroy()
    assembled.destroy()
