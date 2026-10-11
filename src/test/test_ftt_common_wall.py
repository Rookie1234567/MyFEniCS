import copy
import json
from dataclasses import replace

import pytest

from src.postprocessing.ftt_common_wall import select_common_wall


def example():
    histories = {
        "learned": [
            {
                "kind": "core",
                "elapsed_route_seconds": t,
                "committed_checkpoint_sha256": "l" + str(t),
            }
            for t in (2, 6, 12)
        ],
        "freeze": [
            {
                "kind": "core",
                "elapsed_route_seconds": t,
                "committed_checkpoint_sha256": "f" + str(t),
            }
            for t in (3, 8, 10)
        ],
    }
    indices = {
        n: [
            {"sha256": r["committed_checkpoint_sha256"], "retained": True} for r in rows
        ]
        for n, rows in histories.items()
    }
    return histories, indices


def test_shared_wall_latest_committed_state_and_no_label_selection():
    histories, indices = example()
    first = select_common_wall(histories, indices)
    assert first["common_new_wall_seconds"] == 10
    assert first["selected"]["learned"]["elapsed_route_seconds"] == 6
    assert first["selected"]["freeze"]["elapsed_route_seconds"] == 10
    changed = copy.deepcopy(histories)
    for n, rows in changed.items():
        for i, row in enumerate(rows):
            row.update(reference_error=float("nan"), native=1000 - i)
    assert select_common_wall(changed, indices) == first
    assert not first["selection_uses_reference"]


def test_unretained_and_nonfinite_boundary_are_not_legal_partial_scores():
    histories, indices = example()
    indices["learned"][0]["retained"] = False
    with pytest.raises(ValueError, match="NOT_RETAINED"):
        select_common_wall(histories, indices)
    histories, indices = example()
    histories["learned"][0]["elapsed_route_seconds"] = float("nan")
    with pytest.raises(ValueError, match="NONFINITE"):
        select_common_wall(histories, indices)


def test_post_compare_hook_is_opt_in_and_old_default_unchanged(tmp_path, monkeypatch):
    import src.runners.ftt_core_worker as worker
    from src.io.neural_wave_campaign import digest

    path = tmp_path / "design.json"
    path.write_text(json.dumps({}))
    manifest = {
        "spec": {"role": worker.DEFAULT_PROFILE.compare_role},
        "design_sha256": digest(path),
    }
    old = replace(worker.DEFAULT_PROFILE, design=path)
    assert old.compare_postprocess is None
    monkeypatch.setattr(worker, "independent_compare", lambda *_: {"complete": True})
    assert worker.run_stage(manifest, tmp_path, None, tmp_path, old) == {
        "complete": True
    }
    called = []

    def extra(*args):
        called.append(args)
        return {"selection_uses_reference": False}

    new = replace(old, compare_postprocess=extra)
    result = worker.run_stage(manifest, tmp_path, None, tmp_path, new)
    assert len(called) == 1 and result["post_compare_record"] == {
        "selection_uses_reference": False
    }
