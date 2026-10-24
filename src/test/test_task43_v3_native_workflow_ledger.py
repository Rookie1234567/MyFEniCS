"""Exercise the native A2 entry up to, but not through, mesh construction."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_Y6_CONFIG = _REPO_ROOT / (
    "benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/resolved_config.json"
)
_Y6_CONFIG_SHA256 = "57ad47a4a5ce221bf0e420b4faea084c0557bcd19de29b605e62d50a2bbaeedc"
_V2_CONTRACT_SHA256 = "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc"
_A2_NATIVE_CONTRACT_SHA256 = (
    "77c533673eba4178868ef22f4a27f8d7ecfbf50d6a47acbcbf2fe45b269960d0"
)
_V2_PLAN_SHA256 = "864330a9a8d7efeeb1e9e48c73cf48331a9a4963a1bcea1ae061c00c769b455e"
_V3_CONTRACT_SHA256 = "b694a975dee21d8347d77b3c247edda313422c9f2f6c5c605f8bcb52161e3898"
_V3_PLAN_SHA256 = "b162512ed484ae30b88555b83afe0ad0ac669014e18cf1f1114f24c02bdb1db7"


class _StopBeforeMesh(RuntimeError):
    pass


def test_a2_native_entry_writes_workflow_ledger_before_mesh_or_solver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Use the frozen Y6 payload and stop at the native mesh-builder boundary."""

    if not _Y6_CONFIG.is_file():
        pytest.skip("the frozen Y6_1 resolved payload is an ignored workstation input")

    from mpi4py import MPI
    from petsc4py import PETSc

    from benchmarks.task43_hp_adaptivity.a2_native_p6_diagnostic import (
        _validate_v2_y6_native_profile_payload,
    )
    from src.runners.p6_condensed_direct import run_p6_condensed_direct
    from src.solvers import fullspace_same_mesh_hcurl_pmg_global as mesh_builder

    raw_bytes = _Y6_CONFIG.read_bytes()
    assert hashlib.sha256(raw_bytes).hexdigest() == _Y6_CONFIG_SHA256
    raw_payload = json.loads(raw_bytes)
    resolved_payload, compatibility = _validate_v2_y6_native_profile_payload(
        raw_payload,
        raw_path=str(_Y6_CONFIG),
        raw_sha256=_Y6_CONFIG_SHA256,
    )
    assert compatibility["native_validator_passed_on_in_memory_copy"] is True
    assert resolved_payload is not raw_payload
    assert MPI.COMM_WORLD.size == 1
    assert os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION") == "1"
    assert PETSc.ScalarType.__name__ == "complex128"
    assert np.dtype(PETSc.IntType) == np.dtype(np.int64)

    run_directory = tmp_path / "native_run"
    phase_path = tmp_path / "watchdog" / "workflow_phase.json"
    phase_path.parent.mkdir()
    assert not phase_path.exists()

    # The runner's real Task43 resource-profile checks are exercised with a
    # bounded test fixture; this is not a launch-capacity preflight.
    cap_bytes = 192 * 1024**3
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(phase_path.resolve()))
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PARENT_PID", str(os.getpid()))
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_RESOURCE_PROFILE_IDENTITY",
        "task43_hp_adaptivity_resource_v1",
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_RESOURCE_STOP_POLICY", "legacy")
    monkeypatch.setenv("PHYSICAL_WATCHDOG_REQUIRE_ZERO_SWAP", "1")
    monkeypatch.setenv("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", str(cap_bytes))
    monkeypatch.setenv("PHYSICAL_WATCHDOG_RESERVE_BYTES", str(64 * 1024**3))
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PLANNING_CAP_BYTES", str(160 * 1024**3))
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "1")

    mesh_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def stop_before_mesh(*args: object, **kwargs: object) -> None:
        mesh_calls.append((args, kwargs))
        raise _StopBeforeMesh("test sentinel before the first mesh/solver operation")

    monkeypatch.setattr(mesh_builder, "_build_same_mesh_levels", stop_before_mesh)
    v2_diagnostic = {
        "schema": "task43.v2.native_p6_diagnostic.v1",
        "phase": "A2_q",
        "volume_quadrature_degree": 19,
        "surface_quadrature_degree": 32,
        "normal_correction_limit": 2,
        "extra_correction_limit": 1,
        "contract_sha256": _V2_CONTRACT_SHA256,
        "a2_native_contract_sha256": _A2_NATIVE_CONTRACT_SHA256,
        "plan_markdown_sha256": _V2_PLAN_SHA256,
        "reference_resolved_config_path": str(_Y6_CONFIG),
        "reference_resolved_config_sha256": _Y6_CONFIG_SHA256,
    }
    v3_diagnostic = {
        "phase": "A2_q",
        "attempt": 3,
        "contract_path": "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json",
        "contract_sha256": _V3_CONTRACT_SHA256,
        "plan_path": "docs/task43_hp_adaptivity/diagnostic_plan_v3.md",
        "plan_sha256": _V3_PLAN_SHA256,
    }
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(_StopBeforeMesh, match="before the first mesh/solver"):
        run_p6_condensed_direct(
            resolved_payload,
            run_directory,
            source_sha=source_sha,
            task43_v2_diagnostic=v2_diagnostic,
            task43_v3_diagnostic=v3_diagnostic,
        )

    assert len(mesh_calls) == 1
    assert not (run_directory / "resolved_mesh").exists()
    assert not (run_directory / "mesh_3d.h5").exists()
    assert phase_path.is_file()
    phase_record = json.loads(phase_path.read_text())
    stage_path = run_directory / "stages.jsonl"
    assert stage_path.is_file()
    stages = [json.loads(line) for line in stage_path.read_text().splitlines()]
    stage_names = [item["stage"] for item in stages]
    assert stage_names[:3] == [
        "workflow_started",
        "p6_direct_resolved_profile_bound",
        "p6_direct_mesh_setup_started",
    ]
    assert phase_record["stage"].endswith("_FAILED")
    assert phase_record["facts"]["exception_type"] == "_StopBeforeMesh"
    summary = json.loads(
        (run_directory / "p6_condensed_direct_summary.json").read_text()
    )
    assert summary["failed_stage"] == "p6_direct_mesh_setup_started"
    assert summary["exception_type"] == "_StopBeforeMesh"
