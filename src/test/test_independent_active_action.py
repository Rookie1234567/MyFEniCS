from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from src.solvers.independent_active_action import (
    action_group_metrics,
    project_trace_dual_blocks,
)


def test_projected_active_action_matches_explicit_augmented_matrix() -> None:
    trace_expansion = np.asarray(
        [
            [1.0 + 0.0j, 0.0 + 0.0j],
            [0.25 + 0.5j, 0.0 + 0.0j],
            [0.0 + 0.0j, 1.0 + 0.0j],
            [0.0 + 0.0j, -0.5 + 0.25j],
        ],
        dtype=np.complex128,
    )
    blocks = (
        SimpleNamespace(
            full_rows=np.asarray((0, 1), dtype=np.int64),
            independent_rows=np.asarray((0,), dtype=np.int64),
            full_from_independent=trace_expansion[:2, :1],
        ),
        SimpleNamespace(
            full_rows=np.asarray((2, 3), dtype=np.int64),
            independent_rows=np.asarray((1,), dtype=np.int64),
            full_from_independent=trace_expansion[2:, 1:],
        ),
    )
    active_expansion = np.zeros((5, 3), dtype=np.complex128)
    active_expansion[:4, :2] = trace_expansion
    active_expansion[4, 2] = 1.0

    volume_matrix = np.asarray(
        [
            [3.0 + 0.2j, 0.3 - 0.1j, 0.2, 0.1j, 0.0],
            [0.2 + 0.1j, 2.5, 0.0, 0.2j, 0.1],
            [0.0, 0.1 - 0.2j, 2.2 + 0.1j, 0.3, 0.2j],
            [0.1j, 0.0, 0.2, 2.8, 0.1 - 0.1j],
            [0.3, 0.1j, 0.0, 0.2, 1.7 - 0.1j],
        ],
        dtype=np.complex128,
    )
    traction = np.asarray(
        (0.3 + 0.2j, -0.1j, 0.4, 0.2 - 0.3j, 0.0),
        dtype=np.complex128,
    )
    lower_functional = np.asarray(
        (0.2 - 0.1j, 0.1j, -0.3, 0.15 + 0.2j, 0.0),
        dtype=np.complex128,
    )
    denominator = 1.7
    incident_projection = 0.35 - 0.15j
    incident_traction = np.asarray(
        (0.1 + 0.2j, 0.0, -0.1j, 0.3, 0.0),
        dtype=np.complex128,
    )
    independent_field = np.asarray(
        (0.5 - 0.2j, -0.3 + 0.1j, 0.25 + 0.3j),
        dtype=np.complex128,
    )
    auxiliary_amplitude = -0.2 + 0.4j
    active_field = active_expansion @ independent_field

    augmented_matrix = np.zeros((6, 6), dtype=np.complex128)
    augmented_matrix[:5, :5] = volume_matrix
    augmented_matrix[:5, 5] = -traction
    augmented_matrix[5, :5] = -np.conj(lower_functional) / denominator
    augmented_matrix[5, 5] = 1.0
    augmented_rhs = np.zeros(6, dtype=np.complex128)
    # The FE equation is Avol*u - T*alpha = incident - T*incident_projection.
    augmented_rhs[:5] = incident_traction - traction * incident_projection
    augmented_unknown = np.concatenate(
        (active_field, np.asarray((auxiliary_amplitude,)))
    )
    full_residual = augmented_matrix @ augmented_unknown - augmented_rhs
    test_expansion = np.zeros((6, 4), dtype=np.complex128)
    test_expansion[:5, :3] = active_expansion
    test_expansion[5, 3] = 1.0
    expected = test_expansion.conj().T @ full_residual

    projected_trace = project_trace_dual_blocks(
        full_residual[:4],
        independent_trace_rows=2,
        blocks=blocks,
    )
    observed = np.concatenate(
        (
            projected_trace,
            full_residual[4:5],
            full_residual[5:6],
        )
    )
    np.testing.assert_allclose(observed, expected, rtol=0.0, atol=1.0e-14)

    direct_fe_residual = (
        volume_matrix @ active_field
        - traction * auxiliary_amplitude
        - incident_traction
        + traction * incident_projection
    )
    np.testing.assert_allclose(
        full_residual[:5], direct_fe_residual, rtol=0.0, atol=1.0e-14
    )
    raw_modal_lower_residual = (
        denominator * auxiliary_amplitude
        - np.vdot(lower_functional, active_field)
    )
    np.testing.assert_allclose(
        denominator * full_residual[5],
        raw_modal_lower_residual,
        rtol=0.0,
        atol=1.0e-14,
    )
    assert action_group_metrics(projected_trace)["row_count"] == 2
