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
_V2_R10_PLAN = _REPO_ROOT / (
    "benchmarks/artifacts/task43/round10_p_only_authority_attempt1/"
    "plan_output/plans/round10_p_up.json"
)
_V2_ACCEPTANCE = _REPO_ROOT / (
    "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
)
_V2_SELECTION = _REPO_ROOT / (
    "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json"
)


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


def _a1_v3_main_args(run_directory: Path) -> list[str]:
    return [
        "--case",
        "round1_candidate_mpi1",
        "--run-root",
        str(run_directory),
        "--candidate-plan",
        str(_V2_R10_PLAN),
        "--candidate-id",
        "round10_p_up",
        "--candidate-acceptance-contract",
        str(_V2_ACCEPTANCE),
        "--candidate-parent-selection-record",
        str(_V2_SELECTION),
        "--same-lu-solve-residual-correction",
        "--direct-factor-backend",
        "mumps",
        "--same-lu-tightening",
        "--v2-diagnostic-phase",
        "A1_q",
        "--v2-contract",
        str(_REPO_ROOT / "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"),
        "--v2-contract-sha256",
        "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc",
        "--v3-failure-evidence",
        "--v3-contract",
        str(_REPO_ROOT / "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json"),
        "--v3-plan",
        str(_REPO_ROOT / "docs/task43_hp_adaptivity/diagnostic_plan_v3.md"),
    ]


def test_a1_actual_main_records_ledger_before_mesh_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Drive the actual V3 CLI with a sentinel at its first mesh call."""

    if not all(path.is_file() for path in (_V2_R10_PLAN, _V2_ACCEPTANCE, _V2_SELECTION)):
        pytest.skip("frozen A1 candidate inputs are ignored workstation artifacts")

    from benchmarks.task43_hp_adaptivity import h100_anchor

    phase_path = tmp_path / "watchdog" / "workflow_phase.json"
    phase_path.parent.mkdir()
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(phase_path.resolve()))
    expected_parent = int(os.environ["PHYSICAL_WATCHDOG_PARENT_PID"])
    assert expected_parent == os.getppid(), "test must run under the native watchdog"

    run_directory = tmp_path / "a1_run"
    mesh_calls: list[object] = []

    def stop_before_mesh(*_args: object, **_kwargs: object) -> None:
        assert phase_path.is_absolute() and phase_path.is_file()
        phase_record = json.loads(phase_path.read_text(encoding="utf-8"))
        assert phase_record["stage"] == "task43_v3_a1_mesh_setup_started"
        current_stages = [
            json.loads(line) for line in (run_directory / "stages.jsonl").read_text().splitlines()
        ]
        assert current_stages[-1]["stage"] == "task43_v3_a1_mesh_setup_started"
        mesh_calls.append(object())
        raise _StopBeforeMesh("sentinel at actual A1 mesh boundary")

    solver_calls: list[object] = []

    def fail_if_solver_called(*_args: object, **_kwargs: object) -> None:
        solver_calls.append(object())
        raise AssertionError("solver must not be reached by the mesh-boundary sentinel")

    monkeypatch.setattr(h100_anchor, "build_airbox_mesh_3d", stop_before_mesh)
    monkeypatch.setattr(
        h100_anchor, "run_stage4b_block_grating_3d_case", fail_if_solver_called
    )
    with pytest.raises(_StopBeforeMesh, match="actual A1 mesh boundary"):
        h100_anchor.main(_a1_v3_main_args(run_directory))

    assert len(mesh_calls) == 1
    assert not solver_calls
    assert not (run_directory / "resolved_mesh").exists()
    assert phase_path.is_file()
    phase_record = json.loads(phase_path.read_text(encoding="utf-8"))
    stages_path = run_directory / "stages.jsonl"
    assert stages_path.is_file()
    stages = [json.loads(line) for line in stages_path.read_text().splitlines()]
    stage_names = [row["stage"] for row in stages]
    assert stage_names[0] == "workflow_started"
    assert "task43_v3_a1_worker_identity_bound" in stage_names
    assert "task43_v3_a1_candidate_inputs_bound" in stage_names
    assert "task43_v3_a1_mesh_setup_started" in stage_names
    assert "task43_v3_a1_failed" in stage_names
    assert stage_names[-1] == "task43_v3_a1_failed"
    assert phase_record["stage"] == "task43_v3_a1_failed"
    assert phase_record["facts"]["exception_type"] == "_StopBeforeMesh"
    terminal = json.loads(
        (run_directory / "task43_v3_partial_terminal.json").read_text(encoding="utf-8")
    )
    terminal_ref = phase_record["facts"]["terminal_reference"]
    terminal_path = run_directory / "task43_v3_partial_terminal.json"
    assert Path(terminal_ref["path"]) == terminal_path
    assert terminal_ref["sha256"] == hashlib.sha256(terminal_path.read_bytes()).hexdigest()
    assert terminal["status"] == "INCOMPLETE"
    assert terminal["official_result"] is False
    assert terminal["continuation_all_false"] is True
    assert all(value is False for value in terminal["continuation"].values())
    assert terminal["source_identity"]["git_head"]
    assert terminal["continuation"]["cost_campaign"] is False
    assert terminal["continuation"]["iteration"] is False


@pytest.mark.parametrize("preserve_terminal", (False, True))
def test_a1_actual_main_rejects_nonempty_root_without_touching_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, preserve_terminal: bool
) -> None:
    """A refused root preserves every valid preexisting output byte."""

    if not all(path.is_file() for path in (_V2_R10_PLAN, _V2_ACCEPTANCE, _V2_SELECTION)):
        pytest.skip("frozen A1 candidate inputs are ignored workstation artifacts")

    from benchmarks.task43_hp_adaptivity import h100_anchor

    phase_path = tmp_path / "watchdog" / "workflow_phase.json"
    phase_path.parent.mkdir()
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(phase_path.resolve()))
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PARENT_PID", str(os.getppid()))

    run_directory = tmp_path / "existing_a1_run"
    solve_directory = run_directory / "solve"
    solve_directory.mkdir(parents=True)
    (solve_directory / "run_summary.json").write_text(
        json.dumps(
            {
                "schema": "task43.solve.run-summary.v1",
                "case_status": "completed",
                "official_result": True,
                "passed": True,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_directory / "task43_v2_a1_endpoint.json").write_text(
        json.dumps(
            {
                "schema": "task43.v2.a1.endpoint.v1",
                "status": "COMPLETED",
                "pass": True,
                "official_result": True,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if preserve_terminal:
        from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
            task43_v3_partial_terminal_record,
        )

        old_terminal = task43_v3_partial_terminal_record(
            phase="A1_q",
            source_identity={"git_head": "previous-fixture-head"},
            error="previous preserved failure",
            primary_before_extra_packet=None,
            primary_q_samples={},
            primary_q8_q10_bundle=None,
            pre_validation_checkpoint=None,
        )
        (run_directory / "task43_v3_partial_terminal.json").write_text(
            json.dumps(old_terminal, sort_keys=True), encoding="utf-8"
        )
    before_files = {
        str(path.relative_to(run_directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in run_directory.rglob("*")
        if path.is_file()
    }
    mesh_calls: list[object] = []
    solver_calls: list[object] = []

    def fail_if_mesh_called(*_args: object, **_kwargs: object) -> None:
        mesh_calls.append(object())
        raise AssertionError("mesh must not be called for a nonempty output root")

    def fail_if_solver_called(*_args: object, **_kwargs: object) -> None:
        solver_calls.append(object())
        raise AssertionError("solver must not be called for a nonempty output root")

    monkeypatch.setattr(h100_anchor, "build_airbox_mesh_3d", fail_if_mesh_called)
    monkeypatch.setattr(
        h100_anchor, "run_stage4b_block_grating_3d_case", fail_if_solver_called
    )
    with pytest.raises(RuntimeError, match="refusing to overwrite nonempty output root"):
        h100_anchor.main(_a1_v3_main_args(run_directory))

    after_files = {
        str(path.relative_to(run_directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in run_directory.rglob("*")
        if path.is_file()
    }
    assert after_files == before_files
    assert not mesh_calls
    assert not solver_calls


@pytest.mark.parametrize("identity_failure", ["missing_phase", "wrong_parent"])
def test_a1_actual_main_rejects_missing_phase_or_wrong_watchdog_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    identity_failure: str,
) -> None:
    """Fail at CLI preflight before any run directory or mesh is created."""

    from benchmarks.task43_hp_adaptivity import h100_anchor

    if identity_failure == "missing_phase":
        monkeypatch.delenv("PHYSICAL_WATCHDOG_PHASE_PATH", raising=False)
    else:
        phase_path = tmp_path / "watchdog" / "phase.json"
        phase_path.parent.mkdir()
        monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(phase_path.resolve()))
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_PARENT_PID", str(os.getppid() + 100000)
        )
    run_directory = tmp_path / identity_failure
    with pytest.raises(SystemExit) as error:
        h100_anchor.main(_a1_v3_main_args(run_directory))
    assert error.value.code == 2
    expected_message = (
        "V3 A1 requires native watchdog parent and phase identity"
        if identity_failure == "missing_phase"
        else "V3 A1 worker is not the direct child registered by its native watchdog"
    )
    assert expected_message in capsys.readouterr().err
    assert not run_directory.exists()
