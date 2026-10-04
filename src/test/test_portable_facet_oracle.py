"""Minimal independent-oracle/layout/corruption fixtures; no native run."""

import json

import numpy as np
import pytest

from benchmarks.portable_facet_oracle import moments
from benchmarks.portable_facet_result_checker import check_arrays
from src.solvers.interval_facet_moments import unit_interval_moments
from src.solvers.local_facet_functionals import local_port_rows, port_direction_actions


@pytest.mark.parametrize("w", [0.0, 0.37, -0.37, 54.978, -54.978])
def test_independent_integer_integral(w):
    expected, _ = moments(w, 6, 80)
    other, _ = moments(w, 6, 110, direct_quadrature=True)
    assert np.max(abs(expected - other)) < 1e-14
    assert np.max(abs(unit_interval_moments(w, 6) - expected)) < 1e-12


def test_physical_normal_and_adjoint():
    rng = np.random.default_rng(41)
    integral = rng.normal(size=(5, 2)) + 1j * rng.normal(size=(5, 2))
    k = np.array([0.8, 0.3, 0.6])
    e = np.array([0.2, -0.7, 0.4])
    normal = np.array([0.0, 0.0, 1.0])
    B, D, H = local_port_rows(
        integral, k, e, normal, original_area=1250.0, reference_z=130.0
    )
    opposite, _, _ = local_port_rows(
        integral, k, e, -normal, original_area=1250.0, reference_z=-10.0
    )
    assert np.array_equal(opposite, -B)
    assert np.isclose(H, 1250.0 * (0.2**2 + 0.7**2))
    c = rng.normal(size=(3, 5)) + 1j * rng.normal(size=(3, 5))
    load = np.array([0.7 + 0.2j])
    a = port_direction_actions(B[None, :], D[None, :], np.array([H]), c, load)
    assert abs(np.vdot(a["forward"][:, 0], load) - np.vdot(c[0], a["adjoint"])) < 1e-12


def test_persisted_checker_rejects_corrupt_projection(tmp_path):
    rng = np.random.default_rng(42)
    ref = {}
    actual = {}
    ref["moment_oracle110"] = np.zeros((2, 7), complex)
    actual["moment_values"] = ref["moment_oracle110"].copy()
    for p in (4, 6):
        B = rng.normal(size=(2, 4)) + 1j * rng.normal(size=(2, 4))
        D = B * 0.3j
        H = np.array([4.0, 5.0])
        c = rng.normal(size=(3, 4)) + 1j * rng.normal(size=(3, 4))
        load = np.array([0.1j, 0.3])
        ref.update(
            {
                f"p{p}_B": B,
                f"p{p}_D": D,
                f"p{p}_H": H,
                f"p{p}_directions": c,
                f"p{p}_load": load,
            }
        )
        actual.update(
            {
                f"p{p}_B": B,
                f"p{p}_D": D,
                f"p{p}_H": H,
                **{
                    f"p{p}_{k}": v
                    for k, v in port_direction_actions(B, D, H, c, load).items()
                },
            }
        )
    a, b = tmp_path / "actual.npz", tmp_path / "ref.npz"
    np.savez(a, **actual)
    np.savez(b, **ref)
    assert check_arrays(a, b)["passed"]
    actual["p6_projection"][0, 0] += 0.01
    np.savez(a, **actual)
    assert not check_arrays(a, b)["passed"]


def test_v23_real_input_workflow_dispatch(monkeypatch):
    from src.io.feinn_pilot import load_pilot
    from src.runners.feinn_workflow import launch
    import src.runners.fixed_phase_campaign as campaign

    monkeypatch.setattr(campaign, "launch", lambda s: s.derived["campaign_version"])
    for stage in (
        "admission_audit",
        "facet_qualification",
        "analytic_cold",
        "q60_cold",
    ):
        s = load_pilot("input/task042extra_feinn_5nm/v23_" + stage + ".dat")
        assert s.execution["terminate_memory_gib"] == 2
        assert launch(s) == 23
    with open("input/task042extra_feinn_5nm/facet_component_v23.json") as f:
        assert json.load(f)["degrees"] == [4, 6]
