"""Additional CPU admission for opt-in tensor workers; not a PDE fresh replacement."""

from __future__ import annotations

import os
import time
from pathlib import Path


def _cpu_sample():
    result = {}
    for line in Path("/proc/stat").read_text().splitlines():
        f = line.split()
        if f[0].startswith("cpu") and f[0][3:].isdigit():
            result[int(f[0][3:])] = list(map(int, f[1:9]))
    return result


def physical_core(cpu):
    root = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
    return (
        (root / "physical_package_id").read_text().strip(),
        (root / "core_id").read_text().strip(),
    )


def choose_idle_physical_cpus(
    count, *, excluded_cpus=(), sample_seconds=3.0, maximum_busy=0.15
):
    if count not in (1, 4, 8, 16, 32) or sample_seconds < 1:
        raise ValueError("unsupported worker count or CPU sampling interval")
    available = 1024 * int(
        next(
            line.split()[1]
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
    )
    if available < 68719476736:
        raise RuntimeError("host available floor not satisfied")
    before = _cpu_sample()
    time.sleep(sample_seconds)
    after = _cpu_sample()
    used = {physical_core(int(c)) for c in excluded_cpus}
    selected = []
    for busy, cpu in sorted(
        (
            1
            - (after[c][3] + after[c][4] - before[c][3] - before[c][4])
            / max(1, sum(after[c]) - sum(before[c])),
            c,
        )
        for c in os.sched_getaffinity(0)
    ):
        key = physical_core(cpu)
        if busy <= maximum_busy and key not in used:
            selected.append({"cpu": cpu, "physical_core": key, "busy_fraction": busy})
            used.add(key)
            if len(selected) == count:
                return {
                    "selected": selected,
                    "available_bytes": available,
                    "sample_seconds": sample_seconds,
                }
    raise RuntimeError(
        f"only {len(selected)} idle unexcluded physical cores, requested {count}"
    )
