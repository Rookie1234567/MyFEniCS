"""WSL/job resource authorities used by Task034 formal runners."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GIB = 1024**3


def _read_int(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return None if value == "max" else int(value)
    except (OSError, ValueError):
        return None


def _read_limit(path: Path) -> tuple[int | None, str]:
    """Read a cgroup limit while retaining the ``max``/unreadable state."""

    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, "unreadable"
    if value == "max":
        return None, "max_or_unlimited"
    try:
        return int(value), "finite"
    except ValueError:
        return None, "unreadable"


def _read_key_kib(path: Path, key: str) -> int | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith(f"{key}:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def _read_kernel_memavailable(path: Path) -> dict[str, Any]:
    """Read the kernel MemAvailable value with an explicit unit/schema."""

    try:
        rows = [
            line.split(":", 1)[1].split()
            for line in path.read_text(encoding="ascii").splitlines()
            if line.startswith("MemAvailable:")
        ]
    except OSError as exc:
        return {
            "schema": "task041.kernel_memavailable.v1",
            "status": "unknown",
            "bytes": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != "kB":
        return {
            "schema": "task041.kernel_memavailable.v1",
            "status": "unknown",
            "bytes": None,
            "error": "MemAvailable row is missing, duplicated, or not expressed in kB",
        }
    try:
        kib = int(rows[0][0])
    except ValueError:
        kib = -1
    if kib < 0:
        return {
            "schema": "task041.kernel_memavailable.v1",
            "status": "unknown",
            "bytes": None,
            "error": "MemAvailable kB value is malformed or negative",
        }
    return {
        "schema": "task041.kernel_memavailable.v1",
        "status": "measured",
        "bytes": kib * 1024,
        "error": None,
    }


def current_cgroup_path(pid: int | str = "self") -> Path | None:
    """Resolve the unified cgroup v2 path for a process."""

    try:
        lines = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            relative = fields[2].lstrip("/")
            return Path("/sys/fs/cgroup") / relative
    return None


def _cgroup_memory_ancestors(path: Path) -> list[dict[str, Any]]:
    root = Path("/sys/fs/cgroup")
    rows: list[dict[str, Any]] = []
    current = path
    while root == current or root in current.parents:
        limit, limit_state = _read_limit(current / "memory.max")
        try:
            relative = current.relative_to(root).as_posix()
        except ValueError:
            relative = str(current)
        current_memory = _read_int(current / "memory.current")
        if current == root and limit_state == "unreadable" and current_memory is None:
            limit_state = "not_applicable_root"
        rows.append(
            {
                "path": "/" if relative in {"", "."} else f"/{relative}",
                "memory_current_bytes": current_memory,
                "memory_peak_bytes": _read_int(current / "memory.peak"),
                "memory_limit_bytes": limit,
                "memory_limit_state": limit_state,
                "memory_headroom_bytes": (
                    None
                    if limit is None or current_memory is None
                    else max(0, limit - current_memory)
                ),
            }
        )
        if current == root:
            break
        current = current.parent
    return rows


def cgroup_snapshot(pid: int | str = "self") -> dict[str, Any]:
    path = current_cgroup_path(pid)
    if path is None:
        return {
            "path": None,
            "readable": False,
            "dedicated_job_cgroup": False,
            "memory_current_bytes": None,
            "memory_peak_bytes": None,
            "memory_limit_bytes": None,
            "memory_limit_state": "unreadable",
            "memory_headroom_bytes": None,
            "ancestor_memory": [],
            "ancestor_hard_limit_bytes": None,
            "ancestor_hard_limit_state": "unreadable",
            "ancestor_memory_headroom_bytes": None,
            "swap_current_bytes": None,
        }
    try:
        members = {
            int(value)
            for value in (path / "cgroup.procs").read_text(encoding="utf-8").split()
        }
    except (OSError, ValueError):
        members = set()
    # WSL commonly places all distro processes in /init.scope.  It is useful
    # diagnostic context, but it is not a dedicated job authority.
    relative = path.relative_to(Path("/sys/fs/cgroup")).as_posix()
    basename = Path(relative).name
    session_scope = (
        relative.startswith("user.slice/")
        and basename.startswith("session-")
        and basename.endswith(".scope")
    )
    dedicated = bool(
        relative not in {".", "", "init.scope"} and not session_scope
    )
    ancestor_memory = _cgroup_memory_ancestors(path)
    finite_limits = [
        int(row["memory_limit_bytes"])
        for row in ancestor_memory
        if row.get("memory_limit_state") == "finite"
    ]
    finite_headroom = [
        int(row["memory_headroom_bytes"])
        for row in ancestor_memory
        if isinstance(row.get("memory_headroom_bytes"), int)
    ]
    ancestor_states = {
        row.get("memory_limit_state")
        for row in ancestor_memory
        if row.get("memory_limit_state") != "not_applicable_root"
    }
    if finite_limits:
        ancestor_limit_state = (
            "partially_unreadable"
            if "unreadable" in ancestor_states
            else "finite"
        )
    elif not ancestor_states and ancestor_memory:
        ancestor_limit_state = "not_applicable_root"
    elif ancestor_memory and "unreadable" not in ancestor_states:
        ancestor_limit_state = "max_or_unlimited"
    else:
        ancestor_limit_state = "unreadable"
    current_limit, current_limit_state = _read_limit(path / "memory.max")
    current_memory = _read_int(path / "memory.current")
    return {
        "path": f"/{relative}" if relative not in {".", ""} else "/",
        "readable": (path / "memory.current").is_file(),
        "dedicated_job_cgroup": dedicated,
        "member_count": len(members),
        "memory_current_bytes": current_memory,
        "memory_peak_bytes": _read_int(path / "memory.peak"),
        "memory_limit_bytes": current_limit,
        "memory_limit_state": current_limit_state,
        "memory_headroom_bytes": (
            None
            if current_limit is None or current_memory is None
            else max(0, current_limit - current_memory)
        ),
        "ancestor_memory": ancestor_memory,
        "ancestor_hard_limit_bytes": min(finite_limits, default=None),
        "ancestor_hard_limit_state": ancestor_limit_state,
        "ancestor_memory_headroom_bytes": min(finite_headroom, default=None),
        "scope_semantics": (
            "shared_cgroup_diagnostic_only"
            if not dedicated
            else "dedicated_job_cgroup_authority"
        ),
        "swap_current_bytes": _read_int(path / "memory.swap.current"),
    }


def vmstat_swap_pages() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        lines = Path("/proc/vmstat").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and fields[0] in {"pswpin", "pswpout"}:
            try:
                values[fields[0]] = int(fields[1])
            except ValueError:
                pass
    return {
        "pswpin_pages": values.get("pswpin"),
        "pswpout_pages": values.get("pswpout"),
    }


def proc_swaps_snapshot() -> dict[str, Any]:
    """Read system swap-device usage as a shared-host diagnostic."""

    try:
        lines = Path("/proc/swaps").read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines()
    except OSError:
        return {
            "readable": False,
            "device_count": None,
            "used_bytes": None,
        }
    rows: list[dict[str, Any]] = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            size_kib = int(fields[2])
            used_kib = int(fields[3])
            priority = int(fields[4])
        except ValueError:
            return {
                "readable": False,
                "device_count": None,
                "used_bytes": None,
            }
        rows.append(
            {
                "type": fields[1],
                "size_bytes": size_kib * 1024,
                "used_bytes": used_kib * 1024,
                "priority": priority,
            }
        )
    return {
        "readable": True,
        "device_count": len(rows),
        "used_bytes": sum(int(row["used_bytes"]) for row in rows),
        "devices": rows,
    }


def wsl_memory_snapshot() -> dict[str, Any]:
    kernel_available = _read_kernel_memavailable(Path("/proc/meminfo"))
    return {
        "mem_total_bytes": (
            None
            if (value := _read_key_kib(Path("/proc/meminfo"), "MemTotal")) is None
            else value * 1024
        ),
        "mem_available_bytes": (
            None
            if (value := _read_key_kib(Path("/proc/meminfo"), "MemAvailable")) is None
            else value * 1024
        ),
        "kernel_memavailable": kernel_available,
    }


def normal_memory_nodes() -> list[int]:
    """Return online NUMA nodes with measurable normal RAM (MemTotal > 0)."""

    root = Path("/sys/devices/system/node")
    online_text = (root / "online").read_text(encoding="ascii").strip()
    online: set[int] = set()
    for token in online_text.split(","):
        if not token:
            raise OSError("NUMA online-node list is empty or malformed")
        bounds = token.split("-", 1)
        if len(bounds) == 1:
            if not bounds[0].isdigit():
                raise OSError("NUMA online-node list is malformed")
            online.add(int(bounds[0]))
            continue
        if (
            not bounds[0].isdigit()
            or not bounds[1].isdigit()
            or int(bounds[1]) < int(bounds[0])
        ):
            raise OSError("NUMA online-node range is malformed")
        online.update(range(int(bounds[0]), int(bounds[1]) + 1))
    if not online:
        raise OSError("NUMA online-node list is empty")
    nodes: list[int] = []
    for node in sorted(online):
        node_path = root / f"node{node}"
        if not node_path.is_dir():
            raise OSError(f"online NUMA node {node} is not present")
        rows = [
            line.split(":", 1)[1].split()
            for line in (node_path / "meminfo").read_text(encoding="ascii").splitlines()
            if line.startswith(f"Node {node} MemTotal:")
        ]
        if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != "kB":
            raise OSError(f"NUMA node {node} MemTotal is unavailable or malformed")
        if int(rows[0][0]) > 0:
            nodes.append(node)
    if not nodes:
        raise OSError("host has no measurable normal RAM NUMA nodes")
    return nodes


def effective_memory_limit(
    *, user_limit_gib: float = 220.0, reserve_gib: float = 24.0
) -> dict[str, Any]:
    memory = wsl_memory_snapshot()
    total = memory["mem_total_bytes"]
    available = memory["mem_available_bytes"]
    candidates = {
        "user_limit_bytes": int(user_limit_gib * GIB),
        "wsl_total_85_percent_bytes": (None if total is None else int(0.85 * total)),
        "available_minus_reserve_bytes": (
            None if available is None else max(0, available - int(reserve_gib * GIB))
        ),
    }
    finite = [value for value in candidates.values() if isinstance(value, int)]
    effective = min(finite) if len(finite) == len(candidates) else None
    return {
        **memory,
        **candidates,
        "effective_limit_bytes": effective,
        "effective_limit_gib": None if effective is None else effective / GIB,
        "warning_bytes": None if effective is None else int(0.80 * effective),
        "termination_bytes": None if effective is None else int(0.95 * effective),
        "formula": "min(user 220 GiB, 0.85*WSL total, available-24 GiB)",
    }


@dataclass(frozen=True)
class ProcessTreeSample:
    root_pid: int
    pids: tuple[int, ...]
    rss_bytes: int
    swap_bytes: int
    all_status_readable: bool
    rss_by_pid_bytes: dict[int, int | None]
    swap_by_pid_bytes: dict[int, int | None]
    read_diagnostics_by_pid: dict[int, dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        read_diagnostics = record.pop("read_diagnostics_by_pid", None)
        if read_diagnostics:
            record["read_diagnostics_by_pid"] = read_diagnostics
        return record


def _status_memory_kib(fields: Mapping[str, str]) -> tuple[int | None, int | None]:
    def kib(name: str) -> int | None:
        try:
            return int(fields[name].split()[0])
        except (KeyError, IndexError, ValueError):
            return None

    rss_kib = kib("VmRSS")
    swap_kib = kib("VmSwap")
    state = fields.get("State", "").split(maxsplit=1)[0]
    if state in {"Z", "X", "x"}:
        # A zombie/dead task has no address space. Linux may omit both fields
        # during normal MPI rank teardown; zero is authoritative.
        rss_kib = 0 if rss_kib is None else rss_kib
        swap_kib = 0 if swap_kib is None else swap_kib
    return rss_kib, swap_kib


def _parse_proc_stat_identity(
    text: str, *, expected_pid: int
) -> dict[str, int | str] | None:
    """Parse PID, state, PPID, and start ticks from one Linux proc stat row."""

    opening = text.find("(")
    closing = text.rfind(")")
    if opening <= 0 or closing <= opening:
        return None
    try:
        pid = int(text[:opening].strip())
    except ValueError:
        return None
    fields = text[closing + 1 :].split()
    if pid != expected_pid or len(fields) <= 19:
        return None
    try:
        ppid = int(fields[1])
        start_ticks = int(fields[19])
    except ValueError:
        return None
    state = fields[0]
    if not state or start_ticks < 0:
        return None
    return {
        "pid": pid,
        "ppid": ppid,
        "state": state,
        "start_ticks": start_ticks,
    }


def _read_proc_stat_identity(
    stat_path: Path, *, expected_pid: int
) -> tuple[dict[str, int | str] | None, str | None]:
    try:
        text = stat_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None, "not_present"
    except OSError as exc:
        return None, f"unreadable:{type(exc).__name__}"
    identity = _parse_proc_stat_identity(text, expected_pid=expected_pid)
    return (identity, None) if identity is not None else (None, "invalid")


def _read_proc_status_fields(
    status_path: Path,
) -> tuple[dict[str, str] | None, str | None]:
    try:
        lines = status_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return None, "not_present"
    except OSError as exc:
        return None, f"unreadable:{type(exc).__name__}"
    fields = {
        key: value.strip()
        for line in lines
        if ":" in line
        for key, value in [line.split(":", 1)]
    }
    return fields, None


def _proc_status_pid_matches(fields: Mapping[str, str] | None, pid: int) -> bool:
    if fields is None:
        return False
    try:
        return int(fields["Pid"]) == pid
    except (KeyError, ValueError):
        return False


def _memory_read_snapshot(
    fields: Mapping[str, str] | None,
    *,
    error: str | None,
    identity: Mapping[str, int | str] | None,
    pid: int,
) -> tuple[int | None, int | None, dict[str, Any]]:
    rss, swap = _status_memory_kib(fields) if fields is not None else (None, None)
    pid_matches = _proc_status_pid_matches(fields, pid)
    if not pid_matches:
        rss = swap = None
    return rss, swap, {
        "status_error": error,
        "status_pid": None if fields is None else fields.get("Pid"),
        "state_raw": None if fields is None else fields.get("State"),
        "state_from_proc_stat": None if identity is None else identity.get("state"),
        "start_ticks": None if identity is None else identity.get("start_ticks"),
        "vmrss_raw": None if fields is None else fields.get("VmRSS"),
        "vmswap_raw": None if fields is None else fields.get("VmSwap"),
        "pid_matches": pid_matches,
        "missing_fields": [
            name
            for name, value in (("VmRSS", rss), ("VmSwap", swap))
            if value is None
        ],
    }


def _bounded_process_memory_reread(
    *,
    pid: int,
    proc_directory: Path,
    first_identity: Mapping[str, int | str] | None,
    first_identity_error: str | None,
    first_status: Mapping[str, str] | None,
    first_status_error: str | None,
) -> tuple[int | None, int | None, dict[str, Any]]:
    """Retry one incomplete status read only while checking the same PID identity."""

    first_rss, first_swap, first_read = _memory_read_snapshot(
        first_status,
        error=first_status_error,
        identity=first_identity,
        pid=pid,
    )
    diagnostic: dict[str, Any] = {
        "pid": pid,
        "first_identity": None if first_identity is None else dict(first_identity),
        "first_identity_error": first_identity_error,
        "first_read": first_read,
        "bounded_reread_count": 0,
        "sample_usable": False,
    }
    if first_identity is None or first_identity.get("pid") != pid:
        diagnostic["resolution"] = "refused_initial_start_ticks_unavailable"
        return first_rss, first_swap, diagnostic

    diagnostic["bounded_reread_count"] = 1
    reread_identity, reread_identity_error = _read_proc_stat_identity(
        proc_directory / "stat", expected_pid=pid
    )
    if reread_identity_error == "not_present":
        diagnostic["reread"] = {
            "proc_stat": "not_present",
            "identity_error": None,
        }
        diagnostic["resolution"] = "confirmed_initial_pid_start_ticks_no_longer_present"
        diagnostic["sample_usable"] = True
        return (
            0,
            0,
            diagnostic,
        )
    if reread_identity is None:
        diagnostic["reread"] = {
            "proc_stat": "unavailable_or_invalid",
            "identity_error": reread_identity_error,
        }
        diagnostic["resolution"] = "refused_reread_identity_unavailable"
        return first_rss, first_swap, diagnostic
    if reread_identity.get("start_ticks") != first_identity.get("start_ticks"):
        diagnostic["reread"] = {"proc_stat_identity": reread_identity}
        diagnostic["resolution"] = "refused_pid_start_ticks_changed"
        return first_rss, first_swap, diagnostic
    if reread_identity.get("state") in {"Z", "X", "x"}:
        diagnostic["reread"] = {"proc_stat_identity": reread_identity}
        diagnostic["resolution"] = "confirmed_same_identity_terminal_state"
        diagnostic["sample_usable"] = True
        return 0, 0, diagnostic

    reread_status, reread_status_error = _read_proc_status_fields(
        proc_directory / "status"
    )
    reread_rss, reread_swap, reread_read = _memory_read_snapshot(
        reread_status,
        error=reread_status_error,
        identity=reread_identity,
        pid=pid,
    )
    after_identity, after_identity_error = _read_proc_stat_identity(
        proc_directory / "stat", expected_pid=pid
    )
    diagnostic["reread"] = {
        "proc_stat_before_status": reread_identity,
        "status": reread_read,
        "proc_stat_after_status": after_identity,
        "proc_stat_after_status_error": after_identity_error,
    }
    if after_identity_error == "not_present":
        diagnostic["resolution"] = "confirmed_initial_pid_start_ticks_exited_during_reread"
        diagnostic["sample_usable"] = True
        return 0, 0, diagnostic
    if after_identity is None:
        diagnostic["resolution"] = "refused_postread_identity_unavailable"
        # Keep the initial observation as the row value. The later status
        # fields remain available in the diagnostic, but without a verified
        # post-read identity they must not be presented as one coherent sample.
        return first_rss, first_swap, diagnostic
    if after_identity.get("start_ticks") != first_identity.get("start_ticks"):
        diagnostic["resolution"] = "refused_pid_start_ticks_changed_after_reread"
        return first_rss, first_swap, diagnostic
    if after_identity.get("state") in {"Z", "X", "x"}:
        diagnostic["resolution"] = "confirmed_same_identity_terminal_after_reread"
        diagnostic["sample_usable"] = True
        return 0, 0, diagnostic
    if (
        reread_read["pid_matches"]
        and reread_rss is not None
        and reread_swap is not None
    ):
        diagnostic["resolution"] = "measured_after_same_pid_start_ticks_reread"
        diagnostic["sample_usable"] = True
        return reread_rss, reread_swap, diagnostic
    diagnostic["resolution"] = "refused_same_identity_status_still_incomplete"
    return first_rss, first_swap, diagnostic


def _read_smaps_rollup(path: Path) -> dict[str, float] | None:
    """Read the small Linux smaps rollup used for process-tree telemetry."""

    wanted = {
        "Rss",
        "Pss",
        "Private_Clean",
        "Private_Dirty",
        "Private_Hugetlb",
        "Shared_Clean",
        "Shared_Dirty",
        "Shared_Hugetlb",
        "Anonymous",
        "Swap",
        "SwapPss",
    }
    values_kib: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line in lines:
        if ":" not in line:
            continue
        key, text = line.split(":", 1)
        if key not in wanted:
            continue
        try:
            values_kib[key] = int(text.split()[0])
        except (IndexError, ValueError):
            return None
    if not {
        "Rss",
        "Pss",
        "Private_Clean",
        "Private_Dirty",
    }.issubset(values_kib):
        return None
    private_kib = sum(
        values_kib.get(key, 0)
        for key in ("Private_Clean", "Private_Dirty", "Private_Hugetlb")
    )
    shared_kib = sum(
        values_kib.get(key, 0)
        for key in ("Shared_Clean", "Shared_Dirty", "Shared_Hugetlb")
    )
    return {
        "rss_mb": values_kib["Rss"] / 1024.0,
        "pss_mb": values_kib["Pss"] / 1024.0,
        "uss_mb": private_kib / 1024.0,
        "shared_mb": shared_kib / 1024.0,
        "anonymous_mb": values_kib.get("Anonymous", 0) / 1024.0,
        "swap_mb": values_kib.get("Swap", 0) / 1024.0,
        "swap_pss_mb": values_kib.get("SwapPss", 0) / 1024.0,
    }


def process_tree_sample(
    root_pid: int, *, proc_root: Path | str = Path("/proc")
) -> ProcessTreeSample:
    """Sample RSS and VmSwap for the root and every live descendant."""

    proc_root = Path(proc_root)
    processes: dict[int, dict[str, Any]] = {}
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        identity, _identity_error = _read_proc_stat_identity(
            entry / "stat", expected_pid=pid
        )
        fields, status_error = _read_proc_status_fields(entry / "status")
        if identity is None and fields is None:
            continue
        ppid_raw = None if fields is None else fields.get("PPid")
        try:
            ppid = int(ppid_raw) if ppid_raw is not None else int(identity["ppid"])
        except (KeyError, TypeError, ValueError):
            ppid = int(identity["ppid"]) if identity is not None else 0
        rss_kib, swap_kib = (
            _status_memory_kib(fields) if fields is not None else (None, None)
        )
        if not _proc_status_pid_matches(fields, pid):
            rss_kib = None
            swap_kib = None
        processes[pid] = {
            "ppid": ppid,
            "rss_kib": rss_kib,
            "swap_kib": swap_kib,
            "identity": identity,
            "identity_error": _identity_error,
            "status": fields,
            "status_error": status_error,
        }
    selected = {int(root_pid)}
    changed = True
    while changed:
        changed = False
        for pid, process in processes.items():
            if pid not in selected and process["ppid"] in selected:
                selected.add(pid)
                changed = True
    diagnostics: dict[int, dict[str, Any]] = {}
    observed: list[tuple[int, int | None, int | None]] = []
    for pid in sorted(selected):
        process = processes.get(pid)
        if process is None:
            continue
        rss_kib = process["rss_kib"]
        swap_kib = process["swap_kib"]
        if (
            rss_kib is None
            or swap_kib is None
            or process["identity"] is None
        ):
            rss_kib, swap_kib, diagnostic = _bounded_process_memory_reread(
                pid=pid,
                proc_directory=proc_root / str(pid),
                first_identity=process["identity"],
                first_identity_error=process["identity_error"],
                first_status=process["status"],
                first_status_error=process["status_error"],
            )
            diagnostics[pid] = diagnostic
        observed.append((pid, rss_kib, swap_kib))
    root_process = processes.get(int(root_pid))
    root_identity = None if root_process is None else root_process["identity"]
    root_status = None if root_process is None else root_process["status"]
    root_states = {
        None if root_identity is None else root_identity.get("state"),
        None
        if root_status is None
        else root_status.get("State", "").split(maxsplit=1)[0],
    }
    root_diagnostic = diagnostics.get(int(root_pid), {})
    root_terminal = bool(root_states & {"Z", "X", "x"}) or (
        root_diagnostic.get("resolution", "").startswith("confirmed_")
    )
    def sample_row_is_usable(pid: int) -> bool:
        diagnostic = diagnostics.get(pid)
        if diagnostic is None:
            return True
        resolution = diagnostic.get("resolution")
        return (
            diagnostic.get("sample_usable") is True
            and not (isinstance(resolution, str) and resolution.startswith("refused"))
        )

    readable = (
        root_process is not None
        and not root_terminal
        and bool(observed)
        and all(
            rss is not None
            and swap is not None
            and sample_row_is_usable(pid)
            for pid, rss, swap in observed
        )
    )
    rss_by_pid = {
        pid: None if rss is None else rss * 1024 for pid, rss, _swap in observed
    }
    swap_by_pid = {
        pid: None if swap is None else swap * 1024 for pid, _rss, swap in observed
    }
    return ProcessTreeSample(
        root_pid=int(root_pid),
        pids=tuple(sorted(pid for pid in selected if pid in processes)),
        rss_bytes=sum(rss for rss in rss_by_pid.values() if rss is not None),
        swap_bytes=sum(swap for swap in swap_by_pid.values() if swap is not None),
        all_status_readable=readable,
        rss_by_pid_bytes=rss_by_pid,
        swap_by_pid_bytes=swap_by_pid,
        read_diagnostics_by_pid=diagnostics or None,
    )


def process_tree_smaps_sample(pids: tuple[int, ...]) -> dict[str, Any]:
    """Aggregate one complete process-tree smaps sample, or mark it incomplete."""

    rows = [
        _read_smaps_rollup(Path("/proc") / str(pid) / "smaps_rollup") for pid in pids
    ]
    readable = [row for row in rows if row is not None]
    result: dict[str, Any] = {
        "complete": bool(pids) and len(readable) == len(pids),
        "readable_pid_count": len(readable),
        "pid_count": len(pids),
        "pss_bytes": None,
        "uss_bytes": None,
    }
    if result["complete"]:
        result["pss_bytes"] = int(
            round(sum(float(row["pss_mb"]) for row in readable) * 1024**2)
        )
        result["uss_bytes"] = int(
            round(sum(float(row["uss_mb"]) for row in readable) * 1024**2)
        )
    return result


def resource_authority_sample(
    root_pid: int, *, include_smaps: bool = False
) -> dict[str, Any]:
    process_tree = process_tree_sample(root_pid)
    cgroup = cgroup_snapshot(root_pid)
    dedicated_current = (
        cgroup["memory_current_bytes"] if cgroup["dedicated_job_cgroup"] else None
    )
    memory_authority = max(
        process_tree.rss_bytes,
        int(dedicated_current or 0),
    )
    dedicated_swap = (
        cgroup["swap_current_bytes"] if cgroup["dedicated_job_cgroup"] else None
    )
    job_no_swap = bool(
        process_tree.all_status_readable
        and process_tree.swap_bytes == 0
        and (dedicated_swap is None or dedicated_swap == 0)
    )
    process_tree_payload = process_tree.to_dict()
    if include_smaps:
        process_tree_payload["smaps"] = process_tree_smaps_sample(process_tree.pids)
    return {
        "process_tree": process_tree_payload,
        "job_cgroup": cgroup,
        "host_memory": wsl_memory_snapshot(),
        "global_swap": proc_swaps_snapshot(),
        "wsl_vm_global_swap_diagnostic": vmstat_swap_pages(),
        "memory_authority_bytes": memory_authority,
        "memory_authority_semantics": (
            "max(process-tree RSS, dedicated job cgroup memory.current when present)"
        ),
        "job_no_swap": job_no_swap,
        "formal_swap_semantics": (
            "process-tree VmSwap plus dedicated job cgroup swap; WSL-global pswp is diagnostic only"
        ),
        "mumps_ooc_is_swap": False,
        "windows_pagefile_is_linux_swap": False,
    }
