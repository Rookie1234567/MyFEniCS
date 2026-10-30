"""Deterministic, output-independent six-dimensional experimental design."""
from __future__ import annotations

import hashlib
import json
import math
import random

OUTPUTS = ("R_total", "T_total", "R00_total")
ANCHORS = (
    (0.5,) * 6,
    (0.75,) * 6,
    (1.0,) * 6,
    (0.5, 1.0, 0.5, 1.0, 0.5, 1.0),
)
DESIGN_SEED = 440700


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def geometry_key(thickness_nm):
    if len(thickness_nm) != 6:
        raise ValueError("six independent thicknesses required")
    if any(type(x) not in (int, float) for x in thickness_nm):
        raise ValueError("thickness must be a JSON number, never bool or numeric text")
    values = tuple(float(x) for x in thickness_nm)
    if not all(math.isfinite(x) and 0.5 <= x <= 1.0 for x in values):
        raise ValueError("thickness outside frozen [0.5, 1.0] nm")
    # No rounding here: nearby but unequal complete geometries stay distinct.
    return tuple(x.hex() for x in values)


def _candidate_pool(seed, count=512):
    rng = random.Random(seed)
    axes = []
    for _ in range(6):
        permutation = list(range(count))
        rng.shuffle(permutation)
        axes.append([(j + rng.random()) / count for j in permutation])
    return [tuple(round(0.5 + 0.5 * axes[j][i], 12) for j in range(6))
            for i in range(count)]


def _spread(pool, selected, count):
    """Greedy maximin on a seeded LHS pool; prefixes are NOT themselves LHS."""
    selected = list(selected)
    for _ in range(count):
        distances = [min(sum((a - b) ** 2 for a, b in zip(p, q))
                         for q in selected) for p in pool]
        index = max(range(len(pool)), key=lambda i: (distances[i], -i))
        selected.append(pool.pop(index))
    return selected[-count:]


def make_design(seed=DESIGN_SEED, train_count=8, dev_count=4, blind_count=6):
    """Counts are planning choices, NOT mandatory runs or research stopping caps."""
    if any(type(n) is not int for n in (train_count, dev_count, blind_count, seed)):
        raise ValueError("integer split sizes required")
    if train_count < 4 or dev_count < 1 or blind_count < 1:
        raise ValueError("A-D plus nonempty disjoint holdouts required")
    train = list(ANCHORS)
    if train_count > 4:
        train += _spread(_candidate_pool(seed, max(512, 4 * train_count)), train, train_count - 4)
    dev = _spread(_candidate_pool(seed + 1, max(512, 4 * dev_count)), train, dev_count)
    blind = _spread(_candidate_pool(seed + 2, max(512, 4 * blind_count)), train + dev, blind_count)
    points = []
    for split, values in (("train", train), ("dev", dev), ("blind", blind)):
        for index, values_i in enumerate(values):
            points.append({"sample_id": f"{split}-{index + 1:03d}", "split": split,
                           "order": index + 1, "thickness_nm": list(values_i),
                           "anchor": "ABCD"[index] if split == "train" and index < 4 else None})
    design = {"schema": "sixlayer-design-v1", "seed": seed,
              "sampling": "fixed LHS candidate pool512 then greedy maximin; no output adaptation",
              "range_nm": [0.5, 1.0],
              "planned_counts": {"train": train_count, "dev": dev_count, "blind": blind_count},
              "training_rule": "arbitrary nested contiguous prefixes starting with A-D; no obligation to fill pool",
              "points": points, "blind_labels": "separate protected file; never in this design"}
    validate_design(design)
    return design


def extend_training(design, additional=4, *, reason):
    """Add output-justified training points without replacing dev/blind geometries."""
    validate_design(design)
    if additional != 4 or not isinstance(reason, str) or not reason.strip():
        raise ValueError("one justified four-point extension required")
    result = json.loads(json.dumps(design))
    current = [p["thickness_nm"] for p in result["points"] if p["split"] == "train"]
    excluded = {geometry_key(p["thickness_nm"]) for p in result["points"]}
    pool = [p for p in _candidate_pool(design["seed"]) if geometry_key(p) not in excluded]
    if len(pool) < additional:
        raise ValueError("candidate pool exhausted; declare a new pool strategy before more sampling")
    new = _spread(pool, current, additional)
    rows = [{"sample_id": f"train-{len(current) + i + 1:03d}", "split": "train",
             "order": len(current) + i + 1, "thickness_nm": list(p), "anchor": None}
            for i, p in enumerate(new)]
    result["points"] = ([p for p in result["points"] if p["split"] == "train"] + rows
                        + [p for p in result["points"] if p["split"] != "train"])
    result["planned_counts"]["train"] += additional
    result.setdefault("extensions", []).append({"prior_design_sha256": digest(design), "reason": reason})
    validate_design(result)
    return result


def validate_design(design):
    if design["schema"] != "sixlayer-design-v1" or design["range_nm"] != [0.5, 1.0]:
        raise ValueError("design contract changed")
    points = design["points"]
    keys = [geometry_key(p["thickness_nm"]) for p in points]
    ids = [p["sample_id"] for p in points]
    counts = design["planned_counts"]
    if set(counts) != {"train", "dev", "blind"} or any(type(n) is not int for n in counts.values()):
        raise ValueError("invalid planned split counts")
    if counts["train"] < 4 or min(counts.values()) < 1:
        raise ValueError("invalid planned split counts")
    total = sum(counts.values())
    if len(points) != total or len(set(keys)) != total or len(set(ids)) != total:
        raise ValueError("duplicate or missing complete geometries/sample IDs")
    for split, count in counts.items():
        rows = [p for p in points if p["split"] == split]
        if any(type(p["order"]) is not int for p in rows):
            raise ValueError("integer point order required")
        if [p["order"] for p in rows] != list(range(1, count + 1)):
            raise ValueError("wrong split count/order")
        if any(p["sample_id"] != f"{split}-{i + 1:03d}" for i, p in enumerate(rows)):
            raise ValueError("sample ID/order mismatch")
    first = [p for p in points if p["split"] == "train"][:4]
    if [geometry_key(p["thickness_nm"]) for p in first] != [geometry_key(a) for a in ANCHORS]:
        raise ValueError("A-D must be first four training points")
    if any(set(p) != {"sample_id", "split", "order", "thickness_nm", "anchor"} for p in points):
        raise ValueError("design cannot carry labels or unreviewed fields")
    return {p["sample_id"]: p for p in points}


def permitted_batch_count(remaining_seconds, recent_complete_seconds, requested, reserve_seconds=1800):
    """Budget advice only; never starts a PDE or resets the owner's time ledger."""
    if not math.isfinite(remaining_seconds) or remaining_seconds < 0 or requested < 0:
        raise ValueError("invalid elapsed time/request")
    if not recent_complete_seconds or not all(math.isfinite(t) and t > 0 for t in recent_complete_seconds):
        return {"count": 0, "reason": "measured full-sample times required"}
    slow = max(recent_complete_seconds)
    remaining = max(0, remaining_seconds - reserve_seconds)
    return {"count": min(int(requested), int(remaining // (1.3 * slow))),
            "reserve_seconds": reserve_seconds, "per_sample_budget_seconds": 1.3 * slow}
