from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys

import pytest

from benchmarks.run_task033_full3d_watchdog import (
    TASK035E_BLIND_CANDIDATE_BACKEND,
    TASK035E_INTERNAL_PROBE_SCHEMA,
    _full3d_config,
    _parse_args,
    _task035e_blind_candidate_authority,
    _task035e_blind_candidate_plan_gate,
    _task035e_internal_probe_authority,
    _task035e_internal_probe_success_status,
    _validate_task035e_formal_runtime,
    _worker_command,
    _worker_launch_contract,
    _write_task035e_private_json_atomic,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.common.config_3d import target_stage4_config


SOURCE_SHA = "6" * 40
ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_probe_cli(
    tmp_path: Path,
    *,
    kind: str,
    mpi_size: int = 8,
) -> tuple[list[str], dict[str, object], Path, str]:
    tmp_path.mkdir(parents=True)
    plan = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        path_id="A",
        source_sha=SOURCE_SHA,
        comm_size=8,
    ).plan_payload()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(plan, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    plan_path.chmod(0o600)
    plan_sha = _sha(plan_path)
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}\n", encoding="utf-8")
    snapshot_path.chmod(0o600)
    snapshot_sha = _sha(snapshot_path)
    cli = [
        "--degree",
        "6",
        "--h-nm",
        "20",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        str(mpi_size),
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        TASK035E_BLIND_CANDIDATE_BACKEND,
        "--stage4-local-h-refinement-plan",
        str(plan_path),
        "--stage4-local-h-refinement-plan-sha256",
        plan_sha,
        "--task035e-blind-candidate-gate",
        "--task035e-internal-probe-kind",
        kind,
        "--task035e-blind-trial-id",
        "path-a-cycle-0",
        "--task035e-blind-cycle-index",
        "0",
        "--task035e-blind-output-role",
        "current",
        "--task035e-current-snapshot-manifest",
        str(snapshot_path),
        "--task035e-current-snapshot-manifest-sha256",
        snapshot_sha,
        "--verified-clean-sha",
        SOURCE_SHA,
    ]
    return cli, plan, plan_path, plan_sha


def test_three_mpi8_probe_kinds_reach_config_and_worker_contract(
    tmp_path: Path,
) -> None:
    algebraic_cli, plan, plan_path, plan_sha = _base_probe_cli(
        tmp_path / "algebraic",
        kind="algebraic",
    )
    algebraic = _parse_args(algebraic_cli)
    algebraic.run_dir = tmp_path / "algebraic-run"
    assert _full3d_config(algebraic).stage4_dtn_order_policy == (
        "auto_propagating"
    )
    assert (
        _full3d_config(algebraic).stage4_dtn_quadrature_degree is None
    )
    algebraic_probe = _task035e_internal_probe_authority(algebraic)
    assert algebraic_probe is not None
    assert algebraic_probe["schema_version"] == TASK035E_INTERNAL_PROBE_SCHEMA
    assert algebraic_probe["config_overrides"] == {}
    assert (
        _task035e_internal_probe_success_status(
            algebraic,
            qualified=True,
        )
        == "task035e_internal_probe_mpi8_pass"
    )
    assert (
        _task035e_blind_candidate_authority(
            algebraic,
            {"config": {"degree": 6}},
            source_sha=SOURCE_SHA,
            qualified=True,
        )
        is None
    )
    contract = _worker_launch_contract(algebraic)
    assert contract["task035e_internal_probe"] == algebraic_probe
    command = _worker_command(algebraic, algebraic.run_dir)
    assert "--task035e-internal-probe-kind" in command
    assert "--task035e-transition-action" not in command
    assert "--task035e-current-snapshot-manifest" in command

    binding = {
        "plan_payload": plan,
        "plan_identity": {
            "file_sha256": plan_sha,
            "forest_leaf_catalog_sha256": plan["expected_forest"][
                "leaf_catalog_sha256"
            ],
            "cell_degree_plan_sha256": plan[
                "cell_interior_degree_plan_sha256"
            ],
        },
        "snapshot_cycle_index": 0,
    }
    gate = _task035e_blind_candidate_plan_gate(
        plan,
        expected_file_sha256=plan_sha,
        observed_file_sha256=plan_sha,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=0,
        expected_output_role="current",
        current_snapshot_binding=binding,
        internal_probe_kind="algebraic",
    )
    assert gate["pass"] is True, gate["failures"]
    assert gate["checks"]["internal_probe_same_plan_snapshot_bound"] is True
    assert plan_path.is_file()

    dtn_cli, _, _, _ = _base_probe_cli(
        tmp_path / "dtn",
        kind="dtn",
    )
    dtn = _parse_args(
        [
            *dtn_cli,
            "--task035e-probe-dtn-max-m",
            "8",
            "--task035e-probe-dtn-max-n",
            "2",
        ]
    )
    dtn_cfg = _full3d_config(dtn)
    assert dtn_cfg.stage4_dtn_order_policy == "manual"
    assert dtn_cfg.diffraction_order_max_m == 8
    assert dtn_cfg.diffraction_order_max_n == 2

    post_cli, _, _, _ = _base_probe_cli(
        tmp_path / "postprocess",
        kind="postprocess",
    )
    post = _parse_args(
        [
            *post_cli,
            "--task035e-probe-surface-quadrature-degree",
            "29",
        ]
    )
    assert _full3d_config(post).stage4_dtn_quadrature_degree == 29


def test_only_explicit_serial_probe_can_use_mpi1(tmp_path: Path) -> None:
    serial_cli, _, _, _ = _base_probe_cli(
        tmp_path / "serial",
        kind="serial_mpi1",
        mpi_size=1,
    )
    serial = _parse_args(serial_cli)
    assert serial.mpi_size == 1
    assert _task035e_internal_probe_authority(serial)["kind"] == (
        "serial_mpi1"
    )
    assert (
        _task035e_internal_probe_success_status(
            serial,
            qualified=True,
        )
        == "task035e_internal_probe_serial_mpi1_pass"
    )

    algebraic_cli, _, _, _ = _base_probe_cli(
        tmp_path / "bad-algebraic",
        kind="algebraic",
        mpi_size=1,
    )
    with pytest.raises(SystemExit):
        _parse_args(algebraic_cli)

    wrong_serial_cli, _, _, _ = _base_probe_cli(
        tmp_path / "bad-serial",
        kind="serial_mpi1",
        mpi_size=8,
    )
    with pytest.raises(SystemExit):
        _parse_args(wrong_serial_cli)


def test_formal_runtime_requires_repo_entrypoint_and_linux_tmp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setenv("TMPDIR", "/tmp")
    monkeypatch.setenv("TMP", "/tmp")
    monkeypatch.setenv("TEMP", "/tmp")
    monkeypatch.setattr(
        sys,
        "executable",
        str(ROOT / ".venv" / "bin" / "python"),
    )
    runtime = _validate_task035e_formal_runtime(
        require_private_worker_tmp=True,
    )
    assert runtime["python_executable"] == str(
        ROOT / ".venv" / "bin" / "python"
    )
    assert runtime["petsc_scalar_type"] == "complex128"
    assert runtime["petsc_int_type"] == "int32"

    monkeypatch.setenv("TMP", "/mnt/c/Windows/Temp")
    with pytest.raises(SystemExit, match="TMP must be exactly /tmp"):
        _validate_task035e_formal_runtime(
            require_private_worker_tmp=True,
        )

    monkeypatch.setenv("TMP", "/tmp")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    with pytest.raises(SystemExit, match="repository .venv Python"):
        _validate_task035e_formal_runtime(
            require_private_worker_tmp=True,
        )


def test_task035e_formal_record_writer_is_atomic_and_private(
    tmp_path: Path,
) -> None:
    output = tmp_path / "watchdog-summary.json"
    output.write_text('{"old":true}\n', encoding="utf-8")
    output.chmod(0o644)

    _write_task035e_private_json_atomic(
        output,
        {"schema_version": "fixture.v1", "status": "pass"},
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": "fixture.v1",
        "status": "pass",
    }
    assert not list(tmp_path.glob(".watchdog-summary.json.*.tmp"))
