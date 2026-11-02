"""Cold 4/8/16/32-process scaling over 32 distinct real Gate-CD q21 classes.

The four-process batch is the all-class byte reference; serial correctness is
separately witnessed by the real mapped-mesh test and serial/two-worker probe.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

from src.common.gate_cd_materials import GATE_CD_REGION_TAGS
from src.geometry.task40_gate_cd_mesh_plan import (
    _cell_midpoint,
    build_gate_cd_plan,
    gate_cd_material_label,
)
from src.solvers.parallel_tensor_cache import (
    atomic_json,
    key_for,
    load_shard,
    run_batch,
)


def core(cpu):
    p = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
    return ((p / "physical_package_id").read_text(), (p / "core_id").read_text())


def cpu_sample():
    return {
        int(a[0][3:]): list(map(int, a[1:9]))
        for line in Path("/proc/stat").read_text().splitlines()
        if (a := line.split())[0][3:].isdigit()
    }


def admit(count, protected):
    excluded = {core(cpu) for cpu in protected}
    a = cpu_sample()
    time.sleep(3)
    b = cpu_sample()
    answer = []
    for busy, c in sorted(
        (1 - (b[c][3] + b[c][4] - a[c][3] - a[c][4]) / max(1, sum(b[c]) - sum(a[c])), c)
        for c in os.sched_getaffinity(0)
    ):
        if busy < 0.15 and core(c) not in excluded:
            answer.append({"cpu": c, "busy_fraction": busy})
            excluded.add(core(c))
            if len(answer) == count:
                return answer
    return None


def jobs_from_actual_geometry(template):
    plan = build_gate_cd_plan()
    classes = {}
    for k in range(23):
        for j in range(240):
            for i in range(5):
                z0, z1 = plan.z[k : k + 2]
                xb = plan.x_sections[k, i : i + 2]
                xt = plan.x_sections[k + 1, i : i + 2]
                yb = plan.y_sections[k, j : j + 2]
                yt = plan.y_sections[k + 1, j : j + 2]
                tag = GATE_CD_REGION_TAGS[
                    gate_cd_material_label(*_cell_midpoint(xb, xt, yb, yt, z0, z1))
                ]
                coords = np.array(
                    [
                        [x, y, z]
                        for z, xs, ys in [(z0, xb, yb), (z1, xt, yt)]
                        for y in ys
                        for x in xs
                    ]
                )
                coords -= coords.min(axis=0)
                coords[coords == 0] = 0
                key = (tag, *coords.ravel())
                classes.setdefault(key, coords)
    ordered = sorted(classes)
    indices = np.linspace(0, len(ordered) - 1, 32, dtype=int)
    jobs = [
        {
            **template,
            "tag": int(ordered[i][0]),
            "coordinates": classes[ordered[i]].tolist(),
        }
        for i in indices
    ]
    assert len({key_for(job) for job in jobs}) == 32
    return jobs, len(classes)


def main(args):
    out = args.directory.resolve()
    out.mkdir(parents=True, exist_ok=False)
    template = json.loads(args.template_receipt.read_text())["jobs"][0]
    jobs, total = jobs_from_actual_geometry(template)
    atomic_json(out / "jobs.json", jobs)
    report = {
        "status": "RUNNING",
        "total_exact_geometry_classes": total,
        "benchmark_classes": 32,
        "q": 21,
        "degree": 6,
        "runs": [],
        "comparison": "all 32 tensors compared bitwise to cold four-worker batch; independent serial equality checked separately",
        "protected_cpus": [18, 5, 10, 44, 4, 6, 11, 17, 2, 12, 31, 1],
    }
    os.nice(10)
    for n in (4, 8, 16, 32):
        while (cpus := admit(n, report["protected_cpus"])) is None:
            report["phase"] = f"WAIT_IDLE_{n}_PHYSICAL_CORES"
            atomic_json(out / "report.json", report)
            time.sleep(45)
        report["phase"] = f"COLD_{n}"
        atomic_json(out / "report.json", report)
        start = time.perf_counter()
        start_ns = time.time_ns()
        results = run_batch(
            jobs,
            out / f"cold-{n}",
            [c["cpu"] for c in cpus],
            timeout=None,
            progress=lambda done, total, last, n=n: atomic_json(
                out / f"progress-{n}.json", {"done": done, "total": total, "last": last}
            ),
        )
        elapsed = time.perf_counter() - start
        end_ns = time.time_ns()
        comparisons = []
        for job in jobs:
            baseline = load_shard(out / "cold-4", job)
            observed = load_shard(out / f"cold-{n}", job)
            comparisons.append(
                baseline["metadata"]["payload_sha256"]
                == observed["metadata"]["payload_sha256"]
            )
        assert all(comparisons), "tensor bytes changed with worker count"
        warm_start = time.perf_counter()
        warm_start_ns = time.time_ns()
        hits = run_batch(
            jobs, out / f"cold-{n}", [c["cpu"] for c in cpus], timeout=None
        )
        warm_seconds = time.perf_counter() - warm_start
        assert all(v["cache_hit"] for v in hits.values())
        record = {
            "workers": n,
            "cpus": cpus,
            "cold_seconds": elapsed,
            "started_ns": start_ns,
            "ended_ns": end_ns,
            "warm_seconds": warm_seconds,
            "warm_started_ns": warm_start_ns,
            "warm_ended_ns": time.time_ns(),
            "all_32_bitwise_equal": True,
            "cold_cache_hits": sum(v["cache_hit"] for v in results.values()),
            "worker_peak_max_bytes": max(
                v.get("worker_peak_rss_bytes", 0) for v in results.values()
            ),
            "kernel_cpu_sum_seconds": sum(
                v.get("kernel_cpu_seconds", 0) for v in results.values()
            ),
            "warning": "worker_peak_max is not simultaneous process-tree RSS; use watchdog interval samples",
        }
        report["runs"].append(record)
        atomic_json(out / "report.json", report)
    report["phase"] = "COMPLETE"
    report["status"] = "PASS_32_REAL_CLASSES_SCALING_AND_DISK_REUSE"
    atomic_json(out / "report.json", report)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--template-receipt", type=Path, required=True)
    main(p.parse_args())
