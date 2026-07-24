"""Build a Task035b p4/p5/p6 smoothness classification from two records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.adaptivity.hp_smoothness_classifier import (
    classify_hp_correction_decay,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pair_and_snapshot(
    payload: dict[str, Any],
) -> tuple[tuple[int, int], dict[str, Any]]:
    coarse = payload.get("coarse") or {}
    enriched = payload.get("enriched") or {}
    pair = (int(coarse.get("degree", -1)), int(enriched.get("degree", -1)))
    snapshot = (payload.get("R5") or {}).get("cell_indicator_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError(f"p{pair[0]}/p{pair[1]} record lacks a full R5 snapshot")
    if snapshot.get("storage") != "inline_complete_vector":
        raise ValueError("Task035b classifier requires a complete inline snapshot")
    return pair, snapshot


def build_hp_classifier_record(
    lower_payload: dict[str, Any],
    higher_payload: dict[str, Any],
    *,
    lower_source: dict[str, str] | None = None,
    higher_source: dict[str, str] | None = None,
    p_decay_ratio_threshold: float = 0.5,
    p_down_indicator_fraction: float = 1.0e-3,
) -> dict[str, Any]:
    """Validate and classify aligned p4/p5 and p5/p6 R5 indicators."""

    lower_pair, lower = _pair_and_snapshot(lower_payload)
    higher_pair, higher = _pair_and_snapshot(higher_payload)
    if lower_pair != (4, 5) or higher_pair != (5, 6):
        raise ValueError("Task035b classifier requires p4/p5 and p5/p6 records")
    if (
        lower.get("mesh_geometry_sha256")
        != higher.get("mesh_geometry_sha256")
    ):
        raise ValueError("p4/p5 and p5/p6 snapshots use different mesh geometry")
    lower_ids = np.asarray(lower["canonical_cell_ids"], dtype=np.int64)
    higher_ids = np.asarray(higher["canonical_cell_ids"], dtype=np.int64)
    if not np.array_equal(lower_ids, higher_ids):
        raise ValueError("p4/p5 and p5/p6 canonical cell IDs are not aligned")
    lower_marked = set(
        int(value)
        for value in (lower_payload.get("R5") or {}).get(
            "marked_canonical_cell_ids", []
        )
    )
    higher_marked = set(
        int(value)
        for value in (higher_payload.get("R5") or {}).get(
            "marked_canonical_cell_ids", []
        )
    )
    marked_union = sorted(lower_marked | higher_marked)
    if not marked_union:
        raise ValueError("p4/p5 and p5/p6 records have no canonical marked cells")
    classifier = classify_hp_correction_decay(
        lower_ids,
        np.asarray(lower["indicator_values"], dtype=np.float64),
        np.asarray(higher["indicator_values"], dtype=np.float64),
        marked_union,
        degrees=(4, 5, 6),
        p_decay_ratio_threshold=float(p_decay_ratio_threshold),
        p_down_indicator_fraction=float(p_down_indicator_fraction),
    )
    return {
        "schema_version": "task035b.same-mesh-p4-p5-p6-classifier.v1",
        "status": "same_mesh_hp_classifier_pass",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "geometry": "Task034 fixed rectangular block grating",
        "mesh_geometry_sha256": lower["mesh_geometry_sha256"],
        "cell_count": int(len(lower_ids)),
        "indicator_pairs": {
            "eta_p4p5": {
                "snapshot_sha256": lower[
                    "canonical_ids_and_values_sha256"
                ],
                "indicator_sum": lower["indicator_sum"],
            },
            "eta_p5p6": {
                "snapshot_sha256": higher[
                    "canonical_ids_and_values_sha256"
                ],
                "indicator_sum": higher["indicator_sum"],
            },
        },
        "marked_policy": "union_of_p4p5_and_p5p6_Dorfler_sets",
        "marked_canonical_cell_ids": marked_union,
        "source_records": {
            "p4_p5": lower_source,
            "p5_p6": higher_source,
        },
        "classifier": classifier,
        "scope_note": (
            "R5 correction-decay research classification only; DWR R00/R/T "
            "and conformity closure remain separate gates before local-p use"
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p4-p5-record", type=Path, required=True)
    parser.add_argument("--p5-p6-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--p-decay-ratio-threshold", type=float, default=0.5)
    parser.add_argument("--p-down-indicator-fraction", type=float, default=1.0e-3)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    lower_path = args.p4_p5_record.resolve()
    higher_path = args.p5_p6_record.resolve()
    record = build_hp_classifier_record(
        json.loads(lower_path.read_text(encoding="utf-8")),
        json.loads(higher_path.read_text(encoding="utf-8")),
        lower_source={
            "path": str(lower_path),
            "sha256": _sha256(lower_path),
        },
        higher_source={
            "path": str(higher_path),
            "sha256": _sha256(higher_path),
        },
        p_decay_ratio_threshold=args.p_decay_ratio_threshold,
        p_down_indicator_fraction=args.p_down_indicator_fraction,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
