"""Bounded pure contracts for the explicitly reviewed representation batch."""

import json
import os
from pathlib import Path
import sys
import pytest

from benchmarks.fixed_phase_checker import LIMITS, qualification, solved
from src.geometry.fixed_phase_plan import axes, physical_design, fixture_design
from src.io.feinn_pilot import load_pilot
from src.io.input_loader import InputError

ROOT = Path(__file__).resolve().parents[2]


def valid():
    return dict(
        schema="fixed_phase.qualification.v1",
        gates={k: v / 2 for k, v in LIMITS.items()},
        details=dict(
            ky=0.12,
            all_dof_families={"1": 36, "2": 72, "3": 36},
            negative_controls=dict(
                omitted_curl_difference=0.4,
                double_phase_difference=0.5,
                omitted_internal_rhs_difference=0.6,
                incorrect_physical_ports_difference=0.7,
                old_background_difference=0.4,
            ),
            no_producer_F_read_in_physical_audit=True,
            identity=dict(
                modes=[
                    dict(side=side, m=m, n=n, polarization=pol)
                    for side in ("top", "bottom")
                    for m in range(-1, 2)
                    for n in range(-1, 2)
                    for pol in ("s", "p")
                ]
            ),
        ),
    )


def test_exact_mesh_and_physics_identity():
    for mesh, expected, degree, dofs in (
        ("G0", (6, 4, 14), 3, 27648),
        ("GX560", (10, 4, 14), 6, 365760),
    ):
        d = physical_design(mesh)
        assert tuple(d["geometry"]["cells"]) == expected
        assert tuple(len(a) - 1 for a in axes(mesh)) == expected
        nx, ny, nz = expected
        assert 3 * nx * ny * nz * degree**3 + 2 * nx * ny * degree**2 == dofs
        assert d["boundary"]["channels"] == 340
        assert d["wavelength_nm"] == 0.7
    assert fixture_design()["geometry"]["cells"] == [2, 2, 2]
    assert fixture_design()["incidence"]["azimuth_deg"] != 0


def test_checker_complete_joint_gate():
    assert qualification(valid())["passed"]
    for key in LIMITS:
        r = valid()
        del r["gates"][key]
        assert not qualification(r)["passed"]
        r = valid()
        r["gates"][key] = LIMITS[key] * 1.01
        assert key in qualification(r)["failed"]


@pytest.mark.parametrize(
    "failure",
    [
        "omitted_curl",
        "double_phase",
        "internal_rhs",
        "nan",
        "empty_family",
        "false_independence",
    ],
)
def test_dangerous_record_rejected(failure):
    r = valid()
    if failure in ("omitted_curl", "double_phase", "internal_rhs"):
        name = dict(
            omitted_curl="omitted_curl_difference",
            double_phase="double_phase_difference",
            internal_rhs="omitted_internal_rhs_difference",
        )[failure]
        r["details"]["negative_controls"][name] = 0
    elif failure == "nan":
        r["gates"]["physical_volume"] = float("nan")
    elif failure == "empty_family":
        r["details"]["all_dof_families"]["3"] = 0
    else:
        r["details"]["no_producer_F_read_in_physical_audit"] = False
    assert not qualification(r)["passed"]


def test_missing_port_or_original_equation_rejected():
    r = dict(
        native_relative=1e-12,
        augmented_relative=1e-12,
        original_total_augmented_relative=1e-12,
        independent_physical_weak=1e-12,
        recovery=1e-12,
        channels=340,
        full_FE_recovered=True,
    )
    assert solved(r, reference=True)["passed"]
    for k, v in (
        ("channels", 338),
        ("full_FE_recovered", False),
        ("independent_physical_weak", 2e-6),
    ):
        z = dict(r)
        z[k] = v
        assert not solved(z)["passed"]


def test_explicit_input_and_no_training(tmp_path):
    path = ROOT / "input/task042extra_feinn_5nm/v20_e3.dat"
    spec = load_pilot(path)
    assert spec.method["kind"] == "research_fixed_phase_FE"
    assert spec.derived["neural_training_allowed"] is False
    bad = tmp_path / "bad.dat"
    bad.write_text(
        path.read_text().replace(
            "neural_training_allowed = false", "neural_training_allowed = true"
        )
    )
    with pytest.raises(InputError):
        load_pilot(bad)
    assert "torch" not in sys.modules


def test_identity_guard_refuses_foreign_root(tmp_path):
    from benchmarks.subreaper_watchdog import supervise

    with pytest.raises(RuntimeError, match="identity changed"):
        supervise(
            [sys.executable, "-c", "pass"],
            tmp_path / "never",
            wall_seconds=5,
            sampled_root_identity=dict(pid=os.getpid(), start_ticks=-1),
        )
    assert not (tmp_path / "never").exists()


def test_design_fixture_is_frozen_in_input():
    d = json.loads((ROOT / "input/task042extra_feinn_5nm/design_v20.json").read_text())
    assert d["fixture"] == fixture_design()
    assert d["models"] == {m: physical_design(m) for m in ("G0", "GX560")}


def test_unrun_e4_descriptor_binds_p4_without_changing_frozen_g0():
    spec = load_pilot(ROOT / "input/task042extra_feinn_5nm/v20_e4.dat")
    assert spec.discretization["degree"] == 4
    assert spec.derived["role"] == "E4"
    assert physical_design("G0")["finite_element"] == {
        "family": "N1curl",
        "quadrature_degree": 15,
    }


def test_corrupt_modes_background_and_physical_wavenumber():
    for name in ("incorrect_physical_ports_difference", "old_background_difference"):
        r = valid()
        r["details"]["negative_controls"][name] = 0
        assert not qualification(r)["passed"]
    r = valid()
    r["details"]["identity"]["modes"].pop()
    assert not qualification(r)["passed"]
    r = valid()
    r["details"]["identity"]["modes"][0] = {}
    assert not qualification(r)["passed"]
    r = valid()
    r["gates"]["physical_rhs"] = False
    assert not qualification(r)["passed"]


def _saved_physics_fixture():
    import numpy as np

    keys = np.asarray(
        [
            [s, str(m), str(n), p]
            for s in ("top", "bottom")
            for m in range(-8, 9)
            for n in range(-2, 3)
            for p in ("s", "p")
        ]
    )
    waves = np.zeros((340, 3), complex)
    waves[:, 2] = np.where(keys[:, 0] == "top", 1, -1)
    e = np.tile([1, 0, 0], (340, 1)).astype(complex)
    a = np.zeros(340, complex)
    a[
        np.flatnonzero(
            (keys[:, 0] == "bottom")
            & (keys[:, 1] == "0")
            & (keys[:, 2] == "0")
            & (keys[:, 3] == "s")
        )[0]
    ] = 1
    field = np.asarray([[[1, 0, 0]]], complex)
    curl = np.asarray([[[0, 1j, 0]]], complex)
    power = abs(a) ** 2
    z = dict(
        quadrature_weights_nm3=np.ones((1, 1)),
        total_E=field,
        scattered_E=np.zeros_like(field),
        total_curl=curl,
        scattered_curl=np.zeros_like(curl),
        total_H=curl / 1j,
        scattered_H=np.zeros_like(curl),
        cell_epsilon=np.array([1 + 0j]),
        k0=np.array(1),
        mu_r=np.array(1),
        incident_power=np.array(0.5),
        port_area=np.array(1),
        mode_keys=keys,
        mode_k=waves,
        mode_e=e,
        mode_boundary_z=np.where(keys[:, 0] == "top", 1, -1).astype(float),
        outgoing_boundary=a,
        per_level_power=power,
        physical_field_norms=np.asarray([1, 1, 0, 0]),
    )
    return z


def test_saved_physical_arrays_recompute_power_and_reject_damage():
    import numpy as np
    from benchmarks.fixed_phase_checker import physics_from_arrays

    z = _saved_physics_fixture()
    curl = z["total_curl"]
    r = physics_from_arrays(z)
    assert (
        r["raw_valid"]
        and r["T_total"] == 1
        and r["R_total"] == 0
        and r["energy_closure"] == 0
    )
    damaged = dict(z, total_H=np.zeros_like(curl))
    assert not physics_from_arrays(damaged)["raw_valid"]
    damaged = dict(z, per_level_power=z["per_level_power"] + 0.01)
    assert not physics_from_arrays(damaged)["raw_valid"]
    damaged = dict(z, mode_keys=z["mode_keys"][:-1])
    with pytest.raises(ValueError, match="MODE_KEYS"):
        physics_from_arrays(damaged)


def test_partial_reference_and_finite_p_pair_are_not_full_accuracy():
    import numpy as np
    from benchmarks.fixed_phase_checker import compare_from_arrays

    empty = compare_from_arrays({}, {}, {})
    assert empty["coverage"] == "PARTIAL" and not empty["reference_qualified"]
    assert len(empty["missing_roles"]) == 4 and empty["comparisons"] == {}
    z = _saved_physics_fixture()
    for k in (
        "selected_total_E",
        "selected_total_H",
        "selected_scattered_E",
        "selected_scattered_H",
    ):
        z[k] = np.ones((6, 3), complex)
    for k in ("total_projection", "scattered_projection", "outgoing_origin"):
        z[k] = np.ones(340, complex)
    equations = {
        k: 0.0
        for k in (
            "native_relative",
            "augmented_relative",
            "original_total_augmented_relative",
            "independent_physical_weak",
            "recovery",
        )
    }
    equations.update(channels=340, full_FE_recovered=True)
    first = np.zeros((6, 4, 3))
    first[:, :, 1:] = 1
    r = compare_from_arrays(
        {"E3_vs_E4_q15": first, "E3_vs_E4_q30": first.copy()},
        {"E3": z, "E4": z},
        {"E3": equations, "E4": equations},
    )
    assert r["coverage"] == "PARTIAL" and not r["reference_qualified"]
    assert r["comparisons"]["E3_vs_E4"]["qualified"]
    assert r["target_qualified"] is False
    with pytest.raises(ValueError, match="COVERAGE"):
        compare_from_arrays({}, {"E3": z}, {})
    with pytest.raises(ValueError, match="COVERAGE"):
        compare_from_arrays(
            {}, {"E3": z, "EXTRA": z}, {"E3": equations, "EXTRA": equations}
        )
    with pytest.raises(ValueError, match="COVERAGE"):
        compare_from_arrays({}, {"E3": z, "E4": z}, {"E3": equations, "E4": equations})
