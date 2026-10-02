"""Own durable recovery must preserve identity, tail work and quotas."""

import json
from pathlib import Path

import pytest

from src.runners.feinn_gn_recovery import file_identity, recovery_boundary


def fixture(tmp_path):
    name = "task42extra_v10_phase_cached_gn_20261002T000000Z"
    run = tmp_path / "tmp/task42extra/runs" / name
    artifact = tmp_path / "benchmarks/artifacts/task42extra" / name
    checkpoints = artifact / "durable_checkpoints"
    run.mkdir(parents=True)
    checkpoints.mkdir(parents=True)
    pt = checkpoints / "committed_000006.pt"
    pt.write_bytes(b"unit opaque checkpoint, not a numerical state")
    meta = dict(
        run_id=name,
        source_sha="old-source",
        state_kind="accepted_outer",
        route="V10-PHASE-CACHED-GN-CONTINUE",
        stage="DAMPED_GN",
        reference_used_for_training=False,
        features_reference_exposed=False,
        pde_only_solve=True,
        production_initialization_allowed=False,
        counts=dict(K=233, full_loss_gradient=6, trial_loss=9),
        JVP_VJP_counts=dict(JVP=233, VJP=239),
        inherited_prefix_seconds=10626.0,
    )
    pointer = checkpoints / "current.json"
    pointer.write_text(
        json.dumps(
            dict(
                current=dict(
                    name=pt.name, sha256=file_identity(pt)["sha256"], metadata=meta
                )
            )
        )
    )
    manifest = dict(stage="v10_phase_cached_gn", source_sha="old-source")
    (run / "run_manifest.json").write_text(json.dumps(manifest))
    summary = dict(
        descendants_cleared=True, classification="RESOURCE_WINDOW_UNAVAILABLE"
    )
    (run / "run_summary.json").write_text(json.dumps(summary))
    events = [
        dict(kind="DURABLE_ACCEPTED", checkpoint_sha256=file_identity(pt)["sha256"]),
        dict(
            kind="WORK_EVENT",
            operation="GRADIENT",
            phase="end",
            counts=dict(K=233, full_loss_gradient=7),
            JVP_VJP_counts=dict(JVP=233, VJP=240),
        ),
        dict(
            kind="WORK_EVENT",
            operation="K",
            phase="begin",
            counts=dict(K=257, full_loss_gradient=7, trial_loss=9),
            JVP_VJP_counts=dict(JVP=257, VJP=264),
        ),
    ]
    history = artifact / "history.jsonl"
    history.write_text("\n".join(json.dumps(x) for x in events) + '\n{"incomplete"')
    return [dict(path=str(run / "run_summary.json"))], pointer, history


def test_latest_boundary_preserves_uncommitted_completed_work(tmp_path):
    prior, pointer, _ = fixture(tmp_path)
    result = recovery_boundary(tmp_path, "v10_phase_cached_gn", prior)
    assert (
        result["durable_final"]["sha256"]
        == file_identity(pointer.parent / "committed_000006.pt")["sha256"]
    )
    assert result["spent_counts_lower_bound"]["K"] == 257
    assert result["spent_JVP_VJP_lower_bound"] == dict(JVP=257, VJP=264)
    assert result["incomplete_work_quota_reserve"] == dict(K=1, JVP_VJP=2, trial=0)
    assert result["original_V9_logical_prefix_seconds"] == 10626.0


@pytest.mark.parametrize(
    "change", ["label", "source", "bytes", "uncleared", "pc", "too_many"]
)
def test_identity_and_unretained_work_cannot_be_replayed(tmp_path, change):
    prior, pointer, history = fixture(tmp_path)
    record = json.loads(pointer.read_text())
    if change == "label":
        record["current"]["metadata"]["reference_used_for_training"] = True
    if change == "source":
        record["current"]["metadata"]["source_sha"] = "different"
    pointer.write_text(json.dumps(record))
    if change == "bytes":
        (pointer.parent / "committed_000006.pt").write_bytes(b"changed")
    if change == "uncleared":
        Path(prior[0]["path"]).write_text(
            json.dumps(
                dict(
                    descendants_cleared=False,
                    classification="RESOURCE_WINDOW_UNAVAILABLE",
                )
            )
        )
    if change == "pc":
        with history.open("a") as stream:
            stream.write(
                "\n"
                + json.dumps(
                    dict(kind="WORK_EVENT", operation="PC_BUILD", phase="begin")
                )
            )
    if change == "too_many":
        prior *= 3
    with pytest.raises(RuntimeError):
        recovery_boundary(tmp_path, "v10_phase_cached_gn", prior)
