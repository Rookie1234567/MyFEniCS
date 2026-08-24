"""Focused p2/p3 MPI1/MPI2 checks for the S4-A2a owner-packet bridge."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.fullspace_lor_edge_geometric_mg import (
    ADJOINT_LIMIT,
    DE_RHAM_LIMIT,
    LINEARITY_LIMIT,
    REPEAT_LIMIT,
)
from src.solvers.fullspace_lor_edge_geometric_mg_global import (
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


def _all_ranks_true(comm: MPI.Comm, local_value: bool) -> bool:
    return bool(comm.allreduce(int(bool(local_value)), op=MPI.MIN) == 1)


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
