from __future__ import annotations

import unittest

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.adaptivity.missing_p6_trace_sensitivity import (
    MissingTraceResidualDiagnostic,
    REVIEW_V1_MISSING_TRACE_GOAL_LABELS,
    build_missing_p6_trace_complement,
    split_enriched_local_operator,
)


def _distributed_matrix(
    comm: MPI.Intracomm,
    values: np.ndarray,
) -> PETSc.Mat:
    dense = np.asarray(values, dtype=np.complex128)
    matrix = PETSc.Mat().createAIJ(
        size=dense.shape,
        nnz=dense.shape[1],
        comm=comm,
    )
    start, stop = map(int, matrix.getOwnershipRange())
    columns = np.arange(dense.shape[1], dtype=PETSc.IntType)
    for row in range(start, stop):
        matrix.setValues(
            [row],
            columns,
            np.asarray(
                dense[row : row + 1, :],
                dtype=PETSc.ScalarType,
            ),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    matrix.assemble()
    return matrix


def _distributed_vector(
    matrix: PETSc.Mat,
    values: np.ndarray,
    *,
    side: str,
) -> PETSc.Vec:
    if side == "left":
        vector = matrix.createVecLeft()
    elif side == "right":
        vector = matrix.createVecRight()
    else:
        raise ValueError(side)
    start, stop = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(
        values[start:stop],
        dtype=PETSc.ScalarType,
    )
    vector.assemble()
    return vector


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    packets = comm.allgather(
        np.asarray(
            vector.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
    )
    return np.concatenate(packets)


def _algebraic_problem(comm: MPI.Intracomm):
    retained_rows = 5
    missing_rows = 7
    row_h = np.arange(missing_rows, dtype=np.float64)[:, None]
    col_l = np.arange(retained_rows, dtype=np.float64)[None, :]
    missing_from_retained_dense = (
        0.5
        + 0.07 * row_h
        - 0.11 * col_l
        + 1j * (0.03 + 0.05 * row_h + 0.02 * col_l)
    )
    row_l = np.arange(retained_rows, dtype=np.float64)[:, None]
    col_h = np.arange(missing_rows, dtype=np.float64)[None, :]
    retained_from_missing_dense = (
        -0.2
        + 0.13 * row_l
        + 0.04 * col_h
        + 1j * (0.09 - 0.015 * row_l + 0.025 * col_h)
    )
    state_values = (
        np.linspace(0.2, 1.0, retained_rows)
        + 1j * np.linspace(-0.3, 0.25, retained_rows)
    )
    rhs_values = (
        np.linspace(-0.4, 0.8, missing_rows)
        + 1j * np.linspace(0.35, -0.15, missing_rows)
    )
    missing_from_retained = _distributed_matrix(
        comm,
        missing_from_retained_dense,
    )
    retained_from_missing = _distributed_matrix(
        comm,
        retained_from_missing_dense,
    )
    state = _distributed_vector(
        missing_from_retained,
        state_values,
        side="right",
    )
    rhs = _distributed_vector(
        missing_from_retained,
        rhs_values,
        side="left",
    )
    return {
        "missing_from_retained": missing_from_retained,
        "retained_from_missing": retained_from_missing,
        "state": state,
        "rhs": rhs,
        "missing_from_retained_dense": missing_from_retained_dense,
        "retained_from_missing_dense": retained_from_missing_dense,
        "state_values": state_values,
        "rhs_values": rhs_values,
    }


def _destroy_problem(problem) -> None:
    problem["rhs"].destroy()
    problem["state"].destroy()
    problem["retained_from_missing"].destroy()
    problem["missing_from_retained"].destroy()


class TestTask035bMissingP6TraceSensitivity(unittest.TestCase):
    def test_reference_complement_closes_p5_trace_plus_p6_interior(
        self,
    ) -> None:
        complement = build_missing_p6_trace_complement()
        audit = complement.audit
        self.assertTrue(audit["pass"])
        self.assertEqual(complement.retained_dimension, 750)
        self.assertEqual(complement.enriched_dimension, 882)
        self.assertEqual(complement.missing_dimension, 132)
        self.assertEqual(
            audit["missing_edge_modes_per_entity"],
            (1,) * 12,
        )
        self.assertEqual(
            audit["missing_face_modes_per_entity"],
            (20,) * 6,
        )
        self.assertEqual(audit["direct_sum_rank"], 882)
        self.assertLess(
            audit["entity_orientation_equivariance_error_max"],
            2.0e-11,
        )
        self.assertLess(
            audit["missing_orientation_invariance_error_max"],
            2.0e-11,
        )
        self.assertLess(
            audit["missing_induced_unitarity_error_max"],
            2.0e-11,
        )
        self.assertFalse(audit["candidate_matrix_constructed"])
        self.assertFalse(
            audit["inactive_p6_rows_retained_in_candidate_matrix"]
        )
        self.assertFalse(audit["actual_dwr_indicator"])
        self.assertFalse(audit["lane_b_formal_selection_authorized"])

        rng = np.random.default_rng(2026072501)
        tensor = (
            rng.standard_normal((9, 9))
            + 1j * rng.standard_normal((9, 9))
        )
        retained = rng.standard_normal((9, 5))
        missing = rng.standard_normal((9, 4))
        split = split_enriched_local_operator(
            tensor,
            retained,
            missing,
        )
        change = np.concatenate(
            (retained, missing),
            axis=1,
        ).astype(np.complex128)
        transformed = change.conj().T @ tensor @ change
        np.testing.assert_allclose(
            split["retained_retained"],
            transformed[:5, :5],
            rtol=2.0e-13,
            atol=2.0e-11,
        )
        np.testing.assert_allclose(
            split["retained_missing"],
            transformed[:5, 5:],
            rtol=2.0e-13,
            atol=2.0e-11,
        )
        np.testing.assert_allclose(
            split["missing_retained"],
            transformed[5:, :5],
            rtol=2.0e-13,
            atol=2.0e-11,
        )
        np.testing.assert_allclose(
            split["missing_missing"],
            transformed[5:, 5:],
            rtol=2.0e-13,
            atol=2.0e-11,
        )

    def test_serial_actual_residuals_are_exact_and_proxy_is_not_dwr(
        self,
    ) -> None:
        problem = _algebraic_problem(MPI.COMM_SELF)
        observed: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        try:
            with MissingTraceResidualDiagnostic(
                missing_from_retained=problem[
                    "missing_from_retained"
                ],
                retained_from_missing=problem[
                    "retained_from_missing"
                ],
                retained_state=problem["state"],
                missing_right_hand_side=problem["rhs"],
            ) as diagnostic:
                expected_primal = (
                    problem["rhs_values"]
                    - problem["missing_from_retained_dense"]
                    @ problem["state_values"]
                )
                np.testing.assert_allclose(
                    _global_values(diagnostic.primal_residual),
                    expected_primal,
                    rtol=2.0e-14,
                    atol=2.0e-14,
                )
                for goal_index, label in enumerate(
                    REVIEW_V1_MISSING_TRACE_GOAL_LABELS
                ):
                    retained_adjoint_values = (
                        (goal_index + 1)
                        * np.linspace(0.03, 0.11, 5)
                        + 1j
                        * np.linspace(-0.07, 0.05, 5)
                    )
                    missing_gradient_values = (
                        np.zeros(7, dtype=np.complex128)
                        if goal_index % 2 == 0
                        else (
                            0.01 * np.arange(7)
                            + 1j * 0.005 * np.arange(7)[::-1]
                        )
                    )
                    retained_adjoint = _distributed_vector(
                        problem["retained_from_missing"],
                        retained_adjoint_values,
                        side="left",
                    )
                    missing_gradient = _distributed_vector(
                        problem["retained_from_missing"],
                        missing_gradient_values,
                        side="right",
                    )

                    def observer(
                        primal,
                        adjoint,
                        _metadata,
                        selected_label=label,
                    ):
                        observed[selected_label] = (
                            _global_values(primal),
                            _global_values(adjoint),
                        )

                    report = diagnostic.evaluate_adjoint(
                        label=label,
                        retained_adjoint=retained_adjoint,
                        reference_band=0.25 + goal_index,
                        missing_goal_gradient=missing_gradient,
                        residual_observer=observer,
                    )
                    expected_adjoint = (
                        missing_gradient_values
                        - problem[
                            "retained_from_missing_dense"
                        ].conj().T
                        @ retained_adjoint_values
                    )
                    np.testing.assert_allclose(
                        observed[label][0],
                        expected_primal,
                        rtol=2.0e-14,
                        atol=2.0e-14,
                    )
                    np.testing.assert_allclose(
                        observed[label][1],
                        expected_adjoint,
                        rtol=2.0e-14,
                        atol=2.0e-14,
                    )
                    expected_product = (
                        np.conj(expected_adjoint) * expected_primal
                    )
                    self.assertAlmostEqual(
                        report["paired_residual_l1"],
                        float(np.sum(np.abs(expected_product))),
                        places=12,
                    )
                    self.assertAlmostEqual(
                        report[
                            "rotation_invariant_paired_inner_product_abs"
                        ],
                        float(abs(np.sum(expected_product))),
                        places=12,
                    )
                    self.assertFalse(
                        report[
                            "coordinatewise_missing_mode_ranking_authorized"
                        ]
                    )
                    self.assertFalse(report["actual_dwr_indicator"])
                    self.assertFalse(
                        report["lane_b_formal_selection_authorized"]
                    )
                    self.assertFalse(report["candidate_matrix_constructed"])
                    self.assertFalse(
                        report[
                            "inactive_p6_rows_retained_in_candidate_matrix"
                        ]
                    )
                    missing_gradient.destroy()
                    retained_adjoint.destroy()

                final = diagnostic.finalize()
                self.assertEqual(final["goal_count"], 16)
                self.assertEqual(
                    final["expected_goal_labels"],
                    list(REVIEW_V1_MISSING_TRACE_GOAL_LABELS),
                )
                self.assertFalse(final["actual_dwr_indicator"])
                self.assertFalse(
                    final["lane_b_formal_selection_authorized"]
                )
                self.assertFalse(final["candidate_matrix_constructed"])
        finally:
            _destroy_problem(problem)

    def test_fail_closed_goal_contract(self) -> None:
        problem = _algebraic_problem(MPI.COMM_SELF)
        try:
            with MissingTraceResidualDiagnostic(
                missing_from_retained=problem[
                    "missing_from_retained"
                ],
                retained_from_missing=problem[
                    "retained_from_missing"
                ],
                retained_state=problem["state"],
                missing_right_hand_side=problem["rhs"],
            ) as diagnostic:
                adjoint = _distributed_vector(
                    problem["retained_from_missing"],
                    np.ones(5, dtype=np.complex128),
                    side="left",
                )
                diagnostic.evaluate_adjoint(
                    label="one",
                    retained_adjoint=adjoint,
                    reference_band=1.0,
                )
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    diagnostic.evaluate_adjoint(
                        label="one",
                        retained_adjoint=adjoint,
                        reference_band=1.0,
                    )
                with self.assertRaisesRegex(RuntimeError, "labels do not close"):
                    diagnostic.finalize()
                with self.assertRaisesRegex(ValueError, "positive"):
                    diagnostic.evaluate_adjoint(
                        label="two",
                        retained_adjoint=adjoint,
                        reference_band=0.0,
                    )
                invalid = _distributed_vector(
                    problem["retained_from_missing"],
                    np.asarray(
                        [np.nan, 1.0, 1.0, 1.0, 1.0],
                        dtype=np.complex128,
                    ),
                    side="left",
                )
                with self.assertRaisesRegex(
                    FloatingPointError,
                    "NaN or Inf",
                ):
                    diagnostic.evaluate_adjoint(
                        label="nonfinite",
                        retained_adjoint=invalid,
                        reference_band=1.0,
                    )
                invalid.destroy()
                adjoint.destroy()
        finally:
            _destroy_problem(problem)

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 missing-trace residual identity check",
    )
    def test_mpi2_residual_and_adjoint_identity(self) -> None:
        comm = MPI.COMM_WORLD
        problem = _algebraic_problem(comm)
        try:
            with MissingTraceResidualDiagnostic(
                missing_from_retained=problem[
                    "missing_from_retained"
                ],
                retained_from_missing=problem[
                    "retained_from_missing"
                ],
                retained_state=problem["state"],
                missing_right_hand_side=problem["rhs"],
            ) as diagnostic:
                expected_primal = (
                    problem["rhs_values"]
                    - problem["missing_from_retained_dense"]
                    @ problem["state_values"]
                )
                np.testing.assert_allclose(
                    _global_values(diagnostic.primal_residual),
                    expected_primal,
                    rtol=2.0e-14,
                    atol=2.0e-14,
                )
                for goal_index, label in enumerate(
                    REVIEW_V1_MISSING_TRACE_GOAL_LABELS
                ):
                    retained_values = (
                        np.linspace(0.02, 0.14, 5)
                        * (goal_index + 1)
                        + 1j * np.linspace(0.04, -0.06, 5)
                    )
                    adjoint = _distributed_vector(
                        problem["retained_from_missing"],
                        retained_values,
                        side="left",
                    )
                    captured: list[np.ndarray] = []
                    report = diagnostic.evaluate_adjoint(
                        label=label,
                        retained_adjoint=adjoint,
                        reference_band=1.0 + goal_index,
                        residual_observer=lambda _primal, residual, _meta: (
                            captured.append(_global_values(residual))
                        ),
                    )
                    expected_adjoint = (
                        -problem["retained_from_missing_dense"].conj().T
                        @ retained_values
                    )
                    np.testing.assert_allclose(
                        captured[0],
                        expected_adjoint,
                        rtol=3.0e-14,
                        atol=3.0e-14,
                    )
                    reports = comm.allgather(report)
                    self.assertTrue(
                        all(candidate == reports[0] for candidate in reports)
                    )
                    adjoint.destroy()
                final = diagnostic.finalize()
                finals = comm.allgather(final)
                self.assertTrue(
                    all(candidate == finals[0] for candidate in finals)
                )
                self.assertFalse(final["actual_dwr_indicator"])
                self.assertFalse(
                    final["lane_b_formal_selection_authorized"]
                )
        finally:
            _destroy_problem(problem)

    def test_finalize_rechecks_mutable_primal_residual_and_exact_labels(
        self,
    ) -> None:
        problem = _algebraic_problem(MPI.COMM_SELF)
        try:
            with MissingTraceResidualDiagnostic(
                missing_from_retained=problem[
                    "missing_from_retained"
                ],
                retained_from_missing=problem[
                    "retained_from_missing"
                ],
                retained_state=problem["state"],
                missing_right_hand_side=problem["rhs"],
            ) as diagnostic:
                adjoint = _distributed_vector(
                    problem["retained_from_missing"],
                    np.ones(5, dtype=np.complex128),
                    side="left",
                )
                try:
                    for index in range(16):
                        diagnostic.evaluate_adjoint(
                            label=f"wrong_goal_{index:02d}",
                            retained_adjoint=adjoint,
                            reference_band=1.0,
                        )
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "labels do not close",
                    ):
                        diagnostic.finalize()
                finally:
                    adjoint.destroy()

            with MissingTraceResidualDiagnostic(
                missing_from_retained=problem[
                    "missing_from_retained"
                ],
                retained_from_missing=problem[
                    "retained_from_missing"
                ],
                retained_state=problem["state"],
                missing_right_hand_side=problem["rhs"],
            ) as diagnostic:
                adjoint = _distributed_vector(
                    problem["retained_from_missing"],
                    np.ones(5, dtype=np.complex128),
                    side="left",
                )
                try:
                    for label in REVIEW_V1_MISSING_TRACE_GOAL_LABELS:
                        diagnostic.evaluate_adjoint(
                            label=label,
                            retained_adjoint=adjoint,
                            reference_band=1.0,
                        )
                    diagnostic.primal_residual.getArray()[0] = np.nan
                    with self.assertRaisesRegex(
                        FloatingPointError,
                        "NaN or Inf at finalize",
                    ):
                        diagnostic.finalize()
                finally:
                    adjoint.destroy()
        finally:
            _destroy_problem(problem)


if __name__ == "__main__":
    unittest.main()
