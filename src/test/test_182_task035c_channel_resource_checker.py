from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.task035c_channel_resource_checker import (
    Task035cEvidenceError,
    build_task035c_channel_resource_check,
)


SOURCE_SHA = "1" * 40


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _orders() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    significant_index = 0
    for side in ("bottom", "top"):
        for m in range(-10, 10):
            for polarization in ("s", "p"):
                significant = polarization == "s" and -10 <= m <= -5
                power = (
                    1.0e-4 * (significant_index + 1)
                    if significant
                    else 1.0e-12
                )
                if significant:
                    significant_index += 1
                amplitude = [power**0.5, -0.25 * power**0.5]
                rows.append(
                    {
                        "side": side,
                        "m": m,
                        "n": 0,
                        "polarization": polarization,
                        "power_ratio": power,
                        "outgoing_amplitude": amplitude,
                        "direction": (
                            "outgoing_down" if side == "bottom" else "outgoing_up"
                        ),
                        "medium": "substrate" if side == "bottom" else "air",
                        "order_m": m,
                        "order_n": 0,
                        "vertical_sign": -1 if side == "bottom" else 1,
                        "propagating": True,
                        "power_carrying": True,
                        "rayleigh_warning": False,
                    }
                )
    assert len(rows) == 80
    assert sum(row["power_ratio"] >= 1.0e-8 for row in rows) == 12
    return rows


def _source() -> dict[str, Any]:
    return {
        "commit_sha": SOURCE_SHA,
        "verified_clean_sha": SOURCE_SHA,
        "head_before_sha": SOURCE_SHA,
        "head_after_sha": SOURCE_SHA,
        "tracked_source_dirty": False,
        "source_clean_verified": True,
        "source_stable_during_run": True,
        "stable_and_clean_after": True,
    }


def _make_full(tmp_path: Path) -> tuple[Path, str, list[dict[str, Any]]]:
    run_directory = tmp_path / "full_raw"
    orders = _orders()
    _write_json(run_directory / "orders.json", {"orders": orders})
    summary = {
        "stage_case": "stage4_block_grating",
        "geometry_kind": "rectangular_block_grating",
        "mpi_size": 8,
        "stage4_full3d_assembly_backend_actual": "assembly_time_static_condensed",
        "dtn_port_orders_json": "orders.json",
        "config": {
            "stage4_boundary_model": "dtn_port",
            "stage4_dtn_order_policy": "auto_propagating",
            "scattering_background": "layered",
            "use_floquet_xy": True,
            "polarization_kind": "s",
            "nedelec_degree": 2,
            "mesh_target_size": 5.0,
            "lambda0": 13.5,
            "incident_theta_deg": 80.0,
            "stage4_full3d_assembly_backend": (
                "assembly_time_static_condensed"
            ),
        },
    }
    summary_path = run_directory / "run_summary.json"
    summary_sha = _write_json(summary_path, summary)
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "status": "ordinary_status_must_not_drive_checker",
        "degree": 2,
        "h_nm": 5.0,
        "mpi_size": 8,
        "stage4_full3d_assembly_backend_requested": (
            "assembly_time_static_condensed"
        ),
        "stage4_full3d_assembly_backend_actual": (
            "assembly_time_static_condensed"
        ),
        "source": _source(),
        "raw_evidence": {
            "run_directory": str(run_directory),
            "solver_summary": str(summary_path),
        },
        "solver_summary_sha256": summary_sha,
        "solver_summary": summary,
    }
    record_path = tmp_path / "full_watchdog.json"
    return record_path, _write_json(record_path, record), orders


def _make_hybrid(
    tmp_path: Path,
    full_path: Path,
    full_sha: str,
    orders: list[dict[str, Any]],
    *,
    backend: str = "assembly_time_static_condensed",
    source_sha: str = SOURCE_SHA,
    modes: int = 120,
    peak_bytes: int = 2_000_000_000,
    total_seconds: float = 40.0,
    modal_seconds: float = 10.0,
    label: str = "primary",
) -> tuple[Path, str]:
    case = {
        "material_kind": "stage4_xy",
        "degree": 2,
        "h_nm": 5.0,
        "modal_degree": 2,
        "modal_h_nm": 5.0,
        "requested_modes_per_direction": modes,
        "wavelength_nm": 13.5,
        "incident_grazing_deg": 10.0,
        "polarization_kind": "s",
        "internal_propagation_model": "full3d_uniform_cg",
        "internal_traction_model": "scalar_cg_discrete_derivative",
    }
    metadata = {
        "commit_sha": source_sha,
        "verified_clean_sha": source_sha,
        "source_commit_at_end_full_sha": source_sha,
        "source_clean_and_stable": True,
        "tracked_source_dirty": False,
        "mpi_size": 8,
        "stage4_full3d_assembly_backend_requested": backend,
    }
    rows = 20_000 if backend == "standard_full" else 10_000
    nnz = 2_000_000 if backend == "standard_full" else 800_000
    system = {
        "assembly_backend_requested": backend,
        "bottom_assembly_backend_actual": backend,
        "top_assembly_backend_actual": backend,
        "bottom_global_size": rows // 2,
        "top_global_size": rows // 2,
        "internal_unknown_count": 200,
        "bottom_matrix_stats": {"matrix_nnz_used": nnz // 2},
        "top_matrix_stats": {"matrix_nnz_used": nnz // 2},
    }
    timings = {
        "total": total_seconds,
        "internal_modal_coupling": modal_seconds,
    }
    raw = {
        "status": "raw_status_must_not_drive_checker",
        "case": case,
        "metadata": metadata,
        "hybrid_system": system,
        "validation": {"external_diffraction_orders": orders},
        "timing_seconds_max_rank": timings,
        "full3d_reference_comparison": {
            "reference_file": str(full_path),
            "reference_commit_sha": source_sha,
        },
    }
    raw_path = tmp_path / f"{label}_raw_solver.json"
    raw_sha = _write_json(raw_path, raw)
    source = _source()
    for name in (
        "commit_sha",
        "verified_clean_sha",
        "head_before_sha",
        "head_after_sha",
    ):
        source[name] = source_sha
    record = {
        "schema_version": "task033.memory-watchdog.v2",
        "status": "ordinary_status_must_not_drive_checker",
        "numeric_pass": False,
        "formal_pass": False,
        "source": source,
        "solver_record_ignored_path": str(raw_path),
        "solver_record_sha256": raw_sha,
        "measurements": {
            "case": case,
            "validation": {"external_diffraction_orders": orders},
            "timing_seconds_max_rank": timings,
        },
        "resource_authority": {
            "simultaneous_live_worker_rss_sum_bytes": peak_bytes,
            "container_cgroup_current_bytes": 0,
            "memory_authority_bytes": peak_bytes,
            "memory_authority_gib": peak_bytes / 1024**3,
            "job_cgroup_dedicated": False,
        },
        "launch_gate": {
            "full3d_reference_expected_sha256": full_sha,
            "full3d_reference_observed_sha256": full_sha,
        },
    }
    path = tmp_path / f"{label}_hybrid_watchdog.json"
    return path, _write_json(path, record)


def _make_reference(
    tmp_path: Path,
    orders: list[dict[str, Any]],
    *,
    fail_first_power: bool = False,
) -> tuple[Path, str]:
    significant = [row for row in orders if row["power_ratio"] >= 1.0e-8]
    channels = []
    for index, row in enumerate(significant):
        side = row["side"]
        prefix = "R" if side == "top" else "T"
        power = row["power_ratio"] + (1.0e-5 if index == 0 and fail_first_power else 0.0)
        channels.append(
            {
                "channel": {
                    "label": f"{prefix}({row['m']},{row['n']})_{row['polarization']}",
                    "side": side,
                    "m": row["m"],
                    "n": row["n"],
                    "polarization": row["polarization"],
                },
                "analytic_identity": {
                    name: row[name]
                    for name in (
                        "side",
                        "direction",
                        "medium",
                        "m",
                        "n",
                        "order_m",
                        "order_n",
                        "polarization",
                        "vertical_sign",
                        "propagating",
                        "power_carrying",
                        "rayleigh_warning",
                    )
                },
                "reference_center": {
                    "power": power,
                    "complex_amplitude": row["outgoing_amplitude"],
                },
                "unchanged_v0_acceptance_gate": {
                    "power_absolute_tolerance": 1.0e-9,
                    "complex_amplitude_absolute_tolerance": 1.0e-9,
                    "uses_numerical_convergence_band": False,
                    "uses_h15_or_fixed_diagnostics": False,
                    "unchanged_v0_formula_verified": True,
                },
            }
        )
    payload = {
        "schema_version": "task035b.significant-channel-reference.v1",
        "status": "significant_channel_reference_v1_frozen",
        "pass": True,
        "mechanical_validation_pass": True,
        "authority_manifest": {"mechanically_validated": True},
        "significant_channel_selection": {
            "channel_count": 12,
            "significant_power_floor": 1.0e-8,
        },
        "channels": channels,
    }
    path = tmp_path / "significant_reference.json"
    return path, _write_json(path, payload)


def _base_evidence(tmp_path: Path) -> dict[str, Any]:
    full_path, full_sha, orders = _make_full(tmp_path)
    hybrid_path, hybrid_sha = _make_hybrid(
        tmp_path,
        full_path,
        full_sha,
        copy.deepcopy(orders),
    )
    return {
        "full_path": full_path,
        "full_sha": full_sha,
        "orders": orders,
        "hybrid_path": hybrid_path,
        "hybrid_sha": hybrid_sha,
    }


def _build_args(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "full3d_record": evidence["full_path"],
        "full3d_sha256": evidence["full_sha"],
        "hybrid_record": evidence["hybrid_path"],
        "hybrid_sha256": evidence["hybrid_sha"],
        "expected_source_sha": SOURCE_SHA,
        "expected_modes": 120,
        "gate_kind": "p2-diagnosis",
    }


def test_p2_gate_is_recomputed_from_raw_orders_not_input_status(tmp_path: Path) -> None:
    evidence = _base_evidence(tmp_path)
    result = build_task035c_channel_resource_check(**_build_args(evidence))

    assert result["pass"] is True
    assert result["full3d_vs_hybrid"]["power_pass_count"] == 12
    assert result["full3d_vs_hybrid"]["complex_amplitude_pass_count"] == 12
    assert result["identity"]["order_coverage"] == 80
    assert result["input_status_advisory_only"]["hybrid_watchdog_formal_pass"] is False
    assert result["input_status_advisory_only"]["hybrid_watchdog_numeric_pass"] is False
    assert result["resource_recomputed"]["hybrid"]["peak_memory_bytes"] == 2_000_000_000
    assert result["resource_recomputed"]["hybrid"]["total_seconds_max_rank"] == 40.0


def test_hash_mismatch_fails_closed_and_raw_channel_change_fails_gate(
    tmp_path: Path,
) -> None:
    evidence = _base_evidence(tmp_path)
    args = _build_args(evidence)
    with pytest.raises(Task035cEvidenceError, match="SHA-256 mismatch"):
        build_task035c_channel_resource_check(
            **{**args, "hybrid_sha256": "0" * 64}
        )

    hybrid_record = json.loads(evidence["hybrid_path"].read_text(encoding="utf-8"))
    raw_path = Path(hybrid_record["solver_record_ignored_path"])
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["validation"]["external_diffraction_orders"][0]["power_ratio"] *= 2.0
    hybrid_record["measurements"]["validation"] = copy.deepcopy(raw["validation"])
    hybrid_record["solver_record_sha256"] = _write_json(raw_path, raw)
    evidence["hybrid_sha"] = _write_json(evidence["hybrid_path"], hybrid_record)

    result = build_task035c_channel_resource_check(**_build_args(evidence))
    assert result["pass"] is False
    assert result["full3d_vs_hybrid"]["power_pass_count"] == 11
    assert result["full3d_vs_hybrid"]["complex_amplitude_pass_count"] == 12


def test_p6_absolute_v1_gate_is_separate_from_relative_p2_gate(tmp_path: Path) -> None:
    evidence = _base_evidence(tmp_path)
    reference_path, reference_sha = _make_reference(
        tmp_path,
        evidence["orders"],
        fail_first_power=True,
    )
    args = {
        **_build_args(evidence),
        "gate_kind": "p6-formal",
        "significant_channel_reference": reference_path,
        "significant_channel_reference_sha256": reference_sha,
    }
    result = build_task035c_channel_resource_check(**args)

    assert result["full3d_vs_hybrid"]["pass"] is True
    assert result["p2_diagnosis_gate"]["evaluated"] is False
    assert result["p6_formal_gate"]["evaluated"] is True
    assert result["p6_formal_gate"]["absolute_comparison"]["full3d_power_pass_count"] == 11
    assert result["p6_formal_gate"]["absolute_comparison"]["hybrid_power_pass_count"] == 11
    assert result["pass"] is False

    with pytest.raises(Task035cEvidenceError, match="requires significant channel"):
        build_task035c_channel_resource_check(
            **{
                **_build_args(evidence),
                "gate_kind": "p6-formal",
            }
        )


def test_same_m_standard_static_pair_resource_deltas_and_identity(tmp_path: Path) -> None:
    evidence = _base_evidence(tmp_path)
    standard_path, standard_sha = _make_hybrid(
        tmp_path,
        evidence["full_path"],
        evidence["full_sha"],
        copy.deepcopy(evidence["orders"]),
        backend="standard_full",
        peak_bytes=4_000_000_000,
        total_seconds=50.0,
        modal_seconds=20.0,
        label="standard",
    )
    result = build_task035c_channel_resource_check(
        **_build_args(evidence),
        paired_hybrid_record=standard_path,
        paired_hybrid_sha256=standard_sha,
    )
    pair = result["same_m_backend_pair"]
    assert pair["authoritative_same_source_same_case_pair"] is True
    assert pair["recomputed_deltas"]["memory_saving_fraction"] == pytest.approx(0.5)
    assert pair["recomputed_deltas"]["static_to_standard_total_time_ratio"] == 0.8
    assert (
        pair["recomputed_deltas"]["static_to_standard_modal_coupling_time_ratio"]
        == 0.5
    )

    other_source_path, other_source_sha = _make_hybrid(
        tmp_path,
        evidence["full_path"],
        evidence["full_sha"],
        copy.deepcopy(evidence["orders"]),
        backend="standard_full",
        source_sha="2" * 40,
        label="other_source_standard",
    )
    diagnostic = build_task035c_channel_resource_check(
        **_build_args(evidence),
        paired_hybrid_record=other_source_path,
        paired_hybrid_sha256=other_source_sha,
    )
    assert (
        diagnostic["same_m_backend_pair"][
            "authoritative_same_source_same_case_pair"
        ]
        is False
    )
    assert (
        diagnostic["same_m_backend_pair"]["identity_checks"]["same_source_sha"]
        is False
    )
