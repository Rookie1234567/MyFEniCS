"""Pure-Python boundaries for the Task041 service finalizer."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from benchmarks.task041_balh_workflow import task041_schur_speed_v2_contract
from src.io.input_validation import task041_balh_phase_limits_for_model
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
