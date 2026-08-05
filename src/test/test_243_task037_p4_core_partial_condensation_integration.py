from __future__ import annotations

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse

from src.adaptivity.exact_sequence_variable_p import (
    build_variable_p_reference_space,
    HexaEntityDegreeMap,
)
from src.solvers.hcurl_p4_core_global_partial_condensation import (
    build_global_retained_p4_core_system,
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


def _tensor_and_rhs(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
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
    rhs = 0.2 * np.sin(0.017 * (np.arange(882) + seed)) + 1j * 0.15 * np.cos(
        0.023 * (np.arange(882) + 1 + seed)
    )
    return np.ascontiguousarray(tensor), np.ascontiguousarray(rhs)


def _local_basis(factor) -> np.ndarray:
    basis = np.zeros((882, 882), dtype=np.complex128)
    trace = factor.p6_trace_dofs
    interior = factor.p6_interior_dofs
    basis[np.ix_(trace, np.arange(432))] = np.eye(432)
    basis[
        np.ix_(
            interior,
            np.arange(432, 882),
        )
    ] = np.column_stack((factor.core_basis, factor.eliminated_basis))
    return basis


def test_global_retained_p4_core_action_rhs_and_recovery():
    comm = MPI.COMM_SELF
    p6 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(6))
    tensor0, rhs0 = _tensor_and_rhs(2431)
    tensor1, rhs1 = _tensor_and_rhs(2432)
    references = (rhs0, rhs1)
    factors = (
        condense_p6_local_to_p4_core(tensor0, rhs0, cell_info=0),
        condense_p6_local_to_p4_core(
            tensor1,
            rhs1,
            cell_info=_NONZERO_CELL_INFO,
        ),
    )
    trace_ids = tuple(np.arange(432, dtype=PETSc.IntType) for _ in factors)
    trace_expansions = tuple(
        sparse.eye(432, dtype=PETSc.ScalarType, format="csr") for _ in factors
    )
    system = build_global_retained_p4_core_system(
        factors,
        comm=comm,
        active_trace_rows=432,
        owned_active_trace_rows=432,
        cell_trace_ids=trace_ids,
        cell_trace_expansions=trace_expansions,
    )
    assert system.retained_rows == 648
    assert system.numbering.owned_retained_rows == 648
    assert system.numbering.cell_core_global_ids[0].tolist() == list(range(432, 540))
    assert system.numbering.cell_core_global_ids[1].tolist() == list(range(540, 648))
    assert system.audit["global_p6_matrix_materialized"] is False
    assert system.audit["global_p6_factor_count"] == 0
    assert system.audit["raw_p6_tensor_retained"] is False
    assert system.audit["research_only"] is True
    assert system.audit["ordinary_default_changed"] is False

    full_size = 432 + 2 * 450
    transformed_size = 648 + 2 * 342
    full_operator = np.zeros((full_size, full_size), dtype=np.complex128)
    full_rhs = np.zeros(full_size, dtype=np.complex128)
    transformed_operator = np.zeros(
        (transformed_size, transformed_size),
        dtype=np.complex128,
    )
    transformed_rhs = np.zeros(transformed_size, dtype=np.complex128)
    local_full_ids = []
    local_oriented_rhs = []
    for cell, (factor, tensor, rhs) in enumerate(
        zip(factors, (tensor0, tensor1), references, strict=True)
    ):
        oriented_tensor = p6.orient_hcurl_tensor(
            tensor,
            cell_info=factor.cell_info,
        )
        oriented_rhs = factor.orient_reference_vector(rhs)
        local_oriented_rhs.append(oriented_rhs)
        ids = np.empty(882, dtype=np.int64)
        ids[factor.p6_trace_dofs] = np.arange(432)
        ids[factor.p6_interior_dofs] = 432 + 450 * cell + np.arange(450)
        local_full_ids.append(ids)
        full_operator[np.ix_(ids, ids)] += oriented_tensor
        full_rhs[ids] += oriented_rhs

        local_basis = _local_basis(factor)
        local_transformed = local_basis.conj().T @ oriented_tensor @ local_basis
        local_transformed_rhs = local_basis.conj().T @ oriented_rhs
        transformed_ids = np.concatenate(
            (
                np.arange(432),
                432 + 108 * cell + np.arange(108),
                648 + 342 * cell + np.arange(342),
            )
        )
        transformed_operator[np.ix_(transformed_ids, transformed_ids)] += (
            local_transformed
        )
        transformed_rhs[transformed_ids] += local_transformed_rhs

    eliminated = np.arange(648, transformed_size)
    expected_schur = transformed_operator[:648, :648] - (
        transformed_operator[:648, eliminated]
        @ np.linalg.solve(
            transformed_operator[np.ix_(eliminated, eliminated)],
            transformed_operator[np.ix_(eliminated, np.arange(648))],
        )
    )
    expected_rhs = transformed_rhs[:648] - (
        transformed_operator[:648, eliminated]
        @ np.linalg.solve(
            transformed_operator[np.ix_(eliminated, eliminated)],
            transformed_rhs[eliminated],
        )
    )
    observed_schur = np.zeros((648, 648), dtype=np.complex128)
    for cell in range(2):
        ids, block = system.cell_contribution(cell)
        observed_schur[np.ix_(ids, ids)] += block
    assert _relative(observed_schur, expected_schur) <= 1.0e-11

    reduced_rhs = system.assemble_retained_rhs(reference_rhs_by_cell=references)
    observed_rhs = np.asarray(reduced_rhs.getArray(readonly=True)).copy()
    assert _relative(observed_rhs, expected_rhs) <= 1.0e-11
    reduced_rhs.destroy()

    local_rhs_reduction = system.reduce_reference_rhs_by_cell(references)
    for cell, (factor, oriented_rhs, tensor) in enumerate(
        zip(factors, local_oriented_rhs, (tensor0, tensor1), strict=True)
    ):
        local_basis = _local_basis(factor)
        local = local_basis.conj().T @ oriented_rhs
        local_tensor = p6.orient_hcurl_tensor(
            tensor,
            cell_info=factor.cell_info,
        )
        local_operator = local_basis.conj().T @ local_tensor @ local_basis
        local_expected = local[:540] - (
            local_operator[:540, 540:]
            @ np.linalg.solve(
                local_operator[540:, 540:],
                local[540:],
            )
        )
        assert _relative(local_rhs_reduction[cell], local_expected) <= 1.0e-11

    left_oriented = tuple(
        np.sin(0.031 * (np.arange(882) + cell))
        + 1j * np.cos(0.017 * (np.arange(882) + 1 + cell))
        for cell in range(2)
    )
    right_oriented = tuple(
        np.cos(0.023 * (np.arange(882) + 2 * cell))
        + 1j * np.sin(0.019 * (np.arange(882) + 3 + cell))
        for cell in range(2)
    )
    left_error = 0.0
    expected_left_global = np.zeros(648, dtype=np.complex128)
    bilinear_error = 0.0
    expected_bilinear_global = 0.0 + 0.0j
    for cell, (factor, left, right, tensor) in enumerate(
        zip(
            factors,
            left_oriented,
            right_oriented,
            (tensor0, tensor1),
            strict=True,
        )
    ):
        local_basis = _local_basis(factor)
        local_left = local_basis.conj().T @ left
        local_right = local_basis.conj().T @ right
        local_operator = (
            local_basis.conj().T
            @ p6.orient_hcurl_tensor(
                tensor,
                cell_info=factor.cell_info,
            )
            @ local_basis
        )
        expected_left = (
            local_left[:540]
            + (
                -np.linalg.solve(
                    local_operator[540:, 540:],
                    local_operator[540:, :540],
                )
            )
            .conj()
            .T
            @ local_left[540:]
        )
        observed_left = factor.reduce_oriented_left_functional(left)
        left_error = max(left_error, _relative(observed_left, expected_left))
        cell_ids, _block = system.cell_contribution(cell)
        expected_left_global[cell_ids] += expected_left
        expected_bilinear = local_left[540:].conj().T @ np.linalg.solve(
            local_operator[540:, 540:],
            local_right[540:],
        )
        observed_bilinear = factor.eliminated_complement_bilinear(
            left,
            right,
        )
        bilinear_error = max(
            bilinear_error,
            abs(observed_bilinear - expected_bilinear)
            / max(abs(expected_bilinear), 1.0e-30),
        )
        expected_bilinear_global += expected_bilinear
    assert left_error <= 1.0e-11
    assert bilinear_error <= 1.0e-11
    observed_bilinear_global = system.eliminated_complement_bilinear(
        left_oriented,
        right_oriented,
    )
    global_bilinear_error = abs(
        observed_bilinear_global - expected_bilinear_global
    ) / max(abs(expected_bilinear_global), 1.0e-30)
    assert global_bilinear_error <= 1.0e-11
    left_vector = system.assemble_retained_left_functional(left_oriented)
    left_global_error = _relative(
        np.asarray(left_vector.getArray(readonly=True)),
        expected_left_global,
    )
    assert left_global_error <= 1.0e-11
    left_vector.destroy()

    retained_solution = np.linalg.solve(expected_schur, expected_rhs)
    retained = system.create_retained_vector()
    retained.getArray()[:] = retained_solution
    recovered = system.recover_owned_cell_p6(
        retained,
        reference_rhs_by_cell=references,
    )
    direct_solution = np.linalg.solve(full_operator, full_rhs)
    recovered_error = 0.0
    recovered_global = np.zeros(full_size, dtype=np.complex128)
    for ids, values in zip(local_full_ids, recovered, strict=True):
        direct_values = direct_solution[ids]
        recovered_error = max(recovered_error, _relative(values, direct_values))
        recovered_global[ids] = values
    full_residual = float(
        np.linalg.norm(full_operator @ recovered_global - full_rhs)
        / max(float(np.linalg.norm(full_rhs)), 1.0e-30)
    )
    assert recovered_error <= 1.0e-11
    assert full_residual <= 1.0e-11

    projected = system.project_full_fe_solution(
        tuple(direct_solution[ids] for ids in local_full_ids)
    )
    projection_error = 0.0
    for cell, values in enumerate(projected):
        expected = np.concatenate(
            (
                retained_solution[:432],
                retained_solution[432 + 108 * cell : 432 + 108 * (cell + 1)],
            )
        )
        projection_error = max(projection_error, _relative(values, expected))
    assert projection_error <= 1.0e-11

    action, action_context = system.create_retained_action()
    probe = np.sin(0.011 * np.arange(648)) + 1j * np.cos(0.017 * (np.arange(648) + 1))
    source = system.create_retained_vector()
    target = system.create_retained_vector()
    source.getArray()[:] = probe
    action.mult(source, target)
    action_error = _relative(
        np.asarray(target.getArray(readonly=True)),
        expected_schur @ probe,
    )
    assert action_error <= 1.0e-11
    action.destroy()
    action_context.destroy()
    source.destroy()
    target.destroy()
    retained.destroy()

    for factor in factors:
        assert not hasattr(factor, "p6_tensor")
        for value in vars(factor).values():
            if isinstance(value, np.ndarray):
                assert value.shape != (882, 882)
    print(
        {
            "retained_rows": system.retained_rows,
            "global_core_rows": system.audit["global_core_rows"],
            "schur_error": _relative(observed_schur, expected_schur),
            "rhs_error": _relative(observed_rhs, expected_rhs),
            "action_error": action_error,
            "left_reduction_error": left_error,
            "left_global_error": left_global_error,
            "complement_bilinear_error": bilinear_error,
            "global_complement_bilinear_error": global_bilinear_error,
            "recovery_error": recovered_error,
            "projection_error": projection_error,
            "full_residual": full_residual,
        }
    )
