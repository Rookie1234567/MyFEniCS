"""Resume-safe Task002 S-only Full3D campaign.

The historical Hybrid route is deliberately unavailable here.  Review V3
requires it to remain diagnostic evidence only, never a production fallback.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Mapping

from .forward_model import _abi_identity
from .provenance import canonical_hash, source_identity
from .resource_policy import task001_resource_limits
from .task002_schema import Task002ForwardParameters


CAMPAIGN_SCHEMA_VERSION = "task002.s-continuous-campaign.v1"


def sample_key(parameters: Task002ForwardParameters) -> str:
    return canonical_hash(parameters.as_dict())


def task002_hybrid_command(
    parameters: Task002ForwardParameters, *, root: Path, baseline_sha: str,
    output_record: Path, memory_stages: Path,
) -> list[str]:
    """Fail closed: Hybrid is hard-quarantined from Task002 production."""

    del parameters, root, baseline_sha, output_record, memory_stages
    raise RuntimeError(
        "Task002 Hybrid production route is hard quarantined by Review V3 M2C"
    )


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


def load_manifest(path: Path, *, baseline_sha: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "baseline_sha": baseline_sha, "samples": {},
        }
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise ValueError("Task002 campaign schema mismatch")
    if manifest.get("baseline_sha") != baseline_sha:
        raise ValueError("Task002 campaign baseline mismatch")
    return manifest


def update_manifest(
    path: Path, *, baseline_sha: str, parameters: Task002ForwardParameters,
    status: str, run_directory: Path | None = None,
) -> dict[str, Any]:
    allowed = {"reserved", "measured_pass", "failed_numerical_gate", "controlled_stop_resource"}
    if status not in allowed:
        raise ValueError(f"unsupported Task002 campaign status: {status}")
    manifest = load_manifest(path, baseline_sha=baseline_sha)
    key = sample_key(parameters)
    current = manifest["samples"].get(key)
    if current and current["parameters"] != parameters.as_dict():
        raise ValueError("Task002 campaign sample hash collision")
    if current and current["status"] == "measured_pass" and status != "measured_pass":
        raise ValueError("completed Task002 sample is immutable")
    manifest["samples"][key] = {
        "parameters": parameters.as_dict(), "status": status,
        "run_directory": None if run_directory is None else str(run_directory),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run-one")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--baseline-sha", required=True)
    run.add_argument("--artifact-root", type=Path, required=True)
    run.add_argument("--campaign-manifest", type=Path, required=True)
    run.add_argument("--model-id", required=True)
    run.add_argument("--height-nm", type=float, required=True)
    run.add_argument("--width-x-nm", type=float, required=True)
    run.add_argument("--grazing-deg", type=float, required=True)
    run.add_argument("--azimuth-deg", type=float, required=True)
    run.add_argument("--timeout-seconds", type=float, default=1800.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    parameters = Task002ForwardParameters(
        height_nm=args.height_nm, width_x_nm=args.width_x_nm,
        grazing_deg=args.grazing_deg, azimuth_deg=args.azimuth_deg,
        model_id=args.model_id,
    )
    parameters.validate()
    key = sample_key(parameters)
    run_directory = args.artifact_root / key[:16]
    manifest = load_manifest(args.campaign_manifest, baseline_sha=args.baseline_sha)
    existing = manifest["samples"].get(key)
    if existing is not None:
        print(json.dumps({"status": "already_recorded", "sample_key": key, **existing}, indent=2))
        return 0 if existing["status"] == "measured_pass" else 2
    update_manifest(
        args.campaign_manifest, baseline_sha=args.baseline_sha, parameters=parameters,
        status="reserved", run_directory=run_directory,
    )
    from .task002_full3d import formal_record_status, run_formal_task002_full3d

    result, execution_path = run_formal_task002_full3d(
        parameters, root=args.root.resolve(), baseline_sha=args.baseline_sha,
        run_directory=run_directory, timeout_seconds=args.timeout_seconds,
    )
    status = formal_record_status(run_directory, result)
    update_manifest(
        args.campaign_manifest, baseline_sha=args.baseline_sha, parameters=parameters,
        status=status, run_directory=run_directory,
    )
    print(json.dumps({
        "status": status, "sample_key": key, "run_directory": str(run_directory),
        "execution": str(execution_path), "watchdog": asdict(result),
    }, indent=2))
    return 0 if status == "measured_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
