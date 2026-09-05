"""Focused contracts for the Task041 public MPI1 supervisor boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.task041_exact_side_workflow import task041_inner_mpi_environment
from src.io.execution_plan import (
    TASK041_PUBLIC_SUPERVISOR_ADAPTER,
    method_adapter_identity,
)
from src.io.input_validation import TASK041_MODEL_ID, TASK041_RUN_ID
from src.runners import task038_launcher as launcher
from src.runners import task041_supervisor as supervisor


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
):
    (tmp_path / "numerical_output" / "log").mkdir(parents=True)
    return supervisor._run_phase(
        "producer",
        ["mpiexec", "-n", "1", "fake"],
        tmp_path / "producer",
        log_root=tmp_path / "numerical_output" / "log",
        environment={"OMP_NUM_THREADS": "1"},
        repository_root=tmp_path,
        workflow_started=0.0,
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
    )


def test_task041_adapter_is_exact_and_task039_remains_separate():
    assert (
        method_adapter_identity("hybrid_iterative", TASK041_MODEL_ID)
        == TASK041_PUBLIC_SUPERVISOR_ADAPTER
    )
    assert method_adapter_identity(
        "hybrid_iterative", "task039_5nm_hybrid_iterative_m480_candidate"
    ) == "task039.hybrid_iterative"


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
    popen = _FakePopen(poll_results=[None, None, None, 0])
    terminated = []
    grace_delays = []

    def terminate(process):
        terminated.append(process.pid)
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=samples,
        terminate=terminate,
        popen_factory=popen,
        sleep=grace_delays.append,
    )

    assert phase["returncode"] == 0
    assert phase["sample_count"] == 1
    assert samples.calls == 3
    assert phase["peak_memory_authority_bytes"] == 100
    assert phase["rss_drop"] == {
        "before_process_tree_rss_bytes": 100,
        "after_process_tree_rss_bytes": 0,
        "process_group_gone": True,
        "pass": True,
    }
    assert phase["process_group_gone"] is True
    assert phase["termination"] is None
    assert terminated == []
    assert grace_delays.count(supervisor.TASK041_TERMINAL_SAMPLE_GRACE_SECONDS) == 1


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


def test_phase_cgroup_only_swap_is_authoritative(tmp_path):
    terminated = []

    def terminate(process):
        terminated.append(process.pid)
        process.terminated = True
        return {"requested": True}

    phase = _run_phase(
        tmp_path,
        sample=_Samples(cgroup_swap=1),
        terminate=terminate,
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
