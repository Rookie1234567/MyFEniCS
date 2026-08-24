"""Focused p2/MPI1 checks for the S4-A2a implicit owner-packet bridge."""

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


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


@pytest.fixture(scope="module")
def p2_case():
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("A2a focused fixture is the serial MPI1 check")
    case = build_implicit_lor_transfer_case(2, MPI.COMM_WORLD)
    try:
        yield case
    finally:
        if not case._destroyed:
            case.destroy()


def test_p2_implicit_bridge_owner_orientation_and_algebra(p2_case) -> None:
    case = p2_case
    fixture = case.fixture
    assert fixture.build_hx is False
    assert fixture.node_matrix is None
    assert fixture.hx is None
    assert fixture.audit["high_order_global_aij"] is False
    assert fixture.lor_node_constraint_audit["scalar_node_matrix"] is False
    assert case.audit["numeric_allgather"] is False
    assert case.audit["global_transfer_matrix"] is False

    for name in ("coarse_raw_map", "fine_raw_map"):
        facts = case.audit[name]
        assert facts["active_owner_bijection"] is True
        assert facts["active_raw_rows"] + facts["phase_rows"] == facts["owned_raw_rows"]
        raw_map = getattr(case, name)
        assert np.all(np.isin(raw_map["orientation_factors"], (-1, 1)))
        assert facts["phase_rows"] > 0
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
    assert case.audit["mpi_size"] == 1
    assert case.audit["build_scope"] == "p2_h50_mpi1_transfer_core_only"
    assert case.audit["qualification"] == "focused_core_only_not_S4"
    assert case.audit["global_de_rham"] == "local_A1_only_not_global_MPI_qualified"
    assert case.audit["fine_parent_multiplicity_min"] > 0

    coarse_x1 = case.coarse_matrix.createVecRight()
    coarse_x2 = case.coarse_matrix.createVecRight()
    fine_y1 = fixture.edge_matrix.createVecRight()
    fine_y2 = fixture.edge_matrix.createVecRight()
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
    fine_px2 = case.apply_primal(coarse_x2)
    coarse_phy1 = case.apply_adjoint(fine_y1)
    coarse_phy2 = case.apply_adjoint(fine_y2)
    np.testing.assert_array_equal(coarse_x1.array, coarse_x1_before)
    np.testing.assert_array_equal(coarse_x2.array, coarse_x2_before)
    np.testing.assert_array_equal(fine_y1.array, fine_y1_before)
    np.testing.assert_array_equal(fine_y2.array, fine_y2_before)

    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    coarse_x12 = coarse_x1.copy()
    coarse_x12.scale(alpha)
    coarse_x12.axpy(beta, coarse_x2)
    fine_px12 = case.apply_primal(coarse_x12)
    fine_expected = fine_px1.copy()
    fine_expected.scale(alpha)
    fine_expected.axpy(beta, fine_px2)
    assert _relative(fine_px12.array, fine_expected.array) <= LINEARITY_LIMIT

    fine_y12 = fine_y1.copy()
    fine_y12.scale(alpha)
    fine_y12.axpy(beta, fine_y2)
    coarse_phy12 = case.apply_adjoint(fine_y12)
    coarse_expected = coarse_phy1.copy()
    coarse_expected.scale(alpha)
    coarse_expected.axpy(beta, coarse_phy2)
    assert _relative(coarse_phy12.array, coarse_expected.array) <= LINEARITY_LIMIT

    fine_repeat = case.apply_primal(coarse_x1)
    coarse_repeat = case.apply_adjoint(fine_y1)
    assert _relative(fine_repeat.array, fine_px1.array) <= REPEAT_LIMIT
    assert _relative(coarse_repeat.array, coarse_phy1.array) <= REPEAT_LIMIT
    assert np.all(np.isfinite(fine_px1.array))
    assert np.all(np.isfinite(coarse_phy1.array))

    work_left = np.vdot(fine_px1.array, fine_y1.array)
    work_right = np.vdot(coarse_x1.array, coarse_phy1.array)
    assert abs(work_left - work_right) / max(
        abs(work_left), abs(work_right), np.finfo(float).tiny
    ) <= ADJOINT_LIMIT

    coarse_action = case.coarse_matrix.createVecLeft()
    fine_action = fixture.edge_matrix.createVecLeft()
    case.coarse_matrix.mult(coarse_x1, coarse_action)
    fixture.edge_matrix.mult(fine_px1, fine_action)
    coarse_energy = np.vdot(coarse_x1.array, coarse_action.array)
    fine_energy = np.vdot(fine_px1.array, fine_action.array)
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

    for vector in (
        coarse_x1,
        coarse_x2,
        coarse_x12,
        fine_y1,
        fine_y2,
        fine_y12,
        fine_px1,
        fine_px2,
        fine_px12,
        fine_repeat,
        coarse_phy1,
        coarse_phy2,
        coarse_phy12,
        coarse_repeat,
        coarse_action,
        fine_action,
        fine_expected,
        coarse_expected,
    ):
        vector.destroy()
    case.destroy()
    assert case._destroyed is True
    assert case.fixture is None
    case.destroy()
