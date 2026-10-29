from __future__ import annotations

from decimal import Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import lu_factor

from src.solvers import hcurl_assembly_time_condensation as hcurl
from src.solvers.p6_cell_condensed_action import P6CellCondensedAction
from src.runners import task41_p0_v4_volume_only_audit as saved_worker
from src.runners import task41_p0_v18_saved_jz_checker as independent_checker
from src.runners import task41_p0_v18_saved_jz as saved_jz_worker


def _decimal_sum_of_rounded_products(
    matrix: np.ndarray, vector: np.ndarray, row: int, *, imaginary: bool
) -> float:
    terms: list[Decimal] = []
    with localcontext() as context:
        context.prec = 100
        for column in range(vector.size):
            a = float(matrix[row, column].real)
            b = float(matrix[row, column].imag)
            x = float(vector[column].real)
            y = float(vector[column].imag)
            products = (a * y, b * x) if imaginary else (a * x, -(b * y))
            terms.extend(Decimal.from_float(product) for product in products)
        return float(sum(terms, Decimal(0)))


@pytest.mark.parametrize("order", ["C", "F"])
def test_jz_fsum_uses_all_binary64_products_and_keeps_inputs_readonly(order: str) -> None:
    matrix = np.array(
        [
            [1.0e16 + 0.0j, 1.0 + 0.0j, -1.0e16 + 0.0j],
            [0.0 + 1.0e16j, 0.0 + 1.0j, 0.0 - 1.0e16j],
            [2.0 + 3.0j, -4.0 + 5.0j, 1.0 - 2.0j],
        ],
        dtype=np.complex128,
        order=order,
    )
    vector = np.ones(3, dtype=np.complex128)
    matrix.setflags(write=False)
    vector.setflags(write=False)
    matrix_strides = matrix.strides
    vector_bytes = vector.tobytes()

    correction = hcurl.evaluate_same_lu_internal_rhs_correction(
        matrix,
        vector,
        strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
    )

    assert correction.dtype == np.dtype(np.complex128)
    assert correction.shape == (3,)
    assert correction[0] == -1.0 + 0.0j
    assert correction[1] == 0.0 - 1.0j
    np.testing.assert_array_equal(
        correction[2],
        complex(
            -_decimal_sum_of_rounded_products(matrix, vector, 2, imaginary=False),
            -_decimal_sum_of_rounded_products(matrix, vector, 2, imaginary=True),
        ),
    )
    assert matrix.strides == matrix_strides
    assert not matrix.flags.writeable
    assert not vector.flags.writeable
    assert vector.tobytes() == vector_bytes


def test_jz_fsum_is_nonconjugating_and_blas_remains_the_default() -> None:
    matrix = np.asarray([[2.0 + 3.0j]], dtype=np.complex128)
    vector = np.asarray([5.0 + 7.0j], dtype=np.complex128)
    expected = np.asarray([11.0 - 29.0j], dtype=np.complex128)

    candidate = hcurl.evaluate_same_lu_internal_rhs_correction(
        matrix,
        vector,
        strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
    )
    historical = hcurl.evaluate_same_lu_internal_rhs_correction(matrix, vector)

    np.testing.assert_array_equal(candidate, expected)
    np.testing.assert_array_equal(historical, -(matrix @ vector))


def test_jz_fsum_rejects_invalid_inputs_and_zero_rhs_does_not_bypass_j_validation() -> None:
    finite_matrix = np.ones((1, 2), dtype=np.complex128)
    finite_vector = np.ones(2, dtype=np.complex128)
    with pytest.raises(ValueError, match="dimensions do not agree"):
        hcurl.evaluate_same_lu_internal_rhs_correction(
            finite_matrix,
            finite_vector[:1],
            strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
        )
    nonfinite_matrix = finite_matrix.copy()
    nonfinite_matrix[0, 0] = np.nan + 0.0j
    with pytest.raises(ValueError, match="non-finite"):
        hcurl.evaluate_same_lu_internal_rhs_correction(
            nonfinite_matrix,
            finite_vector,
            strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
        )
    with pytest.raises(ValueError, match="unknown same-LU Jz evaluation strategy"):
        hcurl.evaluate_same_lu_internal_rhs_correction(
            finite_matrix, finite_vector, strategy="decimal"
        )
    with pytest.raises(ValueError, match="J contains non-finite values"):
        hcurl.project_internal_rhs_same_lu(
            (np.eye(2, dtype=np.complex128), np.asarray([0, 1], dtype=np.int32)),
            nonfinite_matrix,
            np.zeros(2, dtype=np.complex128),
            jz_evaluation_strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
        )


def test_project_same_lu_keeps_solved_vector_and_getrs_independent_of_jz_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = np.eye(3, dtype=np.complex128)
    trace_interior = np.asarray(
        [[1.0e16 + 0.0j, 1.0 + 0.0j, -1.0e16 + 0.0j]],
        dtype=np.complex128,
    )
    rhs = np.ones(3, dtype=np.complex128)
    factor = lu_factor(matrix)
    original_lu_solve = hcurl.lu_solve
    calls: list[int] = []

    def counted_lu_solve(*args: object, **kwargs: object) -> np.ndarray:
        calls.append(1)
        return original_lu_solve(*args, **kwargs)

    monkeypatch.setattr(hcurl, "lu_solve", counted_lu_solve)
    solved_blas, correction_blas, timing_blas = hcurl.project_internal_rhs_same_lu(
        factor, trace_interior, rhs
    )
    solved_fsum, correction_fsum, timing_fsum = hcurl.project_internal_rhs_same_lu(
        factor,
        trace_interior,
        rhs,
        jz_evaluation_strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
    )

    np.testing.assert_array_equal(solved_fsum, solved_blas)
    np.testing.assert_array_equal(correction_blas, -(trace_interior @ solved_blas))
    np.testing.assert_array_equal(correction_fsum, np.asarray([-1.0 + 0.0j]))
    assert calls == [1, 1]
    assert timing_blas["jz_evaluation_strategy"] == hcurl.JZ_EVALUATION_BLAS
    assert timing_fsum["jz_evaluation_strategy"] == hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM


def test_saved_jz_entry_uses_shared_helper_without_a_solver_backdoor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = np.asarray([[1.0e16 + 0.0j, 1.0 + 0.0j, -1.0e16 + 0.0j]])
    saved_z = np.ones(3, dtype=np.complex128)
    original_helper = hcurl.evaluate_same_lu_internal_rhs_correction
    helper_calls: list[str] = []

    def counted_helper(
        actual_trace_interior: np.ndarray,
        solved: np.ndarray,
        *,
        strategy: str = hcurl.JZ_EVALUATION_BLAS,
    ) -> np.ndarray:
        helper_calls.append(strategy)
        return original_helper(
            actual_trace_interior, solved, strategy=strategy
        )

    def forbidden_solver(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("saved-Jz candidate must not call GETRS")

    monkeypatch.setattr(
        hcurl, "evaluate_same_lu_internal_rhs_correction", counted_helper
    )
    monkeypatch.setattr(hcurl, "project_internal_rhs_same_lu", forbidden_solver)

    correction = saved_worker.task41_p0_v18_evaluate_saved_jz_candidate(
        matrix, saved_z
    )

    np.testing.assert_array_equal(correction, np.asarray([-1.0 + 0.0j]))
    assert helper_calls == [hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM]


def _cost_bucket() -> dict[str, float | int]:
    return {
        "getrs_count": 0,
        "getrs_seconds": 0.0,
        "initial_getrs_count": 0,
        "initial_getrs_seconds": 0.0,
        "correction_getrs_count": 0,
        "correction_getrs_seconds": 0.0,
        "refinement_steps": 0,
        "residual_evaluation_count": 0,
        "residual_seconds": 0.0,
        "update_seconds": 0.0,
        "j_matvec_seconds": 0.0,
        "core_seconds": 0.0,
        "port_D_seconds": 0.0,
        "mpc_scatter_seconds": 0.0,
    }


def _p6_action_for_saved_rhs(
    *, strategy: str, cells: list[SimpleNamespace], trace_coefficient: complex = 1.0 + 0.0j
) -> P6CellCondensedAction:
    action = object.__new__(P6CellCondensedAction)
    constraints = SimpleNamespace(
        owned_active_original_dofs=(6,),
        original_to_active={6: 0},
        expansion_by_original={
            6: (np.asarray([0], dtype=np.int64), np.asarray([trace_coefficient], dtype=np.complex128))
        },
    )
    action.condensed = SimpleNamespace(
        comm=SimpleNamespace(Get_size=lambda: 1),
        full_rows=7,
        active_rows=1,
        appended_rows=1,
        owned_trace_original_dofs=(6,),
        trace_constraints=constraints,
    )
    action.internal_rhs_strategy = "same_lu_rhs_solve"
    action.jz_evaluation_strategy = strategy
    action.internal_rhs_refinement_max_steps = 0
    action._same_lu_rhs_costs = {"actual_rhs": _cost_bucket()}
    action._same_lu_rhs_solve_count = 0
    action._audit = {}
    action._cells = cells
    return action


def test_p6_candidate_changes_only_full_correction_and_di_reuses_same_solved_vector() -> None:
    identity = np.eye(3, dtype=np.complex128)
    first_rhs = np.ones(3, dtype=np.complex128)
    first_j = np.asarray([[1.0e16 + 0.0j, 0.0j, 0.0j]], dtype=np.complex128)
    second_k = np.eye(1, dtype=np.complex128)
    second_rhs = np.ones(1, dtype=np.complex128)
    second_j = np.asarray([[-1.0 + 0.0j]], dtype=np.complex128)
    first = SimpleNamespace(
        original_interiors=np.asarray([0, 1, 2], dtype=np.int64),
        original_trace=np.asarray([6], dtype=np.int64),
        ports=np.asarray([0], dtype=np.int64),
        interior_lu=lu_factor(identity),
        trace_interior=first_j,
        actual_internal_matrix=None,
        actual_internal_matrix_identity=None,
        factor_matrix_identity=None,
        Di=np.asarray([[2.0 + 1.0j, 3.0, 4.0]], dtype=np.complex128),
        generated_action=None,
    )
    second = SimpleNamespace(
        original_interiors=np.asarray([3], dtype=np.int64),
        original_trace=np.asarray([6], dtype=np.int64),
        ports=np.asarray([], dtype=np.int64),
        interior_lu=lu_factor(second_k),
        trace_interior=second_j,
        actual_internal_matrix=None,
        actual_internal_matrix_identity=None,
        factor_matrix_identity=None,
        Di=np.empty((0, 1), dtype=np.complex128),
        generated_action=None,
    )
    trace_coefficient = 0.6 + 0.8j
    action = _p6_action_for_saved_rhs(
        strategy=hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM,
        cells=[first, second],
        trace_coefficient=trace_coefficient,
    )

    reduced = action.reduce_rhs(np.asarray([1, 1, 1, 1, 0, 0, 1.0e16], dtype=np.complex128))

    # Native trace then cell corrections in production order: 1e16 - 1e16 + 1.
    assert reduced[0] == np.conjugate(trace_coefficient)
    # The nontrivial complex MPC coefficient is conjugated by the P6 reducer.
    # Di consumes exactly the vector returned by the same single GETRS path.
    assert reduced[1] == 9.0 + 1.0j
    assert action._same_lu_rhs_solve_count == 2
    assert action.jz_evaluation_strategy == hcurl.JZ_EVALUATION_BINARY64_REAL_IMAG_FSUM


def test_independent_checker_rejects_tiny_imaginary_corruption_hidden_by_real_ulp() -> None:
    matrix = np.zeros((432, 450), dtype=np.complex128)
    matrix[0, 0] = 1.0e16 + 1.0e-20j
    vector = np.zeros(450, dtype=np.complex128)
    vector[0] = 1.0 + 0.0j
    baseline = -(matrix @ vector)
    corrupted = baseline.copy()
    corrupted[0] = -1.0e16 - 1.0e-12j

    measured = independent_checker._measure_vector(
        matrix, vector, corrupted, baseline, {0}
    )

    assert not measured["candidate_within_one_ulp_of_rounded_decimal_reference"]
    row = measured["all_432_real_imag_component_errors"][0]
    assert row["candidate_rounded_component_within_one_ulp"] == [True, False]
    reference_real, reference_imag = independent_checker._decimal_jz_row(
        matrix, vector, 0, precision=80
    )[:2]
    real_ulp = Decimal.from_float(float(np.spacing(corrupted[0].real)))
    imag_ulp = Decimal.from_float(float(np.spacing(corrupted[0].imag)))
    assert abs(Decimal.from_float(float(corrupted[0].real)) - reference_real) <= abs(real_ulp)
    assert abs(Decimal.from_float(float(corrupted[0].imag)) - reference_imag) > abs(imag_ulp)


def test_v18_scatter_adds_each_trace_contribution_to_existing_accumulator() -> None:
    operation = {
        "target_position": 0,
        "data": np.asarray([1.0 + 0.0j, 1.0 + 0.0j], dtype=np.complex128),
        "indices": np.asarray([0, 0], dtype=np.int64),
        "indptr": np.asarray([0, 1, 2], dtype=np.int64),
    }
    values = np.asarray([-1.0e16 + 0.0j, 1.0 + 0.0j], dtype=np.complex128)

    result = saved_jz_worker._scatter_target(1.0e16 + 0.0j, operation, values)

    assert result == 1.0 + 0.0j
