"""Task44-only service binding around the public runner and shared watchdog."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GIB = 1024**3
HOST_RESERVE_BYTES = 384 * GIB
INITIAL_CAP_BYTES = 128 * GIB
JOB_BUFFER_BYTES = 8 * GIB
BRANCH = "task44_sixlayer_surrogate_0p7nm"
RUNTIME_PROBE_SCHEMA = "task44_isolated_runtime_facts_v2"
TASK44_RUNTIME_CONTROLS = {
    "openmpi_pml": "ob1",
    "hwloc_components": "-x86",
    "hwloc_base_binding_policy": "none",
}
TASK44_SYSTEM_CALL_FILTER = "~sched_setaffinity"
TASK44_SYSTEM_CALL_ERROR_NUMBER = "EPERM"
PREFLIGHT_CAP_BYTES = 4 * GIB
MAX_IDLE_CPU_BUSY_PERCENT = 20.0
CPU_SAMPLE_SECONDS = 0.5
AUTHORIZED_CPU0_NEIGHBOR = {
    "pid": 3893658,
    "start_ticks": 324107938,
    "parent_pid": 1,
    "command_basename": "supervise_authorized_CPU_release_v3_20261030.py",
    "cpu_affinity": [0],
}
_THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
)




def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def verify_task44_root(repo_root: Path, environ: Mapping[str, str]) -> None:
    if environ.get("MYFENICS_NATIVE_COMPLEX_ENV") != "1":
        raise RuntimeError("Task44 execution requires the native complex ABI activation")
    if environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") is not None:
        raise RuntimeError("Task44 native execution rejects a stale WSL activation marker")
    configured = environ.get("MYFENICS_TASK44_ROOT")
    if not configured or Path(configured).resolve(strict=True) != repo_root.resolve(strict=True):
        raise RuntimeError("MYFENICS_TASK44_ROOT does not identify this Task44 worktree")


def _run(argv: list[str], *, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            argv, cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "")
        raise RuntimeError(f"command failed: {argv[0]}: {detail or exc}") from exc


def _active_units() -> list[str]:
    output = _run([
        "systemctl", "--user", "list-units", "--type=service", "--state=running",
        "--no-legend", "--no-pager",
    ])
    return sorted({line.split()[0] for line in output.splitlines() if line.split()})


def _unit_facts(unit: str) -> dict[str, Any]:
    output = _run([
        "systemctl", "--user", "show", unit, "--no-pager",
        "-p", "ControlGroup", "-p", "MemoryMax", "-p", "MemorySwapMax",
        "-p", "ActiveState", "-p", "CPUAffinity", "-p", "MainPID",
        "-p", "InvocationID", "-p", "Restart", "-p", "KillMode",
        "-p", "SystemCallFilter", "-p", "SystemCallErrorNumber",
    ])
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    if set(values) != {
        "ControlGroup", "MemoryMax", "MemorySwapMax", "ActiveState", "CPUAffinity",
        "MainPID", "InvocationID", "Restart", "KillMode",
        "SystemCallFilter", "SystemCallErrorNumber",
    }:
        raise RuntimeError(f"systemd returned incomplete properties for {unit}")
    cgroup = Path("/sys/fs/cgroup") / values["ControlGroup"].lstrip("/")
    try:
        memory_current = int((cgroup / "memory.current").read_text().strip())
        memory_max = int((cgroup / "memory.max").read_text().strip())
        swap_current = int((cgroup / "memory.swap.current").read_text().strip())
        swap_max_text = (cgroup / "memory.swap.max").read_text().strip()
        swap_max = None if swap_max_text == "max" else int(swap_max_text)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read dedicated cgroup for {unit}: {exc}") from exc
    if values["MemoryMax"] == "infinity" or values["MemorySwapMax"] == "infinity":
        raise RuntimeError(f"Task44 service {unit} has an unlimited memory property")
    return {
        "unit": unit,
        "active_state": values["ActiveState"],
        "main_pid": int(values["MainPID"]),
        "invocation_id": values["InvocationID"],
        "restart": values["Restart"],
        "kill_mode": values["KillMode"],
        "cpu_affinity": values["CPUAffinity"],
        "system_call_filter": values["SystemCallFilter"],
        "system_call_error_number": values["SystemCallErrorNumber"],
        "control_group": values["ControlGroup"],
        "memory_max_bytes": int(values["MemoryMax"]),
        "memory_current_bytes": memory_current,
        "cgroup_memory_max_bytes": memory_max,
        "swap_max_bytes": int(values["MemorySwapMax"]),
        "cgroup_swap_max_bytes": swap_max,
        "swap_current_bytes": swap_current,
    }


def _parse_cpu_list(value: str) -> set[int]:
    result: set[int] = set()
    for token in value.replace(",", " ").split():
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise RuntimeError(f"invalid CPU affinity range: {token}")
            result.update(range(start, end + 1))
        else:
            result.add(int(token))
    return result


def _status_fields(path: Path) -> dict[str, str]:
    return {
        key: value.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if ":" in line
        for key, value in (line.split(":", 1),)
    }


def _host_allowed_cpus(proc_root: Path) -> tuple[set[int], str]:
    host_comm = (proc_root / "1/comm").read_text(encoding="utf-8").strip()
    if "systemd" not in host_comm.lower():
        raise RuntimeError(
            f"Task44 CPU gate requires the native host PID namespace; PID1 is {host_comm!r}"
        )
    host_status = _status_fields(proc_root / "1/status")
    host_cpus = _parse_cpu_list(host_status.get("Cpus_allowed_list", ""))
    if not host_cpus:
        raise RuntimeError("native host PID1 has an empty allowed CPU mask")
    return host_cpus, host_comm


def _proc_identity(pid: int, proc_root: Path) -> dict[str, Any]:
    process_root = proc_root / str(pid)
    stat = (process_root / "stat").read_text(encoding="ascii")
    close = stat.rfind(")")
    fields = stat[close + 2 :].split()
    return {
        "pid": pid,
        "parent_pid": int(fields[1]),
        "start_ticks": int(fields[19]),
        "state": fields[0],
        "comm": stat[stat.find("(") + 1 : close],
    }


def _proc_cpu_claim(
    process: Mapping[str, Any], proc_root: Path, host_cpus: set[int], selected_cpu: int
) -> dict[str, Any] | None:
    pid = int(process["pid"])
    process_root = proc_root / str(pid)
    before = _proc_identity(pid, proc_root)
    if before["state"] in {"Z", "X"}:
        return None
    status = _status_fields(process_root / "status")
    cpu_list = status.get("Cpus_allowed_list")
    if not cpu_list:
        raise RuntimeError(f"cannot read CPU affinity for process {pid}")
    affinity = _parse_cpu_list(cpu_list)
    authorized_pid = selected_cpu == 0 and pid == AUTHORIZED_CPU0_NEIGHBOR["pid"]
    narrow_selected_cpu_claim = selected_cpu in affinity and affinity != host_cpus
    if not narrow_selected_cpu_claim and not authorized_pid:
        return None
    command_bytes = (process_root / "cmdline").read_bytes().split(b"\0")
    argv = [part.decode("utf-8", errors="replace") for part in command_bytes if part]
    command_basename = next(
        (Path(part).name for part in argv if part.endswith(".py")),
        Path(argv[0]).name if argv else before["comm"],
    )
    cgroup = (process_root / "cgroup").read_text(encoding="utf-8").strip()
    after = _proc_identity(pid, proc_root)
    after_status = _status_fields(process_root / "status")
    if (
        before["start_ticks"] != after["start_ticks"]
        or before["parent_pid"] != after["parent_pid"]
        or before["comm"] != after["comm"]
        or after_status.get("Cpus_allowed_list") != cpu_list
        or int(process.get("ppid", before["parent_pid"])) != before["parent_pid"]
        or str(process.get("comm", before["comm"])) != before["comm"]
    ):
        raise RuntimeError(
            f"process identity or affinity changed while checking CPU{selected_cpu} claim {pid}"
        )
    return {
        **before,
        "command_basename": command_basename,
        "cpu_affinity": sorted(affinity),
        "narrow_selected_cpu_claim": narrow_selected_cpu_claim,
        "cgroup": "/" + cgroup.split(":", 2)[-1].lstrip("/"),
    }


def _cpu_neighbor_gate(
    *,
    selected_cpu: int,
    proc_root: Path = Path("/proc"),
    ignored_pids: set[int] | None = None,
    ignored_cgroup: str | None = None,
    numerical_processes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if ignored_cgroup is not None and not ignored_cgroup.strip("/"):
        raise RuntimeError("Task44 CPU neighbor gate refuses an empty/root cgroup exclusion")
    host_cpus, host_comm = _host_allowed_cpus(proc_root)
    ignored = ignored_pids or set()
    claims: list[dict[str, Any]] = []
    unreadable: list[dict[str, Any]] = []
    candidates = _numerical_processes() if numerical_processes is None else numerical_processes
    candidates_by_pid = {int(process["pid"]): process for process in candidates}
    authorized_pid = int(AUTHORIZED_CPU0_NEIGHBOR["pid"]) if selected_cpu == 0 else None
    if (
        authorized_pid is not None
        and authorized_pid not in candidates_by_pid
        and (proc_root / str(authorized_pid)).exists()
    ):
        candidates_by_pid[authorized_pid] = {"pid": authorized_pid}
    observed: list[dict[str, Any]] = []
    for process in candidates_by_pid.values():
        pid = int(process["pid"])
        if pid in ignored:
            continue
        try:
            row = _proc_cpu_claim(process, proc_root, host_cpus, selected_cpu)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, RuntimeError) as exc:
            if not (proc_root / str(pid)).exists():
                continue
            unreadable.append({"pid": pid, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if row is None:
            continue
        ignored_path = "/" + ignored_cgroup.lstrip("/") if ignored_cgroup else None
        if ignored_path and (
            row["cgroup"] == ignored_path
            or row["cgroup"].startswith(ignored_path.rstrip("/") + "/")
        ):
            continue
        observed.append(row)
    claims = [row for row in observed if row["narrow_selected_cpu_claim"]]
    authorized = [
        row for row in claims
        if all(row.get(key) == expected for key, expected in AUTHORIZED_CPU0_NEIGHBOR.items())
    ]
    identity_conflicts = [
        row for row in observed
        if row["pid"] == authorized_pid
        and not all(
            row.get(key) == expected
            for key, expected in AUTHORIZED_CPU0_NEIGHBOR.items()
        )
    ]
    unexpected = [
        row for row in claims
        if row not in authorized and row["pid"] != authorized_pid
    ]
    unexpected.extend(identity_conflicts)
    failures = []
    if len(authorized) > 1:
        failures.append("authorized_cpu0_neighbor_identity_duplicated")
    if unexpected:
        failures.append("unexpected_narrow_selected_cpu_affinity_neighbor")
    if identity_conflicts:
        failures.append("authorized_cpu0_pid_identity_mismatch")
    if unreadable:
        failures.append("selected_cpu_neighbor_process_identity_unreadable")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "selected_cpu": selected_cpu,
        "host_pid1_comm": host_comm,
        "host_allowed_cpus": sorted(host_cpus),
        "authorized_neighbor": authorized[0] if authorized else None,
        "authorized_pid_identity_conflicts": identity_conflicts,
        "narrow_selected_cpu_affinity_claims": claims,
        "unexpected_claims": unexpected,
        "unreadable_processes": unreadable,
        "performance_not_isolated": bool(authorized),
    }


def _require_task44_cpu(cpu_affinity: set[int]) -> None:
    if len(cpu_affinity) != 1:
        raise RuntimeError(
            "Task44 one-rank MPI execution requires affinity to exactly one selected CPU"
        )


def _require_sched_setaffinity_eperm(expected_cpus: set[int]) -> dict[str, Any]:
    actual_cpus = set(os.sched_getaffinity(0))
    if actual_cpus != expected_cpus:
        raise RuntimeError(
            f"Task44 process affinity mismatch: expected={sorted(expected_cpus)}, "
            f"actual={sorted(actual_cpus)}"
        )
    try:
        os.sched_setaffinity(0, actual_cpus)
    except OSError as exc:
        if exc.errno != errno.EPERM:
            raise RuntimeError(
                f"same-mask sched_setaffinity failed with errno {exc.errno}, expected EPERM"
            ) from exc
    else:
        raise RuntimeError("same-mask sched_setaffinity succeeded despite the Task44 seccomp gate")
    unchanged_cpus = set(os.sched_getaffinity(0))
    if unchanged_cpus != expected_cpus:
        raise RuntimeError(
            f"Task44 seccomp denial changed the process CPU mask: {sorted(unchanged_cpus)}"
        )
    return {
        "status": "pass",
        "requested_cpu_affinity": sorted(actual_cpus),
        "actual_cpu_affinity": sorted(unchanged_cpus),
        "denied_syscall": "sched_setaffinity",
        "errno": "EPERM",
    }


def _verify_filtered_unit(
    unit: str, *, expected_cpus: set[int], cap_bytes: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    from benchmarks.task034_wsl_resources import current_cgroup_path

    facts = _unit_facts(unit)
    expected_cgroup = Path("/sys/fs/cgroup") / facts["control_group"].lstrip("/")
    own_cgroup = current_cgroup_path(os.getpid())
    error_number = facts["system_call_error_number"]
    if error_number == str(errno.EPERM):
        error_number = "EPERM"
    if (
        facts["main_pid"] != os.getpid()
        or facts["active_state"] != "active"
        or facts["restart"] != "no"
        or facts["kill_mode"] != "control-group"
        or facts["memory_max_bytes"] != cap_bytes
        or facts["cgroup_memory_max_bytes"] != cap_bytes
        or facts["swap_max_bytes"] != 0
        or facts["cgroup_swap_max_bytes"] != 0
        or facts["swap_current_bytes"] != 0
        or _parse_cpu_list(facts["cpu_affinity"]) != expected_cpus
        or facts["system_call_filter"].split() != [TASK44_SYSTEM_CALL_FILTER]
        or error_number != TASK44_SYSTEM_CALL_ERROR_NUMBER
        or own_cgroup is None
        or expected_cgroup.resolve(strict=True) != own_cgroup.resolve(strict=True)
    ):
        raise RuntimeError(f"Task44 filtered unit identity or seccomp properties mismatch: {facts}")
    syscall_test = _require_sched_setaffinity_eperm(expected_cpus)
    return facts, syscall_test


def _pid_start_ticks(pid: int) -> int:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    return int(stat[stat.rfind(")") + 2 :].split()[19])


def _write_service_identity(
    unit: str, repo_root: Path, expected_cpus: set[int], cap_bytes: int,
    native_environment: Mapping[str, Any],
    cpu_neighbor_gate: Mapping[str, Any],
    seccomp_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import current_cgroup_path

    facts = _unit_facts(unit)
    own_cpus = set(os.sched_getaffinity(0))
    own_cgroup = current_cgroup_path(os.getpid())
    expected_cgroup = Path("/sys/fs/cgroup") / facts["control_group"].lstrip("/")
    if (
        facts["main_pid"] != os.getpid()
        or not facts["invocation_id"]
        or facts["active_state"] != "active"
        or facts["restart"] != "no"
        or facts["kill_mode"] != "control-group"
        or facts["memory_max_bytes"] != cap_bytes
        or facts["cgroup_memory_max_bytes"] != cap_bytes
        or facts["swap_max_bytes"] != 0
        or facts["cgroup_swap_max_bytes"] != 0
        or facts["swap_current_bytes"] != 0
        or _parse_cpu_list(facts["cpu_affinity"]) != expected_cpus
        or facts["system_call_filter"].split() != [TASK44_SYSTEM_CALL_FILTER]
        or facts["system_call_error_number"] not in {"EPERM", str(errno.EPERM)}
        or own_cpus != expected_cpus
        or own_cgroup is None
        or expected_cgroup.resolve(strict=True) != own_cgroup.resolve(strict=True)
    ):
        raise RuntimeError(f"Task44 service process identity does not match its unit: {facts}")
    native = native_environment.get("native_complex_identity")
    probe = native_environment.get("isolated_runtime_probe")
    runtime_syscall_test = native_environment.get("sched_setaffinity_filter_test")
    if (
        not isinstance(native, dict)
        or native.get("task44_runtime_controls") != TASK44_RUNTIME_CONTROLS
        or not isinstance(probe, dict)
        or probe.get("exit_code") != 0
        or not isinstance(probe.get("facts_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", probe["facts_sha256"])
        or not isinstance(runtime_syscall_test, dict)
        or runtime_syscall_test.get("status") != "pass"
        or runtime_syscall_test.get("errno") != "EPERM"
        or cpu_neighbor_gate.get("status") != "pass"
        or seccomp_receipt.get("sched_setaffinity_filter_test", {}).get("status") != "pass"
    ):
        raise RuntimeError("Task44 service identity is missing its qualified isolated ABI probe receipt")
    receipt = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "service_unit": unit,
        "main_pid": os.getpid(),
        "main_pid_start_ticks": _pid_start_ticks(os.getpid()),
        "invocation_id": facts["invocation_id"],
        "control_group": facts["control_group"],
        "active_state": facts["active_state"],
        "memory_max_bytes": facts["memory_max_bytes"],
        "memory_swap_max_bytes": facts["swap_max_bytes"],
        "restart": facts["restart"],
        "kill_mode": facts["kill_mode"],
        "system_call_filter": facts["system_call_filter"],
        "system_call_error_number": facts["system_call_error_number"],
        "sched_setaffinity_filter_test": dict(
            seccomp_receipt["sched_setaffinity_filter_test"]
        ),
        "cpu_affinity": sorted(expected_cpus),
        "actual_process_cpu_affinity": sorted(own_cpus),
        "working_directory": str(repo_root),
        "isolated_runtime_probe": {
            "exit_code": probe["exit_code"],
            "facts_sha256": probe["facts_sha256"],
            "sched_setaffinity_filter_test": runtime_syscall_test,
            "module_paths": native["module_paths"],
            "runtime_controls": native["task44_runtime_controls"],
        },
        "cpu_neighbor_gate": dict(cpu_neighbor_gate),
        "performance_not_isolated": bool(
            cpu_neighbor_gate.get("performance_not_isolated")
        ),
    }
    path = repo_root / "benchmarks/artifacts/task44_native_services" / unit / "service_identity.json"
    _atomic_write_json(path, receipt)
    return receipt


def _task44_services(units: list[str]) -> list[dict[str, Any]]:
    return [
        _unit_facts(unit)
        for unit in units
        if unit.startswith("task44-sample-") and unit.endswith(".service")
    ]


def _numerical_processes() -> list[dict[str, Any]]:
    text = _run(["ps", "-eo", "pid=,ppid=,comm=,args="])
    marker = re.compile(
        r"python|mpiexec|mpirun|dolfinx|petsc|slepc|gmsh|fenics|pytest|"
        r"supervise_authorized_cpu_release",
        re.IGNORECASE,
    )
    result = []
    for line in text.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) < 3:
            continue
        command = fields[3] if len(fields) == 4 else fields[2]
        if marker.search(f"{fields[2]} {command}"):
            try:
                status = Path(f"/proc/{fields[0]}/status").read_text(encoding="utf-8")
                allowed = next(
                    (line.split(":", 1)[1].strip() for line in status.splitlines()
                     if line.startswith("Cpus_allowed_list:")),
                    None,
                )
            except OSError:
                allowed = None
            result.append({
                "pid": int(fields[0]), "ppid": int(fields[1]),
                "comm": fields[2], "command": command[:240],
                "cpus_allowed_list": allowed,
            })
    return result


def _cpu_counters(path: Path = Path("/proc/stat")) -> dict[int, tuple[int, int]]:
    counters = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.match(r"^cpu(\d+)\s+(.+)$", line)
        if not match:
            continue
        values = [int(value) for value in match.group(2).split()[:8]]
        if len(values) < 4:
            continue
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        counters[int(match.group(1))] = (total, idle)
    if not counters:
        raise RuntimeError("cannot read per-CPU counters from /proc/stat")
    return counters


def _cpu_busy_percentages(
    before: Mapping[int, tuple[int, int]], after: Mapping[int, tuple[int, int]]
) -> dict[int, float]:
    result = {}
    for cpu in sorted(before.keys() & after.keys()):
        total = after[cpu][0] - before[cpu][0]
        idle = after[cpu][1] - before[cpu][1]
        if total <= 0 or idle < 0 or idle > total:
            continue
        result[cpu] = 100.0 * (total - idle) / total
    return result


def select_idle_cpu(*, sample_seconds: float = CPU_SAMPLE_SECONDS) -> dict[str, Any]:
    """Choose the least-busy CPU below the task's strict 20% admission threshold."""
    proc_root = Path("/proc")
    host_cpus, host_comm = _host_allowed_cpus(proc_root)
    own_pid = os.getpid()
    excluded_claims = []
    blocked_cpus: set[int] = set()
    for process in _numerical_processes():
        pid = int(process["pid"])
        if pid == own_pid:
            continue
        cpu_list = process.get("cpus_allowed_list")
        if not cpu_list:
            raise RuntimeError(f"cannot read CPU affinity for numerical process {pid}")
        affinity = _parse_cpu_list(str(cpu_list))
        if not affinity or not affinity.issubset(host_cpus):
            raise RuntimeError(f"numerical process {pid} has an invalid CPU affinity: {cpu_list}")
        if affinity == host_cpus:
            continue
        for cpu in sorted(affinity):
            blocked_cpus.add(cpu)
            excluded_claims.append({
                "cpu": cpu,
                "pid": pid,
                "authorized_cpu0_neighbor_identity_candidate": (
                    cpu == 0 and pid == AUTHORIZED_CPU0_NEIGHBOR["pid"]
                ),
            })

    counter_samples = []

    def sample_counters() -> dict[int, tuple[int, int]]:
        counters = _cpu_counters(proc_root / "stat")
        counter_samples.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "counters": {
                str(cpu): {
                    "total_jiffies": total,
                    "idle_and_iowait_jiffies": idle,
                }
                for cpu, (total, idle) in sorted(counters.items())
            },
        })
        return counters

    first = sample_counters()
    time.sleep(sample_seconds)
    second = sample_counters()
    time.sleep(sample_seconds)
    third = sample_counters()
    sample_busy = [
        _cpu_busy_percentages(first, second),
        _cpu_busy_percentages(second, third),
    ]
    busy = {
        cpu: max(values[cpu] for values in sample_busy if cpu in values)
        for cpu in set(sample_busy[0]) & set(sample_busy[1])
    }
    interval_seconds = [
        (counter_samples[index + 1]["monotonic_ns"] - counter_samples[index]["monotonic_ns"])
        / 1_000_000_000
        for index in range(2)
    ]
    candidates = [
        cpu for cpu in host_cpus
        if cpu in busy
        and cpu not in blocked_cpus
        and busy[cpu] < MAX_IDLE_CPU_BUSY_PERCENT
    ]
    if not candidates:
        raise RuntimeError(
            "no allowed CPU passed the idle and numerical-neighbor gates: "
            f"busy_percent={busy}, blocked_cpus={sorted(blocked_cpus)}, "
            f"required_busy_percent_strictly_below={MAX_IDLE_CPU_BUSY_PERCENT}"
        )
    selected = min(candidates, key=lambda cpu: (busy[cpu], cpu))
    return {
        "schema": "task44.dynamic_cpu_selection.v1",
        "selected_cpu": selected,
        "selected_cpu_busy_percent": busy[selected],
        "busy_percent_limit_strictly_less_than": MAX_IDLE_CPU_BUSY_PERCENT,
        "requested_sample_pause_seconds": sample_seconds,
        "sample_intervals_seconds": interval_seconds,
        "cpu_counter_unit": "jiffies from /proc/stat",
        "cpu_counter_samples": counter_samples,
        "sample_busy_percent": [
            {str(cpu): values[cpu] for cpu in sorted(values)}
            for values in sample_busy
        ],
        "host_pid1_comm": host_comm,
        "host_allowed_cpus": sorted(host_cpus),
        "cpu_busy_percent": {str(cpu): busy[cpu] for cpu in sorted(busy)},
        "blocked_cpus": sorted(blocked_cpus),
        "narrow_numerical_affinity_claims": excluded_claims,
    }


def _input_facts(path: Path, repo_root: Path) -> dict[str, Any]:
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized

    resolved_path = path.resolve(strict=True)
    resolved_path.relative_to(repo_root.resolve(strict=True))
    spec = load_and_resolve(resolved_path)
    config = simulation_config_3d_from_normalized(spec.as_jsonable())
    execution = spec.execution
    if (
        spec.identity.get("model_id") != "task44_sixlayer_0p7nm"
        or len(config.grating_layers) != 6
        or execution.get("mpi_size") != 1
        or execution.get("timeout_seconds") != 0
    ):
        raise RuntimeError("input does not satisfy the six-layer, MPI1, no-timeout Task44 contract")
    threads = {name: os.environ.get(name) for name in _THREAD_VARIABLES}
    if any(value != "1" for value in threads.values()):
        raise RuntimeError(f"Task44 requires every math thread count to be 1: {threads}")
    return {
        "path": str(resolved_path),
        "sha256": spec.input_sha256,
        "model_id": spec.identity["model_id"],
        "run_id": spec.identity["run_id"],
        "layer_count": len(config.grating_layers),
        "mpi_size": execution["mpi_size"],
        "timeout_seconds": execution["timeout_seconds"],
        "thread_controls": threads,
    }


def _runtime_facts_digest(source: Mapping[str, Any], input_facts: Mapping[str, Any],
                          environment: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"source": source, "input": input_facts, "environment": environment},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_runtime_probe(
    document: Any,
    *,
    repo_root: Path,
    input_path: Path,
    expected_source: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(document, dict) or set(document) != {
        "schema", "facts_sha256", "source", "input", "environment",
    }:
        raise RuntimeError("isolated Task44 runtime probe returned an invalid document")
    source = document["source"]
    input_facts = document["input"]
    environment = document["environment"]
    if document["schema"] != RUNTIME_PROBE_SCHEMA:
        raise RuntimeError("isolated Task44 runtime probe schema is unsupported")
    if source != dict(expected_source):
        raise RuntimeError("isolated Task44 runtime probe source identity changed")
    if not isinstance(input_facts, dict) or set(input_facts) != {
        "path", "sha256", "model_id", "run_id", "layer_count", "mpi_size",
        "timeout_seconds", "thread_controls",
    }:
        raise RuntimeError("isolated Task44 runtime probe input facts are incomplete")
    resolved_input = input_path.resolve(strict=True)
    resolved_input.relative_to(repo_root.resolve(strict=True))
    input_sha = hashlib.sha256(resolved_input.read_bytes()).hexdigest()
    if (
        input_facts["path"] != str(resolved_input)
        or input_facts["sha256"] != input_sha
        or input_facts["model_id"] != "task44_sixlayer_0p7nm"
        or input_facts["layer_count"] != 6
        or input_facts["mpi_size"] != 1
        or input_facts["timeout_seconds"] != 0
        or input_facts["thread_controls"] != dict.fromkeys(_THREAD_VARIABLES, "1")
        or not isinstance(input_facts["run_id"], str)
        or not input_facts["run_id"]
    ):
        raise RuntimeError("isolated Task44 runtime probe input binding failed")
    if not isinstance(environment, dict) or set(environment) != {
        "python_executable", "platform", "qualified_activation", "runtime_profile",
        "native_complex_identity", "sched_setaffinity_filter_test",
    }:
        raise RuntimeError("isolated Task44 runtime probe environment facts are incomplete")
    syscall_test = environment["sched_setaffinity_filter_test"]
    if (
        not isinstance(syscall_test, dict)
        or syscall_test.get("status") != "pass"
        or syscall_test.get("denied_syscall") != "sched_setaffinity"
        or syscall_test.get("errno") != "EPERM"
        or syscall_test.get("requested_cpu_affinity") != syscall_test.get("actual_cpu_affinity")
    ):
        raise RuntimeError("isolated Task44 runtime probe did not verify inherited seccomp denial")
    native = environment["native_complex_identity"]
    if not isinstance(native, dict) or set(native) != {
        "activation_marker", "task_root", "petsc_scalar_type", "petsc_int_type",
        "mpi_library_version", "mpi_size", "task44_runtime_controls", "module_paths",
    }:
        raise RuntimeError("isolated Task44 runtime probe native ABI facts are incomplete")
    module_paths = native["module_paths"]
    if not isinstance(module_paths, dict) or set(module_paths) != {
        "petsc4py", "slepc4py", "dolfinx", "basix",
    }:
        raise RuntimeError("isolated Task44 runtime probe module paths are incomplete")
    if (
        environment["python_executable"] != os.path.abspath(sys.executable)
        or environment["qualified_activation"] != "MYFENICS_NATIVE_COMPLEX_ENV=1"
        or environment["runtime_profile"] != "native_linux_complex"
        or native["activation_marker"] != "MYFENICS_NATIVE_COMPLEX_ENV=1"
        or native["task_root"] != str(repo_root.resolve(strict=True))
        or "complex128" not in str(native["petsc_scalar_type"])
        or not native["petsc_int_type"]
        or not native["mpi_library_version"]
        or native["mpi_size"] != 1
        or any(not isinstance(path, str) or not Path(path).is_absolute()
               for path in module_paths.values())
    ):
        raise RuntimeError("isolated Task44 runtime probe native environment gate failed")
    if native["task44_runtime_controls"] != TASK44_RUNTIME_CONTROLS:
        raise RuntimeError("isolated Task44 runtime probe runtime controls gate failed")
    expected_digest = _runtime_facts_digest(source, input_facts, environment)
    if document["facts_sha256"] != expected_digest:
        raise RuntimeError("isolated Task44 runtime probe facts digest does not match")
    return source, input_facts, environment


def _runtime_probe(
    input_path: Path, repo_root: Path, expected_source_sha: str,
    cpu_affinity: set[int],
) -> dict[str, Any]:
    verify_task44_root(repo_root, os.environ)
    _require_task44_cpu(cpu_affinity)
    if set(os.sched_getaffinity(0)) != cpu_affinity:
        raise RuntimeError("isolated Task44 runtime probe must inherit the exact selected CPU affinity")
    source = _source_facts(repo_root)
    if source["source_sha"] != expected_source_sha:
        raise RuntimeError("Task44 source SHA changed before isolated runtime probe")
    inputs = _input_facts(input_path, repo_root)
    from src.runners.task038_launcher import _environment_identity

    environment = _environment_identity()
    environment["sched_setaffinity_filter_test"] = _require_sched_setaffinity_eperm(
        cpu_affinity
    )
    document = {
        "schema": RUNTIME_PROBE_SCHEMA,
        "source": source,
        "input": inputs,
        "environment": environment,
    }
    document["facts_sha256"] = _runtime_facts_digest(source, inputs, environment)
    return document


def _direct_children(pid: int) -> list[int]:
    try:
        content = Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="ascii")
    except OSError as exc:
        raise RuntimeError(f"cannot verify Task44 service child ownership: {exc}") from exc
    return [int(value) for value in content.split()]


def _isolated_runtime_facts(
    input_path: Path, repo_root: Path, source: Mapping[str, Any], cpu_affinity: set[int]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    resolved_input = input_path.resolve(strict=True)
    cpu_text = ",".join(str(cpu) for cpu in sorted(cpu_affinity))
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--input", str(resolved_input),
        "--unit", "task44-runtime-probe.service",
        "--cpu-affinity", cpu_text,
        "--runtime-probe",
        "--expected-source-sha", str(source["source_sha"]),
    ]
    try:
        completed = subprocess.run(
            command, cwd=repo_root, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "")
        raise RuntimeError(f"isolated Task44 runtime probe failed: {detail or exc}") from exc
    lingering = _direct_children(os.getpid())
    if lingering:
        raise RuntimeError(
            f"isolated Task44 runtime probe left child processes in the supervisor: {lingering}"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("isolated Task44 runtime probe did not return JSON") from exc
    source_facts, input_facts, environment = _validate_runtime_probe(
        document,
        repo_root=repo_root,
        input_path=resolved_input,
        expected_source=source,
    )
    environment["isolated_runtime_probe"] = {
        "exit_code": completed.returncode,
        "facts_sha256": document["facts_sha256"],
    }
    return source_facts, input_facts, environment


def _admission_facts(cap_bytes: int, max_concurrent: int) -> dict[str, Any]:
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        memory_envelope,
    )

    units = _active_units()
    services = _task44_services(units)
    if len(services) + 1 > max_concurrent:
        raise RuntimeError(
            f"starting a sample would exceed the concurrency limit {max_concurrent}; "
            f"running Task44 services: {[row['unit'] for row in services]}"
        )
    if any(
        row["active_state"] != "active"
        or row["memory_max_bytes"] != row["cgroup_memory_max_bytes"]
        or row["swap_max_bytes"] != 0
        or row["cgroup_swap_max_bytes"] != 0
        for row in services
    ):
        raise RuntimeError("an active Task44 neighbor has unreadable or unqualified cgroup limits")
    envelope = memory_envelope(
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        host_reserve_bytes=HOST_RESERVE_BYTES,
        task_cgroup_reserve_bytes=0,
        require_cgroup_memory_details=True,
    )
    caps = [row["memory_max_bytes"] for row in services] + [cap_bytes]
    currents = [row["memory_current_bytes"] for row in services] + [0]
    buffers = [max(JOB_BUFFER_BYTES, int(cap * 0.05)) for cap in caps]
    uncommitted = sum(max(cap - current, 0) for cap, current in zip(caps, currents))
    host_required = HOST_RESERVE_BYTES + uncommitted + sum(buffers)
    cgroup_required = uncommitted + sum(buffers)
    host_available = int(envelope["host_mem_available_bytes"])
    cgroup_available = int(envelope["task_cgroup_available_bytes"])
    result = {
        "host_mem_available_bytes": host_available,
        "host_reserve_bytes": HOST_RESERVE_BYTES,
        "task_cgroup_available_bytes": cgroup_available,
        "active_task44_services": services,
        "planned_cap_bytes": cap_bytes,
        "planned_and_active_buffers_bytes": buffers,
        "uncommitted_job_capacity_bytes": uncommitted,
        "required_host_available_bytes": host_required,
        "required_cgroup_available_bytes": cgroup_required,
        "host_headroom_after_reserve_bytes": host_available - host_required,
        "cgroup_headroom_after_job_budgets_bytes": cgroup_available - cgroup_required,
        "memory_envelope": envelope,
    }
    if host_available < host_required or cgroup_available < cgroup_required:
        raise RuntimeError("host reserve, job buffers, or ancestor cgroup headroom gate failed")
    return result


def _exact_service_guard(
    unit: str, cap_bytes: int, max_concurrent: int, expected_cpus: set[int]
) -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import cgroup_snapshot, current_cgroup_path
    from scripts.task44_service_startup import observe_cgroup_cpu_affinity

    try:
        units = _active_units()
        services = _task44_services(units)
        facts = _unit_facts(unit)
        own_cgroup = current_cgroup_path(os.getpid())
        expected_cgroup = Path("/sys/fs/cgroup") / facts["control_group"].lstrip("/")
        snapshot = cgroup_snapshot(os.getpid())
        failures = []
        if facts["active_state"] != "active":
            failures.append("unit_not_active")
        if own_cgroup is None or own_cgroup.resolve(strict=True) != expected_cgroup.resolve(strict=True):
            failures.append("service_cgroup_identity_mismatch")
        if facts["memory_max_bytes"] != cap_bytes or facts["cgroup_memory_max_bytes"] != cap_bytes:
            failures.append("service_memory_max_mismatch")
        if facts["swap_max_bytes"] != 0 or facts["cgroup_swap_max_bytes"] != 0:
            failures.append("service_swap_max_mismatch")
        if facts["swap_current_bytes"] != 0 or snapshot.get("swap_current_bytes") != 0:
            failures.append("service_swap_nonzero_or_unreadable")
        if snapshot.get("readable") is not True or snapshot.get("dedicated_job_cgroup") is not True:
            failures.append("service_cgroup_unreadable_or_not_dedicated")
        active_names = {row["unit"] for row in services}
        if unit not in active_names or len(services) > max_concurrent:
            failures.append("task44_concurrency_gate_failed")
        if _parse_cpu_list(facts["cpu_affinity"]) != expected_cpus:
            failures.append("service_cpu_affinity_property_mismatch")
        if facts["system_call_filter"].split() != [TASK44_SYSTEM_CALL_FILTER]:
            failures.append("service_system_call_filter_mismatch")
        if facts["system_call_error_number"] not in {"EPERM", str(errno.EPERM)}:
            failures.append("service_system_call_error_number_mismatch")
        neighbor_gate = _cpu_neighbor_gate(
            selected_cpu=next(iter(expected_cpus)),
            ignored_cgroup=facts["control_group"]
        )
        if neighbor_gate["status"] != "pass":
            failures.append("selected_cpu_neighbor_gate_failed")
        affinity_report = observe_cgroup_cpu_affinity(expected_cgroup, expected_cpus)
        actual_affinities = affinity_report["service_pid_affinities"]
        if affinity_report["stop"]:
            failures.extend(affinity_report.get("failures") or ["service_process_affinity_monitor_failed"])
        return {
            "stop": bool(failures),
            "reason": "MONITORING_FAILED" if failures else None,
            "failures": failures,
            "unit": unit,
            "service": facts,
            "cgroup_snapshot": snapshot,
            "active_user_services": units,
            "active_task44_services": services,
            "expected_cpu_affinity": sorted(expected_cpus),
            "service_pid_affinities": actual_affinities,
            "service_process_affinity_observation": affinity_report,
            "cpu_neighbor_gate": neighbor_gate,
            "performance_not_isolated": neighbor_gate["performance_not_isolated"],
        }
    except Exception as exc:  # noqa: BLE001 - any monitor error must fail closed.
        return {
            "stop": True,
            "reason": "MONITORING_FAILED",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }


def _source_facts(repo_root: Path) -> dict[str, Any]:
    branch = _run(["git", "branch", "--show-current"], cwd=repo_root)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    status = _run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=repo_root)
    if branch != BRANCH or status:
        raise RuntimeError("Task44 formal service requires a clean worktree on the exact execution branch")
    return {"branch": branch, "source_sha": sha, "worktree_clean": True}


def resource_preflight(
    *, max_concurrent: int, cap_bytes: int, cpu_affinity: set[int]
) -> dict[str, Any]:
    verify_task44_root(Path(__file__).resolve().parents[1], os.environ)
    _require_task44_cpu(cpu_affinity)
    selected_cpu = next(iter(cpu_affinity))
    neighbor_gate = _cpu_neighbor_gate(
        selected_cpu=selected_cpu, ignored_pids={os.getpid()}
    )
    if neighbor_gate["status"] != "pass":
        raise RuntimeError(f"Task44 selected CPU neighbor gate failed: {neighbor_gate}")
    return {
        "schema": "task44.resource_preflight.v1",
        "status": "resource_preflight_pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resources": _admission_facts(cap_bytes, max_concurrent),
        "max_concurrent": max_concurrent,
        "service_memory_max_bytes": cap_bytes,
        "service_memory_swap_max_bytes": 0,
        "selected_cpu_affinity": sorted(cpu_affinity),
        "cpu_neighbor_gate": neighbor_gate,
        "performance_not_isolated": neighbor_gate["performance_not_isolated"],
    }


def preflight(
    input_path: Path, *, unit: str, cpu_affinity: set[int],
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    verify_task44_root(repo_root, os.environ)
    _require_task44_cpu(cpu_affinity)
    unit_facts, syscall_test = _verify_filtered_unit(
        unit, expected_cpus=cpu_affinity, cap_bytes=PREFLIGHT_CAP_BYTES
    )
    selected_cpu = next(iter(cpu_affinity))
    neighbor_gate = _cpu_neighbor_gate(
        selected_cpu=selected_cpu,
        ignored_cgroup=unit_facts["control_group"],
    )
    if neighbor_gate["status"] != "pass":
        raise RuntimeError(f"Task44 selected CPU neighbor gate failed: {neighbor_gate}")
    from src.runners.task038_launcher import _environment_identity

    environment = _environment_identity()
    environment["sched_setaffinity_filter_test"] = syscall_test
    if environment["runtime_profile"] != "native_linux_complex":
        raise RuntimeError("native environment identity did not resolve to native Linux complex runtime")
    native = environment.get("native_complex_identity") or {}
    if "complex128" not in str(native.get("petsc_scalar_type")) or native.get("mpi_size") != 1:
        raise RuntimeError("Task44 requires complex128 PETSc and a one-rank native MPI identity")
    if native.get("task44_runtime_controls") != TASK44_RUNTIME_CONTROLS:
        raise RuntimeError("Task44 activation is missing the qualified hwloc/Open MPI runtime controls")
    source = _source_facts(repo_root)
    inputs = _input_facts(input_path, repo_root)
    return {
        "status": "preflight_pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(repo_root),
        "source": source,
        "input": inputs,
        "environment": environment,
        "active_user_services": _active_units(),
        "preflight_service_memory_max_bytes": PREFLIGHT_CAP_BYTES,
        "service_memory_swap_max_bytes": 0,
        "preflight_service_unit": unit,
        "preflight_service_system_call_filter": unit_facts["system_call_filter"],
        "preflight_service_system_call_error_number": unit_facts["system_call_error_number"],
        "sched_setaffinity_filter_test": syscall_test,
        "selected_cpu_affinity": sorted(cpu_affinity),
        "cpu_neighbor_gate": neighbor_gate,
        "performance_not_isolated": neighbor_gate["performance_not_isolated"],
    }


def run_service(
    input_path: Path, *, unit: str, max_concurrent: int, cap_bytes: int,
    cpu_affinity: set[int], smoke: bool = False,
) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    verify_task44_root(repo_root, os.environ)
    expected_cache_root = (
        Path("/tmp")
        / f"myfenics-task44-native-cache-{os.getuid()}"
        / unit.removesuffix(".service")
    ).resolve()
    cache_root = Path(os.environ.get("MYFENICS_TASK44_CACHE_ROOT", "")).resolve()
    xdg_cache_home = Path(os.environ.get("XDG_CACHE_HOME", "")).resolve()
    if (
        cache_root != expected_cache_root
        or xdg_cache_home != (expected_cache_root / "xdg").resolve()
    ):
        raise RuntimeError(
            "Task44 service JIT cache is not bound to its unique per-service root: "
            f"expected={expected_cache_root / 'xdg'} actual={xdg_cache_home}"
        )
    cache_identity = {
        "root": str(cache_root),
        "xdg_cache_home": str(xdg_cache_home),
        "ffcx_cache_dir": str(xdg_cache_home / "fenics"),
        "worker_environment_binding": "explicit",
    }
    _require_task44_cpu(cpu_affinity)
    unit_facts, syscall_test = _verify_filtered_unit(
        unit, expected_cpus=cpu_affinity, cap_bytes=cap_bytes
    )
    unit_cgroup = unit_facts["control_group"]
    selected_cpu = next(iter(cpu_affinity))
    neighbor_gate = _cpu_neighbor_gate(
        selected_cpu=selected_cpu, ignored_cgroup=unit_cgroup
    )
    if neighbor_gate["status"] != "pass":
        raise RuntimeError(f"Task44 selected CPU neighbor gate failed before ABI probe: {neighbor_gate}")
    source = _source_facts(repo_root)
    source, inputs, native_environment = _isolated_runtime_facts(
        input_path, repo_root, source, cpu_affinity
    )
    neighbor_gate = _cpu_neighbor_gate(
        selected_cpu=selected_cpu, ignored_cgroup=unit_cgroup
    )
    if neighbor_gate["status"] != "pass":
        raise RuntimeError(f"Task44 selected CPU neighbor gate failed after ABI probe: {neighbor_gate}")
    identity = _write_service_identity(
        unit, repo_root, cpu_affinity, cap_bytes, native_environment, neighbor_gate,
        {
            "system_call_filter": unit_facts["system_call_filter"],
            "system_call_error_number": unit_facts["system_call_error_number"],
            "sched_setaffinity_filter_test": syscall_test,
        },
    )
    guard = _exact_service_guard(unit, cap_bytes, max_concurrent, cpu_affinity)
    if guard["stop"]:
        raise RuntimeError(f"Task44 exact-service startup gate failed: {guard}")
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        supervise,
    )
    from src.runners.physical_v14_budget import V14_TIME_POLICY_OBSERVE_ONLY

    artifacts = repo_root / "benchmarks/artifacts/task44_native_services" / unit
    watchdog_directory = artifacts / "watchdog"
    print(
        f"Task44 service unit={unit} supervisor_pid={os.getpid()} "
        f"input_sha256={inputs['sha256']} source_sha={source['source_sha']} "
        f"ffcx_cache_dir={cache_identity['ffcx_cache_dir']}",
        flush=True,
    )
    command = [
        sys.executable,
        str(repo_root / "scripts/run_case.py"),
        str(inputs["path"]),
    ]
    if smoke:
        command.append("--dry-run")
    summary = supervise(
        command,
        watchdog_directory,
        wall_seconds=86400.0,
        interval=5.0,
        grace_seconds=10.0,
        hard_stop_immediate=True,
        time_policy=V14_TIME_POLICY_OBSERVE_ONLY,
        memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        pss_sampling_policy="disabled_by_profile",
        tree_cap_bytes=cap_bytes,
        allow_physical_pressure_tree_cap=True,
        require_job_cgroup_zero_swap=True,
        require_cgroup_memory_details=True,
        host_reserve_bytes=HOST_RESERVE_BYTES,
        task_cgroup_reserve_bytes=JOB_BUFFER_BYTES,
        external_guard=lambda: _exact_service_guard(
            unit, cap_bytes, max_concurrent, cpu_affinity
        ),
        worker_environment={
            "MYFENICS_NATIVE_COMPLEX_ENV": "1",
            "MYFENICS_TASK44_ROOT": str(repo_root),
            "MYFENICS_TASK44_CACHE_ROOT": str(cache_root),
            "XDG_CACHE_HOME": str(xdg_cache_home),
        },
        source_state={
            **source,
            "jit_cache": cache_identity,
            "service_unit": unit,
            "service_identity": identity,
            "input_path": inputs["path"],
            "input_sha256": inputs["sha256"],
            "execution_mode": "public_runner_dry_run_smoke" if smoke else "public_runner_full3d",
            "native_environment": native_environment,
            "cpu_neighbor_gate": neighbor_gate,
            "performance_not_isolated": neighbor_gate["performance_not_isolated"],
            "time_policy": "observe_only; no wall-time termination",
        },
    )
    summary["task44_service"] = {
        "service_unit": unit,
        "input": inputs,
        "source": source,
        "jit_cache": cache_identity,
        "service_gate_start": guard,
        "resource_authority_samples": str(watchdog_directory / "resources.jsonl"),
        "runner_log": str(watchdog_directory / "worker.log"),
        "wall_time_termination": "disabled_by_time_policy_observe_only",
        "smoke": smoke,
        "cpu_neighbor_gate": neighbor_gate,
        "performance_not_isolated": neighbor_gate["performance_not_isolated"],
    }
    _atomic_write_json(artifacts / "service_summary.json", summary)
    print(
        f"Task44 service finished unit={unit} classification={summary.get('classification')} "
        f"elapsed_seconds={summary.get('elapsed_seconds')}",
        flush=True,
    )
    return 0 if summary.get("classification") == "COMPLETED" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--cpu-affinity", required=True)
    parser.add_argument("--max-concurrent", type=int, choices=(1, 2), default=1)
    parser.add_argument("--cap-bytes", type=int, default=INITIAL_CAP_BYTES)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--resource-preflight", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--runtime-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-source-sha", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cpu_affinity = _parse_cpu_list(args.cpu_affinity)
        if args.resource_preflight:
            if args.preflight or args.runtime_probe or args.smoke:
                raise RuntimeError("Task44 resource preflight arguments are invalid")
            result = resource_preflight(
                max_concurrent=args.max_concurrent,
                cap_bytes=args.cap_bytes,
                cpu_affinity=cpu_affinity,
            )
            print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
            return 0
        if args.runtime_probe:
            if args.preflight or args.smoke or not args.expected_source_sha:
                raise RuntimeError("isolated Task44 runtime probe arguments are invalid")
            result = _runtime_probe(
                args.input,
                Path(__file__).resolve().parents[1],
                args.expected_source_sha,
                cpu_affinity,
            )
            print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
            return 0
        if args.preflight:
            result = preflight(
                args.input, unit=args.unit,
                cpu_affinity=cpu_affinity,
            )
            print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
            return 0
        if args.cap_bytes != INITIAL_CAP_BYTES:
            raise RuntimeError("Task44 initial service cap must not exceed 128 GiB")
        return run_service(
            args.input,
            unit=args.unit,
            max_concurrent=args.max_concurrent,
            cap_bytes=args.cap_bytes,
            cpu_affinity=cpu_affinity,
            smoke=args.smoke,
        )
    # Convert any uncaught gate failure to a clear service exit.
    except Exception as exc:  # noqa: BLE001
        print(f"Task44 service gate failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
