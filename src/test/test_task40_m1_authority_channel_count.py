"""Regression coverage for M1's expanded port-mode inventory."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.physical_p4_schur_v14 import _v21_authority_limited_checks


def _write_mode_outputs(output_dir, mode_count):
    modes = []
    orders = []
    amplitudes = []
    for index in range(mode_count):
        side = "top" if index < mode_count // 2 else "bottom"
        local_index = index % (mode_count // 2)
        mode = SimpleNamespace(
            side=side,
            m=local_index // 2,
            n=0,
            polarization="s" if local_index % 2 == 0 else "p",
        )
        modes.append(mode)
        row = {
            "side": mode.side,
            "m": mode.m,
            "n": mode.n,
            "polarization": mode.polarization,
            "auxiliary_amplitude_total_projection": [1.0, 0.0],
            "incident_projection": [0.5, 0.0],
            "outgoing_amplitude": [0.5, 0.0],
            "outgoing_amplitude_at_boundary": [0.5, 0.0],
            "modal_power_code_units": 1.0 / mode_count,
            "power_ratio": 1.0 / mode_count,
            "R": 0.4 / mode_count,
            "T": 0.6 / mode_count,
        }
        orders.append(row)
        amplitudes.append(
            {
                key: row[key]
                for key in (
                    "side",
                    "m",
                    "n",
                    "polarization",
                    "auxiliary_amplitude_total_projection",
                    "incident_projection",
                    "outgoing_amplitude",
                    "outgoing_amplitude_at_boundary",
                )
            }
        )

    (output_dir / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps(
            {
                "orders": orders,
                "metrics": {"incident_power_code_units": 1.0},
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes), encoding="utf-8"
    )
    common = {"fine": {"modes": modes}}
    output = {
        "port_metrics": {
            "R_total": 0.4,
            "T_total": 0.6,
            "A_balance": 0.0,
            "R_plus_T": 1.0,
            "incident_power_code_units": 1.0,
        },
        "volume_metrics": {"A_volume_total": 0.0},
        "electric_finite": True,
        "auxiliary_finite": True,
        "auxiliary": np.full(mode_count, 0.5 + 0.0j),
        "field_export": {
            "max_abs_H": 1.0,
            "curl_postprocess_success": True,
        },
    }
    return common, output, orders, amplitudes


@pytest.mark.parametrize("mode_count", [80, 180])
def test_authority_channel_gate_uses_live_mode_count(tmp_path, mode_count):
    common, output, _orders, _amplitudes = _write_mode_outputs(
        tmp_path, mode_count
    )
    solver_facts = {
        "status": "TRUE_RESIDUAL_PASS",
        "final_true_residual": 1.0e-8,
        "final_evaluation": {
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 0.0,
            "schur_port_identity_relative": 0.0,
        },
    }

    checks, facts = _v21_authority_limited_checks(
        solver_facts,
        output,
        post_release_relative=1.0e-8,
        common=common,
        output_dir=tmp_path,
    )

    assert facts["channel_facts"]["expected_count"] == mode_count
    assert facts["channel_facts"]["checked_count"] == mode_count
    assert all(facts["channel_checks"].values())
    assert all(checks.values())


def test_authority_channel_gate_rejects_a_dropped_m1_mode(tmp_path):
    common, output, orders, amplitudes = _write_mode_outputs(tmp_path, 180)
    (tmp_path / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps(
            {
                "orders": orders[:-1],
                "metrics": {"incident_power_code_units": 1.0},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes[:-1]), encoding="utf-8"
    )
    solver_facts = {
        "status": "TRUE_RESIDUAL_PASS",
        "final_true_residual": 1.0e-8,
        "final_evaluation": {
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 0.0,
            "schur_port_identity_relative": 0.0,
        },
    }

    checks, facts = _v21_authority_limited_checks(
        solver_facts,
        output,
        post_release_relative=1.0e-8,
        common=common,
        output_dir=tmp_path,
    )

    assert facts["channel_facts"]["expected_count"] == 180
    assert facts["channel_checks"]["files"] is False
    assert checks["channel_files"] is False
