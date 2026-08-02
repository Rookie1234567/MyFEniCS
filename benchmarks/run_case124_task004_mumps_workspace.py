"""Run the reviewed Task004 MUMPS workspace ladder and five anchors.

The script is deliberately fail-closed: every attempt gets a new directory,
the first non-workspace numerical failure stops the run, and a workspace value
is frozen only after two consecutive fresh-process full solves pass.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from src.forward_data.provenance import canonical_hash
from src.forward_data.task002_full3d import (
    TASK002_MUMPS_ICNTL_14_VALUES,
    formal_record_status,
    run_formal_task002_full3d,
)
from src.forward_data.task002_m4 import PRODUCTION_MODEL_ID
from src.forward_data.task002_schema import Task002ForwardParameters


ANCHORS = (
    (0.5, 0.0), (0.5, 90.0), (10.0, 0.0), (10.0, 90.0), (5.25, 45.0),
)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _parameters(grazing: float, azimuth: float) -> Task002ForwardParameters:
    return Task002ForwardParameters(
        height_nm=120.0, width_x_nm=17.0,
        grazing_deg=grazing, azimuth_deg=azimuth,
        model_id=PRODUCTION_MODEL_ID,
    )


def _watchdog_safe(result: Any) -> bool:
    return bool(
        result.status == "completed" and result.return_code == 0
        and result.peak_swap_bytes == 0 and result.cleanup_complete
    )


def _attempt(
    *, root: Path, baseline_sha: str, artifact_root: Path,
    label: str, parameters: Task002ForwardParameters, icntl: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    run_directory = artifact_root / label
    result, execution_path = run_formal_task002_full3d(
        parameters, root=root, baseline_sha=baseline_sha,
        run_directory=run_directory, timeout_seconds=timeout_seconds,
        output_profile="compact_surrogate_record", mumps_icntl_14=icntl,
    )
    status = formal_record_status(run_directory, result)
    summary_path = run_directory / "results/run_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    inventory = summary.get("stage4_dtn_factor_inventory") or {}
    return {
        "label": label, "icntl_14": icntl, "status": status,
        "run_directory": str(run_directory.resolve()),
        "execution_path": str(execution_path.resolve()),
        "watchdog": asdict(result),
        "safe_resource_gate": _watchdog_safe(result),
        "requested_icntl_14": icntl,
        "actual_icntl_14": inventory.get("mumps_icntl_14_observed_percent"),
        "workspace_verification": inventory.get("mumps_workspace_relaxation_verified"),
        "failure_stage": summary.get("failure_stage"),
        "direct_solve_exception": summary.get("direct_solve_exception"),
        "formal_record_present": (run_directory / "results/task002_full3d_record.json").is_file(),
    }


def _anchor_manifest(*, baseline_sha: str, artifact_root: Path) -> dict[str, Any]:
    design_id = "task004_anchor_training_v2"
    samples = {}
    for index, (grazing, azimuth) in enumerate(ANCHORS):
        point = [120.0, 17.0, grazing, azimuth]
        samples[f"{design_id}:{index:04d}"] = {
            "design_id": design_id, "design_index": index, "split": "train",
            "point_tuple": point,
            "point_hash": canonical_hash({
                "design_id": design_id, "design_index": index,
                "point_tuple": point,
            }),
            "source_sha": baseline_sha, "status": "reserved",
            "attempt_number": 0, "run_directory": None, "attempts": [],
        }
    return {
        "schema_version": "task004.m0r-anchor-campaign.v1",
        "baseline_sha": baseline_sha,
        "designs": {design_id: {
            "design_id": design_id, "split": "train", "point_count": 5,
            "source_sha": baseline_sha,
            "artifact_root": str(artifact_root.resolve()),
        }},
        "samples": samples, "stop_reason": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--skip-anchors", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(); artifact_root = args.artifact_root.resolve()
    ladder: list[dict[str, Any]] = []
    selected: int | None = None
    stop_reason: str | None = None
    parameters = _parameters(*ANCHORS[0])

    for icntl in TASK002_MUMPS_ICNTL_14_VALUES:
        candidate_passes = 0
        for attempt in (1, 2):
            row = _attempt(
                root=root, baseline_sha=args.baseline_sha,
                artifact_root=artifact_root / "ladder" / f"icntl14_{icntl}",
                label=f"attempt_{attempt:02d}", parameters=parameters,
                icntl=icntl, timeout_seconds=args.timeout_seconds,
            )
            ladder.append(row)
            _write(artifact_root / "mumps_workspace_ladder.json", {
                "schema_version": "task004.m0r-mumps-ladder.v1",
                "baseline_sha": args.baseline_sha,
                "original_failure_point": [120.0, 17.0, 0.5, 0.0],
                "ladder": ladder, "selected_icntl_14": selected,
                "stop_reason": stop_reason,
            })
            if not row["safe_resource_gate"]:
                stop_reason = f"resource_gate:{icntl}:{attempt}"
                break
            if row["status"] == "measured_pass":
                candidate_passes += 1
                continue
            if row["status"] == "failed_direct_lu_workspace_underestimate" and icntl != 120:
                stop_reason = f"workspace_underestimate:{icntl}:{attempt}"
                break
            stop_reason = f"first_unexplained_failure:{row['status']}:{icntl}:{attempt}"
            break
        if stop_reason and not stop_reason.startswith("workspace_underestimate"):
            break
        if candidate_passes == 2:
            selected = icntl
            stop_reason = None
            break
        stop_reason = None

    ladder_result = {
        "schema_version": "task004.m0r-mumps-ladder.v1",
        "baseline_sha": args.baseline_sha,
        "original_failure_point": [120.0, 17.0, 0.5, 0.0],
        "ladder": ladder, "selected_icntl_14": selected,
        "status": "pass" if selected is not None else "controlled_stop",
        "stop_reason": stop_reason,
    }
    _write(artifact_root / "mumps_workspace_ladder.json", ladder_result)
    if selected is None or args.skip_anchors:
        print(json.dumps(ladder_result, indent=2))
        return 0 if selected is not None else 2

    manifest = _anchor_manifest(baseline_sha=args.baseline_sha, artifact_root=artifact_root)
    for index, (grazing, azimuth) in enumerate(ANCHORS):
        key = f"task004_anchor_training_v2:{index:04d}"
        row = manifest["samples"][key]
        row["attempt_number"] = 1
        row["status"] = "running"
        run_result = _attempt(
            root=root, baseline_sha=args.baseline_sha,
            artifact_root=artifact_root / "anchors" / f"{index:04d}",
            label="attempt_01", parameters=_parameters(grazing, azimuth),
            icntl=selected, timeout_seconds=args.timeout_seconds,
        )
        row["run_directory"] = run_result["run_directory"]
        row["attempts"] = [run_result]
        row["status"] = run_result["status"]
        _write(artifact_root / "anchor_campaign_manifest.json", manifest)
        if row["status"] != "measured_pass":
            manifest["stop_reason"] = f"first_anchor_failure:{key}:{row['status']}"
            _write(artifact_root / "anchor_campaign_manifest.json", manifest)
            print(json.dumps({"ladder": ladder_result, "anchors": manifest}, indent=2))
            return 2
    print(json.dumps({"ladder": ladder_result, "anchors": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
