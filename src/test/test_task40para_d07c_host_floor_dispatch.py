"""Prove D07C enters Task40 host-floor admission and retains its default deny."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.io.native_capacity_profile import (
    TASK40_PHI90_D07C_PROFILE_BY_CASE,
    native_profile_facts,
)
from src.runners import native_capacity
from src.runners import reviewed_workstation_admission as admission


def _write_solver(proc_root: Path, pid: int, argv: list[str]) -> None:
    process = proc_root / str(pid)
    process.mkdir(parents=True)
    fields = ["0"] * 37
    fields[0] = "S"
    fields[1] = "1"
    fields[19] = str(pid * 10)
    (process / "stat").write_text(f"{pid} (python) " + " ".join(fields) + "\n")
    (process / "status").write_text(
        "Name:\tpython\nVmRSS:\t1024 kB\nThreads:\t1\n"
        "Cpus_allowed_list:\t0-47\nMems_allowed_list:\t0-1\n"
    )
    (process / "cmdline").write_bytes(
        b"\0".join(token.encode() for token in argv) + b"\0"
    )
    cwd = process.parent / f"cwd-{pid}"
    cwd.mkdir()
    (process / "cwd").symlink_to(cwd)


@pytest.mark.parametrize(
    ("argv_rows", "message"),
    [
        (
            [["/shared/bin/python", "/work/scripts/run_case.py", "case.dat"]],
            "another active run_case/native solver process",
        ),
        (
            [["/shared/bin/python", "-m", "src.runners.task038_future_worker"]],
            "unknown role",
        ),
        (
            [
                ["/shared/bin/python", "/work/scripts/run_case.py", "one.dat"],
                ["/shared/bin/python", "/work/scripts/run_case.py", "two.dat"],
            ],
            "another active run_case/native solver process",
        ),
    ],
    ids=("active-solver", "unknown-solver", "duplicate-solver-trees"),
)
def test_host_floor_admission_default_rejects_solver_candidates(
    tmp_path, monkeypatch, argv_rows, message
):
    proc_root = tmp_path / "proc"
    sys_root = tmp_path / "sys"
    proc_root.mkdir()
    (proc_root / "self").mkdir()
    (proc_root / "self/status").write_text(
        "Mems_allowed_list:\t0-1\nCpus_allowed_list:\t0-47\n"
    )
    cgroup = sys_root / "fs/cgroup/task40"
    cgroup.mkdir(parents=True)
    (cgroup / "cpuset.cpus.effective").write_text("0-47\n")
    topology = sys_root / "devices/system/cpu/cpu24/topology"
    topology.mkdir(parents=True)
    (topology / "physical_package_id").write_text("0\n")
    (topology / "core_id").write_text("24\n")

    for index, argv in enumerate(argv_rows, start=50001):
        _write_solver(proc_root, index, argv)

    monkeypatch.setattr(admission, "_proc_root", lambda: proc_root)
    monkeypatch.setattr(admission, "_sys_root", lambda: sys_root)
    monkeypatch.setattr(admission, "_interleave_probe", lambda: pytest.fail("gate must reject first"))
    import benchmarks.subreaper_watchdog as watchdog
    import benchmarks.task034_wsl_resources as resources

    monkeypatch.setattr(watchdog, "memory_envelope", lambda: {
        "effective_available_bytes": 2 * 1024**4,
        "effective_total_bytes": 2 * 1024**4,
    })
    monkeypatch.setattr(resources, "current_cgroup_path", lambda: cgroup)

    d07c = native_profile_facts(TASK40_PHI90_D07C_PROFILE_BY_CASE["B"])
    assert d07c["resources"]["resource_stop_policy"] == "host_available_floor_v1"
    assert d07c["resources"]["rss_hard_limit_bytes"] is None
    with pytest.raises(admission.InputError, match=message):
        admission.task40_host_floor_interleaved_admission(
            d07c["resources"], [24],
            task_profile=TASK40_PHI90_D07C_PROFILE_BY_CASE["B"],
            task_run_id="task40_phi90_0p7_D07C_B_p6_direct_v1",
        )


def test_native_capacity_guard_dispatches_locked_d07c_to_host_floor_by_default(
    tmp_path, monkeypatch
):
    from src.io import execution_plan

    profile = TASK40_PHI90_D07C_PROFILE_BY_CASE["B"]
    lock = tmp_path / "canonical-heavy.lock"
    common_repo = tmp_path / "task-repository.git"
    common_repo.mkdir()
    calls = []
    monkeypatch.setenv("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setenv("PHYSICAL_NATIVE_CAPACITY", "test-original-profile")
    monkeypatch.delenv("TASK40_PARALLEL_AUTHORIZATION_FILE", raising=False)
    monkeypatch.delenv("TASK40_PARALLEL_AUTHORIZATION_SHA256", raising=False)
    monkeypatch.setattr(
        native_capacity, "_native_capacity_host_lock",
        lambda _root, _profile: (lock, common_repo),
    )
    monkeypatch.setattr(native_capacity.os, "sched_setaffinity", lambda *_args: None)
    monkeypatch.setattr(execution_plan, "native_memory_policy_prefix", lambda _policy: [])
    monkeypatch.setattr(native_capacity, "_launch_swap_snapshot", dict)
    monkeypatch.setattr(
        native_capacity, "_validate_preexisting_swap",
        lambda _snapshot, *, observe_only: "observe-only baseline",
    )
    monkeypatch.setattr(native_capacity, "_cpu_launch_snapshot", lambda _cpus: {"captured": True})

    def host_floor(resources, worker_cpus, **kwargs):
        calls.append((resources, tuple(worker_cpus), kwargs))
        return {
            "policy": "interleave_nodes0_1",
            "resource_stop_policy": resources["resource_stop_policy"],
            "user_parallel_window_authorization": False,
        }

    def legacy(*_args, **_kwargs):
        pytest.fail("D07C must not enter legacy interleaved_admission")

    monkeypatch.setattr(admission, "task40_host_floor_interleaved_admission", host_floor)
    monkeypatch.setattr(admission, "interleaved_admission", legacy)

    with native_capacity.native_capacity_guard(
        profile, memory_policy="interleave_nodes0_1",
        task_run_id="task40_phi90_0p7_D07C_B_p6_direct_v1",
    ) as (_root, isolation):
        assert isolation["native_capacity_heavy_lock"] == str(lock.resolve())
        assert isolation["profile_concurrent_neighbor_authorized"] is False

    assert len(calls) == 1
    resources, cpus, kwargs = calls[0]
    assert resources["resource_stop_policy"] == "host_available_floor_v1"
    assert resources["minimum_available_bytes"] == 64 * 1024**3
    assert resources["rss_hard_limit_bytes"] is None
    assert cpus == (24,)
    assert kwargs["parallel_authority_path"] is None
    assert kwargs["parallel_authority_sha256"] is None
    assert kwargs["task_profile"] == profile
