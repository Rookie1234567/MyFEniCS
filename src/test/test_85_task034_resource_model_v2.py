from __future__ import annotations

from benchmarks.task034_resource_model_v2 import _classification, _prediction


def _base() -> dict[str, float]:
    names = (
        "local_3d_fe_assembly", "local_3d_factorization",
        "qep_coefficient_matrices", "qep_shift_invert_factorization",
        "right_left_mode_vectors", "interface_projection_n_times_m",
        "replicated_dense_modal_arrays", "hybrid_schur_dense_multi_rhs",
        "field_reconstruction", "mpi_process_runtime_overhead",
    )
    value = {name: 1024.0 for name in names}
    value.update({
        "reference_local_fe_dofs_sum": 100.0,
        "reference_qep_dofs": 20.0,
        "reference_modes_per_direction": 10.0,
        "reference_peak_bytes": 10240.0,
        "reference_one_complex_2m_square_bytes": 6400.0,
    })
    return value


def test_predictions_are_monotone_and_never_claim_pde() -> None:
    coarse = _prediction(_base(), 13.5)
    fine = _prediction(_base(), 0.7)
    assert fine["cumulative_component_envelope_gib"] > coarse[
        "cumulative_component_envelope_gib"
    ]
    assert coarse["measured_simultaneous_peak_gib"] is not None
    assert fine["predicted_simultaneous_peak_gib"] is None
    assert fine["simultaneous_peak_model_status"] == "unknown_no_lifecycle_overlap_model"
    assert fine["predicted_modes_per_direction"] > coarse["predicted_modes_per_direction"]
    assert fine["components"]["hybrid_schur_dense_multi_rhs"]["scaling_exponent_in_13p5_over_lambda"] == 5.0


def test_budget_classification_is_fail_closed() -> None:
    assert _classification(300.0, 300.0, 256.0) == "infeasible_current_layout_by_single_component"
    assert _classification(300.0, 100.0, 256.0) == "cumulative_envelope_exceeds_budget_peak_unknown"
    assert _classification(200.0, 100.0, 256.0) == "cumulative_envelope_high_risk_peak_unknown"
    assert (
        _classification(100.0, 100.0, 256.0)
        == "cumulative_envelope_within_guardband_peak_unknown"
    )
