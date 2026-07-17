from __future__ import annotations

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.local_slab_solver import LocalBackendPlan
from src.solvers.lu_teacher_local_solver import SparseLuTeacherLocalSolver
from src.solvers.physical_slab_two_level import DistributedPhysicalSlabSmoother


def _diagonal_matrix(size: int) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(size=(size, size), nnz=1, comm=PETSc.COMM_WORLD)
    matrix.setUp()
    start, end = matrix.getOwnershipRange()
    for row in range(start, end):
        matrix.setValue(row, row, 2.0 + 0.01j * (row + 1))
    matrix.assemble()
    return matrix


def _exact_plan(_subdomain: int) -> LocalBackendPlan:
    return LocalBackendPlan(
        identity="sparse_lu_teacher",
        requires_ilu_factor=False,
        requires_portable_operator=True,
        allows_fallback=False,
    )


def test_plan_rejects_fallback_without_ilu() -> None:
    with pytest.raises(ValueError, match="fallback requires an ILU"):
        LocalBackendPlan(
            identity="invalid",
            requires_ilu_factor=False,
            requires_portable_operator=True,
            allows_fallback=True,
        )


def test_full_exact_profile_gathers_complete_no_hidden_ilu_diagnostics() -> None:
    size = 16
    matrix = _diagonal_matrix(size)
    subdomains = tuple(
        np.arange(start, start + 4, dtype=PETSc.IntType)
        for start in range(0, size, 4)
    )

    def factory(_subdomain, operator, fallback_action):
        assert fallback_action is None
        return SparseLuTeacherLocalSolver(operator)

    smoother = DistributedPhysicalSlabSmoother(
        matrix,
        subdomains,
        ilu_levels=0,
        factor_only_storage=True,
        local_solver_factory=factory,
        local_backend_plan_resolver=_exact_plan,
    )
    source = matrix.createVecRight()
    source.set(1.0 + 0.5j)
    target = source.duplicate()
    smoother.solve(source, target)

    diagnostics = smoother.diagnostics
    rows = diagnostics["global_backend_diagnostics"]
    assert [row["subdomain"] for row in rows] == [0, 1, 2, 3]
    assert {row["owner_rank"] for row in rows}.issubset(
        set(range(PETSc.COMM_WORLD.getSize()))
    )
    assert diagnostics["exact_backend_count"] == 4
    assert diagnostics["ilu_factor_constructed_count"] == 0
    assert diagnostics["global_stored_factor_nnz"] == 0
    assert diagnostics["global_ilu_apply_count"] == 0
    assert diagnostics["global_exact_apply_count"] == 4
    assert diagnostics["hidden_fallback_count"] == 0
    assert all(row["exact_factor_nnz"] > 0 for row in rows)
    assert all(row["exact_factor_storage_bytes"] > 0 for row in rows)

    smoother.destroy()
    assert len(smoother.destroy_diagnostics) == 4
    assert all(row["destroyed"] for row in smoother.destroy_diagnostics)
    smoother.destroy()
    target.destroy()
    source.destroy()
    matrix.destroy()


def test_ordinary_ilu_path_still_builds_and_applies_factor() -> None:
    matrix = _diagonal_matrix(8)
    subdomains = (np.arange(8, dtype=PETSc.IntType),)
    smoother = DistributedPhysicalSlabSmoother(
        matrix,
        subdomains,
        ilu_levels=0,
        factor_only_storage=True,
    )
    source = matrix.createVecRight()
    source.set(1.0)
    target = source.duplicate()
    smoother.solve(source, target)
    diagnostics = smoother.diagnostics
    assert diagnostics["ilu_factor_constructed_count"] == 1
    assert diagnostics["global_stored_factor_nnz"] > 0
    assert diagnostics["global_ilu_apply_count"] == 1
    assert diagnostics["exact_backend_count"] == 0

    smoother.destroy()
    target.destroy()
    source.destroy()
    matrix.destroy()
