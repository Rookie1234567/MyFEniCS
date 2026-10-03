#!/usr/bin/env python3
"""One-off offline four-corner saved-field volume comparison for Task40 Review V4."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "G00": ROOT
    / "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_manual_m2_f3_v1__full3d_iterative__mpi1__Mna/"
    "20261001T154625.204407Z",
    "G10": ROOT
    / "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_gx560_manual_m2_v3_v1__full3d_iterative__mpi1__Mna/"
    "20261003T002312.848713Z",
    "G01": ROOT
    / "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_gz528_manual_m2_v3_v1__full3d_iterative__mpi1__Mna/"
    "20261003T010317.735278Z",
    "G11": ROOT
    / "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1__full3d_iterative__mpi1__Mna/"
    "20261002T000242.608221Z",
}
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/"
    "four_corner_volume_v1.json"
)


def _json_default(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(
                value, stream, indent=2, sort_keys=True, allow_nan=False,
                default=_json_default
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def _worker(run_roots: dict[str, Path], output: Path) -> None:
    from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
        _load_run,
        _qualified_environment,
        _sha256,
    )
    from src.postprocessing.task40_saved_field_h_comparison import (
        compare_four_corner_directional,
        restore_p6_total_field,
    )

    environment = _qualified_environment()
    environment["thread_environment"] = {
        key: os.environ.get(key)
        for key in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"
        )
    }
    started = datetime.now(timezone.utc).isoformat()
    started_monotonic = __import__("time").monotonic()
    runs = {label: _load_run(label, root) for label, root in run_roots.items()}
    signatures = {
        label: _canonical_json(run.input_signature) for label, run in runs.items()
    }
    if len(set(signatures.values())) != 1:
        raise ValueError("the four saved runs have different physical input signatures")

    fields = {
        label: restore_p6_total_field(label, run.cfg, run.vector)
        for label, run in runs.items()
    }
    comparison = compare_four_corner_directional(fields)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    identities = {}
    for label, run in runs.items():
        identities[label] = {
            "run_root": str(run.root),
            "run_id": run.manifest.get("run_id", run.packet.get("run_id")),
            "solver_source_sha": run.manifest["source_sha"],
            "run_manifest_sha256": _sha256(run.root / "run_manifest.json"),
            "input_sha256": run.manifest["input_sha256"],
            "physical_model_sha256": run.manifest["physical_model_sha256"],
            "packet_sha256": run.packet_sha256,
            "vector_sha256": run.vector_sha256,
            "vector_archive_sha256": run.vector_archive_sha256,
            "input_signature_sha256": hashlib.sha256(
                signatures[label].encode("utf-8")
            ).hexdigest(),
        }
    result = {
        "schema": "task40.review-v4.directional-cross-volume.v1",
        "status": "completed",
        "analysis_source_sha": head,
        "qualified_environment": environment,
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": __import__("time").monotonic() - started_monotonic,
        "run_identities": identities,
        "comparison": comparison,
    }
    _atomic_json(output, result)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in RUNS:
        parser.add_argument(
            f"--{label.lower()}-root",
            type=Path,
            default=RUNS[label],
        )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--worker", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    roots = {
        label: getattr(args, f"{label.lower()}_root").resolve() for label in RUNS
    }
    output = args.output.resolve()
    if args.worker:
        _worker(roots, output)
        return 0
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis result: {output}")

    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        supervise,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    watchdog_dir = output.parent / "four_corner_volume_v1_watchdog"
    worker_environment = os.environ.copy()
    worker_environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    command = [
        sys.executable,
        "-m",
        "benchmarks.postprocess_task40_review_v4_directional_cross",
        "--worker",
        "--output",
        str(output),
    ]
    for label, root in roots.items():
        command.extend([f"--{label.lower()}-root", str(root)])
    supervision = supervise(
        command,
        watchdog_dir,
        wall_seconds=43_200,
        interval=0.25,
        grace_seconds=30,
        source_state={"analysis_source_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()},
        worker_environment=worker_environment,
        hard_stop_immediate=True,
        stop_on_global_swap=False,
        allow_swap_observation=False,
        time_policy="observe_only",
        memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        pss_sampling_policy="disabled_by_profile",
    )
    exit_code = supervision.get("leader_exit_code")
    if exit_code != 0 or not output.is_file():
        raise RuntimeError(
            f"four-corner worker did not complete: exit={exit_code}, "
            f"watchdog={watchdog_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
