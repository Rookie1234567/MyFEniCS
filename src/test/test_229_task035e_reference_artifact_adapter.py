from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task035e_reference_certify import (
    H5FactorizationDecisionInput,
    ReferenceArtifactError,
    WatchdogRecordInput,
    adapt_watchdog_reference,
    build_reference_campaign_from_watchdogs,
    main,
)
from src.adaptivity.reference_certifier import (
    QUALIFIED,
    REFERENCE_CERTIFICATION_INCOMPLETE,
    ReferenceCertifier,
)


SOURCE_SHA = "6" * 40
H5_FACTORIZATION_SCHEMA = "task035e.h5-factorization-launch-authority.v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _config(h_nm: float) -> dict[str, object]:
    k0 = 2.0 * np.pi / 13.5
    return {
        "case_name": f"task035e_p6_h{h_nm:g}",
        "geometry_kind": "rectangular_block_grating",
        "stage_case": "stage4_block_grating",
        "period_x": 50.0,
        "period_y": 25.0,
        "x_min": 0.0,
        "x_max": 50.0,
        "y_min": 0.0,
        "y_max": 25.0,
        "z_min": -10.0,
        "z_max": 130.0,
        "physical_z_min": 0.0,
        "physical_z_max": 120.0,
        "air_height": 130.0,
        "substrate_thickness": 10.0,
        "grating_height": 120.0,
        "grating_width_x": 17.0,
        "grating_width_y": 25.0,
        "grating_bounds": [0.0, 17.0, 0.0, 25.0, 0.0, 120.0],
        "interface_z": 0.0,
        "use_pml": False,
        "pml_top_thickness": 0.0,
        "pml_bottom_thickness": 0.0,
        "lambda0": 13.5,
        "n_air": [1.0, 0.0],
        "n_grating": [0.999, 0.0018],
        "n_substrate": [0.999, 0.0018],
        "eps_air": [1.0, 0.0],
        "eps_grating": [0.998, 0.0036],
        "eps_substrate": [0.998, 0.0036],
        "mu_r": [1.0, 0.0],
        "grating_material_label": "Si",
        "substrate_material_label": "Si",
        "incident_theta_deg": 80.0,
        "incident_phi_deg": 0.0,
        "polarization_kind": "s",
        "incident_amplitude": [1.0, 0.0],
        "incident_e0_v_per_m": 1.0,
        "propagation_direction": [0.984807753, 0.0, -0.173648178],
        "wavevector": [float(k0 * 0.984807753), 0.0, float(-k0 * 0.173648178)],
        "scattering_background": "layered",
        "stage4_boundary_model": "dtn_port",
        "stage4_dtn_order_policy": "auto_propagating",
        "stage4_dtn_assembly": "auxiliary",
        "stage4_pml_outer_bc": "natural",
        "use_floquet_xy": True,
        "floquet_phase_x": [0.5, 0.0],
        "floquet_phase_y": [1.0, 0.0],
        "diffraction_zero_order_only": False,
        "diffraction_order_max_m": None,
        "diffraction_order_max_n": None,
        "diffraction_rayleigh_tol": 1.0e-6,
        "full3d_reference_export": True,
        "full3d_reference_plane_z": [10.0, 30.0, 60.0, 90.0, 110.0],
        "full3d_reference_sample_count_x": 2,
        "full3d_reference_sample_count_y": 2,
        "diffraction_sample_count_x": 32,
        "diffraction_sample_count_y": 32,
        "diffraction_probe_fraction": 0.75,
        "electric_field_unit": "V/m",
        "magnetic_field_unit": "A/m",
        "mesh_target_size": h_nm,
        "mesh_cells": int(1000.0 / h_nm),
        "mesh_axis_cell_counts": [5, 3, int(140.0 / h_nm)],
        "nedelec_degree": 6,
        "k0": float(k0),
    }


def _config_authority(config: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "task035e.reference-config-authority.v1",
        "mpi_size": 8,
        "config": config,
    }
    return {
        "schema_version": payload["schema_version"],
        "sha256": _canonical_sha(payload),
        "payload": payload,
    }


def _smooth(center: float, coefficient: float, h_nm: float) -> float:
    return center + coefficient * h_nm**2


def _write_completed(
    root: Path,
    h_nm: float,
    *,
    missing_order: bool = False,
    incident_phi_deg: float = 0.0,
    include_extra_spectrum_order: bool = False,
    resolved_public_backend: bool = False,
) -> WatchdogRecordInput:
    run_dir = root / f"h{h_nm:g}"
    run_dir.mkdir()
    config = _config(h_nm)
    config["incident_phi_deg"] = incident_phi_deg
    if resolved_public_backend:
        config.update(
            {
                "stage4_full3d_assembly_backend": (
                    "assembly_time_static_condensed"
                ),
                "stage4_cell_static_condensation": False,
                "stage4_assembly_time_cell_static_condensation": False,
                "stage4_floquet_slave_elimination": False,
            }
        )
    orders = []
    top_total = 0.0
    bottom_total = 0.0
    r00_s = 0.0
    r00_p = 0.0
    order_pairs = [(m, 0) for m in (0, -1, -2, -3, -4, -5, -6, -7)]
    if include_extra_spectrum_order:
        order_pairs.append((-2, 1))
    for port_index, port in enumerate(("top", "bottom")):
        for m, n in order_pairs:
            for polarization in ("s", "p"):
                if missing_order and (port, m, polarization) == ("bottom", -7, "p"):
                    continue
                index = port_index * 8 - m + 1
                if polarization == "s":
                    power = _smooth(1.0e-5 * index, 1.0e-10 * index, h_nm)
                    amplitude = complex(
                        _smooth(0.01 * index, 1.0e-7 * index, h_nm),
                        _smooth(-0.005 * index, -5.0e-8 * index, h_nm),
                    )
                else:
                    power = _smooth(1.0e-9 * index, 1.0e-14 * index, h_nm)
                    amplitude = complex(
                        _smooth(1.0e-4 * index, 1.0e-9 * index, h_nm),
                        _smooth(2.0e-4 * index, 2.0e-9 * index, h_nm),
                    )
                if port == "top":
                    top_total += power
                    if m == 0 and polarization == "s":
                        r00_s = power
                    if m == 0 and polarization == "p":
                        r00_p = power
                else:
                    bottom_total += power
                beta = 0.2 + 0.01 * (-m)
                orders.append(
                    {
                        "side": port,
                        "m": m,
                        "n": n,
                        "polarization": polarization,
                        "propagating": True,
                        "power_carrying": True,
                        "kz": [beta if port == "top" else -beta, 0.0],
                        "beta": [beta, 0.0],
                        "outgoing_amplitude_at_boundary": [
                            amplitude.real,
                            amplitude.imag,
                        ],
                        "power_ratio": power,
                    }
                )
    a_volume = 1.0 - top_total - bottom_total
    dtn = {
        "metrics": {
            "power_source": "dtn_port_modal_amplitudes",
            "diffraction_total_power_source": "dtn_port_modal_amplitudes",
            "stage4_dtn_assembly": "auxiliary",
            "stage4_dtn_order_policy": "auto_propagating",
            "dtn_port_modal_amplitude_convention": "boundary amplitude",
            "R00_s": r00_s,
            "R00_p": r00_p,
            "R00_total": r00_s + r00_p,
            "R_total": top_total,
            "T_total": bottom_total,
        },
        "orders": orders,
    }
    dtn_path = run_dir / "dtn_port_diffraction_orders_3d.json"
    _write_json(dtn_path, dtn)

    volume = {
        "method": "volume_absorption",
        "status": "ok",
        "power_source": "volume_integral_Im_epsilon_E2",
        "A_volume_total": a_volume,
        "A_volume_grating": 0.8 * a_volume,
        "A_volume_substrate": 0.2 * a_volume,
        "energy_closure_error_port_volume": 0.0,
    }
    volume_path = run_dir / "volume_absorption.json"
    _write_json(volume_path, volume)

    x = np.asarray([12.5, 37.5])
    y = np.asarray([6.25, 18.75])
    z = np.asarray([10.0, 30.0, 60.0, 90.0, 110.0])
    shape = (5, 2, 2, 3)
    base = np.arange(np.prod(shape), dtype=float).reshape(shape) + 1.0
    e = (
        0.01 * base
        + 1j * 0.005 * base
        + h_nm**2 * (1.0e-7 + 2.0e-7j)
    )
    h_field = (
        0.001 * base
        - 1j * 0.0005 * base
        + h_nm**2 * (1.0e-8 - 2.0e-8j)
    )
    archive_path = run_dir / "full3d_reference_samples.npz"
    np.savez(
        archive_path,
        x_nm=x,
        y_nm=y,
        z_nm=z,
        E_V_per_m=e,
        H_A_per_m=h_field,
        interface_z_nm=z[[0, 4]],
        E_t_interface_V_per_m=e[[0, 4], :, :, :2],
        H_t_interface_A_per_m=h_field[[0, 4], :, :, :2],
    )
    archive_sha = _sha(archive_path)
    metadata = {
        "schema_version": 1,
        "archive": archive_path.name,
        "archive_sha256": archive_sha,
        "archive_bytes": archive_path.stat().st_size,
        "array_shape_z_y_x_component": list(shape),
        "point_count": 20,
        "grid_convention": "periodic-cell-centered-x-y; exact-requested-z",
        "interface_plane_indices": [0, 4],
        "middle_plane_indices": [1, 2, 3],
        "components": ["x", "y", "z"],
        "tangential_components": ["x", "y"],
        "electric_field_unit": "V/m",
        "magnetic_field_unit": "A/m",
    }
    metadata_path = run_dir / "full3d_reference_samples.json"
    _write_json(metadata_path, metadata)

    runtime_config = dict(config)
    if resolved_public_backend:
        runtime_config.update(
            {
                "stage4_cell_static_condensation": True,
                "stage4_assembly_time_cell_static_condensation": True,
                "stage4_floquet_slave_elimination": True,
            }
        )
    summary = {
        "config": runtime_config,
        "case_status": "completed",
        "official_result": True,
        "diagnostic_only": False,
        "postprocess_skipped": False,
        "nedelec_degree": 6,
        "polarization_kind": "s",
        "mpi_size": 8,
        "stage4_full3d_assembly_backend_actual": (
            "assembly_time_static_condensed"
        ),
        "stage4_assembly_time_cell_static_condensation": True,
        "stage4_full3d_assembly_backend_qualification": {
            "status": "qualified"
        },
        "cell_static_condensation": {
            "full_global_matrix_allocated": False
        },
        "linear_solve_method": "direct_lu",
        "selected_parallel_lu_solver_type": "mumps",
        "actual_ksp_type": "preonly",
        "actual_pc_type": "lu",
        "actual_pc_factor_solver_type": "mumps",
        "linear_solve_petsc_options": {
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
        },
        "ksp_converged": True,
        "full3d_reference_exported": True,
        "full3d_reference_archive": str(archive_path),
        "full3d_reference_archive_sha256": archive_sha,
        "full3d_reference_archive_bytes": archive_path.stat().st_size,
        "dtn_port_orders_json": dtn_path.name,
        "volume_absorption_file": volume_path.name,
        "R00_s": r00_s,
        "R00_p": r00_p,
        "R00_total": r00_s + r00_p,
        "R_total": top_total,
        "T_total": bottom_total,
        "A_balance": a_volume,
        "A_volume_total": a_volume,
        "linear_system_relative_residual": _smooth(
            1.0e-12, 1.0e-16, h_nm
        ),
    }
    summary_path = run_dir / "run_summary.json"
    _write_json(summary_path, summary)
    live_gate = {
        "pass": True,
        "controlled_resource_stop": False,
        "stop_reason": None,
        "minimum_mem_available_bytes": 40,
        "maximum_swap_authority_bytes": 0,
        "zero_swap_every_sample": True,
        "minimum_headroom_20_percent_preserved": True,
        "policy": {"mem_total_bytes": 100},
    }
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "status": "task035e_reference_full_solve_pass",
        "degree": 6,
        "h_nm": h_nm,
        "polarization_kind": "s",
        "run_kind": "full-solve",
        "mpi_size": 8,
        "profile": "default",
        "stage4_full3d_assembly_backend_requested": (
            "assembly_time_static_condensed"
        ),
        "stage4_full3d_assembly_backend_actual": (
            "assembly_time_static_condensed"
        ),
        "source": {
            "commit_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
            "status_after": "",
        },
        "task035e_reference_certifier": {
            "schema_version": "task035e.reference-resource-authority.v1",
            "selected": True,
            "config_authority": _config_authority(config),
            "lifecycle_authority": {
                "pass": True,
                "checks": {"static": True, "direct": True},
            },
            "live_resource_gate": live_gate,
        },
        "qualification": {"pass": True, "failures": []},
        "controlled_resource_stop": False,
        "no_swap": True,
        "solver_summary_sha256": _sha(summary_path),
        "dtn_orders_sha256": _sha(dtn_path),
        "volume_absorption_sha256": _sha(volume_path),
        "reference_metadata_sha256": _sha(metadata_path),
        "raw_evidence": {
            "run_directory": str(run_dir),
            "solver_summary": str(summary_path),
            "dtn_orders": str(dtn_path),
            "volume_absorption": str(volume_path),
            "reference_metadata": str(metadata_path),
        },
        "solver_summary": summary,
    }
    record_path = run_dir / "watchdog_summary.json"
    _write_json(record_path, record)
    return WatchdogRecordInput(record_path, _sha(record_path))


def _write_controlled_h5(root: Path) -> WatchdogRecordInput:
    run_dir = root / "h5-stop"
    run_dir.mkdir()
    config = _config(5.0)
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "status": "controlled_resource_stop",
        "degree": 6,
        "h_nm": 5.0,
        "polarization_kind": "s",
        "run_kind": "assembly-only",
        "mpi_size": 8,
        "profile": "default",
        "stage4_full3d_assembly_backend_requested": (
            "assembly_time_static_condensed"
        ),
        "source": {
            "commit_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
            "status_after": "",
        },
        "task035e_reference_certifier": {
            "schema_version": "task035e.reference-resource-authority.v1",
            "selected": True,
            "config_authority": _config_authority(config),
            "live_resource_gate": {
                "pass": False,
                "controlled_resource_stop": True,
                "stop_reason": "memavailable_below_20_percent",
                "minimum_mem_available_bytes": 19,
                "maximum_swap_authority_bytes": 0,
                "policy": {"mem_total_bytes": 100},
            },
        },
        "controlled_resource_stop": True,
        "raw_evidence": {"run_directory": str(run_dir)},
    }
    path = run_dir / "watchdog_summary.json"
    _write_json(path, record)
    return WatchdogRecordInput(path, _sha(path))


def _write_h5_prelaunch_deny(
    root: Path,
    *,
    h10: WatchdogRecordInput,
    h7p5: WatchdogRecordInput,
) -> H5FactorizationDecisionInput:
    h5_completed = _write_completed(root, 5.0)
    assembly_record = json.loads(
        h5_completed.path.read_text(encoding="utf-8")
    )
    assembly_record.update(
        {
            "status": "task035e_reference_assembly_resource_pass",
            "run_kind": "assembly-only",
            "controlled_resource_stop": False,
            "no_swap": True,
            "qualification": {"pass": True, "failures": []},
        }
    )
    task035e = assembly_record["task035e_reference_certifier"]
    task035e["credit"] = "resource_only_not_physics"
    _write_json(h5_completed.path, assembly_record)
    assembly_sha = _sha(h5_completed.path)
    config_sha = task035e["config_authority"]["sha256"]

    issued_at = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    payload: dict[str, object] = {
        "schema_version": H5_FACTORIZATION_SCHEMA,
        "authority_role": "resource_launch_decision_only",
        "credit": "no_pde_no_accuracy_no_reference_qualification_credit",
        "issued_at_utc": issued_at.isoformat(),
        "expires_at_utc": (issued_at + timedelta(minutes=15)).isoformat(),
        "validity_seconds": 15 * 60,
        "campaign_identity": {
            "source_sha": SOURCE_SHA,
            "physical_config_sha256": "9" * 64,
            "h5_config_authority_sha256": config_sha,
        },
        "target": {
            "degree": 6,
            "h_nm": 5.0,
            "run_kind_to_authorize": "full-solve",
            "factor_solver": "mumps",
            "mpi_size": 8,
            "assembly_backend": "assembly_time_static_condensed",
            "profile": "default",
        },
        "input_records": {
            "h10_full": {
                "path": str(h10.path),
                "expected_sha256": h10.sha256,
                "observed_sha256": h10.sha256,
            },
            "h7p5_full": {
                "path": str(h7p5.path),
                "expected_sha256": h7p5.sha256,
                "observed_sha256": h7p5.sha256,
            },
            "h5_assembly": {
                "path": str(h5_completed.path),
                "expected_sha256": assembly_sha,
                "observed_sha256": assembly_sha,
            },
        },
        "identity_checks": {
            "same_clean_source": True,
            "same_physical_config_except_mesh_h": True,
        },
        "prediction": {
            "solver_peak_bytes_interval": {
                "lower": 70,
                "central": 90,
                "upper": 110,
            }
        },
        "live_memory": {
            "mem_total_bytes": 100,
            "mem_available_bytes": 80,
            "swap_used_bytes": 0,
            "effective_job_cap_bytes": 100,
        },
        "gate": {
            "launch_allowed": False,
            "predicted_upper_below_dynamic_cap": False,
            "zero_swap_at_decision": True,
            "minimum_20_percent_headroom_available": True,
            "failures": [
                "predicted_solver_peak_upper_not_below_dynamic_cap"
            ],
            "deny_is_controlled_resource_stop": True,
            "launch_semantics": "single immediate h5 full-solve launch only",
        },
    }
    decision = {
        "schema_version": H5_FACTORIZATION_SCHEMA,
        "sha256": _canonical_sha(payload),
        "payload": payload,
    }
    decision_path = root / "h5_factorization_deny.json"
    _write_json(decision_path, decision)
    return H5FactorizationDecisionInput(decision_path, _sha(decision_path))


def test_adapter_builds_typed_qualified_campaign_and_field_vectors(
    tmp_path: Path,
) -> None:
    campaign = build_reference_campaign_from_watchdogs(
        h10=_write_completed(tmp_path, 10.0),
        h7p5=_write_completed(tmp_path, 7.5),
        h5=_write_completed(tmp_path, 5.0),
    )
    certification = ReferenceCertifier().certify(campaign)

    assert certification.status == QUALIFIED
    assert certification.qualified is True
    assert len(campaign.h5.diffraction_orders) == 16
    assert all(order.total_power is not None for order in campaign.h5.diffraction_orders)
    interface = [
        row
        for row in campaign.h5.complex_observations
        if row.category == "interface_field"
    ]
    volume = [
        row
        for row in campaign.h5.complex_observations
        if row.category == "volume_field"
    ]
    assert len(interface) == 32
    assert len(volume) == 72


def test_adapter_normalizes_public_backend_runtime_flags(
    tmp_path: Path,
) -> None:
    run = adapt_watchdog_reference(
        _write_completed(
            tmp_path,
            10.0,
            resolved_public_backend=True,
        ),
        expected_h_nm=10.0,
    )

    assert run.result.gate.completed is True


def test_adapter_preserves_all_propagating_spectrum_beyond_fixed_n8(
    tmp_path: Path,
) -> None:
    campaign = build_reference_campaign_from_watchdogs(
        h10=_write_completed(
            tmp_path,
            10.0,
            include_extra_spectrum_order=True,
        ),
        h7p5=_write_completed(
            tmp_path,
            7.5,
            include_extra_spectrum_order=True,
        ),
        h5=_write_completed(
            tmp_path,
            5.0,
            include_extra_spectrum_order=True,
        ),
    )
    certification = ReferenceCertifier().certify(campaign)

    assert certification.qualified is True
    assert len(campaign.h5.diffraction_orders) == 18
    assert {
        row.identity
        for row in campaign.h5.diffraction_orders
        if row.n == 1
    } == {("top", -2, 1), ("bottom", -2, 1)}
    assert any(
        row.output_id == "order/top/m-2/n1/total_power"
        for row in certification.convergence
    )


def test_adapter_rejects_tamper_and_missing_fixed_order(tmp_path: Path) -> None:
    tampered = _write_completed(tmp_path, 10.0)
    dtn = tampered.path.parent / "dtn_port_diffraction_orders_3d.json"
    dtn.write_text(dtn.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ReferenceArtifactError, match="SHA-256 mismatch"):
        adapt_watchdog_reference(tampered, expected_h_nm=10.0)

    missing = _write_completed(tmp_path, 7.5, missing_order=True)
    with pytest.raises(ReferenceArtifactError, match="missing fixed DtN"):
        adapt_watchdog_reference(missing, expected_h_nm=7.5)


@pytest.mark.parametrize(
    ("filename", "label"),
    [
        ("volume_absorption.json", "volume absorption"),
        ("full3d_reference_samples.json", "reference metadata"),
    ],
)
def test_adapter_rejects_tampered_newly_frozen_artifacts(
    tmp_path: Path,
    filename: str,
    label: str,
) -> None:
    record = _write_completed(tmp_path, 10.0)
    artifact = record.path.parent / filename
    artifact.write_text(
        artifact.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(ReferenceArtifactError, match=rf"{label} SHA-256 mismatch"):
        adapt_watchdog_reference(record, expected_h_nm=10.0)


def test_adapter_rejects_cross_point_physical_identity_drift(
    tmp_path: Path,
) -> None:
    with pytest.raises(ReferenceArtifactError, match="configs differ"):
        build_reference_campaign_from_watchdogs(
            h10=_write_completed(tmp_path, 10.0),
            h7p5=_write_completed(tmp_path, 7.5, incident_phi_deg=1.0),
            h5=_write_completed(tmp_path, 5.0),
        )


def test_h5_controlled_stop_is_incomplete_not_pass(tmp_path: Path) -> None:
    campaign = build_reference_campaign_from_watchdogs(
        h10=_write_completed(tmp_path, 10.0),
        h7p5=_write_completed(tmp_path, 7.5),
        h5=_write_controlled_h5(tmp_path),
    )
    certification = ReferenceCertifier().certify(campaign)

    assert campaign.h5.gate.controlled_resource_stop is True
    assert campaign.h5.gate.completed is False
    assert certification.status == REFERENCE_CERTIFICATION_INCOMPLETE
    assert certification.qualified is False
    assert "h5p0_controlled_resource_stop" in certification.reasons


def test_h5_prelaunch_deny_is_sealable_controlled_resource_stop(
    tmp_path: Path,
) -> None:
    h10 = _write_completed(tmp_path, 10.0)
    h7p5 = _write_completed(tmp_path, 7.5)
    decision = _write_h5_prelaunch_deny(
        tmp_path,
        h10=h10,
        h7p5=h7p5,
    )
    campaign = build_reference_campaign_from_watchdogs(
        h10=h10,
        h7p5=h7p5,
        h5=decision,
    )
    certification = ReferenceCertifier().certify(campaign)

    assert campaign.h5.gate.controlled_resource_stop is True
    assert campaign.h5.gate.completed is False
    assert campaign.h5.scalar_observations == ()
    assert campaign.h5.complex_observations == ()
    assert campaign.h5.diffraction_orders == ()
    assert certification.status == REFERENCE_CERTIFICATION_INCOMPLETE
    assert certification.qualified is False
    assert "h5p0_controlled_resource_stop" in certification.reasons

    sealed = tmp_path / "factor-deny-incomplete.json"
    status = main(
        [
            "--h10-record",
            str(h10.path),
            "--h10-record-sha256",
            h10.sha256,
            "--h7p5-record",
            str(h7p5.path),
            "--h7p5-record-sha256",
            h7p5.sha256,
            "--h5-factorization-decision",
            str(decision.path),
            "--h5-factorization-decision-sha256",
            decision.sha256,
            "--sealed-package",
            str(sealed),
            "--seal-incomplete-evidence",
        ]
    )
    assert status == 3
    assert sealed.is_file()


def test_h5_prelaunch_deny_rejects_different_supplied_coarse_record(
    tmp_path: Path,
) -> None:
    h10 = _write_completed(tmp_path, 10.0)
    h7p5 = _write_completed(tmp_path, 7.5)
    decision = _write_h5_prelaunch_deny(
        tmp_path,
        h10=h10,
        h7p5=h7p5,
    )
    alternate_root = tmp_path / "alternate"
    alternate_root.mkdir()
    alternate_h10 = _write_completed(alternate_root, 10.0)

    with pytest.raises(
        ReferenceArtifactError,
        match="does not bind supplied h10_full",
    ):
        build_reference_campaign_from_watchdogs(
            h10=alternate_h10,
            h7p5=h7p5,
            h5=decision,
        )


def _certify_cli(
    records: tuple[WatchdogRecordInput, WatchdogRecordInput, WatchdogRecordInput],
    *extra: str,
) -> list[str]:
    h10, h7p5, h5 = records
    return [
        "--h10-record",
        str(h10.path),
        "--h10-record-sha256",
        h10.sha256,
        "--h7p5-record",
        str(h7p5.path),
        "--h7p5-record-sha256",
        h7p5.sha256,
        "--h5-record",
        str(h5.path),
        "--h5-record-sha256",
        h5.sha256,
        *extra,
    ]


def test_cli_incomplete_requires_opt_in_and_always_exits_nonzero(
    tmp_path: Path,
) -> None:
    records = (
        _write_completed(tmp_path, 10.0),
        _write_completed(tmp_path, 7.5),
        _write_controlled_h5(tmp_path),
    )
    default_package = tmp_path / "default-incomplete.json"
    status = main(
        _certify_cli(
            records,
            "--sealed-package",
            str(default_package),
        )
    )
    assert status == 3
    assert not default_package.exists()

    explicit_package = tmp_path / "explicit-incomplete.json"
    explicit_status = main(
        _certify_cli(
            records,
            "--sealed-package",
            str(explicit_package),
            "--seal-incomplete-evidence",
        )
    )
    assert explicit_status == 3
    assert explicit_package.is_file()
