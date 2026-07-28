from __future__ import annotations

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.dtn_goal_adjoint import (
    DtnChannelGoal,
    dtn_channel_goal_value,
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
        mode_indices = np.arange(len(modes), dtype=np.float64)
        coordinate_scales = (
            1.15
            + 0.003 * mode_indices
            + 1j * (0.11 + 0.002 * mode_indices)
        ).astype(np.complex128)
        solver_auxiliary_values = state_values[n_fe:].copy()
        physical_auxiliary_values = (
            solver_auxiliary_values / coordinate_scales
        )
        incident_projections = np.zeros(
            len(modes),
            dtype=np.complex128,
        )
        for mode_index, mode in enumerate(modes):
            if mode.side == "top":
                incident_projections[mode_index] = (
                    0.04 * np.cos(0.13 * (mode_index + 1.0))
                    + 0.03j * np.sin(0.17 * (mode_index + 1.0))
                )
        goal_context = {
            "num_fem_dofs_after_mpc": n_fe,
            "modes": modes,
            "auxiliary_values": physical_auxiliary_values,
            "auxiliary_coordinate_scales": coordinate_scales,
            "incident_projections": incident_projections,
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
        assert report["complex_linear_backsolve_basis_rank"] == 12
        assert (
            report["expected_complex_linear_backsolve_basis_rank"]
            == 12
        )
        assert report["real_functional_gradient_span_rank"] == 24
        assert (
            report[
                "expected_real_functional_gradient_span_rank"
            ]
            == 24
        )
        assert report["per_goal_scaled_adjoint_residual_checked"] is True
        assert report["per_goal_finite_difference_verification"] is False
        assert report["selected_goal_set_complete"] is False
        assert (
            report["goal_set_completeness_must_be_asserted_by_caller"]
            is True
        )
        assert report["fem_field_gather"] is False
        assert (
            report[
                "full_adjoint_vector_gather_to_root_for_content_identity"
            ]
            is True
        )
        assert (
            report["full_adjoint_vector_gather_bytes_global"]
            == len(dense) * np.dtype(np.complex128).itemsize
        )
        assert report["auxiliary_scalar_gather_only"] is False
        assert (
            report["unit_adjoint_observer_vector_lifetime"]
            == "callback_only_borrowed_vector"
        )
        assert (
            report[
                "scaled_goal_adjoint_observer_vector_lifetime"
            ]
            == "callback_only_borrowed_vector"
        )
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
            mode_index = int(goal_report["auxiliary_mode_index"])
            direction = complex(
                0.31 + 0.002 * mode_index,
                -0.27 + 0.001 * mode_index,
            )
            step = 1.0e-6
            solver_minus = solver_auxiliary_values.copy()
            solver_plus = solver_auxiliary_values.copy()
            solver_minus[mode_index] -= step * direction
            solver_plus[mode_index] += step * direction
            goal_minus = dtn_channel_goal_value(
                config,
                modes,
                solver_minus / coordinate_scales,
                incident_projections,
                goal=goal,
            )
            goal_plus = dtn_channel_goal_value(
                config,
                modes,
                solver_plus / coordinate_scales,
                incident_projections,
                goal=goal,
            )
            finite_difference = (goal_plus - goal_minus) / (2.0 * step)
            pair = goal_report[
                "gradient_scalar_solver_coordinate"
            ]
            scalar = complex(float(pair[0]), float(pair[1]))
            expected_directional_derivative = float(
                np.real(np.conj(scalar) * direction)
            )
            assert finite_difference == pytest.approx(
                expected_directional_derivative,
                rel=2.0e-8,
                abs=2.0e-10,
            )
            assert goal_report["goal_value"] == pytest.approx(
                dtn_channel_goal_value(
                    config,
                    modes,
                    physical_auxiliary_values,
                    incident_projections,
                    goal=goal,
                ),
                rel=2.0e-13,
                abs=2.0e-13,
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
