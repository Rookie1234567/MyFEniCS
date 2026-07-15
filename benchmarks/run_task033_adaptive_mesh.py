from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.geometry.task033_periodic_graded_mesh import (
    build_adaptive_planning_record,
    build_physics_informed_graded_plan,
    combined_indicator,
    rebuild_from_cell_indicators,
)


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object.")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan the explicit-opt-in Task033 fixed-p2 periodic graded mesh. "
            "The command does not run a PDE and defaults to fail-closed accuracy status."
        )
    )
    parser.add_argument("--reference-h", type=float, choices=(5.0, 3.0), required=True)
    parser.add_argument("--coarse-factor", type=float, default=2.0)
    parser.add_argument("--feature-plane-y", type=float, action="append", default=[])
    parser.add_argument(
        "--indicator-npz",
        type=Path,
        help=(
            "Optional one-cycle indicator archive with bottom_residual, bottom_jump, "
            "top_residual, and top_jump arrays."
        ),
    )
    parser.add_argument("--dorfler-theta", type=float, default=0.5)
    parser.add_argument("--jump-weight", type=float, default=1.0)
    parser.add_argument("--max-total-cells", type=int, default=2_000_000)
    parser.add_argument("--reference-evidence", type=Path)
    parser.add_argument("--candidate-evidence", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    plan = build_physics_informed_graded_plan(
        reference_h_nm=args.reference_h,
        coarse_factor=args.coarse_factor,
        feature_planes_y_nm=args.feature_plane_y,
    )
    if args.indicator_npz is not None:
        with np.load(args.indicator_npz, allow_pickle=False) as archive:
            required = (
                "bottom_residual",
                "bottom_jump",
                "top_residual",
                "top_jump",
            )
            missing = [name for name in required if name not in archive]
            if missing:
                raise ValueError(f"Indicator archive is missing: {', '.join(missing)}")
            bottom = combined_indicator(
                archive["bottom_residual"],
                archive["bottom_jump"],
                jump_weight=args.jump_weight,
            )
            top = combined_indicator(
                archive["top_residual"],
                archive["top_jump"],
                jump_weight=args.jump_weight,
            )
        plan = rebuild_from_cell_indicators(
            plan,
            bottom_indicator=bottom,
            top_indicator=top,
            theta=args.dorfler_theta,
            max_total_cells=args.max_total_cells,
        )
    record = build_adaptive_planning_record(
        plan,
        reference_evidence=_load_json(args.reference_evidence),
        candidate_evidence=_load_json(args.candidate_evidence),
    )
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output_json is None:
        print(payload, end="")
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
