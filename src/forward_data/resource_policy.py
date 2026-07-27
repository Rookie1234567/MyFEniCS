"""Task001 host-resource rules and p6/h7.5 launch prediction."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any


GIB = 1024**3


def meminfo_bytes() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        result[key] = int(value.strip().split()[0]) * 1024
    return result


def task001_resource_limits(root: Path) -> dict[str, Any]:
    memory = meminfo_bytes()
    hard = min(int(10.5 * GIB), int(0.77 * memory["MemTotal"]))
    projection = int(0.90 * hard)
    disk_free = shutil.disk_usage(root).free
    swap_used = memory.get("SwapTotal", 0) - memory.get("SwapFree", 0)
    gates = {
        "mem_available_at_least_hard_plus_1gib": memory["MemAvailable"] >= hard + GIB,
        "swap_unused": swap_used == 0,
        "disk_free_at_least_20gib": disk_free >= 20 * GIB,
        "threads_per_rank_one": True,
        "one_forward_job": True,
    }
    return {
        "mem_total_bytes": memory["MemTotal"],
        "mem_available_bytes": memory["MemAvailable"],
        "swap_total_bytes": memory.get("SwapTotal", 0),
        "swap_used_bytes": swap_used,
        "disk_free_bytes": disk_free,
        "hard_ceiling_bytes": hard,
        "launch_projection_ceiling_bytes": projection,
        "gates": gates,
        "pass": all(gates.values()),
    }


def predict_p6_h7p5(*, measured_h10_peak_bytes: int) -> dict[str, Any]:
    """Three transparent estimates from fixed cell-count scaling."""

    if measured_h10_peak_bytes <= 0:
        raise ValueError("measured_h10_peak_bytes must be positive")
    h10_cells = 6 * 3 * 14
    h7p5_cells = 9 * 4 * 20
    ratio = h7p5_cells / h10_cells
    estimates = {
        "linear_cell_payload_bytes": int(measured_h10_peak_bytes * ratio),
        "central_sparse_fill_bytes": int(measured_h10_peak_bytes * ratio**1.20),
        "conservative_factor_fill_bytes": int(measured_h10_peak_bytes * ratio**1.50),
    }
    return {
        "h10_axis_counts": [6, 3, 14],
        "h7p5_axis_counts": [9, 4, 20],
        "cell_ratio": ratio,
        "measured_h10_peak_bytes": measured_h10_peak_bytes,
        "estimates": estimates,
        "central_estimate_bytes": estimates["central_sparse_fill_bytes"],
        "conservative_estimate_bytes": estimates["conservative_factor_fill_bytes"],
        "semantics": "planning estimates, not measured h7.5 memory",
    }
