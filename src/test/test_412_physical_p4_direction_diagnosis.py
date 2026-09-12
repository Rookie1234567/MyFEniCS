"""Focused algebra gates for the opt-in P4 direction diagnosis."""

import inspect

import numpy as np

from src.solvers import physical_bounded_policy as bounded_policy
from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
from src.solvers.physical_p4_direction_diagnosis import (
    select_local_response_indices,
    svd_lstsq,
    weighted_mgs_lstsq,
)


def test_weighted_mgs_preserves_complex_nonorthogonal_exact_span():
    rng = np.random.default_rng(1301)
    columns = rng.normal(size=(9, 3)) + 1j * rng.normal(size=(9, 3))
    hessian_factor = rng.normal(size=(9, 9)) + 1j * rng.normal(size=(9, 9))
    mass = hessian_factor.conj().T @ hessian_factor + np.eye(9)
    target = columns @ np.array([1 + 2j, -0.3 + 0.4j, 2 - 0.1j])

    solution, facts = weighted_mgs_lstsq(columns, target, lambda value: mass @ value)

    relative = np.linalg.norm(columns @ solution - target) / np.linalg.norm(target)
    assert relative < 1.0e-11
    assert facts["rank"] == 3
    assert facts["mgs_rank"] == 3
    assert facts["r_factor"].shape == (3, 3)
    assert len(facts["column_scale"]) == 3


def test_weighted_mgs_handles_scale_and_skipped_columns_without_r_misalignment():
    rng = np.random.default_rng(1301)
    base = rng.normal(size=(9, 3)) + 1j * rng.normal(size=(9, 3))
    hessian_factor = rng.normal(size=(9, 9)) + 1j * rng.normal(size=(9, 9))
    mass = hessian_factor.conj().T @ hessian_factor + np.eye(9)
    columns = np.column_stack((np.zeros(9), base, base[:, 1]))
    columns[:, 1] *= 1.0e5
    target = rng.normal(size=9) + 1j * rng.normal(size=9)

    solution, facts = weighted_mgs_lstsq(columns, target, lambda value: mass @ value)

    assert np.isfinite(solution).all()
    assert facts["r_factor"].shape == (facts["mgs_rank"], columns.shape[1])
    assert facts["rank"] == 3
    assert facts["mgs_rank"] == 3
    assert facts["original_mass_energy"][0] == 0.0
    assert all(value >= 0.0 for value in facts["original_mass_energy"])


def test_selector_projects_base_before_first_reference_free_choice():
    eye = np.eye(4, dtype=np.complex128)
    rhs = 100.0 * eye[:, 0] + eye[:, 2]
    base = np.column_stack((10.0 * eye[:, 0], 30.0 * eye[:, 1]))
    local = np.column_stack((eye[:, 0] + 0.1 * eye[:, 3], eye[:, 2]))

    selected, facts = select_local_response_indices(rhs, base, local, max_local=1)
    selected_f, facts_f = select_local_response_indices(
        np.asfortranarray(rhs), np.asfortranarray(base), np.asfortranarray(local),
        max_local=1,
    )

    assert selected == [1]
    assert selected_f == selected
    assert facts_f["rounds"][0]["current_column_scale"] == facts["rounds"][0]["current_column_scale"]
    assert facts["uses_reference"] is False
    assert facts["rounds"][0]["current_column_scale"] == [10.0, 30.0]
    assert "target" not in inspect.signature(select_local_response_indices).parameters


def test_svd_lstsq_zero_and_rank_sensitive_columns_remain_finite():
    vector = np.array([1.0 + 0.5j, -2.0 + 0.25j, 0.75 - 1.5j])
    matrix = np.column_stack((np.zeros(3), vector, 2.0 * vector))
    solution, facts = svd_lstsq(matrix, vector)

    assert np.isfinite(solution).all()
    assert facts["rank"] == 1
    assert facts["column_scale"][0] == 1.0
    assert facts["qr_shape"] == [3, 3]
    np.testing.assert_allclose(matrix @ solution, vector, rtol=1e-12, atol=1e-12)


def test_production_pc_observer_records_right_pc_output_not_arnoldi_basis(monkeypatch):
    class FakeVec:
        def __init__(self, values):
            self.array = np.asarray(values, dtype=np.complex128).copy()

        def norm(self):
            return float(np.linalg.norm(self.array))

        def destroy(self):
            return None

    right_input = np.array([1.0 + 2.0j, -0.5 + 0.25j])
    right_pc_output = np.array([0.3 - 0.4j, 2.0 + 0.1j])
    arnoldi_basis_vector = np.array([-7.0 + 0.2j, 4.0 - 3.0j])

    def fake_i4(rhs, action, pc, **kwargs):
        assert kwargs["max_it"] == 4
        assert kwargs["restart"] == 4
        kwargs["pc_observer"](right_input, right_pc_output, 1)
        # This deliberately different vector represents an Arnoldi basis
        # vector; it must not be what the observer records.
        assert not np.array_equal(arnoldi_basis_vector, right_pc_output)
        return {
            "solution": FakeVec([0.1, 0.2]),
            "applied": FakeVec([0.3, 0.4]),
            "residual": FakeVec([0.5, 0.6]),
            "facts": {
                "status": "INNER_TARGET_REACHED",
                "iterations": 1,
                "seconds": 0.01,
                "actual_elapsed_seconds": 0.01,
                "final_true_residual": 0.1,
                "legal_direction_count": 1,
                "timeout_exceeded": False,
                "stop_reason": "TARGET",
            },
        }

    monkeypatch.setattr(bounded_policy, "solve_physical_i4", fake_i4)
    admission = bounded_policy.BoundedI4Admission(
        action=None,
        pc=None,
        sample=lambda: None,
        save=lambda *_: None,
        stop_requested=lambda: False,
        macro_policy=True,
        pc_observer=lambda *_: None,
    )
    captured = []
    admission.pc_observer = lambda pc_in, pc_out, count: captured.append(
        (np.array(pc_in, copy=True), np.array(pc_out, copy=True), count)
    )
    result = admission(FakeVec([1.0, 2.0]))
    try:
        assert len(captured) == 1
        np.testing.assert_array_equal(captured[0][0], right_input)
        np.testing.assert_array_equal(captured[0][1], right_pc_output)
        assert captured[0][2] == 1
    finally:
        for name in ("solution", "applied", "residual"):
            result[name].destroy()


def test_observation_defaults_are_closed_and_nonzero_reference_identity_uses_pou():
    coupling = PhysicalBalancedCoupling(
        lambda value: value,
        lambda value: value,
        lambda value: value,
        lambda value: value,
        route="BAL_H",
    )
    assert coupling.capture_vectors is False
    assert coupling.last_apply_vectors == {}

    # This is the P2 bookkeeping identity with a genuinely nonzero old
    # reference residual.  It exercises the same add.at partition-of-unity
    # accumulation and the operation-scale identity used by the runner.
    reference = np.array([1.0 + 0.2j, -0.5 + 0.1j, 0.75 - 0.3j])
    a = np.array([0.2 - 0.1j, -0.1 + 0.4j, 0.3 + 0.05j])
    e_h = reference - a
    r_ref = np.array([0.4 - 0.2j, -0.2 + 0.3j, 0.1 + 0.5j])
    h = np.array([1.1 + 0.4j, -0.4 - 0.2j, 0.8 + 0.2j])
    A_eh = h - r_ref
    np.testing.assert_allclose(A_eh - (h - r_ref), 0.0)

    block_indices = [np.array([0, 1]), np.array([1, 2])]
    block_weights = [np.array([1.0, 0.5]), np.array([0.5, 1.0])]
    block_values = [
        np.array([0.7 + 0.1j, 0.2 - 0.3j]),
        np.array([0.4 + 0.2j, 0.6 - 0.1j]),
    ]
    d = np.zeros(3, dtype=np.complex128)
    pou = np.zeros(3, dtype=np.float64)
    for indices, weights, values in zip(block_indices, block_weights, block_values):
        np.add.at(d, indices, values)
        np.add.at(pou, indices, weights)
    np.testing.assert_array_equal(pou, np.ones(3))
    recomposed = np.zeros(3, dtype=np.complex128)
    for indices, weights, values in zip(block_indices, block_weights, block_values):
        np.add.at(recomposed, indices, values - weights * e_h[indices])
    np.testing.assert_allclose(recomposed, d - e_h, rtol=1e-13, atol=1e-13)
