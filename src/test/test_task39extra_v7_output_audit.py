"""Pure algebra and saved-output contracts; no mesh, factor or PDE."""

import json
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.v7_n0_output_audit import (
    grouped_powers,
    saved_output_observation,
    truncation_action_observation,
    validate_n0_keys,
    y_variation_observation,
)


def modes():
    return [
        {"side": side, "m": m, "n": 0, "polarization": pol}
        for side in ("bottom", "top")
        for m in range(-142, 1)
        for pol in ("s", "p")
    ]


def test_tail_action_uses_complex_dual_without_second_conjugation_and_correct_sign():
    rows = modes()
    entries = [
        SimpleNamespace(
            mode_identity=row,
            normalization_h=2.0,
            projection_rows=np.array([0, 2]),
            projection_values=np.array([1 + 2j, 3 - 1j]),
            coupling_rows=np.array([1]),
            coupling_values=np.array([2 - 3j]),
        )
        for row in rows
    ]
    u = np.array([1 + 3j, 0j, -2 + 1j])
    residual = np.array([0j, 1 + 1j, 0j])
    result = truncation_action_observation(
        modes=rows,
        entries=entries,
        solution=u,
        residual=residual,
        rhs_norm=2.0,
        incident_projections=[0j] * 572,
    )
    expected = 488 * (2 - 3j) * ((1 + 2j) * u[0] + (3 - 1j) * u[2]) / 2
    assert result["delta20"] == pytest.approx(abs(expected) / 2)
    assert result["b572_minus_A84_u572_relative"] == pytest.approx(
        abs(1 + 1j + expected) / 2
    )
    assert result["new_factor_calls"] == result["new_PDE_calls"] == 0
    assert np.array_equal(u, [1 + 3j, 0j, -2 + 1j])
    assert result["retained_A84_count"] == 84
    entries[0].mode_identity = rows[1]
    with pytest.raises(ValueError, match="ordering"):
        truncation_action_observation(
            modes=rows,
            entries=entries,
            solution=u,
            residual=residual,
            rhs_norm=2.0,
            incident_projections=[0j] * 572,
        )


@pytest.mark.parametrize("kind", ["missing_zero", "duplicate", "wrong_n", "wrong_side"])
def test_exact_inventory_rejects_wrong_truncations(kind):
    rows = modes()
    if kind == "missing_zero":
        rows = [row for row in rows if row["m"] != 0]
    if kind == "duplicate":
        rows[0] = deepcopy(rows[1])
    if kind == "wrong_n":
        rows[0]["n"] = 1
    if kind == "wrong_side":
        rows[0]["side"] = "left"
    with pytest.raises(ValueError, match="572"):
        validate_n0_keys(rows)


def test_power_groups_cover_all_channels_and_do_not_zero_fill_omitted_parent():
    rows = [
        dict(
            row,
            R=0.001 if row["side"] == "top" else 0,
            T=0.002 if row["side"] == "bottom" else 0,
            rayleigh_warning=row["m"] == -142,
        )
        for row in modes()
    ]
    result = grouped_powers(rows)
    assert sum(group["count"] for group in result["groups"].values()) == 572
    assert result["tail20_power"] == pytest.approx(244 * 0.003)
    assert result["groups"]["m0"]["count"] == result["groups"]["m_minus1"]["count"] == 4
    assert len(result["near_cutoff_modes"]) == 4
    rows[1]["R"] = float("nan")
    with pytest.raises(ValueError, match="powers"):
        grouped_powers(rows)


def test_y_complex_phase_changes_are_visible_and_cross_leakage_is_not_a_solve_gate():
    e = np.zeros((2, 4, 3, 3), complex)
    h = np.zeros_like(e)
    e[..., 1] = 1 + 2j
    h[..., 0] = 2 - 1j
    assert not y_variation_observation(e, h, [1, 5, 10, 20])["diagnostic_warning"]
    e[:, 1, :, 1] *= 1j
    result = y_variation_observation(e, h, [1, 5, 10, 20])
    assert result["E_sample_y_variation_relative"] > 0.1
    assert result["phase_fitting"] is False
    assert result["threshold_role"] == "diagnostic_warning_only"
    h[..., 1] = 1
    assert (
        y_variation_observation(e, h, [1, 5, 10, 20])["H_cross_polarization_relative"]
        > 0.1
    )
    with pytest.raises(ValueError):
        y_variation_observation(e[:, :2], h[:, :2], [1, 2])


def test_active_output_path_never_rebuilds_parent_diffraction(monkeypatch, tmp_path):
    from src.common import modes_3d
    from src.postprocessing import diffraction_3d, postprocess_3d, rta_3d
    from src.solvers import dtn_port_3d
    from src.solvers import fullspace_same_mesh_hcurl_pmg_physical as physical

    field = SimpleNamespace(x=SimpleNamespace(array=np.ones(3, complex)))
    monkeypatch.setattr(physical, "restore_p0_full_field", lambda *a, **k: field)
    monkeypatch.setattr(
        dtn_port_3d, "_port_power_metrics", lambda *a: {"R_total": 0.2, "T_total": 0.7}
    )
    monkeypatch.setattr(modes_3d, "incident_power_3d", lambda *a: 1.0)
    monkeypatch.setattr(
        postprocess_3d, "save_airbox_3d_fields", lambda *a: {"saved": True}
    )
    monkeypatch.setattr(
        rta_3d, "compute_volume_absorption_3d", lambda *a, **k: {"A_volume_total": 0.1}
    )

    def forbidden(*a, **k):
        raise AssertionError("full parent diffraction routine must not run for V7")

    monkeypatch.setattr(diffraction_3d, "compute_diffraction_orders_3d", forbidden)
    called = []
    monkeypatch.setattr(dtn_port_3d, "_write_port_outputs", lambda *a: called.append(a))
    bundle = {
        "setup": {
            "floquets": {6: object()},
            "mesh_data": SimpleNamespace(mesh=SimpleNamespace(comm=object())),
        },
        "cfg": object(),
        "modes": [SimpleNamespace(**row) for row in modes()],
        "incident_projections": [0j] * 572,
        "dtn_action": SimpleNamespace(
            recover_auxiliary=lambda u: np.zeros(572, complex)
        ),
    }
    output = physical.recover_p0_outputs(
        bundle,
        object(),
        tmp_path,
        export_all_port_modes=True,
        active_port_outputs_only=True,
    )
    assert len(called) == 1 and len(called[0][2]) == 572
    assert output["diffraction_channel_count"] == 572
    assert output["port_metrics"]["operator_scope"] == "A6_n0"
    assert output["diffraction_metrics"]["omitted_channel_values"] == "NOT_COMPUTED"


def test_saved_observation_checker_rejects_changed_tail_samples_and_curl(tmp_path):
    from benchmarks.v7_anisotropic_n0_checker import saved_observation_errors

    numerical = tmp_path / "numerical_output"
    numerical.mkdir()
    rows = [dict(row, R=0.0005, T=0.001) for row in modes()]
    (numerical / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps({"orders": rows})
    )
    fields = numerical / "fields.npz"
    e = np.zeros((2, 4, 3, 3), complex)
    h = np.zeros_like(e)
    e[..., 1] = 1 + 2j
    h[..., 0] = 3 - 4j
    np.savez(
        fields,
        x_nm=[1, 2, 3],
        y_nm=[1, 5, 10, 20],
        z_nm=[30, 60],
        E_V_per_m=e,
        H_A_per_m=h,
    )
    outputs = {"field_export": {"full3d_reference_archive": str(fields)}}
    cfg = SimpleNamespace(k0=2.0, mu_r=1.0, magnetic_field_scale_A_per_m=0.01)
    audit = saved_output_observation(numerical, outputs, cfg, {"delta20": 0.1})
    summary = {"v7_output_audit": audit, "official_result": outputs}
    assert not saved_observation_errors(tmp_path, summary)
    audit["power_groups"]["tail20_power"] = 0.0
    assert any(
        "power groups" in row for row in saved_observation_errors(tmp_path, summary)
    )
    audit["power_groups"] = grouped_powers(rows)
    audit["y_diagnostics"]["E_sample_y_variation_relative"] = 1.0
    assert any(
        "y diagnostics" in row for row in saved_observation_errors(tmp_path, summary)
    )
    audit["y_diagnostics"] = y_variation_observation(e, h, [1, 5, 10, 20])
    audit["curl_samples"]["sha256"] = "0" * 64
    assert any(
        "curl sample hash" in row for row in saved_observation_errors(tmp_path, summary)
    )


def test_checker_cli_accepts_scoped_v7_success(monkeypatch, tmp_path):
    from benchmarks import physical_intermediate_checker as checker

    monkeypatch.setattr(
        checker,
        "check",
        lambda _: {
            "classification": "ANISOTROPIC_N0_DISCRETE_PASS_AUTHORITY_LIMITED",
            "gate_failures": [],
        },
    )
    assert checker.main([str(tmp_path)]) == 0
