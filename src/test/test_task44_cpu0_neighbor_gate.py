from __future__ import annotations

import errno
from pathlib import Path

import pytest

from scripts import task44_native_service
from scripts.task44_native_service import (
    AUTHORIZED_CPU0_NEIGHBOR,
    _combined_performance_not_isolated,
    _cpu_neighbor_gate,
    _CpuNeighborMonitor,
    _owned_service_context,
)

_B11_LIST_UNITS_ERROR = (
    "command failed: systemctl: Failed to list units: 传输端点尚未连接\n"
)


def _proc_root(tmp_path: Path) -> Path:
    root = tmp_path / "proc"
    systemd = root / "1"
    systemd.mkdir(parents=True)
    (systemd / "comm").write_text("systemd\n", encoding="utf-8")
    (systemd / "status").write_text(
        "Name:\tsystemd\nCpus_allowed_list:\t0-3\n", encoding="utf-8"
    )
    (systemd / "stat").write_text(
        "1 (systemd) S 0 " + "0 " * 18 + "1\n", encoding="ascii"
    )
    return root


def _process(
    root: Path,
    *,
    pid: int,
    start_ticks: int,
    state: str = "S",
    parent_pid: int = 1,
    affinity: str = "0",
    command: str = AUTHORIZED_CPU0_NEIGHBOR["command_basename"],
    cgroup: str = "/user.slice/user-1000.slice/session-4665.scope",
    proc_comm: str = "python",
) -> None:
    process = root / str(pid)
    process.mkdir()
    fields = [state, str(parent_pid), *("0" for _ in range(17)), str(start_ticks)]
    (process / "stat").write_text(
        f"{pid} ({proc_comm}) {' '.join(fields)}\n", encoding="ascii"
    )
    (process / "status").write_text(
        f"Name:\t{proc_comm}\nCpus_allowed_list:\t{affinity}\n", encoding="utf-8"
    )
    (process / "cmdline").write_bytes(
        f"/usr/bin/python3\0/opt/Metrology/{command}\0".encode()
    )
    (process / "cgroup").write_text(f"0::{cgroup}\n", encoding="utf-8")


def _candidate(
    pid: int,
    *,
    parent_pid: int = 1,
    command: str = AUTHORIZED_CPU0_NEIGHBOR["command_basename"],
    snapshot_comm: str = "python",
    start_ticks: int | None = None,
    cgroup_path: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "pid": pid,
        "ppid": parent_pid,
        "comm": snapshot_comm,
        "command": f"python /opt/Metrology/{command}",
    }
    if start_ticks is not None:
        result["start_ticks"] = start_ticks
    if cgroup_path is not None:
        result["cgroup_path"] = cgroup_path
    return result


def _owned_service(
    tmp_path: Path, *, main_pid: int, unit: str = "task44-sample-owned.service"
) -> tuple[dict[str, object], Path, Path]:
    control_group = f"/user.slice/user-1000.slice/app.slice/{unit}"
    cgroup_fs_root = tmp_path / "sys-fs-cgroup"
    cgroup = cgroup_fs_root / control_group.lstrip("/")
    cgroup.mkdir(parents=True)
    (cgroup / "cgroup.procs").write_text(f"{main_pid}\n", encoding="ascii")
    facts: dict[str, object] = {
        "unit": unit,
        "invocation_id": "0123456789abcdef0123456789abcdef",
        "control_group": control_group,
        "active_state": "active",
        "main_pid": main_pid,
        "cpu_affinity": "0",
    }
    return facts, cgroup_fs_root, cgroup


def _patch_owned_service(monkeypatch, facts: dict[str, object], *, affinity: int = 0) -> None:
    monkeypatch.setattr(task44_native_service, "_unit_facts", lambda unit: dict(facts))
    monkeypatch.setattr(
        task44_native_service,
        "_unit_identity_signature_with_timeout",
        lambda unit, *, timeout_seconds: task44_native_service._unit_identity_signature(facts),
    )
    monkeypatch.setattr(task44_native_service.os, "sched_getaffinity", lambda pid: {affinity})


def test_authorized_supervisor_is_the_only_cpu0_claim(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=AUTHORIZED_CPU0_NEIGHBOR["pid"],
        start_ticks=AUTHORIZED_CPU0_NEIGHBOR["start_ticks"],
    )

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        numerical_processes=[_candidate(AUTHORIZED_CPU0_NEIGHBOR["pid"])],
    )

    assert report["status"] == "pass"
    assert report["performance_not_isolated"] is True
    assert report["authorized_neighbor"]["pid"] == AUTHORIZED_CPU0_NEIGHBOR["pid"]
    assert report["unexpected_claims"] == []


def test_no_neighbor_is_allowed_but_does_not_claim_shared_performance(tmp_path):
    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=_proc_root(tmp_path), numerical_processes=[]
    )

    assert report["status"] == "pass"
    assert report["authorized_neighbor"] is None
    assert report["performance_not_isolated"] is False


def test_reused_pid_does_not_inherit_cpu0_sharing_authority(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=AUTHORIZED_CPU0_NEIGHBOR["pid"],
        start_ticks=AUTHORIZED_CPU0_NEIGHBOR["start_ticks"] + 1,
    )

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        numerical_processes=[_candidate(AUTHORIZED_CPU0_NEIGHBOR["pid"])],
    )

    assert report["status"] == "fail"
    assert report["authorized_neighbor"] is None
    assert "authorized_cpu0_pid_identity_mismatch" in report["failures"]


@pytest.mark.parametrize(
    "changes",
    (
        {"parent_pid": 2},
        {"command": "different_supervisor.py"},
        {"affinity": "0-1"},
        {"affinity": "0-3"},
    ),
)
def test_changed_supervisor_identity_does_not_inherit_authority(tmp_path, changes):
    root = _proc_root(tmp_path)
    values = {
        "pid": AUTHORIZED_CPU0_NEIGHBOR["pid"],
        "start_ticks": AUTHORIZED_CPU0_NEIGHBOR["start_ticks"],
    }
    values.update(changes)
    _process(root, **values)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        numerical_processes=[
            _candidate(
                AUTHORIZED_CPU0_NEIGHBOR["pid"],
                parent_pid=changes.get("parent_pid", 1),
                command=changes.get("command", AUTHORIZED_CPU0_NEIGHBOR["command_basename"]),
            )
        ],
    )

    assert report["status"] == "fail"
    assert report["authorized_neighbor"] is None
    assert "authorized_cpu0_pid_identity_mismatch" in report["failures"]


def test_second_narrow_cpu0_process_is_rejected(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=AUTHORIZED_CPU0_NEIGHBOR["pid"],
        start_ticks=AUTHORIZED_CPU0_NEIGHBOR["start_ticks"],
    )
    _process(
        root,
        pid=5000,
        start_ticks=9000,
        command="another_solver.py",
        cgroup="/user.slice/user-1000.slice/app.slice/other.service",
    )

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        numerical_processes=[
            _candidate(AUTHORIZED_CPU0_NEIGHBOR["pid"]),
            _candidate(5000, command="another_solver.py"),
        ],
    )

    assert report["status"] == "fail"
    assert report["failures"] == ["unexpected_narrow_selected_cpu_affinity_neighbor"]
    assert [row["pid"] for row in report["unexpected_claims"]] == [5000]


@pytest.mark.parametrize(
    "unit",
    (
        "task44-sample-owned.service",
        "task44-preflight-owned-1234.service",
    ),
)
def test_owned_service_member_with_exec_comm_transition_is_excluded_and_affinity_is_checked(
    tmp_path, monkeypatch, unit
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _cgroup = _owned_service(
        tmp_path, main_pid=6000, unit=unit
    )
    _process(
        root,
        pid=6000,
        start_ticks=10000,
        command="run_case.py",
        cgroup=facts["control_group"],
    )
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6000, command="run_case.py", snapshot_comm="bash",
            start_ticks=10000, cgroup_path=facts["control_group"],
        )],
    )

    assert report["status"] == "pass"
    assert report["narrow_selected_cpu_affinity_claims"] == []
    assert report["owned_service_context"]["identity_verified"] is True
    assert report["owned_service_context"]["affinity_verified"] is True
    assert report["owned_service_excluded_pids"] == [6000]
    assert report["owned_service_member_proofs"][0]["comm_transition_observed"] is True


@pytest.mark.parametrize(
    "unit",
    (
        "task44-preflight.service",
        "task44-other-owned.service",
        "task44-preflight-owned_bad.service",
    ),
)
def test_owned_service_identity_rejects_unrecognized_or_malformed_unit_names(
    tmp_path, unit
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _cgroup = _owned_service(
        tmp_path, main_pid=6000, unit=unit
    )

    report = _owned_service_context(
        facts,
        ignored_cgroup=facts["control_group"],
        selected_cpu=0,
        proc_root=root,
        cgroup_fs_root=cgroup_fs_root,
    )

    assert report["identity_verified"] is False
    assert report["failures"] == ["owned_service_context_observation_failed"]
    assert report["failure_stage"] == "input_validation"
    assert report["error"] == "service facts do not identify the active selected-CPU invocation"


def test_exited_owned_process_snapshot_is_nonfatal_only_after_direct_stat_enoent(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6015)
    _process(root, pid=6015, start_ticks=10015, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(
                6015,
                command="run_case.py",
                start_ticks=10015,
                cgroup_path=facts["control_group"],
            ),
            _candidate(6016, start_ticks=10016, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "pass"
    assert report["failures"] == []
    assert report["stale_snapshot_confirmed_gone"][0]["pid"] == 6016
    assert report["stale_snapshot_confirmed_gone"][0]["status"] == "stale_snapshot_confirmed_gone"
    assert report["stale_snapshot_confirmed_gone"][0]["proc_directory_confirmation"]["status"] == "gone"
    proof = report["stale_snapshot_confirmed_gone"][0]
    assert proof["member_gap_recheck"]["status"] == "gone"
    assert proof["member_gap_recheck"]["attempt_count"] == 1
    assert report["unverified_owned_members"] == []


def test_owned_candidate_exit_during_bounded_gap_recheck_is_nonfatal(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6014)
    _process(root, pid=6014, start_ticks=10014, cgroup=facts["control_group"])
    _process(root, pid=6024, start_ticks=10024, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    def exit_candidate(_seconds):
        process_dir = root / "6024"
        for item in process_dir.iterdir():
            item.unlink()
        process_dir.rmdir()

    monkeypatch.setattr(task44_native_service.time, "sleep", exit_candidate)
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6014, start_ticks=10014, cgroup_path=facts["control_group"]),
            _candidate(6024, start_ticks=10024, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "pass"
    assert report["failures"] == []
    proof = next(row for row in report["stale_snapshot_confirmed_gone"] if row["pid"] == 6024)
    assert proof["member_gap_recheck"]["status"] == "gone"
    assert proof["member_gap_recheck"]["attempt_count"] == 2
    assert proof["proc_directory_confirmation"]["status"] == "gone"


def test_train_007_transient_assembler_exit_uses_one_fresh_context_query(
    tmp_path, monkeypatch
):
    """Reproduce train_007's 3.872 ms tail query after an assembler exits.

    Factual identity: service task44-sample-train-007-v2.service,
    InvocationID 7ea92ca5d7724a24b2a6770f46108875, MainPID 394010 at
    start ticks 348483132; transient GNU as PID 406525 at start ticks
    349033677, parent 406312. See outcomes/training_results_v2.md and the
    preserved service_summary.json for the run-bound evidence.
    """
    root = _proc_root(tmp_path)
    unit = "task44-sample-train-007-v2.service"
    facts, cgroup_fs_root, cgroup = _owned_service(tmp_path, main_pid=394010, unit=unit)
    facts.update({
        "invocation_id": "7ea92ca5d7724a24b2a6770f46108875",
        "cpu_affinity": "0",
    })
    (cgroup / "cgroup.procs").write_text("394010\n406525\n", encoding="ascii")
    _process(
        root, pid=394010, start_ticks=348483132, parent_pid=2818, affinity="0",
        command="task44_native_service.py", cgroup=facts["control_group"],
    )
    _process(
        root, pid=406525, start_ticks=349033677, parent_pid=406312,
        affinity="0", command="as", proc_comm="as",
        cgroup=facts["control_group"],
    )
    _patch_owned_service(monkeypatch, facts)

    clock = [0.0]
    monkeypatch.setattr(task44_native_service.time, "monotonic", lambda: clock[0])
    signature = task44_native_service._unit_identity_signature(facts)
    query_budgets = []

    def systemd_query_with_observed_tail(unit, *, timeout_seconds):
        query_budgets.append(timeout_seconds)
        if timeout_seconds <= 0.003872454632073641:
            clock[0] += timeout_seconds
            raise task44_native_service.subprocess.TimeoutExpired(
                ["systemctl", "--user", "show", unit], timeout_seconds
            )
        if len(query_budgets) == 2:
            # The old context bracket completed with only the observed 3.872 ms left.
            clock[0] = 0.05 - 0.003872454632073641
        return signature

    monkeypatch.setattr(
        task44_native_service, "_unit_identity_signature_with_timeout",
        systemd_query_with_observed_tail,
    )
    original_member = task44_native_service._owned_service_member

    def exit_transient_assembler(process, **kwargs):
        if int(process["pid"]) != 406525:
            return original_member(process, **kwargs)
        process_dir = root / "406525"
        for item in process_dir.iterdir():
            item.unlink()
        process_dir.rmdir()
        (cgroup / "cgroup.procs").write_text("394010\n", encoding="ascii")
        return False, {
            "pid": 406525,
            "candidate_snapshot": {
                "ppid": 406312,
                "comm": "as",
                "start_ticks": 349033677,
                "cgroup_path": facts["control_group"],
            },
            "failure_stage": "proc_identity_before",
            "error_type": "FileNotFoundError",
            "errno": errno.ENOENT,
            "error": "[Errno 2] No such file or directory: '/proc/406525/stat'",
        }

    monkeypatch.setattr(task44_native_service, "_owned_service_member", exit_transient_assembler)
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(
                394010, parent_pid=2818, command="task44_native_service.py",
                start_ticks=348483132, cgroup_path=facts["control_group"],
            ),
            _candidate(
                406525, parent_pid=406312, command="as", snapshot_comm="as",
                start_ticks=349033677, cgroup_path=facts["control_group"],
            ),
        ],
    )

    assert report["status"] == "pass"
    assert report["failures"] == []
    proof = report["stale_snapshot_confirmed_gone"][0]
    assert proof["pid"] == 406525
    assert proof["member_gap_recheck"]["status"] == "gone"
    assert proof["member_gap_recheck"]["attempt_count"] == 1
    assert query_budgets == [task44_native_service._OWNED_MEMBER_GAP_SYSTEMD_QUERY_TIMEOUT_SECONDS]


@pytest.mark.parametrize(
    ("drift", "expected_status"),
    (("invocation", "invocation_changed"), ("pid_reuse", "pid_reused")),
)
def test_gone_owned_candidate_still_fails_closed_on_identity_drift(
    tmp_path, monkeypatch, drift, expected_status
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, cgroup = _owned_service(tmp_path, main_pid=6042)
    _process(root, pid=6042, start_ticks=10042, cgroup=facts["control_group"])
    _process(root, pid=6043, start_ticks=10043, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    original_member = task44_native_service._owned_service_member
    original_signature = task44_native_service._unit_identity_signature(facts)

    def exit_candidate(process, **kwargs):
        if int(process["pid"]) != 6043:
            return original_member(process, **kwargs)
        process_dir = root / "6043"
        for item in process_dir.iterdir():
            item.unlink()
        process_dir.rmdir()
        (cgroup / "cgroup.procs").write_text("6042\n", encoding="ascii")
        return False, {
            "pid": 6043,
            "candidate_snapshot": {
                "ppid": 6042,
                "comm": "cc1",
                "start_ticks": 10043,
                "cgroup_path": facts["control_group"],
            },
            "failure_stage": "proc_identity_before",
            "error_type": "FileNotFoundError",
            "errno": errno.ENOENT,
            "error": "[Errno 2] No such file or directory: '/proc/6043/stat'",
        }

    monkeypatch.setattr(task44_native_service, "_owned_service_member", exit_candidate)
    if drift == "invocation":
        monkeypatch.setattr(
            task44_native_service,
            "_unit_identity_signature_with_timeout",
            lambda unit, *, timeout_seconds: {
                **original_signature,
                "invocation_id": "f" * 32,
            },
        )
    else:
        original_confirmation = task44_native_service._confirm_proc_pid_directory_gone
        confirmation_calls = 0

        def reuse_after_gone(pid, proc_root):
            nonlocal confirmation_calls
            if pid == 6043:
                confirmation_calls += 1
                if confirmation_calls == 3:
                    _process(
                        root, pid=6043, start_ticks=20043, parent_pid=6042,
                        affinity="0", cgroup=facts["control_group"],
                    )
                    (cgroup / "cgroup.procs").write_text("6042\n6043\n", encoding="ascii")
            return original_confirmation(pid, proc_root)

        monkeypatch.setattr(
            task44_native_service, "_confirm_proc_pid_directory_gone", reuse_after_gone
        )

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6042, start_ticks=10042, cgroup_path=facts["control_group"]),
            _candidate(6043, parent_pid=6042, start_ticks=10043,
                       cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    assert report["stale_snapshot_confirmed_gone"] == []
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6043)
    assert proof["member_gap_recheck"]["status"] == expected_status
    assert "owned_service_member_identity_unverified" in report["failures"]
    if drift == "invocation":
        assert "owned_service_invocation_identity_unverified" in report["failures"]
    else:
        assert "owned_service_invocation_identity_unverified" not in report["failures"]


def test_pid_reuse_during_bounded_gap_recheck_is_not_treated_as_exit(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6013)
    _process(root, pid=6013, start_ticks=10013, cgroup=facts["control_group"])
    _process(root, pid=6023, start_ticks=10023, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    def reuse_candidate(_seconds):
        process_dir = root / "6023"
        for item in process_dir.iterdir():
            item.unlink()
        process_dir.rmdir()
        _process(
            root,
            pid=6023,
            start_ticks=20023,
            affinity="0",
            cgroup=facts["control_group"],
        )

    monkeypatch.setattr(task44_native_service.time, "sleep", reuse_candidate)
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6013, start_ticks=10013, cgroup_path=facts["control_group"]),
            _candidate(6023, start_ticks=10023, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    assert report["stale_snapshot_confirmed_gone"] == []
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6023)
    assert proof["member_gap_recheck"]["status"] == "pid_reused"
    assert proof["member_gap_recheck"]["candidate"]["identity_after"]["start_ticks"] == 20023


def test_missing_proc_stat_does_not_hide_a_present_owned_pid_directory(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6017)
    _process(root, pid=6017, start_ticks=10017, cgroup=facts["control_group"])
    _process(root, pid=6018, start_ticks=10018, affinity="0", cgroup=facts["control_group"])
    (root / "6018" / "stat").unlink()
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(
                6017,
                command="run_case.py",
                start_ticks=10017,
                cgroup_path=facts["control_group"],
            ),
            _candidate(6018, start_ticks=10018, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6018)
    assert proof["proc_directory_confirmation"]["status"] == "present"
    assert "owned_service_member_identity_unverified" in report["failures"]
    assert any(row["pid"] == 6018 for row in report["unreadable_processes"])


def test_malformed_proc_stat_is_not_treated_as_process_exit(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6016)
    _process(root, pid=6016, start_ticks=10016, cgroup=facts["control_group"])
    _process(root, pid=6018, start_ticks=10018, cgroup=facts["control_group"])
    (root / "6018" / "stat").write_text("6018 (python) S 1\n", encoding="ascii")
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6016, start_ticks=10016, cgroup_path=facts["control_group"]),
            _candidate(6018, start_ticks=10018, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    assert report["stale_snapshot_confirmed_gone"] == []
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6018)
    assert proof["member_gap_recheck"]["status"] == "unverified"
    assert proof["error_type"] == "ValueError"
    assert proof["error"] == "/proc/6018/stat is malformed"


def test_pid_reuse_after_owned_snapshot_enoent_remains_fail_closed(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6019)
    _process(root, pid=6019, start_ticks=10019, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    original_owned_member = task44_native_service._owned_service_member

    def vanish_then_reuse(process, **kwargs):
        pid = int(process["pid"])
        if pid != 6020:
            return original_owned_member(process, **kwargs)
        process_dir = root / str(pid)
        if process_dir.exists():
            for item in process_dir.iterdir():
                item.unlink()
            process_dir.rmdir()
        _process(
            root,
            pid=pid,
            start_ticks=20020,
            parent_pid=6019,
            affinity="0",
            cgroup=facts["control_group"],
        )
        return False, {
            "pid": pid,
            "candidate_snapshot": {
                "ppid": 6019,
                "comm": "cc1",
                "start_ticks": 10020,
                "cgroup_path": facts["control_group"],
            },
            "failure_stage": "proc_identity_before",
            "error_type": "FileNotFoundError",
            "error": f"[Errno {errno.ENOENT}] No such file or directory: '{root / str(pid) / 'stat'}'",
        }

    monkeypatch.setattr(task44_native_service, "_owned_service_member", vanish_then_reuse)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(
                6019,
                command="run_case.py",
                start_ticks=10019,
                cgroup_path=facts["control_group"],
            ),
            _candidate(
                6020,
                start_ticks=10020,
                cgroup_path=facts["control_group"],
            ),
        ],
    )

    assert report["status"] == "fail"
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6020)
    assert proof["proc_directory_confirmation"]["status"] == "present"
    assert report["stale_snapshot_confirmed_gone"] == []
    assert any(
        row["pid"] == 6020
        and row["evidence"]["identity_checks"]["snapshot_start_ticks_matches"] is False
        for row in report["unreadable_processes"]
    )


def test_proc_directory_stat_permission_error_is_not_treated_as_exit(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6021)
    _process(root, pid=6021, start_ticks=10021, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    process_path = root / "6022"
    original_stat = Path.stat

    def permission_denied(path, *args, **kwargs):
        if path == process_path:
            raise PermissionError(errno.EACCES, "test procfs access denied", str(path))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", permission_denied)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(
                6021,
                command="run_case.py",
                start_ticks=10021,
                cgroup_path=facts["control_group"],
            ),
            _candidate(6022, start_ticks=10022, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6022)
    assert proof["proc_directory_confirmation"]["status"] == "unverified"
    assert proof["proc_directory_confirmation"]["error_type"] == "PermissionError"
    assert proof["member_gap_recheck"]["status"] == "unverified"
    assert report["stale_snapshot_confirmed_gone"] == []


def test_same_pid_with_new_start_ticks_is_not_owned(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6001)
    _process(root, pid=6001, start_ticks=10001, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6001, start_ticks=10000, cgroup_path=facts["control_group"]
        )],
    )

    assert report["status"] == "fail"
    assert report["owned_service_excluded_pids"] == []
    proof = report["owned_service_member_proofs"][0]
    assert proof["checks"]["candidate_start_ticks_match_both_reads"] is False
    assert proof["invocation_context_corroboration"]["checks"][
        "candidate_context_membership_before"
    ] is True
    assert proof["invocation_context_corroboration"]["used"] is False
    assert report["unreadable_processes"][0]["evidence"]["identity_checks"]["snapshot_start_ticks_matches"] is False
    assert proof["member_gap_recheck"]["status"] == "pid_reused"
    assert proof["member_gap_recheck"]["attempt_count"] == 0


def test_owned_service_invocation_id_must_stay_stable(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6011)
    _process(root, pid=6011, start_ticks=10011, cgroup=facts["control_group"])
    invocations = iter((dict(facts), {**facts, "invocation_id": "f" * 32}))
    monkeypatch.setattr(task44_native_service, "_unit_facts", lambda unit: next(invocations))
    monkeypatch.setattr(task44_native_service.os, "sched_getaffinity", lambda pid: {0})

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6011, start_ticks=10011, cgroup_path=facts["control_group"]
        )],
    )

    assert report["status"] == "fail"
    assert report["owned_service_context"]["identity_checks"]["systemd_facts_match_invocation"] is False
    assert report["owned_service_excluded_pids"] == []


def test_owned_context_invocation_change_during_gap_recheck_fails_closed(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6010)
    _process(root, pid=6010, start_ticks=10010, cgroup=facts["control_group"])
    _process(root, pid=6020, start_ticks=10020, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    original_signature = task44_native_service._unit_identity_signature(facts)
    reads = 0

    def invocation_changes(unit, *, timeout_seconds):
        nonlocal reads
        reads += 1
        if reads == 1:
            return dict(original_signature)
        return {**original_signature, "invocation_id": "f" * 32}

    monkeypatch.setattr(
        task44_native_service, "_unit_identity_signature_with_timeout", invocation_changes
    )
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6010, start_ticks=10010, cgroup_path=facts["control_group"]),
            _candidate(6020, start_ticks=10020, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    assert reads == 2
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6020)
    assert proof["member_gap_recheck"]["status"] == "invocation_changed"
    assert proof["member_gap_recheck"]["attempt_count"] == 1
    assert "owned_service_invocation_identity_unverified" in report["failures"]


@pytest.mark.parametrize(
    ("first_conflict", "expected_status"),
    (("pid_reused_then_gone", "pid_reused"),
     ("cgroup_changed_then_restored", "cgroup_changed")),
)
def test_initial_identity_conflict_cannot_be_overridden_by_later_snapshot(
    tmp_path, monkeypatch, first_conflict, expected_status
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, cgroup = _owned_service(tmp_path, main_pid=6034)
    target_pid = 6035
    moved_group = "/user.slice/user-1000.slice/app.slice/other.service"
    _process(root, pid=6034, start_ticks=10034, cgroup=facts["control_group"])
    current_start = 20035 if first_conflict == "pid_reused_then_gone" else 10035
    current_group = facts["control_group"] if first_conflict == "pid_reused_then_gone" else moved_group
    _process(root, pid=target_pid, start_ticks=current_start, cgroup=current_group)
    (cgroup / "cgroup.procs").write_text("6034\n6035\n", encoding="ascii")
    _patch_owned_service(monkeypatch, facts)
    original_member = task44_native_service._owned_service_member

    def conflict_then_change(process, **kwargs):
        owned, proof = original_member(process, **kwargs)
        if int(process["pid"]) != target_pid:
            return owned, proof
        if first_conflict == "pid_reused_then_gone":
            for child in (root / str(target_pid)).iterdir():
                child.unlink()
            (root / str(target_pid)).rmdir()
            (cgroup / "cgroup.procs").write_text("6034\n", encoding="ascii")
        else:
            (root / str(target_pid) / "cgroup").write_text(
                f"0::{facts['control_group']}\n", encoding="utf-8"
            )
        return owned, proof

    monkeypatch.setattr(task44_native_service, "_owned_service_member", conflict_then_change)
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6034, start_ticks=10034, cgroup_path=facts["control_group"]),
            _candidate(target_pid, start_ticks=10035, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    assert report["stale_snapshot_confirmed_gone"] == []
    assert target_pid not in report["owned_service_excluded_pids"]
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == target_pid)
    assert proof["member_gap_recheck"]["status"] == expected_status
    assert proof["member_gap_recheck"]["attempt_count"] == 0



@pytest.mark.parametrize(
    "candidate_status",
    ("pid_reused", "cgroup_changed", "candidate_affinity_changed"),
)
def test_confirmed_candidate_drift_is_not_hidden_by_later_identity_query_timeout(
    tmp_path, monkeypatch, candidate_status
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6050)
    target_pid = 6051
    _process(root, pid=6050, start_ticks=10050, cgroup=facts["control_group"])
    _process(root, pid=target_pid, start_ticks=10051, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    signature = task44_native_service._unit_identity_signature(facts)
    systemd_reads = 0

    def stable_then_timeout(unit, *, timeout_seconds):
        nonlocal systemd_reads
        systemd_reads += 1
        if systemd_reads == 4:
            raise task44_native_service.subprocess.TimeoutExpired(
                ["systemctl", "--user", "show", unit], timeout_seconds
            )
        return dict(signature)

    def confirmed_drift(process, **kwargs):
        assert int(process["pid"]) == target_pid
        return {"status": candidate_status, "candidate": {"pid": target_pid}}

    monkeypatch.setattr(
        task44_native_service, "_unit_identity_signature_with_timeout", stable_then_timeout
    )
    monkeypatch.setattr(
        task44_native_service, "_owned_gap_candidate_observation", confirmed_drift
    )
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6050, start_ticks=10050, cgroup_path=facts["control_group"]),
            _candidate(target_pid, start_ticks=10051, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == target_pid)
    recheck = proof["member_gap_recheck"]
    assert recheck["status"] == candidate_status
    assert recheck["context_after"]["status"] == "identity_query_unavailable"
    assert recheck["attempt_count"] == 1
    assert recheck["systemd_query_count"] == 4
    assert recheck["max_systemd_query_count"] == 12
    assert recheck["systemd_query_count_max_per_attempt"] == 4
    assert recheck["max_systemd_query_wait_seconds"] == 3 * 4 * 0.25
    assert systemd_reads == 4


def test_first_confirmed_invocation_drift_is_not_hidden_by_query_timeout(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6052)
    target_pid = 6053
    _process(root, pid=6052, start_ticks=10052, cgroup=facts["control_group"])
    _process(root, pid=target_pid, start_ticks=10053, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    signature = task44_native_service._unit_identity_signature(facts)
    systemd_reads = 0

    def drift_then_timeout(unit, *, timeout_seconds):
        nonlocal systemd_reads
        systemd_reads += 1
        if systemd_reads == 1:
            return {**signature, "invocation_id": "f" * 32}
        raise task44_native_service.subprocess.TimeoutExpired(
            ["systemctl", "--user", "show", unit], timeout_seconds
        )

    monkeypatch.setattr(
        task44_native_service, "_unit_identity_signature_with_timeout", drift_then_timeout
    )
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6052, start_ticks=10052, cgroup_path=facts["control_group"]),
            _candidate(target_pid, start_ticks=10053, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == target_pid)
    recheck = proof["member_gap_recheck"]
    assert recheck["status"] == "invocation_changed"
    assert recheck["context_before"]["systemd_queries"][0]["status"] == "ok"
    assert recheck["attempt_count"] == 1
    assert recheck["systemd_query_count"] == 1
    assert systemd_reads == 1


def test_gone_candidate_identity_query_timeout_is_retried_with_fixed_budget(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6040)
    target_pid = 6041
    _process(root, pid=6040, start_ticks=10040, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    query_budgets = []
    signature = task44_native_service._unit_identity_signature(facts)

    def timeout_then_success(unit, *, timeout_seconds):
        query_budgets.append(timeout_seconds)
        if len(query_budgets) == 1:
            raise task44_native_service.subprocess.TimeoutExpired(
                ["systemctl", "--user", "show", unit], timeout_seconds
            )
        return dict(signature)

    monkeypatch.setattr(task44_native_service, "_unit_identity_signature_with_timeout", timeout_then_success)
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6040, start_ticks=10040, cgroup_path=facts["control_group"]),
            _candidate(target_pid, start_ticks=10041, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "pass"
    assert report["failures"] == []
    proof = next(row for row in report["stale_snapshot_confirmed_gone"] if row["pid"] == target_pid)
    recheck = proof["member_gap_recheck"]
    assert recheck["status"] == "gone"
    assert recheck["attempt_count"] == 2
    assert recheck["systemd_query_count"] == 2
    assert recheck["systemd_query_timeout_count"] == 1
    assert query_budgets == [
        task44_native_service._OWNED_MEMBER_GAP_SYSTEMD_QUERY_TIMEOUT_SECONDS,
        task44_native_service._OWNED_MEMBER_GAP_SYSTEMD_QUERY_TIMEOUT_SECONDS,
    ]
    assert [query["status"] for query in recheck["systemd_queries"]] == ["timeout", "ok"]


def test_exhausted_systemd_identity_query_retries_remain_unavailable(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6044)
    _process(root, pid=6044, start_ticks=10044, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)
    query_budgets = []

    def systemd_query_unavailable(unit, *, timeout_seconds):
        query_budgets.append(timeout_seconds)
        raise task44_native_service.subprocess.TimeoutExpired(
            ["systemctl", "--user", "show", unit], timeout_seconds
        )

    monkeypatch.setattr(
        task44_native_service,
        "_unit_identity_signature_with_timeout",
        systemd_query_unavailable,
    )
    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6044, start_ticks=10044, cgroup_path=facts["control_group"]),
            _candidate(6045, start_ticks=10045, cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "fail"
    proof = next(row for row in report["unverified_owned_members"] if row["pid"] == 6045)
    recheck = proof["member_gap_recheck"]
    assert recheck["status"] == "identity_query_unavailable"
    assert recheck["attempt_count"] == 3
    assert recheck["systemd_query_count"] == 3
    assert recheck["systemd_query_timeout_count"] == 3
    assert len(query_budgets) == 3
    assert all(
        timeout == task44_native_service._OWNED_MEMBER_GAP_SYSTEMD_QUERY_TIMEOUT_SECONDS
        for timeout in query_budgets
    )


def test_confirmed_zombie_exit_from_owned_cgroup_is_stale_after_context_recheck(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6046)
    target_pid = 6047
    _process(root, pid=6046, start_ticks=10046, cgroup=facts["control_group"])
    _process(root, pid=target_pid, start_ticks=10047, state="Z", cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0,
        proc_root=root,
        ignored_cgroup=facts["control_group"],
        owned_service_facts=facts,
        cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6046, start_ticks=10046, cgroup_path=facts["control_group"]),
            _candidate(6047, command="run_case.py", start_ticks=10047,
                       cgroup_path=facts["control_group"]),
        ],
    )

    assert report["status"] == "pass"
    proof = next(row for row in report["stale_snapshot_confirmed_gone"] if row["pid"] == target_pid)
    recheck = proof["member_gap_recheck"]
    assert recheck["status"] == "gone"
    assert recheck["candidate_exit_reason"] == "confirmed_zombie_exit"
    exit_confirmation = recheck["candidate"]["exit_confirmation"]
    assert exit_confirmation["kind"] == "stable_zombie_without_direct_membership"
    assert exit_confirmation["states"] == ["Z", "Z", "Z"]
    assert exit_confirmation["direct_membership_before"] is False
    assert exit_confirmation["direct_membership_after"] is False


def test_process_moved_out_of_owned_cgroup_is_not_exempt(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6002)
    moved_group = "/user.slice/user-1000.slice/app.slice/other.service"
    _process(root, pid=6002, start_ticks=10002, cgroup=moved_group)
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6002, start_ticks=10002, cgroup_path=moved_group
        )],
    )

    assert report["status"] == "fail"
    assert report["owned_service_excluded_pids"] == []
    assert [row["pid"] for row in report["unexpected_claims"]] == [6002]


def _b9_owned_service_fixture(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    (root / "1" / "status").write_text(
        "Name:\tsystemd\nCpus_allowed_list:\t0-9\n", encoding="utf-8"
    )
    unit = "task44-sample-boundary-plane-b9-r1-20261101.service"
    group = "/user.slice/user-1000.slice/user@1000.service/app.slice/" + unit
    cgroup_fs_root = tmp_path / "sys-fs-cgroup"
    cgroup = cgroup_fs_root / group.lstrip("/")
    cgroup.mkdir(parents=True)
    main_pid, cc1_pid = 251629, 266703
    (cgroup / "cgroup.procs").write_text(f"{main_pid}\n{cc1_pid}\n", encoding="ascii")
    facts = {
        "unit": unit,
        "invocation_id": "4cf69115f25442d6a9c5ecad8cae67b0",
        "control_group": group,
        "active_state": "active",
        "main_pid": main_pid,
        "cpu_affinity": "9",
    }
    _process(root, pid=main_pid, start_ticks=344406517, parent_pid=2818,
             affinity="9", command="task44_native_service.py", cgroup=group)
    _process(root, pid=cc1_pid, start_ticks=344751437, parent_pid=266702,
             affinity="9", command="cc1", cgroup=group)
    stat = root / str(cc1_pid) / "stat"
    stat.write_text(stat.read_text(encoding="ascii").replace("(python)", "(cc1)", 1), encoding="ascii")
    _patch_owned_service(monkeypatch, facts, affinity=9)
    candidates = [
        _candidate(main_pid, parent_pid=2818, command="task44_native_service.py",
                   start_ticks=344406517, cgroup_path=group),
        _candidate(cc1_pid, parent_pid=266702, command="cc1", snapshot_comm="cc1",
                   start_ticks=344751437, cgroup_path=group),
    ]
    return root, facts, cgroup_fs_root, candidates, cc1_pid


@pytest.mark.parametrize(
    ("context_member_before", "context_member_after"),
    ((True, True), (True, False), (False, True), (False, False)),
)
def test_b9_owned_cc1_requires_same_call_context_membership_and_stable_proc_identity(
    tmp_path, monkeypatch, context_member_before, context_member_after
):
    root, facts, cgroup_root, candidates, cc1_pid = _b9_owned_service_fixture(
        tmp_path, monkeypatch
    )
    original_read = task44_native_service._read_direct_cgroup_members
    reads = 0

    def discrepant_read(path):
        nonlocal reads
        reads += 1
        members = original_read(path)
        if reads == 1 and not context_member_before:
            members.discard(cc1_pid)
        if reads == 2 and not context_member_after:
            members.discard(cc1_pid)
        if reads in (5, 6):
            members.discard(cc1_pid)
        return members

    monkeypatch.setattr(task44_native_service, "_read_direct_cgroup_members", discrepant_read)
    report = _cpu_neighbor_gate(
        selected_cpu=9, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_root,
        numerical_processes=candidates,
    )

    proof = next(row for row in report["owned_service_member_proofs"] if row["pid"] == cc1_pid)
    assert reads >= 6
    assert report["owned_service_context"]["invocation_id"] == facts["invocation_id"]
    assert proof["checks"]["direct_membership_stable"] is False
    assert proof["invocation_context_corroboration"]["binding"]["unit"] == facts["unit"]
    assert proof["invocation_context_corroboration"]["binding"]["main_pid"] == facts["main_pid"]
    assert proof["invocation_context_corroboration"]["checks"][
        "candidate_context_membership_before"
    ] is context_member_before
    assert proof["invocation_context_corroboration"]["checks"][
        "candidate_context_membership_after"
    ] is context_member_after
    if context_member_before and context_member_after:
        assert report["status"] == "pass"
        assert cc1_pid in report["owned_service_excluded_pids"]
        assert proof["invocation_context_corroboration"]["used"] is False
        assert proof["invocation_context_corroboration"]["context_corroborated"] is True
        assert proof["ownership_decision"] == (
            "bounded_recheck_direct_membership_plus_stable_proc_identity"
        )
        assert proof["member_gap_recheck"]["status"] == "member_reconfirmed"
        assert report["unexpected_claims"] == []
    else:
        # A fresh direct-member proof may resolve the original snapshot gap;
        # context membership by itself is never enough to accept the PID.
        assert report["status"] == "pass"
        assert cc1_pid in report["owned_service_excluded_pids"]
        assert proof["invocation_context_corroboration"]["used"] is False
        assert proof["invocation_context_corroboration"]["context_corroborated"] is False
        assert proof["member_gap_recheck"]["status"] == "member_reconfirmed"


def test_context_membership_does_not_override_candidate_proc_cgroup_change(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_root, cgroup = _owned_service(tmp_path, main_pid=6030)
    candidate_pid = 6031
    moved_group = "/user.slice/user-1000.slice/app.slice/other.service"
    _process(root, pid=6030, start_ticks=10030, cgroup=facts["control_group"])
    _process(root, pid=candidate_pid, start_ticks=10031, affinity="0", cgroup=moved_group)
    (cgroup / "cgroup.procs").write_text("6030\n6031\n", encoding="ascii")
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_root,
        numerical_processes=[
            _candidate(6030, start_ticks=10030, cgroup_path=facts["control_group"]),
            _candidate(6031, start_ticks=10031, cgroup_path=facts["control_group"]),
        ],
    )

    proof = next(row for row in report["owned_service_member_proofs"] if row["pid"] == candidate_pid)
    assert report["status"] == "fail"
    assert candidate_pid not in report["owned_service_excluded_pids"]
    assert proof["invocation_context_corroboration"]["checks"][
        "candidate_context_membership_before"
    ] is True
    assert proof["invocation_context_corroboration"]["checks"][
        "candidate_proc_identity_stable"
    ] is False
    assert proof["invocation_context_corroboration"]["used"] is False
    assert proof["member_gap_recheck"]["status"] == "cgroup_changed"


def test_same_cgroup_path_without_direct_membership_is_not_exempt(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6012)
    _process(root, pid=6012, start_ticks=10012, cgroup=facts["control_group"])
    _process(root, pid=6013, start_ticks=10013, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6013, start_ticks=10013, cgroup_path=facts["control_group"]
        )],
    )

    assert report["status"] == "fail"
    assert report["owned_service_excluded_pids"] == []
    assert report["owned_service_member_proofs"][0]["checks"]["direct_membership_stable"] is False
    assert report["owned_service_member_proofs"][0]["member_gap_recheck"]["status"] == (
        "still_present_without_direct_membership"
    )
    assert report["owned_service_member_proofs"][0]["member_gap_recheck"]["attempt_count"] == 3
    assert report["owned_service_member_proofs"][0]["member_gap_recheck"]["max_attempts"] == 3
    assert [row["pid"] for row in report["unexpected_claims"]] == [6013]


def test_similar_cgroup_prefix_is_not_exempt(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6003)
    neighbor_group = f"{facts['control_group']}-extra"
    _process(root, pid=6003, start_ticks=10003, cgroup=facts["control_group"])
    _process(root, pid=6004, start_ticks=10004, command="other_solver.py", cgroup=neighbor_group)
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6003, start_ticks=10003, cgroup_path=facts["control_group"]),
            _candidate(6004, command="other_solver.py", start_ticks=10004, cgroup_path=neighbor_group),
        ],
    )

    assert report["status"] == "fail"
    assert report["owned_service_excluded_pids"] == [6003]
    assert [row["pid"] for row in report["unexpected_claims"]] == [6004]


def test_foreign_narrow_neighbor_is_still_rejected_beside_owned_member(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6005)
    foreign_group = "/user.slice/user-1000.slice/app.slice/foreign.service"
    _process(root, pid=6005, start_ticks=10005, cgroup=facts["control_group"])
    _process(root, pid=6006, start_ticks=10006, command="foreign_solver.py", cgroup=foreign_group)
    _patch_owned_service(monkeypatch, facts)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[
            _candidate(6005, start_ticks=10005, cgroup_path=facts["control_group"]),
            _candidate(6006, command="foreign_solver.py", start_ticks=10006, cgroup_path=foreign_group),
        ],
    )

    assert report["status"] == "fail"
    assert report["owned_service_excluded_pids"] == [6005]
    assert [row["pid"] for row in report["unexpected_claims"]] == [6006]


def test_owned_service_wrong_affinity_is_not_excused_by_ownership(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6007)
    _process(root, pid=6007, start_ticks=10007, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts, affinity=1)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6007, start_ticks=10007, cgroup_path=facts["control_group"]
        )],
    )

    assert report["status"] == "fail"
    assert report["owned_service_context"]["identity_verified"] is True
    assert report["owned_service_context"]["affinity_verified"] is False
    assert "owned_service_affinity_gate_failed" in report["failures"]


def test_owned_service_unknown_affinity_fails_closed(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, _ = _owned_service(tmp_path, main_pid=6008)
    _process(root, pid=6008, start_ticks=10008, cgroup=facts["control_group"])
    _patch_owned_service(monkeypatch, facts)

    def unreadable_affinity(pid):
        raise PermissionError("synthetic affinity read denied")

    monkeypatch.setattr(task44_native_service.os, "sched_getaffinity", unreadable_affinity)
    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=facts["control_group"],
        owned_service_facts=facts, cgroup_fs_root=cgroup_fs_root,
        numerical_processes=[_candidate(
            6008, start_ticks=10008, cgroup_path=facts["control_group"]
        )],
    )

    assert report["status"] == "fail"
    assert report["owned_service_context"]["identity_verified"] is True
    assert report["owned_service_context"]["affinity_verified"] is False
    assert report["owned_service_context"]["service_affinity_observation"]["stop"] is True


def test_cgroup_path_without_invocation_facts_cannot_hide_member(tmp_path):
    root = _proc_root(tmp_path)
    group = "/user.slice/user-1000.slice/app.slice/task44-sample-a.service"
    _process(root, pid=6009, start_ticks=10009, cgroup=group)

    report = _cpu_neighbor_gate(
        selected_cpu=0, proc_root=root, ignored_cgroup=group,
        numerical_processes=[_candidate(6009, start_ticks=10009, cgroup_path=group)],
    )

    assert report["status"] == "fail"
    assert "ignored_cgroup_requires_invocation_bound_service_facts" in report["failures"]
    assert [row["pid"] for row in report["unexpected_claims"]] == [6009]


def test_claim_identity_error_keeps_before_after_fields(tmp_path, monkeypatch):
    root = _proc_root(tmp_path)
    _process(root, pid=6010, start_ticks=10010, affinity="2", command="external.py")
    identities = iter((
        {"pid": 6010, "parent_pid": 1, "start_ticks": 10010, "state": "S", "comm": "python"},
        {"pid": 6010, "parent_pid": 1, "start_ticks": 10010, "state": "S", "comm": "time"},
    ))
    monkeypatch.setattr(task44_native_service, "_proc_identity", lambda pid, proc_root: next(identities))

    report = _cpu_neighbor_gate(
        selected_cpu=2, proc_root=root,
        numerical_processes=[_candidate(
            6010, command="external.py", snapshot_comm="python",
            start_ticks=10010, cgroup_path="/user.slice/user-1000.slice/session-4665.scope",
        )],
    )

    evidence = report["unreadable_processes"][0]["evidence"]
    assert report["status"] == "fail"
    assert evidence["identity_before"]["comm"] == "python"
    assert evidence["identity_after"]["comm"] == "time"
    assert evidence["identity_checks"]["comm_stable"] is False
    assert evidence["cgroup_before"] == evidence["cgroup_after"]


@pytest.mark.parametrize("ignored_cgroup", ("", "/"))
def test_empty_or_root_cgroup_cannot_hide_neighbor_processes(tmp_path, ignored_cgroup):
    with pytest.raises(RuntimeError, match="refuses an empty/root cgroup exclusion"):
        _cpu_neighbor_gate(
            selected_cpu=0,
            proc_root=_proc_root(tmp_path),
            ignored_cgroup=ignored_cgroup,
            numerical_processes=[],
        )


def test_dynamic_selected_cpu_rejects_a_narrow_neighbor_claim(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=5001,
        start_ticks=9010,
        affinity="2",
        command="another_solver.py",
    )

    report = _cpu_neighbor_gate(
        selected_cpu=2,
        proc_root=root,
        numerical_processes=[_candidate(5001, command="another_solver.py")],
    )

    assert report["status"] == "fail"
    assert report["selected_cpu"] == 2
    assert report["authorized_neighbor"] is None
    assert report["failures"] == ["unexpected_narrow_selected_cpu_affinity_neighbor"]


def test_cpu0_sharing_exception_does_not_apply_to_another_selected_cpu(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=AUTHORIZED_CPU0_NEIGHBOR["pid"],
        start_ticks=AUTHORIZED_CPU0_NEIGHBOR["start_ticks"],
    )

    report = _cpu_neighbor_gate(
        selected_cpu=1,
        proc_root=root,
        numerical_processes=[_candidate(AUTHORIZED_CPU0_NEIGHBOR["pid"])],
    )

    assert report["status"] == "pass"
    assert report["authorized_neighbor"] is None
    assert report["performance_not_isolated"] is False


def _selected_cpu_2_gate(root: Path, candidates: list[dict[str, object]]) -> dict[str, object]:
    return _cpu_neighbor_gate(
        selected_cpu=2, proc_root=root, numerical_processes=candidates
    )


def _narrow_candidate(
    pid: int,
    start_ticks: int,
    *,
    parent_pid: int = 1,
    snapshot_comm: str = "python",
) -> dict[str, object]:
    return _candidate(
        pid,
        parent_pid=parent_pid,
        start_ticks=start_ticks,
        command="another_solver.py",
        snapshot_comm=snapshot_comm,
        cgroup_path="/user.slice/user-1000.slice/session-4665.scope",
    )


def _patch_exact_service_guard(monkeypatch, *, own_cgroup: Path):
    from benchmarks import task034_wsl_resources
    from scripts import task44_service_startup

    unit = "task44-sample-monitor-test.service"
    cap_bytes = 1024
    facts = {
        "unit": unit,
        "active_state": "active",
        "control_group": "",
        "memory_max_bytes": cap_bytes,
        "cgroup_memory_max_bytes": cap_bytes,
        "swap_max_bytes": 0,
        "cgroup_swap_max_bytes": 0,
        "swap_current_bytes": 0,
        "cpu_affinity": "2",
        "system_call_filter": task44_native_service.TASK44_SYSTEM_CALL_FILTER,
        "system_call_error_number": "EPERM",
    }
    neighbor_gate = {
        "status": "fail",
        "failures": ["unexpected_narrow_selected_cpu_affinity_neighbor"],
        "unexpected_claims": [],
        "host_allowed_cpus": [0, 1, 2, 3],
        "performance_not_isolated": True,
    }
    monkeypatch.setattr(task44_native_service, "_active_units", lambda: [unit])
    monkeypatch.setattr(task44_native_service, "_task44_services", lambda _units: [facts])
    monkeypatch.setattr(task44_native_service, "_unit_facts", lambda _unit: facts)
    monkeypatch.setattr(
        task034_wsl_resources, "current_cgroup_path", lambda _pid: own_cgroup
    )
    monkeypatch.setattr(
        task034_wsl_resources,
        "cgroup_snapshot",
        lambda _pid: {
            "readable": True,
            "dedicated_job_cgroup": True,
            "swap_current_bytes": 0,
        },
    )
    monkeypatch.setattr(
        task44_native_service, "_cpu_neighbor_gate", lambda **_kwargs: neighbor_gate
    )
    monkeypatch.setattr(
        task44_service_startup,
        "observe_cgroup_cpu_affinity",
        lambda _cgroup, _cpus: {"stop": False, "service_pid_affinities": {}},
    )
    return unit, cap_bytes


def test_runtime_neighbor_monitor_accepts_verified_affinity_release(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6101, start_ticks=10101, affinity="2", command="another_solver.py")
    candidate = _narrow_candidate(6101, 10101)
    review = _CpuNeighborMonitor()
    startup_gate = {"performance_not_isolated": False}
    assert _combined_performance_not_isolated(startup_gate, review) is False

    initial = review.assess(_selected_cpu_2_gate(root, [candidate]),
                            selected_cpu=2, proc_root=root, now=100.0)
    assert _combined_performance_not_isolated(startup_gate, review) is True
    (root / "6101" / "status").write_text(
        "Name:\tpython\nCpus_allowed_list:\t0-3\n", encoding="utf-8"
    )
    cleared = review.assess(_selected_cpu_2_gate(root, []),
                            selected_cpu=2, proc_root=root, now=105.0)

    assert initial["status"] == "shared_cpu"
    assert initial["first_conflict_monotonic"] == 100.0
    assert cleared["status"] == "released"
    assert cleared["stop"] is False
    assert cleared["performance_not_isolated"] is True
    assert cleared["claims"][0]["last_observation"]["status"] == "released"
    assert review.first_conflict_monotonic is None
    assert _combined_performance_not_isolated(startup_gate, review) is True


def test_runtime_neighbor_monitor_accepts_verified_process_exit(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6102, start_ticks=10102, affinity="2", command="another_solver.py")
    candidate = _narrow_candidate(6102, 10102)
    review = _CpuNeighborMonitor()
    review.assess(_selected_cpu_2_gate(root, [candidate]),
                  selected_cpu=2, proc_root=root, now=100.0)
    for child in (root / "6102").iterdir():
        child.unlink()
    (root / "6102").rmdir()

    cleared = review.assess(_selected_cpu_2_gate(root, [candidate]),
                            selected_cpu=2, proc_root=root, now=105.0)

    assert cleared["status"] == "released"
    assert cleared["stop"] is False
    assert cleared["claims"][0]["last_observation"]["status"] == "gone"


def test_runtime_neighbor_continues_past_former_fifteen_second_deadline(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6103, start_ticks=10103, affinity="2", command="another_solver.py")
    candidate = _narrow_candidate(6103, 10103)
    review = _CpuNeighborMonitor()

    first = review.assess(_selected_cpu_2_gate(root, [candidate]),
                          selected_cpu=2, proc_root=root, now=100.0)
    after_former_deadline = review.assess(
        _selected_cpu_2_gate(root, [candidate]),
        selected_cpu=2, proc_root=root, now=10_100.0,
    )

    assert first["status"] == "shared_cpu" and first["stop"] is False
    assert after_former_deadline["status"] == "shared_cpu"
    assert after_former_deadline["stop"] is False
    assert after_former_deadline["first_conflict_monotonic"] == 100.0
    assert after_former_deadline["performance_not_isolated"] is True


def test_runtime_neighbor_replacement_does_not_renew_deadline(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6104, start_ticks=10104, affinity="2", command="another_solver.py")
    first_candidate = _narrow_candidate(6104, 10104)
    review = _CpuNeighborMonitor()
    review.assess(_selected_cpu_2_gate(root, [first_candidate]),
                  selected_cpu=2, proc_root=root, now=100.0)
    _process(root, pid=6105, start_ticks=10105, affinity="2", command="another_solver.py")

    both = review.assess(
        _selected_cpu_2_gate(root, [first_candidate, _narrow_candidate(6105, 10105)]),
        selected_cpu=2, proc_root=root, now=110.0,
    )
    sustained = review.assess(
        _selected_cpu_2_gate(root, [first_candidate, _narrow_candidate(6105, 10105)]),
        selected_cpu=2, proc_root=root, now=10_000.0,
    )

    assert both["status"] == "shared_cpu"
    assert both["first_conflict_monotonic"] == 100.0
    assert len(both["claims"]) == 2
    assert sustained["status"] == "shared_cpu" and sustained["stop"] is False
    assert len(sustained["claims"]) == 2


def test_runtime_neighbor_monitor_separates_reused_pid_from_old_claim(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6106, start_ticks=10106, affinity="2", command="another_solver.py")
    review = _CpuNeighborMonitor()
    review.assess(
        _selected_cpu_2_gate(root, [_narrow_candidate(6106, 10106)]),
        selected_cpu=2,
        proc_root=root,
        now=100.0,
    )
    for child in (root / "6106").iterdir():
        child.unlink()
    (root / "6106").rmdir()
    _process(root, pid=6106, start_ticks=99999, affinity="2", command="another_solver.py")

    result = review.assess(
        _selected_cpu_2_gate(root, [_narrow_candidate(6106, 99999)]),
        selected_cpu=2,
        proc_root=root,
        now=101.0,
    )

    assert result["status"] == "shared_cpu"
    assert result["stop"] is False
    assert result["performance_not_isolated"] is True
    assert [claim["identity"]["start_ticks"] for claim in result["claims"]] == [
        10106,
        99999,
    ]
    assert [claim["status"] for claim in result["claims"]] == ["replaced", "active"]
    assert result["claims"][0]["last_observation"]["status"] == "replaced"


def test_runtime_neighbor_monitor_records_b10_reparenting_without_stopping(tmp_path):
    root = _proc_root(tmp_path)
    pid = 276683
    start_ticks = 344964110
    _process(
        root,
        pid=pid,
        start_ticks=start_ticks,
        parent_pid=276682,
        affinity="2",
        command="another_solver.py",
    )
    review = _CpuNeighborMonitor()
    first = review.assess(
        _selected_cpu_2_gate(
            root, [_narrow_candidate(pid, start_ticks, parent_pid=276682)]
        ),
        selected_cpu=2,
        proc_root=root,
        now=100.0,
    )
    fields = ["S", "275870", *("0" for _ in range(17)), str(start_ticks)]
    (root / str(pid) / "stat").write_text(
        f"{pid} (python) {' '.join(fields)}\n", encoding="ascii"
    )

    current = review.assess(
        _selected_cpu_2_gate(
            root, [_narrow_candidate(pid, start_ticks, parent_pid=275870)]
        ),
        selected_cpu=2,
        proc_root=root,
        now=101.0,
    )

    assert first["status"] == "shared_cpu" and first["stop"] is False
    assert current["status"] == "shared_cpu"
    assert current["stop"] is False
    assert current["performance_not_isolated"] is True
    claim = current["claims"][0]
    assert claim["identity"] == {"pid": pid, "start_ticks": start_ticks}
    assert claim["first_observation"]["parent_pid"] == 276682
    assert claim["latest_candidate_observation"]["parent_pid"] == 275870
    lifecycle = claim["last_observation"]["evidence"]["lifecycle_changes"]["parent_pid"]
    assert lifecycle["changed_since_first_observation"] is True
    assert lifecycle["changed_during_read"] is False


def test_runtime_neighbor_monitor_records_exec_comm_change_without_stopping(tmp_path):
    root = _proc_root(tmp_path)
    pid = 6110
    start_ticks = 10110
    _process(
        root,
        pid=pid,
        start_ticks=start_ticks,
        affinity="2",
        command="another_solver.py",
    )
    review = _CpuNeighborMonitor()
    review.assess(
        _selected_cpu_2_gate(root, [_narrow_candidate(pid, start_ticks)]),
        selected_cpu=2,
        proc_root=root,
        now=100.0,
    )
    fields = ["S", "1", *("0" for _ in range(17)), str(start_ticks)]
    (root / str(pid) / "stat").write_text(
        f"{pid} (solver) {' '.join(fields)}\n", encoding="ascii"
    )

    current = review.assess(
        _selected_cpu_2_gate(
            root, [_narrow_candidate(pid, start_ticks, snapshot_comm="solver")]
        ),
        selected_cpu=2,
        proc_root=root,
        now=101.0,
    )

    assert current["status"] == "shared_cpu"
    assert current["stop"] is False
    assert current["claims"][0]["identity"] == {
        "pid": pid,
        "start_ticks": start_ticks,
    }
    lifecycle = current["claims"][0]["last_observation"]["evidence"]["lifecycle_changes"]["comm"]
    assert lifecycle["changed_since_first_observation"] is True
    assert lifecycle["changed_during_read"] is False


def test_runtime_neighbor_monitor_records_unreadable_identity_as_unknown(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6107, start_ticks=10107, affinity="2", command="another_solver.py")
    candidate = _narrow_candidate(6107, 10107)
    review = _CpuNeighborMonitor()
    review.assess(
        _selected_cpu_2_gate(root, [candidate]),
        selected_cpu=2,
        proc_root=root,
        now=100.0,
    )
    (root / "6107" / "status").unlink()

    result = review.assess(
        _selected_cpu_2_gate(root, []),
        selected_cpu=2,
        proc_root=root,
        now=101.0,
    )

    assert result["status"] == "unknown"
    assert result["stop"] is False
    assert result["performance_not_isolated"] is True
    assert result["diagnostic_uncertainty"]
    assert result["claims"][0]["observation_status"] == "unknown"
    assert result["claims"][0]["last_observation"]["status"] == "unknown"


def test_runtime_neighbor_monitor_keeps_owned_context_identity_hard(tmp_path):
    root = _proc_root(tmp_path)
    gate = _selected_cpu_2_gate(root, [])
    gate["owned_service_context"] = {
        "identity_verified": False,
        "affinity_verified": True,
        "failures": ["owned_service_invocation_identity_unverified"],
    }
    gate["unverified_owned_members"] = []
    review = _CpuNeighborMonitor()

    result = review.assess(
        gate,
        selected_cpu=2,
        proc_root=root,
        require_owned_context=True,
    )

    assert result["status"] == "hard_gate_failed"
    assert result["stop"] is True
    assert result["failures"] == ["owned_service_invocation_identity_unverified"]


@pytest.mark.parametrize(
    "hard_failure",
    [
        "service_memory_max_mismatch",
        "service_swap_nonzero_or_unreadable",
        "service_cgroup_identity_mismatch",
    ],
)
def test_runtime_neighbor_review_does_not_delay_unrelated_hard_gate(
    tmp_path, hard_failure
):
    from benchmarks.subreaper_watchdog import _external_guard_stop_reason

    root = _proc_root(tmp_path)
    _process(root, pid=6108, start_ticks=10108, affinity="2", command="another_solver.py")
    review = _CpuNeighborMonitor()

    result = review.assess(
        _selected_cpu_2_gate(root, [_narrow_candidate(6108, 10108)]),
        selected_cpu=2, proc_root=root, hard_failures=[hard_failure],
        now=100.0,
    )

    assert result["status"] == "hard_gate_failed"
    assert result["stop"] is True
    assert result["hard_failures"] == [hard_failure]
    assert review.first_conflict_monotonic is None
    waiting_facts = {"stop": False, "reason": None}
    assert _external_guard_stop_reason(
        "RESOURCE_CONTROLLED_STOP", waiting_facts
    ) == "RESOURCE_CONTROLLED_STOP"
    assert _external_guard_stop_reason(
        "MONITORING_FAILED", waiting_facts
    ) == "MONITORING_FAILED"


def test_neighbor_grace_closes_only_after_all_claims_release_then_starts_new_episode(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6109, start_ticks=10109, affinity="2", command="another_solver.py")
    candidate_a = _narrow_candidate(6109, 10109)
    review = _CpuNeighborMonitor()
    review.assess(_selected_cpu_2_gate(root, [candidate_a]),
                  selected_cpu=2, proc_root=root, now=0.0)
    for child in (root / "6109").iterdir():
        child.unlink()
    (root / "6109").rmdir()
    released_a = review.assess(_selected_cpu_2_gate(root, []),
                               selected_cpu=2, proc_root=root, now=5.0)
    _process(root, pid=6110, start_ticks=10110, affinity="2", command="another_solver.py")
    next_episode = review.assess(
        _selected_cpu_2_gate(root, [_narrow_candidate(6110, 10110)]),
        selected_cpu=2, proc_root=root, now=100.0,
    )
    before_new_deadline = review.assess(
        _selected_cpu_2_gate(root, [_narrow_candidate(6110, 10110)]),
        selected_cpu=2, proc_root=root, now=114.999,
    )

    assert released_a["status"] == "released"
    assert review.first_conflict_monotonic == 100.0
    assert next_episode["status"] == "shared_cpu"
    assert before_new_deadline["status"] == "shared_cpu"


def test_neighbor_monitor_tracks_replacement_claims_without_timeout(tmp_path):
    root = _proc_root(tmp_path)
    _process(root, pid=6111, start_ticks=10111, affinity="2", command="another_solver.py")
    candidate_a = _narrow_candidate(6111, 10111)
    review = _CpuNeighborMonitor()
    review.assess(_selected_cpu_2_gate(root, [candidate_a]),
                  selected_cpu=2, proc_root=root, now=0.0)
    _process(root, pid=6112, start_ticks=10112, affinity="2", command="another_solver.py")
    for child in (root / "6111").iterdir():
        child.unlink()
    (root / "6111").rmdir()
    candidate_b = _narrow_candidate(6112, 10112)

    still_shared = review.assess(
        _selected_cpu_2_gate(root, [candidate_b]), selected_cpu=2,
        proc_root=root, now=5.0,
    )
    sustained = review.assess(
        _selected_cpu_2_gate(root, [candidate_b]), selected_cpu=2,
        proc_root=root, now=10_000.0,
    )

    assert still_shared["status"] == "shared_cpu"
    assert still_shared["first_conflict_monotonic"] == 0.0
    assert [row["last_observation"]["status"] for row in still_shared["claims"]] == [
        "gone", "active"
    ]
    assert sustained["status"] == "shared_cpu" and sustained["stop"] is False


def test_default_neighbor_gate_fails_fast_and_watchdog_sleep_is_opt_in(tmp_path):
    from benchmarks.subreaper_watchdog import _external_guard_sleep_duration

    root = _proc_root(tmp_path)
    _process(root, pid=6113, start_ticks=10113, affinity="2", command="another_solver.py")
    strict_gate = _selected_cpu_2_gate(root, [_narrow_candidate(6113, 10113)])

    assert strict_gate["status"] == "fail"
    assert strict_gate["failures"] == ["unexpected_narrow_selected_cpu_affinity_neighbor"]
    assert _external_guard_sleep_duration(5.0, None, now=10.0) == 5.0
    assert _external_guard_sleep_duration(5.0, {}, now=10.0) == 5.0
    assert _external_guard_sleep_duration(
        5.0, {"cpu_neighbor_grace": {"status": "shared_cpu"}}, now=10.0
    ) == 5.0
    assert _external_guard_sleep_duration(
        5.0, {"next_poll_deadline_monotonic": 12.0}, now=10.0
    ) == 2.0
    assert _external_guard_sleep_duration(
        5.0, {"next_poll_deadline_monotonic": 9.0}, now=10.0
    ) == 0.0


def test_exact_service_startup_gate_still_rejects_cpu_neighbor(monkeypatch):
    unit, cap_bytes = _patch_exact_service_guard(
        monkeypatch, own_cgroup=Path("/sys/fs/cgroup")
    )

    result = task44_native_service._exact_service_guard(unit, cap_bytes, 1, {2})

    assert result["stop"] is True
    assert result["failures"] == ["selected_cpu_neighbor_gate_failed"]
    assert result["cpu_neighbor_grace"] is None


def test_runtime_cpu_monitor_does_not_hide_service_identity_failure(
    monkeypatch, tmp_path
):
    unit, cap_bytes = _patch_exact_service_guard(monkeypatch, own_cgroup=tmp_path)
    monitor = _CpuNeighborMonitor()

    result = task44_native_service._exact_service_guard(
        unit, cap_bytes, 1, {2}, cpu_neighbor_monitor=monitor
    )

    assert result["stop"] is True
    assert result["failures"] == ["service_cgroup_identity_mismatch"]
    assert result["cpu_neighbor_grace"]["status"] == "hard_gate_failed"
    assert monitor.first_conflict_monotonic is None


def test_runtime_inventory_failure_continues_only_with_fresh_exact_unit(
    monkeypatch,
):
    unit, cap_bytes = _patch_exact_service_guard(
        monkeypatch, own_cgroup=Path("/sys/fs/cgroup")
    )
    exact_facts = task44_native_service._unit_facts
    calls = []
    inventory_error = _B11_LIST_UNITS_ERROR

    def read_exact_unit(name):
        calls.append("exact_unit")
        return exact_facts(name)

    def fail_global_inventory():
        calls.append("global_inventory")
        raise RuntimeError(inventory_error)

    monkeypatch.setattr(task44_native_service, "_unit_facts", read_exact_unit)
    monkeypatch.setattr(
        task44_native_service, "_active_units", fail_global_inventory
    )
    monkeypatch.setattr(
        task44_native_service,
        "_task44_services",
        lambda *_args: pytest.fail("unknown inventory must not be treated as empty"),
    )
    monkeypatch.setattr(
        task44_native_service,
        "_cpu_neighbor_gate",
        lambda **_kwargs: {
            "status": "pass",
            "failures": [],
            "unexpected_claims": [],
            "host_allowed_cpus": [0, 1, 2, 3],
            "performance_not_isolated": False,
        },
    )
    monitor = _CpuNeighborMonitor()

    def clear_review(_gate, **kwargs):
        assert kwargs["hard_failures"] == []
        return {
            "stop": False,
            "status": "clear",
            "performance_not_isolated": False,
            "next_poll_deadline_monotonic": None,
        }

    monkeypatch.setattr(monitor, "assess", clear_review)
    result = task44_native_service._exact_service_guard(
        unit, cap_bytes, 1, {2}, cpu_neighbor_monitor=monitor
    )

    assert calls == ["exact_unit", "global_inventory"]
    assert result["stop"] is False
    assert result["unit_inventory_status"] == "unknown"
    assert result["unit_inventory_error"] == {
        "exception_type": "RuntimeError",
        "message": inventory_error,
    }
    assert result["active_user_services"] is None
    assert result["active_task44_services"] is None
    assert result["service"]["unit"] == unit


def test_runtime_inventory_failure_still_fails_closed_if_exact_unit_unavailable(
    monkeypatch,
):
    unit, cap_bytes = _patch_exact_service_guard(
        monkeypatch, own_cgroup=Path("/sys/fs/cgroup")
    )
    calls = []
    exact_error = "command failed: systemctl show exact unit: Transport endpoint is not connected"

    def fail_exact_unit(name):
        calls.append(name)
        raise RuntimeError(exact_error)

    monkeypatch.setattr(task44_native_service, "_unit_facts", fail_exact_unit)
    monkeypatch.setattr(
        task44_native_service,
        "_active_units",
        lambda: pytest.fail("do not query global inventory without exact identity"),
    )
    result = task44_native_service._exact_service_guard(
        unit, cap_bytes, 1, {2}, cpu_neighbor_monitor=_CpuNeighborMonitor()
    )

    assert calls == [unit]
    assert result["stop"] is True
    assert result["reason"] == "MONITORING_FAILED"
    assert result["exception_message"] == exact_error


def test_runtime_inventory_failure_does_not_hide_hard_swap_gate(
    monkeypatch,
):
    unit, cap_bytes = _patch_exact_service_guard(
        monkeypatch, own_cgroup=Path("/sys/fs/cgroup")
    )
    exact_facts = task44_native_service._unit_facts

    def facts_with_nonzero_swap(name):
        facts = exact_facts(name)
        facts["swap_current_bytes"] = 1
        return facts

    def fail_global_inventory():
        raise RuntimeError("list-units unavailable")

    monkeypatch.setattr(
        task44_native_service, "_unit_facts", facts_with_nonzero_swap
    )
    monkeypatch.setattr(
        task44_native_service, "_active_units", fail_global_inventory
    )
    monitor = _CpuNeighborMonitor()

    result = task44_native_service._exact_service_guard(
        unit, cap_bytes, 1, {2}, cpu_neighbor_monitor=monitor
    )

    assert result["unit_inventory_status"] == "unknown"
    assert result["stop"] is True
    assert "service_swap_nonzero_or_unreadable" in result["failures"]
    assert result["cpu_neighbor_grace"]["status"] == "hard_gate_failed"


def test_startup_service_guard_fails_closed_when_global_inventory_unavailable(
    monkeypatch,
):
    unit, cap_bytes = _patch_exact_service_guard(
        monkeypatch, own_cgroup=Path("/sys/fs/cgroup")
    )

    def fail_global_inventory():
        raise RuntimeError("list-units unavailable")

    monkeypatch.setattr(
        task44_native_service, "_active_units", fail_global_inventory
    )
    monkeypatch.setattr(
        task44_native_service,
        "_unit_facts",
        lambda *_args: pytest.fail("startup inventory failure must stop first"),
    )
    result = task44_native_service._exact_service_guard(
        unit, cap_bytes, 1, {2}
    )

    assert result["stop"] is True
    assert result["reason"] == "MONITORING_FAILED"
    assert "list-units unavailable" in result["exception_message"]


def test_startup_service_guard_keeps_concurrency_limit_when_inventory_available(
    monkeypatch,
):
    unit, cap_bytes = _patch_exact_service_guard(
        monkeypatch, own_cgroup=Path("/sys/fs/cgroup")
    )
    exact_facts = task44_native_service._unit_facts
    own_facts = exact_facts(unit)
    second_service = {**own_facts, "unit": "task44-sample-other.service"}
    monkeypatch.setattr(
        task44_native_service,
        "_task44_services",
        lambda _units: [own_facts, second_service],
    )

    result = task44_native_service._exact_service_guard(
        unit, cap_bytes, 1, {2}
    )

    assert result["stop"] is True
    assert "task44_concurrency_gate_failed" in result["failures"]
