from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from mpi4py import MPI

from src.validation.task035_hcurl_estimator_fixtures import build_fixture_summary


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "fixture_summary.json"
)


def mpi_identity_probe() -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    canonical_contributions = (
        (3, 0.02),
        (7, 0.01),
        (19, 0.03),
        (41, 0.04),
    )
    local_sum = math.fsum(
        value
        for cell_id, value in canonical_contributions
        if cell_id % comm.size == comm.rank
    )
    global_sum = comm.allreduce(local_sum, op=MPI.SUM)
    reference = math.fsum(value for _, value in canonical_contributions)
    return {
        "mpi_size": comm.size,
        "global_sum": global_sum,
        "reference_sum": reference,
        "absolute_difference": abs(global_sum - reference),
        "pass": abs(global_sum - reference) <= 1.0e-14,
        "reduction": "scalar_allreduce_no_full_vector_gather",
    }


def build_record() -> dict[str, Any]:
    record = build_fixture_summary()
    probe = mpi_identity_probe()
    record["mpi_identity"] = probe
    if not probe["pass"]:
        record["status"] = "fixture_negative"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run hermetic Task035 analytic/manufactured estimator fixtures."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write rank-zero JSON to this path; omit for stdout-only operation.",
    )
    args = parser.parse_args()
    comm = MPI.COMM_WORLD
    record = build_record()
    if comm.rank == 0:
        payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(payload, end="")
    return 0 if record["status"] == "algebraic_precursor_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
