"""Pure Task42 resource-gate contracts; no launcher or PDE is started."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks import task034_wsl_resources as resource_sampler
from benchmarks.task034_wsl_resources import ProcessTreeSample
from src.io import load_and_resolve
from src.io.input_validation import (
    TASK041_BALH_CELL_CONDENSED_RESERVE_BYTES,
    TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES,
    TASK041_BALH_W0P7NM_P6_PILOT_POLICY_RESERVE_BYTES,
    TASK42_MEMORY_RESERVE_BYTES,
    TASK42_SOFT_TARGET_SECONDS,
    TASK42_STARTUP_PREDICTED_DELTA_BYTES,
    TASK42_WORKSPACE_MIN_BYTES,
    task041_v16_phase_memory_gate,
    task42_memory_authority_inputs,
    task42_memory_parameters,
    task42_phase_memory_gate,
    task42_runtime_memory_gate_from_authority,
    task42_startup_memory_budget,
)
from src.runners.task038_input_worker import _task42_stage_gate_callback
from src.runners.task038_launcher import (
    _append_task42_phase_record,
    launch_specification,
)

ROOT = Path(__file__).resolve().parents[2]
TASK42_DIRECT_INPUT = ROOT / (
    "input/official/task42hybrid_az90_50x50_17x20_0p7nm/"
    "13p5nm_p6h10_full3d_direct_mpi8.dat"
)


def test_task42_authority_accepts_real_process_tree_tuple_and_json_list():
    root_pid = 42100
    authority = _task42_authority(
        root_pid=root_pid,
        tree_rss_bytes=1024,
        memavailable_bytes=512 * 2**30,
    )
    process_tree = ProcessTreeSample(
        root_pid=root_pid,
        pids=(root_pid, root_pid + 1),
        rss_bytes=1024,
        swap_bytes=0,
        all_status_readable=True,
        rss_by_pid_bytes={root_pid: 512, root_pid + 1: 512},
        swap_by_pid_bytes={root_pid: 0, root_pid + 1: 0},
    )
    authority["process_tree"] = process_tree.to_dict()

    tuple_result = task42_memory_authority_inputs(
        authority, expected_root_pid=root_pid
    )
    assert tuple_result["status"] == "measured"
    assert tuple_result["process_tree_pids"] == [root_pid, root_pid + 1]
    assert tuple_result["tree_rss_scope"] == "whole_job"

    list_authority = {
        **authority,
        "process_tree": {
            **process_tree.to_dict(),
            "pids": [root_pid, root_pid + 1],
        },
    }
    list_result = task42_memory_authority_inputs(
        list_authority, expected_root_pid=root_pid
    )
    assert list_result["status"] == "measured"
    assert list_result["process_tree_pids"] == tuple_result["process_tree_pids"]
    assert list_result["tree_rss_bytes"] == tuple_result["tree_rss_bytes"]

    missing_root_authority = {
        **authority,
        "process_tree": {**process_tree.to_dict(), "pids": (root_pid + 1,)},
    }
    missing_root = task42_memory_authority_inputs(
        missing_root_authority, expected_root_pid=root_pid
    )
    assert missing_root["status"] == "refused"
    assert "whole_job_process_tree_is_incomplete_or_unreadable" in missing_root[
        "errors"
    ]

    invalid_pid_authority = {
        **authority,
        "process_tree": {
            **process_tree.to_dict(),
            "pids": (root_pid, "not-a-pid"),
        },
    }
    invalid_pid = task42_memory_authority_inputs(
        invalid_pid_authority, expected_root_pid=root_pid
    )
    assert invalid_pid["status"] == "refused"
    assert "whole_job_process_tree_is_incomplete_or_unreadable" in invalid_pid[
        "errors"
    ]

    invalid_value_authority = {
        **authority,
        "process_tree": {
            **process_tree.to_dict(),
            "pids": (root_pid, 0),
        },
    }
    invalid_value = task42_memory_authority_inputs(
        invalid_value_authority, expected_root_pid=root_pid
    )
    assert invalid_value["status"] == "refused"
    assert "whole_job_process_tree_is_incomplete_or_unreadable" in invalid_value[
        "errors"
    ]

    unreadable_authority = {
        **authority,
        "process_tree": {
            **process_tree.to_dict(),
            "all_status_readable": False,
        },
    }
    unreadable = task42_memory_authority_inputs(
        unreadable_authority, expected_root_pid=root_pid
    )
    assert unreadable["status"] == "refused"
    assert "whole_job_process_tree_is_incomplete_or_unreadable" in unreadable[
        "errors"
    ]


def _proc_stat_fixture(pid: int, ppid: int, state: str, start_ticks: int) -> str:
    tail = [state, str(ppid), *(["0"] * 17), str(start_ticks)]
    return f"{pid} (short-lived ) helper) {' '.join(tail)}\n"


def _proc_status_fixture(
    pid: int,
    ppid: int,
    *,
    state: str = "R",
    rss_kib: int | None = 128,
    swap_kib: int | None = 0,
) -> str:
    rows = [
        "Name:\tfixture",
        f"State:\t{state} (running)",
        f"Pid:\t{pid}",
        f"PPid:\t{ppid}",
    ]
    if rss_kib is not None:
        rows.append(f"VmRSS:\t{rss_kib} kB")
    if swap_kib is not None:
        rows.append(f"VmSwap:\t{swap_kib} kB")
    return "\n".join(rows) + "\n"


def _write_proc_fixture(proc_root: Path, *, terminal_root: bool = False) -> tuple[int, int]:
    root_pid, child_pid = 71001, 71002
    root_dir = proc_root / str(root_pid)
    child_dir = proc_root / str(child_pid)
    root_dir.mkdir(parents=True)
    child_dir.mkdir()
    root_state = "Z" if terminal_root else "S"
    (root_dir / "stat").write_text(
        _proc_stat_fixture(root_pid, 1, root_state, 1001), encoding="utf-8"
    )
    (root_dir / "status").write_text(
        _proc_status_fixture(
            root_pid,
            1,
            state=root_state,
            rss_kib=None if terminal_root else 1024,
            swap_kib=None if terminal_root else 0,
        ),
        encoding="utf-8",
    )
    (child_dir / "stat").write_text(
        _proc_stat_fixture(child_pid, root_pid, "R", 1002), encoding="utf-8"
    )
    (child_dir / "status").write_text(
        _proc_status_fixture(child_pid, root_pid, rss_kib=None), encoding="utf-8"
    )
    return root_pid, child_pid


def test_process_tree_sample_bounded_reread_requires_same_pid_start_ticks(
    tmp_path, monkeypatch
):
    root_pid, child_pid = _write_proc_fixture(tmp_path)
    read_status = resource_sampler._read_proc_status_fields
    read_stat = resource_sampler._read_proc_stat_identity
    status_calls = 0

    def status_reader(path):
        nonlocal status_calls
        if path.parent.name == str(child_pid):
            status_calls += 1
            if status_calls == 1:
                return {
                    "Pid": str(child_pid),
                    "PPid": str(root_pid),
                    "State": "R (running)",
                    "VmSwap": "0 kB",
                }, None
            return {
                "Pid": str(child_pid),
                "PPid": str(root_pid),
                "State": "R (running)",
                "VmRSS": "64 kB",
                "VmSwap": "0 kB",
            }, None
        return read_status(path)

    monkeypatch.setattr(resource_sampler, "_read_proc_status_fields", status_reader)
    sample = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    payload = sample.to_dict()

    assert sample.all_status_readable is True
    assert sample.rss_by_pid_bytes[child_pid] == 64 * 1024
    detail = payload["read_diagnostics_by_pid"][child_pid]
    assert detail["first_read"]["state_raw"] == "R (running)"
    assert detail["first_identity"]["start_ticks"] == 1002
    assert detail["reread"]["status"]["vmrss_raw"] == "64 kB"
    assert detail["resolution"] == "measured_after_same_pid_start_ticks_reread"
    assert detail["sample_usable"] is True
    assert status_calls == 2

    status_calls = 0

    def missing_then_complete_status(path):
        nonlocal status_calls
        if path.parent.name == str(child_pid):
            status_calls += 1
            return (
                {
                    "Pid": str(child_pid),
                    "PPid": str(root_pid),
                    "State": "R (running)",
                    "VmSwap": "0 kB",
                },
                None,
            )
        return read_status(path)

    def process_exits_on_reread(path, *, expected_pid):
        if expected_pid == child_pid:
            nonlocal_stat_calls = process_exits_on_reread.calls
            process_exits_on_reread.calls += 1
            if nonlocal_stat_calls == 1:
                return None, "not_present"
        return read_stat(path, expected_pid=expected_pid)

    process_exits_on_reread.calls = 0
    monkeypatch.setattr(
        resource_sampler, "_read_proc_status_fields", missing_then_complete_status
    )
    monkeypatch.setattr(
        resource_sampler, "_read_proc_stat_identity", process_exits_on_reread
    )
    terminated = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    terminal_detail = terminated.to_dict()["read_diagnostics_by_pid"][child_pid]
    assert terminated.all_status_readable is True
    assert terminated.rss_by_pid_bytes[child_pid] == 0
    assert terminal_detail["first_identity"]["start_ticks"] == 1002
    assert terminal_detail["resolution"] == (
        "confirmed_initial_pid_start_ticks_no_longer_present"
    )
    terminal_authority = _task42_authority(
        root_pid=root_pid,
        tree_rss_bytes=terminated.rss_bytes,
        memavailable_bytes=512 * 2**30,
    )
    terminal_authority["process_tree"] = terminated.to_dict()
    terminal_gate = task42_runtime_memory_gate_from_authority(
        terminal_authority, expected_root_pid=root_pid
    )
    assert terminal_gate["pass"] is True
    assert terminal_gate["resident_J_bytes"] == terminated.rss_bytes


def test_process_tree_sample_keeps_unresolved_and_reused_pid_unknown(
    tmp_path, monkeypatch
):
    root_pid, child_pid = _write_proc_fixture(tmp_path)
    read_status = resource_sampler._read_proc_status_fields
    read_stat = resource_sampler._read_proc_stat_identity

    def incomplete_status(path):
        if path.parent.name == str(child_pid):
            return {
                "Pid": str(child_pid),
                "PPid": str(root_pid),
                "State": "R (running)",
                "VmSwap": "0 kB",
            }, None
        return read_status(path)

    monkeypatch.setattr(resource_sampler, "_read_proc_status_fields", incomplete_status)
    unresolved = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    detail = unresolved.to_dict()["read_diagnostics_by_pid"][child_pid]
    assert unresolved.all_status_readable is False
    assert unresolved.rss_by_pid_bytes[child_pid] is None
    assert detail["resolution"] == "refused_same_identity_status_still_incomplete"
    assert detail["first_identity"]["start_ticks"] == 1002
    assert detail["first_read"]["state_raw"] == "R (running)"

    authority = _task42_authority(
        root_pid=root_pid,
        tree_rss_bytes=unresolved.rss_bytes,
        memavailable_bytes=512 * 2**30,
    )
    authority["process_tree"] = unresolved.to_dict()
    extracted = task42_memory_authority_inputs(
        authority, expected_root_pid=root_pid
    )
    assert extracted["status"] == "refused"
    assert extracted["tree_rss_scope"] == "unknown"
    unresolved_gate = task42_runtime_memory_gate_from_authority(
        authority, expected_root_pid=root_pid
    )
    assert unresolved_gate["pass"] is False
    assert "runtime_whole_job_J_is_unknown" in unresolved_gate["errors"]
    assert "runtime_whole_job_J_exceeds_Task42_C" not in unresolved_gate["errors"]

    def reused_pid_identity(path, *, expected_pid):
        identity, error = read_stat(path, expected_pid=expected_pid)
        if expected_pid == child_pid and reused_pid_identity.calls == 1:
            reused_pid_identity.calls += 1
            return {**identity, "start_ticks": 9999}, None
        if expected_pid == child_pid:
            reused_pid_identity.calls += 1
        return identity, error

    reused_pid_identity.calls = 0
    monkeypatch.setattr(
        resource_sampler, "_read_proc_stat_identity", reused_pid_identity
    )
    reused = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    reused_detail = reused.to_dict()["read_diagnostics_by_pid"][child_pid]
    assert reused.all_status_readable is False
    assert reused.rss_by_pid_bytes[child_pid] is None
    assert reused_detail["resolution"] == "refused_pid_start_ticks_changed"
    reused_authority = _task42_authority(
        root_pid=root_pid,
        tree_rss_bytes=reused.rss_bytes,
        memavailable_bytes=512 * 2**30,
    )
    reused_authority["process_tree"] = reused.to_dict()
    reused_gate = task42_runtime_memory_gate_from_authority(
        reused_authority, expected_root_pid=root_pid
    )
    assert reused_gate["pass"] is False
    assert "runtime_whole_job_J_is_unknown" in reused_gate["errors"]
    assert "runtime_whole_job_J_exceeds_Task42_C" not in reused_gate["errors"]


def test_process_tree_sample_rejects_refused_postread_identity_with_full_values(
    tmp_path, monkeypatch
):
    root_pid, child_pid = _write_proc_fixture(tmp_path)
    read_status = resource_sampler._read_proc_status_fields
    read_stat = resource_sampler._read_proc_stat_identity
    child_status_calls = 0
    child_stat_calls = 0

    def status_reader(path):
        nonlocal child_status_calls
        if path.parent.name != str(child_pid):
            return read_status(path)
        child_status_calls += 1
        if child_status_calls == 1:
            return {
                "Pid": str(child_pid),
                "PPid": str(root_pid),
                "State": "R (running)",
                "VmSwap": "0 kB",
            }, None
        return {
            "Pid": str(child_pid),
            "PPid": str(root_pid),
            "State": "R (running)",
            "VmRSS": "64 kB",
            "VmSwap": "2 kB",
        }, None

    def stat_reader(path, *, expected_pid):
        nonlocal child_stat_calls
        if expected_pid == child_pid:
            child_stat_calls += 1
            if child_stat_calls == 3:
                return None, "unreadable:PermissionError"
        return read_stat(path, expected_pid=expected_pid)

    monkeypatch.setattr(resource_sampler, "_read_proc_status_fields", status_reader)
    monkeypatch.setattr(resource_sampler, "_read_proc_stat_identity", stat_reader)
    sample = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    payload = sample.to_dict()
    detail = payload["read_diagnostics_by_pid"][child_pid]

    assert child_status_calls == 2
    assert child_stat_calls == 3
    assert detail["resolution"] == "refused_postread_identity_unavailable"
    assert detail["sample_usable"] is False
    assert detail["bounded_reread_count"] == 1
    assert detail["reread"]["status"]["vmrss_raw"] == "64 kB"
    assert detail["reread"]["status"]["vmswap_raw"] == "2 kB"
    # The row keeps only its first, incomplete observation. The complete later
    # values are retained for diagnosis and are not presented as a coherent row.
    assert sample.rss_by_pid_bytes[child_pid] is None
    assert sample.swap_by_pid_bytes[child_pid] == 0
    assert sample.all_status_readable is False

    authority = _task42_authority(
        root_pid=root_pid,
        tree_rss_bytes=sample.rss_bytes,
        memavailable_bytes=512 * 2**30,
    )
    authority["process_tree"] = payload
    extracted = task42_memory_authority_inputs(
        authority, expected_root_pid=root_pid
    )
    assert extracted["status"] == "refused"
    assert "whole_job_process_tree_is_incomplete_or_unreadable" in extracted[
        "errors"
    ]


def test_process_tree_sample_rejects_root_without_verified_identity(
    tmp_path, monkeypatch
):
    root_pid, _child_pid = _write_proc_fixture(tmp_path)
    read_stat = resource_sampler._read_proc_stat_identity

    def root_identity_unavailable(path, *, expected_pid):
        if expected_pid == root_pid:
            return None, "unreadable:PermissionError"
        return read_stat(path, expected_pid=expected_pid)

    monkeypatch.setattr(
        resource_sampler, "_read_proc_stat_identity", root_identity_unavailable
    )
    sample = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    payload = sample.to_dict()
    root_detail = payload["read_diagnostics_by_pid"][root_pid]

    assert sample.pids[0] == root_pid
    assert sample.rss_by_pid_bytes[root_pid] == 1024 * 1024
    assert root_detail["resolution"] == "refused_initial_start_ticks_unavailable"
    assert root_detail["first_identity_error"] == "unreadable:PermissionError"
    assert root_detail["bounded_reread_count"] == 0
    assert sample.all_status_readable is False


def test_process_tree_sample_does_not_accept_terminal_root(tmp_path):
    root_pid, _child_pid = _write_proc_fixture(tmp_path, terminal_root=True)
    sample = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)

    assert sample.rss_by_pid_bytes[root_pid] == 0
    assert sample.all_status_readable is False

    missing_root = resource_sampler.process_tree_sample(root_pid + 100, proc_root=tmp_path)
    assert missing_root.pids == ()
    assert missing_root.rss_by_pid_bytes == {}
    assert missing_root.all_status_readable is False


def test_process_tree_sample_does_not_accept_root_exit_as_zero(tmp_path, monkeypatch):
    root_pid, child_pid = _write_proc_fixture(tmp_path)
    read_stat = resource_sampler._read_proc_stat_identity
    root_stat_calls = 0

    def status_reader(path):
        if path.parent.name == str(root_pid):
            return {
                "Pid": str(root_pid),
                "PPid": "1",
                "State": "S (sleeping)",
                "VmSwap": "0 kB",
            }, None
        return {
            "Pid": str(child_pid),
            "PPid": str(root_pid),
            "State": "R (running)",
            "VmRSS": "64 kB",
            "VmSwap": "0 kB",
        }, None

    def stat_reader(path, *, expected_pid):
        nonlocal root_stat_calls
        if expected_pid == root_pid:
            root_stat_calls += 1
            if root_stat_calls == 2:
                return None, "not_present"
        return read_stat(path, expected_pid=expected_pid)

    monkeypatch.setattr(resource_sampler, "_read_proc_status_fields", status_reader)
    monkeypatch.setattr(resource_sampler, "_read_proc_stat_identity", stat_reader)
    sample = resource_sampler.process_tree_sample(root_pid, proc_root=tmp_path)
    root_detail = sample.to_dict()["read_diagnostics_by_pid"][root_pid]

    assert root_detail["resolution"] == (
        "confirmed_initial_pid_start_ticks_no_longer_present"
    )
    assert sample.rss_by_pid_bytes[root_pid] == 0
    assert sample.all_status_readable is False


def test_process_tree_sample_reads_a_real_short_lived_process():
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdin.readline()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert child.stdin is not None
        sample = resource_sampler.process_tree_sample(child.pid)
        assert sample.pids == (child.pid,)
        assert sample.all_status_readable is True
        assert sample.rss_by_pid_bytes[child.pid] is not None
        assert sample.rss_by_pid_bytes[child.pid] > 0
        assert set(sample.to_dict()) == {
            "root_pid",
            "pids",
            "rss_bytes",
            "swap_bytes",
            "all_status_readable",
            "rss_by_pid_bytes",
            "swap_by_pid_bytes",
        }
    finally:
        if child.stdin is not None:
            child.stdin.write("exit\n")
            child.stdin.close()
        child.wait()


def _authority(
    *,
    root_pid: int,
    tree_rss_bytes: int,
    memavailable_bytes: int,
    mem_total_bytes: int,
    ancestor_headroom_bytes: int,
) -> dict[str, object]:
    return {
        "process_tree": {
            "root_pid": root_pid,
            "pids": [root_pid, root_pid + 1],
            "all_status_readable": True,
            "rss_bytes": tree_rss_bytes,
        },
        "job_cgroup": {
            "readable": True,
            "dedicated_job_cgroup": False,
            "scope_semantics": "shared_cgroup_diagnostic_only",
            "memory_current_bytes": None,
            "ancestor_hard_limit_state": "finite",
            "ancestor_memory": [
                {
                    "memory_limit_state": "finite",
                    "memory_current_bytes": 1,
                    "memory_limit_bytes": 1 + ancestor_headroom_bytes,
                    "memory_headroom_bytes": ancestor_headroom_bytes,
                }
            ],
        },
        "host_memory": {
            "mem_total_bytes": mem_total_bytes,
            "kernel_memavailable": {
                "status": "measured",
                "bytes": memavailable_bytes,
            },
        },
    }


def _task42_authority(
    *,
    root_pid: int,
    tree_rss_bytes: int,
    memavailable_bytes: int,
    mem_total_bytes: int = 1024 * 2**30,
    ancestor_headroom_bytes: int = 128 * 2**30,
) -> dict[str, object]:
    return {
        "memory_authority_bytes": tree_rss_bytes,
        "process_tree": {
            "root_pid": root_pid,
            "pids": [root_pid, root_pid + 1],
            "all_status_readable": True,
            "rss_bytes": tree_rss_bytes,
            "swap_bytes": 0,
        },
        "job_cgroup": {
            "readable": True,
            "dedicated_job_cgroup": False,
            "scope_semantics": "shared_cgroup_diagnostic_only",
            "memory_current_bytes": None,
            "swap_current_bytes": None,
            "ancestor_hard_limit_state": "finite",
            "ancestor_memory": [
                {
                    "memory_limit_state": "finite",
                    "memory_current_bytes": 1,
                    "memory_limit_bytes": 1 + ancestor_headroom_bytes,
                    "memory_headroom_bytes": ancestor_headroom_bytes,
                }
            ],
        },
        "host_memory": {
            "mem_total_bytes": mem_total_bytes,
            "kernel_memavailable": {
                "status": "measured",
                "bytes": memavailable_bytes,
            },
        },
    }


class _Task42FakeProcess:
    def __init__(self, *, polls_before_exit: int = 1):
        self.pid = 424242
        self.returncode = None
        self._polls_before_exit = polls_before_exit
        self._poll_count = 0

    def poll(self):
        self._poll_count += 1
        if self.returncode is None and self._poll_count > self._polls_before_exit:
            self.returncode = 0
        return self.returncode

    def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def _task42_launch(
    tmp_path,
    *,
    samples,
    process=None,
    monotonic=None,
    sleep=None,
):
    specification = replace(
        load_and_resolve(TASK42_DIRECT_INPUT),
        expected_output_parent=tmp_path / "results",
    )
    calls = {"popen": [], "sampled_roots": [], "terminated": []}
    process = process or _Task42FakeProcess()

    def popen(argv, **kwargs):
        calls["popen"].append((argv, kwargs))
        return process

    def sample(root_pid):
        calls["sampled_roots"].append(root_pid)
        sample_value = samples(root_pid) if callable(samples) else samples.pop(0)
        return sample_value(root_pid) if callable(sample_value) else sample_value

    def terminate(member):
        calls["terminated"].append(member.pid)
        member.returncode = -9
        return {"requested": True, "pid": member.pid}

    result = launch_specification(
        specification,
        source_sha="a" * 40,
        timestamp="20261016Ttask42-resource-contractZ",
        python_executable="/native/python",
        mpiexec_command="/native/mpiexec",
        popen_factory=popen,
        sample_factory=sample,
        terminate_factory=terminate,
        monotonic=monotonic or (lambda: 0.0),
        sleep=sleep or (lambda _seconds: None),
        poll_interval=0.1,
    )
    return result, calls


def test_task42_runtime_does_not_reserve_phase_workspace_permanently():
    mem_total = 2 * 1024**4
    parameters = task42_memory_parameters(mem_total)
    cap = parameters["cap_C_bytes"]
    workspace = parameters["workspace_W_bytes"]
    assert type(cap) is int and type(workspace) is int
    assert TASK42_WORKSPACE_MIN_BYTES <= workspace < cap

    # J is in (C-W, C). Runtime hard limits permit it with host reserve and
    # nonnegative ancestor headroom, while a new phase still reserves W.
    resident = cap - workspace // 2
    authority = _authority(
        root_pid=42000,
        tree_rss_bytes=resident,
        memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
        mem_total_bytes=mem_total,
        ancestor_headroom_bytes=workspace - 1,
    )
    runtime = task42_runtime_memory_gate_from_authority(
        authority, expected_root_pid=42000
    )
    assert runtime["pass"] is True
    assert runtime["workspace_W_applied"] is False
    assert runtime["phase_Delta_applied"] is False
    assert runtime["resident_J_bytes"] == resident
    assert runtime["cap_C_bytes"] == cap
    assert runtime["required_MemAvailable_bytes"] == TASK42_MEMORY_RESERVE_BYTES
    assert runtime["required_finite_ancestor_headroom_bytes"] == 0

    phase = task42_phase_memory_gate(
        tree_rss_bytes=resident,
        tree_rss_scope="whole_job",
        cgroup_current_bytes=None,
        cgroup_current_state="not_applicable",
        phase_additional_bytes=0,
        memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES + workspace - 1,
        mem_total_bytes=mem_total,
        ancestor_limit_state="finite",
        ancestor_memory=[
            {
                "memory_limit_state": "finite",
                "memory_current_bytes": 1,
                "memory_limit_bytes": workspace,
                "memory_headroom_bytes": workspace - 1,
            }
        ],
    )
    assert phase["pass"] is False
    assert phase["resident_cap_pass"] is False
    assert phase["host_memavailable_pass"] is False
    assert phase["finite_ancestor_headroom_pass"] is False

    over_limit = _authority(
        root_pid=42000,
        tree_rss_bytes=resident,
        memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
        mem_total_bytes=mem_total,
        ancestor_headroom_bytes=0,
    )
    over_limit["job_cgroup"]["ancestor_memory"][0]["memory_current_bytes"] = 2
    rejected = task42_runtime_memory_gate_from_authority(
        over_limit, expected_root_pid=42000
    )
    assert rejected["pass"] is False
    assert "finite_ancestor_cgroup_row_0_headroom_is_inconsistent" in rejected[
        "errors"
    ]


def test_task42_runtime_labels_only_known_whole_job_cap_exceedance():
    mem_total = 1024 * 2**30
    parameters = task42_memory_parameters(mem_total)
    cap = parameters["cap_C_bytes"]
    assert type(cap) is int

    # This is the relevant-field projection of the saved 062050 final sample:
    # whole-job status was incomplete although partial tree RSS and dedicated
    # cgroup current were numeric.
    saved_sample_root = 2112622
    saved_sample = {
        "process_tree": {
            "root_pid": saved_sample_root,
            "pids": [
                saved_sample_root,
                2112625,
                2112631,
                2112632,
                2112633,
                2112634,
                2112635,
                2112636,
                2112637,
                2112638,
            ],
            "all_status_readable": False,
            "rss_bytes": 71376896,
        },
        "job_cgroup": {
            "readable": True,
            "dedicated_job_cgroup": True,
            "scope_semantics": "dedicated_job_cgroup_authority",
            "memory_current_bytes": 11119267840,
            "ancestor_hard_limit_state": "max_or_unlimited",
            "ancestor_memory": [
                {"memory_limit_state": "max_or_unlimited"},
                {"memory_limit_state": "not_applicable_root"},
            ],
        },
        "host_memory": {
            "mem_total_bytes": 2163100385280,
            "kernel_memavailable": {
                "status": "measured",
                "bytes": 1859294306304,
            },
        },
    }
    actual_refusal = task42_runtime_memory_gate_from_authority(
        saved_sample, expected_root_pid=saved_sample_root
    )
    assert actual_refusal["pass"] is False
    assert actual_refusal["authority_inputs"]["tree_rss_scope"] == "unknown"
    assert actual_refusal["resident_J_bytes"] == 11119267840
    assert actual_refusal["errors"] == [
        "whole_job_process_tree_is_incomplete_or_unreadable",
        "runtime_whole_job_J_is_unknown",
    ]

    for resident, expected_pass, expected_error in (
        (cap - 1, True, None),
        (cap, True, None),
        (cap + 1, False, "runtime_whole_job_J_exceeds_Task42_C"),
    ):
        authority = _authority(
            root_pid=42000,
            tree_rss_bytes=resident,
            memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
            mem_total_bytes=mem_total,
            ancestor_headroom_bytes=0,
        )
        runtime = task42_runtime_memory_gate_from_authority(
            authority, expected_root_pid=42000
        )
        assert runtime["pass"] is expected_pass
        if expected_error is None:
            assert "runtime_whole_job_J_exceeds_Task42_C" not in runtime["errors"]
        else:
            assert expected_error in runtime["errors"]

    missing_ancestor = _authority(
        root_pid=42000,
        tree_rss_bytes=1 * 2**30,
        memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
        mem_total_bytes=mem_total,
        ancestor_headroom_bytes=0,
    )
    missing_ancestor["job_cgroup"]["ancestor_memory"] = []
    missing_ancestor_gate = task42_runtime_memory_gate_from_authority(
        missing_ancestor, expected_root_pid=42000
    )
    assert missing_ancestor_gate["pass"] is False
    assert "ancestor_cgroup_memory_chain_is_missing" in missing_ancestor_gate[
        "errors"
    ]
    assert "runtime_whole_job_J_exceeds_Task42_C" not in missing_ancestor_gate[
        "errors"
    ]


def test_task42_startup_budget_is_evidence_bound_and_predicted():
    budget = task42_startup_memory_budget(8)
    assert budget["status"] == "predicted"
    assert budget["pass"] is True
    assert budget["delta_bytes"] == TASK42_STARTUP_PREDICTED_DELTA_BYTES
    assert budget["evidence"]["role"] == "predicted_startup_delta_not_measurement"
    assert budget["evidence"]["observed_window_growth_bytes"] < budget["delta_bytes"]
    assert task42_startup_memory_budget(4)["pass"] is False


def test_task42_launcher_soft_target_and_runtime_cap_use_whole_job_root(tmp_path):
    cap = task42_memory_parameters(1024 * 2**30)["cap_C_bytes"]
    assert type(cap) is int
    def initial(root):
        return _task42_authority(
            root_pid=root,
            tree_rss_bytes=2 * 2**30,
            memavailable_bytes=600 * 2**30,
        )

    def at_cap(root):
        return _task42_authority(
            root_pid=root,
            tree_rss_bytes=cap,
            memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
            ancestor_headroom_bytes=0,
        )

    class _SoftTargetClock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += max(seconds, TASK42_SOFT_TARGET_SECONDS + 1)

    clock = _SoftTargetClock()
    result, calls = _task42_launch(
        tmp_path,
        samples=[initial, at_cap, at_cap],
        process=_Task42FakeProcess(polls_before_exit=1),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    resource = result["resource_authority"]["task42_staged_direct"]
    assert calls["popen"]
    assert calls["terminated"] == []
    assert result["result_classification"] == "worker_exit0"
    assert resource["soft_target_reached"] is True
    assert resource["hard_wall_timeout"] is False
    assert resource["latest_gate"]["pass"] is True
    assert resource["latest_gate"]["resident_J_bytes"] == cap
    assert resource["warning_threshold_bytes"] == (9 * cap) // 10
    assert resource["warning_threshold_role"] == "0.9_times_current_Task42_cap_C"
    assert resource["latest_gate"]["workspace_W_applied"] is False
    assert resource["root_pid"] == calls["sampled_roots"][0]
    assert calls["sampled_roots"] == [resource["root_pid"]] * 3
    assert calls["popen"][0][1]["env"]["TASK038_JOB_ROOT_PID"] == str(
        resource["root_pid"]
    )


def test_task42_launcher_terminates_only_after_runtime_J_exceeds_C(tmp_path):
    cap = task42_memory_parameters(1024 * 2**30)["cap_C_bytes"]
    assert type(cap) is int
    samples = [
        lambda root: _task42_authority(
            root_pid=root,
            tree_rss_bytes=2 * 2**30,
            memavailable_bytes=600 * 2**30,
        ),
        lambda root: _task42_authority(
            root_pid=root,
            tree_rss_bytes=cap + 1,
            memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
            ancestor_headroom_bytes=0,
        ),
    ]
    result, calls = _task42_launch(tmp_path, samples=samples)
    assert calls["sampled_roots"] == [result["resource_authority"][
        "task42_staged_direct"
    ]["root_pid"]] * 2
    assert calls["terminated"] == [424242]
    assert result["result_classification"] == "task42_runtime_resource_gate_refused"
    assert result["resource_authority"]["task42_staged_direct"]["latest_gate"][
        "resident_J_bytes"
    ] == cap + 1


def test_task42_startup_refusal_does_not_start_worker(tmp_path):
    def refuse_before_spawn(root):
        return _task42_authority(
            root_pid=root,
            tree_rss_bytes=2 * 2**30,
            memavailable_bytes=TASK42_MEMORY_RESERVE_BYTES,
        )

    result, calls = _task42_launch(tmp_path, samples=refuse_before_spawn)
    assert result["result_classification"] == "task42_initial_resource_refused"
    assert calls["sampled_roots"] == [result["resource_authority"]["root_pid"]]
    assert calls["popen"] == []
    assert calls["terminated"] == []


def test_task041_v16_phase_wrapper_keeps_legacy_schema_and_error_vectors():
    gib = 2**30
    cap = TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES
    reserve = TASK041_BALH_CELL_CONDENSED_RESERVE_BYTES
    workspace = TASK041_BALH_W0P7NM_P6_PILOT_POLICY_RESERVE_BYTES
    tree = 12 * gib
    cgroup = 13 * gib
    delta = 2 * gib
    host_available = reserve + delta + workspace
    ancestors = [
        {
            "memory_limit_state": "finite",
            "memory_headroom_bytes": delta + workspace,
        }
    ]
    valid = task041_v16_phase_memory_gate(
        tree_rss_bytes=tree,
        cgroup_current_bytes=cgroup,
        phase_additional_bytes=delta,
        memavailable_bytes=host_available,
        ancestor_limit_state="finite",
        ancestor_memory=ancestors,
    )
    assert set(valid) == {
        "schema",
        "status",
        "pass",
        "authority_schema",
        "resident_J_bytes",
        "tree_rss_bytes",
        "dedicated_cgroup_current_bytes",
        "phase_additional_Delta_bytes",
        "workspace_W_bytes",
        "projected_J_plus_Delta_plus_W_bytes",
        "cap_bytes",
        "MemAvailable_bytes",
        "required_MemAvailable_bytes",
        "reserve_bytes",
        "ancestor_required_headroom_bytes",
        "ancestor_limit_state",
        "finite_ancestor_headrooms_bytes",
        "external_resource_gates",
        "errors",
    }
    assert valid["schema"] == "task041.v16.phase_memavailable_gate.v1"
    assert valid["status"] == "passed"
    assert valid["pass"] is True
    assert valid["errors"] == []
    assert valid["resident_J_bytes"] == cgroup
    assert valid["phase_additional_Delta_bytes"] == delta
    assert valid["workspace_W_bytes"] == TASK041_BALH_W0P7NM_P6_PILOT_POLICY_RESERVE_BYTES
    assert valid["projected_J_plus_Delta_plus_W_bytes"] == cgroup + delta + workspace
    assert valid["cap_bytes"] == TASK041_BALH_W0P7NM_P6_PILOT_HARD_MEMORY_BYTES
    assert valid["MemAvailable_bytes"] == host_available
    assert valid["required_MemAvailable_bytes"] == reserve + delta + workspace
    assert valid["external_resource_gates"] == {
        "resident_cap": True,
        "host_memavailable": True,
        "finite_ancestor_headroom": True,
    }

    invalid_cap = task041_v16_phase_memory_gate(
        tree_rss_bytes=tree,
        cgroup_current_bytes=cgroup,
        phase_additional_bytes=delta,
        memavailable_bytes=host_available,
        ancestor_limit_state="finite",
        ancestor_memory=ancestors,
        cap_bytes=cap + 1,
    )
    assert invalid_cap["errors"] == [
        "V16_cap_reserve_or_W_contract_mismatch",
        "resident_J_plus_Delta_plus_W_exceeds_cap_or_is_unknown",
        "MemAvailable_below_reserve_plus_Delta_plus_W_or_unknown",
    ]

    missing_tree = task041_v16_phase_memory_gate(
        tree_rss_bytes=None,
        cgroup_current_bytes=cgroup,
        phase_additional_bytes=delta,
        memavailable_bytes=host_available,
        ancestor_limit_state="finite",
        ancestor_memory=ancestors,
    )
    assert missing_tree["errors"] == [
        "resident_Delta_or_MemAvailable_input_missing_or_invalid",
        "resident_J_plus_Delta_plus_W_exceeds_cap_or_is_unknown",
    ]

    unknown_cgroup = task041_v16_phase_memory_gate(
        tree_rss_bytes=tree,
        cgroup_current_bytes=None,
        phase_additional_bytes=delta,
        memavailable_bytes=host_available,
        ancestor_limit_state="finite",
        ancestor_memory=ancestors,
    )
    assert unknown_cgroup["errors"] == [
        "resident_Delta_or_MemAvailable_input_missing_or_invalid",
        "resident_J_plus_Delta_plus_W_exceeds_cap_or_is_unknown",
    ]

    short_ancestor = task041_v16_phase_memory_gate(
        tree_rss_bytes=tree,
        cgroup_current_bytes=cgroup,
        phase_additional_bytes=delta,
        memavailable_bytes=host_available,
        ancestor_limit_state="finite",
        ancestor_memory=[
            {
                "memory_limit_state": "finite",
                "memory_headroom_bytes": delta + workspace - 1,
            }
        ],
    )
    assert short_ancestor["errors"] == [
        "finite_ancestor_headroom_below_Delta_plus_W_or_unknown"
    ]


def test_launcher_resource_log_create_new_rejects_existing_bytes(tmp_path):
    path = tmp_path / "task42_resource_phases.jsonl"
    _append_task42_phase_record(
        path, {"schema": "task42.test.v1", "phase": "first"}, create_new=True
    )
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        _append_task42_phase_record(
            path, {"schema": "task42.test.v1", "phase": "overwrite"}, create_new=True
        )
    assert path.read_bytes() == original


class _Task42GateComm:
    def __init__(self, *, replicated_rows=1, rank_deltas=None, alter_rows=None):
        self.rank = 0
        self.size = replicated_rows
        self.rank_deltas = rank_deltas
        self.alter_rows = alter_rows
        self.broadcast_count = 0

    def allgather(self, value):
        rows = []
        deltas = (
            self.rank_deltas
            if self.rank_deltas is not None
            else [value.get("local_delta_bytes", 0)] * self.size
        )
        for rank, delta in enumerate(deltas):
            row = dict(value)
            row["rank"] = rank
            if self.rank_deltas is not None:
                row["local_delta_bytes"] = delta
            if isinstance(row.get("inventory"), dict):
                components = row["inventory"].get("components")
                if isinstance(components, list):
                    components = [
                        dict(component)
                        if isinstance(component, dict)
                        else component
                        for component in components
                    ]
                if self.rank_deltas is not None and isinstance(components, list):
                    rank_local = [
                        component
                        for component in components
                        if isinstance(component, dict)
                        and component.get("scope") == "rank_local"
                    ]
                    if len(rank_local) == 1:
                        rank_local[0] = {**rank_local[0], "delta_bytes": delta}
                        components = [
                            rank_local[0]
                            if isinstance(component, dict)
                            and component.get("scope") == "rank_local"
                            else component
                            for component in components
                        ]
                row["inventory"] = {
                    **row["inventory"],
                    "components": components,
                }
            rows.append(row)
        if self.alter_rows is not None:
            self.alter_rows(rows)
        return rows

    def bcast(self, value, root=0):
        assert root == 0
        self.broadcast_count += 1
        return value


def test_task42_worker_phase_receipts_append_two_stages_and_scope_delta(
    tmp_path, monkeypatch
):
    import benchmarks.task034_wsl_resources as resources
    import src.io.input_validation as validation

    authority = {"schema": "task42.test_authority.v1"}
    monkeypatch.setattr(resources, "resource_authority_sample", lambda _pid: authority)
    gate_calls = []

    def phase_gate(sample, *, expected_root_pid, phase_additional_bytes):
        gate_calls.append((sample, expected_root_pid, phase_additional_bytes))
        return {"pass": True, "phase_additional_bytes": phase_additional_bytes}

    monkeypatch.setattr(validation, "task42_memory_gate_from_authority", phase_gate)
    output = tmp_path / "out"
    output.mkdir()
    receipt = output / "numerical_output/task42_stage_resource_gates.jsonl"
    open_modes = []
    original_open = Path.open

    def record_open_mode(path, mode="r", *args, **kwargs):
        if path == receipt:
            open_modes.append(mode)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record_open_mode)
    callback = _task42_stage_gate_callback(
        output_directory=output,
        comm=_Task42GateComm(replicated_rows=1),
        root_pid=42000,
    )
    first = callback(
        "symbolic_preflight",
        10,
        {
            "components": [
                {
                    "name": "factor_metadata",
                    "scope": "rank_local",
                    "delta_bytes": 10,
                    "unit": "bytes",
                }
            ]
        },
    )
    second = callback(
        "numeric_preflight",
        20,
        {
            "components": [
                {
                    "name": "numeric_workspace",
                    "scope": "rank_local",
                    "delta_bytes": 20,
                    "unit": "bytes",
                }
            ]
        },
    )
    assert first["pass"] is True
    assert second["pass"] is True
    assert [entry[2] for entry in gate_calls] == [10, 20]

    assert open_modes == ["x", "a"]
    records = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert [record["phase"] for record in records] == [
        "symbolic_preflight",
        "numeric_preflight",
    ]
    assert [record["phase_additional_bytes"] for record in records] == [10, 20]


def test_task42_worker_sums_rank_local_delta_components(tmp_path, monkeypatch):
    import benchmarks.task034_wsl_resources as resources
    import src.io.input_validation as validation

    monkeypatch.setattr(
        resources,
        "resource_authority_sample",
        lambda _pid: {"schema": "task42.test_authority.v1"},
    )
    observed_delta = []
    monkeypatch.setattr(
        validation,
        "task42_memory_gate_from_authority",
        lambda _sample, *, expected_root_pid, phase_additional_bytes: (
            observed_delta.append(phase_additional_bytes) or {"pass": True}
        ),
    )
    output = tmp_path / "out"
    output.mkdir()
    callback = _task42_stage_gate_callback(
        output_directory=output,
        comm=_Task42GateComm(rank_deltas=[3, 5]),
        root_pid=42005,
    )
    result = callback(
        "mesh_export_preflight",
        3,
        {
            "components": [
                {
                    "name": "rank_local_csr_export",
                    "scope": "rank_local",
                    "delta_bytes": 3,
                    "unit": "bytes",
                }
            ]
        },
    )
    assert result["pass"] is True
    assert observed_delta == [8]
    record = json.loads(
        (output / "numerical_output/task42_stage_resource_gates.jsonl")
        .read_text()
        .splitlines()[0]
    )
    assert record["phase_additional_bytes"] == 8
    assert record["phase_delta_aggregation"]["rank_local_csr_export"] == {
        "scope": "rank_local",
        "unit": "bytes",
        "rank_values_bytes": [3, 5],
        "counted_bytes": 8,
        "aggregation": "sum_rank_local_values",
    }


def test_task42_recovery_gather_buffers_are_rank_local_and_summed(
    tmp_path, monkeypatch
):
    import benchmarks.task034_wsl_resources as resources
    import src.io.input_validation as validation
    from src.solvers.dtn_port_3d import (
        _task42_active_trace_gather_memory_component,
    )

    active_trace_rows = 125
    scalar_bytes = 16
    component = _task42_active_trace_gather_memory_component(
        active_trace_rows=active_trace_rows,
        scalar_bytes=scalar_bytes,
    )
    per_rank_bytes = 2 * active_trace_rows * scalar_bytes
    assert component["scope"] == "rank_local"
    assert component["delta_bytes"] == per_rank_bytes
    assert component["basis"]["formula"] == (
        "2*global_active_trace_rows*scalar_bytes per rank"
    )
    assert component["basis"]["copies_per_rank"] == 2

    monkeypatch.setattr(
        resources,
        "resource_authority_sample",
        lambda _pid: {"schema": "task42.test_authority.v1"},
    )
    observed_delta = []
    monkeypatch.setattr(
        validation,
        "task42_memory_gate_from_authority",
        lambda _sample, *, expected_root_pid, phase_additional_bytes: (
            observed_delta.append(phase_additional_bytes) or {"pass": True}
        ),
    )
    output = tmp_path / "out"
    output.mkdir()
    callback = _task42_stage_gate_callback(
        output_directory=output,
        comm=_Task42GateComm(rank_deltas=[per_rank_bytes] * 8),
        root_pid=42008,
    )
    result = callback(
        "before_full_field_recovery_after_factor_destroy",
        per_rank_bytes,
        {"components": [component]},
    )
    assert result["pass"] is True
    assert result["phase_additional_bytes"] == 8 * per_rank_bytes
    assert observed_delta == [8 * per_rank_bytes]
    record = json.loads(
        (output / "numerical_output/task42_stage_resource_gates.jsonl")
        .read_text()
        .splitlines()[0]
    )
    assert record["phase_delta_aggregation"][
        "task42_global_active_trace_gather_buffers"
    ] == {
        "scope": "rank_local",
        "unit": "bytes",
        "rank_values_bytes": [per_rank_bytes] * 8,
        "counted_bytes": 8 * per_rank_bytes,
        "aggregation": "sum_rank_local_values",
    }


def test_task42_worker_counts_replicated_global_delta_once(tmp_path, monkeypatch):
    import benchmarks.task034_wsl_resources as resources
    import src.io.input_validation as validation

    monkeypatch.setattr(
        resources,
        "resource_authority_sample",
        lambda _pid: {"schema": "task42.test_authority.v1"},
    )
    observed_delta = []
    monkeypatch.setattr(
        validation,
        "task42_memory_gate_from_authority",
        lambda _sample, *, expected_root_pid, phase_additional_bytes: (
            observed_delta.append(phase_additional_bytes) or {"pass": True}
        ),
    )
    output = tmp_path / "out"
    output.mkdir()
    callback = _task42_stage_gate_callback(
        output_directory=output,
        comm=_Task42GateComm(replicated_rows=8),
        root_pid=42001,
    )
    result = callback(
        "mumps_symbolic_info",
        0,
        {
            "components": [
                {
                    "name": "mumps_infog17_sum_symbolic_work",
                    "scope": "global_replicated",
                    "delta_bytes": 64 * 2**20,
                    "unit": "bytes",
                    "source": "MUMPS_INFOG_17_global_sum_symbolic_work",
                    "source_unit": "million_bytes_10^6_bytes; raw integer retained",
                    "conversion": "raw_integer_times_1000000",
                }
            ]
        },
    )
    assert result["pass"] is True
    assert observed_delta == [64 * 2**20]
    record = json.loads(
        (output / "numerical_output/task42_stage_resource_gates.jsonl")
        .read_text()
        .splitlines()[0]
    )
    assert record["phase_delta_aggregation"][
        "mumps_infog17_sum_symbolic_work"
    ] == {
        "scope": "global_replicated",
        "unit": "bytes",
        "rank_values_bytes": [64 * 2**20] * 8,
        "counted_bytes": 64 * 2**20,
        "aggregation": "count_one_replicated_global_value",
    }
    assert record["phase_additional_bytes"] == 64 * 2**20


def test_task42_worker_requires_consistent_delta_scope_and_inventory(tmp_path, monkeypatch):
    import benchmarks.task034_wsl_resources as resources
    import src.io.input_validation as validation

    monkeypatch.setattr(
        resources,
        "resource_authority_sample",
        lambda _pid: {"schema": "task42.test_authority.v1"},
    )
    gate_calls = []

    def phase_gate(_sample, *, expected_root_pid, phase_additional_bytes):
        gate_calls.append(phase_additional_bytes)
        return {"pass": True}

    monkeypatch.setattr(validation, "task42_memory_gate_from_authority", phase_gate)
    output = tmp_path / "out"
    output.mkdir()
    inconsistent = _task42_stage_gate_callback(
        output_directory=output,
        comm=_Task42GateComm(
            replicated_rows=8,
            alter_rows=lambda rows: rows[-1]["inventory"]["components"][0].update(
                delta_bytes=65
            ),
        ),
        root_pid=42003,
    )
    result = inconsistent(
        "mumps_symbolic_info",
        0,
        {
            "components": [
                {
                    "name": "mumps_infog17",
                    "scope": "global_replicated",
                    "delta_bytes": 64,
                    "unit": "bytes",
                }
            ]
        },
    )
    assert result["pass"] is False
    assert "replicated_global_component_mumps_infog17_differs" in result[
        "errors"
    ]
    assert gate_calls == []

    mismatch_output = tmp_path / "mismatch"
    mismatch_output.mkdir()
    mismatched_inventory = _task42_stage_gate_callback(
        output_directory=mismatch_output,
        comm=_Task42GateComm(),
        root_pid=42004,
    )
    mismatch = mismatched_inventory(
        "numeric_estimate",
        65,
        {
            "components": [
                {
                    "name": "rank_local_numeric_copy",
                    "scope": "rank_local",
                    "delta_bytes": 64,
                    "unit": "bytes",
                }
            ]
        },
    )
    assert mismatch["pass"] is False
    assert "rank_0_rank_local_inventory_differs_from_gate_argument" in mismatch[
        "errors"
    ]
    assert gate_calls == []


def test_task42_worker_broadcasts_first_receipt_write_failure(tmp_path, monkeypatch):
    import benchmarks.task034_wsl_resources as resources
    import src.io.input_validation as validation

    monkeypatch.setattr(
        resources,
        "resource_authority_sample",
        lambda _pid: {"schema": "task42.test_authority.v1"},
    )
    monkeypatch.setattr(
        validation,
        "task42_memory_gate_from_authority",
        lambda *_args, **_kwargs: {"pass": True},
    )
    output = tmp_path / "out"
    output.mkdir()
    comm = _Task42GateComm()
    callback = _task42_stage_gate_callback(
        output_directory=output, comm=comm, root_pid=42002
    )
    samples_path = output / "numerical_output/task42_stage_resource_gates.jsonl"
    original_open = Path.open

    def fail_first_receipt_open(path, *args, **kwargs):
        if path == samples_path:
            raise PermissionError("fixture blocks first receipt writer")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_first_receipt_open)
    result = callback(
        "symbolic_preflight",
        1,
        {
            "components": [
                {
                    "name": "rank_local_matrix_copy",
                    "scope": "rank_local",
                    "delta_bytes": 1,
                    "unit": "bytes",
                }
            ]
        },
    )
    assert result["pass"] is False
    assert result["decision"] == "refuse"
    assert result["errors"] == [
        "phase_receipt_write_failed:PermissionError:fixture blocks first receipt writer"
    ]
    assert comm.broadcast_count == 2
    assert not samples_path.exists()
