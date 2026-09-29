"""Finite, complex non-Hermitian diagnostics, including projection breakdown."""

import numpy as np
import pytest

from src.io.task042_v5_gate import check_complement, check_same_residual
from src.solvers.learned_fixed_localization import (
    complement_probes,
    coverage,
    diagnostic_budget,
    same_residual_actions,
    scaled_thin_lstsq,
)
from src.solvers.learned_two_level import (
    BalancedTwoLevelPC,
    algebra_audit,
    build_schur_encoding,
)


class Local:
    representation_bytes = factor_bytes = 0
    declarations = ()

    def __init__(self, matrix):
        self.matrix = matrix

    def apply_array(self, source):
        return self.matrix @ source


def make_pc(s, b, z):
    def operator(v):
        return s @ v

    z, u, r, _ = build_schur_encoding(np.asfortranarray(z), operator)
    return BalancedTwoLevelPC(Local(b), operator, z, u, r)


def toy():
    rng = np.random.default_rng(420806)
    s = (
        rng.standard_normal((23, 23))
        + 1j * rng.standard_normal((23, 23))
        + 8 * np.eye(23)
    )
    b = np.diag(1.0 / np.diag(s))
    z = np.linalg.qr(rng.standard_normal((23, 4)) + 1j * rng.standard_normal((23, 4)))[
        0
    ]
    r = np.asarray(rng.standard_normal(23) + 1j * rng.standard_normal(23))
    return make_pc(s, b, z), s, b, r


def test_new_identities_and_small_LS_match_explicit_nonhermitian():
    pc, s, b, r = toy()
    report, corrections, _ = same_residual_actions(pc, r)
    assert not np.allclose(s, s.conj().T)
    assert max(report["additional_identities"].values()) < 1e-12
    szb = np.column_stack((s @ pc.z, s @ (b @ r)))
    coeff = np.linalg.lstsq(szb, r, rcond=1e-10)[0]
    exact = pc.z @ coeff[:-1] + coeff[-1] * (b @ r)
    np.testing.assert_allclose(corrections["ZB_LS"], exact, rtol=1e-11, atol=1e-12)
    assert report["rho_ZB"] <= report["rho_BC"] + 1e-12
    assert report["rho_BC"] <= report["directions"]["B"]["rho_opt"] + 1e-12
    assert report["rho_ZB"] <= report["coverage_r"]["eta"] + 1e-12


def test_phase_scale_zero_immutability_and_complex_optimum():
    pc, s, _, r = toy()
    before = r.copy()
    basis_before = tuple(a.tobytes() for a in (pc.z, pc.u, pc.r))
    report, corrections, _ = same_residual_actions(pc, r)
    for scale in (1j, -1j, 1e-3, 1e3):
        scaled, adjusted, _ = same_residual_actions(pc, scale * r)
        for key in corrections:
            np.testing.assert_allclose(
                adjusted[key], scale * corrections[key], rtol=2e-11, atol=1e-12
            )
        assert scaled["rho_ZB"] == pytest.approx(report["rho_ZB"], abs=1e-12)
    alpha = complex(*report["directions"]["B"]["alpha"])
    sd = s @ corrections["B_unit"]
    assert alpha == pytest.approx(np.vdot(sd, r) / np.vdot(sd, sd))
    zero, zcorrections, _ = same_residual_actions(pc, np.zeros_like(r))
    assert zero["coverage_r"]["zero_rule"].startswith("exact zero")
    assert all(not np.any(a) for a in zcorrections.values())
    np.testing.assert_array_equal(before, r)
    assert basis_before == tuple(a.tobytes() for a in (pc.z, pc.u, pc.r))


def test_old_four_identities_do_not_guarantee_complement_action():
    s = np.eye(2, dtype=np.complex128)
    b = np.array([[0, 1], [1, 0]], dtype=np.complex128)
    pc = make_pc(s, b, np.array([[1], [0]], dtype=np.complex128))
    assert algebra_audit(pc, count=2)["passed"]
    b2 = np.column_stack([pc.apply_array(s[:, j]) for j in range(2)])
    np.testing.assert_array_equal(b2, np.diag([1, 0]))
    report, arrays = complement_probes(pc, [("e2", s[:, 1])])
    assert report["effective_rank"] == 1
    assert report["witness"]["HV_absolute"] == pytest.approx(1)
    assert report["witness"]["TV_absolute"] == pytest.approx(0)
    np.testing.assert_allclose(arrays["SB2v"], arrays["Tv"], atol=1e-12)


def test_normal_complement_control_and_small_projection_caveat():
    s = np.eye(4, dtype=np.complex128)
    # Full complement action swaps e2/e3: small V^H T V can be zero although
    # the sampled full image has norm one and is entirely retained.
    b = np.array(
        [[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 2j]], dtype=np.complex128
    )
    pc = make_pc(s, b, s[:, :1])
    report, _ = complement_probes(pc, [("e2", s[:, 1])])
    assert report["effective_rank"] == 3
    assert report["witness"]["TV_over_HV"] == pytest.approx(1)
    assert min(report["TV_singular_values"]) == pytest.approx(1)
    assert report["Pi_HV_norm"] < 1e-12
    assert np.vdot(s[:, 1], b @ s[:, 1]) == 0


def test_fixed_rank_rule_zero_and_dependent_LS_columns():
    rng = np.random.default_rng(17)
    y = rng.standard_normal(12) + 1j * rng.standard_normal(12)
    a = np.column_stack((y, 1j * y, np.zeros(12, dtype=np.complex128)))
    c, proof = scaled_thin_lstsq(a, y)
    assert proof["effective_rank"] == 1
    assert proof["zero_columns"] == [2]
    np.testing.assert_allclose(a @ c, y, rtol=1e-12, atol=1e-12)
    with pytest.raises(ValueError, match="129"):
        scaled_thin_lstsq(np.zeros((2, 130), dtype=np.complex128), np.zeros(2))


def test_coverage_zero_and_orthogonality_gate():
    pc, _, _, r = toy()
    record, represented, outside = coverage(r, pc.u)
    np.testing.assert_allclose(represented + outside, r, atol=1e-12)
    assert record["eta"] ** 2 + record["gamma"] ** 2 == pytest.approx(1)
    with pytest.raises(ValueError, match="decomposition"):
        coverage(r, np.asfortranarray(pc.u * 2))


def test_probe_inventory_deterministic_dependency_and_capacity():
    pc, _, _, r = toy()
    first, _ = complement_probes(
        pc, [("r", r), ("phase", 1j * r), ("zero", np.zeros_like(r))]
    )
    assert not first["sources"][1]["kept"] and not first["sources"][2]["kept"]
    assert first["registered_probe_count"] == 7
    assert first["effective_rank"] == 5
    assert first["real_SB2_vs_TV_max_defect"] < 1e-12
    bound = diagnostic_budget(21824, 128, 53084, 3010048, 302047392)
    assert bound["representation_workspace_bound_bytes"] < 512 * 2**20
    assert bound["all_factor_bound_bytes"] < 512 * 2**20
    with pytest.raises(ValueError, match="capacity"):
        diagnostic_budget(100000, 128, 250000, 3010048, 302047392)


def test_independent_checker_recomputes_raw_arrays_and_detects_tampering():
    pc, s, _, r = toy()
    report, corrections, arrays = same_residual_actions(pc, r)
    for name, d in corrections.items():
        arrays["remaining_" + name] = r - s @ d
    record = {"report": report, "corrected_audits": {}}
    assert check_same_residual(record, arrays)["passed"]
    record["report"]["rho_ZB"] *= 0.5
    with pytest.raises(ValueError, match="independent"):
        check_same_residual(record, arrays)


def test_complement_checker_uses_complete_images():
    pc, _, _, r = toy()
    report, arrays = complement_probes(pc, [("r", r)])
    assert check_complement(report, arrays)["passed"]
    arrays["Tv"] *= 0.5
    with pytest.raises(ValueError, match="complete-image"):
        check_complement(report, arrays)
