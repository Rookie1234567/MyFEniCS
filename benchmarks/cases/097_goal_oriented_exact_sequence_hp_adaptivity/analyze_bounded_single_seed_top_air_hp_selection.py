#!/usr/bin/env python3
"""Freeze the bounded single-root-seed Task035d top-air h/p decision.

The tracked selective-face DWR is used only as a location oracle.  This tool
enumerates every distinct closure action obtained from one requested top-air
root represented by that compact DWR, adds the one legal single-root seed
absent from the compact endpoint as an explicit unranked action, and combines
those signals with measured Stage-4 structural costs.  Multi-seed combinations
are not evaluated.  This does not claim an unrun local-h surplus or forecast
PDE success.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
CASE095_RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
)
COMPACT = RECORD_DIR / "selective_face_selection_compact_v1.json"
PREFLIGHT = (
    RECORD_DIR / "bounded_single_seed_top_air_hp_preflight_v1.json"
)
COARSE_CHECK = RECORD_DIR / (
    "h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json"
)
H13_RECORD = CASE095_RECORDS / (
    "fixed_p5trace_p6interior_h13_directional_z_mpi8.json"
)
H15_RECORD = CASE095_RECORDS / (
    "fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json"
)
SUPERSEDED_OUTER = (
    RECORD_DIR / "outer_top_periodic_p5fine_selection_v1.json"
)
DEFAULT_OUTPUT = (
    RECORD_DIR / "bounded_single_seed_top_air_hp_selection_v2.json"
)
ANALYZER_RELATIVE = str(Path(__file__).resolve().relative_to(ROOT))

SELECTED_CANDIDATE_ID = (
    "h15_left_grating_top_closure_p5fine_v1"
)
PHYSICAL_X_BANDS = (
    (0.0, 8.25),
    (16.5, 25.0),
    (25.0, 33.5),
    (33.5, 41.75),
    (41.75, 50.0),
)
ACTION_BANDS = {
    "outer_periodic": ((0.0, 8.25), (41.75, 50.0)),
    "left_grating_top": ((16.5, 25.0),),
    "right_grating_top": ((25.0, 33.5),),
    "right_inner": ((33.5, 41.75),),
}
EXPECTED_PREFLIGHT_ACTIONS = {
    "outer_left_alias": {
        "requested_mark_nm": [0.0, 0.0, 120.0, 8.25, 12.5, 130.0],
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 3,
            "user": 1,
        },
        "split_root_count": 4,
    },
    "outer_right_alias": {
        "requested_mark_nm": [
            41.75,
            0.0,
            120.0,
            50.0,
            12.5,
            130.0,
        ],
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 3,
            "user": 1,
        },
        "split_root_count": 4,
    },
    "left_inner_without_compact_dwr": {
        "requested_mark_nm": [
            8.25,
            0.0,
            120.0,
            16.5,
            12.5,
            130.0,
        ],
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 1,
            "user": 1,
        },
        "split_root_count": 2,
    },
    "left_grating_top": {
        "requested_mark_nm": [
            16.5,
            0.0,
            120.0,
            25.0,
            12.5,
            130.0,
        ],
        "closure_counts": {
            "balance": 0,
            "material": 4,
            "periodic": 1,
            "user": 1,
        },
        "split_root_count": 6,
    },
    "right_grating_top": {
        "requested_mark_nm": [
            25.0,
            0.0,
            120.0,
            33.5,
            12.5,
            130.0,
        ],
        "closure_counts": {
            "balance": 0,
            "material": 4,
            "periodic": 1,
            "user": 1,
        },
        "split_root_count": 6,
    },
    "right_inner": {
        "requested_mark_nm": [
            33.5,
            0.0,
            120.0,
            41.75,
            12.5,
            130.0,
        ],
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 1,
            "user": 1,
        },
        "split_root_count": 2,
    },
}


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


def _commit_blob_sha(source_sha: str, relative: str) -> str:
    content = subprocess.check_output(
        ("git", "show", f"{source_sha}:{relative}"),
        cwd=ROOT,
    )
    return hashlib.sha256(content).hexdigest()


def _source_identity(
    source_sha: str,
    paths: tuple[Path, ...],
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    relative_files = (
        ANALYZER_RELATIVE,
        *(str(path.relative_to(ROOT)) for path in paths),
    )
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
            *relative_files,
        ),
        cwd=ROOT,
        text=True,
    ).strip()
    live = {
        relative: _sha256(ROOT / relative)
        for relative in relative_files
    }
    committed = {
        relative: _commit_blob_sha(source_sha, relative)
        for relative in relative_files
    }
    if head != source_sha or status or live != committed:
        raise RuntimeError(
            "selection requires clean committed algorithm and inputs"
        )
    return {
        "head": head,
        "status_lines": [],
        "verified_clean_algorithm_and_inputs": True,
        "file_sha256": live,
    }


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


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
) -> tuple[
    tuple[tuple[int, int], ...],
    dict[str, dict[tuple[int, int], float]],
]:
    bands = tuple(
        sorted(
            {
                _face_band(row)
                for goal in goals.values()
                for row in goal["face_contributions"]
            }
        )
    )
    if len(bands) != 5:
        raise ValueError(
            "the compact selective-face report must contain five x bands"
        )
    result: dict[str, dict[tuple[int, int], float]] = {}
    for label, goal in goals.items():
        by_band = {band: 0.0 for band in bands}
        counts: Counter[tuple[int, int]] = Counter()
        for row in goal["face_contributions"]:
            band = _face_band(row)
            by_band[band] += float(row["signed_real_contribution"])
            counts[band] += 1
        if set(counts) != set(bands) or set(counts.values()) != {2}:
            raise ValueError(
                f"{label} does not have two y faces per x band"
            )
        result[str(label)] = by_band
    return bands, result


def _component_errors(
    channel_comparison: Mapping[str, Any],
) -> tuple[dict[str, float], tuple[str, ...]]:
    errors: dict[str, float] = {}
    failed: list[str] = []
    for channel in channel_comparison["channels"]:
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
        raise ValueError(
            "the frozen selective endpoint must expose 36/19 goals"
        )
    return errors, tuple(sorted(failed))


def _normalized_contributions(
    *,
    bands: tuple[tuple[int, int], ...],
    contributions: Mapping[
        str,
        Mapping[tuple[int, int], float],
    ],
    goals: Mapping[str, Any],
) -> dict[str, dict[tuple[int, int], float]]:
    return {
        label: {
            band: float(by_band[band])
            / float(goals[label]["unchanged_v0_absolute_tolerance"])
            for band in bands
        }
        for label, by_band in contributions.items()
    }


def _band_rows(
    *,
    bands: tuple[tuple[int, int], ...],
    normalized: Mapping[
        str,
        Mapping[tuple[int, int], float],
    ],
    errors: Mapping[str, float],
    failed_labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    failed = set(failed_labels)
    rows = []
    for physical, band in zip(PHYSICAL_X_BANDS, bands, strict=True):
        rows.append(
            {
                "physical_x_nm": list(physical),
                "quantized_x_band": list(band),
                "all_36_absolute_normalized_support": sum(
                    abs(normalized[label][band])
                    for label in normalized
                ),
                "failed_19_absolute_normalized_support": sum(
                    abs(normalized[label][band]) for label in failed
                ),
                "failed_19_negative_error_dot_action": -sum(
                    errors[label] * normalized[label][band]
                    for label in failed
                ),
            }
        )
    return rows


def _subset_screen(
    *,
    coarse: Mapping[str, Any],
    bands: tuple[tuple[int, int], ...],
    contributions: Mapping[
        str,
        Mapping[tuple[int, int], float],
    ],
) -> dict[str, Any]:
    rows = []
    for bits in itertools.product((0, 1), repeat=len(bands)):
        selected = {
            band
            for band, enabled in zip(bands, bits, strict=True)
            if enabled
        }
        power_passes = 0
        amplitude_passes = 0
        regressed = set()
        for channel in coarse["channel_comparison"]["channels"]:
            prefix = _channel_prefix(channel)
            amplitude = [
                float(value)
                for value in channel[
                    "candidate_outgoing_amplitude_at_boundary"
                ]
            ]
            for index, suffix in enumerate(("real", "imag")):
                label = f"{prefix}_amplitude_{suffix}"
                amplitude[index] += sum(
                    contributions[label][band] for band in selected
                )
            reference = complex(
                *map(
                    float,
                    channel[
                        "reference_outgoing_amplitude_at_boundary"
                    ],
                )
            )
            predicted = complex(*amplitude)
            amplitude_pass = (
                abs(predicted - reference)
                <= float(
                    channel[
                        "unchanged_v0_complex_amplitude_tolerance"
                    ]
                )
            )
            coarse_amplitude = complex(
                *map(
                    float,
                    channel[
                        "candidate_outgoing_amplitude_at_boundary"
                    ],
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
                regressed.add(
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
                "predicted_complex_amplitude_pass_count": (
                    amplitude_passes
                ),
                "regressed_previously_passing_channel_count": len(
                    regressed
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
            row["predicted_complex_amplitude_pass_count"]
            for row in rows
        ),
        "best_fail_closed_subset": best,
        "no_subset_predicts_12_plus_12": all(
            row["predicted_power_pass_count"] < 12
            or row["predicted_complex_amplitude_pass_count"] < 12
            for row in rows
        ),
    }


def _action_rows(
    *,
    bands: tuple[tuple[int, int], ...],
    normalized: Mapping[
        str,
        Mapping[tuple[int, int], float],
    ],
    errors: Mapping[str, float],
    failed_labels: tuple[str, ...],
    preflight: Mapping[str, Any],
) -> list[dict[str, Any]]:
    quantized_by_physical = dict(
        zip(PHYSICAL_X_BANDS, bands, strict=True)
    )
    failed = set(failed_labels)
    baseline = preflight["fixed_h15_baseline"]
    action_costs = preflight["action_rows"]
    rows = []
    for action_id, physical_bands in ACTION_BANDS.items():
        quantized = tuple(
            quantized_by_physical[physical]
            for physical in physical_bands
        )
        cost_id = (
            "outer_right_alias"
            if action_id == "outer_periodic"
            else action_id
        )
        cost = action_costs[cost_id]
        closure_by_goal = {
            label: sum(normalized[label][band] for band in quantized)
            for label in normalized
        }
        added_dofs = (
            int(cost["actual_full3d_equivalent_active_fe_dofs"])
            - int(
                baseline[
                    "actual_full3d_equivalent_active_fe_dofs"
                ]
            )
        )
        added_rows = (
            int(cost["predicted_direct_solve_rows"])
            - int(baseline["predicted_direct_solve_rows"])
        )
        alignment = -sum(
            errors[label] * closure_by_goal[label] for label in failed
        )
        row = {
            "action_id": action_id,
            "physical_x_bands_nm": [
                list(band) for band in physical_bands
            ],
            "quantized_x_bands": [
                list(band) for band in quantized
            ],
            "dwr_status": "available_from_frozen_ten_face_compact",
            "all_36_sum_band_absolute_normalized_support": sum(
                abs(normalized[label][band])
                for label in normalized
                for band in quantized
            ),
            "all_36_closure_combined_absolute_normalized_support": sum(
                abs(closure_by_goal[label]) for label in normalized
            ),
            "failed_19_sum_band_absolute_normalized_support": sum(
                abs(normalized[label][band])
                for label in failed
                for band in quantized
            ),
            "failed_19_closure_combined_absolute_normalized_support": sum(
                abs(closure_by_goal[label]) for label in failed
            ),
            "failed_19_negative_error_dot_action": alignment,
            "actual_full3d_equivalent_active_fe_dofs": cost[
                "actual_full3d_equivalent_active_fe_dofs"
            ],
            "predicted_direct_solve_rows": cost[
                "predicted_direct_solve_rows"
            ],
            "added_active_fe_dofs": added_dofs,
            "added_solve_rows": added_rows,
            "alignment_per_1000_added_active_fe_dofs": (
                1000.0 * alignment / added_dofs
            ),
            "alignment_per_1000_added_solve_rows": (
                1000.0 * alignment / added_rows
            ),
            "dof_budget_pass": (
                cost["actual_full3d_equivalent_active_fe_dofs"]
                <= 90_000
            ),
            "positive_alignment": alignment > 0.0,
        }
        row["ranking_eligible"] = (
            row["dof_budget_pass"] and row["positive_alignment"]
        )
        rows.append(row)
    unavailable_cost = action_costs[
        "left_inner_without_compact_dwr"
    ]
    rows.append(
        {
            "action_id": "left_inner_without_compact_dwr",
            "physical_x_bands_nm": [[8.25, 16.5]],
            "dwr_status": "not_available_from_compact",
            "ranking_eligible": False,
            "reason": (
                "the compact DWR coarse endpoint already contains this "
                "local-h split; its contribution cannot be set to zero"
            ),
            "actual_full3d_equivalent_active_fe_dofs": unavailable_cost[
                "actual_full3d_equivalent_active_fe_dofs"
            ],
            "predicted_direct_solve_rows": unavailable_cost[
                "predicted_direct_solve_rows"
            ],
            "dof_budget_pass": (
                unavailable_cost[
                    "actual_full3d_equivalent_active_fe_dofs"
                ]
                <= 90_000
            ),
        }
    )
    return rows


def analyze(source_sha: str) -> dict[str, Any]:
    input_paths = (
        COMPACT,
        PREFLIGHT,
        COARSE_CHECK,
        H13_RECORD,
        H15_RECORD,
        SUPERSEDED_OUTER,
    )
    source = _source_identity(source_sha, input_paths)
    compact = _strict_load(COMPACT)
    preflight = _strict_load(PREFLIGHT)
    coarse = _strict_load(COARSE_CHECK)
    h13 = _strict_load(H13_RECORD)
    h15 = _strict_load(H15_RECORD)
    superseded = _strict_load(SUPERSEDED_OUTER)
    goals = compact["goal_dwr"]["goals"]
    bands, contributions = _paired_contributions(goals)
    errors, failed_labels = _component_errors(
        compact["selective_channel_comparison"]
    )
    normalized = _normalized_contributions(
        bands=bands,
        contributions=contributions,
        goals=goals,
    )
    band_rows = _band_rows(
        bands=bands,
        normalized=normalized,
        errors=errors,
        failed_labels=failed_labels,
    )
    action_rows = _action_rows(
        bands=bands,
        normalized=normalized,
        errors=errors,
        failed_labels=failed_labels,
        preflight=preflight,
    )
    eligible = [row for row in action_rows if row["ranking_eligible"]]
    ranked = sorted(
        eligible,
        key=lambda row: (
            row["alignment_per_1000_added_active_fe_dofs"],
            row["alignment_per_1000_added_solve_rows"],
            row["failed_19_negative_error_dot_action"],
        ),
        reverse=True,
    )
    selected = ranked[0] if ranked else {}
    by_action = {
        row["action_id"]: row for row in action_rows
    }
    left_action = by_action["left_grating_top"]
    outer_action = by_action["outer_periodic"]
    preflight_rows = preflight.get("action_rows")
    preflight_rows = (
        preflight_rows if isinstance(preflight_rows, dict) else {}
    )
    preflight_catalog_exact = (
        set(preflight_rows) == set(EXPECTED_PREFLIGHT_ACTIONS)
        and preflight.get("unique_action_aliases")
        == {
            "outer_periodic": [
                "outer_left_alias",
                "outer_right_alias",
            ],
            "left_inner_without_compact_dwr": [
                "left_inner_without_compact_dwr"
            ],
            "left_grating_top": ["left_grating_top"],
            "right_grating_top": ["right_grating_top"],
            "right_inner": ["right_inner"],
        }
        and all(
            row.get("pass") is True
            and row.get("requested_mark_nm")
            == EXPECTED_PREFLIGHT_ACTIONS[action_id][
                "requested_mark_nm"
            ]
            and row.get("closure_counts")
            == EXPECTED_PREFLIGHT_ACTIONS[action_id]["closure_counts"]
            and row.get("split_root_count")
            == EXPECTED_PREFLIGHT_ACTIONS[action_id][
                "split_root_count"
            ]
            for action_id, row in preflight_rows.items()
        )
    )
    subset = _subset_screen(
        coarse=coarse,
        bands=bands,
        contributions=contributions,
    )
    selected_faces = compact["selected_p6_face_geometry_keys"]
    checks = {
        "compact_dwr_authority_pass": (
            compact.get("pass") is True
            and compact["goal_dwr"]["passed_real_goal_count"] == 36
            and len(goals) == 36
        ),
        "structural_preflight_pass": preflight.get("pass") is True,
        "preflight_single_seed_catalog_identity": (
            preflight.get("schema_version")
            == "case097.bounded-single-seed-top-air-hp-preflight.v1"
            and preflight.get("status")
            == "bounded_single_seed_top_air_hp_preflight_pass"
            and preflight_catalog_exact
        ),
        "selective_endpoint_is_controlled_negative": (
            compact["selective_channel_comparison"][
                "significant_power_pass_count"
            ]
            == 5
            and compact["selective_channel_comparison"][
                "significant_complex_amplitude_pass_count"
            ]
            == 6
        ),
        "frozen_ten_face_subset_has_no_complete_signal": (
            subset["subset_count"] == 32
            and subset["no_subset_predicts_12_plus_12"] is True
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
        "complete_available_single_seed_action_catalog": (
            {row["action_id"] for row in action_rows}
            == {
                "outer_periodic",
                "left_inner_without_compact_dwr",
                "left_grating_top",
                "right_grating_top",
                "right_inner",
            }
        ),
        "unavailable_action_is_not_zero_filled": (
            next(
                row
                for row in action_rows
                if row["action_id"]
                == "left_inner_without_compact_dwr"
            )["dwr_status"]
            == "not_available_from_compact"
        ),
        "selected_action_is_unique_cost_normalized_positive": (
            selected.get("action_id") == "left_grating_top"
            and selected[
                "actual_full3d_equivalent_active_fe_dofs"
            ]
            == 88_915
            and selected["predicted_direct_solve_rows"] == 21_650
            and len(ranked) == 2
            and {
                row["action_id"] for row in ranked
            }
            == {"outer_periodic", "left_grating_top"}
            and left_action["failed_19_negative_error_dot_action"]
            > outer_action["failed_19_negative_error_dot_action"]
            and left_action[
                "alignment_per_1000_added_active_fe_dofs"
            ]
            > outer_action[
                "alignment_per_1000_added_active_fe_dofs"
            ]
            and left_action[
                "alignment_per_1000_added_solve_rows"
            ]
            > outer_action[
                "alignment_per_1000_added_solve_rows"
            ]
        ),
        "superseded_outer_v1_preserved": (
            superseded.get("pass") is True
            and superseded.get("status")
            == "outer_top_periodic_p5fine_selection_pass"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            "case097.bounded-single-seed-top-air-hp-selection.v2"
        ),
        "status": (
            "bounded_single_seed_top_air_hp_selection_pass"
            if not failures
            else "bounded_single_seed_top_air_hp_selection_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "source_sha": source_sha,
        "source_identity": source,
        "inputs": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in input_paths
        },
        "superseded_outer_v1": {
            "path": str(SUPERSEDED_OUTER.relative_to(ROOT)),
            "sha256": _sha256(SUPERSEDED_OUTER),
            "classification": (
                "incomplete_action_catalog_controlled_negative"
            ),
            "reason": (
                "v1 compared only outer-periodic and right-inner actions, "
                "omitting the stronger legal x=16.5..25 closure"
            ),
            "pde_started_for_superseded_v2_lane": False,
        },
        "frozen_ten_face_subset_lane": {
            "catalog_sha256": _json_sha256(selected_faces),
            "selected_face_count": len(selected_faces),
            "linear_signed_dwr_subset_screen": subset,
            "decision": "close_frozen_ten_face_subset_lane",
            "whole_top_port_selective_p6_lane": (
                "not_closed_unrun_faces_orbits_and_edge_modes_remain"
            ),
        },
        "location_oracle": {
            "face_band_rows": band_rows,
            "action_rows": action_rows,
            "ranked_positive_budget_feasible_action_ids": [
                row["action_id"] for row in ranked
            ],
            "formal_boundary": (
                "actual selective-face DWR is a frozen ten-face location "
                "oracle only; it is not an unrun local-h surplus"
            ),
        },
        "selected_action": {
            "candidate_id": SELECTED_CANDIDATE_ID,
            "action_id": selected.get("action_id"),
            "marked_root_nm": [
                16.5,
                0.0,
                120.0,
                25.0,
                12.5,
                130.0,
            ],
            "closure_counts": {
                "balance": 0,
                "material": 4,
                "periodic": 1,
                "user": 1,
            },
            "trace_degree": 5,
            "fine_child_interior_degree": 5,
            "fine_p5_cell_count": 48,
            "remaining_p6_cell_count": 114,
            "selected_p6_face_count": 0,
            "actual_full3d_equivalent_active_fe_dofs": selected.get(
                "actual_full3d_equivalent_active_fe_dofs"
            ),
            "predicted_direct_solve_rows": selected.get(
                "predicted_direct_solve_rows"
            ),
            "formal_pde_authorization": (
                "one MPI8 discriminator only after MPI1/2/8 component "
                "identity and dedicated launch/solver gates pass"
            ),
            "actual_local_h_dwr_surplus_available": False,
            "success_forecast": False,
        },
        "multi_seed_combinations": {
            "status": "not_evaluated",
            "reason": (
                "this discriminator ranks only one requested root seed "
                "and its mandatory periodic/material closure"
            ),
        },
        "ordinary_default_changed": False,
        "production_qualified": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()
    if output != DEFAULT_OUTPUT.resolve():
        raise ValueError("formal selection output path is fixed")
    if output.exists():
        raise FileExistsError("formal selection record is immutable")
    result = analyze(str(args.source_sha))
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
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
