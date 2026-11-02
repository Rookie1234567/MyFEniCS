"""Join bounded benchmark phase times to sampled simultaneous tree resources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.solvers.parallel_tensor_cache import atomic_json, digest


def summarize(samples, start, end, *, monotonic=False):
    # NUMA observations are cached for five seconds. Only the initial fresh
    # observation calibrates the watchdog origin; never treat a cached NUMA
    # timestamp as the timestamp of a later process sample.
    origin = (
        samples[0]["node_memory_observation"]["sampled_monotonic"]
        - samples[0]["elapsed_seconds"]
        if monotonic and samples
        else 0.0
    )
    selected = []
    for sample in samples:
        timestamp = (
            origin + sample["elapsed_seconds"] if monotonic else sample["timestamp_ns"]
        )
        if start <= timestamp <= end:
            selected.append(sample)
    if not selected:
        return {"status": "NOT_SAMPLED", "samples": 0}
    return {
        "status": "SAMPLED",
        "samples": len(selected),
        "simultaneous_tree_rss_peak_bytes": max(s["rss_bytes"] for s in selected),
        "simultaneous_tree_swap_peak_bytes": max(s["swap_bytes"] for s in selected),
        "minimum_effective_available_bytes": min(
            s["resource_policy_observations"]["effective_available_bytes"]
            for s in selected
        ),
        "all_samples_readable": all(s["all_status_readable"] for s in selected),
        "any_warning": any(s["warning"] for s in selected),
        "maximum_live_exec_workers": max(
            sum("parallel_tensor_cache.py --job" in m["cmdline"] for m in s["members"])
            for s in selected
        ),
        "scope": "same-instant supervisor plus descendants; not sum of per-process peaks",
        "phase_clock": (
            "watchdog elapsed calibrated to initial fresh NUMA monotonic observation; "
            "sub-sample timing approximation"
            if monotonic
            else "recorded wall timestamp_ns"
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    if report.get("status", "").startswith("RUNNING"):
        raise ValueError("benchmark is not finished")
    with args.resources.open() as stream:
        samples = [json.loads(line) for line in stream if line.strip()]
    results = []
    for record in report["runs"]:
        if "started_ns" in record:
            resources = summarize(samples, record["started_ns"], record["ended_ns"])
            warm = summarize(
                samples, record["warm_started_ns"], record["warm_ended_ns"]
            )
            results.append({**record, "resources": resources, "warm_resources": warm})
        else:
            resources = summarize(
                samples,
                record["started_monotonic"],
                record["ended_monotonic"],
                monotonic=True,
            )
            results.append({**record, "resources": resources})
    atomic_json(
        args.output,
        {
            "benchmark_status": report["status"],
            "report_sha256": digest(args.report),
            "resources_sha256": digest(args.resources),
            "runs": results,
            "pss": "disabled; RSS sums can include shared pages more than once",
        },
    )


if __name__ == "__main__":
    main()
