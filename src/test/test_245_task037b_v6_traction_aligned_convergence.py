from __future__ import annotations

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduIterativeConfig,
    create_action_block_ldu_preconditioner,
    multimetric_true_residual_decision,
    solve_hybrid_block_ldu_iterative,
)
from src.solvers.hybrid_fem_modal_iterative import create_hybrid_assembled_block_action
from src.test.test_241_task037b_hybrid_action_modal_schur import (
    _actions,
    _destroy_fixture,
    _tiny_fixture,
)


def _residuals(value: float) -> dict[str, float]:
    return {
        "reported_relative_residual": value,
        "global_true_relative_residual": value,
        "bottom_true_relative_residual": value,
        "top_true_relative_residual": value,
        "modal_true_relative_residual": value,
    }


def test_outer_ksp_profile_keeps_variable_pc_fgmres_and_allows_fixed_gmres10():
    default = HybridBlockLduIterativeConfig()
    assert default.ksp_type == "fgmres"
    assert default.restart == 90
    fixed = HybridBlockLduIterativeConfig(
        ksp_type="gmres", restart=10, fixed_preconditioner=True
    )
    assert fixed.ksp_type == "gmres"
    assert fixed.restart == 10
    with pytest.raises(ValueError, match="fixed-preconditioner"):
        HybridBlockLduIterativeConfig(ksp_type="gmres", restart=10)
    with pytest.raises(ValueError, match="fixed-preconditioner"):
        HybridBlockLduIterativeConfig(
            ksp_type="gmres", restart=90, fixed_preconditioner=True
        )


def test_tight_five_residual_decision_is_fail_closed():
    passing = multimetric_true_residual_decision(1, _residuals(4.0e-9))
    assert passing["positive"] is True
    expected_decision = (
        "CONVERGED_USER"
        if getattr(PETSc.KSP.ConvergedReason, "CONVERGED_USER", None) is not None
        else "CONVERGED_RTOL"
    )
    assert passing["decision"] == expected_decision
    one_failed = _residuals(4.0e-9)
    one_failed["top_true_relative_residual"] = 5.1e-9
    assert multimetric_true_residual_decision(1, one_failed)["decision"] == "ITERATING"
    nonfinite = _residuals(4.0e-9)
    nonfinite["modal_true_relative_residual"] = np.nan
    assert (
        multimetric_true_residual_decision(1, nonfinite)["decision"]
        == "DIVERGED_NANORINF"
    )
    negative = _residuals(4.0e-9)
    negative["bottom_true_relative_residual"] = -1.0
    assert (
        multimetric_true_residual_decision(1, negative)["decision"]
        == "DIVERGED_NANORINF"
    )
    maxed = _residuals(5.0e-9)
    maxed["modal_true_relative_residual"] = 5.1e-9
    assert (
        multimetric_true_residual_decision(1000, maxed)["decision"] == "DIVERGED_MAX_IT"
    )


@pytest.mark.parametrize(
    "ksp_type,restart,fixed_preconditioner",
    [("fgmres", 90, False), ("gmres", 10, True)],
    ids=["default-fgmres90", "fixed-gmres10"],
)
def test_tiny_right_ksp_profiles_retain_snapshot_and_release_workspace(
    ksp_type, restart, fixed_preconditioner
):
    fixture = _tiny_fixture()
    bottom, top = _actions(fixture)
    operator, operator_context = create_hybrid_assembled_block_action(
        fixture["bottom"], fixture["top"], fixture["coupling"]
    )
    preconditioner = None
    result = None
    rhs_bottom = fixture["bottom"].A.createVecRight()
    rhs_top = fixture["top"].A.createVecRight()
    rhs_bottom.set(0.0)
    rhs_top.set(0.0)
    first, last = (int(value) for value in rhs_bottom.getOwnershipRange())
    rhs_bottom.getArray()[:] = np.asarray(
        [1.0 + 0.1j, -0.5 + 0.2j, 0.8 - 0.3j, 0.2 + 0.4j][first:last],
        dtype=PETSc.ScalarType,
    )
    first, last = (int(value) for value in rhs_top.getOwnershipRange())
    rhs_top.getArray()[:] = np.asarray(
        [-0.4 + 0.2j, 0.7 - 0.1j, 1.2 + 0.3j, -0.3 - 0.2j][first:last],
        dtype=PETSc.ScalarType,
    )
    rhs = fixture["layout"].pack(
        rhs_bottom,
        rhs_top,
        np.asarray([0.3 + 0.1j, -0.2 + 0.4j, 0.5 - 0.2j, -0.1 + 0.3j]),
    )
    try:
        preconditioner = create_action_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            bottom,
            top,
        )
        rows = []
        result = solve_hybrid_block_ldu_iterative(
            operator,
            rhs,
            preconditioner,
            config=HybridBlockLduIterativeConfig(
                ksp_type=ksp_type,
                restart=restart,
                fixed_preconditioner=fixed_preconditioner,
            ),
            progress_callback=rows.append,
        )
        assert result.timing["restart"] == float(restart)
        assert result.timing["ksp_type"] == ksp_type
        assert result.postsolve_audit["restart"] == restart
        assert result.postsolve_audit["ksp_type"] == ksp_type
        assert result.converged_reason > 0
        assert result.timing["max_it"] == 1000.0
        assert result.timing["threshold"] == 5.0e-9
        assert result.history_evaluation_count == len(result.history)
        assert len({row["iteration"] for row in result.history}) == len(result.history)
        assert result.postsolve_evaluation_count == 1
        assert len(rows) == len(result.history)
        assert result.postsolve_audit["pass"] is True
        assert all(
            float(result.postsolve_audit[key]) <= 5.0e-9
            for key in (
                "reported_relative_residual",
                "global_true_relative_residual",
                "bottom_true_relative_residual",
                "top_true_relative_residual",
                "modal_true_relative_residual",
            )
        )
        assert result.release["ksp_destroyed"] is True
        assert result.release["pc_context_destroyed"] is True
        assert result.release["action_modal_schur_retained_after_pc_destroyed"] is True
        assert result.release["borrowed_side_actions_retained"] is True
        assert result.solution.getSize() == fixture["layout"].global_size
        result.release_deferred_action_modal_schur()
        assert result.release["action_modal_schur_released"] is True
        result.destroy()
        result = None
    finally:
        if result is not None:
            result.destroy()
        if preconditioner is not None and not preconditioner._destroyed:
            preconditioner.destroy()
        rhs.destroy()
        rhs_top.destroy()
        rhs_bottom.destroy()
        operator.destroy()
        operator_context.destroy()
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)
