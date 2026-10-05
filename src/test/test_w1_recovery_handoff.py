"""V27 pure fixtures for actual sealing/consumers and bounded admission.

The small manifest is explicitly fixture-only: no Basix, FE or generator.
"""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from src.io.finite_json import atomic_json
from src.io.w1_evidence import file_receipt, scientific_identity
from src.io.w1_recovery_commit import commit_recovery
from src.io import w1_receiver_contract as contract
from src.runners.w1_admission_scope import body_sha, validate_scope
from src.runners.task042_shared import spare_cores
from src.runners.w1_component_receiver import compute_stage_deadline, prepare_B_window
from src.test.test_w1_input_recovery import receipt_fixture


def topology():
    return [
        {"cpu": i, "core": i % 4, "socket": 0, "siblings": [i % 4, i % 4 + 4]}
        for i in range(8)
    ]


@pytest.mark.parametrize(
    "case", ["busy_original", "all_busy", "SMT", "sleeping_narrow"]
)
def test_current_scope_preserves_protection(case):
    rows, busy = [], {i: 0.0 for i in range(8)}
    if case == "busy_original":
        busy[0] = 0.1
        assert 1 in spare_cores(topology(), rows, busy, {})
        assert 0 not in spare_cores(topology(), rows, busy, {})
    elif case == "all_busy":
        assert not spare_cores(topology(), rows, {i: 0.051 for i in range(8)}, {})
    else:
        rows = [
            {
                "pid": 100,
                "start_ticks": 7,
                "threads": [{"tid": 101, "cpu": 4, "affinity": [4], "start_ticks": 8}],
            }
        ]
        candidates = spare_cores(topology(), rows, busy, {101: 0})
        assert 0 not in candidates and 4 not in candidates and 1 in candidates


def scope_fixture():
    value = {
        "schema": "w1-allowed-core-scope.v1",
        "pid": 100,
        "start_ticks": 7,
        "owner_uid": os.getuid(),
        "allowed_cpus": list(range(8)),
        "cpuset_cpus": list(range(8)),
        "topology": topology(),
        "preferred_cpu": 0,
    }
    return {**value, "body_sha256": body_sha(value)}


@pytest.mark.parametrize("damage", ["hash", "range", "cpuset", "PID_reuse"])
def test_scope_identity_and_cpuset_reject(tmp_path, damage):
    value = scope_fixture()
    assert validate_scope(value, current_cpuset={1, 2}, proc_root=tmp_path) == [1, 2]
    current = set(range(8))
    if damage == "hash":
        value["body_sha256"] = "0" * 64
    elif damage == "range":
        value["allowed_cpus"].append(99)
    elif damage == "cpuset":
        current = {99}
    else:
        p = tmp_path / "100"
        p.mkdir()
        fields = ["0"] * 37
        fields[0], fields[19] = "S", "99"
        (p / "stat").write_text("100 (fixture) " + " ".join(fields))
    with pytest.raises(ValueError):
        validate_scope(value, current_cpuset=current, proc_root=tmp_path)


def test_unmatched_self_and_failed_sample_are_retained(monkeypatch):
    import src.runners.task042_shared as resource
    import src.runners.w1_admission_scope as scopes

    sink = []
    monkeypatch.setattr(resource, "proc_stats", lambda: {})
    monkeypatch.setattr(scopes, "validate_scope", lambda value: [0])
    monkeypatch.setattr(resource, "_thread_ticks", lambda: {})
    monkeypatch.setattr(resource, "_cpu_ticks", lambda: {0: (100, 0, 0, 0, 0, 0, 0, 0)})
    monkeypatch.setattr(resource.os, "sched_getaffinity", lambda pid: {0})
    monkeypatch.setattr(resource.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        resource, "shared_envelope", lambda: {"launch_cap_bytes": resource.HARD}
    )
    monkeypatch.setattr(
        resource, "pressure", lambda: {"some": {"avg10": 0}, "full": {"avg10": 0}}
    )
    monkeypatch.setattr(
        resource.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="", returncode=0),
    )
    with pytest.raises(RuntimeError, match="No audited"):
        resource.audit(
            observed_activity=True,
            compensate_self=True,
            observation_sink=sink.append,
            candidate_scope=scope_fixture(),
        )
    assert sink[0]["pinned_observer_self_compensation"]["subtracted_ticks"] == 0
    assert sink[0]["pinned_observer_self_compensation"]["identity_matched"] is False
    assert sink[0]["per_core_exclusion_reasons"]["0"]
    assert sink[0]["raw_cpu_busy_fractions"][0] == 1


def handoff_fixture(tmp_path, monkeypatch):
    _, old_manifest, value, _, _ = receipt_fixture(tmp_path)
    output = old_manifest.parent
    run = output / "input_recovery"
    run.mkdir()
    rows = []
    for index, (side, pol) in enumerate(
        [("top", "s"), ("top", "p"), ("bottom", "s"), ("bottom", "p")]
    ):
        rows.append(
            {
                "side": side,
                "m": 0,
                "n": 0,
                "polarization": pol,
                "mode_index": index,
                "projection_denominator": 1.0,
                **{
                    f: [{"real": 0.0, "imag": 0.0}] * 3
                    for f in ("k_vector", "e_vector", "traction_vector")
                },
            }
        )
    manifest = run / "manifest.json"
    atomic_json(manifest, {"fixture_only": True, "modes": rows})
    manifest_sha = contract.digest(manifest)
    key_sha = hashlib.sha256(
        json.dumps(
            [[r["side"], r["m"], r["n"], r["polarization"]] for r in rows],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(contract, "MANIFEST_SHA", manifest_sha)
    monkeypatch.setattr(contract, "MANIFEST_BYTES", manifest.stat().st_size)
    monkeypatch.setattr(contract, "KEY_SHA", key_sha)
    original_inventory = contract.validate_inventory
    monkeypatch.setattr(
        contract,
        "validate_inventory",
        lambda doc, ledger: original_inventory(doc, ledger, count=4, key_sha=key_sha),
    )
    datum = output / "fixture.dat"
    datum.write_text("fixture only, no worker\n")
    qualification = output / "fixture_qualification.json"
    qualification.write_text("{}")
    window_path = output / "window.json"
    now = time.monotonic()
    window = {
        "schema": "task42extra.w1-receiver-P0RB-window.v27",
        "budget_seconds": 10800,
        "origin_monotonic": now - 1799,
        "deadline_monotonic": now + 9001,
        "deadline_utc": (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=9001)
        ).isoformat(),
        "T0_utc": (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1799)
        ).isoformat(),
        "P0_budget_seconds": 1800,
        "R_stage_budget_seconds": 900,
        "admission_samples_limit": 12,
        "foreground_wait_limit_seconds": 300,
        "numerical_and_checker_budget_seconds": 7200,
        "delivery_reserve_seconds": 1800,
        "old_v26_window_preserved": True,
        "input_binding_file": str(output / "inputs.json"),
    }
    atomic_json(window_path, window)
    spec = {
        "manifest_path": str(manifest),
        "ledger_path": str(run / "final_receipt.json"),
        "math_commit": contract.MATH_COMMIT,
        "input_origin": "bitwise_reproduced_v26",
        "output_root": str(output),
        "window_path": str(window_path),
        "A_qualification_path": str(qualification),
        "stage": "input_recovery",
        "path": str(datum),
        "input_sha256": contract.digest(datum),
    }
    binding = {
        "stage": "input_recovery",
        "receiver_source_sha": "a" * 40,
        "math_source_sha": contract.MATH_COMMIT,
        "spec": spec,
        "contract": spec,
        "original_inputs": {"received": False},
        "receiver_files": {},
        "source_manifest_sha256": "0" * 64,
        "window_sha256": contract.digest(window_path),
    }
    atomic_json(run / "binding.json", binding)
    candidate = {
        **value,
        "status": "BITWISE_REPRODUCED_INPUT_PENDING_RECEIPT",
        "manifest": file_receipt(manifest),
        "git_sources": [
            {**r, "kind": "git_blob", "commit": contract.MATH_COMMIT}
            for r in value["git_sources"]
        ],
    }
    for key in ("schema", "binding", "candidate", "supervision"):
        candidate.pop(key, None)
    atomic_json(run / "recovery_candidate.json", candidate)
    component = {
        **candidate,
        "receiver_source_sha": "a" * 40,
        "binding_sha256": contract.digest(run / "binding.json"),
    }
    atomic_json(run / "component_result.json", component)
    atomic_json(
        run / "supervisor_summary.json",
        json.loads((output / "supervision.json").read_text()),
    )
    result = {
        "receiver_classification": "COMPLETED",
        "receiver_exit_code": 0,
        "receiver_source_sha": "a" * 40,
        "binding_sha256": contract.digest(run / "binding.json"),
        "worker_started": True,
        "cleared": True,
    }
    atomic_json(
        output / "P0_complete.json",
        {
            "window_sha256": contract.digest(window_path),
            "P0_elapsed_seconds": 1799,
            "qualification_sha256": contract.digest(qualification),
        },
    )
    return run, spec, window, result, binding


def test_actual_R_writer_seal_reopen_consumer(tmp_path, monkeypatch):
    run, spec, window, result, binding = handoff_fixture(tmp_path, monkeypatch)
    commit_recovery(run, spec, window, result)
    original = contract.validate_originals(spec)
    assert original["received"] is True
    marker = json.loads(Path(window["input_binding_file"]).read_text())
    assert marker["original_inputs"] == original
    prepare_B_window({**spec, "stage": "control"}, original)
    evidence = json.loads((run / "evidence.json").read_text())
    assert evidence["scientific_identity"] == scientific_identity(binding)
    assert len(evidence["git_sources"]) == 6 and evidence["raw_files"]


@pytest.mark.parametrize(
    "damage",
    ["git", "manifest", "updated_hash_bad_manifest", "supervision", "missing_artifact"],
)
def test_R_seal_failure_never_publishes_inputs(tmp_path, monkeypatch, damage):
    run, spec, window, result, _ = handoff_fixture(tmp_path, monkeypatch)
    path = run / "component_result.json"
    component = json.loads(path.read_text())
    if damage == "git":
        component["git_sources"][0]["sha256"] = "0" * 64
        atomic_json(path, component)
    elif damage in ("manifest", "updated_hash_bad_manifest"):
        Path(spec["manifest_path"]).write_text('{"damaged":true}')
        if damage == "updated_hash_bad_manifest":
            component["manifest"] = file_receipt(spec["manifest_path"])
            atomic_json(path, component)
    elif damage == "supervision":
        summary = json.loads((run / "supervisor_summary.json").read_text())
        summary["descendants_cleared"] = False
        atomic_json(run / "supervisor_summary.json", summary)
    else:
        Path(spec["manifest_path"]).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        commit_recovery(run, spec, window, result)
    assert not Path(window["input_binding_file"]).exists()
    assert not Path(spec["ledger_path"]).exists()


def test_P0_and_R_clocks_are_separate():
    window = {
        "schema": "task42extra.w1-receiver-P0RB-window.v27",
        "origin_monotonic": 0,
        "deadline_monotonic": 10800,
    }
    assert compute_stage_deadline(window, 1799, 0, "input_recovery", now=1799) == 2699
    assert compute_stage_deadline(window, 1801, 60, "input_recovery", now=1801) == 2701
    assert compute_stage_deadline(window, 7900, 0, "input_recovery", now=7900) == 8800
    for origin, used in [(8950, 0), (2000, 7100)]:
        with pytest.raises(TimeoutError):
            compute_stage_deadline(window, origin, used, "input_recovery", now=origin)


def test_shared_admission_budget_does_not_reset(tmp_path):
    from src.runners.w1_admission_budget import update_budget

    path = tmp_path / "window.json"
    atomic_json(path, {"schema": "task42extra.w1-receiver-P0RB-window.v27"})
    for index in range(12):
        update_budget(path)
        update_budget(
            path, {"kind": "admission", "elapsed_seconds": 1, "inner": index % 2 == 1}
        )
    with pytest.raises(TimeoutError):
        update_budget(path)
    assert (
        json.loads((tmp_path / "resource_samples.json").read_text())[
            "admission_samples"
        ]
        == 12
    )


def test_bad_git_type_is_not_an_artifact_escape(tmp_path, monkeypatch):
    run, spec, window, result, _ = handoff_fixture(tmp_path, monkeypatch)
    p = run / "component_result.json"
    c = json.loads(p.read_text())
    c["git_sources"][0]["kind"] = "ignore_me"
    atomic_json(p, c)
    with pytest.raises(ValueError, match="TYPED"):
        commit_recovery(run, spec, window, result)


@pytest.mark.parametrize("damage", ["sealed_evidence", "receiver_result", "candidate"])
def test_saved_R_proof_damage_refused(tmp_path, monkeypatch, damage):
    run, spec, window, result, _ = handoff_fixture(tmp_path, monkeypatch)
    commit_recovery(run, spec, window, result)
    receipt = json.loads(Path(spec["ledger_path"]).read_text())
    Path(receipt[damage]["path"]).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        contract.validate_originals(spec)


def test_actual_audit_searches_original_range_using_new_sample(monkeypatch):
    import src.runners.task042_shared as r
    import src.runners.w1_admission_scope as s

    sink = []
    samples = iter(
        [
            {0: (100, 0, 0, 1000, 0, 0, 0, 0), 1: (100, 0, 0, 1000, 0, 0, 0, 0)},
            {0: (110, 0, 0, 1010, 0, 0, 0, 0), 1: (100, 0, 0, 1020, 0, 0, 0, 0)},
        ]
    )
    monkeypatch.setattr(r, "proc_stats", lambda: {})
    monkeypatch.setattr(r, "_thread_ticks", lambda: {})
    monkeypatch.setattr(r, "_cpu_ticks", lambda: next(samples))
    monkeypatch.setattr(r.os, "sched_getaffinity", lambda pid: {0})
    monkeypatch.setattr(r.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(r, "shared_envelope", lambda: {"launch_cap_bytes": r.HARD})
    monkeypatch.setattr(
        r, "pressure", lambda: {"some": {"avg10": 0}, "full": {"avg10": 0}}
    )
    monkeypatch.setattr(
        r.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", returncode=0)
    )
    monkeypatch.setattr(s, "validate_scope", lambda scope: [0, 1])
    value = r.audit(
        observed_activity=True,
        compensate_self=True,
        candidate_scope=scope_fixture(),
        observation_sink=sink.append,
    )
    assert value["cpu"] == 1 and value["candidate_cpus"] == [1]
    assert value["observer_affinity"] == [0] and value["allowed_candidate_cpus"] == [
        0,
        1,
    ]
    assert value["cpu_busy_fractions"][0] == 0.5 and sink


def test_generator_claim_is_single_across_namespaces(tmp_path):
    from src.runners.w1_input_recovery import claim_generator

    path = claim_generator(tmp_path, "a" * 40)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        claim_generator(tmp_path, "b" * 40)
    assert path.read_bytes() == original
