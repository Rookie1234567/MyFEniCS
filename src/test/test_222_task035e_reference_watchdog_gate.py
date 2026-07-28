from __future__ import annotations

import hashlib
import json
import signal
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from benchmarks.run_task033_full3d_watchdog import (
    GIB,
    TASK035E_REFERENCE_BACKEND,
    TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA,
    TASK035E_REFERENCE_RESOURCE_AUTHORITY_SCHEMA,
    _apply_task035e_reference_dynamic_cap,
    _parse_args,
    _full3d_config,
    _terminate,
    _task035e_reference_config_authority,
    _task035e_h5_factorization_authority_gate,
    _task035e_reference_resource_authority_gate,
    _task035e_reference_resource_decision,
    _task035e_reference_resource_policy,
    _task035e_reference_resource_summary,
    _validate_task035e_reference_resource_authority,
    _validate_task035e_h5_factorization_authority,
    _worker_command,
    _worker_launch_contract,
)
from src.common.config_3d import qualify_stage4_full3d_assembly_backend


SOURCE_SHA = "a" * 40
AUTHORITY_SHA256 = "b" * 64
FACTOR_AUTHORITY_SHA256 = "c" * 64


def _assembly_cli(h_nm: str = "10") -> list[str]:
    return [
        "--degree",
        "6",
        "--h-nm",
        h_nm,
        "--polarization-kind",
        "s",
        "--run-kind",
        "assembly-only",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        TASK035E_REFERENCE_BACKEND,
        "--task035e-reference-certifier-gate",
        "--verified-clean-sha",
        SOURCE_SHA,
    ]


def _full_cli(h_nm: str = "10") -> list[str]:
    result = [
        *_assembly_cli(h_nm),
        "--task035e-reference-resource-authority",
        "/tmp/task035e_resource_authority.json",
        "--task035e-reference-resource-authority-sha256",
        AUTHORITY_SHA256,
    ]
    if h_nm == "5":
        result.extend(
            (
                "--task035e-h5-factorization-authority",
                "/tmp/task035e_h5_factorization_authority.json",
                "--task035e-h5-factorization-authority-sha256",
                FACTOR_AUTHORITY_SHA256,
            )
        )
    return result


def _replace_option(cli: list[str], option: str, value: str) -> list[str]:
    result = list(cli)
    result[result.index(option) + 1] = value
    return result


def _resource_policy() -> dict[str, object]:
    return _task035e_reference_resource_policy(
        {
            "wsl_total_bytes": 100 * GIB,
            "host_available_bytes": 90 * GIB,
        }
    )


def _assembly_authority(
    config_sha256: str,
    *,
    h_nm: float = 10.0,
) -> dict[str, object]:
    policy = _resource_policy()
    live_gate = {
        "schema_version": "task035e.reference-live-resource-gate.v1",
        "pass": True,
        "controlled_resource_stop": False,
        "stop_reason": None,
        "sample_count": 2,
        "minimum_mem_available_bytes": 60 * GIB,
        "maximum_job_memory_authority_bytes": 50 * GIB,
        "maximum_swap_authority_bytes": 0,
        "zero_swap_every_sample": True,
        "minimum_headroom_20_percent_preserved": True,
        "effective_job_cap_respected": True,
        "policy": policy,
    }
    return {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "status": "task035e_reference_assembly_resource_pass",
        "degree": 6,
        "h_nm": h_nm,
        "polarization_kind": "s",
        "run_kind": "assembly-only",
        "mpi_size": 8,
        "profile": "default",
        "stage4_full3d_assembly_backend_requested": (
            TASK035E_REFERENCE_BACKEND
        ),
        "stage4_full3d_assembly_backend_actual": (
            TASK035E_REFERENCE_BACKEND
        ),
        "no_swap": True,
        "source": {
            "commit_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
        },
        "environment_before": {
            "wsl_total_bytes": 100 * GIB,
            "host_available_bytes": 90 * GIB,
        },
        "calibration": {
            "exact_rows": 100,
            "exact_assembled_nnz": 1_000,
        },
        "qualification": {"pass": True, "failures": []},
        "task035e_reference_certifier": {
            "schema_version": TASK035E_REFERENCE_RESOURCE_AUTHORITY_SCHEMA,
            "selected": True,
            "credit": "resource_only_not_physics",
            "config_authority": {"sha256": config_sha256},
            "live_resource_gate": live_gate,
        },
    }


def _factor_authority(
    config_sha256: str,
    assembly_sha256: str,
    *,
    issued_at: datetime,
    allow: bool = True,
) -> dict[str, object]:
    inputs = {
        "h10_full": {
            "path": "/tmp/h10.json",
            "expected_sha256": "1" * 64,
            "observed_sha256": "1" * 64,
        },
        "h7p5_full": {
            "path": "/tmp/h7p5.json",
            "expected_sha256": "2" * 64,
            "observed_sha256": "2" * 64,
        },
        "h5_assembly": {
            "path": "/tmp/h5.json",
            "expected_sha256": assembly_sha256,
            "observed_sha256": assembly_sha256,
        },
    }
    failures = [] if allow else [
        "predicted_solver_peak_upper_not_below_dynamic_cap"
    ]
    payload: dict[str, object] = {
        "schema_version": TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA,
        "authority_role": "resource_launch_decision_only",
        "credit": "no_pde_no_accuracy_no_reference_qualification_credit",
        "issued_at_utc": issued_at.isoformat(),
        "expires_at_utc": (issued_at + timedelta(minutes=15)).isoformat(),
        "validity_seconds": 15 * 60,
        "campaign_identity": {
            "source_sha": SOURCE_SHA,
            "physical_config_sha256": "3" * 64,
            "h5_config_authority_sha256": config_sha256,
        },
        "target": {
            "degree": 6,
            "h_nm": 5.0,
            "run_kind_to_authorize": "full-solve",
            "factor_solver": "mumps",
            "mpi_size": 8,
            "assembly_backend": TASK035E_REFERENCE_BACKEND,
            "profile": "default",
        },
        "input_records": inputs,
        "identity_checks": {
            "same_clean_source": True,
            "same_physical_config_except_mesh_h": True,
        },
        "prediction": {
            "solver_peak_bytes_interval": {
                "lower": 10,
                "central": 20,
                "upper": 30,
            }
        },
        "live_memory": {
            "effective_job_cap_bytes": 40,
            "swap_used_bytes": 0,
        },
        "gate": {
            "launch_allowed": allow,
            "predicted_upper_below_dynamic_cap": allow,
            "zero_swap_at_decision": True,
            "minimum_20_percent_headroom_available": True,
            "failures": failures,
            "deny_is_controlled_resource_stop": not allow,
            "launch_semantics": "single immediate h5 full-solve launch only",
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "payload": payload,
    }


def test_ordinary_defaults_and_p6_fail_closed_are_unchanged() -> None:
    ordinary = _parse_args(["--degree", "3"])
    assert ordinary.task035e_reference_certifier_gate is False
    assert ordinary.stage4_full3d_assembly_backend == "standard_full"
    assert ordinary.run_kind == "assembly-only"

    with pytest.raises(SystemExit):
        _parse_args(["--degree", "6", "--h-nm", "7.5"])


@pytest.mark.parametrize("h_nm", ["10", "7.5", "5"])
@pytest.mark.parametrize("run_kind", ["assembly-only", "full-solve"])
def test_task035e_gate_accepts_only_three_reference_points(
    h_nm: str,
    run_kind: str,
) -> None:
    cli = _assembly_cli(h_nm) if run_kind == "assembly-only" else _full_cli(h_nm)
    if run_kind == "full-solve":
        cli = _replace_option(cli, "--run-kind", "full-solve")
    args = _parse_args(cli)
    assert args.degree == 6
    assert args.h_nm == float(h_nm)
    assert args.mpi_size == 8
    assert args.profile == "default"
    assert args.stage4_full3d_assembly_backend == TASK035E_REFERENCE_BACKEND


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--degree", "4"),
        ("--h-nm", "15"),
        ("--polarization-kind", "p"),
        ("--run-kind", "factorization-only"),
        ("--mpi-size", "4"),
        ("--profile", "mumps_ooc"),
        ("--stage4-full3d-assembly-backend", "standard_full"),
    ],
)
def test_task035e_scope_drift_is_rejected(option: str, value: str) -> None:
    with pytest.raises(SystemExit):
        _parse_args(_replace_option(_assembly_cli(), option, value))

    with pytest.raises(SystemExit):
        _parse_args([*_assembly_cli(), "--allow-swap"])


def test_full_solve_requires_authorities_and_assembly_forbids_them() -> None:
    with pytest.raises(SystemExit):
        _parse_args(_replace_option(_assembly_cli(), "--run-kind", "full-solve"))

    with pytest.raises(SystemExit):
        _parse_args(
            [
                *_assembly_cli(),
                "--task035e-reference-resource-authority",
                "/tmp/authority.json",
                "--task035e-reference-resource-authority-sha256",
                AUTHORITY_SHA256,
            ]
        )

    h5_without_factor = [
        value
        for index, value in enumerate(_full_cli("5"))
        if (
            value
            not in {
                "--task035e-h5-factorization-authority",
                "/tmp/task035e_h5_factorization_authority.json",
                "--task035e-h5-factorization-authority-sha256",
                FACTOR_AUTHORITY_SHA256,
            }
        )
    ]
    with pytest.raises(SystemExit):
        _parse_args(
            _replace_option(h5_without_factor, "--run-kind", "full-solve")
        )

    with pytest.raises(SystemExit):
        _parse_args(
            [
                *_assembly_cli("5"),
                "--task035e-h5-factorization-authority",
                "/tmp/factor.json",
                "--task035e-h5-factorization-authority-sha256",
                FACTOR_AUTHORITY_SHA256,
            ]
        )

    with pytest.raises(SystemExit):
        _parse_args(
            [
                *_full_cli("7.5"),
                "--task035e-h5-factorization-authority",
                "/tmp/factor.json",
                "--task035e-h5-factorization-authority-sha256",
                FACTOR_AUTHORITY_SHA256,
            ]
        )


def test_config_identity_is_run_kind_neutral_and_h_specific() -> None:
    assembly = _parse_args(_assembly_cli())
    full = _parse_args(_replace_option(_full_cli(), "--run-kind", "full-solve"))
    h7p5 = _parse_args(_assembly_cli("7.5"))
    assert (
        _task035e_reference_config_authority(assembly)["sha256"]
        == _task035e_reference_config_authority(full)["sha256"]
    )
    assert (
        _task035e_reference_config_authority(assembly)["sha256"]
        != _task035e_reference_config_authority(h7p5)["sha256"]
    )
    config = _full3d_config(assembly)
    assert config.petsc_direct_solver_profile_requested == "default"
    assert config.petsc_extra_options == {}
    assert config.direct_release_base_after_augmentation is False
    assert config.direct_release_solver_before_postprocess is False


def test_config_authority_is_the_real_jsonable_solver_config() -> None:
    args = _parse_args(_assembly_cli())
    authority = _task035e_reference_config_authority(args)
    expected = replace(
        _full3d_config(args),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_static_condensed_resource_only_assembly=False,
        full3d_reference_export=True,
        full3d_reference_plane_z=(10.0, 30.0, 60.0, 90.0, 110.0),
        unique_output=False,
    ).as_jsonable()
    canonical_expected = json.loads(json.dumps(expected))
    assert authority["payload"]["config"] == canonical_expected
    for derived_key in (
        "x_min",
        "x_max",
        "physical_z_min",
        "physical_z_max",
        "grating_bounds",
        "eps_grating",
        "k0",
    ):
        assert derived_key in authority["payload"]["config"]


def test_static_assembly_resource_scope_is_explicit_and_has_no_physics_credit() -> None:
    assembly = _full3d_config(_parse_args(_assembly_cli()))
    assert assembly.stage4_static_condensed_resource_only_assembly is True
    qualification = qualify_stage4_full3d_assembly_backend(assembly)
    assert qualification["status"] == "qualified_resource_only"
    assert qualification["resource_only"] is True
    assert qualification["physics_credit"] is False
    assert (
        qualification["contract"][-1]
        == "assembly_only_resource_authority_no_physics_credit"
    )

    with pytest.raises(ValueError, match="complete direct solve"):
        qualify_stage4_full3d_assembly_backend(
            replace(
                assembly,
                stage4_static_condensed_resource_only_assembly=False,
            )
        )
    with pytest.raises(ValueError, match="requires stage4_full3d_assembly_backend"):
        qualify_stage4_full3d_assembly_backend(
            replace(
                assembly,
                stage4_full3d_assembly_backend="standard_full",
            )
        )

    full_args = _parse_args(
        _replace_option(_full_cli(), "--run-kind", "full-solve")
    )
    full_qualification = qualify_stage4_full3d_assembly_backend(
        _full3d_config(full_args)
    )
    assert full_qualification["status"] == "qualified"
    assert "resource_only" not in full_qualification


def test_parent_worker_contract_binds_gate_and_both_authority_hashes() -> None:
    args = _parse_args(_replace_option(_full_cli(), "--run-kind", "full-solve"))
    args.run_dir = Path("/tmp/task035e-worker-contract")
    config_sha = _task035e_reference_config_authority(args)["sha256"]
    contract = _worker_launch_contract(args)
    assert contract["task035e_reference_certifier_gate"] is True
    assert contract["task035e_reference_config_authority_sha256"] == config_sha
    assert (
        contract["task035e_reference_resource_authority_sha256"]
        == AUTHORITY_SHA256
    )
    command = _worker_command(args, args.run_dir)
    assert "--task035e-reference-certifier-gate" in command
    assert "--task035e-reference-resource-authority" in command
    assert "--task035e-reference-resource-authority-sha256" in command

    h5_args = _parse_args(
        _replace_option(_full_cli("5"), "--run-kind", "full-solve")
    )
    h5_args.run_dir = Path("/tmp/task035e-h5-worker-contract")
    h5_contract = _worker_launch_contract(h5_args)
    h5_command = _worker_command(h5_args, h5_args.run_dir)
    assert (
        h5_contract["task035e_h5_factorization_authority_sha256"]
        == FACTOR_AUTHORITY_SHA256
    )
    assert "--task035e-h5-factorization-authority" in h5_command
    assert "--task035e-h5-factorization-authority-sha256" in h5_command


def test_dynamic_resource_cap_uses_exact_task_formula() -> None:
    policy = _resource_policy()
    assert policy["pass"] is True
    assert policy["headroom_floor_bytes"] == 20 * GIB
    assert policy["total_fraction_cap_bytes"] == 80 * GIB
    assert policy["available_minus_headroom_bytes"] == 70 * GIB
    assert policy["effective_job_cap_bytes"] == 70 * GIB

    unreadable = _task035e_reference_resource_policy({})
    assert unreadable["pass"] is False
    low = _task035e_reference_resource_policy(
        {
            "wsl_total_bytes": 100 * GIB,
            "host_available_bytes": 19 * GIB,
        }
    )
    assert low["pass"] is False


def test_dynamic_resource_cap_is_applied_and_cannot_be_loosened() -> None:
    snapshot = {
        "wsl_total_bytes": 100 * GIB,
        "host_available_bytes": 90 * GIB,
    }
    args = _parse_args(_assembly_cli())
    policy = _apply_task035e_reference_dynamic_cap(args, snapshot)
    assert policy["effective_job_cap_bytes"] == 70 * GIB
    assert args.terminate_gib == 70.0
    assert args.warning_gib == 56.0

    exact = _parse_args(_assembly_cli())
    exact.terminate_gib = 70.0
    _apply_task035e_reference_dynamic_cap(exact, snapshot)
    assert exact.terminate_gib == 70.0

    loose = _parse_args(_assembly_cli())
    loose.terminate_gib = 71.0
    with pytest.raises(SystemExit, match="do not override"):
        _apply_task035e_reference_dynamic_cap(loose, snapshot)


def test_terminate_signals_the_worker_process_group(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 123

        @staticmethod
        def poll():
            return None

        @staticmethod
        def wait(*, timeout: int):
            assert timeout == 10
            return 0

        @staticmethod
        def terminate():
            raise AssertionError("POSIX process-group termination was bypassed")

    monkeypatch.setattr("os.getpgid", lambda pid: 456)
    monkeypatch.setattr(
        "os.killpg",
        lambda pgid, signum: signals.append((pgid, signum)),
    )
    _terminate(FakeProcess())
    assert signals == [(456, signal.SIGTERM)]


def test_live_resource_decision_stops_at_first_swap_then_headroom_or_cap() -> None:
    policy = _resource_policy()
    row = {
        "mpi_process_tree_rss_mb": 10 * 1024,
        "mpi_process_tree_swap_mb": 0.0,
        "job_cgroup_dedicated": False,
    }
    safe = _task035e_reference_resource_decision(
        row,
        mem_available_bytes=80 * GIB,
        policy=policy,
    )
    assert safe["stop"] is False

    swap = _task035e_reference_resource_decision(
        {**row, "mpi_process_tree_swap_mb": 1.0},
        mem_available_bytes=1,
        policy=policy,
    )
    assert swap["reason"] == "nonzero_swap"
    partially_readable_swap = _task035e_reference_resource_decision(
        {
            **row,
            "mpi_process_tree_swap_mb": 1.0,
            "job_cgroup_dedicated": True,
            "container_cgroup_current_mb": None,
            "container_swap_current_mb": None,
        },
        mem_available_bytes=80 * GIB,
        policy=policy,
    )
    assert partially_readable_swap["reason"] == "nonzero_swap"

    low_headroom = _task035e_reference_resource_decision(
        row,
        mem_available_bytes=19 * GIB,
        policy=policy,
    )
    assert low_headroom["reason"] == "memavailable_below_20_percent"

    cap = _task035e_reference_resource_decision(
        {**row, "mpi_process_tree_rss_mb": 70 * 1024},
        mem_available_bytes=80 * GIB,
        policy=policy,
    )
    assert cap["reason"] == "effective_job_cap_reached"


def test_resource_summary_and_authority_are_resource_only_and_fail_closed() -> None:
    policy = _resource_policy()
    safe_samples = [
        {
            "mem_available_bytes": 80 * GIB,
            "job_memory_authority_bytes": 10 * GIB,
            "swap_authority_bytes": 0,
        },
        {
            "mem_available_bytes": 60 * GIB,
            "job_memory_authority_bytes": 50 * GIB,
            "swap_authority_bytes": 0,
        },
    ]
    summary = _task035e_reference_resource_summary(
        policy=policy,
        samples=safe_samples,
        stop_reason=None,
    )
    assert summary["pass"] is True

    args = _parse_args(_assembly_cli())
    config_sha = _task035e_reference_config_authority(args)["sha256"]
    payload = _assembly_authority(config_sha)
    gate = _task035e_reference_resource_authority_gate(
        payload,
        expected_sha256=AUTHORITY_SHA256,
        observed_sha256=AUTHORITY_SHA256,
        expected_source_sha=SOURCE_SHA,
        expected_config_sha256=config_sha,
        expected_h_nm=10.0,
    )
    assert gate["pass"] is True, gate["failures"]
    assert gate["role"] == "assembly_resource_only_not_physics_authority"

    payload["no_swap"] = False
    rejected = _task035e_reference_resource_authority_gate(
        payload,
        expected_sha256=AUTHORITY_SHA256,
        observed_sha256=AUTHORITY_SHA256,
        expected_source_sha=SOURCE_SHA,
        expected_config_sha256=config_sha,
        expected_h_nm=10.0,
    )
    assert rejected["pass"] is False
    assert "zero_swap" in rejected["failures"]


def test_parent_and_worker_revalidate_authority_file_hash(
    tmp_path: Path,
) -> None:
    assembly_args = _parse_args(_assembly_cli())
    config_sha = _task035e_reference_config_authority(assembly_args)["sha256"]
    path = tmp_path / "assembly_resource_authority.json"
    path.write_text(
        json.dumps(_assembly_authority(config_sha), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    args = _parse_args(
        _replace_option(
            [
                *_full_cli(),
            ],
            "--run-kind",
            "full-solve",
        )
    )
    args.task035e_reference_resource_authority = path
    args.task035e_reference_resource_authority_sha256 = sha256
    assert _validate_task035e_reference_resource_authority(args)["pass"] is True

    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        _validate_task035e_reference_resource_authority(args)


def test_h5_factorization_allow_is_fresh_hash_bound_and_fail_closed(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    h5_assembly_args = _parse_args(_assembly_cli("5"))
    config_sha = _task035e_reference_config_authority(
        h5_assembly_args
    )["sha256"]
    assembly_path = tmp_path / "h5_assembly.json"
    assembly_path.write_text(
        json.dumps(
            _assembly_authority(config_sha, h_nm=5.0),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    assembly_sha = hashlib.sha256(assembly_path.read_bytes()).hexdigest()
    factor_path = tmp_path / "h5_factor_allow.json"
    factor_path.write_text(
        json.dumps(
            _factor_authority(
                config_sha,
                assembly_sha,
                issued_at=now,
            ),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    factor_sha = hashlib.sha256(factor_path.read_bytes()).hexdigest()

    gate = _task035e_h5_factorization_authority_gate(
        json.loads(factor_path.read_text(encoding="utf-8")),
        expected_file_sha256=factor_sha,
        observed_file_sha256=factor_sha,
        expected_assembly_sha256=assembly_sha,
        expected_source_sha=SOURCE_SHA,
        expected_config_sha256=config_sha,
        now_utc=now + timedelta(minutes=1),
    )
    assert gate["pass"] is True, gate["failures"]

    identity_drift = json.loads(
        factor_path.read_text(encoding="utf-8")
    )
    identity_drift["payload"]["identity_checks"][
        "same_physical_config_except_mesh_h"
    ] = False
    encoded = json.dumps(
        identity_drift["payload"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    identity_drift["sha256"] = hashlib.sha256(encoded).hexdigest()
    drift_gate = _task035e_h5_factorization_authority_gate(
        identity_drift,
        expected_file_sha256=factor_sha,
        observed_file_sha256=factor_sha,
        expected_assembly_sha256=assembly_sha,
        expected_source_sha=SOURCE_SHA,
        expected_config_sha256=config_sha,
        now_utc=now + timedelta(minutes=1),
    )
    assert drift_gate["pass"] is False
    assert "campaign_identity_checks" in drift_gate["failures"]

    expired = _task035e_h5_factorization_authority_gate(
        json.loads(factor_path.read_text(encoding="utf-8")),
        expected_file_sha256=factor_sha,
        observed_file_sha256=factor_sha,
        expected_assembly_sha256=assembly_sha,
        expected_source_sha=SOURCE_SHA,
        expected_config_sha256=config_sha,
        now_utc=now + timedelta(minutes=16),
    )
    assert expired["pass"] is False
    assert "fresh_at_launch" in expired["failures"]

    cli = _full_cli("5")
    cli = _replace_option(cli, "--run-kind", "full-solve")
    cli = _replace_option(
        cli,
        "--task035e-reference-resource-authority-sha256",
        assembly_sha,
    )
    cli = _replace_option(
        cli,
        "--task035e-h5-factorization-authority-sha256",
        factor_sha,
    )
    args = _parse_args(cli)
    args.task035e_reference_resource_authority = assembly_path
    args.task035e_h5_factorization_authority = factor_path
    assert _validate_task035e_reference_resource_authority(args)["pass"] is True
    assert _validate_task035e_h5_factorization_authority(
        args,
        now_utc=now + timedelta(minutes=1),
    )["pass"] is True

    factor_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="factorization authority failed"):
        _validate_task035e_h5_factorization_authority(
            args,
            now_utc=now + timedelta(minutes=1),
        )
