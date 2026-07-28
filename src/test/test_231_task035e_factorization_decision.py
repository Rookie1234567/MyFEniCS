from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import benchmarks.task035e_factorization_decision as decision
from benchmarks.task035e_factorization_decision import (
    AUTHORITY_SCHEMA,
    FactorizationDecisionError,
    build_factorization_decision,
    main,
    write_authority_exclusive,
)


GIB = 1024**3
SOURCE_SHA = "7" * 40


def _json_sha(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_authority(h_nm: float, *, material: str = "silicon") -> dict[str, object]:
    config: dict[str, object] = {
        "case_name": f"task035e_p6_h{h_nm:g}",
        "mesh_target_size": h_nm,
        "mesh_cells": int(100000 / h_nm),
        "mesh_axis_cell_counts": [5, 3, int(140 / h_nm)],
        "geometry_kind": "rectangular_block_grating",
        "material": material,
        "wavelength_nm": 13.5,
        "polarization_kind": "s",
        "stage4_boundary_model": "dtn_port",
        "full3d_reference_export": True,
    }
    payload: dict[str, object] = {
        "schema_version": "task035e.reference-config-authority.v1",
        "mpi_size": 8,
        "config": config,
    }
    return {
        "schema_version": payload["schema_version"],
        "sha256": _json_sha(payload),
        "payload": payload,
    }


def _lifecycle() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "task035e.reference-lifecycle-authority.v1",
        "comparison_anchor": "Task035c p6/h10 Full3D static MPI8",
        "assembly_backend": "assembly_time_static_condensed",
        "petsc_direct_solver_profile": "default",
        "selected_parallel_lu_solver_type": "mumps",
        "petsc_extra_options": {},
        "mumps_icntl_overrides": {},
        "direct_release_base_after_augmentation": False,
        "direct_release_solver_before_postprocess": False,
        "full3d_reference_plane_z_nm": [10.0, 30.0, 60.0, 90.0, 110.0],
        "full3d_reference_sample_count_x": 40,
        "full3d_reference_sample_count_y": 20,
    }
    checks = {
        "static_backend_actual": True,
        "default_direct_profile": True,
        "direct_mumps_selected": True,
        "no_mumps_icntl_drift": True,
        "task035c_lifecycle_match": True,
        "live_resource_gate": True,
        "assembly_resource_authority": True,
    }
    return {
        **payload,
        "sha256": _json_sha(payload),
        "checks": checks,
        "pass": True,
    }


def _live_gate() -> dict[str, object]:
    total = 512 * GIB
    available = 470 * GIB
    headroom = int(0.2 * total)
    cap = min(int(0.8 * total), available - headroom)
    return {
        "schema_version": "task035e.reference-live-resource-gate.v1",
        "pass": True,
        "controlled_resource_stop": False,
        "stop_reason": None,
        "sample_count": 12,
        "minimum_mem_available_bytes": 300 * GIB,
        "maximum_job_memory_authority_bytes": 32 * GIB,
        "maximum_swap_authority_bytes": 0,
        "zero_swap_every_sample": True,
        "minimum_headroom_20_percent_preserved": True,
        "effective_job_cap_respected": True,
        "policy": {
            "schema_version": "task035e.reference-resource-policy.v1",
            "pass": True,
            "failure": None,
            "mem_total_bytes": total,
            "mem_available_start_bytes": available,
            "minimum_headroom_fraction": 0.2,
            "total_memory_cap_fraction": 0.8,
            "headroom_floor_bytes": headroom,
            "total_fraction_cap_bytes": int(0.8 * total),
            "available_minus_headroom_bytes": available - headroom,
            "effective_job_cap_bytes": cap,
            "formula": "min(0.8*MemTotal, MemAvailable_start-0.2*MemTotal)",
        },
    }


def _record(
    h_nm: float,
    *,
    rows: int,
    matrix_nnz: int,
    factor_nnz: int | None,
    assembly_peak_mb: float,
    solver_peak_mb: float | None,
    run_kind: str,
    mpi_size: int = 8,
    material: str = "silicon",
) -> dict[str, object]:
    full = run_kind == "full-solve"
    stages: list[dict[str, object]] = [
        {
            "stage": "stage4_full3d_assembly_backend",
            "max_mpi_process_tree_rss_mb": assembly_peak_mb,
            "max_container_cgroup_current_mb": assembly_peak_mb + 100.0,
        }
    ]
    if solver_peak_mb is not None:
        stages.extend(
            [
                {
                    "stage": "during_ksp_setup_peak",
                    "max_mpi_process_tree_rss_mb": solver_peak_mb,
                    "max_container_cgroup_current_mb": solver_peak_mb + 100.0,
                },
                {
                    "stage": "during_ksp_solve_peak",
                    "max_mpi_process_tree_rss_mb": solver_peak_mb - 20.0,
                    "max_container_cgroup_current_mb": solver_peak_mb + 80.0,
                },
            ]
        )
    solver_summary: dict[str, object] = {
        "petsc_direct_solver_profile": "default",
        "selected_parallel_lu_solver_type": "mumps",
        "actual_pc_factor_solver_type": "mumps" if full else None,
        "linear_solve_petsc_options": {
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
        },
    }
    if factor_nnz is not None:
        solver_summary["stage4_dtn_factor_inventory"] = {
            "available": True,
            "factor_solver_type": "mumps",
            "matrix_stats": {
                "matrix_rows": rows,
                "matrix_cols": rows,
                "matrix_nnz_used": float(factor_nnz),
            },
            "mumps_api_available": True,
        }
    return {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "status": (
            "task035e_reference_full_solve_pass"
            if full
            else "task035e_reference_assembly_resource_pass"
        ),
        "degree": 6,
        "h_nm": h_nm,
        "polarization_kind": "s",
        "run_kind": run_kind,
        "mpi_size": mpi_size,
        "profile": "default",
        "stage4_full3d_assembly_backend_requested": (
            "assembly_time_static_condensed"
        ),
        "stage4_full3d_assembly_backend_actual": "assembly_time_static_condensed",
        "source": {
            "commit_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "head_after_sha": SOURCE_SHA,
            "status_after": "",
            "stable_and_clean_after": True,
        },
        "task035e_reference_certifier": {
            "schema_version": "task035e.reference-resource-authority.v1",
            "selected": True,
            "credit": (
                "reference_physics_pending_hidden_certifier"
                if full
                else "resource_only_not_physics"
            ),
            "config_authority": _config_authority(h_nm, material=material),
            "lifecycle_authority": _lifecycle(),
            "live_resource_gate": _live_gate(),
        },
        "no_swap": True,
        "resource_authority": {
            "sample_count": 100,
            "dedicated_job_cgroup_observed": False,
            "memory_authority_mb": max(
                assembly_peak_mb, solver_peak_mb or assembly_peak_mb
            ),
            "memory_authority_gib": max(
                assembly_peak_mb, solver_peak_mb or assembly_peak_mb
            )
            / 1024.0,
            "max_process_tree_swap_mb": 0.0,
            "stage_peaks": stages,
        },
        "calibration": {
            "exact_rows": rows,
            "exact_assembled_nnz": float(matrix_nnz),
            "factorization_or_solve_stage_seen": full,
        },
        "qualification": {"pass": True, "failures": []},
        "solver_summary": solver_summary,
    }


def _write(path: Path, payload: dict[str, object]) -> tuple[Path, str]:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path, _file_sha(path)


@pytest.fixture
def campaign(tmp_path: Path) -> dict[str, object]:
    h10 = _write(
        tmp_path / "h10.json",
        _record(
            10.0,
            rows=50_000,
            matrix_nnz=40_000_000,
            factor_nnz=200_000_000,
            assembly_peak_mb=6_000.0,
            solver_peak_mb=14_000.0,
            run_kind="full-solve",
        ),
    )
    h7p5 = _write(
        tmp_path / "h7p5.json",
        _record(
            7.5,
            rows=140_000,
            matrix_nnz=120_000_000,
            factor_nnz=720_000_000,
            assembly_peak_mb=12_000.0,
            solver_peak_mb=32_000.0,
            run_kind="full-solve",
        ),
    )
    h5 = _write(
        tmp_path / "h5_assembly.json",
        _record(
            5.0,
            rows=330_000,
            matrix_nnz=300_000_000,
            factor_nnz=None,
            assembly_peak_mb=25_000.0,
            solver_peak_mb=None,
            run_kind="assembly-only",
        ),
    )
    return {
        "h10_record": h10[0],
        "h10_sha256": h10[1],
        "h7p5_record": h7p5[0],
        "h7p5_sha256": h7p5[1],
        "h5_assembly_record": h5[0],
        "h5_assembly_sha256": h5[1],
    }


def _memory(
    *,
    total_gib: int = 512,
    available_gib: int = 470,
    swap_used_bytes: int = 0,
) -> dict[str, object]:
    total = total_gib * GIB
    available = available_gib * GIB
    headroom = int(0.2 * total)
    cap = min(int(0.8 * total), available - headroom)
    return {
        "schema_version": "task035e.h5-factorization-live-memory.v1",
        "captured_from": "/proc/meminfo",
        "captured_at_utc": "2026-07-28T12:00:00+00:00",
        "mem_total_bytes": total,
        "mem_available_bytes": available,
        "swap_total_bytes": 32 * GIB,
        "swap_free_bytes": 32 * GIB - swap_used_bytes,
        "swap_used_bytes": swap_used_bytes,
        "minimum_headroom_fraction": 0.2,
        "headroom_floor_bytes": headroom,
        "total_memory_cap_fraction": 0.8,
        "effective_job_cap_bytes": cap,
        "formula": "min(0.8*MemTotal, MemAvailable-0.2*MemTotal)",
    }


def test_allow_authority_is_hash_bound_and_carries_no_pde_credit(
    campaign: dict[str, object],
) -> None:
    authority = build_factorization_decision(
        **campaign, live_memory=_memory()  # type: ignore[arg-type]
    )

    assert set(authority) == {"schema_version", "sha256", "payload"}
    assert authority["schema_version"] == AUTHORITY_SCHEMA
    assert authority["sha256"] == _json_sha(authority["payload"])
    payload = authority["payload"]
    assert payload["gate"]["launch_allowed"] is True
    assert payload["gate"]["failures"] == []
    issued = datetime.fromisoformat(payload["issued_at_utc"])
    expires = datetime.fromisoformat(payload["expires_at_utc"])
    assert expires - issued == timedelta(minutes=15)
    assert payload["validity_seconds"] == 15 * 60
    assert payload["campaign_identity"]["source_sha"] == SOURCE_SHA
    assert (
        payload["campaign_identity"]["h5_config_authority_sha256"]
        == _config_authority(5.0)["sha256"]
    )
    assert payload["credit"] == "no_pde_no_accuracy_no_reference_qualification_credit"
    assert payload["prediction"]["factor_nnz_interval"]["upper"] > 0
    assert (
        payload["prediction"]["solver_peak_bytes_interval"]["upper"]
        < payload["live_memory"]["effective_job_cap_bytes"]
    )
    assert all(
        row["expected_sha256"] == row["observed_sha256"]
        for row in payload["input_records"].values()
    )


def test_decision_time_must_be_aware_and_is_content_bound(
    campaign: dict[str, object],
) -> None:
    with pytest.raises(FactorizationDecisionError, match="timezone-aware"):
        build_factorization_decision(
            **campaign,  # type: ignore[arg-type]
            live_memory=_memory(),
            decision_time=datetime(2026, 7, 28, 12, 0),
        )

    issued = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    authority = build_factorization_decision(
        **campaign,  # type: ignore[arg-type]
        live_memory=_memory(),
        decision_time=issued,
    )
    assert authority["payload"]["issued_at_utc"] == issued.isoformat()
    assert authority["sha256"] == _json_sha(authority["payload"])


def test_prediction_upper_above_dynamic_cap_denies_launch(
    campaign: dict[str, object],
) -> None:
    authority = build_factorization_decision(
        **campaign,  # type: ignore[arg-type]
        live_memory=_memory(total_gib=160, available_gib=140),
    )

    gate = authority["payload"]["gate"]
    assert gate["launch_allowed"] is False
    assert "predicted_solver_peak_upper_not_below_dynamic_cap" in gate["failures"]
    assert gate["deny_is_controlled_resource_stop"] is True


def test_independent_file_hash_tamper_fails_closed(
    campaign: dict[str, object],
) -> None:
    path = campaign["h7p5_record"]
    assert isinstance(path, Path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(" ")

    authority = build_factorization_decision(
        **campaign, live_memory=_memory()  # type: ignore[arg-type]
    )

    gate = authority["payload"]["gate"]
    assert gate["launch_allowed"] is False
    assert any("h7p5_full: h7p5_full record hash mismatch" in row for row in gate["failures"])
    assert authority["payload"]["prediction"] is None


@pytest.mark.parametrize(
    ("label", "mutation", "expected"),
    [
        (
            "h7p5_record",
            lambda row: row.__setitem__("mpi_size", 4),
            "mpi8",
        ),
        (
            "h7p5_record",
            lambda row: row["task035e_reference_certifier"][
                "lifecycle_authority"
            ].__setitem__("selected_parallel_lu_solver_type", "superlu_dist"),
            "MUMPS lifecycle identity",
        ),
        (
            "h5_assembly_record",
            lambda row: row["task035e_reference_certifier"][
                "config_authority"
            ]["payload"]["config"].__setitem__("material", "copper"),
            "reference config authority hash",
        ),
    ],
)
def test_identity_or_field_drift_denies(
    campaign: dict[str, object],
    label: str,
    mutation: object,
    expected: str,
) -> None:
    path = campaign[label]
    assert isinstance(path, Path)
    row = json.loads(path.read_text(encoding="utf-8"))
    mutation(row)  # type: ignore[operator]
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    sha_key = label.replace("_record", "_sha256")
    campaign[sha_key] = _file_sha(path)

    authority = build_factorization_decision(
        **campaign, live_memory=_memory()  # type: ignore[arg-type]
    )

    failures = authority["payload"]["gate"]["failures"]
    assert authority["payload"]["gate"]["launch_allowed"] is False
    assert any(expected in failure for failure in failures)


def test_missing_factor_inventory_and_nonzero_swap_deny(
    campaign: dict[str, object],
) -> None:
    path = campaign["h10_record"]
    assert isinstance(path, Path)
    row = json.loads(path.read_text(encoding="utf-8"))
    row["solver_summary"].pop("stage4_dtn_factor_inventory")
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    campaign["h10_sha256"] = _file_sha(path)

    authority = build_factorization_decision(
        **campaign,  # type: ignore[arg-type]
        live_memory=_memory(swap_used_bytes=4096),
    )

    failures = authority["payload"]["gate"]["failures"]
    assert authority["payload"]["gate"]["launch_allowed"] is False
    assert any("stage4_dtn_factor_inventory" in failure for failure in failures)
    assert "live_memory: nonzero_swap" in failures


def test_valid_but_different_physical_config_is_not_same_campaign(
    campaign: dict[str, object],
) -> None:
    path = campaign["h5_assembly_record"]
    assert isinstance(path, Path)
    row = json.loads(path.read_text(encoding="utf-8"))
    config_authority = row["task035e_reference_certifier"]["config_authority"]
    config_authority["payload"]["config"]["material"] = "copper"
    config_authority["sha256"] = _json_sha(config_authority["payload"])
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    campaign["h5_assembly_sha256"] = _file_sha(path)

    authority = build_factorization_decision(
        **campaign, live_memory=_memory()  # type: ignore[arg-type]
    )

    assert authority["payload"]["gate"]["launch_allowed"] is False
    assert (
        "same_physical_config_except_mesh_h"
        in authority["payload"]["gate"]["failures"]
    )


def test_cli_returns_nonzero_for_deny_and_output_is_exclusive(
    campaign: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "decision.json"
    monkeypatch.setattr(
        decision,
        "read_live_memory_snapshot",
        lambda: _memory(total_gib=160, available_gib=140),
    )
    argv = [
        "--h10-record",
        str(campaign["h10_record"]),
        "--h10-sha256",
        str(campaign["h10_sha256"]),
        "--h7p5-record",
        str(campaign["h7p5_record"]),
        "--h7p5-sha256",
        str(campaign["h7p5_sha256"]),
        "--h5-assembly-record",
        str(campaign["h5_assembly_record"]),
        "--h5-assembly-sha256",
        str(campaign["h5_assembly_sha256"]),
        "--output",
        str(output),
    ]

    assert main(argv) == 2
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["payload"]["gate"]["launch_allowed"] is False
    assert output.stat().st_mode & 0o777 == 0o600
    assert main(argv) == 3
    with pytest.raises(FactorizationDecisionError, match="refusing to overwrite"):
        write_authority_exclusive(output, persisted)
