"""Label-free selection of retained committed states for equal-wall diagnostics.

This metadata-only module does not import Torch, FE, reference data or solvers.
The old and new clocks include setup; inherited prefixes are attributed once.
"""

import hashlib
import json
from pathlib import Path


def retained_before(index, target):
    entry = index["files"]["checkpoint_index"]
    path = Path(entry["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("COMMON_WALL_CHECKPOINT_INDEX_HASH_CHANGED")
    records = json.loads(path.read_text())["checkpoints"]
    directory = Path(index["files"]["durable_final"]["path"]).parent
    eligible = []
    for record in records:
        meta = record["metadata"]
        elapsed = meta.get("logical_path_seconds", meta["elapsed_charged_seconds"])
        if (
            record.get("retained")
            and (directory / record["name"]).is_file()
            and elapsed <= target
            and meta["source_sha"] == index["source_sha"]
        ):
            eligible.append((elapsed, record))
    if not eligible:
        return dict(status="NOT_RETAINED", target_logical_seconds=target)
    elapsed, record = max(eligible, key=lambda x: (x[0], x[1]["generation"]))
    return dict(
        status="RETAINED_COMMITTED",
        target_logical_seconds=target,
        actual_logical_seconds=elapsed,
        gap_seconds=target - elapsed,
        checkpoint=dict(path=str(directory / record["name"]), sha256=record["sha256"]),
        metadata=record["metadata"],
        generation=record["generation"],
        source_sha=index["source_sha"],
        reference_used_for_selection=False,
    )


def common_wall_pair(new, old):
    # End-of-worker clocks contain import/setup and publishing costs. Selection
    # uses earlier persisted boundaries, and explicitly retains the time gap.
    new_end = new["result"]["logical_path_seconds"]
    old_end = old["result"]["launcher_charged_seconds"]
    target = min(new_end, old_end)
    return dict(
        target_logical_seconds=target,
        new_final_logical_seconds=new_end,
        V8_final_logical_seconds=old_end,
        new=retained_before(new, target),
        V8=retained_before(old, target),
        interpolation_used=False,
        selected_by_reference_error=False,
    )
