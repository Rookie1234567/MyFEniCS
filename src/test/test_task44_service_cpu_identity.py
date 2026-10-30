from __future__ import annotations

from pathlib import Path

import scripts.task44_service_startup as startup


def _cgroup(tmp_path: Path, pid: int) -> Path:
    root = tmp_path / "service-cgroup"
    root.mkdir()
    (root / "cgroup.procs").write_text(f"{pid}\n", encoding="ascii")
    return root


def _identity(pid: int, start_ticks: int) -> dict[str, object]:
    return {
        "pid": pid,
        "parent_pid": 4000,
        "state": "S",
        "start_ticks": start_ticks,
        "command_line": f"python worker-for-{pid}",
    }


def test_process_identity_records_parent_and_state(tmp_path):
    pid = 4242
    process_root = tmp_path / str(pid)
    process_root.mkdir()
    stat_fields = ["S", "4000", *(["0"] * 17), "99123"]
    (process_root / "stat").write_text(
        f"{pid} (python worker) {' '.join(stat_fields)}\n", encoding="ascii"
    )
    (process_root / "cmdline").write_bytes(b"python\0worker\0")

    assert startup._read_process_identity(pid, tmp_path) == {
        "pid": pid,
        "parent_pid": 4000,
        "state": "S",
        "start_ticks": 99123,
        "command_line": "python worker",
    }


def test_stable_affinity_mismatch_is_bound_to_pid_start_ticks_and_cgroup(
    tmp_path, monkeypatch
):
    pid = 4242
    cgroup = _cgroup(tmp_path, pid)
    monkeypatch.setattr(
        startup,
        "_read_process_identity",
        lambda observed_pid, _proc_root: _identity(observed_pid, 99123),
    )
    monkeypatch.setattr(startup.os, "sched_getaffinity", lambda _pid: {31})
    monkeypatch.setattr(startup.time, "sleep", lambda _seconds: None)

    result = startup.observe_cgroup_cpu_affinity(cgroup, {32})

    assert result["stop"] is True
    assert result["failures"] == ["service_pid_affinity_mismatch:4242"]
    mismatch = result["mismatch_processes"][0]
    assert mismatch["pid"] == pid
    assert mismatch["identity"]["start_ticks"] == 99123
    assert mismatch["identity"]["parent_pid"] == 4000
    assert mismatch["identity"]["state"] == "S"
    assert mismatch["identity"]["command_line"] == "python worker-for-4242"
    assert mismatch["cgroup_path"] == str(cgroup)
    assert [sample["cpu_affinity"] for sample in mismatch["affinity_samples"]] == [
        [31],
        [31],
    ]


def test_active_process_with_unreadable_affinity_fails_closed(tmp_path, monkeypatch):
    pid = 4545
    cgroup = _cgroup(tmp_path, pid)
    monkeypatch.setattr(
        startup,
        "_read_process_identity",
        lambda observed_pid, _proc_root: _identity(observed_pid, 99345),
    )

    def unreadable_affinity(_pid):
        raise PermissionError("scheduler affinity is not readable")

    monkeypatch.setattr(startup.os, "sched_getaffinity", unreadable_affinity)

    result = startup.observe_cgroup_cpu_affinity(cgroup, {32})

    assert result["stop"] is True
    assert result["failures"] == ["service_pid_affinity_unreadable:4545"]
    unreadable = next(
        row for row in result["observations"] if row.get("status") == "affinity_unreadable"
    )
    assert unreadable["identity"]["start_ticks"] == 99345
    assert unreadable["error"] == "scheduler affinity is not readable"


def test_exited_pid_during_affinity_query_is_recorded_as_transient(tmp_path, monkeypatch):
    pid = 4343
    cgroup = _cgroup(tmp_path, pid)
    monkeypatch.setattr(
        startup,
        "_read_process_identity",
        lambda observed_pid, _proc_root: _identity(observed_pid, 99234),
    )

    def affinity_then_exit(_pid):
        (cgroup / "cgroup.procs").write_text("", encoding="ascii")
        raise ProcessLookupError("process exited during observation")

    monkeypatch.setattr(startup.os, "sched_getaffinity", affinity_then_exit)

    result = startup.observe_cgroup_cpu_affinity(cgroup, {32})

    assert result["stop"] is False
    assert result["member_pids_final"] == []
    assert any(
        row.get("pid") == pid and row.get("status") == "transient_identity"
        for row in result["observations"]
    )


def test_reused_pid_is_retried_under_its_new_start_tick(tmp_path, monkeypatch):
    pid = 4444
    cgroup = _cgroup(tmp_path, pid)
    identities = iter((100, 101, 101, 101, 101))

    def changing_identity(observed_pid, _proc_root):
        try:
            start_ticks = next(identities)
        except StopIteration:
            start_ticks = 101
        return _identity(observed_pid, start_ticks)

    monkeypatch.setattr(startup, "_read_process_identity", changing_identity)
    monkeypatch.setattr(startup.os, "sched_getaffinity", lambda _pid: {32})

    result = startup.observe_cgroup_cpu_affinity(cgroup, {32})

    assert result["stop"] is False
    assert result["member_pids_final"] == [pid]
    assert result["service_pid_affinities"][str(pid)] == [32]
    assert any(
        row.get("pid") == pid
        and row.get("status") == "transient_identity"
        and row.get("identity_before", {}).get("start_ticks") == 100
        and row.get("identity_after", {}).get("start_ticks") == 101
        for row in result["observations"]
    )
