"""Actual retained boundaries, inherited time, and no best-state selection."""

import hashlib
import json

from src.solvers.feinn_common_wall import common_wall_pair, retained_before


def make_index(tmp_path, name, times, *, new=False):
    directory = tmp_path / name
    directory.mkdir()
    records = []
    for j, (elapsed, retained) in enumerate(times):
        file = directory / f"state_{j}.pt"
        if retained:
            file.write_bytes(b"state")
        meta = dict(
            source_sha=name,
            elapsed_charged_seconds=elapsed,
            logical_path_seconds=elapsed + 500 if new else elapsed,
        )
        records.append(
            dict(
                name=file.name,
                generation=j,
                retained=retained,
                sha256="bound-hash",
                metadata=meta,
            )
        )
    p = directory / "index.json"
    p.write_text(json.dumps(dict(checkpoints=records)))
    return dict(
        source_sha=name,
        files=dict(
            checkpoint_index=dict(
                path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()
            ),
            durable_final=dict(path=str(directory / "final.pt")),
        ),
        result=dict(
            logical_path_seconds=700 if new else None, launcher_charged_seconds=900
        ),
    )


def test_common_wall_chooses_nearest_retained_before_target_and_reports_gap(tmp_path):
    new = make_index(
        tmp_path, "new", [(1, True), (100, True), (150, False), (210, True)], new=True
    )
    old = make_index(
        tmp_path, "old", [(100, True), (620, True), (690, False), (800, True)]
    )
    pair = common_wall_pair(new, old)
    assert pair["target_logical_seconds"] == 700
    assert pair["new"]["generation"] == 1 and pair["new"]["gap_seconds"] == 100
    assert pair["V8"]["generation"] == 1 and pair["V8"]["gap_seconds"] == 80
    assert not pair["selected_by_reference_error"]
    assert retained_before(new, 499)["status"] == "NOT_RETAINED"
