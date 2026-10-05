import numpy as np
from petsc4py import PETSc

from src.runners.task40_v10_worker import (
    _assign_vector_storage,
    _regular_inverse_gate_facts,
)


def _regular_inverse_gate_inputs():
    return {
        "equation_relative": 1.5e-11,
        "action_relative": 5.0e-12,
        "recovery": {
            "internal_row_count": 36_000,
            "internal_residual_relative": 5.0e-12,
            "port_mode_count": 532,
            "port_residual_relative": 5.0e-9,
            "native_identity_relative": 5.0e-11,
            "schur_port_identity_relative": 5.0e-11,
            "projected_saved_field_recovery_relative": 5.0e-12,
        },
        "local_equation_relative": 5.0e-11,
        "port_closure_relative": 5.0e-12,
        "q_residual_relative": 5.0e-11,
        "q_coverage_passed": True,
    }


def test_assign_vector_storage_uses_public_writable_petsc_array_api():
    vector = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    try:
        _assign_vector_storage(vector, np.array([1 + 2j, 3 + 4j, 5 + 6j]))
        _assign_vector_storage(
            vector, np.array([9 + 1j, 8 + 2j]), rows=np.array([0, 2], dtype=np.int64)
        )
        np.testing.assert_array_equal(
            np.asarray(vector.array_r),
            np.array([9 + 1j, 3 + 4j, 8 + 2j], dtype=np.complex128),
        )
    finally:
        vector.destroy()


def test_regular_inverse_equation_gate_is_distinct_from_action_gate():
    facts = _regular_inverse_gate_facts(**_regular_inverse_gate_inputs())

    assert facts["passed"]
    assert facts["gates"]["original_regular_equation"]
    assert facts["gates"]["independent_sector_action_consistency"]


def test_regular_inverse_gate_failures_are_reported_independently():
    cases = (
        ("original_regular_equation", "equation_relative", None, 1.01e-10),
        ("independent_sector_action_consistency", "action_relative", None, 1.01e-11),
        ("full_internal_recovery", "recovery", "internal_residual_relative", 1.01e-11),
        ("two_local_original_equations", "local_equation_relative", None, 1.01e-10),
        ("all_532_port_equations", "recovery", "port_residual_relative", 1.01e-8),
        ("native_action_recovery_identity", "recovery", "native_identity_relative", 1.01e-10),
        ("schur_port_recovery_identity", "recovery", "schur_port_identity_relative", 1.01e-10),
        (
            "saved_field_local_recovery_identity",
            "recovery",
            "projected_saved_field_recovery_relative",
            1.01e-11,
        ),
        ("global_alpha_port_closure", "port_closure_relative", None, 1.01e-11),
        ("all_four_q_true_residuals", "q_residual_relative", None, 1.01e-10),
        ("all_four_q_true_residuals", "q_coverage_passed", None, False),
    )

    for expected_failure, input_name, recovery_key, value in cases:
        inputs = _regular_inverse_gate_inputs()
        if recovery_key is None:
            inputs[input_name] = value
        else:
            inputs["recovery"] = dict(inputs["recovery"])
            inputs["recovery"][recovery_key] = value
        facts = _regular_inverse_gate_facts(**inputs)
        assert facts["failed_gates"] == [expected_failure]
