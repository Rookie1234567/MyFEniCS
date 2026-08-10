from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import run_task033_full3d_watchdog as watchdog
from benchmarks.task037c_robustness import direction_s_phase_audit


SHA40 = "a" * 40
SHA64 = "b" * 64


def _task37c_argv() -> list[str]:
    return [
        "--task037c-robustness-gate",
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--incident-grazing-deg",
        "1",
        "--incident-phi-deg",
        "-5",
        "--task035c-p6-preflight-authority",
        "authority.json",
        "--task035c-p6-preflight-sha256",
        SHA64,
        "--verified-clean-sha",
        SHA40,
    ]


def test_task37c_parser_config_and_worker_argv(tmp_path: Path) -> None:
    args = watchdog._parse_args(_task37c_argv())
    assert args.task037c_robustness_gate is True
    assert args.task035c_p6_h10_gate is False
    cfg = watchdog._full3d_config(args)
    assert cfg.incident_theta_deg == 89.0
    assert cfg.incident_phi_deg == -5.0
    assert cfg.polarization_kind == "s"
    command = watchdog._worker_command(args, tmp_path / "run")
    assert "--task037c-robustness-gate" in command
    assert "--incident-grazing-deg" in command
    assert "--incident-phi-deg" in command
    assert "--task035c-p6-preflight-authority" in command
    assert "--task035c-p6-h10-gate" not in command


def test_task035c_parser_lane_remains_separate() -> None:
    args = watchdog._parse_args(
        [
            "--degree",
            "6",
            "--h-nm",
            "10",
            "--polarization-kind",
            "s",
            "--run-kind",
            "full-solve",
            "--mpi-size",
            "8",
            "--profile",
            "default",
            "--stage4-full3d-assembly-backend",
            "assembly_time_static_condensed",
            "--task035c-p6-h10-gate",
            "--task035c-p6-preflight-authority",
            "authority.json",
            "--task035c-p6-preflight-sha256",
            SHA64,
            "--verified-clean-sha",
            SHA40,
        ]
    )
    assert args.task035c_p6_h10_gate is True
    assert args.task037c_robustness_gate is False


def test_task37c_qualification_keeps_common_failures_and_is_json_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = watchdog._parse_args(_task37c_argv())
    expected = direction_s_phase_audit(-5.0)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    manifest_sha = watchdog._sha256(manifest)
    monkeypatch.setattr(
        watchdog,
        "_task037c_order_export_gate",
        lambda _path: {"pass": True, "count": 42},
    )
    monkeypatch.setattr(
        watchdog,
        "_task037c_reference_export_gate",
        lambda _summary, _run_dir: {"pass": True},
    )
    config = {
        "incident_theta_deg": 89.0,
        "incident_phi_deg": -5.0,
        "polarization_kind": "s",
        "nedelec_degree": 6,
        "mesh_target_size": 10.0,
        "propagation_direction": list(expected["direction"]),
        "polarization": [[value, 0.0] for value in expected["s_basis"]],
        "wavevector": [[expected["kx"], 0.0], [expected["ky"], 0.0], [0.0, 0.0]],
        "floquet_phase_x": [
            expected["floquet_phase_x"].real,
            expected["floquet_phase_x"].imag,
        ],
        "floquet_phase_y": [
            expected["floquet_phase_y"].real,
            expected["floquet_phase_y"].imag,
        ],
    }
    summary = {
        "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": 1},
        "polarization_kind": "s",
        "config": config,
        "case_status": "completed",
        "official_result": True,
        "ksp_converged": True,
        "linear_system_relative_residual": 1.0e-10,
        "R_total": 0.1,
        "T_total": 0.7,
        "A_balance": 0.2,
        "A_volume_total": 0.2,
        "energy_closure_error_port_volume": 0.0,
        "dtn_port_orders_json": "orders.json",
        "task037c_canonical_export": {
            "roles": {
                "active_trace": {
                    "manifest": "manifest.json",
                    "manifest_sha256": manifest_sha,
                },
                "full_fe": {
                    "manifest": "manifest.json",
                    "manifest_sha256": manifest_sha,
                },
            }
        },
    }
    result = watchdog._qualify(
        args=args,
        solver_summary=summary,
        run_dir=tmp_path,
        events=[],
        return_code=1,
        terminated_for_memory=True,
        terminated_for_timeout=True,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=7,
    )
    assert result["pass"] is False
    assert "process_completed" in result["failures"]
    assert "not_terminated_for_memory" in result["failures"]
    assert "all_expected_mpi_ranks_observed" in result["failures"]
    json.dumps(result)


def test_task37c_reference_export_missing_archive_fails_closed(tmp_path: Path) -> None:
    result = watchdog._task037c_reference_export_gate(
        {
            "full3d_reference_metadata": "missing_metadata.json",
            "full3d_reference_archive": "missing_archive.npz",
        },
        tmp_path,
    )
    assert result["pass"] is False


def test_task37c_auxiliary_export_gate_hash_counts_and_missing(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "side": "bottom",
            "m": 0,
            "n": 0,
            "polarization": "s",
            "beta": [1.0, 0.0],
            "auxiliary_amplitude_total_projection": [0.1, 0.0],
            "outgoing_amplitude": [0.1, 0.0],
            "outgoing_amplitude_at_boundary": [0.1, 0.0],
        },
        {
            "side": "top",
            "m": 0,
            "n": 0,
            "polarization": "s",
            "beta": [1.0, 0.0],
            "auxiliary_amplitude_total_projection": [0.2, 0.0],
            "outgoing_amplitude": [0.2, 0.0],
            "outgoing_amplitude_at_boundary": [0.2, 0.0],
        },
    ]
    path = tmp_path / "dtn_auxiliary_amplitudes_3d.json"
    path.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    result = watchdog._task037c_auxiliary_export_gate(
        {
            "dtn_auxiliary_amplitudes_file": path.name,
            "dtn_port_bottom_mode_count": 1,
            "dtn_port_top_mode_count": 1,
        },
        tmp_path,
        {"keys": [("bottom", 0, 0, "s"), ("top", 0, 0, "s")]},
    )
    assert result["pass"] is True
    assert result["checks"]["hash_available"] is True
    missing = watchdog._task037c_auxiliary_export_gate(
        {
            "dtn_auxiliary_amplitudes_file": "missing.json",
            "dtn_port_bottom_mode_count": 1,
            "dtn_port_top_mode_count": 1,
        },
        tmp_path,
        {"keys": []},
    )
    assert missing["pass"] is False


def test_task037c_order_export_gate_binds_descriptor_on_pass_and_failure(
    tmp_path: Path,
) -> None:
    rows = {
        "orders": [
            {
                "side": "bottom",
                "m": 0,
                "n": 0,
                "polarization": "s",
                "beta": [1.0, 0.0],
                "outgoing_amplitude": [1.0, 0.0],
                "outgoing_amplitude_at_boundary": [1.0, 0.0],
                "power_ratio": 0.5,
                "R": 0.5,
                "T": 0.5,
            }
        ]
    }
    path = tmp_path / "orders.json"
    path.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    result = watchdog._task037c_order_export_gate(path)
    assert result["pass"] is True
    assert result["path"] == str(path.resolve())
    assert result["observed_sha256"] == watchdog._sha256(path)
    assert result["bytes"] == path.stat().st_size

    rows["orders"][0]["beta"] = [float("nan"), 0.0]
    path.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    failed = watchdog._task037c_order_export_gate(path)
    assert failed["pass"] is False
    assert failed["path"] == str(path.resolve())
    assert failed["observed_sha256"] == watchdog._sha256(path)
    assert failed["bytes"] == path.stat().st_size
