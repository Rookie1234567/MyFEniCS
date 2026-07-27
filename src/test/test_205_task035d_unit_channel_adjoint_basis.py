from __future__ import annotations

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.dtn_goal_adjoint import (
    DtnChannelGoal,
    evaluate_actual_dtn_unit_channel_adjoint_basis,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    return np.concatenate(
        vector.comm.tompi4py().allgather(
            np.asarray(
                vector.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
        )
    )


def _nonhermitian_augmented_system(size: int) -> np.ndarray:
    rows = np.arange(size, dtype=np.float64)
    matrix = np.diag(
        4.0 + 0.01 * rows + 0.08j * np.sin(0.07 * rows)
    ).astype(np.complex128)
    matrix[np.arange(size - 1), np.arange(1, size)] = 0.07 - 0.02j
    matrix[np.arange(1, size), np.arange(size - 1)] = -0.03 + 0.04j
    matrix[0, -1] = 0.015j
    matrix[-1, 0] = -0.02 + 0.005j
    return matrix


def _petsc_system(
    dense: np.ndarray,
) -> tuple[PETSc.Mat, PETSc.Vec, PETSc.Vec, PETSc.KSP]:
    comm = MPI.COMM_WORLD
    size = len(dense)
    matrix = PETSc.Mat().createAIJ(size=(size, size), comm=comm)
    matrix.setUp()
    start, stop = matrix.getOwnershipRange()
    columns = np.arange(size, dtype=PETSc.IntType)
    for row in range(start, stop):
        nonzero = np.flatnonzero(np.abs(dense[row]) > 0.0)
        matrix.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            columns[nonzero],
            dense[row, nonzero].reshape((1, len(nonzero))),
        )
    matrix.assemble()
    right_hand_side = PETSc.Vec().createMPI(size, comm=comm)
    owned_start, owned_stop = right_hand_side.getOwnershipRange()
    owned_rows = np.arange(owned_start, owned_stop, dtype=np.float64)
    right_hand_side.getArray()[:] = (
        np.sin(0.11 * (owned_rows + 1.0))
        + 0.3j * np.cos(0.09 * (owned_rows + 1.0))
    )
    right_hand_side.assemble()
    solver = PETSc.KSP().create(comm)
    solver.setType(PETSc.KSP.Type.PREONLY)
    solver.getPC().setType(PETSc.PC.Type.LU)
    solver.getPC().setFactorSolverType("mumps")
    solver.setOperators(matrix)
    solver.setErrorIfNotConverged(True)
    state = right_hand_side.duplicate()
    solver.solve(right_hand_side, state)
    assert solver.getConvergedReason() > 0
    return matrix, right_hand_side, state, solver


def test_36_real_goals_use_12_unit_channel_backsolves() -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip("Task035d unit channel basis qualifies serial/MPI2/MPI8")
    config = target_stage4_config(degree=2, h_nm=50.0)
    modes = outgoing_port_modes_3d(config)
    n_fe = 2
    dense = _nonhermitian_augmented_system(n_fe + len(modes))
    matrix, rhs, state, solver = _petsc_system(dense)
    captured: dict[tuple[str, int, int, str], np.ndarray] = {}
    try:
        state_values = _global_values(state)
        goal_context = {
            "num_fem_dofs_after_mpc": n_fe,
            "modes": modes,
            "auxiliary_values": state_values[n_fe:].copy(),
            "incident_projections": np.zeros(
                len(modes),
                dtype=np.complex128,
            ),
            "normalization": (
                "finite-port outgoing modal power / incident power"
            ),
        }
        channels = tuple(
            (side, m)
            for side in ("bottom", "top")
            for m in (-7, -5, -4, -2, -1, 0)
        )
        goals = tuple(
            DtnChannelGoal(side, m, 0, "s", quantity)
            for side, m in channels
            for quantity in (
                "power",
                "amplitude_real",
                "amplitude_imag",
            )
        )

        def capture(
            identity: dict[str, object],
            unit_adjoint: PETSc.Vec,
        ) -> None:
            key = (
                str(identity["side"]),
                int(identity["m"]),
                int(identity["n"]),
                str(identity["polarization"]),
            )
            captured[key] = _global_values(unit_adjoint)

        report = evaluate_actual_dtn_unit_channel_adjoint_basis(
            linear_system={
                "A": matrix,
                "b": rhs,
                "x": state,
                "ksp": solver,
            },
            dtn_result={"goal_context": goal_context},
            config=config,
            communicator=MPI.COMM_WORLD,
            goals=goals,
            unit_adjoint_observer=capture,
        )
        assert report["pass"] is True
        assert report["requested_real_goal_count"] == 36
        assert report["independent_power_goal_count"] == 12
        assert (
            report[
                "independent_complex_amplitude_component_goal_count"
            ]
            == 24
        )
        assert report["complete_complex_amplitude_channel_count"] == 12
        assert report["physical_channel_count"] == 12
        assert report["unit_adjoint_solve_count"] == 12
        assert report["uncompressed_adjoint_solve_count"] == 36
        assert report["factor_backsolve_reduction_fraction"] == pytest.approx(
            2.0 / 3.0
        )
        assert report["unit_gradient_coefficient_matrix_rank"] == 12
        assert report["expected_unit_gradient_span_rank"] == 12
        assert report["per_goal_scaled_adjoint_residual_checked"] is True
        assert report["per_goal_finite_difference_verification"] is False
        assert len(captured) == 12

        for key, observed in captured.items():
            side, m, n, polarization = key
            mode_index = next(
                index
                for index, mode in enumerate(modes)
                if (
                    mode.side == side
                    and int(mode.m) == m
                    and int(mode.n) == n
                    and mode.polarization == polarization
                )
            )
            unit = np.zeros(len(dense), dtype=np.complex128)
            unit[n_fe + mode_index] = 1.0
            expected = np.linalg.solve(dense.conj().T, unit)
            np.testing.assert_allclose(
                observed,
                expected,
                rtol=2.0e-12,
                atol=2.0e-12,
            )
        for goal in goals:
            goal_report = report["goals"][goal.label]
            assert goal_report["pass"] is True
            assert (
                goal_report["independent_factor_backsolve_performed"]
                is False
            )
            assert goal_report["recovered_from_unit_channel_adjoint"] is True
            assert (
                goal_report["gradient_scaling_relative_error"]
                <= 5.0e-13
            )
            assert (
                goal_report["scaled_adjoint_residual"][
                    "relative_residual"
                ]
                <= 1.0e-12
            )
    finally:
        state.destroy()
        solver.destroy()
        rhs.destroy()
        matrix.destroy()


def test_unit_channel_basis_fails_without_live_factor_objects() -> None:
    config = target_stage4_config(degree=2, h_nm=50.0)
    goal = DtnChannelGoal("top", -2, 0, "s", "power")
    with pytest.raises(RuntimeError, match="live matrix/state"):
        evaluate_actual_dtn_unit_channel_adjoint_basis(
            linear_system={"A": None, "x": None, "ksp": None},
            dtn_result={
                "goal_context": {
                    "normalization": "fixture",
                }
            },
            config=config,
            communicator=MPI.COMM_WORLD,
            goals=(goal,),
        )
