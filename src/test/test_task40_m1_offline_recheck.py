"""Small positive and negative fixtures for the saved M1 checker."""

import json
from pathlib import Path

import numpy as np

from benchmarks.check_task40_g0_m1_offline_v1 import (
    _residual_audit,
    _resource_cleanup_pass,
    _saved_channel_checks,
)


def _write_channels(output_dir: Path, mode_count: int = 180):
    modes = []
    orders = []
    amplitudes = []
    for index in range(mode_count):
        side = "top" if index < mode_count // 2 else "bottom"
        local = index % (mode_count // 2)
        mode = {
            "side": side,
            "m": local // 6,
            "n": local % 6 // 2 - 1,
            "polarization": "s" if local % 2 == 0 else "p",
        }
        modes.append(mode)
        outgoing = [0.5, 0.0]
        orders.append(
            {
                **mode,
                "auxiliary_amplitude_total_projection": [1.0, 0.0],
                "incident_projection": [0.5, 0.0],
                "outgoing_amplitude": outgoing,
                "outgoing_amplitude_at_boundary": outgoing,
                "modal_power_code_units": 1.0 / mode_count,
                "power_ratio": 1.0 / mode_count,
                "R": 0.4 / mode_count,
                "T": 0.6 / mode_count,
            }
        )
        amplitudes.append(
            {
                **mode,
                "auxiliary_amplitude_total_projection": [1.0, 0.0],
                "incident_projection": [0.5, 0.0],
                "outgoing_amplitude": outgoing,
                "outgoing_amplitude_at_boundary": outgoing,
            }
        )
    (output_dir / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps({"orders": orders, "metrics": {"incident_power_code_units": 1.0}}),
        encoding="utf-8",
    )
    (output_dir / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes), encoding="utf-8"
    )
    return modes, orders, amplitudes


def _run_saved_channel_check(output_dir: Path, modes):
    solver = {
        "status": "TRUE_RESIDUAL_PASS",
        "final_true_residual": 1.0e-8,
        "final_evaluation": {
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 0.0,
            "schur_port_identity_relative": 0.0,
        },
    }
    return _saved_channel_checks(
        modes,
        output_dir,
        {
            "R_total": 0.4,
            "T_total": 0.6,
            "A_balance": 0.0,
            "R_plus_T": 1.0,
            "incident_power_code_units": 1.0,
        },
        {"A_volume_total": 0.0},
        electric_finite=True,
        auxiliary_finite=True,
        field_export={"max_abs_H": 1.0, "curl_postprocess_success": True},
        solver_facts=solver,
        post_release_relative=1.0e-8,
    )


def test_m1_offline_adapter_uses_all_180_manifest_modes(tmp_path):
    modes, _, _ = _write_channels(tmp_path)

    checks, facts = _run_saved_channel_check(tmp_path, modes)

    assert facts["channel_facts"]["expected_count"] == 180
    assert facts["channel_facts"]["checked_count"] == 180
    assert all(facts["channel_checks"].values())
    assert all(checks.values())


def test_m1_offline_adapter_rejects_a_missing_saved_mode(tmp_path):
    modes, orders, amplitudes = _write_channels(tmp_path)
    (tmp_path / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps(
            {"orders": orders[:-1], "metrics": {"incident_power_code_units": 1.0}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes[:-1]), encoding="utf-8"
    )

    checks, facts = _run_saved_channel_check(tmp_path, modes)

    assert facts["channel_facts"]["expected_count"] == 180
    assert facts["channel_checks"]["files"] is False
    assert checks["channel_files"] is False


def test_offline_residual_is_recomputed_from_saved_rhs_and_action():
    arrays = {
        "rhs": np.asarray([3.0 + 0.0j, 4.0 + 0.0j]),
        "applied": np.asarray([2.0 + 0.0j, 4.0 + 0.0j]),
        "residual": np.asarray([1.0 + 0.0j, 0.0 + 0.0j]),
    }
    packet = {
        "rhs": {"array_key": "rhs"},
        "applied": {"array_key": "applied"},
        "residual": {"array_key": "residual"},
        "explicit_relative_residual": 0.2,
    }

    audit = _residual_audit(packet, arrays)

    assert audit["recomputed_norm_b_minus_Ax_over_b"] == 0.2
    assert audit["residual_vector_consistent"] is True
    assert audit["recomputed_matches_packet"] is True
    assert audit["residual_gate"] is False


def test_offline_residual_rejects_a_packet_vector_that_disagrees():
    arrays = {
        "rhs": np.asarray([3.0 + 0.0j, 4.0 + 0.0j]),
        "applied": np.asarray([2.0 + 0.0j, 4.0 + 0.0j]),
        "residual": np.asarray([0.0 + 0.0j, 1.0 + 0.0j]),
    }
    packet = {
        "rhs": {"array_key": "rhs"},
        "applied": {"array_key": "applied"},
        "residual": {"array_key": "residual"},
        "explicit_relative_residual": 0.2,
    }

    audit = _residual_audit(packet, arrays)

    assert audit["residual_vector_consistent"] is False
    assert audit["recomputed_matches_packet"] is True


def test_offline_resource_gate_requires_zero_swap_and_cleared_children():
    watchdog = {
        "sampled_process_tree_swap_peak_bytes": 0,
        "descendants_cleared": True,
        "remaining_child_pids": [],
    }
    qualification = {
        "status": "qualified_zero",
        "process_tree_peak_swap_bytes": 0,
        "process_tree_all_status_readable": True,
        "process_tree_identity_coverage": "complete",
    }

    assert _resource_cleanup_pass(watchdog, qualification) is True
    assert _resource_cleanup_pass(
        {**watchdog, "sampled_process_tree_swap_peak_bytes": 4096}, qualification
    ) is False
    assert _resource_cleanup_pass(
        {**watchdog, "descendants_cleared": False}, qualification
    ) is False
