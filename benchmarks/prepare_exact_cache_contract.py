"""Prepare an additional hash-bound cache contract after normal case review/fresh.

This command does not start FE, bypass the normal admission guard or reserve a
whole host. Re-run it immediately before a separately reviewed future launch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from src.runners.exact_cache_admission import choose_idle_physical_cpus
from src.solvers.parallel_tensor_cache import atomic_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--resolved-json", type=Path, required=True)
    p.add_argument("--workers", type=int, required=True)
    p.add_argument("--exclude-cpus", required=True)
    p.add_argument("--tensor-root", type=Path, required=True)
    p.add_argument("--carrier-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("preserve existing admission contract")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError(
            "freeze and commit source before preparing a formal launch contract"
        )
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    admission = choose_idle_physical_cpus(
        a.workers, excluded_cpus=[int(v) for v in a.exclude_cpus.split(",") if v]
    )
    payload = json.loads(a.resolved_json.read_text())
    doc = {
        "schema": "exact-cache-execution.v1",
        "source_sha": source,
        "resolved_payload_sha256": hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest(),
        "worker_cpus": [item["cpu"] for item in admission["selected"]],
        "tensor_root": str(a.tensor_root.resolve()),
        "carrier_root": str(a.carrier_root.resolve()),
        "cpu_admission": admission,
        "does_not_replace_case_fresh": True,
    }
    atomic_json(a.output, doc)
    print(
        json.dumps(
            {
                "path": str(a.output.resolve()),
                "sha256": hashlib.sha256(a.output.read_bytes()).hexdigest(),
                "worker_cpus": doc["worker_cpus"],
            }
        )
    )


if __name__ == "__main__":
    main()
