"""Focused p2/p3 MPI1/MPI2 checks for the S4-A2a owner-packet bridge."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.fullspace_lor_edge_geometric_mg import (
    ADJOINT_LIMIT,
    CHEBYSHEV_DEGREE,
    DE_RHAM_LIMIT,
    FixedChebyshevJacobi,
    LAMBDA_HI_FACTOR,
    LAMBDA_LO_FACTOR,
    LINEARITY_LIMIT,
    POWER_STEPS,
    REPEAT_LIMIT,
)
from src.solvers.fullspace_lor_edge_geometric_mg_global import (
    FixedChebyshevJacobiPETSc,
    FixedOneVCycle,
    build_implicit_lor_transfer_case,
)


def _fill_raw_probe(vector, raw_map: dict[str, np.ndarray], offset: float) -> None:
    raw_ids = np.asarray(raw_map["raw_ids"], dtype=np.float64)
    vector.array[:] = (
        np.sin(0.013 * raw_ids + offset)
        + 0.31j * np.cos(0.017 * raw_ids - 0.7 * offset)
    )
    vector.array[np.asarray(raw_map["phase_codes"]) != 0] = 0.0


def _vec_relative(left, right) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    result = float(
        difference.norm() / max(right.norm(), np.finfo(float).tiny)
    )
    difference.destroy()
    return result


def _true_residual_rho(matrix, rhs, solution) -> float:
    action = matrix.createVecLeft()
    residual = matrix.createVecLeft()
    try:
        matrix.mult(solution, action)
        rhs.copy(residual)
        residual.axpy(-1.0, action)
        return float(
            residual.norm() / max(rhs.norm(), np.finfo(float).tiny)
        )
    finally:
        action.destroy()
        residual.destroy()


def _all_ranks_true(comm: MPI.Comm, local_value: bool) -> bool:
    return bool(comm.allreduce(int(bool(local_value)), op=MPI.MIN) == 1)


def _check_vcycle(case) -> None:
    comm = case.fixture.comm
    cycle = FixedOneVCycle(case)
    vectors = []
    try:
        assert len(cycle.smoother.power_history) == POWER_STEPS
        assert cycle.smoother.lambda_hi == (
            LAMBDA_HI_FACTOR * cycle.smoother.lambda_power10
        )
        assert cycle.smoother.lambda_lo == (
            LAMBDA_LO_FACTOR * cycle.smoother.lambda_hi
        )
        rhs1 = case.fixture.edge_matrix.createVecRight()
        vectors.append(rhs1)
        rhs2 = case.fixture.edge_matrix.createVecRight()
        vectors.append(rhs2)
        _fill_raw_probe(rhs1, case.fine_raw_map, 5.0)
        _fill_raw_probe(rhs2, case.fine_raw_map, 6.2)
        rhs1_before = rhs1.array.copy()
        rhs2_before = rhs2.array.copy()

        coarse_probe_rhs = case.coarse_matrix.createVecRight()
        coarse_probe_action = case.coarse_matrix.createVecLeft()
        coarse_probe_residual = case.coarse_matrix.createVecLeft()
        coarse_probe_solution = None
        try:
            _fill_raw_probe(coarse_probe_rhs, case.coarse_raw_map, 7.4)
            coarse_probe_solution, qualification = cycle.coarse_solver.solve(
                coarse_probe_rhs
            )
            case.coarse_matrix.mult(coarse_probe_solution, coarse_probe_action)
            coarse_probe_rhs.copy(coarse_probe_residual)
            coarse_probe_residual.axpy(-1.0, coarse_probe_action)
            qualification_residual = float(
                coarse_probe_residual.norm()
                / max(coarse_probe_rhs.norm(), np.finfo(float).tiny)
            )
            assert qualification["backend"] == "petsc-preonly-lu-mumps"
            assert qualification["finite"] is True
            assert qualification_residual <= 1.0e-11
            assert cycle.coarse_solver.solve_count == 1
        finally:
            if coarse_probe_solution is not None:
                coarse_probe_solution.destroy()
            coarse_probe_rhs.destroy()
            coarse_probe_action.destroy()
            coarse_probe_residual.destroy()

        output1 = cycle.apply(rhs1)
        vectors.append(output1)
        facts1 = dict(cycle.last_apply_facts)
        output2 = cycle.apply(rhs2)
        vectors.append(output2)
        facts2 = dict(cycle.last_apply_facts)
        assert np.array_equal(rhs1.array, rhs1_before)
        assert np.array_equal(rhs2.array, rhs2_before)
        for facts, expected_count in ((facts1, 2), (facts2, 3)):
            assert facts["coarse_solver_backend"] == "petsc-preonly-lu-mumps"
            assert facts["coarse_finite"] is True
            assert facts["fine_smoother_matrix_mult_count"] == 4
            assert facts["fine_matrix_mult_count"] == 2
            assert facts["transfer_primal_count"] == 1
            assert facts["transfer_adjoint_count"] == 1
            assert facts["coarse_factor_solve_count"] == expected_count

        alpha = 0.37 + 0.19j
        beta = -0.23 + 0.41j
        rhs12 = rhs1.copy()
        vectors.append(rhs12)
        rhs12.scale(alpha)
        rhs12.axpy(beta, rhs2)
        output12 = cycle.apply(rhs12)
        vectors.append(output12)
        expected12 = output1.copy()
        vectors.append(expected12)
        expected12.scale(alpha)
        expected12.axpy(beta, output2)
        linearity_error = _vec_relative(output12, expected12)
        assert linearity_error <= LINEARITY_LIMIT
        repeated = cycle.apply(rhs1)
        vectors.append(repeated)
        repeat_error = _vec_relative(repeated, output1)
        assert repeat_error <= REPEAT_LIMIT
        true_rhos = tuple(
            _true_residual_rho(case.fixture.edge_matrix, rhs, output)
            for rhs, output in (
                (rhs1, output1),
                (rhs2, output2),
                (rhs12, output12),
                (rhs1, repeated),
            )
        )
        assert all(np.isfinite(rho) and rho >= 0.0 for rho in true_rhos)
        correction_ratios = tuple(
            float(output.norm() / max(rhs.norm(), np.finfo(float).tiny))
            for rhs, output in (
                (rhs1, output1),
                (rhs2, output2),
                (rhs12, output12),
                (rhs1, repeated),
            )
        )
        assert all(np.isfinite(ratio) and ratio >= 0.0 for ratio in correction_ratios)
        for output in (output1, output2, output12, repeated):
            assert _all_ranks_true(
                comm, np.all(np.isfinite(np.asarray(output.array)))
            )
        assert cycle.smoother.apply_count == 8
    finally:
        cycle.destroy()
        assert cycle._destroyed is True
        assert cycle.coarse_solver.ksp is None
        assert cycle.smoother._destroyed is True
        for vector in vectors:
            vector.destroy()


def _check_case(case) -> None:
    comm = case.fixture.comm
    fixture = case.fixture
    assert comm.size in (1, 2)
    assert fixture.build_hx is False
    assert fixture.node_matrix is None
    assert fixture.hx is None
    assert fixture.audit["high_order_global_aij"] is False
    assert fixture.lor_node_constraint_audit["scalar_node_matrix"] is False
    assert case.audit["numeric_allgather"] is False
    assert case.audit["global_transfer_matrix"] is False
    assert case.audit["setup_closure_route"] == "typed_uint32_metadata_alltoallv"
    assert case.audit["apply_owner_route"] == "typed_complex128_alltoallv"
    assert case.audit["mpi_size"] == comm.size
    assert case.audit["build_scope"] == (
        f"p{case.degree}_h50_mpi{comm.size}_transfer_core_only"
    )
    assert case.audit["qualification"] == "focused_core_only_not_S4"
    assert case.audit["global_de_rham"] == (
        "local_A1_only_not_global_MPI_qualified"
    )

    for name in ("coarse_raw_map", "fine_raw_map"):
        facts = case.audit[name]
        assert facts["active_owner_bijection"] is True
        assert facts["active_raw_local_unique"] is True
        assert facts["canonical_owner_closure"] == "exact_sorted_set_once"
        assert facts["canonical_owner_received_rows"] > 0
        assert facts["global_active_raw_rows"] > 0
        assert facts["global_phase_rows"] > 0
        assert facts["global_owned_raw_rows"] == (
            facts["global_active_raw_rows"] + facts["global_phase_rows"]
        )
        assert _all_ranks_true(
            comm,
            np.all(np.isin(getattr(case, name)["orientation_factors"], (-1, 1))),
        )
    for topology in (
        case.coarse_topology,
        case.fine_parent_topology,
        case.fine_raw_topology,
    ):
        phase_values = np.asarray(topology.phase_values, dtype=np.complex128)
        assert np.any(np.abs(phase_values - 1.0) > 1.0e-12)
    assert case.audit["orientation_phase_contract"] == (
        "canonical route divides by phase; pull multiplies phase"
    )
    assert case.audit["fine_parent_multiplicity_min"] > 0

    vectors = []
    try:
        coarse_x1 = case.coarse_matrix.createVecRight()
        vectors.append(coarse_x1)
        coarse_x2 = case.coarse_matrix.createVecRight()
        vectors.append(coarse_x2)
        fine_y1 = fixture.edge_matrix.createVecRight()
        vectors.append(fine_y1)
        fine_y2 = fixture.edge_matrix.createVecRight()
        vectors.append(fine_y2)
        for vector, raw_map, offset in (
            (coarse_x1, case.coarse_raw_map, 0.2),
            (coarse_x2, case.coarse_raw_map, 1.1),
            (fine_y1, case.fine_raw_map, 2.0),
            (fine_y2, case.fine_raw_map, 3.4),
        ):
            _fill_raw_probe(vector, raw_map, offset)

        coarse_x1_before = coarse_x1.array.copy()
        coarse_x2_before = coarse_x2.array.copy()
        fine_y1_before = fine_y1.array.copy()
        fine_y2_before = fine_y2.array.copy()
        fine_px1 = case.apply_primal(coarse_x1)
        vectors.append(fine_px1)
        fine_px2 = case.apply_primal(coarse_x2)
        vectors.append(fine_px2)
        coarse_phy1 = case.apply_adjoint(fine_y1)
        vectors.append(coarse_phy1)
        coarse_phy2 = case.apply_adjoint(fine_y2)
        vectors.append(coarse_phy2)
        assert _all_ranks_true(comm, np.array_equal(coarse_x1.array, coarse_x1_before))
        assert _all_ranks_true(comm, np.array_equal(coarse_x2.array, coarse_x2_before))
        assert _all_ranks_true(comm, np.array_equal(fine_y1.array, fine_y1_before))
        assert _all_ranks_true(comm, np.array_equal(fine_y2.array, fine_y2_before))

        alpha = 0.37 + 0.19j
        beta = -0.23 + 0.41j
        coarse_x12 = coarse_x1.copy()
        vectors.append(coarse_x12)
        coarse_x12.scale(alpha)
        coarse_x12.axpy(beta, coarse_x2)
        fine_px12 = case.apply_primal(coarse_x12)
        vectors.append(fine_px12)
        fine_expected = fine_px1.copy()
        vectors.append(fine_expected)
        fine_expected.scale(alpha)
        fine_expected.axpy(beta, fine_px2)
        assert _vec_relative(fine_px12, fine_expected) <= LINEARITY_LIMIT

        fine_y12 = fine_y1.copy()
        vectors.append(fine_y12)
        fine_y12.scale(alpha)
        fine_y12.axpy(beta, fine_y2)
        coarse_phy12 = case.apply_adjoint(fine_y12)
        vectors.append(coarse_phy12)
        coarse_expected = coarse_phy1.copy()
        vectors.append(coarse_expected)
        coarse_expected.scale(alpha)
        coarse_expected.axpy(beta, coarse_phy2)
        assert _vec_relative(coarse_phy12, coarse_expected) <= LINEARITY_LIMIT

        fine_repeat = case.apply_primal(coarse_x1)
        vectors.append(fine_repeat)
        coarse_repeat = case.apply_adjoint(fine_y1)
        vectors.append(coarse_repeat)
        assert _vec_relative(fine_repeat, fine_px1) <= REPEAT_LIMIT
        assert _vec_relative(coarse_repeat, coarse_phy1) <= REPEAT_LIMIT
        assert _all_ranks_true(
            comm,
            all(np.all(np.isfinite(vector.array)) for vector in (
                fine_px1, coarse_phy1, fine_px12, coarse_phy12
            )),
        )

        work_left = fine_px1.dot(fine_y1)
        work_right = coarse_x1.dot(coarse_phy1)
        assert abs(work_left - work_right) / max(
            abs(work_left), abs(work_right), np.finfo(float).tiny
        ) <= ADJOINT_LIMIT

        coarse_action = case.coarse_matrix.createVecLeft()
        vectors.append(coarse_action)
        fine_action = fixture.edge_matrix.createVecLeft()
        vectors.append(fine_action)
        case.coarse_matrix.mult(coarse_x1, coarse_action)
        fixture.edge_matrix.mult(fine_px1, fine_action)
        coarse_energy = coarse_x1.dot(coarse_action)
        fine_energy = fine_px1.dot(fine_action)
        assert np.isfinite(coarse_energy) and np.isfinite(fine_energy)
        assert coarse_energy.real > 0.0 and fine_energy.real > 0.0
        assert abs(coarse_energy.imag) / max(
            abs(coarse_energy), np.finfo(float).tiny
        ) <= ADJOINT_LIMIT
        assert abs(fine_energy.imag) / max(
            abs(fine_energy), np.finfo(float).tiny
        ) <= ADJOINT_LIMIT
        assert abs(fine_energy - coarse_energy) / max(
            abs(coarse_energy), np.finfo(float).tiny
        ) <= 1.0e-9

        assert case.local_transfer.audit["gradient_commuting_relative"] <= DE_RHAM_LIMIT
        assert case.local_transfer.audit["curl_commuting_relative"] <= DE_RHAM_LIMIT
        _check_vcycle(case)
    finally:
        for vector in vectors:
            vector.destroy()


@pytest.mark.parametrize("degree", [2, 3])
def test_implicit_bridge_p2_p3_global_owner_algebra(degree: int) -> None:
    if MPI.COMM_WORLD.size not in (1, 2):
        pytest.skip("A2b focused bridge supports MPI1 or MPI2")
    case = build_implicit_lor_transfer_case(degree, MPI.COMM_WORLD)
    try:
        _check_case(case)
    finally:
        case.destroy()
        assert case._destroyed is True
        assert case.fixture is None


def test_petsc_fixed_chebyshev_matches_dense_a1_and_independent_t3() -> None:
    dense_matrix = np.asarray(
        [[2.0 + 0.0j, 0.25 - 0.1j], [0.25 + 0.1j, 1.5 + 0.0j]],
        dtype=np.complex128,
    )
    matrix = PETSc.Mat().createAIJ([2, 2], nnz=2, comm=PETSc.COMM_SELF)
    matrix.setUp()
    matrix.setValues([0, 1], [0, 1], dense_matrix)
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.array[:] = [1.0 + 0.5j, -0.75 + 0.25j]
    dense = FixedChebyshevJacobi(dense_matrix)
    petsc = FixedChebyshevJacobiPETSc(matrix)
    try:
        observed = petsc.apply(rhs)
        expected = dense.apply(np.asarray(rhs.array, dtype=np.complex128))
        assert len(petsc.power_history) == POWER_STEPS
        assert petsc.power_matrix_mult_count == 2 * POWER_STEPS
        assert petsc.lambda_hi == LAMBDA_HI_FACTOR * petsc.lambda_power10
        assert petsc.lambda_lo == LAMBDA_LO_FACTOR * petsc.lambda_hi
        assert np.linalg.norm(observed.array - expected) / np.linalg.norm(expected) <= 1.0e-13

        scaled_rhs = dense.scale * np.asarray(rhs.array, dtype=np.complex128)
        identity = np.eye(2, dtype=np.complex128)
        half_width = 0.5 * (dense.lambda_hi - dense.lambda_lo)
        center = 0.5 * (dense.lambda_hi + dense.lambda_lo)
        argument = (center * identity - dense.scaled_matrix) / half_width
        t1 = argument
        t2 = 2.0 * argument @ t1 - identity
        t3 = 2.0 * argument @ t2 - t1
        scalar_t3 = 4.0 * (center / half_width) ** 3 - 3.0 * (center / half_width)
        residual_polynomial = t3 / scalar_t3
        reference = dense.scale * np.linalg.solve(
            dense.scaled_matrix, (identity - residual_polynomial) @ scaled_rhs
        )
        assert np.linalg.norm(observed.array - reference) / np.linalg.norm(reference) <= 1.0e-13
        observed.destroy()
        petsc.destroy()
        assert petsc._destroyed is True
    finally:
        if not petsc._destroyed:
            petsc.destroy()
        rhs.destroy()
        matrix.destroy()


def test_fixed_one_vcycle_rejects_p6_coarse_direct_path() -> None:
    class P6Only:
        degree = 6

    with pytest.raises(ValueError, match="p2/p3"):
        FixedOneVCycle(P6Only())
