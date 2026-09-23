"""Pure-Python boundaries for the Task041 service finalizer."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from benchmarks import task041_balh_workflow
from benchmarks.task041_balh_workflow import (
    TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
    TASK041_P4_BACKEND_PAIR_MODE,
    TASK041_REPRESENTATIVE_RHS_SCOPE,
    TASK041_SCHUR_SPEED_V2_PROFILE,
    TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    load_task041_representative_rhs_manifest,
    task041_p4_backend_pair_identity,
    task041_schur_speed_v2_contract,
)
from src.io.input_validation import (
    TASK041_BALH_2NM_MODEL_ID,
    task041_balh_phase_limits_for_model,
    task041_balh_service_contract,
)
from src.runners import task041_service as service
from src.runners import task041_supervisor as supervisor

MODEL = "task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8"
SOURCE_SHA = "a" * 40
INVOCATION_ID = "s1c4-test-invocation"
UNIT = "task041-s1c4-test.service"


def _write_ledger(path: Path, used: float = 100.0) -> None:
    supervisor._write_json(
        path,
        {
            "schema": "task041.compute_wall_ledger.v2",
            "profile_id": service.PROFILE,
            "used_compute_wall_seconds": used,
            "used_status": "measured_plus_conservative_upper_bound",
            "shared_S0_S1_S3_used_seconds": 0.0,
            "S2_used_seconds": used,
            "S4_used_seconds": 0.0,
            "batch_used_compute_wall_seconds": used,
            "source_records": [],
        },
    )


def _write_config(tmp_path: Path, *, root: Path | None = None) -> tuple[Path, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = root or tmp_path / "supervision"
    ledger = tmp_path / "ledger.json"
    _write_ledger(ledger)
    config = {
        "unit": UNIT,
        "model_id": MODEL,
        "source_sha": SOURCE_SHA,
        "ledger_path": str(ledger),
        "supervision_root": str(root),
        "public_command": [sys.executable, "-m", "tests.non_pde_public"],
        "global_swap_baseline": {
            "global_swap_used_bytes": 8192,
            "global_pswpin_pages": 0,
            "global_pswpout_pages": 2,
        },
    }
    path = tmp_path / "job_config.json"
    supervisor._write_json(path, config)
    return path, config


def _write_registered_2nm_config(
    tmp_path: Path, *, root: Path | None = None
) -> tuple[Path, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = root or tmp_path / "registered-2nm-supervision"
    contract = task041_balh_service_contract(TASK041_BALH_2NM_MODEL_ID)
    ledger = tmp_path / contract["ledger"]["filename"]
    supervisor._write_json(
        ledger,
        {
            "schema": "task041.compute_wall_ledger.v1",
            "case_id": TASK041_BALH_2NM_MODEL_ID,
            "profile_id": None,
            "limit_seconds": None,
            "used_compute_wall_seconds": 100.0,
            "used_status": "measured",
            "measured": {"status": "measured", "seconds": 100.0, "records": []},
            "source_records": [],
            "budget_semantics": contract["budget_semantics"],
        },
    )
    config = {
        "unit": UNIT,
        "model_id": TASK041_BALH_2NM_MODEL_ID,
        "source_sha": SOURCE_SHA,
        "ledger_path": str(ledger),
        "supervision_root": str(root),
        "public_command": [sys.executable, "-m", "tests.non_pde_public"],
        "global_swap_baseline": {
            "global_swap_used_bytes": 8192,
            "global_pswpin_pages": 0,
            "global_pswpout_pages": 2,
        },
    }
    path = tmp_path / "registered_2nm_job_config.json"
    supervisor._write_json(path, config)
    return path, config


def _identity(start_ns: int = 1_000_000_000) -> dict:
    return {
        "unit": UNIT,
        "main_pid": os.getpid(),
        "parent_pid": os.getppid(),
        "pid_starttime_ticks": 123,
        "invocation_id": INVOCATION_ID,
        "control_group": "/user.slice/task041-s1c4.scope",
        "proc_control_group": "/user.slice/task041-s1c4.scope",
        "systemd_fields": {
            "MainPID": str(os.getpid()),
            "InvocationID": INVOCATION_ID,
            "ControlGroup": "/user.slice/task041-s1c4.scope",
            "ExecMainStartTimestampMonotonic": str(start_ns // 1000),
        },
        "unit_start_monotonic_ns": start_ns,
    }


def _launch(config: dict, root: Path, start_ns: int = 1_000_000_000) -> dict:
    identity = _identity(start_ns)
    contract = task041_schur_speed_v2_contract(config["model_id"])
    return {
        "schema": service.LAUNCH_SCHEMA,
        "config_path": str(root.parent / "job_config.json"),
        "unit": config["unit"],
        "model_id": config["model_id"],
        "source_sha": config["source_sha"],
        "parent_pid": os.getpid(),
        "invocation_id": INVOCATION_ID,
        "ledger_path": config["ledger_path"],
        "supervision_root": str(root),
        "global_swap_baseline": config["global_swap_baseline"],
        "profile_id": service.PROFILE,
        "scope": contract["scope"],
        "representative_rhs_probe": None,
        "ledger_owner": service.LEDGER_OWNER,
        "service_identity": identity,
        "budget_snapshot_before": {
            "phase_group": "S2",
            "phase_used_before_seconds": 100.0,
            "batch_used_before_seconds": 100.0,
            "phase_limit_seconds": 7200.0,
            "batch_limit_seconds": 201600.0,
        },
    }


def _normal_terminal(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "_terminal_capture",
        lambda: {
            "SERVICE_RESULT": "success",
            "EXIT_CODE": "exited",
            "EXIT_STATUS": "0",
            "INVOCATION_ID": INVOCATION_ID,
            "available": True,
            "normal_exit": True,
        },
    )


def _closed_summaries(root: Path, *, parent: bool = True) -> None:
    if parent:
        supervisor._write_json(
            root / "service_parent_summary.json",
            {
                "pre_exit_membership": {
                    "members": [os.getpid()],
                    "expected_main_pid": os.getpid(),
                    "pass": True,
                }
            },
        )
    supervisor._write_json(
        root / "summary.json",
        {
            "status": "completed",
            "phase_result": {"returncode": 0},
        },
    )


def _patch_post(monkeypatch, *, post_result, post_error=None, captured=None):
    def fake_post(root, finalizer_root, contract, phase_limits, launch, remaining):
        if captured is not None:
            captured["remaining"] = remaining
        supervisor._write_json(
            finalizer_root / "artifact_hashes.json", {"pass": True}
        )
        return post_result, post_error

    monkeypatch.setattr(service, "_run_post_hash", fake_post)


def _controlled_summaries(
    root: Path,
    *,
    parent_members: list[int] | None = None,
    parent_pass: bool = False,
    public_status: str = "failed",
    public_returncode: int = -15,
    public_classification: str = "process_tree_rss_limit",
    reason: str = "process_tree_rss_limit",
) -> None:
    parent_pid = os.getpid()
    members = (
        [parent_pid, parent_pid + 1]
        if parent_members is None
        else parent_members
    )
    supervisor._write_json(
        root / "service_parent_summary.json",
        {
            "status": "pre_exit_failed",
            "public_supervision_completed": False,
            "public_result_classification": public_classification,
            "public_exit_status": public_returncode,
            "public_phase_termination_reason": reason,
            "public_phase_resource_classification": public_classification,
            "pre_exit_membership": {
                "members": members,
                "expected_main_pid": parent_pid,
                "pass": parent_pass,
            },
        },
    )
    supervisor._write_json(
        root / "summary.json",
        {
            "status": public_status,
            "result_classification": public_classification,
            "phase_result": {
                "returncode": public_returncode,
                "termination_reason": reason,
            },
        },
    )


def _controlled_terminal(monkeypatch, *, service_result="exit-code") -> None:
    monkeypatch.setattr(
        service,
        "_terminal_capture",
        lambda: {
            "SERVICE_RESULT": service_result,
            "EXIT_CODE": "exited",
            "EXIT_STATUS": "3",
            "INVOCATION_ID": INVOCATION_ID,
            "available": True,
            "normal_exit": False,
        },
    )


def test_service_probe_binding_is_fixed_to_scope(tmp_path):
    probe = tmp_path / "representative_rhs.json"
    probe.write_text("{}\n", encoding="utf-8")
    command = [
        sys.executable,
        "scripts/run_case.py",
        "input.dat",
        "--task041-rhs-probe",
        str(probe),
    ]

    binding = service._representative_rhs_probe_binding(command, "representative_rhs")

    assert binding == {
        "path": str(probe),
        "sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
    }
    with pytest.raises(service.Task041ServiceError):
        service._representative_rhs_probe_binding(command, "formal_consumer")


@pytest.mark.parametrize(
    "classification",
    [
        "PAIRING_SETUP_FAILURE",
        "NUMERICAL_GATE_FAIL",
        "ACTION_EQUIVALENCE_FAIL",
        "RESPONSE_SENSITIVITY_UNRESOLVED",
    ],
)
def test_consumer_result_preserves_common_partial_failure(classification, tmp_path):
    root = tmp_path / "consumer"
    root.mkdir()
    supervisor._write_json(
        root / "consumer_summary.json",
        {
            "schema": "task041.side_balh.common_layout_equivalence.v1",
            "status": "task041_common_layout_equivalence_failed",
            "classification": classification,
            "failure_evidence": {
                "ordinal": 0,
                "cause": "preserved partial evidence",
            },
            "markers": {"observed": []},
            "lifecycle": {
                "setup_released": False,
                "rss_marker_emitted": True,
            },
            "gates": {"pass": False},
        },
    )

    result = supervisor._consumer_result(
        root,
        process_group_gone=False,
        expected_side_setup_schedule="sequential_component",
        expected_comparison_mode="common_layout_equivalence",
    )

    assert result["complete"] is False
    assert result["classification"] == classification
    assert result["worker_classification"] == classification
    assert result["completion_scope"] == "representative_rhs"
    assert result["failure_evidence"]["ordinal"] == 0


def test_parent_writes_loader_identity_and_forwards_v2_limits(monkeypatch, tmp_path):
    config_path, config = _write_config(tmp_path)
    identity = _identity()
    monkeypatch.setattr(service, "_parent_unit_identity", lambda _unit: identity)
    monkeypatch.setattr(service, "_sparse_sample_factory", lambda: "sparse-sampler")
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 2_000_000_000)
    monkeypatch.setattr(
        service,
        "_cgroup_members",
        lambda _group: [os.getpid(), os.getpid() + 1],
    )
    observed = {}

    def fake_public(command, root, **kwargs):
        observed.update(command=command, kwargs=kwargs)
        launch = kwargs["launch_manifest"]
        assert launch["parent_pid"] == os.getpid()
        assert launch["invocation_id"] == INVOCATION_ID
        Path(root).mkdir(parents=True, exist_ok=True)
        supervisor._write_json(Path(root) / "launch_manifest.json", launch)
        return {
            "status": "completed",
            "result_classification": "worker_exit0",
            "phase_result": {"returncode": 0, "wall_seconds": 1.0},
        }

    monkeypatch.setattr(
        supervisor, "run_task041_supervised_public_command", fake_public
    )
    result = service.run_service_parent(config_path)

    assert result["status"] == "pre_exit_failed"
    assert observed["command"] == config["public_command"]
    assert observed["kwargs"]["sample_factory"] == "sparse-sampler"
    limits = observed["kwargs"]["resource_limits"]
    assert limits["min_cgroup_ancestor_headroom_bytes"] == limits[
        "min_memavailable_bytes"
    ]
    assert limits["swap_limit_bytes"] == 0
    baseline = observed["kwargs"]["global_swap_baseline"]
    assert baseline == config["global_swap_baseline"]
    assert baseline["global_swap_used_bytes"] == 8192
    assert baseline["global_pswpin_pages"] == 0
    assert baseline["global_pswpout_pages"] == 2
    manifest = supervisor._read_json(
        Path(config["supervision_root"]) / "launch_manifest.json"
    )
    assert manifest["parent_pid"] == os.getpid()
    assert manifest["invocation_id"] == INVOCATION_ID
    assert manifest["scope"] == "formal_consumer"
    assert manifest["representative_rhs_probe"] is None
    assert result["pre_exit_membership"]["pass"] is False


def test_registered_2nm_parent_and_finalizer_keep_unlimited_budget(monkeypatch, tmp_path):
    config_path, config = _write_registered_2nm_config(tmp_path)
    identity = _identity()
    observed = {}

    monkeypatch.setattr(service, "_parent_unit_identity", lambda _unit: identity)
    monkeypatch.setattr(service, "_cgroup_members", lambda _group: [os.getpid()])
    monkeypatch.setattr(service, "_sparse_sample_factory", lambda: "case-sampler")

    def fake_public(command, root, **kwargs):
        observed.update(command=command, kwargs=kwargs)
        launch = kwargs["launch_manifest"]
        Path(root).mkdir(parents=True, exist_ok=True)
        supervisor._write_json(Path(root) / "launch_manifest.json", launch)
        supervisor._write_json(
            Path(root) / "summary.json",
            {
                "status": "completed",
                "result_classification": "worker_exit0",
                "phase_result": {"returncode": 0, "wall_seconds": 2.0},
            },
        )
        return {
            "status": "completed",
            "result_classification": "worker_exit0",
            "phase_result": {"returncode": 0, "wall_seconds": 2.0},
        }

    monkeypatch.setattr(
        supervisor, "run_task041_supervised_public_command", fake_public
    )
    parent = service.run_service_parent(config_path)

    assert parent["status"] == "pre_exit_ok"
    assert observed["command"] == config["public_command"]
    assert observed["kwargs"]["profile_contract"]["case_id"] == (
        TASK041_BALH_2NM_MODEL_ID
    )
    limits = observed["kwargs"]["resource_limits"]
    assert limits["timeout_seconds"] is None
    assert limits["time_stop_enforced"] is False
    assert limits["hard_memory_bytes"] == 1759218604442
    assert observed["kwargs"]["launch_manifest"]["case_id"] == (
        TASK041_BALH_2NM_MODEL_ID
    )
    assert observed["kwargs"]["launch_manifest"]["contract_kind"] == (
        "task041_registered_case_service"
    )

    captured = {}

    def fake_post(root, finalizer_root, contract, phase_limits, launch, remaining):
        captured.update(
            contract=contract,
            phase_limits=phase_limits,
            launch=launch,
            remaining=remaining,
        )
        supervisor._write_json(
            finalizer_root / "artifact_hashes.json", {"pass": True}
        )
        return (
            {
                "returncode": 0,
                "termination_reason": None,
                "partial": False,
                "process_group_gone": True,
            },
            None,
        )

    monkeypatch.setattr(service, "_run_post_hash", fake_post)
    _normal_terminal(monkeypatch)
    finalizer = service.run_service_finalize(config_path)

    assert captured["remaining"] is None
    assert captured["phase_limits"]["timeout_seconds"] is None
    assert captured["phase_limits"]["time_stop_enforced"] is False
    assert finalizer["status"] == "completed"
    assert finalizer["checks"]["post_hash_phase_completed"] is True
    assert finalizer["checks"]["ledger_written"] is True
    ledger = supervisor._read_json(Path(config["ledger_path"]))
    assert ledger["case_id"] == TASK041_BALH_2NM_MODEL_ID
    assert ledger["limit_seconds"] is None
    assert ledger["profile_id"] is None
    assert len(ledger["source_records"]) == 1
    assert ledger["used_compute_wall_seconds"] > 100.0


def test_fixed_pair_service_requires_full_config_and_canonical_v5_path(tmp_path):
    repository_root = Path(__file__).resolve().parents[2]
    manifest_path = (
        repository_root
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    canonical_ledger = task041_balh_workflow.task041_review_v5_ledger_path(
        repository_root
    )
    command = [
        sys.executable,
        "scripts/run_case.py",
        "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat",
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
        "--task041-side-setup-schedule",
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "--task041-comparison-mode",
        TASK041_P4_BACKEND_PAIR_MODE,
        "--task041-rhs-probe",
        str(manifest_path),
    ]
    config = {
        "model_id": TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "performance_profile": TASK041_SCHUR_SPEED_V2_PROFILE,
        "ledger_path": canonical_ledger,
        "public_command": command,
    }

    contract = service._service_contract(
        config,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert contract["p4_backend_pair_identity"]["rhs_count"] == 8
    assert contract["memory_cap_bytes"] == 68_719_476_736
    assert contract["warning_memory_bytes"] == 61_847_529_062
    assert contract["registered_memory_cap_bytes"] == 53_221_163_008
    assert contract["registered_memory_cap_source"] == (
        "review_report_v2_section_5_explicit_cap"
    )
    assert contract["memory_cap_source"] == (
        "user_authorized_single_5nm_fixed8_p4_backend_pair_64_gib"
    )
    assert contract["ledger"]["schema"] == (
        "task041.review_v5.r1_load_ledger.v1"
    )
    with pytest.raises(ValueError, match="complete 5 nm|sequential_component"):
        service._service_contract(
            config,
            side_setup_schedule=None,
            comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        )
    with pytest.raises(service.Task041ServiceError, match="canonical Review V5"):
        service._service_contract(
            {**config, "ledger_path": tmp_path / "wrong-ledger.json"},
            side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        )
    with pytest.raises(service.Task041ServiceError, match="config and command"):
        service._service_contract(
            {**config, "performance_profile": None},
            side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        )
    with pytest.raises(service.Task041ServiceError, match="comparison mode"):
        service._comparison_mode_binding(command, "common_layout_equivalence")


def test_fixed_pair_public_supervision_ignores_v2_clock_but_keeps_resource_gate(
    monkeypatch, tmp_path
):
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    manifest = load_task041_representative_rhs_manifest(manifest_path)
    contract = task041_schur_speed_v2_contract(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
    )
    contract["p4_backend_pair_identity"] = task041_p4_backend_pair_identity(
        model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        rhs_probe_binding=manifest,
    )
    canonical_ledger = tmp_path / "canonical-v5.json"
    contract["ledger"]["path"] = str(canonical_ledger)
    monkeypatch.setattr(
        task041_balh_workflow,
        "task041_review_v5_ledger_path",
        lambda _root: canonical_ledger,
    )
    resource_limits = {
        "warning_memory_bytes": 240_518_168_576,
        "hard_memory_bytes": 274_877_906_944,
        "swap_limit_bytes": 0,
        "min_memavailable_bytes": 412_316_860_416,
        "min_cgroup_ancestor_headroom_bytes": 412_316_860_416,
    }
    observed = {}

    def fake_run_phase(_phase, _command, _root, **kwargs):
        observed.update(kwargs)
        return {
            "returncode": -15,
            "termination_reason": "process_tree_rss_limit",
            "process_group_gone": True,
        }

    monkeypatch.setattr(supervisor, "_run_phase", fake_run_phase)
    pair_result = supervisor.run_task041_supervised_public_command(
        [sys.executable, "scripts/run_case.py"],
        tmp_path / "pair-supervision",
        profile_contract=contract,
        ledger_snapshot={
            "schema": "task041.review_v5.r1_load_ledger.v1",
            "used_compute_wall_seconds": 300_000.0,
        },
        resource_limits=resource_limits,
        environment={name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
        sample_factory=lambda _pid: {},
        repository_root=tmp_path,
        launch_manifest={"ledger_path": str(canonical_ledger)},
    )
    assert pair_result["result_classification"] == "process_tree_rss_limit"
    assert pair_result["budget"]["effective_remaining_seconds"] is None
    assert observed["timeout_seconds"] is None
    assert observed["phase_elapsed_timeout"] is False
    assert observed["cumulative_compute_limit_seconds"] is None
    assert observed["enforce_time_stops"] is False
    assert observed["process_tree_rss_warning_bytes"] == 61_847_529_062
    assert observed["process_tree_rss_cap_bytes"] == 68_719_476_736
    assert observed["warning_memory_bytes"] == 240_518_168_576
    assert observed["hard_memory_bytes"] == 274_877_906_944
    assert observed["min_memavailable_bytes"] == 412_316_860_416
    assert observed["min_cgroup_ancestor_headroom_bytes"] == 412_316_860_416

    legacy_contract = task041_schur_speed_v2_contract(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    legacy_result = supervisor.run_task041_supervised_public_command(
        [sys.executable, "scripts/run_case.py"],
        tmp_path / "legacy-v2-supervision",
        profile_contract=legacy_contract,
        ledger_snapshot={
            "schema": "task041.compute_wall_ledger.v2",
            "used_compute_wall_seconds": 201_600.0,
            "batch_used_compute_wall_seconds": 201_600.0,
            "shared_S0_S1_S3_used_seconds": 21_600.0,
        },
        resource_limits=resource_limits,
        environment={name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
        sample_factory=lambda _pid: {},
        repository_root=tmp_path,
    )
    assert legacy_result["result_classification"] == "cumulative_wall_timeout"


def test_fixed_pair_service_finalizer_appends_one_v5_record_after_parent(
    monkeypatch, tmp_path
):
    repository_root = Path(__file__).resolve().parents[2]
    manifest_path = (
        repository_root
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    ledger_path = tmp_path / "r1_load_ledger.json"
    def canonical_v5(_root):
        return ledger_path

    monkeypatch.setattr(service, "task041_review_v5_ledger_path", canonical_v5)
    monkeypatch.setattr(task041_balh_workflow, "task041_review_v5_ledger_path", canonical_v5)
    old_entries = [
        {"id": "old-1", "seconds": 10.0},
        {"id": "old-2", "seconds": 20.0},
    ]
    old_payload = {
        "schema": "task041.review_v5.r1_load_ledger.v1",
        "scope": "r1_load_ledger",
        "ledger_status": "measured_plus_conservative_upper_bound",
        "charge_rule": {"basis": "one service-unit interval"},
        "charged_seconds": 300_000.0,
        "entries": old_entries,
    }
    supervisor._write_json(ledger_path, old_payload)
    root = tmp_path / "pair-service-root"
    config = {
        "unit": UNIT,
        "model_id": TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        "source_sha": SOURCE_SHA,
        "ledger_path": str(ledger_path),
        "supervision_root": str(root),
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "performance_profile": TASK041_SCHUR_SPEED_V2_PROFILE,
        "side_setup_schedule": TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "comparison_mode": TASK041_P4_BACKEND_PAIR_MODE,
        "public_command": [
            sys.executable,
            "scripts/run_case.py",
            "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat",
            "--task041-performance-profile",
            TASK041_SCHUR_SPEED_V2_PROFILE,
            "--task041-side-setup-schedule",
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            "--task041-comparison-mode",
            TASK041_P4_BACKEND_PAIR_MODE,
            "--task041-rhs-probe",
            str(manifest_path),
        ],
        "global_swap_baseline": {
            "global_swap_used_bytes": 0,
            "global_pswpin_pages": 0,
            "global_pswpout_pages": 0,
        },
    }
    config_path = tmp_path / "pair-job-config.json"
    supervisor._write_json(config_path, config)
    identity = _identity(start_ns=1_000_000_000_000)
    monkeypatch.setattr(service, "_parent_unit_identity", lambda _unit: identity)
    monkeypatch.setattr(service, "_cgroup_members", lambda _group: [os.getpid()])
    monkeypatch.setattr(service, "_sparse_sample_factory", lambda: "pair-sampler")
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 2_000_000_000_000)
    public_observed = {}

    def fake_public(command, supervision_root, **kwargs):
        public_observed.update(command=command, kwargs=kwargs)
        Path(supervision_root).mkdir(parents=True, exist_ok=True)
        supervisor._write_json(
            Path(supervision_root) / "launch_manifest.json",
            kwargs["launch_manifest"],
        )
        supervisor._write_json(
            Path(supervision_root) / "summary.json",
            {
                "status": "completed",
                "result_classification": "worker_exit0",
                "phase_result": {"returncode": 0, "wall_seconds": 3.0},
            },
        )
        return {
            "status": "completed",
            "result_classification": "worker_exit0",
            "phase_result": {"returncode": 0, "wall_seconds": 3.0},
        }

    monkeypatch.setattr(
        supervisor, "run_task041_supervised_public_command", fake_public
    )
    parent = service.run_service_parent(config_path)
    assert parent["status"] == "pre_exit_ok"
    assert public_observed["kwargs"]["profile_contract"][
        "compute_wall_unlimited"
    ] is True
    assert public_observed["kwargs"]["ledger_snapshot"][
        "used_compute_wall_seconds"
    ] == 300_000.0
    assert public_observed["kwargs"]["resource_limits"]["timeout_seconds"] is None
    assert public_observed["kwargs"]["resource_limits"]["time_stop_enforced"] is False
    assert public_observed["kwargs"]["launch_manifest"]["ledger_path"] == str(
        ledger_path
    )
    assert supervisor._read_json(ledger_path) == old_payload

    finalizer_observed = {}

    def fake_post(_root_path, finalizer_root, contract, phase_limits, launch, remaining):
        finalizer_observed.update(
            contract=contract,
            phase_limits=phase_limits,
            launch=launch,
            remaining=remaining,
        )
        supervisor._write_json(
            finalizer_root / "artifact_hashes.json", {"pass": True}
        )
        return (
            {
                "returncode": 0,
                "termination_reason": None,
                "partial": False,
                "process_group_gone": True,
            },
            None,
        )

    monkeypatch.setattr(service, "_run_post_hash", fake_post)
    _normal_terminal(monkeypatch)
    finalizer = service.run_service_finalize(config_path)
    assert finalizer["status"] == "completed"
    assert finalizer["checks"]["ledger_written"] is True
    assert finalizer_observed["remaining"] is None
    assert finalizer_observed["phase_limits"]["timeout_seconds"] is None
    assert finalizer_observed["phase_limits"]["time_stop_enforced"] is False
    assert finalizer["timing"]["basis"] == (
        "fixed-eight-RHS V5 ledger has no elapsed wall limit"
    )

    updated = supervisor._read_json(ledger_path)
    assert updated["schema"] == old_payload["schema"]
    assert updated["charge_rule"] == old_payload["charge_rule"]
    assert updated["entries"][: len(old_entries)] == old_entries
    new_entries = updated["entries"][len(old_entries) :]
    assert len(new_entries) == 1
    assert new_entries[0]["p4_backend_pair_identity"]["rhs_count"] == 8
    assert "case_id" not in new_entries[0]
    assert updated["charged_seconds"] == pytest.approx(
        old_payload["charged_seconds"] + new_entries[0]["seconds"]
    )


def test_finalize_deducts_unit_wall_once_and_limits_post_time(monkeypatch, tmp_path):
    config_path, config = _write_config(tmp_path)
    root = Path(config["supervision_root"])
    root.mkdir()
    supervisor._write_json(root / "launch_manifest.json", _launch(config, root))
    _closed_summaries(root)
    _normal_terminal(monkeypatch)
    captured = {}
    _patch_post(
        monkeypatch,
        captured=captured,
        post_result={
            "returncode": 0,
            "termination_reason": None,
            "partial": False,
            "process_group_gone": True,
        },
    )
    monkeypatch.setattr(service, "_cgroup_members", lambda _group: [os.getpid()])
    clock = iter((51_000_000_000, 71_000_000_000))
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: next(clock))

    result = service.run_service_finalize(config_path)

    assert result["status"] == "completed"
    assert captured["remaining"] == pytest.approx(7050.0)
    ledger = supervisor._read_json(Path(config["ledger_path"]))
    assert ledger["S2_used_seconds"] == pytest.approx(170.0)
    assert ledger["batch_used_compute_wall_seconds"] == pytest.approx(170.0)
    assert len(ledger["source_records"]) == 1


def test_finalize_missing_parent_summary_still_posts_and_records_ledger(
    monkeypatch, tmp_path
):
    config_path, config = _write_config(tmp_path)
    root = Path(config["supervision_root"])
    root.mkdir()
    supervisor._write_json(root / "launch_manifest.json", _launch(config, root))
    _closed_summaries(root, parent=False)
    _normal_terminal(monkeypatch)
    _patch_post(
        monkeypatch,
        post_result={
            "returncode": 0,
            "termination_reason": None,
            "partial": False,
            "process_group_gone": True,
        },
    )
    monkeypatch.setattr(service, "_cgroup_members", lambda _group: [os.getpid()])
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 6_000_000_000)

    result = service.run_service_finalize(config_path)

    assert result["status"] == "failed"
    assert result["checks"]["parent_summary_present"] is False
    assert result["ledger"]["status"] == "written"
    assert supervisor._read_json(Path(config["ledger_path"]))[
        "batch_used_compute_wall_seconds"
    ] == pytest.approx(105.0)


@pytest.mark.parametrize(
    ("start_us", "same_invocation", "expected_ledger"),
    ((1_000_000, True, True), (0, True, False), (1_000_000, False, False)),
    ids=("start-proven", "start-zero", "invocation-mismatch"),
)
def test_finalize_missing_launch_only_records_proven_unit_wall(
    monkeypatch, tmp_path, start_us, same_invocation, expected_ledger
):
    config_path, config = _write_config(tmp_path)
    root = Path(config["supervision_root"])
    root.mkdir()
    invocation = INVOCATION_ID if same_invocation else "other-invocation"
    monkeypatch.setattr(
        service,
        "_systemd_identity",
        lambda _unit: {
            "MainPID": "0",
            "InvocationID": invocation,
            "ControlGroup": "/user.slice/task041-s1c4.scope",
            "ExecMainStartTimestampMonotonic": str(start_us),
        },
    )
    monkeypatch.setattr(
        service,
        "_terminal_capture",
        lambda: {
            "SERVICE_RESULT": "success",
            "EXIT_CODE": "exited",
            "EXIT_STATUS": "0",
            "INVOCATION_ID": INVOCATION_ID,
            "available": True,
            "normal_exit": True,
        },
    )
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 6_000_000_000)

    result = service.run_service_finalize(config_path)

    assert result["status"] == "failed"
    assert result["result_classification"] == "launch_manifest_missing"
    assert result["timing"]["unit_elapsed_seconds"] == (
        pytest.approx(5.0) if expected_ledger else None
    )
    assert (result["ledger"]["status"] == "written") is expected_ledger
    if expected_ledger:
        assert supervisor._read_json(Path(config["ledger_path"]))[
            "batch_used_compute_wall_seconds"
        ] == pytest.approx(105.0)


@pytest.mark.parametrize(
    ("post_result", "post_error"),
    (
        (
            {
                "returncode": 0,
                "termination_reason": "phase_exception",
                "partial": True,
                "process_group_gone": True,
            },
            None,
        ),
        (
            {
                "returncode": 0,
                "termination_reason": None,
                "partial": False,
                "process_group_gone": True,
            },
            {"type": "Task041SupervisorError", "message": "tail sample failed"},
        ),
    ),
    ids=("terminal-sample-failure", "post-error"),
)
def test_finalize_rejects_post_sampling_failure_but_writes_terminal_record(
    monkeypatch, tmp_path, post_result, post_error
):
    config_path, config = _write_config(tmp_path)
    root = Path(config["supervision_root"])
    root.mkdir()
    supervisor._write_json(root / "launch_manifest.json", _launch(config, root))
    _closed_summaries(root)
    _normal_terminal(monkeypatch)
    _patch_post(
        monkeypatch,
        post_result=post_result,
        post_error=post_error,
    )
    monkeypatch.setattr(service, "_cgroup_members", lambda _group: [os.getpid()])
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 6_000_000_000)

    result = service.run_service_finalize(config_path)

    assert result["status"] == "failed"
    assert result["checks"]["post_hash_phase_completed"] is False
    assert result["checks"]["ledger_written"] is True
    assert (root / "finalizer" / "finalizer_summary.json").is_file()


def test_fixed_hash_and_post_command_keep_closed_root_separate(monkeypatch, tmp_path):
    root = tmp_path / "closed"
    root.mkdir()
    for relative in service.FIXED_ARTIFACTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    output = tmp_path / "finalizer" / "artifact_hashes.json"
    result = service.hash_closed_root(root, output)
    assert result["pass"] is True
    assert set(result["artifacts"]) == set(service.FIXED_ARTIFACTS)
    assert json.loads(output.read_text(encoding="utf-8"))["pass"] is True

    captured = {}

    def fake_run_phase(phase, argv, phase_root, **kwargs):
        captured.update(phase=phase, argv=argv, phase_root=phase_root, kwargs=kwargs)
        return {
            "returncode": 0,
            "termination_reason": None,
            "partial": False,
            "process_group_gone": True,
        }

    monkeypatch.setattr(supervisor, "_run_phase", fake_run_phase)
    monkeypatch.setattr(service, "_sparse_sample_factory", lambda: "sparse")
    _config_path, config = _write_config(tmp_path / "config")
    root2 = Path(config["supervision_root"])
    finalizer_root = root2 / "finalizer"
    contract = task041_schur_speed_v2_contract(MODEL)
    phase_limits = dict(task041_balh_phase_limits_for_model(MODEL, "consumer"))
    phase_limits["min_cgroup_ancestor_headroom_bytes"] = phase_limits[
        "min_memavailable_bytes"
    ]
    launch = _launch(config, root2)
    post, error = service._run_post_hash(
        root2, finalizer_root, contract, phase_limits, launch, 5.0
    )

    assert error is None
    assert post["returncode"] == 0
    assert captured["argv"][0] == sys.executable
    assert captured["argv"][1:4] == ["-m", "src.runners.task041_service", "hash"]
    assert captured["kwargs"]["sample_root_pid"] == os.getpid()
    assert captured["kwargs"]["memory_stages_path"] != root2 / "memory_stages.jsonl"
    assert captured["kwargs"]["enforce_time_stops"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "terminal-result",
        "public-status",
        "parent-completed",
        "parent-binding",
        "membership",
        "post-cgroup",
    ],
    ids=(
        "controlled-stop",
        "wrong-service-result",
        "wrong-public-status",
        "parent-reports-completed",
        "contradictory-parent",
        "unknown-pre-exit-membership",
        "post-cgroup-residual",
    ),
)
def test_finalize_accepts_only_bound_controlled_stop(
    monkeypatch, tmp_path, mutation
):
    config_path, config = _write_config(tmp_path)
    root = Path(config["supervision_root"])
    root.mkdir()
    supervisor._write_json(root / "launch_manifest.json", _launch(config, root))
    _controlled_summaries(root)
    _controlled_terminal(
        monkeypatch,
        service_result="success" if mutation == "terminal-result" else "exit-code",
    )
    if mutation == "public-status":
        public = supervisor._read_json(root / "summary.json")
        public["status"] = "completed"
        supervisor._write_json(root / "summary.json", public)
    elif mutation == "parent-completed":
        parent = supervisor._read_json(root / "service_parent_summary.json")
        parent["public_supervision_completed"] = True
        supervisor._write_json(root / "service_parent_summary.json", parent)
    elif mutation == "parent-binding":
        parent = supervisor._read_json(root / "service_parent_summary.json")
        parent["public_exit_status"] = -9
        supervisor._write_json(root / "service_parent_summary.json", parent)
    elif mutation == "membership":
        parent = supervisor._read_json(root / "service_parent_summary.json")
        parent["pre_exit_membership"] = None
        supervisor._write_json(root / "service_parent_summary.json", parent)
    _patch_post(
        monkeypatch,
        post_result={
            "returncode": 0,
            "termination_reason": None,
            "partial": False,
            "process_group_gone": True,
        },
    )
    monkeypatch.setattr(
        service,
        "_cgroup_members",
        lambda _group: [os.getpid(), os.getpid() + 2]
        if mutation == "post-cgroup"
        else [os.getpid()],
    )
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 6_000_000_000)

    result = service.run_service_finalize(config_path)

    if mutation is None:
        assert result["status"] == "completed"
        assert result["result_classification"] == "controlled_stop"
        assert result["completion_scope"] == "service_finalization"
        assert result["public_summary"]["completed"] is False
        assert result["checks"]["pre_exit_members_clean"] is False
        assert result["checks"]["pre_exit_membership_record"] is True
        assert result["parent_summary"]["pre_exit_members"] == [
            os.getpid(),
            os.getpid() + 1,
        ]
        assert result["controlled_stop"]["checks"]["service_terminal_exit3"] is True
        assert result["controlled_stop"]["checks"]["public_failed"] is True
        assert (
            result["controlled_stop"]["checks"][
                "parent_reports_supervision_failure"
            ]
            is True
        )
        assert (
            result["controlled_stop"]["checks"]["parent_phase_result_binding"]
            is True
        )
        assert result["controlled_stop"]["termination_reason"] == (
            "process_tree_rss_limit"
        )
    else:
        assert result["status"] == "failed"
        assert result["result_classification"] == "service_boundary_failure"
        assert result["controlled_stop"]["active"] is False
