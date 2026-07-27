#!/usr/bin/env python3
"""Freeze the bounded Task035d cycle-2 h/p action decision.

This is a selection/evidence tool, not a solver.  It combines the already-run
36-goal selective-face DWR, the independently checked channel endpoints, and
the exact periodic/material closure of candidate root marks.  Face DWR is used
only as a location oracle; it is never relabelled as an unrun local-h surplus.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adaptivity.stage4_local_h import _build_forest  # noqa: E402
from src.common.config_3d import target_stage4_config  # noqa: E402


CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
CASE095_RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
)
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
COARSE_CHECK = RECORD_DIR / (
    "h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json"
)
H13_RECORD = CASE095_RECORDS / (
    "fixed_p5trace_p6interior_h13_directional_z_mpi8.json"
)
H15_RECORD = CASE095_RECORDS / (
    "fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json"
)
PLAN = RECORD_DIR / "h15_outer_top_periodic_p5fine_plan_v1.json"
DEFAULT_OUTPUT = RECORD_DIR / "outer_top_periodic_p5fine_selection_v1.json"

OUTER_RIGHT_MARK = (41.75, 0.0, 120.0, 50.0, 12.5, 130.0)
RIGHT_INNER_MARK = (33.5, 0.0, 120.0, 41.75, 12.5, 130.0)
PHYSICAL_X_BANDS = (
    (0.0, 8.25),
    (16.5, 25.0),
    (25.0, 33.5),
    (33.5, 41.75),
    (41.75, 50.0),
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


def _channel_prefix(channel: Mapping[str, Any]) -> str:
    side = "R" if channel["side"] == "top" else "T"
    return (
        f"{side}_m{int(channel['m'])}_n{int(channel['n'])}_"
        f"{channel['polarization']}"
    )


def _face_band(
    face_contribution: Mapping[str, Any],
) -> tuple[int, int]:
    key = tuple(map(int, face_contribution["geometry_key"]))
    if len(key) != 6 or key[0] != 2:
        raise ValueError("Task035d selection expects horizontal face keys")
    return key[2], key[3]


def _paired_contributions(
    goals: Mapping[str, Any],
) -> tuple[tuple[tuple[int, int], ...], dict[str, dict[tuple[int, int], float]]]:
    bands = sorted(
        {
            _face_band(row)
            for goal in goals.values()
            for row in goal["face_contributions"]
        }
    )
    if len(bands) != 5:
        raise ValueError("the frozen selective-face report must contain five x bands")
    result: dict[str, dict[tuple[int, int], float]] = {}
    for label, goal in goals.items():
        by_band = {band: 0.0 for band in bands}
        counts = Counter()
        for row in goal["face_contributions"]:
            band = _face_band(row)
            by_band[band] += float(row["signed_real_contribution"])
            counts[band] += 1
        if set(counts.values()) != {2}:
            raise ValueError(f"{label} does not have two y faces per x band")
        result[str(label)] = by_band
    return tuple(bands), result


def _component_errors(
    selective: Mapping[str, Any],
) -> tuple[dict[str, float], tuple[str, ...]]:
    errors: dict[str, float] = {}
    failed: list[str] = []
    for channel in selective["channel_comparison"]["channels"]:
        prefix = _channel_prefix(channel)
        power_label = f"{prefix}_power"
        power_error = (
            float(channel["candidate_power_ratio"])
            - float(channel["reference_power_ratio"])
        ) / float(channel["unchanged_v0_power_tolerance"])
        errors[power_label] = power_error
        if channel["power_pass"] is not True:
            failed.append(power_label)

        amplitude = channel["candidate_outgoing_amplitude_at_boundary"]
        reference = channel["reference_outgoing_amplitude_at_boundary"]
        tolerance = float(
            channel["unchanged_v0_complex_amplitude_tolerance"]
        )
        for index, suffix in enumerate(("real", "imag")):
            label = f"{prefix}_amplitude_{suffix}"
            errors[label] = (
                float(amplitude[index]) - float(reference[index])
            ) / tolerance
            if channel["complex_amplitude_pass"] is not True:
                failed.append(label)
    if len(errors) != 36 or len(failed) != 19:
        raise ValueError("the frozen selective endpoint must expose 36/19 goals")
    return errors, tuple(sorted(failed))


def _band_metrics(
    *,
    bands: tuple[tuple[int, int], ...],
    contributions: Mapping[str, Mapping[tuple[int, int], float]],
    goals: Mapping[str, Any],
    normalized_errors: Mapping[str, float],
    failed_labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = []
    failed_set = set(failed_labels)
    for physical, band in zip(PHYSICAL_X_BANDS, bands, strict=True):
        normalized = {
            label: float(by_band[band])
            / float(goals[label]["unchanged_v0_absolute_tolerance"])
            for label, by_band in contributions.items()
        }
        rows.append(
            {
                "physical_x_nm": list(physical),
                "quantized_x_band": list(band),
                "all_36_absolute_normalized_support": sum(
                    abs(value) for value in normalized.values()
                ),
                "failed_19_absolute_normalized_support": sum(
                    abs(normalized[label]) for label in failed_set
                ),
                "failed_19_negative_error_dot_action": -sum(
                    normalized_errors[label] * normalized[label]
                    for label in failed_set
                ),
                "failed_goal_normalized_signed_contributions": {
                    label: normalized[label] for label in failed_labels
                },
            }
        )
    return rows


def _subset_screen(
    *,
    coarse: Mapping[str, Any],
    bands: tuple[tuple[int, int], ...],
    contributions: Mapping[str, Mapping[tuple[int, int], float]],
) -> dict[str, Any]:
    rows = []
    channels = coarse["channel_comparison"]["channels"]
    for bits in itertools.product((0, 1), repeat=len(bands)):
        selected = {
            band for band, enabled in zip(bands, bits, strict=True) if enabled
        }
        power_passes = 0
        amplitude_passes = 0
        regressed_passed_channels = set()
        for channel in channels:
            prefix = _channel_prefix(channel)
            amplitude = [
                float(value)
                for value in channel["candidate_outgoing_amplitude_at_boundary"]
            ]
            for index, suffix in enumerate(("real", "imag")):
                label = f"{prefix}_amplitude_{suffix}"
                amplitude[index] += sum(
                    contributions[label][band] for band in selected
                )
            reference = complex(
                *map(
                    float,
                    channel["reference_outgoing_amplitude_at_boundary"],
                )
            )
            predicted = complex(*amplitude)
            amplitude_pass = (
                abs(predicted - reference)
                <= float(
                    channel["unchanged_v0_complex_amplitude_tolerance"]
                )
            )
            coarse_amplitude = complex(
                *map(
                    float,
                    channel["candidate_outgoing_amplitude_at_boundary"],
                )
            )
            power_weight = float(channel["candidate_power_ratio"]) / (
                abs(coarse_amplitude) ** 2
            )
            predicted_power = power_weight * abs(predicted) ** 2
            power_pass = (
                abs(
                    predicted_power
                    - float(channel["reference_power_ratio"])
                )
                <= float(channel["unchanged_v0_power_tolerance"])
            )
            power_passes += int(power_pass)
            amplitude_passes += int(amplitude_pass)
            if (
                channel["power_pass"] is True
                and not power_pass
                or channel["complex_amplitude_pass"] is True
                and not amplitude_pass
            ):
                regressed_passed_channels.add(
                    (
                        str(channel["side"]),
                        int(channel["m"]),
                        int(channel["n"]),
                        str(channel["polarization"]),
                    )
                )
        rows.append(
            {
                "mask": list(bits),
                "selected_band_count": sum(bits),
                "predicted_power_pass_count": power_passes,
                "predicted_complex_amplitude_pass_count": amplitude_passes,
                "regressed_previously_passing_channel_count": len(
                    regressed_passed_channels
                ),
            }
        )
    best = max(
        rows,
        key=lambda row: (
            min(
                row["predicted_power_pass_count"],
                row["predicted_complex_amplitude_pass_count"],
            ),
            row["predicted_power_pass_count"]
            + row["predicted_complex_amplitude_pass_count"],
            -row["regressed_previously_passing_channel_count"],
            -row["selected_band_count"],
        ),
    )
    return {
        "subset_count": len(rows),
        "maximum_predicted_power_pass_count": max(
            row["predicted_power_pass_count"] for row in rows
        ),
        "maximum_predicted_complex_amplitude_pass_count": max(
            row["predicted_complex_amplitude_pass_count"] for row in rows
        ),
        "best_fail_closed_subset": best,
        "no_subset_predicts_12_plus_12": all(
            row["predicted_power_pass_count"] < 12
            or row["predicted_complex_amplitude_pass_count"] < 12
            for row in rows
        ),
        "no_subset_improves_both_coarse_pass_counts": all(
            row["predicted_power_pass_count"] <= 6
            or row["predicted_complex_amplitude_pass_count"] <= 6
            for row in rows
        ),
    }


def _forest_row(mark: tuple[float, ...]) -> dict[str, Any]:
    cfg = target_stage4_config(degree=6, h_nm=15.0)
    forest = _build_forest(
        cfg,
        comm_size=8,
        marked_root_boxes=(mark,),
        maximum_level=1,
    )
    closure = dict(forest.audit["closure_split_counts"])
    return {
        "requested_mark_nm": list(mark),
        "split_root_count": sum(map(int, closure.values())),
        "leaf_cell_count": len(forest.leaves),
        "hanging_patch_count": len(forest.hanging_faces),
        "closure_counts": closure,
    }


def analyze() -> dict[str, Any]:
    dwr = _strict_load(DWR_REPORT)
    selective = _strict_load(SELECTIVE_CHECK)
    coarse = _strict_load(COARSE_CHECK)
    h13 = _strict_load(H13_RECORD)
    h15 = _strict_load(H15_RECORD)
    plan = _strict_load(PLAN)
    goals = dwr["goal_dwr"]["goals"]
    bands, contributions = _paired_contributions(goals)
    normalized_errors, failed_labels = _component_errors(selective)
    band_rows = _band_metrics(
        bands=bands,
        contributions=contributions,
        goals=goals,
        normalized_errors=normalized_errors,
        failed_labels=failed_labels,
    )
    by_physical = {
        tuple(row["physical_x_nm"]): row for row in band_rows
    }
    outer_rows = (
        by_physical[(0.0, 8.25)],
        by_physical[(41.75, 50.0)],
    )
    right_inner = by_physical[(33.5, 41.75)]
    outer_failed_support = sum(
        row["failed_19_absolute_normalized_support"] for row in outer_rows
    )
    outer_alignment = sum(
        row["failed_19_negative_error_dot_action"] for row in outer_rows
    )
    plan_degree_counts = Counter(
        int(row["degree"]) for row in plan["cell_interior_degrees"]
    )
    checks = {
        "dwr_36_goal_closure_pass": (
            dwr.get("pass") is True
            and dwr["goal_dwr"]["passed_real_goal_count"] == 36
        ),
        "selective_face_endpoint_is_controlled_negative": (
            selective.get("status")
            == "task035d_selective_p6_face_controlled_negative"
            and selective["channel_comparison"][
                "significant_power_pass_count"
            ]
            == 5
            and selective["channel_comparison"][
                "significant_complex_amplitude_pass_count"
            ]
            == 6
        ),
        "face_subset_lane_has_no_complete_signal": (
            _subset_screen(
                coarse=coarse,
                bands=bands,
                contributions=contributions,
            )["no_subset_predicts_12_plus_12"]
        ),
        "directional_z_h13_is_positive_h_oracle": (
            h15["diffraction_channel_comparison"][
                "significant_power_pass_count"
            ]
            == 6
            and h15["diffraction_channel_comparison"][
                "significant_complex_amplitude_pass_count"
            ]
            == 7
            and h13["diffraction_channel_comparison"][
                "significant_power_pass_count"
            ]
            == 10
            and h13["diffraction_channel_comparison"][
                "significant_complex_amplitude_pass_count"
            ]
            == 10
        ),
        "outer_periodic_support_exceeds_right_inner": (
            outer_failed_support
            > right_inner["failed_19_absolute_normalized_support"]
            and outer_alignment > 0.0
            and right_inner["failed_19_negative_error_dot_action"] < 0.0
        ),
        "selected_plan_is_true_bounded_hp": (
            plan["marked_root_boxes"]
            == [
                {
                    "lower": [41.75, 0.0, 120.0],
                    "upper": [50.0, 12.5, 130.0],
                }
            ]
            and plan["expected_forest"]["closure_counts"]
            == {"balance": 0, "material": 0, "periodic": 3, "user": 1}
            and plan_degree_counts == Counter({5: 32, 6: 116})
            and "selected_p6_face_geometry_keys" not in plan
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    subset = _subset_screen(
        coarse=coarse,
        bands=bands,
        contributions=contributions,
    )
    return {
        "schema_version": "case097.outer-top-periodic-p5fine-selection.v1",
        "status": (
            "outer_top_periodic_p5fine_selection_pass"
            if not failures
            else "outer_top_periodic_p5fine_selection_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "inputs": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in (
                DWR_REPORT,
                SELECTIVE_CHECK,
                COARSE_CHECK,
                H13_RECORD,
                H15_RECORD,
                PLAN,
            )
        },
        "selective_face_lane": {
            "measured_endpoint": {
                "power_pass_count": 5,
                "complex_amplitude_pass_count": 6,
            },
            "linear_signed_dwr_subset_screen": subset,
            "decision": "close_top_port_selective_p6_face_lane",
        },
        "location_oracle": {
            "face_band_rows": band_rows,
            "outer_periodic_failed_19_support": outer_failed_support,
            "outer_periodic_failed_19_negative_error_dot_action": (
                outer_alignment
            ),
            "right_inner_failed_19_support": right_inner[
                "failed_19_absolute_normalized_support"
            ],
            "right_inner_failed_19_negative_error_dot_action": right_inner[
                "failed_19_negative_error_dot_action"
            ],
            "outer_to_right_inner_support_ratio": (
                outer_failed_support
                / right_inner["failed_19_absolute_normalized_support"]
            ),
            "formal_boundary": (
                "actual selected-face DWR is a location oracle only; "
                "it is not an unrun local-h surplus"
            ),
        },
        "closure_discriminator": {
            "selected_outer_periodic": _forest_row(OUTER_RIGHT_MARK),
            "rejected_right_inner": _forest_row(RIGHT_INNER_MARK),
        },
        "selected_action": {
            "candidate_id": "h15_outer_top_periodic_p5fine_v1",
            "marked_root_nm": list(OUTER_RIGHT_MARK),
            "trace_degree": 5,
            "fine_child_interior_degree": 5,
            "fine_p5_cell_count": 32,
            "remaining_p6_cell_count": 116,
            "selected_p6_face_count": 0,
            "predicted_actual_conforming_active_fe_dofs": 84_850,
            "predicted_direct_solve_rows": 20_360,
            "formal_pde_authorization": (
                "one MPI8 discriminator only after MPI1/2/8 component "
                "identity and launch gates pass"
            ),
            "success_forecast": False,
        },
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
        raise ValueError("formal selection output path is fixed")
    if output.exists():
        raise FileExistsError("formal selection record is immutable")
    result = analyze()
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
