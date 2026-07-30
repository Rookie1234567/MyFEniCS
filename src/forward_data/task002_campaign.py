"""Design-bound, resume-safe Task002 Ny4 p5-only production campaign v4."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .forward_model import _abi_identity
from .provenance import canonical_hash, file_hash, source_identity
from .resource_policy import task001_resource_limits
from .task002_m4 import (
    design_point_hash, load_frozen_design, parameters_from_design_point,
)
from .task002_schema import Task002ForwardParameters


CAMPAIGN_SCHEMA_VERSION = "task002.s-p5-ny4-design-campaign.v4"
ALLOWED_STATUSES = {
    "reserved", "running", "measured_pass", "failed_numerical_gate",
    "controlled_stop_resource", "interrupted_retryable",
}


def sample_key(parameters: Task002ForwardParameters) -> str:
    return canonical_hash(parameters.as_dict())


def task002_hybrid_command(*_args, **_kwargs) -> list[str]:
    raise RuntimeError("Task002 Hybrid production route is hard quarantined")


def formal_preflight(root: Path, baseline_sha: str) -> dict[str, Any]:
    identity = source_identity(root)
    if identity["dirty"]:
        raise RuntimeError("Task002 formal PDE requires a clean source tree")
    if identity["source_sha"] != baseline_sha or len(baseline_sha) != 40:
        raise RuntimeError("Task002 formal PDE baseline SHA mismatch")
    resources = task001_resource_limits(root)
    if not resources["pass"]:
        raise RuntimeError(f"Task002 resource preflight failed: {resources['gates']}")
    return {"source": identity, "abi": _abi_identity(root), "resources": resources}


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def load_manifest(path: Path, *, baseline_sha: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "baseline_sha": baseline_sha, "designs": {}, "samples": {},
            "stop_reason": None,
        }
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise ValueError("Task002 Ny4 campaign v4 schema mismatch")
    if manifest.get("baseline_sha") != baseline_sha:
        raise ValueError("Task002 campaign baseline mismatch")
    return manifest


def _row_key(design_id: str, design_index: int) -> str:
    return f"{design_id}:{design_index:04d}"


def register_design(
    manifest: dict[str, Any], *, design: dict[str, Any], design_path: Path,
    split: str,
) -> None:
    design_id = design["design_id"]
    identity = {
        "design_id": design_id, "split": split,
        "design_file": str(design_path.resolve()),
        "design_file_sha256": file_hash(design_path),
        "point_tuple_sha256": design["point_tuple_sha256"],
        "point_count": design["point_count"], "source_sha": design["source_sha"],
        "parameter_schema_version": design["parameter_schema_version"],
        "observable_schema_version": design["observable_schema_version"],
        "production_model_id": design["production_model_id"],
        "production_solver_route_id": design["production_solver_route_id"],
    }
    existing = manifest["designs"].get(design_id)
    if existing is not None and existing != identity:
        raise ValueError("campaign design registration is immutable")
    manifest["designs"][design_id] = identity
    for index, point in enumerate(design["points"]):
        key = _row_key(design_id, index)
        point_values = [float(value) for value in (
            point["height_nm"], point["width_x_nm"], point["grazing_deg"],
            point["azimuth_deg"],
        )]
        expected = {
            "design_id": design_id, "design_index": index, "split": split,
            "point_tuple": point_values,
            "point_hash": design_point_hash(
                design_id=design_id, design_index=index, point=point,
            ),
            "source_sha": design["source_sha"], "status": "reserved",
            "attempt_number": 0, "run_directory": None, "attempts": [],
        }
        current = manifest["samples"].get(key)
        if current is None:
            manifest["samples"][key] = expected
        else:
            for field in ("design_id", "design_index", "split", "point_tuple",
                          "point_hash", "source_sha"):
                if current.get(field) != expected[field]:
                    raise ValueError(f"campaign frozen row changed: {key}/{field}")


def _artifacts_pass(run_directory: Path) -> bool:
    record_path = run_directory / "results/task002_full3d_record.json"
    execution_path = run_directory / "execution.json"
    if not record_path.is_file() or not execution_path.is_file():
        return False
    record = json.loads(record_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    watchdog = execution.get("watchdog", {})
    return bool(
        record.get("gates") and all(record["gates"].values())
        and watchdog.get("status") == "completed"
        and watchdog.get("return_code") == 0
        and watchdog.get("peak_swap_bytes") == 0
        and watchdog.get("cleanup_complete")
    )


def recover_or_retry_row(row: dict[str, Any]) -> str:
    """Audit stale state and return measured_pass or interrupted_retryable."""

    if row["status"] == "measured_pass":
        return "measured_pass"
    run = None if row.get("run_directory") is None else Path(row["run_directory"])
    if row["status"] in {"reserved", "running", "interrupted_retryable"}:
        if run is not None and _artifacts_pass(run):
            row["status"] = "measured_pass"
            if row["attempts"]:
                row["attempts"][-1]["status"] = "measured_pass_recovered"
            return "measured_pass"
        row["status"] = "interrupted_retryable"
        if row["attempts"] and row["attempts"][-1]["status"] in {"reserved", "running"}:
            row["attempts"][-1]["status"] = "interrupted_retryable"
        return "interrupted_retryable"
    return row["status"]


def selected_indices(design: dict[str, Any], *, role: str | None,
                     start: int | None, stop: int | None) -> list[int]:
    indices = list(range(len(design["points"])))
    if role is not None:
        indices = [i for i in indices if design["points"][i].get("role") == role]
    lower = 0 if start is None else start
    upper = len(design["points"]) if stop is None else stop
    return [i for i in indices if lower <= i < upper]


def run_design(args: argparse.Namespace) -> int:
    design = load_frozen_design(
        args.design, baseline_sha=args.baseline_sha, split=args.split,
    )
    manifest = load_manifest(args.campaign_manifest, baseline_sha=args.baseline_sha)
    register_design(manifest, design=design, design_path=args.design, split=args.split)
    _atomic_write(args.campaign_manifest, manifest)
    indices = selected_indices(
        design, role=args.role, start=args.start_index, stop=args.stop_index,
    )
    completed_this_call = 0
    completed_indices: list[int] = []
    for index in indices:
        key = _row_key(design["design_id"], index)
        row = manifest["samples"][key]
        state = recover_or_retry_row(row)
        _atomic_write(args.campaign_manifest, manifest)
        if state == "measured_pass":
            continue
        if state in {"failed_numerical_gate", "controlled_stop_resource"}:
            manifest["stop_reason"] = f"existing_failure:{key}:{state}"
            _atomic_write(args.campaign_manifest, manifest)
            return 2
        point = design["points"][index]
        parameters = parameters_from_design_point(point)
        row["attempt_number"] += 1
        attempt = row["attempt_number"]
        run_directory = (
            args.artifact_root / design["design_id"] / f"{index:04d}_"
            f"{row['point_hash'][:12]}" / f"attempt_{attempt:02d}"
        )
        row["run_directory"] = str(run_directory.resolve())
        row["status"] = "reserved"
        row["attempts"].append({
            "attempt_number": attempt, "run_directory": row["run_directory"],
            "status": "reserved",
        })
        _atomic_write(args.campaign_manifest, manifest)
        row["status"] = "running"
        row["attempts"][-1]["status"] = "running"
        _atomic_write(args.campaign_manifest, manifest)
        from .task002_full3d import formal_record_status, run_formal_task002_full3d
        try:
            result, _execution = run_formal_task002_full3d(
                parameters, root=args.root.resolve(), baseline_sha=args.baseline_sha,
                run_directory=run_directory, timeout_seconds=args.timeout_seconds,
                output_profile="compact_surrogate_record",
            )
        except (KeyboardInterrupt, SystemExit):
            row["status"] = "interrupted_retryable"
            row["attempts"][-1]["status"] = "interrupted_retryable"
            _atomic_write(args.campaign_manifest, manifest)
            raise
        except RuntimeError as exc:
            # A formal preflight refusal happens before the watchdog can return a
            # result.  Preserve it as an explained, retryable interruption rather
            # than stranding the row in ``running`` or fabricating a numerical
            # failure.  A later resume must repeat the full formal preflight.
            row["status"] = "interrupted_retryable"
            row["attempts"][-1].update({
                "status": "interrupted_retryable",
                "preflight_error": str(exc),
            })
            manifest["stop_reason"] = f"preflight_interruption:{key}"
            _atomic_write(args.campaign_manifest, manifest)
            print(json.dumps(campaign_status(manifest), indent=2))
            return 3
        status = formal_record_status(run_directory, result)
        row["status"] = status
        row["attempts"][-1].update({"status": status, "watchdog": asdict(result)})
        _atomic_write(args.campaign_manifest, manifest)
        if status != "measured_pass":
            manifest["stop_reason"] = f"first_unexplained_failure:{key}:{status}"
            _atomic_write(args.campaign_manifest, manifest)
            return 2
        completed_this_call += 1
        completed_indices.append(index)
        if len(completed_indices) % 16 == 0:
            _write_batch_summary(
                artifact_root=args.artifact_root, design_id=design["design_id"],
                indices=completed_indices[-16:], manifest=manifest,
            )
        if args.max_samples is not None and completed_this_call >= args.max_samples:
            break
    remainder = len(completed_indices) % 16
    if remainder:
        _write_batch_summary(
            artifact_root=args.artifact_root, design_id=design["design_id"],
            indices=completed_indices[-remainder:], manifest=manifest,
        )
    print(json.dumps(campaign_status(manifest), indent=2))
    return 0


def campaign_status(manifest: dict[str, Any]) -> dict[str, Any]:
    counts = {status: 0 for status in sorted(ALLOWED_STATUSES)}
    for row in manifest["samples"].values():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": manifest["schema_version"],
        "baseline_sha": manifest["baseline_sha"], "designs": manifest["designs"],
        "status_counts": counts, "stop_reason": manifest.get("stop_reason"),
    }


def _write_batch_summary(*, artifact_root: Path, design_id: str,
                         indices: list[int], manifest: dict[str, Any]) -> None:
    if not indices:
        return
    rows = [manifest["samples"][_row_key(design_id, index)] for index in indices]
    payload = {
        "schema_version": "task002.s-p5-ny4-campaign-batch-summary.v2",
        "design_id": design_id, "indices": indices,
        "status_counts": {
            status: sum(row["status"] == status for row in rows)
            for status in sorted({row["status"] for row in rows})
        },
        "peak_rss_bytes": max(
            (row["attempts"][-1].get("watchdog", {}).get("peak_rss_bytes", 0)
             for row in rows if row["attempts"]), default=0,
        ),
        "peak_swap_bytes": max(
            (row["attempts"][-1].get("watchdog", {}).get("peak_swap_bytes", 0)
             for row in rows if row["attempts"]), default=0,
        ),
        "all_measured_pass": all(row["status"] == "measured_pass" for row in rows),
    }
    path = (artifact_root / "batch_summaries" / design_id
            / f"indices_{min(indices):04d}_{max(indices):04d}.json")
    _atomic_write(path, payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run-design", "resume-design"):
        run = subparsers.add_parser(name)
        run.add_argument("--root", type=Path, required=True)
        run.add_argument("--baseline-sha", required=True)
        run.add_argument("--design", type=Path, required=True)
        run.add_argument("--split", choices=("train", "frozen_validation"), required=True)
        run.add_argument("--artifact-root", type=Path, required=True)
        run.add_argument("--campaign-manifest", type=Path, required=True)
        run.add_argument("--role")
        run.add_argument("--start-index", type=int)
        run.add_argument("--stop-index", type=int)
        run.add_argument("--max-samples", type=int)
        run.add_argument("--timeout-seconds", type=float, default=1800.0)
    status = subparsers.add_parser("status")
    status.add_argument("--baseline-sha", required=True)
    status.add_argument("--campaign-manifest", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "status":
        print(json.dumps(campaign_status(load_manifest(
            args.campaign_manifest, baseline_sha=args.baseline_sha,
        )), indent=2))
        return 0
    return run_design(args)


if __name__ == "__main__":
    raise SystemExit(main())
