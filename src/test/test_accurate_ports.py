"""Targeted final-recovery arithmetic, corruption and actual-vector tests."""

import copy
import json
from pathlib import Path
import numpy as np
import pytest

from src.solvers.accurate_ports import recover_ports
from benchmarks.accurate_port_checker import decimal_ports, check_published


def fixture():
    return dict(
        H=np.array([0.3]),
        gp=np.array([0j]),
        dp=np.array([0, 0, 0]),
        dr=np.arange(3),
        dv=np.array([1e16 + 0j, 1 + 1j, -1e16 + 0j]),
        masters=np.arange(3),
        background=np.zeros(3, complex),
        background_alpha=np.zeros(1, complex),
    )


def test_exact_product_and_sum_nonzero_complex_rhs():
    a = fixture()
    c = np.ones(3, complex)
    a["gp"] = np.array([0.7 + 0.2j])
    out, work = recover_ports(a, c)
    assert np.array_equal(out, decimal_ports(a, c))
    assert out[0] != (np.sum(a["dv"] * c) + a["gp"][0]) / a["H"][0]
    assert work["complex_products"] == 3
    with pytest.raises(ValueError, match="INPUT_INVALID"):
        recover_ports(dict(a, H=-a["H"]), c)


def test_checker_rejects_alpha_H_gp_missing_term_mode_and_background():
    a, c = fixture(), np.ones(3, complex)
    alpha, _ = recover_ports(a, c)
    state = dict(
        c_scattered=c,
        c_total=c.copy(),
        alpha_scattered=alpha,
        alpha_total=alpha.copy(),
        background=a["background"],
        background_alpha=a["background_alpha"],
        masters=a["masters"],
    )
    assert check_published(a, state, expected_mode_hash="frozen", mode_hash="frozen")[
        "passed"
    ]
    damaged = dict(state, alpha_scattered=alpha + 0.01, alpha_total=alpha + 0.01)
    assert not check_published(
        a, damaged, expected_mode_hash="frozen", mode_hash="frozen"
    )["passed"]
    for bad in (
        dict(a, H=a["H"] * 1.01),
        dict(a, gp=np.array([0.01j])),
        dict(a, dp=a["dp"][1:], dr=a["dr"][1:], dv=a["dv"][1:]),
    ):
        assert not check_published(
            bad, state, expected_mode_hash="frozen", mode_hash="frozen"
        )["passed"]
    with pytest.raises(ValueError, match="MODE_IDENTITY"):
        check_published(a, state, expected_mode_hash="frozen", mode_hash="wrong")
    with pytest.raises(ValueError, match="BACKGROUND"):
        check_published(
            dict(a, background=a["background"] + 0.01j),
            state,
            expected_mode_hash="frozen",
            mode_hash="frozen",
        )


def test_joint_qualification_rejects_missing_or_proxy_flux():
    from src.test.test_fixed_phase_contract import valid
    from benchmarks.fixed_phase_checker import qualification

    r = valid()
    r["details"]["zero_carrier_old_rhs_relative"] = 0.0
    flux = dict(
        channels=36,
        physical_E_cross_H=True,
        independent_Poynting_vs_port_max_absolute=0.0,
        all_mode_vs_analytic_max_absolute=0.0,
        reflected=0.0,
        transmitted=1.0,
        energy_closure=0.0,
        per_mode_physical_power=[0.0] * 36,
        per_mode_analytic_power=[0.0] * 36,
    )
    r["details"]["plane"] = [
        dict(z_sign=s, physical_flux=copy.deepcopy(flux)) for s in (-1, 1)
    ]
    assert qualification(r, joint_ports=True)["passed"]
    del r["details"]["plane"][0]["physical_flux"]
    assert not qualification(r, joint_ports=True)["passed"]


def test_frozen_severely_cancelled_real_ports():
    root = Path(__file__).resolve().parents[2]
    index = json.loads(
        (
            root / "docs/task042extra_feinn_5nm/outcomes/records/run_index_v20.json"
        ).read_text()
    )
    for role in ("O3", "E3"):
        row = next(
            r
            for r in index["runs"]
            if r["role"] == role
            and any(v["path"].endswith("field_state.npz") for v in r["artifacts"])
        )
        paths = {Path(v["path"]).name: root / v["path"] for v in row["artifacts"]}
        with np.load(paths["native.npz"], allow_pickle=False) as z:
            a = {k: np.array(z[k]) for k in ("H", "dp", "dr", "dv", "gp")}
        with np.load(paths["field_state.npz"], allow_pickle=False) as z:
            c = np.array(z["c_scattered"])
        out, _ = recover_ports(a, c)
        assert np.array_equal(out, decimal_ports(a, c, precision=90))
        assert np.array_equal(out, decimal_ports(a, c, precision=110))


def test_actual_audit_does_not_replace_saved_alpha():
    from src.test.test_feinn_p5_condensation import synthetic
    from src.solvers.accurate_ports import actual_vector_audit

    p = synthetic()
    c = np.ones(p.size, complex)
    alpha, _ = recover_ports(p.a, c)
    first = actual_vector_audit(p, c, alpha)
    p.alpha = lambda *_: (_ for _ in ()).throw(AssertionError("hidden replacement"))
    damaged = actual_vector_audit(p, c, alpha + 0.1j)
    assert damaged["augmented_relative"] != first["augmented_relative"]
    assert damaged["actual_output_used"] and not damaged["port_replaced_during_audit"]


def test_held_factor_correction_reduces_the_original_complex_system():
    from src.test.test_feinn_p5_condensation import synthetic
    from src.solvers.feinn_exact_condensation import ExactInteriorCondensation

    p = synthetic()
    reduced = ExactInteriorCondensation(p, [2])
    M, _ = reduced.assemble()
    rng = np.random.default_rng(422108)
    body = rng.normal(size=p.size) + 1j * rng.normal(size=p.size)
    port = rng.normal(size=p.np) + 1j * rng.normal(size=p.np)
    rhs, ui = reduced.correction_rhs(body, port)
    c, a = reduced.recover_correction(np.linalg.solve(M.toarray(), rhs), ui)
    np.testing.assert_allclose(p.volume(c) + p.B(a), body, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(-p.D(c) + p.a["H"] * a, port, rtol=1e-12, atol=1e-12)


def test_review_v21_explicit_roles_and_phase_p4_degree():
    from src.io.fixed_phase_pilot import STAGES, ROOT
    from src.io.feinn_pilot import load_pilot

    for name in STAGES:
        if name.startswith("v21_"):
            spec = load_pilot(ROOT / "input/task042extra_feinn_5nm" / (name + ".dat"))
            assert spec.derived["campaign_version"] == 21
            assert spec.derived["neural_training_allowed"] is False
            if name == "v21_e4":
                assert spec.discretization["degree"] == 4


def test_actual_launch_gate_rejects_proxy_even_with_passed_flag(monkeypatch, tmp_path):
    import hashlib
    import json
    from src.runners import fixed_phase_campaign as campaign
    from src.test.test_fixed_phase_contract import _joint_fixture

    bad = _joint_fixture()
    bad["stage_qualified"] = True
    for plane in bad["base"]["details"]["plane"]:
        del plane["physical_flux"]["physical_E_cross_H"]
    raw = tmp_path / "result.json"
    raw.write_text(json.dumps(bad))
    index = dict(
        source_sha="fixture",
        result=bad,
        files=dict(
            result=dict(
                path=str(raw), sha256=hashlib.sha256(raw.read_bytes()).hexdigest()
            )
        ),
    )
    (tmp_path / "index_v21_joint_qualification_attempt3.json").write_text(
        json.dumps(index)
    )
    monkeypatch.setattr(campaign, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(campaign, "selected", lambda stage: dict(result=bad))
    for stage in ("v21_o6", "v21_saved_p3_recovery"):
        with pytest.raises(
            RuntimeError, match="ROLE_COMPLETE.*physical_flux_missing_or_proxy"
        ):
            campaign.v21_admission(stage, [])
