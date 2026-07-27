#!/usr/bin/env python3
"""Extract the tracked compact authority needed for later h/p decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "task035d"
    / "case097"
    / "selective_face_h15_v2"
)
DWR_REPORT = (
    ARTIFACT_DIR
    / "p6_h15_pols_full-solve_mpi8_20260727T154023Z"
    / "selective_face_dwr_report.json"
)
SELECTIVE_CHECK = ARTIFACT_DIR / "selective_face_case097_requalified_full.json"
DEFAULT_OUTPUT = (
    CASE_DIR / "records" / "selective_face_selection_compact_v1.json"
)


def _strict_load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {value}")
        ),
    )
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain one JSON object")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_compact() -> dict[str, Any]:
    dwr = _strict_load(DWR_REPORT)
    selective = _strict_load(SELECTIVE_CHECK)
    raw_goals = dwr["goal_dwr"]["goals"]
    goals = {
        str(label): {
            "actual_goal_delta_a_minus_b": row[
                "actual_goal_delta_a_minus_b"
            ],
            "face_contributions": [
                {
                    "geometry_key": contribution["geometry_key"],
                    "signed_real_contribution": contribution[
                        "signed_real_contribution"
                    ],
                }
                for contribution in row["face_contributions"]
            ],
            "pass": row["pass"],
            "signed_dwr_estimate": row["signed_dwr_estimate"],
            "signed_goal_closure_error": row[
                "signed_goal_closure_error"
            ],
            "unchanged_v0_absolute_tolerance": row[
                "unchanged_v0_absolute_tolerance"
            ],
        }
        for label, row in sorted(raw_goals.items())
    }
    checks = {
        "dwr_report_pass": (
            dwr.get("pass") is True
            and dwr.get("status")
            == "selective_face_cross_trace_live_dwr_pass"
        ),
        "all_36_real_goals_pass": (
            dwr["goal_dwr"]["requested_real_goal_count"] == 36
            and dwr["goal_dwr"]["passed_real_goal_count"] == 36
            and len(goals) == 36
            and all(row["pass"] is True for row in goals.values())
        ),
        "ten_face_contributions_per_goal": all(
            len(row["face_contributions"]) == 10
            for row in goals.values()
        ),
        "selective_endpoint_is_controlled_negative": (
            selective.get("status")
            == "task035d_selective_p6_face_controlled_negative"
            and selective.get("pass") is False
            and selective["channel_comparison"][
                "significant_power_pass_count"
            ]
            == 5
            and selective["channel_comparison"][
                "significant_complex_amplitude_pass_count"
            ]
            == 6
        ),
        "source_identity": (
            dwr["enriched_candidate"]["source_sha"]
            == "0ecd914b246f433614252f6f3c0513b06b078542"
            and selective["source_sha"]
            == "0ecd914b246f433614252f6f3c0513b06b078542"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "case097.selective-face-selection-compact.v1",
        "status": (
            "selective_face_selection_compact_pass"
            if not failures
            else "selective_face_selection_compact_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "source_sha": "0ecd914b246f433614252f6f3c0513b06b078542",
        "raw_inputs": {
            str(DWR_REPORT.relative_to(ROOT)): _sha256(DWR_REPORT),
            str(SELECTIVE_CHECK.relative_to(ROOT)): _sha256(
                SELECTIVE_CHECK
            ),
        },
        "endpoint_identity_authorities": dwr[
            "endpoint_identity_authorities"
        ],
        "selected_p6_face_geometry_keys": dwr["root_transfer"][
            "selected_p6_face_geometry_keys"
        ],
        "goal_dwr": {
            "requested_real_goal_count": 36,
            "passed_real_goal_count": 36,
            "goals": goals,
        },
        "selective_channel_comparison": selective[
            "channel_comparison"
        ],
        "ordinary_default_changed": False,
        "production_qualified": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()
    if output != DEFAULT_OUTPUT.resolve():
        raise ValueError("formal compact authority output path is fixed")
    if output.exists():
        raise FileExistsError("formal compact authority is immutable")
    result = build_compact()
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": _sha256(output),
                "status": result["status"],
                "pass": result["pass"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
