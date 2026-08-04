"""Small bridge executed with the immutable Task005 forward worktree.

The driver is kept in the surrogate repository, but inserts the read-only
forward worktree at the front of ``sys.path`` before importing any solver
module.  Consequently the actual preflight, runner, and compact record come
from the exact qualified forward SHA rather than from the development tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forward-root", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--height", type=float)
    parser.add_argument("--width", type=float)
    parser.add_argument("--grazing", type=float)
    parser.add_argument("--azimuth", type=float)
    parser.add_argument("--design-id", default="task005_m1_audit_v1")
    parser.add_argument("--design-index", type=int, default=0)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()
    root = args.forward_root.resolve()
    sys.path.insert(0, str(root))

    from src.forward_data.provenance import canonical_hash, file_hash
    from src.forward_data.task002_full3d import (
        formal_record_status, run_formal_task002_full3d,
    )
    from src.forward_data.task002_m4 import formal_record_to_production_sample
    from src.forward_data.task002_campaign import formal_preflight
    from src.forward_data.task002_schema import Task002ForwardParameters

    preflight = formal_preflight(root, args.baseline_sha)
    if args.preflight_only:
        print(json.dumps({"status": "preflight_pass", "preflight": preflight}, indent=2))
        return 0
    if None in (args.height, args.width, args.grazing, args.azimuth):
        parser.error("geometry and angle are required unless --preflight-only is used")
    parameters = Task002ForwardParameters(
        height_nm=float(args.height), width_x_nm=float(args.width),
        grazing_deg=float(args.grazing), azimuth_deg=float(args.azimuth),
        model_id="S_PROD_FULL3D_STATIC_P5_H10_NY4",
    )
    parameters.validate()
    run_directory = args.run_directory.resolve()
    result, execution_path = run_formal_task002_full3d(
        parameters, root=root, baseline_sha=args.baseline_sha,
        run_directory=run_directory, timeout_seconds=float(args.timeout_seconds),
        output_profile="compact_surrogate_record", mumps_icntl_14=40,
    )
    status = formal_record_status(run_directory, result)
    formal_path = run_directory / "results/task002_full3d_record.json"
    sample_path = run_directory / "task005_production_sample.json"
    sample_written = False
    if status == "measured_pass" and formal_path.is_file():
        point_tuple = [float(args.height), float(args.width), float(args.grazing), float(args.azimuth)]
        manifest_row = {
            "design_id": args.design_id, "design_index": int(args.design_index),
            "split": "audit", "point_tuple": point_tuple,
            "point_hash": canonical_hash({
                "design_id": args.design_id, "design_index": int(args.design_index),
                "point_tuple": point_tuple,
            }), "source_sha": args.baseline_sha, "status": "measured_pass",
        }
        sample = formal_record_to_production_sample(
            manifest_row=manifest_row, formal_record_path=formal_path,
            execution_path=execution_path,
        )
        sample_path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n")
        sample_written = True
    summary = {
        "schema_version": "task005.forward-driver-result.v1",
        "status": status, "run_directory": str(run_directory),
        "execution_path": str(execution_path),
        "formal_record_path": str(formal_path),
        "sample_path": str(sample_path) if sample_written else None,
        "formal_record_sha256": file_hash(formal_path) if formal_path.is_file() else None,
        "execution_sha256": file_hash(execution_path) if execution_path.is_file() else None,
        "watchdog": asdict(result), "preflight": preflight,
        "source_sha": args.baseline_sha, "parameters": parameters.as_dict(),
    }
    (run_directory / "task005_driver_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if status == "measured_pass" and sample_written else 2


if __name__ == "__main__":
    raise SystemExit(main())
