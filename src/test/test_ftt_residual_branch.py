"""Independent residual algebra and preservation of the original physical RHS."""

import numpy as np
import pytest
from src.solvers.ftt_residual_branch import (
    ResidualTrainingAction,
    residual_policy,
    residual_trend,
)


class MatrixAction:
    def __init__(self):
        self.A = np.array(
            [[2 + 1j, 3 - 2j], [0.2 + 4j, -1 + 0.5j]], dtype=np.complex128
        )
        self.f = np.array([1 + 2j, 3 - 0.4j], dtype=np.complex128)
        self.bnorm = float(np.linalg.norm(self.f))
        self.size = 2
        self.nc = 1
        self.np = 2
        self.counts = {}
        self.costs = {}

    def apply(self, c, *, adjoint=False):
        return (self.A.conj().T if adjoint else self.A) @ c

    def audit(self, c):
        return dict(
            native_relative=float(np.linalg.norm(self.A @ c - self.f) / self.bnorm)
        )


def test_exact_residual_identity_original_norm_and_rhs_immutable():
    a = MatrixAction()
    f = a.f.copy()
    base = np.array([0.3 + 0.2j, -0.2 + 1j])
    d = np.array([0.1 - 0.5j, 0.8 + 0.2j])
    v = ResidualTrainingAction(a, base)
    r = v.apply(d) - v.f
    np.testing.assert_allclose(r, a.A @ (base + d) - f, rtol=1e-14, atol=1e-14)
    assert v.original_relative(r) == pytest.approx(
        v.bnorm / a.bnorm * np.linalg.norm(r) / v.bnorm
    )
    assert v.audit(d)["native_relative"] == pytest.approx(
        np.linalg.norm(a.A @ (base + d) - f) / a.bnorm
    )
    np.testing.assert_array_equal(a.f, f)
    with pytest.raises(ValueError):
        v.f[0] = 0
    assert np.linalg.norm(v.apply(d) + v.f - (a.A @ (base + d) - f)) > 1e-2
    assert abs(np.linalg.norm(r) / v.bnorm - v.original_relative(r)) > 1e-2


@pytest.mark.parametrize(
    "changed",
    [
        "c_base_sha256",
        "training_rhs_sha256",
        "original_rhs_sha256",
        "bnorm_train",
        "bnorm_original",
    ],
)
def test_wrong_base_rhs_or_normalizer_binding_rejected(changed):
    a = MatrixAction()
    v = ResidualTrainingAction(a, np.array([1j, 0.4 + 0j]))
    expected = dict(v.identity)
    expected[changed] = "wrong"
    with pytest.raises(ValueError, match="IDENTITY_CHANGED"):
        ResidualTrainingAction(a, v.c_base, v.f, expected=expected)


def test_true_combined_fields_and_wrong_g_sign_rejected():
    a = MatrixAction()
    v = ResidualTrainingAction(a, np.array([0.2j, 1 + 0j]))
    d = np.array([0.1j, 0.3 + 0j])
    r = v.apply(d) - v.f
    fields = v.fields(d, r)
    np.testing.assert_allclose(fields["r_original"], a.A @ fields["c_combined"] - a.f)
    with pytest.raises(ValueError, match="EQUATION_MISMATCH"):
        v.fields(d, -r)
    a.f[0] += 1
    with pytest.raises(ValueError, match="RHS_MUTATED"):
        v.fields(d, r)


def test_nonhermitian_complex_adjoint_unchanged():
    a = MatrixAction()
    v = ResidualTrainingAction(a, np.array([0.2j, 1 + 0j]))
    x = np.array([1 + 2j, 0.5j])
    y = np.array([0.3 - 1j, 2 + 0.4j])
    assert np.vdot(v.apply(x), y) == pytest.approx(np.vdot(x, v.apply(y, adjoint=True)))


def test_core_history_original_residual_matches_full_physical_equation():
    a = MatrixAction()
    base = np.array([0.2j, 1 + 0j])
    d = np.array([0.1j, 0.3 + 0j])
    view = ResidualTrainingAction(a, base)
    r = a.A @ d - view.f
    loss = np.linalg.norm(r) ** 2 / (2 * view.bnorm**2)
    row = view.diagnostics(
        dict(native_trial=np.linalg.norm(r) / view.bnorm, trial_loss=loss)
    )
    assert row["native_trial"] == pytest.approx(a.audit(base + d)["native_relative"])
    assert row["training_native_trial"] != pytest.approx(row["native_trial"])
    assert row["original_trial_loss"] == pytest.approx(
        np.linalg.norm(a.A @ (base + d) - a.f) ** 2 / (2 * a.bnorm**2)
    )


@pytest.mark.parametrize("number", [2, 4])
def test_diagnostic_rounds_do_not_reapply_old_point_one_screen(number):
    s = {
        k: 1.0
        for k in (
            "native_relative",
            "augmented_relative",
            "scattered_E_relative",
            "scattered_H_relative",
            "scattered_curl_relative",
        )
    }
    assert residual_trend(number, s, residual_policy(True))["allowed"]
    s["scattered_H_relative"] = float("nan")
    assert not residual_trend(number, s, residual_policy(True))["allowed"]


def test_residual_stage_uses_current_window_and_failure_pool():
    from src.io.neural_wave_campaign import profile_paths
    from src.runners.block_wave_admission import pool, wait_limit
    from src.runners.neural_wave_campaign import stage_deadline

    paths = profile_paths({"campaign_version": 46})
    assert paths["root"].name == "v46" and paths["reserve"] == 3600
    assert pool(paths["root"]).parent.name == "v46" and wait_limit(paths["root"]) == 900
    assert stage_deadline(
        {"campaign_version": 46},
        {"deadline_monotonic": 10000},
        {"deadline_monotonic": 12000},
    ) == (8400, 3600)
