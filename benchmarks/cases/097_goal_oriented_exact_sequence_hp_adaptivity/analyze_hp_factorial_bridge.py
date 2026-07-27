#!/usr/bin/env python3
"""Independently attribute the Task035d A/B/D h/p factorial signals."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
RECORDS = CASE_DIR / "records"
SCRIPT_RELATIVE = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/"
    "analyze_hp_factorial_bridge.py"
)
OUTPUT = RECORDS / "hp_factorial_bridge_attribution_v1.json"
INPUTS = {
    "A_one_sided_h": {
        "path": RECORDS / "h15_top_air_local_h_mpi8_controlled_negative_v1.json",
        "sha256": (
            "995026ed9d2e6e70c8f681d8dfc7a7d1c49ff2bb2574d49733e9ce90c661fe23"
        ),
        "candidate_id": "h15_top_air_local_h_v1",
        "power_passes": 6,
        "amplitude_passes": 6,
    },
    "B_one_sided_h_remote_p5": {
        "path": (
            RECORDS
            / "h15_top_air_remote_p5_interior_bridge_mpi8_candidate_check_v1.json"
        ),
        "sha256": (
            "8ab6ecf79b3c8750be9338e842668da51724a3e96d75d41055e340d3de01f799"
        ),
        "candidate_id": "h15_top_air_remote_p5_interior_bridge_v1",
        "power_passes": 4,
        "amplitude_passes": 4,
    },
    "D_symmetric_h_remote_p5": {
        "path": (
            RECORDS
            / "h15_symmetric_top_air_remote_p5_interior_mpi8_candidate_check_v2.json"
        ),
        "sha256": (
            "3eaa00584387f60db3d5e570774537dd0ec60848235ad8db0d39651436730870"
        ),
        "candidate_id": "h15_symmetric_top_air_remote_p5_interior_v1",
        "power_passes": 4,
        "amplitude_passes": 4,
    },
}
PLANS = {
    "A_one_sided_h": (
        RECORDS / "h15_top_air_local_h_plan_v1.json"
    ),
    "B_one_sided_h_remote_p5": (
        RECORDS / "h15_top_air_remote_p5_interior_bridge_plan_v1.json"
    ),
    "D_symmetric_h_remote_p5": (
        RECORDS / "h15_symmetric_top_air_remote_p5_interior_plan_v1.json"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_load(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda raw: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {raw}")
        ),
    )
    if not isinstance(value, dict):
        raise TypeError(f"{path} does not contain a JSON object")
    return value


def _channel_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(row["side"]),
        int(row["m"]),
        int(row["n"]),
        str(row["polarization"]),
    )


def _complex(row: Mapping[str, Any], name: str) -> complex:
    value = row[name]
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, (int, float)) for item in value)
    ):
        raise TypeError(f"{name} is not a complex pair")
    return complex(float(value[0]), float(value[1]))


def _channels(record: Mapping[str, Any]) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    comparison = record["channel_comparison"]
    rows = comparison["channels"]
    result = {
        _channel_key(row): dict(row)
        for row in rows
        if isinstance(row, Mapping)
    }
    if len(rows) != 12 or len(result) != 12:
        raise ValueError("factorial evidence must contain 12 unique channels")
    return result


def _p5_boxes(plan: Mapping[str, Any]) -> set[tuple[float, ...]]:
    return {
        (
            *map(float, row["lower"]),
            *map(float, row["upper"]),
        )
        for row in plan.get("cell_interior_degrees", ())
        if isinstance(row, Mapping) and int(row.get("degree", -1)) == 5
    }


def _nonchannel_gates_pass(record: Mapping[str, Any]) -> bool:
    return all(
        isinstance(record.get(name), Mapping)
        and record[name].get("pass") is True
        for name in (
            "observable_comparison",
            "energy_comparison",
            "field_comparison",
            "resource_comparison",
            "solver_gate",
        )
    )


def analyze_factorial_bridge(
    *,
    source_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    input_identity: dict[str, dict[str, Any]] = {}
    for name, spec in INPUTS.items():
        path = Path(spec["path"])
        observed = _sha256(path)
        if observed != spec["sha256"]:
            raise ValueError(f"frozen factorial input drifted: {name}")
        record = _strict_load(path)
        comparison = record.get("channel_comparison")
        if not isinstance(comparison, Mapping):
            raise TypeError(f"{name} has no channel comparison")
        if (
            record.get("candidate_id") != spec["candidate_id"]
            or int(comparison.get("significant_power_pass_count", -1))
            != spec["power_passes"]
            or int(
                comparison.get(
                    "significant_complex_amplitude_pass_count",
                    -1,
                )
            )
            != spec["amplitude_passes"]
        ):
            raise ValueError(f"frozen factorial result identity failed: {name}")
        records[name] = record
        input_identity[name] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": observed,
            "candidate_id": spec["candidate_id"],
            "status": record.get("status"),
        }

    plans = {name: _strict_load(path) for name, path in PLANS.items()}
    plan_identity = {
        name: {
            "path": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
            "marked_root_boxes": plans[name].get("marked_root_boxes"),
            "p5_interior_box_count": len(_p5_boxes(plans[name])),
        }
        for name, path in PLANS.items()
    }
    channels = {name: _channels(record) for name, record in records.items()}
    keys = sorted(channels["A_one_sided_h"])
    if any(set(table) != set(keys) for table in channels.values()):
        raise ValueError("factorial channel identities do not match")

    rows: list[dict[str, Any]] = []
    lost_power = 0
    gained_power = 0
    lost_amplitude = 0
    gained_amplitude = 0
    bridge_symmetric_power_delta: list[float] = []
    bridge_symmetric_amplitude_delta: list[float] = []
    for key in keys:
        a = channels["A_one_sided_h"][key]
        b = channels["B_one_sided_h_remote_p5"][key]
        d = channels["D_symmetric_h_remote_p5"][key]
        power_tolerance = float(a["unchanged_v0_power_tolerance"])
        amplitude_tolerance = float(
            a["unchanged_v0_complex_amplitude_tolerance"]
        )
        if not (
            math.isclose(
                power_tolerance,
                float(b["unchanged_v0_power_tolerance"]),
                rel_tol=0.0,
                abs_tol=0.0,
            )
            and math.isclose(
                power_tolerance,
                float(d["unchanged_v0_power_tolerance"]),
                rel_tol=0.0,
                abs_tol=0.0,
            )
            and math.isclose(
                amplitude_tolerance,
                float(b["unchanged_v0_complex_amplitude_tolerance"]),
                rel_tol=0.0,
                abs_tol=0.0,
            )
            and math.isclose(
                amplitude_tolerance,
                float(d["unchanged_v0_complex_amplitude_tolerance"]),
                rel_tol=0.0,
                abs_tol=0.0,
            )
        ):
            raise ValueError("unchanged v0 channel tolerance drifted")
        a_power = bool(a["power_pass"])
        b_power = bool(b["power_pass"])
        a_amplitude = bool(a["complex_amplitude_pass"])
        b_amplitude = bool(b["complex_amplitude_pass"])
        lost_power += int(a_power and not b_power)
        gained_power += int(not a_power and b_power)
        lost_amplitude += int(a_amplitude and not b_amplitude)
        gained_amplitude += int(not a_amplitude and b_amplitude)
        b_d_power = abs(
            float(b["candidate_power_ratio"])
            - float(d["candidate_power_ratio"])
        ) / power_tolerance
        b_d_amplitude = abs(
            _complex(b, "candidate_outgoing_amplitude_at_boundary")
            - _complex(d, "candidate_outgoing_amplitude_at_boundary")
        ) / amplitude_tolerance
        bridge_symmetric_power_delta.append(b_d_power)
        bridge_symmetric_amplitude_delta.append(b_d_amplitude)
        rows.append(
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "A_normalized_power_error": (
                    float(a["candidate_vs_reference_power_absolute_error"])
                    / power_tolerance
                ),
                "A_normalized_amplitude_error": (
                    float(
                        a[
                            "candidate_vs_reference_amplitude_absolute_error"
                        ]
                    )
                    / amplitude_tolerance
                ),
                "B_normalized_power_error": (
                    float(b["candidate_vs_reference_power_absolute_error"])
                    / power_tolerance
                ),
                "B_normalized_amplitude_error": (
                    float(
                        b[
                            "candidate_vs_reference_amplitude_absolute_error"
                        ]
                    )
                    / amplitude_tolerance
                ),
                "D_normalized_power_error": (
                    float(d["candidate_vs_reference_power_absolute_error"])
                    / power_tolerance
                ),
                "D_normalized_amplitude_error": (
                    float(
                        d[
                            "candidate_vs_reference_amplitude_absolute_error"
                        ]
                    )
                    / amplitude_tolerance
                ),
                "A_pass_mask": [a_power, a_amplitude],
                "B_pass_mask": [b_power, b_amplitude],
                "D_pass_mask": [
                    bool(d["power_pass"]),
                    bool(d["complex_amplitude_pass"]),
                ],
                "B_vs_D_normalized_power_delta": b_d_power,
                "B_vs_D_normalized_amplitude_delta": b_d_amplitude,
            }
        )

    a_plan = plans["A_one_sided_h"]
    b_plan = plans["B_one_sided_h_remote_p5"]
    d_plan = plans["D_symmetric_h_remote_p5"]
    b_d_same_pass_mask = all(
        row["B_pass_mask"] == row["D_pass_mask"] for row in rows
    )
    checks = {
        "A_and_B_have_identical_local_h_action": (
            a_plan["marked_root_boxes"] == b_plan["marked_root_boxes"]
            and a_plan["expected_forest"] == b_plan["expected_forest"]
        ),
        "B_and_D_have_identical_remote_p5_boxes": (
            len(_p5_boxes(b_plan)) == 32
            and _p5_boxes(b_plan) == _p5_boxes(d_plan)
        ),
        "D_adds_exactly_one_symmetric_h_root": (
            len(d_plan["marked_root_boxes"]) == 2
            and len(b_plan["marked_root_boxes"]) == 1
            and b_plan["marked_root_boxes"][0]
            in d_plan["marked_root_boxes"]
        ),
        "B_and_D_all_nonchannel_gates_pass": all(
            _nonchannel_gates_pass(records[name])
            for name in (
                "B_one_sided_h_remote_p5",
                "D_symmetric_h_remote_p5",
            )
        ),
        "A_broad_physics_and_resource_gates_pass_with_known_residual_negative": (
            all(
                records["A_one_sided_h"][name].get("pass") is True
                for name in (
                    "observable_comparison",
                    "energy_comparison",
                    "field_comparison",
                    "resource_comparison",
                )
            )
            and records["A_one_sided_h"]["solver_gate"].get("pass") is False
            and records["A_one_sided_h"]["solver_gate"].get("failures")
            == ["full_explicit_true_residual"]
        ),
        "A_is_6_plus_6_positive_anchor": (
            INPUTS["A_one_sided_h"]["power_passes"] == 6
            and INPUTS["A_one_sided_h"]["amplitude_passes"] == 6
        ),
        "B_and_D_are_independent_4_plus_4_negatives": (
            records["B_one_sided_h_remote_p5"]["status"]
            == "task035d_hp_factorial_bridge_controlled_negative"
            and records["D_symmetric_h_remote_p5"]["status"]
            == "task035d_combined_hp_interior_controlled_negative"
            and b_d_same_pass_mask
        ),
        "remote_pdown_loses_passing_channels_without_any_new_pass": (
            lost_power == 2
            and gained_power == 0
            and lost_amplitude == 2
            and gained_amplitude == 0
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    lane_closed = not failures
    return {
        "schema_version": "case097.hp-factorial-bridge-attribution.v1",
        "status": (
            "remote_p5_interior_lane_closed_controlled_negative"
            if lane_closed
            else "hp_factorial_bridge_attribution_fail_closed"
        ),
        "pass": lane_closed,
        "classification": "controlled_negative",
        "source_identity": (
            None if source_identity is None else dict(source_identity)
        ),
        "inputs": input_identity,
        "plans": plan_identity,
        "factorial_design": {
            "A": "one-sided local-h, all p6 cell interiors",
            "B": "same one-sided local-h plus 32 remote p5 interiors",
            "D": "symmetric local-h plus the same 32 remote p5 interiors",
            "isolated_contrasts": {
                "B_minus_A": "remote p6-to-p5 cell-interior action",
                "D_minus_B": "second symmetric top-air h split",
            },
        },
        "channel_rows": rows,
        "attribution": {
            "A_pass_counts": {"power": 6, "amplitude": 6},
            "B_pass_counts": {"power": 4, "amplitude": 4},
            "D_pass_counts": {"power": 4, "amplitude": 4},
            "A_to_B_lost_power_passes": lost_power,
            "A_to_B_gained_power_passes": gained_power,
            "A_to_B_lost_amplitude_passes": lost_amplitude,
            "A_to_B_gained_amplitude_passes": gained_amplitude,
            "B_and_D_same_pass_mask": b_d_same_pass_mask,
            "B_vs_D_max_normalized_power_delta": max(
                bridge_symmetric_power_delta
            ),
            "B_vs_D_max_normalized_amplitude_delta": max(
                bridge_symmetric_amplitude_delta
            ),
            "conclusion": (
                "The 32-cell remote p6-to-p5 interior action is the "
                "identified cause of the 6/12+6/12 to 4/12+4/12 loss. "
                "The second symmetric h split does not restore a channel "
                "and is not the primary cause of the degradation."
            ),
        },
        "lane_decision": {
            "lane": "remote_homogeneous_air_p6_to_p5_cell_interior",
            "formal_negative_signal_count": 2,
            "closed": lane_closed,
            "eight_cell_C_discriminator": "not_run",
            "eight_cell_C_reason": (
                "two independent formal negatives close this heuristic "
                "p-down lane; additional subset scanning would be blind"
            ),
            "next_route": (
                "actual 12-channel nested-p complement DWR with signed "
                "cell and port/aux closure"
            ),
        },
        "selection_credit": {
            "factorial_attribution_credit": lane_closed,
            "actual_channel_dwr": False,
            "goal_oriented_selection_credit": False,
            "complete_combined_hp_credit": False,
        },
        "checks": checks,
        "failures": failures,
        "ordinary_default_changed": False,
    }


def _source_identity(source_sha: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.check_output(
        (
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            SCRIPT_RELATIVE,
        ),
        cwd=ROOT,
        text=True,
    ).strip()
    live = _sha256(ROOT / SCRIPT_RELATIVE)
    committed = hashlib.sha256(
        subprocess.check_output(
            ("git", "show", f"{source_sha}:{SCRIPT_RELATIVE}"),
            cwd=ROOT,
        )
    ).hexdigest()
    identity = {
        "source_sha": source_sha,
        "live_head": head,
        "script_path": SCRIPT_RELATIVE,
        "live_script_sha256": live,
        "committed_script_sha256": committed,
        "status_lines": status.splitlines(),
        "verified_clean_source": (
            head == source_sha and live == committed and not status
        ),
    }
    if identity["verified_clean_source"] is not True:
        raise RuntimeError("factorial analyzer source identity is not clean")
    return identity


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.resolve() != OUTPUT.resolve():
        raise ValueError("formal factorial attribution output path is fixed")
    if output.exists():
        raise FileExistsError("formal factorial attribution is immutable")
    result = analyze_factorial_bridge(
        source_identity=_source_identity(str(args.source_sha))
    )
    output.write_text(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
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
