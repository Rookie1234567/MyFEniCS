from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_local_dtn_woodbury import (
    HYBRID_DTN_WOODBURY_MODE_COUNT,
    HybridLocalDtnWoodburyFixedAction,
)
from src.solvers.hybrid_whole_endcap_fixed_smoother import (
    WHOLE_ENDCAP_COORDINATE_AXIS,
    WHOLE_ENDCAP_NUM_SLABS,
    WHOLE_ENDCAP_OVERLAP_FRACTION,
    WHOLE_ENDCAP_PRECONDITIONER_PROFILE,
    HybridWholeEndcapFixedSmootherAction,
    build_hybrid_whole_endcap_fixed_smoother_action,
)
from src.solvers.static_local_schur_action import create_static_local_schur_action


def _build_fixture(comm):
    mesh_3d = mesh.create_unit_cube(
        comm,
        6,
        3,
        2,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = mesh_3d.topology.dim
    owned_cells = int(mesh_3d.topology.index_map(tdim).size_local)
    cell_tags = mesh.meshtags(
        mesh_3d,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    V = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    return mesh_3d, cell_tags, V, compiled


def _fill_rhs(rhs: PETSc.Vec, seed: int) -> None:
    rng = np.random.default_rng(seed)
    values = rng.standard_normal(rhs.getSize()) + 1j * rng.standard_normal(
        rhs.getSize()
    )
    start, end = rhs.getOwnershipRange()
    rhs.getArray()[:] = np.asarray(values[start:end], dtype=PETSc.ScalarType)


def _relative_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _build_tiny_woodbury_components(operator: PETSc.Mat):
    rows = int(operator.getSize()[0])
    if rows < HYBRID_DTN_WOODBURY_MODE_COUNT:
        raise RuntimeError("tiny Woodbury smoke needs at least 40 active rows")
    comm = operator.getComm()
    mode_count = HYBRID_DTN_WOODBURY_MODE_COUNT
    H = PETSc.Mat().createAIJ((mode_count, mode_count), comm=comm)
    H.setUp()
    active_local_rows = int(operator.getLocalSize()[0])
    auxiliary_local_rows = int(H.getLocalSize()[0])
    C = PETSc.Mat().createAIJ(
        size=((active_local_rows, rows), (auxiliary_local_rows, mode_count)),
        comm=comm,
    )
    D = PETSc.Mat().createAIJ(
        size=((auxiliary_local_rows, mode_count), (active_local_rows, rows)),
        comm=comm,
    )
    C.setUp()
    D.setUp()
    c_first, c_last = (int(value) for value in C.getOwnershipRange())
    for row in range(c_first, min(c_last, mode_count)):
        C.setValue(row, row, PETSc.ScalarType(1.0))
    d_first, d_last = (int(value) for value in D.getOwnershipRange())
    for row in range(d_first, min(d_last, mode_count)):
        D.setValue(row, row, PETSc.ScalarType(1.0))
    h_first, h_last = (int(value) for value in H.getOwnershipRange())
    for row in range(h_first, min(h_last, mode_count)):
        H.setValue(row, row, PETSc.ScalarType(100.0))
    for matrix in (C, D, H):
        matrix.assemble()
    return C, D, H


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2, 4),
    reason="fixed whole-endcap smoke runs serial, MPI2, or MPI4",
)
def test_fixed_whole_endcap_smoother_and_woodbury_lifecycle():
    comm = MPI.COMM_WORLD
    mesh_3d, cell_tags, V, compiled = _build_fixture(comm)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    assert condensed.matrix is None
    action, action_context = create_static_local_schur_action(condensed)
    rhs = condensed.create_active_vector()
    other = condensed.create_active_vector()
    _fill_rhs(rhs, 237)
    _fill_rhs(other, 238)
    action_carrier = SimpleNamespace(
        A=action,
        b=rhs,
        static_condensation=SimpleNamespace(condensed=condensed),
        local_mesh=SimpleNamespace(mesh=mesh_3d),
        inventory={
            "global_A_materialized": False,
            "direct_factor_count": 0,
        },
    )
    fixed_smoother = None
    fixed_woodbury = None
    vectors: list[PETSc.Vec] = []
    auxiliary_matrices = None
    try:
        fixed_smoother = build_hybrid_whole_endcap_fixed_smoother_action(action_carrier)
        assert isinstance(fixed_smoother, HybridWholeEndcapFixedSmootherAction)
        assert fixed_smoother.operator.getType() == "python"
        assert fixed_smoother.plan.coordinate_axis == WHOLE_ENDCAP_COORDINATE_AXIS
        assert len(fixed_smoother.plan.coordinate_intervals) == WHOLE_ENDCAP_NUM_SLABS
        assert WHOLE_ENDCAP_OVERLAP_FRACTION == 0.0
        diagnostics = fixed_smoother.diagnostics
        assert diagnostics["operator_identity"] == "whole_endcap_ilu0_fixed_smoother"
        assert diagnostics["preconditioner_profile"] == (
            WHOLE_ENDCAP_PRECONDITIONER_PROFILE
        )
        assert diagnostics["ksp_created"] is False
        assert diagnostics["lifecycle"]["candidate_direct_factor_count"] == 0
        assert diagnostics["smoother"]["factor_only_storage"] is True
        assert diagnostics["smoother"]["local_solver_types"] == ["ilu"]
        assert diagnostics["factor_rows"] > 0
        assert diagnostics["factor_nnz"] > 0
        assert diagnostics["factor_csr_payload_estimate_bytes"] > 0
        assert diagnostics["smoother"]["max_sender_payload_bytes"] > 0
        assert diagnostics["smoother"]["max_owner_payload_bytes"] > 0

        first = action.createVecLeft()
        second = action.createVecLeft()
        combined = action.createVecRight()
        lhs = action.createVecLeft()
        rhs_action = action.createVecLeft()
        other_action = action.createVecLeft()
        vectors.extend((first, second, combined, lhs, rhs_action, other_action))
        fixed_smoother.apply(rhs, first)
        fixed_smoother.apply(rhs, second)
        assert _relative_error(first, second) <= 1.0e-14
        alpha = PETSc.ScalarType(0.7 - 0.2j)
        beta = PETSc.ScalarType(-0.3 + 0.4j)
        rhs.copy(combined)
        combined.scale(alpha)
        combined.axpy(beta, other)
        fixed_smoother.apply(combined, lhs)
        fixed_smoother.apply(rhs, rhs_action)
        fixed_smoother.apply(other, other_action)
        rhs_action.scale(alpha)
        other_action.scale(beta)
        rhs_action.axpy(PETSc.ScalarType(1.0), other_action)
        assert _relative_error(lhs, rhs_action) <= 1.0e-12

        smoother_apply_before_woodbury = fixed_smoother.diagnostics["apply_count"]
        auxiliary_matrices = _build_tiny_woodbury_components(action)
        fixed_woodbury = HybridLocalDtnWoodburyFixedAction(
            fixed_smoother,
            SimpleNamespace(
                F=action,
                C=auxiliary_matrices[0],
                D=auxiliary_matrices[1],
                H=auxiliary_matrices[2],
            ),
        )
        woodbury_diagnostics = fixed_woodbury.diagnostics
        assert woodbury_diagnostics["nested_ksp_created"] is False
        assert woodbury_diagnostics["base_factor_count"] == 1
        assert woodbury_diagnostics["woodbury"]["K_rank"] == (
            HYBRID_DTN_WOODBURY_MODE_COUNT
        )
        assert np.isfinite(woodbury_diagnostics["woodbury"]["K_condition_number"])
        assert woodbury_diagnostics["woodbury"]["arrays_finite"] is True
        assert woodbury_diagnostics["woodbury"]["apply_count"] == 0
        assert fixed_smoother.diagnostics["apply_count"] == (
            smoother_apply_before_woodbury + HYBRID_DTN_WOODBURY_MODE_COUNT
        )

        woodbury_target = action.createVecLeft()
        vectors.append(woodbury_target)
        fixed_woodbury.apply(rhs, woodbury_target)
        assert fixed_woodbury.diagnostics["woodbury"]["apply_count"] == 1
        assert fixed_smoother.diagnostics["apply_count"] == (
            smoother_apply_before_woodbury + HYBRID_DTN_WOODBURY_MODE_COUNT + 1
        )
        fixed_woodbury.destroy()
        assert fixed_woodbury.diagnostics["destroyed"] is True
        assert fixed_smoother.diagnostics["destroyed"] is False

        borrowed_target = action.createVecLeft()
        vectors.append(borrowed_target)
        fixed_smoother.apply(rhs, borrowed_target)
        assert np.isfinite(float(borrowed_target.norm()))
        fixed_smoother.destroy()
        assert fixed_smoother.factor_count_before_destroy == 1
        assert fixed_smoother.factor_count_after_destroy == 0
        assert fixed_smoother.factors_released is True
        assert fixed_smoother.diagnostics["destroyed"] is True
        with pytest.raises(RuntimeError, match="destroyed"):
            fixed_smoother.apply(rhs, borrowed_target)
        assert action.getType() == "python"
    finally:
        if fixed_woodbury is not None:
            fixed_woodbury.destroy()
        if fixed_smoother is not None:
            fixed_smoother.destroy()
        for vector in vectors:
            vector.destroy()
        rhs.destroy()
        other.destroy()
        action.destroy()
        action_context.destroy()
        if auxiliary_matrices is not None:
            for matrix in auxiliary_matrices:
                matrix.destroy()
        condensed.destroy()
