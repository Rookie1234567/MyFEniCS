from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from mpi4py import MPI

from src.validation.task035_mesh_backend_bakeoff import run_mesh_backend_bakeoff


def _scalar_identity(record: Mapping[str, Any]) -> dict[str, float]:
    tetra = record["tetra_marked_refinement_control"]
    return {
        "coarse_cells": float(tetra["coarse_cells"]),
        "marked_coarse_cells": float(tetra["marked_coarse_cells"]),
        "refined_cells": float(tetra["refined_cells"]),
        "minimum_signed_volume_proxy": float(tetra["minimum_signed_volume_proxy"]),
        "inside_marked_region_mean_volume": float(
            tetra["inside_marked_region_mean_volume"]
        ),
        "outside_marked_region_mean_volume": float(
            tetra["outside_marked_region_mean_volume"]
        ),
        "coarse_Nedelec_interpolation_error": float(
            tetra["coarse_Nedelec_interpolation_error"]
        ),
        "refined_Nedelec_interpolation_error": float(
            tetra["refined_Nedelec_interpolation_error"]
        ),
    }


def compare_serial_mpi2(
    serial: Mapping[str, Any], mpi2: Mapping[str, Any]
) -> dict[str, Any]:
    failures = []
    left = _scalar_identity(serial)
    right = _scalar_identity(mpi2)
    differences = {}
    for name in left:
        delta = abs(left[name] - right[name])
        tolerance = 2.0e-10 * max(1.0, abs(left[name]), abs(right[name]))
        if (
            not math.isfinite(left[name])
            or not math.isfinite(right[name])
            or delta > tolerance
        ):
            failures.append(name)
            differences[name] = {
                "serial": left[name],
                "mpi2": right[name],
                "delta": delta,
                "tolerance": tolerance,
            }
    for record in (serial, mpi2):
        if record["status"] != "phase_d_complete_controlled_negative":
            failures.append("phase_d_status")
    return {
        "schema_version": "task035.phase-d-mpi-identity.v1",
        "status": "serial_mpi2_identity_pass"
        if not failures
        else "serial_mpi2_identity_fail",
        "pass": not failures,
        "failures": failures,
        "differences": differences,
    }


def _write(record: Mapping[str, Any], output: Path | None) -> None:
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if MPI.COMM_WORLD.rank == 0:
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(payload, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args(argv)
    if args.compare:
        serial = json.loads(args.compare[0].read_text(encoding="utf-8"))
        mpi2 = json.loads(args.compare[1].read_text(encoding="utf-8"))
        record = compare_serial_mpi2(serial, mpi2)
    else:
        record = run_mesh_backend_bakeoff()
    _write(record, args.output)
    return 0 if record.get("pass", record["phase_d_internal_gate"] == "complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
