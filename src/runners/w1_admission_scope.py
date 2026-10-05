"""Identity-bound optional search scope; admission thresholds remain elsewhere."""

import hashlib
import json
import os
from pathlib import Path


def body_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cpuset_cpus():
    from benchmarks.task034_wsl_resources import current_cgroup_path

    path = current_cgroup_path()
    if path is None:
        raise ValueError("W1_CPUSET_LIMIT_UNKNOWN")
    while path.is_relative_to("/sys/fs/cgroup"):
        file = path / "cpuset.cpus.effective"
        if file.is_file() and (text := file.read_text().strip()):
            result = set()
            for item in text.split(","):
                pair = item.split("-")
                result.update(range(int(pair[0]), int(pair[-1]) + 1))
            return result
        if path == Path("/sys/fs/cgroup"):
            break
        path = path.parent
    raise ValueError("W1_CPUSET_LIMIT_UNKNOWN")


def capture_scope(facts):
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    scope = {
        "schema": "w1-allowed-core-scope.v1",
        "owner_uid": os.getuid(),
        "pid": os.getpid(),
        "start_ticks": int(fields[19]),
        "allowed_cpus": sorted(os.sched_getaffinity(0)),
        "cpuset_cpus": sorted(cpuset_cpus()),
        "topology": facts["topology"],
        "preferred_cpu": facts["cpu"],
    }
    if scope["allowed_cpus"] != [row["cpu"] for row in facts["topology"]]:
        raise ValueError("W1_SCOPE_CAPTURE_AFFINITY_CHANGED")
    return {**scope, "body_sha256": body_sha(scope)}


def validate_scope(scope, *, current_cpuset=None, proc_root=Path("/proc"), uid=None):
    body = {k: v for k, v in scope.items() if k != "body_sha256"}
    current = cpuset_cpus() if current_cpuset is None else set(current_cpuset)
    owner = os.getuid() if uid is None else uid
    cpus = scope.get("allowed_cpus", [])
    if (
        scope.get("schema") != "w1-allowed-core-scope.v1"
        or scope.get("body_sha256") != body_sha(body)
        or scope.get("owner_uid") != owner
        or type(scope.get("pid")) is not int
        or scope["pid"] <= 0
        or type(scope.get("start_ticks")) is not int
        or scope["start_ticks"] <= 0
        or not cpus
        or cpus != sorted(set(cpus))
        or any(type(cpu) is not int for cpu in cpus)
        or cpus != [row["cpu"] for row in scope.get("topology", [])]
        or not set(cpus) <= set(scope.get("cpuset_cpus", []))
    ):
        raise ValueError("W1_UNVERIFIED_ALLOWED_CORE_SCOPE")
    process = proc_root / str(scope["pid"])
    if process.exists():
        fields = (process / "stat").read_text().rsplit(")", 1)[1].split()
        if int(fields[19]) != scope["start_ticks"] or process.stat().st_uid != owner:
            raise ValueError("W1_SCOPE_PID_REUSED_OR_OWNER_CHANGED")
    # The exited outer launcher remains a hash-bound historical capture, not
    # a live process permit. Live server/pane/socket are checked separately.
    allowed = sorted(set(cpus) & current)
    if not allowed:
        raise ValueError("W1_SCOPE_OUTSIDE_CURRENT_CPUSET")
    return allowed


def exclusion_reasons(topology, neighbors, fractions, thread_deltas):
    reasons = {}
    for row in topology:
        denied = []
        for sibling in row["siblings"]:
            if fractions.get(sibling, 0) > 0.05:
                denied.append(
                    {
                        "kind": "busy_cpu_or_SMT",
                        "cpu": sibling,
                        "fraction": fractions[sibling],
                    }
                )
            for process in neighbors:
                for thread in process["threads"]:
                    narrow = len(thread["affinity"]) <= 16
                    blocked = thread["affinity"] if narrow else [thread["cpu"]]
                    if sibling in blocked and (
                        narrow or thread_deltas.get(thread["tid"], 1) > 0
                    ):
                        denied.append(
                            {
                                "kind": "reserved_narrow_thread"
                                if narrow
                                else "active_wide_thread",
                                "pid": process["pid"],
                                "start_ticks": process["start_ticks"],
                                "tid": thread["tid"],
                                "cpu": sibling,
                            }
                        )
        reasons[str(row["cpu"])] = denied
    return reasons
