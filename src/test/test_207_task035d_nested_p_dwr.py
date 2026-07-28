from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from src.adaptivity.nested_p_dwr import (
    affine_channel_value,
    affine_goal_gradient,
    cell_schur_action_delta_residual,
    cell_schur_delta_residual,
    complex_pairing,
    effective_enriched_residual,
    hermitian_adjoint,
    operator_delta_residual,
    scaled_unit_adjoint_pairing,
    signed_dwr_partition_audit,
    signed_pairing,
    unit_channel_goal_scalar,
)


@dataclass(frozen=True)
class _Cell:
    rows: np.ndarray
    expansion: np.ndarray
    schur_a: np.ndarray
    schur_b: np.ndarray
    rhs_a: np.ndarray
    rhs_b: np.ndarray


@dataclass(frozen=True)
class _Fixture:
    matrix_a: np.ndarray
    matrix_b: np.ndarray
    rhs_a: np.ndarray
    rhs_b: np.ndarray
    state_a: np.ndarray
    state_b: np.ndarray
    effective: np.ndarray
    cells: tuple[_Cell, ...]
    components: dict[str, np.ndarray]


def _cell(
    *,
    rows: tuple[int, int, int],
    phase: complex,
    shift: float,
) -> _Cell:
    expansion = np.asarray(
        [
            [1.0, 0.08j * phase, 0.0],
            [0.0, phase, -0.06 + 0.03j],
            [0.04 - 0.02j, 0.0, np.conj(phase)],
        ],
        dtype=np.complex128,
    )
    schur_b = np.asarray(
        [
            [2.1 + shift + 0.17j, 0.12 - 0.08j, -0.03j],
            [-0.05 + 0.04j, 1.8 + 0.5 * shift - 0.11j, 0.09],
            [0.02 + 0.03j, -0.07j, 2.3 + 0.3 * shift + 0.06j],
        ],
        dtype=np.complex128,
    )
    schur_a = schur_b + (1.0 + 0.8 * shift) * np.asarray(
        [
            [0.13 + 0.04j, -0.035 + 0.01j, 0.008j],
            [0.021 - 0.015j, -0.09 + 0.025j, 0.017],
            [-0.013j, 0.028 + 0.009j, 0.07 - 0.02j],
        ],
        dtype=np.complex128,
    )
    rhs_b = np.asarray(
        [0.14 + 0.03j, -0.08 + 0.09j, 0.05 - 0.04j],
        dtype=np.complex128,
    ) * (1.0 + 0.1 * shift)
    rhs_a = rhs_b + (1.0 + 0.6 * shift) * np.asarray(
        [0.012 - 0.007j, -0.009 + 0.004j, 0.006 + 0.003j],
        dtype=np.complex128,
    )
    return _Cell(
        rows=np.asarray(rows, dtype=np.int64),
        expansion=expansion,
        schur_a=schur_a,
        schur_b=schur_b,
        rhs_a=rhs_a,
        rhs_b=rhs_b,
    )


def _assemble_cell(
    matrix: np.ndarray,
    rhs: np.ndarray,
    cell: _Cell,
    *,
    enriched: bool,
) -> None:
    schur = cell.schur_a if enriched else cell.schur_b
    local_rhs = cell.rhs_a if enriched else cell.rhs_b
    rows = cell.rows
    matrix[np.ix_(rows, rows)] += (
        cell.expansion.conj().T @ schur @ cell.expansion
    )
    rhs[rows] += cell.expansion.conj().T @ local_rhs


def _fixture() -> _Fixture:
    size = 7
    cells = (
        _cell(rows=(0, 1, 2), phase=np.exp(0.31j), shift=0.0),
        _cell(rows=(2, 3, 4), phase=np.exp(-0.27j), shift=0.4),
    )
    common = np.diag(
        np.asarray(
            [
                3.2 + 0.08j,
                3.5 - 0.05j,
                3.0 + 0.11j,
                3.7 - 0.04j,
                3.3 + 0.07j,
                2.9 - 0.09j,
                3.6 + 0.03j,
            ],
            dtype=np.complex128,
        )
    )
    common[0, 4] = 0.04 - 0.02j
    common[4, 0] = -0.03 + 0.01j

    port_b = np.zeros((size, size), dtype=np.complex128)
    port_b[1, 5] = 0.18 - 0.07j
    port_b[5, 1] = -0.11 + 0.05j
    port_b[4, 5] = -0.09j
    port_b[5, 4] = 0.06 + 0.02j
    port_a = port_b.copy()
    port_a[1, 5] += 0.035 + 0.012j
    port_a[5, 1] -= 0.019 - 0.008j

    auxiliary_b = np.zeros((size, size), dtype=np.complex128)
    auxiliary_b[5:, 5:] = np.asarray(
        [[1.7 + 0.13j, 0.08 - 0.03j], [-0.04j, 1.9 - 0.06j]]
    )
    auxiliary_a = auxiliary_b.copy()
    auxiliary_a[5:, 5:] += np.asarray(
        [[0.06 - 0.02j, -0.015j], [0.022 + 0.01j, -0.04 + 0.03j]]
    )

    matrix_a = common + port_a + auxiliary_a
    matrix_b = common + port_b + auxiliary_b
    rhs_a = np.asarray(
        [0.2 + 0.1j, -0.1 + 0.03j, 0.07j, 0.04, -0.02j, 0.3, -0.16j],
        dtype=np.complex128,
    )
    rhs_b = rhs_a.copy()
    port_rhs_a = np.zeros(size, dtype=np.complex128)
    port_rhs_b = np.zeros(size, dtype=np.complex128)
    port_rhs_a[[1, 5]] = (0.014 - 0.006j, -0.009 + 0.004j)
    port_rhs_b[[1, 5]] = (-0.006 + 0.002j, 0.005 - 0.003j)
    auxiliary_rhs_a = np.zeros(size, dtype=np.complex128)
    auxiliary_rhs_b = np.zeros(size, dtype=np.complex128)
    auxiliary_rhs_a[6] = 0.011 + 0.008j
    auxiliary_rhs_b[6] = -0.004 + 0.002j
    rhs_a += port_rhs_a + auxiliary_rhs_a
    rhs_b += port_rhs_b + auxiliary_rhs_b
    for cell in cells:
        _assemble_cell(matrix_a, rhs_a, cell, enriched=True)
        _assemble_cell(matrix_b, rhs_b, cell, enriched=False)

    assert np.linalg.cond(matrix_a) < 1.0e3
    exact_a = np.linalg.solve(matrix_a, rhs_a)
    exact_b = np.linalg.solve(matrix_b, rhs_b)
    perturb_a = 2.0e-5 * np.asarray(
        [0.4 + 0.2j, -0.3j, 0.1, -0.2 + 0.1j, 0.15j, -0.1, 0.25]
    )
    perturb_b = 1.5e-5 * np.asarray(
        [-0.2j, 0.3, -0.15 + 0.05j, 0.22j, -0.1, 0.18, -0.12j]
    )
    state_a = exact_a + perturb_a
    state_b = exact_b + perturb_b
    effective = effective_enriched_residual(
        matrix_a,
        rhs_a,
        state_a,
        state_b,
    )

    cell_components: dict[str, np.ndarray] = {}
    for index, cell in enumerate(cells):
        result = cell_schur_delta_residual(
            global_size=size,
            rows=cell.rows,
            expansion=cell.expansion,
            schur_a=cell.schur_a,
            schur_b=cell.schur_b,
            rhs_a=cell.rhs_a,
            rhs_b=cell.rhs_b,
            state_b=state_b,
        )
        cell_components[f"cell_{index}"] = result.global_residual

    coarse_residual = rhs_b - matrix_b @ state_b
    enriched_residual_correction = -(rhs_a - matrix_a @ state_a)
    port = operator_delta_residual(
        port_rhs_a,
        port_rhs_b,
        port_a @ state_b,
        port_b @ state_b,
    )
    auxiliary = operator_delta_residual(
        auxiliary_rhs_a,
        auxiliary_rhs_b,
        auxiliary_a @ state_b,
        auxiliary_b @ state_b,
    )
    components = {
        "coarse_solver_residual": coarse_residual,
        **cell_components,
        "port": port,
        "auxiliary": auxiliary,
        "enriched_solver_correction": enriched_residual_correction,
    }
    np.testing.assert_allclose(
        np.sum(np.stack(tuple(components.values())), axis=0),
        effective,
        rtol=2.0e-12,
        atol=2.0e-13,
    )
    return _Fixture(
        matrix_a=matrix_a,
        matrix_b=matrix_b,
        rhs_a=rhs_a,
        rhs_b=rhs_b,
        state_a=state_a,
        state_b=state_b,
        effective=effective,
        cells=cells,
        components=components,
    )


def test_streamed_cell_action_matches_dense_schur_identity() -> None:
    fixture = _fixture()
    cell = fixture.cells[0]
    local_trace = cell.expansion @ fixture.state_b[cell.rows]
    dense = cell_schur_delta_residual(
        global_size=len(fixture.state_b),
        rows=cell.rows,
        expansion=cell.expansion,
        schur_a=cell.schur_a,
        schur_b=cell.schur_b,
        rhs_a=cell.rhs_a,
        rhs_b=cell.rhs_b,
        state_b=fixture.state_b,
    )
    streamed = cell_schur_action_delta_residual(
        global_size=len(fixture.state_b),
        rows=cell.rows,
        expansion=cell.expansion,
        action_a_on_trace_b=cell.schur_a @ local_trace,
        action_b_on_trace_b=cell.schur_b @ local_trace,
        interior_rhs_correction_a=cell.rhs_a,
        interior_rhs_correction_b=cell.rhs_b,
    )
    assert streamed.local_trace.shape == (0,)
    np.testing.assert_allclose(
        streamed.local_residual,
        dense.local_residual,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        streamed.global_residual,
        dense.global_residual,
        rtol=2.0e-13,
        atol=2.0e-13,
    )


@pytest.mark.parametrize(
    "quantity",
    ("amplitude_real", "amplitude_imag", "power"),
)
def test_complex_nonhermitian_signed_partition_is_exact(
    quantity: str,
) -> None:
    fixture = _fixture()
    row = np.asarray(
        [
            0.11 - 0.04j,
            -0.07 + 0.03j,
            0.02j,
            0.09,
            -0.05 - 0.02j,
            0.8 + 0.27j,
            -0.13j,
        ],
        dtype=np.complex128,
    )
    offset = -0.12 + 0.08j
    value_a = affine_channel_value(row, offset, fixture.state_a)
    value_b = affine_channel_value(row, offset, fixture.state_b)
    weight = 0.73
    if quantity == "amplitude_real":
        actual = float(value_a.real - value_b.real)
    elif quantity == "amplitude_imag":
        actual = float(value_a.imag - value_b.imag)
    else:
        actual = float(
            weight * (abs(value_a) ** 2 - abs(value_b) ** 2)
        )
    gradient = affine_goal_gradient(
        row,
        quantity=quantity,
        value_a=value_a,
        value_b=value_b,
        weight=weight,
    )
    adjoint = hermitian_adjoint(fixture.matrix_a, gradient)
    report = signed_dwr_partition_audit(
        actual_goal_delta=actual,
        adjoint=adjoint,
        effective_residual=fixture.effective,
        component_residuals=fixture.components,
    )
    assert report["pass"] is True
    assert report["residual_partition_pass"] is True
    assert report["goal_closure_pass"] is True
    assert report["unexplained_residual_norm"] <= 2.0e-13
    assert report["unexplained_residual_added_back_as_component"] is False

    wrong_adjoint = np.linalg.solve(fixture.matrix_a.T, gradient)
    wrong_estimate = signed_pairing(wrong_adjoint, fixture.effective)
    assert abs(wrong_estimate - actual) > 1.0e-6
    wrong_dot = float(np.real(np.dot(adjoint, fixture.effective)))
    assert abs(wrong_dot - actual) > 1.0e-6


def test_unit_channel_scaling_and_midpoint_power_are_exact() -> None:
    fixture = _fixture()
    index = 5
    scale = 1.2 + 0.43j
    boundary_phase = 0.83 - 0.29j
    incident = 0.14 + 0.06j
    weight = 0.61
    outgoing_a = fixture.state_a[index] / scale - incident
    outgoing_b = fixture.state_b[index] / scale - incident
    boundary_a = boundary_phase * outgoing_a
    boundary_b = boundary_phase * outgoing_b
    unit = np.zeros(len(fixture.state_a), dtype=np.complex128)
    unit[index] = 1.0
    unit_adjoint = hermitian_adjoint(fixture.matrix_a, unit)
    unit_pairing = complex_pairing(unit_adjoint, fixture.effective)

    for quantity, actual in (
        ("amplitude_real", boundary_a.real - boundary_b.real),
        ("amplitude_imag", boundary_a.imag - boundary_b.imag),
        (
            "power",
            weight * (abs(outgoing_a) ** 2 - abs(outgoing_b) ** 2),
        ),
    ):
        scalar = unit_channel_goal_scalar(
            quantity=quantity,
            coordinate_scale=scale,
            boundary_phase=boundary_phase,
            power_weight=weight,
            outgoing_a=outgoing_a,
            outgoing_b=outgoing_b,
        )
        estimate = float(
            np.real(
                scaled_unit_adjoint_pairing(unit_pairing, scalar)
            )
        )
        assert estimate == pytest.approx(
            actual,
            rel=2.0e-12,
            abs=2.0e-13,
        )

    correct_real = unit_channel_goal_scalar(
        quantity="amplitude_real",
        coordinate_scale=scale,
        boundary_phase=boundary_phase,
    )
    wrong_real = np.conj(boundary_phase) / scale
    assert abs(
        np.real(scaled_unit_adjoint_pairing(unit_pairing, wrong_real))
        - (boundary_a.real - boundary_b.real)
    ) > 1.0e-6
    assert correct_real != pytest.approx(wrong_real)

    power_delta = weight * (
        abs(outgoing_a) ** 2 - abs(outgoing_b) ** 2
    )
    delta_amplitude = outgoing_a - outgoing_b
    scalar_b = 2.0 * weight * outgoing_b / np.conj(scale)
    scalar_a = 2.0 * weight * outgoing_a / np.conj(scale)
    estimate_b = float(
        np.real(scaled_unit_adjoint_pairing(unit_pairing, scalar_b))
    )
    estimate_a = float(
        np.real(scaled_unit_adjoint_pairing(unit_pairing, scalar_a))
    )
    endpoint_gap = weight * abs(delta_amplitude) ** 2
    assert estimate_b == pytest.approx(
        power_delta - endpoint_gap,
        rel=5.0e-12,
        abs=5.0e-13,
    )
    assert estimate_a == pytest.approx(
        power_delta + endpoint_gap,
        rel=5.0e-12,
        abs=5.0e-13,
    )
    assert endpoint_gap > 1.0e-8


def test_complex_constraint_and_cell_identity_controls_fail_closed() -> None:
    fixture = _fixture()
    cell = fixture.cells[0]
    correct = cell_schur_delta_residual(
        global_size=len(fixture.state_b),
        rows=cell.rows,
        expansion=cell.expansion,
        schur_a=cell.schur_a,
        schur_b=cell.schur_b,
        rhs_a=cell.rhs_a,
        rhs_b=cell.rhs_b,
        state_b=fixture.state_b,
    )
    wrong_global = np.zeros_like(fixture.effective)
    np.add.at(
        wrong_global,
        cell.rows,
        cell.expansion.T @ correct.local_residual,
    )
    assert np.linalg.norm(
        wrong_global - correct.global_residual
    ) > 1.0e-6

    reversed_components = dict(reversed(tuple(fixture.components.items())))
    row = np.linspace(0.1, 0.7, len(fixture.state_a)).astype(
        np.complex128
    )
    value_a = affine_channel_value(row, 0.0, fixture.state_a)
    value_b = affine_channel_value(row, 0.0, fixture.state_b)
    gradient = affine_goal_gradient(row, quantity="amplitude_real")
    adjoint = hermitian_adjoint(fixture.matrix_a, gradient)
    reordered = signed_dwr_partition_audit(
        actual_goal_delta=value_a.real - value_b.real,
        adjoint=adjoint,
        effective_residual=fixture.effective,
        component_residuals=reversed_components,
    )
    assert reordered["pass"] is True

    first, second = fixture.cells
    shuffled_first = cell_schur_delta_residual(
        global_size=len(fixture.state_b),
        rows=first.rows,
        expansion=first.expansion,
        schur_a=second.schur_a,
        schur_b=second.schur_b,
        rhs_a=second.rhs_a,
        rhs_b=second.rhs_b,
        state_b=fixture.state_b,
    )
    broken = dict(fixture.components)
    broken["cell_0"] = shuffled_first.global_residual
    shuffled = signed_dwr_partition_audit(
        actual_goal_delta=value_a.real - value_b.real,
        adjoint=adjoint,
        effective_residual=fixture.effective,
        component_residuals=broken,
    )
    assert shuffled["pass"] is False
    assert shuffled["unexplained_residual_norm"] > 1.0e-6

    missing_port = {
        name: vector
        for name, vector in fixture.components.items()
        if name not in {"port", "auxiliary"}
    }
    omitted = signed_dwr_partition_audit(
        actual_goal_delta=value_a.real - value_b.real,
        adjoint=adjoint,
        effective_residual=fixture.effective,
        component_residuals=missing_port,
    )
    assert omitted["pass"] is False
    assert omitted["unexplained_residual_norm"] > 1.0e-6


def test_solver_residual_corrections_and_signed_sum_are_not_hidden() -> None:
    fixture = _fixture()
    without_enriched_correction = {
        name: vector
        for name, vector in fixture.components.items()
        if name != "enriched_solver_correction"
    }
    without_coarse_residual = {
        name: vector
        for name, vector in fixture.components.items()
        if name != "coarse_solver_residual"
    }
    assert np.linalg.norm(
        fixture.effective
        - np.sum(
            np.stack(tuple(without_enriched_correction.values())),
            axis=0,
        )
    ) > 1.0e-6
    assert np.linalg.norm(
        fixture.effective
        - np.sum(
            np.stack(tuple(without_coarse_residual.values())),
            axis=0,
        )
    ) > 1.0e-6

    adjoint = np.asarray([1.0 + 0.0j])
    effective = np.asarray([1.0e-3 + 0.0j])
    cancellation = signed_dwr_partition_audit(
        actual_goal_delta=1.0e-3,
        adjoint=adjoint,
        effective_residual=effective,
        component_residuals={
            "positive": np.asarray([1.0 + 0.0j]),
            "negative": np.asarray([-0.999 + 0.0j]),
        },
    )
    assert cancellation["pass"] is True
    assert cancellation["component_signed_sum"] == pytest.approx(1.0e-3)
    assert cancellation["component_absolute_marking_sum"] == pytest.approx(
        1.999
    )
    assert cancellation["absolute_sum_used_for_closure"] is False
