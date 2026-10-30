from __future__ import annotations

from pathlib import Path

import pytest

from scripts.task44_native_service import (
    AUTHORIZED_CPU0_NEIGHBOR,
    _cpu0_neighbor_gate,
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
) -> dict[str, object]:
    return {
        "pid": pid,
        "ppid": parent_pid,
        "comm": "python",
        "command": f"python /opt/Metrology/{command}",
    }


def test_authorized_supervisor_is_the_only_cpu0_claim(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=AUTHORIZED_CPU0_NEIGHBOR["pid"],
        start_ticks=AUTHORIZED_CPU0_NEIGHBOR["start_ticks"],
    )

    report = _cpu0_neighbor_gate(
        proc_root=root,
        numerical_processes=[_candidate(AUTHORIZED_CPU0_NEIGHBOR["pid"])],
    )

    assert report["status"] == "pass"
    assert report["performance_not_isolated"] is True
    assert report["authorized_neighbor"]["pid"] == AUTHORIZED_CPU0_NEIGHBOR["pid"]
    assert report["unexpected_claims"] == []


def test_no_neighbor_is_allowed_but_does_not_claim_shared_performance(tmp_path):
    report = _cpu0_neighbor_gate(proc_root=_proc_root(tmp_path), numerical_processes=[])

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

    report = _cpu0_neighbor_gate(
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

    report = _cpu0_neighbor_gate(
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

    report = _cpu0_neighbor_gate(
        proc_root=root,
        numerical_processes=[
            _candidate(AUTHORIZED_CPU0_NEIGHBOR["pid"]),
            _candidate(5000, command="another_solver.py"),
        ],
    )

    assert report["status"] == "fail"
    assert report["failures"] == ["unexpected_narrow_cpu0_affinity_neighbor"]
    assert [row["pid"] for row in report["unexpected_claims"]] == [5000]


def test_task44_service_cgroup_is_not_misclassified_as_a_neighbor(tmp_path):
    root = _proc_root(tmp_path)
    _process(
        root,
        pid=6000,
        start_ticks=10000,
        command="run_case.py",
        cgroup="/user.slice/user-1000.slice/app.slice/task44-sample-a.service",
    )

    report = _cpu0_neighbor_gate(
        proc_root=root,
        ignored_cgroup="/user.slice/user-1000.slice/app.slice/task44-sample-a.service",
        numerical_processes=[_candidate(6000, command="run_case.py")],
    )

    assert report["status"] == "pass"
    assert report["narrow_cpu0_affinity_claims"] == []


@pytest.mark.parametrize("ignored_cgroup", ("", "/"))
def test_empty_or_root_cgroup_cannot_hide_neighbor_processes(tmp_path, ignored_cgroup):
    with pytest.raises(RuntimeError, match="refuses an empty/root cgroup exclusion"):
        _cpu0_neighbor_gate(
            proc_root=_proc_root(tmp_path),
            ignored_cgroup=ignored_cgroup,
            numerical_processes=[],
        )
