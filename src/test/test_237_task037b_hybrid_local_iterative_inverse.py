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
from src.solvers.hybrid_local_iterative_inverse import (
    H5_ATOL,
    H5_COORDINATE_AXIS,
    H5_ILU_LEVELS,
    H5_INTERPOLATION,
    H5_MAX_IT,
    H5_NUM_SLABS,
    H5_OVERLAP_FRACTION,
    H5_RESTART,
    H5_RTOL,
    build_hybrid_local_iterative_inverse,
)
from src.solvers.physical_slab_two_level import build_owner_local_slab_plan
from src.solvers.static_local_schur_action import create_static_local_schur_action


def _build_h5_fixture(comm):
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


def _fill_rhs(rhs: PETSc.Vec) -> None:
    rng = np.random.default_rng(237)
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


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="H5 tiny local inverse runs serial or MPI2",
)
def test_h5_local_inverse_configuration_residual_and_lifecycle():
    comm = MPI.COMM_WORLD
    mesh_3d, cell_tags, V, compiled = _build_h5_fixture(comm)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    action, action_context = create_static_local_schur_action(condensed)
    rhs = condensed.create_active_vector()
    _fill_rhs(rhs)
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
    default_plan = build_owner_local_slab_plan(
        condensed,
        mesh_3d,
        domain_z=(0.0, 1.0),
        num_slabs=6,
        overlap_fraction=0.0,
    )
    assert default_plan.coordinate_axis == 2
    assert len(default_plan.coordinate_intervals) == 6

    inverse = build_hybrid_local_iterative_inverse(action_carrier)
    result = None
    repeat = None
    f_only_inverse = None
    f_only_result = None
    try:
        assert inverse.plan.coordinate_axis == H5_COORDINATE_AXIS == 0
        assert len(inverse.plan.coordinate_intervals) == H5_NUM_SLABS
        diagnostics = inverse._diagnostics()
        config = diagnostics["configuration"]
        assert config == {
            "coordinate_axis": H5_COORDINATE_AXIS,
            "num_slabs": H5_NUM_SLABS,
            "overlap_fraction": H5_OVERLAP_FRACTION,
            "interpolation": H5_INTERPOLATION,
            "ilu_levels": H5_ILU_LEVELS,
            "factor_only": True,
            "one_apply_per_pc_apply": True,
            "two_step_action_operator": None,
            "outer_solver": "right_fgmres",
            "restart": H5_RESTART,
            "max_it": H5_MAX_IT,
            "rtol": H5_RTOL,
            "atol": H5_ATOL,
            "true_residual_limit": 1.0e-8,
        }
        assert action.getType() == "python"
        assert diagnostics["operator"]["global_A_materialized"] is False
        assert diagnostics["operator"]["identity"] == "complete_hybrid_action"
        assert diagnostics["operator"]["external_dtn_correction"] == "included"
        assert diagnostics["no_direct_fallback"] is True
        assert diagnostics["smoother"]["factor_only_storage"] is True
        assert diagnostics["smoother"]["local_solver_types"] == ["ilu"] * H5_NUM_SLABS
        assert diagnostics["assembly_payload"]["max_sender_payload_bytes"] > 0
        assert (
            diagnostics["assembly_payload"]["max_owner_payload_bytes"]
            >= (diagnostics["assembly_payload"]["max_sender_payload_bytes"])
        )

        result = inverse.solve(rhs)
        assert result.converged_reason > 0
        assert result.iterations <= H5_MAX_IT
        assert np.isfinite(result.reported_relative_residual)
        assert np.isfinite(result.true_relative_residual)
        independent_residual = rhs.duplicate()
        action.mult(result.solution, independent_residual)
        independent_residual.scale(PETSc.ScalarType(-1.0))
        independent_residual.axpy(PETSc.ScalarType(1.0), rhs)
        independent_true = float(independent_residual.norm()) / max(
            float(rhs.norm()),
            1.0e-30,
        )
        independent_residual.destroy()
        assert result.true_relative_residual <= 1.0e-8
        assert abs(result.true_relative_residual - independent_true) <= 1.0e-13
        assert inverse.smoother.diagnostics["partition_weight_sum_error"] <= 1.0e-12
        assert set(result.stationary_correction_residuals) == {1, 2, 4, 8}
        assert all(
            np.isfinite(value)
            for value in result.stationary_correction_residuals.values()
        )

        repeat = inverse.solve(rhs)
        assert repeat.converged_reason == result.converged_reason
        assert repeat.iterations == result.iterations
        assert _relative_error(result.solution, repeat.solution) <= 1.0e-10

        inverse.destroy()
        f_only_inverse = build_hybrid_local_iterative_inverse(
            action_carrier,
            operator_override=action,
            operator_identity="fine_action_F_only",
        )
        f_only_diagnostics = f_only_inverse._diagnostics()
        assert f_only_diagnostics["operator"]["identity"] == "fine_action_F_only"
        assert f_only_diagnostics["operator"]["external_dtn_correction"] == ("excluded")
        f_only_result = f_only_inverse.solve(rhs)
        assert f_only_result.converged_reason > 0
        assert f_only_result.true_relative_residual <= 1.0e-8
        assert action.getType() == "python"
        f_only_inverse.destroy()
        assert f_only_inverse.factors_released is True
    finally:
        if f_only_result is not None:
            f_only_result.destroy()
        if f_only_inverse is not None:
            f_only_inverse.destroy()
        if repeat is not None:
            repeat.destroy()
        if result is not None:
            result.destroy()
        inverse.destroy()
        assert inverse.factors_released is True
        assert action.getType() == "python"
        rhs.destroy()
        action.destroy()
        action_context.destroy()
        condensed.destroy()
