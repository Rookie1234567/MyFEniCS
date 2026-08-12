"""WSL/job resource authorities used by Task034 formal runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

GIB = 1024**3


def _read_int(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return None if value == "max" else int(value)
    except (OSError, ValueError):
        return None


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
    dedicated = bool(relative not in {".", "", "init.scope"})
    return {
        "path": f"/{relative}" if relative not in {".", ""} else "/",
        "readable": (path / "memory.current").is_file(),
        "dedicated_job_cgroup": dedicated,
        "member_count": len(members),
        "memory_current_bytes": _read_int(path / "memory.current"),
        "memory_peak_bytes": _read_int(path / "memory.peak"),
        "memory_limit_bytes": _read_int(path / "memory.max"),
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
    return {"pswpin_pages": values.get("pswpin"), "pswpout_pages": values.get("pswpout")}


def wsl_memory_snapshot() -> dict[str, int | None]:
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
    }


def effective_memory_limit(
    *, user_limit_gib: float = 220.0, reserve_gib: float = 24.0
) -> dict[str, Any]:
    memory = wsl_memory_snapshot()
    total = memory["mem_total_bytes"]
    available = memory["mem_available_bytes"]
    candidates = {
        "user_limit_bytes": int(user_limit_gib * GIB),
        "wsl_total_85_percent_bytes": (
            None if total is None else int(0.85 * total)
        ),
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _status_memory_kib(
    fields: Mapping[str, str], statm_fields: Sequence[str] | None = None
) -> tuple[int | None, int | None]:
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
    elif (
        rss_kib is None
        and swap_kib is None
        and "VmRSS" not in fields
        and "VmSwap" not in fields
        and statm_fields is not None
    ):
        try:
            address_space_pages = int(statm_fields[0])
            resident_pages = int(statm_fields[1])
        except (IndexError, ValueError):
            pass
        else:
            if address_space_pages == 0 and resident_pages == 0:
                rss_kib = 0
                swap_kib = 0
    return rss_kib, swap_kib


def process_tree_sample(root_pid: int) -> ProcessTreeSample:
    """Sample RSS and VmSwap for the root and every live descendant."""

    processes: dict[int, tuple[int, int | None, int | None]] = {}
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            lines = (entry / "status").read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines()
        except OSError:
            continue
        fields = {
            key: value.strip()
            for line in lines
            if ":" in line
            for key, value in [line.split(":", 1)]
        }
        try:
            ppid = int(fields.get("PPid", "0"))
        except ValueError:
            ppid = 0
        rss_kib, swap_kib = _status_memory_kib(fields)
        if (
            rss_kib is None
            and swap_kib is None
            and "VmRSS" not in fields
            and "VmSwap" not in fields
        ):
            try:
                statm_fields = (entry / "statm").read_text(
                    encoding="utf-8", errors="ignore"
                ).split()
            except OSError:
                statm_fields = None
            rss_kib, swap_kib = _status_memory_kib(fields, statm_fields)
        processes[pid] = (ppid, rss_kib, swap_kib)
    selected = {int(root_pid)}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss, _swap) in processes.items():
            if pid not in selected and ppid in selected:
                selected.add(pid)
                changed = True
    observed = [processes[pid] for pid in selected if pid in processes]
    readable = bool(observed) and all(
        rss is not None and swap is not None for _ppid, rss, swap in observed
    )
    return ProcessTreeSample(
        root_pid=int(root_pid),
        pids=tuple(sorted(pid for pid in selected if pid in processes)),
        rss_bytes=sum(int(rss or 0) * 1024 for _ppid, rss, _swap in observed),
        swap_bytes=sum(int(swap or 0) * 1024 for _ppid, _rss, swap in observed),
        all_status_readable=readable,
    )


def resource_authority_sample(root_pid: int) -> dict[str, Any]:
    process_tree = process_tree_sample(root_pid)
    cgroup = cgroup_snapshot(root_pid)
    dedicated_current = (
        cgroup["memory_current_bytes"]
        if cgroup["dedicated_job_cgroup"]
        else None
    )
    memory_authority = max(
        process_tree.rss_bytes,
        int(dedicated_current or 0),
    )
    dedicated_swap = (
        cgroup["swap_current_bytes"]
        if cgroup["dedicated_job_cgroup"]
        else None
    )
    job_no_swap = bool(
        process_tree.all_status_readable
        and process_tree.swap_bytes == 0
        and (dedicated_swap is None or dedicated_swap == 0)
    )
    return {
        "process_tree": process_tree.to_dict(),
        "job_cgroup": cgroup,
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
