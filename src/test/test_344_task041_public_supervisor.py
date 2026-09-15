"""Focused contracts for the Task041 public MPI1 supervisor boundary."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.task041_exact_side_workflow import task041_inner_mpi_environment
from src.io.execution_plan import (
    TASK041_PUBLIC_SUPERVISOR_ADAPTER,
    method_adapter_available,
    method_adapter_identity,
)
from src.io.input_validation import (
    TASK041_MODEL_ID,
    TASK041_RUN_ID,
    TASK041_SHORTWAVE_MODEL_IDS,
    load_and_resolve,
)
from src.runners import task038_launcher as launcher
from src.runners import task041_supervisor as supervisor

ROOT = Path(__file__).resolve().parents[2]


class _Clock:
    def __init__(self, *values: float):
        self.values = list(values)

    def __call__(self) -> float:
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


class _FakeProcess:
    _next_pid = 41000

    def __init__(self, returncode: int = 0, on_wait=None, poll_results=None):
        self.pid = _FakeProcess._next_pid
        _FakeProcess._next_pid += 1
        self.returncode = returncode
        self.on_wait = on_wait
        self.poll_results = (
            list(poll_results) if poll_results is not None else None
        )
        self.poll_count = 0
        self.terminated = False

    def poll(self):
        self.poll_count += 1
        if self.poll_results is not None:
            if self.poll_results:
                return self.poll_results.pop(0)
            return self.returncode
        if self.poll_count == 1 and not self.terminated:
            return None
        return self.returncode

    def wait(self):
        if self.on_wait is not None:
            self.on_wait()
            self.on_wait = None
        return self.returncode


class _FakePopen:
    def __init__(self, *, returncodes=None, on_wait=None, poll_results=None):
        self.returncodes = iter(returncodes or [0])
        self.on_wait = on_wait
        self.poll_results = poll_results
        self.calls = []
        self.processes = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        callback = None
        if self.on_wait is not None:
            callback = self.on_wait(list(argv))
        process = _FakeProcess(
            next(self.returncodes), callback, poll_results=self.poll_results
        )
        self.processes.append(process)
        return process


class _Samples:
    def __init__(self, *, memory: int = 100, swap: bool = True, cgroup_swap=None):
        self.memory = memory
        self.swap = swap
        self.cgroup_swap = cgroup_swap
        self.counts = {}

    def __call__(self, pid: int) -> dict[str, object]:
        count = self.counts.get(pid, 0)
        self.counts[pid] = count + 1
        rss = self.memory if count < 2 else 0
        return {
            "memory_authority_bytes": rss,
            "job_no_swap": self.swap,
            "process_tree": {
                "rss_bytes": rss,
                "swap_bytes": 0 if self.swap else 1,
                "all_status_readable": True,
                "smaps": {
                    "pss_bytes": rss,
                    "uss_bytes": rss // 2,
                },
            },
            "job_cgroup": {
                "dedicated_job_cgroup": self.cgroup_swap is not None,
                "swap_current_bytes": self.cgroup_swap or 0,
            },
        }


def _run_phase(
    tmp_path: Path,
    *,
    sample,
    clock=None,
    terminate=None,
    popen_factory=None,
    sleep=None,
    process_group_gone=None,
    warning_memory_bytes=None,
    hard_memory_bytes=None,
    process_tree_rss_warning_bytes=None,
    process_tree_rss_cap_bytes=None,
    timeout_seconds=None,
    workflow_started=0.0,
    phase_elapsed_timeout=False,
    sample_root_pid=None,
    min_memavailable_bytes=None,
    min_cgroup_ancestor_headroom_bytes=None,
    cumulative_compute_used_seconds=0.0,
    cumulative_compute_limit_seconds=None,
    global_swap_baseline=None,
    partial_phase_results=None,
    enforce_time_stops=True,
):
    (tmp_path / "numerical_output" / "log").mkdir(parents=True)
    limits = {
        name: value
        for name, value in (
            ("warning_memory_bytes", warning_memory_bytes),
            ("hard_memory_bytes", hard_memory_bytes),
            ("timeout_seconds", timeout_seconds),
        )
        if value is not None
    }
    return supervisor._run_phase(
        "producer",
        ["mpiexec", "-n", "1", "fake"],
        tmp_path / "producer",
        log_root=tmp_path / "numerical_output" / "log",
        environment={"OMP_NUM_THREADS": "1"},
        repository_root=tmp_path,
        workflow_started=workflow_started,
        popen_factory=popen_factory or _FakePopen(),
        sample_factory=sample,
        terminate_factory=terminate or (lambda process: {"requested": True}),
        monotonic=clock or _Clock(0.0),
        sleep=sleep or (lambda _seconds: None),
        poll_interval=0.01,
        memory_stages_path=tmp_path
        / "numerical_output"
        / "log"
        / "memory_stages.jsonl",
        marker_path=tmp_path
        / "numerical_output"
        / "log"
        / "memory_stage_markers.jsonl",
        process_group_gone=process_group_gone or (lambda _pid: True),
        phase_elapsed_timeout=phase_elapsed_timeout,
        process_tree_rss_warning_bytes=process_tree_rss_warning_bytes,
        process_tree_rss_cap_bytes=process_tree_rss_cap_bytes,
        sample_root_pid=sample_root_pid,
        min_memavailable_bytes=min_memavailable_bytes,
        min_cgroup_ancestor_headroom_bytes=min_cgroup_ancestor_headroom_bytes,
        cumulative_compute_used_seconds=cumulative_compute_used_seconds,
        cumulative_compute_limit_seconds=cumulative_compute_limit_seconds,
        global_swap_baseline=global_swap_baseline,
        partial_phase_results=partial_phase_results,
        enforce_time_stops=enforce_time_stops,
        **limits,
    )


def test_sparse_smaps_sampler_keeps_authority_polling_and_throttles_smaps():
    calls = []
    clock = iter((0.0, 1.0, 30.0, 30.1))

    def base_sampler(pid, *, include_smaps):
        calls.append((pid, include_smaps))
        return {"pid": pid, "include_smaps": include_smaps}

    sampler = launcher._task041_sparse_smaps_sample_factory(
        base_sampler, lambda: next(clock)
    )

    assert [sampler(17) for _ in range(4)] == [
        {"pid": 17, "include_smaps": True},
        {"pid": 17, "include_smaps": False},
        {"pid": 17, "include_smaps": True},
        {"pid": 17, "include_smaps": False},
    ]
    assert calls == [(17, True), (17, False), (17, True), (17, False)]


def test_task041_adapter_is_exact_and_task039_remains_separate():
    assert (
        method_adapter_identity("hybrid_iterative", TASK041_MODEL_ID)
        == TASK041_PUBLIC_SUPERVISOR_ADAPTER
    )
    assert method_adapter_identity(
        "hybrid_iterative", "task039_5nm_hybrid_iterative_m480_candidate"
    ) == "task039.hybrid_iterative"
    for model_id in TASK041_SHORTWAVE_MODEL_IDS:
        assert (
            method_adapter_identity("hybrid_iterative", model_id)
            == TASK041_PUBLIC_SUPERVISOR_ADAPTER
        )
        assert method_adapter_available("hybrid_iterative", model_id) is True


@pytest.mark.parametrize(
    ("filename", "model_id", "run_id", "mode_count"),
    [
        (
            "3nm_p6h3_m800_mpi8.dat",
            "task041_3nm_exact_side_hybrid_iterative_p6h3_m800",
            "task041_3nm_p6h3_m800_mpi8",
            800,
        ),
        (
            "3nm_p6h3_m1200_mpi8.dat",
            "task041_3nm_exact_side_hybrid_iterative_p6h3_m1200",
            "task041_3nm_p6h3_m1200_mpi8",
            1200,
        ),
        (
            "3nm_p6h2_m1200_mpi8.dat",
            "task041_3nm_exact_side_hybrid_iterative_p6h2_m1200",
            "task041_3nm_p6h2_m1200_mpi8",
            1200,
        ),
    ],
)
def test_shortwave_supervisor_identity_comes_from_validated_official_dat(
    filename, model_id, run_id, mode_count
):
    specification = load_and_resolve(ROOT / "input/official/task041" / filename)
    identity = supervisor._validate_specification(specification, ROOT)
    assert identity["model_id"] == model_id
    assert identity["run_id"] == run_id
    assert identity["requested_modes"] == mode_count
    assert identity["mpi_size"] == 8
    assert identity["input_sha256"] == specification.input_sha256
    assert identity["physical_model_sha256"] == specification.physical_model_sha256
    assert identity["resolved_config_sha256"]
    limits = supervisor._runtime_limits_for_identity(identity)
    if "p6h2" in filename:
        assert limits == {
            "warning_memory_bytes": 1539316278886,
            "hard_memory_bytes": 1759218604442,
            "swap_limit_bytes": 0,
            "timeout_seconds": 259200,
        }
        assert supervisor.task041_shortwave_timeout_scope(model_id) == "workflow"
    else:
        assert limits == dict(supervisor.TASK041_SHORTWAVE_WORKFLOW_LIMITS)
        assert supervisor.task041_shortwave_timeout_scope(model_id) == "phase"



def test_inner_mpi_environment_is_copied_and_sanitized():
    original = {
        "PATH": "/bin",
        "OMPI_COMM_WORLD_SIZE": "8",
        "PMIX_RANK": "0",
        "DISPLAY": ":0",
        "OMP_NUM_THREADS": "16",
    }
    cleaned = task041_inner_mpi_environment(original)
    assert original["OMP_NUM_THREADS"] == "16"
    assert "OMPI_COMM_WORLD_SIZE" not in cleaned
    assert "PMIX_RANK" not in cleaned
    assert "DISPLAY" not in cleaned
    assert cleaned["PATH"] == "/bin"
    for name in supervisor.TASK041_REQUIRED_THREADS:
        assert cleaned[name] == "1"


def test_outer_mpi_launch_identity_accepts_openmpi_markers(monkeypatch):
    monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: 1)
    monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: 0)
    monkeypatch.setenv("OMPI_COMM_WORLD_SIZE", "1")
    monkeypatch.setenv("OMPI_COMM_WORLD_RANK", "0")

    identity = supervisor._outer_mpi_launch_identity()

    assert identity == {
        "launcher": "OpenMPI",
        "markers": {
            "OMPI_COMM_WORLD_SIZE": "1",
            "OMPI_COMM_WORLD_RANK": "0",
        },
        "mpi_size": 1,
        "mpi_rank": 0,
        "launched_via_mpiexec": True,
    }


def test_v2_outer_identity_accepts_native_public_singleton(monkeypatch):
    monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: 1)
    monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: 0)
    monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
    monkeypatch.delenv("OMPI_COMM_WORLD_RANK", raising=False)

    identity = supervisor._outer_mpi_launch_identity(
        "task041_schur_speed_v2"
    )

    assert identity["launcher"] == "native_python_singleton"
    assert identity["mpi_size"] == 1
    assert identity["mpi_rank"] == 0
    assert identity["launched_via_mpiexec"] is False
    assert identity["native_public_singleton"] is True
    assert identity["qualification"] == "native_public_singleton"


def test_v2_outer_identity_rejects_outer_multi_rank(monkeypatch):
    monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: 2)
    monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: 0)
    monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
    monkeypatch.delenv("OMPI_COMM_WORLD_RANK", raising=False)

    with pytest.raises(supervisor.Task041SupervisorError) as error:
        supervisor._outer_mpi_launch_identity("task041_schur_speed_v2")

    assert error.value.classification == "task041_identity_failure"
    assert error.value.stage == "outer_mpi_identity"


@pytest.mark.parametrize(
    ("size_marker", "rank_marker"),
    [(None, "0"), ("2", "0"), ("1", "1")],
)
def test_outer_mpi_launch_identity_rejects_missing_or_mismatched_markers(
    monkeypatch, size_marker, rank_marker
):
    monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: 1)
    monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: 0)
    if size_marker is None:
        monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
    else:
        monkeypatch.setenv("OMPI_COMM_WORLD_SIZE", size_marker)
    monkeypatch.setenv("OMPI_COMM_WORLD_RANK", rank_marker)

    with pytest.raises(supervisor.Task041SupervisorError) as error:
        supervisor._outer_mpi_launch_identity()

    assert error.value.classification == "task041_identity_failure"
    assert error.value.stage == "outer_mpi_identity"


def test_phase_handoff_records_rss_drop_and_pss_uss_without_summing(tmp_path):
    phase = _run_phase(tmp_path, sample=_Samples())
    assert phase["returncode"] == 0
    assert phase["rss_drop"]["pass"] is True
    assert phase["process_group_gone"] is True
    assert phase["peak_memory_authority_bytes"] == 100
    assert phase["peak_pss_bytes"] == 100
    assert phase["peak_uss_bytes"] == 50
    assert phase["rss_drop"]["before_process_tree_rss_bytes"] == 100
    assert phase["rss_drop"]["after_process_tree_rss_bytes"] == 0
    assert phase["sample_count"] == 1
    assert phase["smaps_complete_sample_count"] == 1
    assert phase["resource_sampling_semantics"].startswith("RSS/VmSwap")


def test_v2_rss_cap_uses_complete_process_tree_rss_in_addition_to_authority(
    tmp_path,
):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        return {"requested": True}

    sample = _complete_resource_sample(rss=250)
    sample["memory_authority_bytes"] = 100
    samples = iter((sample, _complete_resource_sample(rss=100)))
    phase = _run_phase(
        tmp_path,
        sample=lambda _pid: next(samples),
        terminate=terminate,
        hard_memory_bytes=1000,
        process_tree_rss_warning_bytes=180,
        process_tree_rss_cap_bytes=200,
        sample_root_pid=9000,
        process_group_gone=lambda _pid: True,
    )
    assert phase["termination_reason"] == "process_tree_rss_limit"
    assert phase["process_tree_rss_warning_reached"] is True
    assert phase["limits"]["process_tree_rss_cap_bytes"] == 200
    assert terminated


def test_v2_rss_cap_waits_for_normal_exit_when_tree_rss_is_incomplete(tmp_path):
    terminated = []
    sample = _complete_resource_sample(rss=250)
    sample["memory_authority_bytes"] = 100
    sample["process_tree"]["all_status_readable"] = False
    sample["job_cgroup"].update(
        {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_current_bytes": 100,
            "swap_current_bytes": 0,
        }
    )

    phase = _run_phase(
        tmp_path,
        sample=lambda _pid: sample,
        popen_factory=_FakePopen(poll_results=[None, None, 0]),
        terminate=lambda process: terminated.append(process.pid),
        process_tree_rss_cap_bytes=200,
    )
    assert phase["termination_reason"] is None
    assert phase["sample_count"] == 0
    assert terminated == []


def _complete_resource_sample(
    *,
    rss: int = 100,
    memavailable: int | None = 1024,
    cgroup_state: str = "max_or_unlimited",
    cgroup_current: int | None = None,
    cgroup_headroom: int | None = None,
):
    host_memory = (
        {}
        if memavailable is None
        else {"mem_available_bytes": memavailable}
    )
    job_cgroup = {
        "dedicated_job_cgroup": False,
        "swap_current_bytes": 0,
        "ancestor_hard_limit_state": cgroup_state,
        "ancestor_memory_headroom_bytes": cgroup_headroom,
        "ancestor_memory": [],
    }
    if cgroup_state == "finite":
        job_cgroup.update(
            {
                "memory_limit_state": "finite",
                "memory_limit_bytes": 1024,
                "memory_current_bytes": cgroup_current,
                "memory_headroom_bytes": cgroup_headroom,
                "ancestor_hard_limit_bytes": 1024,
                "ancestor_memory": [
                    {
                        "memory_limit_state": "finite",
                        "memory_current_bytes": cgroup_current,
                        "memory_headroom_bytes": cgroup_headroom,
                    }
                ],
            }
        )
    return {
        "memory_authority_bytes": rss,
        "job_no_swap": True,
        "host_memory": host_memory,
        "process_tree": {
            "rss_bytes": rss,
            "swap_bytes": 0,
            "all_status_readable": True,
            "smaps": {"pss_bytes": None, "uss_bytes": None},
        },
        "job_cgroup": job_cgroup,
    }


def test_supervised_public_command_keeps_outer_evidence_and_limits_separate(
    tmp_path,
):
    public_root = tmp_path / "public_runroot"
    final_copy_marker = public_root / "final-copy-complete"
    command = [
        "qualified-python",
        "scripts/run_case.py",
        "one_dat",
        "--task041-performance-profile",
        "task041_schur_speed_v2",
    ]
    launch_manifest = {
        "profile_id": "task041_schur_speed_v2",
        "model_id": "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8",
        "source_sha": "a" * 40,
        "parent_pid": os.getpid(),
        "invocation_id": "test-invocation",
        "ledger_owner": "service_finalizer",
        "ledger_path": str((tmp_path / "compute_wall_ledger.json").resolve()),
    }
    calls = []
    sample_observations = []

    class _FinalCopyProcess(_FakeProcess):
        def __init__(self):
            super().__init__(poll_results=[None, None, 0])

        def poll(self):
            if self.poll_results and self.poll_results[0] == 0:
                final_copy_marker.parent.mkdir(parents=True, exist_ok=True)
                final_copy_marker.write_text("complete", encoding="utf-8")
            return super().poll()

    def popen_factory(argv, **kwargs):
        manifest_path = Path(
            argv[argv.index("--task041-supervision-record") + 1]
        )
        assert manifest_path.is_file()
        assert json.loads(manifest_path.read_text(encoding="utf-8")) == (
            launch_manifest
        )
        calls.append((list(argv), kwargs))
        return _FinalCopyProcess()

    def sample(_pid):
        sample_observations.append((_pid, final_copy_marker.exists()))
        return _complete_resource_sample(rss=100)

    sample.smaps_interval_seconds = 30.0
    profile_contract = {
        "profile_id": "task041_schur_speed_v2",
        "model_id": "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8",
        "memory_cap_bytes": 900,
        "warning_memory_bytes": 810,
        "phase_budgets_seconds": {
            "shared_S0_S1_S3": 21600.0,
            "S2": 7200.0,
            "S4": 100.0,
        },
        "active_consumer_phase": "S4",
        "batch_budget_seconds": 1000.0,
    }
    ledger_snapshot = {
        "S4_used_seconds": 20.0,
        "batch_used_compute_wall_seconds": 30.0,
        "used_compute_wall_seconds": 30.0,
    }
    resource_limits = {
        "warning_memory_bytes": 1000,
        "hard_memory_bytes": 2000,
        "swap_limit_bytes": 0,
        "min_memavailable_bytes": 384,
        "min_cgroup_ancestor_headroom_bytes": 384,
    }
    environment = {
        name: "1" for name in supervisor.TASK041_REQUIRED_THREADS
    }
    result = supervisor.run_task041_supervised_public_command(
        command,
        tmp_path / "supervision",
        profile_contract=profile_contract,
        ledger_snapshot=ledger_snapshot,
        resource_limits=resource_limits,
        environment=environment,
        sample_factory=sample,
        repository_root=tmp_path,
        popen_factory=popen_factory,
        terminate_factory=lambda _process: pytest.fail(
            "normal public completion must not request termination"
        ),
        monotonic=_Clock(0.0, 0.0, 0.1, 0.2, 0.3, 0.3),
        sleep=lambda _seconds: None,
        process_group_gone=lambda _pid: True,
        global_swap_baseline={
            "global_swap_used_bytes": 0,
            "global_pswpin_pages": 0,
            "global_pswpout_pages": 0,
        },
        launch_manifest=launch_manifest,
    )

    supervision_root = tmp_path / "supervision"
    spawned_command = command + [
        "--task041-supervision-record",
        str(supervision_root / "launch_manifest.json"),
    ]
    phase = result["phase_result"]
    assert result["status"] == "completed"
    assert result["result_classification"] == "worker_exit0"
    assert result["budget"]["effective_remaining_seconds"] == 80.0
    assert phase["argv"] == spawned_command
    assert phase["sample_root_pid"] == os.getpid()
    assert phase["sample_root_scope"] == "public_launcher_and_all_descendants"
    assert phase["limits"]["timeout_seconds"] == 80.0
    assert phase["limits"]["cumulative_compute_limit_seconds"] == 100.0
    assert phase["process_group_gone"] is True
    assert phase["termination"] is None
    assert calls[0][0] == spawned_command
    assert sample_observations
    assert {pid for pid, _marker_exists in sample_observations} == {os.getpid()}
    assert any(not marker_exists for _pid, marker_exists in sample_observations)
    assert any(marker_exists for _pid, marker_exists in sample_observations)
    assert final_copy_marker.is_file()
    assert (supervision_root / "memory_stages.jsonl").is_file()
    assert (supervision_root / "markers.jsonl").is_file()
    assert (supervision_root / "log" / "public_command_stdout.txt").is_file()
    assert (supervision_root / "summary.json").is_file()
    assert result["launch_manifest"]["path"] == str(
        supervision_root / "launch_manifest.json"
    )
    assert result["launch_manifest"]["ledger_owner"] == "service_finalizer"
    assert not (public_root / "memory_stages.jsonl").exists()

    failed_root = tmp_path / "failed_supervision"
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    def high_rss_sample(_pid):
        return _complete_resource_sample(rss=901)

    failed = supervisor.run_task041_supervised_public_command(
        command,
        failed_root,
        profile_contract=profile_contract,
        ledger_snapshot=ledger_snapshot,
        resource_limits=resource_limits,
        environment=environment,
        sample_factory=high_rss_sample,
        repository_root=tmp_path,
        popen_factory=_FakePopen(poll_results=[None]),
        terminate_factory=terminate,
        monotonic=_Clock(1.0, 1.0, 1.0, 1.0, 1.0),
        sleep=lambda _seconds: None,
        process_group_gone=lambda _pid: True,
    )
    assert failed["status"] == "failed"
    assert failed["result_classification"] == "process_tree_rss_limit"
    assert terminated


def test_supervised_public_command_stops_before_spawn_when_budget_is_exhausted(
    tmp_path,
):
    profile_contract = {
        "profile_id": "task041_schur_speed_v2",
        "model_id": "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8",
        "memory_cap_bytes": 900,
        "warning_memory_bytes": 810,
        "phase_budgets_seconds": {"S4": 100.0},
        "active_consumer_phase": "S4",
        "batch_budget_seconds": 100.0,
    }
    resource_limits = {
        "warning_memory_bytes": 1000,
        "hard_memory_bytes": 2000,
        "swap_limit_bytes": 0,
        "min_memavailable_bytes": 384,
        "min_cgroup_ancestor_headroom_bytes": 384,
    }
    environment = {
        name: "1" for name in supervisor.TASK041_REQUIRED_THREADS
    }
    calls = []

    def unexpected_popen(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("zero remaining budget must not spawn")

    result = supervisor.run_task041_supervised_public_command(
        ["qualified-python", "scripts/run_case.py", "one_dat"],
        tmp_path / "zero_budget",
        profile_contract=profile_contract,
        ledger_snapshot={
            "S4_used_seconds": 100.0,
            "batch_used_compute_wall_seconds": 100.0,
        },
        resource_limits=resource_limits,
        environment=environment,
        sample_factory=lambda _pid: _complete_resource_sample(),
        repository_root=tmp_path,
        popen_factory=unexpected_popen,
    )

    assert result["prestart_stop"] is True
    assert result["result_classification"] == "cumulative_wall_timeout"
    assert result["phase_result"] is None
    assert calls == []
    assert json.loads(
        (tmp_path / "zero_budget" / "summary.json").read_text(
            encoding="utf-8"
        )
    )["prestart_stop"] is True


def test_supervised_public_command_preserves_partial_supervisor_error(
    tmp_path,
):
    profile_contract = {
        "profile_id": "task041_schur_speed_v2",
        "model_id": "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8",
        "memory_cap_bytes": 900,
        "warning_memory_bytes": 810,
        "phase_budgets_seconds": {"S4": 100.0},
        "active_consumer_phase": "S4",
        "batch_budget_seconds": 1000.0,
    }
    resource_limits = {
        "warning_memory_bytes": 1000,
        "hard_memory_bytes": 2000,
        "swap_limit_bytes": 0,
        "min_memavailable_bytes": 384,
        "min_cgroup_ancestor_headroom_bytes": 384,
    }
    environment = {
        name: "1" for name in supervisor.TASK041_REQUIRED_THREADS
    }
    sample_calls = []

    def sample(pid):
        sample_calls.append(pid)
        if len(sample_calls) == 1:
            return _complete_resource_sample(rss=100)
        raise supervisor.Task041SupervisorError(
            "sample failed after spawn",
            classification="task041_resource_sample_failure",
            stage="public_command_resource_sample",
        )

    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    gone_states = iter((False, True, True))
    result = supervisor.run_task041_supervised_public_command(
        ["qualified-python", "scripts/run_case.py", "one_dat"],
        tmp_path / "partial_error",
        profile_contract=profile_contract,
        ledger_snapshot={
            "S4_used_seconds": 20.0,
            "batch_used_compute_wall_seconds": 30.0,
        },
        resource_limits=resource_limits,
        environment=environment,
        sample_factory=sample,
        repository_root=tmp_path,
        popen_factory=_FakePopen(poll_results=[None, None]),
        terminate_factory=terminate,
        monotonic=_Clock(0.0, 0.1, 0.2, 0.3, 0.3),
        sleep=lambda _seconds: None,
        process_group_gone=lambda _pid: next(gone_states),
    )

    assert result["status"] == "failed"
    assert result["result_classification"] == (
        "task041_resource_sample_failure"
    )
    assert result["phase_result"] is not None
    assert result["phase_result"]["partial"] is True
    assert result["phase_result"]["sample_count"] == 1
    assert result["phase_result"]["termination"] is not None
    assert result["phase_result"]["cleanup_attempted"] is True
    assert result["phase_result"]["process_group_gone"] is True
    assert terminated


def test_task041_supervision_record_defers_v2_ledger_after_time_gate(
    tmp_path, monkeypatch
):
    from benchmarks.task041_balh_workflow import task041_schur_speed_v2_contract

    specification = load_and_resolve(
        ROOT / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    source_sha = "a" * 40
    contract = task041_schur_speed_v2_contract(
        str(specification.identity["model_id"])
    )
    ledger_path = tmp_path / "compute_wall_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task041.compute_wall_ledger.v2",
                "used_compute_wall_seconds": contract["batch_budget_seconds"],
                "batch_used_compute_wall_seconds": contract[
                    "batch_budget_seconds"
                ],
                "shared_S0_S1_S3_used_seconds": 21600.0,
                "S2_used_seconds": 7200.0,
                "S4_used_seconds": contract["active_consumer_budget_seconds"],
                "used_status": "measured",
                "basis": "test-local V2 ledger",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    invocation_id = "test-supervision-invocation"
    monkeypatch.setenv("INVOCATION_ID", invocation_id)
    monkeypatch.setattr(
        supervisor,
        "_outer_mpi_launch_identity",
        lambda _profile: {
            "launcher": "native_python_singleton",
            "markers": {
                "OMPI_COMM_WORLD_SIZE": None,
                "OMPI_COMM_WORLD_RANK": None,
            },
            "mpi_size": 1,
            "mpi_rank": 0,
            "launched_via_mpiexec": False,
            "native_public_singleton": True,
            "qualification": "native_public_singleton",
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_write_task041_compute_wall_ledger",
        lambda *_args, **_kwargs: pytest.fail(
            "external supervision must defer the global ledger write"
        ),
    )
    record_path = tmp_path / "launch_manifest.json"
    record_path.write_text(
        json.dumps(
            {
                "profile_id": contract["profile_id"],
                "model_id": specification.identity["model_id"],
                "source_sha": source_sha,
                "scope": contract["scope"],
                "representative_rhs_probe": None,
                "parent_pid": os.getppid(),
                "invocation_id": invocation_id,
                "ledger_owner": "service_finalizer",
                "ledger_path": str(ledger_path.resolve()),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow").mkdir()
    result = supervisor.run_task041_public_supervisor(
        specification,
        source_sha=source_sha,
        run_directory=tmp_path / "workflow",
        compute_wall_ledger_path=ledger_path,
        legacy_native_packet_descriptor=tmp_path / "descriptor.json",
        performance_profile=contract["profile_id"],
        task041_supervision_record=record_path,
        popen_factory=lambda *_args, **_kwargs: pytest.fail(
            "time gate must stop before spawning a worker"
        ),
    )
    assert result["result_classification"] == "cumulative_wall_timeout"
    assert result["supervision_record"]["sha256"] == hashlib.sha256(
        record_path.read_bytes()
    ).hexdigest()
    assert result["ledger_owner"] == "service_finalizer"
    assert result["ledger_update"] == "deferred_to_service_finalizer"
    assert result["used_after"] == "pending"
    assert result["compute_wall_budget"]["used_after"] == "pending"
    assert result["compute_wall_budget"]["used_after_seconds"] is None


def test_balh_public_root_sampling_and_worker_only_termination(tmp_path):
    sampled_pids = []
    terminated = []
    sample_count = {9000: 0}

    def sample(pid):
        sampled_pids.append(pid)
        sample_count[pid] += 1
        sample = _complete_resource_sample(
            rss=100 if sample_count[pid] == 1 else 55
        )
        if sample_count[pid] == 1:
            sample["process_tree"]["smaps"] = {
                "pss_bytes": 80,
                "uss_bytes": 60,
            }
        return sample

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=sample,
        popen_factory=_FakePopen(poll_results=[None, 0]),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        sample_root_pid=9000,
        process_tree_rss_cap_bytes=200,
        clock=_Clock(0.0, 0.1, 0.4, 0.7, 0.7),
    )
    assert sampled_pids == [9000, 9000]
    assert terminated == []
    assert phase["sample_root_pid"] == 9000
    assert phase["worker_process_group_pid"] != 9000
    assert phase["sample_root_scope"] == "public_launcher_and_all_descendants"
    assert phase["rss_drop"]["after_process_tree_rss_bytes"] == 55
    assert phase["rss_drop"]["measurement_scope"] == (
        "public_launcher_root_after_worker_group_exit"
    )
    assert phase["sample_count"] == 2
    assert phase["smaps_complete_sample_count"] == 1
    assert phase["sampling"]["pss_uss_missing_sample_count"] == 1
    assert phase["peak_pss_bytes"] == 80
    assert phase["peak_uss_bytes"] == 60
    assert phase["peak_process_tree_rss_bytes"] == 100
    assert phase["minimum_host_memavailable_bytes"] == 1024
    gaps = phase["sampling"]["sample_timestamp_gap_seconds"]
    assert gaps["count"] == 1
    assert gaps["min"] == pytest.approx(0.6)
    assert gaps["max"] == pytest.approx(0.6)
    raw_records = [
        json.loads(line)
        for line in (
            tmp_path / "numerical_output" / "log" / "memory_stages.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    markers = [
        json.loads(line)
        for line in (
            tmp_path / "numerical_output" / "log" / "memory_stage_markers.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert markers[0]["stage"] == "producer_started"
    assert markers[0]["workflow_started_monotonic_seconds"] == 0.0
    assert markers[0]["clock"] == "CLOCK_MONOTONIC"
    assert [record["sample_role"] for record in raw_records] == [
        "phase_running",
        "phase_end_public_root",
    ]
    assert max(record["process_tree_rss_bytes"] for record in raw_records) == phase[
        "peak_process_tree_rss_bytes"
    ]
    assert min(record["host_memavailable_bytes"] for record in raw_records) == phase[
        "minimum_host_memavailable_bytes"
    ]
    assert max(
        record["pss_bytes"]
        for record in raw_records
        if record["pss_bytes"] is not None
    ) == phase["peak_pss_bytes"]
    assert max(
        record["uss_bytes"]
        for record in raw_records
        if record["uss_bytes"] is not None
    ) == phase["peak_uss_bytes"]
    assert sum(
        record["pss_bytes"] is None or record["uss_bytes"] is None
        for record in raw_records
    ) == phase["sampling"]["pss_uss_missing_sample_count"]
    assert (
        raw_records[1]["sample_elapsed_seconds"]
        - raw_records[0]["sample_elapsed_seconds"]
    ) == pytest.approx(gaps["min"])

    low_sample = lambda _pid: _complete_resource_sample(memavailable=100)
    phase = _run_phase(
        tmp_path / "low",
        sample=low_sample,
        popen_factory=_FakePopen(poll_results=[None]),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        sample_root_pid=9000,
        min_memavailable_bytes=384,
        hard_memory_bytes=10**9,
    )
    assert phase["termination_reason"] == "memavailable_floor"
    assert terminated[-1] != 9000


def _phase_end_gate_sample_pair(first, second):
    samples = iter((first, second))

    def sample(_pid):
        return next(samples)

    return sample


@pytest.mark.parametrize(
    ("second", "phase_kwargs", "reason"),
    [
        (
            _complete_resource_sample(rss=201),
            {"process_tree_rss_cap_bytes": 200},
            "process_tree_rss_limit",
        ),
        (
            {
                **_complete_resource_sample(rss=100),
                "job_no_swap": False,
            },
            {"process_tree_rss_cap_bytes": 200},
            "swap_detected",
        ),
        (
            _complete_resource_sample(memavailable=100),
            {
                "process_tree_rss_cap_bytes": 200,
                "min_memavailable_bytes": 384,
            },
            "memavailable_floor",
        ),
        (
            _complete_resource_sample(
                cgroup_state="finite", cgroup_current=900, cgroup_headroom=100
            ),
            {
                "process_tree_rss_cap_bytes": 200,
                "min_cgroup_ancestor_headroom_bytes": 384,
            },
            "cgroup_headroom_floor",
        ),
        (
            {
                "memory_authority_bytes": 100,
                "job_no_swap": True,
                "process_tree": {
                    "rss_bytes": None,
                    "swap_bytes": None,
                    "all_status_readable": False,
                },
                "job_cgroup": {
                    "dedicated_job_cgroup": True,
                    "readable": True,
                    "memory_current_bytes": 100,
                    "swap_current_bytes": 0,
                },
            },
            {"process_tree_rss_cap_bytes": 200},
            "process_tree_rss_unmeasured",
        ),
    ],
)
def test_v2_phase_end_resource_gate_fails_without_signalling_gone_group(
    tmp_path, second, phase_kwargs, reason
):
    partial = {}
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        return {"requested": True}

    with pytest.raises(supervisor.Task041SupervisorError) as error:
        _run_phase(
            tmp_path,
            sample=_phase_end_gate_sample_pair(
                _complete_resource_sample(rss=100), second
            ),
            popen_factory=_FakePopen(poll_results=[None, 0]),
            terminate=terminate,
            process_group_gone=lambda _pid: True,
            sample_root_pid=9000,
            partial_phase_results=partial,
            clock=_Clock(0.0, 0.1, 0.2, 0.3, 0.4),
            **phase_kwargs,
        )

    record = partial["producer"]
    assert error.value.classification == "task041_resource_sample_failure"
    assert record["termination_reason"] == reason
    assert record["returncode"] == 0
    assert record["process_group_gone"] is True
    assert record["partial"] is True
    assert terminated == []


def test_v2_phase_end_resource_gate_time_failure_keeps_exit_without_signal(tmp_path):
    partial = {}
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        return {"requested": True}

    with pytest.raises(supervisor.Task041SupervisorError):
        _run_phase(
            tmp_path,
            sample=_phase_end_gate_sample_pair(
                _complete_resource_sample(), _complete_resource_sample()
            ),
            popen_factory=_FakePopen(poll_results=[None, 0]),
            process_group_gone=lambda _pid: True,
            sample_root_pid=9000,
            partial_phase_results=partial,
            process_tree_rss_cap_bytes=200,
            timeout_seconds=1.0,
            clock=_Clock(0.0, 0.1, 0.2, 2.0, 2.1),
            terminate=terminate,
        )

    assert partial["producer"]["termination_reason"] == "wall_timeout"
    assert partial["producer"]["returncode"] == 0
    assert partial["producer"]["process_group_gone"] is True
    assert terminated == []


@pytest.mark.parametrize("enforce_time_stops", [True, False])
@pytest.mark.parametrize(
    ("sample_kwargs", "reason"),
    [
        ({"memavailable": None}, "memavailable_unmeasured"),
        ({"memavailable": 100}, "memavailable_floor"),
        (
            {
                "cgroup_state": "finite",
                "cgroup_current": None,
                "cgroup_headroom": None,
            },
            "cgroup_headroom_unmeasured",
        ),
        (
            {
                "cgroup_state": "finite",
                "cgroup_current": 900,
                "cgroup_headroom": 100,
            },
            "cgroup_headroom_floor",
        ),
    ],
)
def test_balh_runtime_reserves_reject_missing_or_low_measurements(
    tmp_path, sample_kwargs, reason, enforce_time_stops
):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=lambda _pid: _complete_resource_sample(**sample_kwargs),
        popen_factory=_FakePopen(poll_results=[None]),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        sample_root_pid=9100,
        min_memavailable_bytes=384,
        min_cgroup_ancestor_headroom_bytes=384,
        hard_memory_bytes=10**9,
        enforce_time_stops=enforce_time_stops,
    )
    assert phase["termination_reason"] == reason
    assert terminated


@pytest.mark.parametrize(
    "record",
    [
        {"cgroup_ancestor_hard_limit_state": "not_applicable_root"},
        {"cgroup_ancestor_hard_limit_state": "max_or_unlimited"},
        {
            "cgroup_ancestor_hard_limit_state": "max_or_unlimited",
            "cgroup_ancestor_limit_states": ["max_or_unlimited"],
        },
    ],
)
def test_balh_unlimited_or_root_cgroup_does_not_require_headroom(record):
    assert supervisor._cgroup_ancestor_headroom_unmeasured(record) is False


def test_phase_reports_actual_sampling_gaps(tmp_path):
    phase = _run_phase(
        tmp_path,
        sample=_Samples(),
        popen_factory=_FakePopen(poll_results=[None, None, 0]),
        clock=_Clock(0.0, 0.1, 0.4, 0.8, 0.8),
    )
    gaps = phase["sampling"]["sample_timestamp_gap_seconds"]
    assert gaps["count"] == 1
    assert gaps["min"] == pytest.approx(0.3)
    assert gaps["max"] == pytest.approx(0.3)
    assert gaps["mean"] == pytest.approx(0.3)


def test_phase_enforces_cumulative_wall_budget_at_phase_boundary(tmp_path):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=lambda _pid: _complete_resource_sample(),
        popen_factory=_FakePopen(poll_results=[None]),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        clock=_Clock(0.0, 2.0, 2.0, 2.0),
        hard_memory_bytes=10**9,
        cumulative_compute_used_seconds=9.0,
        cumulative_compute_limit_seconds=10.0,
    )
    assert phase["termination_reason"] == "cumulative_wall_timeout"
    assert phase["limits"]["cumulative_compute_limit_seconds"] == 10.0
    assert terminated


def test_balh_time_stop_override_skips_only_time_gates(tmp_path):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    timed = _run_phase(
        tmp_path / "timed_phase",
        sample=_Samples(),
        popen_factory=_FakePopen(poll_results=[None]),
        clock=_Clock(0.0, 43201.0),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        timeout_seconds=43200,
        cumulative_compute_used_seconds=0.0,
        cumulative_compute_limit_seconds=172800.0,
    )
    assert timed["termination_reason"] == "wall_timeout"

    cumulative = _run_phase(
        tmp_path / "timed_cumulative",
        sample=_Samples(),
        popen_factory=_FakePopen(poll_results=[None]),
        clock=_Clock(0.0, 2.0),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        timeout_seconds=43200,
        cumulative_compute_used_seconds=172799.0,
        cumulative_compute_limit_seconds=172800.0,
    )
    assert cumulative["termination_reason"] == "cumulative_wall_timeout"

    phase = _run_phase(
        tmp_path / "time_override",
        sample=_Samples(),
        popen_factory=_FakePopen(poll_results=[None, 0]),
        clock=_Clock(0.0, 43201.0),
        hard_memory_bytes=10**9,
        timeout_seconds=43200,
        cumulative_compute_used_seconds=172799.0,
        cumulative_compute_limit_seconds=172800.0,
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        enforce_time_stops=False,
    )
    assert phase["returncode"] == 0
    assert phase["time_stop_enforced"] is False
    assert phase["termination_reason"] is None

    limited = _run_phase(
        tmp_path / "memory_gate",
        sample=lambda _pid: _complete_resource_sample(rss=101),
        popen_factory=_FakePopen(poll_results=[None]),
        terminate=terminate,
        process_group_gone=lambda _pid: True,
        hard_memory_bytes=100,
        timeout_seconds=43200,
        cumulative_compute_used_seconds=172799.0,
        cumulative_compute_limit_seconds=172800.0,
        enforce_time_stops=False,
    )
    assert limited["time_stop_enforced"] is False
    assert limited["termination_reason"] == "absolute_memory_limit"
    assert terminated


@pytest.mark.parametrize(
    ("warning_memory_bytes", "hard_memory_bytes", "timeout_seconds", "reason"),
    [
        (50, 50, 999, "absolute_memory_limit"),
        (1000, 10**9, 0, "wall_timeout"),
    ],
)
def test_phase_accepts_injected_shortwave_runtime_limits(
    tmp_path, warning_memory_bytes, hard_memory_bytes, timeout_seconds, reason
):
    phase = _run_phase(
        tmp_path,
        sample=_Samples(),
        clock=_Clock(0.0),
        warning_memory_bytes=warning_memory_bytes,
        hard_memory_bytes=hard_memory_bytes,
        timeout_seconds=timeout_seconds,
    )
    assert phase["termination_reason"] == reason
    assert phase["warning_reached"] is (warning_memory_bytes <= 100)


def test_phase_uses_phase_elapsed_for_shortwave_wall_timeout(tmp_path):
    phase = _run_phase(
        tmp_path,
        sample=_Samples(),
        clock=_Clock(100.0, 100.5, 100.5),
        workflow_started=0.0,
        warning_memory_bytes=100,
        timeout_seconds=1,
        hard_memory_bytes=10**9,
        phase_elapsed_timeout=True,
    )
    assert phase["returncode"] == 0
    assert phase["termination_reason"] is None
    assert phase["timeout_scope"] == "phase"
    assert phase["phase_wall_seconds"] == 0.5
    assert phase["limits"] == {
        "warning_memory_bytes": 100,
        "hard_memory_bytes": 10**9,
        "swap_limit_bytes": 0,
        "timeout_seconds": 1,
        "min_memavailable_bytes": None,
        "min_cgroup_ancestor_headroom_bytes": None,
        "cumulative_compute_limit_seconds": None,
    }
    finished = json.loads(
        (tmp_path / "numerical_output" / "log" / "memory_stage_markers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[-1]
    )
    assert finished["phase_wall_seconds"] == phase["phase_wall_seconds"]
    assert finished["timeout_scope"] == "phase"
    assert finished["limits"] == phase["limits"]


def test_legacy_phase_timeout_remains_workflow_elapsed(tmp_path):
    phase = _run_phase(
        tmp_path,
        sample=_Samples(),
        clock=_Clock(100.0, 100.5, 100.5),
        workflow_started=0.0,
        timeout_seconds=1,
        hard_memory_bytes=10**9,
    )
    assert phase["termination_reason"] == "wall_timeout"
    assert phase["timeout_scope"] == "workflow"


class _TerminalUnreadableSample:
    def __init__(self):
        self.calls = 0

    def __call__(self, _pid):
        self.calls += 1
        readable = self.calls == 1
        rss = 100 if readable else 0
        return {
            "memory_authority_bytes": rss,
            "job_no_swap": True,
            "process_tree": {
                "rss_bytes": rss,
                "swap_bytes": 0,
                "all_status_readable": readable,
                "smaps": {"pss_bytes": rss, "uss_bytes": rss // 2},
            },
            "job_cgroup": {
                "dedicated_job_cgroup": False,
                "swap_current_bytes": 0,
            },
        }


class _TerminalReadableZeroSample:
    def __init__(self):
        self.calls = 0

    def __call__(self, _pid):
        self.calls += 1
        rss = 100 if self.calls == 1 else 0
        return {
            "memory_authority_bytes": rss,
            "job_no_swap": True,
            "process_tree": {
                "rss_bytes": rss,
                "swap_bytes": 0,
                "all_status_readable": True,
                "smaps": {"pss_bytes": rss, "uss_bytes": rss // 2},
            },
            "job_cgroup": {
                "dedicated_job_cgroup": False,
                "swap_current_bytes": 0,
            },
        }


class _UnreadableThenReadableSample:
    def __init__(self):
        self.calls = 0
        self.readable = _Samples()

    def __call__(self, pid):
        self.calls += 1
        if self.calls == 1:
            return {"process_tree": {"all_status_readable": False}}
        return self.readable(pid)


class _PersistentUnreadableSample:
    def __init__(self):
        self.calls = 0

    def __call__(self, _pid):
        self.calls += 1
        return {"process_tree": {"all_status_readable": False}}


class _CgroupFallbackSample:
    def __init__(
        self,
        *,
        cgroup_memory: int = 500,
        cgroup_swap: int = 0,
        readable_first: bool = True,
        first_rss: int = 100,
    ):
        self.cgroup_memory = cgroup_memory
        self.cgroup_swap = cgroup_swap
        self.readable_first = readable_first
        self.first_rss = first_rss
        self.calls = 0

    def __call__(self, _pid):
        self.calls += 1
        if self.readable_first and self.calls == 1:
            return {
                "memory_authority_bytes": self.first_rss,
                "job_no_swap": True,
                "process_tree": {
                    "rss_bytes": self.first_rss,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                    "smaps": {
                        "pss_bytes": self.first_rss,
                        "uss_bytes": self.first_rss // 2,
                    },
                },
                "job_cgroup": {
                    "dedicated_job_cgroup": True,
                    "readable": True,
                    "memory_current_bytes": self.cgroup_memory,
                    "swap_current_bytes": self.cgroup_swap,
                },
            }
        return {
            "memory_authority_bytes": 1,
            "job_no_swap": False,
            "process_tree": {
                "rss_bytes": 0,
                "swap_bytes": 0,
                "all_status_readable": False,
            },
            "job_cgroup": {
                "dedicated_job_cgroup": True,
                "readable": True,
                "memory_current_bytes": self.cgroup_memory,
                "swap_current_bytes": self.cgroup_swap,
            },
        }


def test_phase_records_one_readable_resample_and_continues(tmp_path):
    samples = _UnreadableThenReadableSample()
    popen = _FakePopen(poll_results=[None, None, None, 0])
    grace_delays = []

    phase = _run_phase(
        tmp_path,
        sample=samples,
        popen_factory=popen,
        sleep=grace_delays.append,
    )

    assert phase["returncode"] == 0
    assert phase["sample_count"] == 1
    assert samples.calls == 2
    assert popen.processes[0].poll_count == 4
    assert phase["peak_memory_authority_bytes"] == 100
    assert phase["rss_drop"]["pass"] is True
    assert phase["termination"] is None
    assert grace_delays.count(supervisor.TASK041_TERMINAL_SAMPLE_GRACE_SECONDS) == 1


def test_phase_rechecks_natural_exit_after_terminal_unreadable_sample(tmp_path):
    samples = _TerminalUnreadableSample()
    popen = _FakePopen(poll_results=[None] * 49 + [0])
    terminated = []
    clock_value = [0.0]
    transition_delays = []

    def clock():
        return clock_value[0]

    def sleep(seconds):
        transition_delays.append(seconds)
        clock_value[0] += seconds

    def terminate(process):
        terminated.append(process.pid)
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=samples,
        terminate=terminate,
        popen_factory=popen,
        clock=clock,
        sleep=sleep,
    )

    assert phase["returncode"] == 0
    assert phase["sample_count"] == 1
    assert samples.calls == 25
    assert phase["peak_memory_authority_bytes"] == 100
    assert phase["rss_drop"] == {
        "before_process_tree_rss_bytes": 100,
        "after_process_tree_rss_bytes": 0,
        "process_group_gone": True,
        "measurement_scope": "legacy_worker_group_process_tree",
        "pass": True,
    }
    assert phase["process_group_gone"] is True
    assert phase["termination"] is None
    assert terminated == []
    assert sum(
        delay
        for delay in transition_delays
        if delay == supervisor.TASK041_TERMINAL_SAMPLE_GRACE_SECONDS
    ) == pytest.approx(6.0)


def test_phase_fails_after_terminal_transition_budget(tmp_path):
    samples = _TerminalUnreadableSample()
    popen = _FakePopen(poll_results=[None] * 260)
    terminated = []
    clock_value = [0.0]
    transition_delays = []

    def clock():
        return clock_value[0]

    def sleep(seconds):
        transition_delays.append(seconds)
        clock_value[0] += seconds

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    gone_states = iter((False, True))
    with pytest.raises(supervisor.Task041SupervisorError) as error:
        _run_phase(
            tmp_path,
            sample=samples,
            terminate=terminate,
            popen_factory=popen,
            clock=clock,
            sleep=sleep,
            process_group_gone=lambda _pid: next(gone_states),
        )

    assert error.value.classification == "task041_resource_sample_failure"
    assert error.value.stage == "producer_resource_sample"
    assert sum(
        delay
        for delay in transition_delays
        if delay == supervisor.TASK041_TERMINAL_SAMPLE_GRACE_SECONDS
    ) == pytest.approx(
        30.0
    )
    assert terminated == [popen.processes[0].pid]


def test_phase_ignores_terminal_readable_zero_for_rss_drop(tmp_path):
    samples = _TerminalReadableZeroSample()
    popen = _FakePopen(poll_results=[None, None, 0])

    phase = _run_phase(
        tmp_path,
        sample=samples,
        popen_factory=popen,
    )

    assert phase["returncode"] == 0
    assert phase["sample_count"] == 2
    assert phase["peak_process_tree_rss_bytes"] == 100
    assert phase["rss_drop"] == {
        "before_process_tree_rss_bytes": 100,
        "after_process_tree_rss_bytes": 0,
        "process_group_gone": True,
        "measurement_scope": "legacy_worker_group_process_tree",
        "pass": True,
    }


def test_phase_accepts_dedicated_cgroup_fallback_during_natural_exit(tmp_path):
    samples = _CgroupFallbackSample(cgroup_memory=500)
    popen = _FakePopen(poll_results=[None, None, 0])

    phase = _run_phase(
        tmp_path,
        sample=samples,
        popen_factory=popen,
    )

    assert phase["returncode"] == 0
    assert phase["sample_count"] == 2
    assert phase["peak_memory_authority_bytes"] == 500
    assert phase["peak_process_tree_rss_bytes"] == 100
    assert phase["rss_drop"] == {
        "before_process_tree_rss_bytes": 100,
        "after_process_tree_rss_bytes": 0,
        "process_group_gone": True,
        "measurement_scope": "legacy_worker_group_process_tree",
        "pass": True,
    }
    records = [
        json.loads(line)
        for line in (
            tmp_path / "numerical_output" / "log" / "memory_stages.jsonl"
        ).read_text().splitlines()
    ]
    assert records[-1]["authority_kind"] == "dedicated_cgroup_fallback"
    assert records[-1]["memory_authority_bytes"] == 500
    assert records[-1]["job_no_swap"] is True
    assert records[-1]["pss_bytes"] is None
    assert records[-1]["uss_bytes"] is None


@pytest.mark.parametrize(
    ("cgroup_memory", "cgroup_swap", "reason"),
    [
        (supervisor.TASK041_HARD_MEMORY_BYTES, 0, "absolute_memory_limit"),
        (1, 1, "swap_detected"),
    ],
)
def test_phase_dedicated_cgroup_fallback_enforces_memory_and_swap(
    tmp_path, cgroup_memory, cgroup_swap, reason
):
    samples = _CgroupFallbackSample(
        cgroup_memory=cgroup_memory,
        cgroup_swap=cgroup_swap,
        readable_first=False,
    )
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=samples,
        popen_factory=_FakePopen(poll_results=[None]),
        terminate=terminate,
    )

    assert phase["termination_reason"] == reason
    assert len(terminated) == 1
    assert phase["peak_memory_authority_bytes"] == cgroup_memory
    assert phase["peak_swap_bytes"] == cgroup_swap


def test_phase_fails_if_unreadable_child_survives_terminal_grace(tmp_path):
    samples = _PersistentUnreadableSample()
    popen = _FakePopen(poll_results=[None, None, None, None])
    terminated = []
    grace_delays = []
    gone_states = iter((False, True))

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    with pytest.raises(supervisor.Task041SupervisorError) as error:
        _run_phase(
            tmp_path,
            sample=samples,
            terminate=terminate,
            popen_factory=popen,
            sleep=grace_delays.append,
            process_group_gone=lambda _pid: next(gone_states),
        )

    assert error.value.classification == "task041_resource_sample_failure"
    assert error.value.stage == "producer_resource_sample"
    assert samples.calls == 2
    assert grace_delays.count(supervisor.TASK041_TERMINAL_SAMPLE_GRACE_SECONDS) == 1
    assert terminated == [popen.processes[0].pid]


@pytest.mark.parametrize(
    ("reason", "memory", "swap", "clock"),
    [
        ("absolute_memory_limit", supervisor.TASK041_HARD_MEMORY_BYTES, True, _Clock(0.0)),
        ("swap_detected", 100, False, _Clock(0.0)),
        ("wall_timeout", 100, True, _Clock(0.0, float(supervisor.TASK041_TIMEOUT_SECONDS))),
    ],
)
def test_phase_resource_limits_terminate_the_child(tmp_path, reason, memory, swap, clock):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=_Samples(memory=memory, swap=swap),
        clock=clock,
        terminate=terminate,
    )
    assert phase["termination_reason"] == reason
    assert len(terminated) == 1


@pytest.mark.parametrize("enforce_time_stops", [True, False])
def test_phase_cgroup_only_swap_is_authoritative(tmp_path, enforce_time_stops):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=_Samples(cgroup_swap=1),
        terminate=terminate,
        enforce_time_stops=enforce_time_stops,
    )
    assert phase["termination_reason"] == "swap_detected"
    assert phase["peak_swap_bytes"] == 1
    assert terminated


@pytest.mark.parametrize(
    ("reason", "classification"),
    [
        ("absolute_memory_limit", "memory_terminate"),
        ("swap_detected", "swap_policy_violation"),
        ("wall_timeout", "timeout"),
    ],
)
def test_phase_resource_classification_is_distinct(reason, classification):
    assert (
        supervisor._phase_resource_classification({"termination_reason": reason})
        == classification
    )


def test_phase_monitor_failure_cleans_up_and_does_not_linger(tmp_path):
    (tmp_path / "numerical_output" / "log").mkdir(parents=True)
    terminated = []
    gone_states = iter((False, True))

    def sample(_pid):
        raise RuntimeError("sample failed")

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    with pytest.raises(RuntimeError, match="^sample failed$") as error:
        supervisor._run_phase(
            "producer",
            ["fake"],
            tmp_path / "producer",
            log_root=tmp_path / "numerical_output" / "log",
            environment={"OMP_NUM_THREADS": "1"},
            repository_root=tmp_path,
            workflow_started=0.0,
            popen_factory=_FakePopen(),
            sample_factory=sample,
            terminate_factory=terminate,
            monotonic=_Clock(0.0),
            sleep=lambda _seconds: None,
            poll_interval=0.01,
            memory_stages_path=tmp_path / "stages.jsonl",
            marker_path=tmp_path / "markers.jsonl",
            process_group_gone=lambda _pid: next(gone_states),
        )
    assert str(error.value) == "sample failed"
    assert terminated


def test_phase_exception_records_cleanup_and_partial_wall_after_spawn(tmp_path):
    (tmp_path / "numerical_output" / "log").mkdir(parents=True)
    partial = {}
    terminated = []
    calls = 0

    def sample(_pid):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Samples()(_pid)
        raise RuntimeError("sample failed after spawn")

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    gone_states = iter((False, True, True))
    with pytest.raises(RuntimeError, match="sample failed after spawn"):
        supervisor._run_phase(
            "producer",
            ["fake"],
            tmp_path / "producer",
            log_root=tmp_path / "numerical_output" / "log",
            environment={"OMP_NUM_THREADS": "1"},
            repository_root=tmp_path,
            workflow_started=0.0,
            popen_factory=_FakePopen(poll_results=[None, None]),
            sample_factory=sample,
            terminate_factory=terminate,
            monotonic=_Clock(0.0, 0.2, 0.5, 0.5, 0.5),
            sleep=lambda _seconds: None,
            poll_interval=0.01,
            memory_stages_path=tmp_path / "stages.jsonl",
            marker_path=tmp_path / "markers.jsonl",
            process_group_gone=lambda _pid: next(gone_states),
            partial_phase_results=partial,
        )
    record = partial["producer"]
    assert terminated
    assert record["cleanup_attempted"] is True
    assert record["process_group_gone"] is True
    assert record["sample_count"] == 1
    assert record["phase_wall_seconds"] == pytest.approx(0.5)
    assert record["partial"] is True


def test_compute_wall_ledger_accumulates_current_phases_without_reuse_reset(
    tmp_path,
):
    ledger_path = tmp_path / "compute_wall_ledger.json"
    initial = {
        "used_compute_wall_seconds": 10.0,
        "used_status": "derived_conservative_allowance",
        "basis": "test ledger",
        "initial_batch_allowance": {"seconds": 6000.0},
        "derived_allowance_margin_seconds": 2008.69,
        "source_records": [{"path": "history", "seconds": 10.0}],
        "measured": {
            "status": "measured",
            "seconds": 2.0,
            "records": [{"path": "earlier", "seconds": 2.0}],
        },
        "derived_upper_bound": {"status": "derived", "seconds": 8.0},
    }
    producer = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=initial,
        current_seconds=4.0,
        run_directory=tmp_path / "producer",
        phase_seconds={"producer": 4.0},
    )
    consumer = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=producer,
        current_seconds=3.0,
        run_directory=tmp_path / "consumer",
        phase_seconds={"consumer": 3.0},
    )
    assert consumer["used_compute_wall_seconds"] == pytest.approx(17.0)
    assert consumer["measured"]["seconds"] == pytest.approx(9.0)
    assert consumer["source_records"][-2]["phase_seconds"] == {"producer": 4.0}
    assert consumer["source_records"][-1]["phase_seconds"] == {"consumer": 3.0}
    assert all(
        "producer" not in record.get("phase_seconds", {})
        for record in consumer["source_records"][-1:]
    )
    assert json.loads(ledger_path.read_text(encoding="utf-8")) == consumer


def test_task041_v2_ledger_keeps_group_buckets_and_history(tmp_path):
    ledger_path = tmp_path / "task041_schur_speed_v2_compute_wall_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task041.compute_wall_ledger.v2",
                "profile_id": "task041_schur_speed_v2",
                "phase_scope": "S0/S1/S3",
                "history": {"previous": "kept"},
                "used_compute_wall_seconds": 3.7,
                "used_status": "measured_scoped_checks",
                "budget_semantics": "shared S0/S1/S3 history",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _, loaded = supervisor._load_task041_compute_wall_ledger(ledger_path)
    shared_first = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=loaded,
        current_seconds=2.0,
        run_directory=tmp_path / "s1",
        phase_seconds={"S1": 2.0},
        limit_seconds=201600.0,
        profile_id="task041_schur_speed_v2",
        phase_group="shared_S0_S1_S3",
    )
    shared_second = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=shared_first,
        current_seconds=4.0,
        run_directory=tmp_path / "s3",
        phase_seconds={"S3": 4.0},
        limit_seconds=201600.0,
        profile_id="task041_schur_speed_v2",
        phase_group="shared_S0_S1_S3",
    )
    final = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=shared_second,
        current_seconds=7.0,
        run_directory=tmp_path / "s4",
        phase_seconds={"S4": 7.0},
        limit_seconds=201600.0,
        profile_id="task041_schur_speed_v2",
        phase_group="S4",
    )
    assert final["schema"] == "task041.compute_wall_ledger.v2"
    assert final["history"] == {"previous": "kept"}
    assert final["phase_scope"] == "S0/S1/S3"
    assert final["shared_S0_S1_S3_used_seconds"] == pytest.approx(9.7)
    assert final["S2_used_seconds"] == pytest.approx(0.0)
    assert final["S4_used_seconds"] == pytest.approx(7.0)
    assert final["batch_used_compute_wall_seconds"] == pytest.approx(16.7)
    assert final["used_compute_wall_seconds"] == pytest.approx(16.7)
    assert final["budget_limit_seconds"] == pytest.approx(201600.0)
    assert final["phase_remaining_seconds"]["S4"] == pytest.approx(172793.0)
    assert [
        record["phase_group"] for record in final["source_records"]
    ] == [
        "shared_S0_S1_S3",
        "shared_S0_S1_S3",
        "S4",
    ]
    mixed_before = dict(final)
    mixed_before["used_status"] = "measured_plus_conservative_upper_bound"
    mixed = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=mixed_before,
        current_seconds=463.599,
        run_directory=tmp_path / "s1a_2b_turn",
        phase_seconds={"s1a_2b_turn": 463.599},
        limit_seconds=201600.0,
        profile_id="task041_schur_speed_v2",
        phase_group="shared_S0_S1_S3",
    )
    assert mixed["used_status"] == "measured_plus_conservative_upper_bound"
    assert mixed["remaining_status"] == (
        "derived_from_measured_and_conservative_upper_bound"
    )
    assert mixed["shared_S0_S1_S3_used_seconds"] == pytest.approx(
        9.7 + 463.599
    )
    assert mixed["source_records"][-1]["seconds"] == pytest.approx(463.599)


def test_task041_terminal_copy_and_streaming_hash_keep_artifact_bytes(tmp_path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "terminal.bin"
    source.write_bytes((bytes(range(256)) * 8193) + b"tail")
    supervisor._copy_file_bounded(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert supervisor._sha256_file(destination) == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


def test_phase_normal_exit_with_lingering_group_is_cleaned_and_fails(tmp_path):
    (tmp_path / "numerical_output" / "log").mkdir(parents=True)
    terminated = []
    gone_states = iter((False, True))

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    with pytest.raises(supervisor.Task041SupervisorError, match="lingered"):
        supervisor._run_phase(
            "producer",
            ["fake"],
            tmp_path / "producer",
            log_root=tmp_path / "numerical_output" / "log",
            environment={"OMP_NUM_THREADS": "1"},
            repository_root=tmp_path,
            workflow_started=0.0,
            popen_factory=_FakePopen(),
            sample_factory=_Samples(),
            terminate_factory=terminate,
            monotonic=_Clock(0.0),
            sleep=lambda _seconds: None,
            poll_interval=0.01,
            memory_stages_path=tmp_path / "stages.jsonl",
            marker_path=tmp_path / "markers.jsonl",
            process_group_gone=lambda _pid: next(gone_states),
        )
    assert terminated


def _public_spec_and_identity():
    spec = SimpleNamespace(
        source_path=Path("input/official/task041/5nm_p6h4_m480_mpi1.dat"),
        input_sha256="i" * 64,
        physical_model_sha256="p" * 64,
    )
    identity = {
        "model_id": TASK041_MODEL_ID,
        "run_id": TASK041_RUN_ID,
        "input_sha256": spec.input_sha256,
        "physical_model_sha256": spec.physical_model_sha256,
        "resolved_config_sha256": "r" * 64,
        "requested_modes": 480,
        "mpi_size": 1,
    }
    return spec, identity


def _install_public_fakes(monkeypatch, spec, identity):
    monkeypatch.setattr(
        supervisor,
        "_outer_mpi_launch_identity",
        lambda: {
            "launcher": "OpenMPI",
            "markers": {
                "OMPI_COMM_WORLD_SIZE": "1",
                "OMPI_COMM_WORLD_RANK": "0",
            },
            "mpi_size": 1,
            "mpi_rank": 0,
            "launched_via_mpiexec": True,
        },
    )
    monkeypatch.setattr(supervisor, "_validate_specification", lambda *_args: identity)
    monkeypatch.setattr(
        supervisor,
        "_git_identity",
        lambda *_args: {
            "head": "a" * 40,
            "branch": supervisor.TASK041_BRANCH,
            "source_sha": "a" * 40,
            "worktree_clean": True,
            "status_scope": "nonignored+untracked",
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_environment_snapshot",
        lambda *_args: {"native_marker": "1", "threads": {"OMP_NUM_THREADS": "1"}},
    )
    monkeypatch.setattr(
        supervisor,
        "_child_environment",
        lambda: {name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
    )
    monkeypatch.setattr(
        supervisor,
        "_task041_builders",
        lambda: {
            "mode_prep": lambda _python, _input, run, source: [
                "mpiexec",
                "--phase",
                "mode-prep",
                "--run-directory",
                str(run),
                source,
            ],
            "consumer": lambda _python, _input, _manifest, _identity, _sha, run, source: [
                "mpiexec",
                "--phase",
                "consumer",
                "--run-directory",
                str(run),
                source,
            ],
        },
    )


def test_shortwave_supervisor_control_plane_dispatches_mpi8_children_sequentially(
    tmp_path, monkeypatch
):
    specification = load_and_resolve(
        ROOT / "input/official/task041/3nm_p6h3_m800_mpi8.dat"
    )
    source_sha = "a" * 40
    (tmp_path / "workflow").mkdir()
    phase_calls = []
    packet_calls = []

    def fake_run_phase(phase, argv, phase_root, **kwargs):
        phase_calls.append({"phase": phase, "argv": list(argv), "limits": kwargs})
        return {
            "phase": phase,
            "argv": list(argv),
            "returncode": 0,
            "termination_reason": None,
            "rss_drop": {"pass": True},
            "process_group_gone": True,
            "peak_memory_authority_bytes": 100,
            "peak_process_tree_rss_bytes": 100,
            "peak_pss_bytes": 100,
            "peak_uss_bytes": 50,
            "peak_process_tree_swap_bytes": 0,
            "peak_dedicated_cgroup_swap_bytes": 0,
            "peak_swap_bytes": 0,
        }

    def fake_validate_packet(producer_root, specification_arg, source, identity):
        packet_calls.append((producer_root, specification_arg, source, identity))
        manifest = producer_root / "selected_mode_packet" / "manifest.json"
        return {
            "summary": {"environment": {}},
            "identity": dict(identity),
            "manifest": str(manifest),
            "manifest_sha256": "b" * 64,
            "manifest_bytes": 0,
            "packet_directory": {"file_count": 0, "bytes": 0},
            "packet_directory_bytes": 0,
            "packet_directory_file_count": 0,
            "compact_manifest": {
                "path": str(manifest),
                "sha256": "b" * 64,
            },
        }

    monkeypatch.setattr(
        supervisor,
        "_outer_mpi_launch_identity",
        lambda: {
            "launcher": "OpenMPI",
            "markers": {
                "OMPI_COMM_WORLD_SIZE": "1",
                "OMPI_COMM_WORLD_RANK": "0",
            },
            "mpi_size": 1,
            "mpi_rank": 0,
            "launched_via_mpiexec": True,
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_git_identity",
        lambda *_args: {
            "head": source_sha,
            "branch": supervisor.TASK041_BRANCH,
            "source_sha": source_sha,
            "worktree_clean": True,
            "status_scope": "nonignored+untracked",
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_environment_snapshot",
        lambda *_args: {"native_marker": "1", "threads": {"OMP_NUM_THREADS": "1"}},
    )
    monkeypatch.setattr(
        supervisor,
        "_child_environment",
        lambda: {name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
    )
    monkeypatch.setattr(supervisor, "_run_phase", fake_run_phase)
    monkeypatch.setattr(supervisor, "_validate_producer_packet", fake_validate_packet)
    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        lambda _root, process_group_gone=None: {
            "complete": True,
            "classification": "worker_exit0",
            "factor_inventory": {"bottom": [], "top": []},
        },
    )

    result = supervisor.run_task041_public_supervisor(
        specification,
        source_sha=source_sha,
        run_directory=tmp_path / "workflow",
        python_executable="/repo/.venv/bin/python",
        monotonic=_Clock(0.0),
    )

    expected_prefix = [
        "mpiexec",
        "-n",
        "8",
        "--bind-to",
        "cpu-list:ordered",
        "--cpu-list",
        "0-7",
        "--report-bindings",
        "/repo/.venv/bin/python",
    ]
    assert [call["phase"] for call in phase_calls] == ["producer", "consumer"]
    assert len(packet_calls) == 1
    expected_phase_limits = {
        phase: dict(supervisor.task041_shortwave_phase_limits(phase))
        for phase in ("producer", "consumer")
    }
    for call in phase_calls:
        assert call["argv"][:9] == expected_prefix
        assert call["argv"][call["argv"].index("--input") + 1] == str(
            specification.source_path
        )
        limits = expected_phase_limits[call["phase"]]
        assert call["limits"]["warning_memory_bytes"] == limits["warning_memory_bytes"]
        assert call["limits"]["hard_memory_bytes"] == limits["hard_memory_bytes"]
        assert call["limits"]["timeout_seconds"] == limits["timeout_seconds"]
        assert call["limits"]["phase_elapsed_timeout"] is True
    assert result["identity"]["requested_modes"] == 800
    assert result["identity"]["mpi_size"] == 8
    assert result["outer_mpi_identity"]["mpi_size"] == 1
    assert result["limits"] == {
        "warning_memory_bytes": supervisor.TASK041_SHORTWAVE_WARNING_MEMORY_BYTES,
        "hard_memory_bytes": supervisor.TASK041_SHORTWAVE_HARD_MEMORY_BYTES,
        "swap_limit_bytes": 0,
        "timeout_seconds": supervisor.TASK041_SHORTWAVE_TIMEOUT_SECONDS,
    }
    assert result["phase_limits"] == expected_phase_limits
    resource_authority = result["resource_authority"]
    assert resource_authority["workflow_limits"] == result["limits"]
    assert resource_authority["phase_limits"] == expected_phase_limits
    resource_summary = json.loads(
        (tmp_path / "workflow" / "resource_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert resource_summary["workflow_limits"] == result["limits"]
    assert resource_summary["phase_limits"] == expected_phase_limits


@pytest.mark.parametrize(
    ("consumer_returncode", "consumer_classification", "expected_classification"),
    [
        (0, "TASK041_CONSUMER_PASS", "worker_exit0"),
        (9, "TASK041_CONSUMER_PASS", "task041_consumer_process_failure"),
        (9, "TASK041_CONSUMER_STAGE_FAILURE", "TASK041_CONSUMER_STAGE_FAILURE"),
    ],
)
def test_public_consumer_exit_and_success_gates(
    tmp_path,
    monkeypatch,
    consumer_returncode,
    consumer_classification,
    expected_classification,
):
    spec, identity = _public_spec_and_identity()
    _install_public_fakes(monkeypatch, spec, identity)
    source_sha = "a" * 40
    (tmp_path / "workflow").mkdir()

    def on_wait(argv):
        phase = argv[argv.index("--phase") + 1]
        phase_root = Path(argv[argv.index("--run-directory") + 1])
        if phase == "mode-prep":
            packet = {
                "source_sha": source_sha,
                "input_sha256": spec.input_sha256,
                "physical_sha256": spec.physical_model_sha256,
                "resolved_sha256": identity["resolved_config_sha256"],
                "model_id": TASK041_MODEL_ID,
                "run_id": TASK041_RUN_ID,
                "mode_count": 480,
                "mpi_size": 1,
            }
            manifest = phase_root / "selected_mode_packet" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('{"fresh":true}\n', encoding="utf-8")
            (phase_root / "packet_identity.json").write_text(
                json.dumps(packet), encoding="utf-8"
            )
            (phase_root / "mode_prep_summary.json").write_text(
                json.dumps(
                    {
                        "source_sha": source_sha,
                        "classification": "TASK041_MODE_PREP_PACKET_READY",
                        "cleanup": {"producer_scope_released": True},
                        "environment": {
                            "petsc_scalar_type": "complex128",
                            "petsc_int_type": "numpy.int32",
                            "packages": {"mpi4py": "/native/mpi4py"},
                        },
                        "packet": {
                            "manifest_sha256": hashlib.sha256(
                                manifest.read_bytes()
                            ).hexdigest()
                        },
                    }
                ),
                encoding="utf-8",
            )
        else:
            phase_root.mkdir(parents=True)
            (phase_root / "consumer_summary.json").write_text(
                json.dumps(
                    {
                        "classification": consumer_classification,
                        "status": "task041_consumer_completed",
                        "gates": {"pass": True},
                        "lifecycle": {
                            "setup_released": True,
                            "rss_drop_pass": True,
                            "rss_marker_emitted": True,
                        },
                        "markers": {
                            "observed": [
                                "outer_ksp_destroyed",
                                "bottom_top_factors_destroyed",
                                "large_matrices_destroyed",
                                "final_cleanup_complete",
                            ]
                        },
                        "factor_inventory": {"bottom": [], "top": []},
                        "official_rta": {"status": "measured", "R": 0.0},
                    }
                ),
                encoding="utf-8",
            )

    popen = _FakePopen(returncodes=[0, consumer_returncode], on_wait=on_wait)
    result = supervisor.run_task041_public_supervisor(
        spec,
        source_sha=source_sha,
        run_directory=tmp_path / "workflow",
        popen_factory=popen,
        sample_factory=_Samples(),
        monotonic=_Clock(0.0),
        sleep=lambda _seconds: None,
        process_group_gone=lambda _pid: True,
    )
    assert result["result_classification"] == expected_classification
    assert len(popen.calls) == 2
    assert result["workflow_peak"]["memory_authority_bytes"] == 100
    assert (tmp_path / "workflow" / "selected_mode_manifest.json").is_file()
    assert (tmp_path / "workflow" / "external_mode_manifest.json").is_file()
    assert (tmp_path / "workflow" / "workflow_summary.json").is_file()
    resource_summary = json.loads(
        (tmp_path / "workflow" / "resource_summary.json").read_text()
    )
    assert resource_summary["workflow_peak"]["pss_bytes"] == 100
    assert resource_summary["workflow_peak"]["uss_bytes"] == 50
    assert resource_summary["total_wall_seconds"] >= 0.0
    assert result["git_before"]["branch"] == supervisor.TASK041_BRANCH
    assert result["outer_mpi_identity"]["launched_via_mpiexec"] is True
    mpi_environment = json.loads(
        (tmp_path / "workflow" / "mpi_environment.json").read_text()
    )
    assert mpi_environment["outer_mpi_identity"]["markers"] == {
        "OMPI_COMM_WORLD_SIZE": "1",
        "OMPI_COMM_WORLD_RANK": "0",
    }
    selected_manifest = json.loads(
        (tmp_path / "workflow" / "selected_mode_manifest.json").read_text()
    )
    assert selected_manifest["path"] == "producer/selected_mode_packet/manifest.json"
    assert selected_manifest["packet_directory"]["file_count"] == 1
    if (
        consumer_returncode != 0
        and consumer_classification != "TASK041_CONSUMER_PASS"
    ):
        assert result["consumer"]["worker_classification"] == consumer_classification
        assert result["consumer"]["classification"] == consumer_classification
    if consumer_returncode == 0:
        assert result["git_after"]["branch"] == supervisor.TASK041_BRANCH
        assert result["environment"]["worker"]["petsc_scalar_type"] == "complex128"
        assert "summary" not in result["consumer"]
        assert result["consumer"]["summary_artifact"]["bytes"] > 0
        assert {
            "outer_ksp_destroyed",
            "bottom_top_factors_destroyed",
            "large_matrices_destroyed",
            "final_cleanup_complete",
        } <= set(result["consumer"]["markers"]["observed"])
        assert result["consumer"]["official_rta"]["status"] == "measured"


def test_public_producer_failure_does_not_start_consumer(tmp_path, monkeypatch):
    spec, identity = _public_spec_and_identity()
    _install_public_fakes(monkeypatch, spec, identity)
    popen = _FakePopen(returncodes=[7])
    (tmp_path / "workflow").mkdir()
    result = supervisor.run_task041_public_supervisor(
        spec,
        source_sha="a" * 40,
        run_directory=tmp_path / "workflow",
        popen_factory=popen,
        sample_factory=_Samples(),
        monotonic=_Clock(0.0),
        sleep=lambda _seconds: None,
        process_group_gone=lambda _pid: True,
    )
    assert result["result_classification"] == "task041_producer_failure"
    assert len(popen.calls) == 1


@pytest.mark.parametrize(
    ("rss_drop_pass", "rss_marker_emitted", "group_gone"),
    [(False, True, True), (True, False, True), (True, True, False)],
)
def test_consumer_lifecycle_gates_are_required(
    tmp_path, rss_drop_pass, rss_marker_emitted, group_gone
):
    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir()
    (consumer_root / "consumer_summary.json").write_text(
        json.dumps(
            {
                "classification": "TASK041_CONSUMER_PASS",
                "status": "task041_consumer_completed",
                "gates": {"pass": True},
                "lifecycle": {
                    "setup_released": True,
                    "rss_drop_pass": rss_drop_pass,
                    "rss_marker_emitted": rss_marker_emitted,
                },
                "markers": {"observed": ["final_cleanup_complete"]},
            }
        ),
        encoding="utf-8",
    )
    status = supervisor._consumer_result(
        consumer_root, process_group_gone=group_gone
    )
    assert status["complete"] is False
    assert status["classification"] == "task041_consumer_lifecycle_failure"


def test_git_identity_requires_task041_branch(monkeypatch, tmp_path):
    outputs = iter(("s" * 40, "wrong-branch", ""))

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(stdout=next(outputs))

    monkeypatch.setattr(supervisor.subprocess, "run", fake_run)
    with pytest.raises(supervisor.Task041SupervisorError, match="branch"):
        supervisor._git_identity(tmp_path, "s" * 40)


def test_git_identity_requires_matching_end_source(monkeypatch, tmp_path):
    outputs = iter(("h" * 40, supervisor.TASK041_BRANCH, ""))

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(stdout=next(outputs))

    monkeypatch.setattr(supervisor.subprocess, "run", fake_run)
    with pytest.raises(supervisor.Task041SupervisorError, match="source SHA"):
        supervisor._git_identity(tmp_path, "s" * 40)


def test_launcher_lazy_dispatch_does_not_build_generic_plan(tmp_path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    fake_spec = SimpleNamespace(
        method={"kind": "hybrid_iterative"},
        identity={"model_id": TASK041_MODEL_ID},
    )
    called = {}
    monkeypatch.setattr(launcher, "_validate_source_sha", lambda value: value)
    monkeypatch.setattr(launcher, "_timestamp_directory", lambda *_args: root)
    monkeypatch.setattr(
        launcher,
        "_write_bootstrap",
        lambda *_args, **_kwargs: ({"run_id": "test", "output_directory": str(root)}, "r" * 64),
    )
    monkeypatch.setattr(
        launcher,
        "build_execution_plan",
        lambda *_args, **_kwargs: pytest.fail("generic plan must not be built"),
    )

    def fake_supervisor(specification, **kwargs):
        called["specification"] = specification
        called["kwargs"] = kwargs
        return {
            "exit_status": 0,
            "result_classification": "worker_exit0",
            "resource_authority": {"status": "measured"},
        }

    monkeypatch.setattr(supervisor, "run_task041_public_supervisor", fake_supervisor)
    result = launcher.launch_specification(fake_spec, source_sha="s" * 40)
    assert called["specification"] is fake_spec
    assert result["result_classification"] == "worker_exit0"
    assert called["kwargs"]["sample_factory"] is not launcher.resource_authority_sample

    def custom_sampler(_pid):
        return {}

    launcher.launch_specification(
        fake_spec,
        source_sha="s" * 40,
        sample_factory=custom_sampler,
    )
    assert called["kwargs"]["sample_factory"] is custom_sampler
