from __future__ import annotations

from pathlib import Path

import pytest

import scripts.task44_native_service as task44_native_service
from scripts.task44_native_service import (
    AUTHORIZED_CPU0_NEIGHBOR,
    _cpu_neighbor_gate,
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
    parent_pid: int = 1,
    affinity: str = "0",
    command: str = AUTHORIZED_CPU0_NEIGHBOR["command_basename"],
    cgroup: str = "/user.slice/user-1000.slice/session-4665.scope",
) -> None:
    process = root / str(pid)
    process.mkdir()
    fields = ["S", str(parent_pid), *("0" for _ in range(17)), str(start_ticks)]
    (process / "stat").write_text(
        f"{pid} (python) {' '.join(fields)}\n", encoding="ascii"
    )
    (process / "status").write_text(
        f"Name:\tpython\nCpus_allowed_list:\t{affinity}\n", encoding="utf-8"
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


def _owned_service(tmp_path: Path, *, main_pid: int) -> tuple[dict[str, object], Path, Path]:
    unit = "task44-sample-owned.service"
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


def test_owned_service_member_with_exec_comm_transition_is_excluded_and_affinity_is_checked(
    tmp_path, monkeypatch
):
    root = _proc_root(tmp_path)
    facts, cgroup_fs_root, cgroup = _owned_service(tmp_path, main_pid=6000)
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
    assert report["owned_service_member_proofs"][0]["checks"]["candidate_start_ticks_match_both_reads"] is False
    assert report["unreadable_processes"][0]["evidence"]["identity_checks"]["snapshot_start_ticks_matches"] is False


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
