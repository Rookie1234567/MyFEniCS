"""Pure-Python boundaries for the Task041 service finalizer."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
    TASK041_BALH_2NM_CELL_CONDENSED_MODEL_ID,
    TASK041_BALH_2NM_MODEL_ID,
    TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID,
    TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID,
    task041_balh_case,
    task041_balh_phase_limits_for_model,
    task041_balh_service_contract,
)
from src.runners import task041_service as service
from src.runners import task041_supervisor as supervisor

MODEL = "task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8"
SOURCE_SHA = "a" * 40
INVOCATION_ID = "s1c4-test-invocation"
UNIT = "task041-s1c4-test.service"


def test_task041_modal_policy_binding_stays_outside_numerical_imports():
    child = r'''
import json
import sys

def deny_process_creation(event, _args):
    if event in {"subprocess.Popen", "os.system", "os.fork", "os.posix_spawn"}:
        raise RuntimeError("metadata binding attempted to start a child process")

sys.addaudithook(deny_process_creation)

from benchmarks import task041_balh_workflow as workflow
from src.solvers import task041_modal_policy as policy

common = dict(
    enabled=True,
    candidate=True,
    mpi_size=8,
    mode_count=400,
    p4_inverse_backend="cell_condensed",
    p4_refinement_target_tolerance=5.0e-13,
    task041_resource_policy=workflow.TASK041_V8_SWAP_OBSERVE_CONTINUE,
    expected_rank_cpus=tuple(range(10, 18)),
)
v13_common = dict(
    common,
    expected_rank_cpus=workflow.TASK041_V13_MPI8_RANK_CPUS,
)
model_id = workflow.TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID
default = workflow.task041_fixed_h6_modal_gmres_binding(model_id, **common)
v12 = workflow.task041_fixed_h6_modal_gmres_binding(
    model_id,
    modal_solver_policy=policy.TASK041_V12_MODAL_SOLVER_POLICY_ID,
    **common,
)
v13 = workflow.task041_fixed_h6_modal_gmres_binding(
    model_id,
    modal_solver_policy=policy.TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
    **v13_common,
)
if "modal_solver_policy" in default:
    raise AssertionError("legacy fixed-H6 binding gained a policy")
if "memory_policy" in default or "membind_node" in default:
    raise AssertionError("legacy fixed-H6 binding changed memory semantics")
if v12["modal_solver_policy"]["policy_id"] != policy.TASK041_V12_MODAL_SOLVER_POLICY_ID:
    raise AssertionError("V12 policy binding mismatch")
if "memory_policy" in v12 or "membind_node" in v12:
    raise AssertionError("V12 binding changed its historical memory contract")
if v13["modal_solver_policy"]["policy_id"] != policy.TASK041_V13_CONSISTENT_MODAL_POLICY_ID:
    raise AssertionError("V13 policy binding mismatch")
if v13["memory_policy"] != workflow.TASK041_V13_MEMORY_POLICY:
    raise AssertionError("V13 memory policy mismatch")
if "membind_node" not in v13 or v13["membind_node"] is not None:
    raise AssertionError("V13 did not explicitly resolve unbound memory")
if v13["expected_rank_cpus"] != list(workflow.TASK041_V13_MPI8_RANK_CPUS):
    raise AssertionError("V13 frozen MPI8 CPU map mismatch")
if v13["required_thread_environment"] != workflow.TASK041_V13_REQUIRED_THREAD_ENVIRONMENT:
    raise AssertionError("V13 required thread environment mismatch")
if v13["resource_headroom_policy"] != workflow.TASK041_V13_RESOURCE_HEADROOM_POLICY:
    raise AssertionError("V13 aggregate resource policy mismatch")
try:
    workflow.task041_fixed_h6_modal_gmres_binding(
        model_id,
        modal_solver_policy=policy.TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
        **common,
    )
except ValueError:
    pass
else:
    raise AssertionError("V13 accepted the legacy/test CPU map")
wrong = dict(v13["modal_solver_policy"])
wrong["outer_threshold"] = 1.0e-8
try:
    policy.resolve_task041_modal_solver_policy(wrong)
except ValueError:
    pass
else:
    raise AssertionError("modified policy contract was accepted")

for name in (
    "mpi4py",
    "petsc4py",
    "slepc4py",
    "dolfinx",
    "src.solvers.hybrid_fem_modal_block_ldu",
):
    if name in sys.modules:
        raise AssertionError(f"metadata binding imported numerical module: {name}")
print(json.dumps({"default": True, "v12": True, "v13": True}))
'''
    result = subprocess.run(
        [sys.executable, "-c", child],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "default": True,
        "v12": True,
        "v13": True,
    }

    from src.solvers import hybrid_fem_modal_block_ldu as numerical_core
    from src.solvers import task041_modal_policy as pure_policy

    assert (
        numerical_core.resolve_task041_modal_solver_policy
        is pure_policy.resolve_task041_modal_solver_policy
    )
    for name in (
        "TASK041_V12_MODAL_SOLVER_POLICY_ID",
        "TASK041_V12_MODAL_BACKUP_POLICY_ID",
        "TASK041_V12_MODAL_BACKUP_QUALIFICATION_METHOD",
        "TASK041_V13_CONSISTENT_MODAL_POLICY_ID",
        "_TASK041_V12_MODAL_SOLVER_POLICY",
        "_TASK041_V12_MODAL_BACKUP_POLICY",
        "_TASK041_V13_CONSISTENT_MODAL_POLICY",
    ):
        assert getattr(numerical_core, name) is getattr(pure_policy, name)


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
    output_root = tmp_path / "parent-output"
    config["output_root"] = str(output_root)
    config_path = output_root / "runtime_service_config.json"
    service.bind_task041_output_roots(
        output_root,
        config["supervision_root"],
        config_path,
        create_output=True,
    )
    supervisor._write_json(config_path, config)
    assert not os.path.lexists(config["supervision_root"])
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
    assert manifest["output_root_binding"]["output_root"] == str(output_root)
    assert manifest["output_root_binding"]["supervision_root_absent_by_lexists"] is True
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
    assert contract["memory_cap_bytes"] == 53_221_163_008
    assert contract["warning_memory_bytes"] == 47_899_046_707
    assert contract["registered_memory_cap_bytes"] == 53_221_163_008
    assert contract["registered_memory_cap_source"] == (
        "review_report_v2_section_5_explicit_cap"
    )
    assert contract["memory_cap_source"] == (
        "review_report_v2_section_5_explicit_cap"
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

    correction_command = [
        *command,
        "--task041-top-causal-replay",
        "--task041-p4-response-correction-steps",
        "1",
    ]
    correction_config = {
        **config,
        "public_command": correction_command,
        "p4_response_correction_steps": 1,
    }
    assert service._p4_response_correction_steps_binding(
        correction_command, 1
    ) == 1
    correction_contract = service._service_contract(
        correction_config,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        p4_response_correction_steps=1,
    )
    assert correction_contract["top_causal_replay"] is True
    assert correction_contract["p4_response_correction"]["requested_steps"] == 1
    with pytest.raises(service.Task041ServiceError, match="does not match service config"):
        service._p4_response_correction_steps_binding(correction_command, 0)
    with pytest.raises(service.Task041ServiceError, match="top causal replay"):
        service._p4_response_correction_steps_binding(
            [*command, "--task041-p4-response-correction-steps", "1"], 1
        )

    target_command = [
        *command,
        "--task041-p4-refinement-target-tolerance",
        "5e-13",
        "--task041-p4-backend-pair-side",
        "bottom",
    ]
    target_config = {
        **config,
        "public_command": target_command,
        "p4_refinement_target_tolerance": 5.0e-13,
        "p4_backend_pair_side": "bottom",
    }
    target_binding = service._p4_refinement_target_binding(
        target_command,
        target_config["p4_refinement_target_tolerance"],
        target_config["p4_backend_pair_side"],
        model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert target_binding[2]["selected_side"] == "bottom"
    target_contract = service._service_contract(
        target_config,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        p4_refinement_target_tolerance=5.0e-13,
        p4_backend_pair_side="bottom",
    )
    target_contract_binding = target_contract["p4_refinement_target"]
    assert all(
        target_contract_binding[key] == value
        for key, value in target_binding[2].items()
    )
    assert target_contract_binding["max_corrections_per_p4_call"] == 2
    assert target_contract_binding["original_gates_unchanged"] is True

    formal_target_command = [
        sys.executable,
        "scripts/run_case.py",
        "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat",
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
        "--task041-p4-refinement-target-tolerance",
        "5e-13",
    ]
    formal_target_config = {
        "model_id": TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        "scope": None,
        "performance_profile": TASK041_SCHUR_SPEED_V2_PROFILE,
        "ledger_path": canonical_ledger,
        "public_command": formal_target_command,
        "p4_refinement_target_tolerance": 5.0e-13,
        "p4_backend_pair_side": None,
    }
    formal_target_binding = service._p4_refinement_target_binding(
        formal_target_command,
        5.0e-13,
        None,
        model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
        scope=None,
        side_setup_schedule=None,
        comparison_mode=None,
    )
    assert formal_target_binding[2] == {
        "scope": "registered_5nm_formal_consumer_target",
        "tolerance": 5.0e-13,
        "selected_side": None,
    }
    formal_target_contract = service._service_contract(
        formal_target_config,
        side_setup_schedule=None,
        comparison_mode=None,
        p4_refinement_target_tolerance=5.0e-13,
        p4_backend_pair_side=None,
    )
    formal_contract_binding = formal_target_contract["p4_refinement_target"]
    assert all(
        formal_contract_binding[key] == value
        for key, value in formal_target_binding[2].items()
    )
    assert formal_contract_binding["max_corrections_per_p4_call"] == 2
    assert formal_contract_binding["original_gates_unchanged"] is True
    with pytest.raises(
        service.Task041ServiceError,
        match="P4 refinement target options do not match service config",
    ):
        service._p4_refinement_target_binding(
            target_command,
            5.0e-13,
            "top",
            model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
            profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
            scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
            side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
        )
    for incompatible in (
        [*target_command, "--task041-top-causal-replay"],
        [*target_command, "--task041-p4-correction-replay-from", "g1"],
        [*target_command, "--task041-p4-response-correction-steps", "1"],
    ):
        with pytest.raises(service.Task041ServiceError, match="cannot be combined"):
            service._p4_refinement_target_binding(
                incompatible,
                5.0e-13,
                "bottom",
                model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
                profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
                scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
                side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
                comparison_mode=TASK041_P4_BACKEND_PAIR_MODE,
            )


def test_task041_output_binding_and_real_supervised_child_manifest_order(
    tmp_path,
):
    output_root = tmp_path / "attempt-out"
    supervision_root = tmp_path / "attempt-supervision"
    runtime_config = output_root / "runtime_service_config.json"
    prepared = service.bind_task041_output_roots(
        output_root,
        supervision_root,
        runtime_config,
        create_output=True,
    )
    assert output_root.is_dir()
    assert not os.path.lexists(supervision_root)
    assert output_root.parent == supervision_root.parent
    assert prepared["binding_state"] == (
        "out_created_exclusively_sup_reserved_for_supervisor"
    )
    supervisor._write_json(runtime_config, {"prepared": True})
    bound = service.bind_task041_output_roots(
        output_root,
        supervision_root,
        runtime_config,
        create_output=False,
    )
    assert bound["binding_state"] == (
        "runtime_config_bound_out_present_sup_absent_before_dispatch"
    )

    child = """import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
manifest_arg = sys.argv.index('--task041-supervision-record')
manifest_path = pathlib.Path(sys.argv[manifest_arg + 1])
manifest = json.loads(manifest_path.read_text())
if not manifest_path.is_file():
    raise SystemExit(21)
if manifest_path.parent != pathlib.Path(manifest['supervision_root']):
    raise SystemExit(22)
if pathlib.Path(manifest['config_path']) != out / 'runtime_service_config.json':
    raise SystemExit(23)
if not pathlib.Path(manifest['config_path']).is_file():
    raise SystemExit(24)
if manifest['output_root_binding']['output_root'] != str(out):
    raise SystemExit(25)
(out / 'child_receipt.json').write_text(json.dumps({
    'launch_manifest_visible_before_child_receipt': True,
    'launch_manifest': str(manifest_path),
    'config_path': manifest['config_path'],
}))
"""
    model_id = TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    profile = task041_schur_speed_v2_contract(model_id)
    ledger = {
        "schema": "task041.compute_wall_ledger.v2",
        "used_compute_wall_seconds": 0.0,
        "batch_used_compute_wall_seconds": 0.0,
        "shared_S0_S1_S3_used_seconds": 0.0,
        "S2_used_seconds": 0.0,
        "S4_used_seconds": 0.0,
    }

    def sample_factory(pid):
        pid = int(pid)
        return {
            "memory_authority_bytes": 4096,
            "job_no_swap": True,
            "process_tree": {
                "all_status_readable": True,
                "rss_bytes": 4096,
                "swap_bytes": 0,
                "pids": [pid],
                "rss_by_pid_bytes": {str(pid): 4096},
                "swap_by_pid_bytes": {str(pid): 0},
                "smaps": {"pss_bytes": 2048, "uss_bytes": 1024},
            },
            "host_memory": {
                "mem_available_bytes": 2**50,
                "mem_total_bytes": 2**50,
            },
            "global_swap": {"used_bytes": 0, "readable": True},
            "job_cgroup": {"dedicated_job_cgroup": False},
        }

    result = supervisor.run_task041_supervised_public_command(
        [sys.executable, "-c", child, str(output_root)],
        supervision_root,
        profile_contract=profile,
        ledger_snapshot=ledger,
        resource_limits={
            "warning_memory_bytes": 10**7,
            "hard_memory_bytes": 10**8,
            "swap_limit_bytes": 0,
            "min_memavailable_bytes": None,
            "min_cgroup_ancestor_headroom_bytes": None,
        },
        environment={name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
        sample_factory=sample_factory,
        repository_root=tmp_path,
        launch_manifest={
            "config_path": str(runtime_config),
            "supervision_root": str(supervision_root),
            "output_root_binding": bound,
        },
    )
    assert result["status"] == "completed"
    assert result["phase_result"]["returncode"] == 0
    receipt = json.loads((output_root / "child_receipt.json").read_text())
    assert receipt["launch_manifest_visible_before_child_receipt"] is True
    existing_manifest = supervision_root / "launch_manifest.json"
    assert existing_manifest.is_file()
    existing_manifest_bytes = existing_manifest.read_bytes()

    popen_calls = []

    def unexpected_spawn(*args, **kwargs):
        popen_calls.append((args, kwargs))
        raise AssertionError("existing SUP must reject before child spawn")

    with pytest.raises(FileExistsError):
        supervisor.run_task041_supervised_public_command(
            [sys.executable, "-c", child, str(output_root)],
            supervision_root,
            profile_contract=profile,
            ledger_snapshot=ledger,
            resource_limits={
                "warning_memory_bytes": 10**7,
                "hard_memory_bytes": 10**8,
                "swap_limit_bytes": 0,
                "min_memavailable_bytes": None,
                "min_cgroup_ancestor_headroom_bytes": None,
            },
            environment={
                name: "1" for name in supervisor.TASK041_REQUIRED_THREADS
            },
            sample_factory=sample_factory,
            repository_root=tmp_path,
            popen_factory=unexpected_spawn,
            launch_manifest={
                "config_path": str(runtime_config),
                "supervision_root": str(supervision_root),
                "output_root_binding": bound,
            },
        )
    assert popen_calls == []
    assert existing_manifest.read_bytes() == existing_manifest_bytes


@pytest.mark.parametrize("existing_kind", ("directory", "dangling_symlink"))
def test_task041_output_binding_rejects_any_existing_sup_before_out_create(
    tmp_path, existing_kind
):
    output_root = tmp_path / "new-attempt-out"
    supervision_root = tmp_path / "reserved-supervision"
    runtime_config = output_root / "runtime_service_config.json"
    if existing_kind == "directory":
        supervision_root.mkdir()
        marker = supervision_root / "launch_manifest.json"
        marker.write_text('{"existing":true}\n')
        original_marker = marker.read_bytes()
    else:
        supervision_root.symlink_to(tmp_path / "missing-supervision-target")
    with pytest.raises(service.Task041ServiceError, match="SUP already exists"):
        service.bind_task041_output_roots(
            output_root,
            supervision_root,
            runtime_config,
            create_output=True,
        )
    assert os.path.lexists(supervision_root)
    assert not os.path.lexists(output_root)
    if existing_kind == "directory":
        assert marker.read_bytes() == original_marker


def test_task041_output_binding_rejects_runtime_config_in_sup(tmp_path):
    output_root = tmp_path / "out"
    supervision_root = tmp_path / "sup"
    runtime_config = supervision_root / "runtime_service_config.json"
    with pytest.raises(service.Task041ServiceError, match="direct file inside OUT"):
        service.bind_task041_output_roots(
            output_root,
            supervision_root,
            runtime_config,
            create_output=True,
        )
    assert not output_root.exists()
    assert not os.path.lexists(supervision_root)


def test_task041_output_binding_requires_sibling_roots_and_exclusive_out(tmp_path):
    output_root = tmp_path / "out"
    supervision_root = tmp_path / "nested" / "sup"
    runtime_config = output_root / "runtime_service_config.json"
    with pytest.raises(service.Task041ServiceError, match="distinct sibling"):
        service.bind_task041_output_roots(
            output_root,
            supervision_root,
            runtime_config,
            create_output=True,
        )
    assert not os.path.lexists(output_root)

    supervision_root = tmp_path / "sup"
    output_root.mkdir()
    sentinel = output_root / "existing.marker"
    sentinel.write_text("preserve\n", encoding="utf-8")
    with pytest.raises(service.Task041ServiceError, match="OUT already exists"):
        service.bind_task041_output_roots(
            output_root,
            supervision_root,
            runtime_config,
            create_output=True,
        )
    assert sentinel.read_text(encoding="utf-8") == "preserve\n"
    assert not os.path.lexists(supervision_root)


def test_v13_candidate_helper_forwards_real_factory_callback_into_ldu_guard(
    tmp_path, monkeypatch
):
    """Use the real candidate helper, LDU guards, and production factory callback.

    Only the bridge object, staged-factor implementation, and modal numerical
    builder are stubbed. The actual factory closure, candidate-to-LDU call,
    authority callback, and both independent refusal matchers remain active.
    """

    from types import SimpleNamespace

    from benchmarks import task041_exact_side_workflow as worker
    from src.io.input_validation import (
        TASK041_BALH_CELL_CONDENSED_RESERVE_BYTES,
        TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES,
        TASK041_BALH_W0P7NM_P6_PILOT_WARNING_MEMORY_BYTES,
    )
    from src.runners import task041_supervisor
    from src.solvers import hybrid_fem_modal_block_ldu as block_ldu
    from src.solvers import petsc_lu_stage
    from src.solvers import physical_balanced_side_inverse as side_inverse
    from src.test.test_349_task041_balh_side_inverse import _build_fixture

    class EightRankRootFixture:
        rank = 0
        size = 8

        @staticmethod
        def allgather(value):
            return [value] * 8

        @staticmethod
        def bcast(value, root):
            assert root == 0
            return value

    comm = EightRankRootFixture()
    binding = {
        "schema": "task041.w0p7.supervisor_memory_binding.v1",
        "invocation_id": "factory-route-fixture",
        "source_sha": "a" * 40,
        "unit": "factory-route-fixture.service",
        "launch_manifest_sha256": "b" * 64,
        "supervisor_root_pid": 424242,
    }
    monitor = {
        **binding,
        "sample_root_pid": binding["supervisor_root_pid"],
        "file_age_seconds": 0.1,
        "phase": "public_command",
        "sample_role": "phase_running",
        "sample_row_sha256": "c" * 64,
    }
    raw_sample = {
        "process_tree": {
            "all_status_readable": True,
            "rss_bytes": 1024,
            "pids": [binding["supervisor_root_pid"]],
        },
        "job_cgroup": {
            "dedicated_job_cgroup": True,
            "memory_current_bytes": 1024,
            "ancestor_hard_limit_state": "max_or_unlimited",
            "ancestor_memory_headroom_bytes": None,
        },
        "host_memory": {"mem_available_bytes": 2**50},
        "memory_authority_bytes": 1024,
    }
    monkeypatch.setattr(
        worker, "_task041_latest_supervisor_memory_sample", lambda _binding: monitor
    )
    monkeypatch.setattr(worker, "_resource_snapshot", lambda _pid: raw_sample)
    monkeypatch.setattr(
        worker, "_task041_node_memfree_bytes", lambda _node: 2**50
    )

    bridge_path = tmp_path / "test-bridge.so"
    bridge_path.write_bytes(b"metadata-only bridge fixture")
    bridge = SimpleNamespace(
        __file__=str(bridge_path),
        petsc_int_sizeof=4,
        mumps_package_version_major=5,
        mumps_package_version_minor=6,
        mumps_package_version_subminor=2,
    )

    class StubStagedMumpsFactory:
        def __init__(self, *_args, **_kwargs):
            self.live_factor_inventory = {}

    monkeypatch.setattr(petsc_lu_stage, "load_lu_stage_bridge", lambda _path: bridge)
    monkeypatch.setattr(
        petsc_lu_stage, "StagedMumpsLUFactory", StubStagedMumpsFactory
    )
    limits = {
        "hard_memory_bytes": TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES,
        "process_tree_rss_cap_bytes": TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES,
        "process_tree_rss_warning_bytes": TASK041_BALH_W0P7NM_P6_PILOT_WARNING_MEMORY_BYTES,
        "min_memavailable_bytes": TASK041_BALH_CELL_CONDENSED_RESERVE_BYTES,
    }
    stage_factory, _stage_binding = worker._build_task041_w0p7_stage_factory(
        bridge_path,
        supervisor_memory_binding=binding,
        comm=comm,
        limits=limits,
        expected_rank_cpus=tuple(range(8)),
        memory_policy=task041_balh_workflow.TASK041_V13_MEMORY_POLICY,
        marker_callback=lambda *_args: None,
        failure_evidence={},
    )
    production_factory_callback = stage_factory.v13_fresh_authority_callback

    bottom_inverse, bottom_owned = _build_fixture(size=1)
    top_inverse, top_owned = _build_fixture(size=1)
    setup = SimpleNamespace(
        bottom=bottom_owned["side_system"],
        top=top_owned["side_system"],
        coupling=SimpleNamespace(),
    )
    layout = SimpleNamespace(modal_owner=7, local_size=1)

    class FixtureAction(side_inverse.FixedPhysicalBalancedActiveTraceAction):
        @property
        def audit(self):
            return {"destroyed": True}

    def create_fixture_action(_self):
        return object.__new__(FixtureAction)

    monkeypatch.setattr(
        side_inverse.SideBalancedInverse,
        "create_fixed_physical_balh_active_trace_action",
        create_fixture_action,
    )
    observed = {}

    class AuthorityRefusalReached(RuntimeError):
        pass

    def invoke_real_factory_callback(
        _coupling,
        _bottom_action,
        _top_action,
        *,
        fresh_authority_callback,
        **_kwargs,
    ):
        observed["callback"] = fresh_authority_callback
        report = {"phase": "outer_restart32_workspace", "target_restart": 32}
        response = fresh_authority_callback("outer_restart32_workspace", report)
        observed["response"] = response
        assert response["status"] == "refused"
        assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
            "outer_restart32_workspace", report, response, rank_count=8
        )
        assert not task041_supervisor._v13_outer_authority_pass_matches_report(
            "outer_restart32_workspace", report, response, rank_count=8
        )
        raise AuthorityRefusalReached("factory callback refusal reached LDU path")

    monkeypatch.setattr(
        block_ldu,
        "build_task041_v13_consistent_modal_surrogate",
        invoke_real_factory_callback,
    )
    sample_columns = list(range(8))
    roles = {str(column): ["registered_fixture"] for column in sample_columns}
    callback = lambda *_args, **_kwargs: None
    try:
        with pytest.raises(AuthorityRefusalReached, match="reached LDU path"):
            worker._task041_create_candidate_ldu_context(
                layout,
                setup,
                {"bottom": bottom_inverse, "top": top_inverse},
                sampled_column_contract={
                    "columns": sample_columns,
                    "roles": roles,
                    "sha256": "d" * 64,
                },
                marker_callback=callback,
                use_anderson_modal_inner=False,
                fixed_h6_modal_gmres_research=True,
                fixed_h6_modal_feedback_method=None,
                modal_solver_policy=block_ldu.resolve_task041_modal_solver_policy(
                    block_ldu.TASK041_V13_CONSISTENT_MODAL_POLICY_ID
                ),
                modal_snapshot_callback=None,
                factor_stage_factory=stage_factory,
                complex_qr_research=False,
                capture_modal_solve_trace=False,
            )
        assert observed["callback"] is production_factory_callback
        assert observed["response"]["status"] == "refused"
    finally:
        bottom_inverse.destroy()
        top_inverse.destroy()
        bottom_owned["operator"].destroy()
        top_owned["operator"].destroy()


@pytest.mark.parametrize("failure", ("jsonable", "append", "resource_check"))
def test_v13_outer_marker_write_failure_broadcasts_before_failing(
    tmp_path, monkeypatch, failure
):
    """Exercise the rank-0 status protocol with injected serialization/I/O failure.

    This is a single-process protocol fixture; it checks that the production
    writer broadcasts its failure status, not that an MPI runtime was launched.
    """

    from benchmarks import task041_exact_side_workflow as worker

    output_root = tmp_path / "markers-root"
    if failure in {"jsonable", "resource_check"}:
        output_root.mkdir()

    class ProtocolComm:
        rank = 0
        size = 2

        def __init__(self):
            self.broadcasts = []

        def allgather(self, value):
            return [dict(value), {**dict(value), "rank": 1}]

        def bcast(self, value, root):
            assert root == 0
            self.broadcasts.append(value)
            return value

    comm = ProtocolComm()
    monkeypatch.setattr(worker, "_resource_snapshot", lambda: {"sample": 1})
    if failure == "resource_check":
        def reject_resource(*_args, **_kwargs):
            raise RuntimeError("synthetic resource rejection")

        monkeypatch.setattr(worker, "_check_resource", reject_resource)
    else:
        monkeypatch.setattr(
            worker, "_check_resource", lambda *_args, **_kwargs: None
        )
    if failure == "jsonable":
        def fail_jsonable(_value):
            raise TypeError("synthetic marker conversion failure")

        monkeypatch.setattr(worker, "_jsonable", fail_jsonable)

    with pytest.raises(
        RuntimeError, match="marker collective failed"
    ) as collective_error:
        worker._write_v13_outer_authority_marker_collective(
            output_root,
            1.0,
            {"request": {"phase": "outer_restart32_workspace"}},
            environment={"fixture": True},
            comm=comm,
            schema=task041_balh_workflow.TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA,
            limits={},
            enforce_time_stop=False,
        )

    assert len(comm.broadcasts) == 1
    if failure == "jsonable":
        assert isinstance(comm.broadcasts[0]["error"], str)
        assert comm.broadcasts[0]["ok"] is False
        assert "synthetic marker conversion failure" in comm.broadcasts[0]["error"]
    elif failure == "append":
        assert isinstance(comm.broadcasts[0]["error"], str)
        assert comm.broadcasts[0]["ok"] is False
        assert "FileNotFoundError" in comm.broadcasts[0]["error"]
    else:
        assert comm.broadcasts[0]["ok"] is True
        assert comm.broadcasts[0]["error"] is None
        assert "synthetic resource rejection" in str(collective_error.value)
        marker = json.loads(
            (output_root / "markers.jsonl").read_text(encoding="utf-8")
        )
        assert marker["rank_resource_samples"][0]["resource"] == {"sample": 1}
        assert "synthetic resource rejection" in marker["rank_resource_samples"][0][
            "resource_error"
        ]


def test_v13_outer_marker_writer_real_mpi2_append_and_write_failure(monkeypatch):
    """Check marker append and failed-write collectives with two MPI ranks."""

    import shutil
    import tempfile

    from mpi4py import MPI

    from benchmarks import task041_exact_side_workflow as worker

    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("the marker writer regression requires exactly MPI2")

    shared = None
    if comm.rank == 0:
        try:
            shared = {"root": tempfile.mkdtemp(prefix="task041-v13-marker-mpi2-")}
        except Exception as exc:  # noqa: BLE001 - broadcast setup failure to both ranks
            shared = {"error": f"{type(exc).__name__}: {exc}"}
    shared = comm.bcast(shared, root=0)
    if not isinstance(shared, dict) or "root" not in shared:
        pytest.fail(f"rank 0 could not create shared marker fixture: {shared!r}")
    root = Path(shared["root"])

    monkeypatch.setattr(
        worker,
        "_resource_snapshot",
        lambda: {"rank": int(comm.rank), "sample": 1},
    )
    monkeypatch.setattr(worker, "_check_resource", lambda *_args, **_kwargs: None)

    success_error = None
    try:
        worker._write_v13_outer_authority_marker_collective(
            root,
            1.0,
            {"phase": "outer_restart32_workspace", "target_restart": 32},
            environment={"fixture": "mpi2"},
            comm=comm,
            schema=task041_balh_workflow.TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA,
            limits={},
            enforce_time_stop=False,
        )
    except Exception as exc:  # noqa: BLE001 - compare each rank's observed failure
        success_error = f"{type(exc).__name__}: {exc}"
    success_errors = comm.allgather(success_error)

    marker_line = None
    if comm.rank == 0:
        try:
            marker_line = (root / "markers.jsonl").read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - keep cleanup collective below
            marker_line = f"READ_ERROR:{type(exc).__name__}:{exc}"
    marker_line = comm.bcast(marker_line, root=0)

    write_error = None
    try:
        worker._write_v13_outer_authority_marker_collective(
            root / "missing-directory",
            1.0,
            {"phase": "outer_restart32_workspace", "target_restart": 32},
            environment={"fixture": "mpi2"},
            comm=comm,
            schema=task041_balh_workflow.TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA,
            limits={},
            enforce_time_stop=False,
        )
    except Exception as exc:  # noqa: BLE001 - all ranks should receive root refusal
        write_error = f"{type(exc).__name__}: {exc}"
    write_errors = comm.allgather(write_error)

    cleanup_error = None
    if comm.rank == 0:
        try:
            shutil.rmtree(root)
        except Exception as exc:  # noqa: BLE001 - broadcast cleanup result
            cleanup_error = f"{type(exc).__name__}: {exc}"
    cleanup_error = comm.bcast(cleanup_error, root=0)

    assert success_errors == [None, None]
    assert isinstance(marker_line, str) and not marker_line.startswith("READ_ERROR:")
    marker = json.loads(marker_line)
    assert marker["schema"] == task041_balh_workflow.TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA
    assert marker["stage"] == "v13_outer_workspace_authority"
    assert [row["resource"]["rank"] for row in marker["rank_resource_samples"]] == [0, 1]
    assert marker["detail"]["target_restart"] == 32
    assert len(write_errors) == 2
    assert all(error is not None for error in write_errors)
    assert write_errors[0] == write_errors[1]
    assert "marker collective failed" in write_errors[0]
    assert "FileNotFoundError" in write_errors[0]
    assert cleanup_error is None


def test_v15_modal_snapshot_writer_real_mpi2_preserves_primary_and_broadcasts_write_failure(
    monkeypatch,
):
    """Use the real MPI2 owner writer and retain the primary row-gate refusal."""

    import shutil
    import tempfile

    import numpy as np
    from mpi4py import MPI

    from benchmarks import task041_exact_side_workflow as worker
    from src.solvers import hybrid_fem_modal_block_ldu as block_ldu

    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("the V15 evidence writer regression requires exactly MPI2")
    modal_owner = 1
    shared = None
    if comm.rank == 0:
        try:
            shared = {"root": tempfile.mkdtemp(prefix="task041-v15-snapshot-mpi2-")}
        except Exception as exc:  # noqa: BLE001 - broadcast fixture setup failure
            shared = {"error": f"{type(exc).__name__}: {exc}"}
    shared = comm.bcast(shared, root=0)
    if not isinstance(shared, dict) or "root" not in shared:
        pytest.fail(f"rank 0 could not create shared V15 fixture: {shared!r}")
    root = Path(shared["root"])
    source_sha = "a" * 64
    packet_sha = hashlib.sha256(b"v15-real-mpi2-snapshot-fixture").hexdigest()
    identity = {"test": "V15 real MPI2 writer protocol", "source_sha": source_sha}
    consumer_binding = {"fixture_scope": "writer protocol only; no FE solve"}

    def writer(payload):
        return worker._write_task041_v13_modal_evidence_snapshot(
            root,
            payload,
            source_sha=source_sha,
            identity=identity,
            packet_manifest_sha256=packet_sha,
            consumer_binding=consumer_binding,
        )

    def system_for(snapshot_callback):
        system = object.__new__(block_ldu.Task041V13ConsistentModalSurrogateSystem)
        system.comm = comm
        system.rank = int(comm.rank)
        system.modal_owner = modal_owner
        system._snapshot_callback = snapshot_callback
        system._original_modal_row_snapshot_slots = set()
        system._last_original_modal_row = None
        system._last_original_modal_row_arrays = None
        system._last_original_modal_row_snapshot_receipt = None
        return system

    system = system_for(writer)
    primary_record = {
        "status": "rejected",
        "classification": "numeric_gate_reject",
        "attempt_index": 7,
        "reason": "eta_terms_inf_exceeded_1e-10",
        "nonfinite_nan": float("nan"),
        "nonfinite_positive_infinity": float("inf"),
    }
    system.record_original_modal_row(
        primary_record,
        {"d": np.asarray([complex(float("nan"), float("inf"))])},
    )
    success_receipt = system.persist_v13_evidence_snapshot(
        {
            "snapshot_kind": "v15_terminal_numeric_reject",
            "attempt_index": 7,
            "record": primary_record,
            "arrays": {
                "d": np.asarray([complex(float("nan"), float("inf"))]),
                "w_modal": np.asarray([1.0 + 0.0j]),
            },
        }
    )
    success_rows = comm.allgather(success_receipt)
    assert success_rows == [success_rows[0], success_rows[0]]
    assert success_receipt["status"] == "written"

    success_artifact_check = None
    if comm.rank == modal_owner:
        try:
            index_path = root / "numerical_output" / "v13_modal_row_evidence" / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            artifact_record = index["records"]["v15_terminal_numeric_reject"]
            if artifact_record["metadata"]["record"]["nonfinite_nan"] != {
                "value": None,
                "nonfinite": "NaN",
            }:
                raise AssertionError("NaN JSON marker differs")
            if artifact_record["metadata"]["record"][
                "nonfinite_positive_infinity"
            ] != {"value": None, "nonfinite": "+Inf"}:
                raise AssertionError("infinity JSON marker differs")
            artifact_path = root / artifact_record["path"]
            if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != (
                artifact_record["sha256"]
            ):
                raise AssertionError("owner snapshot hash mismatch")
            with np.load(artifact_path, allow_pickle=False) as artifact:
                if not np.isnan(artifact["d"].real[0]) or not np.isinf(
                    artifact["d"].imag[0]
                ):
                    raise AssertionError("NPZ did not retain raw non-finite values")
            success_artifact_check = {
                "status": "readable_with_raw_nonfinite_values"
            }
        except Exception as exc:  # noqa: BLE001 - broadcast owner reader failure before assertion
            success_artifact_check = {
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:400]}",
            }
    success_artifact_check = comm.bcast(success_artifact_check, root=modal_owner)
    assert success_artifact_check["status"] == "readable_with_raw_nonfinite_values", (
        success_artifact_check
    )

    original_path_open = Path.open

    def fail_owner_npz_open(path, *args, **kwargs):
        if (
            comm.rank == modal_owner
            and path.name == ".v15_evidence_failure.npz.tmp"
        ):
            raise OSError("injected owner snapshot write failure")
        return original_path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_owner_npz_open)
    failed_system = system_for(writer)
    failed_primary = {
        "status": "rejected",
        "classification": "numeric_gate_reject",
        "attempt_index": 8,
        "reason": "original row gate remains primary",
    }
    failed_system.record_original_modal_row(failed_primary)
    failure_receipt = failed_system.persist_v13_evidence_snapshot(
        {
            "snapshot_kind": "v15_evidence_failure",
            "attempt_index": 8,
            "record": {"snapshot_write_is_secondary": True},
            "arrays": {"d": np.asarray([0.0 + 0.0j])},
        }
    )
    failure_rows = comm.allgather(failure_receipt)
    assert failure_rows == [failure_rows[0], failure_rows[0]]
    assert failure_receipt["status"] == "failed"
    assert "injected owner snapshot write failure" in str(
        failure_receipt["error"]
    )
    frozen_failure = failed_system.frozen_original_modal_row()
    assert frozen_failure["record"] == failed_primary
    assert frozen_failure["arrays"] is None

    cleanup_error = None
    if comm.rank == 0:
        try:
            shutil.rmtree(root)
        except Exception as exc:  # noqa: BLE001 - report cleanup status collectively
            cleanup_error = f"{type(exc).__name__}: {exc}"
    cleanup_error = comm.bcast(cleanup_error, root=0)
    assert cleanup_error is None


def test_v15_real_tiny_builder_pc_owner_writer_failure_mpi2(
    monkeypatch, tmp_path
):
    """Reuse test350's real tiny V13 builder and PC, not a hand-made system."""

    from mpi4py import MPI

    if MPI.COMM_WORLD.size != 2:
        pytest.skip("the real tiny builder writer-failure path requires MPI2")
    from src.test.test_350_task041_balh_block_ldu import (
        _exercise_v13_unmocked_builder_owner_lu_and_original_modal_row_math,
    )

    _exercise_v13_unmocked_builder_owner_lu_and_original_modal_row_math(
        monkeypatch,
        tmp_path,
        inject_owner_writer_failure=True,
    )


@pytest.mark.parametrize(
    "callback_failure", ("invalid_response", "exception", "invalid_request")
)
def test_v13_outer_authorization_marker_preserves_raw_failure_evidence(
    callback_failure,
):
    from src.solvers import hybrid_fem_modal_block_ldu as block_ldu

    class SelfCollective:
        rank = 0
        size = 1

        @staticmethod
        def allgather(value):
            return [value]

    raw_response = {
        "schema": "incorrect.schema",
        "status": "refused",
        "decision": "stop",
        "authority_receipt_payload": {"refusal_reason": "fixture evidence"},
    }
    marker_records = []

    def authority_callback(_phase, _report):
        if callback_failure == "exception":
            raise ValueError("synthetic authority callback failure")
        return raw_response

    system = object.__new__(block_ldu.Task041V13ConsistentModalSurrogateSystem)
    system._destroyed = False
    system._fresh_authority_callback = authority_callback
    system._marker_callback = lambda _stage, detail: marker_records.append(detail)
    system.comm = SelfCollective()

    report = (
        {"fixture_request": float("nan")}
        if callback_failure == "invalid_request"
        else {"fixture_request": 1}
    )
    expected_error = (
        "outer restart report is unbindable"
        if callback_failure == "invalid_request"
        else "authority validation failed"
    )
    with pytest.raises(RuntimeError, match=expected_error):
        system.authorize_outer_workspace(
            "outer_restart32_workspace", report
        )

    assert len(marker_records) == 1
    detail = marker_records[0]
    assert detail["validation_error"]
    if callback_failure == "invalid_request":
        assert detail["request_validation_error"]
        assert detail["request_json"] is None
        assert detail["response"] is None
        assert detail["rank_validation"] == []
        return
    rank_row = detail["rank_validation"][0]
    if callback_failure == "invalid_response":
        assert json.loads(rank_row["raw_response"]) == raw_response
        assert json.loads(rank_row["raw_receipt"]) == raw_response[
            "authority_receipt_payload"
        ]
        assert "incorrect.schema" in rank_row["raw_response"]
    else:
        assert rank_row["raw_response"] is None
        assert rank_row["raw_receipt"] is None
        assert "synthetic authority callback failure" in rank_row["error"]


def test_v13_outer_marker_callback_mismatch_fails_before_authority_collective():
    """Optional component markers must be consistently present across ranks."""

    from src.solvers import hybrid_fem_modal_block_ldu as block_ldu

    class MixedMarkerCollective:
        rank = 0
        size = 2

        def __init__(self):
            self.calls = 0

        def allgather(self, value):
            self.calls += 1
            if self.calls == 1:
                return [
                    dict(value),
                    {**dict(value), "rank": 1, "marker_callback_available": False},
                ]
            return [value, value]

    authority_calls = []
    marker_calls = []
    system = object.__new__(block_ldu.Task041V13ConsistentModalSurrogateSystem)
    system._destroyed = False
    system._fresh_authority_callback = (
        lambda *_args: authority_calls.append("called")
    )
    system._marker_callback = lambda *_args: marker_calls.append("called")
    system.comm = MixedMarkerCollective()

    with pytest.raises(RuntimeError, match="marker callback availability differs"):
        system.authorize_outer_workspace(
            "outer_restart32_workspace", {"target_restart": 32}
        )
    assert authority_calls == []
    assert marker_calls == []


def test_registered_5nm_formal_target_keeps_case_resource_and_time_contract(
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    model_id = TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID
    input_path = (
        repository_root
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_cell_condensed.dat"
    )
    case = task041_balh_case(model_id)
    assert case["p4_inverse_backend"] == "cell_condensed"
    registered = task041_balh_service_contract(model_id)
    ledger_path = (
        repository_root / registered["ledger"]["path"]
    ).resolve()
    command = [
        sys.executable,
        "scripts/run_case.py",
        str(input_path),
        "--producer-packet-root",
        str(tmp_path / "producer"),
        "--task041-p4-refinement-target-tolerance",
        "5e-13",
    ]
    config = {
        "model_id": model_id,
        "scope": "formal_consumer",
        "performance_profile": None,
        "ledger_path": ledger_path,
        "public_command": command,
        "p4_refinement_target_tolerance": 5.0e-13,
        "p4_backend_pair_side": None,
    }
    tolerance, side, binding = service._p4_refinement_target_binding(
        command,
        config["p4_refinement_target_tolerance"],
        config["p4_backend_pair_side"],
        model_id=model_id,
        profile_id=None,
        scope=None,
        side_setup_schedule=None,
        comparison_mode=None,
    )
    assert tolerance == 5.0e-13
    assert side is None
    assert binding["scope"] == (
        "registered_5nm_cell_condensed_formal_consumer_target"
    )
    contract = service._service_contract(
        config,
        side_setup_schedule=None,
        comparison_mode=None,
        p4_refinement_target_tolerance=tolerance,
        p4_backend_pair_side=side,
    )
    assert contract["p4_refinement_target"]["tolerance"] == 5.0e-13
    assert contract["p4_refinement_target"]["max_corrections_per_p4_call"] == 2
    assert contract["memory_cap_bytes"] == 53_221_163_008
    assert contract["warning_memory_bytes"] == 47_899_046_707
    assert contract["runtime_reserve_bytes"] == 412_316_860_416
    assert contract["swap_limit_bytes"] == 0
    assert contract["compute_wall_unlimited"] is True
    assert contract["time_stop"]["consumer_enforced"] is False
    assert contract["time_stop"]["consumer_timeout_seconds"] is None
    assert contract["ledger"] == registered["ledger"]

    for invalid_model, invalid_input in (
        (
            TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID,
            "13p5nm_p6h10_m120_mpi8_cell_condensed.dat",
        ),
        (TASK041_BALH_2NM_MODEL_ID, "2nm_p6h1p5_m1200_mpi8_balh.dat"),
    ):
        invalid_case_contract = task041_balh_service_contract(invalid_model)
        invalid_ledger_path = invalid_case_contract["ledger"].get("path")
        if isinstance(invalid_ledger_path, str):
            invalid_ledger_path = (repository_root / invalid_ledger_path).resolve()
        else:
            invalid_ledger_path = ledger_path
        invalid_config = {
            **config,
            "model_id": invalid_model,
            "ledger_path": invalid_ledger_path,
            "public_command": [
                sys.executable,
                "scripts/run_case.py",
                str(
                    repository_root
                    / "input/official/task041/side_balh"
                    / invalid_input
                ),
                "--task041-p4-refinement-target-tolerance",
                "5e-13",
            ],
        }
        with pytest.raises(
            service.Task041ServiceError,
            match="registered P4 refinement target is limited",
        ):
            service._service_contract(
                invalid_config,
                side_setup_schedule=None,
                comparison_mode=None,
                p4_refinement_target_tolerance=5.0e-13,
                p4_backend_pair_side=None,
            )


@pytest.mark.parametrize(
    ("model_id", "input_name", "target_scope"),
    [
        (
            TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID,
            "5nm_p6h4_m480_mpi8_cell_condensed.dat",
            task041_balh_workflow.TASK041_P4_REGISTERED_5NM_TARGET_SCOPE,
        ),
        (
            TASK041_BALH_2NM_CELL_CONDENSED_MODEL_ID,
            "2nm_p6h1p5_m1200_mpi8_cell_condensed.dat",
            task041_balh_workflow.TASK041_P4_REGISTERED_2NM_TARGET_SCOPE,
        ),
    ],
)
def test_v8_resource_policy_is_bound_by_registered_condensed_finalizer(
    model_id, input_name, target_scope, monkeypatch, tmp_path
):
    repository_root = Path(__file__).resolve().parents[2]
    registered = task041_balh_service_contract(model_id)
    ledger_path = (repository_root / registered["ledger"]["path"]).resolve()
    root = tmp_path / "v8-service-root"
    root.mkdir()
    policy = task041_balh_workflow.TASK041_V8_SWAP_OBSERVE_CONTINUE
    input_path = repository_root / "input/official/task041/side_balh" / input_name
    config = {
        "unit": UNIT,
        "model_id": model_id,
        "source_sha": SOURCE_SHA,
        "ledger_path": str(ledger_path),
        "supervision_root": str(root),
        "public_command": [
            sys.executable,
            "scripts/run_case.py",
            str(input_path),
            "--producer-packet-root",
            str(tmp_path / "producer"),
            "--task041-p4-refinement-target-tolerance",
            "5e-13",
            "--task041-resource-policy",
            policy,
        ],
        "p4_refinement_target_tolerance": 5.0e-13,
        "task041_resource_policy": policy,
        "global_swap_baseline": {
            "global_swap_used_bytes": 8192,
            "global_pswpin_pages": 0,
            "global_pswpout_pages": 2,
        },
    }
    config_path = tmp_path / "v8-job-config.json"
    supervisor._write_json(config_path, config)
    identity = _identity(start_ns=1_000_000_000)
    monkeypatch.setattr(
        supervisor,
        "_load_task041_compute_wall_ledger",
        lambda path: (Path(path), {"used_compute_wall_seconds": 100.0}),
    )
    monkeypatch.setattr(service, "_parent_unit_identity", lambda _unit: identity)
    monkeypatch.setattr(service, "_cgroup_members", lambda _group: [os.getpid()])
    monkeypatch.setattr(service, "_sparse_sample_factory", lambda: "sampler")
    monkeypatch.setattr(service.time, "monotonic_ns", lambda: 2_000_000_000)

    def fake_public(_command, supervision_root, **kwargs):
        supervisor._write_json(
            Path(supervision_root) / "launch_manifest.json",
            kwargs["launch_manifest"],
        )
        supervisor._write_json(
            Path(supervision_root) / "summary.json",
            {
                "status": "completed",
                "result_classification": "worker_exit0",
                "phase_result": {
                    "returncode": 0,
                    "termination_reason": None,
                    "wall_seconds": 1.0,
                },
            },
        )
        return {
            "status": "completed",
            "result_classification": "worker_exit0",
            "phase_result": {
                "returncode": 0,
                "termination_reason": None,
                "wall_seconds": 1.0,
            },
        }

    monkeypatch.setattr(supervisor, "run_task041_supervised_public_command", fake_public)
    parent = service.run_service_parent(config_path)
    assert parent["status"] == "pre_exit_ok"
    launch = supervisor._read_json(root / "launch_manifest.json")
    policy_binding = launch["task041_resource_policy"]
    target_binding = launch["p4_refinement_target_binding"]
    assert launch["p4_refinement_target_tolerance"] == 5.0e-13
    assert target_binding["scope"] == target_scope

    monkeypatch.setattr(
        service,
        "_record_unit_wall",
        lambda *_args: ({"used_compute_wall_seconds": 101.0}, None),
    )

    def fake_post_hash(_root, finalizer_root, *_args):
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

    monkeypatch.setattr(service, "_run_post_hash", fake_post_hash)
    _normal_terminal(monkeypatch)

    finalizer = service.run_service_finalize(config_path)

    assert finalizer["status"] == "completed"
    assert finalizer["result_classification"] == "service_complete"
    assert all(finalizer["checks"].values())
    assert finalizer["checks"]["invocation_matches"] is True
    assert finalizer["launch_manifest"]["path"] == str(
        root / "launch_manifest.json"
    )
    assert finalizer["task041_resource_policy"] == policy_binding
    assert finalizer["public_to_finalizer_time_target"] == {
        "target_seconds": 86400,
        "wall_seconds": 1.0,
        "met": True,
        "scope": "public-to-finalizer unit wall; not a resource-safety gate",
    }


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
    assert observed["process_tree_rss_warning_bytes"] == 47_899_046_707
    assert observed["process_tree_rss_cap_bytes"] == 53_221_163_008
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


def test_v12_policy_finalizer_follows_exact_inner_artifact_chain_and_stays_unknown(
    tmp_path: Path,
):
    from src.io.input_validation import task041_balh_service_contract

    policy = "task041_v12_bounded_inexact_modal_once_backup"
    source_sha = "c" * 40
    invocation_id = "v12-layered-policy-fixture"
    unit = "task041-v12-layered-policy-fixture.service"
    model_id = "task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot"
    runtime_contract = dict(task041_balh_service_contract(model_id))
    root = (tmp_path / "service-root").resolve()
    inner = (tmp_path / "inner-run").resolve()
    consumer_root = inner / "consumer"
    (root / "log").mkdir(parents=True)
    consumer_root.mkdir(parents=True)
    fixed_binding = {
        "method": "fixed_h6_modal_gmres_research",
        "model_id": model_id,
        "modal_solver_policy": {"policy_id": policy},
    }
    launch = {
        "schema": service.LAUNCH_SCHEMA,
        "unit": unit,
        "model_id": model_id,
        "source_sha": source_sha,
        "invocation_id": invocation_id,
        "supervision_root": str(root),
        "modal_solver_policy": policy,
        "fixed_h6_modal_gmres_research": fixed_binding,
    }
    launch_path = root / "launch_manifest.json"
    launch_path.write_text(json.dumps(launch, sort_keys=True) + "\n")
    launch_sha = supervisor._sha256_file(launch_path)
    supervision_record = {
        "path": str(launch_path),
        "sha256": launch_sha,
        "invocation_id": invocation_id,
        "source_sha": source_sha,
        "modal_solver_policy": policy,
        "fixed_h6_modal_gmres_research": fixed_binding,
    }
    consumer_summary = {
        "schema": "task041.side_balh.candidate_consumer.v1",
        "run_directory": str(consumer_root),
        "source_sha": source_sha,
        "modal_solver_policy": policy,
        "fixed_h6_modal_gmres_research": fixed_binding,
        "failure_evidence": {
            "side_rhs_audits": {
                "modal_inner_solver": {"method": "fixed_physical_balh_once"}
            }
        },
    }
    consumer_path = consumer_root / "consumer_summary.json"
    consumer_bytes = json.dumps(consumer_summary, sort_keys=True).encode()
    consumer_path.write_bytes(consumer_bytes)
    consumer_artifact = {
        "path": str(consumer_path),
        "bytes": len(consumer_bytes),
        "sha256": hashlib.sha256(consumer_bytes).hexdigest(),
    }
    supervisor_summary = {
        "schema": "task041.public.supervisor.v1",
        "run_directory": str(inner),
        "output_directory": str(inner),
        "source_sha": source_sha,
        "modal_solver_policy": policy,
        "fixed_h6_modal_gmres_research": fixed_binding,
        "supervision_record": supervision_record,
        "service_contract": runtime_contract,
        "consumer": {"summary_artifact": consumer_artifact},
    }
    run_summary = dict(supervisor_summary)
    run_manifest = {
        "source_sha": source_sha,
        "modal_solver_policy": policy,
        "fixed_h6_modal_gmres_research": fixed_binding,
        "supervision_record": supervision_record,
        "model_id": model_id,
        "output_directory": str(inner),
    }
    supervisor._write_json(inner / "supervisor_summary.json", supervisor_summary)
    supervisor._write_json(inner / "run_summary.json", run_summary)
    supervisor._write_json(inner / "run_manifest.json", run_manifest)
    supervisor._write_json(
        consumer_root / "factor_inventory.json",
        {
            "schema": "task041.side_balh.candidate_factor_inventory.v1",
            "candidate_inventory": {},
        },
    )
    public_command = ["python", "scripts/run_case.py", "input.dat"]
    public_stdout = {
        **supervisor_summary,
        "summary": str(inner / "run_summary.json"),
        "manifest": str(inner / "run_manifest.json"),
    }
    public_stdout_path = root / "log" / "public_command_stdout.txt"
    public_stdout_path.write_text(json.dumps(public_stdout, sort_keys=True) + "\n")
    outer_summary = {
        "schema": "task041.supervised_public_command.v1",
        "supervision_root": str(root),
        "model_id": model_id,
        "modal_solver_policy": policy,
        "launch_manifest": {"path": str(launch_path), "sha256": launch_sha},
        "phase_result": {
            "stdout": str(public_stdout_path),
            "argv": public_command,
        },
    }
    contract = {
        "unit": unit,
        "model_id": model_id,
        "modal_solver_policy": policy,
        "fixed_h6_modal_gmres_research": fixed_binding,
    }
    kwargs = {
        "supervision_root": root,
        "launch_manifest": launch,
        "sealed_public_command": public_command,
        "expected_source_sha": source_sha,
        "terminal_invocation_id": invocation_id,
        "expected_unit": unit,
    }

    # The exact layer chain is present, but the historical V12 payload has no
    # candidate inventory or setup evidence to establish the requested method.
    assert service._modal_solver_policy_matches_request(
        contract, outer_summary, **kwargs
    ) is False


def test_v13_resume_owner_records_allow_empty_rank_but_require_global_nonzero_x():
    empty_sha = hashlib.sha256(b"").hexdigest()
    assert supervisor._v13_sha256_text(empty_sha)
    rows = [
        {
            "rank": 0,
            "x_range": [0, 0],
            "f_range": [0, 0],
            "solution_local_norm_before_resume": 0.0,
        },
        {
            "rank": 1,
            "x_range": [0, 2],
            "f_range": [0, 2],
            "solution_local_norm_before_resume": 1.25,
        },
    ]
    for range_key in ("x_range", "f_range"):
        assert supervisor._v13_owner_ranges_cover(
            rows, range_key=range_key, global_size=2, rank_count=2
        )
    assert supervisor._v13_global_owner_norms_valid(
        rows,
        rank_count=2,
        norm_key="solution_local_norm_before_resume",
    )
    rows[1]["solution_local_norm_before_resume"] = 0.0
    assert not supervisor._v13_global_owner_norms_valid(
        rows,
        rank_count=2,
        norm_key="solution_local_norm_before_resume",
    )


def test_v13_finite_stop_rhs_reader_uses_its_rank_local_binding_source():
    rhs_hashes = [hashlib.sha256(f"rhs-{rank}".encode()).hexdigest() for rank in range(2)]
    finite_stop_rows = [
        {
            "rank": rank,
            "rhs_local_sha256_before": digest,
            "rhs_local_sha256_after": digest,
        }
        for rank, digest in enumerate(rhs_hashes)
    ]
    candidate_rows = [dict(row) for row in finite_stop_rows]
    valid, observed = supervisor._v13_original_rhs_binding_sources_agree(
        rank_count=2,
        original_rows=None,
        finite_stop_rows=finite_stop_rows,
        restart_candidate_rows=candidate_rows,
    )
    assert valid is True
    assert observed == dict(enumerate(rhs_hashes))
    candidate_rows[1]["rhs_local_sha256_after"] = hashlib.sha256(
        b"different original rhs"
    ).hexdigest()
    valid, observed = supervisor._v13_original_rhs_binding_sources_agree(
        rank_count=2,
        original_rows=None,
        finite_stop_rows=finite_stop_rows,
        restart_candidate_rows=candidate_rows,
    )
    assert valid is False
    assert observed is None


def _v13_rank_runtime_fixture(expected_rank_cpus=None):
    expected_cpus = list(
        task041_balh_workflow.TASK041_V13_MPI8_RANK_CPUS
        if expected_rank_cpus is None
        else expected_rank_cpus
    )
    binding = task041_balh_workflow.task041_fixed_h6_modal_gmres_binding(
        task041_balh_workflow.TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID,
        enabled=True,
        candidate=True,
        mpi_size=8,
        mode_count=400,
        p4_inverse_backend="cell_condensed",
        p4_refinement_target_tolerance=5.0e-13,
        task041_resource_policy=task041_balh_workflow.TASK041_V8_SWAP_OBSERVE_CONTINUE,
        expected_rank_cpus=expected_cpus,
        modal_solver_policy=(
            "task041_v13_consistent_fixed_balh_modal_surrogate"
        ),
    )
    session_id = 1900
    required_threads = dict(
        task041_balh_workflow.TASK041_V13_REQUIRED_THREAD_ENVIRONMENT
    )
    resource_policy = dict(
        task041_balh_workflow.TASK041_V13_RESOURCE_HEADROOM_POLICY
    )
    cgroup_identity = {"path": "/user.slice/task041-v13-fixture.scope"}
    ranks = []
    for rank, cpu in enumerate(expected_cpus):
        ranks.append(
            {
                "rank": rank,
                "evidence": {
                    "rank_identity": {
                        "pid": 2001 + rank,
                        "ppid": 1800,
                        "pgid": 1800,
                        "sid": session_id,
                        "starttime_ticks": 10001 + rank,
                        "current_cpu": cpu,
                        "sched_getaffinity": [cpu],
                        "cpu_topology": [
                            {"os_cpu": cpu, "socket": 0, "numa_nodes": [0]}
                        ],
                    },
                    "task_policy": {
                        "status": "measured",
                        "mode": 0,
                        "policy": "default",
                    },
                    "memory_scope": {
                        "status": "measured",
                        "pass": True,
                        "allowed_nodes_match": True,
                        "cgroup_identity_stable": True,
                        "proc_allowed_nodes": [0, 1],
                        "effective_nodes": [0, 1],
                        "cgroup_identity_before": cgroup_identity,
                        "cgroup_identity_after": cgroup_identity,
                    },
                    "math_thread_environment": {
                        "status": "measured",
                        "all_one": True,
                        "variables": dict(required_threads),
                    },
                },
            }
        )
    return binding, {
        "rank_numa_evidence": [
            {
                "schema": "task041.rank_numa_stage.v1",
                "stage": "startup",
                "collective_status": "measured",
                "qualification": {
                    "status": "passed",
                    "memory_policy": "system_default_unbound",
                    "membind_node": None,
                    "page_placement_semantics": "observation_only",
                    "expected_rank_cpus": expected_cpus,
                    "required_thread_environment": required_threads,
                    "resource_headroom_policy": resource_policy,
                },
                "ranks": ranks,
            }
        ]
    }, {
        "schema": "task041.owned_session_cleanup.v1",
        "session_id": session_id,
        "status": "empty",
        "empty": True,
        "members": [],
        "unreadable": [],
        "inspection": "full_visible_proc_session_scan_after_owned_launcher_wait",
    }


def _owned_session_snapshot_fixture(session_id, members, *, unreadable=None):
    rows = [dict(member) for member in members]
    unreadable_rows = list(unreadable or [])
    empty = not rows and not unreadable_rows
    return {
        "schema": "task041.owned_session_cleanup.v1",
        "session_id": session_id,
        "status": "empty" if empty else "members_remain" if rows else "unknown",
        "empty": empty,
        "members": rows,
        "unreadable": unreadable_rows,
        "inspection": "full_visible_proc_session_scan_after_owned_launcher_wait",
    }


def _owned_session_member(pid, ppid, pgid, session_id, start_ticks):
    return {
        "pid": pid,
        "ppid": ppid,
        "pgid": pgid,
        "sid": session_id,
        "start_ticks": start_ticks,
    }


def _owned_session_leader(session_id):
    return {
        "schema": "task041.owned_session_leader.v1",
        "status": "measured",
        "pid": session_id,
        "ppid": 1,
        "pgid": session_id,
        "sid": session_id,
        "start_ticks": 1200,
    }


def test_v13_owned_session_cleanup_targets_rank_groups_after_launcher_group_gone():
    session_id = 900
    members = [
        _owned_session_member(901, 1, 920, session_id, 1301),
        _owned_session_member(902, 1, 930, session_id, 1302),
    ]
    state = {"members": [dict(member) for member in members], "now": 0.0}
    signals = []

    def snapshot_reader(requested_session_id):
        assert requested_session_id == session_id
        return _owned_session_snapshot_fixture(session_id, state["members"])

    def signal_group(pgid, sig):
        signals.append((pgid, sig))
        if (sig == supervisor.signal.SIGTERM and pgid == 920) or (
            sig == supervisor.signal.SIGKILL
        ):
            state["members"] = [
                member for member in state["members"] if member["pgid"] != pgid
            ]

    def sleep(seconds):
        state["now"] += seconds

    result = supervisor._terminate_owned_session_members(
        session_id,
        _owned_session_snapshot_fixture(session_id, members),
        leader_identity=_owned_session_leader(session_id),
        grace_seconds=0.1,
        snapshot_reader=snapshot_reader,
        signal_process_group=signal_group,
        monotonic=lambda: state["now"],
        sleep=sleep,
    )

    assert [member["pid"] for member in result["initial_snapshot"]["members"]] == [
        901,
        902,
    ]
    assert {member["pgid"] for member in result["initial_snapshot"]["members"]} == {
        920,
        930,
    }
    assert signals == [
        (920, supervisor.signal.SIGTERM),
        (930, supervisor.signal.SIGTERM),
        (930, supervisor.signal.SIGKILL),
    ]
    assert result["sigkill_required"] is True
    assert result["verified_empty"] is True
    assert result["final_snapshot"]["status"] == "empty"


def test_v13_owned_session_cleanup_unknown_or_unowned_never_signals():
    session_id = 900
    member = _owned_session_member(901, 1, 920, session_id, 1301)
    signals = []

    def signal_group(pgid, sig):
        signals.append((pgid, sig))

    unreadable = _owned_session_snapshot_fixture(
        session_id, [], unreadable=[{"path": "/proc", "error": "PermissionError"}]
    )
    live = _owned_session_snapshot_fixture(session_id, [member])
    unknown = supervisor._terminate_owned_session_members(
        session_id,
        live,
        leader_identity=_owned_session_leader(session_id),
        snapshot_reader=lambda _sid: unreadable,
        signal_process_group=signal_group,
    )
    assert unknown["status"] == "unknown"
    assert unknown["verified_empty"] is False
    assert signals == []

    unowned = supervisor._terminate_owned_session_members(
        session_id,
        live,
        leader_identity=None,
        snapshot_reader=lambda _sid: live,
        signal_process_group=signal_group,
    )
    assert unowned["status"] == "unknown"
    assert unowned["verified_empty"] is False
    assert signals == []


def test_v13_run_phase_records_residual_session_cleanup_without_replacing_error(
    tmp_path, monkeypatch
):
    session_id = 900
    residual = _owned_session_snapshot_fixture(
        session_id,
        [
            _owned_session_member(901, 1, 920, session_id, 1301),
            _owned_session_member(902, 1, 930, session_id, 1302),
        ],
    )
    empty = _owned_session_snapshot_fixture(session_id, [])
    snapshots = iter((residual, residual, empty))
    cleanup_calls = []
    leader = _owned_session_leader(session_id)

    class ExitedLauncher:
        pid = session_id

        def poll(self):
            return 17

        def wait(self):
            return 17

    monkeypatch.setattr(
        supervisor,
        "_owned_session_leader_identity",
        lambda pid: leader if pid == session_id else {},
    )
    monkeypatch.setattr(
        supervisor,
        "_owned_session_snapshot",
        lambda sid: next(snapshots) if sid == session_id else {},
    )

    def cleanup(sid, initial_snapshot, *, leader_identity, **_kwargs):
        cleanup_calls.append((sid, initial_snapshot, leader_identity))
        return {
            "schema": "task041.owned_session_termination.v1",
            "session_id": sid,
            "status": "empty",
            "verified_empty": True,
            "initial_snapshot": dict(initial_snapshot),
            "final_snapshot": empty,
            "signal_attempts": [],
        }

    monkeypatch.setattr(supervisor, "_terminate_owned_session_members", cleanup)
    log_root = tmp_path / "log"
    marker_root = tmp_path / "markers"
    memory_root = tmp_path / "memory"
    log_root.mkdir()
    marker_root.mkdir()
    memory_root.mkdir()
    partial = {}

    with pytest.raises(supervisor.Task041SupervisorError) as caught:
        supervisor._run_phase(
            "mpi2",
            ["fake-launcher"],
            tmp_path / "phase",
            log_root=log_root,
            environment={},
            repository_root=tmp_path,
            workflow_started=0.0,
            popen_factory=lambda *_args, **_kwargs: ExitedLauncher(),
            sample_factory=lambda _pid: {},
            terminate_factory=lambda _process: {},
            monotonic=lambda: 1.0,
            sleep=lambda _seconds: None,
            poll_interval=0.1,
            memory_stages_path=memory_root / "stages.jsonl",
            marker_path=marker_root / "markers.jsonl",
            process_group_gone=lambda _pid: True,
            partial_phase_results=partial,
            require_owned_session_empty=True,
        )

    assert caught.value.stage == "mpi2_owned_session_cleanup"
    assert len(cleanup_calls) == 1
    assert cleanup_calls[0][0] == session_id
    assert {row["pgid"] for row in cleanup_calls[0][1]["members"]} == {920, 930}
    assert cleanup_calls[0][2] == leader
    assert partial["mpi2"]["owned_session_termination"]["verified_empty"] is True
    assert partial["mpi2"]["owned_session_cleanup"]["status"] == "empty"


def test_v13_initial_resource_gate_requires_aggregate_and_node1_availability():
    gib = 2**30
    valid = supervisor._task041_v13_initial_resource_gate_record(
        384 * gib, 80 * gib
    )
    assert valid["pass"] is True
    assert valid["aggregate_memfree_bytes"] == 464 * gib
    assert valid["node1_is_availability_only_not_memory_binding"] is True
    assert not supervisor._task041_v13_initial_resource_gate_record(
        383 * gib, 80 * gib
    )["pass"]
    assert not supervisor._task041_v13_initial_resource_gate_record(
        385 * gib, 79 * gib
    )["pass"]
    assert not supervisor._task041_v13_initial_resource_gate_record(
        None, 80 * gib
    )["pass"]


def test_v13_rank_runtime_recomputes_default_scope_threads_and_session():
    expected_cpus = tuple(range(8))
    binding, summary, cleanup = _v13_rank_runtime_fixture(
        expected_rank_cpus=expected_cpus
    )
    assert binding["expected_rank_cpus"] == list(expected_cpus)
    assert supervisor._task041_v13_rank_runtime_evidence(
        summary,
        expected_binding=binding,
        owned_session_cleanup=cleanup,
    )["pass"] is True

    bad_policy = json.loads(json.dumps(summary))
    bad_policy["rank_numa_evidence"][0]["ranks"][0]["evidence"][
        "task_policy"
    ]["mode"] = 2
    assert supervisor._task041_v13_rank_runtime_evidence(
        bad_policy, expected_binding=binding, owned_session_cleanup=cleanup
    )["pass"] is False

    bad_nodes = json.loads(json.dumps(summary))
    bad_nodes["rank_numa_evidence"][0]["ranks"][0]["evidence"][
        "memory_scope"
    ]["proc_allowed_nodes"] = []
    assert supervisor._task041_v13_rank_runtime_evidence(
        bad_nodes, expected_binding=binding, owned_session_cleanup=cleanup
    )["pass"] is False

    mismatched_scope = json.loads(json.dumps(summary))
    mismatched_scope["rank_numa_evidence"][0]["ranks"][0]["evidence"][
        "memory_scope"
    ]["effective_nodes"] = [0]
    assert supervisor._task041_v13_rank_runtime_evidence(
        mismatched_scope, expected_binding=binding, owned_session_cleanup=cleanup
    )["pass"] is False

    bad_threads = json.loads(json.dumps(summary))
    del bad_threads["rank_numa_evidence"][0]["ranks"][0]["evidence"][
        "math_thread_environment"
    ]["variables"]["BLIS_NUM_THREADS"]
    assert supervisor._task041_v13_rank_runtime_evidence(
        bad_threads, expected_binding=binding, owned_session_cleanup=cleanup
    )["pass"] is False

    wrong_thread = json.loads(json.dumps(summary))
    wrong_thread["rank_numa_evidence"][0]["ranks"][0]["evidence"][
        "math_thread_environment"
    ]["variables"]["MKL_NUM_THREADS"] = "2"
    assert supervisor._task041_v13_rank_runtime_evidence(
        wrong_thread, expected_binding=binding, owned_session_cleanup=cleanup
    )["pass"] is False

    bad_session = dict(cleanup, members=[{"pid": 2001, "sid": 1900}])
    assert supervisor._task041_v13_rank_runtime_evidence(
        summary, expected_binding=binding, owned_session_cleanup=bad_session
    )["pass"] is False

    wrong_actual_cpu = json.loads(json.dumps(summary))
    rank_three_identity = wrong_actual_cpu["rank_numa_evidence"][0]["ranks"][3][
        "evidence"
    ]["rank_identity"]
    rank_three_identity["current_cpu"] = 21
    rank_three_identity["sched_getaffinity"] = [21]
    rank_three_identity["cpu_topology"][0]["os_cpu"] = 21
    assert supervisor._task041_v13_rank_runtime_evidence(
        wrong_actual_cpu,
        expected_binding=binding,
        owned_session_cleanup=cleanup,
    )["pass"] is False

    summary_map_is_not_authority = json.loads(json.dumps(summary))
    summary_map_is_not_authority["rank_numa_evidence"][0]["qualification"][
        "expected_rank_cpus"
    ] = list(task041_balh_workflow.TASK041_V13_MPI8_RANK_CPUS)
    assert supervisor._task041_v13_rank_runtime_evidence(
        summary_map_is_not_authority,
        expected_binding=binding,
        owned_session_cleanup=cleanup,
    )["pass"] is False

    missing_expected_map = dict(binding)
    del missing_expected_map["expected_rank_cpus"]
    assert supervisor._task041_v13_rank_runtime_evidence(
        summary,
        expected_binding=missing_expected_map,
        owned_session_cleanup=cleanup,
    )["pass"] is False


def test_v13_outer_reader_recomputes_B_delta_W_and_external_gate_set():
    from src.solvers import hybrid_fem_modal_block_ldu as block_ldu

    phase = "outer_restart32_workspace"
    phase_reports = {
        "outer_PC_with_retained_workspaces": {
            "known_additional_bytes_by_rank": [10, 10],
            "additional_temporary_bytes_by_rank": [2, 3],
            "additional_replicated_bytes_by_rank": [1, 1],
            "additional_bytes_by_rank": [13, 14],
        },
        "outer_original_A_true_residual": {
            "known_additional_bytes_by_rank": [10, 10],
            "additional_temporary_bytes_by_rank": [5, 4],
            "additional_replicated_bytes_by_rank": [1, 1],
            "additional_bytes_by_rank": [16, 15],
        },
    }
    selected_phase = "outer_original_A_true_residual"
    additional = [16, 15]
    gib = 2**30
    cap = 85_899_345_920
    reserve = 8_589_934_592
    floor = 412_316_860_416
    fresh = 2_000_000_000
    required = sum(additional) + reserve
    node0_free = floor + required + 100
    node1_free = 80 * gib + sum(additional)
    aggregate_free = node0_free + node1_free
    host_available = floor + required + 200
    cgroup_headroom = required + 300
    projected = fresh + required
    sample_sha = "b" * 64
    report = {
        "phase": phase,
        "target_restart": 32,
        "known_additional_bytes_by_rank": [10, 10],
        "additional_temporary_bytes_by_rank": [5, 4],
        "additional_replicated_bytes_by_rank": [1, 1],
        "phase_memory_projection": {
            "phase_reports": phase_reports,
            "phase_total_bytes": {
                "outer_PC_with_retained_workspaces": 27,
                "outer_original_A_true_residual": 31,
            },
            "selected_phase": selected_phase,
            "selected_phase_payload_bytes": 31,
        },
    }
    request_sha = hashlib.sha256(
        json.dumps(
            report, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    external = {
        "bound_fresh_supervisor_sample": True,
        "tree_cgroup_and_all_mpi_ranks": True,
        "initial_aggregate_memfree_gate": True,
        "initial_node1_memfree_gate": True,
        "aggregate_floor_headroom": True,
        "node1_phase_headroom": True,
        "host_floor_headroom": True,
        "cgroup_ancestor_headroom": True,
        "case_cap_projection": True,
        "sample_cost_contract": True,
    }
    payload = {
        "phase": phase,
        "request_sha256": request_sha,
        "invocation_id": "outer-reader-fixture",
        "source_sha": "c" * 40,
        "unit": "task041-v13-outer-reader-fixture.service",
        "sample_row_sha256": sample_sha,
        "sample_root_pid": 999,
        "resource_B_bytes": fresh,
        "node0_memfree_bytes": node0_free,
        "node1_memfree_bytes": node1_free,
        "aggregate_memfree_bytes": aggregate_free,
        "aggregate_memfree_reserve_bytes": floor,
        "aggregate_floor_headroom_bytes": aggregate_free - floor,
        "node1_phase_additional_bytes": sum(additional),
        "node1_headroom_after_phase_additional_bytes": (
            node1_free - sum(additional)
        ),
        "initial_resource_gate": {
            "required": False,
            "source": "supervisor_resource_preflight",
            "initial_aggregate_memfree_minimum_bytes": 464 * gib,
            "initial_node1_memfree_minimum_bytes": 80 * gib,
        },
        "selected_memory_phase": selected_phase,
        "rank_pids": [101, 102],
        "selected_memory_phase_payload_bytes": sum(additional),
        "additional_bytes_by_rank": additional,
        "cap_bytes": cap,
        "W_policy_reserve_bytes": reserve,
        "floor_bytes": floor,
        "host_available_bytes": host_available,
        "host_headroom_after_aggregate_reserve_bytes": host_available - floor,
        "cgroup_limit_state": "finite",
        "cgroup_headroom_bytes": cgroup_headroom,
        "projected_B_plus_delta_plus_W_bytes": projected,
    }
    receipt_sha = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    authority = {
        "schema": "task041.v13.modal_builder_admission.v1",
        "phase": phase,
        "status": "pass",
        "decision": "continue",
        "request_sha256": request_sha,
        "authority_receipt_payload": payload,
        "authority_receipt_sha256": receipt_sha,
        "fresh_job_authority_bytes": fresh,
        "cap_bytes": cap,
        "W_policy_reserve_bytes": reserve,
        "floor_bytes": floor,
        "additional_bytes_by_rank": additional,
        "additional_temporary_bytes_by_rank": [5, 4],
        "additional_replicated_bytes_by_rank": [1, 1],
        "selected_memory_phase": selected_phase,
        "selected_memory_phase_payload_bytes": sum(additional),
        "external_resource_gates": external,
        "sample_row_sha256": sample_sha,
        "sample_age_seconds": 0.5,
        "root_pid": 999,
        "rank_pids": [101, 102],
        "node0_memfree_bytes": node0_free,
        "node1_memfree_bytes": node1_free,
        "aggregate_memfree_bytes": aggregate_free,
        "aggregate_memfree_reserve_bytes": floor,
        "aggregate_floor_headroom_bytes": aggregate_free - floor,
        "node1_phase_additional_bytes": sum(additional),
        "node1_headroom_after_phase_additional_bytes": (
            node1_free - sum(additional)
        ),
        "host_available_bytes": host_available,
        "host_headroom_after_aggregate_reserve_bytes": host_available - floor,
        "cgroup_headroom_bytes": cgroup_headroom,
        "cgroup_limit_state": "finite",
        "projected_B_plus_delta_plus_W_bytes": projected,
        "cost_assessment": {
            "scope": "outer_ksp_workspace_admission",
            "status": "workspace_model_valid",
            "target_restart": 32,
            "W_policy_reserve_bytes": reserve,
            "target_is_elapsed_stop": False,
        },
    }
    assert supervisor._v13_outer_authority_pass_matches_report(
        phase, report, authority, rank_count=2
    )
    assert block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
        phase, report, authority, rank_count=2
    )
    stale_node0_schema = json.loads(json.dumps(authority))
    stale_node0_schema["external_resource_gates"]["node0_floor_headroom"] = True
    del stale_node0_schema["external_resource_gates"]["aggregate_floor_headroom"]
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, stale_node0_schema, rank_count=2
    )
    assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
        phase, report, stale_node0_schema, rank_count=2
    )
    bad_aggregate = json.loads(json.dumps(authority))
    bad_aggregate["aggregate_memfree_bytes"] += 1
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, bad_aggregate, rank_count=2
    )
    assert not block_ldu._task041_v13_outer_workspace_pass_resource_contract_valid(
        phase, report, bad_aggregate, rank_count=2
    )
    bad_B = dict(authority, fresh_job_authority_bytes=fresh + 1)
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, bad_B, rank_count=2
    )
    bad_receipt_B = {
        **authority,
        "authority_receipt_payload": {
            **payload,
            "resource_B_bytes": fresh + 1,
        },
    }
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, bad_receipt_B, rank_count=2
    )
    bad_delta = dict(authority, additional_bytes_by_rank=[17, 15])
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, bad_delta, rank_count=2
    )
    missing_external = dict(authority, external_resource_gates={})
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, missing_external, rank_count=2
    )
    bad_request_hash = dict(authority, request_sha256="0" * 64)
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, bad_request_hash, rank_count=2
    )
    bad_receipt_hash = dict(authority, authority_receipt_sha256="0" * 64)
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, bad_receipt_hash, rank_count=2
    )
    refused = dict(authority, status="refused", decision="stop")
    assert not supervisor._v13_outer_authority_pass_matches_report(
        phase, report, refused, rank_count=2
    )


def test_v13_outer_policy_without_actual_solve_record_stays_not_persisted():
    evidence = supervisor._task041_v13_outer_control_evidence(
        None, expected_rank_count=8
    )
    assert evidence["status"] == "not_persisted"
    assert evidence["pass"] is None


@pytest.mark.parametrize(
    "tamper",
    (
        None,
        "policy",
        "method",
        "source",
        "invocation",
        "path",
        "bytes",
        "sha",
        "side_apply_count",
        "resource_cap",
        "modal_count",
        "modal_shape",
        "modal_column_count",
        "missing_column",
        "duplicate_column",
        "boundary_terminal",
        "crossed_boundary_without_evidence",
    ),
    ids=(
        "complete-v13-chain",
        "policy-mismatch",
        "actual-method-mismatch",
        "consumer-source-mismatch",
        "invocation-mismatch",
        "inner-summary-path-mismatch",
        "consumer-byte-count-mismatch",
        "consumer-sha-mismatch",
        "nonzero-borrowed-side-call",
        "resource-contract-mismatch",
        "modal-count-does-not-match-sealed-mode-count",
        "modal-schur-shape-mismatch",
        "completed-modal-column-count-mismatch",
        "missing-modal-column",
        "duplicate-modal-column",
        "converged-at-iteration-48-without-restart-observation",
        "continued-past-iteration-48-without-window-evidence",
    ),
)
def test_v13_policy_finalizer_requires_complete_actual_chain_and_consumer_evidence(
    tmp_path: Path, tamper: str | None
):
    model_id = task041_balh_workflow.TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID
    policy_id = "task041_v13_consistent_fixed_balh_modal_surrogate"
    method = "task041_v13_consistent_fixed_balh_modal_surrogate"
    source_sha = "d" * 40
    invocation_id = "v13-layered-policy-fixture"
    unit = "task041-v13-layered-policy-fixture.service"
    root = (tmp_path / "service-root").resolve()
    inner = (tmp_path / "inner-run").resolve()
    consumer_root = inner / "consumer"
    (root / "log").mkdir(parents=True)
    consumer_root.mkdir(parents=True)
    expected_cpus = tuple(range(8))
    fixed_binding = task041_balh_workflow.task041_fixed_h6_modal_gmres_binding(
        model_id,
        enabled=True,
        candidate=True,
        mpi_size=8,
        mode_count=400,
        p4_inverse_backend="cell_condensed",
        p4_refinement_target_tolerance=5.0e-13,
        task041_resource_policy=(
            task041_balh_workflow.TASK041_V8_SWAP_OBSERVE_CONTINUE
        ),
        expected_rank_cpus=expected_cpus,
        modal_solver_policy=policy_id,
    )
    assert isinstance(fixed_binding, dict)
    rank_binding, rank_summary, owned_session_cleanup = (
        _v13_rank_runtime_fixture(expected_rank_cpus=expected_cpus)
    )
    assert rank_binding == fixed_binding
    v13_metadata = {
        "memory_policy": task041_balh_workflow.TASK041_V13_MEMORY_POLICY,
        "membind_node": None,
        "resource_headroom_policy": dict(
            task041_balh_workflow.TASK041_V13_RESOURCE_HEADROOM_POLICY
        ),
        "required_thread_environment": dict(
            task041_balh_workflow.TASK041_V13_REQUIRED_THREAD_ENVIRONMENT
        ),
        "environment_threads": dict(
            task041_balh_workflow.TASK041_V13_REQUIRED_THREAD_ENVIRONMENT
        ),
    }
    policy_binding = fixed_binding["modal_solver_policy"]
    from src.solvers.hybrid_fem_modal_block_ldu import (
        _v13_modal_schur_diagnostic_fields,
    )

    modal_count = 2 * fixed_binding["mode_count"]
    build_audit = {
        "formula": "S_B=C-LBG",
        "full_owner_matrix_pages_materialized_before_sample_gate": True,
        "sample_columns_written_directly_to_final_matrix": list(range(8)),
        "remaining_columns_applied_once": list(range(8, modal_count)),
    }
    actual_v13 = {
        "schema": "task041.v13.consistent_modal_surrogate.v1",
        "policy_id": policy_id,
        "method": method,
        "operator": "V13 S_B=C-LBG with the same fixed approximate B in modal and LDU terms",
        **_v13_modal_schur_diagnostic_fields(modal_count, build_audit),
        "modal_ksp_handle_count": 0,
        "modal_ksp_solve_count": 0,
        "owner_lu_factor_count_local": 1,
        "borrowed_action_identity": {"not_owned": True},
        "side_operation_deltas": {
            side: {"apply_count": 0, "total_iterations": 0}
            for side in ("bottom", "top")
        },
        "last_original_modal_row": {
            "equation": "extract_modal_rows(A_original @ pc_output) - r_modal",
            "finite": True,
            "tolerance": 1.0e-10,
            "relative_backward_error": 5.0e-11,
        },
        "fixed_physical_balh_actions": {
            side: {
                "method": "fixed_physical_balh_once",
                "operator_identity": "borrowed_fixed_physical_balh_active_trace",
            }
            for side in ("bottom", "top")
        },
        "feedback_method": None,
        "modal_solver_policy": policy_binding,
    }
    candidate_inventory = {
        "modal_inner_method": method,
        "modal_actual_method": method,
        "modal_actual_solver_inventory_key": (
            "task041_v13_consistent_modal_surrogate"
        ),
        "v13_actual_solver_inventory": actual_v13,
        "modal_solver_policy": policy_binding,
        "v13_same_B_objects_for_all_LDU_terms_and_modal_Schur": True,
        "v13_modal_ksp_solve_count": 0,
        "v13_modal_ksp_handle_count": 0,
        "v13_side_solver_entry_zero_supported": True,
        "v13_fixed_physical_balh_action_identity": "fixed_physical_balh_once",
        "v13_pc_apply_count": 1,
        "borrowed_side_inverse_inventory_by_side": {
            side: {"p4_factor_count": 1, "direct_factor_count": 1}
            for side in ("bottom", "top")
        },
    }
    if tamper == "method":
        actual_v13["method"] = "fixed_h6_modal_gmres_research"
    elif tamper == "side_apply_count":
        actual_v13["side_operation_deltas"]["bottom"]["apply_count"] = 1
    elif tamper == "modal_count":
        actual_v13["modal_count"] = 799
    elif tamper == "modal_shape":
        actual_v13["modal_schur_shape"] = [800, 799]
    elif tamper == "modal_column_count":
        actual_v13["modal_schur_column_count"] = 799
    elif tamper == "missing_column":
        actual_v13["build_audit"]["remaining_columns_applied_once"].pop()
    elif tamper == "duplicate_column":
        actual_v13["build_audit"]["remaining_columns_applied_once"][0] = 7
    consumer_summary = {
        "schema": "task041.side_balh.candidate_consumer.v1",
        "run_directory": str(consumer_root),
        "source_sha": "e" * 40 if tamper == "source" else source_sha,
        "status": "task041_consumer_completed",
        "classification": "TASK041_CONSUMER_PASS",
        "qualification_method": (
            "task041_v13_consistent_fixed_balh_modal_surrogate_with_original_outer_fgmres"
        ),
        "fixed_h6_modal_gmres_research": fixed_binding,
        "modal_solver_policy": policy_id,
        "modal_feedback_binding": None,
        "setup": {
            "candidate_inventory": candidate_inventory,
            "full_formal": {
                "solve": {
                    "inventory": {
                        "task041_v13_consistent_modal_surrogate": actual_v13,
                        "modal_solver_policy": policy_binding,
                    }
                }
            },
        },
        "gates": {"pass": True},
        "lifecycle": {},
        "markers": {"observed": []},
        "process_group_gone": True,
        **v13_metadata,
    }
    consumer_summary["rank_numa_evidence"] = rank_summary["rank_numa_evidence"]
    v13_initial_gate = supervisor._task041_v13_initial_resource_gate_record(
        384 * 2**30, 80 * 2**30
    )
    assert v13_initial_gate["pass"] is True
    rank_count = 8
    hard_cap = 85_899_345_920
    reserve = 8_589_934_592
    floor = 412_316_860_416
    fresh_B = 10_000_000_000
    phase_name = "outer_PC_with_retained_workspaces"
    known_by_rank = [16] * rank_count
    zeros_by_rank = [0] * rank_count
    delta_by_rank = list(known_by_rank)
    required = sum(delta_by_rank) + reserve
    node0_free = floor + required + 100
    node1_free = 80 * 2**30 + sum(delta_by_rank)
    aggregate_free = node0_free + node1_free
    host_available = floor + required + 200
    cgroup_headroom = required + 300
    sample_sha = "a" * 64
    outer_report = {
        "phase": "outer_restart32_workspace",
        "target_restart": 32,
        "known_additional_bytes_by_rank": known_by_rank,
        "additional_temporary_bytes_by_rank": zeros_by_rank,
        "additional_replicated_bytes_by_rank": zeros_by_rank,
        "phase_memory_projection": {
            "phase_reports": {
                phase_name: {
                    "known_additional_bytes_by_rank": known_by_rank,
                    "additional_temporary_bytes_by_rank": zeros_by_rank,
                    "additional_replicated_bytes_by_rank": zeros_by_rank,
                    "additional_bytes_by_rank": delta_by_rank,
                }
            },
            "phase_total_bytes": {phase_name: sum(delta_by_rank)},
            "selected_phase": phase_name,
            "selected_phase_payload_bytes": sum(delta_by_rank),
        },
    }
    outer_request_sha = hashlib.sha256(
        json.dumps(outer_report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    outer_projected = fresh_B + required
    rank_pids = list(range(1001, 1001 + rank_count))
    outer_receipt_payload = {
        "phase": "outer_restart32_workspace",
        "request_sha256": outer_request_sha,
        "invocation_id": invocation_id,
        "source_sha": source_sha,
        "unit": unit,
        "sample_row_sha256": sample_sha,
        "sample_root_pid": 999,
        "rank_pids": rank_pids,
        "resource_B_bytes": fresh_B,
        "node0_memfree_bytes": node0_free,
        "node1_memfree_bytes": node1_free,
        "aggregate_memfree_bytes": aggregate_free,
        "aggregate_memfree_reserve_bytes": floor,
        "aggregate_floor_headroom_bytes": aggregate_free - floor,
        "node1_phase_additional_bytes": sum(delta_by_rank),
        "node1_headroom_after_phase_additional_bytes": (
            node1_free - sum(delta_by_rank)
        ),
        "initial_resource_gate": {
            "required": False,
            "source": "supervisor_resource_preflight",
            "initial_aggregate_memfree_minimum_bytes": 464 * 2**30,
            "initial_node1_memfree_minimum_bytes": 80 * 2**30,
        },
        "selected_memory_phase": phase_name,
        "selected_memory_phase_payload_bytes": sum(delta_by_rank),
        "additional_bytes_by_rank": delta_by_rank,
        "cap_bytes": hard_cap,
        "W_policy_reserve_bytes": reserve,
        "floor_bytes": floor,
        "host_available_bytes": host_available,
        "host_headroom_after_aggregate_reserve_bytes": host_available - floor,
        "cgroup_limit_state": "finite",
        "cgroup_headroom_bytes": cgroup_headroom,
        "projected_B_plus_delta_plus_W_bytes": outer_projected,
    }
    outer_authority = {
        "schema": "task041.v13.modal_builder_admission.v1",
        "phase": "outer_restart32_workspace",
        "status": "pass",
        "decision": "continue",
        "request_sha256": outer_request_sha,
        "authority_receipt_payload": outer_receipt_payload,
        "authority_receipt_sha256": hashlib.sha256(
            json.dumps(
                outer_receipt_payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest(),
        "fresh_job_authority_bytes": fresh_B,
        "cap_bytes": hard_cap,
        "W_policy_reserve_bytes": reserve,
        "floor_bytes": floor,
        "additional_bytes_by_rank": delta_by_rank,
        "additional_temporary_bytes_by_rank": zeros_by_rank,
        "additional_replicated_bytes_by_rank": zeros_by_rank,
        "selected_memory_phase": phase_name,
        "selected_memory_phase_payload_bytes": sum(delta_by_rank),
        "external_resource_gates": {
            key: True
            for key in (
                "bound_fresh_supervisor_sample",
                "tree_cgroup_and_all_mpi_ranks",
                "initial_aggregate_memfree_gate",
                "initial_node1_memfree_gate",
                "aggregate_floor_headroom",
                "node1_phase_headroom",
                "host_floor_headroom",
                "cgroup_ancestor_headroom",
                "case_cap_projection",
                "sample_cost_contract",
            )
        },
        "sample_row_sha256": sample_sha,
        "sample_age_seconds": 0.5,
        "root_pid": 999,
        "rank_pids": rank_pids,
        "node0_memfree_bytes": node0_free,
        "node1_memfree_bytes": node1_free,
        "aggregate_memfree_bytes": aggregate_free,
        "aggregate_memfree_reserve_bytes": floor,
        "aggregate_floor_headroom_bytes": aggregate_free - floor,
        "node1_phase_additional_bytes": sum(delta_by_rank),
        "node1_headroom_after_phase_additional_bytes": (
            node1_free - sum(delta_by_rank)
        ),
        "host_available_bytes": host_available,
        "host_headroom_after_aggregate_reserve_bytes": host_available - floor,
        "cgroup_headroom_bytes": cgroup_headroom,
        "cgroup_limit_state": "finite",
        "projected_B_plus_delta_plus_W_bytes": outer_projected,
        "cost_assessment": {
            "scope": "outer_ksp_workspace_admission",
            "status": "workspace_model_valid",
            "target_restart": 32,
            "W_policy_reserve_bytes": reserve,
            "target_is_elapsed_stop": False,
        },
    }
    consumer_summary["setup"]["full_formal"]["solve"][
        "task041_v13_outer_control"
    ] = {
        "schema": "task041.v13.outer_control.v1",
        "policy_id": policy_id,
        "enabled": True,
        "initial_restart": 32,
        "configured_max_it": 128,
        "final_restart": 32,
        "total_iterations": 4,
        "restart64_trial_count": 0,
        "total_wall_seconds": 1.25,
        "cumulative_pc_apply_count": 4,
        "cumulative_bottom_action_apply_count": 4,
        "cumulative_top_action_apply_count": 4,
        "restart_history": [
            {"iteration": 0, "restart": 32, "reason": "initial"}
        ],
        "initial_restart32_workspace_report": outer_report,
        "initial_restart32_authority": outer_authority,
        "restart64_evidence": None,
        "restart64_decision": None,
        "finite_stop_windows": [],
        "finite_stop": None,
    }
    if tamper in {"boundary_terminal", "crossed_boundary_without_evidence"}:
        outer_control = consumer_summary["setup"]["full_formal"]["solve"][
            "task041_v13_outer_control"
        ]
        solve_record = consumer_summary["setup"]["full_formal"]["solve"]
        terminal_residuals = {
            "reported_relative_residual": 1.0e-9,
            "global_true_relative_residual": 1.1e-9,
            "bottom_true_relative_residual": 1.2e-9,
            "top_true_relative_residual": 1.3e-9,
            "modal_true_relative_residual": 1.4e-9,
        }
        if tamper == "boundary_terminal":
            terminal_reason = 2  # Synthetic PETSc-positive convergence reason.
            terminal_iteration = 48
            terminal_decision = "CONVERGED_RTOL"
            terminal_pass = True
        else:
            terminal_reason = -3
            terminal_iteration = 49
            terminal_decision = "DIVERGED_MAX_IT"
            terminal_pass = False
            terminal_residuals["global_true_relative_residual"] = 1.0e-3
        outer_control.update(
            {
                "total_iterations": terminal_iteration,
                "final_reason": terminal_reason,
                "final_reason_name": terminal_decision,
            }
        )
        solve_record.update(
            {
                "ksp_type": "fgmres",
                "iterations": terminal_iteration,
                "max_it": 128,
                "converged_reason": terminal_reason,
                "pass": terminal_pass,
                "postsolve": {
                    **terminal_residuals,
                    "threshold": 5.0e-9,
                    "reason": terminal_reason,
                    "decision": terminal_decision,
                    "all_finite_nonnegative": True,
                    "pass": terminal_pass,
                },
            }
        )
    consumer_bytes = json.dumps(consumer_summary, sort_keys=True).encode()
    consumer_path = consumer_root / "consumer_summary.json"
    consumer_path.write_bytes(consumer_bytes)
    consumer_artifact = {
        "path": str(consumer_path),
        "bytes": len(consumer_bytes),
        "sha256": hashlib.sha256(consumer_bytes).hexdigest(),
    }
    if tamper == "bytes":
        consumer_artifact["bytes"] += 1
    elif tamper == "sha":
        consumer_artifact["sha256"] = "0" * 64

    launch_path = root / "launch_manifest.json"
    launch = {
        "schema": service.LAUNCH_SCHEMA,
        "unit": unit,
        "model_id": model_id,
        "source_sha": source_sha,
        "invocation_id": invocation_id,
        "supervision_root": str(root),
        "modal_solver_policy": policy_id,
        "fixed_h6_modal_gmres_research": fixed_binding,
        **v13_metadata,
        "parent_environment_threads": dict(
            task041_balh_workflow.TASK041_V13_REQUIRED_THREAD_ENVIRONMENT
        ),
    }
    launch_path.write_text(json.dumps(launch, sort_keys=True) + "\n")
    launch_sha = supervisor._sha256_file(launch_path)
    supervision_record = {
        "path": str(launch_path),
        "sha256": launch_sha,
        "invocation_id": "wrong-invocation" if tamper == "invocation" else invocation_id,
        "source_sha": source_sha,
        "modal_solver_policy": policy_id,
        "fixed_h6_modal_gmres_research": fixed_binding,
    }
    registered_contract = dict(task041_balh_service_contract(model_id))
    registered_contract.update(
        {
            key: value
            for key, value in v13_metadata.items()
            if key != "environment_threads"
        }
    )
    if tamper == "resource_cap":
        registered_contract["memory_cap_bytes"] += 1
    supervisor_summary = {
        "schema": "task041.public.supervisor.v1",
        "run_directory": str(inner),
        "output_directory": str(inner),
        "source_sha": source_sha,
        "modal_solver_policy": policy_id,
        "fixed_h6_modal_gmres_research": fixed_binding,
        **v13_metadata,
        "supervision_record": supervision_record,
        "service_contract": registered_contract,
        "consumer": {"summary_artifact": consumer_artifact},
        "v13_initial_aggregate_resource_gate": v13_initial_gate,
        "phase_results": {
            "consumer": {
                "owned_session_id": owned_session_cleanup["session_id"],
                "owned_session_cleanup": owned_session_cleanup,
            }
        },
    }
    run_summary = dict(supervisor_summary)
    run_manifest = {
        "source_sha": source_sha,
        "modal_solver_policy": policy_id,
        "fixed_h6_modal_gmres_research": fixed_binding,
        **v13_metadata,
        "supervision_record": supervision_record,
        "model_id": model_id,
        "output_directory": str(inner),
    }
    supervisor._write_json(inner / "supervisor_summary.json", supervisor_summary)
    supervisor._write_json(inner / "run_summary.json", run_summary)
    supervisor._write_json(inner / "run_manifest.json", run_manifest)
    public_command = ["python", "scripts/run_case.py", "input.dat"]
    public_stdout = {
        **supervisor_summary,
        "summary": str(inner / "run_summary.json"),
        "manifest": str(inner / "run_manifest.json"),
    }
    if tamper == "policy":
        public_stdout["modal_solver_policy"] = "task041_v12_bounded_inexact_modal"
    elif tamper == "path":
        public_stdout["summary"] = str(inner / "wrong_summary.json")
    public_stdout_path = root / "log" / "public_command_stdout.txt"
    public_stdout_path.write_text(json.dumps(public_stdout, sort_keys=True) + "\n")
    outer_summary = {
        "schema": "task041.supervised_public_command.v1",
        "supervision_root": str(root),
        "model_id": model_id,
        "modal_solver_policy": policy_id,
        "fixed_h6_modal_gmres_research": fixed_binding,
        **v13_metadata,
        "resolved_memory_policy": {
            "policy": task041_balh_workflow.TASK041_V13_MEMORY_POLICY,
            "membind_node": None,
            "source": "resolved_fixed_h6_modal_gmres_research_binding",
        },
        "launch_manifest": {"path": str(launch_path), "sha256": launch_sha},
        "phase_result": {"stdout": str(public_stdout_path), "argv": public_command},
    }
    contract = {
        "unit": unit,
        "model_id": model_id,
        "modal_solver_policy": policy_id,
        "fixed_h6_modal_gmres_research": fixed_binding,
    }
    kwargs = {
        "supervision_root": root,
        "launch_manifest": launch,
        "sealed_public_command": public_command,
        "expected_source_sha": source_sha,
        "terminal_invocation_id": invocation_id,
        "expected_unit": unit,
    }
    if tamper in {None, "boundary_terminal"}:
        checked = supervisor._consumer_result(
            consumer_root,
            expected_fixed_h6_modal_gmres_research=True,
            expected_modal_solver_policy=policy_id,
            expected_fixed_h6_binding=fixed_binding,
            owned_session_cleanup=owned_session_cleanup,
        )
        assert checked["fixed_h6_method_validation"]["pass"] is True
        assert checked["v13_outer_control_validation"]["pass"] is True
        if tamper == "boundary_terminal":
            assert checked["v13_outer_control_validation"][
                "restart64_terminal_boundary_accepted"
            ] is True
        assert service._modal_solver_policy_matches_request(
            contract, outer_summary, **kwargs
        ) is True
    elif tamper == "crossed_boundary_without_evidence":
        checked = supervisor._consumer_result(
            consumer_root,
            expected_fixed_h6_modal_gmres_research=True,
            expected_modal_solver_policy=policy_id,
            expected_fixed_h6_binding=fixed_binding,
            owned_session_cleanup=owned_session_cleanup,
        )
        assert checked["v13_outer_control_validation"]["pass"] is False
        assert any(
            error == "outer_crossed_restart_boundary_without_window_evidence"
            for error in checked["v13_outer_control_validation"]["errors"]
        )
        assert service._modal_solver_policy_matches_request(
            contract, outer_summary, **kwargs
        ) is False
    else:
        assert service._modal_solver_policy_matches_request(
            contract, outer_summary, **kwargs
        ) is False

    # The finalizer passes the same invocation context for the legacy default;
    # a None request must remain on the old no-policy path.
    assert service._modal_solver_policy_matches_request(
        {"model_id": model_id, "modal_solver_policy": None},
        {"modal_solver_policy": None, "setup": {}},
        **kwargs,
    ) is True

    public_stdout["summary"] = str(inner / "supervisor_summary.json")
    public_stdout_path.write_text(json.dumps(public_stdout, sort_keys=True) + "\n")
    assert service._modal_solver_policy_matches_request(
        contract, outer_summary, **kwargs
    ) is False
