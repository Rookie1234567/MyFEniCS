"""Correction-decay h/p classifier for Task035 research meshes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np


def classify_hp_correction_decay(
    canonical_cell_ids: np.ndarray,
    lower_pair_indicators: np.ndarray,
    higher_pair_indicators: np.ndarray,
    marked_canonical_cell_ids: list[int] | np.ndarray,
    *,
    degrees: tuple[int, int, int] = (4, 5, 6),
    p_decay_ratio_threshold: float = 0.5,
    significance_floor_fraction: float = 1.0e-12,
    p_down_indicator_fraction: float = 1.0e-3,
) -> dict[str, Any]:
    """Classify marked cells from consecutive p-correction decay.

    A higher/lower correction ratio at or below ``p_decay_ratio_threshold``
    indicates fast p-decay and therefore a smooth ``p_candidate``. Slower
    decay indicates an ``h_candidate``. Cells for which both corrections are
    below the global significance floor remain ``undetermined``.
    """

    ids = np.asarray(canonical_cell_ids, dtype=np.int64)
    lower = np.asarray(lower_pair_indicators, dtype=np.float64)
    higher = np.asarray(higher_pair_indicators, dtype=np.float64)
    marked = np.asarray(marked_canonical_cell_ids, dtype=np.int64)
    if (
        ids.ndim != 1
        or lower.shape != ids.shape
        or higher.shape != ids.shape
        or len(set(int(value) for value in ids)) != len(ids)
    ):
        raise ValueError("cell identities and correction arrays must be aligned")
    if (
        not np.all(np.isfinite(lower))
        or not np.all(np.isfinite(higher))
        or np.any(lower < 0.0)
        or np.any(higher < 0.0)
    ):
        raise ValueError("correction indicators must be finite and nonnegative")
    if (
        len(marked) == 0
        or len(set(int(value) for value in marked)) != len(marked)
        or not set(int(value) for value in marked).issubset(
            int(value) for value in ids
        )
    ):
        raise ValueError("marked canonical cell IDs must be a unique nonempty subset")
    if (
        len(degrees) != 3
        or degrees[1] != degrees[0] + 1
        or degrees[2] != degrees[1] + 1
    ):
        raise ValueError("classifier requires three consecutive polynomial degrees")
    if not 0.0 < float(p_decay_ratio_threshold) < 1.0:
        raise ValueError("p-decay ratio threshold must lie in (0, 1)")
    if not 0.0 <= float(significance_floor_fraction) < 1.0:
        raise ValueError("significance floor fraction must lie in [0, 1)")
    if not 0.0 < float(p_down_indicator_fraction) < 1.0:
        raise ValueError("p-down indicator fraction must lie in (0, 1)")

    value_by_id = {
        int(cell_id): (float(lower_value), float(higher_value))
        for cell_id, lower_value, higher_value in zip(
            ids, lower, higher, strict=True
        )
    }
    global_scale = max(
        float(np.max(lower, initial=0.0)),
        float(np.max(higher, initial=0.0)),
    )
    absolute_floor = float(significance_floor_fraction) * global_scale
    decisions: list[dict[str, Any]] = []
    counts = {"h_candidate": 0, "p_candidate": 0, "undetermined": 0}
    for cell_id in sorted(int(value) for value in marked):
        lower_value, higher_value = value_by_id[cell_id]
        if max(lower_value, higher_value) <= absolute_floor:
            decision = "undetermined"
            ratio = None
            reason = "both consecutive corrections are below significance floor"
        else:
            ratio = higher_value / max(lower_value, absolute_floor, np.finfo(float).tiny)
            if ratio <= float(p_decay_ratio_threshold):
                decision = "p_candidate"
                reason = "higher-order correction decays sufficiently fast"
            else:
                decision = "h_candidate"
                reason = "higher-order correction decay is slow or stalled"
        counts[decision] += 1
        decisions.append(
            {
                "canonical_cell_id": cell_id,
                "lower_pair_indicator": lower_value,
                "higher_pair_indicator": higher_value,
                "higher_to_lower_ratio": ratio,
                "decision": decision,
                "reason": reason,
            }
        )

    classified = counts["h_candidate"] + counts["p_candidate"]
    marked_set = set(int(value) for value in marked)
    p_down_floor = float(p_down_indicator_fraction) * global_scale
    action_counts = {
        "p_down": 0,
        "p_keep": 0,
        "p_up": 0,
        "h_refine": 0,
    }
    local_order_actions: list[dict[str, Any]] = []
    for cell_id in sorted(int(value) for value in ids):
        lower_value, higher_value = value_by_id[cell_id]
        ratio = higher_value / max(
            lower_value,
            absolute_floor,
            np.finfo(float).tiny,
        )
        is_marked = cell_id in marked_set
        if is_marked and max(lower_value, higher_value) <= absolute_floor:
            action = "p_keep"
            reason = "marked but below numerical significance floor"
        elif is_marked and ratio <= float(p_decay_ratio_threshold):
            action = "p_up"
            reason = "goal-important cell with fast consecutive p-decay"
        elif is_marked:
            action = "h_refine"
            reason = "goal-important cell with slow or stalled p-decay"
        elif max(lower_value, higher_value) <= p_down_floor:
            action = "p_down"
            reason = "unmarked cell below the conservative p-down floor"
        else:
            action = "p_keep"
            reason = "unmarked cell retains non-negligible correction"
        action_counts[action] += 1
        local_order_actions.append(
            {
                "canonical_cell_id": cell_id,
                "marked": is_marked,
                "lower_pair_indicator": lower_value,
                "higher_pair_indicator": higher_value,
                "higher_to_lower_ratio": ratio,
                "action": action,
                "reason": reason,
            }
        )
    return {
        "schema_version": "task035b.hp-correction-decay-classifier.v2",
        "status": "hp_candidate_classification_pass",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "method": "consecutive_goal_indicator_p_correction_decay",
        "degrees": list(degrees),
        "lower_pair": f"p{degrees[0]}_p{degrees[1]}",
        "higher_pair": f"p{degrees[1]}_p{degrees[2]}",
        "p_decay_ratio_threshold": float(p_decay_ratio_threshold),
        "significance_floor_fraction": float(significance_floor_fraction),
        "absolute_significance_floor": absolute_floor,
        "p_down_indicator_fraction": float(p_down_indicator_fraction),
        "absolute_p_down_floor": p_down_floor,
        "marked_cell_count": len(marked),
        "counts": counts,
        "classified_cell_count": classified,
        "p_candidate_fraction_of_classified": float(
            counts["p_candidate"] / max(classified, 1)
        ),
        "decisions": decisions,
        "local_order_action_counts": action_counts,
        "local_order_actions": local_order_actions,
        "decision_scope": (
            "research-only p-down/p-keep/p-up/h-refine candidates; no "
            "variable-p space or mesh mutation"
        ),
    }


def classify_hp_signals_v3(
    canonical_cell_ids: np.ndarray,
    eta_p_decay_ratio: np.ndarray,
    physical_hierarchical_decay_ratio: np.ndarray,
    physical_hierarchical_resolved: np.ndarray,
    coefficient_decay_ratio: np.ndarray,
    coefficient_decay_resolved: np.ndarray,
    p4_relative_projection_defect: np.ndarray,
    p5_relative_projection_defect: np.ndarray,
    goal_important_cell_ids: list[int] | np.ndarray,
    *,
    base_actions: list[str],
    material_interface: np.ndarray,
    corner_or_edge: np.ndarray,
    periodic_mate_groups: list[dict[str, Any]],
    phase_resolution_ratio: np.ndarray | None = None,
    fast_ratio_threshold: float = 0.35,
    slow_ratio_threshold: float = 0.55,
    p4_resolution_defect_limit: float = 0.5,
    phase_resolution_ratio_limit: float = 1.0,
    significance_floor: float = 1.0e-12,
) -> dict[str, Any]:
    """Fuse physical p-decay signals with goal and periodic constraints.

    Physical hierarchical energy and projection-defect decay are primary.
    Raw coefficient decay is retained as advisory evidence only.  Periodic
    equivalence classes are aggregated conservatively before decisions.
    """

    ids = np.asarray(canonical_cell_ids, dtype=np.int64)
    arrays = {
        "eta_p_decay_ratio": np.asarray(
            eta_p_decay_ratio,
            dtype=np.float64,
        ),
        "physical_hierarchical_decay_ratio": np.asarray(
            physical_hierarchical_decay_ratio,
            dtype=np.float64,
        ),
        "physical_hierarchical_resolved": np.asarray(
            physical_hierarchical_resolved,
            dtype=bool,
        ),
        "coefficient_decay_ratio": np.asarray(
            coefficient_decay_ratio,
            dtype=np.float64,
        ),
        "coefficient_decay_resolved": np.asarray(
            coefficient_decay_resolved,
            dtype=bool,
        ),
        "p4_relative_projection_defect": np.asarray(
            p4_relative_projection_defect,
            dtype=np.float64,
        ),
        "p5_relative_projection_defect": np.asarray(
            p5_relative_projection_defect,
            dtype=np.float64,
        ),
        "material_interface": np.asarray(material_interface, dtype=bool),
        "corner_or_edge": np.asarray(corner_or_edge, dtype=bool),
    }
    if (
        ids.ndim != 1
        or not np.array_equal(ids, np.arange(len(ids), dtype=np.int64))
        or any(value.shape != ids.shape for value in arrays.values())
        or len(base_actions) != len(ids)
    ):
        raise ValueError("v3 hp signals must align to contiguous canonical IDs")
    nonnegative_names = (
        "physical_hierarchical_decay_ratio",
        "coefficient_decay_ratio",
        "p4_relative_projection_defect",
        "p5_relative_projection_defect",
    )
    if any(
        not np.all(np.isfinite(arrays[name]))
        or np.any(arrays[name] < 0.0)
        for name in nonnegative_names
    ):
        raise ValueError("v3 physical hp signals must be finite and nonnegative")
    eta = arrays["eta_p_decay_ratio"]
    if np.any(np.isinf(eta)) or np.any(eta[np.isfinite(eta)] < 0.0):
        raise ValueError("eta p-decay ratios must be nonnegative or unresolved NaN")
    if not 0.0 < fast_ratio_threshold < slow_ratio_threshold < 1.0:
        raise ValueError("v3 fast/slow thresholds must satisfy 0 < fast < slow < 1")
    if (
        p4_resolution_defect_limit <= 0.0
        or phase_resolution_ratio_limit <= 0.0
        or significance_floor < 0.0
    ):
        raise ValueError("v3 resolution thresholds must be positive")
    allowed_base_actions = {
        "p_down_candidate",
        "p_keep_candidate",
        "p_up_candidate",
        "h_refine_candidate",
        "undetermined",
    }
    if any(action not in allowed_base_actions for action in base_actions):
        raise ValueError("v3 base action is not recognized")
    goal_ids = {int(value) for value in goal_important_cell_ids}
    if not goal_ids.issubset(set(ids.tolist())):
        raise ValueError("goal-important IDs are not a subset of canonical IDs")
    if phase_resolution_ratio is None:
        phase = np.full(len(ids), np.nan, dtype=np.float64)
    else:
        phase = np.asarray(phase_resolution_ratio, dtype=np.float64)
        if (
            phase.shape != ids.shape
            or np.any(np.isinf(phase))
            or np.any(phase[np.isfinite(phase)] < 0.0)
        ):
            raise ValueError("phase-resolution ratios are invalid")

    parent = list(range(len(ids)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for group in periodic_mate_groups:
        left = int(group["min_cell_id"])
        right = int(group["max_cell_id"])
        if left not in set(ids.tolist()) or right not in set(ids.tolist()):
            raise ValueError("periodic mate ID is outside the classifier mesh")
        union(left, right)
    components: dict[int, list[int]] = {}
    for cell_id in ids.tolist():
        components.setdefault(find(cell_id), []).append(cell_id)

    decisions: list[dict[str, Any]] = []
    action_counts = {
        "p_down_candidate": 0,
        "p_keep_candidate": 0,
        "p_up_candidate": 0,
        "h_refine_candidate": 0,
        "undetermined": 0,
    }
    component_rows: list[dict[str, Any]] = []
    for component_id, members in sorted(components.items()):
        member_array = np.asarray(members, dtype=np.int64)
        component_goal = bool(goal_ids.intersection(members))
        component_interface = bool(
            np.any(arrays["material_interface"][member_array])
        )
        component_corner = bool(
            np.any(arrays["corner_or_edge"][member_array])
        )
        eta_values = eta[member_array]
        eta_resolved = bool(np.all(np.isfinite(eta_values)))
        eta_worst = (
            float(np.max(eta_values)) if eta_resolved else None
        )
        hierarchical_resolved = bool(
            np.all(
                arrays["physical_hierarchical_resolved"][member_array]
            )
        )
        hierarchical_worst = float(
            np.max(
                arrays["physical_hierarchical_decay_ratio"][member_array]
            )
        )
        coefficient_resolved = bool(
            np.all(arrays["coefficient_decay_resolved"][member_array])
        )
        coefficient_worst = float(
            np.max(arrays["coefficient_decay_ratio"][member_array])
        )
        p4_defect = float(
            np.max(
                arrays["p4_relative_projection_defect"][member_array]
            )
        )
        p5_defect = float(
            np.max(
                arrays["p5_relative_projection_defect"][member_array]
            )
        )
        member_projection_scale = np.maximum(
            arrays["p4_relative_projection_defect"][member_array],
            arrays["p5_relative_projection_defect"][member_array],
        )
        projection_resolved = bool(
            np.all(member_projection_scale > significance_floor)
        )
        projection_decay = (
            float(
                np.max(
                    arrays["p5_relative_projection_defect"][member_array]
                    / np.maximum(
                        arrays[
                            "p4_relative_projection_defect"
                        ][member_array],
                        significance_floor,
                    )
                )
            )
            if projection_resolved
            else None
        )
        finite_phase = phase[member_array][
            np.isfinite(phase[member_array])
        ]
        phase_available = bool(len(finite_phase))
        phase_worst = (
            float(np.max(finite_phase)) if phase_available else None
        )
        resolution_failed = (
            p4_defect > p4_resolution_defect_limit
            or (
                phase_available
                and phase_worst is not None
                and phase_worst > phase_resolution_ratio_limit
            )
        )
        all_primary_resolved = (
            eta_resolved
            and hierarchical_resolved
            and projection_resolved
        )
        primary_ratios = (
            []
            if not all_primary_resolved
            else [
                float(eta_worst),
                hierarchical_worst,
                float(projection_decay),
            ]
        )
        all_fast = bool(primary_ratios) and all(
            value <= fast_ratio_threshold for value in primary_ratios
        )
        any_slow = bool(primary_ratios) and any(
            value >= slow_ratio_threshold for value in primary_ratios
        )
        if resolution_failed:
            action = "undetermined"
            reason = "independent resolution gate failed"
        elif not all_primary_resolved:
            if component_goal and (component_interface or component_corner):
                action = "p_keep_candidate"
                reason = (
                    "goal-important interface/corner signal is unresolved; "
                    "retain moderate p without inventing h evidence"
                )
            elif component_goal:
                action = "undetermined"
                reason = "goal-important primary smoothness signal is unresolved"
            else:
                action = (
                    "p_down_candidate"
                    if all(
                        base_actions[index] == "p_down_candidate"
                        for index in members
                    )
                    else "p_keep_candidate"
                )
                reason = "goal-unmarked unresolved component preserves base order"
        elif any_slow:
            action = (
                "h_refine_candidate"
                if component_goal
                else "p_keep_candidate"
            )
            reason = "at least one physical primary p-decay signal is slow"
        elif all_fast:
            if component_goal:
                action = "p_up_candidate"
                reason = "all physical primary p-decay signals are fast"
            else:
                action = (
                    "p_down_candidate"
                    if all(
                        base_actions[index] == "p_down_candidate"
                        for index in members
                    )
                    else "p_keep_candidate"
                )
                reason = "smooth but goal-unmarked component preserves base order"
        elif component_goal and component_corner:
            action = "h_refine_candidate"
            reason = "gray-zone physical decay with a corner prior"
        elif component_goal and component_interface:
            action = "p_keep_candidate"
            reason = "gray-zone physical decay at an interface retains moderate p"
        elif component_goal:
            action = "undetermined"
            reason = "gray-zone physical p-decay requires actual competition"
        else:
            action = "p_keep_candidate"
            reason = "goal-unmarked gray-zone component retains p"

        component_row = {
            "component_id": int(component_id),
            "canonical_cell_ids": members,
            "goal_important": component_goal,
            "material_interface": component_interface,
            "corner_or_edge": component_corner,
            "primary_signals_resolved": all_primary_resolved,
            "resolution_gate": (
                "failed" if resolution_failed else "pass"
            ),
            "phase_resolution_evidence": (
                "actual_or_fixture_value"
                if phase_available
                else "not_available_projection_defect_screen_only"
            ),
            "features": {
                "eta_p_decay_ratio_worst": eta_worst,
                "physical_hierarchical_decay_ratio_worst": (
                    hierarchical_worst
                ),
                "projection_defect_decay_ratio_worst": projection_decay,
                "p4_relative_projection_defect_worst": p4_defect,
                "p5_relative_projection_defect_worst": p5_defect,
                "phase_resolution_ratio_worst": phase_worst,
                "coefficient_decay_ratio_worst_advisory": (
                    coefficient_worst
                ),
                "coefficient_decay_resolved_advisory": (
                    coefficient_resolved
                ),
            },
            "action": action,
            "reason": reason,
        }
        component_rows.append(component_row)
        for cell_id in members:
            action_counts[action] += 1
            decisions.append(
                {
                    "canonical_cell_id": cell_id,
                    "periodic_component_id": int(component_id),
                    "action": action,
                    "reason": reason,
                    "goal_important": component_goal,
                    "individual_signals": {
                        "eta_p_decay_ratio": (
                            None
                            if not np.isfinite(eta[cell_id])
                            else float(eta[cell_id])
                        ),
                        "physical_hierarchical_decay_ratio": float(
                            arrays[
                                "physical_hierarchical_decay_ratio"
                            ][cell_id]
                        ),
                        "physical_hierarchical_resolved": bool(
                            arrays[
                                "physical_hierarchical_resolved"
                            ][cell_id]
                        ),
                        "coefficient_decay_ratio_advisory": float(
                            arrays["coefficient_decay_ratio"][cell_id]
                        ),
                        "coefficient_decay_resolved_advisory": bool(
                            arrays["coefficient_decay_resolved"][cell_id]
                        ),
                        "p4_relative_projection_defect": float(
                            arrays[
                                "p4_relative_projection_defect"
                            ][cell_id]
                        ),
                        "p5_relative_projection_defect": float(
                            arrays[
                                "p5_relative_projection_defect"
                            ][cell_id]
                        ),
                        "phase_resolution_ratio": (
                            None
                            if not np.isfinite(phase[cell_id])
                            else float(phase[cell_id])
                        ),
                    },
                }
            )
    decisions.sort(key=lambda row: int(row["canonical_cell_id"]))
    decision_identity = [
        [int(row["canonical_cell_id"]), str(row["action"])]
        for row in decisions
    ]
    decision_sha256 = hashlib.sha256(
        json.dumps(
            decision_identity,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "task035b.hp-signal-fusion-classifier.v3",
        "status": "hp_signal_fusion_classification_pass",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "thresholds": {
            "fast_ratio": float(fast_ratio_threshold),
            "slow_ratio": float(slow_ratio_threshold),
            "p4_resolution_defect_limit": float(
                p4_resolution_defect_limit
            ),
            "phase_resolution_ratio_limit": float(
                phase_resolution_ratio_limit
            ),
            "significance_floor": float(significance_floor),
        },
        "primary_signals": [
            "eta_p5p6_over_eta_p4p5",
            "physical_hierarchical_shell_decay",
            "p5_over_p4_projection_defect_decay",
        ],
        "advisory_signals": [
            "raw_cell_coefficient_shell_decay",
            "material_interface_and_corner_prior_in_gray_zone_only",
        ],
        "periodic_policy": (
            "transitive mate components aggregate worst physical signal, "
            "goal importance, and resolution failure before one shared action"
        ),
        "action_counts": action_counts,
        "components": component_rows,
        "decisions": decisions,
        "decision_identity_sha256": decision_sha256,
        "limitations": [
            "projection-defect resolution screening cannot exclude every alias",
            "missing independent phase resolution prevents production qualification",
            "h_refine remains provisional without same-patch actual competition",
        ],
    }


__all__ = [
    "classify_hp_correction_decay",
    "classify_hp_signals_v3",
]
