from __future__ import annotations

import numpy as np

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    apply_active_dof_transformation,
    build_variable_p_reference_space,
)
from src.solvers.hcurl_p4_core_partial_condensation import (
    condense_p6_local_to_p4_core,
)


_NONZERO_CELL_INFO = (
    1 | (2 << 1) | (1 << (3 * 3 + 1)) | (1 << (18 + 1)) | (1 << (18 + 9))
)


def _relative(observed: np.ndarray, reference: np.ndarray) -> float:
    scale = max(float(np.linalg.norm(reference)), 1.0e-30)
    return float(np.linalg.norm(observed - reference) / scale)


def _reference_tensor_and_rhs() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(242037)
    lower = np.tril(
        rng.standard_normal((882, 882)) + 1j * rng.standard_normal((882, 882)),
        k=-1,
    )
    upper = np.triu(
        rng.standard_normal((882, 882)) + 1j * rng.standard_normal((882, 882)),
        k=1,
    )
    diagonal = 8.0 + 0.013j * np.arange(882, dtype=np.float64)
    tensor = np.diag(diagonal) + 0.002 * lower + (0.001 + 0.001j) * upper
    rhs = 0.2 * np.sin(0.017 * np.arange(882)) + 1j * 0.15 * np.cos(
        0.023 * (np.arange(882) + 1)
    )
    return np.ascontiguousarray(tensor), np.ascontiguousarray(rhs)


def _oriented_interior_embedding(source, p6, cell_info: int) -> np.ndarray:
    interior = np.asarray(source.interior_dofs, dtype=np.int32)
    columns = np.zeros(
        (source.hcurl_dimension, interior.size),
        dtype=np.float64,
    )
    columns[interior, np.arange(interior.size)] = 1.0
    reference_columns = source.apply_hcurl_dof_transform(
        columns,
        cell_info=cell_info,
        transpose=True,
    )
    expanded = source.hcurl_to_p6 @ reference_columns
    return np.ascontiguousarray(
        apply_active_dof_transformation(
            p6,
            expanded,
            family="hcurl",
            cell_info=cell_info,
        )
    )


def _independent_basis(p4, p5, p6, cell_info: int):
    e4 = _oriented_interior_embedding(p4, p6, cell_info)
    e5 = _oriented_interior_embedding(p5, p6, cell_info)
    trace = np.asarray(p6.trace_dofs, dtype=np.int32)
    interior = np.asarray(p6.interior_dofs, dtype=np.int32)
    e4_int = e4[interior]
    e5_int = e5[interior]
    q4, singular4, _ = np.linalg.svd(e4_int, full_matrices=False)
    q5_full, singular5, _ = np.linalg.svd(e5_int, full_matrices=False)
    q4 = q4[:, :108]
    q5_full = q5_full[:, :240]
    nested = _relative(
        q5_full @ (q5_full.conj().T @ e4_int),
        e4_int,
    )
    e5_perp = e5_int - q4 @ (q4.conj().T @ e5_int)
    q5, singular_increment, _ = np.linalg.svd(
        e5_perp,
        full_matrices=False,
    )
    q5 = q5[:, :132]
    q45 = np.column_stack((q4, q5))
    q_complete, _ = np.linalg.qr(q45, mode="complete")
    q6 = q_complete[:, 240:]
    q = np.column_stack((q4, q5, q6))
    return {
        "trace": trace,
        "interior": interior,
        "q4": q4,
        "q": q,
        "p4_rank": int(np.count_nonzero(singular4 > 1.0e-12 * singular4[0])),
        "p5_rank": int(np.count_nonzero(singular5 > 1.0e-12 * singular5[0])),
        "p5_increment_rank": int(
            np.count_nonzero(singular_increment > 1.0e-12 * singular_increment[0])
        ),
        "nested_error": nested,
        "trace_leakage": float(
            max(
                np.max(np.abs(e4[trace]), initial=0.0),
                np.max(np.abs(e5[trace]), initial=0.0),
            )
        ),
        "orthogonality_error": float(
            np.max(
                np.abs(q.conj().T @ q - np.eye(450)),
                initial=0.0,
            )
        ),
    }


def _basis_matrix(trace: np.ndarray, interior: np.ndarray, q: np.ndarray):
    basis = np.zeros((882, 882), dtype=np.complex128)
    basis[np.ix_(trace, np.arange(trace.size))] = np.eye(trace.size)
    basis[np.ix_(interior, np.arange(trace.size, 882))] = q
    return basis


def test_p4_core_partial_condensation_local_oracles():
    p4 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(4))
    p5 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(5))
    p6 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(6))
    tensor_reference, rhs_reference = _reference_tensor_and_rhs()
    assert np.max(np.abs(tensor_reference - tensor_reference.conj().T)) > 1.0e-8

    for cell_info in (0, _NONZERO_CELL_INFO):
        independent = _independent_basis(p4, p5, p6, cell_info)
        assert independent["p4_rank"] == 108
        assert independent["p5_rank"] == 240
        assert independent["p5_increment_rank"] == 132
        assert independent["nested_error"] <= 1.0e-11
        assert independent["trace_leakage"] <= 1.0e-11
        assert independent["orthogonality_error"] <= 1.0e-11

        oriented_tensor = p6.orient_hcurl_tensor(
            tensor_reference,
            cell_info=cell_info,
        )
        oriented_rhs = p6.apply_hcurl_dof_transform(
            rhs_reference,
            cell_info=cell_info,
        )
        result = condense_p6_local_to_p4_core(
            tensor_reference,
            rhs_reference,
            cell_info=cell_info,
        )
        audit = result.audit
        assert (audit["p4_interior_rows"], audit["p5_interior_rows"]) == (
            108,
            240,
        )
        assert (audit["p6_trace_rows"], audit["p6_interior_rows"]) == (
            432,
            450,
        )
        assert (audit["p5_increment_rank"], audit["p6_increment_rank"]) == (
            132,
            210,
        )
        assert audit["nested_range_relative_error"] <= 1.0e-11
        assert audit["p6_trace_leakage_max"] <= 1.0e-11
        assert audit["orthogonality_error_max"] <= 1.0e-11
        assert audit["prefix_assumption_used"] is False
        assert audit["raw_p6_tensor_retained"] is False
        assert audit["research_only"] is True
        assert audit["ordinary_default_changed"] is False
        assert result.p6_trace_dofs.size == 432
        assert result.p6_interior_dofs.size == 450
        assert result.core_basis.shape == (450, 108)
        assert result.eliminated_basis.shape == (450, 342)
        assert result.partial_schur.shape == (540, 540)
        assert result.core_basis.dtype == np.float64
        assert result.eliminated_basis.dtype == np.float64

        observed_basis = _basis_matrix(
            result.p6_trace_dofs,
            result.p6_interior_dofs,
            np.column_stack((result.core_basis, result.eliminated_basis)),
        )
        core_projector_error = _relative(
            result.core_basis @ result.core_basis.conj().T,
            independent["q4"] @ independent["q4"].conj().T,
        )
        assert core_projector_error <= 1.0e-11
        observed_p5_basis = np.column_stack(
            (result.core_basis, result.eliminated_basis[:, :132])
        )
        expected_p5_basis = independent["q"][:, :240]
        p5_projector_error = _relative(
            observed_p5_basis @ observed_p5_basis.conj().T,
            expected_p5_basis @ expected_p5_basis.conj().T,
        )
        assert p5_projector_error <= 1.0e-11

        observed_operator = observed_basis.conj().T @ oriented_tensor @ observed_basis
        observed_rhs = observed_basis.conj().T @ oriented_rhs
        expected_schur = observed_operator[:540, :540] - (
            observed_operator[:540, 540:]
            @ np.linalg.solve(
                observed_operator[540:, 540:],
                observed_operator[540:, :540],
            )
        )
        expected_rhs = observed_rhs[:540] - (
            observed_operator[:540, 540:]
            @ np.linalg.solve(
                observed_operator[540:, 540:],
                observed_rhs[540:],
            )
        )
        partial_schur_error = _relative(result.partial_schur, expected_schur)
        partial_rhs_error = _relative(result.partial_rhs, expected_rhs)
        assert partial_schur_error <= 1.0e-11
        assert partial_rhs_error <= 1.0e-11

        probe = np.sin(0.031 * np.arange(540)) + 1j * np.cos(
            0.017 * (np.arange(540) + 1)
        )
        partial_action_error = _relative(
            result.partial_schur @ probe,
            expected_schur @ probe,
        )
        assert partial_action_error <= 1.0e-11

        partial_trace = result.partial_schur[:432, :432] - (
            result.partial_schur[:432, 432:]
            @ np.linalg.solve(
                result.partial_schur[432:, 432:],
                result.partial_schur[432:, :432],
            )
        )
        trace = independent["trace"]
        interior = independent["interior"]
        A_tt = oriented_tensor[np.ix_(trace, trace)]
        A_ti = oriented_tensor[np.ix_(trace, interior)]
        A_it = oriented_tensor[np.ix_(interior, trace)]
        A_ii = oriented_tensor[np.ix_(interior, interior)]
        full_trace = A_tt - A_ti @ np.linalg.solve(A_ii, A_it)
        trace_schur_error = _relative(partial_trace, full_trace)
        assert trace_schur_error <= 1.0e-11

        retained_solution = np.linalg.solve(expected_schur, expected_rhs)
        direct_solution = np.linalg.solve(oriented_tensor, oriented_rhs)
        recovered = result.recover_p6_coefficients(retained_solution)
        recovered_solution_error = _relative(recovered, direct_solution)
        full_residual = float(
            np.linalg.norm(oriented_tensor @ recovered - oriented_rhs)
            / max(float(np.linalg.norm(oriented_rhs)), 1.0e-30)
        )
        assert recovered_solution_error <= 1.0e-11
        assert full_residual <= 1.0e-11

        repeat = condense_p6_local_to_p4_core(
            tensor_reference,
            rhs_reference,
            cell_info=cell_info,
        )
        repeated = repeat.recover_p6_coefficients(retained_solution)
        repeat_schur_error = _relative(repeat.partial_schur, result.partial_schur)
        repeat_recovery_error = _relative(repeated, recovered)
        assert repeat_schur_error <= 1.0e-11
        assert repeat_recovery_error <= 1.0e-11
        assert not hasattr(result, "p6_tensor")
        for value in vars(result).values():
            if isinstance(value, np.ndarray):
                assert value.shape != (882, 882)
        print(
            {
                "cell_info": cell_info,
                "nested": audit["nested_range_relative_error"],
                "leakage": audit["p6_trace_leakage_max"],
                "orthogonality": audit["orthogonality_error_max"],
                "core_projector_error": core_projector_error,
                "p5_projector_error": p5_projector_error,
                "partial_schur_error": partial_schur_error,
                "partial_rhs_error": partial_rhs_error,
                "partial_action_error": partial_action_error,
                "trace_schur_error": trace_schur_error,
                "recovered_solution_error": recovered_solution_error,
                "full_residual": full_residual,
                "repeat_schur_error": repeat_schur_error,
                "repeat_recovery_error": repeat_recovery_error,
            }
        )
