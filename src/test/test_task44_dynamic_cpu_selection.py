from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import scripts.task44_native_service as native_service
from src.runners import task038_launcher


def test_select_idle_cpu_uses_maximum_of_two_samples_and_strict_20_percent(
    monkeypatch,
):
    samples = iter(
        (
            {0: (0, 0), 1: (0, 0), 2: (0, 0)},
            {0: (100, 90), 1: (100, 90), 2: (100, 80)},
            {0: (200, 150), 1: (200, 180), 2: (200, 160)},
        )
    )
    monkeypatch.setattr(native_service, "_host_allowed_cpus", lambda _root: ({0, 1, 2}, "systemd"))
    monkeypatch.setattr(native_service, "_numerical_processes", list)
    monkeypatch.setattr(native_service, "_cpu_counters", lambda _path: next(samples))
    monkeypatch.setattr(native_service.time, "sleep", lambda _seconds: None)

    report = native_service.select_idle_cpu()

    assert report["selected_cpu"] == 1
    assert report["selected_cpu_busy_percent"] == 10.0
    assert report["cpu_busy_percent"] == {"0": 40.0, "1": 10.0, "2": 20.0}
    assert report["busy_percent_limit_strictly_less_than"] == 20.0
    assert report["requested_sample_pause_seconds"] == 0.5
    assert len(report["sample_intervals_seconds"]) == 2
    assert len(report["cpu_counter_samples"]) == 3
    assert report["cpu_counter_samples"][0]["counters"]["0"] == {
        "total_jiffies": 0,
        "idle_and_iowait_jiffies": 0,
    }
    assert all(sample["timestamp_utc"] for sample in report["cpu_counter_samples"])


def test_resource_preflight_uses_formal_budget_in_its_outer_caller(
    monkeypatch,
):
    observed = {}
    monkeypatch.setattr(native_service, "verify_task44_root", lambda *_args: None)
    monkeypatch.setattr(native_service, "_require_task44_cpu", lambda _cpus: None)
    monkeypatch.setattr(
        native_service,
        "_cpu_neighbor_gate",
        lambda **_kwargs: {"status": "pass", "performance_not_isolated": False},
    )

    def admission(cap_bytes, max_concurrent):
        observed.update(
            caller_pid=os.getpid(), cap_bytes=cap_bytes, max_concurrent=max_concurrent
        )
        return {"task_cgroup_available_bytes": 64 * native_service.GIB}

    monkeypatch.setattr(native_service, "_admission_facts", admission)
    caller_pid = os.getpid()

    report = native_service.resource_preflight(
        max_concurrent=1,
        cap_bytes=native_service.INITIAL_CAP_BYTES,
        cpu_affinity={7},
    )

    assert observed == {
        "caller_pid": caller_pid,
        "cap_bytes": native_service.INITIAL_CAP_BYTES,
        "max_concurrent": 1,
    }
    assert report["resources"]["task_cgroup_available_bytes"] == 64 * native_service.GIB
    assert report["service_memory_max_bytes"] == native_service.INITIAL_CAP_BYTES
    assert report["selected_cpu_affinity"] == [7]


def test_filtered_abi_preflight_does_not_run_formal_memory_admission(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(native_service, "verify_task44_root", lambda *_args: None)
    monkeypatch.setattr(native_service, "_require_task44_cpu", lambda _cpus: None)
    monkeypatch.setattr(
        native_service,
        "_verify_filtered_unit",
        lambda *_args, **_kwargs: (
            {"control_group": "/user.slice/task44-preflight-test.service",
             "system_call_filter": "~sched_setaffinity",
             "system_call_error_number": "EPERM"},
            {"status": "pass", "errno": "EPERM"},
        ),
    )
    monkeypatch.setattr(
        native_service,
        "_cpu_neighbor_gate",
        lambda **_kwargs: {"status": "pass", "performance_not_isolated": False},
    )
    monkeypatch.setattr(
        task038_launcher,
        "_environment_identity",
        lambda: {
            "runtime_profile": "native_linux_complex",
            "native_complex_identity": {
                "petsc_scalar_type": "numpy.complex128",
                "mpi_size": 1,
                "task44_runtime_controls": native_service.TASK44_RUNTIME_CONTROLS,
            },
        },
    )
    monkeypatch.setattr(native_service, "_source_facts", lambda _root: {"source_sha": "a" * 40})
    monkeypatch.setattr(native_service, "_input_facts", lambda *_args: {"sha256": "b" * 64})
    monkeypatch.setattr(native_service, "_active_units", list)

    def forbidden_memory_admission(*_args, **_kwargs):
        raise AssertionError("filtered 4 GiB ABI preflight must not evaluate the 128 GiB budget")

    monkeypatch.setattr(native_service, "_admission_facts", forbidden_memory_admission)

    report = native_service.preflight(
        tmp_path / "input.dat", unit="task44-preflight-test.service", cpu_affinity={7}
    )

    assert report["preflight_service_memory_max_bytes"] == native_service.PREFLIGHT_CAP_BYTES
    assert report["selected_cpu_affinity"] == [7]
    assert "resources" not in report


def test_dynamic_selection_excludes_cpu0_while_authorized_supervisor_claims_it(
    monkeypatch,
):
    counters = iter(
        (
            {0: (0, 0), 1: (0, 0)},
            {0: (100, 100), 1: (100, 90)},
            {0: (200, 200), 1: (200, 180)},
        )
    )
    monkeypatch.setattr(native_service, "_host_allowed_cpus", lambda _root: ({0, 1}, "systemd"))
    monkeypatch.setattr(
        native_service,
        "_numerical_processes",
        lambda: [{"pid": 3893658, "cpus_allowed_list": "0"}],
    )
    monkeypatch.setattr(native_service, "_cpu_counters", lambda _path: next(counters))
    monkeypatch.setattr(native_service.time, "sleep", lambda _seconds: None)

    report = native_service.select_idle_cpu()

    assert report["selected_cpu"] == 1
    assert report["blocked_cpus"] == [0]
    assert report["narrow_numerical_affinity_claims"] == [
        {
            "cpu": 0,
            "pid": 3893658,
            "authorized_cpu0_neighbor_identity_candidate": True,
        }
    ]


def test_manifest_identity_records_child_seccomp_test(monkeypatch):
    repo_root = Path(task038_launcher.__file__).resolve().parents[2]
    monkeypatch.setenv("MYFENICS_NATIVE_COMPLEX_ENV", "1")
    monkeypatch.setenv("MYFENICS_TASK44_ROOT", str(repo_root))
    syscall_test = {
        "status": "pass",
        "requested_cpu_affinity": [7],
        "actual_cpu_affinity": [7],
        "denied_syscall": "sched_setaffinity",
        "errno": "EPERM",
    }

    def fake_run(argv, **_kwargs):
        compile(argv[2], "<task44-manifest-environment-probe>", "exec")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "environment": {
                    "qualified_activation": "MYFENICS_NATIVE_COMPLEX_ENV=1",
                    "runtime_profile": "native_linux_complex",
                },
                "sched_setaffinity_filter_test": syscall_test,
            }),
            stderr="",
        )

    monkeypatch.setattr(task038_launcher.subprocess, "run", fake_run)

    identity = task038_launcher._manifest_environment_identity()

    assert identity["task44_sched_setaffinity_filter_test"] == syscall_test
