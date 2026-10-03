"""Exercise the actual parent/lock/admission/watchdog chain with a tiny leaf."""

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sys
from time import monotonic

import pytest


@pytest.mark.parametrize(
    "case", ["success", "leaf_failure", "bad_source", "bad_hash", "resource_refusal"]
)
def test_real_parent_v18_contract_with_numerical_leaf_stub(monkeypatch, tmp_path, case):
    from src.io.feinn_pilot import load_pilot
    from src.runners import feinn_attribution_campaign as c
    from src.runners import feinn_workflow as w
    from src.runners import feinn_resources as resources

    real_root = w.ROOT
    stage = "v18_saved_field_integrals"
    spec = load_pilot(real_root / "input/task042extra_feinn_5nm" / (stage + ".dat"))
    output = tmp_path / "results"
    output.mkdir()
    spec = replace(spec, expected_output_parent=output)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (tmp_path / "tmp/task42extra").mkdir(parents=True)
    (tmp_path / "tmp/task42extra/setup").mkdir()
    shutil.copy(
        real_root / "tmp/task42extra/setup/fe_abi.json",
        tmp_path / "tmp/task42extra/setup/fe_abi.json",
    )
    proof = tmp_path / "tmp/task42extra/durable" / stage / "terminal_identity.json"
    proof.parent.mkdir(parents=True)
    proof.write_text('{"fixture_only":true}')
    clock = tmp_path / "clock.json"
    clock.write_text(
        json.dumps(
            dict(start_monotonic=monotonic(), startup_unobserved_allowance_seconds=0)
        )
    )
    identity = {}
    for name in c.DEPENDENCIES[stage]:
        key = {
            "e1_fe": "native",
            "e3_reference": "reference",
            "v12_saved_state_freeze": "fields",
            "v12_saved_field_attribution": "result",
        }[name]
        leaf = artifacts / (name + ".bin")
        leaf.write_bytes(b"explicit tiny fixture; no numerical code")
        files = {key: dict(path=str(leaf), sha256=w.sha(leaf))}
        record = dict(
            source_sha="1" * 40,
            files=files,
            result=dict(
                identity=dict(
                    mesh_coordinates_sha256="mesh",
                    cell_tags_sha256="tags",
                    mode_manifest_sha256="modes",
                )
            ),
        )
        (artifacts / ("index_" + name + ".json")).write_text(json.dumps(record))
        identity[name] = dict(source_sha="1" * 40, files=files)
    campaign = tmp_path / "campaign.json"
    campaign.write_text(
        json.dumps(
            dict(batch_clock="clock.json", saved_field_design=dict(identity=identity))
        )
    )
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "V18_DESIGN_RECORD", campaign)
    monkeypatch.setattr(w, "ROOT", tmp_path)
    monkeypatch.setattr(w, "ARTIFACTS", artifacts)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TASK42EXTRA_ENV_MODE", "fe")
    original_git = w.subprocess.check_output

    def fixture_git(command, *args, **kwargs):
        if command[:2] == ["git", "rev-parse"]:
            return "2" * 40 + "\n"
        if command[:3] == ["git", "branch", "--show-current"]:
            return "task42extra_feinn_5nm\n"
        if command[:2] == ["git", "status"]:
            return " M blocked" if case == "bad_source" else ""
        return original_git(command, *args, **kwargs)

    monkeypatch.setattr(w.subprocess, "check_output", fixture_git)
    original_stability = resources.stable_window
    monkeypatch.setattr(
        resources,
        "stable_window",
        lambda directory, hard: original_stability(directory, hard, seconds=0.01),
    )
    observed = []

    def admission(hard):
        observed.append(hard)
        if case == "resource_refusal":
            raise RuntimeError("explicit fixture resource refusal")
        return dict(cpu=min(os.sched_getaffinity(0)), neighbor_processes=[])

    monkeypatch.setattr(w, "admission", admission)
    real_supervise = w.supervise
    called = []

    def bounded_real_watchdog(command, directory, **options):
        called.append(options["rss_hard_limit_bytes"])
        # Preserve the real parent-death guard. Only the numerical leaf changes.
        assert command[1:3] == ["-m", "src.runners.guarded_exec"]
        parent_dir = Path(directory).parent
        code = (
            "from pathlib import Path; import json; p=Path("
            + repr(str(parent_dir))
            + '); (p/"worker_result.json").write_text(json.dumps({"fixture_only":True})); raise SystemExit('
            + ("7" if case == "leaf_failure" else "0")
            + ")"
        )
        stub = command[:5] + [sys.executable, "-c", code]
        options.update(interval=0.05, wall_seconds=5)
        return real_supervise(stub, directory, **options)

    monkeypatch.setattr(w, "supervise", bounded_real_watchdog)
    if case == "bad_hash":
        (artifacts / "e1_fe.bin").write_bytes(b"corrupt")
    if case in ("bad_source", "bad_hash"):
        with pytest.raises(
            (RuntimeError, ValueError), match="clean committed|ARTIFACT_IDENTITY"
        ):
            w.launch(spec)
        assert not called
        return
    summary = w.launch(spec)
    assert observed == [16 * 2**30]
    assert summary["descendants_cleared"]
    if case == "resource_refusal":
        assert summary["classification"] == "RESOURCE_WINDOW_UNAVAILABLE" and not called
        return
    assert called == [16 * 2**30]
    assert summary["classification"] == (
        "WORKER_FAILED" if case == "leaf_failure" else "COMPLETED"
    )
    directory = Path(summary["directory"])
    state = json.loads((directory / "run_manifest.json").read_text())
    assert state["v18_review_sha"] == c.V18_REVIEW_SHA
    assert state["v18_diagnostic_design_sha256"] == w.sha(campaign)
    assert state["gram_loaded_by_route"] is False and state["gram_sha256"] is None
    assert state["supervision_budget_origin_monotonic"] < monotonic()
    assert state["watchdog_terminal_cutoff_reserve_seconds"] == 150
    assert (
        state["frozen_dependencies_before_worker_launch"]["e1_fe"]["files"]
        == identity["e1_fe"]["files"]
    )
    assert (directory / "worker_result.json").exists() and (
        directory / "run_summary.json"
    ).exists()
