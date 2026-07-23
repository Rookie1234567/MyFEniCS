"""Correction-decay h/p classifier for Task035 research meshes."""

from __future__ import annotations

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
    return {
        "schema_version": "task035.hp-correction-decay-classifier.v1",
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
        "marked_cell_count": len(marked),
        "counts": counts,
        "classified_cell_count": classified,
        "p_candidate_fraction_of_classified": float(
            counts["p_candidate"] / max(classified, 1)
        ),
        "decisions": decisions,
        "decision_scope": (
            "research-only h/p candidates; no variable-p space or mesh mutation"
        ),
    }


__all__ = ["classify_hp_correction_decay"]
