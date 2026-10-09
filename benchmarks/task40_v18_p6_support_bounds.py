#!/usr/bin/env python3
"""Research-only P6 support/CSR bounds runner using the reusable src counter.

This script derives structured topology and conservative bounds from a complete
ordered mode manifest. It does not construct a target FE space, CSR matrix,
factor, or PDE. Ny4 calibration is used only when its coverage matches exactly;
Ny8 keeps the conservative 432-channel fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

from src.solvers.task40_p6_support_bounds import (
    assign_ordered_modes_to_q,
    derive_p6_q_csr_bounds,
    p6_periodic_topology_counts,
    support_bounds_from_native_calibration,
)

DEFAULT_MANIFEST = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/"
    "original_size_auto_mode_manifest.json"
)
DEFAULT_CALIBRATION = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/"
    "target_p4_topology_support_attempt02.json"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/"
    "v18_p3_full_manifest_ny4_ny8_bounds_tracked_runner_v2.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--calibration", default=str(DEFAULT_CALIBRATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    manifest_path, calibration_path, output_path = map(
        repo_path, (args.manifest, args.calibration, args.output)
    )
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite saved bounds: {output_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    calibration_receipt = json.loads(calibration_path.read_text(encoding="utf-8"))
    rows = manifest["modes"]
    modes = [
        SimpleNamespace(
            gamma=complex(row["gamma"]["real"], row["gamma"]["imag"]),
            mode_key=f'{row["side"]}:{row["m"]}:{row["n"]}:{row["polarization"]}',
            side=row["side"],
        )
        for row in rows
    ]
    native = calibration_receipt["q_support_and_index_bounds"][
        "target_support_calibration"
    ]
    calibration = {
        "native_scan": native["native_scan"],
        "calibration_permutation_code_set": native[
            "calibration_permutation_code_set"
        ],
    }
    target_codes = calibration_receipt["target_owner_classes"][
        "cell_permutation_codes"
    ]
    ny_results: dict[str, Any] = {}
    for ny in (4, 8):
        axes = {
            "x": (0.0, 50.0),
            "y": tuple(float(25.0 * index / ny) for index in range(ny + 1)),
            "z": (-10.0, 130.0),
        }
        assigned = assign_ordered_modes_to_q(
            modes, SimpleNamespace(ky=0.0, period_y=25.0), axes
        )
        topology = p6_periodic_topology_counts(272, ny, 14)
        support = support_bounds_from_native_calibration(
            (272, ny, 14), [int(code) for code in target_codes] if ny == 4 else (),
            calibration,
        )
        bounds = derive_p6_q_csr_bounds(
            topology,
            assigned["q_side_counts"],
            folded_cell_trace_support_upper=support[
                "folded_cell_trace_support_upper"
            ],
            boundary_trace_support_upper_per_face=support[
                "boundary_trace_support_upper_per_face"
            ],
            evidence_classification=(
                "derived_q_csr_structural_upper_from_complete_saved_mode_manifest"
            ),
        )
        ny_results[str(ny)] = {
            "mode_assignment": {
                key: value for key, value in assigned.items() if key != "q_for_mode"
            },
            "topology": topology,
            "support_selection": support,
            "csr_bounds": bounds,
        }
    if len(rows) != 32060:
        raise ValueError(f"saved complete manifest mode count changed: {len(rows)}")
    runner_path = Path(__file__).resolve()
    module_path = ROOT / "src/solvers/task40_p6_support_bounds.py"
    result = {
        "schema": "task40extra.review_v18_p3_complete_manifest_bounds.v1",
        "status": "DERIVED_BOUNDS_COMPLETE",
        "classification": (
            "complete ordered mode manifest mapped by tracked src counter; "
            "topology-derived, no target FE/CSR/factor/PDE"
        ),
        "manifest": {
            "path": str(manifest_path.relative_to(ROOT)),
            "sha256": sha256(manifest_path),
            "ordered_mode_count": len(rows),
        },
        "native_calibration_receipt": {
            "path": str(calibration_path.relative_to(ROOT)),
            "sha256": sha256(calibration_path),
            "classification": calibration["native_scan"]["classification"],
        },
        "counter": {
            "path": str(module_path.relative_to(ROOT)),
            "sha256": sha256(module_path),
        },
        "runner": {
            "path": str(runner_path.relative_to(ROOT)),
            "sha256": sha256(runner_path),
            "arguments": {
                "manifest": str(manifest_path.relative_to(ROOT)),
                "calibration": str(calibration_path.relative_to(ROOT)),
                "output": str(output_path.relative_to(ROOT)),
            },
        },
        "Ny4_and_Ny8": ny_results,
        "limitations": [
            "Ny8 uses the conservative 432 local trace and 432*Nx boundary fallback; Ny4 calibration is not transferred.",
            "structural NNZ bounds are not measured stored numerical NNZ or memory residency.",
            "distinct-q CSR payload sum is not a simultaneous-memory claim.",
            "mode cutoff qualification is not established by this propagating-mode manifest.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(output_path),
                "manifest_sha256": result["manifest"]["sha256"],
                "ordered_mode_count": len(rows),
                "ny4_q_counts": ny_results["4"]["mode_assignment"]["q_counts"],
                "ny4_q_digest": ny_results["4"]["mode_assignment"][
                    "ordered_q_assignment_sha256"
                ],
                "ny8_q_counts": ny_results["8"]["mode_assignment"]["q_counts"],
                "ny8_q_digest": ny_results["8"]["mode_assignment"][
                    "ordered_q_assignment_sha256"
                ],
                "ny8_total_int32_csr_upper_bytes": ny_results["8"][
                    "csr_bounds"
                ]["q_count_distinct_payload_upper_bytes"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
